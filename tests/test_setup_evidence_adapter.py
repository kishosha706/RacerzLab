from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from racelab_engine.io.ibt_types import IBTVariableDefinition
from racelab_engine.knowledge.setup.evidence_adapter import (
    build_run_evidence_context,
    query_setup_for_run_context,
    run_context_result_to_dict,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.import_service import write_channel_metadata, write_telemetry_cache
from racelab_engine.storage.repository import RaceLabRepository


def _configure_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    data_dir = tmp_path / "data"
    db_path = tmp_path / "racelab.sqlite"
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    return data_dir, db_path


def _seed_run(
    tmp_path: Path,
    *,
    run_id: str = "run-1",
    car_name: str = "NASCAR Cup Series Next Gen Chevrolet Camaro ZL1",
    track_name: str = "Charlotte 2025 Oval",
    channels: dict[str, float] | None = None,
    setup_json: dict | None = None,
    extracted_values: dict | None = None,
    useful_laps: int = 3,
    include_setup_snapshot: bool = True,
) -> None:
    data_dir = Path(os.environ["RACELAB_DATA_DIR"])
    db_path = Path(os.environ["RACELAB_DB_PATH"])
    repo = RaceLabRepository(db_path=db_path)
    repo.initialize()

    base_row = {"session_time": 0.0, "lap": 1, "speed_mph": 150.0}
    base_row.update(channels or {})
    write_telemetry_cache(run_id, [base_row], data_dir=data_dir)
    definitions = [
        IBTVariableDefinition(name=name, description=name, unit=None, data_type="float", count=1)
        for name in base_row
    ]
    write_channel_metadata(run_id, definitions, data_dir=data_dir)

    laps = [
        LapSummary(
            lap_id=f"{run_id}:lap:{idx}",
            run_id=run_id,
            lap_number=idx,
            lap_type="timed",
            is_complete=True,
            is_useful=True,
            lap_time=30.0 + idx,
            sample_count=100,
            pct_min=0.0,
            pct_max=100.0,
            pct_span=100.0,
        )
        for idx in range(1, useful_laps + 1)
    ]
    setup_snapshot = None
    if include_setup_snapshot:
        setup_snapshot = SetupSnapshot(
            setup_id=f"{run_id}:setup",
            run_id=run_id,
            setup_name="Baseline",
            setup_json=setup_json or {"Front": {"Tape": "45"}},
            extracted_values=extracted_values or {"cross_weight_percent": 50.0},
        )
    overview = RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            car_name=car_name,
            track_name=track_name,
            track_display_name=track_name,
            track_id_or_path=track_name,
            setup_name="Baseline",
        ),
        laps=laps,
        setup_snapshot=setup_snapshot,
    )
    repo.save_import(overview)


def test_evidence_adapter_detects_setup_snapshot_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path)
    context = build_run_evidence_context("run-1")
    assert context.setup_snapshot_status == "ready"


def test_evidence_adapter_detects_shock_histogram_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 0.9,
            "rr_shock_vel_in_s": 1.2,
        },
    )
    context = build_run_evidence_context("run-1")
    shock_group = next(group for group in context.evidence_groups if group.group_id == "shock_histogram")
    assert shock_group.status == "ready"
    assert "shock_histogram" in context.evidence_flags


def test_shock_histogram_missing_when_only_garage_damper_values_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        setup_json={"Shocks": {"LF": {"Compression": "6", "Rebound": "5"}}},
        extracted_values={"front_brake_bias_percent": 52.0},
    )
    context = build_run_evidence_context("run-1")
    shock_group = next(group for group in context.evidence_groups if group.group_id == "shock_histogram")
    assert shock_group.status == "missing"
    assert any("Garage damper settings exist" in note for note in shock_group.notes)


def test_diffuser_proxy_ready_when_diffuser_channels_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "front_center_rh_in": 1.9,
            "rear_center_rh_in": 2.6,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
        },
    )
    context = build_run_evidence_context("run-1")
    diffuser_group = next(group for group in context.evidence_groups if group.group_id == "diffuser_proxy")
    assert diffuser_group.status == "ready"


def test_platform_trace_ready_when_front_and_rear_ride_heights_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "cfs_ride_height_in": 1.5,
            "lf_ride_height_in": 2.0,
            "rf_ride_height_in": 2.1,
            "lr_ride_height_in": 3.0,
            "rr_ride_height_in": 2.9,
        },
    )
    context = build_run_evidence_context("run-1")
    platform_group = next(group for group in context.evidence_groups if group.group_id == "platform_trace")
    assert platform_group.status == "ready"


def test_tire_temps_ready_when_tire_temp_channels_exist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "lf_tire_temp_inner": 180.0,
            "lf_tire_temp_middle": 185.0,
            "rf_tire_temp_inner": 195.0,
            "rf_tire_temp_middle": 200.0,
        },
    )
    context = build_run_evidence_context("run-1")
    tire_group = next(group for group in context.evidence_groups if group.group_id == "tire_temps")
    assert tire_group.status == "ready"


def test_next_gen_car_family_detected_from_next_gen_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, car_name="stockcars chevycamarozl12022")
    context = build_run_evidence_context("run-1")
    assert context.car_family == "next_gen"


def test_unknown_car_stays_unknown_if_resolver_is_unsure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, car_name="Mystery Prototype Car")
    context = build_run_evidence_context("run-1")
    assert context.car_family == "unknown"


def test_next_gen_run_context_query_never_returns_legacy_areas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "cfs_ride_height_in": 1.5,
            "lf_ride_height_in": 2.0,
            "rf_ride_height_in": 2.1,
            "lr_ride_height_in": 3.0,
            "rr_ride_height_in": 2.9,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
        },
    )
    result = query_setup_for_run_context("run-1", "tight center", limit=20)
    assert {item.effect.setup_area for item in result.setup_query.candidate_effects}.isdisjoint({"track_bar", "truck_arm_mount", "bump_stop", "packer"})


def test_unknown_car_run_context_query_never_returns_legacy_areas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        car_name="Mystery Prototype Car",
        channels={
            "cfs_ride_height_in": 1.5,
            "lf_ride_height_in": 2.0,
            "rf_ride_height_in": 2.1,
            "lr_ride_height_in": 3.0,
            "rr_ride_height_in": 2.9,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
        },
    )
    result = query_setup_for_run_context("run-1", "tight center", limit=20)
    assert {item.effect.setup_area for item in result.setup_query.candidate_effects}.isdisjoint({"track_bar", "truck_arm_mount", "bump_stop", "packer"})


def test_shock_effects_show_missing_key_evidence_without_shock_histogram(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "throttle_pct": 100.0,
            "yaw_rate": 1.1,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.4,
            "cfs_ride_height_in": 1.6,
            "lr_ride_height_in": 2.8,
            "rr_ride_height_in": 2.7,
        },
    )
    result = query_setup_for_run_context("run-1", "loose off", limit=12)
    shock_candidates = [item for item in result.setup_query.candidate_effects if item.effect.setup_area == "ls_rebound"]
    assert shock_candidates
    assert all(item.readiness == "missing_key_evidence" for item in shock_candidates)


def test_platform_effects_show_missing_key_evidence_without_platform_trace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "speed_mph": 185.0,
            "throttle_pct": 99.0,
            "yaw_rate": 1.0,
            "rr_shock_vel_in_s": 0.5,
        },
    )
    result = query_setup_for_run_context("run-1", "rear scrape", limit=12)
    platform_candidates = [
        item
        for item in result.setup_query.candidate_effects
        if item.effect.setup_area in {"rear_ride_height_platform", "diffuser_platform", "ride_height"}
    ]
    assert platform_candidates
    assert all(item.readiness == "missing_key_evidence" for item in platform_candidates)


def test_cli_json_returns_stable_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir, db_path = _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "cfs_ride_height_in": 1.5,
            "lf_ride_height_in": 2.0,
            "rf_ride_height_in": 2.1,
            "lr_ride_height_in": 3.0,
            "rr_ride_height_in": 2.9,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
        },
    )
    env = os.environ.copy()
    env["RACELAB_DATA_DIR"] = str(data_dir)
    env["RACELAB_DB_PATH"] = str(db_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/query_setup_with_run_context.py",
            "--run-id",
            "run-1",
            "--symptom",
            "loose off",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(completed.stdout)
    assert {"run_id", "car_family", "track_family", "evidence_flags", "evidence_groups", "parsed_symptom", "candidates", "candidate_readiness"}.issubset(payload)


def test_cli_show_evidence_outputs_present_missing_and_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir, db_path = _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "smooth_center_rake_in": 0.6,
            "diffuser_volume_ft3": 11.5,
        },
    )
    env = os.environ.copy()
    env["RACELAB_DATA_DIR"] = str(data_dir)
    env["RACELAB_DB_PATH"] = str(db_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/query_setup_with_run_context.py",
            "--run-id",
            "run-1",
            "--symptom",
            "loose off",
            "--show-evidence",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "evidence_flags:" in completed.stdout
    assert "present:" in completed.stdout
    assert "notes:" in completed.stdout


def test_query_with_run_context_returns_parsed_symptom_and_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "cfs_ride_height_in": 1.5,
            "lf_ride_height_in": 2.0,
            "rf_ride_height_in": 2.1,
            "lr_ride_height_in": 3.0,
            "rr_ride_height_in": 2.9,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
        },
    )
    result = query_setup_for_run_context("run-1", "loose off", limit=5)
    payload = run_context_result_to_dict(result)
    assert payload["parsed_symptom"]["canonical_symptom"] == "loose_exit"
    assert payload["candidates"]


def test_diffuser_proxy_warning_uses_derived_proxy_language(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "front_center_rh_in": 1.9,
            "rear_center_rh_in": 2.6,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
        },
    )
    context = build_run_evidence_context("run-1")
    diffuser_group = next(group for group in context.evidence_groups if group.group_id == "diffuser_proxy")
    combined = " ".join([*context.warnings, *diffuser_group.notes]).lower()
    assert "measured downforce" in combined
    assert "not measured downforce" in combined


def test_adapter_uses_channel_summary_path_without_row_materialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "cfs_ride_height_in": 1.5,
            "lf_ride_height_in": 2.0,
            "rf_ride_height_in": 2.1,
            "lr_ride_height_in": 3.0,
            "rr_ride_height_in": 2.9,
        },
    )
    import racelab_engine.services.import_service as import_service

    def _boom(*args, **kwargs):
        raise AssertionError("read_telemetry_rows should not be used for evidence adapter metadata path")

    monkeypatch.setattr(import_service, "read_telemetry_rows", _boom)
    context = build_run_evidence_context("run-1")
    assert context.run_id == "run-1"
