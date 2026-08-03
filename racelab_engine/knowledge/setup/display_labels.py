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

SUCCESS_TARGET_WORDING = {
    "brake_stability": "the car needs fewer corrections under braking",
    "center_rotation": "center balance moves closer to neutral",
    "center_speed": "center speed improves beyond normal lap variation",
    "drive_off": "throttle pickup is cleaner and exit acceleration improves",
    "entry_rotation": "entry rotation moves closer to neutral",
    "entry_stability": "entry becomes calmer without adding push",
    "entry_yaw": "entry rotation moves closer to neutral",
    "exit_yaw": "exit rotation moves closer to neutral",
    "front_contact": "front contact events decrease in the same track zone",
    "front_height": "front ride-height margin improves in the problem zone",
    "rpm_trace": "RPM stays in the useful range without reaching the limiter too early",
    "scrape": "repeatable scrape events decrease",
    "speed_loss": "speed loss through the problem zone decreases",
    "speed_trace": "speed improves at the same track position",
    "steering_trace": "steering demand decreases for the same corner",
    "straight_speed": "straight speed improves without losing too much drive-off",
    "turn_in_response": "turn-in response improves without making entry nervous",
}

WATCH_TARGET_WORDING = {
    "brake_entry_instability": "the rear becomes less stable under braking",
    "diffuser_choke_or_stall": "rear-height proxy behavior becomes less stable or speed falls",
    "front_feed_instability": "front ride-height behavior becomes less stable",
    "front_platform_contact": "front contact events increase",
    "exit_yaw": "exit balance moves farther from neutral",
    "loose_entry": "entry becomes looser",
    "loose_exit": "exit becomes looser",
    "low_straight_speed": "straight speed falls beyond normal run variation",
    "poor_drive_off": "drive-off acceleration gets worse",
    "rear_float": "the rear feels less planted at speed",
    "rear_scrape": "rear scrape events increase",
    "rear_height": "rear ride-height behavior moves the wrong way",
    "rf_tire_temp": "RF tire temperature rises without a balance improvement",
    "ride_height_trace": "ride-height movement becomes less controlled",
    "scrape": "scrape events increase",
    "speed_loss": "speed falls in the same track zone",
    "tight_center": "center push increases",
    "tight_entry": "entry push increases",
    "tight_exit": "exit push increases",
    "tire_overwork": "tire temperature or wear increases without a pace gain",
    "unstable_exit": "throttle pickup requires more corrections",
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


def format_success_target(value: str) -> str:
    return SUCCESS_TARGET_WORDING.get(value, f"{format_target_label(value)} moves in the intended direction")


def format_watch_target(value: str) -> str:
    return WATCH_TARGET_WORDING.get(value, f"{format_target_label(value)} gets worse")


def format_driver_targets(text: str) -> str:
    formatted = text
    for target, label in sorted(TARGET_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        formatted = re.sub(rf"\b{re.escape(target)}\b", label, formatted)
    return formatted
