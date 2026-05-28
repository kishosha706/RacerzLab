/** Centralized channel metadata helper for consistent UI display. */

export interface ChannelUiMeta {
  label: string;
  unit: string;
  isProxy: boolean;
  isEstimate: boolean;
  category: string;
  precision: number;
  warning?: string;
}

const CHANNEL_META: Record<string, ChannelUiMeta> = {
  // ── Controls ──
  throttle_pct: { label: "Throttle", unit: "%", isProxy: false, isEstimate: false, category: "controls", precision: 1 },
  brake_pct: { label: "Brake", unit: "%", isProxy: false, isEstimate: false, category: "controls", precision: 1 },
  steering_deg: { label: "Steering", unit: "°", isProxy: false, isEstimate: false, category: "controls", precision: 1 },
  abs_steering_deg: { label: "|Steering|", unit: "°", isProxy: false, isEstimate: false, category: "controls", precision: 1 },
  abs_lat_accel: { label: "|Lat Accel|", unit: "m/s²", isProxy: false, isEstimate: false, category: "controls", precision: 2 },
  lat_accel_g: { label: "Lat Accel", unit: "g", isProxy: false, isEstimate: false, category: "controls", precision: 2 },
  long_accel_g: { label: "Long Accel", unit: "g", isProxy: false, isEstimate: false, category: "controls", precision: 2 },
  vert_accel_g: { label: "Vert Accel", unit: "g", isProxy: false, isEstimate: false, category: "controls", precision: 2 },

  // ── Speed / pull ──
  speed_mph: { label: "Speed", unit: "mph", isProxy: false, isEstimate: false, category: "speed", precision: 1 },
  speed_fps: { label: "Speed", unit: "ft/s", isProxy: false, isEstimate: false, category: "speed", precision: 1 },
  speed_rate_mph_s: { label: "Speed Rate", unit: "mph/s", isProxy: false, isEstimate: false, category: "speed", precision: 2 },
  speed_rate_mph_1000ft: { label: "Speed Rate", unit: "mph/1000ft", isProxy: false, isEstimate: false, category: "speed", precision: 2 },
  speed_rate_mps2: { label: "Speed Rate", unit: "m/s²", isProxy: false, isEstimate: false, category: "speed", precision: 2 },
  rpm: { label: "RPM", unit: "rpm", isProxy: false, isEstimate: false, category: "speed", precision: 0 },
  gear: { label: "Gear", unit: "", isProxy: false, isEstimate: false, category: "speed", precision: 0 },
  lap_dist_pct_100: { label: "Position", unit: "%", isProxy: false, isEstimate: false, category: "speed", precision: 1 },

  // ── Grade ──
  dynamic_grade_rad: { label: "Grade", unit: "rad", isProxy: true, isEstimate: true, category: "grade", precision: 3,
    warning: "Estimated from acceleration vs speed derivative, not surveyed elevation." },
  dynamic_grade_deg: { label: "Grade", unit: "°", isProxy: true, isEstimate: true, category: "grade", precision: 1,
    warning: "Estimated from acceleration vs speed derivative, not surveyed elevation." },
  grade_context_label: { label: "Grade Context", unit: "", isProxy: true, isEstimate: true, category: "grade", precision: 0 },
  grade_corrected_long_accel_mps2: { label: "Grade-Corrected Long Accel", unit: "m/s²", isProxy: true, isEstimate: true, category: "grade", precision: 2 },
  grade_force_proxy_n: { label: "Grade Force", unit: "N", isProxy: true, isEstimate: true, category: "grade", precision: 0,
    warning: "Proxy — requires vehicle mass. Grade is inferred, not measured." },
  grade_corrected_speed_loss_mph_s: { label: "Grade-Corrected Speed Loss", unit: "mph/s", isProxy: true, isEstimate: true, category: "grade", precision: 2 },

  // ── Dynamic pressure / aero ──
  dynamic_pressure_pa: { label: "Dynamic Pressure", unit: "Pa", isProxy: false, isEstimate: false, category: "aero", precision: 0 },
  dynamic_pressure_psf: { label: "Dynamic Pressure", unit: "psf", isProxy: false, isEstimate: false, category: "aero", precision: 1 },
  dynamic_pressure_lap_index: { label: "DP Lap Index", unit: "index", isProxy: true, isEstimate: true, category: "aero", precision: 3,
    warning: "Lap-relative — not comparable across runs." },
  dynamic_pressure_index: { label: "DP Index", unit: "index", isProxy: true, isEstimate: true, category: "aero", precision: 3,
    warning: "Lap-relative — not comparable across runs." },
  aero_load_index: { label: "Aero Load Index", unit: "index", isProxy: true, isEstimate: true, category: "aero", precision: 3,
    warning: "Proxy — not a direct force measurement." },
  aero_load_index_180mph: { label: "Aero Load Index", unit: "index", isProxy: true, isEstimate: true, category: "aero", precision: 3,
    warning: "Proxy — not a direct force measurement." },

  // ── Ride heights / platform ──
  cfs_ride_height_in: { label: "CFS Ride Height", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 3 },
  cfs_ride_height_mm: { label: "CFS Ride Height", unit: "mm", isProxy: false, isEstimate: false, category: "platform", precision: 1 },
  cfsr_height_mm: { label: "CFS Ride Height", unit: "mm", isProxy: false, isEstimate: false, category: "platform", precision: 1 },
  lf_ride_height_in: { label: "LF Ride Height", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  rf_ride_height_in: { label: "RF Ride Height", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  lr_ride_height_in: { label: "LR Ride Height", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  rr_ride_height_in: { label: "RR Ride Height", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  center_rake_fs_in: { label: "Center Rake", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  side_rake_in: { label: "Side Rake", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 3 },
  front_split_in: { label: "Front Split", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  rear_split_in: { label: "Rear Split", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  front_avg_rh_in: { label: "Front Avg RH", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  rear_avg_rh_in: { label: "Rear Avg RH", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  left_avg_rh_in: { label: "Left Avg RH", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },
  right_avg_rh_in: { label: "Right Avg RH", unit: "in", isProxy: false, isEstimate: false, category: "platform", precision: 2 },

  // ── Platform angles / roll ──
  platform_pitch_deg_from_rh: { label: "Platform Pitch", unit: "°", isProxy: true, isEstimate: true, category: "platform", precision: 2,
    warning: "Estimate from ride heights — assumes 1:1 motion ratio." },
  platform_roll_deg_from_rh: { label: "Platform Roll", unit: "°", isProxy: true, isEstimate: true, category: "platform", precision: 2,
    warning: "Estimate from ride heights — assumes 1:1 motion ratio." },
  front_platform_roll_deg_from_rh: { label: "Front Roll", unit: "°", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  rear_platform_roll_deg_from_rh: { label: "Rear Roll", unit: "°", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  platform_roll_balance_deg: { label: "Roll Balance", unit: "°", isProxy: true, isEstimate: true, category: "platform", precision: 2 },

  // ── Risk / stability ──
  cfs_risk_score: { label: "CFS Risk", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  platform_risk_score: { label: "Platform Risk", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  platform_stability_score: { label: "Platform Stability", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 3 },
  rake_stability_score: { label: "Rake Stability", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 3 },
  platform_compression_index: { label: "Platform Compression", unit: "index", isProxy: true, isEstimate: true, category: "platform", precision: 3 },
  full_throttle_resistance_index: { label: "Full-Throttle Resistance", unit: "index", isProxy: true, isEstimate: true, category: "scrub", precision: 3 },

  // ── Rear scrape ──
  rear_min_ride_height_mm: { label: "Rear Min RH", unit: "mm", isProxy: true, isEstimate: true, category: "platform", precision: 1 },
  rear_min_ride_height_in: { label: "Rear Min RH", unit: "in", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  rear_scrape_margin_mm: { label: "Rear Scrape Margin", unit: "mm", isProxy: true, isEstimate: true, category: "platform", precision: 1 },
  rear_scrape_risk_score: { label: "Rear Scrape Risk", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  rear_platform_contact_risk: { label: "Rear Contact Risk", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  rear_scrape_side: { label: "Rear Scrape Side", unit: "code", isProxy: true, isEstimate: true, category: "platform", precision: 0 },
  rear_scrape_side_label: { label: "Rear Scrape Side", unit: "", isProxy: true, isEstimate: true, category: "platform", precision: 0 },

  // ── Platform balance ──
  front_platform_risk_score: { label: "Front Platform Risk", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  rear_platform_risk_score: { label: "Rear Platform Risk", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  whole_car_bottoming_risk: { label: "Whole-Car Bottoming", unit: "score", isProxy: true, isEstimate: true, category: "platform", precision: 2 },
  platform_balance_label: { label: "Platform Balance", unit: "", isProxy: false, isEstimate: false, category: "platform", precision: 0 },
  platform_balance_explanation: { label: "Balance Explanation", unit: "", isProxy: false, isEstimate: false, category: "platform", precision: 0 },

  // ── Aero/load proxies ──
  front_load_proxy_n: { label: "Front Load", unit: "N", isProxy: true, isEstimate: true, category: "aero", precision: 0,
    warning: "Proxy — requires setup spring rates and ride heights." },
  rear_load_proxy_n: { label: "Rear Load", unit: "N", isProxy: true, isEstimate: true, category: "aero", precision: 0,
    warning: "Proxy — requires setup spring rates and ride heights." },
  front_aero_proxy_n: { label: "Front Aero", unit: "N", isProxy: true, isEstimate: true, category: "aero", precision: 0,
    warning: "Proxy — not a direct force measurement." },
  rear_aero_proxy_n: { label: "Rear Aero", unit: "N", isProxy: true, isEstimate: true, category: "aero", precision: 0,
    warning: "Proxy — not a direct force measurement." },
  rear_downforce_proxy_n: { label: "Rear Downforce", unit: "N", isProxy: true, isEstimate: true, category: "aero", precision: 0,
    warning: "Proxy — not a direct force measurement." },
  rear_platform_proxy_n: { label: "Rear Platform", unit: "N", isProxy: true, isEstimate: true, category: "aero", precision: 0 },
  rear_diffuser_proxy_n: { label: "Rear Diffuser", unit: "N", isProxy: true, isEstimate: true, category: "aero", precision: 0,
    warning: "Very low confidence — not a direct force measurement." },
  aero_balance_front_pct: { label: "Aero Balance Front", unit: "%", isProxy: true, isEstimate: true, category: "aero", precision: 1 },

  // ── Drag / scrub / steering ──
  drag_scrub_suspicion: { label: "Drag/Scrub Suspicion", unit: "index", isProxy: true, isEstimate: true, category: "scrub", precision: 3 },
  front_scrub_proxy: { label: "Front Scrub", unit: "proxy", isProxy: true, isEstimate: true, category: "scrub", precision: 3 },
  rear_scrub_proxy: { label: "Rear Scrub", unit: "proxy", isProxy: true, isEstimate: true, category: "scrub", precision: 3 },
  yaw_error_proxy: { label: "Yaw Error", unit: "rad/s", isProxy: true, isEstimate: true, category: "scrub", precision: 3 },
  ackermann_steering_expected_deg: { label: "Ackermann Expected", unit: "°", isProxy: true, isEstimate: true, category: "scrub", precision: 2 },
  ackermann_steering_error_deg: { label: "Ackermann Error", unit: "°", isProxy: true, isEstimate: true, category: "scrub", precision: 2 },
  ackermann_scrub_proxy: { label: "Ackermann Scrub", unit: "proxy", isProxy: true, isEstimate: true, category: "scrub", precision: 3 },

  // ── Slip ratios / wheel speed ──
  lf_slip_ratio: { label: "LF Slip", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  rf_slip_ratio: { label: "RF Slip", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  lr_slip_ratio: { label: "LR Slip", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  rr_slip_ratio: { label: "RR Slip", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  lf_slip_ratio_proxy: { label: "LF Slip Proxy", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  rf_slip_ratio_proxy: { label: "RF Slip Proxy", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  lr_slip_ratio_proxy: { label: "LR Slip Proxy", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  rr_slip_ratio_proxy: { label: "RR Slip Proxy", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  driven_wheel_slip_proxy: { label: "Driven Wheel Slip", unit: "ratio", isProxy: true, isEstimate: true, category: "tires", precision: 3 },
  front_wheel_speed_mismatch_raw: { label: "Front Wheel Mismatch", unit: "m/s", isProxy: false, isEstimate: false, category: "scrub", precision: 2 },
  rear_wheel_speed_mismatch_raw: { label: "Rear Wheel Mismatch", unit: "m/s", isProxy: false, isEstimate: false, category: "scrub", precision: 2 },
  front_wheel_speed_mismatch_corrected: { label: "Front Mismatch (corr)", unit: "m/s", isProxy: false, isEstimate: false, category: "scrub", precision: 2 },
  rear_wheel_speed_mismatch_corrected: { label: "Rear Mismatch (corr)", unit: "m/s", isProxy: false, isEstimate: false, category: "scrub", precision: 2 },

  // ── Tires ──
  lf_pressure: { label: "LF Pressure", unit: "psi", isProxy: false, isEstimate: false, category: "tires", precision: 1 },
  rf_pressure: { label: "RF Pressure", unit: "psi", isProxy: false, isEstimate: false, category: "tires", precision: 1 },
  lr_pressure: { label: "LR Pressure", unit: "psi", isProxy: false, isEstimate: false, category: "tires", precision: 1 },
  rr_pressure: { label: "RR Pressure", unit: "psi", isProxy: false, isEstimate: false, category: "tires", precision: 1 },
  lf_pressure_gain: { label: "LF Pressure Gain", unit: "psi", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  rf_pressure_gain: { label: "RF Pressure Gain", unit: "psi", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  lr_pressure_gain: { label: "LR Pressure Gain", unit: "psi", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  rr_pressure_gain: { label: "RR Pressure Gain", unit: "psi", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  lf_temp_spread: { label: "LF Temp Spread", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  rf_temp_spread: { label: "RF Temp Spread", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  lr_temp_spread: { label: "LR Temp Spread", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  rr_temp_spread: { label: "RR Temp Spread", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  lf_wear_spread: { label: "LF Wear Spread", unit: "mm", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  rf_wear_spread: { label: "RF Wear Spread", unit: "mm", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  lr_wear_spread: { label: "LR Wear Spread", unit: "mm", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  rr_wear_spread: { label: "RR Wear Spread", unit: "mm", isProxy: true, isEstimate: true, category: "tires", precision: 2 },
  lf_camber_temp_bias_c: { label: "LF Camber Bias", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  rf_camber_temp_bias_c: { label: "RF Camber Bias", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  lr_camber_temp_bias_c: { label: "LR Camber Bias", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  rr_camber_temp_bias_c: { label: "RR Camber Bias", unit: "°C", isProxy: true, isEstimate: true, category: "tires", precision: 1 },
  lf_camber_bias_label: { label: "LF Camber", unit: "", isProxy: true, isEstimate: true, category: "tires", precision: 0 },
  rf_camber_bias_label: { label: "RF Camber", unit: "", isProxy: true, isEstimate: true, category: "tires", precision: 0 },
  lr_camber_bias_label: { label: "LR Camber", unit: "", isProxy: true, isEstimate: true, category: "tires", precision: 0 },
  rr_camber_bias_label: { label: "RR Camber", unit: "", isProxy: true, isEstimate: true, category: "tires", precision: 0 },

  // ── Shocks ──
  lf_shock_defl_in: { label: "LF Shock Defl", unit: "in", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  rf_shock_defl_in: { label: "RF Shock Defl", unit: "in", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  lr_shock_defl_in: { label: "LR Shock Defl", unit: "in", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  rr_shock_defl_in: { label: "RR Shock Defl", unit: "in", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  lf_shock_vel_in_s: { label: "LF Shock Vel", unit: "in/s", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  rf_shock_vel_in_s: { label: "RF Shock Vel", unit: "in/s", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  lr_shock_vel_in_s: { label: "LR Shock Vel", unit: "in/s", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  rr_shock_vel_in_s: { label: "RR Shock Vel", unit: "in/s", isProxy: false, isEstimate: false, category: "shocks", precision: 2 },
  lf_shock_velocity_rms: { label: "LF Shock RMS", unit: "in/s", isProxy: true, isEstimate: true, category: "shocks", precision: 2 },
  rf_shock_velocity_rms: { label: "RF Shock RMS", unit: "in/s", isProxy: true, isEstimate: true, category: "shocks", precision: 2 },
  lr_shock_velocity_rms: { label: "LR Shock RMS", unit: "in/s", isProxy: true, isEstimate: true, category: "shocks", precision: 2 },
  rr_shock_velocity_rms: { label: "RR Shock RMS", unit: "in/s", isProxy: true, isEstimate: true, category: "shocks", precision: 2 },
  lf_shock_activity_index: { label: "LF Shock Activity", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  rf_shock_activity_index: { label: "RF Shock Activity", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  lr_shock_activity_index: { label: "LR Shock Activity", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  rr_shock_activity_index: { label: "RR Shock Activity", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  lf_damper_energy_proxy: { label: "LF Damper Energy", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  rf_damper_energy_proxy: { label: "RF Damper Energy", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  lr_damper_energy_proxy: { label: "LR Damper Energy", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  rr_damper_energy_proxy: { label: "RR Damper Energy", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  shock_velocity_rms: { label: "Shock Velocity RMS", unit: "in/s", isProxy: true, isEstimate: true, category: "shocks", precision: 2 },
  shock_activity_index: { label: "Shock Activity", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  damper_energy_proxy: { label: "Damper Energy", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },
  damper_work_proxy: { label: "Damper Work", unit: "index", isProxy: true, isEstimate: true, category: "shocks", precision: 3 },

  // ── GPS / track ──
  track_x_m: { label: "Track X", unit: "m", isProxy: false, isEstimate: false, category: "gps", precision: 1 },
  track_y_m: { label: "Track Y", unit: "m", isProxy: false, isEstimate: false, category: "gps", precision: 1 },
  track_x_ft: { label: "Track X", unit: "ft", isProxy: false, isEstimate: false, category: "gps", precision: 0 },
  track_y_ft: { label: "Track Y", unit: "ft", isProxy: false, isEstimate: false, category: "gps", precision: 0 },
};

export function getChannelUiMeta(channel: string): ChannelUiMeta | null {
  return CHANNEL_META[channel] ?? null;
}

export function isProxyChannel(channel: string): boolean {
  return CHANNEL_META[channel]?.isProxy ?? false;
}

export function isEstimateChannel(channel: string): boolean {
  return CHANNEL_META[channel]?.isEstimate ?? false;
}

export function isMissingValue(value: unknown): boolean {
  return value == null || (typeof value === "number" && (Number.isNaN(value) || !Number.isFinite(value))) || value === "" || value === "Unavailable";
}

export function displayUnavailable(reason?: string): string {
  return reason ? `Unavailable — ${reason}` : "Unavailable";
}

/** Get a human-readable disclaimer for a proxy/estimate channel. */
export function getChannelDisclaimer(channel: string): string | undefined {
  return CHANNEL_META[channel]?.warning;
}

/** Get the display precision for a channel. */
export function getChannelPrecision(channel: string): number {
  return CHANNEL_META[channel]?.precision ?? 2;
}

/** Get the display unit for a channel. */
export function getChannelUnit(channel: string): string {
  return CHANNEL_META[channel]?.unit ?? "";
}

/** Get the display label for a channel. */
export function getChannelLabel(channel: string): string {
  return CHANNEL_META[channel]?.label ?? channel;
}

/**
 * Get a legend label for ECharts series.
 * In race mode, returns the human-readable label.
 * In learning mode, appends the raw channel name in parentheses.
 */
export function getLegendLabel(channel: string, mode: "race" | "learning" = "race"): string {
  const label = getChannelLabel(channel);
  if (mode === "learning") {
    return `${label} (${channel})`;
  }
  return label;
}
