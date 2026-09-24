import { Check, LoaderCircle, Sparkles } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import type {
  CountQuantifier,
  CountRecord,
  EvidenceSpan,
  ExclusionRecord,
  ExperimentBlock,
} from "./types";

export type CorrectionPatch = Array<Record<string, unknown>>;

type Reason = "typo" | "parser_error" | "model_error" | "source_missing" | "domain_judgement" | "other";

const QUANTIFIERS: CountQuantifier[] = [
  "EXACT",
  "APPROXIMATE",
  "LOWER_BOUND",
  "UPPER_BOUND",
  "RANGE",
  "UNKNOWN",
  "NOT_REPORTED",
];

const COUNT_KINDS: CountRecord["kind"][] = [
  "planned_n",
  "allocated_n",
  "treated_n",
  "observed_n",
  "excluded_n",
  "analysed_n",
  "declared_n",
  "observational_n",
  "analytical_n",
  "independent_n",
  "biological_source_count",
  "effective_n",
];

const PHASES: ExclusionRecord["phase"][] = [
  "pre_allocation",
  "post_allocation",
  "post_treatment",
  "post_measurement",
  "post_outcome",
  "unknown",
];

const LIFECYCLES = ["planned", "allocated", "treated", "observed", "excluded", "analysed"] as const;

function clone<T>(value: T): T {
  return structuredClone(value);
}

function numberOrNull(value: string): number | null {
  return value.trim() === "" ? null : Number(value);
}

function normalizedQuantifier(record: CountRecord, quantifier: CountQuantifier): CountRecord {
  if (quantifier === "RANGE") {
    return {
      ...record,
      quantifier,
      value: null,
      lower_bound: record.lower_bound ?? null,
      upper_bound: record.upper_bound ?? null,
    };
  }
  if (["EXACT", "APPROXIMATE", "LOWER_BOUND", "UPPER_BOUND"].includes(quantifier)) {
    return {
      ...record,
      quantifier,
      value: record.value ?? null,
      lower_bound: null,
      upper_bound: null,
    };
  }
  return { ...record, quantifier, value: null, lower_bound: null, upper_bound: null };
}

function isValidCountNumber(value: number | null | undefined, allowFraction: boolean): boolean {
  return (
    value !== null &&
    value !== undefined &&
    Number.isFinite(value) &&
    value >= 0 &&
    (allowFraction || Number.isInteger(value))
  );
}

function countDraftIsValid(record: CountRecord): boolean {
  const allowFraction = record.kind === "effective_n";
  if (record.quantifier === "RANGE") {
    return (
      isValidCountNumber(record.lower_bound, allowFraction) &&
      isValidCountNumber(record.upper_bound, allowFraction) &&
      (record.lower_bound as number) <= (record.upper_bound as number) &&
      record.value === null
    );
  }
  if (["EXACT", "APPROXIMATE", "LOWER_BOUND", "UPPER_BOUND"].includes(record.quantifier)) {
    return (
      isValidCountNumber(record.value, allowFraction) &&
      record.lower_bound === null &&
      record.upper_bound === null
    );
  }
  return record.value === null && record.lower_bound === null && record.upper_bound === null;
}

function updateScope(
  record: CountRecord,
  field: keyof CountRecord["scope"],
  rawValue: string,
): CountRecord {
  if (field === "unknown_reasons") return record;
  const value = rawValue.trim() || null;
  const unknownReasons = { ...record.scope.unknown_reasons };
  const decisive = ["unit_type", "factor_id", "contrast_id", "group_or_level", "endpoint_id", "timepoint", "lifecycle"];
  if (decisive.includes(field)) {
    if (value === null) unknownReasons[field] = "not reported after human review";
    else delete unknownReasons[field];
  }
  return {
    ...record,
    scope: { ...record.scope, [field]: value, unknown_reasons: unknownReasons },
  };
}

function updateExclusion(
  record: ExclusionRecord,
  field: "endpoint_id" | "group" | "author_role" | "reason" | "impact",
  rawValue: string,
): ExclusionRecord {
  const value = rawValue.trim() || null;
  const unknownReasons = { ...record.unknown_reasons };
  if (value === null) unknownReasons[field] = "not reported after human review";
  else delete unknownReasons[field];
  return { ...record, [field]: value, unknown_reasons: unknownReasons };
}

function updateExclusionState(
  record: ExclusionRecord,
  field: "phase" | "prespecified",
  value: ExclusionRecord[typeof field],
): ExclusionRecord {
  const unknownReasons = { ...record.unknown_reasons };
  const isUnknown = value === "unknown" || value === "UNKNOWN";
  if (isUnknown) unknownReasons[field] = "not reported after human review";
  else delete unknownReasons[field];
  return { ...record, [field]: value, unknown_reasons: unknownReasons };
}

function ReasonFields({
  language,
  reason,
  rationale,
  onReason,
  onRationale,
}: {
  language: "it" | "en";
  reason: Reason;
  rationale: string;
  onReason: (value: Reason) => void;
  onRationale: (value: string) => void;
}) {
  return (
    <>
      <label className="field-label">
        {language === "it" ? "Motivo" : "Reason"}
        <select value={reason} onChange={(event) => onReason(event.target.value as Reason)}>
          <option value="typo">{language === "it" ? "Refuso nella fonte" : "Source typo"}</option>
          <option value="parser_error">{language === "it" ? "Errore parser" : "Parser error"}</option>
          <option value="model_error">{language === "it" ? "Errore modello" : "Model error"}</option>
          <option value="source_missing">{language === "it" ? "Fonte incompleta" : "Incomplete source"}</option>
          <option value="domain_judgement">{language === "it" ? "Giudizio di dominio" : "Domain judgement"}</option>
          <option value="other">{language === "it" ? "Altro" : "Other"}</option>
        </select>
      </label>
      <label className="field-label">
        {language === "it" ? "Giustificazione" : "Rationale"}
        <textarea
          value={rationale}
          onChange={(event) => onRationale(event.target.value)}
          placeholder={language === "it" ? "Cita la fonte o spiega il giudizio (minimo 8 caratteri)." : "Cite the source or explain the judgement (minimum 8 characters)."}
          rows={3}
        />
      </label>
    </>
  );
}

export function CanonicalCorrectionForm({
  block,
  evidence,
  language,
  isDemo,
  onApply,
}: {
  block: ExperimentBlock;
  evidence?: EvidenceSpan;
  language: "it" | "en";
  isDemo: boolean;
  onApply: (patch: CorrectionPatch, rationale: string, reason: string) => Promise<void> | void;
}) {
  const hasCounts = block.count_records.length > 0;
  const hasExclusions = block.exclusion_records.length > 0;
  const [target, setTarget] = useState<"count" | "exclusion">(hasCounts ? "count" : "exclusion");
  const [countIndex, setCountIndex] = useState(0);
  const [exclusionIndex, setExclusionIndex] = useState(0);
  const [countDraft, setCountDraft] = useState<CountRecord | undefined>();
  const [exclusionDraft, setExclusionDraft] = useState<ExclusionRecord | undefined>();
  const [reason, setReason] = useState<Reason>("domain_judgement");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (hasCounts) setCountDraft(clone(block.count_records[countIndex] ?? block.count_records[0]));
  }, [block.id, block.count_records, countIndex, hasCounts]);
  useEffect(() => {
    if (hasExclusions) setExclusionDraft(clone(block.exclusion_records[exclusionIndex] ?? block.exclusion_records[0]));
  }, [block.id, block.exclusion_records, exclusionIndex, hasExclusions]);
  useEffect(() => {
    setTarget(hasCounts ? "count" : "exclusion");
    setCountIndex(0);
    setExclusionIndex(0);
  }, [block.id, hasCounts]);

  const original = target === "count" ? block.count_records[countIndex] : block.exclusion_records[exclusionIndex];
  const draft = target === "count" ? countDraft : exclusionDraft;
  const changed = useMemo(() => JSON.stringify(original) !== JSON.stringify(draft), [draft, original]);
  const draftValid = target !== "count" || (countDraft !== undefined && countDraftIsValid(countDraft));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft || !changed || !draftValid || rationale.trim().length < 8) return;
    setBusy(true);
    try {
      await onApply(
        [{ op: "replace", path: `/${target === "count" ? "count_records" : "exclusion_records"}/${target === "count" ? countIndex : exclusionIndex}`, value: draft }],
        rationale.trim(),
        reason,
      );
      setRationale("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="correction-form canonical-correction-form">
      {hasCounts && hasExclusions && (
        <label className="field-label">
          {language === "it" ? "Registro da correggere" : "Registry to correct"}
          <select aria-label={language === "it" ? "Registro da correggere" : "Registry to correct"} value={target} onChange={(event) => setTarget(event.target.value as "count" | "exclusion")}>
            <option value="count">CountRecord · lifecycle n</option>
            <option value="exclusion">ExclusionRecord · attrition</option>
          </select>
        </label>
      )}

      {target === "count" && countDraft && (
        <div className="canonical-fields">
          <label className="field-label">
            CountRecord
            <select aria-label="CountRecord" value={countIndex} onChange={(event) => setCountIndex(Number(event.target.value))}>
              {block.count_records.map((record, index) => <option key={record.count_id} value={index}>{record.kind} · {record.count_id}</option>)}
            </select>
          </label>
          <div className="field-grid">
            <label className="field-label">Kind
              <select aria-label="Count kind" value={countDraft.kind} onChange={(event) => {
                const kind = event.target.value as CountRecord["kind"];
                setCountDraft({ ...countDraft, kind, diagnostic_only: kind === "effective_n" });
              }}>
                {COUNT_KINDS.map((kind) => <option key={kind}>{kind}</option>)}
              </select>
            </label>
            <label className="field-label">Quantifier
              <select aria-label="Count quantifier" value={countDraft.quantifier} onChange={(event) => setCountDraft(normalizedQuantifier(countDraft, event.target.value as CountQuantifier))}>
                {QUANTIFIERS.map((quantifier) => <option key={quantifier}>{quantifier}</option>)}
              </select>
            </label>
            {countDraft.quantifier === "RANGE" ? <>
              <label className="field-label">Lower bound<input aria-label="Count lower bound" type="number" min="0" step={countDraft.kind === "effective_n" ? "any" : "1"} value={countDraft.lower_bound ?? ""} onChange={(event) => setCountDraft({ ...countDraft, lower_bound: numberOrNull(event.target.value) })} /></label>
              <label className="field-label">Upper bound<input aria-label="Count upper bound" type="number" min="0" step={countDraft.kind === "effective_n" ? "any" : "1"} value={countDraft.upper_bound ?? ""} onChange={(event) => setCountDraft({ ...countDraft, upper_bound: numberOrNull(event.target.value) })} /></label>
            </> : ["EXACT", "APPROXIMATE", "LOWER_BOUND", "UPPER_BOUND"].includes(countDraft.quantifier) && (
              <label className="field-label">Value<input aria-label="Count value" type="number" min="0" step={countDraft.kind === "effective_n" ? "any" : "1"} value={countDraft.value ?? ""} onChange={(event) => setCountDraft({ ...countDraft, value: numberOrNull(event.target.value) })} /></label>
            )}
          </div>
          {!draftValid && (
            <p role="alert" className="field-error">
              {language === "it"
                ? "Inserisci esplicitamente un conteggio valido; N-Truth non presume zero."
                : "Enter a valid count explicitly; N-Truth never assumes zero."}
            </p>
          )}
          <fieldset>
            <legend>{language === "it" ? "Scope canonico" : "Canonical scope"}</legend>
            <div className="field-grid">
              <label className="field-label">Unit type<input aria-label="Count unit type" value={countDraft.scope.unit_type ?? ""} onChange={(event) => setCountDraft(updateScope(countDraft, "unit_type", event.target.value))} /></label>
              <label className="field-label">Lifecycle<select aria-label="Count lifecycle" value={countDraft.scope.lifecycle ?? ""} onChange={(event) => setCountDraft(updateScope(countDraft, "lifecycle", event.target.value))}><option value="">—</option>{LIFECYCLES.map((value) => <option key={value}>{value}</option>)}</select></label>
              <label className="field-label">Factor<select aria-label="Count factor" value={countDraft.scope.factor_id ?? ""} onChange={(event) => setCountDraft(updateScope(countDraft, "factor_id", event.target.value))}><option value="">—</option>{block.factors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <label className="field-label">Contrast<select aria-label="Count contrast" value={countDraft.scope.contrast_id ?? ""} onChange={(event) => setCountDraft(updateScope(countDraft, "contrast_id", event.target.value))}><option value="">—</option>{block.contrasts.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
              <label className="field-label">Endpoint<select aria-label="Count endpoint" value={countDraft.scope.endpoint_id ?? ""} onChange={(event) => setCountDraft(updateScope(countDraft, "endpoint_id", event.target.value))}><option value="">—</option>{block.endpoints.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              {(["group_or_level", "timepoint", "population", "condition"] as const).map((field) => <label className="field-label" key={field}>{field}<input aria-label={`Count ${field}`} value={countDraft.scope[field] ?? ""} onChange={(event) => setCountDraft(updateScope(countDraft, field, event.target.value))} /></label>)}
            </div>
          </fieldset>
          <p className="muted">{countDraft.diagnostic_only ? "diagnostic_only · non replication" : "physical/scoped count"} · evidence {countDraft.evidence_ids.join(", ") || "—"}</p>
        </div>
      )}

      {target === "exclusion" && exclusionDraft && (
        <div className="canonical-fields">
          <label className="field-label">ExclusionRecord
            <select aria-label="ExclusionRecord" value={exclusionIndex} onChange={(event) => setExclusionIndex(Number(event.target.value))}>
              {block.exclusion_records.map((record, index) => <option key={record.id} value={index}>{record.unit_type} · {record.id}</option>)}
            </select>
          </label>
          <div className="field-grid">
            <label className="field-label">Unit type<input aria-label="Exclusion unit type" value={exclusionDraft.unit_type} onChange={(event) => setExclusionDraft({ ...exclusionDraft, unit_type: event.target.value })} /></label>
            <label className="field-label">Phase<select aria-label="Exclusion phase" value={exclusionDraft.phase} onChange={(event) => setExclusionDraft(updateExclusionState(exclusionDraft, "phase", event.target.value as ExclusionRecord["phase"]))}>{PHASES.map((phase) => <option key={phase}>{phase}</option>)}</select></label>
            <label className="field-label">Prespecified<select aria-label="Exclusion prespecified" value={exclusionDraft.prespecified} onChange={(event) => setExclusionDraft(updateExclusionState(exclusionDraft, "prespecified", event.target.value as ExclusionRecord["prespecified"]))}>{["TRUE", "FALSE", "UNKNOWN"].map((value) => <option key={value}>{value}</option>)}</select></label>
            <label className="field-label">Endpoint<select aria-label="Exclusion endpoint" value={exclusionDraft.endpoint_id ?? ""} onChange={(event) => setExclusionDraft(updateExclusion(exclusionDraft, "endpoint_id", event.target.value))}><option value="">—</option>{block.endpoints.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="field-label">Factor<select aria-label="Exclusion factor" value={exclusionDraft.factor_id ?? ""} onChange={(event) => setExclusionDraft({ ...exclusionDraft, factor_id: event.target.value || null })}><option value="">—</option>{block.factors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label className="field-label">Contrast<select aria-label="Exclusion contrast" value={exclusionDraft.contrast_id ?? ""} onChange={(event) => setExclusionDraft({ ...exclusionDraft, contrast_id: event.target.value || null })}><option value="">—</option>{block.contrasts.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
            <label className="field-label">unit_id<input aria-label="Exclusion unit_id" value={exclusionDraft.unit_id ?? ""} onChange={(event) => setExclusionDraft({ ...exclusionDraft, unit_id: event.target.value || null })} /></label>
            {(["group", "author_role", "reason", "impact"] as const).map((field) => <label className="field-label" key={field}>{field}<input aria-label={`Exclusion ${field}`} value={exclusionDraft[field] ?? ""} onChange={(event) => setExclusionDraft(updateExclusion(exclusionDraft, field, event.target.value))} /></label>)}
          </div>
          <p className="muted">evidence {exclusionDraft.evidence_ids.join(", ") || "—"}</p>
        </div>
      )}

      <ReasonFields language={language} reason={reason} rationale={rationale} onReason={setReason} onRationale={setRationale} />
      <div className="correction-footnote">Linked evidence: {evidence?.id ?? "—"}</div>
      <div className="form-actions">
        <span className="candidate-note"><Sparkles size={15} /> {isDemo ? "Demo non scientifica" : "Candidate annotation, not gold"}</span>
        <button className="button primary compact" disabled={busy || !changed || !draftValid || rationale.trim().length < 8}>
          {busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />} {language === "it" ? "Applica e ricalcola" : "Apply and recalculate"}
        </button>
      </div>
    </form>
  );
}
