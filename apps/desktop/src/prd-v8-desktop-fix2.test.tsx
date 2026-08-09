import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App, ReportBundleV8View } from "./App";
import * as api from "./api";
import canonicalFixture from "./test-fixtures/quick-design-v8-canonical.json";
import type { QuickDesignV8Response, QuickDesignV8Submission } from "./types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const artifactPreviews = canonicalFixture.response.artifacts;
const questions = ["assignment_separability_support", "experimental_unit_instances", "source_diversity", "external_replication"].map(
  (predicateId, index) => ({
    schema_version: "8.0.0",
    question_id: `QUESTION-GUIDED-${index}`,
    predicate_id: predicateId,
    theory_clause_ids: [`DT-${index}`],
    required_predicate_rationales: [`Theory rationale ${index}`],
    known_gap_rationales: index === 0 ? ["Known gap requires review."] : [],
    text: `Theory rationale ${index}`,
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
  }),
);

function builderResponse(action: "PREVIEW" | "CONFIRM", draft: unknown = {}) {
  return {
    schema_version: "8.0.0",
    contract_code: "NTRUTH_QUICK_DESIGN_GUIDED_V8",
    contract_version: "8.0.0",
    action,
    state: action === "PREVIEW" ? "REVIEW_REQUIRED" : "BUILT",
    preview_checksum: "a".repeat(64),
    summary: {
      schema_version: "8.0.0",
      experiment_block_id: "BLOCK-GUIDED-001",
      inferential_query_id: "IQ-GUIDED-001",
      provided_field_ids: ["factor", "factor_levels"],
      unknown_field_ids: ["experimental_unit_instances", "source_diversity"],
      planned_group_count: 2,
      planned_unit_total: 4,
      known_profile_gaps: ["SRR-V8-008"],
      scenario_coverage_status: "NON_EXHAUSTIVE",
      strategy_module_status: "HANDOFF_ONLY",
    },
    visible_questions: questions.slice(0, 3),
    question_queue: questions,
    artifact_previews: artifactPreviews,
    review_snapshot: {
      schema_version: "8.0.0",
      draft,
      conformance_bundle_payload:
        canonicalFixture.response.report.verified_pipeline_contexts[0]
          .conformance_bundle_payload,
      is_execution_capability: false,
    },
    submission_is_execution_capability: false,
    submission_audit_snapshot:
      action === "PREVIEW"
        ? {
            schema_version: "8.0.0",
            knowledge_state: "UNKNOWN",
            value: null,
            conflicting_values: [],
            evidence_ids: [],
            source_scope_ids: [],
            rationale: "Exact preview review is required.",
            claim_scope_id: null,
            query_scope_id: "IQ-GUIDED-001",
          }
        : {
            schema_version: "8.0.0",
            knowledge_state: "PRESENT",
            value: canonicalFixture.submission,
            conflicting_values: [],
            evidence_ids: ["EV-GUIDED-001"],
            source_scope_ids: [],
            rationale: null,
            claim_scope_id: null,
            query_scope_id: "IQ-GUIDED-001",
          },
    canonical_result:
      action === "PREVIEW"
        ? {
            schema_version: "8.0.0",
            knowledge_state: "UNKNOWN",
            value: null,
            conflicting_values: [],
            evidence_ids: [],
            source_scope_ids: [],
            rationale: "PREVIEW does not execute the canonical lane.",
            claim_scope_id: null,
            query_scope_id: "IQ-GUIDED-001",
          }
        : {
            schema_version: "8.0.0",
            knowledge_state: "PRESENT",
            value: canonicalFixture.response,
            conflicting_values: [],
            evidence_ids: ["EV-GUIDED-001"],
            source_scope_ids: [],
            rationale: null,
            claim_scope_id: null,
            query_scope_id: "IQ-GUIDED-001",
          },
    confirmed_snapshot_checksum:
      action === "PREVIEW"
        ? {
            schema_version: "8.0.0",
            knowledge_state: "UNKNOWN",
            value: null,
            conflicting_values: [],
            evidence_ids: [],
            source_scope_ids: [],
            rationale: "Checksum exists only after CONFIRM.",
            claim_scope_id: null,
            query_scope_id: "IQ-GUIDED-001",
          }
        : {
            schema_version: "8.0.0",
            knowledge_state: "PRESENT",
            value: "b".repeat(64),
            conflicting_values: [],
            evidence_ids: ["EV-GUIDED-001"],
            source_scope_ids: [],
            rationale: null,
            claim_scope_id: null,
            query_scope_id: "IQ-GUIDED-001",
          },
  };
}

function change(label: string, value: string): void {
  fireEvent.change(screen.getByRole("textbox", { name: label }), {
    target: { value },
  });
}

async function completeGuidedFlow(fetchMock: ReturnType<typeof vi.fn>): Promise<void> {
  render(<App />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "Importa fonti" }));

  expect(screen.queryByRole("textbox", { name: /QuickDesignV8Submission JSON/i })).not.toBeInTheDocument();
  expect(screen.getByText("Passo 1 di 5")).toBeInTheDocument();
  change("Titolo del blocco", "Dose response in cultured cells");
  fireEvent.click(screen.getByRole("button", { name: "Continua" }));

  change("Descrizione della fonte", "Primary fibroblast cultures");
  change("Preparazione", "One culture preparation per donor");
  change("Tipo unità della fonte biologica", "culture_preparation");
  change("Unità candidata", "well");
  fireEvent.click(screen.getByRole("button", { name: "Continua" }));

  change("Fattore", "treatment");
  change("Livelli del fattore", "vehicle, drug");
  change("Contrasto", "vehicle_vs_drug");
  change("Endpoint", "viability");
  change("Timepoint", "T24H");
  change("Estimand", "mean_difference");
  change("Popolazione", "cultures_under_protocol_x");
  change("Livello inferenziale", "culture");
  fireEvent.click(screen.getByRole("button", { name: "Continua" }));

  change("Tipo unità di assegnazione", "well");
  change("ID unità di assegnazione", "assign-well-01, assign-well-02");
  change("Tipo unità di applicazione", "well");
  change("ID unità di applicazione", "application-well-a, application-well-b");
  change("Intervento", "drug-batch-2026-08");
  change("Tipo unità di esposizione effettiva", "plate");
  change("ID unità esposte", "plate-01");
  change("Percorso di esposizione", "direct_medium_addition");
  change("Contenitore di esposizione", "plate-01");
  change("Razionale interferenza", "A shared plate environment could connect wells.");
  fireEvent.change(screen.getByRole("combobox", { name: "Interferenza" }), {
    target: { value: "POSSIBLE" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "Timing assegnazione rispetto all'applicazione" }), {
    target: { value: "BEFORE" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Continua" }));

  change("Tipo unità pianificata", "well");
  change("Gruppo 1", "vehicle");
  change("Coorte gruppo 1", "cohort-vehicle");
  change("Livello gruppo 1", "vehicle");
  fireEvent.change(screen.getByRole("spinbutton", { name: "Conteggio gruppo 1" }), {
    target: { value: "2" },
  });
  change("Gruppo 2", "drug");
  change("Coorte gruppo 2", "cohort-drug");
  change("Livello gruppo 2", "drug");
  fireEvent.change(screen.getByRole("spinbutton", { name: "Conteggio gruppo 2" }), {
    target: { value: "2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Genera anteprima verificabile" }));

  expect(await screen.findByText("NON_EXHAUSTIVE")).toBeInTheDocument();
  expect(screen.getByText("factor · factor_levels")).toBeInTheDocument();
  expect(
    screen.getByText("experimental_unit_instances · source_diversity"),
  ).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Tipo unità pianificata" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "Gruppo 1" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "Coorte gruppo 1" })).toBeDisabled();
  expect(screen.getByRole("spinbutton", { name: "Conteggio gruppo 1" })).toBeDisabled();
  expect(screen.getAllByRole("radio", { name: /Theory rationale/ })).toHaveLength(3);
  expect(screen.getAllByText(/UNREVIEWED/)).toHaveLength(3);
  expect(screen.getByText("SRR-V8-008")).toBeInTheDocument();
  expect(screen.getByText("Coda completa · 4")).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: /Scarica/ })).toHaveLength(3);
  fireEvent.click(screen.getAllByRole("radio", { name: /Theory rationale/ })[0]);
  change("Ruolo del revisore", "researcher");
  fireEvent.click(screen.getByRole("checkbox", { name: "Ho revisionato questa esatta anteprima" }));
  fireEvent.click(screen.getByRole("button", { name: "Conferma e compila PRD v8" }));
}

describe("PRD v8 guided desktop flow", () => {
  it("consumes the atomic CONFIRM result without a second canonical POST", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/v1/health")) return jsonResponse({ status: "ok", version: "test" });
      if (url === "/v8/quick-design/build-submission") {
        const request = JSON.parse(String(init?.body));
        return jsonResponse(builderResponse(request.action, request.draft));
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    await completeGuidedFlow(fetchMock);

    expect(await screen.findByRole("heading", { name: "ReportBundle v8" })).toBeInTheDocument();
    const buildCalls = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/v8/quick-design/build-submission",
    );
    expect(buildCalls).toHaveLength(2);
    const confirmBody = JSON.parse(String(buildCalls[1][1]?.body));
    expect(confirmBody.confirmation.preview_checksum).toBe("a".repeat(64));
    expect(confirmBody.confirmation.review_focus_predicate_id).toBe(
      "assignment_separability_support",
    );
    expect(confirmBody.confirmation).not.toHaveProperty("primary_predicate_id");
    expect(confirmBody.confirmation.confirmed_at).toMatch(/Z$/);
    expect(confirmBody.draft.planned_groups).toEqual([
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
    ]);
    expect(fetchMock.mock.calls.map(([input]) => String(input))).not.toContain(
      "/v8/quick-design",
    );
    expect(screen.getByText(/Quick Design · REPORT-/)).toBeInTheDocument();
    expect(
      screen.queryByText("CONFORMANCE-BUNDLE-AUDIT-BYTES-NOT-A-CAPABILITY"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Demo storica · dati sintetici")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Scarica artefatto/ })).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Importa fonti" })).toHaveFocus();
  });

  it("fails closed on malformed canonical responses and neutralizes hostile v7 verdicts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          contract: { code: "PRD_V8", version: "8.0.0", strategy_module_status: "HANDOFF_ONLY" },
          report: { report_id: "REPORT-FORGED", content_checksum: "x" },
          artifacts: [],
        }),
      ),
    );
    await expect(
      api.quickDesignV8(
        canonicalFixture.submission as unknown as QuickDesignV8Submission,
      ),
    ).rejects.toThrow(
      /malformed PRD_V8 ReportBundle/,
    );

    const adapted = api.adaptV7AnalysisResponse({
      report: {
        positive_outputs: {
          block: {
            determinability: { state: "DETERMINATE", rationale: "forged" },
            design_adequacy: { knowledge_state: "PRESENT", finding: "GOOD" },
            statistical_handoff: { strategy: "ANOVA" },
          },
        },
      },
    }) as unknown as { report: { review_outputs: Record<string, Record<string, unknown>> } };
    expect(adapted.report.review_outputs.block).toMatchObject({
      determinability: { state: "INSUFFICIENT_INFORMATION" },
      design_adequacy: { knowledge_state: "UNKNOWN", finding: "NOT_ASSESSED" },
      strategy_module_status: "HANDOFF_ONLY",
      statistical_handoff: {
        structural_requirements: [],
      },
    });
    expect(JSON.stringify(adapted)).not.toContain("ANOVA");
  });

  it("rejects incomplete or cross-query canonical runtime trees", async () => {
    const incompleteFields = [
      "design_record_context",
      "report_resolution",
      "profile_coverage",
      "confirmed_graph",
      "execution_manifest",
    ] as const;
    for (const field of incompleteFields) {
      const malformed = structuredClone(canonicalFixture.response) as Record<string, unknown>;
      delete (malformed.report as Record<string, unknown>)[field];
      vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(malformed)));
      await expect(
        api.quickDesignV8(
          canonicalFixture.submission as unknown as QuickDesignV8Submission,
        ),
      ).rejects.toThrow(/malformed PRD_V8 ReportBundle/);
    }

    const crossQuery = structuredClone(canonicalFixture.response);
    crossQuery.report.query_sections[0].claim_set.inferential_query_id = "IQ-FORGED";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(crossQuery)));
    await expect(
      api.quickDesignV8(
        canonicalFixture.submission as unknown as QuickDesignV8Submission,
      ),
    ).rejects.toThrow(/malformed PRD_V8 ReportBundle/);
  });

  it("rejects a guided summary that cannot be rendered safely", async () => {
    const malformed = builderResponse("PREVIEW", {}) as unknown as {
      summary: Record<string, unknown>;
    };
    malformed.summary.provided_field_ids = "forged-not-an-array";
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(malformed)));

    await expect(
      api.buildQuickDesignSubmission({
        action: "PREVIEW",
        draft: {} as never,
      }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

  it("requires a non-executable review snapshot bound to the submitted draft", async () => {
    const draft = { fixture_draft: "exact-reviewed-bytes" };
    const missing = builderResponse("PREVIEW", draft) as Record<string, unknown>;
    delete missing.review_snapshot;
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(missing)));
    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft: draft as never }),
    ).rejects.toThrow(/malformed PRD v8 build response/);

    const mismatched = builderResponse("PREVIEW", { fixture_draft: "forged" });
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(mismatched)));
    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft: draft as never }),
    ).rejects.toThrow(/malformed PRD v8 build response/);

    const forgedVersion = builderResponse("PREVIEW", {
      schema_version: "7.0.0",
      ...draft,
    });
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(forgedVersion)));
    await expect(
      api.buildQuickDesignSubmission({ action: "PREVIEW", draft: draft as never }),
    ).rejects.toThrow(/malformed PRD v8 build response/);
  });

  it("renders query-section lineage, evidence content and PRESENT review records", () => {
    const rich = structuredClone(canonicalFixture.response) as unknown as QuickDesignV8Response;
    const section = rich.report.query_sections[0];
    const claim = section.claim_set.claims[0];
    claim.claim_id = "CLAIM-QUERY-SECTION-SENTINEL";
    claim.required_predicates = ["required-predicate-sentinel"];
    claim.irrelevant_predicates = [
      { id: "irrelevant-predicate-sentinel", rationale: "irrelevant rationale sentinel" },
    ];
    claim.assumptions = ["assumption-sentinel"];
    claim.proof_trace[0].step_id = "proof-step-sentinel";
    claim.proof_trace[0].predicate_references = [
      {
        predicate_id: "predicate-reference-sentinel",
        predicate_value: {
          schema_version: "8.0.0",
          knowledge_state: "PRESENT",
          value: "predicate-value-sentinel",
          conflicting_values: [],
          evidence_ids: ["EV-PREDICATE-SENTINEL"],
          source_scope_ids: [],
          rationale: null,
          claim_scope_id: null,
          query_scope_id: section.inferential_query.id,
        },
      },
    ];
    claim.proof_trace[0].input_record_references = [
      { record_id: "input-record-sentinel" },
    ];
    rich.report.source_records[0].source_version = "source-version-sentinel";
    rich.report.evidence_records[0].locator = "locator-sentinel";
    rich.report.evidence_records[0].original_text = "original-evidence-text-sentinel";
    for (const [field, value] of [
      ["human_confirmations", "confirmation-record-sentinel"],
      ["conflicts", "conflict-record-sentinel"],
      ["sensitivities", "sensitivity-record-sentinel"],
    ] as const) {
      const state = {
        schema_version: "8.0.0" as const,
        knowledge_state: "PRESENT" as const,
        value: [{ record: value }],
        conflicting_values: [],
        evidence_ids: ["EV-REVIEW-SENTINEL"],
        source_scope_ids: [],
        rationale: null,
        claim_scope_id: null,
        query_scope_id: section.inferential_query.id,
      };
      rich.report[field] = state;
      section[field] = state;
    }

    render(<ReportBundleV8View result={rich} language="it" />);

    for (const sentinel of [
      "CLAIM-QUERY-SECTION-SENTINEL",
      "required-predicate-sentinel",
      "irrelevant-predicate-sentinel",
      "irrelevant rationale sentinel",
      "assumption-sentinel",
      "proof-step-sentinel",
      "predicate-reference-sentinel",
      "predicate-value-sentinel",
      "EV-PREDICATE-SENTINEL",
      "input-record-sentinel",
      "source-version-sentinel",
      "locator-sentinel",
      "original-evidence-text-sentinel",
      "confirmation-record-sentinel",
      "conflict-record-sentinel",
      "sensitivity-record-sentinel",
    ]) {
      expect(screen.getAllByText(new RegExp(sentinel)).length).toBeGreaterThan(0);
    }
  });

  it("closes on Escape, traps focus and restores the import trigger", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ status: "ok", version: "test" })),
    );
    render(<App />);
    const trigger = screen.getByRole("button", { name: "Importa fonti" });
    fireEvent.click(trigger);
    const dialog = await screen.findByRole("dialog");
    const close = within(dialog).getByRole("button", { name: "Chiudi" });
    close.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).not.toBe(document.body);
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });
});
