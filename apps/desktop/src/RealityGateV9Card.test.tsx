import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RealityGateV9Card } from "./RealityGateV9Card";
import { defaultGate, gateResponse, presentFlag } from "./test-fixtures/reality-gate-v9";

afterEach(() => vi.unstubAllGlobals());

function deferredResponse() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>(r => { resolve = r; });
  return { promise, resolve };
}

describe("Reality Gate v9 inspection", () => {
  it("uses a neutral unloaded/offline state without a satisfied indicator", () => {
    const { container, rerender } = render(<RealityGateV9Card language="en" apiOnline />);
    expect(screen.getByText(/Not loaded yet/)).toBeInTheDocument();
    expect(container.querySelector(".lucide-shield-check")).toBeNull();
    expect(screen.queryByText(/flags satisfied/)).toBeNull();
    rerender(<RealityGateV9Card language="en" apiOnline={false} />);
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("loads the default gate as HOLD with 0/23 and inspectable UNKNOWN flags", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(defaultGate())));
    render(<RealityGateV9Card language="en" apiOnline />);
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByText(/0\/23 flags satisfied/)).toBeInTheDocument();
    expect(screen.getByText("HOLD")).toBeInTheDocument();
    const row = screen.getByRole("listitem", { name: "blocking_schema_or_theory_gaps" });
    expect(within(row).getByText("UNKNOWN")).toBeInTheDocument();
    expect(within(row).getByText(/Value: unavailable/)).toBeInTheDocument();
    expect(within(row).getByText(/Expected: 0/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(23);
  });

  it("counts exact values, not PRESENT, truthiness, or coerced bool/int equality", async () => {
    const gate = defaultGate();
    presentFlag(gate, 0, false);
    presentFlag(gate, 1, 1);
    presentFlag(gate, 2, true);
    presentFlag(gate, 9, 0);
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(gate)));
    render(<RealityGateV9Card language="en" apiOnline />);
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByText(/2\/23 flags satisfied/)).toBeInTheDocument();
    const wrong = screen.getByRole("listitem", { name: "canonical_schema_registry_frozen" });
    expect(within(wrong).getByText("PRESENT")).toBeInTheDocument();
    expect(within(wrong).getByText(/Value: false/)).toBeInTheDocument();
    expect(within(wrong).getByText(/Expected: true/)).toBeInTheDocument();
    expect(within(wrong).getByText("Not satisfied")).toBeInTheDocument();
  });

  it.each(["ABSENT_EXPLICIT", "NOT_REPORTED", "UNKNOWN", "NOT_APPLICABLE", "CONFLICTING"])("keeps %s unavailable and unsatisfied", async state => {
    const gate = defaultGate();
    const flag = presentFlag(gate, 0, true);
    Object.assign(flag.value, {
      knowledge_state: state, value: null, rationale: "Not resolved",
      source_scope_ids: ["source-1"], conflicting_values: state === "CONFLICTING" ? [true, false] : [],
    });
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(gate)));
    render(<RealityGateV9Card language="en" apiOnline />);
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByText(/0\/23 flags satisfied/)).toBeInTheDocument();
    const row = screen.getByRole("listitem", { name: "canonical_schema_registry_frozen" });
    expect(within(row).getByText(state)).toBeInTheDocument();
    expect(within(row).getByText(/Value: unavailable/)).toBeInTheDocument();
    if (state === "CONFLICTING") expect(within(row).getByText(/Alternatives: true, false/)).toBeInTheDocument();
  });

  it("removes old status during refresh and remains neutral on refresh failure", async () => {
    const pending = deferredResponse();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(gateResponse(defaultGate())).mockReturnValueOnce(pending.promise));
    const { container } = render(<RealityGateV9Card language="en" apiOnline />);
    fireEvent.click(screen.getByRole("button"));
    await screen.findByText("HOLD");
    fireEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(screen.queryByText("HOLD")).toBeNull();
    expect(screen.getByRole("button")).toBeDisabled();
    await act(async () => pending.resolve(gateResponse({})));
    expect(await screen.findByText(/Status unavailable/)).toBeInTheDocument();
    expect(screen.queryByText(/flags satisfied/)).toBeNull();
    expect(container.querySelector(".lucide-shield-check")).toBeNull();
  });

  it("does not count boolean false as integer zero", async () => {
    const gate = defaultGate();
    presentFlag(gate, 9, false);
    vi.stubGlobal("fetch", vi.fn(async () => gateResponse(gate)));
    render(<RealityGateV9Card language="it" apiOnline />);
    fireEvent.click(screen.getByRole("button"));
    expect(await screen.findByText(/0\/23 flag soddisfatti/)).toBeInTheDocument();
    const row = screen.getByRole("listitem", { name: "blocking_schema_or_theory_gaps" });
    expect(within(row).getByText(/Valore: false/)).toBeInTheDocument();
    expect(within(row).getByText(/Atteso: 0/)).toBeInTheDocument();
    expect(within(row).getByText("Non soddisfatto")).toBeInTheDocument();
  });

  it("aborts a pending request on unmount", async () => {
    const pending = deferredResponse();
    let signal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      signal = init.signal ?? undefined;
      return pending.promise;
    }));
    const { unmount } = render(<RealityGateV9Card language="en" apiOnline />);
    fireEvent.click(screen.getByRole("button"));
    unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => pending.resolve(gateResponse(defaultGate())));
  });

  it("discards late responses across offline/reconnect and permits a fresh check", async () => {
    const old = deferredResponse();
    vi.stubGlobal("fetch", vi.fn().mockReturnValueOnce(old.promise).mockResolvedValueOnce(gateResponse(defaultGate())));
    const { rerender } = render(<RealityGateV9Card language="en" apiOnline />);
    fireEvent.click(screen.getByRole("button"));
    rerender(<RealityGateV9Card language="en" apiOnline={false} />);
    expect(screen.getByText(/offline/i)).toBeInTheDocument();
    rerender(<RealityGateV9Card language="en" apiOnline />);
    expect(screen.getByRole("button")).toBeEnabled();
    fireEvent.click(screen.getByRole("button"));
    await screen.findByText("HOLD");
    await act(async () => old.resolve(gateResponse({})));
    expect(screen.getByText("HOLD")).toBeInTheDocument();
    expect(screen.queryByText(/Status unavailable/)).toBeNull();
    rerender(<RealityGateV9Card language="en" apiOnline={false} />);
    expect(screen.queryByText("HOLD")).toBeNull();
    rerender(<RealityGateV9Card language="en" apiOnline />);
    expect(screen.queryByText("HOLD")).toBeNull();
  });
});
