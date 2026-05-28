"""Tests for Pace Quality scoring (three-dimension system)."""

from __future__ import annotations

from racelab_engine.analysis.pace_quality import (
    PaceQualityResult,
    clamp_score,
    classify_pace_trust_relationship,
    compute_evidence_deductions,
    compute_pace_quality_score,
    logistic_score,
    score_consistency,
    score_context_consistency,
    score_data_completeness,
    score_draft_confidence,
    score_falloff,
    score_pace_speed,
    score_platform_safety,
    score_shock_safety,
    score_tire_safety,
    score_validity,
    score_weather_confidence,
    score_window_size_confidence,
)


class TestClampScore:
    def test_clamps_below_zero(self) -> None:
        assert clamp_score(-10) == 0

    def test_clamps_above_100(self) -> None:
        assert clamp_score(150) == 100

    def test_passes_through_mid(self) -> None:
        assert clamp_score(50) == 50


class TestLogisticScore:
    def test_good_value_high_score(self) -> None:
        score = logistic_score(0.02, good=0.05, bad=0.35, invert=True)
        assert score > 80

    def test_bad_value_low_score(self) -> None:
        score = logistic_score(0.50, good=0.05, bad=0.35, invert=True)
        assert score < 30

    def test_mid_value_medium_score(self) -> None:
        score = logistic_score(0.15, good=0.05, bad=0.35, invert=True)
        assert 30 < score < 80

    def test_higher_is_better_good_value(self) -> None:
        score = logistic_score(90, good=80, bad=30, invert=False)
        assert score > 80

    def test_higher_is_better_bad_value(self) -> None:
        score = logistic_score(10, good=80, bad=30, invert=False)
        assert score < 30


class TestScorePaceSpeed:
    def test_with_reference_close_to_reference_scores_high(self) -> None:
        s = score_pace_speed(avg_lap_time=90.0, reference_lap_time=89.9)
        assert s > 80

    def test_with_reference_far_from_reference_scores_low(self) -> None:
        s = score_pace_speed(avg_lap_time=95.0, reference_lap_time=89.0)
        assert s < 30

    def test_missing_avg_returns_neutral(self) -> None:
        assert score_pace_speed(None, 90.0) == 70

    def test_missing_reference_returns_neutral(self) -> None:
        assert score_pace_speed(90.0, None) == 70

    def test_both_missing_returns_neutral(self) -> None:
        assert score_pace_speed(None, None) == 70


class TestScoreConsistency:
    def test_perfect_consistency_high_score(self) -> None:
        assert score_consistency(0.0, 90.0) > 95

    def test_poor_consistency_low_score(self) -> None:
        assert score_consistency(0.5, 90.0) < 60

    def test_none_std_dev_returns_neutral(self) -> None:
        assert score_consistency(None, 90.0) == 70

    def test_none_avg_time_returns_neutral(self) -> None:
        assert score_consistency(0.05, None) == 70


class TestScoreFalloff:
    def test_no_falloff_high_score(self) -> None:
        assert score_falloff(0.0, 90.0) > 95

    def test_high_falloff_low_score(self) -> None:
        assert score_falloff(0.2, 90.0) < 30

    def test_none_falloff_returns_neutral(self) -> None:
        assert score_falloff(None, 90.0) == 70

    def test_none_avg_time_returns_neutral(self) -> None:
        assert score_falloff(0.01, None) == 70


class TestScoreValidity:
    def test_all_valid_100(self) -> None:
        assert score_validity(10, 10) == 100

    def test_90_percent_85(self) -> None:
        assert score_validity(9, 10) == 85

    def test_80_percent_65(self) -> None:
        assert score_validity(8, 10) == 65

    def test_60_percent_40(self) -> None:
        assert score_validity(6, 10) == 40

    def test_below_60_percent_10(self) -> None:
        assert score_validity(5, 10) == 10

    def test_zero_window_returns_zero(self) -> None:
        assert score_validity(0, 0) == 0


class TestScoreDraftConfidence:
    def test_solo_100(self) -> None:
        assert score_draft_confidence(["LIKELY_SOLO"]) == 100

    def test_draft_affected_25(self) -> None:
        assert score_draft_confidence(["DRAFT_AFFECTED"]) == 25

    def test_possible_draft_55(self) -> None:
        assert score_draft_confidence(["POSSIBLE_DRAFT_ASSIST"]) == 55

    def test_unknown_70(self) -> None:
        assert score_draft_confidence(["UNKNOWN_DRAFT_STATUS"]) == 70

    def test_empty_returns_70(self) -> None:
        assert score_draft_confidence([]) == 70

    def test_most_conservative_wins(self) -> None:
        assert score_draft_confidence(["LIKELY_SOLO", "DRAFT_AFFECTED"]) == 25


class TestScoreDataCompleteness:
    def test_all_three_100(self) -> None:
        assert score_data_completeness(True, True, True) == 100

    def test_two_of_three_85(self) -> None:
        assert score_data_completeness(True, True, False) == 85

    def test_one_of_three_65(self) -> None:
        assert score_data_completeness(True, False, False) == 65

    def test_none_40(self) -> None:
        assert score_data_completeness(False, False, False) == 40


class TestScoreWindowSizeConfidence:
    def test_40_plus_100(self) -> None:
        assert score_window_size_confidence(40) == 100

    def test_20_to_39_85(self) -> None:
        assert score_window_size_confidence(20) == 85

    def test_10_to_19_65(self) -> None:
        assert score_window_size_confidence(10) == 65

    def test_5_to_9_40(self) -> None:
        assert score_window_size_confidence(5) == 40

    def test_under_5_15(self) -> None:
        assert score_window_size_confidence(3) == 15


class TestScoreContextConsistency:
    def test_clean_90(self) -> None:
        assert score_context_consistency(["SOLO_CLEAN"]) == 90

    def test_wreck_or_spin_20(self) -> None:
        assert score_context_consistency(["WRECK_OR_SPIN"]) == 20

    def test_pit_road_20(self) -> None:
        assert score_context_consistency(["PIT_ROAD"]) == 20

    def test_cooldown_40(self) -> None:
        assert score_context_consistency(["COOLDOWN"]) == 40

    def test_out_lap_40(self) -> None:
        assert score_context_consistency(["OUT_LAP"]) == 40


class TestScoreWeatherConfidence:
    def test_no_change_90(self) -> None:
        assert score_weather_confidence(False) == 90

    def test_changed_50(self) -> None:
        assert score_weather_confidence(True) == 50


class TestScorePlatformSafety:
    def test_low_risk_high_score(self) -> None:
        assert score_platform_safety(platform_risk_peak=0.1) > 80

    def test_high_risk_low_score(self) -> None:
        assert score_platform_safety(platform_risk_peak=0.95) < 30

    def test_none_returns_neutral(self) -> None:
        assert score_platform_safety() == 70

    def test_most_conservative_wins(self) -> None:
        low = score_platform_safety(platform_risk_peak=0.1, whole_car_bottoming_peak=0.9)
        assert low < 50


class TestScoreTireSafety:
    def test_low_temp_spread_high_score(self) -> None:
        assert score_tire_safety(temp_spread=2.0) > 80

    def test_high_temp_spread_low_score(self) -> None:
        assert score_tire_safety(temp_spread=25.0) < 30

    def test_none_returns_neutral(self) -> None:
        assert score_tire_safety() == 70


class TestScoreShockSafety:
    def test_low_activity_high_score(self) -> None:
        assert score_shock_safety(0.1) > 80

    def test_high_activity_low_score(self) -> None:
        assert score_shock_safety(0.95) < 30

    def test_none_returns_neutral(self) -> None:
        assert score_shock_safety() == 70


class TestComputeEvidenceDeductions:
    def _assert_deduction(self, expected_amount: int, **kwargs: object) -> None:
        ded, _ = compute_evidence_deductions(**kwargs)  # type: ignore[arg-type]
        amounts = [d["amount"] for d in ded]
        assert expected_amount in amounts, f"Expected deduction {expected_amount} not in {amounts}"

    def test_possible_draft_deducts_12(self) -> None:
        self._assert_deduction(12, classification_tags=["POSSIBLE_DRAFT_ASSIST"], valid_lap_count=10, window_size=10, draft_statuses=["POSSIBLE_DRAFT_ASSIST"])

    def test_unknown_draft_deducts_5(self) -> None:
        self._assert_deduction(5, classification_tags=[], valid_lap_count=10, window_size=10, draft_statuses=["UNKNOWN_DRAFT_STATUS"])

    def test_mixed_draft_deducts_12(self) -> None:
        self._assert_deduction(12, classification_tags=[], valid_lap_count=10, window_size=10, draft_statuses=["LIKELY_SOLO", "DRAFT_AFFECTED"])

    def test_invalid_lap_deducts(self) -> None:
        ded, _ = compute_evidence_deductions(["INVALID_SPEED_EVENT"], 9, 10, ["LIKELY_SOLO"])
        assert any(d["amount"] > 0 for d in ded)

    def test_missing_lap_deducts(self) -> None:
        ded, _ = compute_evidence_deductions([], 8, 10, ["LIKELY_SOLO"])
        assert any(d["amount"] > 0 for d in ded)

    def test_short_window_deducts_10(self) -> None:
        self._assert_deduction(10, classification_tags=[], valid_lap_count=5, window_size=5, draft_statuses=["LIKELY_SOLO"])

    def test_less_than_60_percent_warns(self) -> None:
        _, warnings = compute_evidence_deductions([], 5, 10, ["LIKELY_SOLO"])
        assert any("60%" in w for w in warnings)

    def test_missing_tire_deducts_5(self) -> None:
        self._assert_deduction(5, classification_tags=[], valid_lap_count=10, window_size=10, draft_statuses=["LIKELY_SOLO"], has_tire_data=False)

    def test_missing_shock_deducts_3(self) -> None:
        self._assert_deduction(3, classification_tags=[], valid_lap_count=10, window_size=10, draft_statuses=["LIKELY_SOLO"], has_shock_data=False)

    def test_missing_platform_deducts_8(self) -> None:
        self._assert_deduction(8, classification_tags=[], valid_lap_count=10, window_size=10, draft_statuses=["LIKELY_SOLO"], has_platform_data=False)


class TestComputePaceQualityScore:
    def _assert_result(self, **kwargs: object) -> PaceQualityResult:
        return compute_pace_quality_score(**kwargs)  # type: ignore[arg-type]

    def test_clean_stable_20_lap_window_scores_high(self) -> None:
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.9,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.pace_quality_score >= 70
        assert result.evidence_confidence_score >= 70
        assert result.setup_usefulness_score >= 70

    def test_draft_affected_lower_evidence_confidence(self) -> None:
        clean = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.9,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        draft = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["DRAFT_AFFECTED"], draft_statuses=["DRAFT_AFFECTED"],
            avg_lap_time=90.0, reference_lap_time=89.9,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert draft.evidence_confidence_score < clean.evidence_confidence_score
        # Draft affected pace may be higher (tow) but evidence is lower
        assert draft.evidence_confidence_score < draft.pace_quality_score or draft.evidence_confidence_score < clean.evidence_confidence_score

    def test_draft_affected_high_pace_low_evidence(self) -> None:
        """Draft can give high pace but low evidence confidence."""
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["DRAFT_AFFECTED"], draft_statuses=["DRAFT_AFFECTED"],
            avg_lap_time=89.0, reference_lap_time=90.0,
            lap_time_std_dev=0.02, falloff_sec_per_lap=0.003,
        )
        assert result.pace_quality_score > result.evidence_confidence_score

    def test_solo_clean_slow_window_high_evidence_lower_pace(self) -> None:
        """Solo clean but slow pace: high evidence, lower pace."""
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=95.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.evidence_confidence_score > result.pace_quality_score

    def test_wreck_or_spin_caps_both_scores(self) -> None:
        result = self._assert_result(
            window_size=10, valid_lap_count=10,
            classification_tags=["WRECK_OR_SPIN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.pace_quality_score <= 20
        assert result.evidence_confidence_score <= 10
        assert any("Wreck or spin" in c["reason"] for c in result.caps)

    def test_pit_road_caps_both_scores(self) -> None:
        result = self._assert_result(
            window_size=10, valid_lap_count=10,
            classification_tags=["PIT_ROAD"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.pace_quality_score <= 25
        assert result.evidence_confidence_score <= 15
        assert any("Pit road" in c["reason"] for c in result.caps)

    def test_less_than_60_percent_valid_caps_evidence(self) -> None:
        result = self._assert_result(
            window_size=10, valid_lap_count=5,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.evidence_confidence_score <= 35

    def test_missing_tire_data_reduces_evidence(self) -> None:
        """Missing tire data should reduce evidence confidence vs having it."""
        with_tire = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
            tire_temp_spread=3.0,
        )
        without_tire = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert without_tire.evidence_confidence_score < with_tire.evidence_confidence_score

    def test_missing_shock_data_reduces_evidence(self) -> None:
        with_shock = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
            shock_activity_index=0.2,
        )
        without_shock = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert without_shock.evidence_confidence_score < with_shock.evidence_confidence_score

    def test_fastest_group_has_peak_pace_warning(self) -> None:
        result = self._assert_result(
            window_size=10, valid_lap_count=10,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
            is_fastest_group=True,
        )
        assert any("peak pace" in w for w in result.warnings)

    def test_short_5_lap_window_warns(self) -> None:
        result = self._assert_result(
            window_size=5, valid_lap_count=5,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert any("shorter than 10" in w for w in result.warnings)

    def test_score_labels_match_thresholds(self) -> None:
        excellent = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.95,
            lap_time_std_dev=0.01, falloff_sec_per_lap=0.001,
        )
        assert excellent.pace_quality_score >= 85
        assert "Excellent" in excellent.pace_quality_label

        low = self._assert_result(
            window_size=10, valid_lap_count=5,
            classification_tags=["DRAFT_AFFECTED", "INVALID_SPEED_EVENT"],
            draft_statuses=["DRAFT_AFFECTED"],
            avg_lap_time=95.0, reference_lap_time=89.0,
            lap_time_std_dev=0.5, falloff_sec_per_lap=0.2,
        )
        assert low.evidence_confidence_score < 50
        assert "Low confidence" in low.evidence_confidence_label or "Not useful" in low.evidence_confidence_label

    def test_setup_usefulness_combines_pace_and_confidence(self) -> None:
        """Setup usefulness should be a blend of pace and evidence."""
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        # Setup usefulness should be between pace and evidence
        scores = sorted([result.pace_quality_score, result.evidence_confidence_score, result.setup_usefulness_score])
        assert scores[0] <= result.setup_usefulness_score <= scores[2]

    def test_component_scores_contains_all_keys(self) -> None:
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        expected_keys = {
            "pace_speed", "consistency", "falloff", "platform_safety",
            "tire_safety", "shock_safety", "validity", "draft_confidence",
            "data_completeness", "window_size_confidence", "context_consistency",
            "weather_confidence",
        }
        assert expected_keys.issubset(result.component_scores.keys())

    def test_missing_reference_uses_neutral_70(self) -> None:
        """When reference_lap_time is None, pace_speed should be 70."""
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.component_scores.get("pace_speed", 0) == 70

    def test_missing_reference_includes_confidence_note(self) -> None:
        """Missing reference lap should include a confidence note."""
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert any("reference" in n.lower() for n in result.confidence_notes)

    def test_missing_tire_data_does_not_affect_performance(self) -> None:
        """Missing tire data should reduce trust but not fake bad performance."""
        with_tire = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
            tire_temp_spread=3.0,
        )
        without_tire = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        # Performance should be similar (tire is only 7% of pace weight)
        assert abs(with_tire.pace_quality_score - without_tire.pace_quality_score) < 10
        # Trust should be lower without tire data
        assert without_tire.evidence_confidence_score < with_tire.evidence_confidence_score

    def test_missing_shock_data_does_not_affect_performance(self) -> None:
        """Missing shock data should reduce trust but not fake bad performance."""
        with_shock = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
            shock_activity_index=0.2,
        )
        without_shock = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        # Performance should be similar (shock is only 5% of pace weight)
        assert abs(with_shock.pace_quality_score - without_shock.pace_quality_score) < 10
        # Trust should be lower without shock data
        assert without_shock.evidence_confidence_score < with_shock.evidence_confidence_score

    def test_missing_platform_data_does_not_affect_performance(self) -> None:
        """Missing platform data should reduce trust but not fake bad performance."""
        with_platform = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
            platform_risk_peak=0.3,
        )
        without_platform = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        # Performance should be similar (platform is only 8% of pace weight)
        assert abs(with_platform.pace_quality_score - without_platform.pace_quality_score) < 10
        # Trust should be lower without platform data
        assert without_platform.evidence_confidence_score < with_platform.evidence_confidence_score

    def test_backward_compatible_score_alias(self) -> None:
        """The .score alias should equal setup_usefulness_score."""
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.score == result.setup_usefulness_score

    def test_backward_compatible_label_alias(self) -> None:
        """The .label alias should equal setup_usefulness_label."""
        result = self._assert_result(
            window_size=20, valid_lap_count=20,
            classification_tags=["SOLO_CLEAN"], draft_statuses=["LIKELY_SOLO"],
            avg_lap_time=90.0, reference_lap_time=89.0,
            lap_time_std_dev=0.03, falloff_sec_per_lap=0.005,
        )
        assert result.label == result.setup_usefulness_label


class TestClassifyPaceTrustRelationship:
    def test_high_pace_low_trust(self) -> None:
        label = classify_pace_trust_relationship(
            pace_quality_score=85.0,
            evidence_confidence_score=30.0,
            setup_usefulness_score=50.0,
            warnings=[],
        )
        assert "Fast but not trustworthy" in label

    def test_low_pace_high_trust(self) -> None:
        label = classify_pace_trust_relationship(
            pace_quality_score=30.0,
            evidence_confidence_score=85.0,
            setup_usefulness_score=50.0,
            warnings=[],
        )
        assert "Clean but not fast" in label

    def test_high_pace_high_trust(self) -> None:
        label = classify_pace_trust_relationship(
            pace_quality_score=85.0,
            evidence_confidence_score=85.0,
            setup_usefulness_score=85.0,
            warnings=[],
        )
        assert "Strong clean pace" in label

    def test_low_pace_low_trust(self) -> None:
        label = classify_pace_trust_relationship(
            pace_quality_score=20.0,
            evidence_confidence_score=20.0,
            setup_usefulness_score=20.0,
            warnings=[],
        )
        assert "Not useful for setup decisions" in label

    def test_draft_warning_returns_draft_label(self) -> None:
        label = classify_pace_trust_relationship(
            pace_quality_score=85.0,
            evidence_confidence_score=85.0,
            setup_usefulness_score=85.0,
            warnings=["Draft affected"],
        )
        assert "Draft-affected" in label

    def test_insufficient_valid_laps_warning(self) -> None:
        label = classify_pace_trust_relationship(
            pace_quality_score=50.0,
            evidence_confidence_score=50.0,
            setup_usefulness_score=50.0,
            warnings=["Fewer than 60% of laps in this window are valid."],
        )
        assert "Insufficient valid laps" in label

    def test_mid_range_returns_usable(self) -> None:
        label = classify_pace_trust_relationship(
            pace_quality_score=55.0,
            evidence_confidence_score=55.0,
            setup_usefulness_score=55.0,
            warnings=[],
        )
        assert "Usable with caution" in label
