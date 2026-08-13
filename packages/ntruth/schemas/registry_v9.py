"""PRD v9 Canonical Schema Registry draft — not frozen, not live root.

The implemented root contract remains PRD v7. This module is the machine-readable
decision pack used to generate and check names. It does not replace live models,
does not set ``normative_registry_v9_frozen=true``, and does not authorize GOLD.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from ntruth.schemas.core import Determinability, FrozenModel, content_checksum
from ntruth.schemas.counts import COUNT_KIND_ALIASES, CountKind
from ntruth.schemas.determinability_v7 import DeterminabilityStateV7, migrate_v3_state

REGISTRY_DRAFT_VERSION = "0.1.0-draft"
REGISTRY_STATUS = "PENDING_HUMAN_SCIENTIFIC_APPROVAL"
NORMATIVE_REGISTRY_V9_FROZEN = False

FORBIDDEN_CANONICAL_V9_LABELS: frozenset[str] = frozenset(
    {
        "FactorRole",
        "ContrastType",
        "ContrastSupportClaim",
        "ObservedEvidenceScope",
        "TargetPopulationClaim",
    }
)


class RegistryKind(StrEnum):
    ENUM = "enum"
    FIELD_NAME = "field_name"
    CLAIM_TYPE = "claim_type"
    ERROR_CODE = "error_code"
    COUNT_KIND = "count_kind"
    STATUS = "status"


class FieldAuthority(StrEnum):
    DECISIVE = "decisive"
    CANDIDATE_INFERENCE = "candidate_inference"


class FactorRole(StrEnum):
    ASSIGNED_INTERVENTION = "ASSIGNED_INTERVENTION"
    OBSERVATIONAL_EXPOSURE = "OBSERVATIONAL_EXPOSURE"
    INTRINSIC_ATTRIBUTE = "INTRINSIC_ATTRIBUTE"
    BLOCKING_FACTOR = "BLOCKING_FACTOR"
    BATCH_NUISANCE = "BATCH_NUISANCE"
    REPEATED_MEASURE_INDEX = "REPEATED_MEASURE_INDEX"
    MEASUREMENT_CONDITION = "MEASUREMENT_CONDITION"
    UNKNOWN = "UNKNOWN"


class ContrastType(StrEnum):
    ASSIGNED_INTERVENTION_EFFECT = "ASSIGNED_INTERVENTION_EFFECT"
    OBSERVATIONAL_ASSOCIATION = "OBSERVATIONAL_ASSOCIATION"
    INTRINSIC_ATTRIBUTE_COMPARISON = "INTRINSIC_ATTRIBUTE_COMPARISON"
    WITHIN_UNIT_REPEATED_CONTRAST = "WITHIN_UNIT_REPEATED_CONTRAST"
    NUISANCE_OR_BATCH_COMPARISON = "NUISANCE_OR_BATCH_COMPARISON"
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    UNKNOWN = "UNKNOWN"


class KnowledgeState(StrEnum):
    PRESENT = "PRESENT"
    ABSENT_EXPLICIT = "ABSENT_EXPLICIT"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTING = "CONFLICTING"


class ScenarioCompleteness(StrEnum):
    COMPLETE_UNDER_DECLARED_ASSUMPTION_SET = "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET"
    INCOMPLETE_KNOWN = "INCOMPLETE_KNOWN"
    UNKNOWN_COMPLETENESS = "UNKNOWN_COMPLETENESS"


class TargetPopulationClaimStatus(StrEnum):
    NOT_ASSESSED = "NOT_ASSESSED"
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    INSUFFICIENT = "INSUFFICIENT"
    INDETERMINATE = "INDETERMINATE"


class AmbiguousState(StrEnum):
    """States that remain expressible; silence is not absence."""

    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    INDETERMINATE = "INDETERMINATE"
    UNKNOWN = "UNKNOWN"
    NOT_REPORTED = "NOT_REPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTING_INFORMATION = "CONFLICTING_INFORMATION"
    MULTIPLE_PLAUSIBLE_GRAPHS = "MULTIPLE_PLAUSIBLE_GRAPHS"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


FACTOR_ROLE_CONTRAST_COMPATIBILITY: dict[FactorRole, frozenset[ContrastType]] = {
    FactorRole.ASSIGNED_INTERVENTION: frozenset(
        {ContrastType.ASSIGNED_INTERVENTION_EFFECT, ContrastType.DESCRIPTIVE_ONLY}
    ),
    FactorRole.OBSERVATIONAL_EXPOSURE: frozenset(
        {ContrastType.OBSERVATIONAL_ASSOCIATION, ContrastType.DESCRIPTIVE_ONLY}
    ),
    FactorRole.INTRINSIC_ATTRIBUTE: frozenset(
        {ContrastType.INTRINSIC_ATTRIBUTE_COMPARISON, ContrastType.DESCRIPTIVE_ONLY}
    ),
    FactorRole.REPEATED_MEASURE_INDEX: frozenset(
        {ContrastType.WITHIN_UNIT_REPEATED_CONTRAST, ContrastType.DESCRIPTIVE_ONLY}
    ),
    FactorRole.BLOCKING_FACTOR: frozenset({ContrastType.DESCRIPTIVE_ONLY}),
    FactorRole.BATCH_NUISANCE: frozenset(
        {ContrastType.NUISANCE_OR_BATCH_COMPARISON, ContrastType.DESCRIPTIVE_ONLY}
    ),
    FactorRole.MEASUREMENT_CONDITION: frozenset({ContrastType.DESCRIPTIVE_ONLY}),
    FactorRole.UNKNOWN: frozenset(),
}

EXPERIMENT_GRAPH_FIELD_AUTHORITY: dict[str, FieldAuthority] = {
    "FactorRole": FieldAuthority.DECISIVE,
    "ContrastType": FieldAuthority.DECISIVE,
    "ContrastSupportClaim": FieldAuthority.DECISIVE,
    "ObservedEvidenceScope": FieldAuthority.DECISIVE,
    "ExperimentalUnitClaim": FieldAuthority.DECISIVE,
    "AssignmentUnit": FieldAuthority.DECISIVE,
    "InferentialQuery": FieldAuthority.DECISIVE,
    "MaterialLineage": FieldAuthority.DECISIVE,
    "TargetPopulationClaim": FieldAuthority.CANDIDATE_INFERENCE,
    "AdequacyAssessment": FieldAuthority.CANDIDATE_INFERENCE,
    "SupportProfile": FieldAuthority.CANDIDATE_INFERENCE,
    "experimental_unit_count": FieldAuthority.CANDIDATE_INFERENCE,
}

V7_TO_V9_FIELD_MIGRATION: dict[str, dict[str, str]] = {
    "Determinability.INDETERMINATE": {
        "v9": "DeterminabilityStateV7.INSUFFICIENT_INFORMATION",
        "kind": "status",
        "mode": "explicit_alias",
    },
    "Determinability.DETERMINATE": {
        "v9": "DeterminabilityStateV7.DETERMINATE",
        "kind": "status",
        "mode": "identity",
    },
    "Determinability.MULTIPLE_PLAUSIBLE_GRAPHS": {
        "v9": "DeterminabilityStateV7.MULTIPLE_PLAUSIBLE_GRAPHS",
        "kind": "status",
        "mode": "identity",
    },
    "Determinability.CONFLICTING_INFORMATION": {
        "v9": "DeterminabilityStateV7.CONFLICTING_INFORMATION",
        "kind": "status",
        "mode": "identity",
    },
    "Factor.kind": {
        "v9": "FactorRole",
        "kind": "enum",
        "mode": "no_silent_mapping",
    },
    "Contrast": {
        "v9": "ContrastType",
        "kind": "enum",
        "mode": "no_silent_mapping",
    },
}

V7_COUNT_KIND_ALIASES: dict[str, str] = {
    alias: kind.value for alias, kind in COUNT_KIND_ALIASES.items()
}


class RegistryEntry(FrozenModel):
    name: str
    kind: RegistryKind
    values: tuple[str, ...] = ()
    authority: FieldAuthority | None = None
    notes: str = ""


class RegistryDecisionPack(FrozenModel):
    schema_version: Literal["0.1.0-draft"] = REGISTRY_DRAFT_VERSION
    artifact_type: Literal["ntruth-prd-v9-registry-decision-pack"] = (
        "ntruth-prd-v9-registry-decision-pack"
    )
    status: Literal["PENDING_HUMAN_SCIENTIFIC_APPROVAL"] = REGISTRY_STATUS
    normative_registry_v9_frozen: Literal[False] = False
    implemented_root_contract: Literal["PRD_V7"] = "PRD_V7"
    normative_target: Literal["PRD_V9"] = "PRD_V9"
    single_canonical_registry_topics: tuple[str, ...]
    entries: tuple[RegistryEntry, ...]
    ambiguous_indeterminate_states: tuple[str, ...]
    rulebook_status: str
    annotation_guideline_status: str
    experiment_graph_field_authority: dict[str, str]
    v7_to_v9_migration: dict[str, dict[str, str]]
    human_approval: Literal[None] = None
    gold_frozen: Literal[False] = False

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        payload.pop("human_approval", None)
        return content_checksum(payload)


def _enum_entry(
    name: str,
    values: type[StrEnum],
    *,
    authority: FieldAuthority | None = None,
    notes: str = "",
) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        kind=RegistryKind.ENUM,
        values=tuple(item.value for item in values),
        authority=authority,
        notes=notes,
    )


def build_registry_decision_pack() -> RegistryDecisionPack:
    entries = (
        _enum_entry(
            "FactorRole",
            FactorRole,
            authority=FieldAuthority.DECISIVE,
            notes="PRD v9 §0.3 / §7.2; not a live v7 field; adapters cannot invent it",
        ),
        _enum_entry(
            "ContrastType",
            ContrastType,
            authority=FieldAuthority.DECISIVE,
            notes="PRD v9 §0.3 / §7.3; not a live v7 field; adapters cannot invent it",
        ),
        RegistryEntry(
            name="ContrastSupportClaim",
            kind=RegistryKind.CLAIM_TYPE,
            authority=FieldAuthority.DECISIVE,
            notes="Assignment-anchored support of a contrast; a mention is not a claim",
        ),
        RegistryEntry(
            name="ObservedEvidenceScope",
            kind=RegistryKind.CLAIM_TYPE,
            authority=FieldAuthority.DECISIVE,
            notes="Descriptive scope of observed units/sources/protocols",
        ),
        RegistryEntry(
            name="TargetPopulationClaim",
            kind=RegistryKind.CLAIM_TYPE,
            authority=FieldAuthority.CANDIDATE_INFERENCE,
            notes="Optional; default NOT_ASSESSED; never inferred from observed scope",
        ),
        _enum_entry("KnowledgeState", KnowledgeState, notes="PRD v9 §0.3 / §0.5"),
        _enum_entry(
            "DeterminabilityState",
            DeterminabilityStateV7,
            notes="v7 contract retained; INDETERMINATE remains expressible via alias",
        ),
        _enum_entry("ScenarioCompleteness", ScenarioCompleteness),
        _enum_entry(
            "AmbiguousState",
            AmbiguousState,
            notes="Insufficiente/indeterminata/unknown must remain first-class",
        ),
        RegistryEntry(
            name="CountKind",
            kind=RegistryKind.COUNT_KIND,
            values=tuple(item.value for item in CountKind),
            notes="v7 CountKind is the implemented count registry; aliases are read-only",
        ),
        RegistryEntry(
            name="error_code",
            kind=RegistryKind.ERROR_CODE,
            values=(
                "UNKNOWN_REGISTRY_TOKEN",
                "LEGACY_ALIAS_EMITTED",
                "FORBIDDEN_V9_LABEL_FROM_ADAPTER",
                "SILENT_FACTORROLE_INFERENCE",
                "REGISTRY_NOT_FROZEN",
                "INSUFFICIENT_OR_INDETERMINATE_REQUIRED",
            ),
        ),
        RegistryEntry(
            name="field_name",
            kind=RegistryKind.FIELD_NAME,
            values=tuple(sorted(EXPERIMENT_GRAPH_FIELD_AUTHORITY)),
        ),
        RegistryEntry(
            name="status",
            kind=RegistryKind.STATUS,
            values=(
                REGISTRY_STATUS,
                "APPROVED_BY_HUMAN_SCIENTIFIC_OWNER",
                "HISTORICAL",
            ),
        ),
    )
    return RegistryDecisionPack(
        single_canonical_registry_topics=(
            "enum",
            "field name",
            "claim type",
            "error code",
            "count kind",
            "status",
        ),
        entries=entries,
        ambiguous_indeterminate_states=tuple(item.value for item in AmbiguousState),
        rulebook_status=(
            "PENDING_HUMAN_SCIENTIFIC_APPROVAL: Rulebook remains the executable "
            "conformance layer under the registry; this pack does not freeze it"
        ),
        annotation_guideline_status=(
            "PENDING_HUMAN_SCIENTIFIC_APPROVAL: CP-DATA annotation guideline is "
            "required before GOLD; this pack does not approve it"
        ),
        experiment_graph_field_authority={
            name: authority.value for name, authority in EXPERIMENT_GRAPH_FIELD_AUTHORITY.items()
        },
        v7_to_v9_migration=V7_TO_V9_FIELD_MIGRATION,
    )


def registry_draft_path() -> Path:
    return Path(__file__).with_name("registry_v9_draft.json")


@lru_cache(maxsize=1)
def load_registry_draft() -> dict[str, Any]:
    path = registry_draft_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("registry v9 draft must be a JSON object")
    if payload.get("normative_registry_v9_frozen") is True:
        raise ValueError("registry draft cannot self-freeze")
    return payload


def assert_registry_not_self_approved(payload: Mapping[str, Any] | None = None) -> None:
    document = payload if payload is not None else load_registry_draft()
    if document.get("normative_registry_v9_frozen") is True:
        raise ValueError("registry draft cannot set normative_registry_v9_frozen=true")
    if document.get("human_approval") not in (None, False):
        raise ValueError("registry draft cannot record human approval")
    if document.get("gold_frozen") is True:
        raise ValueError("registry draft cannot freeze GOLD")
    if document.get("status") == "APPROVED_BY_HUMAN_SCIENTIFIC_OWNER":
        raise ValueError("registry draft cannot self-approve")


def _forbidden_token(text: str) -> str | None:
    if text in FORBIDDEN_CANONICAL_V9_LABELS:
        return text
    if "-" in text:
        tail = text.split("-", 1)[1]
        if tail in FORBIDDEN_CANONICAL_V9_LABELS:
            return tail
    return None


def collect_forbidden_v9_labels(value: object) -> tuple[str, ...]:
    """Return canonical v9 names used as invented labels in a public payload."""

    found: set[str] = set()

    def walk(item: object) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                token = _forbidden_token(str(key))
                if token:
                    found.add(token)
                walk(nested)
        elif isinstance(item, (list, tuple, set)):
            for nested in item:
                walk(nested)
        elif isinstance(item, str):
            token = _forbidden_token(item)
            if token:
                found.add(token)

    walk(value)
    return tuple(sorted(found))


def reject_public_adapter_v9_labels(payload: object, *, adapter: str) -> None:
    invented = collect_forbidden_v9_labels(payload)
    if invented:
        raise ValueError(
            f"{adapter} cannot emit canonical N-Truth v9 labels: {', '.join(invented)}"
        )


class V7toV9MigrationReport(FrozenModel):
    implemented_root_contract: Literal["PRD_V7"] = "PRD_V7"
    normative_target: Literal["PRD_V9"] = "PRD_V9"
    mapped_statuses: dict[str, str]
    preserved_ambiguous_states: tuple[str, ...]
    unmigrated_decisive_fields: tuple[str, ...]
    invented_v9_labels: tuple[str, ...]
    silent_factor_role_inference: Literal[False] = False
    registry_frozen: Literal[False] = False
    accepted: bool


def migrate_v7_record(record: Mapping[str, Any]) -> V7toV9MigrationReport:
    """Checkable v7 → v9 draft migration. Never invents decisive v9 labels."""

    mapped: dict[str, str] = {}
    preserved: list[str] = []
    determinability = record.get("determinability")
    if isinstance(determinability, str):
        try:
            v3 = Determinability(determinability)
            mapped[determinability] = migrate_v3_state(v3).value
        except ValueError:
            try:
                v7 = DeterminabilityStateV7(determinability)
                mapped[determinability] = v7.value
            except ValueError:
                mapped[determinability] = "UNKNOWN_REGISTRY_TOKEN"
    if isinstance(determinability, Mapping):
        status = determinability.get("status")
        if isinstance(status, str):
            try:
                v3 = Determinability(status)
                mapped[status] = migrate_v3_state(v3).value
            except ValueError:
                mapped[status] = status
            if status in {item.value for item in AmbiguousState} or status == "INDETERMINATE":
                preserved.append(status)

    for state in AmbiguousState:
        token = state.value
        blob = json.dumps(record, sort_keys=True, default=str)
        if token in blob:
            preserved.append(token)

    invented = collect_forbidden_v9_labels(record)
    unmigrated = tuple(
        name
        for name, authority in EXPERIMENT_GRAPH_FIELD_AUTHORITY.items()
        if authority is FieldAuthority.DECISIVE and name not in record
    )
    return V7toV9MigrationReport(
        mapped_statuses=mapped,
        preserved_ambiguous_states=tuple(dict.fromkeys(preserved)),
        unmigrated_decisive_fields=unmigrated,
        invented_v9_labels=invented,
        accepted=not invented and bool(unmigrated),
    )


def write_registry_draft(path: Path | None = None) -> dict[str, Any]:
    pack = build_registry_decision_pack()
    payload = pack.model_dump(mode="json")
    payload["fingerprint"] = pack.fingerprint()
    assert_registry_not_self_approved(payload)
    target = path or registry_draft_path()
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
