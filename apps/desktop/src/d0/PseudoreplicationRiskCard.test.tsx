import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PseudoreplicationRiskCard, rowStructure } from "./PseudoreplicationRiskCard";
import { createSampleRow } from "./rowHelpers";
import type { D0DesignDraft, SampleSheetRow } from "./types";

const draft = (allocationLevel: D0DesignDraft["allocationLevel"]): D0DesignDraft => ({
  question: "q",
  inferenceTarget: "t",
  factorName: "treatment",
  factorKind: "treatment",
  levelA: "drug",
  levelB: "vehicle",
  endpointName: "viability",
  endpointId: "viability",
  measuredOn: "Well",
  allocationLevel,
  applicationLevel: allocationLevel,
  independentlyAssigned: "TRUE",
  independenceMechanism: "separate plates",
  sharedEnvironment: "",
  targetBiologicalUnit: "Well",
  effectMeasure: "difference",
  estimandTargetPopulation: "cultures",
  generalizationLevel: "plate",
  estimandCondition: "",
  reviewerRole: "researcher",
});

/** Tre piastre per braccio, quattro pozzetti per piastra. */
function plateRows(): SampleSheetRow[] {
  const rows: SampleSheetRow[] = [];
  for (const [level, plates] of [["drug", ["P01", "P02", "P03"]], ["vehicle", ["P04", "P05", "P06"]]] as const) {
    for (const plate of plates) {
      for (const well of ["A01", "A02", "A03", "A04"]) {
        rows.push({ ...createSampleRow(rows, "viability"), plateId: plate, wellId: well, factorLevel: level });
      }
    }
  }
  return rows;
}

describe("rowStructure", () => {
  it("counts allocated units and rows per unit, ignoring excluded rows", () => {
    const rows = plateRows();
    rows[0] = { ...rows[0], lifecycleStatus: "excluded" };
    expect(rowStructure(rows, draft("Plate"))).toEqual({ units: 6, observations: 23, perUnit: 23 / 6 });
    expect(rowStructure(rows, draft("Well"))).toEqual({ units: 23, observations: 23, perUnit: 1 });
  });

  it("withholds the structure when a unit key or a contrast level is missing", () => {
    expect(rowStructure(plateRows(), draft("UNKNOWN"))).toBeNull();
    const onlyDrug = plateRows().filter((row) => row.factorLevel === "drug");
    expect(rowStructure(onlyDrug, draft("Plate"))).toBeNull();
    // Una piastra in entrambi i livelli: fattore confuso con l'unita, niente stima.
    const shared = plateRows().map((row) => (row.plateId === "P04" ? { ...row, plateId: "P01" } : row));
    expect(rowStructure(shared, draft("Plate"))).toBeNull();
  });
});

describe("PseudoreplicationRiskCard", () => {
  it("explains that one row per unit is not pseudoreplication and never calls the API", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<PseudoreplicationRiskCard rows={plateRows()} draft={draft("Well")} language="it" />);
    expect(screen.getByText(/una riga per unità/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Calcola rischio/ })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("computes the real false-positive rate only on request", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          pseudoreplication_risk: {
            alpha_nominal: 0.05,
            declared: null,
            sensitivity: [
              { icc: 0.05, alpha_actual: 0.0754 },
              { icc: 0.2, alpha_actual: 0.1621 },
            ],
            naive_df: 22,
            method: "EXACT_BALANCED_RANDOM_INTERCEPT",
            caveats: [],
          },
          strategy: "HANDOFF_ONLY",
          input_mode: "HUMAN_DECLARED",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<PseudoreplicationRiskCard rows={plateRows()} draft={draft("Plate")} language="it" />);
    expect(screen.getByText(/24 righe da 6 unità allocate/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Calcola rischio/ }));
    expect(await screen.findByRole("table", { name: "Alpha reale per ICC" })).toBeInTheDocument();
    expect(screen.getByText("16,2%")).toBeInTheDocument();
    expect(screen.getByText("×3,2")).toBeInTheDocument();
    expect(screen.getByText("0,20")).toBeInTheDocument();

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/v1/power/pseudoreplication-risk");
    expect(JSON.parse(String(init.body))).toEqual({ total_units: 6, mean_obs_per_unit: 4, groups: 2 });
  });

  it("surfaces API errors without inventing a rate", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: { message: "struttura incoerente" } }), {
          status: 422,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(<PseudoreplicationRiskCard rows={plateRows()} draft={draft("Plate")} language="en" />);
    fireEvent.click(screen.getByRole("button", { name: /Compute risk/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("struttura incoerente");
    expect(screen.queryByRole("table")).toBeNull();
  });
});
