from __future__ import annotations

from racelab_engine.analysis.pace_quality import (
    classify_pace_trust_relationship,
    compute_evidence_deductions,
    compute_pace_quality_score,
    score_validity,
)


def test_score_validity_scale() -> None:
    assert score_validity(10, 10) == 100
    assert score_validity(5, 10) == 10


def test_evidence_deductions_no_draft_inputs() -> None:
    deductions, warnings = compute_evidence_deductions(
        classification_tags=["INVALID_SPEED_EVENT"],
        valid_lap_count=5,
        window_size=10,
    )
    assert any(d["amount"] > 0 for d in deductions)
    assert any("60%" in w for w in warnings)


def test_pace_quality_result_contains_no_draft_component() -> None:
    result = compute_pace_quality_score(
        window_size=20,
        valid_lap_count=20,
        classification_tags=["SOLO_CLEAN"],
        avg_lap_time=90.0,
        reference_lap_time=89.9,
        lap_time_std_dev=0.03,
        falloff_sec_per_lap=0.005,
    )
    assert "draft_confidence" not in result.component_scores


def test_classification_relationship_still_works() -> None:
    label = classify_pace_trust_relationship(80, 30, 50, [])
    assert "Fast but not trustworthy" in label


def test_pace_quality_caps_low_valid_ratio_and_keeps_deductions_deterministic() -> None:
    result = compute_pace_quality_score(
        window_size=10,
        valid_lap_count=5,
        classification_tags=["SOLO_CLEAN"],
        avg_lap_time=50.0,
        reference_lap_time=50.0,
    )

    assert result.evidence_confidence_score <= 35.0
    assert any("60%" in warning for warning in result.warnings)
    assert any(cap["reason"] == "Fewer than 60% valid laps" for cap in result.caps)


def test_wreck_tag_caps_pace_and_evidence() -> None:
    result = compute_pace_quality_score(
        window_size=12,
        valid_lap_count=12,
        classification_tags=["WRECK_OR_SPIN"],
        avg_lap_time=50.0,
        reference_lap_time=49.9,
    )

    assert result.pace_quality_score <= 20.0
    assert result.evidence_confidence_score <= 10.0
    assert result.setup_usefulness_score <= 14.0


def test_missing_measurements_remain_none_instead_of_becoming_neutral_scores() -> None:
    result = compute_pace_quality_score(
        window_size=20,
        valid_lap_count=20,
        classification_tags=["ELIGIBLE_FLYING_LAP"],
    )

    assert result.component_scores["pace_speed"] is None
    assert result.component_scores["consistency"] is None
    assert result.component_scores["falloff"] is None
    assert result.component_scores["platform_safety"] is None
    assert result.component_scores["tire_safety"] is None
    assert result.component_scores["shock_safety"] is None
    assert result.setup_usefulness_score <= 35.0
    assert any("no neutral score was substituted" in note for note in result.confidence_notes)


def test_short_run_cannot_claim_high_setup_usefulness() -> None:
    result = compute_pace_quality_score(
        window_size=5,
        valid_lap_count=5,
        classification_tags=["ELIGIBLE_FLYING_LAP"],
        avg_lap_time=50.0,
        reference_lap_time=50.0,
        lap_time_std_dev=0.01,
        falloff_sec_per_lap=0.0,
        platform_risk_peak=0.0,
        tire_temp_spread=0.0,
        shock_activity_index=0.0,
    )

    assert result.setup_usefulness_score <= 35.0
    assert any("Short run" in cap["reason"] for cap in result.caps)
