"""Server-owned Crew Chief and controlled A/B/A2 workflow assembly."""

from __future__ import annotations

import math
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Literal
from uuid import uuid4

from racelab_engine.analysis.comparison import build_lap_grid, interpolate_run_to_grid
from racelab_engine.analysis.crew_chief_packet import (
    CauseCandidate,
    KaizenEvidencePacket,
    OpportunityEvidence,
    build_kaizen_packet,
)
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    canonical_setup_value_key,
    numeric_setup_value,
    setup_control_values_equal,
)
from racelab_engine.analysis.setup_diff import (
    diff_setups,
    setup_control_value,
    setup_controls_comparable,
    unmapped_setup_change_paths,
)
from racelab_engine.analysis.sim_integrity import build_sim_integrity_certificate
from racelab_engine.analysis.test_director import (
    TestEvidenceLink,
    TestExecution,
    score_test_execution,
)
from racelab_engine.analysis.time_alignment import TimeAlignmentResult, analyze_time_alignment
from racelab_engine.knowledge.setup.dial_in_service import build_dial_in_response
from racelab_engine.knowledge.setup.dial_in_controls import expanded_related_setup_keys
from racelab_engine.knowledge.setup.evidence_adapter import (
    event_matches_phase,
    event_matches_zone,
    event_mechanism_flags,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.services.import_service import read_telemetry_manifest, read_telemetry_rows
from racelab_engine.storage.repository import RaceLabRepository


_WORKFLOW_COLUMNS = [
    "lap", "lap_dist_pct_100", "lap_dist_ft", "session_time", "session_tick",
    "speed_mps", "speed_mph", "throttle_pct", "brake_pct", "steering_deg",
    "yaw_rate", "lat_accel", "long_accel", "vert_accel", "vert_accel_g",
    "lat", "lon", "alt", "on_pit_road", "enter_exit_reset_state",
    "fuel_level", "air_temp", "track_temp", "wind_vel",
    "player_tire_compound", "tire_compound",
    "tire_sets_used", "left_tire_sets_used", "right_tire_sets_used",
    "car_distance_ahead_m", "car_distance_behind_m",
    "lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m",
    "lf_shock_defl_in", "rf_shock_defl_in", "lr_shock_defl_in", "rr_shock_defl_in",
    "lf_shock_vel_in_s", "rf_shock_vel_in_s", "lr_shock_vel_in_s", "rr_shock_vel_in_s",
    "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in",
    "cfs_ride_height_in", "frame_rate", "cpu_usage_foreground", "gpu_usage",
    "memory_page_faults_per_s", "channel_latency_s", "channel_quality",
    "front_platform_risk_score", "cfs_risk_score", "platform_risk_score",
    "rear_platform_risk_score", "rear_platform_contact_risk", "rear_scrape_risk_score",
    "rear_scrape_margin_mm", "min_rear_ride_height_mm", "water_temp", "oil_temp",
    "engine_warnings", "shift_indicator_pct", "rpm", "gear",
]

_TIME_COUNTEREFFECT_GUARDRAIL = (
    "Median non-target phase time must not worsen beyond empirical noise."
)

def _expanded_related_setup_keys(keys: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return expanded_related_setup_keys(keys)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sim_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _recording_interval(
    overview: Any, manifest: dict[str, Any],
) -> tuple[float, float] | None:
    session_start = _sim_timestamp(overview.session.sim_date_time)
    bounds = manifest.get("recording_session_time_bounds_s") or {}
    start = _finite(bounds.get("start"))
    end = _finite(bounds.get("end"))
    if session_start is None or start is None or end is None or end < start:
        return None
    epoch = session_start.timestamp()
    return epoch + start, epoch + end


def _recording_provenance(overview: Any, manifest: dict[str, Any]) -> dict[str, Any] | None:
    interval = _recording_interval(overview, manifest)
    session_start = _sim_timestamp(overview.session.sim_date_time)
    bounds = manifest.get("recording_session_time_bounds_s") or {}
    if interval is None or session_start is None:
        return None
    return {
        "session_start_basis_utc": session_start.isoformat(),
        "raw_session_time_start_s": _finite(bounds.get("start")),
        "raw_session_time_end_s": _finite(bounds.get("end")),
        "absolute_recording_start_epoch_s": interval[0],
        "absolute_recording_end_epoch_s": interval[1],
        "provenance": "file-declared session start plus archived SessionTime bounds",
    }


def _recording_order_is_valid(
    *,
    stage: Literal["A", "B", "A2"],
    run_id: str,
    source_run_id: str,
    current_interval: tuple[float, float],
    previous_interval: tuple[float, float],
    workflow_created_epoch_s: float,
) -> bool:
    if stage == "A" and run_id == source_run_id:
        return current_interval == previous_interval
    if current_interval[0] <= previous_interval[1]:
        return False
    return stage == "A" or current_interval[0] > workflow_created_epoch_s


def _provenance_value_key(control_key: str, value: Any) -> str:
    return canonical_setup_value_key(control_key, value)


def _is_complete_single_control_option(current_setup: Any, candidate_setup: Any, control_key: str) -> bool:
    changes = diff_setups(current_setup, candidate_setup)
    return bool(
        setup_controls_comparable(current_setup, candidate_setup)
        and len(changes) == 1
        and changes[0].setup_key == control_key
        and not unmapped_setup_change_paths(current_setup, candidate_setup, changes)
    )


def _cause_candidate_from_swing(
    swing: Any,
    index: int,
    event_ids_by_key: dict[str, list[str]],
    event_source_channels_by_id: dict[str, tuple[str, ...]] | None = None,
    event_mechanism_flags_by_id: dict[str, tuple[str, ...]] | None = None,
) -> CauseCandidate | None:
    """Build an evidence score without treating static rank as probability.

    ``index`` is retained for API compatibility with older callers, but it no
    longer changes the candidate score.  A lower list position is not physical
    evidence and must not manufacture confidence.
    """
    del index
    supported_keys = [item for item in swing.control_keys if item in SETUP_CONTROL_SPECS]
    if len(supported_keys) != 1 or len(swing.control_keys) != 1:
        return None
    key = supported_keys[0]
    linked_events = tuple(event_ids_by_key.get(key, ()))
    event_link = 1.0 if linked_events else 0.0
    observed_channels = tuple(dict.fromkeys(
        channel
        for event_id in linked_events
        for channel in (event_source_channels_by_id or {}).get(event_id, ())
    ))
    required_mechanisms = set(getattr(swing, "observed_evidence_flags", ()))
    linked_mechanisms = {
        flag
        for event_id in linked_events
        for flag in (event_mechanism_flags_by_id or {}).get(event_id, ())
    }
    mechanism_coverage = (
        len(required_mechanisms & linked_mechanisms) / len(required_mechanisms)
        if required_mechanisms
        else 0.0
    )
    raw_evidence_state = getattr(swing, "evidence_state", "needs_confirmation")
    evidence_state = str(getattr(raw_evidence_state, "value", raw_evidence_state))
    evidence_state_readiness = {
        "measured": 1.0,
        "calculated": 0.9,
        "observed_correlation": 0.7,
        "controlled_test_effect": 1.0,
        "estimated_proxy": 0.5,
        "needs_confirmation": 0.45,
    }.get(evidence_state, 0.0)
    readiness = (
        1.0
        if getattr(swing, "readiness_label", "") == "Observed mechanism"
        and mechanism_coverage >= 1.0
        else min(0.45, evidence_state_readiness)
    )
    risk_text = str(getattr(swing, "risk_label", "medium")).casefold()
    risk_margin = 0.35 if "high" in risk_text else 0.65 if "medium" in risk_text else 0.9
    blocker_clear = 0.0 if swing.blocker_reasons else 1.0
    components = {
        "eligible_event_link": event_link,
        "observed_mechanism_coverage": round(mechanism_coverage, 3),
        "observed_source_channel_count": float(len(observed_channels)),
        "evidence_readiness": readiness,
        "countereffect_margin": risk_margin,
        "blocker_clear": blocker_clear,
    }
    score = (
        0.45 * event_link
        + 0.20 * mechanism_coverage
        + 0.15 * readiness
        + 0.10 * risk_margin
        + 0.10 * blocker_clear
    )
    if not linked_events:
        score = min(score, 0.35)
    if swing.blocker_reasons:
        score = 0.0
    return CauseCandidate(
        cause_bucket=swing.setup_area,
        control_key=key,
        direction_sign=swing.direction_sign,
        score=round(max(0.0, min(1.0, score)), 3),
        hypothesis=f"{swing.effect} Expected trade-off: {swing.counter_effect}",
        success_metrics=tuple(swing.validate_with_labels or swing.validate_with),
        countereffects=tuple(dict.fromkeys((
            str(swing.counter_effect).strip(),
            _TIME_COUNTEREFFECT_GUARDRAIL,
        ))),
        supporting_event_ids=linked_events,
        blocked_reasons=tuple(swing.blocker_reasons),
        score_components=components,
    )


def _phase_matches(observed_phase: str, requested_phase: str | None) -> bool:
    if not requested_phase:
        return True
    requested = requested_phase.strip().casefold().replace(" ", "_")
    observed = observed_phase.strip().casefold().replace(" ", "_")
    families = {
        "braking": {"brake_application", "threshold_braking", "brake_release"},
        "entry": {"brake_application", "threshold_braking", "brake_release", "turn_in", "entry"},
        "center": {"center", "apex_region"},
        "exit": {"initial_throttle", "full_throttle_exit", "following_straight_carry"},
        "transition": {"transition"},
        "bump_curb": {"bump", "curb", "bump_curb"},
        "straight": {"straight"},
    }
    return requested in {"unknown", "all", "general"} or observed == requested or observed in families.get(requested, set())


def _validated_selected_zone(
    start_pct: float | None,
    end_pct: float | None,
) -> tuple[float, float] | None:
    if start_pct is None and end_pct is None:
        return None
    if start_pct is None or end_pct is None:
        raise ValueError("A selected Dial-In zone requires both start and end track positions.")
    if not all(math.isfinite(value) for value in (start_pct, end_pct)):
        raise ValueError("Selected Dial-In zone positions must be finite.")
    if not 0.0 <= start_pct < end_pct <= 100.0:
        raise ValueError("Selected Dial-In zone must satisfy 0 <= start < end <= 100.")
    return float(start_pct), float(end_pct)


def _selected_zone_contains_window(
    selected_zone: tuple[float, float] | None,
    start_pct: float,
    end_pct: float,
) -> bool:
    return selected_zone is None or (
        start_pct >= selected_zone[0] - 1e-9
        and end_pct <= selected_zone[1] + 1e-9
    )


def _memory_objective(objective: str | None, priority: str | None) -> str:
    normalized_objective = (objective or "setup-development").strip() or "setup-development"
    normalized_priority = (priority or "").strip()
    if not normalized_priority or normalized_priority == "overall-pace":
        return normalized_objective
    return f"{normalized_objective}|priority:{normalized_priority}"


def _decision_context_blocker(objective: str | None, priority: str | None) -> str | None:
    normalized_objective = (objective or "race-pace").strip().casefold()
    normalized_priority = (priority or "overall-pace").strip().casefold()
    if normalized_objective in {"long-run", "tire-conservation", "driver-confidence"}:
        return (
            f"The {normalized_objective.replace('-', ' ')} objective cannot be certified by the current short phase-time A/B/A2 protocol; "
            "collect the objective-specific stint, tire, or driver-confidence evidence first."
        )
    if normalized_priority == "tire-life":
        return (
            "Tire-life priority requires a clean continuous stint and repeated tire-state history; "
            "a three-lap phase-time test cannot certify it."
        )
    if normalized_priority == "platform-margin":
        return (
            "Platform-margin priority requires same-position clearance, contact, and platform-stability scoring; "
            "phase time alone cannot certify it."
        )
    return None


def _priority_phase(priority: str | None) -> str | None:
    return {
        "entry-security": "entry",
        "center-rotation": "center",
        "exit-drive": "exit",
    }.get((priority or "").strip().casefold())


_PLATFORM_MARGIN_CONTROLS = {
    "lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm",
    "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm",
    "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm",
}


def _apply_personal_response_models(
    candidates: list[CauseCandidate],
    *,
    opportunity: OpportunityEvidence,
    current_setup_values: dict[str, object],
    surrounding_fingerprint_by_control: dict[str, str],
    legal_values_by_control: dict[str, list[object]],
    response_models: dict[str, dict[str, Any]],
) -> list[CauseCandidate]:
    """Let qualified exact-context history outrank generic guide ordering.

    Models are used only inside their observed input range and exact target
    window. A prediction is an ordinal ranking input for one controlled next
    test, never a promised gain or an automatic setup change.
    """
    updated: list[CauseCandidate] = []
    for candidate in candidates:
        surrounding_fingerprint = surrounding_fingerprint_by_control.get(candidate.control_key)
        if not surrounding_fingerprint:
            updated.append(candidate)
            continue
        current = numeric_setup_value(current_setup_values.get(candidate.control_key))
        options = [
            (numeric_setup_value(value), value)
            for value in legal_values_by_control.get(candidate.control_key, ())
        ]
        directional = [
            (number, raw)
            for number, raw in options
            if number is not None
            and current is not None
            and ((number > current + 1e-9) if candidate.direction_sign > 0 else (number < current - 1e-9))
        ]
        if current is None or not directional:
            updated.append(candidate)
            continue
        proposed, _raw = (
            min(directional, key=lambda item: item[0])
            if candidate.direction_sign > 0
            else max(directional, key=lambda item: item[0])
        )
        assert proposed is not None
        delta = proposed - current
        matching = [
            model
            for model in response_models.values()
            if model.get("setup_key") == candidate.control_key
            and model.get("surrounding_setup_fingerprint") == surrounding_fingerprint
            and round(float(model.get("target_zone", {}).get("start_pct", -1.0)), 3)
            == round(opportunity.start_pct, 3)
            and round(float(model.get("target_zone", {}).get("end_pct", -1.0)), 3)
            == round(opportunity.end_pct, 3)
            and float(model.get("observed_delta_range", {}).get("minimum", math.inf)) - 1e-9
            <= delta
            <= float(model.get("observed_delta_range", {}).get("maximum", -math.inf)) + 1e-9
            and float(model.get("observed_absolute_control_range", {}).get("minimum", math.inf)) - 1e-9
            <= current
            <= float(model.get("observed_absolute_control_range", {}).get("maximum", -math.inf)) + 1e-9
            and float(model.get("observed_absolute_control_range", {}).get("minimum", math.inf)) - 1e-9
            <= proposed
            <= float(model.get("observed_absolute_control_range", {}).get("maximum", -math.inf)) + 1e-9
        ]
        if not matching:
            updated.append(candidate)
            continue
        model = max(matching, key=lambda item: int(item.get("observation_count", 0)))
        linear = _finite(model.get("linear_effect_s_per_input_unit"))
        quadratic = _finite(model.get("quadratic_effect_s_per_input_unit_squared"))
        uncertainty = _finite(model.get("residual_uncertainty_s"))
        if linear is None or quadratic is None or uncertainty is None:
            updated.append(candidate)
            continue
        predicted = linear * delta + quadratic * (proposed * proposed - current * current)
        if not math.isfinite(predicted):
            updated.append(candidate)
            continue
        support = 1.0 if predicted < -uncertainty else 0.0 if predicted > uncertainty else 0.5
        components = {
            **candidate.score_components,
            "personal_response_support": support,
            "personal_model_prediction_s": round(predicted, 6),
            "personal_model_uncertainty_s": round(uncertainty, 6),
        }
        score = round(max(0.0, min(1.0, 0.75 * candidate.score + 0.25 * support)), 3)
        blocked = list(candidate.blocked_reasons)
        if support == 0.0:
            blocked.append(
                "Qualified exact-context response history predicts this direction will worsen the target zone beyond model residual uncertainty."
            )
        updated.append(candidate.model_copy(update={
            "score": score,
            "score_components": components,
            "score_basis": (
                "Ordinal mechanism evidence plus qualified exact-context response history; "
                "not a calibrated probability or promised gain."
            ),
            "blocked_reasons": tuple(dict.fromkeys(blocked)),
            "hypothesis": (
                f"{candidate.hypothesis} Personal exact-context history estimates "
                f"{predicted:+.3f} s in this target window with {uncertainty:.3f} s residual uncertainty."
            ),
        }))
    return updated


def _lap_rows(run_id: str, lap_numbers: list[int]) -> dict[int, list[dict[str, Any]]]:
    wanted = set(lap_numbers)
    grouped = {lap: [] for lap in lap_numbers}
    for row in read_telemetry_rows(run_id, columns=_WORKFLOW_COLUMNS):
        lap = _finite(row.get("lap"))
        if lap is not None and int(lap) in wanted:
            grouped[int(lap)].append(row)
    return grouped


def _driver_similarity(reference: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> float:
    """Conservative matched-position input/line score; missing coverage scores zero."""
    grid = build_lap_grid(0.0, 100.0, 0.2)
    names = ["throttle_pct", "brake_pct", "steering_deg", "lat", "lon"]
    left = interpolate_run_to_grid(reference, names, grid)
    right = interpolate_run_to_grid(candidate, names, grid)
    thresholds = {"throttle_pct": 4.0, "brake_pct": 3.0, "steering_deg": 1.5}
    scores: list[float] = []
    for name, threshold in thresholds.items():
        pairs = [(a, b) for a, b in zip(left[name], right[name]) if a is not None and b is not None]
        if len(pairs) < 0.9 * len(grid):
            return 0.0
        mae = sum(abs(a - b) for a, b in pairs) / len(pairs)
        scores.append(max(0.0, 1.0 - mae / threshold))
    gps_pairs = [
        (la, lo, ra, ro)
        for la, lo, ra, ro in zip(left["lat"], left["lon"], right["lat"], right["lon"])
        if None not in (la, lo, ra, ro)
    ]
    if len(gps_pairs) < 0.9 * len(grid):
        return 0.0
    line_m = median(
        math.hypot((la - ra) * 111_320.0, (lo - ro) * 111_320.0 * math.cos(math.radians(la)))
        for la, lo, ra, ro in gps_pairs
    )
    scores.append(max(0.0, 1.0 - line_m / 1.5))
    return round(min(scores), 3)


def _context_score(
    lap_sets: list[list[dict[str, Any]]], *, allow_stint_progression: bool = False,
) -> float:
    if len(lap_sets) < 3:
        return 0.0
    compounds = []
    for rows in lap_sets:
        values = [str(row.get("player_tire_compound") or row.get("tire_compound")) for row in rows if row.get("player_tire_compound") is not None or row.get("tire_compound") is not None]
        if not values:
            return 0.0
        compounds.append(max(set(values), key=values.count))
    if len(set(compounds)) != 1:
        return 0.0
    tire_set_counts: list[float] = []
    for rows in lap_sets:
        values = [
            value
            for row in rows
            for channel in ("tire_sets_used", "left_tire_sets_used", "right_tire_sets_used")
            if (value := _finite(row.get(channel))) is not None
        ]
        if not values:
            return 0.0
        tire_set_counts.append(median(values))
    if any(right < left or right - left > 1.0 for left, right in zip(tire_set_counts, tire_set_counts[1:])):
        return 0.0
    tolerances = {"air_temp": 5.0, "track_temp": 5.0, "wind_vel": 5.0}
    scores: list[float] = []
    for channel, tolerance in tolerances.items():
        centers = [median(values) for rows in lap_sets if (values := [_finite(r.get(channel)) for r in rows if _finite(r.get(channel)) is not None])]
        if len(centers) != len(lap_sets):
            return 0.0
        scores.append(max(0.0, 1.0 - (max(centers) - min(centers)) / tolerance))
    fuel_centers = [
        median(values)
        for rows in lap_sets
        if (values := [_finite(row.get("fuel_level")) for row in rows if _finite(row.get("fuel_level")) is not None])
    ]
    if len(fuel_centers) != len(lap_sets):
        return 0.0
    if allow_stint_progression:
        if any(right > left + 0.5 for left, right in zip(fuel_centers, fuel_centers[1:])):
            return 0.0
        scores.append(1.0)
    else:
        scores.append(max(0.0, 1.0 - (max(fuel_centers) - min(fuel_centers)) / 2.0))
    tire_age_centers = []
    for rows in lap_sets:
        values = [
            value
            for row in rows
            for channel in ("lf_tire_distance_m", "rf_tire_distance_m", "lr_tire_distance_m", "rr_tire_distance_m")
            if (value := _finite(row.get(channel))) is not None
        ]
        if not values:
            return 0.0
        tire_age_centers.append(median(values))
    if allow_stint_progression:
        if any(right + 100.0 < left for left, right in zip(tire_age_centers, tire_age_centers[1:])):
            return 0.0
        scores.append(1.0)
    else:
        # Ordinal A/B/A2 laps must start at comparable tire distance.
        scores.append(max(0.0, 1.0 - (max(tire_age_centers) - min(tire_age_centers)) / 5_000.0))
    return round(min(scores), 3)


def _continuous_stage_cohort(
    lap_numbers: list[int], grouped_rows: dict[int, list[dict[str, Any]]],
) -> tuple[bool, str | None]:
    if not lap_numbers or lap_numbers != list(range(lap_numbers[0], lap_numbers[0] + len(lap_numbers))):
        return False, "Warm-up and measured laps must be consecutive with no pit, reset, or invalid-lap boundary."
    rows_by_lap = [grouped_rows.get(number, []) for number in lap_numbers]
    if any(not rows for rows in rows_by_lap):
        return False, "Every warm-up and measured lap requires a readable telemetry trace."
    if any(
        bool(row.get("on_pit_road"))
        or bool(row.get("reset_event"))
        or bool(row.get("active_reset_event"))
        or bool(row.get("reset_discontinuity"))
        for rows in rows_by_lap
        for row in rows
    ):
        return False, "The stage cohort crosses a pit or reset boundary."
    compounds = {
        str(row.get("player_tire_compound") or row.get("tire_compound"))
        for rows in rows_by_lap
        for row in rows
        if row.get("player_tire_compound") is not None or row.get("tire_compound") is not None
    }
    tire_set_values = {
        channel: {
            value
            for rows in rows_by_lap
            for row in rows
            if (value := _finite(row.get(channel))) is not None
        }
        for channel in ("tire_sets_used", "left_tire_sets_used", "right_tire_sets_used")
    }
    if (
        len(compounds) != 1
        or not any(tire_set_values.values())
        or any(len(values) > 1 for values in tire_set_values.values())
    ):
        return False, "Tire compound or tire-set identity changed inside the stage cohort."
    if _context_score(rows_by_lap, allow_stint_progression=True) < 0.8:
        return False, "Fuel, tire-set, tire-age, compound, or weather continuity changed inside the stage cohort."
    return True, None


def _derive_opportunity(
    run_id: str,
    overview: Any,
    *,
    selected_lap: int | None = None,
    selected_zone_start_pct: float | None = None,
    selected_zone_end_pct: float | None = None,
    selected_phase: str | None = None,
) -> tuple[OpportunityEvidence, float, float, bool | None]:
    selected_zone = _validated_selected_zone(selected_zone_start_pct, selected_zone_end_pct)
    laps = [lap for lap in eligible_laps(overview.laps) if lap.lap_time is not None]
    laps.sort(key=lambda lap: float(lap.lap_time))
    lap_numbers = [lap.lap_number for lap in laps]
    grouped = _lap_rows(run_id, lap_numbers)
    usable = [lap for lap in laps if grouped.get(lap.lap_number)]
    chronological_lap_rows = [
        grouped[lap.lap_number]
        for lap in sorted(usable, key=lambda item: item.lap_number)
    ]
    empty = OpportunityEvidence(
        start_pct=0.0, end_pct=100.0, phase="unknown", observed_time_loss_s=None,
        empirical_noise_s=None, alignment_confidence=0.0, repeatable=False,
        evidence_links=(), source_channels=(),
        contradictory_evidence=("At least three eligible complete laps with readable telemetry are required.",),
    )
    if len(usable) < 3:
        return empty, 0.0, 0.0, None
    if selected_lap is not None and selected_lap not in {lap.lap_number for lap in usable}:
        return empty.model_copy(update={
            "contradictory_evidence": ("The selected lap is not a server-eligible complete lap with readable telemetry.",),
        }), 0.0, 0.0, None

    reference = usable[0]
    comparisons: list[tuple[int, TimeAlignmentResult]] = []
    for lap in usable[1:]:
        comparisons.append((
            lap.lap_number,
            analyze_time_alignment(grouped[reference.lap_number], grouped[lap.lap_number], step_pct=0.2),
        ))
    buckets: dict[tuple[str, float, float], list[tuple[float, float, list[str], int]]] = {}
    for lap_number, result in comparisons:
        for effect in result.phase_effects:
            if effect.delta_s is not None and effect.delta_s > 0 and effect.evidence_state != "unavailable":
                key = (effect.phase, round(effect.start_pct, 1), round(effect.end_pct, 1))
                buckets.setdefault(key, []).append((
                    effect.delta_s,
                    effect.alignment_confidence,
                    effect.source_channels,
                    lap_number,
                ))
    repeated = [
        (key, values)
        for key, values in buckets.items()
        if len(values) >= 2
        and (selected_lap is None or selected_lap == reference.lap_number or selected_lap in {value[3] for value in values})
        and _phase_matches(key[0], selected_phase)
        and _selected_zone_contains_window(selected_zone, key[1], key[2])
    ]
    if not repeated:
        scope = "the selected zone and phase" if selected_zone is not None or selected_phase else "any physical-position phase"
        return empty.model_copy(update={"contradictory_evidence": (f"No loss in {scope} repeated on two eligible laps.",)}), _context_score(chronological_lap_rows, allow_stint_progression=True), 0.0, None
    (phase, start, end), effects = max(repeated, key=lambda item: median(v[0] for v in item[1]))
    lap_times = [float(lap.lap_time) for lap in usable]
    center = median(lap_times)
    noise = median(abs(value - center) for value in lap_times)
    observed = median(value[0] for value in effects)
    alignment = min(value[1] for value in effects)
    sources = tuple(dict.fromkeys(source for value in effects for source in value[2]))

    eligible_numbers = {lap.lap_number for lap in usable}
    links = []
    for event in overview.events:
        related_setup_keys = _expanded_related_setup_keys(event.related_setup_keys)
        if (
            event.lap_number in eligible_numbers and event.valid_for_tuning
            and event_matches_zone(event, (start, end)) and related_setup_keys
            and event_matches_phase(event, phase)
        ):
            links.append(TestEvidenceLink(
                event_id=event.event_id, eligible_lap=True, valid_for_tuning=True,
                phase=phase, related_setup_keys=related_setup_keys,
            ))
    certificates = [
        build_sim_integrity_certificate(grouped[lap.lap_number], expected_sample_rate_hz=overview.session.telemetry_rate_hz)
        for lap in usable
    ]
    integrity = (
        None if any(item.is_clear_for_analysis is None for item in certificates)
        else all(item.is_clear_for_analysis is True for item in certificates)
    )
    driver_score = min(_driver_similarity(grouped[reference.lap_number], grouped[lap.lap_number]) for lap in usable[1:])
    repeatable = observed > noise and alignment >= 0.8 and len(effects) >= 2
    opportunity = OpportunityEvidence(
        start_pct=start, end_pct=end, phase=phase,
        observed_time_loss_s=round(observed, 4), empirical_noise_s=round(noise, 4),
        alignment_confidence=round(alignment, 3), repeatable=repeatable,
        evidence_links=tuple(links), source_channels=sources,
        supporting_evidence=(
            f"{phase.replace('_', ' ').title()} loss repeated on {len(effects)} eligible laps from {start:.1f}% to {end:.1f}% track position.",
            f"Median observed loss {observed:.3f} s versus {noise:.3f} s empirical lap noise.",
        ),
        contradictory_evidence=() if repeatable else ("The phase loss did not clear alignment and empirical-noise gates.",),
    )
    return opportunity, _context_score(
        chronological_lap_rows, allow_stint_progression=True,
    ), driver_score, integrity


def build_server_kaizen_packet(
    run_id: str,
    complaint: str,
    *,
    selected_lap: int | None = None,
    selected_zone_start_pct: float | None = None,
    selected_zone_end_pct: float | None = None,
    selected_zone_label: str | None = None,
    selected_phase: str | None = None,
    objective: str = "setup-development",
    priority: str | None = None,
    repository: RaceLabRepository | None = None,
) -> KaizenEvidencePacket:
    repo = repository or RaceLabRepository()
    overview = repo.get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    effective_phase = selected_phase or _priority_phase(priority)
    dial = build_dial_in_response(
        run_id,
        complaint,
        selected_lap=selected_lap,
        selected_zone_start_pct=selected_zone_start_pct,
        selected_zone_end_pct=selected_zone_end_pct,
        selected_phase=effective_phase,
        objective=objective,
        priority=priority,
        limit=18,
    )
    resolved_phase = effective_phase or dial.interpreted_phase
    opportunity, context_score, driver_score, integrity = _derive_opportunity(
        run_id,
        overview,
        selected_lap=selected_lap,
        selected_zone_start_pct=selected_zone_start_pct,
        selected_zone_end_pct=selected_zone_end_pct,
        selected_phase=resolved_phase,
    )
    requested_phase = (
        resolved_phase
        or ""
    ).casefold()
    complaint_phase_matches = _phase_matches(opportunity.phase, requested_phase)
    if not complaint_phase_matches:
        opportunity = opportunity.model_copy(update={
            "contradictory_evidence": tuple(dict.fromkeys([
                *opportunity.contradictory_evidence,
                f"The complaint points to {requested_phase.replace('_', ' ')}, but the strongest repeatable observed opportunity is {opportunity.phase.replace('_', ' ')}.",
            ])),
        })
    qualified_mechanism_event_ids = set(
        dial.evidence_strength.supporting_event_ids
        if dial.evidence_strength is not None
        else ()
    )
    event_ids_by_key: dict[str, list[str]] = {}
    event_source_channels_by_id = {
        event.event_id: tuple(event.source_channels)
        for event in overview.events
        if event.event_id in qualified_mechanism_event_ids
    }
    event_mechanism_flags_by_id = {
        event.event_id: tuple(sorted(event_mechanism_flags(event.event_type, set(event.source_channels))))
        for event in overview.events
        if event.event_id in qualified_mechanism_event_ids
    }
    for link in opportunity.evidence_links:
        if link.event_id not in qualified_mechanism_event_ids:
            continue
        for key in link.related_setup_keys:
            event_ids_by_key.setdefault(key, []).append(link.event_id)
    candidates: list[CauseCandidate] = []
    for index, swing in enumerate(dial.top_swings):
        swing_event_ids = set(getattr(swing, "supporting_event_ids", ()))
        candidate_event_ids_by_key = {
            key: [event_id for event_id in event_ids if event_id in swing_event_ids]
            for key, event_ids in event_ids_by_key.items()
        }
        candidate = _cause_candidate_from_swing(
            swing,
            index,
            candidate_event_ids_by_key,
            event_source_channels_by_id,
            event_mechanism_flags_by_id,
        )
        if candidate is not None:
            candidate_blockers = list(candidate.blocked_reasons)
            context_blocker = _decision_context_blocker(objective, priority)
            if context_blocker:
                candidate_blockers.append(context_blocker)
            if (
                (priority or "").strip().casefold() == "platform-margin"
                and candidate.control_key not in _PLATFORM_MARGIN_CONTROLS
            ):
                candidate_blockers.append(
                    "Platform-margin priority requires a platform or suspension control with measured platform evidence."
                )
            if getattr(swing, "readiness_label", "") != "Observed mechanism":
                candidate_blockers.append(
                    "This candidate does not have complete observed mechanism evidence; channel capability alone cannot authorize a test."
                )
            elif not candidate.supporting_event_ids:
                candidate_blockers.append(
                    "No qualified mechanism event links this setup control to the selected physical opportunity."
                )
            elif candidate.score_components.get("observed_mechanism_coverage", 0.0) < 1.0:
                candidate_blockers.append(
                    "The opportunity-linked events do not cover every mechanism input required by this candidate."
                )
            if candidate_blockers:
                candidate = candidate.model_copy(update={
                    "score": 0.0,
                    "blocked_reasons": tuple(dict.fromkeys(candidate_blockers)),
                })
            if not complaint_phase_matches:
                candidate = candidate.model_copy(update={
                    "blocked_reasons": tuple(dict.fromkeys([
                        *candidate.blocked_reasons,
                        "The complaint phase and observed opportunity phase do not match; do not attach this setup cause to that time loss.",
                    ])),
                })
            candidates.append(candidate)
    setup = repo.get_setup_snapshot(run_id)
    values = {key: setup_control_value(setup, key) for key in SETUP_CONTROL_SPECS}
    legal_values_by_control: dict[str, list[object]] = {}
    legal_value_provenance_by_control: dict[str, dict[str, list[str]]] = {}
    response_models: dict[str, dict[str, Any]] = {}
    surrounding_fingerprint_by_control: dict[str, str] = {}
    if setup is not None:
        from racelab_engine.services.setup_learning_service import (
            build_setup_response_context,
            get_observed_tech_envelope,
            get_setup_response_models,
            surrounding_setup_fingerprint,
        )

        eligible_numbers = [lap.lap_number for lap in eligible_laps(overview.laps)]
        context_rows_by_lap = _lap_rows(run_id, eligible_numbers)
        context_rows = [row for number in eligible_numbers for row in context_rows_by_lap[number]]
        identity = read_telemetry_manifest(run_id).get("compatibility_identity") or {}
        response_context = build_setup_response_context(
            compatibility_identity=identity,
            rows=context_rows,
            baseline_setup=setup.model_dump(mode="json"),
            package_archetype=str(identity.get("track_configuration_name") or identity.get("track_name") or "unknown"),
            objective=_memory_objective(objective, priority),
        )
        envelope = get_observed_tech_envelope(response_context, db_path=repo.db_path)
        response_models = get_setup_response_models(response_context, db_path=repo.db_path)
        setup_payload = setup.model_dump(mode="json")
        legal_identity_fields = (
            "car_id", "car_path", "car_version", "car_configuration_id", "iracing_build_version",
            "track_id", "track_configuration_name", "track_version", "session_type",
        )
        compatible_snapshots: list[tuple[str, Any]] = []
        for item in repo.list_runs():
            candidate_run_id = str(item.get("run_id") or "")
            candidate_overview = repo.get_overview(candidate_run_id) if candidate_run_id else None
            candidate_setup = repo.get_setup_snapshot(candidate_run_id) if candidate_run_id else None
            if (
                candidate_overview is None
                or candidate_setup is None
                or candidate_overview.session.setup_passed_tech is not True
            ):
                continue
            candidate_identity = read_telemetry_manifest(candidate_run_id).get("compatibility_identity") or {}
            if any(
                identity.get(field) is None
                or candidate_identity.get(field) is None
                or identity.get(field) != candidate_identity.get(field)
                for field in legal_identity_fields
            ):
                continue
            compatible_snapshots.append((candidate_run_id, candidate_setup))
        for key, current_value in values.items():
            surrounding = surrounding_setup_fingerprint(setup_payload, key)
            surrounding_fingerprint_by_control[key] = surrounding
            match = next((
                item for item in envelope.values()
                if item.get("setup_key") == key
                and item.get("surrounding_setup_fingerprint") == surrounding
            ), None)
            observed_values: list[object] = []
            provenance: dict[str, list[str]] = {}
            for candidate_run_id, candidate_setup in compatible_snapshots:
                candidate_payload = candidate_setup.model_dump(mode="json")
                if (
                    _is_complete_single_control_option(setup, candidate_setup, key)
                    and surrounding_setup_fingerprint(candidate_payload, key) == surrounding
                ):
                    candidate_value = setup_control_value(candidate_setup, key)
                    if candidate_value is not None:
                        observed_values.append(candidate_value)
                        provenance.setdefault(_provenance_value_key(key, candidate_value), []).append(
                            f"tech-passing-setup:{candidate_run_id}"
                        )
            if match is not None:
                observed_values.extend(match.get("observed_values", []))
                for observed in match.get("observed_values", []):
                    provenance.setdefault(_provenance_value_key(key, observed), []).extend(
                        f"controlled-observation:{observation_id}"
                        for observation_id in match.get("source_observation_ids", [])
                    )
            if observed_values:
                legal_values_by_control[key] = list(dict.fromkeys([current_value, *observed_values]))
                legal_value_provenance_by_control[key] = provenance
    candidates = _apply_personal_response_models(
        candidates,
        opportunity=opportunity,
        current_setup_values=values,
        surrounding_fingerprint_by_control=surrounding_fingerprint_by_control,
        legal_values_by_control=legal_values_by_control,
        response_models=response_models,
    )
    return build_kaizen_packet(
        opportunity=opportunity,
        canonical_symptom=dial.interpreted_symptom or "unresolved",
        candidates=candidates,
        current_setup_values=values,
        eligible_baseline_laps=len(eligible_laps(overview.laps)),
        context_matched=context_score >= 0.8 and overview.session.setup_passed_tech is True,
        driver_matched=driver_score >= 0.8,
        sim_integrity_clear=integrity,
        legal_values_by_control=legal_values_by_control,
        legal_value_provenance_by_control=legal_value_provenance_by_control,
        external_blockers=[reason for reason in [
            _decision_context_blocker(objective, priority),
            *getattr(dial, "blocker_reasons", ()),
        ] if reason],
    )


def create_workflow(
    run_id: str,
    complaint: str,
    *,
    selected_lap: int | None = None,
    selected_zone_start_pct: float | None = None,
    selected_zone_end_pct: float | None = None,
    selected_zone_label: str | None = None,
    selected_phase: str | None = None,
    objective: str = "setup-development",
    priority: str | None = None,
    repository: RaceLabRepository | None = None,
) -> ControlledWorkflow:
    repo = repository or RaceLabRepository()
    packet = build_server_kaizen_packet(
        run_id,
        complaint,
        selected_lap=selected_lap,
        selected_zone_start_pct=selected_zone_start_pct,
        selected_zone_end_pct=selected_zone_end_pct,
        selected_zone_label=selected_zone_label,
        selected_phase=selected_phase,
        objective=objective,
        priority=priority,
        repository=repo,
    )
    now = datetime.now(timezone.utc)
    decision_context = {
        "selected_lap": selected_lap,
        "selected_zone_start_pct": selected_zone_start_pct,
        "selected_zone_end_pct": selected_zone_end_pct,
        "selected_zone_label": selected_zone_label,
        "selected_phase": selected_phase,
        "objective": (objective or "setup-development").strip(),
        "priority": priority,
    }
    workflow = ControlledWorkflow(
        workflow_id=f"aba_{uuid4().hex[:20]}", created_at=now, updated_at=now,
        status="planned", source_run_id=run_id, complaint=complaint, packet=packet,
        reproduction_snapshot={"decision_context": decision_context},
    )
    repo.save_controlled_workflow(workflow)
    return workflow


def _planned_numeric_value(card: Any) -> float | str | None:
    if card.proposed_value_raw is not None:
        return card.proposed_value_raw
    if card.proposed_value is None:
        return None
    value = numeric_setup_value(card.proposed_value)
    return value if value is not None else card.proposed_value


def _assert_balanced_eligible_cohorts(lap_counts: dict[str, int]) -> None:
    if any(count < 3 for count in lap_counts.values()):
        raise ValueError("A, B, and A2 each require at least three eligible flying laps.")
    if len(set(lap_counts.values())) != 1:
        raise ValueError(
            "A, B, and A2 must have equal eligible-lap counts so every eligible trace is scored without cherry-picking."
        )


def _analysis_code_hash(packet: KaizenEvidencePacket) -> str:
    digest = hashlib.sha256(packet.model_dump_json().encode())
    engine_root = Path(__file__).resolve().parents[1] / "analysis"
    repo_root = Path(__file__).resolve().parents[2]
    for path in (
        Path(__file__),
        engine_root / "comparison.py",
        engine_root / "lap_eligibility.py",
        engine_root / "proximity_context.py",
        engine_root / "setup_controls.py",
        engine_root / "setup_diff.py",
        engine_root / "sim_integrity.py",
        engine_root / "test_director.py",
        engine_root / "time_alignment.py",
        Path(__file__).with_name("setup_learning_service.py"),
        repo_root / "pyproject.toml",
    ):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _setup_snapshot_hash(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _controlled_cohort_size(lap_rows: dict[str, list[list[dict[str, Any]]]]) -> int:
    counts = {stage: len(lap_rows.get(stage, ())) for stage in ("A", "B", "A2")}
    if min(counts.values(), default=0) < 3:
        raise ValueError("A, B, and A2 each require at least three readable eligible lap traces.")
    if len(set(counts.values())) != 1:
        raise ValueError(
            "A, B, and A2 eligible-lap cohort counts must match; no eligible lap may be ignored."
        )
    return counts["A"]


def _score_countereffect_guardrail(
    other_phase_effects: dict[str, list[float]],
    within_baseline_by_phase: dict[str, list[float]],
    *,
    guardrail_declared: bool,
) -> tuple[bool | None, dict[str, float]]:
    noise_by_phase = {
        phase: median(values)
        for phase, values in within_baseline_by_phase.items()
        if len(values) >= 3
    }
    if (
        not guardrail_declared
        or not other_phase_effects
        or any(len(values) < 3 for values in other_phase_effects.values())
        or any(phase not in noise_by_phase for phase in other_phase_effects)
    ):
        return None, noise_by_phase
    passed = not any(
        median(values) > noise_by_phase[phase]
        for phase, values in other_phase_effects.items()
    )
    return passed, noise_by_phase


def _lap_channel_stat(
    rows: list[dict[str, Any]], channel: str, *, reducer: Literal["max", "min"] = "max",
    braking_only: bool = False, absolute: bool = False,
) -> float | None:
    values = [
        value
        for row in rows
        if not braking_only or (_finite(row.get("brake_pct")) or 0.0) >= 10.0
        if (value := _finite(row.get(channel))) is not None
    ]
    if not values:
        return None
    if absolute:
        values = [abs(value) for value in values]
    return max(values) if reducer == "max" else min(values)


def _risk_metric_guardrail(
    lap_rows: dict[str, list[list[dict[str, Any]]]],
    *,
    channel: str,
    reducer: Literal["max", "min"] = "max",
    braking_only: bool = False,
    absolute: bool = False,
    tolerance_floor: float = 0.0,
) -> tuple[bool | None, dict[str, float]]:
    series: dict[str, list[float]] = {}
    for stage in ("A", "B", "A2"):
        values = [
            value
            for rows in lap_rows[stage]
            if (value := _lap_channel_stat(
                rows, channel, reducer=reducer, braking_only=braking_only,
                absolute=absolute,
            )) is not None
        ]
        if len(values) != len(lap_rows[stage]) or len(values) < 3:
            return None, {}
        # Convert clearance (where higher is safer) to the same lower-is-safer
        # risk convention used by the remaining guardrail channels.
        series[stage] = [-value for value in values] if reducer == "min" else values
    baseline_noise = [
        abs(right - left)
        for stage in ("A", "A2")
        for left, right in zip(series[stage], series[stage][1:])
    ]
    if len(baseline_noise) < 3:
        return None, {}
    reference = min(median(series["A"]), median(series["A2"]))
    tolerance = max(tolerance_floor, median(baseline_noise))
    observed_b = median(series["B"])
    return observed_b <= reference + tolerance, {
        f"{channel}_b": round(observed_b, 6),
        f"{channel}_baseline_limit": round(reference + tolerance, 6),
        f"{channel}_baseline_noise": round(median(baseline_noise), 6),
    }


def _control_guardrail_evaluation(
    control_key: str,
    lap_rows: dict[str, list[list[dict[str, Any]]]],
) -> tuple[bool | None, dict[str, float]]:
    front_controls = {
        "lf_ride_height_mm", "rf_ride_height_mm",
        "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm",
    }
    rear_controls = {
        "lr_ride_height_mm", "rr_ride_height_mm",
        "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm",
    }
    if control_key in front_controls:
        candidates = (
            ("front_platform_risk_score", "max", 0.02),
            ("cfs_risk_score", "max", 0.02),
            ("platform_risk_score", "max", 0.02),
            ("cfs_ride_height_in", "min", 0.02),
        )
    elif control_key in rear_controls:
        candidates = (
            ("rear_platform_risk_score", "max", 0.02),
            ("rear_platform_contact_risk", "max", 0.02),
            ("rear_scrape_risk_score", "max", 0.02),
            ("rear_scrape_margin_mm", "min", 0.5),
            ("min_rear_ride_height_mm", "min", 0.5),
        )
    else:
        candidates = ()
    available_results: list[tuple[bool, dict[str, float]]] = []
    for channel, reducer, tolerance in candidates:
        passed, metrics = _risk_metric_guardrail(
            lap_rows, channel=channel, reducer=reducer, tolerance_floor=tolerance,
        )
        if passed is not None:
            available_results.append((passed, metrics))
    if candidates:
        if not available_results:
            return None, {}
        return all(passed for passed, _metrics in available_results), {
            key: value for _passed, metrics in available_results for key, value in metrics.items()
        }

    if control_key == "tape_percent":
        results = [
            _risk_metric_guardrail(lap_rows, channel=channel, tolerance_floor=0.5)
            for channel in ("water_temp", "oil_temp")
        ]
        if any(passed is None for passed, _metrics in results):
            return None, {}
        return all(bool(passed) for passed, _metrics in results), {
            key: value for _passed, metrics in results for key, value in metrics.items()
        }

    if control_key == "rear_end_ratio":
        limiter_passed, limiter_metrics = _risk_metric_guardrail(
            lap_rows, channel="shift_indicator_pct", tolerance_floor=1.0,
        )
        if limiter_passed is None or any(
            _lap_channel_stat(rows, "gear") is None
            for stage in ("A", "B", "A2")
            for rows in lap_rows[stage]
        ):
            return None, {}
        return limiter_passed, limiter_metrics

    if control_key == "front_brake_bias_percent":
        return _risk_metric_guardrail(
            lap_rows, channel="yaw_rate", braking_only=True, absolute=True, tolerance_floor=0.05,
        )

    # Balance and driver-control tests retain the strict target/non-target
    # time, context, driver-input and simulator-integrity guardrails. They do
    # not have an additional universally directional safety KPI.
    return True, {}


def _target_effect_distribution_state(
    target_effects: dict[str, list[float]], noise: float | None,
) -> Literal["faster", "slower", "inconclusive", "inconsistent"] | None:
    if noise is None or not target_effects or any(len(values) < 3 for values in target_effects.values()):
        return None
    all_values = [value for values in target_effects.values() for value in values]
    medians = [median(values) for values in target_effects.values()]
    if all(value < -noise for value in all_values):
        return "faster"
    if all(value > noise for value in all_values):
        return "slower"
    if all(value < -noise for value in medians) or all(value > noise for value in medians):
        return "inconsistent"
    return "inconclusive"


def attach_stage(workflow_id: str, stage: Literal["A", "B", "A2"], run_id: str, *, repository: RaceLabRepository | None = None) -> ControlledWorkflow:
    repo = repository or RaceLabRepository()
    workflow = repo.get_controlled_workflow(workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow not found: {workflow_id}")
    if workflow.packet.decision != "test" or workflow.packet.primary_test is None:
        raise ValueError("This workflow is a measurement mission and has no A/B/A2 setup stage to attach.")
    expected = ("A", "B", "A2")[len(workflow.stage_run_ids)] if len(workflow.stage_run_ids) < 3 else None
    if stage != expected:
        raise ValueError(f"Next required stage is {expected or 'none'}; stages must be attached in A/B/A2 order.")
    overview = repo.get_overview(run_id)
    card = workflow.packet.primary_test
    stage_plan = next(item for item in card.stages if item.stage == stage)
    ordered_eligible = sorted(eligible_laps(overview.laps), key=lambda item: item.lap_number) if overview else []
    required_total = stage_plan.warmup_laps + stage_plan.required_flying_laps
    if overview is None or len(ordered_eligible) < required_total:
        raise ValueError(
            f"Stage {stage} requires {stage_plan.warmup_laps} warm-up laps followed by "
            f"{stage_plan.required_flying_laps} server-eligible measured laps."
        )
    measured_laps = tuple(
        lap.lap_number
        for lap in ordered_eligible[
            stage_plan.warmup_laps:stage_plan.warmup_laps + stage_plan.required_flying_laps
        ]
    )
    if overview.session.setup_passed_tech is not True:
        raise ValueError(f"Stage {stage} setup is not recorded as passing tech inspection.")
    source_overview = repo.get_overview(workflow.source_run_id)
    if source_overview is None or source_overview.session.setup_passed_tech is not True:
        raise ValueError("The source baseline is not recorded as passing tech inspection.")
    identity_fields = (
        "driver_user_id", "car_id", "car_path", "car_version", "track_id",
        "track_configuration_name", "track_version", "iracing_build_version", "session_type",
    )
    source_manifest = read_telemetry_manifest(workflow.source_run_id)
    stage_manifest = read_telemetry_manifest(run_id)
    source_identity = source_manifest.get("compatibility_identity") or {}
    stage_identity = stage_manifest.get("compatibility_identity") or {}
    missing = [key for key in identity_fields if source_identity.get(key) is None or stage_identity.get(key) is None]
    mismatched = [key for key in identity_fields if source_identity.get(key) != stage_identity.get(key)]
    if missing or mismatched:
        raise ValueError(
            "Stage compatibility identity is incomplete or mismatched: "
            + ", ".join([*missing, *mismatched])
            + "."
        )
    previous_run_id = workflow.source_run_id
    previous = source_overview
    previous_manifest = source_manifest
    if workflow.stage_run_ids:
        previous_stage = list(workflow.stage_run_ids)[-1]
        previous_run_id = workflow.stage_run_ids[previous_stage]
        previous = repo.get_overview(previous_run_id)
        assert previous is not None
        previous_manifest = read_telemetry_manifest(previous_run_id)
    previous_interval = _recording_interval(previous, previous_manifest)
    current_interval = _recording_interval(overview, stage_manifest)
    if previous_interval is None or current_interval is None:
        raise ValueError(
            "Immutable recording start/end SessionTime bounds are required for A/B/A2 chronology. "
            "Re-import the source .ibt files to upgrade their telemetry manifests."
        )
    if not _recording_order_is_valid(
        stage=stage,
        run_id=run_id,
        source_run_id=workflow.source_run_id,
        current_interval=current_interval,
        previous_interval=previous_interval,
        workflow_created_epoch_s=workflow.created_at.timestamp(),
    ):
        raise ValueError(
            f"Stage {stage} must be the verified source baseline or begin after {previous_run_id} ended "
            "and, for B/A2, after the workflow was planned; overlapping or historical runs are rejected."
        )
    setup = repo.get_setup_snapshot(run_id)
    observed = setup_control_value(setup, card.control_key)
    baseline = card.current_value
    if stage in {"A", "A2"} and not setup_control_values_equal(card.control_key, observed, baseline):
        raise ValueError(f"Stage {stage} did not restore the recorded baseline {card.control_label} value.")
    planned = _planned_numeric_value(card)
    if stage == "B" and (planned is None or not setup_control_values_equal(card.control_key, observed, planned)):
        raise ValueError(f"Stage B does not contain the exact planned {card.control_label} value.")
    baseline_setup = repo.get_setup_snapshot(workflow.source_run_id)
    changes = diff_setups(baseline_setup, setup)
    unmapped = unmapped_setup_change_paths(baseline_setup, setup, changes)
    if not setup_controls_comparable(baseline_setup, setup) or unmapped:
        raise ValueError("Complete comparable setup snapshots are required; untracked setup changes fail closed.")
    allowed = 1 if stage == "B" else 0
    if len(changes) != allowed or (stage == "B" and changes[0].setup_key != card.control_key):
        raise ValueError("The requested stage contains an unrelated setup change.")
    cohort_laps = [lap.lap_number for lap in ordered_eligible[:required_total]]
    cohort_ok, cohort_reason = _continuous_stage_cohort(
        cohort_laps,
        _lap_rows(run_id, cohort_laps),
    )
    if not cohort_ok:
        raise ValueError(cohort_reason or "The stage cohort is not continuous.")
    stage_ids = {**workflow.stage_run_ids, stage: run_id}
    stage_cohorts = {**workflow.stage_eligible_lap_numbers, stage: measured_laps}
    status = {"A": "a_recorded", "B": "b_recorded", "A2": "a2_recorded"}[stage]
    reproduction_snapshot = dict(workflow.reproduction_snapshot)
    chronology = dict(reproduction_snapshot.get("recording_chronology") or {})
    chronology.setdefault("source", _recording_provenance(source_overview, source_manifest))
    chronology[stage] = _recording_provenance(overview, stage_manifest)
    reproduction_snapshot["recording_chronology"] = chronology
    updated = workflow.model_copy(update={
        "stage_run_ids": stage_ids,
        "stage_eligible_lap_numbers": stage_cohorts,
        "status": status,
        "reproduction_snapshot": reproduction_snapshot,
        "updated_at": datetime.now(timezone.utc),
    })
    repo.save_controlled_workflow(updated)
    return updated


def score_workflow(workflow_id: str, *, repository: RaceLabRepository | None = None) -> ControlledWorkflow:
    repo = repository or RaceLabRepository()
    workflow = repo.get_controlled_workflow(workflow_id)
    if workflow is None or set(workflow.stage_run_ids) != {"A", "B", "A2"}:
        raise ValueError("A, B, and A2 must all be server-verified before scoring.")
    if workflow.status == "scored":
        raise ValueError("A scored controlled workflow is immutable; create a new workflow for another test.")
    card = workflow.packet.primary_test
    assert card is not None
    decision_context = workflow.reproduction_snapshot.get("decision_context", {})
    objective = str(decision_context.get("objective") or "setup-development")
    priority = str(decision_context.get("priority") or "overall-pace")
    if context_blocker := _decision_context_blocker(objective, priority):
        raise ValueError(context_blocker)
    if required_phase := _priority_phase(priority):
        if not _phase_matches(card.target_phase, required_phase):
            raise ValueError(
                "The persisted target phase does not match the workflow's driver priority; create a new plan."
            )
    if priority.casefold() == "platform-margin" and card.control_key not in _PLATFORM_MARGIN_CONTROLS:
        raise ValueError("The persisted control cannot certify platform-margin priority.")
    overviews = {stage: repo.get_overview(run_id) for stage, run_id in workflow.stage_run_ids.items()}
    setups = {stage: repo.get_setup_snapshot(run_id) for stage, run_id in workflow.stage_run_ids.items()}
    source_setup = repo.get_setup_snapshot(workflow.source_run_id)
    if source_setup is None or any(setup is None for setup in setups.values()):
        raise ValueError("Complete source, A, B, and A2 setup snapshots are required at scoring time.")
    setup_pairs = {
        "source-to-A": (source_setup, setups["A"]),
        "A-to-B": (setups["A"], setups["B"]),
        "A-to-A2": (setups["A"], setups["A2"]),
    }
    pair_changes: dict[str, list[Any]] = {}
    for label, (left, right) in setup_pairs.items():
        changes = diff_setups(left, right)
        if (
            not setup_controls_comparable(left, right)
            or unmapped_setup_change_paths(left, right, changes)
        ):
            raise ValueError(f"{label} setup isolation is incomplete or contains unmapped changes.")
        pair_changes[label] = changes
    if pair_changes["source-to-A"] or pair_changes["A-to-A2"]:
        raise ValueError("A and A2 must exactly restore the complete source baseline setup.")
    if (
        len(pair_changes["A-to-B"]) != 1
        or pair_changes["A-to-B"][0].setup_key != card.control_key
    ):
        raise ValueError("B must differ from A by exactly the one planned setup control.")
    planned_value = _planned_numeric_value(card)
    observed_source = setup_control_value(source_setup, card.control_key)
    observed_a = setup_control_value(setups["A"], card.control_key)
    observed_b = setup_control_value(setups["B"], card.control_key)
    observed_a2 = setup_control_value(setups["A2"], card.control_key)
    if (
        planned_value is None
        or not setup_control_values_equal(card.control_key, observed_source, card.current_value)
        or not setup_control_values_equal(card.control_key, observed_a, card.current_value)
        or not setup_control_values_equal(card.control_key, observed_a2, card.current_value)
        or not setup_control_values_equal(card.control_key, observed_b, planned_value)
    ):
        raise ValueError("Scoring-time setup values no longer match the immutable A/B/A2 test plan.")
    if set(workflow.stage_eligible_lap_numbers) != {"A", "B", "A2"}:
        raise ValueError("The immutable post-warmup A/B/A2 measurement cohorts were not recorded at attachment time.")
    lap_counts = {stage: len(workflow.stage_eligible_lap_numbers[stage]) for stage in ("A", "B", "A2")}
    _assert_balanced_eligible_cohorts(lap_counts)
    stage_eligible_lap_numbers: dict[str, tuple[int, ...]] = {}
    lap_rows: dict[str, list[list[dict[str, Any]]]] = {}
    for stage in ("A", "B", "A2"):
        overview = overviews[stage]
        if overview is None:
            raise ValueError(f"Stage {stage} run is unavailable.")
        numbers = list(workflow.stage_eligible_lap_numbers[stage])
        eligible_numbers = {lap.lap_number for lap in eligible_laps(overview.laps)}
        stage_plan = next(item for item in card.stages if item.stage == stage)
        if len(numbers) != stage_plan.required_flying_laps or not set(numbers) <= eligible_numbers:
            raise ValueError(f"Stage {stage} measured cohort changed or contains a no-longer-eligible lap.")
        stage_eligible_lap_numbers[stage] = tuple(numbers)
        grouped = _lap_rows(workflow.stage_run_ids[stage], numbers)
        lap_rows[stage] = [grouped[number] for number in numbers if grouped[number]]
        if len(lap_rows[stage]) < 3:
            raise ValueError(f"Stage {stage} no longer has three readable eligible lap traces.")

    cohort_size = _controlled_cohort_size(lap_rows)

    alignment_confidences: list[float] = []

    def phase_effect(result: TimeAlignmentResult) -> float | None:
        start = workflow.packet.opportunity.start_pct
        end = workflow.packet.opportunity.end_pct
        if getattr(result, "time_delta_complete", None) is not True:
            return None
        coverage = getattr(result, "coverage_fraction", None)
        local = getattr(result, "local_alignment_confidence", None)
        if coverage is None or coverage < 0.95 or local is None:
            return None
        local_confidence = float(local)
        if local_confidence < 0.8:
            return None
        target_indices = [
            index for index, (pct, phase) in enumerate(zip(result.grid_pct, result.phase_by_position))
            if start <= pct <= end and phase == card.target_phase
        ]
        points = getattr(result, "alignment", ())
        target_points = [points[index] for index in target_indices if index < len(points)]
        if target_points and any(point.is_gap or point.confidence < 0.8 for point in target_points):
            return None
        phase_effects = [
            effect for effect in getattr(result, "phase_effects", ())
            if effect.phase == card.target_phase and effect.end_pct >= start and effect.start_pct <= end
        ]
        if phase_effects and any(
            effect.delta_s is None
            or effect.alignment_confidence < 0.8
            or effect.evidence_state in {"unavailable", "blocked_by_context"}
            for effect in phase_effects
        ):
            return None
        alignment_confidences.extend([
            local_confidence,
            *(point.confidence for point in target_points),
            *(effect.alignment_confidence for effect in phase_effects),
        ])
        values = [
            delta
            for pct, phase, delta in zip(
                result.grid_pct,
                result.phase_by_position,
                result.incremental_delta_s,
            )
            if start <= pct <= end and phase == card.target_phase and delta is not None
        ]
        return sum(values) if values else None

    comparison_results: dict[str, list[TimeAlignmentResult]] = {"AB": [], "A2B": []}
    for baseline_stage, key in (("A", "AB"), ("A2", "A2B")):
        comparison_results[key] = [
            analyze_time_alignment(lap_rows[baseline_stage][index], lap_rows["B"][index], step_pct=0.2)
            for index in range(cohort_size)
        ]
    target_effects = {
        key: [effect for result in results if (effect := phase_effect(result)) is not None]
        for key, results in comparison_results.items()
    }
    if any(len(values) < 3 for values in target_effects.values()):
        raise ValueError("Three matched-position target-phase effects are required for both A/B and B/A2.")
    within_baseline: list[float] = []
    within_baseline_by_phase: dict[str, list[float]] = {}
    countereffect_alignment_incomplete = False

    def non_target_phase_totals(result: TimeAlignmentResult) -> dict[str, float]:
        nonlocal countereffect_alignment_incomplete
        if (
            getattr(result, "time_delta_complete", None) is not True
            or getattr(result, "coverage_fraction", None) is None
            or result.coverage_fraction < 0.95
            or getattr(result, "local_alignment_confidence", None) is None
            or result.local_alignment_confidence < 0.8
        ):
            countereffect_alignment_incomplete = True
            return {}
        totals: dict[str, float] = {}
        invalid_phases: set[str] = set()
        points = getattr(result, "alignment", ())
        for index, (pct, phase, delta) in enumerate(zip(
            result.grid_pct, result.phase_by_position, result.incremental_delta_s,
        )):
            if delta is None or phase is None:
                continue
            is_target = (
                workflow.packet.opportunity.start_pct <= pct <= workflow.packet.opportunity.end_pct
                and phase == card.target_phase
            )
            if not is_target:
                if index >= len(points) or points[index].is_gap or points[index].confidence < 0.8:
                    invalid_phases.add(phase)
                    continue
                totals[phase] = totals.get(phase, 0.0) + delta
        qualified_phases = {
            effect.phase
            for effect in getattr(result, "phase_effects", ())
            if effect.delta_s is not None
            and effect.alignment_confidence >= 0.8
            and effect.evidence_state not in {"unavailable", "blocked_by_context"}
        }
        invalid_effect_phases = {
            effect.phase
            for effect in getattr(result, "phase_effects", ())
            if effect.delta_s is None
            or effect.alignment_confidence < 0.8
            or effect.evidence_state in {"unavailable", "blocked_by_context"}
        }
        invalid_phases.update(invalid_effect_phases)
        if getattr(result, "phase_effects", ()):
            totals = {phase: value for phase, value in totals.items() if phase in qualified_phases}
        if invalid_phases:
            countereffect_alignment_incomplete = True
        totals = {phase: value for phase, value in totals.items() if phase not in invalid_phases}
        return totals

    for stage in ("A", "A2"):
        for left, right in zip(lap_rows[stage], lap_rows[stage][1:]):
            baseline_alignment = analyze_time_alignment(left, right, step_pct=0.2)
            effect = phase_effect(baseline_alignment)
            if effect is not None:
                within_baseline.append(abs(effect))
            for phase, phase_delta in non_target_phase_totals(baseline_alignment).items():
                within_baseline_by_phase.setdefault(phase, []).append(abs(phase_delta))
    noise = median(within_baseline) if len(within_baseline) >= 3 else None
    context = min(
        _context_score([lap_rows["A"][index], lap_rows["B"][index], lap_rows["A2"][index]])
        for index in range(cohort_size)
    )
    driver_scores = [
        _driver_similarity(lap_rows[baseline_stage][index], lap_rows["B"][index])
        for baseline_stage in ("A", "A2")
        for index in range(cohort_size)
    ]
    driver = min(driver_scores, default=0.0)
    certificates = [
        build_sim_integrity_certificate(
            rows,
            expected_sample_rate_hz=overviews[stage].session.telemetry_rate_hz,
        )
        for stage in ("A", "B", "A2")
        for rows in lap_rows[stage]
    ]
    integrity = min((item.confidence_cap if item.is_clear_for_analysis else 0.0) for item in certificates)
    other_phase_effects: dict[str, list[float]] = {}
    for results in comparison_results.values():
        for result in results:
            for phase, effect in non_target_phase_totals(result).items():
                other_phase_effects.setdefault(phase, []).append(effect)
    declared_guardrail = _TIME_COUNTEREFFECT_GUARDRAIL
    countereffect_passed, countereffect_noise_by_phase = _score_countereffect_guardrail(
        other_phase_effects,
        within_baseline_by_phase,
        guardrail_declared=(
            declared_guardrail in card.countereffects
            and not countereffect_alignment_incomplete
        ),
    )
    control_guardrails_passed, control_guardrail_metrics = _control_guardrail_evaluation(
        card.control_key,
        lap_rows,
    )
    target_distribution_state = _target_effect_distribution_state(target_effects, noise)
    unrelated = [change.setup_key for change in diff_setups(setups["A"], setups["B"]) if change.setup_key != card.control_key]
    execution = TestExecution(
        eligible_laps_a=lap_counts["A"], eligible_laps_b=lap_counts["B"], eligible_laps_a2=lap_counts["A2"],
        unrelated_setup_changes=len(unrelated), unrelated_changed_controls=tuple(unrelated),
        control_key=card.control_key, planned_b_value=_planned_numeric_value(card),
        observed_a_value=setup_control_value(setups["A"], card.control_key),
        observed_b_value=setup_control_value(setups["B"], card.control_key),
        observed_a2_value=setup_control_value(setups["A2"], card.control_key),
        context_match_score=context, driver_match_score=driver, sim_integrity_score=integrity,
        phase_effect_b_vs_a_s=median(target_effects["AB"]),
        phase_effect_b_vs_a2_s=median(target_effects["A2B"]),
        empirical_noise_s=noise,
        empirical_noise_observations=len(within_baseline),
        minimum_alignment_confidence=min(alignment_confidences, default=None),
        countereffect_noise_by_phase_s=countereffect_noise_by_phase,
        target_effect_distributions_consistent=target_distribution_state in {"faster", "slower"},
        target_effect_distribution_state=target_distribution_state,
        countereffect_passed=countereffect_passed,
        control_guardrails_passed=control_guardrails_passed,
        control_guardrail_metrics=control_guardrail_metrics,
    )
    result = score_test_execution(execution)
    observed_effect = median([*target_effects["AB"], *target_effects["A2B"]])
    learning_admitted: bool | None = None
    if result.controlled_effect_eligible and result.verdict in {"keep", "undo"}:
        from racelab_engine.analysis.comparison import (
            DidItWorkVerdict,
            DriverComparison,
            PaceComparison,
            TargetZoneComparison,
            TestDisciplineResult,
        )
        from racelab_engine.models.evidence import EvidenceState
        from racelab_engine.services.setup_learning_service import (
            build_setup_response_context,
            record_setup_response,
        )

        identity = read_telemetry_manifest(workflow.stage_run_ids["A"]).get("compatibility_identity") or {}
        baseline_setup_dict = setups["A"].model_dump(mode="json") if setups["A"] is not None else None
        test_setup_dict = setups["B"].model_dump(mode="json") if setups["B"] is not None else None
        response_context = build_setup_response_context(
            compatibility_identity=identity,
            rows=[row for lap in lap_rows["A"] for row in lap],
            baseline_setup=baseline_setup_dict,
            package_archetype=str(identity.get("track_configuration_name") or identity.get("track_name") or "unknown"),
            objective=_memory_objective(
                str(workflow.reproduction_snapshot.get("decision_context", {}).get("objective") or "setup-development"),
                str(workflow.reproduction_snapshot.get("decision_context", {}).get("priority") or "") or None,
            ),
        )
        evidence_ids = list(dict.fromkeys([
            *card.evidence_event_ids,
            *(f"{workflow.workflow_id}:{stage}:{workflow.stage_run_ids[stage]}" for stage in ("A", "B", "A2")),
        ]))
        source_channels = list(dict.fromkeys([
            *workflow.packet.opportunity.source_channels,
            *(channel for results in comparison_results.values() for aligned in results for channel in aligned.source_channels),
        ]))
        learning_admitted = record_setup_response(
            comparison_id=workflow.workflow_id,
            car_name=overviews["B"].session.car_name,
            track_name=overviews["B"].session.track_display_name or overviews["B"].session.track_name,
            baseline_run_id=workflow.stage_run_ids["A"],
            test_run_id=workflow.stage_run_ids["B"],
            baseline_lap=stage_eligible_lap_numbers["A"][0],
            test_lap=stage_eligible_lap_numbers["B"][0],
            setup_changes=diff_setups(setups["A"], setups["B"]),
            discipline=TestDisciplineResult(score=100, label="clean"),
            target_zone=TargetZoneComparison(
                start_pct=workflow.packet.opportunity.start_pct,
                end_pct=workflow.packet.opportunity.end_pct,
            ),
            verdict=DidItWorkVerdict(
                verdict="keep_direction" if result.verdict == "keep" else "undo",
                confidence_score=result.score / 100.0,
                headline=(
                    "Controlled A/B/A2 effect reproduced and cleared countereffects."
                    if result.verdict == "keep"
                    else "Controlled target response measured, but a control-specific guardrail worsened."
                    if execution.control_guardrails_passed is False
                    else "Controlled target response measured, but a non-target countereffect worsened."
                    if execution.countereffect_passed is False
                    else "Controlled A/B/A2 effect reproduced in the wrong direction."
                ),
                evidence=list(result.supporting_evidence),
                warnings=list(result.contradictory_evidence),
            ),
            pace=PaceComparison(
                cohort_delta_s=observed_effect,
                baseline_eligible_laps=lap_counts["A"],
                test_eligible_laps=lap_counts["B"],
                noise_band_s=noise,
                is_significant=True,
                direction="faster" if observed_effect < 0 else "slower",
                confidence_score=result.score / 100.0,
            ),
            driver=DriverComparison(driver_verdict="consistent", repeatability_score=driver * 100.0),
            context_problem_count=0,
            response_context=response_context,
            test_driver_id=str((read_telemetry_manifest(workflow.stage_run_ids["B"]).get("compatibility_identity") or {}).get("driver_user_id") or ""),
            sim_integrity_clear=True,
            controlled_effect_eligible=True,
            evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
            source_channels=source_channels,
            evidence_event_ids=evidence_ids,
            source_run_ids=[
                workflow.stage_run_ids["A"],
                workflow.stage_run_ids["B"],
                workflow.stage_run_ids["A2"],
            ],
            controlled_effect_components={
                "b_vs_a_target_effects_s": target_effects["AB"],
                "b_vs_a2_target_effects_s": target_effects["A2B"],
                "pooled_effect_s": [observed_effect],
                "within_baseline_noise_effects_s": within_baseline,
                **{
                    f"within_baseline_{phase}_countereffect_noise_s": values
                    for phase, values in within_baseline_by_phase.items()
                },
                **{
                    f"observed_{phase}_countereffect_s": values
                    for phase, values in other_phase_effects.items()
                },
                **{
                    f"control_guardrail_{name}": [value]
                    for name, value in control_guardrail_metrics.items()
                },
            },
            baseline_setup_passed_tech=True,
            test_setup_passed_tech=True,
            baseline_setup_for_model=baseline_setup_dict,
            test_setup_for_model=test_setup_dict,
            is_same_run=False,
            target_phase=card.target_phase,
            db_path=repo.db_path,
        )
    reproduction_stages: dict[str, Any] = {}
    for stage in ("A", "B", "A2"):
        manifest = read_telemetry_manifest(workflow.stage_run_ids[stage])
        setup_payload = setups[stage].model_dump(mode="json") if setups[stage] is not None else None
        reproduction_stages[stage] = {
            "run_id": workflow.stage_run_ids[stage],
            "source_file_sha256": overviews[stage].session.file_hash,
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "cache_version": manifest.get("cache_version"),
            "compatibility_identity": manifest.get("compatibility_identity") or {},
            "setup_fingerprint": _setup_snapshot_hash(setup_payload),
            "setup_values": setup_payload,
            "eligible_lap_numbers": list(stage_eligible_lap_numbers[stage]),
        }
    reproduction_snapshot = {
        "analysis_version": workflow.analysis_version,
        "analysis_code_and_config_sha256": _analysis_code_hash(workflow.packet),
        "stages": reproduction_stages,
        "target_effect_distributions_s": {
            "b_vs_a": target_effects["AB"],
            "b_vs_a2": target_effects["A2B"],
            "within_baseline_noise": within_baseline,
        },
        "pooled_target_effect_s": observed_effect,
        "countereffect_phase_distributions_s": other_phase_effects,
        "countereffect_baseline_noise_distributions_s": within_baseline_by_phase,
        "recording_chronology": workflow.reproduction_snapshot.get("recording_chronology", {}),
        "decision_context": workflow.reproduction_snapshot.get("decision_context", {}),
    }
    updated = workflow.model_copy(update={
        "stage_eligible_lap_numbers": stage_eligible_lap_numbers,
        "execution": execution,
        "reproduction_snapshot": reproduction_snapshot,
        "quality": result,
        "learning_admitted": learning_admitted,
        "status": "scored",
        "updated_at": datetime.now(timezone.utc),
    })
    repo.save_controlled_workflow(updated)
    return updated


__all__ = ["attach_stage", "build_server_kaizen_packet", "create_workflow", "score_workflow"]
