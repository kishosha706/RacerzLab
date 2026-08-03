from __future__ import annotations

from typing import Any, cast

from racelab_engine.analysis.comparison import ContextChange, SetupChange, SetupGroup
from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    assess_setup_change,
    display_setup_value,
    format_setup_delta,
)

SETUP_GROUPS: dict[str, tuple[SetupGroup, str]] = {
    key: (cast(SetupGroup, spec.group), spec.label)
    for key, spec in SETUP_CONTROL_SPECS.items()
}

SETUP_VALUE_ALIASES: dict[str, tuple[str, ...]] = {
    "rear_end_ratio": ("final_drive_ratio", "FinalDriveRatio", "RearEndRatio"),
    "steering_ratio": ("steering_pinion_mm", "SteeringPinion", "SteeringRatio"),
    "tape_percent": ("TapeConfiguration", "Tape"),
}


def setup_control_value(setup: Any, key: str) -> Any:
    if setup is None:
        return None
    if hasattr(setup, key):
        value = getattr(setup, key)
        if value is not None:
            return value
        if hasattr(setup, "model_dump"):
            setup = setup.model_dump()
    if not isinstance(setup, dict):
        return None
    candidate_keys = (key, *SETUP_VALUE_ALIASES.get(key, ()))
    for candidate in candidate_keys:
        if candidate in setup and setup.get(candidate) is not None:
            return setup.get(candidate)
    for value in setup.values():
        nested_value = setup_control_value(value, key)
        if nested_value is not None:
            return nested_value
    return None


def setup_control_coverage(setup: Any) -> tuple[int, int, list[str]]:
    missing = [key for key in SETUP_GROUPS if setup_control_value(setup, key) is None]
    return len(SETUP_GROUPS) - len(missing), len(SETUP_GROUPS), missing


def setup_controls_comparable(baseline_setup: Any, test_setup: Any) -> bool:
    if baseline_setup is None or test_setup is None:
        return False
    matched_controls = 0
    for key in SETUP_GROUPS:
        baseline_value = setup_control_value(baseline_setup, key)
        test_value = setup_control_value(test_setup, key)
        if (baseline_value is None) != (test_value is None):
            return False
        if baseline_value is not None:
            matched_controls += 1
    return matched_controls > 0


def diff_setups(baseline_setup: Any, test_setup: Any) -> list[SetupChange]:
    changes: list[SetupChange] = []

    for key, (group, label) in SETUP_GROUPS.items():
        bl = setup_control_value(baseline_setup, key)
        t = setup_control_value(test_setup, key)
        if bl is None and t is None:
            continue
        if bl == t:
            continue
        spec = SETUP_CONTROL_SPECS[key]
        assessment = assess_setup_change(key, bl, t)
        delta_str = format_setup_delta(key, assessment, bl, t)
        display_bl = display_setup_value(key, bl)
        display_test = display_setup_value(key, t)
        unit = None if key == "steering_ratio" and isinstance(bl, str) else spec.display_unit

        changes.append(SetupChange(
            setup_key=key, label=label, group=group,
            baseline_value=display_bl, test_value=display_test,
            unit=unit, delta=delta_str, significance=assessment.label,
            magnitude_basis=assessment.basis,
            relative_delta_percent=assessment.relative_delta_percent,
            related_to_target_issue=group in ("front_platform", "rear_platform", "shocks", "springs"),
        ))
    return changes


def diff_context(
    baseline_session: Any,
    test_session: Any,
    baseline_lap_valid: bool = True,
    test_lap_valid: bool = True,
) -> list[ContextChange]:
    changes: list[ContextChange] = []

    def _get(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if hasattr(obj, key):
            return getattr(obj, key)
        return obj.get(key) if isinstance(obj, dict) else None

    checks = [
        ("air_temp", "Air Temp", None, 5.0, "Weather changed: air temp delta > 5°C"),
        ("track_temp", "Track Temp", None, 5.0, "Weather changed: track temp delta > 5°C"),
        ("air_density", "Air Density", None, 0.05, "Air density changed meaningfully"),
        ("wind_speed", "Wind Speed", None, 5.0, "Wind speed changed"),
    ]
    for key, label, _unit, threshold, warning in checks:
        bl = _get(baseline_session, key)
        t = _get(test_session, key)
        if bl is None or t is None:
            continue
        try:
            if abs(float(t) - float(bl)) > threshold:
                changes.append(ContextChange(key=key, label=label, baseline_value=bl,
                    test_value=t, warning=warning, is_problem=True))
        except (TypeError, ValueError):
            changes.append(ContextChange(key=key, label=label, baseline_value=bl,
                test_value=t, warning=f"Could not compare {label}.", is_problem=True))

    if not baseline_lap_valid:
        changes.append(ContextChange(key="baseline_lap", label="Baseline Lap",
            warning="Baseline lap is not valid/useful.", is_problem=True))
    if not test_lap_valid:
        changes.append(ContextChange(key="test_lap", label="Test Lap",
            warning="Test lap is not valid/useful.", is_problem=True))

    bl_dur = _get(baseline_session, "duration_seconds")
    t_dur = _get(test_session, "duration_seconds")
    if bl_dur is not None and t_dur is not None and bl_dur > 0:
        if abs(float(t_dur) - float(bl_dur)) / float(bl_dur) > 0.3:
            changes.append(ContextChange(key="run_length", label="Run Length",
                warning="Run length changed significantly.", is_problem=True))

    return changes
