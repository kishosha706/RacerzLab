from __future__ import annotations

from racelab_engine.analysis.test_director import MeasurementMission
from racelab_engine.models.experiment import MeasurementAttempt, SessionResourceSnapshot
from racelab_engine.models.intelligence import InformationPlan
from racelab_engine.services.experiment_service import (
    bind_durable_experiment_lifecycle,
    bind_experiment_lifecycle,
    record_durable_measurement_attempt,
)
from racelab_engine.storage.repository import RaceLabRepository


def _plan() -> InformationPlan:
    mission = MeasurementMission(
        purpose="Resolve the repeated exit signal.",
        procedure=("Record three eligible laps with the setup unchanged.",),
        required_laps_or_passes=3,
        controlled_variables=("setup", "fuel", "tires", "traffic"),
        target_phase="exit",
        acceptance_thresholds=("Three eligible laps cover the exact target window.",),
        stop_rule="Stop after an incident or telemetry-integrity failure.",
        blockers=(),
    )
    return InformationPlan(
        kind="measurement_mission",
        title="Repeat the exit window",
        instruction=mission.procedure[0],
        rationale="Resolve one typed measurement debt.",
        measurement_mission=mission,
    )


def test_mission_contract_is_stable_and_resource_aware() -> None:
    resources = SessionResourceSnapshot(
        remaining_laps=10,
        fuel_laps_available=8.5,
        source="simulator_channels",
    )
    first = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        required_channels=("speed_mph", "throttle_pct"),
        cause_ids=("exit-drive",),
        telemetry_health_identity="health-1",
        resource_snapshot=resources,
    )
    second = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        required_channels=("speed_mph", "throttle_pct"),
        cause_ids=("exit-drive",),
        telemetry_health_identity="health-1",
        resource_snapshot=resources,
    )
    assert first.mission_contract is not None
    assert second.mission_contract is not None
    assert first.mission_contract.contract_sha256 == second.mission_contract.contract_sha256

    infeasible = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        resource_snapshot=SessionResourceSnapshot(
            remaining_laps=2,
            fuel_laps_available=10.0,
            source="simulator_channels",
        ),
    )
    assert infeasible.kind == "stop_testing"
    assert "infeasible" in infeasible.title.casefold()
    assert infeasible.mission_contract is not None


def test_two_exact_contract_no_signal_attempts_stop_unchanged_repetition() -> None:
    bound = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
    )
    contract = bound.mission_contract
    assert contract is not None
    attempts = tuple(
        MeasurementAttempt(
            attempt_id=f"attempt-{index}",
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            run_id="run-1",
            outcome="no_signal",
            outcome_reasons=("The declared signal did not exceed the frozen threshold.",),
        )
        for index in (1, 2)
    )
    stopped = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        prior_attempts=attempts,
    )
    assert stopped.kind == "stop_testing"
    assert "repeating" in stopped.title.casefold()
    assert stopped.mission_contract is not None
    assert stopped.mission_contract.contract_id == contract.contract_id
    assert stopped.mission_contract.contract_sha256 == contract.contract_sha256

    stale = bind_experiment_lifecycle(
        _plan(),
        candidate_id="different-contract",
        run_id="run-1",
        prior_attempts=attempts,
    )
    assert stale.kind == "measurement_mission"
    assert stale.mission_contract is not None


def test_durable_attempt_history_reconstructs_stop_testing_after_restart(tmp_path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    first_repository = RaceLabRepository(db_path)
    first = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=first_repository,
    )
    contract = first.mission_contract
    assert contract is not None
    for index in (1, 2):
        record_durable_measurement_attempt(
            contract,
            MeasurementAttempt(
                attempt_id=f"attempt-{index}",
                contract_id=contract.contract_id,
                contract_sha256=contract.contract_sha256,
                run_id=f"attempt-run-{index}",
                outcome="no_signal",
                outcome_reasons=("The declared signal did not exceed the frozen threshold.",),
            ),
            repository=first_repository,
        )

    restarted = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=RaceLabRepository(db_path),
    )

    assert restarted.kind == "stop_testing"
    assert restarted.mission_contract is not None
    assert restarted.mission_contract.contract_sha256 == contract.contract_sha256
