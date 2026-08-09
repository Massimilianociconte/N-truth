import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportBundleV8View } from "./App";
import * as api from "./api";
import canonicalFixture from "./test-fixtures/quick-design-v8-canonical.json";
import type {
  GuidedQuickDesignDraft,
  QuickDesignV8Response,
  QuickDesignV8Submission,
} from "./types";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function canonicalResponse(): QuickDesignV8Response {
  return structuredClone(
    canonicalFixture.response,
  ) as unknown as QuickDesignV8Response;
}

function validDraft(): GuidedQuickDesignDraft {
  return {
    template_id: "simple_cell_culture",
    block_title: "Reviewed culture experiment",
    source_description: { status: "PROVIDED", value: "Primary cultures" },
    preparation_description: { status: "PROVIDED", value: "One preparation" },
    biological_source_unit_type: { status: "PROVIDED", value: "culture" },
    candidate_unit_type: { status: "PROVIDED", value: "well" },
    factor_id: "treatment",
    factor_levels: ["vehicle", "drug"],
    contrast_id: "vehicle_vs_drug",
    endpoint_id: "viability",
    timepoint_id: "T24H",
    estimand: "mean_difference",
    population_scope: "cultures_under_protocol_x",
    inference_level: "culture",
    assignment_unit_type: { status: "PROVIDED", value: "well" },
    assignment_unit_ids: { status: "PROVIDED", values: ["well-1", "well-2"] },
    application_unit_type: { status: "PROVIDED", value: "well" },
    application_unit_ids: { status: "PROVIDED", values: ["well-1", "well-2"] },
    intervention_id: { status: "PROVIDED", value: "drug" },
    effective_exposure_unit_type: { status: "PROVIDED", value: "plate" },
    exposed_unit_ids: { status: "PROVIDED", values: ["well-1", "well-2"] },
    exposure_pathway: { status: "PROVIDED", value: "shared medium" },
    exposure_container: { status: "PROVIDED", value: "plate-1" },
    interference: { status: "POSSIBLE", rationale: "A shared medium may connect wells." },
    assignment_to_application_timing: { status: "PROVIDED", relation: "BEFORE" },
    planned_unit_type: { status: "PROVIDED", value: "well" },
    planned_groups: [
      {
        group_id: "vehicle",
        cohort_id: { status: "PROVIDED", value: "cohort-vehicle" },
        factor_level: "vehicle",
        planned_count: 2,
      },
      {
        group_id: "drug",
        cohort_id: { status: "PROVIDED", value: "cohort-drug" },
        factor_level: "drug",
        planned_count: 2,
      },
    ],
  };
}

const guidedQuestion = {
  schema_version: "8.0.0",
  question_id: "QUESTION-GUIDED-0",
  predicate_id: "assignment_separability_support",
  theory_clause_ids: ["DT-A-ASSIGNMENT-UNIT"],
  required_predicate_rationales: ["Assignment separability needs explicit support."],
  known_gap_rationales: ["Known gap requires scientific review."],
  text: "Can assignment separability be supported?",
  priority_state: "UNREVIEWED",
  priority_review: {
    schema_version: "8.0.0",
    issue_id: "SRR-V8-025",
    status: "SCIENTIFIC_REVIEW_REQUIRED",
    rationale: "Question priority has not received scientific review.",
  },
  evidence_required: {
    schema_version: "8.0.0",
    knowledge_state: "UNKNOWN",
    value: null,
    conflicting_values: [],
    evidence_ids: [],
    source_scope_ids: [],
    rationale: "Evidence request contract is unknown.",
    claim_scope_id: null,
    query_scope_id: "IQ-GUIDED-001",
  },
} as const;

function previewResponse(draft: GuidedQuickDesignDraft): Record<string, unknown> {
  const unknown = (rationale: string) => ({
    schema_version: "8.0.0",
    knowledge_state: "UNKNOWN",
    value: null,
    conflicting_values: [],
    evidence_ids: [],
    source_scope_ids: [],
    rationale,
    claim_scope_id: null,
    query_scope_id: "IQ-GUIDED-001",
  });
  return {
    schema_version: "8.0.0",
    contract_code: "NTRUTH_QUICK_DESIGN_GUIDED_V8",
    contract_version: "8.0.0",
    action: "PREVIEW",
    state: "REVIEW_REQUIRED",
    preview_checksum: "a".repeat(64),
    summary: {
      schema_version: "8.0.0",
      experiment_block_id: "BLOCK-GUIDED-001",
      inferential_query_id: "IQ-GUIDED-001",
      provided_field_ids: ["factor", "factor_levels"],
      unknown_field_ids: ["experimental_unit_instances"],
      planned_group_count: 2,
      planned_unit_total: 4,
      known_profile_gaps: ["SRR-V8-008"],
      scenario_coverage_status: "NON_EXHAUSTIVE",
      strategy_module_status: "HANDOFF_ONLY",
    },
    visible_questions: [structuredClone(guidedQuestion)],
    question_queue: [structuredClone(guidedQuestion)],
    artifact_previews: structuredClone(canonicalFixture.response.artifacts),
    review_snapshot: {
      schema_version: "8.0.0",
      draft: structuredClone(draft),
      conformance_bundle_payload: structuredClone(
        canonicalFixture.response.report.verified_pipeline_contexts[0]
          .conformance_bundle_payload,
      ),
      is_execution_capability: false,
    },
    submission_is_execution_capability: false,
    submission_audit_snapshot: unknown("Exact preview review is required."),
    canonical_result: unknown("PREVIEW does not execute the canonical lane."),
    confirmed_snapshot_checksum: unknown("Checksum exists only after CONFIRM."),
  };
}

async function expectCanonicalRejection(
  mutate: (response: QuickDesignV8Response) => void,
): Promise<void> {
  const response = canonicalResponse();
  mutate(response);
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(response)));
  await expect(
    api.quickDesignV8(
      canonicalFixture.submission as unknown as QuickDesignV8Submission,
    ),
  ).rejects.toThrow(/malformed PRD_V8 ReportBundle/);
}

describe("PRD v8 Desktop strict runtime boundaries", () => {
  it.each([
    ["report schema_version", (response: QuickDesignV8Response) => {
      delete (response.report as unknown as Record<string, unknown>).schema_version;
    }],
    ["verified pipeline contexts", (response: QuickDesignV8Response) => {
      delete (response.report as unknown as Record<string, unknown>).verified_pipeline_contexts;
    }],
    ["prospective input ledgers", (response: QuickDesignV8Response) => {
      delete (response.report as unknown as Record<string, unknown>).prospective_input_ledgers;
    }],
    ["evidence type", (response: QuickDesignV8Response) => {
      delete (response.report.evidence_records[0] as unknown as Record<string, unknown>)
        .evidence_type;
    }],
    ["PRESENT evidence binding", (response: QuickDesignV8Response) => {
      delete (
        response.report.report_resolution.resolution as unknown as Record<string, unknown>
      ).evidence_ids;
    }],
    ["artifact content checksum", (response: QuickDesignV8Response) => {
      response.artifacts[0].content += "forged-row\n";
    }],
  ])("rejects a canonical response missing or violating %s", async (_name, mutate) => {
    await expectCanonicalRejection(mutate);
  });

  it.each([
    ["invalid conformance bundle", (response: Record<string, unknown>) => {
      const snapshot = response.review_snapshot as Record<string, unknown>;
      snapshot.conformance_bundle_payload = { garbage: true };
    }],
    ["empty visible question prefix", (response: Record<string, unknown>) => {
      response.visible_questions = [];
    }],
    ["structurally divergent visible question", (response: Record<string, unknown>) => {
      const visible = response.visible_questions as Array<Record<string, unknown>>;
      visible[0].text = "Same ID, forged question meaning";
    }],
  ])("rejects PREVIEW with %s", async (_name, mutate) => {
    const draft = validDraft();
    const response = previewResponse(draft);
    mutate(response);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(response)));
    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

  it("rejects a structurally invalid draft even when the snapshot mirrors it", async () => {
    const invalidDraft = {
      ...validDraft(),
      assignment_unit_ids: { status: "PROVIDED", values: [] },
    } as GuidedQuickDesignDraft;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(previewResponse(invalidDraft))),
    );
    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft: invalidDraft }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

  it("neutralizes recursively normalized v7 verdict and strategy aliases", () => {
    const aliases = {
      design_verdict: "HOSTILE-DESIGN-VERDICT",
      "Design Verdict": "HOSTILE-DESIGN-SPACED",
      "design-verdict": "HOSTILE-DESIGN-DASHED",
      analysis_strategy: "HOSTILE-ANALYSIS-STRATEGY",
      analysisStrategies: "HOSTILE-ANALYSIS-PLURAL",
      "Analysis Strategy": "HOSTILE-ANALYSIS-SPACED",
      model_strategy: "HOSTILE-MODEL-STRATEGY",
      adequacyVerdict: "HOSTILE-ADEQUACY-VERDICT",
    };
    const adapted = api.adaptV7AnalysisResponse({
      report: {
        positive_outputs: {
          block: {
            nested: [{ aliases }, { deeper: aliases }],
          },
        },
      },
    });
    const serialized = JSON.stringify(adapted);
    for (const hostile of Object.values(aliases)) {
      expect(serialized).not.toContain(hostile);
    }
  });

  it("renders mandatory pipeline, ledger, design-state and theory lineage", () => {
    const response = canonicalResponse();
    const context = response.report.verified_pipeline_contexts[0];
    const ledger = response.report.prospective_input_ledgers.value?.[0];
    const design = response.report.design_record_context;
    render(<ReportBundleV8View result={response} language="it" />);

    for (const lineageValue of [
      context.context_id,
      context.content_checksum,
      context.conformance_bundle_checksum,
      ledger?.ledger_id,
      ledger?.content_checksum,
      design.executed_design_record.rationale,
      design.reconciliation_record.rationale,
      response.report.execution_manifest.theory_checksum,
      response.report.execution_manifest.rulebook_checksum,
    ]) {
      expect(lineageValue).toBeTruthy();
      expect(screen.getAllByText(new RegExp(String(lineageValue))).length).toBeGreaterThan(0);
    }
  });
});
