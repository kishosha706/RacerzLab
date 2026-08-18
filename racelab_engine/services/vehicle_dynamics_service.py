"""P35 measured/proxy-only runtime vehicle-dynamics assessment.

This service consumes only producer-owned P20, P26, and P32 projections.  It
does not read telemetry, infer setup values, rank P19 causes, or emit runtime
causal graph edges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.engineering_projection import EngineeringAwarenessProjection
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.performance_intelligence import (
    CornerPerformanceChain,
    LapTimeOpportunity,
    PerformanceIntelligenceProjection,
    PerformancePhaseState,
)
from racelab_engine.models.vehicle_dynamics_knowledge import (
    DynamicResponseRegime,
    DynamicsChainStageKind,
    PerformanceMechanismAssessment,
    PerformanceMechanismCandidate,
    MechanismSeparationRow,
    PhaseResponseMetric,
    VehicleDynamicMechanism,
    VehicleDynamicsChainStage,
    VehicleDynamicsFocusArtifact,
    VehicleDynamicsKnowledgeGraph,
    VehicleDynamicsKnowledgeResolution,
    VehicleDynamicsPhase,
    VehicleDynamicsRuntimeMechanismTrust,
    VehicleProblemSignature,
    VehicleResponseObservation,
    build_phase_response_metric,
    build_performance_mechanism_assessment,
    build_vehicle_problem_signature,
    build_vehicle_response_observation,
)


_MANDATORY_UNAVAILABLE_QUANTITIES = (
    "quantity:exact_tire_force",
    "quantity:exact_wheel_load",
    "quantity:exact_spring_force",
    "quantity:exact_damper_force",
    "quantity:exact_arb_torque",
    "quantity:exact_aerodynamic_downforce",
    "quantity:exact_aerodynamic_balance",
    "quantity:exact_aerodynamic_drag_force",
    "quantity:exact_drag_coefficient",
    "quantity:exact_differential_torque",
    "quantity:exact_contact_patch_distribution",
    "quantity:exact_friction_coefficient",
)

_POSITIVE_EVIDENCE_STATES = {
    EvidenceState.MEASURED,
    EvidenceState.CALCULATED,
    EvidenceState.ESTIMATED_PROXY,
    EvidenceState.OBSERVED_CORRELATION,
    EvidenceState.CONTROLLED_TEST_EFFECT,
}

_DRIVER_INPUT_CHANNELS_BY_FIELD = {
    "throttle": {"Throttle", "throttle_pct", "throttle_01", "throttle"},
    "brake": {"Brake", "brake_pct", "brake_01"},
    "steering": {"SteeringWheelAngle", "steering_deg", "steering_rad"},
}
_DRIVER_INPUT_CHANNELS = frozenset(
    channel
    for channels in _DRIVER_INPUT_CHANNELS_BY_FIELD.values()
    for channel in channels
)
_NON_DIAGNOSTIC_PHYSICS_CHANNELS = frozenset(
    {
        "front_slip_angle_deg",
        "rear_slip_angle_deg",
        "slip_angle_balance_deg",
        "ackermann_steering_error_deg",
        "ackermann_scrub_proxy",
        "wheel_power_proxy_w",
        "cda_coastdown_proxy_m2",
        "full_throttle_resistance_cda_proxy_m2",
        "platform_roll_deg_from_rh",
        "front_load_proxy_n",
        "rear_load_proxy_n",
        "front_aero_proxy_n",
        "rear_aero_proxy_n",
        "aero_balance_front_pct",
        "rear_downforce_proxy_n",
        "rear_platform_proxy_n",
        "rear_diffuser_proxy_n",
        "aero_load_proxy_n",
        "drag_force_proxy_n",
        "dynamic_pressure_pa",
        "dynamic_pressure_psf",
        "dynamic_pressure_lap_index",
        "dynamic_pressure_index",
        "aero_load_index",
        "aero_load_index_180mph",
    }
)


@dataclass(frozen=True)
class _P20MechanismSupport:
    source_artifact_id: str
    source_channels: tuple[str, ...]
    lap_number: int
    lap_pct_start: float
    lap_pct_end: float
    phase: str
    evidence_state: EvidenceState


@dataclass(frozen=True)
class _ComparisonContextTruth:
    qualified: bool
    traffic_blocked: bool
    blockers: tuple[str, ...]


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _diagnostic_channels(values: Iterable[str]) -> tuple[str, ...]:
    return _unique(
        value for value in values if value not in _NON_DIAGNOSTIC_PHYSICS_CHANNELS
    )


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))


def _runtime_payload(p26: object) -> dict[str, object]:
    runtime = getattr(p26, "runtime_identity", None)
    if runtime is None:
        return {"state": "unavailable"}
    if hasattr(runtime, "model_dump"):
        return dict(runtime.model_dump(mode="json"))
    if isinstance(runtime, dict):
        return dict(runtime)
    return {"state": "unavailable"}


def _runtime_text(runtime: dict[str, object], key: str) -> str | None:
    value = runtime.get(key)
    return str(value) if value not in {None, ""} else None


def _track_package(track_configuration: str | None) -> str | None:
    # P26 currently owns a configuration name, not a reviewed package subtype.
    # Venue-name parsing would manufacture applicability.  The reviewed graph
    # explicitly covers the generic oval package, so only the producer-owned
    # exact generic ``oval`` configuration can enter it.  A road-course (or any
    # other) configuration must never be silently relabelled as an oval.
    if track_configuration is None or track_configuration.casefold() != "oval":
        return None
    return "oval"


def _compile_and_resolve_graph(
    *,
    car_path: str | None,
    car_version: str | None,
    iracing_build_version: str | None,
    track_package: str | None,
) -> tuple[VehicleDynamicsKnowledgeGraph, VehicleDynamicsKnowledgeResolution]:
    # Imported lazily so the runtime assessment remains isolated from the
    # static compiler implementation and its import-time graph construction.
    from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
        compile_next_gen_oval_knowledge_graph,
        resolve_next_gen_oval_knowledge_graph,
    )

    graph = compile_next_gen_oval_knowledge_graph()
    resolution = resolve_next_gen_oval_knowledge_graph(
        car_path=car_path,
        car_version=car_version,
        iracing_build_version=iracing_build_version,
        track_package=track_package,
    )
    if resolution.status == "ready" and (
        resolution.graph is None
        or resolution.graph.content_sha256 != graph.content_sha256
    ):
        raise ValueError("P35 resolution does not match the canonical reviewed graph")
    return graph, resolution


def _leading_opportunity(
    p32: PerformanceIntelligenceProjection,
) -> LapTimeOpportunity | None:
    measured = tuple(
        item
        for item in p32.opportunity_map.opportunities
        if item.local_delta_s is not None
    )
    losses = tuple(item for item in measured if (item.local_delta_s or 0.0) > 0.0)
    cohort = losses or measured
    return min(
        cohort,
        key=lambda item: (
            -(item.local_delta_s if losses else abs(item.local_delta_s or 0.0)),
            item.start_pct,
            item.opportunity_id,
        ),
        default=None,
    )


def _comparison_context_truth(
    p32: PerformanceIntelligenceProjection,
    opportunity: LapTimeOpportunity | None,
) -> _ComparisonContextTruth:
    if opportunity is None:
        return _ComparisonContextTruth(qualified=False, traffic_blocked=False, blockers=())
    fractions = (
        opportunity.source_traffic_exposure_fraction,
        opportunity.reference_traffic_exposure_fraction,
    )
    traffic_unknown = any(value is None for value in fractions)
    traffic_exposed = any(value is not None and value > 0.0 for value in fractions)
    basis_blockers = tuple(p32.basis.context_blockers)
    traffic_blocked = bool(
        opportunity.attribution_state == "blocked_by_traffic"
        or traffic_exposed
        or any("traffic" in item.casefold() for item in basis_blockers)
    )
    locally_qualified = bool(
        _enum_text(opportunity.context_state) in {"qualified", "qualified_pair"}
        and opportunity.attribution_state == "candidate_only"
    )
    blockers = _unique(
        (
            *basis_blockers,
            *(
                (
                    "Traffic exposure context is unavailable for one or both sides of "
                    "the selected P32 comparison.",
                )
                if traffic_unknown
                else ()
            ),
            *(
                ("Nonzero typed traffic exposure blocks P35 mechanism attribution.",)
                if traffic_exposed
                else ()
            ),
            *(
                (
                    "P32 attribution is blocked by the current typed comparison context "
                    f"({opportunity.attribution_state}).",
                )
                if not locally_qualified
                else ()
            ),
            *(opportunity.contradictions if not locally_qualified else ()),
        )
    )
    return _ComparisonContextTruth(
        qualified=locally_qualified and not blockers and not traffic_unknown,
        traffic_blocked=traffic_blocked,
        blockers=blockers,
    )


def _phase_kind(phase: str) -> VehicleDynamicsPhase | None:
    text = phase.casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "braking": VehicleDynamicsPhase.BRAKE,
        "brake_application": VehicleDynamicsPhase.BRAKE,
        "brake_release": VehicleDynamicsPhase.TRANSITION,
        "brake_release_transition": VehicleDynamicsPhase.TRANSITION,
        "bump_curb": VehicleDynamicsPhase.TRANSITION,
        "corner_entry": VehicleDynamicsPhase.ENTRY,
        "mid_corner": VehicleDynamicsPhase.CENTER,
        "apex": VehicleDynamicsPhase.CENTER,
        "throttle": VehicleDynamicsPhase.THROTTLE_PICKUP,
        "power": VehicleDynamicsPhase.THROTTLE_PICKUP,
        "full_throttle_exit": VehicleDynamicsPhase.EXIT,
        "carry": VehicleDynamicsPhase.FOLLOWING_STRAIGHT,
        "following_straight_carry": VehicleDynamicsPhase.FOLLOWING_STRAIGHT,
        "following_straight_time": VehicleDynamicsPhase.FOLLOWING_STRAIGHT,
    }
    if text in aliases:
        return aliases[text]
    for item in VehicleDynamicsPhase:
        if item.value == text:
            return item
    return None


def _response_regime(phase: VehicleDynamicsPhase) -> DynamicResponseRegime:
    if phase in {
        VehicleDynamicsPhase.LIFT,
        VehicleDynamicsPhase.BRAKE,
        VehicleDynamicsPhase.TURN_IN,
        VehicleDynamicsPhase.ENTRY,
        VehicleDynamicsPhase.THROTTLE_PICKUP,
        VehicleDynamicsPhase.TRANSITION,
    }:
        return DynamicResponseRegime.TRANSIENT
    if phase in {
        VehicleDynamicsPhase.STRAIGHT,
        VehicleDynamicsPhase.CENTER,
        VehicleDynamicsPhase.FOLLOWING_STRAIGHT,
    }:
        return DynamicResponseRegime.STEADY_STATE
    return DynamicResponseRegime.BOTH


def _chain_phase_states(
    chain: CornerPerformanceChain,
) -> tuple[PerformancePhaseState, ...]:
    return tuple(
        state
        for state in (
            chain.approach_state,
            chain.braking_state,
            chain.entry_state,
            chain.center_state,
            chain.exit_state,
            chain.carry_state,
        )
        if state is not None
    )


def _matching_chain(
    p32: PerformanceIntelligenceProjection,
    opportunity: LapTimeOpportunity | None,
) -> CornerPerformanceChain | None:
    if opportunity is None or len(opportunity.source_laps) < 2:
        return None
    source_lap_numbers = opportunity.source_laps[:1]
    reference_lap_numbers = opportunity.source_laps[1:]
    exact_region = tuple(
        item
        for item in p32.corner_chains
        if item.track_region == opportunity.track_region
        and item.turn == opportunity.turn
        and item.lap_numbers == source_lap_numbers
        and item.reference_lap_numbers == reference_lap_numbers
    )
    ranked = sorted(
        exact_region,
        key=lambda item: (
            not any(
                state.phase == opportunity.phase for state in _chain_phase_states(item)
            ),
            item.chain_id,
        ),
    )
    return ranked[0] if ranked else None


def _matching_phase_state(
    chain: CornerPerformanceChain | None,
    opportunity: LapTimeOpportunity | None,
) -> PerformancePhaseState | None:
    if chain is None:
        return None
    states = _chain_phase_states(chain)
    if opportunity is not None:
        exact = tuple(
            item
            for item in states
            if item.phase == opportunity.phase
            and item.start_pct == opportunity.start_pct
            and item.end_pct == opportunity.end_pct
        )
        if exact:
            return exact[0]
    return None


def _matched_driver_vehicle_separation(
    chain: CornerPerformanceChain | None,
    opportunity: LapTimeOpportunity | None,
) -> tuple[bool, str]:
    if chain is None or opportunity is None:
        return False, "The exact P32 driver-versus-vehicle separation is unavailable."
    states = tuple(
        item
        for item in chain.driver_vehicle_separation
        if item.phase == opportunity.phase
    )
    matched = tuple(
        item
        for item in states
        if _enum_text(item.result)
        == "vehicle_response_changed_with_matched_inputs"
        and item.driver_demand_changed is False
        and item.vehicle_response_changed is True
        and item.line_changed is False
        and item.context_changed is False
        and item.time_changed is True
        and not item.blockers
    )
    if matched:
        return True, ""
    if states:
        return (
            False,
            "P32 driver-versus-vehicle separation does not show vehicle response changing "
            "under matched driver demand in this exact phase.",
        )
    return False, "No P32 driver-versus-vehicle separation matches the exact current phase."


def _unavailable_stage(
    stage: DynamicsChainStageKind,
    reason: str,
    *,
    blocked: bool = False,
    source_artifact_ids: tuple[str, ...] = (),
    source_channels: tuple[str, ...] = (),
) -> VehicleDynamicsChainStage:
    return VehicleDynamicsChainStage(
        stage=stage,
        evidence_state=(
            EvidenceState.BLOCKED_BY_CONTEXT if blocked else EvidenceState.UNAVAILABLE
        ),
        source_artifact_ids=source_artifact_ids,
        source_channels=source_channels,
        summary=reason,
        blocker_reasons=(reason,),
    )


def _driver_input_stage(
    chain: CornerPerformanceChain | None,
    state: PerformancePhaseState | None,
) -> VehicleDynamicsChainStage:
    driver_values = (
        state.throttle_delta_pct if state is not None else None,
        state.brake_delta_pct if state is not None else None,
        state.steering_delta_deg if state is not None else None,
    )
    available_driver_channels: set[str] = set()
    if state is not None:
        if state.throttle_delta_pct is not None:
            available_driver_channels.update(_DRIVER_INPUT_CHANNELS_BY_FIELD["throttle"])
        if state.brake_delta_pct is not None:
            available_driver_channels.update(_DRIVER_INPUT_CHANNELS_BY_FIELD["brake"])
        if state.steering_delta_deg is not None:
            available_driver_channels.update(_DRIVER_INPUT_CHANNELS_BY_FIELD["steering"])
    source_channels = (
        tuple(
            channel
            for channel in state.source_channels
            if channel in available_driver_channels
        )
        if state is not None
        else ()
    )
    if (
        chain is None
        or state is None
        or not any(value is not None for value in driver_values)
        or not source_channels
        or not chain.lap_numbers
    ):
        return _unavailable_stage(
            DynamicsChainStageKind.DRIVER_INPUT,
            "Driver-input demand is unresolved in the typed P32 phase evidence.",
        )
    return VehicleDynamicsChainStage(
        stage=DynamicsChainStageKind.DRIVER_INPUT,
        evidence_state=EvidenceState.MEASURED,
        source_artifact_ids=(chain.chain_id,),
        source_channels=source_channels,
        summary=(
            "Measured brake, throttle, or steering demand is available for the current phase; "
            "it remains distinct from vehicle response."
        ),
    )


def _vehicle_demand_stage(
    p32: PerformanceIntelligenceProjection,
) -> VehicleDynamicsChainStage:
    demand = p32.track_demand
    available = any(
        value is not None
        for value in (
            demand.braking_fraction,
            demand.cornering_fraction,
            demand.combined_acceleration_fraction,
            demand.speed_min_mph,
            demand.speed_max_mph,
            demand.median_corner_duration_s,
        )
    )
    if not available or not demand.source_channels:
        return _unavailable_stage(
            DynamicsChainStageKind.VEHICLE_DEMAND,
            "Run-specific vehicle demand is unavailable from the typed P32 track profile.",
        )
    artifact_id = f"p32-track-demand:{canonical_json_sha256(demand)[:20]}"
    return VehicleDynamicsChainStage(
        stage=DynamicsChainStageKind.VEHICLE_DEMAND,
        evidence_state=EvidenceState.ESTIMATED_PROXY,
        source_artifact_ids=(artifact_id,),
        source_channels=demand.source_channels,
        summary=(
            "One or more available typed braking, cornering, combined-acceleration, speed, "
            "or duration proxies describe relative demand; exact tire and wheel loads "
            "remain unavailable."
        ),
    )


def _vehicle_response_stage(
    chain: CornerPerformanceChain | None,
    state: PerformancePhaseState | None,
) -> VehicleDynamicsChainStage:
    response_values = (
        state.yaw_rate_delta if state is not None else None,
        state.long_accel_delta if state is not None else None,
        state.speed_delta_mph if state is not None else None,
        state.line_separation_m if state is not None else None,
    )
    source_channels = (
        _diagnostic_channels(
            channel
            for channel in state.source_channels
            if channel not in _DRIVER_INPUT_CHANNELS
        )
        if state is not None
        else ()
    )
    if (
        chain is None
        or state is None
        or not any(value is not None for value in response_values)
        or not source_channels
        or not chain.lap_numbers
    ):
        return _unavailable_stage(
            DynamicsChainStageKind.VEHICLE_RESPONSE,
            "Yaw, acceleration, speed, and line response are unresolved in typed P32 evidence.",
        )
    return VehicleDynamicsChainStage(
        stage=DynamicsChainStageKind.VEHICLE_RESPONSE,
        evidence_state=EvidenceState.MEASURED,
        source_artifact_ids=(chain.chain_id,),
        source_channels=source_channels,
        summary=(
            "One or more measured yaw, acceleration, speed, or line-response signals are "
            "available independently of the driver-input layer."
        ),
    )


def _tire_platform_stage(
    p32: PerformanceIntelligenceProjection,
    *,
    traffic_blocked: bool,
    context_blockers: tuple[str, ...] = (),
) -> VehicleDynamicsChainStage:
    demand = p32.track_demand
    artifact_id = f"p32-track-demand:{canonical_json_sha256(demand)[:20]}"
    if traffic_blocked:
        return _unavailable_stage(
            DynamicsChainStageKind.TIRE_PLATFORM_STATE,
            "Traffic exposure blocks clean tire/platform and aero-proxy attribution.",
            blocked=True,
            source_artifact_ids=(artifact_id,),
            source_channels=demand.source_channels,
        )
    if context_blockers:
        return _unavailable_stage(
            DynamicsChainStageKind.TIRE_PLATFORM_STATE,
            context_blockers[0],
            blocked=True,
            source_artifact_ids=(artifact_id,),
            source_channels=demand.source_channels,
        )
    proxy_available = bool(
        demand.source_channels
        and (
            demand.combined_acceleration_fraction is not None
            or demand.platform_load_speed_bands_mph
            or demand.disturbance_exposure_fraction is not None
            or demand.tire_state_development == "observable"
        )
    )
    if not proxy_available:
        return _unavailable_stage(
            DynamicsChainStageKind.TIRE_PLATFORM_STATE,
            "Typed tire/platform proxies are unavailable; exact tire force and platform loads stay locked.",
        )
    return VehicleDynamicsChainStage(
        stage=DynamicsChainStageKind.TIRE_PLATFORM_STATE,
        evidence_state=EvidenceState.ESTIMATED_PROXY,
        source_artifact_ids=(artifact_id,),
        source_channels=demand.source_channels,
        summary=(
            "Relative combined-demand, tire-state, disturbance, or speed-band proxies are available; "
            "no exact grip, wheel-load, or aero value is claimed."
        ),
    )


def _time_stage(
    opportunity: LapTimeOpportunity | None,
) -> VehicleDynamicsChainStage:
    if (
        opportunity is None
        or opportunity.local_delta_s is None
        or not opportunity.source_channels
        or not opportunity.source_laps
    ):
        return _unavailable_stage(
            DynamicsChainStageKind.TIME_CONSEQUENCE,
            "No measured P32 elapsed-time consequence is available for a qualified physical scope.",
        )
    return VehicleDynamicsChainStage(
        stage=DynamicsChainStageKind.TIME_CONSEQUENCE,
        evidence_state=EvidenceState.MEASURED,
        source_artifact_ids=(opportunity.opportunity_id,),
        source_channels=opportunity.source_channels,
        summary=(
            f"P32 measured {opportunity.local_delta_s:+.6f} s in this physical window; "
            "P35 does not assign causation."
        ),
    )


def _focus_id(tool_id: str, *parts: object) -> str:
    suffix = tool_id.removeprefix("inspect_")
    return f"p35.focus.{suffix}:{canonical_json_sha256(parts)[:24]}"


def _candidate_mechanisms(
    graph: VehicleDynamicsKnowledgeGraph,
    *,
    p32_mechanism_ids: tuple[str, ...],
    phase: VehicleDynamicsPhase,
    regime: DynamicResponseRegime,
    time_origin: object,
) -> tuple[VehicleDynamicMechanism, ...]:
    requested = set(p32_mechanism_ids)
    values: list[VehicleDynamicMechanism] = []
    for mechanism in graph.mechanisms:
        if not requested.intersection(mechanism.p32_performance_mechanism_ids):
            continue
        if phase not in mechanism.relevant_phases:
            continue
        if time_origin not in mechanism.allowed_time_origin_kinds:
            continue
        if regime is not DynamicResponseRegime.BOTH and mechanism.response_regime not in {
            regime,
            DynamicResponseRegime.BOTH,
        }:
            continue
        values.append(mechanism)
    return tuple(values[:6])


def _focus_scope(
    opportunity: LapTimeOpportunity,
) -> dict[str, object]:
    return {
        "source_artifact_ids": (opportunity.opportunity_id,),
        "source_channels": opportunity.source_channels,
        "lap_numbers": opportunity.source_laps,
        "lap_pct_start": opportunity.start_pct,
        "lap_pct_end": opportunity.end_pct,
        "phase": opportunity.phase,
    }


def _exact_p20_mechanism_support(
    p20: EngineeringAwarenessProjection,
    mechanism: VehicleDynamicMechanism,
    opportunity: LapTimeOpportunity,
) -> tuple[_P20MechanismSupport | None, str]:
    """Resolve one exact current P20 observation without widening its scope."""

    mechanism_ids = set(mechanism.p20_mechanism_ids)
    primary = p20.primary_state
    if (
        primary is not None
        and primary.mechanism.value in mechanism_ids
        and len(primary.source_artifact_ids) == 1
        and primary.evidence_state in _POSITIVE_EVIDENCE_STATES
        and primary.phase == opportunity.phase
        and primary.lap_pct_start == opportunity.start_pct
        and primary.lap_pct_end == opportunity.end_pct
        and bool(opportunity.source_laps)
        and primary.lap_number == opportunity.source_laps[0]
    ):
        if _NON_DIAGNOSTIC_PHYSICS_CHANNELS.intersection(primary.source_channels):
            return (
                None,
                "A research/display-only force, slip-angle, aero, or nominal-geometry proxy cannot support a P35 mechanism.",
            )
        return (
            _P20MechanismSupport(
                source_artifact_id=primary.source_artifact_ids[0],
                source_channels=primary.source_channels,
                lap_number=primary.lap_number,
                lap_pct_start=primary.lap_pct_start,
                lap_pct_end=primary.lap_pct_end,
                phase=primary.phase,
                evidence_state=primary.evidence_state,
            ),
            "",
        )

    states = tuple(
        state
        for state in p20.subsystem_states
        if state.mechanism.value in mechanism_ids
    )
    for state in states:
        if (
            state.status == "ready"
            and len(state.source_artifact_ids) == 1
            and state.evidence_state in _POSITIVE_EVIDENCE_STATES
            and state.phase == opportunity.phase
            and state.lap_number is not None
            and bool(opportunity.source_laps)
            and state.lap_number == opportunity.source_laps[0]
            and state.lap_pct_start == opportunity.start_pct
            and state.lap_pct_end == opportunity.end_pct
            and state.source_channels
        ):
            if _NON_DIAGNOSTIC_PHYSICS_CHANNELS.intersection(
                state.source_channels
            ):
                return (
                    None,
                    "A research/display-only force, slip-angle, aero, or nominal-geometry proxy cannot support a P35 mechanism.",
                )
            assert state.lap_pct_start is not None
            assert state.lap_pct_end is not None
            return (
                _P20MechanismSupport(
                    source_artifact_id=state.source_artifact_ids[0],
                    source_channels=state.source_channels,
                    lap_number=state.lap_number,
                    lap_pct_start=state.lap_pct_start,
                    lap_pct_end=state.lap_pct_end,
                    phase=state.phase,
                    evidence_state=state.evidence_state,
                ),
                "",
            )

    blockers = _unique(
        reason
        for state in states
        if state.status in {"blocked", "unavailable"}
        for reason in state.blocker_reasons
    )
    if blockers:
        return None, blockers[0]
    if any(state.status == "no_finding" for state in states):
        return (
            None,
            "P20 has no current observation for this mechanism family in the exact physical scope.",
        )
    if any(state.status == "ready" for state in states):
        return (
            None,
            "P20 mechanism evidence does not match the exact current lap, phase, and physical window.",
        )
    return (
        None,
        "A typed P20 observation for this mechanism family is unavailable in the exact current scope.",
    )


def _p20_focus_scope(support: _P20MechanismSupport) -> dict[str, object]:
    return {
        "source_artifact_ids": (support.source_artifact_id,),
        "source_channels": support.source_channels,
        "lap_numbers": (support.lap_number,),
        "lap_pct_start": support.lap_pct_start,
        "lap_pct_end": support.lap_pct_end,
        "phase": support.phase,
    }


def _runtime_support_contract_blockers(
    trust: VehicleDynamicsRuntimeMechanismTrust,
    stages: tuple[VehicleDynamicsChainStage, ...],
    p20_source_channels: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate one candidate against the frozen layer/channel support contract."""

    from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
        unmet_runtime_support_channel_requirement_ids,
    )

    by_stage = {stage.stage: stage for stage in stages}
    missing_layers = tuple(
        layer.value
        for layer in trust.support_required_evidence_layers
        if layer not in by_stage
        or by_stage[layer].evidence_state not in _POSITIVE_EVIDENCE_STATES
    )
    channels_by_layer = {
        layer: (
            _unique((*stage.source_channels, *p20_source_channels))
            if layer is DynamicsChainStageKind.VEHICLE_RESPONSE
            else stage.source_channels
        )
        for layer, stage in by_stage.items()
    }
    missing_groups = unmet_runtime_support_channel_requirement_ids(
        trust,
        channels_by_layer,
    )
    blockers: list[str] = []
    if missing_layers:
        blockers.append(
            "P35 support is missing required typed evidence layers: "
            + ", ".join(missing_layers)
            + "."
        )
    if missing_groups:
        blockers.append(
            "P35 support is missing reviewed channel requirements: "
            + ", ".join(missing_groups)
            + "."
        )
    return tuple(blockers)


def _build_candidate_evidence(
    graph: VehicleDynamicsKnowledgeGraph,
    mechanisms: tuple[VehicleDynamicMechanism, ...],
    *,
    p20: EngineeringAwarenessProjection,
    opportunity: LapTimeOpportunity,
    stages: tuple[VehicleDynamicsChainStage, ...],
    matched_driver_vehicle_separation: bool,
    driver_vehicle_separation_blocker: str,
    traffic_blocked: bool,
    attribution_blockers: tuple[str, ...] = (),
) -> tuple[
    tuple[PerformanceMechanismCandidate, ...],
    tuple[VehicleDynamicsFocusArtifact, ...],
]:
    candidates: list[PerformanceMechanismCandidate] = []
    focus_artifacts: list[VehicleDynamicsFocusArtifact] = []
    source_scope = _focus_scope(opportunity)
    if not opportunity.source_channels or not opportunity.source_laps:
        return (), ()
    traffic_reason = (
        next(
            (
                item
                for item in opportunity.contradictions
                if "traffic" in item.casefold()
            ),
            "Traffic exposure blocks current mechanism attribution.",
        )
        if traffic_blocked
        else None
    )
    attribution_reason = traffic_reason or (
        attribution_blockers[0] if attribution_blockers else None
    )
    pending_candidates: list[PerformanceMechanismCandidate] = []
    from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
        compile_next_gen_oval_runtime_trust_manifest,
    )

    trust_by_mechanism = {
        item.mechanism_id: item
        for item in compile_next_gen_oval_runtime_trust_manifest().mechanisms
    }
    exact_driver_response_available = bool(
        stages[0].evidence_state in _POSITIVE_EVIDENCE_STATES
        and stages[2].evidence_state in _POSITIVE_EVIDENCE_STATES
    )
    for mechanism in mechanisms:
        tool_id = mechanism.inspection_tool_id.value
        contradiction_id = _focus_id(
            tool_id,
            opportunity.opportunity_id,
            mechanism.definition_id,
            "uncertainty",
        )
        discriminator_id = mechanism.discriminator_contract_ids[0]
        discriminator_contract = graph.observation_contract(discriminator_id)
        discriminator_tool = discriminator_contract.inspection_tool_id.value
        discriminator_focus_id = _focus_id(
            discriminator_tool,
            opportunity.opportunity_id,
            mechanism.definition_id,
            discriminator_id,
            "discriminator",
        )
        p20_support, p20_blocker = _exact_p20_mechanism_support(
            p20,
            mechanism,
            opportunity,
        )
        trust = trust_by_mechanism[mechanism.definition_id]
        support_contract_blockers = (
            _runtime_support_contract_blockers(
                trust,
                stages,
                p20_support.source_channels,
            )
            if p20_support is not None
            else ()
        )
        support_available = bool(
            attribution_reason is None
            and exact_driver_response_available
            and matched_driver_vehicle_separation
            and p20_support is not None
            and not support_contract_blockers
        )
        support_ids: tuple[str, ...] = ()
        if support_available:
            assert p20_support is not None
            support_id = _focus_id(
                tool_id,
                opportunity.opportunity_id,
                mechanism.definition_id,
                p20_support.source_artifact_id,
                "support",
            )
            support_ids = (support_id,)
            focus_artifacts.append(
                VehicleDynamicsFocusArtifact(
                    artifact_id=support_id,
                    mechanism_id=mechanism.definition_id,
                    inspection_tool_id=mechanism.inspection_tool_id,
                    stage=DynamicsChainStageKind.VEHICLE_RESPONSE,
                    evidence_state=p20_support.evidence_state,
                    polarity="support",
                    summary=(
                        "A typed P20 mechanism observation matches the exact P32 driver-input, "
                        "vehicle-response, and physical-window chain. It supports candidate "
                        "relevance only, never component cause."
                    ),
                    **_p20_focus_scope(p20_support),
                )
            )
        candidate_blocker = (
            attribution_reason
            or (
                "The exact P32 driver-input and vehicle-response chain is unavailable."
                if not exact_driver_response_available
                else driver_vehicle_separation_blocker
                if not matched_driver_vehicle_separation
                else support_contract_blockers[0]
                if support_contract_blockers
                else p20_blocker
            )
        )
        uncertainty = candidate_blocker or (
            "The current observation does not separate this candidate from the other compatible mechanisms."
        )
        focus_artifacts.append(
            VehicleDynamicsFocusArtifact(
                artifact_id=contradiction_id,
                mechanism_id=mechanism.definition_id,
                inspection_tool_id=mechanism.inspection_tool_id,
                stage=DynamicsChainStageKind.TIRE_PLATFORM_STATE,
                evidence_state=(
                    EvidenceState.BLOCKED_BY_CONTEXT
                    if attribution_reason is not None
                    else EvidenceState.NEEDS_CONFIRMATION
                ),
                polarity="uncertainty",
                summary=f"Strongest contradiction or uncertainty: {uncertainty}",
                blocker_reasons=(uncertainty,),
                **source_scope,
            )
        )
        focus_artifacts.append(
            VehicleDynamicsFocusArtifact(
                artifact_id=discriminator_focus_id,
                mechanism_id=mechanism.definition_id,
                observation_contract_id=discriminator_id,
                inspection_tool_id=discriminator_contract.inspection_tool_id,
                stage=DynamicsChainStageKind.TIRE_PLATFORM_STATE,
                evidence_state=(
                    EvidenceState.BLOCKED_BY_CONTEXT
                    if attribution_reason is not None
                    else EvidenceState.NEEDS_CONFIRMATION
                ),
                polarity="neutral",
                summary=(
                    "This typed observation contract is the next bounded discriminator; "
                    "it carries no setup or causal authority."
                ),
                blocker_reasons=(
                    attribution_reason
                    or "The discriminator has not yet been observed in the current exact context.",
                ),
                **source_scope,
            )
        )
        pending_candidates.append(
            PerformanceMechanismCandidate(
                mechanism_id=mechanism.definition_id,
                p32_performance_mechanism_ids=tuple(
                    item
                    for item in mechanism.p32_performance_mechanism_ids
                    if item in set(opportunity.mechanism_candidates)
                ),
                support_artifact_ids=support_ids,
                contradiction_artifact_ids=(contradiction_id,),
                discriminator_contract_ids=mechanism.discriminator_contract_ids,
                component_family_ids=mechanism.p26_component_family_ids,
                blocker_reasons=((candidate_blocker,) if candidate_blocker else ()),
                relevance=("candidate" if support_available else "blocked"),
            )
        )
    # Blocked families remain explicit with zero positive support so the user
    # can see what must be discriminated without mistaking measured time for a
    # mechanism observation.  The core contract permits this only when every
    # retained family has a typed blocker and uncertainty/discriminator.
    candidates.extend(pending_candidates)
    return tuple(candidates), tuple(focus_artifacts)


def _augment_vehicle_response_with_p20(
    stages: tuple[VehicleDynamicsChainStage, ...],
    focus_artifacts: tuple[VehicleDynamicsFocusArtifact, ...],
) -> tuple[VehicleDynamicsChainStage, ...]:
    support_focus = tuple(
        item
        for item in focus_artifacts
        if item.polarity == "support"
        and item.stage is DynamicsChainStageKind.VEHICLE_RESPONSE
    )
    if not support_focus:
        return stages
    response_index = tuple(DynamicsChainStageKind).index(
        DynamicsChainStageKind.VEHICLE_RESPONSE
    )
    response = stages[response_index]
    if response.evidence_state not in _POSITIVE_EVIDENCE_STATES:
        raise ValueError("P20 support cannot replace a missing exact P32 response chain")
    updated = response.model_copy(
        update={
            "source_artifact_ids": _unique(
                (
                    *response.source_artifact_ids,
                    *(
                        artifact_id
                        for item in support_focus
                        for artifact_id in item.source_artifact_ids
                    ),
                )
            ),
            "source_channels": _unique(
                (
                    *response.source_channels,
                    *(
                        channel
                        for item in support_focus
                        for channel in item.source_channels
                    ),
                )
            ),
            "summary": (
                f"{response.summary} Matching P20 observations are retained as a distinct "
                "observation layer."
            ),
        }
    )
    values = list(stages)
    values[response_index] = VehicleDynamicsChainStage.model_validate(updated)
    return tuple(values)


def _runtime_unavailable_quantities(
    graph: VehicleDynamicsKnowledgeGraph,
    p32: PerformanceIntelligenceProjection,
) -> tuple[str, ...]:
    values = [
        *graph.unavailable_quantity_ids,
        *graph.oval_track_demand_model.unavailable_quantity_ids,
    ]
    # P32 exposes empirical speed and corner-duration demand, but not producer-
    # owned banking/radius/curvature/line geometry.
    _ = p32.track_demand.speed_min_mph, p32.track_demand.median_corner_duration_s
    return _unique((*_MANDATORY_UNAVAILABLE_QUANTITIES, *values))


_PHASE_METRIC_SPECS = (
    (
        "elapsed_time_delta_s",
        "s",
        "calculated_delta",
        ("session_time", "SessionTime", "lap_dist_pct_100", "lap_dist_pct"),
    ),
    (
        "speed_delta_mph",
        "mph",
        "measured_delta",
        ("speed_mph", "Speed", "speed_mps"),
    ),
    (
        "throttle_demand_delta_pct",
        "%",
        "measured_delta",
        ("Throttle", "throttle_pct", "throttle_01", "throttle"),
    ),
    (
        "brake_demand_delta_pct",
        "%",
        "measured_delta",
        ("Brake", "brake_pct", "brake_01"),
    ),
    (
        "steering_wheel_demand_delta_deg",
        "deg",
        "measured_delta",
        ("SteeringWheelAngle", "steering_deg", "steering_rad"),
    ),
    (
        "yaw_rate_response_delta_rad_s",
        "rad/s",
        "measured_delta",
        ("YawRate", "yaw_rate"),
    ),
    (
        "longitudinal_accel_response_delta_mps2",
        "m/s^2",
        "measured_delta",
        ("LongAccel", "long_accel", "long_accel_mps2"),
    ),
    (
        "path_delta_m",
        "m",
        "calculated_delta",
        ("lat", "lon", "Lat", "Lon", "lap_dist_pct_100"),
    ),
    (
        "line_separation_m",
        "m",
        "calculated_delta",
        ("lat", "lon", "Lat", "Lon", "lap_dist_pct_100"),
    ),
)


def _phase_response_metrics(
    opportunity: LapTimeOpportunity,
    state: PerformancePhaseState | None,
) -> tuple[PhaseResponseMetric, ...]:
    values: dict[str, float | None] = {
        "elapsed_time_delta_s": opportunity.local_delta_s,
        "speed_delta_mph": state.speed_delta_mph if state is not None else None,
        "throttle_demand_delta_pct": (
            state.throttle_delta_pct if state is not None else None
        ),
        "brake_demand_delta_pct": state.brake_delta_pct if state is not None else None,
        "steering_wheel_demand_delta_deg": (
            state.steering_delta_deg if state is not None else None
        ),
        "yaw_rate_response_delta_rad_s": (
            state.yaw_rate_delta if state is not None else None
        ),
        "longitudinal_accel_response_delta_mps2": (
            state.long_accel_delta if state is not None else None
        ),
        "path_delta_m": state.path_delta_m if state is not None else None,
        "line_separation_m": state.line_separation_m if state is not None else None,
    }
    available_channels = _unique(
        (
            *opportunity.source_channels,
            *(state.source_channels if state is not None else ()),
        )
    )
    metrics: list[PhaseResponseMetric] = []
    for quantity, units, semantics, accepted_channels in _PHASE_METRIC_SPECS:
        value = values[quantity]
        if value is None:
            continue
        channels = tuple(
            channel for channel in available_channels if channel in accepted_channels
        )
        if not channels:
            # P32 owns the numeric delta, but missing per-quantity provenance must
            # stay unavailable to this narrower response layer.
            continue
        metrics.append(
            build_phase_response_metric(
                {
                    "quantity": quantity,
                    "value": value,
                    "units": units,
                    "semantics": semantics,
                    "source_channels": channels,
                }
            )
        )
    return tuple(metrics)


def _response_and_signature(
    *,
    run_id: str,
    opportunity: LapTimeOpportunity | None,
    chain: CornerPerformanceChain | None,
    phase_state: PerformancePhaseState | None,
    regime: DynamicResponseRegime | None,
    context_truth: _ComparisonContextTruth,
) -> tuple[tuple[VehicleResponseObservation, ...], VehicleProblemSignature | None]:
    if opportunity is None or opportunity.local_delta_s is None or regime is None:
        return (), None
    metrics = _phase_response_metrics(opportunity, phase_state)
    if not metrics or not any(
        metric.quantity == "elapsed_time_delta_s" for metric in metrics
    ):
        return (), None
    separations = tuple(
        item
        for item in (chain.driver_vehicle_separation if chain is not None else ())
        if item.phase == opportunity.phase
    )
    separation = separations[0] if separations else None
    result = _enum_text(separation.result) if separation is not None else "unresolved"
    driver_state = {
        "vehicle_response_changed_with_matched_inputs": "matched",
        "driver_execution_changed": "changed",
        "mixed_change": "mixed",
    }.get(result, "unavailable")
    vehicle_state = (
        "changed"
        if separation is not None and separation.vehicle_response_changed is True
        else "not_established"
        if separation is not None and separation.vehicle_response_changed is False
        else "unavailable"
    )
    line_state = (
        "changed"
        if separation is not None and separation.line_changed is True
        else "matched"
        if separation is not None and separation.line_changed is False
        else "unavailable"
    )
    persistence = {
        "carried_in": "carried_forward",
        "amplified": "carried_forward",
        "surrendered": "carried_forward",
        "recovered": "recovered",
        "local_generation": "phase_local",
    }.get(_enum_text(opportunity.origin_kind), "unavailable")
    context_state = (
        "qualified"
        if context_truth.qualified
        else "blocked"
        if context_truth.blockers
        else "unavailable"
    )
    blockers = context_truth.blockers if context_state != "qualified" else ()
    source_laps = chain.lap_numbers if chain is not None else opportunity.source_laps[:1]
    reference_laps = (
        chain.reference_lap_numbers
        if chain is not None
        else opportunity.source_laps[1:]
    )
    if not source_laps or not reference_laps:
        return (), None
    source_channels = _unique(
        channel for metric in metrics for channel in metric.source_channels
    )
    source_artifacts = _unique(
        (
            opportunity.opportunity_id,
            *((chain.chain_id,) if chain is not None and phase_state is not None else ()),
        )
    )
    observation = build_vehicle_response_observation(
        {
            "opportunity_id": opportunity.opportunity_id,
            "run_id": run_id,
            "source_lap_numbers": source_laps,
            "reference_lap_numbers": reference_laps,
            "phase": opportunity.phase,
            "lap_pct_start": opportunity.start_pct,
            "lap_pct_end": opportunity.end_pct,
            "onset_pct": opportunity.start_pct,
            "response_regime": regime,
            "driver_demand_state": driver_state,
            "vehicle_response_state": vehicle_state,
            "line_state": line_state,
            "context_state": context_state,
            "persistence": persistence,
            "metrics": metrics,
            "source_artifact_ids": source_artifacts,
            "source_channels": source_channels,
            "blocker_reasons": blockers,
            "evidence_state": (
                EvidenceState.MEASURED
                if context_state == "qualified"
                else EvidenceState.BLOCKED_BY_CONTEXT
                if context_state == "blocked"
                else EvidenceState.NEEDS_CONFIRMATION
            ),
        }
    )
    strongest_contradiction = next(
        iter(
            _unique(
                (
                    *context_truth.blockers,
                    *(separation.contradictions if separation is not None else ()),
                    *(separation.blockers if separation is not None else ()),
                    *opportunity.contradictions,
                    "No mechanism has yet survived a controlled discriminator.",
                )
            )
        )
    )
    signature = build_vehicle_problem_signature(
        {
            "response_observation_id": observation.observation_id,
            "opportunity_id": opportunity.opportunity_id,
            "time_origin": opportunity.origin_kind,
            "local_time_delta_s": opportunity.local_delta_s,
            "phase": opportunity.phase,
            "onset_pct": opportunity.start_pct,
            "response_regime": regime,
            "driver_demand_state": driver_state,
            "vehicle_response_state": vehicle_state,
            "line_state": line_state,
            "traffic_dependence": (
                "blocked"
                if context_truth.traffic_blocked
                else "clear"
                if context_truth.qualified
                else "unavailable"
            ),
            "strongest_contradiction": strongest_contradiction,
        }
    )
    return (observation,), signature


def _mechanism_separation_rows(
    mechanisms: tuple[VehicleDynamicMechanism, ...],
    candidates: tuple[PerformanceMechanismCandidate, ...],
    response_observations: tuple[VehicleResponseObservation, ...],
) -> tuple[MechanismSeparationRow, ...]:
    if not response_observations:
        return ()
    by_id = {item.definition_id: item for item in mechanisms}
    response_id = response_observations[0].observation_id
    rows: list[MechanismSeparationRow] = []
    for candidate in candidates:
        mechanism = by_id[candidate.mechanism_id]
        missing = candidate.blocker_reasons or (
            "The leading mechanism remains unresolved from competing candidates.",
        )
        rows.append(
            MechanismSeparationRow(
                mechanism_id=candidate.mechanism_id,
                response_observation_id=response_id,
                required_response_kpi_ids=mechanism.support_contract_ids,
                support_artifact_ids=candidate.support_artifact_ids,
                contradiction_artifact_ids=candidate.contradiction_artifact_ids,
                missing_evidence=missing,
                discriminator_contract_ids=candidate.discriminator_contract_ids,
                protected_countereffects=mechanism.expected_countereffects,
                component_family_ids=candidate.component_family_ids,
                state=("alive" if candidate.relevance == "candidate" else "blocked"),
            )
        )
    return tuple(rows)


def build_vehicle_dynamics_assessment(
    *,
    run_id: str,
    session_id: str,
    objective_id: str,
    p19_reasoning_snapshot_sha256: str,
    p20: EngineeringAwarenessProjection,
    p26: object,
    p32: PerformanceIntelligenceProjection,
) -> PerformanceMechanismAssessment:
    """Build one current P35 assessment without reading raw telemetry.

    The caller supplies only already-built typed producer projections.  Static
    graph resolution is server-owned and build-applicable.
    """

    p26_graph_version = str(getattr(p26, "graph_version"))
    p26_graph_sha256 = str(getattr(p26, "knowledge_graph_sha256"))
    if (
        p32.run_id != run_id
        or p32.session_id != session_id
        or p32.objective_id != objective_id
        or p32.p19_reasoning_snapshot_sha256
        != p19_reasoning_snapshot_sha256
        or p32.p20_state_revision != p20.state_revision
        or p32.p26_knowledge_graph_sha256 != p26_graph_sha256
        or p20.run_id != run_id
        or p20.session_id != session_id
        or p20.request_identity.session_id != session_id
        or p20.reasoning_snapshot_id != p19_reasoning_snapshot_sha256
        or p20.request_identity.reasoning_snapshot_id
        != p19_reasoning_snapshot_sha256
        or getattr(p26, "reasoning_snapshot_sha256", None)
        != p19_reasoning_snapshot_sha256
    ):
        raise ValueError("P35 requires one exact atomic P19/P20/P26/P32 scope")

    runtime = _runtime_payload(p26)
    car_path = _runtime_text(runtime, "car_path")
    car_version = _runtime_text(runtime, "car_version")
    iracing_build = _runtime_text(runtime, "iracing_build_version")
    track_configuration = _runtime_text(runtime, "track_configuration_name")
    track_package = _track_package(track_configuration)
    graph, resolution = _compile_and_resolve_graph(
        car_path=car_path,
        car_version=car_version,
        iracing_build_version=iracing_build,
        track_package=track_package,
    )

    opportunity = _leading_opportunity(p32)
    phase = _phase_kind(opportunity.phase if opportunity is not None else "transition")
    regime = (
        _response_regime(phase)
        if opportunity is not None and phase is not None
        else None
    )
    chain = _matching_chain(p32, opportunity)
    phase_state = _matching_phase_state(chain, opportunity)
    (
        separation_matched,
        separation_blocker,
    ) = _matched_driver_vehicle_separation(chain, opportunity)
    context_truth = _comparison_context_truth(p32, opportunity)
    traffic_blocked = context_truth.traffic_blocked
    attribution_blockers = context_truth.blockers
    stages = (
        _driver_input_stage(chain, phase_state),
        _vehicle_demand_stage(p32),
        _vehicle_response_stage(chain, phase_state),
        _tire_platform_stage(
            p32,
            traffic_blocked=traffic_blocked,
            context_blockers=attribution_blockers,
        ),
        _time_stage(opportunity),
    )

    measured_opportunity = (
        opportunity
        if stages[-1].evidence_state == EvidenceState.MEASURED
        else None
    )
    response_observations, problem_signature = _response_and_signature(
        run_id=run_id,
        opportunity=measured_opportunity,
        chain=chain,
        phase_state=phase_state,
        regime=regime,
        context_truth=context_truth,
    )

    p32_mechanism_ids = _unique(
        measured_opportunity.mechanism_candidates
        if measured_opportunity is not None
        else ()
    )
    mechanisms: tuple[VehicleDynamicMechanism, ...] = ()
    candidates: tuple[PerformanceMechanismCandidate, ...] = ()
    focus_artifacts: tuple[VehicleDynamicsFocusArtifact, ...] = ()
    if (
        resolution.status == "ready"
        and measured_opportunity is not None
        and regime is not None
        and response_observations
        and measured_opportunity.local_delta_s != 0.0
    ):
        mechanisms = _candidate_mechanisms(
            graph,
            p32_mechanism_ids=p32_mechanism_ids,
            phase=phase,
            regime=regime,
            time_origin=measured_opportunity.origin_kind,
        )
        candidates, focus_artifacts = _build_candidate_evidence(
            graph,
            mechanisms,
            p20=p20,
            opportunity=measured_opportunity,
            stages=stages,
            matched_driver_vehicle_separation=separation_matched,
            driver_vehicle_separation_blocker=separation_blocker,
            traffic_blocked=traffic_blocked,
            attribution_blockers=attribution_blockers,
        )
        stages = _augment_vehicle_response_with_p20(stages, focus_artifacts)
    mechanism_separation = _mechanism_separation_rows(
        mechanisms,
        candidates,
        response_observations,
    )

    # Graph states remain reviewed possibilities until one typed observer
    # directly supports their exact identity.  Do not project every
    # phase-compatible static state as current runtime truth.
    tire_demand_state_ids: tuple[str, ...] = ()
    load_path_ids: tuple[str, ...] = ()
    application_blockers = resolution.blocker_reasons
    blockers = _unique(
        (
            *p32.blockers,
            *application_blockers,
            *(
                (
                    "Traffic exposure blocks mechanism and platform/aero-proxy attribution; "
                    "the P32 elapsed-time observation remains visible."
                ,)
                if traffic_blocked
                else ()
            ),
            *(
                ("No current P32 mechanism vocabulary matched the reviewed P35 graph.",)
                if resolution.status == "ready" and not mechanisms
                else ()
            ),
            *(
                (
                    "A phase-response comparison requires distinct source and reference lap identities; mechanism candidates remain withheld.",
                )
                if measured_opportunity is not None
                and regime is not None
                and not response_observations
                else ()
            ),
            *(
                (
                    "No P35 mechanism candidate has both an exact typed P20 observation "
                    "and an exact P32 driver-input/vehicle-response chain in this scope.",
                )
                if resolution.status == "ready" and mechanisms and not candidates
                else ()
            ),
            *(
                (
                    f"P32 phase '{opportunity.phase}' is outside the reviewed P35 phase vocabulary.",
                )
                if opportunity is not None and phase is None
                else ()
            ),
            *(
                (
                    "The selected P32 opportunity has zero elapsed-time difference; "
                    "P35 withholds mechanism candidates because no time consequence changed.",
                )
                if opportunity is not None and opportunity.local_delta_s == 0.0
                else ()
            ),
            (
                "Banking, radius, curvature, line, transition severity, and straight length "
                "are unavailable because no current typed producer publishes them."
            ),
            (
                "Typed oval package subtype is unavailable; P35 uses only the reviewed generic oval applicability."
            ),
        )
    )
    leading_candidate = next(
        (item for item in candidates if item.relevance == "candidate"),
        candidates[0] if candidates else None,
    )
    strongest_support = (
        leading_candidate.support_artifact_ids[0]
        if leading_candidate is not None and leading_candidate.support_artifact_ids
        else None
    )
    strongest_contradiction = (
        leading_candidate.contradiction_artifact_ids[0]
        if leading_candidate is not None
        else None
    )
    next_discriminator = (
        leading_candidate.discriminator_contract_ids[0]
        if leading_candidate is not None
        else None
    )
    return build_performance_mechanism_assessment(
        {
            "run_id": run_id,
            "session_id": session_id,
            "objective_id": objective_id,
            "car_path": car_path or "unavailable",
            "car_version": car_version or "unavailable",
            "iracing_build_version": iracing_build or "unavailable",
            "track_package": track_package or "unavailable",
            "vehicle_runtime_identity_sha256": canonical_json_sha256(runtime),
            "graph_id": graph.graph_id,
            "graph_version": graph.graph_version,
            "knowledge_version": graph.knowledge_version,
            "knowledge_graph_sha256": graph.content_sha256,
            "p19_reasoning_snapshot_sha256": p19_reasoning_snapshot_sha256,
            "p20_state_revision": p20.state_revision,
            "p20_profile_hash": p20.profile_hash,
            "p26_graph_version": p26_graph_version,
            "p26_knowledge_graph_sha256": p26_graph_sha256,
            "p32_projection_sha256": p32.projection_sha256,
            "p32_performance_mechanism_ids": p32_mechanism_ids,
            "performance_opportunity_ids": (
                (measured_opportunity.opportunity_id,)
                if measured_opportunity is not None
                else ()
            ),
            "measured_time_consequence_available": (
                stages[-1].evidence_state == EvidenceState.MEASURED
            ),
            "chain": stages,
            "tire_demand_state_ids": tire_demand_state_ids,
            "load_path_ids": load_path_ids,
            "response_regime": regime,
            "response_observations": response_observations,
            "problem_signature": problem_signature,
            "mechanism_separation": mechanism_separation,
            "candidates": candidates,
            "focus_artifacts": focus_artifacts,
            "strongest_support_artifact_id": strongest_support,
            "strongest_contradiction_artifact_id": strongest_contradiction,
            "next_discriminator_contract_id": next_discriminator,
            "unavailable_quantity_ids": _runtime_unavailable_quantities(graph, p32),
            "traffic_blocked": traffic_blocked,
            "applicability_state": resolution.status,
            "applicability_blockers": application_blockers,
            "blocker_reasons": blockers,
        }
    )


def build_unavailable_vehicle_dynamics_assessment(
    *,
    run_id: str,
    session_id: str,
    objective_id: str,
    p19_reasoning_snapshot_sha256: str,
    p20: EngineeringAwarenessProjection,
    p26: object,
    p32: PerformanceIntelligenceProjection,
    blocker_reason: str,
) -> PerformanceMechanismAssessment:
    """Fail contained while retaining any already-measured P32 consequence."""

    runtime = _runtime_payload(p26)
    car_path = _runtime_text(runtime, "car_path")
    car_version = _runtime_text(runtime, "car_version")
    iracing_build = _runtime_text(runtime, "iracing_build_version")
    track_package = _track_package(_runtime_text(runtime, "track_configuration_name"))
    graph, resolution = _compile_and_resolve_graph(
        car_path=car_path,
        car_version=car_version,
        iracing_build_version=iracing_build,
        track_package=track_package,
    )
    opportunity = _leading_opportunity(p32)
    phase = _phase_kind(opportunity.phase if opportunity is not None else "")
    context_truth = _comparison_context_truth(p32, opportunity)
    traffic_blocked = context_truth.traffic_blocked
    chain = _matching_chain(p32, opportunity)
    phase_state = _matching_phase_state(chain, opportunity)
    stages = (
        _driver_input_stage(chain, phase_state),
        _vehicle_demand_stage(p32),
        _vehicle_response_stage(chain, phase_state),
        _tire_platform_stage(
            p32,
            traffic_blocked=traffic_blocked,
            context_blockers=context_truth.blockers,
        ),
        _time_stage(opportunity),
    )
    measured_opportunity = (
        opportunity
        if stages[-1].evidence_state == EvidenceState.MEASURED
        else None
    )
    regime = (
        _response_regime(phase)
        if opportunity is not None and phase is not None
        else None
    )
    response_observations, problem_signature = _response_and_signature(
        run_id=run_id,
        opportunity=measured_opportunity,
        chain=chain,
        phase_state=phase_state,
        regime=regime,
        context_truth=context_truth,
    )
    return build_performance_mechanism_assessment(
        {
            "run_id": run_id,
            "session_id": session_id,
            "objective_id": objective_id,
            "car_path": car_path or "unavailable",
            "car_version": car_version or "unavailable",
            "iracing_build_version": iracing_build or "unavailable",
            "track_package": track_package or "unavailable",
            "vehicle_runtime_identity_sha256": canonical_json_sha256(runtime),
            "graph_id": graph.graph_id,
            "graph_version": graph.graph_version,
            "knowledge_version": graph.knowledge_version,
            "knowledge_graph_sha256": graph.content_sha256,
            "p19_reasoning_snapshot_sha256": p19_reasoning_snapshot_sha256,
            "p20_state_revision": p20.state_revision,
            "p20_profile_hash": p20.profile_hash,
            "p26_graph_version": str(getattr(p26, "graph_version")),
            "p26_knowledge_graph_sha256": str(
                getattr(p26, "knowledge_graph_sha256")
            ),
            "p32_projection_sha256": p32.projection_sha256,
            "p32_performance_mechanism_ids": _unique(
                measured_opportunity.mechanism_candidates
                if measured_opportunity is not None
                else ()
            ),
            "performance_opportunity_ids": (
                (measured_opportunity.opportunity_id,)
                if measured_opportunity is not None
                else ()
            ),
            "measured_time_consequence_available": (
                stages[-1].evidence_state == EvidenceState.MEASURED
            ),
            "chain": stages,
            "tire_demand_state_ids": (),
            "load_path_ids": (),
            "response_regime": regime,
            "response_observations": response_observations,
            "problem_signature": problem_signature,
            "mechanism_separation": (),
            "candidates": (),
            "focus_artifacts": (),
            "strongest_support_artifact_id": None,
            "strongest_contradiction_artifact_id": None,
            "next_discriminator_contract_id": None,
            "unavailable_quantity_ids": _runtime_unavailable_quantities(graph, p32),
            "traffic_blocked": traffic_blocked,
            "applicability_state": resolution.status,
            "applicability_blockers": resolution.blocker_reasons,
            "blocker_reasons": _unique(
                (
                    *p32.blockers,
                    *context_truth.blockers,
                    *resolution.blocker_reasons,
                    blocker_reason,
                )
            ),
        }
    )


__all__ = [
    "build_unavailable_vehicle_dynamics_assessment",
    "build_vehicle_dynamics_assessment",
]
