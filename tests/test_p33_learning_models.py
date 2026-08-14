from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from racelab_engine.models.engineering_learning import (
    AttentionOrderItem,
    CarResponseFact,
    CrewChiefLearningPrior,
    EngineeringExperienceContext,
    EngineeringExperienceRecord,
    EngineeringLearningLedger,
    EngineeringSourceProvenance,
    EvidenceUnitCounts,
    P19CauseMemory,
    P19ReasoningMemory,
    PerformanceResponseFact,
    PostRunLearningBrief,
    ProblemFingerprint,
    RecurringProblemMatch,
)


def _counts(*, observations: int = 0, episodes: int = 0, workflows: int = 0):
    return EvidenceUnitCounts(
        observation_count=observations,
        independent_episode_count=episodes,
        independent_workflow_count=workflows,
        distinct_session_count=min(observations, 1),
        distinct_context_count=min(observations, 1),
    )


def _context() -> EngineeringExperienceContext:
    return EngineeringExperienceContext.build(
        run_id="run-a",
        session_id="session-a",
        driver_id="driver-a",
        car_path="nascar-nextgen-chevy",
        car_version="2026.08",
        iracing_build="2026.08.1",
        track="atlanta",
        track_configuration="oval",
        package_type="speedway",
        setup_family=None,
        setup_snapshot_sha256="a" * 64,
        objective="race_long_run",
        physical_scope_sha256="b" * 64,
        phase="center",
        physical_region="T1-T2",
        speed_load_band="high_speed_loaded",
        fuel_state="short_run",
        tire_state="short_run",
        weather_state="recorded",
        traffic_state="clear",
        driver_execution_state="matched_inputs",
    )


def _problem() -> ProblemFingerprint:
    return ProblemFingerprint.build(
        physical_episode_id="episode-a",
        performance_opportunity_id="opportunity-a",
        phase="center",
        physical_region="T1-T2",
        time_origin_class="local_loss",
        carry_behavior="following_straight_carry",
        driver_demand_state="matched_inputs",
        vehicle_response_state="changed_response",
        p20_mechanism_families=("platform", "tire_state"),
        p26_component_families=("rf_tire",),
        traffic_context_state="clear",
        tire_stint_state="short_run",
        objective="race_long_run",
        source_artifact_ids=("artifact-a",),
    )


def _provenance() -> EngineeringSourceProvenance:
    return EngineeringSourceProvenance.build(
        artifact_id="artifact-a",
        producer_id="p33.controlled-workflow",
        run_id="run-a",
        session_id="session-a",
        setup_id="setup-a",
        setup_snapshot_sha256="a" * 64,
        build_context_sha256="4" * 64,
        lap_numbers=(7,),
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        phase="center",
        source_channels=("speed_mps",),
        evidence_state="controlled_test_effect",
        polarity="support",
    )


def _reasoning() -> P19ReasoningMemory:
    return P19ReasoningMemory(
        reasoning_snapshot_sha256="c" * 64,
        causes=(
            P19CauseMemory(
                cause_id="cause-platform",
                status="possible",
                ordinal_rank=1,
                mechanism_family="platform",
            ),
            P19CauseMemory(
                cause_id="cause-tire",
                status="possible",
                ordinal_rank=2,
                mechanism_family="tire_state",
            ),
        ),
        measurement_plan_kind="measurement_only",
        discriminator_ids=("tire-state-development",),
        authority_level="measurement",
        setup_authorized=False,
    )


def _ledger() -> EngineeringLearningLedger:
    return EngineeringLearningLedger(
        investigations_opened=0,
        investigations_resolved=0,
        no_call_outcomes=0,
        driver_focus_outcomes=0,
        measurement_missions=0,
        controlled_tests=0,
        keep_outcomes=0,
        undo_outcomes=0,
        retest_outcomes=0,
        laps_consumed_before_resolution=0,
        questions_asked=0,
        recurring_problem_count=0,
        recurrence_resolved_faster_count=0,
    )


def _empty_prior(**updates: object) -> CrewChiefLearningPrior:
    values = {
        "history_revision": "d" * 64,
        "run_id": "run-a",
        "session_id": "session-a",
        "objective_id": "race_long_run",
        "selected_scope_hash": "e" * 64,
        "p19_reasoning_snapshot_sha256": "c" * 64,
        "p32_projection_sha256": "f" * 64,
        "current_context_sha256": _context().context_sha256,
        "current_problem_sha256": _problem().problem_sha256,
        "state": "insufficient_history",
        "recurrence": RecurringProblemMatch(
            recurrence_id="recurrence-none",
            classification="new_problem",
            problem_sha256s=(_problem().problem_sha256,),
            statement="No prior recurrence is qualified.",
            strongest_contradiction="No independent prior episode is available.",
            counts=_counts(),
            strength="insufficient",
        ),
        "context_transfer_level": "blocked",
        "strength": "insufficient",
        "counts": _counts(),
        "ledger": _ledger(),
        "post_run_brief": PostRunLearningBrief(
            state="insufficient_history",
            blocker_reasons=("No qualified history is available.",),
        ),
        "blocker_reasons": ("No qualified history is available.",),
    }
    values.update(updates)
    return CrewChiefLearningPrior.build(**values)


def test_experience_identity_is_deterministic_and_tamper_evident() -> None:
    values = {
        "source_kind": "controlled_workflow",
        "source_workflow_id": "workflow-a",
        "created_at": datetime(2026, 8, 14, 12, tzinfo=timezone.utc),
        "context": _context(),
        "problem": _problem(),
        "source_p19_reasoning_snapshot_sha256": "c" * 64,
        "source_p32_projection_sha256": "f" * 64,
        "closing_reasoning": _reasoning(),
        "source_provenance": (_provenance(),),
        "source_artifact_ids": ("artifact-a",),
    }
    first = EngineeringExperienceRecord.build(**values)
    second = EngineeringExperienceRecord.build(**values)

    assert first == second
    assert EngineeringExperienceRecord.model_validate_json(first.model_dump_json()) == first
    hostile = first.model_dump(mode="json")
    hostile["context"]["traffic_state"] = "traffic"
    with pytest.raises(ValidationError, match="context identity is corrupt"):
        EngineeringExperienceRecord.model_validate(hostile)

    with pytest.raises(ValidationError, match="nested facts"):
        EngineeringExperienceRecord.build(
            **{
                **values,
                "problem": ProblemFingerprint.build(
                    **{
                        **_problem().model_dump(
                            mode="python", exclude={"problem_sha256"}
                        ),
                        "source_artifact_ids": ("detached-artifact",),
                    }
                ),
            }
        )

    with pytest.raises(ValidationError, match="closing reasoning"):
        EngineeringExperienceRecord.build(
            **{**values, "source_p19_reasoning_snapshot_sha256": "d" * 64}
        )


def test_signed_performance_history_and_undo_axes_are_fail_closed() -> None:
    with pytest.raises(ValidationError, match="sign is inconsistent"):
        PerformanceResponseFact(
            observed_delta_s=-0.1,
            observed_direction="loss",
            attribution_state="candidate_only",
            time_origin="center",
            recovery_surrender="recovered",
        )
    with pytest.raises(ValidationError, match="sign is inconsistent"):
        PerformanceResponseFact(
            observed_delta_s=0.0,
            observed_direction="loss",
            attribution_state="candidate_only",
            time_origin="center",
            recovery_surrender="recovered",
        )
    with pytest.raises(ValidationError, match="unavailable attribution"):
        PerformanceResponseFact(
            observed_delta_s=0.1,
            observed_direction="loss",
            attribution_state="unavailable",
            time_origin="center",
            recovery_surrender="recovered",
        )
    with pytest.raises(ValidationError, match="preserve its countereffect"):
        CarResponseFact(
            response_id="response-a",
            component="platform",
            control="cross_weight",
            direction="decrease",
            magnitude_class="small",
            expected_vehicle_response="more center rotation",
            observed_vehicle_response="center rotation increased",
            p32_time_origin="center",
            recovery_surrender="carried_to_exit",
            p19_mechanism_assessment="unchanged",
            control_response_assessment="matched",
            policy_verdict="undo",
            source_workflow_id="workflow-a",
        )

    base_response = {
        "response_id": "response-safe",
        "component": "platform",
        "control": "cross_weight_percent",
        "direction": "decrease",
        "magnitude_class": "adjacent",
        "expected_vehicle_response": "The workflow preserved its response metric.",
        "observed_vehicle_response": "The recorded control response was matched.",
        "p32_time_origin": "center",
        "recovery_surrender": "No measured carry was recorded.",
        "p19_mechanism_assessment": "unchanged",
        "control_response_assessment": "matched",
        "policy_verdict": "keep",
        "source_workflow_id": "workflow-safe",
    }
    with pytest.raises(ValidationError, match="exceeds attention-only authority"):
        CarResponseFact(
            **{
                **base_response,
                "observed_vehicle_response": "Set cross weight to 52%.",
            }
        )
    with pytest.raises(ValidationError, match="magnitude_class"):
        CarResponseFact(**{**base_response, "magnitude_class": "0.5%"})


def test_p19_memory_preserves_canonical_competition_ranking_ties() -> None:
    memory = P19ReasoningMemory(
        reasoning_snapshot_sha256="d" * 64,
        causes=(
            P19CauseMemory(
                cause_id="leading",
                status="likely",
                ordinal_rank=1,
                mechanism_family="tire_state",
            ),
            P19CauseMemory(
                cause_id="platform-left",
                status="possible",
                ordinal_rank=2,
                mechanism_family="platform",
            ),
            P19CauseMemory(
                cause_id="platform-right",
                status="possible",
                ordinal_rank=2,
                mechanism_family="platform",
            ),
        ),
        measurement_plan_kind="discriminator",
        discriminator_ids=("separate-platform-from-tire",),
        authority_level="measurement",
        setup_authorized=False,
    )

    assert tuple(item.ordinal_rank for item in memory.causes) == (1, 2, 2)


@pytest.mark.parametrize(
    "statement",
    (
        "Set cross weight to 52%.",
        "Cross weight was 52% in the prior setup.",
        "Keep the change.",
        "Shocks caused the loss.",
        "The shocks drove the loss.",
        "The loss came from the dampers.",
        "This response explains the handling problem.",
        "The instability was attributable to cross weight.",
    ),
)
def test_memory_prose_cannot_smuggle_setup_or_causal_authority(statement: str) -> None:
    with pytest.raises(ValidationError, match="exceeds attention-only authority"):
        RecurringProblemMatch(
            recurrence_id="recurrence-a",
            classification="possible_recurrence",
            problem_sha256s=(_problem().problem_sha256,),
            experience_ids=("p33x_" + "1" * 24,),
            statement=statement,
            strongest_contradiction="The current evidence remains unresolved.",
            counts=_counts(observations=1, episodes=1),
            strength="single_case",
        )


def test_memory_prose_allows_explicit_non_causal_and_dead_end_language() -> None:
    match = RecurringProblemMatch(
        recurrence_id="recurrence-non-causal",
        classification="possible_recurrence",
        problem_sha256s=(_problem().problem_sha256,),
        experience_ids=("p33x_" + "1" * 24,),
        statement=(
            "Shock inspection produced no discriminating evidence and did not cause the observed loss."
        ),
        strongest_contradiction="The current evidence remains unresolved.",
        counts=_counts(observations=1, episodes=1),
        strength="single_case",
    )
    assert "did not cause" in match.statement


def test_references_cannot_inflate_strong_recurrence() -> None:
    with pytest.raises(ValidationError, match="two independent evidence units"):
        RecurringProblemMatch(
            recurrence_id="recurrence-a",
            classification="strong_recurrence",
            problem_sha256s=(_problem().problem_sha256,),
            experience_ids=("p33x_" + "1" * 24,),
            statement="A prior qualified case has a similar physical pattern.",
            strongest_contradiction="Only one independent episode is qualified.",
            counts=_counts(observations=20, episodes=1, workflows=0),
            strength="single_case",
        )


def test_weak_or_blocked_history_cannot_reorder_crew_tools() -> None:
    attention = AttentionOrderItem(
        tool_id="inspect_tire_state",
        safety_band="current_measurements",
        learned_rank_within_band=1,
        baseline_rank_within_band=2,
        reason="Prior exact cases used this discriminator earlier.",
        transfer_level="exact",
        source_experience_ids=(
            "p33x_" + "1" * 24,
            "p33x_" + "2" * 24,
        ),
        investigation_count=2,
        session_count=2,
        independent_workflow_count=0,
    )
    with pytest.raises(ValidationError, match="blocked P33 history"):
        _empty_prior(
            state="blocked",
            recommended_attention_order=(attention,),
            context_transfer_level="blocked",
            blocker_reasons=("Build compatibility is not reviewed.",),
        )


def test_prior_contract_has_no_probability_or_current_setup_action_surface() -> None:
    prior = _empty_prior()
    assert prior.authority == "attention_only"
    assert prior.setup_authorized is False
    assert prior.p19_rank_modified is False
    schema_text = str(CrewChiefLearningPrior.model_json_schema()).casefold()
    for forbidden in (
        "probability",
        "confidence_score",
        "setup_target",
        "setup_direction",
        "terminal_setup_action",
    ):
        assert forbidden not in schema_text
    hostile = prior.model_dump(mode="json")
    hostile["learned_probability"] = 0.9
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CrewChiefLearningPrior.model_validate(hostile)
