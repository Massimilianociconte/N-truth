import { AlertTriangle, Calculator } from "lucide-react";
import { useState } from "react";

import { ApiError, pseudoreplicationRisk, type PseudoreplicationRiskResponse } from "../api";
import { allocationKey } from "./rowHelpers";
import type { D0DesignDraft, D0Language, SampleSheetRow } from "./types";

function text(language: D0Language, it: string, en: string): string {
  return language === "it" ? it : en;
}

function decimal(language: D0Language, value: number, digits = 1): string {
  return value.toLocaleString(language === "it" ? "it-IT" : "en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export interface RowStructure {
  units: number;
  observations: number;
  perUnit: number;
}

/**
 * Righe incluse dei due livelli del contrasto e unita allocate distinte.
 * Le righe escluse non entrano nell'analisi e non contano come osservazioni.
 */
export function rowStructure(rows: SampleSheetRow[], draft: D0DesignDraft): RowStructure | null {
  const included = rows.filter(
    (row) => (row.factorLevel === draft.levelA || row.factorLevel === draft.levelB) && row.lifecycleStatus !== "excluded",
  );
  const keys = included.map((row) => allocationKey(row, draft.allocationLevel));
  if (!included.length || keys.some((key) => !key)) return null;
  const perGroup = [draft.levelA, draft.levelB].map(
    (level) => new Set(included.filter((row) => row.factorLevel === level).map((row) => allocationKey(row, draft.allocationLevel))).size,
  );
  const units = new Set(keys).size;
  // Un'unita presente in entrambi i livelli non e un'unita sperimentale del
  // contrasto: il rischio non e calcolabile (e il compiler lo segnala a parte).
  if (perGroup.some((count) => count === 0) || units !== perGroup[0] + perGroup[1]) return null;
  return { units, observations: included.length, perUnit: included.length / units };
}

type RiskState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; key: string; result: PseudoreplicationRiskResponse["pseudoreplication_risk"] };

export function PseudoreplicationRiskCard({ rows, draft, language }: { rows: SampleSheetRow[]; draft: D0DesignDraft; language: D0Language }) {
  const [state, setState] = useState<RiskState>({ status: "idle" });
  const structure = rowStructure(rows, draft);
  const key = structure ? `${structure.units}:${structure.observations}` : "";
  const current = state.status === "ready" && state.key !== key ? { status: "idle" as const } : state;

  const compute = async () => {
    if (!structure) return;
    setState({ status: "loading" });
    try {
      const response = await pseudoreplicationRisk({ total_units: structure.units, mean_obs_per_unit: structure.perUnit, groups: 2 });
      setState({ status: "ready", key, result: response.pseudoreplication_risk });
    } catch (error) {
      setState({ status: "error", message: error instanceof ApiError ? error.message : String(error) });
    }
  };

  return (
    <section className="d0-result-section d0-pseudoreplication" aria-labelledby="pseudoreplication-heading">
      <div className="d0-subheading">
        <div>
          <span className="eyebrow">{text(language, "diagnostica · non fa parte del compiler", "diagnostic · not part of the compiler")}</span>
          <h3 id="pseudoreplication-heading">{text(language, "Rischio di falsi positivi da pseudoreplicazione", "False-positive risk from pseudoreplication")}</h3>
        </div>
      </div>
      {!structure ? (
        <p className="muted">{text(language, "Servono righe incluse con un'unità allocata leggibile e distinta per ciascun livello del contrasto.", "Included rows need a readable allocated unit that is distinct for each contrast level.")}</p>
      ) : structure.perUnit <= 1 ? (
        <p className="muted">{text(language, `${structure.observations} righe da ${structure.units} unità allocate: una riga per unità, le righe non pseudoreplicano l'unità allocata.`, `${structure.observations} rows from ${structure.units} allocated units: one row per unit, rows do not pseudoreplicate the allocated unit.`)}</p>
      ) : (
        <>
          <p>
            {text(
              language,
              `${structure.observations} righe da ${structure.units} unità allocate (${decimal(language, structure.perUnit)} per unità). Se l'analisi trattasse le righe come indipendenti, il tasso reale di falsi positivi dipenderebbe dall'ICC tra righe della stessa unità:`,
              `${structure.observations} rows from ${structure.units} allocated units (${decimal(language, structure.perUnit)} per unit). If the analysis treated rows as independent, the real false-positive rate would depend on the ICC between rows of the same unit:`,
            )}
          </p>
          {current.status === "ready" ? (
            <div className="d0-table-wrap">
              <table className="d0-count-table" aria-label={text(language, "Alpha reale per ICC", "Real alpha by ICC")}>
                <thead><tr><th>ICC</th><th>{text(language, "Falsi positivi reali", "Real false positives")}</th><th>{text(language, "vs nominale", "vs nominal")}</th></tr></thead>
                <tbody>
                  {current.result.sensitivity.map((row) => (
                    <tr key={row.icc}>
                      <td>{decimal(language, row.icc, 2)}</td>
                      <td>{decimal(language, row.alpha_actual * 100)}%</td>
                      <td>×{decimal(language, row.alpha_actual / current.result.alpha_nominal)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <button className="button secondary compact" type="button" onClick={compute} disabled={current.status === "loading"}>
              <Calculator size={15} /> {current.status === "loading" ? text(language, "Calcolo…", "Computing…") : text(language, "Calcola rischio", "Compute risk")}
            </button>
          )}
          {current.status === "error" && (
            <p className="form-error" role="alert"><AlertTriangle size={14} /> {current.message}</p>
          )}
          <small className="muted">
            {text(
              language,
              `Alpha nominale 0,05, test t a due campioni sulle righe, intercetto casuale per unità. Diagnostica: non sostituisce independent_n = ${structure.units} e non valida l'analisi pianificata.`,
              `Nominal alpha 0.05, two-sample t test on rows, random intercept per unit. Diagnostic only: it does not replace independent_n = ${structure.units} nor validate the planned analysis.`,
            )}
          </small>
        </>
      )}
    </section>
  );
}
