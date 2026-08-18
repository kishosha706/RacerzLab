"""Strict observation-only contracts for continuous vehicle response signatures."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from racelab_engine.models.engineering import EngineeringModel
from racelab_engine.models.evidence import EvidenceState


ResponseTransition = Literal["rising", "falling"]
ResponsePolarity = Literal["positive", "negative", "either"]
ResponseStatus = Literal["ready", "partial", "blocked", "no_finding"]
PathResponseStatus = Literal["ready", "partial", "blocked", "no_finding"]


class DynamicResponseModel(EngineeringModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class DynamicResponsePathContract(DynamicResponseModel):
    """Reusable input-to-response measurement contract.

    The contract describes a temporal observation only.  It deliberately has
    no handling-cause threshold, component conclusion, setup target, or test
    authority.
    """

    contract_id: str = Field(min_length=1)
    formula_version: str = Field(min_length=1)
    producer_id: Literal["p20.dynamic_response"] = "p20.dynamic_response"
    input_channel: str = Field(min_length=1)
    input_unit: str = Field(min_length=1)
    input_transition: ResponseTransition
    response_channel: str = Field(min_length=1)
    response_unit: str = Field(min_length=1)
    response_polarity: ResponsePolarity
    gain_unit: str = Field(min_length=1)
    required_channels: tuple[str, ...] = Field(min_length=5)
    preferred_channels: tuple[str, ...] = ()
    minimum_independent_laps: int = Field(default=2, ge=2)
    onset_semantics: Literal["episode_relative_empirical_noise"] = (
        "episode_relative_empirical_noise"
    )
    evidence_state: Literal[EvidenceState.CALCULATED] = EvidenceState.CALCULATED
    authority: Literal["observation_only"] = "observation_only"
    cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def contract_is_non_authoritative_and_complete(
        self,
    ) -> DynamicResponsePathContract:
        if len(self.required_channels) != len(set(self.required_channels)):
            raise ValueError("dynamic-response required channels must be unique")
        if len(self.preferred_channels) != len(set(self.preferred_channels)):
            raise ValueError("dynamic-response preferred channels must be unique")
        if set(self.required_channels) & set(self.preferred_channels):
            raise ValueError("required and preferred response channels cannot overlap")
        if self.input_channel not in self.required_channels:
            raise ValueError("the response contract must require its input channel")
        if self.response_channel not in self.required_channels:
            raise ValueError("the response contract must require its response channel")
        return self


class ResponsePhysicalScope(DynamicResponseModel):
    lap_pct_start: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    input_onset_lap_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)
    response_onset_lap_pct: float = Field(ge=0.0, le=100.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def scope_is_ordered(self) -> ResponsePhysicalScope:
        if self.lap_pct_end < self.lap_pct_start:
            raise ValueError("dynamic-response physical scope must be ordered")
        if not self.lap_pct_start <= self.input_onset_lap_pct <= self.lap_pct_end:
            raise ValueError("input onset must stay inside response physical scope")
        if not self.lap_pct_start <= self.response_onset_lap_pct <= self.lap_pct_end:
            raise ValueError("response onset must stay inside response physical scope")
        return self


class ResponseSpeedBand(DynamicResponseModel):
    minimum_mps: float = Field(ge=0.0, allow_inf_nan=False)
    median_mps: float = Field(ge=0.0, allow_inf_nan=False)
    maximum_mps: float = Field(ge=0.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def speed_band_is_ordered(self) -> ResponseSpeedBand:
        if not self.minimum_mps <= self.median_mps <= self.maximum_mps:
            raise ValueError("dynamic-response speed band must be ordered")
        return self


class QualifiedClockBinding(DynamicResponseModel):
    clock_id: str = Field(pattern=r"^telemetry-clock:[0-9a-f]{24}$")
    run_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    primary_clock: Literal["session_tick", "session_time", "unavailable"]
    clock_state: Literal["qualified", "degraded", "blocked", "unavailable"]
    tick_rate_hz: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    canonical_clock_coverage_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
    )
    source_channels: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def binding_retains_clock_truth(self) -> QualifiedClockBinding:
        if self.clock_state == "qualified" and (
            self.primary_clock != "session_tick"
            or self.tick_rate_hz is None
            or self.blockers
        ):
            raise ValueError("qualified response clocks require an unblocked tick clock")
        if self.clock_state == "blocked" and not self.blockers:
            raise ValueError("blocked response clocks require canonical clock blockers")
        return self


class DynamicResponseEpisode(DynamicResponseModel):
    episode_id: str = Field(pattern=r"^response-episode:[0-9a-f]{24}$")
    contract_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    lap_number: int = Field(ge=0)
    phase: str = Field(min_length=1)
    physical_scope: ResponsePhysicalScope
    input_onset_time_s: float = Field(allow_inf_nan=False)
    response_onset_time_s: float = Field(allow_inf_nan=False)
    observed_lag_s: float = Field(ge=0.0, allow_inf_nan=False)
    input_delta: float = Field(allow_inf_nan=False)
    response_delta: float = Field(allow_inf_nan=False)
    initial_gain: float | None = Field(default=None, allow_inf_nan=False)
    peak_gain: float | None = Field(default=None, allow_inf_nan=False)
    steady_gain: float | None = Field(default=None, allow_inf_nan=False)
    gain_unit: str = Field(min_length=1)
    overshoot_fraction: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    settling_duration_s: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    correction_count: int = Field(ge=0)
    speed_band: ResponseSpeedBand
    sample_count: int = Field(ge=3)
    source_channels: tuple[str, ...] = Field(min_length=5)
    canonical_clock_id: str = Field(pattern=r"^telemetry-clock:[0-9a-f]{24}$")
    canonical_clock_state: Literal["qualified"] = "qualified"
    canonical_clock_blockers: tuple[()] = ()
    evidence_state: Literal[EvidenceState.CALCULATED] = EvidenceState.CALCULATED
    authority: Literal["observation_only"] = "observation_only"
    cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def episode_is_clock_bound_and_non_authoritative(
        self,
    ) -> DynamicResponseEpisode:
        if self.response_onset_time_s < self.input_onset_time_s:
            raise ValueError("response onset cannot precede the measured input onset")
        if abs(
            (self.response_onset_time_s - self.input_onset_time_s)
            - self.observed_lag_s
        ) > 1e-9:
            raise ValueError("observed lag must equal the two canonical onsets")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("dynamic-response episode channels must be unique")
        return self


class DynamicResponseRepeatability(DynamicResponseModel):
    score: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    independent_lap_count: int = Field(ge=2)
    independent_lap_numbers: tuple[int, ...] = Field(min_length=2)
    basis: Literal["distinct_canonical_eligible_laps"] = (
        "distinct_canonical_eligible_laps"
    )
    input_onset_position_mad_pct: float = Field(ge=0.0, allow_inf_nan=False)
    observed_lag_mad_s: float = Field(ge=0.0, allow_inf_nan=False)
    peak_gain_relative_mad: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def repetitions_are_laps_not_samples(self) -> DynamicResponseRepeatability:
        if self.independent_lap_count != len(self.independent_lap_numbers):
            raise ValueError("repeatability count must equal distinct cited lap identities")
        if len(self.independent_lap_numbers) != len(set(self.independent_lap_numbers)):
            raise ValueError("raw rows or duplicate lap episodes cannot inflate repeatability")
        return self


class DynamicResponseSignature(DynamicResponseModel):
    signature_id: str = Field(pattern=r"^dynamic-response:[0-9a-f]{24}$")
    contract: DynamicResponsePathContract
    run_id: str = Field(min_length=1)
    setup_id: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    physical_scope: ResponsePhysicalScope
    representative_input_onset_time_s: float = Field(allow_inf_nan=False)
    representative_response_onset_time_s: float = Field(allow_inf_nan=False)
    median_observed_lag_s: float = Field(ge=0.0, allow_inf_nan=False)
    median_initial_gain: float | None = Field(default=None, allow_inf_nan=False)
    median_peak_gain: float | None = Field(default=None, allow_inf_nan=False)
    median_steady_gain: float | None = Field(default=None, allow_inf_nan=False)
    gain_unit: str = Field(min_length=1)
    median_overshoot_fraction: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    median_settling_duration_s: float | None = Field(
        default=None,
        ge=0.0,
        allow_inf_nan=False,
    )
    median_correction_count: float = Field(ge=0.0, allow_inf_nan=False)
    speed_band: ResponseSpeedBand
    repeatability: DynamicResponseRepeatability
    episodes: tuple[DynamicResponseEpisode, ...] = Field(min_length=2)
    source_channels: tuple[str, ...] = Field(min_length=5)
    canonical_clock_ids: tuple[str, ...] = Field(min_length=2)
    canonical_clock_blockers: tuple[()] = ()
    evidence_state: Literal[EvidenceState.CALCULATED] = EvidenceState.CALCULATED
    authority: Literal["observation_only"] = "observation_only"
    cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def signature_has_independent_exact_episodes(
        self,
    ) -> DynamicResponseSignature:
        lap_numbers = tuple(episode.lap_number for episode in self.episodes)
        if len(lap_numbers) != len(set(lap_numbers)):
            raise ValueError("one lap can contribute at most one independent episode")
        if lap_numbers != self.repeatability.independent_lap_numbers:
            raise ValueError("signature episodes must match repeatability lap identities")
        if self.repeatability.independent_lap_count != len(self.episodes):
            raise ValueError("signature repetition count must equal episode count")
        if self.gain_unit != self.contract.gain_unit:
            raise ValueError("signature gain units must match the response contract")
        if any(
            episode.contract_id != self.contract.contract_id
            or episode.run_id != self.run_id
            or episode.setup_id != self.setup_id
            or episode.phase != self.phase
            or episode.gain_unit != self.gain_unit
            for episode in self.episodes
        ):
            raise ValueError("dynamic-response episodes must match signature scope")
        episode_clock_ids = tuple(dict.fromkeys(
            episode.canonical_clock_id for episode in self.episodes
        ))
        if episode_clock_ids != self.canonical_clock_ids:
            raise ValueError("signature clock identities must cover every exact episode")
        if len(self.source_channels) != len(set(self.source_channels)):
            raise ValueError("dynamic-response signature channels must be unique")
        return self


class DynamicResponsePathResult(DynamicResponseModel):
    contract: DynamicResponsePathContract
    status: PathResponseStatus
    detected_episode_count: int = Field(ge=0)
    independent_lap_count: int = Field(ge=0)
    signatures: tuple[DynamicResponseSignature, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def path_status_matches_evidence(self) -> DynamicResponsePathResult:
        if self.status == "ready" and (not self.signatures or self.blocker_reasons):
            raise ValueError("ready response paths require signatures and no blockers")
        if self.status == "partial" and (not self.signatures or not self.blocker_reasons):
            raise ValueError("partial response paths require evidence and exclusion blockers")
        if self.status == "blocked" and (self.signatures or not self.blocker_reasons):
            raise ValueError("blocked response paths require blockers and no signatures")
        if self.status == "no_finding" and (self.signatures or self.blocker_reasons):
            raise ValueError("no-finding response paths cannot carry evidence or blockers")
        return self


class DynamicResponseReport(DynamicResponseModel):
    report_id: str = Field(pattern=r"^dynamic-response-report:[0-9a-f]{24}$")
    status: ResponseStatus
    run_id: str = Field(min_length=1)
    setup_id: str | None
    eligible_lap_numbers: tuple[int, ...] = ()
    analyzed_lap_numbers: tuple[int, ...] = ()
    clock_bindings: tuple[QualifiedClockBinding, ...] = ()
    paths: tuple[DynamicResponsePathResult, ...] = Field(min_length=1)
    blocker_reasons: tuple[str, ...] = ()
    evidence_state: Literal[
        EvidenceState.CALCULATED,
        EvidenceState.BLOCKED_BY_CONTEXT,
    ]
    authority: Literal["observation_only"] = "observation_only"
    cause_authorized: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def report_is_scoped_and_fail_closed(self) -> DynamicResponseReport:
        if len(self.eligible_lap_numbers) != len(set(self.eligible_lap_numbers)):
            raise ValueError("eligible dynamic-response laps must be distinct")
        if len(self.analyzed_lap_numbers) != len(set(self.analyzed_lap_numbers)):
            raise ValueError("analyzed dynamic-response laps must be distinct")
        if not set(self.analyzed_lap_numbers) <= set(self.eligible_lap_numbers):
            raise ValueError("response analysis cannot use ineligible laps")
        ready_paths = tuple(path for path in self.paths if path.status == "ready")
        evidence_paths = tuple(
            path for path in self.paths if path.status in {"ready", "partial"}
        )
        blocked_paths = tuple(path for path in self.paths if path.status == "blocked")
        if self.status == "ready" and (
            len(ready_paths) != len(self.paths)
            or self.blocker_reasons
            or self.evidence_state is not EvidenceState.CALCULATED
        ):
            raise ValueError("ready response reports require every path")
        if self.status == "partial" and (
            not evidence_paths
            or len(ready_paths) == len(self.paths)
            or self.evidence_state is not EvidenceState.CALCULATED
            or (
                any(path.status in {"partial", "blocked"} for path in self.paths)
                != bool(self.blocker_reasons)
            )
        ):
            raise ValueError(
                "partial response reports require at least one ready and one unresolved path"
            )
        if self.status == "blocked" and (
            evidence_paths
            or not self.blocker_reasons
            or self.evidence_state is not EvidenceState.BLOCKED_BY_CONTEXT
        ):
            raise ValueError("blocked response reports require scoped blockers")
        if self.status == "no_finding" and (
            evidence_paths
            or blocked_paths
            or self.blocker_reasons
            or self.evidence_state is not EvidenceState.CALCULATED
        ):
            raise ValueError("no-finding response reports cannot carry blockers")
        for binding in self.clock_bindings:
            if binding.run_id != self.run_id:
                raise ValueError("response clock bindings must match the requested run")
        for path in evidence_paths:
            for signature in path.signatures:
                if signature.run_id != self.run_id or signature.setup_id != self.setup_id:
                    raise ValueError("response signatures must match report scope")
        return self


__all__ = [
    "DynamicResponseEpisode",
    "DynamicResponsePathContract",
    "DynamicResponsePathResult",
    "DynamicResponseRepeatability",
    "DynamicResponseReport",
    "DynamicResponseSignature",
    "QualifiedClockBinding",
    "ResponsePhysicalScope",
    "ResponseSpeedBand",
]
