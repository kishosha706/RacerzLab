from __future__ import annotations

from racelab_engine.analysis.setup_diff import (
    SETUP_GROUPS,
    diff_setups,
    setup_controls_comparable,
    unmapped_setup_change_paths,
)


def test_changed_and_unchanged_setup_fields() -> None:
    changes = diff_setups(
        {"lf_ride_height_mm": 55.0, "rf_ride_height_mm": 55.0},
        {"lf_ride_height_mm": 57.0, "rf_ride_height_mm": 55.0},
    )

    assert [change.setup_key for change in changes] == ["lf_ride_height_mm"]
    assert changes[0].baseline_value == 2.165
    assert changes[0].test_value == 2.244
    assert changes[0].unit == "in"
    assert changes[0].delta == "+0.079 in"
    assert changes[0].significance == "medium"


def test_missing_on_both_sides_does_not_create_fake_change() -> None:
    assert diff_setups({}, {}) == []


def test_missing_on_one_side_is_reported_without_fake_zero() -> None:
    changes = diff_setups({"tape_percent": 30}, {})

    assert len(changes) == 1
    assert changes[0].baseline_value == 30
    assert changes[0].test_value is None
    assert changes[0].delta == "removed"
    assert changes[0].significance == "unknown"


def test_nested_setup_sections_are_compared() -> None:
    changes = diff_setups(
        {"platform": {"lr_ride_height_mm": 70.0}},
        {"platform": {"lr_ride_height_mm": 71.0}},
    )

    assert len(changes) == 1
    assert changes[0].setup_key == "lr_ride_height_mm"
    assert changes[0].group == "rear_platform"


def test_matching_car_specific_control_coverage_is_comparable() -> None:
    baseline = {key: 1.0 for key in SETUP_GROUPS}
    test = dict(baseline)
    test["lf_ride_height_mm"] = 2.0

    assert setup_controls_comparable(baseline, test) is True
    assert setup_controls_comparable(baseline, {"lf_ride_height_mm": None}) is False
    assert setup_controls_comparable(
        {"lf_ride_height_mm": 55.0},
        {"lf_ride_height_mm": 56.0},
    ) is False
    assert setup_controls_comparable({}, {}) is False


def test_small_truthy_setup_fragment_is_not_mistaken_for_complete_source() -> None:
    baseline = {
        "setup_json": {"Chassis": {"LeftRear": {"SpringRate": "800 N/mm"}}},
        **{key: 1.0 for key in SETUP_GROUPS if key not in {"lr_ride_height_mm", "tape_percent"}},
    }
    test = dict(baseline)
    test["rear_end_ratio"] = 2.0

    assert setup_controls_comparable(baseline, test) is False


def test_unmapped_raw_chassis_change_blocks_isolated_change_claim() -> None:
    controls = {key: 1.0 for key in SETUP_GROUPS}
    baseline = {
        **controls,
        "setup_json": {"Chassis": {"Rear": {"FinalDriveRatio": 3.5, "DiffPreload": "20 Nm"}}},
    }
    test = {
        **controls,
        "rear_end_ratio": 3.6,
        "setup_json": {"Chassis": {"Rear": {"FinalDriveRatio": 3.6, "DiffPreload": "30 Nm"}}},
    }
    mapped = diff_setups(baseline, test)

    assert len(mapped) == 1
    assert unmapped_setup_change_paths(baseline, test, mapped) == ["Rear.DiffPreload"]


def test_mapped_raw_chassis_change_is_accounted_for_by_exact_path() -> None:
    controls = {key: 1.0 for key in SETUP_GROUPS}
    baseline = {
        **controls,
        "rear_end_ratio": 3.5,
        "setup_json": {"Chassis": {"Rear": {"FinalDriveRatio": 3.5}}},
    }
    test = {
        **controls,
        "rear_end_ratio": 3.6,
        "setup_json": {"Chassis": {"Rear": {"FinalDriveRatio": 3.6}}},
    }
    mapped = diff_setups(baseline, test)

    assert unmapped_setup_change_paths(baseline, test, mapped) == []


def test_unmapped_tire_setup_change_blocks_isolated_change_claim() -> None:
    controls = {key: 1.0 for key in SETUP_GROUPS}
    baseline = {
        **controls,
        "setup_json": {"Tires": {"LeftFront": {"ColdPressure": "20 psi"}}},
    }
    test = {
        **controls,
        "setup_json": {"Tires": {"LeftFront": {"ColdPressure": "22 psi"}}},
    }

    mapped = diff_setups(baseline, test)

    assert mapped == []
    assert unmapped_setup_change_paths(baseline, test, mapped) == [
        "Tires.LeftFront.ColdPressure"
    ]


def test_change_size_uses_control_specific_units_and_bands() -> None:
    changes = diff_setups(
        {
            "rf_front_spring_n_per_mm": 100.0,
            "cross_weight_percent": 50.0,
            "tape_percent": 20.0,
            "rear_end_ratio": 3.45,
        },
        {
            "rf_front_spring_n_per_mm": 105.0,
            "cross_weight_percent": 50.5,
            "tape_percent": 25.0,
            "rear_end_ratio": 3.55,
        },
    )
    by_key = {change.setup_key: change for change in changes}

    assert by_key["rf_front_spring_n_per_mm"].unit == "lb/in"
    assert by_key["rf_front_spring_n_per_mm"].significance == "small"
    assert by_key["rf_front_spring_n_per_mm"].delta == "+29 lb/in"
    assert by_key["cross_weight_percent"].delta == "+0.5 percentage points"
    assert by_key["cross_weight_percent"].significance == "small"
    assert by_key["tape_percent"].significance == "small"
    assert by_key["rear_end_ratio"].significance == "medium"


def test_steering_ratio_string_change_is_measured_relatively() -> None:
    change = diff_setups({"steering_ratio": "10:1"}, {"steering_ratio": "12:1"})[0]

    assert change.baseline_value == "10:1"
    assert change.test_value == "12:1"
    assert change.delta == "+2.0"
    assert change.significance == "medium"
    assert change.relative_delta_percent == 20.0


def test_discrete_tape_mode_change_is_large_and_keeps_mode_names() -> None:
    change = diff_setups({"tape_percent": "Race"}, {"tape_percent": "Qual"})[0]

    assert change.baseline_value == "Race"
    assert change.test_value == "Qual"
    assert change.delta == "Race -> Qual"
    assert change.significance == "large"
    assert "discrete configuration change" in (change.magnitude_basis or "")
