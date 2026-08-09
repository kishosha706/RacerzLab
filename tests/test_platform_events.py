from __future__ import annotations

import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import routes_events
from api.main import app
from racelab_engine.analysis.platform_events import (
    PlatformEvent,
    _classify_event_display,
    _event_distance_ft,
    _front_contact_context,
    _rear_contact_context,
    _speed_loss_context,
    _strong_proxy_context,
    _window_support,
    detect_platform_events,
)
from racelab_engine.models.lap import LapSummary
from test_setup_evidence_adapter import _configure_env, _seed_run


def _row(sample_index: int = 0, **overrides: float | int | str | None) -> dict[str, float | int | str | None]:
    row: dict[str, float | int | str | None] = {
        "lap": 1,
        "lap_dist_ft": 100.0 + sample_index * 12.0,
        "lap_dist_pct_100": 20.0 + sample_index * 0.2,
        "speed_mph": 180.0,
        "throttle_pct": 99.0,
        "brake_pct": 0.0,
        "cfs_ride_height_in": 0.75,
        "cfs_risk_score": 0.08,
        "center_rake_fs_in": 1.2,
        "platform_compression_index": 0.0,
        "shock_activity_index": 0.0,
        "lf_shock_velocity_rms": 0.0,
        "rf_shock_velocity_rms": 0.0,
        "lr_shock_velocity_rms": 0.0,
        "rr_shock_velocity_rms": 0.0,
        "rear_min_ride_height_mm": 15.0,
        "rear_min_ride_height_in": 15.0 / 25.4,
        "rear_scrape_margin_mm": 15.0,
        "rear_scrape_risk_score": 0.08,
        "front_platform_risk_score": 0.08,
        "rear_platform_risk_score": 0.08,
        "whole_car_bottoming_risk": 0.08,
        "dynamic_pressure_psf": 120.0,
        "air_density": 1.22,
    }
    row.update(overrides)
    return row


def _event(events: list[PlatformEvent], event_type: str) -> PlatformEvent:
    return next(event for event in events if event.event_type == event_type)


def test_window_support_counts_sustained_span_and_single_frame_contact() -> None:
    rows = [
        _row(sample_index=0, lap_dist_ft=100.0, cfs_ride_height_in=0.18),
        _row(sample_index=1, lap_dist_ft=112.0, cfs_ride_height_in=0.75),
        _row(sample_index=2, lap_dist_ft=124.0, cfs_ride_height_in=0.18),
        _row(sample_index=3, lap_dist_ft=136.0, cfs_ride_height_in=0.18),
        _row(sample_index=4, lap_dist_ft=148.0, cfs_ride_height_in=0.18),
    ]

    sustained = _window_support(
        rows,
        2,
        lambda row: row["cfs_ride_height_in"] is not None and float(row["cfs_ride_height_in"]) <= 0.236,
    )
    one_frame = _window_support(
        rows,
        0,
        lambda row: row["cfs_ride_height_in"] is not None and float(row["cfs_ride_height_in"]) <= 0.236,
    )

    assert sustained == (3, 24.0)
    assert one_frame == (1, 0.0)


def test_contact_and_proxy_context_helpers_gate_driver_visible_events() -> None:
    assert _front_contact_context(_row(cfs_ride_height_in=0.18)) is True
    assert _front_contact_context(_row(cfs_ride_height_in=0.75, cfs_risk_score=0.08)) is False
    assert _rear_contact_context(_row(rear_min_ride_height_mm=5.0, rear_scrape_margin_mm=5.0)) is True
    assert _rear_contact_context(_row(rear_min_ride_height_mm=15.0, rear_scrape_margin_mm=15.0)) is False
    assert _speed_loss_context(_row(speed_rate_mph_1000ft=-1.6)) is True
    assert _speed_loss_context(_row(speed_rate_mph_s=-2.1)) is True
    assert _speed_loss_context(_row(speed_rate_mph_1000ft=-0.2, speed_rate_mph_s=-0.5)) is False
    assert _strong_proxy_context(_row(platform_compression_index=0.71)) is True
    assert _strong_proxy_context(_row(shock_activity_index=5.1)) is True
    assert _strong_proxy_context(_row(drag_scrub_suspicion=0.71)) is True
    assert _strong_proxy_context(_row(platform_compression_index=0.2, shock_activity_index=1.0)) is False


def test_event_distance_uses_fallback_and_keeps_nan_unavailable() -> None:
    fallback = PlatformEvent(
        event_id="fallback",
        event_type="MIN_SPLITTER",
        title="Fallback",
        severity="watch",
        confidence="medium",
        lap=1,
        sample_index=0,
        lap_dist_ft=321.0,
        lap_pct=None,
    )

    assert _event_distance_ft({"lap_dist_m": 10.0}) == pytest.approx(32.80839895)
    assert _event_distance_ft({"lap_dist_ft": math.nan, "lap_dist_m": math.nan}) is None
    assert _event_distance_ft({"lap_dist_ft": None}, fallback=fallback) == 321.0


def test_display_scope_classification_has_no_debug_scope() -> None:
    rows = [_row(cfs_ride_height_in=0.75, cfs_risk_score=0.08)]
    event = PlatformEvent(
        event_id="manual",
        event_type="MAX_DYNAMIC_PRESSURE",
        title="Manual",
        severity="info",
        confidence="high",
        lap=1,
        sample_index=0,
        lap_dist_ft=100.0,
        lap_pct=20.0,
    )

    classified = _classify_event_display(event, rows)

    assert classified.display_scope == "internal"
    assert classified.display_scope != "debug"


def test_highest_shock_activity_is_internal_by_default() -> None:
    events = detect_platform_events([
        _row(
            shock_activity_index=6.4,
            lf_shock_velocity_rms=3.0,
            rf_shock_velocity_rms=3.1,
            lr_shock_velocity_rms=2.9,
            rr_shock_velocity_rms=3.2,
        )
    ])

    event = _event(events, "HIGHEST_SHOCK_ACTIVITY")
    assert event.display_scope == "internal"
    assert event.is_visible_default is False
    assert event.contributes_to_backend_evidence is True


def test_clear_internal_evidence_is_preserved_in_backend_payload() -> None:
    events = detect_platform_events([
        _row(dynamic_pressure_psf=180.0, speed_mph=194.0),
    ])

    event = _event(events, "MAX_DYNAMIC_PRESSURE")
    assert event.severity == "info"
    assert event.display_scope == "internal"
    assert event.is_visible_default is False
    assert event.diagnostic_state == "context"
    assert event.contributes_to_backend_evidence is True


def test_only_explicit_supported_risk_checks_can_be_classified_clear() -> None:
    events = detect_platform_events([_row(platform_compression_index=0.2)])

    assert _event(events, "MIN_SPLITTER").diagnostic_state == "clear_check"
    assert _event(events, "MIN_REAR_RIDE_HEIGHT").diagnostic_state == "clear_check"
    assert _event(events, "WHOLE_CAR_BOTTOMING_RISK").diagnostic_state == "clear_check"
    assert _event(events, "MAX_DYNAMIC_PRESSURE").diagnostic_state == "context"
    assert _event(events, "HIGHEST_PLATFORM_COMPRESSION").diagnostic_state == "context"


def test_highest_platform_compression_is_internal_without_contact_gate() -> None:
    events = detect_platform_events([
        _row(
            platform_compression_index=0.86,
            cfs_risk_score=0.08,
            drag_scrub_suspicion=0.12,
        )
    ])

    event = _event(events, "HIGHEST_PLATFORM_COMPRESSION")
    assert event.display_scope == "internal"
    assert event.reason_for_hidden is not None


def test_highest_center_rake_is_internal_without_driver_facing_impact() -> None:
    events = detect_platform_events([
        _row(
            center_rake_fs_in=2.9,
            cfs_ride_height_in=0.82,
            cfs_risk_score=0.08,
            whole_car_bottoming_risk=0.08,
        )
    ])

    event = _event(events, "HIGHEST_RAKE")
    assert event.display_scope == "internal"
    assert event.is_visible_default is False


def test_whole_car_bottoming_risk_stays_internal_when_not_sustained() -> None:
    events = detect_platform_events([
        _row(
            cfs_ride_height_in=0.35,
            cfs_risk_score=0.38,
            rear_min_ride_height_mm=9.0,
            rear_min_ride_height_in=9.0 / 25.4,
            rear_scrape_margin_mm=9.0,
            rear_scrape_risk_score=0.38,
            front_platform_risk_score=0.38,
            rear_platform_risk_score=0.38,
            whole_car_bottoming_risk=0.38,
        )
    ])

    event = _event(events, "WHOLE_CAR_BOTTOMING_RISK")
    assert event.display_scope == "internal"
    assert event.is_visible_default is False


def test_whole_car_bottoming_risk_becomes_visible_when_repeated() -> None:
    rows = [
        _row(
            sample_index=index,
            cfs_ride_height_in=0.35,
            cfs_risk_score=0.38,
            rear_min_ride_height_mm=9.0,
            rear_min_ride_height_in=9.0 / 25.4,
            rear_scrape_margin_mm=9.0,
            rear_scrape_risk_score=0.38,
            front_platform_risk_score=0.38,
            rear_platform_risk_score=0.38,
            whole_car_bottoming_risk=0.38,
        )
        for index in range(3)
    ]

    events = detect_platform_events(rows)
    event = _event(events, "WHOLE_CAR_BOTTOMING_RISK")
    assert event.display_scope == "watch"
    assert event.is_visible_default is True


def test_true_contact_events_remain_visible() -> None:
    events = detect_platform_events([
        _row(
            cfs_ride_height_in=0.18,
            cfs_risk_score=0.72,
            rear_min_ride_height_mm=2.0,
            rear_min_ride_height_in=2.0 / 25.4,
            rear_scrape_margin_mm=2.0,
            rear_scrape_risk_score=0.92,
            front_platform_risk_score=0.72,
            rear_platform_risk_score=0.92,
            whole_car_bottoming_risk=0.72,
        )
    ])

    assert _event(events, "MIN_SPLITTER").display_scope == "actionable"
    assert _event(events, "REAR_PLATFORM_LOW").display_scope == "actionable"
    assert _event(events, "WHOLE_CAR_BOTTOMING_RISK").display_scope == "actionable"


def test_platform_events_api_includes_display_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_env(monkeypatch, tmp_path)
    _seed_run(
        tmp_path,
        channels={
            "lap_dist_ft": 120.0,
            "lap_dist_pct_100": 24.5,
            "shock_activity_index": 6.2,
            "lf_shock_velocity_rms": 3.2,
            "rf_shock_velocity_rms": 3.1,
            "lr_shock_velocity_rms": 3.0,
            "rr_shock_velocity_rms": 3.3,
        },
    )
    client = TestClient(app)

    response = client.get("/api/runs/run-1/platform-events?lap=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    first = payload[0]
    assert "display_scope" in first
    assert "is_visible_default" in first
    assert "reason_for_hidden" in first
    assert "diagnostic_state" in first
    assert "contributes_to_backend_evidence" in first


def test_platform_event_report_separates_clear_context_findings_and_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repo:
        @staticmethod
        def get_session(_run_id: str) -> object:
            return object()

        @staticmethod
        def get_laps(run_id: str) -> list[LapSummary]:
            return [LapSummary(
                lap_id=f"{run_id}:lap:1", run_id=run_id, lap_number=1,
                lap_type="timed", is_complete=True, is_useful=True, lap_time=30.0,
            )]

    monkeypatch.setattr(routes_events, "repository", lambda: Repo())
    monkeypatch.setattr(routes_events, "_source_signature", lambda run_id: (run_id,))
    routes_events._PLATFORM_EVENTS_CACHE.clear()

    def platform_event(run_id: str) -> PlatformEvent:
        state_by_run = {
            "clear": ("MIN_SPLITTER", "clear_check", "internal"),
            "context": ("MAX_DYNAMIC_PRESSURE", "context", "internal"),
            "finding": ("MIN_SPLITTER", "finding", "watch"),
        }
        event_type, diagnostic_state, display_scope = state_by_run[run_id]
        return PlatformEvent(
            event_id=run_id,
            event_type=event_type,
            title=run_id,
            severity="info" if display_scope == "internal" else "watch",
            confidence="high",
            lap=1,
            sample_index=0,
            lap_dist_ft=100.0,
            lap_pct=20.0,
            diagnostic_state=diagnostic_state,
            display_scope=display_scope,
            is_visible_default=display_scope != "internal",
        )

    monkeypatch.setattr(
        routes_events,
        "read_telemetry_rows",
        lambda run_id, **_kwargs: (
            [] if run_id == "missing" else [{"run_id": run_id, "lap": 1}]
        ),
    )
    monkeypatch.setattr(
        routes_events,
        "detect_platform_events",
        lambda rows, **_kwargs: [platform_event(str(rows[0]["run_id"]))],
    )

    clear = routes_events.get_platform_events_report("clear")
    assert clear.run_id == "clear"
    assert clear.lap is None
    assert clear.evidence_status == "clear"
    assert routes_events.get_platform_events_report("finding").evidence_status == "findings"
    context = routes_events.get_platform_events_report("context")
    assert context.evidence_status == "unavailable"
    assert context.blocker_reasons
    missing = routes_events.get_platform_events_report("missing")
    assert missing.evidence_status == "unavailable"
    assert "No telemetry rows" in missing.blocker_reasons[0]


def test_platform_event_report_withholds_events_from_a_different_requested_lap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repo:
        @staticmethod
        def get_session(_run_id: str) -> object:
            return object()

        @staticmethod
        def get_laps(run_id: str) -> list[LapSummary]:
            return [LapSummary(
                lap_id=f"{run_id}:lap:5", run_id=run_id, lap_number=5,
                lap_type="timed", is_complete=True, is_useful=True, lap_time=30.0,
            )]

    monkeypatch.setattr(routes_events, "repository", lambda: Repo())
    monkeypatch.setattr(routes_events, "_source_signature", lambda run_id: (run_id,))
    monkeypatch.setattr(
        routes_events,
        "read_telemetry_rows",
        lambda *_args, **_kwargs: [{"run_id": "run-a", "lap": 5}],
    )
    monkeypatch.setattr(
        routes_events,
        "detect_platform_events",
        lambda *_args, **_kwargs: [PlatformEvent(
            event_id="wrong-lap",
            event_type="MIN_SPLITTER",
            title="Wrong lap",
            severity="watch",
            confidence="high",
            lap=7,
            sample_index=0,
            lap_dist_ft=100.0,
            lap_pct=20.0,
            diagnostic_state="finding",
            display_scope="watch",
        )],
    )
    routes_events._PLATFORM_EVENTS_CACHE.clear()

    report = routes_events.get_platform_events_report("run-a", lap=5)

    assert report.run_id == "run-a"
    assert report.lap == 5
    assert report.evidence_status == "unavailable"
    assert report.events == []
    assert "requested lap" in report.blocker_reasons[0]


def test_platform_event_report_rejects_a_cooldown_lap_before_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Repo:
        @staticmethod
        def get_session(_run_id: str) -> object:
            return object()

        @staticmethod
        def get_laps(run_id: str) -> list[LapSummary]:
            return [LapSummary(
                lap_id=f"{run_id}:lap:52", run_id=run_id, lap_number=52,
                lap_type="invalid", is_complete=True, is_useful=False, lap_time=39.7,
                classification_tags=["COOLDOWN", "NO_SETUP_CONCLUSION"],
            )]

    monkeypatch.setattr(routes_events, "repository", lambda: Repo())
    monkeypatch.setattr(
        routes_events,
        "read_telemetry_rows",
        lambda *_args, **_kwargs: pytest.fail("Ineligible lap telemetry must not be analyzed."),
    )

    report = routes_events.get_platform_events_report("cooldown", lap=52)

    assert report.evidence_status == "unavailable"
    assert report.events == []
    assert "Cool-down or abnormally slow lap" in report.blocker_reasons[0]
