from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from racelab_engine.analysis.comparison import (
    ComparedChannelDelta,
    DidItWorkVerdict,
    DriverComparison,
    PaceComparison,
    SetupChange,
    TargetZoneComparison,
    TestDisciplineResult,
)
from racelab_engine.storage.db import initialize_database


CONTROL_TO_SETUP_AREAS: dict[str, tuple[str, ...]] = {
    "lf_ride_height_mm": ("front_ride_height_platform", "ride_height", "diffuser_platform"),
    "rf_ride_height_mm": ("front_ride_height_platform", "ride_height", "diffuser_platform"),
    "lr_ride_height_mm": ("rear_ride_height_platform", "ride_height", "diffuser_platform"),
    "rr_ride_height_mm": ("rear_ride_height_platform", "ride_height", "diffuser_platform"),
    "lf_front_spring_n_per_mm": ("spring_rate",),
    "rf_front_spring_n_per_mm": ("spring_rate",),
    "lr_rear_spring_n_per_mm": ("spring_rate",),
    "rr_rear_spring_n_per_mm": ("spring_rate",),
    "nose_weight_percent": ("nose_weight",),
    "cross_weight_percent": ("cross_weight",),
    "tape_percent": ("aero_cooling",),
    "rear_end_ratio": ("final_drive",),
    "front_brake_bias_percent": ("brake_bias",),
    "steering_ratio": ("steering_response",),
    "steering_offset_deg": ("steering_response",),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
        value = match.group(0) if match else value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _channel_delta(zone: TargetZoneComparison, channel: str) -> float | None:
    item: ComparedChannelDelta | None = next((delta for delta in zone.channel_deltas if delta.channel == channel), None)
    return item.delta if item else None


def _observation_id(comparison_id: str, setup_key: str, start_pct: float, end_pct: float) -> str:
    digest = hashlib.sha256(f"{comparison_id}|{setup_key}|{start_pct:.4f}|{end_pct:.4f}".encode()).hexdigest()[:20]
    return f"obs_{digest}"


def record_setup_response(
    *,
    comparison_id: str,
    car_name: str | None,
    track_name: str | None,
    baseline_run_id: str,
    test_run_id: str,
    baseline_lap: int | None,
    test_lap: int | None,
    setup_changes: list[SetupChange],
    discipline: TestDisciplineResult,
    target_zone: TargetZoneComparison,
    verdict: DidItWorkVerdict,
    pace: PaceComparison,
    driver: DriverComparison,
    context_problem_count: int,
    is_same_run: bool = False,
    db_path: str | Path | None = None,
) -> bool:
    """Persist one controlled setup response for conservative background learning."""
    if (
        is_same_run
        or len(setup_changes) != 1
        or discipline.label != "clean"
        or context_problem_count != 0
        or driver.driver_verdict == "changed"
        or verdict.verdict not in {"keep_direction", "undo"}
        or verdict.confidence_score < 0.55
        or pace.is_significant is not True
        or pace.baseline_eligible_laps < 3
        or pace.test_eligible_laps < 3
    ):
        return False
    change = setup_changes[0]
    baseline_value = _number(change.baseline_value)
    test_value = _number(change.test_value)
    numeric_delta = test_value - baseline_value if baseline_value is not None and test_value is not None else None
    direction_sign = 0 if numeric_delta is None or abs(numeric_delta) < 1e-12 else (1 if numeric_delta > 0 else -1)
    if direction_sign == 0:
        return False
    relative_delta_percent = change.relative_delta_percent
    if relative_delta_percent is None and baseline_value is not None and abs(baseline_value) > 1e-12:
        relative_delta_percent = abs(numeric_delta or 0.0) / abs(baseline_value) * 100.0
    magnitude_label = change.significance if change.significance != "unknown" else None

    evidence = {
        "headline": verdict.headline,
        "evidence": verdict.evidence,
        "warnings": verdict.warnings,
        "pace_direction": pace.direction,
        "pace_confidence": pace.confidence_score,
    }
    observation_id = _observation_id(
        comparison_id,
        change.setup_key,
        target_zone.start_pct,
        target_zone.end_pct,
    )
    conn = initialize_database(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO setup_response_observations (
              observation_id, comparison_id, created_at, car_name, track_name,
              baseline_run_id, test_run_id, baseline_lap, test_lap,
              setup_key, setup_label, setup_group, direction_sign,
              baseline_value, test_value, numeric_delta, magnitude_label, relative_delta_percent,
              verdict, confidence_score, discipline_score,
              target_zone_start_pct, target_zone_end_pct,
              median_lap_delta_s, pace_noise_band_s,
              target_speed_delta_mph, cfs_delta_in,
              driver_repeatability_score, context_problem_count, evidence_json
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(comparison_id, setup_key, target_zone_start_pct, target_zone_end_pct)
            DO UPDATE SET
              created_at=excluded.created_at,
              verdict=excluded.verdict,
              confidence_score=excluded.confidence_score,
              discipline_score=excluded.discipline_score,
              magnitude_label=excluded.magnitude_label,
              relative_delta_percent=excluded.relative_delta_percent,
              median_lap_delta_s=excluded.median_lap_delta_s,
              pace_noise_band_s=excluded.pace_noise_band_s,
              target_speed_delta_mph=excluded.target_speed_delta_mph,
              cfs_delta_in=excluded.cfs_delta_in,
              driver_repeatability_score=excluded.driver_repeatability_score,
              evidence_json=excluded.evidence_json
            """,
            (
                observation_id, comparison_id, _utc_now(), car_name, track_name,
                baseline_run_id, test_run_id, baseline_lap, test_lap,
                change.setup_key, change.label, change.group, direction_sign,
                str(change.baseline_value), str(change.test_value), numeric_delta,
                magnitude_label, relative_delta_percent,
                verdict.verdict, verdict.confidence_score, discipline.score,
                target_zone.start_pct, target_zone.end_pct,
                pace.cohort_delta_s, pace.noise_band_s,
                _channel_delta(target_zone, "speed_mph"),
                _channel_delta(target_zone, "cfs_ride_height_in"),
                driver.repeatability_score, context_problem_count,
                json.dumps(evidence, separators=(",", ":")),
            ),
        )
    conn.close()
    return True


def get_setup_area_biases(
    car_name: str | None,
    track_name: str | None,
    *,
    minimum_observations: int = 3,
    db_path: str | Path | None = None,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Return only repeated, direction-specific history; sparse history stays neutral."""
    if not car_name or not track_name:
        return {}
    conn = initialize_database(db_path)
    rows = conn.execute(
        """
        SELECT setup_key, direction_sign, verdict, confidence_score,
               numeric_delta, magnitude_label, relative_delta_percent,
               median_lap_delta_s, target_speed_delta_mph
        FROM setup_response_observations
        WHERE car_name = ? AND track_name = ? AND direction_sign != 0
        """,
        (car_name, track_name),
    ).fetchall()
    conn.close()

    grouped: dict[tuple[str, int], list[Any]] = {}
    for row in rows:
        for area in CONTROL_TO_SETUP_AREAS.get(row["setup_key"], ()):
            grouped.setdefault((area, int(row["direction_sign"])), []).append(row)

    result: dict[tuple[str, int], dict[str, Any]] = {}
    outcome_value = {"keep_direction": 1.0, "undo": -1.0, "retest": 0.0, "inconclusive": 0.0}
    for key, observations in grouped.items():
        if len(observations) < minimum_observations:
            continue
        weights = [max(0.05, min(1.0, float(row["confidence_score"] or 0.0))) for row in observations]
        weighted_outcome = sum(
            outcome_value.get(row["verdict"], 0.0) * weight
            for row, weight in zip(observations, weights)
        ) / sum(weights)
        lap_deltas = [float(row["median_lap_delta_s"]) for row in observations if row["median_lap_delta_s"] is not None]
        speed_deltas = [float(row["target_speed_delta_mph"]) for row in observations if row["target_speed_delta_mph"] is not None]
        numeric_deltas = [abs(float(row["numeric_delta"])) for row in observations if row["numeric_delta"] is not None]
        relative_deltas = [float(row["relative_delta_percent"]) for row in observations if row["relative_delta_percent"] is not None]
        magnitude_counts = Counter(str(row["magnitude_label"] or "unknown") for row in observations)
        magnitude_outcomes: dict[str, float] = {}
        for magnitude in magnitude_counts:
            magnitude_rows = [row for row in observations if str(row["magnitude_label"] or "unknown") == magnitude]
            magnitude_weights = [max(0.05, min(1.0, float(row["confidence_score"] or 0.0))) for row in magnitude_rows]
            magnitude_outcomes[magnitude] = round(sum(
                outcome_value.get(row["verdict"], 0.0) * weight
                for row, weight in zip(magnitude_rows, magnitude_weights)
            ) / sum(magnitude_weights), 3)
        result[key] = {
            "count": len(observations),
            "weighted_outcome": round(weighted_outcome, 3),
            "mean_lap_delta_s": round(sum(lap_deltas) / len(lap_deltas), 4) if lap_deltas else None,
            "mean_target_speed_delta_mph": round(sum(speed_deltas) / len(speed_deltas), 4) if speed_deltas else None,
            "mean_abs_numeric_delta": round(sum(numeric_deltas) / len(numeric_deltas), 4) if numeric_deltas else None,
            "mean_relative_delta_percent": round(sum(relative_deltas) / len(relative_deltas), 3) if relative_deltas else None,
            "magnitude_counts": dict(magnitude_counts),
            "weighted_outcome_by_magnitude": magnitude_outcomes,
        }
    return result
