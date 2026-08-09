"""Exact-session engineering history and controlled-hypothesis lifecycle contracts.

These models keep observed run-to-run changes separate from controlled-test
outcomes.  A session ledger is descriptive only; causal setup learning remains
owned by the A/B/A2 workflow and prediction-grade contracts.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class SessionIntelligenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


EvidenceCitationKind = Literal[
    "run",
    "lap",
    "event",
    "setup",
    "manifest",
    "position_evidence",
    "workflow",
    "prediction_contract",
    "prediction_grade",
]


class SessionEvidenceCitation(SessionIntelligenceModel):
    kind: EvidenceCitationKind
    reference_id: str = Field(min_length=1)
    run_id: str | None = None
    lap_number: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_exact_scope(self) -> SessionEvidenceCitation:
        if self.reference_id != self.reference_id.strip():
            raise ValueError("evidence citation identities must be canonical")
        if self.kind == "run" and self.reference_id != self.run_id:
            raise ValueError("run citations must repeat their exact run identity")
        if self.kind == "lap" and (
            self.run_id is None
            or self.lap_number is None
            or self.reference_id != f"{self.run_id}:{self.lap_number}"
        ):
            raise ValueError("lap citations require an exact run and lap identity")
        if self.lap_number is not None and self.kind != "lap":
            raise ValueError("only lap citations may publish a lap number")
        return self


class NumericOperatingContextMatch(SessionIntelligenceModel):
    channel: str = Field(min_length=1)
    baseline_range: tuple[FiniteFloat, FiniteFloat]
    test_range: tuple[FiniteFloat, FiniteFloat]
    baseline_coverage: FiniteFloat = Field(ge=0.95, le=1.0)
    test_coverage: FiniteFloat = Field(ge=0.95, le=1.0)
    tolerance: FiniteFloat = Field(ge=0.0)
    maximum_within_lap_span: FiniteFloat = Field(gt=0.0)
    matched: Literal[True] = True

    @model_validator(mode="after")
    def ranges_are_stable_and_overlap(self) -> NumericOperatingContextMatch:
        baseline_low, baseline_high = self.baseline_range
        test_low, test_high = self.test_range
        if baseline_low > baseline_high or test_low > test_high:
            raise ValueError("context ranges must be ordered")
        if (
            baseline_high - baseline_low > self.maximum_within_lap_span
            or test_high - test_low > self.maximum_within_lap_span
        ):
            raise ValueError("within-lap context varied beyond its comparison limit")
        if max(baseline_low, test_low) > min(baseline_high, test_high) + self.tolerance:
            raise ValueError("context ranges do not overlap inside the declared tolerance")
        return self


class AngularOperatingContextMatch(SessionIntelligenceModel):
    channel: Literal["wind_dir"] = "wind_dir"
    baseline_median: FiniteFloat = Field(ge=-2.0 * math.pi, le=2.0 * math.pi)
    test_median: FiniteFloat = Field(ge=-2.0 * math.pi, le=2.0 * math.pi)
    absolute_delta_rad: FiniteFloat = Field(ge=0.0, le=math.pi)
    maximum_delta_rad: FiniteFloat = Field(gt=0.0, le=math.pi)
    baseline_coverage: FiniteFloat = Field(ge=0.95, le=1.0)
    test_coverage: FiniteFloat = Field(ge=0.95, le=1.0)
    matched: Literal[True] = True

    @model_validator(mode="after")
    def direction_stays_inside_limit(self) -> AngularOperatingContextMatch:
        if self.absolute_delta_rad > self.maximum_delta_rad:
            raise ValueError("wind direction changed beyond its comparison limit")
        return self


class CategoricalOperatingContextMatch(SessionIntelligenceModel):
    channel: Literal["player_tire_compound"] = "player_tire_compound"
    baseline_value: str = Field(min_length=1)
    test_value: str = Field(min_length=1)
    baseline_coverage: FiniteFloat = Field(ge=0.95, le=1.0)
    test_coverage: FiniteFloat = Field(ge=0.95, le=1.0)
    matched: Literal[True] = True

    @model_validator(mode="after")
    def categories_match_exactly(self) -> CategoricalOperatingContextMatch:
        if self.baseline_value != self.test_value:
            raise ValueError("tire compound must match exactly")
        return self


class RacingLineContextMatch(SessionIntelligenceModel):
    channels: tuple[str, str] = ("lat", "lon")
    coverage_fraction: FiniteFloat = Field(ge=0.95, le=1.0)
    median_deviation_m: FiniteFloat = Field(ge=0.0)
    p95_deviation_m: FiniteFloat = Field(ge=0.0)
    maximum_median_deviation_m: FiniteFloat = Field(gt=0.0, le=1.5)
    maximum_p95_deviation_m: FiniteFloat = Field(default=3.0, gt=0.0, le=3.0)
    matched: Literal[True] = True

    @model_validator(mode="after")
    def line_stays_inside_limit(self) -> RacingLineContextMatch:
        if self.channels != ("lat", "lon"):
            raise ValueError("line context requires exact GPS channels")
        if self.p95_deviation_m < self.median_deviation_m:
            raise ValueError("racing-line p95 deviation cannot be below its median")
        if self.median_deviation_m > self.maximum_median_deviation_m:
            raise ValueError("racing-line deviation exceeded the comparison limit")
        if self.p95_deviation_m > self.maximum_p95_deviation_m:
            raise ValueError("racing-line tail deviation exceeded the comparison limit")
        return self


class ProximityOperatingContextMatch(SessionIntelligenceModel):
    channels: tuple[str, ...] = Field(min_length=3)
    baseline_state: Literal["no_nearby_car_reported"]
    test_state: Literal["no_nearby_car_reported"]
    baseline_coverage: Literal[1.0]
    test_coverage: Literal[1.0]
    baseline_min_distance_ahead_m: FiniteFloat = Field(ge=0.0)
    baseline_min_distance_behind_m: FiniteFloat = Field(ge=0.0)
    test_min_distance_ahead_m: FiniteFloat = Field(ge=0.0)
    test_min_distance_behind_m: FiniteFloat = Field(ge=0.0)
    baseline_min_time_gap_ahead_s: FiniteFloat = Field(ge=0.0)
    baseline_min_time_gap_behind_s: FiniteFloat = Field(ge=0.0)
    test_min_time_gap_ahead_s: FiniteFloat = Field(ge=0.0)
    test_min_time_gap_behind_s: FiniteFloat = Field(ge=0.0)
    ahead_exclusion_seconds: FiniteFloat = Field(gt=0.0)
    behind_exclusion_seconds: FiniteFloat = Field(gt=0.0)
    matched: Literal[True] = True

    @model_validator(mode="after")
    def exact_proximity_channels_are_cited(self) -> ProximityOperatingContextMatch:
        required = {"car_distance_ahead_m", "car_distance_behind_m"}
        if not required <= set(self.channels) or not {
            "speed_mps",
            "speed_mph",
        } & set(self.channels):
            raise ValueError("proximity context requires both distances and player speed")
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("proximity context channels must be unique")
        if (
            min(
                self.baseline_min_time_gap_ahead_s,
                self.test_min_time_gap_ahead_s,
            )
            <= self.ahead_exclusion_seconds
            or min(
                self.baseline_min_time_gap_behind_s,
                self.test_min_time_gap_behind_s,
            )
            <= self.behind_exclusion_seconds
        ):
            raise ValueError(
                "no-nearby-car context requires measured gaps outside both exclusion windows"
            )
        return self


class PairedLapOperatingContext(SessionIntelligenceModel):
    baseline_lap_id: str = Field(min_length=1)
    test_lap_id: str = Field(min_length=1)
    fuel: NumericOperatingContextMatch
    air_temperature: NumericOperatingContextMatch
    track_temperature: NumericOperatingContextMatch
    wind_speed: NumericOperatingContextMatch
    wind_direction: AngularOperatingContextMatch
    tire_distances: tuple[NumericOperatingContextMatch, ...] = Field(
        min_length=4,
        max_length=4,
    )
    tire_compound: CategoricalOperatingContextMatch
    line: RacingLineContextMatch
    proximity: ProximityOperatingContextMatch
    source_channels: tuple[str, ...] = Field(min_length=9)

    @model_validator(mode="after")
    def required_roles_and_channels_are_exact(self) -> PairedLapOperatingContext:
        required_roles = {
            self.fuel.channel,
            self.air_temperature.channel,
            self.track_temperature.channel,
            self.wind_speed.channel,
            self.wind_direction.channel,
            *self.line.channels,
            *self.proximity.channels,
        }
        tire_roles = {
            *(match.channel for match in self.tire_distances),
            self.tire_compound.channel,
        }
        if not required_roles | tire_roles <= set(self.source_channels):
            raise ValueError("paired context must cite every matched context channel")
        if len(set(self.source_channels)) != len(self.source_channels):
            raise ValueError("paired context channels must be unique")
        if self.fuel.channel not in {"fuel_level", "fuel_level_pct"}:
            raise ValueError("fuel context must use a canonical measured fuel channel")
        if self.air_temperature.channel != "air_temp":
            raise ValueError("air-temperature context must use air_temp")
        if self.track_temperature.channel != "track_temp":
            raise ValueError("track-temperature context must use track_temp")
        if self.wind_speed.channel != "wind_vel":
            raise ValueError("wind-speed context must use wind_vel")
        allowed_tire_channels = {
            "lf_tire_distance_m",
            "rf_tire_distance_m",
            "lr_tire_distance_m",
            "rr_tire_distance_m",
        }
        if any(match.channel not in allowed_tire_channels for match in self.tire_distances):
            raise ValueError("tire-distance context must use canonical per-corner channels")
        if {
            match.channel for match in self.tire_distances
        } != allowed_tire_channels:
            raise ValueError("tire-distance context requires all four canonical corners")
        physical_limits = {
            "fuel_level": (0.0, 1_000.0),
            "fuel_level_pct": (0.0, 100.0),
            "air_temp": (-100.0, 100.0),
            "track_temp": (-100.0, 200.0),
            "wind_vel": (0.0, 200.0),
            **{channel: (0.0, 10_000_000.0) for channel in allowed_tire_channels},
        }
        for match in (
            self.fuel,
            self.air_temperature,
            self.track_temperature,
            self.wind_speed,
            *self.tire_distances,
        ):
            minimum, maximum = physical_limits[match.channel]
            if any(
                value < minimum or value > maximum
                for bounds in (match.baseline_range, match.test_range)
                for value in bounds
            ):
                raise ValueError(
                    f"{match.channel} context falls outside broad physical limits"
                )
        return self


class OperatingContextAttestation(SessionIntelligenceModel):
    status: Literal["matched"] = "matched"
    comparison_scope: Literal["paired_lap_physical_window"] = (
        "paired_lap_physical_window"
    )
    pairs: tuple[PairedLapOperatingContext, ...] = Field(min_length=3)
    source_channels: tuple[str, ...] = Field(min_length=9)
    noise_method: Literal["paired_lap_median_absolute_deviation"] = (
        "paired_lap_median_absolute_deviation"
    )

    @model_validator(mode="after")
    def pair_identities_are_unique_and_channels_are_complete(
        self,
    ) -> OperatingContextAttestation:
        baseline_ids = [pair.baseline_lap_id for pair in self.pairs]
        test_ids = [pair.test_lap_id for pair in self.pairs]
        if len(set(baseline_ids)) != len(baseline_ids) or len(set(test_ids)) != len(
            test_ids
        ):
            raise ValueError("context-match lap identities must be unique")
        pair_channels = {channel for pair in self.pairs for channel in pair.source_channels}
        if pair_channels != set(self.source_channels):
            raise ValueError("context attestation channels must equal its paired evidence")
        if len(set(self.source_channels)) != len(self.source_channels):
            raise ValueError("context-match channel identities must be unique")
        return self


class PositionAlignedEvidence(SessionIntelligenceModel):
    """Producer-owned, position-aligned observation supplied to the ledger.

    ``delta_s`` is test minus baseline.  Negative values are observed gains.
    The service validates the digest, exact pair, eligible lap identities, and
    alignment coverage before using this evidence.
    """

    evidence_id: str = Field(min_length=1)
    baseline_run_id: str = Field(min_length=1)
    test_run_id: str = Field(min_length=1)
    baseline_lap_ids: tuple[str, ...] = Field(min_length=1)
    test_lap_ids: tuple[str, ...] = Field(min_length=1)
    start_pct: FiniteFloat = Field(ge=0.0, le=100.0)
    end_pct: FiniteFloat = Field(ge=0.0, le=100.0)
    phase: str = Field(min_length=1)
    delta_s: FiniteFloat
    empirical_noise_s: FiniteFloat = Field(ge=0.0)
    alignment_confidence: FiniteFloat = Field(ge=0.0, le=1.0)
    source_channels: tuple[str, ...] = Field(min_length=1)
    context_match: OperatingContextAttestation
    provenance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_physical_window_and_unique_scope(self) -> PositionAlignedEvidence:
        if self.baseline_run_id == self.test_run_id:
            raise ValueError("position evidence requires two distinct runs")
        if self.end_pct <= self.start_pct:
            raise ValueError("position evidence requires a non-zero physical window")
        for values, label in (
            (self.baseline_lap_ids, "baseline lap"),
            (self.test_lap_ids, "test lap"),
            (self.source_channels, "channel"),
        ):
            if any(not value.strip() or value != value.strip() for value in values):
                raise ValueError(f"position-evidence {label} identities must be canonical")
            if len(set(values)) != len(values):
                raise ValueError(f"position-evidence {label} identities must be unique")
        if tuple(pair.baseline_lap_id for pair in self.context_match.pairs) != (
            self.baseline_lap_ids
        ) or tuple(pair.test_lap_id for pair in self.context_match.pairs) != self.test_lap_ids:
            raise ValueError("context-match laps must equal the position-evidence cohort")
        if not set(self.context_match.source_channels) <= set(self.source_channels):
            raise ValueError("context-match channels must be bound to position evidence")
        if abs(self.delta_s) <= self.empirical_noise_s:
            raise ValueError("position-aligned delta must exceed paired-lap empirical noise")
        return self


class ComparabilityDebt(SessionIntelligenceModel):
    debt_id: str = Field(min_length=1)
    kind: Literal[
        "session_pair",
        "eligible_laps",
        "observation_scope",
        "insufficient_repetition",
        "telemetry_rows",
        "position_alignment",
        "operating_context",
        "no_signal",
        "integrity",
    ]
    baseline_run_id: str | None = None
    test_run_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    required_channels: tuple[str, ...] = ()
    recovery: str = Field(min_length=1)


class SessionPositionEvidenceResult(SessionIntelligenceModel):
    current_run_id: str = Field(min_length=1)
    evidence: tuple[PositionAlignedEvidence, ...] = ()
    comparability_debt: tuple[ComparabilityDebt, ...] = ()

    @model_validator(mode="after")
    def result_is_explicit(self) -> SessionPositionEvidenceResult:
        if not self.evidence and not self.comparability_debt:
            raise ValueError("empty position evidence requires typed comparability debt")
        if self.evidence and self.comparability_debt:
            raise ValueError("complete evidence cannot carry unresolved comparability debt")
        return self


class LedgerSetupChange(SessionIntelligenceModel):
    setup_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    baseline_value: Any = None
    test_value: Any = None
    delta: str | None = None


class RunEvidenceIdentity(SessionIntelligenceModel):
    run_id: str = Field(min_length=1)
    source_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    telemetry_cache_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    setup_id: str | None = None
    eligible_lap_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def lap_ids_belong_to_run(self) -> RunEvidenceIdentity:
        if any(not lap_id.startswith(f"{self.run_id}:") for lap_id in self.eligible_lap_ids):
            raise ValueError("eligible lap identities must belong to the run evidence identity")
        if len(set(self.eligible_lap_ids)) != len(self.eligible_lap_ids):
            raise ValueError("eligible lap identities must be unique")
        return self


LedgerState = Literal[
    "new",
    "improved",
    "regressed",
    "recurring",
    "resolved",
    "not_comparable",
]


class SessionLedgerEntry(SessionIntelligenceModel):
    entry_id: str = Field(min_length=1)
    state: LedgerState
    observation_kind: Literal[
        "pace",
        "new_issue",
        "recurring_issue",
        "resolved_issue",
        "comparability",
    ]
    baseline_run_id: str = Field(min_length=1)
    test_run_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_scope: Literal["position_aligned", "whole_lap", "event_signature", "none"]
    delta_s: FiniteFloat | None = None
    start_pct: FiniteFloat | None = Field(default=None, ge=0.0, le=100.0)
    end_pct: FiniteFloat | None = Field(default=None, ge=0.0, le=100.0)
    phase: str | None = None
    setup_changes: tuple[LedgerSetupChange, ...] = ()
    attribution: Literal["observation_only"] = "observation_only"
    causal_claim: Literal[False] = False
    citations: tuple[SessionEvidenceCitation, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def keep_observation_and_authority_consistent(self) -> SessionLedgerEntry:
        if self.baseline_run_id == self.test_run_id:
            raise ValueError("ledger entries require two distinct runs")
        if self.state == "not_comparable":
            if not self.blocker_reasons or self.delta_s is not None or self.evidence_scope != "none":
                raise ValueError("not-comparable entries require blockers and cannot publish an effect")
        elif self.blocker_reasons or not self.citations:
            raise ValueError("comparable ledger observations require citations and no blockers")
        if self.state == "improved" and (self.delta_s is None or self.delta_s >= 0.0):
            raise ValueError("improved observations require a negative test-minus-baseline delta")
        if self.state == "regressed" and (self.delta_s is None or self.delta_s <= 0.0):
            raise ValueError("regressed observations require a positive test-minus-baseline delta")
        if self.state in {"new", "recurring", "resolved"} and self.delta_s is not None:
            raise ValueError("issue-state observations cannot publish a time effect")
        has_window = self.start_pct is not None or self.end_pct is not None
        if has_window and (
            self.start_pct is None
            or self.end_pct is None
            or self.end_pct <= self.start_pct
            or self.evidence_scope not in {"position_aligned", "event_signature"}
        ):
            raise ValueError("track windows require ordered position-aligned or event evidence")
        return self


class SessionEngineeringLedger(SessionIntelligenceModel):
    session_id: str = Field(min_length=1)
    session_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["ready", "limited", "blocked"]
    ordered_run_ids: tuple[str, ...]
    run_evidence: tuple[RunEvidenceIdentity, ...] = ()
    entries: tuple[SessionLedgerEntry, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def entries_stay_inside_exact_session(self) -> SessionEngineeringLedger:
        if len(set(self.ordered_run_ids)) != len(self.ordered_run_ids):
            raise ValueError("session run identities must be unique and ordered")
        scope = set(self.ordered_run_ids)
        if any(identity.run_id not in scope for identity in self.run_evidence):
            raise ValueError("run evidence must remain inside the exact session")
        if any(
            entry.baseline_run_id not in scope or entry.test_run_id not in scope
            for entry in self.entries
        ):
            raise ValueError("ledger entries must remain inside the exact session")
        if self.status == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked ledgers require recovery blockers")
        if self.status == "ready" and (
            self.blocker_reasons
            or any(entry.state == "not_comparable" for entry in self.entries)
        ):
            raise ValueError("ready ledgers cannot contain blocked transitions")
        return self


class HypothesisTargetEffect(SessionIntelligenceModel):
    metric: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    expected_direction: Literal["decrease", "increase"] | None = None
    expected_range_s: tuple[FiniteFloat, FiniteFloat] | None = None
    actual_effect_s: FiniteFloat | None = None
    actual_direction: Literal["decrease", "increase", "inconclusive", "unavailable"]
    direction_result: Literal["matched", "missed", "inconclusive", "unavailable"]
    range_result: Literal["inside", "outside", "inconclusive", "unavailable"]

    @model_validator(mode="after")
    def range_is_ordered(self) -> HypothesisTargetEffect:
        if self.expected_range_s is not None and self.expected_range_s[0] > self.expected_range_s[1]:
            raise ValueError("expected target-effect ranges must be ordered")
        return self


class HypothesisCountereffects(SessionIntelligenceModel):
    criteria: tuple[str, ...]
    passed: bool | None
    observed_metrics: dict[str, FiniteFloat] = Field(default_factory=dict)


class HypothesisProtocol(SessionIntelligenceModel):
    source_run_id: str = Field(min_length=1)
    a_run_id: str | None = None
    b_run_id: str | None = None
    a2_run_id: str | None = None
    eligible_lap_ids: tuple[str, ...] = ()
    protocol_valid: bool
    evidence_score: FiniteFloat = Field(ge=0.0, le=100.0)
    verdict: Literal["keep", "undo", "retest", "invalid"]
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_protocol_requires_complete_aba2(self) -> HypothesisProtocol:
        stage_ids = (self.a_run_id, self.b_run_id, self.a2_run_id)
        if self.protocol_valid and (
            any(run_id is None for run_id in stage_ids)
            or len(set(stage_ids)) != 3
            or self.blocker_reasons
            or not self.eligible_lap_ids
        ):
            raise ValueError("valid hypothesis protocols require exact A/B/A2 evidence")
        if not self.protocol_valid and not self.blocker_reasons:
            raise ValueError("invalid hypothesis protocols require blockers")
        return self


HypothesisOutcome = Literal["supported", "contradicted", "inconclusive", "invalid"]
HypothesisLifecycleState = Literal[
    "supported", "contradicted", "inconclusive", "invalid", "do_not_repeat"
]
HypothesisPolicyDimension = Literal[
    "context",
    "setup",
    "location",
    "symptom",
    "cause",
    "control",
    "direction",
    "metric",
    "phase",
    "countereffects",
]

_HYPOTHESIS_POLICY_VERSION = "exact-context-v2"
_HYPOTHESIS_POLICY_DIMENSION_ORDER: tuple[HypothesisPolicyDimension, ...] = (
    "context",
    "setup",
    "location",
    "symptom",
    "cause",
    "control",
    "direction",
    "metric",
    "phase",
    "countereffects",
)


def _policy_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class HypothesisPolicyIdentity(SessionIntelligenceModel):
    """Stable exact-context identity used only by the repeat-memory policy.

    This identity deliberately excludes workflow/run identities, evidence-event
    identities, and explanatory prose. Those remain bound by the separate
    per-instance protocol fingerprint and its provenance checks. The stable
    physical-position target remains a material policy dimension.
    """

    policy_version: Literal["exact-context-v2"] = _HYPOTHESIS_POLICY_VERSION
    policy_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    setup_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposed_control_value_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_symptom: str = Field(min_length=1)
    cause_bucket: str = Field(min_length=1)
    control_key: str = Field(min_length=1)
    control_direction_sign: Literal[-1, 1]
    expected_effect_direction: Literal["decrease", "increase"] | None = None
    target_metric: str = Field(min_length=1)
    target_phase: str = Field(min_length=1)
    countereffects: tuple[str, ...]

    @classmethod
    def build(
        cls,
        *,
        context_sha256: str,
        setup_sha256: str,
        target_scope_sha256: str,
        proposed_control_value_sha256: str,
        canonical_symptom: str,
        cause_bucket: str,
        control_key: str,
        control_direction_sign: Literal[-1, 1],
        expected_effect_direction: Literal["decrease", "increase"] | None,
        target_metric: str,
        target_phase: str,
        countereffects: tuple[str, ...],
    ) -> HypothesisPolicyIdentity:
        dimensions: dict[str, Any] = {
            "policy_version": _HYPOTHESIS_POLICY_VERSION,
            "context_sha256": context_sha256,
            "setup_sha256": setup_sha256,
            "target_scope_sha256": target_scope_sha256,
            "proposed_control_value_sha256": proposed_control_value_sha256,
            "canonical_symptom": canonical_symptom,
            "cause_bucket": cause_bucket,
            "control_key": control_key,
            "control_direction_sign": control_direction_sign,
            "expected_effect_direction": expected_effect_direction,
            "target_metric": target_metric,
            "target_phase": target_phase,
            "countereffects": countereffects,
        }
        return cls(policy_key=_policy_sha256(dimensions), **dimensions)

    @model_validator(mode="after")
    def key_binds_every_policy_dimension(self) -> HypothesisPolicyIdentity:
        dimensions = self.model_dump(mode="json", exclude={"policy_key"})
        if self.policy_key != _policy_sha256(dimensions):
            raise ValueError("hypothesis policy key must bind every exact policy dimension")
        if any(
            not value.strip() or value != value.strip()
            for value in (
                self.canonical_symptom,
                self.cause_bucket,
                self.control_key,
                self.target_metric,
                self.target_phase,
                *self.countereffects,
            )
        ):
            raise ValueError("hypothesis policy dimensions must be canonical")
        if tuple(sorted(set(self.countereffects))) != self.countereffects:
            raise ValueError("hypothesis countereffect identities must be sorted and unique")
        return self


class HypothesisRepeatPolicyComparison(SessionIntelligenceModel):
    workflow_id: str = Field(min_length=1)
    hypothesis_policy_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    changed_dimensions: tuple[HypothesisPolicyDimension, ...] = ()

    @model_validator(mode="after")
    def dimensions_are_unique_and_canonical(self) -> HypothesisRepeatPolicyComparison:
        expected = tuple(
            dimension
            for dimension in _HYPOTHESIS_POLICY_DIMENSION_ORDER
            if dimension in self.changed_dimensions
        )
        if self.changed_dimensions != expected:
            raise ValueError("changed policy dimensions must be unique and canonical")
        return self


class HistoricalIntelligenceDebt(SessionIntelligenceModel):
    """A saved session that cannot safely be treated as absent history."""

    session_id: str = Field(min_length=1)
    kind: Literal["history_incomplete"] = "history_incomplete"
    reason: str = Field(min_length=1)
    recovery: str = Field(min_length=1)


class HypothesisRepeatPolicyDecision(SessionIntelligenceModel):
    status: Literal["allowed", "blocked"]
    allowed: bool
    candidate_policy_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    matched_workflow_ids: tuple[str, ...] = ()
    comparisons: tuple[HypothesisRepeatPolicyComparison, ...] = ()
    changed_dimensions: tuple[HypothesisPolicyDimension, ...] = ()
    history_debt: tuple[HistoricalIntelligenceDebt, ...] = ()
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def decision_matches_exact_policy_comparisons(self) -> HypothesisRepeatPolicyDecision:
        if self.allowed != (self.status == "allowed"):
            raise ValueError("repeat-policy status and allowed flag must agree")
        exact_matches = tuple(
            comparison.workflow_id
            for comparison in self.comparisons
            if not comparison.changed_dimensions
        )
        if self.matched_workflow_ids != exact_matches:
            raise ValueError("matched workflows must be exact no-change policy comparisons")
        if self.allowed and (self.matched_workflow_ids or self.history_debt):
            raise ValueError("repeat policy cannot allow a matching Undo or incomplete history")
        if not self.allowed and not (self.matched_workflow_ids or self.history_debt):
            raise ValueError("blocked repeat policy requires a matching Undo or incomplete history")
        expected_changed = () if not self.allowed else tuple(
            dimension
            for dimension in _HYPOTHESIS_POLICY_DIMENSION_ORDER
            if any(
                dimension in comparison.changed_dimensions
                for comparison in self.comparisons
            )
        )
        if self.changed_dimensions != expected_changed:
            raise ValueError("decision changes must equal the deterministic comparison changes")
        history_ids = [item.session_id for item in self.history_debt]
        if len(history_ids) != len(set(history_ids)):
            raise ValueError("incomplete-history sessions must be unique")
        return self


class HypothesisLifecycleEntry(SessionIntelligenceModel):
    workflow_id: str = Field(min_length=1)
    hypothesis_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    hypothesis_policy: HypothesisPolicyIdentity | None = None
    lifecycle_state: HypothesisLifecycleState
    outcome_classification: HypothesisOutcome
    hypothesis: str = Field(min_length=1)
    expected_mechanism: str | None = None
    control_key: str | None = None
    direction_sign: Literal[-1, 1] | None = None
    target_effect: HypothesisTargetEffect
    countereffects: HypothesisCountereffects
    protocol: HypothesisProtocol
    do_not_repeat: bool = False
    do_not_repeat_reason: str | None = None
    citations: tuple[SessionEvidenceCitation, ...] = ()

    @model_validator(mode="after")
    def lifecycle_matches_outcome_and_policy(self) -> HypothesisLifecycleEntry:
        if (
            self.protocol_fingerprint is not None
            and self.protocol_fingerprint != self.hypothesis_fingerprint
        ):
            raise ValueError("legacy hypothesis fingerprint must equal the protocol fingerprint")
        if self.lifecycle_state == "do_not_repeat":
            if (
                self.outcome_classification == "invalid"
                or not self.do_not_repeat
                or not self.do_not_repeat_reason
                or not self.protocol.protocol_valid
                or self.protocol.verdict != "undo"
            ):
                raise ValueError(
                    "do-not-repeat requires a valid Undo policy and a non-invalid target outcome"
                )
        elif self.do_not_repeat or self.do_not_repeat_reason is not None:
            raise ValueError("only do-not-repeat lifecycle entries may block an exact hypothesis")
        if self.lifecycle_state != "do_not_repeat" and (
            self.lifecycle_state != self.outcome_classification
        ):
            raise ValueError("lifecycle state must match its outcome classification")
        if self.outcome_classification == "invalid" and self.protocol.protocol_valid:
            raise ValueError("invalid outcomes cannot publish a valid protocol")
        if self.outcome_classification != "invalid" and not self.protocol.protocol_valid:
            raise ValueError("non-invalid outcomes require a valid protocol")
        return self


class HypothesisLifecycle(SessionIntelligenceModel):
    session_id: str = Field(min_length=1)
    session_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["ready", "limited", "blocked"]
    ordered_run_ids: tuple[str, ...]
    entries: tuple[HypothesisLifecycleEntry, ...] = ()
    do_not_repeat_hypothesis_fingerprints: tuple[str, ...] = ()
    do_not_repeat_hypothesis_policy_keys: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def blocked_fingerprints_resolve_exactly(self) -> HypothesisLifecycle:
        expected = tuple(
            dict.fromkeys(
                entry.hypothesis_fingerprint
                for entry in self.entries
                if entry.lifecycle_state == "do_not_repeat"
            )
        )
        if self.do_not_repeat_hypothesis_fingerprints != expected:
            raise ValueError("do-not-repeat fingerprints must resolve to exact lifecycle entries")
        expected_policy_keys = tuple(
            dict.fromkeys(
                entry.hypothesis_policy.policy_key
                for entry in self.entries
                if entry.lifecycle_state == "do_not_repeat"
                and entry.hypothesis_policy is not None
            )
        )
        if self.do_not_repeat_hypothesis_policy_keys != expected_policy_keys:
            raise ValueError("do-not-repeat policy keys must resolve to exact lifecycle entries")
        if self.status == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked lifecycle reports require blockers")
        return self


class SessionIntelligenceBundle(SessionIntelligenceModel):
    session_ledger: SessionEngineeringLedger
    hypothesis_lifecycle: HypothesisLifecycle

    @model_validator(mode="after")
    def scopes_match(self) -> SessionIntelligenceBundle:
        if (
            self.session_ledger.session_id != self.hypothesis_lifecycle.session_id
            or self.session_ledger.session_scope_sha256
            != self.hypothesis_lifecycle.session_scope_sha256
            or self.session_ledger.ordered_run_ids
            != self.hypothesis_lifecycle.ordered_run_ids
        ):
            raise ValueError("session intelligence components must share one immutable scope")
        return self


__all__ = [
    "AngularOperatingContextMatch",
    "CategoricalOperatingContextMatch",
    "ComparabilityDebt",
    "HistoricalIntelligenceDebt",
    "HypothesisCountereffects",
    "HypothesisLifecycle",
    "HypothesisLifecycleEntry",
    "HypothesisPolicyDimension",
    "HypothesisPolicyIdentity",
    "HypothesisProtocol",
    "HypothesisRepeatPolicyComparison",
    "HypothesisRepeatPolicyDecision",
    "HypothesisTargetEffect",
    "LedgerSetupChange",
    "NumericOperatingContextMatch",
    "OperatingContextAttestation",
    "PairedLapOperatingContext",
    "PositionAlignedEvidence",
    "ProximityOperatingContextMatch",
    "RacingLineContextMatch",
    "RunEvidenceIdentity",
    "SessionEngineeringLedger",
    "SessionEvidenceCitation",
    "SessionIntelligenceBundle",
    "SessionLedgerEntry",
    "SessionPositionEvidenceResult",
]
