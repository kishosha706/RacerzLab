from __future__ import annotations

import math

from racelab_engine.analysis.units import (
    input_01_to_percent,
    meters_to_millimeters,
    mps_to_mph,
    radians_to_degrees,
)


def test_unit_conversions() -> None:
    assert mps_to_mph(1) == 2.23693629
    assert meters_to_millimeters(0.00358) == 3.58
    assert radians_to_degrees(math.pi) == 180
    assert input_01_to_percent(0.72) == 72
