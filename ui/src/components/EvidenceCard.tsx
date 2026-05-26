import { AlertTriangle, Gauge, MapPin } from "lucide-react";
import type { TelemetryEvent } from "../types/telemetry";

type EvidenceCardProps = {
  event: TelemetryEvent;
};

export function EvidenceCard({ event }: EvidenceCardProps) {
  const confidence = `${Math.round(event.confidence_score * 100)}%`;

  return (
    <article className="evidence-card">
      <header>
        <span className={`severity severity-${event.severity}`}>{event.severity}</span>
        <strong>{event.event_type.replace(/_/g, " ")}</strong>
      </header>
      <div className="evidence-grid">
        <span><MapPin size={15} /> {event.zone_name ?? "Unknown zone"}</span>
        <span><Gauge size={15} /> {event.primary_metric_name}: {event.primary_metric_value ?? "n/a"}</span>
        <span><AlertTriangle size={15} /> {confidence}</span>
      </div>
      <p>{event.recommended_actions[0] ?? "No action attached yet."}</p>
    </article>
  );
}
