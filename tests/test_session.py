from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.services.lap_service import (
    classify_lap_type,
    compute_lap_delta,
    find_best_lap,
    format_delta,
    format_lap_time,
    useful_laps,
)
from racelab_engine.services.session_service import (
    add_run_to_session,
    archive_session,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    remove_run_from_session,
    update_session,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_sessions.sqlite"


# ── Lap service tests ────────────────────────────────────────

def test_format_lap_time() -> None:
    assert format_lap_time(29.462) == "0:29.462"
    assert format_lap_time(72.345) == "1:12.345"
    assert format_lap_time(0.0) == "0:00.000"
    assert format_lap_time(None) == "--:--.---"


def test_format_delta() -> None:
    assert format_delta(0.246) == "+0:00.246"
    assert format_delta(-0.118) == "-0:00.118"
    assert format_delta(0.0) == "+0:00.000"
    assert format_delta(None) == ""


def test_compute_lap_delta() -> None:
    assert compute_lap_delta(30.0, 29.5) == 0.5
    assert compute_lap_delta(29.5, 30.0) == -0.5
    assert compute_lap_delta(None, 30.0) is None
    assert compute_lap_delta(30.0, None) is None


def test_find_best_lap() -> None:
    from racelab_engine.models.lap import LapSummary

    laps = [
        LapSummary(lap_id="l1", run_id="r1", lap_number=1, lap_time=30.0, is_useful=True, is_complete=True),
        LapSummary(lap_id="l2", run_id="r1", lap_number=2, lap_time=29.5, is_useful=True, is_complete=True),
        LapSummary(lap_id="l3", run_id="r1", lap_number=3, lap_time=31.0, is_useful=True, is_complete=True),
    ]
    best = find_best_lap(laps)
    assert best is not None
    assert best.lap_number == 2
    assert best.lap_time == 29.5


def test_find_best_lap_excludes_invalid() -> None:
    from racelab_engine.models.lap import LapSummary

    laps = [
        LapSummary(lap_id="l1", run_id="r1", lap_number=1, lap_time=29.0, is_useful=False, is_complete=False),
        LapSummary(lap_id="l2", run_id="r1", lap_number=2, lap_time=30.0, is_useful=True, is_complete=True),
    ]
    best = find_best_lap(laps)
    assert best is not None
    assert best.lap_number == 2


def test_find_best_lap_empty() -> None:
    assert find_best_lap([]) is None


def test_useful_laps() -> None:
    from racelab_engine.models.lap import LapSummary

    laps = [
        LapSummary(lap_id="l1", run_id="r1", lap_number=1, is_useful=True),
        LapSummary(lap_id="l2", run_id="r1", lap_number=2, is_useful=False),
        LapSummary(lap_id="l3", run_id="r1", lap_number=3, is_useful=True),
    ]
    useful = useful_laps(laps)
    assert len(useful) == 2
    assert useful[0].lap_number == 1
    assert useful[1].lap_number == 3


def test_classify_lap_type_out_timed_in() -> None:
    from racelab_engine.models.lap import LapSummary

    laps = [
        LapSummary(lap_id="l1", run_id="r1", lap_number=1, is_useful=False, is_complete=False, lap_time=None),
        LapSummary(lap_id="l2", run_id="r1", lap_number=2, is_useful=True, is_complete=True, lap_time=30.0),
        LapSummary(lap_id="l3", run_id="r1", lap_number=3, is_useful=True, is_complete=True, lap_time=29.5),
        LapSummary(lap_id="l4", run_id="r1", lap_number=4, is_useful=False, is_complete=False, lap_time=None),
    ]
    assert classify_lap_type(laps[0], laps) == "out"
    assert classify_lap_type(laps[1], laps) == "timed"
    assert classify_lap_type(laps[2], laps) == "timed"
    assert classify_lap_type(laps[3], laps) == "in"


def test_classify_lap_type_unknown() -> None:
    from racelab_engine.models.lap import LapSummary

    laps = [
        LapSummary(lap_id="l1", run_id="r1", lap_number=1, is_useful=False, is_complete=False, lap_time=None),
    ]
    assert classify_lap_type(laps[0], laps) == "unknown"


# ── Session service tests ────────────────────────────────────

def test_create_session(db_path: Path) -> None:
    session = create_session(name="Test Session", db_path=db_path)
    assert session.session_id.startswith("session_")
    assert session.name == "Test Session"
    assert session.status == "active"
    assert session.run_ids == []


def test_create_session_default_name(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    assert session.name is not None
    assert session.session_id is not None


def test_get_session(db_path: Path) -> None:
    created = create_session(name="Get Test", db_path=db_path)
    retrieved = get_session(created.session_id, db_path)
    assert retrieved is not None
    assert retrieved.name == "Get Test"
    assert retrieved.session_id == created.session_id


def test_get_session_not_found(db_path: Path) -> None:
    assert get_session("nonexistent", db_path) is None


def test_list_sessions(db_path: Path) -> None:
    create_session(name="S1", db_path=db_path)
    create_session(name="S2", db_path=db_path)
    sessions = list_sessions(db_path=db_path)
    assert len(sessions) == 2


def test_list_sessions_excludes_archived(db_path: Path) -> None:
    s1 = create_session(name="Active", db_path=db_path)
    create_session(name="Archived", db_path=db_path)
    archive_session(s1.session_id, db_path)  # archive the first one
    sessions = list_sessions(db_path=db_path)
    # Only the active one should appear (the one NOT archived)
    assert len(sessions) == 1


def test_list_sessions_include_archived(db_path: Path) -> None:
    s1 = create_session(name="S1", db_path=db_path)
    archive_session(s1.session_id, db_path)
    sessions = list_sessions(include_archived=True, db_path=db_path)
    assert len(sessions) == 1


def test_update_session(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    updated = update_session(session.session_id, name="Renamed", track_name="Talladega", db_path=db_path)
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.track_name == "Talladega"


def test_delete_session(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    deleted = delete_session(session.session_id, db_path)
    assert deleted is True
    assert get_session(session.session_id, db_path) is None


def test_delete_session_not_found(db_path: Path) -> None:
    assert delete_session("nonexistent", db_path) is False


def test_archive_session(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    archived = archive_session(session.session_id, db_path)
    assert archived is not None
    assert archived.status == "archived"


def test_add_run_to_session(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    updated = add_run_to_session(session.session_id, "run_123", db_path)
    assert updated is not None
    assert "run_123" in updated.run_ids
    assert len(updated.run_ids) == 1


def test_add_run_duplicate_is_safe(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    add_run_to_session(session.session_id, "run_123", db_path)
    updated = add_run_to_session(session.session_id, "run_123", db_path)
    assert updated is not None
    assert updated.run_ids == ["run_123"]  # no duplicate


def test_remove_run_from_session(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    add_run_to_session(session.session_id, "run_123", db_path)
    add_run_to_session(session.session_id, "run_456", db_path)
    updated = remove_run_from_session(session.session_id, "run_123", db_path)
    assert updated is not None
    assert "run_123" not in updated.run_ids
    assert "run_456" in updated.run_ids


def test_remove_missing_run_is_safe(db_path: Path) -> None:
    session = create_session(db_path=db_path)
    add_run_to_session(session.session_id, "run_123", db_path)
    updated = remove_run_from_session(session.session_id, "nonexistent", db_path)
    assert updated is not None
    assert updated.run_ids == ["run_123"]


def test_delete_session_does_not_affect_other_sessions(db_path: Path) -> None:
    s1 = create_session(name="S1", db_path=db_path)
    s2 = create_session(name="S2", db_path=db_path)
    delete_session(s1.session_id, db_path)
    remaining = list_sessions(db_path=db_path)
    assert len(remaining) == 1
    assert remaining[0].session_id == s2.session_id
