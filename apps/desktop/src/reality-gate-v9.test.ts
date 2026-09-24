import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiErrorCode, apiErrorIssueId, realityGateV9 } from "./api";
import { defaultGate, gateResponse, presentFlag } from "./test-fixtures/reality-gate-v9";

afterEach(() => vi.unstubAllGlobals());

describe("Reality Gate v9 consumed wire boundary", () => {
  it("accepts the Python default HOLD projection without serialized satisfied properties", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(defaultGate())));
    const gate = await realityGateV9();
    expect(gate.effective_state).toBe("HOLD");
    expect(gate.predicates_satisfied).toBe(false);
    expect(gate.v9_evidence_ledger.predicate_assessments).toHaveLength(23);
  });

  const malformed: [string, (gate: ReturnType<typeof defaultGate>) => void][] = [
    ["empty flags", g => { g.v9_evidence_ledger.predicate_assessments = []; }],
    ["missing flag", g => { g.v9_evidence_ledger.predicate_assessments.pop(); }],
    ["duplicate name", g => { g.v9_evidence_ledger.predicate_assessments[1].name = g.v9_evidence_ledger.predicate_assessments[0].name; }],
    ["unknown name", g => { g.v9_evidence_ledger.predicate_assessments[0].name = "invented"; }],
    ["nonhex checksum", g => { g.content_checksum = "z".repeat(64); }],
    ["detached composition ID", g => { g.composition_id = "wrong"; }],
    ["detached ledger ID", g => { g.v9_evidence_ledger.ledger_id = "wrong"; }],
    ["unsupported state", g => { g.effective_state = "GO"; }],
    ["authorization", g => { g.authorizes_substantive_training = true; }],
    ["missing aggregate", g => { Reflect.deleteProperty(g, "predicates_satisfied"); }],
    ["string aggregate", g => { Object.assign(g, { predicates_satisfied: "false" }); }],
    ["false aggregate claim", g => { g.predicates_satisfied = true; }],
    ["false readiness claim", g => { g.effective_state = "READY_FOR_SCIENTIFIC_REVIEW"; }],
    ["noncanonical boolean expectation", g => { g.v9_evidence_ledger.predicate_assessments[0].expected_value = 1; }],
    ["noncanonical integer expectation", g => { g.v9_evidence_ledger.predicate_assessments[9].expected_value = false; }],
    ["unknown epistemic state", g => { g.v9_evidence_ledger.predicate_assessments[0].value.knowledge_state = "READY"; }],
    ["missing value wrapper", g => { Object.assign(g.v9_evidence_ledger.predicate_assessments[0], { value: null }); }],
    ["PRESENT null", g => { presentFlag(g, 0, true).value.value = null; }],
    ["PRESENT string", g => { Object.assign(presentFlag(g, 0, true).value, { value: "true" }); }],
    ["PRESENT float", g => { presentFlag(g, 0, true).value.value = 0.5; }],
    ["unsafe integer", g => { presentFlag(g, 0, true).value.value = Number.MAX_SAFE_INTEGER + 1; }],
    ["PRESENT without review", g => { presentFlag(g, 0, true).reviewer_decision_refs = []; }],
    ["PRESENT without evidence", g => { presentFlag(g, 0, true).value.evidence_ids = []; }],
    ["PRESENT with alternatives", g => { presentFlag(g, 0, true).value.conflicting_values = [true, false]; }],
    ["dangling evidence", g => { presentFlag(g, 0, true).value.evidence_ids = ["missing"]; }],
    ["duplicate reviews", g => { const f = presentFlag(g, 0, true); f.reviewer_decision_refs.push(...f.reviewer_decision_refs); }],
    ["duplicate artifacts", g => { presentFlag(g, 0, true); g.v9_evidence_ledger.evidence_artifacts.push(...g.v9_evidence_ledger.evidence_artifacts); }],
    ["UNKNOWN with selected value", g => { g.v9_evidence_ledger.predicate_assessments[0].value.value = false; }],
    ["UNKNOWN without rationale", g => { g.v9_evidence_ledger.predicate_assessments[0].value.rationale = null; }],
    ["UNKNOWN without scope", g => { g.v9_evidence_ledger.predicate_assessments[0].value.claim_scope_id = null; }],
    ["unbounded rationale", g => { g.v9_evidence_ledger.predicate_assessments[0].value.rationale = "x".repeat(100_000); }],
    ["unbounded references", g => { g.v9_evidence_ledger.predicate_assessments[0].value.source_scope_ids = Array.from({ length: 10_000 }, (_, i) => `s${i}`); }],
    ["CONFLICTING with one distinct alternative", g => { const f = presentFlag(g, 0, true); Object.assign(f.value, { knowledge_state: "CONFLICTING", value: null, conflicting_values: [true, true] }); }],
  ];
  it.each(malformed)("rejects %s", async (_label, mutate) => {
    const gate = defaultGate();
    mutate(gate);
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(gate)));
    await expect(realityGateV9()).rejects.toThrow(/malformed PRD v9 reality gate composition/);
  });

  it.each([null, [], {}, { v9_evidence_ledger: [] }])("rejects malformed envelope %j", async body => {
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(body)));
    await expect(realityGateV9()).rejects.toThrow(/malformed/);
  });

  it.each([false, 1, 0, true])("accepts strict scalar %s even when it does not satisfy the expectation", async value => {
    const gate = defaultGate();
    presentFlag(gate, 0, value);
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(gate)));
    await expect(realityGateV9()).resolves.toMatchObject({ predicates_satisfied: false });
  });

  it("allows all v9 flags satisfied with HOLD and false aggregate because v8 can still block", async () => {
    const gate = defaultGate();
    gate.v9_evidence_ledger.predicate_assessments.forEach((f, i) => presentFlag(gate, i, f.expected_value));
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(gate)));
    await expect(realityGateV9()).resolves.toMatchObject({ effective_state: "HOLD", predicates_satisfied: false });
  });

  it("preserves transport errors and ApiError identity through the facade", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: {
      message: "Unavailable", code: "GATE_UNAVAILABLE", issue_id: "gate-1",
    } }), { status: 503 })));
    const error = await realityGateV9().catch(e => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(503);
    expect(error.message).toBe("Unavailable");
    expect(apiErrorCode(error)).toBe("GATE_UNAVAILABLE");
    expect(apiErrorIssueId(error)).toBe("gate-1");
  });

  it("accepts coherent ready serialization without requiring computed fields on nested models", async () => {
    const gate = defaultGate();
    gate.v9_evidence_ledger.predicate_assessments.forEach((f, i) => presentFlag(gate, i, f.expected_value));
    gate.predicates_satisfied = true;
    gate.effective_state = "READY_FOR_SCIENTIFIC_REVIEW";
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(gate)));
    await expect(realityGateV9()).resolves.toMatchObject({ effective_state: "READY_FOR_SCIENTIFIC_REVIEW" });
  });
});
