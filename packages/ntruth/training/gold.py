"""Target parser adjudicati, distinti dagli output candidati del modello."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from ntruth.parser_ai.stages import CandidateGraphSet, StageAuthority, StageStatus
from ntruth.schemas.core import FrozenModel, content_checksum

GOLD_PARSER_TARGET_VERSION: Literal["1.0.0"] = "1.0.0"


class SubmissionComparison(FrozenModel):
    """Differenza esplicita tra una submission cieca e il target adjudicato."""

    submission_id: str
    reviewer_role: str
    changed_paths: tuple[str, ...] = ()
    summary: str

    @field_validator("submission_id", "reviewer_role", "summary")
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("comparison di adjudication con campo vuoto")
        return normalized

    @field_validator("changed_paths")
    @classmethod
    def _valid_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("changed_paths duplicati")
        if any(not value.startswith("/") for value in values):
            raise ValueError("changed_paths deve contenere JSON Pointer")
        return values


class GoldParserTarget(FrozenModel):
    """Gold parser completo soltanto dopo doppia annotazione e adjudication.

    Il payload scientifico usa il contratto candidate-only v6, ma ne cambia
    l'autorita tramite provenance di adjudication. Non contiene determinability
    o verdict: tali output restano derivati dal motore deterministico.
    """

    schema_version: Literal["1.0.0"] = GOLD_PARSER_TARGET_VERSION
    target_id: str
    source_record_id: str
    guideline_version: str
    adjudication_id: str
    adjudication_rationale: str
    adjudicator_roles: tuple[str, ...] = Field(min_length=1)
    source_submission_ids: tuple[str, ...] = Field(min_length=2)
    comparisons: tuple[SubmissionComparison, ...] = Field(min_length=2)
    adjudicated_graph: CandidateGraphSet

    @field_validator(
        "target_id",
        "source_record_id",
        "guideline_version",
        "adjudication_id",
        "adjudication_rationale",
    )
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("GoldParserTarget con campo testuale vuoto")
        return normalized

    @field_validator("adjudicator_roles")
    @classmethod
    def _roles_are_explicit(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("adjudicator_roles contiene un ruolo vuoto")
        if len(normalized) != len(set(normalized)):
            raise ValueError("adjudicator_roles duplicati")
        return normalized

    @model_validator(mode="after")
    def _is_adjudicated(self) -> Self:
        if len(self.source_submission_ids) != len(set(self.source_submission_ids)):
            raise ValueError("source_submission_ids duplicati")
        comparison_ids = [item.submission_id for item in self.comparisons]
        if len(comparison_ids) != len(set(comparison_ids)):
            raise ValueError("una submission ha piu comparison")
        if set(comparison_ids) != set(self.source_submission_ids):
            raise ValueError("comparisons deve coprire esattamente le submission sorgenti")
        if self.adjudicated_graph.status is not StageStatus.COMPLETE:
            raise ValueError("il grafo gold deve avere status=complete")
        if self.adjudicated_graph.provenance.authority is not StageAuthority.ADJUDICATION:
            raise ValueError("il grafo gold richiede provenance authority=adjudication")
        return self

    def checksum(self) -> str:
        return content_checksum(self.model_dump(mode="json"))

    def model_candidate_graph(self) -> CandidateGraphSet:
        """Proietta il gold adjudicato nel contratto che il parser puo dichiarare.

        Review, adjudication e relative autorita restano nel wrapper gold e non
        vengono insegnate al modello come se fossero sue. Il target del modello
        conserva i fatti candidate-only ma usa sempre ``authority=model``.
        """

        graph = self.adjudicated_graph
        provenance = graph.provenance.model_copy(
            update={
                "stage_run_id": f"model-target-{self.target_id}",
                "authority": StageAuthority.MODEL,
                "producer": "ntruth-parser-candidate",
                "producer_version": "training-target-v6",
                "input_artifact_ids": (),
                "input_checksums": {},
                "parent_result_ids": (),
                "actor_role": None,
                "started_at": None,
                "completed_at": None,
            }
        )
        return graph.model_copy(
            update={
                "result_id": f"model-result-{self.target_id}",
                "graph_set_id": f"model-graph-{self.target_id}",
                "source_result_ids": (),
                "provenance": provenance,
            }
        )


__all__ = [
    "GOLD_PARSER_TARGET_VERSION",
    "GoldParserTarget",
    "SubmissionComparison",
]
