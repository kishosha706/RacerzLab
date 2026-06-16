import { AlertTriangle, Gauge, Layers, MapPin } from "lucide-react";
import { useCallback } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { buildWindowEvidence, buildZoneEvidence } from "../utils/evidenceFocus";
import type { TelemetryEvent } from "../types/telemetry";

type EvidenceCardProps = {
  event: TelemetryEvent;
  onToggleMapOverlay?: () => void;
};

export function EvidenceCard({ event, onToggleMapOverlay }: EvidenceCardProps) {
  const confidence = `${Math.round(event.confidence_score * 100)}%`;
  const { selection, focusEvidence } = useTelemetrySelection();

  const buildCardEvidence = useCallback(() => {
    const lapDistFt = event.distance_m_peak != null ? event.distance_m_peak * 3.280839895 : null;
    const lapPct = event.lap_pct_peak ?? event.lap_pct_start ?? event.lap_pct_end ?? null;
    const hasLocation = lapDistFt != null || lapPct != null;

    return {
      runId: event.run_id,
      lapNumber: event.lap_number ?? null,
      ...buildWindowEvidence(selection, event.lap_number),
      ...buildZoneEvidence(selection, { lapPct, preserveWithoutLapPct: true }),
      eventId: event.event_id,
      sampleIndex: null,
      lapDistFt,
      lapPct,
      selectionSource: "overview" as const,
      lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
      valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
    };
  }, [event, selection]);

  const handleOpenPlatform = useCallback(() => {
    focusEvidence(buildCardEvidence(), "platform_trace");
  }, [focusEvidence, buildCardEvidence]);

  const handleOpenMap = useCallback(() => {
    focusEvidence(buildCardEvidence());
    onToggleMapOverlay?.();
  }, [focusEvidence, buildCardEvidence, onToggleMapOverlay]);

  return (
    <article className="evidence-card" style={{ cursor: "pointer" }} onClick={handleOpenPlatform} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleOpenPlatform(); } }} role="button" tabIndex={0} title="Open in Platform Trace">
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
        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleOpenPlatform(); }} title="Open Platform" aria-label="Open Platform for this event">
          <Layers size={10} />
        </button>
        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleOpenMap(); }} title="Show map overlay" aria-label="Show map overlay for this event">
          <MapPin size={10} />
        </button>
      </div>
    </article>
  );
}
