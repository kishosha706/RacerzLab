import { AlertTriangle, Focus } from "lucide-react";
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

/** Check if a setup key is related to the current focus. */
function isRelated(key: string, relatedKeys: Set<string>): boolean {
  return relatedKeys.has(key);
}

export function SetupTab({ overview }: SetupTabProps) {
  const setup = overview.setup_snapshot;
  const { selection } = useTelemetrySelection();

  // Resolve related setup keys from selected event
  const relatedSetupKeys = useMemo(() => {
    if (!selection.selectedEventId) return new Set<string>();
    const event = overview.events.find((e) => e.event_id === selection.selectedEventId);
    if (!event) return new Set<string>();
    const keys = (event.related_setup_keys?.length ?? 0) > 0
      ? event.related_setup_keys
      : inferSetupKeys(event.event_type);
    return new Set(keys);
  }, [selection.selectedEventId, overview.events]);

  const hasFocus = relatedSetupKeys.size > 0;

  // Resolve selected event name for display
  const selectedEventName = useMemo(() => {
    if (!selection.selectedEventId) return null;
    const event = overview.events.find((e) => e.event_id === selection.selectedEventId);
    if (!event) return null;
    return event.event_subtype ?? event.event_type.replace(/_/g, " ");
  }, [selection.selectedEventId, overview.events]);

  // Check if keys are from backend or inferred
  const isInferred = useMemo(() => {
    if (!selection.selectedEventId) return false;
    const event = overview.events.find((e) => e.event_id === selection.selectedEventId);
    if (!event) return true;
    return (event.related_setup_keys?.length ?? 0) === 0;
  }, [selection.selectedEventId, overview.events]);

  // ── Setup Diff ───────────────────────────────────────────────
  const { basket } = useCompareBasket();
  const [diffMode, setDiffMode] = useState<"current" | "diff">("current");
  const hasBaselineSetup = diffMode === "diff" && basket.baseline != null;

  // Mock baseline setup data — in production this would come from the baseline run's setup_snapshot
  // For now, show the toggle but indicate when no baseline is selected
  const showDiffUnavailable = diffMode === "diff" && !basket.baseline;

  return (
    <section className="workspace-section setup-grid">
      <h2>Setup</h2>

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
        <p className="setup-diff-empty">Select a baseline in Compare or Compare Basket to view setup diff.</p>
      )}

      {/* Setup Focus Mode */}
      {hasFocus && (
        <div className="setup-focus-banner">
          <Focus size={14} />
          <span>Setup Focus Mode — {selectedEventName ? `related to "${selectedEventName}"` : "fields related to the selected event are highlighted."}</span>
          {isInferred ? (
            <span className="setup-related-tag" style={{ position: "static", background: "rgba(245,158,11,0.15)", color: "#f59e0b" }} title="Suggested from event type mapping">
              Inferred
            </span>
          ) : (
            <span className="setup-related-tag" style={{ position: "static", background: "rgba(34,197,94,0.15)", color: "#22c55e" }} title="Provided by event metadata">
              Explicit
            </span>
          )}
        </div>
      )}
      {selection.selectedEventId && !hasFocus && (
        <div className="setup-focus-banner setup-focus-empty">
          <AlertTriangle size={14} />
          <span>No setup linkage available for this event.</span>
        </div>
      )}

      <dl>
        <SetupFieldRow
          label="Tape"
          currentValue={setup?.tape_percent != null ? `${setup.tape_percent}%` : "n/a"}
          hasFocus={hasFocus}
          isRelated={isRelated("tape_percent", relatedSetupKeys)}
          diffMode={diffMode}
          baselineValue={hasBaselineSetup ? "—" : undefined}
        />
        <SetupFieldRow
          label="Rear gear"
          currentValue={setup?.rear_end_ratio != null ? String(setup.rear_end_ratio) : "n/a"}
          hasFocus={hasFocus}
          isRelated={isRelated("rear_end_ratio", relatedSetupKeys)}
          diffMode={diffMode}
          baselineValue={hasBaselineSetup ? "—" : undefined}
        />
        <SetupFieldRow
          label="Front ride heights"
          currentValue={`LF ${setup?.lf_ride_height_mm ?? "n/a"} / RF ${setup?.rf_ride_height_mm ?? "n/a"} mm`}
          hasFocus={hasFocus}
          isRelated={isRelated("lf_ride_height_mm", relatedSetupKeys) || isRelated("rf_ride_height_mm", relatedSetupKeys)}
          diffMode={diffMode}
          baselineValue={hasBaselineSetup ? "—" : undefined}
        />
        <SetupFieldRow
          label="Rear ride heights"
          currentValue={`LR ${setup?.lr_ride_height_mm ?? "n/a"} / RR ${setup?.rr_ride_height_mm ?? "n/a"} mm`}
          hasFocus={hasFocus}
          isRelated={isRelated("lr_ride_height_mm", relatedSetupKeys) || isRelated("rr_ride_height_mm", relatedSetupKeys)}
          diffMode={diffMode}
          baselineValue={hasBaselineSetup ? "—" : undefined}
        />
        <SetupFieldRow
          label="Springs"
          currentValue={`LF ${setup?.lf_front_spring_n_per_mm ?? "n/a"} / RF ${setup?.rf_front_spring_n_per_mm ?? "n/a"} / LR ${setup?.lr_rear_spring_n_per_mm ?? "n/a"} / RR ${setup?.rr_rear_spring_n_per_mm ?? "n/a"}`}
          hasFocus={hasFocus}
          isRelated={isRelated("lf_front_spring_n_per_mm", relatedSetupKeys) || isRelated("rf_front_spring_n_per_mm", relatedSetupKeys) || isRelated("lr_rear_spring_n_per_mm", relatedSetupKeys) || isRelated("rr_rear_spring_n_per_mm", relatedSetupKeys)}
          diffMode={diffMode}
          baselineValue={hasBaselineSetup ? "—" : undefined}
        />
        <SetupFieldRow
          label="Steering"
          currentValue={`${setup?.steering_ratio ?? "n/a"} / ${setup?.steering_offset_deg ?? "n/a"} deg`}
          hasFocus={hasFocus}
          isRelated={isRelated("steering_ratio", relatedSetupKeys) || isRelated("steering_offset_deg", relatedSetupKeys)}
          diffMode={diffMode}
          baselineValue={hasBaselineSetup ? "—" : undefined}
        />
      </dl>
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
