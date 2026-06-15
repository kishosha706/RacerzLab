import type { TelemetryEvent, PlatformEventItem, PlatformEventVisibilityMode } from "../types/telemetry";
import { filterPlatformEvents, isMutedPlatformEvent } from "./platformEventVisibility";

export type PlatformChartAnnotation = {
  distFt: number;
  label: string;
  severity: string;
  muted: boolean;
  source: "platform" | "legacy";
};

export type PlatformChartAnnotationModel = {
  annotations: PlatformChartAnnotation[];
  markLines: Array<{ xAxis: number; name: string; lineStyle?: { opacity?: number } }>;
  markAreas: Array<{ xAxis: number; color: string; opacity: number }>;
  showLineLabels: boolean;
};

function legacyEventDistanceFt(event: TelemetryEvent): number | null {
  return event.distance_m_peak == null ? null : event.distance_m_peak * 3.280839895;
}

export function platformEventAnnotationColor(severity: string): string {
  return severity === "critical"
    ? "#ef4444"
    : severity === "high"
      ? "#f97316"
      : severity === "watch"
        ? "#f59e0b"
        : "#38bdf8";
}

export function buildPlatformChartAnnotations({
  platformEvents,
  legacyEvents,
  mode,
}: {
  platformEvents: PlatformEventItem[];
  legacyEvents: TelemetryEvent[];
  mode: PlatformEventVisibilityMode;
}): PlatformChartAnnotationModel {
  const visiblePlatformEvents = filterPlatformEvents(platformEvents, mode);
  const structuredAnnotations = visiblePlatformEvents
    .filter((event) => event.lap_dist_ft != null)
    .map((event) => ({
      distFt: event.lap_dist_ft!,
      label: event.title,
      severity: event.severity,
      muted: isMutedPlatformEvent(event, mode),
      source: "platform" as const,
    }));

  const legacyAnnotations: PlatformChartAnnotation[] = platformEvents.length > 0
    ? []
    : legacyEvents
      .reduce<PlatformChartAnnotation[]>((annotations, event) => {
        const distFt = legacyEventDistanceFt(event);
        if (distFt != null) {
          annotations.push({
            distFt,
            label: event.event_subtype ?? event.event_type,
            severity: event.severity,
            muted: false,
            source: "legacy" as const,
          });
        }
        return annotations;
      }, []);

  const annotations = [...structuredAnnotations, ...legacyAnnotations];

  return {
    annotations,
    showLineLabels: false,
    markLines: annotations.map((event) => ({
      xAxis: event.distFt,
      name: event.label,
      lineStyle: { opacity: event.muted ? 0.42 : 1 },
    })),
    markAreas: annotations.map((event) => ({
      xAxis: event.distFt - 25,
      color: platformEventAnnotationColor(event.severity),
      opacity: event.muted ? 0.04 : 0.08,
    })),
  };
}
