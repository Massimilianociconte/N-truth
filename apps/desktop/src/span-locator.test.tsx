import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  SpanLocator,
  buildRefinement,
  evidenceLocatorLabel,
  refinementPatchEntry,
} from "./SpanLocator";
import type { EvidenceSpan } from "./types";

function span(): EvidenceSpan {
  return {
    id: "ev-1",
    file_id: "methods.md",
    section_title: "Methods",
    start: 100,
    end: 116,
    text: "twelve independent cultures were analysed",
    parser_version: "test",
  };
}

describe("buildRefinement", () => {
  it("anchors offsets to the evidence start", () => {
    const built = buildRefinement(span(), 0, 6);
    expect(built).not.toBeNull();
    expect(built?.start).toBe(100);
    expect(built?.end).toBe(106);
    expect(built?.text).toBe("twelve");
  });

  it("normalises inverted selections", () => {
    const built = buildRefinement(span(), 7, 18);
    expect(built?.start).toBe(107);
    expect(built?.end).toBe(118);
    expect(built?.text).toBe("independent");
  });

  it("rejects empty, whitespace and out-of-bounds selections", () => {
    expect(buildRefinement(span(), 5, 5)).toBeNull();
    expect(buildRefinement(span(), 6, 7)).toBeNull();
    expect(buildRefinement(span(), -1, 4)).toBeNull();
    expect(buildRefinement(span(), 0, 999)).toBeNull();
  });
});

describe("evidenceLocatorLabel", () => {
  it("renders the canonical doc:start-end format", () => {
    expect(evidenceLocatorLabel(span(), 100, 106)).toBe("Methods:100-106");
  });
});

describe("refinementPatchEntry", () => {
  it("produces an auditable patch entry", () => {
    const built = buildRefinement(span(), 0, 6);
    const entry = refinementPatchEntry(built!);
    expect(entry.op).toBe("ntruth.evidence_span.refine");
    expect(entry.span_id).toBe("ev-1");
    expect(entry.start).toBe(100);
    expect(entry.end).toBe(106);
  });
});

describe("SpanLocator interactions", () => {
  it("selects a range with two clicks and offers it for apply", () => {
    const onApply = vi.fn();
    render(<SpanLocator evidence={span()} language="it" onApply={onApply} />);
    const chars = screen
      .getByRole("textbox", { name: "Selettore visivo dello span" })
      .querySelectorAll(".span-char");
    fireEvent.click(chars[0]);
    fireEvent.click(chars[5]);
    const range = screen.getByTestId("span-locator-range");
    expect(range.textContent).toContain("Methods:100-106");
    fireEvent.click(screen.getByRole("button", { name: "Usa come evidenza della correzione" }));
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply.mock.calls[0][0].text).toBe("twelve");
  });
});
