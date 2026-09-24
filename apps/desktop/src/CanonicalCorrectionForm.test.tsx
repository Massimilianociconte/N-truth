import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CanonicalCorrectionForm } from "./CanonicalCorrectionForm";
import { DEMO_REPORT } from "./data/demo";
import type { CountRecord, ExclusionRecord, ExperimentBlock } from "./types";

function blockWithUnreportedCount(): ExperimentBlock {
  const base = DEMO_REPORT.blocks[0];
  const count: CountRecord = {
    count_id: "count-unreported",
    kind: "observed_n",
    value: null,
    quantifier: "NOT_REPORTED",
    lower_bound: null,
    upper_bound: null,
    scope: {
      unit_type: "Animal",
      factor_id: base.factors[0].id,
      contrast_id: base.contrasts[0].id,
      group_or_level: base.factors[0].levels[0],
      endpoint_id: base.endpoints[0].id,
      lifecycle: "observed",
      timepoint: null,
      population: null,
      condition: null,
      unknown_reasons: {
        timepoint: "not reported",
      },
    },
    evidence_ids: [base.evidence[0].id],
    rule_trace_ids: [],
    diagnostic_only: false,
    provenance: {
      origin: "explicit",
      evidence_ids: [base.evidence[0].id],
    },
  };
  return { ...base, count_records: [count] };
}

function blockWithExclusion(): ExperimentBlock {
  const base = DEMO_REPORT.blocks[0];
  const exclusion: ExclusionRecord = {
    id: "exclusion-reviewed",
    unit_id: base.hierarchy.nodes[0].id,
    unit_type: base.hierarchy.nodes[0].type,
    phase: "post_measurement",
    prespecified: "FALSE",
    endpoint_id: base.endpoints[0].id,
    factor_id: base.factors[0].id,
    contrast_id: base.contrasts[0].id,
    group: base.factors[0].levels[0],
    author_role: "wet_lab_reviewer",
    reason: "quality-control failure",
    impact: "removed from analysed_n",
    evidence_ids: [base.evidence[0].id],
    unknown_reasons: {},
    provenance: {
      origin: "user",
      evidence_ids: [base.evidence[0].id],
      actor_role: "wet_lab_reviewer",
    },
  };
  return { ...base, count_records: [], exclusion_records: [exclusion] };
}

describe("CanonicalCorrectionForm", () => {
  it("never invents zero when a missing count becomes numeric", () => {
    const onApply = vi.fn();
    render(
      <CanonicalCorrectionForm
        block={blockWithUnreportedCount()}
        language="it"
        isDemo={false}
        onApply={onApply}
      />,
    );

    fireEvent.change(screen.getByLabelText("Count quantifier"), {
      target: { value: "EXACT" },
    });

    expect(screen.getByLabelText("Count value")).toHaveValue(null);
    expect(screen.getByRole("alert")).toHaveTextContent("non presume zero");
    fireEvent.change(screen.getByPlaceholderText(/Cita la fonte/), {
      target: { value: "Conteggio verificato nella fonte primaria." },
    });
    const apply = screen.getByRole("button", { name: /Applica e ricalcola/ });
    expect(apply).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Count value"), { target: { value: "0" } });
    expect(apply).toBeEnabled();
  });

  it("requires both range bounds instead of pre-filling them", () => {
    render(
      <CanonicalCorrectionForm
        block={blockWithUnreportedCount()}
        language="en"
        isDemo={false}
        onApply={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("Count quantifier"), {
      target: { value: "RANGE" },
    });

    expect(screen.getByLabelText("Count lower bound")).toHaveValue(null);
    expect(screen.getByLabelText("Count upper bound")).toHaveValue(null);
    expect(screen.getByRole("alert")).toHaveTextContent("never assumes zero");
  });

  it("records explicit reason codes when exclusion audit fields become unknown", () => {
    const onApply = vi.fn();
    render(
      <CanonicalCorrectionForm
        block={blockWithExclusion()}
        language="it"
        isDemo={false}
        onApply={onApply}
      />,
    );

    fireEvent.change(screen.getByLabelText("Exclusion phase"), {
      target: { value: "unknown" },
    });
    fireEvent.change(screen.getByLabelText("Exclusion prespecified"), {
      target: { value: "UNKNOWN" },
    });
    fireEvent.change(screen.getByPlaceholderText(/Cita la fonte/), {
      target: { value: "La fonte non riporta fase o preregistrazione." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Applica e ricalcola/ }));

    const patch = onApply.mock.calls[0][0] as Array<{ value: ExclusionRecord }>;
    expect(patch[0].value.phase).toBe("unknown");
    expect(patch[0].value.prespecified).toBe("UNKNOWN");
    expect(patch[0].value.unknown_reasons).toMatchObject({
      phase: "not reported after human review",
      prespecified: "not reported after human review",
    });
  });
});
