/**
 * ImportPanel — unified import UI with native Tauri picker and browser fallback.
 *
 * Desktop mode (Tauri):
 * - "Choose Telemetry File" — native .ibt/.sto picker (primary)
 * - "Scan Telemetry Folder" — native folder picker, scans for .ibt files
 * - "Manage Track Maps" — native .mt2 picker (secondary/fallback)
 *
 * Browser mode:
 * - Hidden file input for .ibt/.sto/.mt2 (existing behavior)
 * - "Import .ibt" button
 *
 * Track maps are applied automatically when a matching local .mt2 is found.
 */

import { Bug, Copy, Folder, HardDrive, MapPin, Monitor, Upload, X } from "lucide-react";
import { useCallback, useState } from "react";
import { importIbtFileFromPath, importMt2FileFromPath, scanTelemetryFolder } from "../api/client";
import { isTauri } from "../utils/env";
import { pickTelemetryFile, pickTrackMapFile, pickTelemetryFolder } from "../utils/tauriImport";
import { importDebug } from "../utils/importDebug";
import type { TrackMapResolution } from "../types/telemetry";

const RECENT_TELEMETRY_KEY = "racelab_recent_telemetry_files";
const RECENT_MAPS_KEY = "racelab_recent_track_maps";
const TELEMETRY_FOLDER_KEY = "racelab_telemetry_folder";
const MAX_RECENT = 5;

interface RecentEntry {
  path: string;
  name: string;
  importedAt: string;
}

type ImportPanelProps = {
  onImportComplete: (runId?: string | null, trackMap?: TrackMapResolution | null) => void;
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
function addRecentAfterImport(key: string, path: string, name: string) {
  const entries = loadRecent(key);
  const filtered = entries.filter((e) => e.path !== path);
  filtered.unshift({ path, name, importedAt: new Date().toISOString() });
  saveRecent(key, filtered);
}

export function ImportPanel({
  onImportComplete, importing, importStage, error, status,
  fileInputRef, onFileSelected, onImportClick,
}: ImportPanelProps) {
  const desktop = isTauri();
  const [recentTelemetry] = useState<RecentEntry[]>(() => loadRecent(RECENT_TELEMETRY_KEY));
  const [recentMaps] = useState<RecentEntry[]>(() => loadRecent(RECENT_MAPS_KEY));
  const [telemetryFolder, setTelemetryFolder] = useState<string | null>(() => {
    try { return localStorage.getItem(TELEMETRY_FOLDER_KEY); }
    catch { return null; }
  });
  const [folderImporting, setFolderImporting] = useState(false);
  const [showDebug, setShowDebug] = useState(false);

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
    try {
      importDebug.start("import_request_started", { source: "native_file", fileName });
      const resp = await importIbtFileFromPath(result.filePath);
      importDebug.success("import_request_finished", {
        source: "native_file", fileName,
        run_id: resp.run_id,
        track_map_status: resp.track_map?.status,
      });
      // Only add to recent AFTER successful import
      addRecentAfterImport(RECENT_TELEMETRY_KEY, result.filePath, fileName);
      importDebug.log("on_import_complete_called", { runId: resp.run_id });
      onImportComplete(resp.run_id, resp.track_map ?? null);
    } catch (caught) {
      const msg = caught instanceof Error ? caught.message : "Import failed";
      importDebug.error("import_request_finished", msg, { source: "native_file", fileName });
      // Re-throw so parent can catch and show error
      throw caught;
    }
  }, [onImportComplete]);

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
    try {
      importDebug.start("import_request_started", { source: "native_map", fileName });
      await importMt2FileFromPath(result.filePath);
      importDebug.success("import_request_finished", { source: "native_map", fileName });
      addRecentAfterImport(RECENT_MAPS_KEY, result.filePath, fileName);
      onImportComplete(null, null);
    } catch (caught) {
      const msg = caught instanceof Error ? caught.message : "Import failed";
      importDebug.error("import_request_finished", msg, { source: "native_map", fileName });
      throw caught;
    }
  }, [onImportComplete]);

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
    importDebug.start("folder_scan_started", { folder: telemetryFolder });
    try {
      const result = await scanTelemetryFolder(telemetryFolder);
      importDebug.log("folder_scan_finished", { count: result.files.length });
      if (result.files.length === 0) {
        setFolderImporting(false);
        return;
      }
      const newest = result.files[0];
      importDebug.log("folder_scan_selected", { fileName: newest.name });
      importDebug.start("import_request_started", { source: "folder_latest", fileName: newest.name });
      const resp = await importIbtFileFromPath(newest.path);
      importDebug.success("import_request_finished", {
        source: "folder_latest", fileName: newest.name,
        run_id: resp.run_id,
      });
      addRecentAfterImport(RECENT_TELEMETRY_KEY, newest.path, newest.name);
      importDebug.log("on_import_complete_called", { runId: resp.run_id });
      onImportComplete(resp.run_id, resp.track_map ?? null);
    } catch (caught) {
      const msg = caught instanceof Error ? caught.message : "Import failed";
      importDebug.error("import_request_finished", msg, { source: "folder_latest" });
    }
    finally { setFolderImporting(false); }
  }, [telemetryFolder, onImportComplete]);

  // ── Click recent file ─────────────────────────────────────────
  const handleRecentClick = useCallback(async (entry: RecentEntry) => {
    importDebug.log("recent_file_clicked", { fileName: entry.name });
    try {
      if (entry.path.endsWith(".mt2")) {
        await importMt2FileFromPath(entry.path);
        onImportComplete(null, null);
      } else {
        const resp = await importIbtFileFromPath(entry.path);
        importDebug.log("on_import_complete_called", { runId: resp.run_id });
        onImportComplete(resp.run_id, resp.track_map ?? null);
      }
    } catch { /* parent handles error display */ }
  }, [onImportComplete]);

  return (
    <div className="import-panel">
      {/* Mode badge */}
      <div className="import-mode-badge">
        {desktop ? (
          <span><Monitor size={12} /> Desktop Mode</span>
        ) : (
          <span><Upload size={12} /> Browser Mode</span>
        )}
      </div>

      <p className="import-description">
        {desktop
          ? "Choose telemetry directly from your iRacing folder."
          : "Select an .ibt file to import."}
      </p>

      {/* ── Desktop native buttons ── */}
      {desktop && (
        <div className="import-desktop-actions">
          <button className="secondary-button" onClick={handleNativeTelemetryPick} disabled={importing} style={{ fontWeight: 600 }}>
            <HardDrive size={14} /> Choose Telemetry File
          </button>
          <button className="secondary-button" onClick={handleNativeFolderPick} disabled={importing}>
            <Folder size={14} /> Scan Telemetry Folder
          </button>
          <button className="secondary-button" onClick={handleNativeMapPick} disabled={importing} style={{ opacity: 0.7 }}>
            <MapPin size={14} /> Manage Track Maps
          </button>
        </div>
      )}
      {desktop && (
        <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          Track maps are applied automatically when a matching local .mt2 is found.
        </p>
      )}

      {/* ── Browser fallback ── */}
      {!desktop && (
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
          <button className="secondary-button" onClick={onImportClick} disabled={importing}>
            {importStage ?? (importing ? "Importing…" : "Import .ibt or .mt2")}
          </button>
        </div>
      )}

      {/* ── Selected telemetry folder ── */}
      {desktop && telemetryFolder && (
        <div className="import-folder-info">
          <span className="import-folder-path">
            <Folder size={12} /> {telemetryFolder}
          </span>
          <button className="trackmap-action-btn" onClick={handleScanFolder} disabled={folderImporting}>
            {folderImporting ? "Scanning…" : "Import Latest .ibt"}
          </button>
          <span className="muted" style={{ fontSize: 10, marginLeft: 4 }}>
            (scans for newest .ibt file)
          </span>
        </div>
      )}

      {/* ── Progress ── */}
      {importStage && <p className="import-stage">{importStage}</p>}
      {importing && !importStage && (
        <p className="import-stage" style={{ color: "#8d9aaa" }}>
          Importing telemetry… this can take a minute for large .ibt files.
        </p>
      )}
      {error && <p className="error-text">{error}</p>}
      {status && <p className="status-text">{status}</p>}

      {/* ── Cache info ── */}
      {status && status.includes("cached") && (
        <div className="import-cache-info" style={{ fontSize: 10, color: "#8d9aaa", marginTop: 4 }}>
          <span>📦 Cached locally — parquet format</span>
        </div>
      )}

      {/* ── Recent telemetry files ── */}
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

      {/* ── Import Debug Panel ── */}
      <div style={{ marginTop: 12, borderTop: "1px solid #1f2937", paddingTop: 8 }}>
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
  );
}

/** Dev-only import debug panel. Shows last 50 import steps. */
function ImportDebugPanel() {
  const log = importDebug.getLog();
  const handleCopy = () => {
    const text = log.map(e =>
      `[${e.timestamp}] ${e.status.toUpperCase()} ${e.step}${e.durationMs ? ` (${e.durationMs}ms)` : ""}${e.data ? ` ${JSON.stringify(e.data)}` : ""}`
    ).join("\n");
    navigator.clipboard.writeText(text).catch(() => {});
  };
  return (
    <div style={{ marginTop: 8, fontSize: 10, background: "#0a0d14", border: "1px solid #1f2937", borderRadius: 6, padding: 8, maxHeight: 300, overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ color: "#8d9aaa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
          Import Debug Log ({log.length} entries)
        </span>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="trackmap-action-btn" onClick={handleCopy} title="Copy debug log">
            <Copy size={10} /> Copy
          </button>
          <button className="trackmap-action-btn" onClick={() => importDebug.clear()} title="Clear debug log">
            <X size={10} /> Clear
          </button>
        </div>
      </div>
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
