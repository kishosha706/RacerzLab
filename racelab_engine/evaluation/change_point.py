"""Offline-only frozen change-point candidate evaluation."""

from __future__ import annotations

import math
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel, canonical_hash


class ChangePointConfig(EvidenceLabModel):
    config_id: str = Field(pattern=r"^cpc-[0-9a-f]{20}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    version: str = Field(min_length=1)
    method: Literal["p20_persistent", "robust_threshold", "cusum", "pelt"]
    threshold: float = Field(gt=0.0, allow_inf_nan=False)
    minimum_segment_laps: int = Field(ge=2)
    localization_tolerance_laps: int = Field(ge=0)
    tuned_on_partitions: tuple[Literal["train", "calibration", "evaluation"], ...]
    authority: Literal["shadow_only"] = "shadow_only"

    @model_validator(mode="after")
    def config_is_frozen_before_evaluation(self) -> ChangePointConfig:
        payload = self.model_dump(mode="json", exclude={"config_id", "config_hash"})
        expected = canonical_hash(payload)
        if self.config_hash != expected or self.config_id != f"cpc-{expected[:20]}":
            raise ValueError("change-point config identity does not match its content")
        return self


class StintSeries(EvidenceLabModel):
    stint_id: str = Field(min_length=1)
    lap_numbers: tuple[int, ...] = Field(min_length=4)
    values: tuple[float, ...] = Field(min_length=4)
    known_change_lap: int | None = None
    known_null: bool = False
    context_contaminated: bool = False
    synthetic: bool = False
    partition: Literal["train", "calibration", "evaluation", "prospective"]

    @model_validator(mode="after")
    def stint_is_contiguous_and_labeled(self) -> StintSeries:
        if len(self.lap_numbers) != len(self.values):
            raise ValueError("stint lap/value lengths differ")
        if any(
            later != earlier + 1
            for earlier, later in zip(self.lap_numbers, self.lap_numbers[1:])
        ):
            raise ValueError("change-point stints must be uninterrupted")
        if self.known_null == (self.known_change_lap is not None):
            raise ValueError("stints require exactly one null or known-shift label")
        if self.known_change_lap is not None and self.known_change_lap not in self.lap_numbers:
            raise ValueError("known change lap is outside the stint")
        if not all(math.isfinite(value) for value in self.values):
            raise ValueError("change-point values must be finite")
        return self


class ChangePointStintResult(EvidenceLabModel):
    stint_id: str
    detected_laps: tuple[int, ...]
    known_change_lap: int | None
    known_null: bool
    localization_error_laps: int | None = Field(default=None, ge=0)
    context_contaminated: bool
    synthetic: bool


class ChangePointEvaluation(EvidenceLabModel):
    config_id: str
    method: str
    state: Literal["valid", "invalid", "unavailable"]
    evaluated_stints: int = Field(ge=0)
    null_stints: int = Field(ge=0)
    shifted_stints: int = Field(ge=0)
    synthetic_stints: int = Field(ge=0)
    false_change_point_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    detection_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    median_localization_error_laps: float | None = Field(default=None, ge=0.0)
    contaminated_detection_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    results: tuple[ChangePointStintResult, ...]
    blockers: tuple[str, ...]
    authority: Literal["shadow_only"] = "shadow_only"


def build_change_point_config(**payload) -> ChangePointConfig:
    if {"config_id", "config_hash"} & payload.keys():
        raise ValueError("change-point config identity is derived")
    normalized = {"authority": "shadow_only", **payload}
    config_hash = canonical_hash(normalized)
    return ChangePointConfig(
        config_id=f"cpc-{config_hash[:20]}",
        config_hash=config_hash,
        **normalized,
    )


def evaluate_change_points(
    config: ChangePointConfig,
    stints: tuple[StintSeries, ...],
) -> ChangePointEvaluation:
    blockers: list[str] = []
    if "evaluation" in config.tuned_on_partitions:
        blockers.append("Detector parameters were selected on the evaluation set.")
    if config.method == "pelt":
        blockers.append("PELT candidate is unavailable without a frozen implementation.")
        return _evaluation(config, stints, (), blockers, state="unavailable")
    evaluation_stints = tuple(
        stint for stint in stints if stint.partition in {"evaluation", "prospective"}
    )
    if not evaluation_stints:
        blockers.append("No untouched evaluation or prospective stints are available.")
    results = tuple(_score_stint(config, stint) for stint in evaluation_stints)
    return _evaluation(
        config,
        evaluation_stints,
        results,
        blockers,
        state="invalid" if blockers else "valid",
    )


def _score_stint(
    config: ChangePointConfig,
    stint: StintSeries,
) -> ChangePointStintResult:
    indexes = (
        _cusum_indexes(stint.values, config)
        if config.method == "cusum"
        else _robust_indexes(stint.values, config)
    )
    detected_laps = tuple(stint.lap_numbers[index] for index in indexes)
    error = (
        None
        if stint.known_change_lap is None or not detected_laps
        else min(abs(lap - stint.known_change_lap) for lap in detected_laps)
    )
    return ChangePointStintResult(
        stint_id=stint.stint_id,
        detected_laps=detected_laps,
        known_change_lap=stint.known_change_lap,
        known_null=stint.known_null,
        localization_error_laps=error,
        context_contaminated=stint.context_contaminated,
        synthetic=stint.synthetic,
    )


def _robust_indexes(values: tuple[float, ...], config: ChangePointConfig) -> tuple[int, ...]:
    minimum = config.minimum_segment_laps
    candidates: list[tuple[float, float, int]] = []
    for index in range(minimum, len(values) - minimum + 1):
        before = median(values[:index])
        after = median(values[index:])
        delta = abs(after - before)
        if delta >= config.threshold:
            absolute_error = sum(abs(value - before) for value in values[:index]) + sum(
                abs(value - after) for value in values[index:]
            )
            candidates.append((absolute_error, -delta, index))
    return () if not candidates else (min(candidates)[2],)


def _cusum_indexes(values: tuple[float, ...], config: ChangePointConfig) -> tuple[int, ...]:
    baseline = median(values[: config.minimum_segment_laps])
    positive = 0.0
    negative = 0.0
    for index, value in enumerate(values[config.minimum_segment_laps :], start=config.minimum_segment_laps):
        delta = value - baseline
        positive = max(0.0, positive + delta)
        negative = min(0.0, negative + delta)
        if positive >= config.threshold or abs(negative) >= config.threshold:
            return (index,)
    return ()


def _evaluation(
    config: ChangePointConfig,
    stints: tuple[StintSeries, ...],
    results: tuple[ChangePointStintResult, ...],
    blockers: list[str],
    *,
    state: Literal["valid", "invalid", "unavailable"],
) -> ChangePointEvaluation:
    null_results = [result for result in results if result.known_null]
    shifted = [result for result in results if result.known_change_lap is not None]
    detected_shifted = [
        result
        for result in shifted
        if result.localization_error_laps is not None
        and result.localization_error_laps <= config.localization_tolerance_laps
    ]
    localization = [
        result.localization_error_laps
        for result in shifted
        if result.localization_error_laps is not None
    ]
    contaminated = [result for result in results if result.context_contaminated]
    return ChangePointEvaluation(
        config_id=config.config_id,
        method=config.method,
        state=state,
        evaluated_stints=len(stints),
        null_stints=len(null_results),
        shifted_stints=len(shifted),
        synthetic_stints=sum(stint.synthetic for stint in stints),
        false_change_point_rate=(
            None
            if not null_results
            else sum(bool(result.detected_laps) for result in null_results)
            / len(null_results)
        ),
        detection_recall=(
            None if not shifted else len(detected_shifted) / len(shifted)
        ),
        median_localization_error_laps=(
            None if not localization else float(median(localization))
        ),
        contaminated_detection_rate=(
            None
            if not contaminated
            else sum(bool(result.detected_laps) for result in contaminated)
            / len(contaminated)
        ),
        results=results,
        blockers=tuple(blockers),
    )


__all__ = [
    "ChangePointConfig",
    "ChangePointEvaluation",
    "ChangePointStintResult",
    "StintSeries",
    "build_change_point_config",
    "evaluate_change_points",
]
