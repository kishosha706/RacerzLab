/**
 * Import debug logger - local-only instrumentation for diagnosing import failures.
 *
 * Stores last 50 entries in memory. Optionally persists to localStorage
 * when DEBUG_IMPORT=1 is set.
 *
 * Usage:
 *   import { importDebug } from "../utils/importDebug";
 *   importDebug.log("picker_selected", { fileName: "test.ibt" });
 */

const MAX_ENTRIES = 50;
const STORAGE_KEY = "racelab_import_debug_log";

export interface ImportDebugEntry {
  timestamp: string;
  step: string;
  status: "started" | "success" | "error" | "info";
  data?: Record<string, unknown>;
  durationMs?: number;
}

let entries: ImportDebugEntry[] = [];
let lastTimestamp = 0;

function isDebugEnabled(): boolean {
  try {
    return localStorage.getItem("DEBUG_IMPORT") === "1";
  } catch {
    return false;
  }
}

function persist(entries: ImportDebugEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)));
  } catch {
    // localStorage full - ignore
  }
}

export const importDebug = {
  /** Log an import step. Always logged for import-related steps. */
  log(step: string, data?: Record<string, unknown>): void {
    const now = Date.now();
    const entry: ImportDebugEntry = {
      timestamp: new Date().toISOString(),
      step,
      status: "info",
      data,
      durationMs: lastTimestamp ? now - lastTimestamp : undefined,
    };
    lastTimestamp = now;
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) entries = entries.slice(-MAX_ENTRIES);
    if (isDebugEnabled()) persist(entries);
    // Always log import steps to console in dev
    if (step.startsWith("import_") || step.startsWith("picker_") || step.startsWith("on_") ||
        step.startsWith("sessions_") || step.startsWith("open_") || step === "error" ||
        step.startsWith("startup_")) {
      console.debug(`[ImportDebug] ${entry.timestamp} ${step}`, data ?? "");
    }
  },

  /** Log a started step with a timer. */
  start(step: string, data?: Record<string, unknown>): void {
    const now = Date.now();
    const entry: ImportDebugEntry = {
      timestamp: new Date().toISOString(),
      step,
      status: "started",
      data: { ...data, _start: now },
    };
    lastTimestamp = now;
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) entries = entries.slice(-MAX_ENTRIES);
    if (isDebugEnabled()) persist(entries);
    console.debug(`[ImportDebug] START ${step}`, data ?? "");
  },

  /** Mark the last started step as success. */
  success(step: string, data?: Record<string, unknown>): void {
    const now = Date.now();
    // Find the matching start entry
    const startIdx = [...entries].reverse().findIndex(e => e.step === step && e.status === "started");
    const startEntry = startIdx >= 0 ? entries[entries.length - 1 - startIdx] : null;
    const startTime = startEntry?.data?._start as number | undefined;
    const entry: ImportDebugEntry = {
      timestamp: new Date().toISOString(),
      step,
      status: "success",
      data,
      durationMs: startTime ? now - startTime : undefined,
    };
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) entries = entries.slice(-MAX_ENTRIES);
    if (isDebugEnabled()) persist(entries);
    console.debug(`[ImportDebug] OK    ${step}${entry.durationMs ? ` (${entry.durationMs}ms)` : ""}`, data ?? "");
  },

  /** Log an error step. */
  error(step: string, errorMsg: string, data?: Record<string, unknown>): void {
    const entry: ImportDebugEntry = {
      timestamp: new Date().toISOString(),
      step,
      status: "error",
      data: { ...data, error: errorMsg },
    };
    entries.push(entry);
    if (entries.length > MAX_ENTRIES) entries = entries.slice(-MAX_ENTRIES);
    if (isDebugEnabled()) persist(entries);
    console.error(`[ImportDebug] ERROR ${step}: ${errorMsg}`, data ?? "");
  },

  /** Get the full debug log. */
  getLog(): ImportDebugEntry[] {
    return [...entries];
  },

  /** Clear the debug log. */
  clear(): void {
    entries = [];
    lastTimestamp = 0;
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  },
};
