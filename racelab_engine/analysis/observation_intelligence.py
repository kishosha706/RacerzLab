"""Pure, evidence-only builders for same-setup observation intelligence.

Every calculation aligns laps by physical track position.  Telemetry rows are
samples, never independent experiments; repetition counts always mean distinct
eligible laps.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import math
from statistics import median
from typing import Any

from racelab_engine.analysis.comparison import build_lap_grid, interpolate_run_to_grid
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.time_alignment import detect_engineering_phases
from racelab_engine.models.engineering import EngineeringConclusion
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    DriverChannelRepeatability,
    DriverCoachingFocus,
    DriverRepeatabilitySignature,
    MechanismKind,
    MechanismObservation,
    MechanismObservationReport,
    ObservationCitation,
    ObservationStatus,
    OpportunitySignature,
    OpportunitySignatureReport,
    SameSetupAnomaly,
    SameSetupAnomalyReport,
)


_QUALIFIED_STATES = frozenset({
    EvidenceState.MEASURED,
    EvidenceState.CALCULATED,
    EvidenceState.ESTIMATED_PROXY,
    EvidenceState.OBSERVED_CORRELATION,
    EvidenceState.CONTROLLED_TEST_EFFECT,
})
_POSITION_CHANNEL = "lap_dist_pct_100"
_OPPORTUNITY_CHANNELS = (_POSITION_CHANNEL, "session_time")
_DRIVER_CHANNELS = ("brake_pct", "throttle_pct", "steering_deg")
_DRIVER_UNITS = {"brake_pct": "%", "throttle_pct": "%", "steering_deg": "deg"}
_DRIVER_SPREAD_LIMITS = {"brake_pct": 3.0, "throttle_pct": 3.0, "steering_deg": 1.5}
_ANOMALY_FLOORS = {
    "brake_pct": 2.0,
    "throttle_pct": 2.0,
    "steering_deg": 0.75,
    "speed_mph": 0.5,
    "speed_mps": 0.25,
    "yaw_rate": 0.02,
    "lat_accel": 0.25,
    "long_accel": 0.25,
    "cfs_ride_height_in": 0.03,
}
_ANOMALY_SCOPE_RESOLUTION_PCT = 0.5
_DRIVER_SCOPE_RESOLUTION_PCT = 0.5


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _row_lap_number(row: Mapping[str, Any]) -> int | None:
    value = _finite(row.get("lap", row.get("lap_number")))
    if value is None or value < 0 or not value.is_integer():
        return None
    return int(value)


def _row_lap_pct(row: Mapping[str, Any]) -> float | None:
    value = _finite(row.get(_POSITION_CHANNEL))
    if value is not None:
        return value if 0.0 <= value <= 100.0 else None
    value = _finite(row.get("lap_dist_pct"))
    if value is None:
        return None
    value = value * 100.0 if 0.0 <= value <= 1.5 else value
    return value if 0.0 <= value <= 100.0 else None


def _normalize_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        lap_number = _row_lap_number(row)
        lap_pct = _row_lap_pct(row)
        if lap_number is None or lap_pct is None:
            continue
        normalized.append({**row, "lap": lap_number, _POSITION_CHANNEL: lap_pct})
    return normalized


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _identity_and_eligibility(
    rows: Sequence[Mapping[str, Any]],
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    setup_id: str | None,
    lap_setup_ids: Mapping[int, str] | None,
) -> tuple[list[dict[str, Any]], tuple[LapSummary, ...], tuple[str, ...]]:
    blockers: list[str] = []
    if not run_id.strip():
        blockers.append("A non-empty run identity is required.")
    if setup_id is None or not setup_id.strip():
        blockers.append("A recorded setup identity is required for same-setup observations.")
    if any(lap.run_id != run_id for lap in laps):
        blockers.append("A lap summary belongs to a different run than the requested scope.")
    row_run_ids = {
        str(row.get("run_id"))
        for row in rows
        if row.get("run_id") not in {None, ""}
    }
    if row_run_ids and row_run_ids != {run_id}:
        blockers.append("Telemetry rows contain a cross-run identity mismatch.")
    numbers = [lap.lap_number for lap in laps]
    if len(numbers) != len(set(numbers)):
        blockers.append("Lap summary identities are duplicated within the run.")
    eligible = tuple(eligible_laps(laps)) if not blockers else ()
    if lap_setup_ids is not None and setup_id is not None:
        mismatched = [
            lap.lap_number
            for lap in eligible
            if lap_setup_ids.get(lap.lap_number) != setup_id
        ]
        if mismatched:
            blockers.append(
                "Eligible laps do not all carry the requested same-setup identity: "
                + ", ".join(str(number) for number in mismatched)
                + "."
            )
    normalized = _normalize_rows(rows)
    return normalized, eligible, tuple(dict.fromkeys(blockers))


def _lap_rows(
    rows: Sequence[dict[str, Any]],
    lap_numbers: Sequence[int],
) -> dict[int, list[dict[str, Any]]]:
    selected = set(lap_numbers)
    grouped = {number: [] for number in lap_numbers}
    for row in rows:
        number = _row_lap_number(row)
        if number in selected:
            grouped[number].append(row)
    for values in grouped.values():
        values.sort(key=lambda row: (_row_lap_pct(row) or 0.0, _finite(row.get("session_time")) or 0.0))
    return grouped


def _required_channel_blockers(
    grouped: Mapping[int, Sequence[Mapping[str, Any]]],
    channels: Sequence[str],
) -> tuple[str, ...]:
    blockers: list[str] = []
    for channel in channels:
        missing_laps = [
            number
            for number, rows in grouped.items()
            if not any(_finite(row.get(channel)) is not None for row in rows)
        ]
        if missing_laps:
            blockers.append(
                f"Required channel {channel} is unavailable on eligible lap(s) "
                + ", ".join(str(number) for number in missing_laps)
                + "."
            )
    return tuple(blockers)


def _grid_channels(
    grouped: Mapping[int, list[dict[str, Any]]],
    channels: Sequence[str],
    grid: list[float],
) -> tuple[dict[int, dict[str, list[float | None]]], tuple[str, ...]]:
    output: dict[int, dict[str, list[float | None]]] = {}
    blockers: list[str] = []
    for number, rows in grouped.items():
        interpolated = interpolate_run_to_grid(rows, list(channels), grid)
        for channel in channels:
            values = interpolated[channel]
            coverage = sum(value is not None for value in values) / len(grid) if grid else 0.0
            if coverage < 0.9:
                blockers.append(
                    f"Eligible lap {number} has only {coverage:.0%} physical-position "
                    f"coverage for {channel}."
                )
        output[number] = interpolated
    return output, tuple(blockers)


def _phase_grid(
    grouped: Mapping[int, list[dict[str, Any]]],
    grid: list[float],
) -> list[str]:
    if not grouped:
        return ["unknown"] * len(grid)
    representative = max(grouped.values(), key=len)
    explicit = [
        (_row_lap_pct(row), str(row.get("engineering_phase")))
        for row in representative
        if _row_lap_pct(row) is not None and row.get("engineering_phase")
    ]
    if explicit:
        return [
            min(explicit, key=lambda item: abs(float(item[0]) - pct))[1]
            for pct in grid
        ]
    try:
        phases, _intervals, _channels = detect_engineering_phases(representative, grid=grid)
    except (KeyError, TypeError, ValueError):
        return ["unknown"] * len(grid)
    return [str(phase or "unknown") for phase in phases]


def _robust_sigma(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    center = median(values)
    return 1.4826 * median(abs(value - center) for value in values)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    left = math.floor(position)
    right = math.ceil(position)
    if left == right:
        return ordered[left]
    weight = position - left
    return ordered[left] * (1.0 - weight) + ordered[right] * weight


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _samples_in_window(
    rows: Sequence[Mapping[str, Any]],
    start_pct: float,
    end_pct: float,
    channel: str | None = None,
) -> int:
    return sum(
        1
        for row in rows
        if (pct := _row_lap_pct(row)) is not None
        and start_pct <= pct <= end_pct
        and (channel is None or _finite(row.get(channel)) is not None)
    )


def _blocked_opportunity_report(
    run_id: str,
    setup_id: str | None,
    eligible: Sequence[LapSummary],
    rows: Sequence[Mapping[str, Any]],
    blockers: Sequence[str],
) -> OpportunitySignatureReport:
    return OpportunitySignatureReport(
        status=ObservationStatus.BLOCKED,
        run_id=run_id,
        setup_id=setup_id,
        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        eligible_lap_numbers=tuple(lap.lap_number for lap in eligible),
        eligible_lap_count=len(eligible),
        telemetry_sample_count=len(rows),
        blocker_reasons=tuple(dict.fromkeys(blockers)),
    )


def build_opportunity_signatures(
    rows: Sequence[Mapping[str, Any]],
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    setup_id: str | None,
    lap_setup_ids: Mapping[int, str] | None = None,
    grid_step_pct: float = 0.25,
    minimum_window_pct: float = 0.75,
    minimum_segment_loss_s: float = 0.004,
    minimum_repetitions: int = 2,
    maximum_signatures: int = 3,
) -> OpportunitySignatureReport:
    """Find repeated segment-time loss against the best same-setup execution.

    This is an observational opportunity, not a setup recommendation.  At least
    three eligible laps establish the cohort and at least two distinct laps must
    repeat the physical-position loss.
    """
    normalized, eligible, identity_blockers = _identity_and_eligibility(
        rows,
        laps,
        run_id=run_id,
        setup_id=setup_id,
        lap_setup_ids=lap_setup_ids,
    )
    blockers = list(identity_blockers)
    if len(eligible) < 3:
        blockers.append("At least three eligible same-setup laps are required.")
    if minimum_repetitions < 2:
        blockers.append("Opportunity repetition must represent at least two distinct laps.")
    if not math.isfinite(grid_step_pct) or not 0.05 <= grid_step_pct <= 2.0:
        blockers.append("Opportunity grid resolution must be between 0.05% and 2.0% of a lap.")
    if not math.isfinite(minimum_window_pct) or minimum_window_pct < grid_step_pct:
        blockers.append("The minimum opportunity window must span at least one aligned interval.")
    if blockers:
        return _blocked_opportunity_report(run_id, setup_id, eligible, normalized, blockers)

    lap_numbers = tuple(lap.lap_number for lap in eligible)
    grouped = _lap_rows(normalized, lap_numbers)
    channel_blockers = _required_channel_blockers(grouped, _OPPORTUNITY_CHANNELS)
    if channel_blockers:
        return _blocked_opportunity_report(
            run_id, setup_id, eligible, normalized, channel_blockers
        )
    grid = build_lap_grid(0.0, 100.0, grid_step_pct)
    gridded, coverage_blockers = _grid_channels(grouped, ("session_time",), grid)
    if coverage_blockers:
        return _blocked_opportunity_report(
            run_id, setup_id, eligible, normalized, coverage_blockers
        )
    phases = _phase_grid(grouped, grid)
    durations: dict[int, list[float | None]] = {}
    for lap_number, channels in gridded.items():
        times = channels["session_time"]
        durations[lap_number] = [None] + [
            right - left
            if left is not None and right is not None and right > left
            else None
            for left, right in zip(times, times[1:])
        ]

    points: list[dict[str, Any] | None] = [None]
    for index in range(1, len(grid)):
        values_by_lap = {
            lap_number: values[index]
            for lap_number, values in durations.items()
            if values[index] is not None
        }
        if len(values_by_lap) != len(lap_numbers):
            points.append(None)
            continue
        values = [float(value) for value in values_by_lap.values() if value is not None]
        best = min(values)
        noise = _robust_sigma(values)
        threshold = max(minimum_segment_loss_s, noise)
        losses = {
            lap_number: max(0.0, float(value) - best)
            for lap_number, value in values_by_lap.items()
            if value is not None
        }
        supporters = tuple(
            lap_number for lap_number, loss in losses.items() if loss >= threshold
        )
        point_loss = median(list(losses.values()))
        points.append(
            {
                "phase": phases[index],
                "supporters": supporters,
                "loss": point_loss,
                "noise": noise,
            }
            if len(supporters) >= minimum_repetitions and point_loss > 0.0
            else None
        )

    groups: list[list[int]] = []
    for index, point in enumerate(points):
        if point is None:
            continue
        if (
            not groups
            or index != groups[-1][-1] + 1
            or points[groups[-1][-1]]["phase"] != point["phase"]  # type: ignore[index]
        ):
            groups.append([index])
        else:
            groups[-1].append(index)

    signatures: list[OpportunitySignature] = []
    assert setup_id is not None
    for indices in groups:
        start_pct = grid[max(0, indices[0] - 1)]
        end_pct = grid[indices[-1]]
        if end_pct - start_pct + 1e-9 < minimum_window_pct:
            continue
        support_requirement = math.ceil(0.7 * len(indices))
        supporter_laps = tuple(
            lap_number
            for lap_number in lap_numbers
            if sum(
                lap_number in points[index]["supporters"]  # type: ignore[index]
                for index in indices
            )
            >= support_requirement
        )
        if len(supporter_laps) < minimum_repetitions:
            continue
        peak_index = max(indices, key=lambda index: points[index]["loss"])  # type: ignore[index]
        phase = str(points[peak_index]["phase"])  # type: ignore[index]
        citations = tuple(
            ObservationCitation(
                run_id=run_id,
                lap_number=lap_number,
                setup_id=setup_id,
                lap_pct_start=start_pct,
                lap_pct_end=end_pct,
                lap_pct_peak=grid[peak_index],
                phase=phase,
                evidence_state=EvidenceState.OBSERVED_CORRELATION,
                source_channels=_OPPORTUNITY_CHANNELS,
                telemetry_sample_count=max(
                    1, _samples_in_window(grouped[lap_number], start_pct, end_pct)
                ),
            )
            for lap_number in supporter_laps
        )
        median_opportunity_s = round(
            sum(float(points[index]["loss"]) for index in indices), 6  # type: ignore[index]
        )
        empirical_noise_s = round(
            sum(float(points[index]["noise"]) for index in indices), 6  # type: ignore[index]
        )
        if median_opportunity_s <= empirical_noise_s:
            continue
        signatures.append(
            OpportunitySignature(
                signature_id=_stable_id(
                    "opportunity", run_id, setup_id, phase, start_pct, end_pct
                ),
                run_id=run_id,
                setup_id=setup_id,
                phase=phase,
                lap_pct_start=start_pct,
                lap_pct_end=end_pct,
                lap_pct_peak=grid[peak_index],
                eligible_lap_count=len(eligible),
                repetition_count=len(supporter_laps),
                telemetry_sample_count=sum(
                    citation.telemetry_sample_count for citation in citations
                ),
                aligned_bin_count=len(indices),
                median_opportunity_s=median_opportunity_s,
                empirical_noise_s=empirical_noise_s,
                source_channels=_OPPORTUNITY_CHANNELS,
                citations=citations,
            )
        )
    signatures.sort(
        key=lambda item: (-item.median_opportunity_s, item.lap_pct_start, item.phase)
    )
    signatures = signatures[: max(1, maximum_signatures)]
    return OpportunitySignatureReport(
        status=ObservationStatus.READY if signatures else ObservationStatus.NO_FINDING,
        run_id=run_id,
        setup_id=setup_id,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=_OPPORTUNITY_CHANNELS,
        eligible_lap_numbers=lap_numbers,
        eligible_lap_count=len(eligible),
        telemetry_sample_count=sum(len(grouped[number]) for number in lap_numbers),
        signatures=tuple(signatures),
    )


def _mechanism_kind(*values: str) -> MechanismKind:
    text = " ".join(values).casefold().replace("-", "_")
    mappings = (
        (("driver", "line", "correction"), MechanismKind.DRIVER_EXECUTION),
        (("brake", "braking", "abs", "lock"), MechanismKind.BRAKING_RESPONSE),
        (("rotation", "yaw", "corner_balance"), MechanismKind.CORNER_ROTATION),
        (("tire", "wear", "thermal"), MechanismKind.TIRE_STATE),
        (("damper", "shock", "suspension"), MechanismKind.DAMPER_RESPONSE),
        (("platform", "ride_height", "bottom"), MechanismKind.PLATFORM_RESPONSE),
        (("resistance", "scrub", "coastdown"), MechanismKind.RESISTANCE_SCRUB_LIKE),
        (("powertrain", "gear", "rpm", "shift"), MechanismKind.POWERTRAIN_RESPONSE),
        (("stint", "degradation", "strategy"), MechanismKind.STINT_TREND),
        (("integrity", "latency", "dropped_tick"), MechanismKind.SIM_INTEGRITY),
    )
    return next(
        (kind for needles, kind in mappings if any(needle in text for needle in needles)),
        MechanismKind.UNCLASSIFIED,
    )


def _event_window(event: TelemetryEvent) -> tuple[float, float, float] | None:
    peak = _finite(event.lap_pct_peak)
    start = _finite(event.lap_pct_start)
    end = _finite(event.lap_pct_end)
    if peak is not None:
        start = peak if start is None else start
        end = peak if end is None else end
    if start is None or end is None:
        return None
    peak = (start + end) / 2.0 if peak is None else peak
    if not 0.0 <= start <= peak <= end <= 100.0:
        return None
    return start, end, peak


def _positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number > 0 else default


def _safe_event_phase(event: TelemetryEvent, mechanism: MechanismKind) -> str:
    """Keep event scope machine-like so producer prose cannot become UI copy."""
    candidate = str(event.event_subtype or event.event_type or "").strip()
    if (
        candidate
        and len(candidate) <= 64
        and all(character.isalnum() or character in {"_", "-", ":"} for character in candidate)
    ):
        return candidate
    return mechanism.value


def adapt_event_mechanism_observations(
    events: Sequence[TelemetryEvent],
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    setup_id: str | None,
) -> MechanismObservationReport:
    """Convert producer-qualified telemetry events into non-authorizing observations."""
    eligible_by_number = {
        lap.lap_number: lap for lap in eligible_laps(laps) if lap.run_id == run_id
    }
    global_blockers: list[str] = []
    if setup_id is None or not setup_id.strip():
        global_blockers.append("A recorded setup identity is required for mechanism scope.")
    if any(lap.run_id != run_id for lap in laps):
        global_blockers.append("A lap summary belongs to a different run than requested.")
    if any(event.run_id != run_id for event in events):
        global_blockers.append("A telemetry event belongs to a different run than requested.")
    if global_blockers:
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=tuple(dict.fromkeys(global_blockers)),
        )
    observations: list[MechanismObservation] = []
    assert setup_id is not None
    for event in events:
        mechanism = _mechanism_kind(event.event_type, event.event_subtype or "")
        blockers = list(event.blocker_reasons)
        window = _event_window(event)
        if event.lap_number is None or event.lap_number not in eligible_by_number:
            blockers.append("The event is not linked to an eligible lap in this run.")
        if window is None:
            blockers.append("The event has no complete physical-position window.")
        if not event.valid_for_tuning:
            blockers.append("The producing engine did not qualify this event for tuning evidence.")
        if event.valid_for_tuning and event.confidence_score <= 0.0:
            blockers.append(
                "The producer marked the event valid for tuning but supplied no positive "
                "confidence; the evidence contract is incoherent."
            )
        if event.evidence_state not in _QUALIFIED_STATES:
            blockers.append("The event does not carry a qualified evidence state.")
        if not event.source_channels or any(not channel for channel in event.source_channels):
            blockers.append("The event has no complete source-channel provenance.")
        blockers = list(dict.fromkeys(blockers))
        phase = _safe_event_phase(event, mechanism)
        sample_count = _positive_int(event.evidence_json.get("sample_count"), 1)
        if blockers:
            observations.append(
                MechanismObservation(
                    observation_id=f"event:{event.event_id}",
                    mechanism=mechanism,
                    run_id=run_id,
                    setup_id=setup_id,
                    lap_number=event.lap_number,
                    phase=phase,
                    lap_pct_start=window[0] if window else None,
                    lap_pct_end=window[1] if window else None,
                    lap_pct_peak=window[2] if window else None,
                    summary="The producer observation was retained but is not evidence-qualified.",
                    evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                    qualified=False,
                    source_channels=_ordered_unique(event.source_channels),
                    required_channels=_ordered_unique(event.source_channels),
                    telemetry_sample_count=sample_count,
                    repetition_count=0,
                    blocker_reasons=tuple(blockers),
                )
            )
            continue
        assert event.lap_number is not None
        assert window is not None
        citation = ObservationCitation(
            run_id=run_id,
            lap_number=event.lap_number,
            setup_id=setup_id,
            lap_pct_start=window[0],
            lap_pct_end=window[1],
            lap_pct_peak=window[2],
            phase=phase,
            evidence_state=event.evidence_state,
            source_channels=_ordered_unique(event.source_channels),
            event_id=event.event_id,
            telemetry_sample_count=sample_count,
        )
        source_channels = _ordered_unique(event.source_channels)
        mechanism_label = mechanism.value.replace("_", " ")
        observations.append(
            MechanismObservation(
                observation_id=f"event:{event.event_id}",
                mechanism=mechanism,
                run_id=run_id,
                setup_id=setup_id,
                lap_number=event.lap_number,
                phase=phase,
                lap_pct_start=window[0],
                lap_pct_end=window[1],
                lap_pct_peak=window[2],
                summary=(
                    f"Producer-qualified {mechanism_label} evidence was observed on an "
                    "eligible lap at an exact physical-position window."
                ),
                evidence_state=event.evidence_state,
                qualified=True,
                source_channels=source_channels,
                required_channels=source_channels,
                supporting_evidence=(
                    "The producing engine tied the observation to an eligible lap and an "
                    "exact physical-position window.",
                    f"The event declares {sample_count} source samples across "
                    f"{len(source_channels)} named telemetry channels; exact rows must be "
                    "revalidated before publication.",
                ),
                telemetry_sample_count=sample_count,
                repetition_count=1,
                citations=(citation,),
            )
        )
    qualified = [item for item in observations if item.qualified]
    blocked = [reason for item in observations for reason in item.blocker_reasons]
    return MechanismObservationReport(
        status=(
            ObservationStatus.READY
            if qualified
            else ObservationStatus.BLOCKED
            if observations
            else ObservationStatus.NO_FINDING
        ),
        run_id=run_id,
        setup_id=setup_id,
        observations=tuple(observations),
        blocker_reasons=tuple(dict.fromkeys(blocked)) if observations and not qualified else (),
    )


def adapt_p3_report_observations(
    report: Any,
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    setup_id: str | None,
    lap_number: int,
    phase: str,
    lap_pct_start: float,
    lap_pct_end: float,
    lap_pct_peak: float,
    telemetry_sample_count: int,
    repetition_count: int | None = None,
) -> MechanismObservationReport:
    """Adapt an existing P3 report without propagating its setup recommendation text."""
    gate = getattr(report, "gate", None)
    conclusions = tuple(getattr(report, "conclusions", ()) or ())
    eligible = tuple(lap for lap in eligible_laps(laps) if lap.run_id == run_id)
    blockers: list[str] = []
    if any(lap.run_id != run_id for lap in laps):
        blockers.append("A lap summary belongs to a different run than requested.")
    if setup_id is None or not setup_id.strip():
        blockers.append("A recorded setup identity is required for mechanism scope.")
    if lap_number not in {lap.lap_number for lap in eligible}:
        blockers.append("The selected P3 lap is not eligible in the requested run.")
    if gate is None or getattr(gate, "eligible", False) is not True:
        blockers.extend(tuple(getattr(gate, "blocker_reasons", ()) or ()))
        blockers.append("The producing P3 evidence contract did not pass.")
    if not 0.0 <= lap_pct_start <= lap_pct_peak <= lap_pct_end <= 100.0:
        blockers.append("The P3 adapter requires one exact physical-position window.")
    if telemetry_sample_count < 1:
        blockers.append("The P3 adapter requires a positive telemetry sample count.")
    if not conclusions:
        blockers.append("The P3 report has no conclusions to adapt.")
    if blockers:
        return MechanismObservationReport(
            status=ObservationStatus.BLOCKED,
            run_id=run_id,
            setup_id=setup_id,
            blocker_reasons=tuple(dict.fromkeys(blockers)),
        )
    assert setup_id is not None
    # This generic adapter publishes one exact selected-lap citation.  Cohort
    # counts from a producer are not evidence that every conclusion repeated on
    # those laps; a bridge may add exact per-lap citations afterwards.
    del repetition_count
    observations: list[MechanismObservation] = []
    for index, conclusion in enumerate(conclusions):
        if not isinstance(conclusion, EngineeringConclusion):
            continue
        item_blockers = list(conclusion.blocker_reasons)
        if conclusion.evidence_state not in _QUALIFIED_STATES:
            item_blockers.append("The P3 conclusion is not evidence-qualified.")
        if not conclusion.source_channels:
            item_blockers.append("The P3 conclusion has no source-channel provenance.")
        if not conclusion.supporting_evidence:
            item_blockers.append("The P3 conclusion has no supporting evidence statements.")
        item_blockers = list(dict.fromkeys(item_blockers))
        observation_id = _stable_id(
            "p3", run_id, lap_number, conclusion.key, phase, lap_pct_start, lap_pct_end, index
        )
        if item_blockers:
            observations.append(
                MechanismObservation(
                    observation_id=observation_id,
                    mechanism=_mechanism_kind(
                        str(getattr(gate, "contract_key", "")), conclusion.key
                    ),
                    run_id=run_id,
                    setup_id=setup_id,
                    lap_number=lap_number,
                    phase=phase,
                    lap_pct_start=lap_pct_start,
                    lap_pct_end=lap_pct_end,
                    lap_pct_peak=lap_pct_peak,
                    summary="The P3 observation was retained but is not evidence-qualified.",
                    evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                    source_channels=_ordered_unique(conclusion.source_channels),
                    required_channels=_ordered_unique(conclusion.source_channels),
                    telemetry_sample_count=telemetry_sample_count,
                    repetition_count=0,
                    blocker_reasons=tuple(item_blockers),
                )
            )
            continue
        citation = ObservationCitation(
            run_id=run_id,
            lap_number=lap_number,
            setup_id=setup_id,
            lap_pct_start=lap_pct_start,
            lap_pct_end=lap_pct_end,
            lap_pct_peak=lap_pct_peak,
            phase=phase,
            evidence_state=conclusion.evidence_state,
            source_channels=_ordered_unique(conclusion.source_channels),
            telemetry_sample_count=telemetry_sample_count,
        )
        observations.append(
            MechanismObservation(
                observation_id=observation_id,
                mechanism=_mechanism_kind(
                    str(getattr(gate, "contract_key", "")), conclusion.key
                ),
                run_id=run_id,
                setup_id=setup_id,
                lap_number=lap_number,
                phase=phase,
                lap_pct_start=lap_pct_start,
                lap_pct_end=lap_pct_end,
                lap_pct_peak=lap_pct_peak,
                summary=conclusion.summary,
                evidence_state=conclusion.evidence_state,
                qualified=True,
                source_channels=_ordered_unique(conclusion.source_channels),
                required_channels=_ordered_unique(conclusion.source_channels),
                supporting_evidence=tuple(conclusion.supporting_evidence),
                contradicting_evidence=tuple(conclusion.contradicting_evidence),
                telemetry_sample_count=telemetry_sample_count,
                repetition_count=1,
                citations=(citation,),
            )
        )
    qualified = [item for item in observations if item.qualified]
    blocked = [reason for item in observations for reason in item.blocker_reasons]
    return MechanismObservationReport(
        status=(
            ObservationStatus.READY
            if qualified
            else ObservationStatus.BLOCKED
            if observations
            else ObservationStatus.NO_FINDING
        ),
        run_id=run_id,
        setup_id=setup_id,
        observations=tuple(observations),
        blocker_reasons=tuple(dict.fromkeys(blocked)) if observations and not qualified else (),
    )


def _blocked_anomaly_report(
    run_id: str,
    setup_id: str | None,
    channels: Sequence[str],
    eligible: Sequence[LapSummary],
    rows: Sequence[Mapping[str, Any]],
    blockers: Sequence[str],
) -> SameSetupAnomalyReport:
    return SameSetupAnomalyReport(
        status=ObservationStatus.BLOCKED,
        run_id=run_id,
        setup_id=setup_id,
        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        required_channels=(_POSITION_CHANNEL, *tuple(channels)),
        eligible_lap_numbers=tuple(lap.lap_number for lap in eligible),
        eligible_lap_count=len(eligible),
        reference_lap_count=max(0, len(eligible) - 1),
        telemetry_sample_count=len(rows),
        blocker_reasons=tuple(dict.fromkeys(blockers)),
    )


def _competing_anomaly_context_splits(
    anomalies: Sequence[SameSetupAnomaly],
    *,
    eligible_lap_count: int,
    minimum_sustained_pct: float,
) -> tuple[str, ...]:
    """Detect reciprocal leave-one-out findings that indicate two cohorts, not outliers."""
    if eligible_lap_count < 4:
        return ()
    minimum_group_size = max(2, math.ceil(0.3 * eligible_lap_count))
    split_channels: list[str] = []
    for channel in _ordered_unique(tuple(item.channel for item in anomalies)):
        channel_items = tuple(item for item in anomalies if item.channel == channel)
        positions = build_lap_grid(0.0, 100.0, _ANOMALY_SCOPE_RESOLUTION_PCT)
        competing = [
            len({
                item.lap_number
                for item in channel_items
                if item.direction == "above_envelope"
                and item.lap_pct_start <= position <= item.lap_pct_end
            })
            >= minimum_group_size
            and len({
                item.lap_number
                for item in channel_items
                if item.direction == "below_envelope"
                and item.lap_pct_start <= position <= item.lap_pct_end
            })
            >= minimum_group_size
            for position in positions
        ]
        groups: list[list[int]] = []
        for index, is_competing in enumerate(competing):
            if not is_competing:
                continue
            if not groups or index != groups[-1][-1] + 1:
                groups.append([index])
            else:
                groups[-1].append(index)
        if any(
            positions[indices[-1]] - positions[indices[0]] + 1e-9
            >= minimum_sustained_pct
            for indices in groups
        ):
            split_channels.append(channel)
    return tuple(split_channels)


def build_same_setup_anomaly_envelopes(
    rows: Sequence[Mapping[str, Any]],
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    setup_id: str | None,
    channels: Sequence[str],
    lap_setup_ids: Mapping[int, str] | None = None,
    grid_step_pct: float = 0.25,
    minimum_sustained_pct: float = 0.75,
    mad_multiplier: float = 3.5,
    minimum_absolute_deviation: Mapping[str, float] | None = None,
) -> SameSetupAnomalyReport:
    """Detect sustained leave-one-lap-out deviations from a same-setup envelope."""
    requested_channels = _ordered_unique(tuple(channels))
    normalized, eligible, identity_blockers = _identity_and_eligibility(
        rows,
        laps,
        run_id=run_id,
        setup_id=setup_id,
        lap_setup_ids=lap_setup_ids,
    )
    blockers = list(identity_blockers)
    if not requested_channels:
        blockers.append("At least one anomaly channel is required.")
    if len(eligible) < 3:
        blockers.append("At least three eligible same-setup laps are required.")
    if not math.isfinite(grid_step_pct) or not 0.05 <= grid_step_pct <= 2.0:
        blockers.append("Anomaly grid resolution must be between 0.05% and 2.0% of a lap.")
    if not math.isfinite(minimum_sustained_pct) or minimum_sustained_pct < grid_step_pct:
        blockers.append("A sustained anomaly must span at least one aligned interval.")
    if not math.isfinite(mad_multiplier) or mad_multiplier <= 0.0:
        blockers.append("The anomaly MAD multiplier must be positive and finite.")
    if blockers:
        return _blocked_anomaly_report(
            run_id, setup_id, requested_channels, eligible, normalized, blockers
        )
    lap_numbers = tuple(lap.lap_number for lap in eligible)
    grouped = _lap_rows(normalized, lap_numbers)
    channel_blockers = _required_channel_blockers(grouped, requested_channels)
    if channel_blockers:
        return _blocked_anomaly_report(
            run_id, setup_id, requested_channels, eligible, normalized, channel_blockers
        )
    grid = build_lap_grid(0.0, 100.0, grid_step_pct)
    gridded, coverage_blockers = _grid_channels(grouped, requested_channels, grid)
    if coverage_blockers:
        return _blocked_anomaly_report(
            run_id, setup_id, requested_channels, eligible, normalized, coverage_blockers
        )
    phases = _phase_grid(grouped, grid)
    configured_floors = dict(minimum_absolute_deviation or {})
    invalid_floors = [
        channel
        for channel, value in configured_floors.items()
        if _finite(value) is None or float(value) < 0.0
    ]
    if invalid_floors:
        return _blocked_anomaly_report(
            run_id,
            setup_id,
            requested_channels,
            eligible,
            normalized,
            ("Every anomaly absolute-deviation floor must be finite and non-negative.",),
        )

    anomalies: list[SameSetupAnomaly] = []
    assert setup_id is not None
    for channel in requested_channels:
        floor = float(configured_floors.get(channel, _ANOMALY_FLOORS.get(channel, 1e-6)))
        for lap_number in lap_numbers:
            flags: list[dict[str, Any] | None] = []
            for index in range(len(grid)):
                observed = gridded[lap_number][channel][index]
                reference = [
                    gridded[other][channel][index]
                    for other in lap_numbers
                    if other != lap_number and gridded[other][channel][index] is not None
                ]
                if observed is None or len(reference) != len(lap_numbers) - 1:
                    flags.append(None)
                    continue
                reference_values = [float(value) for value in reference if value is not None]
                center = median(reference_values)
                mad = median(abs(value - center) for value in reference_values)
                threshold = max(floor, mad_multiplier * 1.4826 * mad)
                deviation = observed - center
                flags.append(
                    {
                        "direction": "above_envelope" if deviation > 0.0 else "below_envelope",
                        "observed": observed,
                        "reference": center,
                        "mad": mad,
                        "magnitude": abs(deviation),
                        "phase": phases[index],
                    }
                    if abs(deviation) > threshold
                    else None
                )
            groups: list[list[int]] = []
            for index, flag in enumerate(flags):
                if flag is None:
                    continue
                if (
                    not groups
                    or index != groups[-1][-1] + 1
                    or flags[groups[-1][-1]]["direction"] != flag["direction"]  # type: ignore[index]
                    or flags[groups[-1][-1]]["phase"] != flag["phase"]  # type: ignore[index]
                ):
                    groups.append([index])
                else:
                    groups[-1].append(index)
            for indices in groups:
                raw_start_pct = grid[indices[0]]
                raw_end_pct = grid[indices[-1]]
                if raw_end_pct - raw_start_pct + 1e-9 < minimum_sustained_pct:
                    continue
                # Linear interpolation around a step can add one boundary bin
                # when a source is sampled more sparsely.  Publish anomaly
                # scope only at a fixed physical resolution and trim the
                # calculation to that scope; row rate must not move a finding.
                start_pct = round(
                    round(raw_start_pct / _ANOMALY_SCOPE_RESOLUTION_PCT)
                    * _ANOMALY_SCOPE_RESOLUTION_PCT,
                    2,
                )
                end_pct = round(
                    round(raw_end_pct / _ANOMALY_SCOPE_RESOLUTION_PCT)
                    * _ANOMALY_SCOPE_RESOLUTION_PCT,
                    2,
                )
                indices = [
                    index for index in indices if start_pct <= grid[index] <= end_pct
                ]
                if (
                    not indices
                    or end_pct - start_pct + 1e-9 < minimum_sustained_pct
                ):
                    continue
                peak_index = max(
                    indices, key=lambda index: flags[index]["magnitude"]  # type: ignore[index]
                )
                phase = str(flags[peak_index]["phase"])  # type: ignore[index]
                sample_count = max(
                    1,
                    _samples_in_window(
                        grouped[lap_number], start_pct, end_pct, channel
                    ),
                )
                citation = ObservationCitation(
                    run_id=run_id,
                    lap_number=lap_number,
                    setup_id=setup_id,
                    lap_pct_start=start_pct,
                    lap_pct_end=end_pct,
                    lap_pct_peak=grid[peak_index],
                    phase=phase,
                    evidence_state=EvidenceState.OBSERVED_CORRELATION,
                    source_channels=(_POSITION_CHANNEL, channel),
                    telemetry_sample_count=sample_count,
                )
                references = tuple(number for number in lap_numbers if number != lap_number)
                anomalies.append(
                    SameSetupAnomaly(
                        anomaly_id=_stable_id(
                            "anomaly",
                            run_id,
                            setup_id,
                            lap_number,
                            channel,
                            start_pct,
                            end_pct,
                        ),
                        run_id=run_id,
                        setup_id=setup_id,
                        lap_number=lap_number,
                        channel=channel,
                        direction=str(flags[peak_index]["direction"]),  # type: ignore[index,arg-type]
                        phase=phase,
                        lap_pct_start=start_pct,
                        lap_pct_end=end_pct,
                        lap_pct_peak=grid[peak_index],
                        reference_lap_numbers=references,
                        repetition_count=len(references),
                        telemetry_sample_count=sample_count,
                        aligned_bin_count=len(indices),
                        median_observed_value=round(
                            median([float(flags[index]["observed"]) for index in indices]), 8  # type: ignore[index]
                        ),
                        median_reference_value=round(
                            median([float(flags[index]["reference"]) for index in indices]), 8  # type: ignore[index]
                        ),
                        median_absolute_deviation=round(
                            median([float(flags[index]["mad"]) for index in indices]), 8  # type: ignore[index]
                        ),
                        source_channels=(_POSITION_CHANNEL, channel),
                        citations=(citation,),
                    )
                )
    anomalies.sort(key=lambda item: (item.lap_number, item.lap_pct_start, item.channel))
    context_splits = _competing_anomaly_context_splits(
        anomalies,
        eligible_lap_count=len(lap_numbers),
        minimum_sustained_pct=minimum_sustained_pct,
    )
    if context_splits:
        return _blocked_anomaly_report(
            run_id,
            setup_id,
            requested_channels,
            eligible,
            normalized,
            (
                "Reciprocal high-frequency same-setup findings overlap for "
                + ", ".join(context_splits)
                + "; the cohort contains an unresolved context split, so neither mode is "
                "published as an anomalous lap.",
            ),
        )
    return SameSetupAnomalyReport(
        status=ObservationStatus.READY if anomalies else ObservationStatus.NO_FINDING,
        run_id=run_id,
        setup_id=setup_id,
        evidence_state=(
            EvidenceState.OBSERVED_CORRELATION if anomalies else EvidenceState.CALCULATED
        ),
        required_channels=(_POSITION_CHANNEL, *requested_channels),
        source_channels=(_POSITION_CHANNEL, *requested_channels),
        eligible_lap_numbers=lap_numbers,
        eligible_lap_count=len(eligible),
        reference_lap_count=len(eligible) - 1,
        telemetry_sample_count=sum(len(grouped[number]) for number in lap_numbers),
        anomalies=tuple(anomalies),
    )


def _pairwise_robust_spread(values: Sequence[float]) -> float:
    differences = [
        abs(right - left)
        for index, left in enumerate(values)
        for right in values[index + 1 :]
    ]
    return median(differences) if differences else 0.0


def _blocked_driver_signature(
    run_id: str,
    setup_id: str | None,
    eligible: Sequence[LapSummary],
    rows: Sequence[Mapping[str, Any]],
    blockers: Sequence[str],
) -> DriverRepeatabilitySignature:
    return DriverRepeatabilitySignature(
        status=ObservationStatus.BLOCKED,
        run_id=run_id,
        setup_id=setup_id,
        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
        eligible_lap_numbers=tuple(lap.lap_number for lap in eligible),
        eligible_lap_count=len(eligible),
        telemetry_sample_count=len(rows),
        blocker_reasons=tuple(dict.fromkeys(blockers)),
    )


def build_driver_repeatability_signature(
    rows: Sequence[Mapping[str, Any]],
    laps: Sequence[LapSummary],
    *,
    run_id: str,
    setup_id: str | None,
    lap_setup_ids: Mapping[int, str] | None = None,
    grid_step_pct: float = 0.25,
    minimum_focus_window_pct: float = 0.75,
) -> DriverRepeatabilitySignature:
    """Build one position-aligned driving-practice focus; never authorize setup."""
    normalized, eligible, identity_blockers = _identity_and_eligibility(
        rows,
        laps,
        run_id=run_id,
        setup_id=setup_id,
        lap_setup_ids=lap_setup_ids,
    )
    blockers = list(identity_blockers)
    if len(eligible) < 3:
        blockers.append("At least three eligible same-setup laps are required.")
    if not math.isfinite(grid_step_pct) or not 0.05 <= grid_step_pct <= 2.0:
        blockers.append("Driver grid resolution must be between 0.05% and 2.0% of a lap.")
    if not math.isfinite(minimum_focus_window_pct) or minimum_focus_window_pct < grid_step_pct:
        blockers.append("A driver focus must span at least one aligned interval.")
    if blockers:
        return _blocked_driver_signature(run_id, setup_id, eligible, normalized, blockers)
    lap_numbers = tuple(lap.lap_number for lap in eligible)
    grouped = _lap_rows(normalized, lap_numbers)
    channel_blockers = _required_channel_blockers(grouped, _DRIVER_CHANNELS)
    if channel_blockers:
        return _blocked_driver_signature(
            run_id, setup_id, eligible, normalized, channel_blockers
        )
    grid = build_lap_grid(0.0, 100.0, grid_step_pct)
    gridded, coverage_blockers = _grid_channels(grouped, _DRIVER_CHANNELS, grid)
    if coverage_blockers:
        return _blocked_driver_signature(
            run_id, setup_id, eligible, normalized, coverage_blockers
        )
    incomplete_common_grid = [
        (
            number,
            channel,
            sum(value is not None for value in gridded[number][channel]) / len(grid),
        )
        for number in lap_numbers
        for channel in _DRIVER_CHANNELS
        if any(value is None for value in gridded[number][channel])
    ]
    if incomplete_common_grid:
        detail = ", ".join(
            f"lap {number} {channel} {coverage:.0%}"
            for number, channel, coverage in incomplete_common_grid
        )
        return _blocked_driver_signature(
            run_id,
            setup_id,
            eligible,
            normalized,
            (
                "Driver repeatability requires a complete common physical-position grid; "
                f"incomplete aligned coverage remains for {detail}.",
            ),
        )
    phases = _phase_grid(grouped, grid)
    spreads: dict[str, list[float]] = {}
    channel_summaries: list[DriverChannelRepeatability] = []
    for channel in _DRIVER_CHANNELS:
        values = [
            _pairwise_robust_spread(
                [float(gridded[number][channel][index]) for number in lap_numbers]  # type: ignore[arg-type]
            )
            for index in range(len(grid))
        ]
        spreads[channel] = values
        channel_summaries.append(
            DriverChannelRepeatability(
                channel=channel,
                unit=_DRIVER_UNITS[channel],
                median_robust_spread=round(median(values), 6),
                p90_robust_spread=round(_percentile(values, 0.9), 6),
                aligned_bin_count=len(values),
            )
        )

    candidate_groups: list[tuple[float, str, list[int]]] = []
    for channel, values in spreads.items():
        limit = _DRIVER_SPREAD_LIMITS[channel]
        flagged = [value >= limit for value in values]
        groups: list[list[int]] = []
        for index, is_flagged in enumerate(flagged):
            if not is_flagged:
                continue
            if (
                not groups
                or index != groups[-1][-1] + 1
                or phases[groups[-1][-1]] != phases[index]
            ):
                groups.append([index])
            else:
                groups[-1].append(index)
        for indices in groups:
            if grid[indices[-1]] - grid[indices[0]] + 1e-9 < minimum_focus_window_pct:
                continue
            # Keep the sustained core of the variation.  Interpolated edge
            # ramps move with source sample rate; the high-variation core does
            # not, and is the useful coaching scope.
            core_threshold = max(
                limit,
                0.75 * median([values[index] for index in indices]),
            )
            core = [index for index in indices if values[index] >= core_threshold]
            if not core:
                continue
            start_pct = round(
                round(grid[core[0]] / _DRIVER_SCOPE_RESOLUTION_PCT)
                * _DRIVER_SCOPE_RESOLUTION_PCT,
                2,
            )
            end_pct = round(
                round(grid[core[-1]] / _DRIVER_SCOPE_RESOLUTION_PCT)
                * _DRIVER_SCOPE_RESOLUTION_PCT,
                2,
            )
            core = [index for index in core if start_pct <= grid[index] <= end_pct]
            if (
                not core
                or end_pct - start_pct + 1e-9 < minimum_focus_window_pct
            ):
                continue
            score = median([values[index] / limit for index in core])
            candidate_groups.append((score, channel, core))

    focus: DriverCoachingFocus | None = None
    assert setup_id is not None
    if candidate_groups:
        _score, channel, indices = max(
            candidate_groups,
            key=lambda item: (item[0], len(item[2]), -item[2][0]),
        )
        start_pct = round(
            round(grid[indices[0]] / _DRIVER_SCOPE_RESOLUTION_PCT)
            * _DRIVER_SCOPE_RESOLUTION_PCT,
            2,
        )
        end_pct = round(
            round(grid[indices[-1]] / _DRIVER_SCOPE_RESOLUTION_PCT)
            * _DRIVER_SCOPE_RESOLUTION_PCT,
            2,
        )
        phase = phases[max(indices, key=lambda index: spreads[channel][index])]
        instruction_by_channel = {
            "brake_pct": (
                "Repeat this phase without changing setup and use one fixed braking marker; "
                "aim for the same application and release shape on each lap."
            ),
            "throttle_pct": (
                "Repeat this phase without changing setup and use one fixed throttle pickup "
                "marker; aim for the same progression on each lap."
            ),
            "steering_deg": (
                "Repeat this phase without changing setup and use one fixed turn-in reference; "
                "aim for one smooth steering build with fewer corrections."
            ),
        }
        citations = tuple(
            ObservationCitation(
                run_id=run_id,
                lap_number=number,
                setup_id=setup_id,
                lap_pct_start=start_pct,
                lap_pct_end=end_pct,
                lap_pct_peak=grid[max(indices, key=lambda index: spreads[channel][index])],
                phase=phase,
                evidence_state=EvidenceState.CALCULATED,
                source_channels=(_POSITION_CHANNEL, channel),
                telemetry_sample_count=max(
                    1, _samples_in_window(grouped[number], start_pct, end_pct, channel)
                ),
            )
            for number in lap_numbers
        )
        focus = DriverCoachingFocus(
            phase=phase,
            lap_pct_start=start_pct,
            lap_pct_end=end_pct,
            channel=channel,
            instruction=instruction_by_channel[channel],
            success_check=(
                f"On at least three eligible same-setup laps, keep the position-aligned "
                f"{channel.replace('_', ' ')} spread below "
                f"{_DRIVER_SPREAD_LIMITS[channel]:g} {_DRIVER_UNITS[channel]}."
            ),
            citations=citations,
        )
    return DriverRepeatabilitySignature(
        status=ObservationStatus.READY if focus is not None else ObservationStatus.NO_FINDING,
        run_id=run_id,
        setup_id=setup_id,
        evidence_state=EvidenceState.CALCULATED,
        eligible_lap_numbers=lap_numbers,
        eligible_lap_count=len(eligible),
        telemetry_sample_count=sum(len(grouped[number]) for number in lap_numbers),
        source_channels=(_POSITION_CHANNEL, *_DRIVER_CHANNELS),
        channel_repeatability=tuple(channel_summaries),
        focus=focus,
    )


__all__ = [
    "adapt_event_mechanism_observations",
    "adapt_p3_report_observations",
    "build_driver_repeatability_signature",
    "build_opportunity_signatures",
    "build_same_setup_anomaly_envelopes",
]
