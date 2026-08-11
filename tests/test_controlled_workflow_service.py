from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from racelab_engine.analysis.crew_chief_packet import CauseCandidate, OpportunityEvidence, build_kaizen_packet
from racelab_engine.analysis.test_director import (
    TestEvidenceLink,
    TestExecution,
    TestQualityResult as WorkflowQualityResult,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import controlled_workflow_service as service
from racelab_engine.storage.repository import RaceLabRepository
from racelab_engine.knowledge.setup.dial_in_controls import _PLANS, garage_action_for_effect
from racelab_engine.models.evidence import EvidenceState
from test_setup_evidence_adapter import _configure_env, _seed_run
from racelab_engine.models.segment import SegmentSummary


def _packet():
    link = TestEvidenceLink(
        event_id="entry-proof", eligible_lap=True, valid_for_tuning=True,
        phase="entry", related_setup_keys=("cross_weight_percent",),
    )
    return build_kaizen_packet(
        opportunity=OpportunityEvidence(
            start_pct=20.0, end_pct=30.0, phase="entry", observed_time_loss_s=0.2,
            empirical_noise_s=0.04, alignment_confidence=0.95, repeatable=True,
            evidence_links=(link,), source_channels=("lap_dist_pct_100", "speed_mps"),
            supporting_evidence=("Loss repeated on three eligible laps.",),
        ),
        canonical_symptom="tight_entry",
        candidates=[CauseCandidate(
            cause_bucket="corner_balance", control_key="cross_weight_percent",
            direction_sign=1, score=0.9, hypothesis="Test entry balance.",
            success_metrics=("Target-window entry time",),
            countereffects=("Median non-target phase time must not worsen beyond empirical noise.",),
            supporting_event_ids=("entry-proof",),
        )],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3, context_matched=True, driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={
            "cross_weight_percent": {"50.5": ["tech-passing-setup:option-run"]},
        },
    )


def _overview(run_id: str, timestamp: str) -> RunOverview:
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(run_id=run_id, sim_date_time=timestamp, setup_passed_tech=True),
        laps=[
            LapSummary(
                lap_id=f"{run_id}-{number}", run_id=run_id, lap_number=number,
                lap_type="flying", is_complete=True, is_useful=True, lap_time=30.0 + number,
            )
            for number in range(1, 6)
        ],
    )


class _Repo:
    db_path = None

    def __init__(self, workflow: ControlledWorkflow):
        self.workflow = workflow
        self.overviews = {
            "source": _overview("source", "2026-08-04T10:00:00+00:00"),
            "run-a": _overview("run-a", "2026-08-04T10:30:00+00:00"),
            "run-b-old": _overview("run-b-old", "2026-08-04T11:00:00+00:00"),
        }

    def get_controlled_workflow(self, workflow_id: str):
        return self.workflow if workflow_id == self.workflow.workflow_id else None

    def get_overview(self, run_id: str):
        return self.overviews.get(run_id)

    def get_setup_snapshot(self, run_id: str):
        return None


def test_attach_rejects_historical_b_run_even_when_stage_order_is_chronological(monkeypatch: pytest.MonkeyPatch) -> None:
    planned = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="aba-historical", created_at=planned, updated_at=planned,
        status="a_recorded", source_run_id="source", complaint="tight entry",
        packet=_packet(), stage_run_ids={"A": "run-a"},
    )
    identity = {
        "driver_user_id": "driver", "car_id": "car", "car_path": "car/path",
        "car_version": "1", "track_id": "track", "track_configuration_name": "oval",
        "track_version": "1", "iracing_build_version": "build", "session_type": "test",
    }
    bounds = {
        "source": {"start": 0.0, "end": 100.0},
        "run-a": {"start": 200.0, "end": 300.0},
        "run-b-old": {"start": 150.0, "end": 190.0},
    }
    monkeypatch.setattr(service, "read_telemetry_manifest", lambda run_id: {
        "compatibility_identity": identity,
        "recording_session_time_bounds_s": bounds[run_id],
    })
    monkeypatch.setattr(
        service,
        "revalidate_controlled_workflow_packet",
        lambda _workflow, **_kwargs: (_workflow.packet, ()),
    )
    monkeypatch.setattr(service, "_validate_recorded_stage_bindings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "read_telemetry_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, "_workflow_decision_context", lambda _workflow: {})

    with pytest.raises(ValueError, match="workflow was planned"):
        service.attach_stage("aba-historical", "B", "run-b-old", repository=_Repo(workflow))


def test_legacy_manifest_without_recording_bounds_requires_reimport() -> None:
    overview = _overview("legacy", "2026-08-04T10:00:00+00:00")
    assert service._recording_interval(overview, {"manifest_schema_version": 2}) is None


def test_source_run_can_be_frozen_as_a_but_b_must_be_post_plan() -> None:
    interval = (100.0, 200.0)
    assert service._recording_order_is_valid(
        stage="A", run_id="source", source_run_id="source",
        current_interval=interval, previous_interval=interval,
        workflow_created_epoch_s=300.0,
    ) is True
    assert service._recording_order_is_valid(
        stage="B", run_id="historical-b", source_run_id="source",
        current_interval=(210.0, 250.0), previous_interval=interval,
        workflow_created_epoch_s=300.0,
    ) is False


def test_card_keeps_observed_option_provenance() -> None:
    packet = _packet()
    assert packet.primary_test is not None
    assert packet.primary_test.proposed_value_raw == 50.5
    assert packet.primary_test.proposed_value_provenance == ("tech-passing-setup:option-run",)


def test_only_one_active_controlled_test_can_touch_a_run(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    active = ControlledWorkflow(
        workflow_id="aba-active", created_at=now, updated_at=now,
        status="planned", source_run_id="source", complaint="tight entry", packet=_packet(),
    )

    class Repo:
        db_path = None

        def list_controlled_workflows(self, *, active_only: bool = False):
            assert active_only is True
            return [active]

        def save_controlled_workflow(self, _workflow: ControlledWorkflow) -> None:
            raise AssertionError("A competing workflow must not be saved.")

    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *args, **kwargs: _packet())

    with pytest.raises(ValueError, match="Finish or explicitly abandon"):
        service.create_workflow("source", "loose exit", repository=Repo())


def test_cancel_workflow_preserves_an_auditable_cancelled_record() -> None:
    now = datetime.now(timezone.utc)
    active = ControlledWorkflow(
        workflow_id="aba-abandon", created_at=now, updated_at=now,
        status="a_recorded", source_run_id="source", complaint="tight entry", packet=_packet(),
    )

    class Repo:
        def __init__(self):
            self.saved: ControlledWorkflow | None = None

        def get_controlled_workflow(self, workflow_id: str):
            return active if workflow_id == active.workflow_id else None

        def save_controlled_workflow(self, workflow: ControlledWorkflow) -> None:
            self.saved = workflow

    repo = Repo()
    cancelled = service.cancel_workflow(active.workflow_id, repository=repo)

    assert cancelled.status == "cancelled"
    assert cancelled.workflow_id == active.workflow_id
    assert cancelled.stage_run_ids == active.stage_run_ids
    assert repo.saved == cancelled


@pytest.mark.parametrize(
    ("control_key", "label", "baseline", "planned"),
    [
        ("steering_ratio", "Steering Ratio / Pinion", "14:1", "12:1"),
        ("tape_percent", "Tape", "5%", "0%"),
    ],
)
def test_attach_b_accepts_exact_typed_garage_value_without_float_coercion(
    monkeypatch: pytest.MonkeyPatch,
    control_key: str,
    label: str,
    baseline: str,
    planned: str,
) -> None:
    packet = _packet()
    assert packet.primary_test is not None
    card = packet.primary_test.model_copy(update={
        "control_key": control_key,
        "control_label": label,
        "current_value": baseline,
        "proposed_value": planned,
        "proposed_value_raw": planned,
    })
    packet = packet.model_copy(update={"primary_test": card})
    created = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id=f"aba-{control_key}", created_at=created, updated_at=created,
        status="a_recorded", source_run_id="source", complaint="test",
        packet=packet, stage_run_ids={"A": "run-a"},
    )

    class AttachRepo(_Repo):
        def __init__(self) -> None:
            super().__init__(workflow)
            self.overviews["run-a"] = _overview("run-a", "2026-08-04T12:30:00+00:00")
            self.overviews["run-b"] = _overview("run-b", "2026-08-04T13:00:00+00:00")
            self.setups = {
                "source": {control_key: baseline},
                "run-a": {control_key: baseline},
                "run-b": {control_key: planned},
            }

        def get_setup_snapshot(self, run_id: str):
            return self.setups.get(run_id)

        def save_controlled_workflow(self, updated: ControlledWorkflow) -> None:
            self.workflow = updated

    identity = {
        "driver_user_id": "driver", "car_id": "car", "car_path": "car/path",
        "car_version": "1", "track_id": "track", "track_configuration_name": "oval",
        "track_version": "1", "iracing_build_version": "build", "session_type": "test",
    }
    bounds = {
        "source": {"start": 0.0, "end": 100.0},
        "run-a": {"start": 200.0, "end": 300.0},
        "run-b": {"start": 400.0, "end": 500.0},
    }
    monkeypatch.setattr(service, "read_telemetry_manifest", lambda run_id: {
        "compatibility_identity": identity,
        "recording_session_time_bounds_s": bounds[run_id],
    })
    monkeypatch.setattr(
        service,
        "revalidate_controlled_workflow_packet",
        lambda _workflow, **_kwargs: (_workflow.packet, ()),
    )
    monkeypatch.setattr(service, "_validate_recorded_stage_bindings", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "read_telemetry_rows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(service, "_workflow_decision_context", lambda _workflow: {})
    monkeypatch.setattr(service, "setup_controls_comparable", lambda _left, _right: True)
    monkeypatch.setattr(service, "unmapped_setup_change_paths", lambda _left, _right, _changes: [])
    monkeypatch.setattr(service, "_continuous_stage_cohort", lambda _numbers, _rows: (True, None))
    monkeypatch.setattr(
        service,
        "diff_setups",
        lambda _left, _right: [SimpleNamespace(setup_key=control_key)],
    )

    attached = service.attach_stage(workflow.workflow_id, "B", "run-b", repository=AttachRepo())

    assert attached.stage_run_ids["B"] == "run-b"
    assert attached.stage_eligible_lap_numbers["B"] == (3, 4, 5)


def test_stage_cohort_rejects_an_eligible_lap_gap() -> None:
    ok, reason = service._continuous_stage_cohort([1, 2, 3, 5, 6], {})
    assert ok is False
    assert reason is not None and "consecutive" in reason


def test_platform_margin_cannot_be_certified_from_phase_time_only() -> None:
    blocker = service._decision_context_blocker("race-pace", "platform-margin")
    assert blocker is not None
    assert "phase time alone cannot certify" in blocker


def test_countereffect_uses_its_own_phase_noise_not_target_window_noise() -> None:
    passed, noise = service._score_countereffect_guardrail(
        {"exit": [0.04, 0.04, 0.04, 0.04]},
        {"exit": [0.002, 0.002, 0.002, 0.002]},
        guardrail_declared=True,
    )
    assert noise["exit"] == pytest.approx(0.002)
    assert passed is False


def _guardrail_laps(channel: str, a: float, b: float, a2: float) -> dict[str, list[list[dict[str, float]]]]:
    return {
        "A": [[{channel: a + offset}] for offset in (0.0, 0.001, -0.001)],
        "B": [[{channel: b + offset}] for offset in (0.0, 0.001, -0.001)],
        "A2": [[{channel: a2 + offset}] for offset in (0.0, 0.001, -0.001)],
    }


def test_platform_guardrail_cannot_hide_worsening_clearance_behind_a_safe_risk_alias() -> None:
    laps = _guardrail_laps("front_platform_risk_score", 0.20, 0.19, 0.21)
    clearance = _guardrail_laps("cfs_ride_height_in", 2.0, 1.8, 2.0)
    for stage in ("A", "B", "A2"):
        for index, rows in enumerate(laps[stage]):
            rows[0].update(clearance[stage][index][0])

    passed, metrics = service._control_guardrail_evaluation("rf_front_spring_n_per_mm", laps)

    assert passed is False
    assert "cfs_ride_height_in_b" in metrics


def test_platform_guardrail_is_unavailable_without_platform_telemetry() -> None:
    empty = {stage: [[{}], [{}], [{}]] for stage in ("A", "B", "A2")}
    assert service._control_guardrail_evaluation("lf_ride_height_mm", empty) == (None, {})


@pytest.mark.parametrize(
    ("effects", "expected"),
    [
        ({"AB": [-0.2, -0.18, -0.19], "A2B": [-0.17, -0.16, -0.18]}, "faster"),
        ({"AB": [-0.2, -0.18, 0.02], "A2B": [-0.17, -0.16, -0.18]}, "inconsistent"),
        ({"AB": [-0.02, 0.01, 0.0], "A2B": [-0.01, 0.02, 0.0]}, "inconclusive"),
    ],
)
def test_target_distribution_state_never_calls_inconclusive_laps_consistent(
    effects: dict[str, list[float]], expected: str,
) -> None:
    assert service._target_effect_distribution_state(effects, 0.05) == expected


def test_context_matching_allows_normal_progression_but_compares_stage_ordinals() -> None:
    def lap(fuel: float, tire_distance: float) -> list[dict[str, object]]:
        return [{
            "player_tire_compound": "dry", "tire_sets_used": 1,
            "fuel_level": fuel, "air_temp": 25.0, "track_temp": 30.0, "wind_vel": 1.0,
            "lf_tire_distance_m": tire_distance, "rf_tire_distance_m": tire_distance,
            "lr_tire_distance_m": tire_distance, "rr_tire_distance_m": tire_distance,
            "car_distance_ahead_m": 500000.0, "car_distance_behind_m": 500000.0,
            "speed_mps": 50.0,
        }]

    stint = [lap(50.0, 1000.0), lap(48.0, 5000.0), lap(46.0, 9000.0)]
    assert service._context_score(stint, allow_stint_progression=True) == 1.0
    for ordinal in range(3):
        assert service._context_score([stint[ordinal], stint[ordinal], stint[ordinal]]) == 1.0


@pytest.mark.parametrize(
    "b_context",
    [
        {"car_distance_ahead_m": 5.0, "car_distance_behind_m": 500000.0},
        {"car_distance_ahead_m": 500000.0, "car_distance_behind_m": 5.0},
        {"car_distance_ahead_m": None, "car_distance_behind_m": 500000.0},
    ],
)
def test_context_matching_blocks_nearby_or_unknown_proximity(
    b_context: dict[str, float | None],
) -> None:
    def lap(proximity: dict[str, float | None]) -> list[dict[str, object]]:
        return [{
            "player_tire_compound": "dry", "tire_sets_used": 1,
            "fuel_level": 50.0, "air_temp": 25.0, "track_temp": 30.0, "wind_vel": 1.0,
            "lf_tire_distance_m": 1000.0, "rf_tire_distance_m": 1000.0,
            "lr_tire_distance_m": 1000.0, "rr_tire_distance_m": 1000.0,
            "speed_mps": 50.0,
            **proximity,
        }]

    far = {"car_distance_ahead_m": 500000.0, "car_distance_behind_m": 500000.0}

    assert service._context_score([lap(far), lap(b_context), lap(far)]) == 0.0


def test_every_dial_in_plan_preserves_structured_direction_without_parsing_prose() -> None:
    for effect_id, plan in _PLANS.items():
        action = garage_action_for_effect(
            SimpleNamespace(effect=SimpleNamespace(effect_id=effect_id)),
            {},
        )
        assert action is not None
        assert action.direction_sign == plan.direction_sign

    source = (Path(__file__).resolve().parents[1] / "racelab_engine/services/controlled_workflow_service.py").read_text(encoding="utf-8")
    assert "direction_sign=swing.direction_sign" in source


def test_candidate_score_is_evidence_based_not_list_position() -> None:
    swing = SimpleNamespace(
        control_keys=["cross_weight_percent"], direction_sign=1,
        setup_area="cross_weight", effect="Expected effect.",
        counter_effect="Expected trade-off.", validate_with_labels=["Target phase time"],
        validate_with=[], blocker_reasons=[], source_channels=["yaw_rate", "steering_deg"],
        evidence_state=EvidenceState.OBSERVED_CORRELATION, risk_label="Medium coupling risk",
    )

    source_channels = {"event-1": ("yaw_rate", "steering_deg")}
    first = service._cause_candidate_from_swing(
        swing, {"cross_weight_percent": ["event-1"]}, source_channels,
    )
    repeated = service._cause_candidate_from_swing(
        swing, {"cross_weight_percent": ["event-1"]}, source_channels,
    )

    assert first is not None and repeated is not None
    assert first.score == repeated.score
    assert first.score_components["eligible_event_link"] == 1.0
    assert "not a calibrated probability" in first.score_basis


def test_candidate_without_event_link_cannot_receive_strong_score() -> None:
    swing = SimpleNamespace(
        control_keys=["cross_weight_percent"], direction_sign=1,
        setup_area="cross_weight", effect="Expected effect.",
        counter_effect="Expected trade-off.", validate_with_labels=["Target phase time"],
        validate_with=[], blocker_reasons=[],
        source_channels=["yaw_rate", "steering_deg", "speed_mps", "lap_dist_pct_100"],
        evidence_state=EvidenceState.MEASURED, risk_label="Low coupling risk",
    )

    candidate = service._cause_candidate_from_swing(swing, {})

    assert candidate is not None
    assert candidate.score <= 0.35
    assert candidate.supporting_event_ids == ()
    assert candidate.score_components["eligible_event_link"] == 0.0


def test_multi_control_swing_cannot_be_truncated_into_one_exact_action() -> None:
    swing = SimpleNamespace(
        control_keys=["lf_ride_height_mm", "rf_ride_height_mm"], direction_sign=1,
        setup_area="front_platform", effect="Raise the front.", counter_effect="Trade-off.",
        validate_with_labels=["Platform margin"], validate_with=[], blocker_reasons=[],
        source_channels=["lf_ride_height_in", "rf_ride_height_in"],
        observed_evidence_flags=["front_platform"], supporting_event_ids=["event-1"],
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        readiness_label="Observed mechanism", risk_label="Medium risk",
    )

    assert service._cause_candidate_from_swing(
        swing,
        {"lf_ride_height_mm": ["event-1"], "rf_ride_height_mm": ["event-1"]},
    ) is None


@pytest.mark.parametrize(
    ("start", "end"),
    [(20.0, None), (None, 30.0), (-1.0, 30.0), (30.0, 30.0), (40.0, 30.0), (20.0, 101.0)],
)
def test_selected_zone_validation_fails_closed(start: float | None, end: float | None) -> None:
    with pytest.raises(ValueError, match="selected Dial-In zone|Selected Dial-In zone"):
        service._validated_selected_zone(start, end)


def test_selected_zone_cannot_widen_to_a_partially_overlapping_phase_window() -> None:
    assert service._selected_zone_contains_window((29.0, 30.0), 10.0, 30.0) is False
    assert service._selected_zone_contains_window((20.0, 40.0), 25.0, 30.0) is True


@pytest.mark.parametrize("objective", ["long-run", "tire-conservation", "driver-confidence"])
def test_short_phase_protocol_cannot_certify_unsupported_objective(objective: str) -> None:
    assert service._decision_context_blocker(objective, "overall-pace") is not None


def test_driver_priority_has_a_server_owned_phase_scope() -> None:
    assert service._priority_phase("entry-security") == "entry"
    assert service._priority_phase("center-rotation") == "center"
    assert service._priority_phase("exit-drive") == "exit"


def test_event_relation_families_expand_only_to_supported_exact_controls() -> None:
    assert service._expanded_related_setup_keys(["front_springs", "packers"]) == (
        "lf_front_spring_n_per_mm",
        "rf_front_spring_n_per_mm",
    )


def test_requested_phase_accepts_only_its_physical_phase_family() -> None:
    assert service._phase_matches("threshold_braking", "braking") is True
    assert service._phase_matches("brake_release", "entry") is True
    assert service._phase_matches("initial_throttle", "exit") is True
    assert service._phase_matches("bump_curb", "bump_curb") is True
    assert service._phase_matches("initial_throttle", "entry") is False


def test_specific_priority_is_part_of_personal_learning_context() -> None:
    assert service._memory_objective("long-run", "tire-life") == "long-run|priority:tire-life"
    assert service._memory_objective("race-pace", "overall-pace") == "race-pace"


def test_exact_context_response_model_can_block_a_generic_direction() -> None:
    candidate = CauseCandidate(
        cause_bucket="cross_weight", control_key="cross_weight_percent",
        direction_sign=1, score=0.8, hypothesis="Test the direction.",
        success_metrics=("Target phase time",), countereffects=("Guardrail",),
        supporting_event_ids=("event-1",), score_components={"eligible_event_link": 1.0},
    )
    models = {
        "model": {
            "setup_key": "cross_weight_percent",
            "surrounding_setup_fingerprint": "surrounding-1",
            "target_zone": {"start_pct": 20.0, "end_pct": 30.0},
            "observed_delta_range": {"minimum": -1.0, "maximum": 1.0},
            "observed_absolute_control_range": {"minimum": 49.0, "maximum": 51.0},
            "linear_effect_s_per_input_unit": 0.10,
            "quadratic_effect_s_per_input_unit_squared": 0.0,
            "residual_uncertainty_s": 0.02,
            "observation_count": 8,
        }
    }
    opportunity = OpportunityEvidence(
        start_pct=20.0, end_pct=30.0, phase="entry", observed_time_loss_s=0.2,
        empirical_noise_s=0.04, alignment_confidence=0.95, repeatable=True,
        evidence_links=(), source_channels=("speed_mps",),
    )

    result = service._apply_personal_response_models(
        [candidate], opportunity=opportunity,
        current_setup_values={"cross_weight_percent": 50.0},
        surrounding_fingerprint_by_control={"cross_weight_percent": "surrounding-1"},
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        response_models=models,
    )

    assert result[0].score_components["personal_response_support"] == 0.0
    assert result[0].blocked_reasons
    assert "exact-context response history" in result[0].blocked_reasons[0]


def test_response_model_is_not_used_outside_observed_delta_range() -> None:
    candidate = CauseCandidate(
        cause_bucket="cross_weight", control_key="cross_weight_percent",
        direction_sign=1, score=0.8, hypothesis="Test the direction.",
        success_metrics=("Target phase time",), countereffects=("Guardrail",),
        supporting_event_ids=("event-1",),
    )
    opportunity = OpportunityEvidence(
        start_pct=20.0, end_pct=30.0, phase="entry", observed_time_loss_s=0.2,
        empirical_noise_s=0.04, alignment_confidence=0.95, repeatable=True,
        evidence_links=(), source_channels=("speed_mps",),
    )
    models = {"model": {
        "setup_key": "cross_weight_percent",
        "surrounding_setup_fingerprint": "surrounding-1",
        "target_zone": {"start_pct": 20.0, "end_pct": 30.0},
        "observed_delta_range": {"minimum": -0.25, "maximum": 0.25},
        "observed_absolute_control_range": {"minimum": 49.0, "maximum": 51.0},
        "linear_effect_s_per_input_unit": -0.1,
        "quadratic_effect_s_per_input_unit_squared": 0.0,
        "residual_uncertainty_s": 0.01,
        "observation_count": 8,
    }}

    result = service._apply_personal_response_models(
        [candidate], opportunity=opportunity,
        current_setup_values={"cross_weight_percent": 50.0},
        surrounding_fingerprint_by_control={"cross_weight_percent": "surrounding-1"},
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        response_models=models,
    )

    assert result == [candidate]


def test_response_model_is_not_shared_across_surrounding_setups() -> None:
    candidate = CauseCandidate(
        cause_bucket="cross_weight", control_key="cross_weight_percent",
        direction_sign=1, score=0.8, hypothesis="Test the direction.",
        success_metrics=("Target phase time",), countereffects=("Guardrail",),
        supporting_event_ids=("event-1",),
    )
    opportunity = OpportunityEvidence(
        start_pct=20.0, end_pct=30.0, phase="entry", observed_time_loss_s=0.2,
        empirical_noise_s=0.04, alignment_confidence=0.95, repeatable=True,
        evidence_links=(), source_channels=("speed_mps",),
    )
    models = {"model": {
        "setup_key": "cross_weight_percent",
        "surrounding_setup_fingerprint": "different-surrounding-setup",
        "target_zone": {"start_pct": 20.0, "end_pct": 30.0},
        "observed_delta_range": {"minimum": -1.0, "maximum": 1.0},
        "observed_absolute_control_range": {"minimum": 49.0, "maximum": 51.0},
        "linear_effect_s_per_input_unit": 0.1,
        "quadratic_effect_s_per_input_unit_squared": 0.0,
        "residual_uncertainty_s": 0.01,
        "observation_count": 8,
    }}

    result = service._apply_personal_response_models(
        [candidate], opportunity=opportunity,
        current_setup_values={"cross_weight_percent": 50.0},
        surrounding_fingerprint_by_control={"cross_weight_percent": "current-surrounding-setup"},
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        response_models=models,
    )

    assert result == [candidate]


def test_response_model_is_not_used_outside_absolute_control_levels() -> None:
    candidate = CauseCandidate(
        cause_bucket="cross_weight", control_key="cross_weight_percent",
        direction_sign=1, score=0.8, hypothesis="Test the direction.",
        success_metrics=("Target phase time",), countereffects=("Guardrail",),
        supporting_event_ids=("event-1",),
    )
    opportunity = OpportunityEvidence(
        start_pct=20.0, end_pct=30.0, phase="entry", observed_time_loss_s=0.2,
        empirical_noise_s=0.04, alignment_confidence=0.95, repeatable=True,
        evidence_links=(), source_channels=("speed_mps",),
    )
    models = {"model": {
        "setup_key": "cross_weight_percent",
        "surrounding_setup_fingerprint": "surrounding-1",
        "target_zone": {"start_pct": 20.0, "end_pct": 30.0},
        "observed_delta_range": {"minimum": -1.0, "maximum": 1.0},
        "observed_absolute_control_range": {"minimum": 49.0, "maximum": 51.0},
        "linear_effect_s_per_input_unit": 0.1,
        "quadratic_effect_s_per_input_unit_squared": 0.5,
        "residual_uncertainty_s": 0.01,
        "observation_count": 8,
    }}

    result = service._apply_personal_response_models(
        [candidate], opportunity=opportunity,
        current_setup_values={"cross_weight_percent": 60.0},
        surrounding_fingerprint_by_control={"cross_weight_percent": "surrounding-1"},
        legal_values_by_control={"cross_weight_percent": [60.0, 60.5]},
        response_models=models,
    )

    assert result == [candidate]


def test_server_packet_requires_same_qualified_mechanism_event_as_opportunity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    overview = _overview("source", "2026-08-04T10:00:00+00:00")
    overview.events = [SimpleNamespace(
        event_id="opportunity-event", lap_number=1, valid_for_tuning=True,
        lap_pct_peak=25.0, lap_pct_start=24.0,
        related_setup_keys=["cross_weight_percent"],
    )]

    class PacketRepo:
        db_path = None

        def get_overview(self, run_id: str):
            return overview if run_id == "source" else None

        def get_setup_snapshot(self, _run_id: str):
            return None

    swing = SimpleNamespace(
        control_keys=["cross_weight_percent"], direction_sign=1,
        setup_area="cross_weight", effect="Expected effect.", counter_effect="Trade-off.",
        validate_with_labels=["Target phase time"], validate_with=[], blocker_reasons=[],
        source_channels=["yaw_rate"], evidence_state=EvidenceState.NEEDS_CONFIRMATION,
        risk_label="Medium coupling risk",
    )
    dial = SimpleNamespace(
        interpreted_phase="entry", interpreted_symptom="tight_entry", top_swings=[swing],
        evidence_strength=SimpleNamespace(
            setup_test_ready=True,
            supporting_event_ids=["different-qualified-event"],
        ),
    )
    opportunity = OpportunityEvidence(
        start_pct=20.0, end_pct=30.0, phase="entry", observed_time_loss_s=0.2,
        empirical_noise_s=0.04, alignment_confidence=0.95, repeatable=True,
        evidence_links=(TestEvidenceLink(
            event_id="opportunity-event", eligible_lap=True, valid_for_tuning=True,
            phase="entry", related_setup_keys=("cross_weight_percent",),
        ),),
        source_channels=("speed_mps",), supporting_evidence=("Repeated loss.",),
    )
    monkeypatch.setattr(service, "build_dial_in_response", lambda *_args, **_kwargs: dial)
    monkeypatch.setattr(service, "_derive_opportunity", lambda *_args, **_kwargs: (opportunity, 1.0, 1.0, True))

    packet = service.build_server_kaizen_packet("source", "tight entry", repository=PacketRepo())

    assert packet.decision == "measure"
    assert any("No setup cause" in blocker for blocker in packet.blockers)


def test_server_packet_uses_proven_adjacent_option_before_candidate_gating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_env(monkeypatch, tmp_path)

    def setup_values(cross_weight: float) -> dict[str, object]:
        return {
            "lf_ride_height_mm": 50.0,
            "rf_ride_height_mm": 51.0,
            "lr_ride_height_mm": 70.0,
            "rr_ride_height_mm": 71.0,
            "lf_front_spring_n_per_mm": 100.0,
            "rf_front_spring_n_per_mm": 101.0,
            "lr_rear_spring_n_per_mm": 90.0,
            "rr_rear_spring_n_per_mm": 91.0,
            "nose_weight_percent": 52.0,
            "cross_weight_percent": cross_weight,
            "tape_percent": 45.0,
            "rear_end_ratio": 3.5,
            "front_brake_bias_percent": 54.0,
            "steering_ratio": "14:1",
            "steering_offset_deg": 0.0,
        }

    def raw_setup(cross_weight: float) -> dict[str, object]:
        return {"Chassis": {
            "LeftFront": {"RideHeight": 50.0, "SpringRate": 100.0},
            "RightFront": {"RideHeight": 51.0, "SpringRate": 101.0},
            "LeftRear": {"RideHeight": 70.0, "SpringRate": 90.0},
            "RightRear": {"RideHeight": 71.0, "SpringRate": 91.0},
            "Front": {
                "NoseWeight": 52.0,
                "CrossWeight": cross_weight,
                "Tape": 45.0,
                "FrontBrakeBias": 54.0,
                "SteeringRatio": "14:1",
                "SteeringOffset": 0.0,
            },
            "Rear": {"RearEndRatio": 3.5},
            "Other": {"DeclaredLeafA": 1, "DeclaredLeafB": 2},
        }}

    _seed_run(
        tmp_path,
        run_id="source",
        channels={
            "yaw_rate": 1.0,
            "lf_tire_pressure": 30.0,
            "rf_tire_pressure": 30.0,
        },
        setup_json=raw_setup(50.0),
        extracted_values=setup_values(50.0),
        useful_laps=3,
    )
    _seed_run(
        tmp_path,
        run_id="option-run",
        channels={"yaw_rate": 1.0},
        setup_json=raw_setup(49.5),
        extracted_values=setup_values(49.5),
        useful_laps=3,
    )
    repo = RaceLabRepository()
    source = repo.get_overview("source")
    option = repo.get_overview("option-run")
    assert source is not None and option is not None

    def event(event_id: str, event_type: str, source_channels: list[str]) -> TelemetryEvent:
        return TelemetryEvent(
            event_id=event_id,
            run_id="source",
            lap_number=1,
            event_type=event_type,
            lap_pct_start=24.0,
            lap_pct_end=26.0,
            lap_pct_peak=25.0,
            confidence_score=0.9,
            valid_for_tuning=True,
            evidence_state=EvidenceState.CALCULATED,
            evidence_json={"phase": "center"},
            source_channels=source_channels,
            related_setup_keys=["cross_weight_percent"],
            blocker_reasons=[],
        )

    mechanism_events = [
        event("center-yaw-proof", "YAW_EXIT", ["yaw_rate"]),
        event(
            "center-tire-proof",
            "TIRE_PRESSURE",
            ["lf_tire_pressure", "rf_tire_pressure"],
        ),
    ]
    repo.save_import(source.model_copy(update={
        "events": mechanism_events,
        "session": source.session.model_copy(update={"setup_passed_tech": True}),
    }))
    repo.save_import(option.model_copy(update={
        "session": option.session.model_copy(update={"setup_passed_tech": True}),
    }))
    for index in range(51):
        decoy_run_id = f"newer-baseline-{index:02d}"
        repo.save_import(RunOverview(
            run_id=decoy_run_id,
            session=source.session.model_copy(update={
                "run_id": decoy_run_id,
                "setup_passed_tech": True,
            }),
            setup_snapshot=SetupSnapshot(
                setup_id=f"{decoy_run_id}:setup",
                run_id=decoy_run_id,
                setup_name="Unchanged baseline",
                setup_json=raw_setup(50.0),
                extracted_values=setup_values(50.0),
            ),
        ))
    assert "option-run" not in {item["run_id"] for item in repo.list_runs()}

    compatibility_identity = {
        "car_id": "car",
        "car_path": "cars/cup",
        "car_version": "1",
        "car_configuration_id": "configuration",
        "iracing_build_version": "build",
        "track_id": "track",
        "track_configuration_name": "oval",
        "track_version": "1",
        "session_type": "test",
    }
    manifest_reads: list[str] = []

    def manifest_for(run_id: str) -> dict[str, object]:
        manifest_reads.append(run_id)
        return {"compatibility_identity": compatibility_identity}

    monkeypatch.setattr(
        service,
        "read_telemetry_manifest",
        manifest_for,
    )
    opportunity = OpportunityEvidence(
        start_pct=20.0,
        end_pct=30.0,
        phase="center",
        observed_time_loss_s=0.2,
        empirical_noise_s=0.04,
        alignment_confidence=0.95,
        repeatable=True,
        evidence_links=tuple(
            TestEvidenceLink(
                event_id=item.event_id,
                eligible_lap=True,
                valid_for_tuning=True,
                phase="center",
                related_setup_keys=("cross_weight_percent",),
            )
            for item in mechanism_events
        ),
        source_channels=("yaw_rate", "lf_tire_pressure", "rf_tire_pressure"),
        supporting_evidence=("Repeated center loss on three eligible laps.",),
    )
    monkeypatch.setattr(
        service,
        "_derive_opportunity",
        lambda *_args, **_kwargs: (opportunity, 1.0, 1.0, True),
    )

    packet = service.build_server_kaizen_packet(
        "source",
        "tight center",
        selected_zone_start_pct=20.0,
        selected_zone_end_pct=30.0,
        selected_phase="center",
        repository=repo,
    )

    assert packet.decision == "test"
    assert packet.primary_test is not None
    assert packet.primary_test.control_key == "cross_weight_percent"
    assert packet.primary_test.proposed_value_raw == 49.5
    assert packet.primary_test.exact_change == (
        "50.0% -> 49.5% (adjacent observed tech-passing option)"
    )
    assert packet.primary_test.proposed_value_provenance == (
        "tech-passing-setup:option-run",
    )
    assert not packet.blockers
    assert manifest_reads == ["source", "option-run"]


def test_repository_round_trips_explicit_learning_admission_outcome(tmp_path) -> None:
    repo = RaceLabRepository(tmp_path / "workflow.sqlite")
    source = _overview("source", "2026-08-04T10:00:00+00:00")
    source.session.source_file = "source.ibt"
    repo.save_import(source)
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="aba-roundtrip", created_at=now, updated_at=now,
        status="scored", source_run_id="source", complaint="tight entry",
        packet=_packet(), learning_admitted=False,
    )

    repo.save_controlled_workflow(workflow)
    loaded = repo.get_controlled_workflow("aba-roundtrip")

    assert loaded is not None
    assert loaded.learning_admitted is False


def test_duplicate_run_import_preserves_controlled_workflow_history(tmp_path) -> None:
    repo = RaceLabRepository(tmp_path / "workflow-reimport.sqlite")
    source = _overview("source", "2026-08-04T10:00:00+00:00")
    source.session.source_file = "source.ibt"
    repo.save_import(source)
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="aba-survives-reimport",
        created_at=now,
        updated_at=now,
        status="scored",
        source_run_id="source",
        complaint="tight entry",
        packet=_packet(),
        stage_run_ids={"A": "source", "B": "source-b", "A2": "source-a2"},
        stage_eligible_lap_numbers={"A": (1, 2, 3), "B": (4, 5, 6), "A2": (7, 8, 9)},
        analysis_version="immutable-history-test",
        execution=TestExecution(
            eligible_laps_a=3,
            eligible_laps_b=3,
            eligible_laps_a2=3,
            unrelated_setup_changes=0,
            control_key="cross_weight_percent",
            planned_b_value=50.5,
            observed_a_value=50.0,
            observed_b_value=50.5,
            observed_a2_value=50.0,
            context_match_score=1.0,
            driver_match_score=1.0,
            sim_integrity_score=1.0,
            phase_effect_b_vs_a_s=-0.05,
            phase_effect_b_vs_a2_s=-0.04,
            empirical_noise_s=0.01,
            minimum_alignment_confidence=0.95,
            target_effect_distributions_consistent=True,
            countereffect_passed=True,
            control_guardrails_passed=True,
        ),
        reproduction_snapshot={
            "certificate_inputs": {"run_ids": ["source", "source-b", "source-a2"]},
            "decision_context": {"selected_zone_start_pct": 20.0, "selected_zone_end_pct": 30.0},
        },
        quality=WorkflowQualityResult(
            protocol_valid=True,
            score=94.0,
            verdict="keep",
            blockers=(),
            supporting_evidence=("A/B/A2 effect reproduced.",),
            contradictory_evidence=(),
            controlled_effect_eligible=True,
        ),
        learning_admitted=False,
    )
    repo.save_controlled_workflow(workflow)
    persisted_before = repo.get_controlled_workflow("aba-survives-reimport")
    assert persisted_before is not None

    source.session.setup_name = "Re-imported setup snapshot"
    repo.save_import(source)

    loaded = repo.get_controlled_workflow("aba-survives-reimport")
    assert loaded is not None
    assert loaded.model_dump(mode="json") == persisted_before.model_dump(mode="json")
    assert loaded.source_run_id == "source"
    assert loaded.status == "scored"
    assert loaded.learning_admitted is False
    refreshed = repo.get_overview("source")
    assert refreshed is not None
    assert refreshed.session.setup_name == "Re-imported setup snapshot"


def test_duplicate_run_import_clears_segments_from_the_previous_analysis(tmp_path) -> None:
    repo = RaceLabRepository(tmp_path / "segment-reimport.sqlite")
    source = _overview("source", "2026-08-04T10:00:00+00:00")
    source.session.source_file = "source.ibt"
    repo.save_import(source)
    repo.save_segments("source", [SegmentSummary(
        segment_id="source:lap:1:0-5",
        run_id="source",
        lap_number=1,
        segment_name="0-5%",
        pct_start=0.0,
        pct_end=5.0,
    )])
    assert [segment.segment_id for segment in repo.list_segments("source")] == [
        "source:lap:1:0-5"
    ]

    source.session.setup_name = "Re-import with a new analysis generation"
    repo.save_import(source)

    assert repo.list_segments("source") == []


def test_scoring_rejects_unequal_eligible_cohorts_before_effect_selection() -> None:
    with pytest.raises(ValueError, match="every eligible trace"):
        service._assert_balanced_eligible_cohorts({"A": 3, "B": 10, "A2": 3})

    service._assert_balanced_eligible_cohorts({"A": 4, "B": 4, "A2": 4})


def test_unequal_aba_cohorts_fail_instead_of_ignoring_eligible_b_laps() -> None:
    lap = [{"lap_dist_pct_100": 50.0}]
    with pytest.raises(ValueError, match="no eligible lap may be ignored"):
        service._controlled_cohort_size({
            "A": [lap, lap, lap],
            "B": [lap] * 10,
            "A2": [lap, lap, lap],
        })


def test_sparse_setup_snapshot_cannot_supply_a_legal_option() -> None:
    current = {
        "cross_weight_percent": 50.0,
        "setup_json": {"Chassis": {"Front": {"CrossWeight": 50.0}}},
    }
    candidate = {
        "cross_weight_percent": 50.5,
        "setup_json": {"Chassis": {"Front": {"CrossWeight": 50.5}}},
    }

    assert service._is_complete_single_control_option(
        current, candidate, "cross_weight_percent",
    ) is False


def test_score_workflow_persists_a_retest_without_learning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="aba-retest", created_at=now, updated_at=now,
        status="a2_recorded", source_run_id="source", complaint="tight entry",
        packet=_packet(), stage_run_ids={"A": "run-a", "B": "run-b", "A2": "run-a2"},
        stage_eligible_lap_numbers={"A": (3, 4, 5), "B": (3, 4, 5), "A2": (3, 4, 5)},
    )

    class ScoreRepo:
        db_path = None

        def __init__(self) -> None:
            self.workflow = workflow
            self.overviews = {
                stage: _overview(stage, f"2026-08-04T{hour:02d}:00:00+00:00")
                for stage, hour in (("source", 12), ("run-a", 13), ("run-b", 14), ("run-a2", 15))
            }
            self.setups = {
                "source": SetupSnapshot(
                    setup_id="setup-source", run_id="source", cross_weight_percent=50.0,
                ),
                "run-a": SetupSnapshot(
                    setup_id="setup-a", run_id="run-a", cross_weight_percent=50.0,
                ),
                "run-b": SetupSnapshot(
                    setup_id="setup-b", run_id="run-b", cross_weight_percent=50.5,
                ),
                "run-a2": SetupSnapshot(
                    setup_id="setup-a2", run_id="run-a2", cross_weight_percent=50.0,
                ),
            }

        def get_controlled_workflow(self, workflow_id: str):
            return self.workflow if workflow_id == self.workflow.workflow_id else None

        def get_overview(self, run_id: str):
            return self.overviews.get(run_id)

        def get_setup_snapshot(self, run_id: str):
            return self.setups.get(run_id)

        def save_controlled_workflow(self, updated: ControlledWorkflow) -> None:
            self.workflow = updated

    repo = ScoreRepo()
    monkeypatch.setattr(
        service,
        "validate_workflow_for_authoritative_use",
        lambda current, **_kwargs: current,
    )
    monkeypatch.setattr(service, "_workflow_decision_context", lambda _workflow: {})
    identity = {"driver_user_id": "driver", "car_id": "car", "track_id": "track"}
    monkeypatch.setattr(
        service,
        "read_telemetry_manifest",
        lambda _run_id: {
            "compatibility_identity": identity,
            "schema_fingerprint": "schema",
            "cache_version": "cache",
        },
    )
    monkeypatch.setattr(
        service,
        "_lap_rows",
        lambda _run_id, lap_numbers: {
            number: [{"lap": number, "lap_dist_pct_100": 25.0}]
            for number in lap_numbers
        },
    )
    monkeypatch.setattr(service, "_context_score", lambda _lap_sets: 1.0)
    monkeypatch.setattr(service, "_driver_similarity", lambda _left, _right: 1.0)
    monkeypatch.setattr(service, "setup_controls_comparable", lambda _left, _right: True)
    monkeypatch.setattr(service, "unmapped_setup_change_paths", lambda _left, _right, _changes: [])
    monkeypatch.setattr(
        service,
        "build_sim_integrity_certificate",
        lambda _rows, **_kwargs: SimpleNamespace(is_clear_for_analysis=True, confidence_cap=1.0),
    )
    monkeypatch.setattr(
        service,
        "analyze_time_alignment",
        lambda _baseline, _test, **_kwargs: SimpleNamespace(
            grid_pct=[25.0],
            phase_by_position=["entry"],
            incremental_delta_s=[-0.02],
            source_channels=["lap_dist_pct_100", "session_time"],
            time_delta_complete=True,
            coverage_fraction=1.0,
            local_alignment_confidence=1.0,
            alignment=[SimpleNamespace(is_gap=False, confidence=1.0)],
            phase_effects=[],
        ),
    )

    scored = service.score_workflow(workflow.workflow_id, repository=repo)

    assert scored.status == "scored"
    assert scored.quality is not None and scored.quality.verdict == "retest"
    assert scored.learning_admitted is not True
    assert scored.reproduction_snapshot["pooled_target_effect_s"] == pytest.approx(-0.02)
    assert repo.workflow == scored


@pytest.mark.parametrize(
    ("b_ahead_m", "b_behind_m"),
    [
        (5.0, 500000.0),
        (500000.0, None),
    ],
    ids=("nearby-in-b", "unknown-in-b"),
)
def test_score_workflow_cannot_certify_or_learn_with_b_only_proximity_context(
    monkeypatch: pytest.MonkeyPatch,
    b_ahead_m: float,
    b_behind_m: float | None,
) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="aba-proximity", created_at=now, updated_at=now,
        status="a2_recorded", source_run_id="source", complaint="tight entry",
        packet=_packet(), stage_run_ids={"A": "run-a", "B": "run-b", "A2": "run-a2"},
        stage_eligible_lap_numbers={"A": (3, 4, 5), "B": (3, 4, 5), "A2": (3, 4, 5)},
    )

    class ScoreRepo:
        db_path = None

        def __init__(self) -> None:
            self.workflow = workflow
            self.overviews = {
                stage: _overview(stage, f"2026-08-04T{hour:02d}:00:00+00:00")
                for stage, hour in (("source", 12), ("run-a", 13), ("run-b", 14), ("run-a2", 15))
            }
            self.setups = {
                "source": SetupSnapshot(setup_id="setup-source", run_id="source", cross_weight_percent=50.0),
                "run-a": SetupSnapshot(setup_id="setup-a", run_id="run-a", cross_weight_percent=50.0),
                "run-b": SetupSnapshot(setup_id="setup-b", run_id="run-b", cross_weight_percent=50.5),
                "run-a2": SetupSnapshot(setup_id="setup-a2", run_id="run-a2", cross_weight_percent=50.0),
            }

        def get_controlled_workflow(self, workflow_id: str):
            return self.workflow if workflow_id == self.workflow.workflow_id else None

        def get_overview(self, run_id: str):
            return self.overviews.get(run_id)

        def get_setup_snapshot(self, run_id: str):
            return self.setups.get(run_id)

        def save_controlled_workflow(self, updated: ControlledWorkflow) -> None:
            self.workflow = updated

    identity = {"driver_user_id": "driver", "car_id": "car", "track_id": "track"}
    monkeypatch.setattr(
        service,
        "validate_workflow_for_authoritative_use",
        lambda current, **_kwargs: current,
    )
    monkeypatch.setattr(service, "_workflow_decision_context", lambda _workflow: {})
    monkeypatch.setattr(service, "read_telemetry_manifest", lambda _run_id: {
        "compatibility_identity": identity, "schema_fingerprint": "schema", "cache_version": "cache",
    })

    def lap_rows(run_id: str, lap_numbers: list[int]) -> dict[int, list[dict[str, object]]]:
        proximity = (
            {"car_distance_ahead_m": b_ahead_m, "car_distance_behind_m": b_behind_m}
            if run_id == "run-b"
            else {"car_distance_ahead_m": 500000.0, "car_distance_behind_m": 500000.0}
        )
        stage = "B" if run_id == "run-b" else "baseline"
        return {
            number: [{
                "lap": number, "lap_dist_pct_100": 25.0, "stage": stage,
                "player_tire_compound": "dry", "tire_sets_used": 1,
                "fuel_level": 50.0, "air_temp": 25.0, "track_temp": 30.0, "wind_vel": 1.0,
                "lf_tire_distance_m": 1000.0, "rf_tire_distance_m": 1000.0,
                "lr_tire_distance_m": 1000.0, "rr_tire_distance_m": 1000.0,
                "speed_mps": 50.0, **proximity,
            }]
            for number in lap_numbers
        }

    def alignment(left: list[dict[str, object]], right: list[dict[str, object]], **_kwargs):
        delta = -0.20 if right[0]["stage"] == "B" else -0.01
        return SimpleNamespace(
            grid_pct=[25.0], phase_by_position=["entry"], incremental_delta_s=[delta],
            source_channels=["lap_dist_pct_100", "session_time"],
            time_delta_complete=True, coverage_fraction=1.0, local_alignment_confidence=1.0,
            alignment=[SimpleNamespace(is_gap=False, confidence=1.0)], phase_effects=[],
        )

    monkeypatch.setattr(service, "_lap_rows", lap_rows)
    monkeypatch.setattr(service, "_driver_similarity", lambda _left, _right: 1.0)
    monkeypatch.setattr(service, "setup_controls_comparable", lambda _left, _right: True)
    monkeypatch.setattr(service, "unmapped_setup_change_paths", lambda _left, _right, _changes: [])
    monkeypatch.setattr(service, "build_sim_integrity_certificate", lambda _rows, **_kwargs: SimpleNamespace(
        is_clear_for_analysis=True, confidence_cap=1.0,
    ))
    monkeypatch.setattr(service, "analyze_time_alignment", alignment)
    monkeypatch.setattr(service, "_score_countereffect_guardrail", lambda *_args, **_kwargs: (True, {}))
    monkeypatch.setattr(service, "_control_guardrail_evaluation", lambda *_args, **_kwargs: (True, {}))

    scored = service.score_workflow(workflow.workflow_id, repository=ScoreRepo())

    assert scored.quality is not None
    assert scored.quality.verdict == "invalid"
    assert scored.quality.controlled_effect_eligible is False
    assert "Context match is below the controlled-test threshold." in scored.quality.blockers
    assert scored.learning_admitted is not True


def test_scoring_rechecks_complete_a2_setup_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="aba-a2-drift", created_at=now, updated_at=now,
        status="a2_recorded", source_run_id="source", complaint="tight entry",
        packet=_packet(), stage_run_ids={"A": "run-a", "B": "run-b", "A2": "run-a2"},
        stage_eligible_lap_numbers={"A": (3, 4, 5), "B": (3, 4, 5), "A2": (3, 4, 5)},
    )

    class DriftRepo:
        db_path = None

        def get_controlled_workflow(self, _workflow_id: str):
            return workflow

        def get_overview(self, _run_id: str):
            return None

        def get_setup_snapshot(self, run_id: str):
            values = {
                "source": (50.0, 50.0),
                "run-a": (50.0, 50.0),
                "run-b": (50.5, 50.0),
                "run-a2": (50.0, 55.0),
            }
            cross, brake = values[run_id]
            return SetupSnapshot(
                setup_id=f"setup-{run_id}", run_id=run_id,
                cross_weight_percent=cross, front_brake_bias_percent=brake,
            )

    monkeypatch.setattr(service, "setup_controls_comparable", lambda _left, _right: True)
    monkeypatch.setattr(service, "unmapped_setup_change_paths", lambda _left, _right, _changes: [])
    monkeypatch.setattr(
        service,
        "validate_workflow_for_authoritative_use",
        lambda current, **_kwargs: current,
    )

    with pytest.raises(ValueError, match="A and A2 must exactly restore"):
        service.score_workflow(workflow.workflow_id, repository=DriftRepo())


def test_scored_workflow_is_immutable() -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="aba-final", created_at=now, updated_at=now,
        status="scored", source_run_id="source", complaint="tight entry",
        packet=_packet(), stage_run_ids={"A": "run-a", "B": "run-b", "A2": "run-a2"},
        stage_eligible_lap_numbers={"A": (3, 4, 5), "B": (3, 4, 5), "A2": (3, 4, 5)},
    )

    class FinalRepo:
        def get_controlled_workflow(self, _workflow_id: str):
            return workflow

    with pytest.raises(ValueError, match="immutable"):
        service.score_workflow(workflow.workflow_id, repository=FinalRepo())
