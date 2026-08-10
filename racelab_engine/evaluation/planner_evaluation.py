"""Offline deterministic-planner versus candidate-planner comparisons."""

from __future__ import annotations

from statistics import median
from typing import Literal

from pydantic import Field

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel


class PlannerComparisonCase(EvidenceLabModel):
    session_id: str = Field(min_length=1)
    partition: Literal["evaluation", "prospective"]
    deterministic_clean_laps: int = Field(ge=0)
    candidate_clean_laps: int = Field(ge=0)
    deterministic_blockers_closed: int = Field(ge=0)
    candidate_blockers_closed: int = Field(ge=0)
    deterministic_mechanisms_discriminated: int = Field(ge=0)
    candidate_mechanisms_discriminated: int = Field(ge=0)
    deterministic_mission_failures: int = Field(ge=0)
    candidate_mission_failures: int = Field(ge=0)
    deterministic_false_stop: bool
    candidate_false_stop: bool
    candidate_authority_violations: int = Field(ge=0)


class PlannerCandidateEvaluation(EvidenceLabModel):
    independent_sessions: int = Field(ge=0)
    prospective_sessions: int = Field(ge=0)
    median_clean_lap_cost_delta: float | None = None
    mean_blockers_closed_delta: float | None = None
    mean_mechanisms_discriminated_delta: float | None = None
    mission_failure_delta: int = 0
    false_stop_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    authority_violations: int = Field(ge=0)
    outperforms_deterministic: bool
    state: Literal["invalid", "historical_shadow", "prospective_shadow"]
    blockers: tuple[str, ...]
    planner_authority: Literal[False] = False
    authority: Literal["shadow_only"] = "shadow_only"


def evaluate_candidate_planner(
    cases: tuple[PlannerComparisonCase, ...],
) -> PlannerCandidateEvaluation:
    blockers: list[str] = []
    if len({case.session_id for case in cases}) != len(cases):
        blockers.append("Planner comparison duplicates an independent session.")
    if not cases:
        blockers.append("No held-out planner comparisons are available.")
    lap_deltas = [case.candidate_clean_laps - case.deterministic_clean_laps for case in cases]
    blocker_deltas = [
        case.candidate_blockers_closed - case.deterministic_blockers_closed
        for case in cases
    ]
    mechanism_deltas = [
        case.candidate_mechanisms_discriminated
        - case.deterministic_mechanisms_discriminated
        for case in cases
    ]
    failure_delta = sum(
        case.candidate_mission_failures - case.deterministic_mission_failures
        for case in cases
    )
    false_stop_rate = (
        None if not cases else sum(case.candidate_false_stop for case in cases) / len(cases)
    )
    violations = sum(case.candidate_authority_violations for case in cases)
    median_lap_delta = None if not lap_deltas else float(median(lap_deltas))
    mean_blocker_delta = None if not cases else sum(blocker_deltas) / len(cases)
    mean_mechanism_delta = None if not cases else sum(mechanism_deltas) / len(cases)
    outperforms = bool(cases) and (
        violations == 0
        and false_stop_rate is not None
        and false_stop_rate <= 0.05
        and median_lap_delta is not None
        and median_lap_delta <= 0.0
        and failure_delta <= 0
        and mean_blocker_delta is not None
        and mean_blocker_delta >= 0.0
        and mean_mechanism_delta is not None
        and mean_mechanism_delta >= 0.0
        and (mean_blocker_delta > 0.0 or mean_mechanism_delta > 0.0)
    )
    if violations:
        blockers.append("Candidate planner committed an authority violation.")
    if false_stop_rate is not None and false_stop_rate > 0.05:
        blockers.append("Candidate planner false-stop rate exceeds five percent.")
    if median_lap_delta is not None and median_lap_delta > 0.0:
        blockers.append("Candidate planner increased median clean-lap cost.")
    if cases and not outperforms and not blockers:
        blockers.append("Candidate planner did not outperform the deterministic baseline.")
    prospective = sum(case.partition == "prospective" for case in cases)
    return PlannerCandidateEvaluation(
        independent_sessions=len(cases),
        prospective_sessions=prospective,
        median_clean_lap_cost_delta=median_lap_delta,
        mean_blockers_closed_delta=mean_blocker_delta,
        mean_mechanisms_discriminated_delta=mean_mechanism_delta,
        mission_failure_delta=failure_delta,
        false_stop_rate=false_stop_rate,
        authority_violations=violations,
        outperforms_deterministic=outperforms,
        state=(
            "invalid"
            if blockers
            else "prospective_shadow"
            if prospective == len(cases)
            else "historical_shadow"
        ),
        blockers=tuple(blockers),
    )


__all__ = [
    "PlannerCandidateEvaluation",
    "PlannerComparisonCase",
    "evaluate_candidate_planner",
]
