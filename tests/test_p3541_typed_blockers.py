from __future__ import annotations

from pathlib import Path

from racelab_engine.io.ibt_reader import _build_overview_engineering_blockers
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import (
    EngineeringBlockerSeverity,
    EngineeringBlockTarget,
    EvidenceState,
)
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


def blocked_drag_event() -> TelemetryEvent:
    return TelemetryEvent(
        event_id="drag-1",
        run_id="run-1",
        lap_number=4,
        event_type="FULL_THROTTLE_SPEED_LOSS",
        lap_pct_start=20.0,
        lap_pct_end=40.0,
        lap_pct_peak=32.0,
        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        source_channels=["speed_mph", "car_dist_ahead", "car_dist_behind"],
        blocker_reasons=["Nearby-car context overlaps this window."],
    )


def test_traffic_exposure_blocks_attribution_not_observation_or_performance() -> None:
    blockers = _build_overview_engineering_blockers(
        run_id="run-1",
        missing_channels=[],
        available_channels={"LFshockDefl"},
        proximity_warning="Nearby-car context overlaps this window.",
        drag_events=[blocked_drag_event()],
        invalid_scrapes=[],
    )

    traffic = next(blocker for blocker in blockers if blocker.code == "TRAFFIC_EXPOSURE")
    assert traffic.scope == "relative_resistance"
    assert set(traffic.blocks) == {
        EngineeringBlockTarget.MECHANISM,
        EngineeringBlockTarget.COMPONENT,
        EngineeringBlockTarget.SETUP_ATTRIBUTION,
    }
    assert EngineeringBlockTarget.OBSERVATION not in traffic.blocks
    assert EngineeringBlockTarget.PERFORMANCE not in traffic.blocks
    assert EngineeringBlockTarget.NAVIGATION not in traffic.blocks
    assert traffic.physical_scope is not None
    assert traffic.physical_scope.event_ids == ("drag-1",)


def test_warning_prose_cannot_change_typed_decision_scope() -> None:
    blockers = _build_overview_engineering_blockers(
        run_id="run-1",
        missing_channels=[],
        available_channels={"LFshockDefl"},
        proximity_warning="arbitrary localized prose",
        drag_events=[blocked_drag_event()],
        invalid_scrapes=[],
    )
    traffic = next(blocker for blocker in blockers if blocker.code == "TRAFFIC_EXPOSURE")

    changed = traffic.model_copy(update={"message": "Completely different display text."})
    assert changed.blocks == traffic.blocks
    assert changed.scope == traffic.scope


def test_typed_blockers_round_trip_and_malformed_storage_fails_closed(
    tmp_path: Path,
) -> None:
    database = tmp_path / "racelab.sqlite"
    blocker = _build_overview_engineering_blockers(
        run_id="run-1",
        missing_channels=[],
        available_channels={"LFshockDefl"},
        proximity_warning="Nearby-car context overlaps this window.",
        drag_events=[blocked_drag_event()],
        invalid_scrapes=[],
    )[-1]
    overview = RunOverview(
        run_id="run-1",
        session=SessionSummary(
            run_id="run-1",
            source_file="run.ibt",
            file_hash="a" * 64,
        ),
        engineering_blockers=[blocker],
    )
    repository = RaceLabRepository(database)
    repository.save_import(overview)

    loaded = repository.get_overview("run-1")
    assert loaded is not None
    assert loaded.engineering_blockers == [blocker]

    connection = initialize_database(database)
    with connection:
        connection.execute(
            "UPDATE runs SET engineering_blockers_json = ? WHERE run_id = ?",
            ('[{"code":"forged"}]', "run-1"),
        )
    connection.close()

    failed = RaceLabRepository(database).get_overview("run-1")
    assert failed is not None
    integrity = next(
        item
        for item in failed.engineering_blockers
        if item.code == "STORED_EVIDENCE_INTEGRITY_FAILURE"
    )
    assert integrity.severity == EngineeringBlockerSeverity.CRITICAL
    assert set(integrity.blocks) == set(EngineeringBlockTarget)


def test_legacy_run_without_typed_scope_requires_reimport(tmp_path: Path) -> None:
    database = tmp_path / "racelab.sqlite"
    repository = RaceLabRepository(database)
    repository.save_import(
        RunOverview(
            run_id="run-1",
            session=SessionSummary(run_id="run-1", source_file="run.ibt"),
        )
    )
    connection = initialize_database(database)
    with connection:
        connection.execute(
            "UPDATE runs SET engineering_blockers_json = NULL WHERE run_id = ?",
            ("run-1",),
        )
    connection.close()

    loaded = RaceLabRepository(database).get_overview("run-1")
    assert loaded is not None
    legacy = next(
        item
        for item in loaded.engineering_blockers
        if item.code == "LEGACY_TYPED_BLOCKER_SCOPE_UNAVAILABLE"
    )
    assert set(legacy.blocks) == set(EngineeringBlockTarget)
