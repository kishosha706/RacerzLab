"""Held-out shadow scoring for separate response, mechanism, and policy targets."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import Field

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


Direction = Literal[-1, 0, 1]
PolicyVerdict = Literal["keep", "undo", "retest", "inconclusive"]


class ResponseWorkflowCase(EvidenceLabModel):
    workflow_id: str = Field(min_length=1)
    partition: Literal["train", "calibration", "evaluation", "prospective"]
    complete_aba2: bool
    one_control: bool
    exact_context: bool
    restoration_passed: bool
    target_metric_sign: Direction
    mechanism_response_sign: Direction
    policy_verdict: PolicyVerdict
    countereffect_occurred: bool
    predicted_target_metric_sign: Direction
    predicted_mechanism_response_sign: Direction
    predicted_policy_verdict: PolicyVerdict
    predicted_countereffect: bool
    synthetic: bool = False


class ResponseTargetScore(EvidenceLabModel):
    target_key: str
    accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    no_model_baseline_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    beats_baseline: bool


class ResponseModelEvaluation(EvidenceLabModel):
    evaluated_workflows: int = Field(ge=0)
    excluded_workflows: int = Field(ge=0)
    real_workflows: int = Field(ge=0)
    synthetic_workflows: int = Field(ge=0)
    target_metric: ResponseTargetScore
    mechanism_response: ResponseTargetScore
    policy_verdict: ResponseTargetScore
    countereffect: ResponseTargetScore
    state: Literal["valid", "invalid"]
    blockers: tuple[str, ...]
    authority: Literal["shadow_only"] = "shadow_only"


def evaluate_response_model(
    cases: tuple[ResponseWorkflowCase, ...],
) -> ResponseModelEvaluation:
    blockers: list[str] = []
    workflow_ids = [case.workflow_id for case in cases]
    if len(workflow_ids) != len(set(workflow_ids)):
        blockers.append("A workflow appears more than once in response evaluation.")
    evaluation_cases = [
        case for case in cases if case.partition in {"evaluation", "prospective"}
    ]
    qualified = [
        case
        for case in evaluation_cases
        if case.complete_aba2
        and case.one_control
        and case.exact_context
        and case.restoration_passed
    ]
    if not qualified:
        blockers.append("No protocol-valid held-out workflows are available.")
    scores = {
        "target_metric": _score(
            "target_metric_sign",
            qualified,
            actual=lambda case: case.target_metric_sign,
            predicted=lambda case: case.predicted_target_metric_sign,
        ),
        "mechanism_response": _score(
            "mechanism_response_sign",
            qualified,
            actual=lambda case: case.mechanism_response_sign,
            predicted=lambda case: case.predicted_mechanism_response_sign,
        ),
        "policy_verdict": _score(
            "policy_verdict",
            qualified,
            actual=lambda case: case.policy_verdict,
            predicted=lambda case: case.predicted_policy_verdict,
        ),
        "countereffect": _score(
            "countereffect_occurred",
            qualified,
            actual=lambda case: case.countereffect_occurred,
            predicted=lambda case: case.predicted_countereffect,
        ),
    }
    if qualified and not all(score.beats_baseline for score in scores.values()):
        blockers.append("Shadow response model does not beat every descriptive baseline.")
    return ResponseModelEvaluation(
        evaluated_workflows=len(qualified),
        excluded_workflows=len(evaluation_cases) - len(qualified),
        real_workflows=sum(not case.synthetic for case in qualified),
        synthetic_workflows=sum(case.synthetic for case in qualified),
        target_metric=scores["target_metric"],
        mechanism_response=scores["mechanism_response"],
        policy_verdict=scores["policy_verdict"],
        countereffect=scores["countereffect"],
        state="invalid" if blockers else "valid",
        blockers=tuple(blockers),
    )


def _score(target_key, cases, *, actual, predicted) -> ResponseTargetScore:
    if not cases:
        return ResponseTargetScore(target_key=target_key, beats_baseline=False)
    actual_values = [actual(case) for case in cases]
    accuracy = sum(actual(case) == predicted(case) for case in cases) / len(cases)
    baseline = Counter(actual_values).most_common(1)[0][1] / len(cases)
    return ResponseTargetScore(
        target_key=target_key,
        accuracy=accuracy,
        no_model_baseline_accuracy=baseline,
        beats_baseline=accuracy > baseline,
    )


__all__ = [
    "ResponseModelEvaluation",
    "ResponseTargetScore",
    "ResponseWorkflowCase",
    "evaluate_response_model",
]
