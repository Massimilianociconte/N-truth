/** Ripristino del progetto dal checkpoint locale al boot dell'app. */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { DEMO_REPORT } from "./data/demo";

vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
vi.stubGlobal("scrollTo", vi.fn());
Element.prototype.scrollIntoView = vi.fn();

function seed(status: "open" | "closed"): void {
  window.localStorage.setItem(
    "ntruth.checkpoint.v1",
    JSON.stringify({
      version: 1,
      tab_id: "tab-test",
      saved_at: new Date().toISOString(),
      status,
      surface: "workspace",
      is_demo: true,
      report: DEMO_REPORT,
      ui: {
        active_view: "experiments",
        selected_block: DEMO_REPORT.blocks[0].id,
        selected_alert: DEMO_REPORT.blocks[0].alerts[0]?.id,
        collapsed: {},
        domain_acknowledged: false,
      },
    }),
  );
}

describe("ripristino da checkpoint al boot", () => {
  beforeEach(() => window.localStorage.clear());
  it("checkpoint open (crash): riapre il workspace con banner di recovery", () => {
    seed("open");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Blocchi sperimentali" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Esperimenti" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByText(/interruzione non volontaria/)).toBeInTheDocument();
  });

  it("checkpoint closed (refresh): riapre il workspace con messaggio neutro", () => {
    seed("closed");
    render(<App />);
    expect(screen.getByRole("heading", { name: "Blocchi sperimentali" })).toBeInTheDocument();
    expect(screen.getByText(/riaperto dal checkpoint locale/)).toBeInTheDocument();
    expect(screen.queryByText(/interruzione non volontaria/)).not.toBeInTheDocument();
  });

  it("senza checkpoint si resta sulla welcome", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /Chiarisci il disegno/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Blocchi sperimentali" })).not.toBeInTheDocument();
  });
});

describe("ReportBundle v8 aperto: niente viste o badge della demo", () => {
  beforeEach(() => window.localStorage.clear());

  it("disabilita le viste di revisione v7 e non mostra conteggi sintetici", async () => {
    const { default: canonicalFixture } = await import("./test-fixtures/quick-design-v8-canonical.json");
    window.localStorage.setItem(
      "ntruth.checkpoint.v1",
      JSON.stringify({
        version: 1,
        tab_id: "tab-test",
        saved_at: new Date().toISOString(),
        status: "closed",
        surface: "workspace",
        is_demo: false,
        report: DEMO_REPORT,
        quick_design: {
          planned_design: canonicalFixture.response.planned_design,
          report: canonicalFixture.response.report_bundle,
          artifacts: canonicalFixture.response.artifacts,
          contract: { code: "PRD_V8", version: "8.0.0", strategy_module_status: "HANDOFF_ONLY" },
        },
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
    expect(screen.getByRole("heading", { name: "ReportBundle v8" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Progetto" })).toHaveAttribute("aria-current", "page");
    for (const name of ["Esperimenti", "Elicitazione", "Grafo", "Documenti", "Correzioni", "Esporta"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toHaveAttribute("aria-disabled", "true");
      expect(button).not.toHaveAttribute("aria-current");
    }
    expect(screen.queryByText(`${DEMO_REPORT.blocks.length} blocchi`)).not.toBeInTheDocument();
  });
});
