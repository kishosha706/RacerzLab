"""Auditable, fail-closed activation policies for advanced capabilities."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import EvidenceLabModel, canonical_hash
from racelab_engine.evaluation.metric_evaluation import EvaluationArtifact, MetricThreshold
from racelab_engine.storage.db import initialize_database


ActivationState = Literal[
    "locked_insufficient_data",
    "locked_failed_validation",
    "shadow",
    "eligible_for_prospective_shadow",
    "eligible_for_limited_activation",
    "activated",
]

_STATE_ORDER: tuple[ActivationState, ...] = (
    "locked_insufficient_data",
    "locked_failed_validation",
    "shadow",
    "eligible_for_prospective_shadow",
    "eligible_for_limited_activation",
    "activated",
)


class ActivationGate(EvidenceLabModel):
    gate_id: str = Field(pattern=r"^acg-[0-9a-f]{20}$")
    gate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_version: str = Field(min_length=1)
    capability_key: str = Field(min_length=1)
    created_at: datetime
    required_dataset_counts: dict[str, int]
    minimum_counts: dict[str, int]
    split_policy_kinds: tuple[str, ...] = Field(min_length=1)
    metric_thresholds: tuple[MetricThreshold, ...] = Field(min_length=1)
    negative_control_ids: tuple[str, ...] = Field(min_length=1)
    subgroup_requirements: tuple[str, ...] = Field(min_length=1)
    prerequisite_keys: tuple[str, ...] = ()
    prospective_validation_required: bool
    minimum_prospective_units: int = Field(ge=0)
    maximum_state: ActivationState
    manual_override_allowed: Literal[False] = False

    @model_validator(mode="after")
    def gate_is_pre_registered_and_content_addressed(self) -> ActivationGate:
        if any(value < 0 for value in self.required_dataset_counts.values()):
            raise ValueError("required dataset counts must be non-negative")
        if any(value < 0 for value in self.minimum_counts.values()):
            raise ValueError("activation minimum counts must be non-negative")
        for values, label in (
            (self.split_policy_kinds, "split policy"),
            (self.negative_control_ids, "negative control"),
            (self.subgroup_requirements, "subgroup"),
            (self.prerequisite_keys, "prerequisite"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"activation {label} values must be unique")
        payload = self.model_dump(mode="json", exclude={"gate_id", "gate_hash"})
        expected = canonical_hash(payload)
        if self.gate_hash != expected or self.gate_id != f"acg-{expected[:20]}":
            raise ValueError("activation gate identity does not match its frozen policy")
        return self


class ActivationEvidence(EvidenceLabModel):
    dataset_counts: dict[str, int]
    counts: dict[str, int]
    ready_prerequisites: tuple[str, ...]
    prospective_units: int = Field(ge=0)
    dataset_hashes: tuple[str, ...]
    code_hash: str = Field(min_length=7)
    evaluation_split_policy_kind: str | None = None


class ActivationEvaluation(EvidenceLabModel):
    gate_id: str
    gate_hash: str
    evaluated_at: datetime
    dataset_hashes: tuple[str, ...]
    code_hash: str
    evaluation_artifact_id: str | None = None
    count_deficits: dict[str, int]
    missing_dataset_kinds: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    failed_metrics: tuple[str, ...]
    failed_negative_controls: tuple[str, ...]
    failed_subgroups: tuple[str, ...]
    identity_failures: tuple[str, ...]


class ActivationDecision(EvidenceLabModel):
    decision_id: str = Field(pattern=r"^acd-[0-9a-f]{20}$")
    decision_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_key: str
    state: ActivationState
    evaluated_at: datetime
    gate_id: str
    gate_hash: str
    evaluation: ActivationEvaluation
    blockers: tuple[str, ...]
    auditable: Literal[True] = True
    manual_override_used: Literal[False] = False

    @model_validator(mode="after")
    def decision_is_content_addressed(self) -> ActivationDecision:
        payload = self.model_dump(mode="json", exclude={"decision_id", "decision_hash"})
        expected = canonical_hash(payload)
        if self.decision_hash != expected or self.decision_id != f"acd-{expected[:20]}":
            raise ValueError("activation decision identity does not match its evidence")
        return self


def build_activation_gate(payload: dict[str, Any]) -> ActivationGate:
    if {"gate_id", "gate_hash"} & payload.keys():
        raise ValueError("activation-gate identity is derived")
    normalized = {
        "created_at": datetime.now(timezone.utc),
        "prerequisite_keys": (),
        "manual_override_allowed": False,
        **payload,
    }
    normalized["metric_thresholds"] = tuple(
        MetricThreshold.model_validate(item) for item in normalized["metric_thresholds"]
    )
    identity_payload = ActivationGate.model_construct(
        gate_id="acg-" + "0" * 20,
        gate_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"gate_id", "gate_hash"})
    gate_hash = canonical_hash(identity_payload)
    return ActivationGate(
        gate_id=f"acg-{gate_hash[:20]}",
        gate_hash=gate_hash,
        **normalized,
    )


def evaluate_activation_gate(
    gate: ActivationGate,
    evidence: ActivationEvidence,
    *,
    evaluation_artifact: EvaluationArtifact | None = None,
    evaluated_at: datetime | None = None,
) -> ActivationDecision:
    timestamp = evaluated_at or datetime.now(timezone.utc)
    missing_dataset_kinds = tuple(
        sorted(
            kind
            for kind, required in gate.required_dataset_counts.items()
            if evidence.dataset_counts.get(kind, 0) < required
        )
    )
    count_deficits = {
        key: required - evidence.counts.get(key, 0)
        for key, required in gate.minimum_counts.items()
        if evidence.counts.get(key, 0) < required
    }
    missing_prerequisites = tuple(
        sorted(set(gate.prerequisite_keys) - set(evidence.ready_prerequisites))
    )
    failed_metrics: list[str] = []
    failed_controls: list[str] = []
    failed_subgroups: list[str] = []
    identity_failures: list[str] = []
    if evaluation_artifact is not None:
        if evaluation_artifact.capability_key != gate.capability_key:
            identity_failures.append("Evaluation capability does not match the gate.")
        if evaluation_artifact.dataset_hash not in evidence.dataset_hashes:
            identity_failures.append("Evaluation dataset hash is not in activation evidence.")
        if evaluation_artifact.code_commit != evidence.code_hash:
            identity_failures.append("Evaluation code identity does not match activation evidence.")
        if evidence.evaluation_split_policy_kind not in gate.split_policy_kinds:
            identity_failures.append("Evaluation split policy is not allowed by the gate.")
        if not evaluation_artifact.eligible_for_activation_review:
            identity_failures.append("Evaluation artifact is not eligible for activation review.")
        for threshold in gate.metric_thresholds:
            if not _passes(evaluation_artifact.metrics.get(threshold.metric_key), threshold):
                failed_metrics.append(threshold.metric_key)
        control_by_id = {
            control.control_id: control for control in evaluation_artifact.negative_controls
        }
        failed_controls = [
            control_id
            for control_id in gate.negative_control_ids
            if control_id not in control_by_id or not control_by_id[control_id].passed
        ]
        subgroup_by_key = {
            subgroup.subgroup_key: subgroup for subgroup in evaluation_artifact.subgroups
        }
        failed_subgroups = [
            subgroup
            for subgroup in gate.subgroup_requirements
            if subgroup not in subgroup_by_key or not subgroup_by_key[subgroup].passed
        ]
    evaluation = ActivationEvaluation(
        gate_id=gate.gate_id,
        gate_hash=gate.gate_hash,
        evaluated_at=timestamp,
        dataset_hashes=evidence.dataset_hashes,
        code_hash=evidence.code_hash,
        evaluation_artifact_id=(
            None if evaluation_artifact is None else evaluation_artifact.evaluation_id
        ),
        count_deficits=count_deficits,
        missing_dataset_kinds=missing_dataset_kinds,
        missing_prerequisites=missing_prerequisites,
        failed_metrics=tuple(failed_metrics),
        failed_negative_controls=tuple(failed_controls),
        failed_subgroups=tuple(failed_subgroups),
        identity_failures=tuple(identity_failures),
    )
    blockers: list[str] = []
    if missing_dataset_kinds:
        blockers.append("Required dataset kinds are missing or undersized.")
    if count_deficits:
        blockers.append("Minimum independent evidence counts are not met.")
    if missing_prerequisites:
        blockers.append("Scientific prerequisites are not validated.")
    if blockers:
        state: ActivationState = "locked_insufficient_data"
    elif evaluation_artifact is None:
        state = _cap_state("shadow", gate.maximum_state)
        blockers.append("No frozen evaluation artifact has been scored.")
    elif (
        evaluation_artifact.state != "valid"
        or failed_metrics
        or failed_controls
        or failed_subgroups
        or identity_failures
    ):
        state = "locked_failed_validation"
        blockers.append("Frozen validation, negative controls, or subgroups failed.")
    elif (
        gate.prospective_validation_required
        and evidence.prospective_units < gate.minimum_prospective_units
    ):
        state = _cap_state("eligible_for_prospective_shadow", gate.maximum_state)
        blockers.append("Prospective shadow validation is still required.")
    else:
        state = _cap_state("eligible_for_limited_activation", gate.maximum_state)
        if state != "eligible_for_limited_activation":
            blockers.append("The pre-registered P21 authority ceiling remains in force.")
    normalized = {
        "capability_key": gate.capability_key,
        "state": state,
        "evaluated_at": timestamp,
        "gate_id": gate.gate_id,
        "gate_hash": gate.gate_hash,
        "evaluation": evaluation,
        "blockers": tuple(blockers),
        "auditable": True,
        "manual_override_used": False,
    }
    identity_payload = ActivationDecision.model_construct(
        decision_id="acd-" + "0" * 20,
        decision_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"decision_id", "decision_hash"})
    decision_hash = canonical_hash(identity_payload)
    return ActivationDecision(
        decision_id=f"acd-{decision_hash[:20]}",
        decision_hash=decision_hash,
        **normalized,
    )


def save_activation_decision(
    decision: ActivationDecision,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            row = connection.execute(
                "SELECT decision_hash, decision_json FROM activation_decisions "
                "WHERE decision_id = ?",
                (decision.decision_id,),
            ).fetchone()
            if row is not None:
                if (
                    row["decision_hash"] != decision.decision_hash
                    or ActivationDecision.model_validate_json(row["decision_json"])
                    != decision
                ):
                    raise ValueError("immutable activation-decision identity collision")
                return False
            connection.execute(
                "INSERT INTO activation_decisions "
                "(decision_id, decision_hash, capability_key, state, evaluated_at, "
                "decision_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    decision.decision_id,
                    decision.decision_hash,
                    decision.capability_key,
                    decision.state,
                    decision.evaluated_at.isoformat(),
                    decision.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def p21_activation_gates(
    *,
    created_at: datetime | None = None,
) -> tuple[ActivationGate, ...]:
    timestamp = created_at or datetime(2026, 8, 10, tzinfo=timezone.utc)
    common = {
        "gate_version": "p21-product-policy-v1",
        "created_at": timestamp,
        "split_policy_kinds": ("whole_session", "whole_workflow", "whole_stint"),
        "negative_control_ids": ("same_setup_unchanged", "sim_integrity_degraded"),
        "subgroup_requirements": ("short_track", "intermediate", "superspeedway"),
        "prospective_validation_required": True,
        "minimum_prospective_units": 10,
        "maximum_state": "eligible_for_prospective_shadow",
    }
    definitions = (
        {
            "capability_key": "driver_noise_envelope",
            "required_dataset_counts": {"driver_repeatability": 1},
            "minimum_counts": {"independent_sessions": 3, "eligible_laps": 30},
            "metric_thresholds": (
                {"metric_key": "false_episode_rate", "operator": "lte", "value": 0.05},
            ),
        },
        {
            "capability_key": "change_point",
            "required_dataset_counts": {"long_run_tire": 1, "null_no_change": 1},
            "minimum_counts": {"uninterrupted_stints": 30, "null_stints": 10},
            "metric_thresholds": (
                {"metric_key": "false_change_point_rate", "operator": "lte", "value": 0.05},
                {"metric_key": "median_localization_error_laps", "operator": "lte", "value": 1.0},
            ),
        },
        {
            "capability_key": "causal_control_family",
            "required_dataset_counts": {"controlled_aba": 1, "null_no_change": 1},
            "minimum_counts": {"controlled_workflows": 30, "contexts": 3, "per_factor": 6},
            "metric_thresholds": (
                {"metric_key": "placebo_false_positive_rate", "operator": "lte", "value": 0.05},
                {"metric_key": "direction_replication", "operator": "gte", "value": 0.80},
                {"metric_key": "restoration_pass_rate", "operator": "eq", "value": 1.0},
            ),
        },
        {
            "capability_key": "formal_information_gain",
            "required_dataset_counts": {"historical_archive": 1},
            "minimum_counts": {"prospective_missions": 30},
            "metric_thresholds": (
                {"metric_key": "authority_violations", "operator": "eq", "value": 0.0},
                {"metric_key": "false_stop_rate", "operator": "lte", "value": 0.05},
                {"metric_key": "median_clean_lap_cost_delta", "operator": "lte", "value": 0.0},
            ),
            "prerequisite_keys": ("deterministic_planner_comparator",),
        },
        {
            "capability_key": "probability_calibration",
            "required_dataset_counts": {"controlled_aba": 1, "null_no_change": 1},
            "minimum_counts": {"graded_predictions": 100, "independent_sessions": 30},
            "metric_thresholds": (
                {"metric_key": "brier_skill_vs_baseline", "operator": "gte", "value": 0.05},
            ),
        },
        {
            "capability_key": "response_model",
            "required_dataset_counts": {"controlled_aba": 1},
            "minimum_counts": {"controlled_workflows": 30, "contexts": 3, "per_factor": 6},
            "metric_thresholds": (
                {"metric_key": "held_out_score", "operator": "gte", "value": 0.65},
                {"metric_key": "direction_replication", "operator": "gte", "value": 0.80},
                {"metric_key": "contradiction_rate", "operator": "lte", "value": 0.25},
            ),
        },
        {
            "capability_key": "conformal_uncertainty",
            "required_dataset_counts": {"historical_archive": 1},
            "minimum_counts": {"independent_sessions": 30},
            "metric_thresholds": (
                {"metric_key": "absolute_coverage_gap", "operator": "lte", "value": 0.05},
            ),
            "prerequisite_keys": ("separate_calibration_set",),
        },
        {
            "capability_key": "hierarchical_transfer",
            "required_dataset_counts": {"historical_archive": 1},
            "minimum_counts": {"independent_sessions": 30, "tracks": 3, "drivers": 2},
            "metric_thresholds": (
                {"metric_key": "negative_transfer_subgroups", "operator": "eq", "value": 0.0},
            ),
            "prerequisite_keys": ("no_transfer_baseline",),
        },
        {
            "capability_key": "shadow_sideslip",
            "required_dataset_counts": {"shadow_observer_ground_truth": 1},
            "minimum_counts": {"independent_sessions": 30},
            "metric_thresholds": (
                {"metric_key": "frozen_error_target_pass", "operator": "eq", "value": 1.0},
            ),
            "prerequisite_keys": (
                "body_axes",
                "steering_conversion",
                "wheelbase",
                "bank_gravity_treatment",
                "frozen_error_targets",
            ),
        },
        {
            "capability_key": "gravity_compensation",
            "required_dataset_counts": {"shadow_observer_ground_truth": 1},
            "minimum_counts": {"independent_sessions": 30},
            "metric_thresholds": (
                {"metric_key": "reference_error_target_pass", "operator": "eq", "value": 1.0},
            ),
            "prerequisite_keys": ("body_axes", "gravity_convention"),
        },
        {
            "capability_key": "geometry_wheel_disagreement",
            "required_dataset_counts": {"vehicle_profile_validation": 1, "shadow_observer_ground_truth": 1},
            "minimum_counts": {"independent_events": 30},
            "metric_thresholds": (
                {"metric_key": "negative_control_false_positive_rate", "operator": "lte", "value": 0.05},
            ),
            "prerequisite_keys": (
                "wheelbase",
                "front_track_width",
                "rear_track_width",
                "wheel_speed_semantics",
            ),
        },
        {
            "capability_key": "bayesian_optimization",
            "required_dataset_counts": {"controlled_aba": 1},
            "minimum_counts": {"controlled_workflows": 100, "contexts": 3, "per_factor": 6},
            "metric_thresholds": (
                {"metric_key": "held_out_score", "operator": "gte", "value": 0.65},
                {"metric_key": "authority_violations", "operator": "eq", "value": 0.0},
            ),
            "prerequisite_keys": (
                "countereffect_model",
                "negative_transfer_passed",
                "safe_legal_domain",
                "restoration_tests",
            ),
            "maximum_state": "shadow",
        },
        {
            "capability_key": "multi_control_optimization",
            "required_dataset_counts": {"controlled_aba": 1},
            "minimum_counts": {"controlled_workflows": 100, "multi_factor_experiments": 30},
            "metric_thresholds": (
                {"metric_key": "held_out_score", "operator": "gte", "value": 0.65},
                {"metric_key": "authority_violations", "operator": "eq", "value": 0.0},
            ),
            "prerequisite_keys": ("single_control_response_validated", "safe_legal_domain"),
            "maximum_state": "shadow",
        },
    )
    return tuple(build_activation_gate({**common, **definition}) for definition in definitions)


def _passes(observed: float | int | None, threshold: MetricThreshold) -> bool:
    if observed is None:
        return False
    value = float(observed)
    target = threshold.value
    return {
        "lt": value < target,
        "lte": value <= target,
        "gt": value > target,
        "gte": value >= target,
        "eq": value == target,
    }[threshold.operator]


def _cap_state(state: ActivationState, maximum: ActivationState) -> ActivationState:
    return _STATE_ORDER[min(_STATE_ORDER.index(state), _STATE_ORDER.index(maximum))]


__all__ = [
    "ActivationDecision",
    "ActivationEvaluation",
    "ActivationEvidence",
    "ActivationGate",
    "ActivationState",
    "build_activation_gate",
    "evaluate_activation_gate",
    "p21_activation_gates",
    "save_activation_decision",
]
