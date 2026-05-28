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
    "LFSHshockDefl",
    "RFSHshockDefl",
    "LRSHshockDefl",
    "RRSHshockDefl",
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
    "dynamic_grade_deg": "deg",
    "front_slip_angle_deg": "deg",
    "rear_slip_angle_deg": "deg",
    "slip_angle_balance_deg": "deg",
    "track_x_m": "m",
    "track_y_m": "m",
    "track_x_ft": "ft",
    "track_y_ft": "ft",
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
        "description": "Normalized dynamic pressure (0-1 scale relative to max in lap). LAP-RELATIVE index — NOT comparable across runs.",
        "formula": "dynamic_pressure_psf / max(dynamic_pressure_psf in lap)",
        "dependencies": ["dynamic_pressure_psf"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["DYNAMIC_PRESSURE_PEAK"],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
        "comparable_across_runs": False,
    },
    "dynamic_pressure_index": {
        "label": "Dynamic Pressure Index",
        "description": "Alias for dynamic_pressure_lap_index. LAP-RELATIVE — NOT comparable across runs.",
        "formula": "dynamic_pressure_psf / max(dynamic_pressure_psf in lap)",
        "dependencies": ["dynamic_pressure_psf"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["DYNAMIC_PRESSURE_PEAK"],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
        "comparable_across_runs": False,
    },
    "aero_load_index": {
        "label": "Aero Load Index",
        "description": "Cross-run comparable aero load index. Ratio of current dynamic pressure to reference pressure at 180 mph sea level. Safe for Notebook comparisons across runs, tracks, weather, and sessions.",
        "formula": "dynamic_pressure_pa / REFERENCE_DYNAMIC_PRESSURE_PA",
        "dependencies": ["dynamic_pressure_pa"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [AERO_PLATFORM_CHECK],
        "comparable_across_runs": True,
    },
    "aero_load_index_180mph": {
        "label": "Aero Load Index (180 mph ref)",
        "description": "Alias for aero_load_index. Cross-run comparable.",
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
        "description": "Splitter risk: 1.0 = scrape, 0.92 = critical (<3mm), 0.72 = high (<6mm), 0.38 = watch (<10mm), 0.08 = safe",
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
        "description": "Composite shock activity score from velocity magnitude and peaks.",
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
        "description": "Rate of CFS ride height change over time. Higher = less stable platform.",
        "dependencies": ["cfs_ride_height_in", "session_time"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": ["PLATFORM_COMPRESSION"],
        "used_by_recommendations": [PLATFORM_SCRUB_TEST],
    },
    "rake_stability_score": {
        "label": "Rake Stability",
        "description": "Rate of center rake change over time. Higher = less stable rake.",
        "dependencies": ["center_rake_fs_in", "session_time"],
        "used_by_charts": [AERO_PLATFORM],
        "used_by_events": [],
        "used_by_recommendations": [RIDE_HEIGHT_REVIEW],
    },
    "platform_risk_score": {
        "label": "Platform Risk Score",
        "description": "Alias for CFS risk score. Higher = riskier splitter margin.",
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
        "description": "ESTIMATE — track slope (grade) angle derived by comparing sensor longitudinal acceleration vs GPS speed derivative. Positive = uphill, negative = downhill.",
        "formula": "asin((long_accel - speed_rate_mps2) / 9.81)",
        "dependencies": ["long_accel", "speed_rate_mps2"],
        "used_by_charts": [SPEED_RPM_PULL],
        "used_by_events": [],
        "used_by_recommendations": [],
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
    "LFSHshockDefl": "lf_shock_defl",
    "RFSHshockDefl": "rf_shock_defl",
    "LRSHshockDefl": "lr_shock_defl",
    "RRSHshockDefl": "rr_shock_defl",
}

_SHOCK_VEL_KEYS: dict[str, str] = {
    "LFSHshockVel": "lf_shock_vel",
    "RFSHshockVel": "rf_shock_vel",
    "LRSHshockVel": "lr_shock_vel",
    "RRSHshockVel": "rr_shock_vel",
}

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
        sv = _number(row.get(f"{corner}_shock_vel_in_s")) or 0.0
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
            values = [_number(row.get(key)) or 0.0 for key in corner_keys]
            row[component] = sum(values) / len(values)


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

    if wb_m and wb_m > 0:
        fl_mm = _number(item.get("lf_ride_height_mm"))
        fr_mm = _number(item.get("rf_ride_height_mm"))
        rl_mm = _number(item.get("lr_ride_height_mm"))
        rr_mm = _number(item.get("rr_ride_height_mm"))
        
        if None not in (fl_mm, fr_mm, rl_mm, rr_mm):
            assert fl_mm is not None and fr_mm is not None and rl_mm is not None and rr_mm is not None
            front_m = ride_height_mm_to_m((fl_mm + fr_mm) / 2.0)
            rear_m = ride_height_mm_to_m((rl_mm + rr_mm) / 2.0)
            pitch = compute_pitch_deg(front_m, rear_m, wb_m, front_motion_ratio=mrf, rear_motion_ratio=mrr)
            if pitch is not None:
                _set_number(item, "platform_pitch_deg_from_rh", pitch)

    if tw_m and tw_m > 0:
        fl_mm = _number(item.get("lf_ride_height_mm"))
        fr_mm = _number(item.get("rf_ride_height_mm"))
        rl_mm = _number(item.get("lr_ride_height_mm"))
        rr_mm = _number(item.get("rr_ride_height_mm"))
        
        if None not in (fl_mm, fr_mm, rl_mm, rr_mm):
            assert fl_mm is not None and fr_mm is not None and rl_mm is not None and rr_mm is not None
            left_m = ride_height_mm_to_m((fl_mm + rl_mm) / 2.0)
            right_m = ride_height_mm_to_m((fr_mm + rr_mm) / 2.0)
            # Use front track width for simplicity as roll ref if only one available
            roll = compute_roll_deg(left_m, right_m, tw_m, left_motion_ratio=mrf, right_motion_ratio=mrf)
            if roll is not None:
                _set_number(item, "platform_roll_deg_from_rh", roll)


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
    """Estimate track grade (slope) by comparing acceleration vs GPS speed change."""
    ax = _number(row.get("long_accel"))
    dvdt = _number(row.get("speed_rate_mps2"))
    if ax is not None and dvdt is not None:
        # ax_sensor = dv/dt + g*sin(theta)
        # sin(theta) = (ax_sensor - dv/dt) / g
        sin_theta = (ax - dvdt) / 9.81
        sin_theta = max(-1.0, min(1.0, sin_theta))
        grade_rad = math.asin(sin_theta)
        row["dynamic_grade_deg"] = math.degrees(grade_rad)


def _apply_rolling_aggregates(rows: list[dict[str, Any]], window: int = 60) -> None:
    """Compute trailing-window shock RMS, activity, damper energy, and shock_activity_index."""
    corners = ("lf", "rf", "lr", "rr")
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
    _apply_rolling_aggregates(normalized)
    _apply_gps_projection(normalized)

    return normalized
