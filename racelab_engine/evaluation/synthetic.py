"""Deterministic signal injections for detector mechanics, never real validation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


class SyntheticSignal(EvidenceLabModel):
    signal_id: str = Field(min_length=1)
    values: tuple[float | None, ...] = Field(min_length=2)
    injection_kind: Literal[
        "none",
        "shift",
        "delay",
        "gap",
        "clipping",
        "slip_onset",
        "thermal_lag",
        "pit_boundary",
    ]
    injection_index: int | None = Field(default=None, ge=0)
    magnitude: float | None = Field(default=None, allow_inf_nan=False)
    synthetic: Literal[True] = True
    allowed_use: Literal["mechanics_and_failure_behavior_only"] = (
        "mechanics_and_failure_behavior_only"
    )

    @model_validator(mode="after")
    def injection_index_is_in_range(self) -> SyntheticSignal:
        if self.injection_kind == "none" and self.injection_index is not None:
            raise ValueError("null synthetic signals cannot have an injection index")
        if self.injection_kind != "none" and (
            self.injection_index is None or self.injection_index >= len(self.values)
        ):
            raise ValueError("synthetic injection index is outside the signal")
        return self


def constant_signal(signal_id: str, *, length: int, value: float) -> SyntheticSignal:
    if length < 2:
        raise ValueError("synthetic signals require at least two values")
    return SyntheticSignal(
        signal_id=signal_id,
        values=(float(value),) * length,
        injection_kind="none",
    )


def inject_shift(
    signal_id: str,
    base_values: tuple[float, ...],
    *,
    index: int,
    magnitude: float,
) -> SyntheticSignal:
    _validate_index(base_values, index)
    values = tuple(
        value if position < index else value + magnitude
        for position, value in enumerate(base_values)
    )
    return SyntheticSignal(
        signal_id=signal_id,
        values=values,
        injection_kind="shift",
        injection_index=index,
        magnitude=magnitude,
    )


def inject_gap(
    signal_id: str,
    base_values: tuple[float, ...],
    *,
    index: int,
    width: int = 1,
) -> SyntheticSignal:
    _validate_index(base_values, index)
    if width < 1 or index + width > len(base_values):
        raise ValueError("synthetic gap width is outside the signal")
    values: list[float | None] = list(base_values)
    values[index : index + width] = [None] * width
    return SyntheticSignal(
        signal_id=signal_id,
        values=tuple(values),
        injection_kind="gap",
        injection_index=index,
        magnitude=float(width),
    )


def inject_clipping(
    signal_id: str,
    base_values: tuple[float, ...],
    *,
    index: int,
    ceiling: float,
) -> SyntheticSignal:
    _validate_index(base_values, index)
    values = tuple(
        value if position < index else min(value, ceiling)
        for position, value in enumerate(base_values)
    )
    return SyntheticSignal(
        signal_id=signal_id,
        values=values,
        injection_kind="clipping",
        injection_index=index,
        magnitude=ceiling,
    )


def inject_delay(
    signal_id: str,
    base_values: tuple[float, ...],
    *,
    index: int,
    samples: int,
    kind: Literal["delay", "thermal_lag"] = "delay",
) -> SyntheticSignal:
    _validate_index(base_values, index)
    if samples < 1:
        raise ValueError("synthetic delay must be positive")
    anchor = base_values[index - 1] if index else base_values[index]
    values = list(base_values)
    values[index : min(len(values), index + samples)] = [anchor] * min(
        samples,
        len(values) - index,
    )
    return SyntheticSignal(
        signal_id=signal_id,
        values=tuple(values),
        injection_kind=kind,
        injection_index=index,
        magnitude=float(samples),
    )


def inject_slip_onset(
    signal_id: str,
    base_values: tuple[float, ...],
    *,
    index: int,
    magnitude: float,
) -> SyntheticSignal:
    shifted = inject_shift(signal_id, base_values, index=index, magnitude=magnitude)
    return SyntheticSignal(
        **shifted.model_dump(exclude={"injection_kind"}),
        injection_kind="slip_onset",
    )


def inject_thermal_lag(
    signal_id: str,
    base_values: tuple[float, ...],
    *,
    index: int,
    samples: int,
) -> SyntheticSignal:
    return inject_delay(
        signal_id,
        base_values,
        index=index,
        samples=samples,
        kind="thermal_lag",
    )


def inject_pit_boundary(
    signal_id: str,
    base_values: tuple[float, ...],
    *,
    index: int,
) -> SyntheticSignal:
    _validate_index(base_values, index)
    return SyntheticSignal(
        signal_id=signal_id,
        values=base_values,
        injection_kind="pit_boundary",
        injection_index=index,
        magnitude=0.0,
    )


def _validate_index(values: tuple[float, ...], index: int) -> None:
    if len(values) < 2 or not 0 <= index < len(values):
        raise ValueError("synthetic injection index is outside the signal")


__all__ = [
    "SyntheticSignal",
    "constant_signal",
    "inject_clipping",
    "inject_delay",
    "inject_gap",
    "inject_pit_boundary",
    "inject_slip_onset",
    "inject_shift",
    "inject_thermal_lag",
]
