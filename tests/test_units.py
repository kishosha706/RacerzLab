from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.units import (
    MPS_TO_MPH,
    input_01_to_percent,
    meters_to_millimeters,
    mps_to_mph,
    radians_to_degrees,
)


def test_speed_conversion_and_round_trip() -> None:
    mph = mps_to_mph(44.704)

    assert mph == pytest.approx(100.0, rel=1e-5)
    assert mph / MPS_TO_MPH == pytest.approx(44.704)


def test_metric_and_angle_conversions() -> None:
    assert meters_to_millimeters(0.0254) == pytest.approx(25.4)
    assert radians_to_degrees(math.pi) == pytest.approx(180.0)
    assert input_01_to_percent(0.42) == pytest.approx(42.0)


def test_none_nan_and_infinity_return_unavailable() -> None:
    for fn in (mps_to_mph, meters_to_millimeters, radians_to_degrees, input_01_to_percent):
        assert fn(None) is None
        assert fn(math.nan) is None
        assert fn(math.inf) is None
