from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from racelab_engine.knowledge.setup.dial_in_service import build_dial_in_response
from test_setup_evidence_adapter import _configure_env, _seed_run


def test_loose_off_returns_interpreted_loose_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    assert response.interpreted_symptom == "loose_exit"


def test_tight_center_returns_interpreted_tight_center(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "tight center")
    assert response.interpreted_symptom == "tight_center"


def test_generic_loose_returns_clarification_needed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path)
    response = build_dial_in_response("run-1", "loose")
    assert response.clarification.needed is True
    assert response.clarification.question == "Where is it happening?"
    assert response.clarification.options == ["Entry", "Center", "Exit", "Whole corner", "On brake", "On throttle"]
    assert response.top_swings == []


def test_generic_tight_returns_clarification_needed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path)
    response = build_dial_in_response("run-1", "tight")
    assert response.clarification.needed is True
    assert response.clarification.question == "Where is it happening?"
    assert response.top_swings == []


def test_default_response_hides_raw_evidence_group_spam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"front_center_rh_in": 1.8, "rear_center_rh_in": 2.5})
    response = build_dial_in_response("run-1", "loose off")
    payload = response.model_dump(exclude_none=True)
    dumped = json.dumps(payload)
    assert "hidden_evidence_summary" not in payload
    assert "front_center_rh_in" not in dumped
    assert "evidence_groups" not in dumped


def test_debug_response_includes_hidden_evidence_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off", include_debug_evidence=True)
    assert response.hidden_evidence_summary is not None
    assert response.hidden_evidence_summary.evidence_flags


def test_top_swings_include_effect_and_counter_effect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    assert response.top_swings
    assert response.top_swings[0].effect
    assert response.top_swings[0].counter_effect


def test_top_swings_include_one_change_test_and_validate_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    first = response.top_swings[0]
    assert first.one_change_test
    assert first.validate_with


def test_one_change_test_uses_concise_driver_language(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    assert response.top_swings
    assert "Effect:" not in response.top_swings[0].one_change_test
    assert "Counter-effect:" not in response.top_swings[0].one_change_test
    assert "exit_yaw" not in response.top_swings[0].one_change_test
    assert "drive_off" not in response.top_swings[0].one_change_test


def test_cross_weight_swing_uses_full_setup_term(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    cross_swings = [swing for swing in response.top_swings if swing.setup_area == "cross_weight"]
    assert cross_swings
    assert all("cross weight" in swing.title.lower() for swing in cross_swings)
    assert all("add a little cross." not in swing.title.lower() for swing in cross_swings)


def test_rear_pressure_split_swing_explains_lr_rr_relationship(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
            "lf_tire_temp_inner_c": 85.0,
            "rf_tire_temp_inner_c": 90.0,
            "lr_tire_temp_inner_c": 92.0,
            "rr_tire_temp_inner_c": 88.0,
        },
    )
    response = build_dial_in_response("run-1", "snaps loose on throttle", limit=10)
    pressure_swings = [swing for swing in response.top_swings if swing.id == "add_rear_stability_pressure_swing"]
    assert pressure_swings
    combined = " ".join(
        [
            pressure_swings[0].title,
            pressure_swings[0].effect,
            pressure_swings[0].counter_effect,
            pressure_swings[0].one_change_test,
        ]
    ).lower()
    assert "lr/rr" in combined
    assert "rear tire pressure" in combined
    assert "not all four tires" in combined
    assert "long_run_falloff" not in combined


def test_driver_response_avoids_bad_product_phrases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    text = json.dumps(response.model_dump(exclude_none=True)).lower()
    assert "guaranteed" not in text
    assert "ai recommends" not in text
    assert "ai interpretation" not in text
    assert "diagnosis" not in text
    assert "evidence factor" not in text
    assert "rank score" not in text
    assert "confidence float" not in text
    assert "evidence_id" not in text
    assert "matcher" not in text
    assert "measured downforce" not in text


def test_driver_response_uses_data_profile_language(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    combined = " ".join([response.readiness_label, response.driver_message, response.next_step or ""]).lower()
    assert "data profile" in combined or "cleaner run" in combined
    assert "confidence score" not in combined


def test_next_gen_response_never_includes_legacy_disabled_areas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    response = build_dial_in_response("run-1", "tight center")
    assert {swing.setup_area for swing in response.top_swings}.isdisjoint({"track_bar", "truck_arm_mount", "bump_stop", "packer"})


def test_unknown_car_family_stays_conservative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, car_name="Mystery Prototype Car", channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "tight center")
    assert {swing.setup_area for swing in response.top_swings}.isdisjoint({"track_bar", "truck_arm_mount", "bump_stop", "packer"})


def test_missing_compare_context_produces_simple_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off", baseline_run_id="missing-baseline")
    assert "Compare baseline is missing." in (response.driver_message + " " + (response.next_step or ""))
    assert "compare_baseline" not in response.driver_message


def test_diffuser_candidate_wording_does_not_claim_measured_downforce(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "front_center_rh_in": 1.9,
            "rear_center_rh_in": 2.6,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
            "speed_mph": 185.0,
        },
    )
    response = build_dial_in_response("run-1", "rear scrape", include_debug_evidence=True)
    combined = " ".join([swing.effect + " " + swing.counter_effect for swing in response.top_swings]).lower()
    assert "measured downforce" not in combined


def test_normal_diffuser_response_uses_proxy_safe_language(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "front_center_rh_in": 1.9,
            "rear_center_rh_in": 2.6,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
            "speed_mph": 185.0,
        },
    )
    response = build_dial_in_response("run-1", "rear scrape")
    text = json.dumps(response.model_dump(exclude_none=True)).lower()
    assert "measured downforce" not in text
    assert "diffuser" in text
    assert "proxy" in text


def test_shock_histogram_wording_does_not_say_proves_setup_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 1.0,
            "rr_shock_vel_in_s": 1.2,
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
        },
    )
    response = build_dial_in_response("run-1", "loose off")
    text = " ".join([response.driver_message, *(swing.effect + " " + swing.counter_effect for swing in response.top_swings)]).lower()
    assert "histogram proves" not in text
    assert "histogram confirms" not in text


def test_limit_defaults_to_three(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    assert len(response.top_swings) <= 3


def test_limit_nine_returns_expanded_disciplined_candidate_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "throttle_pct": 100.0,
            "yaw_rate": 1.2,
            "front_center_rh_in": 1.8,
            "rear_center_rh_in": 2.5,
            "smooth_center_rake_in": 0.7,
            "diffuser_volume_ft3": 12.0,
            "speed_mph": 185.0,
            "lf_tire_temp_inner_c": 85.0,
            "rf_tire_temp_inner_c": 90.0,
            "lr_tire_temp_inner_c": 92.0,
            "rr_tire_temp_inner_c": 88.0,
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 1.0,
            "rr_shock_vel_in_s": 1.2,
        },
    )
    response = build_dial_in_response("run-1", "tight center", limit=9)

    assert 3 < len(response.top_swings) <= 9
    assert sum(1 for swing in response.top_swings if swing.strength_label == "Package-level lever") <= 1
    assert {swing.setup_area for swing in response.top_swings}.isdisjoint({"track_bar", "truck_arm_mount", "bump_stop", "packer"})


def test_cli_json_returns_stable_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir, db_path = _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    env = os.environ.copy()
    env["RACELAB_DATA_DIR"] = str(data_dir)
    env["RACELAB_DB_PATH"] = str(db_path)
    completed = subprocess.run(
        [sys.executable, "-B", "scripts/query_dial_in.py", "--run-id", "run-1", "--complaint", "loose off", "--json"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(completed.stdout)
    assert {"run_id", "complaint_raw", "confidence_label", "readiness_label", "driver_message", "top_swings", "clarification", "warnings"}.issubset(payload)


def test_cli_debug_evidence_includes_backend_factors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir, db_path = _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    env = os.environ.copy()
    env["RACELAB_DATA_DIR"] = str(data_dir)
    env["RACELAB_DB_PATH"] = str(db_path)
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/query_dial_in.py",
            "--run-id",
            "run-1",
            "--complaint",
            "loose off",
            "--json",
            "--debug-evidence",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    payload = json.loads(completed.stdout)
    assert "hidden_evidence_summary" in payload
    assert "evidence_flags" in payload["hidden_evidence_summary"]


def test_no_full_row_materialization_guard_still_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    import racelab_engine.services.import_service as import_service

    def _boom(*args, **kwargs):
        raise AssertionError("read_telemetry_rows should not be used for dial-in metadata path")

    monkeypatch.setattr(import_service, "read_telemetry_rows", _boom)
    response = build_dial_in_response("run-1", "loose off")
    assert response.run_id == "run-1"
