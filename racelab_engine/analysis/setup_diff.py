from __future__ import annotations

from typing import Any

from racelab_engine.analysis.comparison import ContextChange, SetupChange, SetupGroup

SETUP_GROUPS: dict[str, tuple[SetupGroup, str]] = {
    "lf_ride_height_mm": ("front_platform", "LF Ride Height"),
    "rf_ride_height_mm": ("front_platform", "RF Ride Height"),
    "lr_ride_height_mm": ("rear_platform", "LR Ride Height"),
    "rr_ride_height_mm": ("rear_platform", "RR Ride Height"),
    "lf_front_spring_n_per_mm": ("springs", "LF Spring"),
    "rf_front_spring_n_per_mm": ("springs", "RF Spring"),
    "lr_rear_spring_n_per_mm": ("springs", "LR Spring"),
    "rr_rear_spring_n_per_mm": ("springs", "RR Spring"),
    "nose_weight_percent": ("weight_distribution", "Nose Weight"),
    "cross_weight_percent": ("weight_distribution", "Cross Weight"),
    "tape_percent": ("aero_cooling", "Tape"),
    "rear_end_ratio": ("gearing", "Rear Gear"),
    "front_brake_bias_percent": ("alignment", "Brake Bias"),
    "steering_ratio": ("alignment", "Steering Ratio"),
    "steering_offset_deg": ("alignment", "Steering Offset"),
}


def diff_setups(baseline_setup: Any, test_setup: Any) -> list[SetupChange]:
    changes: list[SetupChange] = []

    def _get(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if hasattr(obj, key):
            return getattr(obj, key)
        if not isinstance(obj, dict):
            return None
        if key in obj:
            return obj.get(key)
        for value in obj.values():
            nested_value = _get(value, key)
            if nested_value is not None:
                return nested_value
        return None

    for key, (group, label) in SETUP_GROUPS.items():
        bl = _get(baseline_setup, key)
        t = _get(test_setup, key)
        if bl is None and t is None:
            continue
        if bl == t:
            continue
        delta_str = None
        sig: Any = "minor"
        try:
            if bl is not None and t is not None:
                d = float(t) - float(bl)
                delta_str = f"{d:+.3f}"
                sig = "major" if abs(d) >= 5 else ("moderate" if abs(d) >= 1 else "minor")
        except (TypeError, ValueError):
            delta_str = str(t) if t is not None else "removed"

        changes.append(SetupChange(
            setup_key=key, label=label, group=group,
            baseline_value=bl, test_value=t,
            unit=None, delta=delta_str, significance=sig,
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
