/**
 * Checkpoint locale: roundtrip, chiusura brusca, corruzione, refresh pulito.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  clearCheckpoint,
  corruptBackupExists,
  loadCheckpoint,
  markCheckpointClosed,
  saveCheckpoint,
  type CheckpointPayload,
} from "./checkpoint";

function base(): Partial<CheckpointPayload> {
  return { surface: "workspace", is_demo: true, report: { report_id: "rep-1" } };
}

beforeEach(() => clearCheckpoint());

describe("checkpoint locale", () => {
  it("roundtrip preserva lo stato del workspace", () => {
    saveCheckpoint(base());
    saveCheckpoint({
      ui: { active_view: "graph", collapsed: {}, domain_acknowledged: false },
    });
    const result = loadCheckpoint();
    expect(result).not.toBeNull();
    expect(result!.payload.report).toEqual({ report_id: "rep-1" });
    expect(result!.payload.ui?.active_view).toBe("graph");
  });

  it("un checkpoint open indica chiusura brusca", () => {
    saveCheckpoint(base());
    const result = loadCheckpoint();
    expect(result?.abrupt).toBe(true);
  });

  it("una chiusura volontaria non è brusca e conserva i dati", () => {
    saveCheckpoint(base());
    markCheckpointClosed();
    const result = loadCheckpoint();
    expect(result?.abrupt).toBe(false);
    expect(result?.payload.report).toEqual({ report_id: "rep-1" });
  });

  it("un payload corrotto viene messo da parte e ignorato", () => {
    window.localStorage.setItem("ntruth.checkpoint.v1", "{not-json");
    expect(loadCheckpoint()).toBeNull();
    expect(corruptBackupExists()).toBe(true);
    saveCheckpoint(base());
    const result = loadCheckpoint();
    expect(result?.abrupt).toBe(true);
  });

  it("clearCheckpoint rimuove tutto", () => {
    saveCheckpoint(base());
    clearCheckpoint();
    expect(loadCheckpoint()).toBeNull();
  });

  it("saved_at è aggiornato a ogni salvataggio", () => {
    saveCheckpoint(base());
    const first = loadCheckpoint()!.payload.saved_at;
    saveCheckpoint({
      ui: { active_view: "graph", collapsed: {}, domain_acknowledged: false },
    });
    const second = loadCheckpoint()!.payload.saved_at;
    expect(new Date(second).getTime()).toBeGreaterThanOrEqual(new Date(first).getTime());
  });
});
