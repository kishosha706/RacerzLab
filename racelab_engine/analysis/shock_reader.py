from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any, Iterable

from racelab_engine.analysis.shock_reader_schema import (
    Confidence,
    ObservedShockSetting,
    Pattern,
    ShockCornerRead,
    ShockReaderResponse,
    ShockSetting,
)
from racelab_engine.analysis.lap_eligibility import eligible_laps, find_lap, lap_ineligibility_reasons
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import (
    assert_telemetry_cache_identity,
    default_data_dir,
    parquet_path,
)


SHOCK_CORNERS = ("LF", "RF", "LR", "RR")
DEFAULT_BOUNDARY_IN_S = 1.0
NEXT_GEN_BOUNDARY_IN_S = 1.5
DEFAULT_BIN_WIDTH_IN_S = 0.5
MIN_SAMPLE_COUNT = 64
MIN_CONTINUOUS_DURATION_S = 0.75
MIN_FINITE_SHOCK_COVERAGE = 0.80
CENTER_DEADBAND_IN_S = 0.05
MAX_OBSERVATION_ZONE_WIDTH_PCT = 20.0
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
    "throttle_pct",
    "brake_pct",
    "abs_steering_deg",
    "steering_deg",
    "cfs_ride_height_in",
    "cfs_ride_height_mm",
    "rear_scrape_margin_mm",
    "rear_scrape_risk_score",
    "rear_platform_contact_risk",
    "shock_activity_index",
    "damper_energy_proxy",
]

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

INLINE_SETTINGS: tuple[tuple[ObservedShockSetting, str, ShockSetting], ...] = (
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
    expected_sample_rate_hz: float = 60.0,
    setup_snapshot: SetupSnapshot | None = None,
    lap_summaries: list[LapSummary] | None = None,
    data_dir: str | Path | None = None,
) -> ShockReaderResponse:
    warnings: list[str] = []
    zone = _validated_zone(zone_start_pct, zone_end_pct)
    observation_blocked_reason, eligible_lap_numbers = _shock_observation_eligibility(
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
            bin_width_in_s=DEFAULT_BIN_WIDTH_IN_S,
            setup_snapshot_available=setup_snapshot is not None,
            corners=[],
            warnings=[*warnings, "Shock telemetry unavailable for this run/window."],
            evidence_state=EvidenceState.UNAVAILABLE,
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
    )
    corners = _apply_context_patterns(corners, context)
    corners = [
        corner.model_copy(update={"setup_values": _corner_setup_values(setup_snapshot, corner.corner)})
        for corner in corners
    ]
    if observation_blocked_reason is not None:
        warnings.append(observation_blocked_reason)
    if all(corner.pattern == "insufficient_evidence" for corner in corners):
        warnings.append("Shock velocity channels are missing or too sparse for a guarded observation.")

    return ShockReaderResponse(
        run_id=run_id,
        lap_window=_format_lap_window(lap=lap, lap_window=lap_window),
        phase=phase,
        zone_start_pct=zone[0] if zone is not None else None,
        zone_end_pct=zone[1] if zone is not None else None,
        boundary_in_s=boundary,
        boundary_basis=boundary_basis,
        bin_width_in_s=DEFAULT_BIN_WIDTH_IN_S,
        setup_snapshot_available=setup_snapshot is not None,
        corners=corners,
        warnings=warnings,
        evidence_state=(
            EvidenceState.BLOCKED_BY_CONTEXT
            if observation_blocked_reason is not None
            else EvidenceState.UNAVAILABLE
            if all(corner.pattern == "insufficient_evidence" for corner in corners)
            else EvidenceState.NEEDS_CONFIRMATION
        ),
        source_channels=[
            channel for channel in VELOCITY_CHANNELS.values() if data.get(channel)
        ],
        blocker_reasons=(
            [observation_blocked_reason]
            if observation_blocked_reason is not None
            else ["Shock velocity channels are missing or too sparse."]
            if all(corner.pattern == "insufficient_evidence" for corner in corners)
            else []
        ),
    )


def _shock_observation_eligibility(
    lap_summaries: list[LapSummary] | None,
    *,
    lap: int | None,
    lap_window: tuple[int, int] | None,
) -> tuple[str | None, set[int] | None]:
    """Return an observation block and safe all-run filter without hiding samples."""
    if lap_summaries is None:
        return (
            "Canonical lap eligibility is unavailable. Recorded shock distributions remain visible "
            "as blocked context but cannot support a qualified comparison.",
            None,
        )

    eligible_numbers = {summary.lap_number for summary in eligible_laps(lap_summaries)}
    if lap is not None:
        summary = find_lap(lap_summaries, lap)
        reasons = ["Lap summary unavailable"] if summary is None else lap_ineligibility_reasons(summary)
        if summary is None or lap not in eligible_numbers:
            detail = ", ".join(reasons) or "Lap did not pass the canonical evidence gate"
            return (
                f"Lap {lap} is not eligible for a qualified shock observation ({detail}). "
                "Its recorded distribution remains visible as blocked context and cannot support causal attribution.",
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
                f"Lap window {start}-{end} is not eligible for a qualified shock observation ({detail}). "
                "Its recorded distributions remain visible as blocked context and cannot support causal attribution.",
                None,
            )
        return None, None

    if not eligible_numbers:
        return (
            "No eligible flying laps are available for a qualified shock observation. Recorded shock "
            "distributions remain visible as blocked context and cannot support causal attribution.",
            None,
        )
    return None, eligible_numbers


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


def _corner_setup_values(
    setup_snapshot: SetupSnapshot | None,
    corner: str,
) -> dict[ObservedShockSetting, int | None]:
    return {setting: _setup_value(setup_snapshot, corner, _schema_setting) for setting, _label, _schema_setting in INLINE_SETTINGS}


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
    assert_telemetry_cache_identity(run_id, data_root)
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
    if (lap is not None or lap_window is not None or eligible_lap_numbers is not None) and "lap" not in safe:
        warnings.append(
            "Lap-scoped shock analysis is unavailable because lap identity telemetry is missing; "
            "full-run data was not substituted."
        )
        return {}
    if zone is not None and "lap_dist_pct" not in safe:
        warnings.append(
            "Selected-zone shock analysis is unavailable because lap-position telemetry is missing; full-lap data was not substituted."
        )
        return {}
    if phase_blocker := _phase_filter_blocker(phase, safe):
        warnings.append(phase_blocker)
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


def _phase_filter_blocker(phase: str | None, columns: list[str]) -> str | None:
    if not phase:
        return None
    normalized = phase.strip().lower().replace("-", "_").replace(" ", "_")
    steering_available = "abs_steering_deg" in columns or "steering_deg" in columns
    available = {
        "braking": "brake_pct" in columns,
        "turn_in": steering_available,
        "entry": steering_available,
        "exit": "throttle_pct" in columns,
        "straight": steering_available and "throttle_pct" in columns,
    }
    if normalized not in available:
        return (
            f"Selected shock phase {phase!r} is unsupported; unfiltered data was not substituted."
        )
    if available[normalized]:
        return None
    return (
        f"Selected shock phase {phase!r} is unavailable because its selector telemetry is missing; "
        "unfiltered data was not substituted."
    )


def _apply_phase_filter(frame: Any, pl: Any, phase: str | None, columns: list[str]) -> Any:
    if not phase:
        return frame
    normalized = phase.strip().lower().replace("-", "_").replace(" ", "_")
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
        return {
            "front_contact": front_contact,
            "rear_contact": rear_contact,
            "chatter": chatter,
        }

    observed = observe(data)
    recovery = phase in {"transition", "exit", "entry"} or observed["chatter"]
    return {
        "selected_zone": selected_zone,
        "front_contact": observed["front_contact"],
        "rear_contact": observed["rear_contact"],
        "recovery": recovery,
    }


def _corner_contact(context: dict[str, Any], corner: ShockCornerRead) -> bool:
    return bool(context["front_contact"] if corner.corner in {"LF", "RF"} else context["rear_contact"])


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
        raise ValueError("Shock observation needs both zone_start_pct and zone_end_pct.")
    if not all(math.isfinite(value) for value in (start, end)) or not 0.0 <= start < end <= 100.0:
        raise ValueError("Shock observation zone must satisfy 0 <= start < end <= 100 percent.")
    if end - start > MAX_OBSERVATION_ZONE_WIDTH_PCT:
        raise ValueError(
            f"Shock observation zone must be {MAX_OBSERVATION_ZONE_WIDTH_PCT:.0f}% of a lap or narrower."
        )
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
