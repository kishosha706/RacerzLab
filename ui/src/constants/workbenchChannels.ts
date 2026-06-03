/** Shared trace channel list — used by both initial load and lap-change requests. */
export const TRACE_WORKBENCH_CHANNELS = [
  // ── Controls / input ──
  "throttle_pct", "brake_pct", "steering_deg", "abs_steering_deg",
  "abs_lat_accel", "lat_accel_g", "long_accel_g", "vert_accel_g",

  // ── Speed / pull ──
  "lap_dist_pct_100", "speed_mph", "speed_fps",
  "speed_rate_mph_s", "speed_rate_mph_1000ft", "speed_rate_mps2",
  "grade_corrected_speed_loss_mph_s", "rpm", "gear",

  // ── Dynamic grade ──
  "dynamic_grade_rad", "dynamic_grade_deg", "grade_context_label",
  "grade_corrected_long_accel_mps2", "grade_force_proxy_n",

  // ── Dynamic pressure / aero ──
  "dynamic_pressure_pa", "dynamic_pressure_psf",
  "dynamic_pressure_lap_index", "dynamic_pressure_index",
  "aero_load_index", "aero_load_index_180mph",

  // ── Ride heights / platform ──
  "cfs_ride_height_in", "cfs_ride_height_mm", "cfsr_height_mm",
  "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in",
  "lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm",
  "front_avg_rh_in", "rear_avg_rh_in", "left_avg_rh_in", "right_avg_rh_in",
  "center_rake_fs_in", "side_rake_in", "front_split_in", "rear_split_in",

  // ── Platform angles / roll ──
  "platform_pitch_deg_from_rh", "platform_roll_deg_from_rh",
  "front_platform_roll_deg_from_rh", "rear_platform_roll_deg_from_rh",
  "platform_roll_balance_deg",

  // ── Risk / stability ──
  "cfs_risk_score", "platform_risk_score", "platform_stability_score",
  "rake_stability_score", "platform_compression_index",
  "full_throttle_resistance_index",

  // ── Rear scrape ──
  "rear_min_ride_height_mm", "rear_min_ride_height_in",
  "rear_scrape_margin_mm", "rear_scrape_risk_score",
  "rear_platform_contact_risk", "rear_scrape_side", "rear_scrape_side_label",

  // ── Platform balance ──
  "front_platform_risk_score", "rear_platform_risk_score",
  "whole_car_bottoming_risk", "platform_balance_label", "platform_balance_explanation",

  // ── Aero/load proxies ──
  "front_load_proxy_n", "rear_load_proxy_n",
  "front_aero_proxy_n", "rear_aero_proxy_n",
  "rear_downforce_proxy_n", "rear_platform_proxy_n", "rear_diffuser_proxy_n",
  "aero_balance_front_pct",

  // ── Drag / scrub / steering ──
  "drag_scrub_suspicion", "front_scrub_proxy", "rear_scrub_proxy", "yaw_error_proxy",
  "ackermann_steering_expected_deg", "ackermann_steering_error_deg", "ackermann_scrub_proxy",

  // ── Slip ratios / wheel speed ──
  "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
  "lf_slip_ratio_proxy", "rf_slip_ratio_proxy", "lr_slip_ratio_proxy", "rr_slip_ratio_proxy",
  "driven_wheel_slip_proxy",
  "front_wheel_speed_mismatch_raw", "rear_wheel_speed_mismatch_raw",
  "front_wheel_speed_mismatch_corrected", "rear_wheel_speed_mismatch_corrected",

  // ── Tires ──
  "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
  "lf_pressure_gain", "rf_pressure_gain", "lr_pressure_gain", "rr_pressure_gain",
  "lf_temp_inner", "lf_temp_middle", "lf_temp_outer",
  "rf_temp_inner", "rf_temp_middle", "rf_temp_outer",
  "lr_temp_inner", "lr_temp_middle", "lr_temp_outer",
  "rr_temp_inner", "rr_temp_middle", "rr_temp_outer",
  "lf_carcass_temp_l", "lf_carcass_temp_m", "lf_carcass_temp_r",
  "rf_carcass_temp_l", "rf_carcass_temp_m", "rf_carcass_temp_r",
  "lr_carcass_temp_l", "lr_carcass_temp_m", "lr_carcass_temp_r",
  "rr_carcass_temp_l", "rr_carcass_temp_m", "rr_carcass_temp_r",
  "lf_temp_spread", "rf_temp_spread", "lr_temp_spread", "rr_temp_spread",
  "lf_wear_spread", "rf_wear_spread", "lr_wear_spread", "rr_wear_spread",
  "lf_camber_temp_bias_c", "rf_camber_temp_bias_c",
  "lr_camber_temp_bias_c", "rr_camber_temp_bias_c",
  "lf_camber_bias_label", "rf_camber_bias_label",
  "lr_camber_bias_label", "rr_camber_bias_label",

  // ── Shocks ──
  "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
  "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
  "lf_shock_static_defl_in", "rf_shock_static_defl_in", "lr_shock_static_defl_in", "rr_shock_static_defl_in",
  "lf_shock_defl_delta_in", "rf_shock_defl_delta_in", "lr_shock_defl_delta_in", "rr_shock_defl_delta_in",
  "lf_shock_velocity_rms", "rf_shock_velocity_rms",
  "lr_shock_velocity_rms", "rr_shock_velocity_rms",
  "lf_shock_activity_index", "rf_shock_activity_index",
  "lr_shock_activity_index", "rr_shock_activity_index",
  "lf_damper_energy_proxy", "rf_damper_energy_proxy",
  "lr_damper_energy_proxy", "rr_damper_energy_proxy",
  "shock_velocity_rms", "shock_activity_index", "damper_energy_proxy",

  // ── Diffuser geometry ──
  "front_center_rh_in", "lr_height_rub_block_in", "rear_center_rh_in",
  "center_rake_in", "smooth_center_rake_in",
  "diffuser_track_width_in", "diffuser_wheelbase_in",
  "diffuser_base_volume_ft3", "diffuser_wedge_volume_ft3",
  "diffuser_volume_ft3", "smooth_diffuser_volume_ft3",

  // ── GPS / track fallback ──
  "track_x_m", "track_y_m", "track_x_ft", "track_y_ft",
];
