from __future__ import annotations

import re
from typing import Any

import yaml  # type: ignore[import-untyped]

from racelab_engine.models.session import SessionSummary
from racelab_engine.models.setup import SetupSnapshot


def parse_session_yaml(yaml_text: str) -> dict[str, Any]:
    if not yaml_text.strip():
        return {}
    parsed = yaml.safe_load(yaml_text)
    return parsed if isinstance(parsed, dict) else {}


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    return next((mapping[key] for key in keys if key in mapping and mapping[key] not in (None, "")), None)


def _nested(mapping: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = mapping
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})
    return current if isinstance(current, dict) else {}


def _float_from_text(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
    return float(match[0]) if match else None


def _string_or_none(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _find_value_by_label(data: Any, label_fragments: tuple[str, ...]) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            key_text = str(key).lower()
            if all(fragment in key_text for fragment in label_fragments):
                return value
            found = _find_value_by_label(value, label_fragments)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_value_by_label(item, label_fragments)
            if found is not None:
                return found
    return None


def _find_driver_entry(driver: dict[str, Any]) -> dict[str, Any]:
    car_idx = driver.get("DriverCarIdx")
    drivers = driver.get("Drivers", [])
    if isinstance(drivers, list):
        for entry in drivers:
            if not isinstance(entry, dict):
                continue
            if car_idx is not None and entry.get("CarIdx") == car_idx:
                return entry
        for entry in drivers:
            if isinstance(entry, dict):
                return entry
    return {}


def _setup_chassis_section(car_setup: dict[str, Any], section: str) -> dict[str, Any]:
    chassis = car_setup.get("Chassis", {})
    if not isinstance(chassis, dict):
        return {}
    value = chassis.get(section, {})
    return value if isinstance(value, dict) else {}


def _setup_value(car_setup: dict[str, Any], section: str, key: str) -> Any:
    return _setup_chassis_section(car_setup, section).get(key)


def _steering_ratio_from_yaml(yaml_text: str, fallback: Any) -> str | None:
    for line in yaml_text.splitlines():
        if re.match(r"\s*SteeringRatio\s*:", line):
            value = line.split(":", 1)[1].strip().strip('"')
            return value or None
        if re.match(r"\s*Steering ratio\s*:", line, flags=re.IGNORECASE):
            value = line.split(":", 1)[1].strip().strip('"')
            return value or None
    if fallback in (None, ""):
        return None
    if isinstance(fallback, int) and fallback == 601:
        return "10:1"
    return str(fallback)


def _gather_session_data(data: dict[str, Any]) -> dict[str, Any]:
    weekend = _nested(data, "WeekendInfo")
    driver = _nested(data, "DriverInfo")
    driver_entry = _find_driver_entry(driver)
    session_info = _nested(data, "SessionInfo")
    sessions = session_info.get("Sessions", []) if isinstance(session_info, dict) else []
    current_session = sessions[0] if isinstance(sessions, list) and sessions and isinstance(sessions[0], dict) else {}
    weather = _nested(data, "WeatherInfo")
    car_name = _first(driver, "DriverCarName", "CarScreenName", "CarName") or _first(driver_entry, "CarScreenName", "CarName")
    car_path = _first(driver, "DriverCarPath", "CarPath") or _first(driver_entry, "CarPath")
    track_name = _first(weekend, "TrackName", "TrackID", "TrackConfigName")
    track_display_name = _first(weekend, "TrackDisplayName", "TrackName")
    return {
        "weekend": weekend, "driver": driver, "driver_entry": driver_entry,
        "session_info": session_info, "current_session": current_session, "weather": weather,
        "car_name": car_name, "car_path": car_path,
        "track_name": track_name, "track_display_name": track_display_name,
    }


def extract_session_summary(yaml_text: str, run_id: str = "unassigned") -> SessionSummary:
    data = parse_session_yaml(yaml_text)
    g = _gather_session_data(data)
    w, dr, _de, si, cs, we = g["weekend"], g["driver"], g["driver_entry"], g["session_info"], g["current_session"], g["weather"]

    return SessionSummary(
        run_id=run_id,
        sim_date_time=_string_or_none(_first(w, "WeekendStartTime", "SessionStartTime", "Date")),
        car_name=g["car_name"],
        car_path=str(g["car_path"]) if g["car_path"] is not None else None,
        track_name=g["track_name"],
        track_display_name=g["track_display_name"],
        track_id_or_path=str(_first(w, "TrackID", "TrackName")) if w else None,
        session_type=_first(cs, "SessionType", "SessionName") or _first(si, "SessionType", "SessionName") or _first(w, "EventType"),
        weather_summary=_first(we, "Skies", "WeatherType") or _first(w, "TrackSkies"),
        air_temp=_float_from_text(_first(we, "AirTemp", "AirTemperature") or _first(w, "TrackAirTemp")),
        track_temp=_float_from_text(_first(we, "TrackTemp", "TrackTemperature") or _first(w, "TrackSurfaceTemp")),
        wind_speed=_float_from_text(_first(we, "WindSpeed") or _first(w, "TrackWindVel")),
        wind_direction=_float_from_text(_first(we, "WindDir", "WindDirection") or _first(w, "TrackWindDir")),
        air_pressure=_float_from_text(_first(we, "AirPressure") or _first(w, "TrackAirPressure")),
        setup_name=(
            _first(data, "SetupName")
            or _first(dr, "DriverSetupName")
            or _first(_nested(data, "CarSetup"), "SetupName")
        ),
        setup_passed_tech=bool(_first(dr, "DriverSetupPassedTech")) if _first(dr, "DriverSetupPassedTech") is not None else None,
        setup_modified=bool(_first(dr, "DriverSetupIsModified")) if _first(dr, "DriverSetupIsModified") is not None else None,
        notes=["Extracted from provided iRacing session YAML text"],
    )


def _setup_value_or_label(car_setup: dict[str, Any], section: str, key: str, label_fragments: tuple[str, ...]) -> Any:
    return _setup_value(car_setup, section, key) or _find_value_by_label(car_setup or {}, label_fragments)


def _setup_extracted_values(car_setup: dict[str, Any], source: dict[str, Any], yaml_text: str) -> dict[str, Any]:
    front = _setup_chassis_section(car_setup, "Front")
    return {
        "raw_source": "CarSetup" if car_setup else "session_yaml",
        "tape_percent": _float_from_text(front.get("TapeConfiguration") or _find_value_by_label(source, ("tape",))),
        "rear_end_ratio": _float_from_text(front.get("RearEndRatio") or _find_value_by_label(source, ("rear", "ratio"))),
        "lf_ride_height_mm": _float_from_text(_setup_value_or_label(car_setup, "LeftFront", "RideHeight", ("lf", "ride", "height"))),
        "rf_ride_height_mm": _float_from_text(_setup_value_or_label(car_setup, "RightFront", "RideHeight", ("rf", "ride", "height"))),
        "lr_ride_height_mm": _float_from_text(_setup_value_or_label(car_setup, "LeftRear", "RideHeight", ("lr", "ride", "height"))),
        "rr_ride_height_mm": _float_from_text(_setup_value_or_label(car_setup, "RightRear", "RideHeight", ("rr", "ride", "height"))),
        "lf_front_spring_n_per_mm": _float_from_text(_setup_value_or_label(car_setup, "LeftFront", "SpringRate", ("lf", "spring"))),
        "rf_front_spring_n_per_mm": _float_from_text(_setup_value_or_label(car_setup, "RightFront", "SpringRate", ("rf", "spring"))),
        "lr_rear_spring_n_per_mm": _float_from_text(_setup_value_or_label(car_setup, "LeftRear", "SpringRate", ("lr", "spring"))),
        "rr_rear_spring_n_per_mm": _float_from_text(_setup_value_or_label(car_setup, "RightRear", "SpringRate", ("rr", "spring"))),
        "nose_weight_percent": _float_from_text(front.get("NoseWeight") or _find_value_by_label(source, ("nose", "weight"))),
        "cross_weight_percent": _float_from_text(front.get("CrossWeight") or _find_value_by_label(source, ("cross", "weight"))),
        "front_brake_bias_percent": _float_from_text(front.get("FrontBrakeBias") or _find_value_by_label(source, ("brake", "bias"))),
        "steering_ratio": _steering_ratio_from_yaml(yaml_text, front.get("SteeringRatio") or _find_value_by_label(source, ("steering", "ratio"))),
        "steering_offset_deg": _float_from_text(front.get("SteeringOffset") or _find_value_by_label(source, ("steering", "offset"))),
    }


def extract_setup_snapshot(yaml_text: str, run_id: str = "unassigned") -> SetupSnapshot:
    data = parse_session_yaml(yaml_text)
    car_setup = _nested(data, "CarSetup")
    driver = _nested(data, "DriverInfo")
    source = car_setup or data
    ev = _setup_extracted_values(car_setup, source, yaml_text)

    return SetupSnapshot(
        setup_id=f"{run_id}:setup",
        run_id=run_id,
        setup_name=_first(source, "SetupName", "Name") or _first(driver, "DriverSetupName"),
        setup_json=car_setup,
        extracted_values=ev,
        tape_percent=ev["tape_percent"],
        rear_end_ratio=ev["rear_end_ratio"],
        lf_ride_height_mm=ev["lf_ride_height_mm"],
        rf_ride_height_mm=ev["rf_ride_height_mm"],
        lr_ride_height_mm=ev["lr_ride_height_mm"],
        rr_ride_height_mm=ev["rr_ride_height_mm"],
        lf_front_spring_n_per_mm=ev["lf_front_spring_n_per_mm"],
        rf_front_spring_n_per_mm=ev["rf_front_spring_n_per_mm"],
        lr_rear_spring_n_per_mm=ev["lr_rear_spring_n_per_mm"],
        rr_rear_spring_n_per_mm=ev["rr_rear_spring_n_per_mm"],
        nose_weight_percent=ev["nose_weight_percent"],
        cross_weight_percent=ev["cross_weight_percent"],
        front_brake_bias_percent=ev["front_brake_bias_percent"],
        steering_ratio=ev["steering_ratio"],
        steering_offset_deg=ev["steering_offset_deg"],
    )
