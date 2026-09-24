import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";
import appSource from "./App.tsx?raw";
import { DEMO_REPORT } from "./data/demo";
import demoSource from "./data/demo.ts?raw";
import stylesSource from "./styles.css?raw";
import typesSource from "./types.ts?raw";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function analysisErrorFetch(detail: Record<string, unknown>) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/v1/health")) {
      return jsonResponse({ status: "ok", version: "test" });
    }
    if (url.includes("/v1/preflight")) {
      return jsonResponse({
        ...DEMO_REPORT.domain_transparency,
        validation_status: "validated",
        requires_acknowledgement: false,
        warning: "",
      });
    }
    if (url.includes("/v7/analyze")) {
      return jsonResponse({ detail }, 409);
    }
    throw new Error(`unexpected request: ${url}`);
  });
}

async function submitImport(): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: "Importa fonti" }));
  fireEvent.click(
    await screen.findByRole("radio", { name: "Flusso storico v7 deprecato" }),
  );
  await screen.findByRole("button", { name: "Avvia analisi v7 deprecata" });
  fireEvent.change(screen.getByPlaceholderText("/percorso/locale/metodi-e-sample-sheet"), {
    target: { value: "/tmp/methods.md" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Avvia analisi v7 deprecata" }));
}

describe("PRD v8 desktop scientific boundary", () => {
  it("renders SCIENTIFIC_REVIEW_REQUIRED as a scientific blocker, not a domain acknowledgement", async () => {
    const fetchMock = analysisErrorFetch({
      code: "SCIENTIFIC_REVIEW_REQUIRED",
      issue_id: "SRR-V8-008",
      message: "Profile predicate closure requires scientific review.",
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await submitImport();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Revisione scientifica richiesta");
    expect(alert).toHaveTextContent("SRR-V8-008");
    expect(alert).not.toHaveTextContent("dominio richiede una conferma");
  });

  it("keeps domain_acknowledgement_required as its own 409 response", async () => {
    const fetchMock = analysisErrorFetch({
      code: "domain_acknowledgement_required",
      message: "Explicit domain acknowledgement is required.",
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await submitImport();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Il dominio richiede una conferma esplicita");
    expect(alert).not.toHaveTextContent("Revisione scientifica richiesta");
  });

  it("exposes HANDOFF_ONLY and keeps determinability separate from design adequacy", () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Apri demo sintetica" }));

    expect(screen.getByText("Demo storica · dati sintetici")).toBeInTheDocument();
    expect(screen.queryByText("Pronto")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    expect(screen.getByTestId("handoff-pin")).toBeVisible();
    expect(screen.getByTestId("handoff-pin")).toHaveTextContent("HANDOFF_ONLY");
    expect(screen.getByTestId("l2-boundary")).toHaveTextContent("La determinabilità non è approvazione del disegno.");
    expect(screen.getByText("Struttura completa")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Alternative e domande" }));
    const determinability = screen.getByTestId("axis-determinability");
    expect(within(determinability).getByText("INSUFFICIENT_INFORMATION")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Methods e handoff" }));
    const panel = screen.getByRole("tabpanel");
    const adequacy = within(panel).getByTestId("axis-design-adequacy");
    expect(within(adequacy).getByText("NOT_ASSESSED")).toBeInTheDocument();
    // Un solo livello ontologico alla volta: l'asse determinabilità non è in questo pannello.
    expect(within(panel).queryByTestId("axis-determinability")).not.toBeInTheDocument();
  });

  it("keeps adequacy unassessed when a user only confirms the structural target", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Apri demo sintetica" }));

    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    fireEvent.click(screen.getByRole("button", { name: "Modifica target" }));
    fireEvent.click(screen.getByRole("radio", { name: "L'unità assegnata al trattamento" }));
    fireEvent.click(screen.getByRole("radio", { name: "n = 1: i 12 sono osservazioni replicate" }));
    fireEvent.click(screen.getByRole("radio", { name: "Consegna vincoli e domande allo statistico, senza suggerire test" }));
    expect(await screen.findByText(/Comprensione registrata per questo blocco/)).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/Perché questo è il target corretto/), {
      target: { value: "Domanda e popolazione sono state confermate dal ricercatore." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Conferma target ed estimand/ }));

    fireEvent.click(screen.getByRole("tab", { name: "Methods e handoff" }));
    const adequacy = screen.getByTestId("axis-design-adequacy");
    expect(within(adequacy).getByText("NOT_ASSESSED")).toBeInTheDocument();
    expect(within(adequacy).getByText(/non autorizza una valutazione di adequacy/)).toBeInTheDocument();
  });

  it("contains no strategy-candidate field or positive ready-state vocabulary in production UI", () => {
    const productionSource = [appSource, typesSource, demoSource, stylesSource].join("\n");
    const strategyCandidateField = ["candidate", "analysis", "strategies"].join("_");
    const positiveReadyState = ["ready", "for", "review"].join("_");

    expect(productionSource).not.toContain(strategyCandidateField);
    expect(productionSource).not.toContain(positiveReadyState);
    expect(productionSource).not.toContain("positive-ready");
    expect(productionSource).not.toContain(".compiler-status.ready { color: #08764d");
  });
});
