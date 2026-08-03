from __future__ import annotations

from pathlib import Path

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    DidItWorkVerdict,
    DriverComparison,
    PaceComparison,
    SetupChange,
    TargetZoneComparison,
    TestDisciplineResult,
)
from racelab_engine.services.setup_learning_service import get_setup_area_biases, record_setup_response


def _record(db_path: Path, comparison_id: str, verdict: str = "keep_direction") -> bool:
    return record_setup_response(
        comparison_id=comparison_id,
        car_name="Next Gen Camaro",
        track_name="Charlotte Oval",
        baseline_run_id=f"{comparison_id}-a",
        test_run_id=f"{comparison_id}-b",
        baseline_lap=2,
        test_lap=2,
        setup_changes=[SetupChange(
            setup_key="rf_front_spring_n_per_mm",
            label="RF Spring",
            group="springs",
            baseline_value=300.0,
            test_value=305.0,
            significance="small",
            relative_delta_percent=1.667,
        )],
        discipline=TestDisciplineResult(score=92, label="clean"),
        target_zone=TargetZoneComparison(
            start_pct=55.0,
            end_pct=70.0,
            channel_deltas=[
                ComparedChannelDelta("speed_mph", "Speed", "mph", delta=0.25),
                ComparedChannelDelta("cfs_ride_height_in", "CFS", "in", delta=0.01),
            ],
        ),
        verdict=DidItWorkVerdict(verdict=verdict, confidence_score=0.75, headline="Measured result"),
        pace=PaceComparison(
            cohort_delta_s=-0.2,
            noise_band_s=0.05,
            baseline_eligible_laps=4,
            test_eligible_laps=4,
            is_significant=True,
            direction="faster",
            confidence_score=0.8,
        ),
        driver=DriverComparison(driver_verdict="consistent", repeatability_score=92.0),
        context_problem_count=0,
        db_path=db_path,
    )


def test_repeated_controlled_tests_create_directional_learning_bias(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    for index in range(3):
        assert _record(db_path, f"comparison-{index}") is True

    biases = get_setup_area_biases(
        "Next Gen Camaro",
        "Charlotte Oval",
        db_path=db_path,
    )

    signal = biases[("spring_rate", 1)]
    assert signal["count"] == 3
    assert signal["weighted_outcome"] == 1.0
    assert signal["mean_lap_delta_s"] == -0.2
    assert signal["magnitude_counts"] == {"small": 3}
    assert signal["weighted_outcome_by_magnitude"] == {"small": 1.0}
    assert signal["mean_abs_numeric_delta"] == 5.0


def test_uncontrolled_comparison_is_not_learned(tmp_path: Path) -> None:
    db_path = tmp_path / "learning.sqlite"
    recorded = record_setup_response(
        comparison_id="bad-test",
        car_name="Next Gen Camaro",
        track_name="Charlotte Oval",
        baseline_run_id="a",
        test_run_id="b",
        baseline_lap=1,
        test_lap=1,
        setup_changes=[],
        discipline=TestDisciplineResult(score=10, label="invalid"),
        target_zone=TargetZoneComparison(start_pct=55, end_pct=70),
        verdict=DidItWorkVerdict(verdict="inconclusive", confidence_score=0.1, headline="Invalid"),
        pace=PaceComparison(),
        driver=DriverComparison(driver_verdict="changed"),
        context_problem_count=1,
        db_path=db_path,
    )

    assert recorded is False
    assert get_setup_area_biases("Next Gen Camaro", "Charlotte Oval", db_path=db_path) == {}
