import { Car, Flag, Gauge, MapPin, ThermometerSun, Wrench } from "lucide-react";
import { useCallback, useMemo } from "react";
import type { RunOverview, LapSummary } from "../types/telemetry";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { humanizeWorkspaceLabel, humanizeModeLabel, classifyLapTags, humanizeClassificationTag } from "../constants/ui";

type RunContextBarProps = {
  overview: RunOverview | null;
  runs: Array<{ run_id: string; track_name?: string | null }>;
  onSelectRun: (runId: string) => void;
  onSelectLap?: (lap: number | null) => void;
};

export function RunContextBar({ overview, runs, onSelectLap }: RunContextBarProps) {
  const { selection, setMode } = useTelemetrySelection();
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
            {session.weather_summary && (
              <>
                <span className="context-sep">|</span>
                <span className="context-item"><ThermometerSun size={14} /> {session.weather_summary}</span>
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
                  {!lap.is_useful ? " (invalid)" : ""}
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

        {/* baseline badge TODO */}
        {/* Future: show "Baseline" / "Test Run" badge from session/notebook state */}
      </div>
    </header>
  );
}
