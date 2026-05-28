/** Channel formatting and trace value helpers. */
import type { TraceResponse, TraceChannelPayload } from "../types/telemetry";

export function getTracePayload(
  trace: TraceResponse | null,
  channel: string,
): TraceChannelPayload | null {
  if (!trace) return null;
  const raw = trace.channels[channel];
  if (!raw) return null;
  return Array.isArray(raw) ? { values: raw } : raw;
}

export function getTraceValues(
  trace: TraceResponse | null,
  channel: string,
): Array<number | string | null> {
  return getTracePayload(trace, channel)?.values ?? [];
}

export function getLatestTraceValue(
  trace: TraceResponse | null,
  channel: string,
): number | string | null {
  const vals = getTraceValues(trace, channel);
  return vals.length > 0 ? vals[vals.length - 1] : null;
}

export function hasChannel(trace: TraceResponse | null, channel: string): boolean {
  if (!trace) return false;
  const raw = trace.channels[channel];
  if (!raw) return false;
  const vals = Array.isArray(raw) ? raw : raw.values;
  return vals.some((v) => v != null);
}

export function safeStringValue(value: unknown): string {
  if (value == null || value === "") return "Unavailable";
  return String(value);
}

export function formatChannelValue(
  value: number | string | null | undefined,
  unit?: string,
  digits = 2,
): string {
  if (value == null || (typeof value === "number" && Number.isNaN(value))) return "Unavailable";
  if (typeof value === "string") return value;
  if (unit === "%" || unit === "pct") return `${value.toFixed(1)}%`;
  if (unit === "mph") return `${value.toFixed(1)} mph`;
  if (unit === "ft") return `${value.toFixed(0)} ft`;
  if (unit === "in") return `${value.toFixed(digits)} in`;
  if (unit === "mm") return `${value.toFixed(1)} mm`;
  if (unit === "deg" || unit === "°") return `${value.toFixed(1)}°`;
  if (unit === "rad") return `${value.toFixed(3)} rad`;
  if (unit === "N") return `${value.toFixed(0)} N`;
  if (unit === "psf") return `${value.toFixed(1)} psf`;
  if (unit === "Pa") return `${value.toFixed(0)} Pa`;
  if (unit === "C") return `${value.toFixed(1)}°C`;
  if (unit === "m/s^2") return `${value.toFixed(2)} m/s²`;
  if (unit === "g") return `${value.toFixed(2)} g`;
  if (unit === "rpm") return `${value.toFixed(0)} rpm`;
  if (unit === "mph/s") return `${value.toFixed(2)} mph/s`;
  if (unit === "in/s") return `${value.toFixed(2)} in/s`;
  if (unit === "m/s") return `${value.toFixed(2)} m/s`;
  if (unit === "psi") return `${value.toFixed(2)} psi`;
  if (unit === "index" || unit === "score" || unit === "proxy") return value.toFixed(3);
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

export function formatRiskScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "Unavailable";
  if (value >= 1.0) return "Scrape";
  if (value >= 0.92) return "Critical";
  if (value >= 0.72) return "High";
  if (value >= 0.38) return "Watch";
  return "Safe";
}

export function formatForceProxyN(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "Unavailable";
  const abs = Math.abs(value);
  if (abs >= 1000) return `${(value / 1000).toFixed(1)} kN`;
  return `${value.toFixed(0)} N`;
}

export function formatDegrees(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "Unavailable";
  return `${value.toFixed(1)}°`;
}

export function formatInches(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "Unavailable";
  return `${value.toFixed(2)} in`;
}

export function formatMm(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "Unavailable";
  return `${value.toFixed(1)} mm`;
}

export function formatMph(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "Unavailable";
  return `${value.toFixed(1)} mph`;
}

/**
 * Format a lap percentage for user-facing display.
 * Replaces raw "X%" with a friendlier label.
 * If sections are available, uses location name; otherwise uses "lap position".
 */
export function formatLapPct(pct: number | null | undefined, fallback = "lap position"): string {
  if (pct == null || Number.isNaN(pct)) return "—";
  // Use a descriptive range label instead of raw percentage
  if (pct < 5) return "Start/Finish";
  if (pct >= 95) return "Approaching Start/Finish";
  return `${fallback}`;
}

/**
 * Format a lap percentage range for user-facing display.
 */
export function formatLapPctRange(startPct: number | null | undefined, endPct: number | null | undefined): string {
  if (startPct == null && endPct == null) return "—";
  return "target zone";
}
