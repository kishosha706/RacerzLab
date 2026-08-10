"""P22 prospective campaign operations and deterministic acquisition guidance.

This module makes P21 campaign contracts executable. It may qualify evidence
collection, but it cannot rank causes, change setup, stop a P19 mission, or grant
statistical authority.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.evaluation.campaigns import (
    CampaignKind,
    CampaignProgress,
    EvidenceCampaign,
    append_campaign_attempt,
    build_campaign_attempt,
    campaign_progress,
    initial_campaigns,
    save_campaign,
)
from racelab_engine.evaluation.dataset_registry import EvidenceLabModel, canonical_hash
from racelab_engine.services.engineering_context_service import detect_control_mutations
from racelab_engine.services.import_service import read_telemetry_manifest, read_telemetry_rows
from racelab_engine.services.lap_engineering_context_service import (
    load_lap_engineering_context_report,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


OperationEventType = Literal["started", "paused", "resumed", "completed", "abandoned"]
OperationState = Literal["active", "paused", "completed", "abandoned"]
AssessmentState = Literal["usable", "rejected", "pending_protocol", "infeasible"]

_OPERATION_TRANSITIONS: dict[
    tuple[OperationState | None, OperationEventType], OperationState
] = {
    (None, "started"): "active",
    ("active", "paused"): "paused",
    ("paused", "resumed"): "active",
    ("active", "completed"): "completed",
    ("paused", "completed"): "completed",
    ("active", "abandoned"): "abandoned",
    ("paused", "abandoned"): "abandoned",
}

_CONTROL_CHANNELS = (
    "session_time",
    "lap",
    "lap_number",
    "lap_dist_pct_100",
    "applied_brake_bias",
    "dcBrakeBias",
    "requested_lf_tire_cold_pressure_pa",
    "requested_rf_tire_cold_pressure_pa",
    "requested_lr_tire_cold_pressure_pa",
    "requested_rr_tire_cold_pressure_pa",
    "requested_left_tire_change",
    "requested_right_tire_change",
    "requested_fuel_fill",
    "requested_fuel_add_kg",
)


class NumericBand(EvidenceLabModel):
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self) -> NumericBand:
        if self.maximum < self.minimum:
            raise ValueError("context bands must be ordered")
        return self


class CampaignOperationContext(EvidenceLabModel):
    reference_run_id: str = Field(min_length=1)
    source_file_fingerprint: str = Field(min_length=7)
    car_path: str = Field(min_length=1)
    track_id: str = Field(min_length=1)
    iracing_build_version: str = Field(min_length=1)
    setup_fingerprint: str | None = None
    fuel_band: NumericBand | None = None
    track_temperature_band: NumericBand | None = None
    air_temperature_band: NumericBand | None = None
    maximum_traffic_exposure_fraction: float = Field(default=0.05, ge=0.0, le=1.0)
    minimum_clean_laps_per_unit: int = Field(ge=0)
    exact_track_required: bool = True
    exact_setup_required: bool = True
    reject_control_mutations: bool = True


class CampaignOperation(EvidenceLabModel):
    operation_id: str = Field(pattern=r"^eco-[0-9a-f]{20}$")
    operation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_version: str = Field(min_length=1)
    campaign_id: str
    campaign_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_kind: CampaignKind
    created_at: datetime
    context: CampaignOperationContext
    allowed_outputs: tuple[Literal["qualification", "collection_guidance"], ...] = (
        "qualification",
        "collection_guidance",
    )
    authority: Literal["data_collection_only"] = "data_collection_only"

    @model_validator(mode="after")
    def identity_is_immutable(self) -> CampaignOperation:
        payload = self.model_dump(mode="json", exclude={"operation_id", "operation_hash"})
        digest = canonical_hash(payload)
        if self.operation_hash != digest or self.operation_id != f"eco-{digest[:20]}":
            raise ValueError("campaign-operation identity does not match its contract")
        return self


class CampaignOperationEvent(EvidenceLabModel):
    event_id: str = Field(pattern=r"^ece-[0-9a-f]{20}$")
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str
    operation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: datetime
    event_type: OperationEventType
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def identity_is_immutable(self) -> CampaignOperationEvent:
        payload = self.model_dump(mode="json", exclude={"event_id", "event_hash"})
        digest = canonical_hash(payload)
        if self.event_hash != digest or self.event_id != f"ece-{digest[:20]}":
            raise ValueError("campaign-operation event identity does not match its content")
        return self


class CampaignRunAssessment(EvidenceLabModel):
    assessment_id: str = Field(pattern=r"^ecr-[0-9a-f]{20}$")
    assessment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str
    operation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_id: str
    campaign_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    recorded_at: datetime
    source_file_fingerprint: str = Field(min_length=7)
    independence_unit_id: str = Field(min_length=1)
    state: AssessmentState
    accepted_lap_numbers: tuple[int, ...] = ()
    rejected_lap_numbers: tuple[int, ...] = ()
    lap_rejection_reasons: dict[int, tuple[str, ...]] = Field(default_factory=dict)
    rejection_reasons: tuple[str, ...] = ()
    qualified_context: tuple[str, ...] = ()
    control_mutation_ids: tuple[str, ...] = ()
    promoted_to_p21_attempt: bool = False
    authority: Literal["qualification_only"] = "qualification_only"

    @model_validator(mode="after")
    def result_is_explained_and_immutable(self) -> CampaignRunAssessment:
        if set(self.accepted_lap_numbers) & set(self.rejected_lap_numbers):
            raise ValueError("one lap cannot be both accepted and rejected")
        if set(self.lap_rejection_reasons) != set(self.rejected_lap_numbers):
            raise ValueError("every rejected lap requires exact per-lap reasons")
        if any(not reasons for reasons in self.lap_rejection_reasons.values()):
            raise ValueError("rejected-lap reasons cannot be empty")
        if self.state == "usable" and self.rejection_reasons:
            raise ValueError("usable run assessments cannot retain rejection reasons")
        if self.state != "usable" and not self.rejection_reasons:
            raise ValueError("non-usable run assessments must explain why")
        payload = self.model_dump(mode="json", exclude={"assessment_id", "assessment_hash"})
        digest = canonical_hash(payload)
        if self.assessment_hash != digest or self.assessment_id != f"ecr-{digest[:20]}":
            raise ValueError("campaign-run assessment identity does not match its content")
        return self


class AcquisitionScoreComponents(EvidenceLabModel):
    deficit_fraction: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    rule_fit_estimate: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    gates_helped: int = Field(ge=0)
    estimated_driver_laps: int = Field(ge=0)
    deterministic_value: float = Field(ge=0.0, allow_inf_nan=False)
    formal_information_gain: Literal[False] = False


class AcquisitionOption(EvidenceLabModel):
    campaign_kind: CampaignKind
    label: str
    state: Literal["highest", "candidate", "infeasible"]
    helps: tuple[str, ...]
    need_next: tuple[str, ...]
    blockers: tuple[str, ...]
    score: AcquisitionScoreComponents
    authority: Literal["collection_guidance_only"] = "collection_guidance_only"


class LearningLedgerEntry(EvidenceLabModel):
    ledger_key: str = Field(min_length=1)
    section: Literal["proven_guardrail", "in_validation", "failed_validation", "locked"]
    label: str
    summary: str
    current: int | None = Field(default=None, ge=0)
    required: int | None = Field(default=None, ge=0)
    evidence_basis: Literal[
        "verified_architecture",
        "qualified_real_evidence",
        "frozen_gate_policy",
    ]
    authority: Literal["p19_p20_unchanged"] = "p19_p20_unchanged"


class ActiveCampaignProjection(EvidenceLabModel):
    operation: CampaignOperation
    state: OperationState
    progress: CampaignProgress
    latest_assessment: CampaignRunAssessment | None = None
    prospective_prediction_count: int = Field(default=0, ge=0)
    unscored_prediction_count: int = Field(default=0, ge=0)


def _content_addressed(model: type[EvidenceLabModel], prefix: str, payload: dict[str, Any]):
    identity_name = {
        "eco": ("operation_id", "operation_hash"),
        "ece": ("event_id", "event_hash"),
        "ecr": ("assessment_id", "assessment_hash"),
    }[prefix]
    identity_field, hash_field = identity_name
    constructed = model.model_construct(
        **{identity_field: f"{prefix}-" + "0" * 20, hash_field: "0" * 64, **payload}
    )
    digest = canonical_hash(
        constructed.model_dump(mode="json", exclude={identity_field, hash_field})
    )
    return model(**{identity_field: f"{prefix}-{digest[:20]}", hash_field: digest, **payload})


def _campaign(kind: CampaignKind) -> EvidenceCampaign:
    return next(item for item in initial_campaigns() if item.campaign_kind == kind)


def _finite_values(semantics: list[Any]) -> list[float]:
    values: list[float] = []
    for semantic in semantics:
        for value in (semantic.start_value, semantic.end_value, semantic.minimum_value, semantic.maximum_value):
            if value is not None:
                values.append(float(value))
    return values


def _band(values: list[float], padding: float) -> NumericBand | None:
    return None if not values else NumericBand(minimum=min(values) - padding, maximum=max(values) + padding)


def _setup_fingerprint(overview: Any) -> str | None:
    return (
        None
        if overview.setup_snapshot is None
        else canonical_hash(overview.setup_snapshot.model_dump(mode="json"))
    )


def build_campaign_operation(
    campaign_kind: CampaignKind,
    reference_run_id: str,
    *,
    db_path: str | Path | None = None,
    created_at: datetime | None = None,
) -> CampaignOperation:
    campaign = _campaign(campaign_kind)
    overview = RaceLabRepository(db_path).get_overview(reference_run_id)
    if overview is None:
        raise ValueError(f"Run not found: {reference_run_id}")
    manifest = read_telemetry_manifest(reference_run_id)
    identity = manifest.get("compatibility_identity") or {}
    source_fingerprint = str(
        manifest.get("source_file_sha256") or overview.session.file_hash or ""
    ).strip()
    car_path = str(identity.get("car_path") or overview.session.car_path or "").strip()
    track_id = str(
        identity.get("track_id")
        or identity.get("track_id_or_path")
        or overview.session.track_id_or_path
        or ""
    ).strip()
    build_version = str(identity.get("iracing_build_version") or "").strip()
    blockers = []
    if len(source_fingerprint) < 7:
        blockers.append("immutable source-file fingerprint")
    if not car_path:
        blockers.append("car identity")
    if not track_id:
        blockers.append("track identity")
    if not build_version:
        blockers.append("iRacing build identity")
    setup_fingerprint = _setup_fingerprint(overview)
    if campaign.required_setup_snapshots and setup_fingerprint is None:
        blockers.append("complete setup snapshot")
    if blockers:
        raise ValueError(
            "Campaign cannot start until the reference run has: " + ", ".join(blockers) + "."
        )
    # Geometry validation is an external source-integrity campaign.  It must be
    # startable even when the reference recording cannot supply lap context;
    # the campaign exists precisely to replace missing vehicle constants.
    eligible_numbers = {lap.lap_number for lap in eligible_laps(overview.laps)}
    if campaign_kind == "vehicle_geometry_validation":
        contexts = []
    else:
        try:
            context_report = load_lap_engineering_context_report(
                reference_run_id, db_path=db_path
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise ValueError(
                "Campaign cannot freeze eligible-lap engineering context from this run."
            ) from exc
        contexts = [
            item
            for item in context_report.contexts
            if item.lap_number in eligible_numbers
        ]
    minimum_laps = {
        "driver_noise_baseline": 10,
        "controlled_setup_response": 9,
        "tire_update_semantics": 0,
        "long_run_development": 20,
        "vehicle_geometry_validation": 0,
        "control_workload": 10,
        "no_change_null": 10,
    }[campaign_kind]
    exact_track_required = campaign_kind not in {
        "tire_update_semantics",
        "vehicle_geometry_validation",
    }
    exact_setup_required = campaign.required_setup_snapshots
    fuel_band = _band(_finite_values([item.fuel_level for item in contexts]), 0.25)
    track_temperature_band = _band(
        _finite_values([item.track_temperature for item in contexts]), 2.0
    )
    air_temperature_band = _band(
        _finite_values([item.air_temperature for item in contexts]), 2.0
    )
    if campaign_kind not in {"tire_update_semantics", "vehicle_geometry_validation"}:
        missing_bands = [
            label
            for label, band in (
                ("fuel", fuel_band),
                ("track temperature", track_temperature_band),
                ("air temperature", air_temperature_band),
            )
            if band is None
        ]
        if missing_bands:
            raise ValueError(
                "Campaign cannot freeze matched context without eligible-lap "
                + ", ".join(missing_bands)
                + " evidence."
            )
    operation_context = CampaignOperationContext(
        reference_run_id=reference_run_id,
        source_file_fingerprint=source_fingerprint,
        car_path=car_path,
        track_id=track_id,
        iracing_build_version=build_version,
        setup_fingerprint=setup_fingerprint,
        fuel_band=fuel_band,
        track_temperature_band=track_temperature_band,
        air_temperature_band=air_temperature_band,
        minimum_clean_laps_per_unit=minimum_laps,
        exact_track_required=exact_track_required,
        exact_setup_required=exact_setup_required,
        reject_control_mutations=campaign_kind not in {
            "tire_update_semantics",
            "vehicle_geometry_validation",
        },
    )
    payload = {
        "operation_version": "p22-campaign-operation-v1",
        "campaign_id": campaign.campaign_id,
        "campaign_hash": campaign.campaign_hash,
        "campaign_kind": campaign.campaign_kind,
        "created_at": created_at or datetime.now(timezone.utc),
        "context": operation_context,
        "allowed_outputs": ("qualification", "collection_guidance"),
        "authority": "data_collection_only",
    }
    return _content_addressed(CampaignOperation, "eco", payload)


def build_operation_event(
    operation: CampaignOperation,
    event_type: OperationEventType,
    reason: str,
    *,
    recorded_at: datetime | None = None,
) -> CampaignOperationEvent:
    return _content_addressed(
        CampaignOperationEvent,
        "ece",
        {
            "operation_id": operation.operation_id,
            "operation_hash": operation.operation_hash,
            "recorded_at": recorded_at or datetime.now(timezone.utc),
            "event_type": event_type,
            "reason": reason,
        },
    )


def save_campaign_operation(
    operation: CampaignOperation,
    *,
    db_path: str | Path | None = None,
) -> bool:
    campaign = _campaign(operation.campaign_kind)
    if campaign.campaign_id != operation.campaign_id or campaign.campaign_hash != operation.campaign_hash:
        raise ValueError("operation does not match the frozen campaign contract")
    save_campaign(campaign, db_path=db_path)
    connection = initialize_database(db_path)
    try:
        with connection:
            row = connection.execute(
                "SELECT operation_hash, operation_json FROM evidence_campaign_operations "
                "WHERE operation_id = ?",
                (operation.operation_id,),
            ).fetchone()
            if row is not None:
                if row["operation_hash"] != operation.operation_hash or (
                    CampaignOperation.model_validate_json(row["operation_json"]) != operation
                ):
                    raise ValueError("immutable campaign-operation identity collision")
                return False
            connection.execute(
                "INSERT INTO evidence_campaign_operations "
                "(operation_id, operation_hash, campaign_id, created_at, operation_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    operation.operation_id,
                    operation.operation_hash,
                    operation.campaign_id,
                    operation.created_at.isoformat(),
                    operation.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def append_operation_event(
    event: CampaignOperationEvent,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            operation = connection.execute(
                "SELECT operation_hash FROM evidence_campaign_operations WHERE operation_id = ?",
                (event.operation_id,),
            ).fetchone()
            if operation is None or operation["operation_hash"] != event.operation_hash:
                raise ValueError("operation event does not match a stored operation")
            existing = connection.execute(
                "SELECT event_hash, event_json FROM evidence_campaign_operation_events "
                "WHERE event_id = ?",
                (event.event_id,),
            ).fetchone()
            if existing is not None:
                if existing["event_hash"] != event.event_hash or (
                    CampaignOperationEvent.model_validate_json(existing["event_json"]) != event
                ):
                    raise ValueError("immutable operation-event identity collision")
                return False
            prior_rows = connection.execute(
                "SELECT event_json FROM evidence_campaign_operation_events "
                "WHERE operation_id = ? ORDER BY rowid",
                (event.operation_id,),
            ).fetchall()
            state: OperationState | None = None
            prior_events = [
                CampaignOperationEvent.model_validate_json(row[0]) for row in prior_rows
            ]
            for prior_event in prior_events:
                next_state = _OPERATION_TRANSITIONS.get((state, prior_event.event_type))
                if next_state is None:
                    raise ValueError(
                        "campaign operation contains an invalid lifecycle transition"
                    )
                state = next_state
            if _OPERATION_TRANSITIONS.get((state, event.event_type)) is None:
                raise ValueError(
                    f"Cannot append {event.event_type} while operation is "
                    f"{state or 'not started'}."
                )
            if prior_events and event.recorded_at < prior_events[-1].recorded_at:
                raise ValueError("operation events cannot move backward in time")
            connection.execute(
                "INSERT INTO evidence_campaign_operation_events "
                "(event_id, event_hash, operation_id, recorded_at, event_type, event_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.event_hash,
                    event.operation_id,
                    event.recorded_at.isoformat(),
                    event.event_type,
                    event.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def operation_state(
    operation_id: str,
    *,
    db_path: str | Path | None = None,
) -> OperationState:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT event_json FROM evidence_campaign_operation_events "
            "WHERE operation_id = ? ORDER BY rowid",
            (operation_id,),
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        raise ValueError("campaign operation has no lifecycle event")
    events = [CampaignOperationEvent.model_validate_json(row[0]) for row in rows]
    state: OperationState | None = None
    for event in events:
        next_state = _OPERATION_TRANSITIONS.get((state, event.event_type))
        if next_state is None:
            raise ValueError("campaign operation contains an invalid lifecycle transition")
        state = next_state
    assert state is not None
    return state


def start_campaign_operation(
    campaign_kind: CampaignKind,
    reference_run_id: str,
    *,
    db_path: str | Path | None = None,
    created_at: datetime | None = None,
) -> CampaignOperation:
    for existing in list_campaign_operations(db_path=db_path):
        if (
            existing.campaign_kind == campaign_kind
            and existing.context.reference_run_id == reference_run_id
            and operation_state(existing.operation_id, db_path=db_path) in {"active", "paused"}
        ):
            return existing
    operation = build_campaign_operation(
        campaign_kind,
        reference_run_id,
        db_path=db_path,
        created_at=created_at,
    )
    save_campaign_operation(operation, db_path=db_path)
    append_operation_event(
        build_operation_event(
            operation,
            "started",
            "Driver started the frozen evidence campaign operation.",
            recorded_at=created_at,
        ),
        db_path=db_path,
    )
    return operation


def transition_campaign_operation(
    operation_id: str,
    event_type: Literal["paused", "resumed", "completed", "abandoned"],
    reason: str,
    *,
    db_path: str | Path | None = None,
    recorded_at: datetime | None = None,
) -> CampaignOperationEvent:
    operation = next(
        (
            item
            for item in list_campaign_operations(db_path=db_path)
            if item.operation_id == operation_id
        ),
        None,
    )
    if operation is None:
        raise ValueError(f"Campaign operation not found: {operation_id}")
    current = operation_state(operation_id, db_path=db_path)
    allowed: dict[OperationState, tuple[OperationEventType, ...]] = {
        "active": ("paused", "completed", "abandoned"),
        "paused": ("resumed", "completed", "abandoned"),
        "completed": (),
        "abandoned": (),
    }
    if event_type not in allowed[current]:
        raise ValueError(f"Cannot record {event_type} while operation is {current}.")
    event = build_operation_event(
        operation,
        event_type,
        reason,
        recorded_at=recorded_at,
    )
    append_operation_event(event, db_path=db_path)
    return event


def list_campaign_operations(
    *,
    db_path: str | Path | None = None,
) -> tuple[CampaignOperation, ...]:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT operation_json FROM evidence_campaign_operations "
            "ORDER BY created_at, operation_id"
        ).fetchall()
    finally:
        connection.close()
    return tuple(CampaignOperation.model_validate_json(row[0]) for row in rows)


def _in_band(value: float | None, band: NumericBand | None) -> bool:
    return band is None or (value is not None and band.minimum <= value <= band.maximum)


def _semantic_center(semantic: Any) -> float | None:
    values = [value for value in (semantic.start_value, semantic.end_value) if value is not None]
    return None if not values else sum(float(value) for value in values) / len(values)


def assess_run_for_operation(
    operation: CampaignOperation,
    run_id: str,
    *,
    db_path: str | Path | None = None,
    recorded_at: datetime | None = None,
) -> CampaignRunAssessment:
    if operation_state(operation.operation_id, db_path=db_path) != "active":
        raise ValueError("only an active campaign operation may assess imported runs")
    overview = RaceLabRepository(db_path).get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    manifest = read_telemetry_manifest(run_id)
    identity = manifest.get("compatibility_identity") or {}
    fingerprint = str(manifest.get("source_file_sha256") or overview.session.file_hash or "").strip()
    reasons: list[str] = []
    if len(fingerprint) < 7:
        fingerprint = f"missing:{run_id}"
        reasons.append("Immutable source-file fingerprint is unavailable.")
    connection = initialize_database(db_path)
    try:
        duplicate = connection.execute(
            "SELECT assessment_id FROM evidence_campaign_run_assessments "
            "WHERE operation_id = ? AND source_file_fingerprint = ? AND state = 'usable' "
            "AND run_id <> ? LIMIT 1",
            (operation.operation_id, fingerprint, run_id),
        ).fetchone()
    finally:
        connection.close()
    if duplicate is not None:
        reasons.append("This source telemetry already counted as one independence unit.")
    context = operation.context
    car_path = str(identity.get("car_path") or overview.session.car_path or "").strip()
    track_id = str(
        identity.get("track_id")
        or identity.get("track_id_or_path")
        or overview.session.track_id_or_path
        or ""
    ).strip()
    build_version = str(identity.get("iracing_build_version") or "").strip()
    if car_path != context.car_path:
        reasons.append("Car identity does not match the operation contract.")
    if context.exact_track_required and track_id != context.track_id:
        reasons.append("Track identity does not match the operation contract.")
    if build_version != context.iracing_build_version:
        reasons.append("iRacing build identity does not match the operation contract.")
    if context.exact_setup_required and _setup_fingerprint(overview) != context.setup_fingerprint:
        reasons.append("Setup snapshot does not match the frozen operation setup.")
    control_rows = read_telemetry_rows(run_id, columns=list(_CONTROL_CHANNELS))
    mutations = detect_control_mutations(control_rows, run_id=run_id)
    if context.reject_control_mutations and mutations:
        reasons.append("A material or requested control changed inside the recording.")
    accepted: list[int] = []
    rejected: list[int] = []
    lap_rejection_reasons: dict[int, tuple[str, ...]] = {}
    context_report = load_lap_engineering_context_report(run_id, db_path=db_path)
    by_lap = {item.lap_number: item for item in context_report.contexts}
    for lap in eligible_laps(overview.laps):
        item = by_lap.get(lap.lap_number)
        lap_reasons = []
        if item is None or item.blocker_reasons:
            lap_reasons.append("engineering context is incomplete")
        else:
            traffic = item.nearby_traffic_exposure_fraction
            if traffic is None or traffic > context.maximum_traffic_exposure_fraction:
                lap_reasons.append("nearby-car context is contaminated or unknown")
            if not _in_band(_semantic_center(item.fuel_level), context.fuel_band):
                lap_reasons.append("fuel is outside the frozen band")
            if not _in_band(
                _semantic_center(item.track_temperature), context.track_temperature_band
            ):
                lap_reasons.append("track temperature is outside the frozen band")
            if not _in_band(_semantic_center(item.air_temperature), context.air_temperature_band):
                lap_reasons.append("air temperature is outside the frozen band")
        if lap_reasons:
            rejected.append(lap.lap_number)
            lap_rejection_reasons[lap.lap_number] = tuple(lap_reasons)
        else:
            accepted.append(lap.lap_number)
    protocol_only = operation.campaign_kind in {
        "controlled_setup_response",
        "tire_update_semantics",
        "vehicle_geometry_validation",
        "control_workload",
        "no_change_null",
    }
    if protocol_only:
        state: AssessmentState = "pending_protocol"
        reasons.append("This campaign requires a controlled workflow or external validation record.")
    elif reasons:
        state = "rejected"
    elif len(accepted) < context.minimum_clean_laps_per_unit:
        state = "rejected"
        reasons.append(
            f"Only {len(accepted)} clean laps qualify; "
            f"{context.minimum_clean_laps_per_unit} are required."
        )
    elif operation.campaign_kind == "long_run_development" and any(
        right != left + 1 for left, right in zip(accepted, accepted[1:])
    ):
        state = "rejected"
        reasons.append("The qualifying laps are not one uninterrupted clean stint.")
    else:
        state = "usable"
    payload = {
        "operation_id": operation.operation_id,
        "operation_hash": operation.operation_hash,
        "campaign_id": operation.campaign_id,
        "campaign_hash": operation.campaign_hash,
        "run_id": run_id,
        "recorded_at": recorded_at or datetime.now(timezone.utc),
        "source_file_fingerprint": fingerprint,
        "independence_unit_id": f"source-session:{fingerprint}",
        "state": state,
        "accepted_lap_numbers": tuple(accepted),
        "rejected_lap_numbers": tuple(rejected),
        "lap_rejection_reasons": lap_rejection_reasons,
        "rejection_reasons": tuple(dict.fromkeys(reasons)),
        "qualified_context": (
            ("exact_car_build",)
            + (("exact_track",) if context.exact_track_required else ())
            + (("exact_setup",) if context.exact_setup_required else ())
            + ("fuel_weather_traffic_bands",)
        ),
        "control_mutation_ids": tuple(event.mutation_id for event in mutations),
        "promoted_to_p21_attempt": False,
        "authority": "qualification_only",
    }
    return _content_addressed(CampaignRunAssessment, "ecr", payload)


def save_run_assessment(
    assessment: CampaignRunAssessment,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            row = connection.execute(
                "SELECT operation_hash, campaign_id FROM evidence_campaign_operations "
                "WHERE operation_id = ?",
                (assessment.operation_id,),
            ).fetchone()
            if (
                row is None
                or row["operation_hash"] != assessment.operation_hash
                or row["campaign_id"] != assessment.campaign_id
            ):
                raise ValueError("run assessment does not match a stored operation")
            existing = connection.execute(
                "SELECT assessment_hash, assessment_json FROM evidence_campaign_run_assessments "
                "WHERE assessment_id = ? OR (operation_id = ? AND run_id = ?)",
                (assessment.assessment_id, assessment.operation_id, assessment.run_id),
            ).fetchone()
            if existing is not None:
                if existing["assessment_hash"] != assessment.assessment_hash or (
                    CampaignRunAssessment.model_validate_json(existing["assessment_json"])
                    != assessment
                ):
                    raise ValueError(
                        "one operation/run pair may have only one immutable assessment"
                    )
                return False
            connection.execute(
                "INSERT INTO evidence_campaign_run_assessments "
                "(assessment_id, assessment_hash, operation_id, campaign_id, run_id, "
                "source_file_fingerprint, recorded_at, state, assessment_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    assessment.assessment_id,
                    assessment.assessment_hash,
                    assessment.operation_id,
                    assessment.campaign_id,
                    assessment.run_id,
                    assessment.source_file_fingerprint,
                    assessment.recorded_at.isoformat(),
                    assessment.state,
                    assessment.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def promote_run_assessment(
    assessment: CampaignRunAssessment,
    *,
    db_path: str | Path | None = None,
) -> CampaignRunAssessment:
    if assessment.state != "usable":
        raise ValueError("only a usable run assessment may enter P21 campaign progress")
    operation = next(
        (
            item
            for item in list_campaign_operations(db_path=db_path)
            if item.operation_id == assessment.operation_id
        ),
        None,
    )
    if operation is None or operation.operation_hash != assessment.operation_hash:
        raise ValueError("assessment operation is unavailable or changed")
    campaign = _campaign(operation.campaign_kind)
    if campaign.campaign_id != assessment.campaign_id:
        raise ValueError("assessment campaign does not match its operation")
    attempt = build_campaign_attempt(
        campaign,
        {
            "outcome": "usable",
            "independence_unit_id": assessment.independence_unit_id,
            "independence_level": campaign.required_independence_level,
            "source_run_ids": (assessment.run_id,),
            "source_session_ids": (assessment.independence_unit_id,),
            "source_file_fingerprints": (assessment.source_file_fingerprint,),
            "eligible_lap_count": len(assessment.accepted_lap_numbers),
            "context_keys": campaign.required_context,
            "available_telemetry": campaign.required_telemetry,
            "setup_snapshot_present": operation.context.setup_fingerprint is not None,
        },
    )
    append_campaign_attempt(attempt, db_path=db_path)
    payload = assessment.model_dump(
        mode="python",
        exclude={"assessment_id", "assessment_hash"},
    )
    payload["promoted_to_p21_attempt"] = True
    return _content_addressed(CampaignRunAssessment, "ecr", payload)


def assess_active_operations_for_run(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> tuple[CampaignRunAssessment, ...]:
    results = []
    for operation in list_campaign_operations(db_path=db_path):
        if operation_state(operation.operation_id, db_path=db_path) != "active":
            continue
        connection = initialize_database(db_path)
        try:
            existing = connection.execute(
                "SELECT assessment_json FROM evidence_campaign_run_assessments "
                "WHERE operation_id = ? AND run_id = ? "
                "ORDER BY recorded_at DESC, assessment_id DESC LIMIT 1",
                (operation.operation_id, run_id),
            ).fetchone()
        finally:
            connection.close()
        if existing is not None:
            results.append(CampaignRunAssessment.model_validate_json(existing[0]))
            continue
        assessment = assess_run_for_operation(operation, run_id, db_path=db_path)
        if assessment.state == "usable":
            assessment = promote_run_assessment(assessment, db_path=db_path)
        save_run_assessment(assessment, db_path=db_path)
        results.append(assessment)
    return tuple(results)


def _latest_assessment(
    operation_id: str,
    *,
    db_path: str | Path | None,
) -> CampaignRunAssessment | None:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT assessment_json FROM evidence_campaign_run_assessments "
            "WHERE operation_id = ? ORDER BY recorded_at DESC, assessment_id DESC LIMIT 1",
            (operation_id,),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else CampaignRunAssessment.model_validate_json(row[0])


def active_campaign_projections(
    *,
    db_path: str | Path | None = None,
) -> tuple[ActiveCampaignProjection, ...]:
    projections = []
    for operation in list_campaign_operations(db_path=db_path):
        state = operation_state(operation.operation_id, db_path=db_path)
        if state not in {"active", "paused"}:
            continue
        connection = initialize_database(db_path)
        try:
            prediction_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM prospective_test_predictions "
                    "WHERE operation_id = ?",
                    (operation.operation_id,),
                ).fetchone()[0]
            )
            unscored_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM prospective_test_predictions AS prediction "
                    "LEFT JOIN prospective_test_outcomes AS outcome "
                    "ON outcome.prediction_id = prediction.prediction_id "
                    "WHERE prediction.operation_id = ? AND outcome.outcome_id IS NULL",
                    (operation.operation_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()
        projections.append(
            ActiveCampaignProjection(
                operation=operation,
                state=state,
                progress=campaign_progress(_campaign(operation.campaign_kind), db_path=db_path),
                latest_assessment=_latest_assessment(operation.operation_id, db_path=db_path),
                prospective_prediction_count=prediction_count,
                unscored_prediction_count=unscored_count,
            )
        )
    return tuple(projections)


_LABELS: dict[CampaignKind, str] = {
    "driver_noise_baseline": "Driver noise baseline",
    "controlled_setup_response": "Controlled setup response",
    "tire_update_semantics": "Tire update semantics",
    "long_run_development": "Long-run development",
    "vehicle_geometry_validation": "Vehicle geometry validation",
    "control_workload": "Steering workload envelope",
    "no_change_null": "No-change null baseline",
}
_LAPS: dict[CampaignKind, int] = {
    "driver_noise_baseline": 12,
    "controlled_setup_response": 9,
    "tire_update_semantics": 3,
    "long_run_development": 22,
    "vehicle_geometry_validation": 0,
    "control_workload": 12,
    "no_change_null": 12,
}
_GATES: dict[CampaignKind, tuple[str, ...]] = {
    "driver_noise_baseline": ("Driver noise", "Probability calibration", "Response model"),
    "controlled_setup_response": ("Control-family response", "Response model", "Calibration"),
    "tire_update_semantics": ("Tire-state semantics",),
    "long_run_development": ("Change-point shadow", "Long-run state migration"),
    "vehicle_geometry_validation": ("Sideslip prerequisites", "Wheel geometry shadow"),
    "control_workload": ("Steering workload envelope", "Yaw-response calibration"),
    "no_change_null": ("False-positive controls", "Change-point shadow", "Calibration"),
}


def acquisition_options(
    run_id: str,
    *,
    db_path: str | Path | None = None,
) -> tuple[AcquisitionOption, ...]:
    overview = RaceLabRepository(db_path).get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    manifest = read_telemetry_manifest(run_id)
    identity = manifest.get("compatibility_identity") or {}
    eligible = eligible_laps(overview.laps)
    eligible_count = len(eligible)
    eligible_numbers = {lap.lap_number for lap in eligible}
    matched_context_ready = False
    if (
        manifest.get("source_file_sha256") or overview.session.file_hash
    ) and identity.get("iracing_build_version"):
        try:
            report = load_lap_engineering_context_report(run_id, db_path=db_path)
            contexts = [
                item for item in report.contexts if item.lap_number in eligible_numbers
            ]
            matched_context_ready = all(
                band is not None
                for band in (
                    _band(_finite_values([item.fuel_level for item in contexts]), 0.25),
                    _band(
                        _finite_values([item.track_temperature for item in contexts]),
                        2.0,
                    ),
                    _band(
                        _finite_values([item.air_temperature for item in contexts]),
                        2.0,
                    ),
                )
            )
        except (OSError, RuntimeError, ValueError):
            matched_context_ready = False
    candidates: list[tuple[float, CampaignKind, AcquisitionOption]] = []
    for campaign in initial_campaigns():
        progress = campaign_progress(campaign, db_path=db_path)
        required = campaign.acceptance_criteria.minimum_independent_units
        deficit = min(1.0, progress.remaining_independent_units / required)
        blockers = []
        if not manifest.get("source_file_sha256") and not overview.session.file_hash:
            blockers.append("Immutable telemetry fingerprint is missing.")
        if not identity.get("iracing_build_version"):
            blockers.append("Exact iRacing build identity is missing.")
        if campaign.required_setup_snapshots and overview.setup_snapshot is None:
            blockers.append("A complete setup snapshot is missing.")
        if campaign.campaign_kind not in {
            "tire_update_semantics",
            "vehicle_geometry_validation",
        } and not matched_context_ready:
            blockers.append(
                "Eligible-lap fuel and weather context cannot be frozen from this run."
            )
        if campaign.campaign_kind == "vehicle_geometry_validation":
            blockers.append(
                "Vehicle geometry requires an external source-validation operation, not driver laps."
            )
        required_laps = {
            "driver_noise_baseline": 10,
            "controlled_setup_response": 9,
            "tire_update_semantics": 0,
            "long_run_development": 20,
            "vehicle_geometry_validation": 0,
            "control_workload": 10,
            "no_change_null": 10,
        }[campaign.campaign_kind]
        lap_ratio = 1.0 if required_laps == 0 else min(1.0, eligible_count / required_laps)
        rule_fit = 0.0 if blockers else round(0.25 + 0.70 * lap_ratio, 3)
        cost = _LAPS[campaign.campaign_kind]
        gate_count = len(_GATES[campaign.campaign_kind])
        score = (
            0.0
            if blockers
            else deficit * rule_fit * gate_count / max(1, cost) * 100.0
        )
        need = [
            f"{progress.remaining_independent_units} more independent unit(s)",
            f"{max(0, required_laps - eligible_count)} more clean lap(s) in the next unit",
        ]
        if progress.missing_contexts:
            need.append("Missing contexts: " + ", ".join(progress.missing_contexts))
        option = AcquisitionOption(
            campaign_kind=campaign.campaign_kind,
            label=_LABELS[campaign.campaign_kind],
            state="infeasible" if blockers else "candidate",
            helps=_GATES[campaign.campaign_kind],
            need_next=tuple(need),
            blockers=tuple(blockers),
            score=AcquisitionScoreComponents(
                deficit_fraction=deficit,
                rule_fit_estimate=rule_fit,
                gates_helped=gate_count,
                estimated_driver_laps=cost,
                deterministic_value=round(score, 3),
            ),
        )
        candidates.append((score, campaign.campaign_kind, option))
    feasible = [item for item in candidates if not item[2].blockers]
    highest_kind = max(feasible, default=None, key=lambda item: (item[0], item[1]))
    return tuple(
        option.model_copy(update={"state": "highest"})
        if highest_kind is not None and kind == highest_kind[1]
        else option
        for _score, kind, option in sorted(candidates, key=lambda item: (-item[0], item[1]))
    )


def learning_ledger(
    *,
    db_path: str | Path | None = None,
) -> tuple[LearningLedgerEntry, ...]:
    entries: list[LearningLedgerEntry] = [
        LearningLedgerEntry(
            ledger_key="guardrail:qualified-vs-archived",
            section="proven_guardrail",
            label="Archive inventory is not qualified evidence",
            summary="Duplicate source identity and independence checks fail closed.",
            evidence_basis="verified_architecture",
        ),
        LearningLedgerEntry(
            ledger_key="guardrail:prospective-lock",
            section="proven_guardrail",
            label="Predictions freeze before outcomes",
            summary="One immutable outcome may attach only after its prediction timestamp.",
            evidence_basis="verified_architecture",
        ),
        LearningLedgerEntry(
            ledger_key="guardrail:authority",
            section="proven_guardrail",
            label="P19/P20 authority remains isolated",
            summary="Campaign and director outputs are collection guidance only.",
            evidence_basis="verified_architecture",
        ),
    ]
    for campaign in initial_campaigns():
        progress = campaign_progress(campaign, db_path=db_path)
        entries.append(
            LearningLedgerEntry(
                ledger_key=f"campaign:{campaign.campaign_kind}",
                section="in_validation",
                label=_LABELS[campaign.campaign_kind],
                summary=(
                    "Campaign complete; activation still requires frozen evaluation and prospective gates."
                    if progress.complete
                    else progress.blockers[0]
                ),
                current=progress.independent_units,
                required=campaign.acceptance_criteria.minimum_independent_units,
                evidence_basis="qualified_real_evidence",
            )
        )
    connection = initialize_database(db_path)
    try:
        decision_rows = connection.execute(
            "SELECT decision_json FROM activation_decisions "
            "ORDER BY evaluated_at DESC, decision_id DESC"
        ).fetchall()
    finally:
        connection.close()
    seen: set[str] = set()
    for row in decision_rows:
        import json

        decision = json.loads(row[0])
        capability = str(decision.get("capability_key") or "unknown")
        if capability in seen:
            continue
        seen.add(capability)
        state = str(decision.get("state") or "locked_insufficient_data")
        entries.append(
            LearningLedgerEntry(
                ledger_key=f"activation:{capability}",
                section=("failed_validation" if state == "locked_failed_validation" else "locked"),
                label=capability.replace("_", " ").title(),
                summary=(decision.get("blockers") or ["Activation gate remains closed."])[0],
                evidence_basis="qualified_real_evidence",
            )
        )
    for capability in (
        "Cause probabilities",
        "Formal information gain",
        "Bayesian optimization",
        "Multi-control optimization",
    ):
        key = capability.casefold().replace(" ", "_")
        if key not in seen:
            entries.append(
                LearningLedgerEntry(
                    ledger_key=f"locked:{key}",
                    section="locked",
                    label=capability,
                    summary="No frozen gate has earned production authority.",
                    evidence_basis="frozen_gate_policy",
                )
            )
    return tuple(entries)


__all__ = [
    "AcquisitionOption",
    "ActiveCampaignProjection",
    "CampaignOperation",
    "CampaignOperationContext",
    "CampaignOperationEvent",
    "CampaignRunAssessment",
    "LearningLedgerEntry",
    "NumericBand",
    "acquisition_options",
    "active_campaign_projections",
    "append_operation_event",
    "assess_active_operations_for_run",
    "assess_run_for_operation",
    "build_campaign_operation",
    "build_operation_event",
    "learning_ledger",
    "list_campaign_operations",
    "operation_state",
    "promote_run_assessment",
    "save_campaign_operation",
    "save_run_assessment",
    "start_campaign_operation",
    "transition_campaign_operation",
]
