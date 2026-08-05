from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any, Iterable

from racelab_engine.analysis.shock_reader_schema import (
    Confidence,
    Pattern,
    SettingConfidence,
    ShockCornerRead,
    ShockReaderResponse,
    ShockRecommendation,
    ShockSettingRecommendation,
    ShockSetting,
)
from racelab_engine.analysis.lap_eligibility import eligible_laps, find_lap, lap_ineligibility_reasons
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import default_data_dir, parquet_path


SHOCK_CORNERS = ("LF", "RF", "LR", "RR")
DEFAULT_BOUNDARY_IN_S = 1.0
NEXT_GEN_BOUNDARY_IN_S = 1.5
DEFAULT_BIN_WIDTH_IN_S = 0.5
MIN_SAMPLE_COUNT = 64
MIN_CONTINUOUS_DURATION_S = 0.75
MIN_FINITE_SHOCK_COVERAGE = 0.80
CENTER_DEADBAND_IN_S = 0.05
MAX_SLOPE_ZONE_WIDTH_PCT = 20.0

VELOCITY_CHANNELS = {
    "LF": "lf_shock_vel_in_s",
    "RF": "rf_shock_vel_in_s",
    "LR": "lr_shock_vel_in_s",
    "RR": "rr_shock_vel_in_s",
}
DEFLECTION_DELTA_CHANNELS = {
    "LF": ("lf_shock_defl_delta_in", "lf_shock_defl_in"),
    "RF": ("rf_shock_defl_delta_in", "rf_shock_defl_in"),
    "LR": ("lr_shock_defl_delta_in", "lr_shock_defl_in"),
    "RR": ("rr_shock_defl_delta_in", "rr_shock_defl_in"),
}
ACTIVITY_CHANNELS = {
    "LF": "lf_shock_activity_index",
    "RF": "rf_shock_activity_index",
    "LR": "lr_shock_activity_index",
    "RR": "rr_shock_activity_index",
}

CONTEXT_CHANNELS = [
    "lap",
    "session_time",
    "lap_dist_pct",
    "speed_mph",
    "throttle_pct",
    "brake_pct",
    "abs_steering_deg",
    "steering_deg",
    "cfs_ride_height_in",
    "cfs_ride_height_mm",
    "front_center_rh_in",
    "rear_center_rh_in",
    "rear_scrape_margin_mm",
    "rear_scrape_risk_score",
    "rear_platform_contact_risk",
    "platform_contact",
    "platform_compression_index",
    "shock_activity_index",
    "damper_energy_proxy",
]

DISPLAY_SETTING: dict[ShockSetting, str] = {
    "ls_compression": "LS bump",
    "hs_compression": "HS bump",
    "hs_compression_slope": "compression slope",
    "ls_rebound": "LS rebound",
    "hs_rebound": "HS rebound",
    "hs_rebound_slope": "rebound slope",
    "compression_slope": "compression slope",
    "rebound_slope": "rebound slope",
}

SETUP_KEY_CANDIDATES: dict[ShockSetting, tuple[str, ...]] = {
    "ls_compression": ("ls_compression", "ls_comp"),
    "hs_compression": ("hs_compression", "hs_comp"),
    "hs_compression_slope": ("hs_compression_slope", "compression_slope", "hs_comp_slope", "hs_compression_slope"),
    "ls_rebound": ("ls_rebound", "ls_reb"),
    "hs_rebound": ("hs_rebound", "hs_reb"),
    "hs_rebound_slope": ("hs_rebound_slope", "rebound_slope", "hs_reb_slope", "hs_rebound_slope"),
    "compression_slope": ("compression_slope", "hs_comp_slope", "hs_compression_slope"),
    "rebound_slope": ("rebound_slope", "hs_reb_slope", "hs_rebound_slope"),
}

INLINE_SETTINGS: tuple[tuple[str, str, ShockSetting], ...] = (
    ("ls_compression", "LS Comp", "ls_compression"),
    ("hs_compression", "HS Comp", "hs_compression"),
    ("hs_compression_slope", "HS-S Comp", "hs_compression_slope"),
    ("ls_rebound", "LS Reb", "ls_rebound"),
    ("hs_rebound", "HS Reb", "hs_rebound"),
    ("hs_rebound_slope", "HS-S Reb", "hs_rebound_slope"),
)


def build_shock_reader_response(
    run_id: str,
    *,
    lap: int | None = None,
    lap_window: tuple[int, int] | None = None,
    phase: str | None = None,
    zone_start_pct: float | None = None,
    zone_end_pct: float | None = None,
    boundary_in_s: float = DEFAULT_BOUNDARY_IN_S,
    boundary_basis: str = "Descriptive 1.0 in/s boundary; no verified car-specific slope transition is available.",
    slope_boundary_verified: bool = False,
    expected_sample_rate_hz: float = 60.0,
    include_debug: bool = False,
    setup_snapshot: SetupSnapshot | None = None,
    lap_summaries: list[LapSummary] | None = None,
    data_dir: str | Path | None = None,
) -> ShockReaderResponse:
    warnings: list[str] = []
    zone = _validated_zone(zone_start_pct, zone_end_pct)
    tuning_blocked_reason, eligible_lap_numbers = _shock_tuning_eligibility(
        lap_summaries,
        lap=lap,
        lap_window=lap_window,
    )
    boundary = boundary_in_s if math.isfinite(boundary_in_s) and boundary_in_s > 0 else DEFAULT_BOUNDARY_IN_S
    data = _read_shock_reader_columns(
        run_id,
        lap=lap,
        lap_window=lap_window,
        phase=phase,
        zone=zone,
        data_dir=data_dir,
        warnings=warnings,
        eligible_lap_numbers=eligible_lap_numbers,
    )
    if not data:
        return ShockReaderResponse(
            run_id=run_id,
            lap_window=_format_lap_window(lap=lap, lap_window=lap_window),
            phase=phase,
            zone_start_pct=zone[0] if zone is not None else None,
            zone_end_pct=zone[1] if zone is not None else None,
            boundary_in_s=boundary,
            boundary_basis=boundary_basis,
            slope_actions_available=False,
            bin_width_in_s=DEFAULT_BIN_WIDTH_IN_S,
            setup_snapshot_available=setup_snapshot is not None,
            corners=[],
            recommendations=[],
            warnings=[*warnings, "Shock telemetry unavailable for this run/window."],
            evidence_state="unavailable",
            blocker_reasons=["Shock telemetry unavailable for this run/window."],
        )

    corners = [
        compute_corner_read(corner, data.get(VELOCITY_CHANNELS[corner], []), data, boundary)
        for corner in SHOCK_CORNERS
    ]
    corners = [
        _qualify_corner_shape(corner, data, boundary, expected_sample_rate_hz)
        for corner in corners
    ]
    context = _build_context(
        data,
        phase=phase,
        selected_zone=zone is not None,
        slope_boundary_verified=slope_boundary_verified,
    )
    corners = _apply_context_patterns(corners, context)
    corners = _attach_setting_recommendations(corners, context, setup_snapshot)
    corners = _enforce_one_change(corners)
    recommendations = _build_recommendations(
        corners,
        context,
        setup_snapshot=setup_snapshot,
        include_debug=include_debug,
    )
    if tuning_blocked_reason is not None:
        corners = _suppress_ineligible_shock_actions(corners, tuning_blocked_reason)
        recommendations = []
        warnings.append(tuning_blocked_reason)
    if all(corner.pattern == "insufficient_evidence" for corner in corners):
        warnings.append("Shock velocity channels are missing or too sparse for guarded recommendations.")

    return ShockReaderResponse(
        run_id=run_id,
        lap_window=_format_lap_window(lap=lap, lap_window=lap_window),
        phase=phase,
        zone_start_pct=zone[0] if zone is not None else None,
        zone_end_pct=zone[1] if zone is not None else None,
        boundary_in_s=boundary,
        boundary_basis=boundary_basis,
        slope_actions_available=any(
            recommendation.setting in {"hs_compression_slope", "hs_rebound_slope"}
            and recommendation.direction in {"add", "subtract"}
            for corner in corners
            for recommendation in corner.setting_recommendations
        ),
        bin_width_in_s=DEFAULT_BIN_WIDTH_IN_S,
        setup_snapshot_available=setup_snapshot is not None,
        corners=corners,
        recommendations=recommendations,
        warnings=warnings,
        evidence_state=(
            "blocked_by_context"
            if tuning_blocked_reason is not None
            else "unavailable"
            if all(corner.pattern == "insufficient_evidence" for corner in corners)
            else "needs_confirmation"
        ),
        source_channels=[
            channel for channel in VELOCITY_CHANNELS.values() if data.get(channel)
        ],
        blocker_reasons=(
            [tuning_blocked_reason]
            if tuning_blocked_reason is not None
            else ["Shock velocity channels are missing or too sparse."]
            if all(corner.pattern == "insufficient_evidence" for corner in corners)
            else []
        ),
    )


def _shock_tuning_eligibility(
    lap_summaries: list[LapSummary] | None,
    *,
    lap: int | None,
    lap_window: tuple[int, int] | None,
) -> tuple[str | None, set[int] | None]:
    """Return a tuning block and safe all-run filter without hiding observations."""
    if lap_summaries is None:
        return (
            "Canonical lap eligibility is unavailable for shock tuning. Measured shock observations "
            "are retained, but exact setting actions are suppressed.",
            None,
        )

    eligible_numbers = {summary.lap_number for summary in eligible_laps(lap_summaries)}
    if lap is not None:
        summary = find_lap(lap_summaries, lap)
        reasons = ["Lap summary unavailable"] if summary is None else lap_ineligibility_reasons(summary)
        if summary is None or lap not in eligible_numbers:
            detail = ", ".join(reasons) or "Lap did not pass the setup-evidence gate"
            return (
                f"Lap {lap} is not eligible for shock tuning ({detail}). "
                "Measured shock observations are retained, but exact setting actions are suppressed.",
                None,
            )
        return None, None

    if lap_window is not None:
        start, end = lap_window
        selected = [summary for summary in lap_summaries if start <= summary.lap_number <= end]
        blocked = [summary for summary in selected if summary.lap_number not in eligible_numbers]
        if not selected or blocked:
            detail = "no summarized laps in the selected window" if not selected else "; ".join(
                f"lap {summary.lap_number}: {', '.join(lap_ineligibility_reasons(summary))}"
                for summary in blocked
            )
            return (
                f"Lap window {start}-{end} is not eligible for shock tuning ({detail}). "
                "Measured shock observations are retained, but exact setting actions are suppressed.",
                None,
            )
        return None, None

    if not eligible_numbers:
        return (
            "No eligible flying laps are available for shock tuning. Measured shock observations "
            "are retained, but exact setting actions are suppressed.",
            None,
        )
    return None, eligible_numbers


def _suppress_ineligible_shock_actions(
    corners: list[ShockCornerRead],
    reason: str,
) -> list[ShockCornerRead]:
    return [
        corner.model_copy(
            update={
                "setting_recommendations": [
                    recommendation.model_copy(
                        update={
                            "delta": None,
                            "suggested_value": None,
                            "direction": "needs_more_evidence",
                            "magnitude": "hold",
                            "confidence": "needs_more_evidence",
                            "reason_short": "Observation only; this lap selection cannot support a tuning action.",
                            "blocked_reason": reason,
                            "evidence_state": "blocked_by_context",
                            "blocker_reasons": [reason],
                        }
                    )
                    for recommendation in corner.setting_recommendations
                ]
            }
        )
        for corner in corners
    ]


def compute_corner_read(
    corner: str,
    velocities: Iterable[Any],
    data: dict[str, list[Any]] | None = None,
    boundary_in_s: float = DEFAULT_BOUNDARY_IN_S,
) -> ShockCornerRead:
    values = [_finite(value) for value in velocities]
    samples = [value for value in values if value is not None]
    if len(samples) < MIN_SAMPLE_COUNT:
        return ShockCornerRead(
            corner=corner,  # type: ignore[arg-type]
            sample_count=len(samples),
            rebound_hi_pct=0.0,
            rebound_lo_pct=0.0,
            bump_lo_pct=0.0,
            bump_hi_pct=0.0,
            avg_rebound_in_s=None,
            avg_bump_in_s=None,
            center_pct=0.0,
            rms_in_s=None,
            activity_index=None,
            deflection_delta_range_in=None,
            pattern="insufficient_evidence",
            confidence="low",
        )

    boundary = max(0.01, abs(boundary_in_s))
    deadband = min(CENTER_DEADBAND_IN_S, boundary / 2.0)
    rebound_hi = [value for value in samples if value <= -boundary]
    rebound_lo = [value for value in samples if -boundary < value < -deadband]
    bump_lo = [value for value in samples if deadband < value < boundary]
    bump_hi = [value for value in samples if value >= boundary]
    moving_total = len(rebound_hi) + len(rebound_lo) + len(bump_lo) + len(bump_hi)
    total = len(samples)
    read = {
        "rebound_hi_pct": _pct(len(rebound_hi), moving_total),
        "rebound_lo_pct": _pct(len(rebound_lo), moving_total),
        "bump_lo_pct": _pct(len(bump_lo), moving_total),
        "bump_hi_pct": _pct(len(bump_hi), moving_total),
    }
    rms = math.sqrt(sum(value * value for value in samples) / total)
    activity = _mean(_numeric_series(data, ACTIVITY_CHANNELS[corner])) if data else None
    if activity is None:
        activity = rms
    deflection_range = _deflection_range(data, corner) if data else None
    pattern, confidence = classify_corner_pattern(
        read["rebound_hi_pct"],
        read["rebound_lo_pct"],
        read["bump_lo_pct"],
        read["bump_hi_pct"],
        rms,
        activity,
    )
    return ShockCornerRead(
        corner=corner,  # type: ignore[arg-type]
        sample_count=total,
        rebound_hi_pct=read["rebound_hi_pct"],
        rebound_lo_pct=read["rebound_lo_pct"],
        bump_lo_pct=read["bump_lo_pct"],
        bump_hi_pct=read["bump_hi_pct"],
        avg_rebound_in_s=_mean(abs(value) for value in samples if value < 0),
        avg_bump_in_s=_mean(value for value in samples if value > 0),
        center_pct=_pct(sum(abs(value) <= deadband for value in samples), total),
        rms_in_s=rms,
        activity_index=activity,
        deflection_delta_range_in=deflection_range,
        pattern=pattern,
        confidence=confidence,
    )


def _high_speed_signature(corner: ShockCornerRead) -> str:
    high_delta = corner.bump_hi_pct - corner.rebound_hi_pct
    high_total = corner.bump_hi_pct + corner.rebound_hi_pct
    if high_total >= 38 and corner.bump_hi_pct >= 10 and corner.rebound_hi_pct >= 10:
        return "both"
    if high_delta >= 12 and corner.bump_hi_pct >= 18:
        return "compression"
    if high_delta <= -12 and corner.rebound_hi_pct >= 18:
        return "rebound"
    return "neutral"


def _qualify_corner_shape(
    corner: ShockCornerRead,
    data: dict[str, list[Any]],
    boundary_in_s: float,
    expected_sample_rate_hz: float,
) -> ShockCornerRead:
    """Require lap repetition and threshold stability before changing curve shape."""
    velocities = data.get(VELOCITY_CHANNELS[corner.corner], [])
    lap_values = data.get("lap", [])
    times = data.get("session_time", [])
    grouped: dict[int, list[tuple[Any, Any]]] = {}
    for index, (lap_value, velocity) in enumerate(zip(lap_values, velocities)):
        numeric_lap = _finite(lap_value)
        if numeric_lap is not None and numeric_lap.is_integer():
            time = times[index] if index < len(times) else None
            grouped.setdefault(int(numeric_lap), []).append((time, velocity))
    qualified_numbers = [
        number
        for number in sorted(grouped)
        if _continuous_shock_slice(grouped[number], expected_sample_rate_hz)
    ]
    per_lap_reads = [
        compute_corner_read(
            corner.corner,
            [velocity for _, velocity in grouped[number]],
            boundary_in_s=boundary_in_s,
        )
        for number in qualified_numbers
    ]
    lap_numbers = qualified_numbers
    signatures = [_high_speed_signature(read) for read in per_lap_reads]
    compression_repeatable = len(signatures) >= 2 and all(
        signature in {"compression", "both"} for signature in signatures
    )
    rebound_repeatable = len(signatures) >= 2 and all(
        signature in {"rebound", "both"} for signature in signatures
    )

    sensitivity_patterns = []
    for number in qualified_numbers:
        lap_velocities = [velocity for _, velocity in grouped[number]]
        for multiplier in (0.75, 1.0, 1.25):
            read = compute_corner_read(
                corner.corner,
                lap_velocities,
                boundary_in_s=max(0.01, boundary_in_s * multiplier),
            )
            sensitivity_patterns.append(
                f"L{number}@{multiplier:.2f}:{_high_speed_signature(read)}"
            )
    compression_stable = all(
        item.rsplit(":", 1)[-1] in {"compression", "both"}
        for item in sensitivity_patterns
    ) and len(qualified_numbers) >= 2
    rebound_stable = all(
        item.rsplit(":", 1)[-1] in {"rebound", "both"}
        for item in sensitivity_patterns
    ) and len(qualified_numbers) >= 2
    return corner.model_copy(update={
        "source_lap_numbers": lap_numbers,
        "repeatability_lap_count": len(per_lap_reads),
        "high_speed_compression_repeatable": compression_repeatable,
        "high_speed_rebound_repeatable": rebound_repeatable,
        "compression_boundary_stable": compression_stable,
        "rebound_boundary_stable": rebound_stable,
        "boundary_sensitivity_patterns": sensitivity_patterns,
    })


def _continuous_shock_slice(samples: list[tuple[Any, Any]], expected_sample_rate_hz: float) -> bool:
    scoped_times = [time for raw_time, _ in samples if (time := _finite(raw_time)) is not None]
    qualified = [
        (time, velocity)
        for raw_time, raw_velocity in samples
        if (time := _finite(raw_time)) is not None
        and (velocity := _finite(raw_velocity)) is not None
    ]
    if len(qualified) < MIN_SAMPLE_COUNT:
        return False
    if not samples or len(scoped_times) / len(samples) < MIN_FINITE_SHOCK_COVERAGE:
        return False
    if len(qualified) / len(samples) < MIN_FINITE_SHOCK_COVERAGE:
        return False
    times = [time for time, _ in qualified]
    deltas = [right - left for left, right in zip(times, times[1:])]
    if not deltas or any(delta <= 0 for delta in deltas):
        return False
    ordered = sorted(deltas)
    median = ordered[len(ordered) // 2]
    if median <= 0 or times[-1] - times[0] < MIN_CONTINUOUS_DURATION_S:
        return False
    scoped_span = max(scoped_times) - min(scoped_times)
    if scoped_span > 0 and (times[-1] - times[0]) / scoped_span < MIN_FINITE_SHOCK_COVERAGE:
        return False
    expected_rate = expected_sample_rate_hz if math.isfinite(expected_sample_rate_hz) and expected_sample_rate_hz > 0 else 60.0
    if 1.0 / median < expected_rate * 0.80:
        return False
    if max(deltas) > median * 1.5:
        return False
    jitter = max(abs(delta - median) for delta in deltas) / median
    return jitter <= 0.10


def classify_corner_pattern(
    rebound_hi_pct: float,
    rebound_lo_pct: float,
    bump_lo_pct: float,
    bump_hi_pct: float,
    rms_in_s: float | None,
    activity_index: float | None,
) -> tuple[Pattern, Confidence]:
    low_delta = bump_lo_pct - rebound_lo_pct
    high_delta = bump_hi_pct - rebound_hi_pct
    high_total = bump_hi_pct + rebound_hi_pct
    active = max(rms_in_s or 0.0, activity_index or 0.0)

    if high_total >= 38 and bump_hi_pct >= 10 and rebound_hi_pct >= 10 and active >= 1.6:
        return "excessive_high_speed_shoulders", "medium"  # type: ignore[return-value]
    if high_delta >= 12 and bump_hi_pct >= 18:
        return "high_speed_bump_heavy", "medium"  # type: ignore[return-value]
    if high_delta <= -12 and rebound_hi_pct >= 18:
        return "high_speed_rebound_heavy", "medium"  # type: ignore[return-value]
    if low_delta >= 12 and bump_lo_pct >= 18:
        return "low_speed_bump_heavy", "medium"  # type: ignore[return-value]
    if low_delta <= -12 and rebound_lo_pct >= 18:
        return "low_speed_rebound_heavy", "medium"  # type: ignore[return-value]
    if abs(low_delta) <= 8 and abs(high_delta) <= 8 and high_total < 32:
        return "balanced", "high"  # type: ignore[return-value]
    return "balanced", "medium"  # type: ignore[return-value]


def _build_recommendations(
    corners: list[ShockCornerRead],
    context: dict[str, Any],
    *,
    setup_snapshot: SetupSnapshot | None,
    include_debug: bool,
) -> list[ShockRecommendation]:
    usable = [corner for corner in corners if corner.pattern != "insufficient_evidence"]
    candidates = [
        (corner, rec)
        for corner in corners
        for rec in corner.setting_recommendations
        if rec.direction in {"add", "subtract", "blocked"} and rec.confidence != "needs_more_evidence"
        and rec.confidence in {"medium", "high"}
    ]
    if candidates:
        corner, rec = max(candidates, key=lambda item: _recommendation_priority(item[1], item[0]))
        return [_compat_recommend(corner, rec, context, include_debug)]

    return [
        ShockRecommendation(
            id="shock_reader_leave_alone",
            corner_scope="all",
            setting="ls_compression",
            display_setting="LS bump",
            semantic_direction="leave_alone",
            numeric_step=None,
            current_value=None,
            suggested_value=None,
            blocked_by_limit=False,
            classification="leave_alone",
            goal="Leave the shock package alone until a selected zone shows a repeatable imbalance.",
            tradeoff="Changing a balanced histogram can create a problem that was not there.",
            next_test="Keep the current shock settings and compare the same lap/window again after the next run.",
            watch_for=["New contact, chatter, or recovery issues in the same zone."],
            confidence="high" if all(corner.pattern == "balanced" for corner in usable) else "medium",
            evidence_summary="Shock histogram zones are reasonably balanced and no guarded shock swing is justified.",
            hidden_debug={"patterns": [corner.pattern for corner in usable]} if include_debug else None,
        )
    ]


def _attach_setting_recommendations(
    corners: list[ShockCornerRead],
    context: dict[str, Any],
    setup_snapshot: SetupSnapshot | None,
) -> list[ShockCornerRead]:
    return [
        corner.model_copy(
            update={
                "setup_values": _corner_setup_values(setup_snapshot, corner.corner),
                "setting_recommendations": _build_setting_recommendations(corner, context, setup_snapshot),
            }
        )
        for corner in corners
    ]


def _enforce_one_change(corners: list[ShockCornerRead]) -> list[ShockCornerRead]:
    actionable = [
        (corner, recommendation)
        for corner in corners
        for recommendation in corner.setting_recommendations
        if recommendation.direction in {"add", "subtract"}
        and recommendation.confidence in {"medium", "high"}
    ]
    if len(actionable) <= 1:
        return corners
    primary_corner, primary = max(
        actionable,
        key=lambda item: _recommendation_priority(item[1], item[0]),
    )
    reason = (
        f"One-change discipline: test {primary_corner.corner} {primary.display_label} first; "
        "all other shock rows stay unchanged for this stage."
    )
    return [
        corner.model_copy(update={
            "setting_recommendations": [
                recommendation
                if corner.corner == primary_corner.corner and recommendation.setting == primary.setting
                else recommendation.model_copy(update={
                    "delta": None,
                    "suggested_value": None,
                    "direction": "hold",
                    "magnitude": "hold",
                    "confidence": "low",
                    "reason_short": reason,
                    "action_text": f"Hold {recommendation.display_label}; {reason}",
                    "expected_effect": "No effect is assigned while the primary one-change test is running.",
                    "change_size_explanation": "No test input in this stage.",
                    "keep_if": "Keep this row unchanged through A/B/A2.",
                    "undo_if": "Not applicable; this row was not changed.",
                    "blocked_reason": reason,
                    "blocker_reasons": [reason],
                })
                if recommendation.direction in {"add", "subtract"}
                else recommendation
                for recommendation in corner.setting_recommendations
            ]
        })
        for corner in corners
    ]


def _corner_setup_values(setup_snapshot: SetupSnapshot | None, corner: str) -> dict[str, int | None]:
    return {setting: _setup_value(setup_snapshot, corner, _schema_setting) for setting, _label, _schema_setting in INLINE_SETTINGS}


def _build_setting_recommendations(
    corner: ShockCornerRead,
    context: dict[str, Any],
    setup_snapshot: SetupSnapshot | None,
) -> list[ShockSettingRecommendation]:
    return [
        _setting_recommendation(corner, context, setup_snapshot, label, schema_setting)
        for _setup_key, label, schema_setting in INLINE_SETTINGS
    ]


def _setting_recommendation(
    corner: ShockCornerRead,
    context: dict[str, Any],
    setup_snapshot: SetupSnapshot | None,
    display_label: str,
    setting: ShockSetting,
) -> ShockSettingRecommendation:
    current = _setup_value(setup_snapshot, corner.corner, setting)
    slope_blocker = _slope_blocker(corner, context, setting)
    signed_score, reason = _setting_signal(corner, context, setting)
    absolute_score = abs(signed_score)
    confidence = _setting_confidence(corner, context, absolute_score)
    desired_delta = _scaled_delta(signed_score, setting, context)
    direction: str = "add" if desired_delta > 0 else "subtract" if desired_delta < 0 else "hold"
    blocked_reason: str | None = None
    delta: int | None = None
    suggested: int | None = None

    if slope_blocker is not None:
        direction = "needs_more_evidence"
        confidence = "needs_more_evidence"
        blocked_reason = slope_blocker
        reason = slope_blocker
    elif corner.pattern == "insufficient_evidence" or confidence == "needs_more_evidence":
        direction = "needs_more_evidence"
        reason = "Need a cleaner selected lap/window before changing this setting."
    elif desired_delta != 0 and confidence == "low":
        direction = "needs_more_evidence"
        reason = "The signal is visible, but it is not strong enough for an exact click change. Repeat the same zone."
    elif desired_delta == 0:
        direction = "hold"
        reason = reason or "No guarded change for this row."
    elif current is None:
        direction = "needs_more_evidence"
        blocked_reason = "setup value missing"
        reason = "Capture the current corner-specific setting before authorizing a setup change."
    else:
        # The setup snapshot carries the current value, not every car's legal option
        # table. Authorize only an adjacent direction and never invent a target value.
        delta = desired_delta
        suggested = None

    magnitude = _setting_magnitude(delta if delta is not None else desired_delta if direction in {"add", "subtract"} else 0)
    goal, tradeoff, watch_for = _setting_text(setting, direction, reason)
    action_text, expected_effect, size_explanation, keep_if, undo_if = _setting_action_contract(
        setting,
        direction,
        current=current,
        delta=delta,
        suggested=suggested,
        reason=reason,
    )
    return ShockSettingRecommendation(
        corner=corner.corner,  # type: ignore[arg-type]
        setting=setting,  # type: ignore[arg-type]
        display_label=display_label,  # type: ignore[arg-type]
        current_value=current,
        delta=delta,
        suggested_value=suggested,
        direction=direction,  # type: ignore[arg-type]
        magnitude=magnitude,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        reason_short=reason,
        action_text=action_text,
        expected_effect=expected_effect,
        change_size_explanation=size_explanation,
        keep_if=keep_if,
        undo_if=undo_if,
        goal=goal,
        tradeoff=tradeoff,
        watch_for=watch_for,
        blocked_reason=blocked_reason,
        source_channels=[
            f"{corner.corner.lower()}_shock_vel_in_s",
            "lap_dist_pct",
            *(
                ["platform_compression_index", "rear_scrape_margin_mm", "shock_activity_index"]
                if setting in {"hs_compression_slope", "hs_rebound_slope"}
                else []
            ),
        ],
        blocker_reasons=[blocked_reason] if blocked_reason else [],
    )


def _setting_signal(corner: ShockCornerRead, context: dict[str, Any], setting: ShockSetting) -> tuple[int, str]:
    low_delta = corner.bump_lo_pct - corner.rebound_lo_pct
    high_delta = corner.bump_hi_pct - corner.rebound_hi_pct
    active = max(corner.rms_in_s or 0.0, corner.activity_index or 0.0)

    if setting == "ls_compression":
        if corner.pattern == "low_speed_rebound_heavy" and low_delta <= -12 and _corner_packed(context, corner):
            return _score_from_gap(abs(low_delta), active, context, corner=corner), "Low-speed bump is under the matching rebound share; add platform support."
        if corner.pattern == "low_speed_bump_heavy" and low_delta >= 12:
            return -_score_from_gap(abs(low_delta), active, context, corner=corner), "Low-speed bump is high versus rebound; free compression before adding support."
    elif setting == "hs_compression":
        if corner.pattern == "impact_contact_driven" or (high_delta >= 12 and _corner_contact(context, corner)):
            return _score_from_gap(abs(high_delta), active, context, corner=corner, bonus=1), "High-speed bump and platform/contact evidence point to more support."
        if high_delta >= 12 and context["chatter"] and not _corner_contact(context, corner):
            return -_score_from_gap(abs(high_delta), active, context, corner=corner), "High-speed bump is active without contact; reduce harshness/chatter."
    elif setting == "hs_compression_slope":
        if not _slope_context(context, corner, "compression"):
            return 0, "Compression slope needs repeated compression and platform-contact evidence in the same physical zone."
        if high_delta >= 16:
            return min(3, _score_from_gap(abs(high_delta), active, context, corner=corner)), "Repeated high-speed compression and platform contact in the same zone support testing a more linear curve."
    elif setting == "ls_rebound":
        if corner.pattern == "low_speed_rebound_heavy" and low_delta <= -12:
            return -_score_from_gap(abs(low_delta), active, context, corner=corner), "Low-speed rebound is high; reduce tie-down risk."
        if corner.pattern == "low_speed_bump_heavy" and low_delta >= 12 and context["recovery"]:
            return _score_from_gap(abs(low_delta), active, context, corner=corner), "Low-speed recovery is under-controlled versus bump."
    elif setting == "hs_rebound":
        if corner.pattern == "oscillation_recovery_issue" and not _corner_packed(context, corner):
            return _score_from_gap(abs(high_delta), active, context, corner=corner, bonus=1), "High-speed recovery looks too free after the hit."
        if high_delta <= -12 or (corner.pattern == "oscillation_recovery_issue" and _corner_packed(context, corner)):
            return -_score_from_gap(abs(high_delta), active, context, corner=corner), "High-speed rebound is heavy; reduce packing/tie-down risk."
    elif setting == "hs_rebound_slope":
        if not _slope_context(context, corner, "rebound"):
            return 0, "Rebound slope needs repeated extension and packing/contact evidence in the same physical zone."
        if high_delta <= -16 and _corner_packed(context, corner):
            return -min(3, _score_from_gap(abs(high_delta), active, context, corner=corner)), "Repeated high-speed extension with packing/contact in the same zone supports testing a more digressive curve."

    return 0, "No guarded signal for this setting."


def _score_from_gap(
    gap: float,
    active: float,
    context: dict[str, Any],
    *,
    corner: ShockCornerRead,
    bonus: int = 0,
) -> int:
    score = 1 if gap >= 10 else 0
    if gap >= 18:
        score += 1
    if gap >= 30:
        score += 1
    if active >= 1.4:
        score += 1
    if context["selected_zone"]:
        score += 1
    if _corner_contact(context, corner) or _corner_packed(context, corner):
        score += 1
    return max(0, min(5, score + bonus))


def _slope_context(context: dict[str, Any], corner: ShockCornerRead, side: str) -> bool:
    if not context["slope_allowed"]:
        return False
    if side == "compression":
        return (
            corner.high_speed_compression_repeatable
            and corner.compression_boundary_stable
            and corner.bump_hi_pct >= 18
            and _corner_contact(context, corner)
        )
    return (
        corner.high_speed_rebound_repeatable
        and corner.rebound_boundary_stable
        and corner.rebound_hi_pct >= 18
        and _corner_packed(context, corner)
    )


def _slope_blocker(
    corner: ShockCornerRead,
    context: dict[str, Any],
    setting: ShockSetting,
) -> str | None:
    if setting not in {"hs_compression_slope", "hs_rebound_slope"}:
        return None
    side = "compression" if setting == "hs_compression_slope" else "rebound"
    if not context["slope_boundary_verified"]:
        return "Slope action is withheld because this car does not have a verified high-speed transition boundary."
    repeated = (
        corner.high_speed_compression_repeatable
        if side == "compression"
        else corner.high_speed_rebound_repeatable
    )
    boundary_stable = corner.compression_boundary_stable if side == "compression" else corner.rebound_boundary_stable
    if corner.repeatability_lap_count < 2:
        return "Slope shape needs the same high-speed signature on at least two eligible laps; select a clean lap window."
    if not repeated:
        return f"The high-speed {side} signature did not repeat in the same direction across the eligible laps."
    if not boundary_stable:
        return "The slope conclusion changes when the analytical high/low boundary moves by 25%, so the shape signal is not robust."
    if not _corner_slope_context_repeatable(context, corner):
        return f"{corner.corner} axle platform contact or packing context did not repeat on at least two eligible laps."
    if not context["slope_allowed"]:
        return "Slope shape needs a selected physical zone with repeated measured platform contact or packing context."
    return None


def _setting_confidence(corner: ShockCornerRead, context: dict[str, Any], score: int) -> SettingConfidence:
    if corner.pattern == "insufficient_evidence" or corner.sample_count < MIN_SAMPLE_COUNT:
        return "needs_more_evidence"
    elif score == 0:
        return "low"
    elif score >= 4 and context["selected_zone"]:
        return "high"
    elif score >= 2:
        return "medium"
    else:
        return "low"


def _scaled_delta(score: int, setting: ShockSetting, context: dict[str, Any]) -> int:
    sign = 1 if score > 0 else -1 if score < 0 else 0
    return sign


def _bounded_delta(current: int, desired_delta: int) -> tuple[int | None, int | None, bool]:
    return (1 if desired_delta > 0 else -1 if desired_delta < 0 else None), None, False


def _setting_magnitude(delta: int) -> str:
    amount = abs(delta)
    if amount == 0:
        return "hold"
    elif amount == 1:
        return "small"
    elif amount <= 3:
        return "medium"
    else:
        return "big"


def _setting_text(setting: ShockSetting, direction: str, reason: str) -> tuple[str, str, list[str]]:
    if direction == "needs_more_evidence":
        return (
            "Collect a cleaner shock read before touching this row.",
            "Guessing here can create a setup problem that was not in the data.",
            ["Repeat the same lap/window", "Look for stable corner pattern"],
        )
    if direction == "blocked":
        return (
            "The requested direction is already against the click limit.",
            "A bigger package change may be needed before this click can move.",
            ["Do not force past the 1-10 range", "Re-check adjacent settings"],
        )
    if direction == "hold":
        return (
            "Leave this row alone for the next run.",
            "Changing a quiet row can mask the real shock signal.",
            ["New imbalance after the next clean run"],
        )
    if setting == "ls_compression":
        return (
            "Tune low-speed platform support at this corner.",
            "More LS compression adds support; less can improve compliance.",
            ["Platform movement", "Harshness over driver inputs"],
        )
    if setting == "hs_compression":
        return (
            "Tune high-speed bump support without touching rebound.",
            "More support protects the platform; less can calm chatter.",
            ["Contact/blow-through", "Harshness and tire load spikes"],
        )
    if setting == "hs_compression_slope":
        return (
            "Shape high-speed compression response.",
            "More linear adds support; more digressive adds compliance.",
            ["Harshness if too linear", "Contact if too digressive"],
        )
    if setting == "ls_rebound":
        return (
            "Tune low-speed recovery and tie-down.",
            "More rebound slows extension; less helps the corner recover.",
            ["Lazy recovery", "Tied-down feel"],
        )
    if setting == "hs_rebound":
        return (
            "Tune high-speed recovery after bumps or platform hits.",
            "More rebound can control bounce; less can reduce packing.",
            ["Bounce after hits", "Packing down"],
        )
    return (
        "Shape high-speed rebound recovery.",
        "More linear supports recovery; more digressive adds compliance.",
        ["Packing if too linear", "Bounce if too digressive"],
    )


def _setting_action_contract(
    setting: ShockSetting,
    direction: str,
    *,
    current: int | None,
    delta: int | None,
    suggested: int | None,
    reason: str,
) -> tuple[str, str, str, str, str]:
    is_slope = setting in {"hs_compression_slope", "hs_rebound_slope"}
    side = "compression" if setting in {"ls_compression", "hs_compression", "hs_compression_slope"} else "rebound"
    if direction == "needs_more_evidence":
        return (
            f"Hold {DISPLAY_SETTING[setting]}; {reason}",
            "No curve-shape or damping-strength effect is claimed until the evidence gate passes.",
            "No test input is authorized.",
            "Keep the current setting while collecting the requested repeat evidence.",
            "Do not change this setting from an unqualified histogram.",
        )
    if direction == "blocked":
        return (
            f"Hold {DISPLAY_SETTING[setting]} at {current}; the requested direction is outside the configured range.",
            "No out-of-range setting is proposed.",
            "Blocked by the configured click limit.",
            "Keep the current setting and reassess the surrounding package.",
            "Do not force a value beyond the garage limit.",
        )
    if direction == "hold":
        return (
            f"Hold {DISPLAY_SETTING[setting]} at {current if current is not None else 'the recorded value'}.",
            "The qualified window does not justify changing this row.",
            "No test input.",
            "Keep it unchanged while the same-zone evidence remains balanced.",
            "Reopen this row only if a repeatable imbalance appears.",
        )

    verb = "Increase" if direction == "add" else "Decrease"
    transition = (
        f" from {current} to {suggested}"
        if current is not None and suggested is not None
        else " by one adjacent available garage option"
        if is_slope
        else " by one available click"
    )
    if is_slope:
        shape = "more linear" if direction == "add" else "more digressive"
        expected = (
            f"A {shape} high-speed {side} curve changes how damping force grows at larger shaft speeds; "
            "the low-speed click setting is left unchanged."
        )
        keep_if = (
            "Keep only if the same high-speed zone repeats with less contact/blow-through and no added harshness or tire-load spike."
            if side == "compression" and direction == "add"
            else "Keep only if the same high-speed zone repeats with less harshness/chatter and no new platform contact."
            if side == "compression"
            else "Keep only if high-speed extension becomes controlled without wheel unloading or suspension packing."
            if direction == "add"
            else "Keep only if packing reduces and the wheel recovers without a new rebound oscillation."
        )
        undo_if = (
            "Undo immediately if the target symptom does not improve, the opposite guardrail worsens, or the signature fails to repeat on A2."
        )
        return (
            f"{verb} {DISPLAY_SETTING[setting]}{transition} toward a {shape} curve.",
            expected,
            "One adjacent slope option is a small control input but a package-level curve-shape experiment; change no other shock row.",
            keep_if,
            undo_if,
        )

    expected = (
        f"This changes high-speed {side} damping strength in the measured shaft-speed regime."
        if setting in {"hs_compression", "hs_rebound"}
        else f"This changes low-speed {side} control during platform and driver-input motion."
    )
    amount = abs(delta or 1)
    return (
        f"{verb} {DISPLAY_SETTING[setting]}{transition}.",
        expected,
        f"{amount} click{'s' if amount != 1 else ''}: {_setting_magnitude(amount)} input; test this row by itself.",
        "Keep only if the target-zone motion improves beyond normal variation without worsening the declared guardrails.",
        "Undo if the target does not improve, grip/harshness worsens, or the effect does not repeat against restored baseline.",
    )


def _recommendation_priority(rec: ShockSettingRecommendation, corner: ShockCornerRead) -> tuple[int, int, float, float]:
    direction_rank = 1 if rec.direction == "blocked" else 2
    confidence_rank = {"needs_more_evidence": 0, "low": 1, "medium": 2, "high": 3}[rec.confidence]
    slope_rank = 1 if rec.setting in {"hs_compression_slope", "hs_rebound_slope"} else 0
    return (direction_rank, slope_rank, confidence_rank, corner.bump_hi_pct + corner.rebound_hi_pct)


def _compat_recommend(
    corner: ShockCornerRead,
    rec: ShockSettingRecommendation,
    context: dict[str, Any],
    include_debug: bool,
) -> ShockRecommendation:
    semantic: str
    if rec.direction == "add":
        semantic = "move_more_linear" if rec.setting in {"hs_compression_slope", "hs_rebound_slope"} else "add"
    elif rec.direction == "subtract":
        semantic = "move_more_digressive" if rec.setting in {"hs_compression_slope", "hs_rebound_slope"} else "subtract"
    else:
        semantic = "subtract" if (rec.delta or 0) < 0 else "add"
    classification = "package_swing" if rec.setting in {"hs_compression_slope", "hs_rebound_slope"} else "balance_swing" if rec.magnitude in {"medium", "big"} else "fine_tune"
    rec_confidence: Confidence = "high" if rec.confidence == "high" else "medium" if rec.confidence == "medium" else "low"
    return ShockRecommendation(
        id=f"shock_reader_{corner.corner.lower()}_{rec.setting}_{rec.direction}",
        corner_scope=corner.corner,  # type: ignore[arg-type]
        setting=rec.setting,
        display_setting=rec.display_label,
        semantic_direction=semantic,  # type: ignore[arg-type]
        numeric_step=rec.delta,
        current_value=rec.current_value,
        suggested_value=rec.suggested_value,
        blocked_by_limit=rec.direction == "blocked",
        classification=classification,  # type: ignore[arg-type]
        goal=rec.goal,
        tradeoff=rec.tradeoff,
        next_test=(
            f"{rec.action_text} Run A/B/A2 through the same zone with at least three eligible passes per stage; "
            "restore A exactly for A2."
        ),
        watch_for=rec.watch_for,
        confidence=rec_confidence,
        evidence_summary=_evidence_summary(corner, context),
        hidden_debug={
            "inline_setting": rec.setting,
            "inline_direction": rec.direction,
            "reason": rec.reason_short,
        } if include_debug else None,
        source_channels=rec.source_channels,
        blocker_reasons=[rec.blocked_reason] if rec.blocked_reason else [],
    )


def _apply_context_patterns(corners: list[ShockCornerRead], context: dict[str, Any]) -> list[ShockCornerRead]:
    updated: list[ShockCornerRead] = []
    for corner in corners:
        if (
            corner.pattern == "high_speed_bump_heavy"
            and _corner_contact(context, corner)
            and corner.high_speed_compression_repeatable
        ):
            updated.append(corner.model_copy(update={"pattern": "impact_contact_driven", "confidence": "high" if context["selected_zone"] else "medium"}))
        elif corner.pattern == "high_speed_rebound_heavy" and context["recovery"]:
            updated.append(corner.model_copy(update={"pattern": "oscillation_recovery_issue"}))
        else:
            updated.append(corner)
    return updated


def _recommend(
    corner: ShockCornerRead,
    setting: ShockSetting,
    semantic_direction: str,
    step: int,
    classification: str,
    context: dict[str, Any],
    setup_snapshot: SetupSnapshot | None,
    include_debug: bool,
) -> ShockRecommendation:
    current = _setup_value(setup_snapshot, corner.corner, setting)
    numeric_step, suggested, blocked = _bounded_step(current, step)
    goal, tradeoff, watch_for = _recommendation_text(setting, semantic_direction, corner.pattern)
    if setting in {"compression_slope", "rebound_slope"}:
        semantic_direction = "move_more_linear" if step > 0 else "move_more_digressive"
    return ShockRecommendation(
        id=f"shock_reader_{corner.corner.lower()}_{setting}_{'add' if step > 0 else 'subtract'}",
        corner_scope=corner.corner,  # type: ignore[arg-type]
        setting=setting,
        display_setting=DISPLAY_SETTING[setting],
        semantic_direction=semantic_direction,  # type: ignore[arg-type]
        numeric_step=numeric_step,
        current_value=current,
        suggested_value=suggested,
        blocked_by_limit=blocked,
        classification=classification,  # type: ignore[arg-type]
        goal=goal,
        tradeoff=tradeoff,
        next_test=f"Try one {DISPLAY_SETTING[setting]} click on {corner.corner}, then compare the same Shocks lap/window.",
        watch_for=watch_for,
        confidence=_recommendation_confidence(corner, context),
        evidence_summary=_evidence_summary(corner, context),
        hidden_debug={
            "pattern": corner.pattern,
            "selected_zone": context["selected_zone"],
            "contact": context["contact"],
            "chatter": context["chatter"],
            "recovery": context["recovery"],
        } if include_debug else None,
        source_channels=[f"{corner.corner.lower()}_shock_vel_in_s", "lap_dist_pct"],
        blocker_reasons=["Shock setting is at its configured limit."] if blocked else [],
    )


def _recommendation_text(setting: ShockSetting, semantic_direction: str, pattern: str) -> tuple[str, str, list[str]]:
    if setting == "ls_compression":
        return (
            "Let that corner compress more cleanly during driver/platform movement.",
            "Too little LS bump can let the platform move too much.",
            ["More platform movement", "Loss of support on brake/turn/drive inputs"],
        )
    if setting == "ls_rebound":
        return (
            "Let the corner recover and extend more freely.",
            "Too little rebound can allow bounce or sloppy recovery.",
            ["Bounce after release", "Lazy platform recovery"],
        )
    if setting == "hs_compression":
        if semantic_direction == "add":
            return (
                "Add high-speed support to prevent blow-through/contact.",
                "Can increase tire load variation and harshness.",
                ["Harshness", "More tire load variation", "Lost compliance over bumps"],
            )
        return (
            "Reduce high-speed harshness or chatter.",
            "May lose floor protection on larger bumps.",
            ["New scrape/contact", "Less platform protection"],
        )
    if setting == "hs_rebound":
        return (
            "Clean up platform/tire recovery after a sharp hit.",
            "Wrong direction can pack the suspension down or let it bounce.",
            ["Packing down", "Bouncing after sharp hits"],
        )
    if setting == "compression_slope":
        return (
            "Change high-speed compression shape without changing low-speed behavior.",
            "Slope is a package swing and should be tested by itself.",
            ["Harshness if too linear", "Contact if too digressive"],
        )
    return (
        "Change high-speed rebound shape without changing low-speed behavior.",
        "Slope is a package swing and should be tested by itself.",
        ["Packing if too linear", "Bounce if too digressive"],
    )


def _read_shock_reader_columns(
    run_id: str,
    *,
    lap: int | None,
    lap_window: tuple[int, int] | None,
    phase: str | None,
    zone: tuple[float, float] | None,
    data_dir: str | Path | None,
    warnings: list[str],
    eligible_lap_numbers: set[int] | None,
) -> dict[str, list[Any]]:
    if importlib.util.find_spec("polars") is None:
        warnings.append("Polars is unavailable; shock reader requires parquet cache access.")
        return {}
    pl = __import__("polars")
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    path = parquet_path(data_root, run_id)
    if not path.exists():
        warnings.append(f"Parquet cache not found for run {run_id}.")
        return {}

    schema = pl.read_parquet_schema(path)
    existing = set(schema.keys())
    wanted = list(dict.fromkeys([*VELOCITY_CHANNELS.values(), *CONTEXT_CHANNELS]))
    for channels in DEFLECTION_DELTA_CHANNELS.values():
        wanted.extend(channels)
    wanted.extend(ACTIVITY_CHANNELS.values())
    safe = [column for column in dict.fromkeys(wanted) if column in existing]
    if all(channel not in safe for channel in VELOCITY_CHANNELS.values()):
        return {}
    if zone is not None and "lap_dist_pct" not in safe:
        warnings.append(
            "Selected-zone shock analysis is unavailable because lap-position telemetry is missing; full-lap data was not substituted."
        )
        return {}

    frame = pl.scan_parquet(path).select(safe)
    if lap is not None and "lap" in safe:
        frame = frame.filter(pl.col("lap") == int(lap))
    elif lap_window is not None and "lap" in safe:
        start, end = lap_window
        frame = frame.filter((pl.col("lap") >= int(start)) & (pl.col("lap") <= int(end)))
    elif eligible_lap_numbers is not None and "lap" in safe:
        frame = frame.filter(pl.col("lap").is_in(sorted(eligible_lap_numbers)))
    frame = _apply_phase_filter(frame, pl, phase, safe)
    if zone is not None and "lap_dist_pct" in safe:
        start, end = zone
        frame = frame.filter(
            (pl.col("lap_dist_pct") >= start / 100.0)
            & (pl.col("lap_dist_pct") <= end / 100.0)
        )
    collected = frame.collect()
    return {column: collected.get_column(column).to_list() for column in collected.columns}


def _apply_phase_filter(frame: Any, pl: Any, phase: str | None, columns: list[str]) -> Any:
    if not phase:
        return frame
    normalized = phase.lower()
    has_brake = "brake_pct" in columns
    has_throttle = "throttle_pct" in columns
    steering_col = "abs_steering_deg" if "abs_steering_deg" in columns else "steering_deg" if "steering_deg" in columns else None
    expr = None
    if normalized == "braking" and has_brake:
        expr = pl.col("brake_pct") > 5
    elif normalized in {"turn_in", "entry"} and steering_col:
        expr = pl.col(steering_col).abs() > 2
        if has_throttle:
            expr = expr & (pl.col("throttle_pct") < 85)
    elif normalized == "exit" and has_throttle:
        expr = pl.col("throttle_pct") > 35
    elif normalized == "straight" and steering_col and has_throttle:
        expr = (pl.col(steering_col).abs() < 2) & (pl.col("throttle_pct") > 70)
    return frame if expr is None else frame.filter(expr)


def _build_context(
    data: dict[str, list[Any]],
    *,
    phase: str | None,
    selected_zone: bool,
    slope_boundary_verified: bool,
) -> dict[str, Any]:
    def observe(dataset: dict[str, list[Any]]) -> dict[str, bool]:
        rear_margin = _min(_numeric_series(dataset, "rear_scrape_margin_mm"))
        rear_scrape = _max(_numeric_series(dataset, "rear_scrape_risk_score"))
        rear_contact = _max(_numeric_series(dataset, "rear_platform_contact_risk"))
        cfs_in = _min(_numeric_series(dataset, "cfs_ride_height_in"))
        cfs_mm = _min(_numeric_series(dataset, "cfs_ride_height_mm"))
        rear_contact = any(
            value is not None and value > threshold
            for value, threshold in [(rear_scrape, 0.45), (rear_contact, 0.45)]
        ) or (rear_margin is not None and rear_margin <= 0.0)
        front_contact = (cfs_in is not None and cfs_in <= 0.12) or (cfs_mm is not None and cfs_mm <= 3.0)
        contact = rear_contact or front_contact
        global_activity = _mean(_numeric_series(dataset, "shock_activity_index"))
        damper_energy = _mean(_numeric_series(dataset, "damper_energy_proxy"))
        chatter = not contact and ((global_activity or 0.0) >= 1.4 or (damper_energy or 0.0) >= 1.4)
        compression_index = _max(_numeric_series(dataset, "platform_compression_index"))
        platform_trace = any(
            name in dataset
            for name in (
                "cfs_ride_height_in", "rear_scrape_margin_mm", "rear_platform_contact_risk",
                "front_center_rh_in", "rear_center_rh_in",
            )
        )
        return {
            "contact": contact,
            "front_contact": front_contact,
            "rear_contact": rear_contact,
            "chatter": chatter,
            "platform_trace": platform_trace,
            "packed": contact or (compression_index is not None and compression_index > 0.65),
            "front_packed": front_contact,
            "rear_packed": rear_contact,
        }

    observed = observe(data)
    lap_values = data.get("lap", [])
    lap_numbers = sorted({int(value) for value in (_finite(item) for item in lap_values) if value is not None and value.is_integer()})
    per_lap_context: list[dict[str, bool]] = []
    for number in lap_numbers:
        indexes = [index for index, item in enumerate(lap_values) if _finite(item) == number]
        if not indexes:
            continue
        per_lap_context.append(observe({
            channel: [items[index] for index in indexes if index < len(items)]
            for channel, items in data.items()
        }))
    contact_lap_count = sum(item["contact"] for item in per_lap_context)
    front_contact_lap_count = sum(item["front_contact"] for item in per_lap_context)
    rear_contact_lap_count = sum(item["rear_contact"] for item in per_lap_context)
    chatter_lap_count = sum(item["chatter"] for item in per_lap_context)
    packed_lap_count = sum(item["packed"] for item in per_lap_context)
    repeated_context = contact_lap_count >= 2 or packed_lap_count >= 2
    recovery = phase in {"transition", "exit", "entry"} or observed["chatter"]
    return {
        "selected_zone": selected_zone,
        "phase": phase,
        "contact": observed["contact"],
        "front_contact": observed["front_contact"],
        "rear_contact": observed["rear_contact"],
        "platform_trace": observed["platform_trace"],
        "chatter": observed["chatter"],
        "recovery": recovery,
        "packed": observed["packed"],
        "front_packed": observed["front_packed"],
        "rear_packed": observed["rear_packed"],
        "contact_lap_count": contact_lap_count,
        "front_contact_lap_count": front_contact_lap_count,
        "rear_contact_lap_count": rear_contact_lap_count,
        "chatter_lap_count": chatter_lap_count,
        "packed_lap_count": packed_lap_count,
        "slope_boundary_verified": slope_boundary_verified,
        "slope_context_repeatable": repeated_context,
        "slope_allowed": (
            selected_zone
            and (observed["contact"] or observed["packed"])
            and observed["platform_trace"]
            and repeated_context
            and slope_boundary_verified
        ),
    }


def _corner_contact(context: dict[str, Any], corner: ShockCornerRead) -> bool:
    return bool(context["front_contact"] if corner.corner in {"LF", "RF"} else context["rear_contact"])


def _corner_packed(context: dict[str, Any], corner: ShockCornerRead) -> bool:
    return bool(context["front_packed"] if corner.corner in {"LF", "RF"} else context["rear_packed"])


def _corner_slope_context_repeatable(context: dict[str, Any], corner: ShockCornerRead) -> bool:
    count = context["front_contact_lap_count"] if corner.corner in {"LF", "RF"} else context["rear_contact_lap_count"]
    return count >= 2


def _setup_value(setup: SetupSnapshot | None, corner: str, setting: ShockSetting) -> int | None:
    if setup is None:
        return None
    extracted = setup.extracted_values or {}
    corner_key = corner.lower()
    candidates = SETUP_KEY_CANDIDATES[setting]
    corner_values = extracted.get(corner_key)
    if isinstance(corner_values, dict):
        for key in candidates:
            value = _click_value(corner_values.get(key))
            if value is not None:
                return value
    for key in candidates:
        for flat_key in (f"{corner_key}_{key}", f"{corner}_{key}", key):
            value = _click_value(extracted.get(flat_key))
            if value is not None:
                return value
    return None


def _setting_available(setup: SetupSnapshot | None, corner: str, setting: ShockSetting) -> bool:
    return _setup_value(setup, corner, setting) is not None


def _bounded_step(current: int | None, step: int) -> tuple[int | None, int | None, bool]:
    if current is None or step == 0:
        return None, None, False
    return 1 if step > 0 else -1, None, False


def _click_value(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer():
        return None
    return int(numeric)


def _recommendation_confidence(corner: ShockCornerRead, context: dict[str, Any]) -> Confidence:
    if corner.confidence == "high" and context["selected_zone"]:
        return "high"
    if context["selected_zone"] and (context["contact"] or context["chatter"] or corner.sample_count >= 80):
        return "medium"
    return "low"


def _evidence_summary(corner: ShockCornerRead, context: dict[str, Any]) -> str:
    context_bits = []
    if context["selected_zone"]:
        context_bits.append("selected-zone context")
    if context["contact"]:
        context_bits.append("platform/contact evidence")
    if context["chatter"]:
        context_bits.append("high activity/chatter context")
    suffix = f" with {', '.join(context_bits)}" if context_bits else " without extra platform context"
    return (
        f"{corner.corner} pattern {corner.pattern}: RHi {corner.rebound_hi_pct:.1f}%, "
        f"RLo {corner.rebound_lo_pct:.1f}%, BLo {corner.bump_lo_pct:.1f}%, BHi {corner.bump_hi_pct:.1f}%{suffix}. "
        f"High-speed signature qualification used {corner.repeatability_lap_count} eligible lap(s); "
        f"boundary sensitivity patterns: {', '.join(corner.boundary_sensitivity_patterns) or 'unavailable'}."
    )


def _format_lap_window(*, lap: int | None, lap_window: tuple[int, int] | None) -> str | None:
    if lap is not None:
        return str(lap)
    elif lap_window is None:
        return None
    else:
        return f"{lap_window[0]}-{lap_window[1]}"


def _validated_zone(start: float | None, end: float | None) -> tuple[float, float] | None:
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise ValueError("Shock slope analysis needs both zone_start_pct and zone_end_pct.")
    if not all(math.isfinite(value) for value in (start, end)) or not 0.0 <= start < end <= 100.0:
        raise ValueError("Shock slope zone must satisfy 0 <= start < end <= 100 percent.")
    if end - start > MAX_SLOPE_ZONE_WIDTH_PCT:
        raise ValueError(f"Shock slope zone must be {MAX_SLOPE_ZONE_WIDTH_PCT:.0f}% of a lap or narrower.")
    return float(start), float(end)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _numeric_series(data: dict[str, list[Any]], channel: str) -> list[float]:
    return [value for value in (_finite(item) for item in data.get(channel, [])) if value is not None]


def _mean(values: Iterable[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    return sum(clean) / len(clean) if clean else None


def _min(values: Iterable[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    return min(clean, default=None)


def _max(values: Iterable[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    return max(clean, default=None)


def _pct(count: int, total: int) -> float:
    return (count / total) * 100.0 if total else 0.0


def _deflection_range(data: dict[str, list[Any]], corner: str) -> float | None:
    for channel in DEFLECTION_DELTA_CHANNELS[corner]:
        values = _numeric_series(data, channel)
        if values:
            return max(values) - min(values)
    return None
