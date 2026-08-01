"""FR-025/026/030: patch, audit append-only, undo/redo e candidate export."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ntruth.corrections import (
    CorrectionLedger,
    CorrectionSequenceError,
    CorrectionValidationError,
    DuplicateCorrection,
    JsonPatchError,
    NothingToRedo,
    NothingToUndo,
    ProtectedCorrectionPath,
    apply_json_patch,
    candidate_annotations_payload,
    recalculate_corrected_block,
    write_candidate_annotations,
)
from ntruth.pipeline import AnalysisResult, BlockAnalysis
from ntruth.schemas.core import Confidence, Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    Correction,
    CorrectionReason,
    ExperimentBlock,
    Hierarchy,
    Versions,
)
from ntruth.schemas.graph import GraphNode, GraphRelation, NodeType, RelationType
from ntruth.schemas.rules import Ruleset

SCIENTIFIC_FIXTURES = Path(__file__).parents[1] / "scientific_fixtures"


def _provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.EXPLICIT)


def _block() -> ExperimentBlock:
    animal = GraphNode(
        id="animal-1",
        type=NodeType.ANIMAL,
        label="animale originale",
        provenance=_provenance(),
    )
    cell = GraphNode(
        id="cell-1",
        type=NodeType.CELL,
        label="cellula",
        provenance=_provenance(),
    )
    nesting = GraphRelation(
        id="nested-1",
        type=RelationType.NESTED_IN,
        source=cell.id,
        target=animal.id,
        provenance=_provenance(),
    )
    return ExperimentBlock(
        id="block-1",
        document_id="document-1",
        hierarchy=Hierarchy(nodes=(animal, cell), relations=(nesting,)),
        versions=Versions(
            schema_version="0.1.0",
            parser_version="0.1.0",
            graph_version="0.1.0",
            ruleset_id="ntruth-core",
            ruleset_version="0.1.0",
        ),
    )


def _case_analysis(
    analyze: Callable[..., AnalysisResult],
    case_name: str,
) -> BlockAnalysis:
    return analyze(SCIENTIFIC_FIXTURES / case_name).block_analyses[0]


def _remove_all_kind(
    root: str,
    values: tuple[Any, ...],
    kind: str,
) -> tuple[dict[str, object], ...]:
    indices = [index for index, value in enumerate(values) if value.kind == kind]
    return tuple({"op": "remove", "path": f"/{root}/{index}"} for index in reversed(indices))


def _label_correction(
    correction_id: str,
    sequence: int,
    old: str,
    new: str,
) -> Correction:
    return Correction(
        id=correction_id,
        sequence=sequence,
        reason=CorrectionReason.DOMAIN_JUDGEMENT,
        rationale="Correzione locale del label; nessuna regola scientifica modificata.",
        reviewer_role="domain_reviewer",
        patch=(
            {"op": "test", "path": "/hierarchy/nodes/0/label", "value": old},
            {"op": "replace", "path": "/hierarchy/nodes/0/label", "value": new},
        ),
    )


def test_json_patch_supports_all_rfc6902_operations_atomically() -> None:
    original = {"items": [1, 2], "meta": {"value": 1}}
    patched = apply_json_patch(
        original,
        (
            {"op": "add", "path": "/items/-", "value": 3},
            {"op": "replace", "path": "/meta/value", "value": 2},
            {"op": "copy", "from": "/meta/value", "path": "/meta/copied"},
            {"op": "move", "from": "/meta/copied", "path": "/moved"},
            {"op": "test", "path": "/moved", "value": 2},
            {"op": "remove", "path": "/items/0"},
        ),
    )
    assert patched == {"items": [2, 3], "meta": {"value": 2}, "moved": 2}
    assert original == {"items": [1, 2], "meta": {"value": 1}}


def test_json_patch_failure_never_mutates_the_original() -> None:
    original = {"value": 1}
    with pytest.raises(JsonPatchError):
        apply_json_patch(
            original,
            (
                {"op": "replace", "path": "/value", "value": 2},
                {"op": "test", "path": "/value", "value": 999},
            ),
        )
    assert original == {"value": 1}


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "add", "value": 1},
        {"op": "move", "path": "/x"},
        {"op": "replace", "path": "not-a-pointer", "value": 1},
        {"op": "unknown", "path": "/x"},
    ],
)
def test_malformed_json_patch_is_rejected(operation: dict[str, Any]) -> None:
    with pytest.raises(JsonPatchError):
        apply_json_patch({}, (operation,))


def test_apply_is_immutable_and_records_an_append_only_audit() -> None:
    block = _block()
    ledger = CorrectionLedger.start(block)
    correction = _label_correction("correction-0", 0, "animale originale", "animale confermato")

    updated = ledger.apply(correction)

    assert block.hierarchy.nodes[0].label == "animale originale"
    assert ledger.records == () and ledger.audit_trail == ()
    assert updated.current_block.hierarchy.nodes[0].label == "animale confermato"
    assert [item.id for item in updated.current_block.corrections] == ["correction-0"]
    assert updated.active_correction_ids == ("correction-0",)
    assert updated.active_changed_roots == ("hierarchy",)
    assert updated.requires_rule_rerun is True
    assert updated.audit_trail[0].action.value == "apply"
    assert updated.integrity_errors() == ()


def test_audit_checksum_tampering_is_detected() -> None:
    applied = CorrectionLedger.start(_block()).apply(
        _label_correction("correction-0", 0, "animale originale", "corretto")
    )
    tampered_event = replace(applied.audit_trail[0], after_checksum="0" * 64)
    tampered = replace(applied, audit_trail=(tampered_event,))

    assert any("checksum incoerente" in error for error in tampered.integrity_errors())


def test_undo_redo_preserve_records_and_audit_history() -> None:
    applied = CorrectionLedger.start(_block()).apply(
        _label_correction("correction-0", 0, "animale originale", "corretto")
    )
    undone = applied.undo()
    redone = undone.redo()

    assert undone.current_block.hierarchy.nodes[0].label == "animale originale"
    assert len(undone.records) == 1
    assert [item.id for item in undone.current_block.corrections] == ["correction-0"]
    assert undone.active_correction_ids == ()
    assert undone.requires_rule_rerun is False
    assert undone.redo_correction_ids == ("correction-0",)
    assert [event.action.value for event in undone.audit_trail] == ["apply", "undo"]

    assert redone.current_block.hierarchy.nodes[0].label == "corretto"
    assert redone.active_correction_ids == ("correction-0",)
    assert [event.action.value for event in redone.audit_trail] == [
        "apply",
        "undo",
        "redo",
    ]
    assert redone.integrity_errors() == ()


def test_new_correction_after_undo_creates_a_branch_without_deleting_history() -> None:
    first = CorrectionLedger.start(_block()).apply(
        _label_correction("correction-0", 0, "animale originale", "prima")
    )
    second = first.apply(_label_correction("correction-1", 1, "prima", "seconda"))
    branched = second.undo().apply(
        _label_correction("correction-2", 2, "prima", "ramo alternativo")
    )

    assert branched.current_block.hierarchy.nodes[0].label == "ramo alternativo"
    assert branched.active_correction_ids == ("correction-0", "correction-2")
    assert [record.correction.id for record in branched.records] == [
        "correction-0",
        "correction-1",
        "correction-2",
    ]
    assert branched.redo_correction_ids == ()
    with pytest.raises(NothingToRedo):
        branched.redo()


def test_sequence_duplicate_and_empty_history_navigation_are_rejected() -> None:
    ledger = CorrectionLedger.start(_block())
    with pytest.raises(NothingToUndo):
        ledger.undo()
    with pytest.raises(NothingToRedo):
        ledger.redo()
    with pytest.raises(CorrectionSequenceError):
        ledger.apply(_label_correction("correction-wrong-sequence", 3, "animale originale", "x"))

    applied = ledger.apply(_label_correction("correction-0", 0, "animale originale", "x"))
    with pytest.raises(DuplicateCorrection):
        applied.apply(_label_correction("correction-0", 1, "x", "y"))


def test_protected_source_and_audit_paths_cannot_be_patched() -> None:
    ledger = CorrectionLedger.start(_block())
    for path in (
        "/versions/schema_version",
        "/evidence",
        "/corrections/-",
        "/alerts/-",
        "",
    ):
        correction = Correction(
            id=f"protected-{len(path)}",
            sequence=0,
            reason=CorrectionReason.TYPO,
            patch=({"op": "add", "path": path, "value": "forbidden"},),
        )
        with pytest.raises(ProtectedCorrectionPath):
            ledger.apply(correction)


def test_patch_that_leaves_a_dangling_relation_is_rejected() -> None:
    ledger = CorrectionLedger.start(_block())
    correction = Correction(
        id="remove-parent",
        sequence=0,
        reason=CorrectionReason.DOMAIN_JUDGEMENT,
        patch=({"op": "remove", "path": "/hierarchy/nodes/0"},),
    )
    with pytest.raises(CorrectionValidationError, match="dangling_relation_endpoint"):
        ledger.apply(correction)


def test_empty_patch_can_record_a_confirmation_without_changing_scientific_state() -> None:
    ledger = CorrectionLedger.start(_block())
    confirmation = Correction(
        id="confirmation-0",
        sequence=0,
        reason=CorrectionReason.DOMAIN_JUDGEMENT,
        rationale="Nodo confermato dal reviewer locale.",
        reviewer_role="domain_reviewer",
        patch=(),
    )
    confirmed = ledger.apply(confirmation)
    assert confirmed.base_checksum == confirmed.current_checksum
    assert [item.id for item in confirmed.current_block.corrections] == ["confirmation-0"]


def test_candidate_export_is_separate_from_gold_and_keeps_inactive_records(
    tmp_path: Path,
) -> None:
    applied = CorrectionLedger.start(_block()).apply(
        _label_correction("correction-0", 0, "animale originale", "corretto")
    )
    undone = applied.undo()
    payload = candidate_annotations_payload(undone)

    assert payload["artifact_type"] == "ntruth_candidate_annotations"
    assert payload["gold_status"] == "not_gold"
    assert payload["training_eligible"] is False
    assert payload["requires_separate_curation"] is True
    assert payload["requires_rule_rerun"] is False
    assert payload["candidate_annotations"][0]["active"] is False
    assert payload["candidate_annotations"][0]["training_eligible"] is False
    assert payload["audit_trail"][-1]["action"] == "undo"

    path = write_candidate_annotations(undone, tmp_path / "candidate.json")
    assert json.loads(path.read_text(encoding="utf-8")) == payload


def test_model_removal_is_versioned_and_not_restored_during_recalculation(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc12_mixed_model")
    assert analysis.block.models
    assert analysis.block.models == analysis.build.models
    assert all(
        model.id and set(model.evidence_ids).issubset(model.provenance.evidence_ids)
        for model in analysis.block.models
    )
    correction = Correction(
        id="remove-models",
        sequence=0,
        reason=CorrectionReason.MODEL_ERROR,
        rationale="Il modello dichiarato era stato attribuito al blocco sbagliato.",
        patch=tuple(
            {"op": "remove", "path": f"/models/{index}"}
            for index in reversed(range(len(analysis.block.models)))
        ),
    )

    ledger = CorrectionLedger.start(analysis.block).apply(correction)
    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert ledger.active_changed_roots == ("models",)
    assert ledger.requires_rule_rerun is True
    assert recalculated.analysis.block.models == ()
    assert recalculated.analysis.build.models == ()
    assert all(
        assessment.data_sufficiency.statistical_model is Confidence.UNKNOWN
        for assessment in recalculated.analysis.block.unit_assessments
    )


def test_pooling_removal_changes_predicates_and_unit_resolution(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc07_pooling")
    assert analysis.block.processes == analysis.build.processes
    assert all(
        process.id and set(process.evidence_ids).issubset(process.provenance.evidence_ids)
        for process in analysis.block.processes
    )
    patch = _remove_all_kind("processes", analysis.block.processes, "pooling")
    assert patch
    correction = Correction(
        id="remove-pooling",
        sequence=0,
        reason=CorrectionReason.PARSER_ERROR,
        rationale="La frase descriveva una miscela tecnica, non pooling del disegno.",
        patch=patch,
    )

    ledger = CorrectionLedger.start(analysis.block).apply(correction)
    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert ledger.requires_rule_rerun is True
    assert not any(item.kind == "pooling" for item in recalculated.analysis.block.processes)
    assert not any(item.kind == "pooling" for item in recalculated.analysis.build.processes)
    assert all(
        assessment.experimental_unit is not NodeType.POOL
        for assessment in recalculated.analysis.block.unit_assessments
    )
    assert "GEN-008" not in {alert.rule_id for alert in recalculated.analysis.block.alerts}


def test_exclusion_removal_changes_process_predicate_without_restoring_source_fact(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc09_exclusions")
    patch = _remove_all_kind("processes", analysis.block.processes, "exclusion")
    assert patch
    correction = Correction(
        id="remove-exclusions",
        sequence=0,
        reason=CorrectionReason.DOMAIN_JUDGEMENT,
        rationale="Le righe erano controlli tecnici e non esclusioni di animali.",
        patch=patch,
    )

    ledger = CorrectionLedger.start(analysis.block).apply(correction)
    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert not any(item.kind == "exclusion" for item in recalculated.analysis.block.processes)
    assert not any(item.kind == "exclusion" for item in recalculated.analysis.build.processes)
    assert "ANI-005" not in {alert.rule_id for alert in recalculated.analysis.block.alerts}


def test_exclusion_value_correction_reaches_recalculated_build(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc09_exclusions")
    process_index = next(
        index
        for index, process in enumerate(analysis.block.processes)
        if process.kind == "exclusion" and process.value is not None
    )
    original_value = analysis.block.processes[process_index].value
    assert original_value is not None
    corrected_value = original_value + 2
    correction = Correction(
        id="correct-exclusion-count",
        sequence=0,
        reason=CorrectionReason.PARSER_ERROR,
        rationale="Il conteggio esplicito delle esclusioni e stato corretto.",
        patch=(
            {
                "op": "replace",
                "path": f"/processes/{process_index}/value",
                "value": corrected_value,
            },
        ),
    )

    ledger = CorrectionLedger.start(analysis.block).apply(correction)
    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.block.processes[process_index].value == corrected_value
    assert recalculated.analysis.build.processes[process_index].value == corrected_value
