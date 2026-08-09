from __future__ import annotations

from pathlib import Path

import pytest

from racelab_engine.services.notebook_service import (
    build_setup_memory_summary,
    create_test_plan,
    get_finding,
    list_findings,
    list_test_plans,
    save_finding,
    update_finding,
    update_test_plan,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_notebook.sqlite"


def test_save_and_get_finding(db_path: Path) -> None:
    finding = save_finding(
        car_name="Camaro ZL1",
        track_name="Talladega",
        setup_name="Baseline",
        baseline_run_id="bl_run_1",
        test_run_id="test_run_1",
        comparison_id="comp_1",
        baseline_lap=2,
        test_lap=3,
        target_zone_start_pct=55.0,
        target_zone_end_pct=70.0,
        verdict="keep_direction",
        confidence_score=0.75,
        confidence_tier="high",
        test_discipline_score=88.0,
        target_zone_classification="stable_gain",
        summary_headline="Speed improved with stable platform",
        key_takeaways=["Speed +0.3 mph in target zone", "CFS height unchanged"],
        evidence=["Speed delta: +0.320 mph", "CFS delta: +0.008 in"],
        warnings=[],
        sector_summaries=[{"sector_name": "Sector 1", "avg_speed_delta_mph": 0.15}],
        setup_changes=[{"setup_key": "lf_ride_height_mm", "label": "LF Ride Height", "delta": "+1.0"}],
        context_changes=[{"key": "air_temp", "warning": "Air temp changed"}],
        improved_metrics=["speed_mph"],
        worsened_metrics=[],
        next_step="Confirm with another clean run.",
        notes="Good test.",
        tags=["talladega", "platform"],
        db_path=db_path,
    )
    assert finding.finding_id.startswith("finding_")
    assert finding.verdict == "keep_direction"
    assert finding.car_name == "Camaro ZL1"
    assert finding.track_name == "Talladega"
    assert finding.status == "saved"  # keep_direction -> saved

    # Retrieve
    retrieved = get_finding(finding.finding_id, db_path)
    assert retrieved is not None
    assert retrieved.summary_headline == "Speed improved with stable platform"
    assert len(retrieved.key_takeaways) == 2
    assert retrieved.key_takeaways[0] == "Speed +0.3 mph in target zone"


def test_start_finish_zone_round_trips_without_legacy_default_substitution(
    db_path: Path,
) -> None:
    finding = save_finding(
        comparison_id="start-finish-comparison",
        baseline_run_id="baseline",
        test_run_id="test",
        target_zone_start_pct=0.0,
        target_zone_end_pct=5.0,
        verdict="retest",
        db_path=db_path,
    )

    loaded = get_finding(finding.finding_id, db_path)
    assert loaded is not None
    assert loaded.target_zone_start_pct == 0.0
    assert loaded.target_zone_end_pct == 5.0

    plan = create_test_plan(
        finding.finding_id,
        target_zone_start_pct=0.0,
        target_zone_end_pct=5.0,
        db_path=db_path,
    )
    assert plan is not None
    listed = next(item for item in list_test_plans(db_path=db_path) if item.test_plan_id == plan.test_plan_id)
    assert listed.target_zone_start_pct == 0.0
    assert listed.target_zone_end_pct == 5.0

    updated = update_test_plan(plan.test_plan_id, planned_notes="Start/finish retest", db_path=db_path)
    assert updated is not None
    assert updated.target_zone_start_pct == 0.0
    assert updated.target_zone_end_pct == 5.0


def test_list_findings_with_filters(db_path: Path) -> None:
    save_finding(car_name="Car A", track_name="Track 1", verdict="keep_direction", db_path=db_path)
    save_finding(car_name="Car B", track_name="Track 2", verdict="undo", db_path=db_path)
    save_finding(car_name="Car A", track_name="Track 1", verdict="retest", db_path=db_path)

    all_findings = list_findings(db_path=db_path)
    assert len(all_findings) == 3

    car_a = list_findings(car_name="Car A", db_path=db_path)
    assert len(car_a) == 2

    track_1 = list_findings(track_name="Track 1", db_path=db_path)
    assert len(track_1) == 2

    keep = list_findings(verdict="keep_direction", db_path=db_path)
    assert len(keep) == 1


def test_update_finding_status_and_notes(db_path: Path) -> None:
    finding = save_finding(verdict="retest", db_path=db_path)
    assert finding.status == "needs_retest"  # retest -> needs_retest

    updated = update_finding(finding.finding_id, status="confirmed", notes="Confirmed in second test.", db_path=db_path)
    assert updated is not None
    assert updated.status == "confirmed"
    assert updated.notes == "Confirmed in second test."


def test_create_test_plan_from_finding(db_path: Path) -> None:
    finding = save_finding(
        car_name="Camaro ZL1",
        track_name="Talladega",
        verdict="retest",
        next_step="Try reducing LF ride height by 1mm.",
        db_path=db_path,
    )

    plan = create_test_plan(
        finding.finding_id,
        goal="Reduce LF ride height",
        change_to_try="LF ride height -1mm",
        do_not_change=["RF ride height", "rear springs"],
        success_metric="Speed gain without CFS worsening",
        db_path=db_path,
    )
    assert plan is not None
    assert plan.test_plan_id.startswith("plan_")
    assert plan.car_name == "Camaro ZL1"
    assert plan.track_name == "Talladega"
    assert plan.goal == "Reduce LF ride height"
    assert len(plan.do_not_change) == 2
    assert plan.status == "planned"


def test_list_test_plans(db_path: Path) -> None:
    f1 = save_finding(verdict="retest", next_step="Test 1", db_path=db_path)
    f2 = save_finding(verdict="retest", next_step="Test 2", db_path=db_path)
    create_test_plan(f1.finding_id, goal="Goal 1", db_path=db_path)
    create_test_plan(f2.finding_id, goal="Goal 2", db_path=db_path)

    plans = list_test_plans(db_path=db_path)
    assert len(plans) == 2


def test_update_test_plan_status(db_path: Path) -> None:
    finding = save_finding(verdict="retest", db_path=db_path)
    plan = create_test_plan(finding.finding_id, db_path=db_path)
    assert plan is not None

    updated = update_test_plan(plan.test_plan_id, status="completed", db_path=db_path)
    assert updated is not None
    assert updated.status == "completed"


def test_setup_memory_summary_counts(db_path: Path) -> None:
    save_finding(car_name="Car A", track_name="Track 1", verdict="keep_direction", db_path=db_path)
    save_finding(car_name="Car A", track_name="Track 1", verdict="keep_direction", db_path=db_path)
    save_finding(car_name="Car A", track_name="Track 1", verdict="undo", db_path=db_path)
    save_finding(car_name="Car A", track_name="Track 1", verdict="retest", db_path=db_path)

    summary = build_setup_memory_summary(car_name="Car A", track_name="Track 1", db_path=db_path)
    assert summary.total_findings == 4
    assert summary.keep_count == 2
    assert summary.undo_count == 1
    assert summary.retest_count == 1
    assert summary.inconclusive_count == 0


def test_setup_memory_empty(db_path: Path) -> None:
    summary = build_setup_memory_summary(db_path=db_path)
    assert summary.total_findings == 0
    assert summary.keep_count == 0
    assert summary.latest_finding is None
    assert summary.recommended_next_test is None


def test_save_with_missing_optionals(db_path: Path) -> None:
    """Save finding with minimal fields — should not crash."""
    finding = save_finding(
        verdict="keep_direction",
        db_path=db_path,
    )
    assert finding.finding_id is not None
    assert finding.key_takeaways == []
    assert finding.evidence == []
    assert finding.warnings == []
    assert finding.sector_summaries == []
    assert finding.setup_changes == []
    assert finding.context_changes == []
    assert finding.improved_metrics == []
    assert finding.worsened_metrics == []
    assert finding.tags == []


def test_duplicate_save_creates_new_finding(db_path: Path) -> None:
    """Saving the same comparison twice should create two distinct findings."""
    f1 = save_finding(
        comparison_id="comp_dup_test",
        verdict="keep_direction",
        db_path=db_path,
    )
    f2 = save_finding(
        comparison_id="comp_dup_test",
        verdict="keep_direction",
        db_path=db_path,
    )
    assert f1.finding_id != f2.finding_id
    findings = list_findings(db_path=db_path)
    assert len(findings) == 2


def test_status_default_mapping(db_path: Path) -> None:
    assert save_finding(verdict="keep_direction", db_path=db_path).status == "saved"
    assert save_finding(verdict="undo", db_path=db_path).status == "rejected"
    assert save_finding(verdict="retest", db_path=db_path).status == "needs_retest"
    assert save_finding(verdict="inconclusive", db_path=db_path).status == "needs_retest"
    assert save_finding(verdict=None, db_path=db_path).status == "saved"


def test_notebook_stores_comparison_as_is_no_recompute(db_path: Path) -> None:
    """Notebook must save comparison payload as-is, not recompute or reinterpret."""
    finding = save_finding(
        comparison_id="comp_recompute_test",
        verdict="keep_direction",
        confidence_score=0.75,
        confidence_tier="high",
        key_takeaways=["Speed +0.3 mph"],
        evidence=["Speed delta: +0.320 mph"],
        sector_summaries=[{"sector_name": "S1", "avg_speed_delta_mph": 0.15}],
        db_path=db_path,
    )
    retrieved = get_finding(finding.finding_id, db_path)
    assert retrieved is not None
    # Verdict must be stored verbatim, not reinterpreted
    assert retrieved.verdict == "keep_direction"
    assert retrieved.confidence_tier == "high"
    assert retrieved.key_takeaways == ["Speed +0.3 mph"]
    assert retrieved.sector_summaries == [{"sector_name": "S1", "avg_speed_delta_mph": 0.15}]


def test_settings_compatible_with_local_only(tmp_path: Path) -> None:
    """Verify notebook DB does not connect to remote services."""
    from racelab_engine.storage.db import initialize_database
    db = tmp_path / "test.sqlite"
    conn = initialize_database(db)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = [t[0] for t in tables]
    assert "notebook_findings" in table_names
    assert "test_plans" in table_names
    conn.close()
