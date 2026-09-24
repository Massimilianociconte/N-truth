export type D0Language = "it" | "en";

export type DeterminabilityState =
  | "DETERMINATE"
  | "CONDITIONALLY_DETERMINATE"
  | "MULTIPLE_PLAUSIBLE_GRAPHS"
  | "INSUFFICIENT_INFORMATION"
  | "CONFLICTING_INFORMATION"
  | "INVALID_GRAPH"
  | "OUT_OF_SCOPE";

export type AssignmentState = "TRUE" | "FALSE" | "UNKNOWN";

export type D0FactorKind =
  | "treatment"
  | "genotype"
  | "dose"
  | "time"
  | "diet"
  | "other"
  | "unknown";

export type LifecycleStatus =
  | "planned"
  | "treated"
  | "observed"
  | "excluded"
  | "analysed";

export interface D0DesignDraft {
  question: string;
  inferenceTarget: string;
  factorName: string;
  factorKind: D0FactorKind;
  levelA: string;
  levelB: string;
  endpointName: string;
  endpointId: string;
  measuredOn: "Well";
  allocationLevel: "Well" | "Plate" | "UNKNOWN";
  applicationLevel: "Well" | "Plate" | "UNKNOWN";
  independentlyAssigned: AssignmentState;
  independenceMechanism: string;
  sharedEnvironment: string;
  targetBiologicalUnit: "Well" | "Plate";
  effectMeasure: string;
  estimandTargetPopulation: string;
  generalizationLevel: string;
  estimandCondition: string;
  reviewerRole: string;
}

export interface SampleSheetRow {
  sampleId: string;
  sourceId: string;
  preparationId: string;
  cultureId: string;
  plateId: string;
  wellId: string;
  batchId: string;
  dayId: string;
  operatorId: string;
  incubatorId: string;
  timepoint: string;
  factorLevel: string;
  endpointId: string;
  lifecycleStatus: LifecycleStatus;
  exclusionReason: string;
  fileRef: string;
}

export type Quantifier =
  | "EXACT"
  | "LOWER_BOUND"
  | "UPPER_BOUND"
  | "APPROXIMATE"
  | "RANGE"
  | "UNKNOWN"
  | "NOT_REPORTED";

export interface D0Evidence {
  id: string;
  title: string;
  locator: string;
  text: string;
  evidenceType: "USER_CONFIRMATION" | "SAMPLE_METADATA" | "DERIVED_FACT";
  origin: string;
}

export interface ProofPremise {
  id: string;
  expression: string;
  label: string;
  status: "satisfied" | "unresolved" | "failed";
  evidenceId: string;
}

export interface LifecycleCount {
  phase:
    | "planned_n"
    | "allocated_n"
    | "treated_n"
    | "observed_n"
    | "excluded_n"
    | "analysed_n";
  group: string;
  value: number | null;
  quantifier: Quantifier;
  unitType: "Well" | "Plate" | "UNKNOWN";
  factorId: string;
  contrastId: string;
  endpointId: string;
  timepoint: string;
  evidenceId: string;
  sourceCell: string;
  source: "SampleSheet" | "derived";
}
