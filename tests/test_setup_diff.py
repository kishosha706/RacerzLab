from __future__ import annotations

from racelab_engine.analysis.setup_diff import diff_setups


def test_changed_and_unchanged_setup_fields() -> None:
    changes = diff_setups(
        {"lf_ride_height_mm": 55.0, "rf_ride_height_mm": 55.0},
        {"lf_ride_height_mm": 57.0, "rf_ride_height_mm": 55.0},
    )

    assert [change.setup_key for change in changes] == ["lf_ride_height_mm"]
    assert changes[0].delta == "+2.000"
    assert changes[0].significance == "moderate"


def test_missing_on_both_sides_does_not_create_fake_change() -> None:
    assert diff_setups({}, {}) == []


def test_missing_on_one_side_is_reported_without_fake_zero() -> None:
    changes = diff_setups({"tape_percent": 30}, {})

    assert len(changes) == 1
    assert changes[0].baseline_value == 30
    assert changes[0].test_value is None
    assert changes[0].delta is None


def test_nested_setup_sections_are_compared() -> None:
    changes = diff_setups(
        {"platform": {"lr_ride_height_mm": 70.0}},
        {"platform": {"lr_ride_height_mm": 71.0}},
    )

    assert len(changes) == 1
    assert changes[0].setup_key == "lr_ride_height_mm"
    assert changes[0].group == "rear_platform"
