import {
  AlertTriangle,
  ArrowDownToLine,
  Beaker,
  BookOpen,
  Check,
  ChevronRight,
  CircleHelp,
  ClipboardList,
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
  useRef,
  useState,
} from "react";

import {
  ApiError,
  apiErrorCode,
  apiErrorIssueId,
  analyzeV7,
  applyCorrection,
  confirmInferenceTarget,
  downloadJson,
  health,
  navigateCorrection,
  preflight,
  type InferenceTargetDraft,
} from "./api";
import { CanonicalCorrectionForm, type CorrectionPatch } from "./CanonicalCorrectionForm";
import { DEMO_REPORT } from "./data/demo";
import {
  downloadProspectiveArtifact,
  QuickDesignWizard,
} from "./QuickDesignWizard";
import { SpanLocator, refinementPatchEntry, type SpanRefinement } from "./SpanLocator";
import { ProspectiveD0Workspace } from "./d0/ProspectiveD0Workspace";
import {
  clearCheckpoint,
  loadCheckpoint,
  markCheckpointClosed,
  saveCheckpoint,
} from "./checkpoint";
import type {
  Alert,
  AnalysisResponse,
  AssessmentScope,
  AuditEntry,
  BlockReviewOutput,
  DesignCompilation,
  EvidenceSpan,
  ExperimentBlock,
  GraphNode,
  GraphRelation,
  KnowledgeValue,
  PrivacyAudit,
  QuickDesignV8Response,
  Report,
  Severity,
  ShareReadiness,
} from "./types";

type Icon = LucideIcon;
type View =
  | "prospective"
  | "project"
  | "documents"
  | "experiments"
  | "graph"
  | "questions"
  | "corrections"
  | "export";

const NAVIGATION: Array<{ id: View; it: string; en: string; icon: Icon }> = [
  { id: "prospective", it: "Progettazione D0", en: "D0 design", icon: ClipboardList },
  { id: "project", it: "Progetto", en: "Project", icon: FolderOpen },
  { id: "documents", it: "Documenti", en: "Documents", icon: FileText },
  { id: "experiments", it: "Esperimenti", en: "Experiments", icon: Beaker },
  { id: "graph", it: "Grafo", en: "Graph", icon: GitBranch },
  { id: "questions", it: "Elicitazione", en: "Elicitation", icon: CircleHelp },
  { id: "corrections", it: "Correzioni", en: "Corrections", icon: PencilLine },
  { id: "export", it: "Esporta", en: "Export", icon: ArrowDownToLine },
];

/** Raggruppamento visivo Fase 1: 5 gruppi percepiti, 8 bottoni invariati.
 * Nessun cambio di id/label/aria-label/onClick/ordine/tab-order. */
const NAV_GROUPS: Array<{ key: string; it: string; en: string; ids: View[] }> = [
  { key: "design", it: "Progetta", en: "Design", ids: ["prospective"] },
  { key: "frame", it: "Inquadra", en: "Frame", ids: ["project", "experiments"] },
  { key: "clarify", it: "Chiarisci", en: "Clarify", ids: ["questions", "graph"] },
  { key: "sources", it: "Fonti e correzioni", en: "Sources & corrections", ids: ["documents", "corrections"] },
  { key: "share", it: "Condividi", en: "Share", ids: ["export"] },
];

const NAV_BY_ID: Record<View, { id: View; it: string; en: string; icon: Icon }> =
  Object.fromEntries(NAVIGATION.map((item) => [item.id, item])) as Record<
    View, { id: View; it: string; en: string; icon: Icon }
  >;

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

/** Label semplici accanto al termine canonico (il canonico resta invariato). */
const EVIDENCE_TYPE_LABEL: Record<string, { it: string; en: string }> = {
  STRUCTURAL_FACT: { it: "Fatto dal disegno", en: "Design fact" },
  AUTHOR_ASSERTION: { it: "Dichiarazione autori", en: "Author statement" },
  SAMPLE_METADATA: { it: "Info campione", en: "Sample info" },
  STATISTICAL_CODE: { it: "Codice analisi", en: "Analysis code" },
  USER_CONFIRMATION: { it: "Conferma utente", en: "User confirmation" },
  MODEL_INFERENCE: { it: "Lettura automatica", en: "Automatic reading" },
  DERIVED_FACT: { it: "Fatto calcolato", en: "Computed fact" },
  CONFLICTING_EVIDENCE: { it: "Versioni in contrasto", en: "Conflicting versions" },
};

function evidenceLocator(evidence?: EvidenceSpan): string {  if (!evidence) return "Evidenza non localizzata";
  if (evidence.cell) {
    const sheet = evidence.cell.sheet ? `${evidence.cell.sheet}!` : "";
    return `${sheet}${evidence.cell.table_id} · riga ${evidence.cell.row + 1} · ${evidence.cell.column}`;
  }
  const section = evidence.section_title || evidence.section_id || evidence.file_id;
  if (evidence.start != null) return `${section} · caratteri ${evidence.start}–${evidence.end ?? "?"}`;
  return section;
}

function formatAuditTime(value: string | undefined, language: "it" | "en"): string {
  if (!value) return language === "it" ? "timestamp legacy non registrato" : "legacy timestamp not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString();
}

function focusId(view: View): string {
  return {
    prospective: "d0-panel",
    project: "project-heading",
    documents: "evidence-heading",
    experiments: "blocks-heading",
    graph: "graph-heading",
    questions: "issues-heading",
    corrections: "correction-heading",
    export: "export-heading",
  }[view];
}

function WelcomeHome({
  language,
  apiState,
  onStartDesign,
  onOpenDemo,
}: {
  language: "it" | "en";
  apiState: "checking" | "online" | "offline";
  onStartDesign: () => void;
  onOpenDemo: () => void;
}) {
  const it = language === "it";
  return (
    <section className="welcome" aria-labelledby="welcome-heading">
      <p className="welcome-kicker">{it ? "Compilatore locale · un solo Mac" : "Local compiler · this Mac only"}</p>
      <h1 id="welcome-heading">{it ? "Chiarisci il disegno prima di contare l’n." : "Settle the design before you count n."}</h1>
      <p className="welcome-lead">
        {it
          ? "N-Truth registra fatti, lacune e claim. Non approva un esperimento e non sostituisce un biostatistico."
          : "N-Truth records facts, gaps and claims. It does not approve an experiment and does not replace a biostatistician."}
      </p>
      <ul className="welcome-pins" aria-label={it ? "Stato scientifico" : "Scientific status"}>
        <li><strong>HANDOFF_ONLY</strong>{it ? "nessun test statistico consigliato" : "no statistical test is recommended"}</li>
        <li><strong>NOT_STARTED</strong>{it ? "validazione scientifica non iniziata" : "scientific validation has not started"}</li>
        <li><strong>HOLD</strong>{it ? "training e External Challenge fermi" : "training and External Challenge remain held"}</li>
      </ul>
      <p className="welcome-honesty">
        {it
          ? "La determinabilità non è approvazione del disegno. Un’anteprima del browser non è il risultato canonico Python."
          : "Determinability is not design approval. A browser preview is not the canonical Python result."}
      </p>
      <div className="welcome-actions">
        <button type="button" className="button primary" onClick={onStartDesign}>
          {it ? "Progetta un esperimento" : "Design an experiment"}
        </button>
        <button type="button" className="button secondary" onClick={onOpenDemo}>
          {it ? "Apri demo sintetica" : "Open synthetic demo"}
        </button>
      </div>
      <p className="welcome-next">
        {apiState === "online"
          ? it
            ? "Passo successivo: compila in Quick Design. Il PREVIEW resta non canonico finché non confermi."
            : "Next: compile in Quick Design. PREVIEW stays non-canonical until you confirm."
          : it
            ? "API offline. Puoi aprire la demo sintetica, oppure avvia ntruth-api per compilare."
            : "API offline. Open the synthetic demo, or start ntruth-api to compile."}
      </p>
    </section>
  );
}

function StatusSheet({
  language,
  apiState,
  disclaimer,
  onClose,
  onCloseProject,
}: {
  language: "it" | "en";
  apiState: "checking" | "online" | "offline";
  disclaimer?: string;
  onClose: () => void;
  onCloseProject?: () => void;
}) {
  const it = language === "it";
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => closeButtonRef.current?.focus(), []);
  const handleDialogKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      ),
    ).filter((element) => !element.hasAttribute("hidden"));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        className="dialog status-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="status-title"
        onKeyDown={handleDialogKeyDown}
      >
        <div className="dialog-header">
          <div>
            <span className="eyebrow">{it ? "Stato del prodotto" : "Product status"}</span>
            <h2 id="status-title">{it ? "Limiti e gate" : "Limits and gates"}</h2>
          </div>
          <button ref={closeButtonRef} type="button" aria-label={it ? "Chiudi" : "Close"} onClick={onClose}><X size={20} /></button>
        </div>
        <div className="status-sheet-body">
          <dl className="v8-definition-grid">
            <div><dt>API</dt><dd>{apiState === "online" ? (it ? "loopback attiva" : "loopback online") : apiState === "offline" ? (it ? "non raggiungibile" : "unreachable") : (it ? "verifica…" : "checking…")}</dd></div>
            <div><dt>Validazione scientifica</dt><dd>NOT_STARTED</dd></div>
            <div><dt>Training / External Challenge</dt><dd>HOLD</dd></div>
            <div><dt>Modulo statistico</dt><dd>HANDOFF_ONLY</dd></div>
          </dl>
          <p>
            {it
              ? "Questi gate non si aprono da questa schermata. Completeness strutturale non è verità biologica."
              : "These gates cannot be opened from this screen. Structural completeness is not biological truth."}
          </p>
          {disclaimer && <p className="status-disclaimer">{disclaimer}</p>}
          {onCloseProject && (
            <div className="status-close-project">
              <button
                type="button"
                className="button compact"
                onClick={() => {
                  onCloseProject();
                }}
              >
                {language === "it" ? "Chiudi progetto e torna alla welcome" : "Close project and return to welcome"}
              </button>
              <small>
                {language === "it"
                  ? "Elimina il checkpoint locale di questa sessione."
                  : "Clears this session's local checkpoint."}
              </small>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

/** Lista blocchi riusata nelle schermate Progetto (overview) ed Esperimenti (master).
 * Gli id sono parametrizzati: una sola istanza conserva gli id canonici
 * (focus + aria), le altre usano suffissi per non duplicare il DOM. */
function BlockListPanel({
  blocks,
  summaries,
  selectedBlockId,
  onSelect,
  language,
  focused = false,
  panelId = "blocks-panel",
  headingId = "blocks-heading",
}: {
  blocks: ExperimentBlock[];
  summaries: Report["summaries"];
  selectedBlockId?: string;
  onSelect: (blockId: string) => void;
  language: "it" | "en";
  focused?: boolean;
  panelId?: string;
  headingId?: string;
}) {
  const it = language === "it";
  return (
    <section
      id={panelId}
      className={`panel block-list-panel${focused ? " focused-panel" : ""}`}
      aria-labelledby={headingId}
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{it ? "Unità primaria di revisione" : "Primary review unit"}</span>
          <h2 id={headingId}>{it ? "Blocchi sperimentali" : "Experiment blocks"}</h2>
        </div>
        <span className="count-label">{blocks.length}</span>
      </div>
      <div className="block-list">
        {blocks.map((item, index) => {
          const summary = summaries.find((entry) => entry.block_id === item.id);
          const active = item.id === selectedBlockId;
          return (
            <button
              key={item.id}
              className={active ? "block-card selected" : "block-card"}
              onClick={() => onSelect(item.id)}
              aria-pressed={active}
            >
              <span className="block-index">E{index + 1}</span>
              <span className="block-copy">
                <strong>{item.title || `${it ? "Esperimento" : "Experiment"} ${index + 1}`}</strong>
                <small>{item.evidence[0]?.section_title ?? (it ? "Fonte" : "Source")} · {item.source_file_ids.length} file</small>
                <span className="block-meta">
                  {item.corrections.length ? <><Check size={14} aria-hidden="true" /> {it ? "Corretto" : "Corrected"}</> : <><span className="empty-dot" /> {it ? "Da revisionare" : "Needs review"}</>}
                  <span><Link2 size={14} aria-hidden="true" /> {summary?.n_alerts ?? item.alerts.length} {it ? "questioni" : "issues"}</span>
                </span>
              </span>
              <ChevronRight size={17} className="block-chevron" aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </section>
  );
}

function ReviewProgress({
  reviewed,
  total,
  language,
}: {
  reviewed: number;
  total: number;
  language: "it" | "en";
}) {
  const it = language === "it";
  const progress = total ? Math.round((reviewed / total) * 100) : 0;
  return (
    <div className="review-progress">
      <div className="progress-title"><Check size={19} aria-hidden="true" /> <strong>{reviewed} {it ? "di" : "of"} {total} {it ? "blocchi corretti" : "corrected blocks"}</strong></div>
      <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
      <small>{progress}%</small>
    </div>
  );
}

function DomainGate({
  report,
  domainAcknowledged,
  onAcknowledge,
  language,
  withCheckbox,
}: {
  report: Report;
  domainAcknowledged: boolean;
  onAcknowledge: (value: boolean) => void;
  language: "it" | "en";
  withCheckbox: boolean;
}) {
  const it = language === "it";
  return (
    <div className="domain-gate">
      <ShieldAlert size={22} aria-hidden="true" />
      <div>
        <strong>{report.domain_transparency.validation_status === "validated" ? (it ? "Dominio validato" : "Validated domain") : (it ? "Dominio non validato" : "Unvalidated domain")}</strong>
        <p>{report.domain_transparency.warning}</p>
        {withCheckbox && report.domain_transparency.requires_acknowledgement && (
          <label><input type="checkbox" checked={domainAcknowledged} onChange={(event) => onAcknowledge(event.target.checked)} /> {it ? "Ho verificato il limite e confermo" : "I reviewed and acknowledge this limitation"}</label>
        )}
        {!withCheckbox && report.domain_transparency.requires_acknowledgement && !domainAcknowledged && (
          <small>{it ? "Conferma richiesta nella schermata Esporta." : "Acknowledgement required in the Export screen."}</small>
        )}
      </div>
    </div>
  );
}

function PrivacyGate({
  isDemo,
  privacyAudit,
  shareReadiness,
  language,
}: {
  isDemo: boolean;
  privacyAudit?: PrivacyAudit;
  shareReadiness?: ShareReadiness;
  language: "it" | "en";
}) {
  const it = language === "it";
  return (
    <div className={`privacy-gate ${privacyAudit?.status ?? "not-evaluated"}`}>
      <ShieldAlert size={22} aria-hidden="true" />
      <div>
        <strong>
          {isDemo
            ? it ? "Privacy non valutata nella demo" : "Privacy not evaluated in demo"
            : privacyAudit?.status === "clean"
              ? it ? "Scansione privacy pulita" : "Privacy scan clean"
              : it ? "Revisione privacy richiesta" : "Privacy review required"}
        </strong>
        <p>
          {isDemo
            ? it ? "L’export demo resta marcato come non scientifico." : "Demo export remains marked as non-scientific."
            : privacyAudit?.status === "clean"
              ? it ? `${privacyAudit.scanned_fields} campi verificati localmente. La distribuzione resta soggetta a un gate esplicito.` : `${privacyAudit.scanned_fields} fields checked locally. Distribution still requires an explicit gate.`
              : it ? `${privacyAudit?.finding_count ?? 0} finding: export locale bloccato finché non viene applicata una policy.` : `${privacyAudit?.finding_count ?? 0} findings: local export is blocked until a policy is applied.`}
        </p>
        {!isDemo && shareReadiness && (
          <small>
            {it ? "Condivisione non autorizzata" : "Sharing not authorized"}
            {shareReadiness.reasons.length ? ` · ${shareReadiness.reasons.join(" · ")}` : ""}
          </small>
        )}
      </div>
    </div>
  );
}

/** Schermata Elicitazione: solo chiarire ciò che sblocca una decisione.
 * Read-only: il form target vive solo in Esperimenti, qui solo link. */
function QuestionsScreen({
  block,
  compilation,
  reviewOutput,
  rulesetVersion,
  selectedAlertId,
  onSelectAlert,
  language,
  onOpenExperiments,
  onOpenCorrections,
  onOpenDocuments,
}: {
  block?: ExperimentBlock;
  compilation?: DesignCompilation;
  reviewOutput?: BlockReviewOutput;
  rulesetVersion?: string | null;
  selectedAlertId?: string;
  onSelectAlert: (alertId: string, evidenceId?: string) => void;
  language: "it" | "en";
  onOpenExperiments: () => void;
  onOpenCorrections: () => void;
  onOpenDocuments: () => void;
}) {
  const it = language === "it";
  if (!block) return <EmptyState language={language} />;
  const blocking = compilation?.elicitation.questions ?? [];
  return (
    <section className="panel questions-screen" aria-labelledby="issues-heading">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">Ruleset {String(rulesetVersion ?? "—")}</span>
          <h2 id="issues-heading">{it ? "Questioni rilevate" : "Detected issues"}</h2>
        </div>
        <span className="panel-tools">
          <span className="count-label">{block.alerts.length}</span>
        </span>
      </div>
      <div className="questions-body">
      {reviewOutput?.discriminating_question && (
        <div className="discriminating">
          <span className="eyebrow">{it ? "Domanda discriminante" : "Discriminating question"}</span>
          <blockquote>{reviewOutput.discriminating_question.text}</blockquote>
        </div>
      )}
      {!!blocking.length && (
        <div className="blocking-questions">
          <span className="eyebrow">
            {it ? `Domande bloccanti (${blocking.length})` : `Blocking questions (${blocking.length})`}
          </span>
          <ul>
            {blocking.map((item) => (
              <li key={item.id}>{item.text}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="issue-list">
        {block.alerts.map((alert) => (
          <IssueCard
            key={alert.id}
            alert={alert}
            selected={alert.id === selectedAlertId}
            language={language}
            onSelect={() => onSelectAlert(alert.id, alert.evidence_ids[0])}
          />
        ))}
        {!block.alerts.length && (
          <p className="muted empty-copy">{it ? "Nessun alert generato dal ruleset attivo." : "No alerts generated by the active ruleset."}</p>
        )}
      </div>
      {!!block.questions.length && (
        <details className="questions-drawer">
          <summary>{block.questions.length} {it ? "domande mirate agli autori" : "targeted questions for the authors"}</summary>
          <ul>{block.questions.map((item) => (
            <li key={item.id}>
              {item.decisive && <strong>{it ? "Decisiva" : "Decisive"} · </strong>}{item.text}
              {item.priority != null && <small> {it ? "priorita" : "priority"} {item.priority}</small>}
            </li>
          ))}</ul>
        </details>
      )}
      <div className="screen-ctas">
        <button type="button" className="button secondary compact" onClick={onOpenExperiments}>
          {it ? "Rispondi in Esperimenti" : "Answer in Experiments"}
        </button>
        <button type="button" className="button secondary compact" onClick={onOpenCorrections}>
          {it ? "Vai a Correzioni" : "Go to Corrections"}
        </button>
        <button type="button" className="button secondary compact" onClick={onOpenDocuments}>
          {it ? "Verifica le fonti" : "Check the sources"}
        </button>
      </div>
      </div>
    </section>
  );
}

export function App() {
  const [report, setReport] = useState<Report>(DEMO_REPORT);
  const [quickDesignResult, setQuickDesignResult] = useState<QuickDesignV8Response>();
  const [surface, setSurface] = useState<"welcome" | "workspace">("welcome");
  const [showStatus, setShowStatus] = useState(false);
  const [isDemo, setIsDemo] = useState(false);
  const [activeView, setActiveView] = useState<View>("project");
  const [selectedBlockId, setSelectedBlockId] = useState(DEMO_REPORT.blocks[0].id);
  const [selectedAlertId, setSelectedAlertId] = useState(DEMO_REPORT.blocks[0].alerts[0].id);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string>();
  const [uiLanguage, setUiLanguage] = useState<"it" | "en">("it");
  const [apiState, setApiState] = useState<"checking" | "online" | "offline">("checking");
  const [showImport, setShowImport] = useState(false);
  const importButtonRef = useRef<HTMLButtonElement>(null);
  const statusButtonRef = useRef<HTMLButtonElement>(null);
  const viewScrollRef = useRef<HTMLDivElement>(null);
  const closeStatus = () => {
    setShowStatus(false);
    window.setTimeout(() => statusButtonRef.current?.focus(), 0);
  };
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
  const [wizardInitialStep, setWizardInitialStep] = useState(1);
  const [restoreInfo, setRestoreInfo] = useState<{ abrupt: boolean; at: string }>();
  // Accordion residuo per compatibilità checkpoint: il routing vero non usa collapse.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({
    "graph-panel": true,
    "issues-panel": true,
    "review-output": true,
  });
  // Tab contestuali L2: preferenza presentazionale per blocco, default fail-closed su target.
  // Non persistita nel checkpoint (ricostruibile, evita merge tra schede).
  const [blockTab, setBlockTab] = useState<Record<string, BlockTabKey>>({});
  const selectBlockTab = (blockId: string, tab: BlockTabKey) =>
    setBlockTab((current) => ({ ...current, [blockId]: tab }));
  // Gate di comprensione: uno stato leggero per blocco, persistito come domain_acknowledged.
  const [gateState, setGateState] = useState<Record<string, GateState>>({});
  const passGate = (blockId: string) => {
    setGateState((current) => ({
      ...current,
      [blockId]: {
        passed: true,
        skipped: false,
        motivation: "",
        attempts: current[blockId]?.attempts ?? 0,
        answeredAt: new Date().toISOString(),
      },
    }));
    setNotice(
      uiLanguage === "it"
        ? "Comprensione registrata per questo blocco. Non è un'approvazione del disegno."
        : "Comprehension recorded for this block. Not a design approval.",
    );
  };
  const skipGate = (blockId: string, motivation: string) => {
    setGateState((current) => ({
      ...current,
      [blockId]: {
        passed: false,
        skipped: true,
        motivation,
        attempts: current[blockId]?.attempts ?? 0,
        answeredAt: new Date().toISOString(),
      },
    }));
    setNotice(
      uiLanguage === "it"
        ? "Skip registrato con motivazione. Non è un'approvazione del disegno."
        : "Skip recorded with motivation. Not a design approval.",
    );
  };
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

  const workspaceActive = surface === "workspace" || quickDesignResult !== undefined;
  // A canonical v8 ReportBundle replaces the document-review workspace: only the
  // D0 planner and the report itself ("project") apply. The v7 views would show
  // the synthetic demo still held in `report` as if it were the user's project.
  const quickDesignActive = quickDesignResult !== undefined;
  const viewAppliesToQuickDesign = (view: View): boolean =>
    view === "prospective" || view === "project";
  // Routing vero: ogni voce apre UNA schermata (render condizionale su activeView),
  // contenuta nella viewport. Niente scroll-spy, niente espansioni di pannelli.
  const navigate = (view: View) => {
    if (!workspaceActive && view !== "prospective") {
      setNotice(
        uiLanguage === "it"
          ? "Nessun progetto attivo: apri la demo sintetica o importa le fonti per attivare la navigazione."
          : "No active project: open the synthetic demo or import sources to enable navigation.",
      );
      return;
    }
    if (quickDesignActive && !viewAppliesToQuickDesign(view)) {
      setNotice(
        uiLanguage === "it"
          ? "Vista non applicabile al ReportBundle v8 del Quick Design: riguarda la revisione di fonti importate."
          : "View not applicable to the Quick Design v8 ReportBundle: it covers review of imported sources.",
      );
      return;
    }
    setActiveView(view);
    // Torna in cima alla schermata (no-op sicuro in jsdom/test).
    try {
      viewScrollRef.current?.scrollTo?.({ top: 0 });
    } catch {
      // Contenitore non scrollabile in test: il focus resta la via di orientamento.
    }
    requestAnimationFrame(() => {
      // Il focus sull'h2 della vista è l'annuncio per tastiera e screen-reader.
      const heading = document.getElementById(focusId(view));
      if (!heading) return;
      if (!heading.hasAttribute("tabindex")) {
        heading.setAttribute("tabindex", "-1");
        heading.addEventListener("blur", () => heading.removeAttribute("tabindex"), { once: true });
      }
      try {
        (heading as HTMLElement).focus({ preventScroll: true });
      } catch {
        // jsdom/test senza focus layout: l'heading resta il punto di orientamento.
      }
    });
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
          actor_role: "reviewer",
          recorded_at: new Date().toISOString(),
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
              actor_role: "researcher",
              recorded_at: new Date().toISOString(),
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
              actor_role: "researcher",
              recorded_at: new Date().toISOString(),
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
      const structuralCompilation: DesignCompilation = {
        specification_id: `${selectedBlock.id}-design-confirmed`,
        status: "ready",
        abstained: false,
        elicitation: { questions: [], blocking_question_ids: [], complete: true },
        analysis_handoff: {
          target_population_support: "conditional",
          targets: nextBlock.inference_targets.map((item) => ({
            inference_target_id: item.id,
            status: item.status,
            question_text: item.question_text,
            claim_text: item.claim_text,
            population_of_inference: item.population_of_inference,
            target_biological_unit: item.target_biological_unit,
            target_population_support: "conditional" as const,
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
          [nextBlock.id]: structuralCompilation,
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
            actor_role: draft.reviewer_role,
            recorded_at: new Date().toISOString(),
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
      setNotice("Target inferenziale confermato nella demo; compilazione strutturale registrata.");
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
      const recordedAt = new Date().toISOString();
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
            actor_role: "researcher",
            recorded_at: recordedAt,
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

  const closeImport = () => {
    setShowImport(false);
    window.setTimeout(() => importButtonRef.current?.focus(), 0);
  };

  const onAnalysis = (response: AnalysisResponse) => {
    setQuickDesignResult(undefined);
    setReport(response.report);
    setSurface("workspace");
    setIsDemo(false);
    setSessionId(response.session_id);
    setArtifacts(response.artifacts);
    setSelectedBlockId(response.report.blocks[0]?.id ?? "");
    setSelectedAlertId(response.report.blocks[0]?.alerts[0]?.id ?? "");
    setSelectedEvidenceId(undefined);
    setUiLanguage(response.report.language === "en" ? "en" : "it");
    setDomainAcknowledged(!response.domain_transparency.requires_acknowledgement);
    closeImport();
    setNotice(response.ingest_summary);
    setAudit({});
    setCorrectionState({});
    setCandidateExports({});
    setBlockTab({});
    setGateState({});
    applyGovernanceState(response);
  };

  const onQuickDesign = (response: QuickDesignV8Response) => {
    setQuickDesignResult(response);
    setIsDemo(false);
    setSurface("workspace");
    setSessionId(undefined);
    setArtifacts({});
    setPrivacyAudit(undefined);
    setShareReadiness(undefined);
    setAudit({});
    setCorrectionState({});
    setCandidateExports({});
    closeImport();
    setNotice(`PRD v8 ReportBundle ${response.report.report_id} compilato.`);
  };

  const openSyntheticDemo = () => {
    setReport(DEMO_REPORT);
    setQuickDesignResult(undefined);
    setIsDemo(true);
    setSurface("workspace");
    setSelectedBlockId(DEMO_REPORT.blocks[0].id);
    setSelectedAlertId(DEMO_REPORT.blocks[0].alerts[0].id);
    setDomainAcknowledged(false);
    setBlockTab({});
    setGateState({});
  };

  // Deep-link QA/demo: ?demo=1 workspace sintetico, ?status=1 pannello gate,
  // ?wizard=N apre l'import direttamente al passo N del builder guidato.
  // ?view= apre direttamente la schermata richiesta (routing vero, niente scroll).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("demo") === "1") {
      openSyntheticDemo();
      const view = params.get("view");
      if (view && (["prospective", "project", "documents", "experiments", "graph", "questions", "corrections", "export"] as const).includes(view as View)) {
        setActiveView(view as View);
      }
    }
    if (params.get("status") === "1") setShowStatus(true);
    const wizardStep = Number(params.get("wizard") ?? "");
    if (Number.isInteger(wizardStep) && wizardStep >= 1 && wizardStep <= 5) {
      setWizardInitialStep(wizardStep);
      setShowImport(true);
    }

    // ---- Checkpoint: ripristino del progetto aperto (refresh, crash, spegnimento)
    const checkpoint = loadCheckpoint();
    if (checkpoint && checkpoint.payload.surface === "workspace" && checkpoint.payload.report) {
      try {
        const cp = checkpoint.payload;
        setReport(cp.report as typeof DEMO_REPORT);
        if (cp.quick_design) setQuickDesignResult(cp.quick_design as QuickDesignV8Response);
        setIsDemo(cp.is_demo);
        setSurface("workspace");
        if (cp.session_id) setSessionId(cp.session_id);
        const ui = cp.ui;
        if (ui) {
          if (ui.selected_block) setSelectedBlockId(ui.selected_block);
          if (ui.selected_alert) setSelectedAlertId(ui.selected_alert);
          if (ui.selected_evidence) setSelectedEvidenceId(ui.selected_evidence);
          setActiveView((ui.active_view as View) ?? "experiments");
          setCollapsed(ui.collapsed ?? {});
          setDomainAcknowledged(Boolean(ui.domain_acknowledged));
          if (ui.comprehension_gate) {
            const restored: Record<string, GateState> = {};
            for (const [blockId, record] of Object.entries(ui.comprehension_gate)) {
              if (record && (record.passed || record.skipped)) {
                restored[blockId] = {
                  passed: Boolean(record.passed),
                  skipped: Boolean(record.skipped),
                  motivation: typeof record.motivation === "string" ? record.motivation : "",
                  attempts: typeof record.attempts === "number" ? record.attempts : 0,
                };
              }
            }
            setGateState(restored);
          }
        }
        if (cp.corrections) setCorrectionState(cp.corrections as typeof correctionState);
        if (cp.candidate_exports) setCandidateExports(cp.candidate_exports as typeof candidateExports);
        if (cp.audit) setAudit(cp.audit as typeof audit);
        if (cp.privacy) setPrivacyAudit(cp.privacy as PrivacyAudit);
        if (cp.share) setShareReadiness(cp.share as ShareReadiness);
        const at = new Date(cp.saved_at).toLocaleTimeString(uiLanguage === "it" ? "it-IT" : "en-GB");
        setRestoreInfo({ abrupt: checkpoint.abrupt, at });
        saveCheckpoint({ status: "open" });
      } catch {
        // Checkpoint incompatibile: si riparte dalla welcome senza bloccare l'app.
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Autosave checkpoint (debounce 400ms) + flush su chiusura/nascondimento
  useEffect(() => {
    if (surface !== "workspace") return;
    const timer = window.setTimeout(() => {
      saveCheckpoint({
        surface,
        is_demo: isDemo,
        session_id: sessionId,
        report,
        quick_design: quickDesignResult,
        corrections: correctionState,
        candidate_exports: candidateExports,
        audit,
        privacy: privacyAudit,
        share: shareReadiness,
        ui: {
          active_view: activeView,
          selected_block: selectedBlockId,
          selected_alert: selectedAlertId,
          selected_evidence: selectedEvidenceId,
          collapsed,
          domain_acknowledged: domainAcknowledged,
          comprehension_gate: gateState,
        },
      });
    }, 400);
    return () => window.clearTimeout(timer);
  }, [
    surface, isDemo, sessionId, report, quickDesignResult, correctionState,
    candidateExports, audit, privacyAudit, shareReadiness, activeView,
    selectedBlockId, selectedAlertId, selectedEvidenceId, collapsed,
    domainAcknowledged, gateState,
  ]);

  useEffect(() => {
    const flush = () => markCheckpointClosed();
    const save = () => saveCheckpoint({ status: "open" });
    window.addEventListener("pagehide", flush);
    window.addEventListener("beforeunload", flush);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") save();
    });
    return () => {
      window.removeEventListener("pagehide", flush);
      window.removeEventListener("beforeunload", flush);
    };
  }, []);

  const closeProject = () => {
    clearCheckpoint();
    setRestoreInfo(undefined);
    setSurface("welcome");
    setQuickDesignResult(undefined);
    setIsDemo(false);
    setSessionId(undefined);
    setReport(DEMO_REPORT);
    setSelectedBlockId(DEMO_REPORT.blocks[0]?.id);
    setSelectedAlertId(DEMO_REPORT.blocks[0]?.alerts[0]?.id);
    setSelectedEvidenceId(undefined);
    setCorrectionState({});
    setCandidateExports({});
    setAudit({});
    setPrivacyAudit(undefined);
    setShareReadiness(undefined);
    setBlockTab({});
    setGateState({});
    setActiveView("project");
    setShowStatus(false);
  };

  const reviewed = report.blocks.filter((item) => item.corrections.length > 0).length;
  const progress = report.blocks.length ? Math.round((reviewed / report.blocks.length) * 100) : 0;
  const exportBlocked =
    (report.domain_transparency.requires_acknowledgement && !domainAcknowledged) ||
    privacyExportBlocked;
  // Badge sobri testuali per la nav (mai solo colore; aria-hidden, il nome resta canonico).
  // With a v8 ReportBundle open, the report is the "project" view whatever view
  // a restored checkpoint remembered.
  const effectiveView: View =
    quickDesignActive && !viewAppliesToQuickDesign(activeView) ? "project" : activeView;
  const navBadges: Partial<Record<View, string>> = workspaceActive && !quickDesignActive
    ? {
        experiments: `${report.blocks.length} ${uiLanguage === "it" ? "blocchi" : "blocks"}`,
        questions: (() => {
          const open = report.blocks.flatMap((item) => item.questions).filter((item) => item.decisive).length;
          return open > 0 ? `${open} ${uiLanguage === "it" ? "bloccanti" : "blocking"}` : undefined;
        })(),
        documents: selectedBlock && selectedBlock.evidence.length > 0
          ? `${selectedBlock.evidence.length} span`
          : undefined,
        corrections: (() => {
          const total = report.blocks.reduce((sum, item) => sum + item.corrections.length, 0);
          return total > 0 ? `${total} ${uiLanguage === "it" ? "candidate" : "candidates"}` : undefined;
        })(),
        export: exportBlocked ? (uiLanguage === "it" ? "gate" : "gated") : undefined,
      }
    : {};

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label={uiLanguage === "it" ? "Navigazione principale" : "Main navigation"}>
        <div className="brand"><strong>N-TRUTH</strong><small>DESIGN COMPILER</small></div>
        <nav className="primary-nav">
          {NAV_GROUPS.map((group) => (
            <div
              key={group.key}
              className="nav-group"
              role="group"
              aria-labelledby={`nav-group-${group.key}`}
            >
              <span className="nav-group-heading" id={`nav-group-${group.key}`}>
                {uiLanguage === "it" ? group.it : group.en}
              </span>
              {group.ids.map((id) => {
                const { it, en, icon: NavIcon } = NAV_BY_ID[id];
                const label = uiLanguage === "it" ? it : en;
                const notApplicable = quickDesignActive && !viewAppliesToQuickDesign(id);
                const disabled = !workspaceActive || notApplicable;
                // Sottotitolo operativo: conserva il termine canonico (aria-label),
                // aggiunge una riga semplice via title senza rinominare la voce.
                const plainHint: Record<View, { it: string; en: string }> = {
                  prospective: { it: "Progetta prima di eseguire: domanda, unità, piano", en: "Design before running: question, units, plan" },
                  project: { it: "Riepilogo del progetto e stato di revisione", en: "Project summary and review status" },
                  documents: { it: "Fonti sincronizzate ed evidenza citabile", en: "Synchronised sources and citable evidence" },
                  experiments: { it: "Blocchi sperimentali da revisionare", en: "Experiment blocks to review" },
                  graph: { it: "Struttura ricostruita del disegno", en: "Reconstructed design structure" },
                  questions: { it: "Domande da chiarire, bloccanti e informative", en: "Questions to clarify, blocking and informative" },
                  corrections: { it: "Correzioni proposte, candidate e mai gold", en: "Proposed corrections, candidate and never gold" },
                  export: { it: "Gate di dominio e privacy, poi export locale", en: "Domain and privacy gates, then local export" },
                };
                const hint = uiLanguage === "it" ? plainHint[id].it : plainHint[id].en;
                const badge = navBadges[id];
                return (
                <button
                  key={id}
                  className={`nav-item${disabled ? " disabled" : effectiveView === id ? " active" : ""}`}
                  onClick={() => navigate(id)}
                  aria-current={!disabled && effectiveView === id ? "page" : undefined}
                  aria-disabled={disabled || undefined}
                  title={
                    notApplicable
                      ? uiLanguage === "it"
                        ? `Non applicabile al ReportBundle v8 del Quick Design · ${hint}`
                        : `Not applicable to the Quick Design v8 ReportBundle · ${hint}`
                      : disabled
                      ? uiLanguage === "it"
                        ? `Attiva un progetto (demo o import) per usare questa sezione · ${hint}`
                        : `Activate a project (demo or import) to use this section · ${hint}`
                      : badge
                        ? `${hint} · ${badge}`
                        : hint
                  }
                  aria-label={label}
                >
                  <NavIcon size={20} strokeWidth={1.8} aria-hidden="true" />
                  <span>{label}</span>
                  {badge && <span className="nav-count" aria-hidden="true">{badge}</span>}
                </button>
                );
              })}
            </div>
          ))}
          {!workspaceActive && (
            <p className="nav-hint">
              {uiLanguage === "it"
                ? "Le sezioni si attivano con la demo o importando le fonti."
                : "Sections activate with the demo or by importing sources."}
            </p>
          )}
        </nav>
        <div className="sidebar-footer">
          <button ref={statusButtonRef} className="nav-item" onClick={() => setShowStatus(true)}>
            <Settings size={19} /> <span>{uiLanguage === "it" ? "Stato e limiti" : "Status and limits"}</span>
          </button>
          <div className="build-status">
            <span>v0.1.0</span>
            <span className={`status-dot ${apiState}`} />
            {apiState === "online" ? (uiLanguage === "it" ? "API locale" : "Local API") : apiState === "offline" ? (uiLanguage === "it" ? "Solo demo" : "Demo only") : uiLanguage === "it" ? "Verifica…" : "Checking…"}
          </div>
        </div>
      </aside>

      <main className="app-main" id="workspace">
        {restoreInfo && surface === "workspace" && (
          <div className="restore-banner" role="status">
            <History size={17} />
            <span>
              {restoreInfo.abrupt
                ? uiLanguage === "it"
                  ? `Ripristino automatico dopo un'interruzione non volontaria — checkpoint delle ${restoreInfo.at}.`
                  : `Automatic recovery after an unexpected shutdown — checkpoint from ${restoreInfo.at}.`
                : uiLanguage === "it"
                  ? `Progetto riaperto dal checkpoint locale delle ${restoreInfo.at}.`
                  : `Project reopened from the local checkpoint at ${restoreInfo.at}.`}
            </span>
            <button
              type="button"
              className="button compact"
              onClick={() => {
                clearCheckpoint();
                setRestoreInfo(undefined);
                setNotice(
                  uiLanguage === "it"
                    ? "Checkpoint locale eliminato: il progetto resta aperto in memoria."
                    : "Local checkpoint cleared: the project stays open in memory.",
                );
              }}
            >
              {uiLanguage === "it" ? "Ignora checkpoint" : "Dismiss checkpoint"}
            </button>
          </div>
        )}
        <header className="topbar">
          <div className="project-title">
            <BookOpen size={20} />
            <div>
              <strong>
                {quickDesignResult
                  ? `Quick Design · ${quickDesignResult.report.report_id}`
                  : surface === "welcome"
                    ? (uiLanguage === "it" ? "Sessione nuova" : "New session")
                    : report.project_name}
              </strong>
              {isDemo && surface === "workspace" && <span className="demo-label">{uiLanguage === "it" ? "Demo storica · dati sintetici" : "Historical demo · synthetic data"}</span>}
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
            <button
              ref={importButtonRef}
              className="button secondary"
              onClick={() => setShowImport(true)}
            >
              <Upload size={18} /> {uiLanguage === "it" ? "Importa fonti" : "Import sources"}
            </button>
          </div>
        </header>

        {notice && (
          <div className="toast" role="status" aria-atomic="true" aria-live="polite">
            <Info size={17} /> <span>{notice}</span>
            <button aria-label={uiLanguage === "it" ? "Chiudi avviso" : "Close notice"} onClick={() => setNotice(undefined)}><X size={16} /></button>
          </div>
        )}

        {showStatus && (
          <StatusSheet
            language={uiLanguage}
            apiState={apiState}
            disclaimer={report.disclaimer}
            onClose={closeStatus}
            onCloseProject={() => {
              closeProject();
            }}
          />
        )}

        <div className="view-scroll" ref={viewScrollRef}>
        <div className="view view-d0" hidden={activeView !== "prospective"}>
          <ProspectiveD0Workspace active={activeView === "prospective"} language={uiLanguage} />
        </div>

        {activeView === "prospective" ? null : surface === "welcome" && !quickDesignResult ? (
          <div className="view view-welcome">
          <WelcomeHome
            language={uiLanguage}
            apiState={apiState}
            onStartDesign={() => setShowImport(true)}
            onOpenDemo={openSyntheticDemo}
          />
          </div>
        ) : quickDesignResult ? (
          <div className="view view-report">
          <ReportBundleV8View result={quickDesignResult} language={uiLanguage} />
          </div>
        ) : (
          <>
            <div className="view view-project" hidden={activeView !== "project"}>
                <div className="view-heading-row">
                  <div>
                    <span className="eyebrow">{uiLanguage === "it" ? "Orientarsi nel progetto" : "Getting oriented in the project"}</span>
                    <h2 id="project-heading">{uiLanguage === "it" ? "Progetto" : "Project"}</h2>
                  </div>
                </div>
                <WorkspaceSummaryStrip
                  block={selectedBlock}
                  blockIndex={Math.max(0, report.blocks.findIndex((item) => item.id === selectedBlock?.id))}
                  blockCount={report.blocks.length}
                  output={selectedBlock ? report.review_outputs?.[selectedBlock.id] : undefined}
                  compilation={selectedCompilation}
                  decisiveOpen={selectedBlock ? selectedBlock.questions.filter((item) => item.decisive).length : 0}
                  domainBlocked={report.domain_transparency.requires_acknowledgement && !domainAcknowledged}
                  privacyBlocked={privacyExportBlocked}
                  language={uiLanguage}
                />
                <div className="project-grid">
                  <BlockListPanel
                    blocks={report.blocks}
                    summaries={report.summaries}
                    selectedBlockId={selectedBlock?.id}
                    panelId="project-blocks-panel"
                    headingId="project-blocks-heading"
                    onSelect={(blockId) => {
                      setSelectedBlockId(blockId);
                      navigate("experiments");
                    }}
                    language={uiLanguage}
                  />
                  <section className="panel project-side" aria-label={uiLanguage === "it" ? "Stato e prossimi passi" : "Status and next steps"}>
                    <ReviewProgress reviewed={reviewed} total={report.blocks.length} language={uiLanguage} />
                    <DomainGate
                      report={report}
                      domainAcknowledged={domainAcknowledged}
                      onAcknowledge={setDomainAcknowledged}
                      language={uiLanguage}
                      withCheckbox={false}
                    />
                    <PrivacyGate
                      isDemo={isDemo}
                      privacyAudit={privacyAudit}
                      shareReadiness={shareReadiness}
                      language={uiLanguage}
                    />
                    <p className="axis-boundary">
                      {uiLanguage === "it"
                        ? "La determinabilità non è approvazione del disegno."
                        : "Determinability is not design approval."}
                    </p>
                    <div className="screen-ctas">
                      <button type="button" className="button primary compact" onClick={() => navigate("experiments")}>
                        {uiLanguage === "it" ? "Vai a Esperimenti" : "Go to Experiments"}
                      </button>
                      <button type="button" className="button secondary compact" onClick={() => navigate("questions")}>
                        {uiLanguage === "it" ? "Vai a Elicitazione" : "Go to Elicitation"}
                      </button>
                    </div>
                    <p className="muted screen-note">
                      {uiLanguage === "it"
                        ? "Questa schermata non contiene form di conferma, diagnostica né export."
                        : "This screen contains no confirmation form, diagnostics or export."}
                    </p>
                  </section>
                </div>
              </div>
            <div className="view view-experiments" hidden={activeView !== "experiments"}>
                <div className="experiments-grid">
                  <BlockListPanel
                    blocks={report.blocks}
                    summaries={report.summaries}
                    selectedBlockId={selectedBlock?.id}
                    onSelect={setSelectedBlockId}
                    language={uiLanguage}
                    focused
                  />
                  <div className="experiments-detail">
                    {selectedBlock ? (
                      <BlockReviewTabs
                        block={selectedBlock}
                        output={report.review_outputs?.[selectedBlock.id]}
                        compilation={selectedCompilation}
                        evidence={selectedEvidence}
                        isDemo={isDemo}
                        language={uiLanguage}
                        onConfirm={confirmTarget}
                        gate={gateState[selectedBlock.id] ?? EMPTY_GATE}
                        onGatePass={() => passGate(selectedBlock.id)}
                        onGateSkip={(motivation) => skipGate(selectedBlock.id, motivation)}
                        tab={blockTab[selectedBlock.id] ?? "target"}
                        onTabChange={(next) => selectBlockTab(selectedBlock.id, next)}
                        active
                        onOpenQuestions={() => navigate("questions")}
                      />
                    ) : (
                      <EmptyState language={uiLanguage} />
                    )}
                  </div>
                </div>
              </div>
            <div className="view view-questions" hidden={activeView !== "questions"}>
                <QuestionsScreen
                  block={selectedBlock}
                  compilation={selectedCompilation}
                  reviewOutput={selectedBlock ? report.review_outputs?.[selectedBlock.id] : undefined}
                  rulesetVersion={report.versions.ruleset_version}
                  selectedAlertId={selectedAlertId}
                  onSelectAlert={(alertId, evidenceId) => {
                    setSelectedAlertId(alertId);
                    if (evidenceId) setSelectedEvidenceId(evidenceId);
                  }}
                  language={uiLanguage}
                  onOpenExperiments={() => navigate("experiments")}
                  onOpenCorrections={() => navigate("corrections")}
                  onOpenDocuments={() => navigate("documents")}
                />
              </div>
            <div className="view view-graph" hidden={activeView !== "graph"}>
            <section
              id="graph-panel"
              className="panel graph-panel"
              aria-labelledby="graph-heading"
            >
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{uiLanguage === "it" ? "Struttura ricostruita" : "Reconstructed structure"}</span>
                  <h2 id="graph-heading">{uiLanguage === "it" ? "Grafo del disegno sperimentale" : "Experimental design graph"}</h2>
                </div>
                <span className="panel-tools">
                  <span className="count-label">{selectedBlock?.hierarchy.nodes.length ?? 0}</span>
                </span>
              </div>
              <div className="panel-collapse" id="graph-body" role="group">
              {selectedBlock ? (
                <GraphView
                  block={selectedBlock}
                  evidence={selectedEvidence}
                  language={uiLanguage}
                  onEvidenceSelect={(evidenceId) => {
                    setSelectedEvidenceId(evidenceId);
                    navigate("documents");
                  }}
                  onEdit={applyGraphCorrection}
                />
              ) : <EmptyState language={uiLanguage} />}
              </div>
            </section>
              </div>
            <div className="view view-documents" hidden={activeView !== "documents"}>
            <section
              id="evidence-panel"
              className="panel evidence-panel"
              aria-labelledby="evidence-heading"
            >
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">{uiLanguage === "it" ? "Fonte sincronizzata" : "Synchronized source"}</span>
                  <h2 id="evidence-heading">{uiLanguage === "it" ? "Evidenza" : "Evidence"}</h2>
                </div>
                {selectedAlert && (
                  <span className="panel-tools">
                    <Confidence
                      value={selectedAlert.premise_confidence ?? selectedAlert.confidence}
                      label={uiLanguage === "it" ? "Confidenza premesse" : "Premise confidence"}
                    />
                  </span>
                )}
              </div>
              <div className="evidence-body">
              <div className="source-locator"><FileText size={15} aria-hidden="true" /> {evidenceLocator(selectedEvidence)}</div>
              <blockquote className="evidence-excerpt">
                {selectedEvidence?.text || (uiLanguage === "it" ? "Nessuno span di evidenza collegato a questa selezione." : "No evidence span is linked to this selection.")}
              </blockquote>
              <div className="provenance-row">
                <span>File <code>{selectedEvidence?.file_id ?? "—"}</code></span>
                <span>
                  {uiLanguage === "it" ? "Tipo" : "Type"}{" "}
                  {selectedEvidence?.evidence_type ?? (uiLanguage === "it" ? "non classificato" : "unclassified")}
                  {selectedEvidence?.evidence_type && EVIDENCE_TYPE_LABEL[selectedEvidence.evidence_type] && (
                    <> · {uiLanguage === "it" ? EVIDENCE_TYPE_LABEL[selectedEvidence.evidence_type].it : EVIDENCE_TYPE_LABEL[selectedEvidence.evidence_type].en}</>
                  )}
                </span>
                <span>Parser {selectedEvidence?.parser_version ?? "—"}</span>
              </div>
              {selectedBlock && selectedBlock.evidence.length > 0 && (
                <div className="evidence-list-wrap">
                  <span className="evidence-list-label" id="evidence-list-label">
                    {uiLanguage === "it"
                      ? `Span del blocco (${selectedBlock.evidence.length})`
                      : `Block spans (${selectedBlock.evidence.length})`}
                  </span>
                  <ul className="evidence-list" role="listbox" aria-labelledby="evidence-list-label">
                    {selectedBlock.evidence.map((span) => {
                      const isActive = span.id === selectedEvidence?.id;
                      const typeLabel = span.evidence_type && EVIDENCE_TYPE_LABEL[span.evidence_type]
                        ? (uiLanguage === "it" ? EVIDENCE_TYPE_LABEL[span.evidence_type].it : EVIDENCE_TYPE_LABEL[span.evidence_type].en)
                        : span.evidence_type ?? "";
                      return (
                        <li key={span.id} role="option" aria-selected={isActive}>
                          <button
                            type="button"
                            className={`evidence-option${isActive ? " selected" : ""}`}
                            aria-current={isActive || undefined}
                            onClick={() => setSelectedEvidenceId(span.id)}
                          >
                            <span className="evidence-option-locator">{evidenceLocator(span)}</span>
                            {typeLabel && <span className="evidence-option-type">{typeLabel}</span>}
                            <span className="evidence-option-excerpt">{span.text.slice(0, 140)}{span.text.length > 140 ? "…" : ""}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              </div>
            </section>
              </div>
            <div className="view view-corrections" hidden={activeView !== "corrections"}>
            <CorrectionPanel
              id="correction-panel"
              active
              block={selectedBlock}
              evidence={selectedEvidence}
              events={selectedBlock ? audit[selectedBlock.id] ?? [] : []}
              isDemo={isDemo}
              language={uiLanguage}
              canUndo={isDemo ? demoPast.length > 0 : Boolean(selectedBlock && (correctionState[selectedBlock.id]?.active.length ?? 0) > 0)}
              canRedo={isDemo ? demoFuture.length > 0 : Boolean(selectedBlock && (correctionState[selectedBlock.id]?.redo.length ?? 0) > 0)}
              onUndo={undo}
              onRedo={redo}
              onApply={async (patch, rationale, reason) => {
                if (!selectedBlock) return;
                const evidenceIds = selectedEvidence ? [selectedEvidence.id] : [];
                if (isDemo) {
                  const legacyValue = patch.find(
                    (operation) => operation.path === "/n_statements/0/value",
                  )?.value;
                  if (typeof legacyValue !== "number") {
                    setNotice("La demo sintetica supporta soltanto l'adapter n legacy.");
                    return;
                  }
                  applyDemoCorrection(legacyValue, rationale, reason, evidenceIds);
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
                    patch,
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
              </div>
            <div className="view view-export" hidden={activeView !== "export"}>
                <section className="panel export-screen" aria-labelledby="export-heading" data-testid="export-screen">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">{uiLanguage === "it" ? "Governare prima di scaricare" : "Govern before downloading"}</span>
                      <h2 id="export-heading">{uiLanguage === "it" ? "Esporta" : "Export"}</h2>
                    </div>
                  </div>
                  <div className="export-body">
                  <ReviewProgress reviewed={reviewed} total={report.blocks.length} language={uiLanguage} />
                  <DomainGate
                    report={report}
                    domainAcknowledged={domainAcknowledged}
                    onAcknowledge={setDomainAcknowledged}
                    language={uiLanguage}
                    withCheckbox
                  />
                  <PrivacyGate
                    isDemo={isDemo}
                    privacyAudit={privacyAudit}
                    shareReadiness={shareReadiness}
                    language={uiLanguage}
                  />
                  </div>
                  <div className="export-actions">
                    <button
                      className="button secondary"
                      disabled={privacyExportBlocked}
                      onClick={() => downloadJson("ntruth-report.json", report)}
                    >
                      <Save size={18} aria-hidden="true" /> {uiLanguage === "it" ? "Salva report" : "Save report"}
                    </button>
                    <button className="button primary" disabled={exportBlocked} onClick={exportArtifact}>
                      <Download size={18} aria-hidden="true" /> {isDemo ? (uiLanguage === "it" ? "Esporta demo JSON" : "Export demo JSON") : (uiLanguage === "it" ? "Scarica RO-Crate locale" : "Download local RO-Crate")}
                    </button>
                  </div>
                  <p className="muted screen-note">
                    {uiLanguage === "it"
                      ? "L'export resta locale. Dettagli tecnici (proof trace, checksum) via link sobrio su richiesta."
                      : "Export stays local. Technical details (proof trace, checksums) via a discreet link on request."}
                  </p>
                </section>
              </div>
          </>
        )}
        </div>
      </main>

      {showImport && (
        <ImportDialog
          apiState={apiState}
          uiLanguage={uiLanguage}
          onClose={closeImport}
          onAnalysis={onAnalysis}
          onQuickDesign={onQuickDesign}
          initialWizardStep={wizardInitialStep}
        />
      )}
    </div>
  );
}

function scientificValueText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) return value.map(scientificValueText).join(" · ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return "";
}

function KnowledgeStateValue({ value }: { value: KnowledgeValue }) {
  const text = scientificValueText(value.value);
  return (
    <div className="knowledge-value">
      <span className={`knowledge-state state-${value.knowledge_state.toLowerCase()}`}>
        {value.knowledge_state}
      </span>
      {text && <code>{text}</code>}
      {value.rationale && <small>{value.rationale}</small>}
    </div>
  );
}

export function ReportBundleV8View({
  result,
  language,
}: {
  result: QuickDesignV8Response;
  language: "it" | "en";
}) {
  const report = result.report;
  const planned = report.design_record_context.planned_design_record;
  const executed = report.design_record_context.executed_design_record;
  const reconciliation = report.design_record_context.reconciliation_record;
  const prospectiveLedgers = report.prospective_input_ledgers;
  const handoffItems = report.statistical_handoff.items;
  const labels = language === "it"
    ? {
        source: "Fonti e contesto del disegno",
        resolution: "Risoluzione del report",
        claims: "Claim derivati per query inferenziale",
        adequacy: "Valutazioni di adeguatezza del disegno",
        counts: "Conteggi canonici",
        coverage: "Copertura di scenari e profilo",
        review: "Sensitività e domande di revisione",
        handoff: "Handoff statistico",
        limits: "Limiti inferenziali",
      }
    : {
        source: "Sources and design context",
        resolution: "Report resolution",
        claims: "Derived claims by inferential query",
        adequacy: "Design adequacy evaluations",
        counts: "Canonical counts",
        coverage: "Scenario and profile coverage",
        review: "Sensitivities and review questions",
        handoff: "Statistical handoff",
        limits: "Inference limits",
      };

  return (
    <section className="v8-report-workspace" aria-labelledby="v8-report-heading">
      <header className="v8-report-header">
        <div>
          <span className="eyebrow">PRD v8 · canonical query-scoped output</span>
          <h1 id="v8-report-heading">ReportBundle v8</h1>
          <p>{report.epistemic_boundary}</p>
        </div>
        <div className="v8-contract-pins" aria-label="PRD v8 contract pins">
          <span>{result.contract.code}</span>
          <span>{result.contract.version}</span>
          <span>{report.strategy_module_status}</span>
          {result.artifacts.map((artifact) => (
            <button
              type="button"
              className="button secondary compact"
              key={artifact.artifact_id}
              aria-label={`Scarica artefatto ${artifact.kind}`}
              onClick={() => downloadProspectiveArtifact(artifact)}
            >
              <Download size={14} /> {artifact.kind}
            </button>
          ))}
        </div>
      </header>

      <div className="v8-report-grid">
        <section className="v8-card" aria-label="Sources and design context">
          <h2>{labels.source}</h2>
          <dl className="v8-definition-grid">
            <div><dt>Report</dt><dd><code>{report.report_id}</code></dd></div>
            <div><dt>Checksum</dt><dd><code>{report.content_checksum}</code></dd></div>
            <div><dt>Design mode</dt><dd>{report.design_record_context.mode}</dd></div>
            <div><dt>Planned design state</dt><dd>{planned.knowledge_state}</dd></div>
            {planned.value && <div><dt>Plan ID</dt><dd><code>{planned.value.plan_id}</code></dd></div>}
            <div><dt>Executed design state</dt><dd>{executed.knowledge_state}</dd></div>
            <div><dt>Reconciliation state</dt><dd>{reconciliation.knowledge_state}</dd></div>
            <div><dt>Prospective ledger state</dt><dd>{prospectiveLedgers.knowledge_state}</dd></div>
          </dl>
          <KnowledgeStateValue value={executed} />
          <KnowledgeStateValue value={reconciliation} />
          <details>
            <summary>Verified pipeline lineage · {report.verified_pipeline_contexts.length}</summary>
            <ul>
              {report.verified_pipeline_contexts.map((context) => (
                <li key={context.context_id}>
                  <code>{context.context_id}</code>
                  <small>context checksum: <code>{context.content_checksum}</code></small>
                  <small>conformance bundle: <code>{context.conformance_bundle_checksum}</code></small>
                </li>
              ))}
            </ul>
          </details>
          {prospectiveLedgers.knowledge_state === "PRESENT" && prospectiveLedgers.value && (
            <details>
              <summary>Prospective input ledgers · {prospectiveLedgers.value.length}</summary>
              <ul>
                {prospectiveLedgers.value.map((ledger) => (
                  <li key={ledger.ledger_id}>
                    <code>{ledger.ledger_id}</code>
                    <small>ledger checksum: <code>{ledger.content_checksum}</code></small>
                    <small>request checksum: <code>{ledger.request_checksum}</code></small>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <div className="v8-record-list">
            {report.source_records.map((source) => (
              <article key={source.source_id} aria-label={`Source ${source.source_id}`}>
                <strong>{source.source_id}</strong>
                <span>{source.source_context}</span>
                <span>{source.source_class.token}</span>
                <small>{source.source_class.registry_id}</small>
                <small>{source.source_version}</small>
              </article>
            ))}
          </div>
          <details>
            <summary>Evidence ledger · {report.evidence_records.length}</summary>
            <ul>
              {report.evidence_records.map((evidence) => (
                <li key={evidence.evidence_id}>
                  <code>{evidence.evidence_id}</code> · {evidence.evidence_type} · {evidence.source_id}
                  <small>{evidence.locator}</small>
                  <blockquote>{evidence.original_text}</blockquote>
                </li>
              ))}
            </ul>
          </details>
        </section>

        <section className="v8-card" aria-label="Report resolution">
          <h2>{labels.resolution}</h2>
          <KnowledgeStateValue value={report.report_resolution.resolution} />
          <p className="v8-neutral-note">
            {language === "it"
              ? "La risoluzione aggrega stati query-scoped; non certifica la qualità del disegno."
              : "Resolution aggregates query-scoped states; it does not certify design quality."}
          </p>
        </section>

        <section className="v8-card v8-span-all" aria-label="Derived claims by inferential query">
          <h2>{labels.claims}</h2>
          {report.query_sections.map((querySection) => {
            const claimSet = querySection.claim_set;
            return (
            <section className="v8-query-section" key={claimSet.claim_set_id}>
              <h3>
                {querySection.inferential_query.id} · {querySection.inferential_query.profile_id}
              </h3>
              <small>
                counts: {querySection.count_record_ids.join(" · ")} · questions: {querySection.questions.length}
              </small>
              <div className="v8-claim-grid">
                {claimSet.claims.map((claim) => (
                  <article
                    className="v8-claim"
                    key={claim.claim_id}
                    aria-label={`Derived claim ${claim.claim_id} for query ${claimSet.inferential_query_id}`}
                  >
                    <div className="v8-claim-heading">
                      <strong>{claim.claim_type}</strong>
                      <span>{claim.determinability_state}</span>
                    </div>
                    <code>{claim.claim_id}</code>
                    <KnowledgeStateValue value={claim.value} />
                    <dl>
                      <div><dt>Support grade</dt><dd>{claim.support_grade.token}</dd></div>
                      <div><dt>Vocabulary</dt><dd>{claim.support_grade.vocabulary_id}</dd></div>
                    </dl>
                    <details>
                      <summary>Proof trace · {claim.proof_trace.length}</summary>
                      <ul>
                        {claim.proof_trace.map((step) => (
                          <li key={step.step_id}>
                            <code>{step.step_id}</code> · <code>{step.theory_clause_id}</code> → <code>{step.rule_id}</code>
                            <ul>
                              {step.predicate_references.map((reference) => (
                                <li key={`${step.step_id}-${reference.predicate_id}`}>
                                  <code>{reference.predicate_id}</code> · {reference.predicate_value.knowledge_state}
                                  {reference.predicate_value.evidence_ids?.length
                                    ? ` · evidence ${reference.predicate_value.evidence_ids.join(" · ")}`
                                    : ""}
                                  {reference.predicate_value.value !== null && reference.predicate_value.value !== undefined
                                    ? ` · ${scientificValueText(reference.predicate_value.value)}`
                                    : ""}
                                </li>
                              ))}
                              {step.input_record_references.map((reference, referenceIndex) => (
                                <li key={`${step.step_id}-input-${referenceIndex}`}>
                                  input: <code>{scientificValueText(reference)}</code>
                                </li>
                              ))}
                            </ul>
                          </li>
                        ))}
                      </ul>
                    </details>
                    <details>
                      <summary>Predicate contract</summary>
                      <strong>Required predicates</strong>
                      <ul>{claim.required_predicates.map((predicate) => <li key={predicate}><code>{predicate}</code></li>)}</ul>
                      <strong>Irrelevant predicates</strong>
                      <ul>
                        {claim.irrelevant_predicates.map((predicate) => (
                          <li key={predicate.id}><code>{predicate.id}</code> · {predicate.rationale}</li>
                        ))}
                      </ul>
                      <strong>Assumptions</strong>
                      <ul>{claim.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
                    </details>
                  </article>
                ))}
              </div>
              <details>
                <summary>Query-scoped review records</summary>
                <dl className="v8-definition-grid">
                  <div><dt>AI</dt><dd>{querySection.ai_candidates.knowledge_state}</dd></div>
                  <div><dt>Confirmations</dt><dd>{querySection.human_confirmations.knowledge_state}</dd></div>
                  <div><dt>Conflicts</dt><dd>{querySection.conflicts.knowledge_state}</dd></div>
                  <div><dt>Sensitivities</dt><dd>{querySection.sensitivities.knowledge_state}</dd></div>
                </dl>
                {[querySection.human_confirmations, querySection.conflicts, querySection.sensitivities]
                  .filter((value) => value.knowledge_state === "PRESENT")
                  .map((value, index) => (
                    <pre key={`${claimSet.claim_set_id}-review-${index}`}>
                      {JSON.stringify(value.value, null, 2)}
                    </pre>
                  ))}
              </details>
            </section>
            );
          })}
        </section>

        <section className="v8-card v8-span-all" aria-label="Design adequacy evaluations">
          <h2>{labels.adequacy}</h2>
          <p className="v8-neutral-note">
            DETERMINATE ≠ good design. {language === "it" ? "Questo asse resta separato dai claim." : "This axis remains separate from claims."}
          </p>
          <div className="v8-record-list">
            {report.design_adequacy_evaluations.map((evaluation) => (
              <article
                key={evaluation.evaluation_id}
                aria-label={`Design adequacy ${evaluation.evaluation_id} for query ${evaluation.inferential_query_id}`}
              >
                <strong>{evaluation.axis}</strong>
                <code>{evaluation.evaluation_id}</code>
                <KnowledgeStateValue value={evaluation.outcome} />
                <small>{evaluation.rationale}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="v8-card" aria-label="Canonical counts">
          <h2>{labels.counts}</h2>
          <p><code>{report.count_registry.registry_version}</code></p>
          <div className="v8-record-list">
            {report.count_registry.records.map((count) => (
              <article key={count.count_id} aria-label={`Canonical count ${count.count_id}`}>
                <strong>{count.kind}</strong>
                <span>{count.quantifier} · {count.origin}</span>
                <KnowledgeStateValue value={count.value} />
                <small>query: {count.scope.query_id}</small>
              </article>
            ))}
          </div>
        </section>

        <section className="v8-card" aria-label="Scenario and profile coverage">
          <h2>{labels.coverage}</h2>
          <strong>{report.profile_coverage.profile_id}</strong>
          <p><code>{report.profile_coverage.statement_id}</code></p>
          <p>{report.profile_coverage.contract_review.status} · {report.profile_coverage.contract_review.issue_id}</p>
          <ul>
            {report.scenario_coverages.map((coverage, index) => (
              <li key={`${coverage.profile_id}-${index}`}>
                <strong>{coverage.status}</strong> · {coverage.profile_id}
                <KnowledgeStateValue value={coverage.omitted_dimensions} />
                <KnowledgeStateValue value={coverage.caveat} />
              </li>
            ))}
          </ul>
        </section>

        <section className="v8-card" aria-label="Sensitivities and review questions">
          <h2>{labels.review}</h2>
          <dl className="v8-definition-grid">
            <div><dt>Sensitivities</dt><dd>{report.sensitivities.knowledge_state}</dd></div>
            <div><dt>Confirmations</dt><dd>{report.human_confirmations.knowledge_state}</dd></div>
            <div><dt>Conflicts</dt><dd>{report.conflicts.knowledge_state}</dd></div>
            <div><dt>AI candidates</dt><dd>{report.ai_candidates.map((item) => item.knowledge_state).join(" · ")}</dd></div>
          </dl>
          {[report.sensitivities, report.human_confirmations, report.conflicts]
            .filter((value) => value.knowledge_state === "PRESENT")
            .map((value, index) => (
              <pre key={`global-review-record-${index}`}>{JSON.stringify(value.value, null, 2)}</pre>
            ))}
          <ul>
            {report.questions.map((question) => (
              <li key={question.question_id}>
                <strong>{question.primary ? "Review focus" : "Review"}</strong> · {question.text}
                <small>{question.inferential_query_id} · evidence: {question.evidence_required.join(" · ")}</small>
              </li>
            ))}
          </ul>
        </section>

        <section className="v8-card" aria-label="Statistical handoff">
          <h2>{labels.handoff}</h2>
          <strong>{report.statistical_handoff.strategy_module_status}</strong>
          <div className="v8-record-list">
            {handoffItems.map((item, index) => (
              <article key={`${item.category}-${index}`}>
                <strong>{item.category}</strong>
                <span>{item.origin} · {item.authority}</span>
                <small>
                  query: {item.inferential_query_id} · evidence: {item.evidence_refs.join(" · ")}
                </small>
                {(item.predicate_ids.length > 0 || item.question_ids.length > 0) && (
                  <small>
                    predicates: {item.predicate_ids.join(" · ") || "N/A"} · questions: {item.question_ids.join(" · ") || "N/A"}
                  </small>
                )}
              </article>
            ))}
          </div>
        </section>

        <section className="v8-card" aria-label="Confirmed graph and execution pins">
          <h2>{language === "it" ? "Grafo confermato e pin di esecuzione" : "Confirmed graph and execution pins"}</h2>
          <p>{report.confirmed_graph.nodes.length} nodes · {report.confirmed_graph.relations.length} relations</p>
          <ul>
            {report.confirmed_graph.nodes.map((node) => (
              <li key={node.node_id}><code>{node.node_id}</code> · {node.node_type}</li>
            ))}
          </ul>
          <dl className="v8-definition-grid">
            <div><dt>Manifest</dt><dd><code>{report.execution_manifest.manifest_id}</code></dd></div>
            <div><dt>Theory</dt><dd>{report.execution_manifest.theory_id} · {report.execution_manifest.theory_version}</dd></div>
            <div><dt>Theory checksum</dt><dd><code>{report.execution_manifest.theory_checksum}</code></dd></div>
            <div><dt>Rulebook</dt><dd>{report.execution_manifest.rulebook_id} · {report.execution_manifest.rulebook_version}</dd></div>
            <div><dt>Rulebook checksum</dt><dd><code>{report.execution_manifest.rulebook_checksum}</code></dd></div>
            <div><dt>Release blockers</dt><dd>{report.execution_manifest.release_blocker_issue_ids.join(" · ")}</dd></div>
          </dl>
        </section>

        <section className="v8-card v8-span-all" aria-label="Inference limits">
          <h2>{labels.limits}</h2>
          <ul>{report.inference_limits.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      </div>
    </section>
  );
}

type BlockTabKey = "target" | "counts" | "alternatives" | "methods";

const BLOCK_TABS: Array<{ key: BlockTabKey; it: string; en: string }> = [
  { key: "target", it: "Target e scope", en: "Target and scope" },
  { key: "counts", it: "Unità e conteggi", en: "Units and counts" },
  { key: "alternatives", it: "Alternative e domande", en: "Alternatives and questions" },
  { key: "methods", it: "Methods e handoff", en: "Methods and handoff" },
];

function pathStatusLabel(
  status: BlockReviewOutput["path_status"],
  language: "it" | "en",
): string {
  return {
    review_required: language === "it" ? "Revisione richiesta" : "Review required",
    conditional: language === "it" ? "Condizionale" : "Conditional",
    incomplete: language === "it" ? "Incompleto" : "Incomplete",
  }[status];
}

function scopeSummaryText(scope: AssessmentScope): string {
  const parts = [
    scope.factor_id,
    scope.contrast_id,
    scope.endpoint_id,
    scope.group,
    scope.timepoint,
    scope.unit_type,
    scope.lifecycle,
    scope.population,
    scope.condition,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "scope globale";
}

/** Tab B — solo unità e conteggi canonici. La diagnostica resta separata e chiusa. */
function UnitCountsTab({
  block,
  output,
  language,
}: {
  block: ExperimentBlock;
  output?: BlockReviewOutput;
  language: "it" | "en";
}) {
  const it = language === "it";
  const canonical = output?.count_records ?? [];
  const diagnostic = output?.diagnostic_count_records ?? [];
  const exclusions = output?.exclusion_records ?? [];
  return (
    <div className="tabpanel-section">
      {!!output?.n_table.length && (
        <div className="count-block">
          <h3>{it ? "Tabella n per ambito" : "n table by scope"}</h3>
          <div className="count-table-wrap">
            <table className="count-table" aria-label={it ? "Conteggi canonici per ambito" : "Canonical counts by scope"}>
              <thead>
                <tr>
                  <th scope="col">{it ? "Ambito" : "Scope"}</th>
                  <th scope="col">{it ? "Unità sperimentale" : "Experimental unit"}</th>
                  <th scope="col">n {it ? "dichiarato" : "declared"}</th>
                  <th scope="col">n {it ? "indipendente" : "independent"}</th>
                  <th scope="col">{it ? "Inferibilità" : "Inferability"}</th>
                </tr>
              </thead>
              <tbody>
                {output.n_table.map((row) => (
                  <tr key={row.assessment_id}>
                    <td>{row.scope}</td>
                    <td>{row.experimental_unit ?? "—"}</td>
                    <td>{row.n_declared ?? "—"}</td>
                    <td>{row.n_independent ?? "—"}</td>
                    <td>{row.inferability}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {!!block.unit_assessments.length && (
        <div className="count-block">
          <h3>{it ? "Valutazioni di unità per ambito" : "Unit assessments by scope"}</h3>
          <ul className="unit-assessment-list">
            {block.unit_assessments.map((item) => (
              <li key={item.id}>
                <strong>{scopeSummaryText(item.scope)}</strong>
                <span>
                  EU {item.experimental_unit ?? "—"} · {it ? "allocazione" : "allocation"}{" "}
                  {item.allocation_unit_candidate ?? "—"} · n {it ? "indipendente" : "independent"}{" "}
                  {item.n_independent ?? "—"} · {item.inferability} · {it ? "rischio" : "risk"} {item.risk}
                </span>
                {!!item.conditional_scenarios.length && (
                  <small>
                    {item.conditional_scenarios.length}{" "}
                    {it ? "scenari condizionali" : "conditional scenarios"}
                  </small>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <details className="review-details" open={canonical.length === 0}>
        <summary>
          {it ? "CANONICO — registro dei conteggi per replication" : "CANONICAL — count registry for replication"} · {canonical.length}
        </summary>
        {canonical.length ? (
          <ul>
            {canonical.map((record) => (
              <li key={record.count_id}>
                <code>{record.kind}</code> · {record.quantifier} ·{" "}
                {record.value ?? (record.lower_bound != null || record.upper_bound != null
                  ? `${record.lower_bound ?? "—"} - ${record.upper_bound ?? "—"}` : "—")} ·{" "}
                {record.scope.lifecycle ?? "lifecycle unknown"}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{it ? "Nessun conteggio canonico in questo blocco." : "No canonical counts in this block."}</p>
        )}
      </details>
      {!!diagnostic.length && (
        <details className="review-details diagnostic-counts">
          <summary>
            {it ? "DIAGNOSTICO — statistica separata · non replication" : "DIAGNOSTIC — separate statistics · non replication"} · {diagnostic.length}
          </summary>
          <p className="muted">
            {it
              ? "Diagnostica per il controllo tecnico: non usare per n indipendente."
              : "Technical-check diagnostics: do not use for independent n."}
          </p>
          <ul>
            {diagnostic.map((record) => (
              <li key={record.count_id}>
                <code>{record.kind}</code> = {record.value ?? "—"}{" "}
                <span className="diagnostic-only-badge">diagnostic_only</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {!!exclusions.length && (
        <details className="review-details">
          <summary>{it ? "Registro esclusioni" : "Exclusion registry"} · {exclusions.length}</summary>
          <ul>
            {exclusions.map((record) => (
              <li key={record.id}>
                {record.unit_type} · {record.phase} · {record.prespecified} · {record.reason ?? "reason not reported"}
              </li>
            ))}
          </ul>
        </details>
      )}
      {/* Il details CANONICO sopra copre già il caso vuoto: niente fallback duplicato. */}
    </div>
  );
}

/** Tab C — solo incertezza decidibile: determinabilità, alternative, discriminante. */
function AlternativesTab({
  block,
  output,
  language,
  onOpenQuestions,
}: {
  block: ExperimentBlock;
  output?: BlockReviewOutput;
  language: "it" | "en";
  onOpenQuestions: () => void;
}) {
  const it = language === "it";
  const humanConfirmations = block.alerts.filter((item) => item.requires_human_confirmation).length;
  return (
    <div className="tabpanel-section">
      {output ? (
        <section className="scientific-axis axis-determinability" data-testid="axis-determinability">
          <span>{it ? "Determinabilità" : "Determinability"}</span>
          <strong>{output.determinability.state}</strong>
          <small>{output.determinability.rationale}</small>
        </section>
      ) : (
        <p className="muted empty-copy">
          {it ? "Output di revisione non disponibile per questo blocco." : "Review output unavailable for this block."}
        </p>
      )}
      {output?.plausible_graph_set ? (
        <details className="review-details">
          <summary>
            {it ? "Grafi alternativi non risolti" : "Unresolved alternative graphs"} · {output.plausible_graph_set.alternatives.length}
          </summary>
          <p className="muted">
            {it ? "Nessuna alternativa viene scelta automaticamente." : "No alternative is selected automatically."}
          </p>
          {output.discriminating_question && <blockquote>{output.discriminating_question.text}</blockquote>}
          <div className="statement-list">
            {output.plausible_graph_set.alternatives.map((alternative) => (
              <div className="statement-layer layer-hypothesis" key={alternative.id}>
                <span>{alternative.label}</span>
                <div>
                  {alternative.consequences.map((consequence) => (
                    <p key={consequence.id}>
                      {consequence.description} · EU {consequence.experimental_unit ?? "—"} · n {consequence.n_independent ?? "—"}
                    </p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </details>
      ) : (
        <p className="muted empty-copy">
          {it ? "Nessun grafo alternativo: struttura univoca dal testo." : "No alternative graphs: single structure from the text."}
        </p>
      )}
      <p className="muted tab-crosslink">
        {humanConfirmations > 0
          ? it
            ? `${humanConfirmations} questioni richiedono conferma umana.`
            : `${humanConfirmations} issues require human confirmation.`
          : it
            ? "Nessuna questione richiede conferma umana in questo blocco."
            : "No issues require human confirmation in this block."}{" "}
        <button type="button" className="link-button" onClick={onOpenQuestions}>
          {it ? "Apri Elicitazione" : "Open Elicitation"}
        </button>
      </p>
    </div>
  );
}

/** Tab D — methods non certificante, handoff strutturale, mappatura DRIVER. */
function MethodsTab({
  output,
  language,
}: {
  output?: BlockReviewOutput;
  language: "it" | "en";
}) {
  const it = language === "it";
  if (!output) {
    return (
      <p className="muted empty-copy">
        {it ? "Output di revisione non disponibile per questo blocco." : "Review output unavailable for this block."}
      </p>
    );
  }
  return (
    <div className="tabpanel-section">
      <section className="scientific-axis axis-design-adequacy" data-testid="axis-design-adequacy">
        <span>{it ? "Adeguatezza del disegno" : "Design adequacy"}</span>
        <strong>{output.design_adequacy.finding}</strong>
        <small>{output.design_adequacy.rationale}</small>
      </section>
      <div className="statistical-handoff">
        <div>
          <span>{it ? "Handoff statistico" : "Statistical handoff"}</span>
          <strong>{output.strategy_module_status}</strong>
        </div>
        <small>
          {it
            ? "Solo requisiti strutturali e domande; nessuna strategia di analisi viene suggerita."
            : "Structural requirements and questions only; no analysis strategy is suggested."}
        </small>
      </div>
      <div className="review-methods">
        <p>{output.status_reason}</p>
        <blockquote>{output.methods_statement.text}</blockquote>
        {output.methods_statement.limitations.map((item) => <small key={item}>{item}</small>)}
      </div>
      <details className="review-details">
        <summary>DRIVER · {it ? "mappatura informativa" : "informative mapping"}</summary>
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
      <details className="review-details">
        <summary>{it ? "Fatti, inferenze, ipotesi e limiti" : "Facts, inferences, hypotheses and limitations"}</summary>
        <div className="statement-list">
          {output.statements.map((item) => (
            <div key={item.id} className={`statement-layer layer-${item.layer}`}>
              <span>{item.layer}</span><p>{item.text}</p>
            </div>
          ))}
        </div>
      </details>
    </div>
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
  const severityText = SEVERITY_LABEL[alert.severity];
  return (
    <button className={`issue-card severity-${alert.severity} ${selected ? "selected" : ""}`} onClick={onSelect} aria-describedby={`${alert.id}-severity`}>
      <span className="issue-icon" aria-hidden="true"><AlertTriangle size={19} /></span>
      <span className="issue-copy">
        <strong>{alert.message}</strong>
        <small>{alert.rule_id} · {alert.alert_class?.replaceAll("_", " ") ?? (language === "it" ? "classe legacy" : "legacy class")} · {alert.requires_human_confirmation ? (language === "it" ? "conferma umana richiesta" : "human confirmation required") : (language === "it" ? "conseguenza deterministica" : "deterministic consequence")}</small>
        <small id={`${alert.id}-severity`} className="issue-severity-label">{severityText}</small>
      </span>
      <span className="issue-confidence" title={language === "it" ? "Affidabilità della lettura automatica delle premesse, non probabilità che il claim sia vero" : "Automatic premise-reading reliability, not the probability that the claim is true"}><small>{language === "it" ? "Premesse" : "Premises"}</small>{(alert.premise_confidence ?? alert.confidence).toFixed(2)}</span>
      <Link2 size={16} aria-hidden="true" />
    </button>
  );
}

function Confidence({ value, label = "Confidenza" }: { value: number; label?: string }) {
  return (
    <span
      className="confidence"
      title="Affidabilità della lettura automatica (parser) · non è la probabilità che il claim scientifico sia vero"
    >
      {label} {value.toFixed(2)}
    </span>
  );
}

export interface GateState {
  passed: boolean;
  skipped: boolean;
  motivation: string;
  attempts: number;
}

export const EMPTY_GATE: GateState = { passed: false, skipped: false, motivation: "", attempts: 0 };

interface GateQuestion {
  id: string;
  conceptIt: string;
  conceptEn: string;
  textIt: string;
  textEn: string;
  optionsIt: [string, string, string];
  optionsEn: [string, string, string];
  correct: number;
  feedbackIt: string;
  feedbackEn: string;
}

const GATE_QUESTIONS: GateQuestion[] = [
  {
    id: "eu",
    conceptIt: "Unità sperimentale",
    conceptEn: "Experimental unit",
    textIt: "Cosa decide l'unità sperimentale (n indipendente)?",
    textEn: "What defines the experimental unit (independent n)?",
    optionsIt: [
      "Il pozzetto o la cellula dove misuro l'endpoint",
      "L'unità assegnata al trattamento",
      "Il punto dove applico il farmaco con la pipetta",
    ],
    optionsEn: [
      "The well or cell where I measure the endpoint",
      "The unit assigned to treatment",
      "The spot where I pipette the drug",
    ],
    correct: 1,
    feedbackIt: "Misurare non è assegnare: conta dove randomizzi, non dove leggi.",
    feedbackEn: "Measuring is not assigning: count where you randomize, not where you read.",
  },
  {
    id: "nlifecycle",
    conceptIt: "Conteggi nel ciclo di vita",
    conceptEn: "Lifecycle counts",
    textIt: "Hai 1 donatore e 12 pozzetti misurati. Quanto vale n indipendente?",
    textEn: "You have 1 donor and 12 measured wells. What is the independent n?",
    optionsIt: [
      "n = 12, uno per pozzetto",
      "n = 1: i 12 sono osservazioni replicate",
      "Dipende dal valore p",
    ],
    optionsEn: [
      "n = 12, one per well",
      "n = 1: the 12 are replicate observations",
      "It depends on the p-value",
    ],
    correct: 1,
    feedbackIt: "Le repliche tecniche non creano donatori nuovi.",
    feedbackEn: "Technical replicates do not create new donors.",
  },
  {
    id: "handoff",
    conceptIt: "Passaggio al biostatistico",
    conceptEn: "Handoff to the biostatistician",
    textIt: "Cosa fa N-Truth dopo la conferma del target?",
    textEn: "What does N-Truth do after target confirmation?",
    optionsIt: [
      "Suggerisce test, modello e potenza",
      "Consegna vincoli e domande allo statistico, senza suggerire test",
      "Approva il disegno sperimentale",
    ],
    optionsEn: [
      "It suggests a test, a model and power",
      "It hands constraints and questions to the statistician, suggesting no test",
      "It approves the experimental design",
    ],
    correct: 1,
    feedbackIt: "Chiarire la domanda non è approvarla; nessun test viene suggerito.",
    feedbackEn: "Clarifying the question is not approving it; no test is suggested.",
  },
];

/** Gate di comprensione leggero e non punitivo: sblocca la conferma del target.
 * Tentativi illimitati; lo skip motivato resta visibile e vale solo per il blocco. */
function ComprehensionGate({
  blockId,
  language,
  gate,
  onPass,
  onSkip,
}: {
  blockId: string;
  language: "it" | "en";
  gate: GateState;
  onPass: () => void;
  onSkip: (motivation: string) => void;
}) {
  const it = language === "it";
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [skipOpen, setSkipOpen] = useState(false);
  const [motivation, setMotivation] = useState("");
  const doneRef = useRef(false);

  useEffect(() => {
    setAnswers({});
    setSkipOpen(false);
    setMotivation("");
    doneRef.current = gate.passed || gate.skipped;
  }, [blockId, gate.passed, gate.skipped]);

  if (gate.passed || gate.skipped) {
    return (
      <p className="gate-done" role="status">
        <Check size={15} aria-hidden="true" />{" "}
        {gate.skipped
          ? it
            ? `Comprensione saltata con motivazione registrata · non è un'approvazione del disegno.`
            : `Comprehension skipped with recorded motivation · not a design approval.`
          : it
            ? `Comprensione registrata · non è un'approvazione del disegno.`
            : `Comprehension recorded · not a design approval.`}
      </p>
    );
  }

  const choose = (question: GateQuestion, index: number) => {
    setAnswers((current) => {
      if (current[question.id] === question.correct) return current;
      const next = { ...current, [question.id]: index };
      const allCorrect = GATE_QUESTIONS.every((item) => next[item.id] === item.correct);
      if (allCorrect && !doneRef.current) {
        doneRef.current = true;
        window.setTimeout(onPass, 0);
      }
      return next;
    });
  };

  return (
    <section className="gate" aria-labelledby={`gate-heading-${blockId}`}>
      <div className="gate-heading">
        <CircleHelp size={18} aria-hidden="true" />
        <div>
          <span className="eyebrow">
            {it ? "Prima di confermare · 3 mini-domande" : "Before confirming · 3 quick checks"}
          </span>
          <h3 id={`gate-heading-${blockId}`}>
            {it ? "Verifica di comprensione" : "Comprehension check"}
          </h3>
        </div>
      </div>
      <p className="muted gate-intro">
        {it
          ? "Ti aiutano a usare i concetti giusti, non ti valutano. Tentativi illimitati."
          : "They help you use the right concepts; they do not grade you. Unlimited attempts."}
      </p>
      {GATE_QUESTIONS.map((question) => {
        const answer = answers[question.id];
        const resolved = answer !== undefined;
        const correct = answer === question.correct;
        return (
          <fieldset key={question.id} className="gate-question">
            <legend>
              <span className="gate-concept">{it ? question.conceptIt : question.conceptEn}</span>
              {it ? question.textIt : question.textEn}
            </legend>
            {(it ? question.optionsIt : question.optionsEn).map((option, index) => (
              <label key={option} className={`gate-option${resolved && index === question.correct ? " is-correct" : ""}${resolved && index === answer && !correct ? " is-wrong" : ""}`}>
                <input
                  type="radio"
                  name={`gate-${blockId}-${question.id}`}
                  checked={answer === index}
                  onChange={() => choose(question, index)}
                />
                {option}
              </label>
            ))}
            {resolved && (
              <p className={`gate-feedback${correct ? " is-correct" : " is-wrong"}`} role="status">
                {correct
                  ? it ? `Corretto · ${question.feedbackIt}` : `Correct · ${question.feedbackEn}`
                  : it ? "Non ancora: rileggi il feedback e riprova." : "Not yet: re-read the feedback and retry."}
              </p>
            )}
          </fieldset>
        );
      })}
      <details className="gate-skip" open={skipOpen} onToggle={(event) => setSkipOpen((event.target as HTMLDetailsElement).open)}>
        <summary>{it ? "Salta con motivazione (revisori avanzati)" : "Skip with motivation (advanced reviewers)"}</summary>
        <label className="field-label">
          {it ? "Motivazione dello skip" : "Skip motivation"}
          <textarea
            value={motivation}
            onChange={(event) => setMotivation(event.target.value)}
            rows={2}
            placeholder={it ? "Almeno 20 caratteri: ruolo e motivo." : "At least 20 characters: role and reason."}
          />
        </label>
        <button
          type="button"
          className="button secondary compact"
          disabled={motivation.trim().length < 20}
          onClick={() => onSkip(motivation.trim())}
        >
          {it ? "Salta con motivazione" : "Skip with motivation"}
        </button>
      </details>
    </section>
  );
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
  gate,
  onGatePass,
  onGateSkip,
}: {
  id: string;
  active: boolean;
  block?: ExperimentBlock;
  compilation?: DesignCompilation;
  evidence?: EvidenceSpan;
  isDemo: boolean;
  language: "it" | "en";
  onConfirm: (draft: InferenceTargetDraft) => Promise<void> | void;
  gate?: GateState;
  onGatePass?: () => void;
  onGateSkip?: (motivation: string) => void;
}) {
  // Senza wiring del gate (uso standalone/test) la conferma resta sbloccata.
  const gateOk = !gate || gate.passed || gate.skipped;
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
      preservedEstimands.every(Boolean) &&
      gateOk,
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
          {status === "ready" ? (language === "it" ? "Struttura completa" : "Structure complete") : (language === "it" ? "Astensione" : "Abstained")}
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
        <strong>{support === "supported" ? (language === "it" ? "Scope strutturalmente compilato" : "Scope structurally compiled") : support === "conditional" ? (language === "it" ? "Scope condizionale" : "Conditional scope") : (language === "it" ? "Scope non definito" : "Scope not defined")}</strong>
        <small>{language === "it" ? "Questo stato descrive soltanto la struttura; non esprime adequacy o validità scientifica." : "This state describes structure only; it does not express adequacy or scientific validity."}</small>
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
        {gate && onGatePass && onGateSkip && block && (
          <div className="wide-field">
            <ComprehensionGate
              key={block.id}
              blockId={block.id}
              language={language}
              gate={gate}
              onPass={onGatePass}
              onSkip={onGateSkip}
            />
            {!gateOk && (
              <p className="gate-block-note" role="note">
                {language === "it"
                  ? "Rispondi alle 3 mini-domande qui sopra per attivare la conferma: ti aiutano, non ti valutano."
                  : "Answer the 3 quick checks above to enable confirmation: they help you, they do not grade you."}
              </p>
            )}
          </div>
        )}
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

/** Sezione di revisione per-blocco con tab contestuali L2.
 * Header sempre visibile (h2 ancorata ai test + stato percorso + HANDOFF_ONLY);
 * un solo livello ontologico visibile alla volta. */
export function BlockReviewTabs({
  block,
  output,
  compilation,
  evidence,
  isDemo,
  language,
  onConfirm,
  gate,
  onGatePass,
  onGateSkip,
  tab,
  onTabChange,
  active,
  onOpenQuestions,
}: {
  block: ExperimentBlock;
  output?: BlockReviewOutput;
  compilation?: DesignCompilation;
  evidence?: EvidenceSpan;
  isDemo: boolean;
  language: "it" | "en";
  onConfirm: (draft: InferenceTargetDraft) => Promise<void> | void;
  gate: GateState;
  onGatePass: () => void;
  onGateSkip: (motivation: string) => void;
  tab: BlockTabKey;
  onTabChange: (tab: BlockTabKey) => void;
  active: boolean;
  onOpenQuestions: () => void;
}) {
  const it = language === "it";
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onTabListKeyDown = (event: React.KeyboardEvent) => {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
    const target = event.target as HTMLElement;
    if (target.closest("input, select, textarea, a, button:not([role='tab'])")) return;
    event.preventDefault();
    const order = BLOCK_TABS.map((item) => item.key);
    const current = order.indexOf(tab);
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % order.length;
    if (event.key === "ArrowLeft") next = (current - 1 + order.length) % order.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = order.length - 1;
    onTabChange(order[next]);
    tabRefs.current[order[next]]?.focus();
  };

  return (
    <section
      id="review-output"
      className={`panel review-output-panel ${active ? "focused-panel" : ""}`}
      aria-labelledby="review-output-heading"
    >
      <div className="panel-heading">
        <div>
          <span className="eyebrow">
            {it ? "Output di revisione · non certificante" : "Review output · non-certifying"}
          </span>
          <h2 id="review-output-heading">
            {it ? "Methods e percorso di revisione" : "Methods and review path"}
          </h2>
        </div>
        <span className="panel-tools">
          {output && (
            <span className={`compiler-status review-status-${output.path_status}`}>
              {pathStatusLabel(output.path_status, language)}
            </span>
          )}
          <span className="compiler-status handoff-pin" data-testid="handoff-pin" title={it ? "Nessun test o modello suggerito" : "No test or model suggested"}>
            HANDOFF_ONLY
          </span>
        </span>
      </div>
      <p className="axis-boundary" data-testid="l2-boundary">
        {it
          ? "La determinabilità non è approvazione del disegno."
          : "Determinability is not design approval."}
      </p>
      <div
        className="block-tablist"
        role="tablist"
        aria-label={it ? "Sezioni del blocco in revisione" : "Sections of the block under review"}
        onKeyDown={onTabListKeyDown}
      >
        {BLOCK_TABS.map((item) => {
          const selected = tab === item.key;
          const label = it ? item.it : item.en;
          return (
            <button
              key={item.key}
              ref={(element) => {
                tabRefs.current[item.key] = element;
              }}
              type="button"
              role="tab"
              id={`blocktab-${block.id}-${item.key}`}
              aria-selected={selected}
              aria-controls={`blockpanel-${block.id}-${item.key}`}
              tabIndex={selected ? 0 : -1}
              className={`block-tab${selected ? " selected" : ""}`}
              onClick={() => onTabChange(item.key)}
            >
              {label}
            </button>
          );
        })}
      </div>
      <div
        role="tabpanel"
        id={`blockpanel-${block.id}-target`}
        aria-labelledby={`blocktab-${block.id}-target`}
        hidden={tab !== "target"}
        tabIndex={0}
      >
        <InferencePanel
          id="inference-panel"
          active={active}
          block={block}
          compilation={compilation}
          evidence={evidence}
          isDemo={isDemo}
          language={language}
          onConfirm={onConfirm}
          gate={gate}
          onGatePass={onGatePass}
          onGateSkip={onGateSkip}
        />
      </div>
      <div
        role="tabpanel"
        id={`blockpanel-${block.id}-counts`}
        aria-labelledby={`blocktab-${block.id}-counts`}
        hidden={tab !== "counts"}
        tabIndex={0}
      >
        <UnitCountsTab block={block} output={output} language={language} />
      </div>
      <div
        role="tabpanel"
        id={`blockpanel-${block.id}-alternatives`}
        aria-labelledby={`blocktab-${block.id}-alternatives`}
        hidden={tab !== "alternatives"}
        tabIndex={0}
      >
        <AlternativesTab block={block} output={output} language={language} onOpenQuestions={onOpenQuestions} />
      </div>
      <div
        role="tabpanel"
        id={`blockpanel-${block.id}-methods`}
        aria-labelledby={`blocktab-${block.id}-methods`}
        hidden={tab !== "methods"}
        tabIndex={0}
      >
        <MethodsTab output={output} language={language} />
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
  const [extendedCanvasEnabled, setExtendedCanvasEnabled] = useState(false);
  const [editing, setEditing] = useState(false);
  const [nodeType, setNodeType] = useState("CellCulture");
  const [nodeLabel, setNodeLabel] = useState("");
  const [relationType, setRelationType] = useState("nested_in");
  const [relationSource, setRelationSource] = useState(block.hierarchy.nodes[0]?.id ?? "");
  const [relationTarget, setRelationTarget] = useState(block.hierarchy.nodes[1]?.id ?? "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setExtendedCanvasEnabled(false);
    setEditing(false);
  }, [block.id]);

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
  const positions = useMemo(
    () => layoutNodes(nodes, block.hierarchy.relations),
    [nodes, block.hierarchy.relations],
  );
  const maxRank = Math.max(
    0,
    ...[...positions.values()].map((point) => Math.round((point.y - 26) / 138)),
  );
  const canvasHeight = Math.max(360, 26 + (maxRank + 1) * 138 + 34);
  const rankCounts = new Map<number, number>();
  for (const point of positions.values()) {
    const key = Math.round((point.y - 26) / 138);
    rankCounts.set(key, (rankCounts.get(key) ?? 0) + 1);
  }
  const maxRowWidth = Math.max(
    0,
    ...[...rankCounts.values()].map((count) => count * 196 + (count - 1) * 20),
  );
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
      <div className="graph-feature-gate">
        <Sparkles size={18} />
        <div>
          <strong>
            {language === "it"
              ? "Canvas esteso sperimentale · post-v0.1-D"
              : "Experimental extended canvas · post-v0.1-D"}
          </strong>
          <span>
            {language === "it"
              ? "Il percorso D0 usa wizard, tabelle e Core Profile. Il canvas libero richiede un opt-in esplicito e non fa parte del profilo validato."
              : "The D0 path uses the wizard, tables and Core Profile. The free canvas requires explicit opt-in and is not part of the validated profile."}
          </span>
        </div>
        <label>
          <input
            type="checkbox"
            checked={extendedCanvasEnabled}
            onChange={(event) => {
              setExtendedCanvasEnabled(event.target.checked);
              if (!event.target.checked) setEditing(false);
            }}
          />
          {language === "it"
            ? "Abilita canvas esteso sperimentale"
            : "Enable experimental extended canvas"}
        </label>
      </div>
      {!extendedCanvasEnabled && (
        <div className="graph-gated-placeholder">
          <GitBranch size={27} />
          <strong>{language === "it" ? "Canvas non attivo" : "Canvas is not active"}</strong>
          <p>
            {language === "it"
              ? "La struttura resta disponibile nel riepilogo e nelle tabelle D0 senza attivare funzioni sperimentali."
              : "The structure remains available in the D0 summary and tables without enabling experimental features."}
          </p>
        </div>
      )}
      {extendedCanvasEnabled && <>
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
      <div className="graph-scroll">
      <div
        className="graph-canvas"
        role="group"
        aria-label={`Grafo con ${nodes.length} nodi e ${relations.length} relazioni`}
      >
        <div
            className="graph-stage"
            style={{
              height: `${canvasHeight}px`,
              minWidth: `${Math.max(720, maxRowWidth + 24)}px`,
              transform: `scale(${zoom})`,
            }}
          >
            <svg className="graph-edges" viewBox={`0 0 720 ${canvasHeight}`} aria-hidden="true">
              <defs>
                <marker id="arrow" markerWidth="9" markerHeight="9" refX="7.5" refY="4.5" orient="auto">
                  <path d="M0,0 L9,4.5 L0,9 Z" fill="#5c6d7e" />
                </marker>
              </defs>
              {relations.map((relation) => {
                const source = positions.get(relation.source);
                const target = positions.get(relation.target);
                if (!source || !target) return null;
                const sx = source.x + NODE_W / 2;
                const sy = source.y + NODE_H / 2;
                const tx = target.x + NODE_W / 2;
                const ty = target.y + NODE_H / 2;
                const downward = ty >= sy;
                const x1 = sx;
                const y1 = downward ? sy + NODE_H / 2 : sy - NODE_H / 2;
                const x2 = tx;
                const y2 = downward ? ty - NODE_H / 2 : ty + NODE_H / 2;
                const bend = downward
                  ? Math.max(28, (y2 - y1) / 2)
                  : Math.max(48, Math.abs(x2 - x1) / 2);
                const d = downward
                  ? `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`
                  : `M ${x1 < x2 ? x1 + NODE_W / 2 : x1 - NODE_W / 2} ${y1} C ${x1 + (x2 - x1) / 2} ${y1}, ${x1 + (x2 - x1) / 2} ${y2}, ${x2 < x1 ? x2 + NODE_W / 2 : x2 - NODE_W / 2} ${y2}`;
                return (
                  <path key={relation.id} className="graph-edge" d={d} markerEnd="url(#arrow)" />
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
                title={`${item.type} · affidabilità lettura automatica ${item.confidence.toFixed(2)} (non probabilità di verità)`}
                onClick={() => item.evidence_ids[0] && onEvidenceSelect(item.evidence_ids[0])}
              >
                <small>{NODE_LABEL[item.type] ?? item.type}</small>
                <strong>{item.label}</strong>
                <span className="graph-node-meta">
                  {item.count != null && <em>n = {item.count}</em>}
                  <em>conf {item.confidence.toFixed(2)}</em>
                </span>
              </button>
            );
          })}
          {!nodes.length && <EmptyState language={language} />}
          <svg className="graph-edge-labels" viewBox={`0 0 720 ${canvasHeight}`} aria-hidden="true">
            {relations.map((relation, index) => {
              const source = positions.get(relation.source);
              const target = positions.get(relation.target);
              if (!source || !target) return null;
              // L'etichetta vive nel varco tra le righe: midpoint del segmento
              // tra i bordi delle card (stessa geometria degli edge disegnati).
              const sx = source.x + NODE_W / 2;
              const sy = source.y + NODE_H / 2;
              const tx = target.x + NODE_W / 2;
              const ty = target.y + NODE_H / 2;
              const downward = ty >= sy;
              const x1 = sx;
              const y1 = downward ? sy + NODE_H / 2 : sy - NODE_H / 2;
              const x2 = tx;
              const y2 = downward ? ty - NODE_H / 2 : ty + NODE_H / 2;
              const spread = (index - (relations.length - 1) / 2) * 16;
              const midX = (x1 + x2) / 2;
              const midY = Math.min(
                canvasHeight - 10,
                Math.max(14, (y1 + y2) / 2 + spread * 0.6),
              );
              return (
                <text key={`lbl-${relation.id}`} className="graph-edge-label" x={midX} y={midY} textAnchor="middle">
                  {relation.type.replaceAll("_", " ")}
                </text>
              );
            })}
          </svg>
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
      </>}
    </div>
  );
}

const NODE_W = 196;
const NODE_H = 84;
const ROW_H = 138;
const COL_PITCH = 216;

/** Layout stratificato: rank = cammino piu' lungo dalle radici; righe centrate. */
function layoutNodes(
  nodes: GraphNode[],
  relations: { source: string; target: string }[],
): Map<string, { x: number; y: number }> {
  const ids = nodes.map((item) => item.id);
  const idSet = new Set(ids);
  const edges = relations.filter((item) => idSet.has(item.source) && idSet.has(item.target));
  const incoming = new Map<string, string[]>(ids.map((id) => [id, []]));
  const outgoing = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const edge of edges) {
    incoming.get(edge.target)!.push(edge.source);
    outgoing.get(edge.source)!.push(edge.target);
  }
  const rank = new Map<string, number>(ids.map((id) => [id, 0]));
  // longest-path rank (iterativo, ordine topologico approssimato a ripetizioni)
  for (let pass = 0; pass < ids.length; pass += 1) {
    let changed = false;
    for (const edge of edges) {
      const next = rank.get(edge.source)! + 1;
      if (next > rank.get(edge.target)!) {
        rank.set(edge.target, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const byRank = new Map<number, string[]>();
  for (const id of ids) {
    const key = rank.get(id)!;
    (byRank.get(key) ?? byRank.set(key, []).get(key)!).push(id);
  }
  const positions = new Map<string, { x: number; y: number }>();
  const stageW = 720;
  const ranks = [...byRank.keys()].sort((a, b) => a - b);
  ranks.forEach((key, rowIndex) => {
    const row = byRank.get(key)!.slice().sort(); // ordine stabile
    const pitch = COL_PITCH;
    const totalW = row.length * NODE_W + (row.length - 1) * (pitch - NODE_W);
    const startX = Math.max(12, (stageW - totalW) / 2 + (pitch - NODE_W) / 2);
    row.forEach((id, colIndex) => {
      positions.set(id, { x: startX + colIndex * pitch, y: 26 + rowIndex * ROW_H });
    });
  });
  return positions;
}

function graphCanvasHeight(nodeCount: number, relations: { source: string; target: string }[]): number {
  const idSet = new Set(nodeCount ? [] : []);
  void idSet;
  const rows = Math.max(1, nodeCount);
  void relations;
  return rows; // placeholder rimpiazzato dal chiamante
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
  onApply: (patch: CorrectionPatch, rationale: string, reason: string) => Promise<void> | void;
  onExport: () => void;
  hasCandidate: boolean;
  exportAllowed: boolean;
}) {
  const current = block?.n_statements[0]?.value;
  const [nextValue, setNextValue] = useState(String(current ?? ""));
  const [rationale, setRationale] = useState("");
  const [reason, setReason] = useState("typo");
  const [busy, setBusy] = useState(false);
  const [refinement, setRefinement] = useState<SpanRefinement | null>(null);

  useEffect(() => setRefinement(null), [block?.id, current]);

  useEffect(() => setNextValue(String(current ?? "")), [block?.id, current]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const parsed = Number(nextValue);
    if (!Number.isInteger(parsed) || parsed < 0 || rationale.trim().length < 8) return;
    setBusy(true);
    try {
      const patch: CorrectionPatch = [
        { op: "replace", path: "/n_statements/0/value", value: parsed },
      ];
      if (refinement) patch.push(refinementPatchEntry(refinement));
      await onApply(patch, rationale.trim(), reason);
      setRationale("");
      setRefinement(null);
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
      <div className="correction-body">
      {block && (block.count_records.length > 0 || block.exclusion_records.length > 0) ? (
        <CanonicalCorrectionForm
          block={block}
          evidence={evidence}
          language={language}
          isDemo={isDemo}
          onApply={onApply}
        />
      ) : !block?.n_statements.length ? (
        <p className="muted empty-copy">{language === "it" ? "Nessuna menzione di n modificabile in questo blocco." : "No editable n statement in this block."}</p>
      ) : (
        <form onSubmit={submit} className="correction-form">
          <div className="diff-row">
            <span><small>{language === "it" ? "Campo" : "Field"}</small><code>/n_statements/0/value</code></span>
            <span><small>{language === "it" ? "Valore precedente" : "Previous value"}</small><del>n = {current ?? "—"}</del></span>
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
          <div className="correction-footnote"><Link2 size={14} aria-hidden="true" /> {evidence ? evidenceLocator(evidence) : (language === "it" ? "nessuna evidenza collegata" : "no linked evidence")}</div>
          {evidence && (
            <details className="span-refine-drawer">
              <summary>{language === "it" ? "Raffina span di evidenza" : "Refine evidence span"}</summary>
              <SpanLocator
                evidence={evidence}
                language={language}
                onApply={(value) => {
                  setRefinement(value);
                  setRationale((currentRationale) =>
                    currentRationale.trim().length >= 8
                      ? currentRationale
                      : `${value.locator}: ${currentRationale}`.trim(),
                  );
                }}
              />
            </details>
          )}
          {refinement && (
            <p className="span-refined-note" data-testid="span-refined-note">
              {language === "it" ? "Evidenza raffinata" : "Refined evidence"}: <code>{refinement.locator}</code>
            </p>
          )}
          <div className="form-actions">
            <span className="candidate-note"><Sparkles size={15} /> {isDemo ? (language === "it" ? "Demo non scientifica" : "Non-scientific demo") : (language === "it" ? "Annotazione candidata, non gold" : "Candidate annotation, not gold")}</span>
            <button className="button primary compact" disabled={busy || rationale.trim().length < 8 || nextValue === String(current ?? "")}>
              {busy ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />} {language === "it" ? "Applica e ricalcola" : "Apply and recalculate"}
            </button>
          </div>
        </form>
      )}
      <div className="audit-panel">
        <div className="audit-title"><span><History size={16} aria-hidden="true" /> {language === "it" ? "Traccia di audit" : "Audit trail"}</span><button disabled={!hasCandidate || !exportAllowed} onClick={onExport}>{language === "it" ? "Esporta candidate" : "Export candidates"}</button></div>
        {events.length ? events.slice(-3).reverse().map((event) => (
          <div className="audit-entry" key={event.id}>
            <span className="avatar" aria-hidden="true">{(event.actor_role ?? "R").slice(0, 1).toUpperCase()}</span>
            <span>
              <strong>{event.action === "apply" ? (language === "it" ? "Correzione applicata" : "Correction applied") : event.action === "undo" ? (language === "it" ? "Correzione annullata" : "Correction undone") : (language === "it" ? "Correzione ripristinata" : "Correction restored")}</strong>
              <small>{event.actor_role ?? (language === "it" ? "ruolo legacy non registrato" : "legacy role not recorded")} · {formatAuditTime(event.recorded_at ?? event.at, language)}</small>
              <small>{event.correction_id}</small>
            </span>
          </div>
        )) : <p className="muted">{language === "it" ? "Nessuna correzione registrata per questo blocco." : "No correction recorded for this block."}</p>}
        {events.length > 3 && (
          <details className="audit-full">
            <summary>
              {language === "it"
                ? `Storia completa delle revisioni (${events.length})`
                : `Full revision history (${events.length})`}
            </summary>
            <ul>
              {events.map((event) => (
                <li key={event.id}>
                  {event.action} · {event.correction_id} · {event.actor_role ?? "—"} · {formatAuditTime(event.recorded_at ?? event.at, language)}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
      </div>
    </section>
  );
}

function ImportDialog({
  apiState,
  uiLanguage,
  onClose,
  onAnalysis,
  onQuickDesign,
  initialWizardStep = 1,
}: {
  apiState: "checking" | "online" | "offline";
  uiLanguage: "it" | "en";
  onClose: () => void;
  onAnalysis: (result: AnalysisResponse) => void;
  onQuickDesign: (result: QuickDesignV8Response) => void;
  initialWizardStep?: number;
}) {
  const [mode, setMode] = useState<"v8" | "v7">("v8");
  const dialogRef = useRef<HTMLElement>(null);
  const [source, setSource] = useState("");
  const [out, setOut] = useState("./ntruth-out");
  const [domain, setDomain] = useState("quantitative_microscopy");
  const [language, setLanguage] = useState<"it" | "en">(uiLanguage);
  const [acknowledged, setAcknowledged] = useState(false);
  const [domainNotice, setDomainNotice] = useState<Report["domain_transparency"]>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (apiState !== "online" || mode !== "v7") return;
    preflight(domain).then(setDomainNotice).catch(() => undefined);
  }, [apiState, domain, mode]);

  useEffect(() => {
    const firstFocusable = dialogRef.current?.querySelector<HTMLElement>(
      "button, input, select, textarea, [tabindex]:not([tabindex='-1'])",
    );
    firstFocusable?.focus();
  }, []);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    setError(undefined);
    setBusy(true);
    try {
      const result = await analyzeV7({
        source: source.trim(),
        out: out.trim(),
        language,
        domain,
        acknowledge_unvalidated_domain: acknowledged,
      });
      onAnalysis(result);
    } catch (caught) {
      if (
        caught instanceof ApiError &&
        caught.status === 409 &&
        apiErrorCode(caught) === "SCIENTIFIC_REVIEW_REQUIRED"
      ) {
        const issue = apiErrorIssueId(caught);
        const title = uiLanguage === "it"
          ? "Revisione scientifica richiesta"
          : "Scientific review required";
        setError(`${title}${issue ? ` · ${issue}` : ""}. ${caught.message}`);
      } else if (
        caught instanceof ApiError &&
        caught.status === 409 &&
        apiErrorCode(caught) === "domain_acknowledgement_required"
      ) {
        setError(uiLanguage === "it" ? "Il dominio richiede una conferma esplicita prima dell’analisi." : "The domain requires explicit acknowledgement before analysis.");
      } else {
        setError(caught instanceof Error ? caught.message : (uiLanguage === "it" ? "Analisi non avviata." : "Analysis was not started."));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDialogKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab" || !dialogRef.current) return;
    const focusable = Array.from(
      dialogRef.current.querySelectorAll<HTMLElement>(
        "button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
      ),
    ).filter((element) => !element.hasAttribute("hidden"));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !dialogRef.current.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
        onKeyDown={handleDialogKeyDown}
      >
        <div className="dialog-header">
          <div><span className="eyebrow">{uiLanguage === "it" ? "Nessun upload · elaborazione locale" : "No upload · local processing"}</span><h2 id="import-title">{uiLanguage === "it" ? "Compila o importa" : "Compile or import"}</h2></div>
          <button aria-label={uiLanguage === "it" ? "Chiudi" : "Close"} onClick={onClose}><X size={20} /></button>
        </div>
        {apiState !== "online" ? (
          <div className="offline-message"><Database size={22} /><div><strong>{uiLanguage === "it" ? "API locale non raggiungibile" : "Local API is unreachable"}</strong><p>{uiLanguage === "it" ? <>Avvia <code>ntruth-api</code>; nel frattempo resta disponibile la demo sintetica.</> : <>Start <code>ntruth-api</code>; the synthetic demo remains available.</>}</p></div></div>
        ) : (
          <div className="import-form">
            <fieldset className="workflow-selector">
              <legend>{uiLanguage === "it" ? "Contratto di elaborazione" : "Processing contract"}</legend>
              <label>
                <input
                  type="radio"
                  name="workflow-contract"
                  checked={mode === "v8"}
                  onChange={() => { setMode("v8"); setError(undefined); }}
                />
                {uiLanguage === "it" ? "Quick Design v8 canonico" : "Canonical Quick Design v8"}
              </label>
              <label>
                <input
                  type="radio"
                  name="workflow-contract"
                  checked={mode === "v7"}
                  onChange={() => { setMode("v7"); setError(undefined); }}
                />
                {uiLanguage === "it" ? "Flusso storico v7 deprecato" : "Deprecated historical v7 flow"}
              </label>
            </fieldset>
            {mode === "v8" ? (
              <>
                <div className="canonical-contract-note">
                  <strong>PRD v8 · guided builder · canonical lane atomica</strong>
                  <p>{uiLanguage === "it" ? "Il PREVIEW è solo revisione. CONFIRM esegue atomicamente il contratto canonico e conserva la submission esclusivamente come snapshot di audit non eseguibile." : "PREVIEW is review-only. CONFIRM atomically executes the canonical contract and retains the submission only as a non-executable audit snapshot."}</p>
                </div>
                <QuickDesignWizard language={uiLanguage} initialStep={initialWizardStep} onComplete={onQuickDesign} />
              </>
            ) : (
              <>
                <div className="legacy-contract-warning" role="note">
                  <strong>{uiLanguage === "it" ? "Compatibilità storica v7 · deprecata" : "Historical v7 compatibility · deprecated"}</strong>
                  <p>{uiLanguage === "it" ? "Questo percorso usa esclusivamente /v7/analyze e viene adattato in una presentazione neutra." : "This path uses only /v7/analyze and is adapted to a neutral presentation."}</p>
                </div>
                <label className="field-label">{uiLanguage === "it" ? "File o cartella sorgente" : "Source file or folder"}
                  <input aria-label={uiLanguage === "it" ? "File o cartella sorgente" : "Source file or folder"} required value={source} onChange={(event) => setSource(event.target.value)} placeholder="/percorso/locale/metodi-e-sample-sheet" />
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
              </>
            )}
            {mode === "v7" && (
              <>
                {error && <p className="form-error" role="alert">{error}</p>}
                <div className="dialog-actions">
                  <button type="button" className="button secondary" onClick={onClose}>{uiLanguage === "it" ? "Annulla" : "Cancel"}</button>
                  <button
                    type="button"
                    className="button primary"
                    disabled={busy || !source.trim() || Boolean(domainNotice?.requires_acknowledgement && !acknowledged)}
                    onClick={() => void submit()}
                  >
                    {busy ? <LoaderCircle className="spin" size={18} /> : <Beaker size={18} />} {uiLanguage === "it" ? "Avvia analisi v7 deprecata" : "Start deprecated v7 analysis"}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function EmptyState({ language = "it" }: { language?: "it" | "en" } = {}) {
  return (
    <div className="empty-state">
      <RotateCcw size={22} aria-hidden="true" />
      <span>{language === "it" ? "Nessun dato disponibile per questa vista." : "No data available for this view."}</span>
    </div>
  );
}

/** L1 — barra di contesto: le 5 informazioni per orientarsi senza scroll.
 * Additiva: non sposta logica, legge solo lo stato esistente. */
function WorkspaceSummaryStrip({
  block,
  blockIndex,
  blockCount,
  output,
  compilation,
  decisiveOpen,
  domainBlocked,
  privacyBlocked,
  language,
}: {
  block?: ExperimentBlock;
  blockIndex: number;
  blockCount: number;
  output?: BlockReviewOutput;
  compilation?: DesignCompilation;
  decisiveOpen: number;
  domainBlocked: boolean;
  privacyBlocked: boolean;
  language: "it" | "en";
}) {
  const it = language === "it";
  const experimentalUnit =
    block?.unit_assessments.find((item) => item.experimental_unit)?.experimental_unit ?? "—";
  const independentN =
    block?.unit_assessments.find((item) => item.n_independent != null)?.n_independent ?? null;
  return (
    <div className="workspace-context-bar" role="region" aria-label={it ? "Riepilogo del blocco" : "Block summary"}>
      <div className="context-block">
        <span className="context-label">{it ? "Blocco" : "Block"}</span>
        <strong>{block ? `${blockIndex + 1}/${blockCount} · ${block.title || block.id}` : "—"}</strong>
      </div>
      <span className="context-sep" aria-hidden="true">·</span>
      <div className="context-block">
        <span className="context-label">{it ? "Percorso" : "Path"}</span>
        <strong>{output ? output.path_status : (compilation?.status === "ready" ? (it ? "Struttura completa" : "Structure complete") : (it ? "Astensione" : "Abstained"))}</strong>
      </div>
      <span className="context-sep" aria-hidden="true">·</span>
      <div className="context-block">
        <span className="context-label">{it ? "Si può decidere dal testo?" : "Decidable from text?"}</span>
        <strong>{output?.determinability.state ?? "—"}</strong>
      </div>
      <span className="context-sep" aria-hidden="true">·</span>
      <div className="context-block">
        <span className="context-label">{it ? "Disegno adeguato?" : "Adequate design?"}</span>
        <strong>{output?.design_adequacy.finding ?? "—"}</strong>
      </div>
      <span className="context-sep" aria-hidden="true">·</span>
      <div className="context-block">
        <span className="context-label">{it ? "Unità sperimentale · n indipendente" : "Experimental unit · independent n"}</span>
        <strong>{experimentalUnit}{independentN != null ? ` · n = ${independentN}` : ""}</strong>
      </div>
      <span className="context-sep" aria-hidden="true">·</span>
      <div className="context-block">
        <span className="context-label">{it ? "Prossima azione" : "Next action"}</span>
        <strong className={`context-gate ${decisiveOpen > 0 || domainBlocked || privacyBlocked ? "is-blocking" : "is-ok"}`}>
          {decisiveOpen > 0
            ? it ? `${decisiveOpen} domande decisive aperte` : `${decisiveOpen} decisive questions open`
            : domainBlocked
              ? it ? "Conferma il limite di dominio" : "Acknowledge the domain limit"
              : privacyBlocked
                ? it ? "Completa la revisione privacy" : "Complete the privacy review"
                : it ? "Nessun blocco: procedi all'handoff" : "No blockers: proceed to handoff"}
        </strong>
      </div>
    </div>
  );
}
