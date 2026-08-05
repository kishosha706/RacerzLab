from __future__ import annotations

from racelab_engine.services.insight_service import build_comparison_insights


def _rows(
    speed_mph: float,
    *,
    speed_slope: float = 0.0,
    rpm_slope: float = 0.0,
) -> list[dict[str, float]]:
    return [
        {
            "lap_dist_pct_100": float(index),
            "lap_dist_ft": float(index * 50),
            "speed_mph": speed_mph + index * speed_slope,
            "cfs_ride_height_in": 0.20,
            "abs_steering_deg": 0.5,
            "drag_scrub_suspicion": 0.1,
            "rpm": 7000.0 + index * rpm_slope,
        }
        for index in range(101)
    ]


def test_insights_show_measured_change_but_suppress_causal_setup_classification() -> None:
    result = build_comparison_insights(
        comparison_id="cmp-test",
        baseline_run_id="baseline",
        test_run_id="test",
        baseline_lap=1,
        test_lap=1,
        baseline_rows=_rows(180.0),
        test_rows=_rows(181.0, speed_slope=0.01, rpm_slope=10.0),
        channels=[
            "speed_mph",
            "cfs_ride_height_in",
            "abs_steering_deg",
            "drag_scrub_suspicion",
            "rpm",
        ],
        causal_attribution_blocked=True,
        causal_block_reason="A car behind was observed within 0.50 seconds.",
        causal_block_reasons=["Test lap 2: car behind at 0.48 seconds."],
        causal_retest_instruction="Repeat with no car within 0.5 seconds behind.",
    )

    assert result.target_zone_classification.classification == "inconclusive"
    assert result.target_zone_classification.headline == "Observed change; setup cause not established"
    assert "A car behind was observed within 0.50 seconds." in result.target_zone_classification.evidence
    assert result.summary_headline == "Observed change; setup cause not established"
    assert "A car behind was observed within 0.50 seconds." in result.warnings
    assert "Test lap 2: car behind at 0.48 seconds." in result.target_zone_classification.evidence
    assert all("Gained in" not in takeaway for takeaway in result.key_takeaways)
    assert result.key_takeaways[-1] == "Repeat with no car within 0.5 seconds behind."
    assert result.correlations
    assert all(
        insight.narrative.startswith("Observed correlation only")
        for insight in result.correlations
    )
    assert all(annotation.recommendation is None for annotation in result.annotations)
    assert all(annotation.description.startswith("Observed telemetry only") for annotation in result.annotations)
    assert all(sector.classification == "observed_only" for sector in result.sectors)


def test_sparse_target_zone_cannot_create_gain_or_correlation_story() -> None:
    baseline_rows = [
        {
            "lap_dist_pct_100": pct,
            "speed_mph": 180.0,
            "cfs_ride_height_in": 0.20,
            "rpm": 7000.0,
        }
        for pct in (60.0, 61.0)
    ]
    test_rows = [
        {
            "lap_dist_pct_100": pct,
            "speed_mph": 181.0,
            "cfs_ride_height_in": 0.20,
            "rpm": 7100.0,
        }
        for pct in (60.0, 61.0)
    ]

    result = build_comparison_insights(
        comparison_id="cmp-sparse",
        baseline_run_id="baseline",
        test_run_id="test",
        baseline_lap=1,
        test_lap=1,
        baseline_rows=baseline_rows,
        test_rows=test_rows,
        channels=["speed_mph", "cfs_ride_height_in", "rpm"],
    )

    assert result.target_zone_classification.classification == "inconclusive"
    assert result.target_zone_classification.headline == "Insufficient paired speed evidence"
    assert result.correlations == []
    assert result.annotations == []
    assert all(sector.classification == "insufficient_data" for sector in result.sectors)
    assert all(sector.avg_speed_delta_mph is None for sector in result.sectors)
