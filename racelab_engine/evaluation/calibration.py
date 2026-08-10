"""Shadow-only probability calibration and conformal coverage diagnostics."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


class CalibrationObservation(EvidenceLabModel):
    unit_id: str = Field(min_length=1)
    predicted_probability: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    outcome: Literal[0, 1]
    subgroup: str = Field(min_length=1)
    partition: Literal["train", "calibration", "evaluation", "prospective"]
    synthetic: bool = False


class ReliabilityBin(EvidenceLabModel):
    lower: float = Field(ge=0.0, le=1.0)
    upper: float = Field(ge=0.0, le=1.0)
    count: int = Field(ge=0)
    mean_prediction: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class ProbabilityCalibrationEvaluation(EvidenceLabModel):
    independent_units: int = Field(ge=0)
    real_units: int = Field(ge=0)
    synthetic_units: int = Field(ge=0)
    brier_score: float | None = Field(default=None, ge=0.0, le=1.0)
    log_loss: float | None = Field(default=None, ge=0.0)
    reliability: tuple[ReliabilityBin, ...]
    subgroup_metrics: dict[str, dict[str, float | int | None]]
    state: Literal["valid", "invalid"]
    blockers: tuple[str, ...]
    probability_authority: Literal[False] = False
    authority: Literal["shadow_only"] = "shadow_only"


class IntervalObservation(EvidenceLabModel):
    unit_id: str
    lower: float = Field(allow_inf_nan=False)
    upper: float = Field(allow_inf_nan=False)
    actual: float = Field(allow_inf_nan=False)
    subgroup: str
    partition: Literal["calibration", "evaluation", "prospective"]

    @model_validator(mode="after")
    def interval_is_ordered(self) -> IntervalObservation:
        if self.lower > self.upper:
            raise ValueError("uncertainty interval must be ordered")
        return self


class CoverageEvaluation(EvidenceLabModel):
    nominal_coverage: float = Field(gt=0.0, lt=1.0)
    actual_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_interval_width: float | None = Field(default=None, ge=0.0)
    subgroup_coverage: dict[str, float | None]
    independent_units: int = Field(ge=0)
    state: Literal["valid", "invalid"]
    blockers: tuple[str, ...]
    public_intervals_allowed: Literal[False] = False
    authority: Literal["shadow_only"] = "shadow_only"


def evaluate_probability_calibration(
    observations: tuple[CalibrationObservation, ...],
    *,
    bins: int = 10,
) -> ProbabilityCalibrationEvaluation:
    blockers: list[str] = []
    if bins < 2:
        raise ValueError("calibration requires at least two reliability bins")
    unit_ids = [observation.unit_id for observation in observations]
    if len(unit_ids) != len(set(unit_ids)):
        blockers.append("Calibration observations duplicate an independence unit.")
    held_out = [
        observation
        for observation in observations
        if observation.partition in {"evaluation", "prospective"}
    ]
    if not held_out:
        blockers.append("No untouched evaluation or prospective outcomes are available.")
    brier = (
        None
        if not held_out
        else round(
            sum(
                (observation.predicted_probability - observation.outcome) ** 2
                for observation in held_out
            )
            / len(held_out),
            12,
        )
    )
    epsilon = 1e-15
    log_loss = (
        None
        if not held_out
        else round(
            -sum(
                observation.outcome
                * math.log(max(epsilon, observation.predicted_probability))
                + (1 - observation.outcome)
                * math.log(max(epsilon, 1.0 - observation.predicted_probability))
                for observation in held_out
            )
            / len(held_out),
            12,
        )
    )
    reliability = _reliability_bins(held_out, bins)
    subgroup_metrics: dict[str, dict[str, float | int | None]] = {}
    for subgroup in sorted({observation.subgroup for observation in held_out}):
        group = [observation for observation in held_out if observation.subgroup == subgroup]
        subgroup_metrics[subgroup] = {
            "count": len(group),
            "brier_score": round(
                sum(
                    (observation.predicted_probability - observation.outcome) ** 2
                    for observation in group
                )
                / len(group),
                12,
            ),
        }
    return ProbabilityCalibrationEvaluation(
        independent_units=len(held_out),
        real_units=sum(not observation.synthetic for observation in held_out),
        synthetic_units=sum(observation.synthetic for observation in held_out),
        brier_score=brier,
        log_loss=log_loss,
        reliability=reliability,
        subgroup_metrics=subgroup_metrics,
        state="invalid" if blockers else "valid",
        blockers=tuple(blockers),
    )


def evaluate_interval_coverage(
    observations: tuple[IntervalObservation, ...],
    *,
    nominal_coverage: float,
) -> CoverageEvaluation:
    if not 0.0 < nominal_coverage < 1.0:
        raise ValueError("nominal coverage must be between zero and one")
    blockers: list[str] = []
    unit_ids = [observation.unit_id for observation in observations]
    if len(unit_ids) != len(set(unit_ids)):
        blockers.append("Coverage observations duplicate an independence unit.")
    held_out = [
        observation
        for observation in observations
        if observation.partition in {"evaluation", "prospective"}
    ]
    if not held_out:
        blockers.append("No untouched coverage evaluation set is available.")
    covered = [
        observation.lower <= observation.actual <= observation.upper
        for observation in held_out
    ]
    by_subgroup: dict[str, list[bool]] = defaultdict(list)
    for observation, is_covered in zip(held_out, covered):
        by_subgroup[observation.subgroup].append(is_covered)
    return CoverageEvaluation(
        nominal_coverage=nominal_coverage,
        actual_coverage=None if not covered else sum(covered) / len(covered),
        mean_interval_width=(
            None
            if not held_out
            else sum(observation.upper - observation.lower for observation in held_out)
            / len(held_out)
        ),
        subgroup_coverage={
            subgroup: sum(values) / len(values)
            for subgroup, values in sorted(by_subgroup.items())
        },
        independent_units=len(held_out),
        state="invalid" if blockers else "valid",
        blockers=tuple(blockers),
    )


def _reliability_bins(
    observations: list[CalibrationObservation],
    bins: int,
) -> tuple[ReliabilityBin, ...]:
    buckets: list[list[CalibrationObservation]] = [[] for _ in range(bins)]
    for observation in observations:
        index = min(bins - 1, int(observation.predicted_probability * bins))
        buckets[index].append(observation)
    result = []
    for index, bucket in enumerate(buckets):
        result.append(
            ReliabilityBin(
                lower=index / bins,
                upper=(index + 1) / bins,
                count=len(bucket),
                mean_prediction=(
                    None
                    if not bucket
                    else sum(item.predicted_probability for item in bucket) / len(bucket)
                ),
                observed_rate=(
                    None if not bucket else sum(item.outcome for item in bucket) / len(bucket)
                ),
            )
        )
    return tuple(result)


__all__ = [
    "CalibrationObservation",
    "CoverageEvaluation",
    "IntervalObservation",
    "ProbabilityCalibrationEvaluation",
    "ReliabilityBin",
    "evaluate_interval_coverage",
    "evaluate_probability_calibration",
]
