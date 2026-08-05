"""Shared fail-closed qualification and numeric helpers for P3 engines."""

from __future__ import annotations

import math
from statistics import mean
from typing import Any, Iterable

from racelab_engine.analysis.evidence_contracts import (
    AnalysisEvidenceContract,
    EvidenceEvaluation,
    EvidenceEvaluationInput,
    evaluate_evidence_contract,
)
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.time_alignment import detect_engineering_phases
from racelab_engine.models.engineering import EngineGate
from racelab_engine.models.lap import LapSummary


def finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def values(rows: Iterable[dict[str, Any]], channel: str) -> list[float]:
    return [number for row in rows if (number := finite(row.get(channel))) is not None]


def average(rows: Iterable[dict[str, Any]], channel: str) -> float | None:
    items = values(rows, channel)
    return mean(items) if items else None


def bounded_confidence(value: Any) -> float:
    """Clamp confidence to 0..1 and fail closed for missing/non-finite input."""
    number = finite(value)
    return max(0.0, min(1.0, number)) if number is not None else 0.0


def percentile(items: list[float], pct: float) -> float | None:
    if not items:
        return None
    ordered = sorted(items)
    index = (len(ordered) - 1) * max(0.0, min(1.0, pct))
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def lap_pct(row: dict[str, Any]) -> float | None:
    percent = finite(row.get("lap_dist_pct_100"))
    if percent is not None:
        return percent if 0.0 <= percent <= 100.0 else None
    number = finite(row.get("lap_dist_pct"))
    if number is None:
        return None
    return number * 100.0 if 0.0 <= number <= 1.5 else number


def lap_number(row: dict[str, Any]) -> int | None:
    number = finite(row.get("lap", row.get("lap_number")))
    return int(number) if number is not None else None


def _phase_rows(
    rows: list[dict[str, Any]],
    target_phases: set[str] | None,
) -> tuple[list[dict[str, Any]], set[str]]:
    explicit = [str(row.get("engineering_phase")) for row in rows if row.get("engineering_phase")]
    if explicit:
        phases = set(explicit)
        selected = [
            row for row in rows
            if not target_phases or str(row.get("engineering_phase")) in target_phases
        ]
        return selected, phases
    grid = sorted({round(pct, 3) for row in rows if (pct := lap_pct(row)) is not None})
    if len(grid) < 3:
        return [], set()
    detector_rows = [
        row if row.get("lap_dist_pct_100") is not None
        else {**row, "lap_dist_pct_100": lap_pct(row)}
        for row in rows
    ]
    phase_by_position, _intervals, _channels = detect_engineering_phases(detector_rows, grid=grid)
    phase_map = dict(zip(grid, phase_by_position))
    annotated: list[dict[str, Any]] = []
    observed: set[str] = set()
    for row in rows:
        pct = lap_pct(row)
        if pct is None:
            continue
        nearest = min(grid, key=lambda item: abs(item - pct))
        phase = phase_map.get(nearest)
        if phase:
            observed.add(phase)
        if not target_phases or phase in target_phases:
            annotated.append({**row, "engineering_phase": phase})
    return annotated, observed


def scope_phase_rows(
    rows: list[dict[str, Any]],
    target_phases: set[str] | None,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Qualify and annotate one lap using either canonical position representation."""
    return _phase_rows(rows, target_phases)


def qualify_phase_engine(
    contract: AnalysisEvidenceContract,
    rows: list[dict[str, Any]],
    lap_summaries: list[LapSummary] | None,
    *,
    selected_lap: int,
    target_phases: set[str] | None,
    sim_integrity_clear: bool | None,
    sim_integrity_confidence_cap: float = 1.0,
    requested_outputs: frozenset[str],
) -> tuple[list[dict[str, Any]], set[str], EvidenceEvaluation, EngineGate]:
    eligible = eligible_laps(lap_summaries or [])
    eligible_numbers = {lap.lap_number for lap in eligible}
    lap_rows = [row for row in rows if lap_number(row) == selected_lap]
    scoped_rows, observed_phases = _phase_rows(lap_rows, target_phases)
    usable = frozenset(
        channel for row in scoped_rows for channel, value in row.items() if finite(value) is not None
    )
    pcts = [pct for row in lap_rows if (pct := lap_pct(row)) is not None]
    evaluation = evaluate_evidence_contract(
        contract,
        EvidenceEvaluationInput(
            usable_channels=usable,
            condition_results={
                "eligible_lap": selected_lap in eligible_numbers,
                "phase_scoped": bool(scoped_rows and observed_phases),
                "track_position_available": bool(pcts and max(pcts) - min(pcts) >= 95.0),
            },
            blocker_results={
                "junk_lap_context": selected_lap not in eligible_numbers,
                "sim_integrity_uncertain": (
                    False if sim_integrity_clear is True else True if sim_integrity_clear is False else None
                ),
            },
            repetitions=len(eligible),
            requested_outputs=requested_outputs,
        ),
    )
    gate = EngineGate(
        contract_key=evaluation.contract_key,
        eligible=evaluation.eligible,
        confidence_cap=min(evaluation.confidence_cap, bounded_confidence(sim_integrity_confidence_cap)),
        blocker_reasons=[item.message for item in evaluation.blockers],
        needed_measurements=[item.instruction for item in evaluation.needed_measurements],
    )
    return scoped_rows, observed_phases, evaluation, gate


def derivative(values_: list[float], times: list[float]) -> list[float]:
    output: list[float] = []
    for previous, current, t0, t1 in zip(values_, values_[1:], times, times[1:]):
        dt = t1 - t0
        if dt > 0:
            output.append((current - previous) / dt)
    return output


def rms(items: list[float]) -> float | None:
    return math.sqrt(sum(item * item for item in items) / len(items)) if items else None


__all__ = [
    "average", "derivative", "finite", "lap_number", "lap_pct", "percentile",
    "qualify_phase_engine", "rms", "values",
]
