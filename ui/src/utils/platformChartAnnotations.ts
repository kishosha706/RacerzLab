import type { PlatformEventItem, PlatformEventVisibilityMode } from "../types/telemetry";
import { filterPlatformEvents, isMutedPlatformEvent } from "./platformEventVisibility";

export type PlatformChartAnnotation = {
  distFt: number;
  label: string;
  severity: string;
  muted: boolean;
  source: "platform";
};

export type PlatformChartAnnotationModel = {
  annotations: PlatformChartAnnotation[];
  markLines: Array<{ xAxis: number; name: string; lineStyle?: { opacity?: number } }>;
  markAreas: Array<{ xAxis: number; color: string; opacity: number }>;
  showLineLabels: boolean;
};

export function platformEventAnnotationColor(severity: string): string {
  return severity === "critical"
    ? "#ef4444"
    : severity === "high"
      ? "#f97316"
      : severity === "watch"
        ? "#f59e0b"
        : "#38bdf8";
}

/** Build chart markers only from the structured /platform-events contract. */
export function buildPlatformChartAnnotations({
  platformEvents,
  mode,
}: {
  platformEvents: PlatformEventItem[];
  mode: PlatformEventVisibilityMode;
}): PlatformChartAnnotationModel {
  const visiblePlatformEvents = filterPlatformEvents(platformEvents, mode);
  const annotations = visiblePlatformEvents
    .filter((event) => event.lap_dist_ft != null)
    .map((event) => ({
      distFt: event.lap_dist_ft!,
      label: event.title,
      severity: event.severity,
      muted: isMutedPlatformEvent(event, mode),
      source: "platform" as const,
    }));

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
