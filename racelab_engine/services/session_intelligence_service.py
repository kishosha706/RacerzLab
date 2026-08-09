"""Evidence-bound session ledger and controlled-hypothesis lifecycle.

The ledger reports observations only.  It never assigns a setup cause to an
uncontrolled run transition.  Controlled outcome states are assembled
separately from scored A/B/A2 workflows and their immutable prediction grades.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path
from typing import Any

from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA
from racelab_engine.analysis.channel_registry import canonical_name
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.setup_diff import (
    SETUP_GROUPS,
    SETUP_RAW_PATHS,
    SETUP_VALUE_ALIASES,
    diff_setups,
    setup_controls_comparable,
    unmapped_setup_change_paths,
)
from racelab_engine.analysis.setup_controls import canonical_setup_value_key
from racelab_engine.analysis.test_director import score_test_execution
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session_intelligence import (
    HypothesisCountereffects,
    HypothesisLifecycle,
    HypothesisLifecycleEntry,
    HypothesisPolicyDimension,
    HypothesisPolicyIdentity,
    HypothesisProtocol,
    HypothesisRepeatPolicyComparison,
    HypothesisRepeatPolicyDecision,
    HypothesisTargetEffect,
    LedgerSetupChange,
    PositionAlignedEvidence,
    RunEvidenceIdentity,
    SessionEngineeringLedger,
    SessionEvidenceCitation,
    SessionIntelligenceBundle,
    SessionLedgerEntry,
)
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.engineering_memory_service import (
    build_prediction_contract,
    build_prediction_grade,
    get_prediction_contract,
    get_prediction_grade,
)
from racelab_engine.services.import_service import build_telemetry_capability_payload
from racelab_engine.services.session_service import get_session
from racelab_engine.storage.repository import (
    RaceLabRepository,
    StoredEvidenceIntegrityError,
)

_COMPATIBILITY_KEYS = (
    "driver_user_id",
    "car_id",
    "car_path",
    "car_version",
    "track_id",
    "track_configuration_name",
    "track_version",
    "iracing_build_version",
    "session_type",
)
_HEX_64 = frozenset("0123456789abcdef")
_ACTIONABLE_EVENT_STATES = frozenset({
    EvidenceState.MEASURED,
    EvidenceState.CALCULATED,
    EvidenceState.ESTIMATED_PROXY,
    EvidenceState.OBSERVED_CORRELATION,
    EvidenceState.CONTROLLED_TEST_EFFECT,
})


class SessionScopeChangedError(ValueError):
    """Raised when caller and storage no longer name the same ordered session."""


@dataclass(frozen=True)
class _RunContext:
    run_id: str
    session: Any | None
    laps: tuple[LapSummary, ...]
    eligible: tuple[LapSummary, ...]
    events: tuple[TelemetryEvent, ...]
    setup: SetupSnapshot | None
    manifest: Mapping[str, Any]
    compatibility_identity: Mapping[str, Any]
    evidence_identity: RunEvidenceIdentity | None
    blockers: tuple[str, ...]


def _canonical_json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"), allow_nan=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text if len(text) == 64 and all(char in _HEX_64 for char in text) else None


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _exact_session(
    session_id: str,
    *,
    expected_run_ids: Sequence[str] | None,
    db_path: str | Path | None,
) -> tuple[str, ...]:
    session = get_session(session_id, db_path=db_path)
    if session is None:
        raise ValueError(f"Session {session_id} was not found.")
    ordered = tuple(session.run_ids)
    if (
        any(not isinstance(run_id, str) or not run_id.strip() or run_id != run_id.strip() for run_id in ordered)
        or len(set(ordered)) != len(ordered)
    ):
        raise SessionScopeChangedError("Stored session membership is malformed or duplicated.")
    if expected_run_ids is not None and ordered != tuple(expected_run_ids):
        raise SessionScopeChangedError(
            "Session membership changed while intelligence was being assembled; reload the exact session."
        )
    return ordered


def _session_scope_sha256(session_id: str, ordered_run_ids: Sequence[str]) -> str:
    return _sha256({"session_id": session_id, "ordered_run_ids": list(ordered_run_ids)})


def position_evidence_sha256(evidence: PositionAlignedEvidence) -> str:
    payload = evidence.model_dump(mode="json", exclude={"provenance_sha256"})
    return _sha256(payload)


def _lap_citation(run_id: str, lap_number: int) -> SessionEvidenceCitation:
    return SessionEvidenceCitation(
        kind="lap",
        reference_id=f"{run_id}:{lap_number}",
        run_id=run_id,
        lap_number=lap_number,
    )


def _run_citation(run_id: str) -> SessionEvidenceCitation:
    return SessionEvidenceCitation(kind="run", reference_id=run_id, run_id=run_id)


def _dedupe_citations(
    citations: Iterable[SessionEvidenceCitation],
) -> tuple[SessionEvidenceCitation, ...]:
    seen: set[tuple[str, str, str | None, int | None]] = set()
    result: list[SessionEvidenceCitation] = []
    for citation in citations:
        key = (citation.kind, citation.reference_id, citation.run_id, citation.lap_number)
        if key not in seen:
            seen.add(key)
            result.append(citation)
    return tuple(result)


def _load_run_context(
    run_id: str,
    *,
    repository: RaceLabRepository,
    data_dir: str | Path | None,
) -> _RunContext:
    blockers: list[str] = []
    session = repository.get_session(run_id)
    if session is None or session.run_id != run_id:
        blockers.append("The run record is unavailable or identity-mismatched.")
        return _RunContext(run_id, session, (), (), (), None, {}, {}, None, tuple(blockers))

    try:
        laps = tuple(repository.get_laps(run_id))
        events = tuple(repository.get_events(run_id))
    except StoredEvidenceIntegrityError as exc:
        laps = ()
        events = ()
        blockers.append(str(exc))
    setup = repository.get_setup_snapshot(run_id)
    current_eligible = tuple(eligible_laps(laps))
    if not current_eligible:
        blockers.append("No currently eligible complete flying lap is available.")
    if setup is None or setup.run_id != run_id:
        blockers.append("A complete run-owned setup snapshot is unavailable.")
    if session.setup_passed_tech is not True:
        blockers.append("The setup is not recorded as passing tech inspection.")

    try:
        manifest = build_telemetry_capability_payload(
            run_id,
            data_dir,
            expected_source_file_sha256=session.file_hash,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        manifest = {}
        blockers.append(f"Telemetry artifact provenance could not be read: {exc}.")
    manifest_identity = manifest.get("manifest_identity") if isinstance(manifest, dict) else None
    if not isinstance(manifest_identity, dict) or manifest_identity.get("status") != "verified":
        reason = (
            str((manifest_identity or {}).get("reason") or "Telemetry artifact provenance is unavailable.")
            if isinstance(manifest_identity, dict)
            else "Telemetry artifact provenance is unavailable."
        )
        blockers.append(reason)
    cache_compatibility = manifest.get("cache_compatibility") if isinstance(manifest, dict) else None
    if (
        not isinstance(cache_compatibility, dict)
        or cache_compatibility.get("status") != "current"
    ):
        blockers.append(
            str(
                (cache_compatibility or {}).get("reason")
                or "The telemetry cache does not satisfy the current lossless archive contract."
            )
        )
    compatibility_identity = (
        manifest.get("compatibility_identity") or {} if isinstance(manifest, dict) else {}
    )
    missing = [key for key in _COMPATIBILITY_KEYS if compatibility_identity.get(key) is None]
    if missing:
        blockers.append("Compatibility identity is incomplete: " + ", ".join(missing) + ".")
    compatibility_fingerprint = (
        _valid_sha256(manifest.get("compatibility_fingerprint"))
        if isinstance(manifest, dict)
        else None
    )
    source_hash = _valid_sha256(session.file_hash)
    cache_hash = (
        _valid_sha256(manifest_identity.get("telemetry_cache_sha256"))
        if isinstance(manifest_identity, dict)
        else None
    )
    if compatibility_fingerprint is None:
        blockers.append("The compatibility fingerprint is missing or malformed.")
    if source_hash is None:
        blockers.append("The run source-file hash is missing or malformed.")
    if cache_hash is None:
        blockers.append("The telemetry-cache hash is missing or malformed.")

    evidence_identity = None
    if not blockers and source_hash and cache_hash and compatibility_fingerprint:
        evidence_identity = RunEvidenceIdentity(
            run_id=run_id,
            source_file_sha256=source_hash,
            telemetry_cache_sha256=cache_hash,
            compatibility_fingerprint=compatibility_fingerprint,
            setup_id=setup.setup_id if setup is not None else None,
            eligible_lap_ids=tuple(f"{run_id}:{lap.lap_number}" for lap in current_eligible),
        )
    return _RunContext(
        run_id=run_id,
        session=session,
        laps=laps,
        eligible=current_eligible,
        events=events,
        setup=setup,
        manifest=manifest,
        compatibility_identity=compatibility_identity,
        evidence_identity=evidence_identity,
        blockers=_unique(blockers),
    )


def _contexts_match(baseline: _RunContext, test: _RunContext) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    for key in _COMPATIBILITY_KEYS:
        baseline_value = baseline.compatibility_identity.get(key)
        test_value = test.compatibility_identity.get(key)
        if baseline_value is None or test_value is None:
            blockers.append(f"Compatibility field {key} is unavailable.")
        elif baseline_value != test_value:
            blockers.append(f"Compatibility field {key} changed between runs.")
    return not blockers, _unique(blockers)


def _setup_changes(
    baseline: _RunContext,
    test: _RunContext,
) -> tuple[tuple[LedgerSetupChange, ...], tuple[str, ...]]:
    if baseline.setup is None or test.setup is None:
        return (), ("Complete setup snapshots are required for comparison.",)
    changes = diff_setups(baseline.setup, test.setup)
    blockers: list[str] = []
    if not setup_controls_comparable(baseline.setup, test.setup):
        blockers.append("Setup snapshots do not expose a complete comparable control set.")
    unmapped = unmapped_setup_change_paths(baseline.setup, test.setup, changes)
    if unmapped:
        blockers.append("Unmapped setup values changed: " + ", ".join(unmapped) + ".")
    if len(changes) > 1:
        blockers.append("More than one setup control changed, so this transition is not isolated.")
    public = tuple(
        LedgerSetupChange(
            setup_key=change.setup_key,
            label=change.label,
            baseline_value=change.baseline_value,
            test_value=change.test_value,
            delta=change.delta,
        )
        for change in changes
    )
    return public, _unique(blockers)


def _manifest_citation(context: _RunContext) -> SessionEvidenceCitation:
    return SessionEvidenceCitation(
        kind="manifest",
        reference_id=f"{context.run_id}:{context.evidence_identity.telemetry_cache_sha256}",
        run_id=context.run_id,
    )


def _transition_citations(
    baseline: _RunContext,
    test: _RunContext,
    setup_changes: Sequence[LedgerSetupChange],
) -> list[SessionEvidenceCitation]:
    citations = [
        _run_citation(baseline.run_id),
        _run_citation(test.run_id),
        _manifest_citation(baseline),
        _manifest_citation(test),
    ]
    for context in (baseline, test):
        if context.setup is not None:
            citations.append(
                SessionEvidenceCitation(
                    kind="setup",
                    reference_id=context.setup.setup_id,
                    run_id=context.run_id,
                )
            )
    del setup_changes
    return citations


def _entry_id(kind: str, baseline_run_id: str, test_run_id: str, identity: str) -> str:
    return "ledger_" + _sha256(
        {
            "kind": kind,
            "baseline_run_id": baseline_run_id,
            "test_run_id": test_run_id,
            "identity": identity,
        }
    )[:24]


def _position_evidence_blockers(
    evidence: PositionAlignedEvidence,
    baseline: _RunContext,
    test: _RunContext,
) -> tuple[str, ...]:
    blockers: list[str] = []
    try:
        PositionAlignedEvidence.model_validate(evidence.model_dump(mode="python"))
    except (TypeError, ValueError):
        blockers.append(
            "Position evidence lacks a valid paired fuel, tire, weather, line, and proximity attestation."
        )
    if evidence.baseline_run_id != baseline.run_id or evidence.test_run_id != test.run_id:
        blockers.append("Position evidence does not belong to this exact ordered run pair.")
    if evidence.provenance_sha256 != position_evidence_sha256(evidence):
        blockers.append("Position-evidence provenance hash does not match its immutable payload.")
    baseline_laps = {f"{baseline.run_id}:{lap.lap_number}" for lap in baseline.eligible}
    test_laps = {f"{test.run_id}:{lap.lap_number}" for lap in test.eligible}
    if not set(evidence.baseline_lap_ids) <= baseline_laps:
        blockers.append("Position evidence cites a baseline lap that is no longer eligible.")
    if not set(evidence.test_lap_ids) <= test_laps:
        blockers.append("Position evidence cites a test lap that is no longer eligible.")
    if len(evidence.baseline_lap_ids) < 3 or len(evidence.test_lap_ids) < 3:
        blockers.append("Position evidence requires at least three paired eligible laps per run.")
    if abs(float(evidence.delta_s)) <= float(evidence.empirical_noise_s):
        blockers.append("The position-aligned delta does not exceed paired-lap empirical noise.")
    if evidence.alignment_confidence < 0.8:
        blockers.append("Local physical-position alignment confidence is below 80%.")
    return _unique(blockers)


def _pace_entries(
    baseline: _RunContext,
    test: _RunContext,
    setup_changes: tuple[LedgerSetupChange, ...],
    evidence: Sequence[PositionAlignedEvidence],
) -> list[SessionLedgerEntry]:
    citations = _transition_citations(baseline, test, setup_changes)
    entries: list[SessionLedgerEntry] = []
    if evidence:
        for item in evidence:
            delta = float(item.delta_s)
            if item.empirical_noise_s is not None and abs(delta) <= item.empirical_noise_s:
                continue
            if abs(delta) <= 1e-9:
                continue
            state = "improved" if delta < 0.0 else "regressed"
            item_citations = [
                *citations,
                SessionEvidenceCitation(
                    kind="position_evidence",
                    reference_id=item.evidence_id,
                ),
                *(
                    _lap_citation(baseline.run_id, int(lap_id.rsplit(":", 1)[1]))
                    for lap_id in item.baseline_lap_ids
                ),
                *(
                    _lap_citation(test.run_id, int(lap_id.rsplit(":", 1)[1]))
                    for lap_id in item.test_lap_ids
                ),
            ]
            direction = "lower" if delta < 0 else "higher"
            entries.append(
                SessionLedgerEntry(
                    entry_id=_entry_id("pace", baseline.run_id, test.run_id, item.evidence_id),
                    state=state,
                    observation_kind="pace",
                    baseline_run_id=baseline.run_id,
                    test_run_id=test.run_id,
                    description=(
                        f"Observed position-aligned {item.phase} time was {abs(delta):.4f} s {direction}. "
                        "This does not attribute the change to setup."
                    ),
                    evidence_scope="position_aligned",
                    delta_s=delta,
                    start_pct=item.start_pct,
                    end_pct=item.end_pct,
                    phase=item.phase,
                    setup_changes=setup_changes,
                    citations=_dedupe_citations(item_citations),
                )
            )
        return entries
    return []


def _event_signature(event: TelemetryEvent) -> str | None:
    if (
        not event.valid_for_tuning
        or event.evidence_state not in _ACTIONABLE_EVENT_STATES
        or event.confidence_score <= 0.0
        or bool(event.blocker_reasons)
        or event.lap_number is None
        or not event.source_channels
        or any(
            not channel.strip() or channel != channel.strip()
            for channel in event.source_channels
        )
        or len(set(event.source_channels)) != len(event.source_channels)
        or not event.event_type.strip()
    ):
        return None
    start = _finite(event.lap_pct_start)
    end = _finite(event.lap_pct_end)
    peak = _finite(event.lap_pct_peak)
    window = (
        [round(start, 1), round(end, 1)]
        if start is not None and end is not None and end > start
        else [round(peak, 1), round(peak, 1)] if peak is not None else None
    )
    if window is None:
        return None
    phase = str(event.evidence_json.get("phase") or "").strip().casefold()
    return _canonical_json(
        {
            "event_type": event.event_type.strip().casefold(),
            "event_subtype": (event.event_subtype or "").strip().casefold(),
            "zone_name": (event.zone_name or "").strip().casefold(),
            "phase": phase,
            "window": window,
            "source_channels": sorted(event.source_channels),
        }
    )


def _channel_lineage(channel: str) -> frozenset[str]:
    pending = [channel]
    lineage: set[str] = set()
    while pending:
        current = pending.pop()
        key = str(current).strip()
        folded = key.casefold()
        if not key or folded in lineage:
            continue
        lineage.add(folded)
        mapped = canonical_name(key)
        if mapped:
            lineage.add(mapped.casefold())
        metadata = CHANNEL_METADATA.get(key)
        if isinstance(metadata, dict):
            dependencies = metadata.get("dependencies", ())
            if isinstance(dependencies, (list, tuple)):
                pending.extend(
                    dependency
                    for dependency in dependencies
                    if isinstance(dependency, str)
                )
    return frozenset(lineage)


def _unobservable_event_channels(
    context: _RunContext,
    source_channels: Sequence[str],
) -> tuple[str, ...]:
    profiles = context.manifest.get("channels", ())
    if not isinstance(profiles, list):
        return tuple(source_channels)
    unavailable: list[str] = []
    for source in source_channels:
        lineage = _channel_lineage(source)
        observable = False
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            identities = {
                str(profile.get(key) or "").strip().casefold()
                for key in ("name", "raw_name", "canonical_name", "archive_column")
            }
            if not lineage & identities:
                continue
            record_count = _finite(profile.get("record_count"))
            valid_count = _finite(profile.get("valid_record_count"))
            if (
                profile.get("archive_status") == "cached"
                and profile.get("health_status") == "healthy"
                and record_count is not None
                and valid_count is not None
                and record_count > 0.0
                and valid_count / record_count >= 0.95
            ):
                observable = True
                break
        if not observable:
            unavailable.append(source)
    return _unique(unavailable)


def _event_entries(
    baseline: _RunContext,
    test: _RunContext,
    setup_changes: tuple[LedgerSetupChange, ...],
) -> tuple[list[SessionLedgerEntry], tuple[str, ...]]:
    eligible_baseline = {lap.lap_number for lap in baseline.eligible}
    eligible_test = {lap.lap_number for lap in test.eligible}
    baseline_events: dict[str, list[TelemetryEvent]] = {}
    test_events: dict[str, list[TelemetryEvent]] = {}
    for event, eligible_numbers, target in (
        *((event, eligible_baseline, baseline_events) for event in baseline.events),
        *((event, eligible_test, test_events) for event in test.events),
    ):
        signature = _event_signature(event)
        if signature is not None and event.lap_number in eligible_numbers:
            target.setdefault(signature, []).append(event)

    shared_citations = _transition_citations(baseline, test, setup_changes)
    entries: list[SessionLedgerEntry] = []
    blockers: list[str] = []
    for signature, old_events in baseline_events.items():
        current_events = test_events.get(signature, [])
        representative = old_events[0]
        if not current_events:
            unobservable = _unobservable_event_channels(
                test,
                representative.source_channels,
            )
            if unobservable:
                blockers.append(
                    "A resolved-event claim was withheld because the next run cannot prove "
                    "healthy observable source-channel coverage for: "
                    + ", ".join(unobservable)
                    + "."
                )
                continue
        state = "recurring" if current_events else "resolved"
        kind = "recurring_issue" if current_events else "resolved_issue"
        event_citations = [
            *shared_citations,
            *(
                SessionEvidenceCitation(
                    kind="event",
                    reference_id=event.event_id,
                    run_id=event.run_id,
                )
                for event in (*old_events, *current_events)
            ),
            *(
                _lap_citation(event.run_id, event.lap_number)
                for event in (*old_events, *current_events)
                if event.lap_number is not None
            ),
        ]
        label = representative.event_subtype or representative.event_type
        description = (
            f"The eligible {label} signature recurred at the same physical window."
            if current_events
            else f"The eligible {label} signature was not observed in the next comparable run."
        )
        entries.append(
            SessionLedgerEntry(
                entry_id=_entry_id(kind, baseline.run_id, test.run_id, signature),
                state=state,
                observation_kind=kind,
                baseline_run_id=baseline.run_id,
                test_run_id=test.run_id,
                description=description,
                evidence_scope="event_signature",
                start_pct=representative.lap_pct_start,
                end_pct=representative.lap_pct_end,
                phase=str(representative.evidence_json.get("phase") or "").strip() or None,
                setup_changes=setup_changes,
                citations=_dedupe_citations(event_citations),
            )
        )
    return entries, _unique(blockers)


def build_session_engineering_ledger(
    session_id: str,
    *,
    expected_run_ids: Sequence[str] | None = None,
    position_evidence: Sequence[PositionAlignedEvidence] = (),
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> SessionEngineeringLedger:
    """Build a descriptive ledger against current ordered session membership."""

    ordered = _exact_session(session_id, expected_run_ids=expected_run_ids, db_path=db_path)
    scope_hash = _session_scope_sha256(session_id, ordered)
    repository = RaceLabRepository(db_path)
    contexts = {
        run_id: _load_run_context(run_id, repository=repository, data_dir=data_dir)
        for run_id in ordered
    }
    by_pair: dict[tuple[str, str], list[PositionAlignedEvidence]] = {}
    supplied_blockers: list[str] = []
    for evidence in position_evidence:
        pair = (evidence.baseline_run_id, evidence.test_run_id)
        if pair not in set(pairwise(ordered)):
            supplied_blockers.append(
                f"Position evidence {evidence.evidence_id} does not belong to an adjacent ordered session transition."
            )
            continue
        by_pair.setdefault(pair, []).append(evidence)

    entries: list[SessionLedgerEntry] = []
    report_blockers: list[str] = list(supplied_blockers)
    comparable_transitions = 0
    for baseline_run_id, test_run_id in pairwise(ordered):
        baseline = contexts[baseline_run_id]
        test = contexts[test_run_id]
        changes, setup_blockers = _setup_changes(baseline, test)
        _matched, context_blockers = _contexts_match(baseline, test)
        transition_evidence = tuple(by_pair.get((baseline_run_id, test_run_id), ()))
        position_blockers = tuple(
            reason
            for item in transition_evidence
            for reason in _position_evidence_blockers(item, baseline, test)
        )
        blockers = _unique(
            [*baseline.blockers, *test.blockers, *setup_blockers, *context_blockers, *position_blockers]
        )
        if blockers:
            report_blockers.extend(blockers)
            entries.append(
                SessionLedgerEntry(
                    entry_id=_entry_id("not-comparable", baseline_run_id, test_run_id, "|".join(blockers)),
                    state="not_comparable",
                    observation_kind="comparability",
                    baseline_run_id=baseline_run_id,
                    test_run_id=test_run_id,
                    description="This ordered run transition cannot support an engineering comparison.",
                    evidence_scope="none",
                    setup_changes=changes,
                    blocker_reasons=blockers,
                )
            )
            continue
        comparable_transitions += 1
        if not transition_evidence:
            report_blockers.append(
                "Position-aligned, operating-context-matched pace evidence is unavailable for "
                f"{baseline_run_id} -> {test_run_id}; whole-lap pace change is withheld."
            )
        entries.extend(_pace_entries(baseline, test, changes, transition_evidence))
        event_entries, event_blockers = _event_entries(baseline, test, changes)
        entries.extend(event_entries)
        report_blockers.extend(event_blockers)

    if not ordered:
        status = "blocked"
        report_blockers.append("The session contains no runs.")
    elif len(ordered) == 1:
        status = "limited"
        report_blockers.append("Add another compatible run to build a session transition.")
    elif comparable_transitions == 0:
        status = "blocked"
    elif report_blockers:
        status = "limited"
    else:
        status = "ready"
    return SessionEngineeringLedger(
        session_id=session_id,
        session_scope_sha256=scope_hash,
        status=status,
        ordered_run_ids=ordered,
        run_evidence=tuple(
            context.evidence_identity
            for context in contexts.values()
            if context.evidence_identity is not None
        ),
        entries=tuple(entries),
        blocker_reasons=_unique(report_blockers),
    )


def controlled_hypothesis_fingerprint(
    workflow: ControlledWorkflow,
    compatibility_identity: Mapping[str, Any],
    *,
    source_setup_fingerprint: str | None,
) -> str:
    """Bind one immutable issued protocol instance and all of its provenance.

    This is intentionally more specific than the repeat-policy identity below:
    source-run identity, event identities, and plan wording belong here because
    changing any of them produces a different issued protocol instance.
    """

    card = workflow.packet.primary_test
    context = {key: compatibility_identity.get(key) for key in _COMPATIBILITY_KEYS}
    if card is None:
        semantics: dict[str, Any] = {
            "complaint": workflow.complaint,
            "decision": workflow.packet.decision,
        }
    else:
        semantics = {
            "canonical_symptom": workflow.packet.canonical_symptom,
            "cause_bucket": workflow.packet.primary_cause_bucket,
            "hypothesis": card.hypothesis,
            "control_key": card.control_key,
            "direction_sign": card.direction_sign,
            "current_value": card.current_value,
            "proposed_value_raw": card.proposed_value_raw,
            "target_phase": card.target_phase,
            "expected_mechanism": card.expected_mechanism,
            "success_metrics": card.success_metrics,
            "countereffects": card.countereffects,
            "rollback_rule": card.rollback_rule,
            "keep_rule": card.keep_rule,
            "stop_rule": card.stop_rule,
            "stages": tuple(stage.model_dump(mode="json") for stage in card.stages),
            "evidence_event_ids": card.evidence_event_ids,
        }
    return _sha256(
        {
            "fingerprint_version": "controlled-protocol-instance-v2",
            "workflow_instance": {
                "workflow_id": workflow.workflow_id,
                "created_at": workflow.created_at,
                "analysis_version": workflow.analysis_version,
            },
            "source_scope": {
                "run_id": workflow.source_run_id,
                "setup_fingerprint": _valid_sha256(source_setup_fingerprint),
            },
            "context": context,
            "semantics": semantics,
        }
    )


def setup_snapshot_fingerprint(setup: SetupSnapshot | None) -> str | None:
    if setup is None:
        return None
    payload = setup.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _canonical_policy_number(value: int | float) -> str:
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("setup policy numbers must be finite") from exc
    if not number.is_finite():
        raise ValueError("setup policy numbers must be finite")
    if number == 0:
        return "0"
    return str(number.normalize()).casefold()


def _canonical_policy_position(value: float) -> str:
    # Opportunity windows are produced on a 0.1%-position grid. Six decimal
    # places retain substantially finer physical scope while removing binary
    # float serialization noise from an otherwise identical window.
    return _canonical_policy_number(round(value, 6))


def _canonical_policy_mapping_key(value: Any) -> str:
    return " ".join(str(value).split()).casefold()


def _canonical_policy_value(value: Any) -> Any:
    """Return a representation-stable, JSON-safe policy value.

    Policy identity is semantic rather than serialization identity: harmless
    producer churn such as dictionary-key casing, surrounding whitespace, or
    ``50`` versus ``50.0`` must not make a failed setup policy look new.
    """

    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("number", _canonical_policy_number(value))
    if isinstance(value, str):
        normalized = " ".join(value.split()).casefold()
        return ("text", normalized)
    if isinstance(value, Mapping):
        canonical: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = _canonical_policy_mapping_key(raw_key)
            if not key:
                raise ValueError("setup policy keys must be nonblank")
            child_value = _canonical_policy_value(child)
            if key in canonical:
                raise ValueError("setup policy contains colliding keys after normalization")
            canonical[key] = child_value
        return ("mapping", canonical)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return ("sequence", tuple(_canonical_policy_value(child) for child in value))
    raise ValueError(
        f"unsupported setup policy value type: {type(value).__name__}"
    )


def _setup_policy_identifier(value: Any) -> str:
    return "".join(
        character
        for character in str(value).casefold()
        if character.isalnum()
    )


def _control_alias_identifiers(control_key: str) -> frozenset[str]:
    _group, label = SETUP_GROUPS[control_key]
    values = {
        control_key,
        label,
        *SETUP_VALUE_ALIASES.get(control_key, ()),
    }
    for suffix in ("_n_per_mm", "_percent", "_deg", "_mm"):
        if control_key.endswith(suffix):
            values.add(control_key[: -len(suffix)])
    return frozenset(_setup_policy_identifier(value) for value in values)


_SETUP_CONTROL_ALIAS_IDENTIFIERS: dict[str, frozenset[str]] = {
    control_key: _control_alias_identifiers(control_key)
    for control_key in SETUP_GROUPS
}
_SETUP_CONTROL_RAW_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    control_key: tuple(
        tuple(_setup_policy_identifier(part) for part in path.split("."))
        for path in SETUP_RAW_PATHS.get(control_key, ())
    )
    for control_key in SETUP_GROUPS
}
_SETUP_NAME_IDENTIFIERS = frozenset({"name", "setupname"})
_DERIVED_SETUP_METADATA_IDENTIFIERS = frozenset({"rawsource"})


def _setup_control_for_policy_path(path: tuple[str, ...]) -> str | None:
    normalized_path = tuple(_setup_policy_identifier(part) for part in path)
    leaf = normalized_path[-1] if normalized_path else ""
    matches: set[str] = set()
    for control_key, aliases in _SETUP_CONTROL_ALIAS_IDENTIFIERS.items():
        if leaf in aliases:
            matches.add(control_key)
        for raw_path in _SETUP_CONTROL_RAW_PATHS[control_key]:
            if len(normalized_path) >= len(raw_path) and normalized_path[-len(raw_path) :] == raw_path:
                matches.add(control_key)
    if len(matches) > 1:
        raise ValueError(
            "setup policy source path maps to multiple known controls: "
            + ".".join(path)
        )
    return next(iter(matches), None)


def _record_setup_policy_control(
    controls: dict[str, str],
    control_key: str,
    value: Any,
    *,
    source_path: tuple[str, ...] = (),
) -> None:
    if value is None:
        return
    if isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    ):
        raise ValueError(f"setup policy control {control_key} must be scalar")
    semantic_value = value
    if (
        control_key == "steering_ratio"
        and source_path
        and _setup_policy_identifier(source_path[-1])
        in {"steeringpinion", "steeringpinionmm"}
    ):
        represented = str(value).casefold()
        if "mm/rev" not in represented:
            semantic_value = f"{value} mm/rev"
    canonical_value = canonical_setup_value_key(control_key, semantic_value)
    existing = controls.get(control_key)
    if existing is not None and existing != canonical_value:
        raise ValueError(
            f"setup policy contains conflicting semantic values for {control_key}"
        )
    controls[control_key] = canonical_value


def _prune_known_setup_policy_leaves(
    value: Any,
    controls: dict[str, str],
    *,
    path: tuple[str, ...] = (),
) -> Any:
    if isinstance(value, Mapping):
        pruned: dict[str, Any] = {}
        normalized_keys: set[str] = set()
        for raw_key, child in value.items():
            normalized_key = _canonical_policy_mapping_key(raw_key)
            if not normalized_key:
                raise ValueError("setup policy keys must be nonblank")
            if normalized_key in normalized_keys:
                raise ValueError("setup policy contains colliding keys after normalization")
            normalized_keys.add(normalized_key)
            child_path = (*path, str(raw_key))
            identifier = _setup_policy_identifier(raw_key)
            # Only the root setup display name is non-material metadata. A
            # nested field named ``Name`` may identify a material option (for
            # example a tire compound) and must remain in the semantic policy.
            if not path and identifier in _SETUP_NAME_IDENTIFIERS:
                continue
            if not isinstance(child, Mapping) and not (
                isinstance(child, Sequence)
                and not isinstance(child, (str, bytes, bytearray))
            ):
                control_key = _setup_control_for_policy_path(child_path)
                if control_key is not None:
                    _record_setup_policy_control(
                        controls,
                        control_key,
                        child,
                        source_path=child_path,
                    )
                    continue
            pruned_child = _prune_known_setup_policy_leaves(
                child,
                controls,
                path=child_path,
            )
            if isinstance(pruned_child, Mapping) and not pruned_child:
                continue
            pruned[str(raw_key)] = pruned_child
        return pruned
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(
            _prune_known_setup_policy_leaves(child, controls, path=path)
            for child in value
        )
    return value


def _collect_derived_setup_policy_controls(
    value: Any,
    controls: dict[str, str],
    *,
    path: tuple[str, ...] = (),
) -> tuple[str, ...]:
    unknown: list[str] = []
    if isinstance(value, Mapping):
        normalized_keys: set[str] = set()
        for raw_key, child in value.items():
            normalized_key = _canonical_policy_mapping_key(raw_key)
            if not normalized_key:
                raise ValueError("setup policy keys must be nonblank")
            if normalized_key in normalized_keys:
                raise ValueError("setup policy contains colliding keys after normalization")
            normalized_keys.add(normalized_key)
            child_path = (*path, str(raw_key))
            identifier = _setup_policy_identifier(raw_key)
            # Derived producer metadata is ignored only at the document root.
            # Reusing one of these labels inside a setup section cannot hide a
            # material value from exact-session repeat memory.
            if not path and identifier in (
                _SETUP_NAME_IDENTIFIERS | _DERIVED_SETUP_METADATA_IDENTIFIERS
            ):
                continue
            if not isinstance(child, Mapping) and not (
                isinstance(child, Sequence)
                and not isinstance(child, (str, bytes, bytearray))
            ):
                control_key = _setup_control_for_policy_path(child_path)
                if control_key is not None:
                    _record_setup_policy_control(
                        controls,
                        control_key,
                        child,
                        source_path=child_path,
                    )
                elif child is not None:
                    unknown.append(".".join(child_path))
                continue
            unknown.extend(
                _collect_derived_setup_policy_controls(
                    child,
                    controls,
                    path=child_path,
                )
            )
        return tuple(unknown)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            unknown.extend(
                _collect_derived_setup_policy_controls(
                    child,
                    controls,
                    path=(*path, str(index)),
                )
            )
        return tuple(unknown)
    if value is not None:
        unknown.append(".".join(path) or "<root>")
    return tuple(unknown)


def setup_policy_fingerprint(setup: SetupSnapshot | None) -> str | None:
    """Hash material setup configuration without run/name identity churn."""

    if setup is None:
        return None
    canonical_controls: dict[str, str] = {}
    for control_key in SETUP_GROUPS:
        _record_setup_policy_control(
            canonical_controls,
            control_key,
            getattr(setup, control_key, None),
        )
    material_raw_setup = _prune_known_setup_policy_leaves(
        setup.setup_json,
        canonical_controls,
    )
    unknown_derived = _collect_derived_setup_policy_controls(
        setup.extracted_values,
        canonical_controls,
    )
    if not setup.setup_json and unknown_derived:
        raise ValueError(
            "setup policy cannot verify derived-only material setup fields without raw setup: "
            + ", ".join(sorted(set(unknown_derived)))
        )
    return _sha256(
        {
            "setup_policy_version": "semantic-setup-v3",
            "canonical_controls": dict(sorted(canonical_controls.items())),
            "unmapped_raw_setup": _canonical_policy_value(material_raw_setup),
        }
    )


def _normalized_policy_text(value: Any, *, label: str) -> str:
    normalized = " ".join(str(value or "").split()).casefold()
    if not normalized:
        raise ValueError(f"{label} is required for an exact hypothesis policy identity")
    return normalized


def controlled_hypothesis_policy_identity(
    workflow: ControlledWorkflow,
    compatibility_identity: Mapping[str, Any],
    *,
    source_setup: SetupSnapshot | None,
    prediction_contract: Any | None = None,
) -> HypothesisPolicyIdentity:
    """Build the stable, exact-context identity used by Undo repeat memory.

    Producer-owned categorical values are normalized exactly (case and
    whitespace only). No prose similarity, probability, or cross-session
    transfer is inferred.
    """

    card = workflow.packet.primary_test
    if card is None or workflow.packet.decision != "test":
        raise ValueError("only a controlled-test card can have a repeat-policy identity")
    if source_setup is None:
        raise ValueError("an exact source setup is required for repeat-policy identity")
    setup_sha256 = setup_policy_fingerprint(source_setup)
    if setup_sha256 is None:
        raise ValueError("an exact source setup fingerprint is required")
    contract = prediction_contract or build_prediction_contract(workflow)
    if (
        contract.workflow_id != workflow.workflow_id
        or contract.source_run_id != workflow.source_run_id
    ):
        raise ValueError("prediction contract must belong to this exact workflow instance")
    context = {key: compatibility_identity.get(key) for key in _COMPATIBILITY_KEYS}
    if any(value is None or (isinstance(value, str) and not value.strip()) for value in context.values()):
        raise ValueError("complete compatibility identity is required for repeat-policy identity")
    canonical_context = {
        key: _canonical_policy_value(value)
        for key, value in context.items()
    }
    opportunity = workflow.packet.opportunity
    target_start_pct = _finite(opportunity.start_pct)
    target_end_pct = _finite(opportunity.end_pct)
    if (
        target_start_pct is None
        or target_end_pct is None
        or not 0.0 <= target_start_pct < target_end_pct <= 100.0
    ):
        raise ValueError(
            "an exact non-zero physical target window is required for repeat-policy identity"
        )
    target_scope_sha256 = _sha256(
        {
            "scope_version": "lap-position-window-v1",
            "start_pct": _canonical_policy_position(target_start_pct),
            "end_pct": _canonical_policy_position(target_end_pct),
        }
    )
    countereffects = tuple(
        sorted(
            {
                _normalized_policy_text(value, label="countereffect criterion")
                for value in card.countereffects
            }
        )
    )
    return HypothesisPolicyIdentity.build(
        context_sha256=_sha256(canonical_context),
        setup_sha256=setup_sha256,
        target_scope_sha256=target_scope_sha256,
        proposed_control_value_sha256=_sha256(
            canonical_setup_value_key(card.control_key, card.proposed_value_raw)
        ),
        canonical_symptom=_normalized_policy_text(
            workflow.packet.canonical_symptom,
            label="canonical symptom",
        ),
        cause_bucket=_normalized_policy_text(
            workflow.packet.primary_cause_bucket,
            label="cause bucket",
        ),
        control_key=_normalized_policy_text(card.control_key, label="control key"),
        control_direction_sign=card.direction_sign,
        expected_effect_direction=contract.expected_direction,
        target_metric=_normalized_policy_text(contract.target_metric, label="target metric"),
        target_phase=_normalized_policy_text(contract.target_phase, label="target phase"),
        countereffects=countereffects,
    )


_POLICY_DIMENSION_ORDER: tuple[HypothesisPolicyDimension, ...] = (
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


def _changed_policy_dimensions(
    candidate: HypothesisPolicyIdentity,
    previous: HypothesisPolicyIdentity,
) -> tuple[HypothesisPolicyDimension, ...]:
    changed: set[HypothesisPolicyDimension] = set()
    if candidate.context_sha256 != previous.context_sha256:
        changed.add("context")
    if (
        candidate.setup_sha256 != previous.setup_sha256
        or candidate.proposed_control_value_sha256
        != previous.proposed_control_value_sha256
    ):
        changed.add("setup")
    if candidate.target_scope_sha256 != previous.target_scope_sha256:
        changed.add("location")
    if candidate.canonical_symptom != previous.canonical_symptom:
        changed.add("symptom")
    if candidate.cause_bucket != previous.cause_bucket:
        changed.add("cause")
    if candidate.control_key != previous.control_key:
        changed.add("control")
    if (
        candidate.control_direction_sign != previous.control_direction_sign
        or candidate.expected_effect_direction != previous.expected_effect_direction
    ):
        changed.add("direction")
    if candidate.target_metric != previous.target_metric:
        changed.add("metric")
    if candidate.target_phase != previous.target_phase:
        changed.add("phase")
    if candidate.countereffects != previous.countereffects:
        changed.add("countereffects")
    return tuple(dimension for dimension in _POLICY_DIMENSION_ORDER if dimension in changed)


def evaluate_hypothesis_repeat(
    lifecycle: HypothesisLifecycle,
    candidate: HypothesisPolicyIdentity | str,
) -> HypothesisRepeatPolicyDecision:
    """Evaluate exact-session Undo memory without granting setup authority."""

    if isinstance(candidate, str):
        candidate_key = _valid_sha256(candidate)
        if candidate_key is None:
            raise ValueError("candidate repeat-policy identity must be a valid SHA-256 value")
        comparisons: list[HypothesisRepeatPolicyComparison] = []
        for entry in lifecycle.entries:
            if entry.lifecycle_state != "do_not_repeat":
                continue
            policy_key = (
                entry.hypothesis_policy.policy_key
                if entry.hypothesis_policy is not None
                else entry.hypothesis_fingerprint
            )
            if candidate_key in {policy_key, entry.hypothesis_fingerprint}:
                comparisons.append(
                    HypothesisRepeatPolicyComparison(
                        workflow_id=entry.workflow_id,
                        hypothesis_policy_key=policy_key,
                    )
                )
        matched = tuple(comparison.workflow_id for comparison in comparisons)
        return HypothesisRepeatPolicyDecision(
            status="blocked" if matched else "allowed",
            allowed=not matched,
            candidate_policy_key=candidate_key,
            matched_workflow_ids=matched,
            comparisons=tuple(comparisons),
            changed_dimensions=(),
            reason=(
                "A valid exact-session Undo result blocks this exact policy identity."
                if matched
                else "No exact blocked policy identity matched; changed dimensions are unavailable from a hash-only check."
            ),
        )

    comparisons = tuple(
        HypothesisRepeatPolicyComparison(
            workflow_id=entry.workflow_id,
            hypothesis_policy_key=entry.hypothesis_policy.policy_key,
            changed_dimensions=_changed_policy_dimensions(
                candidate,
                entry.hypothesis_policy,
            ),
        )
        for entry in lifecycle.entries
        if entry.lifecycle_state == "do_not_repeat"
        and entry.hypothesis_policy is not None
    )
    matched = tuple(
        comparison.workflow_id
        for comparison in comparisons
        if not comparison.changed_dimensions
    )
    changed_dimensions = () if matched else tuple(
        dimension
        for dimension in _POLICY_DIMENSION_ORDER
        if any(dimension in comparison.changed_dimensions for comparison in comparisons)
    )
    return HypothesisRepeatPolicyDecision(
        status="blocked" if matched else "allowed",
        allowed=not matched,
        candidate_policy_key=candidate.policy_key,
        matched_workflow_ids=matched,
        comparisons=comparisons,
        changed_dimensions=changed_dimensions,
        reason=(
            "A valid exact-session Undo result blocks this unchanged hypothesis policy."
            if matched
            else (
                "The hypothesis policy changed in an exact material dimension and may be tested as a new controlled hypothesis."
                if comparisons
                else "No valid exact-session Undo policy exists for this hypothesis."
            )
        ),
    )


def _stage_binding_hash(workflow: ControlledWorkflow) -> str:
    payload = {
        "stage_run_ids": workflow.stage_run_ids,
        "stage_eligible_lap_numbers": workflow.stage_eligible_lap_numbers,
        "recording_chronology": workflow.reproduction_snapshot.get("recording_chronology", {}),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _plan_binding_hash(workflow: ControlledWorkflow) -> str | None:
    context = workflow.reproduction_snapshot.get("decision_context")
    if not isinstance(context, dict):
        return None
    payload = {
        "source_run_id": workflow.source_run_id,
        "complaint": workflow.complaint,
        "decision_context": context,
        "packet": workflow.packet.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _workflow_validation_blockers(
    workflow: ControlledWorkflow,
    *,
    ordered_run_ids: Sequence[str],
    contexts: Mapping[str, _RunContext],
    repository: RaceLabRepository,
    db_path: str | Path | None,
) -> tuple[tuple[str, ...], Any | None, Any | None]:
    blockers: list[str] = []
    card = workflow.packet.primary_test
    execution = workflow.execution
    quality = workflow.quality
    stage_order = ("A", "B", "A2")
    if workflow.status != "scored":
        blockers.append("Only scored controlled workflows can enter hypothesis history.")
    if card is None or workflow.packet.decision != "test":
        blockers.append("The scored workflow has no complete controlled-test card.")
    if execution is None or quality is None:
        blockers.append("The scored workflow has no complete execution and quality certificate.")
    if tuple(workflow.stage_run_ids) != stage_order:
        blockers.append("The workflow does not contain the exact A/B/A2 stage order.")
    stage_ids = tuple(workflow.stage_run_ids.get(stage) for stage in stage_order)
    if any(not run_id for run_id in stage_ids) or len(set(stage_ids)) != 3:
        blockers.append("A/B/A2 stage run identities are missing or reused.")
    workflow_runs = {workflow.source_run_id, *(run_id for run_id in stage_ids if run_id)}
    scope = set(ordered_run_ids)
    if not workflow_runs <= scope:
        blockers.append("A workflow source or stage run is no longer a member of this exact session.")

    source = contexts.get(workflow.source_run_id)
    if source is None:
        blockers.append("The workflow source run is unavailable in this exact session.")
    else:
        blockers.extend(source.blockers)
    for stage, run_id in zip(stage_order, stage_ids):
        context = contexts.get(str(run_id)) if run_id else None
        if context is None:
            blockers.append(f"Stage {stage} is unavailable in this exact session.")
            continue
        blockers.extend(context.blockers)
        if source is not None:
            _matched, mismatch = _contexts_match(source, context)
            blockers.extend(mismatch)
        stored_laps = tuple(workflow.stage_eligible_lap_numbers.get(stage, ()))
        current_laps = {lap.lap_number for lap in context.eligible}
        if not stored_laps or any(lap_number not in current_laps for lap_number in stored_laps):
            blockers.append(f"Stage {stage} cites a lap that is no longer eligible.")
        if execution is not None:
            expected_count = {
                "A": execution.eligible_laps_a,
                "B": execution.eligible_laps_b,
                "A2": execution.eligible_laps_a2,
            }[stage]
            if expected_count != len(stored_laps):
                blockers.append(f"Stage {stage} lap count conflicts with the execution certificate.")

    if card is not None and source is not None and source.setup is not None:
        for stage, run_id in zip(stage_order, stage_ids):
            context = contexts.get(str(run_id)) if run_id else None
            if context is None or context.setup is None:
                continue
            changes = diff_setups(source.setup, context.setup)
            if (
                not setup_controls_comparable(source.setup, context.setup)
                or unmapped_setup_change_paths(source.setup, context.setup, changes)
            ):
                blockers.append(f"Stage {stage} setup isolation is incomplete or unmapped.")
                continue
            allowed = 1 if stage == "B" else 0
            if len(changes) != allowed or (
                stage == "B" and (not changes or changes[0].setup_key != card.control_key)
            ):
                blockers.append(f"Stage {stage} does not preserve the one-change setup protocol.")

    if execution is not None and quality is not None:
        if card is not None and execution.control_key != card.control_key:
            blockers.append("The execution certificate names a different setup control.")
        if score_test_execution(execution) != quality:
            blockers.append("The stored quality verdict does not match the scored execution.")
        if not quality.protocol_valid or quality.verdict == "invalid":
            blockers.extend(quality.blockers or ("The controlled-test protocol is invalid.",))

    stored_plan_hash = _valid_sha256(workflow.reproduction_snapshot.get("plan_binding_sha256"))
    expected_plan_hash = _plan_binding_hash(workflow)
    if stored_plan_hash is None or expected_plan_hash is None or stored_plan_hash != expected_plan_hash:
        blockers.append("The immutable workflow plan binding failed provenance validation.")
    stored_stage_hash = _valid_sha256(workflow.reproduction_snapshot.get("stage_binding_sha256"))
    if stored_stage_hash is None or stored_stage_hash != _stage_binding_hash(workflow):
        blockers.append("The immutable stage/cohort binding failed provenance validation.")

    reproduction_stages = workflow.reproduction_snapshot.get("stages")
    if not isinstance(reproduction_stages, dict) or set(reproduction_stages) != set(stage_order):
        blockers.append("The scored workflow reproduction stages are missing or malformed.")
    else:
        for stage, run_id in zip(stage_order, stage_ids):
            context = contexts.get(str(run_id)) if run_id else None
            stored = reproduction_stages.get(stage)
            if context is None or not isinstance(stored, dict):
                continue
            expected_setup = context.setup.model_dump(mode="json") if context.setup is not None else None
            expected = {
                "run_id": run_id,
                "source_file_sha256": context.session.file_hash if context.session else None,
                "schema_fingerprint": context.manifest.get("schema_fingerprint"),
                "cache_version": context.manifest.get("cache_version"),
                "compatibility_identity": dict(context.compatibility_identity),
                "setup_fingerprint": setup_snapshot_fingerprint(context.setup),
                "setup_values": expected_setup,
                "eligible_lap_numbers": list(workflow.stage_eligible_lap_numbers.get(stage, ())),
            }
            if stored != expected:
                blockers.append(f"Stage {stage} reproduction provenance no longer matches bound evidence.")

    if card is not None and source is not None:
        source_event_ids = {event.event_id for event in source.events if event.valid_for_tuning}
        if not card.evidence_event_ids or not set(card.evidence_event_ids) <= source_event_ids:
            blockers.append("The controlled hypothesis cites source events that are no longer tuning-valid.")

    contract = None
    grade = None
    try:
        contract = get_prediction_contract(workflow.workflow_id, db_path=db_path)
        grade = get_prediction_grade(workflow.workflow_id, db_path=db_path)
    except (TypeError, ValueError):
        blockers.append("The prediction contract or grade is malformed.")
    if contract is None or grade is None:
        blockers.append("An immutable prediction contract and grade are required.")
    else:
        try:
            expected_contract = build_prediction_contract(workflow)
            expected_grade = build_prediction_grade(workflow, contract)
        except (TypeError, ValueError):
            blockers.append("The prediction contract cannot be rebuilt from this exact workflow.")
        else:
            if contract != expected_contract:
                blockers.append("The prediction contract no longer matches the immutable workflow plan.")
            if grade != expected_grade:
                blockers.append("The prediction grade hash or outcome provenance does not match the workflow.")
    del repository
    return _unique(blockers), contract, grade


def _hypothesis_citations(
    workflow: ControlledWorkflow,
    contexts: Mapping[str, _RunContext],
    contract: Any | None,
    grade: Any | None,
) -> tuple[SessionEvidenceCitation, ...]:
    citations: list[SessionEvidenceCitation] = [
        SessionEvidenceCitation(kind="workflow", reference_id=workflow.workflow_id),
    ]
    for run_id in dict.fromkeys([workflow.source_run_id, *workflow.stage_run_ids.values()]):
        if run_id in contexts:
            citations.append(_run_citation(run_id))
            context = contexts[run_id]
            if context.evidence_identity is not None:
                citations.append(_manifest_citation(context))
            if context.setup is not None:
                citations.append(
                    SessionEvidenceCitation(
                        kind="setup", reference_id=context.setup.setup_id, run_id=run_id
                    )
                )
    for stage, run_id in workflow.stage_run_ids.items():
        for lap_number in workflow.stage_eligible_lap_numbers.get(stage, ()):
            context = contexts.get(run_id)
            if context is not None and lap_number in {lap.lap_number for lap in context.eligible}:
                citations.append(_lap_citation(run_id, lap_number))
    source = contexts.get(workflow.source_run_id)
    valid_event_ids = {
        event.event_id for event in source.events if event.valid_for_tuning
    } if source is not None else set()
    for event_id in workflow.packet.opportunity.evidence_event_ids:
        if event_id in valid_event_ids:
            citations.append(
                SessionEvidenceCitation(
                    kind="event", reference_id=event_id, run_id=workflow.source_run_id
                )
            )
    if contract is not None:
        citations.append(
            SessionEvidenceCitation(
                kind="prediction_contract", reference_id=contract.contract_id
            )
        )
    if grade is not None:
        citations.append(
            SessionEvidenceCitation(kind="prediction_grade", reference_id=grade.grade_id)
        )
    return _dedupe_citations(citations)


def _invalid_target(workflow: ControlledWorkflow) -> HypothesisTargetEffect:
    card = workflow.packet.primary_test
    return HypothesisTargetEffect(
        metric="target_phase_time_s",
        phase=card.target_phase if card is not None else workflow.packet.opportunity.phase or "unavailable",
        expected_direction=None,
        expected_range_s=None,
        actual_effect_s=None,
        actual_direction="unavailable",
        direction_result="unavailable",
        range_result="unavailable",
    )


def _lifecycle_entry(
    workflow: ControlledWorkflow,
    *,
    ordered_run_ids: Sequence[str],
    contexts: Mapping[str, _RunContext],
    repository: RaceLabRepository,
    db_path: str | Path | None,
) -> HypothesisLifecycleEntry:
    blockers, contract, grade = _workflow_validation_blockers(
        workflow,
        ordered_run_ids=ordered_run_ids,
        contexts=contexts,
        repository=repository,
        db_path=db_path,
    )
    card = workflow.packet.primary_test
    source_identity = (
        contexts[workflow.source_run_id].compatibility_identity
        if workflow.source_run_id in contexts
        else {}
    )
    source_setup_fingerprint = (
        setup_snapshot_fingerprint(contexts[workflow.source_run_id].setup)
        if workflow.source_run_id in contexts
        else None
    )
    fingerprint = controlled_hypothesis_fingerprint(
        workflow,
        source_identity,
        source_setup_fingerprint=source_setup_fingerprint,
    )
    hypothesis_policy: HypothesisPolicyIdentity | None = None
    if contract is not None:
        try:
            hypothesis_policy = controlled_hypothesis_policy_identity(
                workflow,
                source_identity,
                source_setup=(
                    contexts[workflow.source_run_id].setup
                    if workflow.source_run_id in contexts
                    else None
                ),
                prediction_contract=contract,
            )
        except ValueError as exc:
            blockers = _unique((*blockers, str(exc)))
    execution = workflow.execution
    quality = workflow.quality
    citations = _hypothesis_citations(
        workflow,
        contexts,
        contract if not blockers else None,
        grade if not blockers else None,
    )

    if blockers or contract is None or grade is None or execution is None or quality is None:
        outcome = "invalid"
        state = "invalid"
        target = _invalid_target(workflow)
        protocol_valid = False
        verdict = "invalid"
        evidence_score = float(quality.score) if quality is not None else 0.0
        policy = False
        policy_reason = None
    else:
        target = HypothesisTargetEffect(
            metric=contract.target_metric,
            phase=contract.target_phase,
            expected_direction=contract.expected_direction,
            expected_range_s=contract.expected_range_s,
            actual_effect_s=grade.actual_effect_s,
            actual_direction=grade.actual_direction,
            direction_result=grade.direction_result,
            range_result=grade.range_result,
        )
        protocol_valid = True
        verdict = quality.verdict
        evidence_score = float(quality.score)
        policy = False
        policy_reason = None
        if grade.direction_result == "matched":
            outcome = "supported"
        elif grade.direction_result == "missed":
            outcome = "contradicted"
        else:
            outcome = "inconclusive"
        if quality.verdict == "undo":
            state = "do_not_repeat"
            policy = True
            policy_reason = (
                "This exact context, setup target, target effect, countereffects, and A/B/A2 "
                "protocol produced a valid Undo policy result. The target-direction outcome is "
                "recorded separately for cause reasoning; materially change the policy or context "
                "before testing this control again."
            )
        else:
            state = outcome

    observed_metrics: dict[str, float] = {}
    if execution is not None:
        for prefix, values in (
            ("countereffect_noise", execution.countereffect_noise_by_phase_s),
            ("guardrail", execution.control_guardrail_metrics),
        ):
            for key, value in values.items():
                number = _finite(value)
                if number is not None:
                    observed_metrics[f"{prefix}:{key}"] = number
    eligible_lap_ids = tuple(
        f"{run_id}:{lap_number}"
        for stage, run_id in workflow.stage_run_ids.items()
        for lap_number in workflow.stage_eligible_lap_numbers.get(stage, ())
        if run_id in contexts
        and lap_number in {lap.lap_number for lap in contexts[run_id].eligible}
    )
    protocol = HypothesisProtocol(
        source_run_id=workflow.source_run_id,
        a_run_id=workflow.stage_run_ids.get("A"),
        b_run_id=workflow.stage_run_ids.get("B"),
        a2_run_id=workflow.stage_run_ids.get("A2"),
        eligible_lap_ids=eligible_lap_ids,
        protocol_valid=protocol_valid,
        evidence_score=evidence_score,
        verdict=verdict,
        blocker_reasons=blockers if not protocol_valid else (),
    )
    return HypothesisLifecycleEntry(
        workflow_id=workflow.workflow_id,
        hypothesis_fingerprint=fingerprint,
        protocol_fingerprint=fingerprint,
        hypothesis_policy=hypothesis_policy,
        lifecycle_state=state,
        outcome_classification=outcome,
        hypothesis=card.hypothesis if card is not None else workflow.complaint,
        expected_mechanism=card.expected_mechanism if card is not None else None,
        control_key=card.control_key if card is not None else None,
        direction_sign=card.direction_sign if card is not None else None,
        target_effect=target,
        countereffects=HypothesisCountereffects(
            criteria=card.countereffects if card is not None else (),
            passed=execution.countereffect_passed if execution is not None else None,
            observed_metrics=observed_metrics,
        ),
        protocol=protocol,
        do_not_repeat=policy,
        do_not_repeat_reason=policy_reason,
        citations=citations,
    )


def build_hypothesis_lifecycle(
    session_id: str,
    *,
    expected_run_ids: Sequence[str] | None = None,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> HypothesisLifecycle:
    """Build exact controlled-outcome history from current scored workflows."""

    ordered = _exact_session(session_id, expected_run_ids=expected_run_ids, db_path=db_path)
    scope_hash = _session_scope_sha256(session_id, ordered)
    repository = RaceLabRepository(db_path)
    contexts = {
        run_id: _load_run_context(run_id, repository=repository, data_dir=data_dir)
        for run_id in ordered
    }
    workflows, repository_blockers = repository.list_controlled_workflows_for_run_scope(ordered)
    scored = sorted(
        (workflow for workflow in workflows if workflow.status == "scored"),
        key=lambda workflow: (workflow.updated_at, workflow.workflow_id),
    )
    entries = tuple(
        _lifecycle_entry(
            workflow,
            ordered_run_ids=ordered,
            contexts=contexts,
            repository=repository,
            db_path=db_path,
        )
        for workflow in scored
    )
    invalid = [entry for entry in entries if entry.lifecycle_state == "invalid"]
    blockers = list(repository_blockers)
    blockers.extend(
        reason
        for entry in invalid
        for reason in entry.protocol.blocker_reasons
    )
    if repository_blockers and not entries:
        status = "blocked"
    elif invalid:
        status = "limited" if len(invalid) < len(entries) else "blocked"
    elif not entries:
        status = "limited"
        blockers.append("No scored controlled workflow belongs to this exact session yet.")
    else:
        status = "ready"
    blocked_fingerprints = tuple(
        dict.fromkeys(
            entry.hypothesis_fingerprint
            for entry in entries
            if entry.lifecycle_state == "do_not_repeat"
        )
    )
    blocked_policy_keys = tuple(
        dict.fromkeys(
            entry.hypothesis_policy.policy_key
            for entry in entries
            if entry.lifecycle_state == "do_not_repeat"
            and entry.hypothesis_policy is not None
        )
    )
    return HypothesisLifecycle(
        session_id=session_id,
        session_scope_sha256=scope_hash,
        status=status,
        ordered_run_ids=ordered,
        entries=entries,
        do_not_repeat_hypothesis_fingerprints=blocked_fingerprints,
        do_not_repeat_hypothesis_policy_keys=blocked_policy_keys,
        blocker_reasons=_unique(blockers),
    )


def hypothesis_may_repeat(
    lifecycle: HypothesisLifecycle,
    hypothesis_fingerprint: HypothesisPolicyIdentity | str,
) -> bool:
    """Compatibility wrapper around the typed repeat-policy decision."""

    try:
        return evaluate_hypothesis_repeat(lifecycle, hypothesis_fingerprint).allowed
    except ValueError:
        return False


def build_session_intelligence(
    session_id: str,
    *,
    expected_run_ids: Sequence[str] | None = None,
    position_evidence: Sequence[PositionAlignedEvidence] = (),
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> SessionIntelligenceBundle:
    """Build both session intelligence views against one pinned membership."""

    pinned = _exact_session(session_id, expected_run_ids=expected_run_ids, db_path=db_path)
    ledger = build_session_engineering_ledger(
        session_id,
        expected_run_ids=pinned,
        position_evidence=position_evidence,
        db_path=db_path,
        data_dir=data_dir,
    )
    lifecycle = build_hypothesis_lifecycle(
        session_id,
        expected_run_ids=pinned,
        db_path=db_path,
        data_dir=data_dir,
    )
    _exact_session(session_id, expected_run_ids=pinned, db_path=db_path)
    return SessionIntelligenceBundle(
        session_ledger=ledger,
        hypothesis_lifecycle=lifecycle,
    )


__all__ = [
    "SessionScopeChangedError",
    "build_hypothesis_lifecycle",
    "build_session_engineering_ledger",
    "build_session_intelligence",
    "controlled_hypothesis_fingerprint",
    "controlled_hypothesis_policy_identity",
    "evaluate_hypothesis_repeat",
    "hypothesis_may_repeat",
    "position_evidence_sha256",
    "setup_policy_fingerprint",
    "setup_snapshot_fingerprint",
]
