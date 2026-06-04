from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any, Iterable

from racelab_engine.analysis.shock_reader_schema import (
    ShockCornerRead,
    ShockReaderResponse,
    ShockRecommendation,
    ShockSetting,
)
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import default_data_dir, parquet_path


SHOCK_CORNERS = ("LF", "RF", "LR", "RR")
DEFAULT_BOUNDARY_IN_S = 1.0
DEFAULT_BIN_WIDTH_IN_S = 0.5
MIN_SAMPLE_COUNT = 20
SETUP_MIN = 1
SETUP_MAX = 10

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
    "ls_rebound": "LS rebound",
    "hs_compression": "HS bump",
    "hs_rebound": "HS rebound",
    "compression_slope": "compression slope",
    "rebound_slope": "rebound slope",
}

SETUP_KEY_CANDIDATES: dict[ShockSetting, tuple[str, ...]] = {
    "ls_compression": ("ls_compression", "ls_comp"),
    "hs_compression": ("hs_compression", "hs_comp"),
    "ls_rebound": ("ls_rebound", "ls_reb"),
    "hs_rebound": ("hs_rebound", "hs_reb"),
    "compression_slope": ("compression_slope", "hs_comp_slope", "hs_compression_slope"),
    "rebound_slope": ("rebound_slope", "hs_reb_slope", "hs_rebound_slope"),
}


def build_shock_reader_response(
    run_id: str,
    *,
    lap: int | None = None,
    lap_window: tuple[int, int] | None = None,
    phase: str | None = None,
    boundary_in_s: float = DEFAULT_BOUNDARY_IN_S,
    include_debug: bool = False,
    setup_snapshot: SetupSnapshot | None = None,
    data_dir: str | Path | None = None,
) -> ShockReaderResponse:
    warnings: list[str] = []
    boundary = boundary_in_s if math.isfinite(boundary_in_s) and boundary_in_s > 0 else DEFAULT_BOUNDARY_IN_S
    data = _read_shock_reader_columns(
        run_id,
        lap=lap,
        lap_window=lap_window,
        phase=phase,
        data_dir=data_dir,
        warnings=warnings,
    )
    if not data:
        return ShockReaderResponse(
            run_id=run_id,
            lap_window=_format_lap_window(lap=lap, lap_window=lap_window),
            phase=phase,
            boundary_in_s=boundary,
            bin_width_in_s=DEFAULT_BIN_WIDTH_IN_S,
            setup_snapshot_available=setup_snapshot is not None,
            corners=[],
            recommendations=[],
            warnings=[*warnings, "Shock telemetry unavailable for this run/window."],
        )

    corners = [
        compute_corner_read(corner, data.get(VELOCITY_CHANNELS[corner], []), data, boundary)
        for corner in SHOCK_CORNERS
    ]
    context = _build_context(data, phase=phase, selected_zone=_has_selected_zone(lap, lap_window, phase))
    corners = _apply_context_patterns(corners, context)
    recommendations = _build_recommendations(
        corners,
        context,
        setup_snapshot=setup_snapshot,
        include_debug=include_debug,
    )
    if all(corner.pattern == "insufficient_evidence" for corner in corners):
        warnings.append("Shock velocity channels are missing or too sparse for guarded recommendations.")

    return ShockReaderResponse(
        run_id=run_id,
        lap_window=_format_lap_window(lap=lap, lap_window=lap_window),
        phase=phase,
        boundary_in_s=boundary,
        bin_width_in_s=DEFAULT_BIN_WIDTH_IN_S,
        setup_snapshot_available=setup_snapshot is not None,
        corners=corners,
        recommendations=recommendations,
        warnings=warnings,
    )


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
    rebound_hi = [value for value in samples if value < -boundary]
    rebound_lo = [value for value in samples if -boundary <= value < 0]
    bump_lo = [value for value in samples if 0 <= value <= boundary]
    bump_hi = [value for value in samples if value > boundary]
    total = len(samples)
    read = {
        "rebound_hi_pct": _pct(len(rebound_hi), total),
        "rebound_lo_pct": _pct(len(rebound_lo), total),
        "bump_lo_pct": _pct(len(bump_lo), total),
        "bump_hi_pct": _pct(len(bump_hi), total),
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
        center_pct=_pct(sum(1 for value in samples if abs(value) < 0.05), total),
        rms_in_s=rms,
        activity_index=activity,
        deflection_delta_range_in=deflection_range,
        pattern=pattern,
        confidence=confidence,
    )


def classify_corner_pattern(
    rebound_hi_pct: float,
    rebound_lo_pct: float,
    bump_lo_pct: float,
    bump_hi_pct: float,
    rms_in_s: float | None,
    activity_index: float | None,
) -> tuple[str, str]:
    low_delta = bump_lo_pct - rebound_lo_pct
    high_delta = bump_hi_pct - rebound_hi_pct
    high_total = bump_hi_pct + rebound_hi_pct
    active = max(rms_in_s or 0.0, activity_index or 0.0)

    if high_total >= 38 and bump_hi_pct >= 10 and rebound_hi_pct >= 10 and active >= 1.6:
        return "excessive_high_speed_shoulders", "medium"
    if high_delta >= 12 and bump_hi_pct >= 18:
        return "high_speed_bump_heavy", "medium"
    if high_delta <= -12 and rebound_hi_pct >= 18:
        return "high_speed_rebound_heavy", "medium"
    if low_delta >= 12 and bump_lo_pct >= 18:
        return "low_speed_bump_heavy", "medium"
    if low_delta <= -12 and rebound_lo_pct >= 18:
        return "low_speed_rebound_heavy", "medium"
    if abs(low_delta) <= 8 and abs(high_delta) <= 8 and high_total < 32:
        return "balanced", "high"
    return "balanced", "medium"


def _build_recommendations(
    corners: list[ShockCornerRead],
    context: dict[str, Any],
    *,
    setup_snapshot: SetupSnapshot | None,
    include_debug: bool,
) -> list[ShockRecommendation]:
    usable = [corner for corner in corners if corner.pattern != "insufficient_evidence"]
    if not usable:
        return []

    contact_corners = [
        corner
        for corner in usable
        if corner.pattern in {"high_speed_bump_heavy", "impact_contact_driven"} and context["contact"]
    ]
    if contact_corners:
        corner = max(contact_corners, key=lambda item: item.bump_hi_pct)
        if context["slope_allowed"] and _setting_available(setup_snapshot, corner.corner, "compression_slope"):
            return [_recommend(corner, "compression_slope", "move_more_linear", 1, "package_swing", context, setup_snapshot, include_debug)]
        return [_recommend(corner, "hs_compression", "add", 1, "balance_swing", context, setup_snapshot, include_debug)]

    shoulder_corners = [corner for corner in usable if corner.pattern == "excessive_high_speed_shoulders"]
    if shoulder_corners and not context["contact"]:
        corner = max(shoulder_corners, key=lambda item: (item.bump_hi_pct + item.rebound_hi_pct))
        if context["slope_allowed"] and context["chatter"] and _setting_available(setup_snapshot, corner.corner, "compression_slope"):
            return [_recommend(corner, "compression_slope", "move_more_digressive", -1, "package_swing", context, setup_snapshot, include_debug)]
        setting: ShockSetting = "hs_compression" if corner.bump_hi_pct >= corner.rebound_hi_pct else "hs_rebound"
        return [_recommend(corner, setting, "subtract", -1, "balance_swing", context, setup_snapshot, include_debug)]

    rebound_corners = [
        corner
        for corner in usable
        if corner.pattern in {"high_speed_rebound_heavy", "oscillation_recovery_issue"}
    ]
    if rebound_corners and context["recovery"]:
        corner = max(rebound_corners, key=lambda item: item.rebound_hi_pct)
        direction = -1 if context["packed"] else 1
        semantic = "subtract" if direction < 0 else "add"
        return [_recommend(corner, "hs_rebound", semantic, direction, "balance_swing", context, setup_snapshot, include_debug)]

    low_bump = [corner for corner in usable if corner.pattern == "low_speed_bump_heavy"]
    if low_bump:
        corner = max(low_bump, key=lambda item: item.bump_lo_pct - item.rebound_lo_pct)
        return [_recommend(corner, "ls_compression", "subtract", -1, "fine_tune", context, setup_snapshot, include_debug)]

    low_rebound = [corner for corner in usable if corner.pattern == "low_speed_rebound_heavy"]
    if low_rebound:
        corner = max(low_rebound, key=lambda item: item.rebound_lo_pct - item.bump_lo_pct)
        return [_recommend(corner, "ls_rebound", "subtract", -1, "fine_tune", context, setup_snapshot, include_debug)]

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


def _apply_context_patterns(corners: list[ShockCornerRead], context: dict[str, Any]) -> list[ShockCornerRead]:
    updated: list[ShockCornerRead] = []
    for corner in corners:
        if corner.pattern == "high_speed_bump_heavy" and context["contact"]:
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
    data_dir: str | Path | None,
    warnings: list[str],
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
    if not any(channel in safe for channel in VELOCITY_CHANNELS.values()):
        return {}

    frame = pl.scan_parquet(path).select(safe)
    if lap is not None and "lap" in safe:
        frame = frame.filter(pl.col("lap") == int(lap))
    elif lap_window is not None and "lap" in safe:
        start, end = lap_window
        frame = frame.filter((pl.col("lap") >= int(start)) & (pl.col("lap") <= int(end)))
    frame = _apply_phase_filter(frame, pl, phase, safe)
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
    if expr is None:
        return frame
    return frame.filter(expr)


def _build_context(data: dict[str, list[Any]], *, phase: str | None, selected_zone: bool) -> dict[str, Any]:
    rear_margin = _min(_numeric_series(data, "rear_scrape_margin_mm"))
    rear_scrape = _max(_numeric_series(data, "rear_scrape_risk_score"))
    rear_contact = _max(_numeric_series(data, "rear_platform_contact_risk"))
    cfs_in = _min(_numeric_series(data, "cfs_ride_height_in"))
    cfs_mm = _min(_numeric_series(data, "cfs_ride_height_mm"))
    contact = any(
        value is not None and value > threshold
        for value, threshold in [(rear_scrape, 0.45), (rear_contact, 0.45)]
    ) or (rear_margin is not None and rear_margin <= 0.0) or (cfs_in is not None and cfs_in <= 0.12) or (cfs_mm is not None and cfs_mm <= 3.0)
    global_activity = _mean(_numeric_series(data, "shock_activity_index"))
    damper_energy = _mean(_numeric_series(data, "damper_energy_proxy"))
    chatter = bool(not contact and ((global_activity or 0.0) >= 1.4 or (damper_energy or 0.0) >= 1.4))
    recovery = phase in {"transition", "exit", "entry"} or chatter
    packed = contact or bool(_max(_numeric_series(data, "platform_compression_index")) and (_max(_numeric_series(data, "platform_compression_index")) or 0) > 0.65)
    return {
        "selected_zone": selected_zone,
        "phase": phase,
        "contact": contact,
        "platform_trace": any(name in data for name in ("cfs_ride_height_in", "rear_scrape_margin_mm", "rear_platform_contact_risk", "front_center_rh_in", "rear_center_rh_in")),
        "chatter": chatter,
        "recovery": recovery,
        "packed": packed,
        "slope_allowed": selected_zone and (contact or chatter) and any(name in data for name in ("cfs_ride_height_in", "rear_scrape_margin_mm", "rear_platform_contact_risk", "front_center_rh_in", "rear_center_rh_in")),
    }


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
    if current is None or current < SETUP_MIN or current > SETUP_MAX:
        return None, None, False
    suggested = current + step
    if suggested < SETUP_MIN or suggested > SETUP_MAX:
        return None, None, True
    return step, suggested, False


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


def _recommendation_confidence(corner: ShockCornerRead, context: dict[str, Any]) -> str:
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
        f"RLo {corner.rebound_lo_pct:.1f}%, BLo {corner.bump_lo_pct:.1f}%, BHi {corner.bump_hi_pct:.1f}%{suffix}."
    )


def _format_lap_window(*, lap: int | None, lap_window: tuple[int, int] | None) -> str | None:
    if lap is not None:
        return str(lap)
    if lap_window is None:
        return None
    return f"{lap_window[0]}-{lap_window[1]}"


def _has_selected_zone(lap: int | None, lap_window: tuple[int, int] | None, phase: str | None) -> bool:
    return lap is not None or lap_window is not None or bool(phase)


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
    if not clean:
        return None
    return sum(clean) / len(clean)


def _min(values: Iterable[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    return min(clean) if clean else None


def _max(values: Iterable[float]) -> float | None:
    clean = [value for value in values if math.isfinite(value)]
    return max(clean) if clean else None


def _pct(count: int, total: int) -> float:
    return (count / total) * 100.0 if total else 0.0


def _deflection_range(data: dict[str, list[Any]], corner: str) -> float | None:
    for channel in DEFLECTION_DELTA_CHANNELS[corner]:
        values = _numeric_series(data, channel)
        if values:
            return max(values) - min(values)
    return None
