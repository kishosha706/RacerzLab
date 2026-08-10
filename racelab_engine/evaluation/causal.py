"""Offline scoring of protocol-valid intervention effects and placebo controls."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


class ControlledEffectCase(EvidenceLabModel):
    workflow_id: str = Field(min_length=1)
    control_family: str = Field(min_length=1)
    partition: Literal["train", "calibration", "evaluation", "prospective"]
    complete_aba2: bool
    one_control: bool
    exact_context: bool
    observational_only: bool = False
    intervention_delta: float = Field(allow_inf_nan=False)
    baseline_a: float = Field(allow_inf_nan=False)
    intervention_b: float = Field(allow_inf_nan=False)
    restoration_a2: float = Field(allow_inf_nan=False)
    restoration_tolerance: float = Field(ge=0.0, allow_inf_nan=False)
    noise_threshold: float = Field(ge=0.0, allow_inf_nan=False)
    placebo: bool = False
    mechanism_response_sign: Literal[-1, 0, 1]
    policy_verdict: Literal["keep", "undo", "retest", "inconclusive"]
    countereffect_occurred: bool
    synthetic: bool = False

    @model_validator(mode="after")
    def placebo_has_no_intervention(self) -> ControlledEffectCase:
        if self.placebo and abs(self.intervention_delta) > 1e-12:
            raise ValueError("placebo workflows cannot contain an intervention delta")
        return self

    @property
    def restoration_passed(self) -> bool:
        return abs(self.restoration_a2 - self.baseline_a) <= self.restoration_tolerance

    @property
    def shadow_effect(self) -> float:
        return self.intervention_b - mean((self.baseline_a, self.restoration_a2))


class ControlFamilyEffect(EvidenceLabModel):
    control_family: str
    workflows: int = Field(ge=0)
    median_shadow_effect: float | None = Field(default=None, allow_inf_nan=False)
    direction_replication: float | None = Field(default=None, ge=0.0, le=1.0)
    countereffect_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    keep_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class CausalEffectEvaluation(EvidenceLabModel):
    qualified_workflows: int = Field(ge=0)
    excluded_workflows: int = Field(ge=0)
    placebo_workflows: int = Field(ge=0)
    placebo_false_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    restoration_pass_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    control_families: tuple[ControlFamilyEffect, ...]
    state: Literal["valid", "invalid"]
    blockers: tuple[str, ...]
    production_causal_authority: Literal[False] = False
    authority: Literal["shadow_only"] = "shadow_only"


def evaluate_controlled_effects(
    cases: tuple[ControlledEffectCase, ...],
) -> CausalEffectEvaluation:
    blockers: list[str] = []
    ids = [case.workflow_id for case in cases]
    if len(ids) != len(set(ids)):
        blockers.append("A controlled workflow appears more than once.")
    held_out = [case for case in cases if case.partition in {"evaluation", "prospective"}]
    protocol = [
        case
        for case in held_out
        if case.complete_aba2
        and case.one_control
        and case.exact_context
        and not case.observational_only
        and case.restoration_passed
        and (case.placebo or abs(case.intervention_delta) > 1e-12)
    ]
    if not protocol:
        blockers.append("No protocol-valid held-out interventions are available.")
    placebo = [case for case in protocol if case.placebo]
    placebo_false_positive_rate = (
        None
        if not placebo
        else sum(abs(case.shadow_effect) > case.noise_threshold for case in placebo)
        / len(placebo)
    )
    if not placebo:
        blockers.append("No held-out placebo workflow is available.")
    restoration_pass_rate = (
        None
        if not held_out
        else sum(case.restoration_passed for case in held_out) / len(held_out)
    )
    by_family: dict[str, list[ControlledEffectCase]] = defaultdict(list)
    for case in protocol:
        if not case.placebo:
            by_family[case.control_family].append(case)
    families = []
    for family, rows in sorted(by_family.items()):
        effects = [case.shadow_effect for case in rows]
        effect_signs = [0 if abs(value) <= 1e-12 else (1 if value > 0.0 else -1) for value in effects]
        replicated = Counter(effect_signs).most_common(1)[0][1] / len(effect_signs)
        ordered = sorted(effects)
        middle = len(ordered) // 2
        median_effect = (
            ordered[middle]
            if len(ordered) % 2
            else mean((ordered[middle - 1], ordered[middle]))
        )
        families.append(
            ControlFamilyEffect(
                control_family=family,
                workflows=len(rows),
                median_shadow_effect=median_effect,
                direction_replication=replicated,
                countereffect_rate=sum(row.countereffect_occurred for row in rows) / len(rows),
                keep_rate=sum(row.policy_verdict == "keep" for row in rows) / len(rows),
            )
        )
    return CausalEffectEvaluation(
        qualified_workflows=len(protocol),
        excluded_workflows=len(held_out) - len(protocol),
        placebo_workflows=len(placebo),
        placebo_false_positive_rate=placebo_false_positive_rate,
        restoration_pass_rate=restoration_pass_rate,
        control_families=tuple(families),
        state="invalid" if blockers else "valid",
        blockers=tuple(blockers),
    )


__all__ = [
    "CausalEffectEvaluation",
    "ControlFamilyEffect",
    "ControlledEffectCase",
    "evaluate_controlled_effects",
]
