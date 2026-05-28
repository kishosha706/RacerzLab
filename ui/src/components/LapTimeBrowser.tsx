import { AlertTriangle, CheckCircle, Clock, Flag, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchRunLapList } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { LapSummaryItem, RunLapList } from "../types/session";

type LapTimeBrowserProps = {
  runId: string | null;
};

const LAP_TYPE_COLORS: Record<string, string> = {
  out: "#8d9aaa",
  timed: "#22c55e",
  in: "#8d9aaa",
  unknown: "#6b7280",
};

const LAP_TYPE_LABELS: Record<string, string> = {
  out: "Out",
  timed: "Timed",
  in: "In",
  unknown: "Unknown",
};

export function LapTimeBrowser({ runId }: LapTimeBrowserProps) {
  const { selection, selectLap } = useTelemetrySelection();
  const [lapList, setLapList] = useState<RunLapList | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!runId) { setLapList(null); return; }
    setLoading(true);
    fetchRunLapList(runId).then(setLapList).catch(() => setLapList(null)).finally(() => setLoading(false));
  }, [runId]);

  const handleLapClick = useCallback((lap: LapSummaryItem) => {
    selectLap(lap.lap_number);
  }, [selectLap]);

  if (!runId) {
    return (
      <div className="lap-browser-empty">
        <p className="muted">Select a run to view laps.</p>
      </div>
    );
  }

  if (loading) {
    return <div className="lap-browser-loading"><p className="muted">Loading laps…</p></div>;
  }

  if (!lapList || lapList.laps.length === 0) {
    return (
      <div className="lap-browser-empty">
        <p className="muted">No lap data available for this run.</p>
      </div>
    );
  }

  return (
    <div className="lap-browser">
      <div className="lap-browser-header">
        <span className="lap-browser-title"><Clock size={14} /> Laps</span>
        <span className="lap-browser-count">{lapList.laps.length} laps</span>
      </div>
      <div className="lap-browser-run-name">{lapList.display_name}</div>
      <div className="lap-browser-list">
        {lapList.laps.map((lap) => {
          const isSelected = selection.selectedLap === lap.lap_number;
          const isBest = lap.delta_display === "BEST";
          const hasDraftFlag = lap.warnings?.some((w) => w.toLowerCase().includes("draft")) ?? false;
          const hasInvalidFlag = !lap.is_useful || (lap.invalid_reasons?.length ?? 0) > 0;
          return (
            <button
              key={lap.lap_id}
              className={`lap-browser-row ${isSelected ? "selected" : ""} ${lap.is_useful ? "useful" : "invalid"}`}
              onClick={() => handleLapClick(lap)}
            >
              <span className="lap-row-indicator" style={{ backgroundColor: LAP_TYPE_COLORS[lap.lap_type] ?? "#6b7280" }} />
              <span className="lap-row-label">
                {lap.label}
                {lap.lap_type === "timed" && <Flag size={10} className="lap-timed-icon" />}
              </span>
              <span className="lap-row-time">{lap.lap_time_display}</span>
              <span className={`lap-row-delta ${isBest ? "best" : ""}`}>
                {isBest ? "BEST" : lap.delta_display}
              </span>
              <span className="lap-row-badges">
                {/* Lap type badge */}
                <span className="lap-type-badge" style={{ background: `${LAP_TYPE_COLORS[lap.lap_type] ?? "#6b7280"}20`, color: LAP_TYPE_COLORS[lap.lap_type] ?? "#6b7280" }}>
                  {LAP_TYPE_LABELS[lap.lap_type] ?? lap.lap_type}
                </span>
                {/* Draft flag */}
                {hasDraftFlag && (
                  <span className="lap-flag-badge lap-flag-draft" title="Draft suspected">
                    <AlertTriangle size={10} /> Draft
                  </span>
                )}
                {/* Invalid flag */}
                {hasInvalidFlag && (
                  <span className="lap-flag-badge lap-flag-invalid" title="Invalid for clean comparison">
                    <XCircle size={10} /> Invalid
                  </span>
                )}
              </span>
              <span className="lap-row-status">
                {lap.is_useful ? <CheckCircle size={12} color="#22c55e" /> : <XCircle size={12} color="#ef4444" />}
              </span>
            </button>
          );
        })}
      </div>
      {/* TODO: If backend provides draft-suspected or dirty/invalid flags, show Draft Suspected / Dirty badges */}
    </div>
  );
}
