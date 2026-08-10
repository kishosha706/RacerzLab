from __future__ import annotations

import pytest
from pydantic import ValidationError

from racelab_engine.models.engineering_awareness import (
    AnalyzerVersion,
    ChannelCoverage,
    ChannelRole,
    DerivedMetricContract,
    EngineeringStateFrame,
    EpisodeRepeatability,
    FrameChannelSemantic,
    MechanismEpisode,
    MetricProvenance,
    StateEvidenceReference,
    StateTransition,
    SubsystemStateReference,
    TemporalRelationship,
    TrustAxis,
    TrustBudget,
    TrustState,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.lap_engineering_context import ChannelUpdateSemantic
from racelab_engine.models.observation_intelligence import MechanismKind


def _evidence(**updates: object) -> StateEvidenceReference:
    values: dict[str, object] = {
        "evidence_id": "evidence-1",
        "artifact_id": "artifact-1",
        "run_id": "run-1",
        "setup_id": "setup-1",
        "lap_number": 8,
        "lap_pct_start": 35.0,
        "lap_pct_end": 42.0,
        "lap_pct_peak": 39.0,
        "evidence_state": EvidenceState.OBSERVED_CORRELATION,
        "source_channels": ("lap_dist_pct_100", "yaw_rate"),
        "summary": "Observed rotation response in the exact center window.",
    }
    values.update(updates)
    return StateEvidenceReference(**values)


def _subsystem(**updates: object) -> SubsystemStateReference:
    values: dict[str, object] = {
        "artifact_id": "rotation-artifact-1",
        "producer_id": "phase_engineering.rotation",
        "mechanism": MechanismKind.CORNER_ROTATION,
        "run_id": "run-1",
        "setup_id": "setup-1",
        "lap_number": 8,
        "lap_pct_start": 35.0,
        "lap_pct_end": 42.0,
        "lap_pct_peak": 39.0,
    }
    values.update(updates)
    return SubsystemStateReference(**values)


def _frame_data(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "frame_id": "frame-1",
        "run_id": "run-1",
        "lap_number": 8,
        "setup_id": "setup-1",
        "context_id": "context-1",
        "independence_cluster_id": "run-1:setup-1:stint-2",
        "lap_pct_start": 35.0,
        "lap_pct_end": 42.0,
        "lap_pct_peak": 39.0,
        "session_time_start": 502.0,
        "session_time_end": 505.5,
        "phase": "center",
        "source_artifact_ids": ("artifact-1", "rotation-artifact-1"),
        "source_event_ids": ("event-1",),
        "source_channels": ("lap_dist_pct_100", "yaw_rate"),
        "channel_semantics": (
            FrameChannelSemantic(
                channel="lap_dist_pct_100",
                role=ChannelRole.POSITION_LOCATOR,
                update_semantic=ChannelUpdateSemantic.CONTINUOUS,
            ),
            FrameChannelSemantic(
                channel="yaw_rate",
                role=ChannelRole.MEASUREMENT,
                update_semantic=ChannelUpdateSemantic.CONTINUOUS,
            ),
        ),
        "coverage_by_channel": (
            ChannelCoverage(channel="lap_dist_pct_100", sample_coverage=1.0),
            ChannelCoverage(channel="yaw_rate", sample_coverage=0.98),
        ),
        "vehicle_profile_id": None,
        "vehicle_profile_hash": None,
        "analyzer_versions": (
            AnalyzerVersion(analyzer_id="phase_engineering.rotation", version="1"),
        ),
        "rotation": _subsystem(),
        "evidence_states": (EvidenceState.OBSERVED_CORRELATION,),
        "supporting_evidence": (_evidence(),),
    }
    values.update(updates)
    return values


def _frame(**updates: object) -> EngineeringStateFrame:
    return EngineeringStateFrame(**_frame_data(**updates))


def _transition_data(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "transition_id": "transition-1",
        "run_id": "run-1",
        "setup_id": "setup-1",
        "context_id": "context-1",
        "from_frame_id": "frame-1",
        "to_frame_id": "frame-2",
        "relationship": TemporalRelationship.RESPONDS_AFTER,
        "onset_time": 502.2,
        "peak_time": 503.0,
        "recovery_time": 505.0,
        "onset_lap_pct": 35.5,
        "peak_lap_pct": 39.0,
        "observed_lag_ms": 180.0,
        "source_artifact_ids": ("artifact-1",),
        "source_channels": ("yaw_rate",),
        "evidence_state": EvidenceState.OBSERVED_CORRELATION,
        "supporting_evidence": (_evidence(),),
    }
    values.update(updates)
    return values


def _trust_axis(
    state: TrustState = TrustState.TRUSTED,
    *,
    blockers: tuple[str, ...] = (),
) -> TrustAxis:
    return TrustAxis(
        state=state,
        basis="Exact typed evidence was evaluated for this axis.",
        blockers=blockers,
        source_artifact_ids=("artifact-1",),
    )


def test_channel_role_has_no_fake_unknown_member() -> None:
    assert "unknown" not in {role.value for role in ChannelRole}
    semantic = FrameChannelSemantic(
        channel="future_channel",
        role=None,
        update_semantic=ChannelUpdateSemantic.CONSTANT,
    )
    assert semantic.role is None


def test_derived_metric_contract_is_observation_only_and_fail_closed() -> None:
    contract = DerivedMetricContract(
        metric_key="yaw_response_lag",
        formula_version="v1",
        label="Yaw response lag",
        evidence_state=EvidenceState.ESTIMATED_PROXY,
        required_channels=("steering_angle", "yaw_rate"),
        preferred_channels=("steering_wheel_torque",),
        allowed_channel_semantics=(ChannelUpdateSemantic.CONTINUOUS,),
        required_vehicle_profile_fields=(),
        valid_phases=("entry", "center"),
        hard_blockers=("material_control_mutation", "insufficient_alignment"),
        minimum_sample_coverage=0.9,
        minimum_repetitions=3,
        allowed_outputs=("observed_response_lag_ms",),
        forbidden_claims=("caused_understeer", "optimal_setup_value"),
        description="Describes timing only; it does not establish a cause.",
        provenance=MetricProvenance(
            producer_id="transient_response",
            source_module="racelab_engine.analysis.transient_response",
            source_contract_ids=("phase_alignment_v1",),
        ),
    )

    assert contract.authority_ceiling == "observation_only"
    with pytest.raises(ValidationError):
        DerivedMetricContract(
            **{
                **contract.model_dump(),
                "allowed_channel_semantics": (ChannelUpdateSemantic.MISSING,),
            }
        )
    with pytest.raises(ValidationError):
        DerivedMetricContract(
            **{
                **contract.model_dump(),
                "authority_ceiling": "setup_authority",
            }
        )


@pytest.mark.parametrize(
    ("reference_update", "match"),
    (
        ({"run_id": "run-2"}, "run/setup/lap"),
        ({"setup_id": "setup-2"}, "run/setup/lap"),
        ({"lap_number": 9}, "run/setup/lap"),
        ({"lap_pct_start": 34.0}, "exact run/setup/lap window"),
    ),
)
def test_state_frame_rejects_cross_scope_evidence(
    reference_update: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        _frame(supporting_evidence=(_evidence(**reference_update),))


def test_state_frame_rejects_cross_scope_subsystem_reference() -> None:
    with pytest.raises(ValidationError, match="exact frame scope"):
        _frame(rotation=_subsystem(setup_id="setup-2"))


def test_state_frame_cannot_span_material_control_mutation() -> None:
    with pytest.raises(ValidationError):
        EngineeringStateFrame(
            **_frame_data(spans_material_control_mutation=True)
        )


def test_state_frame_requires_exact_semantics_and_coverage() -> None:
    with pytest.raises(ValidationError, match="semantics must cover"):
        _frame(
            channel_semantics=(
                FrameChannelSemantic(
                    channel="lap_dist_pct_100",
                    role=ChannelRole.POSITION_LOCATOR,
                    update_semantic=ChannelUpdateSemantic.CONTINUOUS,
                ),
            )
        )
    with pytest.raises(ValidationError, match="coverage must cover"):
        _frame(
            coverage_by_channel=(
                ChannelCoverage(channel="lap_dist_pct_100", sample_coverage=1.0),
            )
        )
    with pytest.raises(ValidationError, match="artifacts must be declared"):
        _frame(supporting_evidence=(_evidence(artifact_id="undeclared-artifact"),))
    with pytest.raises(ValidationError, match="channels must be declared"):
        _frame(
            supporting_evidence=(
                _evidence(source_channels=("lap_dist_pct_100", "undeclared_channel")),
            )
        )


def test_state_frame_cannot_carry_setup_or_policy_authority() -> None:
    with pytest.raises(ValidationError):
        EngineeringStateFrame(**_frame_data(setup_target="front_arb"))
    with pytest.raises(ValidationError):
        EngineeringStateFrame(**_frame_data(policy_verdict="keep"))
    with pytest.raises(ValidationError):
        EngineeringStateFrame(**_frame_data(authority="setup_authority"))


def test_transition_vocabulary_is_temporal_and_never_causal() -> None:
    transition = StateTransition(**_transition_data())
    assert transition.relationship is TemporalRelationship.RESPONDS_AFTER
    assert transition.authority == "observation_only"
    assert {item.value for item in TemporalRelationship} == {
        "precedes",
        "responds_after",
        "co_occurs_with",
        "persists_into",
        "recovers_after",
    }
    with pytest.raises(ValidationError):
        StateTransition(**_transition_data(relationship="causes"))
    with pytest.raises(ValidationError):
        StateTransition(**_transition_data(authority="setup_authority"))


def test_transition_rejects_mismatched_evidence_and_reversed_time() -> None:
    with pytest.raises(ValidationError, match="run and setup"):
        StateTransition(
            **_transition_data(supporting_evidence=(_evidence(run_id="run-2"),))
        )
    with pytest.raises(ValidationError, match="peak cannot precede"):
        StateTransition(**_transition_data(peak_time=501.0))


def test_mechanism_episode_has_temporal_evidence_but_no_setup_authority() -> None:
    episode = MechanismEpisode(
        episode_id="episode-1",
        run_id="run-1",
        setup_id="setup-1",
        context_id="context-1",
        lap_scope=(8, 9),
        phase="center",
        lap_pct_start=35.0,
        lap_pct_end=42.0,
        lap_pct_peak=39.0,
        state_frame_ids=("frame-1", "frame-2", "frame-3"),
        transition_ids=("transition-1", "transition-2"),
        supporting_mechanism_kinds=(MechanismKind.CORNER_ROTATION,),
        contradicting_mechanism_kinds=(MechanismKind.DRIVER_EXECUTION,),
        supporting_artifact_ids=("artifact-1",),
        contradicting_artifact_ids=("artifact-2",),
        independence_cluster_ids=("run-1:setup-1:stint-2",),
        repeatability=EpisodeRepeatability(
            repetition_count=2,
            distinct_lap_count=2,
            independent_cluster_count=1,
            basis="Adjacent same-stint laps show repeatability, not independent experiments.",
        ),
        time_effect_s=0.08,
        mind_change_requirements=("Repeat with a protocol-valid diagnostic control.",),
        measurement_requirements=("Capture the same physical window on three clean laps.",),
    )

    assert episode.authority == "observation_only"
    assert episode.repeatability.independent_cluster_count == 1
    with pytest.raises(ValidationError):
        MechanismEpisode(**{**episode.model_dump(), "policy_verdict": "undo"})
    with pytest.raises(ValidationError):
        MechanismEpisode(**{**episode.model_dump(), "authority": "setup_authority"})
    with pytest.raises(ValidationError, match="ordered chronologically"):
        MechanismEpisode(**{**episode.model_dump(), "lap_scope": (9, 8)})


def test_trust_budget_keeps_axes_and_hard_blockers_separate() -> None:
    budget = TrustBudget(
        data_health=_trust_axis(),
        alignment_quality=_trust_axis(),
        context_comparability=_trust_axis(
            TrustState.BLOCKED,
            blockers=("Weight penalty differs between compared runs.",),
        ),
        driver_repeatability=_trust_axis(
            TrustState.LIMITED,
            blockers=("Only two same-stint repetitions are available.",),
        ),
        mechanism_separation=_trust_axis(),
        controlled_response_validity=_trust_axis(
            TrustState.UNAVAILABLE,
            blockers=("No controlled A/B/A2 outcome exists.",),
        ),
        policy_countereffect_risk=_trust_axis(),
        history_completeness=_trust_axis(),
    )

    assert budget.context_comparability.state is TrustState.BLOCKED
    assert "confidence" not in budget.model_fields
    with pytest.raises(ValidationError, match="require blockers"):
        _trust_axis(TrustState.BLOCKED)
    with pytest.raises(ValidationError, match="cannot hide blockers"):
        _trust_axis(TrustState.TRUSTED, blockers=("hidden blocker",))


def test_awareness_models_are_frozen_and_extra_forbid() -> None:
    frame = _frame()
    with pytest.raises(ValidationError):
        frame.phase = "exit"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        TrustAxis(
            state=TrustState.TRUSTED,
            basis="Exact evidence.",
            blockers=(),
            source_artifact_ids=(),
            average_confidence=0.9,
        )
