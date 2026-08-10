"""Production bridge from P3 engines to non-authorizing observations.

The P3 analyzers remain the owners of channel qualification and engineering
conclusions.  This module invokes each applicable producer once from one
verified telemetry read, removes recommendation authority through the shared
adapter, and attaches exact run/lap/position citations.  Paired driver and
rotation evidence cites both same-setup laps used by the position alignment.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import math
from statistics import median
from typing import Any

from racelab_engine.analysis.braking_efficiency import analyze_braking_efficiency
from racelab_engine.analysis.damper_response import analyze_damper_response
from racelab_engine.analysis.evidence_contracts import (
    RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT,
)
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.observation_intelligence import (
    adapt_p3_report_observations,
)
from racelab_engine.analysis.p3_common import lap_number, lap_pct, scope_phase_rows
from racelab_engine.analysis.p3_contracts import (
    BRAKING_EFFICIENCY_CONTRACT,
    DAMPER_RESPONSE_CONTRACT,
    POWERTRAIN_GEARING_CONTRACT,
    SIM_INTEGRITY_CONTRACT,
    STINT_STRATEGY_CONTRACT,
    TIRE_STATE_CONTRACT,
)
from racelab_engine.analysis.phase_engineering import analyze_phase_engineering_systems
from racelab_engine.analysis.phase_engineering_contracts import (
    AERO_PLATFORM_WINDOW_CONTRACT,
)
from racelab_engine.analysis.powertrain_gearing import analyze_powertrain_gearing
from racelab_engine.analysis.sim_integrity import (
    SimIntegrityCertificate,
    build_sim_integrity_certificate,
    comparison_integrity_gate,
)
from racelab_engine.analysis.stint_strategy import analyze_stint_strategy
from racelab_engine.analysis.time_alignment import TimeAlignmentResult, analyze_time_alignment
from racelab_engine.analysis.tire_state_energy import analyze_tire_state
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    MechanismKind,
    MechanismObservation,
    MechanismObservationReport,
    ObservationCitation,
    ObservationStatus,
)


_INTEGRITY_CHANNELS = (
    "session_tick",
    "session_time",
    "frame_rate",
    "cpu_usage_foreground",
    "cpu_usage_background",
    "gpu_usage",
    "memory_page_faults_per_s",
    "memory_soft_page_faults_per_s",
    "channel_latency_s",
    "channel_average_latency_s",
    "channel_quality",
    "SessionTick",
    "SessionTime",
    "FrameRate",
    "CpuUsageFG",
    "CpuUsageBG",
    "GpuUsage",
    "MemPageFaultSec",
    "MemSoftPageFaultSec",
    "ChanLatency",
    "ChanAvgLatency",
    "ChanQuality",
)
_PHASE_COMPARISON_CHANNELS = (
    "lap_dist_pct_100",
    "lap_dist_pct",
    "lap_dist_ft",
    "session_time",
    "speed_mps",
    "speed_mph",
    "throttle_pct",
    "brake_pct",
    "steering_deg",
    "yaw_rate",
    "lat_accel",
    "long_accel",
    "vert_accel",
    "vert_accel_g",
    "lat",
    "lon",
    "alt",
    "curvature_1_per_m",
    "on_pit_road",
    "enter_exit_reset_state",
    "lf_shock_defl_in",
    "rf_shock_defl_in",
    "lr_shock_defl_in",
    "rr_shock_defl_in",
    "lf_shock_vel_in_s",
    "rf_shock_vel_in_s",
    "lr_shock_vel_in_s",
    "rr_shock_vel_in_s",
    "lf_ride_height_in",
    "rf_ride_height_in",
    "lr_ride_height_in",
    "rr_ride_height_in",
    "cfs_ride_height_in",
    "front_avg_rh_in",
    "rear_avg_rh_in",
    "center_rake_fs_in",
    "side_rake_in",
    "dynamic_pressure_psf",
    "cfs_risk_score",
)
_TIRE_HISTORY_CHANNELS = tuple(
    f"{corner}_{suffix}"
    for corner in ("lf", "rf", "lr", "rr")
    for suffix in (
        "cold_pressure",
        "carcass_temp_l",
        "carcass_temp_m",
        "carcass_temp_r",
    )
)
_PRODUCER_CONTRACTS = {
    MechanismKind.BRAKING_RESPONSE: BRAKING_EFFICIENCY_CONTRACT,
    MechanismKind.TIRE_STATE: TIRE_STATE_CONTRACT,
    MechanismKind.DAMPER_RESPONSE: DAMPER_RESPONSE_CONTRACT,
    MechanismKind.POWERTRAIN_RESPONSE: POWERTRAIN_GEARING_CONTRACT,
}
_PAIRED_KINDS = frozenset({
    MechanismKind.DRIVER_EXECUTION,
    MechanismKind.CORNER_ROTATION,
    MechanismKind.PLATFORM_RESPONSE,
})
_PRODUCER_ERRORS = (ArithmeticError, IndexError, KeyError, TypeError, ValueError)
_P3_BINDING_REQUIREMENTS = {
    MechanismKind.BRAKING_RESPONSE: (3, 0.90),
    MechanismKind.TIRE_STATE: (3, 0.90),
    MechanismKind.DAMPER_RESPONSE: (32, 0.80),
    MechanismKind.POWERTRAIN_RESPONSE: (3, 0.90),
    MechanismKind.DRIVER_EXECUTION: (3, 0.90),
    MechanismKind.CORNER_ROTATION: (3, 0.90),
    MechanismKind.PLATFORM_RESPONSE: (3, 0.90),
    MechanismKind.STINT_TREND: (3, 0.90),
    MechanismKind.SIM_INTEGRITY: (3, 0.90),
}


@dataclass(frozen=True)
class _ObservationWindow:
    phase: str
    start_pct: float
    end_pct: float
    peak_pct: float
    sample_count: int


def p3_observation_columns(
    excluded_mechanisms: Iterable[MechanismKind] = (),
) -> tuple[str, ...]:
    """Return one column projection for all P3 producers not already represented."""
    excluded = frozenset(excluded_mechanisms)
    columns: list[str] = [
        "lap",
        "lap_number",
        "engineering_phase",
        *_INTEGRITY_CHANNELS,
    ]
    for mechanism, contract in _PRODUCER_CONTRACTS.items():
        if mechanism not in excluded:
            columns.extend(sorted(contract.required_channels | contract.preferred_channels))
    if not _PAIRED_KINDS <= excluded:
        columns.extend(_PHASE_COMPARISON_CHANNELS)
    if MechanismKind.TIRE_STATE not in excluded:
        columns.extend(_TIRE_HISTORY_CHANNELS)
    if MechanismKind.STINT_TREND not in excluded:
        columns.extend(
            sorted(
                STINT_STRATEGY_CONTRACT.required_channels
                | STINT_STRATEGY_CONTRACT.preferred_channels
            )
        )
    return tuple(dict.fromkeys(columns))


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _group_rows(rows: Sequence[Mapping[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for source in rows:
        row = dict(source)
        number = lap_number(row)
        if number is not None:
            grouped.setdefault(number, []).append(row)
    return grouped


def _selected_laps(
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    preferred_lap_number: int | None,
) -> tuple[tuple[LapSummary, ...], LapSummary | None, LapSummary | None, tuple[str, ...]]:
    if any(lap.run_id != run_id for lap in laps):
        return (), None, None, ("A lap summary belongs to a different run than requested.",)
    eligible = tuple(eligible_laps(laps))
    if not eligible:
        return (), None, None, ("No canonical eligible flying lap is available for P3 observations.",)
    by_number = {lap.lap_number: lap for lap in eligible}
    selected = by_number.get(preferred_lap_number) if preferred_lap_number is not None else None
    if selected is None:
        selected = min(
            eligible,
            key=lambda lap: (
                float(lap.lap_time) if lap.lap_time is not None else float("inf"),
                lap.lap_number,
            ),
        )
    reference_candidates = tuple(lap for lap in eligible if lap.lap_number != selected.lap_number)
    selected_time = selected.lap_time
    reference = (
        min(
            reference_candidates,
            key=lambda lap: (
                abs(float(lap.lap_time) - float(selected_time))
                if lap.lap_time is not None and selected_time is not None
                else float("inf"),
                lap.lap_number,
            ),
        )
        if reference_candidates
        else None
    )
    return eligible, selected, reference, ()


def _window_for_phases(
    rows: Sequence[Mapping[str, Any]],
    *,
    lap_number_value: int,
    phases: Sequence[str],
    phase_label: str,
    peak_override: float | None = None,
) -> _ObservationWindow | None:
    lap_rows = [dict(row) for row in rows if lap_number(dict(row)) == lap_number_value]
    if not lap_rows:
        return None
    scoped = lap_rows
    if phases:
        scoped, _observed = scope_phase_rows(lap_rows, set(phases))
    positioned = [(row, lap_pct(row)) for row in scoped]
    positioned = [(row, pct) for row, pct in positioned if pct is not None]
    if not positioned:
        return None
    positions = [float(pct) for _row, pct in positioned]
    start_pct = min(positions)
    end_pct = max(positions)
    peak_pct = (
        float(peak_override)
        if peak_override is not None and start_pct <= peak_override <= end_pct
        else float(median(positions))
    )
    return _ObservationWindow(
        phase=phase_label,
        start_pct=start_pct,
        end_pct=end_pct,
        peak_pct=peak_pct,
        sample_count=len(positioned),
    )


def _blocked_observation(
    *,
    run_id: str,
    setup_id: str | None,
    mechanism: MechanismKind,
    label: str,
    blockers: Sequence[str],
    required_channels: Iterable[str] = (),
    lap_number_value: int | None = None,
    window: _ObservationWindow | None = None,
) -> MechanismObservation:
    reasons = _ordered_unique(blockers) or ("The producing P3 evidence contract did not pass.",)
    observation_id = f"p3:{run_id}:{mechanism.value}:blocked"
    return MechanismObservation(
        observation_id=observation_id,
        producer_id=f"p3:{mechanism.value}",
        artifact_id=observation_id,
        source_run_ids=(run_id,),
        source_setup_ids=((setup_id,) if setup_id is not None else ()),
        sample_coverage=0.0,
        mechanism=mechanism,
        run_id=run_id,
        setup_id=setup_id,
        lap_number=lap_number_value,
        phase=window.phase if window is not None else None,
        lap_pct_start=window.start_pct if window is not None else None,
        lap_pct_end=window.end_pct if window is not None else None,
        lap_pct_peak=window.peak_pct if window is not None else None,
        summary=f"{label} is unavailable for a qualified telemetry observation.",
        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        qualified=False,
        required_channels=tuple(sorted(set(required_channels))),
        telemetry_sample_count=window.sample_count if window is not None else 0,
        repetition_count=0,
        blocker_reasons=reasons,
    )


def _adapt_report(
    report: Any,
    laps: Sequence[LapSummary],
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    setup_id: str | None,
    lap_number_value: int,
    mechanism: MechanismKind,
    label: str,
    required_channels: Iterable[str],
    phase_label: str,
    repetition_count: int,
    peak_override: float | None = None,
) -> MechanismObservationReport:
    phases = tuple(str(value) for value in (getattr(report, "phases", ()) or ()) if value)
    exact_phase_label = (
        f"{phase_label}:{'+'.join(sorted(set(phases)))}"
        if phases
        else phase_label
    )
    window = _window_for_phases(
        rows,
        lap_number_value=lap_number_value,
        phases=phases,
        phase_label=exact_phase_label,
        peak_override=peak_override,
    )
    if window is None:
        blocker = _blocked_observation(
            run_id=run_id,
            setup_id=setup_id,
            mechanism=mechanism,
            label=label,
            blockers=("The producer has no exact lap-position scope to cite.",),
            required_channels=required_channels,
            lap_number_value=lap_number_value,
        )
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            observations=(blocker,),
            blocker_reasons=blocker.blocker_reasons,
        )
    adapted = adapt_p3_report_observations(
        report,
        laps,
        run_id=run_id,
        setup_id=setup_id,
        lap_number=lap_number_value,
        phase=window.phase,
        lap_pct_start=window.start_pct,
        lap_pct_end=window.end_pct,
        lap_pct_peak=window.peak_pct,
        telemetry_sample_count=window.sample_count,
        repetition_count=max(1, repetition_count),
        mechanism_override=mechanism,
    )
    if adapted.observations:
        return adapted
    blocker = _blocked_observation(
        run_id=run_id,
        setup_id=setup_id,
        mechanism=mechanism,
        label=label,
        blockers=adapted.blocker_reasons,
        required_channels=required_channels,
        lap_number_value=lap_number_value,
        window=window,
    )
    return MechanismObservationReport(
        status=ObservationStatus.BLOCKED,
        run_id=run_id,
        setup_id=setup_id,
        observations=(blocker,),
        blocker_reasons=blocker.blocker_reasons,
    )


def _cohort_integrity(
    grouped_rows: Mapping[int, list[dict[str, Any]]],
    eligible: Sequence[LapSummary],
    telemetry_rate_hz: float | None,
) -> tuple[bool | None, float, dict[int, SimIntegrityCertificate]]:
    certificates = {
        lap.lap_number: build_sim_integrity_certificate(
            grouped_rows.get(lap.lap_number, []),
            expected_sample_rate_hz=telemetry_rate_hz,
        )
        for lap in eligible
    }
    if not certificates or any(
        certificate.is_clear_for_analysis is None for certificate in certificates.values()
    ):
        return (
            None,
            min((item.confidence_cap for item in certificates.values()), default=0.0),
            certificates,
        )
    if any(
        certificate.is_clear_for_analysis is False for certificate in certificates.values()
    ):
        return (
            False,
            min(item.confidence_cap for item in certificates.values()),
            certificates,
        )
    return (
        True,
        min(item.confidence_cap for item in certificates.values()),
        certificates,
    )


def _paired_window(alignment: TimeAlignmentResult) -> _ObservationWindow | None:
    positions = [
        float(position)
        for position, point in zip(alignment.grid_pct, alignment.alignment)
        if not point.is_gap and point.aligned_test_pct is not None
    ]
    if not positions:
        return None
    return _ObservationWindow(
        phase="matched_engineering_phases",
        start_pct=min(positions),
        end_pct=max(positions),
        peak_pct=float(median(positions)),
        sample_count=len(positions),
    )


def _add_reference_citations(
    report: MechanismObservationReport,
    *,
    reference_lap: int,
    selected_lap: int,
    grouped_rows: Mapping[int, list[dict[str, Any]]],
) -> MechanismObservationReport:
    qualified: list[MechanismObservation] = []
    for observation in report.observations:
        if not observation.qualified:
            qualified.append(observation)
            continue
        assert observation.setup_id is not None
        assert observation.phase is not None
        assert observation.lap_pct_start is not None
        assert observation.lap_pct_end is not None
        assert observation.lap_pct_peak is not None
        reference_samples = sum(
            observation.lap_pct_start <= position <= observation.lap_pct_end
            for row in grouped_rows.get(reference_lap, [])
            if (position := lap_pct(row)) is not None
        )
        selected_samples = sum(
            observation.lap_pct_start <= position <= observation.lap_pct_end
            for row in grouped_rows.get(selected_lap, [])
            if (position := lap_pct(row)) is not None
        )
        if reference_samples < 1 or selected_samples < 1:
            qualified.append(
                _blocked_observation(
                    run_id=observation.run_id,
                    setup_id=observation.setup_id,
                    mechanism=observation.mechanism,
                    label="Paired P3 evidence",
                    blockers=("Both matched laps require telemetry samples inside the cited window.",),
                    required_channels=observation.required_channels,
                    lap_number_value=selected_lap,
                )
            )
            continue
        citations = tuple(
            ObservationCitation(
                run_id=observation.run_id,
                lap_number=number,
                setup_id=observation.setup_id,
                lap_pct_start=observation.lap_pct_start,
                lap_pct_end=observation.lap_pct_end,
                lap_pct_peak=observation.lap_pct_peak,
                phase=observation.phase,
                evidence_state=observation.evidence_state,
                source_channels=observation.source_channels,
                telemetry_sample_count=sample_count,
            )
            for number, sample_count in (
                (reference_lap, reference_samples),
                (selected_lap, selected_samples),
            )
        )
        payload = observation.model_dump()
        payload.update({
            "telemetry_sample_count": reference_samples + selected_samples,
            "repetition_count": 2,
            "citations": [citation.model_dump() for citation in citations],
        })
        qualified.append(MechanismObservation.model_validate(payload))
    has_qualified = any(item.qualified for item in qualified)
    blockers = _ordered_unique(
        reason for item in qualified for reason in item.blocker_reasons
    )
    return MechanismObservationReport(
        status=(
            ObservationStatus.READY
            if has_qualified
            else ObservationStatus.BLOCKED
            if blockers
            else ObservationStatus.NO_FINDING
        ),
        run_id=report.run_id,
        setup_id=report.setup_id,
        observations=tuple(qualified),
        blocker_reasons=() if has_qualified else blockers,
    )


def merge_mechanism_observation_reports(
    run_id: str,
    setup_id: str | None,
    reports: Sequence[MechanismObservationReport],
) -> MechanismObservationReport:
    """Merge producer reports without letting one qualified engine unblock another."""
    scope_blockers = [
        "A mechanism report belongs to a different run or setup scope."
        for report in reports
        if report.run_id != run_id or report.setup_id != setup_id
    ]
    if scope_blockers:
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=tuple(scope_blockers),
        )
    observations: list[MechanismObservation] = []
    seen: dict[tuple[str, str], MechanismObservation] = {}
    artifact_conflicts: list[str] = []
    for report in reports:
        for observation in report.observations:
            artifact_identity = (observation.producer_id, observation.artifact_id)
            if artifact_identity not in seen:
                seen[artifact_identity] = observation
                observations.append(observation)
            elif seen[artifact_identity] != observation:
                artifact_conflicts.append(
                    "Producer artifact identity has conflicting observation payloads: "
                    f"{observation.producer_id}/{observation.artifact_id}."
                )
    if artifact_conflicts:
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=_ordered_unique(artifact_conflicts),
        )
    qualified = tuple(item for item in observations if item.qualified)
    blockers = _ordered_unique(
        reason
        for report in reports
        for reason in (
            *report.blocker_reasons,
            *(reason for item in report.observations for reason in item.blocker_reasons),
        )
    )
    return MechanismObservationReport(
        status=(
            ObservationStatus.READY
            if qualified
            else ObservationStatus.BLOCKED
            if blockers or observations
            else ObservationStatus.NO_FINDING
        ),
        run_id=run_id,
        setup_id=setup_id,
        observations=tuple(observations),
        blocker_reasons=() if qualified else blockers,
    )


def _usable_event_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return bool(str(value).strip())


def _rebind_p3_observation_rows(
    report: MechanismObservationReport,
    grouped_rows: Mapping[int, list[dict[str, Any]]],
) -> MechanismObservationReport:
    """Bind every P3 citation to rows where all claimed channels coexist."""
    rebound: list[MechanismObservation] = []
    for observation in report.observations:
        if not observation.qualified:
            rebound.append(observation)
            continue
        minimum_samples, minimum_coverage = _P3_BINDING_REQUIREMENTS.get(
            observation.mechanism,
            (3, 0.90),
        )
        citations: list[ObservationCitation] = []
        citation_coverages: list[float] = []
        blockers: list[str] = []
        for citation in observation.citations:
            window_rows = [
                row
                for row in grouped_rows.get(citation.lap_number, [])
                if (position := lap_pct(row)) is not None
                and citation.lap_pct_start <= position <= citation.lap_pct_end
            ]
            coobserved = [
                row
                for row in window_rows
                if all(
                    _usable_event_value(row.get(channel))
                    for channel in citation.source_channels
                )
            ]
            coverage = len(coobserved) / len(window_rows) if window_rows else 0.0
            if len(coobserved) < minimum_samples or coverage < minimum_coverage:
                missing = tuple(
                    channel
                    for channel in citation.source_channels
                    if not any(
                        _usable_event_value(row.get(channel)) for row in window_rows
                    )
                )
                missing_text = (
                    " Missing throughout: " + ", ".join(missing) + "."
                    if missing
                    else ""
                )
                blockers.append(
                    f"{observation.mechanism.value.replace('_', ' ').title()} lap "
                    f"{citation.lap_number} has {len(coobserved)}/{len(window_rows)} "
                    "cited-window rows with every source channel co-observed; "
                    f"at least {minimum_samples} rows and {minimum_coverage:.0%} "
                    f"coverage are required.{missing_text}"
                )
                continue
            citation_payload = citation.model_dump()
            citation_payload["telemetry_sample_count"] = len(coobserved)
            citations.append(ObservationCitation.model_validate(citation_payload))
            citation_coverages.append(coverage)
        if blockers or len(citations) != len(observation.citations):
            payload = observation.model_dump()
            payload.update({
                "summary": (
                    "The P3 observation was withheld because its exact telemetry rows "
                    "did not support the claimed source-channel scope."
                ),
                "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                "qualified": False,
                "supporting_evidence": (),
                "contradicting_evidence": (),
                "telemetry_sample_count": 0,
                "sample_coverage": 0.0,
                "repetition_count": 0,
                "citations": (),
                "blocker_reasons": _ordered_unique(blockers),
            })
            rebound.append(MechanismObservation.model_validate(payload))
            continue
        payload = observation.model_dump()
        payload.update({
            "telemetry_sample_count": sum(
                citation.telemetry_sample_count for citation in citations
            ),
            "sample_coverage": min(citation_coverages),
            "citations": [citation.model_dump() for citation in citations],
        })
        rebound.append(MechanismObservation.model_validate(payload))
    qualified = tuple(item for item in rebound if item.qualified)
    blockers = _ordered_unique(
        reason for item in rebound for reason in item.blocker_reasons
    )
    return MechanismObservationReport(
        status=(
            ObservationStatus.READY
            if qualified
            else ObservationStatus.BLOCKED
            if blockers
            else ObservationStatus.NO_FINDING
        ),
        run_id=report.run_id,
        setup_id=report.setup_id,
        observations=tuple(rebound),
        blocker_reasons=() if qualified else blockers,
    )


def revalidate_event_mechanism_observations(
    report: MechanismObservationReport,
    rows: Sequence[Mapping[str, Any]],
) -> MechanismObservationReport:
    """Re-bind persisted event citations to their exact source telemetry rows."""
    rebound: list[MechanismObservation] = []
    for observation in report.observations:
        if not observation.qualified:
            rebound.append(observation)
            continue
        citations: list[ObservationCitation] = []
        citation_coverages: list[float] = []
        missing_channels: set[str] = set()
        for citation in observation.citations:
            window_rows = [
                row
                for row in rows
                if lap_number(dict(row)) == citation.lap_number
                and (position := lap_pct(dict(row))) is not None
                and citation.lap_pct_start <= position <= citation.lap_pct_end
            ]
            coobserved = [
                row
                for row in window_rows
                if all(_usable_event_value(row.get(channel)) for channel in citation.source_channels)
            ]
            if not coobserved:
                missing_channels.update(
                    channel
                    for channel in citation.source_channels
                    if not any(_usable_event_value(row.get(channel)) for row in window_rows)
                )
                if not missing_channels:
                    missing_channels.update(citation.source_channels)
                continue
            payload = citation.model_dump()
            payload["telemetry_sample_count"] = len(coobserved)
            citations.append(ObservationCitation.model_validate(payload))
            citation_coverages.append(
                len(coobserved) / len(window_rows) if window_rows else 0.0
            )
        if len(citations) != len(observation.citations):
            payload = observation.model_dump()
            payload.update({
                "summary": "The persisted event could not be rebound to its source telemetry.",
                "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                "qualified": False,
                "supporting_evidence": (),
                "contradicting_evidence": (),
                "telemetry_sample_count": 0,
                "sample_coverage": 0.0,
                "repetition_count": 0,
                "citations": (),
                "blocker_reasons": (
                    "The cited event window has no co-observed source telemetry for: "
                    + ", ".join(sorted(missing_channels))
                    + ".",
                ),
            })
            rebound.append(MechanismObservation.model_validate(payload))
            continue
        payload = observation.model_dump()
        payload.update({
            "telemetry_sample_count": sum(
                citation.telemetry_sample_count for citation in citations
            ),
            "sample_coverage": min(citation_coverages),
            "citations": [citation.model_dump() for citation in citations],
        })
        rebound.append(MechanismObservation.model_validate(payload))
    qualified = tuple(item for item in rebound if item.qualified)
    blockers = _ordered_unique(
        reason for item in rebound for reason in item.blocker_reasons
    )
    return MechanismObservationReport(
        status=(
            ObservationStatus.READY
            if qualified
            else ObservationStatus.BLOCKED
            if blockers
            else ObservationStatus.NO_FINDING
        ),
        run_id=report.run_id,
        setup_id=report.setup_id,
        observations=tuple(rebound),
        blocker_reasons=() if qualified else blockers,
    )


def _adapt_integrity_certificate(
    certificate: SimIntegrityCertificate,
    *,
    run_id: str,
    setup_id: str | None,
    lap_number_value: int,
    rows: Sequence[Mapping[str, Any]],
) -> MechanismObservationReport:
    """Publish the integrity producer's own state without clearing other producers."""
    window = _window_for_phases(
        rows,
        lap_number_value=lap_number_value,
        phases=(),
        phase_label="sim_integrity_window",
    )
    conclusion = certificate.conclusion
    blockers: list[str] = []
    if setup_id is None:
        blockers.append("A recorded setup identity is required for integrity scope.")
    if window is None:
        blockers.append("The integrity certificate has no exact lap-position scope to cite.")
    if conclusion.evidence_state not in {
        EvidenceState.CALCULATED,
        EvidenceState.OBSERVED_CORRELATION,
    }:
        blockers.extend(conclusion.blocker_reasons)
        blockers.append("The simulator/data integrity state is unavailable.")
    if not conclusion.source_channels:
        blockers.append("The integrity certificate has no source-channel provenance.")
    state_evidence = tuple(
        dict.fromkeys(
            (*conclusion.supporting_evidence, *conclusion.contradicting_evidence)
        )
    )
    if not state_evidence:
        blockers.append("The integrity certificate has no typed check evidence.")
    observation_id = f"p3:{run_id}:sim_integrity:{lap_number_value}"
    if blockers or window is None or setup_id is None:
        blocked = _blocked_observation(
            run_id=run_id,
            setup_id=setup_id,
            mechanism=MechanismKind.SIM_INTEGRITY,
            label="Simulator/data integrity",
            blockers=blockers,
            required_channels=SIM_INTEGRITY_CONTRACT.required_channels,
            lap_number_value=lap_number_value,
            window=window,
        )
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            observations=(blocked,),
            blocker_reasons=blocked.blocker_reasons,
        )
    source_channels = _ordered_unique(conclusion.source_channels)
    citation = ObservationCitation(
        run_id=run_id,
        lap_number=lap_number_value,
        setup_id=setup_id,
        lap_pct_start=window.start_pct,
        lap_pct_end=window.end_pct,
        lap_pct_peak=window.peak_pct,
        phase=window.phase,
        evidence_state=conclusion.evidence_state,
        source_channels=source_channels,
        telemetry_sample_count=window.sample_count,
    )
    observation = MechanismObservation(
        observation_id=observation_id,
        producer_id=SIM_INTEGRITY_CONTRACT.key,
        artifact_id=observation_id,
        source_run_ids=(run_id,),
        source_setup_ids=(setup_id,),
        sample_coverage=1.0,
        mechanism=MechanismKind.SIM_INTEGRITY,
        run_id=run_id,
        setup_id=setup_id,
        lap_number=lap_number_value,
        phase=window.phase,
        lap_pct_start=window.start_pct,
        lap_pct_end=window.end_pct,
        lap_pct_peak=window.peak_pct,
        summary=conclusion.summary,
        evidence_state=conclusion.evidence_state,
        qualified=True,
        source_channels=source_channels,
        required_channels=tuple(sorted(SIM_INTEGRITY_CONTRACT.required_channels)),
        supporting_evidence=state_evidence,
        contradicting_evidence=tuple(conclusion.contradicting_evidence),
        telemetry_sample_count=window.sample_count,
        repetition_count=1,
        citations=(citation,),
    )
    return MechanismObservationReport(
        status=ObservationStatus.READY,
        run_id=run_id,
        setup_id=setup_id,
        observations=(observation,),
    )


def _add_stint_citations(
    report: MechanismObservationReport,
    *,
    lap_numbers: Sequence[int],
    grouped_rows: Mapping[int, list[dict[str, Any]]],
) -> MechanismObservationReport:
    """Bind aggregate stint conclusions to every exact producer-used lap scope."""
    rebound: list[MechanismObservation] = []
    for observation in report.observations:
        if not observation.qualified:
            rebound.append(observation)
            continue
        assert observation.setup_id is not None
        citations: list[ObservationCitation] = []
        for number in lap_numbers:
            positioned = [
                (row, float(position))
                for row in grouped_rows.get(number, ())
                if (position := lap_pct(row)) is not None
            ]
            if not positioned:
                continue
            positions = [position for _row, position in positioned]
            citations.append(
                ObservationCitation(
                    run_id=observation.run_id,
                    lap_number=number,
                    setup_id=observation.setup_id,
                    lap_pct_start=min(positions),
                    lap_pct_end=max(positions),
                    lap_pct_peak=float(median(positions)),
                    phase="continuous_stint",
                    evidence_state=observation.evidence_state,
                    source_channels=observation.source_channels,
                    telemetry_sample_count=len(positioned),
                )
            )
        if not citations or observation.lap_number not in {
            citation.lap_number for citation in citations
        }:
            rebound.append(
                _blocked_observation(
                    run_id=observation.run_id,
                    setup_id=observation.setup_id,
                    mechanism=MechanismKind.STINT_TREND,
                    label="Stint trend",
                    blockers=(
                        "The producer-used continuous stint has no exact position scope "
                        "for the anchor lap.",
                    ),
                    required_channels=observation.required_channels,
                    lap_number_value=observation.lap_number,
                )
            )
            continue
        payload = observation.model_dump()
        payload.update(
            {
                "phase": "continuous_stint",
                "repetition_count": len(citations),
                "telemetry_sample_count": sum(
                    citation.telemetry_sample_count for citation in citations
                ),
                "citations": [citation.model_dump() for citation in citations],
            }
        )
        rebound.append(MechanismObservation.model_validate(payload))
    qualified = tuple(item for item in rebound if item.qualified)
    blockers = _ordered_unique(
        reason for item in rebound for reason in item.blocker_reasons
    )
    return MechanismObservationReport(
        status=(
            ObservationStatus.READY
            if qualified
            else ObservationStatus.BLOCKED
            if blockers
            else ObservationStatus.NO_FINDING
        ),
        run_id=report.run_id,
        setup_id=report.setup_id,
        observations=tuple(rebound),
        blocker_reasons=() if qualified else blockers,
    )


def build_p3_mechanism_observations(
    rows: Sequence[Mapping[str, Any]],
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    setup_id: str | None,
    telemetry_rate_hz: float | None,
    preferred_lap_number: int | None = None,
    existing_mechanisms: Iterable[MechanismKind] = (),
) -> MechanismObservationReport:
    """Run missing deterministic P3 producers and adapt only their evidence outputs."""
    existing = frozenset(existing_mechanisms)
    eligible, selected, reference, selection_blockers = _selected_laps(
        laps,
        run_id=run_id,
        preferred_lap_number=preferred_lap_number,
    )
    if setup_id is None or not setup_id.strip():
        selection_blockers = (
            *selection_blockers,
            "A recorded setup identity is required for P3 mechanism scope.",
        )
    if any(str(row.get("run_id") or "") != run_id for row in rows):
        selection_blockers = (
            *selection_blockers,
            "A telemetry row belongs to a different run than requested.",
        )
    if selection_blockers or selected is None:
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=_ordered_unique(selection_blockers),
        )

    normalized_rows = [dict(row) for row in rows]
    grouped = _group_rows(normalized_rows)
    selected_rows = grouped.get(selected.lap_number, [])
    if not selected_rows:
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=("The selected eligible lap has no telemetry rows.",),
        )
    try:
        cohort_clear, cohort_cap, certificates = _cohort_integrity(
            grouped,
            eligible,
            telemetry_rate_hz,
        )
    except _PRODUCER_ERRORS as exc:
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=(f"Simulator/data integrity could not be verified: {exc}",),
        )

    reports: list[MechanismObservationReport] = []
    if MechanismKind.RESISTANCE_SCRUB_LIKE not in existing:
        resistance_blocker = _blocked_observation(
            run_id=run_id,
            setup_id=setup_id,
            mechanism=MechanismKind.RESISTANCE_SCRUB_LIKE,
            label="Resistance/scrub-like response",
            blockers=(
                "A server-verified controlled A/B/A2 producer artifact is required; "
                "a single-run resistance-like proxy cannot establish this mechanism.",
            ),
            required_channels=RELATIVE_HIGH_SPEED_RESISTANCE_CONTRACT.required_channels,
            lap_number_value=selected.lap_number,
        )
        reports.append(
            MechanismObservationReport(
                status=ObservationStatus.BLOCKED,
                run_id=run_id,
                setup_id=setup_id,
                observations=(resistance_blocker,),
                blocker_reasons=resistance_blocker.blocker_reasons,
            )
        )
    if MechanismKind.SIM_INTEGRITY not in existing:
        reports.append(
            _adapt_integrity_certificate(
                certificates[selected.lap_number],
                run_id=run_id,
                setup_id=setup_id,
                lap_number_value=selected.lap_number,
                rows=normalized_rows,
            )
        )
    single_specs = (
        (
            MechanismKind.BRAKING_RESPONSE,
            "Braking response",
            "braking_phase_aggregate",
            BRAKING_EFFICIENCY_CONTRACT,
            analyze_braking_efficiency,
        ),
        (
            MechanismKind.TIRE_STATE,
            "Tire state",
            "tire_state_phase_aggregate",
            TIRE_STATE_CONTRACT,
            analyze_tire_state,
        ),
        (
            MechanismKind.DAMPER_RESPONSE,
            "Damper response",
            "damper_phase_aggregate",
            DAMPER_RESPONSE_CONTRACT,
            analyze_damper_response,
        ),
        (
            MechanismKind.POWERTRAIN_RESPONSE,
            "Powertrain response",
            "powertrain_phase_aggregate",
            POWERTRAIN_GEARING_CONTRACT,
            analyze_powertrain_gearing,
        ),
    )
    for mechanism, label, phase_label, contract, analyzer in single_specs:
        if mechanism in existing:
            continue
        try:
            if mechanism is MechanismKind.DAMPER_RESPONSE:
                producer_report = analyzer(
                    normalized_rows,
                    list(laps),
                    run_id=run_id,
                    selected_lap=selected.lap_number,
                    sim_integrity_clear=cohort_clear,
                    sim_integrity_confidence_cap=cohort_cap,
                    setup_snapshot_captured=False,
                )
            elif mechanism is MechanismKind.POWERTRAIN_RESPONSE:
                producer_report = analyzer(
                    normalized_rows,
                    list(laps),
                    selected_lap=selected.lap_number,
                    sim_integrity_clear=cohort_clear,
                    sim_integrity_confidence_cap=cohort_cap,
                    redline_rpm=None,
                )
            else:
                producer_report = analyzer(
                    normalized_rows,
                    list(laps),
                    selected_lap=selected.lap_number,
                    sim_integrity_clear=cohort_clear,
                    sim_integrity_confidence_cap=cohort_cap,
                )
            peak_override = (
                getattr(getattr(producer_report, "metrics", None), "incipient_lock_lap_pct", None)
                if mechanism is MechanismKind.BRAKING_RESPONSE
                else None
            )
            repetition_count = (
                int(getattr(producer_report, "working_history_laps", 1) or 1)
                if mechanism is MechanismKind.TIRE_STATE
                else len(eligible)
                if mechanism is MechanismKind.DAMPER_RESPONSE
                else len(
                    getattr(
                        getattr(producer_report, "context_diagnostics", None),
                        "comparable_laps",
                        (),
                    )
                )
                if mechanism is MechanismKind.POWERTRAIN_RESPONSE
                else 1
            )
            reports.append(
                _adapt_report(
                    producer_report,
                    laps,
                    normalized_rows,
                    run_id=run_id,
                    setup_id=setup_id,
                    lap_number_value=selected.lap_number,
                    mechanism=mechanism,
                    label=label,
                    required_channels=contract.required_channels,
                    phase_label=phase_label,
                    repetition_count=max(1, repetition_count),
                    peak_override=peak_override,
                )
            )
        except _PRODUCER_ERRORS as exc:
            blocker = _blocked_observation(
                run_id=run_id,
                setup_id=setup_id,
                mechanism=mechanism,
                label=label,
                blockers=(f"The {label.casefold()} producer failed closed: {exc}",),
                required_channels=contract.required_channels,
                lap_number_value=selected.lap_number,
            )
            reports.append(
                MechanismObservationReport(
                    status=ObservationStatus.BLOCKED,
                    run_id=run_id,
                    setup_id=setup_id,
                    observations=(blocker,),
                    blocker_reasons=blocker.blocker_reasons,
                )
            )

    if MechanismKind.STINT_TREND not in existing:
        try:
            stint_report = analyze_stint_strategy(
                normalized_rows,
                list(laps),
                sim_integrity_clear=cohort_clear,
                sim_integrity_confidence_cap=cohort_cap,
            )
            producer_laps = tuple(
                dict.fromkeys(
                    (
                        *getattr(stint_report, "historical_segment_laps", ()),
                        *getattr(stint_report, "active_segment_laps", ()),
                    )
                )
            )
            anchor_lap = (
                selected.lap_number
                if selected.lap_number in producer_laps
                else producer_laps[-1]
                if producer_laps
                else selected.lap_number
            )
            adapted_stint = _adapt_report(
                stint_report,
                laps,
                normalized_rows,
                run_id=run_id,
                setup_id=setup_id,
                lap_number_value=anchor_lap,
                mechanism=MechanismKind.STINT_TREND,
                label="Stint trend",
                required_channels=STINT_STRATEGY_CONTRACT.required_channels,
                phase_label="continuous_stint",
                repetition_count=max(1, len(producer_laps)),
            )
            reports.append(
                _add_stint_citations(
                    adapted_stint,
                    lap_numbers=producer_laps,
                    grouped_rows=grouped,
                )
            )
        except _PRODUCER_ERRORS as exc:
            blocker = _blocked_observation(
                run_id=run_id,
                setup_id=setup_id,
                mechanism=MechanismKind.STINT_TREND,
                label="Stint trend",
                blockers=(f"The stint trend producer failed closed: {exc}",),
                required_channels=STINT_STRATEGY_CONTRACT.required_channels,
                lap_number_value=selected.lap_number,
            )
            reports.append(
                MechanismObservationReport(
                    status=ObservationStatus.BLOCKED,
                    run_id=run_id,
                    setup_id=setup_id,
                    observations=(blocker,),
                    blocker_reasons=blocker.blocker_reasons,
                )
            )

    paired_needed = bool(_PAIRED_KINDS - existing)
    if paired_needed and reference is None:
        for mechanism, label in (
            (MechanismKind.DRIVER_EXECUTION, "Driver comparison"),
            (MechanismKind.CORNER_ROTATION, "Rotation comparison"),
            (MechanismKind.PLATFORM_RESPONSE, "Platform comparison"),
        ):
            if mechanism in existing:
                continue
            blocker = _blocked_observation(
                run_id=run_id,
                setup_id=setup_id,
                mechanism=mechanism,
                label=label,
                blockers=("Two eligible same-setup laps are required for matched comparison.",),
                lap_number_value=selected.lap_number,
            )
            reports.append(
                MechanismObservationReport(
                    status=ObservationStatus.BLOCKED,
                    run_id=run_id,
                    setup_id=setup_id,
                    observations=(blocker,),
                    blocker_reasons=blocker.blocker_reasons,
                )
            )
    elif paired_needed and reference is not None:
        reference_rows = grouped.get(reference.lap_number, [])
        try:
            alignment = analyze_time_alignment(
                reference_rows,
                selected_rows,
                start_pct=0.0,
                end_pct=100.0,
                step_pct=0.25,
            )
            reference_certificate = certificates[reference.lap_number]
            selected_certificate = certificates[selected.lap_number]
            pair_clear, pair_cap, pair_warnings = comparison_integrity_gate(
                reference_certificate,
                selected_certificate,
            )
            phase_report = analyze_phase_engineering_systems(
                reference_rows,
                selected_rows,
                alignment,
                baseline_run_id=run_id,
                test_run_id=run_id,
                baseline_lap=reference.lap_number,
                test_lap=selected.lap_number,
                eligible_laps=True,
                repetitions=1,
                setup_change_isolated=True,
                sim_integrity_clear=pair_clear,
                sim_integrity_confidence_cap=pair_cap,
                baseline_sim_integrity_status=reference_certificate.status,
                test_sim_integrity_status=selected_certificate.status,
                sim_integrity_warnings=pair_warnings,
            )
            pair_window = _paired_window(alignment)
            for mechanism, label, producer_report, required_channels in (
                (
                    MechanismKind.DRIVER_EXECUTION,
                    "Driver execution",
                    phase_report.driver_line,
                    (
                        "lap_dist_pct_100",
                        "session_time",
                        "speed_mps",
                        "throttle_pct",
                        "brake_pct",
                        "steering_deg",
                        "lat",
                        "lon",
                    ),
                ),
                (
                    MechanismKind.CORNER_ROTATION,
                    "Corner rotation",
                    phase_report.corner_rotation,
                    (
                        "lap_dist_pct_100",
                        "speed_mps",
                        "yaw_rate",
                        "steering_deg",
                        "lat_accel",
                    ),
                ),
                (
                    MechanismKind.PLATFORM_RESPONSE,
                    "Platform response",
                    phase_report.aero_platform,
                    tuple(sorted(AERO_PLATFORM_WINDOW_CONTRACT.required_channels)),
                ),
            ):
                if mechanism in existing:
                    continue
                if pair_window is None:
                    blocker = _blocked_observation(
                        run_id=run_id,
                        setup_id=setup_id,
                        mechanism=mechanism,
                        label=label,
                        blockers=("The matched laps have no common physical-position scope.",),
                        required_channels=required_channels,
                        lap_number_value=selected.lap_number,
                    )
                    reports.append(
                        MechanismObservationReport(
                            status=ObservationStatus.BLOCKED,
                            run_id=run_id,
                            setup_id=setup_id,
                            observations=(blocker,),
                            blocker_reasons=blocker.blocker_reasons,
                        )
                    )
                    continue
                report_phases = sorted({
                    str(metric.phase)
                    for metric in (getattr(producer_report, "phase_metrics", ()) or ())
                    if getattr(metric, "phase", None)
                })
                exact_pair_window = _ObservationWindow(
                    phase=(
                        "matched_engineering_phases:"
                        + "+".join(report_phases)
                        if report_phases
                        else pair_window.phase
                    ),
                    start_pct=pair_window.start_pct,
                    end_pct=pair_window.end_pct,
                    peak_pct=pair_window.peak_pct,
                    sample_count=pair_window.sample_count,
                )
                adapted = adapt_p3_report_observations(
                    producer_report,
                    laps,
                    run_id=run_id,
                    setup_id=setup_id,
                    lap_number=selected.lap_number,
                    phase=exact_pair_window.phase,
                    lap_pct_start=exact_pair_window.start_pct,
                    lap_pct_end=exact_pair_window.end_pct,
                    lap_pct_peak=exact_pair_window.peak_pct,
                    telemetry_sample_count=exact_pair_window.sample_count,
                    repetition_count=2,
                    mechanism_override=mechanism,
                )
                if not adapted.observations:
                    blocker = _blocked_observation(
                        run_id=run_id,
                        setup_id=setup_id,
                        mechanism=mechanism,
                        label=label,
                        blockers=adapted.blocker_reasons,
                        required_channels=required_channels,
                        lap_number_value=selected.lap_number,
                        window=exact_pair_window,
                    )
                    adapted = MechanismObservationReport(
                        status=ObservationStatus.BLOCKED,
                        run_id=run_id,
                        setup_id=setup_id,
                        observations=(blocker,),
                        blocker_reasons=blocker.blocker_reasons,
                    )
                reports.append(
                    _add_reference_citations(
                        adapted,
                        reference_lap=reference.lap_number,
                        selected_lap=selected.lap_number,
                        grouped_rows=grouped,
                    )
                )
        except _PRODUCER_ERRORS as exc:
            for mechanism, label in (
                (MechanismKind.DRIVER_EXECUTION, "Driver comparison"),
                (MechanismKind.CORNER_ROTATION, "Rotation comparison"),
                (MechanismKind.PLATFORM_RESPONSE, "Platform comparison"),
            ):
                if mechanism in existing:
                    continue
                blocker = _blocked_observation(
                    run_id=run_id,
                    setup_id=setup_id,
                    mechanism=mechanism,
                    label=label,
                    blockers=(f"The matched-position producer failed closed: {exc}",),
                    lap_number_value=selected.lap_number,
                )
                reports.append(
                    MechanismObservationReport(
                        status=ObservationStatus.BLOCKED,
                        run_id=run_id,
                        setup_id=setup_id,
                        observations=(blocker,),
                        blocker_reasons=blocker.blocker_reasons,
                    )
                )

    merged = merge_mechanism_observation_reports(run_id, setup_id, reports)
    return _rebind_p3_observation_rows(merged, grouped)


__all__ = [
    "build_p3_mechanism_observations",
    "merge_mechanism_observation_reports",
    "p3_observation_columns",
    "revalidate_event_mechanism_observations",
]
