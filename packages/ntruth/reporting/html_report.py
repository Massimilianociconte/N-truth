"""Report HTML stampabile e navigabile (PRD 20, FR-024, FR-027).

Ogni alert apre la propria evidenza. Il renderer legge solo il Report: non
esiste un percorso per cui l'HTML mostri un fatto assente dal JSON (PRD 11.3).
"""

from __future__ import annotations

import html
from collections.abc import Iterable
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from ntruth import DISCLAIMER
from ntruth.schemas.core import EvidenceSpan, Severity
from ntruth.schemas.experiment import Alert, DataSufficiency, ExperimentBlock, UnitAssessment
from ntruth.schemas.report import Report

SEVERITY_LABEL_IT: dict[str, str] = {
    "critical": "critico",
    "high": "alto",
    "medium": "medio",
    "info": "informativo",
    "insufficient": "informazione insufficiente",
}

RISK_LABEL_IT: dict[str, str] = {
    "no_issue": "nessun problema rilevato",
    "potential_pseudoreplication": "pseudoreplicazione possibile",
    "likely_pseudoreplication": "pseudoreplicazione probabile",
    "critical_pseudoreplication": "pseudoreplicazione critica",
    "insufficient_information": "informazione insufficiente",
}

_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.INSUFFICIENT: 3,
    Severity.INFO: 4,
}

_TEMPLATE = """<!doctype html>
<html lang="{{ report.language }}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>N-Truth — {{ report.project_name }}</title>
<style>
:root {
  --bg: #ffffff; --fg: #17242e; --muted: #5a6b78; --line: #d9e1e7;
  --card: #f7fafb; --critical: #b3261e; --high: #b25b00; --medium: #8a6d00;
  --info: #12626b; --insufficient: #4b4f7a; --accent: #12626b;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#12181d; --fg:#e6edf2; --muted:#9fb0bd; --line:#2a353e; --card:#1a222a;
          --critical:#ff7b72; --high:#ffa657; --medium:#e3c46a; --info:#68d0d8;
          --insufficient:#a9adde; --accent:#68d0d8; }
}
* { box-sizing: border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
  font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  max-width:64rem; margin-inline:auto; }
h1 { font-size:1.7rem; margin:0 0 .25rem; }
h2 { font-size:1.2rem; margin:2.25rem 0 .75rem; border-bottom:1px solid var(--line);
  padding-bottom:.35rem; }
h3 { font-size:1rem; margin:1.25rem 0 .4rem; }
p, li { margin:.4rem 0; }
.sub { color:var(--muted); margin:0 0 1.25rem; }
.card { background:var(--card); border:1px solid var(--line); border-radius:.5rem;
  padding:.85rem 1rem; margin:.75rem 0; }
.badge { display:inline-block; font-size:.72rem; letter-spacing:.04em; text-transform:uppercase;
  padding:.15rem .5rem; border-radius:.25rem; border:1px solid currentColor; font-weight:600; }
.sev-critical { color:var(--critical); } .sev-high { color:var(--high); }
.sev-medium { color:var(--medium); } .sev-info { color:var(--info); }
.sev-insufficient { color:var(--insufficient); }
table { border-collapse:collapse; width:100%; font-size:.92rem; }
th, td { text-align:left; padding:.4rem .55rem; border-bottom:1px solid var(--line);
  vertical-align:top; }
th { color:var(--muted); font-weight:600; }
.scroll { overflow-x:auto; }
code, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.85em; }
details { margin:.4rem 0; }
summary { cursor:pointer; color:var(--accent); }
blockquote { margin:.4rem 0 .4rem .5rem; padding:.35rem .75rem; border-left:3px solid var(--line);
  color:var(--muted); font-size:.9rem; }
.disclaimer { border:1px solid var(--line); border-left:4px solid var(--accent);
  padding:.75rem 1rem; border-radius:.35rem; font-size:.9rem; color:var(--muted); }
ul.plain { padding-left:1.1rem; }
.kv { display:grid; grid-template-columns:minmax(9rem,auto) 1fr; gap:.2rem .9rem; font-size:.92rem; }
.kv dt { color:var(--muted); } .kv dd { margin:0; }
.layer { border-left:3px solid var(--line); padding-left:.7rem; margin:.55rem 0; }
.path-ready_for_review { color:#1c6b42; }
.path-conditional, .path-incomplete { color:var(--insufficient); }
</style>
</head>
<body>
<h1>N-Truth — {{ report.project_name }}</h1>
<p class="sub">Report locale del disegno sperimentale · ruleset
  <span class="mono">{{ report.versions.ruleset_id }}@{{ report.versions.ruleset_version }}</span>
  · schema <span class="mono">{{ report.versions.schema_version }}</span></p>

<div class="disclaimer">{{ disclaimer }}</div>

<h2>Sintesi</h2>
<div class="scroll">
<table>
  <tr><th>Blocchi</th><td>{{ totals.blocks }}</td></tr>
  <tr><th>Compilazioni astenute</th><td>{{ totals.compiler_abstained }}</td></tr>
  <tr><th>Alert</th><td>{{ totals.alerts }} (critical: {{ totals.critical }},
    informazione insufficiente: {{ totals.insufficient }})</td></tr>
  <tr><th>Domande aperte</th><td>{{ totals.questions }}</td></tr>
  <tr><th>Conflitti non risolti</th><td>{{ totals.unresolved_conflicts }}</td></tr>
</table>
</div>

{% for block in report.blocks %}
<h2>Blocco: {{ block.title }}</h2>

<h3>Fattori, allocazione e applicazione</h3>
{% if block.factors %}
<div class="scroll">
<table>
  <tr><th>Fattore</th><th>Livelli</th><th>Allocation level</th>
    <th>Application level</th><th>Randomizzazione</th></tr>
  {% for factor in block.factors %}
  <tr>
    <td>{{ factor.name }}</td>
    <td>{{ factor.levels | join(", ") if factor.levels else "non riportati" }}</td>
    <td>{{ factor.allocation_level or "non determinato" }}</td>
    <td>{{ factor.application_level or "non determinato" }}</td>
    <td>{{ "si" if factor.randomized is sameas true else "no" if factor.randomized is sameas false else "non riportata" }}</td>
  </tr>
  {% endfor %}
</table>
</div>
{% else %}
<p class="sub">Nessun fattore identificato nel blocco.</p>
{% endif %}

{% set compilation = report.design_compilations.get(block.id) %}
<h3>Target inferenziale e compilazione</h3>
{% if compilation %}
<div class="card">
  <span class="badge {{ 'sev-info' if not compilation.abstained else 'sev-insufficient' }}">
    {{ compilation.status.value }}
  </span>
  <p><strong>Supporto della popolazione target:</strong>
    {{ compilation.analysis_handoff.target_population_support.value }}</p>
  {% if compilation.analysis_handoff.targets %}
  {% for target in compilation.analysis_handoff.targets %}
  <dl class="kv">
    <dt>Domanda</dt><dd>{{ target.question_text or "non dichiarata" }}</dd>
    <dt>Claim</dt><dd>{{ target.claim_text or "non dichiarato" }}</dd>
    <dt>Popolazione</dt><dd>{{ target.population_of_inference or "non dichiarata" }}</dd>
    <dt>Stato</dt><dd>{{ target.status.value }} · {{ target.target_population_support.value }}</dd>
  </dl>
  {% endfor %}
  {% else %}
  <p class="sub">Nessun target inferenziale dichiarato: l'handoff resta bloccato.</p>
  {% endif %}
  {% if compilation.analysis_handoff.estimands %}
  <h3>Estimand nell'analysis handoff</h3>
  <div class="scroll">
  <table>
    <tr><th>Endpoint</th><th>Misura dell'effetto</th><th>Popolazione o unita target</th>
      <th>Generalizzazione</th><th>Fattori</th><th>Tempo / condizione</th></tr>
    {% for estimand in compilation.analysis_handoff.estimands %}
    <tr>
      <td>{{ endpoint_name(block, estimand.endpoint_id) }}</td>
      <td>{{ estimand.effect_measure }}</td>
      <td>{{ estimand.target_population_or_unit }}</td>
      <td>{{ estimand.generalization_level }}</td>
      <td>{{ factor_names(block, estimand.factor_ids) }}</td>
      <td>{{ estimand.timepoint or "—" }} / {{ estimand.condition or "—" }}</td>
    </tr>
    {% endfor %}
  </table>
  </div>
  {% else %}
  <p class="sub">Nessun estimand minimo disponibile nell'analysis handoff.</p>
  {% endif %}
  {% if compilation.elicitation.blocking_question_ids %}
  <p class="sub">Domande bloccanti: {{ compilation.elicitation.blocking_question_ids | length }}.</p>
  {% endif %}
  <p class="sub">Il compiler non seleziona test, formule o power analysis.</p>
</div>
{% else %}
<p class="sub">Esito del design compiler non disponibile in questo report legacy.</p>
{% endif %}

{% set positive = report.positive_outputs.get(block.id) %}
{% if positive %}
<h3>Percorso positivo e bozza Methods</h3>
<div class="card">
  <span class="badge path-{{ positive.path_status.value }}">{{ positive.path_status.value }}</span>
  <p>{{ positive.status_reason }}</p>
  <p><strong>Bozza non certificante:</strong> {{ positive.methods_statement.text }}</p>
  {% for limitation in positive.methods_statement.limitations %}
  <p class="sub">{{ limitation }}</p>
  {% endfor %}
  {% if positive.candidate_analysis_strategies %}
  <p><strong>Strategie candidate da discutere con il biostatistico:</strong></p>
  <ul class="plain">
  {% for strategy in positive.candidate_analysis_strategies %}<li>{{ strategy }}</li>{% endfor %}
  </ul>
  {% endif %}
</div>

<details>
  <summary>Checklist DRIVER informativa (non certificante)</summary>
  <div class="scroll"><table>
    <tr><th>Voce</th><th>Stato osservato</th><th>Limite</th></tr>
    {% for item in positive.driver_checklist %}
    <tr><td><a href="{{ item.source_url }}">{{ item.item_id }} · {{ item.title }}</a></td>
      <td>{{ item.status.value }}</td><td>{{ item.note }}</td></tr>
    {% endfor %}
  </table></div>
</details>

<details>
  <summary>Fatti, inferenze, ipotesi e limiti</summary>
  {% for statement in positive.statements %}
  <div class="layer"><span class="badge">{{ statement.layer.value }}</span> {{ statement.text }}</div>
  {% endfor %}
</details>
{% endif %}

<h3>Unita e n per scope</h3>
<div class="scroll">
<table>
<tr>
  <th>Fattore / contrasto</th><th>Endpoint</th><th>Unita sperimentale</th>
  <th>Unita osservazionale</th><th>n dichiarato</th><th>n osservazionale</th>
  <th>n indipendente</th><th>Inferibilita</th><th>Rischio</th>
</tr>
{% for a in block.unit_assessments %}
<tr>
  <td>{{ scope_factor(block, a) }}</td>
  <td>{{ scope_endpoint(block, a) }}</td>
  <td>{{ a.experimental_unit or "non determinata" }}</td>
  <td>{{ a.observational_unit or "non determinata" }}</td>
  <td>{{ a.n_declared if a.n_declared is not none else "non riportato" }}</td>
  <td>{{ a.n_observational if a.n_observational is not none else "non determinato" }}</td>
  <td><strong>{{ a.n_independent if a.n_independent is not none else "non determinabile" }}</strong></td>
  <td>{{ a.inferability.value }}</td>
  <td>{{ risk_label(a.risk.value) }}</td>
</tr>
{% endfor %}
</table>
</div>

{% for a in block.unit_assessments %}
<details>
  <summary>Motivazione — {{ scope_factor(block, a) }} / {{ scope_endpoint(block, a) }}</summary>
  <p>{{ a.rationale }}</p>
  <dl class="kv">
    <dt>Unita biologica</dt><dd>{{ a.biological_unit or "non determinata" }}</dd>
    <dt>Unita analitica</dt><dd>{{ a.analytical_unit or "non determinata" }}</dd>
    <dt>Livelli di cluster</dt>
    <dd>{{ a.cluster_types | join(", ") if a.cluster_types else "nessuno rilevato" }}</dd>
    <dt>Completezza</dt><dd>{{ sufficiency(a.data_sufficiency) }}</dd>
  </dl>
</details>
{% endfor %}

<h3>Alert</h3>
{% if block.alerts %}
{% for alert in alerts_sorted(block) %}
<div class="card">
  <span class="badge sev-{{ alert.severity.value }}">{{ severity_label(alert.severity.value) }}</span>
  <span class="badge">{{ alert.alert_class.value }}</span>
  <span class="mono">{{ alert.rule_id }}@{{ alert.ruleset_version }}</span>
  <p>{{ alert.message }}</p>
  {% if alert.missing_information %}
  <p class="sub">Informazione mancante:
    {{ alert.missing_information | join("; ") }}</p>
  {% endif %}
  {% if evidence_of(block, alert) %}
  <details>
    <summary>Evidenza ({{ evidence_of(block, alert) | length }})</summary>
    {% for ev in evidence_of(block, alert) %}
    <blockquote><span class="mono">{{ ev.locator() }}</span> — {{ ev.text }}</blockquote>
    {% endfor %}
  </details>
  {% endif %}
  {% if alert.requires_human_confirmation %}
  <p class="sub">Richiede conferma umana prima di qualunque uso.</p>
  {% endif %}
</div>
{% endfor %}
{% else %}
<p class="sub">Nessun alert generato dal ruleset attivo.</p>
{% endif %}

<h3>Gerarchia ricostruita</h3>
<div class="scroll">
<table>
<tr><th>Livello</th><th>Conteggio</th><th>Contenuto in</th><th>Confidenza</th><th>Nota</th></tr>
{% for row in hierarchy_rows(block) %}
<tr><td>{{ row.level }}</td><td>{{ row.count }}</td><td>{{ row.parent }}</td>
    <td>{{ row.confidence }}</td><td>{{ row.note }}</td></tr>
{% endfor %}
</table>
</div>

{% if block.n_statements %}
<h3>Menzioni di n nel materiale</h3>
<div class="scroll">
<table>
<tr><th>Valore</th><th>Entita</th><th>Tipo</th><th>Testo originale</th><th>Fonte</th></tr>
{% for s in block.n_statements %}
<tr>
  <td>{{ s.value if s.value is not none else "—" }}</td>
  <td>{{ s.entity_type }}</td>
  <td>{{ s.node_type or "non risolta" }}</td>
  <td><code>{{ s.raw_text }}</code></td>
  <td class="mono">{{ locator_of(block, s.evidence_ids) }}</td>
</tr>
{% endfor %}
</table>
</div>
{% endif %}

{% if block.contradictions %}
<h3>Contraddizioni</h3>
<ul class="plain">
{% for c in block.contradictions %}
<li>{{ c.description }} <span class="sub">({{ c.status }})</span></li>
{% endfor %}
</ul>
{% endif %}

{% if block.questions %}
<h3>Domande da porre agli autori</h3>
<ul class="plain">
{% for q in block.questions %}<li>{{ "[decisiva] " if q.decisive else "" }}{{ q.text }}
  <span class="sub">— {{ q.reason }} · priorita {{ q.priority }}</span></li>{% endfor %}
</ul>
{% endif %}
{% endfor %}

{% if report.limits %}
<h2>Limiti dichiarati</h2>
<ul class="plain">{% for limit in report.limits %}<li>{{ limit }}</li>{% endfor %}</ul>
{% endif %}

{% if report.parser_warnings %}
<h2>Avvisi di parsing</h2>
<ul class="plain">{% for w in report.parser_warnings %}<li>{{ w }}</li>{% endfor %}</ul>
{% endif %}

<h2>Fonti e riproducibilita</h2>
<dl class="kv">
  <dt>Checksum input</dt><dd class="mono">{{ report.input_checksum[:32] }}</dd>
  <dt>Checksum ruleset</dt><dd class="mono">{{ report.ruleset_checksum[:32] }}</dd>
  <dt>Checksum contenuto</dt><dd class="mono">{{ content_checksum[:32] }}</dd>
  <dt>Parser</dt><dd class="mono">{{ report.versions.parser_version }}</dd>
  <dt>Grafo</dt><dd class="mono">{{ report.versions.graph_version }}</dd>
</dl>
</body>
</html>
"""


def render_html(report: Report) -> str:
    env = Environment(
        autoescape=True, undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True
    )
    template = env.from_string(_TEMPLATE)
    return template.render(
        report=report,
        totals=report.totals(),
        disclaimer=DISCLAIMER,
        content_checksum=report.content_checksum(),
        severity_label=lambda value: SEVERITY_LABEL_IT.get(value, value),
        risk_label=lambda value: RISK_LABEL_IT.get(value, value),
        scope_factor=_scope_factor,
        scope_endpoint=_scope_endpoint,
        endpoint_name=_endpoint_name,
        factor_names=_factor_names,
        evidence_of=_evidence_of,
        alerts_sorted=_alerts_sorted,
        hierarchy_rows=_hierarchy_rows,
        sufficiency=_sufficiency,
        locator_of=_locator_of,
    )


def write_html(report: Report, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path


def _scope_factor(block: ExperimentBlock, assessment: UnitAssessment) -> str:
    factor = block.factor(assessment.scope.factor_id) if assessment.scope.factor_id else None
    contrast = next((c for c in block.contrasts if c.id == assessment.scope.contrast_id), None)
    if factor is None:
        return "nessun fattore identificato"
    return f"{factor.name} · {contrast.label}" if contrast else factor.name


def _scope_endpoint(block: ExperimentBlock, assessment: UnitAssessment) -> str:
    endpoint = (
        block.endpoint(assessment.scope.endpoint_id) if assessment.scope.endpoint_id else None
    )
    return endpoint.name if endpoint else "non specificato"


def _endpoint_name(block: ExperimentBlock, endpoint_id: str) -> str:
    endpoint = block.endpoint(endpoint_id)
    return endpoint.name if endpoint is not None else endpoint_id


def _factor_names(block: ExperimentBlock, factor_ids: Iterable[str]) -> str:
    names = []
    for factor_id in factor_ids:
        factor = block.factor(factor_id)
        names.append(factor.name if factor is not None else factor_id)
    return ", ".join(names) or "non specificati"


def _evidence_of(block: ExperimentBlock, alert: Alert) -> list[EvidenceSpan]:
    return [e for e in (block.evidence_by_id(i) for i in alert.evidence_ids) if e is not None]


def _alerts_sorted(block: ExperimentBlock) -> list[Alert]:
    return sorted(block.alerts, key=lambda a: (_SEVERITY_ORDER.get(a.severity, 9), a.rule_id))


def _hierarchy_rows(block: ExperimentBlock) -> list[dict[str, str]]:
    by_id = {node.id: node for node in block.hierarchy.nodes}
    parents: dict[str, list[str]] = {}
    notes: dict[str, list[str]] = {}
    for relation in block.hierarchy.relations:
        source = by_id.get(relation.source)
        target = by_id.get(relation.target)
        if source is None or target is None:
            continue
        if str(relation.type) in {"nested_in", "derived_from"}:
            parents.setdefault(source.id, []).append(str(target.type))
            if relation.attributes.get("default_containment"):
                notes.setdefault(source.id, []).append("contenimento tecnico predefinito")

    rows: list[dict[str, str]] = []
    ordered = sorted(block.hierarchy.nodes, key=lambda n: n.rank if n.rank is not None else 999)
    for node in ordered:
        note_parts = list(notes.get(node.id, []))
        if node.attributes.get("conflicting_counts"):
            note_parts.append(f"conteggi in conflitto: {node.attributes['conflicting_counts']}")
        if node.attributes.get("count_scope") == "per_group":
            note_parts.append("conteggio riferito al gruppo")
        if node.attributes.get("declared_independent"):
            note_parts.append("dichiarato indipendente nel testo")
        rows.append(
            {
                "level": str(node.type),
                "count": str(node.count) if node.count is not None else "non riportato",
                "parent": ", ".join(parents.get(node.id, [])) or "—",
                "confidence": f"{node.confidence:.2f}",
                "note": "; ".join(note_parts) or "—",
            }
        )
    return rows


def _sufficiency(sufficiency: DataSufficiency) -> str:
    parts = [
        f"intervento: {sufficiency.intervention_level.value}",
        f"indipendenza sorgenti: {sufficiency.source_independence.value}",
        f"esclusioni: {sufficiency.exclusions.value}",
        f"aggregazione: {sufficiency.aggregation.value}",
        f"modello: {sufficiency.statistical_model.value}",
    ]
    return html.escape("; ".join(parts))


def _locator_of(block: ExperimentBlock, evidence_ids: Iterable[str]) -> str:
    for evidence_id in evidence_ids:
        evidence = block.evidence_by_id(evidence_id)
        if evidence is not None:
            return evidence.locator()
    return "—"
