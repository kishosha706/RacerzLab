from __future__ import annotations

import math
from typing import Any, Mapping

NEXT_GEN_CAR_PATHS = {
    "stockcars chevycamarozl12022",
    "stockcars fordmustang2022",
    "stockcars toyotacamry2022",
}

LR_RIDE_HEIGHT_OFFSET_IN = -0.5
LR_RIDE_HEIGHT_OFFSET_REASON = "Next Gen LR ride-height calibration"
MM_PER_IN = 25.4

OFFSET_METADATA_KEYS = (
    "lr_ride_height_offset_applied",
    "lr_ride_height_offset_in",
    "lr_ride_height_offset_reason",
    "lr_ride_height_offset_car_path",
)


def normalize_car_path(car_path: Any) -> str | None:
    if car_path is None:
        return None
    text = str(car_path).strip().lower()
    return text or None


def is_next_gen_car_path(car_path: Any) -> bool:
    return normalize_car_path(car_path) in NEXT_GEN_CAR_PATHS


def lr_ride_height_offset_metadata(car_path: Any) -> dict[str, Any]:
    normalized = normalize_car_path(car_path)
    applied = normalized in NEXT_GEN_CAR_PATHS
    return {
        "lr_ride_height_offset_applied": applied,
        "lr_ride_height_offset_in": LR_RIDE_HEIGHT_OFFSET_IN if applied else 0.0,
        "lr_ride_height_offset_reason": LR_RIDE_HEIGHT_OFFSET_REASON if applied else None,
        "lr_ride_height_offset_car_path": normalized,
    }


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _average(*values: Any) -> float | None:
    numbers = [_finite_number(value) for value in values]
    if any(value is None for value in numbers):
        return None
    return sum(value for value in numbers if value is not None) / len(numbers)


def _difference(left: Any, right: Any) -> float | None:
    left_number = _finite_number(left)
    right_number = _finite_number(right)
    if left_number is None or right_number is None:
        return None
    return left_number - right_number


def _rear_risk_from_mm(value: Any) -> float | None:
    rear_mm = _finite_number(value)
    if rear_mm is None:
        return None
    from racelab_engine.analysis.constants import REAR_CRITICAL_MM, REAR_HIGH_MM, REAR_SCRAPE_MM, REAR_WATCH_MM

    return next(
        (
            score
            for threshold, score in (
                (REAR_SCRAPE_MM, 1.0),
                (REAR_CRITICAL_MM, 0.92),
                (REAR_HIGH_MM, 0.72),
                (REAR_WATCH_MM, 0.38),
            )
            if rear_mm <= threshold
        ),
        0.08,
    )


def recompute_lr_platform_derivatives(row: dict[str, Any]) -> None:
    lf = _finite_number(row.get("lf_ride_height_in"))
    rf = _finite_number(row.get("rf_ride_height_in"))
    lr = _finite_number(row.get("lr_ride_height_in"))
    rr = _finite_number(row.get("rr_ride_height_in"))

    rear_avg = _average(lr, rr)
    left_avg = _average(lf, lr)
    right_avg = _average(rf, rr)
    row["rear_avg_rh_in"] = rear_avg
    row["left_avg_rh_in"] = left_avg
    row["right_avg_rh_in"] = right_avg
    cfs = _finite_number(row.get("cfs_ride_height_in"))
    row["center_rake_fs_in"] = rear_avg - cfs if rear_avg is not None and cfs is not None else None
    row["side_rake_in"] = right_avg - left_avg if right_avg is not None and left_avg is not None else None
    row["rear_split_in"] = _difference(rr, lr)

    lr_mm = _finite_number(row.get("lr_ride_height_mm"))
    rr_mm = _finite_number(row.get("rr_ride_height_mm"))
    if lr_mm is None or rr_mm is None:
        row["rear_min_ride_height_mm"] = None
        row["rear_min_ride_height_in"] = None
        row["rear_scrape_margin_mm"] = None
        row["rear_scrape_risk_score"] = None
        row["rear_platform_contact_risk"] = None
        row["rear_scrape_side"] = None
        row["rear_scrape_side_label"] = None
    else:
        from racelab_engine.analysis.constants import REAR_SCRAPE_MM

        rear_min = min(lr_mm, rr_mm)
        row["rear_min_ride_height_mm"] = rear_min
        row["rear_min_ride_height_in"] = rear_min / MM_PER_IN
        row["rear_scrape_margin_mm"] = rear_min - REAR_SCRAPE_MM
        risk = _rear_risk_from_mm(rear_min)
        row["rear_scrape_risk_score"] = risk
        row["rear_platform_contact_risk"] = risk
        if abs(lr_mm - rr_mm) < 0.001:
            side = 0
        else:
            side = -1 if lr_mm < rr_mm else 1
        row["rear_scrape_side"] = side
        row["rear_scrape_side_label"] = {-1: "left_rear", 0: "both_rear", 1: "right_rear"}[side]

    cfs_risk = _finite_number(row.get("cfs_risk_score"))
    rear_risk = _finite_number(row.get("rear_scrape_risk_score"))
    if rear_risk is not None:
        row["rear_platform_risk_score"] = rear_risk
    if cfs_risk is not None and rear_risk is not None:
        row["whole_car_bottoming_risk"] = min(cfs_risk, rear_risk)
    else:
        row["whole_car_bottoming_risk"] = None

    elevated = 0.72
    if cfs_risk is None or rear_risk is None:
        row["platform_balance_label"] = "unavailable"
        row["platform_balance_explanation"] = "Insufficient ride-height channels to classify platform balance."
    elif cfs_risk >= elevated and rear_risk >= elevated:
        row["platform_balance_label"] = "whole_car_bottoming"
        row["platform_balance_explanation"] = "Front and rear are both low - likely whole-car bottoming or ride height too low."
    elif cfs_risk >= elevated:
        row["platform_balance_label"] = "front_platform_risk"
        row["platform_balance_explanation"] = "Front/CFS is low while rear platform is safe - likely splitter/front platform risk."
    elif rear_risk >= elevated:
        row["platform_balance_label"] = "rear_platform_risk"
        row["platform_balance_explanation"] = "Rear platform is low while front/CFS is safe - likely rear platform contact or rear bottoming."
    else:
        row["platform_balance_label"] = "balanced_safe"
        row["platform_balance_explanation"] = "Front and rear platform margins look safe."


def apply_next_gen_lr_ride_height_offset_to_row(
    row: dict[str, Any],
    car_path: Any = None,
    *,
    recompute_derived: bool = False,
) -> None:
    detection_path = normalize_car_path(car_path if car_path is not None else row.get("car_path"))
    metadata = lr_ride_height_offset_metadata(detection_path)
    applied = bool(metadata["lr_ride_height_offset_applied"])

    row["lr_ride_height_offset_applied"] = applied
    row["lr_ride_height_offset_in"] = metadata["lr_ride_height_offset_in"]
    row["lr_ride_height_offset_reason"] = metadata["lr_ride_height_offset_reason"]
    row["lr_ride_height_offset_car_path"] = detection_path
    if detection_path is not None:
        row.setdefault("car_path", detection_path)

    lr_in = _finite_number(row.get("lr_ride_height_in"))
    lr_mm = _finite_number(row.get("lr_ride_height_mm"))
    if lr_in is None:
        row["lr_ride_height_in"] = None
    if lr_mm is None:
        row["lr_ride_height_mm"] = None

    if not applied or row.get("lr_ride_height_offset_already_applied") is True:
        if recompute_derived:
            recompute_lr_platform_derivatives(row)
        return
    if row.get("lr_ride_height_offset_applied_to_values") is True:
        if recompute_derived:
            recompute_lr_platform_derivatives(row)
        return

    if lr_in is not None:
        row.setdefault("lr_ride_height_raw_in", lr_in)
        row["lr_ride_height_in"] = lr_in + LR_RIDE_HEIGHT_OFFSET_IN
    if lr_mm is not None:
        row.setdefault("lr_ride_height_raw_mm", lr_mm)
        row["lr_ride_height_mm"] = lr_mm + LR_RIDE_HEIGHT_OFFSET_IN * MM_PER_IN
    if lr_in is not None or lr_mm is not None:
        row["lr_ride_height_offset_applied_to_values"] = True
    if recompute_derived:
        recompute_lr_platform_derivatives(row)


def apply_next_gen_lr_ride_height_offset_to_rows(
    rows: list[dict[str, Any]],
    car_path: Any = None,
    *,
    recompute_derived: bool = False,
) -> None:
    for row in rows:
        apply_next_gen_lr_ride_height_offset_to_row(row, car_path=car_path, recompute_derived=recompute_derived)


def trace_offset_metadata(rows: list[Mapping[str, Any]], car_path: Any = None) -> dict[str, Any]:
    detection_path = normalize_car_path(car_path)
    if detection_path is None:
        detection_path = next(
            (
                normalize_car_path(row.get("lr_ride_height_offset_car_path") or row.get("car_path"))
                for row in rows
                if normalize_car_path(row.get("lr_ride_height_offset_car_path") or row.get("car_path")) is not None
            ),
            None,
        )
    return lr_ride_height_offset_metadata(detection_path)
