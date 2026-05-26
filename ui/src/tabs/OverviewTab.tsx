import { EvidenceCard } from "../components/EvidenceCard";
import { MetricCard } from "../components/MetricCard";
import type { RunOverview } from "../types/telemetry";

type OverviewTabProps = {
  overview: RunOverview;
};

export function OverviewTab({ overview }: OverviewTabProps) {
  const lap = overview.best_useful_lap;

  return (
    <div className="tab-grid">
      <section className="metrics-row">
        <MetricCard label="Best lap" value={lap ? `Lap ${lap.lap_number}` : "n/a"} tone="good" />
        <MetricCard label="Avg speed" value={lap?.avg_speed_mph ? `${lap.avg_speed_mph.toFixed(2)} mph` : "n/a"} />
        <MetricCard label="Min splitter" value={lap?.min_splitter_mm ? `${lap.min_splitter_mm.toFixed(2)} mm` : "n/a"} tone="warn" />
        <MetricCard label="Brake" value={lap?.avg_brake_pct != null ? `${lap.avg_brake_pct}%` : "n/a"} />
      </section>
      <section className="workspace-section">
        <h2>Primary Findings</h2>
        <ol className="findings-list">
          {overview.primary_findings.map((finding) => (
            <li key={finding}>{finding}</li>
          ))}
        </ol>
      </section>
      <section className="evidence-list">
        {overview.events.map((event) => (
          <EvidenceCard event={event} key={event.event_id} />
        ))}
      </section>
    </div>
  );
}
