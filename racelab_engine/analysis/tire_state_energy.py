"""Per-corner tire state and thermal-origin evidence engine."""

from __future__ import annotations

from statistics import mean
from typing import Any, Literal

from pydantic import Field

from racelab_engine.analysis.p3_common import average, lap_number, qualify_phase_engine, values
from racelab_engine.analysis.p3_contracts import TIRE_STATE_CONTRACT
from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.models.engineering import EngineGate, EngineeringConclusion, EngineeringModel
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap import LapSummary


TireCause = Literal[
    "pressure_driven_heating", "shoulder_load", "surface_scrub", "carcass_heat",
    "braking_heat", "traction_heat", "camber_bias", "aging", "saturation", "falloff",
]
TIRE_PHASES = {
    "brake_application", "threshold_braking", "brake_release", "entry", "center",
    "apex_region", "initial_throttle", "full_throttle_exit", "straight",
}


class TireCornerState(EngineeringModel):
    corner: Literal["LF", "RF", "LR", "RR"]
    running_pressure: float | None = None
    cold_pressure: float | None = None
    pressure_gain: float | None = None
    surface_inner: float | None = None
    surface_middle: float | None = None
    surface_outer: float | None = None
    surface_average: float | None = None
    carcass_average: float | None = None
    middle_vs_shoulders: float | None = None
    inner_outer_gradient: float | None = None
    wear_inner: float | None = None
    wear_middle: float | None = None
    wear_outer: float | None = None
    tire_distance_m: float | None = None
    slip_ratio_rms: float | None = None
    load_context_proxy: float | None = None
    cause_classes: list[TireCause] = Field(default_factory=list)


class TireStateReport(EngineeringModel):
    selected_lap: int
    phases: list[str] = Field(default_factory=list)
    gate: EngineGate
    corners: list[TireCornerState] = Field(default_factory=list)
    conclusions: list[EngineeringConclusion] = Field(default_factory=list)
    working_history_laps: int = 0


def _avg_optional(items: list[float | None]) -> float | None:
    present = [item for item in items if item is not None]
    return mean(present) if present else None


def _rms(items: list[float]) -> float | None:
    return (sum(item * item for item in items) / len(items)) ** 0.5 if items else None


def _repeated_pressure_pattern(
    rows: list[dict[str, Any]],
    eligible_numbers: set[int],
    corner: str,
) -> int:
    repeated = 0
    for number in eligible_numbers:
        lap_rows = [row for row in rows if lap_number(row) == number]
        inner = average(lap_rows, f"{corner}_temp_inner")
        middle = average(lap_rows, f"{corner}_temp_middle")
        outer = average(lap_rows, f"{corner}_temp_outer")
        running = average(lap_rows, f"{corner}_pressure")
        cold = average(lap_rows, f"{corner}_cold_pressure")
        if None in {inner, middle, outer, running, cold}:
            continue
        shoulders = (float(inner) + float(outer)) / 2.0
        if float(middle) - shoulders >= 3.0 and float(running) > float(cold):
            repeated += 1
    return repeated


def _falloff_supported(laps: list[LapSummary]) -> bool:
    eligible = eligible_laps(laps)
    if len(eligible) < 10:
        return False
    times = [float(lap.lap_time) for lap in sorted(eligible, key=lambda item: item.lap_number)]
    return mean(times[-3:]) - mean(times[:3]) >= 0.15


def analyze_tire_state(
    rows: list[dict[str, Any]],
    lap_summaries: list[LapSummary] | None,
    *,
    selected_lap: int,
    sim_integrity_clear: bool | None,
    sim_integrity_confidence_cap: float = 1.0,
) -> TireStateReport:
    scoped, phases, evaluation, gate = qualify_phase_engine(
        TIRE_STATE_CONTRACT,
        rows,
        lap_summaries,
        selected_lap=selected_lap,
        target_phases=TIRE_PHASES,
        sim_integrity_clear=sim_integrity_clear,
        sim_integrity_confidence_cap=sim_integrity_confidence_cap,
        requested_outputs=frozenset({"tire_state_vector", "tire_energy_cause_hypothesis"}),
    )
    eligible_numbers = {lap.lap_number for lap in eligible_laps(lap_summaries or [])}
    if not evaluation.eligible:
        return TireStateReport(
            selected_lap=selected_lap,
            phases=sorted(phases & TIRE_PHASES),
            gate=gate,
            working_history_laps=len(eligible_numbers),
            conclusions=[EngineeringConclusion(
                key="tire_state_blocked",
                summary="Tire state is unavailable for a guarded engineering conclusion.",
                evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                confidence_score=0.0,
                blocker_reasons=gate.blocker_reasons,
            )],
        )

    states: list[TireCornerState] = []
    conclusions: list[EngineeringConclusion] = []
    falloff = _falloff_supported(lap_summaries or [])
    phase_set = phases & TIRE_PHASES
    for corner_upper in ("LF", "RF", "LR", "RR"):
        corner = corner_upper.lower()
        inner = average(scoped, f"{corner}_temp_inner")
        middle = average(scoped, f"{corner}_temp_middle")
        outer = average(scoped, f"{corner}_temp_outer")
        surface = _avg_optional([inner, middle, outer])
        carcass = _avg_optional([
            average(scoped, f"{corner}_carcass_temp_l"),
            average(scoped, f"{corner}_carcass_temp_m"),
            average(scoped, f"{corner}_carcass_temp_r"),
        ])
        running = average(scoped, f"{corner}_pressure")
        cold = average(scoped, f"{corner}_cold_pressure")
        pressure_gain = running - cold if running is not None and cold is not None else None
        middle_shoulders = (
            middle - ((inner + outer) / 2.0)
            if inner is not None and middle is not None and outer is not None else None
        )
        gradient = inner - outer if inner is not None and outer is not None else None
        slip_values = values(scoped, f"{corner}_slip_ratio")
        slip_rms = _rms(slip_values)
        causes: list[TireCause] = []
        repeated_pressure = _repeated_pressure_pattern(rows, eligible_numbers, corner)
        if middle_shoulders is not None and middle_shoulders >= 3.0 and pressure_gain is not None and pressure_gain > 0:
            causes.append("pressure_driven_heating")
        if gradient is not None and abs(gradient) >= 6.0:
            causes.extend(["shoulder_load", "camber_bias"])
        if surface is not None and carcass is not None and surface - carcass >= 8.0 and (slip_rms or 0.0) >= 0.04:
            causes.append("surface_scrub")
        if surface is not None and carcass is not None and carcass >= surface - 2.0:
            causes.append("carcass_heat")
        if corner_upper.startswith("F") and phase_set & {"brake_application", "threshold_braking", "brake_release"}:
            causes.append("braking_heat")
        if corner_upper.startswith("R") and phase_set & {"initial_throttle", "full_throttle_exit"} and (slip_rms or 0.0) >= 0.03:
            causes.append("traction_heat")
        distance = average(scoped, f"{corner}_tire_distance_m")
        wear_values = [
            average(scoped, f"{corner}_wear_inner"),
            average(scoped, f"{corner}_wear_middle"),
            average(scoped, f"{corner}_wear_outer"),
        ]
        if distance is not None and all(value is not None for value in wear_values):
            causes.append("aging")
        if falloff and surface is not None and carcass is not None:
            causes.extend(["saturation", "falloff"])
        state = TireCornerState(
            corner=corner_upper,  # type: ignore[arg-type]
            running_pressure=running,
            cold_pressure=cold,
            pressure_gain=pressure_gain,
            surface_inner=inner,
            surface_middle=middle,
            surface_outer=outer,
            surface_average=surface,
            carcass_average=carcass,
            middle_vs_shoulders=middle_shoulders,
            inner_outer_gradient=gradient,
            wear_inner=wear_values[0],
            wear_middle=wear_values[1],
            wear_outer=wear_values[2],
            tire_distance_m=distance,
            slip_ratio_rms=slip_rms,
            load_context_proxy=average(scoped, "vert_accel_g"),
            cause_classes=list(dict.fromkeys(causes)),
        )
        states.append(state)
        sources = [
            f"{corner}_pressure", f"{corner}_temp_inner", f"{corner}_temp_middle",
            f"{corner}_temp_outer", f"{corner}_wear_inner", f"{corner}_wear_middle",
            f"{corner}_wear_outer", f"{corner}_tire_distance_m", f"{corner}_slip_ratio",
            "brake_pct", "throttle_pct", "lap_dist_pct",
        ]
        support = [
            f"Surface profile I/M/O: {inner:.1f}/{middle:.1f}/{outer:.1f}."
            if None not in {inner, middle, outer} else "Complete surface-temperature profile unavailable.",
            f"Running-minus-cold pressure: {pressure_gain:.2f}." if pressure_gain is not None else "Cold-to-running pressure gain unavailable.",
            f"Thermal/usage classes: {', '.join(state.cause_classes) or 'none established'}.",
        ]
        contradictions = [
            "Center-tread temperature alone is not treated as a pressure command.",
        ]
        if carcass is None:
            contradictions.append("Carcass temperature is missing, so surface heat cannot establish thermal origin alone.")
        if repeated_pressure < 3:
            contradictions.append("Fewer than three eligible laps repeat the pressure/profile pattern.")
        recommendation = None
        if "pressure_driven_heating" in causes and repeated_pressure >= 3 and carcass is not None:
            recommendation = (
                "Test one small pressure reduction at this corner only; keep it only if pressure gain, "
                "surface/carcass profile, wear, and phase performance all improve on repeated laps."
            )
        conclusions.append(EngineeringConclusion(
            key=f"{corner}_tire_state",
            summary=(
                f"{corner_upper} tire state supports {', '.join(state.cause_classes)}."
                if state.cause_classes else f"{corner_upper} tire state has no supported causal class yet."
            ),
            evidence_state=EvidenceState.ESTIMATED_PROXY,
            confidence_score=min(0.8 if state.cause_classes else 0.45, gate.confidence_cap),
            source_channels=sources,
            supporting_evidence=support,
            contradicting_evidence=contradictions,
            recommendation=recommendation,
        ))
    actionable = [index for index, conclusion in enumerate(conclusions) if conclusion.recommendation]
    if len(actionable) > 1:
        primary = max(
            actionable,
            key=lambda index: abs(states[index].middle_vs_shoulders or 0.0),
        )
        conclusions = [
            conclusion if index == primary or not conclusion.recommendation else conclusion.model_copy(update={
                "recommendation": None,
                "contradicting_evidence": [
                    *conclusion.contradicting_evidence,
                    f"Held back because {states[primary].corner} is the single primary pressure test; change one setup control at a time.",
                ],
            })
            for index, conclusion in enumerate(conclusions)
        ]
    return TireStateReport(
        selected_lap=selected_lap,
        phases=sorted(phase_set),
        gate=gate,
        corners=states,
        conclusions=conclusions,
        working_history_laps=len(eligible_numbers),
    )


__all__ = ["TireCornerState", "TireStateReport", "analyze_tire_state"]
