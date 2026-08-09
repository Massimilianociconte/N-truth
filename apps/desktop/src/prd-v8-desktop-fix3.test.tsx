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
  return {
    planned_design: structuredClone(canonicalFixture.response.planned_design),
    report: structuredClone(canonicalFixture.response.report_bundle),
    artifacts: structuredClone(canonicalFixture.response.artifacts),
    contract: {
      code: "PRD_V8",
      version: "8.0.0",
      strategy_module_status: "HANDOFF_ONLY",
    },
  } as unknown as QuickDesignV8Response;
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

function pythonSerializedDraft(draft: GuidedQuickDesignDraft): Record<string, unknown> {
  const textAnswer = (answer: Record<string, unknown>) => ({
    schema_version: "8.0.0",
    status: answer.status,
    value: answer.value ?? null,
    rationale: answer.rationale ?? null,
  });
  const idSetAnswer = (answer: Record<string, unknown>) => ({
    schema_version: "8.0.0",
    status: answer.status,
    values: answer.values ?? [],
    rationale: answer.rationale ?? null,
  });
  const serialized = structuredClone(draft) as unknown as Record<string, unknown>;
  serialized.schema_version = "8.0.0";
  for (const field of [
    "source_description",
    "preparation_description",
    "biological_source_unit_type",
    "candidate_unit_type",
    "assignment_unit_type",
    "application_unit_type",
    "intervention_id",
    "effective_exposure_unit_type",
    "exposure_pathway",
    "exposure_container",
    "planned_unit_type",
  ]) {
    serialized[field] = textAnswer(serialized[field] as Record<string, unknown>);
  }
  for (const field of ["assignment_unit_ids", "application_unit_ids", "exposed_unit_ids"]) {
    serialized[field] = idSetAnswer(serialized[field] as Record<string, unknown>);
  }
  const timing = serialized.assignment_to_application_timing as Record<string, unknown>;
  serialized.assignment_to_application_timing = {
    schema_version: "8.0.0",
    status: timing.status,
    relation: timing.relation ?? null,
    rationale: timing.rationale ?? null,
  };
  serialized.interference = {
    schema_version: "8.0.0",
    ...(serialized.interference as Record<string, unknown>),
  };
  serialized.planned_groups = (
    serialized.planned_groups as Array<Record<string, unknown>>
  ).map((group) => ({
    schema_version: "8.0.0",
    ...group,
    cohort_id: textAnswer(group.cohort_id as Record<string, unknown>),
  }));
  return serialized;
}

async function previewResponse(
  draft: GuidedQuickDesignDraft,
  pythonSerializedSnapshot = false,
): Promise<Record<string, unknown>> {
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
  const response: Record<string, unknown> = {
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
      draft: pythonSerializedSnapshot
        ? pythonSerializedDraft(draft)
        : structuredClone(draft),
      conformance_bundle_payload: structuredClone(
        canonicalFixture.response.report_bundle.verified_pipeline_contexts[0]
          .conformance_bundle_payload,
      ),
      is_execution_capability: false,
    },
    submission_is_execution_capability: false,
    submission_audit_snapshot: unknown("Exact preview review is required."),
    canonical_result: unknown("PREVIEW does not execute the canonical lane."),
    confirmed_snapshot_checksum: unknown("Checksum exists only after CONFIRM."),
  };
  const summary = response.summary as Record<string, unknown>;
  const blockId = await stableId("BLOCK-QD", draft.template_id, draft.block_title);
  summary.experiment_block_id = blockId;
  summary.inferential_query_id = await stableId(
    "IQ-QD",
    blockId,
    draft.factor_id,
    draft.contrast_id,
    draft.endpoint_id,
    draft.timepoint_id,
    draft.estimand,
    draft.population_scope,
    draft.inference_level,
  );
  summary.planned_group_count = draft.planned_groups.length;
  summary.planned_unit_total = draft.planned_groups.reduce(
    (total, group) => total + group.planned_count,
    0,
  );
  const snapshot = response.review_snapshot as Record<string, unknown>;
  const bundle = snapshot.conformance_bundle_payload as Record<string, unknown>;
  summary.known_profile_gaps = structuredClone(
    (bundle.profile_closure as Record<string, unknown>).known_gaps,
  );
  await readdressPreview(response);
  return response;
}

async function confirmedResponse(
  draft: GuidedQuickDesignDraft,
): Promise<Record<string, unknown>> {
  const response = await previewResponse(draft, true);
  const present = (value: unknown) => ({
    schema_version: "8.0.0",
    knowledge_state: "PRESENT",
    value,
    conflicting_values: [],
    evidence_ids: ["EV-GUIDED-001"],
    source_scope_ids: [],
    rationale: null,
    claim_scope_id: null,
    query_scope_id: "IQ-GUIDED-001",
  });
  response.action = "CONFIRM";
  response.state = "BUILT";
  const submission = structuredClone(canonicalFixture.submission);
  const result = structuredClone(canonicalFixture.response);
  response.submission_audit_snapshot = present(submission);
  response.canonical_result = present(result);
  response.confirmed_snapshot_checksum = present("0".repeat(64));
  await readdressConfirmedSnapshot(response);
  return response;
}

async function readdressConfirmedSnapshot(response: Record<string, unknown>): Promise<void> {
  const submission = response.submission_audit_snapshot as Record<string, unknown>;
  const result = response.canonical_result as Record<string, unknown>;
  const confirmed = response.confirmed_snapshot_checksum as Record<string, unknown>;
  confirmed.value = await sha256Hex(
    pythonJson({
      preview_checksum: response.preview_checksum,
      submission_audit_snapshot: submission.value,
      canonical_result: result.value,
    }),
  );
}

function pythonJson(value: unknown): string {
  if (value === null || typeof value === "boolean" || typeof value === "number") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(pythonJson).join(", ")}]`;
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}: ${pythonJson(record[key])}`)
      .join(", ")}}`;
  }
  throw new Error("not JSON serializable");
}

async function readdressPreview(response: Record<string, unknown>): Promise<void> {
  const snapshot = response.review_snapshot as Record<string, unknown>;
  const bundle = snapshot.conformance_bundle_payload as Record<string, unknown>;
  const theory = bundle.theory as Record<string, unknown>;
  const artifacts = response.artifact_previews as Array<Record<string, unknown>>;
  response.preview_checksum = await sha256Hex(
    pythonJson({
      draft: snapshot.draft,
      theory_checksum: theory.declared_checksum,
      questions: response.question_queue,
      artifacts: artifacts.map((artifact) => artifact.content_checksum),
      summary: response.summary,
    }),
  );
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return Array.from(
    new Uint8Array(digest),
    (byte) => byte.toString(16).padStart(2, "0"),
  ).join("");
}

async function stableId(prefix: string, ...parts: string[]): Promise<string> {
  const digest = await sha256Hex(pythonJson(parts));
  return `${prefix}-${digest.slice(0, 12)}`;
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
  it("accepts and normalizes the genuine Python QuickDesignV8Result wire tree", async () => {
    const draft = validDraft();
    const response = await confirmedResponse(draft);
    const fetchMock = vi.fn(async () => jsonResponse(response));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      api.buildQuickDesignSubmission({ action: "CONFIRM", draft }),
    ).resolves.toMatchObject({
      action: "CONFIRM",
      state: "BUILT",
      canonical_result: {
        knowledge_state: "PRESENT",
        value: {
          planned_design: canonicalFixture.response.planned_design,
          report: canonicalFixture.response.report_bundle,
          artifacts: canonicalFixture.response.artifacts,
          contract: {
            code: "PRD_V8",
            version: "8.0.0",
            strategy_module_status: "HANDOFF_ONLY",
            guided_confirmation: true,
          },
        },
      },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["report bundle", (wire: Record<string, unknown>) => {
      const report = wire.report_bundle as Record<string, unknown>;
      const claimSets = report.claim_sets as Array<Record<string, unknown>>;
      claimSets[0].claim_set_id = "CLAIM-SET-FORGED";
    }],
    ["pipeline execution manifest", (wire: Record<string, unknown>) => {
      const pipeline = wire.pipeline_result as Record<string, unknown>;
      const manifest = pipeline.execution_manifest as Record<string, unknown>;
      manifest.manifest_id = "MANIFEST-FORGED-BUT-SHAPED";
    }],
    ["pipeline claim set", (wire: Record<string, unknown>) => {
      const pipeline = wire.pipeline_result as Record<string, unknown>;
      const claimSet = pipeline.claim_set as Record<string, unknown>;
      claimSet.claim_set_id = "CLAIM-SET-FORGED-BUT-SHAPED";
    }],
    ["planned design", (wire: Record<string, unknown>) => {
      const plan = wire.planned_design as Record<string, unknown>;
      plan.plan_id = "PLAN-FORGED";
    }],
    ["artifact", (wire: Record<string, unknown>) => {
      const artifacts = wire.artifacts as Array<Record<string, unknown>>;
      artifacts[0].content = `${String(artifacts[0].content)}forged-row\n`;
    }],
  ])("rejects a hostile Python wire %s mismatch", async (_label, mutate) => {
    const draft = validDraft();
    const response = await confirmedResponse(draft);
    const canonicalResult = response.canonical_result as Record<string, unknown>;
    const wire = canonicalResult.value as Record<string, unknown>;
    mutate(wire);
    await readdressConfirmedSnapshot(response);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(response)));

    await expect(
      api.buildQuickDesignSubmission({ action: "CONFIRM", draft }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

  it("accepts the genuine Python model_dump draft defaults in PREVIEW", async () => {
    const draft = validDraft();
    const response = await previewResponse(draft, true);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(response)));

    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft }),
    ).resolves.toMatchObject({
      action: "PREVIEW",
      state: "REVIEW_REQUIRED",
      preview_checksum: response.preview_checksum,
    });
  });

  it("rejects a non-default value hidden in Python materialized draft fields", async () => {
    const draft = validDraft();
    const response = await previewResponse(draft, true);
    const snapshot = response.review_snapshot as Record<string, unknown>;
    const serializedDraft = snapshot.draft as Record<string, unknown>;
    const source = serializedDraft.source_description as Record<string, unknown>;
    source.rationale = "FORGED-NON-DEFAULT-RATIONALE";
    await readdressPreview(response);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(response)));

    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

  it("rejects a forged PREVIEW checksum and detached summary", async () => {
    const draft = validDraft();
    const response = await previewResponse(draft);
    response.preview_checksum = "0".repeat(64);
    response.summary = {
      ...(response.summary as Record<string, unknown>),
      experiment_block_id: "FORGED-BLOCK",
      inferential_query_id: "FORGED-QUERY",
      planned_group_count: -7,
      planned_unit_total: -9,
      known_profile_gaps: ["FORGED-GAP"],
    };
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(response)));

    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

  it("rejects a readdressed PREVIEW with wrong stable IDs, counts, and profile gaps", async () => {
    const draft = validDraft();
    const response = await previewResponse(draft);
    response.summary = {
      ...(response.summary as Record<string, unknown>),
      experiment_block_id: "BLOCK-QD-READDRESSED",
      inferential_query_id: "IQ-QD-READDRESSED",
      planned_group_count: 7,
      planned_unit_total: 9,
      known_profile_gaps: ["READDRESSED-GAP"],
    };
    await readdressPreview(response);
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(response)));

    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

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
    const response = await previewResponse(draft);
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
      vi.fn(async () => jsonResponse(await previewResponse(invalidDraft))),
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
