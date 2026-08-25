"""Determinability v7 + Value of Abstention contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.abstention import (
    AbstentionReport,
    BilingualText,
    ConditionRecord,
    empty_abstention_is_invalid,
)
from ntruth.graph.determinability_v7 import V7GraphFacts, derive_determinability_v7
from ntruth.schemas.authority import AuthorityLedger, ConflictRecord, make_conflict_id
from ntruth.schemas.core import Determinability
from ntruth.schemas.determinability_v7 import (
    FORBIDDEN_OUTPUTS,
    DeterminabilityStateV7,
    migrate_v3_state,
)


def test_v3_indeterminate_maps_to_insufficient_information() -> None:
    assert (
        migrate_v3_state(Determinability.INDETERMINATE)
        is DeterminabilityStateV7.INSUFFICIENT_INFORMATION
    )


def test_assertion_only_never_determinate() -> None:
    facts = V7GraphFacts(
        allocation_known=True,
        operational_independence_known=True,
        contrast_defined=True,
        endpoint_defined=True,
        counts_sufficient=True,
        interference_unknown=False,
        assertion_only=True,
    )
    assert derive_determinability_v7(facts) is DeterminabilityStateV7.INSUFFICIENT_INFORMATION


def test_unknown_interference_blocks_determinate() -> None:
    facts = V7GraphFacts(
        allocation_known=True,
        operational_independence_known=True,
        contrast_defined=True,
        endpoint_defined=True,
        counts_sufficient=True,
        interference_unknown=True,
    )
    assert derive_determinability_v7(facts) is DeterminabilityStateV7.INSUFFICIENT_INFORMATION


def test_unresolved_conflict_blocks_determinate() -> None:
    ledger = AuthorityLedger(ledger_id="l").append_conflict(
        ConflictRecord(
            id=make_conflict_id("allocation_level", ("a", "b")),
            field="allocation_level",
            sources=("a", "b"),
        )
    )
    facts = V7GraphFacts(
        allocation_known=True,
        operational_independence_known=True,
        contrast_defined=True,
        endpoint_defined=True,
        counts_sufficient=True,
        interference_unknown=False,
        decisive_fields=frozenset({"allocation_level"}),
    )
    assert (
        derive_determinability_v7(facts, ledger) is DeterminabilityStateV7.CONFLICTING_INFORMATION
    )


def test_conditionally_determinate_when_enumerable() -> None:
    facts = V7GraphFacts(
        allocation_known=False,
        operational_independence_known=True,
        contrast_defined=True,
        endpoint_defined=True,
        counts_sufficient=True,
        interference_unknown=False,
        missing_predicate="allocation_level",
        enumerable_branches=True,
    )
    assert derive_determinability_v7(facts) is DeterminabilityStateV7.CONDITIONALLY_DETERMINATE


def test_abstention_requires_eleven_elements() -> None:
    with pytest.raises(ValidationError):
        AbstentionReport(
            state=DeterminabilityStateV7.INSUFFICIENT_INFORMATION,
            observed_facts=(),
            author_assertions=(),
            candidate_model_facts=(),
            missing_decisive_fact="",
            plausible_scenarios=(),
            primary_question="",
            reporting_improvement="",
            inference_limit="",
            useful_artefacts=(),
            recommended_next_action="",
        )


def test_full_abstention_valid() -> None:
    from ntruth.abstention import PlausibleScenario

    report = AbstentionReport(
        state=DeterminabilityStateV7.INSUFFICIENT_INFORMATION,
        observed_facts=("two levels reported",),
        author_assertions=("n=3 per well claimed",),
        candidate_model_facts=("factor=treatment",),
        missing_decisive_fact="allocation level of treatment",
        plausible_scenarios=(
            PlausibleScenario(description="well-level", consequence="n per well"),
            PlausibleScenario(description="plate-level", consequence="n per plate"),
        ),
        primary_question="At which level was treatment allocated?",
        reporting_improvement="state allocation unit in Methods",
        inference_limit="independent_n cannot be finalised",
        useful_artefacts=("factor table", "sample sheet draft"),
        recommended_next_action="ask author for allocation unit",
    )
    assert empty_abstention_is_invalid(report.state)
    assert not report.is_empty_abstention


def test_condition_record_bilingual() -> None:
    rec = ConditionRecord(
        id="cond-1",
        predicate="allocation_level",
        human_readable=BilingualText(
            it="A quale livello e stato allocato il trattamento?",
            en="At which level was treatment allocated?",
        ),
        evidence_required=("methods sentence",),
        if_true_effect="independent_n at well",
        if_false_effect="independent_n at culture",
        primary_question_id="q1",
    )
    assert rec.human_readable.en.startswith("At which")


def test_forbidden_outputs_table_present() -> None:
    assert "eu_or_n_guess" in FORBIDDEN_OUTPUTS[DeterminabilityStateV7.INSUFFICIENT_INFORMATION]
