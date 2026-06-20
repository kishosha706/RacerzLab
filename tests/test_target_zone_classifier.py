from __future__ import annotations

from racelab_engine.analysis.target_zone_classifier import classify_target_zone


def test_stable_gain_classification() -> None:
    result = classify_target_zone(0.25, 0.01, 0.0, 0.0, 0.0, "clean")

    assert result.gain_class == "stable_gain"
    assert result.label == "Stable gain"
    assert result.confidence >= 0.7


def test_missing_speed_data_falls_back_to_inconclusive() -> None:
    result = classify_target_zone(None, None, None, None, None, "clean")

    assert result.gain_class == "inconclusive"
    assert result.label == "No speed data"
    assert result.confidence == 0.0


def test_platform_related_loss_when_speed_and_cfs_worsen() -> None:
    result = classify_target_zone(-0.2, -0.01, 0.0, 0.0, 0.0, "clean")

    assert result.label == "Platform-related loss"
    assert result.recommendation == "Undo or reduce platform change."


def test_zone_classifier_uses_labels_not_raw_percent_locations() -> None:
    result = classify_target_zone(0.01, 0.0, 0.0, 0.0, 0.0, "clean")

    assert "%" not in result.label
    assert result.label == "No meaningful change"
