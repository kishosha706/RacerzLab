import { Crosshair, Layers, MapPin } from "lucide-react";
import { useMemo, useState } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket } from "../store/CompareBasketContext";
import type { RunOverview } from "../types/telemetry";

type SetupTabProps = {
  overview: RunOverview;
};

/** Map event types to related setup keys when backend doesn't provide them. */
function inferSetupKeys(eventType: string): string[] {
  const map: Record<string, string[]> = {
    PLATFORM_LOW: ["lf_ride_height_mm", "rf_ride_height_mm", "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm", "nose_weight_pct", "cross_weight_pct"],
    PLATFORM_SCRAPE: ["lf_ride_height_mm", "rf_ride_height_mm", "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm", "lf_packer_mm", "rf_packer_mm", "nose_weight_pct"],
    REAR_PLATFORM_LOW: ["lr_ride_height_mm", "rr_ride_height_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm", "rear_arb_rating", "cross_weight_pct"],
    REAR_PLATFORM_SCRAPE: ["lr_ride_height_mm", "rr_ride_height_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm", "lr_packer_mm", "rr_packer_mm", "cross_weight_pct"],
    REAR_CONTACT_RISK: ["lr_ride_height_mm", "rr_ride_height_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm"],
    WHOLE_CAR_BOTTOMING_RISK: ["lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm", "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm", "nose_weight_pct", "cross_weight_pct"],
    STEERING_SCRUB: ["steering_ratio", "steering_offset_deg", "front_arb_rating", "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm", "cross_weight_pct"],
    TIRE_SCRUB: ["lf_pressure_kpa", "rf_pressure_kpa", "lr_pressure_kpa", "rr_pressure_kpa"],
    FULL_THROTTLE_SPEED_LOSS: ["rear_end_ratio", "tape_percent", "lf_ride_height_mm", "rf_ride_height_mm"],
    RPM_FLATTENING: ["rear_end_ratio", "tape_percent"],
    DRAG_SCRUB_SUSPICION: ["lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm", "rear_end_ratio"],
    DYNAMIC_PRESSURE_PEAK: ["tape_percent", "lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"],
    SHOCK_ACTIVITY: ["lf_rebound_per_click", "rf_rebound_per_click", "lr_rebound_per_click", "rr_rebound_per_click", "lf_compression_per_click", "rf_compression_per_click", "lr_compression_per_click", "rr_compression_per_click"],
    HIGH_CENTER_RAKE: ["lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"],
    PLATFORM_COMPRESSION: ["lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm", "nose_weight_pct", "cross_weight_pct"],
    MAX_DYNAMIC_PRESSURE: ["tape_percent", "lf_ride_height_mm", "rf_ride_height_mm"],
  };
  return map[eventType] ?? [];
}

// ── Setup field groups ──────────────────────────────────────
type SetupField = {
  key: string;
  label: string;
  group: string;
  getValue: (s: NonNullable<RunOverview["setup_snapshot"]>) => string;
};

const SETUP_FIELDS: SetupField[] = [
  // Aero / Body
  { key: "tape_percent", label: "Tape", group: "Aero / Body", getValue: (s) => s.tape_percent != null ? `${s.tape_percent}%` : "n/a" },
  // Gearing / Pull
  { key: "rear_end_ratio", label: "Rear gear", group: "Gearing / Pull", getValue: (s) => s.rear_end_ratio != null ? String(s.rear_end_ratio) : "n/a" },
  // Front Platform
  { key: "lf_ride_height_mm", label: "Front ride heights", group: "Front Platform", getValue: (s) => `LF ${s.lf_ride_height_mm ?? "n/a"} / RF ${s.rf_ride_height_mm ?? "n/a"} mm` },
  // Rear Platform
  { key: "lr_ride_height_mm", label: "Rear ride heights", group: "Rear Platform", getValue: (s) => `LR ${s.lr_ride_height_mm ?? "n/a"} / RR ${s.rr_ride_height_mm ?? "n/a"} mm` },
  // Springs / Dampers
  { key: "lf_front_spring_n_per_mm", label: "Springs", group: "Springs / Dampers", getValue: (s) => `LF ${s.lf_front_spring_n_per_mm ?? "n/a"} / RF ${s.rf_front_spring_n_per_mm ?? "n/a"} / LR ${s.lr_rear_spring_n_per_mm ?? "n/a"} / RR ${s.rr_rear_spring_n_per_mm ?? "n/a"}` },
  // Steering / Geometry
  { key: "steering_ratio", label: "Steering", group: "Steering / Geometry", getValue: (s) => `${s.steering_ratio ?? "n/a"} / ${s.steering_offset_deg ?? "n/a"} deg` },
];

/** Check if a setup key is related to the current focus. */
function isRelated(key: string, relatedKeys: Set<string>): boolean {
  return relatedKeys.has(key);
}

export function SetupTab({ overview }: SetupTabProps) {
  const setup = overview.setup_snapshot;
  const { selection, setWorkspace } = useTelemetrySelection();

  // Resolve selected event for display
  const selectedEvent = useMemo(() => {
    if (!selection.selectedEventId) return null;
    return overview.events.find((e) => e.event_id === selection.selectedEventId) ?? null;
  }, [selection.selectedEventId, overview.events]);

  // Resolve related setup keys from selected event
  const relatedSetupKeys = useMemo(() => {
    if (!selectedEvent) return new Set<string>();
    const keys = (selectedEvent.related_setup_keys?.length ?? 0) > 0
      ? selectedEvent.related_setup_keys
      : inferSetupKeys(selectedEvent.event_type);
    return new Set(keys);
  }, [selectedEvent]);

  const hasFocus = relatedSetupKeys.size > 0;

  // Selected event name for display
  const selectedEventName = useMemo(() => {
    if (!selectedEvent) return null;
    return selectedEvent.event_subtype ?? selectedEvent.event_type.replace(/_/g, " ");
  }, [selectedEvent]);

  // Check if keys are from backend or inferred
  const isInferred = useMemo(() => {
    if (!selectedEvent) return false;
    return (selectedEvent.related_setup_keys?.length ?? 0) === 0;
  }, [selectedEvent]);

  // ── Setup Diff ───────────────────────────────────────────────
  const { basket } = useCompareBasket();
  const [diffMode, setDiffMode] = useState<"current" | "diff">("current");

  const hasBaselineSetup = diffMode === "diff"
    && basket.baseline != null
    && basket.baseline.has_setup_snapshot;

  const showDiffUnavailable = diffMode === "diff"
    && (!basket.baseline || !basket.baseline.has_setup_snapshot);

  const diffUnavailableReason = basket.baseline
    ? "Setup diff unavailable — baseline setup snapshot not found."
    : "Select a baseline in Compare or Compare Basket to view setup diff.";

  // ── Group fields ─────────────────────────────────────────────
  const groupedSetupFields = useMemo(() => {
    const groups = new Map<string, SetupField[]>();
    for (const field of SETUP_FIELDS) {
      const g = groups.get(field.group) ?? [];
      g.push(field);
      groups.set(field.group, g);
    }
    // Sort groups: related group first, then alphabetically
    const related = hasFocus ? [...relatedSetupKeys] : [];
    const order = (group: string): number => {
      const groupKeys = SETUP_FIELDS.filter(f => f.group === group).map(f => f.key);
      if (related.some(k => groupKeys.includes(k))) return 0;
      return 1;
    };
    return [...groups.entries()].sort((a, b) => order(a[0]) - order(b[0]));
  }, [hasFocus, relatedSetupKeys]);

  return (
    <section className="workspace-section setup-grid">
      <h2>Setup</h2>

      {/* Selected evidence context */}
      {selectedEvent && (
        <div className="setup-focus-banner" style={{ marginBottom: 8 }}>
          <Crosshair size={14} />
          <span style={{ flex: 1 }}>Evidence: {selectedEventName}</span>
          {selection.selectedLap != null && (
            <span className="lap-flag-badge" style={{ fontSize: 9 }}>Lap {selection.selectedLap}</span>
          )}
          {selection.selectedLapDistFt != null && (
            <span className="lap-flag-badge" style={{ fontSize: 9 }}>{selection.selectedLapDistFt.toFixed(0)} ft</span>
          )}
          {selection.selectedZoneLabel && (
            <span className="lap-flag-badge" style={{ fontSize: 9 }}>{selection.selectedZoneLabel}</span>
          )}
          <span className="setup-related-tag" style={{
            position: "static",
            background: isInferred ? "rgba(245,158,11,0.15)" : "rgba(34,197,94,0.15)",
            color: isInferred ? "#f59e0b" : "#22c55e",
          }}>
            {isInferred ? "Inferred" : "Explicit"}
          </span>
          <button className="trackmap-action-btn" onClick={() => setWorkspace("platform_trace", "setup_table")} title="Open Platform">
            <Layers size={10} /> Platform
          </button>
          <button className="trackmap-action-btn" onClick={() => setWorkspace("map", "setup_table")} title="Open Map">
            <MapPin size={10} /> Map
          </button>
        </div>
      )}
      {!selectedEvent && (
        <p className="section-note" style={{ marginBottom: 8, fontSize: 11 }}>
          Select evidence in Platform, Laps, or Map to show related setup fields.
        </p>
      )}

      {/* Setup Diff Toggle */}
      <div className="setup-diff-toggle">
        <button
          className={`setup-diff-toggle-btn ${diffMode === "current" ? "active" : ""}`}
          onClick={() => setDiffMode("current")}
        >
          Current Setup
        </button>
        <button
          className={`setup-diff-toggle-btn ${diffMode === "diff" ? "active" : ""}`}
          onClick={() => setDiffMode("diff")}
        >
          Diff vs Baseline
        </button>
      </div>

      {showDiffUnavailable && (
        <p className="setup-diff-empty">{diffUnavailableReason}</p>
      )}

      {/* Setup groups */}
      {groupedSetupFields.map(([groupName, fields]) => {
        const groupRelated = fields.some(f => isRelated(f.key, relatedSetupKeys));
        return (
          <div key={groupName} className={`setup-group ${groupRelated && hasFocus ? "setup-group-related" : ""}`}>
            <h4 className="setup-group-title">{groupName}</h4>
            <dl>
              {fields.map(field => (
                <SetupFieldRow
                  key={field.key}
                  label={field.label}
                  currentValue={setup ? field.getValue(setup) : "n/a"}
                  hasFocus={hasFocus}
                  isRelated={isRelated(field.key, relatedSetupKeys)}
                  diffMode={diffMode}
                  baselineValue={hasBaselineSetup ? "—" : undefined}
                />
              ))}
            </dl>
          </div>
        );
      })}
    </section>
  );
}

/** A single setup field row that supports diff mode. */
function SetupFieldRow({
  label,
  currentValue,
  hasFocus,
  isRelated: fieldIsRelated,
  diffMode,
  baselineValue,
}: {
  label: string;
  currentValue: string;
  hasFocus: boolean;
  isRelated: boolean;
  diffMode: "current" | "diff";
  baselineValue?: string;
}) {
  const isChanged = diffMode === "diff" && baselineValue !== undefined && currentValue !== baselineValue;
  const rowClass = hasFocus
    ? fieldIsRelated ? "setup-field-highlighted" : "setup-field-dimmed"
    : "";

  return (
    <div className={`${rowClass} ${diffMode === "diff" ? (isChanged ? "setup-diff-row changed" : "setup-diff-row unchanged") : ""}`}>
      <dt>{label}</dt>
      {diffMode === "diff" && baselineValue !== undefined ? (
        <div className="setup-diff-values">
          <span className="setup-diff-baseline">{baselineValue}</span>
          <span className="setup-diff-arrow">→</span>
          <span className="setup-diff-test">{currentValue}</span>
        </div>
      ) : (
        <dd>{currentValue}</dd>
      )}
      {fieldIsRelated && <span className="setup-related-tag">Related</span>}
    </div>
  );
}
