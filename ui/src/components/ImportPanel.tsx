/**
 * ImportPanel - unified import UI with native Tauri picker and browser fallback.
 *
 * Desktop mode (Tauri):
 * - native telemetry file picker
 *
 * Browser mode:
 * - Hidden file input for supported telemetry/setup/map files (existing behavior)
 * - "Import telemetry" button
 *
 * Imported track maps are applied automatically when a matching local RacerZLab cached map is found.
 */

import { Check, FileArchive, HardDrive, ShieldCheck } from "lucide-react";
import { useCallback, useState } from "react";
import { importIbtFileFromPath } from "../api/client";
import { isTauri } from "../utils/env";
import { pickTelemetryFile } from "../utils/tauriImport";
import { importDebug } from "../utils/importDebug";
import type { TrackMapResolution } from "../types/telemetry";

type ImportPanelProps = {
  onImportComplete: (runId?: string | null, trackMap?: TrackMapResolution | null) => boolean | Promise<boolean>;
  importing: boolean;
  importStage: string | null;
  error: string | null;
  status: string | null;
  importOutcome: "run" | "map" | null;
  /** Browser file input ref for fallback */
  fileInputRef: React.RefObject<HTMLInputElement>;
  /** Browser file input change handler */
  onFileSelected: (file: File) => void;
  /** Browser import click handler */
  onImportClick: () => void;
};

const IMPORT_STEPS = [
  "Select file",
  "Decode archive",
  "Qualify evidence",
  "Open cockpit",
] as const;

function importProgressIndex(
  stage: string | null,
  status: string | null,
  busy: boolean,
): number | null {
  if (status && !busy) return IMPORT_STEPS.length;
  if (!busy && !stage) return null;
  const normalized = (stage ?? "").toLowerCase();
  if (/opening|refreshing|cockpit/.test(normalized)) return 3;
  if (/qualif|analy|cache|index|manifest|setup|map/.test(normalized)) return 2;
  return 1;
}

function splitImportError(error: string): { summary: string[]; technical: string | null } {
  const lines = error.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const technical = lines.find((line) => line.startsWith("Technical detail:"))?.replace("Technical detail:", "").trim() ?? null;
  const summary = lines.filter((line) => !line.startsWith("Technical detail:"));
  return {
    summary: summary.length > 0 ? summary : [
      "Import failed",
      "The telemetry file could not be processed.",
      "No completed run was created.",
      "Try importing again, or choose a different .ibt file.",
    ],
    technical,
  };
}

function ImportRecoveryMessage({ error }: { error: string }) {
  const { summary, technical } = splitImportError(error);
  const [title, ...details] = summary;
  const importWasSaved = summary.some((line) => /\bimport(?:ed)?\b.*\bsaved\b/i.test(line));
  return (
    <div className="import-alert import-alert-error import-recovery-card" aria-live="polite">
      <strong>{title || "Import failed"}</strong>
      {details.map((line) => <p key={line}>{line}</p>)}
      {!importWasSaved && !details.some((line) => line.includes("No completed run was created")) && (
        <p>No completed run was created.</p>
      )}
      {!importWasSaved && !details.some((line) => line.includes("Try importing again")) && (
        <p>Try importing again, or choose a different .ibt file.</p>
      )}
      {technical && (
        <details>
          <summary>Technical detail</summary>
          <p>{technical}</p>
        </details>
      )}
    </div>
  );
}

export function ImportPanel({
  onImportComplete, importing, importStage, error, status,
  importOutcome,
  fileInputRef, onFileSelected, onImportClick,
}: ImportPanelProps) {
  const desktop = isTauri();
  const [nativeBusy, setNativeBusy] = useState(false);
  const [nativeStage, setNativeStage] = useState<string | null>(null);
  const [nativeError, setNativeError] = useState<string | null>(null);
  const [nativeStatus, setNativeStatus] = useState<string | null>(null);
  const [nativeOutcome, setNativeOutcome] = useState<"run" | null>(null);

  const busy = importing || nativeBusy;
  const displayedStage = nativeStage ?? importStage;
  const displayedError = nativeError ?? error;
  const displayedStatus = nativeStatus ?? status;
  const displayedOutcome = nativeOutcome ?? importOutcome;
  const progressIndex = displayedError || displayedOutcome === "map"
    ? null
    : importProgressIndex(displayedStage, displayedStatus, busy);

  const completeImport = useCallback(async (runId?: string | null, trackMap?: TrackMapResolution | null) => {
    setNativeStage(runId ? "Opening cockpit..." : "Refreshing local library...");
    const completed = await onImportComplete(runId, trackMap);
    if (!completed) {
      throw new Error([
        "Import saved",
        "The telemetry run was imported and saved, but the active session changed before it could be opened.",
        "Open the saved run from Sessions when you are ready.",
      ].join("\n"));
    }
  }, [onImportComplete]);

  // ── Native telemetry file picker (primary) ────────────────────
  const handleNativeTelemetryPick = useCallback(async () => {
    importDebug.start("picker_opened", { source: "native_file" });
    const result = await pickTelemetryFile();
    if (result.cancelled) {
      importDebug.log("picker_cancelled", { source: "native_file" });
      return;
    }
    if (!result.filePath) {
      importDebug.error("picker_selected", "No file path returned", { source: "native_file" });
      return;
    }
    const fileName = result.filePath.split(/[/\\]/).pop() ?? result.filePath;
    importDebug.log("picker_selected", { source: "native_file", fileName });
    setNativeBusy(true);
    setNativeStage("Reading .ibt and decoding telemetry...");
    setNativeError(null);
    setNativeStatus(null);
    setNativeOutcome(null);
    try {
      importDebug.start("import_request_started", { source: "native_file", fileName });
      const resp = await importIbtFileFromPath(result.filePath);
      importDebug.success("import_request_finished", {
        source: "native_file", fileName,
        run_id: resp.run_id,
        track_map_status: resp.track_map?.status,
      });
      if (!resp.run_id) {
        throw new Error([
          "Import failed",
          resp.status.message || "The telemetry file could not be processed.",
          "No completed run was created.",
          "Try importing again, or choose a different .ibt file.",
        ].join("\n"));
      }
      importDebug.log("on_import_complete_called", { runId: resp.run_id });
      await completeImport(resp.run_id, resp.track_map ?? null);
      setNativeStatus(resp.status.message);
      setNativeOutcome("run");
    } catch (caught) {
      const msg = caught instanceof Error ? caught.message : "Import failed";
      importDebug.error("import_request_finished", msg, { source: "native_file", fileName });
      setNativeStatus(null);
      setNativeOutcome(null);
      setNativeError(msg);
    } finally {
      setNativeBusy(false);
      setNativeStage(null);
    }
  }, [completeImport]);

  return (
    <div className="import-panel import-panel-compact">
      <div className="import-panel-heading">
        <div>
          <span className="eyebrow">Local data intake</span>
          <strong>Bring in the next run</strong>
        </div>
        <span className="import-privacy-badge"><ShieldCheck size={13} aria-hidden="true" /> Local only</span>
      </div>

      {/* ── Primary: Choose Telemetry File ── */}
      <div className="import-primary-row">
        {desktop ? (
          <button className="secondary-button import-file-button" onClick={handleNativeTelemetryPick} disabled={busy} aria-label="Choose iRacing telemetry file">
            <FileArchive size={15} aria-hidden="true" /> Choose run file
          </button>
        ) : (
          <div className="import-row">
            <input
              ref={fileInputRef}
              type="file"
              accept=".ibt,.mt2"
              style={{ display: "none" }}
              onChange={(e) => {
                const input = e.currentTarget;
                const file = input.files?.[0] ?? null;
                input.value = "";
                if (file) onFileSelected(file);
              }}
            />
            <button className="secondary-button import-file-button" onClick={onImportClick} disabled={busy}>
              <FileArchive size={15} aria-hidden="true" />
              {busy ? "Importing…" : "Import telemetry or track map"}
            </button>
          </div>
        )}
      </div>

      <div className="import-file-support" aria-label="Supported local files">
        <span className="import-file-chip">.ibt telemetry</span>
        {!desktop && <span className="import-file-chip">.mt2 track map</span>}
      </div>

      {progressIndex != null && (
        <ol className="import-progress-track" aria-label="Import progress">
          {IMPORT_STEPS.map((step, index) => {
            const state = progressIndex >= IMPORT_STEPS.length || index < progressIndex
              ? "done"
              : index === progressIndex ? "active" : "upcoming";
            return (
              <li key={step} className="import-progress-step" data-state={state} aria-current={state === "active" ? "step" : undefined}>
                <span className="import-progress-dot" aria-hidden="true">{state === "done" ? <Check size={10} /> : index + 1}</span>
                <span>{step}</span>
              </li>
            );
          })}
        </ol>
      )}

      {/* ── Progress / status ── */}
      {displayedStage && <p className="import-stage import-alert import-alert-stage" aria-live="polite">{displayedStage}</p>}
      {busy && !displayedStage && (
        <p className="import-stage import-alert import-alert-stage">
          Importing telemetry… this can take a minute for large .ibt files.
        </p>
      )}
      {displayedError && <ImportRecoveryMessage error={displayedError} />}
      {displayedStatus && <p className="status-text import-alert import-alert-status" aria-live="polite">{displayedStatus}</p>}
      {displayedStatus && displayedStatus.includes("cached") && (
        <div className="import-cache-info">
          <HardDrive size={12} aria-hidden="true" />
          <span>Cached locally in the fast telemetry archive</span>
        </div>
      )}

    </div>
  );
}

