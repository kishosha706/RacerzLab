"""Server-owned Crew Chief and controlled A/B/A2 workflow assembly."""

from __future__ import annotations

import math
import hashlib
import json
import logging
import re
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
from racelab_engine.analysis.proximity_context import classify_proximity_time_gap_window
from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    canonical_setup_value_key,
    format_setup_value,
    numeric_setup_value,
    resolve_adjacent_setup_target,
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
    ControlledTestCard,
    MeasurementMission,
    TestEvidenceLink,
    TestExecution,
    score_test_execution,
)
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.analysis.time_alignment import TimeAlignmentResult, analyze_time_alignment
from racelab_engine.knowledge.setup.dial_in_service import build_dial_in_response
from racelab_engine.knowledge.setup.dial_in_controls import expanded_related_setup_keys
from racelab_engine.knowledge.setup.evidence_adapter import (
    event_matches_phase,
    event_matches_zone,
    event_mechanism_flags,
)
from racelab_engine.models.controlled_workflow import (
    AppliedControlCertificate,
    ControlledWorkflow,
    StageExperimentContext,
    VehicleConditionEpoch,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.services.engineering_memory_service import (
    record_workflow_cancellation,
    record_workflow_outcome,
    record_workflow_plan,
    record_workflow_stage,
)
from racelab_engine.services.import_service import read_telemetry_manifest, read_telemetry_rows
from racelab_engine.services.session_intelligence_service import (
    build_hypothesis_lifecycle,
    controlled_hypothesis_policy_identity,
    evaluate_hypothesis_repeat,
)
from racelab_engine.services.session_service import get_session, list_sessions
from racelab_engine.storage.repository import RaceLabRepository


_log = logging.getLogger(__name__)


_WORKFLOW_COLUMNS = [
    "lap", "lap_dist_pct_100", "lap_dist_ft", "session_time", "session_tick",
    "speed_mps", "speed_mph", "throttle_pct", "brake_pct", "steering_deg",
    "yaw_rate", "lat_accel", "long_accel", "vert_accel", "vert_accel_g",
    "lat", "lon", "alt", "on_pit_road", "enter_exit_reset_state",
    "fuel_level", "air_temp", "track_temp", "wind_vel",
    "wind_dir", "precipitation", "track_wetness", "skies", "relative_humidity",
    "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
    "lf_temp_left", "lf_temp_middle", "lf_temp_right",
    "rf_temp_left", "rf_temp_middle", "rf_temp_right",
    "lr_temp_left", "lr_temp_middle", "lr_temp_right",
    "rr_temp_left", "rr_temp_middle", "rr_temp_right",
    "player_incident_count", "player_driver_incident_count", "player_team_incident_count",
    "player_tow_service_time_s", "player_pit_service_status",
    "pit_repair_remaining_s", "pit_optional_repair_remaining_s", "pending_pit_service_flags",
    "applied_brake_bias",
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
_WORKFLOW_PACKET_BLOCKER = (
    "Stored workflow evidence failed server revalidation. Exact setup targets and "
    "protocol instructions are withheld; cancel this workflow and create a new one."
)
_REPEAT_POLICY_UNVERIFIABLE_BLOCKER = (
    "The exact hypothesis repeat-policy identity could not be verified; rebuild the "
    "controlled test from current evidence before exposing or executing a setup target."
)
_REPEAT_POLICY_BLOCKED_BLOCKER = (
    "This unchanged context, setup, physical target, symptom, cause, control, direction, "
    "metric, phase, and countereffect policy previously produced a valid Undo result in "
    "this session and is marked do-not-repeat."
)
_DECISION_CONTEXT_KEYS = frozenset({
    "selected_lap",
    "lap_scope",
    "window_start_lap",
    "window_end_lap",
    "representative_lap",
    "selected_zone_start_pct",
    "selected_zone_end_pct",
    "selected_zone_label",
    "selected_phase",
    "objective",
    "priority",
})
_WORKFLOW_LAP_SCOPES = frozenset({"run", "single_lap", "lap_window", "track_zone"})
P19_WORKFLOW_AUTHORITY_BINDING_SCHEMA = "p19.controlled-workflow-authority.v1"

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
    event_ids_by_key: dict[str, list[str]],
    event_source_channels_by_id: dict[str, tuple[str, ...]] | None = None,
    event_mechanism_flags_by_id: dict[str, tuple[str, ...]] | None = None,
) -> CauseCandidate | None:
    """Build an evidence score without treating static rank as probability."""
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


_INCIDENT_CHANNELS = (
    "player_incident_count", "player_driver_incident_count", "player_team_incident_count",
)
_CONDITION_BOUNDARY_CHANNELS = (
    "player_tow_service_time_s", "player_pit_service_status", "pit_repair_remaining_s",
    "pit_optional_repair_remaining_s", "pending_pit_service_flags",
)


def _vehicle_condition_epoch(rows: list[dict[str, Any]]) -> VehicleConditionEpoch:
    observed = tuple(sorted({
        channel for channel in (*_INCIDENT_CHANNELS, *_CONDITION_BOUNDARY_CHANNELS)
        if any(_finite(row.get(channel)) is not None for row in rows)
    }))
    reasons: list[str] = []
    baselines: dict[str, float] = {}
    if not all(channel in observed for channel in _INCIDENT_CHANNELS):
        reasons.append("All authoritative incident counters require healthy cohort coverage.")
    for channel in _INCIDENT_CHANNELS:
        values = [_finite(row.get(channel)) for row in rows]
        finite_values = [value for value in values if value is not None]
        if len(finite_values) != len(rows) or not finite_values:
            continue
        baselines[channel] = finite_values[0]
        if finite_values[0] != 0:
            reasons.append(f"{channel} was already elevated when the recording began; prior condition is unknown.")
        if max(finite_values) != min(finite_values):
            reasons.append(f"{channel} crossed a vehicle-condition boundary inside the cohort.")
    boundary_observed = False
    for channel in _CONDITION_BOUNDARY_CHANNELS:
        values = [_finite(row.get(channel)) for row in rows]
        finite_values = [value for value in values if value is not None]
        if not finite_values:
            continue
        if max(finite_values) != min(finite_values) or any(value > 0 for value in finite_values):
            boundary_observed = True
            reasons.append(f"{channel} indicates tow, repair, or pit-service condition uncertainty.")
    status: Literal["known_clear", "unknown", "boundary_observed"]
    if boundary_observed or any("crossed" in reason for reason in reasons):
        status = "boundary_observed"
    elif reasons:
        status = "unknown"
    else:
        status = "known_clear"
    identity = canonical_json_sha256({
        "schema": "p31.vehicle-condition-epoch.v1",
        "status": status,
        "incident_baseline": baselines,
        "observed_channels": observed,
    })
    return VehicleConditionEpoch(
        status=status,
        identity_sha256=identity,
        observed_channels=observed,
        incident_baseline=baselines,
        blocker_reasons=tuple(reasons),
    )


def _applied_control_certificate(
    rows: list[dict[str, Any]], *, control_key: str, expected_value: Any,
) -> AppliedControlCertificate:
    if control_key != "front_brake_bias_percent":
        return AppliedControlCertificate(status="not_applicable", control_key=control_key)
    expected = _finite(expected_value)
    values = [_finite(row.get("applied_brake_bias")) for row in rows]
    observed = [value for value in values if value is not None]
    coverage = len(observed) / len(rows) if rows else 0.0
    if expected is None or coverage < 0.95:
        return AppliedControlCertificate(
            status="missing", control_key=control_key, expected_value=expected,
            coverage_fraction=coverage, source_channel="applied_brake_bias",
            blocker_reasons=("Applied brake-bias coverage must be at least 95% for this experiment.",),
        )
    spread = max(observed) - min(observed)
    center = median(observed)
    if spread > 0.05:
        return AppliedControlCertificate(
            status="mutated", control_key=control_key, expected_value=expected,
            observed_value=center, coverage_fraction=coverage, observed_range=spread,
            source_channel="applied_brake_bias",
            blocker_reasons=("Applied brake bias changed inside the controlled cohort.",),
        )
    if not math.isclose(center, expected, abs_tol=0.05):
        return AppliedControlCertificate(
            status="setup_mismatch", control_key=control_key, expected_value=expected,
            observed_value=center, coverage_fraction=coverage, observed_range=spread,
            source_channel="applied_brake_bias",
            blocker_reasons=("Applied brake bias does not match the immutable planned garage value.",),
        )
    return AppliedControlCertificate(
        status="stable", control_key=control_key, expected_value=expected,
        observed_value=center, coverage_fraction=coverage, observed_range=spread,
        source_channel="applied_brake_bias",
    )


def _stage_experiment_context(
    rows: list[dict[str, Any]], *, control_key: str, expected_value: Any,
) -> StageExperimentContext:
    return StageExperimentContext(
        vehicle_condition=_vehicle_condition_epoch(rows),
        applied_control=_applied_control_certificate(
            rows, control_key=control_key, expected_value=expected_value,
        ),
    )


def _experiment_context_blocker(context: StageExperimentContext) -> str | None:
    if context.vehicle_condition.status != "known_clear":
        return " ".join(context.vehicle_condition.blocker_reasons) or "Vehicle condition is unknown."
    if context.applied_control.status not in {"not_applicable", "stable"}:
        return " ".join(context.applied_control.blocker_reasons) or "Applied control state is unverified."
    return None


def _context_score(
    lap_sets: list[list[dict[str, Any]]], *, allow_stint_progression: bool = False,
) -> float:
    if len(lap_sets) < 3:
        return 0.0
    if any(
        classify_proximity_time_gap_window(rows).hard_blocker_active
        for rows in lap_sets
    ):
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
    tolerances = {
        "air_temp": 5.0, "track_temp": 5.0, "wind_vel": 5.0,
        "relative_humidity": 10.0, "precipitation": 0.01,
    }
    scores: list[float] = []
    for channel, tolerance in tolerances.items():
        centers = [median(values) for rows in lap_sets if (values := [_finite(r.get(channel)) for r in rows if _finite(r.get(channel)) is not None])]
        if len(centers) != len(lap_sets):
            return 0.0
        scores.append(max(0.0, 1.0 - (max(centers) - min(centers)) / tolerance))
    wind_directions: list[float] = []
    for rows in lap_sets:
        values = [_finite(row.get("wind_dir")) for row in rows]
        finite_values = [value for value in values if value is not None]
        if len(finite_values) < 0.9 * len(rows) or not finite_values:
            return 0.0
        sin_center = median([math.sin(value) for value in finite_values])
        cos_center = median([math.cos(value) for value in finite_values])
        wind_directions.append(math.atan2(sin_center, cos_center))
    angular_span = max(
        abs(math.atan2(math.sin(left - right), math.cos(left - right)))
        for left in wind_directions for right in wind_directions
    )
    scores.append(max(0.0, 1.0 - angular_span / math.radians(30.0)))
    for channel in ("track_wetness", "skies"):
        centers = []
        for rows in lap_sets:
            values = [_finite(row.get(channel)) for row in rows]
            finite_values = [value for value in values if value is not None]
            if len(finite_values) < 0.9 * len(rows) or not finite_values:
                return 0.0
            centers.append(median(finite_values))
        if max(centers) != min(centers):
            return 0.0
        scores.append(1.0)
    for corner in ("lf", "rf", "lr", "rr"):
        for channel, relative_tolerance, absolute_floor in (
            (f"{corner}_pressure", 0.05, 1.0),
            (f"{corner}_temp_middle", 0.08, 5.0),
        ):
            centers = []
            for rows in lap_sets:
                values = [_finite(row.get(channel)) for row in rows]
                finite_values = [value for value in values if value is not None]
                if len(finite_values) < 0.7 * len(rows) or not finite_values:
                    return 0.0
                centers.append(median(finite_values))
            tolerance = max(abs(median(centers)) * relative_tolerance, absolute_floor)
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
    condition = _vehicle_condition_epoch([row for rows in rows_by_lap for row in rows])
    if condition.status != "known_clear":
        return False, " ".join(condition.blocker_reasons) or "Vehicle condition is unknown."
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


def _discover_legal_setup_options(
    run_id: str,
    *,
    overview: Any,
    objective: str,
    priority: str | None,
    repository: RaceLabRepository,
) -> tuple[
    dict[str, object],
    dict[str, list[object]],
    dict[str, dict[str, list[str]]],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    """Load only exact-context, sourced setup options before Dial-In selects a target."""
    setup = repository.get_setup_snapshot(run_id)
    values = {key: setup_control_value(setup, key) for key in SETUP_CONTROL_SPECS}
    legal_values_by_control: dict[str, list[object]] = {}
    legal_value_provenance_by_control: dict[str, dict[str, list[str]]] = {}
    response_models: dict[str, dict[str, Any]] = {}
    surrounding_fingerprint_by_control: dict[str, str] = {}
    if setup is None:
        return (
            values,
            legal_values_by_control,
            legal_value_provenance_by_control,
            response_models,
            surrounding_fingerprint_by_control,
        )

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
        package_archetype=str(
            identity.get("track_configuration_name") or identity.get("track_name") or "unknown"
        ),
        objective=_memory_objective(objective, priority),
    )
    envelope = get_observed_tech_envelope(response_context, db_path=repository.db_path)
    response_models = get_setup_response_models(response_context, db_path=repository.db_path)
    setup_payload = setup.model_dump(mode="json")
    for key in values:
        surrounding_fingerprint_by_control[key] = surrounding_setup_fingerprint(
            setup_payload, key,
        )
    legal_identity_fields = (
        "car_id", "car_path", "car_version", "car_configuration_id", "iracing_build_version",
        "track_id", "track_configuration_name", "track_version", "session_type",
    )
    observed_snapshot_options: dict[str, list[tuple[str, object]]] = {}
    for candidate_run_id, candidate_setup in repository.list_tech_passing_setup_candidates(
        car_path=overview.session.car_path,
        track_id_or_path=overview.session.track_id_or_path,
        session_type=overview.session.session_type,
    ):
        if candidate_run_id == run_id:
            continue
        changes = diff_setups(setup, candidate_setup)
        if (
            not setup_controls_comparable(setup, candidate_setup)
            or len(changes) != 1
            or unmapped_setup_change_paths(setup, candidate_setup, changes)
        ):
            continue
        key = changes[0].setup_key
        if key not in values:
            continue
        candidate_payload = candidate_setup.model_dump(mode="json")
        if (
            surrounding_setup_fingerprint(candidate_payload, key)
            != surrounding_fingerprint_by_control[key]
        ):
            continue
        candidate_value = setup_control_value(candidate_setup, key)
        if candidate_value is None:
            continue
        candidate_identity = read_telemetry_manifest(candidate_run_id).get("compatibility_identity") or {}
        if any(
            identity.get(field) is None
            or candidate_identity.get(field) is None
            or identity.get(field) != candidate_identity.get(field)
            for field in legal_identity_fields
        ):
            continue
        observed_snapshot_options.setdefault(key, []).append(
            (candidate_run_id, candidate_value)
        )
    for key, current_value in values.items():
        surrounding = surrounding_fingerprint_by_control[key]
        match = next((
            item for item in envelope.values()
            if item.get("setup_key") == key
            and item.get("surrounding_setup_fingerprint") == surrounding
        ), None)
        observed_values: list[object] = []
        provenance: dict[str, list[str]] = {}
        for candidate_run_id, candidate_value in observed_snapshot_options.get(key, []):
            observed_values.append(candidate_value)
            provenance.setdefault(_provenance_value_key(key, candidate_value), []).append(
                f"tech-passing-setup:{candidate_run_id}"
            )
        if match is not None:
            observed_options = match.get("observed_options", [])
            observed_values.extend(
                option.get("value") for option in observed_options if option.get("value") is not None
            )
            for option in observed_options:
                observed = option.get("value")
                if observed is None:
                    continue
                provenance.setdefault(_provenance_value_key(key, observed), []).extend(
                    f"controlled-observation:{observation_id}"
                    for observation_id in option.get("source_observation_ids", [])
                )
        if observed_values:
            legal_values_by_control[key] = list(dict.fromkeys([current_value, *observed_values]))
            legal_value_provenance_by_control[key] = {
                value_key: list(dict.fromkeys(source_ids))
                for value_key, source_ids in provenance.items()
            }
    return (
        values,
        legal_values_by_control,
        legal_value_provenance_by_control,
        response_models,
        surrounding_fingerprint_by_control,
    )


def validate_controlled_test_target(
    run_id: str,
    card: ControlledTestCard,
    *,
    overview: Any,
    objective: str,
    priority: str | None,
    repository: RaceLabRepository,
) -> tuple[str, ...]:
    """Re-prove a persisted exact target against the current server-owned catalog.

    Stored card strings and provenance tokens are an audit record, not authority.
    Authorization is retained only when the exact current value, adjacent target,
    display transition, and every recorded source are reproduced from immutable
    same-context tech/observation evidence.
    """
    if overview.session.setup_passed_tech is not True:
        return (
            "The source baseline setup is not currently recorded as tech-passing.",
        )
    try:
        (
            current_values,
            legal_values_by_control,
            legal_provenance_by_control,
            _,
            _,
        ) = _discover_legal_setup_options(
            run_id,
            overview=overview,
            objective=objective,
            priority=priority,
            repository=repository,
        )
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
        return (
            "The stored setup target could not be revalidated from the current immutable run context.",
        )

    key = card.control_key
    current_value = current_values.get(key)
    blockers: list[str] = []
    if (
        current_value is None
        or card.current_value != current_value
        or not setup_control_values_equal(key, current_value, card.current_value)
    ):
        blockers.append(
            "The stored controlled-test baseline no longer matches the run's setup snapshot."
        )

    resolution = resolve_adjacent_setup_target(
        key,
        current_value,
        card.direction_sign,
        legal_values=legal_values_by_control.get(key),
        legal_value_provenance=legal_provenance_by_control.get(key),
    )
    if resolution.blocker:
        blockers.append(
            "The current server-owned catalog does not prove a sourced, small adjacent target "
            "for this control and direction."
        )
        return tuple(dict.fromkeys(blockers))

    target_value = resolution.target_value
    if target_value is None or not setup_control_values_equal(
        key, target_value, card.proposed_value_raw,
    ):
        blockers.append(
            "The stored controlled-test target is not the currently proven adjacent garage option."
        )
    expected_label = format_setup_value(key, target_value)
    if card.proposed_value != expected_label:
        blockers.append(
            "The stored controlled-test target label does not match the proven adjacent option."
        )
    expected_transition = (
        f"{format_setup_value(key, current_value)} -> {expected_label} "
        "(adjacent observed tech-passing option)"
    )
    if card.exact_change != expected_transition:
        blockers.append(
            "The stored controlled-test instruction does not match the proven adjacent transition."
        )
    proven_sources = set(resolution.provenance)
    stored_sources = set(card.proposed_value_provenance)
    if not stored_sources or not stored_sources.issubset(proven_sources):
        blockers.append(
            "The stored controlled-test provenance is not tied to that exact current legal option."
        )
    return tuple(dict.fromkeys(blockers))


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
    (
        values,
        legal_values_by_control,
        legal_value_provenance_by_control,
        response_models,
        surrounding_fingerprint_by_control,
    ) = _discover_legal_setup_options(
        run_id,
        overview=overview,
        objective=objective,
        priority=priority,
        repository=repo,
    )
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
        legal_values_by_control=legal_values_by_control,
        legal_value_provenance_by_control=legal_value_provenance_by_control,
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
    for swing in dial.top_swings:
        swing_event_ids = set(getattr(swing, "supporting_event_ids", ()))
        candidate_event_ids_by_key = {
            key: [event_id for event_id in event_ids if event_id in swing_event_ids]
            for key, event_ids in event_ids_by_key.items()
        }
        candidate = _cause_candidate_from_swing(
            swing,
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
            *(
                getattr(dial, "blocker_reasons", ())
                if not dial.top_swings or getattr(dial, "evidence_state", None) == "blocked_by_context"
                else ()
            ),
        ] if reason],
    )


def _normalize_workflow_lap_context(
    *,
    selected_lap: int | None,
    lap_scope: str | None,
    window_start_lap: int | None,
    window_end_lap: int | None,
    representative_lap: int | None,
) -> tuple[str, int | None, int | None, int | None]:
    scope = lap_scope or ("single_lap" if selected_lap is not None else "run")
    if scope not in _WORKFLOW_LAP_SCOPES:
        raise ValueError("Workflow lap scope must be run, single_lap, lap_window, or track_zone.")
    identities = (selected_lap, window_start_lap, window_end_lap, representative_lap)
    if any(value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1) for value in identities):
        raise ValueError("Workflow lap identities must be positive integer lap numbers.")
    if scope == "lap_window":
        if None in identities:
            raise ValueError(
                "Lap-window workflows require start, end, representative, and selected lap identities."
            )
        assert window_start_lap is not None
        assert window_end_lap is not None
        assert representative_lap is not None
        if not window_start_lap <= representative_lap <= window_end_lap:
            raise ValueError("The representative lap must fall inside the selected lap window.")
        if selected_lap != representative_lap:
            raise ValueError("The planner selected lap must equal the window representative lap.")
    elif any(value is not None for value in (window_start_lap, window_end_lap, representative_lap)):
        raise ValueError("Lap-window identities require lap_scope='lap_window'.")
    if scope == "single_lap" and selected_lap is None:
        raise ValueError("Single-lap workflow scope requires selected_lap.")
    if scope == "run" and selected_lap is not None:
        raise ValueError("Run-scoped workflows cannot carry a selected lap identity.")
    return scope, window_start_lap, window_end_lap, representative_lap


def _workflow_decision_context(workflow: ControlledWorkflow) -> dict[str, Any]:
    snapshot = workflow.reproduction_snapshot
    if not isinstance(snapshot, dict):
        raise ValueError("The stored workflow reproduction snapshot is malformed.")
    context = snapshot.get("decision_context") or {}
    if not isinstance(context, dict) or set(context) != _DECISION_CONTEXT_KEYS:
        raise ValueError("The stored workflow decision context is malformed.")
    if not isinstance(workflow.complaint, str) or not workflow.complaint.strip():
        raise ValueError("The stored workflow complaint is unavailable.")
    lap_scope, _window_start, _window_end, _representative = _normalize_workflow_lap_context(
        selected_lap=context.get("selected_lap"),
        lap_scope=context.get("lap_scope"),
        window_start_lap=context.get("window_start_lap"),
        window_end_lap=context.get("window_end_lap"),
        representative_lap=context.get("representative_lap"),
    )
    selected_zone = _validated_selected_zone(
        context.get("selected_zone_start_pct"),
        context.get("selected_zone_end_pct"),
    )
    if lap_scope == "track_zone" and selected_zone is None:
        raise ValueError("Track-zone workflow scope requires an exact physical window.")
    return dict(context)


def _workflow_plan_binding_hash(
    workflow: ControlledWorkflow,
    packet: KaizenEvidencePacket,
    context: dict[str, Any],
) -> str:
    payload = {
        "source_run_id": workflow.source_run_id,
        "complaint": workflow.complaint,
        "decision_context": context,
        "packet": packet.model_dump(mode="json"),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def workflow_authority_action_identity(
    workflow: ControlledWorkflow,
) -> dict[str, object]:
    """Return the exact public P19 action identity sealed by a workflow origin."""

    card = workflow.packet.primary_test
    if workflow.packet.decision != "test" or card is None:
        raise ValueError("The workflow does not contain one controlled setup action.")
    return {
        "control_key": card.control_key,
        "current_value": format_setup_value(card.control_key, card.current_value),
        "proposed_value": format_setup_value(
            card.control_key,
            card.proposed_value_raw,
        ),
        "instruction": card.exact_change,
        "source_event_ids": list(card.evidence_event_ids),
    }


def validate_p19_workflow_origin(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository | None = None,
    expected_session_id: str | None = None,
    expected_session_run_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Validate the immutable P19 origin before stored workflow policy is consumed.

    Session membership may grow as B and A2 runs are imported, but every run in
    the frozen creation scope must remain in the same saved session. The caller
    still re-derives P19 against the complete current session before publishing
    or mutating the workflow.
    """

    repo = repository or RaceLabRepository()
    binding = workflow.reproduction_snapshot.get("p19_authority_binding")
    if not isinstance(binding, dict):
        raise ValueError("The workflow has no immutable P19 authority origin.")
    session_id = binding.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("The workflow P19 session identity is unavailable.")
    if expected_session_id is not None and session_id != expected_session_id:
        raise ValueError("The workflow P19 session identity does not match this request.")
    session = get_session(session_id, db_path=repo.db_path)
    overview = repo.get_overview(workflow.source_run_id)
    if session is None or overview is None or workflow.source_run_id not in session.run_ids:
        raise ValueError("The workflow P19 run/session identity is unavailable.")
    current_scope = tuple(session.run_ids)
    if len(current_scope) != len(set(current_scope)):
        raise ValueError("The workflow P19 session scope is ambiguous.")
    if expected_session_run_ids is not None and current_scope != tuple(
        expected_session_run_ids
    ):
        raise ValueError("The workflow P19 session scope changed during this request.")
    origin_scope = binding.get("session_run_ids")
    if (
        not isinstance(origin_scope, list)
        or not origin_scope
        or any(not isinstance(run_id, str) or not run_id for run_id in origin_scope)
        or len(origin_scope) != len(set(origin_scope))
        or workflow.source_run_id not in origin_scope
        or any(run_id not in current_scope for run_id in origin_scope)
    ):
        raise ValueError("The frozen workflow P19 session scope is invalid.")
    manifest = read_telemetry_manifest(workflow.source_run_id)
    setup = overview.setup_snapshot
    action = workflow_authority_action_identity(workflow)
    plan_binding = workflow.reproduction_snapshot.get("plan_binding_sha256")
    expected = {
        "schema_version": P19_WORKFLOW_AUTHORITY_BINDING_SCHEMA,
        "workflow_id": workflow.workflow_id,
        "run_id": workflow.source_run_id,
        "session_id": session_id,
        "setup_id": setup.setup_id if setup is not None else None,
        "setup_snapshot_sha256": (
            canonical_json_sha256(setup) if setup is not None else None
        ),
        "source_file_sha256": overview.session.file_hash,
        "compatibility_fingerprint": str(
            manifest.get("compatibility_fingerprint") or ""
        ),
        "compatibility_identity_sha256": canonical_json_sha256(
            manifest.get("compatibility_identity") or {}
        ),
        "plan_binding_sha256": plan_binding,
        "authority_action_sha256": canonical_json_sha256(action),
        "source_event_ids": action["source_event_ids"],
    }
    if any(binding.get(key) != value for key, value in expected.items()):
        raise ValueError("The immutable workflow P19 authority origin changed.")
    for key in (
        "setup_snapshot_sha256",
        "source_file_sha256",
        "compatibility_fingerprint",
        "compatibility_identity_sha256",
        "plan_binding_sha256",
        "authority_action_sha256",
        "reasoning_snapshot_sha256",
    ):
        if re.fullmatch(r"[0-9a-f]{64}", str(binding.get(key) or "")) is None:
            raise ValueError(f"The workflow P19 {key} is unavailable.")
    eligible_lap_ids = binding.get("eligible_lap_ids")
    if (
        not isinstance(eligible_lap_ids, list)
        or not eligible_lap_ids
        or any(not isinstance(lap_id, str) or not lap_id for lap_id in eligible_lap_ids)
        or len(eligible_lap_ids) != len(set(eligible_lap_ids))
    ):
        raise ValueError("The workflow P19 eligible-lap identity is unavailable.")
    return binding


def _workflow_packet_authority_signature(packet: KaizenEvidencePacket) -> dict[str, Any]:
    """Stable authority fields unaffected by post-test response-model learning."""
    payload = packet.model_dump(mode="json")
    for key in (
        "confidence_score",
        "recommendation_score_components",
        "recommendation_score_basis",
        "held_back_alternatives",
        "race_mode_summary",
        "learning_mode_explanation",
    ):
        payload.pop(key, None)
    card = payload.get("primary_test")
    if isinstance(card, dict):
        # A scored result may itself enter response memory and add a personal
        # estimate to these explanatory fields. The create-time binding still
        # seals their exact stored text; current evidence must continue to agree
        # on every executable target, protocol, guardrail, and evidence identity.
        card.pop("hypothesis", None)
        card.pop("expected_mechanism", None)
    return payload


def revalidate_controlled_workflow_packet(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository | None = None,
) -> tuple[KaizenEvidencePacket | None, tuple[str, ...]]:
    """Rebuild a persisted workflow packet before it can be consumed or published.

    The full opportunity and card/mission must match the server planner. This is
    intentionally stricter than checking only the control and target: protocol
    prose, evidence identity, lap window, and action rules are authority-bearing.
    """
    try:
        context = _workflow_decision_context(workflow)
    except ValueError as exc:
        return None, (str(exc),)
    objective = str(context.get("objective") or "setup-development")
    raw_priority = str(context.get("priority") or "").strip()
    try:
        rebuilt = build_server_kaizen_packet(
            workflow.source_run_id,
            workflow.complaint,
            selected_lap=context.get("selected_lap"),
            selected_zone_start_pct=context.get("selected_zone_start_pct"),
            selected_zone_end_pct=context.get("selected_zone_end_pct"),
            selected_zone_label=context.get("selected_zone_label"),
            selected_phase=context.get("selected_phase"),
            objective=objective,
            priority=raw_priority or None,
            repository=repository,
        )
    except Exception:
        return None, (
            "The stored workflow could not be rebuilt from current immutable evidence.",
        )
    stored_binding = workflow.reproduction_snapshot.get("plan_binding_sha256")
    if not isinstance(stored_binding, str) or not stored_binding:
        return None, (
            "The immutable workflow plan binding is unavailable; recreate this workflow from current evidence.",
        )
    if stored_binding != _workflow_plan_binding_hash(
        workflow, workflow.packet, context,
    ):
        return None, (
            "The stored complaint, decision context, or packet no longer matches the immutable workflow plan binding.",
        )
    if workflow.packet.model_dump(mode="json") != rebuilt.model_dump(mode="json"):
        if (
            workflow.status == "scored"
            and stored_binding is not None
            and _workflow_packet_authority_signature(workflow.packet)
            == _workflow_packet_authority_signature(rebuilt)
        ):
            # Scoring can add this same workflow to response memory. Preserve the
            # create-time sealed prose while requiring the fresh planner to agree
            # on every executable and evidence-bearing field.
            return workflow.packet, ()
        return None, (
            "The stored opportunity, evidence, target, or protocol does not match the current server-owned workflow packet.",
        )
    return rebuilt, ()


def revalidate_controlled_test_packet(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository | None = None,
) -> tuple[KaizenEvidencePacket | None, tuple[str, ...]]:
    """Compatibility wrapper for consumers that specifically require a test."""
    rebuilt, blockers = revalidate_controlled_workflow_packet(
        workflow,
        repository=repository,
    )
    if blockers or rebuilt is None:
        return None, blockers
    if rebuilt.decision != "test" or rebuilt.primary_test is None:
        return None, ("The stored workflow does not contain a controlled-test card.",)
    return rebuilt, ()


def _blocked_workflow_packet(
    *additional_blockers: str,
) -> KaizenEvidencePacket:
    blockers = tuple(dict.fromkeys((
        _WORKFLOW_PACKET_BLOCKER,
        *(reason for reason in additional_blockers if reason),
    )))
    mission = MeasurementMission(
        purpose="Recover a workflow whose stored evidence can no longer be trusted.",
        procedure=(
            "Cancel the blocked workflow.",
            "Create a new workflow from the current server-owned run evidence.",
        ),
        required_laps_or_passes=1,
        controlled_variables=("No setup change is authorized.",),
        target_phase="unavailable",
        acceptance_thresholds=("A newly generated server-owned packet passes revalidation.",),
        stop_rule="Do not execute any stored setup action or protocol from this workflow.",
        blockers=blockers,
    )
    return KaizenEvidencePacket(
        decision="measure",
        opportunity=OpportunityEvidence(
            start_pct=0.0,
            end_pct=0.0,
            phase="unavailable",
            observed_time_loss_s=None,
            empirical_noise_s=None,
            alignment_confidence=0.0,
            repeatable=False,
            evidence_links=(),
            source_channels=(),
        ),
        canonical_symptom="unresolved",
        primary_cause_bucket=None,
        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        confidence_score=0.0,
        blockers=blockers,
        supporting_evidence=(),
        contradictory_evidence=(),
        measurement_mission=mission,
        held_back_alternatives=0,
        race_mode_summary="Workflow evidence blocked. No setup action is authorized.",
        learning_mode_explanation=(
            "The workflow identity remains visible so it can be explicitly cancelled, but its "
            "stored evidence and instructions did not pass server revalidation."
        ),
    )


def _exact_repeat_policy_session_scope(
    repository: RaceLabRepository,
    source_run_id: str,
) -> tuple[str, tuple[str, ...]] | None:
    """Resolve one immutable session membership for repeat-policy evaluation.

    A standalone run has no exact-session memory to evaluate. Multiple matching
    sessions, or malformed membership in the matching session, are ambiguous and
    therefore non-authoritative.
    """

    matches: list[tuple[str, tuple[str, ...]]] = []
    for session in list_sessions(include_archived=True, db_path=repository.db_path):
        ordered_run_ids = tuple(session.run_ids)
        if source_run_id not in ordered_run_ids:
            continue
        if (
            any(
                not isinstance(run_id, str)
                or not run_id.strip()
                or run_id != run_id.strip()
                for run_id in ordered_run_ids
            )
            or len(set(ordered_run_ids)) != len(ordered_run_ids)
        ):
            raise ValueError("The repeat-policy session membership is malformed or duplicated.")
        matches.append((session.session_id, ordered_run_ids))
    matches.sort(key=lambda item: item[0])
    if len(matches) > 1:
        raise ValueError(
            "The source run belongs to more than one session, so exact repeat-policy scope is ambiguous."
        )
    return matches[0] if matches else None


def enforce_hypothesis_repeat_policy(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository | None = None,
) -> tuple[KaizenEvidencePacket | None, tuple[str, ...]]:
    """Fail closed when an exact test repeats a valid same-session Undo policy.

    The guard owns no setup recommendation. It only verifies the candidate card's
    exact semantic policy against controlled outcome memory. Measurement missions
    and dependency-injected test repositories remain outside exact-session memory.
    """

    packet = workflow.packet
    if packet.decision != "test" or packet.primary_test is None:
        return packet, ()
    repo = repository or RaceLabRepository()
    if not isinstance(repo, RaceLabRepository):
        return packet, ()
    try:
        scope = _exact_repeat_policy_session_scope(repo, workflow.source_run_id)
        if scope is None:
            return packet, ()
        session_id, ordered_run_ids = scope
        lifecycle = build_hypothesis_lifecycle(
            session_id,
            expected_run_ids=ordered_run_ids,
            db_path=repo.db_path,
        )
        if (
            lifecycle.session_id != session_id
            or lifecycle.ordered_run_ids != ordered_run_ids
            or lifecycle.status == "blocked"
            or any(entry.lifecycle_state == "invalid" for entry in lifecycle.entries)
            or (lifecycle.entries and lifecycle.blocker_reasons)
        ):
            return None, (_REPEAT_POLICY_UNVERIFIABLE_BLOCKER,)
        compatibility_identity = (
            read_telemetry_manifest(workflow.source_run_id).get("compatibility_identity")
            or {}
        )
        candidate_policy = controlled_hypothesis_policy_identity(
            workflow,
            compatibility_identity,
            source_setup=repo.get_setup_snapshot(workflow.source_run_id),
        )
        decision = evaluate_hypothesis_repeat(lifecycle, candidate_policy)
    except Exception:
        return None, (_REPEAT_POLICY_UNVERIFIABLE_BLOCKER,)
    if not decision.allowed:
        return None, (_REPEAT_POLICY_BLOCKED_BLOCKER,)
    return packet, ()


def project_workflow_for_publication(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository | None = None,
) -> ControlledWorkflow:
    """Return a fresh authoritative packet or a non-actionable recovery projection."""
    repo = repository or RaceLabRepository()
    if isinstance(repo, RaceLabRepository):
        try:
            validate_p19_workflow_origin(workflow, repository=repo)
        except (AttributeError, FileNotFoundError, OSError, TypeError, ValueError):
            return withhold_workflow_authority(
                workflow,
                "The workflow has no valid exact-session P19 authority origin.",
            )
    packet, blockers = revalidate_controlled_workflow_packet(
        workflow,
        repository=repo,
    )
    if packet is not None and not blockers:
        fresh = workflow.model_copy(update={"packet": packet})
        try:
            _validate_recorded_stage_bindings(
                fresh,
                packet,
                repo,
                require_complete=fresh.status == "scored",
            )
        except (AttributeError, FileNotFoundError, KeyError, OSError, TypeError, ValueError):
            pass
        else:
            # A scored workflow is immutable audit history, not a new setup
            # authority surface. Its exact tested target/result remains visible
            # only after packet, stage, execution, and quality integrity pass.
            if fresh.status == "scored":
                return fresh
            packet, repeat_blockers = enforce_hypothesis_repeat_policy(
                fresh,
                repository=repo,
            )
            blockers = tuple(dict.fromkeys((*blockers, *repeat_blockers)))
            if packet is not None and not blockers:
                return fresh.model_copy(update={"packet": packet})
    return workflow.model_copy(update={
        "packet": _blocked_workflow_packet(*blockers),
        "stage_eligible_lap_numbers": {},
        "execution": None,
        "reproduction_snapshot": {},
        "quality": None,
        "learning_admitted": None,
    })


def withhold_workflow_authority(
    workflow: ControlledWorkflow,
    *blockers: str,
) -> ControlledWorkflow:
    """Return workflow identity without publishing setup or policy authority."""

    return workflow.model_copy(update={
        "packet": _blocked_workflow_packet(*blockers),
        "stage_eligible_lap_numbers": {},
        "execution": None,
        "reproduction_snapshot": {},
        "quality": None,
        "learning_admitted": None,
    })


def _workflow_scope_run_ids(
    repository: Any,
    run_ids: tuple[str, ...] | list[str] | set[str],
) -> tuple[str, ...]:
    scope = {run_id for run_id in run_ids if isinstance(run_id, str) and run_id}
    if isinstance(repository, RaceLabRepository):
        sessions = list_sessions(include_archived=True, db_path=repository.db_path)
        changed = True
        while changed:
            changed = False
            for session in sessions:
                session_run_ids = set(session.run_ids)
                if scope & session_run_ids and not session_run_ids <= scope:
                    scope.update(session_run_ids)
                    changed = True
    return tuple(sorted(scope))


def workflow_scope_run_ids(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
) -> tuple[str, ...]:
    """Return the exact saved-session scope occupied by one workflow."""

    return _workflow_scope_run_ids(
        repository,
        {workflow.source_run_id, *workflow.stage_run_ids.values()},
    )


def _active_workflow_conflict(
    repository: Any,
    scope_run_ids: tuple[str, ...],
    *,
    exclude_workflow_id: str | None = None,
) -> ControlledWorkflow | None:
    list_workflows = getattr(repository, "list_controlled_workflows", None)
    if not callable(list_workflows):
        return None
    scope = set(scope_run_ids)
    for item in list_workflows(active_only=True):
        if item.workflow_id == exclude_workflow_id:
            continue
        occupied = {item.source_run_id, *item.stage_run_ids.values()}
        if scope & occupied:
            return item
    return None


def _assert_active_workflow_slot(
    repository: Any,
    scope_run_ids: tuple[str, ...],
    *,
    exclude_workflow_id: str | None = None,
) -> None:
    conflict = _active_workflow_conflict(
        repository,
        scope_run_ids,
        exclude_workflow_id=exclude_workflow_id,
    )
    if conflict is not None:
        raise ValueError(
            "Finish or explicitly abandon the active controlled workflow "
            f"{conflict.workflow_id} before continuing another workflow in this session."
        )


def create_workflow(
    run_id: str,
    complaint: str,
    *,
    selected_lap: int | None = None,
    lap_scope: str | None = None,
    window_start_lap: int | None = None,
    window_end_lap: int | None = None,
    representative_lap: int | None = None,
    selected_zone_start_pct: float | None = None,
    selected_zone_end_pct: float | None = None,
    selected_zone_label: str | None = None,
    selected_phase: str | None = None,
    objective: str = "setup-development",
    priority: str | None = None,
    repository: RaceLabRepository | None = None,
    persist: bool = False,
) -> ControlledWorkflow:
    repo = repository or RaceLabRepository()
    (
        lap_scope,
        window_start_lap,
        window_end_lap,
        representative_lap,
    ) = _normalize_workflow_lap_context(
        selected_lap=selected_lap,
        lap_scope=lap_scope,
        window_start_lap=window_start_lap,
        window_end_lap=window_end_lap,
        representative_lap=representative_lap,
    )
    selected_zone = _validated_selected_zone(
        selected_zone_start_pct,
        selected_zone_end_pct,
    )
    if lap_scope == "track_zone" and selected_zone is None:
        raise ValueError("Track-zone workflow scope requires an exact physical window.")
    scoped_run_ids = _workflow_scope_run_ids(repo, (run_id,))
    _assert_active_workflow_slot(repo, scoped_run_ids)
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
        "lap_scope": lap_scope,
        "window_start_lap": window_start_lap,
        "window_end_lap": window_end_lap,
        "representative_lap": representative_lap,
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
        analysis_version="controlled-workflow-aba2-v2",
        reproduction_snapshot={"decision_context": decision_context},
    )
    authorized_packet, repeat_blockers = enforce_hypothesis_repeat_policy(
        workflow,
        repository=repo,
    )
    if authorized_packet is None:
        authorized_packet = _blocked_workflow_packet(*repeat_blockers)
    workflow.packet = authorized_packet
    workflow.reproduction_snapshot["plan_binding_sha256"] = _workflow_plan_binding_hash(
        workflow,
        authorized_packet,
        decision_context,
    )
    if persist:
        persist_workflow_candidate(workflow, repository=repo)
    return workflow


def persist_workflow_candidate(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository | None = None,
) -> ControlledWorkflow:
    """Atomically persist one server-built, still-planned workflow candidate."""

    repo = repository or RaceLabRepository()
    if (
        workflow.status != "planned"
        or workflow.stage_run_ids
        or workflow.stage_eligible_lap_numbers
        or workflow.execution is not None
        or workflow.quality is not None
    ):
        raise ValueError("Only a pristine server-built planned workflow can be persisted.")
    try:
        context = _workflow_decision_context(workflow)
    except ValueError as exc:
        raise ValueError(_WORKFLOW_PACKET_BLOCKER) from exc
    if workflow.reproduction_snapshot.get(
        "plan_binding_sha256"
    ) != _workflow_plan_binding_hash(workflow, workflow.packet, context):
        raise ValueError(_WORKFLOW_PACKET_BLOCKER)
    if isinstance(repo, RaceLabRepository):
        validate_p19_workflow_origin(workflow, repository=repo)
    scoped_run_ids = _workflow_scope_run_ids(repo, (workflow.source_run_id,))
    if isinstance(repo, RaceLabRepository):
        repo.create_controlled_workflow_if_scope_available(workflow, scoped_run_ids)
        record_workflow_plan(workflow, db_path=repo.db_path)
    else:
        _assert_active_workflow_slot(repo, scoped_run_ids)
        repo.save_controlled_workflow(workflow)
    return workflow


def cancel_workflow(
    workflow_id: str,
    *,
    repository: RaceLabRepository | None = None,
) -> ControlledWorkflow:
    """Explicitly abandon an unfinished controlled test without erasing its audit trail."""
    repo = repository or RaceLabRepository()
    workflow = repo.get_controlled_workflow(workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow not found: {workflow_id}")
    if workflow.status == "scored":
        raise ValueError("A scored controlled test is immutable and cannot be abandoned.")
    if workflow.status == "cancelled":
        return workflow
    workflow.status = "cancelled"
    workflow.updated_at = datetime.now(timezone.utc)
    repo.save_controlled_workflow(workflow)
    if isinstance(repo, RaceLabRepository):
        record_workflow_cancellation(workflow, db_path=repo.db_path)
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
    return canonical_json_sha256(payload)


def _stage_binding_hash(
    stage_run_ids: dict[str, str],
    stage_eligible_lap_numbers: dict[str, tuple[int, ...]],
    chronology: dict[str, Any],
    stage_experiment_contexts: dict[str, StageExperimentContext] | None = None,
) -> str:
    payload = {
        "stage_run_ids": stage_run_ids,
        "stage_eligible_lap_numbers": stage_eligible_lap_numbers,
        "recording_chronology": chronology,
        "stage_experiment_contexts": {
            stage: context.model_dump(mode="json")
            for stage, context in (stage_experiment_contexts or {}).items()
        },
    }
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
    if workflow.status in {"scored", "cancelled"}:
        raise ValueError(f"A {workflow.status} workflow cannot accept another stage.")
    if isinstance(repo, RaceLabRepository):
        validate_p19_workflow_origin(workflow, repository=repo)
    fresh_packet, packet_blockers = revalidate_controlled_workflow_packet(
        workflow,
        repository=repo,
    )
    if fresh_packet is None or packet_blockers:
        raise ValueError(_WORKFLOW_PACKET_BLOCKER)
    if fresh_packet.decision != "test" or fresh_packet.primary_test is None:
        raise ValueError("This workflow is a measurement mission and has no A/B/A2 setup stage to attach.")
    fresh_packet, repeat_blockers = enforce_hypothesis_repeat_policy(
        workflow.model_copy(update={"packet": fresh_packet}),
        repository=repo,
    )
    if fresh_packet is None or repeat_blockers:
        raise ValueError(" ".join(repeat_blockers or (_REPEAT_POLICY_UNVERIFIABLE_BLOCKER,)))
    _validate_recorded_stage_bindings(
        workflow.model_copy(update={"packet": fresh_packet}),
        fresh_packet,
        repo,
        require_complete=False,
    )
    scope = _workflow_scope_run_ids(
        repo,
        {workflow.source_run_id, run_id, *workflow.stage_run_ids.values()},
    )
    _assert_active_workflow_slot(repo, scope, exclude_workflow_id=workflow.workflow_id)
    expected = ("A", "B", "A2")[len(workflow.stage_run_ids)] if len(workflow.stage_run_ids) < 3 else None
    if stage != expected:
        raise ValueError(f"Next required stage is {expected or 'none'}; stages must be attached in A/B/A2 order.")
    overview = repo.get_overview(run_id)
    card = fresh_packet.primary_test
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
    cohort_rows_by_lap = _lap_rows(run_id, cohort_laps)
    cohort_ok, cohort_reason = _continuous_stage_cohort(cohort_laps, cohort_rows_by_lap)
    if not cohort_ok:
        raise ValueError(cohort_reason or "The stage cohort is not continuous.")
    cohort_rows = [row for number in cohort_laps for row in cohort_rows_by_lap.get(number, [])]
    expected_applied = planned if stage == "B" else baseline
    experiment_context = _stage_experiment_context(
        cohort_rows, control_key=card.control_key, expected_value=expected_applied,
    )
    if cohort_rows and (context_reason := _experiment_context_blocker(experiment_context)):
        raise ValueError(context_reason)
    stage_ids = {**workflow.stage_run_ids, stage: run_id}
    stage_cohorts = {**workflow.stage_eligible_lap_numbers, stage: measured_laps}
    stage_contexts = {**workflow.stage_experiment_contexts, stage: experiment_context}
    status = {"A": "a_recorded", "B": "b_recorded", "A2": "a2_recorded"}[stage]
    reproduction_snapshot = dict(workflow.reproduction_snapshot)
    chronology = dict(reproduction_snapshot.get("recording_chronology") or {})
    chronology.setdefault("source", _recording_provenance(source_overview, source_manifest))
    chronology[stage] = _recording_provenance(overview, stage_manifest)
    reproduction_snapshot["recording_chronology"] = chronology
    reproduction_snapshot["plan_binding_sha256"] = _workflow_plan_binding_hash(
        workflow,
        fresh_packet,
        _workflow_decision_context(workflow),
    )
    reproduction_snapshot["stage_binding_sha256"] = _stage_binding_hash(
        stage_ids,
        stage_cohorts,
        chronology,
        stage_contexts,
    )
    updated = workflow.model_copy(update={
        "packet": fresh_packet,
        "stage_run_ids": stage_ids,
        "stage_eligible_lap_numbers": stage_cohorts,
        "stage_experiment_contexts": stage_contexts,
        "status": status,
        "reproduction_snapshot": reproduction_snapshot,
        "updated_at": datetime.now(timezone.utc),
    })
    if isinstance(repo, RaceLabRepository):
        repo.save_controlled_workflow_if_scope_exclusive(updated, scope)
    else:
        repo.save_controlled_workflow(updated)
    if isinstance(repo, RaceLabRepository):
        record_workflow_stage(updated, stage, db_path=repo.db_path)
    return updated


def _validate_recorded_stage_bindings(
    workflow: ControlledWorkflow,
    packet: KaizenEvidencePacket,
    repository: Any,
    *,
    require_complete: bool,
) -> None:
    """Recompute stage identity, chronology, setup isolation, and lap cohorts."""
    card = packet.primary_test
    if packet.decision != "test" or card is None:
        if workflow.stage_run_ids or workflow.stage_eligible_lap_numbers:
            raise ValueError("A measurement workflow cannot contain A/B/A2 stage bindings.")
        if workflow.status not in {"planned", "cancelled"}:
            raise ValueError("A measurement workflow has an impossible controlled-test status.")
        return

    stage_order = ("A", "B", "A2")
    stage_count = len(workflow.stage_run_ids)
    if stage_count > len(stage_order) or set(workflow.stage_run_ids) != set(stage_order[:stage_count]):
        raise ValueError("Stored stage run identities are not an exact A/B/A2 prefix.")
    if set(workflow.stage_eligible_lap_numbers) != set(workflow.stage_run_ids):
        raise ValueError("Stored stage lap cohorts do not exactly match the recorded stage identities.")
    expected_status = {
        0: "planned",
        1: "a_recorded",
        2: "b_recorded",
        3: "a2_recorded",
    }[stage_count]
    valid_statuses = {expected_status, "cancelled"}
    if stage_count == 3:
        valid_statuses.add("scored")
    if workflow.status not in valid_statuses:
        raise ValueError("Workflow status does not match its exact recorded A/B/A2 stage prefix.")
    if require_complete and (stage_count != 3 or workflow.status not in {"a2_recorded", "scored"}):
        raise ValueError("A, B, and A2 must all be server-verified before authoritative use.")
    if stage_count == 0:
        return
    stored_binding = workflow.reproduction_snapshot.get("stage_binding_sha256")
    if not isinstance(stored_binding, str) or not stored_binding:
        raise ValueError(
            "The immutable stage binding is unavailable; cancel and recreate this workflow."
        )

    stage_ids = [workflow.stage_run_ids[stage] for stage in stage_order[:stage_count]]
    if any(not isinstance(run_id, str) or not run_id.strip() for run_id in stage_ids):
        raise ValueError("Stored stage run identities are malformed.")
    if len(stage_ids) != len(set(stage_ids)):
        # A may use the source run, but no two named stages may reuse one run.
        raise ValueError("A, B, and A2 must bind to distinct named stage runs.")

    source_overview = repository.get_overview(workflow.source_run_id)
    source_setup = repository.get_setup_snapshot(workflow.source_run_id)
    if source_overview is None or source_setup is None:
        raise ValueError("The workflow source run or complete baseline setup is unavailable.")
    if source_overview.run_id != workflow.source_run_id or source_setup.run_id != workflow.source_run_id:
        raise ValueError("The workflow source evidence was relabelled across run identities.")
    if source_overview.session.setup_passed_tech is not True:
        raise ValueError("The workflow source setup is not recorded as passing tech inspection.")
    source_manifest = read_telemetry_manifest(workflow.source_run_id)
    identity_fields = (
        "driver_user_id", "car_id", "car_path", "car_version", "track_id",
        "track_configuration_name", "track_version", "iracing_build_version", "session_type",
    )
    source_identity = source_manifest.get("compatibility_identity") or {}
    if any(source_identity.get(key) is None for key in identity_fields):
        raise ValueError("The source compatibility identity is incomplete.")
    previous_overview = source_overview
    previous_manifest = source_manifest
    chronology = workflow.reproduction_snapshot.get("recording_chronology") or {}
    if not isinstance(chronology, dict):
        raise ValueError("Stored recording chronology is malformed.")
    expected_chronology: dict[str, Any] = {
        "source": _recording_provenance(source_overview, source_manifest),
    }
    expected_reproduction_stages: dict[str, dict[str, Any]] = {}
    expected_stage_contexts: dict[str, StageExperimentContext] = {}

    baseline_setup = source_setup
    for stage in stage_order[:stage_count]:
        run_id = workflow.stage_run_ids[stage]
        overview = repository.get_overview(run_id)
        setup = repository.get_setup_snapshot(run_id)
        if overview is None or setup is None:
            raise ValueError(f"Stage {stage} run or complete setup snapshot is unavailable.")
        if overview.run_id != run_id or setup.run_id != run_id:
            raise ValueError(f"Stage {stage} evidence was relabelled across run identities.")
        if overview.session.setup_passed_tech is not True:
            raise ValueError(f"Stage {stage} setup is not recorded as passing tech inspection.")
        manifest = read_telemetry_manifest(run_id)
        identity = manifest.get("compatibility_identity") or {}
        if any(identity.get(key) is None for key in identity_fields) or any(
            identity.get(key) != source_identity.get(key) for key in identity_fields
        ):
            raise ValueError(f"Stage {stage} compatibility identity is incomplete or mismatched.")
        previous_interval = _recording_interval(previous_overview, previous_manifest)
        current_interval = _recording_interval(overview, manifest)
        if previous_interval is None or current_interval is None or not _recording_order_is_valid(
            stage=stage,
            run_id=run_id,
            source_run_id=workflow.source_run_id,
            current_interval=current_interval,
            previous_interval=previous_interval,
            workflow_created_epoch_s=workflow.created_at.timestamp(),
        ):
            raise ValueError(f"Stage {stage} recording chronology is missing, overlapping, or out of order.")
        expected_chronology[stage] = _recording_provenance(overview, manifest)

        stage_plan = next(item for item in card.stages if item.stage == stage)
        ordered_eligible = sorted(eligible_laps(overview.laps), key=lambda item: item.lap_number)
        required_total = stage_plan.warmup_laps + stage_plan.required_flying_laps
        if len(ordered_eligible) < required_total:
            raise ValueError(f"Stage {stage} no longer contains its full warm-up and measured cohort.")
        expected_measured = tuple(
            lap.lap_number
            for lap in ordered_eligible[
                stage_plan.warmup_laps:stage_plan.warmup_laps + stage_plan.required_flying_laps
            ]
        )
        if workflow.stage_eligible_lap_numbers[stage] != expected_measured:
            raise ValueError(
                f"Stage {stage} stored measured laps are not the deterministic post-warmup cohort; "
                "cherry-picked eligible laps are rejected."
            )
        cohort_laps = [lap.lap_number for lap in ordered_eligible[:required_total]]
        cohort_rows_by_lap = _lap_rows(run_id, cohort_laps)
        cohort_ok, cohort_reason = _continuous_stage_cohort(cohort_laps, cohort_rows_by_lap)
        if not cohort_ok:
            raise ValueError(
                cohort_reason
                or f"Stage {stage} warm-up and measured cohort is no longer continuous."
            )

        changes = diff_setups(baseline_setup, setup)
        if (
            not setup_controls_comparable(baseline_setup, setup)
            or unmapped_setup_change_paths(baseline_setup, setup, changes)
        ):
            raise ValueError(f"Stage {stage} setup isolation is incomplete or contains unmapped changes.")
        allowed = 1 if stage == "B" else 0
        if len(changes) != allowed or (
            stage == "B" and (not changes or changes[0].setup_key != card.control_key)
        ):
            raise ValueError(f"Stage {stage} does not match the one-change immutable setup plan.")
        observed = setup_control_value(setup, card.control_key)
        expected_value = _planned_numeric_value(card) if stage == "B" else card.current_value
        if expected_value is None or not setup_control_values_equal(
            card.control_key,
            observed,
            expected_value,
        ):
            raise ValueError(f"Stage {stage} setup value does not match the immutable test card.")
        cohort_rows = [row for number in cohort_laps for row in cohort_rows_by_lap.get(number, [])]
        expected_context = _stage_experiment_context(
            cohort_rows, control_key=card.control_key, expected_value=expected_value,
        )
        expected_stage_contexts[stage] = expected_context

        setup_payload = setup.model_dump(mode="json") if hasattr(setup, "model_dump") else setup
        expected_reproduction_stages[stage] = {
            "run_id": run_id,
            "source_file_sha256": overview.session.file_hash,
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "cache_version": manifest.get("cache_version"),
            "compatibility_identity": identity,
            "setup_fingerprint": _setup_snapshot_hash(setup_payload),
            "setup_values": setup_payload,
            "eligible_lap_numbers": list(expected_measured),
            "experiment_context": expected_context.model_dump(mode="json"),
        }

        previous_overview = overview
        previous_manifest = manifest

    for stage, expected_context in expected_stage_contexts.items():
        if context_reason := _experiment_context_blocker(expected_context):
            raise ValueError(f"Stage {stage} experiment context is invalid: {context_reason}")
        if workflow.stage_experiment_contexts.get(stage) != expected_context:
            raise ValueError(f"Stage {stage} vehicle-condition or applied-control binding changed.")

    if set(chronology) != set(expected_chronology) or chronology != expected_chronology:
        raise ValueError("Stored recording chronology does not exactly match the bound source and stage runs.")
    expected_binding = _stage_binding_hash(
        workflow.stage_run_ids,
        workflow.stage_eligible_lap_numbers,
        chronology,
        workflow.stage_experiment_contexts,
    )
    if stored_binding != expected_binding:
        raise ValueError("Stored stage run, cohort, or chronology bindings failed integrity validation.")
    if workflow.status == "scored":
        if workflow.reproduction_snapshot.get("stages") != expected_reproduction_stages:
            raise ValueError(
                "The scored certificate stage identities, setups, or cohorts do not match current bound evidence."
            )
        execution = workflow.execution
        quality = workflow.quality
        if execution is None or quality is None:
            raise ValueError("A scored workflow requires its immutable execution and quality certificate.")
        counts = {
            stage: len(workflow.stage_eligible_lap_numbers[stage])
            for stage in stage_order
        }
        if (
            execution.eligible_laps_a != counts["A"]
            or execution.eligible_laps_b != counts["B"]
            or execution.eligible_laps_a2 != counts["A2"]
            or execution.control_key != card.control_key
            or not setup_control_values_equal(
                card.control_key,
                execution.planned_b_value,
                _planned_numeric_value(card),
            )
            or quality != score_test_execution(execution)
        ):
            raise ValueError("The scored execution or quality certificate failed integrity validation.")


def validate_workflow_for_authoritative_use(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository | None = None,
    require_complete_stages: bool = False,
) -> ControlledWorkflow:
    """Return a fresh workflow only after all authority-bearing bindings pass."""
    repo = repository or RaceLabRepository()
    if isinstance(repo, RaceLabRepository):
        validate_p19_workflow_origin(workflow, repository=repo)
    packet, blockers = revalidate_controlled_workflow_packet(workflow, repository=repo)
    if packet is None or blockers:
        raise ValueError(_WORKFLOW_PACKET_BLOCKER)
    fresh = workflow.model_copy(update={"packet": packet})
    _validate_recorded_stage_bindings(
        fresh,
        packet,
        repo,
        require_complete=require_complete_stages,
    )
    if fresh.status != "scored":
        packet, repeat_blockers = enforce_hypothesis_repeat_policy(
            fresh,
            repository=repo,
        )
        if packet is None or repeat_blockers:
            raise ValueError(" ".join(repeat_blockers or (_REPEAT_POLICY_UNVERIFIABLE_BLOCKER,)))
        fresh = fresh.model_copy(update={"packet": packet})
    return fresh


def score_workflow(
    workflow_id: str,
    *,
    repository: RaceLabRepository | None = None,
    persist: bool = True,
) -> ControlledWorkflow:
    repo = repository or RaceLabRepository()
    workflow = repo.get_controlled_workflow(workflow_id)
    if workflow is None or set(workflow.stage_run_ids) != {"A", "B", "A2"}:
        raise ValueError("A, B, and A2 must all be server-verified before scoring.")
    if workflow.status == "scored":
        raise ValueError("A scored controlled workflow is immutable; create a new workflow for another test.")
    if workflow.status == "cancelled":
        raise ValueError("A cancelled controlled workflow cannot be scored.")
    scope = _workflow_scope_run_ids(
        repo,
        {workflow.source_run_id, *workflow.stage_run_ids.values()},
    )
    _assert_active_workflow_slot(repo, scope, exclude_workflow_id=workflow.workflow_id)
    workflow = validate_workflow_for_authoritative_use(
        workflow,
        repository=repo,
        require_complete_stages=True,
    )
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
    origin_threshold = max(0.02, noise or 0.05)
    time_origins: list[tuple[float, str]] = []
    carry_effects: list[float] = []
    for results in comparison_results.values():
        for aligned in results:
            cumulative = getattr(aligned, "cumulative_delta_s", ())
            origin_index = next((
                index for index, value in enumerate(cumulative)
                if value is not None and abs(value) > origin_threshold
            ), None)
            if origin_index is not None:
                phases = getattr(aligned, "phase_by_position", ())
                grid = getattr(aligned, "grid_pct", ())
                if origin_index < len(phases) and origin_index < len(grid):
                    phase = phases[origin_index]
                    if phase is not None:
                        time_origins.append((grid[origin_index], phase))
            carry = getattr(aligned, "phase_attribution", {}).get("following_straight_carry_delta_s")
            if carry is not None:
                carry_effects.append(carry)
    time_origins.sort(key=lambda item: (item[0], item[1]))
    representative_origin = time_origins[(len(time_origins) - 1) // 2] if time_origins else None
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
        time_origin_phase=representative_origin[1] if representative_origin else None,
        time_origin_pct=representative_origin[0] if representative_origin else None,
        downstream_carry_effect_s=median(carry_effects) if carry_effects else None,
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
    if not result.protocol_valid or result.verdict == "invalid":
        execution = execution.model_copy(
            update={
                "time_origin_phase": None,
                "time_origin_pct": None,
                "downstream_carry_effect_s": None,
            }
        )
    observed_effect = median([*target_effects["AB"], *target_effects["A2B"]])
    learning_admitted: bool | None = None
    # Transient scoring is used by the API to derive the final P19 outcome
    # binding before one atomic workflow/P33 commit.  It must be a pure
    # computation: legacy setup-response admission may write SQLite and is
    # therefore retained only for callers that explicitly request persistence.
    # P19/P26 controlled history is reconstructed from the final workflow's
    # exact controlled outcome, not from this auxiliary observation table.
    if persist and result.controlled_effect_eligible and result.verdict in {"keep", "undo"}:
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
        stored_context = workflow.stage_experiment_contexts.get(stage)
        if stored_context is None:
            expected_value = _planned_numeric_value(card) if stage == "B" else card.current_value
            stored_context = _stage_experiment_context(
                [row for lap in lap_rows[stage] for row in lap],
                control_key=card.control_key,
                expected_value=expected_value,
            )
        reproduction_stages[stage] = {
            "run_id": workflow.stage_run_ids[stage],
            "source_file_sha256": overviews[stage].session.file_hash,
            "schema_fingerprint": manifest.get("schema_fingerprint"),
            "cache_version": manifest.get("cache_version"),
            "compatibility_identity": manifest.get("compatibility_identity") or {},
            "setup_fingerprint": _setup_snapshot_hash(setup_payload),
            "setup_values": setup_payload,
            "eligible_lap_numbers": list(stage_eligible_lap_numbers[stage]),
            "experiment_context": stored_context.model_dump(mode="json"),
        }
    reproduction_snapshot = {
        "analysis_version": workflow.analysis_version,
        "analysis_code_and_config_sha256": _analysis_code_hash(workflow.packet),
        "plan_binding_sha256": _workflow_plan_binding_hash(
            workflow,
            workflow.packet,
            _workflow_decision_context(workflow),
        ),
        "stage_binding_sha256": _stage_binding_hash(
            workflow.stage_run_ids,
            stage_eligible_lap_numbers,
            workflow.reproduction_snapshot.get("recording_chronology", {}),
            workflow.stage_experiment_contexts,
        ),
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
        "p19_authority_binding": workflow.reproduction_snapshot.get(
            "p19_authority_binding"
        ),
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
    if persist:
        if isinstance(repo, RaceLabRepository):
            repo.save_controlled_workflow_if_scope_exclusive(updated, scope)
        else:
            repo.save_controlled_workflow(updated)
        record_scored_workflow_side_effects(updated, repository=repo)
    return updated


def record_scored_workflow_side_effects(
    workflow: ControlledWorkflow,
    *,
    repository: RaceLabRepository,
) -> None:
    """Persist non-authoritative presentation/evaluation facts after score commit."""

    if not isinstance(repository, RaceLabRepository):
        return
    if workflow.status != "scored" or workflow.quality is None:
        raise ValueError("Only a fully scored workflow may emit outcome side effects.")
    try:
        record_workflow_outcome(workflow, db_path=repository.db_path)
    except Exception as exc:
        # Presentation memory is downstream of the canonical score/P33 commit.
        # It may be repaired independently and cannot roll back or mask truth.
        _log.warning(
            "Engineering presentation-memory attachment failed for workflow %s: %s",
            workflow.workflow_id,
            exc,
        )
    try:
        from racelab_engine.evaluation.prospective import (
            attach_matching_outcome_after_score,
        )

        attach_matching_outcome_after_score(
            workflow.workflow_id,
            workflow.source_run_id,
            db_path=repository.db_path,
        )
    except Exception as exc:
        # P22 shadow grading cannot weaken or roll back the canonical P19
        # score. The frozen prediction remains visibly unscored for recovery.
        _log.warning(
            "Prospective outcome attachment failed closed for workflow %s: %s",
            workflow.workflow_id,
            exc,
        )


__all__ = [
    "P19_WORKFLOW_AUTHORITY_BINDING_SCHEMA",
    "attach_stage",
    "build_server_kaizen_packet",
    "cancel_workflow",
    "create_workflow",
    "enforce_hypothesis_repeat_policy",
    "project_workflow_for_publication",
    "record_scored_workflow_side_effects",
    "persist_workflow_candidate",
    "revalidate_controlled_test_packet",
    "revalidate_controlled_workflow_packet",
    "score_workflow",
    "validate_p19_workflow_origin",
    "validate_workflow_for_authoritative_use",
    "workflow_authority_action_identity",
    "workflow_scope_run_ids",
    "withhold_workflow_authority",
]
