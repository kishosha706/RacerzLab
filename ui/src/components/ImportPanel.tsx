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

import { Folder, HardDrive, MapPin, Monitor, Upload } from "lucide-react";
import { useCallback, useState } from "react";
import { importIbtFileFromPath, importMt2FileFromPath, scanTelemetryFolder } from "../api/client";
import { isTauri } from "../utils/env";
import { pickTelemetryFile, pickTrackMapFile, pickTelemetryFolder } from "../utils/tauriImport";
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

function addRecent(key: string, path: string, name: string) {
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

  // ── Native telemetry file picker (primary) ────────────────────
  const handleNativeTelemetryPick = useCallback(async () => {
    const result = await pickTelemetryFile();
    if (!result.filePath || result.cancelled) return;
    addRecent(RECENT_TELEMETRY_KEY, result.filePath, result.filePath.split(/[/\\]/).pop() ?? result.filePath);
    try {
      const resp = await importIbtFileFromPath(result.filePath);
      onImportComplete(resp.run_id, resp.track_map ?? null);
    } catch (caught) {
      throw caught;
    }
  }, [onImportComplete]);

  // ── Native track map picker (secondary/fallback) ──────────────
  const handleNativeMapPick = useCallback(async () => {
    const result = await pickTrackMapFile();
    if (!result.filePath || result.cancelled) return;
    addRecent(RECENT_MAPS_KEY, result.filePath, result.filePath.split(/[/\\]/).pop() ?? result.filePath);
    try {
      await importMt2FileFromPath(result.filePath);
      onImportComplete(null, null);
    } catch (caught) {
      throw caught;
    }
  }, [onImportComplete]);

  // ── Native folder picker ──────────────────────────────────────
  const handleNativeFolderPick = useCallback(async () => {
    const result = await pickTelemetryFolder();
    if (!result.filePath || result.cancelled) return;
    setTelemetryFolder(result.filePath);
    try {
      localStorage.setItem(TELEMETRY_FOLDER_KEY, result.filePath);
    } catch { /* ignore */ }
  }, []);

  // ── Scan telemetry folder for .ibt files only ─────────────────
  const handleScanFolder = useCallback(async () => {
    if (!telemetryFolder) return;
    setFolderImporting(true);
    try {
      const result = await scanTelemetryFolder(telemetryFolder);
      if (result.files.length === 0) {
        setFolderImporting(false);
        return;
      }
      const newest = result.files[0];
      addRecent(RECENT_TELEMETRY_KEY, newest.path, newest.name);
      const resp = await importIbtFileFromPath(newest.path);
      onImportComplete(resp.run_id, resp.track_map ?? null);
    } catch { /* parent handles error */ }
    finally { setFolderImporting(false); }
  }, [telemetryFolder, onImportComplete]);

  // ── Click recent file ─────────────────────────────────────────
  const handleRecentClick = useCallback(async (entry: RecentEntry) => {
    try {
      if (entry.path.endsWith(".mt2")) {
        await importMt2FileFromPath(entry.path);
        onImportComplete(null, null);
      } else {
        const resp = await importIbtFileFromPath(entry.path);
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
    </div>
  );
}
