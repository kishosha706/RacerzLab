from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    DidItWorkVerdict,
    DriverComparison,
    PaceComparison,
    SetupChange,
    TargetZoneComparison,
    TestDisciplineResult,
)
from racelab_engine.analysis.setup_controls import canonical_setup_value_key
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.recording_identity import (
    RecordingIdentityError,
    require_independent_recordings,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository

CONTROL_TO_SETUP_AREAS: dict[str, tuple[str, ...]] = {
    "lf_ride_height_mm": ("front_ride_height_platform", "ride_height", "diffuser_platform"),
    "rf_ride_height_mm": ("front_ride_height_platform", "ride_height", "diffuser_platform"),
    "lr_ride_height_mm": ("rear_ride_height_platform", "ride_height", "diffuser_platform"),
    "rr_ride_height_mm": ("rear_ride_height_platform", "ride_height", "diffuser_platform"),
    "lf_front_spring_n_per_mm": ("spring_rate",),
    "rf_front_spring_n_per_mm": ("spring_rate",),
    "lr_rear_spring_n_per_mm": ("spring_rate",),
    "rr_rear_spring_n_per_mm": ("spring_rate",),
    "nose_weight_percent": ("nose_weight",),
    "cross_weight_percent": ("cross_weight",),
    "tape_percent": ("aero_cooling",),
    "rear_end_ratio": ("final_drive",),
    "front_brake_bias_percent": ("brake_bias",),
    "steering_ratio": ("steering_response",),
    "steering_offset_deg": ("steering_response",),
}


def _source_runs_are_independent(
    source_run_ids: list[str] | tuple[str, ...],
    *,
    db_path: str | Path | None,
) -> bool:
    """Require complete source identities and reject recording aliases.

    Durable learning cannot treat an unknown legacy run as an independent
    observation.  Every source run must resolve to one immutable recording
    SHA before it can affect recurrence, response summaries, or fitted models.
    """

    ordered = tuple(source_run_ids)
    source_by_run = RaceLabRepository(db_path).get_recording_sha256s(ordered)
    if len(source_by_run) != len(set(ordered)):
        return False
    try:
        require_independent_recordings(source_by_run, ordered_run_ids=ordered)
    except RecordingIdentityError:
        return False
    return True


@dataclass(frozen=True)
class SetupResponseContext:
    """Exact compatibility key required before history can affect advice."""

    driver_id: str
    car_name: str
    car_version: str
    track_name: str
    track_configuration: str
    track_version: str
    sim_build: str
    weather_bucket: str
    tire_age_bucket: str
    fuel_bucket: str
    run_type: str
    package_archetype: str
    objective: str
    baseline_setup_fingerprint: str
    tire_compound: str

    @property
    def is_complete(self) -> bool:
        return all(str(value).strip() for value in asdict(self).values())

    @property
    def key(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


def _median_number(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
    values: list[float] = []
    for row in rows:
        for key in keys:
            number = _number(row.get(key))
            if number is not None:
                values.append(number)
                break
    return median(values) if values else None


def _mode_text(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> str | None:
    values: list[str] = []
    for row in rows:
        value = next((row.get(key) for key in keys if row.get(key) is not None), None)
        if value is not None and str(value).strip():
            values.append(str(value).strip())
    return Counter(values).most_common(1)[0][0] if values else None


def _bucket(value: float | None, width: float, unit: str) -> str:
    if value is None:
        return ""
    low = math.floor(value / width) * width
    high = low + width
    return f"{low:g}-{high:g} {unit}"


def build_setup_response_context(
    *,
    compatibility_identity: dict[str, Any],
    rows: list[dict[str, Any]],
    baseline_setup: dict[str, Any] | None,
    package_archetype: str,
    objective: str,
) -> SetupResponseContext | None:
    """Build a complete, version-sensitive memory key or fail closed."""
    air_temp = _median_number(rows, ("air_temp", "AirTemp"))
    track_temp = _median_number(rows, ("track_temp", "TrackTemp"))
    wind = _median_number(rows, ("wind_vel", "WindVel"))
    fuel = _median_number(rows, ("fuel_level", "FuelLevel"))
    tire_age = _median_number(
        rows,
        (
            "lf_tire_distance_m",
            "rf_tire_distance_m",
            "lr_tire_distance_m",
            "rr_tire_distance_m",
        ),
    )
    compound = _mode_text(rows, ("player_tire_compound", "tire_compound", "PlayerTireCompound"))
    weather_parts = (
        _bucket(air_temp, 2.0, "C air"),
        _bucket(track_temp, 2.0, "C track"),
        _bucket(wind, 1.0, "m/s wind"),
    )
    if not all(weather_parts):
        return None
    setup_payload = _physical_setup_payload(baseline_setup)
    if not setup_payload:
        return None
    setup_json = json.dumps(setup_payload, sort_keys=True, default=str, separators=(",", ":"))
    context = SetupResponseContext(
        driver_id=str(compatibility_identity.get("driver_user_id") or ""),
        car_name=str(compatibility_identity.get("car_name") or ""),
        car_version=str(compatibility_identity.get("car_version") or ""),
        track_name=str(compatibility_identity.get("track_name") or ""),
        track_configuration=str(compatibility_identity.get("track_configuration_name") or ""),
        track_version=str(compatibility_identity.get("track_version") or ""),
        sim_build=str(compatibility_identity.get("iracing_build_version") or ""),
        weather_bucket="/".join(weather_parts),
        tire_age_bucket=_bucket(tire_age, 5_000.0, "m tire distance"),
        fuel_bucket=_bucket(fuel, 5.0, "fuel units"),
        run_type=str(compatibility_identity.get("session_type") or ""),
        package_archetype=package_archetype,
        objective=objective,
        baseline_setup_fingerprint=hashlib.sha256(setup_json.encode()).hexdigest(),
        tire_compound=compound or "",
    )
    return context if context.is_complete else None


_SETUP_METADATA_KEYS = {
    "setup_id", "run_id", "created_at", "updated_at", "setup_name", "source",
}


def _physical_setup_payload(setup: dict[str, Any] | None) -> dict[str, Any]:
    """Remove run identity while retaining the complete physical setup content."""
    if not isinstance(setup, dict):
        return {}

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): clean(child)
                for key, child in value.items()
                if str(key).casefold() not in _SETUP_METADATA_KEYS
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    setup_json = setup.get("setup_json")
    extracted = setup.get("extracted_values")
    if isinstance(setup_json, dict) and setup_json:
        payload: dict[str, Any] = {"setup_json": clean(setup_json)}
        if isinstance(extracted, dict) and extracted:
            payload["extracted_values"] = clean(extracted)
        return payload
    if isinstance(extracted, dict) and extracted:
        return {"extracted_values": clean(extracted)}
    return clean(setup)


def physical_setup_fingerprint(setup: dict[str, Any] | None) -> str | None:
    payload = _physical_setup_payload(setup)
    if not payload:
        return None
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def response_environment_key(context: SetupResponseContext) -> str:
    """Hash exact context without the tested baseline level."""
    payload = asdict(context)
    payload.pop("baseline_setup_fingerprint", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def surrounding_setup_fingerprint(
    setup: dict[str, Any] | None,
    tested_control_key: str,
) -> str | None:
    """Fingerprint the surrounding package while excluding one tested control."""
    payload = _physical_setup_payload(setup)
    if not payload:
        return None
    from racelab_engine.analysis.setup_diff import SETUP_RAW_PATHS, SETUP_VALUE_ALIASES

    target = tested_control_key.casefold()
    aliases = {target, *(value.casefold() for value in SETUP_VALUE_ALIASES.get(tested_control_key, ()))}
    raw_paths = {value.casefold() for value in SETUP_RAW_PATHS.get(tested_control_key, ())}
    raw_leaf_names = {path.rsplit(".", 1)[-1] for path in raw_paths}

    def strip_tested(value: Any, prefix: str = "") -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, child in value.items():
                key_text = str(key)
                path = f"{prefix}.{key_text}" if prefix else key_text
                folded_key = key_text.casefold()
                folded_path = path.casefold()
                if (
                    folded_key in aliases
                    or folded_key in raw_leaf_names
                    or any(folded_path.endswith(raw_path) for raw_path in raw_paths)
                ):
                    continue
                cleaned[key_text] = strip_tested(child, path)
            return cleaned
        if isinstance(value, list):
            return [strip_tested(item, prefix) for item in value]
        return value

    stripped = strip_tested(payload)
    encoded = json.dumps(stripped, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
        value = match.group(0) if match else value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_object(value: Any) -> dict[str, Any] | None:
    try:
        payload = json.loads(value or "{}")
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _json_string_list(value: Any) -> list[str] | None:
    try:
        payload = json.loads(value or "[]")
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(payload, list)
        or any(not isinstance(item, str) or not item.strip() for item in payload)
        or len(set(payload)) != len(payload)
    ):
        return None
    return payload


def _same_optional_number(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    left_number = _number(left)
    right_number = _number(right)
    return bool(
        left_number is not None
        and right_number is not None
        and math.isclose(left_number, right_number, rel_tol=1e-9, abs_tol=1e-9)
    )


def _qualified_setup_response_row(
    row: Any,
    response_context: SetupResponseContext,
    *,
    exact_context: bool,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    """Bind a stored response row to its immutable context and evidence payload."""
    payload = dict(row)
    context_payload = _json_object(payload.get("response_context_json"))
    evidence = _json_object(payload.get("evidence_json"))
    if context_payload is None or evidence is None:
        return None
    try:
        stored_context = SetupResponseContext(**context_payload)
    except (TypeError, ValueError):
        return None
    expected_environment = response_environment_key(response_context)
    stored_environment = response_environment_key(stored_context)
    if (
        not stored_context.is_complete
        or payload.get("response_context_key") != stored_context.key
        or payload.get("environment_context_key") != stored_environment
        or stored_environment != expected_environment
        or exact_context and stored_context != response_context
        or payload.get("car_name") != stored_context.car_name
        or payload.get("track_name") != stored_context.track_name
    ):
        return None

    from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS

    setup_key = str(payload.get("setup_key") or "")
    spec = SETUP_CONTROL_SPECS.get(setup_key)
    comparison_id = str(payload.get("comparison_id") or "")
    source_runs = evidence.get("source_run_ids")
    source_channels = evidence.get("source_channels")
    source_events = evidence.get("evidence_event_ids")
    if (
        spec is None
        or not comparison_id
        or not str(payload.get("surrounding_setup_fingerprint") or "")
        or payload.get("baseline_setup_passed_tech") != 1
        or payload.get("test_setup_passed_tech") != 1
        or payload.get("context_problem_count") != 0
        or evidence.get("evidence_packet_id") != comparison_id
        or evidence.get("evidence_state") != EvidenceState.CONTROLLED_TEST_EFFECT.value
        or not isinstance(source_runs, list)
        or len(source_runs) != 3
        or len(set(source_runs)) != 3
        or any(
            not isinstance(item, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", item) is None
            for item in source_runs
        )
        or source_runs[0] != payload.get("baseline_run_id")
        or source_runs[1] != payload.get("test_run_id")
        or not isinstance(source_channels, list)
        or not source_channels
        or any(
            not isinstance(item, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", item) is None
            for item in source_channels
        )
        or not isinstance(source_events, list)
        or not source_events
        or any(
            not isinstance(item, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", item) is None
            for item in source_events
        )
    ):
        return None
    expected_provenance = hashlib.sha256(
        "|".join([*source_runs, setup_key]).encode()
    ).hexdigest()
    start = _number(payload.get("target_zone_start_pct"))
    end = _number(payload.get("target_zone_end_pct"))
    baseline = _number(payload.get("baseline_value"))
    test = _number(payload.get("test_value"))
    numeric_delta = _number(payload.get("numeric_delta"))
    if (
        payload.get("source_run_provenance_key") != expected_provenance
        or start is None
        or end is None
        or not 0.0 <= start < end <= 100.0
        or baseline is None
        or test is None
        or numeric_delta is None
        or not math.isclose(test - baseline, numeric_delta, rel_tol=1e-9, abs_tol=1e-9)
        or int(payload.get("direction_sign") or 0) != (1 if numeric_delta > 0.0 else -1)
        or payload.get("observation_id")
        != _observation_id(comparison_id, setup_key, start, end)
        or payload.get("setup_unit") != spec.display_unit
        or payload.get("setup_value_kind")
        != ("continuous" if spec.step_strategy == "numeric_test" else "discrete")
    ):
        return None
    observed = evidence.get("observed_phase_effects")
    if not isinstance(observed, dict) or any(
        not _same_optional_number(observed.get(evidence_key), payload.get(row_key))
        for evidence_key, row_key in (
            ("target_zone_start_pct", "target_zone_start_pct"),
            ("target_zone_end_pct", "target_zone_end_pct"),
            ("median_lap_delta_s", "median_lap_delta_s"),
            ("target_speed_delta_mph", "target_speed_delta_mph"),
            ("cfs_delta_in", "cfs_delta_in"),
        )
    ):
        return None
    return payload, evidence, context_payload


def _channel_delta(zone: TargetZoneComparison, channel: str) -> float | None:
    item: ComparedChannelDelta | None = next((delta for delta in zone.channel_deltas if delta.channel == channel), None)
    return item.delta if item else None


def _observation_id(comparison_id: str, setup_key: str, start_pct: float, end_pct: float) -> str:
    digest = hashlib.sha256(f"{comparison_id}|{setup_key}|{start_pct:.4f}|{end_pct:.4f}".encode()).hexdigest()[:20]
    return f"obs_{digest}"


def record_setup_response(
    *,
    comparison_id: str,
    car_name: str | None,
    track_name: str | None,
    baseline_run_id: str,
    test_run_id: str,
    baseline_lap: int | None,
    test_lap: int | None,
    setup_changes: list[SetupChange],
    discipline: TestDisciplineResult,
    target_zone: TargetZoneComparison,
    verdict: DidItWorkVerdict,
    pace: PaceComparison,
    driver: DriverComparison,
    context_problem_count: int,
    response_context: SetupResponseContext | None = None,
    test_driver_id: str | None = None,
    sim_integrity_clear: bool | None = None,
    controlled_effect_eligible: bool = False,
    evidence_state: EvidenceState | None = None,
    source_channels: list[str] | None = None,
    evidence_event_ids: list[str] | None = None,
    source_run_ids: list[str] | None = None,
    controlled_effect_components: dict[str, list[float]] | None = None,
    baseline_setup_passed_tech: bool | None = None,
    test_setup_passed_tech: bool | None = None,
    baseline_setup_for_model: dict[str, Any] | None = None,
    test_setup_for_model: dict[str, Any] | None = None,
    is_same_run: bool = False,
    target_phase: str | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Persist one controlled setup response for conservative background learning."""
    if (
        is_same_run
        or len(setup_changes) != 1
        or discipline.label != "clean"
        or context_problem_count != 0
        or driver.driver_verdict != "consistent"
        or verdict.verdict not in {"keep_direction", "undo"}
        or verdict.confidence_score < 0.55
        or pace.is_significant is not True
        or pace.baseline_eligible_laps < 3
        or pace.test_eligible_laps < 3
        or response_context is None
        or not response_context.is_complete
        or not test_driver_id
        or str(test_driver_id) != response_context.driver_id
        or sim_integrity_clear is not True
        or controlled_effect_eligible is not True
        or evidence_state is not EvidenceState.CONTROLLED_TEST_EFFECT
        or not source_channels
        or not evidence_event_ids
        or not source_run_ids
        or len(source_run_ids) != 3
        or len(set(source_run_ids)) != 3
        or source_run_ids[0] != baseline_run_id
        or source_run_ids[1] != test_run_id
        or baseline_setup_passed_tech is not True
        or test_setup_passed_tech is not True
    ):
        return False
    assert source_run_ids is not None
    if not _source_runs_are_independent(source_run_ids, db_path=db_path):
        return False
    change = setup_changes[0]
    baseline_surrounding = surrounding_setup_fingerprint(baseline_setup_for_model, change.setup_key)
    test_surrounding = surrounding_setup_fingerprint(test_setup_for_model, change.setup_key)
    if baseline_surrounding is None or baseline_surrounding != test_surrounding:
        return False
    baseline_value = _number(change.baseline_value)
    test_value = _number(change.test_value)
    numeric_delta = test_value - baseline_value if baseline_value is not None and test_value is not None else None
    direction_sign = 0 if numeric_delta is None or abs(numeric_delta) < 1e-12 else (1 if numeric_delta > 0 else -1)
    if direction_sign == 0:
        return False
    relative_delta_percent = change.relative_delta_percent
    if relative_delta_percent is None and baseline_value is not None and abs(baseline_value) > 1e-12:
        relative_delta_percent = abs(numeric_delta or 0.0) / abs(baseline_value) * 100.0
    magnitude_label = change.significance if change.significance != "unknown" else None

    evidence = {
        "evidence_packet_id": comparison_id,
        "hypothesis": verdict.headline,
        "target_phase": target_phase,
        "observed_phase_effects": {
            "target_zone_start_pct": target_zone.start_pct,
            "target_zone_end_pct": target_zone.end_pct,
            "median_lap_delta_s": pace.cohort_delta_s,
            "target_speed_delta_mph": _channel_delta(target_zone, "speed_mph"),
            "cfs_delta_in": _channel_delta(target_zone, "cfs_ride_height_in"),
        },
        "countereffects": {
            "warnings": verdict.warnings,
            "do_not_change": verdict.do_not_change_warnings,
        },
        "evidence_state": evidence_state.value,
        "source_channels": list(dict.fromkeys(source_channels)),
        "evidence_event_ids": list(dict.fromkeys(evidence_event_ids)),
        "source_run_ids": list(source_run_ids),
        "headline": verdict.headline,
        "evidence": verdict.evidence,
        "warnings": verdict.warnings,
        "pace_direction": pace.direction,
        "pace_confidence": pace.confidence_score,
        "controlled_effect_components": controlled_effect_components or {},
    }
    source_run_provenance_key = hashlib.sha256(
        "|".join([*source_run_ids, change.setup_key]).encode()
    ).hexdigest()
    observation_id = _observation_id(
        comparison_id,
        change.setup_key,
        target_zone.start_pct,
        target_zone.end_pct,
    )
    conn = initialize_database(db_path)
    from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS

    spec = SETUP_CONTROL_SPECS.get(change.setup_key)
    setup_unit = spec.display_unit if spec else None
    setup_value_kind = (
        "continuous" if spec and spec.step_strategy == "numeric_test" else "discrete"
    )
    existing_observation = conn.execute(
        """
        SELECT * FROM setup_response_observations
        WHERE comparison_id = ? AND setup_key = ?
          AND target_zone_start_pct = ? AND target_zone_end_pct = ?
        """,
        (comparison_id, change.setup_key, target_zone.start_pct, target_zone.end_pct),
    ).fetchone()
    if existing_observation is not None:
        expected = {
            "car_name": car_name,
            "track_name": track_name,
            "response_context_key": response_context.key,
            "environment_context_key": response_environment_key(response_context),
            "surrounding_setup_fingerprint": baseline_surrounding,
            "source_run_provenance_key": source_run_provenance_key,
            "baseline_run_id": baseline_run_id,
            "test_run_id": test_run_id,
            "baseline_lap": baseline_lap,
            "test_lap": test_lap,
            "setup_label": change.label,
            "setup_group": change.group,
            "direction_sign": direction_sign,
            "baseline_value": str(change.baseline_value),
            "test_value": str(change.test_value),
            "numeric_delta": numeric_delta,
            "magnitude_label": magnitude_label,
            "relative_delta_percent": relative_delta_percent,
            "verdict": verdict.verdict,
            "confidence_score": verdict.confidence_score,
            "discipline_score": discipline.score,
            "median_lap_delta_s": pace.cohort_delta_s,
            "pace_noise_band_s": pace.noise_band_s,
            "target_speed_delta_mph": _channel_delta(target_zone, "speed_mph"),
            "cfs_delta_in": _channel_delta(target_zone, "cfs_ride_height_in"),
            "driver_repeatability_score": driver.repeatability_score,
            "context_problem_count": context_problem_count,
            "baseline_setup_passed_tech": 1,
            "test_setup_passed_tech": 1,
            "setup_unit": setup_unit,
            "setup_value_kind": setup_value_kind,
        }
        identical = all(existing_observation[key] == value for key, value in expected.items())
        identical = identical and json.loads(existing_observation["response_context_json"] or "{}") == asdict(response_context)
        identical = identical and json.loads(existing_observation["evidence_json"] or "{}") == evidence
        conn.close()
        return identical
    existing_provenance = conn.execute(
        "SELECT comparison_id FROM setup_response_observations WHERE source_run_provenance_key = ?",
        (source_run_provenance_key,),
    ).fetchone()
    if existing_provenance is not None and existing_provenance["comparison_id"] != comparison_id:
        conn.close()
        return False
    with conn:
        conn.execute(
            """
            INSERT INTO setup_response_observations (
              observation_id, comparison_id, created_at, car_name, track_name,
              response_context_key, response_context_json,
              environment_context_key, surrounding_setup_fingerprint,
              source_run_provenance_key,
              baseline_run_id, test_run_id, baseline_lap, test_lap,
              setup_key, setup_label, setup_group, direction_sign,
              baseline_value, test_value, numeric_delta, magnitude_label, relative_delta_percent,
              verdict, confidence_score, discipline_score,
              target_zone_start_pct, target_zone_end_pct,
              median_lap_delta_s, pace_noise_band_s,
              target_speed_delta_mph, cfs_delta_in,
              driver_repeatability_score, context_problem_count,
              baseline_setup_passed_tech, test_setup_passed_tech,
              setup_unit, setup_value_kind, evidence_json
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(comparison_id, setup_key, target_zone_start_pct, target_zone_end_pct)
            DO UPDATE SET
              created_at=excluded.created_at,
              response_context_key=excluded.response_context_key,
              response_context_json=excluded.response_context_json,
              environment_context_key=excluded.environment_context_key,
              surrounding_setup_fingerprint=excluded.surrounding_setup_fingerprint,
              verdict=excluded.verdict,
              confidence_score=excluded.confidence_score,
              discipline_score=excluded.discipline_score,
              magnitude_label=excluded.magnitude_label,
              relative_delta_percent=excluded.relative_delta_percent,
              median_lap_delta_s=excluded.median_lap_delta_s,
              pace_noise_band_s=excluded.pace_noise_band_s,
              target_speed_delta_mph=excluded.target_speed_delta_mph,
              cfs_delta_in=excluded.cfs_delta_in,
              driver_repeatability_score=excluded.driver_repeatability_score,
              baseline_setup_passed_tech=excluded.baseline_setup_passed_tech,
              test_setup_passed_tech=excluded.test_setup_passed_tech,
              setup_unit=excluded.setup_unit,
              setup_value_kind=excluded.setup_value_kind,
              evidence_json=excluded.evidence_json
            """,
            (
                observation_id, comparison_id, _utc_now(), car_name, track_name,
                response_context.key,
                json.dumps(asdict(response_context), sort_keys=True, separators=(",", ":")),
                response_environment_key(response_context), baseline_surrounding,
                source_run_provenance_key,
                baseline_run_id, test_run_id, baseline_lap, test_lap,
                change.setup_key, change.label, change.group, direction_sign,
                str(change.baseline_value), str(change.test_value), numeric_delta,
                magnitude_label, relative_delta_percent,
                verdict.verdict, verdict.confidence_score, discipline.score,
                target_zone.start_pct, target_zone.end_pct,
                pace.cohort_delta_s, pace.noise_band_s,
                _channel_delta(target_zone, "speed_mph"),
                _channel_delta(target_zone, "cfs_ride_height_in"),
                driver.repeatability_score, context_problem_count,
                1, 1,
                setup_unit, setup_value_kind,
                json.dumps(evidence, separators=(",", ":")),
            ),
        )
    conn.close()
    return True


def get_setup_area_biases(
    car_name: str | None,
    track_name: str | None,
    *,
    response_context: SetupResponseContext | None = None,
    target_zone: tuple[float, float] | None = None,
    target_phase: str | None = None,
    minimum_observations: int = 3,
    db_path: str | Path | None = None,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Return only repeated, direction-specific history; sparse history stays neutral."""
    if (
        not car_name
        or not track_name
        or response_context is None
        or not response_context.is_complete
        or response_context.car_name != car_name
        or response_context.track_name != track_name
    ):
        return {}
    conn = initialize_database(db_path)
    rows = conn.execute(
        """
        SELECT *
        FROM setup_response_observations
        WHERE car_name = ? AND track_name = ?
          AND response_context_key = ? AND direction_sign != 0
        """,
        (car_name, track_name, response_context.key),
    ).fetchall()
    conn.close()

    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        qualified = _qualified_setup_response_row(
            row,
            response_context,
            exact_context=True,
        )
        if qualified is None:
            continue
        row_payload, evidence, _ = qualified
        row = row_payload
        if target_zone is not None and (
            abs(float(row["target_zone_start_pct"]) - target_zone[0]) > 1e-3
            or abs(float(row["target_zone_end_pct"]) - target_zone[1]) > 1e-3
        ):
            continue
        if target_phase is not None:
            observed_phase = str(evidence.get("target_phase") or "")
            if observed_phase.casefold() != target_phase.casefold():
                continue
        setup_key = str(row["setup_key"] or "")
        if setup_key:
            grouped.setdefault((setup_key, int(row["direction_sign"])), []).append(row)

    result: dict[tuple[str, int], dict[str, Any]] = {}
    outcome_value = {"keep_direction": 1.0, "undo": -1.0, "retest": 0.0, "inconclusive": 0.0}
    for key, observations in grouped.items():
        if len(observations) < minimum_observations:
            continue
        weights = [max(0.05, min(1.0, float(row["confidence_score"] or 0.0))) for row in observations]
        weighted_outcome = sum(
            outcome_value.get(row["verdict"], 0.0) * weight
            for row, weight in zip(observations, weights)
        ) / sum(weights)
        lap_deltas = [float(row["median_lap_delta_s"]) for row in observations if row["median_lap_delta_s"] is not None]
        speed_deltas = [float(row["target_speed_delta_mph"]) for row in observations if row["target_speed_delta_mph"] is not None]
        numeric_deltas = [abs(float(row["numeric_delta"])) for row in observations if row["numeric_delta"] is not None]
        relative_deltas = [float(row["relative_delta_percent"]) for row in observations if row["relative_delta_percent"] is not None]
        magnitude_counts = Counter(str(row["magnitude_label"] or "unknown") for row in observations)
        magnitude_outcomes: dict[str, float] = {}
        for magnitude in magnitude_counts:
            magnitude_rows = [row for row in observations if str(row["magnitude_label"] or "unknown") == magnitude]
            magnitude_weights = [max(0.05, min(1.0, float(row["confidence_score"] or 0.0))) for row in magnitude_rows]
            magnitude_outcomes[magnitude] = round(sum(
                outcome_value.get(row["verdict"], 0.0) * weight
                for row, weight in zip(magnitude_rows, magnitude_weights)
            ) / sum(magnitude_weights), 3)
        result[key] = {
            "count": len(observations),
            "weighted_outcome": round(weighted_outcome, 3),
            "mean_lap_delta_s": round(sum(lap_deltas) / len(lap_deltas), 4) if lap_deltas else None,
            "mean_target_speed_delta_mph": round(sum(speed_deltas) / len(speed_deltas), 4) if speed_deltas else None,
            "mean_abs_numeric_delta": round(sum(numeric_deltas) / len(numeric_deltas), 4) if numeric_deltas else None,
            "mean_relative_delta_percent": round(sum(relative_deltas) / len(relative_deltas), 3) if relative_deltas else None,
            "magnitude_counts": dict(magnitude_counts),
            "weighted_outcome_by_magnitude": magnitude_outcomes,
        }
    return result


def _solve_regularized_normal_equations(
    features: list[list[float]],
    targets: list[float],
    weights: list[float],
    *,
    ridge: float = 1e-8,
) -> list[float] | None:
    """Solve a small weighted least-squares system without optional dependencies."""
    if not features or len(features) != len(targets) or len(targets) != len(weights):
        return None
    width = len(features[0])
    if width == 0 or any(len(row) != width for row in features):
        return None
    matrix = [[0.0 for _ in range(width + 1)] for _ in range(width)]
    for row, target, weight in zip(features, targets, weights):
        if weight <= 0.0 or not math.isfinite(weight):
            return None
        for left in range(width):
            matrix[left][width] += weight * row[left] * target
            for right in range(width):
                matrix[left][right] += weight * row[left] * row[right]
    for index in range(1, width):
        matrix[index][index] += ridge
    for pivot in range(width):
        swap = max(range(pivot, width), key=lambda row: abs(matrix[row][pivot]))
        if abs(matrix[swap][pivot]) < 1e-12:
            return None
        matrix[pivot], matrix[swap] = matrix[swap], matrix[pivot]
        divisor = matrix[pivot][pivot]
        matrix[pivot] = [value / divisor for value in matrix[pivot]]
        for row in range(width):
            if row == pivot:
                continue
            factor = matrix[row][pivot]
            matrix[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(matrix[row], matrix[pivot])
            ]
    solution = [matrix[index][width] for index in range(width)]
    return solution if all(math.isfinite(value) for value in solution) else None


def get_setup_response_models(
    response_context: SetupResponseContext | None,
    *,
    minimum_observations: int = 6,
    db_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Fit exact-context linear/quadratic control responses from controlled tests.

    The model describes only the observed input range.  It never extrapolates a
    legal limit or pools drivers/builds/weather buckets.
    """
    if response_context is None or not response_context.is_complete:
        return {}
    conn = initialize_database(db_path)
    rows = conn.execute(
        """
        SELECT *
        FROM setup_response_observations
        WHERE environment_context_key = ?
          AND baseline_setup_passed_tech = 1
          AND test_setup_passed_tech = 1
          AND numeric_delta IS NOT NULL
          AND median_lap_delta_s IS NOT NULL
        ORDER BY created_at, observation_id
        """,
        (response_environment_key(response_context),),
    ).fetchall()
    conn.close()
    evidence_by_observation: dict[str, dict[str, Any]] = {}
    valid_rows: list[dict[str, Any]] = []
    for row in rows:
        qualified = _qualified_setup_response_row(
            row,
            response_context,
            exact_context=False,
        )
        if qualified is None:
            continue
        row, evidence, _ = qualified
        observation_id = str(row["observation_id"])
        evidence_by_observation[observation_id] = evidence
        valid_rows.append(row)
    rows = valid_rows
    grouped: dict[tuple[str, str, float, float], list[Any]] = {}
    for row in rows:
        grouped.setdefault((
            str(row["setup_key"]),
            str(row["surrounding_setup_fingerprint"] or ""),
            round(float(row["target_zone_start_pct"]), 3),
            round(float(row["target_zone_end_pct"]), 3),
        ), []).append(row)
    result: dict[str, dict[str, Any]] = {}
    for (setup_key, surrounding_fingerprint, zone_start, zone_end), observations in grouped.items():
        if not surrounding_fingerprint:
            continue
        inputs = [float(row["numeric_delta"]) for row in observations]
        baseline_levels = [_number(row["baseline_value"]) for row in observations]
        test_levels = [_number(row["test_value"]) for row in observations]
        targets = [float(row["median_lap_delta_s"]) for row in observations]
        if (
            len(observations) < minimum_observations
            or any(value is None for value in [*baseline_levels, *test_levels])
            or not all(math.isfinite(value) for value in [*inputs, *targets])
        ):
            continue
        baselines = [float(value) for value in baseline_levels if value is not None]
        tests = [float(value) for value in test_levels if value is not None]
        distinct_inputs = sorted({round(value, 9) for value in inputs})
        replication = Counter(
            (round(baseline, 9), round(test, 9))
            for baseline, test in zip(baselines, tests)
        )
        distinct_absolute_levels = sorted({round(value, 9) for value in [*baselines, *tests]})
        if (
            len(distinct_inputs) < 3
            or len(distinct_absolute_levels) < 3
            or not any(value < -1e-12 for value in inputs)
            or not any(value > 1e-12 for value in inputs)
            or any(count < 2 for count in replication.values())
        ):
            continue
        absolute_center = sum([*baselines, *tests]) / (len(baselines) + len(tests))
        scale = max(abs(value - absolute_center) for value in [*baselines, *tests])
        if scale <= 1e-12:
            continue
        normalized_baselines = [(value - absolute_center) / scale for value in baselines]
        normalized_tests = [(value - absolute_center) / scale for value in tests]
        features = [
            [test - baseline, test * test - baseline * baseline]
            for baseline, test in zip(normalized_baselines, normalized_tests)
        ]
        weights = []
        for row in observations:
            confidence = max(0.05, min(1.0, float(row["confidence_score"] or 0.0)))
            noise = max(0.01, float(row["pace_noise_band_s"] or 0.05))
            weights.append(confidence / (noise * noise))
        coefficients = _solve_regularized_normal_equations(features, targets, weights)
        if coefficients is None:
            continue
        predictions = [sum(coef * value for coef, value in zip(coefficients, row)) for row in features]
        residual_sigma = math.sqrt(sum(
            weight * (target - prediction) ** 2
            for weight, target, prediction in zip(weights, targets, predictions)
        ) / max(sum(weights), 1e-12))
        quadratic = coefficients[1] / (scale * scale)
        linear = coefficients[0] / scale - 2.0 * absolute_center * quadratic
        warnings = []
        observations_with_countereffects = 0
        event_ids: list[str] = []
        for row in observations:
            evidence = evidence_by_observation[str(row["observation_id"])]
            row_warnings = [str(item) for item in evidence.get("warnings", [])]
            row_warnings.extend(str(item) for item in evidence.get("countereffects", {}).get("do_not_change", []))
            if row_warnings:
                observations_with_countereffects += 1
            warnings.extend(row_warnings)
            event_ids.extend(str(item) for item in evidence.get("evidence_event_ids", []))
        curvature_span = abs(quadratic) * (max([*baselines, *tests]) - min([*baselines, *tests])) ** 2
        result[f"{setup_key}:{surrounding_fingerprint[:16]}:{zone_start:.3f}-{zone_end:.3f}"] = {
            "environment_context_key": response_environment_key(response_context),
            "surrounding_setup_fingerprint": surrounding_fingerprint,
            "setup_key": setup_key,
            "observation_count": len(observations),
            "distinct_input_count": len(distinct_inputs),
            "distinct_absolute_control_levels": len(distinct_absolute_levels),
            "replications_by_pair": {f"{key[0]}->{key[1]}": value for key, value in sorted(replication.items())},
            "observed_delta_range": {"minimum": min(inputs), "maximum": max(inputs)},
            "observed_absolute_control_range": {
                "minimum": min([*baselines, *tests]),
                "maximum": max([*baselines, *tests]),
            },
            "linear_effect_s_per_input_unit": round(linear, 8),
            "quadratic_effect_s_per_input_unit_squared": round(quadratic, 8),
            "nonlinearity_detected": curvature_span > max(0.02, 2.0 * residual_sigma),
            "residual_uncertainty_s": round(residual_sigma, 6),
            "target_zone": {"start_pct": zone_start, "end_pct": zone_end},
            "countereffect_warning_count": len(warnings),
            "countereffect_observation_fraction": round(
                observations_with_countereffects / len(observations), 4
            ),
            "countereffects_by_warning": dict(Counter(warnings)),
            "source_observation_ids": [str(row["observation_id"]) for row in observations],
            "evidence_event_ids": list(dict.fromkeys(event_ids)),
            "scope": "observed_exact_context_only_no_extrapolation",
        }
    return result


def get_observed_tech_envelope(
    response_context: SetupResponseContext | None,
    *,
    db_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Return observed tech-passing ranges, never inferred universal limits."""
    if response_context is None or not response_context.is_complete:
        return {}
    conn = initialize_database(db_path)
    rows = conn.execute(
        """
        SELECT *
        FROM setup_response_observations
        WHERE environment_context_key = ?
          AND baseline_setup_passed_tech = 1
          AND test_setup_passed_tech = 1
        ORDER BY created_at, observation_id
        """,
        (response_environment_key(response_context),),
    ).fetchall()
    conn.close()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        qualified = _qualified_setup_response_row(
            row,
            response_context,
            exact_context=False,
        )
        if qualified is None:
            continue
        row, _, _ = qualified
        grouped.setdefault((
            str(row["setup_key"]),
            str(row["surrounding_setup_fingerprint"] or ""),
        ), []).append(row)
    envelope: dict[str, dict[str, Any]] = {}
    for (setup_key, surrounding_fingerprint), observations in grouped.items():
        if not surrounding_fingerprint:
            continue
        option_sources: dict[str, dict[str, Any]] = {}
        for row in observations:
            observation_id = str(row["observation_id"])
            for raw_value in (row["baseline_value"], row["test_value"]):
                if raw_value is None:
                    continue
                canonical_key = canonical_setup_value_key(setup_key, raw_value)
                numeric = _number(raw_value)
                option = option_sources.setdefault(canonical_key, {
                    "value": numeric if numeric is not None else str(raw_value),
                    "canonical_value_key": canonical_key,
                    "source_observation_ids": [],
                })
                if observation_id not in option["source_observation_ids"]:
                    option["source_observation_ids"].append(observation_id)
        observed_options = sorted(
            option_sources.values(),
            key=lambda item: (
                _number(item["value"]) is None,
                _number(item["value"]) if _number(item["value"]) is not None else str(item["value"]),
            ),
        )
        values = [item["value"] for item in observed_options]
        if len(values) < 2:
            continue
        from racelab_engine.analysis.setup_controls import SETUP_CONTROL_SPECS

        spec = SETUP_CONTROL_SPECS.get(setup_key)
        is_discrete = spec is None or spec.step_strategy != "numeric_test"
        numeric_values = [value for value in (_number(item) for item in values) if value is not None]
        envelope[f"{setup_key}:{surrounding_fingerprint[:16]}"] = {
            "setup_key": setup_key,
            "environment_context_key": response_environment_key(response_context),
            "surrounding_setup_fingerprint": surrounding_fingerprint,
            "observed_minimum": None if is_discrete or not numeric_values else min(numeric_values),
            "observed_maximum": None if is_discrete or not numeric_values else max(numeric_values),
            "observed_values": values,
            "observed_options": observed_options,
            "value_kind": "discrete_observed_options" if is_discrete else "continuous_observed_range",
            "unit": observations[0]["setup_unit"],
            "distinct_tech_passing_values": len(values),
            "observation_count": len(observations),
            "source_observation_ids": [str(row["observation_id"]) for row in observations],
            "scope": "observed_tech_passing_exact_context_not_a_universal_limit",
        }
    return envelope


def record_interaction_response(
    *,
    experiment_id: str,
    response_context: SetupResponseContext | None,
    factor_deltas: dict[str, float],
    outcomes: dict[str, float],
    uncertainty: float,
    setup_passed_tech: bool | None,
    evidence_packet_ids: list[str],
    source_run_ids: list[str],
    experiment_unlock: Any,
    controlled_effect_eligible: bool = False,
    evidence_state: EvidenceState | None = None,
    driver_matched: bool | None = None,
    sim_integrity_clear: bool | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Persist one qualified DOE row after every production gate is proven."""
    if (
        response_context is None
        or not response_context.is_complete
        or not experiment_id.strip()
        or not getattr(experiment_unlock, "unlocked", False)
        or setup_passed_tech is not True
        or not 2 <= len(factor_deltas) <= 6
        or not outcomes
        or not evidence_packet_ids
        or not source_run_ids
        or len(source_run_ids) < 3
        or len(set(source_run_ids)) != len(source_run_ids)
        or controlled_effect_eligible is not True
        or evidence_state is not EvidenceState.CONTROLLED_TEST_EFFECT
        or driver_matched is not True
        or sim_integrity_clear is not True
        or uncertainty < 0.0
        or not math.isfinite(uncertainty)
    ):
        return False
    if not _source_runs_are_independent(source_run_ids, db_path=db_path):
        return False
    qualified = set(getattr(experiment_unlock, "qualified_factor_keys", ()))
    if not set(factor_deltas).issubset(qualified):
        return False
    numeric_values = [*factor_deltas.values(), *outcomes.values()]
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in numeric_values):
        return False
    if sum(abs(float(value)) > 1e-12 for value in factor_deltas.values()) < 2:
        return False
    context_json = json.dumps(asdict(response_context), sort_keys=True, separators=(",", ":"))
    factors_json = json.dumps(factor_deltas, sort_keys=True, separators=(",", ":"))
    outcomes_json = json.dumps(outcomes, sort_keys=True, separators=(",", ":"))
    packets_json = json.dumps(list(dict.fromkeys(evidence_packet_ids)), separators=(",", ":"))
    runs_json = json.dumps(list(dict.fromkeys(source_run_ids)), separators=(",", ":"))
    conn = initialize_database(db_path)
    existing = conn.execute(
        """
        SELECT response_context_key, response_context_json, factor_deltas_json,
               outcomes_json, uncertainty, evidence_packet_ids_json, source_run_ids_json
        FROM setup_interaction_observations WHERE experiment_id = ?
        """,
        (experiment_id,),
    ).fetchone()
    if existing is not None:
        identical = (
            existing["response_context_key"] == response_context.key
            and existing["response_context_json"] == context_json
            and existing["factor_deltas_json"] == factors_json
            and existing["outcomes_json"] == outcomes_json
            and float(existing["uncertainty"]) == float(uncertainty)
            and existing["evidence_packet_ids_json"] == packets_json
            and existing["source_run_ids_json"] == runs_json
        )
        conn.close()
        return identical
    with conn:
        conn.execute(
            """
            INSERT INTO setup_interaction_observations (
              experiment_id, created_at, response_context_key, response_context_json,
              factor_deltas_json, outcomes_json, uncertainty, setup_passed_tech,
              evidence_packet_ids_json, source_run_ids_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                experiment_id,
                _utc_now(),
                response_context.key,
                context_json,
                factors_json,
                outcomes_json,
                uncertainty,
                packets_json,
                runs_json,
            ),
        )
    conn.close()
    return True


def get_interaction_response_models(
    response_context: SetupResponseContext | None,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Fit traceable linear and pair-interaction terms within one exact context."""
    if response_context is None or not response_context.is_complete:
        return {}
    conn = initialize_database(db_path)
    rows = conn.execute(
        """
        SELECT experiment_id, response_context_json, factor_deltas_json, outcomes_json, uncertainty,
               evidence_packet_ids_json, source_run_ids_json
        FROM setup_interaction_observations
        WHERE response_context_key = ? AND setup_passed_tech = 1
        ORDER BY created_at, experiment_id
        """,
        (response_context.key,),
    ).fetchall()
    conn.close()
    interaction_source_run_ids = {
        run_id
        for row in rows
        for run_id in (_json_string_list(row["source_run_ids_json"]) or ())
    }
    interaction_recording_sha_by_run = RaceLabRepository(
        db_path
    ).get_recording_sha256s(tuple(sorted(interaction_source_run_ids)))
    parsed_rows: list[dict[str, Any]] = []
    for row in rows:
        context_payload = _json_object(row["response_context_json"])
        factors_payload = _json_object(row["factor_deltas_json"])
        outcomes_payload = _json_object(row["outcomes_json"])
        packet_ids = _json_string_list(row["evidence_packet_ids_json"])
        source_run_ids = _json_string_list(row["source_run_ids_json"])
        try:
            stored_context = (
                SetupResponseContext(**context_payload)
                if context_payload is not None
                else None
            )
            factors = {
                key: float(value) for key, value in (factors_payload or {}).items()
            }
            outcomes = {
                key: float(value) for key, value in (outcomes_payload or {}).items()
            }
            uncertainty = float(row["uncertainty"])
        except (TypeError, ValueError):
            continue
        if (
            stored_context is None
            or not stored_context.is_complete
            or stored_context.key != response_context.key
            or not factors
            or not outcomes
            or not all(math.isfinite(value) for value in [*factors.values(), *outcomes.values()])
            or not math.isfinite(uncertainty)
            or uncertainty < 0.0
            or packet_ids is None
            or not packet_ids
            or source_run_ids is None
            or not source_run_ids
        ):
            continue
        source_hashes = tuple(
            interaction_recording_sha_by_run.get(run_id)
            for run_id in source_run_ids
        )
        if (
            not all(source_hashes)
            or len(set(source_hashes)) != len(source_hashes)
        ):
            continue
        parsed_rows.append({
            "experiment_id": str(row["experiment_id"]),
            "factors": factors,
            "outcomes": outcomes,
            "uncertainty": uncertainty,
            "evidence_packet_ids": packet_ids,
            "source_run_ids": source_run_ids,
        })
    if not parsed_rows:
        return {}
    factor_sets = [set(row["factors"]) for row in parsed_rows]
    outcome_sets = [set(row["outcomes"]) for row in parsed_rows]
    if any(keys != factor_sets[0] for keys in factor_sets) or any(keys != outcome_sets[0] for keys in outcome_sets):
        return {}
    factors = sorted(factor_sets[0])
    outcomes = sorted(outcome_sets[0])
    term_names = ["intercept", *factors]
    term_names.extend(
        f"{left}*{right}"
        for index, left in enumerate(factors)
        for right in factors[index + 1:]
    )
    if len(parsed_rows) < len(term_names) + 2:
        return {}
    feature_rows: list[list[float]] = []
    outcome_payloads: list[dict[str, float]] = []
    weights: list[float] = []
    for row in parsed_rows:
        values = row["factors"]
        features = [1.0, *(values[key] for key in factors)]
        features.extend(
            values[left] * values[right]
            for index, left in enumerate(factors)
            for right in factors[index + 1:]
        )
        feature_rows.append(features)
        outcome_payloads.append(row["outcomes"])
        weights.append(1.0 / max(row["uncertainty"] ** 2, 1e-4))
    fitted: dict[str, Any] = {}
    for outcome in outcomes:
        targets = [payload[outcome] for payload in outcome_payloads]
        coefficients = _solve_regularized_normal_equations(feature_rows, targets, weights, ridge=1e-6)
        if coefficients is None:
            continue
        predictions = [sum(coef * value for coef, value in zip(coefficients, features)) for features in feature_rows]
        residual = math.sqrt(sum(
            weight * (target - prediction) ** 2
            for weight, target, prediction in zip(weights, targets, predictions)
        ) / max(sum(weights), 1e-12))
        fitted[outcome] = {
            "coefficients": {name: round(value, 8) for name, value in zip(term_names, coefficients)},
            "residual_uncertainty": round(residual, 6),
        }
    if not fitted:
        return {}
    return {
        "context_key": response_context.key,
        "observation_count": len(parsed_rows),
        "factors": factors,
        "outcomes": fitted,
        "source_experiment_ids": [row["experiment_id"] for row in parsed_rows],
        "evidence_packet_ids": list(dict.fromkeys(
            item
            for row in parsed_rows
            for item in row["evidence_packet_ids"]
        )),
        "source_run_ids": list(dict.fromkeys(
            item
            for row in parsed_rows
            for item in row["source_run_ids"]
        )),
        "scope": "qualified_tech_passing_exact_context_doe_only",
    }


def get_setup_response_graph(
    response_context: SetupResponseContext | None,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return exact-context response edges without hiding contradictions."""
    if response_context is None or not response_context.is_complete:
        return {
            "context_key": None,
            "edges": [],
            "control_summaries": {},
            "response_models": {},
            "interaction_models": {},
            "observed_tech_envelope": {},
        }
    conn = initialize_database(db_path)
    rows = conn.execute(
        """
        SELECT *
        FROM setup_response_observations
        WHERE response_context_key = ?
          AND baseline_setup_passed_tech = 1
          AND test_setup_passed_tech = 1
        ORDER BY created_at, observation_id
        """,
        (response_context.key,),
    ).fetchall()
    conn.close()
    candidate_run_ids: set[str] = {
        str(value)
        for row in rows
        for value in (row["baseline_run_id"], row["test_run_id"])
        if value
    }
    for row in rows:
        try:
            evidence = json.loads(row["evidence_json"] or "{}")
        except (TypeError, ValueError):
            continue
        source_runs = evidence.get("source_run_ids") if isinstance(evidence, dict) else None
        if isinstance(source_runs, list):
            candidate_run_ids.update(
                str(run_id)
                for run_id in source_runs
                if isinstance(run_id, str) and run_id
            )
    recording_sha_by_run = RaceLabRepository(db_path).get_recording_sha256s(
        tuple(sorted(candidate_run_ids))
    )
    edges: list[dict[str, Any]] = []
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in rows:
        qualified = _qualified_setup_response_row(
            row,
            response_context,
            exact_context=True,
        )
        if qualified is None:
            continue
        edge, evidence, stored_context_payload = qualified
        edge.pop("evidence_json", None)
        edge.pop("response_context_json", None)
        edge["evidence"] = evidence
        edge["response_context"] = stored_context_payload
        evidence_source_runs = edge["evidence"].get("source_run_ids")
        edge["source_runs"] = (
            list(evidence_source_runs)
            if isinstance(evidence_source_runs, list) and evidence_source_runs
            else [edge["baseline_run_id"], edge["test_run_id"]]
        )
        source_runs = tuple(str(run_id) for run_id in edge["source_runs"])
        source_hashes = tuple(
            recording_sha_by_run.get(run_id) for run_id in source_runs
        )
        if (
            not source_runs
            or not all(source_hashes)
            or len(set(source_hashes)) != len(source_hashes)
        ):
            # Retain the immutable row for audit, but it cannot affect response
            # summaries, models, setup envelopes, or P19 history projection.
            continue
        edge["source_laps"] = [edge["baseline_lap"], edge["test_lap"]]
        edge["setup_passed_tech"] = (
            edge.pop("baseline_setup_passed_tech") == 1
            and edge.pop("test_setup_passed_tech") == 1
        )
        edges.append(edge)
        grouped.setdefault((str(edge["setup_key"]), int(edge["direction_sign"])), []).append(edge)

    summaries: dict[str, Any] = {}
    for (setup_key, direction), observations in grouped.items():
        verdicts = [str(edge["verdict"]) for edge in observations]
        keep_count = verdicts.count("keep_direction")
        undo_count = verdicts.count("undo")
        contradictions = keep_count > 0 and undo_count > 0
        magnitudes = sorted({str(edge["magnitude_label"] or "unknown") for edge in observations})
        outcomes_by_magnitude = {
            magnitude: sorted(
                {str(edge["verdict"]) for edge in observations if str(edge["magnitude_label"] or "unknown") == magnitude}
            )
            for magnitude in magnitudes
        }
        observed_values = [
            value
            for edge in observations
            for value in (_number(edge["baseline_value"]), _number(edge["test_value"]))
            if value is not None
        ]
        summaries[f"{setup_key}:{direction}"] = {
            "observation_count": len(observations),
            "keep_count": keep_count,
            "undo_count": undo_count,
            "contradictory": contradictions,
            "confidence_capped_for_contradiction": 0.5 if contradictions else None,
            "outcomes_by_magnitude": outcomes_by_magnitude,
            "observed_setup_envelope": (
                {"minimum": min(observed_values), "maximum": max(observed_values), "scope": "observed_exact_context_only"}
                if observed_values
                else None
            ),
            "source_observation_ids": [edge["observation_id"] for edge in observations],
        }
    return {
        "context_key": response_context.key,
        "context": asdict(response_context),
        "edges": edges,
        "control_summaries": summaries,
        "response_models": get_setup_response_models(response_context, db_path=db_path),
        "interaction_models": get_interaction_response_models(response_context, db_path=db_path),
        "observed_tech_envelope": get_observed_tech_envelope(response_context, db_path=db_path),
    }
