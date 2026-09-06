/** Card ispezionabile del Reality Gate v9 (PRD v9 §0.8) sulla welcome.
 *
 * Lo stato arriva dall'endpoint `/v9/reality-gate` (composizione
 * content-addressed sul gate v8 pinnato). La card non valuta nulla: mostra
 * solo il registro, che resta HOLD senza evidenze reali.
 */

import { useCallback, useState } from "react";
import { ShieldAlert, ShieldCheck } from "lucide-react";
import { realityGateV9, type RealityGateV9Composition } from "./api";

export function RealityGateV9Card({
  language,
  apiOnline,
}: {
  language: "it" | "en";
  apiOnline: boolean;
}) {
  const it = language === "it";
  const [composition, setComposition] = useState<RealityGateV9Composition | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setComposition(await realityGateV9());
    } catch (exc) {
      setComposition(null);
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  }, []);

  const unsatisfied = composition
    ? composition.v9_evidence_ledger.predicate_assessments.filter(
        (flag) => flag.value.knowledge_state !== "PRESENT",
      ).length
    : composition
      ? 0
      : 0;
  const total = composition?.v9_evidence_ledger.predicate_assessments.length ?? 23;

  return (
    <section className="v9-gate-card" aria-labelledby="v9-gate-heading">
      <h2 id="v9-gate-heading" className="v9-gate-title">
        {composition?.effective_state === "HOLD" ? <ShieldAlert size={18} /> : <ShieldCheck size={18} />}
        Reality Gate v9 · PRD v9 §0.8
      </h2>
      {composition === null ? (
        <>
          <p className="v9-gate-note">
            {error
              ? it
                ? `Stato non disponibile: ${error}`
                : `Status unavailable: ${error}`
              : it
                ? "Composizione content-addressed dei 23 flag v9 sul gate v8 pinnato. Non ancora caricata."
                : "Content-addressed composition of the 23 v9 flags over the pinned v8 gate. Not loaded yet."}
          </p>
          <button
            type="button"
            className="button secondary"
            onClick={load}
            disabled={!apiOnline || loading}
          >
            {loading
              ? it
                ? "Verifica in corso…"
                : "Checking…"
              : it
                ? "Verifica Reality Gate v9"
                : "Check Reality Gate v9"}
          </button>
        </>
      ) : (
        <>
          <p className="v9-gate-state">
            <strong>{composition.effective_state}</strong>
            {" · "}
            {it
              ? `${total - unsatisfied}/${total} flag soddisfatti`
              : `${total - unsatisfied}/${total} flags satisfied`}
          </p>
          <p className="v9-gate-note">
            {composition.authorizes_substantive_training
              ? it
                ? "La composizione non autorizza mai il training da sola."
                : "The composition alone never authorizes training."
              : it
                ? "Training sostanzivo non autorizzato: servono evidenze reali registrate."
                : "Substantive training not authorized: registered real evidence is required."}
          </p>
          <p className="v9-gate-meta">
            {composition.composition_id}
            <br />
            {composition.content_checksum.slice(0, 16)}…
          </p>
          <button type="button" className="button secondary" onClick={load} disabled={loading}>
            {loading ? (it ? "Ricarica in corso…" : "Reloading…") : it ? "Ricarica" : "Reload"}
          </button>
        </>
      )}
    </section>
  );
}
