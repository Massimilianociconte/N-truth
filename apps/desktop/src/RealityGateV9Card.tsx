/** Inspect the canonical backend composition and its v9 flag values. */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Shield, ShieldAlert, ShieldCheck } from "lucide-react";
import {
  isRealityGateV9FlagSatisfied,
  realityGateV9,
  type RealityGateV9Composition,
} from "./realityGateV9";

export interface RealityGateV9CardProps {
  language: "it" | "en";
  apiOnline: boolean;
}

export function RealityGateV9Card({ language, apiOnline }: RealityGateV9CardProps) {
  const it = language === "it";
  const headingId = useId();
  const [composition, setComposition] = useState<RealityGateV9Composition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    setComposition(null);
    setError(null);
    setLoading(false);
    return () => {
      activeRequest.current?.abort();
      activeRequest.current = null;
    };
  }, [apiOnline]);

  const load = useCallback(async () => {
    if (!apiOnline || activeRequest.current) return;
    const controller = new AbortController();
    activeRequest.current = controller;
    setComposition(null);
    setLoading(true);
    setError(null);
    try {
      const result = await realityGateV9(controller.signal);
      if (activeRequest.current === controller) setComposition(result);
    } catch (exc) {
      if (activeRequest.current === controller) {
        setError(exc instanceof Error ? exc.message : String(exc));
      }
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  }, [apiOnline]);

  // Hide data immediately on the offline render, before effect cleanup.
  const current = apiOnline ? composition : null;
  const flags = current?.v9_evidence_ledger.predicate_assessments ?? [];
  const satisfied = flags.filter(isRealityGateV9FlagSatisfied).length;
  const Icon = !current ? Shield : current.effective_state === "HOLD" ? ShieldAlert : ShieldCheck;

  return (
    <section className="v9-gate-card" aria-labelledby={headingId} aria-busy={loading && apiOnline}>
      <h2 id={headingId} className="v9-gate-title">
        <Icon size={18} aria-hidden="true" />
        Reality Gate v9 · PRD v9 §0.8
      </h2>
      <div aria-live="polite">
        {current ? (
          <p className="v9-gate-state">
            <strong>{current.effective_state}</strong>{" · "}
            {it ? `${satisfied}/${flags.length} flag soddisfatti` : `${satisfied}/${flags.length} flags satisfied`}
          </p>
        ) : (
          <p className="v9-gate-note">
            {!apiOnline
              ? it ? "API offline. Stato non disponibile; verifica di nuovo dopo la riconnessione." : "API offline. Status unavailable; check again after reconnecting."
              : error
                ? it ? `Stato non disponibile: ${error}` : `Status unavailable: ${error}`
                : loading
                  ? it ? "Verifica in corso…" : "Checking…"
                  : it ? "Composizione dei 23 flag v9 sul gate v8 pinnato. Non ancora caricata." : "Composition of the 23 v9 flags over the pinned v8 gate. Not loaded yet."}
          </p>
        )}
      </div>
      {current && (
        <>
          <p className="v9-gate-note">
            {it ? "La composizione non autorizza il training sostanzivo. Lo stato include anche il gate v8 pinnato." : "The composition does not authorize substantive training. Its state also includes the pinned v8 gate."}
          </p>
          <p className="v9-gate-meta" style={{ overflowWrap: "anywhere" }}>
            {current.composition_id}<br />{current.content_checksum}
          </p>
          <details>
            <summary>{it ? "Ispeziona i 23 flag" : "Inspect all 23 flags"}</summary>
            <ul>
              {flags.map(flag => (
                <li key={flag.name} aria-label={flag.name} style={{ overflowWrap: "anywhere" }}>
                  <code>{flag.name}</code>{" · "}<strong>{flag.value.knowledge_state}</strong>
                  <p>
                    <span>{it ? "Valore" : "Value"}: {flag.value.value === null ? it ? "non disponibile" : "unavailable" : String(flag.value.value)}</span>
                    {" · "}<span>{it ? "Atteso" : "Expected"}: {String(flag.expected_value)}</span>
                    {" · "}<span>{isRealityGateV9FlagSatisfied(flag) ? it ? "Soddisfatto" : "Satisfied" : it ? "Non soddisfatto" : "Not satisfied"}</span>
                  </p>
                  {flag.value.knowledge_state === "CONFLICTING" && <p>{it ? "Alternative" : "Alternatives"}: {flag.value.conflicting_values.map(String).join(", ")}</p>}
                  {flag.value.rationale && <p>{flag.value.rationale}</p>}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      <button type="button" className="button secondary" onClick={load} disabled={!apiOnline || loading}>
        {loading && apiOnline
          ? it ? "Verifica in corso…" : "Checking…"
          : current ? it ? "Ricarica" : "Reload"
            : it ? "Verifica Reality Gate v9" : "Check Reality Gate v9"}
      </button>
    </section>
  );
}
