import { AlertTriangle, BarChart3, Clock, Gauge, Layers, MapPin, TrendingDown, Trophy } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchLapWindows } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { ValueDisplay } from "../components/ValueDisplay";
import type { RunOverview } from "../types/telemetry";
import type { LapWindowsResponse } from "../types/laps";

type LapsTabProps = {
  overview: RunOverview;
};

function formatTime(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const min = Math.floor(seconds / 60);
  const sec = (seconds % 60).toFixed(3);
  return `${min}:${sec.padStart(6, "0")}`;
}

function formatDelta(seconds: number | null | undefined, best: number | null | undefined): string {
  if (seconds == null || best == null || Number.isNaN(seconds) || Number.isNaN(best)) return "";
  const delta = seconds - best;
  if (Math.abs(delta) < 0.001) return "BEST";
  return `+${delta.toFixed(3)}`;
}

export function LapsTab({ overview }: LapsTabProps) {
  const { selection, selectLap, setWorkspace } = useTelemetrySelection();
  const [windowsData, setWindowsData] = useState<LapWindowsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedLap, setExpandedLap] = useState<number | null>(null);
  const [includeDraft, setIncludeDraft] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetchLapWindows(overview.run_id, includeDraft)
      .then(setWindowsData)
      .catch(() => setWindowsData(null))
      .finally(() => setLoading(false));
  }, [overview.run_id, includeDraft]);

  const laps = overview.laps;
  const bestTime = useMemo(
    () => Math.min(...laps.filter((l) => l.lap_time != null).map((l) => l.lap_time!)),
    [laps],
  );

  const handleSelectLap = useCallback((lapNumber: number) => {
    selectLap(lapNumber);
    setWorkspace("platform_trace", "manual");
  }, [selectLap, setWorkspace]);

  const handleAddToCompare = useCallback((lapNumber: number) => {
    selectLap(lapNumber);
    setWorkspace("compare", "manual");
  }, [selectLap, setWorkspace]);

  return (
    <div className="tab-grid">
      {/* ── Header ── */}
      <section className="workspace-section">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2><Clock size={18} /> Laps</h2>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <span className="muted">{overview.session.track_display_name ?? overview.session.track_name} — {overview.session.car_name}</span>
            <label className="toggle-label" style={{ fontSize: 11 }}>
              <input type="checkbox" checked={includeDraft} onChange={() => setIncludeDraft(!includeDraft)} />
              Include Draft
            </label>
          </div>
        </div>
        <p className="section-note">
          {windowsData?.total_valid_laps ?? 0} valid of {windowsData?.total_laps ?? laps.length} total laps
          {windowsData && windowsData.total_valid_laps < 10 && (
            <span style={{ color: "#f59e0b", marginLeft: 8 }}>
              <AlertTriangle size={12} /> Need 10+ valid laps for window analysis
            </span>
          )}
        </p>
      </section>

      {/* ── Top Cards ── */}
      {windowsData && (
        <section className="metrics-row" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
          <div className="metric-card">
            <span><Trophy size={14} /> Fastest Lap</span>
            <strong style={{ color: "#22c55e" }}>
              {windowsData.fastest_groups[0]?.laps[0]?.lap_time != null
                ? formatTime(windowsData.fastest_groups[0].laps[0].lap_time)
                : "—"}
            </strong>
          </div>
          <div className="metric-card">
            <span><Gauge size={14} /> Best 10-Lap Avg</span>
            <strong style={{ color: "#38bdf8" }}>
              {windowsData.best_windows.find(w => w.window_size === 10)?.best_window?.average_lap_time != null
                ? formatTime(windowsData.best_windows.find(w => w.window_size === 10)!.best_window!.average_lap_time)
                : windowsData.total_valid_laps < 10 ? "Need 10 laps" : "—"}
            </strong>
          </div>
          <div className="metric-card">
            <span><Gauge size={14} /> Best 20-Lap Avg</span>
            <strong style={{ color: "#38bdf8" }}>
              {windowsData.best_windows.find(w => w.window_size === 20)?.best_window?.average_lap_time != null
                ? formatTime(windowsData.best_windows.find(w => w.window_size === 20)!.best_window!.average_lap_time)
                : windowsData.total_valid_laps < 20 ? "Need 20 laps" : "—"}
            </strong>
          </div>
          {windowsData.degradation && windowsData.degradation.lap_count >= 10 && (
            <div className="metric-card">
              <span><TrendingDown size={14} /> Falloff</span>
              <strong style={{ color: (windowsData.degradation.falloff_early_to_late ?? 0) > 0.5 ? "#ef4444" : "#f59e0b" }}>
                {windowsData.degradation.falloff_early_to_late != null
                  ? `+${windowsData.degradation.falloff_early_to_late.toFixed(2)}s`
                  : "—"}
              </strong>
            </div>
          )}
        </section>
      )}

      {/* ── Degradation coaching message ── */}
      {windowsData?.degradation?.coaching_message && windowsData.degradation.lap_count >= 10 && (
        <section className="crew-chief-brief" style={{ borderColor: "#f59e0b" }}>
          <h2>Pace Trend</h2>
          <p className="crew-chief-text">{windowsData.degradation.coaching_message}</p>
          {windowsData.degradation.draft_warning && (
            <p className="warning-line" style={{ marginTop: 6 }}><AlertTriangle size={12} /> {windowsData.degradation.draft_warning}</p>
          )}
        </section>
      )}

      {/* ── Lap Table ── */}
      <section className="workspace-section" style={{ padding: 0, overflow: "auto" }}>
        <table className="compact-table" style={{ margin: 0 }}>
          <thead>
            <tr>
              <th>#</th>
              <th>Time</th>
              <th>Δ</th>
              <th>Type</th>
              <th>Tags</th>
              <th>Avg Speed</th>
              <th>Min Splitter</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {laps.map((lap) => {
              const isSelected = selection.selectedLap === lap.lap_number;
              const isExpanded = expandedLap === lap.lap_number;
              const tags = lap.classification_tags ?? [];
              const hasDraft = tags.some((t) => t.includes("DRAFT"));
              const isValid = lap.is_useful && !hasDraft;
              return (
                <React.Fragment key={lap.lap_id}>
                  <tr
                    className={isSelected ? "selected-row" : ""}
                    style={{ cursor: "pointer", opacity: isValid ? 1 : 0.5 }}
                    onClick={() => setExpandedLap(isExpanded ? null : lap.lap_number)}
                  >
                    <td>{lap.lap_number}</td>
                    <td style={{ fontWeight: 600 }}>{formatTime(lap.lap_time)}</td>
                    <td style={{ color: formatDelta(lap.lap_time, bestTime) === "BEST" ? "#22c55e" : "#8d9aaa" }}>
                      {formatDelta(lap.lap_time, bestTime)}
                    </td>
                    <td>
                      <span className="lap-type-badge" style={{
                        background: lap.lap_type === "timed" ? "#22c55e20" : "#8d9aaa20",
                        color: lap.lap_type === "timed" ? "#22c55e" : "#8d9aaa",
                      }}>
                        {lap.lap_type}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                        {hasDraft && <span className="lap-flag-badge lap-flag-draft">Draft</span>}
                        {!lap.is_useful && <span className="lap-flag-badge lap-flag-invalid">Invalid</span>}
                        {tags.includes("LIKELY_SOLO") && <span className="lap-flag-badge" style={{ background: "#22c55e20", color: "#22c55e" }}>Solo</span>}
                      </div>
                    </td>
                    <td><ValueDisplay value={lap.avg_speed_mph} unit="mph" precision={1} /></td>
                    <td><ValueDisplay value={lap.min_splitter_mm} unit="mm" precision={1} /></td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleSelectLap(lap.lap_number); }} title="Open Platform">
                          <Layers size={10} />
                        </button>
                        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleAddToCompare(lap.lap_number); }} title="Add to Compare">
                          <BarChart3 size={10} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr key={`${lap.lap_id}-expanded`}>
                      <td colSpan={8} style={{ padding: "8px 16px", background: "#0a0d14" }}>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
                          <div><span className="muted">Max Speed</span><br /><ValueDisplay value={lap.max_speed_mph} unit="mph" precision={1} /></div>
                          <div><span className="muted">Max Speed</span><br /><ValueDisplay value={lap.max_speed_mph} unit="mph" precision={1} /></div>
                          <div><span className="muted">Avg Throttle</span><br /><ValueDisplay value={lap.avg_throttle_pct} unit="%" precision={1} /></div>
                          <div><span className="muted">Avg Brake</span><br /><ValueDisplay value={lap.avg_brake_pct} unit="%" precision={1} /></div>
                        </div>
                        <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
                          <button className="secondary-button" onClick={() => { selectLap(lap.lap_number); setWorkspace("map", "manual"); }}>
                            <MapPin size={14} /> Open Map
                          </button>
                          <button className="secondary-button" onClick={() => { selectLap(lap.lap_number); setWorkspace("platform_trace", "manual"); }}>
                            <Layers size={14} /> Open Platform
                          </button>
                          <button className="secondary-button" onClick={() => { selectLap(lap.lap_number); setWorkspace("compare", "manual"); }}>
                            <BarChart3 size={14} /> Compare
                          </button>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
