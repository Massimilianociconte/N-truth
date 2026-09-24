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
from ntruth.prospective import ProspectiveD0CompileRequest, compile_prospective_d0
from ntruth.schemas.core import Confidence, Determinability, Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    Correction,
    CorrectionReason,
    CountKind,
    CountQuantifier,
    CountRecord,
    CountScope,
    ExperimentBlock,
    GraphStatus,
    Hierarchy,
    LifecycleStatus,
    NKind,
    Versions,
)
from ntruth.schemas.graph import GraphNode, GraphRelation, GraphViolation, NodeType, RelationType
from ntruth.schemas.rules import Ruleset

SCIENTIFIC_FIXTURES = Path(__file__).parents[1] / "scientific_fixtures"


def _provenance() -> Provenance:
    return Provenance(
        origin=ProvenanceKind.DERIVED,
        derivation="synthetic correction-engine fixture",
    )


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
    assert updated.audit_trail[0].actor_role == "domain_reviewer"
    assert updated.audit_trail[0].recorded_at.utcoffset() is not None
    assert updated.current_block.corrections[0].recorded_at == updated.audit_trail[0].recorded_at
    assert updated.integrity_errors() == ()


def test_invalid_graph_baseline_can_be_repaired_without_weakening_ledger_integrity() -> None:
    block = _block()
    relation = block.hierarchy.relations[0]
    unmarked_invalid = block.model_copy(
        update={
            "hierarchy": block.hierarchy.model_copy(
                update={"relations": (relation.model_copy(update={"target": "missing-parent"}),)}
            ),
        }
    )
    with pytest.raises(CorrectionValidationError, match="dangling_relation_endpoint"):
        CorrectionLedger.start(unmarked_invalid)

    invalid = unmarked_invalid.model_copy(
        update={
            "graph_status": GraphStatus.INVALID,
            "determinability": Determinability.INVALID_GRAPH,
        }
    )

    ledger = CorrectionLedger.start(invalid)
    assert ledger.current_block.determinability is Determinability.INVALID_GRAPH
    with pytest.raises(CorrectionValidationError, match="dangling_relation_endpoint"):
        ledger.apply(
            Correction(
                id="does-not-repair-invalid-graph",
                sequence=0,
                reason=CorrectionReason.TYPO,
                rationale="Una modifica non strutturale non puo aggirare il validator.",
                patch=({"op": "replace", "path": "/title", "value": "Solo titolo"},),
            )
        )
    assert ledger.records == () and ledger.audit_trail == ()

    repaired = ledger.apply(
        Correction(
            id="repair-invalid-graph",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="Ripristino dell'endpoint e stato del grafo con audit umano.",
            reviewer_role="domain_reviewer",
            patch=(
                {
                    "op": "replace",
                    "path": "/hierarchy/relations/0/target",
                    "value": "animal-1",
                },
                {
                    "op": "replace",
                    "path": "/graph_status",
                    "value": GraphStatus.HUMAN_CONFIRMED.value,
                },
            ),
        )
    )

    assert repaired.current_block.hierarchy.relations[0].target == "animal-1"
    assert repaired.current_block.graph_status is GraphStatus.HUMAN_CONFIRMED
    assert repaired.integrity_errors() == ()
    undone = repaired.undo(actor_role="adjudicator")
    assert undone.current_block.hierarchy.relations[0].target == "missing-parent"
    assert undone.integrity_errors() == ()
    redone = undone.redo(actor_role="wet_lab_reviewer")
    assert redone.current_block.hierarchy.relations[0].target == "animal-1"
    assert [event.action.value for event in redone.audit_trail] == ["apply", "undo", "redo"]
    assert [event.actor_role for event in redone.audit_trail] == [
        "domain_reviewer",
        "adjudicator",
        "wet_lab_reviewer",
    ]
    assert redone.integrity_errors() == ()


def test_recalculation_cannot_clear_unmaterialized_builder_violation(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    """Cambiare graph_status non ripara un fatto sorgente scartato dal builder."""

    analysis = _case_analysis(analyze, "uc01_donor_cells")
    source_violation = GraphViolation(
        code="dangling_instance_assignment",
        message="assegnazione tabulare senza istanza corrispondente",
        blocking=True,
    )
    invalid_analysis = replace(
        analysis,
        block=analysis.block.model_copy(
            update={
                "graph_status": GraphStatus.INVALID,
                "determinability": Determinability.INVALID_GRAPH,
            }
        ),
        build=replace(analysis.build, violations=(source_violation,)),
    )
    ledger = CorrectionLedger.start(invalid_analysis.block).apply(
        Correction(
            id="status-only-cannot-repair-source",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="Tentativo di cambiare soltanto lo stato dichiarato.",
            reviewer_role="domain_reviewer",
            patch=(
                {
                    "op": "replace",
                    "path": "/graph_status",
                    "value": GraphStatus.HUMAN_CONFIRMED.value,
                },
            ),
        )
    )

    recalculated = recalculate_corrected_block(invalid_analysis, ledger, ruleset)

    assert recalculated.analysis.block.graph_status is GraphStatus.INVALID
    assert recalculated.analysis.block.determinability is Determinability.INVALID_GRAPH
    assert recalculated.analysis.verification.status.value == "failed"
    assert {item.code for item in recalculated.analysis.verification.violations} == {
        "dangling_instance_assignment"
    }
    assert recalculated.analysis.evaluations == ()


def test_audit_checksum_tampering_is_detected() -> None:
    applied = CorrectionLedger.start(_block()).apply(
        _label_correction("correction-0", 0, "animale originale", "corretto")
    )
    tampered_event = replace(applied.audit_trail[0], after_checksum="0" * 64)
    tampered = replace(applied, audit_trail=(tampered_event,))

    assert any("checksum incoerente" in error for error in tampered.integrity_errors())

    tampered_role = replace(applied.audit_trail[0], actor_role="different_reviewer")
    role_tampered_ledger = replace(applied, audit_trail=(tampered_role,))
    assert any(
        "audit event id incoerente" in error for error in role_tampered_ledger.integrity_errors()
    )
    assert any(
        "actor role divergente dal record" in error
        for error in role_tampered_ledger.integrity_errors()
    )


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
        "/corrections/-",
        "/alerts/-",
        "/determinability",
        "/plausible_graph_set",
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


def test_evidence_overlay_is_correctable_but_must_match_immutable_document(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc01_donor_cells")
    evidence_index = next(
        index
        for index, evidence in enumerate(analysis.block.evidence)
        if evidence.start is not None and evidence.end is not None
    )

    valid_ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="correct-evidence-type",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="L'annotatore riclassifica il tipo mantenendo il locator sorgente.",
            patch=(
                {
                    "op": "replace",
                    "path": f"/evidence/{evidence_index}/evidence_type",
                    "value": "USER_CONFIRMATION",
                },
            ),
        )
    )
    valid = recalculate_corrected_block(analysis, valid_ledger, ruleset)
    assert "evidence" in valid_ledger.active_changed_roots
    assert valid.analysis.verification.status.value != "failed"

    invalid_ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="mismatched-evidence-text",
            sequence=0,
            reason=CorrectionReason.PARSER_ERROR,
            rationale="Caso negativo: il testo non coincide con il documento immutabile.",
            patch=(
                {
                    "op": "replace",
                    "path": f"/evidence/{evidence_index}/text",
                    "value": "testo inventato che non appartiene alla fonte",
                },
            ),
        )
    )
    invalid = recalculate_corrected_block(analysis, invalid_ledger, ruleset)
    assert invalid.analysis.block.graph_status is GraphStatus.INVALID
    assert "evidence_text_mismatch" in {
        item.code for item in invalid.analysis.verification.violations
    }

    locator_stripped_ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="evidence-without-verifiable-locator",
            sequence=0,
            reason=CorrectionReason.PARSER_ERROR,
            rationale="Caso negativo: il client elimina ogni locator e inventa il testo.",
            patch=(
                {
                    "op": "replace",
                    "path": f"/evidence/{evidence_index}/text",
                    "value": "FABRICATED HUMAN TEXT",
                },
                *(
                    {
                        "op": "replace",
                        "path": f"/evidence/{evidence_index}/{field_name}",
                        "value": None,
                    }
                    for field_name in (
                        "start",
                        "end",
                        "section_id",
                        "section_title",
                        "cell",
                        "page",
                    )
                ),
            ),
        )
    )
    locator_stripped = recalculate_corrected_block(
        analysis,
        locator_stripped_ledger,
        ruleset,
    )
    assert locator_stripped.analysis.block.graph_status is GraphStatus.INVALID
    assert "evidence_missing_verifiable_locator" in {
        item.code for item in locator_stripped.analysis.verification.violations
    }


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


def test_non_evidence_correction_keeps_csv_cell_provenance_valid(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc11_well_treatment")
    assert any(item.cell is not None for item in analysis.block.evidence)
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="csv-title-correction",
            sequence=0,
            reason=CorrectionReason.TYPO,
            rationale="Correzione del titolo senza alterare provenance o celle sorgente.",
            patch=(
                {
                    "op": "replace",
                    "path": "/title",
                    "value": "Well-level treatment, reviewed title",
                },
            ),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.verification.status.value != "failed", [
        (item.code, item.message) for item in recalculated.analysis.verification.violations
    ]
    assert not {
        item.code
        for item in recalculated.analysis.verification.violations
        if item.code.startswith("evidence_")
    }


def test_resolved_builder_question_is_not_reintroduced_after_recalculation(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc02_preparations")
    factor_index = 0
    factor = analysis.block.factors[factor_index]
    missing_field = f"factor[{factor.name}].independently_assigned"
    assert any(question.missing_field == missing_field for question in analysis.block.questions)
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="confirm-operational-independence",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="Il reviewer conferma preparazioni separate e allocazione indipendente.",
            reviewer_role="wet_lab_reviewer",
            patch=(
                {
                    "op": "replace",
                    "path": f"/factors/{factor_index}/independently_assigned",
                    "value": "TRUE",
                },
                {
                    "op": "replace",
                    "path": f"/factors/{factor_index}/independence_mechanism",
                    "value": "preparazioni avviate separatamente prima dell'allocazione",
                },
                {
                    "op": "replace",
                    "path": f"/factors/{factor_index}/provenance",
                    "value": {
                        "origin": "user",
                        "actor_role": "wet_lab_reviewer",
                    },
                },
            ),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.verification.status.value != "failed", [
        (item.code, item.message) for item in recalculated.analysis.verification.violations
    ]
    assert all(
        question.missing_field != missing_field
        for question in recalculated.analysis.block.questions
    )


def test_resolved_ambiguous_n_entities_close_the_unscoped_builder_question(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc08_undefined_experiments")
    missing_field = "n_statement.entity_type"
    assert any(question.missing_field == missing_field for question in analysis.block.questions)
    patch: list[dict[str, object]] = []
    for index, _statement in enumerate(analysis.block.n_statements):
        patch.extend(
            (
                {
                    "op": "replace",
                    "path": f"/n_statements/{index}/entity_type",
                    "value": "PrimaryCulture",
                },
                {
                    "op": "replace",
                    "path": f"/n_statements/{index}/node_type",
                    "value": "PrimaryCulture",
                },
                {
                    "op": "replace",
                    "path": f"/n_statements/{index}/scope/unit_type",
                    "value": "PrimaryCulture",
                },
            )
        )
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="resolve-ambiguous-n-entities",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="Ogni menzione viene collegata alla coltura primaria pertinente.",
            reviewer_role="wet_lab_reviewer",
            patch=tuple(patch),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.verification.status.value != "failed"
    assert all(
        question.missing_field != missing_field
        for question in recalculated.analysis.block.questions
    )


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


def test_estimand_correction_requires_rule_rerun_in_candidate_export() -> None:
    request = ProspectiveD0CompileRequest.model_validate(
        {
            "draft": {
                "experimentBlockId": "EB-D0-CORRECTION-001",
                "question": "Does treatment change viability?",
                "inferenceTarget": "declared wells",
                "factorName": "Treatment",
                "factorKind": "treatment",
                "levelA": "vehicle",
                "levelB": "drug",
                "endpointName": "viability",
                "endpointId": "EP-V",
                "measuredOn": "Well",
                "allocationLevel": "Well",
                "applicationLevel": "Well",
                "independentlyAssigned": "TRUE",
                "independenceMechanism": "Independent allocation recorded per well.",
                "targetBiologicalUnit": "Well",
                "estimand": {
                    "effectMeasure": "difference in means",
                    "targetPopulationOrUnit": "declared wells",
                    "generalizationLevel": "declared conditions",
                },
            },
            "rows": [
                {
                    "sampleId": "S1",
                    "plateId": "P1",
                    "wellId": "A01",
                    "factorLevel": "vehicle",
                    "endpointId": "EP-V",
                    "lifecycleStatus": "planned",
                },
                {
                    "sampleId": "S2",
                    "plateId": "P1",
                    "wellId": "A02",
                    "factorLevel": "drug",
                    "endpointId": "EP-V",
                    "lifecycleStatus": "planned",
                },
            ],
        }
    )
    block = compile_prospective_d0(request).block
    original = block.estimands[0].effect_measure
    ledger = CorrectionLedger.start(block).apply(
        Correction(
            id="correct-estimand-effect-measure",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="L'estimand confermato usa una misura di effetto diversa.",
            reviewer_role="biostatistician",
            patch=(
                {
                    "op": "test",
                    "path": "/estimands/0/effect_measure",
                    "value": original,
                },
                {
                    "op": "replace",
                    "path": "/estimands/0/effect_measure",
                    "value": "risk ratio",
                },
            ),
        )
    )

    assert ledger.active_changed_roots == ("estimands",)
    assert ledger.requires_rule_rerun is True
    assert candidate_annotations_payload(ledger)["requires_rule_rerun"] is True


def test_model_removal_is_versioned_and_not_restored_during_recalculation(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc12_mixed_model")
    assert analysis.block.models
    assert analysis.block.models == analysis.build.models
    removed_model_ids = {model.id for model in analysis.block.models}
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
    assert not any(
        node.type is NodeType.STATISTICAL_MODEL or node.id in removed_model_ids
        for node in recalculated.analysis.block.hierarchy.nodes
    )
    assert not any(
        relation.source in removed_model_ids or relation.target in removed_model_ids
        for relation in recalculated.analysis.block.hierarchy.relations
    )
    assert all(
        assessment.data_sufficiency.statistical_model is Confidence.UNKNOWN
        for assessment in recalculated.analysis.block.unit_assessments
    )


def test_model_only_design_unit_is_removed_with_its_model(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
    tmp_path: Path,
) -> None:
    source = tmp_path / "model-only-source"
    source.mkdir()
    (source / "methods.md").write_text(
        "Data were analysed with a mixed model with a random effect for plate.\n",
        encoding="utf-8",
    )
    analysis = analyze(source).block_analyses[0]
    assert analysis.block.models
    assert any(
        node.type is NodeType.PLATE
        and node.attributes.get("materialized_from_design_field") is True
        for node in analysis.block.hierarchy.nodes
    )
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="remove-model-only-plate",
            sequence=0,
            reason=CorrectionReason.PARSER_ERROR,
            rationale="La frase statistica non appartiene al blocco corrente.",
            patch=tuple(
                {"op": "remove", "path": f"/models/{index}"}
                for index in reversed(range(len(analysis.block.models)))
            ),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.block.models == ()
    assert not any(
        node.type in {NodeType.STATISTICAL_MODEL, NodeType.PLATE}
        for node in recalculated.analysis.block.hierarchy.nodes
    )


def test_v6_canonical_count_survives_unrelated_recalculation(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc01_donor_cells")
    count = CountRecord(
        count_id="canonical-observed-count",
        kind=CountKind.OBSERVED_N,
        value=3,
        quantifier=CountQuantifier.EXACT,
        scope=CountScope(
            unit_type=NodeType.PRIMARY_CULTURE,
            factor_id=None,
            contrast_id=None,
            group_or_level=None,
            endpoint_id=None,
            timepoint=None,
            lifecycle=LifecycleStatus.OBSERVED,
            population="three source preparations",
            condition=None,
            unknown_reasons={
                "factor_id": "not reported",
                "contrast_id": "not reported",
                "group_or_level": "not reported",
                "endpoint_id": "not reported",
                "timepoint": "not reported",
            },
        ),
        provenance=Provenance(origin=ProvenanceKind.USER, actor_role="reviewer"),
    )
    canonical_analysis = replace(
        analysis,
        block=analysis.block.model_copy(update={"n_statements": (), "count_records": (count,)}),
        build=replace(analysis.build, n_statements=()),
    )
    ledger = CorrectionLedger.start(canonical_analysis.block).apply(
        Correction(
            id="title-only-keeps-canonical-count",
            sequence=0,
            reason=CorrectionReason.TYPO,
            rationale="Correzione editoriale senza modifica dei conteggi.",
            patch=({"op": "replace", "path": "/title", "value": "Titolo corretto"},),
        )
    )

    recalculated = recalculate_corrected_block(canonical_analysis, ledger, ruleset)

    assert recalculated.analysis.block.count_records == (count,)
    assert len(recalculated.analysis.build.n_statements) == 1
    assert recalculated.analysis.build.n_statements[0].value == 3


def test_v6_canonical_count_patch_reaches_legacy_resolver_adapter(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc01_donor_cells")
    assert analysis.block.count_records
    count_index = next(
        index
        for index, count in enumerate(analysis.block.count_records)
        if count.kind not in {CountKind.INDEPENDENT_N, CountKind.EFFECTIVE_N}
        and count.quantifier in {CountQuantifier.EXACT, CountQuantifier.APPROXIMATE}
    )
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="correct-canonical-count",
            sequence=0,
            reason=CorrectionReason.PARSER_ERROR,
            rationale="Il conteggio osservato e stato corretto dalla fonte.",
            patch=(
                {
                    "op": "replace",
                    "path": f"/count_records/{count_index}/value",
                    "value": 7,
                },
            ),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert "count_records" in ledger.active_changed_roots
    corrected_id = analysis.block.count_records[count_index].count_id
    corrected_count = next(
        item for item in recalculated.analysis.block.count_records if item.count_id == corrected_id
    )
    corrected_statement = next(
        item for item in recalculated.analysis.build.n_statements if item.id == corrected_id
    )
    assert corrected_count.value == 7
    assert corrected_statement.value == 7


def test_correction_hard_preflight_blocks_invalid_operational_independence(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc11_well_treatment")
    factor_index = next(
        index
        for index, factor in enumerate(analysis.block.factors)
        if factor.allocation_level is None
    )
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="invalid-independence-without-allocation",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="Caso negativo: TRUE senza unita di allocazione documentata.",
            patch=(
                {
                    "op": "replace",
                    "path": f"/factors/{factor_index}/independently_assigned",
                    "value": "TRUE",
                },
                {
                    "op": "replace",
                    "path": f"/factors/{factor_index}/independence_mechanism",
                    "value": "separate handling asserted without allocation evidence",
                },
            ),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.block.graph_status is GraphStatus.INVALID
    assert recalculated.analysis.block.determinability is Determinability.INVALID_GRAPH
    assert recalculated.analysis.evaluations == ()
    assert recalculated.analysis.verification.status.value == "failed"
    assert "independence_without_allocation_unit" in {
        item.code for item in recalculated.analysis.verification.violations
    }


def test_correction_invalid_branch_never_serializes_numeric_independent_count(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc01_donor_cells")
    template = next(
        item
        for item in analysis.block.count_records
        if item.value is not None and item.kind is not CountKind.EFFECTIVE_N
    )
    independent = template.model_copy(
        update={
            "count_id": "correction-injected-independent-count",
            "kind": CountKind.INDEPENDENT_N,
            "value": 3,
        }
    )
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="inject-invalid-independent-count",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="Caso negativo per il gate pubblico del conteggio indipendente.",
            patch=(
                {
                    "op": "add",
                    "path": "/count_records/-",
                    "value": independent.model_dump(mode="json"),
                },
            ),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.block.determinability is Determinability.INVALID_GRAPH
    assert not any(
        item.kind is CountKind.INDEPENDENT_N and item.value is not None
        for item in recalculated.analysis.block.count_records
    )
    assert not any(
        item.kind is NKind.INDEPENDENT and item.value is not None
        for item in recalculated.analysis.block.n_statements
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
    assert recalculated.analysis.block.exclusion_records == ()
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


def test_canonical_exclusion_removal_controls_legacy_predicates(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc09_exclusions")
    assert analysis.block.exclusion_records
    patch = tuple(
        {"op": "remove", "path": f"/exclusion_records/{index}"}
        for index in reversed(range(len(analysis.block.exclusion_records)))
    )
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="remove-canonical-exclusions",
            sequence=0,
            reason=CorrectionReason.DOMAIN_JUDGEMENT,
            rationale="Il registro canonico conferma che non vi furono esclusioni.",
            patch=patch,
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert recalculated.analysis.block.exclusion_records == ()
    assert not any(item.kind == "exclusion" for item in recalculated.analysis.block.processes)
    assert not any(item.kind == "exclusion" for item in recalculated.analysis.build.processes)
    assert "ANI-005" not in {alert.rule_id for alert in recalculated.analysis.block.alerts}


def test_canonical_exclusion_update_reaches_recalculated_build(
    analyze: Callable[..., AnalysisResult],
    ruleset: Ruleset,
) -> None:
    analysis = _case_analysis(analyze, "uc09_exclusions")
    record_index = next(
        index
        for index, record in enumerate(analysis.block.exclusion_records)
        if "excluded_count=" in (record.impact or "")
    )
    ledger = CorrectionLedger.start(analysis.block).apply(
        Correction(
            id="update-canonical-exclusion",
            sequence=0,
            reason=CorrectionReason.PARSER_ERROR,
            rationale="Corregge motivo e conteggio del registro canonico verificato.",
            patch=(
                {
                    "op": "replace",
                    "path": f"/exclusion_records/{record_index}/reason",
                    "value": "criterio QC predefinito",
                },
                {
                    "op": "replace",
                    "path": f"/exclusion_records/{record_index}/impact",
                    "value": "excluded_count=9",
                },
            ),
        )
    )

    recalculated = recalculate_corrected_block(analysis, ledger, ruleset)

    assert any(
        process.kind == "exclusion"
        and process.detail == "criterio QC predefinito"
        and process.value == 9
        for process in recalculated.analysis.build.processes
    )
