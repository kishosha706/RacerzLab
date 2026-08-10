"""Deterministic, evidence-grounded intelligence for RaceLab Garage.

The service composes existing canonical evidence and controlled-test contracts.
It does not call a generative model, infer a legal setup value, or treat an
ordinal ranking as a probability.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from racelab_engine.analysis.lap_eligibility import lap_ineligibility_reasons, lap_is_eligible
from racelab_engine.analysis.calculated_channels import (
    CALCULATED_CHANNEL_UNITS,
    CORE_REQUIRED_CHANNELS,
    HIGH_VALUE_RAW_CHANNELS,
)
from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    assess_setup_change,
    expected_control_effect,
    format_setup_value,
    setup_control_values_equal,
    setup_target_increment_blocker,
)
from racelab_engine.analysis.test_director import (
    MeasurementMission,
    TestDirectorDecision,
    score_test_execution,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.engineering_awareness import MechanismEpisode
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import (
    CalibrationSummary,
    CapabilityAssessment,
    CauseDiscriminator,
    CauseHypothesis,
    ControlResponseOutcome,
    ControlledOutcomeAssessment,
    DataQualityAssessment,
    EvidenceCitation,
    EvidenceEdge,
    EvidenceEdgeKind,
    EvidenceGraph,
    EvidenceIndependenceCluster,
    EvidenceNode,
    EvidenceNodeKind,
    GroundedClaim,
    GroundedQueryResult,
    GuardedCounterfactualRange,
    InformationPlan,
    IntelligenceAction,
    IntelligenceBriefing,
    InternalIntelligenceReport,
    MechanismClaimOutcome,
    MindChangeCriterion,
    NavigationTarget,
    PublicCompetingCause,
    PolicyAcceptabilityOutcome,
    RankedCause,
    ReasoningAuthorityEnvelope,
    ReasoningSnapshot,
    ResponseMemorySummary,
    SetupEvidenceValue,
)
from racelab_engine.models.smart_guidance import (
    MeasurementBlocker,
    MeasurementCandidate,
    MeasurementCandidateEvaluation,
    MeasurementPriority,
    MeasurementSelectionAudit,
    measurement_priority_rank,
)
from racelab_engine.models.observation_intelligence import (
    MechanismObservation,
    ObservationCitation,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.lap_engineering_context import LapEngineeringContextReport
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.services.setup_learning_service import (
    SetupResponseContext,
    get_setup_response_graph,
)


_QUALIFIED_STATES = frozenset(
    {
        EvidenceState.MEASURED,
        EvidenceState.CALCULATED,
        EvidenceState.ESTIMATED_PROXY,
        EvidenceState.OBSERVED_CORRELATION,
        EvidenceState.CONTROLLED_TEST_EFFECT,
    }
)

_MIN_REPEATED_CAUSE_EVIDENCE_UNITS = 2
_TYPED_PHASE_TERMS = {
    "braking": ("brake", "braking", "brake zone"),
    "entry": ("entry", "corner entry", "turn in"),
    "center": ("center", "centre", "mid corner", "apex"),
    "exit": ("exit", "corner exit", "power down"),
    "straight": ("straight", "full throttle", "straightaway"),
}


def _typed_phase(*values: str | None) -> str | None:
    normalized = " ".join(
        re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
        for value in values
        if isinstance(value, str) and value.strip()
    )
    matches = tuple(
        phase
        for phase, terms in _TYPED_PHASE_TERMS.items()
        if any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in terms)
    )
    return matches[0] if len(matches) == 1 else None
_PUBLIC_EVIDENCE_CHANNELS = frozenset(
    (*CALCULATED_CHANNEL_UNITS, *CORE_REQUIRED_CHANNELS, *HIGH_VALUE_RAW_CHANNELS)
)


def _unique_text(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _setup_authorization_fingerprint(
    *,
    control_key: str,
    current_value: Any,
    proposed_value: Any,
    proposed_value_provenance: Sequence[str],
    source_event_ids: Sequence[str],
) -> str | None:
    if (
        control_key not in SETUP_CONTROL_SPECS
        or current_value is None
        or proposed_value is None
        or isinstance(current_value, bool)
        or isinstance(proposed_value, bool)
        or not proposed_value_provenance
        or not source_event_ids
    ):
        return None
    identities = (*proposed_value_provenance, *source_event_ids)
    if any(
        not isinstance(identity, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", identity) is None
        for identity in identities
    ):
        return None
    try:
        current_display = format_setup_value(control_key, current_value)
        proposed_display = format_setup_value(control_key, proposed_value)
    except (TypeError, ValueError, OverflowError):
        return None
    payload = "\x1f".join(
        (
            control_key,
            current_display,
            proposed_display,
            *sorted(set(proposed_value_provenance)),
            "events",
            *sorted(set(source_event_ids)),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _setup_value_matches_controlled_workflow(
    value: SetupEvidenceValue,
    workflow: ControlledWorkflow,
) -> bool:
    card = workflow.packet.primary_test
    execution = workflow.execution
    if (
        card is None
        or execution is None
        or not _controlled_card_is_semantically_complete(card)
        or value.setup_key != card.control_key
        or set(value.source_event_ids) != set(card.evidence_event_ids)
        or set(value.proposed_value_provenance)
        != set(card.proposed_value_provenance)
        or set(value.proposed_value_provenance)
        != {workflow.stage_run_ids.get("B")}
    ):
        return False
    try:
        return bool(
            setup_control_values_equal(
                card.control_key, value.current_value_raw, card.current_value
            )
            and setup_control_values_equal(
                card.control_key, value.proposed_value_raw, card.proposed_value_raw
            )
            and setup_control_values_equal(
                card.control_key, value.current_value_raw, execution.observed_a_value
            )
            and setup_control_values_equal(
                card.control_key, value.current_value_raw, execution.observed_a2_value
            )
            and setup_control_values_equal(
                card.control_key, value.proposed_value_raw, execution.observed_b_value
            )
        )
    except (TypeError, ValueError, OverflowError):
        return False


def _event_workspace(event: TelemetryEvent) -> str:
    identity = f"{event.event_type} {event.event_subtype or ''}".casefold()
    if any(token in identity for token in ("platform", "ride_height", "shock", "damper")):
        return "platform"
    if event.related_setup_keys:
        return "setup"
    return "overview"


def _event_qualification(
    event: TelemetryEvent,
    laps_by_key: Mapping[tuple[str, int], LapSummary],
) -> tuple[bool, tuple[str, ...]]:
    reasons = list(event.blocker_reasons)
    if (
        not event.event_id.strip()
        or event.event_id != event.event_id.strip()
        or not event.run_id.strip()
        or event.run_id != event.run_id.strip()
    ):
        reasons.append("The event has no stable event and run identity.")
    if not event.event_type.strip():
        reasons.append("The event has no stable event type.")
    if event.evidence_state not in _QUALIFIED_STATES:
        reasons.append("The event does not have a qualified evidence state.")
    if not event.valid_for_tuning:
        reasons.append("The event is not valid for tuning.")
    if not event.source_channels:
        reasons.append("The event has no recorded source channels.")
    elif any(
        not str(channel).strip()
        or str(channel) != str(channel).strip()
        or str(channel) not in _PUBLIC_EVIDENCE_CHANNELS
        for channel in event.source_channels
    ):
        reasons.append("The event contains an unrecognized or non-canonical source channel.")
    if any(
        not str(setup_key).strip() or str(setup_key) != str(setup_key).strip()
        for setup_key in event.related_setup_keys
    ):
        reasons.append("The event contains an empty or non-canonical setup-key identity.")
    peak = _finite_number(event.lap_pct_peak)
    start = _finite_number(event.lap_pct_start)
    end = _finite_number(event.lap_pct_end)
    if peak is None or not 0.0 <= peak <= 100.0:
        reasons.append("The event has no valid physical track-position peak.")
    if (event.lap_pct_start is None) != (event.lap_pct_end is None):
        reasons.append("The event track-position window is incomplete.")
    elif event.lap_pct_start is not None and (
        start is None
        or end is None
        or not 0.0 <= start <= end <= 100.0
    ):
        reasons.append("The event track-position window is invalid.")
    if event.lap_number is None:
        reasons.append("The event is not linked to a specific eligible lap.")
    else:
        lap = laps_by_key.get((event.run_id, event.lap_number))
        if lap is None:
            reasons.append("The event's source lap is unavailable in the current evidence scope.")
        elif not lap_is_eligible(lap):
            reasons.append("The event's source lap is not eligible for a setup conclusion.")
            reasons.extend(lap_ineligibility_reasons(lap))
    normalized = _unique_text(reasons)
    return not normalized, normalized


def _event_citation(
    event: TelemetryEvent,
    *,
    qualified: bool,
) -> EvidenceCitation:
    label = (event.event_subtype or event.event_type).strip() or "Unlabeled telemetry event"
    start = _finite_number(event.lap_pct_start)
    end = _finite_number(event.lap_pct_end)
    peak = _finite_number(event.lap_pct_peak)
    if start is None or end is None or not 0.0 <= start <= end <= 100.0:
        start = None
        end = None
    if peak is None or not 0.0 <= peak <= 100.0:
        peak = None
    return EvidenceCitation(
        citation_id=f"event:{event.event_id}",
        run_id=event.run_id,
        lap_number=event.lap_number,
        lap_pct_start=start,
        lap_pct_end=end,
        lap_pct_peak=peak,
        event_id=event.event_id,
        workspace=_event_workspace(event),
        phase=_typed_phase(event.event_subtype, event.event_type),
        channels=tuple(
            dict.fromkeys(
                channel
                for channel in event.source_channels
                if channel.strip() and channel == channel.strip()
            )
        ),
        evidence_state=event.evidence_state,
        valid_for_tuning=qualified,
        summary=f"{label} on lap {event.lap_number if event.lap_number is not None else 'unknown'}",
    )


def build_evidence_graph(
    *,
    claims: Sequence[GroundedClaim] = (),
    causes: Sequence[CauseHypothesis] = (),
    observations: Sequence[MechanismObservation] = (),
    events: Sequence[TelemetryEvent] = (),
    recommendations: Sequence[Recommendation] = (),
    laps: Sequence[LapSummary] = (),
    setup_values: Sequence[SetupEvidenceValue] = (),
    workflows: Sequence[ControlledWorkflow] = (),
    setup_authority_verifier: Callable[[SetupEvidenceValue], bool] | None = None,
) -> EvidenceGraph:
    """Build a traceable evidence graph while retaining fail-closed nodes."""
    nodes: dict[str, EvidenceNode] = {}
    edges: list[EvidenceEdge] = []
    graph_blockers: list[str] = []

    def add_node(node: EvidenceNode) -> None:
        if node.node_id in nodes:
            reason = f"Duplicate evidence node identity: {node.node_id}."
            graph_blockers.append(reason)
            existing = nodes[node.node_id]
            citation = existing.citation
            if citation is not None:
                citation = citation.model_copy(update={"valid_for_tuning": False})
            nodes[node.node_id] = existing.model_copy(
                update={
                    "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                    "qualified": False,
                    "blocker_reasons": _unique_text([*existing.blocker_reasons, reason]),
                    "citation": citation,
                }
            )
            return
        nodes[node.node_id] = node

    def add_edge(
        source: str,
        target: str,
        kind: EvidenceEdgeKind,
        *,
        qualified: bool,
    ) -> None:
        edges.append(
            EvidenceEdge(
                source_node_id=source,
                target_node_id=target,
                kind=kind,
                qualified=qualified,
            )
        )

    laps_by_key: dict[tuple[str, int], LapSummary] = {}
    lap_identity_counts = Counter((lap.run_id, lap.lap_number) for lap in laps)
    reported_duplicate_laps: set[tuple[str, int]] = set()
    for lap in laps:
        if (
            not lap.run_id.strip()
            or lap.run_id != lap.run_id.strip()
            or not lap.lap_id.strip()
            or lap.lap_id != lap.lap_id.strip()
            or lap.lap_number < 0
        ):
            graph_blockers.append("A lap has an invalid run, lap, or lap-number identity.")
            continue
        key = (lap.run_id, lap.lap_number)
        if lap_identity_counts[key] > 1:
            if key not in reported_duplicate_laps:
                reason = f"Duplicate lap evidence for {lap.run_id} lap {lap.lap_number}."
                graph_blockers.append(reason)
                reported_duplicate_laps.add(key)
                add_node(
                    EvidenceNode(
                        node_id=f"lap:{lap.run_id}:{lap.lap_number}",
                        entity_id=f"{lap.run_id}:{lap.lap_number}",
                        kind=EvidenceNodeKind.LAP,
                        label=f"Lap {lap.lap_number}",
                        evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                        qualified=False,
                        blocker_reasons=(reason,),
                        citation=EvidenceCitation(
                            citation_id=f"lap:{lap.run_id}:{lap.lap_number}",
                            run_id=lap.run_id,
                            lap_number=lap.lap_number,
                            workspace="laps",
                            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
                            valid_for_tuning=False,
                            summary=f"Lap {lap.lap_number} has a duplicate identity",
                        ),
                    )
                )
            continue
        if key in laps_by_key:
            reason = f"Duplicate lap evidence for {lap.run_id} lap {lap.lap_number}."
            graph_blockers.append(reason)
            node_id = f"lap:{lap.run_id}:{lap.lap_number}"
            if node_id in nodes:
                nodes[node_id] = nodes[node_id].model_copy(
                    update={
                        "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                        "qualified": False,
                        "blocker_reasons": (reason,),
                    }
                )
            continue
        laps_by_key[key] = lap
        qualified = lap_is_eligible(lap)
        blockers = () if qualified else tuple(lap_ineligibility_reasons(lap))
        add_node(
            EvidenceNode(
                node_id=f"lap:{lap.run_id}:{lap.lap_number}",
                entity_id=f"{lap.run_id}:{lap.lap_number}",
                kind=EvidenceNodeKind.LAP,
                label=f"Lap {lap.lap_number}",
                evidence_state=(
                    EvidenceState.MEASURED if qualified else EvidenceState.BLOCKED_BY_CONTEXT
                ),
                qualified=qualified,
                blocker_reasons=blockers,
                citation=EvidenceCitation(
                    citation_id=f"lap:{lap.run_id}:{lap.lap_number}",
                    run_id=lap.run_id,
                    lap_number=lap.lap_number,
                    workspace="laps",
                    evidence_state=(
                        EvidenceState.MEASURED
                        if qualified
                        else EvidenceState.BLOCKED_BY_CONTEXT
                    ),
                    valid_for_tuning=False,
                    summary=f"Lap {lap.lap_number} eligibility",
                ),
            )
        )

    observation_qualified: dict[str, bool] = {}
    referenced_channels: dict[str, bool] = {}
    for observation in observations:
        if not observation.observation_id.strip() or observation.observation_id != observation.observation_id.strip():
            graph_blockers.append("A mechanism observation has an invalid identity.")
            continue
        for index, citation in enumerate(observation.citations):
            entity_id = f"{observation.observation_id}:{index}"
            lap_node_id = f"lap:{citation.run_id}:{citation.lap_number}"
            lap_node = nodes.get(lap_node_id)
            qualified = bool(
                observation.qualified
                and citation.run_id == observation.run_id
                and lap_node is not None
                and lap_node.qualified
                and citation.evidence_state in _QUALIFIED_STATES
            )
            blockers = () if qualified else (
                "The typed observation is not bound to a qualified eligible lap.",
            )
            observation_qualified[entity_id] = qualified
            node_id = f"observation:{entity_id}"
            add_node(EvidenceNode(
                node_id=node_id,
                entity_id=entity_id,
                kind=EvidenceNodeKind.OBSERVATION,
                label=f"{observation.mechanism.value.replace('_', ' ').title()} observation",
                evidence_state=(
                    citation.evidence_state if qualified else EvidenceState.BLOCKED_BY_CONTEXT
                ),
                qualified=qualified,
                blocker_reasons=blockers,
                citation=EvidenceCitation(
                    citation_id=node_id,
                    run_id=citation.run_id,
                    lap_number=citation.lap_number,
                    lap_pct_start=citation.lap_pct_start,
                    lap_pct_end=citation.lap_pct_end,
                    lap_pct_peak=citation.lap_pct_peak,
                    event_id=None,
                    workspace="platform",
                    phase=_typed_phase(citation.phase),
                    channels=citation.source_channels,
                    evidence_state=(
                        citation.evidence_state
                        if qualified
                        else EvidenceState.BLOCKED_BY_CONTEXT
                    ),
                    valid_for_tuning=False,
                    summary=observation.summary,
                ),
            ))
            if lap_node is not None:
                add_edge(
                    node_id,
                    lap_node_id,
                    EvidenceEdgeKind.OBSERVED_ON,
                    qualified=qualified,
                )
            for channel in citation.source_channels:
                referenced_channels[channel] = referenced_channels.get(channel, False) or qualified
                add_edge(
                    node_id,
                    f"channel:{channel}",
                    EvidenceEdgeKind.USES_CHANNEL,
                    qualified=qualified,
                )

    events_by_id: dict[str, TelemetryEvent] = {}
    event_qualified: dict[str, bool] = {}
    referenced_setups: dict[str, bool] = {}
    for event in events:
        if (
            not event.event_id.strip()
            or event.event_id != event.event_id.strip()
            or not event.run_id.strip()
            or event.run_id != event.run_id.strip()
        ):
            graph_blockers.append("A telemetry event has an invalid event or run identity.")
            continue
        if event.event_id in events_by_id:
            reason = f"Duplicate telemetry event identity: {event.event_id}."
            graph_blockers.append(reason)
            event_qualified[event.event_id] = False
            node_id = f"event:{event.event_id}"
            if node_id in nodes:
                existing = nodes[node_id]
                citation = existing.citation
                if citation is not None:
                    citation = citation.model_copy(update={"valid_for_tuning": False})
                nodes[node_id] = existing.model_copy(
                    update={
                        "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                        "qualified": False,
                        "blocker_reasons": (reason,),
                        "citation": citation,
                    }
                )
            continue
        events_by_id[event.event_id] = event
        qualified, blockers = _event_qualification(event, laps_by_key)
        event_qualified[event.event_id] = qualified
        event_node_id = f"event:{event.event_id}"
        add_node(
            EvidenceNode(
                node_id=event_node_id,
                entity_id=event.event_id,
                kind=EvidenceNodeKind.EVENT,
                label=(event.event_subtype or event.event_type).strip()
                or f"Unlabeled event {event.event_id}",
                evidence_state=event.evidence_state,
                qualified=qualified,
                blocker_reasons=blockers,
                citation=_event_citation(event, qualified=qualified),
            )
        )
        if event.lap_number is not None:
            lap_node_id = f"lap:{event.run_id}:{event.lap_number}"
            if lap_node_id in nodes:
                add_edge(
                    event_node_id,
                    lap_node_id,
                    EvidenceEdgeKind.OBSERVED_ON,
                    qualified=qualified and nodes[lap_node_id].qualified,
                )
        for channel in dict.fromkeys(event.source_channels):
            if not channel.strip() or channel != channel.strip():
                graph_blockers.append(
                    f"Event {event.event_id} has a malformed source-channel identity."
                )
                continue
            referenced_channels[channel] = referenced_channels.get(channel, False) or qualified
            add_edge(
                event_node_id,
                f"channel:{channel}",
                EvidenceEdgeKind.USES_CHANNEL,
                qualified=qualified,
            )
        for setup_key in dict.fromkeys(event.related_setup_keys):
            if not setup_key.strip() or setup_key != setup_key.strip():
                graph_blockers.append(
                    f"Event {event.event_id} has a malformed setup-key identity."
                )
                continue
            referenced_setups[setup_key] = referenced_setups.get(setup_key, False) or qualified
            add_edge(
                event_node_id,
                f"setup:{setup_key}",
                EvidenceEdgeKind.RELATES_TO_SETUP,
                qualified=qualified,
            )

    recommendation_qualified: dict[str, bool] = {}
    seen_recommendation_ids: set[str] = set()
    for recommendation in recommendations:
        if (
            not recommendation.recommendation_id.strip()
            or recommendation.recommendation_id != recommendation.recommendation_id.strip()
            or not recommendation.run_id.strip()
            or recommendation.run_id != recommendation.run_id.strip()
        ):
            graph_blockers.append("A recommendation has an invalid recommendation or run identity.")
            continue
        node_id = f"recommendation:{recommendation.recommendation_id}"
        if recommendation.recommendation_id in seen_recommendation_ids:
            reason = f"Duplicate recommendation identity: {recommendation.recommendation_id}."
            graph_blockers.append(reason)
            recommendation_qualified[recommendation.recommendation_id] = False
            if node_id in nodes:
                nodes[node_id] = nodes[node_id].model_copy(
                    update={
                        "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                        "qualified": False,
                        "blocker_reasons": (reason,),
                    }
                )
            continue
        seen_recommendation_ids.add(recommendation.recommendation_id)
        linked_events = [
            events_by_id[event_id]
            for event_id in recommendation.evidence_event_ids
            if event_id in events_by_id
        ]
        linked = [event_qualified.get(event_id) for event_id in recommendation.evidence_event_ids]
        blockers = list(recommendation.blocker_reasons)
        if not recommendation.issue.strip():
            blockers.append("The recommendation has no stable issue label.")
        if recommendation.evidence_state not in _QUALIFIED_STATES:
            blockers.append("The recommendation does not have a qualified evidence state.")
        if not recommendation.source_channels:
            blockers.append("The recommendation has no recorded source channels.")
        elif any(
            not channel.strip() or channel != channel.strip()
            for channel in recommendation.source_channels
        ):
            blockers.append(
                "The recommendation contains an empty or non-canonical source-channel identity."
            )
        if not linked:
            blockers.append("The recommendation is not linked to telemetry events.")
        elif not all(value is True for value in linked):
            blockers.append("A linked event is unavailable or not qualified on an eligible lap.")
        if linked_events and any(event.run_id != recommendation.run_id for event in linked_events):
            blockers.append("A linked event belongs to a different run than the recommendation.")
        linked_channels = {
            channel for event in linked_events for channel in event.source_channels
        }
        unsupported_channels = set(recommendation.source_channels) - linked_channels
        if unsupported_channels:
            blockers.append(
                "Recommendation source channels are not supplied by its linked events: "
                + ", ".join(sorted(unsupported_channels))
                + "."
            )
        normalized = _unique_text(blockers)
        qualified = not normalized
        recommendation_qualified[recommendation.recommendation_id] = qualified
        add_node(
            EvidenceNode(
                node_id=node_id,
                entity_id=recommendation.recommendation_id,
                kind=EvidenceNodeKind.RECOMMENDATION,
                label=recommendation.issue.strip()
                or f"Unlabeled recommendation {recommendation.recommendation_id}",
                evidence_state=recommendation.evidence_state,
                qualified=qualified,
                blocker_reasons=normalized,
            )
        )
        for event_id in dict.fromkeys(recommendation.evidence_event_ids):
            target = f"event:{event_id}"
            if target not in nodes:
                graph_blockers.append(
                    f"Recommendation {recommendation.recommendation_id} references missing event "
                    f"{event_id}."
                )
                continue
            add_edge(
                node_id,
                target,
                EvidenceEdgeKind.RECOMMENDS_FROM,
                qualified=qualified and nodes[target].qualified,
            )
        for channel in dict.fromkeys(recommendation.source_channels):
            if not channel.strip() or channel != channel.strip():
                graph_blockers.append(
                    f"Recommendation {recommendation.recommendation_id} has a malformed channel identity."
                )
                continue
            referenced_channels[channel] = referenced_channels.get(channel, False) or qualified
            add_edge(
                node_id,
                f"channel:{channel}",
                EvidenceEdgeKind.USES_CHANNEL,
                qualified=qualified,
            )

    workflow_qualified: dict[str, bool] = {}
    seen_workflow_ids: set[str] = set()
    for workflow in workflows:
        if (
            not workflow.workflow_id.strip()
            or workflow.workflow_id != workflow.workflow_id.strip()
            or not workflow.source_run_id.strip()
            or workflow.source_run_id != workflow.source_run_id.strip()
        ):
            graph_blockers.append("A workflow has an invalid workflow or source-run identity.")
            continue
        if workflow.workflow_id in seen_workflow_ids:
            reason = f"Duplicate workflow identity: {workflow.workflow_id}."
            graph_blockers.append(reason)
            workflow_qualified[workflow.workflow_id] = False
            node_id = f"workflow:{workflow.workflow_id}"
            if node_id in nodes:
                nodes[node_id] = nodes[node_id].model_copy(
                    update={
                        "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                        "qualified": False,
                        "blocker_reasons": (reason,),
                    }
                )
            continue
        seen_workflow_ids.add(workflow.workflow_id)
        quality = workflow.quality
        execution = workflow.execution
        try:
            rescored_quality = (
                score_test_execution(execution) if execution is not None else None
            )
        except (TypeError, ValueError, OverflowError):
            rescored_quality = None
        card = workflow.packet.primary_test
        card_semantically_complete = bool(
            card is not None and _controlled_card_is_semantically_complete(card)
        )
        card_provenance_matches_stage_b = bool(
            card is not None
            and card.proposed_value_provenance
            and set(card.proposed_value_provenance)
            == {workflow.stage_run_ids.get("B")}
        )
        execution_matches_card = False
        if execution is not None and card is not None:
            try:
                execution_matches_card = bool(
                    execution.control_key == card.control_key
                    and setup_control_values_equal(
                        card.control_key, execution.planned_b_value, card.proposed_value_raw
                    )
                    and setup_control_values_equal(
                        card.control_key, execution.observed_a_value, card.current_value
                    )
                    and setup_control_values_equal(
                        card.control_key, execution.observed_b_value, card.proposed_value_raw
                    )
                    and setup_control_values_equal(
                        card.control_key, execution.observed_a2_value, card.current_value
                    )
                )
            except (TypeError, ValueError, OverflowError):
                execution_matches_card = False
        stage_keys_complete = set(workflow.stage_run_ids) == {"A", "B", "A2"}
        stage_laps_complete = set(workflow.stage_eligible_lap_numbers) == {"A", "B", "A2"}
        stage_evidence_qualified = bool(
            stage_keys_complete
            and stage_laps_complete
            and len(set(workflow.stage_run_ids.values())) == 3
        )
        if stage_evidence_qualified:
            for stage in ("A", "B", "A2"):
                run_id = workflow.stage_run_ids[stage]
                lap_numbers = workflow.stage_eligible_lap_numbers[stage]
                consecutive = bool(
                    len(lap_numbers) == 3
                    and tuple(lap_numbers)
                    == tuple(range(lap_numbers[0], lap_numbers[0] + 3))
                )
                if not consecutive or any(
                    (lap := laps_by_key.get((run_id, lap_number))) is None
                    or not lap_is_eligible(lap)
                    for lap_number in lap_numbers
                ):
                    stage_evidence_qualified = False
                    break
        event_evidence_qualified = bool(
            card is not None
            and card.evidence_event_ids
            and all(
                event_qualified.get(event_id) is True
                and card.control_key in events_by_id[event_id].related_setup_keys
                and events_by_id[event_id].run_id == workflow.source_run_id
                for event_id in card.evidence_event_ids
                if event_id in events_by_id
            )
            and all(event_id in events_by_id for event_id in card.evidence_event_ids)
        )
        qualified = bool(
            workflow.status == "scored"
            and quality is not None
            and execution is not None
            and rescored_quality is not None
            and quality == rescored_quality
            and execution_matches_card
            and card_semantically_complete
            and card_provenance_matches_stage_b
            and (
                execution.eligible_laps_a,
                execution.eligible_laps_b,
                execution.eligible_laps_a2,
            )
            == tuple(
                len(workflow.stage_eligible_lap_numbers.get(stage, ()))
                for stage in ("A", "B", "A2")
            )
            and quality.protocol_valid
            and quality.controlled_effect_eligible
            and quality.verdict in {"keep", "undo"}
            and not quality.blockers
            and card is not None
            and event_evidence_qualified
            and stage_evidence_qualified
            and workflow.stage_run_ids.get("A") == workflow.source_run_id
        )
        blockers = () if qualified else (
            "The workflow has not produced a protocol-valid controlled effect.",
        )
        workflow_qualified[workflow.workflow_id] = qualified
        node_id = f"workflow:{workflow.workflow_id}"
        add_node(
            EvidenceNode(
                node_id=node_id,
                entity_id=workflow.workflow_id,
                kind=EvidenceNodeKind.WORKFLOW,
                label=f"Controlled workflow {workflow.workflow_id}",
                evidence_state=(
                    EvidenceState.CONTROLLED_TEST_EFFECT
                    if qualified
                    else EvidenceState.NEEDS_CONFIRMATION
                ),
                qualified=qualified,
                blocker_reasons=blockers,
            )
        )
        if card is not None:
            referenced_setups[card.control_key] = (
                referenced_setups.get(card.control_key, False) or qualified
            )
            add_edge(
                node_id,
                f"setup:{card.control_key}",
                EvidenceEdgeKind.TESTS_SETUP,
                qualified=qualified,
            )
            for event_id in card.evidence_event_ids:
                target = f"event:{event_id}"
                if target in nodes:
                    add_edge(
                        node_id,
                        target,
                        EvidenceEdgeKind.SUPPORTED_BY,
                        qualified=qualified and nodes[target].qualified,
                    )
        for stage, run_id in workflow.stage_run_ids.items():
            for lap_number in workflow.stage_eligible_lap_numbers.get(stage, ()):
                target = f"lap:{run_id}:{lap_number}"
                if target in nodes:
                    add_edge(
                        node_id,
                        target,
                        EvidenceEdgeKind.PART_OF_WORKFLOW,
                        qualified=qualified and nodes[target].qualified,
                    )

    setup_value_counts = Counter(value.setup_key for value in setup_values)
    setup_value_by_key = {value.setup_key: value for value in setup_values}
    setup_authorization_by_key: dict[str, str] = {}
    for value in setup_values:
        if setup_value_counts[value.setup_key] > 1:
            graph_blockers.append(f"Duplicate exact setup value identity: {value.setup_key}.")
            referenced_setups[value.setup_key] = False
            continue
        trusted_event_links = [
            bool(
                event_qualified.get(item)
                and value.setup_key in events_by_id[item].related_setup_keys
            )
            for item in value.source_event_ids
            if item in events_by_id
        ]
        if len(trusted_event_links) != len(value.source_event_ids):
            trusted_event_links.append(False)
        workflow_by_id = {workflow.workflow_id: workflow for workflow in workflows}
        trusted_workflow_links = [
            bool(
                workflow_qualified.get(item)
                and _setup_value_matches_controlled_workflow(value, workflow_by_id[item])
            )
            for item in value.workflow_ids
            if item in workflow_by_id
        ]
        if len(trusted_workflow_links) != len(value.workflow_ids):
            trusted_workflow_links.append(False)
        qualified = bool(
            (trusted_event_links or trusted_workflow_links)
            and all(item is True for item in [*trusted_event_links, *trusted_workflow_links])
        )
        authorization_fingerprint = _setup_authorization_fingerprint(
            control_key=value.setup_key,
            current_value=value.current_value_raw,
            proposed_value=value.proposed_value_raw,
            proposed_value_provenance=value.proposed_value_provenance,
            source_event_ids=value.source_event_ids,
        )
        repository_authority_verified = False
        if (
            value.authorization_basis == "repository_revalidated_legal_option"
            and setup_authority_verifier is not None
        ):
            try:
                repository_authority_verified = (
                    setup_authority_verifier(value) is True
                )
            except Exception:  # pragma: no cover - injected boundary must fail closed
                repository_authority_verified = False
        repository_authority_resolved = bool(
            value.authorization_basis == "repository_revalidated_legal_option"
            and repository_authority_verified
            and trusted_event_links
            and all(trusted_event_links)
            and not value.workflow_ids
            and authorization_fingerprint is not None
            and setup_target_increment_blocker(
                value.setup_key,
                value.current_value_raw,
                value.proposed_value_raw,
            )
            is None
        )
        workflow_authority_resolved = bool(
            value.authorization_basis == "scored_controlled_workflow"
            and trusted_workflow_links
            and all(trusted_workflow_links)
            and authorization_fingerprint is not None
        )
        authority_resolved = repository_authority_resolved or workflow_authority_resolved
        if value.value_display is not None:
            try:
                allowed_displays = {
                    format_setup_value(value.setup_key, value.current_value_raw),
                    format_setup_value(value.setup_key, value.proposed_value_raw),
                }
            except (TypeError, ValueError, OverflowError):
                allowed_displays = set()
            qualified = bool(
                qualified and authority_resolved and value.value_display in allowed_displays
            )
        if qualified and authority_resolved and authorization_fingerprint is not None:
            setup_authorization_by_key[value.setup_key] = authorization_fingerprint
        # An exact displayed value must stand on its own provenance. It cannot
        # inherit trust from an unrelated generic event-to-control association.
        referenced_setups[value.setup_key] = qualified

    # Recompute referenced-node trust after duplicate identities and workflow /
    # recommendation qualification are known. A poisoned event must not leave a
    # qualified channel or setup node behind through an earlier optimistic OR.
    qualified_event_channels = {
        channel
        for event_id, event in events_by_id.items()
        if event_qualified.get(event_id) is True
        for channel in event.source_channels
    }
    qualified_recommendation_channels = {
        channel
        for recommendation in recommendations
        if recommendation_qualified.get(recommendation.recommendation_id) is True
        for channel in recommendation.source_channels
    }
    qualified_observation_channels = {
        channel
        for observation in observations
        for index, citation in enumerate(observation.citations)
        if observation_qualified.get(f"{observation.observation_id}:{index}") is True
        for channel in citation.source_channels
    }
    for channel in referenced_channels:
        referenced_channels[channel] = channel in (
            qualified_event_channels
            | qualified_recommendation_channels
            | qualified_observation_channels
        )
    qualified_event_setups = {
        setup_key
        for event_id, event in events_by_id.items()
        if event_qualified.get(event_id) is True
        for setup_key in event.related_setup_keys
    }
    qualified_workflow_setups = {
        workflow.packet.primary_test.control_key
        for workflow in workflows
        if workflow_qualified.get(workflow.workflow_id) is True
        and workflow.packet.primary_test is not None
    }
    for setup_key in referenced_setups:
        if setup_key not in setup_value_by_key:
            referenced_setups[setup_key] = setup_key in (
                qualified_event_setups | qualified_workflow_setups
            )

    for channel, qualified in sorted(referenced_channels.items()):
        add_node(
            EvidenceNode(
                node_id=f"channel:{channel}",
                entity_id=channel,
                kind=EvidenceNodeKind.CHANNEL,
                label=channel,
                evidence_state=(
                    EvidenceState.MEASURED if qualified else EvidenceState.BLOCKED_BY_CONTEXT
                ),
                qualified=qualified,
                blocker_reasons=(
                    ()
                    if qualified
                    else ("No qualified event currently establishes this channel as evidence.",)
                ),
            )
        )
    for setup_key, qualified in sorted(referenced_setups.items()):
        value = setup_value_by_key.get(setup_key)
        label = setup_key if value is None or value.value_display is None else (
            f"{setup_key}: {value.value_display}"
        )
        add_node(
            EvidenceNode(
                node_id=f"setup:{setup_key}",
                entity_id=setup_key,
                kind=EvidenceNodeKind.SETUP,
                label=label,
                evidence_state=(
                    EvidenceState.CONTROLLED_TEST_EFFECT
                    if qualified
                    else EvidenceState.BLOCKED_BY_CONTEXT
                ),
                qualified=qualified,
                authorization_fingerprint=(
                    setup_authorization_by_key.get(setup_key) if qualified else None
                ),
                blocker_reasons=(
                    ()
                    if qualified
                    else ("No qualified telemetry event or controlled workflow links this setup value.",)
                ),
            )
        )

    for claim in claims:
        node_id = f"claim:{claim.claim_id}"
        blockers = list(claim.blocker_reasons)
        supported_channels: set[str] = set()
        supported_setup_keys: set[str] = set()
        if claim.evidence_state not in _QUALIFIED_STATES:
            blockers.append("The claim does not have a qualified evidence state.")
        anchors = 0
        provenance_anchors = 0
        for event_id in claim.supporting_event_ids:
            target = f"event:{event_id}"
            if target not in nodes:
                blockers.append(f"Supporting event {event_id} is unavailable.")
                continue
            anchors += 1
            if not nodes[target].qualified:
                blockers.append(f"Supporting event {event_id} is not qualified.")
            else:
                provenance_anchors += 1
                supported_channels.update(events_by_id[event_id].source_channels)
                supported_setup_keys.update(events_by_id[event_id].related_setup_keys)
        for event_id in claim.contradicting_event_ids:
            target = f"event:{event_id}"
            if target in nodes and nodes[target].qualified:
                blockers.append(f"Qualified event {event_id} contradicts this claim.")
            elif target not in nodes:
                blockers.append(f"Contradicting event {event_id} is unavailable.")
            else:
                blockers.append(f"Contradicting event {event_id} is not qualified.")
        for recommendation_id in claim.recommendation_ids:
            anchors += 1
            if recommendation_qualified.get(recommendation_id) is not True:
                blockers.append(f"Recommendation {recommendation_id} is unavailable or unqualified.")
            else:
                provenance_anchors += 1
                recommendation = next(
                    item
                    for item in recommendations
                    if item.recommendation_id == recommendation_id
                )
                supported_channels.update(recommendation.source_channels)
        for reference in claim.lap_references:
            anchors += 1
            lap = laps_by_key.get((reference.run_id, reference.lap_number))
            if lap is None or not lap_is_eligible(lap):
                blockers.append(
                    f"Lap {reference.run_id}/{reference.lap_number} is unavailable or ineligible."
                )
        for workflow_id in claim.workflow_ids:
            anchors += 1
            if workflow_qualified.get(workflow_id) is not True:
                blockers.append(f"Workflow {workflow_id} has no qualified controlled effect.")
            else:
                provenance_anchors += 1
                workflow = next(item for item in workflows if item.workflow_id == workflow_id)
                card = workflow.packet.primary_test
                if card is not None:
                    supported_setup_keys.add(card.control_key)
        unsupported_channels = set(claim.source_channels) - supported_channels
        if unsupported_channels:
            blockers.append(
                "Claim source channels are not supplied by its qualified evidence: "
                + ", ".join(sorted(unsupported_channels))
                + "."
            )
        unsupported_setups = set(claim.setup_keys) - supported_setup_keys
        if unsupported_setups:
            blockers.append(
                "Claim setup links are not supplied by its qualified evidence: "
                + ", ".join(sorted(unsupported_setups))
                + "."
            )
        for setup_key in claim.setup_keys:
            if (
                setup_key in setup_value_by_key
                and not nodes[f"setup:{setup_key}"].qualified
            ):
                blockers.append(
                    f"Exact setup value {setup_key} lacks its own qualified provenance."
                )
        if anchors == 0:
            blockers.append("The claim has no qualified event, recommendation, lap, or workflow anchor.")
        if provenance_anchors == 0:
            blockers.append(
                "The claim has no qualified provenance-bearing event, recommendation, or workflow."
            )
        normalized = _unique_text(blockers)
        qualified = not normalized
        add_node(
            EvidenceNode(
                node_id=node_id,
                entity_id=claim.claim_id,
                kind=EvidenceNodeKind.CLAIM,
                label=claim.text,
                evidence_state=claim.evidence_state,
                qualified=qualified,
                blocker_reasons=normalized,
            )
        )
        for recommendation_id in claim.recommendation_ids:
            target = f"recommendation:{recommendation_id}"
            if target in nodes:
                add_edge(
                    node_id,
                    target,
                    EvidenceEdgeKind.SUPPORTED_BY,
                    qualified=qualified and nodes[target].qualified,
                )
        for reference in claim.lap_references:
            target = f"lap:{reference.run_id}:{reference.lap_number}"
            if target in nodes:
                add_edge(
                    node_id,
                    target,
                    EvidenceEdgeKind.OBSERVED_ON,
                    qualified=qualified and nodes[target].qualified,
                )
        for workflow_id in claim.workflow_ids:
            target = f"workflow:{workflow_id}"
            if target in nodes:
                add_edge(
                    node_id,
                    target,
                    EvidenceEdgeKind.SUPPORTED_BY,
                    qualified=qualified and nodes[target].qualified,
                )
        for channel in claim.source_channels:
            target = f"channel:{channel}"
            current = nodes.get(target)
            if current is None:
                nodes[target] = EvidenceNode(
                    node_id=target,
                    entity_id=channel,
                    kind=EvidenceNodeKind.CHANNEL,
                    label=channel,
                    evidence_state=(
                        EvidenceState.MEASURED
                        if qualified
                        else EvidenceState.BLOCKED_BY_CONTEXT
                    ),
                    qualified=qualified,
                    blocker_reasons=(
                        ()
                        if qualified
                        else ("No qualified claim currently establishes this channel.",)
                    ),
                )
            elif qualified and not current.qualified:
                nodes[target] = current.model_copy(
                    update={
                        "evidence_state": EvidenceState.MEASURED,
                        "qualified": True,
                        "blocker_reasons": (),
                    }
                )
            add_edge(
                node_id,
                target,
                EvidenceEdgeKind.USES_CHANNEL,
                qualified=qualified,
            )
        for event_id in claim.supporting_event_ids:
            target = f"event:{event_id}"
            if target in nodes:
                add_edge(
                    node_id,
                    target,
                    EvidenceEdgeKind.SUPPORTED_BY,
                    qualified=qualified and nodes[target].qualified,
                )
        for event_id in claim.contradicting_event_ids:
            target = f"event:{event_id}"
            if target in nodes:
                add_edge(
                    node_id,
                    target,
                    EvidenceEdgeKind.CONTRADICTED_BY,
                    qualified=nodes[target].qualified,
                )
        for setup_key in claim.setup_keys:
            target = f"setup:{setup_key}"
            if target in nodes:
                if (
                    qualified
                    and setup_key not in setup_value_by_key
                    and not nodes[target].qualified
                ):
                    nodes[target] = nodes[target].model_copy(
                        update={
                            "evidence_state": claim.evidence_state,
                            "qualified": True,
                            "blocker_reasons": (),
                        }
                    )
                add_edge(
                    node_id,
                    target,
                    EvidenceEdgeKind.RELATES_TO_SETUP,
                    qualified=qualified and nodes[target].qualified,
                )

    for value in setup_values:
        setup_node_id = f"setup:{value.setup_key}"
        for event_id in value.source_event_ids:
            target = f"event:{event_id}"
            if setup_node_id in nodes and target in nodes:
                add_edge(
                    setup_node_id,
                    target,
                    EvidenceEdgeKind.SUPPORTED_BY,
                    qualified=nodes[setup_node_id].qualified and nodes[target].qualified,
                )
        for workflow_id in value.workflow_ids:
            target = f"workflow:{workflow_id}"
            if setup_node_id in nodes and target in nodes:
                add_edge(
                    setup_node_id,
                    target,
                    EvidenceEdgeKind.PART_OF_WORKFLOW,
                    qualified=nodes[setup_node_id].qualified and nodes[target].qualified,
                )

    for cause in causes:
        cause_node_id = f"cause:{cause.cause_id}"
        support_targets = tuple(dict.fromkeys((
            *(f"event:{event_id}" for event_id in cause.supporting_event_ids),
            *(
                f"observation:{observation_id}"
                for observation_id in cause.supporting_observation_ids
            ),
        )))
        contradiction_targets = tuple(dict.fromkeys((
            *(f"event:{event_id}" for event_id in cause.contradicting_event_ids),
            *(
                f"observation:{observation_id}"
                for observation_id in cause.contradicting_observation_ids
            ),
        )))
        diagnostic_workflows = tuple(
            outcome.workflow_id
            for outcome in cause.controlled_outcomes
            if outcome.diagnostic_validity == "mechanism_diagnostic"
            and outcome.outcome in {"supported", "contradicted"}
        )
        missing_targets = tuple(
            target
            for target in (*support_targets, *contradiction_targets)
            if target not in nodes
        )
        qualified_targets = tuple(
            target
            for target in (*support_targets, *contradiction_targets)
            if target in nodes and nodes[target].qualified
        )
        qualified_diagnostic_workflows = tuple(
            workflow_id
            for workflow_id in diagnostic_workflows
            if nodes.get(f"workflow:{workflow_id}") is not None
            and nodes[f"workflow:{workflow_id}"].qualified
        )
        cause_blockers = list(cause.blocker_reasons)
        cause_blockers.extend(
            f"Cause evidence target {target} is unavailable."
            for target in missing_targets
        )
        qualified = bool(qualified_targets or qualified_diagnostic_workflows)
        add_node(EvidenceNode(
            node_id=cause_node_id,
            entity_id=cause.cause_id,
            kind=EvidenceNodeKind.CAUSE,
            label=cause.label,
            evidence_state=(
                EvidenceState.OBSERVED_CORRELATION
                if qualified_targets
                else EvidenceState.CONTROLLED_TEST_EFFECT
                if qualified_diagnostic_workflows
                else EvidenceState.BLOCKED_BY_CONTEXT
            ),
            qualified=qualified,
            blocker_reasons=() if qualified else _unique_text((
                *cause_blockers,
                "No qualified evidence currently supports or contradicts this cause.",
            )),
        ))
        for target in support_targets:
            if target in nodes:
                add_edge(
                    cause_node_id,
                    target,
                    EvidenceEdgeKind.SUPPORTED_BY,
                    qualified=qualified and nodes[target].qualified,
                )
        for target in contradiction_targets:
            if target in nodes:
                add_edge(
                    cause_node_id,
                    target,
                    EvidenceEdgeKind.CONTRADICTED_BY,
                    qualified=qualified and nodes[target].qualified,
                )
        for outcome in cause.controlled_outcomes:
            target = f"workflow:{outcome.workflow_id}"
            if target not in nodes or outcome.diagnostic_validity != "mechanism_diagnostic":
                continue
            edge_kind = (
                EvidenceEdgeKind.SUPPORTED_BY
                if outcome.outcome == "supported"
                else EvidenceEdgeKind.CONTRADICTED_BY
            )
            if outcome.outcome in {"supported", "contradicted"}:
                add_edge(
                    cause_node_id,
                    target,
                    edge_kind,
                    qualified=qualified and nodes[target].qualified,
                )

    edge_qualifications: dict[tuple[str, str, EvidenceEdgeKind], list[bool]] = {}
    for edge in edges:
        if edge.source_node_id not in nodes or edge.target_node_id not in nodes:
            continue
        edge_qualifications.setdefault(
            (edge.source_node_id, edge.target_node_id, edge.kind), []
        ).append(edge.qualified)
    unique_edges: list[tuple[str, str, EvidenceEdgeKind, bool]] = []
    for source, target, kind in sorted(
        edge_qualifications,
        key=lambda item: (item[0], item[1], item[2].value),
    ):
        qualifications = edge_qualifications[(source, target, kind)]
        if len(set(qualifications)) > 1:
            graph_blockers.append(
                f"Conflicting qualification was withheld for graph edge {source} -> {target} ({kind.value})."
            )
        unique_edges.append((source, target, kind, all(qualifications)))
    return EvidenceGraph(
        nodes=tuple(nodes[key] for key in sorted(nodes)),
        edges=tuple(
            EvidenceEdge(
                source_node_id=source,
                target_node_id=target,
                kind=kind,
                qualified=(
                    qualified
                    and nodes[source].qualified
                    and nodes[target].qualified
                ),
            )
            for source, target, kind, qualified in unique_edges
        ),
        blocker_reasons=_unique_text(graph_blockers),
    )


def _qualified_evidence_citations(graph: EvidenceGraph) -> dict[str, EvidenceCitation]:
    return {
        node.entity_id: node.citation
        for node in graph.nodes
        if node.kind in {EvidenceNodeKind.EVENT, EvidenceNodeKind.OBSERVATION}
        and node.qualified
        and node.citation is not None
    }


def _qualified_event_setup_links(graph: EvidenceGraph) -> set[tuple[str, str]]:
    nodes_by_id = {node.node_id: node for node in graph.nodes}
    links: set[tuple[str, str]] = set()
    for edge in graph.edges:
        source = nodes_by_id.get(edge.source_node_id)
        target = nodes_by_id.get(edge.target_node_id)
        if (
            edge.kind is EvidenceEdgeKind.RELATES_TO_SETUP
            and edge.qualified
            and source is not None
            and source.kind is EvidenceNodeKind.EVENT
            and source.qualified
            and source.node_id == f"event:{source.entity_id}"
            and target is not None
            and target.kind is EvidenceNodeKind.SETUP
            and target.qualified
            and target.node_id == f"setup:{target.entity_id}"
        ):
            links.add((source.node_id, target.node_id))
    return links


def _card_matches_setup_authorization(graph: EvidenceGraph, card: Any) -> bool:
    fingerprint = _setup_authorization_fingerprint(
        control_key=card.control_key,
        current_value=card.current_value,
        proposed_value=card.proposed_value_raw,
        proposed_value_provenance=card.proposed_value_provenance,
        source_event_ids=card.evidence_event_ids,
    )
    if fingerprint is None:
        return False
    setup_node = next(
        (
            node
            for node in graph.nodes
            if node.node_id == f"setup:{card.control_key}"
            and node.entity_id == card.control_key
            and node.kind is EvidenceNodeKind.SETUP
            and node.qualified
        ),
        None,
    )
    return bool(
        setup_node is not None
        and setup_node.authorization_fingerprint is not None
        and setup_node.authorization_fingerprint == fingerprint
    )


def _controlled_card_is_semantically_complete(card: Any) -> bool:
    required_text = (
        card.hypothesis,
        card.control_key,
        card.control_label,
        card.exact_change,
        card.change_size,
        card.target_phase,
        card.expected_mechanism,
        card.rollback_rule,
        card.keep_rule,
        card.stop_rule,
    )
    required_collections = (
        card.success_metrics,
        card.countereffects,
        card.evidence_event_ids,
        card.proposed_value_provenance,
        card.do_not_change,
    )
    if any(
        not isinstance(value, str) or not value.strip() or value != value.strip()
        for value in required_text
    ):
        return False
    if any(
        not values
        or any(
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            for value in values
        )
        for values in required_collections
    ):
        return False
    if any(len(set(values)) != len(values) for values in required_collections):
        return False
    if any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", identity) is None
        for identity in (*card.evidence_event_ids, *card.proposed_value_provenance)
    ):
        return False
    if (
        card.current_value is None
        or isinstance(card.current_value, bool)
        or card.proposed_value is None
        or not str(card.proposed_value).strip()
        or card.proposed_value_raw is None
        or isinstance(card.proposed_value_raw, bool)
    ):
        return False
    if len(card.stages) != 3 or tuple(stage.stage for stage in card.stages) != (
        "A",
        "B",
        "A2",
    ):
        return False
    if not all(
        stage.setup_instruction.strip()
        and stage.purpose.strip()
        and stage.setup_instruction == stage.setup_instruction.strip()
        and stage.purpose == stage.purpose.strip()
        for stage in card.stages
    ):
        return False
    spec = SETUP_CONTROL_SPECS.get(card.control_key)
    if spec is None or card.control_label != spec.label:
        return False
    try:
        current_display = format_setup_value(card.control_key, card.current_value)
        proposed_display = format_setup_value(card.control_key, card.proposed_value_raw)
        assessment = assess_setup_change(
            card.control_key, card.current_value, card.proposed_value_raw
        )
        increment_blocker = setup_target_increment_blocker(
            card.control_key, card.current_value, card.proposed_value_raw
        )
        expected_mechanism = expected_control_effect(
            card.control_key, card.direction_sign, card.current_value
        )
    except (TypeError, ValueError, OverflowError):
        return False
    if (
        increment_blocker is not None
        or assessment.label != "small"
        or assessment.display_delta is None
        or abs(assessment.display_delta) <= 1e-12
        or (1 if assessment.display_delta > 0 else -1) != card.direction_sign
    ):
        return False
    transition = (
        f"{current_display} -> {proposed_display} "
        "(adjacent observed tech-passing option)"
    )
    baseline_instruction = f"Keep {spec.label} at the recorded baseline value."
    expected_stage_instructions = (
        baseline_instruction,
        f"Change only {spec.label}: {transition}.",
        baseline_instruction,
    )
    return bool(
        card.proposed_value == proposed_display
        and card.exact_change == transition
        and card.change_size
        == f"{assessment.label.title()} test input · adjacent observed garage option"
        and card.expected_mechanism == expected_mechanism
        and tuple(stage.setup_instruction for stage in card.stages)
        == expected_stage_instructions
        and set(card.do_not_change) == set(SETUP_CONTROL_SPECS) - {card.control_key}
    )


def _measurement_mission_is_semantically_complete(mission: MeasurementMission) -> bool:
    required_text = (mission.purpose, mission.target_phase, mission.stop_rule)
    required_collections = (
        mission.procedure,
        mission.controlled_variables,
        mission.acceptance_thresholds,
    )
    return bool(
        all(
            isinstance(value, str) and value.strip() and value == value.strip()
            for value in required_text
        )
        and all(
            values
            and len(set(values)) == len(values)
            and all(
                isinstance(value, str) and value.strip() and value == value.strip()
                for value in values
            )
            for values in required_collections
        )
        and all(
            isinstance(value, str) and value.strip() and value == value.strip()
            for value in mission.blockers
        )
    )


def _public_non_action_plan(plan: InformationPlan) -> InformationPlan:
    """Remove producer prose from plans that carry no setup authority."""
    if plan.kind == "measurement_mission" and plan.measurement_mission is not None:
        mission = plan.measurement_mission
        safe_mission = MeasurementMission(
            purpose="Collect the missing qualified evidence without changing the setup.",
            procedure=(
                "Record the declared telemetry channels on eligible laps with the setup unchanged.",
            ),
            required_laps_or_passes=mission.required_laps_or_passes,
            controlled_variables=("Keep the setup and run context unchanged.",),
            target_phase="producer-declared target phase",
            acceptance_thresholds=(
                f"Record at least {mission.required_laps_or_passes} additional eligible laps or passes.",
            ),
            stop_rule="Stop and discard the sample after a pit, reset, incident, or invalid lap.",
            blockers=("No setup change is authorized until this mission is complete.",),
        )
        return InformationPlan(
            kind="measurement_mission",
            title="Run the evidence measurement mission",
            instruction=safe_mission.procedure[0],
            rationale="More qualified evidence is required before any setup action.",
            measurement_mission=safe_mission,
            mission_contract=plan.mission_contract,
            blocker_reasons=safe_mission.blockers,
        )
    if plan.kind == "discriminator" and plan.discriminator is not None:
        discriminator = plan.discriminator
        cause_ids = _unique_text(discriminator.distinguishes_cause_ids)
        if cause_ids:
            safe_discriminator = CauseDiscriminator(
                discriminator_id="evidence-discriminator",
                title="Evidence discriminator",
                instruction=(
                    "Record an unchanged-setup comparison that tests the declared cause."
                ),
                target_phase="producer-declared target phase",
                acceptance_thresholds=(
                    "Complete the declared eligible observations without changing the setup",
                ),
                distinguishes_cause_ids=cause_ids,
                source_event_ids=_unique_text(discriminator.source_event_ids),
            )
            return InformationPlan(
                kind="discriminator",
                title="Run the evidence discriminator",
                instruction=safe_discriminator.instruction,
                rationale="One unresolved cause requires a controlled observation.",
                discriminator=safe_discriminator,
                mission_contract=plan.mission_contract,
                source_event_ids=safe_discriminator.source_event_ids,
            )
    if plan.kind == "stop_testing":
        return InformationPlan(
            kind="stop_testing",
            title="Stop repeating this measurement",
            instruction="Preserve the evidence and redesign the next measurement.",
            rationale="The exact mission reached a declared feasibility or information stop rule.",
            mission_contract=plan.mission_contract,
            blocker_reasons=("The current measurement contract should not be repeated unchanged.",),
        )
    return InformationPlan(
        kind="blocked",
        title="Setup action withheld",
        instruction="Collect qualified evidence before changing the setup.",
        rationale="The current report does not authorize an exact setup target.",
        blocker_reasons=("No evidence-qualified setup action is authorized.",),
        recovery_priority=plan.recovery_priority,
    )


def _public_authorized_plan(plan: InformationPlan) -> InformationPlan:
    card = plan.controlled_test
    assert card is not None
    safe_stages = tuple(
        stage.model_copy(
            update={
                "purpose": {
                    "A": "Measure baseline variability.",
                    "B": "Test the single evidence-linked control.",
                    "A2": "Confirm reversibility and reject run drift.",
                }[stage.stage]
            }
        )
        for stage in card.stages
    )
    safe_card = card.model_copy(
        update={
            "hypothesis": "Test the evidence-linked single-control hypothesis.",
            "target_phase": "producer-declared target phase",
            "success_metrics": (
                "B must beat A and restored A2 beyond the empirical noise floor.",
            ),
            "countereffects": (
                "No measured countereffect may worsen beyond its noise floor.",
            ),
            "rollback_rule": (
                f"Restore {card.control_label} to the recorded A value after a countereffect."
            ),
            "keep_rule": (
                "Keep only if B beats A and restored A2 beyond noise without a countereffect."
            ),
            "stop_rule": (
                "Stop after a pit, reset, caution, incident, integrity fault, contact, or unsafe handling."
            ),
            "stages": safe_stages,
        }
    )
    return InformationPlan(
        kind="controlled_test",
        title="Run one controlled A/B/A2 test",
        instruction=card.exact_change,
        rationale="The evidence-linked Test Director card passed current-run revalidation.",
        setup_authorized=True,
        controlled_test=safe_card,
        source_event_ids=card.evidence_event_ids,
    )


def _public_evidence_citation(citation: EvidenceCitation) -> EvidenceCitation:
    channels = tuple(
        channel for channel in citation.channels if channel in _PUBLIC_EVIDENCE_CHANNELS
    )
    return EvidenceCitation(
        **{
            **citation.model_dump(),
            "channels": channels,
            "valid_for_tuning": citation.valid_for_tuning and bool(channels),
            "summary": (
                f"{citation.evidence_state.value.replace('_', ' ').title()} evidence in "
                f"the {citation.workspace} workspace."
            ),
        }
    )


def _public_evidence_graph(graph: EvidenceGraph) -> EvidenceGraph:
    safe_labels = {
        EvidenceNodeKind.CLAIM: "Evidence claim",
        EvidenceNodeKind.EVENT: "Telemetry event",
        EvidenceNodeKind.RECOMMENDATION: "Evidence recommendation",
        EvidenceNodeKind.LAP: "Lap evidence",
        EvidenceNodeKind.CHANNEL: "Telemetry channel",
        EvidenceNodeKind.SETUP: "Setup evidence",
        EvidenceNodeKind.WORKFLOW: "Controlled workflow",
        EvidenceNodeKind.CAUSE: "Cause candidate",
        EvidenceNodeKind.OBSERVATION: "Mechanism observation",
    }
    retained = {
        node.node_id: node
        for node in graph.nodes
        if node.kind is not EvidenceNodeKind.CHANNEL
        or node.entity_id in _PUBLIC_EVIDENCE_CHANNELS
    }
    public_citations = {
        node_id: (
            _public_evidence_citation(node.citation)
            if node.citation is not None
            else None
        )
        for node_id, node in retained.items()
    }
    qualified = {
        node_id: bool(
            node.qualified
            and (
                node.kind is not EvidenceNodeKind.EVENT
                or public_citations[node_id] is not None
                and public_citations[node_id].valid_for_tuning
            )
        )
        for node_id, node in retained.items()
    }
    public_nodes = tuple(
        EvidenceNode(
            node_id=node.node_id,
            entity_id=node.entity_id,
            kind=node.kind,
            label=safe_labels[node.kind],
            evidence_state=node.evidence_state,
            qualified=qualified[node.node_id],
            blocker_reasons=(
                ()
                if qualified[node.node_id]
                else ("This evidence node is not qualified for a setup conclusion.",)
            ),
            citation=public_citations[node.node_id],
            authorization_fingerprint=(
                node.authorization_fingerprint
                if qualified[node.node_id] and node.kind is EvidenceNodeKind.SETUP
                else None
            ),
        )
        for node in sorted(retained.values(), key=lambda item: item.node_id)
    )
    public_edges = tuple(
        EvidenceEdge(
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            kind=edge.kind,
            qualified=bool(
                edge.qualified
                and qualified[edge.source_node_id]
                and qualified[edge.target_node_id]
            ),
        )
        for edge in sorted(
            (
                edge
                for edge in graph.edges
                if edge.source_node_id in retained and edge.target_node_id in retained
            ),
            key=lambda item: (
                item.source_node_id,
                item.target_node_id,
                item.kind.value,
            ),
        )
    )
    return EvidenceGraph(
        nodes=public_nodes,
        edges=public_edges,
        blocker_reasons=(
            ("One or more evidence graph records failed qualification.",)
            if graph.blocker_reasons
            or len(retained) != len(graph.nodes)
            or any(node.qualified and not qualified[node.node_id] for node in retained.values())
            else ()
        ),
    )


def _public_response_memory(summary: ResponseMemorySummary) -> ResponseMemorySummary:
    counterfactual = summary.counterfactual_range
    if counterfactual is not None:
        counterfactual = counterfactual.model_copy(
            update={"metric": "target_phase_time_delta", "unit": "s"}
        )
    return summary.model_copy(
        update={
            "context_key": "qualified-context" if summary.context_key is not None else None,
            "control_key": (
                summary.control_key
                if summary.control_key in SETUP_CONTROL_SPECS
                else "unresolved_control"
            ),
            "verdicts": (
                ("qualified controlled result",) if summary.verdicts else ()
            ),
            "counterfactual_range": counterfactual,
            "matching_context": (
                ("Exact producer-declared context matched.",)
                if summary.matching_context
                else ()
            ),
            "mismatches": (
                ("A producer-declared context mismatch was recorded.",)
                if summary.mismatches
                else ()
            ),
            "blocker_reasons": (
                ("Response memory did not qualify for setup authorization.",)
                if summary.blocker_reasons
                else ()
            ),
        }
    )


def _revalidate_response_summaries(
    summaries: Sequence[ResponseMemorySummary],
    *,
    current_context_key: str | None,
) -> tuple[tuple[ResponseMemorySummary, ...], tuple[str, ...]]:
    retained = [summary for summary in summaries if summary.status != "exact_context_match"]
    candidates: dict[str, ResponseMemorySummary] = {}
    blockers: list[str] = []
    invalid_scope: set[tuple[str, int]] = set()
    for summary in summaries:
        if summary.status != "exact_context_match":
            continue
        if current_context_key is None or summary.context_key != current_context_key:
            invalid_scope.add((summary.control_key, summary.direction_sign))
            blockers.append(
                "An exact-context response summary did not match the current report context."
            )
            continue
        candidates.setdefault(summary.model_dump_json(), summary)

    unique_candidates = tuple(candidates[key] for key in sorted(candidates))
    observation_counts = Counter(
        identity
        for summary in unique_candidates
        for identity in summary.source_observation_ids
    )
    run_counts = Counter(
        identity for summary in unique_candidates for identity in summary.source_run_ids
    )
    event_counts = Counter(
        identity for summary in unique_candidates for identity in summary.evidence_event_ids
    )
    conflicting_scope: set[tuple[str, int]] = set()
    for summary in unique_candidates:
        conflicts = bool(
            any(observation_counts[item] > 1 for item in summary.source_observation_ids)
            or any(run_counts[item] > 1 for item in summary.source_run_ids)
            or any(event_counts[item] > 1 for item in summary.evidence_event_ids)
        )
        if conflicts:
            conflicting_scope.add((summary.control_key, summary.direction_sign))
            blockers.append(
                "Overlapping response-memory provenance was withheld instead of double-counted."
            )
        else:
            retained.append(summary)

    for control_key, direction_sign in sorted(invalid_scope | conflicting_scope):
        retained.append(
            ResponseMemorySummary(
                context_key=current_context_key,
                status=(
                    "contradictory_history"
                    if (control_key, direction_sign) in conflicting_scope
                    else "context_mismatch"
                ),
                control_key=control_key,
                direction_sign=direction_sign,
                qualified_observation_count=0,
                matching_context=(
                    (f"Exact context key {current_context_key}",)
                    if current_context_key is not None
                    else ()
                ),
                mismatches=("The response-memory scope could not be proven exact.",),
                blocker_reasons=(
                    "Rebuild response memory from distinct observations in the current context.",
                ),
            )
        )
    return (
        tuple(
            sorted(
                retained,
                key=lambda summary: (
                    summary.control_key,
                    summary.direction_sign,
                    summary.status,
                    summary.context_key or "",
                    summary.source_observation_ids,
                ),
            )
        ),
        _unique_text(blockers),
    )


def _evidence_independence_clusters(
    cause_id: str,
    polarity: str,
    citations: Sequence[EvidenceCitation],
) -> tuple[EvidenceIndependenceCluster, ...]:
    """Group correlated same-run, same-phase, overlapping-window observations.

    Repeated laps inside one continuous run show repeatability, but they are not
    independent causal experiments. A new run creates a new cluster. Distinct
    non-overlapping physical windows in the same run remain separate.
    """

    grouped: dict[tuple[str, str | None], list[EvidenceCitation]] = {}
    for citation in citations:
        grouped.setdefault((citation.run_id, citation.phase), []).append(citation)
    result: list[EvidenceIndependenceCluster] = []
    for (run_id, phase), scoped in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1] or "")
    ):
        ordered = sorted(
            scoped,
            key=lambda citation: (
                citation.lap_pct_start
                if citation.lap_pct_start is not None
                else citation.lap_pct_peak
                if citation.lap_pct_peak is not None
                else -1.0,
                citation.lap_pct_end
                if citation.lap_pct_end is not None
                else citation.lap_pct_peak
                if citation.lap_pct_peak is not None
                else 101.0,
                citation.lap_number if citation.lap_number is not None else -1,
                citation.citation_id,
            ),
        )
        partitions: list[list[EvidenceCitation]] = []
        partition_end: list[float | None] = []
        for citation in ordered:
            start = (
                citation.lap_pct_start
                if citation.lap_pct_start is not None
                else citation.lap_pct_peak
            )
            end = (
                citation.lap_pct_end
                if citation.lap_pct_end is not None
                else citation.lap_pct_peak
            )
            matched_index = next(
                (
                    index
                    for index, current_end in enumerate(partition_end)
                    if current_end is None or start is None or start <= current_end + 1.0
                ),
                None,
            )
            if matched_index is None:
                partitions.append([citation])
                partition_end.append(end)
            else:
                partitions[matched_index].append(citation)
                if end is not None:
                    current_end = partition_end[matched_index]
                    partition_end[matched_index] = (
                        end if current_end is None else max(current_end, end)
                    )
        for partition in partitions:
            starts = [
                value
                for citation in partition
                if (value := citation.lap_pct_start) is not None
            ]
            ends = [
                value
                for citation in partition
                if (value := citation.lap_pct_end) is not None
            ]
            citation_ids = tuple(
                dict.fromkeys(citation.citation_id for citation in partition)
            )
            digest = hashlib.sha256(
                "|".join((cause_id, polarity, run_id, phase or "", *citation_ids)).encode()
            ).hexdigest()[:16]
            result.append(EvidenceIndependenceCluster(
                cluster_id=f"cluster:{digest}",
                cause_id=cause_id,
                polarity=polarity,
                run_id=run_id,
                phase=phase,
                lap_numbers=tuple(sorted({
                    citation.lap_number
                    for citation in partition
                    if citation.lap_number is not None
                })),
                citation_ids=citation_ids,
                lap_pct_start=min(starts) if starts and len(starts) == len(partition) else None,
                lap_pct_end=max(ends) if ends and len(ends) == len(partition) else None,
            ))
    return tuple(result)


def rank_competing_causes(
    hypotheses: Sequence[CauseHypothesis],
    graph: EvidenceGraph,
) -> tuple[RankedCause, ...]:
    """Rank causes by independent eligible laps and exact controlled outcomes."""
    cause_ids = [cause.cause_id for cause in hypotheses]
    if len(cause_ids) != len(set(cause_ids)):
        raise ValueError("competing causes require unique cause_id values")
    citations = _qualified_evidence_citations(graph)
    preliminary: list[dict[str, Any]] = []
    for cause in hypotheses:
        supporting_ids = tuple(dict.fromkeys((
            *cause.supporting_event_ids,
            *cause.supporting_observation_ids,
        )))
        contradicting_ids = tuple(dict.fromkeys((
            *cause.contradicting_event_ids,
            *cause.contradicting_observation_ids,
        )))
        overlapping_ids = set(supporting_ids) & set(contradicting_ids)
        support = tuple(
            citations[event_id]
            for event_id in supporting_ids
            if event_id in citations and event_id not in overlapping_ids
        )
        against = tuple(
            citations[event_id]
            for event_id in contradicting_ids
            if event_id in citations and event_id not in overlapping_ids
        )
        missing = list(cause.required_evidence)
        missing.extend(
            f"Qualified supporting event {event_id}"
            for event_id in supporting_ids
            if event_id not in citations
        )
        missing.extend(
            f"Qualified contradicting event {event_id}"
            for event_id in contradicting_ids
            if event_id not in citations
        )
        if overlapping_ids:
            missing.append(
                "Evidence declared as both support and contradiction must be reclassified."
            )
        controlled_support = tuple(
            outcome
            for outcome in cause.controlled_outcomes
            if outcome.diagnostic_validity == "mechanism_diagnostic"
            and outcome.outcome == "supported"
        )
        controlled_against = tuple(
            outcome
            for outcome in cause.controlled_outcomes
            if outcome.diagnostic_validity == "mechanism_diagnostic"
            and outcome.outcome == "contradicted"
        )
        controlled_inconclusive = tuple(
            outcome
            for outcome in cause.controlled_outcomes
            if outcome.diagnostic_validity == "mechanism_diagnostic"
            and outcome.outcome == "inconclusive"
        )
        controlled_invalid = tuple(
            outcome for outcome in cause.controlled_outcomes if outcome.outcome == "invalid"
        )
        missing.extend(
            "A protocol-valid controlled result was inconclusive; run a new exact discriminator."
            for _outcome in controlled_inconclusive
        )
        controlled_invalid_blockers = [
            reason
            for outcome in controlled_invalid
            for reason in outcome.blocker_reasons
        ]
        normalized_missing = _unique_text(missing)
        normalized_blockers = _unique_text(
            [*cause.blocker_reasons, *controlled_invalid_blockers]
        )
        support_clusters = _evidence_independence_clusters(
            cause.cause_id, "support", support
        )
        against_clusters = _evidence_independence_clusters(
            cause.cause_id, "contradiction", against
        )
        controlled_conflict = bool(controlled_support and controlled_against)
        ruled_out_by_controlled_result = bool(
            controlled_against
            and not controlled_support
            and not controlled_inconclusive
            and not controlled_invalid
        )
        ruled_out = ruled_out_by_controlled_result
        has_any_contradiction = bool(against_clusters or controlled_against)
        support_tier = (
            3
            if controlled_support and not controlled_conflict and not controlled_against
            else 2
            if len(support_clusters) >= _MIN_REPEATED_CAUSE_EVIDENCE_UNITS
            else 1
            if support_clusters
            else 0
        )
        strength = (
            0 if ruled_out else 1,
            support_tier,
            0 if controlled_conflict else 1,
            0 if controlled_against else 1,
            0 if against_clusters else 1,
            min(len(support_clusters), _MIN_REPEATED_CAUSE_EVIDENCE_UNITS),
            -len(normalized_missing),
            -len(normalized_blockers),
        )
        preliminary.append(
            {
                "cause": cause,
                "support": support,
                "against": against,
                "missing": normalized_missing,
                "blockers": normalized_blockers,
                "support_unit_count": len(support_clusters),
                "against_unit_count": len(against_clusters),
                "support_clusters": support_clusters,
                "against_clusters": against_clusters,
                "controlled_support": controlled_support,
                "controlled_against": controlled_against,
                "controlled_inconclusive": controlled_inconclusive,
                "controlled_invalid": controlled_invalid,
                "controlled_conflict": controlled_conflict,
                "has_any_contradiction": has_any_contradiction,
                "ruled_out": ruled_out,
                "strength": strength,
            }
        )

    ordered = sorted(
        preliminary,
        key=lambda item: (
            *(-value for value in item["strength"]),
            item["cause"].cause_id,
        ),
    )
    distinct_strengths = sorted(
        {item["strength"] for item in preliminary},
        reverse=True,
    )
    rank_by_strength = {strength: index + 1 for index, strength in enumerate(distinct_strengths)}
    rank_one = [item for item in preliminary if rank_by_strength[item["strength"]] == 1]
    uniquely_likely_id = None
    if len(rank_one) == 1:
        leader = rank_one[0]
        if (
            (
                leader["controlled_support"]
                or leader["support_unit_count"]
                >= _MIN_REPEATED_CAUSE_EVIDENCE_UNITS
            )
            and not leader["has_any_contradiction"]
            and not leader["controlled_conflict"]
            and not leader["controlled_inconclusive"]
            and not leader["controlled_invalid"]
            and (
                leader["controlled_support"]
                or not leader["missing"]
                and not leader["blockers"]
            )
            and not leader["ruled_out"]
        ):
            uniquely_likely_id = leader["cause"].cause_id

    ranked: list[RankedCause] = []
    for item in ordered:
        cause = item["cause"]
        if item["ruled_out"]:
            status = "ruled_out"
        elif (
            item["controlled_conflict"]
            or item["controlled_inconclusive"]
            or item["controlled_invalid"]
        ):
            status = "unresolved"
        elif cause.cause_id == uniquely_likely_id:
            status = "likely"
        elif not item["support_clusters"] and not item["controlled_support"] and (
            item["against_clusters"] or item["missing"] or item["blockers"]
        ):
            status = "unresolved"
        else:
            status = "possible"
        ranked.append(
            RankedCause(
                cause_id=cause.cause_id,
                label=cause.label,
                hypothesis=cause.hypothesis,
                status=status,
                ordinal_rank=rank_by_strength[item["strength"]],
                rank_basis=(
                    "Ordinal evidence ordering: "
                    f"{item['support_unit_count']} supporting and "
                    f"{item['against_unit_count']} contradicting run/window independence "
                    "clusters; repeated laps inside one cluster show repeatability without "
                    "becoming separate causal votes; "
                    f"{len(item['controlled_support'])} supporting, "
                    f"{len(item['controlled_against'])} contradicting, "
                    f"{len(item['controlled_inconclusive'])} inconclusive, and "
                    f"{len(item['controlled_invalid'])} invalid exact controlled outcomes; "
                    f"{len(item['missing'])} missing. "
                    "This is not a probability."
                ),
                supporting_evidence=item["support"],
                contradicting_evidence=item["against"],
                supporting_evidence_unit_count=item["support_unit_count"],
                contradicting_evidence_unit_count=item["against_unit_count"],
                supporting_clusters=item["support_clusters"],
                contradicting_clusters=item["against_clusters"],
                controlled_outcomes=cause.controlled_outcomes,
                controlled_conflict=item["controlled_conflict"],
                missing_evidence=item["missing"],
                blocker_reasons=item["blockers"],
                discriminator=cause.discriminator,
            )
        )
    return tuple(ranked)


def _controlled_outcome_assessment(
    outcome: Any,
) -> ControlledOutcomeAssessment:
    if outcome.outcome == "invalid":
        mechanism_state = "invalid"
        response_result = "invalid"
    elif outcome.diagnostic_validity == "mechanism_diagnostic":
        mechanism_state = {
            "supported": "supported",
            "contradicted": "weakened",
            "inconclusive": "inconclusive",
        }[outcome.outcome]
        response_result = outcome.control_direction_result or "inconclusive"
    else:
        mechanism_state = "unchanged"
        response_result = outcome.control_direction_result or "inconclusive"
    policy_acceptable = (
        True if outcome.verdict == "keep" else False if outcome.verdict == "undo" else None
    )
    return ControlledOutcomeAssessment(
        workflow_id=outcome.workflow_id,
        mechanism=MechanismClaimOutcome(
            workflow_id=outcome.workflow_id,
            state=mechanism_state,
            diagnostic_validity=outcome.diagnostic_validity,
            reason=(
                "A producer-owned diagnostic intervention may update mechanism evidence."
                if outcome.diagnostic_validity == "mechanism_diagnostic"
                else "This setup-control test measures treatment response; mechanism truth is unchanged."
            ),
        ),
        control_response=ControlResponseOutcome(
            workflow_id=outcome.workflow_id,
            result=response_result,
            metric=outcome.metric,
            phase=outcome.phase,
            control_key=outcome.control_key,
            reason=(
                "The exact control moved the target metric in the declared direction."
                if response_result == "matched"
                else "The exact control missed the declared target direction."
                if response_result == "missed"
                else "The exact control response was not conclusive."
            ),
        ),
        policy=PolicyAcceptabilityOutcome(
            workflow_id=outcome.workflow_id,
            verdict=outcome.verdict,
            acceptable=policy_acceptable,
            countereffects=outcome.countereffects,
            reason=(
                "Keep is a policy verdict, not proof of the mechanism."
                if outcome.verdict == "keep"
                else "Undo rejects this exact policy while preserving separate mechanism evidence."
                if outcome.verdict == "undo"
                else "Retest requires another protocol-valid result."
                if outcome.verdict == "retest"
                else "Invalid execution cannot update mechanism, response, or policy memory."
            ),
        ),
    )


def _graph_with_ranked_causes(
    graph: EvidenceGraph,
    causes: Sequence[RankedCause],
) -> EvidenceGraph:
    """Ensure the canonical backend graph, not the adapter, owns cause assertions."""

    nodes = {
        node.node_id: node
        for node in graph.nodes
        if node.kind is not EvidenceNodeKind.CAUSE
    }
    edges = {
        (edge.source_node_id, edge.target_node_id, edge.kind): edge
        for edge in graph.edges
        if edge.source_node_id in nodes and edge.target_node_id in nodes
    }
    for cause in causes:
        node_id = f"cause:{cause.cause_id}"
        citations = (*cause.supporting_evidence, *cause.contradicting_evidence)
        diagnostic = tuple(
            outcome
            for outcome in cause.controlled_outcomes
            if outcome.diagnostic_validity == "mechanism_diagnostic"
            and outcome.outcome in {"supported", "contradicted"}
        )
        qualified = bool(citations or diagnostic)
        nodes[node_id] = EvidenceNode(
            node_id=node_id,
            entity_id=cause.cause_id,
            kind=EvidenceNodeKind.CAUSE,
            label=cause.label,
            evidence_state=(
                citations[0].evidence_state
                if citations
                else EvidenceState.CONTROLLED_TEST_EFFECT
                if diagnostic
                else EvidenceState.BLOCKED_BY_CONTEXT
            ),
            qualified=qualified,
            blocker_reasons=(
                ()
                if qualified
                else ("No qualified evidence currently supports or contradicts this cause.",)
            ),
        )
        for polarity, scoped, edge_kind in (
            ("support", cause.supporting_evidence, EvidenceEdgeKind.SUPPORTED_BY),
            ("contradiction", cause.contradicting_evidence, EvidenceEdgeKind.CONTRADICTED_BY),
        ):
            del polarity
            for citation in scoped:
                target = (
                    f"event:{citation.event_id}"
                    if citation.event_id is not None
                    else citation.citation_id
                )
                if target in nodes:
                    edges[(node_id, target, edge_kind)] = EvidenceEdge(
                        source_node_id=node_id,
                        target_node_id=target,
                        kind=edge_kind,
                        qualified=nodes[target].qualified,
                    )
        for outcome in diagnostic:
            target = f"workflow:{outcome.workflow_id}"
            if target in nodes:
                edge_kind = (
                    EvidenceEdgeKind.SUPPORTED_BY
                    if outcome.outcome == "supported"
                    else EvidenceEdgeKind.CONTRADICTED_BY
                )
                edges[(node_id, target, edge_kind)] = EvidenceEdge(
                    source_node_id=node_id,
                    target_node_id=target,
                    kind=edge_kind,
                    qualified=nodes[target].qualified,
                )
    return EvidenceGraph(
        nodes=tuple(nodes[node_id] for node_id in sorted(nodes)),
        edges=tuple(
            edges[key]
            for key in sorted(edges, key=lambda item: (item[0], item[1], item[2].value))
        ),
        blocker_reasons=graph.blocker_reasons,
    )


def build_reasoning_snapshot(
    *,
    run_id: str,
    session_id: str | None,
    graph: EvidenceGraph,
    ranked_causes: Sequence[RankedCause],
    measurement_plan: InformationPlan,
    data_quality: DataQualityAssessment,
    lap_context: LapEngineeringContextReport | None = None,
    mechanism_episodes: Sequence[MechanismEpisode] = (),
    mechanism_episode_blocker_reasons: Sequence[str] = (),
    blocker_reasons: Sequence[str] = (),
) -> ReasoningSnapshot:
    canonical_graph = _graph_with_ranked_causes(graph, ranked_causes)
    clusters = tuple(
        cluster
        for cause in ranked_causes
        for cluster in (*cause.supporting_clusters, *cause.contradicting_clusters)
    )
    assessments_by_workflow: dict[str, ControlledOutcomeAssessment] = {}
    duplicate_workflows: set[str] = set()
    for cause in ranked_causes:
        for outcome in cause.controlled_outcomes:
            assessment = _controlled_outcome_assessment(outcome)
            existing = assessments_by_workflow.get(outcome.workflow_id)
            if existing is not None and existing != assessment:
                duplicate_workflows.add(outcome.workflow_id)
                continue
            assessments_by_workflow[outcome.workflow_id] = assessment
    if duplicate_workflows:
        raise ValueError(
            "one controlled workflow cannot publish conflicting reasoning assessments"
        )
    if data_quality.status == "blocked" or measurement_plan.kind == "blocked":
        level = "blocked"
    elif measurement_plan.kind == "controlled_test" and measurement_plan.setup_authorized:
        level = "controlled_setup"
    elif measurement_plan.kind in {"measurement_mission", "discriminator"}:
        level = "measurement"
    else:
        level = "observation"
    card = measurement_plan.controlled_test
    authority = ReasoningAuthorityEnvelope(
        level=level,
        setup_authorized=level == "controlled_setup",
        control_key=card.control_key if level == "controlled_setup" and card is not None else None,
        source_event_ids=(
            card.evidence_event_ids
            if level == "controlled_setup" and card is not None
            else ()
        ),
        reason=(
            "One current-run evidence-linked A/B/A2 setup test is authorized."
            if level == "controlled_setup"
            else "Collect the producer-owned measurement without changing setup."
            if level == "measurement"
            else "Evidence may be observed but does not authorize setup."
            if level == "observation"
            else "Current evidence integrity blocks engineering authority."
        ),
    )
    return ReasoningSnapshot(
        run_id=run_id,
        session_id=session_id,
        evidence_graph=canonical_graph,
        causes=tuple(ranked_causes),
        evidence_clusters=clusters,
        controlled_outcomes=tuple(
            assessments_by_workflow[key] for key in sorted(assessments_by_workflow)
        ),
        measurement_plan=measurement_plan,
        data_quality=data_quality,
        lap_context=lap_context,
        mechanism_episodes=tuple(mechanism_episodes),
        mechanism_episode_blocker_reasons=_unique_text(
            mechanism_episode_blocker_reasons
        ),
        authority=authority,
        blocker_reasons=_unique_text(blocker_reasons),
    )


def _measurement_channel_lineage(
    channel: str,
    channel_lineage_by_channel: Mapping[str, Sequence[str]] | None,
) -> frozenset[str]:
    folded = channel.strip().casefold()
    if not folded:
        return frozenset()
    lineage = {folded}
    if channel_lineage_by_channel is None:
        return frozenset(lineage)
    for key in (channel, folded):
        values = channel_lineage_by_channel.get(key)
        if values is not None:
            lineage.update(
                value.strip().casefold()
                for value in values
                if isinstance(value, str) and value.strip()
            )
    return frozenset(lineage)


def evaluate_measurement_candidates(
    causes: Sequence[RankedCause],
    measurement_candidates: Sequence[MeasurementCandidate],
    *,
    known_blockers: Sequence[MeasurementBlocker] = (),
    known_available_channels: Sequence[str] = (),
    graph: EvidenceGraph | None = None,
    current_run_id: str | None = None,
    affected_health_channels: Sequence[str] = (),
    channel_lineage_by_channel: Mapping[str, Sequence[str]] | None = None,
) -> MeasurementSelectionAudit:
    """Evaluate producer candidates against planner-owned current-run identities.

    Ranking is ordinal and deterministic.  It deliberately carries no probability
    or formal information-gain claim.
    """
    candidate_counts = Counter(candidate.candidate_id for candidate in measurement_candidates)
    duplicate_candidate_ids = tuple(
        sorted(candidate_id for candidate_id, count in candidate_counts.items() if count > 1)
    )
    blocker_counts = Counter(blocker.blocker_id for blocker in known_blockers)
    ambiguous_blocker_ids = {
        blocker_id for blocker_id, count in blocker_counts.items() if count > 1
    }
    blockers_by_id = {
        blocker.blocker_id: blocker
        for blocker in known_blockers
        if blocker.blocker_id not in ambiguous_blocker_ids
    }
    all_cause_ids = {cause.cause_id for cause in causes}
    unresolved_cause_ids = {
        cause.cause_id for cause in causes if cause.status != "ruled_out"
    }
    discriminator_contracts: dict[
        str,
        set[tuple[str, tuple[str, ...], tuple[str, ...]]],
    ] = {}
    for cause in causes:
        discriminator = cause.discriminator
        if discriminator is None:
            continue
        discriminator_contracts.setdefault(discriminator.discriminator_id, set()).add(
            (
                discriminator.target_phase,
                discriminator.source_event_ids,
                discriminator.distinguishes_cause_ids,
            )
        )
    qualified_events = {
        node.entity_id: node
        for node in graph.nodes
        if node.kind is EvidenceNodeKind.EVENT
        and node.qualified
        and node.citation is not None
        and node.citation.valid_for_tuning
    } if graph is not None else {}
    available_channels = {
        channel.strip().casefold()
        for channel in known_available_channels
        if isinstance(channel, str) and channel.strip()
    }
    affected_lineage: set[str] = set()
    for channel in affected_health_channels:
        affected_lineage.update(
            _measurement_channel_lineage(channel, channel_lineage_by_channel)
        )

    evaluations: list[MeasurementCandidateEvaluation] = []
    for candidate in measurement_candidates:
        if candidate.candidate_id in duplicate_candidate_ids:
            evaluations.append(
                MeasurementCandidateEvaluation(
                    candidate_id=candidate.candidate_id,
                    admissible=False,
                    priority="integrity",
                    required_new_laps=candidate.required_laps,
                    rejection_reasons=("duplicate_candidate_id",),
                    priority_rank=measurement_priority_rank("integrity"),
                    blocker_coverage=0,
                    cause_coverage=0,
                )
            )
            continue

        claimed_blockers = set(candidate.resolves_blocker_ids)
        unknown_blockers = claimed_blockers - set(blockers_by_id)
        unauthorized_blockers = {
            blocker_id
            for blocker_id in claimed_blockers & set(blockers_by_id)
            if candidate.candidate_id
            not in blockers_by_id[blocker_id].resolving_candidate_ids
        }
        claimed_causes = set(candidate.distinguishes_cause_ids)
        unknown_causes = claimed_causes - all_cause_ids
        candidate_contracts = discriminator_contracts.get(candidate.candidate_id, set())
        authorized_cause_ids: set[str] = set()
        if len(candidate_contracts) == 1:
            target_phase, source_event_ids, cause_ids = next(iter(candidate_contracts))
            if (
                candidate.target_phase == target_phase
                and candidate.source_event_ids == source_event_ids
            ):
                authorized_cause_ids.update(cause_ids)
        unauthorized_causes = (
            claimed_causes & all_cause_ids
        ) - authorized_cause_ids
        resolved_blocker_ids = tuple(
            blocker_id
            for blocker_id in candidate.resolves_blocker_ids
            if blocker_id in blockers_by_id
            and candidate.candidate_id
            in blockers_by_id[blocker_id].resolving_candidate_ids
        )
        distinguished_cause_ids = tuple(
            cause_id
            for cause_id in candidate.distinguishes_cause_ids
            if cause_id in unresolved_cause_ids
            and cause_id in authorized_cause_ids
        )
        unknown_event_ids: list[str] = []
        cross_run_event_ids: list[str] = []
        resolved_source_event_ids: list[str] = []
        for event_id in candidate.source_event_ids:
            event_node = qualified_events.get(event_id)
            if event_node is None or event_node.citation is None:
                unknown_event_ids.append(event_id)
            elif (
                current_run_id is not None
                and event_node.citation.run_id != current_run_id
            ):
                cross_run_event_ids.append(event_id)
            else:
                resolved_source_event_ids.append(event_id)

        unavailable_required_channels = tuple(
            channel
            for channel in candidate.required_channels
            if channel.strip().casefold() not in available_channels
        )
        required_lineage: set[str] = set()
        for channel in candidate.required_channels:
            required_lineage.update(
                _measurement_channel_lineage(channel, channel_lineage_by_channel)
            )
        affected = bool(required_lineage & affected_lineage)

        rejections: list[str] = []
        if unknown_blockers or ambiguous_blocker_ids & claimed_blockers:
            rejections.append("unknown_blocker_reference")
        if unauthorized_blockers:
            rejections.append("unauthorized_blocker_claim")
        if unknown_causes:
            rejections.append("unknown_cause_reference")
        if unauthorized_causes:
            rejections.append("unauthorized_cause_claim")
        if unknown_event_ids:
            rejections.append("unknown_event_reference")
        if cross_run_event_ids:
            rejections.append("cross_run_event_reference")
        if unavailable_required_channels:
            rejections.append("unavailable_required_channel")
        if affected:
            rejections.append("affected_channel_health")
        if not resolved_blocker_ids and not distinguished_cause_ids:
            rejections.append("no_current_planning_value")

        priorities = [
            blockers_by_id[blocker_id].priority
            for blocker_id in resolved_blocker_ids
        ]
        if not priorities and distinguished_cause_ids:
            priorities.append("discrimination")
        priority: MeasurementPriority = min(
            priorities or ["discrimination"],
            key=measurement_priority_rank,
        )
        unique_rejections = tuple(dict.fromkeys(rejections))
        evaluations.append(
            MeasurementCandidateEvaluation(
                candidate_id=candidate.candidate_id,
                admissible=not unique_rejections,
                priority=priority,
                resolved_blocker_ids=resolved_blocker_ids,
                distinguished_cause_ids=distinguished_cause_ids,
                resolved_source_event_ids=tuple(resolved_source_event_ids),
                required_new_laps=candidate.required_laps,
                rejection_reasons=unique_rejections,
                priority_rank=measurement_priority_rank(priority),
                blocker_coverage=len(resolved_blocker_ids),
                cause_coverage=len(distinguished_cause_ids),
            )
        )

    selected_candidate_id: str | None = None
    if not duplicate_candidate_ids:
        admissible = [evaluation for evaluation in evaluations if evaluation.admissible]
        admissible.sort(
            key=lambda evaluation: (
                evaluation.priority_rank,
                -evaluation.blocker_coverage,
                -evaluation.cause_coverage,
                evaluation.required_new_laps,
                evaluation.candidate_id,
            )
        )
        if admissible:
            selected_candidate_id = admissible[0].candidate_id
    return MeasurementSelectionAudit(
        selected_candidate_id=selected_candidate_id,
        evaluations=tuple(evaluations),
        known_blocker_ids=tuple(sorted(blockers_by_id)),
        known_cause_ids=tuple(sorted(all_cause_ids)),
        known_event_ids=tuple(sorted(qualified_events)),
        duplicate_candidate_ids=duplicate_candidate_ids,
    )


def plan_best_next_measurement(
    causes: Sequence[RankedCause],
    *,
    controlled_decision: TestDirectorDecision | None = None,
    measurement_mission: MeasurementMission | None = None,
    measurement_candidates: Sequence[MeasurementCandidate] = (),
    known_measurement_blockers: Sequence[MeasurementBlocker] = (),
    known_available_channels: Sequence[str] = (),
    planning_prerequisite: MeasurementBlocker | None = None,
    graph: EvidenceGraph | None = None,
    current_run_id: str | None = None,
    affected_health_channels: Sequence[str] = (),
    channel_lineage_by_channel: Mapping[str, Sequence[str]] | None = None,
) -> InformationPlan:
    """Return one existing authorized test, mission, or cause discriminator."""
    trusted_ids = {
        citation.event_id
        for ranked in causes
        for citation in ranked.supporting_evidence
        if citation.event_id is not None and citation.valid_for_tuning
    }
    if (
        planning_prerequisite is not None
        and planning_prerequisite.priority
        in {"integrity", "data_qualification", "affected_channel_health"}
    ):
        return InformationPlan(
            kind="blocked",
            title=(
                "Restore current-run evidence integrity"
                if planning_prerequisite.priority == "integrity"
                else "Qualify the current-run evidence"
                if planning_prerequisite.priority == "data_qualification"
                else "Restore affected telemetry health"
            ),
            instruction=planning_prerequisite.reason,
            rationale=(
                "The current-run prerequisite has higher deterministic priority than a "
                "repetition, discriminator, or setup test."
            ),
            blocker_reasons=(planning_prerequisite.reason,),
            recovery_priority=planning_prerequisite.priority,
        )
    if controlled_decision is not None:
        if controlled_decision.ready and controlled_decision.card is not None:
            card = controlled_decision.card
            qualified_control_links = (
                _qualified_event_setup_links(graph) if graph is not None else set()
            )
            if (
                not _controlled_card_is_semantically_complete(card)
                or graph is None
                or not _card_matches_setup_authorization(graph, card)
                or any(
                event_id not in trusted_ids for event_id in card.evidence_event_ids
                )
                or any(
                (f"event:{event_id}", f"setup:{card.control_key}")
                not in qualified_control_links
                for event_id in card.evidence_event_ids
                )
            ):
                return InformationPlan(
                    kind="blocked",
                    title="Rebuild the controlled test",
                    instruction="Re-qualify the source laps and evidence events before setup action.",
                    rationale=(
                        "The existing card is no longer linked to current qualified evidence "
                        "for its exact setup control."
                    ),
                    blocker_reasons=(
                        "The controlled-test card references stale, unqualified, or cross-control evidence.",
                    ),
                )
            return InformationPlan(
                kind="controlled_test",
                title="Run one controlled A/B/A2 test",
                instruction=card.exact_change,
                rationale="The existing Test Director card is evidence-linked and legally sourced.",
                setup_authorized=True,
                controlled_test=card,
                source_event_ids=card.evidence_event_ids,
            )
        if controlled_decision.mission is not None:
            measurement_mission = controlled_decision.mission
    if measurement_mission is not None:
        if not _measurement_mission_is_semantically_complete(measurement_mission):
            return InformationPlan(
                kind="blocked",
                title="Rebuild the measurement mission",
                instruction="Create a provenance-complete measurement mission before collecting more data.",
                rationale="The persisted mission is incomplete and cannot safely direct a test.",
                blocker_reasons=(
                    "The measurement mission has missing or malformed procedure semantics.",
                ),
            )
        return InformationPlan(
            kind="measurement_mission",
            title="Run the existing measurement mission",
            instruction=measurement_mission.procedure[0],
            rationale="The controlled-test authority requires more evidence before setup action.",
            measurement_mission=measurement_mission,
            blocker_reasons=measurement_mission.blockers,
        )

    unresolved_cause_ids = {
        cause.cause_id for cause in causes if cause.status != "ruled_out"
    }
    selection_audit = evaluate_measurement_candidates(
        causes,
        measurement_candidates,
        known_blockers=known_measurement_blockers,
        known_available_channels=known_available_channels,
        graph=graph,
        current_run_id=current_run_id,
        affected_health_channels=affected_health_channels,
        channel_lineage_by_channel=channel_lineage_by_channel,
    )
    if selection_audit.duplicate_candidate_ids:
        return InformationPlan(
            kind="blocked",
            title="Rebuild the measurement candidate set",
            instruction="Resolve duplicate producer candidate identities before collecting data.",
            rationale="Ambiguous candidate identity makes deterministic selection unsafe.",
            blocker_reasons=(
                "Duplicate measurement candidate identities were rejected fail closed.",
            ),
            recovery_priority="integrity",
        )
    if selection_audit.selected_candidate_id is not None:
        candidate = next(
            item
            for item in measurement_candidates
            if item.candidate_id == selection_audit.selected_candidate_id
        )
        evaluation = next(
            item
            for item in selection_audit.evaluations
            if item.candidate_id == candidate.candidate_id
        )
        mission = MeasurementMission(
            purpose=candidate.purpose,
            procedure=candidate.procedure,
            required_laps_or_passes=evaluation.required_new_laps,
            controlled_variables=candidate.controlled_variables,
            target_phase=candidate.target_phase,
            acceptance_thresholds=candidate.acceptance_thresholds,
            stop_rule=candidate.stop_rule,
            blockers=(),
        )
        return InformationPlan(
            kind="measurement_mission",
            title=candidate.title,
            instruction=candidate.procedure[0],
            rationale=(
                f"This producer-owned mission resolves {evaluation.blocker_coverage} current "
                f"typed prerequisite{'s' if evaluation.blocker_coverage != 1 else ''} at "
                f"{evaluation.priority.replace('_', ' ')} priority, then uses required new laps "
                "and stable identity as deterministic tie-breaks."
            ),
            measurement_mission=mission,
            source_event_ids=evaluation.resolved_source_event_ids,
        )

    candidates = [
        cause
        for cause in causes
        if cause.status != "ruled_out"
        and cause.discriminator is not None
        and set(cause.discriminator.distinguishes_cause_ids) & unresolved_cause_ids
    ]
    candidates.sort(
        key=lambda cause: (
            -len(
                set(cause.discriminator.distinguishes_cause_ids)
                & unresolved_cause_ids
            ),
            cause.ordinal_rank,
            cause.discriminator.discriminator_id,
        )
    )
    affected_measurement_rejected = any(
        "affected_channel_health" in evaluation.rejection_reasons
        for evaluation in selection_audit.evaluations
    )

    def discriminator_touches_affected_channel(cause: RankedCause) -> bool:
        discriminator = cause.discriminator
        if (
            discriminator is None
            or not affected_health_channels
            or graph is None
        ):
            return False
        affected_lineage: set[str] = set()
        for channel in affected_health_channels:
            affected_lineage.update(
                _measurement_channel_lineage(channel, channel_lineage_by_channel)
            )
        for event_id in discriminator.source_event_ids:
            event_node = next(
                (
                    node
                    for node in graph.nodes
                    if node.kind is EvidenceNodeKind.EVENT
                    and node.entity_id == event_id
                    and node.qualified
                    and node.citation is not None
                    and node.citation.valid_for_tuning
                    and (
                        current_run_id is None
                        or node.citation.run_id == current_run_id
                    )
                ),
                None,
            )
            if event_node is None or event_node.citation is None:
                continue
            event_lineage: set[str] = set()
            for channel in event_node.citation.channels:
                event_lineage.update(
                    _measurement_channel_lineage(channel, channel_lineage_by_channel)
                )
            if event_lineage & affected_lineage:
                return True
        return False

    unaffected_candidates: list[RankedCause] = []
    for cause in candidates:
        if discriminator_touches_affected_channel(cause):
            affected_measurement_rejected = True
        else:
            unaffected_candidates.append(cause)
    if unaffected_candidates:
        cause = unaffected_candidates[0]
        discriminator = cause.discriminator
        assert discriminator is not None
        separated_count = len(
            set(discriminator.distinguishes_cause_ids) & unresolved_cause_ids
        )
        rationale = (
            "This single measurement separates multiple producer-declared unresolved cause buckets "
            "in the current ordinal ranking."
            if separated_count > 1
            else "This single measurement tests the highest-ranked producer-declared unresolved cause."
        )
        return InformationPlan(
            kind="discriminator",
            title=discriminator.title,
            instruction=discriminator.instruction,
            rationale=rationale,
            discriminator=discriminator,
            source_event_ids=tuple(
                event_id for event_id in discriminator.source_event_ids if event_id in trusted_ids
            ),
        )
    if affected_measurement_rejected:
        return InformationPlan(
            kind="blocked",
            title="Restore affected telemetry health",
            instruction=(
                "Complete the typed telemetry-health recovery before repeating this measurement."
            ),
            rationale=(
                "The next available measurement depends on a channel lineage with a current "
                "recording-health warning."
            ),
            blocker_reasons=(
                "Affected telemetry-channel health must be restored before this measurement.",
            ),
            recovery_priority="affected_channel_health",
        )
    return InformationPlan(
        kind="blocked",
        title="No safe next test is available",
        instruction="Collect eligible telemetry before changing the setup.",
        rationale="No existing authorized test, measurement mission, or defined discriminator exists.",
        blocker_reasons=(
            "A producer-owned measurement mission or cause discriminator is required.",
        ),
    )


def summarize_response_memory(
    *,
    response_context: SetupResponseContext | None,
    response_graph: Mapping[str, Any],
    control_key: str,
    direction_sign: int,
    target_zone_start_pct: float,
    target_zone_end_pct: float,
    surrounding_setup_fingerprint: str,
    proposed_delta: float | None = None,
) -> ResponseMemorySummary:
    """Summarize only qualified, exact-context controlled response history."""
    if (
        isinstance(direction_sign, bool)
        or not isinstance(direction_sign, int)
        or direction_sign not in {-1, 1}
    ):
        raise ValueError("direction_sign must be -1 or 1")
    if control_key not in SETUP_CONTROL_SPECS:
        raise ValueError("control_key must identify a canonical setup control")
    direction = direction_sign
    requested_start = _finite_number(target_zone_start_pct)
    requested_end = _finite_number(target_zone_end_pct)
    if (
        requested_start is None
        or requested_end is None
        or not 0.0 <= requested_start < requested_end <= 100.0
    ):
        raise ValueError("target zone must be a finite, ordered physical-position window")
    if not surrounding_setup_fingerprint.strip():
        raise ValueError("surrounding_setup_fingerprint is required")
    if response_context is None or not response_context.is_complete:
        return ResponseMemorySummary(
            context_key=None,
            status="incomplete_context",
            control_key=control_key,
            direction_sign=direction,
            qualified_observation_count=0,
            mismatches=("The current response-memory context is incomplete.",),
            blocker_reasons=("Complete exact driver, car, track, build, and operating context.",),
        )
    context_key = response_context.key
    graph_context_key = response_graph.get("context_key")
    if graph_context_key != context_key:
        return ResponseMemorySummary(
            context_key=context_key,
            status="context_mismatch",
            control_key=control_key,
            direction_sign=direction,
            qualified_observation_count=0,
            mismatches=(
                f"Response graph context {graph_context_key or 'missing'} does not match "
                f"current context {context_key}.",
            ),
            blocker_reasons=("Do not transfer controlled effects across context keys.",),
        )

    raw_edges = response_graph.get("edges", ())
    if not isinstance(raw_edges, Sequence) or isinstance(raw_edges, (str, bytes)):
        return ResponseMemorySummary(
            context_key=context_key,
            status="no_qualified_history",
            control_key=control_key,
            direction_sign=direction,
            qualified_observation_count=0,
            matching_context=(f"Exact context key {context_key}",),
            blocker_reasons=("The response graph edge collection is malformed.",),
        )

    qualified: list[dict[str, Any]] = []
    expected_context = asdict(response_context)
    for raw_edge in raw_edges:
        if not isinstance(raw_edge, Mapping):
            continue
        if raw_edge.get("setup_key") != control_key:
            continue
        raw_direction = raw_edge.get("direction_sign")
        if (
            isinstance(raw_direction, bool)
            or not isinstance(raw_direction, int)
            or raw_direction != direction
        ):
            continue
        if raw_edge.get("surrounding_setup_fingerprint") != surrounding_setup_fingerprint:
            continue
        edge_context = raw_edge.get("response_context")
        if not isinstance(edge_context, Mapping) or dict(edge_context) != expected_context:
            continue
        zone_start = _finite_number(raw_edge.get("target_zone_start_pct"))
        zone_end = _finite_number(raw_edge.get("target_zone_end_pct"))
        if (
            zone_start is None
            or zone_end is None
            or abs(zone_start - requested_start) > 1e-6
            or abs(zone_end - requested_end) > 1e-6
        ):
            continue
        evidence = raw_edge.get("evidence")
        if not isinstance(evidence, Mapping):
            continue
        source_channels = evidence.get("source_channels")
        event_ids = evidence.get("evidence_event_ids")
        source_runs = evidence.get("source_run_ids")
        if (
            raw_edge.get("setup_passed_tech") is not True
            or evidence.get("evidence_state") != EvidenceState.CONTROLLED_TEST_EFFECT.value
            or not isinstance(source_channels, list)
            or not source_channels
            or any(
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                or value not in _PUBLIC_EVIDENCE_CHANNELS
                for value in source_channels
            )
            or not isinstance(event_ids, list)
            or not event_ids
            or any(
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                for value in event_ids
            )
            or len(set(event_ids)) != len(event_ids)
            or not isinstance(source_runs, list)
            or len(source_runs) != 3
            or any(
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
                for value in source_runs
            )
            or len(set(source_runs)) != 3
            or raw_edge.get("baseline_run_id") != source_runs[0]
            or raw_edge.get("test_run_id") != source_runs[1]
        ):
            continue
        observation_id = raw_edge.get("observation_id")
        numeric_delta = _finite_number(raw_edge.get("numeric_delta"))
        effect = _finite_number(raw_edge.get("median_lap_delta_s"))
        baseline = _finite_number(raw_edge.get("baseline_value"))
        test = _finite_number(raw_edge.get("test_value"))
        confidence = _finite_number(raw_edge.get("confidence_score"))
        noise = _finite_number(raw_edge.get("pace_noise_band_s"))
        verdict = raw_edge.get("verdict")
        countereffects = evidence.get("countereffects")
        countereffect_evidence = bool(
            isinstance(countereffects, Mapping)
            and any(
                isinstance(countereffects.get(key), Sequence)
                and not isinstance(countereffects.get(key), (str, bytes))
                and any(
                    isinstance(item, str) and item.strip()
                    for item in countereffects.get(key, ())
                )
                for key in ("warnings", "do_not_change")
            )
        )
        change_is_guarded = False
        if baseline is not None and test is not None:
            try:
                assessment = assess_setup_change(control_key, baseline, test)
                change_is_guarded = bool(
                    assessment.label == "small"
                    and setup_target_increment_blocker(control_key, baseline, test) is None
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                change_is_guarded = False
        if (
            not isinstance(observation_id, str)
            or not observation_id.strip()
            or observation_id != observation_id.strip()
            or numeric_delta is None
            or effect is None
            or baseline is None
            or test is None
            or confidence is None
            or confidence < 0.55
            or noise is None
            or noise < 0.0
            or abs(effect) <= noise
            or numeric_delta * direction <= 0.0
            or not math.isclose(test - baseline, numeric_delta, abs_tol=1e-9)
            or not change_is_guarded
            or verdict not in {"keep_direction", "undo"}
            or (verdict == "keep_direction" and effect >= -noise)
            or (verdict == "undo" and effect <= noise and not countereffect_evidence)
        ):
            continue
        qualified.append(
            {
                "observation_id": observation_id,
                "numeric_delta": numeric_delta,
                "effect": effect,
                "baseline": baseline,
                "test": test,
                "verdict": str(verdict),
                "source_runs": tuple(str(value) for value in source_runs),
                "event_ids": tuple(str(value) for value in event_ids),
            }
        )

    identity_conflicts: list[str] = []
    by_observation_id: dict[str, list[dict[str, Any]]] = {}
    for row in qualified:
        by_observation_id.setdefault(row["observation_id"], []).append(row)
    deduped: list[dict[str, Any]] = []
    for observation_id in sorted(by_observation_id):
        rows = by_observation_id[observation_id]
        if any(row != rows[0] for row in rows[1:]):
            identity_conflicts.append(
                f"Observation identity {observation_id} has conflicting controlled effects."
            )
        else:
            deduped.append(rows[0])
    by_source_triplet: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in deduped:
        by_source_triplet.setdefault(tuple(sorted(row["source_runs"])), []).append(row)
    for source_runs, rows in by_source_triplet.items():
        if len(rows) > 1:
            identity_conflicts.append(
                "One A/B/A2 source-run triplet has multiple observation identities: "
                + ", ".join(sorted(row["observation_id"] for row in rows))
                + f" ({', '.join(source_runs)})."
            )
    source_run_usage = Counter(
        run_id for row in deduped for run_id in row["source_runs"]
    )
    overlapping_runs = sorted(
        run_id for run_id, count in source_run_usage.items() if count > 1
    )
    if overlapping_runs:
        identity_conflicts.append(
            "Controlled observations reuse source runs and are not independent: "
            + ", ".join(overlapping_runs)
            + "."
        )
    event_usage = Counter(
        event_id for row in deduped for event_id in row["event_ids"]
    )
    overlapping_events = sorted(
        event_id for event_id, count in event_usage.items() if count > 1
    )
    if overlapping_events:
        identity_conflicts.append(
            "Controlled observations reuse evidence events and are not independent: "
            + ", ".join(overlapping_events)
            + "."
        )
    if identity_conflicts:
        observation_ids = tuple(
            sorted({row["observation_id"] for row in qualified})
        )
        source_run_ids = tuple(
            sorted({run_id for row in qualified for run_id in row["source_runs"]})
        )
        event_ids = tuple(
            sorted({event_id for row in qualified for event_id in row["event_ids"]})
        )
        values = [
            value for row in qualified for value in (row["baseline"], row["test"])
        ]
        return ResponseMemorySummary(
            context_key=context_key,
            status="contradictory_history",
            control_key=control_key,
            direction_sign=direction,
            qualified_observation_count=len(qualified),
            verdicts=tuple(sorted({row["verdict"] for row in qualified})),
            observed_setup_envelope=(min(values), max(values)) if values else None,
            source_observation_ids=observation_ids,
            source_run_ids=source_run_ids,
            evidence_event_ids=event_ids,
            matching_context=(
                f"Exact context key {context_key}",
                f"Exact target window {requested_start:g}-{requested_end:g}%",
                f"Exact surrounding setup {surrounding_setup_fingerprint}",
            ),
            blocker_reasons=_unique_text(identity_conflicts),
        )
    qualified = deduped

    if not qualified:
        return ResponseMemorySummary(
            context_key=context_key,
            status="no_qualified_history",
            control_key=control_key,
            direction_sign=direction,
            qualified_observation_count=0,
            matching_context=(f"Exact context key {context_key}",),
            blocker_reasons=(
                "No provenance-complete, tech-passing controlled history matches this exact scope.",
            ),
        )
    observation_ids = tuple(dict.fromkeys(row["observation_id"] for row in qualified))
    source_run_ids = tuple(
        dict.fromkeys(run_id for row in qualified for run_id in row["source_runs"])
    )
    event_ids = tuple(
        dict.fromkeys(event_id for row in qualified for event_id in row["event_ids"])
    )
    verdicts = tuple(sorted({row["verdict"] for row in qualified}))
    observed_values = [value for row in qualified for value in (row["baseline"], row["test"])]
    input_deltas = [row["numeric_delta"] for row in qualified]
    effects = [row["effect"] for row in qualified]
    contradictory = len(verdicts) > 1 or (min(effects) < 0.0 < max(effects))
    if contradictory:
        return ResponseMemorySummary(
            context_key=context_key,
            status="contradictory_history",
            control_key=control_key,
            direction_sign=direction,
            qualified_observation_count=len(qualified),
            verdicts=verdicts,
            observed_setup_envelope=(min(observed_values), max(observed_values)),
            source_observation_ids=observation_ids,
            source_run_ids=source_run_ids,
            evidence_event_ids=event_ids,
            matching_context=(
                f"Exact context key {context_key}",
                f"Exact target window {requested_start:g}-{requested_end:g}%",
                f"Exact surrounding setup {surrounding_setup_fingerprint}",
            ),
            blocker_reasons=(
                "Exact-context controlled history contradicts itself; no response range is authorized.",
            ),
        )

    counterfactual = None
    counterfactual_blockers: list[str] = []
    proposed = _finite_number(proposed_delta)
    if proposed_delta is not None and proposed is None:
        counterfactual_blockers.append("The proposed input delta is not finite.")
    elif proposed is not None:
        low_delta, high_delta = min(input_deltas), max(input_deltas)
        if proposed < low_delta - 1e-12 or proposed > high_delta + 1e-12:
            counterfactual_blockers.append(
                "The proposed input is outside the observed exact-context controlled range."
            )
        elif len(observation_ids) < 2:
            counterfactual_blockers.append(
                "At least two qualified controlled observations are required for a range."
            )
        else:
            counterfactual = GuardedCounterfactualRange(
                metric="target_phase_time_delta",
                minimum=min(effects),
                maximum=max(effects),
                unit="s",
                observed_delta_minimum=low_delta,
                observed_delta_maximum=high_delta,
                source_observation_ids=observation_ids,
            )
    return ResponseMemorySummary(
        context_key=context_key,
        status="exact_context_match",
        control_key=control_key,
        direction_sign=direction,
        qualified_observation_count=len(qualified),
        verdicts=verdicts,
        observed_setup_envelope=(min(observed_values), max(observed_values)),
        counterfactual_range=counterfactual,
        source_observation_ids=observation_ids,
        source_run_ids=source_run_ids,
        evidence_event_ids=event_ids,
        matching_context=(
            f"Exact context key {context_key}",
            f"Exact target window {requested_start:g}-{requested_end:g}%",
            f"Exact surrounding setup {surrounding_setup_fingerprint}",
        ),
        blocker_reasons=_unique_text(counterfactual_blockers),
    )


def summarize_stored_response_memory(
    *,
    response_context: SetupResponseContext | None,
    control_key: str,
    direction_sign: int,
    target_zone_start_pct: float,
    target_zone_end_pct: float,
    surrounding_setup_fingerprint: str,
    proposed_delta: float | None = None,
    db_path: str | Path | None = None,
) -> ResponseMemorySummary:
    """Convenience adapter over the existing exact-context response store."""
    graph = get_setup_response_graph(response_context, db_path=db_path)
    return summarize_response_memory(
        response_context=response_context,
        response_graph=graph,
        control_key=control_key,
        direction_sign=direction_sign,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
        surrounding_setup_fingerprint=surrounding_setup_fingerprint,
        proposed_delta=proposed_delta,
    )


def assess_data_quality(
    *,
    laps: Sequence[LapSummary],
    events: Sequence[TelemetryEvent],
    capability: CapabilityAssessment | None,
) -> DataQualityAssessment:
    """Assess current evidence using canonical lap and event qualification."""
    invalid_lap_identities = [
        lap
        for lap in laps
        if not lap.run_id.strip()
        or lap.run_id != lap.run_id.strip()
        or not lap.lap_id.strip()
        or lap.lap_id != lap.lap_id.strip()
        or lap.lap_number < 0
    ]
    identity_valid_laps = [lap for lap in laps if lap not in invalid_lap_identities]
    lap_key_counts = Counter((lap.run_id, lap.lap_number) for lap in identity_valid_laps)
    laps_by_key = {
        (lap.run_id, lap.lap_number): lap
        for lap in identity_valid_laps
        if lap_key_counts[(lap.run_id, lap.lap_number)] == 1
    }
    eligible = [lap for lap in laps_by_key.values() if lap_is_eligible(lap)]
    qualified_events: list[TelemetryEvent] = []
    invalid_events: list[tuple[TelemetryEvent, tuple[str, ...]]] = []
    invalid_event_identities = [
        event
        for event in events
        if not event.event_id.strip()
        or event.event_id != event.event_id.strip()
        or not event.run_id.strip()
        or event.run_id != event.run_id.strip()
    ]
    event_id_counts = Counter(event.event_id for event in events)
    for event in events:
        if event_id_counts[event.event_id] != 1:
            invalid_events.append((event, ("Duplicate telemetry event identity.",)))
            continue
        qualified, reasons = _event_qualification(event, laps_by_key)
        if qualified:
            qualified_events.append(event)
        else:
            invalid_events.append((event, reasons))

    issues: list[str] = []
    recovery: list[str] = []
    if invalid_lap_identities:
        issues.append("A lap has an invalid run, lap, or lap-number identity.")
        recovery.append("Rebuild lap summaries with stable non-empty run and lap identities.")
    if invalid_event_identities:
        issues.append("A telemetry event has an invalid event or run identity.")
        recovery.append("Re-run event detection with stable non-empty event and run identities.")
    duplicate_lap_keys = [key for key, count in lap_key_counts.items() if count > 1]
    duplicate_event_ids = [key for key, count in event_id_counts.items() if count > 1]
    if duplicate_lap_keys:
        issues.append("Duplicate run/lap identities make lap evidence ambiguous.")
        recovery.append("Rebuild the run's lap summaries with one canonical row per run and lap.")
    if duplicate_event_ids:
        issues.append("Duplicate event identities make evidence provenance ambiguous.")
        recovery.append("Re-run event detection with unique stable event identities.")
    if not laps:
        issues.append("No lap summaries are available in the current scope.")
        recovery.append("Import a run containing complete flying laps, then re-run qualification.")
    elif not eligible:
        issues.append("No lap passed the canonical setup-evidence gate.")
        recovery.append(
            "Record complete flying laps without pit, reset, caution, wreck, cooldown, or invalid-speed contamination."
        )
    if not qualified_events:
        issues.append("No telemetry event is trusted for a setup conclusion.")
        recovery.append(
            "Record a provenance-complete target-phase event on an eligible lap with healthy source channels."
        )
    if capability is None or capability.status == "unknown":
        issues.append("Telemetry capability health has not been assessed.")
        recovery.append("Load the run capability manifest and verify required channel health.")
    else:
        issues.extend(capability.issues)
        recovery.extend(capability.recovery_steps)
        if capability.status == "limited" and not capability.issues:
            issues.append("Telemetry capability health is limited for the requested analysis.")
            recovery.append("Record the analysis-required channels and verify they are healthy and varying.")
        elif capability.status == "blocked" and not capability.issues:
            issues.append("Telemetry capabilities block the requested analysis.")
            recovery.append("Resolve the capability blockers before drawing a setup conclusion.")

    if (
        not eligible
        or invalid_lap_identities
        or invalid_event_identities
        or duplicate_lap_keys
        or duplicate_event_ids
        or capability is not None
        and capability.status == "blocked"
    ):
        status = "blocked"
    elif issues:
        status = "limited"
    else:
        status = "ready"
    citations = tuple(
        _event_citation(event, qualified=False)
        for event, _ in invalid_events[:3]
        if event.event_id.strip()
        and event.event_id == event.event_id.strip()
        and event.run_id.strip()
        and event.run_id == event.run_id.strip()
    )
    return DataQualityAssessment(
        status=status,
        eligible_lap_count=len(eligible),
        total_lap_count=len(laps),
        trusted_event_count=len(qualified_events),
        scope_run_ids=tuple(
            sorted(
                {
                    *(lap.run_id for lap in identity_valid_laps),
                    *(
                        event.run_id
                        for event in events
                        if event.run_id.strip() and event.run_id == event.run_id.strip()
                    ),
                }
            )
        ),
        eligible_lap_ids=tuple(sorted(lap.lap_id for lap in eligible)),
        trusted_event_ids=tuple(sorted(event.event_id for event in qualified_events)),
        issues=_unique_text(issues),
        recovery_steps=_unique_text(recovery),
        citations=citations,
    )


def _build_mind_change_criteria(
    *,
    run_id: str,
    session_id: str | None,
    causes: Sequence[PublicCompetingCause],
    ranked_causes: Sequence[RankedCause],
    measurement: InformationPlan,
    current_event_ids: set[str],
) -> tuple[MindChangeCriterion, ...]:
    unresolved = tuple(cause for cause in causes if cause.state != "ruled_out")
    if not unresolved:
        return ()
    ranked_by_id = {cause.cause_id: cause for cause in ranked_causes}

    if measurement.kind == "controlled_test" and measurement.controlled_test is not None:
        card = measurement.controlled_test
        phase = _typed_phase(card.target_phase)
        if phase is None:
            return ()
        source_ids = tuple(
            event_id
            for event_id in dict.fromkeys(card.evidence_event_ids)
            if event_id in current_event_ids
        )
        candidate_ids = {
            cause_id
            for cause_id, ranked in ranked_by_id.items()
            if set(source_ids).issubset(
                {
                    citation.event_id
                    for citation in ranked.supporting_evidence
                    if citation.event_id is not None
                }
            )
        }
        candidates = sorted(
            (
                cause
                for cause in unresolved
                if cause.cause_id in candidate_ids
            ),
            key=lambda cause: (
                0 if cause.cause_id.startswith("workflow:") else 1,
                cause.rank,
                cause.cause_id,
            ),
        )
        if not candidates:
            return ()
        cause = candidates[0]
        return (
            MindChangeCriterion(
                criterion_id=f"mind-change:{run_id}:{cause.cause_id}:aba2",
                cause_id=cause.cause_id,
                current_state=cause.state,
                evidence_kind="controlled_test",
                run_id=run_id,
                session_id=session_id,
                metric="target_phase_time_s",
                phase=phase,
                control_key=(
                    card.control_key if card.control_key in SETUP_CONTROL_SPECS else None
                ),
                threshold_source=(
                    "Frozen empirical A/A2 noise plus the score_test_execution target-direction "
                    "and protocol-validity gates; countereffects govern the control policy separately."
                ),
                acceptance_conditions=(
                    "Only the declared setup control changes; observed B matches the frozen planned target and restored A2 exactly matches A.",
                    "Context match, driver match, simulator integrity, and target-window alignment each meet or exceed 0.8.",
                    "At least three qualified within-baseline effects establish noise, both phase effects are present, and the lap-level distribution state agrees with the aggregate A/B/A2 target effect.",
                    "Every matched B-vs-A and B-vs-restored-A2 target-phase effect is faster beyond the frozen empirical noise floor.",
                    "The lap-level target-effect distribution is faster and its consistency flag is true.",
                    "The frozen controlled-test quality score is at least 80.",
                ),
                falsification_conditions=(
                    "Every matched B-vs-A and B-vs-restored-A2 target-phase effect is slower beyond the frozen empirical noise floor.",
                    "The lap-level target-effect distribution is slower and its consistency flag is true.",
                ),
                minimum_independent_evidence_units=9,
                minimum_evidence=(
                    "Three eligible flying laps in A, three in B, and three in restored A2, "
                    "with every persisted protocol-validity input complete."
                ),
                requires_aba2=True,
                minimum_laps_per_stage=3,
                countereffects=_unique_text(
                    [
                        *card.countereffects,
                        "The control-specific telemetry guardrail passes.",
                        "A countereffect or guardrail failure produces Undo for the unchanged control policy but does not by itself falsify the target-direction cause.",
                    ]
                ),
                next_state_if_accepted="leading",
                next_state_if_falsified="ruled_out",
                next_state_if_inconclusive="unresolved",
                source_event_ids=source_ids,
            ),
        )

    if measurement.kind == "discriminator" and measurement.discriminator is not None:
        discriminator = measurement.discriminator
        phase = _typed_phase(discriminator.target_phase)
        if phase is None:
            return ()
        cause_ids = set(discriminator.distinguishes_cause_ids)
        candidates = tuple(cause for cause in unresolved if cause.cause_id in cause_ids)
        return tuple(
            MindChangeCriterion(
                criterion_id=f"mind-change:{run_id}:{cause.cause_id}:discriminator",
                cause_id=cause.cause_id,
                current_state=cause.state,
                evidence_kind="discriminator",
                run_id=run_id,
                session_id=session_id,
                metric="producer_declared_signal",
                phase=phase,
                threshold_source="Producer-owned discriminator acceptance contract.",
                acceptance_conditions=tuple(discriminator.acceptance_thresholds),
                falsification_conditions=(
                    "The producer-owned collection contract is incomplete; no typed causal opposite was declared.",
                ),
                minimum_independent_evidence_units=3,
                minimum_evidence="Three independent eligible laps on the unchanged setup.",
                next_state_if_accepted=cause.state,
                next_state_if_falsified="unresolved",
                next_state_if_inconclusive="unresolved",
                source_event_ids=tuple(
                    event_id
                    for event_id in dict.fromkeys(discriminator.source_event_ids)
                    if event_id in current_event_ids
                ),
            )
            for cause in candidates
        )

    if measurement.kind == "measurement_mission" and measurement.measurement_mission is not None:
        mission = measurement.measurement_mission
        phase = _typed_phase(mission.target_phase)
        if phase is None or len(unresolved) != 1:
            return ()
        cause = unresolved[0]
        minimum_units = max(
            _MIN_REPEATED_CAUSE_EVIDENCE_UNITS,
            mission.required_laps_or_passes,
        )
        return (
            MindChangeCriterion(
                criterion_id=f"mind-change:{run_id}:{cause.cause_id}:mission",
                cause_id=cause.cause_id,
                current_state=cause.state,
                evidence_kind="measurement_mission",
                run_id=run_id,
                session_id=session_id,
                metric="producer_declared_signal",
                phase=phase,
                threshold_source="Producer-owned measurement-mission acceptance contract.",
                acceptance_conditions=tuple(mission.acceptance_thresholds),
                falsification_conditions=(
                    "The producer-owned collection contract is incomplete; no typed causal opposite was declared.",
                ),
                minimum_independent_evidence_units=minimum_units,
                minimum_evidence=(
                    f"At least {minimum_units} independent eligible laps or passes on the unchanged setup."
                ),
                next_state_if_accepted=cause.state,
                next_state_if_falsified="unresolved",
                next_state_if_inconclusive="unresolved",
                source_event_ids=tuple(
                    event_id
                    for event_id in dict.fromkeys(measurement.source_event_ids)
                    if event_id in current_event_ids
                ),
            ),
        )
    return ()


def build_internal_intelligence_report(
    *,
    run_id: str,
    session_id: str | None = None,
    response_context_key: str | None = None,
    issue: str,
    graph: EvidenceGraph,
    ranked_causes: Sequence[RankedCause],
    best_measurement: InformationPlan,
    data_quality: DataQualityAssessment,
    lap_context: LapEngineeringContextReport | None = None,
    mechanism_episodes: Sequence[MechanismEpisode] = (),
    mechanism_episode_blocker_reasons: Sequence[str] = (),
    context_matches: Sequence[ResponseMemorySummary] = (),
    calibration: CalibrationSummary | None = None,
    narrative: Sequence[str] = (),
    suggested_questions: Sequence[str] = (),
) -> InternalIntelligenceReport:
    """Assemble a UI-ready internal report without creating new authority."""
    graph = _graph_with_ranked_causes(graph, ranked_causes)
    validated_context_matches, context_match_blockers = _revalidate_response_summaries(
        context_matches,
        current_context_key=response_context_key,
    )
    qualified_report_event_ids = {
        node.entity_id
        for node in graph.nodes
        if node.kind is EvidenceNodeKind.EVENT
        and node.qualified
        and node.citation is not None
        and node.citation.valid_for_tuning
        and node.citation.run_id == run_id
    }
    data_quality_matches_report = bool(
        data_quality.scope_run_ids == (run_id,)
        and set(data_quality.trusted_event_ids).issubset(qualified_report_event_ids)
    )
    if not data_quality_matches_report:
        data_quality = DataQualityAssessment(
            **{
                **data_quality.model_dump(),
                "status": "blocked",
                "eligible_lap_count": 0,
                "trusted_event_count": 0,
                "scope_run_ids": (run_id,),
                "eligible_lap_ids": (),
                "trusted_event_ids": (),
                "issues": _unique_text(
                    [
                        *data_quality.issues,
                        "Data-quality evidence does not match the requested report run.",
                    ]
                ),
                "recovery_steps": _unique_text(
                    [
                        *data_quality.recovery_steps,
                        "Recompute canonical lap, event, and capability quality for this run.",
                    ]
                ),
            }
        )
    cause_id_counts = Counter(cause.cause_id for cause in ranked_causes)
    duplicate_cause_ids = sorted(
        cause_id for cause_id, count in cause_id_counts.items() if count > 1
    )
    ranking_input_blockers: list[str] = []
    if duplicate_cause_ids:
        ranking_input_blockers.append(
            "Duplicate ranked cause identities were withheld from the report."
        )
    ranked_causes = tuple(
        cause for cause in ranked_causes if cause_id_counts[cause.cause_id] == 1
    )
    normalized_ranked_causes: list[RankedCause] = []
    for cause in ranked_causes:
        supporting_ids = [
            citation.event_id or citation.citation_id
            for citation in cause.supporting_evidence
        ]
        contradicting_ids = [
            citation.event_id or citation.citation_id
            for citation in cause.contradicting_evidence
        ]
        if (
            len(supporting_ids) != len(set(supporting_ids))
            or len(contradicting_ids) != len(set(contradicting_ids))
        ):
            ranking_input_blockers.append(
                "A ranked cause contains duplicate evidence identities."
            )
        overlap_ids = sorted(set(supporting_ids) & set(contradicting_ids))
        if overlap_ids:
            ranking_input_blockers.append(
                "A ranked cause uses the same evidence as support and contradiction."
            )
        supporting_by_id = {
            citation.event_id or citation.citation_id: citation
            for citation in cause.supporting_evidence
            if (citation.event_id or citation.citation_id) not in overlap_ids
            and citation.run_id == run_id
        }
        contradicting_by_id = {
            citation.event_id or citation.citation_id: citation
            for citation in cause.contradicting_evidence
            if (citation.event_id or citation.citation_id) not in overlap_ids
            and citation.run_id == run_id
        }
        cross_run_withheld = bool(
            any(citation.run_id != run_id for citation in cause.supporting_evidence)
            or any(citation.run_id != run_id for citation in cause.contradicting_evidence)
        )
        if cross_run_withheld:
            ranking_input_blockers.append(
                "Cross-run ranked evidence was withheld from this exact-run report."
            )
        support_clusters = tuple(
            cluster
            for cluster in cause.supporting_clusters
            if set(cluster.citation_ids).issubset(
                {citation.citation_id for citation in supporting_by_id.values()}
            )
        )
        against_clusters = tuple(
            cluster
            for cluster in cause.contradicting_clusters
            if set(cluster.citation_ids).issubset(
                {citation.citation_id for citation in contradicting_by_id.values()}
            )
        )
        normalized_ranked_causes.append(RankedCause(
            **{
                **cause.model_dump(),
                "status": (
                    "unresolved"
                    if overlap_ids
                    or len(supporting_ids) != len(set(supporting_ids))
                    or len(contradicting_ids) != len(set(contradicting_ids))
                    else "possible"
                    if cross_run_withheld and cause.status == "likely"
                    else cause.status
                ),
                "supporting_evidence": tuple(supporting_by_id.values()),
                "contradicting_evidence": tuple(contradicting_by_id.values()),
                "supporting_clusters": support_clusters,
                "contradicting_clusters": against_clusters,
                "supporting_evidence_unit_count": (
                    len(support_clusters)
                    if support_clusters
                    else len({
                        (citation.run_id, citation.lap_number)
                        for citation in supporting_by_id.values()
                    })
                ),
                "contradicting_evidence_unit_count": (
                    len(against_clusters)
                    if against_clusters
                    else len({
                        (citation.run_id, citation.lap_number)
                        for citation in contradicting_by_id.values()
                    })
                ),
                "missing_evidence": _unique_text(cause.missing_evidence),
                "blocker_reasons": _unique_text(cause.blocker_reasons),
            }
        ))
    ranked_causes = tuple(
        cause.model_copy(update={
            "status": "possible" if cause.status == "likely" else cause.status,
            "ordinal_rank": 1,
        })
        for cause in normalized_ranked_causes
    ) if ranking_input_blockers else tuple(normalized_ranked_causes)
    retained_node_ids = {
        node.node_id
        for node in graph.nodes
        if node.citation is None or node.citation.run_id == run_id
    }
    scoped_nodes_by_id = {
        node.node_id: node for node in graph.nodes if node.node_id in retained_node_ids
    }
    retained_edges = tuple(
        edge
        for edge in graph.edges
        if edge.source_node_id in retained_node_ids
        and edge.target_node_id in retained_node_ids
    )
    for node_id, node in tuple(scoped_nodes_by_id.items()):
        if node.kind is not EvidenceNodeKind.SETUP or node.authorization_fingerprint is None:
            continue
        has_current_link = any(
            edge.qualified
            and edge.target_node_id == node_id
            and edge.kind is EvidenceEdgeKind.RELATES_TO_SETUP
            and scoped_nodes_by_id[edge.source_node_id].kind is EvidenceNodeKind.EVENT
            for edge in retained_edges
        )
        if not has_current_link:
            scoped_nodes_by_id[node_id] = node.model_copy(update={
                "qualified": False,
                "evidence_state": EvidenceState.BLOCKED_BY_CONTEXT,
                "blocker_reasons": ("No exact-run event supports this setup relation.",),
                "authorization_fingerprint": None,
            })
    retained_edges = tuple(
        edge.model_copy(update={
            "qualified": bool(
                edge.qualified
                and scoped_nodes_by_id[edge.source_node_id].qualified
                and scoped_nodes_by_id[edge.target_node_id].qualified
            )
        })
        for edge in retained_edges
    )
    graph = _graph_with_ranked_causes(
        EvidenceGraph(
            nodes=tuple(scoped_nodes_by_id.values()),
            edges=retained_edges,
            blocker_reasons=graph.blocker_reasons,
        ),
        ranked_causes,
    )
    effective_measurement = best_measurement
    if best_measurement.kind == "controlled_test":
        proposed_card = best_measurement.controlled_test
        qualified_current_events = qualified_report_event_ids
        qualified_control_links = _qualified_event_setup_links(graph)
        card_is_current = bool(
            not ranking_input_blockers
            and not best_measurement.blocker_reasons
            and not any(
                cause.controlled_conflict
                and any(
                    outcome.source_run_id == run_id
                    for outcome in cause.controlled_outcomes
                )
                for cause in ranked_causes
            )
            and proposed_card is not None
            and _controlled_card_is_semantically_complete(proposed_card)
            and _card_matches_setup_authorization(graph, proposed_card)
            and set(proposed_card.evidence_event_ids).issubset(
                data_quality.trusted_event_ids
            )
            and all(
                event_id in qualified_current_events
                and (
                    f"event:{event_id}",
                    f"setup:{proposed_card.control_key}",
                )
                in qualified_control_links
                for event_id in proposed_card.evidence_event_ids
            )
        )
        if data_quality.status != "ready" or not card_is_current:
            reasons = [
                "Current data quality must be ready before a setup target can be authorized."
            ]
            if not card_is_current:
                reasons.append(
                    "The controlled-test card is not linked to qualified current-run events."
                )
            reasons.extend(data_quality.issues)
            effective_measurement = InformationPlan(
                kind="blocked",
                title="Setup action withheld",
                instruction=(
                    data_quality.recovery_steps[0]
                    if data_quality.recovery_steps
                    else "Re-qualify the current run before changing the setup."
                ),
                rationale="The report revalidates evidence at read time and failed closed.",
                blocker_reasons=_unique_text(reasons),
            )
    criterion_measurement = effective_measurement
    if effective_measurement.kind == "controlled_test":
        effective_measurement = _public_authorized_plan(effective_measurement)
    else:
        effective_measurement = _public_non_action_plan(effective_measurement)

    if effective_measurement.kind == "controlled_test":
        card = effective_measurement.controlled_test
        assert card is not None
        action = IntelligenceAction(
            kind="controlled_test",
            title=effective_measurement.title,
            instruction=card.exact_change,
            setup_authorized=True,
            control_key=card.control_key,
            current_value=format_setup_value(card.control_key, card.current_value),
            proposed_value=str(card.proposed_value),
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
            source_event_ids=card.evidence_event_ids,
        )
        success_check = (
            "B must beat A and restored A2 beyond the empirical noise floor without a countereffect."
        )
    elif effective_measurement.kind == "measurement_mission":
        mission = effective_measurement.measurement_mission
        assert mission is not None
        action = IntelligenceAction(
            kind="measurement_mission",
            title=effective_measurement.title,
            instruction=effective_measurement.instruction,
            evidence_state=EvidenceState.BLOCKED_BY_CONTEXT,
            blocker_reasons=_unique_text(effective_measurement.blocker_reasons),
        )
        success_check = "; ".join(mission.acceptance_thresholds)
    elif effective_measurement.kind == "discriminator":
        discriminator = effective_measurement.discriminator
        assert discriminator is not None
        action = IntelligenceAction(
            kind="discriminator",
            title=effective_measurement.title,
            instruction=effective_measurement.instruction,
            evidence_state=EvidenceState.NEEDS_CONFIRMATION,
            source_event_ids=effective_measurement.source_event_ids,
        )
        success_check = "; ".join(discriminator.acceptance_thresholds)
    else:
        action = IntelligenceAction(
            kind="no_call",
            title=effective_measurement.title,
            instruction=effective_measurement.instruction,
            evidence_state=EvidenceState.UNAVAILABLE,
            blocker_reasons=effective_measurement.blocker_reasons,
        )
        success_check = "Collect the missing evidence before making a setup change."

    current_citations: dict[str, EvidenceCitation] = {}
    current_event_ids: set[str] = set()
    for node in graph.nodes:
        if (
            node.kind not in {EvidenceNodeKind.EVENT, EvidenceNodeKind.OBSERVATION}
            or not node.qualified
            or node.citation is None
            or node.citation.run_id != run_id
        ):
            continue
        public_citation = _public_evidence_citation(node.citation)
        evidence_id = public_citation.event_id or public_citation.citation_id
        current_citations[evidence_id] = public_citation
        if node.kind is EvidenceNodeKind.EVENT and public_citation.event_id is not None:
            current_event_ids.add(public_citation.event_id)

    public_causes: list[PublicCompetingCause] = []
    for cause in ranked_causes:
        evidence_for = tuple(
            current_citations[evidence_id]
            for citation in cause.supporting_evidence
            if (evidence_id := citation.event_id or citation.citation_id)
            in current_citations
        )
        evidence_against = tuple(
            current_citations[evidence_id]
            for citation in cause.contradicting_evidence
            if (evidence_id := citation.event_id or citation.citation_id)
            in current_citations
        )
        controlled_outcomes = tuple(
            outcome
            for outcome in cause.controlled_outcomes
            if outcome.source_run_id == run_id
        )
        state = {
            "likely": "leading",
            "possible": "possible",
            "ruled_out": "ruled_out",
            "unresolved": "unresolved",
        }[cause.status]
        evidence_state = (
            evidence_for[0].evidence_state
            if evidence_for
            else evidence_against[0].evidence_state
            if evidence_against
            else EvidenceState.CONTROLLED_TEST_EFFECT
            if any(
                outcome.diagnostic_validity == "mechanism_diagnostic"
                and outcome.outcome in {"supported", "contradicted"}
                for outcome in controlled_outcomes
            )
            else EvidenceState.BLOCKED_BY_CONTEXT
            if controlled_outcomes
            else EvidenceState.UNAVAILABLE
        )
        reason = cause.rank_basis
        if len(evidence_for) != len(cause.supporting_evidence) or len(
            evidence_against
        ) != len(cause.contradicting_evidence):
            reason += " Cross-run or stale citations were withheld from this exact-run view."
        if any(outcome.verdict == "undo" for outcome in controlled_outcomes):
            reason += " Undo rejects the exact control policy; it does not falsify the mechanism."
        public_causes.append(
            PublicCompetingCause(
                cause_id=cause.cause_id,
                label=f"Cause candidate {len(public_causes) + 1}",
                state=state,
                rank=cause.ordinal_rank,
                evidence_state=evidence_state,
                reason=reason,
                evidence_for=evidence_for,
                evidence_against=evidence_against,
                controlled_outcomes=controlled_outcomes,
                controlled_conflict=cause.controlled_conflict,
            )
        )

    mind_change_criteria = _build_mind_change_criteria(
        run_id=run_id,
        session_id=session_id,
        causes=public_causes,
        ranked_causes=ranked_causes,
        measurement=criterion_measurement,
        current_event_ids=current_event_ids,
    )

    blockers = _unique_text(
        [
            *effective_measurement.blocker_reasons,
            *ranking_input_blockers,
            *context_match_blockers,
            *(
                ("Canonical data-quality checks block setup conclusions.",)
                if data_quality.status == "blocked"
                else ()
            ),
        ]
    )
    status = (
        "blocked"
        if data_quality.status == "blocked"
        or effective_measurement.kind in {"blocked", "stop_testing"}
        else "ready"
        if effective_measurement.kind == "controlled_test"
        else "measure"
    )
    confidence_label = (
        "blocked"
        if status == "blocked"
        else "supported"
        if status == "ready" and any(cause.state == "leading" for cause in public_causes)
        else "provisional"
        if data_quality.status == "ready"
        else "limited"
    )
    questions = suggested_questions or (
        "Why this call?",
        "Where is the loss?",
        "What should I do next?",
        "What evidence supports this?",
        "What was ruled out?",
        "What worked here before?",
        "How reliable is this?",
        "What would change your mind?",
        "Is the data good?",
    )
    questions = tuple(
        question
        for question in questions
        if _QUERY_ALIASES.get(_normalize_query(question)) is not None
    ) or (
        "Why this call?",
        "Where is the loss?",
        "What should I do next?",
        "What evidence supports this?",
        "What was ruled out?",
        "What worked here before?",
        "How reliable is this?",
        "What would change your mind?",
        "Is the data good?",
    )
    report_graph = _public_evidence_graph(graph)
    public_issue = "Evidence review requires another measurement."
    public_narrative = (
        "Cause ordering is ordinal and evidence-scoped.",
        "No exact setup target is authorized by this report.",
    )
    if action.setup_authorized:
        assert effective_measurement.controlled_test is not None
        public_issue = (
            "Evidence-qualified controlled test for "
            f"{effective_measurement.controlled_test.control_label}."
        )
        public_narrative = (
            "One adjacent evidence-linked setup control is authorized for A/B/A2 testing.",
            "All other exact setup targets remain withheld.",
        )
    public_calibration = calibration or CalibrationSummary()
    public_calibration = public_calibration.model_copy(
        update={
            "note": "Prediction-direction counts do not authorize an exact setup target."
        }
    )
    public_data_quality = data_quality.model_copy(
        update={
            "issues": (
                ("One or more canonical evidence qualification checks failed.",)
                if data_quality.issues
                else ()
            ),
            "recovery_steps": (
                ("Re-import or re-measure complete eligible telemetry before setup action.",)
                if data_quality.recovery_steps
                else ()
            ),
            "citations": tuple(
                _public_evidence_citation(citation) for citation in data_quality.citations
            ),
        }
    )
    snapshot_causes = tuple(
        RankedCause(
            **{
                **cause.model_dump(),
                "label": f"Cause candidate {index}",
                "hypothesis": "A producer-owned engineering cause is under evidence review.",
                "rank_basis": (
                    "Ordinal evidence ordering uses run/window independence clusters, signed "
                    "contradictions, and explicitly diagnostic controlled outcomes. This is "
                    "not a probability."
                ),
                "supporting_evidence": tuple(
                    _public_evidence_citation(citation)
                    for citation in cause.supporting_evidence
                ),
                "contradicting_evidence": tuple(
                    _public_evidence_citation(citation)
                    for citation in cause.contradicting_evidence
                ),
                "missing_evidence": (
                    ("Additional producer-owned evidence is required.",)
                    if cause.missing_evidence
                    else ()
                ),
                "blocker_reasons": (
                    ("A producer-declared blocker limits this cause.",)
                    if cause.blocker_reasons
                    else ()
                ),
                "discriminator": None,
            }
        )
        for index, cause in enumerate(ranked_causes, start=1)
    )
    reasoning_snapshot = build_reasoning_snapshot(
        run_id=run_id,
        session_id=session_id,
        graph=report_graph,
        ranked_causes=snapshot_causes,
        measurement_plan=effective_measurement,
        data_quality=public_data_quality,
        lap_context=lap_context,
        mechanism_episodes=mechanism_episodes,
        mechanism_episode_blocker_reasons=mechanism_episode_blocker_reasons,
        blocker_reasons=(
            ("One or more canonical reasoning checks blocked authority.",)
            if blockers
            else ()
        ),
    )
    return InternalIntelligenceReport(
        run_id=run_id,
        session_id=session_id,
        response_context_key=(
            "qualified-context" if response_context_key is not None else None
        ),
        status=status,
        briefing=IntelligenceBriefing(
            issue=public_issue,
            action=action,
            success_check=success_check,
            confidence_label=confidence_label,
            blocker_reasons=blockers,
        ),
        competing_causes=tuple(public_causes),
        mind_change_criteria=mind_change_criteria,
        best_measurement=effective_measurement,
        context_matches=tuple(
            _public_response_memory(match) for match in validated_context_matches
        ),
        calibration=public_calibration,
        data_quality=public_data_quality,
        evidence_graph=report_graph,
        reasoning_snapshot=reasoning_snapshot,
        lap_context=lap_context,
        narrative=public_narrative,
        suggested_questions=_unique_text(questions),
        blocker_reasons=blockers,
    )


_QUERY_ALIASES = {
    "why this call": "why_this_call",
    "why": "why_this_call",
    "where is the loss": "where_is_loss",
    "where am i losing time": "where_is_loss",
    "where is the strongest repeatable loss": "where_is_loss",
    "what should i do next": "what_next",
    "what next": "what_next",
    "what evidence supports this": "what_evidence",
    "show evidence": "what_evidence",
    "what was ruled out": "what_was_ruled_out",
    "what worked here before": "what_worked_before",
    "what changed since the last qualified run": "what_changed",
    "what changed": "what_changed",
    "how repeatable is the strongest opportunity": "how_repeatable",
    "how consistent are my inputs": "driver_focus",
    "what should i repeat as a driver": "driver_focus",
    "what anomalies are new": "what_anomalies",
    "show anomalies": "what_anomalies",
    "which typed mechanism has the strongest evidence": "mechanism_evidence",
    "which hypotheses should i avoid repeating": "hypothesis_history",
    "is driver repeatability limiting this setup decision": "driver_focus",
    "which same setup anomaly should i inspect first": "what_anomalies",
    "what evidence should i recover first": "recovery_priority",
    "how reliable is this": "how_reliable",
    "how reliable": "how_reliable",
    "what is the prediction track record": "how_reliable",
    "what would change your mind": "what_would_change_mind",
    "is the data good": "data_quality",
    "data quality": "data_quality",
}


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", query.casefold())).strip()


@dataclass(frozen=True)
class _ParsedGroundedQuery:
    intent: str | None
    lap_number: int | None = None
    window_start_lap: int | None = None
    window_end_lap: int | None = None
    phase: str | None = None
    control_key: str | None = None
    track_region_id: str | None = None
    track_region_label: str | None = None
    clarification: str | None = None


_PHASE_QUERY_TERMS = {
    "braking": ("brake", "braking", "brake zone"),
    "entry": ("entry", "corner entry", "turn in"),
    "center": ("center", "centre", "mid corner", "apex"),
    "exit": ("exit", "corner exit", "power down"),
    "straight": ("straight", "full throttle", "straightaway"),
}


def _query_intent(normalized: str) -> str | None:
    exact = _QUERY_ALIASES.get(normalized)
    if exact is not None:
        return exact
    rules = (
        (
            "what_evidence",
            r"^(?:(?:turn|corner|t)\s*[1-9]\d*|front\s*stretch|frontstretch|"
            r"back\s*stretch|backstretch|connector\s*[1-9]\d*)"
            r"(?:\s+(?:entry|center|centre|exit))?$",
        ),
        ("what_changed", r"\b(what changed|improved|regressed|different since)\b"),
        ("how_repeatable", r"\b(repeatable|repeatability)\b.*\b(loss|opportunity|window)\b"),
        ("driver_focus", r"\b(driver|my inputs|steering|pedal)\b.*\b(consistent|repeat|focus|practice)\b"),
        ("what_anomalies", r"\b(anomal|outlier|unexpected)"),
        ("mechanism_evidence", r"\b(mechanism)\b.*\b(evidence|strongest|support)\b"),
        ("hypothesis_history", r"\b(hypoth|test)\b.*\b(avoid|repeat|failed|contradict)\b"),
        ("recovery_priority", r"\b(recover|missing)\b.*\b(evidence|data|measurement)\b"),
        ("what_was_ruled_out", r"\b(ruled out|rejected|eliminated)\b"),
        (
            "what_worked_before",
            r"\b(worked (?:here )?before|prior result|previous result|history)\b",
        ),
        ("how_reliable", r"\b(reliable|reliability|track record|calibrat)"),
        ("what_would_change_mind", r"\b(change (your|the) mind|disprove|contradict)\b"),
        ("data_quality", r"\b(data quality|data good|telemetry healthy|trust the data)\b"),
        ("where_is_loss", r"\b(where|location|part of (the )?lap)\b.*\b(loss|slow|time)\b"),
        (
            "what_evidence",
            r"\b(what happened|show me|inspect)\b.*"
            r"(?:\b(turn|corner|stretch|frontstretch|backstretch|connector)\b|\bt\s*[1-9]\d*\b)",
        ),
        ("what_evidence", r"\b(evidence|support|proof|citation)\b"),
        ("why_this_call", r"\bwhy\b.*\b(call|recommend|decision|cause|think)\b"),
        ("what_next", r"\b(what next|do next|next move|next step|should i do)\b"),
    )
    return next((intent for intent, pattern in rules if re.search(pattern, normalized)), None)


def _parse_grounded_query(query: str) -> _ParsedGroundedQuery:
    normalized = _normalize_query(query)
    intent = _query_intent(normalized)
    scope_text = re.sub(r"[\u2010-\u2015\u2212]", "-", query.casefold())
    window_matches = tuple(
        re.finditer(
            r"\blaps?\s*(\d+)\s*(?:to|through|thru|-)\s*(\d+)\b",
            scope_text,
        )
    )
    standalone_lap_matches = tuple(
        match
        for match in re.finditer(r"\blap\s*(\d+)\b", scope_text)
        if not any(
            window.start() <= match.start() and match.end() <= window.end()
            for window in window_matches
        )
    )
    shorthand_scope_atom = r"(?:\d+\s*(?:to|through|thru|-)\s*\d+|\d+)"
    multiple_shorthand_scopes = re.search(
        rf"\blaps?\s*{shorthand_scope_atom}\s*"
        rf"(?:,|and|or|versus|vs\.?|&)\s*"
        rf"(?:laps?\s*)?{shorthand_scope_atom}\b(?!\.\d|%)",
        scope_text,
    )
    if (
        len(window_matches) + len(standalone_lap_matches) > 1
        or multiple_shorthand_scopes is not None
    ):
        return _ParsedGroundedQuery(
            intent=intent,
            clarification=(
                "The question names more than one lap scope; ask about one lap or one lap "
                "window at a time."
            ),
        )
    window_match = window_matches[0] if window_matches else None
    window_start = int(window_match.group(1)) if window_match else None
    window_end = int(window_match.group(2)) if window_match else None
    if window_start is not None and window_end is not None and window_start > window_end:
        return _ParsedGroundedQuery(
            intent=intent,
            clarification="The requested lap window is reversed; provide an ordered start and end lap.",
        )
    lap_match = standalone_lap_matches[0] if standalone_lap_matches else None
    lap_number = int(lap_match.group(1)) if lap_match is not None else None
    region_matches: list[tuple[str, str]] = []
    for match in re.finditer(
        r"\b(?:turn|corner)\s*([1-9]\d*)\b|\bt\s*([1-9]\d*)\b",
        normalized,
    ):
        number = int(match.group(1) or match.group(2))
        region_matches.append((f"turn_{number}", f"Turn {number}"))
    if re.search(r"\bfront\s*stretch\b|\bfrontstretch\b", normalized):
        region_matches.append(("front_stretch", "Front Stretch"))
    if re.search(r"\bback\s*stretch\b|\bbackstretch\b", normalized):
        region_matches.append(("backstretch", "Backstretch"))
    for match in re.finditer(r"\bconnector\s*([1-9]\d*)\b", normalized):
        number = int(match.group(1))
        region_matches.append((f"connector_{number}", f"Connector {number}"))
    region_matches = list(dict.fromkeys(region_matches))
    if len(region_matches) > 1:
        return _ParsedGroundedQuery(
            intent=intent,
            lap_number=lap_number,
            window_start_lap=window_start,
            window_end_lap=window_end,
            clarification=(
                "The question names more than one track region; ask about one turn or "
                "straight at a time."
            ),
        )
    phases = tuple(
        phase
        for phase, terms in _PHASE_QUERY_TERMS.items()
        if any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in terms)
    )
    if len(phases) > 1:
        return _ParsedGroundedQuery(
            intent=intent,
            lap_number=lap_number,
            window_start_lap=window_start,
            window_end_lap=window_end,
            track_region_id=region_matches[0][0] if region_matches else None,
            track_region_label=region_matches[0][1] if region_matches else None,
            clarification="The question names more than one driving phase; ask about one phase at a time.",
        )
    control_matches: list[str] = []
    for key, spec in SETUP_CONTROL_SPECS.items():
        aliases = {
            _normalize_query(key.replace("_", " ")),
            _normalize_query(spec.label),
            _normalize_query(spec.garage_label or ""),
        }
        if any(
            alias and len(alias) >= 4 and re.search(rf"\b{re.escape(alias)}\b", normalized)
            for alias in aliases
        ):
            control_matches.append(key)
    control_matches = sorted(set(control_matches))
    if len(control_matches) > 1:
        return _ParsedGroundedQuery(
            intent=intent,
            lap_number=lap_number,
            window_start_lap=window_start,
            window_end_lap=window_end,
            phase=phases[0] if phases else None,
            track_region_id=region_matches[0][0] if region_matches else None,
            track_region_label=region_matches[0][1] if region_matches else None,
            clarification="The question names multiple setup controls; ask about one control at a time.",
        )
    return _ParsedGroundedQuery(
        intent=intent,
        lap_number=lap_number,
        window_start_lap=window_start,
        window_end_lap=window_end,
        phase=phases[0] if phases else None,
        control_key=control_matches[0] if control_matches else None,
        track_region_id=region_matches[0][0] if region_matches else None,
        track_region_label=region_matches[0][1] if region_matches else None,
    )


def _navigation(citations: Sequence[EvidenceCitation]) -> tuple[NavigationTarget, ...]:
    targets: list[NavigationTarget] = []
    seen: set[tuple[Any, ...]] = set()
    for citation in citations:
        key = (
            citation.workspace,
            citation.run_id,
            citation.lap_number,
            citation.event_id,
            citation.lap_pct_peak,
        )
        if key in seen:
            continue
        seen.add(key)
        targets.append(
            NavigationTarget(
                workspace=citation.workspace,
                run_id=citation.run_id,
                lap_number=citation.lap_number,
                event_id=citation.event_id,
                lap_pct=citation.lap_pct_peak,
            )
        )
    return tuple(targets)


def answer_grounded_query(
    query: str,
    report: InternalIntelligenceReport,
    *,
    selected_lap_number: int | None = None,
    selected_window_start_lap: int | None = None,
    selected_window_end_lap: int | None = None,
    selected_window_representative_lap: int | None = None,
    track_region_resolver: Callable[[str, float], Mapping[str, Any] | None] | None = None,
    track_region_catalog: Mapping[str, str] | Callable[[], Mapping[str, str]] | None = None,
) -> GroundedQueryResult:
    """Answer supported intent and scope combinations using report evidence only."""
    normalized = _normalize_query(query)
    parsed = _parse_grounded_query(query)
    intent = parsed.intent
    selected_window_supplied = any(
        value is not None
        for value in (
            selected_window_start_lap,
            selected_window_end_lap,
            selected_window_representative_lap,
        )
    )
    selected_window_complete = all(
        value is not None
        for value in (
            selected_window_start_lap,
            selected_window_end_lap,
            selected_window_representative_lap,
        )
    )
    selected_window_ordered = bool(
        selected_window_complete
        and selected_window_start_lap <= selected_window_end_lap
    )
    representative_in_window = bool(
        selected_window_representative_lap is None
        or selected_window_ordered
        and selected_window_start_lap
        <= selected_window_representative_lap
        <= selected_window_end_lap
    )
    parsed_window_supplied = (
        parsed.window_start_lap is not None and parsed.window_end_lap is not None
    )
    parsed_window_needs_representative = bool(
        parsed_window_supplied
        and not selected_window_complete
        and selected_lap_number is None
    )
    region_clarification: str | None = None
    if parsed.track_region_id is not None:
        if track_region_resolver is None or track_region_catalog is None:
            region_clarification = (
                "Track-region geometry is unavailable for this run; select a run with a "
                "matched canonical map before asking a region-scoped question."
            )
        else:
            resolved_region_catalog = (
                track_region_catalog() if callable(track_region_catalog) else track_region_catalog
            )
            if parsed.track_region_id not in resolved_region_catalog:
                available = ", ".join(resolved_region_catalog.values()) or "no canonical regions"
                region_clarification = (
                    f"{parsed.track_region_label} is not defined on this matched layout. "
                    f"Available regions: {available}."
                )
    scope_clarification: str | None = None
    if selected_window_supplied and not selected_window_complete:
        scope_clarification = (
            "The selected lap window is incomplete; select its start, end, and one exact "
            "representative lap."
        )
    elif selected_window_complete and not selected_window_ordered:
        scope_clarification = (
            "The selected lap window is reversed; select an ordered start and end lap."
        )
    elif not representative_in_window:
        scope_clarification = (
            "The selected representative lap does not belong to the selected lap window."
        )
    elif selected_lap_number is not None and selected_window_supplied:
        scope_clarification = (
            "The selected scope contains both one lap and a lap window; select exactly one."
        )
    elif selected_lap_number is not None and parsed_window_supplied:
        scope_clarification = (
            f"The question names lap window {parsed.window_start_lap}-{parsed.window_end_lap}, "
            f"but the selected scope is lap {selected_lap_number}. Select one exact scope."
        )
    elif selected_window_complete and parsed.lap_number is not None:
        scope_clarification = (
            f"The question names lap {parsed.lap_number}, but the selected scope is lap window "
            f"{selected_window_start_lap}-{selected_window_end_lap}. Select one exact scope."
        )
    elif parsed_window_needs_representative:
        scope_clarification = (
            f"The question names lap window {parsed.window_start_lap}-{parsed.window_end_lap}, "
            "but an exact representative lap was not selected. Select one representative lap "
            "inside that window before asking for a window-scoped conclusion."
        )
    elif (
        selected_lap_number is not None
        and parsed.lap_number is not None
        and parsed.lap_number != selected_lap_number
    ):
        scope_clarification = (
            f"The question names lap {parsed.lap_number}, but the selected scope is lap "
            f"{selected_lap_number}. Select one lap or remove the lap number from the question."
        )
    elif selected_window_complete and parsed_window_supplied and (
        parsed.window_start_lap != selected_window_start_lap
        or parsed.window_end_lap != selected_window_end_lap
    ):
        scope_clarification = (
            f"The question names lap window {parsed.window_start_lap}-{parsed.window_end_lap}, "
            f"but the selected scope is {selected_window_start_lap}-{selected_window_end_lap}. "
            "Use the exact selected window or remove the lap window from the question."
        )
    known_lap_numbers = {
        node.citation.lap_number
        for node in report.evidence_graph.nodes
        if node.kind is EvidenceNodeKind.LAP
        and node.citation is not None
        and node.citation.run_id == report.run_id
        and node.citation.lap_number is not None
    }
    requested_lap_number = (
        selected_lap_number
        if selected_lap_number is not None
        else parsed.lap_number
    )
    effective_window_start_lap = (
        selected_window_start_lap
        if selected_window_complete and selected_window_ordered
        else parsed.window_start_lap
    )
    effective_window_end_lap = (
        selected_window_end_lap
        if selected_window_complete and selected_window_ordered
        else parsed.window_end_lap
    )
    requested_lap_missing = (
        requested_lap_number is not None
        and requested_lap_number not in known_lap_numbers
    )
    requested_window_missing = (
        effective_window_start_lap is not None
        and effective_window_end_lap is not None
        and not any(
            effective_window_start_lap <= lap_number <= effective_window_end_lap
            for lap_number in known_lap_numbers
        )
    )
    interpreted_lap_number = (
        selected_lap_number
        if selected_lap_number is not None
        else None
        if selected_window_complete
        else parsed.lap_number
    )
    interpreted_window_start_lap = (
        selected_window_start_lap
        if selected_window_complete and selected_lap_number is None
        else None
        if selected_lap_number is not None or parsed_window_needs_representative
        else parsed.window_start_lap
    )
    interpreted_window_end_lap = (
        selected_window_end_lap
        if selected_window_complete and selected_lap_number is None
        else None
        if selected_lap_number is not None or parsed_window_needs_representative
        else parsed.window_end_lap
    )
    interpreted_window_representative_lap = (
        selected_window_representative_lap
        if selected_window_complete
        and selected_lap_number is None
        and selected_window_ordered
        and representative_in_window
        else None
    )
    if (
        intent is None
        or parsed.clarification is not None
        or scope_clarification is not None
        or region_clarification is not None
        or requested_lap_missing
        or requested_window_missing
    ):
        clarification = parsed.clarification or scope_clarification or region_clarification or (
            f"Lap {requested_lap_number} does not belong to run {report.run_id}."
            if requested_lap_missing
            else (
                f"No recorded lap belongs to requested window "
                f"{effective_window_start_lap}-{effective_window_end_lap}."
            )
            if requested_window_missing
            else None
        )
        return GroundedQueryResult(
            supported=False,
            intent="unsupported",
            answer=(
                clarification
                or "That question is outside the grounded query vocabulary. Try one of the "
                "suggested questions."
            ),
            citations=(),
            suggested_navigation=(),
            interpreted_lap_number=interpreted_lap_number,
            interpreted_window_start_lap=interpreted_window_start_lap,
            interpreted_window_end_lap=interpreted_window_end_lap,
            interpreted_window_representative_lap=(
                interpreted_window_representative_lap
            ),
            interpreted_phase=parsed.phase,
            interpreted_control_key=parsed.control_key,
            interpreted_track_region_id=parsed.track_region_id,
            interpreted_track_region_label=parsed.track_region_label,
            clarification_required=clarification is not None,
            blocker_reasons=(
                clarification or "Unsupported grounded-query intent.",
            ),
        )

    effective_lap_number = requested_lap_number
    region_scope_requested = parsed.track_region_id is not None
    qualified_control_links = _qualified_event_setup_links(report.evidence_graph)

    def canonical_location_region(location: Mapping[str, Any]) -> str | None:
        region_id = location.get("region_id")
        if isinstance(region_id, str) and region_id.startswith("turn_"):
            return region_id
        label = str(location.get("label") or "").casefold().replace(" ", "")
        if label == "frontstretch":
            return "front_stretch"
        if label == "backstretch":
            return "backstretch"
        if isinstance(region_id, str) and region_id.startswith("straight:"):
            return region_id.split(":", 1)[1]
        return str(region_id) if region_id is not None else None

    def in_query_scope(citation: EvidenceCitation) -> bool:
        phase_matches = parsed.phase is None or citation.phase == parsed.phase
        lap_matches = (
            effective_window_start_lap
            <= citation.lap_number
            <= effective_window_end_lap
            if effective_window_start_lap is not None
            and effective_window_end_lap is not None
            and citation.lap_number is not None
            else effective_lap_number is None
            or citation.lap_number == effective_lap_number
        )
        control_matches = (
            parsed.control_key is None
            or citation.event_id is not None
            and (
                f"event:{citation.event_id}",
                f"setup:{parsed.control_key}",
            )
            in qualified_control_links
        )
        region_matches = True
        if parsed.track_region_id is not None:
            lap_pct = (
                citation.lap_pct_peak
                if citation.lap_pct_peak is not None
                else citation.lap_pct_start
            )
            location = (
                track_region_resolver(citation.run_id, lap_pct)
                if track_region_resolver is not None and lap_pct is not None
                else None
            )
            region_matches = bool(
                location is not None
                and canonical_location_region(location) == parsed.track_region_id
                and (parsed.phase is None or location.get("phase") == parsed.phase)
            )
        return (
            citation.run_id == report.run_id
            and lap_matches
            and phase_matches
            and control_matches
            and region_matches
        )

    def reference_in_lap_scope(
        reference_run_id: str | None,
        reference_lap_number: int | None,
    ) -> bool:
        if effective_lap_number is not None:
            return (
                reference_run_id == report.run_id
                and reference_lap_number == effective_lap_number
            )
        if (
            effective_window_start_lap is not None
            and effective_window_end_lap is not None
        ):
            return bool(
                reference_run_id == report.run_id
                and reference_lap_number is not None
                and effective_window_start_lap
                <= reference_lap_number
                <= effective_window_end_lap
            )
        return True

    graph_event_citations = {
        node.entity_id: node.citation
        for node in report.evidence_graph.nodes
        if node.kind is EvidenceNodeKind.EVENT
        and node.qualified
        and node.citation is not None
        and node.citation.valid_for_tuning
        and in_query_scope(node.citation)
    }
    def resolved_cause_citations(
        cause: PublicCompetingCause, *, contradicting: bool = False
    ) -> tuple[EvidenceCitation, ...]:
        declared = cause.evidence_against if contradicting else cause.evidence_for
        event_ids = tuple(
            dict.fromkeys(
                citation.event_id
                for citation in declared
                if citation.event_id is not None
            )
        )
        return tuple(
            graph_event_citations[event_id]
            for event_id in event_ids
            if event_id in graph_event_citations
        )

    def resolved_controlled_citations(
        cause: PublicCompetingCause,
        *,
        outcomes: tuple[str, ...],
    ) -> tuple[EvidenceCitation, ...]:
        if (
            effective_lap_number is not None
            or effective_window_start_lap is not None
            or region_scope_requested
        ):
            return ()
        citations: list[EvidenceCitation] = []
        for outcome in cause.controlled_outcomes:
            phase = _typed_phase(outcome.phase)
            if (
                outcome.source_run_id != report.run_id
                or outcome.outcome not in outcomes
                or parsed.phase is not None
                and phase != parsed.phase
                or parsed.control_key is not None
                and outcome.control_key != parsed.control_key
            ):
                continue
            result = (
                "supported"
                if outcome.outcome == "supported"
                else "contradicted"
            )
            policy_note = (
                " The unchanged control policy still received Undo."
                if outcome.verdict == "undo"
                else ""
            )
            citations.append(
                EvidenceCitation(
                    citation_id=(
                        f"controlled-outcome:{outcome.workflow_id}:{outcome.outcome}"
                    ),
                    run_id=outcome.source_run_id,
                    workspace="dial_in",
                    channels=(),
                    evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
                    valid_for_tuning=False,
                    summary=(
                        f"Protocol-valid A/B/A2 target evidence {result} this exact cause."
                        f"{policy_note}"
                    ),
                    phase=phase,
                )
            )
        return tuple(citations)

    def observation_citation(
        item: ObservationCitation,
        *,
        citation_id: str,
        summary: str,
        phase: str,
    ) -> EvidenceCitation:
        return EvidenceCitation(
            citation_id=citation_id,
            run_id=item.run_id,
            lap_number=item.lap_number,
            lap_pct_start=item.lap_pct_start,
            lap_pct_end=item.lap_pct_end,
            lap_pct_peak=item.lap_pct_peak,
            event_id=item.event_id,
            workspace="platform",
            channels=item.source_channels,
            evidence_state=item.evidence_state,
            valid_for_tuning=False,
            summary=summary,
            phase=_typed_phase(phase),
        )

    if (
        effective_lap_number is None
        and effective_window_start_lap is None
        and not region_scope_requested
    ):
        candidate_leading = next(
            (cause for cause in report.competing_causes if cause.state == "leading"),
            None,
        )
        leading = (
            candidate_leading
            if candidate_leading is not None
            and (
                resolved_cause_citations(candidate_leading)
                or resolved_controlled_citations(
                    candidate_leading,
                    outcomes=("supported",),
                )
            )
            and not resolved_cause_citations(candidate_leading, contradicting=True)
            and not resolved_controlled_citations(
                candidate_leading,
                outcomes=("contradicted",),
            )
            else None
        )
    else:
        selected_strengths: list[tuple[tuple[int, int], PublicCompetingCause]] = []
        for cause in report.competing_causes:
            evidence_for = resolved_cause_citations(cause)
            evidence_against = resolved_cause_citations(cause, contradicting=True)
            if cause.state == "ruled_out" or not evidence_for:
                continue
            supporting_units = {
                (citation.run_id, citation.lap_number) for citation in evidence_for
            }
            contradicting_units = {
                (citation.run_id, citation.lap_number) for citation in evidence_against
            }
            selected_strengths.append(
                ((len(supporting_units), -len(contradicting_units)), cause)
            )
        best_strength = max(
            (strength for strength, _ in selected_strengths),
            default=None,
        )
        selected_best = [
            (strength, cause)
            for strength, cause in selected_strengths
            if strength == best_strength
        ]
        leading = (
            selected_best[0][1]
            if len(selected_best) == 1
            and selected_best[0][0][1] == 0
            and selected_best[0][1].state == "leading"
            else None
        )
    supporting_citations = tuple(
        dict.fromkeys(
            citation
            for cause in report.competing_causes
            if cause.state in {"leading", "possible"}
            for citation in (
                *resolved_cause_citations(cause),
                *resolved_controlled_citations(
                    cause,
                    outcomes=("supported",),
                ),
            )
        )
    )
    citations: tuple[EvidenceCitation, ...] = ()
    blockers: tuple[str, ...] = ()
    mind_change_criteria: tuple[MindChangeCriterion, ...] = ()
    extra_navigation: tuple[NavigationTarget, ...] = ()
    action_authorized = False
    action_source_event_ids: tuple[str, ...] = ()
    if intent == "how_repeatable":
        opportunity = report.opportunity_signature
        signatures = tuple(opportunity.signatures) if opportunity is not None else ()
        scoped_signatures: list[tuple[Any, tuple[EvidenceCitation, ...]]] = []
        for signature in signatures:
            if parsed.phase is not None and signature.phase.casefold() != parsed.phase:
                continue
            scoped_citations = tuple(
                citation
                for index, item in enumerate(signature.citations, start=1)
                if in_query_scope(
                    citation := observation_citation(
                        item,
                        citation_id=f"opportunity:{signature.signature_id}:{index}",
                        summary=(
                            f"Same-setup {signature.phase} opportunity near "
                            f"{signature.lap_pct_peak:g}% of the lap."
                        ),
                        phase=signature.phase,
                    )
                )
            )
            if scoped_citations and (
                effective_lap_number is None
                and effective_window_start_lap is None
                and parsed.control_key is None
                and not region_scope_requested
                or len(scoped_citations) == len(signature.citations)
            ):
                scoped_signatures.append((signature, scoped_citations))
        if scoped_signatures:
            strongest, citations = sorted(
                scoped_signatures,
                key=lambda item: (
                    -item[0].median_opportunity_s,
                    -item[0].repetition_count,
                    item[0].signature_id,
                ),
            )[0]
            answer = (
                f"The strongest same-setup opportunity repeats on {strongest.repetition_count} "
                f"of {strongest.eligible_lap_count} eligible laps near "
                f"{strongest.lap_pct_start:g}-{strongest.lap_pct_end:g}% in "
                f"{strongest.phase}. Its median opportunity is "
                f"{strongest.median_opportunity_s:.3f}s against an empirical noise floor of "
                f"{strongest.empirical_noise_s:.3f}s. This is an observation, not a cause."
            )
        else:
            answer = "No sustained same-setup opportunity signature is qualified in this scope."
            blockers = (
                (
                    "Every citation behind an aggregate repeatability claim must belong to "
                    "the requested lap scope.",
                )
                if signatures
                else tuple(opportunity.blocker_reasons)
                if opportunity is not None and opportunity.blocker_reasons
                else ("Record at least three eligible same-setup aligned laps.",)
            )
    elif intent == "driver_focus":
        driver = report.driver_focus
        focus = driver.focus if driver is not None else None
        if focus is not None:
            citations = tuple(
                citation
                for index, item in enumerate(focus.citations, start=1)
                if in_query_scope(
                    citation := observation_citation(
                        item,
                        citation_id=f"driver-focus:{driver.run_id}:{index}",
                        summary=(
                            f"Driver-input repeatability evidence in {focus.phase} near "
                            f"{focus.lap_pct_start:g}-{focus.lap_pct_end:g}%."
                        ),
                        phase=focus.phase,
                    )
                )
            )
            answer = (
                f"Driver focus: {focus.instruction} Success check: {focus.success_check} "
                "This coaching does not authorize a setup change."
            )
            if not citations or (
                effective_lap_number is not None
                or effective_window_start_lap is not None
                or parsed.control_key is not None
                or region_scope_requested
            ) and len(citations) != len(focus.citations):
                answer = "No driver-input coaching focus is fully grounded in this lap scope."
                citations = ()
                blockers = (
                    "Every citation behind aggregate driver coaching must belong to the "
                    "requested lap scope.",
                )
        else:
            answer = "No driver-input coaching focus is qualified in this scope."
            blockers = (
                tuple(driver.blocker_reasons)
                if driver is not None and driver.blocker_reasons
                else ("Record comparable same-setup driver-input laps.",)
            )
    elif intent == "what_anomalies":
        anomaly_report = report.anomalies
        anomalies = tuple(anomaly_report.anomalies) if anomaly_report is not None else ()
        scoped_anomalies: list[tuple[Any, tuple[EvidenceCitation, ...]]] = []
        for anomaly in anomalies:
            if parsed.phase is not None and anomaly.phase.casefold() != parsed.phase:
                continue
            scoped_citations = tuple(
                citation
                for index, item in enumerate(anomaly.citations, start=1)
                if in_query_scope(
                    citation := observation_citation(
                        item,
                        citation_id=f"anomaly:{anomaly.anomaly_id}:{index}",
                        summary=(
                            f"Sustained {anomaly.channel} {anomaly.phase} anomaly near "
                            f"{anomaly.lap_pct_start:g}-{anomaly.lap_pct_end:g}%."
                        ),
                        phase=anomaly.phase,
                    )
                )
            )
            if scoped_citations and (
                effective_lap_number is None
                and effective_window_start_lap is None
                and parsed.control_key is None
                and not region_scope_requested
                or len(scoped_citations) == len(anomaly.citations)
            ):
                scoped_anomalies.append((anomaly, scoped_citations))
        if scoped_anomalies:
            anomaly, citations = sorted(
                scoped_anomalies,
                key=lambda item: (-item[0].aligned_bin_count, item[0].anomaly_id),
            )[0]
            answer = (
                f"A sustained {anomaly.channel} cluster is {anomaly.direction.replace('_', ' ')} "
                f"its same-setup robust envelope on lap {anomaly.lap_number} near "
                f"{anomaly.lap_pct_start:g}-{anomaly.lap_pct_end:g}%. It is unexpected "
                "observed behavior, not a diagnosed cause."
            )
        else:
            answer = "No sustained same-setup anomaly is qualified in this scope."
            blockers = (
                tuple(anomaly_report.blocker_reasons)
                if anomaly_report is not None and anomaly_report.blocker_reasons
                else ((
                    "No anomaly citation belongs to the requested run, lap window, and phase."
                    if anomalies
                    else "Build a same-setup robust reference envelope first."
                ),)
            )
    elif intent == "mechanism_evidence":
        mechanism_report = report.mechanism_observations
        observations = (
            tuple(mechanism_report.observations) if mechanism_report is not None else ()
        )
        qualified = tuple(observation for observation in observations if observation.qualified)
        scoped_observations: list[tuple[Any, tuple[EvidenceCitation, ...]]] = []
        for observation in qualified:
            if (
                parsed.phase is not None
                and _typed_phase(observation.phase) != parsed.phase
            ):
                continue
            scoped_citations = tuple(
                citation
                for index, item in enumerate(observation.citations, start=1)
                if in_query_scope(
                    citation := observation_citation(
                        item,
                        citation_id=f"mechanism:{observation.observation_id}:{index}",
                        summary=observation.summary,
                        phase=observation.phase or "",
                    )
                )
            )
            if scoped_citations and (
                effective_lap_number is None
                and effective_window_start_lap is None
                and parsed.control_key is None
                and not region_scope_requested
                or len(scoped_citations) == len(observation.citations)
            ):
                scoped_observations.append((observation, scoped_citations))
        if scoped_observations:
            strongest, citations = sorted(
                scoped_observations,
                key=lambda item: (
                    -len(item[0].supporting_evidence),
                    len(item[0].contradicting_evidence),
                    -item[0].repetition_count,
                    item[0].observation_id,
                ),
            )[0]
            answer = (
                f"The strongest typed observation is {strongest.mechanism.value.replace('_', ' ')}: "
                f"{strongest.summary} It has {len(strongest.supporting_evidence)} supporting and "
                f"{len(strongest.contradicting_evidence)} contradicting producer facts. "
                "It remains observation-only and cannot authorize setup."
            )
        else:
            answer = "No typed mechanism observation is qualified in this scope."
            blockers = (
                (
                    "Every citation behind an aggregate mechanism observation must belong "
                    "to the requested evidence scope.",
                )
                if qualified
                else tuple(mechanism_report.blocker_reasons)
                if mechanism_report is not None and mechanism_report.blocker_reasons
                else ("Run a producer-owned mechanism measurement with complete channels.",)
            )
    elif intent == "hypothesis_history":
        lifecycle = report.hypothesis_lifecycle
        entries = tuple(lifecycle.entries) if lifecycle is not None else ()
        blocked_entries = tuple(
            entry
            for entry in entries
            if entry.lifecycle_state == "do_not_repeat"
            and (
                parsed.control_key is None
                or entry.control_key == parsed.control_key
            )
            and (
                parsed.phase is None
                or _typed_phase(entry.target_effect.phase) == parsed.phase
            )
        )
        if blocked_entries:
            entry = blocked_entries[-1]
            citations = tuple(
                EvidenceCitation(
                    citation_id=(
                        f"hypothesis:{entry.workflow_id}:{reference.kind}:"
                        f"{reference.reference_id}"
                    ),
                    run_id=reference.run_id,
                    lap_number=reference.lap_number,
                    workspace="dial_in",
                    channels=("controlled_workflow_outcome",),
                    evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
                    valid_for_tuning=False,
                    summary="Immutable controlled-hypothesis outcome evidence.",
                    phase=_typed_phase(entry.target_effect.phase),
                )
                for reference in entry.citations
                if reference.run_id is not None
                and reference_in_lap_scope(
                    reference.run_id,
                    reference.lap_number,
                )
            )
            answer = (
                "One exact context-bound control policy is marked do-not-repeat because a valid "
                f"controlled test produced Undo. Its target-direction cause outcome is "
                f"{entry.outcome_classification}; a countereffect-only Undo does not convert "
                "target support into cause contradiction. A materially changed policy or context "
                "receives a different identity and is not automatically blocked."
            )
            if (
                effective_lap_number is not None
                or effective_window_start_lap is not None
                or region_scope_requested
            ):
                answer = (
                    "No do-not-repeat controlled outcome has provenance in the requested "
                    "lap scope."
                )
                citations = ()
                blockers = (
                    "Open Dial-In without a lap scope to audit the exact workflow outcome.",
                )
        else:
            answer = "No exact controlled hypothesis is marked do-not-repeat in this session."
            blockers = (
                tuple(lifecycle.blocker_reasons)
                if lifecycle is not None and lifecycle.blocker_reasons
                else ("Only a valid scored controlled outcome can create this policy.",)
            )
    elif intent == "recovery_priority":
        guidance = report.smart_guidance
        debt = guidance.measurement_debt if guidance is not None else None
        if (
            effective_lap_number is not None
            or effective_window_start_lap is not None
            or parsed.phase is not None
            or parsed.control_key is not None
            or region_scope_requested
        ):
            answer = "No recovery priority is grounded in this narrower evidence scope."
            blockers = (
                "Remove the lap, phase, or control scope to inspect run-level measurement debt.",
            )
        elif debt is not None and debt.items:
            item = debt.items[0]
            answer = f"Recover this first: {item.label}. {item.reason}"
            blockers = tuple(item.blocker_reasons)
        else:
            answer = "No typed evidence prerequisite currently blocks the ranked next move."
    elif intent == "why_this_call":
        if leading is None:
            answer = (
                f"{report.briefing.action.title}. No cause has uniquely leading qualified evidence."
            )
            blockers = report.briefing.blocker_reasons or (
                "No uniquely leading evidence-qualified cause is available.",
            )
        else:
            answer = (
                f"{report.briefing.action.title}. {leading.label} leads only on ordinal "
                "evidence, not probability. Exact setup targets are shown only by the guarded "
                "what-next answer."
            )
            citations = tuple(
                dict.fromkeys(
                    (
                        *resolved_cause_citations(leading),
                        *resolved_controlled_citations(
                            leading,
                            outcomes=("supported",),
                        ),
                    )
                )
            )
    elif intent == "where_is_loss":
        citations = tuple(
            sorted(
                dict.fromkeys(
                    citation
                    for citation in supporting_citations
                    if citation.lap_pct_peak is not None
                ),
                key=lambda citation: (
                    citation.lap_pct_peak,
                    citation.lap_number if citation.lap_number is not None else -1,
                    citation.event_id or citation.citation_id,
                ),
            )
        )
        if normalized == "where is the strongest repeatable loss":
            answer = (
                "Qualified loss locations are cited, but this report does not carry a "
                "repeatability count and comparable loss magnitude needed to name the strongest."
            )
            blockers = (
                "Measure repeated, context-matched physical windows with comparable loss magnitude.",
            )
        elif citations:
            location = citations[0]
            answer = (
                f"The earliest qualified track location is near {location.lap_pct_peak:g}% of lap "
                f"{location.lap_number}; open the cited event for the recorded trace."
            )
        else:
            answer = "No qualified physical-position citation identifies the loss."
            blockers = ("Record a repeatable event with physical track position.",)
    elif intent == "what_next":
        action = report.briefing.action
        answer = (
            "Revalidate the evidence-linked controlled card before showing an exact target."
            if action.setup_authorized
            else action.instruction
        )
        if action.setup_authorized:
            card = (
                report.best_measurement.controlled_test
                if report.best_measurement.kind == "controlled_test"
                else None
            )
            source_ids = (
                tuple(dict.fromkeys(card.evidence_event_ids)) if card is not None else ()
            )
            citations = tuple(
                graph_event_citations[event_id]
                for event_id in source_ids
                if event_id in graph_event_citations
            )
            action_authorized = bool(
                source_ids
                and len(citations) == len(source_ids)
                and all(citation.valid_for_tuning for citation in citations)
                and report.status == "ready"
                and report.data_quality.status == "ready"
                and not report.best_measurement.blocker_reasons
                and card is not None
                and _controlled_card_is_semantically_complete(card)
                and _card_matches_setup_authorization(report.evidence_graph, card)
                and action.kind == "controlled_test"
                and action.control_key is not None
                and action.control_key == card.control_key
                and action.current_value
                == format_setup_value(card.control_key, card.current_value)
                and action.proposed_value == card.proposed_value
                and action.instruction == card.exact_change
                and tuple(action.source_event_ids) == tuple(card.evidence_event_ids)
                and all(
                    (f"event:{event_id}", f"setup:{action.control_key}")
                    in qualified_control_links
                    for event_id in source_ids
                )
            )
            if action_authorized:
                action_source_event_ids = source_ids
                answer = card.exact_change
            else:
                answer = (
                    "No setup action is authorized for the requested evidence scope. "
                    "Rebuild the controlled test from qualified events in this scope."
                )
                citations = ()
                blockers = (
                    "Every controlled-test source event must be qualified and cited in the requested run and lap scope.",
                )
        else:
            blockers = report.briefing.blocker_reasons
    elif intent == "what_evidence":
        citations = tuple(dict.fromkeys(supporting_citations))
        if citations:
            descriptions = "; ".join(citation.summary for citation in citations[:3])
            answer = f"Qualified evidence: {descriptions}."
            if any(not citation.valid_for_tuning for citation in citations):
                answer += (
                    " Controlled-workflow provenance explains cause rank only; it does not "
                    "authorize a setup action."
                )
        else:
            answer = "No qualified evidence currently supports a setup action."
            blockers = ("Collect provenance-complete evidence on eligible laps.",)
    elif intent == "what_was_ruled_out":
        local_evidence_scope = bool(
            effective_lap_number is not None
            or effective_window_start_lap is not None
            or region_scope_requested
        )
        ruled_out_evidence: list[
            tuple[PublicCompetingCause, tuple[EvidenceCitation, ...]]
        ] = []
        for cause in report.competing_causes:
            if cause.state != "ruled_out":
                continue
            evidence_against = resolved_cause_citations(
                cause,
                contradicting=True,
            )
            controlled_against = resolved_controlled_citations(
                cause,
                outcomes=("contradicted",),
            )
            if local_evidence_scope:
                contradiction_units = {
                    (citation.run_id, citation.lap_number)
                    for citation in evidence_against
                }
                if (
                    len(contradiction_units)
                    < _MIN_REPEATED_CAUSE_EVIDENCE_UNITS
                    or resolved_cause_citations(cause)
                    or cause.controlled_outcomes
                ):
                    continue
                ruled_out_evidence.append((cause, evidence_against))
            elif evidence_against or controlled_against:
                ruled_out_evidence.append(
                    (cause, (*evidence_against, *controlled_against))
                )
        citations = tuple(
            citation
            for _cause, cause_citations in ruled_out_evidence
            for citation in cause_citations
        )
        if ruled_out_evidence:
            answer = "Ruled out on qualified contradictory evidence: " + ", ".join(
                cause.label for cause, _citations in ruled_out_evidence
            ) + "."
        else:
            answer = "No cause has enough qualified contradictory evidence to be ruled out."
            blockers = (
                (
                    "Observational contradiction can weaken a cause but cannot rule it out; "
                    "that requires an explicitly mechanism-diagnostic controlled result."
                )
                if local_evidence_scope
                else "Do not treat an untested alternative as ruled out.",
            )
    elif intent == "what_changed":
        ledger = report.session_ledger
        entries = tuple(ledger.entries) if ledger is not None else ()
        previous_run_id = None
        if ledger is not None and report.run_id in ledger.ordered_run_ids:
            current_index = ledger.ordered_run_ids.index(report.run_id)
            if current_index > 0:
                previous_run_id = ledger.ordered_run_ids[current_index - 1]
        local_transition_scope = (
            effective_lap_number is not None
            or effective_window_start_lap is not None
            or region_scope_requested
        )
        relevant = tuple(
            entry
            for entry in entries
            if not local_transition_scope
            and previous_run_id is not None
            and entry.baseline_run_id == previous_run_id
            and entry.test_run_id == report.run_id
            and (
                parsed.phase is None
                or _typed_phase(entry.phase) == parsed.phase
            )
            and (
                parsed.control_key is None
                or any(
                    change.setup_key == parsed.control_key
                    for change in entry.setup_changes
                )
            )
        )
        if relevant:
            entry = relevant[-1]
            answer = entry.description
            citations = tuple(
                EvidenceCitation(
                    citation_id=(
                        f"session-ledger:{entry.entry_id}:{reference.kind}:"
                        f"{reference.reference_id}"
                    ),
                    run_id=reference.run_id,
                    lap_number=reference.lap_number,
                    event_id=(
                        reference.reference_id if reference.kind == "event" else None
                    ),
                    workspace="laps" if reference.kind in {"run", "lap"} else "overview",
                    channels=(),
                    evidence_state=EvidenceState.OBSERVED_CORRELATION,
                    valid_for_tuning=False,
                    summary=entry.description,
                )
                for reference in entry.citations
                if reference.run_id is not None
                and reference_in_lap_scope(
                    reference.run_id,
                    reference.lap_number,
                )
            )
            blockers = tuple(entry.blocker_reasons)
            if entry.attribution == "observation_only":
                answer += " This is an observed compatible-run change, not setup attribution."
        else:
            answer = "No compatible qualified run transition is available in this exact session."
            blockers = (
                "Run transitions cannot be narrowed to one selected lap or lap window."
                if local_transition_scope
                else "Attach at least two compatible qualified runs before comparing what changed.",
            )
    elif intent == "what_worked_before":
        query_context_matches, query_context_blockers = _revalidate_response_summaries(
            report.context_matches,
            current_context_key=report.response_context_key,
        )
        if (
            effective_lap_number is not None
            or effective_window_start_lap is not None
            or parsed.phase is not None
            or region_scope_requested
        ):
            query_context_matches = ()
            query_context_blockers = (
                "Exact-context response memory has no lap-window or driving-phase provenance; "
                "remove that scope or inspect a current-run telemetry answer.",
            )
        matches = sorted(
            (
            match
            for match in query_context_matches
            if match.status == "exact_context_match"
            ),
            key=lambda match: (
                match.control_key,
                match.direction_sign,
                match.context_key or "",
                match.source_observation_ids,
            ),
        )
        current_card = (
            report.best_measurement.controlled_test
            if report.best_measurement.kind == "controlled_test"
            else None
        )
        if parsed.control_key is not None:
            matches = [
                match
                for match in matches
                if match.control_key == parsed.control_key
            ]
        elif current_card is not None:
            matches = [
                match
                for match in matches
                if match.control_key == current_card.control_key
                and match.direction_sign == current_card.direction_sign
            ]
        if matches:
            observation_count = sum(
                match.qualified_observation_count for match in matches
            )
            control_keys = sorted({match.control_key for match in matches})
            verdicts = sorted({verdict for match in matches for verdict in match.verdicts})
            answer = (
                f"{observation_count} qualified exact-context controlled observations exist "
                f"for {', '.join(control_keys)}; verdicts: {', '.join(verdicts)}."
            )
            # Response memory does not yet carry an event -> source-run mapping. Raw event
            # identities therefore cannot safely resolve against current-run citations.
            citations = ()
            extra_navigation = tuple(
                NavigationTarget(workspace="dial_in", run_id=run_id)
                for run_id in sorted(
                    {run_id for match in matches for run_id in match.source_run_ids}
                )
            )
            answer += " Open Context Memory for the linked source runs and event provenance."
        else:
            answer = (
                "No qualified exact-context controlled history matches the requested "
                f"{SETUP_CONTROL_SPECS[parsed.control_key].label} control."
                if parsed.control_key is not None
                else "No qualified exact-context controlled history matches this decision."
            )
            memory_blockers = tuple(
                reason
                for match in query_context_matches
                for reason in match.blocker_reasons
            ) or query_context_blockers
            blockers = memory_blockers or (
                "Run and score a valid A/B/A2 test in this exact context.",
            )
    elif intent == "how_reliable":
        calibration = report.calibration
        citations = ()
        if (
            effective_lap_number is not None
            or effective_window_start_lap is not None
            or parsed.phase is not None
            or parsed.control_key is not None
            or region_scope_requested
        ):
            answer = "No calibration record is attributable to this narrower evidence scope."
            blockers = (
                "Remove the lap, phase, or control scope to inspect run-level calibration.",
            )
        elif calibration.status == "available":
            answer = (
                f"The recorded prediction direction was correct in "
                f"{calibration.correct_direction_count} of "
                f"{calibration.evaluated_predictions} evaluated controlled tests. "
                "Current cause ordering remains ordinal, not a probability. Prediction-grade "
                "citations are not modeled in this report."
            )
            blockers = (
                "Open the immutable calibration record before auditing individual prediction grades.",
            )
        else:
            answer = (
                f"Reliability is {report.briefing.confidence_label}, but no calibrated prediction "
                "track record is available. Cause ordering is ordinal, not a probability."
            )
            blockers = (calibration.note,)
    elif intent == "what_would_change_mind":
        plan = report.best_measurement
        mind_change_criteria = tuple(
            criterion
            for criterion in report.mind_change_criteria
            if (
                effective_lap_number is None
                and effective_window_start_lap is None
                and not region_scope_requested
                or bool(criterion.source_event_ids)
                and all(
                    event_id in graph_event_citations
                    for event_id in criterion.source_event_ids
                )
            )
            and (parsed.phase is None or criterion.phase == parsed.phase)
            and (
                parsed.control_key is None
                or criterion.control_key == parsed.control_key
            )
        )
        citations = tuple(
            citation
            for cause in report.competing_causes
            if cause.state in {"leading", "possible", "unresolved"}
            for citation in (
                *resolved_cause_citations(cause),
                *resolved_cause_citations(cause, contradicting=True),
            )
        )
        cause_labels = {
            cause.cause_id: cause.label for cause in report.competing_causes
        }
        if mind_change_criteria:
            rendered: list[str] = []
            for criterion in mind_change_criteria:
                evidence_minimum = criterion.minimum_evidence
                if criterion.requires_aba2:
                    evidence_minimum += (
                        f" This requires A/B/A2 with at least "
                        f"{criterion.minimum_laps_per_stage} eligible laps per stage."
                    )
                countereffects = (
                    " Countereffects: " + "; ".join(criterion.countereffects) + "."
                    if criterion.countereffects
                    else ""
                )
                if criterion.evidence_kind == "controlled_test":
                    rendered.append(
                        f"For {cause_labels[criterion.cause_id]} "
                        f"({criterion.cause_id}), measure {criterion.metric} in "
                        f"{criterion.phase}. Accept when "
                        f"{'; '.join(criterion.acceptance_conditions)}. Falsify when "
                        f"{'; '.join(criterion.falsification_conditions)}. Minimum evidence: "
                        f"{evidence_minimum} Accepted -> {criterion.next_state_if_accepted}; "
                        f"falsified -> {criterion.next_state_if_falsified}; inconclusive or "
                        f"invalid -> {criterion.next_state_if_inconclusive}.{countereffects}"
                    )
                else:
                    rendered.append(
                        f"For {cause_labels[criterion.cause_id]} "
                        f"({criterion.cause_id}), collect {criterion.metric} in "
                        f"{criterion.phase}. Collection is complete when "
                        f"{'; '.join(criterion.acceptance_conditions)}. It is incomplete when "
                        f"{'; '.join(criterion.falsification_conditions)}. Minimum evidence: "
                        f"{evidence_minimum} Completion -> "
                        f"{criterion.next_state_if_accepted}; incomplete or inconclusive -> "
                        f"{criterion.next_state_if_inconclusive}. This producer declared no "
                        f"causal opposite, so this collection contract cannot rule the cause "
                        f"out.{countereffects}"
                    )
            answer = " ".join(rendered)
        else:
            answer = (
                "No structured mind-change criterion is qualified in this exact evidence "
                "scope."
            )
            blockers = plan.blocker_reasons or (
                "Run the producer-owned measurement plan with its exact acceptance contract.",
            )
    else:
        quality = report.data_quality
        if (
            effective_lap_number is None
            and effective_window_start_lap is None
            and not region_scope_requested
        ):
            answer = (
                f"Data quality is {quality.status}: {quality.eligible_lap_count} of "
                f"{quality.total_lap_count} laps are eligible and {quality.trusted_event_count} "
                "events are trusted."
            )
            citations = tuple(
                citation for citation in quality.citations if in_query_scope(citation)
            )
            blockers = quality.issues
        elif region_scope_requested:
            selected_events = tuple(graph_event_citations.values())
            citations = selected_events
            selected_status = (
                "ready" if selected_events and quality.status == "ready" else "limited"
            )
            answer = (
                f"Region data quality is {selected_status}: {len(selected_events)} trusted "
                "position-resolved events are linked to this region."
            )
            blockers = _unique_text(
                (
                    *(("No provenance-complete tuning event is linked to this region.",) if not selected_events else ()),
                    *(quality.issues if quality.status != "ready" else ()),
                )
            )
        elif (
            effective_window_start_lap is not None
            and effective_window_end_lap is not None
        ):
            window_laps = tuple(
                node
                for node in report.evidence_graph.nodes
                if node.kind is EvidenceNodeKind.LAP
                and node.citation is not None
                and node.citation.run_id == report.run_id
                and node.citation.lap_number is not None
                and effective_window_start_lap
                <= node.citation.lap_number
                <= effective_window_end_lap
            )
            eligible_window_laps = tuple(node for node in window_laps if node.qualified)
            selected_events = tuple(graph_event_citations.values())
            selected_status = (
                "ready"
                if window_laps
                and len(eligible_window_laps) == len(window_laps)
                and selected_events
                and quality.status == "ready"
                else "limited"
            )
            answer = (
                f"Selected lap window {effective_window_start_lap}-"
                f"{effective_window_end_lap} data quality is {selected_status}: "
                f"{len(eligible_window_laps)} of {len(window_laps)} recorded laps are "
                f"eligible and {len(selected_events)} trusted events are linked to the window."
            )
            citations = (
                *(node.citation for node in window_laps if node.citation is not None),
                *selected_events,
            )
            blockers = _unique_text(
                [
                    *(
                        reason
                        for node in window_laps
                        if not node.qualified
                        for reason in node.blocker_reasons
                    ),
                    *(
                        ("No provenance-complete tuning event is linked to the selected window.",)
                        if not selected_events
                        else ()
                    ),
                    *(quality.issues if quality.status != "ready" else ()),
                ]
            )
        else:
            lap_node_id = f"lap:{report.run_id}:{effective_lap_number}"
            lap_node = next(
                (
                    node
                    for node in report.evidence_graph.nodes
                    if node.node_id == lap_node_id and node.kind is EvidenceNodeKind.LAP
                ),
                None,
            )
            selected_events = tuple(graph_event_citations.values())
            if lap_node is None:
                answer = f"No evidence record exists for selected lap {effective_lap_number}."
                blockers = (
                    "Select an imported lap with a canonical eligibility record.",
                )
            elif not lap_node.qualified:
                answer = f"Selected lap {effective_lap_number} is blocked for setup conclusions."
                citations = (lap_node.citation,) if lap_node.citation is not None else ()
                blockers = lap_node.blocker_reasons
            else:
                selected_status = (
                    "ready"
                    if selected_events and quality.status == "ready"
                    else "limited"
                )
                answer = (
                    f"Selected lap {effective_lap_number} data quality is {selected_status}: "
                    f"{len(selected_events)} trusted events are linked to this eligible lap."
                )
                citations = selected_events
                if not selected_events:
                    blockers = (
                        "No provenance-complete tuning event is linked to the selected lap.",
                    )
                elif quality.status != "ready":
                    blockers = quality.issues

    citations = tuple(dict.fromkeys(citations))
    if parsed.track_region_label is not None:
        if citations:
            answer = f"{parsed.track_region_label} scope: {answer}"
        elif not any(parsed.track_region_label in reason for reason in blockers):
            blockers = _unique_text(
                (
                    *blockers,
                    f"No qualified position-resolved evidence belongs to {parsed.track_region_label}.",
                )
            )
    navigation = list(_navigation(citations))
    for target in extra_navigation:
        if target not in navigation:
            navigation.append(target)
    return GroundedQueryResult(
        supported=True,
        intent=intent,
        answer=answer,
        citations=citations,
        suggested_navigation=tuple(navigation),
        mind_change_criteria=mind_change_criteria,
        interpreted_lap_number=effective_lap_number,
        interpreted_window_start_lap=effective_window_start_lap,
        interpreted_window_end_lap=effective_window_end_lap,
        interpreted_window_representative_lap=(
            selected_window_representative_lap
            if selected_window_complete and selected_window_ordered
            else None
        ),
        interpreted_phase=parsed.phase,
        interpreted_control_key=parsed.control_key,
        interpreted_track_region_id=parsed.track_region_id,
        interpreted_track_region_label=parsed.track_region_label,
        action_authorized=action_authorized,
        action_source_event_ids=action_source_event_ids,
        blocker_reasons=_unique_text(blockers),
    )


__all__ = [
    "answer_grounded_query",
    "assess_data_quality",
    "build_evidence_graph",
    "build_internal_intelligence_report",
    "build_reasoning_snapshot",
    "evaluate_measurement_candidates",
    "plan_best_next_measurement",
    "rank_competing_causes",
    "summarize_response_memory",
    "summarize_stored_response_memory",
]
