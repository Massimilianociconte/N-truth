import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App, ReportBundleV8View } from "./App";
import { DEMO_REPORT } from "./data/demo";
import canonicalFixture from "./test-fixtures/quick-design-v8-canonical.json";
import type { QuickDesignV8Response } from "./types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const V8_RESPONSE = {
  planned_design: canonicalFixture.response.planned_design,
  report: canonicalFixture.response.report_bundle,
  artifacts: canonicalFixture.response.artifacts,
  contract: {
    code: "PRD_V8",
    version: "8.0.0",
    strategy_module_status: "HANDOFF_ONLY",
  },
} as const;

function privacyAudit() {
  return {
    document_id: "doc-v7",
    status: "clean",
    scanned_fields: 1,
    scanned_asset_ids: [],
    scans_with_findings: [],
    finding_count: 0,
    original_sources_mutated: false,
    detector_version: "test",
  };
}

function shareReadiness() {
  return {
    analysis_allowed: true,
    share_ready: false,
    redistribute_ready: false,
    privacy_status: "clean",
    governance_status: "not_evaluated",
    privacy_audit_checksum: "b".repeat(64),
    assets: [],
    reasons: ["legacy_adapter_not_share_ready"],
    requires_explicit_distribution_check: true,
  };
}

describe("PRD v8 desktop canonical consumer and v7 boundary", () => {
  it("renders every canonical ReportBundle axis without a legacy adapter", () => {
    render(
      <ReportBundleV8View
        result={V8_RESPONSE as unknown as QuickDesignV8Response}
        language="it"
      />,
    );

    expect(screen.getByRole("heading", { name: "ReportBundle v8" })).toBeInTheDocument();

    const canonicalReport = V8_RESPONSE.report;
    const claimSet = canonicalReport.claim_sets[0];
    const firstClaim = claimSet.claims[0];
    const secondClaim = claimSet.claims[1];
    const claims = screen.getByRole("region", {
      name: "Derived claims by inferential query",
    });
    const firstClaimArticle = within(claims).getByRole("article", {
      name: `Derived claim ${firstClaim.claim_id} for query ${claimSet.inferential_query_id}`,
    });
    expect(within(firstClaimArticle).getByText(firstClaim.determinability_state)).toBeInTheDocument();
    expect(within(firstClaimArticle).getByText(firstClaim.value.knowledge_state)).toBeInTheDocument();
    expect(within(firstClaimArticle).getByText(firstClaim.support_grade.token)).toBeInTheDocument();
    expect(within(firstClaimArticle).getByText(firstClaim.proof_trace[0].theory_clause_id)).toBeInTheDocument();
    expect(within(firstClaimArticle).getByText(firstClaim.proof_trace[0].rule_id)).toBeInTheDocument();
    expect(within(claims).getByRole("article", {
      name: `Derived claim ${secondClaim.claim_id} for query ${claimSet.inferential_query_id}`,
    })).toBeInTheDocument();

    const sources = screen.getByRole("region", { name: "Sources and design context" });
    expect(sources).toHaveTextContent(canonicalReport.source_records[0].source_id);
    expect(sources).toHaveTextContent(canonicalReport.source_records[0].source_context);
    expect(sources).toHaveTextContent(canonicalReport.design_record_context.mode);
    expect(sources).toHaveTextContent(
      canonicalReport.design_record_context.planned_design_record.knowledge_state,
    );
    const resolution = screen.getByRole("region", { name: "Report resolution" });
    expect(resolution).toHaveTextContent(
      canonicalReport.report_resolution.resolution.knowledge_state,
    );
    expect(resolution).toHaveTextContent(
      String(canonicalReport.report_resolution.resolution.value),
    );

    const adequacy = screen.getByRole("region", { name: "Design adequacy evaluations" });
    const evaluation = canonicalReport.design_adequacy_evaluations[0];
    const adequacyArticle = within(adequacy).getByRole("article", {
      name: `Design adequacy ${evaluation.evaluation_id} for query ${evaluation.inferential_query_id}`,
    });
    expect(adequacyArticle).toHaveTextContent(evaluation.outcome.knowledge_state);
    expect(firstClaimArticle).not.toContainElement(adequacyArticle);

    const counts = screen.getByRole("region", { name: "Canonical counts" });
    expect(counts).toHaveTextContent("planned_unit_count");
    expect(counts).toHaveTextContent("experimental_unit_count");
    expect(counts).toHaveTextContent("biological_source_count");
    const coverage = screen.getByRole("region", { name: "Scenario and profile coverage" });
    expect(coverage).toHaveTextContent("NON_EXHAUSTIVE");
    expect(coverage).toHaveTextContent(canonicalReport.profile_coverage.profile_id);
    expect(coverage).toHaveTextContent("SRR-V8-008");
    const reviewInputs = screen.getByRole("region", {
      name: "Sensitivities and review questions",
    });
    expect(reviewInputs).toHaveTextContent(canonicalReport.sensitivities.knowledge_state);
    expect(reviewInputs).toHaveTextContent(canonicalReport.questions[0].text);
    const handoff = screen.getByRole("region", { name: "Statistical handoff" });
    expect(handoff).toHaveTextContent("HANDOFF_ONLY");
    const structural = canonicalReport.statistical_handoff.items.find(
      (item) => item.category === "STRUCTURAL_CONSTRAINT",
    );
    const unresolved = canonicalReport.statistical_handoff.items.find(
      (item) => item.category === "UNRESOLVED_QUESTION",
    );
    expect(handoff).toHaveTextContent(String(structural?.category));
    expect(handoff).toHaveTextContent(String(structural?.evidence_refs[0]));
    expect(handoff).toHaveTextContent(String(unresolved?.category));
    expect(handoff).toHaveTextContent(String(unresolved?.question_ids[0]));
    const limits = screen.getByRole("region", { name: "Inference limits" });
    expect(limits).toHaveTextContent(canonicalReport.inference_limits[0]);
  });

  it("uses the raw-path flow only after explicit opt-in to deprecated /v7/analyze", async () => {
    const blockId = DEMO_REPORT.blocks[0].id;
    const legacyOutput = {
      ...DEMO_REPORT.review_outputs?.[blockId],
      path_status: "ready_for_review",
      methods_statement: {
        ...DEMO_REPORT.review_outputs?.[blockId].methods_statement,
        status: "ready_for_review",
      },
      candidate_analysis_strategies: ["ANOVA must never reach the panel"],
    };
    const { review_outputs: _reviewOutputs, ...legacyReport } = DEMO_REPORT;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/v1/health")) return jsonResponse({ status: "ok", version: "test" });
      if (url.includes("/v1/preflight")) {
        return jsonResponse({
          ...DEMO_REPORT.domain_transparency,
          validation_status: "validated",
          requires_acknowledgement: false,
          warning: "",
        });
      }
      if (url === "/v7/analyze") {
        return jsonResponse({
          report: { ...legacyReport, positive_outputs: { [blockId]: legacyOutput } },
          ingest_summary: "Historical v7 adapter completed.",
          artifacts: {},
          domain_transparency: DEMO_REPORT.domain_transparency,
          privacy_audit: privacyAudit(),
          share_readiness: shareReadiness(),
          contract: { code: "DEPRECATED_V7_ADAPTER", version: "v7" },
        });
      }
      throw new Error(`unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Importa fonti" }));
    fireEvent.click(screen.getByRole("radio", { name: "Flusso storico v7 deprecato" }));
    expect(screen.getByText(/Compatibilità storica v7.*deprecata/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "File o cartella sorgente" }), {
      target: { value: "/tmp/methods.md" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Avvia analisi v7 deprecata" }));

    expect(await screen.findByText("Historical v7 adapter completed.")).toBeInTheDocument();
    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls).toContain("/v7/analyze");
    expect(urls).not.toContain("/v1/analyze");
    expect(screen.getByRole("heading", { name: "Methods e percorso di revisione" })).toBeInTheDocument();
    expect(screen.getByText("Revisione richiesta")).toBeInTheDocument();
    expect(screen.queryByText(/ANOVA must never reach/)).not.toBeInTheDocument();
  });

  it("neutralizes legacy positive outputs recursively at the API boundary", async () => {
    const api = await import("./api");
    expect(api).toHaveProperty("adaptV7AnalysisResponse");
    const adapt = (api as unknown as {
      adaptV7AnalysisResponse: (value: Record<string, unknown>) => Record<string, unknown>;
    }).adaptV7AnalysisResponse;
    const adapted = adapt({
      report: {
        positive_outputs: {
          block: {
            block_id: "block",
            path_status: "ready_for_review",
            methods_statement: { status: "ready_for_review" },
            candidate_analysis_strategies: ["forbidden"],
            nested: { candidate_analysis_strategies: ["also forbidden"] },
          },
        },
      },
    });
    const serialized = JSON.stringify(adapted);

    expect(serialized).not.toContain("positive_outputs");
    expect(serialized).not.toContain("candidate_analysis_strategies");
    expect(serialized).not.toContain("ready_for_review");
    expect(serialized).toContain("review_outputs");
    expect(serialized).toContain("review_required");
  });
});
