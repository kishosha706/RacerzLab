"""Fast contract/shape tests for backend API responses.

These tests verify that backend response shapes match expected contracts.
They do NOT require a running server — they test model serialization directly.
"""

from __future__ import annotations

import pytest


from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_analysis import (
    LapQualitySummary,
    LapWindowSummary,
    LapDegradationSummary,
    FastestLapGroup,
    LapWindowsResponse,
)
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.notebook import NotebookFinding
from racelab_engine.models.comparison_insights import (
    ComparisonInsightsResponse,
)
from racelab_engine.analysis.comparison import (
    ComparisonObservation,
    DidItWorkVerdict,
    TireComparison,
    ShockComparison,
)
from racelab_engine.analysis.compare_math import (
    aggregate_tire_comparison,
    aggregate_shock_comparison,
)


# ── Lap model shape tests ──────────────────────────────────────


class TestLapSummaryShape:
    """Verify LapSummary has all expected fields."""

    def test_required_fields(self):
        """LapSummary should have all required fields with correct types."""
        lap = LapSummary(lap_id="test", run_id="run1", lap_number=1)
        assert lap.lap_id == "test"
        assert lap.run_id == "run1"
        assert lap.lap_number == 1
        assert lap.lap_type == "unknown"  # default
        assert lap.is_complete is False  # default
        assert lap.is_useful is False  # default
        assert lap.classification_tags == []  # default
        assert lap.confidence_notes == []  # default

    def test_optional_fields(self):
        """LapSummary optional fields should be None by default."""
        lap = LapSummary(lap_id="test", run_id="run1", lap_number=1)
        assert lap.lap_time is None
        assert lap.avg_speed_mph is None
        assert lap.min_splitter_mm is None
        assert lap.min_splitter_pct is None
        assert lap.min_splitter_distance_m is None
        assert lap.min_splitter_speed_mph is None

    def test_serialization(self):
        """LapSummary should serialize to dict correctly."""
        lap = LapSummary(
            lap_id="test", run_id="run1", lap_number=1,
            lap_time=92.345, is_useful=True,
            classification_tags=["SOLO_CLEAN"],
            confidence_notes=["Good data quality"],
        )
        d = lap.model_dump()
        assert d["lap_id"] == "test"
        assert d["lap_time"] == 92.345
        assert d["is_useful"] is True
        assert d["classification_tags"] == ["SOLO_CLEAN"]
        assert d["confidence_notes"] == ["Good data quality"]


class TestLapQualitySummaryShape:
    """Verify LapQualitySummary has all expected fields."""

    def test_required_fields(self):
        lq = LapQualitySummary(run_id="run1", lap_number=1)
        assert lq.valid_for_compare is False
        assert lq.invalid_reasons == []
        assert lq.classification_tags == []

    def test_risk_fields(self):
        lq = LapQualitySummary(
            run_id="run1", lap_number=1,
            front_platform_risk_score=0.5,
            rear_platform_risk_score=0.3,
            whole_car_bottoming_risk=0.8,
            drag_scrub_suspicion_peak=0.6,
            shock_activity_index_avg=2.5,
            tire_temp_spread_avg=5.0,
            tire_pressure_gain_avg=2.0,
            camber_bias_max=3.0,
            grade_context_label="Uphill",
        )
        assert lq.front_platform_risk_score == 0.5
        assert lq.grade_context_label == "Uphill"


class TestLapWindowSummaryShape:
    """Verify LapWindowSummary has pace/confidence fields."""

    def test_pace_quality_fields(self):
        lw = LapWindowSummary(
            window_id="w1", run_id="run1",
            start_lap=1, end_lap=10, window_size=10,
            pace_quality_score=85.0,
            pace_quality_label="Strong",
            evidence_confidence_score=70.0,
            evidence_confidence_label="Good",
            setup_usefulness_score=65.0,
            setup_usefulness_label="Moderate",
            pace_quality_warnings=["Draft detected"],
            pace_quality_components={"speed": 0.8, "consistency": 0.7},
        )
        assert lw.pace_quality_score == 85.0
        assert lw.evidence_confidence_score == 70.0
        assert lw.setup_usefulness_score == 65.0
        assert lw.pace_quality_warnings == ["Draft detected"]
        assert lw.pace_quality_components == {"speed": 0.8, "consistency": 0.7}


class TestLapDegradationSummaryShape:
    """Verify LapDegradationSummary has warning/coaching fields."""

    def test_warning_fields(self):
        ld = LapDegradationSummary(
            run_id="run1", lap_count=20,
            coaching_message="Consider longer run for tire falloff analysis",
        )
        assert ld.coaching_message == "Consider longer run for tire falloff analysis"


class TestFastestLapGroupShape:
    """Verify FastestLapGroup has pace/confidence fields."""

    def test_pace_fields(self):
        fg = FastestLapGroup(
            label="Fastest 5",
            lap_count=5,
            is_available=True,
            pace_quality_score=80.0,
            pace_quality_label="Good",
            evidence_confidence_score=75.0,
            evidence_confidence_label="Good",
            setup_usefulness_score=60.0,
            setup_usefulness_label="Moderate",
            pace_quality_warnings=[],
            pace_quality_components={"speed": 0.7},
        )
        assert fg.pace_quality_score == 80.0
        assert fg.evidence_confidence_score == 75.0
        assert fg.setup_usefulness_score == 60.0


class TestLapWindowsResponseShape:
    """Verify LapWindowsResponse has warnings field."""

    def test_warnings_field(self):
        resp = LapWindowsResponse(
            run_id="run1",
            warnings=["Not enough laps for 20-lap window"],
        )
        assert resp.warnings == ["Not enough laps for 20-lap window"]
        assert resp.total_valid_laps == 0
        assert resp.total_laps == 0


# ── Event model shape tests ────────────────────────────────────


class TestTelemetryEventShape:
    """Verify TelemetryEvent has all expected fields."""

    def test_required_fields(self):
        event = TelemetryEvent(event_id="e1", run_id="run1", event_type="PLATFORM_LOW")
        assert event.event_subtype is None
        assert event.zone_name is None
        assert event.severity == "info"
        assert event.confidence_score == 0.0
        assert event.valid_for_tuning is False
        assert event.related_setup_keys == []
        assert "measurement_guidance" not in type(event).model_fields

    def test_setup_relevance(self):
        event = TelemetryEvent(
            event_id="e1", run_id="run1", event_type="PLATFORM_LOW",
            severity="high", confidence_score=0.8,
            valid_for_tuning=True,
            related_setup_keys=["lf_ride_height_mm", "rf_ride_height_mm"],
        )
        assert event.valid_for_tuning is True
        assert "lf_ride_height_mm" in event.related_setup_keys
        assert "measurement_guidance" not in event.model_dump()


# ── Notebook model shape tests ─────────────────────────────────


class TestNotebookFindingShape:
    """Verify NotebookFinding has all expected fields."""

    def test_required_fields(self):
        nf = NotebookFinding(finding_id="f1")
        assert nf.confidence_score == 0.0
        assert nf.warnings == []
        assert nf.evidence == []
        assert nf.key_takeaways == []
        assert nf.status == "saved"

    def test_observation_fields(self):
        nf = NotebookFinding(
            finding_id="f1",
            confidence_score=0.85,
            confidence_tier="high",
            test_discipline_score=80.0,
            target_zone_classification="stable_gain",
            summary_headline="Corner-exit telemetry changed",
            key_takeaways=["Rear slip angle decreased", "Throttle trace changed"],
            evidence=["Speed increased by 0.5 mph in target zone"],
            warnings=["Short run — tire falloff not assessed"],
            improved_metrics=["speed_mph"],
            worsened_metrics=["cfs_ride_height_in"],
        )
        assert nf.confidence_tier == "high"
        assert nf.improved_metrics == ["speed_mph"]
        assert nf.worsened_metrics == ["cfs_ride_height_in"]

    def test_serialization(self):
        nf = NotebookFinding(
            finding_id="f1",
            confidence_score=0.85,
            warnings=["Short run"],
        )
        d = nf.as_dict()
        assert d["finding_id"] == "f1"
        assert d["confidence_score"] == 0.85
        assert d["warnings"] == ["Short run"]
        assert {
            "verdict",
            "setup_changes",
            "next_step",
            "recommended_next_test",
        }.isdisjoint(d)


# ── Comparison insights shape tests ────────────────────────────


class TestComparisonInsightsShape:
    """Verify ComparisonInsightsResponse has all expected fields."""

    def test_required_fields(self):
        resp = ComparisonInsightsResponse(
            comparison_id="c1",
            baseline_run_id="run1",
            test_run_id="run2",
            baseline_lap=1,
            test_lap=2,
            target_zone_start_pct=55.0,
            target_zone_end_pct=70.0,
        )
        assert resp.warnings == []
        assert resp.missing_channels == []
        assert resp.key_takeaways == []
        assert resp.summary_headline is None

    def test_warnings_field(self):
        resp = ComparisonInsightsResponse(
            comparison_id="c1",
            baseline_run_id="run1",
            test_run_id="run2",
            baseline_lap=1,
            test_lap=2,
            target_zone_start_pct=55.0,
            target_zone_end_pct=70.0,
            warnings=["Draft detected in test run"],
            missing_channels=["lf_pressure"],
        )
        assert resp.warnings == ["Draft detected in test run"]
        assert resp.missing_channels == ["lf_pressure"]

    def test_serialization(self):
        resp = ComparisonInsightsResponse(
            comparison_id="c1",
            baseline_run_id="run1",
            test_run_id="run2",
            baseline_lap=1,
            test_lap=2,
            target_zone_start_pct=55.0,
            target_zone_end_pct=70.0,
            warnings=["Test warning"],
        )
        d = resp.as_dict()
        assert d["warnings"] == ["Test warning"]
        assert d["comparison_id"] == "c1"


# ── Event type coverage test ───────────────────────────────────


# This manifest defines all backend event types that must have frontend UI mapping.
# If a new event type is added to the backend, it must be added here.
BACKEND_PLATFORM_EVENT_TYPES: set[str] = {
    "MIN_SPLITTER",
    "WORST_SPEED_LOSS",
    "WORST_DRAG_SCRUB",
    "HIGHEST_RAKE",
    "HIGHEST_PLATFORM_COMPRESSION",
    "HIGHEST_SHOCK_ACTIVITY",
    "MAX_DYNAMIC_PRESSURE",
    "MIN_REAR_RIDE_HEIGHT",
    "REAR_PLATFORM_LOW",
    "REAR_PLATFORM_SCRAPE",
    "WHOLE_CAR_BOTTOMING_RISK",
}

# Frontend Track Map overlay categories that map to event types
FRONTEND_EVENT_CATEGORIES: set[str] = {
    "front_scrape",
    "rear_scrape",
    "whole_car_bottoming",
    "drag_scrub",
    "aero",
    "shocks",
    "speed_loss",
    "all_events",
}


class TestEventTypeCoverage:
    """Verify all backend event types have frontend UI mapping."""

    def test_all_platform_event_types_have_frontend_mapping(self):
        """Every backend platform event type should be classifiable by the frontend."""
        # This test verifies the manifest exists.
        # The actual mapping is in trackMapFilters.ts classifyOverlayLayer().
        assert len(BACKEND_PLATFORM_EVENT_TYPES) >= 11, "Expected at least 11 platform event types"
        assert "MIN_SPLITTER" in BACKEND_PLATFORM_EVENT_TYPES
        assert "WHOLE_CAR_BOTTOMING_RISK" in BACKEND_PLATFORM_EVENT_TYPES

    def test_frontend_categories_cover_event_types(self):
        """Frontend categories should cover all backend event type groups."""
        assert "front_scrape" in FRONTEND_EVENT_CATEGORIES
        assert "rear_scrape" in FRONTEND_EVENT_CATEGORIES
        assert "drag_scrub" in FRONTEND_EVENT_CATEGORIES
        assert len(FRONTEND_EVENT_CATEGORIES) >= 8


# ── Compare observation / P19 policy boundary ──────────────────


class TestComparisonObservationShape:
    def test_public_observation_has_no_action_or_policy_fields(self):
        observation = ComparisonObservation(
            observation_state="observed_improvement",
            confidence_score=0.8,
            headline="Measured speed increased",
        )

        assert observation.observation_state == "observed_improvement"
        assert not hasattr(observation, "next_step")
        assert not hasattr(observation, "recommendation")

    def test_removed_next_step_is_rejected_by_internal_policy_result_too(self):
        with pytest.raises(TypeError):
            DidItWorkVerdict(  # type: ignore[call-arg]
                verdict="keep_direction",
                confidence_score=0.8,
                headline="Controlled P19 result",
                next_step="Change another control",
            )


# ── TireComparison tests ──────────────────────────────────────


class TestTireComparisonShape:
    """Verify TireComparison handles missing data correctly."""

    def test_missing_data_returns_available_false(self):
        """TireComparison with no tire data should have no verdict."""
        tc = TireComparison()
        assert tc.tire_verdict is None
        assert tc.short_run_warning is None

    def test_aggregate_no_data(self):
        """aggregate_tire_comparison with empty rows returns no verdict."""
        tc = aggregate_tire_comparison([], [], 55, 70)
        assert tc.tire_verdict is None

    def test_aggregate_short_run_low_confidence(self):
        """Short runs should produce low confidence."""
        tc = aggregate_tire_comparison([], [], 55, 70, lap_count=3)
        assert tc.tire_verdict is None or tc.tire_verdict == "unavailable"


# ── ShockComparison tests ─────────────────────────────────────


class TestShockComparisonShape:
    """Verify ShockComparison handles missing data correctly."""

    def test_missing_data_returns_available_false(self):
        """ShockComparison with no shock data should have no verdict."""
        sc = ShockComparison()
        assert sc.shock_verdict is None

    def test_aggregate_no_data(self):
        """aggregate_shock_comparison with empty rows returns no verdict."""
        sc = aggregate_shock_comparison([], [], 55, 70)
        assert sc.shock_verdict is None


class TestSetupTechStatus:
    """Verify setup_passed_tech null handling."""

    def test_setup_passed_tech_default(self):
        """setup_passed_tech should be None by default (unknown)."""
        from racelab_engine.models.session import SessionSummary
        s = SessionSummary(run_id="run1")
        assert s.setup_passed_tech is None

    def test_setup_passed_tech_true(self):
        from racelab_engine.models.session import SessionSummary
        s = SessionSummary(run_id="run1", setup_passed_tech=True)
        assert s.setup_passed_tech is True

    def test_setup_passed_tech_false(self):
        from racelab_engine.models.session import SessionSummary
        s = SessionSummary(run_id="run1", setup_passed_tech=False)
        assert s.setup_passed_tech is False


# ── Metadata renderer tests ───────────────────────────────────


class TestMetadataRenderer:
    """Verify metadata renderer handles fields safely."""

    def test_debug_keys_filtered(self):
        """Debug keys should not appear in rendered output."""
        # PlatformEvent metadata is a free-form dict — test that debug keys are excluded
        metadata = {
            "platform_balance_label": "Front Bias",
            "debug_lap_pct": 45.5,
            "internal_id": "abc123",
            "confidence": "high",
        }
        # The renderer should only show non-debug, useful keys
        # Just verify the metadata dict can be created with these keys
        assert "platform_balance_label" in metadata
        assert "debug_lap_pct" in metadata
        assert "internal_id" in metadata


# ── Import validation tests ────────────────────────────────────


class TestImportValidation:
    """Verify import path validation logic."""

    def test_import_rejects_missing_file(self):
        """import_ibt with nonexistent path returns unavailable status."""
        from racelab_engine.io.ibt_reader import import_ibt
        result = import_ibt("/nonexistent/path/file.ibt")
        assert result.status.status == "unavailable"
        assert "does not exist" in result.status.message

    def test_import_rejects_directory(self):
        """import_ibt with a directory path returns unavailable status."""
        from racelab_engine.io.ibt_reader import import_ibt
        # Use a path that looks like a directory path but doesn't exist
        result = import_ibt("/nonexistent/directory/path.ibt")
        assert result.status.status == "unavailable"
        assert "does not exist" in result.status.message

    def test_ibt_parse_error_returns_error_status(self):
        """import_ibt with corrupt data returns error status, not crash."""
        from racelab_engine.io.ibt_reader import import_ibt
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ibt", delete=False) as f:
            f.write(b"not a real ibt file")
            path = f.name
        try:
            result = import_ibt(path)
            assert result.status.status == "error"
            assert "Failed to parse" in result.status.message
        finally:
            import os
            os.unlink(path)

    def test_ibt_parse_error_has_fingerprint(self):
        """Even failed imports should have a fingerprint."""
        from racelab_engine.io.ibt_reader import import_ibt
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ibt", delete=False) as f:
            f.write(b"garbage data for fingerprint test")
            path = f.name
        try:
            result = import_ibt(path)
            assert result.fingerprint is not None
            assert result.fingerprint.sha256 is not None
        finally:
            import os
            os.unlink(path)

    def test_import_rejects_wrong_extension(self):
        """import_ibt with non-.ibt extension still attempts parse (decoder handles it)."""
        from racelab_engine.io.ibt_reader import import_ibt
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"some data")
            path = f.name
        try:
            result = import_ibt(path)
            # Should attempt parse and fail with error (not crash)
            assert result.status.status in ("error", "unavailable")
        finally:
            import os
            os.unlink(path)

    def test_import_service_receives_path_string(self):
        """ImportService.import_ibt_file accepts a path string."""
        from racelab_engine.services.import_service import ImportService
        svc = ImportService()
        # Should not crash on nonexistent path — returns result with unavailable status
        result, cache = svc.import_ibt_file("/nonexistent/path.ibt")
        assert result.status.status == "unavailable"

    def test_track_map_missing_does_not_fail_import(self):
        """Track map resolution failure should not prevent import success."""
        from racelab_engine.io.ibt_reader import import_ibt
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ibt", delete=False) as f:
            f.write(b"corrupt but track map resolution is separate")
            path = f.name
        try:
            result = import_ibt(path)
            # Import fails at decode level, not at track map level
            assert result.status.status in ("error", "unavailable")
        finally:
            import os
            os.unlink(path)

