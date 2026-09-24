import { fieldId, type D0FieldTarget, type D0ValidationIssue } from "./validation";
import { rowLocator } from "./rowHelpers";
import type { D0Language } from "./types";

export function ValidationSummary({ issues, language, onNavigate }: {
  issues: D0ValidationIssue[];
  language: D0Language;
  onNavigate: (target: D0FieldTarget) => void;
}) {
  if (!issues.length) return null;
  return <ul>{issues.map((issue) => <li key={issue.id}>
    <span id={issue.id}>{issue.message}</span>
    {issue.targets.map((target) => <button
      type="button" className="link-button" key={fieldId(target)}
      aria-label={`${issue.message} · ${target.step === "samples" ? `row ${target.row + 1} · ` : ""}${target.field}`}
      onClick={() => onNavigate(target)}
    >{language === "it" ? "Vai a" : "Go to"} {target.field}{target.step === "samples" ? ` · ${rowLocator(target.row)}` : ""}</button>)}
  </li>)}</ul>;
}
