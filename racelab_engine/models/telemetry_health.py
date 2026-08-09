"""Cross-run telemetry measurement-health contracts.

These models describe changes in the recording itself.  They cannot carry a
vehicle-cause attribution, setup target, calibrated probability, or tuning
authority.  Every comparison is bound to an exact saved session and immutable
source, cache, schema, build, and manifest identities.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class TelemetryHealthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def telemetry_health_session_scope_sha256(
    session_id: str,
    ordered_run_ids: tuple[str, ...] | list[str],
) -> str:
    payload = json.dumps(
        {"session_id": session_id, "ordered_run_ids": list(ordered_run_ids)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TelemetryHealthRecovery(TelemetryHealthModel):
    action: Literal["reimport_original_ibt", "record_verification_run"]
    run_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class TelemetryHealthRunIdentity(TelemetryHealthModel):
    session_id: str = Field(min_length=1)
    session_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(min_length=1)
    source_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    telemetry_cache_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_schema_version: int = Field(ge=1)
    universal_archive_version: int = Field(ge=1)
    iracing_build_version: str = Field(min_length=1)


class TelemetryChannelHealthSnapshot(TelemetryHealthModel):
    run_id: str = Field(min_length=1)
    raw_name: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    archive_status: Literal["cached", "metadata_only"]
    record_count: int = Field(ge=0)
    valid_record_count: int = Field(ge=0)
    coverage_fraction: FiniteFloat = Field(ge=0.0, le=1.0)
    missing_fraction: FiniteFloat = Field(ge=0.0, le=1.0)
    distinct_value_count: int = Field(ge=0)
    variation: Literal["varying", "constant", "no_valid_samples", "not_cached"]
    observed_min: FiniteFloat | None = None
    observed_max: FiniteFloat | None = None
    observed_span: FiniteFloat | None = Field(default=None, ge=0.0)
    effective_sample_rate_hz: FiniteFloat | None = Field(default=None, gt=0.0)
    health_status: Literal["healthy", "warning", "not_assessed"]
    clipping_status: str = Field(min_length=1)
    saturation_status: str = Field(min_length=1)
    lower_bound_occupancy_fraction: FiniteFloat = Field(default=0.0, ge=0.0, le=1.0)
    upper_bound_occupancy_fraction: FiniteFloat = Field(default=0.0, ge=0.0, le=1.0)
    numeric_limit_hit_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def metrics_are_internally_consistent(self) -> TelemetryChannelHealthSnapshot:
        if self.valid_record_count > self.record_count:
            raise ValueError("valid channel records cannot exceed total records")
        if abs((self.coverage_fraction + self.missing_fraction) - 1.0) > 1e-6:
            raise ValueError("channel coverage and missingness must be complementary")
        if (self.observed_min is None) != (self.observed_max is None):
            raise ValueError("numeric channel range requires both bounds")
        if self.observed_min is None:
            if self.observed_span is not None:
                raise ValueError("a range span requires numeric bounds")
        else:
            assert self.observed_max is not None
            if self.observed_min > self.observed_max:
                raise ValueError("observed channel range must be ordered")
            if self.observed_span is None or abs(
                self.observed_span - (self.observed_max - self.observed_min)
            ) > 1e-6:
                raise ValueError("observed span must equal the exact numeric range")
        if self.archive_status == "metadata_only" and (
            self.record_count != 0
            or self.valid_record_count != 0
            or self.variation != "not_cached"
        ):
            raise ValueError("metadata-only channels cannot claim archived samples")
        if self.variation == "varying" and self.distinct_value_count < 2:
            raise ValueError("varying channels require at least two distinct values")
        if self.variation == "constant" and self.distinct_value_count > 1:
            raise ValueError("constant channels cannot claim multiple distinct values")
        return self


TelemetryHealthFindingKind = Literal[
    "dropout",
    "became_constant",
    "became_saturated",
    "range_shifted",
    "effective_rate_changed",
]


class TelemetryHealthFinding(TelemetryHealthModel):
    finding_id: str = Field(min_length=1)
    kind: TelemetryHealthFindingKind
    channel: str = Field(min_length=1)
    current_run_id: str = Field(min_length=1)
    baseline_run_ids: tuple[str, ...] = Field(min_length=2)
    source_raw_names: tuple[str, ...] = Field(min_length=1)
    observation: str = Field(min_length=1)
    recovery: TelemetryHealthRecovery
    authority: Literal["measurement_health_only"] = "measurement_health_only"
    vehicle_cause_attributed: Literal[False] = False
    setup_authorized: Literal[False] = False

    @model_validator(mode="after")
    def evidence_scope_is_exact(self) -> TelemetryHealthFinding:
        if (
            len(set(self.baseline_run_ids)) != len(self.baseline_run_ids)
            or self.current_run_id in self.baseline_run_ids
        ):
            raise ValueError("health findings require distinct current and baseline runs")
        if len(set(self.source_raw_names)) != len(self.source_raw_names):
            raise ValueError("health finding source channels must be unique")
        if self.recovery.run_id != self.current_run_id:
            raise ValueError("health recovery must target the exact current run")
        return self


class TelemetryChannelHealthComparison(TelemetryHealthModel):
    channel: str = Field(min_length=1)
    current: TelemetryChannelHealthSnapshot
    baselines: tuple[TelemetryChannelHealthSnapshot, ...] = Field(min_length=2)
    metrics_compared: tuple[
        Literal["coverage"],
        Literal["range"],
        Literal["variation"],
        Literal["effective_rate"],
        Literal["missingness"],
    ] = ("coverage", "range", "variation", "effective_rate", "missingness")
    findings: tuple[TelemetryHealthFinding, ...] = ()

    @model_validator(mode="after")
    def comparison_scope_is_exact(self) -> TelemetryChannelHealthComparison:
        if self.current.canonical_name != self.channel or any(
            item.canonical_name != self.channel for item in self.baselines
        ):
            raise ValueError("channel comparisons require one canonical channel")
        baseline_ids = [item.run_id for item in self.baselines]
        if (
            len(set(baseline_ids)) != len(baseline_ids)
            or self.current.run_id in baseline_ids
        ):
            raise ValueError("channel comparisons require distinct run identities")
        if any(
            finding.channel != self.channel
            or finding.current_run_id != self.current.run_id
            or finding.baseline_run_ids != tuple(baseline_ids)
            for finding in self.findings
        ):
            raise ValueError("comparison findings must bind to the same channel and runs")
        return self


class TelemetryHealthBaselineReport(TelemetryHealthModel):
    status: Literal["healthy", "warning", "insufficient_history", "blocked"]
    authority: Literal["measurement_health_only"] = "measurement_health_only"
    vehicle_cause_attributed: Literal[False] = False
    setup_authorized: Literal[False] = False
    session_id: str = Field(min_length=1)
    ordered_session_run_ids: tuple[str, ...] = Field(min_length=1)
    session_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_run_id: str = Field(min_length=1)
    required_prior_run_count: Literal[2] = 2
    current_identity: TelemetryHealthRunIdentity | None = None
    baseline_identities: tuple[TelemetryHealthRunIdentity, ...] = ()
    comparisons: tuple[TelemetryChannelHealthComparison, ...] = ()
    findings: tuple[TelemetryHealthFinding, ...] = ()
    assessed_channels: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    recovery: tuple[TelemetryHealthRecovery, ...] = ()

    @model_validator(mode="after")
    def report_status_matches_its_evidence(self) -> TelemetryHealthBaselineReport:
        if (
            len(set(self.ordered_session_run_ids)) != len(self.ordered_session_run_ids)
            or self.current_run_id not in self.ordered_session_run_ids
        ):
            raise ValueError("health baseline requires an exact unique session scope")
        expected_scope = telemetry_health_session_scope_sha256(
            self.session_id,
            self.ordered_session_run_ids,
        )
        if self.session_scope_sha256 != expected_scope:
            raise ValueError("health baseline session scope digest is invalid")
        if len({item.run_id for item in self.baseline_identities}) != len(
            self.baseline_identities
        ):
            raise ValueError("health baseline run identities must be unique")
        if self.current_identity is not None and (
            self.current_identity.run_id != self.current_run_id
            or self.current_identity.session_id != self.session_id
            or self.current_identity.session_scope_sha256 != self.session_scope_sha256
        ):
            raise ValueError("current health identity must match the report scope")
        if any(
            item.session_id != self.session_id
            or item.session_scope_sha256 != self.session_scope_sha256
            or item.run_id == self.current_run_id
            for item in self.baseline_identities
        ):
            raise ValueError("baseline health identities must match the exact session scope")
        comparison_channels = tuple(item.channel for item in self.comparisons)
        if comparison_channels != self.assessed_channels or len(set(comparison_channels)) != len(
            comparison_channels
        ):
            raise ValueError("assessed health channels must equal exact comparisons")
        flattened_findings = tuple(
            finding for comparison in self.comparisons for finding in comparison.findings
        )
        if flattened_findings != self.findings:
            raise ValueError("report findings must equal its per-channel findings")
        if self.status in {"healthy", "warning"}:
            if (
                self.current_identity is None
                or len(self.baseline_identities) < self.required_prior_run_count
                or not self.comparisons
                or self.blocker_reasons
            ):
                raise ValueError("publishable health reports require exact comparison evidence")
            baseline_ids = tuple(item.run_id for item in self.baseline_identities)
            if any(
                tuple(item.run_id for item in comparison.baselines) != baseline_ids
                for comparison in self.comparisons
            ):
                raise ValueError("every health channel must use the exact baseline cohort")
            if self.status == "healthy" and self.findings:
                raise ValueError("healthy telemetry cannot carry health findings")
            if self.status == "warning" and not self.findings:
                raise ValueError("warning telemetry requires at least one health finding")
        elif self.status == "insufficient_history":
            if not self.blocker_reasons or not self.recovery or self.comparisons or self.findings:
                raise ValueError("insufficient history requires recovery and no comparisons")
        else:
            if not self.blocker_reasons or not self.recovery or self.comparisons or self.findings:
                raise ValueError("blocked telemetry health requires recovery and no findings")
        return self


__all__ = [
    "TelemetryChannelHealthComparison",
    "TelemetryChannelHealthSnapshot",
    "TelemetryHealthBaselineReport",
    "TelemetryHealthFinding",
    "TelemetryHealthRecovery",
    "TelemetryHealthRunIdentity",
    "telemetry_health_session_scope_sha256",
]
