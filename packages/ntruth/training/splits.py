"""Split deterministici group-aware per impedire leakage tra record correlati."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

from ntruth.governance.lineage import CorpusSplit
from ntruth.training.records import (
    DuplicateDecision,
    IssueSeverity,
    NormalizedRecord,
    SplitRatios,
    ValidationIssue,
    canonical_json,
    normalize_text,
)

_INTERNAL_SPLITS = (
    CorpusSplit.TRAIN,
    CorpusSplit.VALIDATION,
    CorpusSplit.TEST,
)
_RESTRICTIVENESS = {
    CorpusSplit.TRAIN: 0,
    CorpusSplit.VALIDATION: 1,
    CorpusSplit.TEST: 2,
    CorpusSplit.EXTERNAL: 3,
}


@dataclass(frozen=True, slots=True)
class SplitAssignment:
    record_id: str
    leakage_group_id: str
    split: CorpusSplit


@dataclass(frozen=True, slots=True)
class SplitResult:
    assignments: tuple[SplitAssignment, ...]
    issues: tuple[ValidationIssue, ...]
    leakage_group_count: int


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, index: int) -> int:
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def leakage_tokens(record: NormalizedRecord) -> tuple[str, ...]:
    """Restituisce identita conservativamente normalizzate che legano i record."""

    provenance = record.record.provenance
    tokens = {
        f"source:{normalize_text(provenance.source_id)}",
        f"source_asset:{normalize_text(provenance.source_asset_id)}",
        f"source_sha256:{provenance.source_sha256}",
    }
    if provenance.publication_id is not None:
        tokens.add(f"publication:{normalize_text(provenance.publication_id)}")
    if provenance.project_id is not None:
        tokens.add(f"project:{normalize_text(provenance.project_id)}")
    if provenance.bundle_id is not None:
        tokens.add(f"bundle:{normalize_text(provenance.bundle_id)}")
    if provenance.laboratory_id is not None:
        tokens.add(f"laboratory:{normalize_text(provenance.laboratory_id)}")
    if provenance.corresponding_author_id is not None:
        tokens.add(f"corresponding_author:{normalize_text(provenance.corresponding_author_id)}")
    return tuple(sorted(tokens))


def _stable_number(*parts: str) -> int:
    payload = "\x1f".join(parts).encode("utf-8")
    return int(hashlib.sha256(payload).hexdigest(), 16)


def _connected_components(
    records: tuple[NormalizedRecord, ...],
    duplicate_decisions: tuple[DuplicateDecision, ...] = (),
    related_record_pairs: tuple[tuple[str, str], ...] = (),
) -> tuple[tuple[tuple[NormalizedRecord, ...], tuple[str, ...]], ...]:
    union_find = _UnionFind(len(records))
    index_by_record_id = {record.record.record_id: index for index, record in enumerate(records)}
    first_by_token: dict[str, int] = {}
    tokens_by_index: list[tuple[str, ...]] = []
    for index, record in enumerate(records):
        tokens = leakage_tokens(record)
        tokens_by_index.append(tokens)
        for token in tokens:
            previous = first_by_token.setdefault(token, index)
            union_find.union(index, previous)

    # Un duplicato scartato puo essere l'unico portatore di un vincolo test/external
    # o di una identita di provenance. Collegarlo al canonico prima di calcolare le
    # componenti conserva entrambi anche se soltanto il canonico verra esportato.
    for decision in duplicate_decisions:
        try:
            duplicate_index = index_by_record_id[decision.duplicate_record_id]
            canonical_index = index_by_record_id[decision.canonical_record_id]
        except KeyError as exc:
            raise ValueError("decisione di deduplica riferita a record sconosciuto") from exc
        union_find.union(duplicate_index, canonical_index)

    for left_id, right_id in related_record_pairs:
        try:
            left_index = index_by_record_id[left_id]
            right_index = index_by_record_id[right_id]
        except KeyError as exc:
            raise ValueError("collegamento di leakage riferito a record sconosciuto") from exc
        union_find.union(left_index, right_index)

    members_by_root: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        members_by_root[union_find.find(index)].append(index)

    components: list[tuple[tuple[NormalizedRecord, ...], tuple[str, ...]]] = []
    for member_indices in members_by_root.values():
        members = tuple(
            sorted(
                (records[index] for index in member_indices),
                key=lambda item: item.record.record_id,
            )
        )
        component_tokens = tuple(
            sorted({token for index in member_indices for token in tokens_by_index[index]})
        )
        components.append((members, component_tokens))
    return tuple(
        sorted(
            components,
            key=lambda component: tuple(item.record.record_id for item in component[0]),
        )
    )


def _group_id(tokens: tuple[str, ...]) -> str:
    digest = hashlib.sha256(canonical_json(tokens).encode("utf-8")).hexdigest()
    return f"leakage-{digest[:20]}"


def _component_requested_split(
    members: tuple[NormalizedRecord, ...],
) -> tuple[CorpusSplit | None, tuple[ValidationIssue, ...]]:
    requested = {
        member.record.requested_split
        for member in members
        if member.record.requested_split is not None
    }
    synthetic = any(member.record.provenance.synthetic for member in members)
    record_ids = tuple(member.record.record_id for member in members)
    issues: list[ValidationIssue] = []
    if len(requested) > 1:
        issues.append(
            ValidationIssue(
                code="conflicting_requested_splits",
                severity=IssueSeverity.ERROR,
                detail="record collegati richiedono split incompatibili",
                record_ids=record_ids,
            )
        )
    selected = max(requested, key=lambda item: _RESTRICTIVENESS[item]) if requested else None
    if synthetic and selected not in {None, CorpusSplit.TRAIN}:
        issues.append(
            ValidationIssue(
                code="synthetic_group_non_train",
                severity=IssueSeverity.ERROR,
                detail=(
                    "un componente contenente dati sintetici e collegato a uno split non-train"
                ),
                record_ids=record_ids,
            )
        )
    if synthetic:
        selected = CorpusSplit.TRAIN
    return selected, tuple(issues)


def _allocation_error(
    counts: dict[CorpusSplit, int],
    targets: dict[CorpusSplit, float],
    split: CorpusSplit,
    group_size: int,
) -> float:
    return sum(
        (counts[current] + (group_size if current is split else 0) - targets[current]) ** 2
        for current in _INTERNAL_SPLITS
    )


def assign_group_aware_splits(
    records: tuple[NormalizedRecord, ...],
    *,
    ratios: SplitRatios,
    seed: str,
    duplicate_decisions: tuple[DuplicateDecision, ...] = (),
    related_record_pairs: tuple[tuple[str, str], ...] = (),
) -> SplitResult:
    """Assegna componenti di provenance e duplicazione, mai singole righe."""

    components = _connected_components(records, duplicate_decisions, related_record_pairs)
    component_data: list[tuple[str, tuple[NormalizedRecord, ...], CorpusSplit | None]] = []
    issues: list[ValidationIssue] = []
    for members, tokens in components:
        requested_split, component_issues = _component_requested_split(members)
        issues.extend(component_issues)
        component_data.append((_group_id(tokens), members, requested_split))

    assignments_by_group: dict[str, CorpusSplit] = {}
    counts = {split: 0 for split in _INTERNAL_SPLITS}
    external_count = 0
    unassigned: list[tuple[str, tuple[NormalizedRecord, ...]]] = []
    for group_id, members, requested_split in component_data:
        if requested_split is None:
            unassigned.append((group_id, members))
            continue
        assignments_by_group[group_id] = requested_split
        if requested_split is CorpusSplit.EXTERNAL:
            external_count += len(members)
        else:
            counts[requested_split] += len(members)

    internal_total = len(records) - external_count
    targets = {split: ratio * internal_total for split, ratio in ratios.as_dict().items()}
    unassigned.sort(
        key=lambda item: (
            -len(item[1]),
            _stable_number(seed, item[0]),
            item[0],
        )
    )
    for group_id, members in unassigned:
        group_size = len(members)
        selected = min(
            _INTERNAL_SPLITS,
            key=lambda split: (
                _allocation_error(counts, targets, split, group_size),
                _stable_number(seed, group_id, split.value),
                split.value,
            ),
        )
        assignments_by_group[group_id] = selected
        counts[selected] += group_size

    assignments = tuple(
        sorted(
            (
                SplitAssignment(
                    record_id=member.record.record_id,
                    leakage_group_id=group_id,
                    split=assignments_by_group[group_id],
                )
                for group_id, members, _ in component_data
                for member in members
            ),
            key=lambda assignment: assignment.record_id,
        )
    )
    leakage_issues = validate_no_group_leakage(
        records,
        assignments,
        related_record_pairs=related_record_pairs,
    )
    return SplitResult(
        assignments=assignments,
        issues=tuple(
            sorted(
                (*issues, *leakage_issues),
                key=lambda issue: (issue.code, issue.record_ids),
            )
        ),
        leakage_group_count=len(components),
    )


def validate_no_group_leakage(
    records: tuple[NormalizedRecord, ...],
    assignments: tuple[SplitAssignment, ...],
    *,
    related_record_pairs: tuple[tuple[str, str], ...] = (),
) -> tuple[ValidationIssue, ...]:
    """Controlla provenance e relazioni near-duplicate contro gli split."""

    assignment_by_id = {assignment.record_id: assignment for assignment in assignments}
    splits_by_token: dict[str, set[CorpusSplit]] = defaultdict(set)
    record_ids_by_token: dict[str, set[str]] = defaultdict(set)
    for record in records:
        record_id = record.record.record_id
        assignment = assignment_by_id.get(record_id)
        if assignment is None:
            continue
        for token in leakage_tokens(record):
            splits_by_token[token].add(assignment.split)
            record_ids_by_token[token].add(record_id)
    issues = [
        ValidationIssue(
            code="cross_split_leakage",
            severity=IssueSeverity.ERROR,
            detail=f"l'identita condivisa {token!r} attraversa split differenti",
            record_ids=tuple(sorted(record_ids_by_token[token])),
        )
        for token in sorted(splits_by_token)
        if len(splits_by_token[token]) > 1
    ]
    for left_id, right_id in related_record_pairs:
        left = assignment_by_id.get(left_id)
        right = assignment_by_id.get(right_id)
        if left is None or right is None:
            raise ValueError("collegamento di leakage riferito a record senza assegnazione")
        if left.split is right.split:
            continue
        issues.append(
            ValidationIssue(
                code="cross_split_near_duplicate",
                severity=IssueSeverity.ERROR,
                detail="input near-duplicate assegnati a split differenti",
                record_ids=tuple(sorted((left_id, right_id))),
            )
        )
    return tuple(sorted(issues, key=lambda issue: (issue.code, issue.record_ids)))
