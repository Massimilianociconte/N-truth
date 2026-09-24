"""PRD v8 examples, schema snapshot, architecture map, docs and CI truth gates."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from ntruth.schemas.kernel import kernel_json_schemas

ROOT = Path(__file__).resolve().parents[2]


def test_machine_readable_current_to_target_map_is_complete_and_path_valid() -> None:
    from ntruth.governance.repository_truth import validate_current_target_map

    map_path = ROOT / "docs" / "architecture" / "prd-v8-current-to-target.yaml"
    result = validate_current_target_map(map_path, repository_root=ROOT)

    assert result.valid, result.diagnostics
    assert result.base_sha == "fe089eff42c16e3fa55606be340c85df57c5442b"
    assert result.target_contract == "N-Truth PRD v8.0"
    required = {
        "core-semantic-kernel",
        "derivation-theory",
        "rulebook-conformance",
        "query-scoped-claims",
        "canonical-count-registry",
        "event-causal-context",
        "v7-to-v8-migrations",
        "ingest-safety",
        "corrections-rederivation",
        "parser-candidate-boundary",
        "experiment-block-boundary",
        "planned-executed-reporting",
        "evaluation-residual-cluster",
        "reality-gate-v8",
        "guided-quick-design-v8",
        "desktop-v8",
        "prd-examples-and-schema",
        "repository-contract-truth",
    }
    assert required <= set(result.component_ids)
    raw_map = json.loads(map_path.read_text(encoding="utf-8"))
    public_apis = {
        component["component_id"]: set(component["public_api"])
        for component in raw_map["components"]
    }
    assert (
        "python:ntruth.migrations.v7_to_v8:migrate_v7_count_kind"
        in public_apis["canonical-count-registry"]
    )
    assert {
        "python:ntruth.schemas.block_boundary:ExperimentBlockBoundaryChangeLedger",
        "python:ntruth.schemas.block_boundary:verify_experiment_block_boundary_change_ledger",
    } <= public_apis["experiment-block-boundary"]
    assert {
        "python:ntruth.evaluation_v8.scoring:snapshot_report_bundle",
        "python:ntruth.evaluation_v8.scoring:evaluate_end_to_end",
        "python:ntruth.evaluation_v8.scoring:summarize_blind_residual_audit",
        "python:ntruth.evaluation_v8.cluster:cluster_bootstrap_precision",
        "python:ntruth.evaluation_v8.cluster:build_cluster_precision_conformance_artifact",
    } <= public_apis["evaluation-residual-cluster"]
    assert {
        "python:ntruth.reality_gate.v8:build_reality_gate_assessment_v8",
        "python:ntruth.reality_gate.v8:evaluate_training_authorization_v8",
        "python:ntruth.governance.repository_policy:scan_tracked_repository_v8",
    } <= public_apis["reality-gate-v8"]
    assert {
        "http:POST:/v8/quick-design/build-submission",
        "python:ntruth.quick_design.guided:GuidedQuickDesignBuildResponse",
        "python:ntruth.quick_design.guided:run_confirmed_guided_quick_design",
    } <= public_apis["guided-quick-design-v8"]


def test_architecture_map_rejects_nonexistent_api_and_unregistered_blocker(
    tmp_path: Path,
) -> None:
    from ntruth.governance.repository_truth import validate_current_target_map

    source = ROOT / "docs" / "architecture" / "prd-v8-current-to-target.yaml"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["components"][0]["public_api"] = ["python:ntruth.schemas.kernel:DOES_NOT_EXIST"]
    payload["components"][0]["blocker_ids"] = ["SRR-V8-999"]
    forged = tmp_path / "map.yaml"
    forged.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_current_target_map(forged, repository_root=ROOT)

    assert not result.valid
    assert any("DOES_NOT_EXIST" in item for item in result.diagnostics)
    assert any("SRR-V8-999" in item for item in result.diagnostics)


def test_verbatim_prd_examples_are_preserved_and_fail_with_registered_diagnostics() -> None:
    from ntruth.conformance.examples import (
        ExampleExpectation,
        evaluate_prd_v8_examples,
        load_installed_prd_v8_example_registry,
    )

    registry = load_installed_prd_v8_example_registry()
    report = evaluate_prd_v8_examples(registry)

    assert report.passed, report.failures
    entries = {entry.example_id: entry for entry in registry.examples}
    assert set(entries) == {
        "PRD-V8-APPENDIX-A-VERBATIM",
        "PRD-V8-APPENDIX-AF-VERBATIM",
        "PRD-V8-APPENDIX-AG-VERBATIM",
        "PRD-V8-CANONICAL-SCENARIO-COVERAGE",
    }
    assert all(
        entries[entry_id].expectation is ExampleExpectation.EXPECTED_NEGATIVE
        for entry_id in (
            "PRD-V8-APPENDIX-A-VERBATIM",
            "PRD-V8-APPENDIX-AF-VERBATIM",
            "PRD-V8-APPENDIX-AG-VERBATIM",
        )
    )
    assert (
        "report_resolution_state: MULTIPLE_PLAUSIBLE_GRAPHS"
        in entries["PRD-V8-APPENDIX-A-VERBATIM"].verbatim_source
    )
    assert {"SRR-V8-002", "SRR-V8-003", "SRR-V8-008"} <= set(
        entries["PRD-V8-APPENDIX-AF-VERBATIM"].expected_diagnostic_ids
    )
    assert "probes_run: []" in entries["PRD-V8-APPENDIX-AG-VERBATIM"].verbatim_source
    canonical = entries["PRD-V8-CANONICAL-SCENARIO-COVERAGE"]
    assert canonical.expectation is ExampleExpectation.POSITIVE
    assert canonical.source_kind == "ENGINEERING_CANONICAL_BLOCKED"

    def assert_no_bare_unknown(value: object, *, path: str = "payload") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                assert item is not None, f"{path}.{key} contains bare null"
                assert_no_bare_unknown(item, path=f"{path}.{key}")
        elif isinstance(value, list):
            assert value, f"{path} contains a bare empty list"
            for index, item in enumerate(value):
                assert_no_bare_unknown(item, path=f"{path}[{index}]")

    assert_no_bare_unknown(canonical.payload)


def test_readdressed_prd_registry_cannot_replace_verbatim_source_text() -> None:
    from ntruth.conformance.examples import (
        PrdV8ExampleRegistry,
        load_installed_prd_v8_example_registry,
    )

    registry = load_installed_prd_v8_example_registry()
    payload = registry.model_dump(mode="json")
    payload["examples"][0]["verbatim_source"] = "silently_repaired: true"
    addressed_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"registry_id", "declared_checksum"}
    }
    blob = json.dumps(
        addressed_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    checksum = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    payload["declared_checksum"] = checksum
    payload["registry_id"] = f"PRD-V8-EXAMPLES-{checksum[:20]}"

    with pytest.raises(ValidationError, match="verbatim"):
        PrdV8ExampleRegistry.model_validate(payload)


def test_packaged_schema_snapshot_is_exactly_runtime_derived() -> None:
    from ntruth.schemas.schema_snapshot import load_installed_kernel_schema_snapshot

    snapshot = load_installed_kernel_schema_snapshot()

    assert snapshot.schema_version == "8.0.0"
    assert snapshot.schemas == kernel_json_schemas()
    assert {
        "block_boundary_predicate",
        "derived_claim",
        "derived_claim_set",
        "boundary_change_reference",
        "experiment_block_boundary_change_ledger",
        "scenario_coverage",
        "profile_coverage_statement",
        "report_bundle",
        "planned_design_record",
        "executed_design_record",
        "plan_execution_reconciliation",
    } <= set(snapshot.schemas)
    serialized = json.dumps(snapshot.schemas, ensure_ascii=False, sort_keys=True)
    assert "PRD v7" not in serialized
    assert "DEPRECATED_V7_ADAPTER" not in serialized


def test_boundary_change_ledger_is_public_in_the_v8_schema_namespace() -> None:
    import ntruth.schemas as schemas

    assert schemas.BlockBoundaryCriterion
    assert schemas.BlockBoundaryPredicate
    assert schemas.InternalQueryRepresentability
    assert schemas.BoundaryChangeReference
    assert schemas.ExperimentBlockBoundaryChangeLedger
    assert schemas.build_experiment_block_boundary_change
    assert schemas.build_experiment_block_boundary_change_ledger
    assert schemas.append_experiment_block_boundary_change_ledger
    assert schemas.verify_experiment_block_boundary_change_ledger


def test_repository_truth_gate_covers_links_map_examples_schema_and_ci() -> None:
    run = subprocess.run(
        [sys.executable, "scripts/check_prd_v8_contracts.py", "--root", str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert run.returncode == 0, run.stdout + run.stderr
    payload = json.loads(run.stdout)
    assert payload["status"] == "PASS"
    assert payload["checks"] == {
        "architecture_map": "PASS",
        "current_document_links": "PASS",
        "kernel_schema_snapshot": "PASS",
        "prd_examples": "PASS",
        "requirements_matrix": "PASS",
        "theory_rulebook_conformance": "PASS",
    }


def test_final_requirement_matrix_reconciles_every_phase_one_requirement() -> None:
    baseline = (
        ROOT / "docs" / "audits" / "prd-v8-full-migration" / "REQUIREMENT_TRACEABILITY_MATRIX.md"
    ).read_text(encoding="utf-8")
    final = (
        ROOT / "docs" / "audits" / "prd-v8-full-migration" / "FINAL_IMPLEMENTATION_MATRIX.md"
    ).read_text(encoding="utf-8")

    baseline_ids = {
        line.split(":", maxsplit=1)[0].removeprefix("| ")
        for line in baseline.splitlines()
        if line.startswith("| V8-")
    }
    final_rows = [line for line in final.splitlines() if line.startswith("| V8-")]
    final_ids = [line.split("|", maxsplit=2)[1].strip() for line in final_rows]
    final_statuses = [line.split("|")[4].strip() for line in final_rows]

    assert len(baseline_ids) == 88
    assert len(final_ids) == 88
    assert len(final_ids) == len(set(final_ids))
    assert set(final_ids) == baseline_ids
    assert set(final_statuses) <= {"IMPLEMENTED", "PARTIAL", "MISSING"}
    assert "IMPLEMENTED_WITH_EXPLICIT_BLOCKERS" in final


def test_every_partial_or_missing_requirement_names_a_registered_blocker() -> None:
    audit_root = ROOT / "docs" / "audits" / "prd-v8-full-migration"
    final = (audit_root / "FINAL_IMPLEMENTATION_MATRIX.md").read_text(encoding="utf-8")
    register = (audit_root / "SCIENTIFIC_REVIEW_REGISTER.md").read_text(encoding="utf-8")
    registered = set(re.findall(r"^\| (SRR-V8-[0-9]{3}) \|", register, re.MULTILINE))

    failures: list[str] = []
    for line in final.splitlines():
        if not line.startswith("| V8-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 8 or cells[3] not in {"PARTIAL", "MISSING"}:
            continue
        blockers = set(re.findall(r"SRR-V8-[0-9]{3}", cells[6]))
        if not blockers:
            failures.append(f"{cells[0]}: missing blocker ID")
            continue
        unknown = sorted(blockers - registered)
        if unknown:
            failures.append(f"{cells[0]}: unregistered blockers {unknown}")

    assert failures == []


@pytest.mark.parametrize(
    ("replacement", "expected"),
    (
        ("Human review remains required", "lacks a blocker ID"),
        ("Human review remains required (`SRR-V8-999`)", "unregistered blocker IDs"),
        (
            "Human review remains required (`SRR-V8-001`, `999`)",
            "non-canonical blocker shorthand",
        ),
        (
            "Human review remains required (`SRR-V8-001`\N{EN DASH}`999`)",
            "non-canonical blocker shorthand",
        ),
    ),
)
def test_contract_gate_rejects_missing_or_unregistered_matrix_blockers(
    tmp_path: Path,
    replacement: str,
    expected: str,
) -> None:
    script = ROOT / "scripts" / "check_prd_v8_contracts.py"
    spec = importlib.util.spec_from_file_location("ntruth_prd_v8_contract_gate", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    source = ROOT / "docs" / "audits" / "prd-v8-full-migration"
    target = tmp_path / "docs" / "audits" / "prd-v8-full-migration"
    target.mkdir(parents=True)
    for name in (
        "FINAL_IMPLEMENTATION_MATRIX.md",
        "REQUIREMENT_TRACEABILITY_MATRIX.md",
        "SCIENTIFIC_REVIEW_REGISTER.md",
    ):
        (target / name).write_text((source / name).read_text(encoding="utf-8"), encoding="utf-8")

    final_path = target / "FINAL_IMPLEMENTATION_MATRIX.md"
    lines = final_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("| V8-AES |"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        cells[6] = replacement
        lines[index] = "| " + " | ".join(cells) + " |"
        break
    else:  # pragma: no cover - the canonical matrix gate catches this first
        raise AssertionError("V8-AES row missing")
    final_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    diagnostics = module._requirements_matrix_diagnostics(tmp_path)
    assert any(expected in diagnostic for diagnostic in diagnostics), diagnostics


def test_current_public_docs_name_v8_as_current_and_v7_only_as_deprecated() -> None:
    current_docs = (
        ROOT / "README.md",
        ROOT / "docs" / "status-snapshot.md",
        ROOT / "docs" / "public-specification-v0.1.md",
        ROOT / "docs" / "architettura.md",
        ROOT / "docs" / "releasing.md",
        ROOT / "CONTRIBUTING.md",
    )
    combined = "\n".join(path.read_text(encoding="utf-8") for path in current_docs)

    assert "PRD v8.0" in combined
    assert "DEPRECATED_V7_ADAPTER" in combined
    assert "PRD v7.0 current" not in combined
    assert "v7.0 current" not in combined
    assert "IMPLEMENTED_WITH_EXPLICIT_BLOCKERS" in combined


def test_v2_v3_parser_training_and_validation_guides_are_historical_only() -> None:
    docs_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    historical_offset = docs_index.index("## Historical records")
    historical_guides = (
        "parser-ai-contract.md",
        "mlx-training-pipeline.md",
        "validation-protocol-draft.md",
        "data-and-model-development.md",
        "system-card-v0.1.md",
        "governance-workflow.md",
        "governance/external-engagement-policy.md",
        "data-management-plan-draft.md",
        "training/DECISION-hold-pending-real-anchor.md",
    )
    for relative in historical_guides:
        document = (ROOT / "docs" / relative).read_text(encoding="utf-8")
        assert "HISTORICAL_NON_NORMATIVE" in document
        assert docs_index.index(relative) > historical_offset

    current = ROOT / "docs" / "prd-v8-data-training-evaluation-boundary.md"
    text = current.read_text(encoding="utf-8")
    assert "ParserCandidateOutput" in text
    assert "GoldParserTarget" in text
    assert "EXTERNAL_CHALLENGE" in text
    assert "HOLD" in text
    assert "ParserAIOutput" not in text


def test_ci_and_pr_template_expose_explicit_prd_v8_gates() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    template = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")

    assert "scripts/check_prd_v8_contracts.py" in ci
    assert "PRD v8 examples, schema and architecture truth" in ci
    assert "Theory ↔ Rulebook" in template
    assert "Determinability ↔ adequacy separation" in template
    assert "NO_CORPUS" in template
