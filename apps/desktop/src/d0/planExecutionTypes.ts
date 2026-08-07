/** Tipi piano vs esecuzione prospettici allineati a ProspectivePlanExecutionRecord. */

export type PlanExecutionDeviationCategory =
  | "design_change"
  | "procedure_change"
  | "timing_change"
  | "equipment_change"
  | "environment_change"
  | "other";

export type PlanExecutionExclusionPhase =
  | "pre_allocation"
  | "post_allocation"
  | "post_treatment"
  | "post_measurement"
  | "post_outcome"
  | "unknown";

export type PlanExecutionTriState = "TRUE" | "FALSE" | "UNKNOWN";

export interface PlanExecutionDesignSnapshot {
  experimentBlockId: string;
  title: string;
  question: string;
  inferenceTarget: string;
  factorName: string;
  levelA: string;
  levelB: string;
  endpointId: string;
  endpointName: string;
  allocationLevel: string;
  independentlyAssigned: string;
  independenceMechanism: string | null;
  reviewerRole: string;
}

export interface PlanExecutionDeviation {
  deviationId: string;
  category: PlanExecutionDeviationCategory;
  description: string;
  affectedSampleIds: string[];
}

export interface PlanExecutionSubstitution {
  substitutionId: string;
  plannedSampleId: string;
  substituteSampleId: string;
  reason: string;
}

export interface PlanExecutionExclusion {
  exclusionId: string;
  sampleId: string;
  reason: string;
  phase: PlanExecutionExclusionPhase;
  prespecified: PlanExecutionTriState;
  authorRole: string;
}

export interface PlanExecutionPooling {
  poolingId: string;
  inputSampleIds: string[];
  outputSampleId: string;
  reason: string;
}

export interface PlanExecutionLostSample {
  lostSampleId: string;
  sampleId: string;
  phase: string;
  reason: string;
}

export interface PlanExecutionTreatmentChange {
  treatmentChangeId: string;
  sampleId: string;
  factorColumn: string;
  plannedLevel: string;
  executedLevel: string;
  reason: string;
}

/** Body POST /v1/prospective/plan-execution (server-side ProspectivePlanExecutionRecord). */
export interface PlanExecutionSubmitPayload {
  project_id: string;
  project_dir: string;
  actor_role?: string;
  record: {
    contract_version: "1.0.0";
    record_id: string;
    planned_design: Record<string, unknown>;
    planned_sample_sheet: Record<string, unknown>;
    executed_design: Record<string, unknown>;
    deviations: Array<Record<string, unknown>>;
    substitutions: Array<Record<string, unknown>>;
    exclusions: Array<Record<string, unknown>>;
    pooling: Array<Record<string, unknown>>;
    lost_samples: Array<Record<string, unknown>>;
    treatment_changes: Array<Record<string, unknown>>;
    final_sample_sheet: Record<string, unknown>;
    recorded_by_role: string;
  };
}

export interface PlanExecutionSubmitResponse {
  record_id: string;
  project_id: string;
  status: string;
  content_checksum: string;
  payload: Record<string, unknown>;
  actor_role: string | null;
  parent_candidate_id: string | null;
  created_at: string;
}

export interface PlanExecutionGetResponse {
  record_id: string;
  project_id: string;
  status: string;
  content_checksum: string;
  payload: Record<string, unknown>;
  actor_role: string | null;
  parent_candidate_id: string | null;
  created_at: string;
}
