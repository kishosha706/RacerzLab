from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from racelab_engine.evaluation.activation_gates import (
    ActivationEvidence,
    evaluate_activation_gate,
    p22_field_activation_gates,
)
from racelab_engine.evaluation.campaigns import campaign_progress, initial_campaigns
from racelab_engine.evaluation.learning_operations import (
    acquisition_options,
    append_operation_event,
    assess_active_operations_for_run,
    build_operation_event,
    learning_ledger,
    operation_state,
    start_campaign_operation,
    transition_campaign_operation,
)
from racelab_engine.evaluation.readiness import build_learning_readiness_projection
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.storage.repository import RaceLabRepository


NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
SOURCE = "a" * 64


def _overview(run_id: str = "run-1", *, file_hash: str = SOURCE) -> RunOverview:
    laps = [
        LapSummary(
            lap_id=f"{run_id}:lap:{number}",
            run_id=run_id,
            lap_number=number,
            is_complete=True,
            is_useful=True,
            lap_time=30.0,
            pct_min=0.0,
            pct_max=100.0,
            pct_span=100.0,
            sample_count=100,
            avg_throttle_pct=80.0,
            avg_brake_pct=2.0,
            avg_abs_steering_deg=3.0,
        )
        for number in range(1, 11)
    ]
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            file_hash=file_hash,
            car_path="stockcars chevycamarozl12022",
            track_id_or_path="atlanta-oval",
        ),
        laps=laps,
        setup_snapshot=SetupSnapshot(
            setup_id=f"setup:{run_id}",
            run_id=run_id,
            setup_name="S17",
            setup_json={"cross_weight": 50.0},
        ),
    )


def _semantic(value: float):
    return SimpleNamespace(
        start_value=value,
        end_value=value,
        minimum_value=value,
        maximum_value=value,
    )


def _context_report(run_id: str, *, traffic: float = 0.0):
    contexts = tuple(
        SimpleNamespace(
            lap_number=number,
            blocker_reasons=(),
            nearby_traffic_exposure_fraction=traffic,
            fuel_level=_semantic(20.0),
            track_temperature=_semantic(40.0),
            air_temperature=_semantic(25.0),
        )
        for number in range(1, 11)
    )
    return SimpleNamespace(contexts=contexts, status="ready")


def _patch_run(monkeypatch, run_id: str = "run-1", *, traffic: float = 0.0):
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.read_telemetry_manifest",
        lambda selected: {
            "source_file_sha256": SOURCE,
            "compatibility_identity": {
                "car_path": "stockcars chevycamarozl12022",
                "track_id": "atlanta-oval",
                "iracing_build_version": "2026.08.1",
            },
        },
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.load_lap_engineering_context_report",
        lambda selected, db_path=None: _context_report(selected, traffic=traffic),
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.read_telemetry_rows",
        lambda selected, columns=None: [],
    )


def test_campaign_operation_lifecycle_is_append_only_and_validated(tmp_path, monkeypatch):
    database = tmp_path / "operations.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_run(monkeypatch)
    operation = start_campaign_operation(
        "driver_noise_baseline",
        "run-1",
        db_path=database,
        created_at=NOW,
    )
    assert operation.authority == "data_collection_only"
    assert operation_state(operation.operation_id, db_path=database) == "active"
    with pytest.raises(ValueError, match="Cannot append started"):
        append_operation_event(
            build_operation_event(operation, "started", "Invalid second start."),
            db_path=database,
        )
    paused = transition_campaign_operation(
        operation.operation_id,
        "paused",
        "Waiting for a fresh independent simulator session.",
        db_path=database,
        # Equal timestamps are valid; append order, not a hash tie-breaker,
        # preserves the causal lifecycle.
        recorded_at=NOW,
    )
    assert paused.event_type == "paused"
    assert operation_state(operation.operation_id, db_path=database) == "paused"
    with pytest.raises(ValueError, match="Cannot record paused"):
        transition_campaign_operation(
            operation.operation_id,
            "paused",
            "Duplicate transition",
            db_path=database,
        )
    forged = paused.model_copy(update={"reason": "rewritten"})
    with pytest.raises(ValueError):
        append_operation_event(forged, db_path=database)


def test_automatic_assessment_promotes_only_clean_independent_run(tmp_path, monkeypatch):
    database = tmp_path / "qualification.sqlite"
    repo = RaceLabRepository(database)
    repo.save_import(_overview())
    _patch_run(monkeypatch)
    operation = start_campaign_operation(
        "driver_noise_baseline",
        "run-1",
        db_path=database,
        created_at=NOW,
    )
    assessments = assess_active_operations_for_run("run-1", db_path=database)
    assert len(assessments) == 1
    assert assessments[0].state == "usable"
    assert assessments[0].promoted_to_p21_attempt is True
    assert assessments[0].accepted_lap_numbers == tuple(range(1, 11))
    campaign = next(
        item
        for item in initial_campaigns()
        if item.campaign_kind == "driver_noise_baseline"
    )
    progress = campaign_progress(campaign, db_path=database)
    assert progress.independent_units == 1
    assert progress.eligible_laps == 10
    # Re-running the import hook returns the immutable assessment and cannot
    # manufacture a second independent unit.
    again = assess_active_operations_for_run("run-1", db_path=database)
    assert again == assessments
    assert campaign_progress(campaign, db_path=database).independent_units == 1
    assert operation_state(operation.operation_id, db_path=database) == "active"


def test_traffic_contamination_is_rejected_and_never_counts(tmp_path, monkeypatch):
    database = tmp_path / "traffic.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_run(monkeypatch, traffic=0.4)
    start_campaign_operation(
        "driver_noise_baseline",
        "run-1",
        db_path=database,
        created_at=NOW,
    )
    assessment = assess_active_operations_for_run("run-1", db_path=database)[0]
    assert assessment.state == "rejected"
    assert not assessment.accepted_lap_numbers
    assert assessment.rejected_lap_numbers == tuple(range(1, 11))
    assert "nearby-car context" in assessment.lap_rejection_reasons[1][0]
    assert assessment.promoted_to_p21_attempt is False
    campaign = next(
        item
        for item in initial_campaigns()
        if item.campaign_kind == "driver_noise_baseline"
    )
    assert campaign_progress(campaign, db_path=database).independent_units == 0


def test_applied_brake_bias_change_invalidates_campaign_unit(tmp_path, monkeypatch):
    database = tmp_path / "control-change.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_run(monkeypatch)
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.read_telemetry_rows",
        lambda selected, columns=None: [
            {
                "session_time": 1.0,
                "lap": 1,
                "lap_dist_pct_100": 10.0,
                "applied_brake_bias": 43.5,
            },
            {
                "session_time": 2.0,
                "lap": 2,
                "lap_dist_pct_100": 10.0,
                "applied_brake_bias": 44.0,
            },
        ],
    )
    start_campaign_operation(
        "driver_noise_baseline",
        "run-1",
        db_path=database,
        created_at=NOW,
    )
    assessment = assess_active_operations_for_run("run-1", db_path=database)[0]
    assert assessment.state == "rejected"
    assert assessment.control_mutation_ids
    assert "control changed" in " ".join(assessment.rejection_reasons).casefold()


def test_learning_ledger_separates_guardrails_from_empirical_validation(tmp_path):
    entries = learning_ledger(db_path=tmp_path / "ledger.sqlite")
    proven = [item for item in entries if item.section == "proven_guardrail"]
    validation = [item for item in entries if item.section == "in_validation"]
    locked = [item for item in entries if item.section == "locked"]
    assert proven and all(item.evidence_basis == "verified_architecture" for item in proven)
    assert len(validation) == 7
    assert all(item.current == 0 for item in validation)
    assert locked and all(item.authority == "p19_p20_unchanged" for item in locked)


def test_acquisition_director_is_deterministic_inspectable_and_non_authoritative(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "director.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_run(monkeypatch)
    options = acquisition_options("run-1", db_path=database)
    highest = [option for option in options if option.state == "highest"]
    assert len(highest) == 1
    assert all(option.score.formal_information_gain is False for option in options)
    assert all(option.authority == "collection_guidance_only" for option in options)
    geometry = next(
        option
        for option in options
        if option.campaign_kind == "vehicle_geometry_validation"
    )
    assert geometry.state == "infeasible"
    assert "external source-validation" in geometry.blockers[0]
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.load_lap_engineering_context_report",
        lambda selected, db_path=None: SimpleNamespace(contexts=(), status="limited"),
    )
    without_context = acquisition_options("run-1", db_path=database)
    driver_noise = next(
        option
        for option in without_context
        if option.campaign_kind == "driver_noise_baseline"
    )
    assert driver_noise.state == "infeasible"
    assert "cannot be frozen" in " ".join(driver_noise.blockers)


def test_capability_review_does_not_preselect_an_unlock(tmp_path, monkeypatch):
    database = tmp_path / "review.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_run(monkeypatch)
    projection = build_learning_readiness_projection("run-1", db_path=database)
    assert projection.capability_review is not None
    assert projection.capability_review.decision == "remain_locked"
    assert projection.capability_review.eligible_capability_key is None
    assert projection.capability_review.manual_selection is False
    assert projection.active_campaigns == ()


def test_p22_gate_policy_allows_no_planner_or_optimizer_shortcut():
    gates = {gate.capability_key: gate for gate in p22_field_activation_gates()}
    assert gates["driver_noise_envelope"].maximum_state == "eligible_for_limited_activation"
    assert gates["change_point"].maximum_state == "eligible_for_limited_activation"
    assert gates["formal_information_gain"].maximum_state == "eligible_for_prospective_shadow"
    assert gates["bayesian_optimization"].maximum_state == "shadow"
    assert gates["multi_control_optimization"].maximum_state == "shadow"
    assert all(gate.manual_override_allowed is False for gate in gates.values())
    empty = ActivationEvidence(
        dataset_counts={},
        counts={},
        ready_prerequisites=(),
        prospective_units=0,
        dataset_hashes=(),
        code_hash="deadbee",
    )
    decisions = [evaluate_activation_gate(gate, empty) for gate in gates.values()]
    assert all(decision.state == "locked_insufficient_data" for decision in decisions)
