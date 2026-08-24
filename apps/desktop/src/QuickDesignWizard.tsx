import { Check, ChevronLeft, ChevronRight, Download, LoaderCircle } from "lucide-react";
import { useMemo, useState } from "react";

import {
  ApiError,
  apiErrorCode,
  apiErrorIssueId,
  buildQuickDesignSubmission,
} from "./api";
import type {
  GuidedAnswerStatus,
  GuidedIdSetAnswer,
  GuidedQuickDesignBuildResponse,
  GuidedQuickDesignDraft,
  GuidedTextAnswer,
  ProspectiveArtifactV8,
  QuickDesignV8Response,
} from "./types";

type EditableAnswer = {
  status: GuidedAnswerStatus;
  value: string;
  rationale: string;
};

const emptyAnswer = (): EditableAnswer => ({
  status: "PROVIDED",
  value: "",
  rationale: "",
});

function reviewedText(answer: EditableAnswer): GuidedTextAnswer {
  return answer.status === "PROVIDED"
    ? { status: "PROVIDED", value: answer.value.trim() }
    : { status: "NOT_AVAILABLE", rationale: answer.rationale.trim() };
}

function reviewedIds(answer: EditableAnswer): GuidedIdSetAnswer {
  return answer.status === "PROVIDED"
    ? {
        status: "PROVIDED",
        values: answer.value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      }
    : { status: "NOT_AVAILABLE", rationale: answer.rationale.trim() };
}

function completeAnswer(answer: EditableAnswer): boolean {
  return answer.status === "PROVIDED"
    ? Boolean(answer.value.trim())
    : Boolean(answer.rationale.trim());
}

function AnswerField({
  label,
  answer,
  onChange,
  disabled = false,
}: {
  label: string;
  answer: EditableAnswer;
  onChange: (answer: EditableAnswer) => void;
  disabled?: boolean;
}) {
  return (
    <div className="guided-answer">
      <label className="field-label">
        {label} · stato
        <select
          aria-label={`${label} stato`}
          disabled={disabled}
          value={answer.status}
          onChange={(event) =>
            onChange({
              status: event.target.value as GuidedAnswerStatus,
              value: "",
              rationale: "",
            })
          }
        >
          <option value="PROVIDED">Presente · PROVIDED</option>
          <option value="NOT_AVAILABLE">Non disponibile · NOT_AVAILABLE</option>
        </select>
      </label>
      <label className="field-label">
        {answer.status === "PROVIDED" ? label : `${label} · rationale`}
        <input
          aria-label={answer.status === "PROVIDED" ? label : `${label} rationale`}
          disabled={disabled}
          value={answer.status === "PROVIDED" ? answer.value : answer.rationale}
          onChange={(event) =>
            onChange({
              ...answer,
              [answer.status === "PROVIDED" ? "value" : "rationale"]:
                event.target.value,
            })
          }
        />
      </label>
    </div>
  );
}

export function downloadProspectiveArtifact(artifact: ProspectiveArtifactV8): void {
  const blob = new Blob([artifact.content], { type: artifact.media_type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${artifact.kind.toLowerCase()}-${artifact.content_checksum.slice(0, 12)}`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function scientificError(error: unknown, language: "it" | "en"): string {
  if (
    error instanceof ApiError &&
    error.status === 409 &&
    apiErrorCode(error) === "SCIENTIFIC_REVIEW_REQUIRED"
  ) {
    const issue = apiErrorIssueId(error);
    return `${language === "it" ? "Revisione scientifica richiesta" : "Scientific review required"}${issue ? ` · ${issue}` : ""}. ${error.message}`;
  }
  return error instanceof Error
    ? error.message
    : language === "it"
      ? "Compilazione non completata."
      : "Compilation did not complete.";
}

export function QuickDesignWizard({
  language,
  onComplete,
  initialStep = 1,
}: {
  language: "it" | "en";
  onComplete: (response: QuickDesignV8Response) => void;
  initialStep?: number;
}) {
  const [step, setStep] = useState(initialStep);
  const [blockTitle, setBlockTitle] = useState("");
  const [source, setSource] = useState(emptyAnswer);
  const [preparation, setPreparation] = useState(emptyAnswer);
  const [biologicalSourceUnit, setBiologicalSourceUnit] = useState(emptyAnswer);
  const [candidateUnit, setCandidateUnit] = useState(emptyAnswer);
  const [factor, setFactor] = useState("");
  const [factorLevels, setFactorLevels] = useState("");
  const [contrast, setContrast] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [timepoint, setTimepoint] = useState("");
  const [estimand, setEstimand] = useState("");
  const [population, setPopulation] = useState("");
  const [inferenceLevel, setInferenceLevel] = useState("");
  const [assignmentUnit, setAssignmentUnit] = useState(emptyAnswer);
  const [assignmentIds, setAssignmentIds] = useState(emptyAnswer);
  const [applicationUnit, setApplicationUnit] = useState(emptyAnswer);
  const [applicationIds, setApplicationIds] = useState(emptyAnswer);
  const [intervention, setIntervention] = useState(emptyAnswer);
  const [exposureUnit, setExposureUnit] = useState(emptyAnswer);
  const [exposedIds, setExposedIds] = useState(emptyAnswer);
  const [exposurePathway, setExposurePathway] = useState(emptyAnswer);
  const [exposureContainer, setExposureContainer] = useState(emptyAnswer);
  const [interference, setInterference] = useState<"UNKNOWN" | "POSSIBLE">("UNKNOWN");
  const [interferenceRationale, setInterferenceRationale] = useState("");
  const [timing, setTiming] = useState<
    "BEFORE" | "AFTER" | "SAME_EVENT" | "OVERLAPS" | "UNKNOWN"
  >("UNKNOWN");
  const [timingRationale, setTimingRationale] = useState("");
  const [plannedUnit, setPlannedUnit] = useState(emptyAnswer);
  const [groups, setGroups] = useState([
    { groupId: "", cohort: emptyAnswer(), factorLevel: "", count: 1 },
    { groupId: "", cohort: emptyAnswer(), factorLevel: "", count: 1 },
  ]);
  const [preview, setPreview] = useState<GuidedQuickDesignBuildResponse>();
  const [reviewFocusPredicate, setReviewFocusPredicate] = useState("");
  const [actorRole, setActorRole] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const factorLevelValues = useMemo(
    () =>
      factorLevels
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    [factorLevels],
  );

  const stepComplete = {
    1: Boolean(blockTitle.trim()),
    2: [source, preparation, biologicalSourceUnit, candidateUnit].every(completeAnswer),
    3:
      [factor, contrast, endpoint, timepoint, estimand, population, inferenceLevel].every(
        (item) => Boolean(item.trim()),
      ) && factorLevelValues.length >= 2,
    4:
      [
        assignmentUnit,
        assignmentIds,
        applicationUnit,
        applicationIds,
        intervention,
        exposureUnit,
        exposedIds,
        exposurePathway,
        exposureContainer,
      ].every(completeAnswer) &&
      Boolean(interferenceRationale.trim()) &&
      (timing !== "UNKNOWN" || Boolean(timingRationale.trim())),
    5:
      completeAnswer(plannedUnit) &&
      groups.every(
        (group) =>
          Boolean(group.groupId.trim()) &&
          completeAnswer(group.cohort) &&
          Boolean(group.factorLevel.trim()) &&
          group.count >= 1,
      ),
  }[step];

  const draft = (): GuidedQuickDesignDraft => ({
    template_id: "simple_cell_culture",
    block_title: blockTitle.trim(),
    source_description: reviewedText(source),
    preparation_description: reviewedText(preparation),
    biological_source_unit_type: reviewedText(biologicalSourceUnit),
    candidate_unit_type: reviewedText(candidateUnit),
    factor_id: factor.trim(),
    factor_levels: factorLevelValues,
    contrast_id: contrast.trim(),
    endpoint_id: endpoint.trim(),
    timepoint_id: timepoint.trim(),
    estimand: estimand.trim(),
    population_scope: population.trim(),
    inference_level: inferenceLevel.trim(),
    assignment_unit_type: reviewedText(assignmentUnit),
    assignment_unit_ids: reviewedIds(assignmentIds),
    application_unit_type: reviewedText(applicationUnit),
    application_unit_ids: reviewedIds(applicationIds),
    intervention_id: reviewedText(intervention),
    effective_exposure_unit_type: reviewedText(exposureUnit),
    exposed_unit_ids: reviewedIds(exposedIds),
    exposure_pathway: reviewedText(exposurePathway),
    exposure_container: reviewedText(exposureContainer),
    interference: {
      status: interference,
      rationale: interferenceRationale.trim(),
    },
    assignment_to_application_timing:
      timing === "UNKNOWN"
        ? { status: "NOT_AVAILABLE", rationale: timingRationale.trim() }
        : { status: "PROVIDED", relation: timing },
    planned_unit_type: reviewedText(plannedUnit),
    planned_groups: groups.map((group) => ({
      group_id: group.groupId.trim(),
      cohort_id: reviewedText(group.cohort),
      factor_level: group.factorLevel.trim(),
      planned_count: group.count,
    })),
  });

  const generatePreview = async () => {
    setBusy(true);
    setError(undefined);
    try {
      const response = await buildQuickDesignSubmission({
        action: "PREVIEW",
        draft: draft(),
      });
      setPreview(response);
      setReviewFocusPredicate("");
      setReviewed(false);
    } catch (caught) {
      setError(scientificError(caught, language));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!preview || !reviewFocusPredicate || !reviewed) return;
    setBusy(true);
    setError(undefined);
    try {
      const confirmed = await buildQuickDesignSubmission({
        action: "CONFIRM",
        draft: draft(),
        confirmation: {
          preview_checksum: preview.preview_checksum,
          review_focus_predicate_id: reviewFocusPredicate,
          actor_role: actorRole.trim(),
          confirmed_at: new Date().toISOString(),
        },
      });
      const result = confirmed.canonical_result.value;
      if (!result) {
        throw new Error("BUILT response did not contain the atomic canonical result.");
      }
      onComplete(result);
    } catch (caught) {
      setError(scientificError(caught, language));
    } finally {
      setBusy(false);
    }
  };

  const textField = (
    label: string,
    value: string,
    setValue: (value: string) => void,
    disabled = false,
  ) => (
    <label className="field-label">
      {label}
      <input
        aria-label={label}
        disabled={disabled}
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
    </label>
  );

  return (
    <section className="guided-wizard" aria-label="Quick Design v8 guided builder">
      <div className="guided-progress" aria-label="Avanzamento Quick Design">
        <strong>Passo {step} di 5</strong>
        <span>{["Blocco", "Fonte e unità", "Query", "Eventi", "Piano e review"][step - 1]}</span>
        <progress max={5} value={step} />
      </div>

      {step === 1 && (
        <div className="guided-step">
          <label className="field-label">
            Template
            <select aria-label="Template" value="simple_cell_culture" disabled>
              <option value="simple_cell_culture">simple_cell_culture</option>
            </select>
          </label>
          {textField("Titolo del blocco", blockTitle, setBlockTitle)}
        </div>
      )}

      {step === 2 && (
        <div className="guided-step guided-grid">
          <AnswerField label="Descrizione della fonte" answer={source} onChange={setSource} />
          <AnswerField label="Preparazione" answer={preparation} onChange={setPreparation} />
          <AnswerField
            label="Tipo unità della fonte biologica"
            answer={biologicalSourceUnit}
            onChange={setBiologicalSourceUnit}
          />
          <AnswerField label="Unità candidata" answer={candidateUnit} onChange={setCandidateUnit} />
        </div>
      )}

      {step === 3 && (
        <div className="guided-step guided-grid">
          {textField("Fattore", factor, setFactor)}
          {textField("Livelli del fattore", factorLevels, setFactorLevels)}
          {textField("Contrasto", contrast, setContrast)}
          {textField("Endpoint", endpoint, setEndpoint)}
          {textField("Timepoint", timepoint, setTimepoint)}
          {textField("Estimand", estimand, setEstimand)}
          {textField("Popolazione", population, setPopulation)}
          {textField("Livello inferenziale", inferenceLevel, setInferenceLevel)}
        </div>
      )}

      {step === 4 && (
        <div className="guided-step guided-grid">
          <AnswerField
            label="Tipo unità di assegnazione"
            answer={assignmentUnit}
            onChange={setAssignmentUnit}
          />
          <AnswerField
            label="ID unità di assegnazione"
            answer={assignmentIds}
            onChange={setAssignmentIds}
          />
          <AnswerField
            label="Tipo unità di applicazione"
            answer={applicationUnit}
            onChange={setApplicationUnit}
          />
          <AnswerField
            label="ID unità di applicazione"
            answer={applicationIds}
            onChange={setApplicationIds}
          />
          <AnswerField label="Intervento" answer={intervention} onChange={setIntervention} />
          <AnswerField
            label="Tipo unità di esposizione effettiva"
            answer={exposureUnit}
            onChange={setExposureUnit}
          />
          <AnswerField label="ID unità esposte" answer={exposedIds} onChange={setExposedIds} />
          <AnswerField
            label="Percorso di esposizione"
            answer={exposurePathway}
            onChange={setExposurePathway}
          />
          <AnswerField
            label="Contenitore di esposizione"
            answer={exposureContainer}
            onChange={setExposureContainer}
          />
          <label className="field-label">
            Interferenza
            <select
              aria-label="Interferenza"
              value={interference}
              onChange={(event) => setInterference(event.target.value as "UNKNOWN" | "POSSIBLE")}
            >
              <option value="UNKNOWN">UNKNOWN</option>
              <option value="POSSIBLE">POSSIBLE</option>
            </select>
          </label>
          {textField("Razionale interferenza", interferenceRationale, setInterferenceRationale)}
          <label className="field-label">
            Timing assegnazione rispetto all&apos;applicazione
            <select
              aria-label="Timing assegnazione rispetto all'applicazione"
              value={timing}
              onChange={(event) =>
                setTiming(event.target.value as typeof timing)
              }
            >
              <option value="UNKNOWN">UNKNOWN</option>
              <option value="BEFORE">BEFORE</option>
              <option value="AFTER">AFTER</option>
              <option value="SAME_EVENT">SAME_EVENT</option>
              <option value="OVERLAPS">OVERLAPS</option>
            </select>
          </label>
          {timing === "UNKNOWN" &&
            textField("Razionale timing sconosciuto", timingRationale, setTimingRationale)}
        </div>
      )}

      {step === 5 && (
        <div className="guided-step">
          <AnswerField
            label="Tipo unità pianificata"
            answer={plannedUnit}
            onChange={setPlannedUnit}
            disabled={Boolean(preview)}
          />
          <div className="guided-groups" aria-label="Gruppi e conteggi pianificati">
            {groups.map((group, index) => (
              <div className="guided-group-row" key={`planned-group-${index + 1}`}>
                {textField(
                  `Gruppo ${index + 1}`,
                  group.groupId,
                  (value) =>
                    setGroups((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, groupId: value } : item,
                      ),
                    ),
                  Boolean(preview),
                )}
                <AnswerField
                  label={`Coorte gruppo ${index + 1}`}
                  answer={group.cohort}
                  disabled={Boolean(preview)}
                  onChange={(cohort) =>
                    setGroups((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, cohort } : item,
                      ),
                    )
                  }
                />
                {textField(
                  `Livello gruppo ${index + 1}`,
                  group.factorLevel,
                  (value) =>
                    setGroups((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, factorLevel: value } : item,
                      ),
                    ),
                  Boolean(preview),
                )}
                <label className="field-label">
                  Conteggio gruppo {index + 1}
                  <input
                    aria-label={`Conteggio gruppo ${index + 1}`}
                    type="number"
                    min={1}
                    disabled={Boolean(preview)}
                    value={group.count}
                    onChange={(event) =>
                      setGroups((current) =>
                        current.map((item, itemIndex) =>
                          itemIndex === index
                            ? { ...item, count: Number(event.target.value) }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
              </div>
            ))}
          </div>

          {!preview ? (
            <button
              type="button"
              className="button primary"
              disabled={!stepComplete || busy}
              onClick={generatePreview}
            >
              {busy ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}
              Genera anteprima verificabile
            </button>
          ) : (
            <section className="guided-review" aria-label="Review anteprima Quick Design">
              <p className="preview-authority" data-testid="preview-authority">
                {language === "it"
                  ? "Anteprima client non canonica. Non è il risultato Python e non approva il disegno."
                  : "Non-canonical client preview. Not the Python result and not design approval."}
              </p>
              <div className="v8-contract-pins">
                <span>{preview.summary.scenario_coverage_status}</span>
                <span>{preview.summary.strategy_module_status}</span>
                <span>{preview.state}</span>
              </div>
              <dl className="v8-definition-grid">
                <div><dt>Block</dt><dd>{preview.summary.experiment_block_id}</dd></div>
                <div><dt>Query</dt><dd>{preview.summary.inferential_query_id}</dd></div>
                <div><dt>Planned units</dt><dd>{preview.summary.planned_unit_total}</dd></div>
                <div><dt>Checksum</dt><dd><code>{preview.preview_checksum}</code></dd></div>
                <div>
                  <dt>Provided fields</dt>
                  <dd>{preview.summary.provided_field_ids.join(" · ") || "—"}</dd>
                </div>
                <div>
                  <dt>Unknown fields</dt>
                  <dd>{preview.summary.unknown_field_ids.join(" · ") || "—"}</dd>
                </div>
                <div>
                  <dt>Known profile gaps</dt>
                  <dd>{preview.summary.known_profile_gaps.join(" · ")}</dd>
                </div>
              </dl>
              <fieldset className="guided-questions">
                <legend>Scegli un focus di review tra i predicate Theory-derived</legend>
                {preview.visible_questions.map((question) => (
                  <label key={question.question_id}>
                    <input
                      type="radio"
                      name="review-focus-theory-question"
                      aria-label={question.text}
                      checked={reviewFocusPredicate === question.predicate_id}
                      onChange={() => setReviewFocusPredicate(question.predicate_id)}
                    />
                    <span>
                      <strong>{question.text}</strong>
                      <small>{question.theory_clause_ids.join(" · ")}</small>
                      <small>
                        {question.priority_state} · {question.priority_review.issue_id} · {question.priority_review.status}
                      </small>
                      <small>{question.priority_review.rationale}</small>
                      <small>
                        evidence request: {question.evidence_required.knowledge_state}
                        {question.evidence_required.rationale
                          ? ` · ${question.evidence_required.rationale}`
                          : ""}
                      </small>
                      {question.known_gap_rationales.map((rationale) => (
                        <small key={rationale}>{rationale}</small>
                      ))}
                    </span>
                  </label>
                ))}
              </fieldset>
              <details>
                <summary>Coda completa · {preview.question_queue.length}</summary>
                <ul>
                  {preview.question_queue.map((question) => (
                    <li key={question.question_id}>
                      <code>{question.predicate_id}</code> · {question.text}
                    </li>
                  ))}
                </ul>
              </details>
              <div className="guided-artifacts">
                {preview.artifact_previews.map((artifact) => (
                  <button
                    type="button"
                    className="button secondary compact"
                    key={artifact.artifact_id}
                    aria-label={`Scarica ${artifact.kind}`}
                    onClick={() => downloadProspectiveArtifact(artifact)}
                  >
                    <Download size={15} /> Scarica {artifact.kind}
                  </button>
                ))}
              </div>
              {textField("Ruolo del revisore", actorRole, setActorRole)}
              <label className="acknowledge">
                <input
                  type="checkbox"
                  checked={reviewed}
                  onChange={(event) => setReviewed(event.target.checked)}
                />
                Ho revisionato questa esatta anteprima
              </label>
              <button
                type="button"
                className="button primary"
                disabled={!reviewFocusPredicate || !reviewed || !actorRole.trim() || busy}
                onClick={confirm}
              >
                {busy ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />}
                Conferma e compila PRD v8
              </button>
            </section>
          )}
        </div>
      )}

      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="guided-navigation">
        <button
          type="button"
          className="button secondary"
          disabled={step === 1 || busy}
          onClick={() => {
            setStep((current) => Math.max(1, current - 1));
            setPreview(undefined);
          }}
        >
          <ChevronLeft size={17} /> Indietro
        </button>
        {step < 5 && (
          <button
            type="button"
            className="button primary"
            disabled={!stepComplete || busy}
            onClick={() => setStep((current) => Math.min(5, current + 1))}
          >
            Continua <ChevronRight size={17} />
          </button>
        )}
      </div>
    </section>
  );
}
