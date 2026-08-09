from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.routes_runs import get_run_or_404, repository
from racelab_engine.analysis.braking_efficiency import (
    BrakingEfficiencyReport,
    analyze_braking_efficiency,
)
from racelab_engine.analysis.damper_response import DamperResponseReport, analyze_damper_response
from racelab_engine.analysis.p3_contracts import (
    BRAKING_EFFICIENCY_CONTRACT,
    DAMPER_RESPONSE_CONTRACT,
    TIRE_STATE_CONTRACT,
    POWERTRAIN_GEARING_CONTRACT,
    STINT_STRATEGY_CONTRACT,
)
from racelab_engine.analysis.evidence_contracts import RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.p3_common import finite
from racelab_engine.analysis.powertrain_gearing import PowertrainGearingReport, analyze_powertrain_gearing
from racelab_engine.analysis.relative_resistance import RelativeResistanceReport, analyze_relative_resistance_aba
from racelab_engine.analysis.setup_diff import (
    diff_setups,
    setup_controls_comparable,
    unmapped_setup_change_paths,
)
from racelab_engine.analysis.sim_integrity import SimIntegrityCertificate, build_sim_integrity_certificate
from racelab_engine.analysis.tire_state_energy import TireStateReport, analyze_tire_state
from racelab_engine.analysis.stint_strategy import StintStrategyReport, analyze_stint_strategy
from racelab_engine.services.import_service import read_telemetry_manifest, read_telemetry_rows


router = APIRouter(prefix="/api/runs", tags=["p3-engineering"])

_INTEGRITY_CHANNELS = [
    "session_tick", "session_time", "frame_rate", "cpu_usage_foreground",
    "cpu_usage_background", "gpu_usage", "memory_page_faults_per_s",
    "memory_soft_page_faults_per_s", "channel_latency_s",
    "channel_average_latency_s", "channel_quality",
    "SessionTick", "SessionTime", "FrameRate", "CpuUsageFG", "CpuUsageBG",
    "GpuUsage", "MemPageFaultSec", "MemSoftPageFaultSec", "ChanLatency",
    "ChanAvgLatency", "ChanQuality",
]


class RelativeResistanceABARequest(BaseModel):
    a1_run_id: str
    b_run_id: str
    a2_run_id: str
    a1_lap: int | None = None
    b_lap: int | None = None
    a2_lap: int | None = None


_ABA_IDENTITY_FIELDS = {
    "driver_user_id": "driver identity",
    "car_id": "car ID",
    "car_path": "car path",
    "car_version": "car version",
    "track_id": "track ID",
    "track_configuration_name": "track configuration",
    "track_version": "track version",
    "iracing_build_version": "simulator build",
    "session_type": "session type",
}


_DAMPER_CORNER_TOKENS = frozenset({
    "lf", "rf", "lr", "rr", "leftfront", "rightfront", "leftrear", "rightrear",
})
_DAMPER_SETTING_KEYS = frozenset({
    "lscompression", "lscomp", "hscompression", "hscomp",
    "hscompslope", "hscompressionslope", "compressionslope",
    "lsrebound", "lsreb", "hsrebound", "hsreb",
    "hsrebslope", "hsreboundslope", "reboundslope",
    "compressionclick", "compressionclicks", "bumpclick", "bumpclicks",
    "reboundclick", "reboundclicks",
})


def _compact_setup_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _identifies_damper_corner(path_part: str) -> bool:
    if path_part in _DAMPER_CORNER_TOKENS:
        return True
    return any(
        path_part in {f"{corner}shock", f"{corner}damper"}
        for corner in _DAMPER_CORNER_TOKENS
    )


def _has_corner_damper_setting(value: Any, path: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        return any(
            _has_corner_damper_setting(child, (*path, str(key)))
            for key, child in value.items()
        )
    if isinstance(value, bool) or not isinstance(value, (int, float, str)) or str(value).strip() == "":
        return False
    compact_path = tuple(_compact_setup_key(part) for part in path)
    identifies_corner = any(_identifies_damper_corner(part) for part in compact_path)
    identifies_setting = bool(compact_path) and compact_path[-1] in _DAMPER_SETTING_KEYS
    return identifies_corner and identifies_setting


def _assert_aba_compatibility(run_ids: tuple[str, str, str]) -> None:
    identities = [
        read_telemetry_manifest(run_id).get("compatibility_identity") or {}
        for run_id in run_ids
    ]
    missing = [
        label for key, label in _ABA_IDENTITY_FIELDS.items()
        if any(identity.get(key) is None for identity in identities)
    ]
    if missing:
        raise HTTPException(
            409,
            "A/B/A resistance requires complete three-run compatibility identity; missing "
            + ", ".join(missing) + ".",
        )
    mismatches = [
        label for key, label in _ABA_IDENTITY_FIELDS.items()
        if len({str(identity.get(key)) for identity in identities}) != 1
    ]
    if mismatches:
        raise HTTPException(
            400,
            "A/B/A runs are not compatible for setup attribution; mismatched "
            + ", ".join(mismatches) + ".",
        )


def _aba_setup_change_isolated(setups: list[object]) -> bool:
    a1_b = diff_setups(setups[0], setups[1])
    a1_a2 = diff_setups(setups[0], setups[2])
    return bool(
        all(
            setup_controls_comparable(left, right)
            for left, right in ((setups[0], setups[1]), (setups[0], setups[2]))
        )
        and len(a1_b) == 1
        and len(a1_a2) == 0
        and not unmapped_setup_change_paths(setups[0], setups[1], a1_b)
        and not unmapped_setup_change_paths(setups[0], setups[2], a1_a2)
    )


def _selected_lap(run_id: str, requested: int | None) -> tuple[object, int]:
    overview = get_run_or_404(run_id)
    lap = requested if requested is not None else (
        overview.best_useful_lap.lap_number if overview.best_useful_lap is not None else None
    )
    if lap is None:
        raise HTTPException(status_code=409, detail="No eligible flying lap is available.")
    return overview, lap


def _rows(run_id: str, contract, extra: list[str]) -> list[dict]:
    columns = sorted(contract.required_channels | contract.preferred_channels | {"lap", *extra})
    return read_telemetry_rows(run_id, columns=columns)


_SERVER_REDLINE_KEYS = {
    "engineredline", "engineredlinerpm", "redline", "redlinerpm",
    "revlimit", "revlimiter", "revlimitrpm", "rpmlimit", "rpmredline",
}


def _server_setup_redline_rpm(setup: object | None) -> float | None:
    """Extract a limiter only from the persisted setup; client values never authorize action."""
    if setup is None:
        return None
    payload = setup.model_dump() if hasattr(setup, "model_dump") else setup
    candidates: list[float] = []

    def visit(value: Any, key: str = "") -> None:
        normalized = re.sub(r"[^a-z0-9]", "", key.lower())
        if normalized in _SERVER_REDLINE_KEYS:
            match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
            number = finite(match.group(0)) if match else None
            if number is not None and 500.0 <= number <= 30_000.0:
                candidates.append(number)
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child, key)

    visit(payload)
    return candidates[0] if candidates and len(set(candidates)) == 1 else None


def _manifest_grade_source_healthy(manifest: dict[str, Any]) -> bool:
    """Require file-declared, cached, varying meter channels before grade control."""
    channels = manifest.get("channels")
    if not isinstance(channels, list):
        return False
    expected_records = manifest.get("record_count")
    by_canonical = {
        channel.get("canonical_name"): channel
        for channel in channels if isinstance(channel, dict)
    }
    for canonical in ("alt", "lap_dist_m"):
        channel = by_canonical.get(canonical)
        if not isinstance(channel, dict):
            return False
        unit = str(channel.get("unit") or "").strip().lower()
        if unit not in {"m", "meter", "meters", "metre", "metres"}:
            return False
        if (
            channel.get("provenance") != "ibt_variable_definition"
            or channel.get("archive_status") != "cached"
            or channel.get("health_status") != "healthy"
            or channel.get("variation") != "varying"
            or expected_records is None
            or channel.get("valid_record_count") != expected_records
        ):
            return False
    return True


def _certificate(rows: list[dict], telemetry_rate_hz: float | None) -> SimIntegrityCertificate:
    return build_sim_integrity_certificate(rows, expected_sample_rate_hz=telemetry_rate_hz)


def _cohort_integrity(
    rows: list[dict],
    laps: list,
    telemetry_rate_hz: float | None,
) -> tuple[bool | None, float]:
    certificates = [
        _certificate(
            [row for row in rows if row.get("lap") == lap.lap_number],
            telemetry_rate_hz,
        )
        for lap in eligible_laps(laps)
    ]
    if not certificates or any(item.is_clear_for_analysis is None for item in certificates):
        return None, min((item.confidence_cap for item in certificates), default=0.35)
    if any(item.is_clear_for_analysis is False for item in certificates):
        return False, min(item.confidence_cap for item in certificates)
    return True, min(item.confidence_cap for item in certificates)


@router.get("/{run_id}/sim-integrity", response_model=SimIntegrityCertificate)
def get_sim_integrity(run_id: str, lap: int | None = None) -> SimIntegrityCertificate:
    overview, selected = _selected_lap(run_id, lap)
    rows = read_telemetry_rows(run_id, lap=selected, columns=["lap", *_INTEGRITY_CHANNELS])
    return _certificate(rows, overview.session.telemetry_rate_hz)


@router.get("/{run_id}/braking-efficiency", response_model=BrakingEfficiencyReport)
def get_braking_efficiency(run_id: str, lap: int | None = None) -> BrakingEfficiencyReport:
    overview, selected = _selected_lap(run_id, lap)
    rows = _rows(run_id, BRAKING_EFFICIENCY_CONTRACT, _INTEGRITY_CHANNELS)
    cohort_clear, cohort_cap = _cohort_integrity(rows, overview.laps, overview.session.telemetry_rate_hz)
    return analyze_braking_efficiency(
        rows,
        overview.laps,
        selected_lap=selected,
        sim_integrity_clear=cohort_clear,
        sim_integrity_confidence_cap=cohort_cap,
    )


@router.get("/{run_id}/tire-state", response_model=TireStateReport)
def get_tire_state(run_id: str, lap: int | None = None) -> TireStateReport:
    overview, selected = _selected_lap(run_id, lap)
    rows = _rows(run_id, TIRE_STATE_CONTRACT, _INTEGRITY_CHANNELS)
    cohort_clear, cohort_cap = _cohort_integrity(rows, overview.laps, overview.session.telemetry_rate_hz)
    return analyze_tire_state(
        rows,
        overview.laps,
        selected_lap=selected,
        sim_integrity_clear=cohort_clear,
        sim_integrity_confidence_cap=cohort_cap,
    )


@router.get("/{run_id}/damper-response", response_model=DamperResponseReport)
def get_damper_response(run_id: str, lap: int | None = None) -> DamperResponseReport:
    overview, selected = _selected_lap(run_id, lap)
    rows = _rows(run_id, DAMPER_RESPONSE_CONTRACT, _INTEGRITY_CHANNELS)
    cohort_clear, cohort_cap = _cohort_integrity(rows, overview.laps, overview.session.telemetry_rate_hz)
    setup = repository().get_setup_snapshot(run_id)
    setup_captured = bool(
        setup is not None
        and _has_corner_damper_setting(setup.model_dump())
    )
    return analyze_damper_response(
        rows,
        overview.laps,
        run_id=run_id,
        selected_lap=selected,
        sim_integrity_clear=cohort_clear,
        sim_integrity_confidence_cap=cohort_cap,
        setup_snapshot_captured=setup_captured,
    )


@router.get("/{run_id}/powertrain-gearing", response_model=PowertrainGearingReport)
def get_powertrain_gearing(
    run_id: str,
    lap: int | None = None,
    redline_rpm: float | None = None,
) -> PowertrainGearingReport:
    if redline_rpm is not None:
        raise HTTPException(
            422,
            "Client redline_rpm cannot authorize a gearing action; capture the limiter in the persisted setup.",
        )
    overview, selected = _selected_lap(run_id, lap)
    rows = _rows(run_id, POWERTRAIN_GEARING_CONTRACT, _INTEGRITY_CHANNELS)
    cohort_clear, cohort_cap = _cohort_integrity(rows, overview.laps, overview.session.telemetry_rate_hz)
    server_redline_rpm = _server_setup_redline_rpm(repository().get_setup_snapshot(run_id))
    return analyze_powertrain_gearing(
        rows,
        overview.laps,
        selected_lap=selected,
        sim_integrity_clear=cohort_clear,
        sim_integrity_confidence_cap=cohort_cap,
        redline_rpm=server_redline_rpm,
    )


@router.get("/{run_id}/stint-strategy", response_model=StintStrategyReport)
def get_stint_strategy(run_id: str) -> StintStrategyReport:
    overview = get_run_or_404(run_id)
    rows = _rows(run_id, STINT_STRATEGY_CONTRACT, _INTEGRITY_CHANNELS)
    cohort_clear, cohort_cap = _cohort_integrity(rows, overview.laps, overview.session.telemetry_rate_hz)
    return analyze_stint_strategy(
        rows,
        overview.laps,
        sim_integrity_clear=cohort_clear,
        sim_integrity_confidence_cap=cohort_cap,
        session_type=overview.session.session_type,
    )


@router.post("/relative-resistance/aba", response_model=RelativeResistanceReport)
def compare_relative_resistance_aba(request: RelativeResistanceABARequest) -> RelativeResistanceReport:
    run_ids = (request.a1_run_id, request.b_run_id, request.a2_run_id)
    _assert_aba_compatibility(run_ids)
    manifests = [read_telemetry_manifest(run_id) for run_id in run_ids]
    requested_laps = (request.a1_lap, request.b_lap, request.a2_lap)
    resolved = [_selected_lap(run_id, lap) for run_id, lap in zip(run_ids, requested_laps)]
    columns = sorted(
        RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT.required_channels
        | RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT.preferred_channels
        | {"lap", "lf_slip_ratio", "rf_slip_ratio", "lr_slip_ratio", "rr_slip_ratio",
           "lf_brake_line_pressure_bar", "rf_brake_line_pressure_bar",
           "lr_brake_line_pressure_bar", "rr_brake_line_pressure_bar", *_INTEGRITY_CHANNELS}
    )
    row_sets = [read_telemetry_rows(run_id, columns=columns) for run_id in run_ids]
    certificates = [
        _certificate(
            [row for row in rows if row.get("lap") == selected],
            overview.session.telemetry_rate_hz,
        )
        for rows, (overview, selected) in zip(row_sets, resolved)
    ]
    setups = [repository().get_setup_snapshot(run_id) for run_id in run_ids]
    isolated = _aba_setup_change_isolated(setups)
    return analyze_relative_resistance_aba(
        row_sets[0], row_sets[1], row_sets[2],
        lap_summaries=(resolved[0][0].laps, resolved[1][0].laps, resolved[2][0].laps),
        selected_laps=(resolved[0][1], resolved[1][1], resolved[2][1]),
        sim_integrity_clear=tuple(item.is_clear_for_analysis for item in certificates),  # type: ignore[arg-type]
        sim_integrity_confidence_caps=tuple(item.confidence_cap for item in certificates),  # type: ignore[arg-type]
        isolated_single_change=isolated,
        grade_source_declared_healthy=all(
            _manifest_grade_source_healthy(manifest) for manifest in manifests
        ),
        grade_map_identity_matched=True,
    )


__all__ = ["RelativeResistanceABARequest", "router"]
