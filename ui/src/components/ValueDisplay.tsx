/**
 * ValueDisplay — safe primitive for rendering telemetry values.
 *
 * Rules:
 * - null/undefined/NaN/Infinity → "—" with optional reason tooltip
 * - zero displays as 0, not unavailable
 * - string labels display safely
 * - numeric values use formatter/precision/unit
 * - no Math.abs(null), Number(null), or NaN rendering bugs
 */

import { isMissingValue } from "../utils/channelMeta";

type ValueDisplayProps = {
  value: number | string | null | undefined;
  /** Optional unit suffix (e.g. "mph", "mm", "°") */
  unit?: string;
  /** Decimal places for numeric values. Default 2. */
  precision?: number;
  /** Fallback label when value is missing. Default "—" */
  fallback?: string;
  /** Reason shown in tooltip when unavailable */
  missingReason?: string;
  /** Optional formatter override */
  formatter?: (v: number) => string;
  /** CSS class name */
  className?: string;
  /** Inline style */
  style?: React.CSSProperties;
};

function isBadNumber(v: unknown): boolean {
  if (typeof v !== "number") return false;
  return Number.isNaN(v) || !Number.isFinite(v);
}

export function ValueDisplay({
  value, unit, precision = 2, fallback = "—",
  missingReason, formatter, className, style,
}: ValueDisplayProps) {
  // Missing check
  if (value == null || value === "" || isBadNumber(value) || isMissingValue(value)) {
    const tip = missingReason ? `Unavailable — ${missingReason}` : "Unavailable";
    return (
      <span className={`value-display value-display-missing${className ? ` ${className}` : ""}`}
        title={tip} style={style}>
        {fallback}
      </span>
    );
  }

  // String values
  if (typeof value === "string") {
    return (
      <span className={`value-display${className ? ` ${className}` : ""}`} style={style}>
        {value}
      </span>
    );
  }

  // Numeric values
  const display = formatter ? formatter(value) : formatNumeric(value, unit, precision);
  return (
    <span className={`value-display${className ? ` ${className}` : ""}`} style={style}>
      {display}
    </span>
  );
}

/** Pure numeric formatting — no side effects, no null checks needed. */
export function formatNumeric(value: number, unit?: string, precision = 2): string {
  switch (unit) {
    case "%":
    case "pct":
      return `${value.toFixed(1)}%`;
    case "mph":
      return `${value.toFixed(1)} mph`;
    case "ft":
      return `${value.toFixed(0)} ft`;
    case "in":
      return `${value.toFixed(precision)} in`;
    case "mm":
      return `${value.toFixed(1)} mm`;
    case "deg":
    case "°":
      return `${value.toFixed(1)}°`;
    case "rad":
      return `${value.toFixed(3)} rad`;
    case "N":
      return formatForceValue(value);
    case "psf":
      return `${value.toFixed(1)} psf`;
    case "Pa":
      return `${value.toFixed(0)} Pa`;
    case "C":
    case "°C":
      return `${value.toFixed(1)}°C`;
    case "m/s^2":
    case "m/s²":
      return `${value.toFixed(2)} m/s²`;
    case "g":
      return `${value.toFixed(2)} g`;
    case "rpm":
      return `${value.toFixed(0)} rpm`;
    case "mph/s":
      return `${value.toFixed(2)} mph/s`;
    case "in/s":
      return `${value.toFixed(2)} in/s`;
    case "m/s":
      return `${value.toFixed(2)} m/s`;
    case "psi":
      return `${value.toFixed(2)} psi`;
    case "index":
    case "score":
    case "proxy":
      return value.toFixed(precision);
    case "kN":
      return `${value.toFixed(1)} kN`;
    default:
      return `${value.toFixed(precision)}${unit ? ` ${unit}` : ""}`;
  }
}

function formatForceValue(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1000) {
    return `${(value / 1000).toFixed(1)} kN`;
  }
  return `${value.toFixed(0)} N`;
}

/** Risk score → human label */
export function formatRiskLabel(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || !Number.isFinite(value)) return "Unavailable";
  if (value >= 1.0) return "Scrape";
  if (value >= 0.92) return "Critical";
  if (value >= 0.72) return "High";
  if (value >= 0.38) return "Watch";
  return "Safe";
}
