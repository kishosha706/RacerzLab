import { Car, Flag, Gauge, MapPin, ThermometerSun, Wrench } from "lucide-react";
import { useCallback } from "react";
import type { RunOverview, LapSummary } from "../types/telemetry";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";

type RunContextBarProps = {
  overview: RunOverview | null;
  runs: Array<{ run_id: string; track_name?: string | null }>;
  onSelectRun: (runId: string) => void;
  onSelectLap?: (lap: number | null) => void;
};

export function RunContextBar({ overview, runs, onSelectRun, onSelectLap }: RunContextBarProps) {
  const { selection } = useTelemetrySelection();
  const session = overview?.session;
  const laps = overview?.laps ?? [];

  const handleLapChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    onSelectLap?.(val ? Number(val) : null);
  }, [onSelectLap]);

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
        <select
          value={overview?.run_id ?? ""}
          onChange={(e) => onSelectRun(e.target.value)}
          className="context-run-select"
          aria-label="Select run"
        >
          {runs.map((run) => (
            <option key={run.run_id} value={run.run_id}>
              {run.track_name ?? "Run"}
            </option>
          ))}
        </select>

        {/* lap selector */}
        {laps.length > 0 && (
          <select
            value={selection.selectedLap ?? ""}
            onChange={handleLapChange}
            className="context-lap-select"
            aria-label="Select lap"
          >
            <option value="">Lap —</option>
            {laps.map((lap: LapSummary) => (
              <option key={lap.lap_number} value={lap.lap_number}>
                Lap {lap.lap_number}
                {lap.lap_time != null ? ` — ${lap.lap_time.toFixed(3)}s` : ""}
                {lap.is_useful ? "" : " (invalid)"}
              </option>
            ))}
          </select>
        )}

        <span className="context-badge mode-badge">
          <Gauge size={14} /> {selection.selectedMode}
        </span>
        {selection.selectedWorkspace !== "overview" && (
          <span className="context-badge workspace-badge">
            <Flag size={14} /> {selection.selectedWorkspace.replace(/_/g, " ")}
          </span>
        )}
      </div>
    </header>
  );
}
