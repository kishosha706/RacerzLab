"""Build eligible-lap engineering context without promoting snapshots to live data."""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from racelab_engine.analysis.lap_eligibility import lap_is_eligible
from racelab_engine.analysis.proximity_context import (
    classify_proximity_time_gap_window,
    proximity_time_gap_exposure_fraction,
)
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_engineering_context import (
    ChannelSemantic,
    ChannelUpdateSemantic,
    LapEngineeringContext,
    LapEngineeringContextReport,
    TireCornerEngineeringContext,
    WheelSpeedMismatchContext,
)
from racelab_engine.services.import_service import (
    assert_telemetry_cache_identity,
    default_data_dir,
    read_telemetry_manifest,
    read_telemetry_rows,
)
from racelab_engine.storage.db import default_db_path
from racelab_engine.storage.repository import RaceLabRepository


_BASE_CHANNELS: tuple[str, ...] = (
    "lap", "lap_number", "session_time", "fuel_level", "FuelLevel",
    "air_temp", "AirTemp", "track_temp", "TrackTemp", "wind_vel", "WindVel",
    "wind_dir", "WindDir", "player_tire_compound", "PlayerTireCompound",
    "car_distance_ahead_m", "CarDistAhead", "car_distance_behind_m", "CarDistBehind",
    "speed_mps", "Speed", "speed_mph",
    "rear_wheel_speed_mismatch_raw", "rear_wheel_speed_mismatch_corrected",
)


def mission_lap_context_is_clear(context: object) -> bool:
    """Require complete, explicitly traffic-free context for mission credit."""

    return bool(
        not getattr(context, "blocker_reasons", ())
        and getattr(context, "proximity_state", None)
        == "no_nearby_car_reported"
        and getattr(context, "proximity_coverage_fraction", None) == 1.0
        and getattr(context, "nearby_traffic_exposure_fraction", None) == 0.0
    )


def _tire_channels() -> tuple[str, ...]:
    channels: list[str] = []
    for corner, raw in (("lf", "LF"), ("rf", "RF"), ("lr", "LR"), ("rr", "RR")):
        for suffix, raw_suffix in (
            ("temp_inner", "tempL"), ("temp_middle", "tempM"), ("temp_outer", "tempR"),
            ("carcass_temp_l", "tempCL"), ("carcass_temp_m", "tempCM"),
            ("carcass_temp_r", "tempCR"), ("wear_inner", "wearL"),
            ("wear_middle", "wearM"), ("wear_outer", "wearR"),
        ):
            channels.extend((f"{corner}_{suffix}", f"{raw}{raw_suffix}"))
        channels.extend((f"{corner}_pressure", f"{raw}pressure"))
        channels.extend((f"{corner}_tire_distance_m", f"{raw}odometer"))
    return tuple(channels)


_CONTEXT_CHANNELS = tuple(dict.fromkeys((*_BASE_CHANNELS, *_tire_channels())))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _row_value(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None:
            return value
    return None


def _channel_semantic(
    channel: str,
    rows: Sequence[Mapping[str, Any]],
    *sources: str,
    pit_snapshot: bool = False,
) -> ChannelSemantic:
    names = (channel, *sources)
    values = [_number(_row_value(row, names)) for row in rows]
    finite = [value for value in values if value is not None]
    sample_count = len(rows)
    finite_count = len(finite)
    coverage = finite_count / sample_count if sample_count else 0.0
    distinct = len({round(value, 8) for value in finite})
    common = {
        "channel": channel,
        "source_raw_names": tuple(sources),
        "sample_count": sample_count,
        "finite_sample_count": finite_count,
        "distinct_value_count": distinct,
        "finite_coverage_fraction": coverage,
        "start_value": finite[0] if finite else None,
        "end_value": finite[-1] if finite else None,
        "minimum_value": min(finite) if finite else None,
        "maximum_value": max(finite) if finite else None,
    }
    if not finite:
        return ChannelSemantic(
            **common,
            semantic=ChannelUpdateSemantic.MISSING,
            observation_timing="none",
            health_reason="No finite samples were recorded for this lap.",
        )
    if coverage < 0.9:
        return ChannelSemantic(
            **common,
            semantic=ChannelUpdateSemantic.UNHEALTHY,
            observation_timing="none",
            health_reason="Finite channel coverage is below 90% on this lap.",
        )
    if pit_snapshot:
        return ChannelSemantic(
            **common,
            semantic=ChannelUpdateSemantic.PIT_SNAPSHOT,
            observation_timing="pit_boundary",
        )
    if distinct < 2:
        return ChannelSemantic(
            **common,
            semantic=ChannelUpdateSemantic.CONSTANT,
            observation_timing="session_constant",
        )
    return ChannelSemantic(
        **common,
        semantic=ChannelUpdateSemantic.CONTINUOUS,
        observation_timing="live",
    )


def _corner_context(
    corner: str,
    raw: str,
    rows: Sequence[Mapping[str, Any]],
) -> TireCornerEngineeringContext:
    surface = tuple(
        _channel_semantic(f"{corner}_{suffix}", rows, f"{raw}{raw_suffix}")
        for suffix, raw_suffix in (
            ("temp_inner", "tempL"),
            ("temp_middle", "tempM"),
            ("temp_outer", "tempR"),
        )
    )
    carcass = tuple(
        _channel_semantic(
            f"{corner}_{suffix}", rows, f"{raw}{raw_suffix}", pit_snapshot=True
        )
        for suffix, raw_suffix in (
            ("carcass_temp_l", "tempCL"),
            ("carcass_temp_m", "tempCM"),
            ("carcass_temp_r", "tempCR"),
        )
    )
    wear = tuple(
        _channel_semantic(
            f"{corner}_{suffix}", rows, f"{raw}{raw_suffix}", pit_snapshot=True
        )
        for suffix, raw_suffix in (
            ("wear_inner", "wearL"),
            ("wear_middle", "wearM"),
            ("wear_outer", "wearR"),
        )
    )
    return TireCornerEngineeringContext(
        corner=corner,
        surface_temperatures=surface,
        carcass_temperatures=carcass,
        wear=wear,
        pressure=_channel_semantic(f"{corner}_pressure", rows, f"{raw}pressure"),
        odometer=_channel_semantic(
            f"{corner}_tire_distance_m", rows, f"{raw}odometer"
        ),
    )


def build_lap_engineering_context_report(
    *,
    run_id: str,
    laps: Sequence[LapSummary],
    rows: Sequence[Mapping[str, Any]],
) -> LapEngineeringContextReport:
    eligible = [lap for lap in laps if lap.run_id == run_id and lap_is_eligible(lap)]
    excluded = tuple(sorted(
        lap.lap_number for lap in laps if lap.run_id == run_id and not lap_is_eligible(lap)
    ))
    if not eligible:
        return LapEngineeringContextReport(
            run_id=run_id,
            status="blocked",
            excluded_lap_numbers=excluded,
            blocker_reasons=("No canonical eligible flying lap is available for context.",),
        )
    contexts: list[LapEngineeringContext] = []
    rows_by_lap: dict[int, list[Mapping[str, Any]]] = {}
    for row in rows:
        lap_number = _number(_row_value(row, ("lap", "lap_number")))
        if lap_number is None or not lap_number.is_integer():
            continue
        rows_by_lap.setdefault(int(lap_number), []).append(row)
    for lap in eligible:
        lap_rows = rows_by_lap.get(lap.lap_number, [])
        if not lap_rows:
            continue
        lap_rows.sort(key=lambda row: _number(row.get("session_time")) or 0.0)
        proximity = classify_proximity_time_gap_window(lap_rows)
        corrected = _channel_semantic(
            "rear_wheel_speed_mismatch_corrected", lap_rows
        )
        raw = _channel_semantic("rear_wheel_speed_mismatch_raw", lap_rows)
        if corrected.semantic not in {
            ChannelUpdateSemantic.MISSING,
            ChannelUpdateSemantic.UNHEALTHY,
        }:
            mismatch_authority = "geometry_corrected"
            mismatch_reason = "Yaw-rate and rear-track geometry support the corrected mismatch."
        elif raw.semantic not in {
            ChannelUpdateSemantic.MISSING,
            ChannelUpdateSemantic.UNHEALTHY,
        }:
            mismatch_authority = "geometry_contaminated_proxy"
            mismatch_reason = (
                "Rear track-width geometry is unavailable; raw mismatch remains a yaw- and "
                "geometry-contaminated proxy and cannot be called corrected."
            )
        else:
            mismatch_authority = "unavailable"
            mismatch_reason = "Neither corrected nor raw rear wheel-speed mismatch is usable."
        compound = next(
            (
                str(value)
                for row in lap_rows
                if (value := _row_value(row, ("player_tire_compound", "PlayerTireCompound")))
                is not None
            ),
            None,
        )
        blockers: list[str] = []
        if proximity.state.value == "context_unknown":
            blockers.append("Nearby-car context coverage is incomplete for this lap.")
        contexts.append(LapEngineeringContext(
            run_id=run_id,
            lap_id=lap.lap_id,
            lap_number=lap.lap_number,
            sample_count=len(lap_rows),
            fuel_level=_channel_semantic("fuel_level", lap_rows, "FuelLevel"),
            air_temperature=_channel_semantic("air_temp", lap_rows, "AirTemp"),
            track_temperature=_channel_semantic("track_temp", lap_rows, "TrackTemp"),
            wind_speed=_channel_semantic("wind_vel", lap_rows, "WindVel"),
            wind_direction=_channel_semantic("wind_dir", lap_rows, "WindDir"),
            tire_compound=compound,
            proximity_state=proximity.state.value,
            proximity_coverage_fraction=proximity.coverage_fraction,
            nearby_traffic_exposure_fraction=proximity_time_gap_exposure_fraction(
                lap_rows
            ),
            tire_corners=tuple(
                _corner_context(corner, raw_corner, lap_rows)
                for corner, raw_corner in (
                    ("lf", "LF"), ("rf", "RF"), ("lr", "LR"), ("rr", "RR")
                )
            ),
            rear_wheel_speed_mismatch=WheelSpeedMismatchContext(
                corrected=corrected,
                raw=raw,
                authority=mismatch_authority,
                reason=mismatch_reason,
            ),
            blocker_reasons=tuple(blockers),
        ))
    if not contexts:
        return LapEngineeringContextReport(
            run_id=run_id,
            status="blocked",
            excluded_lap_numbers=excluded,
            blocker_reasons=("Eligible lap telemetry rows are unavailable.",),
        )
    limited = len(contexts) != len(eligible) or any(item.blocker_reasons for item in contexts)
    return LapEngineeringContextReport(
        run_id=run_id,
        status="limited" if limited else "ready",
        contexts=tuple(contexts),
        excluded_lap_numbers=excluded,
        blocker_reasons=(
            ("Some eligible laps have incomplete engineering context.",) if limited else ()
        ),
    )


@lru_cache(maxsize=16)
def _load_cached_lap_engineering_context_report(
    run_id: str,
    database_path: str,
    data_path: str,
    source_file_sha256: str,
    telemetry_cache_sha256: str,
    lap_inventory_sha256: str,
) -> LapEngineeringContextReport:
    del source_file_sha256, telemetry_cache_sha256, lap_inventory_sha256
    overview = RaceLabRepository(database_path).get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    rows = read_telemetry_rows(
        run_id, data_dir=data_path, columns=list(_CONTEXT_CHANNELS)
    )
    return build_lap_engineering_context_report(
        run_id=run_id,
        laps=overview.laps,
        rows=rows,
    )


def load_lap_engineering_context_report(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> LapEngineeringContextReport:
    data_path = default_data_dir().resolve()
    manifest = read_telemetry_manifest(run_id, data_path)
    source_file_sha256 = str(manifest.get("source_file_sha256") or "")
    telemetry_cache_sha256 = str(manifest.get("telemetry_cache_sha256") or "")
    if not source_file_sha256 or not telemetry_cache_sha256:
        raise ValueError(
            "Lap engineering context requires immutable source and cache identities."
        )
    assert_telemetry_cache_identity(run_id, data_path)
    database_path = (
        Path(db_path).resolve()
        if db_path is not None
        else default_db_path().resolve()
    )
    overview = RaceLabRepository(database_path).get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    lap_inventory_sha256 = canonical_json_sha256(
        [lap.model_dump(mode="json") for lap in overview.laps]
    )
    return _load_cached_lap_engineering_context_report(
        run_id,
        str(database_path),
        str(data_path),
        source_file_sha256,
        telemetry_cache_sha256,
        lap_inventory_sha256,
    )


__all__ = [
    "build_lap_engineering_context_report",
    "load_lap_engineering_context_report",
    "mission_lap_context_is_clear",
]
