from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.intelligence_schemas import MeasurementAttemptRequest
from api.routes_intelligence import record_measurement_attempt
from racelab_engine.analysis.test_director import MeasurementMission
from racelab_engine.models.intelligence import InformationPlan
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.crew_chief_service import _sentinel
from racelab_engine.services.experiment_service import bind_experiment_lifecycle


RUN_ID = "run-mission"
SESSION_ID = "session-mission"
SETUP_SHA256 = "1" * 64
COMPATIBILITY_FINGERPRINT = "2" * 64
SOURCE_SHA256 = "3" * 64


def _plan() -> InformationPlan:
    mission = MeasurementMission(
        purpose="Resolve the exact exit signal.",
        procedure=("Record three eligible laps with setup unchanged.",),
        required_laps_or_passes=3,
        controlled_variables=("setup", "fuel", "tires", "traffic"),
        target_phase="exit",
        acceptance_thresholds=("The exact signal clears its frozen threshold.",),
        stop_rule="Stop after an incident or integrity failure.",
        blockers=(),
    )
    return InformationPlan(
        kind="measurement_mission",
        title="Repeat the exact exit window",
        instruction=mission.procedure[0],
        rationale="Resolve one immutable measurement contract.",
        measurement_mission=mission,
    )


def _contract_plan() -> InformationPlan:
    return bind_experiment_lifecycle(
        _plan(),
        candidate_id="exit-repeat",
        run_id=RUN_ID,
        session_id=SESSION_ID,
        session_run_ids=(RUN_ID,),
        source_setup_id="setup-source",
        setup_sha256=SETUP_SHA256,
        compatibility_fingerprint=COMPATIBILITY_FINGERPRINT,
        required_channels=("speed_mph",),
    )


def _setup(run_id: str, setup_id: str) -> SetupSnapshot:
    return SetupSnapshot(
        setup_id=setup_id,
        run_id=run_id,
        setup_json={"material": {"cross_weight": "50.0%"}},
    )


def _overview(run_id: str, setup: SetupSnapshot) -> SimpleNamespace:
    return SimpleNamespace(
        setup_snapshot=setup,
        session=SimpleNamespace(file_hash=SOURCE_SHA256),
        laps=[
            LapSummary(
                lap_id=f"{run_id}:{lap_number}",
                run_id=run_id,
                lap_number=lap_number,
                lap_type="flying",
                is_complete=True,
                is_useful=True,
                lap_time=30.0,
                sample_count=120,
            )
            for lap_number in (1, 2, 3)
        ],
    )


def _request(*, attempt_run_id: str = RUN_ID) -> MeasurementAttemptRequest:
    contract = _contract_plan().mission_contract
    assert contract is not None
    return MeasurementAttemptRequest(
        session_id=SESSION_ID,
        contract_id=contract.contract_id,
        contract_sha256=contract.contract_sha256,
        attempt_run_id=attempt_run_id,
        outcome="no_signal",
        eligible_lap_ids=[f"{attempt_run_id}:{lap}" for lap in (1, 2, 3)],
        observed_channels=["speed_mph"],
        outcome_reasons=["The frozen signal threshold was not crossed."],
    )


def test_client_cannot_claim_server_derived_outcome_authority() -> None:
    contract = _contract_plan().mission_contract
    assert contract is not None
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        MeasurementAttemptRequest(
            session_id=SESSION_ID,
            contract_id=contract.contract_id,
            contract_sha256=contract.contract_sha256,
            attempt_run_id=RUN_ID,
            outcome="no_signal",
            eligible_lap_ids=[f"{RUN_ID}:{lap}" for lap in (1, 2, 3)],
            observed_channels=["speed_mph"],
            outcome_reasons=["Client prose cannot score the frozen threshold."],
            outcome_authority="server_derived",  # type: ignore[call-arg]
        )


def _install_route_scope(
    monkeypatch: pytest.MonkeyPatch,
    *,
    attempt_setup: SetupSnapshot,
    session_run_ids: tuple[str, ...] = (RUN_ID,),
    channel_health: str = "healthy",
    context_blocked_laps: tuple[int, ...] = (),
    channel_coverage: float = 1.0,
    position_coverage: float = 1.0,
    gapped_position_trace: bool = False,
) -> list[object]:
    plan = _contract_plan()
    overviews = {attempt_setup.run_id: _overview(attempt_setup.run_id, attempt_setup)}
    recorded: list[object] = []

    def intelligence_bundle(run_id: str, **_kwargs: object) -> SimpleNamespace:
        overview = overviews.get(run_id) or _overview(
            run_id,
            _setup(run_id, "setup-attempt"),
        )
        return SimpleNamespace(
            report=SimpleNamespace(
                best_measurement=plan,
                data_quality=SimpleNamespace(
                    eligible_lap_ids=tuple(lap.lap_id for lap in overview.laps),
                ),
                lap_context=SimpleNamespace(
                    contexts=tuple(
                        SimpleNamespace(
                            lap_number=lap.lap_number,
                            blocker_reasons=(),
                            proximity_state=(
                                "nearby_car_ahead"
                                if lap.lap_number in context_blocked_laps
                                else "no_nearby_car_reported"
                            ),
                            proximity_coverage_fraction=1.0,
                            nearby_traffic_exposure_fraction=(
                                1.0 if lap.lap_number in context_blocked_laps else 0.0
                            ),
                        )
                        for lap in overview.laps
                    )
                ),
            )
        )

    def telemetry_rows(
        _run_id: str,
        *,
        lap: int,
        columns: list[str],
    ) -> list[dict[str, object]]:
        del lap
        row_count = 101
        channel_count = int(row_count * channel_coverage)
        position_count = int(row_count * position_coverage)
        rows: list[dict[str, object]] = []
        for index in range(row_count):
            position = (
                float(index) if index < 9 else 100.0
            ) if gapped_position_trace else (
                float(index) if index < position_count else None
            )
            row: dict[str, object] = {
                "lap_dist_pct_100": position,
                "lap_dist_pct": position / 100.0 if position is not None else None,
            }
            for channel in columns:
                if channel not in {"lap", "lap_dist_pct_100", "lap_dist_pct"}:
                    row[channel] = 150.0 if index < channel_count else None
            rows.append(row)
        return rows

    monkeypatch.setattr(
        "api.routes_intelligence.build_run_intelligence",
        intelligence_bundle,
    )
    monkeypatch.setattr(
        "api.routes_intelligence.get_racelab_session",
        lambda _session_id: SimpleNamespace(run_ids=session_run_ids),
    )
    monkeypatch.setattr(
        "api.routes_intelligence.RaceLabRepository",
        lambda: SimpleNamespace(get_overview=lambda run_id: overviews.get(run_id)),
    )
    monkeypatch.setattr(
        "api.routes_intelligence.setup_policy_fingerprint",
        lambda _setup: SETUP_SHA256,
    )
    monkeypatch.setattr(
        "api.routes_intelligence.build_telemetry_capability_payload",
        lambda *_args, **_kwargs: {
            "compatibility_fingerprint": COMPATIBILITY_FINGERPRINT,
            "channels": [
                {
                    "name": "Speed",
                    "canonical_name": "speed_mph",
                    "archive_status": "cached",
                    "health_status": channel_health,
                    "valid_record_count": 360,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "api.routes_intelligence.read_telemetry_rows",
        telemetry_rows,
    )
    monkeypatch.setattr(
        "api.routes_intelligence.record_durable_measurement_attempt",
        lambda _contract, attempt, **_kwargs: recorded.append(attempt),
    )
    return recorded


def test_foreign_run_cannot_supply_a_durable_mission_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_run = "foreign-run"
    _install_route_scope(
        monkeypatch,
        attempt_setup=_setup(foreign_run, "foreign-setup"),
        session_run_ids=(RUN_ID,),
    )

    with pytest.raises(HTTPException, match="outside the immutable mission session"):
        record_measurement_attempt(RUN_ID, _request(attempt_run_id=foreign_run))


def test_no_signal_requires_server_verified_producer_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _install_route_scope(
        monkeypatch,
        attempt_setup=_setup(RUN_ID, "setup-attempt"),
        channel_health="warning",
    )

    with pytest.raises(HTTPException, match="not usable in its verified archive"):
        record_measurement_attempt(RUN_ID, _request())
    assert recorded == []


def test_traffic_blocked_laps_cannot_become_contract_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _install_route_scope(
        monkeypatch,
        attempt_setup=_setup(RUN_ID, "setup-attempt"),
        context_blocked_laps=(1, 2, 3),
    )

    with pytest.raises(HTTPException, match="context-cleared"):
        record_measurement_attempt(RUN_ID, _request())
    assert recorded == []


@pytest.mark.parametrize(
    ("coverage_kind", "expected_message"),
    (
        ("channel", "complete usable coverage"),
        ("position", "complete finite physical-position coverage"),
        ("position_gap", "complete finite physical-position coverage"),
    ),
)
def test_partial_lap_coverage_cannot_become_contract_accepted(
    monkeypatch: pytest.MonkeyPatch,
    coverage_kind: str,
    expected_message: str,
) -> None:
    recorded = _install_route_scope(
        monkeypatch,
        attempt_setup=_setup(RUN_ID, "setup-attempt"),
        channel_coverage=0.99 if coverage_kind == "channel" else 1.0,
        position_coverage=0.99 if coverage_kind == "position" else 1.0,
        gapped_position_trace=coverage_kind == "position_gap",
    )

    with pytest.raises(HTTPException, match=expected_message):
        record_measurement_attempt(RUN_ID, _request())
    assert recorded == []


def test_mutated_session_membership_cannot_expand_an_immutable_mission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _install_route_scope(
        monkeypatch,
        attempt_setup=_setup(RUN_ID, "setup-attempt"),
        session_run_ids=(RUN_ID, "late-added-run"),
    )

    with pytest.raises(HTTPException, match="run membership changed"):
        record_measurement_attempt(RUN_ID, _request())
    assert recorded == []


def test_exact_session_setup_build_and_channel_scope_records_one_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _install_route_scope(
        monkeypatch,
        attempt_setup=_setup(RUN_ID, "setup-attempt"),
    )

    response = record_measurement_attempt(RUN_ID, _request())

    assert response.outcome == "no_signal"
    assert response.outcome_authority == "client_attested"
    assert response.collection_authority == "server_verified"
    assert response.counts_toward_mission_completion is True
    assert response.counts_toward_stop_testing is False
    assert len(recorded) == 1
    attempt = recorded[0]
    assert attempt.run_id == RUN_ID
    assert attempt.setup_id == "setup-attempt"
    assert attempt.setup_sha256 == SETUP_SHA256
    assert attempt.compatibility_fingerprint == COMPATIBILITY_FINGERPRINT
    assert attempt.outcome_authority == "client_attested"
    assert attempt.collection_authority == "server_verified"
    assert attempt.counts_toward_mission_completion is True
    assert attempt.counts_toward_stop_testing is False

    overview = _overview(RUN_ID, _setup(RUN_ID, "setup-attempt"))
    plan = _contract_plan()
    report = SimpleNamespace(
        run_id=RUN_ID,
        best_measurement=plan,
        briefing=SimpleNamespace(success_check="Three contract-qualified laps."),
        data_quality=SimpleNamespace(
            eligible_lap_ids=tuple(lap.lap_id for lap in overview.laps), issues=()
        ),
        lap_context=SimpleNamespace(
            contexts=tuple(
                SimpleNamespace(
                    lap_number=lap.lap_number,
                    blocker_reasons=(),
                    proximity_state="no_nearby_car_reported",
                    proximity_coverage_fraction=1.0,
                    nearby_traffic_exposure_fraction=0.0,
                )
                for lap in overview.laps
            )
        ),
        smart_guidance=None,
    )
    sentinel = _sentinel(
        SimpleNamespace(report=report),
        overview,
        measurement_attempts=(attempt,),
    )
    assert sentinel.mission_acceptance_basis == "p19_measurement_attempt"
    assert sentinel.collection_complete is True
