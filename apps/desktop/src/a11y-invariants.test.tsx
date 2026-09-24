/** Invarianti di accessibilità ingegneristica sul workspace completo. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
vi.stubGlobal("scrollTo", vi.fn());
Element.prototype.scrollIntoView = vi.fn();

describe("accessibility invariants", () => {
  it("every rendered button exposes an accessible name", () => {
    render(<App />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
    const unnamed = buttons.filter((button) => {
      const label =
        button.getAttribute("aria-label") ??
        button.getAttribute("title") ??
        button.textContent;
      return label === null || label.trim().length === 0;
    });
    expect(unnamed).toEqual([]);
  });

  it("status sheet is a modal dialog with focus on close and Escape to exit", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Stato e limiti" }));
    const dialog = screen.getByRole("dialog", { name: "Limiti e gate" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Chiudi" }),
    );
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Limiti e gate" })).not.toBeInTheDocument();
  });
});
