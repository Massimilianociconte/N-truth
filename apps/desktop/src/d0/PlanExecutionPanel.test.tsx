import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ProspectiveD0CompileResponse } from "../api";
import { PlanExecutionPanel } from "./PlanExecutionPanel";
import type { D0DesignDraft, SampleSheetRow } from "./types";

const draft: D0DesignDraft = {
  question: "Il trattamento modifica la vitalità cellulare a 24 ore?",
  inferenceTarget: "Pozzetti della piastra P01",
  factorName: "Trattamento",
  factorKind: "treatment",
  levelA: "Controllo veicolo",
  levelB: "Composto 10 µM",
  endpointName: "Vitalità cellulare a 24 ore",
  endpointId: "EP-VIABILITY-24H",
  measuredOn: "Well",
  allocationLevel: "Well",
  applicationLevel: "Well",
  independentlyAssigned: "TRUE",
  independenceMechanism: "Randomizzazione documentata dei pozzetti",
  sharedEnvironment: "Piastra P01",
  targetBiologicalUnit: "Well",
  effectMeasure: "Differenza tra medie",
  estimandTargetPopulation: "Pozzetti dichiarati",
  generalizationLevel: "Condizioni dichiarate",
  estimandCondition: "",
  reviewerRole: "researcher",
};

const rows: SampleSheetRow[] = [
  {
    sampleId: "D0-CTL-001",
    sourceId: "SRC-001",
    preparationId: "PREP-001",
    cultureId: "CULT-001",
    plateId: "P01",
    wellId: "A01",
    batchId: "BATCH-001",
    dayId: "DAY-001",
    operatorId: "",
    incubatorId: "INC-001",
    timepoint: "24 h",
    factorLevel: "Controllo veicolo",
    endpointId: "EP-VIABILITY-24H",
    lifecycleStatus: "planned",
    exclusionReason: "",
    fileRef: "",
  },
];

const compileResult = {
  session_id: "session-plan-exec",
  compilation_id: "d0c-plan-exec",
  sample_sheet: { headers: ["sample_id"], rows: [] },
} as unknown as ProspectiveD0CompileResponse;

describe("PlanExecutionPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            record_id: "plan-exec-d0c-plan-exec",
            project_id: "EB-D0-TEST",
            status: "candidate",
            content_checksum: "a".repeat(64),
            payload: {},
            actor_role: "researcher",
            parent_candidate_id: null,
            created_at: "2026-08-01T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
  });

  it("renders planned vs executed distinction", () => {
    render(
      <PlanExecutionPanel
        language="it"
        draft={draft}
        rows={rows}
        experimentBlockId="EB-D0-TEST"
        compileResult={compileResult}
      />,
    );

    expect(screen.getByRole("heading", { name: "Piano vs esecuzione" })).toBeInTheDocument();
    expect(screen.getByTestId("planned-design")).toHaveTextContent("Disegno pianificato");
    expect(screen.getByTestId("executed-design")).toHaveTextContent("Disegno eseguito");
    expect(screen.getByText("Sola lettura")).toBeInTheDocument();
    expect(screen.getByText(/Copia del piano/)).toBeInTheDocument();
    expect(
      screen.getByText(/aggiornamenti di lifecycle devono essere accompagnati da eventi/i),
    ).toBeInTheDocument();
  });

  it("submits API-aligned ProspectivePlanExecutionRecord payload", async () => {
    render(
      <PlanExecutionPanel
        language="it"
        draft={draft}
        rows={rows}
        experimentBlockId="EB-D0-TEST"
        compileResult={compileResult}
      />,
    );

    fireEvent.change(screen.getByLabelText("Titolo eseguito"), {
      target: { value: "Esecuzione wet-lab" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Registra piano vs esecuzione" }));

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toBe("/v1/prospective/plan-execution");
    expect(init?.method).toBe("POST");
    const payload = JSON.parse(String(init?.body));
    expect(payload.project_id).toBe("EB-D0-TEST");
    expect(payload.project_dir).toBe("./ntruth-project");
    expect(payload.actor_role).toBe("researcher");
    expect(payload.record.contract_version).toBe("1.0.0");
    expect(payload.record.record_id).toBe("plan-exec-d0c-plan-exec");
    expect(payload.record.planned_design.experiment_block_id).toBe("EB-D0-TEST");
    expect(payload.record.executed_design.title).toBe("Esecuzione wet-lab");
    expect(payload.record.deviations.length).toBeGreaterThanOrEqual(1);
    expect(payload.record.deviations[0].category).toBe("design_change");
    expect(payload.record.planned_sample_sheet.rows[0].sample_id).toBe("D0-CTL-001");
    expect(payload.record.final_sample_sheet.rows[0].sample_id).toBe("D0-CTL-001");
    expect(payload.record.recorded_by_role).toBe("researcher");
  });
});
