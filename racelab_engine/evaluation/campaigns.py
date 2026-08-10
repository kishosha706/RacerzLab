"""First-class P21 evidence collection campaigns and progress accounting."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.evaluation.dataset_registry import (
    EvidenceLabModel,
    IndependenceLevel,
    canonical_hash,
)
from racelab_engine.storage.db import initialize_database


CampaignKind = Literal[
    "driver_noise_baseline",
    "controlled_setup_response",
    "tire_update_semantics",
    "long_run_development",
    "vehicle_geometry_validation",
    "control_workload",
    "no_change_null",
]
CampaignAttemptOutcome = Literal["usable", "invalid"]


class CampaignAcceptanceCriteria(EvidenceLabModel):
    minimum_independent_units: int = Field(ge=1)
    minimum_eligible_laps: int = Field(ge=0)
    minimum_units_per_context: int = Field(ge=0)
    required_contexts: tuple[str, ...] = ()
    maximum_false_positive_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    )
    restoration_required: bool = False


class EvidenceCampaign(EvidenceLabModel):
    campaign_id: str = Field(pattern=r"^ecp-[0-9a-f]{20}$")
    campaign_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_version: str = Field(min_length=1)
    campaign_kind: CampaignKind
    created_at: datetime
    scientific_question: str = Field(min_length=1)
    required_context: tuple[str, ...] = Field(min_length=1)
    required_runs: int = Field(ge=1)
    required_independence_level: IndependenceLevel
    required_telemetry: tuple[str, ...] = Field(min_length=1)
    required_setup_snapshots: bool
    controlled_variables: tuple[str, ...] = Field(min_length=1)
    allowed_variation: tuple[str, ...]
    acceptance_criteria: CampaignAcceptanceCriteria
    stop_criteria: tuple[str, ...] = Field(min_length=1)
    allowed_outputs: tuple[str, ...] = Field(min_length=1)
    forbidden_outputs: tuple[str, ...] = Field(min_length=1)
    authority_ceiling: Literal["data_collection_only"] = "data_collection_only"

    @model_validator(mode="after")
    def campaign_is_content_addressed(self) -> EvidenceCampaign:
        for values, label in (
            (self.required_context, "required context"),
            (self.required_telemetry, "required telemetry"),
            (self.controlled_variables, "controlled variable"),
            (self.allowed_variation, "allowed variation"),
            (self.stop_criteria, "stop criterion"),
            (self.allowed_outputs, "allowed output"),
            (self.forbidden_outputs, "forbidden output"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} values must be unique")
        payload = self.model_dump(
            mode="json",
            exclude={"campaign_id", "campaign_hash"},
        )
        expected = canonical_hash(payload)
        if (
            self.campaign_hash != expected
            or self.campaign_id != f"ecp-{expected[:20]}"
        ):
            raise ValueError("campaign identity does not match its immutable contract")
        return self


class CampaignAttempt(EvidenceLabModel):
    attempt_id: str = Field(pattern=r"^eca-[0-9a-f]{20}$")
    attempt_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_id: str
    campaign_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: datetime
    outcome: CampaignAttemptOutcome
    independence_unit_id: str = Field(min_length=1)
    independence_level: IndependenceLevel
    source_run_ids: tuple[str, ...] = ()
    source_session_ids: tuple[str, ...] = ()
    source_workflow_ids: tuple[str, ...] = ()
    source_file_fingerprints: tuple[str, ...] = ()
    eligible_lap_count: int = Field(ge=0)
    context_keys: tuple[str, ...] = ()
    available_telemetry: tuple[str, ...] = ()
    setup_snapshot_present: bool
    restoration_passed: bool | None = None
    invalid_reasons: tuple[str, ...] = ()
    dataset_id: str | None = None

    @model_validator(mode="after")
    def attempt_is_append_only_and_explained(self) -> CampaignAttempt:
        if self.outcome == "usable" and self.invalid_reasons:
            raise ValueError("usable campaign attempts cannot retain invalid reasons")
        if self.outcome == "invalid" and not self.invalid_reasons:
            raise ValueError("invalid campaign attempts must explain why")
        payload = self.model_dump(
            mode="json",
            exclude={"attempt_id", "attempt_hash"},
        )
        expected = canonical_hash(payload)
        if self.attempt_hash != expected or self.attempt_id != f"eca-{expected[:20]}":
            raise ValueError("campaign-attempt identity does not match its content")
        return self


class CampaignProgress(EvidenceLabModel):
    campaign_id: str
    usable_attempts: int = Field(ge=0)
    invalid_attempts: int = Field(ge=0)
    independent_units: int = Field(ge=0)
    eligible_laps: int = Field(ge=0)
    remaining_independent_units: int = Field(ge=0)
    remaining_eligible_laps: int = Field(ge=0)
    missing_contexts: tuple[str, ...]
    missing_telemetry: tuple[str, ...]
    complete: bool
    blockers: tuple[str, ...]


def build_campaign(payload: dict[str, Any]) -> EvidenceCampaign:
    if {"campaign_id", "campaign_hash"} & payload.keys():
        raise ValueError("campaign identity is derived")
    normalized = {
        "created_at": datetime.now(timezone.utc),
        "authority_ceiling": "data_collection_only",
        **payload,
    }
    normalized["acceptance_criteria"] = CampaignAcceptanceCriteria.model_validate(
        normalized["acceptance_criteria"]
    )
    normalized["required_independence_level"] = IndependenceLevel(
        normalized["required_independence_level"]
    )
    identity_payload = EvidenceCampaign.model_construct(
        campaign_id="ecp-" + "0" * 20,
        campaign_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"campaign_id", "campaign_hash"})
    campaign_hash = canonical_hash(identity_payload)
    return EvidenceCampaign(
        campaign_id=f"ecp-{campaign_hash[:20]}",
        campaign_hash=campaign_hash,
        **normalized,
    )


def build_campaign_attempt(
    campaign: EvidenceCampaign,
    payload: dict[str, Any],
) -> CampaignAttempt:
    if {"attempt_id", "attempt_hash", "campaign_id", "campaign_hash"} & payload.keys():
        raise ValueError("attempt and campaign identity are derived")
    normalized = {
        "campaign_id": campaign.campaign_id,
        "campaign_hash": campaign.campaign_hash,
        "recorded_at": datetime.now(timezone.utc),
        "source_run_ids": (),
        "source_session_ids": (),
        "source_workflow_ids": (),
        "source_file_fingerprints": (),
        "context_keys": (),
        "available_telemetry": (),
        "restoration_passed": None,
        "invalid_reasons": (),
        "dataset_id": None,
        **payload,
    }
    normalized["independence_level"] = IndependenceLevel(
        normalized["independence_level"]
    )
    contract_failures: list[str] = []
    if normalized["independence_level"] != campaign.required_independence_level:
        contract_failures.append(
            "Attempt independence level does not match the campaign contract."
        )
    missing_context = set(campaign.required_context) - set(normalized["context_keys"])
    if missing_context:
        contract_failures.append("Attempt lacks required scientific context.")
    missing_telemetry = set(campaign.required_telemetry) - set(
        normalized["available_telemetry"]
    )
    if missing_telemetry:
        contract_failures.append("Attempt lacks required telemetry.")
    if campaign.required_setup_snapshots and not normalized["setup_snapshot_present"]:
        contract_failures.append("Attempt lacks the required setup snapshot.")
    if (
        campaign.acceptance_criteria.restoration_required
        and normalized["restoration_passed"] is not True
    ):
        contract_failures.append("Attempt lacks proven A2 restoration.")
    if contract_failures:
        normalized["outcome"] = "invalid"
        normalized["invalid_reasons"] = tuple(
            dict.fromkeys((*normalized["invalid_reasons"], *contract_failures))
        )
    identity_payload = CampaignAttempt.model_construct(
        attempt_id="eca-" + "0" * 20,
        attempt_hash="0" * 64,
        **normalized,
    ).model_dump(mode="json", exclude={"attempt_id", "attempt_hash"})
    attempt_hash = canonical_hash(identity_payload)
    return CampaignAttempt(
        attempt_id=f"eca-{attempt_hash[:20]}",
        attempt_hash=attempt_hash,
        **normalized,
    )


def save_campaign(
    campaign: EvidenceCampaign,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            row = connection.execute(
                "SELECT campaign_hash, campaign_json FROM evidence_campaigns "
                "WHERE campaign_id = ?",
                (campaign.campaign_id,),
            ).fetchone()
            if row is not None:
                if (
                    row["campaign_hash"] != campaign.campaign_hash
                    or EvidenceCampaign.model_validate_json(row["campaign_json"])
                    != campaign
                ):
                    raise ValueError("immutable campaign identity collision")
                return False
            connection.execute(
                "INSERT INTO evidence_campaigns "
                "(campaign_id, campaign_hash, campaign_kind, created_at, campaign_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    campaign.campaign_id,
                    campaign.campaign_hash,
                    campaign.campaign_kind,
                    campaign.created_at.isoformat(),
                    campaign.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def append_campaign_attempt(
    attempt: CampaignAttempt,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        with connection:
            campaign_row = connection.execute(
                "SELECT campaign_hash FROM evidence_campaigns WHERE campaign_id = ?",
                (attempt.campaign_id,),
            ).fetchone()
            if campaign_row is None or campaign_row["campaign_hash"] != attempt.campaign_hash:
                raise ValueError("campaign attempt does not match a registered campaign")
            row = connection.execute(
                "SELECT attempt_hash, attempt_json FROM evidence_campaign_attempts "
                "WHERE attempt_id = ?",
                (attempt.attempt_id,),
            ).fetchone()
            if row is not None:
                if (
                    row["attempt_hash"] != attempt.attempt_hash
                    or CampaignAttempt.model_validate_json(row["attempt_json"]) != attempt
                ):
                    raise ValueError("immutable campaign-attempt identity collision")
                return False
            connection.execute(
                "INSERT INTO evidence_campaign_attempts "
                "(attempt_id, attempt_hash, campaign_id, recorded_at, outcome, "
                "independence_unit_id, attempt_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt.attempt_id,
                    attempt.attempt_hash,
                    attempt.campaign_id,
                    attempt.recorded_at.isoformat(),
                    attempt.outcome,
                    attempt.independence_unit_id,
                    attempt.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def campaign_progress(
    campaign: EvidenceCampaign,
    *,
    db_path: str | Path | None = None,
) -> CampaignProgress:
    connection = initialize_database(db_path)
    try:
        rows = connection.execute(
            "SELECT attempt_json FROM evidence_campaign_attempts "
            "WHERE campaign_id = ? ORDER BY recorded_at, attempt_id",
            (campaign.campaign_id,),
        ).fetchall()
    finally:
        connection.close()
    attempts = tuple(CampaignAttempt.model_validate_json(row[0]) for row in rows)
    usable = tuple(attempt for attempt in attempts if attempt.outcome == "usable")
    unique_usable: dict[str, CampaignAttempt] = {}
    for attempt in usable:
        unique_usable.setdefault(attempt.independence_unit_id, attempt)
    accepted = tuple(unique_usable.values())
    contexts = {context for attempt in accepted for context in attempt.context_keys}
    telemetry = {
        channel for attempt in accepted for channel in attempt.available_telemetry
    }
    criteria = campaign.acceptance_criteria
    independent_units = len(accepted)
    eligible_laps = sum(attempt.eligible_lap_count for attempt in accepted)
    missing_contexts = tuple(sorted(set(criteria.required_contexts) - contexts))
    missing_telemetry = tuple(sorted(set(campaign.required_telemetry) - telemetry))
    blockers: list[str] = []
    if independent_units < criteria.minimum_independent_units:
        blockers.append("Insufficient independent units.")
    if eligible_laps < criteria.minimum_eligible_laps:
        blockers.append("Insufficient eligible laps.")
    if missing_contexts:
        blockers.append("Required context coverage is incomplete.")
    if missing_telemetry:
        blockers.append("Required telemetry coverage is incomplete.")
    if campaign.required_setup_snapshots and any(
        not attempt.setup_snapshot_present for attempt in accepted
    ):
        blockers.append("A usable attempt lacks its required setup snapshot.")
    if criteria.restoration_required and any(
        attempt.restoration_passed is not True for attempt in accepted
    ):
        blockers.append("A usable controlled attempt lacks proven restoration.")
    return CampaignProgress(
        campaign_id=campaign.campaign_id,
        usable_attempts=len(usable),
        invalid_attempts=sum(attempt.outcome == "invalid" for attempt in attempts),
        independent_units=independent_units,
        eligible_laps=eligible_laps,
        remaining_independent_units=max(
            0,
            criteria.minimum_independent_units - independent_units,
        ),
        remaining_eligible_laps=max(0, criteria.minimum_eligible_laps - eligible_laps),
        missing_contexts=missing_contexts,
        missing_telemetry=missing_telemetry,
        complete=not blockers,
        blockers=tuple(blockers),
    )


def initial_campaigns(
    *,
    created_at: datetime | None = None,
) -> tuple[EvidenceCampaign, ...]:
    timestamp = created_at or datetime.now(timezone.utc)
    shared_forbidden = (
        "setup_authority",
        "cause_probability",
        "automatic_control_change",
    )
    definitions = (
        {
            "campaign_kind": "driver_noise_baseline",
            "scientific_question": "What is natural same-setup driver variability?",
            "required_context": ("matched_setup", "matched_tire_fuel_weather"),
            "required_runs": 3,
            "required_independence_level": "session",
            "required_telemetry": ("lap_time", "track_position", "driver_inputs"),
            "required_setup_snapshots": True,
            "controlled_variables": ("setup", "driver", "car", "track"),
            "allowed_variation": ("session_time",),
            "acceptance_criteria": {
                "minimum_independent_units": 3,
                "minimum_eligible_laps": 30,
                "minimum_units_per_context": 3,
                "maximum_false_positive_rate": 0.05,
            },
            "stop_criteria": ("three compatible sessions and thirty clean laps",),
            "allowed_outputs": ("descriptive_noise_envelope",),
        },
        {
            "campaign_kind": "controlled_setup_response",
            "scientific_question": "How does one legal setup control respond under A/B/A2?",
            "required_context": ("exact_context", "one_control", "a2_restoration"),
            "required_runs": 90,
            "required_independence_level": "controlled_workflow",
            "required_telemetry": ("lap_time", "target_metric", "countereffects"),
            "required_setup_snapshots": True,
            "controlled_variables": ("all_non_test_setup_controls",),
            "allowed_variation": ("one_adjacent_legal_control",),
            "acceptance_criteria": {
                "minimum_independent_units": 30,
                "minimum_eligible_laps": 270,
                "minimum_units_per_context": 6,
                "restoration_required": True,
            },
            "stop_criteria": ("P7 minimum history reached",),
            "allowed_outputs": ("descriptive_control_response",),
        },
        {
            "campaign_kind": "tire_update_semantics",
            "scientific_question": "When do Next Gen tire channels actually update?",
            "required_context": ("pit_in_out", "new_tire_set"),
            "required_runs": 3,
            "required_independence_level": "session",
            "required_telemetry": ("tire_channels", "pit_state", "tire_set"),
            "required_setup_snapshots": False,
            "controlled_variables": ("car_family",),
            "allowed_variation": ("track_family", "run_length"),
            "acceptance_criteria": {
                "minimum_independent_units": 3,
                "minimum_eligible_laps": 0,
                "minimum_units_per_context": 1,
                "required_contexts": ("short", "intermediate", "superspeedway"),
            },
            "stop_criteria": ("all required track families observed",),
            "allowed_outputs": ("channel_update_semantics",),
        },
        {
            "campaign_kind": "long_run_development",
            "scientific_question": "How does whole-car state migrate in long clean runs?",
            "required_context": ("continuous_clean_stint", "matched_context"),
            "required_runs": 30,
            "required_independence_level": "stint",
            "required_telemetry": ("lap_time", "fuel", "traffic", "weather"),
            "required_setup_snapshots": True,
            "controlled_variables": ("setup",),
            "allowed_variation": ("lap_number", "tire_age", "fuel_level"),
            "acceptance_criteria": {
                "minimum_independent_units": 30,
                "minimum_eligible_laps": 600,
                "minimum_units_per_context": 3,
            },
            "stop_criteria": ("thirty qualified twenty-lap stints",),
            "allowed_outputs": ("descriptive_state_migration",),
        },
        {
            "campaign_kind": "vehicle_geometry_validation",
            "scientific_question": "Which vehicle-profile fields are source validated?",
            "required_context": ("exact_car_build",),
            "required_runs": 1,
            "required_independence_level": "build",
            "required_telemetry": ("session_identity",),
            "required_setup_snapshots": False,
            "controlled_variables": ("car_path", "build"),
            "allowed_variation": ("profile_field",),
            "acceptance_criteria": {
                "minimum_independent_units": 1,
                "minimum_eligible_laps": 0,
                "minimum_units_per_context": 1,
            },
            "stop_criteria": ("every dependent field has an explicit state",),
            "allowed_outputs": ("field_validation_state",),
        },
        {
            "campaign_kind": "control_workload",
            "scientific_question": "What is normal steering workload for one FFB fingerprint?",
            "required_context": ("exact_ffb_fingerprint", "clean_laps"),
            "required_runs": 3,
            "required_independence_level": "session",
            "required_telemetry": ("steering", "steering_torque", "ffb_config"),
            "required_setup_snapshots": True,
            "controlled_variables": ("ffb_fingerprint", "driver"),
            "allowed_variation": ("session",),
            "acceptance_criteria": {
                "minimum_independent_units": 3,
                "minimum_eligible_laps": 30,
                "minimum_units_per_context": 3,
            },
            "stop_criteria": ("three matching FFB sessions",),
            "allowed_outputs": ("descriptive_workload_range",),
        },
        {
            "campaign_kind": "no_change_null",
            "scientific_question": "How often do detectors fire when nothing changed?",
            "required_context": ("same_setup", "no_mechanism_transition"),
            "required_runs": 10,
            "required_independence_level": "stint",
            "required_telemetry": ("whole_car_state", "context", "integrity"),
            "required_setup_snapshots": True,
            "controlled_variables": ("setup", "sim_integrity"),
            "allowed_variation": ("natural_driver_noise",),
            "acceptance_criteria": {
                "minimum_independent_units": 10,
                "minimum_eligible_laps": 200,
                "minimum_units_per_context": 1,
                "maximum_false_positive_rate": 0.05,
            },
            "stop_criteria": ("ten qualified null stints",),
            "allowed_outputs": ("false_positive_rate",),
        },
    )
    return tuple(
        build_campaign(
            {
                "campaign_version": "p21-campaign-v1",
                "created_at": timestamp,
                "forbidden_outputs": shared_forbidden,
                **definition,
            }
        )
        for definition in definitions
    )


__all__ = [
    "CampaignAcceptanceCriteria",
    "CampaignAttempt",
    "CampaignAttemptOutcome",
    "CampaignKind",
    "CampaignProgress",
    "EvidenceCampaign",
    "append_campaign_attempt",
    "build_campaign",
    "build_campaign_attempt",
    "campaign_progress",
    "initial_campaigns",
    "save_campaign",
]
