"""Provenance prospettica separata tra piano, esecuzione e gold adjudicato."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from ntruth.prospective.schema import ProspectiveD0Draft
from ntruth.sample_sheet.schema import SampleLifecycleStatus, SampleSheetSpec
from ntruth.schemas.core import FrozenModel
from ntruth.schemas.experiment import ExclusionPhase, TriState

PROSPECTIVE_PLAN_EXECUTION_VERSION: Literal["1.0.0"] = "1.0.0"


class ProspectiveDeviationCategory(StrEnum):
    DESIGN_CHANGE = "design_change"
    PROCEDURE_CHANGE = "procedure_change"
    TIMING_CHANGE = "timing_change"
    EQUIPMENT_CHANGE = "equipment_change"
    ENVIRONMENT_CHANGE = "environment_change"
    OTHER = "other"


class ProspectiveDeviation(FrozenModel):
    deviation_id: str = Field(min_length=1, max_length=200)
    category: ProspectiveDeviationCategory
    description: str = Field(min_length=3, max_length=4000)
    affected_sample_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class ProspectiveSubstitution(FrozenModel):
    substitution_id: str = Field(min_length=1, max_length=200)
    planned_sample_id: str = Field(min_length=1, max_length=500)
    substitute_sample_id: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=2000)
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _different_samples(self) -> Self:
        if self.planned_sample_id == self.substitute_sample_id:
            raise ValueError("una sostituzione richiede due sample_id distinti")
        return self


class ProspectiveExecutionExclusion(FrozenModel):
    exclusion_id: str = Field(min_length=1, max_length=200)
    sample_id: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=2000)
    phase: ExclusionPhase
    prespecified: TriState
    author_role: str = Field(min_length=2, max_length=64)
    evidence_refs: tuple[str, ...] = ()


class ProspectivePoolingEvent(FrozenModel):
    pooling_id: str = Field(min_length=1, max_length=200)
    input_sample_ids: tuple[str, ...] = Field(min_length=2)
    output_sample_id: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=2000)
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _distinct_inputs_and_output(self) -> Self:
        if len(self.input_sample_ids) != len(set(self.input_sample_ids)):
            raise ValueError("input_sample_ids del pooling contiene duplicati")
        if self.output_sample_id in self.input_sample_ids:
            raise ValueError("output_sample_id del pooling non puo essere un input")
        return self


class ProspectiveLostSample(FrozenModel):
    lost_sample_id: str = Field(min_length=1, max_length=200)
    sample_id: str = Field(min_length=1, max_length=500)
    phase: str = Field(min_length=2, max_length=500)
    reason: str = Field(min_length=3, max_length=2000)
    evidence_refs: tuple[str, ...] = ()


class ProspectiveTreatmentChange(FrozenModel):
    treatment_change_id: str = Field(min_length=1, max_length=200)
    sample_id: str = Field(min_length=1, max_length=500)
    factor_column: str = Field(pattern=r"^factor_level_[a-z0-9][a-z0-9_.-]*$")
    planned_level: str = Field(min_length=1, max_length=500)
    executed_level: str = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=3, max_length=2000)
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _different_levels(self) -> Self:
        if self.planned_level.casefold() == self.executed_level.casefold():
            raise ValueError("un cambio di trattamento richiede livelli distinti")
        return self


class ProspectivePlanExecutionRecord(FrozenModel):
    """Artefatto candidato: non diventa gold senza il wrapper adjudicato."""

    contract_version: Literal["1.0.0"] = PROSPECTIVE_PLAN_EXECUTION_VERSION
    record_id: str = Field(min_length=1, max_length=200)
    planned_design: ProspectiveD0Draft
    planned_sample_sheet: SampleSheetSpec
    executed_design: ProspectiveD0Draft
    deviations: tuple[ProspectiveDeviation, ...] = ()
    substitutions: tuple[ProspectiveSubstitution, ...] = ()
    exclusions: tuple[ProspectiveExecutionExclusion, ...] = ()
    pooling: tuple[ProspectivePoolingEvent, ...] = ()
    lost_samples: tuple[ProspectiveLostSample, ...] = ()
    treatment_changes: tuple[ProspectiveTreatmentChange, ...] = ()
    final_sample_sheet: SampleSheetSpec
    recorded_by_role: str = Field(min_length=2, max_length=64)

    @model_validator(mode="after")
    def _plan_execution_are_reconciled(self) -> Self:
        if self.planned_design.experiment_block_id != self.executed_design.experiment_block_id:
            raise ValueError(
                "planned_design ed executed_design devono riferirsi allo stesso blocco"
            )
        if set(self.planned_sample_sheet.factor_columns) != set(
            self.final_sample_sheet.factor_columns
        ):
            raise ValueError("planned e final sample sheet devono usare le stesse colonne factor")

        event_ids = [item.deviation_id for item in self.deviations]
        event_ids.extend(item.substitution_id for item in self.substitutions)
        event_ids.extend(item.exclusion_id for item in self.exclusions)
        event_ids.extend(item.pooling_id for item in self.pooling)
        event_ids.extend(item.lost_sample_id for item in self.lost_samples)
        event_ids.extend(item.treatment_change_id for item in self.treatment_changes)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("gli ID degli eventi piano-esecuzione devono essere univoci")

        planned = {item.sample_id: item for item in self.planned_sample_sheet.rows}
        final = {item.sample_id: item for item in self.final_sample_sheet.rows}
        known = set(planned) | set(final)
        for deviation in self.deviations:
            self._require_known(deviation.affected_sample_ids, known, "deviation")
        for substitution in self.substitutions:
            self._require_known((substitution.planned_sample_id,), set(planned), "substitution")
            self._require_known((substitution.substitute_sample_id,), set(final), "substitution")
        for exclusion in self.exclusions:
            self._require_known((exclusion.sample_id,), set(final), "exclusion")
            final_row = final[exclusion.sample_id]
            if final_row.lifecycle_status is not SampleLifecycleStatus.EXCLUDED:
                raise ValueError("un'esclusione deve restare visibile nel final sample sheet")
            if final_row.exclusion_reason != exclusion.reason:
                raise ValueError("la reason dell'esclusione non coincide con il final sample sheet")
        for lost in self.lost_samples:
            self._require_known((lost.sample_id,), set(planned), "lost_sample")
            if lost.sample_id in final:
                raise ValueError("un lost sample non puo apparire nel final sample sheet")
        for event in self.pooling:
            self._require_known(event.input_sample_ids, set(planned), "pooling input")
            self._require_known((event.output_sample_id,), set(final), "pooling output")

        final_exclusions = {
            sample_id
            for sample_id, row in final.items()
            if row.lifecycle_status is SampleLifecycleStatus.EXCLUDED
        }
        declared_exclusions = {item.sample_id for item in self.exclusions}
        if final_exclusions != declared_exclusions:
            raise ValueError("exclusions non coincide con le righe excluded del final sample sheet")

        explained_removed = {
            *(item.planned_sample_id for item in self.substitutions),
            *(item.sample_id for item in self.lost_samples),
            *(sample_id for item in self.pooling for sample_id in item.input_sample_ids),
        }
        unexplained_removed = set(planned) - set(final) - explained_removed
        if unexplained_removed:
            raise ValueError(
                "campioni pianificati assenti senza sostituzione/loss/pooling: "
                + ", ".join(sorted(unexplained_removed))
            )
        explained_added = {
            *(item.substitute_sample_id for item in self.substitutions),
            *(item.output_sample_id for item in self.pooling),
        }
        unexplained_added = set(final) - set(planned) - explained_added
        if unexplained_added:
            raise ValueError(
                "campioni finali non pianificati senza sostituzione/pooling: "
                + ", ".join(sorted(unexplained_added))
            )

        declared_changes = {
            (item.sample_id, item.factor_column): (item.planned_level, item.executed_level)
            for item in self.treatment_changes
        }
        if len(declared_changes) != len(self.treatment_changes):
            raise ValueError("cambio di trattamento duplicato per sample e factor")
        observed_changes: dict[tuple[str, str], tuple[str, str]] = {}
        for sample_id in set(planned) & set(final):
            for factor in self.planned_sample_sheet.factor_columns:
                before = planned[sample_id].factor_levels[factor]
                after = final[sample_id].factor_levels[factor]
                if before != after:
                    observed_changes[(sample_id, factor)] = (before, after)
        if declared_changes != observed_changes:
            raise ValueError(
                "treatment_changes non coincide con le differenze tra planned e final sample sheet"
            )

        if (
            self.planned_design.model_dump(mode="json")
            != self.executed_design.model_dump(mode="json")
            and not self.deviations
        ):
            raise ValueError("un executed_design diverso richiede almeno una deviation")
        return self

    @staticmethod
    def _require_known(values: tuple[str, ...], known: set[str], label: str) -> None:
        missing = sorted(set(values) - known)
        if missing:
            raise ValueError(f"{label} riferisce sample_id sconosciuti: {missing}")


class ProspectiveGoldRecord(FrozenModel):
    """Gold prospettico soltanto dopo doppia annotazione e adjudication esplicita."""

    gold_id: str = Field(min_length=1, max_length=200)
    plan_execution: ProspectivePlanExecutionRecord
    source_annotation_ids: tuple[str, ...] = Field(min_length=2)
    reviewer_roles: tuple[str, ...] = Field(min_length=2)
    adjudicator_role: str = Field(min_length=2, max_length=64)
    adjudicated_at: datetime
    status: Literal["adjudicated_gold"] = "adjudicated_gold"

    @field_validator("adjudicated_at")
    @classmethod
    def _adjudicated_at_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("adjudicated_at deve includere il fuso orario")
        return value

    @model_validator(mode="after")
    def _double_annotation_is_distinct(self) -> Self:
        if len(self.source_annotation_ids) != len(set(self.source_annotation_ids)):
            raise ValueError("source_annotation_ids deve contenere annotazioni distinte")
        normalized_roles = tuple(role.strip() for role in self.reviewer_roles)
        if any(not role for role in normalized_roles):
            raise ValueError("reviewer_roles non puo contenere ruoli vuoti")
        if len(normalized_roles) != len(set(normalized_roles)):
            raise ValueError("reviewer_roles deve rappresentare almeno due ruoli distinti")
        return self
