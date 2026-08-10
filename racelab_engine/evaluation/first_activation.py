"""P23 first-earned-capability audit and immutable validation protocol.

P23 does not activate a capability by construction.  It ranks the current
scientific debt, freezes the first candidate's validation contract, and reports
whether the already-persisted P21/P22 evidence has earned a later review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.activation_gates import (
    ActivationDecision,
    ActivationGate,
    p22_field_activation_gates,
)
from racelab_engine.evaluation.campaigns import campaign_progress, initial_campaigns
from racelab_engine.evaluation.dataset_registry import (
    EvidenceLabModel,
    canonical_hash,
    list_evidence_datasets,
)
from racelab_engine.evaluation.metric_evaluation import (
    EvaluationArtifact,
    MetricThreshold,
)
from racelab_engine.storage.db import initialize_database


P23Status = Literal[
    "no_activation_earned",
    "historical_validation_passed",
    "prospective_shadow_active",
    "limited_activation_earned",
    "blocked_by_evidence_deficit",
]
ValidationState = Literal["not_started", "blocked", "failed", "passed"]


class CapabilityActivationAudit(EvidenceLabModel):
    rank: int = Field(ge=1)
    capability_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    current_authority: Literal["observation_only", "shadow_only", "locked"]
    required_gate_id: str = Field(min_length=1)
    required_gate_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    qualified_evidence_available: tuple[str, ...]
    qualified_evidence_missing: tuple[str, ...] = Field(min_length=1)
    independent_unit_count: int = Field(ge=0)
    negative_control_state: ValidationState
    historical_validation_state: ValidationState
    prospective_validation_state: ValidationState
    subgroup_coverage: dict[str, int]
    vehicle_profile_prerequisites: tuple[str, ...]
    estimated_realistic_collection_cost: str = Field(min_length=1)
    earliest_legitimate_activation_path: str = Field(min_length=1)
    selection_reason: str = Field(min_length=1)
    selected: bool = False


class P23ValidationProtocol(EvidenceLabModel):
    protocol_id: str = Field(pattern=r"^p23p-[0-9a-f]{20}$")
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_version: str = Field(min_length=1)
    created_at: datetime
    candidate_capability: Literal["steering_workload_envelope"]
    source_metric_key: Literal["steering_control_workload"]
    formula_version: Literal["p20.steering_workload.v1"]
    model_code_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    dataset_requirements: dict[str, int]
    independence_unit: Literal["source_session"] = "source_session"
    context_requirements: tuple[str, ...] = Field(min_length=1)
    exclusions: tuple[str, ...] = Field(min_length=1)
    negative_control_ids: tuple[str, ...] = Field(min_length=1)
    split_policy: tuple[str, ...] = Field(min_length=1)
    primary_metrics: tuple[str, ...] = Field(min_length=1)
    thresholds: tuple[MetricThreshold, ...] = Field(min_length=1)
    required_subgroups: tuple[str, ...] = Field(min_length=1)
    failure_thresholds: tuple[MetricThreshold, ...] = Field(min_length=1)
    minimum_prospective_units: int = Field(ge=1)
    drift_criteria: tuple[str, ...] = Field(min_length=1)
    allowed_outputs_if_passed: tuple[str, ...] = Field(min_length=1)
    forbidden_outputs: tuple[str, ...] = Field(min_length=1)
    authority_ceiling: Literal["limited_observation_overlay"] = (
        "limited_observation_overlay"
    )
    current_authority: Literal["shadow_only"] = "shadow_only"
    p19_authority_unchanged: Literal[True] = True
    p20_authority_unchanged: Literal[True] = True

    @model_validator(mode="after")
    def protocol_is_complete_frozen_and_non_authoritative(self) -> P23ValidationProtocol:
        for values, label in (
            (self.context_requirements, "context requirement"),
            (self.exclusions, "exclusion"),
            (self.negative_control_ids, "negative control"),
            (self.split_policy, "split policy"),
            (self.primary_metrics, "primary metric"),
            (self.required_subgroups, "required subgroup"),
            (self.drift_criteria, "drift criterion"),
            (self.allowed_outputs_if_passed, "allowed output"),
            (self.forbidden_outputs, "forbidden output"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique")
        if any(value < 1 for value in self.dataset_requirements.values()):
            raise ValueError("P23 dataset requirements must be positive")
        if {
            "setup_value",
            "cause_probability",
            "cause_rank",
            "keep_undo_policy",
            "measurement_plan",
        } - set(self.forbidden_outputs):
            raise ValueError("P23 protocol must preserve every production-authority ban")
        threshold_keys = [item.metric_key for item in self.thresholds]
        failure_keys = [item.metric_key for item in self.failure_thresholds]
        if len(threshold_keys) != len(set(threshold_keys)):
            raise ValueError("P23 passing-threshold keys must be unique")
        if len(failure_keys) != len(set(failure_keys)):
            raise ValueError("P23 failure-threshold keys must be unique")
        payload = self.model_dump(mode="json", exclude={"protocol_id", "protocol_hash"})
        digest = canonical_hash(payload)
        if self.protocol_hash != digest or self.protocol_id != f"p23p-{digest[:20]}":
            raise ValueError("P23 protocol identity does not match its frozen content")
        return self


class P23ValidationStage(EvidenceLabModel):
    state: ValidationState
    qualified_real_units: int = Field(ge=0)
    required_real_units: int = Field(ge=0)
    artifact_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def stage_truth_is_explicit(self) -> P23ValidationStage:
        if self.state == "passed" and self.blockers:
            raise ValueError("passing P23 stages cannot retain blockers")
        if self.state == "passed" and (
            self.qualified_real_units < self.required_real_units or not self.artifact_ids
        ):
            raise ValueError(
                "passing P23 stages require enough real units and immutable artifacts"
            )
        if self.state != "passed" and not self.blockers:
            raise ValueError("non-passing P23 stages must explain their state")
        return self


class P23FirstActivationAudit(EvidenceLabModel):
    audit_id: str = Field(pattern=r"^p23a-[0-9a-f]{20}$")
    audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_version: str = Field(min_length=1)
    created_at: datetime
    archive_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[CapabilityActivationAudit, ...] = Field(min_length=1)
    selected_capability: Literal["steering_workload_envelope"]
    selection_summary: str = Field(min_length=1)
    protocol_id: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    historical: P23ValidationStage
    prospective: P23ValidationStage
    negative_controls: P23ValidationStage
    subgroups: P23ValidationStage
    activation_decision: P23Status
    exact_authority_envelope: tuple[str, ...]
    remaining_locks: tuple[str, ...] = Field(min_length=1)
    next_collection_missions: tuple[str, ...] = Field(min_length=1)
    p19_sole_reasoning_setup_authority: Literal[True] = True
    p20_sole_state_projection: Literal[True] = True

    @model_validator(mode="after")
    def audit_cannot_skip_scientific_states(self) -> P23FirstActivationAudit:
        selected = [item for item in self.candidates if item.selected]
        if len(selected) != 1 or selected[0].capability_key != self.selected_capability:
            raise ValueError("P23 audit must select exactly its ranked winner")
        all_passed = all(
            stage.state == "passed"
            for stage in (
                self.historical,
                self.prospective,
                self.negative_controls,
                self.subgroups,
            )
        )
        if self.activation_decision == "limited_activation_earned" and not all_passed:
            raise ValueError("limited activation requires every frozen gate to pass")
        if self.activation_decision != "limited_activation_earned" and self.exact_authority_envelope:
            raise ValueError("an unearned capability cannot publish an authority envelope")
        payload = self.model_dump(mode="json", exclude={"audit_id", "audit_hash"})
        digest = canonical_hash(payload)
        if self.audit_hash != digest or self.audit_id != f"p23a-{digest[:20]}":
            raise ValueError("P23 audit identity does not match its evidence")
        return self


def first_activation_protocol() -> P23ValidationProtocol:
    payload = {
        "protocol_version": "p23-steering-workload-field-v1",
        "created_at": datetime(2026, 8, 10, tzinfo=timezone.utc),
        "candidate_capability": "steering_workload_envelope",
        "source_metric_key": "steering_control_workload",
        "formula_version": "p20.steering_workload.v1",
        "model_code_sha256": "c30de28588830da0d3a080269fa85243960b23a12dfbdaeb61a7a82d0e172ddb",
        "baseline_commit": "abf892533de65e850df4a7b17e8e5b51a8976c96",
        "dataset_requirements": {
            "historical_independent_sessions": 9,
            "historical_eligible_laps": 90,
            "prospective_independent_sessions": 10,
            "prospective_eligible_laps": 100,
            "null_stints": 10,
            "sessions_per_track_type": 3,
        },
        "independence_unit": "source_session",
        "context_requirements": (
            "exact car and iRacing build",
            "exact complete FFB fingerprint",
            "exact steering-conversion state",
            "matched physical track-position window",
            "matched speed, fuel, tire-age, weather, and driver context",
            "healthy 360 Hz sub-tick steering-torque clock",
            "canonical eligible laps only",
        ),
        "exclusions": (
            "junk, pit, cooldown, wreck, partial, or invalid-speed lap",
            "traffic-contaminated or line-mismatched window",
            "FFB or steering-conversion mismatch",
            "missing, constant, clipped, gapped, or sample-clock-faulted torque",
            "material setup, control, build, profile, or formula-version mismatch",
            "synthetic evidence presented as real field evidence",
        ),
        "negative_control_ids": (
            "stable_steering_response",
            "ffb_config_changed",
            "driver_line_changed",
            "traffic_context_mismatch",
            "sim_integrity_degraded",
            "profile_build_mismatch",
            "pit_context_boundary",
            "same_setup_unchanged",
        ),
        "split_policy": (
            "whole source session",
            "source fingerprint deduplication",
            "chronological historical train/evaluation split",
            "prospective units strictly after protocol freeze",
            "no adjacent-window independence",
        ),
        "primary_metrics": (
            "absolute_envelope_coverage_gap",
            "known_increase_detection_rate",
            "negative_control_false_positive_rate",
            "ffb_mismatch_block_rate",
            "contamination_acceptance_rate",
        ),
        "thresholds": (
            MetricThreshold(
                metric_key="absolute_envelope_coverage_gap",
                operator="lte",
                value=0.05,
            ),
            MetricThreshold(
                metric_key="known_increase_detection_rate",
                operator="gte",
                value=0.80,
            ),
            MetricThreshold(
                metric_key="negative_control_false_positive_rate",
                operator="lte",
                value=0.05,
            ),
            MetricThreshold(
                metric_key="ffb_mismatch_block_rate",
                operator="eq",
                value=1.0,
            ),
            MetricThreshold(
                metric_key="contamination_acceptance_rate",
                operator="eq",
                value=0.0,
            ),
        ),
        "required_subgroups": (
            "short_track",
            "intermediate",
            "superspeedway",
            "low_track_temperature",
            "high_track_temperature",
            "short_run",
            "long_run",
            "low_fuel",
            "high_fuel",
        ),
        "failure_thresholds": (
            MetricThreshold(
                metric_key="any_subgroup_coverage_gap",
                operator="gt",
                value=0.10,
            ),
            MetricThreshold(
                metric_key="rolling_negative_control_false_positive_rate",
                operator="gt",
                value=0.10,
            ),
            MetricThreshold(
                metric_key="incompatible_context_publication_count",
                operator="gt",
                value=0.0,
            ),
        ),
        "minimum_prospective_units": 10,
        "drift_criteria": (
            "new iRacing build blocks the envelope until re-evaluated",
            "FFB/profile/formula/code hash mismatch blocks the envelope",
            "rolling ten-unit subgroup coverage gap above 0.10 suspends eligibility",
            "any incompatible-context publication suspends eligibility",
        ),
        "allowed_outputs_if_passed": (
            "validated normal steering-workload envelope",
            "inside/outside-envelope descriptive evidence state",
            "validated error bounds and exact context envelope",
            "stronger support or contradiction evidence for P19 consumption",
        ),
        "forbidden_outputs": (
            "setup_value",
            "cause_probability",
            "cause_rank",
            "keep_undo_policy",
            "measurement_plan",
            "automatic control",
            "driver fatigue or impairment claim",
        ),
        "authority_ceiling": "limited_observation_overlay",
        "current_authority": "shadow_only",
        "p19_authority_unchanged": True,
        "p20_authority_unchanged": True,
    }
    constructed = P23ValidationProtocol.model_construct(
        protocol_id="p23p-" + "0" * 20,
        protocol_hash="0" * 64,
        **payload,
    )
    digest = canonical_hash(
        constructed.model_dump(mode="json", exclude={"protocol_id", "protocol_hash"})
    )
    return P23ValidationProtocol(
        protocol_id=f"p23p-{digest[:20]}",
        protocol_hash=digest,
        **payload,
    )


_EXTRA_CANDIDATES = {
    "steering_workload_envelope": {
        "label": "Steering workload envelope",
        "authority": "observation_only",
        "cost": "9 historical + 10 prospective sessions; about 190 clean laps",
        "profile": ("exact FFB fingerprint", "steering conversion"),
        "path": "Run the control-workload and null campaigns, then frozen historical and prospective evaluation.",
        "reason": "Selected: existing deterministic 360 Hz descriptor, strong null/block controls, no geometry dependency, and observation-only utility.",
    },
    "steering_yaw_transient_calibration": {
        "label": "Steering/yaw transient calibration",
        "authority": "observation_only",
        "cost": "At least 30 sessions plus an external yaw-delay reference",
        "profile": ("body axes", "steering conversion"),
        "path": "Validate body axes and steering conversion, then collect external-reference transient events.",
        "reason": "Not selected: useful and descriptive, but reference and profile prerequisites are not yet validated.",
    },
}

_GATE_LABELS = {
    "driver_noise_envelope": "Driver-noise envelope",
    "change_point": "Change-point detection",
    "causal_control_family": "Causal control-family calibration",
    "formal_information_gain": "Formal information gain",
    "probability_calibration": "Calibrated probabilities",
    "response_model": "Setup response model",
    "conformal_uncertainty": "Conformal uncertainty",
    "hierarchical_transfer": "Hierarchical transfer",
    "shadow_sideslip": "Body sideslip observer",
    "gravity_compensation": "Bank/gravity compensation",
    "geometry_wheel_disagreement": "Geometry-corrected wheel disagreement",
    "bayesian_optimization": "Bayesian optimization",
    "multi_control_optimization": "Multi-control optimization",
}

_RANK_ORDER = (
    "steering_workload_envelope",
    "driver_noise_envelope",
    "steering_yaw_transient_calibration",
    "change_point",
    "geometry_wheel_disagreement",
    "gravity_compensation",
    "response_model",
    "causal_control_family",
    "conformal_uncertainty",
    "hierarchical_transfer",
    "probability_calibration",
    "shadow_sideslip",
    "formal_information_gain",
    "bayesian_optimization",
    "multi_control_optimization",
)

_COSTS = {
    "driver_noise_envelope": "3 historical sessions plus 10 prospective sessions; at least 130 clean laps",
    "change_point": "30 long-run stints, 10 null stints, and 10 prospective units",
    "causal_control_family": "30 A/B/A2 workflows across 3 contexts plus 10 prospective units",
    "formal_information_gain": "30 prospective missions after a deterministic-planner comparator passes",
    "probability_calibration": "100 graded predictions across 30 sessions plus prospective validation",
    "response_model": "30 A/B/A2 workflows, 3 contexts, 6 per factor, plus prospective validation",
    "conformal_uncertainty": "30 sessions, a separate calibration split, and 10 prospective units",
    "hierarchical_transfer": "30 sessions, 3 tracks, 2 drivers, no-transfer baseline, and prospective units",
    "shadow_sideslip": "30 sessions with external ground truth and five profile prerequisites",
    "gravity_compensation": "30 sessions with external reference and validated body/gravity conventions",
    "geometry_wheel_disagreement": "Source-backed geometry plus 30 independent labeled events and 10 prospective units",
    "bayesian_optimization": "100 A/B/A2 workflows plus countereffect, transfer, restoration, and safety validation",
    "multi_control_optimization": "100 A/B/A2 workflows and 30 protocol-valid multi-factor experiments",
}


def _latest_decisions(db_path: str | Path | None) -> dict[str, ActivationDecision]:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT decision_json FROM activation_decisions "
            "ORDER BY evaluated_at DESC, decision_id DESC"
        ).fetchall()
    finally:
        connection.close()
    decisions: dict[str, ActivationDecision] = {}
    for row in rows:
        decision = ActivationDecision.model_validate_json(row[0])
        decisions.setdefault(decision.capability_key, decision)
    return decisions


def _evaluation_artifacts(db_path: str | Path | None) -> tuple[EvaluationArtifact, ...]:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT evaluation_json FROM evaluation_artifacts "
            "ORDER BY created_at, evaluation_id"
        ).fetchall()
    finally:
        connection.close()
    return tuple(EvaluationArtifact.model_validate_json(row[0]) for row in rows)


def _qualified_dataset_inventory(db_path: str | Path | None) -> tuple[dict[str, int], int]:
    counts: dict[str, int] = {}
    total = 0
    seen_source_fingerprints: set[str] = set()
    for dataset in list_evidence_datasets(db_path=db_path):
        if dataset.qualification.state != "qualified":
            continue
        real_units = [unit for unit in dataset.units if not unit.synthetic][
            : dataset.qualification.qualified_real_world_units
        ]
        for unit in real_units:
            fingerprints = set(unit.source_file_fingerprints)
            if not fingerprints or fingerprints & seen_source_fingerprints:
                continue
            seen_source_fingerprints.update(fingerprints)
            counts[dataset.dataset_kind] = counts.get(dataset.dataset_kind, 0) + 1
            total += 1
    return counts, total


def _gate_missing(gate: ActivationGate, counts: dict[str, int]) -> tuple[str, ...]:
    missing = [
        f"qualified {kind} dataset"
        for kind, required in gate.required_dataset_counts.items()
        if counts.get(kind, 0) < required
    ]
    missing.extend(
        f"{required} {key.replace('_', ' ')}"
        for key, required in gate.minimum_counts.items()
    )
    missing.extend(f"prerequisite: {key}" for key in gate.prerequisite_keys)
    missing.append(f"{gate.minimum_prospective_units} prospective real units")
    return tuple(dict.fromkeys(missing))


def capability_activation_matrix(
    *, db_path: str | Path | None = None
) -> tuple[CapabilityActivationAudit, ...]:
    gates = {item.capability_key: item for item in p22_field_activation_gates()}
    datasets, _ = _qualified_dataset_inventory(db_path)
    decisions = _latest_decisions(db_path)
    evaluations = _evaluation_artifacts(db_path)
    control_campaign = next(
        campaign for campaign in initial_campaigns() if campaign.campaign_kind == "control_workload"
    )
    control_progress = campaign_progress(control_campaign, db_path=db_path)
    rows = []
    for rank, key in enumerate(_RANK_ORDER, start=1):
        if key in _EXTRA_CANDIDATES:
            definition = _EXTRA_CANDIDATES[key]
            protocol = first_activation_protocol()
            missing = (
                "9 qualified historical source sessions",
                "90 historical clean laps",
                "10 qualified prospective source sessions",
                "100 prospective clean laps",
                "10 real null stints",
                "every required subgroup and negative control",
            )
            if key == "steering_yaw_transient_calibration":
                missing = (
                    "external yaw-delay reference",
                    "30 qualified independent sessions",
                    "validated body axes and steering conversion",
                    "10 qualified prospective units",
                )
            rows.append(
                CapabilityActivationAudit(
                    rank=rank,
                    capability_key=key,
                    label=definition["label"],
                    current_authority=definition["authority"],
                    required_gate_id=(
                        protocol.protocol_id
                        if key == "steering_workload_envelope"
                        else "p23-yaw-transient-not-preregistered"
                    ),
                    required_gate_hash=(
                        protocol.protocol_hash
                        if key == "steering_workload_envelope"
                        else None
                    ),
                    qualified_evidence_available=(),
                    qualified_evidence_missing=missing,
                    independent_unit_count=(
                        control_progress.independent_units
                        if key == "steering_workload_envelope"
                        else 0
                    ),
                    negative_control_state="not_started",
                    historical_validation_state="not_started",
                    prospective_validation_state="not_started",
                    subgroup_coverage={name: 0 for name in ("short_track", "intermediate", "superspeedway")},
                    vehicle_profile_prerequisites=definition["profile"],
                    estimated_realistic_collection_cost=definition["cost"],
                    earliest_legitimate_activation_path=definition["path"],
                    selection_reason=definition["reason"],
                    selected=key == "steering_workload_envelope",
                )
            )
            continue
        gate = gates[key]
        exact_decision = decisions.get(key)
        if exact_decision is not None and exact_decision.gate_hash != gate.gate_hash:
            exact_decision = None
        matching_evaluations = [item for item in evaluations if item.capability_key == key]
        latest = matching_evaluations[-1] if matching_evaluations else None
        controls_state: ValidationState = (
            "passed"
            if latest is not None and all(item.passed for item in latest.negative_controls)
            else "failed"
            if latest is not None
            else "not_started"
        )
        historical_state: ValidationState = (
            "passed"
            if latest is not None
            and latest.evaluation_mode == "historical_real"
            and latest.eligible_for_activation_review
            else "failed"
            if latest is not None and latest.evaluation_mode == "historical_real"
            else "not_started"
        )
        prospective_state: ValidationState = (
            "passed"
            if exact_decision is not None
            and exact_decision.state in {"eligible_for_limited_activation", "activated"}
            else "not_started"
        )
        available = tuple(
            f"{datasets[kind]} qualified real {kind} units"
            for kind in gate.required_dataset_counts
            if datasets.get(kind, 0) > 0
        )
        reason = (
            "Not selected: lower-risk evidence-quality candidates must pass first."
            if key not in {"driver_noise_envelope", "change_point"}
            else "Not selected: collection is feasible, but the reference and negative-control contract is less direct than the workload descriptor."
        )
        rows.append(
            CapabilityActivationAudit(
                rank=rank,
                capability_key=key,
                label=_GATE_LABELS[key],
                current_authority="shadow_only",
                required_gate_id=gate.gate_id,
                required_gate_hash=gate.gate_hash,
                qualified_evidence_available=available,
                qualified_evidence_missing=_gate_missing(gate, datasets),
                independent_unit_count=sum(
                    datasets.get(kind, 0) for kind in gate.required_dataset_counts
                ),
                negative_control_state=controls_state,
                historical_validation_state=historical_state,
                prospective_validation_state=prospective_state,
                subgroup_coverage={name: 0 for name in gate.subgroup_requirements},
                vehicle_profile_prerequisites=gate.prerequisite_keys,
                estimated_realistic_collection_cost=_COSTS[key],
                earliest_legitimate_activation_path=(
                    "Collect every required real dataset and prerequisite, pass whole-session held-out validation and all controls/subgroups, then pass at least ten frozen prospective units."
                ),
                selection_reason=reason,
            )
        )
    return tuple(rows)


def _stage(
    state: ValidationState,
    current: int,
    required: int,
    blocker: str,
    artifact_ids: tuple[str, ...] = (),
) -> P23ValidationStage:
    return P23ValidationStage(
        state=state,
        qualified_real_units=current,
        required_real_units=required,
        artifact_ids=artifact_ids,
        blockers=() if state == "passed" else (blocker,),
    )


def build_first_activation_audit(
    *,
    db_path: str | Path | None = None,
    created_at: datetime | None = None,
) -> P23FirstActivationAudit:
    protocol = first_activation_protocol()
    candidates = capability_activation_matrix(db_path=db_path)
    datasets = list_evidence_datasets(db_path=db_path)
    evaluations = _evaluation_artifacts(db_path)
    connection = initialize_database(db_path)
    try:
        prospective_predictions = int(
            connection.execute("SELECT COUNT(*) FROM prospective_test_predictions").fetchone()[0]
        )
        prospective_outcomes = int(
            connection.execute("SELECT COUNT(*) FROM prospective_test_outcomes").fetchone()[0]
        )
        attempts = int(
            connection.execute("SELECT COUNT(*) FROM evidence_campaign_attempts").fetchone()[0]
        )
        profiles = int(
            connection.execute("SELECT COUNT(*) FROM profile_validation_records").fetchone()[0]
        )
    finally:
        connection.close()
    archive_payload = {
        "datasets": tuple((item.dataset_id, item.dataset_hash) for item in datasets),
        "evaluations": tuple((item.evaluation_id, item.evaluation_hash) for item in evaluations),
        "campaign_attempts": attempts,
        "prospective_predictions": prospective_predictions,
        "prospective_outcomes": prospective_outcomes,
        "profile_validations": profiles,
    }
    payload = {
        "audit_version": "p23-first-earned-capability-v1",
        "created_at": created_at or datetime.now(timezone.utc),
        "archive_fingerprint": canonical_hash(archive_payload),
        "candidates": candidates,
        "selected_capability": "steering_workload_envelope",
        "selection_summary": (
            "The steering-workload envelope is the safest useful first candidate: it reuses the frozen P20 360 Hz descriptor, has exact FFB comparability and strong null/block controls, needs no vehicle geometry, and can never exceed a limited observation overlay."
        ),
        "protocol_id": protocol.protocol_id,
        "protocol_hash": protocol.protocol_hash,
        "historical": _stage(
            "not_started",
            0,
            protocol.dataset_requirements["historical_independent_sessions"],
            "No qualified historical control-workload dataset or exact frozen evaluation artifact exists.",
        ),
        "prospective": _stage(
            "not_started",
            0,
            protocol.minimum_prospective_units,
            "Historical validation has not passed, so prospective shadow collection cannot begin.",
        ),
        "negative_controls": _stage(
            "not_started",
            0,
            len(protocol.negative_control_ids),
            "No real-world negative-control evaluation exists for the selected protocol.",
        ),
        "subgroups": _stage(
            "not_started",
            0,
            len(protocol.required_subgroups),
            "No required subgroup has a qualified independent field unit.",
        ),
        "activation_decision": "no_activation_earned",
        "exact_authority_envelope": (),
        "remaining_locks": tuple(item.capability_key for item in candidates),
        "next_collection_missions": (
            "Run the P22 control-workload campaign for nine independent exact-FFB sessions with at least 90 clean laps across short, intermediate, and superspeedway tracks.",
            "Run ten same-setup/no-change null stints and the frozen stable-response, FFB-mismatch, traffic, line, integrity, build, and pit-boundary controls.",
            "Validate steering-conversion and every FFB fingerprint field for the exact Next Gen car/build before comparing sessions.",
            "After historical held-out validation passes unchanged thresholds, collect ten new prospective source sessions with predictions frozen before outcomes.",
        ),
        "p19_sole_reasoning_setup_authority": True,
        "p20_sole_state_projection": True,
    }
    identity = P23FirstActivationAudit.model_construct(
        audit_id="p23a-" + "0" * 20,
        audit_hash="0" * 64,
        **payload,
    ).model_dump(mode="json", exclude={"audit_id", "audit_hash"})
    digest = canonical_hash(identity)
    return P23FirstActivationAudit(
        audit_id=f"p23a-{digest[:20]}",
        audit_hash=digest,
        **payload,
    )


def save_first_activation_protocol(
    protocol: P23ValidationProtocol,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            version = connection.execute(
                "SELECT protocol_id, protocol_hash, protocol_json "
                "FROM p23_validation_protocols WHERE capability_key = ? AND protocol_version = ?",
                (protocol.candidate_capability, protocol.protocol_version),
            ).fetchone()
            if version is not None:
                if version[0] != protocol.protocol_id or version[1] != protocol.protocol_hash or (
                    P23ValidationProtocol.model_validate_json(version[2]) != protocol
                ):
                    raise ValueError(
                        "P23 thresholds are frozen; changed content requires a new protocol version"
                    )
                return False
            connection.execute(
                "INSERT INTO p23_validation_protocols "
                "(protocol_id, protocol_hash, protocol_version, capability_key, created_at, protocol_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    protocol.protocol_id,
                    protocol.protocol_hash,
                    protocol.protocol_version,
                    protocol.candidate_capability,
                    protocol.created_at.isoformat(),
                    protocol.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def save_first_activation_audit(
    audit: P23FirstActivationAudit,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            protocol = connection.execute(
                "SELECT protocol_hash FROM p23_validation_protocols WHERE protocol_id = ?",
                (audit.protocol_id,),
            ).fetchone()
            if protocol is None or protocol[0] != audit.protocol_hash:
                raise ValueError("P23 audit does not reference its persisted frozen protocol")
            existing = connection.execute(
                "SELECT audit_hash, audit_json FROM p23_activation_audits WHERE audit_id = ?",
                (audit.audit_id,),
            ).fetchone()
            if existing is not None:
                if existing[0] != audit.audit_hash or (
                    P23FirstActivationAudit.model_validate_json(existing[1]) != audit
                ):
                    raise ValueError("immutable P23 activation-audit identity collision")
                return False
            connection.execute(
                "INSERT INTO p23_activation_audits "
                "(audit_id, audit_hash, protocol_id, activation_decision, created_at, audit_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    audit.audit_id,
                    audit.audit_hash,
                    audit.protocol_id,
                    audit.activation_decision,
                    audit.created_at.isoformat(),
                    audit.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def latest_first_activation_audit(
    *, db_path: str | Path | None = None
) -> P23FirstActivationAudit | None:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT audit_json FROM p23_activation_audits "
            "ORDER BY created_at DESC, audit_id DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else P23FirstActivationAudit.model_validate_json(row[0])


__all__ = [
    "CapabilityActivationAudit",
    "P23FirstActivationAudit",
    "P23ValidationProtocol",
    "P23ValidationStage",
    "build_first_activation_audit",
    "capability_activation_matrix",
    "first_activation_protocol",
    "latest_first_activation_audit",
    "save_first_activation_audit",
    "save_first_activation_protocol",
]
