import { AlertTriangle, Car, CheckCircle, Clock, Flag, Gauge, MapPin, ThermometerSun, Wind, Wrench } from "lucide-react";
import { useCallback, useMemo } from "react";
import type { RunOverview, LapSummary } from "../types/telemetry";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket } from "../store/CompareBasketContext";
import { humanizeWorkspaceLabel, humanizeModeLabel, classifyLapTags, humanizeClassificationTag } from "../constants/ui";

type RunContextBarProps = {
  overview: RunOverview | null;
  runs: Array<{ run_id: string; track_name?: string | null }>;
  onSelectRun: (runId: string) => void;
  onSelectLap?: (lap: number | null) => void;
};

export function RunContextBar({ overview, runs: _runs, onSelectLap }: RunContextBarProps) {
  const { selection, setMode } = useTelemetrySelection();
  const { basket, getReadiness } = useCompareBasket();
  const readiness = basket.baseline && basket.test ? getReadiness().status : null;
  const session = overview?.session;
  const laps = overview?.laps ?? [];

  const handleLapChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    onSelectLap?.(val ? Number(val) : null);
  }, [onSelectLap]);

  const handleModeToggle = useCallback(() => {
    setMode(selection.selectedMode === "learning" ? "race" : "learning");
  }, [selection.selectedMode, setMode]);

  const modeLabel = useMemo(() => humanizeModeLabel(selection.selectedMode), [selection.selectedMode]);
  const wsLabel = useMemo(() => humanizeWorkspaceLabel(selection.selectedWorkspace), [selection.selectedWorkspace]);

  return (
    <header className="context-bar">
      <div className="context-bar-left">
        <span className="context-brand">RaceLab Garage</span>
        {session && (
          <>
            <span className="context-sep">|</span>
            <span className="context-item"><MapPin size={14} /> {session.track_display_name ?? session.track_name ?? "Unknown Track"}</span>
            <span className="context-sep">|</span>
            <span className="context-item"><Car size={14} /> {session.car_name ?? "Unknown Car"}</span>
            <span className="context-sep">|</span>
            <span className="context-item"><Wrench size={14} /> {session.setup_name ?? "Unknown Setup"}</span>
            {session.setup_passed_tech != null && (
              <>
                <span className="context-sep">|</span>
                <span className={`context-item ${session.setup_passed_tech ? "" : "text-critical"}`}>
                  <CheckCircle size={14} /> Tech {session.setup_passed_tech ? "Passed" : "Failed"}
                </span>
              </>
            )}
            {session.setup_passed_tech == null && session.setup_name && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item muted">Tech Unknown</span>
              </>
            )}
            {session.setup_modified != null && session.setup_modified && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item" style={{ color: "#f59e0b" }}>Modified</span>
              </>
            )}
            {session.weather_summary && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item"><ThermometerSun size={14} /> {session.weather_summary}</span>
              </>
            )}
            {session.session_type && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item"><Flag size={14} /> {session.session_type}</span>
              </>
            )}
            {session.air_temp != null && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item" title="Air / Track temp"><ThermometerSun size={14} /> {session.air_temp.toFixed(0)}°C{ session.track_temp != null ? ` / ${session.track_temp.toFixed(0)}°C` : ""}</span>
              </>
            )}
            {session.wind_speed != null && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item" title={`Wind ${session.wind_speed} mph @ ${session.wind_direction ?? "?"}°`}><Wind size={14} /> {session.wind_speed.toFixed(0)} mph</span>
              </>
            )}
            {session.duration_seconds != null && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item"><Clock size={14} /> {Math.round(session.duration_seconds / 60)} min</span>
              </>
            )}
          </>
        )}
      </div>

      <div className="context-bar-right">
        {/* lap selector with classification tags */}
        {laps.length > 0 && (
          <select
            value={selection.selectedLap ?? ""}
            onChange={handleLapChange}
            className="context-lap-select"
            aria-label="Select lap"
          >
            <option value="">Lap —</option>
            {laps.map((lap: LapSummary) => {
              const tags = lap.classification_tags ?? [];
              const tagLabels = tags
                .map(t => humanizeClassificationTag(t))
                .slice(0, 2);
              const tagStr = tagLabels.length > 0 ? ` [${tagLabels.join(", ")}]${tags.length > 2 ? " +" : ""}` : "";
              return (
                <option key={lap.lap_number} value={lap.lap_number}>
                  Lap {lap.lap_number}
                  {lap.lap_time != null ? ` — ${lap.lap_time.toFixed(3)}s` : ""}
                  {lap.is_useful ? "" : " (invalid)"}
                  {tagStr}
                </option>
              );
            })}
          </select>
        )}

        {/* lap tag badges */}
        {selection.selectedLap != null && (
          (() => {
            const lap = laps.find(l => l.lap_number === selection.selectedLap);
            if (!lap?.classification_tags?.length) return null;
            const cls = classifyLapTags(lap.classification_tags);
            return cls ? (
              <span className="context-tag-badge" style={{ borderColor: cls.color, color: cls.color }}>
                {cls.label}
              </span>
            ) : null;
          })()
        )}

        {/* mode badge — clickable toggle */}
        <button
          className={`context-badge mode-badge mode-${selection.selectedMode}`}
          onClick={handleModeToggle}
          aria-label={selection.selectedMode === "learning"
            ? "Learning Mode — click to switch to Race Mode"
            : "Race Mode — click to switch to Learning Mode"}
          title={selection.selectedMode === "learning"
            ? "Learning Mode: coaching and explains why — Click for Race Mode"
            : "Race Mode: short, decision-first output — Click for Learning Mode"}
        >
          <Gauge size={14} /> {modeLabel}
        </button>

        {selection.selectedWorkspace !== "overview" && (
          <span className="context-badge workspace-badge">
            <Flag size={14} /> {wsLabel}
          </span>
        )}

        {/* basket status badge */}
        {basket.baseline && basket.test && (
          <span className={`context-badge basket-status-badge basket-status-${readiness}`}>
            {readiness === "ready" ? <CheckCircle size={12} /> : <AlertTriangle size={12} />}
            {readiness === "ready" || readiness === "caution" ? (readiness ?? "").toUpperCase() : ""}
          </span>
        )}
        {(basket.baseline || basket.test) && !(basket.baseline && basket.test) && (
          <span className="context-badge basket-status-badge basket-status-partial">1/2</span>
        )}

        {/* baseline/test badges */}
        {overview?.run_id && (
          <>
            {basket.baseline?.run_id === overview.run_id && basket.test?.run_id !== overview.run_id && (
              <span className="context-badge context-badge-primary">BASELINE</span>
            )}
            {basket.test?.run_id === overview.run_id && basket.baseline?.run_id !== overview.run_id && (
              <span className="context-badge context-badge-primary">TEST</span>
            )}
            {basket.baseline?.run_id === overview.run_id && basket.test?.run_id === overview.run_id && (
              <span className="context-badge context-badge-reference">REFERENCE</span>
            )}
          </>
        )}

        {/* keyboard hint */}
        <span className="context-hint">? help</span>
      </div>
    </header>
  );
}
