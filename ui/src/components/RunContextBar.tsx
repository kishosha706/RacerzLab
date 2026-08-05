import { AlertTriangle, Car, CheckCircle, Flag, Gauge, Info, MapPin, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

function windDirectionDegrees(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "unknown";
  const degrees = ((value * 180 / Math.PI) % 360 + 360) % 360;
  return `${degrees.toFixed(0)}°`;
}

export function RunContextBar({ overview, runs: _runs, onSelectLap }: RunContextBarProps) {
  const { selection, setMode } = useTelemetrySelection();
  const { basket, getReadiness } = useCompareBasket();
  const readiness = basket.baseline && basket.test ? getReadiness().status : null;
  const session = overview?.session;
  const laps = overview?.laps ?? [];
  const [showSessionInfo, setShowSessionInfo] = useState(false);
  const sessionInfoRef = useRef<HTMLDivElement | null>(null);

  const handleLapChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    onSelectLap?.(val ? Number(val) : null);
  }, [onSelectLap]);

  const handleModeToggle = useCallback(() => {
    setMode(selection.selectedMode === "learning" ? "race" : "learning");
  }, [selection.selectedMode, setMode]);

  const modeLabel = useMemo(() => humanizeModeLabel(selection.selectedMode), [selection.selectedMode]);
  const wsLabel = useMemo(() => humanizeWorkspaceLabel(selection.selectedWorkspace), [selection.selectedWorkspace]);

  useEffect(() => {
    if (!showSessionInfo) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowSessionInfo(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showSessionInfo]);

  return (
    <header className="context-bar">
      <div className="context-bar-left">
        <span className="context-brand">RacerZLab</span>
        {session && (
          <>
            <span className="context-sep">|</span>
            <span className="context-item"><MapPin size={14} /> {session.track_display_name ?? session.track_name ?? "Unknown Track"}</span>
            <span className="context-sep">|</span>
            <span className="context-item"><Car size={14} /> {session.car_name ?? "Unknown Car"}</span>
            <span className="context-sep">|</span>
            <span className="context-item"><Wrench size={14} /> {session.setup_name ?? "Unknown Setup"}</span>

            {/* Session Info trigger — shows secondary metadata in a popover */}
            <div ref={sessionInfoRef} style={{ position: "relative", display: "inline-flex" }}>
              <button
                type="button"
                className="session-info-trigger"
                onClick={() => setShowSessionInfo(!showSessionInfo)}
                onBlur={() => setTimeout(() => setShowSessionInfo(false), 200)}
                aria-expanded={showSessionInfo}
                aria-controls="session-details-popover"
                aria-haspopup="dialog"
              >
                <Info size={14} /> Session
              </button>
              {showSessionInfo && (
                <div
                  id="session-details-popover"
                  className="session-info-popover"
                  role="dialog"
                  aria-label="Session details"
                  onMouseDown={(e) => e.preventDefault()}
                >
                  <h4>Session Details</h4>
                  <dl>
                    {session.session_type && <><dt>Type</dt><dd>{session.session_type}</dd></>}
                    {session.weather_summary && <><dt>Weather</dt><dd>{session.weather_summary}</dd></>}
                    {session.air_temp != null && <><dt>Air Temp</dt><dd>{session.air_temp.toFixed(0)}°C</dd></>}
                    {session.track_temp != null && <><dt>Track Temp</dt><dd>{session.track_temp.toFixed(0)}°C</dd></>}
                    {session.wind_speed != null && (
                      <>
                        <dt>Wind</dt>
                        <dd>{session.wind_speed.toFixed(1)} m/s ({(session.wind_speed * 2.236936).toFixed(1)} mph) @ {windDirectionDegrees(session.wind_direction)}</dd>
                      </>
                    )}
                    {session.duration_seconds != null && <><dt>Duration</dt><dd>{Math.round(session.duration_seconds / 60)} min</dd></>}
                  </dl>
                  <h4>Tech Status</h4>
                  <div className="popover-row">
                    <CheckCircle size={12} />
                    {session.setup_passed_tech != null
                      ? `Tech ${session.setup_passed_tech ? "Passed" : "Failed"}`
                      : "Tech Unknown"}
                    {session.setup_modified && <span style={{ color: "#f59e0b" }}> · Modified</span>}
                  </div>
                </div>
              )}
            </div>
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

        {selection.selectedLapScope === "lap_window" && selection.selectedLapWindowStart != null && selection.selectedLapWindowEnd != null && (
          <span className="context-tag-badge" style={{ borderColor: "#38bdf8", color: "#38bdf8" }}>
            Window {selection.selectedLapWindowStart}-{selection.selectedLapWindowEnd}
          </span>
        )}
        {selection.selectedLapScope === "lap_window" && selection.selectedRepresentativeLap != null && (
          <span className="context-tag-badge" style={{ borderColor: "#cbd5e1", color: "#cbd5e1" }}>
            Rep Lap {selection.selectedRepresentativeLap}
          </span>
        )}
        {(selection.selectedZoneLabel || (selection.selectedZoneStartPct != null && selection.selectedZoneEndPct != null)) && (
          <span className="context-tag-badge" style={{ borderColor: "#f59e0b", color: "#f59e0b" }}>
            {selection.selectedZoneLabel
              ? `Area ${selection.selectedZoneLabel}`
              : `Zone ${selection.selectedZoneStartPct?.toFixed(1)}-${selection.selectedZoneEndPct?.toFixed(1)}%`}
          </span>
        )}

        {/* mode badge — clickable toggle */}
        <button
          type="button"
          className={`context-badge mode-badge mode-${selection.selectedMode}`}
          onClick={handleModeToggle}
          aria-live="polite"
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
