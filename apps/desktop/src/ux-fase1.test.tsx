/** Guardrail UX Fase 1: tab L2, gate, inspector L3, sidebar a gruppi, dialog. */

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
vi.stubGlobal("scrollTo", vi.fn());
Element.prototype.scrollIntoView = vi.fn();

function enterSyntheticDemo(): void {
  fireEvent.click(screen.getByRole("button", { name: "Apri demo sintetica" }));
}

function openTargetForm(): void {
  fireEvent.click(screen.getByRole("button", { name: "Modifica target" }));
}

describe("UX Fase 1 — navigazione a gruppi", () => {
  it("groups 8 unchanged buttons under 5 perceivable headings", () => {
    render(<App />);
    for (const heading of ["Progetta", "Inquadra", "Chiarisci", "Fonti e correzioni", "Condividi"]) {
      expect(screen.getByText(heading)).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Progettazione D0" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Elicitazione" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Correzioni" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Esporta" })).toBeInTheDocument();
  });

  it("moves focus to the view heading after navigation", async () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Elicitazione" }));
    await waitFor(() => expect(document.activeElement?.id).toBe("issues-heading"));
    fireEvent.click(screen.getByRole("button", { name: "Grafo" }));
    await waitFor(() => expect(document.activeElement?.id).toBe("graph-heading"));
  });

  it("renders a single screen at a time with aria-current on its voice", () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Grafo" }));
    expect(screen.getByRole("heading", { name: "Grafo del disegno sperimentale" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Blocchi sperimentali" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Target inferenziale" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Evidenza" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Grafo" })).toHaveAttribute("aria-current", "page");
  });
});

describe("UX Fase 1 — tab contestuali L2", () => {
  it("exposes a WAI-ARIA tablist with a single visible ontology at a time", () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    const tablist = screen.getByRole("tablist", { name: "Sezioni del blocco in revisione" });
    const tabs = within(tablist).getAllByRole("tab");
    expect(tabs).toHaveLength(4);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Target inferenziale" })).toBeInTheDocument();
    // Assi separati: adequacy vive nel tab Methods, fuori dal pannello visibile.
    expect(within(screen.getByRole("tabpanel")).queryByTestId("axis-design-adequacy")).not.toBeInTheDocument();
  });

  it("switches tabs and supports arrow-key navigation", () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    const counts = screen.getByRole("tab", { name: "Unità e conteggi" });
    fireEvent.click(counts);
    expect(counts).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText(/CANONICO — registro dei conteggi per replication/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Target inferenziale" })).not.toBeInTheDocument();
    fireEvent.keyDown(counts, { key: "ArrowRight" });
    const alternatives = screen.getByRole("tab", { name: "Alternative e domande" });
    expect(alternatives).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(alternatives);
  });
});

describe("UX Fase 1 — comprehension gate", () => {
  it("blocks confirmation until the 3 checks pass, with unlimited retries", async () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    openTargetForm();
    const compile = screen.getByRole("button", { name: /Conferma target ed estimand/ });
    expect(compile).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "Il pozzetto o la cellula dove misuro l'endpoint" }));
    expect(await screen.findByText(/Non ancora: rileggi il feedback e riprova/)).toBeInTheDocument();
    expect(compile).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "L'unità assegnata al trattamento" }));
    fireEvent.click(screen.getByRole("radio", { name: "n = 1: i 12 sono osservazioni replicate" }));
    fireEvent.click(screen.getByRole("radio", { name: "Consegna vincoli e domande allo statistico, senza suggerire test" }));
    expect(await screen.findByText(/Comprensione registrata per questo blocco/)).toBeInTheDocument();
  });

  it("allows a motivated skip that stays visible and never certifies", async () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    openTargetForm();
    fireEvent.click(screen.getByText("Salta con motivazione (revisori avanzati)"));
    const skip = screen.getByRole("button", { name: "Salta con motivazione" });
    expect(skip).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText(/Almeno 20 caratteri/), {
      target: { value: "Biostatistico: unità già chiarita in call con il team." },
    });
    expect(skip).toBeEnabled();
    fireEvent.click(skip);
    expect(await screen.findByText(/Skip registrato con motivazione/)).toBeInTheDocument();
    expect(screen.getByText(/non è un'approvazione del disegno/)).toBeInTheDocument();
  });
});

describe("UX Fase 1 — inspector evidenza L3", () => {
  it("lists block spans with plain-language type labels and syncs selection", () => {
    render(<App />);
    enterSyntheticDemo();
    fireEvent.click(screen.getByRole("button", { name: "Documenti" }));
    expect(screen.getByText(/Span del blocco \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Tipo AUTHOR_ASSERTION/)).toBeInTheDocument();
    expect(screen.getByText("Dichiarazione autori")).toBeInTheDocument();
    const listbox = screen.getByRole("listbox");
    expect(within(listbox).getAllByRole("option")).toHaveLength(1);
    // Cambio blocco via Esperimenti → inspector sincronizzato sul nuovo blocco.
    fireEvent.click(screen.getByRole("button", { name: "Esperimenti" }));
    fireEvent.click(screen.getByRole("button", { name: /Trattamento antibiotico/ }));
    fireEvent.click(screen.getByRole("button", { name: "Documenti" }));
    expect(screen.getByText(/il numero di unità indipendenti non è riportato/)).toBeInTheDocument();
  });
});

describe("UX Fase 1 — dialog simmetrici", () => {
  it("traps focus in the status sheet and returns focus to its trigger", async () => {
    render(<App />);
    const trigger = screen.getByRole("button", { name: "Stato e limiti" });
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Limiti e gate" });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Chiudi" }));
    // Shift+Tab dal primo elemento riporta all'ultimo (trap).
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    const focusable = within(dialog)
      .getAllByRole("button")
      .filter((button) => !(button as HTMLButtonElement).disabled);
    expect(document.activeElement).toBe(focusable[focusable.length - 1]);
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Limiti e gate" })).not.toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });
});
