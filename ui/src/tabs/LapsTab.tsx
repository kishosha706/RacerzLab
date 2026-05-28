import { AlertTriangle, BarChart3, Clock, Gauge, Layers, List, MapPin, TrendingDown, Trophy } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchLapWindows, fetchRunList } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket } from "../store/CompareBasketContext";
import { makeBasketItem } from "../components/CompareBasket";
import { ValueDisplay } from "../components/ValueDisplay";
import type { RunOverview } from "../types/telemetry";
import type { RunListItem } from "../types/telemetry";
import type { LapWindowsResponse } from "../types/laps";

type LapsTabProps = {
  overview: RunOverview;
};

type LapsSubview = "current" | "windows" | "all_sessions" | "baselines" | "basket";

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

function paceQualityColor(score: number | null | undefined): string {
  if (score == null) return "#8d9aaa";
  if (score >= 85) return "#22c55e";
  if (score >= 70) return "#38bdf8";
  if (score >= 50) return "#f59e0b";
  if (score >= 25) return "#f97316";
  return "#ef4444";
}

/** Human-readable label for the pace–trust relationship. */
function classifyPaceTrust(
  pq: number | null | undefined,
  ec: number | null | undefined,
  _su: number | null | undefined,
  warnings: string[] | undefined,
): string {
  if (!warnings) warnings = [];
  const upper = warnings.map(w => w.toUpperCase());
  if (upper.some(w => w.includes("DRAFT"))) return "Draft-affected: setup conclusions limited";
  if (upper.some(w => w.includes("60%") || w.includes("INSUFFICIENT") || w.includes("ONLY"))) return "Insufficient valid laps";
  if (pq != null && ec != null) {
    if (pq >= 70 && ec < 50) return "Fast but not trustworthy";
    if (ec >= 70 && pq < 50) return "Clean but not fast";
    if (pq >= 70 && ec >= 70) return "Strong clean pace";
    if (pq < 30 && ec < 30) return "Not useful for setup decisions";
  }
  return "Usable with caution";
}

const PERFORMANCE_TOOLTIP = "How strong the pace was, based on speed relative to reference, consistency, falloff, and stress context.";
const TRUST_TOOLTIP = "How trustworthy this data is for setup decisions, based on validity, draft status, data completeness, window size, and context stability.";
const ENGINEERING_VALUE_TOOLTIP = "Combined decision value for setup work. A fast lap with low trust may still have low Engineering Value.";

function stintMapColor(ev: number | null | undefined): string {
  if (ev == null) return "#1f2937";
  if (ev >= 85) return "#22c55e";
  if (ev >= 70) return "#38bdf8";
  if (ev >= 50) return "#f59e0b";
  if (ev >= 25) return "#f97316";
  return "#ef4444";
}

export function LapsTab({ overview }: LapsTabProps) {
  const { selection, selectLap, setWorkspace } = useTelemetrySelection();
  const { setBaseline, setTest } = useCompareBasket();
  const [windowsData, setWindowsData] = useState<LapWindowsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [expandedLap, setExpandedLap] = useState<number | null>(null);
  const [includeDraft, setIncludeDraft] = useState(false);
  const [stintMode, setStintMode] = useState<"ev" | "delta" | "draft" | "falloff">("ev");
  const [subview, setSubview] = useState<LapsSubview>("current");
  const [allRuns, setAllRuns] = useState<RunListItem[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);

  // Load all runs for cross-session views
  useEffect(() => {
    if (subview === "all_sessions" || subview === "baselines") {
      setRunsLoading(true);
      fetchRunList()
        .then(setAllRuns)
        .catch(() => setAllRuns([]))
        .finally(() => setRunsLoading(false));
    }
  }, [subview]);

  useEffect(() => {
    setLoading(true);
    fetchLapWindows(overview.run_id, includeDraft)
      .then(setWindowsData)
      .catch(() => setWindowsData(null))
      .finally(() => setLoading(false));
  }, [overview.run_id, includeDraft]);

  const { laps } = overview;
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

      {/* ── Subview Navigation ── */}
      <div className="compare-subnav">
        {(["current", "windows", "all_sessions", "baselines", "basket"] as LapsSubview[]).map((sv) => (
          <button
            key={sv}
            className={`subnav-item ${subview === sv ? "active" : ""}`}
            onClick={() => setSubview(sv)}
          >
            {sv === "current" ? "Current Run" : sv === "windows" ? "Windows" : sv === "all_sessions" ? "All Sessions" : sv === "baselines" ? "Baselines" : "Basket"}
          </button>
        ))}
      </div>

      {/* ── All Sessions view ── */}
      {subview === "all_sessions" && (
        <section className="workspace-section">
          <h2><List size={16} /> All Sessions</h2>
          {runsLoading && <p className="muted">Loading runs…</p>}
          {!runsLoading && allRuns.length === 0 && <p className="muted">No imported runs found.</p>}
          {!runsLoading && allRuns.length > 0 && (
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Car</th>
                  <th>Track</th>
                  <th>Setup</th>
                  <th>Laps</th>
                  <th>Best Lap</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {allRuns.map((run) => (
                  <tr key={run.run_id}>
                    <td className="cell-val">{run.imported_at?.slice(0, 10) ?? "—"}</td>
                    <td className="cell-label">{run.car_name ?? "—"}</td>
                    <td className="cell-label">{run.track_name ?? "—"}</td>
                    <td className="cell-val">{run.setup_name ?? "—"}</td>
                    <td className="cell-val">{run.lap_count ?? "—"}</td>
                    <td className="cell-val">{run.best_lap_time_s != null ? `${run.best_lap_time_s.toFixed(3)}s` : "—"}</td>
                    <td>
                      <div style={{ display: "flex", gap: 4 }}>
                        <button
                          className="trackmap-action-btn"
                          onClick={() => {
                            const item = makeBasketItem(
                              run.run_id, null,
                              `${run.car_name ?? "Car"} @ ${run.track_name ?? "Track"}`,
                              run.car_name ?? null,
                              run.track_name ?? null,
                              run.setup_name ?? null,
                              run.best_lap_time_s ?? null,
                              [],
                              "UNKNOWN_DRAFT_STATUS",
                              null,
                              run.imported_at ?? null,
                              null,
                              run.has_setup_snapshot ?? false,
                            );
                            setBaseline(item);
                          }}
                          title="Set as Baseline"
                        >
                          <Clock size={10} /> BL
                        </button>
                        <button
                          className="trackmap-action-btn"
                          onClick={() => {
                            const item = makeBasketItem(
                              run.run_id, null,
                              `${run.car_name ?? "Car"} @ ${run.track_name ?? "Track"}`,
                              run.car_name ?? null,
                              run.track_name ?? null,
                              run.setup_name ?? null,
                              run.best_lap_time_s ?? null,
                              [],
                              "UNKNOWN_DRAFT_STATUS",
                              null,
                              run.imported_at ?? null,
                              null,
                              run.has_setup_snapshot ?? false,
                            );
                            setTest(item);
                          }}
                          title="Set as Test"
                        >
                          <Gauge size={10} /> Test
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {/* ── Baselines view ── */}
      {subview === "baselines" && (
        <section className="workspace-section">
          <h2><Trophy size={16} /> Recommended Baselines</h2>
          {runsLoading && <p className="muted">Loading runs…</p>}
          {!runsLoading && allRuns.length === 0 && <p className="muted">No imported runs found.</p>}
          {!runsLoading && allRuns.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {/* Fastest clean lap from current run */}
              {overview.best_useful_lap && (
                <div className="setup-diff-row changed" style={{ justifyContent: "space-between" }}>
                  <div>
                    <strong>Fastest Clean Lap</strong>
                    <span className="muted" style={{ marginLeft: 8, fontSize: 11 }}>
                      Lap {overview.best_useful_lap.lap_number} — {overview.best_useful_lap.lap_time?.toFixed(3)}s
                    </span>
                  </div>
                  <button
                    className="trackmap-action-btn"
                    onClick={() => {
                      const item = makeBasketItem(
                        overview.run_id, overview.best_useful_lap!.lap_number,
                        `Fastest Clean Lap ${overview.best_useful_lap!.lap_number}`,
                        overview.session.car_name ?? null,
                        (overview.session.track_display_name ?? overview.session.track_name) ?? null,
                        overview.session.setup_name ?? null,
                        overview.best_useful_lap!.lap_time ?? null,
                        overview.best_useful_lap!.classification_tags ?? [],
                        "LIKELY_SOLO",
                        null,
                      );
                      setBaseline(item);
                    }}
                    title="Add as Baseline"
                  >
                    <Clock size={10} /> Baseline
                  </button>
                </div>
              )}
              {/* Most recent run */}
              {allRuns.length > 0 && (
                <div className="setup-diff-row" style={{ justifyContent: "space-between" }}>
                  <div>
                    <strong>Most Recent Run</strong>
                    <span className="muted" style={{ marginLeft: 8, fontSize: 11 }}>
                      {allRuns[allRuns.length - 1].car_name} @ {allRuns[allRuns.length - 1].track_name}
                    </span>
                  </div>
                  <button
                    className="trackmap-action-btn"
                    onClick={() => {
                      const run = allRuns[allRuns.length - 1];
                      const item = makeBasketItem(
                        run.run_id, null,
                        `Recent: ${run.car_name} @ ${run.track_name}`,
                        run.car_name ?? null,
                        run.track_name ?? null,
                        run.setup_name ?? null,
                        run.best_lap_time_s ?? null,
                        [],
                        "UNKNOWN_DRAFT_STATUS",
                        null,
                        run.imported_at ?? null,
                        null,
                        run.has_setup_snapshot ?? false,
                      );
                      setBaseline(item);
                    }}
                    title="Add as Baseline"
                  >
                    <Clock size={10} /> Baseline
                  </button>
                </div>
              )}
              {/* Best 10-lap Engineering Value from current run */}
              {windowsData?.best_windows.find(w => w.window_size === 10)?.best_window && (
                <div className="setup-diff-row changed" style={{ justifyContent: "space-between" }}>
                  <div>
                    <strong>Best 10-Lap Window (by Engineering Value)</strong>
                    <span className="muted" style={{ marginLeft: 8, fontSize: 11 }}>
                      Laps {windowsData.best_windows.find(w => w.window_size === 10)!.best_window!.start_lap}–
                      {windowsData.best_windows.find(w => w.window_size === 10)!.best_window!.end_lap}
                      {' · '}
                      EV: {windowsData.best_windows.find(w => w.window_size === 10)!.best_window!.setup_usefulness_score?.toFixed(0) ?? "—"}
                    </span>
                  </div>
                  <button
                    className="trackmap-action-btn"
                    onClick={() => {
                      const bw = windowsData!.best_windows.find(w => w.window_size === 10)!.best_window!;
                      const item = makeBasketItem(
                        overview.run_id, bw.start_lap,
                        `Best 10-Lap Window (Laps ${bw.start_lap}–${bw.end_lap})`,
                        overview.session.car_name ?? null,
                        (overview.session.track_display_name ?? overview.session.track_name) ?? null,
                        overview.session.setup_name ?? null,
                        bw.average_lap_time ?? null,
                        bw.classification_tags ?? [],
                        bw.draft_status_summary,
                        bw.setup_usefulness_score ?? null,
                      );
                      setBaseline(item);
                    }}
                    title="Add as Baseline"
                  >
                    <Clock size={10} /> Baseline
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* ── Stint Map ── */}
      {subview === "current" && windowsData && laps.length > 0 && (
        <section className="workspace-section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            <span style={{ fontSize: 10, color: "#8d9aaa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Stint Shape</span>
            <div style={{ display: "flex", gap: 2 }}>
              {(["ev", "delta", "draft", "falloff"] as const).map((mode) => (
                <button
                  key={mode}
                  className={`setup-diff-toggle-btn ${stintMode === mode ? "active" : ""}`}
                  onClick={() => setStintMode(mode)}
                  style={{ fontSize: 9, padding: "2px 6px" }}
                >
                  {mode === "ev" ? "Eng Val" : mode === "delta" ? "Δ Time" : mode === "draft" ? "Draft" : "Falloff"}
                </button>
              ))}
            </div>
          </div>
          <div className="laps-stint-map">
            {laps.map((lap, idx) => {
              const tags = lap.classification_tags ?? [];
              const hasDraft = tags.some((t) => t.includes("DRAFT"));
              const isValid = lap.is_useful && !hasDraft;
              const isSelected = selection.selectedLap === lap.lap_number;
              // Find best window for this lap
              const inBestWindow = windowsData.best_windows.some((wg) =>
                wg.best_window && lap.lap_number >= wg.best_window.start_lap && lap.lap_number <= wg.best_window.end_lap
              );
              let color = "#1f2937";
              if (stintMode === "ev") {
                // Use Engineering Value from best window if available, else fallback
                const bw = windowsData.best_windows.find(w => w.window_size === 10)?.best_window;
                color = stintMapColor(bw?.setup_usefulness_score);
              } else if (stintMode === "delta") {
                const delta = lap.lap_time != null && bestTime != null ? lap.lap_time - bestTime : null;
                if (delta == null) color = "#1f2937";
                else if (delta < 0.1) color = "#22c55e";
                else if (delta < 0.5) color = "#f59e0b";
                else color = "#ef4444";
              } else if (stintMode === "draft") {
                color = hasDraft ? "#f59e0b" : isValid ? "#22c55e" : "#4a5568";
              } else if (stintMode === "falloff") {
                const falloff = windowsData.degradation?.falloff_slope_sec_per_lap;
                if (falloff == null) color = "#1f2937";
                else if (falloff < 0.01) color = "#22c55e";
                else if (falloff < 0.05) color = "#f59e0b";
                else color = "#ef4444";
              }
              return (
                <div
                  key={lap.lap_id}
                  className={`laps-stint-block ${isSelected ? "selected" : ""} ${!isValid ? "invalid" : ""} ${hasDraft ? "draft" : ""} ${inBestWindow ? "window-outline" : ""}`}
                  style={{ background: color }}
                  onClick={() => selectLap(lap.lap_number)}
                  title={`Lap ${lap.lap_number}: ${lap.lap_time != null ? lap.lap_time.toFixed(3) + "s" : "—"}${hasDraft ? " [DRAFT]" : ""}${!isValid ? " [INVALID]" : ""}`}
                />
              );
            })}
          </div>
          <div className="laps-stint-legend">
            <span className="laps-stint-legend-item">
              <span className="laps-stint-legend-swatch" style={{ background: "#22c55e" }} />
              {stintMode === "ev" ? "High EV" : stintMode === "delta" ? "Fast" : stintMode === "draft" ? "Clean" : "Low falloff"}
            </span>
            <span className="laps-stint-legend-item">
              <span className="laps-stint-legend-swatch" style={{ background: "#f59e0b" }} />
              {stintMode === "ev" ? "Medium EV" : stintMode === "delta" ? "Moderate Δ" : stintMode === "draft" ? "Draft" : "Moderate falloff"}
            </span>
            <span className="laps-stint-legend-item">
              <span className="laps-stint-legend-swatch" style={{ background: "#ef4444" }} />
              {stintMode === "ev" ? "Low EV" : stintMode === "delta" ? "Slow" : stintMode === "draft" ? "Invalid" : "High falloff"}
            </span>
            <span className="laps-stint-legend-item">
              <span className="laps-stint-legend-swatch" style={{ outline: "2px solid var(--cyan)", outlineOffset: 1, background: "transparent" }} />
              Selected
            </span>
            <span className="laps-stint-legend-item">
              <span className="laps-stint-legend-swatch" style={{ boxShadow: "0 0 0 1px var(--cyan)", background: "transparent" }} />
              Best window
            </span>
          </div>
        </section>
      )}

      {/* ── Windows subview ── */}
      {subview === "windows" && windowsData && (
        <section className="workspace-section">
          <h2><BarChart3 size={16} /> Best Windows</h2>
          {windowsData.best_windows.filter(w => w.is_available).length === 0 && (
            <p className="muted">No windows available. Need more valid laps.</p>
          )}
          {windowsData.best_windows.filter(w => w.is_available).map((wg) => (
            <div key={wg.window_size} style={{ marginBottom: 12 }}>
              <h4 style={{ fontSize: 12, color: "#8d9aaa", marginBottom: 4 }}>{wg.label}</h4>
              {wg.best_window && (
                <div className="setup-diff-row changed" style={{ justifyContent: "space-between" }}>
                  <div>
                    <span>Laps {wg.best_window.start_lap}–{wg.best_window.end_lap}</span>
                    <span className="muted" style={{ marginLeft: 8 }}>
                      Avg: {wg.best_window.average_lap_time?.toFixed(3)}s
                      {' · '}EV: {wg.best_window.setup_usefulness_score?.toFixed(0) ?? "—"}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <button
                      className="trackmap-action-btn"
                      onClick={() => {
                        const bw = wg.best_window!;
                        const item = makeBasketItem(
                          overview.run_id, bw.start_lap,
                          `${wg.label} (Laps ${bw.start_lap}–${bw.end_lap})`,
                          overview.session.car_name ?? null,
                          (overview.session.track_display_name ?? overview.session.track_name) ?? null,
                          overview.session.setup_name ?? null,
                          bw.average_lap_time ?? null,
                          bw.classification_tags ?? [],
                          bw.draft_status_summary,
                          bw.setup_usefulness_score ?? null,
                        );
                        setBaseline(item);
                      }}
                      title="Set as Baseline"
                    >
                      <Clock size={10} /> BL
                    </button>
                    <button
                      className="trackmap-action-btn"
                      onClick={() => {
                        const bw = wg.best_window!;
                        const item = makeBasketItem(
                          overview.run_id, bw.start_lap,
                          `${wg.label} (Laps ${bw.start_lap}–${bw.end_lap})`,
                          overview.session.car_name ?? null,
                          (overview.session.track_display_name ?? overview.session.track_name) ?? null,
                          overview.session.setup_name ?? null,
                          bw.average_lap_time ?? null,
                          bw.classification_tags ?? [],
                          bw.draft_status_summary,
                          bw.setup_usefulness_score ?? null,
                        );
                        setTest(item);
                      }}
                      title="Set as Test"
                    >
                      <Gauge size={10} /> Test
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </section>
      )}

      {/* ── Top Cards ── */}
      {subview === "current" && windowsData && (
        <section className="metrics-row" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))" }}>
          <div className="metric-card">
            <span><Trophy size={14} /> Fastest Lap</span>
            <strong style={{ color: "#22c55e" }}>
              {windowsData.fastest_groups[0]?.laps[0]?.lap_time != null
                ? formatTime(windowsData.fastest_groups[0].laps[0].lap_time)
                : "—"}
            </strong>
          </div>
          {[10, 20].map((size) => {
            const bw = windowsData.best_windows.find(w => w.window_size === size)?.best_window;
            const pqScore = bw?.pace_quality_score;
            const ecScore = bw?.evidence_confidence_score;
            const suScore = bw?.setup_usefulness_score;
            const warnings = bw?.pace_quality_warnings;
            const relationship = classifyPaceTrust(pqScore, ecScore, suScore, warnings);
            return (
              <div className="metric-card" key={size}>
                <span><Gauge size={14} /> Best {size}-Lap Avg</span>
                <strong style={{ color: "#38bdf8" }}>
                  {bw?.average_lap_time != null
                    ? formatTime(bw.average_lap_time)
                    : windowsData.total_valid_laps < size ? `Need ${size} laps` : "—"}
                </strong>
                <div style={{ fontSize: 10, color: "#8d9aaa", marginTop: 2 }}>{relationship}</div>
                <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                  {pqScore != null && (
                    <span title={PERFORMANCE_TOOLTIP} style={{ fontSize: 10, color: paceQualityColor(pqScore), background: `${paceQualityColor(pqScore)}15`, padding: "1px 6px", borderRadius: 4, whiteSpace: "nowrap", cursor: "default" }}>
                      Performance: {pqScore.toFixed(0)}
                    </span>
                  )}
                  {ecScore != null && (
                    <span title={TRUST_TOOLTIP} style={{ fontSize: 10, color: paceQualityColor(ecScore), background: `${paceQualityColor(ecScore)}15`, padding: "1px 6px", borderRadius: 4, whiteSpace: "nowrap", cursor: "default" }}>
                      Trust: {ecScore.toFixed(0)}
                    </span>
                  )}
                  {suScore != null && (
                    <span title={ENGINEERING_VALUE_TOOLTIP} style={{ fontSize: 10, color: paceQualityColor(suScore), background: `${paceQualityColor(suScore)}15`, padding: "1px 6px", borderRadius: 4, whiteSpace: "nowrap", cursor: "default" }}>
                      Engineering Value: {suScore.toFixed(0)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
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
      {subview === "current" && windowsData?.degradation?.coaching_message && windowsData.degradation.lap_count >= 10 && (
        <section className="crew-chief-brief" style={{ borderColor: "#f59e0b" }}>
          <h2>Pace Trend</h2>
          <p className="crew-chief-text">{windowsData.degradation.coaching_message}</p>
          {windowsData.degradation.draft_warning && (
            <p className="warning-line" style={{ marginTop: 6 }}><AlertTriangle size={12} /> {windowsData.degradation.draft_warning}</p>
          )}
        </section>
      )}

      {/* ── Lap Table ── */}
      {subview === "current" && (
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
                          <button className="trackmap-action-btn" onClick={(e) => {
                            e.stopPropagation();
                            const item = makeBasketItem(
                              overview.run_id, lap.lap_number,
                              `Lap ${lap.lap_number}`,
                              overview.session.car_name ?? null,
                              (overview.session.track_display_name ?? overview.session.track_name) ?? null,
                              overview.session.setup_name ?? null,
                              lap.lap_time ?? null,
                              lap.classification_tags ?? [],
                              tags.some(t => t.includes("DRAFT")) ? "DRAFT_AFFECTED" : "LIKELY_SOLO",
                              null,
                            );
                            setTest(item);
                          }} title="Set as Test in Compare Basket">
                            <Gauge size={10} />
                          </button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr key={`${lap.lap_id}-expanded`}>
                        <td colSpan={8} style={{ padding: "8px 16px", background: "#0a0d14" }}>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 8 }}>
                            <div><span className="muted">Max Speed</span><br /><ValueDisplay value={lap.max_speed_mph} unit="mph" precision={1} /></div>
                            <div><span className="muted">Min Splitter</span><br /><ValueDisplay value={lap.min_splitter_mm} unit="mm" precision={1} /></div>
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
      )}
    </div>
  );
}
