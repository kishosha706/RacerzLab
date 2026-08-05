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
    # Driver and vehicle state.
    "Speed": "speed_mps",
    "RPM": "rpm",
    "Gear": "gear",
    "Throttle": "throttle_01",
    "Brake": "brake_01",
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
    "LFtempL": "lf_temp_inner",
    "RFtempL": "rf_temp_inner",
    "LRtempL": "lr_temp_inner",
    "RRtempL": "rr_temp_inner",
    "LFtempM": "lf_temp_middle",
    "RFtempM": "rf_temp_middle",
    "LRtempM": "lr_temp_middle",
    "RRtempM": "rr_temp_middle",
    "LFtempR": "lf_temp_outer",
    "RFtempR": "rf_temp_outer",
    "LRtempR": "lr_temp_outer",
    "RRtempR": "rr_temp_outer",
    "LFwearL": "lf_wear_inner",
    "RFwearL": "rf_wear_inner",
    "LRwearL": "lr_wear_inner",
    "RRwearL": "rr_wear_inner",
    "LFwearM": "lf_wear_middle",
    "RFwearM": "rf_wear_middle",
    "LRwearM": "lr_wear_middle",
    "RRwearM": "rr_wear_middle",
    "LFwearR": "lf_wear_outer",
    "RFwearR": "rf_wear_outer",
    "LRwearR": "lr_wear_outer",
    "RRwearR": "rr_wear_outer",
    "LFodometer": "lf_tire_distance_m",
    "RFodometer": "rf_tire_distance_m",
    "LRodometer": "lr_tire_distance_m",
    "RRodometer": "rr_tire_distance_m",
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
