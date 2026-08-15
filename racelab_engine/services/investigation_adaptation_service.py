"""Deterministic P34 paired-policy evaluation and shadow-only readiness."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Iterable, Literal

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.investigation_adaptation import (
    DiscriminatorOutcome,
    InvestigationDecision,
    InvestigationAdaptationContext,
    InvestigationImprovementProjection,
    InvestigationImprovementReadiness,
    InvestigationNegativeTransfer,
    InvestigationOutcomeCertificate,
    InvestigationOutcomeFollowup,
    InvestigationPolicy,
    InvestigationPolicyEvaluation,
    NegativeControlConditionEvidence,
    P19CauseChange,
    P19CauseState,
    P34ActivationDecision,
    P34EfficiencyResults,
    P34InvestigationActivationProtocol,
    P34NegativeControlResult,
    P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS,
    P34QualityResults,
    P34SafetyResults,
    P34SubgroupResult,
    PairedInvestigationComparison,
    PairedInvestigationDecision,
    SafeReorderGroup,
    canonical_context_subgroups,
    investigation_adaptation_source_snapshot_sha256,
)
from racelab_engine.storage.investigation_adaptation_repository import (
    InvestigationAdaptationIntegrityError,
    InvestigationAdaptationRepository,
)
from racelab_engine.storage.db import (
    connect_read_only,
    default_db_path,
    initialize_database,
)


_FROZEN_AT = datetime(2026, 8, 15, 8, 12, 46, tzinfo=timezone.utc)
_CODE_VERSION = "p34.earned-investigation-adaptation.v1"
_VERIFIED_P34_CHAIN_KEYS: dict[tuple[object, ...], None] = {}
_EFFECTIVE_ACTIVATION_CACHE: dict[
    tuple[object, ...], P34ActivationDecision
] = {}
_REPOSITORY_EVALUATION_CACHE: dict[
    tuple[object, ...], InvestigationPolicyEvaluation
] = {}
_P34_SOURCE_REVISION_TRIGGERS = frozenset(
    {
        "p34_source_revision_p34_insert",
        "p34_source_revision_p34_update",
        "p34_source_revision_p34_delete",
        "p34_source_revision_crew_investigation_insert",
        "p34_source_revision_crew_investigation_update",
        "p34_source_revision_crew_investigation_delete",
        "p34_source_revision_crew_event_insert",
        "p34_source_revision_crew_event_update",
        "p34_source_revision_crew_event_delete",
        "p34_source_revision_p33_insert",
        "p34_source_revision_p33_update",
        "p34_source_revision_p33_delete",
        "p34_source_revision_workflow_insert",
        "p34_source_revision_workflow_update",
        "p34_source_revision_workflow_delete",
        "p34_source_revision_run_insert",
        "p34_source_revision_run_update",
        "p34_source_revision_run_delete",
    }
)
_ALLOWED_TOOL_IDS = (
    "inspect_data_quality",
    "inspect_lap_context",
    "inspect_driver_execution",
    "inspect_p19_causes",
    "inspect_mechanism_episodes",
    "inspect_component_state",
    "inspect_controlled_history",
    "inspect_measurement_debt",
    "inspect_lap_time_opportunity",
    "inspect_time_loss_origin",
    "inspect_corner_performance_chain",
    "inspect_exit_carry",
    "inspect_path_efficiency",
    "inspect_driver_vehicle_separation",
    "inspect_track_demand",
    "inspect_component_performance_link",
    "inspect_objective_tradeoff",
)


def _repository_database_file(
    repository: InvestigationAdaptationRepository,
) -> str:
    """Resolve the repository's implicit application database consistently."""

    return str(Path(repository.db_path or default_db_path()).resolve())


_PRECEDENCE_RULES = (
    "identity_integrity",
    "context_qualification",
    "driver_car_confounders",
    "strongest_contradiction",
    "unresolved_p19_mechanisms",
    "component_family_separation",
    "exact_history",
    "measurement_debt",
)
_REORDER_GROUPS = (
    SafeReorderGroup(
        group_id="performance_measurement",
        priority_tier="driver_car_confounders",
        ordered_action_ids=(
            "inspect_lap_time_opportunity",
            "inspect_time_loss_origin",
            "inspect_corner_performance_chain",
            "inspect_exit_carry",
            "inspect_path_efficiency",
            "inspect_driver_vehicle_separation",
            "inspect_track_demand",
        ),
    ),
)


def classify_p34_problem_family(
    *,
    phase: str,
    objective: str,
    driver_demand_state: str,
    vehicle_response_state: str,
) -> Literal[
    "braking",
    "entry",
    "center",
    "exit",
    "straight",
    "long_run",
    "mixed",
    "unresolved",
]:
    """Derive the frozen physical family from producer-owned P33 facts."""

    normalized = phase.casefold().replace("-", "_").replace(" ", "_")
    if "brak" in normalized:
        return "braking"
    if any(marker in normalized for marker in ("entry", "turn_in", "turnin")):
        return "entry"
    if any(marker in normalized for marker in ("center", "centre", "apex", "mid_corner")):
        return "center"
    if any(marker in normalized for marker in ("exit", "throttle_pickup", "power_down")):
        return "exit"
    if "straight" in normalized:
        return "straight"
    if any(marker in normalized for marker in ("long_run", "stint", "degradation")):
        return "long_run"
    if objective == "race_long_run" and normalized in {
        "run",
        "lap",
        "whole_lap",
        "unknown",
    }:
        return "long_run"
    unresolved = {"unknown", "unresolved", "unavailable"}
    if (
        driver_demand_state.casefold() not in unresolved
        and vehicle_response_state.casefold() not in unresolved
    ):
        return "mixed"
    return "unresolved"


def classify_p34_problem_orientation(
    *,
    driver_demand_state: str,
    vehicle_response_state: str,
) -> Literal["driver", "vehicle", "combined", "unresolved"]:
    """Separate driver and vehicle evidence without trusting a pair label."""

    unresolved = {"unknown", "unresolved", "unavailable"}
    demand_known = driver_demand_state.casefold() not in unresolved
    response_known = vehicle_response_state.casefold() not in unresolved
    if demand_known and not response_known:
        return "driver"
    if response_known and not demand_known:
        return "vehicle"
    if demand_known and response_known:
        return "combined"
    return "unresolved"


def classify_p34_track_class(
    *,
    track: str,
    track_configuration: str,
    package_type: str,
) -> Literal[
    "short_track", "intermediate", "superspeedway", "road_course", "unknown"
]:
    """Derive the frozen track subgroup from exact producer context."""

    normalized_track = track.casefold()
    configuration = track_configuration.casefold()
    package = package_type.casefold()
    if any(name in normalized_track for name in ("daytona", "talladega")):
        return "superspeedway"
    if any(
        name in normalized_track
        for name in (
            "bristol",
            "martinsville",
            "richmond",
            "phoenix",
            "wilkesboro",
            "irp",
            "newhampshire",
            "new hampshire",
        )
    ):
        return "short_track"
    if "road" in configuration or "road" in package:
        return "road_course"
    if "oval" in configuration or "speedway" in package:
        return "intermediate"
    return "unknown"


def _policy_configuration_hash(kind: str, maximum_reorder_distance: int) -> str:
    return canonical_json_sha256(
        {
            "code_version": _CODE_VERSION,
            "kind": kind,
            "allowed_tool_ids": _ALLOWED_TOOL_IDS,
            "hard_precedence_rules": _PRECEDENCE_RULES,
            "safe_reorder_groups": _REORDER_GROUPS,
            "maximum_reorder_distance": maximum_reorder_distance,
        }
    )


@lru_cache(maxsize=1)
def baseline_investigation_policy() -> InvestigationPolicy:
    return InvestigationPolicy.build(
        policy_version="p34.deterministic-baseline.v1",
        kind="deterministic_baseline",
        allowed_tool_ids=_ALLOWED_TOOL_IDS,
        hard_precedence_rules=_PRECEDENCE_RULES,
        safe_reorder_groups=_REORDER_GROUPS,
        maximum_reorder_distance=0,
        learning_source_schema="none",
        created_at=_FROZEN_AT,
        code_version=_CODE_VERSION,
        configuration_hash=_policy_configuration_hash(
            "deterministic_baseline", 0
        ),
    )


@lru_cache(maxsize=1)
def memory_shadow_investigation_policy() -> InvestigationPolicy:
    return InvestigationPolicy.build(
        policy_version="p34.memory-informed-shadow.v1",
        kind="memory_informed_shadow",
        allowed_tool_ids=_ALLOWED_TOOL_IDS,
        hard_precedence_rules=_PRECEDENCE_RULES,
        safe_reorder_groups=_REORDER_GROUPS,
        maximum_reorder_distance=1,
        learning_source_schema="p33.engineering-experience.v1",
        created_at=_FROZEN_AT,
        code_version=_CODE_VERSION,
        configuration_hash=_policy_configuration_hash(
            "memory_informed_shadow", 1
        ),
    )


@lru_cache(maxsize=1)
def limited_attention_investigation_policy() -> InvestigationPolicy:
    return InvestigationPolicy.build(
        policy_version="p34.limited-attention.v1",
        kind="limited_attention",
        allowed_tool_ids=_ALLOWED_TOOL_IDS,
        hard_precedence_rules=_PRECEDENCE_RULES,
        safe_reorder_groups=_REORDER_GROUPS,
        maximum_reorder_distance=1,
        learning_source_schema="p33.engineering-experience.v1",
        created_at=_FROZEN_AT,
        code_version=_CODE_VERSION,
        configuration_hash=_policy_configuration_hash("limited_attention", 1),
    )


@lru_cache(maxsize=1)
def p34_activation_protocol() -> P34InvestigationActivationProtocol:
    baseline = baseline_investigation_policy()
    memory = memory_shadow_investigation_policy()
    activated = limited_attention_investigation_policy()
    return P34InvestigationActivationProtocol.build(
        protocol_version="p34.investigation-activation.v1",
        frozen_at=_FROZEN_AT,
        prospective_boundary=_FROZEN_AT,
        baseline_policy_id=baseline.policy_id,
        baseline_policy_sha256=baseline.policy_sha256,
        memory_policy_id=memory.policy_id,
        memory_policy_sha256=memory.policy_sha256,
        activated_policy_id=activated.policy_id,
        activated_policy_sha256=activated.policy_sha256,
        eligibility_rules=(
            "completed qualified investigation with exact run/session/workspace identity",
            "frozen pair exists before outcome exposure",
            "exact P19 snapshot and P33 provenance are present",
            "ordered tool request/result lineage and outcome certificate are present",
            "one investigation counts once regardless of revisions or tool steps",
        ),
        exclusions=(
            "synthetic mechanics-only cases",
            "junk or context-ineligible investigations",
            "counterfactual-unobservable success claims",
            "history created at or after the paired decision",
            "future or unreviewed build transfer",
            "selective removal after outcome exposure",
            "v1 driver-question or prior-surface learned reordering",
        ),
        metrics=(
            "authority violations",
            "P19 action mismatches",
            "mandatory integrity/context/contradiction checks",
            "tool steps to trustworthy terminal decision",
            "elapsed time to trustworthy next move",
            "driver questions consumed",
            "laps consumed",
            "measurement missions consumed",
            "dead-end inspections",
            "repeated no-finding inspections",
            "useful-discriminator timing and hit rate",
            "strongest-contradiction inspection rate",
            "recurrence-match correctness",
            "context-transfer correctness",
            "driver-versus-car correctness",
            "eventual P19 resolution rate",
            "no_call stability",
            "negative-transfer rate",
            "stable, material-drift, and unknown driver-state counts",
            "same, reviewed-compatible, and future-unreviewed build counts",
        ),
        required_subgroups=(
            "exact_context_history",
            "compatible_context_history",
            "weak_history",
            "driver_first",
            "vehicle_response",
            "mixed_problem",
            "braking",
            "entry",
            "center",
            "exit",
            "straight",
            "long_run",
            "qualifying_objective",
            "race_long_run_objective",
            "driver_confidence_objective",
            "short_track",
            "intermediate",
            "superspeedway",
            "stable_driver_fingerprint",
            "driver_drift_detected",
            "same_build",
            "reviewed_compatible_build",
        ),
        negative_control_ids=(
            "no_relevant_history",
            "incompatible_history",
            "corrupt_history",
            "generic_component_knowledge_only",
            "same_words_different_physical_scope",
            "material_driver_drift",
            "future_memory_record",
        ),
        drift_rules=(
            "material driver fingerprint drift blocks driver-history reordering",
            "current qualified evidence overrides historical dead-end attention",
            "future and unreviewed builds remain blocked",
        ),
        rollback_rules=(
            "missing or stale activation identity falls back to baseline",
            "any authority violation disables limited attention",
            "any mandatory-check violation disables limited attention",
            "unknown policy or protocol version falls back to baseline",
        ),
        minimum_historical_investigations=20,
        minimum_prospective_investigations=12,
        minimum_contexts=3,
        minimum_problem_families=4,
        minimum_objectives=2,
        minimum_exact_recurrence_cases=5,
        minimum_compatible_recurrence_cases=5,
        minimum_tool_step_reduction=1,
        minimum_relative_tool_step_reduction=0.15,
        minimum_earlier_discriminator_rate=0.60,
        minimum_dead_end_reduction_rate=0.15,
        maximum_unresolved_rate_worsening=0.05,
        maximum_negative_transfer_rate=0.10,
        maximum_subgroup_efficiency_degradation_pct=20,
    )


def persist_p34_foundation(
    repository: InvestigationAdaptationRepository,
    *,
    connection: sqlite3.Connection | None = None,
) -> None:
    """Append the frozen registry atomically on an explicit mutation path."""

    records = (
        baseline_investigation_policy(),
        memory_shadow_investigation_policy(),
        limited_attention_investigation_policy(),
        p34_activation_protocol(),
    )
    if connection is not None:
        for record in records:
            repository.append_record_in_transaction(connection, record)
        return
    active = initialize_database(repository.db_path)
    try:
        active.execute("BEGIN IMMEDIATE")
        for record in records:
            repository.append_record_in_transaction(active, record)
        active.commit()
    except Exception:
        active.rollback()
        raise
    finally:
        active.close()


def _policy_matches(left: InvestigationPolicy, right: InvestigationPolicy) -> bool:
    return left.policy_id == right.policy_id and left.policy_sha256 == right.policy_sha256


def canonical_investigation_evaluation_pair(
    pairs: Iterable[PairedInvestigationDecision],
) -> PairedInvestigationDecision:
    """Freeze one non-cherry-picked independence-unit representative."""

    ordered = tuple(
        sorted(
            pairs,
            key=lambda item: (item.step_number, item.pair_id),
        )
    )
    if not ordered:
        raise ValueError("P34 outcome requires at least one frozen paired decision")
    investigation_ids = {item.investigation_id for item in ordered}
    if len(investigation_ids) != 1 or len({item.step_number for item in ordered}) != len(
        ordered
    ):
        raise ValueError("P34 canonical pair cohort must be one investigation with unique steps")
    differing_inspections = tuple(
        item
        for item in ordered
        if item.baseline_decision.decision_kind == "inspect_tool"
        and item.memory_decision.decision_kind == "inspect_tool"
        and item.baseline_decision.executable_identity
        != item.memory_decision.executable_identity
    )
    if differing_inspections:
        return differing_inspections[0]
    inspections = tuple(
        item
        for item in ordered
        if item.baseline_decision.decision_kind == "inspect_tool"
    )
    return inspections[0] if inspections else ordered[0]


def _validate_decisions_against_frozen_policies(
    *,
    baseline_policy: InvestigationPolicy,
    memory_policy: InvestigationPolicy,
    baseline_decision: InvestigationDecision,
    memory_decision: InvestigationDecision,
    available_tool_ids: tuple[str, ...],
    eligible_tool_ids: tuple[str, ...],
    completed_tool_ids: tuple[str, ...],
) -> None:
    eligible = tuple(dict.fromkeys(eligible_tool_ids))
    if len(eligible) != len(eligible_tool_ids):
        raise ValueError("P34 eligible tool identities must be unique")
    for decision, policy in (
        (baseline_decision, baseline_policy),
        (memory_decision, memory_policy),
    ):
        if decision.decision_kind != "inspect_tool":
            if decision.safe_reorder_group is not None or decision.baseline_ordinal != decision.selected_ordinal:
                raise ValueError("P34 v1 non-tool decisions cannot be learned reorders")
            continue
        if decision.action_id not in eligible or decision.action_id not in policy.allowed_tool_ids:
            raise ValueError("P34 decision tool is not eligible under its frozen policy")
        matching_groups = tuple(
            group
            for group in policy.safe_reorder_groups
            if decision.action_id in group.ordered_action_ids
        )
        expected_group = matching_groups[0].group_id if matching_groups else None
        if decision.safe_reorder_group != expected_group:
            raise ValueError("P34 decision safe group does not match the frozen policy")
        if matching_groups:
            canonical_ordinal = (
                matching_groups[0].ordered_action_ids.index(decision.action_id) + 1
            )
        else:
            canonical_ordinal = 1
        if decision.baseline_ordinal != canonical_ordinal:
            raise ValueError("P34 decision baseline ordinal is not canonical")
    differs = (
        baseline_decision.executable_identity != memory_decision.executable_identity
    )
    expected_eligible: tuple[str, ...] = ()
    if baseline_decision.decision_kind == "inspect_tool":
        expected_eligible = (baseline_decision.action_id,)
        baseline_group = next(
            (
                group
                for group in baseline_policy.safe_reorder_groups
                if baseline_decision.action_id in group.ordered_action_ids
            ),
            None,
        )
        if baseline_group is not None:
            baseline_index = baseline_group.ordered_action_ids.index(
                baseline_decision.action_id
            )
            immediate_live = next(
                (
                    action_id
                    for action_id in baseline_group.ordered_action_ids[
                        baseline_index + 1 :
                    ]
                    if action_id in available_tool_ids
                    and action_id not in completed_tool_ids
                ),
                None,
            )
            if immediate_live is not None:
                expected_eligible = (*expected_eligible, immediate_live)
    if eligible_tool_ids != expected_eligible:
        raise ValueError(
            "P34 eligible tools must equal baseline plus the immediate live candidate"
        )
    if differs and (
        memory_decision.baseline_ordinal != baseline_decision.baseline_ordinal + 1
        or memory_decision.selected_ordinal != baseline_decision.selected_ordinal
    ):
        raise ValueError("P34 memory may promote only the next safe action by one slot")


def build_paired_investigation_decision(
    *,
    baseline_policy: InvestigationPolicy,
    memory_policy: InvestigationPolicy,
    investigation_id: str,
    investigation_opened_at: datetime,
    run_id: str,
    session_id: str,
    workspace_revision: str,
    authority_revision: str,
    step_number: int,
    baseline_decision: InvestigationDecision,
    memory_decision: InvestigationDecision,
    available_tool_ids: tuple[str, ...],
    eligible_tool_ids: tuple[str, ...],
    completed_tool_ids: tuple[str, ...],
    available_artifact_ids: tuple[str, ...],
    qualified_available_artifact_ids: tuple[str, ...] = (),
    qualified_available_artifact_evidence_states: tuple[
        Literal["measured", "calculated", "controlled_test_effect"], ...
    ] = (),
    qualified_available_artifact_provenance_sha256s: tuple[str, ...] = (),
    current_evidence_pinned_tool_ids: tuple[str, ...] = (),
    current_truth_sha256: str,
    p19_snapshot_sha256: str,
    current_p19_cause_ids: tuple[str, ...],
    current_p19_cause_states: tuple[P19CauseState, ...],
    current_contradiction_ids: tuple[str, ...],
    strongest_contradiction_id: str | None,
    current_objective: str,
    p33_projection_sha256: str,
    p33_history_revision: str,
    p33_ledger_head_sha256: str | None,
    p33_context_sha256: str,
    p33_problem_sha256: str,
    track: str,
    track_configuration: str,
    package_type: str,
    iracing_build: str,
    problem_family: Literal[
        "braking", "entry", "center", "exit", "straight", "long_run", "mixed", "unresolved"
    ],
    problem_orientation: Literal["driver", "vehicle", "combined", "unresolved"],
    track_class: Literal[
        "short_track", "intermediate", "superspeedway", "road_course", "unknown"
    ],
    phase: str,
    build_review_state: Literal[
        "same_build", "reviewed_compatible_build", "future_unreviewed_build"
    ],
    driver_drift_state: Literal["stable", "material_drift", "unknown"],
    decision_frozen_at: datetime,
    context_transfer_class: Literal[
        "none", "exact", "compatible", "weak", "blocked"
    ],
    p20_projection_sha256: str,
    p26_projection_sha256: str,
    p32_projection_sha256: str,
    negative_control_condition: Literal[
        "no_relevant_history",
        "incompatible_history",
        "corrupt_history",
        "generic_component_knowledge_only",
        "same_words_different_physical_scope",
        "material_driver_drift",
        "future_memory_record",
    ] | None = None,
    negative_control_evidence: NegativeControlConditionEvidence | None = None,
    future_memory_record_ids: tuple[str, ...] = (),
    activation_decision: P34ActivationDecision | None = None,
) -> PairedInvestigationDecision:
    canonical_baseline = baseline_investigation_policy()
    protocol = p34_activation_protocol()
    if not _policy_matches(baseline_policy, canonical_baseline):
        raise ValueError("P34 pair requires the frozen deterministic baseline policy")
    if decision_frozen_at.tzinfo is None:
        raise ValueError("P34 decision freeze time must be timezone-aware")
    _validate_decisions_against_frozen_policies(
        baseline_policy=baseline_policy,
        memory_policy=memory_policy,
        baseline_decision=baseline_decision,
        memory_decision=memory_decision,
        available_tool_ids=available_tool_ids,
        eligible_tool_ids=eligible_tool_ids,
        completed_tool_ids=completed_tool_ids,
    )
    if activation_decision is None:
        canonical_memory = memory_shadow_investigation_policy()
        if not _policy_matches(memory_policy, canonical_memory):
            raise ValueError("P34 shadow pair requires the frozen memory-shadow policy")
        activation_state: Literal["shadow_only", "limited_attention"] = "shadow_only"
        production_policy_kind: Literal[
            "deterministic_baseline", "limited_attention"
        ] = "deterministic_baseline"
        production_decision = baseline_decision
        activation_id = None
        activation_sha256 = None
    else:
        canonical_memory = limited_attention_investigation_policy()
        if (
            not _policy_matches(memory_policy, canonical_memory)
            or activation_decision.state != "limited_attention"
            or activation_decision.production_policy_kind != "limited_attention"
            or activation_decision.protocol_id != protocol.protocol_id
            or activation_decision.protocol_sha256 != protocol.protocol_sha256
            or activation_decision.activated_policy_id != protocol.activated_policy_id
            or activation_decision.activated_policy_sha256
            != protocol.activated_policy_sha256
            or activation_decision.blockers
        ):
            raise ValueError("P34 limited attention requires the exact earned activation")
        activation_state = "limited_attention"
        production_policy_kind = "limited_attention"
        production_decision = memory_decision
        activation_id = activation_decision.decision_id
        activation_sha256 = activation_decision.decision_sha256
    return PairedInvestigationDecision.build(
        investigation_id=investigation_id,
        investigation_opened_at=investigation_opened_at,
        run_id=run_id,
        session_id=session_id,
        workspace_revision=workspace_revision,
        authority_revision=authority_revision,
        step_number=step_number,
        baseline_policy_id=baseline_policy.policy_id,
        baseline_policy_sha256=baseline_policy.policy_sha256,
        memory_policy_id=memory_policy.policy_id,
        memory_policy_sha256=memory_policy.policy_sha256,
        activation_protocol_id=protocol.protocol_id,
        activation_protocol_sha256=protocol.protocol_sha256,
        activation_state=activation_state,
        activation_decision_id=activation_id,
        activation_decision_sha256=activation_sha256,
        production_policy_kind=production_policy_kind,
        baseline_decision=baseline_decision,
        memory_decision=memory_decision,
        production_decision=production_decision,
        available_tool_ids=available_tool_ids,
        eligible_tool_ids=eligible_tool_ids,
        completed_tool_ids=completed_tool_ids,
        available_artifact_ids=available_artifact_ids,
        qualified_available_artifact_ids=qualified_available_artifact_ids,
        qualified_available_artifact_evidence_states=(
            qualified_available_artifact_evidence_states
        ),
        qualified_available_artifact_provenance_sha256s=(
            qualified_available_artifact_provenance_sha256s
        ),
        current_evidence_pinned_tool_ids=current_evidence_pinned_tool_ids,
        current_truth_sha256=current_truth_sha256,
        p19_snapshot_sha256=p19_snapshot_sha256,
        p20_projection_sha256=p20_projection_sha256,
        p26_projection_sha256=p26_projection_sha256,
        p32_projection_sha256=p32_projection_sha256,
        current_p19_cause_ids=current_p19_cause_ids,
        current_p19_cause_states=current_p19_cause_states,
        current_contradiction_ids=current_contradiction_ids,
        strongest_contradiction_id=strongest_contradiction_id,
        current_objective=current_objective,
        p33_projection_sha256=p33_projection_sha256,
        p33_history_revision=p33_history_revision,
        p33_ledger_head_sha256=p33_ledger_head_sha256,
        p33_context_sha256=p33_context_sha256,
        p33_problem_sha256=p33_problem_sha256,
        track=track,
        track_configuration=track_configuration,
        package_type=package_type,
        iracing_build=iracing_build,
        problem_family=problem_family,
        problem_orientation=problem_orientation,
        track_class=track_class,
        phase=phase,
        context_subgroup_keys=canonical_context_subgroups(
            context_transfer_class=context_transfer_class,
            problem_orientation=problem_orientation,
            problem_family=problem_family,
            objective=current_objective,
            track_class=track_class,
            driver_drift_state=driver_drift_state,
            build_review_state=build_review_state,
        ),
        build_review_state=build_review_state,
        driver_drift_state=driver_drift_state,
        memory_records_consulted=memory_decision.source_memory_record_ids,
        context_transfer_class=context_transfer_class,
        negative_control_condition=negative_control_condition,
        negative_control_evidence=negative_control_evidence,
        future_memory_record_ids=future_memory_record_ids,
        decision_frozen_at=decision_frozen_at,
    )


def build_investigation_outcome_certificate(
    pair: PairedInvestigationDecision,
    **values: object,
) -> InvestigationOutcomeCertificate:
    values = dict(values)
    values.setdefault("investigation_id", pair.investigation_id)
    values.setdefault("investigation_opened_at", pair.investigation_opened_at)
    values.setdefault("decision_frozen_at", pair.decision_frozen_at)
    values.setdefault("pair_id", pair.pair_id)
    values.setdefault("pair_sha256", pair.pair_sha256)
    values.setdefault("activation_protocol_id", pair.activation_protocol_id)
    values.setdefault(
        "activation_protocol_sha256", pair.activation_protocol_sha256
    )
    certificate = InvestigationOutcomeCertificate.build(**values)
    if certificate.investigation_id != pair.investigation_id:
        raise ValueError("P34 outcome certificate must match its paired investigation")
    if (
        certificate.activation_protocol_id != pair.activation_protocol_id
        or certificate.activation_protocol_sha256
        != pair.activation_protocol_sha256
    ):
        raise ValueError("P34 outcome must bind the pair's exact protocol")
    if certificate.investigation_opened_at != pair.investigation_opened_at:
        raise ValueError("P34 outcome must bind the immutable investigation opening")
    protocol = p34_activation_protocol()
    if certificate.prospective != (
        pair.investigation_opened_at > protocol.prospective_boundary
    ):
        raise ValueError("P34 prospective status must derive from investigation opening")
    if certificate.certified_at <= pair.decision_frozen_at:
        raise ValueError("P34 outcome certificate must follow the frozen decision")
    return certificate


def build_investigation_outcome_followup(
    certificate: InvestigationOutcomeCertificate,
    *,
    observed_p19_snapshot_sha256: str,
    observed_p19_outcome: Literal["keep", "undo", "retest", "no_call", "blocked"],
    source_workflow_id: str | None,
    source_workflow_revision_sha256: str | None,
    source_event_ids: tuple[str, ...],
    source_artifact_ids: tuple[str, ...],
    observed_at: datetime,
) -> InvestigationOutcomeFollowup:
    followup = InvestigationOutcomeFollowup.build(
        activation_protocol_id=certificate.activation_protocol_id,
        activation_protocol_sha256=certificate.activation_protocol_sha256,
        investigation_id=certificate.investigation_id,
        certificate_id=certificate.certificate_id,
        certificate_sha256=certificate.certificate_sha256,
        observed_p19_snapshot_sha256=observed_p19_snapshot_sha256,
        observed_p19_outcome=observed_p19_outcome,
        source_workflow_id=source_workflow_id,
        source_workflow_revision_sha256=source_workflow_revision_sha256,
        source_event_ids=source_event_ids,
        source_artifact_ids=source_artifact_ids,
        observed_at=observed_at,
    )
    if followup.observed_at <= certificate.certified_at:
        raise ValueError("P34 follow-up must occur after terminal certification")
    if source_workflow_id is not None and source_workflow_id not in (
        certificate.created_workflow_ids
    ):
        raise ValueError("P34 follow-up workflow was not created by this investigation")
    return followup


def capture_p34_controlled_workflow_followup(
    repository: InvestigationAdaptationRepository,
    *,
    workflow: object,
) -> InvestigationOutcomeFollowup | None:
    """Idempotently attach one authoritative scored workflow to its P34 outcome."""

    from racelab_engine.analysis.test_director import score_test_execution
    from racelab_engine.models.controlled_workflow import ControlledWorkflow
    from racelab_engine.services.controlled_workflow_service import (
        validate_p19_workflow_origin,
    )
    from racelab_engine.storage.repository import RaceLabRepository

    candidate = ControlledWorkflow.model_validate(workflow)
    source_repository = RaceLabRepository(repository.db_path)
    persisted = source_repository.get_controlled_workflow(candidate.workflow_id)
    if persisted is None or canonical_json_sha256(
        persisted.model_dump(mode="json")
    ) != canonical_json_sha256(candidate.model_dump(mode="json")):
        raise ValueError("P34 follow-up requires the exact persisted workflow")
    if (
        candidate.status != "scored"
        or candidate.execution is None
        or candidate.quality is None
        or not candidate.quality.protocol_valid
        or candidate.quality.verdict not in {"keep", "undo", "retest"}
        or score_test_execution(candidate.execution) != candidate.quality
    ):
        raise ValueError("P34 follow-up requires a qualified scored workflow")
    binding = validate_p19_workflow_origin(candidate, repository=source_repository)
    reasoning_sha256 = binding.get("reasoning_snapshot_sha256")
    source_event_ids = binding.get("source_event_ids")
    if (
        not isinstance(reasoning_sha256, str)
        or len(reasoning_sha256) != 64
        or not isinstance(source_event_ids, list)
        or any(not isinstance(item, str) or not item for item in source_event_ids)
    ):
        raise ValueError("P34 scored workflow lacks exact P19/event lineage")
    protocol_id = p34_activation_protocol().protocol_id
    certificate = repository.get_outcome_certificate_for_workflow(
        protocol_id=protocol_id,
        workflow_id=candidate.workflow_id,
    )
    if certificate is None:
        return None
    workflow_revision = canonical_json_sha256(candidate.model_dump(mode="json"))
    followup = build_investigation_outcome_followup(
        certificate,
        observed_p19_snapshot_sha256=reasoning_sha256,
        observed_p19_outcome=candidate.quality.verdict,
        source_workflow_id=candidate.workflow_id,
        source_workflow_revision_sha256=workflow_revision,
        source_event_ids=tuple(source_event_ids),
        source_artifact_ids=(),
        observed_at=candidate.updated_at,
    )
    existing = repository.query_records(
        record_kinds=("outcome_followup",),
        investigation_id=certificate.investigation_id,
        protocol_id=protocol_id,
        limit=2,
    )
    if existing.blockers:
        raise InvestigationAdaptationIntegrityError(existing.blockers[0])
    if existing.records:
        if len(existing.records) == 1 and existing.records[0] == followup:
            return followup
        raise InvestigationAdaptationIntegrityError(
            "P34 workflow follow-up conflicts with its exact certificate"
        )
    repository.append_outcome_followup(followup)
    return followup


def pending_p34_scored_workflow_ids(
    repository: InvestigationAdaptationRepository,
    *,
    limit: int = 512,
) -> tuple[str, ...]:
    """Return bounded exact workflow IDs whose P34 follow-up is still absent."""

    certificates = repository.query_pending_outcome_certificates(
        protocol_id=p34_activation_protocol().protocol_id,
        limit=limit,
    )
    workflow_ids = tuple(
        workflow_id
        for certificate in certificates
        for workflow_id in certificate.created_workflow_ids
    )
    if len(workflow_ids) != len(set(workflow_ids)):
        raise InvestigationAdaptationIntegrityError(
            "P34 pending workflow identity is ambiguously bound"
        )
    return workflow_ids


def build_discriminator_outcome(
    *,
    activation_protocol_id: str,
    activation_protocol_sha256: str,
    investigation_id: str,
    prediction_pair_id: str,
    prediction_pair_sha256: str,
    source_pair_id: str,
    source_pair_sha256: str,
    source_authority_revision: str,
    workspace_revision: str,
    tool_id: str,
    request_event_id: str,
    request_sequence: int,
    request_recorded_at: datetime,
    result_event_id: str,
    result_sequence: int,
    result_recorded_at: datetime,
    transition_sequence: int,
    lineage_event_ids: tuple[str, ...],
    artifact_ids: tuple[str, ...],
    qualified_evidence_states: tuple[
        Literal[
            "measured",
            "calculated",
            "estimated_proxy",
            "observed_correlation",
            "controlled_test_effect",
        ],
        ...,
    ],
    before_p19_snapshot_sha256: str,
    after_p19_snapshot_sha256: str,
    relevant_ambiguity_ids: tuple[str, ...],
    cause_changes: tuple[P19CauseChange, ...],
    resolved_blocker_ids: tuple[str, ...],
    artifact_available_before_transition: bool,
    exact_workspace_match: bool,
    evaluated_at: datetime,
) -> DiscriminatorOutcome:
    relevant_change = bool(
        set(item.cause_id for item in cause_changes).intersection(
            relevant_ambiguity_ids
        )
    ) or bool(resolved_blocker_ids)
    ordered = request_sequence < result_sequence <= transition_sequence
    earned = (
        bool(artifact_ids)
        and all(
            state in {"measured", "calculated", "controlled_test_effect"}
            for state in qualified_evidence_states
        )
        and ordered
        and before_p19_snapshot_sha256 != after_p19_snapshot_sha256
        and artifact_available_before_transition
        and exact_workspace_match
        and relevant_change
    )
    return DiscriminatorOutcome.build(
        activation_protocol_id=activation_protocol_id,
        activation_protocol_sha256=activation_protocol_sha256,
        investigation_id=investigation_id,
        prediction_pair_id=prediction_pair_id,
        prediction_pair_sha256=prediction_pair_sha256,
        source_pair_id=source_pair_id,
        source_pair_sha256=source_pair_sha256,
        source_authority_revision=source_authority_revision,
        workspace_revision=workspace_revision,
        tool_id=tool_id,
        request_event_id=request_event_id,
        request_sequence=request_sequence,
        request_recorded_at=request_recorded_at,
        result_event_id=result_event_id,
        result_sequence=result_sequence,
        result_recorded_at=result_recorded_at,
        transition_sequence=transition_sequence,
        lineage_event_ids=lineage_event_ids,
        artifact_ids=artifact_ids,
        qualified_evidence_states=qualified_evidence_states,
        before_p19_snapshot_sha256=before_p19_snapshot_sha256,
        after_p19_snapshot_sha256=after_p19_snapshot_sha256,
        relevant_ambiguity_ids=relevant_ambiguity_ids,
        cause_changes=cause_changes,
        resolved_blocker_ids=resolved_blocker_ids,
        blocker_resolved=bool(resolved_blocker_ids),
        artifact_available_before_transition=artifact_available_before_transition,
        exact_workspace_match=exact_workspace_match,
        causally_relevant_transition=relevant_change,
        credit_state="earned" if earned else "rejected",
        credit_reason=(
            "Ordered qualified evidence reduced the frozen ambiguity."
            if earned
            else "The ordered qualified-evidence contract was not fully met."
        ),
        evaluated_at=evaluated_at,
    )


def _exact_p19_cause_changes(
    pair: PairedInvestigationDecision,
    certificate: InvestigationOutcomeCertificate,
) -> tuple[P19CauseChange, ...]:
    before = {item.cause_id: item.state for item in pair.current_p19_cause_states}
    after = {item.cause_id: item.state for item in certificate.final_p19_cause_states}
    ordered_ids = tuple(
        dict.fromkeys(
            (
                *(item.cause_id for item in pair.current_p19_cause_states),
                *(item.cause_id for item in certificate.final_p19_cause_states),
            )
        )
    )
    return tuple(
        P19CauseChange(
            cause_id=cause_id,
            before_state=before.get(cause_id, "absent"),
            after_state=after.get(cause_id, "absent"),
        )
        for cause_id in ordered_ids
        if before.get(cause_id, "absent") != after.get(cause_id, "absent")
    )


def build_discriminator_outcome_from_crew_events(
    *,
    prediction_pair: PairedInvestigationDecision,
    source_pair: PairedInvestigationDecision,
    certificate: InvestigationOutcomeCertificate,
    request_event: object,
    result_event: object,
    investigation_events: tuple[object, ...],
    transition_sequence: int,
    evaluated_at: datetime,
) -> DiscriminatorOutcome:
    """Derive one bounded A->B shadow observation from exact Crew lineage.

    ``prediction_pair`` is the preregistered pair that proposed B before A ran.
    ``source_pair`` is the later pair frozen immediately before Crew actually
    requested B.  Keeping both identities prevents the later observation from
    being rewritten as though it happened in the earlier workspace.
    """

    from racelab_engine.models.crew_chief import CrewChiefEvent
    from racelab_engine.storage.crew_chief_repository import crew_chief_event_hash

    request = CrewChiefEvent.model_validate(request_event)
    result = CrewChiefEvent.model_validate(result_event)
    events = tuple(
        sorted(
            (CrewChiefEvent.model_validate(item) for item in investigation_events),
            key=lambda item: item.sequence,
        )
    )
    prefix = tuple(item for item in events if item.sequence <= transition_sequence)
    if (
        not prefix
        or tuple(item.sequence for item in prefix)
        != tuple(range(1, transition_sequence + 1))
        or any(crew_chief_event_hash(item) != item.event_hash for item in prefix)
    ):
        raise ValueError("P34 discriminator requires the complete valid Crew prefix")
    by_id = {item.event_id: item for item in prefix}
    prediction_event = next(
        (
            item
            for item in prefix
            if item.sequence == prediction_pair.step_number + 1
        ),
        None,
    )
    prediction_source_snapshot_sha256 = (
        investigation_adaptation_source_snapshot_sha256(
            run_id=prediction_pair.run_id,
            session_id=prediction_pair.session_id,
            workspace_revision=prediction_pair.workspace_revision,
            authority_revision=prediction_pair.authority_revision,
            current_truth_sha256=prediction_pair.current_truth_sha256,
            p19_snapshot_sha256=prediction_pair.p19_snapshot_sha256,
            p20_projection_sha256=prediction_pair.p20_projection_sha256,
            p26_projection_sha256=prediction_pair.p26_projection_sha256,
            p32_projection_sha256=prediction_pair.p32_projection_sha256,
        )
    )
    source_snapshot_sha256 = investigation_adaptation_source_snapshot_sha256(
        run_id=source_pair.run_id,
        session_id=source_pair.session_id,
        workspace_revision=source_pair.workspace_revision,
        authority_revision=source_pair.authority_revision,
        current_truth_sha256=source_pair.current_truth_sha256,
        p19_snapshot_sha256=source_pair.p19_snapshot_sha256,
        p20_projection_sha256=source_pair.p20_projection_sha256,
        p26_projection_sha256=source_pair.p26_projection_sha256,
        p32_projection_sha256=source_pair.p32_projection_sha256,
    )
    if (
        by_id.get(request.event_id) != request
        or by_id.get(result.event_id) != result
        or prediction_event is None
        or prediction_event.payload.adaptation_prediction_pair_id
        != prediction_pair.pair_id
        or prediction_event.payload.adaptation_prediction_pair_sha256
        != prediction_pair.pair_sha256
        or prediction_event.payload.adaptation_prediction_source_snapshot_sha256
        != prediction_source_snapshot_sha256
        or prediction_pair.investigation_id != source_pair.investigation_id
        or request.investigation_id != prediction_pair.investigation_id
        or result.investigation_id != prediction_pair.investigation_id
        or certificate.investigation_id != prediction_pair.investigation_id
        or certificate.pair_id != prediction_pair.pair_id
        or certificate.pair_sha256 != prediction_pair.pair_sha256
        or request.event_type != "tool_invoked"
        or result.event_type != "tool_result_attached"
        or request.payload.tool_id is None
        or result.payload.tool_id != request.payload.tool_id
        or request.event_id not in certificate.tool_request_event_ids
        or result.event_id not in certificate.tool_result_event_ids
        or request.workspace_revision != source_pair.workspace_revision
        or result.workspace_revision != source_pair.workspace_revision
        or request.payload.adaptation_prediction_pair_id != source_pair.pair_id
        or request.payload.adaptation_prediction_pair_sha256
        != source_pair.pair_sha256
        or request.payload.adaptation_prediction_source_snapshot_sha256
        != source_snapshot_sha256
        or request.sequence != source_pair.step_number + 1
        or result.sequence <= request.sequence
        or result.sequence > transition_sequence
        or source_pair.decision_frozen_at >= request.created_at
        or prediction_pair.decision_frozen_at >= source_pair.decision_frozen_at
        or source_pair.baseline_decision.decision_kind != "inspect_tool"
        or source_pair.baseline_decision.action_id != request.payload.tool_id
        or prediction_pair.memory_decision.decision_kind != "inspect_tool"
        or prediction_pair.memory_decision.action_id != request.payload.tool_id
    ):
        raise ValueError("P34 discriminator requires exact ordered Crew event lineage")
    exact_transfer_dimensions = (
        prediction_pair.run_id == source_pair.run_id
        and prediction_pair.session_id == source_pair.session_id
        and prediction_pair.activation_protocol_id
        == source_pair.activation_protocol_id
        and prediction_pair.activation_protocol_sha256
        == source_pair.activation_protocol_sha256
        and prediction_pair.authority_revision == source_pair.authority_revision
        and prediction_pair.p19_snapshot_sha256
        == source_pair.p19_snapshot_sha256
        and prediction_pair.p20_projection_sha256
        == source_pair.p20_projection_sha256
        and prediction_pair.p26_projection_sha256
        == source_pair.p26_projection_sha256
        and prediction_pair.p32_projection_sha256
        == source_pair.p32_projection_sha256
        and prediction_pair.p33_context_sha256 == source_pair.p33_context_sha256
        and prediction_pair.p33_problem_sha256 == source_pair.p33_problem_sha256
        and prediction_pair.track == source_pair.track
        and prediction_pair.track_configuration == source_pair.track_configuration
        and prediction_pair.package_type == source_pair.package_type
        and prediction_pair.iracing_build == source_pair.iracing_build
        and prediction_pair.current_objective == source_pair.current_objective
        and prediction_pair.problem_family == source_pair.problem_family
        and prediction_pair.problem_orientation == source_pair.problem_orientation
        and prediction_pair.phase == source_pair.phase
    )
    comparison_events = tuple(
        item
        for item in prefix
        if prediction_pair.step_number < item.sequence <= transition_sequence
    )
    no_rebase = not any(item.event_type == "workspace_rebased" for item in prefix)
    evidence_by_artifact = dict(
        zip(
            certificate.qualified_artifact_ids,
            certificate.qualified_artifact_evidence_states,
            strict=True,
        )
    )
    artifact_ids = tuple(
        artifact_id
        for artifact_id in result.payload.artifact_ids
        if artifact_id in evidence_by_artifact
    )
    all_cause_changes = _exact_p19_cause_changes(source_pair, certificate)
    initial_ambiguities = set(prediction_pair.current_p19_cause_ids)
    cause_changes = tuple(
        item for item in all_cause_changes if item.cause_id in initial_ambiguities
    )
    useful_tool_is_corroborated = (
        certificate.useful_discriminator_id == request.payload.tool_id
    )
    relevant_ambiguity_ids = (
        tuple(item.cause_id for item in cause_changes)
        if useful_tool_is_corroborated
        else ()
    )
    return build_discriminator_outcome(
        activation_protocol_id=prediction_pair.activation_protocol_id,
        activation_protocol_sha256=prediction_pair.activation_protocol_sha256,
        investigation_id=prediction_pair.investigation_id,
        prediction_pair_id=prediction_pair.pair_id,
        prediction_pair_sha256=prediction_pair.pair_sha256,
        source_pair_id=source_pair.pair_id,
        source_pair_sha256=source_pair.pair_sha256,
        source_authority_revision=source_pair.authority_revision,
        workspace_revision=source_pair.workspace_revision,
        tool_id=request.payload.tool_id,
        request_event_id=request.event_id,
        request_sequence=request.sequence,
        request_recorded_at=request.created_at,
        result_event_id=result.event_id,
        result_sequence=result.sequence,
        result_recorded_at=result.created_at,
        transition_sequence=transition_sequence,
        lineage_event_ids=tuple(item.event_id for item in comparison_events),
        artifact_ids=artifact_ids,
        qualified_evidence_states=tuple(
            evidence_by_artifact[item] for item in artifact_ids
        ),
        before_p19_snapshot_sha256=source_pair.p19_snapshot_sha256,
        after_p19_snapshot_sha256=certificate.final_p19_snapshot_sha256,
        relevant_ambiguity_ids=relevant_ambiguity_ids,
        cause_changes=cause_changes,
        resolved_blocker_ids=(),
        artifact_available_before_transition=result.sequence <= transition_sequence,
        exact_workspace_match=exact_transfer_dimensions and no_rebase,
        evaluated_at=evaluated_at,
    )


def build_p34_negative_control_result(
    pair: PairedInvestigationDecision,
    *,
    control_id: Literal[
        "no_relevant_history",
        "incompatible_history",
        "corrupt_history",
        "generic_component_knowledge_only",
        "same_words_different_physical_scope",
        "material_driver_drift",
        "future_memory_record",
    ],
    evaluated_at: datetime,
) -> P34NegativeControlResult:
    """Certify fallback only when the pair carries the exact typed condition."""

    protocol = p34_activation_protocol()
    exact_fallback = (
        pair.negative_control_condition == control_id
        and pair.activation_protocol_id == protocol.protocol_id
        and pair.activation_protocol_sha256 == protocol.protocol_sha256
        and pair.baseline_decision.executable_identity
        == pair.memory_decision.executable_identity
        and not pair.memory_records_consulted
        and evaluated_at > pair.decision_frozen_at
    )
    blockers = () if exact_fallback else (
        "The frozen pair does not prove this exact negative-control condition.",
    )
    return P34NegativeControlResult.build(
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol.protocol_sha256,
        control_id=control_id,
        investigation_id=pair.investigation_id,
        pair_id=pair.pair_id,
        pair_sha256=pair.pair_sha256,
        observed_exact_fallback=exact_fallback,
        passed=exact_fallback,
        source_artifact_ids=(pair.pair_id,),
        blockers=blockers,
        evaluated_at=evaluated_at,
    )


def _derived_negative_transfer_kinds(
    comparison: PairedInvestigationComparison,
) -> tuple[str, ...]:
    kinds: list[str] = []
    if comparison.memory_path_metrics_observed:
        if int(comparison.memory_tool_steps) > comparison.baseline_tool_steps:
            kinds.append("extra_tool_steps")
        if (
            comparison.memory_consumption_metrics_observed
            and int(comparison.memory_laps) > int(comparison.baseline_laps)
        ):
            kinds.append("extra_laps")
        if int(comparison.memory_questions) > comparison.baseline_questions:
            kinds.append("extra_driver_questions")
        if (
            comparison.memory_unresolved_or_abandoned
            and not comparison.baseline_unresolved_or_abandoned
        ):
            kinds.append("premature_terminal_decision")
    if comparison.incompatible_history_transfers:
        kinds.append("wrong_context_history")
    if comparison.driver_memory_mechanical_diagnoses:
        kinds.append("driver_drift_misapplied")
    if comparison.bounded_dead_end_promoted:
        kinds.append("dead_end_promoted")
    if comparison.hidden_contradiction_failures:
        kinds.append("strongest_contradiction_delayed")
    if (
        comparison.baseline_useful_discriminator_step is not None
        and comparison.memory_useful_discriminator_step is not None
        and comparison.memory_useful_discriminator_step
        > comparison.baseline_useful_discriminator_step
    ):
        kinds.append("useful_current_evidence_delayed")
    return tuple(dict.fromkeys(kinds))


def build_investigation_negative_transfer(
    comparison: PairedInvestigationComparison,
    *,
    detected_at: datetime,
) -> InvestigationNegativeTransfer | None:
    """Derive attributable harm from one exact immutable comparison."""

    kinds = _derived_negative_transfer_kinds(comparison)
    if not kinds:
        return None
    memory_steps = comparison.memory_tool_steps
    degradation = (
        max(
            0.0,
            (memory_steps - comparison.baseline_tool_steps)
            / max(comparison.baseline_tool_steps, 1)
            * 100,
        )
        if memory_steps is not None
        else 0.0
    )
    return InvestigationNegativeTransfer.build(
        activation_protocol_id=comparison.activation_protocol_id,
        activation_protocol_sha256=comparison.activation_protocol_sha256,
        investigation_id=comparison.investigation_id,
        pair_id=comparison.pair_id,
        comparison_id=comparison.comparison_id,
        comparison_sha256=comparison.comparison_sha256,
        kinds=kinds,
        baseline_tool_steps=comparison.baseline_tool_steps,
        memory_tool_steps=memory_steps,
        baseline_useful_discriminator_step=(
            comparison.baseline_useful_discriminator_step
        ),
        memory_useful_discriminator_step=(
            comparison.memory_useful_discriminator_step
        ),
        consumption_metrics_observed=(
            comparison.baseline_consumption_metrics_observed
            and comparison.memory_consumption_metrics_observed
        ),
        baseline_laps=comparison.baseline_laps,
        memory_laps=comparison.memory_laps,
        baseline_questions=comparison.baseline_questions,
        memory_questions=comparison.memory_questions,
        material_efficiency_degradation_pct=degradation,
        evidence_artifact_ids=(comparison.comparison_id,),
        detected_at=detected_at,
    )


def capture_p34_negative_transfer(
    repository: InvestigationAdaptationRepository,
    comparison: PairedInvestigationComparison,
    *,
    detected_at: datetime,
    connection: object | None = None,
) -> InvestigationNegativeTransfer | None:
    """Append exact derived harm idempotently, optionally in Crew's transaction."""

    transfer = build_investigation_negative_transfer(
        comparison,
        detected_at=detected_at,
    )
    if transfer is None:
        return None
    if connection is None:
        repository.append_negative_transfer(transfer)
    else:
        repository.append_negative_transfer_in_transaction(connection, transfer)
    return transfer


def classify_counterfactual_observability(
    pair: PairedInvestigationDecision,
    certificate: InvestigationOutcomeCertificate,
    *,
    independently_observed_artifact_ids: tuple[str, ...] = (),
) -> Literal[
    "directly_observed",
    "counterfactual_observable",
    "counterfactual_unobservable",
    "invalid",
]:
    if certificate.investigation_id != pair.investigation_id:
        return "invalid"
    if certificate.outcome_validity != "qualified":
        return "invalid"
    if (
        pair.baseline_decision.executable_identity
        == pair.memory_decision.executable_identity
    ):
        return "directly_observed"
    if pair.memory_decision.decision_kind == "inspect_tool" and (
        pair.memory_decision.action_id in certificate.tool_results_received
    ):
        return "counterfactual_observable"
    return "counterfactual_unobservable"


def build_paired_investigation_comparison(
    *,
    investigation_pairs: tuple[PairedInvestigationDecision, ...],
    certificate: InvestigationOutcomeCertificate,
    discriminator_outcome: DiscriminatorOutcome | None = None,
    outcome_followup: InvestigationOutcomeFollowup | None = None,
    counterfactual_source_certificate: InvestigationOutcomeCertificate | None = None,
    independently_observed_artifact_ids: tuple[str, ...] = (),
    recurrence_match_correct: bool | None = None,
    compared_at: datetime,
) -> PairedInvestigationComparison:
    """Build one comparison only from exact immutable parent lineage."""

    protocol = p34_activation_protocol()
    pair = canonical_investigation_evaluation_pair(investigation_pairs)
    pair_by_id = {item.pair_id: item for item in investigation_pairs}
    source_pair = (
        pair_by_id.get(discriminator_outcome.source_pair_id)
        if discriminator_outcome is not None
        else None
    )
    blockers: list[str] = []
    if recurrence_match_correct is not None:
        blockers.append(
            "Recurrence correctness has no authoritative outcome contract and is withheld."
        )
    if (
        pair.activation_protocol_id != protocol.protocol_id
        or pair.activation_protocol_sha256 != protocol.protocol_sha256
    ):
        blockers.append("The paired decision belongs to another activation protocol.")
    if (
        certificate.investigation_id != pair.investigation_id
        or certificate.activation_protocol_id != pair.activation_protocol_id
        or certificate.activation_protocol_sha256
        != pair.activation_protocol_sha256
        or certificate.investigation_opened_at != pair.investigation_opened_at
        or certificate.pair_id != pair.pair_id
        or certificate.pair_sha256 != pair.pair_sha256
        or certificate.decision_frozen_at != pair.decision_frozen_at
        or certificate.certified_at <= pair.decision_frozen_at
    ):
        blockers.append("The outcome certificate does not bind the exact frozen pair.")
    if certificate.outcome_validity != "qualified":
        blockers.extend(certificate.blockers or ("The outcome certificate is not qualified.",))
    if certificate.synthetic:
        blockers.append("Synthetic mechanics cases cannot qualify activation evidence.")
    expected_prospective = (
        pair.investigation_opened_at > protocol.prospective_boundary
    )
    if certificate.prospective != expected_prospective:
        blockers.append("Prospective status does not match the immutable opening time.")
    if discriminator_outcome is not None and (
        discriminator_outcome.investigation_id != pair.investigation_id
        or discriminator_outcome.activation_protocol_id
        != pair.activation_protocol_id
        or discriminator_outcome.activation_protocol_sha256
        != pair.activation_protocol_sha256
        or discriminator_outcome.prediction_pair_id != pair.pair_id
        or discriminator_outcome.prediction_pair_sha256 != pair.pair_sha256
        or source_pair is None
        or source_pair.pair_sha256 != discriminator_outcome.source_pair_sha256
        or source_pair.investigation_id != pair.investigation_id
        or source_pair.workspace_revision != discriminator_outcome.workspace_revision
        or source_pair.authority_revision
        != discriminator_outcome.source_authority_revision
        or source_pair.authority_revision != pair.authority_revision
        or source_pair.step_number + 1 != discriminator_outcome.request_sequence
        or source_pair.decision_frozen_at
        > discriminator_outcome.request_recorded_at
        or source_pair.baseline_decision.action_id
        != discriminator_outcome.tool_id
        or pair.memory_decision.action_id != discriminator_outcome.tool_id
        or discriminator_outcome.tool_id not in certificate.tools_actually_requested
        or discriminator_outcome.request_event_id
        not in certificate.tool_request_event_ids
        or certificate.tools_actually_requested[
            certificate.tool_request_event_ids.index(
                discriminator_outcome.request_event_id
            )
        ]
        != discriminator_outcome.tool_id
        or discriminator_outcome.tool_id not in certificate.tool_results_received
        or discriminator_outcome.result_event_id not in certificate.tool_result_event_ids
        or certificate.tool_results_received[
            certificate.tool_result_event_ids.index(discriminator_outcome.result_event_id)
        ]
        != discriminator_outcome.tool_id
        or not set(discriminator_outcome.artifact_ids).issubset(
            certificate.qualified_artifact_ids
        )
        or discriminator_outcome.before_p19_snapshot_sha256
        != source_pair.p19_snapshot_sha256
        or discriminator_outcome.after_p19_snapshot_sha256
        != certificate.final_p19_snapshot_sha256
        or not set(discriminator_outcome.relevant_ambiguity_ids).issubset(
            set(pair.current_p19_cause_ids)
        )
        or discriminator_outcome.cause_changes
        != tuple(
            item
            for item in _exact_p19_cause_changes(source_pair, certificate)
            if item.cause_id in set(pair.current_p19_cause_ids)
        )
        or discriminator_outcome.relevant_ambiguity_ids
        != tuple(
            item.cause_id
            for item in _exact_p19_cause_changes(source_pair, certificate)
            if item.cause_id in set(pair.current_p19_cause_ids)
        )
        or discriminator_outcome.resolved_blocker_ids
        or certificate.useful_discriminator_id != discriminator_outcome.tool_id
    ):
        blockers.append("The discriminator outcome is not exact parent lineage.")
    if outcome_followup is not None and (
        outcome_followup.investigation_id != pair.investigation_id
        or outcome_followup.activation_protocol_id != pair.activation_protocol_id
        or outcome_followup.activation_protocol_sha256
        != pair.activation_protocol_sha256
        or outcome_followup.certificate_id != certificate.certificate_id
        or outcome_followup.certificate_sha256 != certificate.certificate_sha256
        or outcome_followup.observed_at <= certificate.certified_at
    ):
        blockers.append("The later P19 follow-up is not bound to this certificate.")
    observed_ids = tuple(dict.fromkeys(independently_observed_artifact_ids))
    available_evidence = set(pair.available_artifact_ids).union(
        certificate.qualified_artifact_ids
    )
    if observed_ids and not set(observed_ids).issubset(available_evidence):
        blockers.append("The independently observed artifacts are not in frozen lineage.")
    if observed_ids:
        blockers.append(
            "Unbound artifact IDs cannot establish memory-action observability."
        )
    observability = classify_counterfactual_observability(
        pair,
        certificate,
        independently_observed_artifact_ids=observed_ids,
    )
    if blockers and observability != "invalid":
        observability = "invalid"
    baseline_discriminator_step = (
        certificate.tool_results_received.index(certificate.useful_discriminator_id) + 1
        if certificate.useful_discriminator_id in certificate.tool_results_received
        else None
    )
    baseline_consumption_observed = certificate.consumption_metrics_state == "observed"
    baseline_metrics: dict[str, object] = {
        "tool_steps": len(certificate.tool_results_received),
        "elapsed_seconds": float(certificate.elapsed_wall_seconds),
        "questions": len(certificate.driver_question_ids),
        "dead_ends": len(certificate.dead_end_tool_ids),
        "repeated_no_findings": len(certificate.repeated_no_finding_tool_ids),
        "unresolved_or_abandoned": bool(certificate.causes_left_unresolved)
        or certificate.terminal_crew_decision in {"blocked", "stale", "abandoned"},
    }
    memory_path_metrics_observed = False
    memory_consumption_observed = False
    memory_metrics: dict[str, object | None] = {
        key: None for key in baseline_metrics
    }
    baseline_laps = (
        len(certificate.lap_ids_consumed or ())
        if baseline_consumption_observed
        else None
    )
    baseline_measurement_missions = (
        len(certificate.measurement_mission_ids or ())
        if baseline_consumption_observed
        else None
    )
    memory_laps: int | None = None
    memory_measurement_missions: int | None = None
    memory_discriminator_step: int | None = None
    counterfactual_id = None
    counterfactual_sha256 = None
    bounded_reorder_observed = False
    bounded_discriminator_step_advance = 0
    bounded_discriminator_step_delay = 0
    bounded_dead_end_promoted = False
    if observability == "directly_observed":
        memory_path_metrics_observed = True
        memory_metrics = dict(baseline_metrics)
        memory_consumption_observed = baseline_consumption_observed
        memory_laps = baseline_laps
        memory_measurement_missions = baseline_measurement_missions
        memory_discriminator_step = baseline_discriminator_step
    elif observability == "counterfactual_observable":
        if pair.memory_decision.action_id in certificate.tool_results_received:
            memory_discriminator_step = (
                certificate.tool_results_received.index(
                    pair.memory_decision.action_id
                )
                + 1
            )
        baseline_action = pair.baseline_decision.action_id
        memory_action = pair.memory_decision.action_id
        baseline_index = (
            certificate.tool_results_received.index(baseline_action)
            if baseline_action in certificate.tool_results_received
            else -1
        )
        memory_index = (
            certificate.tool_results_received.index(memory_action)
            if memory_action in certificate.tool_results_received
            else -1
        )
        bounded_reorder_observed = bool(
            not blockers
            and discriminator_outcome is not None
            and discriminator_outcome.credit_state == "earned"
            and discriminator_outcome.tool_id == memory_action
            and certificate.useful_discriminator_id == memory_action
            and baseline_index >= 0
            and memory_index == baseline_index + 1
            and pair.memory_decision.selected_ordinal
            == pair.baseline_decision.selected_ordinal
        )
        if bounded_reorder_observed:
            memory_discriminator_step = pair.memory_decision.selected_ordinal
            bounded_discriminator_step_advance = 1
            # A pure inspection swap cannot consume a new lap or measurement
            # mission when the exact qualified discriminator artifacts already
            # existed in the preregistered prediction snapshot.  This is a
            # local structural equality only; downstream path/time metrics stay
            # withheld because production still executed the baseline order.
            preexisting_discriminator = bool(
                discriminator_outcome is not None
                and discriminator_outcome.artifact_ids
                and set(discriminator_outcome.artifact_ids).issubset(
                    pair.qualified_available_artifact_ids
                )
                and pair.baseline_decision.decision_kind == "inspect_tool"
                and pair.memory_decision.decision_kind == "inspect_tool"
                and baseline_consumption_observed
            )
            if preexisting_discriminator:
                memory_consumption_observed = True
                memory_laps = baseline_laps
                memory_measurement_missions = baseline_measurement_missions
        bounded_harm_observed = bool(
            not blockers
            and pair.baseline_decision.decision_kind == "inspect_tool"
            and pair.memory_decision.decision_kind == "inspect_tool"
            and certificate.useful_discriminator_id == baseline_action
            and baseline_index >= 0
            and memory_index == baseline_index + 1
            and memory_action
            in {
                *certificate.dead_end_tool_ids,
                *certificate.repeated_no_finding_tool_ids,
            }
            and pair.memory_decision.selected_ordinal
            == pair.baseline_decision.selected_ordinal
        )
        if bounded_harm_observed:
            bounded_reorder_observed = True
            bounded_discriminator_step_delay = 1
            bounded_dead_end_promoted = True
            memory_discriminator_step = baseline_discriminator_step + 1
        if counterfactual_source_certificate is not None:
            blockers.append(
                "Independent investigations cannot supply this pair's path metrics."
            )
            observability = "invalid"
            memory_discriminator_step = None
    required_checks = set(pair.baseline_decision.mandatory_check_ids)
    completed_checks = set(certificate.completed_mandatory_check_ids)
    mandatory_violations = len(required_checks - completed_checks)
    hidden_contradiction = int(
        pair.strongest_contradiction_id is not None
        and (
            not certificate.strongest_contradiction_handled
            or certificate.strongest_contradiction_id
            != pair.strongest_contradiction_id
        )
    )
    qualified = not blockers and not certificate.synthetic
    return PairedInvestigationComparison.build(
        investigation_id=pair.investigation_id,
        pair_id=pair.pair_id,
        pair_sha256=pair.pair_sha256,
        activation_protocol_id=protocol.protocol_id,
        activation_protocol_sha256=protocol.protocol_sha256,
        certificate_id=certificate.certificate_id,
        certificate_sha256=certificate.certificate_sha256,
        discriminator_outcome_id=(
            discriminator_outcome.outcome_id
            if discriminator_outcome is not None
            else None
        ),
        discriminator_outcome_sha256=(
            discriminator_outcome.outcome_sha256
            if discriminator_outcome is not None
            else None
        ),
        outcome_followup_id=(
            outcome_followup.followup_id if outcome_followup is not None else None
        ),
        outcome_followup_sha256=(
            outcome_followup.followup_sha256
            if outcome_followup is not None
            else None
        ),
        counterfactual_source_certificate_id=counterfactual_id,
        counterfactual_source_certificate_sha256=counterfactual_sha256,
        independently_observed_artifact_ids=observed_ids,
        decision_frozen_at=pair.decision_frozen_at,
        observability=observability,
        context_identity_sha256=pair.p33_context_sha256,
        problem_family=pair.problem_family,
        objective=pair.current_objective,
        context_transfer_class=pair.context_transfer_class,
        subgroup_keys=pair.context_subgroup_keys,
        baseline_tool_steps=int(baseline_metrics["tool_steps"]),
        memory_path_metrics_observed=memory_path_metrics_observed,
        bounded_reorder_observed=bounded_reorder_observed,
        bounded_discriminator_step_advance=(
            bounded_discriminator_step_advance
        ),
        bounded_discriminator_step_delay=bounded_discriminator_step_delay,
        bounded_dead_end_promoted=bounded_dead_end_promoted,
        memory_tool_steps=memory_metrics["tool_steps"],
        baseline_elapsed_seconds=float(baseline_metrics["elapsed_seconds"]),
        memory_elapsed_seconds=memory_metrics["elapsed_seconds"],
        baseline_consumption_metrics_observed=baseline_consumption_observed,
        memory_consumption_metrics_observed=memory_consumption_observed,
        baseline_laps=baseline_laps,
        memory_laps=memory_laps,
        baseline_questions=int(baseline_metrics["questions"]),
        memory_questions=memory_metrics["questions"],
        baseline_dead_ends=int(baseline_metrics["dead_ends"]),
        memory_dead_ends=memory_metrics["dead_ends"],
        baseline_measurement_missions=baseline_measurement_missions,
        memory_measurement_missions=memory_measurement_missions,
        baseline_repeated_no_findings=int(
            baseline_metrics["repeated_no_findings"]
        ),
        memory_repeated_no_findings=memory_metrics["repeated_no_findings"],
        baseline_useful_discriminator_step=baseline_discriminator_step,
        memory_useful_discriminator_step=memory_discriminator_step,
        baseline_unresolved_or_abandoned=bool(
            baseline_metrics["unresolved_or_abandoned"]
        ),
        memory_unresolved_or_abandoned=memory_metrics[
            "unresolved_or_abandoned"
        ],
        useful_discriminator_hit=(
            certificate.useful_discriminator_id is not None
            and certificate.useful_discriminator_id
            in certificate.tool_results_received
            and (
                discriminator_outcome is None
                or discriminator_outcome.credit_state == "earned"
            )
        ),
        strongest_contradiction_handled=certificate.strongest_contradiction_handled,
        recurrence_match_correct=recurrence_match_correct,
        context_transfer_correct=(
            recurrence_match_correct
            if observability in {"directly_observed", "counterfactual_observable"}
            else None
        ),
        driver_car_separation_correct=(
            True
            if discriminator_outcome is not None
            and discriminator_outcome.credit_state == "earned"
            and discriminator_outcome.tool_id == "inspect_driver_vehicle_separation"
            else None
        ),
        eventual_p19_resolution=(
            outcome_followup.observed_p19_outcome
            in {"keep", "undo", "retest", "no_call"}
            if outcome_followup is not None
            else None
        ),
        no_call_stable=(
            outcome_followup.observed_p19_outcome == "no_call"
            if outcome_followup is not None
            and certificate.terminal_crew_decision == "no_call"
            else None
        ),
        authority_violations=0,
        p19_action_mismatches=0,
        stale_workspace_actions=0,
        mandatory_check_violations=mandatory_violations,
        hidden_contradiction_failures=hidden_contradiction,
        incompatible_history_transfers=int(
            pair.context_transfer_class == "blocked"
            and bool(pair.memory_records_consulted)
        ),
        driver_memory_mechanical_diagnoses=0,
        memory_only_terminal_actions=0,
        prospective=certificate.prospective,
        synthetic=certificate.synthetic,
        qualified=qualified,
        blockers=tuple(dict.fromkeys(blockers)),
        compared_at=compared_at,
    )


def append_paired_investigation_comparison(
    repository: InvestigationAdaptationRepository,
    **values: object,
) -> PairedInvestigationComparison:
    comparison = build_paired_investigation_comparison(**values)
    repository.append_comparison(comparison)
    return comparison


def append_p34_terminal_capture_unit_in_transaction(
    repository: InvestigationAdaptationRepository,
    connection: object,
    *,
    investigation_pairs: tuple[PairedInvestigationDecision, ...],
    certificate: InvestigationOutcomeCertificate,
    comparison: PairedInvestigationComparison,
    discriminator_outcome: DiscriminatorOutcome | None = None,
) -> tuple[
    InvestigationNegativeTransfer | None,
    P34NegativeControlResult | None,
]:
    """Append a complete terminal P34 unit; derived harm cannot be omitted."""

    expected = build_paired_investigation_comparison(
        investigation_pairs=investigation_pairs,
        certificate=certificate,
        discriminator_outcome=discriminator_outcome,
        compared_at=comparison.compared_at,
    )
    if expected != comparison:
        raise InvestigationAdaptationIntegrityError(
            "P34 terminal comparison is not the canonical derived body"
        )
    if discriminator_outcome is not None:
        repository.append_discriminator_outcome_in_transaction(
            connection,
            discriminator_outcome,
        )
    repository.append_outcome_in_transaction(connection, certificate)
    repository.append_comparison_in_transaction(connection, comparison)
    transfer = capture_p34_negative_transfer(
        repository,
        comparison,
        detected_at=comparison.compared_at,
        connection=connection,
    )
    pair = canonical_investigation_evaluation_pair(investigation_pairs)
    control = (
        build_p34_negative_control_result(
            pair,
            control_id=pair.negative_control_condition,
            evaluated_at=comparison.compared_at,
        )
        if pair.negative_control_condition is not None
        else None
    )
    if control is not None:
        repository.append_negative_control_result_in_transaction(connection, control)
    return transfer, control


def _median(values: Iterable[float]) -> float:
    materialized = tuple(values)
    return float(median(materialized)) if materialized else 0.0


def _rate(values: Iterable[bool]) -> float:
    materialized = tuple(values)
    return (
        sum(1 for value in materialized if value) / len(materialized)
        if materialized
        else 0.0
    )


def evaluate_investigation_policies(
    *,
    protocol: P34InvestigationActivationProtocol,
    comparisons: Iterable[PairedInvestigationComparison],
    pairs: Iterable[PairedInvestigationDecision],
    certificates: Iterable[InvestigationOutcomeCertificate],
    policy_records: Iterable[InvestigationPolicy],
    protocol_records: Iterable[P34InvestigationActivationProtocol],
    discriminator_outcomes: Iterable[DiscriminatorOutcome] = (),
    outcome_followups: Iterable[InvestigationOutcomeFollowup] = (),
    negative_transfers: Iterable[InvestigationNegativeTransfer] = (),
    negative_control_results: Iterable[P34NegativeControlResult] = (),
    activation_decisions: Iterable[P34ActivationDecision] = (),
    policy_evaluations: Iterable[InvestigationPolicyEvaluation] = (),
    authoritative_case_ids: frozenset[str] = frozenset(),
    authoritative_discriminator_ids: frozenset[str] = frozenset(),
    authoritative_followup_ids: frozenset[str] = frozenset(),
    canonical_activation_evaluation_ids: frozenset[str] = frozenset(),
    capacity_overflow_kinds: tuple[str, ...] = (),
    registry_identity_sha256: str,
    ledger_record_count: int,
    ledger_head_sha256: str | None,
    evaluated_at: datetime,
) -> InvestigationPolicyEvaluation:
    canonical_protocol = p34_activation_protocol()
    if (
        protocol.protocol_id != canonical_protocol.protocol_id
        or protocol.protocol_sha256 != canonical_protocol.protocol_sha256
    ):
        raise ValueError("P34 evaluation requires the frozen activation protocol")
    policies_by_id = {item.policy_id: item for item in policy_records}
    protocols_by_id = {item.protocol_id: item for item in protocol_records}
    canonical_baseline = baseline_investigation_policy()
    canonical_shadow = memory_shadow_investigation_policy()
    canonical_limited = limited_attention_investigation_policy()
    foundation_verified = (
        protocols_by_id.get(protocol.protocol_id) == protocol
        and policies_by_id.get(canonical_baseline.policy_id) == canonical_baseline
        and policies_by_id.get(canonical_shadow.policy_id) == canonical_shadow
        and policies_by_id.get(canonical_limited.policy_id) == canonical_limited
    )
    pair_by_id = {item.pair_id: item for item in pairs}
    pairs_by_investigation: dict[str, list[PairedInvestigationDecision]] = {}
    for parent_pair in pair_by_id.values():
        pairs_by_investigation.setdefault(parent_pair.investigation_id, []).append(
            parent_pair
        )
    certificate_by_id = {item.certificate_id: item for item in certificates}
    discriminator_by_id = {
        item.outcome_id: item for item in discriminator_outcomes
    }
    followup_by_id = {item.followup_id: item for item in outcome_followups}
    activation_by_id = {
        item.decision_id: item for item in activation_decisions
    }
    evaluation_by_id = {
        item.evaluation_id: item for item in policy_evaluations
    }
    followups_by_certificate: dict[str, list[InvestigationOutcomeFollowup]] = {}
    for item in outcome_followups:
        if item.followup_id in authoritative_followup_ids:
            followups_by_certificate.setdefault(item.certificate_id, []).append(item)
    by_investigation: dict[str, PairedInvestigationComparison] = {}
    duplicate_conflicts: list[str] = []
    parent_failures: list[str] = []
    for comparison in comparisons:
        existing = by_investigation.get(comparison.investigation_id)
        if existing is None:
            by_investigation[comparison.investigation_id] = comparison
        elif existing.comparison_sha256 != comparison.comparison_sha256:
            duplicate_conflicts.append(comparison.investigation_id)
    bound_by_investigation: dict[str, PairedInvestigationComparison] = {}
    for investigation_id, comparison in by_investigation.items():
        pair = pair_by_id.get(comparison.pair_id)
        certificate = certificate_by_id.get(comparison.certificate_id)
        discriminator: DiscriminatorOutcome | None = None
        followup: InvestigationOutcomeFollowup | None = None
        try:
            canonical_pair = canonical_investigation_evaluation_pair(
                pairs_by_investigation.get(investigation_id, ())
            )
        except ValueError:
            canonical_pair = None
        pair_semantics_valid = False
        if pair is not None:
            try:
                expected_memory_policy = (
                    canonical_shadow
                    if pair.activation_state == "shadow_only"
                    else canonical_limited
                )
                _validate_decisions_against_frozen_policies(
                    baseline_policy=canonical_baseline,
                    memory_policy=expected_memory_policy,
                    baseline_decision=pair.baseline_decision,
                    memory_decision=pair.memory_decision,
                    available_tool_ids=pair.available_tool_ids,
                    eligible_tool_ids=pair.eligible_tool_ids,
                    completed_tool_ids=pair.completed_tool_ids,
                )
                pair_semantics_valid = True
            except ValueError:
                pass
        exact = (
            comparison.activation_protocol_id == protocol.protocol_id
            and comparison.activation_protocol_sha256 == protocol.protocol_sha256
            and pair is not None
            and pair_semantics_valid
            and investigation_id in authoritative_case_ids
            and pair.pair_sha256 == comparison.pair_sha256
            and canonical_pair is not None
            and pair.pair_id == canonical_pair.pair_id
            and pair.investigation_id == investigation_id
            and pair.activation_protocol_id == protocol.protocol_id
            and pair.activation_protocol_sha256 == protocol.protocol_sha256
            and pair.baseline_policy_id == protocol.baseline_policy_id
            and pair.baseline_policy_sha256 == protocol.baseline_policy_sha256
            and (
                (
                    pair.activation_state == "shadow_only"
                    and pair.memory_policy_id == protocol.memory_policy_id
                    and pair.memory_policy_sha256 == protocol.memory_policy_sha256
                    and pair.production_policy_kind == "deterministic_baseline"
                    and pair.production_decision == pair.baseline_decision
                )
                or (
                    pair.activation_state == "limited_attention"
                    and pair.memory_policy_id == protocol.activated_policy_id
                    and pair.memory_policy_sha256
                    == protocol.activated_policy_sha256
                    and pair.production_policy_kind == "limited_attention"
                    and pair.production_decision == pair.memory_decision
                    and pair.activation_decision_id is not None
                    and pair.activation_decision_sha256 is not None
                    and (
                        activation := activation_by_id.get(
                            pair.activation_decision_id
                        )
                    )
                    is not None
                    and activation.decision_sha256
                    == pair.activation_decision_sha256
                    and activation.state == "limited_attention"
                    and not activation.blockers
                    and activation.decided_at <= pair.decision_frozen_at
                    and (
                        activation_evaluation := evaluation_by_id.get(
                            activation.evaluation_id
                        )
                    )
                    is not None
                    and activation_evaluation.evaluation_sha256
                    == activation.evaluation_sha256
                    and activation_evaluation.evaluation_id
                    in canonical_activation_evaluation_ids
                    and activation_evaluation.decision
                    == "limited_attention_earned"
                    and not activation_evaluation.blockers
                    and activation_evaluation.safety.passed
                )
            )
            and pair.p33_context_sha256 == comparison.context_identity_sha256
            and pair.problem_family == comparison.problem_family
            and pair.current_objective == comparison.objective
            and pair.context_transfer_class == comparison.context_transfer_class
            and pair.context_subgroup_keys == comparison.subgroup_keys
            and certificate is not None
            and certificate.activation_protocol_id == protocol.protocol_id
            and certificate.activation_protocol_sha256 == protocol.protocol_sha256
            and certificate.certificate_sha256 == comparison.certificate_sha256
            and certificate.investigation_id == investigation_id
            and certificate.pair_id == comparison.pair_id
            and certificate.pair_sha256 == comparison.pair_sha256
            and certificate.decision_frozen_at == comparison.decision_frozen_at
            and certificate.investigation_opened_at == pair.investigation_opened_at
            and certificate.prospective
            == (pair.investigation_opened_at > protocol.prospective_boundary)
        )
        if comparison.discriminator_outcome_id is not None:
            discriminator = discriminator_by_id.get(
                comparison.discriminator_outcome_id
            )
            source_pair = (
                pair_by_id.get(discriminator.source_pair_id)
                if discriminator is not None
                else None
            )
            exact = exact and (
                discriminator is not None
                and discriminator.outcome_id in authoritative_discriminator_ids
                and discriminator.activation_protocol_id == protocol.protocol_id
                and discriminator.activation_protocol_sha256
                == protocol.protocol_sha256
                and discriminator.outcome_sha256
                == comparison.discriminator_outcome_sha256
                and discriminator.investigation_id == investigation_id
                and discriminator.prediction_pair_id == pair.pair_id
                and discriminator.prediction_pair_sha256 == pair.pair_sha256
                and source_pair is not None
                and source_pair.pair_sha256 == discriminator.source_pair_sha256
                and source_pair.investigation_id == investigation_id
                and source_pair.workspace_revision == discriminator.workspace_revision
                and source_pair.authority_revision
                == discriminator.source_authority_revision
                and source_pair.authority_revision == pair.authority_revision
                and source_pair.step_number + 1 == discriminator.request_sequence
                and source_pair.baseline_decision.action_id
                == discriminator.tool_id
                and pair.memory_decision.action_id == discriminator.tool_id
                and discriminator.tool_id in certificate.tools_actually_requested
                and discriminator.request_event_id in certificate.tool_request_event_ids
                and certificate.tools_actually_requested[
                    certificate.tool_request_event_ids.index(
                        discriminator.request_event_id
                    )
                ]
                == discriminator.tool_id
                and discriminator.tool_id in certificate.tool_results_received
                and discriminator.result_event_id in certificate.tool_result_event_ids
                and certificate.tool_results_received[
                    certificate.tool_result_event_ids.index(
                        discriminator.result_event_id
                    )
                ]
                == discriminator.tool_id
                and discriminator.before_p19_snapshot_sha256
                == source_pair.p19_snapshot_sha256
                and discriminator.after_p19_snapshot_sha256
                == certificate.final_p19_snapshot_sha256
                and set(discriminator.relevant_ambiguity_ids).issubset(
                    set(pair.current_p19_cause_ids)
                )
                and certificate.useful_discriminator_id == discriminator.tool_id
            )
        if comparison.outcome_followup_id is not None:
            followup = followup_by_id.get(comparison.outcome_followup_id)
            exact = exact and (
                followup is not None
                and followup.activation_protocol_id == protocol.protocol_id
                and followup.activation_protocol_sha256 == protocol.protocol_sha256
                and followup.followup_sha256 == comparison.outcome_followup_sha256
                and followup.investigation_id == investigation_id
                and followup.certificate_id == comparison.certificate_id
                and followup.certificate_sha256 == comparison.certificate_sha256
            )
        if comparison.counterfactual_source_certificate_id is not None:
            exact = False
        if exact and pair is not None and certificate is not None:
            try:
                canonical_body = build_paired_investigation_comparison(
                    investigation_pairs=tuple(
                        pairs_by_investigation.get(investigation_id, (pair,))
                    ),
                    certificate=certificate,
                    discriminator_outcome=discriminator,
                    outcome_followup=followup,
                    recurrence_match_correct=None,
                    compared_at=comparison.compared_at,
                )
                exact = canonical_body == comparison
            except (TypeError, ValueError):
                exact = False
        if exact:
            bound_by_investigation[investigation_id] = comparison
        else:
            parent_failures.append(investigation_id)
    bound = tuple(bound_by_investigation.values())
    eligible = tuple(
        item
        for item in bound
        if item.qualified
        and not item.synthetic
        and pair_by_id[item.pair_id].activation_state == "shadow_only"
        and item.prospective
        == (
            pair_by_id[item.pair_id].investigation_opened_at
            > protocol.prospective_boundary
        )
    )
    historical = tuple(item for item in eligible if not item.prospective)
    prospective = tuple(item for item in eligible if item.prospective)
    observable = tuple(
        item
        for item in eligible
        if item.observability
        in {"directly_observed", "counterfactual_observable"}
    )
    unobservable = tuple(
        item
        for item in eligible
        if item.observability in {"pending", "counterfactual_unobservable"}
    )
    invalid_count = sum(
        item.observability == "invalid" for item in bound
    ) + len(parent_failures)
    safety_cases = tuple(item for item in bound if not item.synthetic)
    safety = P34SafetyResults(
        authority_violations=sum(item.authority_violations for item in safety_cases),
        p19_action_mismatches=sum(item.p19_action_mismatches for item in safety_cases),
        stale_workspace_actions=sum(item.stale_workspace_actions for item in safety_cases),
        mandatory_check_violations=sum(
            item.mandatory_check_violations for item in safety_cases
        ),
        hidden_contradiction_failures=sum(
            item.hidden_contradiction_failures for item in safety_cases
        ),
        incompatible_history_transfers=sum(
            item.incompatible_history_transfers for item in safety_cases
        ),
        driver_memory_mechanical_diagnoses=sum(
            item.driver_memory_mechanical_diagnoses for item in safety_cases
        ),
        memory_only_terminal_actions=sum(
            item.memory_only_terminal_actions for item in safety_cases
        ),
    )
    efficiency_observable = tuple(
        item for item in observable if item.memory_path_metrics_observed
    )
    consumption_difference_cases = tuple(
        item
        for item in observable
        if item.baseline_consumption_metrics_observed
        and item.memory_consumption_metrics_observed
    )
    baseline_consumption_observation_count = sum(
        item.baseline_consumption_metrics_observed for item in observable
    )
    step_reductions = tuple(
        item.baseline_tool_steps - int(item.memory_tool_steps)
        for item in efficiency_observable
    )
    relative_reductions = tuple(
        (item.baseline_tool_steps - int(item.memory_tool_steps))
        / item.baseline_tool_steps
        for item in efficiency_observable
        if item.baseline_tool_steps
    )
    baseline_dead_ends = sum(
        item.baseline_dead_ends for item in efficiency_observable
    )
    memory_dead_ends = sum(
        int(item.memory_dead_ends) for item in efficiency_observable
    )
    baseline_repeated = sum(
        item.baseline_repeated_no_findings for item in efficiency_observable
    )
    memory_repeated = sum(
        int(item.memory_repeated_no_findings) for item in efficiency_observable
    )
    efficiency = P34EfficiencyResults(
        median_tool_step_difference=_median(step_reductions),
        relative_tool_step_reduction=_median(relative_reductions),
        median_elapsed_seconds_difference=_median(
            item.baseline_elapsed_seconds - float(item.memory_elapsed_seconds)
            for item in efficiency_observable
        ),
        median_lap_difference=(
            _median(
                int(item.baseline_laps) - int(item.memory_laps)
                for item in consumption_difference_cases
            )
            if consumption_difference_cases
            else None
        ),
        median_question_difference=_median(
            item.baseline_questions - int(item.memory_questions)
            for item in efficiency_observable
        ),
        median_measurement_mission_difference=(
            _median(
                int(item.baseline_measurement_missions)
                - int(item.memory_measurement_missions)
                for item in consumption_difference_cases
            )
            if consumption_difference_cases
            else None
        ),
        lap_consumption_observation_count=baseline_consumption_observation_count,
        measurement_mission_observation_count=(
            baseline_consumption_observation_count
        ),
        dead_end_reduction_rate=(
            (baseline_dead_ends - memory_dead_ends) / baseline_dead_ends
            if baseline_dead_ends
            else 0.0
        ),
        repeated_no_finding_reduction_rate=(
            (baseline_repeated - memory_repeated) / baseline_repeated
            if baseline_repeated
            else 0.0
        ),
        earlier_useful_discriminator_rate=_rate(
            item.baseline_useful_discriminator_step is not None
            and item.memory_useful_discriminator_step is not None
            and item.memory_useful_discriminator_step
            < item.baseline_useful_discriminator_step
            for item in observable
            if item.context_transfer_class in {"exact", "compatible"}
        ),
        unresolved_abandoned_rate_change=(
            _rate(
                bool(item.memory_unresolved_or_abandoned)
                for item in efficiency_observable
            )
            - _rate(
                item.baseline_unresolved_or_abandoned
                for item in efficiency_observable
            )
        ),
    )
    completed_followup_by_investigation: dict[
        str, InvestigationOutcomeFollowup
    ] = {}
    followup_conflicts: list[str] = []
    for item in eligible:
        matches = followups_by_certificate.get(item.certificate_id, ())
        if len(matches) == 1:
            completed_followup_by_investigation[item.investigation_id] = matches[0]
        elif len(matches) > 1:
            followup_conflicts.append(item.investigation_id)
    quality = P34QualityResults(
        useful_discriminator_hit_rate=_rate(
            item.useful_discriminator_hit for item in observable
        ),
        strongest_contradiction_inspection_rate=_rate(
            item.strongest_contradiction_handled for item in eligible
        ),
        recurrence_match_correctness_rate=_rate(
            bool(item.recurrence_match_correct)
            for item in eligible
            if item.recurrence_match_correct is not None
        ),
        context_transfer_correctness_rate=_rate(
            item.context_transfer_correct
            for item in eligible
            if item.context_transfer_correct is not None
        ),
        driver_car_separation_correctness_rate=_rate(
            item.driver_car_separation_correct
            for item in eligible
            if item.driver_car_separation_correct is not None
        ),
        eventual_p19_resolution_rate=_rate(
            followup.observed_p19_outcome in {"keep", "undo", "retest", "no_call"}
            for followup in completed_followup_by_investigation.values()
        ),
        no_call_stability_rate=_rate(
            followup.observed_p19_outcome == "no_call"
            for investigation_id, followup in completed_followup_by_investigation.items()
            if certificate_by_id[
                bound_by_investigation[investigation_id].certificate_id
            ].terminal_crew_decision
            == "no_call"
        ),
    )
    comparison_by_investigation = {
        item.investigation_id: item for item in observable
    }
    transfers_by_investigation: dict[str, InvestigationNegativeTransfer] = {}
    transfer_parent_failures: list[str] = []
    for transfer in negative_transfers:
        comparison = comparison_by_investigation.get(transfer.investigation_id)
        expected_transfer = (
            build_investigation_negative_transfer(
                comparison,
                detected_at=transfer.detected_at,
            )
            if comparison is not None
            else None
        )
        if (
            comparison is None
            or expected_transfer is None
            or transfer != expected_transfer
            or transfer.activation_protocol_id != protocol.protocol_id
            or transfer.activation_protocol_sha256 != protocol.protocol_sha256
            or transfer.pair_id != comparison.pair_id
            or transfer.comparison_id != comparison.comparison_id
            or transfer.comparison_sha256 != comparison.comparison_sha256
            or transfer.evidence_artifact_ids != (comparison.comparison_id,)
            or transfer.detected_at < comparison.compared_at
        ):
            transfer_parent_failures.append(transfer.investigation_id)
            continue
        transfers_by_investigation[transfer.investigation_id] = transfer
    derived_harm_ids = {
        item.investigation_id
        for item in observable
        if _derived_negative_transfer_kinds(item)
    }
    missing_transfer_ids = derived_harm_ids - set(transfers_by_investigation)
    negative_count = len(derived_harm_ids)
    negative_rate = negative_count / len(observable) if observable else 0.0
    control_records = tuple(negative_control_results)
    controls: dict[str, bool] = {}
    for control_id in protocol.negative_control_ids:
        matches = tuple(
            item
            for item in control_records
            if item.control_id == control_id
            and item.protocol_id == protocol.protocol_id
            and item.protocol_sha256 == protocol.protocol_sha256
            and (parent := pair_by_id.get(item.pair_id)) is not None
            and parent.pair_sha256 == item.pair_sha256
            and parent.investigation_id == item.investigation_id
            and parent.investigation_id in authoritative_case_ids
            and parent.negative_control_condition == control_id
            and item
            == build_p34_negative_control_result(
                parent,
                control_id=control_id,
                evaluated_at=item.evaluated_at,
            )
            and parent.baseline_decision.executable_identity
            == parent.memory_decision.executable_identity
            and not parent.memory_records_consulted
            and item.source_artifact_ids == (parent.pair_id,)
            and item.evaluated_at > parent.decision_frozen_at
        )
        controls[control_id] = bool(matches) and all(item.passed for item in matches)
    subgroup_results: list[P34SubgroupResult] = []
    for subgroup_key in protocol.required_subgroups:
        cases = tuple(item for item in eligible if subgroup_key in item.subgroup_keys)
        authority = sum(item.authority_violations for item in cases)
        mandatory = sum(item.mandatory_check_violations for item in cases)
        degradation = max(
            (
                max(
                    0.0,
                    (
                        (
                            int(item.memory_tool_steps)
                            - item.baseline_tool_steps
                        )
                        if item.memory_tool_steps is not None
                        else 0
                    )
                    / max(item.baseline_tool_steps, 1)
                    * 100,
                )
                for item in cases
                if item.memory_tool_steps is not None
            ),
            default=0.0,
        )
        subgroup_blockers = () if cases else ("No qualified independent cases.",)
        passed = bool(cases) and not authority and not mandatory and degradation <= 20
        subgroup_results.append(
            P34SubgroupResult(
                subgroup_key=subgroup_key,
                independent_investigations=len(cases),
                authority_violations=authority,
                mandatory_check_violations=mandatory,
                material_efficiency_degradation_pct=degradation,
                passed=passed,
                blockers=subgroup_blockers,
            )
        )
    context_count = len(
        {
            (
                pair_by_id[item.pair_id].track,
                pair_by_id[item.pair_id].track_configuration,
                pair_by_id[item.pair_id].package_type,
            )
            for item in eligible
        }
    )
    problem_count = len({item.problem_family for item in eligible})
    objective_count = len({item.objective for item in eligible})
    exact_count = sum(
        item.context_transfer_class == "exact"
        and bool(pair_by_id[item.pair_id].memory_records_consulted)
        for item in eligible
    )
    compatible_count = sum(
        item.context_transfer_class == "compatible"
        and bool(pair_by_id[item.pair_id].memory_records_consulted)
        for item in eligible
    )
    future_build_leakage = tuple(
        item
        for item in bound
        if pair_by_id[item.pair_id].build_review_state
        == "future_unreviewed_build"
        and pair_by_id[item.pair_id].baseline_decision.executable_identity
        != pair_by_id[item.pair_id].memory_decision.executable_identity
    )
    prospective_observable = tuple(
        item
        for item in prospective
        if item.observability
        in {"directly_observed", "counterfactual_observable"}
    )
    prospective_full_path = tuple(
        item
        for item in prospective_observable
        if item.memory_path_metrics_observed
    )
    prospective_step_reductions = tuple(
        item.baseline_tool_steps - int(item.memory_tool_steps)
        for item in prospective_full_path
    )
    prospective_relative_reductions = tuple(
        (item.baseline_tool_steps - int(item.memory_tool_steps))
        / max(item.baseline_tool_steps, 1)
        for item in prospective_full_path
    )
    prospective_consumption = tuple(
        item
        for item in prospective_observable
        if item.baseline_consumption_metrics_observed
        and item.memory_consumption_metrics_observed
    )
    prospective_baseline_dead_ends = sum(
        item.baseline_dead_ends for item in prospective_full_path
    )
    prospective_memory_dead_ends = sum(
        int(item.memory_dead_ends) for item in prospective_full_path
    )
    prospective_safety_passed = not any(
        (
            item.authority_violations
            or item.p19_action_mismatches
            or item.stale_workspace_actions
            or item.mandatory_check_violations
            or item.hidden_contradiction_failures
            or item.incompatible_history_transfers
            or item.driver_memory_mechanical_diagnoses
            or item.memory_only_terminal_actions
        )
        for item in prospective
    )
    prospective_negative_rate = (
        sum(bool(_derived_negative_transfer_kinds(item)) for item in prospective_observable)
        / len(prospective_observable)
        if prospective_observable
        else 0.0
    )
    prospective_efficiency_passed = bool(
        len(prospective_observable)
        >= protocol.minimum_prospective_investigations
        and (
            _median(prospective_step_reductions)
            >= protocol.minimum_tool_step_reduction
            or _median(prospective_relative_reductions)
            >= protocol.minimum_relative_tool_step_reduction
        )
        and len(prospective_consumption) == len(prospective_observable)
        and _median(
            int(item.baseline_laps) - int(item.memory_laps)
            for item in prospective_consumption
        )
        >= 0
        and _median(
            int(item.baseline_measurement_missions)
            - int(item.memory_measurement_missions)
            for item in prospective_consumption
        )
        >= 0
        and _rate(
            item.baseline_useful_discriminator_step is not None
            and item.memory_useful_discriminator_step is not None
            and item.memory_useful_discriminator_step
            < item.baseline_useful_discriminator_step
            for item in prospective_observable
            if item.context_transfer_class in {"exact", "compatible"}
        )
        >= protocol.minimum_earlier_discriminator_rate
        and (
            (
                prospective_baseline_dead_ends
                - prospective_memory_dead_ends
            )
            / prospective_baseline_dead_ends
            if prospective_baseline_dead_ends
            else 0.0
        )
        >= protocol.minimum_dead_end_reduction_rate
        and (
            _rate(
                bool(item.memory_unresolved_or_abandoned)
                for item in prospective_full_path
            )
            - _rate(
                item.baseline_unresolved_or_abandoned
                for item in prospective_full_path
            )
        )
        <= protocol.maximum_unresolved_rate_worsening
        and prospective_negative_rate <= protocol.maximum_negative_transfer_rate
    )
    blockers: list[str] = []
    deficits = {
        "historical": protocol.minimum_historical_investigations - len(historical),
        "prospective": protocol.minimum_prospective_investigations - len(prospective),
        "contexts": protocol.minimum_contexts - context_count,
        "problem families": protocol.minimum_problem_families - problem_count,
        "objectives": protocol.minimum_objectives - objective_count,
        "exact recurrence": protocol.minimum_exact_recurrence_cases - exact_count,
        "compatible recurrence": (
            protocol.minimum_compatible_recurrence_cases - compatible_count
        ),
    }
    for label, deficit in deficits.items():
        if deficit > 0:
            blockers.append(f"Need {deficit} additional qualified {label} unit(s).")
    if duplicate_conflicts:
        blockers.append("Conflicting repeated investigation comparisons were withheld.")
    if followup_conflicts:
        blockers.append("Conflicting repeated P19 outcome follow-ups were withheld.")
    if capacity_overflow_kinds:
        blockers.append(
            "P34 activation evidence exceeds the frozen 10000-unit retrieval bound; "
            "no activation can be evaluated without a versioned capacity review."
        )
    if not foundation_verified:
        blockers.append("Frozen P34 policy/protocol records are missing or mismatched.")
    if parent_failures:
        blockers.append("Orphan or swapped-parent comparisons were withheld.")
    if not safety.passed:
        blockers.append("One or more frozen safety gates failed.")
    efficiency_passed = (
        (
            efficiency.median_tool_step_difference
            >= protocol.minimum_tool_step_reduction
            or efficiency.relative_tool_step_reduction
            >= protocol.minimum_relative_tool_step_reduction
        )
        and efficiency.lap_consumption_observation_count == len(observable)
        and efficiency.measurement_mission_observation_count == len(observable)
        and efficiency.median_lap_difference is not None
        and efficiency.median_lap_difference >= 0
        and efficiency.median_measurement_mission_difference is not None
        and efficiency.median_measurement_mission_difference >= 0
        and efficiency.earlier_useful_discriminator_rate
        >= protocol.minimum_earlier_discriminator_rate
        and efficiency.dead_end_reduction_rate
        >= protocol.minimum_dead_end_reduction_rate
        and efficiency.unresolved_abandoned_rate_change
        <= protocol.maximum_unresolved_rate_worsening
    )
    if not efficiency_passed:
        blockers.append("Frozen investigation-efficiency thresholds are not met.")
    if not prospective_safety_passed or not prospective_efficiency_passed:
        blockers.append(
            "Frozen prospective safety and investigation-efficiency thresholds "
            "are not independently met."
        )
    if negative_rate > protocol.maximum_negative_transfer_rate:
        blockers.append("Frozen negative-transfer ceiling is exceeded.")
    if transfer_parent_failures or missing_transfer_ids:
        blockers.append(
            "Attributable negative transfer is missing or not exact parent lineage."
        )
    if not all(controls.values()):
        blockers.append("Frozen negative controls are incomplete or failed.")
    if not all(item.passed for item in subgroup_results):
        blockers.append("One or more required subgroups are missing or failed.")
    if future_build_leakage:
        blockers.append(
            "Future or unreviewed build history crossed the frozen fallback boundary."
        )
    decision = (
        "limited_attention_earned" if not blockers else "no_activation_earned"
    )
    return InvestigationPolicyEvaluation.build(
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol.protocol_sha256,
        registry_identity_sha256=registry_identity_sha256,
        ledger_record_count=ledger_record_count,
        ledger_head_sha256=ledger_head_sha256,
        baseline_policy_id=protocol.baseline_policy_id,
        memory_policy_id=protocol.memory_policy_id,
        independent_investigation_count=len(eligible),
        historical_count=len(historical),
        prospective_count=len(prospective),
        context_count=context_count,
        problem_family_count=problem_count,
        objective_count=objective_count,
        exact_recurrence_count=exact_count,
        compatible_recurrence_count=compatible_count,
        paired_observable_comparisons=len(observable),
        unobservable_comparisons=len(unobservable),
        invalid_comparisons=invalid_count,
        safety=safety,
        efficiency=efficiency,
        quality=quality,
        negative_transfer_count=negative_count,
        negative_transfer_rate=negative_rate,
        negative_control_results=controls,
        subgroup_results=tuple(subgroup_results),
        drift_results={
            "driver_stable": sum(
                pair_by_id[item.pair_id].driver_drift_state == "stable"
                for item in eligible
            ),
            "driver_drift_detected": sum(
                pair_by_id[item.pair_id].driver_drift_state == "material_drift"
                for item in eligible
            ),
            "driver_state_unknown": sum(
                pair_by_id[item.pair_id].driver_drift_state == "unknown"
                for item in eligible
            ),
            "same_build": sum(
                pair_by_id[item.pair_id].build_review_state == "same_build"
                for item in eligible
            ),
            "reviewed_compatible_build": sum(
                pair_by_id[item.pair_id].build_review_state
                == "reviewed_compatible_build"
                for item in eligible
            ),
            "future_unreviewed_build": sum(
                pair_by_id[item.pair_id].build_review_state
                == "future_unreviewed_build"
                for item in eligible
            ),
        },
        blockers=tuple(dict.fromkeys(blockers)),
        decision=decision,
        evaluated_at=evaluated_at,
    )


def _global_activation_rollback_reasons(
    evaluation: InvestigationPolicyEvaluation,
) -> tuple[str, ...]:
    """Return only global safety/integrity debt, never per-case fallback facts."""

    reasons: list[str] = []
    if not evaluation.safety.passed:
        reasons.append(
            "A post-activation authority or mandatory safety gate failed."
        )
    integrity_markers = (
        "missing or mismatched",
        "Orphan or swapped-parent",
        "Conflicting repeated",
        "missing or not exact parent lineage",
        "exceeds the frozen 10000-unit retrieval bound",
    )
    reasons.extend(
        blocker
        for blocker in evaluation.blockers
        if any(marker in blocker for marker in integrity_markers)
    )
    return tuple(dict.fromkeys(reasons))


def build_p34_activation_decision(
    evaluation: InvestigationPolicyEvaluation,
    *,
    repository: InvestigationAdaptationRepository,
    decided_at: datetime,
) -> P34ActivationDecision:
    protocol = p34_activation_protocol()
    if (
        evaluation.protocol_id != protocol.protocol_id
        or evaluation.protocol_sha256 != protocol.protocol_sha256
    ):
        raise ValueError("P34 activation decision requires the frozen protocol")
    recomputed = evaluate_p34_repository(
        repository,
        evaluated_at=evaluation.evaluated_at,
        strict_integrity=True,
    )
    if recomputed != evaluation:
        raise ValueError("P34 activation evaluation does not match the canonical ledger")
    earned = evaluation.decision == "limited_attention_earned" and not evaluation.blockers
    prior_result = repository.query_records(
        record_kinds=("activation_decision",),
        protocol_id=protocol.protocol_id,
        limit=512,
    )
    prior_latest = next(
        (
            item
            for item in prior_result.records
            if isinstance(item, P34ActivationDecision)
            and item.decided_at <= decided_at
        ),
        None,
    )
    prior_limited = (
        prior_latest
        if prior_latest is not None and prior_latest.state == "limited_attention"
        else None
    )
    rollback_reasons = _global_activation_rollback_reasons(evaluation)
    if not earned and prior_limited is not None and not rollback_reasons:
        # A no-memory/drift/blocked-transfer case is a local baseline fallback,
        # not evidence that the globally earned policy became unsafe.
        return prior_limited
    decision_blockers = (
        ()
        if earned
        else rollback_reasons
        if prior_limited is not None
        else evaluation.blockers
    )
    return P34ActivationDecision.build(
        protocol_id=protocol.protocol_id,
        protocol_sha256=protocol.protocol_sha256,
        evaluation_id=evaluation.evaluation_id,
        evaluation_sha256=evaluation.evaluation_sha256,
        activated_policy_id=protocol.activated_policy_id,
        activated_policy_sha256=protocol.activated_policy_sha256,
        state="limited_attention" if earned else "shadow_only",
        production_policy_kind=(
            "limited_attention" if earned else "deterministic_baseline"
        ),
        blockers=decision_blockers,
        recovery_debt=() if earned else decision_blockers,
        supersedes_decision_id=(
            prior_limited.decision_id
            if not earned and prior_limited is not None
            else None
        ),
        supersedes_decision_sha256=(
            prior_limited.decision_sha256
            if not earned and prior_limited is not None
            else None
        ),
        rollback_applied=not earned and prior_limited is not None,
        decided_at=decided_at,
    )


def persist_p34_evaluation_and_activation(
    repository: InvestigationAdaptationRepository,
    *,
    evaluated_at: datetime,
    decided_at: datetime,
) -> tuple[InvestigationPolicyEvaluation, P34ActivationDecision]:
    """Atomically append one canonical evaluation and its activation decision."""

    evaluation = evaluate_p34_repository(
        repository,
        evaluated_at=evaluated_at,
        strict_integrity=True,
    )
    decision = build_p34_activation_decision(
        evaluation,
        repository=repository,
        decided_at=decided_at,
    )
    active = initialize_database(repository.db_path)
    try:
        active.execute("BEGIN IMMEDIATE")
        boundary = repository.stream_state(connection=active)
        evidence_record_count, evidence_head_sha256 = (
            _p34_evidence_stream_boundary(
                active,
                stream_record_count=boundary.record_count,
            )
        )
        if (
            evidence_record_count != evaluation.ledger_record_count
            or evidence_head_sha256 != evaluation.ledger_head_sha256
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 ledger changed between evaluation and activation append"
            )
        repository.append_evaluation_in_transaction(active, evaluation)
        repository.append_activation_decision_in_transaction(active, decision)
        active.commit()
    except Exception:
        active.rollback()
        raise
    finally:
        active.close()
    _mark_current_p34_chain_verified(repository)
    return evaluation, decision


def review_p34_after_terminal_capture(
    repository: InvestigationAdaptationRepository,
    *,
    captured_at: datetime,
) -> tuple[InvestigationPolicyEvaluation, P34ActivationDecision]:
    """Idempotent server-owned post-terminal activation/rollback review seam."""

    candidate = evaluate_p34_repository(
        repository,
        evaluated_at=captured_at,
        strict_integrity=True,
    )
    existing = repository.query_records(
        record_kinds=("policy_evaluation", "activation_decision"),
        protocol_id=p34_activation_protocol().protocol_id,
        limit=512,
    )
    evaluations = {
        item.evaluation_id: item
        for item in existing.records
        if isinstance(item, InvestigationPolicyEvaluation)
        and item.evaluation_id == candidate.evaluation_id
        and item.evaluation_sha256 == candidate.evaluation_sha256
        and item == candidate
    }
    for item in existing.records:
        if (
            isinstance(item, P34ActivationDecision)
            and item.evaluation_id in evaluations
            and item.evaluation_sha256
            == evaluations[item.evaluation_id].evaluation_sha256
        ):
            return evaluations[item.evaluation_id], item
    return persist_p34_evaluation_and_activation(
        repository,
        evaluated_at=captured_at,
        decided_at=captured_at,
    )


def recover_unreviewed_p34_terminal_capture(
    repository: InvestigationAdaptationRepository,
) -> tuple[InvestigationPolicyEvaluation, P34ActivationDecision] | None:
    """Recover the latest crash-window terminal review on an explicit mutation.

    A terminal capture and its comparison commit atomically before review.  The
    ordered immutable ledger therefore makes a missing later evaluation an
    exact, cheap recovery signal.  Read-only workspace projection never calls
    this seam.
    """

    active = connect_read_only(repository.db_path)
    try:
        protocol_id = p34_activation_protocol().protocol_id
        rows = active.execute(
            "SELECT record_kind, MAX(sequence) AS sequence "
            "FROM investigation_adaptation_records "
            "WHERE record_kind IN ('paired_comparison', 'policy_evaluation') "
            "AND protocol_id = ? "
            "GROUP BY record_kind",
            (protocol_id,),
        ).fetchall()
    finally:
        active.close()
    sequences = {row["record_kind"]: int(row["sequence"]) for row in rows}
    comparison_sequence = sequences.get("paired_comparison")
    evaluation_sequence = sequences.get("policy_evaluation", 0)
    if comparison_sequence is None or evaluation_sequence > comparison_sequence:
        return None
    latest = repository.query_records(
        record_kinds=("paired_comparison",),
        protocol_id=p34_activation_protocol().protocol_id,
        limit=1,
    )
    comparison = next(
        (
            item
            for item in latest.records
            if isinstance(item, PairedInvestigationComparison)
        ),
        None,
    )
    if comparison is None:
        return None
    return review_p34_after_terminal_capture(
        repository,
        captured_at=comparison.compared_at,
    )


def assess_investigation_improvement_readiness(
    evaluation: InvestigationPolicyEvaluation,
    *,
    effective_activation: P34ActivationDecision | None = None,
) -> InvestigationImprovementReadiness:
    protocol = p34_activation_protocol()
    evaluation_earned = (
        evaluation.decision == "limited_attention_earned" and not evaluation.blockers
    )
    active = bool(
        effective_activation is not None
        and effective_activation.state == "limited_attention"
        and effective_activation.production_policy_kind == "limited_attention"
        and effective_activation.protocol_id == protocol.protocol_id
        and effective_activation.protocol_sha256 == protocol.protocol_sha256
        and not effective_activation.blockers
        and not _global_activation_rollback_reasons(evaluation)
    )
    deficits = {
        "historical": max(
            0,
            protocol.minimum_historical_investigations - evaluation.historical_count,
        ),
        "prospective": max(
            0,
            protocol.minimum_prospective_investigations - evaluation.prospective_count,
        ),
        "exact": max(
            0,
            protocol.minimum_exact_recurrence_cases
            - evaluation.exact_recurrence_count,
        ),
        "compatible": max(
            0,
            protocol.minimum_compatible_recurrence_cases
            - evaluation.compatible_recurrence_count,
        ),
        "contexts": max(0, protocol.minimum_contexts - evaluation.context_count),
        "problems": max(
            0, protocol.minimum_problem_families - evaluation.problem_family_count
        ),
        "objectives": max(
            0, protocol.minimum_objectives - evaluation.objective_count
        ),
    }
    missions: list[str] = []
    if deficits["historical"]:
        missions.append(
            "Historical qualification remains locked: no scientifically blind "
            "archived-replay admission path is implemented for the frozen 20-case gate."
        )
    missions.extend(
        f"Collect {deficit} additional qualified {label} investigation unit(s)."
        for label, deficit in deficits.items()
        if deficit and label != "historical"
    )
    missions.extend(
        f"Complete frozen negative control: {control_id}."
        for control_id in protocol.negative_control_ids
        if not evaluation.negative_control_results.get(control_id, False)
    )
    missions.extend(
        f"Collect or repair required subgroup: {item.subgroup_key}."
        for item in evaluation.subgroup_results
        if not item.passed
    )
    if not evaluation.safety.passed:
        missions.append(
            "Resolve recorded safety-gate debt before another activation review."
        )
    if "Frozen investigation-efficiency thresholds are not met." in evaluation.blockers:
        missions.append(
            "Frozen v1 shadow evidence can measure discriminator timing but cannot "
            "prove fewer terminal tool steps or skipped dead ends; activation remains "
            "locked until a versioned prospective trial can observe the memory path."
        )
    readiness_blockers = list(evaluation.blockers)
    if evaluation_earned and not active:
        readiness_blockers.append(
            "The earned gate evaluation has no exact current activation artifact; "
            "production remains deterministic baseline."
        )
    return InvestigationImprovementReadiness(
        production_policy=(
            "limited_attention" if active else "deterministic_baseline"
        ),
        memory_policy_state="limited_attention" if active else "shadow_only",
        activation_decision=(
            "limited_attention_earned" if active else "no_activation_earned"
        ),
        evaluation_decision=evaluation.decision,
        effective_activation_decision_id=(
            effective_activation.decision_id if active and effective_activation else None
        ),
        effective_activation_decision_sha256=(
            effective_activation.decision_sha256 if active and effective_activation else None
        ),
        qualified_historical_investigations=evaluation.historical_count,
        qualified_prospective_investigations=evaluation.prospective_count,
        observable_comparisons=evaluation.paired_observable_comparisons,
        unobservable_comparisons=evaluation.unobservable_comparisons,
        historical_deficit=deficits["historical"],
        prospective_deficit=deficits["prospective"],
        exact_recurrence_deficit=deficits["exact"],
        compatible_recurrence_deficit=deficits["compatible"],
        context_deficit=deficits["contexts"],
        problem_family_deficit=deficits["problems"],
        objective_deficit=deficits["objectives"],
        safety_gate_passed=evaluation.safety.passed,
        negative_controls_passed=all(
            evaluation.negative_control_results.get(item, False)
            for item in protocol.negative_control_ids
        ),
        subgroup_gate_passed=all(
            item.passed for item in evaluation.subgroup_results
        ),
        blockers=tuple(dict.fromkeys(readiness_blockers)),
        remaining_collection_missions=tuple(dict.fromkeys(missions)),
    )


def assess_p34_repository_readiness(
    repository: InvestigationAdaptationRepository,
    *,
    evaluated_at: datetime | None = None,
) -> InvestigationImprovementReadiness:
    """Canonical read-only readiness with the effective activation resolved."""

    evaluation = evaluate_p34_repository(repository, evaluated_at=evaluated_at)
    return assess_investigation_improvement_readiness(
        evaluation,
        effective_activation=resolve_effective_activation_decision(repository),
    )


def build_investigation_improvement_projection(
    *,
    run_id: str,
    session_id: str,
    workspace_revision: str,
    readiness: InvestigationImprovementReadiness,
    current_pair: PairedInvestigationDecision | None,
    current_context: InvestigationAdaptationContext | None,
    latest_completed_pair: PairedInvestigationDecision | None = None,
    latest_completed_comparison: PairedInvestigationComparison | None = None,
    safety_blockers: tuple[str, ...] = (),
) -> InvestigationImprovementProjection:
    if current_pair is None and latest_completed_comparison is None:
        blockers = safety_blockers or (
            "No eligible frozen investigation revision is available.",
        )
        return InvestigationImprovementProjection.build(
            run_id=run_id,
            session_id=session_id,
            workspace_revision=workspace_revision,
            state="unavailable",
            production_policy=readiness.production_policy,
            memory_policy_state=readiness.memory_policy_state,
            current_pair=None,
            current_context=None,
            current_pair_status=None,
            latest_completed_pair=None,
            latest_completed_comparison=None,
            latest_outcome_status=None,
            decisions_differ=False,
            difference_explanation=(
                "No paired decision was fabricated; readiness remains visible."
            ),
            memory_evidence_record_ids=(),
            context_transfer_class="none",
            readiness=readiness,
            safety_blockers=blockers,
        )
    surfaced_pair = current_pair or latest_completed_pair
    if surfaced_pair is None:
        raise ValueError("P34 completed comparison requires its exact parent pair")
    differs = (
        surfaced_pair.baseline_decision.executable_identity
        != surfaced_pair.memory_decision.executable_identity
    )
    explanation = (
        surfaced_pair.memory_decision.reason
        if differs
        else "Memory selected the same executable next inspection as baseline."
    )
    return InvestigationImprovementProjection.build(
        run_id=run_id,
        session_id=session_id,
        workspace_revision=workspace_revision,
        state="available",
        production_policy=readiness.production_policy,
        memory_policy_state=readiness.memory_policy_state,
        current_pair=current_pair,
        current_context=current_context,
        current_pair_status="pending" if current_pair is not None else None,
        latest_completed_pair=latest_completed_pair,
        latest_completed_comparison=latest_completed_comparison,
        latest_outcome_status=(
            latest_completed_comparison.observability
            if latest_completed_comparison is not None
            else None
        ),
        decisions_differ=differs,
        difference_explanation=explanation,
        memory_evidence_record_ids=(
            surfaced_pair.memory_records_consulted
        ),
        context_transfer_class=(
            surfaced_pair.context_transfer_class
        ),
        readiness=readiness,
        safety_blockers=safety_blockers,
    )


def latest_completed_comparison_lineage(
    repository: InvestigationAdaptationRepository,
    *,
    run_id: str,
    session_id: str,
) -> tuple[PairedInvestigationDecision, PairedInvestigationComparison] | None:
    """Read one bounded exact parent/comparison lineage for Learning Mode."""

    protocol = p34_activation_protocol()
    result = repository.query_records(
        record_kinds=("paired_comparison",),
        protocol_id=protocol.protocol_id,
        limit=512,
    )
    if result.blockers:
        raise InvestigationAdaptationIntegrityError(result.blockers[0])
    for record in result.records:
        if not isinstance(record, PairedInvestigationComparison):
            continue
        parent = repository.get_paired_decision(record.pair_sha256)
        if parent is None:
            raise InvestigationAdaptationIntegrityError(
                "P34 latest comparison is missing its exact parent pair"
            )
        if (
            parent.pair_id != record.pair_id
            or parent.investigation_id != record.investigation_id
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 latest comparison parent identity is corrupt"
            )
        if parent.run_id == run_id and parent.session_id == session_id:
            return parent, record
    return None


def _repository_storage_fingerprint(database_file: str) -> tuple[object, ...]:
    """Fingerprint every SQLite file that can contain a committed source row."""

    def file_state(path: str) -> tuple[int | None, int | None, int | None]:
        try:
            stat = os.stat(path)
        except OSError:
            return (None, None, None)
        return (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)

    return (
        database_file,
        *file_state(database_file),
        *file_state(f"{database_file}-wal"),
    )


def _authoritative_source_revision(connection: object) -> int:
    """Read the SQLite-owned mutation identity shared by all P34 source tables."""

    row = connection.execute(
        "SELECT revision FROM p34_authoritative_source_revision "
        "WHERE singleton_id = 1"
    ).fetchone()
    triggers = {
        item["name"]
        for item in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' "
            "AND name LIKE 'p34_source_revision_%'"
        ).fetchall()
    }
    if row is None or not _P34_SOURCE_REVISION_TRIGGERS.issubset(triggers):
        raise InvestigationAdaptationIntegrityError(
            "P34 authoritative source revision contract is unavailable"
        )
    return int(row["revision"])


def _verified_p34_stream_boundary(
    repository: InvestigationAdaptationRepository,
    connection: object,
    *,
    pre_snapshot_fingerprint: tuple[object, ...],
    pre_source_revision: int,
    strict_integrity: bool,
) -> tuple[object, tuple[object, ...], int, bool]:
    """Audit a snapshot only under a storage identity stable since before BEGIN."""

    boundary = repository.stream_state(connection=connection)
    database_file = str(pre_snapshot_fingerprint[0])
    storage_fingerprint = _repository_storage_fingerprint(database_file)
    source_revision = _authoritative_source_revision(connection)
    # The trigger-backed revision is committed in the same SQLite transaction
    # as every P34/Crew/P33/workflow source mutation.  File timestamps are only
    # diagnostics: opening a WAL reader may legitimately change sidecar stats.
    storage_stable = source_revision == pre_source_revision
    key = (
        database_file,
        source_revision,
        boundary.record_count,
        boundary.head_sha256,
    )
    main_file_available = storage_fingerprint[1] is not None
    if strict_integrity and (
        not storage_stable
        or not main_file_available
        or key not in _VERIFIED_P34_CHAIN_KEYS
    ):
        boundary = repository.stream_state(
            connection=connection,
            validate_chain=True,
            validate_payloads=False,
        )
        if main_file_available and storage_stable:
            _VERIFIED_P34_CHAIN_KEYS[key] = None
            while len(_VERIFIED_P34_CHAIN_KEYS) > 16:
                _VERIFIED_P34_CHAIN_KEYS.pop(next(iter(_VERIFIED_P34_CHAIN_KEYS)))
    return boundary, storage_fingerprint, source_revision, storage_stable


def _current_p34_chain_key(
    repository: InvestigationAdaptationRepository,
) -> tuple[object, ...] | None:
    database_file = _repository_database_file(repository)
    active = connect_read_only(repository.db_path)
    try:
        source_revision_before = _authoritative_source_revision(active)
        active.execute("BEGIN")
        boundary = repository.stream_state(connection=active)
        active.rollback()
        source_revision_after = _authoritative_source_revision(active)
    except InvestigationAdaptationIntegrityError:
        return None
    finally:
        active.close()
    if source_revision_before != source_revision_after:
        return None
    return (
        database_file,
        source_revision_after,
        boundary.record_count,
        boundary.head_sha256,
    )


def _mark_current_p34_chain_verified(
    repository: InvestigationAdaptationRepository,
) -> None:
    key = _current_p34_chain_key(repository)
    if key is None:
        return
    _VERIFIED_P34_CHAIN_KEYS[key] = None
    while len(_VERIFIED_P34_CHAIN_KEYS) > 16:
        _VERIFIED_P34_CHAIN_KEYS.pop(next(iter(_VERIFIED_P34_CHAIN_KEYS)))


def _p34_evidence_stream_boundary(
    connection: object,
    *,
    stream_record_count: int,
    max_sequence: int | None = None,
) -> tuple[int, str | None]:
    """Exclude review children so retrying a review keeps one evidence identity."""

    sequence_predicate = " AND sequence <= ?" if max_sequence is not None else ""
    sequence_parameters = (max_sequence,) if max_sequence is not None else ()
    review_count = int(
        connection.execute(
            "SELECT COUNT(*) AS value FROM investigation_adaptation_records "
            "WHERE record_kind IN ('policy_evaluation', 'activation_decision')"
            + sequence_predicate,
            sequence_parameters,
        ).fetchone()["value"]
    )
    row = connection.execute(
        "SELECT entry_sha256 FROM investigation_adaptation_records "
        "WHERE record_kind NOT IN ('policy_evaluation', 'activation_decision') "
        + sequence_predicate
        + " "
        "ORDER BY sequence DESC LIMIT 1"
        ,
        sequence_parameters,
    ).fetchone()
    return (
        (max_sequence if max_sequence is not None else stream_record_count)
        - review_count,
        row["entry_sha256"] if row is not None else None,
    )


def _authoritative_crew_lineage(
    connection: object,
    *,
    pairs: tuple[PairedInvestigationDecision, ...],
    certificates: tuple[InvestigationOutcomeCertificate, ...],
    discriminators: tuple[DiscriminatorOutcome, ...],
    followups: tuple[InvestigationOutcomeFollowup, ...],
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Cross-bind activation evidence to server-owned Crew and run registries."""

    if not pairs and not certificates and not discriminators and not followups:
        # The normal zero-comparison/readiness path must not import the whole
        # P33 telemetry intelligence graph merely to return an empty lineage.
        # This keeps the first Crew projection bounded after restart while the
        # exact authoritative machinery remains mandatory once evidence exists.
        return frozenset(), frozenset(), frozenset()

    from racelab_engine.models.crew_chief import (  # local: avoids import cycle
        CrewChiefEvent,
        CrewChiefInvestigation,
    )
    from racelab_engine.storage.crew_chief_repository import crew_chief_event_hash
    from racelab_engine.storage.engineering_learning_repository import (
        EngineeringLearningIntegrityError,
        EngineeringLearningRepository,
    )
    from racelab_engine.services.engineering_learning_service import (
        CurrentLearningInputs,
        _attention_order,
        _car_fingerprints,
        _dead_end_records,
        _driver_fingerprints,
        _investigation_records,
        _mind_change_records,
        _recurrence,
        _transfer_assessment,
    )

    active = connection

    def production_action_matches_next_event(
        pair: PairedInvestigationDecision,
        events: tuple[object, ...],
        certificate: InvestigationOutcomeCertificate,
    ) -> bool:
        next_event = next(
            (
                event
                for event in events
                if event.sequence == pair.step_number + 1
            ),
            None,
        )
        expected_source_snapshot_sha256 = (
            investigation_adaptation_source_snapshot_sha256(
                run_id=pair.run_id,
                session_id=pair.session_id,
                workspace_revision=pair.workspace_revision,
                authority_revision=pair.authority_revision,
                current_truth_sha256=pair.current_truth_sha256,
                p19_snapshot_sha256=pair.p19_snapshot_sha256,
                p20_projection_sha256=pair.p20_projection_sha256,
                p26_projection_sha256=pair.p26_projection_sha256,
                p32_projection_sha256=pair.p32_projection_sha256,
            )
        )
        if (
            next_event is None
            or next_event.created_at <= pair.decision_frozen_at
            or next_event.workspace_revision != pair.workspace_revision
            or next_event.payload.adaptation_prediction_pair_id != pair.pair_id
            or next_event.payload.adaptation_prediction_pair_sha256
            != pair.pair_sha256
            or next_event.payload.adaptation_prediction_source_snapshot_sha256
            != expected_source_snapshot_sha256
        ):
            return False
        decision = pair.production_decision
        if decision.decision_kind == "inspect_tool":
            return bool(
                next_event.event_type == "tool_invoked"
                and next_event.payload.tool_id == decision.action_id
                and next_event.event_id in certificate.tool_request_event_ids
            )
        if decision.decision_kind == "ask_driver":
            return bool(
                next_event.event_type == "driver_question_asked"
                and next_event.payload.question_id == decision.action_id
                and decision.action_id in certificate.driver_question_ids
            )
        if decision.decision_kind in {"no_call", "observe_only"}:
            if next_event.event_type != "decision_emitted":
                return False
            terminal_kind = next_event.payload.decision_kind
            expected_kind = (
                "no_call"
                if decision.decision_kind == "no_call"
                else terminal_kind
            )
            expected_action = (
                f"terminal:{terminal_kind}:"
                f"{canonical_json_sha256([terminal_kind, next_event.payload.message])[:24]}"
            )
            return bool(
                terminal_kind is not None
                and terminal_kind == expected_kind
                and decision.action_id == expected_action
            )
        return False

    def selected_rows(table: str, column: str, identities: set[str]) -> list[object]:
        rows: list[object] = []
        ordered = sorted(identities)
        for offset in range(0, len(ordered), 500):
            chunk = ordered[offset : offset + 500]
            placeholders = ",".join("?" for _ in chunk)
            rows.extend(
                active.execute(
                    f"SELECT * FROM {table} WHERE {column} IN ({placeholders})",
                    chunk,
                ).fetchall()
            )
        return rows

    investigation_ids = {item.investigation_id for item in pairs}
    investigation_rows = {
        row["investigation_id"]: row
        for row in selected_rows(
            "crew_chief_investigations", "investigation_id", investigation_ids
        )
    }
    event_rows: list[object] = []
    ordered_investigations = sorted(investigation_ids)
    for offset in range(0, len(ordered_investigations), 500):
        chunk = ordered_investigations[offset : offset + 500]
        placeholders = ",".join("?" for _ in chunk)
        event_rows.extend(
            active.execute(
                "SELECT * FROM crew_chief_events WHERE investigation_id IN ("
                f"{placeholders}) ORDER BY investigation_id, sequence",
                chunk,
            ).fetchall()
        )
    event_rows_by_investigation: dict[str, list[object]] = {}
    for row in event_rows:
        event_rows_by_investigation.setdefault(row["investigation_id"], []).append(row)
    run_ids = {
        row["run_id"]
        for row in selected_rows("runs", "run_id", {item.run_id for item in pairs})
    }
    terminal_experience_ids: set[str] = set()
    for row in event_rows:
        if (
            row["event_type"]
            not in {"decision_emitted", "investigation_abandoned"}
        ):
            continue
        try:
            terminal_probe = CrewChiefEvent.model_validate_json(row["event_json"])
        except (TypeError, ValueError):
            continue
        if terminal_probe.payload.learning_capture_experience_id is not None:
            terminal_experience_ids.add(
                terminal_probe.payload.learning_capture_experience_id
            )
    consulted_ids = {
        record_id for pair in pairs for record_id in pair.memory_records_consulted
    }
    future_ids = {
        record_id for pair in pairs for record_id in pair.future_memory_record_ids
    }
    control_ids = {
        record_id
        for pair in pairs
        if pair.negative_control_evidence is not None
        for record_id in (
            *pair.negative_control_evidence.context_transfer_record_ids,
            *pair.negative_control_evidence.useful_prior_experience_ids,
            *pair.negative_control_evidence.component_history_experience_ids,
            *pair.negative_control_evidence.future_memory_record_ids,
        )
    }
    p33_evidence_ids = (
        consulted_ids | future_ids | control_ids | terminal_experience_ids
    )
    experience_rows = {
        row["experience_id"]: row
        for row in selected_rows(
            "engineering_experiences", "experience_id", p33_evidence_ids
        )
    }
    p33_prefixes: dict[str, tuple[int, str]] = {}
    validated_experiences: dict[str, object] = {}
    p33_rows_valid = True
    if p33_evidence_ids:
        try:
            EngineeringLearningRepository._stream_state(
                active,
                # P34 validates every exact selected prefix/source row below.
                # A corrupt unrelated P33 tail must not hide a clean current
                # investigation or rewrite its preregistered evaluation.
                validate_chain=False,
            )
            for record_id, row in experience_rows.items():
                record = EngineeringLearningRepository._validate_row(row)
                if record.experience_id != record_id:
                    raise EngineeringLearningIntegrityError(
                        "P34 consulted P33 identity is corrupt"
                    )
                validated_experiences[record_id] = record
            for head_sha256 in {
                pair.p33_ledger_head_sha256
                for pair in pairs
                if pair.p33_ledger_head_sha256 is not None
            }:
                prefix = active.execute(
                    "SELECT sequence FROM engineering_experiences "
                    "WHERE entry_sha256 = ?",
                    (head_sha256,),
                ).fetchone()
                if prefix is not None:
                    p33_prefixes[head_sha256] = (
                        int(prefix["sequence"]),
                        canonical_json_sha256(
                            {
                                "schema_version": "p33.engineering-experience.v1",
                                "record_count": int(prefix["sequence"]),
                                "head_sha256": head_sha256,
                            }
                        ),
                    )
        except (EngineeringLearningIntegrityError, TypeError, ValueError):
            p33_rows_valid = False
    certificates_by_investigation = {
        item.investigation_id: item for item in certificates
    }
    pairs_by_investigation: dict[str, list[PairedInvestigationDecision]] = {}
    for pair in pairs:
        pairs_by_investigation.setdefault(pair.investigation_id, []).append(pair)
    authoritative_cases: set[str] = set()
    authoritative_discriminators: set[str] = set()
    authoritative_followups: set[str] = set()
    parsed_events: dict[str, dict[str, CrewChiefEvent]] = {}
    relevant_p33_cache: dict[
        tuple[int, str, str], tuple[tuple[object, ...], tuple[str, ...]]
    ] = {}

    def relevant_p33_records_as_of(
        current_record: object,
        *,
        max_sequence: int,
    ) -> tuple[tuple[object, ...], tuple[str, ...]]:
        context = current_record.context
        problem = current_record.problem
        key = (max_sequence, context.context_sha256, problem.problem_sha256)
        cached = relevant_p33_cache.get(key)
        if cached is not None:
            return cached
        branches: list[tuple[str, tuple[object, ...]]] = [
            (
                "context_sha256 = ? AND objective = ? AND phase = ?",
                (context.context_sha256, context.objective, context.phase),
            ),
            (
                "car_path = ? AND car_version = ? AND iracing_build = ? "
                "AND track = ? AND track_configuration = ? AND phase = ?",
                (
                    context.car_path,
                    context.car_version,
                    context.iracing_build,
                    context.track,
                    context.track_configuration,
                    context.phase,
                ),
            ),
            ("problem_sha256 = ?", (problem.problem_sha256,)),
        ]
        if context.driver_id is not None:
            branches.append(
                (
                    "driver_id = ? AND car_path = ? AND car_version = ? "
                    "AND iracing_build = ? AND phase = ?",
                    (
                        context.driver_id,
                        context.car_path,
                        context.car_version,
                        context.iracing_build,
                        context.phase,
                    ),
                )
            )
        selected: dict[str, object] = {}
        for predicate, parameters in branches:
            rows = active.execute(
                "SELECT * FROM engineering_experiences WHERE sequence <= ? AND "
                f"{predicate} ORDER BY created_at DESC, experience_id LIMIT 128",
                (max_sequence, *parameters),
            ).fetchall()
            for candidate in rows:
                selected.setdefault(candidate["experience_id"], candidate)
        ordered = sorted(
            selected.values(),
            key=lambda candidate: (
                candidate["created_at"],
                candidate["experience_id"],
            ),
            reverse=True,
        )[:128]
        validated: list[object] = []
        blockers: list[str] = []
        for candidate in ordered:
            try:
                validated.append(
                    EngineeringLearningRepository._validate_row(candidate)
                )
            except EngineeringLearningIntegrityError as exc:
                blockers.append(
                    f"Experience {candidate['experience_id']} withheld: {exc}"
                )
        result = (tuple(validated), tuple(blockers))
        relevant_p33_cache[key] = result
        return result

    for investigation_id, cohort in pairs_by_investigation.items():
        row = investigation_rows.get(investigation_id)
        certificate = certificates_by_investigation.get(investigation_id)
        if row is None or certificate is None:
            continue
        try:
            investigation = CrewChiefInvestigation.model_validate_json(
                row["investigation_json"]
            )
            canonical_pair = canonical_investigation_evaluation_pair(cohort)
            all_event_rows = event_rows_by_investigation.get(investigation_id, ())
            terminal_candidates = tuple(
                item
                for item in all_event_rows
                if item["event_type"] in {"decision_emitted", "investigation_abandoned"}
            )
            if len(terminal_candidates) != 1:
                continue
            relevant_rows = {item["event_id"]: item for item in all_event_rows}
            events = {
                event_id: CrewChiefEvent.model_validate_json(item["event_json"])
                for event_id, item in relevant_rows.items()
            }
        except (TypeError, ValueError):
            continue
        terminal_event = events.get(terminal_candidates[0]["event_id"])
        if terminal_event is None:
            continue
        terminal_experience = (
            validated_experiences.get(
                terminal_event.payload.learning_capture_experience_id
            )
            if terminal_event.payload.learning_capture_experience_id is not None
            else None
        )
        event_rows_valid = all(
            event.event_id == event_id
            and event.investigation_id == investigation_id
            and event.workspace_revision == relevant_rows[event_id]["workspace_revision"]
            and event.created_at.isoformat() == relevant_rows[event_id]["created_at"]
            and event.event_hash == relevant_rows[event_id]["event_hash"]
            and event.event_type == relevant_rows[event_id]["event_type"]
            and crew_chief_event_hash(event) == event.event_hash
            for event_id, event in events.items()
        )
        ordered_events = tuple(sorted(events.values(), key=lambda item: item.sequence))
        complete_stream = (
            len(ordered_events) == len(relevant_rows)
            and tuple(item.sequence for item in ordered_events)
            == tuple(range(1, len(ordered_events) + 1))
            and len({item.event_id for item in ordered_events}) == len(ordered_events)
        )
        production_action_executed = production_action_matches_next_event(
            canonical_pair,
            ordered_events,
            certificate,
        )
        opening_identity = investigation.workspace_identity
        opening_truth_bound = bool(
            canonical_pair.workspace_revision == opening_identity.workspace_revision
            and canonical_pair.authority_revision == opening_identity.authority_revision
            and canonical_pair.p19_snapshot_sha256
            == opening_identity.reasoning_snapshot_sha256
            and canonical_pair.p20_projection_sha256
            == opening_identity.p20_state_revision
            and canonical_pair.p26_projection_sha256
            == opening_identity.p26_knowledge_graph_sha256
            and canonical_pair.p32_projection_sha256
            == opening_identity.p32_projection_sha256
        )
        # V1 credits only the immutable opening authority.  A rebase event
        # changes the event-head-derived workspace/current-truth identities,
        # and its pre-event marker cannot independently authenticate the later
        # pair's complete projection.  Post-rebase pairs remain descriptive.
        source_revision_bound = opening_truth_bound
        source_problem_family = (
            classify_p34_problem_family(
                phase=terminal_experience.problem.phase,
                objective=terminal_experience.context.objective,
                driver_demand_state=(
                    terminal_experience.problem.driver_demand_state
                ),
                vehicle_response_state=(
                    terminal_experience.problem.vehicle_response_state
                ),
            )
            if terminal_experience is not None
            else None
        )
        source_problem_orientation = (
            classify_p34_problem_orientation(
                driver_demand_state=(
                    terminal_experience.problem.driver_demand_state
                ),
                vehicle_response_state=(
                    terminal_experience.problem.vehicle_response_state
                ),
            )
            if terminal_experience is not None
            else None
        )
        source_track_class = (
            classify_p34_track_class(
                track=terminal_experience.context.track,
                track_configuration=(
                    terminal_experience.context.track_configuration
                ),
                package_type=terminal_experience.context.package_type,
            )
            if terminal_experience is not None
            else None
        )
        terminal_current_truth_bound = bool(
            terminal_event.payload.learning_capture_state == "captured"
            and terminal_experience is not None
            and terminal_experience.experience_id
            == terminal_event.payload.learning_capture_experience_id
            and terminal_experience.experience_sha256
            == terminal_event.payload.learning_capture_experience_sha256
            and terminal_experience.source_kind == "resolved_investigation"
            and terminal_experience.source_investigation_id == investigation_id
            and terminal_experience.created_at == terminal_event.created_at
            and terminal_experience.source_event_ids
            == tuple(item.event_id for item in ordered_events)
            and terminal_experience.context.run_id == canonical_pair.run_id
            and terminal_experience.context.session_id == canonical_pair.session_id
            and terminal_experience.context.context_sha256
            == canonical_pair.p33_context_sha256
            and terminal_experience.problem.problem_sha256
            == canonical_pair.p33_problem_sha256
            and terminal_experience.context.track == canonical_pair.track
            and terminal_experience.context.track_configuration
            == canonical_pair.track_configuration
            and terminal_experience.context.package_type
            == canonical_pair.package_type
            and terminal_experience.context.iracing_build
            == canonical_pair.iracing_build
            and terminal_experience.context.objective
            == canonical_pair.current_objective
            and terminal_experience.context.phase == canonical_pair.phase
            and terminal_experience.problem.phase == canonical_pair.phase
            and canonical_pair.problem_family == source_problem_family
            and canonical_pair.problem_orientation == source_problem_orientation
            and canonical_pair.track_class == source_track_class
            and terminal_experience.opening_reasoning
            == investigation.opening_reasoning
            and terminal_experience.problem == investigation.opening_problem
            and (
                terminal_experience.source_p32_projection_sha256 is None
                or terminal_experience.source_p32_projection_sha256
                == canonical_pair.p32_projection_sha256
            )
            and canonical_pair.current_p19_cause_ids
            == tuple(
                item.cause_id for item in investigation.opening_reasoning.causes
            )
            and canonical_pair.current_p19_cause_states
            == tuple(
                P19CauseState(cause_id=item.cause_id, state=item.status)
                for item in investigation.opening_reasoning.causes
            )
        )
        if (
            investigation.investigation_id != investigation_id
            or investigation.workspace_identity.run_id != row["run_id"]
            or investigation.workspace_identity.session_id != row["session_id"]
            or investigation.workspace_identity.workspace_revision
            != row["workspace_revision"]
            or investigation.opened_at.isoformat() != row["opened_at"]
            or canonical_pair.run_id != row["run_id"]
            or canonical_pair.session_id != row["session_id"]
            or canonical_pair.run_id not in run_ids
            or canonical_pair.investigation_opened_at != investigation.opened_at
            or certificate.investigation_opened_at != investigation.opened_at
            or certificate.starting_workspace_revision
            != investigation.workspace_identity.workspace_revision
            or not event_rows_valid
            or not complete_stream
            or not production_action_executed
            or not source_revision_bound
            or not terminal_current_truth_bound
            or int(row["event_count"]) != terminal_event.sequence
            or len(ordered_events) != terminal_event.sequence
            or row["event_head_hash"] != terminal_event.event_hash
        ):
            continue
        requests = tuple(
            events.get(event_id) for event_id in certificate.tool_request_event_ids
        )
        results = tuple(
            events.get(event_id) for event_id in certificate.tool_result_event_ids
        )
        if any(event is None for event in (*requests, *results)):
            continue
        payload = terminal_event.payload
        result_artifact_ids = {
            artifact_id
            for event in results
            for artifact_id in event.payload.artifact_ids
        }
        empty_p33_revision = canonical_json_sha256(
            {
                "schema_version": "p33.engineering-experience.v1",
                "record_count": 0,
                "head_sha256": None,
            }
        )
        prefix = (
            p33_prefixes.get(canonical_pair.p33_ledger_head_sha256)
            if canonical_pair.p33_ledger_head_sha256 is not None
            else None
        )
        prefix_sequence = prefix[0] if prefix is not None else 0
        later_predecision_row = active.execute(
            "SELECT 1 FROM engineering_experiences "
            "WHERE sequence > ? AND created_at <= ? LIMIT 1",
            (
                prefix_sequence,
                canonical_pair.decision_frozen_at.isoformat(),
            ),
        ).fetchone()
        history_prefix_exact = bool(
            p33_rows_valid
            and later_predecision_row is None
            and (
                (
                    canonical_pair.p33_ledger_head_sha256 is None
                    and canonical_pair.p33_history_revision == empty_p33_revision
                )
                or (
                    prefix is not None
                    and prefix[1] == canonical_pair.p33_history_revision
                )
            )
        )
        consulted_records = tuple(
            validated_experiences.get(record_id)
            for record_id in canonical_pair.memory_records_consulted
        )
        memory_is_prior = bool(
            history_prefix_exact
            and all(record is not None for record in consulted_records)
            and all(
                int(experience_rows[record_id]["sequence"]) <= prefix_sequence
                and datetime.fromisoformat(experience_rows[record_id]["created_at"])
                < canonical_pair.decision_frozen_at
                for record_id in canonical_pair.memory_records_consulted
            )
        )
        transfer_assessments = tuple(
            _transfer_assessment(terminal_experience.context, record)
            for record in consulted_records
            if record is not None
        )
        relevant_records, relevant_p33_blockers = relevant_p33_records_as_of(
            terminal_experience,
            max_sequence=prefix_sequence,
        )
        relevant_transfer_by_id = {
            record.experience_id: _transfer_assessment(
                terminal_experience.context,
                record,
            )
            for record in relevant_records
        }
        relevant_by_id = {
            record.experience_id: record for record in relevant_records
        }
        projected_investigations = _investigation_records(
            relevant_records,
            relevant_transfer_by_id,
        )
        projected_dead_ends = _dead_end_records(
            relevant_records,
            relevant_transfer_by_id,
        )
        attention = _attention_order(
            projected_investigations,
            relevant_by_id,
        )
        eligible_attention = tuple(
            item
            for item in attention
            if item.tool_id in canonical_pair.eligible_tool_ids
        )
        selected_attention = (
            min(
                eligible_attention,
                key=lambda item: (
                    item.learned_rank_within_band,
                    item.baseline_rank_within_band,
                    item.tool_id,
                ),
            )
            if eligible_attention
            else None
        )
        transfer_claim_exact = {
            "none": not canonical_pair.memory_records_consulted,
            "exact": bool(transfer_assessments)
            and all(item.level == "exact" for item in transfer_assessments),
            "compatible": bool(transfer_assessments)
            and all(
                item.level in {"exact", "compatible"}
                for item in transfer_assessments
            )
            and any(item.level == "compatible" for item in transfer_assessments),
            "weak": False,
            "blocked": False,
        }[canonical_pair.context_transfer_class]
        future_memory_is_exact = (
            not canonical_pair.future_memory_record_ids
            or (
                p33_rows_valid
                and all(
                    (future_row := experience_rows.get(record_id)) is not None
                    and datetime.fromisoformat(future_row["created_at"])
                    >= canonical_pair.decision_frozen_at
                    for record_id in canonical_pair.future_memory_record_ids
                )
            )
        )
        current_learning = CurrentLearningInputs(
            context=terminal_experience.context,
            problem=terminal_experience.problem,
            reasoning=investigation.opening_reasoning,
            source_provenance=terminal_experience.source_provenance,
            performance_response=terminal_experience.performance_response,
            driver_contributions=terminal_experience.driver_contributions,
        )
        control_assessments = tuple(
            relevant_transfer_by_id[record.experience_id]
            for record in relevant_records
        )
        projected_drivers = _driver_fingerprints(
            current_learning,
            relevant_records,
            relevant_transfer_by_id,
        )
        projected_cars = _car_fingerprints(
            relevant_records,
            relevant_transfer_by_id,
        )
        projected_mind_changes = _mind_change_records(
            relevant_records,
            relevant_transfer_by_id,
        )
        projected_recurrence = _recurrence(
            current_learning,
            relevant_records,
            relevant_transfer_by_id,
        )
        expected_useful_ids = tuple(
            item.experience_id for item in projected_investigations
        )
        expected_component_ids = tuple(
            dict.fromkeys(
                experience_id
                for item in projected_cars
                for experience_id in item.source_experience_ids
            )
        )
        expected_physical_mismatches = tuple(
            dict.fromkeys(
                dimension
                for item in control_assessments
                if item.level == "weak"
                for dimension in item.mismatched_dimensions
                if dimension in P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS
            )
        )
        expected_future = tuple(
            (item.experience_id, item.outcome.completed_at)
            for item in projected_investigations
            if item.outcome.completed_at >= canonical_pair.decision_frozen_at
        )
        expected_driver_state = (
            "material_drift"
            if any(item.state == "changed_behavior" for item in projected_drivers)
            else "stable"
            if control_assessments
            and all(
                not item.drift_reasons
                and "driver_execution_state" in item.matching_dimensions
                and "driver_execution_state" not in item.mismatched_dimensions
                for item in control_assessments
            )
            else "unknown"
        )
        expected_p33_state = (
            "blocked"
            if relevant_p33_blockers
            else "available"
            if (
                projected_investigations
                or projected_dead_ends
                or projected_drivers
                or projected_cars
                or projected_mind_changes
            )
            else "insufficient_history"
        )
        expected_corruption_blockers = tuple(
            canonical_json_sha256(item) for item in relevant_p33_blockers
        )
        physical_mismatches = set(expected_physical_mismatches)
        transfer_levels = tuple(item.level for item in control_assessments)
        expected_negative_control = (
            "future_memory_record"
            if expected_future
            else "material_driver_drift"
            if expected_driver_state == "material_drift"
            else "corrupt_history"
            if relevant_p33_blockers
            else "incompatible_history"
            if (
                "blocked" in transfer_levels
                and canonical_pair.build_review_state
                != "future_unreviewed_build"
                and expected_driver_state == "stable"
            )
            else "generic_component_knowledge_only"
            if (
                "weak" in transfer_levels
                and canonical_pair.problem_orientation == "vehicle"
                and bool(expected_component_ids)
                and not expected_useful_ids
                and not physical_mismatches
            )
            else "same_words_different_physical_scope"
            if (
                "weak" in transfer_levels
                and bool(physical_mismatches)
                and projected_recurrence.classification != "new_problem"
            )
            else "no_relevant_history"
            if (
                not relevant_records
                and not relevant_p33_blockers
                and not expected_useful_ids
                and not transfer_levels
            )
            else None
        )
        expected_build_state = (
            "future_unreviewed_build"
            if any(
                "iRacing_build" in item.mismatched_dimensions
                for item in control_assessments
            )
            else "same_build"
        )
        baseline_is_pinned = bool(
            canonical_pair.baseline_decision.decision_kind == "inspect_tool"
            and canonical_pair.baseline_decision.action_id
            in canonical_pair.current_evidence_pinned_tool_ids
        )
        if baseline_is_pinned:
            # Qualified current evidence is the separately preregistered
            # Scenario-C guard.  It pins the deterministic action and is not
            # simultaneously relabelled as a P33 absence/control case.
            expected_negative_control = None
        selected_attention_is_executable = bool(
            selected_attention is not None
            and (
                selected_attention.tool_id
                == canonical_pair.baseline_decision.action_id
                or (
                    len(canonical_pair.eligible_tool_ids) == 2
                    and selected_attention.tool_id
                    == canonical_pair.eligible_tool_ids[1]
                    and selected_attention.learned_rank_within_band
                    < selected_attention.baseline_rank_within_band
                )
            )
        )
        if baseline_is_pinned:
            expected_memory_action_id = canonical_pair.baseline_decision.action_id
            expected_memory_ids: tuple[str, ...] = ()
            expected_transfer_class = "blocked"
        elif expected_negative_control is not None:
            expected_memory_action_id = canonical_pair.baseline_decision.action_id
            expected_memory_ids = ()
            expected_transfer_class = {
                "no_relevant_history": "none",
                "generic_component_knowledge_only": "weak",
                "same_words_different_physical_scope": "weak",
                "incompatible_history": "blocked",
                "corrupt_history": "blocked",
                "material_driver_drift": "blocked",
                "future_memory_record": "blocked",
            }[expected_negative_control]
        elif (
            expected_build_state == "future_unreviewed_build"
            or expected_driver_state != "stable"
            or canonical_pair.baseline_decision.action_id
            == "inspect_driver_vehicle_separation"
        ):
            expected_memory_action_id = canonical_pair.baseline_decision.action_id
            expected_memory_ids = ()
            expected_transfer_class = "blocked"
        elif selected_attention_is_executable and selected_attention is not None:
            expected_memory_action_id = selected_attention.tool_id
            expected_memory_ids = selected_attention.source_experience_ids
            expected_transfer_class = selected_attention.transfer_level
        else:
            expected_memory_action_id = canonical_pair.baseline_decision.action_id
            expected_memory_ids = ()
            expected_transfer_class = (
                "weak" if "weak" in transfer_levels else "none"
            )
        memory_attention_exact = bool(
            canonical_pair.memory_decision.decision_kind
            == canonical_pair.baseline_decision.decision_kind
            and canonical_pair.memory_decision.action_id
            == expected_memory_action_id
            and canonical_pair.memory_records_consulted == expected_memory_ids
            and canonical_pair.context_transfer_class == expected_transfer_class
        )
        control = canonical_pair.negative_control_evidence
        control_is_source_owned = bool(
            (control is None) == (expected_negative_control is None)
            and canonical_pair.negative_control_condition
            == expected_negative_control
        )
        if control is not None:
            complete_projection_facts = bool(
                control.context_transfer_record_ids
                == tuple(item.experience_id for item in control_assessments)
                and control.context_transfer_levels
                == tuple(item.level for item in control_assessments)
                and control.useful_prior_experience_ids == expected_useful_ids
                and control.component_history_experience_ids
                == expected_component_ids
                and control.physical_scope_mismatch_dimensions
                == expected_physical_mismatches
                and control.recurrence_class
                == projected_recurrence.classification
                and control.corruption_blocker_sha256s
                == expected_corruption_blockers
                and control.future_memory_record_ids
                == tuple(item[0] for item in expected_future)
                and control.future_memory_record_completed_ats
                == tuple(item[1] for item in expected_future)
                and control.driver_drift_state == expected_driver_state
                and control.p33_state == expected_p33_state
            )
            control_is_source_owned = bool(
                control.p33_projection_sha256
                == canonical_pair.p33_projection_sha256
                and control.condition == expected_negative_control
                and complete_projection_facts
                and {
                    "no_relevant_history": not relevant_records
                    and not relevant_p33_blockers,
                    "incompatible_history": "blocked"
                    in control.context_transfer_levels,
                    "corrupt_history": bool(relevant_p33_blockers),
                    "generic_component_knowledge_only": bool(
                        expected_component_ids
                    )
                    and not expected_useful_ids,
                    "same_words_different_physical_scope": bool(
                        physical_mismatches
                    )
                    and set(control.physical_scope_mismatch_dimensions)
                    == physical_mismatches,
                    "material_driver_drift": (
                        expected_driver_state == "material_drift"
                    ),
                    "future_memory_record": bool(
                        control.future_memory_record_ids
                    ),
                }[control.condition]
            )
            if canonical_pair.context_transfer_class == "weak":
                transfer_claim_exact = bool(
                    control_is_source_owned
                    and "weak" in control.context_transfer_levels
                )
            elif canonical_pair.context_transfer_class == "blocked":
                transfer_claim_exact = bool(
                    control_is_source_owned
                    and (
                        "blocked" in control.context_transfer_levels
                        or control.condition == "future_memory_record"
                        or control.condition == "corrupt_history"
                        or control.condition == "material_driver_drift"
                    )
                )
        # The complete P33 prefix above is the authority for both learned
        # reorders and deterministic fallbacks.  In particular, an exact
        # current-evidence pin, an unreviewed build, driver drift, or the
        # mandatory driver/vehicle-separation gate can truthfully require a
        # blocked baseline fallback without a negative-control artifact.
        # Do not leave those source-owned fallbacks impossible merely because
        # the earlier provisional transfer check intentionally rejected every
        # bare ``blocked`` claim.
        transfer_claim_exact = bool(
            memory_attention_exact and control_is_source_owned
        )
        if (
            payload.adaptation_capture_state != "captured"
            or payload.adaptation_capture_certificate_id != certificate.certificate_id
            or payload.adaptation_capture_certificate_sha256
            != certificate.certificate_sha256
            or certificate.pair_id != canonical_pair.pair_id
            or certificate.pair_sha256 != canonical_pair.pair_sha256
            or certificate.ending_workspace_revision != terminal_event.workspace_revision
            or certificate.certified_at != terminal_event.created_at
            or certificate.tool_request_event_ids
            != tuple(event.event_id for event in requests)
            or certificate.tools_actually_requested
            != tuple(event.payload.tool_id for event in requests)
            or certificate.tool_result_event_ids
            != tuple(event.event_id for event in results)
            or certificate.tool_results_received
            != tuple(event.payload.tool_id for event in results)
            or not set(certificate.qualified_artifact_ids).issubset(
                result_artifact_ids
            )
            or not memory_is_prior
            or not history_prefix_exact
            or not transfer_claim_exact
            or not memory_attention_exact
            or canonical_pair.build_review_state != expected_build_state
            or canonical_pair.driver_drift_state != expected_driver_state
            or not future_memory_is_exact
            or not control_is_source_owned
        ):
            continue
        authoritative_cases.add(investigation_id)
        parsed_events[investigation_id] = events
    for discriminator in discriminators:
        events = parsed_events.get(discriminator.investigation_id, {})
        request = events.get(discriminator.request_event_id)
        result = events.get(discriminator.result_event_id)
        prediction_pair = next(
            (
                item
                for item in pairs
                if item.pair_id == discriminator.prediction_pair_id
            ),
            None,
        )
        source_pair = next(
            (item for item in pairs if item.pair_id == discriminator.source_pair_id),
            None,
        )
        certificate = certificates_by_investigation.get(
            discriminator.investigation_id
        )
        try:
            expected = (
                build_discriminator_outcome_from_crew_events(
                    prediction_pair=prediction_pair,
                    source_pair=source_pair,
                    certificate=certificate,
                    request_event=request,
                    result_event=result,
                    investigation_events=tuple(events.values()),
                    transition_sequence=discriminator.transition_sequence,
                    evaluated_at=discriminator.evaluated_at,
                )
                if prediction_pair is not None
                and source_pair is not None
                and certificate is not None
                and request is not None
                and result is not None
                else None
            )
        except (TypeError, ValueError):
            expected = None
        terminal_event = next(
            (
                item
                for item in events.values()
                if item.event_type in {"decision_emitted", "investigation_abandoned"}
            ),
            None,
        )
        terminal_experience = (
            validated_experiences.get(
                terminal_event.payload.learning_capture_experience_id
            )
            if terminal_event is not None
            and terminal_event.payload.learning_capture_experience_id is not None
            else None
        )
        mind_change = getattr(terminal_experience, "mind_change", None)
        outcome = getattr(terminal_experience, "investigation_outcome", None)
        provenance = {
            item.artifact_id: item
            for item in getattr(terminal_experience, "source_provenance", ())
        }
        mind_change_evidence = (
            dict(
                zip(
                    mind_change.new_artifact_ids,
                    mind_change.new_evidence_states,
                    strict=True,
                )
            )
            if mind_change is not None
            else {}
        )
        discriminated_causes = set(
            (
                *(getattr(mind_change, "causes_promoted", ())),
                *(getattr(mind_change, "causes_demoted", ())),
                *(getattr(mind_change, "causes_ruled_out", ())),
            )
        )
        terminal_proof = bool(
            terminal_event is not None
            and terminal_event.payload.learning_capture_state == "captured"
            and terminal_experience is not None
            and terminal_experience.experience_id
            == terminal_event.payload.learning_capture_experience_id
            and terminal_experience.experience_sha256
            == terminal_event.payload.learning_capture_experience_sha256
            and terminal_experience.source_investigation_id
            == discriminator.investigation_id
            and outcome is not None
            and discriminator.tool_id in outcome.successful_discriminator_ids
            and mind_change is not None
            and mind_change.evidence_discriminated
            and mind_change.measurement_discriminator_id == discriminator.tool_id
            and mind_change.before_reasoning.reasoning_snapshot_sha256
            == discriminator.before_p19_snapshot_sha256
            and mind_change.after_reasoning.reasoning_snapshot_sha256
            == discriminator.after_p19_snapshot_sha256
            and set(discriminator.relevant_ambiguity_ids).issubset(
                discriminated_causes
            )
            and all(
                artifact_id in mind_change_evidence
                and artifact_id in provenance
                and mind_change_evidence[artifact_id] == evidence_state
                and provenance[artifact_id].evidence_state.value == evidence_state
                for artifact_id, evidence_state in zip(
                    discriminator.artifact_ids,
                    discriminator.qualified_evidence_states,
                    strict=True,
                )
            )
        )
        if expected == discriminator and terminal_proof:
            authoritative_discriminators.add(discriminator.outcome_id)
    workflow_ids = {
        item.source_workflow_id
        for item in followups
        if item.source_workflow_id is not None
    }
    workflow_rows = {
        row["workflow_id"]: row
        for row in selected_rows("controlled_workflows", "workflow_id", workflow_ids)
    }
    if followups:
        from racelab_engine.analysis.test_director import score_test_execution
        from racelab_engine.storage.repository import RaceLabRepository

        certificates_by_id = {
            item.certificate_id: item for item in certificates
        }
        for followup in followups:
            certificate = certificates_by_id.get(followup.certificate_id)
            row = (
                workflow_rows.get(followup.source_workflow_id)
                if followup.source_workflow_id is not None
                else None
            )
            if certificate is None or row is None:
                continue
            try:
                workflow = RaceLabRepository._controlled_workflow_from_row(row)
                binding = workflow.reproduction_snapshot.get(
                    "p19_authority_binding"
                )
                exact = bool(
                    isinstance(binding, dict)
                    and workflow.status == "scored"
                    and workflow.execution is not None
                    and workflow.quality is not None
                    and workflow.quality.protocol_valid
                    and workflow.quality.verdict in {"keep", "undo", "retest"}
                    and score_test_execution(workflow.execution) == workflow.quality
                    and workflow.workflow_id in certificate.created_workflow_ids
                    and followup.certificate_sha256
                    == certificate.certificate_sha256
                    and followup.investigation_id
                    == certificate.investigation_id
                    and followup.source_workflow_revision_sha256
                    == canonical_json_sha256(workflow.model_dump(mode="json"))
                    and followup.observed_p19_outcome == workflow.quality.verdict
                    and followup.observed_p19_snapshot_sha256
                    == binding.get("reasoning_snapshot_sha256")
                    and followup.source_event_ids
                    == tuple(binding.get("source_event_ids") or ())
                    and followup.source_artifact_ids == ()
                    and followup.observed_at == workflow.updated_at
                    and followup.observed_at > certificate.certified_at
                )
            except (TypeError, ValueError):
                exact = False
            if exact:
                authoritative_followups.add(followup.followup_id)
    return (
        frozenset(authoritative_cases),
        frozenset(authoritative_discriminators),
        frozenset(authoritative_followups),
    )


def _canonical_activation_evaluation_matches(
    repository: InvestigationAdaptationRepository,
    evaluation: InvestigationPolicyEvaluation,
) -> bool:
    """Rebuild an activation evaluation from its exact immutable evidence prefix."""

    if evaluation.ledger_head_sha256 is None or evaluation.ledger_record_count < 1:
        return False
    active = connect_read_only(repository.db_path)
    try:
        rows = active.execute(
            "SELECT sequence FROM investigation_adaptation_records "
            "WHERE entry_sha256 = ? "
            "AND record_kind NOT IN ('policy_evaluation', 'activation_decision') "
            "LIMIT 2",
            (evaluation.ledger_head_sha256,),
        ).fetchall()
        if len(rows) != 1:
            return False
        max_sequence = int(rows[0]["sequence"])
        evidence_count = int(
            active.execute(
                "SELECT COUNT(*) AS value "
                "FROM investigation_adaptation_records "
                "WHERE sequence <= ? "
                "AND record_kind NOT IN "
                "('policy_evaluation', 'activation_decision')",
                (max_sequence,),
            ).fetchone()["value"]
        )
        if evidence_count != evaluation.ledger_record_count:
            return False
    finally:
        active.close()
    try:
        canonical = evaluate_p34_repository(
            repository,
            evaluated_at=evaluation.evaluated_at,
            _evidence_max_sequence=max_sequence,
            strict_integrity=True,
        )
    except (InvestigationAdaptationIntegrityError, ValueError):
        return False
    return canonical == evaluation


def evaluate_p34_repository(
    repository: InvestigationAdaptationRepository,
    *,
    evaluated_at: datetime | None = None,
    _evidence_max_sequence: int | None = None,
    strict_integrity: bool = False,
) -> InvestigationPolicyEvaluation:
    database_file = _repository_database_file(repository)
    pre_snapshot_fingerprint = _repository_storage_fingerprint(database_file)
    active = connect_read_only(repository.db_path)
    pre_snapshot_data_version = int(
        active.execute("PRAGMA data_version").fetchone()[0]
    )
    pre_source_revision = _authoritative_source_revision(active)
    records: list[object] = []
    blockers: list[str] = []
    cache_key: tuple[object, ...] | None = None
    snapshot_stable = False
    storage_stable = False
    try:
        active.execute("BEGIN")
        protocol = p34_activation_protocol()
        (
            boundary,
            storage_fingerprint,
            source_revision,
            storage_stable,
        ) = _verified_p34_stream_boundary(
            repository,
            active,
            pre_snapshot_fingerprint=pre_snapshot_fingerprint,
            pre_source_revision=pre_source_revision,
            strict_integrity=strict_integrity,
        )
        cache_read_safe = bool(
            storage_stable
            and int(active.execute("PRAGMA data_version").fetchone()[0])
            == pre_snapshot_data_version
        )
        if (
            _evidence_max_sequence is not None
            and _evidence_max_sequence > boundary.record_count
        ):
            raise InvestigationAdaptationIntegrityError(
                "P34 historical evaluation boundary exceeds the verified ledger"
            )
        if (
            evaluated_at is None
            and _evidence_max_sequence is None
            and cache_read_safe
        ):
            cache_key = (
                database_file,
                protocol.protocol_id,
                boundary.ledger_revision,
                source_revision,
                strict_integrity,
            )
            cached = _REPOSITORY_EVALUATION_CACHE.get(cache_key)
            if cached is not None:
                return cached
        records.extend(
            repository.query_records_by_ids(
                (
                    baseline_investigation_policy().policy_id,
                    memory_shadow_investigation_policy().policy_id,
                    limited_attention_investigation_policy().policy_id,
                    protocol.protocol_id,
                ),
                max_sequence=_evidence_max_sequence,
                connection=active,
            )
        )
        evaluation_record_kinds = (
            "outcome_certificate",
            "outcome_followup",
            "discriminator_outcome",
            "paired_comparison",
            "negative_transfer",
            "negative_control_result",
        )
        capacity_overflow = repository.evaluation_capacity_overflow(
            protocol_id=protocol.protocol_id,
            record_kinds=evaluation_record_kinds,
            max_sequence=_evidence_max_sequence,
            connection=active,
        )
        for record_kind in evaluation_record_kinds:
            result = repository.query_records(
                record_kinds=(record_kind,),
                protocol_id=protocol.protocol_id,
                max_sequence=_evidence_max_sequence,
                limit=10_000,
                connection=active,
            )
            records.extend(result.records)
            blockers.extend(result.blockers)
        comparison_investigation_ids = tuple(
            dict.fromkeys(
                item.investigation_id
                for item in records
                if isinstance(item, PairedInvestigationComparison)
            )
        )
        canonical_pairs = repository.query_canonical_pairs(
            protocol_id=protocol.protocol_id,
            investigation_ids=comparison_investigation_ids,
            max_sequence=_evidence_max_sequence,
            limit=10_000,
            connection=active,
        )
        records.extend(canonical_pairs)
        discriminator_records = tuple(
            item for item in records if isinstance(item, DiscriminatorOutcome)
        )
        parent_ids = tuple(
            dict.fromkeys(
                item.source_pair_id for item in discriminator_records
            )
        )
        canonical_ids = {item.pair_id for item in canonical_pairs}
        records.extend(
            repository.query_records_by_ids(
                tuple(item for item in parent_ids if item not in canonical_ids),
                max_sequence=_evidence_max_sequence,
                connection=active,
            )
        )
        paired_records = tuple(
            item for item in records if isinstance(item, PairedInvestigationDecision)
        )
        activation_parent_records = repository.query_records_by_ids(
            tuple(
                dict.fromkeys(
                    item.activation_decision_id
                    for item in paired_records
                    if item.activation_decision_id is not None
                )
            ),
            max_sequence=_evidence_max_sequence,
            connection=active,
        )
        records.extend(activation_parent_records)
        records.extend(
            repository.query_records_by_ids(
                tuple(
                    dict.fromkeys(
                        item.evaluation_id
                        for item in activation_parent_records
                        if isinstance(item, P34ActivationDecision)
                    )
                ),
                max_sequence=_evidence_max_sequence,
                connection=active,
            )
        )
        if blockers:
            raise InvestigationAdaptationIntegrityError(blockers[0])
        policies = tuple(
            item for item in records if isinstance(item, InvestigationPolicy)
        )
        protocols = tuple(
            item
            for item in records
            if isinstance(item, P34InvestigationActivationProtocol)
        )
        pairs = tuple(
            item for item in records if isinstance(item, PairedInvestigationDecision)
        )
        certificates = tuple(
            item
            for item in records
            if isinstance(item, InvestigationOutcomeCertificate)
        )
        followups = tuple(
            item for item in records if isinstance(item, InvestigationOutcomeFollowup)
        )
        discriminators = tuple(
            item for item in records if isinstance(item, DiscriminatorOutcome)
        )
        comparisons = tuple(
            item
            for item in records
            if isinstance(item, PairedInvestigationComparison)
        )
        transfers = tuple(
            item
            for item in records
            if isinstance(item, InvestigationNegativeTransfer)
        )
        controls = tuple(
            item for item in records if isinstance(item, P34NegativeControlResult)
        )
        evaluations = tuple(
            item
            for item in records
            if isinstance(item, InvestigationPolicyEvaluation)
        )
        activations = tuple(
            item for item in records if isinstance(item, P34ActivationDecision)
        )
        evidence_record_count, evidence_head_sha256 = (
            _p34_evidence_stream_boundary(
                active,
                stream_record_count=boundary.record_count,
                max_sequence=_evidence_max_sequence,
            )
        )
        (
            authoritative_cases,
            authoritative_discriminators,
            authoritative_followups,
        ) = (
            _authoritative_crew_lineage(
                active,
                pairs=pairs,
                certificates=certificates,
                discriminators=discriminators,
                followups=followups,
            )
        )
    finally:
        if active.in_transaction:
            active.rollback()
        snapshot_stable = bool(
            storage_stable
            and int(active.execute("PRAGMA data_version").fetchone()[0])
            == pre_snapshot_data_version
            and _authoritative_source_revision(active) == pre_source_revision
        )
        active.close()
    canonical_activation_evaluation_ids = frozenset(
        item.evaluation_id
        for item in evaluations
        if _canonical_activation_evaluation_matches(repository, item)
    )
    registry_identity = canonical_json_sha256(
        {
            "policy_sha256": sorted(item.policy_sha256 for item in policies),
            "protocol_sha256": sorted(item.protocol_sha256 for item in protocols),
            "pair_sha256": sorted(item.pair_sha256 for item in pairs),
            "certificate_sha256": sorted(
                item.certificate_sha256 for item in certificates
            ),
            "followup_sha256": sorted(item.followup_sha256 for item in followups),
            "discriminator_sha256": sorted(
                item.outcome_sha256 for item in discriminators
            ),
            "comparison_sha256": sorted(item.comparison_sha256 for item in comparisons),
            "negative_transfer_sha256": sorted(
                item.transfer_sha256 for item in transfers
            ),
            "negative_control_sha256": sorted(
                item.result_sha256 for item in controls
            ),
            "capacity_overflow_kinds": capacity_overflow,
        }
    )
    evaluation = evaluate_investigation_policies(
        protocol=p34_activation_protocol(),
        comparisons=comparisons,
        pairs=pairs,
        certificates=certificates,
        policy_records=policies,
        protocol_records=protocols,
        discriminator_outcomes=discriminators,
        outcome_followups=followups,
        negative_transfers=transfers,
        negative_control_results=controls,
        activation_decisions=activations,
        policy_evaluations=evaluations,
        authoritative_case_ids=authoritative_cases,
        authoritative_discriminator_ids=authoritative_discriminators,
        authoritative_followup_ids=authoritative_followups,
        canonical_activation_evaluation_ids=canonical_activation_evaluation_ids,
        capacity_overflow_kinds=capacity_overflow,
        registry_identity_sha256=registry_identity,
        ledger_record_count=evidence_record_count,
        ledger_head_sha256=evidence_head_sha256,
        evaluated_at=evaluated_at or datetime.now(timezone.utc),
    )
    if (
        cache_key is not None and snapshot_stable
    ):
        _REPOSITORY_EVALUATION_CACHE[cache_key] = evaluation
        while len(_REPOSITORY_EVALUATION_CACHE) > 16:
            _REPOSITORY_EVALUATION_CACHE.pop(
                next(iter(_REPOSITORY_EVALUATION_CACHE))
            )
    return evaluation


def resolve_effective_activation_decision(
    repository: InvestigationAdaptationRepository,
) -> P34ActivationDecision | None:
    """Return only a complete current earned artifact; otherwise baseline fallback."""

    protocol = p34_activation_protocol()
    result = repository.query_records(
        record_kinds=("activation_decision", "policy_evaluation"),
        protocol_id=protocol.protocol_id,
        limit=512,
    )
    if result.blockers:
        return None
    decisions = tuple(
        item for item in result.records if isinstance(item, P34ActivationDecision)
    )
    evaluations = tuple(
        item
        for item in result.records
        if isinstance(item, InvestigationPolicyEvaluation)
    )
    if not decisions:
        return None
    # Repository results are immutable sequence-descending; this also makes
    # equal-timestamp earned->rollback ordering deterministic across restart.
    latest = decisions[0]
    if latest.state != "limited_attention" or latest.blockers:
        return None
    if (
        latest.activated_policy_id != protocol.activated_policy_id
        or latest.activated_policy_sha256 != protocol.activated_policy_sha256
    ):
        return None
    matching = next(
        (
            item
            for item in evaluations
            if item.evaluation_id == latest.evaluation_id
            and item.evaluation_sha256 == latest.evaluation_sha256
            and item.decision == "limited_attention_earned"
            and not item.blockers
            and item.safety.passed
        ),
        None,
    )
    if matching is None:
        return None
    verified_key = _current_p34_chain_key(repository)
    if verified_key is None or verified_key not in _VERIFIED_P34_CHAIN_KEYS:
        # Restart/cold reads never pay an unbounded integrity audit.  Until an
        # explicit mutation-time review verifies the chain, production falls
        # back to the deterministic baseline.
        return None
    active = connect_read_only(repository.db_path)
    try:
        evidence_row = active.execute(
            "SELECT COUNT(*) AS record_count, MAX(sequence) AS last_sequence "
            "FROM investigation_adaptation_records WHERE record_kind IN ("
            "'policy', 'activation_protocol', 'outcome_certificate', "
            "'outcome_followup', 'discriminator_outcome', 'paired_comparison', "
            "'negative_transfer', 'negative_control_result')"
        ).fetchone()
        last_entry = (
            active.execute(
                "SELECT entry_sha256 FROM investigation_adaptation_records "
                "WHERE sequence = ?",
                (evidence_row["last_sequence"],),
            ).fetchone()
            if evidence_row["last_sequence"] is not None
            else None
        )
    finally:
        active.close()
    try:
        current = evaluate_p34_repository(
            repository,
        )
    except (InvestigationAdaptationIntegrityError, ValueError):
        return None
    if _global_activation_rollback_reasons(current):
        return None
    cache_key = (
        _repository_database_file(repository),
        protocol.protocol_id,
        int(evidence_row["record_count"]),
        last_entry["entry_sha256"] if last_entry is not None else None,
        latest.decision_id,
        latest.decision_sha256,
        current.evaluation_id,
        current.evaluation_sha256,
    )
    cached = _EFFECTIVE_ACTIVATION_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if not _canonical_activation_evaluation_matches(repository, matching):
        return None
    _EFFECTIVE_ACTIVATION_CACHE[cache_key] = latest
    while len(_EFFECTIVE_ACTIVATION_CACHE) > 16:
        _EFFECTIVE_ACTIVATION_CACHE.pop(next(iter(_EFFECTIVE_ACTIVATION_CACHE)))
    return latest


def restore_effective_activation_on_mutation(
    repository: InvestigationAdaptationRepository,
) -> P34ActivationDecision | None:
    """Revalidate a durable activation after restart on an explicit mutation.

    Read-only Crew projections remain bounded and fall back to baseline when a
    process has not yet verified the immutable evidence chain.  The next
    server-owned mutation may pay the exact protocol-scoped audit once, then
    reuse the verified revision for normal paired-decision freezes.
    """

    try:
        evaluate_p34_repository(repository, strict_integrity=True)
    except (InvestigationAdaptationIntegrityError, ValueError):
        return None
    return resolve_effective_activation_decision(repository)


__all__ = [
    "append_p34_terminal_capture_unit_in_transaction",
    "append_paired_investigation_comparison",
    "assess_p34_repository_readiness",
    "assess_investigation_improvement_readiness",
    "baseline_investigation_policy",
    "build_discriminator_outcome",
    "build_discriminator_outcome_from_crew_events",
    "build_investigation_outcome_followup",
    "build_investigation_improvement_projection",
    "build_investigation_negative_transfer",
    "build_investigation_outcome_certificate",
    "build_p34_activation_decision",
    "build_p34_negative_control_result",
    "build_paired_investigation_comparison",
    "build_paired_investigation_decision",
    "capture_p34_controlled_workflow_followup",
    "capture_p34_negative_transfer",
    "canonical_investigation_evaluation_pair",
    "classify_p34_problem_family",
    "classify_p34_problem_orientation",
    "classify_p34_track_class",
    "classify_counterfactual_observability",
    "evaluate_investigation_policies",
    "evaluate_p34_repository",
    "limited_attention_investigation_policy",
    "latest_completed_comparison_lineage",
    "memory_shadow_investigation_policy",
    "pending_p34_scored_workflow_ids",
    "p34_activation_protocol",
    "persist_p34_foundation",
    "persist_p34_evaluation_and_activation",
    "resolve_effective_activation_decision",
    "restore_effective_activation_on_mutation",
    "recover_unreviewed_p34_terminal_capture",
    "review_p34_after_terminal_capture",
]
