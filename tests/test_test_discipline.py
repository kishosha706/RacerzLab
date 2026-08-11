from __future__ import annotations

from racelab_engine.analysis.comparison import SetupChange
from racelab_engine.analysis.test_discipline import score_test_discipline


def _change(group: str, key: str = "lf_ride_height_mm") -> SetupChange:
    return SetupChange(setup_key=key, label=key, group=group)  # type: ignore[arg-type]


def test_one_change_test_is_clean() -> None:
    result = score_test_discipline([_change("front_platform")])

    assert result.label == "clean"
    assert result.is_reliable is True


def test_zero_change_comparison_is_reference_not_causal_test() -> None:
    result = score_test_discipline([])

    assert result.label == "reference"
    assert result.is_reliable is False
    assert "repeatability" in (result.measurement_note or "")


def test_multi_change_warning_reduces_score() -> None:
    result = score_test_discipline([_change("front_platform"), _change("rear_platform", "lr_ride_height_mm")])

    assert result.label == "mostly_clean"
    assert result.negative_factors == ["Two setup controls changed; attribution is reduced."]


def test_unknown_change_counts_as_one_group() -> None:
    result = score_test_discipline([_change("unknown", "mystery")])

    assert result.label == "clean"
    assert "One setup control changed: mystery." in result.positive_factors


def test_missing_setup_snapshots_are_never_treated_as_zero_changes() -> None:
    result = score_test_discipline([], setup_data_available=False)

    assert result.label == "invalid"
    assert result.is_reliable is False
    assert "unknown" in result.negative_factors[0].lower()


def test_insufficient_controlled_context_can_make_result_invalid() -> None:
    result = score_test_discipline(
        [
            _change("front_platform"),
            _change("rear_platform", "lr_ride_height_mm"),
            _change("springs", "lf_front_spring_n_per_mm"),
            _change("gearing", "rear_end_ratio"),
        ],
        context_problems=2,
    )

    assert result.label == "invalid"
    assert result.is_reliable is False
