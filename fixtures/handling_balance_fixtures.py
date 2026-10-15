"""Shared deterministic fixtures for the handling-balance producer tests.

Both the P1 producer tests and the P2 investigation tests build the same
synthetic telemetry scenarios, so the builders live in one non-test helper
module instead of importing across test files.
"""

from __future__ import annotations

import math
import random

from racelab_engine.models.lap import LapSummary

RUN_ID = "run-handling-synthetic"


def _lap_summary(lap_number: int, *, tags: tuple[str, ...] = ()) -> LapSummary:
    return LapSummary(
        lap_id=f"lap-{lap_number}",
        run_id=RUN_ID,
        lap_number=lap_number,
        lap_type="flying",
        is_complete=True,
        is_useful=True,
        lap_time=50.0 + 0.1 * lap_number,
        classification_tags=list(tags),
    )


def _eligible_summaries(count: int = 6, start: int = 1) -> list[LapSummary]:
    return [_lap_summary(number) for number in range(start, start + count)]


def _corner_rows(
    *,
    laps: int = 6,
    deficit_fn,
    seed: int = 7,
    with_yaw: bool = True,
    with_steering: bool = True,
    steering_multiplier_fn=None,
) -> list[dict]:
    """Deterministic synthetic laps: one sustained corner at 40-60% lap.

    Speed 55 m/s, corner curvature 0.01 1/m, steering 5 deg. deficit_fn(lap,
    pct) returns the injected kinematic residual (rad/s): positive = rotates
    less than the path reference. steering_multiplier_fn(lap, pct) optionally
    scales steering demand per lap (strand B); without it every lap carries
    the same steering demand, so only the residual strand can qualify.
    """
    rng = random.Random(seed)
    rows: list[dict] = []
    for lap in range(1, laps + 1):
        base_time = lap * 100.0
        for step in range(200):
            pct = step * 0.5
            in_corner = 40.0 <= pct <= 60.0
            ramp_up = 40.0 <= pct < 45.0
            ramp_down = 55.0 < pct <= 60.0
            steering = 0.0
            if ramp_up:
                steering = 5.0 * (pct - 40.0) / 5.0
            elif in_corner and not ramp_down:
                steering = 5.0
            elif ramp_down:
                steering = 5.0 * (60.0 - pct) / 5.0
            if steering_multiplier_fn is not None:
                steering *= steering_multiplier_fn(lap, pct)
            curvature = 0.01 if in_corner else 0.0001
            speed = 55.0
            expected = speed * curvature
            deficit = deficit_fn(lap, pct)
            yaw = expected - deficit + rng.gauss(0.0, 0.003)
            row: dict = {
                "lap": lap,
                "lap_dist_pct_100": pct,
                "session_time": base_time + step * 0.01,
                "speed_mps": speed,
                "speed_mph": speed * 2.2369362920544,
                "yaw_rate": yaw if with_yaw else None,
                "steering_rad": math.radians(steering) if with_steering else None,
                "steering_deg": steering if with_steering else None,
                "lat_accel": speed * yaw,
                "throttle_pct": 50.0 if in_corner else 100.0,
                "brake_pct": 0.0,
                "curvature_1_per_m": curvature,
                "lat": None,
                "lon": None,
                "velocity_y": None,
            }
            rows.append(row)
    return rows


def _constant(deficit: float):
    return lambda _lap, _pct: deficit


def _corroborated_rows(*, direction: str = "deficit", laps: int = 5) -> list[dict]:
    """Two-strand synthetic scenario (asymmetric, unidirectional).

    Three laps carry a larger residual AND a shifted steering demand per
    curvature while two baseline laps stay put, so both strands qualify in
    one direction only: direction "deficit" pairs a positive residual with
    elevated demand; "excess" pairs a negative residual with reduced demand.
    """

    def deficit_fn(lap, _pct):
        return (0.07 if direction == "deficit" else -0.07) if lap >= laps - 2 else (0.02 if direction == "deficit" else -0.02)

    def steering_fn(lap, _pct):
        if lap >= laps - 2:
            return {"deficit": 1.24, "excess": 0.76}[direction]
        return 0.92

    return _corner_rows(
        laps=laps,
        deficit_fn=deficit_fn,
        steering_multiplier_fn=steering_fn,
    )
