/** Routing vero: una voce = una schermata viewport-constrained. */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App, BlockReviewTabs, EMPTY_GATE } from "./App";
import { DEMO_REPORT } from "./data/demo";

vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
vi.stubGlobal("scrollTo", vi.fn());
Element.prototype.scrollIntoView = vi.fn();

function enterSyntheticDemo(): void {
  fireEvent.click(screen.getByRole("button", { name: "Apri demo sintetica" }));
}

describe("view routing", () => {
  beforeEach(() => window.localStorage.clear());
  it("renders a single screen per voice with aria-current on it", () => {
    render(<App />);
    enterSyntheticDemo();
    const voices: Array<[string, string]> = [
      ["Progetto", "Progetto"],
      ["Esperimenti", "Blocchi sperimentali"],
      ["Elicitazione", "Questioni rilevate"],
      ["Grafo", "Grafo del disegno sperimentale"],
      ["Documenti", "Evidenza"],
      ["Correzioni", "Correzione umana"],
      ["Esporta", "Esporta"],
    ];
    for (const [voice, heading] of voices) {
      fireEvent.click(screen.getByRole("button", { name: voice }));
      expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: voice })).toHaveAttribute("aria-current", "page");
    }
    // Una sola voce attiva alla volta.
    const current = screen
      .getAllByRole("button")
      .filter((button) => button.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
  });

  it("moves focus to each view heading without throwing", async () => {
    render(<App />);
    enterSyntheticDemo();
    const targets: Array<[string, string]> = [
      ["Progetto", "project-heading"],
      ["Esperimenti", "blocks-heading"],
      ["Elicitazione", "issues-heading"],
      ["Grafo", "graph-heading"],
      ["Documenti", "evidence-heading"],
      ["Correzioni", "correction-heading"],
      ["Esporta", "export-heading"],
    ];
    for (const [voice, headingId] of targets) {
      fireEvent.click(screen.getByRole("button", { name: voice }));
      await waitFor(() => expect(document.activeElement?.id).toBe(headingId));
    }
  });

  it("announces views via native headings, with live regions only for toasts", () => {
    render(<App />);
    enterSyntheticDemo();
    for (const voice of ["Progetto", "Esperimenti", "Elicitazione", "Grafo", "Documenti", "Correzioni", "Esporta"]) {
      fireEvent.click(screen.getByRole("button", { name: voice }));
    }
    const live = document.querySelectorAll('[aria-live="assertive"], [role="alert"]');
    expect(live).toHaveLength(0);
  });

  it("restores a single checkpointed view without mixing screens", () => {
    window.localStorage.setItem(
      "ntruth.checkpoint.v1",
      JSON.stringify({
        version: 1,
        tab_id: "tab-test",
        saved_at: new Date().toISOString(),
        status: "closed",
        surface: "workspace",
        is_demo: true,
        report: DEMO_REPORT,
        ui: {
          active_view: "graph",
          selected_block: DEMO_REPORT.blocks[0].id,
          selected_alert: DEMO_REPORT.blocks[0].alerts[0]?.id,
          collapsed: {},
          domain_acknowledged: false,
        },
      }),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: "Grafo del disegno sperimentale" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Blocchi sperimentali" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Grafo" })).toHaveAttribute("aria-current", "page");
    window.localStorage.clear();
  });

  it("keeps L2 tabs isolated inside the experiments screen", () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    expect(screen.getByRole("tablist", { name: "Sezioni del blocco in revisione" })).toBeInTheDocument();
    expect(within(screen.getByRole("tabpanel")).queryByTestId("axis-design-adequacy")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Methods e handoff" }));
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByTestId("axis-design-adequacy")).toBeInTheDocument();
    expect(within(panel).queryByTestId("axis-determinability")).not.toBeInTheDocument();
  });

  it("never renders color-only states or ready-state vocabulary", () => {
    render(<App />);
    enterSyntheticDemo();
    for (const voice of ["Progetto", "Esperimenti", "Elicitazione", "Esporta"]) {
      fireEvent.click(screen.getByRole("button", { name: voice }));
    }
    expect(screen.queryByText("Pronto")).not.toBeInTheDocument();
    // I badge nav portano testo, non pallini.
    expect(screen.getByText("3 blocchi")).toBeInTheDocument();
  });

  it("keeps the D0 wizard as its own pre-project screen", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Progettazione D0" }));
    expect(screen.getByRole("heading", { name: "Progettazione prospettica D0" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Chiarisci il disegno/ })).not.toBeInTheDocument();
  });

  it("preserves unsaved drafts when switching sections back and forth", () => {    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    fireEvent.click(screen.getByRole("button", { name: "Modifica target" }));
    fireEvent.change(screen.getByPlaceholderText(/Perché questo è il target corretto/), {
      target: { value: "bozza che deve sopravvivere allo switch" },
    });
    fireEvent.click(screen.getByRole("radio", { name: "L'unità assegnata al trattamento" }));
    expect(screen.getByText(/Corretto ·/)).toBeInTheDocument();
    // Switch altrove e ritorno: niente reset.
    fireEvent.click(screen.getByRole("button", { name: "Grafo" }));
    fireEvent.click(screen.getByRole("button", { name: "Documenti" }));
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    expect(screen.getByPlaceholderText(/Perché questo è il target corretto/)).toHaveValue(
      "bozza che deve sopravvivere allo switch",
    );
    expect(screen.getByText(/Corretto ·/)).toBeInTheDocument();
    // Bozza correzione: stesso contratto.
    fireEvent.click(screen.getByRole("button", { name: "Correzioni" }));
    fireEvent.change(screen.getByPlaceholderText(/Cita la fonte/), {
      target: { value: "bozza correzione persistente" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Esporta" }));
    fireEvent.click(screen.getByRole("button", { name: "Correzioni" }));
    expect(screen.getByPlaceholderText(/Cita la fonte/)).toHaveValue("bozza correzione persistente");
  });

  it("mounts inactive screens hidden with unique ids, preserving their state", () => {
    render(<App />);
    enterSyntheticDemo();
    // Nessun id duplicato in tutto il documento (keep-alive sicuro per focus e aria).
    const ids = Array.from(document.querySelectorAll("[id]")).map((el) => el.id);
    expect(new Set(ids).size).toBe(ids.length);
    // Due istanze dell'heading blocchi (overview + master) con id diversi;
    // attiva (progetto) visibile, l'altra nascosta all'albero di accessibilità.
    const allBlocks = screen.getAllByRole("heading", { name: "Blocchi sperimentali", hidden: true });
    expect(allBlocks).toHaveLength(2);
    expect(allBlocks.filter((heading) => {
      try {
        expect(heading).toBeVisible();
        return true;
      } catch {
        return false;
      }
    })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    const activeBlocks = screen.getByRole("heading", { name: "Blocchi sperimentali" });
    expect(activeBlocks).toBeVisible();
    expect(activeBlocks).toHaveAttribute("id", "blocks-heading");
  });
});

describe("scroll containment", () => {
  it("declares one scroll region per screen without redundant tabindex", () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    // Le regioni contengono controlli reali: nessun tabindex ridondante.
    for (const selector of [".block-list", ".questions-body", ".evidence-body", ".correction-body", ".export-body", ".graph-scroll"]) {
      for (const region of Array.from(document.querySelectorAll(selector))) {
        expect(region).not.toHaveAttribute("tabindex");
      }
    }
    expect(document.querySelectorAll("td[tabindex], th[tabindex]")).toHaveLength(0);
  });

  it("labels data tables and the graph canvas accessibly", () => {
    const block = DEMO_REPORT.blocks[0];
    const base = DEMO_REPORT.review_outputs?.[block.id];
    render(
      <BlockReviewTabs
        block={block}
        output={base && {
          ...base,
          n_table: [{
            assessment_id: "a1",
            scope: "test scope",
            biological_unit: "Animal",
            experimental_unit: "Animal",
            observational_unit: null,
            analytical_unit: null,
            n_declared: 6,
            n_observational: 6,
            n_independent: 1,
            n_allocated: 6,
            n_analyzed: 6,
            inferability: "bassa",
            conditional_scenarios: [],
            evidence_ids: [],
          }],
        }}
        compilation={DEMO_REPORT.design_compilations[block.id]}
        isDemo
        language="it"
        onConfirm={() => undefined}
        gate={EMPTY_GATE}
        onGatePass={() => undefined}
        onGateSkip={() => undefined}
        tab="counts"
        onTabChange={() => undefined}
        active
        onOpenQuestions={() => undefined}
      />,
    );
    const table = screen.getByRole("table", { name: "Conteggi canonici per ambito" });
    for (const header of within(table).getAllByRole("columnheader")) {
      expect(header).toHaveAttribute("scope", "col");
    }
  });

  it("keeps the graph canvas group labelled", () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Grafo" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Abilita canvas esteso sperimentale" }));
    expect(screen.getByRole("group", { name: /Grafo con \d+ nodi/ })).toBeInTheDocument();
  });
});
