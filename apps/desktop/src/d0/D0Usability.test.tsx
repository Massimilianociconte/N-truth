import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProspectiveD0Workspace } from "./ProspectiveD0Workspace";

function openStep(name: string) {
  fireEvent.click(within(screen.getByRole("navigation", { name: "D0 wizard steps" })).getByRole("button", { name: new RegExp(name) }));
}

function change(name: string, value: string) {
  fireEvent.change(screen.getByRole("textbox", { name }), { target: { value } });
}

function expectLinkedError(field: HTMLElement, message: RegExp) {
  expect(field).toHaveAttribute("aria-invalid", "true");
  const descriptions = field.getAttribute("aria-describedby")?.split(" ").map((id) => document.getElementById(id)?.textContent).join(" ");
  expect(descriptions).toMatch(message);
}

describe("D0 editing usability", () => {
  it("keeps the same focused input through successive sample ID edits", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("SampleSheet");
    const input = screen.getByRole("textbox", { name: "sample_id 2" });
    input.focus();
    change("sample_id 2", "CUSTOM-");
    expect(input).toHaveFocus();
    change("sample_id 2", "CUSTOM-123");
    expect(screen.getByRole("textbox", { name: "sample_id 2" })).toBe(input);
    expect(input).toHaveFocus();
    expect(input).toHaveValue("CUSTOM-123");
  });

  it("preserves surviving row DOM identity when an earlier row is deleted", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("SampleSheet");
    const survivor = screen.getByRole("textbox", { name: "sample_id 3" });
    survivor.focus();
    fireEvent.click(screen.getByRole("button", { name: "Remove row 1" }));
    expect(screen.getByRole("textbox", { name: "sample_id 2" })).toBe(survivor);
    expect(survivor).toHaveFocus();
  });

  it("allocates collision-free IDs and coordinates after middle deletion and repeated additions", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("SampleSheet");
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove row 2" }));
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    const ids = screen.getAllByRole("textbox", { name: /^sample_id / }).map((input) => (input as HTMLInputElement).value);
    const plates = screen.getAllByRole("textbox", { name: /^plate_id / });
    const wells = screen.getAllByRole("textbox", { name: /^well_id / }).map((input, index) => `${(plates[index] as HTMLInputElement).value}::${(input as HTMLInputElement).value}`);
    expect(new Set(ids).size).toBe(6);
    expect(new Set(wells).size).toBe(6);
  });

  it("leaves unknown provenance, factor assignment and timepoint blank on new rows", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("SampleSheet");
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    for (const field of ["source_id", "preparation_id", "culture_id", "batch_id", "day_id", "operator_id", "incubator_id", "timepoint"]) {
      expect(screen.getByRole("textbox", { name: `${field} 5` })).toHaveValue("");
    }
    expect(screen.getByRole("combobox", { name: "factor_level_trattamento 5" })).toHaveValue("");
  });

  it("updates evidence and lifecycle source ranges after additions and deletions", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("SampleSheet");
    fireEvent.click(screen.getByRole("button", { name: "Add row" }));
    openStep("Review");
    const counts = screen.getByRole("table", { name: "Scope-aware lifecycle counts" });
    expect(within(counts).getAllByRole("button", { name: "SampleSheet_D0!A2:P6" })).toHaveLength(12);
    fireEvent.click(screen.getByRole("button", { name: "SampleSheet D0" }));
    expect(screen.getByRole("heading", { name: "Evidence View" }).closest("section")).toHaveTextContent("SampleSheet_D0!A2:P6");
    openStep("SampleSheet");
    fireEvent.click(screen.getByRole("button", { name: "Remove row 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove row 1" }));
    openStep("Review");
    expect(screen.getByRole("table", { name: "Scope-aware lifecycle counts" })).toHaveTextContent("SampleSheet_D0!A2:P4");
  });

  it("links required errors across steps and clears field invalidity after correction", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    change("Primary question", "");
    openStep("SampleSheet");
    change("sample_id 2", "");
    openStep("Review");
    fireEvent.click(screen.getByRole("button", { name: /question.*Missing|Missing.*question/i }));
    const question = screen.getByRole("textbox", { name: "Primary question" });
    expect(question).toHaveFocus();
    expectLinkedError(question, /Missing/i);
    change("Primary question", "A revised question");
    expect(question).not.toHaveAttribute("aria-invalid", "true");
    openStep("Review");
    fireEvent.click(screen.getByRole("button", { name: /Missing.*row 2.*sampleId/i }));
    const sample = screen.getByRole("textbox", { name: "sample_id 2" });
    expect(sample).toHaveFocus();
    expectLinkedError(sample, /Missing/i);
  });

  it("links duplicate IDs and well coordinates to every implicated field", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("SampleSheet");
    change("sample_id 2", "D0-CTL-001");
    change("well_id 2", "A01");
    for (const name of ["sample_id 1", "sample_id 2", "plate_id 1", "well_id 1", "plate_id 2", "well_id 2"]) {
      expectLinkedError(screen.getByRole("textbox", { name }), /Duplicate/i);
    }
    openStep("Review");
    fireEvent.click(screen.getByRole("button", { name: /Duplicate sample_id.*row 2.*sampleId/ }));
    expect(screen.getByRole("textbox", { name: "sample_id 2" })).toHaveFocus();
  });

  it("navigates contrast and typed-timepoint errors to their editable fields", () => {
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("Core Profile");
    change("Level B *", "Controllo veicolo");
    openStep("Review");
    fireEvent.click(screen.getByRole("button", { name: /two levels must differ.*levelB/i }));
    expect(screen.getByRole("textbox", { name: "Level B *" })).toHaveFocus();
    expectLinkedError(screen.getByRole("textbox", { name: "Level B *" }), /two levels must differ/i);
    openStep("SampleSheet");
    change("timepoint 2", "24");
    openStep("Review");
    fireEvent.click(screen.getByRole("button", { name: /lacks a supported time unit.*row 2.*timepoint/i }));
    expect(screen.getByRole("textbox", { name: "timepoint 2" })).toHaveFocus();
    expectLinkedError(screen.getByRole("textbox", { name: "timepoint 2" }), /supported time unit/i);
  });

  it("links canonical 422 snake/camel-case field and fields issues using one-based data rows", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: {
      code: "prospective_d0_invalid",
      issues: [
        { code: "origin", message: "Resolve preparation origin", row: 2, field: "preparation_id" },
        { code: "pair", message: "Resolve source pair", row: 3, fields: ["sourceId", "culture_id"] },
        { code: "estimand", message: "Describe effect", field: "estimand.effect_measure" },
      ],
    } }), { status: 422, headers: { "Content-Type": "application/json" } })));
    render(<ProspectiveD0Workspace active language="en" />);
    openStep("Review");
    fireEvent.click(screen.getByRole("button", { name: "Compile with D0 verifier" }));
    fireEvent.click(await screen.findByRole("button", { name: /Resolve preparation origin.*row 2.*preparationId/ }));
    expect(screen.getByRole("textbox", { name: "preparation_id 2" })).toHaveFocus();
    expectLinkedError(screen.getByRole("textbox", { name: "preparation_id 2" }), /Resolve preparation origin/);
    fireEvent.click(screen.getByRole("button", { name: /Resolve source pair.*row 3.*cultureId/ }));
    expect(screen.getByRole("textbox", { name: "culture_id 3" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: /Describe effect.*effectMeasure/ }));
    expect(screen.getByRole("textbox", { name: "effect_measure" })).toHaveFocus();
    change("effect_measure", "Difference");
    expect(screen.queryByRole("button", { name: /Resolve preparation origin/ })).not.toBeInTheDocument();
  });
});
