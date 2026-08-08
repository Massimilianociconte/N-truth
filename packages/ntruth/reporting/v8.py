"""Validated neutral renderers for the canonical PRD v8 ReportBundle."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from ntruth.schemas.knowledge import KnowledgeValue
from ntruth.schemas.report_bundle import ReportBundle


def _validated(report: ReportBundle) -> ReportBundle:
    """Revalidate content addressing even for instances created through model_copy."""

    return ReportBundle.model_validate(report.model_dump(mode="python"))


def report_bundle_to_dict(report: ReportBundle) -> dict[str, Any]:
    return _validated(report).model_dump(mode="json")


def dumps_report_bundle_json(report: ReportBundle) -> str:
    return json.dumps(
        report_bundle_to_dict(report),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def write_report_bundle_json(report: ReportBundle, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps_report_bundle_json(report) + "\n", encoding="utf-8")
    return path


def write_report_bundle_yaml(report: ReportBundle, path: Path) -> Path:
    """Write deterministic YAML 1.2 using its canonical JSON subset."""

    return write_report_bundle_json(report, path)


def read_report_bundle_json(path: Path) -> ReportBundle:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReportBundle.model_validate(payload)


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _json_text(value: object) -> str:
    return escape(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str),
        quote=True,
    )


def _knowledge(value: KnowledgeValue[Any]) -> str:
    payload = value.model_dump(mode="json")
    state = payload.pop("knowledge_state")
    return f"<strong>{_e(state)}</strong><pre>{_json_text(payload)}</pre>"


def _items(values: tuple[str, ...]) -> str:
    return "".join(f"<li>{_e(value)}</li>" for value in values)


def render_report_bundle_html(report: ReportBundle) -> str:
    """Render every normative report axis without design-approval semantics."""

    report = _validated(report)
    context = report.design_record_context

    sources = "".join(
        "<tr>"
        f"<td>{_e(source.source_id)}</td>"
        f"<td>{_e(source.source_context.value)}</td>"
        f"<td>{_e(source.source_class.token)}</td>"
        f"<td>{_e(source.source_version)}</td>"
        "</tr>"
        for source in report.source_records
    )
    evidence_rows = "".join(
        "<tr>"
        f"<td>{_e(record.evidence_id)}</td>"
        f"<td>{_e(record.source_id)}</td>"
        f"<td>{_e(record.evidence_type.value)}</td>"
        f"<td>{_e(record.locator)}</td>"
        "</tr>"
        for record in report.evidence_records
    )
    claim_rows: list[str] = []
    proof_rows: list[str] = []
    for claim_set in report.claim_sets:
        for claim in claim_set.claims:
            claim_rows.append(
                "<tr>"
                f"<td>{_e(claim.inferential_query_id)}</td>"
                f"<td>{_e(claim.claim_id)}</td>"
                f"<td>{_e(claim.claim_type)}</td>"
                f'<td class="axis-determinability">{_e(claim.determinability_state.value)}</td>'
                f"<td>{_knowledge(claim.value)}</td>"
                f'<td class="axis-support">{_e(claim.support_grade.token)}</td>'
                "</tr>"
            )
            steps = "<br>".join(
                f"{_e(step.step_id)} · {_e(step.theory_clause_id)} · {_e(step.rule_id)}"
                for step in claim.proof_trace
            )
            proof_rows.append(
                "<tr>"
                f"<td>{_e(claim.claim_id)}</td>"
                f"<td>{steps}</td>"
                f"<td>{_json_text(claim.required_predicates)}</td>"
                f"<td>{_json_text(tuple(item.model_dump(mode='json') for item in claim.irrelevant_predicates))}</td>"
                f"<td>{_json_text(claim.assumptions)}</td>"
                f"<td>{_json_text(claim.sensitivity_records)}</td>"
                "</tr>"
            )

    adequacy_rows = "".join(
        "<tr>"
        f"<td>{_e(item.inferential_query_id)}</td>"
        f"<td>{_e(item.axis)}</td>"
        f'<td class="axis-adequacy">{_e(item.finding_type or item.outcome.knowledge_state.value)}</td>'
        f"<td>{_knowledge(item.outcome)}</td>"
        f"<td>{_e(item.rationale)}</td>"
        "</tr>"
        for item in report.design_adequacy_evaluations
    )
    scenario_rows = "".join(
        "<tr>"
        f"<td>{_e(item.status.value)}</td>"
        f"<td>{_e(item.profile_id)}</td>"
        f"<td>{_knowledge(item.omitted_dimensions)}</td>"
        f"<td>{_knowledge(item.caveat)}</td>"
        "</tr>"
        for item in report.scenario_coverages
    )
    count_rows = "".join(
        "<tr>"
        f"<td>{_e(item.count_id)}</td>"
        f"<td>{_e(item.kind.value)}</td>"
        f"<td>{_knowledge(item.value)}</td>"
        f"<td>{_e(item.quantifier.value)}</td>"
        f"<td>{_e(item.scope.query_id)}</td>"
        f"<td>{_json_text(item.scope.model_dump(mode='json'))}</td>"
        "</tr>"
        for item in report.count_records
    )
    question_rows = "".join(
        "<tr>"
        f"<td>{_e(item.question_id)}</td>"
        f"<td>{_e(item.inferential_query_id)}</td>"
        f"<td>{_e(item.text)}</td>"
        f"<td>{_json_text(item.evidence_required)}</td>"
        "</tr>"
        for item in report.questions
    )
    section_rows = "".join(
        "<tr>"
        f"<td>{_e(section.inferential_query.id)}</td>"
        f"<td>{_e(section.claim_set.claim_set_id)}</td>"
        f"<td>{_json_text(tuple(item.count_id for item in report.count_registry.records if item.count_id in section.count_record_ids))}</td>"
        f"<td>{_json_text(tuple(item.evaluation_id for item in section.adequacy_evaluations))}</td>"
        f"<td>{_json_text(tuple(item.status.value for item in section.scenario_coverages))}</td>"
        f"<td>{_e(section.profile_coverage.statement_id)}</td>"
        f"<td>{_knowledge(section.ai_candidates)}</td>"
        f"<td>{_knowledge(section.human_confirmations)}</td>"
        f"<td>{_knowledge(section.conflicts)}</td>"
        f"<td>{_knowledge(section.sensitivities)}</td>"
        f"<td>{_json_text(tuple(item.question_id for item in section.questions))}</td>"
        "</tr>"
        for section in report.query_sections
    )
    handoff_rows = "".join(
        "<tr>"
        f"<td>{_e(item.category.value)}</td>"
        f"<td>{_e(item.origin.value)}</td>"
        f"<td>{_e(item.authority.value)}</td>"
        f"<td>{_json_text(item.evidence_refs)}</td>"
        f"<td>{_e(item.inferential_query_id)}</td>"
        f"<td>{_json_text(item.predicate_ids)}</td>"
        f"<td>{_json_text(item.question_ids)}</td>"
        f"<td>{_e(item.user_note or '')}</td>"
        "</tr>"
        for item in report.statistical_handoff.items
    )
    prospective_ledger_rows = "".join(
        "<tr>"
        f"<td>{_e(ledger.ledger_id)}</td>"
        f"<td>{_e(ledger.content_checksum)}</td>"
        f"<td>{_e(ledger.request_checksum)}</td>"
        f"<td>{_json_text(tuple(item.artifact_id for item in ledger.artifacts))}</td>"
        "</tr>"
        for ledger in report.prospective_input_ledgers.value or ()
    )
    execution = context.executed_design_record.value
    executed_ledger = execution.executed_input_ledger if execution is not None else None
    executed_ledger_projection = (
        _json_text(executed_ledger.model_dump(mode="json"))
        if executed_ledger is not None
        else _e("NOT_APPLICABLE")
    )
    context_pins = _json_text(context.model_dump(mode="json"))
    execution_pins = _json_text(
        tuple(
            {
                "context_id": item.context_id,
                "context_checksum": item.content_checksum,
                "conformance_bundle_checksum": item.conformance_bundle_checksum,
                "execution_manifest_id": item.result.execution_manifest.manifest_id,
            }
            for item in report.verified_pipeline_contexts
        )
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>N-Truth PRD v8 neutral report {_e(report.report_id)}</title>
<style>
:root {{ color-scheme: light; --ink:#172033; --muted:#596579; --line:#cbd5e1; --panel:#f8fafc; }}
body {{ color:var(--ink); background:#fff; font:15px/1.5 system-ui,sans-serif; margin:0 auto; max-width:1180px; padding:2rem; }}
h1,h2 {{ line-height:1.2; }} h2 {{ border-bottom:1px solid var(--line); padding-bottom:.35rem; margin-top:2rem; }}
table {{ border-collapse:collapse; width:100%; }} th,td {{ border:1px solid var(--line); padding:.45rem; text-align:left; vertical-align:top; }}
th {{ background:var(--panel); }} pre {{ margin:.25rem 0; white-space:pre-wrap; overflow-wrap:anywhere; }}
.boundary {{ border:2px solid #475569; padding:1rem; }}
.axis-determinability {{ border-left:5px solid #2563eb; }}
.axis-support {{ border-left:5px solid #7c3aed; }}
.axis-adequacy {{ border-left:5px solid #d97706; }}
.axis-conflict {{ border-left:5px solid #b91c1c; }}
.neutral-note {{ color:var(--muted); font-weight:600; }}
</style>
</head>
<body>
<h1>N-Truth PRD v8 ReportBundle</h1>
<p>Report ID: <code>{_e(report.report_id)}</code> · checksum <code>{_e(report.content_checksum)}</code></p>
<p class="neutral-note">Determinability is not design approval. Each axis below is independent.</p>

<h2>Sources and design context</h2>
<p>Context: <strong>{_e(context.mode.value)}</strong></p>
<dl>
<dt>Planned design</dt><dd>{_knowledge(context.planned_design_record)}</dd>
<dt>Executed design</dt><dd>{_knowledge(context.executed_design_record)}</dd>
<dt>Reconciliation</dt><dd>{_knowledge(context.reconciliation_record)}</dd>
<dt>Retrospective sources</dt><dd>{_knowledge(context.retrospective_source_ids)}</dd>
</dl>
<table><thead><tr><th>Source</th><th>Context</th><th>Class</th><th>Version</th></tr></thead><tbody>{sources}</tbody></table>
<h3>Evidence ledger</h3>
<table><thead><tr><th>Evidence</th><th>Source</th><th>Type</th><th>Locator</th></tr></thead><tbody>{evidence_rows}</tbody></table>
<h3>Content-addressed input ledgers</h3>
<table><thead><tr><th>Ledger ID</th><th>Ledger checksum</th><th>Request checksum</th><th>Artifact pins</th></tr></thead><tbody>{prospective_ledger_rows}</tbody></table>
<h3>Executed evidence and artifact ledger</h3><pre>{executed_ledger_projection}</pre>
<p>Full source/authority/evidence/support lineage is retained in the ledgers and records above.</p>

<h2>Confirmed graph</h2>
<pre>{_json_text(report.confirmed_graph.model_dump(mode="json"))}</pre>

<h2>AI candidates</h2>{_knowledge(report.ai_candidates)}

<h2>Human confirmations and conflicts</h2>
<h3>Confirmations</h3>{_knowledge(report.human_confirmations)}
<h3>Conflicts</h3><div class="axis-conflict">{_knowledge(report.conflicts)}</div>

<h2>Query-scoped derived claims</h2>
<p>Report resolution: {_knowledge(report.report_resolution.resolution)}</p>
<table><thead><tr><th>Query</th><th>Claim</th><th>Type</th><th>Determinability</th><th>Value</th><th>Support</th></tr></thead><tbody>{"".join(claim_rows)}</tbody></table>

<h3>Query report sections</h3>
<table><thead><tr><th>Query</th><th>Claim set</th><th>Counts</th><th>Adequacy</th><th>Scenarios</th><th>Profile</th><th>AI candidates</th><th>Confirmations</th><th>Conflicts</th><th>Sensitivities</th><th>Questions</th></tr></thead><tbody>{section_rows}</tbody></table>

<h2>Proof and support</h2>
<h3>Irrelevant predicates and rationale</h3>
<table><thead><tr><th>Claim</th><th>Proof trace</th><th>Required predicates</th><th>Irrelevant predicates and rationale</th><th>Assumptions</th><th>Sensitivity refs</th></tr></thead><tbody>{"".join(proof_rows)}</tbody></table>

<h2>Design adequacy findings</h2>
<table><thead><tr><th>Query</th><th>Axis</th><th>Finding</th><th>Outcome</th><th>Rationale</th></tr></thead><tbody>{adequacy_rows}</tbody></table>

<h2>Scenario and profile coverage</h2>
<table><thead><tr><th>Status</th><th>Profile</th><th>Omitted dimensions</th><th>Caveat</th></tr></thead><tbody>{scenario_rows}</tbody></table>
<p>Profile statement: <code>{_e(report.profile_coverage.statement_id)}</code></p>
<p>Known gaps: {_json_text(report.profile_coverage.known_gap_ids)}</p>

<h2>Counts</h2>
<h3>Full ten-dimensional count scope</h3>
<table><thead><tr><th>ID</th><th>Kind</th><th>Value</th><th>Quantifier</th><th>Query</th><th>Full scope</th></tr></thead><tbody>{count_rows}</tbody></table>

<h2>Sensitivity and questions</h2>
<h3>Sensitivity records</h3>{_knowledge(report.sensitivities)}
<table><thead><tr><th>ID</th><th>Query</th><th>Question</th><th>Evidence required</th></tr></thead><tbody>{question_rows}</tbody></table>

<h2>Statistical handoff</h2>
<p>Status: <strong>{_e(report.statistical_handoff.strategy_module_status.value)}</strong></p>
<table><thead><tr><th>Category</th><th>Origin</th><th>Authority</th><th>Evidence</th><th>Query</th><th>Predicates</th><th>Questions</th><th>Human user note</th></tr></thead><tbody>{handoff_rows}</tbody></table>

<h2>Inference limits</h2><ul>{_items(report.inference_limits)}</ul>

<h2>Provenance and versions</h2>
<p>Execution manifest <code>{_e(report.execution_manifest.manifest_id)}</code>; Theory {_e(report.execution_manifest.theory_version)}; Rulebook {_e(report.execution_manifest.rulebook_version)}.</p>
<h3>Full execution manifest pins</h3>
<pre>{_json_text(report.execution_manifest.model_dump(mode="json"))}</pre>
<h3>Review requirement</h3>
<pre>{_json_text(report.report_resolution.review_requirement.model_dump(mode="json") if report.report_resolution.review_requirement else "NOT_APPLICABLE")}</pre>
<h3>Contract and execution pins</h3>
<pre>{context_pins}</pre><pre>{execution_pins}</pre>

<p class="boundary">{_e(report.epistemic_boundary)}</p>
</body>
</html>
"""


def write_report_bundle_html(report: ReportBundle, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report_bundle_html(report), encoding="utf-8")
    return path


__all__ = [
    "dumps_report_bundle_json",
    "read_report_bundle_json",
    "render_report_bundle_html",
    "report_bundle_to_dict",
    "write_report_bundle_html",
    "write_report_bundle_json",
    "write_report_bundle_yaml",
]
