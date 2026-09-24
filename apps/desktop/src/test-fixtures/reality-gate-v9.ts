// Consumed projection of compose_default_hold_gate_v9().model_dump(mode="json")
// plus the three properties added by GET /v9/reality-gate. Expectations are
// pinned independently of the TypeScript validator to detect contract drift.
export const gateNames = [
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
];

export function defaultGate() {
  return {
    schema_version: "8.0.0",
    composition_id: "REALITY-GATE-V9-COMPOSITION-007fd8e17a640efd2f4d",
    content_checksum: "007fd8e17a640efd2f4db690617904b1e366135261802c2a6fd1210518aaca8c",
    effective_state: "HOLD",
    authorizes_substantive_training: false,
    predicates_satisfied: false,
    v9_evidence_ledger: {
      schema_version: "8.0.0",
      ledger_id: "REALITY-GATE-V9-LEDGER-32b5f4ce6a316245ee45",
      content_checksum: "32b5f4ce6a316245ee454e9d8980a1df4898d6c35849331d3ab33d3e2766da0a",
      predicate_assessments: gateNames.map((name) => ({
        schema_version: "8.0.0",
        name,
        value: {
          schema_version: "8.0.0",
          knowledge_state: "UNKNOWN",
          value: null as boolean | number | null,
          conflicting_values: [] as (boolean | number)[],
          evidence_ids: [] as string[],
          source_scope_ids: [] as string[],
          rationale: "awaiting registered evidence (PRD v9 section 0.8)" as string | null,
          claim_scope_id: `REALITY-GATE-V9:${name}` as string | null,
          query_scope_id: null as string | null,
        },
        expected_value: name === "blocking_schema_or_theory_gaps" ? 0 : true,
        reviewer_decision_refs: [] as string[],
      })),
      evidence_artifacts: [] as ReturnType<typeof reviewArtifact>[],
    },
  };
}

export function reviewArtifact() {
  return {
    schema_version: "8.0.0",
    artifact_id: `GATE-EVIDENCE-${"a".repeat(20)}`,
    content_checksum: "a".repeat(64),
    kind: "REVIEW_RECORD",
    issuer_role: "SCIENTIFIC_REVIEWER",
    reviewer_ids: ["reviewer-1"],
    payload: { assertion: "reviewed" },
  };
}

// Synthetic shaped ledger variants test display/validation, not checksum
// recomputation or scientific evidence verification (owned by Python).
export function presentFlag(gate: ReturnType<typeof defaultGate>, index: number, value: boolean | number) {
  const artifact = reviewArtifact();
  gate.v9_evidence_ledger.evidence_artifacts = [artifact];
  const flag = gate.v9_evidence_ledger.predicate_assessments[index];
  Object.assign(flag.value, {
    knowledge_state: "PRESENT", value, rationale: null,
    evidence_ids: [artifact.artifact_id],
  });
  flag.reviewer_decision_refs = [artifact.artifact_id];
  return flag;
}

export function gateResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}
