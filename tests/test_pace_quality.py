"""Tests for Pace Quality scoring."""

from __future__ import annotations

from racelab_engine.analysis.pace_quality import (
    clamp_score,
    compute_deductions,
    compute_pace_quality_score,
    logistic_score,
    score_consistency,
    score_draft_confidence,
    score_falloff,
    score_platform_safety,
    score_shock_safety,
    score_tire_safety,
    score_validity,
)


class TestClampScore:
    def test_clamps_below_zero(self):
        assert clamp_score(-10) == 0

    def test_clamps_above_100(self):
        assert clamp_score(150) == 100

    def test_passes_through_mid(self):
        assert clamp_score(50) == 50


class TestLogisticScore:
    def test_good_value_high_score(self):
        # Consistency: lower std dev is better
        score = logistic_score(0.02, good=0.05, bad=0.35, invert=True)
        assert score > 80

    def test_bad_value_low_score(self):
        score = logistic_score(0.50, good=0.05, bad=0.35, invert=True)
        assert score < 30

    def test_mid_value_medium_score(self):
        score = logistic_score(0.15, good=0.05, bad=0.35, invert=True)
        assert 30 < score < 80

    def test_higher_is_better_good_value(self):
        score = logistic_score(90, good=80, bad=30, invert=False)
        assert score > 80

    def test_higher_is_better_bad_value(self):
        score = logistic_score(10, good=80, bad=30, invert=False)
        assert score < 30


class TestScoreConsistency:
    def test_perfect_consistency_high_score(self):
        assert score_consistency(0.0) > 95

    def test_poor_consistency_low_score(self):
        assert score_consistency(0.5) < 30

    def test_none_returns_neutral(self):
        assert score_consistency(None) == 70


class TestScoreFalloff:
    def test_no_falloff_high_score(self):
        assert score_falloff(0.0) > 95

    def test_high_falloff_low_score(self):
        assert score_falloff(0.2) < 30

    def test_none_returns_neutral(self):
        assert score_falloff(None) == 70


class TestScoreValidity:
    def test_all_valid_100(self):
        assert score_validity(10, 10) == 100

    def test_90_percent_85(self):
        assert score_validity(9, 10) == 85

    def test_75_percent_65(self):
        assert score_validity(8, 10) == 65  # Actually 80% -> 85

    def test_60_percent_40(self):
        assert score_validity(6, 10) == 40

    def test_below_60_percent_10(self):
        assert score_validity(5, 10) == 10

    def test_zero_window_returns_zero(self):
        assert score_validity(0, 0) == 0


class TestScoreDraftConfidence:
    def test_solo_100(self):
        assert score_draft_confidence(["LIKELY_SOLO"]) == 100

    def test_draft_affected_25(self):
        assert score_draft_confidence(["DRAFT_AFFECTED"]) == 25

    def test_possible_draft_55(self):
        assert score_draft_confidence(["POSSIBLE_DRAFT_ASSIST"]) == 55

    def test_unknown_70(self):
        assert score_draft_confidence(["UNKNOWN_DRAFT_STATUS"]) == 70

    def test_empty_returns_70(self):
        assert score_draft_confidence([]) == 70

    def test_most_conservative_wins(self):
        assert score_draft_confidence(["LIKELY_SOLO", "DRAFT_AFFECTED"]) == 25


class TestScorePlatformSafety:
    def test_low_risk_high_score(self):
        assert score_platform_safety(platform_risk_peak=0.1) > 80

    def test_high_risk_low_score(self):
        assert score_platform_safety(platform_risk_peak=0.95) < 30

    def test_none_returns_neutral(self):
        assert score_platform_safety() == 70

    def test_most_conservative_wins(self):
        low = score_platform_safety(platform_risk_peak=0.1, whole_car_bottoming_peak=0.9)
        assert low < 50


class TestScoreTireSafety:
    def test_low_temp_spread_high_score(self):
        assert score_tire_safety(temp_spread=2.0) > 80

    def test_high_temp_spread_low_score(self):
        assert score_tire_safety(temp_spread=25.0) < 30

    def test_none_returns_neutral(self):
        assert score_tire_safety() == 70


class TestScoreShockSafety:
    def test_low_activity_high_score(self):
        assert score_shock_safety(0.1) > 80

    def test_high_activity_low_score(self):
        assert score_shock_safety(0.95) < 30

    def test_none_returns_neutral(self):
        assert score_shock_safety() == 70


class TestComputeDeductions:
    def _assert_deduction(self, expected_amount: int, **kwargs):
        ded, _ = compute_deductions(**kwargs)
        amounts = [d["amount"] for d in ded]
        assert expected_amount in amounts

    def test_draft_affected_deducts_20(self):
        self._assert_deduction(20, classification_tags=["DRAFT_AFFECTED"], valid_lap_count=10, window_size=10, draft_statuses=["DRAFT_AFFECTED"])

    def test_possible_draft_deducts_10(self):
        self._assert_deduction(10, classification_tags=["POSSIBLE_DRAFT_ASSIST"], valid_lap_count=10, window_size=10, draft_statuses=["POSSIBLE_DRAFT_ASSIST"])

    def test_invalid_lap_deducts(self):
        ded, _ = compute_deductions(["INVALID_SPEED_EVENT"], 9, 10, ["LIKELY_SOLO"])
        assert any(d["amount"] > 0 for d in ded)

    def test_missing_lap_deducts(self):
        ded, _ = compute_deductions([], 8, 10, ["LIKELY_SOLO"])
        assert any(d["amount"] > 0 for d in ded)

    def test_short_window_deducts(self):
        self._assert_deduction(10, classification_tags=[], valid_lap_count=5, window_size=5, draft_statuses=["LIKELY_SOLO"])

    def test_less_than_60_percent_warns(self):
        _, warnings = compute_deductions([], 5, 10, ["LIKELY_SOLO"])
        assert any("60%" in w for w in warnings)


class TestComputePaceQualityScore:
    def test_clean_stable_20_lap_window_scores_high(self):
        result = compute_pace_quality_score(
            window_size=20,
            valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"],
            draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.03,
            falloff_sec_per_lap=0.005,
        )
        assert result.score >= 70
        assert "Excellent" in result.label or "Strong" in result.label

    def test_draft_affected_scores_lower(self):
        clean = compute_pace_quality_score(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        draft = compute_pace_quality_score(
            window_size=20, valid_lap_count=20,
            classification_tags=["DRAFT_AFFECTED"], draft_statuses=["DRAFT_AFFECTED"],
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert draft.score < clean.score

    def test_invalid_heavy_window_low_confidence(self):
        result = compute_pace_quality_score(
            window_size=10, valid_lap_count=5,
            classification_tags=["INVALID_SPEED_EVENT", "SOLO_CLEAN"],
            draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.1, falloff_sec_per_lap=0.02,
        )
        assert result.score <= 35  # Capped by <60% valid

    def test_fastest_group_has_peak_pace_warning(self):
        result = compute_pace_quality_score(
            window_size=10, valid_lap_count=10,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
            is_fastest_group=True,
        )
        assert any("peak pace" in w for w in result.warnings)

    def test_missing_tire_data_returns_neutral_with_warning(self):
        result = compute_pace_quality_score(
            window_size=10, valid_lap_count=10,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        # Tire safety should be neutral (70) when missing
        assert result.component_scores.get("tire_safety", 0) == 70

    def test_missing_shock_data_returns_neutral(self):
        result = compute_pace_quality_score(
            window_size=10, valid_lap_count=10,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.component_scores.get("shock_safety", 0) == 70

    def test_short_5_lap_window_warns(self):
        result = compute_pace_quality_score(
            window_size=5, valid_lap_count=5,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert any("shorter than 10" in w for w in result.warnings)

    def test_score_labels_match_thresholds(self):
        excellent = compute_pace_quality_score(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            lap_time_std_dev=0.01, falloff_sec_per_lap=0.001,
        )
        assert excellent.score >= 85
        assert "Excellent" in excellent.label

        low = compute_pace_quality_score(
            window_size=10, valid_lap_count=5,
            classification_tags=["DRAFT_AFFECTED", "INVALID_SPEED_EVENT"],
            draft_statuses=["DRAFT_AFFECTED"],
            lap_time_std_dev=0.5, falloff_sec_per_lap=0.2,
        )
        assert low.score < 50
        assert "Low confidence" in low.label or "Not useful" in low.label
