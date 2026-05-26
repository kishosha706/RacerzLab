import { CheckCircle, Clock, Flag, XCircle } from "lucide-react";
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
              <span className="lap-row-status">
                {lap.is_useful ? <CheckCircle size={12} color="#22c55e" /> : <XCircle size={12} color="#ef4444" />}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
