"""Evidence-only contracts for same-setup telemetry observations.

These models deliberately cannot carry setup values, setup targets, calibrated
probabilities, or action authority.  They describe what repeated at a physical
track position and what should be measured or practiced next.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.dynamic_response import DynamicResponseReport
from racelab_engine.analysis.stint_response_migration import StintResponseMigrationReport
from racelab_engine.models.evidence import EvidenceState


_OBSERVATION_EVIDENCE_STATES = frozenset({
    EvidenceState.MEASURED,
    EvidenceState.CALCULATED,
    EvidenceState.ESTIMATED_PROXY,
    EvidenceState.OBSERVED_CORRELATION,
    EvidenceState.CONTROLLED_TEST_EFFECT,
})


class ObservationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ObservationStatus(str, Enum):
    READY = "ready"
    NO_FINDING = "no_finding"
    BLOCKED = "blocked"


class MechanismKind(str, Enum):
    DRIVER_EXECUTION = "driver_execution"
    BRAKING_RESPONSE = "braking_response"
    CORNER_ROTATION = "corner_rotation"
    TIRE_STATE = "tire_state"
    DAMPER_RESPONSE = "damper_response"
    PLATFORM_RESPONSE = "platform_response"
    RESISTANCE_SCRUB_LIKE = "resistance_scrub_like"
    POWERTRAIN_RESPONSE = "powertrain_response"
    STINT_TREND = "stint_trend"
    SIM_INTEGRITY = "sim_integrity"
    UNCLASSIFIED = "unclassified"


class PhysicalSegment(ObservationModel):
    """One contiguous non-wrapping part of an exact circular track scope."""

    start_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    end_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    sample_count: int = Field(ge=1)

    @model_validator(mode="after")
    def segment_is_ordered(self) -> PhysicalSegment:
        if self.end_pct < self.start_pct:
            raise ValueError("physical segments must be non-wrapping and ordered")
        return self


class ObservationCitation(ObservationModel):
    run_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    setup_id: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    phase: str = Field(min_length=1)
    evidence_state: EvidenceState
    source_channels: tuple[str, ...] = Field(min_length=1)
    event_id: str | None = None
    telemetry_sample_count: int = Field(ge=1)
    physical_segments: tuple[PhysicalSegment, ...] = ()

    @model_validator(mode="after")
    def citation_is_exact_and_usable(self) -> ObservationCitation:
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("citation peak must be inside its physical window")
        if (
            any(not channel for channel in self.source_channels)
            or len(self.source_channels) != len(set(self.source_channels))
        ):
            raise ValueError("citation source channels must be non-empty and unique")
        if self.evidence_state not in _OBSERVATION_EVIDENCE_STATES:
            raise ValueError("observation citations require usable evidence")
        if not self.physical_segments:
            object.__setattr__(self, "physical_segments", (
                PhysicalSegment(
                    start_pct=self.lap_pct_start,
                    end_pct=self.lap_pct_end,
                    sample_count=self.telemetry_sample_count,
                ),
            ))
        if sum(segment.sample_count for segment in self.physical_segments) != self.telemetry_sample_count:
            raise ValueError("physical-segment sample counts must equal citation coverage")
        if not any(
            segment.start_pct <= self.lap_pct_peak <= segment.end_pct
            for segment in self.physical_segments
        ):
            raise ValueError("citation peak must lie inside one cited physical segment")
        return self


class ProducerArtifactScope(ObservationModel):
    """Exact server-verified scope for one stage of a producer artifact."""

    stage: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    telemetry_sample_count: int = Field(ge=1)
    sample_coverage: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    eligible: Literal[True] = True

    @model_validator(mode="after")
    def producer_scope_is_exact(self) -> ProducerArtifactScope:
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("producer artifact peak must be inside its physical window")
        return self


class OpportunitySignature(ObservationModel):
    signature_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    evidence_state: Literal[EvidenceState.OBSERVED_CORRELATION] = (
        EvidenceState.OBSERVED_CORRELATION
    )
    authority: Literal["observation_only"] = "observation_only"
    observational_label: Literal["repeatable_same_setup_opportunity"] = (
        "repeatable_same_setup_opportunity"
    )
    eligible_lap_count: int = Field(ge=3)
    repetition_count: int = Field(ge=2)
    telemetry_sample_count: int = Field(ge=1)
    aligned_bin_count: int = Field(ge=2)
    median_opportunity_s: float = Field(gt=0.0, allow_inf_nan=False)
    empirical_noise_s: float = Field(ge=0.0, allow_inf_nan=False)
    source_channels: tuple[str, ...] = Field(min_length=2)
    citations: tuple[ObservationCitation, ...] = Field(min_length=2)
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def signature_provenance_is_same_scope(self) -> OpportunitySignature:
        if self.blocker_reasons:
            raise ValueError("ready opportunity signatures cannot carry blockers")
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("opportunity peak must be inside its physical window")
        if self.repetition_count != len(self.citations):
            raise ValueError("opportunity repetition count must equal cited laps")
        if self.median_opportunity_s <= self.empirical_noise_s:
            raise ValueError(
                "opportunity signatures must clear their empirical same-run noise floor"
            )
        lap_numbers = [citation.lap_number for citation in self.citations]
        if len(lap_numbers) != len(set(lap_numbers)):
            raise ValueError("opportunity citations must use distinct laps")
        for citation in self.citations:
            if (
                citation.run_id != self.run_id
                or citation.setup_id != self.setup_id
                or citation.phase != self.phase
                or citation.lap_pct_start != self.lap_pct_start
                or citation.lap_pct_end != self.lap_pct_end
                or citation.lap_pct_peak != self.lap_pct_peak
            ):
                raise ValueError("opportunity citations must match the exact signature scope")
        return self


class OpportunitySignatureReport(ObservationModel):
    status: ObservationStatus
    run_id: str = Field(min_length=1)
    setup_id: str | None
    evidence_state: EvidenceState
    authority: Literal["observation_only"] = "observation_only"
    observational_label: Literal["same_setup_physical_position_scan"] = (
        "same_setup_physical_position_scan"
    )
    required_channels: tuple[str, ...] = ("lap_dist_pct_100", "session_time")
    source_channels: tuple[str, ...] = ()
    eligible_lap_numbers: tuple[int, ...] = ()
    eligible_lap_count: int = Field(ge=0)
    telemetry_sample_count: int = Field(ge=0)
    signatures: tuple[OpportunitySignature, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def report_status_matches_findings(self) -> OpportunitySignatureReport:
        if self.eligible_lap_count != len(self.eligible_lap_numbers):
            raise ValueError("eligible lap count must match exact lap identities")
        if self.status is ObservationStatus.BLOCKED:
            if not self.blocker_reasons or self.signatures:
                raise ValueError("blocked opportunity reports require blockers and no findings")
            if self.evidence_state is not EvidenceState.BLOCKED_BY_CONTEXT:
                raise ValueError("blocked opportunity reports require blocked evidence")
        else:
            if self.blocker_reasons:
                raise ValueError("unblocked opportunity reports cannot carry blockers")
            if self.setup_id is None:
                raise ValueError("same-setup opportunity reports require setup identity")
            if self.status is ObservationStatus.READY and not self.signatures:
                raise ValueError("ready opportunity reports require signatures")
            if self.status is ObservationStatus.NO_FINDING and self.signatures:
                raise ValueError("no-finding opportunity reports cannot carry signatures")
        return self


class MechanismObservation(ObservationModel):
    observation_id: str = Field(min_length=1)
    producer_id: str = Field(min_length=1)
    artifact_id: str = Field(min_length=1)
    source_run_ids: tuple[str, ...] = Field(min_length=1)
    source_setup_ids: tuple[str, ...]
    sample_coverage: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    mechanism: MechanismKind
    mechanism_kinds: tuple[MechanismKind, ...] = ()
    run_id: str = Field(min_length=1)
    setup_id: str | None
    lap_number: int | None = Field(default=None, ge=0)
    phase: str | None = None
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
    summary: str = Field(min_length=1)
    evidence_state: EvidenceState
    authority: Literal["observation_only"] = "observation_only"
    observational_label: Literal["typed_mechanism_observation"] = (
        "typed_mechanism_observation"
    )
    qualified: bool = False
    source_channels: tuple[str, ...] = ()
    required_channels: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    contradicting_evidence: tuple[str, ...] = ()
    telemetry_sample_count: int = Field(ge=0)
    repetition_count: int = Field(ge=0)
    citations: tuple[ObservationCitation, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def qualified_observations_are_fully_cited(self) -> MechanismObservation:
        if not self.mechanism_kinds:
            object.__setattr__(self, "mechanism_kinds", (self.mechanism,))
        if (
            self.mechanism not in self.mechanism_kinds
            or len(self.mechanism_kinds) != len(set(self.mechanism_kinds))
        ):
            raise ValueError(
                "mechanism observation identities must be unique and include the primary mechanism"
            )
        for values, label in ((self.source_run_ids, "source run"),):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError(f"{label} identities must be non-empty and unique")
        if any(not value for value in self.source_setup_ids) or len(
            self.source_setup_ids
        ) != len(set(self.source_setup_ids)):
            raise ValueError("source setup identities must be non-empty and unique")
        if self.run_id not in self.source_run_ids:
            raise ValueError("the observation run must be one of its producer artifact runs")
        if self.setup_id is not None and self.setup_id not in self.source_setup_ids:
            raise ValueError("the observation setup must be one of its producer artifact setups")
        scope = (self.lap_pct_start, self.lap_pct_end, self.lap_pct_peak)
        if self.qualified:
            if (
                self.blocker_reasons
                or self.evidence_state not in _OBSERVATION_EVIDENCE_STATES
                or self.setup_id is None
                or self.lap_number is None
                or self.phase is None
                or any(value is None for value in scope)
                or not self.source_channels
                or not self.supporting_evidence
                or not self.citations
                or self.telemetry_sample_count < 1
                or self.repetition_count < 1
            ):
                raise ValueError("qualified mechanism observations require complete evidence")
            assert self.lap_pct_start is not None
            assert self.lap_pct_end is not None
            assert self.lap_pct_peak is not None
            if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
                raise ValueError("mechanism peak must be inside its physical window")
            for citation in self.citations:
                if (
                    citation.run_id not in self.source_run_ids
                    or citation.setup_id not in self.source_setup_ids
                ):
                    raise ValueError(
                        "mechanism citations must belong to declared producer artifact scope"
                    )
            citation_run_ids = {citation.run_id for citation in self.citations}
            if citation_run_ids != set(self.source_run_ids):
                raise ValueError("mechanism citations must cover every producer artifact run")
            citation_laps = {
                citation.lap_number
                for citation in self.citations
                if citation.run_id == self.run_id
            }
            if self.lap_number not in citation_laps:
                raise ValueError("mechanism citations must include the reported run and lap")
            citation_scopes = {
                (citation.run_id, citation.lap_number) for citation in self.citations
            }
            if self.repetition_count != len(citation_scopes):
                raise ValueError(
                    "mechanism repetition count must equal distinct cited run/lap scopes"
                )
        elif not self.blocker_reasons or self.citations:
            raise ValueError("blocked mechanism observations require blockers and no citations")
        return self


class MechanismObservationReport(ObservationModel):
    status: ObservationStatus
    run_id: str = Field(min_length=1)
    setup_id: str | None
    authority: Literal["observation_only"] = "observation_only"
    observations: tuple[MechanismObservation, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def mechanism_report_is_fail_closed(self) -> MechanismObservationReport:
        qualified = tuple(item for item in self.observations if item.qualified)
        if self.status is ObservationStatus.READY and not qualified:
            raise ValueError("ready mechanism reports require qualified observations")
        if self.status is ObservationStatus.NO_FINDING and qualified:
            raise ValueError("no-finding mechanism reports cannot carry qualified observations")
        if self.status is ObservationStatus.BLOCKED and not self.blocker_reasons:
            raise ValueError("blocked mechanism reports require blockers")
        return self


class SameSetupAnomaly(ObservationModel):
    anomaly_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    channel: str = Field(min_length=1)
    direction: Literal["above_envelope", "below_envelope"]
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    evidence_state: Literal[EvidenceState.OBSERVED_CORRELATION] = (
        EvidenceState.OBSERVED_CORRELATION
    )
    authority: Literal["observation_only"] = "observation_only"
    observational_label: Literal["sustained_same_setup_anomaly"] = (
        "sustained_same_setup_anomaly"
    )
    reference_lap_numbers: tuple[int, ...] = Field(min_length=2)
    repetition_count: int = Field(ge=2)
    telemetry_sample_count: int = Field(ge=1)
    aligned_bin_count: int = Field(ge=2)
    median_observed_value: float = Field(allow_inf_nan=False)
    median_reference_value: float = Field(allow_inf_nan=False)
    median_absolute_deviation: float = Field(ge=0.0, allow_inf_nan=False)
    source_channels: tuple[str, ...] = Field(min_length=2)
    citations: tuple[ObservationCitation, ...] = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def anomaly_has_exact_leave_one_out_scope(self) -> SameSetupAnomaly:
        if self.blocker_reasons:
            raise ValueError("ready anomaly findings cannot carry blockers")
        if self.repetition_count != len(self.reference_lap_numbers):
            raise ValueError("anomaly repetition count is the reference-lap count")
        if self.lap_number in self.reference_lap_numbers:
            raise ValueError("anomalous lap cannot be part of its reference envelope")
        if len(set(self.reference_lap_numbers)) != len(self.reference_lap_numbers):
            raise ValueError("reference lap identities must be unique")
        if not self.lap_pct_start <= self.lap_pct_peak <= self.lap_pct_end:
            raise ValueError("anomaly peak must be inside its physical window")
        if len(self.citations) != 1:
            raise ValueError("one anomaly identifies exactly one anomalous lap")
        citation = self.citations[0]
        if (
            citation.run_id != self.run_id
            or citation.setup_id != self.setup_id
            or citation.lap_number != self.lap_number
            or citation.lap_pct_start != self.lap_pct_start
            or citation.lap_pct_end != self.lap_pct_end
            or citation.lap_pct_peak != self.lap_pct_peak
        ):
            raise ValueError("anomaly citation must match the exact anomaly scope")
        return self


class SameSetupAnomalyReport(ObservationModel):
    status: ObservationStatus
    run_id: str = Field(min_length=1)
    setup_id: str | None
    evidence_state: EvidenceState
    authority: Literal["observation_only"] = "observation_only"
    observational_label: Literal["same_setup_robust_anomaly_scan"] = (
        "same_setup_robust_anomaly_scan"
    )
    required_channels: tuple[str, ...]
    source_channels: tuple[str, ...] = ()
    eligible_lap_numbers: tuple[int, ...] = ()
    eligible_lap_count: int = Field(ge=0)
    reference_lap_count: int = Field(ge=0)
    telemetry_sample_count: int = Field(ge=0)
    anomalies: tuple[SameSetupAnomaly, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def anomaly_report_status_matches_findings(self) -> SameSetupAnomalyReport:
        if self.eligible_lap_count != len(self.eligible_lap_numbers):
            raise ValueError("eligible lap count must match exact lap identities")
        if self.status is ObservationStatus.BLOCKED:
            if not self.blocker_reasons or self.anomalies:
                raise ValueError("blocked anomaly reports require blockers and no findings")
            if self.evidence_state is not EvidenceState.BLOCKED_BY_CONTEXT:
                raise ValueError("blocked anomaly reports require blocked evidence")
        elif self.blocker_reasons:
            raise ValueError("unblocked anomaly reports cannot carry blockers")
        elif self.status is ObservationStatus.READY and not self.anomalies:
            raise ValueError("ready anomaly reports require findings")
        elif self.status is ObservationStatus.NO_FINDING and self.anomalies:
            raise ValueError("no-finding anomaly reports cannot carry findings")
        return self


class DriverChannelRepeatability(ObservationModel):
    channel: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    median_robust_spread: float = Field(ge=0.0, allow_inf_nan=False)
    p90_robust_spread: float = Field(ge=0.0, allow_inf_nan=False)
    aligned_bin_count: int = Field(ge=1)


class DriverCoachingFocus(ObservationModel):
    phase: str = Field(min_length=1)
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    channel: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    success_check: str = Field(min_length=1)
    setup_authorized: Literal[False] = False
    citations: tuple[ObservationCitation, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def focus_uses_distinct_laps(self) -> DriverCoachingFocus:
        lap_numbers = [citation.lap_number for citation in self.citations]
        if len(lap_numbers) != len(set(lap_numbers)):
            raise ValueError("driver coaching citations must use distinct laps")
        return self


class DriverRepeatabilitySignature(ObservationModel):
    status: ObservationStatus
    run_id: str = Field(min_length=1)
    setup_id: str | None
    evidence_state: EvidenceState
    authority: Literal["driver_coaching_only"] = "driver_coaching_only"
    observational_label: Literal["same_setup_driver_repeatability"] = (
        "same_setup_driver_repeatability"
    )
    eligible_lap_numbers: tuple[int, ...] = ()
    eligible_lap_count: int = Field(ge=0)
    telemetry_sample_count: int = Field(ge=0)
    required_channels: tuple[str, ...] = (
        "lap_dist_pct_100",
        "brake_pct",
        "throttle_pct",
        "steering_deg",
    )
    source_channels: tuple[str, ...] = ()
    channel_repeatability: tuple[DriverChannelRepeatability, ...] = ()
    focus: DriverCoachingFocus | None = None
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def coaching_signature_never_becomes_setup_authority(self) -> DriverRepeatabilitySignature:
        if self.eligible_lap_count != len(self.eligible_lap_numbers):
            raise ValueError("eligible lap count must match exact lap identities")
        if self.status is ObservationStatus.BLOCKED:
            if not self.blocker_reasons or self.focus is not None:
                raise ValueError("blocked driver reports require blockers and no focus")
            if self.evidence_state is not EvidenceState.BLOCKED_BY_CONTEXT:
                raise ValueError("blocked driver reports require blocked evidence")
        else:
            if self.blocker_reasons or not self.channel_repeatability:
                raise ValueError("unblocked driver reports require repeatability evidence")
            if self.status is ObservationStatus.READY and self.focus is None:
                raise ValueError("ready driver reports require one coaching focus")
            if self.status is ObservationStatus.NO_FINDING and self.focus is not None:
                raise ValueError("no-finding driver reports cannot carry a focus")
        return self


class RunObservationIntelligence(ObservationModel):
    run_id: str = Field(min_length=1)
    setup_id: str | None
    authority: Literal["observation_only"] = "observation_only"
    opportunity_signatures: OpportunitySignatureReport
    mechanism_observations: MechanismObservationReport
    anomaly_envelopes: SameSetupAnomalyReport
    driver_repeatability: DriverRepeatabilitySignature
    brake_throttle_response: DynamicResponseReport | None = None
    stint_response_migration: StintResponseMigrationReport | None = None
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def nested_run_scope_is_exact(self) -> RunObservationIntelligence:
        scopes = (
            self.opportunity_signatures,
            self.mechanism_observations,
            self.anomaly_envelopes,
            self.driver_repeatability,
        )
        if any(scope.run_id != self.run_id for scope in scopes):
            raise ValueError("all observation reports must match the requested run")
        if (
            self.brake_throttle_response is not None
            and self.brake_throttle_response.run_id != self.run_id
        ):
            raise ValueError("the dynamic-response report must match the requested run")
        if (
            self.stint_response_migration is not None
            and self.stint_response_migration.run_id != self.run_id
        ):
            raise ValueError("the stint-response report must match the requested run")
        return self


__all__ = [
    "DriverChannelRepeatability",
    "DriverCoachingFocus",
    "DriverRepeatabilitySignature",
    "MechanismKind",
    "MechanismObservation",
    "MechanismObservationReport",
    "ObservationCitation",
    "ObservationStatus",
    "PhysicalSegment",
    "ProducerArtifactScope",
    "OpportunitySignature",
    "OpportunitySignatureReport",
    "RunObservationIntelligence",
    "SameSetupAnomaly",
    "SameSetupAnomalyReport",
]
