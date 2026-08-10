from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from racelab_engine.evaluation.learning_operations import start_campaign_operation
from racelab_engine.evaluation.prospective import (
    append_prospective_outcome,
    attach_p19_workflow_outcome,
    freeze_p19_controlled_prediction,
    get_prospective_prediction,
    save_prospective_prediction,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.storage.repository import RaceLabRepository


NOW = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)


def _overview() -> RunOverview:
    return RunOverview(
        run_id="baseline",
        session=SessionSummary(
            run_id="baseline",
            file_hash="b" * 64,
            car_path="stockcars chevycamarozl12022",
            track_id_or_path="atlanta-oval",
        ),
        laps=[
            LapSummary(
                lap_id=f"baseline:{number}",
                run_id="baseline",
                lap_number=number,
                is_complete=True,
                is_useful=True,
                lap_time=30.0,
            )
            for number in range(1, 10)
        ],
        setup_snapshot=SetupSnapshot(
            setup_id="setup:baseline",
            run_id="baseline",
            setup_json={"cross_weight": 50.0},
        ),
    )


def _patch_operation_context(monkeypatch):
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.read_telemetry_manifest",
        lambda run_id: {
            "source_file_sha256": "b" * 64,
            "compatibility_identity": {
                "car_path": "stockcars chevycamarozl12022",
                "track_id": "atlanta-oval",
                "iracing_build_version": "2026.08.1",
            },
        },
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.learning_operations.load_lap_engineering_context_report",
        lambda run_id, db_path=None: SimpleNamespace(
            contexts=tuple(
                SimpleNamespace(
                    lap_number=number,
                    fuel_level=SimpleNamespace(
                        start_value=20.0,
                        end_value=20.0,
                        minimum_value=20.0,
                        maximum_value=20.0,
                    ),
                    track_temperature=SimpleNamespace(
                        start_value=40.0,
                        end_value=40.0,
                        minimum_value=40.0,
                        maximum_value=40.0,
                    ),
                    air_temperature=SimpleNamespace(
                        start_value=25.0,
                        end_value=25.0,
                        minimum_value=25.0,
                        maximum_value=25.0,
                    ),
                )
                for number in range(1, 10)
            ),
            status="ready",
        ),
    )


class _Snapshot:
    def __init__(self, plan, *, outcomes=()):
        self.measurement_plan = plan
        self.causes = (SimpleNamespace(hypothesis="Center instability is repeatable."),)
        self.controlled_outcomes = outcomes

    def model_dump(self, mode="json"):
        return {
            "run_id": "baseline",
            "measurement_plan": {
                "kind": self.measurement_plan.kind,
                "setup_authorized": self.measurement_plan.setup_authorized,
            },
            "causes": ["center_instability"],
        }


def _prediction_bundle():
    card = SimpleNamespace(
        control_key="cross_weight",
        direction_sign=1,
        target_phase="center",
        current_value=50.0,
        proposed_value="50.2%",
        hypothesis="Cross weight may stabilize center.",
        expected_mechanism="Center yaw response should become less abrupt.",
        countereffects=("Exit rotation may increase.",),
        success_metrics=("Center correction demand falls beyond noise.",),
        rollback_rule="Undo if exit rotation exceeds the frozen limit.",
        stop_rule="Stop after contamination or unsafe handling.",
    )
    plan = SimpleNamespace(
        kind="controlled_test",
        setup_authorized=True,
        controlled_test=card,
    )
    return SimpleNamespace(report=SimpleNamespace(reasoning_snapshot=_Snapshot(plan)))


def test_prediction_is_frozen_from_p19_before_outcome(tmp_path, monkeypatch):
    database = tmp_path / "prospective.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_operation_context(monkeypatch)
    operation = start_campaign_operation(
        "controlled_setup_response",
        "baseline",
        db_path=database,
        created_at=NOW,
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.prospective.build_run_intelligence",
        lambda *args, **kwargs: _prediction_bundle(),
    )
    with pytest.raises(ValueError, match="frozen operation run"):
        freeze_p19_controlled_prediction(
            operation.operation_id,
            "different-baseline",
            code_hash="c" * 64,
            db_path=database,
        )
    prediction = freeze_p19_controlled_prediction(
        operation.operation_id,
        "baseline",
        code_hash="c" * 64,
        predicted_at=NOW + timedelta(minutes=1),
        db_path=database,
    )
    assert prediction.prospective is True
    assert prediction.ground_truth_available_at_prediction is False
    assert prediction.authority == "shadow_only"
    assert prediction.context["control_key"] == "cross_weight"
    assert prediction.predicted_countereffects == ("Exit rotation may increase.",)
    assert save_prospective_prediction(prediction, db_path=database)
    assert get_prospective_prediction(
        prediction.prediction_id, db_path=database
    ) == prediction
    with pytest.raises(ValueError, match="identity collision"):
        save_prospective_prediction(
            prediction.model_copy(update={"predicted_control_response": "rewritten"}),
            db_path=database,
        )


def test_server_owned_outcome_keeps_mechanism_control_and_policy_separate(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "outcome.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_operation_context(monkeypatch)
    operation = start_campaign_operation(
        "controlled_setup_response",
        "baseline",
        db_path=database,
        created_at=NOW,
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.prospective.build_run_intelligence",
        lambda *args, **kwargs: _prediction_bundle(),
    )
    prediction = freeze_p19_controlled_prediction(
        operation.operation_id,
        "baseline",
        code_hash="c" * 64,
        predicted_at=NOW + timedelta(minutes=1),
        db_path=database,
    )
    save_prospective_prediction(prediction, db_path=database)
    assessment = SimpleNamespace(
        workflow_id="workflow-1",
        mechanism=SimpleNamespace(state="supported"),
        control_response=SimpleNamespace(result="matched"),
        policy=SimpleNamespace(
            verdict="undo",
            countereffects=("Exit rotation exceeded the limit.",),
        ),
        model_dump=lambda mode="json": {
            "workflow_id": "workflow-1",
            "mechanism": {"state": "supported"},
            "control_response": {"result": "matched"},
            "policy": {"verdict": "undo"},
        },
    )
    outcome_plan = SimpleNamespace(kind="blocked", setup_authorized=False)
    outcome_bundle = SimpleNamespace(
        report=SimpleNamespace(
            reasoning_snapshot=_Snapshot(outcome_plan, outcomes=(assessment,))
        )
    )
    monkeypatch.setattr(
        "racelab_engine.evaluation.prospective.build_run_intelligence",
        lambda *args, **kwargs: outcome_bundle,
    )
    workflow = SimpleNamespace(
        workflow_id="workflow-1",
        source_run_id="baseline",
        status="scored",
        updated_at=NOW + timedelta(hours=1),
        stage_run_ids={"A": "baseline", "B": "test", "A2": "restore"},
        quality=SimpleNamespace(protocol_valid=True, controlled_effect_eligible=True),
        learning_admitted=True,
    )

    class _Repository:
        def __init__(self, db_path=None):
            pass

        def get_controlled_workflow(self, workflow_id):
            return workflow if workflow_id == "workflow-1" else None

    monkeypatch.setattr(
        "racelab_engine.evaluation.prospective.RaceLabRepository",
        _Repository,
    )
    outcome = attach_p19_workflow_outcome(
        prediction.prediction_id,
        "workflow-1",
        db_path=database,
    )
    assert outcome.gradable is True
    assert outcome.observed_mechanism == "supported"
    assert outcome.observed_control_response == "matched"
    assert outcome.observed_policy_result == "undo"
    assert outcome.observed_countereffects == (
        "Exit rotation exceeded the limit.",
    )
    assert append_prospective_outcome(outcome, db_path=database)
    assert not append_prospective_outcome(outcome, db_path=database)


def test_prediction_is_rejected_when_b_or_later_truth_already_exists(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "hindsight.sqlite"
    RaceLabRepository(database).save_import(_overview())
    _patch_operation_context(monkeypatch)
    operation = start_campaign_operation(
        "controlled_setup_response",
        "baseline",
        db_path=database,
        created_at=NOW,
    )

    class _Repository:
        def __init__(self, db_path=None):
            pass

        def list_controlled_workflows(self):
            return [
                SimpleNamespace(
                    source_run_id="baseline",
                    stage_run_ids={"A": "baseline", "B": "test"},
                    status="b_recorded",
                )
            ]

    monkeypatch.setattr(
        "racelab_engine.evaluation.prospective.RaceLabRepository",
        _Repository,
    )
    with pytest.raises(ValueError, match="ground truth already exists"):
        freeze_p19_controlled_prediction(
            operation.operation_id,
            "baseline",
            code_hash="c" * 64,
            db_path=database,
        )
