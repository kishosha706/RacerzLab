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
