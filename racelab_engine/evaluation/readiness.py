"""Fast Learning Mode projection of scientific evidence readiness and debt."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field

from racelab_engine.evaluation.activation_gates import (
    ActivationDecision,
    p22_field_activation_gates,
)
from racelab_engine.evaluation.campaigns import campaign_progress, initial_campaigns
from racelab_engine.evaluation.dataset_registry import EvidenceDataset, EvidenceLabModel
from racelab_engine.evaluation.first_activation import (
    P23FirstActivationAudit,
    build_first_activation_audit,
)
from racelab_engine.evaluation.learning_operations import (
    AcquisitionOption,
    ActiveCampaignProjection,
    LearningLedgerEntry,
    acquisition_options,
    active_campaign_projections,
    learning_ledger,
)
from racelab_engine.services.session_service import get_session
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


class ReadinessCount(EvidenceLabModel):
    key: str
    label: str
    current: int = Field(ge=0)
    required: int = Field(ge=0)
    unit: str
    qualified_only: Literal[True] = True


class CampaignReadiness(EvidenceLabModel):
    campaign_kind: str
    label: str
    usable_units: int = Field(ge=0)
    required_units: int = Field(ge=1)
    invalid_attempts: int = Field(ge=0)
    remaining_units: int = Field(ge=0)
    state: Literal["not_started", "collecting", "complete"]


class CapabilityReadiness(EvidenceLabModel):
    capability_key: str
    label: str
    state: Literal["locked", "shadow", "descriptive_only", "deterministic"]
    summary: str
    blockers: tuple[str, ...]
    authority: Literal["p19_p20_unchanged"] = "p19_p20_unchanged"


class LearningDebt(EvidenceLabModel):
    debt_key: Literal[
        "geometry_unverified",
        "body_axis_unverified",
        "insufficient_null_data",
        "insufficient_controlled_workflows",
        "insufficient_track_diversity",
        "insufficient_build_diversity",
        "poor_subgroup_coverage",
        "calibration_failure",
        "negative_transfer",
        "profile_stale",
        "prospective_validation_required",
    ]
    summary: str
    collection_action: str


class CapabilityReviewItem(EvidenceLabModel):
    capability_key: str
    state: str
    historical_gate: Literal["pass", "fail", "pending"]
    prospective_gate: Literal["pass", "fail", "pending"]
    subgroup_gate: Literal["pass", "fail", "pending"]
    negative_control_gate: Literal["pass", "fail", "pending"]
    decision_id: str | None = None
    blockers: tuple[str, ...]


class AdvancedCapabilityReview(EvidenceLabModel):
    decision: Literal["remain_locked", "eligible_for_limited_activation"]
    eligible_capability_key: str | None = None
    explanation: str
    capabilities: tuple[CapabilityReviewItem, ...]
    manual_selection: Literal[False] = False
    authority: Literal["gate_review_only"] = "gate_review_only"


class LearningReadinessProjection(EvidenceLabModel):
    run_id: str
    session_id: str | None
    scope_key: str
    generated_at: datetime
    deterministic_authority: Literal["P19 reasoning / P20 awareness"] = (
        "P19 reasoning / P20 awareness"
    )
    advanced_models_summary: Literal["Shadow only"] = "Shadow only"
    archived_sessions: int = Field(ge=0)
    archived_runs: int = Field(ge=0)
    counts: tuple[ReadinessCount, ...]
    campaigns: tuple[CampaignReadiness, ...]
    capabilities: tuple[CapabilityReadiness, ...]
    vehicle_profile_status: str
    vehicle_profile_fields_ready: tuple[str, ...]
    vehicle_profile_fields_blocked: tuple[str, ...]
    debts: tuple[LearningDebt, ...]
    active_campaigns: tuple[ActiveCampaignProjection, ...] = ()
    acquisition_options: tuple[AcquisitionOption, ...] = ()
    learning_ledger: tuple[LearningLedgerEntry, ...] = ()
    capability_review: AdvancedCapabilityReview | None = None
    first_activation_audit: P23FirstActivationAudit | None = None
    offline_evaluation_only: Literal[True] = True


def _capability_review(
    *,
    db_path: str | Path | None,
) -> AdvancedCapabilityReview:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT decision_json FROM activation_decisions "
            "ORDER BY evaluated_at DESC, decision_id DESC"
        ).fetchall()
    finally:
        connection.close()
    latest: dict[str, ActivationDecision] = {}
    for row in rows:
        decision = ActivationDecision.model_validate_json(row[0])
        latest.setdefault(decision.capability_key, decision)
    items = []
    eligible = []
    for gate in p22_field_activation_gates():
        decision = latest.get(gate.capability_key)
        exact = decision is not None and decision.gate_hash == gate.gate_hash
        state = decision.state if exact and decision is not None else "locked_insufficient_data"
        evaluation = decision.evaluation if exact and decision is not None else None
        historical = (
            "pass"
            if state
            in {
                "eligible_for_prospective_shadow",
                "eligible_for_limited_activation",
                "activated",
            }
            else "fail"
            if state == "locked_failed_validation"
            else "pending"
        )
        prospective = (
            "pass"
            if state in {"eligible_for_limited_activation", "activated"}
            else "fail"
            if state == "locked_failed_validation"
            else "pending"
        )
        subgroup = (
            "fail"
            if evaluation is not None and evaluation.failed_subgroups
            else "pass"
            if evaluation is not None and evaluation.evaluation_artifact_id is not None
            else "pending"
        )
        controls = (
            "fail"
            if evaluation is not None and evaluation.failed_negative_controls
            else "pass"
            if evaluation is not None and evaluation.evaluation_artifact_id is not None
            else "pending"
        )
        blockers = (
            decision.blockers
            if exact and decision is not None
            else ("No exact current-gate activation decision has been earned.",)
        )
        items.append(
            CapabilityReviewItem(
                capability_key=gate.capability_key,
                state=state,
                historical_gate=historical,
                prospective_gate=prospective,
                subgroup_gate=subgroup,
                negative_control_gate=controls,
                decision_id=decision.decision_id if exact and decision is not None else None,
                blockers=blockers,
            )
        )
        if state == "eligible_for_limited_activation":
            eligible.append(gate.capability_key)
    eligible_key = sorted(eligible)[0] if eligible else None
    return AdvancedCapabilityReview(
        decision=(
            "eligible_for_limited_activation" if eligible_key else "remain_locked"
        ),
        eligible_capability_key=eligible_key,
        explanation=(
            f"{eligible_key} passed its exact frozen limited-activation gate."
            if eligible_key
            else "No advanced capability has passed historical, prospective, subgroup, and negative-control gates."
        ),
        capabilities=tuple(items),
    )


def build_learning_readiness_projection(
    run_id: str,
    *,
    session_id: str | None = None,
    db_path: str | Path | None = None,
) -> LearningReadinessProjection:
    repository = RaceLabRepository(db_path)
    if repository.get_overview(run_id) is None:
        raise ValueError(f"Run not found: {run_id}")
    if session_id is not None:
        session = get_session(session_id, db_path=db_path)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        if run_id not in session.run_ids:
            raise ValueError("Selected run is not a member of the requested session.")

    connection = initialize_database(db_path)
    try:
        dataset_rows = connection.execute(
            "SELECT dataset_json FROM evidence_datasets ORDER BY created_at, dataset_id"
        ).fetchall()
        session_table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'racelab_sessions'"
        ).fetchone()
        archived_sessions = (
            int(connection.execute("SELECT COUNT(*) FROM racelab_sessions").fetchone()[0])
            if session_table_exists
            else 0
        )
        archived_runs = int(connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        controlled_workflows = int(
            connection.execute(
                "SELECT COUNT(*) FROM controlled_test_workflows "
                "WHERE status = 'scored' AND learning_admitted = 1"
            ).fetchone()[0]
        )
        graded_predictions = int(
            connection.execute(
                "SELECT COUNT(*) FROM engineering_prediction_grades"
            ).fetchone()[0]
        )
        mission_attempts = int(
            connection.execute(
                "SELECT COUNT(*) FROM measurement_mission_attempts"
            ).fetchone()[0]
        )
        profile_rows = connection.execute(
            "SELECT field_key, state, created_at, record_id "
            "FROM profile_validation_records "
            "ORDER BY created_at DESC, record_id DESC"
        ).fetchall()
        prospective_predictions = int(
            connection.execute(
                "SELECT COUNT(*) FROM shadow_predictions WHERE prospective = 1"
            ).fetchone()[0]
        )
        prospective_test_predictions = int(
            connection.execute(
                "SELECT COUNT(*) FROM prospective_test_predictions"
            ).fetchone()[0]
        )
    finally:
        connection.close()

    datasets = tuple(
        EvidenceDataset.model_validate_json(row[0]) for row in dataset_rows
    )
    qualified_units = [
        unit
        for dataset in datasets
        if dataset.qualification.state == "qualified"
        for unit in dataset.units
        if not unit.synthetic
    ]
    qualified_sessions = {
        session
        for unit in qualified_units
        for session in unit.source_session_ids
        if unit.independence_level.value == "session"
    }
    qualified_stints = {
        stint
        for unit in qualified_units
        for stint in unit.source_stint_ids
        if unit.independence_level.value == "stint"
    }
    null_stints = {
        unit.unit_id
        for dataset in datasets
        if dataset.dataset_kind == "null_no_change"
        and dataset.qualification.state == "qualified"
        for unit in dataset.units
        if not unit.synthetic
    }
    eligible_laps = sum(
        dataset.manifest.lap_count
        for dataset in datasets
        if dataset.qualification.state == "qualified"
        and dataset.dataset_kind in {"driver_repeatability", "same_setup_repeatability"}
    )
    tracks = {
        identity
        for dataset in datasets
        if dataset.qualification.state == "qualified"
        for identity in dataset.manifest.track_identities
    }
    builds = {
        identity
        for dataset in datasets
        if dataset.qualification.state == "qualified"
        for identity in dataset.manifest.iracing_build_identities
    }

    latest_profile_state: dict[str, str] = {}
    for row in profile_rows:
        latest_profile_state.setdefault(str(row["field_key"]), str(row["state"]))
    geometry_fields = ("wheelbase", "front_track_width", "rear_track_width")
    fields_ready = tuple(
        field
        for field, state in sorted(latest_profile_state.items())
        if state == "empirically_confirmed"
    )
    fields_blocked = tuple(
        field
        for field in geometry_fields
        if latest_profile_state.get(field) != "empirically_confirmed"
    )
    profile_status = "geometry ready" if not fields_blocked else "geometry incomplete"

    counts = (
        ReadinessCount(
            key="controlled_workflows",
            label="Controlled workflows",
            current=controlled_workflows,
            required=100,
            unit="complete A/B/A2 workflows",
        ),
        ReadinessCount(
            key="independent_sessions",
            label="Independent sessions",
            current=len(qualified_sessions),
            required=30,
            unit="qualified sessions",
        ),
        ReadinessCount(
            key="eligible_laps",
            label="Driver-noise laps",
            current=eligible_laps,
            required=30,
            unit="eligible laps in qualified sessions",
        ),
        ReadinessCount(
            key="null_stints",
            label="Null stints",
            current=len(null_stints),
            required=10,
            unit="known no-change stints",
        ),
        ReadinessCount(
            key="graded_predictions",
            label="Graded predictions",
            current=graded_predictions,
            required=100,
            unit="independent frozen outcomes",
        ),
        ReadinessCount(
            key="prospective_predictions",
            label="Prospective shadow",
            current=prospective_predictions + prospective_test_predictions,
            required=10,
            unit="immutable predictions",
        ),
    )
    campaign_items = []
    labels = {
        "driver_noise_baseline": "Driver noise baseline",
        "controlled_setup_response": "Controlled setup response",
        "tire_update_semantics": "Tire update semantics",
        "long_run_development": "Long-run development",
        "vehicle_geometry_validation": "Vehicle geometry",
        "control_workload": "Control workload",
        "no_change_null": "No-change null",
    }
    for campaign in initial_campaigns():
        progress = campaign_progress(campaign, db_path=db_path)
        state: Literal["not_started", "collecting", "complete"] = (
            "complete"
            if progress.complete
            else "collecting"
            if progress.usable_attempts or progress.invalid_attempts
            else "not_started"
        )
        campaign_items.append(
            CampaignReadiness(
                campaign_kind=campaign.campaign_kind,
                label=labels[campaign.campaign_kind],
                usable_units=progress.independent_units,
                required_units=campaign.acceptance_criteria.minimum_independent_units,
                invalid_attempts=progress.invalid_attempts,
                remaining_units=progress.remaining_independent_units,
                state=state,
            )
        )

    capabilities = (
        CapabilityReadiness(
            capability_key="probability_calibration",
            label="Probability calibration",
            state="locked",
            summary="Ordinal evidence remains authoritative.",
            blockers=("Independent held-out and prospective outcomes are insufficient.",),
        ),
        CapabilityReadiness(
            capability_key="change_point",
            label="Change-point model",
            state="shadow",
            summary="Offline candidates only; P20 deterministic drift remains production truth.",
            blockers=(
                f"Need 30 uninterrupted stints and 10 null stints; have "
                f"{len(qualified_stints)} and {len(null_stints)}.",
            ),
        ),
        CapabilityReadiness(
            capability_key="shadow_sideslip",
            label="Sideslip observer",
            state="locked",
            summary="Research contract is blocked by vehicle and gravity prerequisites.",
            blockers=tuple(f"Profile field unavailable: {field}." for field in fields_blocked)
            or ("Body-axis and bank/gravity validation are incomplete.",),
        ),
        CapabilityReadiness(
            capability_key="formal_information_gain",
            label="Information-gain planner",
            state="locked",
            summary="The deterministic P19 measurement planner remains authoritative.",
            blockers=(f"Only {mission_attempts} durable mission attempts are available.",),
        ),
        CapabilityReadiness(
            capability_key="response_model",
            label="Response model",
            state="descriptive_only",
            summary="Mechanism, response, countereffect, and policy targets remain separate.",
            blockers=(f"Only {controlled_workflows} qualified workflows are available.",),
        ),
        CapabilityReadiness(
            capability_key="bayesian_optimization",
            label="Bayesian optimization",
            state="locked",
            summary="No production optimization authority.",
            blockers=("Controlled history and prospective safety gates are not met.",),
        ),
        CapabilityReadiness(
            capability_key="multi_control_optimization",
            label="Multi-control optimization",
            state="locked",
            summary="Single-control foundations have not earned multi-control authority.",
            blockers=("Protocol-valid multi-factor evidence is unavailable.",),
        ),
    )

    debts: list[LearningDebt] = []
    if controlled_workflows < 30:
        debts.append(
            LearningDebt(
                debt_key="insufficient_controlled_workflows",
                summary="Too few protocol-valid A/B/A2 workflows.",
                collection_action="Complete one-control A/B/A2 campaigns with restoration.",
            )
        )
    if len(null_stints) < 10:
        debts.append(
            LearningDebt(
                debt_key="insufficient_null_data",
                summary="False-positive behavior is not yet measurable.",
                collection_action="Collect known no-change uninterrupted stints.",
            )
        )
    if fields_blocked:
        debts.append(
            LearningDebt(
                debt_key="geometry_unverified",
                summary="Geometry-dependent shadows are blocked.",
                collection_action="Validate wheelbase and both track widths for the exact build.",
            )
        )
    if latest_profile_state.get("body_axes") != "empirically_confirmed":
        debts.append(
            LearningDebt(
                debt_key="body_axis_unverified",
                summary="Body-axis and gravity interpretation are not validated.",
                collection_action="Validate body axes and gravity convention for the exact build.",
            )
        )
    if len(tracks) < 3:
        debts.append(
            LearningDebt(
                debt_key="insufficient_track_diversity",
                summary="Qualified evidence does not cover three track contexts.",
                collection_action="Qualify short-track, intermediate, and superspeedway sessions.",
            )
        )
    if len(builds) < 1:
        debts.append(
            LearningDebt(
                debt_key="insufficient_build_diversity",
                summary="No qualified dataset pins an iRacing build identity.",
                collection_action="Register exact build identity in qualified datasets.",
            )
        )
    debts.append(
        LearningDebt(
            debt_key="prospective_validation_required",
            summary="Historical success cannot activate a shadow model.",
            collection_action="Record immutable predictions before new-session outcomes.",
        )
    )
    scope_key = f"{run_id}:{session_id or 'no-session'}"
    first_activation = build_first_activation_audit(db_path=db_path)
    ledger = learning_ledger(db_path=db_path) + (
        LearningLedgerEntry(
            ledger_key="p23:first_activation",
            section="in_validation",
            label="P23 steering-workload envelope",
            summary=(
                "Frozen protocol; no activation earned. Historical field validation has not started."
            ),
            current=first_activation.historical.qualified_real_units,
            required=first_activation.historical.required_real_units,
            evidence_basis="frozen_gate_policy",
        ),
    )
    return LearningReadinessProjection(
        run_id=run_id,
        session_id=session_id,
        scope_key=scope_key,
        generated_at=datetime.now(timezone.utc),
        archived_sessions=archived_sessions,
        archived_runs=archived_runs,
        counts=counts,
        campaigns=tuple(campaign_items),
        capabilities=capabilities,
        vehicle_profile_status=profile_status,
        vehicle_profile_fields_ready=fields_ready,
        vehicle_profile_fields_blocked=fields_blocked,
        debts=tuple(debts),
        active_campaigns=active_campaign_projections(db_path=db_path),
        acquisition_options=acquisition_options(run_id, db_path=db_path),
        learning_ledger=ledger,
        capability_review=_capability_review(db_path=db_path),
        first_activation_audit=first_activation,
    )


__all__ = [
    "CampaignReadiness",
    "AdvancedCapabilityReview",
    "CapabilityReviewItem",
    "CapabilityReadiness",
    "LearningDebt",
    "LearningReadinessProjection",
    "ReadinessCount",
    "build_learning_readiness_projection",
]
