import {
  AlertTriangle,
  ArrowDownToLine,
  Beaker,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  Database,
  Download,
  FileText,
  FolderOpen,
  GitBranch,
  History,
  Info,
  Languages,
  Link2,
  LoaderCircle,
  PencilLine,
  Redo2,
  RotateCcw,
  Save,
  Search,
  Settings,
  ShieldAlert,
  Sparkles,
  Undo2,
  Upload,
  X,
  ZoomIn,
  type LucideIcon,
} from "lucide-react";
import {
  type FormEvent,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  ApiError,
  analyze,
  applyCorrection,
  confirmInferenceTarget,
  downloadJson,
  health,
  navigateCorrection,
  preflight,
  type InferenceTargetDraft,
} from "./api";
import { DEMO_REPORT } from "./data/demo";
import type {
  Alert,
  AnalysisResponse,
  AuditEntry,
  BlockPositiveOutput,
  DesignCompilation,
  EvidenceSpan,
  ExperimentBlock,
  GraphNode,
  GraphRelation,
  PrivacyAudit,
  Report,
  Severity,
  ShareReadiness,
} from "./types";

type Icon = LucideIcon;
type View =
  | "project"
  | "documents"
  | "experiments"
  | "graph"
  | "questions"
  | "corrections"
  | "export";

const NAVIGATION: Array<{ id: View; it: string; en: string; icon: Icon }> = [
  { id: "project", it: "Progetto", en: "Project", icon: FolderOpen },
  { id: "documents", it: "Documenti", en: "Documents", icon: FileText },
  { id: "experiments", it: "Esperimenti", en: "Experiments", icon: Beaker },
  { id: "graph", it: "Grafo", en: "Graph", icon: GitBranch },
  { id: "questions", it: "Elicitazione", en: "Elicitation", icon: CircleHelp },
  { id: "corrections", it: "Correzioni", en: "Corrections", icon: PencilLine },
  { id: "export", it: "Esporta", en: "Export", icon: ArrowDownToLine },
];

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critica",
  high: "Alta",
  medium: "Media",
  insufficient: "Informazioni insufficienti",
  info: "Informativa",
};

const NODE_LABEL: Record<string, string> = {
  Animal: "Animale",
  HumanDonor: "Donatore",
  PrimarySample: "Campione",
  CellCulture: "Coltura",
  Treatment: "Trattamento",
  FactorLevel: "Livello",
  Endpoint: "Endpoint",
  Well: "Pozzetto",
  Cell: "Cellula",
};

const EDITABLE_NODE_TYPES = [
  "HumanDonor",
  "Animal",
  "Tissue",
  "PrimarySample",
  "CellLine",
  "CellCulture",
  "Organoid",
  "Explant",
  "Aliquot",
  "Plate",
  "Well",
  "Field",
  "ROI",
  "Cell",
  "Batch",
  "Run",
  "Timepoint",
  "Factor",
  "FactorLevel",
  "Endpoint",
  "Estimand",
];

const ALLOCATABLE_NODE_TYPES = [
  "Cohort",
  "Cage",
  "Dam",
  "Litter",
  "HumanDonor",
  "Animal",
  "CellLine",
  "Tissue",
  "PrimarySample",
  "Explant",
  "CellCulture",
  "PrimaryCulture",
  "Organoid",
  "Pool",
  "Aliquot",
  "Plate",
  "Run",
  "Library",
  "Well",
  "Section_",
  "Field",
  "Image",
  "ROI",
  "Object",
  "Cell",
  "Batch",
  "Thaw",
  "Passage",
];

const EDITABLE_RELATION_TYPES = [
  "nested_in",
  "derived_from",
  "split_from",
  "pooled_from",
  "paired_with",
  "matched_with",
  "blocked_by",
  "crossed_with",
  "same_source_as",
  "repeated_measure_of",
  "allocated_to",
  "applied_to",
  "measured_on",
  "belongs_to_group",
  "excluded_from",
  "supports",
  "contradicts",
  "declares_clustering",
];

function evidenceLocator(evidence?: EvidenceSpan): string {
  if (!evidence) return "Evidenza non localizzata";
  if (evidence.cell) {
    const sheet = evidence.cell.sheet ? `${evidence.cell.sheet}!` : "";
    return `${sheet}${evidence.cell.table_id} · riga ${evidence.cell.row + 1} · ${evidence.cell.column}`;
  }
  const section = evidence.section_title || evidence.section_id || evidence.file_id;
  if (evidence.start != null) return `${section} · caratteri ${evidence.start}–${evidence.end ?? "?"}`;
  return section;
}

function focusId(view: View): string {
  return {
    project: "workspace",
    documents: "evidence-panel",
    experiments: "blocks-panel",
    graph: "graph-panel",
    questions: "inference-panel",
    corrections: "correction-panel",
    export: "export-bar",
  }[view];
}

export function App() {
  const [report, setReport] = useState<Report>(DEMO_REPORT);
  const [isDemo, setIsDemo] = useState(true);
  const [activeView, setActiveView] = useState<View>("project");
  const [selectedBlockId, setSelectedBlockId] = useState(DEMO_REPORT.blocks[0].id);
  const [selectedAlertId, setSelectedAlertId] = useState(DEMO_REPORT.blocks[0].alerts[0].id);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string>();
  const [uiLanguage, setUiLanguage] = useState<"it" | "en">("it");
  const [apiState, setApiState] = useState<"checking" | "online" | "offline">("checking");
  const [showImport, setShowImport] = useState(false);
  const [sessionId, setSessionId] = useState<string>();
  const [artifacts, setArtifacts] = useState<Record<string, string>>({});
  const [audit, setAudit] = useState<Record<string, AuditEntry[]>>({});
  const [correctionState, setCorrectionState] = useState<
    Record<string, { active: string[]; redo: string[] }>
  >({});
  const [candidateExports, setCandidateExports] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [privacyAudit, setPrivacyAudit] = useState<PrivacyAudit>();
  const [shareReadiness, setShareReadiness] = useState<ShareReadiness>();
  const [domainAcknowledged, setDomainAcknowledged] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [demoPast, setDemoPast] = useState<Report[]>([]);
  const [demoFuture, setDemoFuture] = useState<Report[]>([]);

  useEffect(() => {
    health()
      .then(() => setApiState("online"))
      .catch(() => setApiState("offline"));
  }, []);

  const selectedBlock =
    report.blocks.find((item) => item.id === selectedBlockId) ?? report.blocks[0];
  const selectedAlert =
    selectedBlock?.alerts.find((item) => item.id === selectedAlertId) ??
    selectedBlock?.alerts[0];
  const selectedEvidence =
    selectedBlock?.evidence.find((item) => item.id === selectedEvidenceId) ??
    (selectedAlert
      ? selectedBlock?.evidence.find((item) => selectedAlert.evidence_ids.includes(item.id))
      : selectedBlock?.evidence[0]);
  const selectedCompilation = selectedBlock
    ? report.design_compilations?.[selectedBlock.id]
    : undefined;
  const selectedCandidateExport = selectedBlock
    ? candidateExports[selectedBlock.id]
    : undefined;

  const storeCandidateExport = (blockId: string, payload: Record<string, unknown>) => {
    setCandidateExports((current) => ({ ...current, [blockId]: payload }));
  };

  const applyGovernanceState = (response: {
    privacy_audit: PrivacyAudit;
    share_readiness: ShareReadiness;
  }) => {
    setPrivacyAudit(response.privacy_audit);
    setShareReadiness(response.share_readiness);
  };

  useEffect(() => {
    if (!selectedBlock) return;
    if (!selectedBlock.alerts.some((item) => item.id === selectedAlertId)) {
      setSelectedAlertId(selectedBlock.alerts[0]?.id ?? "");
    }
  }, [selectedAlertId, selectedBlock]);

  const navigate = (view: View) => {
    setActiveView(view);
    document.getElementById(focusId(view))?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const replaceBlock = (nextBlock: ExperimentBlock) => {
    setReport((current) => ({
      ...current,
      blocks: current.blocks.map((item) => (item.id === nextBlock.id ? nextBlock : item)),
    }));
  };

  const applyDemoCorrection = (
    value: number,
    rationale: string,
    reason: string,
    evidenceIds: string[],
  ) => {
    if (!selectedBlock) return;
    setDemoPast((items) => [...items, report]);
    setDemoFuture([]);
    const sequence = selectedBlock.corrections.length;
    const correctionId = `demo-correction-${sequence + 1}`;
    const nextBlock: ExperimentBlock = {
      ...selectedBlock,
      n_statements: selectedBlock.n_statements.map((statement, index) =>
        index === 0 ? { ...statement, value, raw_text: `n = ${value} per gruppo` } : statement,
      ),
      corrections: [
        ...selectedBlock.corrections,
        {
          id: correctionId,
          sequence,
          reason,
          rationale,
          patch: [{ op: "replace", path: "/n_statements/0/value", value }],
          evidence_ids: evidenceIds,
          reviewer_role: "reviewer",
          verified: false,
        },
      ],
    };
    replaceBlock(nextBlock);
    setAudit((current) => ({
      ...current,
      [selectedBlock.id]: [
        ...(current[selectedBlock.id] ?? []),
        {
          id: `demo-audit-${sequence + 1}`,
          sequence,
          action: "apply",
          correction_id: correctionId,
        },
      ],
    }));
    storeCandidateExport(selectedBlock.id, {
      artifact_type: "ntruth_candidate_annotations",
      gold_status: "not_gold",
      training_eligible: false,
      block_id: selectedBlock.id,
      corrections: nextBlock.corrections,
    });
    setNotice("Correzione dimostrativa applicata come annotazione candidata, mai come gold.");
  };

  const undo = async () => {
    if (!selectedBlock) return;
    if (isDemo) {
      const previous = demoPast.at(-1);
      if (!previous) return;
      const correctionId = selectedBlock.corrections.at(-1)?.id;
      setDemoPast((items) => items.slice(0, -1));
      setDemoFuture((items) => [report, ...items]);
      setReport(previous);
      const previousBlock = previous.blocks.find((item) => item.id === selectedBlock.id);
      setCandidateExports((current) => {
        const next = { ...current };
        if (previousBlock?.corrections.length) {
          next[selectedBlock.id] = {
            artifact_type: "ntruth_candidate_annotations",
            gold_status: "not_gold",
            training_eligible: false,
            block_id: selectedBlock.id,
            corrections: previousBlock.corrections,
          };
        } else {
          delete next[selectedBlock.id];
        }
        return next;
      });
      if (correctionId) {
        setAudit((current) => ({
          ...current,
          [selectedBlock.id]: [
            ...(current[selectedBlock.id] ?? []),
            {
              id: `${correctionId}-undo-${current[selectedBlock.id]?.length ?? 0}`,
              sequence: current[selectedBlock.id]?.length ?? 0,
              action: "undo",
              correction_id: correctionId,
            },
          ],
        }));
      }
      setNotice("Ultima correzione dimostrativa annullata; la storia resta visibile.");
      return;
    }
    if (!sessionId) return;
    try {
      const response = await navigateCorrection("undo", sessionId, selectedBlock.id);
      setReport(response.report);
      applyGovernanceState(response);
      setAudit((current) => ({ ...current, [selectedBlock.id]: response.audit_trail }));
      setCorrectionState((current) => ({
        ...current,
        [selectedBlock.id]: {
          active: response.active_correction_ids,
          redo: response.redo_correction_ids,
        },
      }));
      storeCandidateExport(selectedBlock.id, response.candidate_annotations);
      setNotice(`Ricalcolo completato in ${response.recalculation_ms.toFixed(1)} ms.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Impossibile annullare la correzione.");
    }
  };

  const redo = async () => {
    if (!selectedBlock) return;
    if (isDemo) {
      const next = demoFuture[0];
      if (!next) return;
      const nextBlock = next.blocks.find((item) => item.id === selectedBlock.id);
      const correctionId = nextBlock?.corrections.at(-1)?.id;
      setDemoPast((items) => [...items, report]);
      setDemoFuture((items) => items.slice(1));
      setReport(next);
      if (nextBlock?.corrections.length) {
        storeCandidateExport(selectedBlock.id, {
          artifact_type: "ntruth_candidate_annotations",
          gold_status: "not_gold",
          training_eligible: false,
          block_id: selectedBlock.id,
          corrections: nextBlock.corrections,
        });
      }
      if (correctionId) {
        setAudit((current) => ({
          ...current,
          [selectedBlock.id]: [
            ...(current[selectedBlock.id] ?? []),
            {
              id: `${correctionId}-redo-${current[selectedBlock.id]?.length ?? 0}`,
              sequence: current[selectedBlock.id]?.length ?? 0,
              action: "redo",
              correction_id: correctionId,
            },
          ],
        }));
      }
      setNotice("Correzione dimostrativa ripristinata.");
      return;
    }
    if (!sessionId) return;
    try {
      const response = await navigateCorrection("redo", sessionId, selectedBlock.id);
      setReport(response.report);
      applyGovernanceState(response);
      setAudit((current) => ({ ...current, [selectedBlock.id]: response.audit_trail }));
      setCorrectionState((current) => ({
        ...current,
        [selectedBlock.id]: {
          active: response.active_correction_ids,
          redo: response.redo_correction_ids,
        },
      }));
      storeCandidateExport(selectedBlock.id, response.candidate_annotations);
      setNotice(`Ricalcolo completato in ${response.recalculation_ms.toFixed(1)} ms.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Impossibile ripetere la correzione.");
    }
  };

  const confirmTarget = async (draft: InferenceTargetDraft) => {
    if (!selectedBlock) return;
    if (isDemo) {
      setDemoPast((items) => [...items, report]);
      setDemoFuture([]);
      const existingIndex = draft.target_id
        ? selectedBlock.inference_targets.findIndex((item) => item.id === draft.target_id)
        : -1;
      const existing = existingIndex >= 0 ? selectedBlock.inference_targets[existingIndex] : undefined;
      const targetId = existing?.id ?? `${selectedBlock.id}-user-target`;
      const target = {
        id: targetId,
        question_text: draft.question_text,
        claim_text: draft.claim_text,
        population_of_inference: draft.population_of_inference,
        factor_ids: draft.factor_ids,
        contrast_ids: draft.contrast_ids,
        endpoint_ids: draft.endpoint_ids,
        target_biological_unit: draft.target_biological_unit,
        evidence_ids: draft.evidence_ids,
        status: "user_confirmed" as const,
      };
      const nextEstimands = [...selectedBlock.estimands];
      const estimandUpdates = draft.estimands.map((estimandDraft) => {
        const existingEstimandIndex = selectedBlock.estimands.findIndex(
          (item) =>
            item.id === estimandDraft.estimand_id ||
            (!estimandDraft.estimand_id && item.endpoint_id === estimandDraft.endpoint_id),
        );
        const existingEstimand = selectedBlock.estimands[existingEstimandIndex];
        const estimand = {
          id:
            existingEstimand?.id ??
            `${selectedBlock.id}-user-estimand-${estimandDraft.endpoint_id}`,
          endpoint_id: estimandDraft.endpoint_id,
          effect_measure: estimandDraft.effect_measure,
          target_population_or_unit: estimandDraft.target_population_or_unit,
          generalization_level: estimandDraft.generalization_level,
          factor_ids: estimandDraft.factor_ids,
          timepoint: estimandDraft.timepoint ?? null,
          condition: estimandDraft.condition ?? null,
          evidence_ids: estimandDraft.evidence_ids,
          provenance: {
            origin: "user",
            evidence_ids: estimandDraft.evidence_ids,
            actor_role: "researcher",
          },
        };
        if (existingEstimandIndex >= 0) nextEstimands[existingEstimandIndex] = estimand;
        else nextEstimands.push(estimand);
        return { estimand, existingEstimand, existingEstimandIndex };
      });
      const correctionId = `${selectedBlock.id}-target-correction-${selectedBlock.corrections.length + 1}`;
      const nextBlock: ExperimentBlock = {
        ...selectedBlock,
        inference_targets:
          existingIndex >= 0
            ? selectedBlock.inference_targets.map((item, index) =>
                index === existingIndex ? target : item,
              )
            : [...selectedBlock.inference_targets, target],
        estimands: nextEstimands,
        corrections: [
          ...selectedBlock.corrections,
          {
            id: correctionId,
            sequence: selectedBlock.corrections.length,
            reason: "domain_judgement",
            rationale: draft.rationale,
            patch: [
              {
                op: existing ? "replace" : "add",
                path: existing ? `/inference_targets/${existingIndex}` : "/inference_targets/-",
                value: target,
              },
              ...estimandUpdates.map(({ estimand, existingEstimand, existingEstimandIndex }) => ({
                op: existingEstimand ? "replace" : "add",
                path: existingEstimand ? `/estimands/${existingEstimandIndex}` : "/estimands/-",
                value: estimand,
              })),
            ],
            evidence_ids: draft.evidence_ids,
            reviewer_role: draft.reviewer_role,
            verified: false,
          },
        ],
      };
      const readyCompilation: DesignCompilation = {
        specification_id: `${selectedBlock.id}-design-confirmed`,
        status: "ready",
        abstained: false,
        elicitation: { questions: [], blocking_question_ids: [], complete: true },
        analysis_handoff: {
          target_population_support: "supported",
          targets: nextBlock.inference_targets.map((item) => ({
            inference_target_id: item.id,
            status: item.status,
            question_text: item.question_text,
            claim_text: item.claim_text,
            population_of_inference: item.population_of_inference,
            target_biological_unit: item.target_biological_unit,
            target_population_support: "supported" as const,
            estimand_ids: nextBlock.estimands
              .filter(
                (estimand) =>
                  item.endpoint_ids.includes(estimand.endpoint_id) &&
                  estimand.factor_ids.every((factorId) => item.factor_ids.includes(factorId)),
              )
              .map((estimand) => estimand.id),
          })),
          estimands: nextBlock.estimands.map((estimand) => ({
            estimand_id: estimand.id,
            endpoint_id: estimand.endpoint_id,
            effect_measure: estimand.effect_measure,
            target_population_or_unit: estimand.target_population_or_unit,
            generalization_level: estimand.generalization_level,
            factor_ids: estimand.factor_ids,
            timepoint: estimand.timepoint,
            condition: estimand.condition,
            evidence_ids: estimand.evidence_ids,
          })),
          unresolved_assumptions: [],
          prohibited_outputs: [
            "statistical_test_selection",
            "model_formula",
            "power_analysis",
          ],
        },
      };
      setReport((current) => ({
        ...current,
        blocks: current.blocks.map((item) => (item.id === nextBlock.id ? nextBlock : item)),
        design_compilations: {
          ...current.design_compilations,
          [nextBlock.id]: readyCompilation,
        },
      }));
      setAudit((current) => ({
        ...current,
        [selectedBlock.id]: [
          ...(current[selectedBlock.id] ?? []),
          {
            id: `${correctionId}-audit`,
            sequence: selectedBlock.corrections.length,
            action: "apply",
            correction_id: correctionId,
          },
        ],
      }));
      storeCandidateExport(selectedBlock.id, {
        artifact_type: "ntruth_candidate_annotations",
        gold_status: "not_gold",
        training_eligible: false,
        block_id: selectedBlock.id,
        corrections: nextBlock.corrections,
      });
      setNotice("Target inferenziale confermato nella demo; compilazione strutturale pronta.");
      return;
    }
    if (!sessionId) {
      setNotice("Sessione di analisi non disponibile: rieseguire l’analisi.");
      return;
    }
    try {
      const response = await confirmInferenceTarget(sessionId, selectedBlock.id, draft);
      setReport(response.report);
      applyGovernanceState(response);
      setAudit((current) => ({ ...current, [selectedBlock.id]: response.audit_trail }));
      setCorrectionState((current) => ({
        ...current,
        [selectedBlock.id]: {
          active: response.active_correction_ids,
          redo: response.redo_correction_ids,
        },
      }));
      storeCandidateExport(selectedBlock.id, response.candidate_annotations);
      setNotice(`Target confermato e design ricompilato in ${response.recalculation_ms.toFixed(1)} ms.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Target inferenziale non applicabile.");
    }
  };

  const applyGraphCorrection = async (
    nextBlock: ExperimentBlock,
    patch: Array<Record<string, unknown>>,
    rationale: string,
  ) => {
    if (!selectedBlock) return;
    if (isDemo) {
      setDemoPast((items) => [...items, report]);
      setDemoFuture([]);
      const sequence = selectedBlock.corrections.length;
      const correctionId = `${selectedBlock.id}-graph-correction-${sequence + 1}`;
      const corrected: ExperimentBlock = {
        ...nextBlock,
        corrections: [
          ...selectedBlock.corrections,
          {
            id: correctionId,
            sequence,
            reason: "domain_judgement",
            rationale,
            patch,
            evidence_ids: selectedEvidence ? [selectedEvidence.id] : [],
            reviewer_role: "researcher",
            verified: false,
          },
        ],
      };
      replaceBlock(corrected);
      setAudit((current) => ({
        ...current,
        [selectedBlock.id]: [
          ...(current[selectedBlock.id] ?? []),
          {
            id: `${correctionId}-audit`,
            sequence,
            action: "apply",
            correction_id: correctionId,
          },
        ],
      }));
      storeCandidateExport(selectedBlock.id, {
        artifact_type: "ntruth_candidate_annotations",
        gold_status: "not_gold",
        training_eligible: false,
        block_id: selectedBlock.id,
        corrections: corrected.corrections,
      });
      setNotice("Modifica del grafo registrata come correzione candidata; non equivale a conferma.");
      return;
    }
    if (!sessionId) {
      setNotice("Sessione di analisi non disponibile: rieseguire l’analisi.");
      return;
    }
    try {
      const response = await applyCorrection(sessionId, selectedBlock.id, {
        reason: "domain_judgement",
        rationale,
        patch,
        evidence_ids: selectedEvidence ? [selectedEvidence.id] : [],
        reviewer_role: "researcher",
        verified: false,
      });
      setReport(response.report);
      applyGovernanceState(response);
      setAudit((current) => ({ ...current, [selectedBlock.id]: response.audit_trail }));
      setCorrectionState((current) => ({
        ...current,
        [selectedBlock.id]: {
          active: response.active_correction_ids,
          redo: response.redo_correction_ids,
        },
      }));
      storeCandidateExport(selectedBlock.id, response.candidate_annotations);
      setNotice(`Grafo corretto e ricalcolato in ${response.recalculation_ms.toFixed(1)} ms.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Modifica del grafo non applicabile.");
    }
  };

  const privacyExportBlocked =
    !isDemo &&
    (!privacyAudit || !shareReadiness || privacyAudit.status === "review_required");

  const exportArtifact = () => {
    if (isDemo) {
      downloadJson("ntruth-demo-report-not-scientific.json", report);
      setNotice("Esportato il report dimostrativo, esplicitamente non scientifico.");
      return;
    }
    if (privacyExportBlocked) {
      setNotice("Export bloccato: la revisione privacy deve essere completata localmente.");
      return;
    }
    if (!artifacts.ro_crate || !sessionId) {
      setNotice("RO-Crate non disponibile per questa sessione.");
      return;
    }
    window.location.assign(
      `/v1/sessions/${encodeURIComponent(sessionId)}/artifacts/ro_crate`,
    );
  };

  const onAnalysis = (response: AnalysisResponse) => {
    setReport(response.report);
    setIsDemo(false);
    setSessionId(response.session_id);
    setArtifacts(response.artifacts);
    setSelectedBlockId(response.report.blocks[0]?.id ?? "");
    setSelectedAlertId(response.report.blocks[0]?.alerts[0]?.id ?? "");
    setSelectedEvidenceId(undefined);
    setUiLanguage(response.report.language === "en" ? "en" : "it");
    setDomainAcknowledged(!response.domain_transparency.requires_acknowledgement);
    setShowImport(false);
    setNotice(response.ingest_summary);
    setAudit({});
    setCorrectionState({});
    setCandidateExports({});
    applyGovernanceState(response);
  };

  const reviewed = report.blocks.filter((item) => item.corrections.length > 0).length;
  const progress = report.blocks.length ? Math.round((reviewed / report.blocks.length) * 100) : 0;
  const exportBlocked =
    (report.domain_transparency.requires_acknowledgement && !domainAcknowledged) ||
    privacyExportBlocked;

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label={uiLanguage === "it" ? "Navigazione principale" : "Main navigation"}>
        <div className="brand"><strong>N-TRUTH</strong><small>DESIGN COMPILER</small></div>
        <nav className="primary-nav">
          {NAVIGATION.map(({ id, it, en, icon: NavIcon }) => {
            const label = uiLanguage === "it" ? it : en;
            return (
            <button
              key={id}
              className={activeView === id ? "nav-item active" : "nav-item"}
              onClick={() => navigate(id)}
              aria-current={activeView === id ? "page" : undefined}
              aria-label={label}
            >
              <NavIcon size={20} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <button className="nav-item" onClick={() => setNotice(uiLanguage === "it" ? "Impostazioni locali in arrivo." : "Local settings are not available yet.")}>
            <Settings size={19} /> <span>{uiLanguage === "it" ? "Impostazioni" : "Settings"}</span>
          </button>
          <button className="nav-item" onClick={() => setNotice(report.disclaimer)}>
            <Info size={19} /> <span>{uiLanguage === "it" ? "Limiti" : "Limitations"}</span>
          </button>
          <div className="build-status">
            <span>v0.1.0</span>
            <span className={`status-dot ${apiState}`} />
            {apiState === "online" ? (uiLanguage === "it" ? "API locale" : "Local API") : apiState === "offline" ? (uiLanguage === "it" ? "Solo demo" : "Demo only") : uiLanguage === "it" ? "Verifica…" : "Checking…"}
          </div>
        </div>
      </aside>

      <main className="app-main" id="workspace">
        <header className="topbar">
          <div className="project-title">
            <BookOpen size={20} />
            <div>
              <strong>{report.project_name}</strong>
              {isDemo && <span className="demo-label">{uiLanguage === "it" ? "Dati sintetici dimostrativi" : "Synthetic demonstration data"}</span>}
            </div>
          </div>
          <div className="topbar-actions">
            <span className="local-state"><span className="status-dot online" />{uiLanguage === "it" ? "Compilazione locale" : "Local compilation"}</span>
            <button
              className="language language-button"
              onClick={() => setUiLanguage((current) => (current === "it" ? "en" : "it"))}
              aria-label={uiLanguage === "it" ? "Switch interface to English" : "Passa l'interfaccia in italiano"}
            >
              <Languages size={17} />{uiLanguage.toUpperCase()}
            </button>
            <button className="button secondary" onClick={() => setShowImport(true)}>
              <Upload size={18} /> {uiLanguage === "it" ? "Importa fonti" : "Import sources"}
            </button>
          </div>
        </header>

        {notice && (
          <div className="toast" role="status">
            <Info size={17} /> <span>{notice}</span>
            <button aria-label={uiLanguage === "it" ? "Chiudi avviso" : "Close notice"} onClick={() => setNotice(undefined)}><X size={16} /></button>
          </div>
        )}

        <section className="workspace-grid">
          <section
            id="blocks-panel"
            className={`panel block-list-panel ${activeView === "experiments" ? "focused-panel" : ""}`}
            aria-labelledby="blocks-heading"
          >
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{uiLanguage === "it" ? "Unità primaria di revisione" : "Primary review unit"}</span>
                <h2 id="blocks-heading">{uiLanguage === "it" ? "Blocchi sperimentali" : "Experiment blocks"}</h2>
              </div>
              <span className="count-label">{report.blocks.length}</span>
            </div>
            <div className="block-list">
              {report.blocks.map((item, index) => {
                const summary = report.summaries.find((entry) => entry.block_id === item.id);
                const active = item.id === selectedBlock?.id;
                return (
                  <button
                    key={item.id}
                    className={active ? "block-card selected" : "block-card"}
                    onClick={() => setSelectedBlockId(item.id)}
                    aria-pressed={active}
                  >
                    <span className="block-index">E{index + 1}</span>
                    <span className="block-copy">
                      <strong>{item.title || `${uiLanguage === "it" ? "Esperimento" : "Experiment"} ${index + 1}`}</strong>
                      <small>{item.evidence[0]?.section_title ?? (uiLanguage === "it" ? "Fonte" : "Source")} · {item.source_file_ids.length} file</small>
                      <span className="block-meta">
                        {item.corrections.length ? <><Check size={14} /> {uiLanguage === "it" ? "Corretto" : "Corrected"}</> : <><span className="empty-dot" /> {uiLanguage === "it" ? "Da revisionare" : "Needs review"}</>}
                        <span><Link2 size={14} /> {summary?.n_alerts ?? item.alerts.length} {uiLanguage === "it" ? "questioni" : "issues"}</span>
                      </span>
                    </span>
                    <ChevronRight size={17} className="block-chevron" />
                  </button>
                );
              })}
            </div>
          </section>

          <div className="center-stack">
            <InferencePanel
              id="inference-panel"
              active={activeView === "questions"}
              block={selectedBlock}
              compilation={selectedCompilation}
              evidence={selectedEvidence}
              isDemo={isDemo}
              language={uiLanguage}
              onConfirm={confirmTarget}
            />
            <section
              id="graph-panel"
              className={`panel graph-panel ${activeView === "graph" ? "focused-panel" : ""}`}
              aria-labelledby="graph-heading"
            >
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{uiLanguage === "it" ? "Struttura ricostruita" : "Reconstructed structure"}</span>
                  <h2 id="graph-heading">{uiLanguage === "it" ? "Grafo del disegno sperimentale" : "Experimental design graph"}</h2>
                </div>
                <span className="count-label">{selectedBlock?.hierarchy.nodes.length ?? 0}</span>
              </div>
              {selectedBlock ? (
                <GraphView
                  block={selectedBlock}
                  evidence={selectedEvidence}
                  language={uiLanguage}
                  onEvidenceSelect={(evidenceId) => {
                    setSelectedEvidenceId(evidenceId);
                    setActiveView("documents");
                  }}
                  onEdit={applyGraphCorrection}
                />
              ) : <EmptyState />}
            </section>

            <section
              id="issues-panel"
              className="panel issues-panel"
              aria-labelledby="issues-heading"
            >
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">Ruleset {String(report.versions.ruleset_version ?? "—")}</span>
                  <h2 id="issues-heading">{uiLanguage === "it" ? "Questioni rilevate" : "Detected issues"}</h2>
                </div>
                <span className="count-label">{selectedBlock?.alerts.length ?? 0}</span>
              </div>
              <div className="issue-list">
                {selectedBlock?.alerts.map((alert) => (
                  <IssueCard
                    key={alert.id}
                    alert={alert}
                    selected={alert.id === selectedAlert?.id}
                    language={uiLanguage}
                    onSelect={() => {
                      setSelectedAlertId(alert.id);
                      setSelectedEvidenceId(alert.evidence_ids[0]);
                      setActiveView("documents");
                    }}
                  />
                ))}
                {!selectedBlock?.alerts.length && (
                  <p className="muted empty-copy">{uiLanguage === "it" ? "Nessun alert generato dal ruleset attivo." : "No alerts generated by the active ruleset."}</p>
                )}
              </div>
              {!!selectedBlock?.questions.length && (
                <details className="questions-drawer">
                  <summary>{selectedBlock.questions.length} {uiLanguage === "it" ? "domande mirate agli autori" : "targeted questions for the authors"}</summary>
                  <ul>{selectedBlock.questions.map((item) => (
                    <li key={item.id}>
                      {item.decisive && <strong>{uiLanguage === "it" ? "Decisiva" : "Decisive"} · </strong>}{item.text}
                      {item.priority != null && <small> {uiLanguage === "it" ? "priorita" : "priority"} {item.priority}</small>}
                    </li>
                  ))}</ul>
                </details>
              )}
            </section>
          </div>

          <div className="right-stack">
            <section
              id="evidence-panel"
              className={`panel evidence-panel ${activeView === "documents" ? "focused-panel" : ""}`}
              aria-labelledby="evidence-heading"
            >
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{uiLanguage === "it" ? "Fonte sincronizzata" : "Synchronized source"}</span>
                  <h2 id="evidence-heading">{uiLanguage === "it" ? "Evidenza" : "Evidence"}</h2>
                </div>
                {selectedAlert && (
                  <Confidence
                    value={selectedAlert.premise_confidence ?? selectedAlert.confidence}
                    label={uiLanguage === "it" ? "Confidenza premesse" : "Premise confidence"}
                  />
                )}
              </div>
              <div className="source-locator"><FileText size={15} /> {evidenceLocator(selectedEvidence)}</div>
              <blockquote className="evidence-excerpt">
                {selectedEvidence?.text || (uiLanguage === "it" ? "Nessuno span di evidenza collegato a questa selezione." : "No evidence span is linked to this selection.")}
              </blockquote>
              <div className="provenance-row">
                <span>File <code>{selectedEvidence?.file_id ?? "—"}</code></span>
                <span>{uiLanguage === "it" ? "Tipo" : "Type"} {selectedEvidence?.evidence_type ?? (uiLanguage === "it" ? "non classificato" : "unclassified")}</span>
                <span>Parser {selectedEvidence?.parser_version ?? "—"}</span>
              </div>
            </section>

            <CorrectionPanel
              id="correction-panel"
              active={activeView === "corrections"}
              block={selectedBlock}
              evidence={selectedEvidence}
              events={selectedBlock ? audit[selectedBlock.id] ?? [] : []}
              isDemo={isDemo}
              language={uiLanguage}
              canUndo={isDemo ? demoPast.length > 0 : Boolean(selectedBlock && (correctionState[selectedBlock.id]?.active.length ?? 0) > 0)}
              canRedo={isDemo ? demoFuture.length > 0 : Boolean(selectedBlock && (correctionState[selectedBlock.id]?.redo.length ?? 0) > 0)}
              onUndo={undo}
              onRedo={redo}
              onApply={async (value, rationale, reason) => {
                if (!selectedBlock) return;
                const evidenceIds = selectedEvidence ? [selectedEvidence.id] : [];
                if (isDemo) {
                  applyDemoCorrection(value, rationale, reason, evidenceIds);
                  return;
                }
                if (!sessionId) {
                  setNotice("Sessione di analisi non disponibile: rieseguire l’analisi.");
                  return;
                }
                try {
                  const response = await applyCorrection(sessionId, selectedBlock.id, {
                    reason,
                    rationale,
                    patch: [{ op: "replace", path: "/n_statements/0/value", value }],
                    evidence_ids: evidenceIds,
                    reviewer_role: "reviewer",
                    verified: false,
                  });
                  setReport(response.report);
                  applyGovernanceState(response);
                  setAudit((current) => ({ ...current, [selectedBlock.id]: response.audit_trail }));
                  setCorrectionState((current) => ({
                    ...current,
                    [selectedBlock.id]: {
                      active: response.active_correction_ids,
                      redo: response.redo_correction_ids,
                    },
                  }));
                  storeCandidateExport(selectedBlock.id, response.candidate_annotations);
                  setNotice(`Correzione applicata e regole ricalcolate in ${response.recalculation_ms.toFixed(1)} ms.`);
                } catch (error) {
                  setNotice(error instanceof Error ? error.message : "Correzione non applicabile.");
                }
              }}
              onExport={() => {
                if (!selectedCandidateExport || !selectedBlock || privacyExportBlocked) return;
                downloadJson(
                  `candidate-annotations-${selectedBlock.id}.json`,
                  selectedCandidateExport,
                );
              }}
              hasCandidate={Boolean(selectedCandidateExport)}
              exportAllowed={!privacyExportBlocked}
              />
            {selectedBlock && report.positive_outputs?.[selectedBlock.id] && (
              <PositiveOutputPanel
                output={report.positive_outputs[selectedBlock.id]}
                language={uiLanguage}
              />
            )}
          </div>
        </section>

        <footer id="export-bar" className={`review-bar ${activeView === "export" ? "focused-panel" : ""}`}>
          <div className="review-progress">
            <div className="progress-title"><Check size={19} /> <strong>{reviewed} {uiLanguage === "it" ? "di" : "of"} {report.blocks.length} {uiLanguage === "it" ? "blocchi corretti" : "corrected blocks"}</strong></div>
            <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
            <small>{progress}%</small>
          </div>
          <div className="domain-gate">
            <ShieldAlert size={22} />
            <div>
              <strong>{report.domain_transparency.validation_status === "validated" ? (uiLanguage === "it" ? "Dominio validato" : "Validated domain") : (uiLanguage === "it" ? "Dominio non validato" : "Unvalidated domain")}</strong>
              <p>{report.domain_transparency.warning}</p>
              {report.domain_transparency.requires_acknowledgement && (
                <label><input type="checkbox" checked={domainAcknowledged} onChange={(event) => setDomainAcknowledged(event.target.checked)} /> {uiLanguage === "it" ? "Ho verificato il limite e confermo" : "I reviewed and acknowledge this limitation"}</label>
              )}
            </div>
          </div>
          <div className={`privacy-gate ${privacyAudit?.status ?? "not-evaluated"}`}>
            <ShieldAlert size={22} />
            <div>
              <strong>
                {isDemo
                  ? uiLanguage === "it" ? "Privacy non valutata nella demo" : "Privacy not evaluated in demo"
                  : privacyAudit?.status === "clean"
                    ? uiLanguage === "it" ? "Scansione privacy pulita" : "Privacy scan clean"
                    : uiLanguage === "it" ? "Revisione privacy richiesta" : "Privacy review required"}
              </strong>
              <p>
                {isDemo
                  ? uiLanguage === "it" ? "L’export demo resta marcato come non scientifico." : "Demo export remains marked as non-scientific."
                  : privacyAudit?.status === "clean"
                    ? uiLanguage === "it" ? `${privacyAudit.scanned_fields} campi verificati localmente. La distribuzione resta soggetta a un gate esplicito.` : `${privacyAudit.scanned_fields} fields checked locally. Distribution still requires an explicit gate.`
                    : uiLanguage === "it" ? `${privacyAudit?.finding_count ?? 0} finding: export locale bloccato finché non viene applicata una policy.` : `${privacyAudit?.finding_count ?? 0} findings: local export is blocked until a policy is applied.`}
              </p>
              {!isDemo && shareReadiness && (
                <small>
                  {uiLanguage === "it" ? "Condivisione non autorizzata" : "Sharing not authorized"}
                  {shareReadiness.reasons.length ? ` · ${shareReadiness.reasons.join(" · ")}` : ""}
                </small>
              )}
            </div>
          </div>
          <div className="export-actions">
            <button
              className="button secondary"
              disabled={privacyExportBlocked}
              onClick={() => downloadJson("ntruth-report.json", report)}
            >
              <Save size={18} /> {uiLanguage === "it" ? "Salva report" : "Save report"}
            </button>
            <button className="button primary" disabled={exportBlocked} onClick={exportArtifact}>
              <Download size={18} /> {isDemo ? (uiLanguage === "it" ? "Esporta demo JSON" : "Export demo JSON") : (uiLanguage === "it" ? "Scarica RO-Crate locale" : "Download local RO-Crate")}
            </button>
          </div>
        </footer>
      </main>

      {showImport && <ImportDialog apiState={apiState} uiLanguage={uiLanguage} onClose={() => setShowImport(false)} onAnalysis={onAnalysis} />}
    </div>
  );
}

function PositiveOutputPanel({
  output,
  language,
}: {
  output: BlockPositiveOutput;
  language: "it" | "en";
}) {
  const pathLabel = {
    ready_for_review: language === "it" ? "Pronto per revisione" : "Ready for review",
    conditional: language === "it" ? "Condizionale" : "Conditional",
    incomplete: language === "it" ? "Incompleto" : "Incomplete",
  }[output.path_status];
  return (
    <section className="panel positive-output-panel" aria-labelledby="positive-output-heading">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">
            {language === "it" ? "Output positivo · non certificante" : "Positive output · non-certifying"}
          </span>
          <h2 id="positive-output-heading">
            {language === "it" ? "Methods e percorso di revisione" : "Methods and review path"}
          </h2>
        </div>
        <span className={`compiler-status positive-${output.path_status}`}>{pathLabel}</span>
      </div>
      <div className="positive-methods">
        <p>{output.status_reason}</p>
        <blockquote>{output.methods_statement.text}</blockquote>
        {output.methods_statement.limitations.map((item) => <small key={item}>{item}</small>)}
      </div>
      {!!output.candidate_analysis_strategies.length && (
        <details className="positive-details">
          <summary>{language === "it" ? "Strategie candidate" : "Candidate strategies"}</summary>
          <ul>{output.candidate_analysis_strategies.map((item) => <li key={item}>{item}</li>)}</ul>
        </details>
      )}
      <details className="positive-details">
        <summary>DRIVER · {language === "it" ? "mappatura informativa" : "informative mapping"}</summary>
        <div className="driver-list">
          {output.driver_checklist.map((item) => (
            <a key={item.item_id} href={item.source_url} target="_blank" rel="noreferrer">
              <strong>{item.item_id} · {item.title}</strong>
              <span className={`checklist-status status-${item.status}`}>{item.status}</span>
              <small>{item.note}</small>
            </a>
          ))}
        </div>
      </details>
      <details className="positive-details">
        <summary>{language === "it" ? "Fatti, inferenze, ipotesi e limiti" : "Facts, inferences, hypotheses and limitations"}</summary>
        <div className="statement-list">
          {output.statements.map((item) => (
            <div key={item.id} className={`statement-layer layer-${item.layer}`}>
              <span>{item.layer}</span><p>{item.text}</p>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

function IssueCard({
  alert,
  selected,
  language,
  onSelect,
}: {
  alert: Alert;
  selected: boolean;
  language: "it" | "en";
  onSelect: () => void;
}) {
  return (
    <button className={`issue-card severity-${alert.severity} ${selected ? "selected" : ""}`} onClick={onSelect}>
      <span className="issue-icon"><AlertTriangle size={19} /></span>
      <span className="issue-copy">
        <strong>{alert.message}</strong>
        <small>{alert.rule_id} · {alert.alert_class?.replaceAll("_", " ") ?? (language === "it" ? "classe legacy" : "legacy class")} · {alert.requires_human_confirmation ? (language === "it" ? "conferma umana richiesta" : "human confirmation required") : (language === "it" ? "conseguenza deterministica" : "deterministic consequence")}</small>
      </span>
      <span className="issue-confidence"><small>{language === "it" ? "Premesse" : "Premises"}</small>{(alert.premise_confidence ?? alert.confidence).toFixed(2)}</span>
      <Link2 size={16} />
    </button>
  );
}

function Confidence({ value, label = "Confidenza" }: { value: number; label?: string }) {
  return <span className="confidence">{label} {value.toFixed(2)}</span>;
}

export function InferencePanel({
  id,
  active,
  block,
  compilation,
  evidence,
  isDemo,
  language,
  onConfirm,
}: {
  id: string;
  active: boolean;
  block?: ExperimentBlock;
  compilation?: DesignCompilation;
  evidence?: EvidenceSpan;
  isDemo: boolean;
  language: "it" | "en";
  onConfirm: (draft: InferenceTargetDraft) => Promise<void> | void;
}) {
  const targets = block?.inference_targets ?? [];
  const [selectedTargetId, setSelectedTargetId] = useState(targets[0]?.id ?? "");
  const target = targets.find((item) => item.id === selectedTargetId) ?? targets[0];
  const targetHandoff = compilation?.analysis_handoff.targets.find(
    (item) => item.inference_target_id === target?.id,
  );
  const targetEstimands = useMemo(() => {
    const estimands = block?.estimands ?? [];
    if (!target) return estimands;
    const handoffIds = new Set(targetHandoff?.estimand_ids ?? []);
    if (handoffIds.size) return estimands.filter((item) => handoffIds.has(item.id));
    return estimands.filter(
      (item) =>
        target.endpoint_ids.includes(item.endpoint_id) &&
        item.factor_ids.every((factor) => target.factor_ids.includes(factor)),
    );
  }, [block?.estimands, target, targetHandoff?.estimand_ids]);
  const [question, setQuestion] = useState(target?.question_text ?? "");
  const [claim, setClaim] = useState(target?.claim_text ?? "");
  const [population, setPopulation] = useState(target?.population_of_inference ?? "");
  const [factorId, setFactorId] = useState(target?.factor_ids[0] ?? block?.factors[0]?.id ?? "");
  const [contrastId, setContrastId] = useState(
    target?.contrast_ids[0] ?? block?.contrasts[0]?.id ?? "",
  );
  const [endpointId, setEndpointId] = useState(
    target?.endpoint_ids[0] ?? block?.endpoints[0]?.id ?? "",
  );
  const initialEstimand = targetEstimands.find(
    (item) => item.endpoint_id === (target?.endpoint_ids[0] ?? block?.endpoints[0]?.id),
  );
  const [selectedEstimandId, setSelectedEstimandId] = useState(initialEstimand?.id ?? "");
  const [effectMeasure, setEffectMeasure] = useState(initialEstimand?.effect_measure ?? "");
  const [estimandPopulation, setEstimandPopulation] = useState(
    initialEstimand?.target_population_or_unit ?? "",
  );
  const [generalizationLevel, setGeneralizationLevel] = useState(
    initialEstimand?.generalization_level ?? "",
  );
  const [estimandTimepoint, setEstimandTimepoint] = useState(initialEstimand?.timepoint ?? "");
  const [estimandCondition, setEstimandCondition] = useState(initialEstimand?.condition ?? "");
  const biologicalTypes = useMemo(
    () =>
      Array.from(
        new Set(
          (block?.hierarchy.nodes ?? [])
            .map((node) => node.type)
            .filter((type) => ALLOCATABLE_NODE_TYPES.includes(type)),
        ),
      ),
    [block],
  );
  const [biologicalUnit, setBiologicalUnit] = useState(
    target?.target_biological_unit ?? biologicalTypes[0] ?? "",
  );
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(compilation?.status !== "ready");

  useEffect(() => {
    const nextTarget = targets.find((item) => item.id === selectedTargetId) ?? targets[0];
    if (nextTarget && nextTarget.id !== selectedTargetId) setSelectedTargetId(nextTarget.id);
    setQuestion(target?.question_text ?? "");
    setClaim(target?.claim_text ?? "");
    setPopulation(target?.population_of_inference ?? "");
    setFactorId(target?.factor_ids[0] ?? block?.factors[0]?.id ?? "");
    setContrastId(target?.contrast_ids[0] ?? block?.contrasts[0]?.id ?? "");
    const nextEndpointId = target?.endpoint_ids[0] ?? block?.endpoints[0]?.id ?? "";
    const nextEstimand =
      targetEstimands.find((item) => item.id === selectedEstimandId) ??
      targetEstimands.find((item) => item.endpoint_id === nextEndpointId);
    setEndpointId(nextEstimand?.endpoint_id ?? nextEndpointId);
    setSelectedEstimandId(nextEstimand?.id ?? "");
    setEffectMeasure(nextEstimand?.effect_measure ?? "");
    setEstimandPopulation(nextEstimand?.target_population_or_unit ?? "");
    setGeneralizationLevel(nextEstimand?.generalization_level ?? "");
    setEstimandTimepoint(nextEstimand?.timepoint ?? "");
    setEstimandCondition(nextEstimand?.condition ?? "");
    setBiologicalUnit(target?.target_biological_unit ?? biologicalTypes[0] ?? "");
    setRationale("");
    setEditing(compilation?.status !== "ready");
  }, [
    block?.id,
    target?.id,
    target?.status,
    biologicalTypes,
    compilation?.status,
    selectedEstimandId,
    selectedTargetId,
    targetEstimands,
    targets,
  ]);

  const contrasts = (block?.contrasts ?? []).filter(
    (item) => !factorId || item.factor_id === factorId || item.factor_ids?.includes(factorId),
  );
  const scopedFactorIds = target?.factor_ids.length ? target.factor_ids : [factorId].filter(Boolean);
  const scopedContrastIds = target?.contrast_ids.length
    ? target.contrast_ids
    : [contrastId].filter(Boolean);
  const scopedEndpointIds = target?.endpoint_ids.length
    ? target.endpoint_ids
    : [endpointId].filter(Boolean);
  const preservedEstimands = scopedEndpointIds.map((scopedEndpointId) => {
    if (scopedEndpointId === endpointId) {
      return {
          estimand_id: selectedEstimandId || undefined,
          endpoint_id: endpointId,
          effect_measure: effectMeasure.trim(),
          target_population_or_unit: estimandPopulation.trim(),
          generalization_level: generalizationLevel.trim(),
          factor_ids: scopedFactorIds,
          timepoint: estimandTimepoint.trim() || undefined,
          condition: estimandCondition.trim() || undefined,
          evidence_ids: evidence ? [evidence.id] : [],
        };
    }
    const existing = targetEstimands.find((item) => item.endpoint_id === scopedEndpointId);
    return existing
      ? {
          estimand_id: existing.id,
          endpoint_id: existing.endpoint_id,
          effect_measure: existing.effect_measure,
          target_population_or_unit: existing.target_population_or_unit,
          generalization_level: existing.generalization_level,
          factor_ids: existing.factor_ids,
          timepoint: existing.timepoint ?? undefined,
          condition: existing.condition ?? undefined,
          evidence_ids: existing.evidence_ids,
        }
      : undefined;
  });
  const focusEndpoints = target?.endpoint_ids.length
    ? (block?.endpoints ?? []).filter((item) => target.endpoint_ids.includes(item.id))
    : block?.endpoints ?? [];
  const estimandOptions = targetEstimands.filter((item) => item.endpoint_id === endpointId);

  const focusEstimand = (nextEndpointId: string, nextEstimandId?: string) => {
    const nextEstimand =
      targetEstimands.find((item) => item.id === nextEstimandId) ??
      targetEstimands.find((item) => item.endpoint_id === nextEndpointId);
    setEndpointId(nextEndpointId);
    setSelectedEstimandId(nextEstimand?.id ?? "");
    setEffectMeasure(nextEstimand?.effect_measure ?? "");
    setEstimandPopulation(nextEstimand?.target_population_or_unit ?? "");
    setGeneralizationLevel(nextEstimand?.generalization_level ?? "");
    setEstimandTimepoint(nextEstimand?.timepoint ?? "");
    setEstimandCondition(nextEstimand?.condition ?? "");
  };
  const valid = Boolean(
    question.trim().length >= 3 &&
      population.trim().length >= 2 &&
      factorId &&
      contrastId &&
      endpointId &&
      effectMeasure.trim() &&
      estimandPopulation.trim() &&
      generalizationLevel.trim() &&
      biologicalUnit &&
      rationale.trim().length >= 8 &&
      preservedEstimands.every(Boolean),
  );

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    try {
      await onConfirm({
        target_id: target?.id,
        question_text: question.trim(),
        claim_text: claim.trim(),
        population_of_inference: population.trim(),
        factor_ids: scopedFactorIds,
        contrast_ids: scopedContrastIds,
        endpoint_ids: scopedEndpointIds,
        target_biological_unit: biologicalUnit,
        evidence_ids: evidence ? [evidence.id] : [],
        rationale: rationale.trim(),
        reviewer_role: "researcher",
        estimands: preservedEstimands.filter(
          (item): item is NonNullable<typeof item> => Boolean(item),
        ),
      });
      setRationale("");
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };

  const support = compilation?.analysis_handoff.target_population_support ?? "unknown";
  const status = compilation?.status ?? "abstained";

  return (
    <section
      id={id}
      className={`panel inference-panel ${active ? "focused-panel" : ""}`}
      aria-labelledby="inference-heading"
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{language === "it" ? "Prima del calcolo di n" : "Before computing n"}</span>
          <h2 id="inference-heading">{language === "it" ? "Target inferenziale" : "Inference target"}</h2>
        </div>
        <span className={`compiler-status ${status}`}>
          {status === "ready" ? <Check size={14} /> : <CircleHelp size={14} />}
          {status === "ready" ? (language === "it" ? "Pronto" : "Ready") : (language === "it" ? "Astensione" : "Abstained")}
        </span>
      </div>
      {targets.length > 1 && (
        <label className="target-selector">
          <span>{language === "it" ? "Target da revisionare" : "Target to review"}</span>
          <select
            aria-label={language === "it" ? "Target da revisionare" : "Target to review"}
            value={target?.id ?? ""}
            onChange={(event) => setSelectedTargetId(event.target.value)}
          >
            {targets.map((item, index) => (
              <option key={item.id} value={item.id}>
                {index + 1}. {item.question_text || item.claim_text || item.id}
              </option>
            ))}
          </select>
          <small>
            {language === "it"
              ? `${targets.length} target distinti: nessuno viene compresso nel primo.`
              : `${targets.length} distinct targets: none is collapsed into the first.`}
          </small>
        </label>
      )}
      <div className="compiler-summary">
        <span>{language === "it" ? "Popolazione target" : "Target population"}</span>
        <strong>{support === "supported" ? (language === "it" ? "Supportata dallo scope" : "Supported by scope") : support === "conditional" ? (language === "it" ? "Condizionale" : "Conditional") : (language === "it" ? "Non definita" : "Not defined")}</strong>
        <small>{language === "it" ? "“Supportata” indica solo completezza strutturale, non validità scientifica." : "Supported means structural completeness only, not scientific validity."}</small>
      </div>
      {status === "ready" && target && !editing ? (
        <div className="confirmed-target">
          <div><span>{language === "it" ? "Domanda" : "Question"}</span><strong>{target.question_text}</strong></div>
          <div><span>{language === "it" ? "Popolazione" : "Population"}</span><strong>{target.population_of_inference}</strong></div>
          <div><span>Scope</span><strong>{target.factor_ids.map((id) => block?.factors.find((item) => item.id === id)?.name ?? id).join(", ")} · {target.endpoint_ids.map((id) => block?.endpoints.find((item) => item.id === id)?.name ?? id).join(", ")}</strong></div>
          {targetEstimands.map((item) => (
            <div key={item.id}>
              <span>Estimand · {block?.endpoints.find((endpoint) => endpoint.id === item.endpoint_id)?.name ?? item.endpoint_id}</span>
              <strong>{item.effect_measure} · {item.generalization_level}</strong>
            </div>
          ))}
          <button className="button secondary compact" onClick={() => setEditing(true)}>
            <PencilLine size={15} /> {language === "it" ? "Modifica target" : "Edit target"}
          </button>
        </div>
      ) : <form className="inference-form" onSubmit={submit}>
        <label className="field-label wide-field">{language === "it" ? "Domanda scientifica" : "Scientific question"}
          <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={language === "it" ? "Quale effetto, su quale popolazione?" : "Which effect, in which population?"} />
        </label>
        <label className="field-label wide-field">{language === "it" ? "Claim operativo" : "Operational claim"}
          <input value={claim} onChange={(event) => setClaim(event.target.value)} placeholder={language === "it" ? "Opzionale: formulazione che il disegno deve sostenere" : "Optional: claim the design is expected to support"} />
        </label>
        <label className="field-label wide-field">{language === "it" ? "Popolazione di inferenza" : "Population of inference"}
          <input value={population} onChange={(event) => setPopulation(event.target.value)} placeholder={language === "it" ? "Limita esplicitamente la generalizzazione" : "State the generalisation boundary explicitly"} />
        </label>
        <label className="field-label">{language === "it" ? "Fattore" : "Factor"}
          <select value={factorId} onChange={(event) => setFactorId(event.target.value)}>
            <option value="">{language === "it" ? "Seleziona" : "Select"}</option>
            {block?.factors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="field-label">{language === "it" ? "Contrasto" : "Contrast"}
          <select value={contrastId} onChange={(event) => setContrastId(event.target.value)}>
            <option value="">{language === "it" ? "Seleziona" : "Select"}</option>
            {contrasts.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <label className="field-label">Endpoint {language === "it" ? "in focus" : "in focus"}
          <select value={endpointId} onChange={(event) => focusEstimand(event.target.value)}>
            <option value="">{language === "it" ? "Seleziona" : "Select"}</option>
            {focusEndpoints.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="field-label">{language === "it" ? "Unità biologica target" : "Target biological unit"}
          <select value={biologicalUnit} onChange={(event) => setBiologicalUnit(event.target.value)}>
            <option value="">{language === "it" ? "Seleziona" : "Select"}</option>
            {biologicalTypes.map((item) => <option key={item} value={item}>{NODE_LABEL[item] ?? item}</option>)}
          </select>
        </label>
        <div className="form-subheading wide-field">
          <strong>Estimand minimo</strong>
          <small>{language === "it" ? `Dichiarato dall’utente: ${scopedEndpointIds.length} endpoint e ${scopedFactorIds.length} fattori restano nello scope completo.` : `User-declared: all ${scopedEndpointIds.length} endpoints and ${scopedFactorIds.length} factors remain in the complete scope.`}</small>
        </div>
        {estimandOptions.length > 1 && (
          <label className="field-label wide-field">
            {language === "it" ? "Estimand da revisionare" : "Estimand to review"}
            <select
              aria-label={language === "it" ? "Estimand da revisionare" : "Estimand to review"}
              value={selectedEstimandId}
              onChange={(event) => focusEstimand(endpointId, event.target.value)}
            >
              {estimandOptions.map((item, index) => (
                <option key={item.id} value={item.id}>
                  {index + 1}. {item.effect_measure} · {item.generalization_level}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="field-label">{language === "it" ? "Misura dell’effetto" : "Effect measure"}
          <input value={effectMeasure} onChange={(event) => setEffectMeasure(event.target.value)} placeholder={language === "it" ? "es. differenza media" : "e.g. mean difference"} />
        </label>
        <label className="field-label">{language === "it" ? "Livello di generalizzazione" : "Generalisation level"}
          <input value={generalizationLevel} onChange={(event) => setGeneralizationLevel(event.target.value)} placeholder={language === "it" ? "es. animale" : "e.g. animal"} />
        </label>
        <label className="field-label wide-field">{language === "it" ? "Popolazione o unità target dell’estimand" : "Estimand target population or unit"}
          <input value={estimandPopulation} onChange={(event) => setEstimandPopulation(event.target.value)} placeholder={language === "it" ? "Confine esatto dell’effetto da stimare" : "Exact boundary of the effect to estimate"} />
        </label>
        <label className="field-label">{language === "it" ? "Tempo (opzionale)" : "Time (optional)"}
          <input value={estimandTimepoint} onChange={(event) => setEstimandTimepoint(event.target.value)} />
        </label>
        <label className="field-label">{language === "it" ? "Condizione (opzionale)" : "Condition (optional)"}
          <input value={estimandCondition} onChange={(event) => setEstimandCondition(event.target.value)} />
        </label>
        <label className="field-label wide-field">{language === "it" ? "Razionale della conferma" : "Confirmation rationale"}
          <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} rows={2} placeholder={language === "it" ? "Perché questo è il target corretto? (minimo 8 caratteri)" : "Why is this the correct target? (minimum 8 characters)"} />
        </label>
        <div className="compiler-actions wide-field">
          <span>{target ? `${language === "it" ? "Stato fonte" : "Source status"}: ${target.status}` : (language === "it" ? "Nessun target nella fonte" : "No target in the source")} · {isDemo ? (language === "it" ? "demo sintetica" : "synthetic demo") : (language === "it" ? "conferma auditabile" : "auditable confirmation")}</span>
          <button className="button primary compact" disabled={!valid || busy}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}
            {language === "it" ? "Conferma target ed estimand" : "Confirm target and estimand"}
          </button>
        </div>
      </form>}
      {!!compilation?.elicitation.questions.length && (
        <details className="compiler-questions">
          <summary>{compilation.elicitation.blocking_question_ids.length} {language === "it" ? "domande bloccanti" : "blocking questions"}</summary>
          <ul>{compilation.elicitation.questions.map((item) => <li key={item.id}>{item.text}</li>)}</ul>
        </details>
      )}
      <div className="compiler-guardrail">
        {language === "it" ? "Nessuna selezione automatica di test, formula o potenza: l’handoff resta strutturale." : "No automatic selection of tests, formulas or power analysis: the handoff remains structural."}
      </div>
    </section>
  );
}

function GraphView({
  block,
  evidence,
  language,
  onEvidenceSelect,
  onEdit,
}: {
  block: ExperimentBlock;
  evidence?: EvidenceSpan;
  language: "it" | "en";
  onEvidenceSelect: (evidenceId: string) => void;
  onEdit: (
    nextBlock: ExperimentBlock,
    patch: Array<Record<string, unknown>>,
    rationale: string,
  ) => Promise<void> | void;
}) {
  const [query, setQuery] = useState("");
  const [zoom, setZoom] = useState(1);
  const [editing, setEditing] = useState(false);
  const [nodeType, setNodeType] = useState("CellCulture");
  const [nodeLabel, setNodeLabel] = useState("");
  const [relationType, setRelationType] = useState("nested_in");
  const [relationSource, setRelationSource] = useState(block.hierarchy.nodes[0]?.id ?? "");
  const [relationTarget, setRelationTarget] = useState(block.hierarchy.nodes[1]?.id ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRelationSource(block.hierarchy.nodes[0]?.id ?? "");
    setRelationTarget(block.hierarchy.nodes[1]?.id ?? "");
  }, [block.id, block.hierarchy.nodes.length]);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const nodes = useMemo(
    () =>
      block.hierarchy.nodes.filter(
        (item) =>
          !normalizedQuery ||
          item.label.toLocaleLowerCase().includes(normalizedQuery) ||
          item.type.toLocaleLowerCase().includes(normalizedQuery),
      ),
    [block.hierarchy.nodes, normalizedQuery],
  );
  const canvasHeight = Math.max(390, Math.ceil(Math.max(nodes.length, 1) / 4) * 125 + 35);
  const positions = useMemo(() => layoutNodes(nodes), [nodes]);
  const selectedIds = new Set(
    block.hierarchy.nodes
      .filter((item) => evidence && item.evidence_ids.includes(evidence.id))
      .map((item) => item.id),
  );
  const visible = new Set(nodes.map((item) => item.id));
  const relations = block.hierarchy.relations.filter(
    (item) => visible.has(item.source) && visible.has(item.target),
  );

  const runEdit = async (
    nextBlock: ExperimentBlock,
    patch: Array<Record<string, unknown>>,
    rationale: string,
  ) => {
    setBusy(true);
    try {
      await onEdit(nextBlock, patch, rationale);
    } finally {
      setBusy(false);
    }
  };

  const addNode = async (event: FormEvent) => {
    event.preventDefault();
    const label = nodeLabel.trim();
    if (!label) return;
    const slug = label
      .normalize("NFKD")
      .replace(/[^a-zA-Z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .toLocaleLowerCase();
    const baseId = `usr-${block.id}-${nodeType.toLocaleLowerCase()}-${slug || "node"}`;
    let id = baseId;
    let suffix = 2;
    while (block.hierarchy.nodes.some((item) => item.id === id)) id = `${baseId}-${suffix++}`;
    const evidenceIds = evidence ? [evidence.id] : [];
    const node: GraphNode = {
      id,
      type: nodeType,
      label,
      count: null,
      attributes: { user_added: true },
      evidence_ids: evidenceIds,
      confidence: 1,
      provenance: {
        origin: "user",
        evidence_ids: evidenceIds,
        actor_role: "researcher",
      },
    };
    await runEdit(
      {
        ...block,
        hierarchy: { ...block.hierarchy, nodes: [...block.hierarchy.nodes, node] },
      },
      [{ op: "add", path: "/hierarchy/nodes/-", value: node }],
      `Aggiunta manuale del nodo ${node.type} '${node.label}' al grafo sperimentale.`,
    );
    setNodeLabel("");
  };

  const removeNode = async (nodeId: string) => {
    const nodeIndex = block.hierarchy.nodes.findIndex((item) => item.id === nodeId);
    if (nodeIndex < 0) return;
    const relationIndexes = block.hierarchy.relations
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => item.source === nodeId || item.target === nodeId)
      .map(({ index }) => index)
      .sort((left, right) => right - left);
    const patch: Array<Record<string, unknown>> = relationIndexes.map((index) => ({
      op: "remove",
      path: `/hierarchy/relations/${index}`,
    }));
    patch.push({ op: "remove", path: `/hierarchy/nodes/${nodeIndex}` });
    await runEdit(
      {
        ...block,
        hierarchy: {
          nodes: block.hierarchy.nodes.filter((item) => item.id !== nodeId),
          relations: block.hierarchy.relations.filter(
            (item) => item.source !== nodeId && item.target !== nodeId,
          ),
        },
      },
      patch,
      `Rimozione manuale del nodo ${nodeId} e delle relazioni incidenti.`,
    );
  };

  const addRelation = async (event: FormEvent) => {
    event.preventDefault();
    if (!relationSource || !relationTarget || relationSource === relationTarget) return;
    const baseId = `usr-rel-${relationType}-${relationSource}-${relationTarget}`;
    let id = baseId;
    let suffix = 2;
    while (block.hierarchy.relations.some((item) => item.id === id)) id = `${baseId}-${suffix++}`;
    const evidenceIds = evidence ? [evidence.id] : [];
    const relation: GraphRelation = {
      id,
      type: relationType,
      source: relationSource,
      target: relationTarget,
      attributes: { user_added: true },
      evidence_ids: evidenceIds,
      confidence: 1,
      provenance: {
        origin: "user",
        evidence_ids: evidenceIds,
        actor_role: "researcher",
      },
    };
    await runEdit(
      {
        ...block,
        hierarchy: {
          ...block.hierarchy,
          relations: [...block.hierarchy.relations, relation],
        },
      },
      [{ op: "add", path: "/hierarchy/relations/-", value: relation }],
      `Aggiunta manuale della relazione ${relation.type} fra ${relation.source} e ${relation.target}.`,
    );
  };

  const removeRelation = async (relationId: string) => {
    const index = block.hierarchy.relations.findIndex((item) => item.id === relationId);
    if (index < 0) return;
    await runEdit(
      {
        ...block,
        hierarchy: {
          ...block.hierarchy,
          relations: block.hierarchy.relations.filter((item) => item.id !== relationId),
        },
      },
      [{ op: "remove", path: `/hierarchy/relations/${index}` }],
      `Rimozione manuale della relazione ${relationId} dal grafo sperimentale.`,
    );
  };

  const updateFactorLevel = async (
    factorIndex: number,
    field: "allocation_level" | "application_level",
    value: string,
  ) => {
    const factors = block.factors.map((factor, index) =>
      index === factorIndex ? { ...factor, [field]: value || null } : factor,
    );
    await runEdit(
      { ...block, factors },
      [{ op: "add", path: `/factors/${factorIndex}/${field}`, value: value || null }],
      `Impostazione manuale di ${field} per il fattore ${block.factors[factorIndex].name}.`,
    );
  };

  return (
    <div className="graph-workspace">
      <div className="graph-toolbar">
        <label>
          <Search size={15} />
          <span className="sr-only">{language === "it" ? "Cerca nodo" : "Search node"}</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={language === "it" ? "Cerca nodo…" : "Search node…"}
          />
        </label>
        <label className="zoom-control">
          <ZoomIn size={15} />
          <input
            aria-label={language === "it" ? "Zoom del grafo" : "Graph zoom"}
            type="range"
            min="0.75"
            max="1.35"
            step="0.05"
            value={zoom}
            onChange={(event) => setZoom(Number(event.target.value))}
          />
          <span>{Math.round(zoom * 100)}%</span>
        </label>
        <button className="button secondary compact" onClick={() => setEditing((value) => !value)}>
          <PencilLine size={15} />
          {language === "it" ? (editing ? "Chiudi editor" : "Modifica grafo") : editing ? "Close editor" : "Edit graph"}
        </button>
      </div>
      <div
        className="graph-canvas"
        style={{ height: `${canvasHeight + 8}px` }}
        role="group"
        aria-label={`Grafo con ${nodes.length} nodi e ${relations.length} relazioni`}
      >
        <div
          className="graph-stage"
          style={{ height: `${canvasHeight}px`, transform: `scale(${zoom})` }}
        >
          <svg viewBox={`0 0 720 ${canvasHeight}`} aria-hidden="true">
            <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" /></marker></defs>
            {relations.map((relation) => {
              const source = positions.get(relation.source);
              const target = positions.get(relation.target);
              if (!source || !target) return null;
              return (
                <g key={relation.id}>
                  <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} markerEnd="url(#arrow)" />
                  <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 7}>{relation.type.replaceAll("_", " ")}</text>
                </g>
              );
            })}
          </svg>
          {nodes.map((item) => {
            const position = positions.get(item.id)!;
            return (
              <button
                key={item.id}
                className={`graph-node node-${nodeCategory(item)} ${selectedIds.has(item.id) ? "evidence-linked" : ""}`}
                style={{ left: `${(position.x / 720) * 100}%`, top: `${(position.y / canvasHeight) * 100}%` }}
                title={`${item.type} · confidenza premesse ${item.confidence.toFixed(2)}`}
                onClick={() => item.evidence_ids[0] && onEvidenceSelect(item.evidence_ids[0])}
              >
                <small>{NODE_LABEL[item.type] ?? item.type}</small>
                <strong>{item.label}</strong>
                {item.count != null && <span>n = {item.count}</span>}
              </button>
            );
          })}
          {!nodes.length && <EmptyState />}
        </div>
      </div>
      {editing && (
        <div className="graph-editor" aria-label={language === "it" ? "Editor manuale del grafo" : "Manual graph editor"}>
          <p className="graph-editor-note">
            {language === "it"
              ? "Ogni modifica crea una correzione append-only e resta candidata finché non viene confermata esplicitamente."
              : "Every edit creates an append-only correction and remains a candidate until explicitly confirmed."}
          </p>
          <form className="graph-editor-row" onSubmit={addNode}>
            <label>{language === "it" ? "Tipo nodo" : "Node type"}
              <select value={nodeType} onChange={(event) => setNodeType(event.target.value)}>
                {EDITABLE_NODE_TYPES.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label>{language === "it" ? "Etichetta" : "Label"}
              <input required value={nodeLabel} onChange={(event) => setNodeLabel(event.target.value)} />
            </label>
            <button className="button primary compact" disabled={busy || !nodeLabel.trim()}>
              {language === "it" ? "Aggiungi nodo" : "Add node"}
            </button>
          </form>
          <form className="graph-editor-row relation-row" onSubmit={addRelation}>
            <label>{language === "it" ? "Sorgente" : "Source"}
              <select value={relationSource} onChange={(event) => setRelationSource(event.target.value)}>
                {block.hierarchy.nodes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
            <label>{language === "it" ? "Relazione" : "Relation"}
              <select value={relationType} onChange={(event) => setRelationType(event.target.value)}>
                {EDITABLE_RELATION_TYPES.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label>{language === "it" ? "Destinazione" : "Target"}
              <select value={relationTarget} onChange={(event) => setRelationTarget(event.target.value)}>
                {block.hierarchy.nodes.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
            </label>
            <button className="button primary compact" disabled={busy || !relationSource || !relationTarget || relationSource === relationTarget}>
              {language === "it" ? "Aggiungi relazione" : "Add relation"}
            </button>
          </form>
          {!!block.factors.length && (
            <div className="factor-level-editor">
              <strong>{language === "it" ? "Allocazione e applicazione (distinte)" : "Allocation and application (separate)"}</strong>
              {block.factors.map((factor, factorIndex) => (
                <div key={factor.id} className="factor-level-row">
                  <span>{factor.name}</span>
                  <label>{language === "it" ? "Allocazione" : "Allocation"}
                    <select value={factor.allocation_level ?? factor.assignment_level ?? ""} onChange={(event) => void updateFactorLevel(factorIndex, "allocation_level", event.target.value)}>
                      <option value="">—</option>
                      {ALLOCATABLE_NODE_TYPES.map((item) => <option key={item}>{item}</option>)}
                    </select>
                  </label>
                  <label>{language === "it" ? "Applicazione" : "Application"}
                    <select value={factor.application_level ?? ""} onChange={(event) => void updateFactorLevel(factorIndex, "application_level", event.target.value)}>
                      <option value="">—</option>
                      {ALLOCATABLE_NODE_TYPES.map((item) => <option key={item}>{item}</option>)}
                    </select>
                  </label>
                </div>
              ))}
            </div>
          )}
          <details className="graph-object-list">
            <summary>{language === "it" ? "Rimuovi nodi o relazioni" : "Remove nodes or relations"}</summary>
            <div className="graph-object-grid">
              {block.hierarchy.nodes.map((item) => (
                <button key={item.id} disabled={busy} onClick={() => void removeNode(item.id)}>
                  <X size={13} /> {item.type}: {item.label}
                </button>
              ))}
              {block.hierarchy.relations.map((item) => (
                <button key={item.id} disabled={busy} onClick={() => void removeRelation(item.id)}>
                  <X size={13} /> {item.type}: {item.source} → {item.target}
                </button>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

function layoutNodes(nodes: GraphNode[]): Map<string, { x: number; y: number }> {
  const columns = 4;
  return new Map(
    nodes.map((item, index) => {
      const row = Math.floor(index / columns);
      const column = index % columns;
      return [item.id, { x: 90 + column * 180, y: 70 + row * 125 }];
    }),
  );
}

function nodeCategory(node: GraphNode): string {
  if (["Treatment", "Factor", "FactorLevel"].includes(node.type)) return "factor";
  if (["Endpoint", "Analysis"].includes(node.type)) return "endpoint";
  if (["PrimarySample", "Well", "Cell", "Tissue"].includes(node.type)) return "sample";
  return "biological";
}

function CorrectionPanel({
  id,
  active,
  block,
  evidence,
  events,
  isDemo,
  language,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onApply,
  onExport,
  hasCandidate,
  exportAllowed,
}: {
  id: string;
  active: boolean;
  block?: ExperimentBlock;
  evidence?: EvidenceSpan;
  events: AuditEntry[];
  isDemo: boolean;
  language: "it" | "en";
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onApply: (value: number, rationale: string, reason: string) => Promise<void> | void;
  onExport: () => void;
  hasCandidate: boolean;
  exportAllowed: boolean;
}) {
  const current = block?.n_statements[0]?.value;
  const [nextValue, setNextValue] = useState(String(current ?? ""));
  const [rationale, setRationale] = useState("");
  const [reason, setReason] = useState("typo");
  const [busy, setBusy] = useState(false);

  useEffect(() => setNextValue(String(current ?? "")), [block?.id, current]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const parsed = Number(nextValue);
    if (!Number.isInteger(parsed) || parsed < 0 || rationale.trim().length < 8) return;
    setBusy(true);
    try {
      await onApply(parsed, rationale.trim(), reason);
      setRationale("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id={id} className={`panel correction-panel ${active ? "focused-panel" : ""}`} aria-labelledby="correction-heading">
      <div className="panel-heading correction-heading">
        <div>
          <span className="eyebrow">Append-only · candidate</span>
          <h2 id="correction-heading">{language === "it" ? "Correzione umana" : "Human correction"}</h2>
        </div>
        <div className="icon-actions">
          <button aria-label={language === "it" ? "Annulla correzione" : "Undo correction"} disabled={!canUndo} onClick={onUndo}><Undo2 size={17} /></button>
          <button aria-label={language === "it" ? "Ripeti correzione" : "Redo correction"} disabled={!canRedo} onClick={onRedo}><Redo2 size={17} /></button>
        </div>
      </div>
      {!block?.n_statements.length ? (
        <p className="muted empty-copy">{language === "it" ? "Nessuna menzione di n modificabile in questo blocco." : "No editable n statement in this block."}</p>
      ) : (
        <form onSubmit={submit} className="correction-form">
          <div className="diff-row">
            <span><small>{language === "it" ? "Campo" : "Field"}</small><code>/n_statements/0/value</code></span>
            <span><small>{language === "it" ? "Valore precedente" : "Previous value"}</small><del>n = {current ?? "—"}</del></span>
            <ChevronRight size={19} />
            <label><small>{language === "it" ? "Valore nuovo" : "New value"}</small><span className="n-input">n = <input aria-label={language === "it" ? "Nuovo valore di n" : "New n value"} type="number" min="0" step="1" value={nextValue} onChange={(event) => setNextValue(event.target.value)} /></span></label>
          </div>
          <label className="field-label">{language === "it" ? "Motivo" : "Reason"}
            <select value={reason} onChange={(event) => setReason(event.target.value)}>
              <option value="typo">{language === "it" ? "Refuso nella fonte" : "Source typo"}</option>
              <option value="parser_error">{language === "it" ? "Errore parser" : "Parser error"}</option>
              <option value="model_error">{language === "it" ? "Errore modello" : "Model error"}</option>
              <option value="source_missing">{language === "it" ? "Fonte incompleta" : "Incomplete source"}</option>
              <option value="domain_judgement">{language === "it" ? "Giudizio di dominio" : "Domain judgement"}</option>
              <option value="other">{language === "it" ? "Altro" : "Other"}</option>
            </select>
          </label>
          <label className="field-label">{language === "it" ? "Giustificazione" : "Rationale"}
            <textarea value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder={language === "it" ? "Cita la fonte o spiega il giudizio (minimo 8 caratteri)." : "Cite the source or explain the judgement (minimum 8 characters)."} rows={3} />
          </label>
          <div className="correction-footnote"><Link2 size={14} /> {evidence ? evidenceLocator(evidence) : (language === "it" ? "nessuna evidenza collegata" : "no linked evidence")}</div>
          <div className="form-actions">
            <span className="candidate-note"><Sparkles size={15} /> {isDemo ? (language === "it" ? "Demo non scientifica" : "Non-scientific demo") : (language === "it" ? "Annotazione candidata, non gold" : "Candidate annotation, not gold")}</span>
            <button className="button primary compact" disabled={busy || rationale.trim().length < 8 || nextValue === String(current ?? "")}>
              {busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />} {language === "it" ? "Applica e ricalcola" : "Apply and recalculate"}
            </button>
          </div>
        </form>
      )}
      <div className="audit-panel">
        <div className="audit-title"><span><History size={16} /> {language === "it" ? "Traccia di audit" : "Audit trail"}</span><button disabled={!hasCandidate || !exportAllowed} onClick={onExport}>{language === "it" ? "Esporta candidate" : "Export candidates"}</button></div>
        {events.length ? events.slice(-3).reverse().map((event) => (
          <div className="audit-entry" key={event.id}>
            <span className="avatar">R</span>
            <span><strong>{event.action === "apply" ? (language === "it" ? "Correzione applicata" : "Correction applied") : event.action === "undo" ? (language === "it" ? "Correzione annullata" : "Correction undone") : (language === "it" ? "Correzione ripristinata" : "Correction restored")}</strong><small>{event.correction_id}</small></span>
          </div>
        )) : <p className="muted">{language === "it" ? "Nessuna correzione registrata per questo blocco." : "No correction recorded for this block."}</p>}
      </div>
    </section>
  );
}

function ImportDialog({
  apiState,
  uiLanguage,
  onClose,
  onAnalysis,
}: {
  apiState: "checking" | "online" | "offline";
  uiLanguage: "it" | "en";
  onClose: () => void;
  onAnalysis: (result: AnalysisResponse) => void;
}) {
  const [source, setSource] = useState("");
  const [out, setOut] = useState("./ntruth-out");
  const [domain, setDomain] = useState("quantitative_microscopy");
  const [language, setLanguage] = useState<"it" | "en">(uiLanguage);
  const [acknowledged, setAcknowledged] = useState(false);
  const [domainNotice, setDomainNotice] = useState<Report["domain_transparency"]>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (apiState !== "online") return;
    preflight(domain).then(setDomainNotice).catch(() => undefined);
  }, [apiState, domain]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(undefined);
    setBusy(true);
    try {
      const result = await analyze({
        source: source.trim(),
        out: out.trim(),
        language,
        domain,
        acknowledge_unvalidated_domain: acknowledged,
      });
      onAnalysis(result);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setError(uiLanguage === "it" ? "Il dominio richiede una conferma esplicita prima dell’analisi." : "The domain requires explicit acknowledgement before analysis.");
      } else {
        setError(caught instanceof Error ? caught.message : (uiLanguage === "it" ? "Analisi non avviata." : "Analysis was not started."));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="import-title">
        <div className="dialog-header">
          <div><span className="eyebrow">{uiLanguage === "it" ? "Nessun upload · elaborazione locale" : "No upload · local processing"}</span><h2 id="import-title">{uiLanguage === "it" ? "Importa fonti" : "Import sources"}</h2></div>
          <button aria-label={uiLanguage === "it" ? "Chiudi" : "Close"} onClick={onClose}><X size={20} /></button>
        </div>
        {apiState !== "online" ? (
          <div className="offline-message"><Database size={22} /><div><strong>{uiLanguage === "it" ? "API locale non raggiungibile" : "Local API is unreachable"}</strong><p>{uiLanguage === "it" ? <>Avvia <code>ntruth-api</code>; nel frattempo resta disponibile la demo sintetica.</> : <>Start <code>ntruth-api</code>; the synthetic demo remains available.</>}</p></div></div>
        ) : (
          <form onSubmit={submit} className="import-form">
            <label className="field-label">{uiLanguage === "it" ? "File o cartella sorgente" : "Source file or folder"}
              <input autoFocus required value={source} onChange={(event) => setSource(event.target.value)} placeholder="/percorso/locale/metodi-e-sample-sheet" />
              <small>{uiLanguage === "it" ? "Il percorso resta sul computer e viene letto soltanto dall’API in loopback." : "The path stays on this computer and is read only by the loopback API."}</small>
            </label>
            <label className="field-label">{uiLanguage === "it" ? "Cartella output" : "Output folder"}
              <input required value={out} onChange={(event) => setOut(event.target.value)} />
            </label>
            <div className="field-grid">
              <label className="field-label">{uiLanguage === "it" ? "Dominio" : "Domain"}
                <select value={domain} onChange={(event) => { setDomain(event.target.value); setAcknowledged(false); }}>
                  <option value="quantitative_microscopy">{uiLanguage === "it" ? "Microscopia quantitativa" : "Quantitative microscopy"}</option>
                  <option value="cell_culture">{uiLanguage === "it" ? "Colture cellulari" : "Cell culture"}</option>
                  <option value="animal_experiment">{uiLanguage === "it" ? "Esperimenti animali" : "Animal experiments"}</option>
                  <option value="microbiome">{uiLanguage === "it" ? "Microbioma (fuori scope)" : "Microbiome (out of scope)"}</option>
                </select>
              </label>
              <label className="field-label">{uiLanguage === "it" ? "Lingua" : "Language"}
                <select value={language} onChange={(event) => setLanguage(event.target.value as "it" | "en")}>
                  <option value="it">Italiano</option>
                  <option value="en">English</option>
                </select>
              </label>
            </div>
            {domainNotice?.warning && (
              <div className="preflight-warning"><AlertTriangle size={19} /><div><strong>{domainNotice.validation_status === "out_of_scope" ? (uiLanguage === "it" ? "Fuori dal perimetro validato" : "Outside the validated scope") : (uiLanguage === "it" ? "Validazione esterna non completata" : "External validation is incomplete")}</strong><p>{domainNotice.warning}</p></div></div>
            )}
            {domainNotice?.requires_acknowledgement && (
              <label className="acknowledge"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} /> {uiLanguage === "it" ? "Comprendo il limite e autorizzo l’analisi locale senza interpretarla come validazione scientifica." : "I understand the limitation and authorize local analysis without treating it as scientific validation."}</label>
            )}
            {error && <p className="form-error" role="alert">{error}</p>}
            <div className="dialog-actions">
              <button type="button" className="button secondary" onClick={onClose}>{uiLanguage === "it" ? "Annulla" : "Cancel"}</button>
              <button className="button primary" disabled={busy || !source.trim() || Boolean(domainNotice?.requires_acknowledgement && !acknowledged)}>
                {busy ? <LoaderCircle className="spin" size={18} /> : <Beaker size={18} />} {uiLanguage === "it" ? "Avvia analisi" : "Start analysis"}
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

function EmptyState() {
  return <div className="empty-state"><RotateCcw size={22} /><span>Nessun dato disponibile per questa vista.</span></div>;
}
