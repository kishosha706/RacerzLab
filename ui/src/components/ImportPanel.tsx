/**
 * ImportPanel — unified import UI with native Tauri picker and browser fallback.
 *
 * Desktop mode (Tauri):
 * - "Choose Telemetry File" — native .ibt/.sto picker (primary)
 * - "Scan Telemetry Folder" — native folder picker, scans for .ibt files
 * - "Manage Track Maps" — native track map file picker (secondary/fallback)
 *
 * Browser mode:
 * - Hidden file input for supported telemetry/setup/map files (existing behavior)
 * - "Import telemetry" button
 *
 * Imported track maps are applied automatically when a matching local RacerZLab cached map is found.
 */

import { Bug, ChevronDown, ChevronRight, Copy, Folder, HardDrive, MapPin, Monitor, Upload, X } from "lucide-react";
import { useCallback, useState } from "react";
import { importIbtFileFromPath, importMt2FileFromPath, scanTelemetryFolder } from "../api/client";
import { isTauri } from "../utils/env";
import { pickTelemetryFile, pickTrackMapFile, pickTelemetryFolder } from "../utils/tauriImport";
import { importDebug } from "../utils/importDebug";
import type { TrackMapResolution } from "../types/telemetry";
import type { TelemetryFileEntry } from "../api/client";

const RECENT_TELEMETRY_KEY = "racelab_recent_telemetry_files";
const RECENT_MAPS_KEY = "racelab_recent_track_maps";
const TELEMETRY_FOLDER_KEY = "racelab_telemetry_folder";
const MAX_RECENT = 5;

interface RecentEntry {
  path: string;
  name: string;
  importedAt: string;
}

function formatBytes(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  const kb = sizeBytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function formatStamp(isoString: string): string {
  const stamp = new Date(isoString);
  if (Number.isNaN(stamp.getTime())) return isoString;
  return stamp.toLocaleString();
}

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

function loadRecent(key: string): RecentEntry[] {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "[]");
  } catch {
    return [];
  }
}

function saveRecent(key: string, entries: RecentEntry[]) {
  try {
    localStorage.setItem(key, JSON.stringify(entries.slice(0, MAX_RECENT)));
  } catch { /* ignore */ }
}

/** Add to recent list only after successful import. */
function addRecentAfterImport(key: string, path: string, name: string): RecentEntry[] {
  const entries = loadRecent(key);
  const filtered = entries.filter((e) => e.path !== path);
  filtered.unshift({ path, name, importedAt: new Date().toISOString() });
  saveRecent(key, filtered);
  return filtered.slice(0, MAX_RECENT);
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
  const [recentTelemetry, setRecentTelemetry] = useState<RecentEntry[]>(() => loadRecent(RECENT_TELEMETRY_KEY));
  const [recentMaps, setRecentMaps] = useState<RecentEntry[]>(() => loadRecent(RECENT_MAPS_KEY));
  const [telemetryFolder, setTelemetryFolder] = useState<string | null>(() => {
    try { return localStorage.getItem(TELEMETRY_FOLDER_KEY); }
    catch { return null; }
  });
  const [folderImporting, setFolderImporting] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [nativeBusy, setNativeBusy] = useState(false);
  const [nativeStage, setNativeStage] = useState<string | null>(null);
  const [nativeError, setNativeError] = useState<string | null>(null);
  const [nativeStatus, setNativeStatus] = useState<string | null>(null);
  const [latestFolderCandidate, setLatestFolderCandidate] = useState<TelemetryFileEntry | null>(null);

  const busy = importing || nativeBusy || folderImporting;
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
      // Only add to recent AFTER successful import
      setRecentTelemetry(addRecentAfterImport(RECENT_TELEMETRY_KEY, result.filePath, fileName));
      importDebug.log("recent_file_saved", { source: "native_file", fileName });
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

  // ── Native track map picker (secondary/fallback) ──────────────
  const handleNativeMapPick = useCallback(async () => {
    importDebug.start("picker_opened", { source: "native_map" });
    const result = await pickTrackMapFile();
    if (result.cancelled) {
      importDebug.log("picker_cancelled", { source: "native_map" });
      return;
    }
    if (!result.filePath) {
      importDebug.error("picker_selected", "No file path returned", { source: "native_map" });
      return;
    }
    const fileName = result.filePath.split(/[/\\]/).pop() ?? result.filePath;
    importDebug.log("picker_selected", { source: "native_map", fileName });
    setNativeBusy(true);
    setNativeStage("Reading track map...");
    setNativeError(null);
    setNativeStatus(null);
    try {
      importDebug.start("import_request_started", { source: "native_map", fileName });
      await importMt2FileFromPath(result.filePath);
      importDebug.success("import_request_finished", { source: "native_map", fileName });
      setRecentMaps(addRecentAfterImport(RECENT_MAPS_KEY, result.filePath, fileName));
      importDebug.log("recent_file_saved", { source: "native_map", fileName });
      setNativeStatus("Track map import complete. Saved to the local map cache.");
      await completeImport(null, null);
    } catch (caught) {
      const msg = caught instanceof Error ? caught.message : "Import failed";
      importDebug.error("import_request_finished", msg, { source: "native_map", fileName });
      setNativeError(msg);
    } finally {
      setNativeBusy(false);
      setNativeStage(null);
    }
  }, [completeImport]);

  // ── Native folder picker ──────────────────────────────────────
  const handleNativeFolderPick = useCallback(async () => {
    importDebug.log("picker_opened", { source: "folder" });
    const result = await pickTelemetryFolder();
    if (!result.filePath || result.cancelled) {
      importDebug.log("picker_cancelled", { source: "folder" });
      return;
    }
    setTelemetryFolder(result.filePath);
    try {
      localStorage.setItem(TELEMETRY_FOLDER_KEY, result.filePath);
    } catch { /* ignore */ }
  }, []);

  // ── Scan telemetry folder for .ibt files only ─────────────────
  const handleScanFolder = useCallback(async () => {
    if (!telemetryFolder) return;
    setFolderImporting(true);
    setNativeStage("Scanning telemetry folder...");
    setNativeError(null);
    setNativeStatus(null);
    importDebug.start("folder_scan_started", { folder: telemetryFolder });
    try {
      const result = await scanTelemetryFolder(telemetryFolder);
      importDebug.log("folder_scan_finished", { count: result.files.length });
      if (result.files.length === 0) {
        setLatestFolderCandidate(null);
        setNativeStatus("No .ibt files found in the selected folder.");
        setFolderImporting(false);
        setNativeStage(null);
        return;
      }
      const newest = result.files[0];
      setLatestFolderCandidate(newest);
      importDebug.log("folder_scan_selected", { fileName: newest.name });
      const confirmed = window.confirm(
        `Import latest telemetry file?\n\n${newest.name}\n${formatBytes(newest.size_bytes)}\n${formatStamp(newest.modified_at)}\n\n${newest.path}`,
      );
      if (!confirmed) {
        setNativeStatus("Import cancelled.");
        setFolderImporting(false);
        setNativeStage(null);
        return;
      }
      setNativeStage("Reading .ibt and decoding telemetry...");
      importDebug.start("import_request_started", { source: "folder_latest", fileName: newest.name });
      const resp = await importIbtFileFromPath(newest.path);
      importDebug.success("import_request_finished", {
        source: "folder_latest", fileName: newest.name,
        run_id: resp.run_id,
      });
      setRecentTelemetry(addRecentAfterImport(RECENT_TELEMETRY_KEY, newest.path, newest.name));
      importDebug.log("recent_file_saved", { source: "folder_latest", fileName: newest.name });
      setNativeStatus(resp.status.message);
      importDebug.log("on_import_complete_called", { runId: resp.run_id });
      await completeImport(resp.run_id, resp.track_map ?? null);
    } catch (caught) {
      const msg = caught instanceof Error ? caught.message : "Import failed";
      importDebug.error("import_request_finished", msg, { source: "folder_latest" });
      setNativeError(msg);
    }
    finally {
      setFolderImporting(false);
      setNativeStage(null);
    }
  }, [telemetryFolder, completeImport]);

  // ── Click recent file ─────────────────────────────────────────
  const handleRecentClick = useCallback(async (entry: RecentEntry) => {
    importDebug.log("recent_file_clicked", { fileName: entry.name });
    setNativeBusy(true);
    setNativeError(null);
    setNativeStatus(null);
    try {
      if (entry.path.endsWith(".mt2")) {
        setNativeStage("Reading track map...");
        await importMt2FileFromPath(entry.path);
        setRecentMaps(addRecentAfterImport(RECENT_MAPS_KEY, entry.path, entry.name));
        await completeImport(null, null);
      } else {
        setNativeStage("Reading .ibt and decoding telemetry...");
        const resp = await importIbtFileFromPath(entry.path);
        setRecentTelemetry(addRecentAfterImport(RECENT_TELEMETRY_KEY, entry.path, entry.name));
        importDebug.log("on_import_complete_called", { runId: resp.run_id });
        await completeImport(resp.run_id, resp.track_map ?? null);
      }
    } catch (caught) {
      setNativeError(caught instanceof Error ? caught.message : "Import failed");
    }
    finally {
      setNativeBusy(false);
      setNativeStage(null);
    }
  }, [completeImport]);

  const [advancedOpen, setAdvancedOpen] = useState(false);

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

        {/* ── Advanced toggle ── */}
        <button
          className="import-advanced-toggle"
          onClick={() => setAdvancedOpen(!advancedOpen)}
          title="Advanced import tools"
          aria-label={advancedOpen ? "Hide advanced import tools" : "Show advanced import tools"}
          aria-expanded={advancedOpen}
        >
          {advancedOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span>Advanced</span>
        </button>
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

      {/* ── Advanced Import (collapsible) ── */}
      {advancedOpen && (
        <div className="import-advanced-section">
          {/* ── Recent Telemetry Files ── */}
          {recentTelemetry.length > 0 && (
            <div className="import-recent">
              <h4>Recent Telemetry Files</h4>
              {recentTelemetry.map((entry) => (
                <button
                  key={entry.path}
                  className="import-recent-item"
                  onClick={() => handleRecentClick(entry)}
                  title={entry.path}
                >
                  <span className="import-recent-name">{entry.name}</span>
                  <span className="import-recent-meta">{entry.path} · {entry.importedAt.slice(0, 10)}</span>
                </button>
              ))}
            </div>
          )}
          <div className="import-mode-badge">
            {desktop ? (
              <span><Monitor size={12} /> Desktop Mode</span>
            ) : (
              <span><Upload size={12} /> Browser Mode</span>
            )}
          </div>

          {desktop && (
            <>
              <div className="import-desktop-actions">
                <button className="secondary-button" onClick={handleNativeFolderPick} disabled={busy} aria-label="Pick telemetry folder to scan">
                  <Folder size={14} /> Scan Telemetry Folder
                </button>
                <button className="secondary-button" onClick={handleNativeMapPick} disabled={busy} style={{ opacity: 0.7 }} aria-label="Pick track map file">
                  <MapPin size={14} /> Manage Track Maps
                </button>
              </div>
              <p className="muted" style={{ fontSize: 11, margin: "2px 0 4px" }}>
                Imported track maps are applied automatically when RacerZLab finds a local match.
              </p>
            </>
          )}

          {/* ── Selected telemetry folder ── */}
          {desktop && telemetryFolder && (
            <div className="import-folder-info">
              <span className="import-folder-path">
                <Folder size={12} /> {telemetryFolder}
              </span>
              {latestFolderCandidate && (
                <div className="import-latest-candidate" aria-live="polite">
                  <span className="import-latest-candidate-label">Latest candidate</span>
                  <strong>{latestFolderCandidate.name}</strong>
                  <span>{formatBytes(latestFolderCandidate.size_bytes)} · {formatStamp(latestFolderCandidate.modified_at)}</span>
                </div>
              )}
              <button className="trackmap-action-btn" onClick={handleScanFolder} disabled={busy} aria-label="Import latest telemetry file from selected folder">
                {folderImporting ? "Scanning…" : "Review + Import Latest .ibt"}
              </button>
            </div>
          )}

          {/* ── Recent track maps ── */}
          {recentMaps.length > 0 && (
            <div className="import-recent">
              <h4>Recent Track Maps</h4>
              {recentMaps.map((entry) => (
                <button
                  key={entry.path}
                  className="import-recent-item"
                  onClick={() => handleRecentClick(entry)}
                  title={entry.path}
                >
                  <span className="import-recent-name">{entry.name}</span>
                  <span className="import-recent-meta">{entry.path} · {entry.importedAt.slice(0, 10)}</span>
                </button>
              ))}
            </div>
          )}

          {/* ── Import Debug ── */}
          <div style={{ marginTop: 8, borderTop: "1px solid #1f2937", paddingTop: 6 }}>
            <button
              className="trackmap-action-btn"
              onClick={() => setShowDebug(!showDebug)}
              title="Toggle import debug panel"
            >
              <Bug size={10} /> {showDebug ? "Hide" : "Show"} Import Debug
            </button>
            {showDebug && <ImportDebugPanel />}
          </div>
        </div>
      )}
    </div>
  );
}

/** Dev-only import debug panel. Shows last 50 import steps. */
function ImportDebugPanel() {
  const log = importDebug.getLog();
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    const text = log.map(e =>
      `[${e.timestamp}] ${e.status.toUpperCase()} ${e.step}${e.durationMs ? ` (${e.durationMs}ms)` : ""}${e.data ? ` ${JSON.stringify(e.data)}` : ""}`
    ).join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  };
  return (
    <div style={{ marginTop: 8, fontSize: 10, background: "#0a0d14", border: "1px solid #1f2937", borderRadius: 6, padding: 8, maxHeight: 300, overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ color: "#8d9aaa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
          Import Debug Log ({log.length} entries)
        </span>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="trackmap-action-btn" onClick={handleCopy} title="Copy debug log" aria-label="Copy debug log">
            <Copy size={10} /> Copy
          </button>
          <button className="trackmap-action-btn" onClick={() => importDebug.clear()} title="Clear debug log" aria-label="Clear debug log">
            <X size={10} /> Clear
          </button>
        </div>
      </div>
      {copied && <p className="status-text" style={{ marginBottom: 6 }}>Copied</p>}
      {log.length === 0 && <p className="muted" style={{ fontSize: 10 }}>No import debug entries yet.</p>}
      {log.map((e, i) => (
        <div key={i} style={{
          display: "flex", gap: 6, padding: "2px 0",
          color: e.status === "error" ? "#ef4444" : e.status === "success" ? "#22c55e" : e.status === "started" ? "#38bdf8" : "#8d9aaa",
          borderBottom: i < log.length - 1 ? "1px solid #1f2937" : "none",
        }}>
          <span style={{ flexShrink: 0, width: 60, color: "#64748b" }}>
            {e.durationMs != null ? `${e.durationMs}ms` : ""}
          </span>
          <span style={{ flexShrink: 0, width: 8 }}>{e.status === "error" ? "✗" : e.status === "success" ? "✓" : e.status === "started" ? "→" : "·"}</span>
          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.step}</span>
          {e.data?.error != null && <span style={{ color: "#ef4444", flexShrink: 0, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{String(e.data.error)}</span>}
        </div>
      ))}
    </div>
  );
}

