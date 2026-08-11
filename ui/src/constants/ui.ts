// ── Shared UI constants for RacerZLab ────────────────────────
// Centralized to avoid duplication across components.

export const SEVERITY_COLOURS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  watch: "#f59e0b",
  info: "#38bdf8",
};

export const EVENT_SHAPES: Record<string, string> = {
  MIN_SPLITTER: "▼",
  WORST_SPEED_LOSS: "◆",
  WORST_DRAG_SCRUB: "■",
  HIGHEST_RAKE: "▲",
  HIGHEST_PLATFORM_COMPRESSION: "●",
  HIGHEST_SHOCK_ACTIVITY: "⬟",
  MAX_DYNAMIC_PRESSURE: "○",
  PLATFORM_LOW: "▼",
  PLATFORM_SCRAPE: "▼",
  REAR_PLATFORM_LOW: "▽",
  REAR_PLATFORM_SCRAPE: "▽",
  WHOLE_CAR_BOTTOMING_RISK: "⬟",
  DYNAMIC_PRESSURE_PEAK: "○",
  STEERING_SCRUB: "■",
  SHOCK_ACTIVITY: "⬟",
  TIRE_SCRUB: "◆",
  RPM_FLATTENING: "▲",
  HIGH_CENTER_RAKE: "▲",
  PLATFORM_COMPRESSION: "●",
};

export const CATEGORY_LABELS: Record<string, string> = {
  MIN_SPLITTER: "Platform Risk",
  WORST_SPEED_LOSS: "Speed Loss",
  WORST_DRAG_SCRUB: "Drag / Scrub",
  HIGHEST_RAKE: "Platform",
  HIGHEST_PLATFORM_COMPRESSION: "Platform Risk",
  HIGHEST_SHOCK_ACTIVITY: "Shock / Stability",
  MAX_DYNAMIC_PRESSURE: "Aero Context",
  PLATFORM_LOW: "Platform Risk",
  PLATFORM_SCRAPE: "Platform Risk",
  REAR_PLATFORM_LOW: "Rear Platform",
  REAR_PLATFORM_SCRAPE: "Rear Platform",
  WHOLE_CAR_BOTTOMING_RISK: "Whole-Car",
  DYNAMIC_PRESSURE_PEAK: "Aero Context",
  STEERING_SCRUB: "Drag / Scrub",
  SHOCK_ACTIVITY: "Shock / Stability",
  TIRE_SCRUB: "Tires",
  RPM_FLATTENING: "Speed / Pull",
  HIGH_CENTER_RAKE: "Platform",
  PLATFORM_COMPRESSION: "Platform Risk",
};

export const CATEGORY_ORDER: Record<string, number> = {
  "Platform Risk": 1,
  "Speed Loss": 2,
  "Drag / Scrub": 3,
  Platform: 4,
  "Shock / Stability": 5,
  "Aero Context": 6,
};

export const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  watch: 2,
  info: 3,
};

/** Map event type to the workspace tab that should open when clicked. */
export const EVENT_WORKSPACE_MAP: Record<string, string> = {
  MIN_SPLITTER: "platform_trace",
  WORST_SPEED_LOSS: "speed_delta",
  WORST_DRAG_SCRUB: "drag_scrub",
  HIGHEST_RAKE: "platform_trace",
  HIGHEST_PLATFORM_COMPRESSION: "platform_trace",
  HIGHEST_SHOCK_ACTIVITY: "platform_trace",
  MAX_DYNAMIC_PRESSURE: "platform_trace",
  PLATFORM_LOW: "platform_trace",
  PLATFORM_SCRAPE: "platform_trace",
  REAR_PLATFORM_LOW: "platform_trace",
  REAR_PLATFORM_SCRAPE: "platform_trace",
  WHOLE_CAR_BOTTOMING_RISK: "platform_trace",
  DYNAMIC_PRESSURE_PEAK: "platform_trace",
  STEERING_SCRUB: "platform_trace",
  SHOCK_ACTIVITY: "platform_trace",
  TIRE_SCRUB: "platform_trace",
  RPM_FLATTENING: "platform_trace",
  HIGH_CENTER_RAKE: "platform_trace",
  PLATFORM_COMPRESSION: "platform_trace",
};

export function eventWorkspace(eventType: string): string {
  return EVENT_WORKSPACE_MAP[eventType] ?? "platform_trace";
}

export function eventLabel(eventType: string): string {
  const map: Record<string, string> = {
    MIN_SPLITTER: "Platform Trace",
    WORST_SPEED_LOSS: "Speed Delta",
    WORST_DRAG_SCRUB: "Drag/Scrub",
    HIGHEST_RAKE: "Platform Trace",
    HIGHEST_PLATFORM_COMPRESSION: "Platform Trace",
    HIGHEST_SHOCK_ACTIVITY: "Platform Trace",
    MAX_DYNAMIC_PRESSURE: "Platform Trace",
  };
  return map[eventType] ?? "Platform Trace";
}

/** Channels tagged as proxies/estimates — shown with dashed lines and "(proxy)" badge. */
export const PROXY_CHANNELS = new Set([
  "drag_scrub_suspicion",
  "full_throttle_resistance_index",
  "driven_wheel_slip_proxy",
  "aero_balance_front_pct",
  "platform_compression_index",
  "platform_risk_score",
  "cfs_risk_score",
  "front_platform_risk_score",
  "rear_platform_risk_score",
  "whole_car_bottoming_risk",
  "rear_scrape_risk_score",
  "rear_platform_contact_risk",
  "platform_stability_score",
  "rake_stability_score",
  "front_scrub_proxy",
  "rear_scrub_proxy",
  "yaw_error_proxy",
  "ackermann_scrub_proxy",
  "lf_slip_ratio_proxy", "rf_slip_ratio_proxy",
  "lr_slip_ratio_proxy", "rr_slip_ratio_proxy",
  "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
  "front_load_proxy_n", "rear_load_proxy_n",
  "front_aero_proxy_n", "rear_aero_proxy_n",
  "rear_downforce_proxy_n", "rear_platform_proxy_n", "rear_diffuser_proxy_n",
  "aero_load_index", "aero_load_index_180mph",
  "dynamic_pressure_lap_index", "dynamic_pressure_index",
  "grade_force_proxy_n",
  "grade_corrected_speed_loss_mph_s",
  "lf_damper_energy_proxy", "rf_damper_energy_proxy",
  "lr_damper_energy_proxy", "rr_damper_energy_proxy",
  "damper_energy_proxy", "damper_work_proxy",
  "lf_camber_temp_bias_c", "rf_camber_temp_bias_c",
  "lr_camber_temp_bias_c", "rr_camber_temp_bias_c",
  "lf_camber_bias_label", "rf_camber_bias_label",
  "lr_camber_bias_label", "rr_camber_bias_label",
  "lf_pressure_gain", "rf_pressure_gain",
  "lr_pressure_gain", "rr_pressure_gain",
  "lf_temp_spread", "rf_temp_spread",
  "lr_temp_spread", "rr_temp_spread",
  "lf_wear_spread", "rf_wear_spread",
  "lr_wear_spread", "rr_wear_spread",
  "dynamic_grade_rad", "dynamic_grade_deg",
  "grade_context_label",
  "grade_corrected_long_accel_mps2",
  "ackermann_steering_expected_deg",
  "ackermann_steering_error_deg",
  "front_platform_roll_deg_from_rh",
  "rear_platform_roll_deg_from_rh",
  "platform_roll_balance_deg",
]);

// ── Human-readable labels ────────────────────────────────────

/** Map internal event type to a human-readable label. */
export function humanizeEventLabel(eventType: string): string {
  const map: Record<string, string> = {
    MIN_SPLITTER: "Minimum Splitter",
    PLATFORM_LOW: "Front Platform Low",
    PLATFORM_SCRAPE: "Front Platform Scrape",
    REAR_PLATFORM_LOW: "Rear Platform Low",
    REAR_PLATFORM_SCRAPE: "Rear Platform Scrape",
    WHOLE_CAR_BOTTOMING_RISK: "Whole-Car Bottoming Risk",
    FULL_THROTTLE_SPEED_LOSS: "Full-Throttle Speed Loss",
    STEERING_SCRUB: "Steering Scrub",
    DYNAMIC_PRESSURE_PEAK: "Dynamic Pressure Peak",
    MAX_DYNAMIC_PRESSURE: "Max Dynamic Pressure",
    SHOCK_ACTIVITY: "Shock Activity",
    TIRE_SCRUB: "Tire Scrub",
    RPM_FLATTENING: "RPM Flattening",
    HIGH_CENTER_RAKE: "High Center Rake",
    PLATFORM_COMPRESSION: "Platform Compression",
    WORST_SPEED_LOSS: "Worst Speed Loss",
    WORST_DRAG_SCRUB: "Worst Drag/Scrub",
    HIGHEST_RAKE: "Highest Rake",
    HIGHEST_PLATFORM_COMPRESSION: "Highest Platform Compression",
    HIGHEST_SHOCK_ACTIVITY: "Highest Shock Activity",
    MIN_REAR_RIDE_HEIGHT: "Min Rear Ride Height",
  };
  return map[eventType] ?? eventType.replace(/_/g, " ");
}

/** Map internal workspace key to a human-readable label. */
export function humanizeWorkspaceLabel(ws: string): string {
  const map: Record<string, string> = {
    overview: "Overview",
    engineer: "Smart Engineer",
    map: "Track Map",
    platform_trace: "Platform Trace",
    speed_delta: "Speed Delta",
    drag_scrub: "Drag/Scrub",
    setup_impact: "Setup Impact",
    compare: "Compare",
    notebook: "Notes",
    channels: "Raw Channels",
    laps: "Laps",
    dial_in: "Dial-In",
    setup: "Setup",
  };
  return map[ws] ?? ws.replace(/_/g, " ");
}

/** Map classification tag to a compact display label. */
export function humanizeClassificationTag(tag: string): string {
  const map: Record<string, string> = {
    ELIGIBLE_FLYING_LAP: "Eligible",
    SOLO_CLEAN: "Eligible",
    OUT_LAP: "Out Lap",
    COOLDOWN: "Cooldown",
    PIT_ROAD: "Pit Road",
    WRECK_OR_SPIN: "Wreck/Spin",
    INVALID_SPEED_EVENT: "Invalid",
    INVALID_FOR_PLATFORM_TUNING: "Invalid",
    SHORT_RUN: "Short Run",
    LONG_RUN: "Long Run",
    NO_SETUP_CONCLUSION: "No Setup",
    PARTIAL: "Partial",
  };
  return map[tag] ?? tag.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

/** Classify a lap by its tags for display. Returns { label, color, tone }. */
export function classifyLapTags(tags: string[]): { label: string; color: string } | null {
  const invalidTags = new Set([
    "PARTIAL", "SHORT_RUN", "OUT_LAP", "COOLDOWN", "PIT_ROAD", "OFF_TRACK",
    "WRECK_OR_SPIN", "INVALID_SPEED_EVENT", "CAUTION", "YELLOW", "RESET",
    "ACTIVE_RESET", "SAMPLE_DISCONTINUITY", "POSITION_DISCONTINUITY",
    "INVALID_FOR_PLATFORM_TUNING", "NO_SETUP_CONCLUSION",
  ]);
  if (tags.includes("OUT_LAP")) return { label: "Out", color: "#8d9aaa" };
  if (tags.includes("COOLDOWN")) return { label: "Cool", color: "#8d9aaa" };
  if (tags.includes("PIT_ROAD")) return { label: "Pit", color: "#8d9aaa" };
  if (tags.includes("SHORT_RUN")) return { label: "Short", color: "#8d9aaa" };
  if (tags.includes("PARTIAL")) return { label: "Partial", color: "#f59e0b" };
  if (tags.includes("NO_SETUP_CONCLUSION")) return { label: "No Setup", color: "#8d9aaa" };
  if (tags.some(tag => invalidTags.has(tag) || tag.startsWith("INVALID"))) {
    return { label: "Invalid", color: "#ef4444" };
  }
  if (tags.includes("ELIGIBLE_FLYING_LAP") || tags.includes("SOLO_CLEAN")) {
    return { label: "Eligible", color: "#22c55e" };
  }
  if (tags.includes("LONG_RUN")) return { label: "Long", color: "#38bdf8" };
  return null;
}

/** Return the display label for a mode value. */
export function humanizeModeLabel(mode: string): string {
  if (mode === "learning") return "Learning Mode";
  return "Race Mode";
}
