import { ClipboardCheck, ShieldAlert } from "lucide-react";
import type { RunOverview } from "../types/telemetry";

type CrewChiefPanelProps = {
  overview: RunOverview;
};

export function CrewChiefPanel({ overview }: CrewChiefPanelProps) {
  const recommendation = overview.recommendations[0];

  return (
    <aside className="crew-panel">
      <header>
        <ClipboardCheck size={18} />
        <h2>Crew Chief</h2>
      </header>
      <p className="crew-summary">{overview.crew_chief_summary}</p>
      {recommendation ? (
        <section className="crew-block">
          <span className="eyebrow">Next test</span>
          <p>{recommendation.recommendation_text}</p>
          <strong>{recommendation.success_metric}</strong>
        </section>
      ) : (
        <section className="crew-block">
          <span className="eyebrow">No call</span>
          <p>No recommendation is shown without supporting evidence.</p>
        </section>
      )}
      <section className="crew-block warnings">
        <span><ShieldAlert size={16} /> Warnings</span>
        {overview.warnings.map((warning) => (
          <p key={warning}>{warning}</p>
        ))}
      </section>
    </aside>
  );
}
