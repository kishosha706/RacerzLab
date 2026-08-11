import { AlertTriangle, Gauge, Layers, MapPin } from "lucide-react";
import { useCallback } from "react";
import { humanizeEventLabel } from "../constants/ui";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { getChannelLabel, getChannelPrecision, getChannelUnit } from "../utils/channelMeta";
import { buildWindowEvidence, buildZoneEvidence } from "../utils/evidenceFocus";
import { telemetryEventIsActionable } from "../utils/evidenceTrust";
import type { TelemetryEvent } from "../types/telemetry";

type EvidenceCardProps = {
  event: TelemetryEvent;
  onToggleMapOverlay?: () => void;
};

export function EvidenceCard({ event, onToggleMapOverlay }: EvidenceCardProps) {
  const confidence = Number.isFinite(event.confidence_score)
    ? `${Math.round(event.confidence_score * 100)}%`
    : "Unavailable";
  const actionable = telemetryEventIsActionable(event);
  const { selection, focusEvidence } = useTelemetrySelection();
  const rawSubtype = event.event_subtype?.trim();
  const eventLabelSource = rawSubtype && !["critical", "high", "watch", "info"].includes(rawSubtype.toLowerCase())
    ? rawSubtype
    : event.event_type;
  const eventLabel = humanizeEventLabel(eventLabelSource)
    .replace(/\b\w/g, (character) => character.toUpperCase());
  const metricName = event.primary_metric_name;
  const catalogMetricLabel = metricName ? getChannelLabel(metricName) : "Primary metric";
  const metricLabel = metricName && catalogMetricLabel === metricName
    ? metricName
      .replace(/_/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase())
      .replace(/\bMph\b/g, "MPH")
      .replace(/\bRpm\b/g, "RPM")
      .replace(/\bAbs\b/g, "ABS")
    : catalogMetricLabel;
  const metricValue = metricName && typeof event.primary_metric_value === "number" && Number.isFinite(event.primary_metric_value)
    ? `${event.primary_metric_value.toFixed(getChannelPrecision(metricName))}${getChannelUnit(metricName) ? ` ${getChannelUnit(metricName)}` : ""}`
    : event.primary_metric_value ?? "Unavailable";

  const buildCardEvidence = useCallback(() => {
    const lapDistFt = event.distance_m_peak != null ? event.distance_m_peak * 3.280839895 : null;
    const lapPct = event.lap_pct_peak ?? event.lap_pct_start ?? event.lap_pct_end ?? null;
    const hasLocation = lapDistFt != null || lapPct != null;

    return {
      runId: event.run_id,
      lapNumber: event.lap_number ?? null,
      ...buildWindowEvidence(selection, event.lap_number),
      ...buildZoneEvidence(selection, { lapPct }),
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
    <article className="evidence-card">
      <header>
        <span className={`severity severity-${event.severity}`}>{event.severity}</span>
        <strong>{eventLabel}</strong>
        {event.lap_pct_start != null && event.lap_pct_end != null && (
          <span className="muted" style={{ fontSize: 10, marginLeft: 6 }}>
            {event.lap_pct_start.toFixed(1)}–{event.lap_pct_end.toFixed(1)}%
          </span>
        )}
      </header>
      <div className="evidence-grid">
        <span><MapPin size={15} /> {event.zone_name ?? "Unknown zone"}</span>
        <span><Gauge size={15} /> {metricLabel}: {metricValue}</span>
        <span><AlertTriangle size={15} /> {confidence}</span>
        {event.distance_m_peak != null && (
          <span>{(event.distance_m_peak * 3.28084).toFixed(0)} ft</span>
        )}
      </div>
      <p>{actionable
        ? "Inspect this qualified location with the setup unchanged."
        : "Evidence only - no setup action is authorized."}</p>
      {!actionable && event.blocker_reasons[0] && <p className="muted">{event.blocker_reasons[0]}</p>}
      <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleOpenPlatform(); }} title="Open Platform" aria-label="Open Platform for this event">
          <Layers size={10} /> Open Platform
        </button>
        <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); handleOpenMap(); }} title="Show map overlay" aria-label="Show map overlay for this event">
          <MapPin size={10} /> Show on map
        </button>
      </div>
    </article>
  );
}
