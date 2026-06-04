from __future__ import annotations

import re


TARGET_LABELS = {
    "brake_lock": "brake lock",
    "center_balance": "center balance",
    "center_rotation": "center rotation",
    "center_speed": "center speed",
    "correction_count": "correction count",
    "cfs_height": "CFS height",
    "drag_scrub": "drag/scrub",
    "drive_off": "drive-off",
    "driver_input_timing": "driver input timing",
    "entry_balance": "entry balance",
    "entry_stability": "entry stability",
    "entry_yaw": "entry yaw",
    "exit_yaw": "exit yaw",
    "exit_drive": "exit drive",
    "front_contact": "front contact",
    "front_height": "front height",
    "front_platform_contact": "front platform contact",
    "front_response": "front response",
    "front_slip": "front slip",
    "garage_state": "garage state",
    "high_steering_demand": "high steering demand",
    "lap_falloff": "lap falloff",
    "long_run_falloff": "long-run falloff",
    "low_straight_speed": "low straight speed",
    "phase_balance": "phase balance",
    "platform_rate": "platform rate",
    "platform_stability": "platform stability",
    "poor_drive_off": "poor drive-off",
    "rear_height": "rear height",
    "rear_float": "rear float",
    "rear_scrape_margin": "rear scrape margin",
    "rear_slip": "rear slip",
    "rear_tire_trend": "rear tire trend",
    "rf_tire_temp": "RF tire temp",
    "ride_height_trace": "ride-height trace",
    "scrape": "scrape",
    "speed_loss": "speed loss",
    "speed_trace": "speed trace",
    "steering_correction": "steering correction",
    "steering_trace": "steering trace",
    "steering_load": "steering load",
    "straight_speed": "straight speed",
    "throttle_pickup": "throttle pickup",
    "tight_center": "tight center",
    "tight_exit": "tight exit",
    "tire_overwork": "tire overwork",
    "tire_temp": "tire temperature",
    "tire_temp_spread": "tire temperature spread",
    "tire_trend": "tire trend",
    "transition_yaw": "transition yaw",
    "turn_in_response": "turn-in response",
    "unstable_exit": "unstable exit",
}

SETUP_STRENGTH_LABELS = {
    1: "driver feel / small polish",
    2: "fine tuning",
    3: "medium phase-specific lever",
    4: "strong balance lever",
    5: "major package lever",
}

DIAL_IN_STRENGTH_LABELS = {
    1: "Feel polish",
    2: "Fine-tune",
    3: "Balance swing",
    4: "Big swing",
    5: "Package-level lever",
}


def format_target_label(value: str) -> str:
    return TARGET_LABELS.get(value, value.replace("_", " "))


def format_target_list(values: list[str]) -> str:
    return ", ".join(format_target_label(value) for value in values)


def format_driver_targets(text: str) -> str:
    formatted = text
    for target, label in sorted(TARGET_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        formatted = re.sub(rf"\b{re.escape(target)}\b", label, formatted)
    return formatted
