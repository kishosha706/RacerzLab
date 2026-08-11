from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from racelab_engine.knowledge.setup.dial_in_service import build_dial_in_response
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.storage.repository import RaceLabRepository
from test_setup_evidence_adapter import _configure_env, _seed_run


def test_no_eligible_laps_never_emit_exact_dial_in_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, useful_laps=0, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})

    response = build_dial_in_response("run-1", "loose off")

    assert response.top_swings == []
    assert response.readiness_label == "Need cleaner data"
    assert any("No eligible flying laps" in warning for warning in response.warnings)


def test_explicit_phase_conflict_blocks_clear_read_and_setup_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"brake_pct": 50.0, "yaw_rate": 1.0})

    response = build_dial_in_response("run-1", "loose off", selected_phase="braking")

    assert response.top_swings == []
    assert response.confidence_label == "Needs clarification"
    assert response.evidence_state == "blocked_by_context"
    assert "maps to exit" in response.blocker_reasons[0]


def test_explicit_phase_cannot_conflict_with_driver_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 80.0, "yaw_rate": 1.0})

    response = build_dial_in_response(
        "run-1", "loose off", selected_phase="exit", priority="entry-security",
    )

    assert response.top_swings == []
    assert response.evidence_state == "blocked_by_context"
    assert "priority requires entry" in response.blocker_reasons[0]


@pytest.mark.parametrize("phase", ["entry", "center", "exit"])
def test_generic_complaint_is_resolved_by_selected_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"steering_deg": 3.0, "yaw_rate": 1.0})

    response = build_dial_in_response("run-1", f"tight {phase}", selected_phase=phase)

    assert response.clarification.needed is False
    assert response.interpreted_phase == phase


@pytest.mark.parametrize(("complaint", "phase"), [("tight", "exit"), ("loose", "entry")])
def test_bare_balance_complaint_uses_explicit_phase_selector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, complaint: str, phase: str,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"steering_deg": 3.0, "yaw_rate": 1.0})

    response = build_dial_in_response("run-1", complaint, selected_phase=phase)

    assert response.clarification.needed is False
    assert response.interpreted_phase == phase
    assert response.evidence_state != "blocked_by_context"


@pytest.mark.parametrize(
    ("objective", "priority"),
    [
        ("long-run", "overall-pace"),
        ("tire-conservation", "tire-life"),
        ("driver-confidence", "overall-pace"),
        ("race-pace", "platform-margin"),
    ],
)
def test_objective_specific_requests_cannot_certify_a_generic_phase_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, objective: str, priority: str,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 80.0, "yaw_rate": 1.0})

    response = build_dial_in_response(
        "run-1", "loose off", objective=objective, priority=priority,
    )

    assert response.top_swings == []
    assert response.evidence_strength is not None
    assert response.evidence_strength.setup_test_ready is False
    assert response.evidence_state == "blocked_by_context"


def test_sparse_semantic_match_never_emits_exact_actions_or_invented_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"speed_mph": 150.0})

    response = build_dial_in_response(
        "run-1", "rear scrape", include_debug_evidence=True, limit=5
    )

    assert response.top_swings == []
    assert response.evidence_state == "unavailable"
    assert response.source_channels == []
    assert response.blocker_reasons


def test_dial_in_reports_capability_only_as_measurement_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 0.9,
            "rr_shock_vel_in_s": 1.2,
            "throttle_pct": 75.0,
            "yaw_rate": 1.1,
        },
    )

    response = build_dial_in_response("run-1", "loose off")

    assert response.evidence_strength is not None
    assert response.evidence_strength.level == "capability_only"
    assert response.evidence_strength.readiness == "measurement_required"
    assert response.evidence_strength.setup_test_ready is False
    assert response.evidence_strength.observed_mechanism_flags == []


def test_dial_in_reports_qualified_event_without_claiming_controlled_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 0.9,
            "rr_shock_vel_in_s": 1.2,
            "throttle_pct": 75.0,
            "yaw_rate": 1.1,
        },
    )
    repo = RaceLabRepository()
    overview = repo.get_overview("run-1")
    assert overview is not None
    event = TelemetryEvent(
        event_id="run-1:damper-response:1",
        run_id="run-1",
        lap_number=1,
        event_type="DAMPER_RESPONSE",
        confidence_score=0.82,
        valid_for_tuning=True,
        evidence_state=EvidenceState.CALCULATED,
        evidence_json={"phase": "exit"},
        source_channels=["lf_shock_vel_in_s", "throttle_pct", "yaw_rate"],
        blocker_reasons=[],
    )
    repo.save_import(overview.model_copy(update={"events": [event]}))

    response = build_dial_in_response("run-1", "loose off", limit=9)

    assert response.evidence_strength is not None
    assert response.evidence_strength.level == "observed_mechanism"
    assert response.evidence_strength.setup_test_ready is False
    assert response.evidence_strength.requires_controlled_test is True
    assert response.evidence_state == "needs_confirmation"
    assert response.evidence_strength.supporting_event_ids == [event.event_id]


def test_selected_zone_scopes_observed_mechanism_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "lf_shock_vel_in_s": 1.0,
            "rf_shock_vel_in_s": 1.1,
            "lr_shock_vel_in_s": 0.9,
            "rr_shock_vel_in_s": 1.2,
            "throttle_pct": 75.0,
            "yaw_rate": 1.1,
        },
    )
    repo = RaceLabRepository()
    overview = repo.get_overview("run-1")
    assert overview is not None
    event = TelemetryEvent(
        event_id="run-1:damper-response:zone",
        run_id="run-1",
        lap_number=1,
        event_type="DAMPER_RESPONSE",
        lap_pct_peak=25.0,
        confidence_score=0.82,
        valid_for_tuning=True,
        evidence_state=EvidenceState.CALCULATED,
        source_channels=["lf_shock_vel_in_s", "throttle_pct", "yaw_rate"],
        blocker_reasons=[],
    )
    repo.save_import(overview.model_copy(update={"events": [event]}))

    inside = build_dial_in_response(
        "run-1", "loose off", selected_zone_start_pct=20.0, selected_zone_end_pct=30.0,
    )
    outside = build_dial_in_response(
        "run-1", "loose off", selected_zone_start_pct=50.0, selected_zone_end_pct=60.0,
    )

    assert inside.evidence_strength is not None
    assert inside.evidence_strength.level == "capability_only"
    assert outside.evidence_strength is not None
    assert outside.evidence_strength.level == "capability_only"
    assert outside.evidence_strength.setup_test_ready is False


def test_selected_lap_and_phase_scope_observed_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        useful_laps=2,
        channels={"throttle_pct": 75.0, "steering_deg": 2.0, "yaw_rate": 1.1},
    )
    repo = RaceLabRepository()
    overview = repo.get_overview("run-1")
    assert overview is not None
    event = TelemetryEvent(
        event_id="run-1:braking-yaw:lap-1",
        run_id="run-1",
        lap_number=1,
        event_type="BRAKE_ENTRY_YAW",
        lap_pct_peak=25.0,
        confidence_score=0.82,
        valid_for_tuning=True,
        evidence_state=EvidenceState.CALCULATED,
        evidence_json={"phase": "braking"},
        source_channels=["throttle_pct", "steering_deg", "yaw_rate"],
        blocker_reasons=[],
    )
    repo.save_import(overview.model_copy(update={"events": [event]}))

    response = build_dial_in_response(
        "run-1",
        "loose off",
        selected_lap=2,
        selected_zone_start_pct=20.0,
        selected_zone_end_pct=30.0,
        selected_phase="exit",
    )

    assert response.evidence_strength is not None
    assert response.evidence_strength.level == "capability_only"
    assert response.evidence_strength.supporting_event_ids == []


def test_dial_in_sources_are_archived_channels_not_future_validation_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})

    response = build_dial_in_response("run-1", "loose off")

    assert response.top_swings
    assert set(response.source_channels) <= {"throttle_pct", "yaw_rate"}
    assert "exit_yaw" not in response.source_channels


def test_selected_pit_lap_never_emits_exact_dial_in_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, useful_laps=1, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    repo = RaceLabRepository()
    overview = repo.get_overview("run-1")
    assert overview is not None
    pit_lap = LapSummary(
        lap_id="run-1:lap:2",
        run_id="run-1",
        lap_number=2,
        lap_type="complete_invalid",
        is_complete=True,
        is_useful=False,
        lap_time=32.0,
        classification_tags=["PIT_ROAD", "NO_SETUP_CONCLUSION"],
    )
    repo.save_import(overview.model_copy(update={"laps": [*overview.laps, pit_lap]}))

    response = build_dial_in_response("run-1", "loose off", selected_lap=2)

    assert response.top_swings == []
    assert any("Selected lap 2 is not eligible" in warning for warning in response.warnings)


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
    assert "evidence_groups" not in dumped
    # Raw channels may appear only as compact, truthful provenance.
    assert set(response.source_channels) <= {"front_center_rh_in", "rear_center_rh_in"}


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
    assert first.validate_with_labels
    assert all("_" not in label for label in first.validate_with_labels)


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


def test_dial_in_filters_controls_outside_driver_setup_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert all(swing.id != "add_rear_stability_pressure_swing" for swing in response.top_swings)
    allowed = {
        "lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm",
        "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm",
        "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm",
        "nose_weight_percent", "cross_weight_percent", "tape_percent", "rear_end_ratio",
        "front_brake_bias_percent", "steering_ratio", "steering_offset_deg",
    }
    assert all(set(swing.control_keys) <= allowed for swing in response.top_swings)


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


def test_dial_in_response_titles_use_exact_garage_actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    titles = " || ".join(swing.title.lower() for swing in response.top_swings)
    assert "platform support" not in titles
    assert "pressure trim" not in titles
    assert "rear toe stability" not in titles
    assert "high-speed rebound control" not in titles


def test_visible_dial_in_swings_include_specific_change_this_actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
    response = build_dial_in_response("run-1", "tight center", limit=18)
    assert response.top_swings

    vague_terms = [
        "adjust tire pressure",
        "supported axle",
        "tune diff preload",
        "front response toe swing",
        "adjust ride height",
        "adjust tire pressure",
        "tune platform",
        "response swing",
        "pressure trend",
    ]
    visible_text = json.dumps([swing.model_dump(exclude_none=True) for swing in response.top_swings]).lower()
    for term in vague_terms:
        assert term not in visible_text

    for swing in response.top_swings:
        assert swing.change_this
        assert swing.garage_lever
        action = f"{swing.title} {swing.change_this}".lower()
        assert any(
            word in action
            for word in [
                "add",
                "raise",
                "lower",
                "reduce",
                "increase",
                "move",
                "switch",
                "use",
                "soften",
                "stiffen",
                "select",
            ]
        )
        if "ride height" in action:
            assert any(scope in action for scope in ["lf ride height", "lr ride height", "all four corners"])
        if "brake bias" in action:
            assert any(direction in action for direction in ["forward", "rearward", "increase", "decrease"])
        assert "one small step" not in action
        assert swing.change_size_label == "Target unavailable - record adjacent option"
        assert swing.change_size_explanation
        assert swing.proposed_value_label is None
        assert swing.blocker_reasons
        assert swing.evidence_state == "blocked_by_context"
        assert swing.change_this.lower().startswith("do not change")
        assert swing.control_expectation
        assert swing.control_guardrail
        assert swing.keep_if.startswith("Keep it only if")
        assert swing.undo_if.startswith("Undo it if")


def test_driver_response_uses_data_profile_language(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")
    combined = " ".join([response.readiness_label, response.driver_message, response.next_step or ""]).lower()
    assert "data profile" in combined or "cleaner run" in combined
    assert "confidence score" not in combined


def test_driver_response_uses_direct_setup_change_vocabulary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(tmp_path, channels={"throttle_pct": 100.0, "yaw_rate": 1.2})
    response = build_dial_in_response("run-1", "loose off")

    assert response.next_step == (
        "Record the current control and its adjacent tech-passing garage options with source provenance, "
        "then generate one controlled test."
    )
    assert response.validation_summary is not None
    assert response.validation_summary.startswith("Primary evidence signals: ")
    assert "Test one swing" not in response.next_step
    assert "What to watch for" not in response.validation_summary
    assert response.readiness_label == "Need setup option data"
    assert response.blocker_reasons


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
    assert payload["top_swings"][0]["validate_with_labels"]
    assert {
        "change_this",
        "direction_sign",
        "current_value_label",
        "proposed_value_label",
        "one_change_test",
        "keep_if",
        "undo_if",
    }.isdisjoint(payload["top_swings"][0])
    assert "no setup change is authorized" in payload["driver_message"].casefold()


def test_cli_text_uses_public_hypothesis_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "Engineering hypotheses only" in completed.stdout
    assert "Control areas to measure:" in completed.stdout
    assert "Next step:" in completed.stdout


def test_setup_knowledge_package_does_not_export_internal_action_producers() -> None:
    import racelab_engine.knowledge.setup as setup_package

    assert {
        "DialInResponse",
        "DialInSwing",
        "build_dial_in_response",
        "query_setup_for_run_context",
        "query_setup_knowledge",
    }.isdisjoint(setup_package.__all__)
    assert all(not hasattr(setup_package, name) for name in (
        "DialInResponse",
        "DialInSwing",
        "build_dial_in_response",
        "query_setup_for_run_context",
        "query_setup_knowledge",
    ))


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
