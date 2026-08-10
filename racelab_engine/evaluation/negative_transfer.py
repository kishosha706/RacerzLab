"""Fail-closed comparison of hierarchical transfer against no transfer."""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


class TransferCase(EvidenceLabModel):
    unit_id: str
    subgroup: Literal[
        "same_driver_same_track",
        "same_driver_different_track",
        "different_driver_same_track",
        "different_driver_different_track",
        "same_build",
        "different_build",
    ]
    no_transfer_error: float = Field(ge=0.0, allow_inf_nan=False)
    transfer_error: float = Field(ge=0.0, allow_inf_nan=False)


class NegativeTransferEvaluation(EvidenceLabModel):
    independent_units: int = Field(ge=0)
    subgroup_error_delta: dict[str, float]
    negative_transfer_subgroups: tuple[str, ...]
    state: Literal["locked", "no_negative_transfer_observed"]
    authority: Literal["evaluation_only"] = "evaluation_only"


def evaluate_negative_transfer(
    cases: tuple[TransferCase, ...],
) -> NegativeTransferEvaluation:
    if len({case.unit_id for case in cases}) != len(cases):
        raise ValueError("transfer cases must use unique independence units")
    groups: dict[str, list[TransferCase]] = defaultdict(list)
    for case in cases:
        groups[case.subgroup].append(case)
    deltas = {
        subgroup: sum(case.transfer_error - case.no_transfer_error for case in group)
        / len(group)
        for subgroup, group in sorted(groups.items())
    }
    negative = tuple(subgroup for subgroup, delta in deltas.items() if delta > 0.0)
    return NegativeTransferEvaluation(
        independent_units=len(cases),
        subgroup_error_delta=deltas,
        negative_transfer_subgroups=negative,
        state="locked" if negative else "no_negative_transfer_observed",
    )


__all__ = ["NegativeTransferEvaluation", "TransferCase", "evaluate_negative_transfer"]
