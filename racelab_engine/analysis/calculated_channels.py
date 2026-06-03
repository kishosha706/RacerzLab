from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from contextlib import suppress
from typing import Any, cast

from racelab_engine.analysis.constants import (
    SLIP_RATIO_SPEED_FLOOR_MPS,
    SLIP_RATIO_CLAMP_MAX,
    REFERENCE_DYNAMIC_PRESSURE_PA,
)
from racelab_engine.analysis.drag_scrub import compute_drag_scrub_index, aero_normalized_resistance
from racelab_engine.analysis.units import (
    EARTH_RADIUS_M,
    M_TO_FT,
    M_TO_IN,
    MPS_TO_MPH,
    PA_TO_PSF,
    MM_TO_IN,
    input_01_to_percent,
    radians_to_degrees,
)

ChannelMetadata = dict[str, Any]

CORE_REQUIRED_CHANNELS = [
    "SessionTime",
    "SessionTick",
    "Lap",
    "LapCompleted",
    "LapDist",
    "LapDistPct",
    "Speed",
    "RPM",
    "Gear",
    "Throttle",
    "Brake",
    "SteeringWheelAngle",
    "LatAccel",
    "LongAccel",
    "YawRate",
    "CFSRrideHeight",
    "LFrideHeight",
    "RFrideHeight",
    "LRrideHeight",
    "RRrideHeight",
    "LFSHshockDefl",
    "RFSHshockDefl",
    "LRSHshockDefl",
    "RRSHshockDefl",
    "LFSHshockVel",
    "RFSHshockVel",
    "LRSHshockVel",
    "RRSHshockVel",
    "WaterTemp",
    "OilTemp",
    "FuelLevel",
    "FuelUsePerHour",
]

HIGH_VALUE_RAW_CHANNELS = [
    "SteeringWheelAngle",
    "SteeringWheelAngleMax",
    "Throttle",
    "ThrottleRaw",
    "Brake",
    "BrakeRaw",
    "Clutch",
    "ClutchRaw",
    "Gear",
    "RPM",
    "ShiftPowerPct",
    "ShiftGrindRPM",
    "SessionTime",
    "SessionTick",
    "Lap",
    "LapCompleted",
    "LapDist",
    "LapDistPct",
    "LapBestLapTime",
    "LapLastLapTime",
    "LapCurrentLapTime",
    "LapDeltaToBestLap",
    "LapDeltaToOptimalLap",
    "LapDeltaToSessionBestLap",
    "LapDeltaToSessionOptimalLap",
    "Speed",
    "VelocityX",
    "VelocityY",
    "VelocityZ",
    "Yaw",
    "YawNorth",
    "Pitch",
    "Roll",
    "YawRate",
    "PitchRate",
    "RollRate",
    "VertAccel",
    "LatAccel",
    "LongAccel",
    "Lat",
    "Lon",
    "Alt",
    "AirDensity",
    "AirTemp",
    "AirPressure",
    "TrackTemp",
    "TrackTempCrew",
    "WindVel",
    "WindDir",
    "RelativeHumidity",
    "FogLevel",
    "Precipitation",
    "SolarAltitude",
    "SolarAzimuth",
    "Skies",
    "TrackWetness",
    "CFSRrideHeight",
    "LFrideHeight",
    "RFrideHeight",
    "LRrideHeight",
    "RRrideHeight",
    "LFshockDefl",
    "RFshockDefl",
    "LRshockDefl",
    "RRshockDefl",
    "LFSHshockDefl",
    "RFSHshockDefl",
    "LRSHshockDefl",
    "RRSHshockDefl",
    "LFshockVel",
    "RFshockVel",
    "LRshockVel",
    "RRshockVel",
    "LFSHshockVel",
    "RFSHshockVel",
    "LRSHshockVel",
    "RRSHshockVel",
    "LFspeed",
    "RFspeed",
    "LRspeed",
    "RRspeed",
    "LFpressure",
    "RFpressure",
    "LRpressure",
    "RRpressure",
    "LFcoldPressure",
    "RFcoldPressure",
    "LRcoldPressure",
    "RRcoldPressure",
    "LFtempL",
    "LFtempM",
    "LFtempR",
    "RFtempL",
    "RFtempM",
    "RFtempR",
    "LRtempL",
    "LRtempM",
    "LRtempR",
    "RRtempL",
    "RRtempM",
    "RRtempR",
    "LFtempCL",
    "LFtempCM",
    "LFtempCR",
    "RFtempCL",
    "RFtempCM",
    "RFtempCR",
    "LRtempCL",
    "LRtempCM",
    "LRtempCR",
    "RRtempCL",
    "RRtempCM",
    "RRtempCR",
    "LFwearL",
    "LFwearM",
    "LFwearR",
    "RFwearL",
    "RFwearM",
    "RFwearR",
    "LRwearL",
    "LRwearM",
    "LRwearR",
    "RRwearL",
    "RRwearM",
    "RRwearR",
    "FuelUsePerHour",
    "FuelLevel",
    "FuelLevelPct",
    "Voltage",
    "WaterTemp",
    "WaterLevel",
    "FuelPress",
    "OilTemp",
    "OilPress",
    "OilLevel",
    "ManifoldPress",
    "Engine0_RPM",
    "EngineWarnings",
]

CALCULATED_CHANNEL_UNITS: dict[str, str] = {
    "lap_dist_ft": "ft",
    "lap_dist_pct_100": "%",
    "speed_mph": "mph",
    "speed_fps": "ft/s",
    "speed_rate_mph_s": "mph/s",
    "speed_rate_mph_1000ft": "mph/1000ft",
    "dynamic_pressure_pa": "Pa",
    "dynamic_pressure_psf": "psf",
    "cfs_ride_height_mm": "mm",
    "cfs_ride_height_in": "in",
    "cfsr_height_mm": "mm",
    "lf_ride_height_mm": "mm",
    "rf_ride_height_mm": "mm",
    "lr_ride_height_mm": "mm",
    "rr_ride_height_mm": "mm",
    "lf_ride_height_in": "in",
    "rf_ride_height_in": "in",
    "lr_ride_height_in": "in",
    "rr_ride_height_in": "in",
    "front_avg_rh_in": "in",
    "rear_avg_rh_in": "in",
    "left_avg_rh_in": "in",
    "right_avg_rh_in": "in",
    "center_rake_fs_in": "in",
    "side_rake_in": "in",
    "front_split_in": "in",
    "rear_split_in": "in",
    "platform_pitch_deg_from_rh": "deg",
    "platform_roll_deg_from_rh": "deg",
    "lf_shock_defl_in": "in",
    "rf_shock_defl_in": "in",
    "lr_shock_defl_in": "in",
    "rr_shock_defl_in": "in",
    "lf_shock_static_defl_in": "in",
    "rf_shock_static_defl_in": "in",
    "lr_shock_static_defl_in": "in",
    "rr_shock_static_defl_in": "in",
    "lf_shock_defl_delta_in": "in",
    "rf_shock_defl_delta_in": "in",
    "lr_shock_defl_delta_in": "in",
    "rr_shock_defl_delta_in": "in",
    "lf_shock_vel_in_s": "in/s",
    "rf_shock_vel_in_s": "in/s",
    "lr_shock_vel_in_s": "in/s",
    "rr_shock_vel_in_s": "in/s",
    "lf_slip_ratio": "ratio",
    "rf_slip_ratio": "ratio",
    "lr_slip_ratio": "ratio",
    "rr_slip_ratio": "ratio",
    "front_wheel_speed_mismatch": "m/s",
    "rear_wheel_speed_mismatch": "m/s",
    "front_scrub_proxy": "proxy",
    "rear_scrub_proxy": "proxy",
    "cfs_risk_score": "score",
    "platform_risk_score": "score",
    "platform_stability_score": "score",
    "rake_stability_score": "score",
    "full_throttle_resistance_index": "index",
    "drag_scrub_suspicion": "index",
    "driven_wheel_slip_proxy": "ratio",
    "dynamic_pressure_lap_index": "index",
    "dynamic_pressure_index": "index",
    "aero_load_index": "index",
    "aero_load_index_180mph": "index",
    "platform_compression_index": "index",
    "shock_velocity_rms": "in/s",
    "shock_activity_index": "index",
    "damper_energy_proxy": "index",
    "damper_work_proxy": "index",
    "front_load_proxy_n": "N",
    "rear_load_proxy_n": "N",
    "front_aero_proxy_n": "N",
    "rear_aero_proxy_n": "N",
    "aero_balance_front_pct": "%",
    "rear_downforce_proxy_n": "N",
    "rear_platform_proxy_n": "N",
    "rear_diffuser_proxy_n": "N",
    "speed_rate_mps2": "m/s^2",
    "dynamic_grade_rad": "rad",
    "dynamic_grade_deg": "deg",
    "grade_corrected_long_accel_mps2": "m/s^2",
    "grade_force_proxy_n": "N",
    "grade_context_label": "label",
    "grade_corrected_speed_loss_mph_s": "mph/s",
    "ackermann_steering_expected_deg": "deg",
    "ackermann_steering_error_deg": "deg",
    "ackermann_scrub_proxy": "proxy",
    "front_platform_roll_deg_from_rh": "deg",
    "rear_platform_roll_deg_from_rh": "deg",
    "platform_roll_balance_deg": "deg",
    "lf_camber_temp_bias_c": "C",
    "rf_camber_temp_bias_c": "C",
    "lr_camber_temp_bias_c": "C",
    "rr_camber_temp_bias_c": "C",
    "lf_camber_bias_label": "label",
    "rf_camber_bias_label": "label",
    "lr_camber_bias_label": "label",
    "rr_camber_bias_label": "label",
    # raw tire temperature aliases surfaced to the UI
    "lf_temp_inner": "C",
    "lf_temp_middle": "C",
    "lf_temp_outer": "C",
    "rf_temp_inner": "C",
    "rf_temp_middle": "C",
    "rf_temp_outer": "C",
    "lr_temp_inner": "C",
    "lr_temp_middle": "C",
    "lr_temp_outer": "C",
    "rr_temp_inner": "C",
    "rr_temp_middle": "C",
    "rr_temp_outer": "C",
    "lf_carcass_temp_l": "C",
    "lf_carcass_temp_m": "C",
    "lf_carcass_temp_r": "C",
    "rf_carcass_temp_l": "C",
    "rf_carcass_temp_m": "C",
    "rf_carcass_temp_r": "C",
    "lr_carcass_temp_l": "C",
    "lr_carcass_temp_m": "C",
    "lr_carcass_temp_r": "C",
    "rr_carcass_temp_l": "C",
    "rr_carcass_temp_m": "C",
    "rr_carcass_temp_r": "C",
    # ── tire derived ──
    "lf_pressure_gain": "psi",
    "rf_pressure_gain": "psi",
    "lr_pressure_gain": "psi",
    "rr_pressure_gain": "psi",
    "lf_temp_spread": "C",
    "rf_temp_spread": "C",
    "lr_temp_spread": "C",
    "rr_temp_spread": "C",
    "lf_wear_spread": "mm",
    "rf_wear_spread": "mm",
    "lr_wear_spread": "mm",
    "rr_wear_spread": "mm",
    # ── yaw error ──
    "yaw_error_proxy": "rad/s",
    # ── vert accel g ──
    "vert_accel_g": "g",
    "front_slip_angle_deg": "deg",
    "rear_slip_angle_deg": "deg",
    "slip_angle_balance_deg": "deg",
    "track_x_m": "m",
    "track_y_m": "m",
    "track_x_ft": "ft",
    "track_y_ft": "ft",
    # ── input pct ──
    "throttle_pct": "%",
    "brake_pct": "%",
    "steering_deg": "deg",
    "abs_steering_deg": "deg",
    "rpm": "rpm",
    "gear": "gear",
    # ── accel ──
    "lat_accel": "m/s^2",
    "abs_lat_accel": "m/s^2",
    "lat_accel_g": "g",
    "long_accel_g": "g",
    # ── shock per-corner ──
    "lf_shock_velocity_rms": "in/s",
    "rf_shock_velocity_rms": "in/s",
    "lr_shock_velocity_rms": "in/s",
    "rr_shock_velocity_rms": "in/s",
    "lf_shock_activity_index": "index",
    "rf_shock_activity_index": "index",
    "lr_shock_activity_index": "index",
    "rr_shock_activity_index": "index",
    "lf_damper_energy_proxy": "index",
    "rf_damper_energy_proxy": "index",
    "lr_damper_energy_proxy": "index",
    "rr_damper_energy_proxy": "index",
    # ── wheel speed mismatch ──
    "front_wheel_speed_mismatch_raw": "m/s",
    "rear_wheel_speed_mismatch_raw": "m/s",
    "front_wheel_speed_mismatch_corrected": "m/s",
    "rear_wheel_speed_mismatch_corrected": "m/s",
    # ── rear scrape ──
    "rear_min_ride_height_mm": "mm",
    "rear_min_ride_height_in": "in",
    "rear_scrape_margin_mm": "mm",
    "rear_scrape_risk_score": "score",
    "rear_platform_contact_risk": "score",
    "rear_scrape_side": "code",
    "rear_scrape_side_label": "label",
    # ── platform balance ──
    "front_platform_risk_score": "score",
    "rear_platform_risk_score": "score",
    "whole_car_bottoming_risk": "score",
    "platform_balance_label": "label",
    "platform_balance_explanation": "label",
    # ── diffuser geometry ──
    "front_center_rh_in": "in",
    "rear_center_rh_in": "in",
    "lr_height_rub_block_in": "in",
    "center_rake_in": "in",
    "smooth_center_rake_in": "in",
    "diffuser_track_width_in": "in",
    "diffuser_wheelbase_in": "in",
    "diffuser_base_volume_ft3": "ft³",
    "diffuser_wedge_volume_ft3": "ft³",
    "diffuser_volume_ft3": "ft³",
    "smooth_diffuser_volume_ft3": "ft³",
}


# ── channel metadata registry ────────────────────────────────────

PLATFORM_RAKE_RIDE_HEIGHT = "Platform / Rake / Ride Height"
SPEED_RPM_PULL = "Speed / RPM / Pull"
DRAG_SCRUB = "Drag / Scrub"
AERO_PLATFORM = "Aero Platform"
SHOCKS = "Shocks"
TIRES = "Tires"
ENGINE = "Engine"
PLATFORM_SCRUB_TEST = "Platform/Scrub Test"
RIDE_HEIGHT_REVIEW = "Ride Height Review"
LINE_STEERING_REVIEW = "Line/Steering Review"
GEARING_COMPARISON = "Gearing Comparison"
LONG_RUN_TIRE_REVIEW = "Long Run Tire Review"
COOLING_TAPE_REVIEW = "Cooling/Tape Review"
SHOCK_STABILITY_REVIEW = "Shock/Stability Review"
AERO_PLATFORM_CHECK = "Aero Platform Check"

CHART_PRESETS = [
    PLATFORM_RAKE_RIDE_HEIGHT,
    SPEED_RPM_PULL,
    DRAG_SCRUB,
    AERO_PLATFORM,
    SHOCKS,
    TIRES,
    ENGINE,
]

EVENT_LABELS = [
    "PLATFORM_LOW",
    "PLATFORM_SCRAPE",
    "REAR_PLATFORM_LOW",
    "REAR_PLATFORM_SCRAPE",
    "REAR_CONTACT_RISK",
    "WHOLE_CAR_BOTTOMING_RISK",
    "FULL_THROTTLE_SPEED_LOSS",
    "STEERING_SCRUB",
    "DYNAMIC_PRESSURE_PEAK",
    "SHOCK_ACTIVITY",
    "TIRE_SCRUB",
    "RPM_FLATTENING",
    "HIGH_CENTER_RAKE",
    "PLATFORM_COMPRESSION",
    "MAX_DYNAMIC_PRESSURE",
]

RECOMMENDATION_LABELS = [
    PLATFORM_SCRUB_TEST,
    RIDE_HEIGHT_REVIEW,
    LINE_STEERING_REVIEW,
    GEARING_COMPARISON,
    LONG_RUN_TIRE_REVIEW,
    COOLING_TAPE_REVIEW,
    SHOCK_STABILITY_REVIEW,
    AERO_PLATFORM_CHECK,
]

CHANNEL_METADATA: dict[str, ChannelMetadata] = {
    # ── distance ──
    "lap_dist_ft": {
        "label": "Lap Distance",
        "description": "Lap distance in feet, converted from meters",
        "formula": "LapDist * 3.280839895",
        "dependencies": ["LapDist"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, SPEED_RPM_PULL, DRAG_SCRUB, AERO_PLATFORM, SHOCKS, TIRES, ENGINE],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "lap_dist_pct_100": {
        "label": "Lap %",
        "description": "Lap distance as percentage (0-100)",
        "formula": "LapDistPct * 100",
        "dependencies": ["LapDistPct"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, SPEED_RPM_PULL, DRAG_SCRUB],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE", "FULL_THROTTLE_SPEED_LOSS", "STEERING_SCRUB", "DYNAMIC_PRESSURE_PEAK", "HIGH_CENTER_RAKE"],
        "used_by_recommendations": [],
    },

    # ── speed ──
    "speed_mph": {
        "label": "Speed",
        "description": "Vehicle speed in miles per hour",
        "formula": "Speed * 2.236936292",
        "dependencies": ["Speed"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, SPEED_RPM_PULL, DRAG_SCRUB, AERO_PLATFORM, TIRES, ENGINE],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE", "FULL_THROTTLE_SPEED_LOSS", "DYNAMIC_PRESSURE_PEAK", "RPM_FLATTENING"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, GEARING_COMPARISON, LINE_STEERING_REVIEW],
    },
    "speed_rate_mph_s": {
        "label": "Speed Rate",
        "description": "Rate of speed change in mph per second",
        "formula": "d(speed_mph) / d(SessionTime)",
        "dependencies": ["speed_mph", "SessionTime"],
        "used_by_charts": [SPEED_RPM_PULL, DRAG_SCRUB],
        "used_by_events": ["FULL_THROTTLE_SPEED_LOSS"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, LINE_STEERING_REVIEW],
    },
    "speed_rate_mph_1000ft": {
        "label": "Speed Rate / 1000 ft",
        "description": "Rate of speed change per 1000 feet of track distance",
        "formula": "d(speed_mph) / d(lap_dist_ft) * 1000",
        "dependencies": ["speed_mph", "lap_dist_ft"],
        "used_by_charts": [SPEED_RPM_PULL, DRAG_SCRUB],
        "used_by_events": ["FULL_THROTTLE_SPEED_LOSS"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, LINE_STEERING_REVIEW],
    },

    # ── ride heights ──
    "cfs_ride_height_in": {
        "label": "CFS Ride Height",
        "description": "Center front splitter ride height in inches",
        "formula": "CFSRrideHeight * 39.37007874",
        "dependencies": ["CFSRrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM, DRAG_SCRUB],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, RIDE_HEIGHT_REVIEW],
    },
    "cfs_ride_height_mm": {
        "label": "CFS Ride Height (mm)",
        "description": "Center front splitter ride height in millimeters",
        "formula": "CFSRrideHeight * 1000",
        "dependencies": ["CFSRrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, RIDE_HEIGHT_REVIEW],
    },
    "lf_ride_height_in": {
        "label": "LF Ride Height",
        "description": "Left-front ride height in inches",
        "dependencies": ["LFrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["PLATFORM_LOW"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rf_ride_height_in": {
        "label": "RF Ride Height",
        "description": "Right-front ride height in inches",
        "dependencies": ["RFrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["PLATFORM_LOW"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "lr_ride_height_in": {
        "label": "LR Ride Height",
        "description": "Left-rear ride height in inches",
        "dependencies": ["LRrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rr_ride_height_in": {
        "label": "RR Ride Height",
        "description": "Right-rear ride height in inches",
        "dependencies": ["RRrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── platform / rake ──
    "center_rake_fs_in": {
        "label": "Center Rake FS",
        "description": "Splitter-to-rear platform rake proxy: rear average ride height minus CFS ride height. Higher = rear higher than splitter. This is a ride-height-based rake proxy, not an axle-based rake measurement.",
        "formula": "rear_avg_rh_in - cfs_ride_height_in",
        "dependencies": ["lr_ride_height_in", "rr_ride_height_in", "cfs_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["HIGH_CENTER_RAKE", "PLATFORM_LOW"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, RIDE_HEIGHT_REVIEW, AERO_PLATFORM_CHECK],
    },
    "side_rake_in": {
        "label": "Side Rake",
        "description": "Side rake: right average minus left average. Positive = right side higher.",
        "formula": "right_avg_rh_in - left_avg_rh_in",
        "dependencies": ["lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "front_split_in": {
        "label": "Front Split",
        "description": "RF ride height minus LF ride height",
        "dependencies": ["rf_ride_height_in", "lf_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_split_in": {
        "label": "Rear Split",
        "description": "RR ride height minus LR ride height",
        "dependencies": ["rr_ride_height_in", "lr_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── dynamic pressure ──
    "dynamic_pressure_psf": {
        "label": "Dynamic Pressure",
        "description": "Dynamic pressure in pounds per square foot. Aero load scales with this value.",
        "formula": "0.5 * AirDensity * Speed^2 / 47.88025898",
        "dependencies": ["AirDensity", "Speed"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM, DRAG_SCRUB],
        "used_by_events": ["DYNAMIC_PRESSURE_PEAK", "MAX_DYNAMIC_PRESSURE"],
        "used_by_recommendations": [AERO_PLATFORM_CHECK, RIDE_HEIGHT_REVIEW],
    },
    "dynamic_pressure_lap_index": {
        "label": "Dynamic Pressure Lap Index",
        "description": "ESTIMATE — normalized dynamic pressure (0-1 scale relative to max in lap). LAP-RELATIVE index — NOT comparable across runs. Proxy, not absolute pressure.",
        "formula": "dynamic_pressure_psf / max(dynamic_pressure_psf in lap)",
        "dependencies": ["dynamic_pressure_psf"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["DYNAMIC_PRESSURE_PEAK"],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
        "comparable_across_runs": False,
    },
    "dynamic_pressure_index": {
        "label": "Dynamic Pressure Index",
        "description": "ESTIMATE — alias for dynamic_pressure_lap_index. LAP-RELATIVE — NOT comparable across runs. Normalized proxy, not absolute pressure.",
        "formula": "dynamic_pressure_psf / max(dynamic_pressure_psf in lap)",
        "dependencies": ["dynamic_pressure_psf"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["DYNAMIC_PRESSURE_PEAK"],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
        "comparable_across_runs": False,
    },
    "aero_load_index": {
        "label": "Aero Load Index",
        "description": "ESTIMATE — cross-run comparable aero load index. Ratio of current dynamic pressure to reference pressure at 180 mph sea level. Proxy — not a direct force measurement. Safe for Notebook comparisons across runs, tracks, weather, and sessions.",
        "formula": "dynamic_pressure_pa / REFERENCE_DYNAMIC_PRESSURE_PA",
        "dependencies": ["dynamic_pressure_pa"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
        "comparable_across_runs": True,
    },
    "aero_load_index_180mph": {
        "label": "Aero Load Index (180 mph ref)",
        "description": "ESTIMATE — alias for aero_load_index. Cross-run comparable. Proxy — not a direct force measurement.",
        "formula": "dynamic_pressure_pa / (0.5 * 1.225 * 80.4672^2)",
        "dependencies": ["dynamic_pressure_pa"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
        "comparable_across_runs": True,
    },

    # ── risk / suspicion ──
    "cfs_risk_score": {
        "label": "CFS Risk Score",
        "description": "ESTIMATE — splitter contact risk score from ride height. 1.0 = scrape, 0.92 = critical (<3mm), 0.72 = high (<6mm), 0.38 = watch (<10mm), 0.08 = safe. Proxy — not a direct contact sensor.",
        "formula": "piecewise from cfs_ride_height_mm",
        "dependencies": ["cfs_ride_height_mm"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, RIDE_HEIGHT_REVIEW],
    },
    "drag_scrub_suspicion": {
        "label": "Drag/Scrub Suspicion",
        "description": "Composite score estimating whether speed loss is from drag/scrub/resistance. NOT a direct force measurement.",
        "formula": "resistance*0.45 + cfs_risk*0.25 + steering_scrub*0.2 + yaw_rate*0.1",
        "dependencies": ["full_throttle_resistance_index", "cfs_risk_score", "abs_steering_deg", "yaw_rate"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["FULL_THROTTLE_SPEED_LOSS", "STEERING_SCRUB"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, LINE_STEERING_REVIEW],
    },
    "platform_compression_index": {
        "label": "Platform Compression Index",
        "description": "Composite of CFS risk, platform stability, and drag suspicion. Estimate only.",
        "formula": "cfs_risk*0.4 + plat_stability*0.3 + drag_suspicion*0.3",
        "dependencies": ["cfs_risk_score", "platform_stability_score", "drag_scrub_suspicion"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["PLATFORM_COMPRESSION"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST],
    },

    # ── force proxies ──
    "rear_downforce_proxy_n": {
        "label": "Rear Downforce Proxy",
        "description": "ESTIMATE — rear aero load derived from spring rates, ride heights, and dynamic pressure. Not a direct iRacing force channel.",
        "formula": "rear_load_proxy - mechanical_transfer - bump_oscillation (estimate)",
        "dependencies": ["lr_spring_rate", "rr_spring_rate", "lr_ride_height_mm", "rr_ride_height_mm"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK, RIDE_HEIGHT_REVIEW],
    },
    "rear_platform_proxy_n": {
        "label": "Rear Platform Proxy",
        "description": "ESTIMATE — rear platform load proxy. Compare runs, do not treat as absolute force.",
        "dependencies": ["lr_spring_rate", "rr_spring_rate", "lr_ride_height_mm", "rr_ride_height_mm"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
    },
    "aero_balance_front_pct": {
        "label": "Aero Balance Front %",
        "description": "ESTIMATE — front aero load as percentage of total estimated aero load.",
        "formula": "front_aero_proxy / (front_aero_proxy + rear_aero_proxy) * 100",
        "dependencies": ["front_aero_proxy_n", "rear_aero_proxy_n"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
    },

    # ── shock / damper ──
    "shock_velocity_rms": {
        "label": "Shock Velocity RMS",
        "description": "Rolling RMS of four-corner shock velocities. Higher = more platform disturbance.",
        "formula": "mean(sqrt(mean(shock_vel^2) over corners))",
        "dependencies": ["lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "shock_activity_index": {
        "label": "Shock Activity Index",
        "description": "ESTIMATE — composite shock activity score from velocity magnitude and peaks. Proxy for damper activity, not a direct measurement.",
        "dependencies": ["lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },

    # ── tire / wheel ──
    "driven_wheel_slip_proxy": {
        "label": "Driven Wheel Slip Proxy",
        "description": "ESTIMATE — rear wheel speed deviation from vehicle speed. Proxy, not exact slip.",
        "formula": "((LRspeed + RRspeed) / 2 - Speed) / Speed",
        "dependencies": ["LRspeed", "RRspeed", "Speed"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },

    # ── tire derived (pressure gain, temp spread, wear spread) ──
    "lf_pressure_gain": {
        "label": "LF Pressure Gain",
        "description": "ESTIMATE — left-front tire pressure gain (current minus cold). Proxy for tire temperature build-up.",
        "formula": "lf_pressure - lf_cold_pressure",
        "dependencies": ["lf_pressure", "lf_cold_pressure"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LONG_RUN_TIRE_REVIEW],
    },
    "rf_pressure_gain": {
        "label": "RF Pressure Gain",
        "description": "ESTIMATE — right-front tire pressure gain.",
        "formula": "rf_pressure - rf_cold_pressure",
        "dependencies": ["rf_pressure", "rf_cold_pressure"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LONG_RUN_TIRE_REVIEW],
    },
    "lr_pressure_gain": {
        "label": "LR Pressure Gain",
        "description": "ESTIMATE — left-rear tire pressure gain.",
        "formula": "lr_pressure - lr_cold_pressure",
        "dependencies": ["lr_pressure", "lr_cold_pressure"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LONG_RUN_TIRE_REVIEW],
    },
    "rr_pressure_gain": {
        "label": "RR Pressure Gain",
        "description": "ESTIMATE — right-rear tire pressure gain.",
        "formula": "rr_pressure - rr_cold_pressure",
        "dependencies": ["rr_pressure", "rr_cold_pressure"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LONG_RUN_TIRE_REVIEW],
    },
    "lf_temp_spread": {
        "label": "LF Temp Spread",
        "description": "ESTIMATE — left-front tire temperature spread (max minus min across inner/middle/outer). Proxy for uneven tire loading.",
        "formula": "max(lf_temp_inner, lf_temp_middle, lf_temp_outer) - min(...)",
        "dependencies": ["lf_temp_inner", "lf_temp_middle", "lf_temp_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rf_temp_spread": {
        "label": "RF Temp Spread",
        "description": "ESTIMATE — right-front tire temperature spread.",
        "formula": "max(rf_temp_inner, rf_temp_middle, rf_temp_outer) - min(...)",
        "dependencies": ["rf_temp_inner", "rf_temp_middle", "rf_temp_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "lr_temp_spread": {
        "label": "LR Temp Spread",
        "description": "ESTIMATE — left-rear tire temperature spread.",
        "formula": "max(lr_temp_inner, lr_temp_middle, lr_temp_outer) - min(...)",
        "dependencies": ["lr_temp_inner", "lr_temp_middle", "lr_temp_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rr_temp_spread": {
        "label": "RR Temp Spread",
        "description": "ESTIMATE — right-rear tire temperature spread.",
        "formula": "max(rr_temp_inner, rr_temp_middle, rr_temp_outer) - min(...)",
        "dependencies": ["rr_temp_inner", "rr_temp_middle", "rr_temp_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "lf_wear_spread": {
        "label": "LF Wear Spread",
        "description": "ESTIMATE — left-front tire wear spread (max minus min across inner/middle/outer). Proxy for uneven wear or alignment issues.",
        "formula": "max(lf_wear_inner, lf_wear_middle, lf_wear_outer) - min(...)",
        "dependencies": ["lf_wear_inner", "lf_wear_middle", "lf_wear_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rf_wear_spread": {
        "label": "RF Wear Spread",
        "description": "ESTIMATE — right-front tire wear spread.",
        "formula": "max(rf_wear_inner, rf_wear_middle, rf_wear_outer) - min(...)",
        "dependencies": ["rf_wear_inner", "rf_wear_middle", "rf_wear_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "lr_wear_spread": {
        "label": "LR Wear Spread",
        "description": "ESTIMATE — left-rear tire wear spread.",
        "formula": "max(lr_wear_inner, lr_wear_middle, lr_wear_outer) - min(...)",
        "dependencies": ["lr_wear_inner", "lr_wear_middle", "lr_wear_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rr_wear_spread": {
        "label": "RR Wear Spread",
        "description": "ESTIMATE — right-rear tire wear spread.",
        "formula": "max(rr_wear_inner, rr_wear_middle, rr_wear_outer) - min(...)",
        "dependencies": ["rr_wear_inner", "rr_wear_middle", "rr_wear_outer"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },

    # ── inputs ──
    "throttle_pct": {
        "label": "Throttle",
        "description": "Throttle position as percentage",
        "dependencies": ["Throttle"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, SPEED_RPM_PULL, DRAG_SCRUB, ENGINE],
        "used_by_events": ["FULL_THROTTLE_SPEED_LOSS", "RPM_FLATTENING"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, LINE_STEERING_REVIEW],
    },
    "brake_pct": {
        "label": "Brake",
        "description": "Brake position as percentage",
        "dependencies": ["Brake"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, SPEED_RPM_PULL, DRAG_SCRUB],
        "used_by_events": ["FULL_THROTTLE_SPEED_LOSS"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST, LINE_STEERING_REVIEW],
    },
    "steering_deg": {
        "label": "Steering Angle",
        "description": "Steering wheel angle in degrees",
        "dependencies": ["SteeringWheelAngle"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "abs_steering_deg": {
        "label": "|Steering Angle|",
        "description": "Absolute steering wheel angle in degrees",
        "formula": "abs(steering_deg)",
        "dependencies": ["steering_deg"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rpm": {
        "label": "RPM",
        "description": "Engine RPM",
        "dependencies": ["RPM"],
        "used_by_charts": [SPEED_RPM_PULL, ENGINE],
        "used_by_events": ["RPM_FLATTENING"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },
    "gear": {
        "label": "Gear",
        "description": "Current gear number",
        "dependencies": ["Gear"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [GEARING_COMPARISON],
    },

    # ── lat/long accel ──
    "lat_accel": {
        "label": "Lateral Accel",
        "description": "Lateral acceleration in m/s²",
        "dependencies": ["LatAccel"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "abs_lat_accel": {
        "label": "|Lateral Accel|",
        "description": "Absolute lateral acceleration",
        "dependencies": ["LatAccel"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },

    # ── platform angles ──
    "platform_pitch_deg_from_rh": {
        "label": "Platform Pitch (from RH)",
        "description": "ESTIMATE — platform pitch angle derived from front/rear ride height difference. Assumes 1:1 motion ratio unless setup data provides it. Delegates to geometry.compute_pitch_deg().",
        "formula": "geometry.compute_pitch_deg(front_rh_m, rear_rh_m, wheelbase_m)",
        "dependencies": ["front_avg_rh_in", "rear_avg_rh_in", "wheelbase_m"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "platform_roll_deg_from_rh": {
        "label": "Platform Roll (from RH)",
        "description": "ESTIMATE — platform roll angle derived from left/right ride height difference. Assumes 1:1 motion ratio unless setup data provides it. Delegates to geometry.compute_roll_deg().",
        "formula": "geometry.compute_roll_deg(left_rh_m, right_rh_m, track_width_m)",
        "dependencies": ["left_avg_rh_in", "right_avg_rh_in", "front_track_width_m"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── dynamic pressure raw ──
    "dynamic_pressure_pa": {
        "label": "Dynamic Pressure (Pa)",
        "description": "Dynamic pressure in Pascals. Raw SI value before conversion to psf.",
        "formula": "0.5 * AirDensity * Speed^2",
        "dependencies": ["AirDensity", "Speed"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [],
    },

    # ── slip ratios ──
    "lf_slip_ratio": {
        "label": "LF Slip Ratio",
        "description": "Left-front wheel slip ratio from raw wheel speed vs vehicle speed.",
        "dependencies": ["LFspeed", "speed_mps"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rf_slip_ratio": {
        "label": "RF Slip Ratio",
        "description": "Right-front wheel slip ratio from raw wheel speed vs vehicle speed.",
        "dependencies": ["RFspeed", "speed_mps"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "lr_slip_ratio": {
        "label": "LR Slip Ratio",
        "description": "Left-rear wheel slip ratio from raw wheel speed vs vehicle speed.",
        "dependencies": ["LRspeed", "speed_mps"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },
    "rr_slip_ratio": {
        "label": "RR Slip Ratio",
        "description": "Right-rear wheel slip ratio from raw wheel speed vs vehicle speed.",
        "dependencies": ["RRspeed", "speed_mps"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },

    # ── wheel speed mismatch ──
    "front_wheel_speed_mismatch": {
        "label": "Front Wheel Speed Mismatch",
        "description": "Difference between RF and LF wheel speeds. Indicates steering scrub or inside wheel slip.",
        "dependencies": ["RFspeed", "LFspeed"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rear_wheel_speed_mismatch": {
        "label": "Rear Wheel Speed Mismatch",
        "description": "Difference between RR and LR wheel speeds. Indicates inside wheel spin or differential action.",
        "dependencies": ["RRspeed", "LRspeed"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },

    # ── ride height mm variants ──
    "lf_ride_height_mm": {
        "label": "LF Ride Height (mm)",
        "description": "Left-front ride height in millimeters",
        "dependencies": ["LFrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": ["PLATFORM_LOW"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rf_ride_height_mm": {
        "label": "RF Ride Height (mm)",
        "description": "Right-front ride height in millimeters",
        "dependencies": ["RFrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": ["PLATFORM_LOW"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "lr_ride_height_mm": {
        "label": "LR Ride Height (mm)",
        "description": "Left-rear ride height in millimeters",
        "dependencies": ["LRrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rr_ride_height_mm": {
        "label": "RR Ride Height (mm)",
        "description": "Right-rear ride height in millimeters",
        "dependencies": ["RRrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── ride height averages ──
    "front_avg_rh_in": {
        "label": "Front Avg RH",
        "description": "Average front ride height (LF + RF) / 2 in inches",
        "dependencies": ["lf_ride_height_in", "rf_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_avg_rh_in": {
        "label": "Rear Avg RH",
        "description": "Average rear ride height (LR + RR) / 2 in inches",
        "dependencies": ["lr_ride_height_in", "rr_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "left_avg_rh_in": {
        "label": "Left Avg RH",
        "description": "Average left ride height (LF + LR) / 2 in inches",
        "dependencies": ["lf_ride_height_in", "lr_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "right_avg_rh_in": {
        "label": "Right Avg RH",
        "description": "Average right ride height (RF + RR) / 2 in inches",
        "dependencies": ["rf_ride_height_in", "rr_ride_height_in"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── shock mm variants ──
    "lf_shock_defl_in": {
        "label": "LF Shock Deflection",
        "description": "Left-front shock deflection in inches",
        "dependencies": ["LFSHshockDefl"],
        "used_by_charts": [SHOCKS],
        "used_by_events": [],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rf_shock_defl_in": {
        "label": "RF Shock Deflection",
        "description": "Right-front shock deflection in inches",
        "dependencies": ["RFSHshockDefl"],
        "used_by_charts": [SHOCKS],
        "used_by_events": [],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lr_shock_defl_in": {
        "label": "LR Shock Deflection",
        "description": "Left-rear shock deflection in inches",
        "dependencies": ["LRSHshockDefl"],
        "used_by_charts": [SHOCKS],
        "used_by_events": [],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rr_shock_defl_in": {
        "label": "RR Shock Deflection",
        "description": "Right-rear shock deflection in inches",
        "dependencies": ["RRSHshockDefl"],
        "used_by_charts": [SHOCKS],
        "used_by_events": [],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lf_shock_vel_in_s": {
        "label": "LF Shock Velocity",
        "description": "Left-front shock velocity in inches per second",
        "dependencies": ["LFSHshockVel"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rf_shock_vel_in_s": {
        "label": "RF Shock Velocity",
        "description": "Right-front shock velocity in inches per second",
        "dependencies": ["RFSHshockVel"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lr_shock_vel_in_s": {
        "label": "LR Shock Velocity",
        "description": "Left-rear shock velocity in inches per second",
        "dependencies": ["LRSHshockVel"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rr_shock_vel_in_s": {
        "label": "RR Shock Velocity",
        "description": "Right-rear shock velocity in inches per second",
        "dependencies": ["RRSHshockVel"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },

    # ── stability scores ──
    "platform_stability_score": {
        "label": "Platform Stability",
        "description": "ESTIMATE — rate of CFS ride height change over time. Higher = less stable platform. Proxy — ride-height-based, not inertial.",
        "dependencies": ["cfs_ride_height_in", "session_time"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["PLATFORM_COMPRESSION"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST],
    },
    "rake_stability_score": {
        "label": "Rake Stability",
        "description": "ESTIMATE — rate of center rake change over time. Higher = less stable rake. Proxy — ride-height-based, not inertial.",
        "dependencies": ["center_rake_fs_in", "session_time"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "platform_risk_score": {
        "label": "Platform Risk Score",
        "description": "ESTIMATE — alias for CFS risk score. Higher = riskier splitter margin. Proxy — not a direct contact sensor.",
        "dependencies": ["cfs_ride_height_mm"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["PLATFORM_LOW"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST],
    },

    # ── scrub proxies ──
    "front_scrub_proxy": {
        "label": "Front Scrub Proxy",
        "description": "ESTIMATE — front scrub/scrub index from slip mismatch, steering, yaw error, and curvature.",
        "dependencies": ["lf_slip_ratio", "rf_slip_ratio", "abs_steering_deg", "abs_lat_accel", "yaw_rate", "radius_m"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rear_scrub_proxy": {
        "label": "Rear Scrub Proxy",
        "description": "ESTIMATE — rear scrub index from rear slip mismatch.",
        "dependencies": ["lr_slip_ratio", "rr_slip_ratio"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },
    "yaw_error_proxy": {
        "label": "Yaw Error Proxy",
        "description": "ESTIMATE — yaw error from curvature vs actual yaw rate. max(0, theoretical_yaw - actual_yaw). Positive = understeer. Used internally by front_scrub_proxy.",
        "formula": "max(0, speed_mps / radius_m - abs(yaw_rate))",
        "dependencies": ["speed_mps", "radius_m", "yaw_rate"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "full_throttle_resistance_index": {
        "label": "Full-Throttle Resistance",
        "description": "ESTIMATE — aero-normalized resistance index during full-throttle conditions. Higher = more drag/scrub per unit aero load.",
        "dependencies": ["speed_mph", "throttle_pct", "brake_pct", "speed_rate_mph_s", "dynamic_pressure_psf"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": ["FULL_THROTTLE_SPEED_LOSS"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST],
    },
    "damper_energy_proxy": {
        "label": "Damper Energy Proxy",
        "description": "ESTIMATE — trailing-window sum of squared shock velocities. Proxy for damper energy dissipation.",
        "dependencies": ["lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "damper_work_proxy": {
        "label": "Damper Work Proxy",
        "description": "ESTIMATE — alias for damper energy proxy.",
        "dependencies": ["lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": [],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },

    # ── force proxies ──
    "front_load_proxy_n": {
        "label": "Front Load Proxy",
        "description": "ESTIMATE — front total load proxy from spring rates and ride height deltas.",
        "dependencies": ["lf_ride_height_mm", "rf_ride_height_mm"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
    },
    "rear_load_proxy_n": {
        "label": "Rear Load Proxy",
        "description": "ESTIMATE — rear total load proxy from spring rates and ride height deltas.",
        "dependencies": ["lr_ride_height_mm", "rr_ride_height_mm"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
    },
    "front_aero_proxy_n": {
        "label": "Front Aero Proxy",
        "description": "ESTIMATE — front aero load proxy. Not a direct force measurement.",
        "dependencies": ["front_load_proxy_n"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
    },
    "rear_aero_proxy_n": {
        "label": "Rear Aero Proxy",
        "description": "ESTIMATE — rear aero load proxy. Not a direct force measurement.",
        "dependencies": ["rear_load_proxy_n"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
    },
    "rear_diffuser_proxy_n": {
        "label": "Rear Diffuser Proxy",
        "description": "ESTIMATE — rear diffuser load proxy. Very low confidence. Not a direct force measurement.",
        "dependencies": ["rear_load_proxy_n"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
    },

    # ── speed_fps ──
    "speed_fps": {
        "label": "Speed (ft/s)",
        "description": "Vehicle speed in feet per second",
        "formula": "Speed * 3.280839895",
        "dependencies": ["Speed"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [],
    },

    # ── cfsr_height_mm (alias) ──
    "cfsr_height_mm": {
        "label": "CFS Ride Height (mm, raw alias)",
        "description": "Alias for cfs_ride_height_mm from raw CFSRrideHeight channel.",
        "formula": "CFSRrideHeight * 1000",
        "dependencies": ["CFSRrideHeight"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── slip angles ──
    "front_slip_angle_deg": {
        "label": "Front Slip Angle",
        "description": "ESTIMATE — kinematic front tire slip angle from steering, yaw rate, and local velocity. Requires axle-to-CG distance from setup constants.",
        "formula": "tire_dynamics.front_slip_angle_rad(steer, vx, vy, r, a)",
        "dependencies": ["velocity_z", "velocity_x", "yaw_rate", "steering_rad", "front_axle_to_cg_m"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rear_slip_angle_deg": {
        "label": "Rear Slip Angle",
        "description": "ESTIMATE — kinematic rear tire slip angle from yaw rate and local velocity. Requires axle-to-CG distance from setup constants.",
        "formula": "tire_dynamics.rear_slip_angle_rad(vx, vy, r, b)",
        "dependencies": ["velocity_z", "velocity_x", "yaw_rate", "rear_axle_to_cg_m"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "slip_angle_balance_deg": {
        "label": "Slip Angle Balance",
        "description": "ESTIMATE — difference between front and rear slip angles (front - rear). Positive = understeer bias, negative = oversteer bias.",
        "formula": "tire_dynamics.slip_angle_balance_rad(af, ar)",
        "dependencies": ["front_slip_angle_deg", "rear_slip_angle_deg"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },

    # ── dynamic grade ──
    "speed_rate_mps2": {
        "label": "Speed Rate (m/s²)",
        "description": "Rate of speed change in SI units (m/s²). Used for dynamic grade isolation and force balance calculations.",
        "formula": "d(speed_mps) / d(SessionTime)",
        "dependencies": ["speed_mps", "SessionTime"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "dynamic_grade_deg": {
        "label": "Dynamic Grade",
        "description": "ESTIMATE — track slope (grade) angle derived by comparing sensor longitudinal acceleration vs GPS speed derivative. Positive = uphill, negative = downhill. Not surveyed elevation.",
        "formula": "asin((long_accel - speed_rate_mps2) / 9.81)",
        "dependencies": ["long_accel", "speed_rate_mps2"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "dynamic_grade_rad": {
        "label": "Dynamic Grade (rad)",
        "description": "ESTIMATE — track slope in radians. SI unit version of dynamic_grade_deg. Not surveyed elevation.",
        "formula": "asin((long_accel - speed_rate_mps2) / 9.81)",
        "dependencies": ["long_accel", "speed_rate_mps2"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "grade_corrected_long_accel_mps2": {
        "label": "Grade-Corrected Long Accel",
        "description": "ESTIMATE — longitudinal acceleration with estimated grade component removed. a_corrected = a_sensor - g * sin(grade). Confidence depends on clean acceleration and speed derivative.",
        "formula": "long_accel - 9.81 * sin(dynamic_grade_rad)",
        "dependencies": ["long_accel", "speed_rate_mps2"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "grade_force_proxy_n": {
        "label": "Grade Force Proxy",
        "description": "ESTIMATE — grade-induced force component. Positive = uphill resistance, negative = downhill assist. Requires mass_kg; returns None if mass unavailable. Proxy — not a direct force measurement.",
        "formula": "mass_kg * 9.81 * sin(dynamic_grade_rad)",
        "dependencies": ["mass_kg", "long_accel", "speed_rate_mps2"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "grade_context_label": {
        "label": "Grade Context",
        "description": "ESTIMATE — qualitative grade classification: uphill, downhill, flat, or unknown. Based on dynamic_grade_deg with a small deadband around zero. Not surveyed elevation.",
        "formula": "classification from dynamic_grade_deg",
        "dependencies": ["dynamic_grade_deg"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "grade_corrected_speed_loss_mph_s": {
        "label": "Grade-Corrected Speed Loss",
        "description": "ESTIMATE — speed_rate_mph_s with grade-induced acceleration removed. Positive = true speed loss (aero/mechanical), negative = true speed gain. Raw speed_rate_mph_s is preserved. Proxy — grade is inferred, not measured.",
        "formula": "speed_rate_mph_s - grade_accel_mph_s",
        "dependencies": ["speed_rate_mph_s", "dynamic_grade_rad"],
        "used_by_charts": [SPEED_RPM_PULL, DRAG_SCRUB],
        "used_by_events": [],
        "used_by_recommendations": [],
    },

    # ── Ackermann steering ──
    "ackermann_steering_expected_deg": {
        "label": "Ackermann Steering Expected",
        "description": "ESTIMATE — expected steering angle from Ackermann geometry: atan(wheelbase * curvature). Bicycle model, no steering ratio. Positive = left, negative = right.",
        "formula": "atan(wheelbase_m * curvature_1_per_m)",
        "dependencies": ["wheelbase_m", "curvature_1_per_m"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "ackermann_steering_error_deg": {
        "label": "Ackermann Steering Error",
        "description": "ESTIMATE — |actual_steering| - |expected_ackermann|. Positive = more steering than geometry predicts (understeer or extra input). Negative = less steering (oversteer or reduced input).",
        "formula": "abs(steering_deg) - abs(ackermann_steering_expected_deg)",
        "dependencies": ["steering_deg", "ackermann_steering_expected_deg"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "ackermann_scrub_proxy": {
        "label": "Ackermann Scrub Proxy",
        "description": "ESTIMATE — scrub proxy from Ackermann error. clamp01(max(0, error) / 5°). Extra steering beyond Ackermann suggests scrub. Does NOT replace front_scrub_proxy.",
        "formula": "clamp01(max(0, ackermann_steering_error_deg) / 5.0)",
        "dependencies": ["ackermann_steering_error_deg"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },

    # ── front/rear platform roll ──
    "front_platform_roll_deg_from_rh": {
        "label": "Front Platform Roll (from RH)",
        "description": "ESTIMATE — front axle roll angle from LF/RF ride height difference using front track width and front motion ratio. Not a direct chassis attitude measurement.",
        "formula": "compute_roll_deg(lf_rh_m, rf_rh_m, front_track_width_m, front_motion_ratio)",
        "dependencies": ["lf_ride_height_mm", "rf_ride_height_mm", "front_track_width_m"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_platform_roll_deg_from_rh": {
        "label": "Rear Platform Roll (from RH)",
        "description": "ESTIMATE — rear axle roll angle from LR/RR ride height difference using rear track width and rear motion ratio. Not a direct chassis attitude measurement.",
        "formula": "compute_roll_deg(lr_rh_m, rr_rh_m, rear_track_width_m, rear_motion_ratio)",
        "dependencies": ["lr_ride_height_mm", "rr_ride_height_mm", "rear_track_width_m"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "platform_roll_balance_deg": {
        "label": "Platform Roll Balance",
        "description": "ESTIMATE — front roll minus rear roll. Positive = front rolls more than rear (more front grip or softer front roll stiffness). Negative = rear rolls more.",
        "formula": "front_platform_roll_deg_from_rh - rear_platform_roll_deg_from_rh",
        "dependencies": ["front_platform_roll_deg_from_rh", "rear_platform_roll_deg_from_rh"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── camber heat spread proxy ──
    "lf_camber_temp_bias_c": {
        "label": "LF Camber Temp Bias",
        "description": "ESTIMATE — left-front inner minus outer carcass temperature. Positive = inside hotter (too much negative camber or cornering load). Proxy — not a direct camber measurement.",
        "formula": "lf_carcass_temp_l - lf_carcass_temp_r",
        "dependencies": ["lf_carcass_temp_l", "lf_carcass_temp_r"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rf_camber_temp_bias_c": {
        "label": "RF Camber Temp Bias",
        "description": "ESTIMATE — right-front inner minus outer carcass temperature.",
        "formula": "rf_carcass_temp_l - rf_carcass_temp_r",
        "dependencies": ["rf_carcass_temp_l", "rf_carcass_temp_r"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "lr_camber_temp_bias_c": {
        "label": "LR Camber Temp Bias",
        "description": "ESTIMATE — left-rear inner minus outer carcass temperature.",
        "formula": "lr_carcass_temp_l - lr_carcass_temp_r",
        "dependencies": ["lr_carcass_temp_l", "lr_carcass_temp_r"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rr_camber_temp_bias_c": {
        "label": "RR Camber Temp Bias",
        "description": "ESTIMATE — right-rear inner minus outer carcass temperature.",
        "formula": "rr_carcass_temp_l - rr_carcass_temp_r",
        "dependencies": ["rr_carcass_temp_l", "rr_carcass_temp_r"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "lf_camber_bias_label": {
        "label": "LF Camber Bias Label",
        "description": "ESTIMATE — qualitative camber bias: high_inside, high_outside, even, or unknown.",
        "formula": "classification from lf_camber_temp_bias_c",
        "dependencies": ["lf_camber_temp_bias_c"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rf_camber_bias_label": {
        "label": "RF Camber Bias Label",
        "description": "ESTIMATE — qualitative camber bias for right-front.",
        "formula": "classification from rf_camber_temp_bias_c",
        "dependencies": ["rf_camber_temp_bias_c"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "lr_camber_bias_label": {
        "label": "LR Camber Bias Label",
        "description": "ESTIMATE — qualitative camber bias for left-rear.",
        "formula": "classification from lr_camber_temp_bias_c",
        "dependencies": ["lr_camber_temp_bias_c"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rr_camber_bias_label": {
        "label": "RR Camber Bias Label",
        "description": "ESTIMATE — qualitative camber bias for right-rear.",
        "formula": "classification from rr_camber_temp_bias_c",
        "dependencies": ["rr_camber_temp_bias_c"],
        "used_by_charts": [TIRES],
        "used_by_events": [],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },

    # ── track GPS projection ──
    "track_x_m": {
        "label": "Track X (m)",
        "description": "GPS-projected track X position in meters from local origin.",
        "dependencies": ["Lat", "Lon"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "track_y_m": {
        "label": "Track Y (m)",
        "description": "GPS-projected track Y position in meters from local origin.",
        "dependencies": ["Lat", "Lon"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "track_x_ft": {
        "label": "Track X (ft)",
        "description": "GPS-projected track X position in feet.",
        "dependencies": ["track_x_m"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "track_y_ft": {
        "label": "Track Y (ft)",
        "description": "GPS-projected track Y position in feet.",
        "dependencies": ["track_y_m"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },

    # ── g-values ──
    "lat_accel_g": {
        "label": "Lateral Accel (g)",
        "description": "Lateral acceleration in g units.",
        "formula": "lat_accel / 9.81",
        "dependencies": ["lat_accel"],
        "used_by_charts": [DRAG_SCRUB],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "long_accel_g": {
        "label": "Longitudinal Accel (g)",
        "description": "Longitudinal acceleration in g units.",
        "formula": "long_accel / 9.81",
        "dependencies": ["long_accel"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [],
    },
    "vert_accel_g": {
        "label": "Vertical Accel (g)",
        "description": "Vertical acceleration in g units.",
        "formula": "vert_accel / 9.81",
        "dependencies": ["vert_accel"],
        "used_by_charts": [],
        "used_by_events": [],
        "used_by_recommendations": [],
    },

    # ── wheel speed mismatch raw/corrected ──
    "front_wheel_speed_mismatch_raw": {
        "label": "Front Wheel Speed Mismatch (raw)",
        "description": "Raw difference between RF and LF wheel speeds. Indicates steering scrub or inside wheel slip.",
        "formula": "RFspeed - LFspeed",
        "dependencies": ["RFspeed", "LFspeed"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rear_wheel_speed_mismatch_raw": {
        "label": "Rear Wheel Speed Mismatch (raw)",
        "description": "Raw difference between RR and LR wheel speeds.",
        "formula": "RRspeed - LRspeed",
        "dependencies": ["RRspeed", "LRspeed"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },
    "front_wheel_speed_mismatch_corrected": {
        "label": "Front Wheel Speed Mismatch (corrected)",
        "description": "Geometry-corrected front wheel speed mismatch accounting for yaw rate and track width.",
        "formula": "(RFspeed - LFspeed) - (yaw_rate * front_track_width_m)",
        "dependencies": ["RFspeed", "LFspeed", "yaw_rate", "front_track_width_m"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["STEERING_SCRUB"],
        "used_by_recommendations": [LINE_STEERING_REVIEW],
    },
    "rear_wheel_speed_mismatch_corrected": {
        "label": "Rear Wheel Speed Mismatch (corrected)",
        "description": "Geometry-corrected rear wheel speed mismatch accounting for yaw rate and track width.",
        "formula": "(RRspeed - LRspeed) - (yaw_rate * rear_track_width_m)",
        "dependencies": ["RRspeed", "LRspeed", "yaw_rate", "rear_track_width_m"],
        "used_by_charts": [TIRES, DRAG_SCRUB],
        "used_by_events": ["TIRE_SCRUB"],
        "used_by_recommendations": [GEARING_COMPARISON],
    },

    # ── per-corner shock rolling aggregates ──
    "lf_shock_velocity_rms": {
        "label": "LF Shock Velocity RMS",
        "description": "Rolling RMS of left-front shock velocity. Higher = more platform disturbance at LF corner.",
        "formula": "rolling sqrt(mean(lf_shock_vel_in_s^2))",
        "dependencies": ["lf_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rf_shock_velocity_rms": {
        "label": "RF Shock Velocity RMS",
        "description": "Rolling RMS of right-front shock velocity.",
        "formula": "rolling sqrt(mean(rf_shock_vel_in_s^2))",
        "dependencies": ["rf_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lr_shock_velocity_rms": {
        "label": "LR Shock Velocity RMS",
        "description": "Rolling RMS of left-rear shock velocity.",
        "formula": "rolling sqrt(mean(lr_shock_vel_in_s^2))",
        "dependencies": ["lr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rr_shock_velocity_rms": {
        "label": "RR Shock Velocity RMS",
        "description": "Rolling RMS of right-rear shock velocity.",
        "formula": "rolling sqrt(mean(rr_shock_vel_in_s^2))",
        "dependencies": ["rr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lf_shock_activity_index": {
        "label": "LF Shock Activity Index",
        "description": "Composite shock activity score for left-front corner from velocity magnitude and peaks.",
        "formula": "mean(abs(sv)) + max(abs(sv)) * 0.3",
        "dependencies": ["lf_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rf_shock_activity_index": {
        "label": "RF Shock Activity Index",
        "description": "Composite shock activity score for right-front corner.",
        "formula": "mean(abs(sv)) + max(abs(sv)) * 0.3",
        "dependencies": ["rf_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lr_shock_activity_index": {
        "label": "LR Shock Activity Index",
        "description": "Composite shock activity score for left-rear corner.",
        "formula": "mean(abs(sv)) + max(abs(sv)) * 0.3",
        "dependencies": ["lr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rr_shock_activity_index": {
        "label": "RR Shock Activity Index",
        "description": "Composite shock activity score for right-rear corner.",
        "formula": "mean(abs(sv)) + max(abs(sv)) * 0.3",
        "dependencies": ["rr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lf_damper_energy_proxy": {
        "label": "LF Damper Energy Proxy",
        "description": "ESTIMATE — trailing-window sum of squared LF shock velocities. Proxy for damper energy dissipation.",
        "formula": "rolling sum(lf_shock_vel_in_s^2)",
        "dependencies": ["lf_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rf_damper_energy_proxy": {
        "label": "RF Damper Energy Proxy",
        "description": "ESTIMATE — trailing-window sum of squared RF shock velocities.",
        "formula": "rolling sum(rf_shock_vel_in_s^2)",
        "dependencies": ["rf_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "lr_damper_energy_proxy": {
        "label": "LR Damper Energy Proxy",
        "description": "ESTIMATE — trailing-window sum of squared LR shock velocities.",
        "formula": "rolling sum(lr_shock_vel_in_s^2)",
        "dependencies": ["lr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },
    "rr_damper_energy_proxy": {
        "label": "RR Damper Energy Proxy",
        "description": "ESTIMATE — trailing-window sum of squared RR shock velocities.",
        "formula": "rolling sum(rr_shock_vel_in_s^2)",
        "dependencies": ["rr_shock_vel_in_s"],
        "used_by_charts": [SHOCKS],
        "used_by_events": ["SHOCK_ACTIVITY"],
        "used_by_recommendations": [SHOCK_STABILITY_REVIEW],
    },

    # ── rear scrape channels ──
    "rear_min_ride_height_mm": {
        "label": "Rear Min Ride Height",
        "description": "ESTIMATE — minimum rear ride height (LR vs RR) in millimeters. Proxy for rear platform ground clearance.",
        "formula": "min(lr_ride_height_mm, rr_ride_height_mm)",
        "dependencies": ["lr_ride_height_mm", "rr_ride_height_mm"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_min_ride_height_in": {
        "label": "Rear Min Ride Height (in)",
        "description": "ESTIMATE — minimum rear ride height in inches.",
        "formula": "rear_min_ride_height_mm * MM_TO_IN",
        "dependencies": ["rear_min_ride_height_mm"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_scrape_margin_mm": {
        "label": "Rear Scrape Margin",
        "description": "ESTIMATE — rear ground clearance margin in mm. Positive = clearance, zero/negative = contact risk.",
        "formula": "rear_min_ride_height_mm - REAR_SCRAPE_MM",
        "dependencies": ["rear_min_ride_height_mm"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_scrape_risk_score": {
        "label": "Rear Scrape Risk",
        "description": "ESTIMATE — rear platform contact risk score. 1.0 = scrape, 0.92 = critical (<3mm), 0.72 = high (<6mm), 0.38 = watch (<10mm), 0.08 = safe. Proxy — not a direct contact sensor.",
        "formula": "piecewise from rear_min_ride_height_mm",
        "dependencies": ["rear_min_ride_height_mm"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE", "REAR_CONTACT_RISK"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_platform_contact_risk": {
        "label": "Rear Platform Contact Risk",
        "description": "ESTIMATE — alias for rear_scrape_risk_score. Proxy for rear underbody contact risk.",
        "formula": "rear_scrape_risk_score",
        "dependencies": ["rear_scrape_risk_score"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE", "REAR_CONTACT_RISK"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_scrape_side": {
        "label": "Rear Scrape Side",
        "description": "ESTIMATE — which rear corner has lower ride height. -1 = left_rear, 0 = both_rear, 1 = right_rear, None = unavailable.",
        "formula": "-1 if lr < rr, 0 if equal, 1 if rr < lr",
        "dependencies": ["lr_ride_height_mm", "rr_ride_height_mm"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },

    # ── platform balance channels ──
    "front_platform_risk_score": {
        "label": "Front Platform Risk",
        "description": "ESTIMATE — alias for cfs_risk_score. Front platform contact risk for consistent front/rear comparison.",
        "formula": "cfs_risk_score",
        "dependencies": ["cfs_risk_score"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE", "WHOLE_CAR_BOTTOMING_RISK"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_platform_risk_score": {
        "label": "Rear Platform Risk",
        "description": "ESTIMATE — alias for rear_scrape_risk_score. Rear platform contact risk for consistent front/rear comparison.",
        "formula": "rear_scrape_risk_score",
        "dependencies": ["rear_scrape_risk_score"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE", "WHOLE_CAR_BOTTOMING_RISK"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "whole_car_bottoming_risk": {
        "label": "Whole-Car Bottoming Risk",
        "description": "ESTIMATE — combined front/rear bottoming risk. Higher when both front and rear platform risk are elevated. Proxy — not a direct contact sensor.",
        "formula": "min(front_platform_risk_score, rear_platform_risk_score)",
        "dependencies": ["front_platform_risk_score", "rear_platform_risk_score"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["WHOLE_CAR_BOTTOMING_RISK"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "platform_balance_label": {
        "label": "Platform Balance",
        "description": "Classification of platform balance: front_platform_risk, rear_platform_risk, whole_car_bottoming, balanced_safe, or unavailable.",
        "formula": "classification from cfs_risk_score and rear_scrape_risk_score",
        "dependencies": ["cfs_risk_score", "rear_scrape_risk_score"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE", "REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE", "WHOLE_CAR_BOTTOMING_RISK"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "platform_balance_explanation": {
        "label": "Platform Balance Explanation",
        "description": "Human-readable explanation of the current platform balance classification.",
        "formula": "derived from platform_balance_label",
        "dependencies": ["platform_balance_label"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT, AERO_PLATFORM],
        "used_by_events": ["PLATFORM_LOW", "PLATFORM_SCRAPE", "REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE", "WHOLE_CAR_BOTTOMING_RISK"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "rear_scrape_side_label": {
        "label": "Rear Scrape Side Label",
        "description": "Readable label for which rear corner is lower: left_rear, both_rear, right_rear, or None.",
        "formula": "map from rear_scrape_side",
        "dependencies": ["rear_scrape_side"],
        "used_by_charts": [PLATFORM_RAKE_RIDE_HEIGHT],
        "used_by_events": ["REAR_PLATFORM_LOW", "REAR_PLATFORM_SCRAPE"],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    # ── diffuser geometry (Roger's diffuser geometry math) ──
    "front_center_rh_in": {
        "label": "Front Center RH",
        "unit": "in",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Average front ride height: (rf_ride_height_in + lf_ride_height_in) / 2.",
        "formula": "(rf_ride_height_in + lf_ride_height_in) / 2",
        "dependencies": ["rf_ride_height_in", "lf_ride_height_in"],
    },
    "rear_center_rh_in": {
        "label": "Rear Center RH",
        "unit": "in",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Average rear ride height: (rr_ride_height_in + lr_height_rub_block_in) / 2 with 0.5 in rub-block correction on LR.",
        "formula": "(rr_ride_height_in + lr_ride_height_in - 0.5) / 2",
        "dependencies": ["rr_ride_height_in", "lr_ride_height_in"],
    },
    "lr_height_rub_block_in": {
        "label": "LR Height — Rub Block",
        "unit": "in",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Left-rear ride height with 0.5 in rub-block correction subtracted.",
        "formula": "lr_ride_height_in - 0.5",
        "dependencies": ["lr_ride_height_in"],
    },
    "center_rake_in": {
        "label": "Center Rake",
        "unit": "in",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Rake angle proxy: rear_center_rh_in - front_center_rh_in.",
        "formula": "rear_center_rh_in - front_center_rh_in",
        "dependencies": ["rear_center_rh_in", "front_center_rh_in"],
    },
    "smooth_center_rake_in": {
        "label": "Smooth Center Rake",
        "unit": "in",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Trailing/causal smooth of center_rake_in (window 20 samples).",
        "formula": "rolling smooth of center_rake_in, window 20",
        "dependencies": ["center_rake_in"],
    },
    "diffuser_track_width_in": {
        "label": "Diffuser Track Width Used",
        "unit": "in",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Resolved vehicle track width for diffuser calculation. Prefers rear_track_width_m from geometry; falls back to 79 in with assumption label.",
        "formula": "Resolved from geometry or fallback 79 in",
        "dependencies": ["rear_track_width_m", "front_track_width_m"],
    },
    "diffuser_wheelbase_in": {
        "label": "Diffuser Wheelbase Used",
        "unit": "in",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Resolved vehicle wheelbase for diffuser calculation. Prefers wheelbase_m from geometry; falls back to 110 in.",
        "formula": "Resolved from geometry or fallback 110 in",
        "dependencies": ["wheelbase_m"],
    },
    "diffuser_base_volume_ft3": {
        "label": "Diffuser Base Volume",
        "unit": "ft³",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Base diffuser volume: (front_center_rh_in * wheelbase_in * track_width_in) / 1728.",
        "formula": "(front_center_rh_in * diffuser_wheelbase_in * diffuser_track_width_in) / 1728",
        "dependencies": ["front_center_rh_in", "diffuser_wheelbase_in", "diffuser_track_width_in"],
    },
    "diffuser_wedge_volume_ft3": {
        "label": "Diffuser Wedge Volume",
        "unit": "ft³",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Wedge diffuser volume from rake delta and diagonal length.",
        "formula": "(track_width_in * rake_delta * sqrt(wb² + rake_delta²/2)) / 1728",
        "dependencies": ["diffuser_track_width_in", "diffuser_wheelbase_in", "front_center_rh_in", "rear_center_rh_in"],
    },
    "diffuser_volume_ft3": {
        "label": "Diffuser Volume",
        "unit": "ft³",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Total diffuser volume: base + wedge.",
        "formula": "diffuser_base_volume_ft3 + diffuser_wedge_volume_ft3",
        "dependencies": ["diffuser_base_volume_ft3", "diffuser_wedge_volume_ft3"],
    },
    "smooth_diffuser_volume_ft3": {
        "label": "Smooth Diffuser Volume",
        "unit": "ft³",
        "category": "diffuser",
        "source_nature": "derived",
        "precision": 2,
        "description": "Trailing/causal smooth of diffuser_volume_ft3 (window 20 samples).",
        "formula": "rolling smooth of diffuser_volume_ft3, window 20",
        "dependencies": ["diffuser_volume_ft3"],
    },
}


def channel_metadata(name: str) -> ChannelMetadata:
    """Return metadata for a channel, with sensible defaults for unregistered channels."""
    meta = CHANNEL_METADATA.get(name, {})
    return {
        "label": meta.get("label", name),
        "description": meta.get("description"),
        "formula": meta.get("formula"),
        "dependencies": meta.get("dependencies", []),
        "used_by_charts": meta.get("used_by_charts", []),
        "used_by_events": meta.get("used_by_events", []),
        "used_by_recommendations": meta.get("used_by_recommendations", []),
        "comparable_across_runs": meta.get("comparable_across_runs", True),
    }


def rows_from_table(table: Any) -> list[dict[str, Any]]:
    if table is None:
        return []
    if hasattr(table, "to_dicts"):
        return [dict(row) for row in table.to_dicts()]
    if hasattr(table, "to_dict"):
        with suppress(TypeError):
            records = table.to_dict("records")
            return [dict(row) for row in records]
    if isinstance(table, Mapping):
        return [dict(cast(Mapping[str, Any], table))]
    if isinstance(table, Iterable) and not isinstance(table, (str, bytes)):
        iterable = cast(Iterable[Any], table)
        return [
            dict(cast(Mapping[str, Any], raw_row))
            for raw_row in iterable
            if isinstance(raw_row, Mapping)
        ]
    return []


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _set_number(item: dict[str, Any], target: str, value: Any) -> None:
    number = _number(value)
    if number is not None and item.get(target) is None:
        item[target] = number


def _copy_alias(item: dict[str, Any], source: str, target: str) -> None:
    if item.get(target) is None and item.get(source) is not None:
        item[target] = item.get(source)


def _pct(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number * 100.0 if 0.0 <= number <= 1.5 else number


def _risk_from_cfs_mm(value: Any) -> float | None:
    cfs_mm = _number(value)
    if cfs_mm is None:
        return None
    return next((score for threshold, score in ((0, 1.0), (3, 0.92), (6, 0.72), (10, 0.38)) if cfs_mm <= threshold), 0.08)


def _difference(item: dict[str, Any], left: str, right: str) -> float | None:
    left_value = _number(item.get(left))
    right_value = _number(item.get(right))
    if left_value is None or right_value is None:
        return None
    return left_value - right_value


def _average(item: dict[str, Any], *keys: str) -> float | None:
    values = [_number(item.get(key)) for key in keys]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None) / len(values)


# ── _apply_row_calculations helpers ──────────────────────────────

_ALIAS_MAP: dict[str, str] = {
    "SessionTime": "session_time", "SessionTick": "session_tick",
    "Lap": "lap", "LapCompleted": "lap_completed",
    "LapDist": "lap_dist_m", "LapDistPct": "lap_dist_pct",
    "Speed": "speed_mps", "RPM": "rpm", "Gear": "gear",
    "Throttle": "throttle_01", "Brake": "brake_01",
    "SteeringWheelAngle": "steering_rad", "YawRate": "yaw_rate",
    "LatAccel": "lat_accel", "LongAccel": "long_accel",
    "AirDensity": "air_density", "Lat": "lat", "Lon": "lon", "Alt": "alt",
    "CFSRrideHeight": "cfs_ride_height_m",
}

_REMAINING_ALIAS_MAP: dict[str, str] = {
    "WaterTemp": "water_temp", "OilTemp": "oil_temp",
    "FuelLevel": "fuel_level", "FuelLevelPct": "fuel_level_pct",
    "FuelUsePerHour": "fuel_use_per_hour", "Voltage": "voltage",
    "AirTemp": "air_temp", "TrackTemp": "track_temp",
    "WindVel": "wind_vel", "WindDir": "wind_dir",
    "AirPressure": "air_pressure", "WaterLevel": "water_level",
    "FuelPress": "fuel_press", "OilPress": "oil_press",
    "OilLevel": "oil_level", "ManifoldPress": "manifold_press",
    "Engine0_RPM": "engine0_rpm", "EngineWarnings": "engine_warnings",
    "TrackTempCrew": "track_temp_crew", "RelativeHumidity": "relative_humidity",
    "FogLevel": "fog_level", "Skies": "skies",
    "TrackWetness": "track_wetness", "VelocityX": "velocity_x",
    "VelocityY": "velocity_y", "VelocityZ": "velocity_z",
    "Yaw": "yaw", "YawNorth": "yaw_north", "Pitch": "pitch",
    "Roll": "roll", "PitchRate": "pitch_rate", "RollRate": "roll_rate",
    "VertAccel": "vert_accel", "Clutch": "clutch",
    "ClutchRaw": "clutch_raw", "ShiftPowerPct": "shift_power_pct",
    "ShiftGrindRPM": "shift_grind_rpm",
    "SteeringWheelAngleMax": "steering_wheel_angle_max",
}

_RIDE_HEIGHT_RAW_KEYS: dict[str, str] = {
    "CFSRrideHeight": "cfs_ride_height",
    "LFrideHeight": "lf_ride_height",
    "RFrideHeight": "rf_ride_height",
    "LRrideHeight": "lr_ride_height",
    "RRrideHeight": "rr_ride_height",
}

_SHOCK_DEFL_KEYS: dict[str, str] = {
    "LFshockDefl": "lf_shock_defl",
    "RFshockDefl": "rf_shock_defl",
    "LRshockDefl": "lr_shock_defl",
    "RRshockDefl": "rr_shock_defl",
    "LFSHshockDefl": "lf_shock_defl",
    "RFSHshockDefl": "rf_shock_defl",
    "LRSHshockDefl": "lr_shock_defl",
    "RRSHshockDefl": "rr_shock_defl",
}

_SHOCK_VEL_KEYS: dict[str, str] = {
    "LFshockVel": "lf_shock_vel",
    "RFshockVel": "rf_shock_vel",
    "LRshockVel": "lr_shock_vel",
    "RRshockVel": "rr_shock_vel",
    "LFSHshockVel": "lf_shock_vel",
    "RFSHshockVel": "rf_shock_vel",
    "LRSHshockVel": "lr_shock_vel",
    "RRSHshockVel": "rr_shock_vel",
}

_SHOCK_CORNERS: tuple[str, ...] = ("lf", "rf", "lr", "rr")
_SHOCK_STATIC_THROTTLE_MIN_PCT = 10.0
_SHOCK_DELTA_SMOOTH_WINDOW = 16

# ── tire variable aliases ────────────────────────────────────
_TIRE_PRESSURE_KEYS: dict[str, str] = {
    "LFpressure": "lf_pressure", "RFpressure": "rf_pressure",
    "LRpressure": "lr_pressure", "RRpressure": "rr_pressure",
}
_TIRE_COLD_PRESSURE_KEYS: dict[str, str] = {
    "LFcoldPressure": "lf_cold_pressure", "RFcoldPressure": "rf_cold_pressure",
    "LRcoldPressure": "lr_cold_pressure", "RRcoldPressure": "rr_cold_pressure",
}
_TIRE_TEMP_INNER_KEYS: dict[str, str] = {
    "LFtempL": "lf_temp_inner", "RFtempL": "rf_temp_inner",
    "LRtempL": "lr_temp_inner", "RRtempL": "rr_temp_inner",
}
_TIRE_TEMP_MIDDLE_KEYS: dict[str, str] = {
    "LFtempM": "lf_temp_middle", "RFtempM": "rf_temp_middle",
    "LRtempM": "lr_temp_middle", "RRtempM": "rr_temp_middle",
}
_TIRE_TEMP_OUTER_KEYS: dict[str, str] = {
    "LFtempR": "lf_temp_outer", "RFtempR": "rf_temp_outer",
    "LRtempR": "lr_temp_outer", "RRtempR": "rr_temp_outer",
}
_TIRE_CARCASS_TEMP_KEYS: dict[str, str] = {
    "LFtempCL": "lf_carcass_temp_l", "RFtempCL": "rf_carcass_temp_l",
    "LRtempCL": "lr_carcass_temp_l", "RRtempCL": "rr_carcass_temp_l",
    "LFtempCM": "lf_carcass_temp_m", "RFtempCM": "rf_carcass_temp_m",
    "LRtempCM": "lr_carcass_temp_m", "RRtempCM": "rr_carcass_temp_m",
    "LFtempCR": "lf_carcass_temp_r", "RFtempCR": "rf_carcass_temp_r",
    "LRtempCR": "lr_carcass_temp_r", "RRtempCR": "rr_carcass_temp_r",
}
_TIRE_WEAR_KEYS: dict[str, str] = {
    "LFwearL": "lf_wear_inner", "RFwearL": "rf_wear_inner",
    "LRwearL": "lr_wear_inner", "RRwearL": "rr_wear_inner",
    "LFwearM": "lf_wear_middle", "RFwearM": "rf_wear_middle",
    "LRwearM": "lr_wear_middle", "RRwearM": "rr_wear_middle",
    "LFwearR": "lf_wear_outer", "RFwearR": "rf_wear_outer",
    "LRwearR": "lr_wear_outer", "RRwearR": "rr_wear_outer",
}
_WHEEL_SPEED_KEYS: dict[str, str] = {
    "LFspeed": "lf_speed", "RFspeed": "rf_speed",
    "LRspeed": "lr_speed", "RRspeed": "rr_speed",
}

_SLIP_RATIO_KEYS: dict[str, str] = {
    "LFspeed": "lf_slip_ratio",
    "RFspeed": "rf_slip_ratio",
    "LRspeed": "lr_slip_ratio",
    "RRspeed": "rr_slip_ratio",
}


def _copy_aliases(item: dict[str, Any]) -> None:
    for raw_key, normalized_key in _ALIAS_MAP.items():
        _copy_alias(item, raw_key, normalized_key)


def _copy_remaining_aliases(item: dict[str, Any]) -> None:
    for raw_key, normalized_key in _REMAINING_ALIAS_MAP.items():
        _copy_alias(item, raw_key, normalized_key)


def _convert_distances(item: dict[str, Any]) -> None:
    lap_dist = _number(item.get("lap_dist_m"))
    if lap_dist is not None:
        _set_number(item, "lap_dist_ft", lap_dist * M_TO_FT)
    lap_pct = item.get("lap_dist_pct")
    if lap_pct is not None:
        _set_number(item, "lap_dist_pct_100", _pct(lap_pct))


def _convert_speed(item: dict[str, Any]) -> None:
    speed_mps = _number(item.get("speed_mps"))
    if speed_mps is not None:
        _set_number(item, "speed_mph", speed_mps * MPS_TO_MPH)
        _set_number(item, "speed_fps", speed_mps * M_TO_FT)


def _convert_inputs(item: dict[str, Any]) -> None:
    throttle = _number(item.get("throttle_01"))
    if throttle is not None:
        _set_number(item, "throttle_pct", input_01_to_percent(throttle))
    brake = _number(item.get("brake_01"))
    if brake is not None:
        _set_number(item, "brake_pct", input_01_to_percent(brake))
    steering_rad = _number(item.get("steering_rad"))
    if steering_rad is not None:
        _set_number(item, "steering_deg", radians_to_degrees(steering_rad))
    steering_deg = item.get("steering_deg")
    if steering_deg is not None:
        _set_number(item, "abs_steering_deg", abs(float(steering_deg)))
    lat_accel = item.get("lat_accel")
    if lat_accel is not None:
        _set_number(item, "abs_lat_accel", abs(float(lat_accel)))


def _convert_ride_heights(item: dict[str, Any]) -> None:
    for raw_key, prefix in _RIDE_HEIGHT_RAW_KEYS.items():
        value_m = _number(item.get(raw_key))
        if value_m is None and raw_key == "CFSRrideHeight":
            value_m = _number(item.get("cfs_ride_height_m"))
        if value_m is None:
            continue
        _set_number(item, f"{prefix}_mm", value_m * 1000.0)
        _set_number(item, f"{prefix}_in", value_m * M_TO_IN)

    for mm_key, inch_key in {
        "cfsr_height_mm": "cfs_ride_height_in",
        "cfs_ride_height_mm": "cfs_ride_height_in",
        "lf_ride_height_mm": "lf_ride_height_in",
        "rf_ride_height_mm": "rf_ride_height_in",
        "lr_ride_height_mm": "lr_ride_height_in",
        "rr_ride_height_mm": "rr_ride_height_in",
    }.items():
        value_mm = _number(item.get(mm_key))
        if value_mm is not None:
            _set_number(item, inch_key, value_mm * MM_TO_IN)

    cfs_mm = item.get("cfs_ride_height_mm")
    cfsr_mm = item.get("cfsr_height_mm")
    if cfs_mm is not None:
        _set_number(item, "cfsr_height_mm", cfs_mm)
    elif cfsr_mm is not None:
        _set_number(item, "cfs_ride_height_mm", cfsr_mm)


def _convert_shocks(item: dict[str, Any]) -> None:
    for raw_key, prefix in _SHOCK_DEFL_KEYS.items():
        value_m = _number(item.get(raw_key))
        if value_m is not None:
            item.setdefault(prefix, value_m)
            _set_number(item, f"{prefix}_in", value_m * M_TO_IN)
    for raw_key, prefix in _SHOCK_VEL_KEYS.items():
        value_m_s = _number(item.get(raw_key))
        if value_m_s is not None:
            item.setdefault(prefix, value_m_s)
            _set_number(item, f"{prefix}_in_s", value_m_s * M_TO_IN)


def _shock_static_candidate(row: dict[str, Any]) -> bool:
    throttle_pct = _number(row.get("throttle_pct"))
    if throttle_pct is None:
        throttle_raw = _number(row.get("throttle_01"))
        throttle_pct = input_01_to_percent(throttle_raw) if throttle_raw is not None else None
    return throttle_pct is not None and throttle_pct > _SHOCK_STATIC_THROTTLE_MIN_PCT


def _derive_missing_shock_velocities(rows: list[dict[str, Any]]) -> None:
    previous: dict[str, Any] | None = None
    for row in rows:
        if previous is None:
            previous = row
            continue
        session_time = _number(row.get("session_time"))
        previous_time = _number(previous.get("session_time"))
        if session_time is None or previous_time is None:
            previous = row
            continue
        dt = session_time - previous_time
        if dt <= 0:
            previous = row
            continue

        for corner in _SHOCK_CORNERS:
            velocity_key = f"{corner}_shock_vel_in_s"
            if _number(row.get(velocity_key)) is not None:
                continue
            deflection_key = f"{corner}_shock_defl_in"
            current_deflection = _number(row.get(deflection_key))
            previous_deflection = _number(previous.get(deflection_key))
            if current_deflection is None or previous_deflection is None:
                continue
            row[velocity_key] = (current_deflection - previous_deflection) / dt
        previous = row


def _apply_shock_static_and_delta(rows: list[dict[str, Any]]) -> None:
    for corner in _SHOCK_CORNERS:
        deflection_key = f"{corner}_shock_defl_in"
        static_key = f"{corner}_shock_static_defl_in"
        delta_key = f"{corner}_shock_defl_delta_in"

        baseline = next(
            (
                _number(row.get(deflection_key))
                for row in rows
                if _number(row.get(deflection_key)) is not None and _shock_static_candidate(row)
            ),
            None,
        )
        if baseline is None:
            continue

        delta_buffer: list[float] = []
        for row in rows:
            row[static_key] = baseline
            deflection = _number(row.get(deflection_key))
            if deflection is not None:
                delta_buffer.append(deflection - baseline)
                if len(delta_buffer) > _SHOCK_DELTA_SMOOTH_WINDOW:
                    delta_buffer.pop(0)
                row[delta_key] = sum(delta_buffer) / len(delta_buffer)


def _finalize_shock_channels(rows: list[dict[str, Any]]) -> None:
    _derive_missing_shock_velocities(rows)
    _apply_shock_static_and_delta(rows)


def _convert_tires(item: dict[str, Any]) -> None:
    """Alias tire pressures, temps, wear, and wheel speeds from raw .ibt names."""
    for raw_key, norm_key in _TIRE_PRESSURE_KEYS.items():
        _copy_alias(item, raw_key, norm_key)
    for raw_key, norm_key in _TIRE_COLD_PRESSURE_KEYS.items():
        _copy_alias(item, raw_key, norm_key)
    for raw_key, norm_key in _TIRE_TEMP_INNER_KEYS.items():
        _copy_alias(item, raw_key, norm_key)
    for raw_key, norm_key in _TIRE_TEMP_MIDDLE_KEYS.items():
        _copy_alias(item, raw_key, norm_key)
    for raw_key, norm_key in _TIRE_TEMP_OUTER_KEYS.items():
        _copy_alias(item, raw_key, norm_key)
    for raw_key, norm_key in _TIRE_CARCASS_TEMP_KEYS.items():
        _copy_alias(item, raw_key, norm_key)
    for raw_key, norm_key in _TIRE_WEAR_KEYS.items():
        _copy_alias(item, raw_key, norm_key)
    for raw_key, norm_key in _WHEEL_SPEED_KEYS.items():
        _copy_alias(item, raw_key, norm_key)


def _compute_tire_derived(item: dict[str, Any]) -> None:
    """Pressure gain, temp spread, wear spread, slip ratio proxy per corner."""
    for c in ["lf", "rf", "lr", "rr"]:
        p = _number(item.get(f"{c}_pressure"))
        cp = _number(item.get(f"{c}_cold_pressure"))
        if p is not None and cp is not None:
            _set_number(item, f"{c}_pressure_gain", p - cp)
        ti = _number(item.get(f"{c}_temp_inner"))
        tm = _number(item.get(f"{c}_temp_middle"))
        to = _number(item.get(f"{c}_temp_outer"))
        temps = [v for v in [ti, tm, to] if v is not None]
        if len(temps) >= 2:
            _set_number(item, f"{c}_temp_spread", max(temps) - min(temps))
        wi = _number(item.get(f"{c}_wear_inner"))
        wm = _number(item.get(f"{c}_wear_middle"))
        wo = _number(item.get(f"{c}_wear_outer"))
        wears = [v for v in [wi, wm, wo] if v is not None]
        if len(wears) >= 2:
            _set_number(item, f"{c}_wear_spread", max(wears) - min(wears))
        # slip ratio proxy (unified denominator with floor)
        ws = _number(item.get(f"{c}_speed"))
        speed_mps = _number(item.get("speed_mps"))
        if ws is not None and speed_mps is not None:
            denom = max(abs(speed_mps), SLIP_RATIO_SPEED_FLOOR_MPS)
            slip = (ws - speed_mps) / denom
            slip = max(-SLIP_RATIO_CLAMP_MAX, min(SLIP_RATIO_CLAMP_MAX, slip))
            _set_number(item, f"{c}_slip_ratio_proxy", slip)


def _compute_averages(item: dict[str, Any]) -> None:
    front_avg = _average(item, "lf_ride_height_in", "rf_ride_height_in")
    rear_avg = _average(item, "lr_ride_height_in", "rr_ride_height_in")
    left_avg = _average(item, "lf_ride_height_in", "lr_ride_height_in")
    right_avg = _average(item, "rf_ride_height_in", "rr_ride_height_in")
    _set_number(item, "front_avg_rh_in", front_avg)
    _set_number(item, "rear_avg_rh_in", rear_avg)
    _set_number(item, "left_avg_rh_in", left_avg)
    _set_number(item, "right_avg_rh_in", right_avg)
    if rear_avg is not None and item.get("cfs_ride_height_in") is not None:
        _set_number(item, "center_rake_fs_in", rear_avg - float(item["cfs_ride_height_in"]))
    if right_avg is not None and left_avg is not None:
        _set_number(item, "side_rake_in", right_avg - left_avg)
    _set_number(item, "front_split_in", _difference(item, "rf_ride_height_in", "lf_ride_height_in"))
    _set_number(item, "rear_split_in", _difference(item, "rr_ride_height_in", "lr_ride_height_in"))


def _compute_dynamic_pressure(item: dict[str, Any]) -> None:
    air_density = _number(item.get("air_density"))
    speed_mps = _number(item.get("speed_mps"))
    if air_density is not None and speed_mps is not None:
        dynamic_pressure_pa = 0.5 * air_density * speed_mps * speed_mps
        _set_number(item, "dynamic_pressure_pa", dynamic_pressure_pa)
        _set_number(item, "dynamic_pressure_psf", dynamic_pressure_pa * PA_TO_PSF)


def _apply_rear_scrape_risk(item: dict[str, Any], lr_mm: float, rr_mm: float) -> None:
    """Compute and store rear scrape risk channels from ride heights."""
    from racelab_engine.analysis.constants import REAR_SCRAPE_MM
    rear_min = min(lr_mm, rr_mm)
    _set_number(item, "rear_min_ride_height_mm", rear_min)
    _set_number(item, "rear_min_ride_height_in", rear_min * MM_TO_IN)
    margin = rear_min - REAR_SCRAPE_MM
    _set_number(item, "rear_scrape_margin_mm", margin)
    risk = _risk_from_rear_mm(rear_min)
    _set_number(item, "rear_scrape_risk_score", risk)
    _set_number(item, "rear_platform_contact_risk", risk)
    _set_number(item, "rear_scrape_side", _scrape_side_code(lr_mm, rr_mm))


def _scrape_side_code(lr_mm: float, rr_mm: float) -> int:
    """Determine which rear corner is lower: -1=left, 0=both, 1=right."""
    eps = 0.001
    if abs(lr_mm - rr_mm) < eps:
        return 0
    return -1 if lr_mm < rr_mm else 1


def _risk_from_rear_mm(value: Any) -> float | None:
    """Risk score for rear ride height using same scale as CFS risk."""
    from racelab_engine.analysis.constants import REAR_SCRAPE_MM, REAR_CRITICAL_MM, REAR_HIGH_MM, REAR_WATCH_MM
    rear_mm = _number(value)
    if rear_mm is None:
        return None
    return next((score for threshold, score in (
        (REAR_SCRAPE_MM, 1.0),
        (REAR_CRITICAL_MM, 0.92),
        (REAR_HIGH_MM, 0.72),
        (REAR_WATCH_MM, 0.38),
    ) if rear_mm <= threshold), 0.08)


def _compute_rear_scrape(item: dict[str, Any]) -> None:
    """Compute rear scrape risk channels."""
    lr_mm = _number(item.get("lr_ride_height_mm"))
    rr_mm = _number(item.get("rr_ride_height_mm"))
    if lr_mm is not None and rr_mm is not None:
        _apply_rear_scrape_risk(item, lr_mm, rr_mm)


def _compute_platform_balance(item: dict[str, Any]) -> None:
    """Classify platform balance using front/CFS and rear scrape risk."""
    cfs_risk = _number(item.get("cfs_risk_score"))
    rear_risk = _number(item.get("rear_scrape_risk_score"))
    side_raw = item.get("rear_scrape_side")

    if cfs_risk is not None:
        _set_number(item, "front_platform_risk_score", cfs_risk)
    if rear_risk is not None:
        _set_number(item, "rear_platform_risk_score", rear_risk)

    side_map = {-1: "left_rear", 0: "both_rear", 1: "right_rear"}
    if side_raw is not None and isinstance(side_raw, (int, float)):
        item["rear_scrape_side_label"] = side_map.get(int(side_raw))

    if cfs_risk is not None and rear_risk is not None:
        _set_number(item, "whole_car_bottoming_risk", min(cfs_risk, rear_risk))

    ELEVATED = 0.72
    if cfs_risk is None or rear_risk is None:
        item["platform_balance_label"] = "unavailable"
        item["platform_balance_explanation"] = (
            "Insufficient ride-height channels to classify platform balance."
        )
    elif cfs_risk >= ELEVATED and rear_risk >= ELEVATED:
        item["platform_balance_label"] = "whole_car_bottoming"
        item["platform_balance_explanation"] = (
            "Front and rear are both low — likely whole-car bottoming or ride height too low."
        )
    elif cfs_risk >= ELEVATED:
        item["platform_balance_label"] = "front_platform_risk"
        item["platform_balance_explanation"] = (
            "Front/CFS is low while rear platform is safe — likely splitter/front platform risk."
        )
    elif rear_risk >= ELEVATED:
        item["platform_balance_label"] = "rear_platform_risk"
        item["platform_balance_explanation"] = (
            "Rear platform is low while front/CFS is safe — likely rear platform contact or rear bottoming."
        )
    else:
        item["platform_balance_label"] = "balanced_safe"
        item["platform_balance_explanation"] = (
            "Front and rear platform margins look safe."
        )


def _compute_risk_scores(item: dict[str, Any]) -> None:
    cfs_risk = _risk_from_cfs_mm(item.get("cfs_ride_height_mm"))
    _set_number(item, "cfs_risk_score", cfs_risk)
    _set_number(item, "platform_risk_score", cfs_risk)
    _compute_rear_scrape(item)
    _compute_platform_balance(item)


def _compute_slip_ratios(item: dict[str, Any]) -> None:
    speed_mps = _number(item.get("speed_mps"))
    denom = max(abs(speed_mps or 0.0), SLIP_RATIO_SPEED_FLOOR_MPS)
    for raw_key, target in _SLIP_RATIO_KEYS.items():
        wheel_speed = _number(item.get(raw_key))
        if wheel_speed is not None:
            slip = (wheel_speed - speed_mps) / denom if speed_mps is not None else 0.0
            slip = max(-SLIP_RATIO_CLAMP_MAX, min(SLIP_RATIO_CLAMP_MAX, slip))
            _set_number(item, target, slip)

    # Geometry-corrected wheel speed mismatch using yaw rate
    yaw_rate = _number(item.get("yaw_rate")) or 0.0
    front_tw_m = _number(item.get("front_track_width_m"))
    rear_tw_m = _number(item.get("rear_track_width_m"))

    # Raw mismatch (for when track width is missing)
    _set_number(item, "front_wheel_speed_mismatch_raw", _difference(item, "RFspeed", "LFspeed"))
    _set_number(item, "rear_wheel_speed_mismatch_raw", _difference(item, "RRspeed", "LRspeed"))

    # Geometry-corrected mismatch
    if front_tw_m is not None:
        front_geo = yaw_rate * front_tw_m
        front_diff = _difference(item, "RFspeed", "LFspeed")
        if front_diff is not None:
            _set_number(item, "front_wheel_speed_mismatch_corrected", front_diff - front_geo)
    else:
        item.setdefault("front_wheel_speed_mismatch_corrected", None)
    if rear_tw_m is not None:
        rear_geo = yaw_rate * rear_tw_m
        rear_diff = _difference(item, "RRspeed", "LRspeed")
        if rear_diff is not None:
            _set_number(item, "rear_wheel_speed_mismatch_corrected", rear_diff - rear_geo)
    else:
        item.setdefault("rear_wheel_speed_mismatch_corrected", None)

    lr_speed = _number(item.get("LRspeed"))
    rr_speed = _number(item.get("RRspeed"))
    if speed_mps is not None and lr_speed is not None and rr_speed is not None:
        slip = ((lr_speed + rr_speed) / 2.0 - speed_mps) / denom
        slip = max(-SLIP_RATIO_CLAMP_MAX, min(SLIP_RATIO_CLAMP_MAX, slip))
        _set_number(item, "driven_wheel_slip_proxy", slip)


def _compute_scrub_proxies(item: dict[str, Any]) -> None:
    lf_slip = _number(item.get("lf_slip_ratio"))
    rf_slip = _number(item.get("rf_slip_ratio"))
    lr_slip = _number(item.get("lr_slip_ratio"))
    rr_slip = _number(item.get("rr_slip_ratio"))
    steering = _number(item.get("abs_steering_deg")) or 0.0
    lat_accel = _number(item.get("abs_lat_accel")) or 0.0
    speed_mps = _number(item.get("speed_mps")) or 0.0
    yaw_rate = abs(_number(item.get("yaw_rate")) or 0.0)
    radius = _number(item.get("radius_m"))

    # Yaw error: actual yaw rate vs theoretical from curvature
    yaw_error_proxy = 0.0
    if radius is not None and radius > 0 and speed_mps > 1.0:
        yaw_theoretical = speed_mps / radius
        yaw_error_proxy = max(0.0, yaw_theoretical - yaw_rate)
    item["yaw_error_proxy"] = yaw_error_proxy

    # TODO: When understeer_gradient_proxy_deg_per_g is available and
    # abs(lat_accel_g) > 0.1, use it as primary scrub evidence instead of
    # the steering/yaw blend below. Requires wiring vehicle_dynamics
    # understeer functions into runtime (mass/geometry needed).
    if lf_slip is not None and rf_slip is not None:
        YAW_ERROR_CRITICAL = 0.15  # rad/s threshold for understeer
        slip_delta = abs(rf_slip - lf_slip)
        steering_lat = (steering / 90.0) * lat_accel
        yaw_component = min(1.0, yaw_error_proxy / YAW_ERROR_CRITICAL)
        scrub = slip_delta * 0.30 + steering_lat * 0.25 + yaw_component * 0.45
        _set_number(item, "front_scrub_proxy", scrub)
    if lr_slip is not None and rr_slip is not None:
        _set_number(item, "rear_scrub_proxy", abs(rr_slip - lr_slip))


# ── _apply_derivatives helpers ───────────────────────────────────

def _init_derivative_row(row: dict[str, Any]) -> None:
    row["speed_rate_mph_s"] = None
    row["speed_rate_mph_1000ft"] = None
    row["speed_rate_mps2"] = None
    row["platform_stability_score"] = None
    row["rake_stability_score"] = None
    row["platform_compression_index"] = None
    row["dynamic_grade_deg"] = None
    row["dynamic_grade_rad"] = None
    row["grade_corrected_long_accel_mps2"] = None
    row["grade_force_proxy_n"] = None
    row["grade_context_label"] = None
    row["grade_corrected_speed_loss_mph_s"] = None


def _compute_speed_rates(row: dict[str, Any], previous: dict[str, Any]) -> float | None:
    speed = _number(row.get("speed_mph"))
    previous_speed = _number(previous.get("speed_mph"))
    session_time = _number(row.get("session_time"))
    previous_time = _number(previous.get("session_time"))
    lap_dist_ft = _number(row.get("lap_dist_ft"))
    previous_lap_dist_ft = _number(previous.get("lap_dist_ft"))
    speed_mps = _number(row.get("speed_mps"))
    prev_speed_mps = _number(previous.get("speed_mps"))

    speed_rate_s = None
    if speed is not None and previous_speed is not None and session_time is not None and previous_time is not None:
        dt = session_time - previous_time
        if dt > 0:
            speed_rate_s = (speed - previous_speed) / dt
            row["speed_rate_mph_s"] = speed_rate_s
            
            # SI unit rate for dynamic grade calculation
            if speed_mps is not None and prev_speed_mps is not None:
                row["speed_rate_mps2"] = (speed_mps - prev_speed_mps) / dt
        # dt <= 0 (repeated timestamps): leave as None (already initialized)
    if speed is not None and previous_speed is not None and lap_dist_ft is not None and previous_lap_dist_ft is not None:
        dd = lap_dist_ft - previous_lap_dist_ft
        if abs(dd) > 0.1:
            row["speed_rate_mph_1000ft"] = (speed - previous_speed) / dd * 1000.0
        # Tiny distance delta: leave as None
    return speed_rate_s


def _compute_stability_scores(row: dict[str, Any], previous: dict[str, Any]) -> None:
    session_time = _number(row.get("session_time"))
    previous_time = _number(previous.get("session_time"))
    if session_time is None or previous_time is None or session_time <= previous_time:
        return
    dt = session_time - previous_time
    cfs = _number(row.get("cfs_ride_height_in"))
    previous_cfs = _number(previous.get("cfs_ride_height_in"))
    rake = _number(row.get("center_rake_fs_in"))
    previous_rake = _number(previous.get("center_rake_fs_in"))
    if cfs is not None and previous_cfs is not None:
        row["platform_stability_score"] = min(1.0, abs((cfs - previous_cfs) / dt) / 2.0)
    if rake is not None and previous_rake is not None:
        row["rake_stability_score"] = min(1.0, abs((rake - previous_rake) / dt) / 2.0)


def _compute_resistance_indices(row: dict[str, Any], previous: dict[str, Any]) -> None:
    from racelab_engine.analysis.constants import (
        DRAG_SCRUB_MIN_SPEED_MPH, FULL_THROTTLE_PCT, LOW_BRAKE_PCT,
        RESISTANCE_COEFF_CRITICAL,
    )

    speed = _number(row.get("speed_mph")) or 0.0
    throttle = _number(row.get("throttle_pct")) or 0.0
    brake_pct = _number(row.get("brake_pct")) or 0.0
    max_lap_speed = _number(row.get("max_lap_speed_mph")) or speed
    speed_threshold = max_lap_speed * 0.75 if max_lap_speed > 0 else DRAG_SCRUB_MIN_SPEED_MPH

    if throttle >= FULL_THROTTLE_PCT and brake_pct <= LOW_BRAKE_PCT and speed >= speed_threshold:
        resistance_coeff = float(aero_normalized_resistance(row))
        resistance_index = min(1.0, resistance_coeff / RESISTANCE_COEFF_CRITICAL)
        row["full_throttle_resistance_index"] = resistance_index
    else:
        row.setdefault("full_throttle_resistance_index", 0.0)

    # Use canonical drag/scrub index from shared module
    row["drag_scrub_suspicion"] = compute_drag_scrub_index(row)


def _compute_compression_index(row: dict[str, Any]) -> None:
    cfs_risk = _number(row.get("cfs_risk_score")) or 0.0
    plat_stab = _number(row.get("platform_stability_score")) or 0.0
    drag_susp = _number(row.get("drag_scrub_suspicion")) or 0.0
    row["platform_compression_index"] = min(1.0, cfs_risk * 0.4 + plat_stab * 0.3 + drag_susp * 0.3)


# ── _apply_rolling_aggregates helpers ────────────────────────────

def _update_shock_buffers(row: dict[str, Any], buffers: dict[str, list[float]], corners: tuple[str, ...], window: int) -> None:
    for corner in corners:
        sv = _number(row.get(f"{corner}_shock_vel_in_s"))
        if sv is None:
            continue
        buffers[f"{corner}_sv"].append(sv)
        if len(buffers[f"{corner}_sv"]) > window:
            buffers[f"{corner}_sv"].pop(0)

        buf = buffers[f"{corner}_sv"]
        if not buf:
            continue
        mean_sq = sum(v * v for v in buf) / len(buf)
        rms = math.sqrt(mean_sq)
        peak = max(abs(v) for v in buf)
        activity = sum(abs(v) for v in buf) / len(buf) + peak * 0.3
        energy = sum(v * v for v in buf)

        row[f"{corner}_shock_velocity_rms"] = rms
        row[f"{corner}_shock_activity_index"] = activity
        row[f"{corner}_damper_energy_proxy"] = energy


def _compute_component_averages(rows: list[dict[str, Any]], corners: tuple[str, ...]) -> None:
    for component in ("shock_velocity_rms", "shock_activity_index", "damper_energy_proxy"):
        corner_keys = [f"{c}_{component}" for c in corners if rows and f"{c}_{component}" in rows[-1]]
        if not corner_keys:
            continue
        for row in rows:
            values = [_number(row.get(key)) for key in corner_keys]
            numeric_values = [value for value in values if value is not None]
            if numeric_values:
                row[component] = sum(numeric_values) / len(numeric_values)


def _apply_row_calculations(item: dict[str, Any]) -> None:
    _copy_aliases(item)
    _convert_distances(item)
    _convert_speed(item)
    _convert_inputs(item)
    _convert_ride_heights(item)
    _convert_shocks(item)
    _convert_tires(item)
    _compute_tire_derived(item)
    _compute_averages(item)
    _compute_dynamic_pressure(item)
    _compute_risk_scores(item)
    _copy_remaining_aliases(item)
    _compute_slip_ratios(item)
    _compute_kinematic_slip_angles(item)
    _compute_scrub_proxies(item)
    _compute_g_values(item)
    _compute_platform_angles(item)
    _compute_ackermann(item)
    _compute_camber_bias(item)


# ── diffuser geometry (Roger's diffuser geometry math) ────────────

_DIFFUSER_FALLBACK_WHEELBASE_IN = 110.0
_DIFFUSER_FALLBACK_TRACK_WIDTH_IN = 79.0
_DIFFUSER_RUB_BLOCK_CORRECTION_IN = 0.5
_CUBIC_INCHES_PER_FT3 = 1728.0
_DIFFUSER_SMOOTH_WINDOW = 20


def _resolve_diffuser_geometry(
    geometry: Mapping[str, float] | None,
    default_wb: float = _DIFFUSER_FALLBACK_WHEELBASE_IN,
    default_tw: float = _DIFFUSER_FALLBACK_TRACK_WIDTH_IN,
) -> tuple[float, float]:
    """Resolve wheelbase and track-width in inches for diffuser computation."""
    if geometry:
        wb_m = geometry.get("wheelbase_m")
        if wb_m is not None and wb_m > 0:
            wb_in = wb_m * 39.37007874
        else:
            wb_in = default_wb

        rear_tw_m = geometry.get("rear_track_width_m")
        front_tw_m = geometry.get("front_track_width_m")
        if rear_tw_m is not None and rear_tw_m > 0:
            tw_in = rear_tw_m * 39.37007874
        elif front_tw_m is not None and front_tw_m > 0:
            tw_in = front_tw_m * 39.37007874
        else:
            tw_in = default_tw
    else:
        wb_in = default_wb
        tw_in = default_tw
    return wb_in, tw_in


def _compute_diffuser_channels(
    rows: list[dict[str, Any]],
    geometry: Mapping[str, float] | None = None,
) -> None:
    """Compute diffuser geometry channels on all rows (row path)."""
    if not rows:
        return

    wb_in, tw_in = _resolve_diffuser_geometry(geometry)
    rub = _DIFFUSER_RUB_BLOCK_CORRECTION_IN
    ft3_div = _CUBIC_INCHES_PER_FT3

    # Per-row volume calc
    volumes: list[float] = []
    for row in rows:
        lf = row.get("lf_ride_height_in")
        rf = row.get("rf_ride_height_in")
        lr = row.get("lr_ride_height_in")
        rr = row.get("rr_ride_height_in")
        if any(v is None for v in (lf, rf, lr, rr)):
            row["front_center_rh_in"] = None
            row["lr_height_rub_block_in"] = None
            row["rear_center_rh_in"] = None
            row["center_rake_in"] = None
            row["diffuser_track_width_in"] = tw_in
            row["diffuser_wheelbase_in"] = wb_in
            row["diffuser_base_volume_ft3"] = None
            row["diffuser_wedge_volume_ft3"] = None
            row["diffuser_volume_ft3"] = None
            volumes.append(float("nan"))
            continue

        front_c = (rf + lf) / 2.0
        lr_rub = lr - rub
        rear_c = (rr + lr_rub) / 2.0
        rake = rear_c - front_c

        row["front_center_rh_in"] = front_c
        row["lr_height_rub_block_in"] = lr_rub
        row["rear_center_rh_in"] = rear_c
        row["center_rake_in"] = rake
        row["diffuser_track_width_in"] = tw_in
        row["diffuser_wheelbase_in"] = wb_in

        base_vol = (front_c * wb_in * tw_in) / ft3_div
        row["diffuser_base_volume_ft3"] = base_vol

        import math
        diag = math.sqrt(wb_in ** 2 + (rake ** 2) / 2.0)
        wedge_vol = (tw_in * abs(rake) * diag) / ft3_div if rake < 0 else 0.0
        row["diffuser_wedge_volume_ft3"] = wedge_vol

        total_vol = base_vol + wedge_vol
        row["diffuser_volume_ft3"] = total_vol
        volumes.append(total_vol)

    # Trailing/causal rolling smooths
    window = _DIFFUSER_SMOOTH_WINDOW
    for i in range(len(rows)):
        if rows[i].get("center_rake_in") is not None:
            start = max(0, i - window + 1)
            rake_vals = [rows[j]["center_rake_in"] for j in range(start, i + 1) if rows[j].get("center_rake_in") is not None]
            rows[i]["smooth_center_rake_in"] = sum(rake_vals) / len(rake_vals) if rake_vals else None
        else:
            rows[i]["smooth_center_rake_in"] = None

        vol = volumes[i]
        if not (vol != vol):  # not NaN
            start = max(0, i - window + 1)
            vol_vals = [v for v in volumes[start:i + 1] if not (v != v)]
            rows[i]["smooth_diffuser_volume_ft3"] = sum(vol_vals) / len(vol_vals) if vol_vals else None
        else:
            rows[i]["smooth_diffuser_volume_ft3"] = None


def _compute_g_values(item: dict[str, Any]) -> None:
    """Convert m/s² accelerations to g units."""
    for ch in ["lat_accel", "long_accel", "vert_accel"]:
        val = _number(item.get(ch))
        if val is not None:
            _set_number(item, f"{ch}_g", val / 9.81)


def _compute_kinematic_slip_angles(item: dict[str, Any]) -> None:
    """Estimate front and rear slip angles using local velocity and geometry.
    Requires local frame velocities (VelocityX/Z) and axle-to-CG distances.
    """
    from racelab_engine.analysis.tire_dynamics import (
        front_slip_angle_rad, rear_slip_angle_rad, slip_angle_balance_rad
    )
    # iRacing: VelocityZ is forward, VelocityX is sideways
    vx = _number(item.get("velocity_z")) or _number(item.get("speed_mps"))
    vy = _number(item.get("velocity_x"))
    r = _number(item.get("yaw_rate"))
    steer = _number(item.get("steering_rad"))
    a = _number(item.get("front_axle_to_cg_m"))
    b = _number(item.get("rear_axle_to_cg_m"))
    
    if vx and vx > 0.1 and vy is not None and r is not None and steer is not None and a and b:
        af_rad, _ = front_slip_angle_rad(steer, vx, vy, r, a)
        ar_rad, _ = rear_slip_angle_rad(vx, vy, r, b)
        bal_rad, _ = slip_angle_balance_rad(af_rad, ar_rad)
        
        if af_rad is not None:
            _set_number(item, "front_slip_angle_deg", math.degrees(af_rad))
        if ar_rad is not None:
            _set_number(item, "rear_slip_angle_deg", math.degrees(ar_rad))
        if bal_rad is not None:
            _set_number(item, "slip_angle_balance_deg", math.degrees(bal_rad))


def _compute_platform_angles(item: dict[str, Any]) -> None:
    """Estimate platform pitch/roll angles from ride height differences.
    These are geometric estimates only — not true inertial angles.

    Uses geometry.py for SI-first math with motion-ratio hooks.
    Geometry estimate assumes 1:1 motion ratio until setup data provides it.
    """
    from racelab_engine.analysis.geometry import compute_pitch_deg, compute_roll_deg, ride_height_mm_to_m
    wb_m = _number(item.get("wheelbase_m"))
    ftw = _number(item.get("front_track_width_m"))
    rtw = _number(item.get("rear_track_width_m"))
    tw_m = ftw or rtw or ((ftw + rtw) / 2.0 if ftw and rtw else None)

    # Motion ratios (optional setup constants)
    mrf = _number(item.get("motion_ratio_front"))
    mrr = _number(item.get("motion_ratio_rear"))

    fl_mm = _number(item.get("lf_ride_height_mm"))
    fr_mm = _number(item.get("rf_ride_height_mm"))
    rl_mm = _number(item.get("lr_ride_height_mm"))
    rr_mm = _number(item.get("rr_ride_height_mm"))
    has_all_rh = None not in (fl_mm, fr_mm, rl_mm, rr_mm)

    if wb_m and wb_m > 0 and has_all_rh:
        assert fl_mm is not None and fr_mm is not None and rl_mm is not None and rr_mm is not None
        front_m = ride_height_mm_to_m((fl_mm + fr_mm) / 2.0)
        rear_m = ride_height_mm_to_m((rl_mm + rr_mm) / 2.0)
        pitch = compute_pitch_deg(front_m, rear_m, wb_m, front_motion_ratio=mrf, rear_motion_ratio=mrr)
        if pitch is not None:
            _set_number(item, "platform_pitch_deg_from_rh", pitch)

    if tw_m and tw_m > 0 and has_all_rh:
        assert fl_mm is not None and fr_mm is not None and rl_mm is not None and rr_mm is not None
        left_m = ride_height_mm_to_m((fl_mm + rl_mm) / 2.0)
        right_m = ride_height_mm_to_m((fr_mm + rr_mm) / 2.0)
        # Legacy global roll using blended track width
        roll = compute_roll_deg(left_m, right_m, tw_m, left_motion_ratio=mrf, right_motion_ratio=mrf)
        if roll is not None:
            _set_number(item, "platform_roll_deg_from_rh", roll)

        # Front axle roll (uses front track width + front motion ratio)
        if ftw and ftw > 0:
            front_left_m = ride_height_mm_to_m(fl_mm)
            front_right_m = ride_height_mm_to_m(fr_mm)
            front_roll = compute_roll_deg(front_left_m, front_right_m, ftw, left_motion_ratio=mrf, right_motion_ratio=mrf)
            if front_roll is not None:
                _set_number(item, "front_platform_roll_deg_from_rh", front_roll)

        # Rear axle roll (uses rear track width + rear motion ratio)
        if rtw and rtw > 0:
            rear_left_m = ride_height_mm_to_m(rl_mm)
            rear_right_m = ride_height_mm_to_m(rr_mm)
            rear_roll = compute_roll_deg(rear_left_m, rear_right_m, rtw, left_motion_ratio=mrr, right_motion_ratio=mrr)
            if rear_roll is not None:
                _set_number(item, "rear_platform_roll_deg_from_rh", rear_roll)

        # Roll balance (front - rear)
        front_roll_val = _number(item.get("front_platform_roll_deg_from_rh"))
        rear_roll_val = _number(item.get("rear_platform_roll_deg_from_rh"))
        if front_roll_val is not None and rear_roll_val is not None:
            _set_number(item, "platform_roll_balance_deg", front_roll_val - rear_roll_val)


def _compute_ackermann(item: dict[str, Any]) -> None:
    """Compute Ackermann steering channels. Optional — requires wheelbase and curvature."""
    from racelab_engine.analysis.vehicle_dynamics import (
        ackermann_steering_expected_deg as _ase,
        ackermann_steering_error_deg as _ase_err,
        ackermann_scrub_proxy as _asp,
    )
    wb = _number(item.get("wheelbase_m"))
    curv = _number(item.get("curvature_1_per_m"))
    steer = _number(item.get("steering_deg"))

    if wb is not None and curv is not None:
        expected, _ = _ase(wb, curv)
        if expected is not None:
            _set_number(item, "ackermann_steering_expected_deg", expected)

            if steer is not None:
                error, _ = _ase_err(steer, expected)
                if error is not None:
                    _set_number(item, "ackermann_steering_error_deg", error)
                proxy, _ = _asp(steer, expected)
                _set_number(item, "ackermann_scrub_proxy", proxy)


def _compute_camber_bias(item: dict[str, Any]) -> None:
    """Compute camber temp bias channels from carcass temps."""
    CAMBER_BIAS_THRESHOLD_C = 15.0
    for c in ["lf", "rf", "lr", "rr"]:
        inner = _number(item.get(f"{c}_carcass_temp_l"))
        outer = _number(item.get(f"{c}_carcass_temp_r"))
        if inner is not None and outer is not None:
            bias = inner - outer
            _set_number(item, f"{c}_camber_temp_bias_c", bias)
            if abs(bias) < CAMBER_BIAS_THRESHOLD_C:
                item[f"{c}_camber_bias_label"] = "even"
            elif bias > 0:
                item[f"{c}_camber_bias_label"] = "high_inside"
            else:
                item[f"{c}_camber_bias_label"] = "high_outside"


def _apply_derivatives(rows: list[dict[str, Any]]) -> None:
    _max_dynamic_pressure = max(
        (_number(row.get("dynamic_pressure_psf")) or 0.0 for row in rows),
        default=1.0,
    )
    if _max_dynamic_pressure <= 0:
        _max_dynamic_pressure = 1.0

    previous: dict[str, Any] | None = None
    for row in rows:
        dp_psf = _number(row.get("dynamic_pressure_psf")) or 0.0
        row["dynamic_pressure_lap_index"] = dp_psf / _max_dynamic_pressure
        row["dynamic_pressure_index"] = dp_psf / _max_dynamic_pressure  # alias for backward compat

        # Cross-run comparable aero load index
        dp_pa = _number(row.get("dynamic_pressure_pa")) or 0.0
        row["aero_load_index"] = dp_pa / REFERENCE_DYNAMIC_PRESSURE_PA
        row["aero_load_index_180mph"] = dp_pa / REFERENCE_DYNAMIC_PRESSURE_PA

        if previous is None:
            _init_derivative_row(row)
            previous = row
            continue

        _compute_speed_rates(row, previous)
        _compute_stability_scores(row, previous)
        _compute_resistance_indices(row, previous)
        _compute_compression_index(row)
        _compute_dynamic_grade(row)
        previous = row


def _compute_dynamic_grade(row: dict[str, Any]) -> None:
    """Estimate track grade (slope) by comparing acceleration vs GPS speed change.

    Produces optional grade-aware channels alongside existing raw channels.
    All grade values are ESTIMATES — not surveyed elevation.
    """
    from racelab_engine.analysis.vehicle_dynamics import (
        dynamic_grade_rad as _dg_rad,
        dynamic_grade_deg as _dg_deg,
        grade_force_proxy_n as _gf,
        grade_corrected_long_accel_mps2 as _gc,
    )

    ax = _number(row.get("long_accel"))
    dvdt = _number(row.get("speed_rate_mps2"))
    mass = _number(row.get("mass_kg"))

    if ax is not None and dvdt is not None:
        grade_rad, _ = _dg_rad(ax, dvdt)
        grade_deg, _ = _dg_deg(ax, dvdt)

        if grade_rad is not None:
            row["dynamic_grade_rad"] = grade_rad
        if grade_deg is not None:
            row["dynamic_grade_deg"] = grade_deg

        # Grade-corrected longitudinal acceleration
        corrected_accel, _ = _gc(ax, grade_rad)
        if corrected_accel is not None:
            row["grade_corrected_long_accel_mps2"] = corrected_accel

        # Grade force proxy (requires mass)
        if mass is not None and grade_rad is not None:
            force, _ = _gf(mass, grade_rad)
            if force is not None:
                row["grade_force_proxy_n"] = force

        # Grade context label
        if grade_deg is not None:
            row["grade_context_label"] = _grade_context_label(grade_deg)

        # Grade-corrected speed loss (mph/s)
        # grade_accel_mph_s = g * sin(grade_rad) converted from m/s^2 to mph/s
        # 1 m/s^2 = 2.23694 mph/s
        speed_rate = _number(row.get("speed_rate_mph_s"))
        if grade_rad is not None and speed_rate is not None:
            grade_accel_mph_s = 9.81 * math.sin(grade_rad) * MPS_TO_MPH
            row["grade_corrected_speed_loss_mph_s"] = speed_rate - grade_accel_mph_s


def _grade_context_label(grade_deg: float) -> str:
    """Classify grade as uphill/downhill/flat based on dynamic_grade_deg."""
    GRADE_FLAT_THRESHOLD_DEG = 0.5  # ~0.9% grade
    if abs(grade_deg) < GRADE_FLAT_THRESHOLD_DEG:
        return "flat"
    return "uphill" if grade_deg > 0 else "downhill"


def _apply_rolling_aggregates(rows: list[dict[str, Any]], window: int = 60) -> None:
    """Compute trailing-window shock RMS, activity, damper energy, and shock_activity_index."""
    corners = tuple(
        corner
        for corner in _SHOCK_CORNERS
        if any(_number(row.get(f"{corner}_shock_vel_in_s")) is not None for row in rows)
    )
    if not corners:
        return
    buffers: dict[str, list[float]] = {f"{c}_sv": [] for c in corners}

    for row in rows:
        _update_shock_buffers(row, buffers, corners, window)

    _compute_component_averages(rows, corners)


def _apply_gps_projection(rows: list[dict[str, Any]]) -> None:
    origin: tuple[float, float] | None = None
    for row in rows:
        lat = _number(row.get("lat"))
        lon = _number(row.get("lon"))
        if lat is None or lon is None:
            continue
        if abs(lat) > math.pi or abs(lon) > math.pi:
            lat = math.radians(lat)
            lon = math.radians(lon)
        if origin is None:
            origin = (lat, lon)
        lat0, lon0 = origin
        x_m = EARTH_RADIUS_M * math.cos(lat0) * (lon - lon0)
        y_m = EARTH_RADIUS_M * (lat - lat0)
        row["track_x_m"] = x_m
        row["track_y_m"] = y_m
        row["track_x_ft"] = x_m * M_TO_FT
        row["track_y_ft"] = y_m * M_TO_FT


def normalize_telemetry_rows(
    table: Any,
    geometry: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    rows = rows_from_table(table)
    normalized: list[dict[str, Any]] = []

    # Setup constants to inject for physics/geometry math
    physics_keys = [
        "mass_kg", "cg_height_m", "wheelbase_m", "front_track_width_m", 
        "rear_track_width_m", "front_axle_to_cg_m", "rear_axle_to_cg_m", 
        "crr", "motion_ratio_front", "motion_ratio_rear"
    ]

    for row in rows:
        item = dict(row)
        # Inject geometry/physics constants if provided
        if geometry:
            for k in physics_keys:
                if k in geometry and item.get(k) is None:
                    item[k] = geometry[k]
        _apply_row_calculations(item)
        normalized.append(item)

    _apply_derivatives(normalized)
    _finalize_shock_channels(normalized)
    _compute_diffuser_channels(normalized, geometry)
    _apply_rolling_aggregates(normalized)
    _apply_gps_projection(normalized)

    return normalized
