import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App, InferencePanel } from "./App";
import { DEMO_REPORT } from "./data/demo";

vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
vi.stubGlobal("scrollTo", vi.fn());
Element.prototype.scrollIntoView = vi.fn();

describe("N-Truth workspace", () => {
  it("labels synthetic demonstration data and exposes the three synchronized views", () => {
    render(<App />);
    expect(screen.getByText("Dati sintetici dimostrativi")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Blocchi sperimentali" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Target inferenziale" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Grafo del disegno sperimentale" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Evidenza" })).toBeInTheDocument();
  });

  it("keeps export gated until the unvalidated domain is acknowledged", () => {
    render(<App />);
    const exportButton = screen.getByRole("button", { name: "Esporta demo JSON" });
    expect(exportButton).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Ho verificato il limite e confermo" }));
    expect(exportButton).toBeEnabled();
  });

  it("requires a rationale before applying a candidate correction", () => {
    render(<App />);
    const apply = screen.getByRole("button", { name: /Applica e ricalcola/ });
    expect(apply).toBeDisabled();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Nuovo valore di n" }), { target: { value: "8" } });
    fireEvent.change(screen.getByPlaceholderText(/Cita la fonte/), { target: { value: "Il testo corretto è nella riga seguente." } });
    expect(apply).toBeEnabled();
  });

  it("requires and records target plus minimum estimand before compilation", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Modifica target" }));
    const compile = screen.getByRole("button", { name: /Conferma target ed estimand/ });
    expect(compile).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText(/Perché questo è il target corretto/), {
      target: { value: "Domanda e popolazione sono state confermate dal ricercatore." },
    });
    expect(compile).toBeEnabled();
    fireEvent.click(compile);
    expect(screen.getByText(/Target inferenziale confermato nella demo/)).toBeInTheDocument();
  });

  it("shows the non-certifying positive output and typed evidence", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Methods e percorso di revisione" })).toBeInTheDocument();
    expect(screen.getByText(/Tipo AUTHOR_ASSERTION/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/DRIVER · mappatura informativa/));
    expect(screen.getByText(/DRIVER-1 · Experimental unit/)).toBeInTheDocument();
  });

  it("switches the interface language independently from the report payload", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Switch interface to English" }));
    expect(screen.getByRole("heading", { name: "Experiment blocks" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Experimental design graph" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Human correction" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Methods and review path" })).toBeInTheDocument();
  });

  it("edits graph nodes through an append-only candidate correction", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Modifica grafo" }));
    fireEvent.change(screen.getByLabelText("Etichetta"), {
      target: { value: "Coltura aggiunta dall'utente" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aggiungi nodo" }));
    expect(screen.getAllByText("Coltura aggiunta dall'utente").length).toBeGreaterThan(0);
    expect(screen.getByText(/Modifica del grafo registrata come correzione candidata/)).toBeInTheDocument();
  });

  it("indexes candidate exports by block instead of relabeling a stale payload", () => {
    render(<App />);
    const candidateExport = screen.getByRole("button", { name: "Esporta candidate" });
    expect(candidateExport).toBeDisabled();
    fireEvent.change(screen.getByRole("spinbutton", { name: "Nuovo valore di n" }), {
      target: { value: "9" },
    });
    fireEvent.change(screen.getByPlaceholderText(/Cita la fonte/), {
      target: { value: "Correzione specifica del primo blocco." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Applica e ricalcola/ }));
    expect(candidateExport).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: /Trattamento antibiotico/ }));
    expect(screen.getByRole("button", { name: "Esporta candidate" })).toBeDisabled();
  });

  it("offers only scientifically allocatable node types for factor levels", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Modifica grafo" }));
    const allocation = screen.getByLabelText("Allocazione");
    const values = within(allocation)
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);

    expect(values).toContain("Animal");
    expect(values).not.toContain("Factor");
    expect(values).not.toContain("Endpoint");
    expect(values).not.toContain("Estimand");
  });

  it("selects every target explicitly and renders its own estimand", () => {
    const baseBlock = DEMO_REPORT.blocks[0];
    const baseTarget = baseBlock.inference_targets[0];
    const baseEstimand = baseBlock.estimands[0];
    const baseCompilation = DEMO_REPORT.design_compilations[baseBlock.id];
    const secondTarget = {
      ...baseTarget,
      id: "demo-second-target",
      question_text: "Il trattamento modifica il secondo endpoint?",
    };
    const secondEstimand = {
      ...baseEstimand,
      id: "demo-second-estimand",
      effect_measure: "rapporto tra medie del secondo target",
    };
    const block = {
      ...baseBlock,
      inference_targets: [baseTarget, secondTarget],
      estimands: [baseEstimand, secondEstimand],
    };
    const compilation = {
      ...baseCompilation,
      analysis_handoff: {
        ...baseCompilation.analysis_handoff,
        targets: [
          ...baseCompilation.analysis_handoff.targets,
          {
            ...baseCompilation.analysis_handoff.targets[0],
            inference_target_id: secondTarget.id,
            question_text: secondTarget.question_text,
            estimand_ids: [secondEstimand.id],
          },
        ],
        estimands: [
          ...(baseCompilation.analysis_handoff.estimands ?? []),
          {
            estimand_id: secondEstimand.id,
            endpoint_id: secondEstimand.endpoint_id,
            effect_measure: secondEstimand.effect_measure,
            target_population_or_unit: secondEstimand.target_population_or_unit,
            generalization_level: secondEstimand.generalization_level,
            factor_ids: secondEstimand.factor_ids,
            timepoint: secondEstimand.timepoint,
            condition: secondEstimand.condition,
            evidence_ids: secondEstimand.evidence_ids,
          },
        ],
      },
    };

    render(
      <InferencePanel
        id="multi-target"
        active
        block={block}
        compilation={compilation}
        evidence={block.evidence[0]}
        isDemo
        language="it"
        onConfirm={vi.fn()}
      />,
    );
    const selector = screen.getByLabelText("Target da revisionare");
    expect(within(selector).getAllByRole("option")).toHaveLength(2);
    fireEvent.change(selector, { target: { value: secondTarget.id } });
    expect(screen.getAllByText(secondTarget.question_text).length).toBeGreaterThan(0);
    expect(screen.getByText(/rapporto tra medie del secondo target/)).toBeInTheDocument();
  });

  it("shows privacy readiness and blocks every local export while review is required", async () => {
    const domainTransparency = {
      ...DEMO_REPORT.domain_transparency,
      validation_status: "validated" as const,
      requires_acknowledgement: false,
      warning: "",
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.includes("/v1/health")
        ? { status: "ok", version: "test" }
        : url.includes("/v1/preflight")
          ? domainTransparency
          : {
              report: { ...DEMO_REPORT, domain_transparency: domainTransparency },
              ingest_summary: "Analisi fixture completata.",
              artifacts: { ro_crate: "/tmp/ro-crate-metadata.json" },
              domain_transparency: domainTransparency,
              session_id: "session-privacy",
              run_id: "run-privacy",
              revision: 0,
              privacy_audit: {
                document_id: "doc-privacy",
                status: "review_required",
                scanned_fields: 12,
                scanned_asset_ids: ["asset-1"],
                scans_with_findings: [],
                finding_count: 2,
                original_sources_mutated: false,
                detector_version: "1.0.0",
              },
              share_readiness: {
                analysis_allowed: true,
                share_ready: false,
                redistribute_ready: false,
                privacy_status: "review_required",
                governance_status: "not_evaluated",
                privacy_audit_checksum: "a".repeat(64),
                assets: [{ asset_id: "asset-1", sha256: "b".repeat(64) }],
                reasons: ["privacy_findings_require_policy"],
                requires_explicit_distribution_check: true,
              },
            };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Importa fonti" }));
    await screen.findByRole("button", { name: "Avvia analisi" });
    fireEvent.change(screen.getByPlaceholderText("/percorso/locale/metodi-e-sample-sheet"), {
      target: { value: "/tmp/methods.md" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Avvia analisi" }));

    expect(await screen.findByText("Revisione privacy richiesta")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Salva report" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Scarica RO-Crate locale" })).toBeDisabled();
    expect(screen.getByText(/privacy_findings_require_policy/)).toBeInTheDocument();
  });
});
