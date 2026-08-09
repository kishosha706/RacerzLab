"""Fail-closed cross-run telemetry measurement-health baseline."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from racelab_engine.analysis.channel_registry import canonical_name
from racelab_engine.io.telemetry_manifest import (
    MANIFEST_SCHEMA_VERSION,
    UNIVERSAL_ARCHIVE_VERSION,
    compatibility_fingerprint,
)
from racelab_engine.models.telemetry_health import (
    TelemetryChannelHealthComparison,
    TelemetryChannelHealthSnapshot,
    TelemetryHealthBaselineReport,
    TelemetryHealthFinding,
    TelemetryHealthRecovery,
    TelemetryHealthRunIdentity,
    telemetry_health_session_scope_sha256,
)
from racelab_engine.services.import_service import (
    build_telemetry_capability_payload,
    default_data_dir,
    read_telemetry_manifest,
    telemetry_manifest_path,
)
from racelab_engine.services.session_service import get_session
from racelab_engine.storage.repository import RaceLabRepository


DEFAULT_TELEMETRY_HEALTH_CHANNELS: tuple[str, ...] = (
    "session_time",
    "session_tick",
    "lap_dist_pct",
    "speed_mps",
    "throttle_01",
    "brake_01",
    "steering_rad",
    "rpm",
    "gear",
)

_HEX = frozenset("0123456789abcdef")


@dataclass(frozen=True)
class _LoadedArtifact:
    identity: TelemetryHealthRunIdentity
    manifest: Mapping[str, Any]
    profiles: Mapping[str, TelemetryChannelHealthSnapshot]
    trusted_baseline: bool


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _valid_sha256(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if len(text) == 64 and all(character in _HEX for character in text) else None


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= minimum and number == value else None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finding_id(
    kind: str,
    channel: str,
    current_run_id: str,
    baseline_run_ids: tuple[str, ...],
) -> str:
    payload = json.dumps(
        {
            "kind": kind,
            "channel": channel,
            "current_run_id": current_run_id,
            "baseline_run_ids": baseline_run_ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "telemetry_health_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _recovery(
    action: str,
    run_id: str,
    channel: str | None = None,
) -> TelemetryHealthRecovery:
    if action == "reimport_original_ibt":
        detail = f" and verify {channel}" if channel else ""
        return TelemetryHealthRecovery(
            action="reimport_original_ibt",
            run_id=run_id,
            instruction=(
                f"Re-import the original .ibt for run {run_id}{detail}; the staged archive must "
                "reproduce the same immutable source and a newly verified cache manifest."
            ),
        )
    detail = f" with {channel} enabled" if channel else ""
    return TelemetryHealthRecovery(
        action="record_verification_run",
        run_id=run_id,
        instruction=(
            f"Record one unchanged-setup verification run{detail} in the same saved session; "
            "keep the recording context representative before treating this as a persistent sensor fault."
        ),
    )


def _blocked_report(
    *,
    session_id: str,
    ordered_run_ids: tuple[str, ...],
    current_run_id: str,
    blockers: Iterable[str],
    recovery: Iterable[TelemetryHealthRecovery] = (),
) -> TelemetryHealthBaselineReport:
    scope_sha256 = telemetry_health_session_scope_sha256(session_id, ordered_run_ids)
    recovery_items = tuple(recovery) or (_recovery("reimport_original_ibt", current_run_id),)
    return TelemetryHealthBaselineReport(
        status="blocked",
        session_id=session_id,
        ordered_session_run_ids=ordered_run_ids,
        session_scope_sha256=scope_sha256,
        current_run_id=current_run_id,
        blocker_reasons=_unique(blockers),
        recovery=recovery_items,
    )


def _profile(
    channel: Mapping[str, Any],
    *,
    run_id: str,
    canonical: str,
    manifest_record_count: int,
) -> TelemetryChannelHealthSnapshot:
    raw_name = channel.get("raw_name")
    if not isinstance(raw_name, str) or not raw_name.strip() or raw_name != raw_name.strip():
        raise ValueError("a channel has a missing or malformed raw identity")
    if canonical_name(raw_name) != canonical:
        raise ValueError(f"channel {raw_name} has a mismatched canonical identity")
    archive_status = channel.get("archive_status")
    if archive_status not in {"cached", "metadata_only"}:
        raise ValueError(f"channel {raw_name} has an invalid archive status")
    record_count = _integer(channel.get("record_count"))
    valid_count = _integer(channel.get("valid_record_count"))
    distinct_count = _integer(channel.get("distinct_value_count"))
    if record_count is None or valid_count is None or distinct_count is None:
        raise ValueError(f"channel {raw_name} has malformed sample counts")
    if archive_status == "cached" and record_count != manifest_record_count:
        raise ValueError(f"channel {raw_name} record count does not match its manifest")
    if archive_status == "metadata_only" and record_count != 0:
        raise ValueError(f"metadata-only channel {raw_name} claims archived records")
    if valid_count > record_count:
        raise ValueError(f"channel {raw_name} valid records exceed total records")
    exact_missing = 1.0 - (valid_count / record_count) if record_count else 1.0
    declared_missing = _finite(channel.get("missing_fraction"))
    if declared_missing is None or not 0.0 <= declared_missing <= 1.0:
        raise ValueError(f"channel {raw_name} has malformed missingness")
    if abs(declared_missing - exact_missing) > 1e-6:
        raise ValueError(f"channel {raw_name} missingness conflicts with its sample counts")
    variation = channel.get("variation")
    if variation not in {"varying", "constant", "no_valid_samples", "not_cached"}:
        raise ValueError(f"channel {raw_name} has an invalid variation state")
    observed_min = _finite(channel.get("observed_min"))
    observed_max = _finite(channel.get("observed_max"))
    if (channel.get("observed_min") is not None and observed_min is None) or (
        channel.get("observed_max") is not None and observed_max is None
    ):
        raise ValueError(f"channel {raw_name} has a non-finite observed range")
    if (observed_min is None) != (observed_max is None):
        raise ValueError(f"channel {raw_name} has an incomplete observed range")
    if observed_min is not None and observed_max is not None and observed_min > observed_max:
        raise ValueError(f"channel {raw_name} has an inverted observed range")
    effective_rate = _finite(channel.get("effective_sample_rate_hz"))
    if effective_rate is None or effective_rate <= 0.0:
        raise ValueError(f"channel {raw_name} has an invalid effective sample rate")
    health_status = channel.get("health_status")
    if health_status not in {"healthy", "warning", "not_assessed"}:
        raise ValueError(f"channel {raw_name} has an invalid health state")
    lower_occupancy = _finite(channel.get("lower_bound_occupancy_fraction", 0.0))
    upper_occupancy = _finite(channel.get("upper_bound_occupancy_fraction", 0.0))
    numeric_limit_hits = _integer(channel.get("numeric_limit_hit_count", 0))
    if (
        lower_occupancy is None
        or upper_occupancy is None
        or not 0.0 <= lower_occupancy <= 1.0
        or not 0.0 <= upper_occupancy <= 1.0
        or numeric_limit_hits is None
    ):
        raise ValueError(f"channel {raw_name} has malformed saturation evidence")
    clipping_status = channel.get("clipping_status")
    saturation_status = channel.get("saturation_status")
    if not isinstance(clipping_status, str) or not clipping_status.strip():
        raise ValueError(f"channel {raw_name} has no clipping assessment")
    if not isinstance(saturation_status, str) or not saturation_status.strip():
        raise ValueError(f"channel {raw_name} has no saturation assessment")
    return TelemetryChannelHealthSnapshot(
        run_id=run_id,
        raw_name=raw_name,
        canonical_name=canonical,
        archive_status=archive_status,
        record_count=record_count,
        valid_record_count=valid_count,
        coverage_fraction=1.0 - exact_missing,
        missing_fraction=exact_missing,
        distinct_value_count=distinct_count,
        variation=variation,
        observed_min=observed_min,
        observed_max=observed_max,
        observed_span=(
            observed_max - observed_min
            if observed_min is not None and observed_max is not None
            else None
        ),
        effective_sample_rate_hz=effective_rate,
        health_status=health_status,
        clipping_status=clipping_status,
        saturation_status=saturation_status,
        lower_bound_occupancy_fraction=lower_occupancy,
        upper_bound_occupancy_fraction=upper_occupancy,
        numeric_limit_hit_count=numeric_limit_hits,
    )


def _validate_manifest(
    manifest: Mapping[str, Any],
    *,
    run_id: str,
    source_file_sha256: str,
    requested_channels: frozenset[str],
) -> Mapping[str, TelemetryChannelHealthSnapshot]:
    if manifest.get("run_id") != run_id:
        raise ValueError("telemetry manifest run identity changed during the health read")
    if _valid_sha256(manifest.get("source_file_sha256")) != source_file_sha256:
        raise ValueError("telemetry manifest source identity does not match the stored run")
    if _integer(manifest.get("manifest_schema_version"), minimum=1) != MANIFEST_SCHEMA_VERSION:
        raise ValueError("telemetry manifest schema is not the current exact version")
    if _integer(manifest.get("universal_archive_version"), minimum=1) != UNIVERSAL_ARCHIVE_VERSION:
        raise ValueError("telemetry archive is not the current exact version")
    schema_fingerprint = _valid_sha256(manifest.get("schema_fingerprint"))
    compatibility = _valid_sha256(manifest.get("compatibility_fingerprint"))
    compatibility_identity = manifest.get("compatibility_identity")
    if schema_fingerprint is None or compatibility is None or not isinstance(
        compatibility_identity, dict
    ):
        raise ValueError("telemetry schema or compatibility identity is malformed")
    if compatibility_fingerprint(schema_fingerprint, compatibility_identity) != compatibility:
        raise ValueError("telemetry compatibility fingerprint does not match its manifest identity")
    build_version = compatibility_identity.get("iracing_build_version")
    if not isinstance(build_version, str) or not build_version.strip():
        raise ValueError("iRacing build identity is unavailable")
    record_count = _integer(manifest.get("record_count"), minimum=1)
    telemetry_rate = _finite(manifest.get("telemetry_rate_hz"))
    if record_count is None or telemetry_rate is None or telemetry_rate <= 0.0:
        raise ValueError("telemetry manifest recording dimensions are malformed")
    channels = manifest.get("channels")
    declared_count = _integer(manifest.get("declared_channel_count"))
    cached_count = _integer(manifest.get("cached_channel_count"))
    if (
        not isinstance(channels, list)
        or declared_count is None
        or cached_count is None
        or declared_count != len(channels)
    ):
        raise ValueError("telemetry manifest channel inventory is malformed")
    raw_names: list[str] = []
    actual_cached = 0
    channel_by_canonical: dict[str, Mapping[str, Any]] = {}
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError("telemetry manifest contains a malformed channel entry")
        raw_name = channel.get("raw_name")
        if not isinstance(raw_name, str) or not raw_name.strip() or raw_name != raw_name.strip():
            raise ValueError("telemetry manifest contains a malformed raw channel identity")
        raw_names.append(raw_name)
        mapped = canonical_name(raw_name)
        declared_canonical = channel.get("canonical_name")
        if mapped != declared_canonical:
            raise ValueError(f"channel {raw_name} has a stale canonical mapping")
        if channel.get("archive_status") == "cached":
            actual_cached += 1
        if mapped in requested_channels:
            if mapped in channel_by_canonical:
                raise ValueError(f"critical channel {mapped} is ambiguous in the manifest")
            channel_by_canonical[mapped] = channel
    if len(raw_names) != len(set(raw_names)):
        raise ValueError("telemetry manifest raw channel identities are duplicated")
    if cached_count != actual_cached:
        raise ValueError("telemetry manifest cached-channel count is inconsistent")
    return {
        canonical: _profile(
            channel,
            run_id=run_id,
            canonical=canonical,
            manifest_record_count=record_count,
        )
        for canonical, channel in channel_by_canonical.items()
    }


def _load_artifact(
    run_id: str,
    *,
    session_id: str,
    session_scope_sha256: str,
    repository: RaceLabRepository,
    data_dir: Path,
    requested_channels: frozenset[str],
    baseline: bool,
) -> _LoadedArtifact:
    run = repository.get_session(run_id)
    if run is None or run.run_id != run_id:
        raise ValueError("the stored run record is unavailable or identity-mismatched")
    source_hash = _valid_sha256(run.file_hash)
    if source_hash is None:
        raise ValueError("the stored run source-file hash is missing or malformed")
    path = telemetry_manifest_path(data_dir, run_id)
    if not path.is_file():
        raise ValueError("the telemetry manifest file is missing")
    manifest_sha256_before = _sha256_file(path)
    payload = build_telemetry_capability_payload(
        run_id,
        data_dir,
        expected_source_file_sha256=source_hash,
    )
    manifest_sha256_after = _sha256_file(path)
    if manifest_sha256_before != manifest_sha256_after:
        raise ValueError("the telemetry manifest changed while its health was being read")
    manifest_identity = payload.get("manifest_identity") if isinstance(payload, dict) else None
    if not isinstance(manifest_identity, dict) or manifest_identity.get("status") != "verified":
        reason = (
            str(manifest_identity.get("reason") or "telemetry artifact ownership is unavailable")
            if isinstance(manifest_identity, dict)
            else "telemetry artifact ownership is unavailable"
        )
        raise ValueError(reason)
    cache_hash = _valid_sha256(manifest_identity.get("telemetry_cache_sha256"))
    schema_hash = _valid_sha256(payload.get("schema_fingerprint"))
    compatibility_hash = _valid_sha256(payload.get("compatibility_fingerprint"))
    if cache_hash is None or schema_hash is None or compatibility_hash is None:
        raise ValueError("telemetry cache, schema, or compatibility hash is malformed")
    profiles = _validate_manifest(
        payload,
        run_id=run_id,
        source_file_sha256=source_hash,
        requested_channels=requested_channels,
    )
    compatibility_identity = payload.get("compatibility_identity")
    assert isinstance(compatibility_identity, dict)
    identity = TelemetryHealthRunIdentity(
        session_id=session_id,
        session_scope_sha256=session_scope_sha256,
        run_id=run_id,
        source_file_sha256=source_hash,
        telemetry_cache_sha256=cache_hash,
        manifest_sha256=manifest_sha256_after,
        schema_fingerprint=schema_hash,
        compatibility_fingerprint=compatibility_hash,
        manifest_schema_version=MANIFEST_SCHEMA_VERSION,
        universal_archive_version=UNIVERSAL_ARCHIVE_VERSION,
        iracing_build_version=str(compatibility_identity["iracing_build_version"]),
    )
    cache_compatibility = payload.get("cache_compatibility")
    trusted_baseline = bool(
        payload.get("lossless_archive_complete") is True
        and isinstance(cache_compatibility, dict)
        and cache_compatibility.get("status") == "current"
        and profiles
    )
    if baseline and not trusted_baseline:
        raise ValueError("the prior run is not a complete current lossless telemetry archive")
    return _LoadedArtifact(
        identity=identity,
        manifest=payload,
        profiles=profiles,
        trusted_baseline=trusted_baseline,
    )


def _previously_healthy(profile: TelemetryChannelHealthSnapshot) -> bool:
    return bool(
        profile.archive_status == "cached"
        and profile.health_status == "healthy"
        and profile.coverage_fraction >= 0.999
        and profile.numeric_limit_hit_count == 0
        and profile.clipping_status == "none_detected"
        and profile.variation not in {"no_valid_samples", "not_cached"}
    )


def _finding(
    *,
    kind: str,
    channel: str,
    current: TelemetryChannelHealthSnapshot,
    baselines: tuple[TelemetryChannelHealthSnapshot, ...],
    observation: str,
    recovery_action: str,
) -> TelemetryHealthFinding:
    baseline_ids = tuple(item.run_id for item in baselines)
    raw_names = _unique(
        (current.raw_name, *(item.raw_name for item in baselines))
    )
    return TelemetryHealthFinding(
        finding_id=_finding_id(kind, channel, current.run_id, baseline_ids),
        kind=kind,
        channel=channel,
        current_run_id=current.run_id,
        baseline_run_ids=baseline_ids,
        source_raw_names=raw_names,
        observation=observation,
        recovery=_recovery(recovery_action, current.run_id, current.raw_name),
    )


def _channel_findings(
    channel: str,
    current: TelemetryChannelHealthSnapshot,
    baselines: tuple[TelemetryChannelHealthSnapshot, ...],
) -> tuple[TelemetryHealthFinding, ...]:
    if not all(_previously_healthy(item) for item in baselines):
        return ()
    findings: list[TelemetryHealthFinding] = []
    baseline_max_missing = max(item.missing_fraction for item in baselines)
    if (
        current.archive_status != "cached"
        or current.missing_fraction >= max(0.01, baseline_max_missing + 0.01)
    ):
        findings.append(
            _finding(
                kind="dropout",
                channel=channel,
                current=current,
                baselines=baselines,
                observation=(
                    f"{current.raw_name} coverage fell to {current.coverage_fraction:.3f}; "
                    f"the prior trusted runs were at least "
                    f"{min(item.coverage_fraction for item in baselines):.3f}."
                ),
                recovery_action="reimport_original_ibt",
            )
        )
    if current.variation == "constant" and all(
        item.variation == "varying" for item in baselines
    ):
        findings.append(
            _finding(
                kind="became_constant",
                channel=channel,
                current=current,
                baselines=baselines,
                observation=(
                    f"{current.raw_name} is constant in {current.run_id}; it varied in every "
                    "trusted baseline run. This is a recording-health observation, not a vehicle cause."
                ),
                recovery_action="record_verification_run",
            )
        )
    baseline_clipping_clear = all(
        item.numeric_limit_hit_count == 0
        and item.clipping_status == "none_detected"
        and item.saturation_status in {"none_detected", "normal_control_boundary_occupancy"}
        for item in baselines
    )
    suspicious_saturation = bool(
        current.numeric_limit_hit_count > 0
        or current.clipping_status not in {"none_detected", "not_assessed"}
        or current.saturation_status
        not in {"none_detected", "normal_control_boundary_occupancy", "not_assessed"}
    )
    if baseline_clipping_clear and suspicious_saturation:
        findings.append(
            _finding(
                kind="became_saturated",
                channel=channel,
                current=current,
                baselines=baselines,
                observation=(
                    f"{current.raw_name} now reports clipping or saturation evidence that was absent "
                    "from both trusted baseline runs."
                ),
                recovery_action="reimport_original_ibt",
            )
        )
    baseline_rates = [item.effective_sample_rate_hz for item in baselines]
    if (
        current.effective_sample_rate_hz is not None
        and all(rate is not None for rate in baseline_rates)
        and max(float(rate) for rate in baseline_rates)
        - min(float(rate) for rate in baseline_rates)
        <= 1e-9
        and abs(current.effective_sample_rate_hz - float(baseline_rates[0])) > 1e-9
    ):
        findings.append(
            _finding(
                kind="effective_rate_changed",
                channel=channel,
                current=current,
                baselines=baselines,
                observation=(
                    f"{current.raw_name} effective rate is "
                    f"{current.effective_sample_rate_hz:g} Hz; both trusted baselines report "
                    f"{float(baseline_rates[0]):g} Hz."
                ),
                recovery_action="reimport_original_ibt",
            )
        )
    if (
        current.observed_min is not None
        and current.observed_max is not None
        and all(
            item.observed_min is not None
            and item.observed_max is not None
            and item.variation == "varying"
            for item in baselines
        )
    ):
        baseline_lows = [float(item.observed_min) for item in baselines]
        baseline_highs = [float(item.observed_max) for item in baselines]
        baseline_spans = [high - low for low, high in zip(baseline_lows, baseline_highs, strict=True)]
        typical_span = median(baseline_spans)
        centers = [(low + high) / 2.0 for low, high in zip(baseline_lows, baseline_highs, strict=True)]
        stable_baseline = bool(
            typical_span > 0.0
            and max(centers) - min(centers) <= max(0.25 * typical_span, 1e-9)
        )
        margin = 0.5 * typical_span
        shifted = bool(
            current.observed_min > max(baseline_highs) + margin
            or current.observed_max < min(baseline_lows) - margin
        )
        if stable_baseline and shifted:
            findings.append(
                _finding(
                    kind="range_shifted",
                    channel=channel,
                    current=current,
                    baselines=baselines,
                    observation=(
                        f"{current.raw_name} range [{current.observed_min:g}, "
                        f"{current.observed_max:g}] is separated from the stable trusted-baseline "
                        f"envelope [{min(baseline_lows):g}, {max(baseline_highs):g}]."
                    ),
                    recovery_action="record_verification_run",
                )
            )
    return tuple(findings)


def build_telemetry_health_baseline(
    session_id: str,
    current_run_id: str,
    *,
    expected_run_ids: Sequence[str],
    repository: RaceLabRepository | None = None,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    critical_channels: Sequence[str] = DEFAULT_TELEMETRY_HEALTH_CHANNELS,
) -> TelemetryHealthBaselineReport:
    """Compare one run with the nearest two trusted compatible prior runs.

    The service reads only compact manifests plus the cache hashes required by
    immutable artifact verification.  Incompatible prior runs are ignored;
    malformed or swapped artifacts are never admitted as baseline evidence.
    """

    ordered = tuple(expected_run_ids)
    if (
        not ordered
        or any(
            not isinstance(run_id, str)
            or not run_id.strip()
            or run_id != run_id.strip()
            for run_id in ordered
        )
        or len(set(ordered)) != len(ordered)
        or current_run_id not in ordered
    ):
        raise ValueError("expected telemetry-health session scope must be unique and exact")
    scope_sha256 = telemetry_health_session_scope_sha256(session_id, ordered)
    stored_session = get_session(session_id, db_path=db_path)
    if stored_session is None:
        return _blocked_report(
            session_id=session_id,
            ordered_run_ids=ordered,
            current_run_id=current_run_id,
            blockers=("The exact saved session is unavailable.",),
        )
    if tuple(stored_session.run_ids) != ordered:
        return _blocked_report(
            session_id=session_id,
            ordered_run_ids=ordered,
            current_run_id=current_run_id,
            blockers=(
                "Session membership changed while telemetry health was being assembled; reload the exact session.",
            ),
            recovery=(
                _recovery("record_verification_run", current_run_id),
            ),
        )
    requested = tuple(dict.fromkeys(critical_channels))
    if not requested or any(
        not isinstance(channel, str) or not channel.strip() or channel != channel.strip()
        for channel in requested
    ):
        raise ValueError("critical telemetry-health channels must be unique canonical identities")
    repository = repository or RaceLabRepository(db_path)
    data_root = Path(data_dir) if data_dir is not None else default_data_dir()
    requested_set = frozenset(requested)
    try:
        current = _load_artifact(
            current_run_id,
            session_id=session_id,
            session_scope_sha256=scope_sha256,
            repository=repository,
            data_dir=data_root,
            requested_channels=requested_set,
            baseline=False,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _blocked_report(
            session_id=session_id,
            ordered_run_ids=ordered,
            current_run_id=current_run_id,
            blockers=(f"Current telemetry health is blocked: {exc}.",),
        )
    current_index = ordered.index(current_run_id)
    baseline_artifacts: list[_LoadedArtifact] = []
    rejected: list[tuple[str, str]] = []
    for prior_run_id in reversed(ordered[:current_index]):
        # A raw fingerprint is used only as a cheap rejection filter.  Any run
        # admitted to the baseline is subsequently re-read through full source,
        # cache, manifest, schema, and build verification.
        try:
            raw_manifest = read_telemetry_manifest(prior_run_id, data_root)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            rejected.append((prior_run_id, f"manifest could not be read: {exc}"))
            continue
        if raw_manifest.get("schema_fingerprint") != current.identity.schema_fingerprint:
            continue
        if raw_manifest.get("compatibility_fingerprint") != current.identity.compatibility_fingerprint:
            continue
        try:
            candidate = _load_artifact(
                prior_run_id,
                session_id=session_id,
                session_scope_sha256=scope_sha256,
                repository=repository,
                data_dir=data_root,
                requested_channels=requested_set,
                baseline=True,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            rejected.append((prior_run_id, str(exc)))
            continue
        if (
            candidate.identity.schema_fingerprint != current.identity.schema_fingerprint
            or candidate.identity.compatibility_fingerprint
            != current.identity.compatibility_fingerprint
            or candidate.identity.iracing_build_version != current.identity.iracing_build_version
            or candidate.identity.manifest_schema_version
            != current.identity.manifest_schema_version
            or candidate.identity.universal_archive_version
            != current.identity.universal_archive_version
        ):
            continue
        baseline_artifacts.append(candidate)
        if len(baseline_artifacts) == 2:
            break
    baseline_artifacts.reverse()
    if len(baseline_artifacts) < 2:
        count = len(baseline_artifacts)
        blockers = [
            f"Telemetry health needs two prior trusted compatible runs; {count} is available before {current_run_id}."
        ]
        blockers.extend(
            f"Prior run {run_id} was not admitted: {reason}." for run_id, reason in rejected[:3]
        )
        recovery: list[TelemetryHealthRecovery] = [
            _recovery("record_verification_run", current_run_id)
        ]
        recovery.extend(
            _recovery("reimport_original_ibt", run_id) for run_id, _ in rejected[:2]
        )
        return TelemetryHealthBaselineReport(
            status="insufficient_history",
            session_id=session_id,
            ordered_session_run_ids=ordered,
            session_scope_sha256=scope_sha256,
            current_run_id=current_run_id,
            current_identity=current.identity,
            baseline_identities=tuple(item.identity for item in baseline_artifacts),
            blocker_reasons=_unique(blockers),
            recovery=tuple(recovery),
        )
    comparisons: list[TelemetryChannelHealthComparison] = []
    for channel in requested:
        current_profile = current.profiles.get(channel)
        baseline_profiles = tuple(
            artifact.profiles[channel]
            for artifact in baseline_artifacts
            if channel in artifact.profiles
        )
        if current_profile is None or len(baseline_profiles) != len(baseline_artifacts):
            continue
        findings = _channel_findings(channel, current_profile, baseline_profiles)
        comparisons.append(
            TelemetryChannelHealthComparison(
                channel=channel,
                current=current_profile,
                baselines=baseline_profiles,
                findings=findings,
            )
        )
    if not comparisons:
        return TelemetryHealthBaselineReport(
            status="insufficient_history",
            session_id=session_id,
            ordered_session_run_ids=ordered,
            session_scope_sha256=scope_sha256,
            current_run_id=current_run_id,
            current_identity=current.identity,
            baseline_identities=tuple(item.identity for item in baseline_artifacts),
            blocker_reasons=(
                "No default critical channel has a complete comparable health profile across the exact run cohort.",
            ),
            recovery=(_recovery("record_verification_run", current_run_id),),
        )
    findings = tuple(
        finding for comparison in comparisons for finding in comparison.findings
    )
    return TelemetryHealthBaselineReport(
        status="warning" if findings else "healthy",
        session_id=session_id,
        ordered_session_run_ids=ordered,
        session_scope_sha256=scope_sha256,
        current_run_id=current_run_id,
        current_identity=current.identity,
        baseline_identities=tuple(item.identity for item in baseline_artifacts),
        comparisons=tuple(comparisons),
        findings=findings,
        assessed_channels=tuple(item.channel for item in comparisons),
    )


__all__ = [
    "DEFAULT_TELEMETRY_HEALTH_CHANNELS",
    "build_telemetry_health_baseline",
]
