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

import { HardDrive } from "lucide-react";
import { useCallback, useState } from "react";
import { importIbtFileFromPath } from "../api/client";
import { isTauri } from "../utils/env";
import { pickTelemetryFile } from "../utils/tauriImport";
import { importDebug } from "../utils/importDebug";
import type { TrackMapResolution } from "../types/telemetry";

type ImportPanelProps = {
  onImportComplete: (runId?: string | null, trackMap?: TrackMapResolution | null) => void | Promise<void>;
  importing: boolean;
  importStage: string | null;
  error: string | null;
  status: string | null;
  /** Browser file input ref for fallback */
  fileInputRef: React.RefObject<HTMLInputElement>;
  /** Browser file input change handler */
  onFileSelected: (file: File) => void;
  /** Browser import click handler */
  onImportClick: () => void;
};

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
  return (
    <div className="import-alert import-alert-error import-recovery-card" aria-live="polite">
      <strong>{title || "Import failed"}</strong>
      {details.map((line) => <p key={line}>{line}</p>)}
      {!details.some((line) => line.includes("No completed run was created")) && (
        <p>No completed run was created.</p>
      )}
      {!details.some((line) => line.includes("Try importing again")) && (
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
  fileInputRef, onFileSelected, onImportClick,
}: ImportPanelProps) {
  const desktop = isTauri();
  const [nativeBusy, setNativeBusy] = useState(false);
  const [nativeStage, setNativeStage] = useState<string | null>(null);
  const [nativeError, setNativeError] = useState<string | null>(null);
  const [nativeStatus, setNativeStatus] = useState<string | null>(null);

  const busy = importing || nativeBusy;
  const displayedStage = nativeStage ?? importStage;
  const displayedError = nativeError ?? error;
  const displayedStatus = nativeStatus ?? status;

  const completeImport = useCallback(async (runId?: string | null, trackMap?: TrackMapResolution | null) => {
    setNativeStage(runId ? "Opening cockpit..." : "Refreshing local library...");
    await onImportComplete(runId, trackMap);
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
    try {
      importDebug.start("import_request_started", { source: "native_file", fileName });
      const resp = await importIbtFileFromPath(result.filePath);
      importDebug.success("import_request_finished", {
        source: "native_file", fileName,
        run_id: resp.run_id,
        track_map_status: resp.track_map?.status,
      });
      setNativeStatus(resp.status.message);
      importDebug.log("on_import_complete_called", { runId: resp.run_id });
      await completeImport(resp.run_id, resp.track_map ?? null);
    } catch (caught) {
      const msg = caught instanceof Error ? caught.message : "Import failed";
      importDebug.error("import_request_finished", msg, { source: "native_file", fileName });
      setNativeError(msg);
    } finally {
      setNativeBusy(false);
      setNativeStage(null);
    }
  }, [completeImport]);

  return (
    <div className="import-panel import-panel-compact">
      {/* ── Primary: Choose Telemetry File ── */}
      <div className="import-primary-row">
        {desktop ? (
          <button className="secondary-button" onClick={handleNativeTelemetryPick} disabled={busy} style={{ fontWeight: 600 }} aria-label="Choose telemetry file">
            <HardDrive size={14} /> Choose Telemetry File
          </button>
        ) : (
          <div className="import-row">
            <input
              ref={fileInputRef}
              type="file"
              accept=".ibt,.sto,.mt2"
              style={{ display: "none" }}
              onChange={(e) => {
                const { files } = e.currentTarget;
                if (files && files.length > 0) onFileSelected(files[0]);
              }}
            />
            <button className="secondary-button" onClick={onImportClick} disabled={busy}>
              {displayedStage ?? (busy ? "Importing…" : "Import telemetry or track map")}
            </button>
          </div>
        )}
      </div>

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
        <div className="import-cache-info" style={{ fontSize: 10, color: "#8d9aaa", marginTop: 2 }}>
          <span>📦 Cached locally — parquet format</span>
        </div>
      )}

    </div>
  );
}

