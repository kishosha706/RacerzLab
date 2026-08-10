"""P24 evidence acquisition operations for the frozen P23 workload protocol.

This module turns P22 campaign assessments into immutable, protocol-bound
qualification certificates.  Certificates may admit evidence, but they never
change P19/P20 authority or the P23 activation state.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import Field, model_validator

from racelab_engine.analysis.lap_eligibility import lap_ineligibility_reasons
from racelab_engine.evaluation.campaigns import (
    append_campaign_attempt,
    build_campaign_attempt,
    initial_campaigns,
    save_campaign,
)
from racelab_engine.evaluation.dataset_registry import (
    DatasetKind,
    EvidenceDataset,
    EvidenceLabModel,
    build_evidence_dataset,
    canonical_hash,
    register_evidence_dataset,
)
from racelab_engine.evaluation.first_activation import (
    first_activation_protocol,
    save_first_activation_protocol,
)
from racelab_engine.evaluation.learning_operations import (
    CampaignOperation,
    CampaignRunAssessment,
    list_campaign_operations,
    operation_state,
    start_campaign_operation,
)
from racelab_engine.models.engineering_context import (
    ControlMutationEvent,
    SteeringContextFingerprint,
)
from racelab_engine.services.engineering_context_service import (
    P23_STEERING_FINGERPRINT_FIELDS,
    build_steering_context_fingerprint,
    compare_steering_contexts,
    detect_control_mutations,
)
from racelab_engine.services.import_service import (
    read_telemetry_manifest,
    read_telemetry_rows,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository

P23CollectionKind = Literal[
    "historical_exact_ffb",
    "same_setup_null",
    "negative_control",
    "profile_validation",
    "prospective",
]
CertificateState = Literal["qualified", "rejected", "partial", "inventory_only"]
TruthState = Literal["ready", "limited", "scientific_debt", "missing"]
ExpectedControlOutcome = Literal["comparison_rejected", "comparison_allowed"]
P23CollectionPriority = Literal[
    "profile_validation",
    "historical_exact_ffb",
    "same_setup_null",
    "negative_control",
    "subgroup_coverage",
    "historical_gate_review",
]

_P23_PROTOCOL = first_activation_protocol()
_REQUIRED_SUBGROUPS = frozenset(_P23_PROTOCOL.required_subgroups)

_STEERING_CHANNELS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], bool], ...] = (
    ("SteeringWheelTorque_ST", ("SteeringWheelTorque_ST", "steering_wheel_torque_subtick_nm"), ("N*m", "Nm"), True),
    ("SteeringWheelTorque", ("SteeringWheelTorque", "steering_wheel_torque_nm"), ("N*m", "Nm"), True),
    ("SteeringWheelAngle", ("SteeringWheelAngle", "steering_deg"), ("rad", "deg"), True),
    ("SteeringWheelAngleMax", ("SteeringWheelAngleMax", "steering_wheel_angle_max"), ("rad", "deg"), True),
    ("SteeringWheelMaxForceNm", ("SteeringWheelMaxForceNm", "steering_ffb_max_force_nm"), ("N*m", "Nm"), True),
    ("SteeringWheelUseLinear", ("SteeringWheelUseLinear", "steering_ffb_use_linear"), ("bool",), True),
    ("SteeringWheelPctIntensity", ("SteeringWheelPctIntensity", "steering_ffb_intensity_01"), ("%", "fraction"), True),
    ("SteeringWheelPctSmoothing", ("SteeringWheelPctSmoothing", "steering_ffb_smoothing_01"), ("%", "fraction"), True),
    ("SteeringWheelPctDamper", ("SteeringWheelPctDamper", "steering_ffb_damper_01"), ("%", "fraction"), True),
    ("SteeringWheelLimiter", ("SteeringWheelLimiter", "steering_ffb_limiter_01"), ("%", "fraction"), True),
)

_STEERING_READ_COLUMNS = tuple(
    dict.fromkeys(
        (
            "session_time",
            "lap",
            "lap_number",
            "lap_dist_pct_100",
            "steering_ratio",
            *(
                name
                for _key, aliases, _units, _required in _STEERING_CHANNELS
                for name in aliases
            ),
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
    )
)


class SignalTruth(EvidenceLabModel):
    channel_key: str
    source_channel: str | None = None
    raw_unit: str | None = None
    data_type: str | None = None
    expected_units: tuple[str, ...]
    unit_verified: bool
    sample_structure: Literal["scalar", "count_as_time_array", "unavailable"]
    sign_semantics: Literal[
        "observed_signed", "unsigned_configuration", "not_applicable", "unproven"
    ]
    base_sample_rate_hz: float | None = Field(default=None, gt=0.0)
    effective_sample_rate_hz: float | None = Field(default=None, gt=0.0)
    samples_per_record: int = Field(default=0, ge=0)
    count_as_time: bool = False
    coverage_fraction: float = Field(ge=0.0, le=1.0)
    variation: str
    update_behavior: Literal[
        "continuous_per_record",
        "stable_configuration",
        "changing_configuration",
        "fixed_limit",
        "unavailable",
    ]
    canonical_mapping: str | None = None
    comparison_role: Literal["measurement", "configuration", "limit"]
    campaign_requirement: Literal["required_for_p23_admission"] = (
        "required_for_p23_admission"
    )
    health_status: str
    clipping_status: str
    saturation_status: str
    state: TruthState
    scientific_debt: tuple[str, ...] = ()
    required_for_admission: bool = True

    @model_validator(mode="after")
    def truth_is_explicit(self) -> SignalTruth:
        if self.state == "ready" and self.scientific_debt:
            raise ValueError("ready steering signals cannot retain scientific debt")
        if self.state != "ready" and not self.scientific_debt:
            raise ValueError("unready steering signals must explain their scientific debt")
        return self


class SubTickClockTruth(EvidenceLabModel):
    state: Literal["pass", "fail", "unknown"]
    ordering_source: Literal["session_tick_count_as_time", "unavailable"]
    samples_per_record: int = Field(ge=0)
    base_sample_rate_hz: float | None = Field(default=None, gt=0.0)
    effective_sample_rate_hz: float | None = Field(default=None, gt=0.0)
    session_tick_available: bool
    invalid_tick_sample_count: int = Field(ge=0)
    duplicate_tick_transition_count: int = Field(ge=0)
    reversed_tick_transition_count: int = Field(ge=0)
    estimated_dropped_tick_count: int = Field(ge=0)
    invalid_timestamp_sample_count: int = Field(ge=0)
    non_monotonic_timestamp_transition_count: int = Field(ge=0)
    timestamp_gap_count: int = Field(ge=0)
    scientific_debt: tuple[str, ...] = ()

    @model_validator(mode="after")
    def clock_state_is_explained(self) -> SubTickClockTruth:
        if self.state == "pass" and self.scientific_debt:
            raise ValueError("passing sub-tick clocks cannot retain scientific debt")
        if self.state != "pass" and not self.scientific_debt:
            raise ValueError("unproven sub-tick clocks require exact scientific debt")
        return self


class SteeringSignalTruthAudit(EvidenceLabModel):
    audit_id: str = Field(pattern=r"^p24s-[0-9a-f]{20}$")
    audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    audit_version: Literal["p24-steering-signal-truth-v1"]
    created_at: datetime
    run_id: str
    source_file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_id: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    channels: tuple[SignalTruth, ...] = Field(min_length=1)
    ffb_fingerprint: SteeringContextFingerprint
    scalar_subtick_relation: Literal[
        "mean_consistent", "first_consistent", "last_consistent", "inconsistent", "unavailable"
    ]
    scalar_subtick_normalized_error: float | None = Field(default=None, ge=0.0)
    sub_tick_coverage_fraction: float = Field(ge=0.0, le=1.0)
    sub_tick_clock: SubTickClockTruth
    sample_clock_integrity: Literal["pass", "fail", "unknown"]
    effective_sub_tick_rate_hz: float | None = Field(default=None, gt=0.0)
    steering_conversion_model: str | None = None
    state: TruthState
    blocker_reasons: tuple[str, ...]
    authority: Literal["scientific_qualification_only"] = "scientific_qualification_only"

    @model_validator(mode="after")
    def audit_is_fail_closed_and_content_addressed(self) -> SteeringSignalTruthAudit:
        if self.state == "ready" and self.blocker_reasons:
            raise ValueError("ready steering truth audits cannot retain blockers")
        if self.state != "ready" and not self.blocker_reasons:
            raise ValueError("unready steering truth audits must explain their state")
        if self.state == "ready" and (
            self.ffb_fingerprint.state != "ready"
            or self.scalar_subtick_relation in {"inconsistent", "unavailable"}
            or self.sub_tick_clock.state != "pass"
            or self.sample_clock_integrity != "pass"
            or self.sub_tick_coverage_fraction < 0.95
            or self.steering_conversion_model is None
        ):
            raise ValueError("ready steering truth requires every frozen signal gate")
        payload = self.model_dump(mode="json", exclude={"audit_id", "audit_hash"})
        digest = canonical_hash(payload)
        if self.audit_hash != digest or self.audit_id != f"p24s-{digest[:20]}":
            raise ValueError("steering truth audit identity does not match its evidence")
        return self


class FlightRecorderEntry(EvidenceLabModel):
    lap_number: int = Field(ge=0)
    state: Literal["qualified", "excluded", "context_boundary", "inventory"]
    reasons: tuple[str, ...]
    setup_fingerprint: str | None = None
    ffb_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_control_mutation_ids: tuple[str, ...] = ()
    requested_control_mutation_ids: tuple[str, ...] = ()
    nearby_context: Literal["acceptable", "rejected", "unknown"]
    sample_continuity: Literal["pass", "fail", "unknown"]
    sub_tick_coverage_fraction: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def lap_decision_is_explained(self) -> FlightRecorderEntry:
        if self.state == "qualified" and self.reasons:
            raise ValueError("qualified flight-recorder laps cannot retain exclusions")
        if self.state != "qualified" and not self.reasons:
            raise ValueError("non-qualified flight-recorder laps require reasons")
        if set(self.applied_control_mutation_ids) & set(
            self.requested_control_mutation_ids
        ):
            raise ValueError("requested and applied control states must remain distinct")
        return self


class ControlStateBoundary(EvidenceLabModel):
    mutation_id: str
    control_key: str
    mutation_kind: Literal["applied_state", "requested_state", "confirmed_service"]
    lap_number: int = Field(ge=0)
    lap_pct: float = Field(ge=0.0, le=100.0)
    previous_value: float | int | bool | str | None = None
    new_value: float | int | bool | str
    applied_state_confirmed: bool


class TelemetryOwnershipTruth(EvidenceLabModel):
    state: Literal["verified", "blocked"]
    run_id: str
    source_file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_file_size_bytes: int | None = Field(default=None, gt=0)
    telemetry_cache_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    schema_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def ownership_is_fail_closed(self) -> TelemetryOwnershipTruth:
        complete = all(
            (
                self.source_file_sha256,
                self.source_file_size_bytes,
                self.telemetry_cache_sha256,
                self.schema_fingerprint,
            )
        )
        if self.state == "verified" and (not complete or self.blocker_reasons):
            raise ValueError("verified telemetry ownership requires complete immutable identity")
        if self.state == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked telemetry ownership requires exact reasons")
        return self


class DatasetAdmissionRule(EvidenceLabModel):
    admission_key: str
    dataset_kind: DatasetKind
    partition: Literal["evaluation", "prospective"]
    ground_truth_type: Literal[
        "none",
        "same_setup_null",
        "source_declared_reference",
        "prospective_observed_outcome",
    ]
    allowed_use: str
    certificate_only: Literal[True] = True


class NegativeControlExpectation(EvidenceLabModel):
    expectation_id: str = Field(pattern=r"^p24n-[0-9a-f]{20}$")
    expectation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expectation_version: Literal["p24-negative-control-v1"]
    created_at: datetime
    recipe_id: str
    protocol_control_id: str
    operation_id: str
    operation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_run_id: str
    protocol_id: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_outcome: ExpectedControlOutcome
    expected_blocker_keys: tuple[str, ...] = Field(min_length=1)
    observed_run_id: None = None
    observed_result: None = None
    authority: Literal["pre_outcome_expectation_only"] = "pre_outcome_expectation_only"

    @model_validator(mode="after")
    def expectation_is_frozen_before_observation(self) -> NegativeControlExpectation:
        if self.protocol_control_id not in _P23_PROTOCOL.negative_control_ids:
            raise ValueError("negative-control recipe is not mapped to the frozen P23 protocol")
        payload = self.model_dump(
            mode="json", exclude={"expectation_id", "expectation_hash"}
        )
        digest = canonical_hash(payload)
        if (
            self.expectation_hash != digest
            or self.expectation_id != f"p24n-{digest[:20]}"
        ):
            raise ValueError("negative-control expectation identity is invalid")
        return self


class NegativeControlResult(EvidenceLabModel):
    result_id: str = Field(pattern=r"^p24r-[0-9a-f]{20}$")
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    expectation_id: str
    expectation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    certificate_id: str
    certificate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    observed_outcome: ExpectedControlOutcome
    observed_blocker_keys: tuple[str, ...]
    passed: bool
    authority: Literal["negative_control_evidence_only"] = (
        "negative_control_evidence_only"
    )

    @model_validator(mode="after")
    def result_is_content_addressed(self) -> NegativeControlResult:
        payload = self.model_dump(mode="json", exclude={"result_id", "result_hash"})
        digest = canonical_hash(payload)
        if self.result_hash != digest or self.result_id != f"p24r-{digest[:20]}":
            raise ValueError("negative-control result identity is invalid")
        return self


class CampaignQualificationCertificate(EvidenceLabModel):
    certificate_id: str = Field(pattern=r"^p24c-[0-9a-f]{20}$")
    certificate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    certificate_version: Literal[
        "p24-qualification-certificate-v1",
        "p25-qualification-certificate-v2",
    ]
    created_at: datetime
    collection_kind: P23CollectionKind
    campaign_id: str
    protocol_id: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_id: str
    operation_id: str
    operation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    telemetry_ownership: TelemetryOwnershipTruth | None = None
    run_id: str
    session_id: str
    car_identity: str
    track_identity: str
    build_identity: str
    profile_identity: str | None = None
    setup_identity: str | None = None
    ffb_fingerprint: SteeringContextFingerprint
    steering_configuration: dict[str, float | bool | str | None]
    control_state_history: tuple[ControlStateBoundary, ...]
    flight_recorder: tuple[FlightRecorderEntry, ...]
    eligible_laps: tuple[int, ...]
    excluded_laps: tuple[int, ...]
    exclusion_reasons: dict[int, tuple[str, ...]]
    steering_truth_audit_id: str
    steering_truth_audit_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    channel_health: Literal["pass", "fail", "unknown"]
    sub_tick_coverage_fraction: float = Field(ge=0.0, le=1.0)
    sample_clock_integrity: Literal["pass", "fail", "unknown"]
    independence_identity: str
    duplicate_source: bool
    negative_control_expectation_id: str | None = None
    subgroup_memberships: tuple[str, ...]
    qualification_state: CertificateState
    blocker_reasons: tuple[str, ...]
    dataset_admissions: tuple[DatasetAdmissionRule, ...]
    inventory_retained: Literal[True] = True
    p19_authority_unchanged: Literal[True] = True
    p20_authority_unchanged: Literal[True] = True
    p23_authority: Literal["shadow_only"] = "shadow_only"

    @model_validator(mode="after")
    def certificate_owns_admission_and_identity(self) -> CampaignQualificationCertificate:
        if set(self.eligible_laps) & set(self.excluded_laps):
            raise ValueError("one lap cannot be both admitted and excluded")
        if set(self.exclusion_reasons) != set(self.excluded_laps):
            raise ValueError("every excluded certificate lap requires exact reasons")
        if self.qualification_state == "qualified":
            if self.blocker_reasons or self.duplicate_source or not self.dataset_admissions:
                raise ValueError("qualified certificates require clean unique admission")
        elif not self.blocker_reasons:
            raise ValueError("non-qualified certificates require exact blockers")
        if self.qualification_state != "qualified" and self.dataset_admissions:
            raise ValueError("only a qualified certificate may authorize dataset admission")
        if self.qualification_state == "qualified" and self.collection_kind == "prospective" and not any(
            item.partition == "prospective" for item in self.dataset_admissions
        ):
            raise ValueError("qualified prospective evidence requires prospective admission")
        if self.collection_kind != "prospective" and any(
            item.partition == "prospective" for item in self.dataset_admissions
        ):
            raise ValueError("historical evidence cannot masquerade as prospective")
        if self.certificate_version == "p25-qualification-certificate-v2":
            if self.telemetry_ownership is None:
                raise ValueError("P25 certificates require immutable telemetry ownership")
            if (
                self.telemetry_ownership.run_id != self.run_id
                or self.telemetry_ownership.source_file_sha256 != self.source_file_hash
            ):
                raise ValueError("certificate identity does not match telemetry ownership")
            if (
                self.qualification_state == "qualified"
                and self.telemetry_ownership.state != "verified"
            ):
                raise ValueError("unverified telemetry ownership cannot authorize admission")
        payload = self.model_dump(
            mode="json", exclude={"certificate_id", "certificate_hash"}
        )
        digest = canonical_hash(payload)
        if (
            self.certificate_hash != digest
            or self.certificate_id != f"p24c-{digest[:20]}"
        ):
            raise ValueError("qualification certificate identity does not match evidence")
        return self


class CertificateAdmission(EvidenceLabModel):
    admission_id: str = Field(pattern=r"^p24a-[0-9a-f]{20}$")
    admission_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    certificate_id: str
    certificate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_key: str
    dataset_id: str
    dataset_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    admitted_at: datetime

    @model_validator(mode="after")
    def admission_is_content_addressed(self) -> CertificateAdmission:
        payload = self.model_dump(mode="json", exclude={"admission_id", "admission_hash"})
        digest = canonical_hash(payload)
        if self.admission_hash != digest or self.admission_id != f"p24a-{digest[:20]}":
            raise ValueError("certificate admission identity is invalid")
        return self


class P25NullSessionRunCard(EvidenceLabModel):
    card_id: str = Field(pattern=r"^p25n-[0-9a-f]{20}$")
    card_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    card_version: Literal["p25-null-session-run-card-v1"]
    created_at: datetime
    protocol_id: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_id: str
    operation_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_certificate_id: str
    reference_certificate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reference_run_id: str
    source_file_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    car_identity: str
    build_identity: str
    profile_identity: str
    track_identity: str
    setup_identity: str
    ffb_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    steering_conversion_model: str
    minimum_warmup_laps: Literal[1] = 1
    minimum_eligible_laps: Literal[10] = 10
    fuel_band_minimum: float = Field(allow_inf_nan=False)
    fuel_band_maximum: float = Field(allow_inf_nan=False)
    tire_compound: str
    tire_context_requirement: str
    control_state_requirements: tuple[str, ...] = Field(min_length=1)
    telemetry_requirements: tuple[str, ...] = Field(min_length=10, max_length=10)
    null_expectation: str
    qualification_criteria: tuple[str, ...] = Field(min_length=1)
    state: Literal["ready", "blocked"]
    blocker_reasons: tuple[str, ...] = ()
    observed_run_id: None = None
    observed_qualification_state: None = None
    authority: Literal["pre_outcome_collection_contract_only"] = (
        "pre_outcome_collection_contract_only"
    )

    @model_validator(mode="after")
    def card_is_frozen_before_outcome(self) -> P25NullSessionRunCard:
        if self.fuel_band_maximum < self.fuel_band_minimum:
            raise ValueError("null-session fuel band must be ordered")
        if self.protocol_id != _P23_PROTOCOL.protocol_id or self.protocol_hash != _P23_PROTOCOL.protocol_hash:
            raise ValueError("null-session card must bind the frozen P23 protocol")
        if self.state == "ready" and self.blocker_reasons:
            raise ValueError("ready null-session cards cannot retain blockers")
        if self.state == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked null-session cards require exact blockers")
        payload = self.model_dump(mode="json", exclude={"card_id", "card_hash"})
        digest = canonical_hash(payload)
        if self.card_hash != digest or self.card_id != f"p25n-{digest[:20]}":
            raise ValueError("null-session run-card identity does not match its contract")
        return self


class P23AcquisitionProgress(EvidenceLabModel):
    total_attempts: int = Field(ge=0)
    qualified_attempts: int = Field(ge=0)
    historical_sessions: int = Field(ge=0)
    required_historical_sessions: Literal[9] = 9
    null_stints: int = Field(ge=0)
    required_null_stints: Literal[10] = 10
    negative_controls: int = Field(ge=0)
    required_negative_controls: Literal[8] = 8
    covered_subgroups: int = Field(ge=0)
    required_subgroups: Literal[9] = 9
    subgroup_memberships: tuple[str, ...]
    profile_status: Literal["complete", "incomplete"]
    prospective_sessions: int = Field(ge=0)
    required_prospective_sessions: Literal[10] = 10
    prospective_status: Literal["locked_until_historical_gate", "available", "collecting"]
    rejected_attempts: int = Field(ge=0)
    next_best_collection_kind: P23CollectionPriority
    next_best_collection: str
    latest_certificate_id: str | None = None
    latest_run_id: str | None = None
    latest_qualification_state: CertificateState | None = None
    latest_eligible_laps: int = Field(default=0, ge=0)
    latest_excluded_laps: int = Field(default=0, ge=0)
    latest_blocker: str | None = None
    latest_blockers: tuple[str, ...] = ()
    latest_signal_truth_state: TruthState | None = None
    latest_ffb_fingerprint_state: Literal["ready", "limited", "unavailable"] | None = None
    latest_ffb_fingerprint_sha256: str | None = None
    latest_dataset_admissions: tuple[str, ...] = ()
    latest_telemetry_ownership_state: Literal["verified", "blocked"] | None = None
    latest_null_run_card: P25NullSessionRunCard | None = None
    latest_flight_recorder: tuple[FlightRecorderEntry, ...] = ()
    latest_flight_recorder_total: int = Field(default=0, ge=0)
    latest_flight_recorder_truncated: bool = False
    activation_status: Literal["no_activation_earned"] = "no_activation_earned"
    p23_authority: Literal["shadow_only"] = "shadow_only"

    @model_validator(mode="after")
    def progress_is_internally_consistent(self) -> P23AcquisitionProgress:
        if self.qualified_attempts + self.rejected_attempts != self.total_attempts:
            raise ValueError("attempt counts must reconcile")
        if self.covered_subgroups != len(set(self.subgroup_memberships)):
            raise ValueError("subgroup count must match distinct memberships")
        if self.latest_flight_recorder_total < len(self.latest_flight_recorder):
            raise ValueError("flight-recorder total cannot be smaller than its preview")
        if self.latest_flight_recorder_truncated != (
            self.latest_flight_recorder_total > len(self.latest_flight_recorder)
        ):
            raise ValueError("flight-recorder truncation state is inconsistent")
        return self


class PreRunRequirement(EvidenceLabModel):
    key: str
    label: str
    state: Literal["pass", "block", "unknown"]
    observed: str


class P23PreRunChecklist(EvidenceLabModel):
    protocol_id: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    collection_kind: P23CollectionKind
    run_id: str
    requirements: tuple[PreRunRequirement, ...]
    target_clean_laps: int = Field(ge=0)
    campaign_progress: P23AcquisitionProgress
    ready_to_record: bool
    blockers: tuple[str, ...]
    live_telemetry_claimed: Literal[False] = False
    authority: Literal["collection_guidance_only"] = "collection_guidance_only"


class P23CollectionTemplate(EvidenceLabModel):
    collection_kind: P23CollectionKind
    label: str
    state: Literal["available", "locked", "complete"]
    protocol_id: str
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_units: int = Field(ge=1)
    current_units: int = Field(ge=0)
    minimum_clean_laps: int = Field(ge=0)
    requirements: tuple[str, ...]
    blocker_reasons: tuple[str, ...]
    authority: Literal["collection_template_only"] = "collection_template_only"


class NegativeControlRecipe(EvidenceLabModel):
    recipe_id: str
    label: str
    protocol_control_id: str
    expected_blocker_keys: tuple[str, ...]
    expected_outcome: ExpectedControlOutcome
    authority: Literal["expectation_template_only"] = "expectation_template_only"


_NEGATIVE_CONTROL_RECIPES: dict[
    str, tuple[str, tuple[str, ...], ExpectedControlOutcome]
] = {
    "same_setup_unchanged": (
        "same_setup_unchanged",
        ("comparison_allowed",),
        "comparison_allowed",
    ),
    "stable_steering_response": (
        "stable_steering_response",
        ("comparison_allowed",),
        "comparison_allowed",
    ),
    "max_force_mismatch": (
        "ffb_config_changed",
        ("max_force_nm",),
        "comparison_rejected",
    ),
    "linear_mode_mismatch": (
        "ffb_config_changed",
        ("use_linear",),
        "comparison_rejected",
    ),
    "smoothing_mismatch": (
        "ffb_config_changed",
        ("smoothing_01",),
        "comparison_rejected",
    ),
    "damper_mismatch": (
        "ffb_config_changed",
        ("damper_01",),
        "comparison_rejected",
    ),
    "steering_ratio_mismatch": (
        "ffb_config_changed",
        ("steering_conversion_model",),
        "comparison_rejected",
    ),
    "sample_clock_corruption": (
        "sim_integrity_degraded",
        ("sample_clock_integrity",),
        "comparison_rejected",
    ),
    "sub_tick_corruption": (
        "sim_integrity_degraded",
        ("sub_tick_integrity",),
        "comparison_rejected",
    ),
    "profile_build_mismatch": (
        "profile_build_mismatch",
        ("profile_or_build",),
        "comparison_rejected",
    ),
    "driver_line_mismatch": (
        "driver_line_changed",
        ("driver_line_context",),
        "comparison_rejected",
    ),
    "traffic_context_mismatch": (
        "traffic_context_mismatch",
        ("traffic_context",),
        "comparison_rejected",
    ),
    "pit_context_boundary": (
        "pit_context_boundary",
        ("pit_context",),
        "comparison_rejected",
    ),
}

_NEGATIVE_CONTROL_LABELS = {
    "same_setup_unchanged": "Same setup, unchanged context",
    "stable_steering_response": "Stable steering response",
    "max_force_mismatch": "FFB MaxForce mismatch",
    "linear_mode_mismatch": "FFB linear-mode mismatch",
    "smoothing_mismatch": "FFB smoothing mismatch",
    "damper_mismatch": "FFB damper mismatch",
    "steering_ratio_mismatch": "Steering conversion mismatch",
    "sample_clock_corruption": "Sample-clock corruption",
    "sub_tick_corruption": "Sub-tick integrity corruption",
    "profile_build_mismatch": "Vehicle profile or build mismatch",
    "driver_line_mismatch": "Driver-line context mismatch",
    "traffic_context_mismatch": "Traffic context mismatch",
    "pit_context_boundary": "Pit-context boundary",
}


def negative_control_recipes() -> dict[str, tuple[str, ...]]:
    return {
        recipe_id: expected_keys
        for recipe_id, (_protocol_id, expected_keys, _outcome) in _NEGATIVE_CONTROL_RECIPES.items()
    }


def negative_control_recipe_catalog() -> tuple[NegativeControlRecipe, ...]:
    """Return frozen expectation templates without creating an experiment."""

    return tuple(
        NegativeControlRecipe(
            recipe_id=recipe_id,
            label=_NEGATIVE_CONTROL_LABELS[recipe_id],
            protocol_control_id=protocol_control_id,
            expected_blocker_keys=expected_keys,
            expected_outcome=expected_outcome,
        )
        for recipe_id, (
            protocol_control_id,
            expected_keys,
            expected_outcome,
        ) in _NEGATIVE_CONTROL_RECIPES.items()
    )


def p23_collection_templates(
    *, db_path: str | Path | None = None
) -> tuple[P23CollectionTemplate, ...]:
    progress = p23_acquisition_progress(db_path=db_path)
    shared = (
        "exact Next Gen car and iRacing build",
        "complete frozen FFB fingerprint",
        "source-validated steering ratio or pinion",
        "healthy 360 Hz steering torque and sample clock",
        "one immutable source-file session identity",
    )
    definitions = (
        (
            "historical_exact_ffb",
            "Historical exact-FFB session",
            progress.historical_sessions,
            9,
            10,
            (),
        ),
        (
            "same_setup_null",
            "Same-setup null stint",
            progress.null_stints,
            10,
            10,
            ("same setup and no intended intervention",),
        ),
        (
            "negative_control",
            "Frozen negative control",
            progress.negative_controls,
            8,
            0,
            ("expected outcome frozen before observed import",),
        ),
        (
            "profile_validation",
            "Steering signal and conversion validation",
            1 if progress.profile_status == "complete" else 0,
            1,
            0,
            ("units, signs, timing, clipping, limiter, and scalar/sub-tick relationship",),
        ),
        (
            "prospective",
            "Genuinely prospective source session",
            progress.prospective_sessions,
            10,
            10,
            ("prediction frozen before outcome",),
        ),
    )
    templates = []
    for kind, label, current, required, laps, extra in definitions:
        locked = kind == "prospective" and progress.prospective_status == "locked_until_historical_gate"
        state: Literal["available", "locked", "complete"] = (
            "complete" if current >= required else "locked" if locked else "available"
        )
        templates.append(
            P23CollectionTemplate(
                collection_kind=kind,
                label=label,
                state=state,
                protocol_id=_P23_PROTOCOL.protocol_id,
                protocol_hash=_P23_PROTOCOL.protocol_hash,
                required_units=required,
                current_units=current,
                minimum_clean_laps=laps,
                requirements=(*shared, *extra),
                blocker_reasons=(
                    ("Historical validation must pass before prospective collection.",)
                    if locked
                    else ()
                ),
            )
        )
    return tuple(templates)


def _content_addressed(model: type[EvidenceLabModel], prefix: str, payload: dict[str, Any]):
    id_field, hash_field = {
        "p24s": ("audit_id", "audit_hash"),
        "p24n": ("expectation_id", "expectation_hash"),
        "p24r": ("result_id", "result_hash"),
        "p24c": ("certificate_id", "certificate_hash"),
        "p24a": ("admission_id", "admission_hash"),
        "p25n": ("card_id", "card_hash"),
    }[prefix]
    constructed = model.model_construct(
        **{id_field: f"{prefix}-" + "0" * 20, hash_field: "0" * 64, **payload}
    )
    digest = canonical_hash(
        constructed.model_dump(mode="json", exclude={id_field, hash_field})
    )
    return model(**{id_field: f"{prefix}-{digest[:20]}", hash_field: digest, **payload})


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _manifest_channel(manifest: Mapping[str, Any], aliases: Sequence[str]) -> Mapping[str, Any] | None:
    for channel in manifest.get("channels", ()):
        if not isinstance(channel, Mapping):
            continue
        if channel.get("raw_name") in aliases or channel.get("canonical_name") in aliases:
            return channel
    return None


def _unit_matches(
    actual: str | None,
    expected: Sequence[str],
    *,
    data_type: str | None = None,
) -> bool:
    if any(item.casefold() == "bool" for item in expected):
        return str(data_type or "").casefold() in {"bool", "boolean"}
    if actual is None:
        return False
    normalized = actual.casefold().replace(" ", "").replace("·", "*")
    return any(
        normalized == item.casefold().replace(" ", "").replace("·", "*")
        for item in expected
    )


def _row_value(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        if alias in row and row[alias] is not None:
            return row[alias]
    return None


def _scalar_subtick_relation(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[str, float | None]:
    errors: dict[str, list[float]] = {"mean": [], "first": [], "last": []}
    magnitudes: list[float] = []
    for row in rows:
        scalar = _finite(_row_value(row, ("steering_wheel_torque_nm", "SteeringWheelTorque")))
        raw = _row_value(
            row,
            ("steering_wheel_torque_subtick_nm", "SteeringWheelTorque_ST"),
        )
        if scalar is None or not isinstance(raw, (list, tuple)):
            continue
        samples = [number for value in raw if (number := _finite(value)) is not None]
        if not samples:
            continue
        magnitudes.append(abs(scalar))
        errors["mean"].append(abs(scalar - sum(samples) / len(samples)))
        errors["first"].append(abs(scalar - samples[0]))
        errors["last"].append(abs(scalar - samples[-1]))
    if not magnitudes or not any(errors.values()):
        return "unavailable", None
    scale = max(0.1, median(magnitudes))
    normalized = {
        key: median(values) / scale for key, values in errors.items() if values
    }
    best = min(normalized, key=normalized.get)
    error = normalized[best]
    if error > 0.10:
        return "inconsistent", error
    return f"{best}_consistent", error


def _clock_integrity(manifest: Mapping[str, Any]) -> Literal["pass", "fail", "unknown"]:
    continuity = manifest.get("sample_continuity")
    if not isinstance(continuity, Mapping):
        return "unknown"
    status = str(continuity.get("status") or "").casefold()
    if status in {"healthy", "ready", "pass"}:
        return "pass"
    tick_available = continuity.get("session_tick_available") is True
    tick_faults = sum(
        int(continuity.get(key) or 0)
        for key in (
            "invalid_tick_sample_count",
            "duplicate_tick_transition_count",
            "reversed_tick_transition_count",
            "estimated_dropped_tick_count",
        )
    )
    if tick_available:
        return "pass" if tick_faults == 0 else "fail"
    if status in {"warning", "failed", "fail", "invalid", "issues_detected"}:
        return "fail"
    discontinuities = continuity.get("discontinuity_count")
    return "pass" if discontinuities == 0 else "fail" if discontinuities else "unknown"


def _sub_tick_clock_truth(
    manifest: Mapping[str, Any],
    channel: SignalTruth,
) -> SubTickClockTruth:
    continuity = manifest.get("sample_continuity")
    source = continuity if isinstance(continuity, Mapping) else {}
    debt: list[str] = []
    if source.get("session_tick_available") is not True:
        debt.append("SessionTick is unavailable for record-to-record reconstruction.")
    for key, label in (
        ("invalid_tick_sample_count", "invalid SessionTick samples"),
        ("duplicate_tick_transition_count", "duplicate SessionTick transitions"),
        ("reversed_tick_transition_count", "reversed SessionTick transitions"),
        ("estimated_dropped_tick_count", "dropped SessionTick records"),
    ):
        if int(source.get(key) or 0) > 0:
            debt.append(f"The recording contains {label}.")
    if not channel.count_as_time:
        debt.append("The sub-tick array is not declared count-as-time.")
    if channel.samples_per_record != 6:
        debt.append("The sub-tick array does not contain exactly six ordered samples per record.")
    if channel.base_sample_rate_hz is None or not math.isclose(
        channel.base_sample_rate_hz, 60.0, rel_tol=0.0, abs_tol=0.1
    ):
        debt.append("The base record clock is not proven at 60 Hz.")
    if channel.effective_sample_rate_hz is None or not math.isclose(
        channel.effective_sample_rate_hz, 360.0, rel_tol=0.0, abs_tol=0.5
    ):
        debt.append("The reconstructed sub-tick clock is not proven at 360 Hz.")
    state: Literal["pass", "fail", "unknown"]
    state = "pass" if not debt else "fail" if continuity is not None else "unknown"
    return SubTickClockTruth(
        state=state,
        ordering_source=(
            "session_tick_count_as_time"
            if source.get("session_tick_available") is True and channel.count_as_time
            else "unavailable"
        ),
        samples_per_record=channel.samples_per_record,
        base_sample_rate_hz=channel.base_sample_rate_hz,
        effective_sample_rate_hz=channel.effective_sample_rate_hz,
        session_tick_available=source.get("session_tick_available") is True,
        invalid_tick_sample_count=int(source.get("invalid_tick_sample_count") or 0),
        duplicate_tick_transition_count=int(
            source.get("duplicate_tick_transition_count") or 0
        ),
        reversed_tick_transition_count=int(
            source.get("reversed_tick_transition_count") or 0
        ),
        estimated_dropped_tick_count=int(source.get("estimated_dropped_tick_count") or 0),
        invalid_timestamp_sample_count=int(
            source.get("invalid_timestamp_sample_count") or 0
        ),
        non_monotonic_timestamp_transition_count=int(
            source.get("non_monotonic_timestamp_transition_count") or 0
        ),
        timestamp_gap_count=int(source.get("timestamp_gap_count") or 0),
        scientific_debt=tuple(debt),
    )


def _source_hash(manifest: Mapping[str, Any], fallback: str | None = None) -> str:
    value = str(manifest.get("source_file_sha256") or fallback or "").strip().casefold()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("P24 requires an immutable SHA-256 source-file identity")
    return value


def _steering_conversion(overview: Any) -> str | None:
    snapshot = overview.setup_snapshot
    if snapshot is None:
        return None
    value = snapshot.steering_ratio
    if value is None:
        value = snapshot.extracted_values.get("steering_ratio")
    text = str(value).strip() if value is not None else ""
    return text or None


def build_steering_signal_truth_audit(
    *,
    run_id: str,
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    steering_conversion_model: str | None,
    source_file_hash: str | None = None,
    created_at: datetime | None = None,
) -> SteeringSignalTruthAudit:
    source_hash = _source_hash(manifest, source_file_hash)
    channels: list[SignalTruth] = []
    for key, aliases, expected_units, required in _STEERING_CHANNELS:
        manifest_channel = _manifest_channel(manifest, aliases)
        debt: list[str] = []
        source_channel = None
        raw_unit = None
        data_type = None
        base_rate = None
        effective_rate = None
        samples_per_record = 0
        count_as_time = False
        coverage = 0.0
        variation = "missing"
        sample_structure: Literal["scalar", "count_as_time_array", "unavailable"] = (
            "unavailable"
        )
        update_behavior: Literal[
            "continuous_per_record",
            "stable_configuration",
            "changing_configuration",
            "fixed_limit",
            "unavailable",
        ] = "unavailable"
        canonical_mapping = None
        comparison_role: Literal["measurement", "configuration", "limit"] = (
            "measurement"
            if key in {"SteeringWheelTorque_ST", "SteeringWheelTorque", "SteeringWheelAngle"}
            else "limit"
            if key == "SteeringWheelAngleMax"
            else "configuration"
        )
        health_status = "missing"
        clipping_status = "unavailable"
        saturation_status = "unavailable"
        sign = "not_applicable"
        if manifest_channel is None:
            debt.append("Channel is not declared in the immutable telemetry manifest.")
            state: TruthState = "missing"
        else:
            source_channel = str(
                manifest_channel.get("raw_name")
                or manifest_channel.get("canonical_name")
                or key
            )
            raw_unit = str(manifest_channel.get("unit") or "") or None
            data_type = str(manifest_channel.get("data_type") or "") or None
            canonical_mapping = (
                str(manifest_channel.get("canonical_name") or "") or None
            )
            base_rate = _finite(manifest_channel.get("base_sample_rate_hz"))
            effective_rate = _finite(manifest_channel.get("effective_sample_rate_hz"))
            samples_per_record = int(manifest_channel.get("samples_per_record") or 0)
            count_as_time = bool(manifest_channel.get("count_as_time"))
            record_count = int(manifest_channel.get("record_count") or 0)
            valid_count = int(manifest_channel.get("valid_record_count") or 0)
            coverage = valid_count / record_count if record_count > 0 else 0.0
            variation = str(manifest_channel.get("variation") or "unknown")
            health_status = str(manifest_channel.get("health_status") or "unknown")
            clipping_status = str(
                manifest_channel.get("clipping_status") or "unknown"
            )
            saturation_status = str(
                manifest_channel.get("saturation_status") or "unknown"
            )
            sample_structure = (
                "count_as_time_array"
                if count_as_time and samples_per_record > 1
                else "scalar"
            )
            update_behavior = (
                "fixed_limit"
                if comparison_role == "limit"
                else "stable_configuration"
                if comparison_role == "configuration" and variation == "constant"
                else "changing_configuration"
                if comparison_role == "configuration"
                else "continuous_per_record"
            )
            if not _unit_matches(raw_unit, expected_units, data_type=data_type):
                debt.append("Manifest unit does not match the frozen channel contract.")
            if coverage < 0.95:
                debt.append("Channel coverage is below 95 percent.")
            if health_status.casefold() not in {"healthy", "ready", "pass"}:
                debt.append("Manifest channel health is not proven healthy.")
            if int(manifest_channel.get("malformed_array_record_count") or 0) > 0:
                debt.append("Malformed array records are present.")
            if int(manifest_channel.get("non_finite_sample_count") or 0) > 0:
                debt.append("Non-finite samples are present.")
            if int(manifest_channel.get("numeric_limit_hit_count") or 0) > 0:
                debt.append("Numeric rail or limit hits are present.")
            if key in {"SteeringWheelTorque_ST", "SteeringWheelTorque"} and (
                clipping_status.casefold() not in {"none_detected", "none", "clear"}
                or saturation_status.casefold() not in {"none_detected", "none", "clear"}
            ):
                debt.append("Steering torque clipping or saturation is present.")
            if key == "SteeringWheelTorque_ST":
                sign = "observed_signed"
                if not count_as_time or samples_per_record < 2:
                    debt.append("Sub-tick array order is not declared count-as-time.")
                if effective_rate is None or effective_rate < 300.0:
                    debt.append("Effective sub-tick rate is below the 360 Hz contract.")
            elif key in {"SteeringWheelTorque", "SteeringWheelAngle"}:
                sign = "observed_signed"
            elif key in {"SteeringWheelUseLinear"}:
                sign = "unsigned_configuration"
            state = "ready" if not debt else "scientific_debt"
        channels.append(
            SignalTruth(
                channel_key=key,
                source_channel=source_channel,
                raw_unit=raw_unit,
                data_type=data_type,
                expected_units=expected_units,
                unit_verified=_unit_matches(
                    raw_unit,
                    expected_units,
                    data_type=data_type,
                ),
                sample_structure=sample_structure,
                sign_semantics=sign,
                base_sample_rate_hz=base_rate,
                effective_sample_rate_hz=effective_rate,
                samples_per_record=samples_per_record,
                count_as_time=count_as_time,
                coverage_fraction=coverage,
                variation=variation,
                update_behavior=update_behavior,
                canonical_mapping=canonical_mapping,
                comparison_role=comparison_role,
                health_status=health_status,
                clipping_status=clipping_status,
                saturation_status=saturation_status,
                state=state,
                scientific_debt=tuple(debt),
                required_for_admission=required,
            )
        )
    relation, normalized_error = _scalar_subtick_relation(rows)
    sub_tick = next(item for item in channels if item.channel_key == "SteeringWheelTorque_ST")
    sub_tick_clock = _sub_tick_clock_truth(manifest, sub_tick)
    ffb = build_steering_context_fingerprint(
        rows,
        steering_conversion_model=steering_conversion_model,
        required_fields=P23_STEERING_FINGERPRINT_FIELDS,
    )
    blockers = [
        f"{item.channel_key}: {reason}"
        for item in channels
        if item.required_for_admission
        for reason in item.scientific_debt
    ]
    if relation == "unavailable":
        blockers.append("The 60 Hz versus sub-tick torque relationship is unavailable.")
    elif relation == "inconsistent":
        blockers.append("The 60 Hz versus sub-tick torque relationship is inconsistent.")
    if sub_tick_clock.state != "pass":
        blockers.extend(sub_tick_clock.scientific_debt)
    if steering_conversion_model is None:
        blockers.append("Steering ratio/pinion conversion is not source validated.")
    blockers.extend(ffb.blocker_reasons)
    state: TruthState = "ready" if not blockers else "scientific_debt"
    payload = {
        "audit_version": "p24-steering-signal-truth-v1",
        "created_at": created_at or datetime.now(UTC),
        "run_id": run_id,
        "source_file_hash": source_hash,
        "protocol_id": _P23_PROTOCOL.protocol_id,
        "protocol_hash": _P23_PROTOCOL.protocol_hash,
        "channels": tuple(channels),
        "ffb_fingerprint": ffb,
        "scalar_subtick_relation": relation,
        "scalar_subtick_normalized_error": normalized_error,
        "sub_tick_coverage_fraction": sub_tick.coverage_fraction,
        "sub_tick_clock": sub_tick_clock,
        "sample_clock_integrity": sub_tick_clock.state,
        "effective_sub_tick_rate_hz": sub_tick.effective_sample_rate_hz,
        "steering_conversion_model": steering_conversion_model,
        "state": state,
        "blocker_reasons": tuple(dict.fromkeys(blockers)),
        "authority": "scientific_qualification_only",
    }
    return _content_addressed(SteeringSignalTruthAudit, "p24s", payload)


def freeze_negative_control_expectation(
    *,
    recipe_id: str,
    operation: CampaignOperation,
    created_at: datetime | None = None,
) -> NegativeControlExpectation:
    if recipe_id not in _NEGATIVE_CONTROL_RECIPES:
        raise ValueError(f"Unknown P24 negative-control recipe: {recipe_id}")
    protocol_control_id, expected_keys, expected_outcome = _NEGATIVE_CONTROL_RECIPES[
        recipe_id
    ]
    payload = {
        "expectation_version": "p24-negative-control-v1",
        "created_at": created_at or datetime.now(UTC),
        "recipe_id": recipe_id,
        "protocol_control_id": protocol_control_id,
        "operation_id": operation.operation_id,
        "operation_hash": operation.operation_hash,
        "reference_run_id": operation.context.reference_run_id,
        "protocol_id": _P23_PROTOCOL.protocol_id,
        "protocol_hash": _P23_PROTOCOL.protocol_hash,
        "expected_outcome": expected_outcome,
        "expected_blocker_keys": expected_keys,
        "observed_run_id": None,
        "observed_result": None,
        "authority": "pre_outcome_expectation_only",
    }
    return _content_addressed(NegativeControlExpectation, "p24n", payload)


def _setup_identity(overview: Any) -> str | None:
    return (
        None
        if overview.setup_snapshot is None
        else canonical_hash(
            overview.setup_snapshot.model_dump(
                mode="json",
                exclude={"setup_id", "run_id", "setup_name"},
            )
        )
    )


def _subgroups(overview: Any, accepted_laps: Sequence[int]) -> tuple[str, ...]:
    track = str(overview.session.track_id_or_path or "").casefold()
    if any(name in track for name in ("talladega", "daytona")):
        track_group = "superspeedway"
    elif any(name in track for name in ("bristol", "martinsville", "richmond", "north wilkesboro")):
        track_group = "short_track"
    else:
        track_group = "intermediate"
    run_group = "long_run" if len(accepted_laps) >= 20 else "short_run"
    return tuple(item for item in (track_group, run_group) if item in _REQUIRED_SUBGROUPS)


def _control_boundaries(
    mutations: Sequence[ControlMutationEvent],
) -> tuple[ControlStateBoundary, ...]:
    return tuple(
        ControlStateBoundary(
            mutation_id=item.mutation_id,
            control_key=item.control_key,
            mutation_kind=item.mutation_kind.value,
            lap_number=item.lap,
            lap_pct=item.lap_pct,
            previous_value=item.previous_value,
            new_value=item.new_value,
            applied_state_confirmed=item.applied_state_confirmed,
        )
        for item in mutations
    )


def _flight_recorder(
    *,
    overview: Any,
    assessment: CampaignRunAssessment,
    truth: SteeringSignalTruthAudit,
    mutations: Sequence[ControlMutationEvent],
) -> tuple[FlightRecorderEntry, ...]:
    accepted = set(assessment.accepted_lap_numbers)
    rejected = set(assessment.rejected_lap_numbers)
    by_lap: dict[int, list[ControlMutationEvent]] = {}
    for mutation in mutations:
        by_lap.setdefault(mutation.lap, []).append(mutation)
    entries = []
    setup_fingerprint = _setup_identity(overview)
    for lap in sorted(overview.laps, key=lambda item: item.lap_number):
        lap_mutations = by_lap.get(lap.lap_number, [])
        applied = tuple(
            item.mutation_id
            for item in lap_mutations
            if item.mutation_kind.value in {"applied_state", "confirmed_service"}
        )
        requested = tuple(
            item.mutation_id
            for item in lap_mutations
            if item.mutation_kind.value == "requested_state"
        )
        if lap_mutations:
            state = "context_boundary"
            reasons = tuple(
                f"{item.mutation_kind.value}: {item.control_key}" for item in lap_mutations
            )
        elif lap.lap_number in accepted:
            state = "qualified"
            reasons = ()
        elif lap.lap_number in rejected:
            state = "excluded"
            reasons = assessment.lap_rejection_reasons[lap.lap_number]
        else:
            canonical = tuple(lap_ineligibility_reasons(lap))
            state = "excluded" if canonical else "inventory"
            reasons = canonical or ("Lap is outside the campaign qualification block.",)
        nearby: Literal["acceptable", "rejected", "unknown"] = "unknown"
        if state == "qualified":
            nearby = "acceptable"
        elif any("nearby" in reason.casefold() or "traffic" in reason.casefold() for reason in reasons):
            nearby = "rejected"
        entries.append(
            FlightRecorderEntry(
                lap_number=lap.lap_number,
                state=state,
                reasons=reasons,
                setup_fingerprint=setup_fingerprint,
                ffb_fingerprint=truth.ffb_fingerprint.fingerprint_sha256,
                applied_control_mutation_ids=applied,
                requested_control_mutation_ids=requested,
                nearby_context=nearby,
                sample_continuity=truth.sample_clock_integrity,
                sub_tick_coverage_fraction=truth.sub_tick_coverage_fraction,
            )
        )
    return tuple(entries)


def _duplicate_source(
    source_file_hash: str,
    *,
    operation_id: str,
    run_id: str,
    db_path: str | Path | None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT certificate_id FROM p24_qualification_certificates "
            "WHERE source_file_hash = ? AND qualification_state = 'qualified' "
            "AND NOT (operation_id = ? AND run_id = ?) LIMIT 1",
            (source_file_hash, operation_id, run_id),
        ).fetchone()
    finally:
        connection.close()
    return row is not None


def _admission_rule(kind: P23CollectionKind) -> DatasetAdmissionRule:
    mapping: dict[P23CollectionKind, tuple[DatasetKind, str, str, str]] = {
        "historical_exact_ffb": (
            "driver_repeatability",
            "evaluation",
            "source_declared_reference",
            "steering_workload_historical",
        ),
        "same_setup_null": (
            "null_no_change",
            "evaluation",
            "same_setup_null",
            "steering_workload_negative_control",
        ),
        "negative_control": (
            "shadow_observer_ground_truth",
            "evaluation",
            "source_declared_reference",
            "steering_workload_negative_control",
        ),
        "profile_validation": (
            "vehicle_profile_validation",
            "evaluation",
            "source_declared_reference",
            "steering_signal_profile_validation",
        ),
        "prospective": (
            "driver_repeatability",
            "prospective",
            "prospective_observed_outcome",
            "steering_workload_prospective",
        ),
    }
    dataset_kind, partition, ground_truth, allowed_use = mapping[kind]
    return DatasetAdmissionRule(
        admission_key=f"p23:{kind}",
        dataset_kind=dataset_kind,
        partition=partition,
        ground_truth_type=ground_truth,
        allowed_use=allowed_use,
    )


def _scientific_blocker_keys(reasons: Sequence[str]) -> tuple[str, ...]:
    keys: list[str] = []
    for reason in reasons:
        lowered = reason.casefold()
        for key in (
            "max_force_nm",
            "use_linear",
            "smoothing_01",
            "damper_01",
            "steering_conversion_model",
        ):
            if key in lowered:
                keys.append(key)
        if "sample clock" in lowered or "sample continuity" in lowered:
            keys.append("sample_clock_integrity")
        if "sub-tick" in lowered or "sub_tick" in lowered:
            keys.append("sub_tick_integrity")
        if "build identity" in lowered or "profile" in lowered or "car identity" in lowered:
            keys.append("profile_or_build")
        if "nearby" in lowered or "traffic" in lowered:
            keys.append("traffic_context")
        if "driver line" in lowered or "line mismatch" in lowered:
            keys.append("driver_line_context")
        if "pit" in lowered or "out lap" in lowered:
            keys.append("pit_context")
    return tuple(dict.fromkeys(keys))


def _longest_uninterrupted_lap_block(
    lap_numbers: Sequence[int],
    *,
    boundary_laps: set[int],
) -> tuple[int, ...]:
    """Select one clean block without bridging rejected or mutation laps."""

    groups: list[list[int]] = []
    for lap_number in sorted(set(lap_numbers) - boundary_laps):
        if not groups or lap_number != groups[-1][-1] + 1:
            groups.append([lap_number])
        else:
            groups[-1].append(lap_number)
    if not groups:
        return ()
    return tuple(max(groups, key=lambda group: (len(group), -group[0])))


def _telemetry_ownership_truth(
    manifest: Mapping[str, Any],
    *,
    run_id: str,
    source_file_hash: str,
) -> TelemetryOwnershipTruth:
    manifest_run_id = str(manifest.get("run_id") or "").strip()
    manifest_source = str(manifest.get("source_file_sha256") or "").strip()
    cache_hash = str(manifest.get("telemetry_cache_sha256") or "").strip()
    schema_fingerprint = str(manifest.get("schema_fingerprint") or "").strip()
    source_size = manifest.get("source_file_size_bytes")
    blockers: list[str] = []
    def valid_sha256(value: str) -> bool:
        return len(value) == 64 and not any(
            character not in "0123456789abcdef" for character in value.casefold()
        )

    if manifest_run_id != run_id:
        blockers.append(
            f"Telemetry manifest run identity {manifest_run_id or 'missing'} does not match {run_id}."
        )
    if manifest_source != source_file_hash:
        blockers.append("Telemetry manifest source SHA-256 does not match the imported source.")
    if not isinstance(source_size, int) or isinstance(source_size, bool) or source_size <= 0:
        blockers.append("Telemetry manifest source-file byte size is missing or invalid.")
        source_size = None
    if not valid_sha256(cache_hash):
        blockers.append("Telemetry cache SHA-256 is missing or invalid.")
        cache_hash = ""
    if not valid_sha256(schema_fingerprint):
        blockers.append("Telemetry schema fingerprint is missing or invalid.")
        schema_fingerprint = ""
    return TelemetryOwnershipTruth(
        state="blocked" if blockers else "verified",
        run_id=run_id,
        source_file_sha256=manifest_source if valid_sha256(manifest_source) else None,
        source_file_size_bytes=source_size,
        telemetry_cache_sha256=cache_hash or None,
        schema_fingerprint=schema_fingerprint or None,
        blocker_reasons=tuple(blockers),
    )


def build_qualification_certificate(
    *,
    collection_kind: P23CollectionKind,
    operation: CampaignOperation,
    assessment: CampaignRunAssessment,
    overview: Any,
    manifest: Mapping[str, Any],
    truth_audit: SteeringSignalTruthAudit,
    mutations: Sequence[ControlMutationEvent] = (),
    duplicate_source: bool = False,
    negative_control_expectation: NegativeControlExpectation | None = None,
    created_at: datetime | None = None,
) -> CampaignQualificationCertificate:
    source_hash = _source_hash(manifest, overview.session.file_hash)
    ownership = _telemetry_ownership_truth(
        manifest,
        run_id=assessment.run_id,
        source_file_hash=source_hash,
    )
    identity = manifest.get("compatibility_identity") or {}
    car_identity = str(identity.get("car_path") or overview.session.car_path or "").strip()
    track_identity = str(
        identity.get("track_id")
        or identity.get("track_id_or_path")
        or overview.session.track_id_or_path
        or ""
    ).strip()
    build_identity = str(identity.get("iracing_build_version") or "").strip()
    blockers = [
        reason
        for reason in assessment.rejection_reasons
        if "requires a controlled workflow or external validation record" not in reason
    ]
    if truth_audit.state != "ready":
        blockers.extend(truth_audit.blocker_reasons)
    if ownership.state != "verified":
        blockers.extend(ownership.blocker_reasons)
    if duplicate_source:
        blockers.append("This immutable source-file session already counted.")
    expected_ffb = operation.context.ffb_fingerprint_sha256
    if expected_ffb and truth_audit.ffb_fingerprint.fingerprint_sha256 != expected_ffb:
        comparability = compare_steering_contexts(
            operation.context.ffb_fingerprint,
            truth_audit.ffb_fingerprint,
        ) if operation.context.ffb_fingerprint is not None else None
        mismatches = comparability.material_mismatches if comparability else ("ffb_fingerprint",)
        blockers.extend(f"FFB mismatch: {item}" for item in mismatches)
    mutation_laps = {item.lap for item in mutations}
    eligible_laps = _longest_uninterrupted_lap_block(
        assessment.accepted_lap_numbers,
        boundary_laps=mutation_laps,
    )
    if len(eligible_laps) < operation.context.minimum_clean_laps_per_unit:
        blockers.append(
            f"Only {len(eligible_laps)} clean laps qualify; "
            f"{operation.context.minimum_clean_laps_per_unit} are required."
        )
    if not car_identity:
        blockers.append("Car identity is unavailable.")
    if not build_identity:
        blockers.append("iRacing build identity is unavailable.")
    if not track_identity:
        blockers.append("Track identity is unavailable.")
    if collection_kind == "prospective":
        blockers.append("Prospective P23 collection is locked until historical validation passes.")
    if collection_kind == "negative_control":
        if negative_control_expectation is None:
            blockers.append("Negative-control expected outcome was not frozen pre-observation.")
        else:
            observed_keys = set(_scientific_blocker_keys(blockers))
            intentional = set(negative_control_expectation.expected_blocker_keys)
            if (
                negative_control_expectation.expected_outcome == "comparison_rejected"
                and intentional
                and intentional <= observed_keys
            ):
                blockers = [
                    reason
                    for reason in blockers
                    if not set(_scientific_blocker_keys((reason,))) & intentional
                ]
    blockers = list(dict.fromkeys(blockers))
    if not blockers:
        state: CertificateState = "qualified"
    elif eligible_laps:
        state = "partial"
    elif overview.laps:
        state = "rejected"
    else:
        state = "inventory_only"
    admissions = (_admission_rule(collection_kind),) if state == "qualified" else ()
    recorder = _flight_recorder(
        overview=overview,
        assessment=assessment,
        truth=truth_audit,
        mutations=mutations,
    )
    setup_identity = _setup_identity(overview)
    payload = {
        "certificate_version": "p25-qualification-certificate-v2",
        "created_at": created_at or datetime.now(UTC),
        "collection_kind": collection_kind,
        "campaign_id": operation.campaign_id,
        "protocol_id": _P23_PROTOCOL.protocol_id,
        "protocol_hash": _P23_PROTOCOL.protocol_hash,
        "attempt_id": assessment.assessment_id,
        "operation_id": operation.operation_id,
        "operation_hash": operation.operation_hash,
        "source_file_hash": source_hash,
        "telemetry_ownership": ownership,
        "run_id": assessment.run_id,
        "session_id": f"source-session:{source_hash}",
        "car_identity": car_identity or "unavailable",
        "track_identity": track_identity or "unavailable",
        "build_identity": build_identity or "unavailable",
        "profile_identity": canonical_hash(
            {
                "car": car_identity,
                "build": build_identity,
                "steering_conversion": truth_audit.steering_conversion_model,
            }
        ),
        "setup_identity": setup_identity,
        "ffb_fingerprint": truth_audit.ffb_fingerprint,
        "steering_configuration": {
            "max_force_nm": truth_audit.ffb_fingerprint.max_force_nm,
            "use_linear": truth_audit.ffb_fingerprint.use_linear,
            "intensity_01": truth_audit.ffb_fingerprint.intensity_01,
            "smoothing_01": truth_audit.ffb_fingerprint.smoothing_01,
            "damper_01": truth_audit.ffb_fingerprint.damper_01,
            "limiter_01": truth_audit.ffb_fingerprint.limiter_01,
            "steering_conversion_model": truth_audit.steering_conversion_model,
        },
        "control_state_history": _control_boundaries(mutations),
        "flight_recorder": recorder,
        "eligible_laps": eligible_laps,
        "excluded_laps": tuple(
            item.lap_number for item in recorder if item.state != "qualified"
        ),
        "exclusion_reasons": {
            item.lap_number: item.reasons for item in recorder if item.state != "qualified"
        },
        "steering_truth_audit_id": truth_audit.audit_id,
        "steering_truth_audit_hash": truth_audit.audit_hash,
        "channel_health": "pass" if truth_audit.state == "ready" else "fail",
        "sub_tick_coverage_fraction": truth_audit.sub_tick_coverage_fraction,
        "sample_clock_integrity": truth_audit.sample_clock_integrity,
        "independence_identity": f"source-session:{source_hash}",
        "duplicate_source": duplicate_source,
        "negative_control_expectation_id": (
            negative_control_expectation.expectation_id
            if negative_control_expectation is not None
            else None
        ),
        "subgroup_memberships": _subgroups(overview, assessment.accepted_lap_numbers),
        "qualification_state": state,
        "blocker_reasons": tuple(blockers),
        "dataset_admissions": admissions,
        "inventory_retained": True,
        "p19_authority_unchanged": True,
        "p20_authority_unchanged": True,
        "p23_authority": "shadow_only",
    }
    return _content_addressed(CampaignQualificationCertificate, "p24c", payload)


def save_steering_truth_audit(
    audit: SteeringSignalTruthAudit, *, db_path: str | Path | None = None
) -> bool:
    return _save_immutable(
        table="p24_steering_truth_audits",
        id_column="audit_id",
        hash_column="audit_hash",
        json_column="audit_json",
        identity=audit.audit_id,
        digest=audit.audit_hash,
        model=audit,
        extra_columns=("run_id", "source_file_hash", "created_at", "state"),
        extra_values=(audit.run_id, audit.source_file_hash, audit.created_at.isoformat(), audit.state),
        db_path=db_path,
    )


def save_qualification_certificate(
    certificate: CampaignQualificationCertificate,
    *,
    db_path: str | Path | None = None,
) -> bool:
    save_first_activation_protocol(_P23_PROTOCOL, db_path=db_path)
    connection = initialize_database(db_path)
    try:
        with connection:
            truth = connection.execute(
                "SELECT audit_hash FROM p24_steering_truth_audits WHERE audit_id = ?",
                (certificate.steering_truth_audit_id,),
            ).fetchone()
            if truth is None or truth[0] != certificate.steering_truth_audit_hash:
                raise ValueError("certificate does not reference its immutable steering truth audit")
            operation = connection.execute(
                "SELECT operation_hash FROM evidence_campaign_operations WHERE operation_id = ?",
                (certificate.operation_id,),
            ).fetchone()
            if operation is None or operation[0] != certificate.operation_hash:
                raise ValueError("certificate does not reference its frozen campaign operation")
            existing = connection.execute(
                "SELECT certificate_hash, certificate_json FROM p24_qualification_certificates "
                "WHERE certificate_id = ? OR (operation_id = ? AND run_id = ?)",
                (certificate.certificate_id, certificate.operation_id, certificate.run_id),
            ).fetchone()
            if existing is not None:
                if existing[0] != certificate.certificate_hash or (
                    CampaignQualificationCertificate.model_validate_json(existing[1])
                    != certificate
                ):
                    raise ValueError("one operation/run pair has one immutable certificate")
                return False
            connection.execute(
                "INSERT INTO p24_qualification_certificates "
                "(certificate_id, certificate_hash, protocol_id, campaign_id, operation_id, "
                "run_id, source_file_hash, created_at, qualification_state, certificate_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    certificate.certificate_id,
                    certificate.certificate_hash,
                    certificate.protocol_id,
                    certificate.campaign_id,
                    certificate.operation_id,
                    certificate.run_id,
                    certificate.source_file_hash,
                    certificate.created_at.isoformat(),
                    certificate.qualification_state,
                    certificate.model_dump_json(),
                ),
            )
        return True
    finally:
        connection.close()


def _save_immutable(
    *,
    table: str,
    id_column: str,
    hash_column: str,
    json_column: str,
    identity: str,
    digest: str,
    model: EvidenceLabModel,
    extra_columns: tuple[str, ...],
    extra_values: tuple[Any, ...],
    db_path: str | Path | None,
) -> bool:
    allowed = {
        "p24_steering_truth_audits",
        "p24_negative_control_expectations",
        "p24_negative_control_results",
        "p24_certificate_admissions",
        "p25_null_session_run_cards",
    }
    if table not in allowed:
        raise ValueError("unsupported immutable acquisition table")
    connection = initialize_database(db_path)
    try:
        with connection:
            existing = connection.execute(
                f"SELECT {hash_column}, {json_column} FROM {table} WHERE {id_column} = ?",
                (identity,),
            ).fetchone()
            if existing is not None:
                if existing[0] != digest or existing[1] != model.model_dump_json():
                    raise ValueError("immutable acquisition identity collision")
                return False
            columns = (id_column, hash_column, *extra_columns, json_column)
            placeholders = ", ".join("?" for _ in columns)
            connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                (identity, digest, *extra_values, model.model_dump_json()),
            )
        return True
    finally:
        connection.close()


def save_negative_control_expectation(
    expectation: NegativeControlExpectation,
    *,
    db_path: str | Path | None = None,
) -> bool:
    connection = initialize_database(db_path)
    try:
        operation = connection.execute(
            "SELECT operation_hash FROM evidence_campaign_operations WHERE operation_id = ?",
            (expectation.operation_id,),
        ).fetchone()
    finally:
        connection.close()
    if operation is None or operation[0] != expectation.operation_hash:
        raise ValueError("negative-control expectation lacks its frozen operation")
    return _save_immutable(
        table="p24_negative_control_expectations",
        id_column="expectation_id",
        hash_column="expectation_hash",
        json_column="expectation_json",
        identity=expectation.expectation_id,
        digest=expectation.expectation_hash,
        model=expectation,
        extra_columns=("operation_id", "created_at", "recipe_id"),
        extra_values=(
            expectation.operation_id,
            expectation.created_at.isoformat(),
            expectation.recipe_id,
        ),
        db_path=db_path,
    )


def list_qualification_certificates(
    *, db_path: str | Path | None = None, limit: int | None = None
) -> tuple[CampaignQualificationCertificate, ...]:
    if limit is not None and limit < 1:
        raise ValueError("certificate limit must be at least one")
    connection = initialize_database(db_path)
    try:
        if limit is None:
            rows = connection.execute(
                "SELECT certificate_json FROM p24_qualification_certificates "
                "ORDER BY created_at, rowid"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT certificate_json FROM ("
                "SELECT certificate_json, created_at, rowid AS persistence_order "
                "FROM p24_qualification_certificates "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?"
                ") ORDER BY created_at, persistence_order",
                (limit,),
            ).fetchall()
    finally:
        connection.close()
    return tuple(
        CampaignQualificationCertificate.model_validate_json(row[0]) for row in rows
    )


def get_qualification_certificate(
    certificate_id: str,
    *,
    db_path: str | Path | None = None,
) -> CampaignQualificationCertificate | None:
    """Read one immutable certificate without scanning campaign history."""

    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT certificate_json FROM p24_qualification_certificates "
            "WHERE certificate_id = ?",
            (certificate_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return CampaignQualificationCertificate.model_validate_json(row[0])


def latest_null_session_run_card(
    *,
    db_path: str | Path | None = None,
    reference_run_id: str | None = None,
) -> P25NullSessionRunCard | None:
    connection = initialize_database(db_path)
    try:
        if reference_run_id is None:
            row = connection.execute(
                "SELECT card_json FROM p25_null_session_run_cards "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT card_json FROM p25_null_session_run_cards "
                "WHERE reference_run_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (reference_run_id,),
            ).fetchone()
    finally:
        connection.close()
    return None if row is None else P25NullSessionRunCard.model_validate_json(row[0])


def freeze_null_session_run_card(
    reference_run_id: str,
    *,
    db_path: str | Path | None = None,
    created_at: datetime | None = None,
) -> P25NullSessionRunCard:
    existing = latest_null_session_run_card(
        db_path=db_path,
        reference_run_id=reference_run_id,
    )
    if existing is not None:
        return existing
    certificates = [
        item
        for item in list_qualification_certificates(db_path=db_path)
        if item.run_id == reference_run_id
    ]
    if not certificates:
        raise ValueError("A source-owned pilot certificate is required before freezing the null run card.")
    certificate = certificates[-1]
    operation = start_campaign_operation(
        "no_change_null",
        reference_run_id,
        db_path=db_path,
        created_at=created_at,
    )
    rows = read_telemetry_rows(
        reference_run_id,
        columns=["player_tire_compound", "PlayerTireCompound"],
    )
    compounds = tuple(
        dict.fromkeys(
            str(value)
            for row in rows
            if (value := _row_value(row, ("player_tire_compound", "PlayerTireCompound")))
            is not None
        )
    )
    context = operation.context
    blockers: list[str] = []
    ownership = certificate.telemetry_ownership
    if ownership is None or ownership.state != "verified":
        blockers.append("The reference pilot does not have verified immutable telemetry ownership.")
    if certificate.channel_health != "pass" or certificate.ffb_fingerprint.state != "ready":
        blockers.append("The reference pilot steering/FFB truth is not ready.")
    if certificate.profile_identity is None:
        blockers.append("The reference vehicle/profile identity is unavailable.")
    if certificate.setup_identity is None:
        blockers.append("The reference setup identity is unavailable.")
    if context.fuel_band is None:
        blockers.append("The reference eligible-lap fuel band is unavailable.")
    if len(compounds) != 1:
        blockers.append("One exact reference tire compound could not be frozen.")
    if context.minimum_clean_laps_per_unit != 10:
        blockers.append("The frozen operation does not require exactly 10 clean laps.")
    fuel_min = context.fuel_band.minimum if context.fuel_band is not None else 0.0
    fuel_max = context.fuel_band.maximum if context.fuel_band is not None else 0.0
    payload = {
        "card_version": "p25-null-session-run-card-v1",
        "created_at": created_at or datetime.now(UTC),
        "protocol_id": _P23_PROTOCOL.protocol_id,
        "protocol_hash": _P23_PROTOCOL.protocol_hash,
        "operation_id": operation.operation_id,
        "operation_hash": operation.operation_hash,
        "reference_certificate_id": certificate.certificate_id,
        "reference_certificate_hash": certificate.certificate_hash,
        "reference_run_id": reference_run_id,
        "source_file_hash": certificate.source_file_hash,
        "car_identity": certificate.car_identity,
        "build_identity": certificate.build_identity,
        "profile_identity": certificate.profile_identity or "unavailable",
        "track_identity": certificate.track_identity,
        "setup_identity": certificate.setup_identity or "unavailable",
        "ffb_fingerprint_sha256": certificate.ffb_fingerprint.fingerprint_sha256,
        "steering_conversion_model": certificate.ffb_fingerprint.steering_conversion_model
        or "unavailable",
        "minimum_warmup_laps": 1,
        "minimum_eligible_laps": 10,
        "fuel_band_minimum": fuel_min,
        "fuel_band_maximum": fuel_max,
        "tire_compound": compounds[0] if len(compounds) == 1 else "unavailable",
        "tire_context_requirement": (
            "Use the same compound and a fresh, unchanged tire set; carcass/wear snapshots "
            "remain context-only until a pit-boundary update is observed."
        ),
        "control_state_requirements": (
            "same setup identity",
            "same complete FFB fingerprint",
            "same steering ratio/pinion representation",
            "no applied brake-bias change",
            "no pit-service or setup change inside the clean block",
        ),
        "telemetry_requirements": tuple(item[0] for item in _STEERING_CHANNELS),
        "null_expectation": (
            "No meaningful steering-workload intervention is intentionally introduced; "
            "qualification or rejection is decided only after import."
        ),
        "qualification_criteria": tuple(_P23_PROTOCOL.context_requirements),
        "state": "blocked" if blockers else "ready",
        "blocker_reasons": tuple(blockers),
        "observed_run_id": None,
        "observed_qualification_state": None,
        "authority": "pre_outcome_collection_contract_only",
    }
    card = _content_addressed(P25NullSessionRunCard, "p25n", payload)
    _save_immutable(
        table="p25_null_session_run_cards",
        id_column="card_id",
        hash_column="card_hash",
        json_column="card_json",
        identity=card.card_id,
        digest=card.card_hash,
        model=card,
        extra_columns=("reference_run_id", "operation_id", "created_at", "state"),
        extra_values=(
            card.reference_run_id,
            card.operation_id,
            card.created_at.isoformat(),
            card.state,
        ),
        db_path=db_path,
    )
    return card


def _build_dataset_from_certificate(
    certificate: CampaignQualificationCertificate,
    rule: DatasetAdmissionRule,
) -> EvidenceDataset:
    if certificate.qualification_state != "qualified" or rule not in certificate.dataset_admissions:
        raise ValueError("dataset builder must obey a qualified immutable certificate")
    artifact_id = f"certificate:{certificate.certificate_id}"
    unit_id = certificate.independence_identity
    return build_evidence_dataset(
        {
            "dataset_kind": rule.dataset_kind,
            "created_at": certificate.created_at,
            "manifest": {
                "schema_version": "p24-certificate-admission-v1",
                "source_run_ids": (certificate.run_id,),
                "source_session_ids": (certificate.session_id,),
                "car_identities": (certificate.car_identity,),
                "track_identities": (certificate.track_identity,),
                "iracing_build_identities": (certificate.build_identity,),
                "vehicle_profile_hashes": (
                    (certificate.profile_identity,) if certificate.profile_identity else ()
                ),
                "analysis_artifact_versions": (
                    certificate.certificate_version,
                    _P23_PROTOCOL.formula_version,
                ),
                "setup_identities": (
                    (certificate.setup_identity,) if certificate.setup_identity else ()
                ),
                "context_distribution": {
                    item: 1 for item in certificate.subgroup_memberships
                },
                "lap_count": len(certificate.eligible_laps),
                "independence_unit_count": 1,
                "ground_truth_type": rule.ground_truth_type,
                "allowed_evaluation_uses": (rule.allowed_use,),
                "forbidden_uses": (
                    "setup_authority",
                    "cause_probability",
                    "cause_rank",
                    "keep_undo_policy",
                    "measurement_plan",
                ),
            },
            "artifacts": (
                {
                    "artifact_id": artifact_id,
                    "artifact_kind": "campaign_qualification_certificate",
                    "content_sha256": certificate.certificate_hash,
                    "source_file_fingerprint": certificate.source_file_hash,
                    "source_run_ids": (certificate.run_id,),
                    "artifact_version": certificate.certificate_version,
                },
            ),
            "units": (
                {
                    "unit_id": unit_id,
                    "independence_level": "session",
                    "source_artifact_ids": (artifact_id,),
                    "source_file_fingerprints": (certificate.source_file_hash,),
                    "source_run_ids": (certificate.run_id,),
                    "source_session_ids": (certificate.session_id,),
                    "lap_numbers": certificate.eligible_laps,
                    "setup_fingerprints": (
                        (certificate.setup_identity,) if certificate.setup_identity else ()
                    ),
                    "context_fingerprints": (
                        certificate.ffb_fingerprint.fingerprint_sha256,
                    ),
                    "track_ids": (certificate.track_identity,),
                    "build_ids": (certificate.build_identity,),
                    "synthetic": False,
                },
            ),
            "splits": (
                {
                    "split_id": f"split:{certificate.certificate_id}",
                    "partition": rule.partition,
                    "unit_ids": (unit_id,),
                },
            ),
            "qualification": {
                "state": "qualified",
                "qualified_real_world_units": 1,
                "qualified_synthetic_units": 0,
            },
        }
    )


def admit_qualification_certificate(
    certificate: CampaignQualificationCertificate,
    *,
    db_path: str | Path | None = None,
) -> tuple[CertificateAdmission, ...]:
    stored = get_qualification_certificate(
        certificate.certificate_id,
        db_path=db_path,
    )
    if stored != certificate:
        raise ValueError("only the stored immutable certificate may admit a dataset")
    if certificate.qualification_state != "qualified" or not certificate.dataset_admissions:
        raise ValueError("a rejected or admission-empty certificate cannot admit evidence")
    admissions = []
    for rule in certificate.dataset_admissions:
        dataset = _build_dataset_from_certificate(certificate, rule)
        register_evidence_dataset(dataset, db_path=db_path)
        payload = {
            "certificate_id": certificate.certificate_id,
            "certificate_hash": certificate.certificate_hash,
            "admission_key": rule.admission_key,
            "dataset_id": dataset.dataset_id,
            "dataset_hash": dataset.dataset_hash,
            "admitted_at": certificate.created_at,
        }
        admission = _content_addressed(CertificateAdmission, "p24a", payload)
        _save_immutable(
            table="p24_certificate_admissions",
            id_column="admission_id",
            hash_column="admission_hash",
            json_column="admission_json",
            identity=admission.admission_id,
            digest=admission.admission_hash,
            model=admission,
            extra_columns=("certificate_id", "dataset_id", "admitted_at"),
            extra_values=(
                admission.certificate_id,
                admission.dataset_id,
                admission.admitted_at.isoformat(),
            ),
            db_path=db_path,
        )
        admissions.append(admission)
    if certificate.collection_kind in {"historical_exact_ffb", "same_setup_null"}:
        campaign_kind = (
            "control_workload"
            if certificate.collection_kind == "historical_exact_ffb"
            else "no_change_null"
        )
        campaign = next(
            item for item in initial_campaigns() if item.campaign_kind == campaign_kind
        )
        save_campaign(campaign, db_path=db_path)
        attempt = build_campaign_attempt(
            campaign,
            {
                "recorded_at": certificate.created_at,
                "outcome": "usable",
                "independence_unit_id": certificate.independence_identity,
                "independence_level": campaign.required_independence_level,
                "source_run_ids": (certificate.run_id,),
                "source_session_ids": (certificate.session_id,),
                "source_file_fingerprints": (certificate.source_file_hash,),
                "eligible_lap_count": len(certificate.eligible_laps),
                "context_keys": campaign.required_context,
                "available_telemetry": campaign.required_telemetry,
                "setup_snapshot_present": certificate.setup_identity is not None,
                "dataset_id": admissions[0].dataset_id if admissions else None,
            },
        )
        append_campaign_attempt(attempt, db_path=db_path)
    return tuple(admissions)


def _latest_pending_expectation(
    operation_id: str, *, db_path: str | Path | None
) -> NegativeControlExpectation | None:
    connection = initialize_database(db_path)
    try:
        row = connection.execute(
            "SELECT expectation_json FROM p24_negative_control_expectations AS expectation "
            "WHERE expectation.operation_id = ? AND NOT EXISTS ("
            "SELECT 1 FROM p24_negative_control_results AS result "
            "WHERE result.expectation_id = expectation.expectation_id) "
            "ORDER BY expectation.created_at, expectation.expectation_id LIMIT 1",
            (operation_id,),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else NegativeControlExpectation.model_validate_json(row[0])


def qualify_p23_operations_for_run(
    run_id: str,
    *,
    assessments: Sequence[CampaignRunAssessment],
    db_path: str | Path | None = None,
    created_at: datetime | None = None,
) -> tuple[CampaignQualificationCertificate, ...]:
    overview = RaceLabRepository(db_path).get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    manifest = read_telemetry_manifest(run_id)
    rows = read_telemetry_rows(run_id, columns=list(_STEERING_READ_COLUMNS))
    source_hash = _source_hash(manifest, overview.session.file_hash)
    truth = build_steering_signal_truth_audit(
        run_id=run_id,
        manifest=manifest,
        rows=rows,
        steering_conversion_model=_steering_conversion(overview),
        source_file_hash=source_hash,
        created_at=created_at,
    )
    save_steering_truth_audit(truth, db_path=db_path)
    mutations = detect_control_mutations(rows, run_id=run_id)
    operations = {item.operation_id: item for item in list_campaign_operations(db_path=db_path)}
    results = []
    for assessment in assessments:
        operation = operations.get(assessment.operation_id)
        if operation is None or operation_state(operation.operation_id, db_path=db_path) != "active":
            continue
        if operation.campaign_kind not in {"control_workload", "no_change_null"}:
            continue
        if (
            operation.campaign_kind == "no_change_null"
            and source_hash == operation.context.source_file_fingerprint
        ):
            # The frozen pilot is the comparison anchor, never the future null
            # observation. Re-importing it must not manufacture an attempt.
            continue
        connection = initialize_database(db_path)
        try:
            existing = connection.execute(
                "SELECT certificate_json FROM p24_qualification_certificates "
                "WHERE operation_id = ? AND run_id = ?",
                (operation.operation_id, run_id),
            ).fetchone()
        finally:
            connection.close()
        if existing is not None:
            results.append(CampaignQualificationCertificate.model_validate_json(existing[0]))
            continue
        expectation = _latest_pending_expectation(operation.operation_id, db_path=db_path)
        kind: P23CollectionKind = (
            "negative_control"
            if expectation is not None
            else "historical_exact_ffb"
            if operation.campaign_kind == "control_workload"
            else "same_setup_null"
        )
        certificate = build_qualification_certificate(
            collection_kind=kind,
            operation=operation,
            assessment=assessment,
            overview=overview,
            manifest=manifest,
            truth_audit=truth,
            mutations=mutations,
            duplicate_source=_duplicate_source(
                source_hash,
                operation_id=operation.operation_id,
                run_id=run_id,
                db_path=db_path,
            ),
            negative_control_expectation=expectation,
            created_at=created_at,
        )
        save_qualification_certificate(certificate, db_path=db_path)
        if certificate.qualification_state == "qualified":
            admit_qualification_certificate(certificate, db_path=db_path)
        if expectation is not None:
            observed_reasons = tuple(
                reason
                for reason in assessment.rejection_reasons
                if "requires a controlled workflow or external validation record"
                not in reason
            )
            observed_blockers = _scientific_blocker_keys(observed_reasons)
            observed_outcome: ExpectedControlOutcome = (
                "comparison_rejected" if observed_reasons else "comparison_allowed"
            )
            passed = observed_outcome == expectation.expected_outcome and (
                observed_outcome == "comparison_allowed"
                or set(expectation.expected_blocker_keys) <= set(observed_blockers)
            )
            result_payload = {
                "expectation_id": expectation.expectation_id,
                "expectation_hash": expectation.expectation_hash,
                "certificate_id": certificate.certificate_id,
                "certificate_hash": certificate.certificate_hash,
                "observed_at": created_at or datetime.now(UTC),
                "observed_outcome": observed_outcome,
                "observed_blocker_keys": observed_blockers,
                "passed": passed,
                "authority": "negative_control_evidence_only",
            }
            result = _content_addressed(NegativeControlResult, "p24r", result_payload)
            _save_immutable(
                table="p24_negative_control_results",
                id_column="result_id",
                hash_column="result_hash",
                json_column="result_json",
                identity=result.result_id,
                digest=result.result_hash,
                model=result,
                extra_columns=("expectation_id", "certificate_id", "observed_at", "passed"),
                extra_values=(
                    result.expectation_id,
                    result.certificate_id,
                    result.observed_at.isoformat(),
                    int(result.passed),
                ),
                db_path=db_path,
            )
        results.append(certificate)
    return tuple(results)


def p23_acquisition_progress(
    *, db_path: str | Path | None = None
) -> P23AcquisitionProgress:
    certificates = list_qualification_certificates(db_path=db_path)
    source_attempts: dict[str, CampaignQualificationCertificate] = {}
    for certificate in certificates:
        existing = source_attempts.get(certificate.source_file_hash)
        if existing is None or (
            existing.qualification_state != "qualified"
            and certificate.qualification_state == "qualified"
        ):
            # A current-version re-import may repair absent ownership, but one
            # source still projects as one attempt and one collection kind.
            source_attempts[certificate.source_file_hash] = certificate
    qualified = [
        item for item in source_attempts.values() if item.qualification_state == "qualified"
    ]
    unique: dict[str, CampaignQualificationCertificate] = {}
    for certificate in qualified:
        unique.setdefault(certificate.source_file_hash, certificate)
    historical = sum(item.collection_kind == "historical_exact_ffb" for item in unique.values())
    null = sum(item.collection_kind == "same_setup_null" for item in unique.values())
    prospective = sum(item.collection_kind == "prospective" for item in unique.values())
    subgroups = tuple(
        sorted(
            {
                subgroup
                for item in unique.values()
                for subgroup in item.subgroup_memberships
                if subgroup in _REQUIRED_SUBGROUPS
            }
        )
    )
    connection = initialize_database(db_path)
    try:
        controls = int(
            connection.execute(
                "SELECT COUNT(DISTINCT json_extract(expectation.expectation_json, '$.protocol_control_id')) "
                "FROM p24_negative_control_results AS result "
                "JOIN p24_negative_control_expectations AS expectation "
                "ON expectation.expectation_id = result.expectation_id WHERE result.passed = 1"
            ).fetchone()[0]
        )
        profile_ready = connection.execute(
            "SELECT 1 FROM p24_steering_truth_audits WHERE state = 'ready' LIMIT 1"
        ).fetchone() is not None
        historical_passed = connection.execute(
            "SELECT 1 FROM p23_activation_audits "
            "WHERE json_extract(audit_json, '$.historical.state') = 'passed' LIMIT 1"
        ).fetchone() is not None
    finally:
        connection.close()
    if not profile_ready:
        next_kind: P23CollectionPriority = "profile_validation"
        next_best = "Validate steering signal units, sub-tick timing, scalar relationship, and steering ratio/pinion identity."
    elif historical < 9:
        next_kind = "historical_exact_ffb"
        next_best = f"Record historical exact-FFB source session {historical + 1} of 9 with at least 10 clean laps."
    elif null < 10:
        next_kind = "same_setup_null"
        next_best = f"Record same-setup null stint {null + 1} of 10 under the frozen FFB fingerprint."
    elif controls < 8:
        next_kind = "negative_control"
        next_best = "Freeze and run the next unmet negative-control expectation before importing its outcome."
    elif len(subgroups) < 9:
        next_kind = "subgroup_coverage"
        next_best = "Collect the highest-priority missing P23 subgroup under the exact frozen context."
    else:
        next_kind = "historical_gate_review"
        next_best = "Grade the frozen historical gate before any prospective session is accepted."
    attempt_values = tuple(source_attempts.values())
    latest_certificate = attempt_values[-1] if attempt_values else None
    latest_recorder = latest_certificate.flight_recorder if latest_certificate else ()
    recorder_preview = latest_recorder[:12]
    return P23AcquisitionProgress(
        total_attempts=len(source_attempts),
        qualified_attempts=len(qualified),
        historical_sessions=historical,
        null_stints=null,
        negative_controls=min(controls, 8),
        covered_subgroups=len(subgroups),
        subgroup_memberships=subgroups,
        profile_status="complete" if profile_ready else "incomplete",
        prospective_sessions=prospective,
        prospective_status=(
            "collecting"
            if historical_passed and prospective
            else "available"
            if historical_passed
            else "locked_until_historical_gate"
        ),
        rejected_attempts=sum(
            item.qualification_state != "qualified" for item in source_attempts.values()
        ),
        next_best_collection_kind=next_kind,
        next_best_collection=next_best,
        latest_certificate_id=latest_certificate.certificate_id if latest_certificate else None,
        latest_run_id=latest_certificate.run_id if latest_certificate else None,
        latest_qualification_state=(
            latest_certificate.qualification_state if latest_certificate else None
        ),
        latest_eligible_laps=(len(latest_certificate.eligible_laps) if latest_certificate else 0),
        latest_excluded_laps=(len(latest_certificate.excluded_laps) if latest_certificate else 0),
        latest_blocker=(
            latest_certificate.blocker_reasons[0]
            if latest_certificate and latest_certificate.blocker_reasons
            else None
        ),
        latest_blockers=(latest_certificate.blocker_reasons if latest_certificate else ()),
        latest_signal_truth_state=(
            "ready"
            if latest_certificate and latest_certificate.channel_health == "pass"
            else "scientific_debt"
            if latest_certificate
            else None
        ),
        latest_ffb_fingerprint_state=(
            latest_certificate.ffb_fingerprint.state if latest_certificate else None
        ),
        latest_ffb_fingerprint_sha256=(
            latest_certificate.ffb_fingerprint.fingerprint_sha256
            if latest_certificate
            else None
        ),
        latest_dataset_admissions=(
            tuple(item.admission_key for item in latest_certificate.dataset_admissions)
            if latest_certificate
            else ()
        ),
        latest_telemetry_ownership_state=(
            latest_certificate.telemetry_ownership.state
            if latest_certificate and latest_certificate.telemetry_ownership
            else None
        ),
        latest_null_run_card=latest_null_session_run_card(db_path=db_path),
        latest_flight_recorder=recorder_preview,
        latest_flight_recorder_total=len(latest_recorder),
        latest_flight_recorder_truncated=len(latest_recorder) > len(recorder_preview),
    )


def build_pre_run_checklist(
    run_id: str,
    *,
    collection_kind: P23CollectionKind = "historical_exact_ffb",
    db_path: str | Path | None = None,
) -> P23PreRunChecklist:
    overview = RaceLabRepository(db_path).get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    manifest = read_telemetry_manifest(run_id)
    archive_blocker = None
    try:
        rows = read_telemetry_rows(run_id, columns=list(_STEERING_READ_COLUMNS))
    except (OSError, RuntimeError, ValueError) as exc:
        rows = []
        archive_blocker = str(exc)
    truth = build_steering_signal_truth_audit(
        run_id=run_id,
        manifest=manifest,
        rows=rows,
        steering_conversion_model=_steering_conversion(overview),
        source_file_hash=overview.session.file_hash,
    )
    identity = manifest.get("compatibility_identity") or {}
    setup = _setup_identity(overview)
    progress = p23_acquisition_progress(db_path=db_path)
    requirements = (
        PreRunRequirement(
            key="car_build",
            label="Next Gen car and exact iRacing build",
            state="pass" if identity.get("car_path") and identity.get("iracing_build_version") else "block",
            observed=f"{identity.get('car_path') or 'unknown'} / {identity.get('iracing_build_version') or 'unknown'}",
        ),
        PreRunRequirement(
            key="ffb_fingerprint",
            label="Complete exact FFB fingerprint",
            state="pass" if truth.ffb_fingerprint.state == "ready" else "block",
            observed=truth.ffb_fingerprint.state,
        ),
        PreRunRequirement(
            key="steering_conversion",
            label="Steering ratio or pinion identity",
            state="pass" if truth.steering_conversion_model else "block",
            observed=truth.steering_conversion_model or "unavailable",
        ),
        PreRunRequirement(
            key="setup_identity",
            label="Immutable setup identity",
            state="pass" if setup else "block",
            observed=setup[:12] if setup else "unavailable",
        ),
        PreRunRequirement(
            key="steering_signal_truth",
            label="Steering signal truth audit",
            state="pass" if truth.state == "ready" else "block",
            observed=truth.state,
        ),
        PreRunRequirement(
            key="immutable_telemetry_archive",
            label="Immutable telemetry archive available",
            state="pass" if archive_blocker is None else "block",
            observed="available" if archive_blocker is None else archive_blocker,
        ),
        PreRunRequirement(
            key="minimum_laps",
            label="Minimum clean laps in one source session",
            state="unknown",
            observed="10 required after import",
        ),
        PreRunRequirement(
            key="control_state",
            label="No material applied or requested control mutation",
            state="unknown",
            observed="verified after import",
        ),
    )
    blockers = tuple(
        f"{item.label}: {item.observed}" for item in requirements if item.state == "block"
    )
    if collection_kind == "prospective" and progress.prospective_status == "locked_until_historical_gate":
        blockers = (*blockers, "Prospective collection is locked until the historical gate passes.")
    return P23PreRunChecklist(
        protocol_id=_P23_PROTOCOL.protocol_id,
        protocol_hash=_P23_PROTOCOL.protocol_hash,
        collection_kind=collection_kind,
        run_id=run_id,
        requirements=requirements,
        target_clean_laps=10,
        campaign_progress=progress,
        ready_to_record=not blockers,
        blockers=blockers,
        live_telemetry_claimed=False,
        authority="collection_guidance_only",
    )


__all__ = [
    "CampaignQualificationCertificate",
    "CertificateAdmission",
    "ControlStateBoundary",
    "DatasetAdmissionRule",
    "FlightRecorderEntry",
    "NegativeControlExpectation",
    "NegativeControlRecipe",
    "NegativeControlResult",
    "P23AcquisitionProgress",
    "P23CollectionKind",
    "P23CollectionPriority",
    "P23CollectionTemplate",
    "P23PreRunChecklist",
    "PreRunRequirement",
    "SignalTruth",
    "SteeringSignalTruthAudit",
    "admit_qualification_certificate",
    "build_pre_run_checklist",
    "build_qualification_certificate",
    "build_steering_signal_truth_audit",
    "freeze_negative_control_expectation",
    "get_qualification_certificate",
    "list_qualification_certificates",
    "negative_control_recipe_catalog",
    "negative_control_recipes",
    "p23_acquisition_progress",
    "p23_collection_templates",
    "qualify_p23_operations_for_run",
    "save_negative_control_expectation",
    "save_qualification_certificate",
    "save_steering_truth_audit",
]
