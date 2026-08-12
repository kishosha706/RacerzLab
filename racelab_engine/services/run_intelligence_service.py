"""Repository-owned orchestration for the deterministic internal engineer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Any, Sequence

from racelab_engine.analysis.lap_eligibility import eligible_laps
from racelab_engine.analysis.calculated_channels import CHANNEL_METADATA
from racelab_engine.analysis.channel_registry import canonical_name
from racelab_engine.analysis.setup_controls import (
    SETUP_CONTROL_SPECS,
    numeric_setup_value,
    setup_control_values_equal,
)
from racelab_engine.analysis.test_director import (
    ControlledTestCard,
    MeasurementMission,
    TestDirectorDecision,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.engineering_memory import (
    DriverPresentationProfile,
    EngineeringNarrativeEntry,
    PredictionCalibrationSummary,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import (
    CalibrationSummary,
    CapabilityAssessment,
    CauseHypothesis,
    ControlledCauseOutcome,
    GroundedClaim,
    InformationPlan,
    InternalIntelligenceReport,
    SetupEvidenceValue,
)
from racelab_engine.models.lap_engineering_context import LapEngineeringContextReport
from racelab_engine.models.session_intelligence import (
    HypothesisLifecycle,
    HypothesisLifecycleEntry,
    HypothesisPolicyIdentity,
)
from racelab_engine.models.observation_intelligence import (
    MechanismObservationReport,
    ObservationStatus,
    RunObservationIntelligence,
)
from racelab_engine.models.smart_guidance import (
    MeasurementBlocker,
    MeasurementCandidate,
    MeasurementPriority,
)
from racelab_engine.models.telemetry_health import TelemetryHealthBaselineReport
from racelab_engine.services.controlled_workflow_service import (
    revalidate_controlled_test_packet,
    validate_p19_workflow_origin,
)
from racelab_engine.services.engineering_memory_service import (
    build_prediction_contract,
    get_driver_presentation_profile_for_run,
    get_prediction_calibration,
    list_engineering_narrative,
)
from racelab_engine.services.experiment_service import bind_durable_experiment_lifecycle
from racelab_engine.services.engineering_awareness_service import (
    EngineeringAwarenessEvidenceBuild,
)
from racelab_engine.services.import_service import (
    build_telemetry_capability_payload,
    read_telemetry_manifest,
    read_telemetry_rows,
)
from racelab_engine.services.intelligence_service import (
    assess_data_quality,
    build_evidence_graph,
    build_internal_intelligence_report,
    plan_best_next_measurement,
    rank_competing_causes,
    summarize_stored_response_memory,
)
from racelab_engine.services.lap_engineering_context_service import (
    load_lap_engineering_context_report,
)
from racelab_engine.services.observation_intelligence_service import (
    build_observation_intelligence_with_awareness,
)
from racelab_engine.services.session_intelligence_service import (
    build_session_intelligence,
    controlled_hypothesis_policy_identity,
    evaluate_durable_hypothesis_repeat,
    evaluate_hypothesis_repeat,
    setup_policy_fingerprint,
)
from racelab_engine.services.session_position_bridge import (
    build_session_position_evidence_result,
)
from racelab_engine.services.session_service import (
    get_session as get_racelab_session,
)
from racelab_engine.services.setup_learning_service import (
    build_setup_response_context,
    surrounding_setup_fingerprint,
)
from racelab_engine.services.smart_guidance_service import build_smart_guidance
from racelab_engine.services.telemetry_health_service import (
    build_telemetry_health_baseline,
)
from racelab_engine.storage.repository import RaceLabRepository

_QUALIFIED_STATES = frozenset({
    EvidenceState.MEASURED,
    EvidenceState.CALCULATED,
    EvidenceState.ESTIMATED_PROXY,
    EvidenceState.OBSERVED_CORRELATION,
    EvidenceState.CONTROLLED_TEST_EFFECT,
})

_CONTEXT_COLUMNS = [
    "lap",
    "lap_number",
    "air_temp",
    "AirTemp",
    "track_temp",
    "TrackTemp",
    "wind_vel",
    "WindVel",
    "fuel_level",
    "FuelLevel",
    "lf_tire_distance_m",
    "rf_tire_distance_m",
    "lr_tire_distance_m",
    "rr_tire_distance_m",
    "player_tire_compound",
    "tire_compound",
    "PlayerTireCompound",
]

_CAUSE_LABELS = {
    "platform": "Platform evidence",
    "platform_balance": "Platform-balance evidence",
    "platform_risk": "Platform-risk evidence",
    "observed_platform_risk_evidence": "Platform-risk evidence",
    "corner_balance": "Corner-balance evidence",
    "cross_weight": "Corner-balance evidence",
    "driver": "Driver-execution evidence",
    "driver_execution": "Driver-execution evidence",
    "tire": "Tire-state evidence",
    "tire_state": "Tire-state evidence",
    "tire_condition": "Tire-state evidence",
    "brake": "Braking evidence",
    "braking": "Braking evidence",
    "throttle": "Throttle-application evidence",
    "traction": "Traction evidence",
    "rotation": "Rotation evidence",
    "stability": "Stability evidence",
    "damping": "Damper evidence",
    "damper": "Damper evidence",
    "shock": "Shock evidence",
    "spring": "Spring evidence",
    "geometry": "Geometry evidence",
    "mechanical_balance": "Mechanical-balance evidence",
    "observed_resistance_scrub_like_behavior_cause_not_established": (
        "Resistance/scrub-like evidence"
    ),
    "observed_telemetry_issue_cause_not_established": "Unresolved telemetry evidence",
}


@dataclass(frozen=True)
class RunIntelligenceBundle:
    report: InternalIntelligenceReport
    narrative_entries: tuple[EngineeringNarrativeEntry, ...]
    calibration: PredictionCalibrationSummary
    driver_profile: DriverPresentationProfile
    awareness: EngineeringAwarenessEvidenceBuild


@dataclass(frozen=True)
class _ObservationMeasurementInputs:
    candidates: tuple[MeasurementCandidate, ...]
    blockers: tuple[MeasurementBlocker, ...]
    available_channels: tuple[str, ...]


def _resolve_session(
    run_id: str,
    session_id: str | None,
    db_path: str | Path | None,
) -> tuple[str | None, tuple[str, ...]]:
    if session_id is not None:
        session = get_racelab_session(session_id, db_path)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")
        if run_id not in session.run_ids:
            raise ValueError(
                f"Run {run_id} is not attached to the requested session {session_id}."
            )
        return session.session_id, tuple(session.run_ids)
    # Session scope is explicit. A sessionless request stays run-only even if
    # that run happens to be attached to one or more saved sessions.
    return None, (run_id,)


def _related_workflows(
    workflows: list[ControlledWorkflow],
    scope_run_ids: tuple[str, ...],
) -> tuple[ControlledWorkflow, ...]:
    scope = set(scope_run_ids)
    return tuple(
        workflow
        for workflow in workflows
        if workflow.source_run_id in scope
        or bool(scope & set(workflow.stage_run_ids.values()))
    )


def _selected_workflow(
    workflows: tuple[ControlledWorkflow, ...],
    run_id: str,
) -> ControlledWorkflow | None:
    active = [
        workflow
        for workflow in workflows
        if workflow.status not in {"scored", "cancelled"}
        and (
            workflow.source_run_id == run_id
            or run_id in workflow.stage_run_ids.values()
        )
    ]
    if len(active) > 1:
        raise ValueError(
            "Multiple active controlled workflows touch this run. Finish or explicitly "
            "abandon all but one before requesting an engineering action."
        )
    return active[0] if active else None


def _require_one_active_workflow_in_explicit_session(
    workflows: tuple[ControlledWorkflow, ...],
    *,
    session_id: str | None,
) -> None:
    if session_id is None:
        return
    active = [
        workflow
        for workflow in workflows
        if workflow.status not in {"scored", "cancelled"}
    ]
    if len(active) > 1:
        raise ValueError(
            "Multiple active controlled workflows exist in this session. Finish or "
            "explicitly abandon all but one before requesting an engineering action."
        )


def _apply_persistence_integrity_blockers(
    quality: Any,
    *blocker_groups: tuple[str, ...],
) -> Any:
    blockers = tuple(dict.fromkeys(
        blocker
        for group in blocker_groups
        for blocker in group
        if blocker
    ))
    if not blockers:
        return quality
    return quality.model_copy(update={
        "status": "blocked",
        "issues": tuple(dict.fromkeys((*quality.issues, *blockers))),
        "recovery_steps": tuple(dict.fromkeys((
            *quality.recovery_steps,
            "Re-import the run or repair the malformed stored evidence before authorizing a setup action.",
        ))),
    })


def _humanize(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("-", " ").split()).title()


def _canonical_cause(value: str) -> tuple[str, str]:
    key = "_".join(
        "".join(character if character.isalnum() else " " for character in value.casefold())
        .split()
    )
    if key in _CAUSE_LABELS:
        return key, _CAUSE_LABELS[key]
    return "unresolved", "Unresolved telemetry evidence"


def _card_semantic_blockers(card: ControlledTestCard) -> tuple[str, ...]:
    required_text = {
        "hypothesis": card.hypothesis,
        "control label": card.control_label,
        "exact change": card.exact_change,
        "change size": card.change_size,
        "target phase": card.target_phase,
        "expected mechanism": card.expected_mechanism,
        "rollback rule": card.rollback_rule,
        "keep rule": card.keep_rule,
        "stop rule": card.stop_rule,
    }
    blockers = [
        f"The stored controlled-test {label} is blank."
        for label, value in required_text.items()
        if not value.strip()
    ]
    if card.current_value is None or (
        isinstance(card.current_value, str) and not card.current_value.strip()
    ):
        blockers.append("The stored controlled test has no current setup value.")
    if card.proposed_value_raw is None or not str(card.proposed_value or "").strip():
        blockers.append("The stored controlled test has no complete proposed setup value.")
    if not card.proposed_value_provenance or any(
        not token.strip() for token in card.proposed_value_provenance
    ):
        blockers.append("The stored controlled test has malformed legal-option provenance.")
    if not card.evidence_event_ids or any(
        not event_id.strip() for event_id in card.evidence_event_ids
    ):
        blockers.append("The stored controlled test has malformed evidence identities.")
    for label, values in (
        ("success metric", card.success_metrics),
        ("do-not-change control", card.do_not_change),
    ):
        if not values or any(not value.strip() for value in values):
            blockers.append(f"The stored controlled test has a blank {label}.")
    if any(
        not stage.setup_instruction.strip() or not stage.purpose.strip()
        for stage in card.stages
    ):
        blockers.append("The stored controlled test has an incomplete A/B/A2 procedure.")
    return tuple(dict.fromkeys(blockers))


def _channel_lineage(channel: str) -> frozenset[str]:
    """Return a calculated channel's exact raw/canonical dependency lineage."""
    pending = [channel]
    lineage: set[str] = set()
    while pending:
        current = pending.pop()
        key = current.strip()
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


def _telemetry_health_card_blockers(
    health: TelemetryHealthBaselineReport | None,
    workflow: ControlledWorkflow | None,
    events: Sequence[Any],
) -> tuple[str, ...]:
    """Withhold only cards whose evidence uses a newly unhealthy channel."""
    if health is None or workflow is None or workflow.packet.primary_test is None:
        return ()
    if health.status == "blocked":
        return (
            "The controlled setup action is withheld because current-run telemetry-health "
            "identity could not be verified; re-import the original .ibt before revalidation.",
        )
    if health.status != "warning" or not health.findings:
        return ()
    card = workflow.packet.primary_test
    event_ids = set(card.evidence_event_ids)
    source_channels = list(workflow.packet.opportunity.source_channels)
    source_channels.extend(
        channel
        for event in events
        if event.event_id in event_ids
        for channel in event.source_channels
    )
    exact_sources = tuple(
        dict.fromkeys(
            channel.strip()
            for channel in source_channels
            if isinstance(channel, str) and channel.strip()
        )
    )
    intersections: list[tuple[str, str, str]] = []
    for finding in health.findings:
        affected = set(_channel_lineage(finding.channel))
        for raw_name in finding.source_raw_names:
            affected.update(_channel_lineage(raw_name))
        for source in exact_sources:
            if affected & set(_channel_lineage(source)):
                intersections.append((finding.kind, finding.channel, source))
    if not intersections:
        return ()
    kinds = ", ".join(sorted({kind.replace("_", " ") for kind, _, _ in intersections}))
    affected_channels = ", ".join(sorted({channel for _, channel, _ in intersections}))
    action_sources = ", ".join(sorted({source for _, _, source in intersections}))
    return (
        "The controlled setup action is withheld because cross-run telemetry health found "
        f"{kinds} on {affected_channels}, intersecting the card's evidence channels "
        f"({action_sources}). Complete the typed re-import or verification-run recovery, "
        "then revalidate the card.",
    )


def _claims(
    workflow: ControlledWorkflow | None,
    card_blockers: tuple[str, ...] = (),
) -> tuple[GroundedClaim, ...]:
    claims: list[GroundedClaim] = []
    if workflow is not None:
        card = workflow.packet.primary_test
        card_label = (
            card.control_label.strip() or _humanize(card.control_key)
            if card is not None
            else ""
        )
        claims.append(GroundedClaim(
            claim_id=f"workflow:{workflow.workflow_id}",
            text=(
                f"Controlled workflow is testing {card_label}."
                if card is not None
                else "Controlled workflow has no authorized setup target."
            ),
            evidence_state=(
                EvidenceState.BLOCKED_BY_CONTEXT
                if card_blockers
                else workflow.packet.evidence_state
            ),
            supporting_event_ids=workflow.packet.opportunity.evidence_event_ids,
            source_channels=workflow.packet.opportunity.source_channels,
            setup_keys=(card.control_key,) if card is not None else (),
            workflow_ids=(workflow.workflow_id,),
            blocker_reasons=tuple(dict.fromkeys([
                *workflow.packet.blockers,
                *card_blockers,
            ])),
        ))
    return tuple(claims)


def _normalized_reasoning_policy_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _workflow_reasoning_policy_signature(
    workflow: ControlledWorkflow | None,
) -> tuple[Any, ...] | None:
    packet = getattr(workflow, "packet", None)
    if (
        workflow is None
        or packet is None
        or getattr(packet, "decision", None) != "test"
        or getattr(packet, "primary_test", None) is None
    ):
        return None
    card = packet.primary_test
    try:
        contract = build_prediction_contract(workflow)
        canonical_symptom = packet.canonical_symptom
        cause_bucket = packet.primary_cause_bucket
        control_key = card.control_key
        direction_sign = card.direction_sign
        countereffects = tuple(card.countereffects)
        expected_direction = contract.expected_direction
        target_metric = contract.target_metric
        target_phase = contract.target_phase
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    values = (
        canonical_symptom,
        cause_bucket,
        control_key,
        target_metric,
        target_phase,
    )
    if any(not _normalized_reasoning_policy_text(value) for value in values):
        return None
    return (
        _normalized_reasoning_policy_text(canonical_symptom),
        _normalized_reasoning_policy_text(cause_bucket),
        _normalized_reasoning_policy_text(control_key),
        direction_sign,
        expected_direction,
        _normalized_reasoning_policy_text(target_metric),
        _normalized_reasoning_policy_text(target_phase),
        tuple(sorted({
            _normalized_reasoning_policy_text(value)
            for value in countereffects
            if _normalized_reasoning_policy_text(value)
        })),
    )


def _lifecycle_reasoning_policy_signature(
    entry: HypothesisLifecycleEntry,
    completed_workflow: ControlledWorkflow | None,
) -> tuple[Any, ...] | None:
    if entry.hypothesis_policy is not None:
        policy = entry.hypothesis_policy
        return (
            policy.canonical_symptom,
            policy.cause_bucket,
            policy.control_key,
            policy.control_direction_sign,
            policy.expected_effect_direction,
            policy.target_metric,
            policy.target_phase,
            policy.countereffects,
    )
    if completed_workflow is None or completed_workflow.packet.primary_test is None:
        return None
    values = (
        completed_workflow.packet.canonical_symptom,
        completed_workflow.packet.primary_cause_bucket,
        entry.control_key,
        entry.target_effect.metric,
        entry.target_effect.phase,
    )
    if any(not _normalized_reasoning_policy_text(value) for value in values):
        return None
    return (
        _normalized_reasoning_policy_text(completed_workflow.packet.canonical_symptom),
        _normalized_reasoning_policy_text(completed_workflow.packet.primary_cause_bucket),
        _normalized_reasoning_policy_text(entry.control_key),
        entry.direction_sign,
        entry.target_effect.expected_direction,
        _normalized_reasoning_policy_text(entry.target_effect.metric),
        _normalized_reasoning_policy_text(entry.target_effect.phase),
        tuple(sorted({
            _normalized_reasoning_policy_text(value)
            for value in entry.countereffects.criteria
            if _normalized_reasoning_policy_text(value)
        })),
    )


def _hypotheses(
    workflow: ControlledWorkflow | None,
    card_blockers: tuple[str, ...] = (),
    *,
    lifecycle: HypothesisLifecycle | None = None,
    workflows: Sequence[ControlledWorkflow] = (),
    current_run_id: str | None = None,
    current_hypothesis_policy: HypothesisPolicyIdentity | None = None,
) -> tuple[CauseHypothesis, ...]:
    raw: list[CauseHypothesis] = []
    if workflow is not None and workflow.packet.primary_test is not None:
        card = workflow.packet.primary_test
        semantic_blockers = tuple(dict.fromkeys([
            *_card_semantic_blockers(card),
            *card_blockers,
        ]))
        cause_key, label = _canonical_cause(
            str(workflow.packet.primary_cause_bucket or "")
        )
        if cause_key == "unresolved":
            cause_key = f"setup_control_{card.control_key}"
            label = f"{_humanize(card.control_key)} response evidence"
        cause_id = f"workflow:{cause_key}"
        raw.append(CauseHypothesis(
            cause_id=cause_id,
            label=label or "Controlled test",
            hypothesis=(
                card.hypothesis.strip()
                or f"Measure whether {label.casefold() or 'the reported symptom'} repeats."
            ),
            mechanism_key=cause_key,
            related_control_keys=(card.control_key,),
            supporting_event_ids=card.evidence_event_ids if not semantic_blockers else (),
            blocker_reasons=tuple(dict.fromkeys([
                *workflow.packet.blockers,
                *semantic_blockers,
            ])),
        ))
    workflow_by_id = {item.workflow_id: item for item in workflows}
    current_policy_signature = _workflow_reasoning_policy_signature(workflow)
    if lifecycle is not None and current_run_id is not None:
        scoped_lifecycle_entries = tuple(
            entry
            for entry in lifecycle.entries
            if entry.protocol.source_run_id == current_run_id
        )
        lifecycle_workflow_counts = {
            entry.workflow_id: sum(
                other.workflow_id == entry.workflow_id
                for other in scoped_lifecycle_entries
            )
            for entry in scoped_lifecycle_entries
        }
        processed_lifecycle_workflow_ids: set[str] = set()
        for entry in scoped_lifecycle_entries:
            if entry.workflow_id in processed_lifecycle_workflow_ids:
                continue
            processed_lifecycle_workflow_ids.add(entry.workflow_id)
            completed_workflow = workflow_by_id.get(entry.workflow_id)
            entry_policy_signature = _lifecycle_reasoning_policy_signature(
                entry,
                completed_workflow,
            )
            completed_policy_signature = _workflow_reasoning_policy_signature(
                completed_workflow
            )
            workflow_cause = (
                str(completed_workflow.packet.primary_cause_bucket or "")
                if completed_workflow is not None
                else ""
            )
            supplied_cause = workflow_cause or str(entry.expected_mechanism or "")
            mechanism_key, label = _canonical_cause(supplied_cause)
            control_key_is_canonical = (
                entry.control_key is None or entry.control_key in SETUP_CONTROL_SPECS
            )
            control_key = entry.control_key if control_key_is_canonical else None
            if mechanism_key == "unresolved" and control_key is not None:
                mechanism_key = f"setup_control_{control_key}"
                label = f"{_humanize(control_key)} response evidence"

            declared_stage_run_ids = (
                entry.protocol.a_run_id,
                entry.protocol.b_run_id,
                entry.protocol.a2_run_id,
            )
            stage_run_ids = tuple(
                run_id
                for run_id in declared_stage_run_ids
                if run_id is not None and run_id.strip()
            )
            declared_lap_ids = tuple(entry.protocol.eligible_lap_ids)
            countereffects = tuple(entry.countereffects.criteria)
            integrity_blockers: list[str] = []
            if lifecycle_workflow_counts[entry.workflow_id] != 1:
                integrity_blockers.append(
                    "The exact controlled workflow appears more than once in the lifecycle."
                )
            if completed_workflow is None:
                integrity_blockers.append(
                    "The controlled lifecycle workflow is unavailable in the current exact session scope."
                )
            elif (
                entry_policy_signature is None
                or completed_policy_signature is None
                or entry_policy_signature != completed_policy_signature
            ):
                integrity_blockers.append(
                    "The controlled lifecycle reasoning policy conflicts with its producer-owned workflow."
                )
            if (
                not entry.protocol.protocol_valid
                or entry.protocol.verdict == "invalid"
                or entry.outcome_classification == "invalid"
            ):
                integrity_blockers.extend(entry.protocol.blocker_reasons)
                integrity_blockers.append(
                    "The controlled lifecycle protocol is invalid and cannot affect cause rank."
                )
            if (
                len(stage_run_ids) != 3
                or len(set(stage_run_ids)) != 3
                or any(run_id != run_id.strip() for run_id in stage_run_ids)
            ):
                integrity_blockers.append(
                    "The controlled lifecycle must identify three distinct canonical A/B/A2 runs."
                )
            if (
                len(declared_lap_ids) < 9
                or any(not lap_id.strip() or lap_id != lap_id.strip() for lap_id in declared_lap_ids)
                or len(set(declared_lap_ids)) != len(declared_lap_ids)
            ):
                integrity_blockers.append(
                    "The controlled lifecycle must identify nine distinct eligible A/B/A2 laps."
                )
            elif len(stage_run_ids) == 3 and any(
                sum(lap_id.startswith(f"{run_id}:") for lap_id in declared_lap_ids) < 3
                for run_id in stage_run_ids
            ):
                integrity_blockers.append(
                    "Each controlled A/B/A2 stage requires three independently eligible laps."
                )
            if not control_key_is_canonical:
                integrity_blockers.append(
                    "The controlled lifecycle setup control is not canonical."
                )
            if mechanism_key == "unresolved" and control_key is None:
                integrity_blockers.append(
                    "The controlled lifecycle has no canonical mechanism or setup control."
                )
            if (
                not entry.target_effect.metric.strip()
                or not entry.target_effect.phase.strip()
            ):
                integrity_blockers.append(
                    "The controlled lifecycle target metric and phase must be explicit."
                )
            if (
                any(not criterion.strip() for criterion in countereffects)
                or len(set(countereffects)) != len(countereffects)
            ):
                integrity_blockers.append(
                    "The controlled lifecycle countereffect criteria must be canonical and unique."
                )

            # An ordinary setup-control A/B/A2 result grades the exact treatment
            # response and policy.  It is not a producer-owned diagnostic
            # intervention and therefore cannot support or falsify mechanism truth.
            derived_outcome = "inconclusive"

            safe_blockers = tuple(dict.fromkeys(integrity_blockers))
            outcome_classification = "invalid" if safe_blockers else derived_outcome
            outcome = ControlledCauseOutcome(
                workflow_id=entry.workflow_id,
                outcome=outcome_classification,
                verdict=("invalid" if safe_blockers else entry.protocol.verdict),
                source_run_id=entry.protocol.source_run_id,
                stage_run_ids=tuple(dict.fromkeys(stage_run_ids)),
                eligible_lap_ids=tuple(
                    dict.fromkeys(
                        lap_id for lap_id in declared_lap_ids if lap_id.strip()
                    )
                ),
                metric=entry.target_effect.metric.strip() or "unresolved_metric",
                phase=entry.target_effect.phase.strip() or "unresolved_phase",
                control_key=control_key,
                countereffects=tuple(
                    dict.fromkeys(
                        criterion for criterion in countereffects if criterion.strip()
                    )
                ),
                blocker_reasons=safe_blockers,
                diagnostic_validity="control_response_only",
                control_direction_result=(
                    "invalid"
                    if safe_blockers
                    else entry.target_effect.direction_result
                ),
            )
            exact_current_policy = bool(
                not safe_blockers
                and workflow is not None
                and current_policy_signature is not None
                and entry_policy_signature == current_policy_signature
                and (
                    current_hypothesis_policy is None
                    and entry.hypothesis_policy is None
                    or current_hypothesis_policy is not None
                    and entry.hypothesis_policy is not None
                    and entry.hypothesis_policy.policy_key
                    == current_hypothesis_policy.policy_key
                )
            )
            matching_index = next(
                (
                    index
                    for index, cause in enumerate(raw)
                    if exact_current_policy
                    and cause.cause_id.startswith("workflow:")
                    and cause.mechanism_key == mechanism_key
                    and control_key is not None
                    and control_key in cause.related_control_keys
                ),
                None,
            )
            if matching_index is None:
                policy_identity = (
                    entry.hypothesis_policy.policy_key
                    if entry.hypothesis_policy is not None
                    else entry.workflow_id
                )
                lifecycle_cause_id = (
                    f"lifecycle:{mechanism_key}:{control_key or 'unresolved'}:{policy_identity}"
                )
                matching_index = next(
                    (
                        index
                        for index, cause in enumerate(raw)
                        if cause.cause_id == lifecycle_cause_id
                    ),
                    None,
                )
                if matching_index is None:
                    raw.append(CauseHypothesis(
                        cause_id=lifecycle_cause_id,
                        label=label or "Controlled outcome evidence",
                        hypothesis=(
                            "Re-evaluate this exact producer-owned symptom, phase, direction, "
                            "metric, control, and countereffect policy against its completed "
                            "controlled outcomes."
                        ),
                        mechanism_key=mechanism_key,
                        related_control_keys=(
                            (control_key,) if control_key is not None else ()
                        ),
                        controlled_outcomes=(outcome,),
                    ))
                    continue
            existing = raw[matching_index]
            raw[matching_index] = existing.model_copy(update={
                "controlled_outcomes": (*existing.controlled_outcomes, outcome),
            })
    # A generic repeatability mission tests only the cause that produced it.
    # Broader discrimination must be declared by a producer that can actually
    # distinguish those causes; orchestration cannot invent that coverage.
    return tuple(raw)


def _observation_hypotheses(
    report: MechanismObservationReport,
) -> tuple[CauseHypothesis, ...]:
    """Promote producer-owned typed observations into non-authorizing causes."""

    hypotheses: list[CauseHypothesis] = []
    for observation in report.observations:
        if not observation.qualified:
            continue
        observation_ids = tuple(
            f"{observation.observation_id}:{index}"
            for index, _citation in enumerate(observation.citations)
        )
        mechanism_key = observation.mechanism.value
        hypotheses.append(CauseHypothesis(
            cause_id=f"observation:{observation.observation_id}",
            label=_humanize(mechanism_key),
            hypothesis=(
                "Determine whether this typed same-setup mechanism observation remains "
                "repeatable under matched fuel, tire, weather, line, and traffic context."
            ),
            mechanism_key=mechanism_key,
            mechanism_keys=tuple(
                item.value
                for item in (
                    getattr(observation, "mechanism_kinds", ())
                    or (observation.mechanism,)
                )
            ),
            supporting_observation_ids=observation_ids,
            contradiction_notes=tuple(observation.contradicting_evidence),
            required_evidence=tuple(observation.required_channels),
            blocker_reasons=tuple(observation.blocker_reasons),
        ))
    return tuple(hypotheses)


def _setup_values(
    workflow: ControlledWorkflow | None,
    card_blockers: tuple[str, ...] = (),
) -> tuple[SetupEvidenceValue, ...]:
    if workflow is None or workflow.packet.primary_test is None:
        return ()
    card = workflow.packet.primary_test
    if _card_semantic_blockers(card) or card_blockers:
        return ()
    return (SetupEvidenceValue(
        setup_key=card.control_key,
        # Exact values belong only to the revalidated authorized action contract.
        value_display=None,
        current_value_raw=card.current_value,
        proposed_value_raw=card.proposed_value_raw,
        proposed_value_provenance=card.proposed_value_provenance,
        source_event_ids=card.evidence_event_ids,
        authorization_basis="repository_revalidated_legal_option",
        # A planned workflow is not yet a controlled effect. The pre-test
        # control relation stands only on its qualified current-run events;
        # legal target authority is revalidated separately from the catalog.
        workflow_ids=(),
    ),)


def _repository_setup_authority_verifier(
    workflow: ControlledWorkflow | None,
    *,
    requested_run_id: str,
    card_blockers: tuple[str, ...],
):
    """Bind graph authority to the packet just rebuilt from repository evidence."""
    def verify(value: SetupEvidenceValue) -> bool:
        if (
            workflow is None
            or workflow.source_run_id != requested_run_id
            or workflow.packet.primary_test is None
            or card_blockers
        ):
            return False
        card = workflow.packet.primary_test
        if _card_semantic_blockers(card):
            return False
        try:
            values_match = bool(
                setup_control_values_equal(
                    card.control_key,
                    value.current_value_raw,
                    card.current_value,
                )
                and setup_control_values_equal(
                    card.control_key,
                    value.proposed_value_raw,
                    card.proposed_value_raw,
                )
            )
        except (TypeError, ValueError, OverflowError):
            return False
        return bool(
            value.authorization_basis == "repository_revalidated_legal_option"
            and value.setup_key == card.control_key
            and values_match
            and tuple(value.proposed_value_provenance)
            == tuple(card.proposed_value_provenance)
            and tuple(value.source_event_ids) == tuple(card.evidence_event_ids)
            and not value.workflow_ids
        )

    return verify


def _capability(
    run_id: str,
    *,
    source_file_sha256: str | None,
) -> CapabilityAssessment:
    try:
        payload = build_telemetry_capability_payload(
            run_id,
            expected_source_file_sha256=source_file_sha256,
        )
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        payload = {}
    summary = payload.get("capability_summary") if isinstance(payload, dict) else None
    if not isinstance(summary, dict):
        return CapabilityAssessment(
            status="unknown",
            issues=("Telemetry capability health is unavailable for this run.",),
            recovery_steps=("Re-import the original telemetry file to rebuild its capability manifest.",),
        )
    issues: list[str] = []
    recovery: list[str] = []
    if summary.get("lossless_archive_complete") is not True:
        issues.append("The lossless telemetry archive is incomplete.")
        recovery.append("Re-import the original telemetry before drawing setup conclusions.")
        status = "blocked"
    elif int(summary.get("warning_channels") or 0) > 0:
        issues.append(f"{int(summary.get('warning_channels') or 0)} archived channels have health warnings.")
        recovery.append("Review the warned source channels used by the selected analysis.")
        status = "limited"
    else:
        status = "ready"
    return CapabilityAssessment(status=status, issues=tuple(issues), recovery_steps=tuple(recovery))


def _controlled_decision(
    workflow: ControlledWorkflow | None,
    card_blockers: tuple[str, ...] = (),
) -> TestDirectorDecision | None:
    if workflow is None:
        return None
    if (
        workflow.packet.primary_test is not None
        and workflow.packet.decision == "test"
        and not _card_semantic_blockers(workflow.packet.primary_test)
        and not card_blockers
    ):
        return TestDirectorDecision(ready=True, card=workflow.packet.primary_test)
    if workflow.packet.measurement_mission is not None:
        return TestDirectorDecision(
            ready=False,
            mission=MeasurementMission(
                purpose=(
                    "Collect repeatable, context-matched telemetry before considering one setup change."
                ),
                procedure=(
                    "Keep the complete setup unchanged for the measurement run.",
                    "Record at least three complete flying laps through the reported target phase.",
                    "Keep fuel, tire state, weather, driving line, and nearby-car context comparable.",
                    "Discard any pit, reset, caution, incident, cooldown, partial, or invalid-speed lap.",
                ),
                required_laps_or_passes=3,
                controlled_variables=(
                    "complete setup snapshot",
                    "fuel range",
                    "tire age and compound",
                    "weather and wind",
                    "driver inputs and line",
                    "nearby-car context",
                ),
                target_phase="reported target phase",
                acceptance_thresholds=(
                    "At least three eligible complete laps",
                    "Matched context and continuous telemetry",
                    "The observed signal repeats beyond normal run variation",
                ),
                stop_rule=(
                    "Stop after any incident, pit entry, reset, setup drift, simulator-integrity "
                    "fault, or unsafe condition."
                ),
                blockers=(
                    "The persisted measurement request does not authorize a setup target.",
                ),
            ),
        )
    return None


def _response_context(
    run_id: str,
    workflow: ControlledWorkflow,
    overview: Any,
) -> Any | None:
    setup = overview.setup_snapshot
    if setup is None:
        return None
    eligible_numbers = {lap.lap_number for lap in eligible_laps(overview.laps)}
    try:
        rows = read_telemetry_rows(run_id, columns=_CONTEXT_COLUMNS)
        identity = read_telemetry_manifest(run_id).get("compatibility_identity") or {}
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return None
    filtered = [
        row
        for row in rows
        if row.get("lap", row.get("lap_number")) in eligible_numbers
    ]
    decision_context = workflow.reproduction_snapshot.get("decision_context") or {}
    objective = str(decision_context.get("objective") or "race-pace")
    priority = str(decision_context.get("priority") or "overall-pace")
    if priority != "overall-pace":
        objective = f"{objective}|priority:{priority}"
    return build_setup_response_context(
        compatibility_identity=identity,
        rows=filtered,
        baseline_setup=setup.model_dump(mode="json"),
        package_archetype=str(
            identity.get("track_configuration_name")
            or identity.get("track_name")
            or "unknown"
        ),
        objective=objective,
    )


def _context_matches(
    run_id: str,
    workflow: ControlledWorkflow | None,
    overview: Any,
    db_path: str | Path | None,
) -> tuple[tuple[Any, ...], str | None]:
    if workflow is None or workflow.packet.primary_test is None or overview.setup_snapshot is None:
        return (), None
    card = workflow.packet.primary_test
    if _card_semantic_blockers(card):
        return (), None
    response_context = _response_context(run_id, workflow, overview)
    if response_context is None:
        return (), None
    setup_payload = overview.setup_snapshot.model_dump(mode="json")
    fingerprint = surrounding_setup_fingerprint(setup_payload, card.control_key)
    if fingerprint is None:
        return (), response_context.key
    current = numeric_setup_value(card.current_value)
    proposed = numeric_setup_value(card.proposed_value_raw)
    delta = proposed - current if current is not None and proposed is not None else None
    return (
        (summarize_stored_response_memory(
            response_context=response_context,
            control_key=card.control_key,
            direction_sign=card.direction_sign,
            target_zone_start_pct=workflow.packet.opportunity.start_pct,
            target_zone_end_pct=workflow.packet.opportunity.end_pct,
            surrounding_setup_fingerprint=fingerprint,
            proposed_delta=delta,
            db_path=db_path,
        ),),
        response_context.key,
    )


_MECHANISM_MISSION_LABELS = {
    "driver_execution": "Repeat the driver-input window",
    "braking_response": "Repeat the braking window",
    "corner_rotation": "Repeat the corner-rotation window",
    "tire_state": "Measure the tire-state window",
    "damper_response": "Repeat the damper-response window",
    "platform_response": "Repeat the platform-response window",
    "resistance_scrub_like": "Repeat the resistance/scrub-like window",
    "powertrain_response": "Repeat the powertrain window",
    "stint_trend": "Record a comparable long-run window",
    "sim_integrity": "Re-record the telemetry-integrity window",
    "unclassified": "Repeat the unresolved telemetry window",
}


def _observation_measurement_candidates(
    observations: RunObservationIntelligence,
) -> _ObservationMeasurementInputs:
    """Create safe producer-owned missions only when their channels are available."""
    candidates: list[MeasurementCandidate] = []
    blockers: list[MeasurementBlocker] = []
    available_channels: list[str] = []

    def register_available(channels: Sequence[str]) -> None:
        for channel in channels:
            available_channels.extend(sorted(_channel_lineage(channel)))

    def register_blockers(
        candidate_id: str,
        prefix: str,
        reasons: Sequence[str],
        *,
        priority: MeasurementPriority,
        affected_channels: Sequence[str],
    ) -> tuple[str, ...]:
        identities: list[str] = []
        for index, reason in enumerate(reasons, start=1):
            blocker_id = f"{prefix}:blocker:{index}"
            identities.append(blocker_id)
            blockers.append(
                MeasurementBlocker(
                    blocker_id=blocker_id,
                    priority=priority,
                    reason=reason,
                    affected_channels=tuple(affected_channels),
                    resolving_candidate_ids=(candidate_id,),
                )
            )
        return tuple(identities)

    def blocker_priority(
        required_channels: Sequence[str],
        source_channels: Sequence[str],
        eligible_lap_count: int,
    ) -> MeasurementPriority:
        source_lineage = {
            lineage
            for channel in source_channels
            for lineage in _channel_lineage(channel)
        }
        if any(
            not set(_channel_lineage(channel)) & source_lineage
            for channel in required_channels
        ):
            return "data_qualification"
        if eligible_lap_count < 3:
            return "repetition"
        return "discrimination"

    opportunity = observations.opportunity_signatures
    register_available(opportunity.source_channels)
    if opportunity.status is ObservationStatus.BLOCKED and opportunity.blocker_reasons:
        required_new_laps = max(1, 3 - opportunity.eligible_lap_count)
        candidates.append(
            MeasurementCandidate(
                candidate_id="observation:repeatable-opportunity",
                title="Measure a repeatable physical-position opportunity",
                purpose="Resolve whether the same-setup loss repeats above empirical lap noise.",
                procedure=(
                    f"Keep the setup unchanged and record {required_new_laps} additional complete "
                    f"flying lap{'s' if required_new_laps != 1 else ''} on a repeatable line.",
                    "Compare the same physical-position bins and phase on eligible laps only.",
                ),
                required_channels=tuple(opportunity.required_channels),
                available_channels=tuple(opportunity.source_channels),
                resolves_blocker_ids=register_blockers(
                    "observation:repeatable-opportunity",
                    "opportunity",
                    opportunity.blocker_reasons,
                    priority=blocker_priority(
                        opportunity.required_channels,
                        opportunity.source_channels,
                        opportunity.eligible_lap_count,
                    ),
                    affected_channels=opportunity.required_channels,
                ),
                required_laps=required_new_laps,
                target_phase="whole lap physical-position scan",
                acceptance_thresholds=(
                    "At least three eligible same-setup laps with 90% or better aligned coverage.",
                    "A sustained clustered opportunity must exceed the empirical same-run noise floor.",
                ),
                stop_rule="Stop after a pit, reset, incident, setup change, or telemetry-integrity fault.",
                controlled_variables=("setup", "fuel", "tires", "line", "traffic"),
            )
        )
    for observation in observations.mechanism_observations.observations:
        register_available(observation.source_channels)
        if observation.qualified or not observation.blocker_reasons:
            continue
        mechanism = observation.mechanism.value
        required_new_laps = max(1, 3 - observation.repetition_count)
        candidates.append(
            MeasurementCandidate(
                candidate_id=f"observation:mechanism:{observation.observation_id}",
                title=_MECHANISM_MISSION_LABELS[mechanism],
                purpose="Resolve one typed mechanism observation without changing the setup.",
                procedure=(
                    f"Keep the setup unchanged and record {required_new_laps} additional complete "
                    f"comparable pass{'es' if required_new_laps != 1 else ''} through the marked phase.",
                    "Preserve the producer-required channels and compare the same track-position window.",
                ),
                required_channels=tuple(observation.required_channels),
                available_channels=tuple(observation.source_channels),
                resolves_blocker_ids=register_blockers(
                    f"observation:mechanism:{observation.observation_id}",
                    f"mechanism:{observation.observation_id}",
                    observation.blocker_reasons,
                    priority=blocker_priority(
                        observation.required_channels,
                        observation.source_channels,
                        observation.repetition_count,
                    ),
                    affected_channels=observation.required_channels,
                ),
                required_laps=required_new_laps,
                target_phase=observation.phase or "producer-marked phase",
                acceptance_thresholds=(
                    "Three eligible position-aligned observations with complete required channels.",
                ),
                stop_rule="Stop after an incident, reset, setup change, or telemetry-integrity fault.",
                controlled_variables=("setup", "fuel", "tires", "line", "traffic"),
                source_event_ids=(
                    tuple(
                        dict.fromkeys(
                            citation.event_id
                            for citation in observation.citations
                            if citation.event_id is not None
                        )
                    )
                ),
            )
        )
    anomalies = observations.anomaly_envelopes
    register_available(anomalies.source_channels)
    if anomalies.status is ObservationStatus.BLOCKED and anomalies.blocker_reasons:
        required_new_laps = max(1, 3 - anomalies.eligible_lap_count)
        candidates.append(
            MeasurementCandidate(
                candidate_id="observation:same-setup-envelope",
                title="Build a same-setup anomaly envelope",
                purpose="Establish robust position-wise reference bands before labeling an anomaly.",
                procedure=(
                    f"Record {required_new_laps} additional complete same-setup flying "
                    f"lap{'s' if required_new_laps != 1 else ''} with the required channels healthy.",
                    "Compare sustained clusters against held-out robust reference bands.",
                ),
                required_channels=tuple(anomalies.required_channels),
                available_channels=tuple(anomalies.source_channels),
                resolves_blocker_ids=register_blockers(
                    "observation:same-setup-envelope",
                    "anomaly",
                    anomalies.blocker_reasons,
                    priority=blocker_priority(
                        anomalies.required_channels,
                        anomalies.source_channels,
                        anomalies.eligible_lap_count,
                    ),
                    affected_channels=anomalies.required_channels,
                ),
                required_laps=required_new_laps,
                target_phase="whole lap physical-position scan",
                acceptance_thresholds=(
                    "At least three reference laps and 90% aligned local coverage.",
                    "Only sustained clusters may be published; isolated point excursions remain withheld.",
                ),
                stop_rule="Stop after a pit, reset, incident, setup change, or telemetry-integrity fault.",
                controlled_variables=("setup", "fuel", "tires", "line", "traffic"),
            )
        )
    driver = observations.driver_repeatability
    register_available(driver.source_channels)
    if driver.status is ObservationStatus.BLOCKED and driver.blocker_reasons:
        required_new_laps = max(1, 3 - driver.eligible_lap_count)
        candidates.append(
            MeasurementCandidate(
                candidate_id="observation:driver-repeatability",
                title="Measure driver-input repeatability",
                purpose="Separate repeatable driver execution from vehicle-response evidence.",
                procedure=(
                    f"Keep the setup unchanged and record {required_new_laps} additional complete "
                    f"lap{'s' if required_new_laps != 1 else ''} on the same intended line.",
                    "Compare steering, throttle, and brake timing at matched physical positions.",
                ),
                required_channels=tuple(driver.required_channels),
                available_channels=tuple(driver.source_channels),
                resolves_blocker_ids=register_blockers(
                    "observation:driver-repeatability",
                    "driver",
                    driver.blocker_reasons,
                    priority=blocker_priority(
                        driver.required_channels,
                        driver.source_channels,
                        driver.eligible_lap_count,
                    ),
                    affected_channels=driver.required_channels,
                ),
                required_laps=required_new_laps,
                target_phase="whole lap driver-input scan",
                acceptance_thresholds=(
                    "At least three eligible same-setup laps with aligned driver-input channels.",
                ),
                stop_rule="Stop after a pit, reset, incident, setup change, or telemetry-integrity fault.",
                controlled_variables=("setup", "fuel", "tires", "line", "traffic"),
            )
        )
    return _ObservationMeasurementInputs(
        candidates=tuple(candidates),
        blockers=tuple(blockers),
        available_channels=tuple(dict.fromkeys(available_channels)),
    )


def build_run_intelligence(
    run_id: str,
    *,
    session_id: str | None = None,
    db_path: str | Path | None = None,
    workflow_candidate: ControlledWorkflow | None = None,
) -> RunIntelligenceBundle:
    repository = RaceLabRepository(db_path)
    overview = repository.get_overview(run_id)
    if overview is None:
        raise ValueError(f"Run not found: {run_id}")
    resolved_session_id, scope_run_ids = _resolve_session(run_id, session_id, db_path)
    observation_build = build_observation_intelligence_with_awareness(
        run_id,
        scope_run_ids,
        repository=repository,
        db_path=db_path,
    )
    observation_intelligence = observation_build.observations
    awareness_evidence = observation_build.awareness
    position_result = (
        build_session_position_evidence_result(
            run_id,
            scope_run_ids,
            observation_intelligence,
            db_path=db_path,
        )
        if resolved_session_id is not None
        else None
    )
    position_evidence = (
        position_result.evidence if position_result is not None else ()
    )
    session_intelligence = (
        build_session_intelligence(
            resolved_session_id,
            expected_run_ids=scope_run_ids,
            position_evidence=position_evidence,
            db_path=db_path,
        )
        if resolved_session_id is not None
        else None
    )
    telemetry_health = (
        build_telemetry_health_baseline(
            resolved_session_id,
            run_id,
            expected_run_ids=scope_run_ids,
            repository=repository,
            db_path=db_path,
        )
        if resolved_session_id is not None
        else None
    )
    workflow_rows, workflow_integrity_blockers = (
        repository.list_controlled_workflows_for_run_scope(
            scope_run_ids,
            active_only=False,
        )
    )
    origin_valid_workflows: list[ControlledWorkflow] = []
    if resolved_session_id is None:
        if workflow_rows:
            workflow_integrity_blockers = tuple(dict.fromkeys((
                *workflow_integrity_blockers,
                "Stored controlled workflow policy is unavailable without one exact saved session scope.",
            )))
    else:
        for stored_workflow in workflow_rows:
            try:
                validate_p19_workflow_origin(
                    stored_workflow,
                    repository=repository,
                    expected_session_id=resolved_session_id,
                    expected_session_run_ids=scope_run_ids,
                )
            except (AttributeError, FileNotFoundError, OSError, TypeError, ValueError):
                workflow_integrity_blockers = tuple(dict.fromkeys((
                    *workflow_integrity_blockers,
                    "A stored controlled workflow lacks a valid exact-session P19 authority origin and cannot contribute an action or policy verdict.",
                )))
            else:
                origin_valid_workflows.append(stored_workflow)
    workflow_rows = origin_valid_workflows
    if workflow_candidate is not None:
        if (
            resolved_session_id is None
            or workflow_candidate.source_run_id != run_id
            or workflow_candidate.status != "planned"
            or workflow_candidate.stage_run_ids
            or workflow_candidate.stage_eligible_lap_numbers
            or workflow_candidate.execution is not None
            or workflow_candidate.quality is not None
            or workflow_candidate.source_run_id not in scope_run_ids
            or any(
                item.workflow_id == workflow_candidate.workflow_id
                for item in workflow_rows
            )
        ):
            raise ValueError(
                "The proposed workflow candidate does not match the exact current P19 scope."
            )
        workflow_rows = [*workflow_rows, workflow_candidate]
    workflows = _related_workflows(workflow_rows, scope_run_ids)
    _require_one_active_workflow_in_explicit_session(
        workflows,
        session_id=resolved_session_id,
    )
    workflow = _selected_workflow(workflows, run_id)
    card_blockers: tuple[str, ...] = ()
    current_hypothesis_policy: HypothesisPolicyIdentity | None = None
    if workflow is not None and workflow.packet.primary_test is not None:
        if workflow.source_run_id != run_id:
            card_blockers = (
                "An exact controlled-test target is authorized only on its source A run; stage B/A2 runs may report outcomes but cannot inherit that action authority.",
            )
        else:
            rebuilt_packet, card_blockers = revalidate_controlled_test_packet(
                workflow,
                repository=repository,
            )
            if rebuilt_packet is not None:
                workflow = workflow.model_copy(update={"packet": rebuilt_packet})
                workflows = tuple(
                    workflow if item.workflow_id == workflow.workflow_id else item
                    for item in workflows
                )
        if (
            not card_blockers
            and workflow.packet.primary_test is not None
        ):
            compatibility_identity = (
                read_telemetry_manifest(workflow.source_run_id).get(
                    "compatibility_identity"
                )
                or {}
            )
            try:
                current_hypothesis_policy = controlled_hypothesis_policy_identity(
                    workflow,
                    compatibility_identity,
                    source_setup=repository.get_setup_snapshot(workflow.source_run_id),
                )
                repeat_policy = (
                    evaluate_hypothesis_repeat(
                        session_intelligence.hypothesis_lifecycle,
                        current_hypothesis_policy,
                    )
                    if session_intelligence is not None
                    else None
                )
                durable_repeat_policy = evaluate_durable_hypothesis_repeat(
                    current_hypothesis_policy,
                    db_path=db_path,
                )
            except (FileNotFoundError, OSError, TypeError, ValueError):
                card_blockers = (
                    "The exact hypothesis repeat-policy identity could not be verified; rebuild the controlled test from the current evidence before exposing a setup target.",
                )
            else:
                if repeat_policy is not None and not repeat_policy.allowed:
                    card_blockers = (
                        "This unchanged context, setup, symptom, cause, control, direction, metric, phase, and countereffect policy previously produced a valid Undo result in this session and is marked do-not-repeat.",
                    )
                elif durable_repeat_policy.history_debt:
                    card_blockers = (
                        "Durable engineering history is incomplete. Repair or explicitly quarantine the affected saved session before repeating this policy.",
                    )
                elif not durable_repeat_policy.allowed:
                    card_blockers = (
                        "A protocol-valid Undo result blocks this unchanged context, setup, symptom, cause, control, direction, metric, phase, and countereffect policy across saved sessions.",
                    )
    card_blockers = tuple(dict.fromkeys((
        *card_blockers,
        *_telemetry_health_card_blockers(
            telemetry_health,
            workflow,
            overview.events,
        ),
    )))
    lifecycle = (
        session_intelligence.hypothesis_lifecycle
        if session_intelligence is not None
        else None
    )
    preliminary_hypotheses = _hypotheses(
        workflow,
        card_blockers,
        lifecycle=lifecycle,
        workflows=workflows,
        current_run_id=run_id,
        current_hypothesis_policy=current_hypothesis_policy,
    )
    if workflow is not None and workflow.packet.primary_test is not None:
        active_control_key = workflow.packet.primary_test.control_key
        active_conflict = any(
            cause.cause_id.startswith("workflow:")
            and active_control_key in cause.related_control_keys
            and {
                outcome.outcome
                for outcome in cause.controlled_outcomes
                if outcome.diagnostic_validity == "mechanism_diagnostic"
            }
            >= {"supported", "contradicted"}
            for cause in preliminary_hypotheses
        )
        if active_conflict:
            card_blockers = tuple(dict.fromkeys((
                *card_blockers,
                "Exact protocol-valid controlled outcomes conflict for this cause and control; resolve the contradiction before another setup test.",
            )))
    hypotheses = (
        *_hypotheses(
            workflow,
            card_blockers,
            lifecycle=lifecycle,
            workflows=workflows,
            current_run_id=run_id,
            current_hypothesis_policy=current_hypothesis_policy,
        ),
        *_observation_hypotheses(
            observation_intelligence.mechanism_observations
        ),
    )
    claims = _claims(workflow, card_blockers)
    graph = build_evidence_graph(
        claims=claims,
        causes=hypotheses,
        observations=observation_intelligence.mechanism_observations.observations,
        events=overview.events,
        laps=overview.laps,
        setup_values=_setup_values(workflow, card_blockers),
        workflows=workflows,
        setup_authority_verifier=_repository_setup_authority_verifier(
            workflow,
            requested_run_id=run_id,
            card_blockers=card_blockers,
        ),
    )
    causes = rank_competing_causes(
        hypotheses,
        graph,
    )
    capability = _capability(
        run_id,
        source_file_sha256=overview.session.file_hash,
    )
    quality = assess_data_quality(
        laps=overview.laps,
        events=overview.events,
        capability=capability,
    )
    try:
        lap_context = load_lap_engineering_context_report(run_id, db_path=db_path)
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        lap_context = LapEngineeringContextReport(
            run_id=run_id,
            status="blocked",
            blocker_reasons=(
                "Lap engineering context could not be rebuilt from the imported telemetry.",
            ),
        )
    overview_integrity_blockers = tuple(
        warning.removeprefix("Evidence integrity: ").strip()
        for warning in overview.warnings
        if warning.startswith("Evidence integrity: ")
    )
    quality = _apply_persistence_integrity_blockers(
        quality,
        overview_integrity_blockers,
        workflow_integrity_blockers,
    )
    integrity_reasons = tuple(dict.fromkeys((
        *overview_integrity_blockers,
        *workflow_integrity_blockers,
        *(
            capability.issues
            if capability.status in {"blocked", "unknown"}
            else ()
        ),
        *(
            telemetry_health.blocker_reasons
            if telemetry_health is not None
            and telemetry_health.status == "blocked"
            else ()
        ),
    )))
    planning_prerequisite = (
        MeasurementBlocker(
            blocker_id="current-run:evidence-integrity",
            priority="integrity",
            reason=(
                integrity_reasons[0]
                if integrity_reasons
                else "Restore the current-run evidence identity before engineering work."
            ),
        )
        if integrity_reasons
        else MeasurementBlocker(
            blocker_id="current-run:data-qualification",
            priority="data_qualification",
            reason=(
                quality.recovery_steps[0]
                if quality.recovery_steps
                else "Qualify complete eligible telemetry before engineering work."
            ),
        )
        if quality.status == "blocked"
        else None
    )
    decision = _controlled_decision(workflow, card_blockers)
    measurement_inputs = _observation_measurement_candidates(
        observation_intelligence
    )
    if position_result is not None and position_result.comparability_debt:
        debt_blockers = tuple(
            MeasurementBlocker(
                blocker_id=debt.debt_id,
                priority=(
                    "integrity"
                    if debt.kind == "integrity"
                    else "data_qualification"
                    if debt.kind in {"eligible_laps", "telemetry_rows"}
                    else "discrimination"
                ),
                reason=debt.reason,
                affected_channels=debt.required_channels,
                resolving_candidate_ids=(f"mission:{debt.debt_id}",),
            )
            for debt in position_result.comparability_debt
        )
        debt_candidates = tuple(
            MeasurementCandidate(
                candidate_id=f"mission:{debt.debt_id}",
                title="Resolve run-comparability debt",
                purpose=debt.reason,
                procedure=(debt.recovery,),
                required_channels=debt.required_channels,
                available_channels=measurement_inputs.available_channels,
                resolves_blocker_ids=(debt.debt_id,),
                required_laps=3,
                target_phase="producer-marked physical-position window",
                acceptance_thresholds=(
                    "Three eligible laps pass physical-position, fuel, tire, weather, line, and nearby-car context gates.",
                ),
                stop_rule="Stop after a pit, reset, incident, setup change, or integrity fault.",
                controlled_variables=("setup", "fuel", "tires", "weather", "line", "traffic"),
            )
            for debt in position_result.comparability_debt
        )
        measurement_inputs = _ObservationMeasurementInputs(
            candidates=(*measurement_inputs.candidates, *debt_candidates),
            blockers=(*measurement_inputs.blockers, *debt_blockers),
            available_channels=measurement_inputs.available_channels,
        )
    affected_health_channels = tuple(
        dict.fromkeys(
            channel
            for finding in telemetry_health.findings
            for channel in (finding.channel, *finding.source_raw_names)
        )
    ) if telemetry_health is not None and telemetry_health.status == "warning" else ()
    planning_channel_names = {
        *affected_health_channels,
        *(
            channel
            for candidate in measurement_inputs.candidates
            for channel in candidate.required_channels
        ),
        *(
            channel
            for node in graph.nodes
            if node.citation is not None
            for channel in node.citation.channels
        ),
    }
    channel_lineage_by_channel = {
        channel: tuple(sorted(_channel_lineage(channel)))
        for channel in planning_channel_names
    }
    plan = plan_best_next_measurement(
        causes,
        controlled_decision=decision,
        measurement_candidates=measurement_inputs.candidates,
        known_measurement_blockers=measurement_inputs.blockers,
        known_available_channels=measurement_inputs.available_channels,
        planning_prerequisite=planning_prerequisite,
        graph=graph,
        current_run_id=run_id,
        affected_health_channels=affected_health_channels,
        channel_lineage_by_channel=channel_lineage_by_channel,
    )
    try:
        mission_setup = overview.setup_snapshot
        mission_setup_sha256 = setup_policy_fingerprint(mission_setup)
        mission_manifest = read_telemetry_manifest(run_id)
        mission_compatibility_fingerprint = str(
            mission_manifest.get("compatibility_fingerprint") or ""
        )
        if (
            mission_setup is None
            or mission_setup_sha256 is None
            or re.fullmatch(
                r"[0-9a-f]{64}", mission_compatibility_fingerprint
            )
            is None
        ):
            raise ValueError(
                "durable missions require exact setup and compatibility identity"
            )
        plan = bind_durable_experiment_lifecycle(
            plan,
            candidate_id=f"{plan.kind}:{plan.title.casefold().replace(' ', '-')}",
            run_id=run_id,
            repository=repository,
            session_id=resolved_session_id,
            session_run_ids=scope_run_ids,
            source_setup_id=mission_setup.setup_id,
            setup_sha256=mission_setup_sha256,
            compatibility_fingerprint=mission_compatibility_fingerprint,
            required_channels=tuple(sorted(planning_channel_names)),
            cause_ids=tuple(
                cause.cause_id for cause in causes if cause.status != "ruled_out"
            ),
            telemetry_health_identity=(
                telemetry_health.session_scope_sha256
                if telemetry_health is not None
                else f"run:{run_id}:health-unavailable"
            ),
        )
    except (OSError, TypeError, ValueError, sqlite3.Error):
        plan = InformationPlan(
            kind="blocked",
            title="Measurement history requires recovery",
            instruction="Repair or quarantine the incomplete durable mission history before testing again.",
            rationale="Exact-contract attempt history could not be revalidated, so the planner withheld repetition authority.",
            blocker_reasons=(
                "Durable measurement-attempt history could not be verified for the current mission.",
            ),
        )
    context_matches, response_context_key = _context_matches(
        run_id,
        workflow,
        overview,
        db_path,
    )
    calibration = get_prediction_calibration(
        run_id=run_id,
        session_run_ids=scope_run_ids,
        db_path=db_path,
    )
    calibration_model = CalibrationSummary(
        status="available" if calibration.graded_predictions > 0 else "insufficient_history",
        evaluated_predictions=(
            calibration.graded_predictions if calibration.graded_predictions > 0 else None
        ),
        correct_direction_count=(
            calibration.matched_predictions if calibration.graded_predictions > 0 else None
        ),
        note=(
            f"Direction matched in {calibration.matched_predictions} of "
            f"{calibration.graded_predictions} protocol-valid gradable direction outcomes."
            if calibration.graded_predictions > 0
            else "No protocol-valid frozen prediction has a gradable direction in this scope."
        ),
    )
    issue = (
        f"Driver report: {workflow.complaint}"
        if workflow is not None
        else _humanize(overview.primary_findings[0])
        if overview.primary_findings
        else "No evidence-qualified engineering issue is available."
    )
    report = build_internal_intelligence_report(
        run_id=run_id,
        session_id=resolved_session_id,
        session_run_ids=scope_run_ids,
        response_context_key=response_context_key,
        issue=issue,
        graph=graph,
        ranked_causes=causes,
        best_measurement=plan,
        data_quality=quality,
        lap_context=lap_context,
        mechanism_episodes=awareness_evidence.episodes,
        mechanism_episode_blocker_reasons=awareness_evidence.blocker_reasons,
        context_matches=context_matches,
        calibration=calibration_model,
    )
    if session_intelligence is not None:
        report = report.model_copy(
            update={
                "session_ledger": session_intelligence.session_ledger,
                "hypothesis_lifecycle": session_intelligence.hypothesis_lifecycle,
            }
        )
    report = report.model_copy(
        update={
            "opportunity_signature": observation_intelligence.opportunity_signatures,
            "mechanism_observations": observation_intelligence.mechanism_observations,
            "anomalies": observation_intelligence.anomaly_envelopes,
            "driver_focus": observation_intelligence.driver_repeatability,
                "telemetry_health": telemetry_health,
                "comparability_debt": (
                    position_result.comparability_debt
                    if position_result is not None
                    else ()
                ),
            }
    )
    guidance_workflow = workflow or next(
        (
            item
            for item in workflows
            if item.status == "scored"
            and (
                item.source_run_id == run_id
                or run_id in item.stage_run_ids.values()
            )
        ),
        None,
    )
    guidance = build_smart_guidance(report, workflow=guidance_workflow)
    report = report.model_copy(
        update={
            "smart_guidance": guidance,
            "suggested_questions": tuple(
                dict.fromkeys((*guidance.contextual_questions, *report.suggested_questions))
            )[:4],
        }
    )
    narrative = list_engineering_narrative(
        session_id=resolved_session_id,
        run_id=None if resolved_session_id is not None else run_id,
        db_path=db_path,
    )
    profile = get_driver_presentation_profile_for_run(run_id, db_path=db_path)
    return RunIntelligenceBundle(
        report=report,
        narrative_entries=narrative,
        calibration=calibration,
        driver_profile=profile,
        awareness=awareness_evidence,
    )


__all__ = ["RunIntelligenceBundle", "build_run_intelligence"]
