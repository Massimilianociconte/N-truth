import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProspectiveD0Workspace } from "./ProspectiveD0Workspace";

function openStep(name: string) {
  const stepper = screen.getByRole("navigation", { name: "Passi del wizard D0" });
  fireEvent.click(within(stepper).getByText(name).closest("button")!);
}

function confirmIndependence() {
  openStep("Core Profile");
  fireEvent.change(screen.getByRole("combobox", { name: "Indipendenza dell'assegnazione" }), {
    target: { value: "TRUE" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: /independence_mechanism/i }), {
    target: { value: "Randomizzazione documentata dei pozzetti prima del trattamento" },
  });
}

function canonicalCompilation(determinability = "DETERMINATE") {
  const conditional = determinability === "CONDITIONALLY_DETERMINATE";
  const determinate = determinability === "DETERMINATE";
  return {
    session_id: "session-d0-test",
    session_persistence: "ephemeral_process_memory",
    contract_version: "1.0.0",
    compiler_version: "1.0.0",
    compilation_id: "d0c-test",
    ruleset_checksum: "a".repeat(64),
    determinability,
    ready_for_handoff: determinability === "DETERMINATE",
    scientific_validation_status: "not_performed",
    capability: { status: "supported", supported: true, reason_codes: [], details: [] },
    verification: { status: "complete", violations: [], warnings: [], checked_invariants: [] },
    issues: [],
    prohibited_outputs: ["scientific_validity_certification"],
    audit_trail: [],
    block: {
      id: "blk-d0-test",
      count_records: determinate
        ? [
            {
              count_id: "cnt-d0-test",
              kind: "independent_n",
              value: 2,
              quantifier: "EXACT",
              scope: { unit_type: "Well", group_or_level: "vehicle", lifecycle: "planned" },
              evidence_ids: ["ev-d0-test"],
            },
          ]
        : [],
      unit_assessments: [
        {
          id: "uas-d0-test",
          scope: { group: "vehicle", endpoint_id: "EP-VIABILITY-24H", timepoint: "24 h" },
          biological_unit: "Well",
          allocation_unit_candidate: "Well",
          experimental_unit: determinate ? "Well" : null,
          observational_unit: "Well",
          analytical_unit: null,
          n_planned: 2,
          n_independent: determinate ? 2 : null,
          biological_source_count: 1,
          inferability: conditional ? "conditional" : determinate ? "inferable" : "not_inferable",
          conditional_scenarios: conditional
            ? [
                {
                  conditional_on: "independently_assigned",
                  if_confirmed: { n_independent: 2 },
                  if_rejected: { n_independent: null },
                  question: "Were wells independently assigned?",
                  rule_id: "GEN-001",
                  evidence_ids: ["ev-d0-test"],
                },
              ]
            : [],
          evidence_ids: ["ev-d0-test"],
        },
      ],
      alerts: [] as Array<{
        id: string;
        rule_id: string;
        severity: string;
        message: string;
        evidence_ids: string[];
      }>,
      contradictions: [] as Array<{
        id: string;
        description: string;
        retained_interpretations: string[];
        evidence_ids: string[];
      }>,
      questions: [],
      evidence: [
        {
          id: "ev-d0-test",
          file_id: "wizard-d0-test",
          text: "Canonical evidence from the D0 API.",
          parser_version: "1.0.0",
          evidence_type: "USER_CONFIRMATION",
        },
      ],
      hierarchy: {
        nodes: [
          {
            id: "node-well-test",
            type: "Well",
            label: "Well A01",
            evidence_ids: ["ev-d0-test"],
          },
        ],
        relations: [],
      },
    },
    sample_sheet: {},
    design_compilation: {},
    rule_evaluations: [],
  };
}

describe("Prospective D0 workspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(canonicalCompilation()), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
  });

  it("constrains the bootstrap to cell cultures, one factor, two levels and one endpoint", () => {
    render(<ProspectiveD0Workspace active language="it" />);

    expect(screen.getByRole("heading", { name: "Progettazione prospettica D0" })).toBeInTheDocument();
    expect(screen.getByText("Colture + piastre")).toBeInTheDocument();
    expect(screen.getByText("1 fattore")).toBeInTheDocument();
    expect(screen.getByText("2 livelli")).toBeInTheDocument();
    expect(screen.getByText("1 endpoint")).toBeInTheDocument();

    openStep("Core Profile");
    expect(screen.getByText("Bloccato dal profilo D0")).toBeInTheDocument();
    expect(screen.getByText("Un solo endpoint primario nel D0")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Indipendenza dell'assegnazione" })).toHaveValue("UNKNOWN");
  });

  it("renders the Appendix O SampleSheet fields and preserves explicit missing semantics", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("SampleSheet");

    const sampleSheet = screen.getByRole("table", { name: "SampleSheet D0" });
    expect(within(sampleSheet).getByRole("columnheader", { name: /sample_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /source_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /preparation_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /culture_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /factor_level_trattamento/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /batch_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /day_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /operator_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /incubator_id/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /timepoint/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /lifecycle_status/ })).toBeInTheDocument();
    expect(within(sampleSheet).getByRole("columnheader", { name: /file_ref/ })).toBeInTheDocument();
    expect(screen.getByText(/cella può restare vuota.*non usare NULL, unknown/i)).toBeInTheDocument();
  });

  it("shows all seven derived states, calls the canonical API and keeps a linked proof trace", async () => {
    render(<ProspectiveD0Workspace active language="it" />);
    confirmIndependence();
    openStep("Verifica");

    const stateTable = screen.getByRole("table", { name: "Sette stati di determinabilità" });
    for (const state of [
      "DETERMINATE",
      "CONDITIONALLY_DETERMINATE",
      "MULTIPLE_PLAUSIBLE_GRAPHS",
      "INSUFFICIENT_INFORMATION",
      "CONFLICTING_INFORMATION",
      "INVALID_GRAPH",
      "OUT_OF_SCOPE",
    ]) {
      expect(within(stateTable).getByText(state)).toBeInTheDocument();
    }

    const status = screen.getByRole("status");
    expect(within(status).getByText("DETERMINATE")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));
    expect(await within(status).findByText("Risultato canonico API")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Esito canonico del compilatore" })).toBeInTheDocument();

    const fetchMock = vi.mocked(fetch);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, request] = fetchMock.mock.calls[0];
    const payload = JSON.parse(String(request?.body));
    expect(payload.rulesetId).toBe("ntruth-core");
    expect(payload.rulesetVersion).toBe("0.2.0");
    expect(payload.draft.experimentBlockId).toMatch(/^EB-D0-/);
    expect(payload.draft).toMatchObject({
      factorKind: "treatment",
      targetBiologicalUnit: "Well",
      reviewerRole: "researcher",
      estimand: {
        effectMeasure: "Differenza tra medie",
        targetPopulationOrUnit: "Pozzetti dichiarati nel blocco D0",
      },
    });
    expect(payload.rows[0]).toMatchObject({
      sourceId: "SRC-001",
      preparationId: "PREP-001",
      lifecycleStatus: "planned",
      extraFields: {
        day_id: "DAY-001",
        operator_id: null,
        incubator_id: "INC-001",
      },
    });

    const counts = screen.getByRole("table", { name: "Conteggi lifecycle scope-aware" });
    expect(within(counts).getAllByText("planned_n")).toHaveLength(2);
    expect(within(counts).getAllByText("allocated_n")).toHaveLength(2);
    expect(within(counts).getAllByText("NOT_REPORTED").length).toBeGreaterThan(0);
    expect(screen.getByText("NOT_CALCULATED")).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Proof trace · GEN-001@1.0.0" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /samplesheet_invariants_valid/ }));
    expect(screen.getByText(/righe prospettiche; ID, provenienza/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Unita e n canonici API" })).toHaveTextContent(
      "EU=Well",
    );
    expect(screen.getByRole("table", { name: "Nodi canonici API" })).toHaveTextContent(
      "Well A01",
    );
    fireEvent.click(screen.getAllByRole("button", { name: "ev-d0-test" })[0]);
    expect(screen.getByRole("heading", { name: "Evidenza canonica sincronizzata" })).toBeInTheDocument();
    expect(screen.getByText("Canonical evidence from the D0 API.")).toBeInTheDocument();
  });

  it("generates one stable experiment-block identity per new wizard draft", () => {
    const first = render(<ProspectiveD0Workspace active language="it" />);
    const firstId = screen.getByText("experiment_block_id").parentElement?.querySelector("dd")?.textContent;
    expect(firstId).toMatch(/^EB-D0-/);
    openStep("Core Profile");
    fireEvent.change(screen.getByRole("textbox", { name: "Fattore primario" }), {
      target: { value: "Fattore revisionato" },
    });
    expect(screen.getByText("experiment_block_id").parentElement?.querySelector("dd")).toHaveTextContent(
      String(firstId),
    );

    first.unmount();
    render(<ProspectiveD0Workspace active language="it" />);
    const secondId = screen.getByText("experiment_block_id").parentElement?.querySelector("dd")?.textContent;
    expect(secondId).toMatch(/^EB-D0-/);
    expect(secondId).not.toBe(firstId);
  });

  it("fails visibly without the API and never relabels the client preview as canonical", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Verifica");

    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("API locale non raggiungibile");
    const status = screen.getByRole("status");
    expect(within(status).getByText("Anteprima client non autorevole")).toBeInTheDocument();
    expect(within(status).queryByText("Risultato canonico API")).not.toBeInTheDocument();
  });

  it("renders a withheld backend state as canonical even when the client preview differs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(canonicalCompilation("OUT_OF_SCOPE")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(<ProspectiveD0Workspace active language="it" />);
    confirmIndependence();
    openStep("Verifica");
    expect(within(screen.getByRole("status")).getByText("DETERMINATE")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));

    const status = screen.getByRole("status");
    expect(await within(status).findByText("OUT_OF_SCOPE")).toBeInTheDocument();
    expect(within(status).getByText("Risultato canonico API")).toBeInTheDocument();
    const canonical = screen.getByRole("region", { name: "Esito canonico del compilatore" });
    expect(within(canonical).getByText("WITHHELD")).toBeInTheDocument();
    expect(within(canonical).queryByText(/independent_n\(/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Anteprima client non autorevole")).toHaveTextContent(
      "Conclusione candidata della preview",
    );
  });

  it("renders canonical conditional assessments without publishing a scalar EU or n", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(canonicalCompilation("CONDITIONALLY_DETERMINATE")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Verifica");
    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));

    const canonicalUnits = await screen.findByRole("table", { name: "Unita e n canonici API" });
    expect(canonicalUnits).toHaveTextContent("EU=—");
    expect(canonicalUnits).toHaveTextContent("independent=—");
    const conditionalBranch = screen
      .getByText("Were wells independently assigned?")
      .closest(".d0-validation-list");
    expect(conditionalBranch).toBeInTheDocument();
    expect(conditionalBranch).toHaveTextContent(/if_confirmed.*n_independent.*2/);
  });

  it("shows canonical alerts, retained conflict interpretations and their evidence", async () => {
    const response = canonicalCompilation("CONFLICTING_INFORMATION");
    response.block.alerts = [
      {
        id: "alert-confounding",
        rule_id: "GEN-005",
        severity: "high",
        message: "Treatment is perfectly confounded with plate.",
        evidence_ids: ["ev-d0-test"],
      },
    ];
    response.block.contradictions = [
      {
        id: "conflict-plate",
        description: "Allocation and plate topology conflict.",
        retained_interpretations: ["wells are independent", "plate is the allocation cluster"],
        evidence_ids: ["ev-d0-test"],
      },
    ];
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(response), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })),
    );
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Verifica");
    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));

    const canonicalAlerts = (await screen.findByText("Alert canonici")).closest(
      ".d0-validation-list",
    );
    expect(canonicalAlerts).toHaveTextContent("Treatment is perfectly confounded with plate.");
    const canonicalConflicts = screen
      .getByText("Conflitti canonici trattenuti")
      .closest(".d0-validation-list");
    expect(canonicalConflicts).toHaveTextContent("Allocation and plate topology conflict.");
    expect(canonicalConflicts).toHaveTextContent("plate is the allocation cluster");
  });

  it("surfaces structured canonical 422 issues with row and field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            detail: {
              code: "prospective_d0_invalid",
              issues: [
                {
                  code: "preparation_origin_not_functional",
                  message: "preparation_id maps to multiple source_id values",
                  row: 2,
                  field: "preparationId",
                },
              ],
            },
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Verifica");
    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent("prospective_d0_invalid");
    expect(error).toHaveTextContent("preparation_origin_not_functional");
    expect(error).toHaveTextContent("row 2");
    expect(error).toHaveTextContent("preparationId");
  });

  it("discards a stale API response when the draft changes while compilation is pending", async () => {
    let resolveResponse!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolveResponse = resolve;
    });
    vi.stubGlobal("fetch", vi.fn(() => pending));
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Verifica");
    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));

    openStep("Core Profile");
    fireEvent.change(screen.getByRole("textbox", { name: "Fattore primario" }), {
      target: { value: "Trattamento aggiornato" },
    });
    resolveResponse(
      new Response(JSON.stringify(canonicalCompilation()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(1));
    openStep("Verifica");

    expect(within(screen.getByRole("status")).getByText("Anteprima client non autorevole")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Esito canonico del compilatore" })).not.toBeInTheDocument();
  });

  it("derives conditional and invalid states instead of allowing a free state label", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Core Profile");
    fireEvent.change(screen.getByRole("combobox", { name: "Indipendenza dell'assegnazione" }), {
      target: { value: "UNKNOWN" },
    });
    openStep("Verifica");
    expect(within(screen.getByRole("status")).getByText("CONDITIONALLY_DETERMINATE")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rami condizionali materializzati" })).toBeInTheDocument();
    expect(screen.getByText(/Se confermato/)).toBeInTheDocument();
    expect(screen.getByText(/Se rifiutato/)).toBeInTheDocument();

    openStep("SampleSheet");
    const firstId = screen.getByRole("textbox", { name: "sample_id 1" });
    const secondId = screen.getByRole("textbox", { name: "sample_id 2" });
    fireEvent.change(secondId, { target: { value: (firstId as HTMLInputElement).value } });
    openStep("Verifica");
    expect(within(screen.getByRole("status")).getByText("INVALID_GRAPH")).toBeInTheDocument();
    expect(screen.getByText("sample_id duplicati.")).toBeInTheDocument();
  });

  it("requires exclusion audit fields, preserves their meaning and withholds inferred lifecycle counts", async () => {
    render(<ProspectiveD0Workspace active language="it" />);
    confirmIndependence();
    openStep("SampleSheet");
    fireEvent.change(screen.getByRole("combobox", { name: "lifecycle_status 1" }), {
      target: { value: "excluded" },
    });
    openStep("Verifica");
    expect(within(screen.getByRole("status")).getByText("INVALID_GRAPH")).toBeInTheDocument();
    expect(screen.getByText("Riga 1: l'esclusione richiede fase e autore.")).toBeInTheDocument();

    openStep("SampleSheet");
    fireEvent.change(screen.getByRole("textbox", { name: "exclusion_reason 1" }), {
      target: { value: "post-treatment | autore: AB | criterio: contaminazione" },
    });
    openStep("Verifica");
    expect(within(screen.getByRole("status")).getByText("DETERMINATE")).toBeInTheDocument();
    const counts = screen.getByRole("table", { name: "Conteggi lifecycle scope-aware" });
    const excludedRows = within(counts)
      .getAllByText("excluded_n")
      .map((cell) => cell.closest("tr")!);
    expect(within(excludedRows[0]).getByText("NOT_REPORTED")).toBeInTheDocument();
    expect(within(excludedRows[1]).getByText("NOT_REPORTED")).toBeInTheDocument();
    expect(screen.getByText(/fasi successive restano NOT_REPORTED/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Compila con verificatore D0/ }));
    await screen.findByRole("heading", { name: "Esito canonico del compilatore" });
    const [, request] = vi.mocked(fetch).mock.calls[0];
    const payload = JSON.parse(String(request?.body));
    expect(payload.rows[0]).toMatchObject({
      exclusionReason: "post-treatment | autore: AB | criterio: contaminazione",
      exclusionPhase: "post_treatment",
      exclusionAuthorRole: "AB",
      exclusionPrespecified: "UNKNOWN",
      exclusionImpact: null,
    });
  });

  it("rejects a plate assigned to both factor levels and never counts wells as plates", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Core Profile");
    fireEvent.change(screen.getByRole("combobox", { name: "allocation_level" }), {
      target: { value: "Plate" },
    });
    openStep("Verifica");

    expect(within(screen.getByRole("status")).getByText("INVALID_GRAPH")).toBeInTheDocument();
    expect(screen.getByText(/unità di allocazione P01 è associata a più livelli/i)).toBeInTheDocument();
    const counts = screen.getByRole("table", { name: "Conteggi lifecycle scope-aware" });
    const plannedRows = within(counts).getAllByText("planned_n").map((cell) => cell.closest("tr")!);
    expect(within(plannedRows[0]).getByText("1")).toBeInTheDocument();
    expect(within(plannedRows[1]).getByText("1")).toBeInTheDocument();
  });

  it("counts distinct plate allocation units in a valid plate-level design", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("SampleSheet");
    fireEvent.change(screen.getByRole("textbox", { name: "plate_id 3" }), {
      target: { value: "P02" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: "plate_id 4" }), {
      target: { value: "P02" },
    });
    confirmIndependence();
    fireEvent.change(screen.getByRole("combobox", { name: "allocation_level" }), {
      target: { value: "Plate" },
    });
    openStep("Verifica");

    expect(within(screen.getByRole("status")).getByText("DETERMINATE")).toBeInTheDocument();
    expect(screen.getByText(/independent_n\(Controllo veicolo\) = 1/)).toBeInTheDocument();
    expect(screen.getByText(/independent_n\(Composto 10 µM\) = 1/)).toBeInTheDocument();
  });

  it("withholds a contrast when either factor level has no allocation unit", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("SampleSheet");
    for (let index = 3; index <= 4; index += 1) {
      fireEvent.change(screen.getByRole("combobox", { name: `factor_level_trattamento ${index}` }), {
        target: { value: "Controllo veicolo" },
      });
    }
    openStep("Verifica");

    expect(within(screen.getByRole("status")).getByText("INVALID_GRAPH")).toBeInTheDocument();
    expect(screen.getByText(/Composto 10 µM.*non contiene alcuna unità di allocazione/)).toBeInTheDocument();
  });

  it("never turns an unknown allocation level into an exact zero well count", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("Core Profile");
    fireEvent.change(screen.getByRole("combobox", { name: "allocation_level" }), {
      target: { value: "UNKNOWN" },
    });
    openStep("Verifica");

    expect(
      within(screen.getByRole("status")).getByText("INSUFFICIENT_INFORMATION"),
    ).toBeInTheDocument();
    const counts = screen.getByRole("table", { name: "Conteggi lifecycle scope-aware" });
    const plannedRows = within(counts)
      .getAllByText("planned_n")
      .map((cell) => cell.closest("tr")!);
    for (const row of plannedRows) {
      expect(within(row).getByText("—")).toBeInTheDocument();
      expect(within(row).getByText("NOT_REPORTED")).toBeInTheDocument();
      expect(within(row).queryByText("0")).not.toBeInTheDocument();
    }
  });

  it("routes multiple or untyped timepoints out of the D0 capability boundary", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("SampleSheet");
    fireEvent.change(screen.getByRole("textbox", { name: "timepoint 2" }), {
      target: { value: "48 h" },
    });
    openStep("Verifica");
    expect(within(screen.getByRole("status")).getByText("OUT_OF_SCOPE")).toBeInTheDocument();
    expect(screen.getByText("Il profilo D0 accetta un solo timepoint esplicito.")).toBeInTheDocument();

    openStep("SampleSheet");
    for (let index = 1; index <= 4; index += 1) {
      fireEvent.change(screen.getByRole("textbox", { name: `timepoint ${index}` }), {
        target: { value: "24" },
      });
    }
    openStep("Verifica");
    expect(within(screen.getByRole("status")).getByText("OUT_OF_SCOPE")).toBeInTheDocument();
    expect(screen.getByText(/Timepoint '24' privo di unità temporale/)).toBeInTheDocument();
  });

  it("adds nullable source and preparation cells as blanks, never placeholders", () => {
    render(<ProspectiveD0Workspace active language="it" />);
    openStep("SampleSheet");
    fireEvent.click(screen.getByRole("button", { name: /Aggiungi riga/ }));

    expect(screen.getByRole("textbox", { name: "source_id 5" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "preparation_id 5" })).toHaveValue("");
  });
});
