from __future__ import annotations

from api.routes_sessions import _session_picker_payload
from racelab_engine.models.racelab_session import RaceLabSession


def test_session_picker_derives_single_run_context_without_changing_membership() -> None:
    session = RaceLabSession(
        session_id="session-a",
        name="Session 2026-06-20",
        run_ids=["run-a"],
    )

    payload = _session_picker_payload(
        session,
        [{"run_id": "run-a", "track_name": "Bristol", "car_name": "NASCAR Camaro"}],
    )

    assert payload["track_name"] == "Bristol"
    assert payload["car_name"] == "NASCAR Camaro"
    assert payload["run_ids"] == ["run-a"]


def test_session_picker_labels_mixed_context_and_preserves_explicit_names() -> None:
    session = RaceLabSession(
        session_id="session-b",
        name="Session 2026-06-20",
        track_name="Race weekend",
        run_ids=["run-a", "run-b"],
    )

    payload = _session_picker_payload(
        session,
        [
            {"run_id": "run-a", "track_name": "Bristol", "car_name": "NASCAR Camaro"},
            {"run_id": "run-b", "track_name": "Talladega", "car_name": "NASCAR Camaro"},
        ],
    )

    assert payload["track_name"] == "Race weekend"
    assert payload["car_name"] == "NASCAR Camaro"


def test_session_picker_never_invents_missing_run_context() -> None:
    session = RaceLabSession(
        session_id="session-c",
        name="Fresh session",
        run_ids=["missing-run"],
    )

    payload = _session_picker_payload(session, [])

    assert payload["track_name"] is None
    assert payload["car_name"] is None


def test_session_picker_withholds_context_for_partial_or_extra_membership() -> None:
    session = RaceLabSession(
        session_id="session-d",
        name="Two-run session",
        run_ids=["run-a", "run-b"],
    )
    bristol = {"run_id": "run-a", "track_name": "Bristol", "car_name": "NASCAR Camaro"}

    partial = _session_picker_payload(session, [bristol])
    extra = _session_picker_payload(
        session,
        [bristol, {"run_id": "run-c", "track_name": "Talladega", "car_name": "NASCAR Camaro"}],
    )

    assert partial["track_name"] is None
    assert partial["car_name"] is None
    assert extra["track_name"] is None
    assert extra["car_name"] is None
