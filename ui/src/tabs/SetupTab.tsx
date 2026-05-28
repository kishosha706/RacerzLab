import { AlertTriangle, Focus } from "lucide-react";
import { useMemo } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { RunOverview } from "../types/telemetry";

type SetupTabProps = {
  overview: RunOverview;
};

/** Map event types to related setup keys when backend doesn't provide them. */
function inferSetupKeys(eventType: string): string[] {
  const map: Record<string, string[]> = {
    PLATFORM_LOW: ["lf_ride_height_mm", "rf_ride_height_mm", "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm"],
    PLATFORM_SCRAPE: ["lf_ride_height_mm", "rf_ride_height_mm", "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm"],
    REAR_PLATFORM_LOW: ["lr_ride_height_mm", "rr_ride_height_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm"],
    REAR_PLATFORM_SCRAPE: ["lr_ride_height_mm", "rr_ride_height_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm"],
    REAR_CONTACT_RISK: ["lr_ride_height_mm", "rr_ride_height_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm"],
    WHOLE_CAR_BOTTOMING_RISK: ["lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"],
    STEERING_SCRUB: ["steering_ratio", "steering_offset_deg"],
    TIRE_SCRUB: ["lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm"],
    RPM_FLATTENING: ["rear_end_ratio"],
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

  return (
    <section className="workspace-section setup-grid">
      <h2>Setup</h2>

      {/* Setup Focus Mode */}
      {hasFocus && (
        <div className="setup-focus-banner">
          <Focus size={14} />
          <span>Setup Focus Mode — fields related to the selected event are highlighted.</span>
        </div>
      )}
      {selection.selectedEventId && !hasFocus && (
        <div className="setup-focus-banner setup-focus-empty">
          <AlertTriangle size={14} />
          <span>No setup linkage available for this event.</span>
        </div>
      )}

      <dl>
        <div className={hasFocus && isRelated("tape_percent", relatedSetupKeys) ? "setup-field-highlighted" : hasFocus ? "setup-field-dimmed" : ""}>
          <dt>Tape</dt>
          <dd>{setup?.tape_percent ?? "n/a"}%</dd>
          {isRelated("tape_percent", relatedSetupKeys) && <span className="setup-related-tag">Related</span>}
        </div>
        <div className={hasFocus && isRelated("rear_end_ratio", relatedSetupKeys) ? "setup-field-highlighted" : hasFocus ? "setup-field-dimmed" : ""}>
          <dt>Rear gear</dt>
          <dd>{setup?.rear_end_ratio ?? "n/a"}</dd>
          {isRelated("rear_end_ratio", relatedSetupKeys) && <span className="setup-related-tag">Related</span>}
        </div>
        <div className={hasFocus && (isRelated("lf_ride_height_mm", relatedSetupKeys) || isRelated("rf_ride_height_mm", relatedSetupKeys)) ? "setup-field-highlighted" : hasFocus ? "setup-field-dimmed" : ""}>
          <dt>Front ride heights</dt>
          <dd>LF {setup?.lf_ride_height_mm ?? "n/a"} / RF {setup?.rf_ride_height_mm ?? "n/a"} mm</dd>
          {(isRelated("lf_ride_height_mm", relatedSetupKeys) || isRelated("rf_ride_height_mm", relatedSetupKeys)) && <span className="setup-related-tag">Related</span>}
        </div>
        <div className={hasFocus && (isRelated("lr_ride_height_mm", relatedSetupKeys) || isRelated("rr_ride_height_mm", relatedSetupKeys)) ? "setup-field-highlighted" : hasFocus ? "setup-field-dimmed" : ""}>
          <dt>Rear ride heights</dt>
          <dd>LR {setup?.lr_ride_height_mm ?? "n/a"} / RR {setup?.rr_ride_height_mm ?? "n/a"} mm</dd>
          {(isRelated("lr_ride_height_mm", relatedSetupKeys) || isRelated("rr_ride_height_mm", relatedSetupKeys)) && <span className="setup-related-tag">Related</span>}
        </div>
        <div className={hasFocus && (isRelated("lf_front_spring_n_per_mm", relatedSetupKeys) || isRelated("rf_front_spring_n_per_mm", relatedSetupKeys) || isRelated("lr_rear_spring_n_per_mm", relatedSetupKeys) || isRelated("rr_rear_spring_n_per_mm", relatedSetupKeys)) ? "setup-field-highlighted" : hasFocus ? "setup-field-dimmed" : ""}>
          <dt>Springs</dt>
          <dd>LF {setup?.lf_front_spring_n_per_mm ?? "n/a"} / RF {setup?.rf_front_spring_n_per_mm ?? "n/a"} / LR {setup?.lr_rear_spring_n_per_mm ?? "n/a"} / RR {setup?.rr_rear_spring_n_per_mm ?? "n/a"}</dd>
          {(isRelated("lf_front_spring_n_per_mm", relatedSetupKeys) || isRelated("rf_front_spring_n_per_mm", relatedSetupKeys) || isRelated("lr_rear_spring_n_per_mm", relatedSetupKeys) || isRelated("rr_rear_spring_n_per_mm", relatedSetupKeys)) && <span className="setup-related-tag">Related</span>}
        </div>
        <div className={hasFocus && (isRelated("steering_ratio", relatedSetupKeys) || isRelated("steering_offset_deg", relatedSetupKeys)) ? "setup-field-highlighted" : hasFocus ? "setup-field-dimmed" : ""}>
          <dt>Steering</dt>
          <dd>{setup?.steering_ratio ?? "n/a"} / {setup?.steering_offset_deg ?? "n/a"} deg</dd>
          {(isRelated("steering_ratio", relatedSetupKeys) || isRelated("steering_offset_deg", relatedSetupKeys)) && <span className="setup-related-tag">Related</span>}
        </div>
      </dl>
    </section>
  );
}
