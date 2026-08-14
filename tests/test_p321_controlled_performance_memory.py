from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.analysis.test_director import TestExecution, score_test_execution
from racelab_engine.services.engineering_memory_service import (
    build_prediction_contract,
    build_prediction_grade,
    save_prediction_contract,
    save_prediction_grade,
)
from racelab_engine.services.performance_intelligence_service import _response_records
from racelab_engine.services.run_intelligence_service import _hypotheses
from racelab_engine.services.session_intelligence_service import (
    build_hypothesis_lifecycle,
)
from racelab_engine.services.vehicle_systems_service import build_component_awareness
from racelab_engine.storage.repository import RaceLabRepository
from test_session_intelligence_service import (
    _save_run,
    _scored_workflow,
    _session_with_runs,
    _setup,
)
from test_vehicle_systems_intelligence import _report, _runtime_identity


def _restart_fixture(tmp_path: Path, *, valid: bool):
    label = "valid" if valid else "invalid"
    db_path = tmp_path / f"p321-memory-{label}.sqlite"
    data_dir = tmp_path / f"p321-memory-data-{label}"
    repository = RaceLabRepository(db_path)
    setups = {
        "run-source": _setup("run-source"),
        "run-a": _setup("run-a"),
        "run-b": _setup("run-b", cross=50.5),
        "run-a2": _setup("run-a2"),
    }
    manifests = {
        run_id: _save_run(repository, data_dir, run_id, setup=setup)
        for run_id, setup in setups.items()
    }
    session_id = _session_with_runs(db_path, list(setups))
    workflow = _scored_workflow(
        f"workflow-p321-{label}",
        verdict="keep" if valid else "invalid",
        manifests=manifests,
        setups=setups,
    )
    execution = workflow.execution.model_copy(
        update={
            "time_origin_phase": "initial_throttle",
            "time_origin_pct": 63.4,
            "downstream_carry_effect_s": -0.027,
        }
    )
    workflow = workflow.model_copy(
        update={
            "execution": execution,
            "quality": score_test_execution(execution),
            # P26 history is owned by the final exact workflow/P19 outcome,
            # not by the auxiliary setup-response observation store.
            "learning_admitted": None,
        }
    )
    repository.save_controlled_workflow(workflow)
    contract = build_prediction_contract(workflow)
    save_prediction_contract(contract, db_path=db_path)
    save_prediction_grade(
        build_prediction_grade(workflow, contract),
        db_path=db_path,
    )
    return db_path, data_dir, session_id, workflow


def _public_causes(causes):
    return tuple(
        SimpleNamespace(
            cause_id=cause.cause_id,
            related_control_keys=cause.related_control_keys,
            mechanism_key=cause.mechanism_key,
            mechanism_keys=cause.mechanism_keys,
            controlled_outcomes=cause.controlled_outcomes,
            supporting_evidence=(),
            contradicting_evidence=(),
            status="possible",
            ordinal_rank=index,
            discriminator=None,
        )
        for index, cause in enumerate(causes, start=1)
    )


def test_controlled_origin_requires_one_complete_physical_identity() -> None:
    payload = dict(
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
        time_origin_phase="exit",
    )
    with pytest.raises(ValidationError, match="paired time-origin"):
        TestExecution(**payload)


@pytest.mark.integration
def test_restart_preserves_exact_origin_phase_effect_and_downstream_carry(
    tmp_path: Path,
) -> None:
    db_path, data_dir, session_id, workflow = _restart_fixture(tmp_path, valid=True)

    restarted = RaceLabRepository(db_path)
    loaded = restarted.get_controlled_workflow(workflow.workflow_id)
    assert loaded is not None and loaded.execution is not None
    assert loaded.learning_admitted is None
    assert loaded.execution.time_origin_phase == "initial_throttle"
    assert loaded.execution.time_origin_pct == pytest.approx(63.4)
    assert loaded.execution.downstream_carry_effect_s == pytest.approx(-0.027)

    lifecycle = build_hypothesis_lifecycle(
        session_id,
        db_path=db_path,
        data_dir=data_dir,
    )
    target = lifecycle.entries[0].target_effect
    assert target.actual_effect_s == pytest.approx(-0.05)
    assert target.time_origin_phase == "initial_throttle"
    assert target.time_origin_pct == pytest.approx(63.4)
    assert target.downstream_carry_effect_s == pytest.approx(-0.027)

    causes = _hypotheses(
        None,
        lifecycle=lifecycle,
        workflows=(loaded,),
        current_run_id="run-source",
    )
    outcome = causes[0].controlled_outcomes[0]
    assert outcome.actual_effect_s == pytest.approx(-0.05)
    assert outcome.time_origin_phase == "initial_throttle"
    assert outcome.time_origin_pct == pytest.approx(63.4)
    assert outcome.downstream_carry_effect_s == pytest.approx(-0.027)

    projection = build_component_awareness(
        _report(run_id="run-source", causes=_public_causes(causes)),
        runtime_identity=_runtime_identity("run-source"),
        setup_snapshot=_setup("run-source"),
    )
    history = next(
        item
        for state in projection.component_states
        for item in state.controlled_history
        if item.workflow_id == workflow.workflow_id
    )
    assert history.actual_effect_s == pytest.approx(-0.05)
    assert history.time_origin_phase == "initial_throttle"
    assert history.time_origin_pct == pytest.approx(63.4)
    assert history.downstream_carry_effect_s == pytest.approx(-0.027)

    record = next(
        item
        for item in _response_records(projection)
        if item.workflow_id == workflow.workflow_id
    )
    assert record.phase_effect_s == pytest.approx(-0.05)
    assert record.time_origin == "initial_throttle"
    assert record.time_origin_pct == pytest.approx(63.4)
    assert record.downstream_carry_s == pytest.approx(-0.027)


@pytest.mark.integration
def test_invalid_restart_withholds_performance_memory_from_every_projection(
    tmp_path: Path,
) -> None:
    db_path, data_dir, session_id, workflow = _restart_fixture(tmp_path, valid=False)
    loaded = RaceLabRepository(db_path).get_controlled_workflow(workflow.workflow_id)
    assert loaded is not None
    assert loaded.execution is not None
    assert loaded.execution.time_origin_phase is None
    assert loaded.execution.time_origin_pct is None
    assert loaded.execution.downstream_carry_effect_s is None

    lifecycle = build_hypothesis_lifecycle(
        session_id,
        db_path=db_path,
        data_dir=data_dir,
    )
    target = lifecycle.entries[0].target_effect
    assert target.actual_effect_s is None
    assert target.time_origin_phase is None
    assert target.time_origin_pct is None
    assert target.downstream_carry_effect_s is None

    causes = _hypotheses(
        None,
        lifecycle=lifecycle,
        workflows=(loaded,),
        current_run_id="run-source",
    )
    outcome = causes[0].controlled_outcomes[0]
    assert outcome.verdict == "invalid"
    assert outcome.actual_effect_s is None
    assert outcome.time_origin_phase is None
    assert outcome.time_origin_pct is None
    assert outcome.downstream_carry_effect_s is None

    projection = build_component_awareness(
        _report(run_id="run-source", causes=_public_causes(causes)),
        runtime_identity=_runtime_identity("run-source"),
        setup_snapshot=_setup("run-source"),
    )
    history = next(
        item
        for state in projection.component_states
        for item in state.controlled_history
        if item.workflow_id == workflow.workflow_id
    )
    assert history.exact_context is False
    assert history.actual_effect_s is None
    assert history.time_origin_phase is None
    assert history.time_origin_pct is None
    assert history.downstream_carry_effect_s is None
    assert _response_records(projection) == ()
