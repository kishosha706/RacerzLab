"""Typed contracts for evidence-grounded internal intelligence.

These models deliberately separate inspectable evidence from setup authorization.
They contain no language-model state and no calibrated probabilities.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.analysis.test_director import ControlledTestCard, MeasurementMission
from racelab_engine.models.engineering_awareness import MechanismEpisode
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.experiment import MeasurementMissionContract
from racelab_engine.models.lap_engineering_context import LapEngineeringContextReport
from racelab_engine.models.observation_intelligence import (
    DriverRepeatabilitySignature,
    MechanismObservationReport,
    OpportunitySignatureReport,
    SameSetupAnomalyReport,
)
from racelab_engine.models.session_intelligence import (
    ComparabilityDebt,
    HypothesisLifecycle,
    SessionEngineeringLedger,
)
from racelab_engine.models.smart_guidance import MeasurementPriority, SmartGuidance
from racelab_engine.models.telemetry_health import TelemetryHealthBaselineReport

_QUALIFIED_EVIDENCE_STATES = frozenset(
    {
        EvidenceState.MEASURED,
        EvidenceState.CALCULATED,
        EvidenceState.ESTIMATED_PROXY,
        EvidenceState.OBSERVED_CORRELATION,
        EvidenceState.CONTROLLED_TEST_EFFECT,
    }
)


class IntelligenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EvidenceNodeKind(str, Enum):
    CLAIM = "claim"
    CAUSE = "cause"
    OBSERVATION = "observation"
    EVENT = "event"
    LAP = "lap"
    CHANNEL = "channel"
    SETUP = "setup"
    WORKFLOW = "workflow"


class EvidenceEdgeKind(str, Enum):
    SUPPORTED_BY = "supported_by"
    CONTRADICTED_BY = "contradicted_by"
    OBSERVED_ON = "observed_on"
    USES_CHANNEL = "uses_channel"
    RELATES_TO_SETUP = "relates_to_setup"
    PART_OF_WORKFLOW = "part_of_workflow"
    TESTS_SETUP = "tests_setup"


class EvidenceCitation(IntelligenceModel):
    citation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lap_number: int | None = None
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
    lap_pct_peak: float | None = Field(default=None, ge=0.0, le=100.0, allow_inf_nan=False)
    event_id: str | None = None
    workspace: Literal["overview", "laps", "platform", "setup", "dial_in"]
    phase: Literal["braking", "entry", "center", "exit", "straight"] | None = None
    channels: tuple[str, ...] = ()
    evidence_state: EvidenceState
    valid_for_tuning: bool = False
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def tuning_citations_require_complete_provenance(self) -> EvidenceCitation:
        if (
            any(not channel for channel in self.channels)
            or len(set(self.channels)) != len(self.channels)
            or (self.event_id is not None and not self.event_id)
        ):
            raise ValueError("citation channel and event identities must be non-empty and unique")
        if self.valid_for_tuning and (
            not self.event_id
            or self.lap_number is None
            or not self.channels
            or self.evidence_state not in _QUALIFIED_EVIDENCE_STATES
        ):
            raise ValueError(
                "tuning-valid citations require an event, eligible lap, channels, and evidence"
            )
        return self


class EvidenceNode(IntelligenceModel):
    node_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    kind: EvidenceNodeKind
    label: str = Field(min_length=1)
    evidence_state: EvidenceState
    qualified: bool = False
    blocker_reasons: tuple[str, ...] = ()
    citation: EvidenceCitation | None = None
    authorization_fingerprint: str | None = None

    @model_validator(mode="after")
    def qualified_nodes_cannot_carry_blockers(self) -> EvidenceNode:
        if self.qualified and self.blocker_reasons:
            raise ValueError("qualified evidence nodes cannot carry blockers")
        if self.qualified and self.evidence_state not in _QUALIFIED_EVIDENCE_STATES:
            raise ValueError("qualified nodes require a canonical qualified evidence state")
        if self.qualified and self.kind is EvidenceNodeKind.EVENT and (
            self.citation is None or not self.citation.valid_for_tuning
        ):
            raise ValueError("qualified event nodes require a tuning-valid citation")
        if self.authorization_fingerprint is not None and (
            self.kind is not EvidenceNodeKind.SETUP
            or not self.qualified
            or len(self.authorization_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in self.authorization_fingerprint)
        ):
            raise ValueError(
                "setup authorization fingerprints require qualified setup evidence"
            )
        return self


class EvidenceEdge(IntelligenceModel):
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    kind: EvidenceEdgeKind
    qualified: bool = False


class EvidenceGraph(IntelligenceModel):
    nodes: tuple[EvidenceNode, ...]
    edges: tuple[EvidenceEdge, ...]
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identities_and_edges_are_unambiguous(self) -> EvidenceGraph:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("evidence graph node_id values must be unique")
        event_nodes = [node for node in self.nodes if node.kind is EvidenceNodeKind.EVENT]
        event_entity_ids = [node.entity_id for node in event_nodes]
        if len(event_entity_ids) != len(set(event_entity_ids)):
            raise ValueError("evidence graph event identities must be unique")
        citation_event_ids = [
            node.citation.event_id
            for node in event_nodes
            if node.citation is not None and node.citation.event_id is not None
        ]
        if len(citation_event_ids) != len(set(citation_event_ids)):
            raise ValueError("evidence graph citation event identities must be unique")
        edge_ids = [
            (edge.source_node_id, edge.target_node_id, edge.kind) for edge in self.edges
        ]
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("evidence graph semantic edge identities must be unique")
        nodes_by_id = {node.node_id: node for node in self.nodes}
        for node in event_nodes:
            if node.node_id != f"event:{node.entity_id}":
                raise ValueError("event node identity must match its entity identity")
            if node.citation is not None and node.citation.event_id != node.entity_id:
                raise ValueError("event citation identity must match its event node")
        for node in self.nodes:
            if node.node_id != f"{node.kind.value}:{node.entity_id}":
                raise ValueError("evidence node identity prefix must match its declared kind")
        allowed_endpoint_kinds = {
            EvidenceEdgeKind.SUPPORTED_BY: {
                (EvidenceNodeKind.CLAIM, EvidenceNodeKind.EVENT),
                (EvidenceNodeKind.CAUSE, EvidenceNodeKind.EVENT),
                (EvidenceNodeKind.CAUSE, EvidenceNodeKind.OBSERVATION),
                (EvidenceNodeKind.CAUSE, EvidenceNodeKind.WORKFLOW),
                (EvidenceNodeKind.CLAIM, EvidenceNodeKind.WORKFLOW),
                (EvidenceNodeKind.WORKFLOW, EvidenceNodeKind.EVENT),
                (EvidenceNodeKind.SETUP, EvidenceNodeKind.EVENT),
            },
            EvidenceEdgeKind.CONTRADICTED_BY: {
                (EvidenceNodeKind.CLAIM, EvidenceNodeKind.EVENT),
                (EvidenceNodeKind.CAUSE, EvidenceNodeKind.EVENT),
                (EvidenceNodeKind.CAUSE, EvidenceNodeKind.OBSERVATION),
                (EvidenceNodeKind.CAUSE, EvidenceNodeKind.WORKFLOW),
            },
            EvidenceEdgeKind.OBSERVED_ON: {
                (EvidenceNodeKind.EVENT, EvidenceNodeKind.LAP),
                (EvidenceNodeKind.OBSERVATION, EvidenceNodeKind.LAP),
                (EvidenceNodeKind.CLAIM, EvidenceNodeKind.LAP),
            },
            EvidenceEdgeKind.USES_CHANNEL: {
                (EvidenceNodeKind.EVENT, EvidenceNodeKind.CHANNEL),
                (EvidenceNodeKind.OBSERVATION, EvidenceNodeKind.CHANNEL),
                (EvidenceNodeKind.CLAIM, EvidenceNodeKind.CHANNEL),
            },
            EvidenceEdgeKind.RELATES_TO_SETUP: {
                (EvidenceNodeKind.EVENT, EvidenceNodeKind.SETUP),
                (EvidenceNodeKind.CLAIM, EvidenceNodeKind.SETUP),
            },
            EvidenceEdgeKind.PART_OF_WORKFLOW: {
                (EvidenceNodeKind.WORKFLOW, EvidenceNodeKind.LAP),
                (EvidenceNodeKind.SETUP, EvidenceNodeKind.WORKFLOW),
            },
            EvidenceEdgeKind.TESTS_SETUP: {
                (EvidenceNodeKind.WORKFLOW, EvidenceNodeKind.SETUP),
            },
        }
        for edge in self.edges:
            if edge.source_node_id not in nodes_by_id or edge.target_node_id not in nodes_by_id:
                raise ValueError("evidence graph edges require existing endpoint nodes")
            endpoint_kinds = (
                nodes_by_id[edge.source_node_id].kind,
                nodes_by_id[edge.target_node_id].kind,
            )
            if endpoint_kinds not in allowed_endpoint_kinds[edge.kind]:
                raise ValueError("evidence graph edge kind does not match its endpoint kinds")
            if edge.qualified and (
                not nodes_by_id[edge.source_node_id].qualified
                or not nodes_by_id[edge.target_node_id].qualified
            ):
                raise ValueError("qualified edges require two qualified endpoint nodes")
        qualified_edges = {
            (edge.source_node_id, edge.target_node_id, edge.kind)
            for edge in self.edges
            if edge.qualified
        }
        for node in event_nodes:
            if not node.qualified:
                continue
            assert node.citation is not None
            assert node.citation.lap_number is not None
            lap_node_id = f"lap:{node.citation.run_id}:{node.citation.lap_number}"
            lap_node = nodes_by_id.get(lap_node_id)
            if (
                lap_node is None
                or lap_node.kind is not EvidenceNodeKind.LAP
                or not lap_node.qualified
                or (
                    node.node_id,
                    lap_node_id,
                    EvidenceEdgeKind.OBSERVED_ON,
                )
                not in qualified_edges
            ):
                raise ValueError(
                    "qualified events require a qualified observed-on eligible-lap edge"
                )
            for channel in node.citation.channels:
                channel_node_id = f"channel:{channel}"
                channel_node = nodes_by_id.get(channel_node_id)
                if (
                    channel_node is None
                    or channel_node.kind is not EvidenceNodeKind.CHANNEL
                    or not channel_node.qualified
                    or (
                        node.node_id,
                        channel_node_id,
                        EvidenceEdgeKind.USES_CHANNEL,
                    )
                    not in qualified_edges
                ):
                    raise ValueError(
                        "qualified events require qualified source-channel edges"
                    )
        for node in self.nodes:
            if node.authorization_fingerprint is None:
                continue
            linked_events = {
                source_node_id
                for source_node_id, target_node_id, kind in qualified_edges
                if target_node_id == node.node_id
                and kind is EvidenceEdgeKind.RELATES_TO_SETUP
                and nodes_by_id[source_node_id].kind is EvidenceNodeKind.EVENT
            }
            if not linked_events or not any(
                (
                    node.node_id,
                    event_node_id,
                    EvidenceEdgeKind.SUPPORTED_BY,
                )
                in qualified_edges
                for event_node_id in linked_events
            ):
                raise ValueError(
                    "setup authorization requires bidirectional qualified event provenance"
                )
        return self


class LapReference(IntelligenceModel):
    run_id: str = Field(min_length=1)
    lap_number: int


class GroundedClaim(IntelligenceModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_state: EvidenceState
    supporting_event_ids: tuple[str, ...] = ()
    contradicting_event_ids: tuple[str, ...] = ()
    lap_references: tuple[LapReference, ...] = ()
    source_channels: tuple[str, ...] = ()
    setup_keys: tuple[str, ...] = ()
    workflow_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()


class SetupEvidenceValue(IntelligenceModel):
    setup_key: str = Field(min_length=1)
    value_display: str | None = None
    current_value_raw: Any = None
    proposed_value_raw: Any = None
    proposed_value_provenance: tuple[str, ...] = ()
    source_event_ids: tuple[str, ...] = ()
    workflow_ids: tuple[str, ...] = ()
    authorization_basis: Literal[
        "repository_revalidated_legal_option",
        "scored_controlled_workflow",
    ] | None = None


class CauseDiscriminator(IntelligenceModel):
    discriminator_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    target_phase: str = Field(min_length=1)
    acceptance_thresholds: tuple[str, ...] = Field(min_length=1)
    distinguishes_cause_ids: tuple[str, ...] = Field(min_length=1)
    source_event_ids: tuple[str, ...] = ()


class MechanismClaimOutcome(IntelligenceModel):
    """What a controlled result is allowed to say about the diagnosed mechanism."""

    workflow_id: str = Field(min_length=1)
    state: Literal["supported", "weakened", "unchanged", "inconclusive", "invalid"]
    diagnostic_validity: Literal["mechanism_diagnostic", "control_response_only"]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def control_only_results_cannot_change_mechanism_truth(self) -> MechanismClaimOutcome:
        if (
            self.diagnostic_validity == "control_response_only"
            and self.state not in {"unchanged", "inconclusive", "invalid"}
        ):
            raise ValueError("control-response-only evidence cannot change mechanism truth")
        return self


class ControlResponseOutcome(IntelligenceModel):
    """Observed response of one exact setup control, separate from mechanism truth."""

    workflow_id: str = Field(min_length=1)
    result: Literal["matched", "missed", "inconclusive", "unavailable", "invalid"]
    metric: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    control_key: str | None = None
    reason: str = Field(min_length=1)


class PolicyAcceptabilityOutcome(IntelligenceModel):
    """Whether the total controlled result should be kept, undone, or retested."""

    workflow_id: str = Field(min_length=1)
    verdict: Literal["keep", "undo", "retest", "invalid"]
    acceptable: bool | None
    countereffects: tuple[str, ...] = ()
    reason: str = Field(min_length=1)


class ControlledOutcomeAssessment(IntelligenceModel):
    workflow_id: str = Field(min_length=1)
    mechanism: MechanismClaimOutcome
    control_response: ControlResponseOutcome
    policy: PolicyAcceptabilityOutcome

    @model_validator(mode="after")
    def axes_share_one_workflow(self) -> ControlledOutcomeAssessment:
        if {
            self.workflow_id,
            self.mechanism.workflow_id,
            self.control_response.workflow_id,
            self.policy.workflow_id,
        } != {self.workflow_id}:
            raise ValueError("controlled outcome axes must share one workflow identity")
        return self


class ControlledCauseOutcome(IntelligenceModel):
    """Compatibility certificate for one protocol-validated A/B/A2 result.

    ``outcome`` is mechanism evidence only when ``diagnostic_validity`` explicitly
    declares a producer-owned diagnostic intervention. Ordinary setup-control
    tests are control-response evidence and cannot falsify the mechanism.
    """

    workflow_id: str = Field(min_length=1)
    outcome: Literal["supported", "contradicted", "inconclusive", "invalid"]
    verdict: Literal["keep", "undo", "retest", "invalid"]
    source_run_id: str = Field(min_length=1)
    stage_run_ids: tuple[str, ...] = ()
    eligible_lap_ids: tuple[str, ...] = ()
    metric: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    actual_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    time_origin_phase: str | None = None
    time_origin_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    downstream_carry_effect_s: float | None = Field(default=None, allow_inf_nan=False)
    control_key: str | None = None
    countereffects: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    diagnostic_validity: Literal["mechanism_diagnostic", "control_response_only"] = (
        "control_response_only"
    )
    control_direction_result: Literal[
        "matched", "missed", "inconclusive", "unavailable", "invalid"
    ] | None = None

    @model_validator(mode="after")
    def exact_controlled_outcome_is_complete(self) -> ControlledCauseOutcome:
        for values, label in (
            (self.stage_run_ids, "stage run"),
            (self.eligible_lap_ids, "eligible lap"),
            (self.countereffects, "countereffect"),
            (self.blocker_reasons, "blocker"),
        ):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError(f"controlled-outcome {label} values must be non-empty and unique")
        if self.outcome == "invalid":
            if self.verdict != "invalid" or not self.blocker_reasons:
                raise ValueError("invalid controlled outcomes require an invalid verdict and blockers")
        elif (
            self.verdict == "invalid"
            or self.blocker_reasons
            or len(self.stage_run_ids) != 3
            or len(self.eligible_lap_ids) < 9
        ):
            raise ValueError(
                "usable controlled outcomes require exact A/B/A2 runs and nine eligible laps"
            )
        if self.diagnostic_validity == "control_response_only" and self.outcome in {
            "supported",
            "contradicted",
        }:
            raise ValueError(
                "control-response-only outcomes cannot support or contradict mechanism truth"
            )
        if self.outcome != "invalid" and self.control_direction_result is None:
            raise ValueError("usable controlled outcomes require an explicit control response")
        if self.outcome == "invalid" and self.control_direction_result not in {None, "invalid"}:
            raise ValueError("invalid controlled outcomes cannot publish a usable response")
        if (self.time_origin_phase is None) != (self.time_origin_pct is None):
            raise ValueError("controlled outcomes require paired time-origin phase and position")
        if self.outcome == "invalid" and any(
            value is not None
            for value in (
                self.actual_effect_s,
                self.time_origin_phase,
                self.time_origin_pct,
                self.downstream_carry_effect_s,
            )
        ):
            raise ValueError("invalid controlled outcomes cannot publish performance memory")
        if self.actual_effect_s is None and any(
            value is not None
            for value in (
                self.time_origin_phase,
                self.time_origin_pct,
                self.downstream_carry_effect_s,
            )
        ):
            raise ValueError("controlled origin/carry requires a measured phase effect")
        return self


class CauseHypothesis(IntelligenceModel):
    cause_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    mechanism_key: str = Field(default="unresolved", min_length=1)
    mechanism_keys: tuple[str, ...] = ()
    related_control_keys: tuple[str, ...] = ()
    supporting_event_ids: tuple[str, ...] = ()
    contradicting_event_ids: tuple[str, ...] = ()
    supporting_observation_ids: tuple[str, ...] = ()
    contradicting_observation_ids: tuple[str, ...] = ()
    contradiction_notes: tuple[str, ...] = ()
    controlled_outcomes: tuple[ControlledCauseOutcome, ...] = ()
    required_evidence: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    discriminator: CauseDiscriminator | None = None

    @model_validator(mode="after")
    def hypothesis_evidence_is_unambiguous(self) -> CauseHypothesis:
        if not self.mechanism_keys:
            object.__setattr__(self, "mechanism_keys", (self.mechanism_key,))
        if (
            self.mechanism_key not in self.mechanism_keys
            or any(not value for value in self.mechanism_keys)
            or len(self.mechanism_keys) != len(set(self.mechanism_keys))
        ):
            raise ValueError("cause mechanism identities must be unique")
        for values, label in (
            (self.related_control_keys, "related control"),
            (self.supporting_event_ids, "supporting event"),
            (self.contradicting_event_ids, "contradicting event"),
            (self.supporting_observation_ids, "supporting observation"),
            (self.contradicting_observation_ids, "contradicting observation"),
            (self.contradiction_notes, "contradiction note"),
        ):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError(f"cause {label} identities must be non-empty and unique")
        workflow_ids = [outcome.workflow_id for outcome in self.controlled_outcomes]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("one controlled workflow may contribute only one cause outcome")
        return self


class EvidenceIndependenceCluster(IntelligenceModel):
    """Repeated correlated laps grouped into one causal-independence unit."""

    cluster_id: str = Field(min_length=1)
    cause_id: str = Field(min_length=1)
    polarity: Literal["support", "contradiction"]
    run_id: str = Field(min_length=1)
    phase: str | None = None
    lap_numbers: tuple[int, ...] = Field(min_length=1)
    citation_ids: tuple[str, ...] = Field(min_length=1)
    lap_pct_start: float | None = Field(default=None, ge=0.0, le=100.0)
    lap_pct_end: float | None = Field(default=None, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def cluster_scope_is_canonical(self) -> EvidenceIndependenceCluster:
        if len(set(self.lap_numbers)) != len(self.lap_numbers):
            raise ValueError("evidence-cluster lap identities must be unique")
        if len(set(self.citation_ids)) != len(self.citation_ids):
            raise ValueError("evidence-cluster citation identities must be unique")
        if (self.lap_pct_start is None) != (self.lap_pct_end is None):
            raise ValueError("evidence-cluster physical-window bounds are paired")
        if (
            self.lap_pct_start is not None
            and self.lap_pct_end is not None
            and self.lap_pct_end < self.lap_pct_start
        ):
            raise ValueError("evidence-cluster physical windows must be ordered")
        return self


class RankedCause(IntelligenceModel):
    cause_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    mechanism_key: str = Field(default="unresolved", min_length=1)
    mechanism_keys: tuple[str, ...] = ()
    related_control_keys: tuple[str, ...] = ()
    status: Literal["likely", "possible", "ruled_out", "unresolved"]
    ordinal_rank: int = Field(ge=1)
    rank_basis: str = Field(min_length=1)
    supporting_evidence: tuple[EvidenceCitation, ...]
    contradicting_evidence: tuple[EvidenceCitation, ...]
    supporting_evidence_unit_count: int = Field(default=0, ge=0)
    contradicting_evidence_unit_count: int = Field(default=0, ge=0)
    supporting_clusters: tuple[EvidenceIndependenceCluster, ...] = ()
    contradicting_clusters: tuple[EvidenceIndependenceCluster, ...] = ()
    controlled_outcomes: tuple[ControlledCauseOutcome, ...] = ()
    controlled_conflict: bool = False
    missing_evidence: tuple[str, ...]
    blocker_reasons: tuple[str, ...]
    discriminator: CauseDiscriminator | None = None

    @model_validator(mode="after")
    def evidence_identities_are_unambiguous(self) -> RankedCause:
        if not self.mechanism_keys:
            object.__setattr__(self, "mechanism_keys", (self.mechanism_key,))
        if (
            self.mechanism_key not in self.mechanism_keys
            or any(not value for value in self.mechanism_keys)
            or len(self.mechanism_keys) != len(set(self.mechanism_keys))
        ):
            raise ValueError("ranked-cause mechanism identities must be unique")
        if (
            any(not key for key in self.related_control_keys)
            or len(self.related_control_keys) != len(set(self.related_control_keys))
        ):
            raise ValueError("ranked-cause related control identities must be unique")
        supporting_ids = [
            citation.event_id or citation.citation_id for citation in self.supporting_evidence
        ]
        contradicting_ids = [
            citation.event_id or citation.citation_id for citation in self.contradicting_evidence
        ]
        if len(supporting_ids) != len(set(supporting_ids)) or len(contradicting_ids) != len(
            set(contradicting_ids)
        ):
            raise ValueError("ranked-cause evidence identities must be unique")
        if set(supporting_ids) & set(contradicting_ids):
            raise ValueError("one citation cannot both support and contradict a ranked cause")
        supporting_units = (
            {cluster.cluster_id for cluster in self.supporting_clusters}
            if self.supporting_clusters
            else {
                (citation.run_id, citation.lap_number)
                for citation in self.supporting_evidence
            }
        )
        contradicting_units = (
            {cluster.cluster_id for cluster in self.contradicting_clusters}
            if self.contradicting_clusters
            else {
                (citation.run_id, citation.lap_number)
                for citation in self.contradicting_evidence
            }
        )
        if self.supporting_evidence_unit_count != len(supporting_units):
            raise ValueError("supporting evidence-unit count must match independence clusters")
        if self.contradicting_evidence_unit_count != len(contradicting_units):
            raise ValueError("contradicting evidence-unit count must match independence clusters")
        workflow_ids = [outcome.workflow_id for outcome in self.controlled_outcomes]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("ranked controlled outcomes require unique workflow identities")
        outcomes = {
            outcome.outcome
            for outcome in self.controlled_outcomes
            if outcome.diagnostic_validity == "mechanism_diagnostic"
        }
        expected_conflict = "supported" in outcomes and "contradicted" in outcomes
        if self.controlled_conflict != expected_conflict:
            raise ValueError("controlled-conflict state must match exact controlled outcomes")
        if self.controlled_conflict and self.status != "unresolved":
            raise ValueError("conflicting controlled outcomes must remain unresolved")
        return self


class InformationPlan(IntelligenceModel):
    kind: Literal[
        "controlled_test",
        "measurement_mission",
        "discriminator",
        "stop_testing",
        "blocked",
    ]
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    setup_authorized: bool = False
    controlled_test: ControlledTestCard | None = None
    measurement_mission: MeasurementMission | None = None
    discriminator: CauseDiscriminator | None = None
    mission_contract: MeasurementMissionContract | None = None
    source_event_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()
    recovery_priority: MeasurementPriority | None = None

    @model_validator(mode="after")
    def require_exactly_the_declared_plan(self) -> InformationPlan:
        attached = sum(
            item is not None
            for item in (self.controlled_test, self.measurement_mission, self.discriminator)
        )
        expected = 0 if self.kind in {"blocked", "stop_testing"} else 1
        if attached != expected:
            raise ValueError("the plan kind must match exactly one attached plan")
        expected_attachment = {
            "controlled_test": self.controlled_test,
            "measurement_mission": self.measurement_mission,
            "discriminator": self.discriminator,
            "stop_testing": None,
            "blocked": None,
        }[self.kind]
        if self.kind not in {"blocked", "stop_testing"} and expected_attachment is None:
            raise ValueError("the plan kind must match its attached plan type")
        if self.kind == "controlled_test":
            if not self.setup_authorized or self.controlled_test is None:
                raise ValueError("only a controlled-test card may authorize a setup change")
            if not self.controlled_test.evidence_event_ids:
                raise ValueError("controlled-test plans require evidence event identities")
            if self.blocker_reasons:
                raise ValueError("authorized controlled-test plans cannot carry blockers")
        elif self.setup_authorized:
            raise ValueError("measurement and discriminator plans cannot authorize setup")
        if self.mission_contract is not None and self.kind not in {
            "measurement_mission",
            "discriminator",
            "stop_testing",
        }:
            raise ValueError("mission contracts attach only to collection plans or their stop decision")
        if self.kind == "stop_testing" and not self.blocker_reasons:
            raise ValueError("stop-testing plans require an explicit reason")
        if self.kind == "blocked" and not self.blocker_reasons:
            raise ValueError("blocked plans require blocker reasons")
        if self.recovery_priority is not None and self.kind != "blocked":
            raise ValueError("only blocked plans may carry a recovery priority")
        return self


class GuardedCounterfactualRange(IntelligenceModel):
    metric: str = Field(min_length=1)
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)
    observed_delta_minimum: float = Field(allow_inf_nan=False)
    observed_delta_maximum: float = Field(allow_inf_nan=False)
    basis: Literal["qualified_exact_context_controlled_history_only"] = (
        "qualified_exact_context_controlled_history_only"
    )
    source_observation_ids: tuple[str, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def ranges_are_ordered(self) -> GuardedCounterfactualRange:
        if self.minimum > self.maximum:
            raise ValueError("counterfactual effect range must be ordered")
        if self.observed_delta_minimum > self.observed_delta_maximum:
            raise ValueError("observed input range must be ordered")
        if (
            any(not observation_id for observation_id in self.source_observation_ids)
            or len(set(self.source_observation_ids)) != len(self.source_observation_ids)
        ):
            raise ValueError("counterfactual ranges require distinct non-empty observation IDs")
        return self


class ResponseMemorySummary(IntelligenceModel):
    context_key: str | None
    status: Literal[
        "exact_context_match",
        "incomplete_context",
        "context_mismatch",
        "no_qualified_history",
        "contradictory_history",
    ]
    control_key: str = Field(min_length=1)
    direction_sign: Literal[-1, 1]
    qualified_observation_count: int = Field(ge=0)
    verdicts: tuple[str, ...] = ()
    observed_setup_envelope: tuple[float, float] | None = None
    counterfactual_range: GuardedCounterfactualRange | None = None
    source_observation_ids: tuple[str, ...] = ()
    source_run_ids: tuple[str, ...] = ()
    evidence_event_ids: tuple[str, ...] = ()
    matching_context: tuple[str, ...] = ()
    mismatches: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def exact_matches_require_history(self) -> ResponseMemorySummary:
        if (
            self.status == "exact_context_match"
            and (
                not self.context_key
                or self.qualified_observation_count == 0
                or not self.verdicts
                or not self.matching_context
                or len(self.source_observation_ids) != self.qualified_observation_count
                or len(self.source_run_ids) != self.qualified_observation_count * 3
                or len(self.evidence_event_ids) < self.qualified_observation_count
            )
        ):
            raise ValueError(
                "an exact-context match requires complete context, history, and provenance"
            )
        if self.counterfactual_range is not None and self.status != "exact_context_match":
            raise ValueError("counterfactual ranges require an exact-context match")
        for values, label in (
            (self.source_observation_ids, "observation"),
            (self.source_run_ids, "run"),
            (self.evidence_event_ids, "event"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"response-memory {label} identities must be non-empty and unique")
        if self.counterfactual_range is not None and not set(
            self.counterfactual_range.source_observation_ids
        ).issubset(self.source_observation_ids):
            raise ValueError("counterfactual observation IDs must resolve in response memory")
        return self


class CapabilityAssessment(IntelligenceModel):
    status: Literal["ready", "limited", "blocked", "unknown"]
    issues: tuple[str, ...] = ()
    recovery_steps: tuple[str, ...] = ()


class DataQualityAssessment(IntelligenceModel):
    status: Literal["ready", "limited", "blocked"]
    eligible_lap_count: int = Field(ge=0)
    total_lap_count: int = Field(ge=0)
    trusted_event_count: int = Field(ge=0)
    scope_run_ids: tuple[str, ...] = ()
    eligible_lap_ids: tuple[str, ...] = ()
    trusted_event_ids: tuple[str, ...] = ()
    issues: tuple[str, ...]
    recovery_steps: tuple[str, ...]
    citations: tuple[EvidenceCitation, ...] = ()

    @model_validator(mode="after")
    def counts_and_status_are_consistent(self) -> DataQualityAssessment:
        if self.eligible_lap_count > self.total_lap_count:
            raise ValueError("eligible laps cannot exceed total laps")
        for values, label in (
            (self.scope_run_ids, "run"),
            (self.eligible_lap_ids, "lap"),
            (self.trusted_event_ids, "event"),
        ):
            if any(not value for value in values) or len(set(values)) != len(values):
                raise ValueError(f"data-quality {label} identities must be non-empty and unique")
        if self.eligible_lap_count != len(self.eligible_lap_ids):
            raise ValueError("eligible lap count must match its qualified lap identities")
        if self.trusted_event_count != len(self.trusted_event_ids):
            raise ValueError("trusted event count must match its qualified event identities")
        if self.status == "ready" and (
            self.eligible_lap_count == 0
            or self.trusted_event_count == 0
            or not self.scope_run_ids
            or self.issues
        ):
            raise ValueError("ready data requires eligible laps, trusted events, and no issues")
        if self.status == "blocked" and not self.recovery_steps:
            raise ValueError("blocked data requires exact recovery steps")
        return self


class ReasoningAuthorityEnvelope(IntelligenceModel):
    level: Literal["observation", "measurement", "controlled_setup", "blocked"]
    setup_authorized: bool = False
    control_key: str | None = None
    source_event_ids: tuple[str, ...] = ()
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def exact_setup_authority_is_structural(self) -> ReasoningAuthorityEnvelope:
        if self.setup_authorized != (self.level == "controlled_setup"):
            raise ValueError("only the controlled-setup envelope may authorize setup")
        if self.setup_authorized and (not self.control_key or not self.source_event_ids):
            raise ValueError("controlled setup authority requires a control and evidence")
        if not self.setup_authorized and self.control_key is not None:
            raise ValueError("non-authoritative reasoning cannot expose a setup control")
        if len(set(self.source_event_ids)) != len(self.source_event_ids):
            raise ValueError("authority-envelope event identities must be unique")
        return self


class ReasoningSnapshot(IntelligenceModel):
    """Canonical backend state consumed by ranking, planning, memory, and UI."""

    run_id: str = Field(min_length=1)
    session_id: str | None = None
    evidence_graph: EvidenceGraph
    causes: tuple[RankedCause, ...]
    evidence_clusters: tuple[EvidenceIndependenceCluster, ...] = ()
    controlled_outcomes: tuple[ControlledOutcomeAssessment, ...] = ()
    measurement_plan: InformationPlan
    data_quality: DataQualityAssessment
    lap_context: LapEngineeringContextReport | None = None
    mechanism_episodes: tuple[MechanismEpisode, ...] = ()
    mechanism_episode_blocker_reasons: tuple[str, ...] = ()
    authority: ReasoningAuthorityEnvelope
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def snapshot_is_one_consistent_reality(self) -> ReasoningSnapshot:
        cause_ids = [cause.cause_id for cause in self.causes]
        if len(set(cause_ids)) != len(cause_ids):
            raise ValueError("reasoning snapshot cause identities must be unique")
        graph_cause_ids = {
            node.entity_id
            for node in self.evidence_graph.nodes
            if node.kind is EvidenceNodeKind.CAUSE
        }
        if set(cause_ids) != graph_cause_ids:
            raise ValueError("reasoning snapshot causes must equal backend graph causes")
        cluster_ids = [cluster.cluster_id for cluster in self.evidence_clusters]
        if len(set(cluster_ids)) != len(cluster_ids):
            raise ValueError("reasoning snapshot evidence clusters must be unique")
        if any(cluster.cause_id not in graph_cause_ids for cluster in self.evidence_clusters):
            raise ValueError("reasoning snapshot clusters must resolve to a cause")
        workflow_ids = [outcome.workflow_id for outcome in self.controlled_outcomes]
        if len(set(workflow_ids)) != len(workflow_ids):
            raise ValueError("one controlled workflow may enter a snapshot only once")
        if self.data_quality.scope_run_ids != (self.run_id,):
            raise ValueError("reasoning snapshot data quality must match the exact run")
        if self.lap_context is not None and self.lap_context.run_id != self.run_id:
            raise ValueError("reasoning snapshot lap context must match the exact run")
        episode_ids = [episode.episode_id for episode in self.mechanism_episodes]
        if len(episode_ids) != len(set(episode_ids)):
            raise ValueError("reasoning snapshot mechanism episodes must be unique")
        if any(episode.run_id != self.run_id for episode in self.mechanism_episodes):
            raise ValueError("reasoning snapshot episodes must match the exact run")
        if len(self.mechanism_episode_blocker_reasons) != len(
            set(self.mechanism_episode_blocker_reasons)
        ):
            raise ValueError("reasoning snapshot episode blockers must be unique")
        if self.authority.setup_authorized != self.measurement_plan.setup_authorized:
            raise ValueError("reasoning snapshot authority must match its measurement plan")
        return self


class IntelligenceAction(IntelligenceModel):
    kind: Literal["controlled_test", "measurement_mission", "discriminator", "no_call"]
    title: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    setup_authorized: bool = False
    control_key: str | None = None
    setup_effect_id: str | None = None
    experiment_factor_id: str | None = None
    direction_sign: Literal[-1, 1] | None = None
    current_value: str | None = None
    proposed_value: str | None = None
    evidence_state: EvidenceState
    source_event_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def setup_values_require_authorization(self) -> IntelligenceAction:
        setup_values = (self.control_key, self.current_value, self.proposed_value)
        semantic_identity = (
            self.setup_effect_id,
            self.experiment_factor_id,
            self.direction_sign,
        )
        if self.setup_authorized:
            if (
                self.kind != "controlled_test"
                or any(value is None for value in setup_values)
                or any(value is None for value in semantic_identity)
            ):
                raise ValueError("authorized actions require one complete controlled setup target")
            if any(not str(value).strip() for value in setup_values):
                raise ValueError("authorized setup targets cannot contain blank values")
            if not self.source_event_ids or self.blocker_reasons:
                raise ValueError("authorized setup actions require evidence and no blockers")
            if self.evidence_state not in {
                *_QUALIFIED_EVIDENCE_STATES,
                EvidenceState.NEEDS_CONFIRMATION,
            }:
                raise ValueError("authorized setup actions require a usable evidence state")
        elif any(value is not None for value in (*setup_values, *semantic_identity)):
            raise ValueError("unauthorized actions cannot expose setup values")
        return self


class IntelligenceBriefing(IntelligenceModel):
    issue: str
    action: IntelligenceAction
    success_check: str
    confidence_label: Literal["supported", "provisional", "limited", "blocked"]
    blocker_reasons: tuple[str, ...] = ()


class PublicCompetingCause(IntelligenceModel):
    cause_id: str
    label: str
    state: Literal["leading", "possible", "ruled_out", "unresolved"]
    rank: int = Field(ge=1)
    evidence_state: EvidenceState
    reason: str
    evidence_for: tuple[EvidenceCitation, ...]
    evidence_against: tuple[EvidenceCitation, ...]
    controlled_outcomes: tuple[ControlledCauseOutcome, ...] = ()
    controlled_conflict: bool = False

    @model_validator(mode="after")
    def controlled_reasoning_provenance_is_consistent(self) -> PublicCompetingCause:
        workflow_ids = [outcome.workflow_id for outcome in self.controlled_outcomes]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("public controlled outcomes require unique workflow identities")
        outcomes = {outcome.outcome for outcome in self.controlled_outcomes}
        expected_conflict = "supported" in outcomes and "contradicted" in outcomes
        if self.controlled_conflict != expected_conflict:
            raise ValueError("public controlled-conflict state must match exact outcomes")
        if self.controlled_conflict and self.state != "unresolved":
            raise ValueError("public controlled conflicts must remain unresolved")
        return self


class MindChangeCriterion(IntelligenceModel):
    """Public-safe deterministic evidence that would change one cause state."""

    criterion_id: str = Field(min_length=1)
    cause_id: str = Field(min_length=1)
    current_state: Literal["leading", "possible", "ruled_out", "unresolved"]
    evidence_kind: Literal["controlled_test", "measurement_mission", "discriminator"]
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    metric: str = Field(min_length=1)
    phase: Literal["braking", "entry", "center", "exit", "straight"]
    control_key: str | None = None
    threshold_source: str = Field(min_length=1)
    acceptance_conditions: tuple[str, ...] = Field(min_length=1)
    falsification_conditions: tuple[str, ...] = Field(min_length=1)
    minimum_independent_evidence_units: int = Field(ge=2)
    minimum_evidence: str = Field(min_length=1)
    requires_aba2: bool = False
    minimum_laps_per_stage: int | None = Field(default=None, ge=3)
    countereffects: tuple[str, ...] = ()
    next_state_if_accepted: Literal["leading", "possible", "ruled_out", "unresolved"]
    next_state_if_falsified: Literal["leading", "possible", "ruled_out", "unresolved"]
    next_state_if_inconclusive: Literal["unresolved"] = "unresolved"
    source_event_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def criterion_is_complete_and_non_authorizing(self) -> MindChangeCriterion:
        for values, label in (
            (self.acceptance_conditions, "acceptance condition"),
            (self.falsification_conditions, "falsification condition"),
            (self.countereffects, "countereffect"),
            (self.source_event_ids, "source event"),
        ):
            if any(not value for value in values) or len(values) != len(set(values)):
                raise ValueError(f"mind-change {label} values must be non-empty and unique")
        if self.requires_aba2:
            if self.minimum_laps_per_stage is None or self.minimum_independent_evidence_units < 9:
                raise ValueError("A/B/A2 criteria require three stages and at least nine laps")
        elif self.minimum_laps_per_stage is not None:
            raise ValueError("only A/B/A2 criteria may declare laps per stage")
        if self.evidence_kind == "controlled_test" and not self.requires_aba2:
            raise ValueError("controlled-test mind-change criteria require exact A/B/A2")
        if self.evidence_kind != "controlled_test" and (
            self.requires_aba2
            or self.next_state_if_accepted != self.current_state
            or self.next_state_if_falsified != "unresolved"
        ):
            raise ValueError(
                "collection-only criteria cannot infer a causal state transition"
            )
        return self


class CalibrationSummary(IntelligenceModel):
    status: Literal["available", "insufficient_history", "unavailable"] = "unavailable"
    evaluated_predictions: int | None = Field(default=None, ge=0)
    correct_direction_count: int | None = Field(default=None, ge=0)
    note: str = "Prediction calibration has not been supplied."

    @model_validator(mode="after")
    def calibrated_counts_stay_honest(self) -> CalibrationSummary:
        if (
            self.correct_direction_count is not None
            and self.evaluated_predictions is not None
            and self.correct_direction_count > self.evaluated_predictions
        ):
            raise ValueError("correct predictions cannot exceed evaluated predictions")
        if self.status == "available" and (
            self.evaluated_predictions is None or self.correct_direction_count is None
        ):
            raise ValueError("available calibration requires observed counts")
        if self.status == "available" and self.evaluated_predictions == 0:
            raise ValueError("available calibration requires at least one evaluated prediction")
        return self


class InternalIntelligenceReport(IntelligenceModel):
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    response_context_key: str | None = None
    status: Literal["ready", "measure", "blocked"]
    briefing: IntelligenceBriefing
    competing_causes: tuple[PublicCompetingCause, ...]
    mind_change_criteria: tuple[MindChangeCriterion, ...] = ()
    best_measurement: InformationPlan
    context_matches: tuple[ResponseMemorySummary, ...]
    calibration: CalibrationSummary
    data_quality: DataQualityAssessment
    evidence_graph: EvidenceGraph
    reasoning_snapshot: ReasoningSnapshot
    lap_context: LapEngineeringContextReport | None = None
    comparability_debt: tuple[ComparabilityDebt, ...] = ()
    narrative: tuple[str, ...]
    suggested_questions: tuple[str, ...]
    smart_guidance: SmartGuidance | None = None
    session_ledger: SessionEngineeringLedger | None = None
    hypothesis_lifecycle: HypothesisLifecycle | None = None
    opportunity_signature: OpportunitySignatureReport | None = None
    mechanism_observations: MechanismObservationReport | None = None
    anomalies: SameSetupAnomalyReport | None = None
    driver_focus: DriverRepeatabilitySignature | None = None
    telemetry_health: TelemetryHealthBaselineReport | None = None
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def mind_change_criteria_match_report_scope(self) -> InternalIntelligenceReport:
        if (
            self.reasoning_snapshot.run_id != self.run_id
            or self.reasoning_snapshot.session_id != self.session_id
            or self.reasoning_snapshot.measurement_plan != self.best_measurement
            or self.reasoning_snapshot.data_quality != self.data_quality
        ):
            raise ValueError("public report scope, plan, and quality must equal its reasoning snapshot")
        snapshot_by_id = {
            cause.cause_id: cause for cause in self.reasoning_snapshot.causes
        }
        expected_states = {
            "likely": "leading",
            "possible": "possible",
            "ruled_out": "ruled_out",
            "unresolved": "unresolved",
        }
        if any(
            cause.cause_id not in snapshot_by_id
            or cause.rank != snapshot_by_id[cause.cause_id].ordinal_rank
            or cause.state != expected_states[snapshot_by_id[cause.cause_id].status]
            for cause in self.competing_causes
        ) or set(snapshot_by_id) != {cause.cause_id for cause in self.competing_causes}:
            raise ValueError("public competing causes must derive from the reasoning snapshot")
        cause_ids = {cause.cause_id for cause in self.competing_causes}
        controlled_outcomes = tuple(
            outcome
            for cause in self.competing_causes
            for outcome in cause.controlled_outcomes
        )
        workflow_ids = [outcome.workflow_id for outcome in controlled_outcomes]
        if len(workflow_ids) != len(set(workflow_ids)):
            raise ValueError("one controlled workflow may affect only one public cause")
        if any(outcome.source_run_id != self.run_id for outcome in controlled_outcomes):
            raise ValueError("public controlled outcomes must match the exact report run")
        criterion_ids = [criterion.criterion_id for criterion in self.mind_change_criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("mind-change criterion identities must be unique")
        if any(
            criterion.cause_id not in cause_ids
            or criterion.run_id != self.run_id
            or criterion.session_id != self.session_id
            for criterion in self.mind_change_criteria
        ):
            raise ValueError("mind-change criteria must match exact report cause and scope")
        return self


class NavigationTarget(IntelligenceModel):
    workspace: Literal["overview", "laps", "platform", "setup", "dial_in"]
    run_id: str
    lap_number: int | None = None
    event_id: str | None = None
    lap_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class GroundedQueryResult(IntelligenceModel):
    supported: bool
    intent: Literal[
        "why_this_call",
        "where_is_loss",
        "what_next",
        "what_evidence",
        "what_was_ruled_out",
        "what_worked_before",
        "what_changed",
        "how_repeatable",
        "driver_focus",
        "what_anomalies",
        "mechanism_evidence",
        "hypothesis_history",
        "recovery_priority",
        "how_reliable",
        "what_would_change_mind",
        "data_quality",
        "component_awareness",
        "unsupported",
    ]
    answer: str
    citations: tuple[EvidenceCitation, ...]
    suggested_navigation: tuple[NavigationTarget, ...]
    mind_change_criteria: tuple[MindChangeCriterion, ...] = ()
    interpreted_lap_number: int | None = Field(default=None, ge=1)
    interpreted_window_start_lap: int | None = Field(default=None, ge=1)
    interpreted_window_end_lap: int | None = Field(default=None, ge=1)
    interpreted_window_representative_lap: int | None = Field(default=None, ge=1)
    interpreted_phase: Literal["braking", "entry", "center", "exit", "straight"] | None = None
    interpreted_control_key: str | None = None
    interpreted_component_id: str | None = None
    interpreted_track_region_id: str | None = None
    interpreted_track_region_label: str | None = None
    clarification_required: bool = False
    action_authorized: bool = False
    action_source_event_ids: tuple[str, ...] = ()
    blocker_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def authorized_query_actions_require_grounding(self) -> GroundedQueryResult:
        if self.interpreted_component_id is not None and (
            not self.interpreted_component_id
            or self.interpreted_component_id.strip() != self.interpreted_component_id
        ):
            raise ValueError("interpreted component identity must be canonical")
        if self.intent == "component_awareness" and self.interpreted_component_id is None:
            raise ValueError(
                "component-awareness answers require an interpreted component identity"
            )
        if (self.interpreted_track_region_id is None) != (
            self.interpreted_track_region_label is None
        ):
            raise ValueError("interpreted track-region identity and label must be supplied together")
        if self.interpreted_track_region_id is not None and (
            not self.interpreted_track_region_id
            or self.interpreted_track_region_id.strip() != self.interpreted_track_region_id
            or not self.interpreted_track_region_label
            or self.interpreted_track_region_label.strip() != self.interpreted_track_region_label
        ):
            raise ValueError("interpreted track-region context must be canonical")
        if (self.interpreted_window_start_lap is None) != (
            self.interpreted_window_end_lap is None
        ):
            raise ValueError("interpreted lap-window bounds must be supplied together")
        if (
            self.interpreted_window_start_lap is not None
            and self.interpreted_window_end_lap is not None
            and self.interpreted_window_start_lap > self.interpreted_window_end_lap
        ):
            raise ValueError("interpreted lap-window bounds must be ordered")
        if self.interpreted_window_representative_lap is not None and (
            self.interpreted_window_start_lap is None
            or self.interpreted_window_end_lap is None
            or not (
                self.interpreted_window_start_lap
                <= self.interpreted_window_representative_lap
                <= self.interpreted_window_end_lap
            )
        ):
            raise ValueError("interpreted representative lap must belong to the lap window")
        if self.clarification_required and self.action_authorized:
            raise ValueError("an ambiguous query cannot authorize an action")
        if self.mind_change_criteria and self.intent != "what_would_change_mind":
            raise ValueError("structured mind-change criteria require the matching query intent")
        if self.clarification_required and self.mind_change_criteria:
            raise ValueError("ambiguous queries cannot publish mind-change criteria")
        if self.action_authorized and (
            self.intent != "what_next"
            or not self.citations
            or any(not citation.valid_for_tuning for citation in self.citations)
        ):
            raise ValueError("query action authorization requires tuning-valid what-next citations")
        cited_event_ids = {
            citation.event_id for citation in self.citations if citation.event_id is not None
        }
        if self.action_authorized and (
            not self.action_source_event_ids
            or any(
                event_id not in cited_event_ids
                for event_id in self.action_source_event_ids
            )
        ):
            raise ValueError("every authorized action source event must be cited")
        return self


__all__ = [
    "CalibrationSummary",
    "CapabilityAssessment",
    "CauseDiscriminator",
    "CauseHypothesis",
    "ControlResponseOutcome",
    "ControlledCauseOutcome",
    "ControlledOutcomeAssessment",
    "DataQualityAssessment",
    "EvidenceCitation",
    "EvidenceEdge",
    "EvidenceEdgeKind",
    "EvidenceGraph",
    "EvidenceIndependenceCluster",
    "EvidenceNode",
    "EvidenceNodeKind",
    "GroundedClaim",
    "GroundedQueryResult",
    "GuardedCounterfactualRange",
    "InformationPlan",
    "IntelligenceAction",
    "IntelligenceBriefing",
    "InternalIntelligenceReport",
    "LapReference",
    "MechanismClaimOutcome",
    "MindChangeCriterion",
    "NavigationTarget",
    "PolicyAcceptabilityOutcome",
    "PublicCompetingCause",
    "RankedCause",
    "ReasoningAuthorityEnvelope",
    "ReasoningSnapshot",
    "ResponseMemorySummary",
    "SetupEvidenceValue",
]
