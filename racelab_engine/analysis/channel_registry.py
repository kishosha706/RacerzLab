from __future__ import annotations

from enum import Enum

"""Canonical names for raw iRacing telemetry.

The raw name remains the source of truth and is always archived.  Canonical
names are additive compatibility aliases used by analysis code; they never
replace the source identity in the telemetry vault.
"""


RAW_TO_CANONICAL: dict[str, str] = {
    # Time, position, and operating state.
    "SessionTime": "session_time",
    "SessionTick": "session_tick",
    "SessionState": "session_state",
    "SessionFlags": "session_flags",
    "SessionTimeRemain": "session_time_remaining_s",
    "SessionLapsRemain": "session_laps_remaining_legacy",
    "SessionLapsRemainEx": "session_laps_remaining",
    "SessionTimeTotal": "session_time_total_s",
    "SessionLapsTotal": "session_laps_total",
    "Lap": "lap",
    "LapCompleted": "lap_completed",
    "OnPitRoad": "on_pit_road",
    "IsOnTrack": "is_on_track",
    "PlayerTrackSurface": "player_track_surface",
    "PlayerTrackSurfaceMaterial": "player_track_surface_material",
    "PlayerCarWeightPenalty": "player_car_weight_penalty_kg",
    "PlayerCarPowerAdjust": "player_car_power_adjust_pct",
    "PlayerCarPosition": "player_race_position",
    "PlayerCarClassPosition": "player_class_position",
    "PlayerCarClass": "player_car_class_id",
    "PlayerCarIdx": "player_car_index",
    "PlayerCarInPitStall": "player_in_pit_stall",
    "PlayerCarPitSvStatus": "player_pit_service_status",
    "PlayerCarTowTime": "player_tow_service_time_s",
    "PlayerCarTeamIncidentCount": "player_team_incident_count",
    "PlayerCarMyIncidentCount": "player_incident_count",
    "PlayerCarDriverIncidentCount": "player_driver_incident_count",
    "PlayerIncidents": "player_incident_flags",
    "PaceMode": "pace_mode",
    "PitsOpen": "pits_open",
    "PitstopActive": "pitstop_active",
    "PitRepairLeft": "pit_repair_remaining_s",
    "PitOptRepairLeft": "pit_optional_repair_remaining_s",
    "PitSvFlags": "pending_pit_service_flags",
    "PitSvFuel": "pending_pit_fuel_add",
    "LapDist": "lap_dist_m",
    "LapDistPct": "lap_dist_pct",
    # Simulator lap clocks and delta-validity fields are corroboration only.
    # They never replace RacerZLab's qualified base-record clock or physical
    # position integration.
    "LapCurrentLapTime": "lap_current_time_s",
    "LapLastLapTime": "lap_last_time_s",
    "LapBestLapTime": "lap_best_time_s",
    "LapDeltaToBestLap": "lap_delta_to_best_s",
    "LapDeltaToOptimalLap": "lap_delta_to_optimal_s",
    "LapDeltaToSessionBestLap": "lap_delta_to_session_best_s",
    "LapDeltaToSessionOptimalLap": "lap_delta_to_session_optimal_s",
    "LapDeltaToBestLap_OK": "lap_delta_to_best_valid",
    "LapDeltaToOptimalLap_OK": "lap_delta_to_optimal_valid",
    "LapDeltaToSessionBestLap_OK": "lap_delta_to_session_best_valid",
    "LapDeltaToSessionOptimalLap_OK": "lap_delta_to_session_optimal_valid",
    # Driver and vehicle state.
    "Speed": "speed_mps",
    "RPM": "rpm",
    "Gear": "gear",
    "Throttle": "throttle_01",
    "Brake": "brake_01",
    "ThrottleRaw": "throttle_raw_01",
    "BrakeRaw": "brake_raw_01",
    "Shifter": "shifter_input",
    "SteeringWheelFFBEnabled": "steering_ffb_enabled",
    "SteeringWheelMaxForceNm": "steering_ffb_max_force_nm",
    "SteeringWheelUseLinear": "steering_ffb_use_linear",
    "SteeringWheelPctIntensity": "steering_ffb_intensity_01",
    "SteeringWheelPctSmoothing": "steering_ffb_smoothing_01",
    "SteeringWheelPctDamper": "steering_ffb_damper_01",
    "SteeringWheelLimiter": "steering_ffb_limiter_01",
    "dcBrakeBias": "applied_brake_bias",
    "dpLFTireColdPress": "requested_lf_tire_cold_pressure_pa",
    "dpRFTireColdPress": "requested_rf_tire_cold_pressure_pa",
    "dpLRTireColdPress": "requested_lr_tire_cold_pressure_pa",
    "dpRRTireColdPress": "requested_rr_tire_cold_pressure_pa",
    "dpLTireChange": "requested_left_tire_change",
    "dpRTireChange": "requested_right_tire_change",
    "dpFuelFill": "requested_fuel_fill",
    "dpFuelAddKg": "requested_fuel_add_kg",
    "dpFuelAutoFillEnabled": "requested_fuel_auto_fill_enabled",
    "dpFuelAutoFillActive": "requested_fuel_auto_fill_active",
    "TireLF_RumblePitch": "lf_rumble_pitch_hz",
    "TireRF_RumblePitch": "rf_rumble_pitch_hz",
    "TireLR_RumblePitch": "lr_rumble_pitch_hz",
    "TireRR_RumblePitch": "rr_rumble_pitch_hz",
    "SteeringWheelAngle": "steering_rad",
    "YawRate": "yaw_rate",
    "LatAccel": "lat_accel",
    "LongAccel": "long_accel",
    "VertAccel": "vert_accel",
    "AirDensity": "air_density",
    "Lat": "lat",
    "Lon": "lon",
    "Alt": "alt",
    "CarPath": "car_path",
    # Platform and suspension.
    "CFSRrideHeight": "cfs_ride_height_m",
    "LFrideHeight": "lf_ride_height_m",
    "RFrideHeight": "rf_ride_height_m",
    "LRrideHeight": "lr_ride_height_m",
    "RRrideHeight": "rr_ride_height_m",
    "LFshockDefl": "lf_shock_defl_in",
    "RFshockDefl": "rf_shock_defl_in",
    "LRshockDefl": "lr_shock_defl_in",
    "RRshockDefl": "rr_shock_defl_in",
    "LFSHshockDefl": "lf_shock_defl_in",
    "RFSHshockDefl": "rf_shock_defl_in",
    "LRSHshockDefl": "lr_shock_defl_in",
    "RRSHshockDefl": "rr_shock_defl_in",
    "LFshockVel": "lf_shock_vel_in_s",
    "RFshockVel": "rf_shock_vel_in_s",
    "LRshockVel": "lr_shock_vel_in_s",
    "RRshockVel": "rr_shock_vel_in_s",
    "LFSHshockVel": "lf_shock_vel_in_s",
    "RFSHshockVel": "rf_shock_vel_in_s",
    "LRSHshockVel": "lr_shock_vel_in_s",
    "RRSHshockVel": "rr_shock_vel_in_s",
    # Tire state.
    "LFpressure": "lf_pressure",
    "RFpressure": "rf_pressure",
    "LRpressure": "lr_pressure",
    "RRpressure": "rr_pressure",
    "LFcoldPressure": "lf_cold_pressure",
    "RFcoldPressure": "rf_cold_pressure",
    "LRcoldPressure": "lr_cold_pressure",
    "RRcoldPressure": "rr_cold_pressure",
    "LFtempL": "lf_temp_left",
    "RFtempL": "rf_temp_left",
    "LRtempL": "lr_temp_left",
    "RRtempL": "rr_temp_left",
    "LFtempM": "lf_temp_middle",
    "RFtempM": "rf_temp_middle",
    "LRtempM": "lr_temp_middle",
    "RRtempM": "rr_temp_middle",
    "LFtempR": "lf_temp_right",
    "RFtempR": "rf_temp_right",
    "LRtempR": "lr_temp_right",
    "RRtempR": "rr_temp_right",
    "LFtempCL": "lf_carcass_temp_l",
    "RFtempCL": "rf_carcass_temp_l",
    "LRtempCL": "lr_carcass_temp_l",
    "RRtempCL": "rr_carcass_temp_l",
    "LFtempCM": "lf_carcass_temp_m",
    "RFtempCM": "rf_carcass_temp_m",
    "LRtempCM": "lr_carcass_temp_m",
    "RRtempCM": "rr_carcass_temp_m",
    "LFtempCR": "lf_carcass_temp_r",
    "RFtempCR": "rf_carcass_temp_r",
    "LRtempCR": "lr_carcass_temp_r",
    "RRtempCR": "rr_carcass_temp_r",
    "LFwearL": "lf_wear_left",
    "RFwearL": "rf_wear_left",
    "LRwearL": "lr_wear_left",
    "RRwearL": "rr_wear_left",
    "LFwearM": "lf_wear_middle",
    "RFwearM": "rf_wear_middle",
    "LRwearM": "lr_wear_middle",
    "RRwearM": "rr_wear_middle",
    "LFwearR": "lf_wear_right",
    "RFwearR": "rf_wear_right",
    "LRwearR": "lr_wear_right",
    "RRwearR": "rr_wear_right",
    "LFodometer": "lf_tire_distance_m",
    "RFodometer": "rf_tire_distance_m",
    "LRodometer": "lr_tire_distance_m",
    "RRodometer": "rr_tire_distance_m",
    "LFspeed": "lf_speed",
    "RFspeed": "rf_speed",
    "LRspeed": "lr_speed",
    "RRspeed": "rr_speed",
    "PlayerTireCompound": "player_tire_compound",
    "PitSvTireCompound": "pending_pit_tire_compound",
    "PlayerCarDryTireSetLimit": "player_dry_tire_set_limit",
    "LeftTireSetsUsed": "left_tire_sets_used",
    "RightTireSetsUsed": "right_tire_sets_used",
    "FrontTireSetsUsed": "front_tire_sets_used",
    "RearTireSetsUsed": "rear_tire_sets_used",
    "TireSetsUsed": "tire_sets_used",
    "LeftTireSetsAvailable": "left_tire_sets_available",
    "RightTireSetsAvailable": "right_tire_sets_available",
    "FrontTireSetsAvailable": "front_tire_sets_available",
    "RearTireSetsAvailable": "rear_tire_sets_available",
    "TireSetsAvailable": "tire_sets_available",
    # Per-corner tire inventory is a pit-boundary snapshot.  Preserve each
    # corner independently; never collapse it into an on-track tire-state cause.
    "LFTiresUsed": "lf_tires_used",
    "RFTiresUsed": "rf_tires_used",
    "LRTiresUsed": "lr_tires_used",
    "RRTiresUsed": "rr_tires_used",
    "LFTiresAvailable": "lf_tires_available",
    "RFTiresAvailable": "rf_tires_available",
    "LRTiresAvailable": "lr_tires_available",
    "RRTiresAvailable": "rr_tires_available",
    # Brake system.
    "LFbrakeLinePress": "lf_brake_line_pressure_bar",
    "RFbrakeLinePress": "rf_brake_line_pressure_bar",
    "LRbrakeLinePress": "lr_brake_line_pressure_bar",
    "RRbrakeLinePress": "rr_brake_line_pressure_bar",
    "BrakeABSactive": "brake_abs_active",
    "BrakeABScutPct": "brake_abs_cut_01",
    # Nearby-car context.  These channels are archived as context only; their
    # presence does not establish draft/clean-air classification.
    "CarDistAhead": "car_distance_ahead_m",
    "CarDistBehind": "car_distance_behind_m",
    "FuelLevel": "fuel_level",
    "FuelLevelPct": "fuel_level_pct",
    "FuelUsePerHour": "fuel_use_per_hour",
    "WaterTemp": "water_temp",
    "OilTemp": "oil_temp",
    "EngineWarnings": "engine_warnings",
    "Voltage": "voltage",
    "WaterLevel": "water_level",
    "FuelPress": "fuel_press",
    "OilPress": "oil_press",
    "OilLevel": "oil_level",
    "ManifoldPress": "manifold_press",
    "Engine0_RPM": "engine0_rpm",
    "SteeringWheelAngleMax": "steering_wheel_angle_max",
    "Clutch": "clutch",
    "ClutchRaw": "clutch_raw",
    "ShiftPowerPct": "shift_power_pct",
    "ShiftGrindRPM": "shift_grind_rpm",
    "AirTemp": "air_temp",
    "TrackTemp": "track_temp",
    "WindVel": "wind_vel",
    "WindDir": "wind_dir",
    "AirPressure": "air_pressure",
    "TrackTempCrew": "track_temp_crew",
    "RelativeHumidity": "relative_humidity",
    "FogLevel": "fog_level",
    "Skies": "skies",
    "Precipitation": "precipitation",
    "TrackWetness": "track_wetness",
    "VelocityX": "velocity_x",
    "VelocityY": "velocity_y",
    "VelocityZ": "velocity_z",
    "Yaw": "yaw",
    "YawNorth": "yaw_north",
    "Pitch": "pitch",
    "Roll": "roll",
    "PitchRate": "pitch_rate",
    "RollRate": "roll_rate",
    # Steering effort and high-rate samples.
    "SteeringWheelTorque": "steering_wheel_torque_nm",
    "SteeringWheelTorque_ST": "steering_wheel_torque_subtick_nm",
    "SteeringWheelPctTorque": "steering_wheel_torque_unsigned_01",
    "SteeringWheelPctTorqueSign": "steering_wheel_torque_signed_01",
    "SteeringWheelPctTorqueSignStops": "steering_wheel_torque_stops_01",
    # Measurement and simulator-integrity markers.
    "DriverMarker": "driver_marker",
    "EnterExitReset": "enter_exit_reset_state",
    "CpuUsageFG": "cpu_usage_foreground",
    "CpuUsageBG": "cpu_usage_background",
    "FrameRate": "frame_rate",
    "GpuUsage": "gpu_usage",
    "ChanQuality": "channel_quality",
    "ChanLatency": "channel_latency_s",
    "ChanAvgLatency": "channel_average_latency_s",
    "MemPageFaultSec": "memory_page_faults_per_s",
    "MemSoftPageFaultSec": "memory_soft_page_faults_per_s",
}


class CanonicalMappingKind(str, Enum):
    EXACT_ALIAS = "exact_alias"
    UNIT_CONVERTED_ALIAS = "unit_converted_alias"
    DERIVED_FALLBACK = "derived_fallback"
    INCOMPATIBLE_SIMILARLY_NAMED_CHANNEL = "incompatible_similarly_named_channel"
    UNKNOWN = "unknown"


_UNIT_CONVERTED_RAW_NAMES = frozenset(
    raw_name
    for raw_name in RAW_TO_CANONICAL
    if ("shockDefl" in raw_name or "shockVel" in raw_name) and "SHshock" not in raw_name
)
_DERIVED_FALLBACK_RAW_NAMES = frozenset(
    raw_name for raw_name in RAW_TO_CANONICAL if "SHshock" in raw_name
)


def _identity_token(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def canonical_name(raw_name: str) -> str | None:
    return RAW_TO_CANONICAL.get(raw_name)


def canonical_mapping_kind(raw_name: str) -> str:
    if raw_name in _DERIVED_FALLBACK_RAW_NAMES:
        return CanonicalMappingKind.DERIVED_FALLBACK.value
    if raw_name in _UNIT_CONVERTED_RAW_NAMES:
        return CanonicalMappingKind.UNIT_CONVERTED_ALIAS.value
    if raw_name in RAW_TO_CANONICAL:
        return CanonicalMappingKind.EXACT_ALIAS.value

    token = _identity_token(raw_name)
    registered_tokens = {
        _identity_token(value)
        for value in (*RAW_TO_CANONICAL.keys(), *RAW_TO_CANONICAL.values())
    }
    if token and token in registered_tokens:
        return CanonicalMappingKind.INCOMPATIBLE_SIMILARLY_NAMED_CHANNEL.value
    return CanonicalMappingKind.UNKNOWN.value
