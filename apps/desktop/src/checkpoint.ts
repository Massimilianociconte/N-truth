/**
 * Checkpoint locale delle sessioni di lavoro (PRD: nessun dato lascia la macchina).
 *
 * - Scrittura frequente e debounced a ogni modifica rilevante + flush su
 *   `pagehide`/`beforeunload`/`visibilitychange(hidden)`.
 * - Rilevamento chiusura brusca: ogni salvataggio marca `status:"open"`;
 *   solo uno scarico volontario (refresh/chiusura) scrive `status:"closed"`.
 *   Al boot, un checkpoint ancora `open` significa terminazione non volontaria
 *   (crash browser/pc) → ripristino con banner di recovery.
 * - Corruzione: un payload non leggibile viene messo da parte in `*.corrupt`
 *   e ignorato (fail-closed, mai blocco dell'app).
 * - Multi-tab: ultimo scrittore vince (strumento locale single-operatore);
 *   il `tab_id` permette di riconoscere il checkpoint di un'altra scheda.
 */

const KEY = "ntruth.checkpoint.v1";
const CORRUPT_KEY = `${KEY}.corrupt`;
const VERSION = 1;

export interface CheckpointUiState {
  active_view: string;
  selected_block?: string;
  selected_alert?: string;
  selected_evidence?: string;
  collapsed: Record<string, boolean>;
  domain_acknowledged: boolean;
}

export interface CheckpointPayload {
  version: number;
  tab_id: string;
  saved_at: string;
  status: "open" | "closed";
  surface: "welcome" | "workspace";
  is_demo: boolean;
  session_id?: string;
  report?: unknown;
  quick_design?: unknown;
  ui?: CheckpointUiState;
  corrections?: unknown;
  candidate_exports?: unknown;
  audit?: unknown;
  privacy?: unknown;
  share?: unknown;
}

export function currentTabId(): string {
  try {
    const existing = sessionStorage.getItem("ntruth.tab_id");
    if (existing) return existing;
    const created = `tab-${Math.random().toString(36).slice(2, 10)}`;
    sessionStorage.setItem("ntruth.tab_id", created);
    return created;
  } catch {
    return "tab-unknown";
  }
}

export function saveCheckpoint(patch: Partial<CheckpointPayload>): void {
  try {
    const previous = readRaw();
    const merged = { ...(previous ?? {}), ...patch } as CheckpointPayload;
    const next: CheckpointPayload = {
      ...merged,
      surface: merged.surface ?? "welcome",
      is_demo: merged.is_demo ?? false,
      version: VERSION,
      tab_id: currentTabId(),
      saved_at: new Date().toISOString(),
      status: patch.status ?? "open",
    };
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // QuotaExceeded o storage non disponibile: il lavoro resta in memoria;
    // il checkpoint è un beneficio, mai un blocco.
  }
}

export function markCheckpointClosed(): void {
  try {
    const previous = readRaw();
    if (!previous) return;
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ ...previous, status: "closed", saved_at: new Date().toISOString() }),
    );
  } catch {
    /* noop */
  }
}

export function clearCheckpoint(): void {
  try {
    window.localStorage.removeItem(KEY);
    window.localStorage.removeItem(CORRUPT_KEY);
  } catch {
    /* noop */
  }
}

function readRaw(): CheckpointPayload | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CheckpointPayload;
    return parsed?.version === VERSION ? parsed : null;
  } catch {
    return null;
  }
}

export function loadCheckpoint(): {
  payload: CheckpointPayload;
  abrupt: boolean;
} | null {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as CheckpointPayload;
    if (parsed?.version !== VERSION || parsed.status === "closed") {
      return parsed?.version === VERSION
        ? { payload: parsed, abrupt: false }
        : null;
    }
    return { payload: parsed, abrupt: true };
  } catch {
    // Payload corrotto (crash a metà scrittura): mettilo da parte e riparti pulito.
    try {
      window.localStorage.setItem(CORRUPT_KEY, raw);
      window.localStorage.removeItem(KEY);
    } catch {
      /* noop */
    }
    return null;
  }
}

export function corruptBackupExists(): boolean {
  try {
    return Boolean(window.localStorage.getItem(CORRUPT_KEY));
  } catch {
    return false;
  }
}
