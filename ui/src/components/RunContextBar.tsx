import { AlertTriangle, Car, CheckCircle, Flag, Gauge, Info, MapPin, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RunOverview, LapSummary, RunListItem } from "../types/telemetry";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket } from "../store/CompareBasketContext";
import { humanizeWorkspaceLabel, humanizeModeLabel, classifyLapTags, humanizeClassificationTag } from "../constants/ui";
import { bestUsefulLapMatchesRun } from "../utils/evidenceTrust";

type RunContextBarProps = {
  overview: RunOverview | null;
  runs: RunListItem[];
  onSelectRun: (runId: string) => void;
  onSelectLap?: (lap: number | null) => void;
};

const LONG_RUN_REVIEW_MIN_LAPS = 10;

function isEligiblePaceLap(lap: LapSummary, runId: string | null): boolean {
  return runId != null && bestUsefulLapMatchesRun(lap, runId);
}

function longestContinuousEligibleLapBlock(laps: readonly LapSummary[]): number {
  const lapNumbers = [...new Set(laps.map((lap) => lap.lap_number))].sort((left, right) => left - right);
  let longest = 0;
  let current = 0;
  let previous: number | null = null;
  for (const lapNumber of lapNumbers) {
    current = previous != null && lapNumber === previous + 1 ? current + 1 : 1;
    longest = Math.max(longest, current);
    previous = lapNumber;
  }
  return longest;
}

function runOptionLabel(run: RunListItem, index: number): string {
  const rawSetup = run.setup_name ?? "Setup unknown";
  const setup = rawSetup.length > 24 ? `${rawSetup.slice(0, 23).trimEnd()}…` : rawSetup;
  const laps = run.lap_count != null ? `${run.lap_count} laps` : "laps unknown";
  const bestLapTime = run.best_lap_time ?? run.best_lap_time_s;
  const best = bestLapTime != null && Number.isFinite(bestLapTime)
    ? ` · Best ${bestLapTime.toFixed(3)}s`
    : "";
  return `Run ${index + 1} · ${setup} · ${laps}${best}`;
}

function windDirectionDegrees(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "unknown";
  const degrees = ((value * 180 / Math.PI) % 360 + 360) % 360;
  return `${degrees.toFixed(0)}°`;
}

export function RunContextBar({ overview, runs, onSelectRun, onSelectLap }: RunContextBarProps) {
  const { selection, setMode } = useTelemetrySelection();
  const { basket, getReadiness } = useCompareBasket();
  const readiness = basket.baseline && basket.test ? getReadiness().status : null;
  const session = overview?.session;
  const laps = overview?.laps ?? [];
  const [showSessionInfo, setShowSessionInfo] = useState(false);
  const sessionInfoRef = useRef<HTMLDivElement | null>(null);
  const availableRuns = useMemo(() => {
    const byId = new Map(runs.map((run) => [run.run_id, run]));
    if (overview && !byId.has(overview.run_id)) {
      byId.set(overview.run_id, {
        run_id: overview.run_id,
        car_name: overview.session.car_name,
        track_name: overview.session.track_name,
        setup_name: overview.session.setup_name,
        best_lap_number: overview.best_useful_lap?.lap_number ?? null,
        best_lap_time: overview.best_useful_lap?.lap_time ?? null,
        lap_count: overview.laps.length,
        has_setup_snapshot: overview.setup_snapshot != null,
      });
    }
    return [...byId.values()];
  }, [overview, runs]);

  const handleRunChange = useCallback((event: React.ChangeEvent<HTMLSelectElement>) => {
    const runId = event.target.value;
    if (runId && runId !== overview?.run_id) onSelectRun(runId);
  }, [onSelectRun, overview?.run_id]);

  const handleLapChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    onSelectLap?.(val ? Number(val) : null);
  }, [onSelectLap]);

  const handleModeToggle = useCallback(() => {
    setMode(selection.selectedMode === "learning" ? "race" : "learning");
  }, [selection.selectedMode, setMode]);

  const modeLabel = useMemo(() => humanizeModeLabel(selection.selectedMode), [selection.selectedMode]);
  const wsLabel = useMemo(() => humanizeWorkspaceLabel(selection.selectedWorkspace), [selection.selectedWorkspace]);
  const fullSourceFilename = session?.source_file ?? null;
  const currentRunPosition = overview
    ? availableRuns.findIndex((run) => run.run_id === overview.run_id) + 1
    : 0;
  const eligiblePaceLaps = useMemo(
    () => laps.filter((lap) => isEligiblePaceLap(lap, overview?.run_id ?? null)),
    [laps, overview?.run_id],
  );
  const longestCleanBlock = useMemo(
    () => longestContinuousEligibleLapBlock(eligiblePaceLaps),
    [eligiblePaceLaps],
  );
  const bestCleanLap = useMemo(
    () => eligiblePaceLaps.reduce<LapSummary | null>((best, candidate) => (
      best == null || (candidate.lap_time as number) < (best.lap_time as number) ? candidate : best
    ), null),
    [eligiblePaceLaps],
  );
  const cleanLapsNeeded = Math.max(0, LONG_RUN_REVIEW_MIN_LAPS - longestCleanBlock);
  const cleanReadinessLabel = cleanLapsNeeded === 0
    ? `${eligiblePaceLaps.length} clean · 10+ block`
    : `${eligiblePaceLaps.length} clean · Run ${longestCleanBlock}/${LONG_RUN_REVIEW_MIN_LAPS}`;

  useEffect(() => {
    if (!showSessionInfo) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowSessionInfo(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [showSessionInfo]);

  return (
    <header className="context-bar context-bar-two-tier" aria-label="Current telemetry context">
      <div className="context-bar-left">
        <span className="context-brand-lockup">
          <span className="context-brand-mark" aria-hidden="true">RZ</span>
          <span className="context-brand">
            <strong>RacerZLab</strong>
            <small>Decision cockpit</small>
          </span>
        </span>
        {session && (
          <>
            <span className="context-sep">|</span>
            <span className="context-item context-item-primary" title={session.track_display_name ?? session.track_name ?? "Unknown Track"}>
              <MapPin size={14} />
              <span className="context-item-copy">
                <small>{session.track_temp != null ? `Track · ${session.track_temp.toFixed(0)}°C` : "Track"}</small>
                <strong>{session.track_display_name ?? session.track_name ?? "Unknown Track"}</strong>
              </span>
            </span>
            <span className="context-sep">|</span>
            <span className="context-item" title={session.car_name ?? "Unknown Car"}>
              <Car size={14} />
              <span className="context-item-copy"><small>Car</small><strong>{session.car_name ?? "Unknown Car"}</strong></span>
            </span>
            <span className="context-sep">|</span>
            <span className="context-item" title={session.setup_name ?? "Unknown Setup"}>
              <Wrench size={14} />
              <span className="context-item-copy">
                <small>
                  {session.setup_passed_tech === true
                    ? "Setup · Tech pass"
                    : session.setup_passed_tech === false
                      ? "Setup · Tech failed"
                      : "Setup · Tech unknown"}
                </small>
                <strong>{session.setup_name ?? "Unknown Setup"}</strong>
              </span>
            </span>

            {/* Session Info trigger — shows secondary metadata in a popover */}
            <div
              ref={sessionInfoRef}
              className="session-info-anchor"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setShowSessionInfo(false);
              }}
            >
              <button
                type="button"
                className="session-info-trigger"
                onClick={() => setShowSessionInfo(!showSessionInfo)}
                aria-expanded={showSessionInfo}
                aria-controls="session-details-popover"
              >
                <Info size={14} /> Details
              </button>
              {showSessionInfo && (
                <div
                  id="session-details-popover"
                  className="session-info-popover"
                  role="region"
                  aria-label="Session details"
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
                    {session.setup_passed_tech === false ? <AlertTriangle size={12} /> : <CheckCircle size={12} />}
                    {session.setup_passed_tech != null
                      ? `Tech ${session.setup_passed_tech ? "Passed" : "Failed"}`
                      : "Tech Unknown"}
                    {session.setup_modified && <span style={{ color: "#f59e0b" }}> · Modified</span>}
                  </div>
                  <h4>Run Readiness</h4>
                  <dl>
                    <dt>Clean pace laps</dt><dd>{eligiblePaceLaps.length} / {laps.length}</dd>
                    <dt>Best clean lap</dt><dd>{bestCleanLap?.lap_time != null ? `Lap ${bestCleanLap.lap_number} · ${bestCleanLap.lap_time.toFixed(3)}s` : "Not available"}</dd>
                    <dt>Continuous block</dt>
                    <dd>
                      {longestCleanBlock} lap{longestCleanBlock === 1 ? "" : "s"}
                      {cleanLapsNeeded > 0 ? ` · ${cleanLapsNeeded} more for long-run review` : " · long-run review available"}
                    </dd>
                  </dl>
                  <p className="muted">The 10-lap gate opens long-run inspection; it does not by itself prove tire degradation or a setup cause.</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <div className="context-bar-right" aria-label="Run, lap, and mode controls">
        {overview && availableRuns.length > 0 && (
          <label className="context-control context-run-control">
            <span className="context-control-label">Run</span>
            <span className="context-control-position" aria-hidden="true">{currentRunPosition}/{availableRuns.length}</span>
            <select
              value={overview.run_id}
              onChange={handleRunChange}
              className="context-run-select"
              aria-label="Open a run attached to this session"
              title={fullSourceFilename ? `Source file: ${fullSourceFilename}` : "Open a run attached to this session"}
            >
              {availableRuns.map((run, index) => (
                <option
                  key={run.run_id}
                  value={run.run_id}
                  title={run.run_id === overview.run_id && fullSourceFilename ? fullSourceFilename : runOptionLabel(run, index)}
                >
                  {runOptionLabel(run, index)}
                </option>
              ))}
            </select>
          </label>
        )}

        {/* lap selector with classification tags */}
        {laps.length > 0 && (
          <label className="context-control context-lap-control">
            <span className="context-control-label">Lap</span>
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
          </label>
        )}

        {overview && (
          <span
            className="context-tag-badge"
            data-readiness={cleanLapsNeeded === 0 ? "long-run-review" : "short-run"}
            style={{ borderColor: cleanLapsNeeded === 0 ? "#22c55e" : "#f59e0b", color: cleanLapsNeeded === 0 ? "#22c55e" : "#f59e0b" }}
            title={cleanLapsNeeded === 0
              ? `${longestCleanBlock} consecutive clean pace laps are available for long-run inspection.`
              : `Bank ${cleanLapsNeeded} more consecutive clean pace lap${cleanLapsNeeded === 1 ? "" : "s"} before long-run inspection.`}
            aria-label={`Run readiness: ${eligiblePaceLaps.length} eligible clean pace laps. Longest continuous clean block ${longestCleanBlock} laps; ${LONG_RUN_REVIEW_MIN_LAPS} required for long-run inspection.`}
          >
            {cleanReadinessLabel}
          </span>
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
          <Gauge size={14} aria-hidden="true" />
          <span className="mode-badge-copy"><small>Output</small><strong>{modeLabel}</strong></span>
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
