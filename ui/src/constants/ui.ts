// ── Shared UI constants for RaceLab Garage ──────────────────
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
  REAR_CONTACT_RISK: "▽",
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
  REAR_CONTACT_RISK: "Rear Platform",
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
  REAR_CONTACT_RISK: "platform_trace",
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
