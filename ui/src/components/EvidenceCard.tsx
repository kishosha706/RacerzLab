import { AlertTriangle, Gauge, Layers, MapPin } from "lucide-react";
import { useCallback } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { TelemetryEvent } from "../types/telemetry";

type EvidenceCardProps = {
  event: TelemetryEvent;
};

export function EvidenceCard({ event }: EvidenceCardProps) {
  const confidence = `${Math.round(event.confidence_score * 100)}%`;
  const { selectEvent, setWorkspace } = useTelemetrySelection();

  const handleOpenPlatform = useCallback(() => {
    selectEvent(event.event_id, "priority_stack");
    setWorkspace("platform_trace", "priority_stack");
  }, [event.event_id, selectEvent, setWorkspace]);

  const handleOpenMap = useCallback(() => {
    selectEvent(event.event_id, "priority_stack");
    setWorkspace("map", "priority_stack");
  }, [event.event_id, selectEvent, setWorkspace]);

  return (
    <article className="evidence-card" style={{ cursor: "pointer" }} onClick={handleOpenPlatform} title="Open in Platform Trace">
      <header>
        <span className={`severity severity-${event.severity}`}>{event.severity}</span>
        <strong>{event.event_subtype ?? event.event_type.replace(/_/g, " ")}</strong>
        {event.lap_pct_start != null && event.lap_pct_end != null && (
          <span className="muted" style={{ fontSize: 10, marginLeft: 6 }}>
            {event.lap_pct_start.toFixed(1)}–{event.lap_pct_end.toFixed(1)}%
          </span>
        )}
      </header>
      <div className="evidence-grid">
        <span><MapPin size={15} /> {event.zone_name ?? "Unknown zone"}</span>
        <span><Gauge size={15} /> {event.primary_metric_name}: {event.primary_metric_value != null ? event.primary_metric_value : "n/a"}</span>
        <span><AlertTriangle size={15} /> {confidence}</span>
        {event.distance_m_peak != null && (
          <span>{(event.distance_m_peak * 3.28084).toFixed(0)} ft</span>
        )}
      </div>
      <p>{event.recommended_actions[0] ?? "No action attached yet."}</p>
      <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleOpenPlatform(); }} title="Open Platform">
          <Layers size={10} />
        </button>
        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleOpenMap(); }} title="Open Map">
          <MapPin size={10} />
        </button>
      </div>
    </article>
  );
}
