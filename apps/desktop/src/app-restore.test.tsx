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
