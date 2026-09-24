import { request } from "./apiTransport";

// Canonical expectations: packages/ntruth/reality_gate/v9.py, PRD v9 §0.8.
const PREDICATE_NAMES = [
  "canonical_schema_registry_frozen",
  "all_normative_examples_schema_valid",
  "factor_role_and_contrast_type_reviewed",
  "assignment_anchored_derivation_theory_reviewed",
  "material_lineage_clauses_reviewed",
  "contrast_support_contract_reviewed",
  "support_profile_policy_reviewed",
  "profile_assumption_set_reviewed",
  "human_second_review_completed",
  "blocking_schema_or_theory_gaps",
  "real_anchor_available",
  "license_and_data_use_scope_verified",
  "train_dev_test_lineage_frozen",
  "reference_stability_report_available",
  "human_only_baseline_executed",
  "human_ai_team_protocol_frozen",
  "real_baseline_executed",
  "synthetic_factory_human_calibrated",
  "critical_error_and_calibration_contract_frozen",
  "end_to_end_metric_contract_frozen",
  "external_challenge_custody_and_lifecycle_ready",
  "ingestion_threat_model_and_adversarial_tests_passed",
  "requirements_traceability_complete_for_release_scope",
] as const;

type PredicateName = (typeof PREDICATE_NAMES)[number];
type PredicateScalar = boolean | number;
type KnowledgeState = "PRESENT" | "ABSENT_EXPLICIT" | "NOT_REPORTED" |
  "UNKNOWN" | "NOT_APPLICABLE" | "CONFLICTING";

export interface RealityGateV9Flag {
  schema_version: "8.0.0";
  name: PredicateName;
  value: {
    schema_version: "8.0.0";
    knowledge_state: KnowledgeState;
    value: PredicateScalar | null;
    conflicting_values: PredicateScalar[];
    evidence_ids: string[];
    source_scope_ids: string[];
    rationale: string | null;
    claim_scope_id: string | null;
    query_scope_id: string | null;
  };
  expected_value: PredicateScalar;
  reviewer_decision_refs: string[];
}

/** Validated UI projection, not a reimplementation of Python's trust boundary. */
export interface RealityGateV9Composition {
  schema_version: "8.0.0";
  composition_id: string;
  content_checksum: string;
  effective_state: "HOLD" | "READY_FOR_SCIENTIFIC_REVIEW";
  authorizes_substantive_training: false;
  predicates_satisfied: boolean;
  v9_evidence_ledger: {
    schema_version: "8.0.0";
    ledger_id: string;
    content_checksum: string;
    predicate_assessments: RealityGateV9Flag[];
    evidence_artifacts: { artifact_id: string; content_checksum: string }[];
  };
}

// UI limits bound work on consumed fields. Do not recursively walk opaque v8
// assessments or evidence payloads: Python owns checksums and scientific review.
const MAX_TEXT = 8_192;
const MAX_REFS = 256;
const MAX_ARTIFACTS = 1_024;
const names = new Set<string>(PREDICATE_NAMES);

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): value is string {
  return typeof value === "string" && value.length <= MAX_TEXT && value.trim().length > 0;
}

function nullableText(value: unknown): boolean {
  return value === null || text(value);
}

function scalar(value: unknown): value is PredicateScalar {
  return typeof value === "boolean" || (typeof value === "number" && Number.isSafeInteger(value));
}

function refs(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= MAX_REFS &&
    value.every(text) && new Set(value).size === value.length;
}

function addressed(value: unknown, idKey: string, prefix: string): value is Record<string, unknown> {
  return record(value) && value.schema_version === "8.0.0" &&
    typeof value.content_checksum === "string" && /^[0-9a-f]{64}$/.test(value.content_checksum) &&
    value[idKey] === `${prefix}${value.content_checksum.slice(0, 20)}`;
}

/** Python strict bool/int equality: neither truthiness nor numeric coercion. */
export function isRealityGateV9FlagSatisfied(flag: RealityGateV9Flag): boolean {
  return flag.value.knowledge_state === "PRESENT" &&
    typeof flag.value.value === typeof flag.expected_value &&
    flag.value.value === flag.expected_value;
}

function isFlag(value: unknown, artifacts: Set<string>): value is RealityGateV9Flag {
  if (!record(value) || value.schema_version !== "8.0.0" ||
    typeof value.name !== "string" || !names.has(value.name) ||
    value.expected_value !== (value.name === "blocking_schema_or_theory_gaps" ? 0 : true) ||
    !refs(value.reviewer_decision_refs) ||
    !value.reviewer_decision_refs.every(id => artifacts.has(id))) return false;

  const knowledge = value.value;
  if (!record(knowledge) || knowledge.schema_version !== "8.0.0" ||
    !refs(knowledge.evidence_ids) || !knowledge.evidence_ids.every(id => artifacts.has(id)) ||
    !refs(knowledge.source_scope_ids) || !nullableText(knowledge.rationale) ||
    !nullableText(knowledge.claim_scope_id) || !nullableText(knowledge.query_scope_id) ||
    !Array.isArray(knowledge.conflicting_values) || knowledge.conflicting_values.length > MAX_REFS ||
    !knowledge.conflicting_values.every(scalar)) return false;

  const state = knowledge.knowledge_state;
  const alternatives = knowledge.conflicting_values;
  if (state === "PRESENT") {
    return scalar(knowledge.value) && alternatives.length === 0 &&
      knowledge.evidence_ids.length > 0 && value.reviewer_decision_refs.length > 0;
  }
  if (knowledge.value !== null) return false;
  if (state === "CONFLICTING") {
    // Python requires at least two distinct alternatives, not all unique.
    // JS Set retains the bool/int distinction (true and 1 are distinct).
    return new Set(alternatives).size >= 2 && knowledge.evidence_ids.length > 0;
  }
  if (alternatives.length !== 0) return false;
  if (state === "ABSENT_EXPLICIT") return knowledge.evidence_ids.length > 0;
  if (state === "NOT_REPORTED") return knowledge.source_scope_ids.length > 0;
  return (state === "UNKNOWN" || state === "NOT_APPLICABLE") &&
    text(knowledge.rationale) && (text(knowledge.claim_scope_id) || text(knowledge.query_scope_id));
}

export function isRealityGateV9Composition(body: unknown): body is RealityGateV9Composition {
  if (!addressed(body, "composition_id", "REALITY-GATE-V9-COMPOSITION-") ||
    (body.effective_state !== "HOLD" && body.effective_state !== "READY_FOR_SCIENTIFIC_REVIEW") ||
    body.authorizes_substantive_training !== false || typeof body.predicates_satisfied !== "boolean") return false;
  const ledger = body.v9_evidence_ledger;
  if (!addressed(ledger, "ledger_id", "REALITY-GATE-V9-LEDGER-") ||
    !Array.isArray(ledger.evidence_artifacts) || ledger.evidence_artifacts.length > MAX_ARTIFACTS ||
    !Array.isArray(ledger.predicate_assessments) || ledger.predicate_assessments.length !== PREDICATE_NAMES.length) return false;
  const artifactIds = new Set<string>();
  for (const artifact of ledger.evidence_artifacts) {
    if (!addressed(artifact, "artifact_id", "GATE-EVIDENCE-") ||
      !text(artifact.artifact_id) || artifactIds.has(artifact.artifact_id)) return false;
    artifactIds.add(artifact.artifact_id);
  }
  const flags = ledger.predicate_assessments;
  if (!flags.every((flag): flag is RealityGateV9Flag => isFlag(flag, artifactIds)) ||
    new Set(flags.map(flag => flag.name)).size !== PREDICATE_NAMES.length) return false;

  const allSatisfied = flags.every(isRealityGateV9FlagSatisfied);
  // Composition satisfaction includes v8. All v9 flags alone cannot imply
  // aggregate satisfaction or readiness. These properties are added by the
  // endpoint; individual `satisfied` properties are NOT serialized by Python.
  return (!body.predicates_satisfied || allSatisfied) &&
    (body.effective_state !== "READY_FOR_SCIENTIFIC_REVIEW" || body.predicates_satisfied);
}

export async function realityGateV9(signal?: AbortSignal): Promise<RealityGateV9Composition> {
  const body: unknown = await request("/v9/reality-gate", { signal });
  if (!isRealityGateV9Composition(body)) {
    throw new Error("malformed PRD v9 reality gate composition");
  }
  return body;
}
