/**
 * Question-owned Platform projections.
 *
 * The public Platform workspace exposes Balance, Scrape/Scrub, and Shocks.
 * It must not pull tire, nominal-geometry, hidden aero, or other unrelated
 * families merely because they exist in the archive. A Learning-mode custom
 * channel is appended separately as one observation-only lane.
 */
export const TRACE_CONTEXT_CHANNELS = [
  "lap_dist_pct_100",
  "speed_mps",
  "speed_mph",
  "speed_rate_mps2",
  "throttle_pct",
  "brake_pct",
  "steering_deg",
  "abs_steering_deg",
  "lat_accel_g",
  "long_accel_g",
  "vert_accel_g",
] as const;

export const PLATFORM_BALANCE_CHANNELS = [
  "cfs_ride_height_in", "cfs_ride_height_mm", "cfsr_height_mm",
  "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in",
  "lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm",
  "front_avg_rh_in", "rear_avg_rh_in", "left_avg_rh_in", "right_avg_rh_in",
  "center_rake_fs_in", "side_rake_in", "front_split_in", "rear_split_in",
  "cfs_risk_score", "platform_risk_score", "platform_stability_score",
  "rake_stability_score", "platform_compression_index",
  "front_platform_risk_score", "rear_platform_risk_score",
  "whole_car_bottoming_risk", "platform_balance_label", "platform_balance_explanation",
] as const;

export const SCRAPE_SCRUB_CHANNELS = [
  "rear_min_ride_height_mm", "rear_min_ride_height_in",
  "rear_scrape_margin_mm", "rear_scrape_risk_score",
  "rear_platform_contact_risk", "rear_scrape_side", "rear_scrape_side_label",
  "drag_scrub_suspicion", "full_throttle_resistance_index",
] as const;

export const SHOCK_RESPONSE_CHANNELS = [
  "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
  "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
  "lf_shock_static_defl_in", "rf_shock_static_defl_in",
  "lr_shock_static_defl_in", "rr_shock_static_defl_in",
  "lf_shock_defl_delta_in", "rf_shock_defl_delta_in",
  "lr_shock_defl_delta_in", "rr_shock_defl_delta_in",
  "lf_shock_velocity_rms", "rf_shock_velocity_rms",
  "lr_shock_velocity_rms", "rr_shock_velocity_rms",
  "lf_shock_activity_index", "rf_shock_activity_index",
  "lr_shock_activity_index", "rr_shock_activity_index",
  "lf_damper_energy_proxy", "rf_damper_energy_proxy",
  "lr_damper_energy_proxy", "rr_damper_energy_proxy",
  "shock_velocity_rms", "shock_activity_index", "damper_energy_proxy",
] as const;

export const TRACE_WORKBENCH_CHANNELS = [...new Set([
  ...TRACE_CONTEXT_CHANNELS,
  ...PLATFORM_BALANCE_CHANNELS,
  ...SCRAPE_SCRUB_CHANNELS,
  ...SHOCK_RESPONSE_CHANNELS,
])];
