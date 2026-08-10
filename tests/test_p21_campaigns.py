from __future__ import annotations

from datetime import datetime, timedelta, timezone

from racelab_engine.evaluation.campaigns import (
    append_campaign_attempt,
    build_campaign_attempt,
    campaign_progress,
    initial_campaigns,
    save_campaign,
)


NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)


def _driver_campaign():
    return next(
        campaign
        for campaign in initial_campaigns(created_at=NOW)
        if campaign.campaign_kind == "driver_noise_baseline"
    )


def _usable_attempt(campaign, unit_id: str, offset: int = 0):
    return build_campaign_attempt(
        campaign,
        {
            "recorded_at": NOW + timedelta(minutes=offset),
            "outcome": "usable",
            "independence_unit_id": unit_id,
            "independence_level": "session",
            "source_run_ids": (f"run-{unit_id}",),
            "source_session_ids": (unit_id,),
            "source_file_fingerprints": (f"{offset + 1:064x}",),
            "eligible_lap_count": 10,
            "context_keys": ("matched_setup", "matched_tire_fuel_weather"),
            "available_telemetry": (
                "lap_time",
                "track_position",
                "driver_inputs",
            ),
            "setup_snapshot_present": True,
        },
    )


def test_initial_campaigns_cover_all_required_questions():
    campaigns = initial_campaigns(created_at=NOW)
    assert {campaign.campaign_kind for campaign in campaigns} == {
        "driver_noise_baseline",
        "controlled_setup_response",
        "tire_update_semantics",
        "long_run_development",
        "vehicle_geometry_validation",
        "control_workload",
        "no_change_null",
    }
    assert all(campaign.authority_ceiling == "data_collection_only" for campaign in campaigns)
    assert all("setup_authority" in campaign.forbidden_outputs for campaign in campaigns)


def test_duplicate_attempts_do_not_inflate_independence_progress(tmp_path):
    campaign = _driver_campaign()
    database = tmp_path / "campaign.sqlite"
    assert save_campaign(campaign, db_path=database)
    first = _usable_attempt(campaign, "session-1")
    duplicate_unit = _usable_attempt(campaign, "session-1", offset=1)
    assert append_campaign_attempt(first, db_path=database)
    assert append_campaign_attempt(duplicate_unit, db_path=database)
    progress = campaign_progress(campaign, db_path=database)
    assert progress.usable_attempts == 2
    assert progress.independent_units == 1
    assert progress.eligible_laps == 10
    assert progress.remaining_independent_units == 2


def test_campaign_completes_only_with_unique_qualified_units(tmp_path):
    campaign = _driver_campaign()
    database = tmp_path / "campaign.sqlite"
    save_campaign(campaign, db_path=database)
    for index in range(1, 4):
        append_campaign_attempt(
            _usable_attempt(campaign, f"session-{index}", offset=index),
            db_path=database,
        )
    progress = campaign_progress(campaign, db_path=database)
    assert progress.complete
    assert progress.independent_units == 3
    assert progress.eligible_laps == 30
    assert not progress.blockers


def test_missing_context_or_snapshot_becomes_invalid_attempt(tmp_path):
    campaign = _driver_campaign()
    database = tmp_path / "campaign.sqlite"
    save_campaign(campaign, db_path=database)
    attempt = build_campaign_attempt(
        campaign,
        {
            "recorded_at": NOW,
            "outcome": "usable",
            "independence_unit_id": "session-bad",
            "independence_level": "session",
            "eligible_lap_count": 10,
            "context_keys": ("matched_setup",),
            "available_telemetry": ("lap_time",),
            "setup_snapshot_present": False,
        },
    )
    assert attempt.outcome == "invalid"
    assert len(attempt.invalid_reasons) == 3
    append_campaign_attempt(attempt, db_path=database)
    progress = campaign_progress(campaign, db_path=database)
    assert progress.invalid_attempts == 1
    assert progress.independent_units == 0


def test_failed_a2_restoration_cannot_become_usable_evidence():
    campaign = next(
        campaign
        for campaign in initial_campaigns(created_at=NOW)
        if campaign.campaign_kind == "controlled_setup_response"
    )
    attempt = build_campaign_attempt(
        campaign,
        {
            "recorded_at": NOW,
            "outcome": "usable",
            "independence_unit_id": "workflow-1",
            "independence_level": "controlled_workflow",
            "source_workflow_ids": ("workflow-1",),
            "eligible_lap_count": 9,
            "context_keys": ("exact_context", "one_control", "a2_restoration"),
            "available_telemetry": (
                "lap_time",
                "target_metric",
                "countereffects",
            ),
            "setup_snapshot_present": True,
            "restoration_passed": False,
        },
    )
    assert attempt.outcome == "invalid"
    assert "Attempt lacks proven A2 restoration." in attempt.invalid_reasons
