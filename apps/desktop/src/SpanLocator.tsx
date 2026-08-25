import { useCallback, useMemo, useState } from "react";
import { Crosshair } from "lucide-react";
import type { EvidenceSpan } from "./types";

/**
 * Visual locator for EvidenceSpan corrections (PRD v9 review workflow).
 *
 * The reviewer selects a substring of the linked evidence text with two clicks
 * (start anchor, then end anchor). Offsets are ABSOLUTE document coordinates:
 * they are anchored to the evidence span start, so a refined locator always
 * points inside the original evidence. Nothing is mutated client-side: the
 * refinement is returned to the caller and travels inside the append-only
 * correction record for backend source-validation.
 */

export interface SpanRefinement {
  span_id: string;
  /** Absolute document offset of the first selected character. */
  start: number;
  /** Absolute document offset one past the last selected character. */
  end: number;
  /** Exact selected substring, re-validated against the evidence text. */
  text: string;
  /** Human- and machine-readable locator in the project's canonical format. */
  locator: string;
}

interface SpanLocatorProps {
  evidence: EvidenceSpan;
  language: "it" | "en";
  onApply?: (refinement: SpanRefinement) => void;
}

function baseOffset(evidence: EvidenceSpan): number {
  return typeof evidence.start === "number" ? evidence.start : 0;
}

export function evidenceLocatorLabel(
  evidence: EvidenceSpan,
  start: number,
  end: number,
): string {
  const scope = evidence.section_title || evidence.section_id || "doc";
  return `${scope}:${start}-${end}`;
}

export function buildRefinement(
  evidence: EvidenceSpan,
  relativeStart: number,
  relativeEnd: number,
): SpanRefinement | null {
  if (!Number.isInteger(relativeStart) || !Number.isInteger(relativeEnd)) return null;
  if (relativeStart < 0 || relativeEnd <= relativeStart) return null;
  const text = evidence.text;
  if (relativeEnd > text.length) return null;
  const selected = text.slice(relativeStart, relativeEnd);
  if (selected.trim().length === 0) return null;
  const offset = baseOffset(evidence);
  return {
    span_id: evidence.id,
    start: offset + relativeStart,
    end: offset + relativeEnd,
    text: selected,
    locator: evidenceLocatorLabel(evidence, offset + relativeStart, offset + relativeEnd),
  };
}

export function SpanLocator({ evidence, language, onApply }: SpanLocatorProps) {
  const [anchor, setAnchor] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [refinement, setRefinement] = useState<SpanRefinement | null>(null);

  const chars = useMemo(() => Array.from(evidence.text), [evidence.text]);

  const clickChar = useCallback(
    (index: number) => {
      if (anchor === null) {
        setAnchor(index);
        setRefinement(null);
        return;
      }
      const built =
        index >= anchor ? buildRefinement(evidence, anchor, index + 1) : buildRefinement(evidence, index, anchor + 1);
      setAnchor(null);
      setHover(null);
      setRefinement(built);
    },
    [anchor, evidence],
  );

  const labels = {
    title: language === "it" ? "Selettore visivo dello span" : "Visual span selector",
    hint:
      language === "it"
        ? "Primo clic: inizio · secondo clic: fine. Gli offset sono assoluti nel documento."
        : "First click: start · second click: end. Offsets are absolute in the document.",
    pending: language === "it" ? "inizio…" : "start…",
    apply: language === "it" ? "Usa come evidenza della correzione" : "Use as correction evidence",
    none: language === "it" ? "nessuna selezione" : "no selection",
  };

  const rangePreview = (() => {
    if (anchor !== null && hover !== null && hover !== anchor) {
      const lo = Math.min(anchor, hover);
      const hi = Math.max(anchor, hover);
      const built = buildRefinement(evidence, lo, hi + 1);
      return built?.locator ?? labels.pending;
    }
    if (anchor !== null) return `${labels.pending} @${baseOffset(evidence) + anchor}`;
    return refinement ? refinement.locator : labels.none;
  })();

  return (
    <div className="span-locator" data-testid="span-locator">
      <div className="span-locator-head">
        <Crosshair size={15} aria-hidden />
        <span>{labels.title}</span>
        <code className="span-locator-range" data-testid="span-locator-range">
          {rangePreview}
        </code>
      </div>
      <p className="muted span-locator-hint">{labels.hint}</p>
      <div className="span-locator-text" role="textbox" aria-label={labels.title} tabIndex={0}>
        {chars.map((char, index) => {
          const highlighted =
            (anchor !== null &&
              hover !== null &&
              index >= Math.min(anchor, hover) &&
              index <= Math.max(anchor, hover)) ||
            (refinement !== null &&
              index >= refinement.start - baseOffset(evidence) &&
              index < refinement.end - baseOffset(evidence));
          return (
            <span
              key={`${index}-${char}`}
              className={`span-char${highlighted ? " highlighted" : ""}${index === anchor ? " anchor" : ""}`}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
              onClick={() => clickChar(index)}
            >
              {char}
            </span>
          );
        })}
      </div>
      {refinement !== null && onApply !== undefined && (
        <button type="button" className="button compact" onClick={() => onApply(refinement)}>
          {labels.apply}
        </button>
      )}
    </div>
  );
}

/** RFC-6902-style audit entry appended to the immutable correction patch. */
export function refinementPatchEntry(refinement: SpanRefinement): Record<string, unknown> {
  return {
    op: "ntruth.evidence_span.refine",
    span_id: refinement.span_id,
    start: refinement.start,
    end: refinement.end,
    text: refinement.text,
    locator: refinement.locator,
  };
}
