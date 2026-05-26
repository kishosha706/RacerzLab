from __future__ import annotations

import math

MPS_TO_MPH = 2.23693629
M_TO_IN = 39.37007874
M_TO_FT = 3.280839895
PA_TO_PSF = 1 / 47.88025898
MM_TO_IN = 1 / 25.4
EARTH_RADIUS_M = 6_371_000.0


def mps_to_mph(value: float | int | None) -> float | None:
    return None if value is None else float(value) * MPS_TO_MPH


def meters_to_millimeters(value: float | int | None) -> float | None:
    return None if value is None else float(value) * 1000.0


def radians_to_degrees(value: float | int | None) -> float | None:
    return None if value is None else float(value) * 180.0 / math.pi


def input_01_to_percent(value: float | int | None) -> float | None:
    return None if value is None else float(value) * 100.0
