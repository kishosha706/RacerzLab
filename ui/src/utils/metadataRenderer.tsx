/**
 * Safe metadata renderer for PlatformEvent.metadata and TelemetryEvent.evidence_json.
 *
 * Rules:
 * - Only whitelist primitive values (string, number, boolean)
 * - Hide raw debug fields (internal IDs, raw lap_pct, raw coordinates)
 * - Humanize keys (snake_case → Title Case)
 * - Use ValueDisplay for numeric values
 * - Format units when known
 * - Collapse under "More Evidence" or "Metadata"
 * - Avoid raw lap_pct in normal UI
 */

import { ValueDisplay } from "../components/ValueDisplay";

/** Keys that should never be shown in normal UI. */
const DEBUG_KEYS = new Set([
  "raw_lap_pct", "debug_lap_pct", "internal_id",
  "raw_sample_index", "raw_track_x", "raw_track_y",
]);

/** Keys that are always useful to show. */
const USEFUL_KEYS = new Set([
  "platform_balance_label",
  "platform_balance_explanation",
  "front_platform_risk_score",
  "rear_platform_risk_score",
  "whole_car_bottoming_risk",
  "rear_scrape_side_label",
  "confidence",
  "source_id",
  "source_type",
  "related_channels",
  "channel",
  "primary_metric_name",
  "primary_metric_value",
  "zone_name",
  "event_subtype",
  "valid_for_tuning",
]);

/** Known unit suffixes for metadata values. */
const KNOWN_UNITS: Record<string, string> = {
  front_platform_risk_score: "score",
  rear_platform_risk_score: "score",
  whole_car_bottoming_risk: "score",
  primary_metric_value: "",
};

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function isPrimitive(v: unknown): boolean {
  return typeof v === "string" || typeof v === "number" || typeof v === "boolean";
}

function isUsefulKey(key: string): boolean {
  if (USEFUL_KEYS.has(key)) return true;
  if (key.startsWith("related_") || key.startsWith("primary_")) return true;
  return false;
}

interface MetadataRendererProps {
  metadata: Record<string, unknown>;
  /** If true, show all non-debug fields. Default false (show only useful keys). */
  showAll?: boolean;
  /** Max items to show before collapsing. Default 5. */
  maxItems?: number;
  /** Learning mode shows more detail. */
  isLearning?: boolean;
}

export function MetadataRenderer({
  metadata,
  showAll = false,
  maxItems = 5,
  isLearning = false,
}: MetadataRendererProps) {
  const entries = Object.entries(metadata).filter(([key, value]) => {
    if (DEBUG_KEYS.has(key)) return false;
    if (!isPrimitive(value)) return false;
    if (!showAll && !isUsefulKey(key) && !isLearning) return false;
    return true;
  });

  if (entries.length === 0) return null;

  const visible = entries.slice(0, maxItems);
  const remaining = entries.length - maxItems;

  return (
    <div className="metadata-renderer" style={{ fontSize: 11 }}>
      {visible.map(([key, value]) => (
        <div key={key} className="inspector-block" style={{ marginBottom: 2 }}>
          <label>{humanizeKey(key)}</label>
          {typeof value === "number" ? (
            <ValueDisplay
              value={value}
              unit={KNOWN_UNITS[key] ?? ""}
              precision={KNOWN_UNITS[key] === "score" ? 2 : 1}
            />
          ) : (
            <span>{String(value)}</span>
          )}
        </div>
      ))}
      {remaining > 0 && (
        <p className="muted" style={{ fontSize: 10, marginTop: 4 }}>
          +{remaining} more field{remaining > 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
