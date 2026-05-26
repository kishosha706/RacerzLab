import { Activity, Flag, Upload } from "lucide-react";
import type { RunOverview } from "../types/telemetry";

type RunHeaderProps = {
  overview: RunOverview;
};

export function RunHeader({ overview }: RunHeaderProps) {
  const session = overview.session;
  const lap = overview.best_useful_lap;

  return (
    <header className="run-header">
      <div>
        <p className="eyebrow">RaceLab Garage</p>
        <h1>{session.track_display_name ?? "No run loaded"}</h1>
      </div>
      <div className="run-header-meta">
        <span><Flag size={16} /> {session.car_name ?? "Unknown car"}</span>
        <span><Activity size={16} /> Useful lap {lap?.lap_number ?? "n/a"}</span>
        <span>{session.setup_name ?? "No setup"}</span>
      </div>
      <button className="icon-button" title="Import IBT">
        <Upload size={18} />
      </button>
    </header>
  );
}
