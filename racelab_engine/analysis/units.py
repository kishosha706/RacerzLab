from __future__ import annotations

import math

MPS_TO_MPH = 2.23693629
M_TO_IN = 39.37007874
M_TO_FT = 3.280839895
PA_TO_PSF = 1 / 47.88025898
KPA_TO_PSI = 0.14503773773020923
MM_TO_IN = 1 / 25.4
EARTH_RADIUS_M = 6_371_000.0


def _finite(value: float | int | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def mps_to_mph(value: float | int | None) -> float | None:
    number = _finite(value)
    return None if number is None else number * MPS_TO_MPH


def meters_to_millimeters(value: float | int | None) -> float | None:
    number = _finite(value)
    return None if number is None else number * 1000.0


def radians_to_degrees(value: float | int | None) -> float | None:
    number = _finite(value)
    return None if number is None else number * 180.0 / math.pi


def input_01_to_percent(value: float | int | None) -> float | None:
    number = _finite(value)
    return None if number is None else number * 100.0
