"""Deduplica esatta e near-duplicate conservativa dei record supervisionati."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ntruth.training.records import (
    AnnotationStatus,
    DuplicateDecision,
    DuplicateKind,
    IssueSeverity,
    NormalizedRecord,
    ValidationIssue,
    jaccard_similarity,
    normalize_text,
)

_STATUS_PRIORITY = {
    AnnotationStatus.CANDIDATE: 0,
    AnnotationStatus.SINGLE_REVIEWED: 1,
    AnnotationStatus.DOUBLE_REVIEWED: 2,
    AnnotationStatus.ADJUDICATED: 3,
}


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    kept: tuple[NormalizedRecord, ...]
    decisions: tuple[DuplicateDecision, ...]
    leakage_links: tuple[tuple[str, str], ...]
    issues: tuple[ValidationIssue, ...]


def canonical_rank(record: NormalizedRecord) -> tuple[int, int, str]:
    """Preferisce la supervisione piu matura, poi un ID stabile."""

    return (
        -_STATUS_PRIORITY[record.record.annotation_status],
        -int(record.record.training_eligible),
        record.record.record_id,
    )


def duplicate_id_issues(records: tuple[NormalizedRecord, ...]) -> tuple[ValidationIssue, ...]:
    by_id: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        by_id[record.record.record_id].append(record)
    return tuple(
        ValidationIssue(
            code="duplicate_record_id",
            severity=IssueSeverity.ERROR,
            detail="record_id ripetuto: l'identita di una riga JSONL deve essere univoca",
            record_ids=(record_id,),
        )
        for record_id, members in sorted(by_id.items())
        if len(members) > 1
    )


def _conflicting_target_issues(
    records: tuple[NormalizedRecord, ...],
) -> tuple[ValidationIssue, ...]:
    by_content: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        by_content[record.content_key].append(record)

    issues: list[ValidationIssue] = []
    for members in by_content.values():
        if len({record.canonical_target for record in members}) <= 1:
            continue
        record_ids = tuple(sorted(record.record.record_id for record in members))
        issues.append(
            ValidationIssue(
                code="conflicting_targets",
                severity=IssueSeverity.ERROR,
                detail=(
                    "lo stesso input normalizzato ha target incompatibili; "
                    "serve revisione o adjudication"
                ),
                record_ids=record_ids,
            )
        )
    return tuple(sorted(issues, key=lambda issue: issue.record_ids))


def _exact_deduplicate(
    records: tuple[NormalizedRecord, ...],
) -> tuple[tuple[NormalizedRecord, ...], tuple[DuplicateDecision, ...]]:
    by_fingerprint: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        by_fingerprint[record.exact_fingerprint].append(record)

    kept: list[NormalizedRecord] = []
    decisions: list[DuplicateDecision] = []
    for fingerprint in sorted(by_fingerprint):
        members = sorted(by_fingerprint[fingerprint], key=canonical_rank)
        canonical = members[0]
        kept.append(canonical)
        decisions.extend(
            DuplicateDecision(
                kind=DuplicateKind.EXACT,
                duplicate_record_id=duplicate.record.record_id,
                canonical_record_id=canonical.record.record_id,
                duplicate_source_asset_id=duplicate.record.provenance.source_asset_id,
                canonical_source_asset_id=canonical.record.provenance.source_asset_id,
                duplicate_fingerprint=duplicate.exact_fingerprint,
                canonical_fingerprint=canonical.exact_fingerprint,
                similarity=1.0,
                reason="fingerprint esatto su task, lingua, dominio, input e target normalizzati",
            )
            for duplicate in members[1:]
        )
    return tuple(kept), tuple(decisions)


def _near_block_key(record: NormalizedRecord) -> tuple[str, str, str | None, str]:
    source = record.record
    return (
        normalize_text(source.task),
        normalize_text(source.language),
        normalize_text(source.domain) if source.domain is not None else None,
        record.canonical_target,
    )


def _near_leakage_block_key(record: NormalizedRecord) -> tuple[str, str, str | None]:
    source = record.record
    return (
        normalize_text(source.task),
        normalize_text(source.language),
        normalize_text(source.domain) if source.domain is not None else None,
    )


def _near_leakage_links(
    records: tuple[NormalizedRecord, ...],
    *,
    threshold: float,
) -> tuple[tuple[str, str], ...]:
    """Collega ogni coppia near-duplicate senza usare il target come filtro.

    Il target decide se un record puo essere rimosso come duplicato, ma non se
    due input correlati possono attraversare split differenti. Per il leakage
    si conserva quindi il grafo completo delle similarita dirette sopra soglia.
    """

    by_block: dict[tuple[str, str, str | None], list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        by_block[_near_leakage_block_key(record)].append(record)

    links: list[tuple[str, str]] = []
    for block in sorted(by_block, key=repr):
        members = sorted(by_block[block], key=lambda item: item.record.record_id)
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                if jaccard_similarity(left.shingles, right.shingles) < threshold:
                    continue
                links.append((left.record.record_id, right.record.record_id))
    return tuple(links)


def _near_deduplicate(
    records: tuple[NormalizedRecord, ...],
    *,
    threshold: float,
) -> tuple[tuple[NormalizedRecord, ...], tuple[DuplicateDecision, ...]]:
    """Confronta soltanto record semanticamente compatibili e rappresentanti diretti.

    Non si usa una chiusura transitiva: una catena A~B~C non basta a eliminare C
    quando C non supera direttamente la soglia rispetto al rappresentante A.
    """

    by_block: dict[tuple[str, str, str | None, str], list[NormalizedRecord]] = defaultdict(list)
    for record in records:
        by_block[_near_block_key(record)].append(record)

    kept: list[NormalizedRecord] = []
    decisions: list[DuplicateDecision] = []
    for block in sorted(by_block, key=repr):
        representatives: list[NormalizedRecord] = []
        for candidate in sorted(by_block[block], key=canonical_rank):
            matches = [
                (jaccard_similarity(candidate.shingles, canonical.shingles), canonical)
                for canonical in representatives
            ]
            matches = [match for match in matches if match[0] >= threshold]
            if not matches:
                representatives.append(candidate)
                continue
            score, canonical = min(
                matches,
                key=lambda match: (-match[0], canonical_rank(match[1])),
            )
            decisions.append(
                DuplicateDecision(
                    kind=DuplicateKind.NEAR,
                    duplicate_record_id=candidate.record.record_id,
                    canonical_record_id=canonical.record.record_id,
                    duplicate_source_asset_id=candidate.record.provenance.source_asset_id,
                    canonical_source_asset_id=canonical.record.provenance.source_asset_id,
                    duplicate_fingerprint=candidate.exact_fingerprint,
                    canonical_fingerprint=canonical.exact_fingerprint,
                    similarity=score,
                    reason=(
                        "Jaccard degli shingle sopra soglia entro lo stesso "
                        "task/lingua/dominio/target"
                    ),
                )
            )
        kept.extend(representatives)
    return tuple(kept), tuple(decisions)


def _conflicting_duplicate_split_issues(
    records: tuple[NormalizedRecord, ...],
    decisions: tuple[DuplicateDecision, ...],
    leakage_links: tuple[tuple[str, str], ...],
) -> tuple[ValidationIssue, ...]:
    """Rifiuta vincoli di split incompatibili entro una componente duplicata.

    Le decisioni exact e near possono formare una componente transitiva. Il
    controllo deve quindi avvenire sull'intera componente prima che i record
    non canonici vengano esclusi dall'output preparato.
    """

    if not decisions and not leakage_links:
        return ()

    records_by_id = {record.record.record_id: record for record in records}
    parent = {record_id: record_id for record_id in records_by_id}

    def find(record_id: str) -> str:
        while parent[record_id] != record_id:
            parent[record_id] = parent[parent[record_id]]
            record_id = parent[record_id]
        return record_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    duplicate_ids: set[str] = set()
    for decision in decisions:
        duplicate_id = decision.duplicate_record_id
        canonical_id = decision.canonical_record_id
        if duplicate_id not in records_by_id or canonical_id not in records_by_id:
            raise ValueError("decisione di deduplica riferita a record sconosciuto")
        duplicate_ids.update((duplicate_id, canonical_id))
        union(duplicate_id, canonical_id)
    for left_id, right_id in leakage_links:
        if left_id not in records_by_id or right_id not in records_by_id:
            raise ValueError("collegamento di leakage riferito a record sconosciuto")
        duplicate_ids.update((left_id, right_id))
        union(left_id, right_id)

    members_by_root: dict[str, list[NormalizedRecord]] = defaultdict(list)
    for record_id in duplicate_ids:
        members_by_root[find(record_id)].append(records_by_id[record_id])

    issues: list[ValidationIssue] = []
    for members in members_by_root.values():
        requested = {
            member.record.requested_split
            for member in members
            if member.record.requested_split is not None
        }
        if len(requested) <= 1:
            continue
        issues.append(
            ValidationIssue(
                code="conflicting_duplicate_requested_splits",
                severity=IssueSeverity.ERROR,
                detail=(
                    "record exact/near-duplicate richiedono split incompatibili; "
                    "il vincolo non puo essere eliminato scegliendo un canonico"
                ),
                record_ids=tuple(sorted(member.record.record_id for member in members)),
            )
        )
    return tuple(sorted(issues, key=lambda issue: issue.record_ids))


def deduplicate_records(
    records: tuple[NormalizedRecord, ...],
    *,
    near_threshold: float,
) -> DeduplicationResult:
    """Deduplica in ordine stabile conservando conflitti di annotazione espliciti."""

    issues = (*duplicate_id_issues(records), *_conflicting_target_issues(records))
    exact_kept, exact_decisions = _exact_deduplicate(records)
    leakage_links = _near_leakage_links(
        exact_kept,
        threshold=near_threshold,
    )
    near_kept, near_decisions = _near_deduplicate(
        exact_kept,
        threshold=near_threshold,
    )
    decisions = (*exact_decisions, *near_decisions)
    issues = (
        *issues,
        *_conflicting_duplicate_split_issues(records, decisions, leakage_links),
    )
    return DeduplicationResult(
        kept=tuple(sorted(near_kept, key=lambda item: item.record.record_id)),
        decisions=tuple(
            sorted(
                decisions,
                key=lambda decision: (
                    decision.kind.value,
                    decision.duplicate_record_id,
                    decision.canonical_record_id,
                ),
            )
        ),
        leakage_links=leakage_links,
        issues=tuple(
            sorted(
                issues,
                key=lambda issue: (issue.code, issue.record_ids),
            )
        ),
    )
