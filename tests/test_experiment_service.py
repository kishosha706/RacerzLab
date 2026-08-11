from __future__ import annotations

import json

import pytest

from racelab_engine.analysis.test_director import MeasurementMission
from racelab_engine.models.experiment import MeasurementAttempt, SessionResourceSnapshot
from racelab_engine.models.intelligence import InformationPlan
from racelab_engine.services.experiment_service import (
    bind_durable_experiment_lifecycle,
    bind_experiment_lifecycle,
    record_durable_measurement_attempt,
)
from racelab_engine.storage.repository import RaceLabRepository
from racelab_engine.storage.db import initialize_database


MISSION_SCOPE = {
    "session_run_ids": ("run-1",),
    "source_setup_id": "setup-1",
    "setup_sha256": "1" * 64,
    "compatibility_fingerprint": "2" * 64,
    "required_channels": ("speed_mph", "throttle_pct"),
}
SESSION_MISSION_SCOPE = {
    **MISSION_SCOPE,
    "session_id": "session-1",
    "session_run_ids": ("run-1", "run-2"),
}


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
        **MISSION_SCOPE,
        cause_ids=("exit-drive",),
        telemetry_health_identity="health-1",
        resource_snapshot=resources,
    )
    second = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        **MISSION_SCOPE,
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
        **MISSION_SCOPE,
        resource_snapshot=SessionResourceSnapshot(
            remaining_laps=2,
            fuel_laps_available=10.0,
            source="simulator_channels",
        ),
    )
    assert infeasible.kind == "stop_testing"
    assert "infeasible" in infeasible.title.casefold()
    assert infeasible.mission_contract is not None


def test_two_disjoint_cohorts_from_one_run_count_as_one_acquisition() -> None:
    bound = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        **MISSION_SCOPE,
    )
    contract = bound.mission_contract
    assert contract is not None
    attempts = tuple(
        MeasurementAttempt(
            attempt_id=f"attempt-{index}",
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            run_id="run-1",
            setup_id="setup-1",
            setup_sha256=MISSION_SCOPE["setup_sha256"],
            compatibility_fingerprint=MISSION_SCOPE["compatibility_fingerprint"],
            outcome_authority="server_derived",
            eligible_lap_ids=tuple(
                f"run-1:{lap_number}"
                for lap_number in range(index * 3 - 2, index * 3 + 1)
            ),
            outcome="no_signal",
            outcome_reasons=("The declared signal did not exceed the frozen threshold.",),
        )
        for index in (1, 2)
    )
    stopped = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        **MISSION_SCOPE,
        prior_attempts=attempts,
    )
    assert stopped.kind == "measurement_mission"
    assert stopped.mission_contract is not None
    assert stopped.mission_contract.contract_id == contract.contract_id
    assert stopped.mission_contract.contract_sha256 == contract.contract_sha256

    stale = bind_experiment_lifecycle(
        _plan(),
        candidate_id="different-contract",
        run_id="run-1",
        **MISSION_SCOPE,
        prior_attempts=attempts,
    )
    assert stale.kind == "measurement_mission"
    assert stale.mission_contract is not None


def test_two_server_derived_distinct_run_acquisitions_stop_repetition() -> None:
    bound = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        **SESSION_MISSION_SCOPE,
    )
    contract = bound.mission_contract
    assert contract is not None
    attempts = tuple(
        MeasurementAttempt(
            attempt_id=f"attempt-{run_id}",
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            run_id=run_id,
            setup_id=f"setup-{run_id}",
            setup_sha256=MISSION_SCOPE["setup_sha256"],
            compatibility_fingerprint=MISSION_SCOPE["compatibility_fingerprint"],
            outcome_authority="server_derived",
            eligible_lap_ids=tuple(f"{run_id}:{lap}" for lap in (1, 2, 3)),
            outcome="no_signal",
            outcome_reasons=("The server-derived threshold was not crossed.",),
        )
        for run_id in ("run-1", "run-2")
    )

    stopped = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        **SESSION_MISSION_SCOPE,
        prior_attempts=attempts,
    )

    assert stopped.kind == "stop_testing"


def test_client_attested_low_information_cannot_vote_or_break_sequence() -> None:
    bound = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        **SESSION_MISSION_SCOPE,
    )
    contract = bound.mission_contract
    assert contract is not None
    client_attempts = tuple(
        MeasurementAttempt(
            attempt_id=f"client-{run_id}",
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            run_id=run_id,
            setup_id=f"setup-{run_id}",
            setup_sha256=MISSION_SCOPE["setup_sha256"],
            compatibility_fingerprint=MISSION_SCOPE["compatibility_fingerprint"],
            eligible_lap_ids=tuple(f"{run_id}:{lap}" for lap in (1, 2, 3)),
            outcome="no_signal",
            outcome_reasons=("A client claimed no signal.",),
        )
        for run_id in ("run-1", "run-2")
    )

    unchanged = bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        **SESSION_MISSION_SCOPE,
        prior_attempts=client_attempts,
    )

    assert unchanged.kind == "measurement_mission"
    assert all(not attempt.counts_toward_stop_testing for attempt in client_attempts)


def test_client_attested_history_remains_non_authoritative_after_restart(tmp_path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    repository = RaceLabRepository(db_path)
    bound = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=repository,
        **SESSION_MISSION_SCOPE,
    )
    contract = bound.mission_contract
    assert contract is not None
    for run_id in ("run-1", "run-2"):
        record_durable_measurement_attempt(
            contract,
            MeasurementAttempt(
                attempt_id=f"client-{run_id}",
                contract_id=contract.contract_id,
                contract_sha256=contract.contract_sha256,
                run_id=run_id,
                setup_id=f"setup-{run_id}",
                setup_sha256=MISSION_SCOPE["setup_sha256"],
                compatibility_fingerprint=MISSION_SCOPE["compatibility_fingerprint"],
                eligible_lap_ids=tuple(f"{run_id}:{lap}" for lap in (1, 2, 3)),
                outcome="no_signal",
                outcome_reasons=("Client-attested threshold prose.",),
            ),
            repository=repository,
        )

    restarted = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=RaceLabRepository(db_path),
        **SESSION_MISSION_SCOPE,
    )

    assert restarted.kind == "measurement_mission"


def test_disjoint_same_run_history_gets_one_vote_after_restart(tmp_path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    first_repository = RaceLabRepository(db_path)
    first = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=first_repository,
        **SESSION_MISSION_SCOPE,
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
                run_id="run-1",
                setup_id=f"attempt-setup-{index}",
                setup_sha256=MISSION_SCOPE["setup_sha256"],
                compatibility_fingerprint=MISSION_SCOPE["compatibility_fingerprint"],
                outcome_authority="server_derived",
                eligible_lap_ids=tuple(
                    f"run-1:{lap_number}"
                    for lap_number in range(index * 3 - 2, index * 3 + 1)
                ),
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
        **SESSION_MISSION_SCOPE,
    )

    assert restarted.kind == "measurement_mission"
    assert restarted.mission_contract is not None
    assert restarted.mission_contract.contract_sha256 == contract.contract_sha256
    reloaded_repository = RaceLabRepository(db_path)
    assert len(reloaded_repository.list_measurement_mission_attempts(contract)) == 2

    record_durable_measurement_attempt(
        contract,
        MeasurementAttempt(
            attempt_id="attempt-run-2",
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            run_id="run-2",
            setup_id="attempt-setup-run-2",
            setup_sha256=MISSION_SCOPE["setup_sha256"],
            compatibility_fingerprint=MISSION_SCOPE["compatibility_fingerprint"],
            outcome_authority="server_derived",
            eligible_lap_ids=("run-2:1", "run-2:2", "run-2:3"),
            outcome="no_signal",
            outcome_reasons=("The server-derived threshold was not crossed.",),
        ),
        repository=reloaded_repository,
    )
    stopped_after_distinct_acquisition = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=RaceLabRepository(db_path),
        **SESSION_MISSION_SCOPE,
    )

    assert stopped_after_distinct_acquisition.kind == "stop_testing"


def test_overlapping_attempt_replay_cannot_earn_stop_testing_after_restart(tmp_path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    repository = RaceLabRepository(db_path)
    bound = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=repository,
        **MISSION_SCOPE,
    )
    contract = bound.mission_contract
    assert contract is not None
    first = MeasurementAttempt(
        attempt_id="attempt-first",
        contract_id=contract.contract_id,
        contract_sha256=contract.contract_sha256,
        run_id="run-1",
        setup_id="attempt-setup-1",
        setup_sha256=MISSION_SCOPE["setup_sha256"],
        compatibility_fingerprint=MISSION_SCOPE["compatibility_fingerprint"],
        eligible_lap_ids=("run-1:1", "run-1:2", "run-1:3"),
        outcome="no_signal",
        outcome_reasons=("The frozen signal threshold was not crossed.",),
    )
    record_durable_measurement_attempt(contract, first, repository=repository)
    replay = first.model_copy(
        update={
            "attempt_id": "attempt-overlap",
            "eligible_lap_ids": (
                "run-1:3",
                "run-1:4",
                "run-1:5",
            ),
        }
    )

    with pytest.raises(ValueError, match="non-overlapping"):
        record_durable_measurement_attempt(contract, replay, repository=repository)

    restarted = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=RaceLabRepository(db_path),
        **MISSION_SCOPE,
    )
    assert restarted.kind == "measurement_mission"
    assert restarted.mission_contract is not None
    assert restarted.mission_contract.contract_sha256 == contract.contract_sha256


def test_attempt_setup_and_build_identity_must_match_the_immutable_mission(tmp_path) -> None:
    repository = RaceLabRepository(tmp_path / "racelab.sqlite")
    bound = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=repository,
        **MISSION_SCOPE,
    )
    contract = bound.mission_contract
    assert contract is not None
    attempt = MeasurementAttempt(
        attempt_id="attempt-foreign",
        contract_id=contract.contract_id,
        contract_sha256=contract.contract_sha256,
        run_id="foreign-run",
        setup_id="foreign-setup",
        setup_sha256="3" * 64,
        compatibility_fingerprint="4" * 64,
        eligible_lap_ids=("foreign-run:1", "foreign-run:2", "foreign-run:3"),
        outcome="no_signal",
        outcome_reasons=("Foreign evidence must not affect this mission.",),
    )

    with pytest.raises(ValueError, match="setup/build identity"):
        record_durable_measurement_attempt(contract, attempt, repository=repository)
    assert repository.list_measurement_mission_attempts(contract) == ()


def test_legacy_same_scope_mission_history_fails_closed_instead_of_hiding_attempts(
    tmp_path,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    repository = RaceLabRepository(db_path)
    bound = bind_durable_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id="run-1",
        repository=repository,
        **MISSION_SCOPE,
    )
    assert bound.mission_contract is not None
    legacy_payload = {
        "candidate_id": "exit-repeat",
        "run_id": "run-1",
        "session_id": None,
        "purpose": "Old unscoped mission contract",
    }
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            """
            INSERT INTO measurement_mission_contracts (
              contract_id, contract_sha256, created_at, contract_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "mission:legacy-contract",
                "9" * 64,
                "2026-08-01T00:00:00+00:00",
                json.dumps(legacy_payload),
            ),
        )
    connection.close()

    with pytest.raises(ValueError, match="unsupported contract schema"):
        bind_durable_experiment_lifecycle(
            _plan(),
            candidate_id="exit-repeat",
            run_id="run-1",
            repository=RaceLabRepository(db_path),
            **MISSION_SCOPE,
        )
