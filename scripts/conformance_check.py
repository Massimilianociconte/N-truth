"""Conformance harness Theory/Rulebook (PRD v8.0 §20.3, §26.3, NFR-33).

Verifica, sugli artefatti reali:

(a) clause coverage - ogni clausola theory e' riferita da almeno una regola
    oppure dichiarata esplicitamente uncovered con rationale (NFR-33);
(b) consistenza regola<->clausola - ogni regola v8 abilitata mappa a una
    clausola esistente; nessuna mappatura orfana;
(c) discrimine delle fixture - ogni clausola collegata a regole ha almeno una
    fixture positiva e una negativa (Implementation Conformance Fixtures o
    Theory Reference Set); i gap marcati SCIENTIFIC_REVIEW_REQUIRED sono
    riportati ma non bloccano in modalita' non-strict;
(d) release blocker §10.11 - regole senza teoria.

Exit code 0 solo se non ci sono blocker non marcati; ``--strict`` fallisce
anche in presenza di qualsiasi gap SCIENTIFIC_REVIEW_REQUIRED.

Uso: ``uv run python scripts/conformance_check.py [--strict]``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "packages"))

from ntruth.derivation_theory import DerivationTheory, load_theory_ref  # noqa: E402
from ntruth.rules.loader import load_ruleset  # noqa: E402
from ntruth.schemas.rules import Ruleset, TheoryLinkageStatus  # noqa: E402

SRR = TheoryLinkageStatus.SCIENTIFIC_REVIEW_REQUIRED

CATEGORY_COVERAGE = "clause_coverage"
CATEGORY_CONSISTENCY = "rule_clause_consistency"
CATEGORY_FIXTURES = "fixture_discriminativeness"
CATEGORY_BLOCKER = "release_blocker"

SEVERITY_BLOCKER = "blocker"
SEVERITY_SRR = "srr_gap"
SEVERITY_OK = "ok"


@dataclass(frozen=True)
class ConformanceFinding:
    """Esito singolo del conformance harness (PRD §26.3)."""

    category: str
    severity: str
    code: str
    detail: str


@dataclass(frozen=True)
class ConformanceReport:
    """Report completo: findings + stato per clausola."""

    theory_ref: str
    ruleset_ref: str
    findings: tuple[ConformanceFinding, ...] = ()
    clause_rule_map: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def unmarked_blockers(self) -> tuple[ConformanceFinding, ...]:
        return tuple(f for f in self.findings if f.severity == SEVERITY_BLOCKER)

    @property
    def srr_gaps(self) -> tuple[ConformanceFinding, ...]:
        return tuple(f for f in self.findings if f.severity == SEVERITY_SRR)

    def ok(self, *, strict: bool = False) -> bool:
        return not self.unmarked_blockers and not (strict and self.srr_gaps)


def _theory_reference_entries(repo_root: Path) -> dict[str, dict]:
    """Voci del Theory Reference Set per clause_id (PRD §10.9)."""
    manifest_path = repo_root / "tests" / "theory_reference" / "manifest.json"
    if not manifest_path.is_file():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries: dict[str, dict] = {}
    for item in manifest.get("entries", []):
        entry_path = repo_root / item["path"]
        if not entry_path.is_file():
            continue
        payload = yaml.safe_load(entry_path.read_text(encoding="utf-8"))
        entry = payload.get("theory_reference_entry", {})
        entries[entry.get("clause_id", item["clause_id"])] = entry
    return entries


def run_conformance(
    ruleset: Ruleset,
    theory: DerivationTheory,
    *,
    repo_root: Path = REPO_ROOT,
) -> ConformanceReport:
    """Esegue le verifiche (a)-(d) sugli artefatti reali."""
    findings: list[ConformanceFinding] = []
    label = f"{ruleset.ruleset_id}@{ruleset.version}"

    if ruleset.theory_version is None:
        findings.append(
            ConformanceFinding(
                CATEGORY_BLOCKER,
                SEVERITY_BLOCKER,
                "LEGACY_RULESET",
                f"ruleset {label} non dichiara theory_version: nessun conformance theory possibile",
            )
        )
        return ConformanceReport(theory.theory_ref, label, tuple(findings))

    if theory.metadata.status.value == SRR.value:
        findings.append(
            ConformanceFinding(
                CATEGORY_COVERAGE,
                SEVERITY_SRR,
                "THEORY_UNREVIEWED",
                f"teoria {theory.theory_ref} non revisionata (registro {theory.metadata.srr_entry or 'SRR'})",
            )
        )

    clause_ids = set(theory.clause_ids())
    clause_rule_map: dict[str, list[str]] = {cid: [] for cid in clause_ids}

    # (b) consistenza regola <-> clausola.
    for rule in ruleset.rules:
        if rule.theory_clause is not None:
            if rule.theory_clause not in clause_ids:
                findings.append(
                    ConformanceFinding(
                        CATEGORY_CONSISTENCY,
                        SEVERITY_BLOCKER,
                        "ORPHAN_CLAUSE_MAPPING",
                        f"regola {rule.rule_id} mappa alla clausola inesistente {rule.theory_clause}",
                    )
                )
                continue
            clause_rule_map[rule.theory_clause].append(rule.rule_id)
            if not rule.enabled:
                findings.append(
                    ConformanceFinding(
                        CATEGORY_CONSISTENCY,
                        SEVERITY_SRR,
                        "DISABLED_MAPPED_RULE",
                        f"regola {rule.rule_id} mappata a {rule.theory_clause} ma disabilitata",
                    )
                )
        else:
            # (d) release blocker §10.11: regola senza teoria.
            if rule.enabled:
                findings.append(
                    ConformanceFinding(
                        CATEGORY_BLOCKER,
                        SEVERITY_BLOCKER,
                        "RULE_WITHOUT_THEORY",
                        f"regola abilitata {rule.rule_id} senza theory clause (release blocker §10.11)",
                    )
                )
            elif rule.theory_status is SRR:
                findings.append(
                    ConformanceFinding(
                        CATEGORY_BLOCKER,
                        SEVERITY_SRR,
                        "RULE_WITHOUT_THEORY_SRR",
                        f"regola {rule.rule_id} senza clausola difendibile: disabilitata e marcata "
                        f"{SRR.value}; blocker per release readiness fino a revisione",
                    )
                )
            else:
                findings.append(
                    ConformanceFinding(
                        CATEGORY_BLOCKER,
                        SEVERITY_BLOCKER,
                        "RULE_WITHOUT_THEORY_UNMARKED",
                        f"regola disabilitata {rule.rule_id} senza clausola e senza marcatura {SRR.value}",
                    )
                )

    declared_gaps = {gap.clause_id: gap.rationale for gap in ruleset.theory_coverage_gaps}
    for gap in ruleset.theory_coverage_gaps:
        if gap.clause_id not in clause_ids:
            findings.append(
                ConformanceFinding(
                    CATEGORY_CONSISTENCY,
                    SEVERITY_BLOCKER,
                    "ORPHAN_COVERAGE_GAP",
                    f"coverage gap riferisce la clausola inesistente {gap.clause_id}",
                )
            )

    # (a) clause coverage + (c) discrimine delle fixture.
    reference_entries = _theory_reference_entries(repo_root)
    for clause in theory.clauses:
        wired = tuple(clause_rule_map[clause.clause_id])
        if not wired:
            if clause.clause_id in declared_gaps:
                findings.append(
                    ConformanceFinding(
                        CATEGORY_COVERAGE,
                        SEVERITY_SRR,
                        "DECLARED_UNCOVERED_CLAUSE",
                        f"clausola {clause.clause_id} dichiarata uncovered con rationale: "
                        f"{declared_gaps[clause.clause_id]}",
                    )
                )
            else:
                findings.append(
                    ConformanceFinding(
                        CATEGORY_COVERAGE,
                        SEVERITY_BLOCKER,
                        "UNCOVERED_CLAUSE",
                        f"clausola {clause.clause_id} senza regole e senza dichiarazione di coverage",
                    )
                )
            continue

        fixture_kinds: set[str] = set()
        for rule in ruleset.rules:
            if rule.rule_id in wired:
                fixture_kinds.update(f.kind.value for f in rule.fixtures)
        entry = reference_entries.get(clause.clause_id)
        if entry:
            behavior = entry.get("expected_behavior", {})
            if behavior.get("positive"):
                fixture_kinds.add("positive")
            if behavior.get("negative"):
                fixture_kinds.add("negative")
        missing = {"positive", "negative"} - fixture_kinds
        if missing:
            findings.append(
                ConformanceFinding(
                    CATEGORY_FIXTURES,
                    SEVERITY_SRR,
                    "FIXTURE_DISCRIMINATIVENESS_GAP",
                    f"clausola {clause.clause_id} senza fixture {sorted(missing)} "
                    f"(gap marcato {SRR.value})",
                )
            )

    return ConformanceReport(
        theory_ref=theory.theory_ref,
        ruleset_ref=label,
        findings=tuple(findings),
        clause_rule_map={cid: tuple(rules) for cid, rules in clause_rule_map.items()},
    )


def _load_artifacts(ruleset_version: str) -> tuple[Ruleset, DerivationTheory]:
    ruleset = load_ruleset("ntruth-core", ruleset_version)
    if ruleset.theory_version is None:
        raise ValueError(
            f"ruleset ntruth-core@{ruleset_version} e' legacy: nessuna teoria dichiarata"
        )
    return ruleset, load_theory_ref(ruleset.theory_version)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Theory/Rulebook conformance harness (PRD §26.3)")
    parser.add_argument(
        "--ruleset-version", default="0.3.0", help="Versione del ruleset ntruth-core."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fallisce anche in presenza di gap SCIENTIFIC_REVIEW_REQUIRED.",
    )
    args = parser.parse_args(argv)

    ruleset, theory = _load_artifacts(args.ruleset_version)
    report = run_conformance(ruleset, theory)

    for finding in report.findings:
        print(f"[{finding.severity:>8}] {finding.category}/{finding.code}: {finding.detail}")
    print(
        f"theory={report.theory_ref} ruleset={report.ruleset_ref} "
        f"blocker_non_marcati={len(report.unmarked_blockers)} gap_srr={len(report.srr_gaps)}"
    )
    if not report.ok(strict=args.strict):
        print("CONFORMANCE: FAIL")
        return 1
    print("CONFORMANCE: OK" + (" (strict)" if args.strict else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
