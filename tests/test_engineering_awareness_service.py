from __future__ import annotations

from pydantic import ValidationError
import pytest

from racelab_engine.models.engineering_awareness import (
    StateDriftEntry,
    StateDriftMetric,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import CapabilityAssessment
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.observation_intelligence import (
    MechanismKind,
    MechanismObservation,
    MechanismObservationReport,
    ObservationCitation,
    ObservationStatus,
)
from racelab_engine.services.engineering_awareness_service import (
    MECHANISM_SIGNATURE_DEFINITIONS,
    build_engineering_awareness_evidence,
    build_state_drift_ledger,
)
from racelab_engine.services.intelligence_service import (
    assess_data_quality,
    build_evidence_graph,
    build_reasoning_snapshot,
    plan_best_next_measurement,
    rank_competing_causes,
)
from racelab_engine.services.run_intelligence_service import _observation_hypotheses


def _citation(lap: int, mechanism: MechanismKind) -> ObservationCitation:
    channel = {
        MechanismKind.DRIVER_EXECUTION: "steering_deg",
        MechanismKind.CORNER_ROTATION: "yaw_rate",
        MechanismKind.PLATFORM_RESPONSE: "lf_ride_height_mm",
    }[mechanism]
    return ObservationCitation(
        run_id="run-a",
        lap_number=lap,
        setup_id="setup-a",
        lap_pct_start=40.0,
        lap_pct_end=41.0,
        lap_pct_peak=40.5,
        phase="center",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=(channel,),
        telemetry_sample_count=11,
    )


def _observation(mechanism: MechanismKind) -> MechanismObservation:
    citations = tuple(_citation(lap, mechanism) for lap in (4, 5))
    return MechanismObservation(
        observation_id=f"observation:{mechanism.value}",
        producer_id=f"producer.{mechanism.value}",
        artifact_id=f"artifact:{mechanism.value}",
        source_run_ids=("run-a",),
        source_setup_ids=("setup-a",),
        sample_coverage=1.0,
        mechanism=mechanism,
        run_id="run-a",
        setup_id="setup-a",
        lap_number=4,
        phase="center",
        lap_pct_start=40.0,
        lap_pct_end=41.0,
        lap_pct_peak=40.5,
        summary=f"Typed {mechanism.value} response.",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        qualified=True,
        source_channels=citations[0].source_channels,
        required_channels=citations[0].source_channels,
        supporting_evidence=(f"support:{mechanism.value}",),
        telemetry_sample_count=22,
        repetition_count=2,
        citations=citations,
    )


def _rows() -> list[dict[str, float | int | str]]:
    rows = []
    for lap, start in ((4, 10.0), (5, 20.0)):
        for index in range(11):
            fraction = index / 10.0
            rows.append(
                {
                    "run_id": "run-a",
                    "lap": lap,
                    "session_time": start + fraction,
                    "lap_dist_pct_100": 40.0 + fraction,
                    "steering_deg": 8.0 + fraction,
                    "yaw_rate": 0.10 + fraction * 0.02,
                    "lf_ride_height_mm": 50.0 - fraction,
                }
            )
    return rows


def test_one_artifact_preserves_multiple_mechanism_identities() -> None:
    observation = _observation(MechanismKind.CORNER_ROTATION).model_copy(
        update={
            "mechanism_kinds": (
                MechanismKind.CORNER_ROTATION,
                MechanismKind.PLATFORM_RESPONSE,
            )
        }
    )
    validated = MechanismObservation.model_validate(observation.model_dump())
    assert validated.mechanism is MechanismKind.CORNER_ROTATION
    assert validated.mechanism_kinds == (
        MechanismKind.CORNER_ROTATION,
        MechanismKind.PLATFORM_RESPONSE,
    )


def _report() -> MechanismObservationReport:
    return MechanismObservationReport(
        status=ObservationStatus.READY,
        run_id="run-a",
        setup_id="setup-a",
        observations=tuple(
            _observation(mechanism)
            for mechanism in (
                MechanismKind.DRIVER_EXECUTION,
                MechanismKind.CORNER_ROTATION,
                MechanismKind.PLATFORM_RESPONSE,
            )
        ),
    )


def test_production_builder_creates_exact_temporal_episode_for_p19() -> None:
    build = build_engineering_awareness_evidence(
        _report(), _rows(), run_id="run-a", setup_id="setup-a"
    )
    assert len(build.frames) == 6
    assert build.transitions
    assert len(build.episodes) == 1
    episode = build.episodes[0]
    assert episode.authority == "observation_only"
    assert episode.signature_keys == ("center_front_response_chain",)
    assert episode.repeatability.independent_cluster_count == 1
    assert build.episode_observations.status is ObservationStatus.READY
    assert build.episode_observations.observations[0].producer_id == (
        "p20.mechanism_episode_builder"
    )


def test_backend_episode_enters_existing_p19_graph_and_reasoning_snapshot() -> None:
    build = build_engineering_awareness_evidence(
        _report(), _rows(), run_id="run-a", setup_id="setup-a"
    )
    report = build.episode_observations
    causes = _observation_hypotheses(report)
    laps = tuple(
        LapSummary(
            lap_id=f"run-a:{lap}",
            run_id="run-a",
            lap_number=lap,
            lap_type="flying",
            is_complete=True,
            is_useful=True,
            lap_time=30.0,
            sample_count=100,
        )
        for lap in (4, 5)
    )
    graph = build_evidence_graph(
        causes=causes,
        observations=report.observations,
        laps=laps,
    )
    ranked = rank_competing_causes(causes, graph)
    plan = plan_best_next_measurement(ranked)
    quality = assess_data_quality(
        laps=laps,
        events=(),
        capability=CapabilityAssessment(status="ready"),
    ).model_copy(update={"scope_run_ids": ("run-a",), "status": "limited"})
    snapshot = build_reasoning_snapshot(
        run_id="run-a",
        session_id=None,
        graph=graph,
        ranked_causes=ranked,
        measurement_plan=plan,
        data_quality=quality,
        mechanism_episodes=build.episodes,
    )
    assert snapshot.mechanism_episodes == build.episodes
    assert any(
        node.kind.value == "observation" for node in snapshot.evidence_graph.nodes
    )
    assert snapshot.authority.setup_authorized is False


def test_transitions_use_only_noncausal_vocabulary_and_actual_scope() -> None:
    build = build_engineering_awareness_evidence(
        _report(), _rows(), run_id="run-a", setup_id="setup-a"
    )
    assert {item.relationship.value for item in build.transitions} <= {
        "precedes",
        "co_occurs_with",
        "persists_into",
    }
    assert all(item.observed_lag_ms >= 0.0 for item in build.transitions)
    assert all(item.source_channels for item in build.transitions)
    assert all(item.source_artifact_ids for item in build.transitions)


def test_missing_source_channel_blocks_frame_instead_of_becoming_zero() -> None:
    rows = [
        {key: value for key, value in row.items() if key != "yaw_rate"}
        for row in _rows()
    ]
    build = build_engineering_awareness_evidence(
        _report(), rows, run_id="run-a", setup_id="setup-a"
    )
    assert len(build.frames) == 4
    assert any("yaw_rate" in reason for reason in build.blocker_reasons)
    assert all(frame.rotation is None for frame in build.frames)


def test_cross_setup_observation_never_enters_state_frame() -> None:
    source = _observation(MechanismKind.CORNER_ROTATION)
    changed = MechanismObservation.model_validate(
        {
            **source.model_dump(),
            "setup_id": "setup-b",
            "source_setup_ids": ("setup-b",),
            "citations": tuple(
                {**citation.model_dump(), "setup_id": "setup-b"}
                for citation in source.citations
            ),
        }
    )
    frames = MechanismObservationReport(
        status=ObservationStatus.READY,
        run_id="run-a",
        setup_id="setup-a",
        observations=(_observation(MechanismKind.DRIVER_EXECUTION), changed),
    )
    build = build_engineering_awareness_evidence(
        frames, _rows(), run_id="run-a", setup_id="setup-a"
    )
    assert all(frame.setup_id == "setup-a" for frame in build.frames)
    assert any("setup identity" in reason for reason in build.blocker_reasons)


def _drift_entry(lap: int, value: float) -> StateDriftEntry:
    return StateDriftEntry(
        entry_id=f"entry-{lap}",
        run_id="run-a",
        setup_id="setup-a",
        context_id="center:40-41",
        independence_cluster_id="run-a:setup-a:same-stint",
        lap_number=lap,
        phase="center",
        lap_pct_start=40.0,
        lap_pct_end=41.0,
        metrics=(
            StateDriftMetric(
                metric_key="center_steering_demand",
                value=value,
                unit="deg",
                source_artifact_ids=(f"steering-{lap}",),
            ),
        ),
    )


def test_drift_requires_contiguous_comparable_persistent_above_noise_shift() -> None:
    ledger = build_state_drift_ledger(
        (_drift_entry(4, 8.0), _drift_entry(5, 9.0), _drift_entry(6, 9.2)),
        run_id="run-a",
        setup_id="setup-a",
        control_state_unchanged=True,
        channel_health_stable=True,
        context_comparable=True,
        empirical_noise_by_metric={"center_steering_demand": 0.4},
    )
    assert ledger.status == "ready"
    assert ledger.findings[0].relationship == "state_shift_observed"
    assert ledger.formal_change_point_authority is False
    assert ledger.authority == "observation_only"


def test_drift_fails_closed_on_context_or_lap_gap() -> None:
    ledger = build_state_drift_ledger(
        (_drift_entry(4, 8.0), _drift_entry(6, 9.0), _drift_entry(7, 9.2)),
        run_id="run-a",
        setup_id="setup-a",
        control_state_unchanged=True,
        channel_health_stable=True,
        context_comparable=False,
        empirical_noise_by_metric={"center_steering_demand": 0.4},
    )
    assert ledger.status == "blocked"
    assert not ledger.findings
    assert any("not contiguous" in reason for reason in ledger.blocker_reasons)
    assert any("not comparable" in reason for reason in ledger.blocker_reasons)


def test_drift_does_not_publish_noise_or_single_lap_excursion() -> None:
    ledger = build_state_drift_ledger(
        (_drift_entry(4, 8.0), _drift_entry(5, 8.8), _drift_entry(6, 8.1)),
        run_id="run-a",
        setup_id="setup-a",
        control_state_unchanged=True,
        channel_health_stable=True,
        context_comparable=True,
        empirical_noise_by_metric={"center_steering_demand": 0.4},
    )
    assert ledger.status == "no_finding"
    assert not ledger.findings


def test_signature_definitions_are_inspectable_not_probabilistic() -> None:
    assert MECHANISM_SIGNATURE_DEFINITIONS
    for definition in MECHANISM_SIGNATURE_DEFINITIONS:
        dumped = definition.model_dump()
        assert "probability" not in dumped
        assert "confidence" not in dumped
        assert definition.authority == "observation_only"
    with pytest.raises(ValidationError):
        MECHANISM_SIGNATURE_DEFINITIONS[0].model_copy(
            update={"authority": "setup_authority"}
        ).__class__.model_validate(
            {
                **MECHANISM_SIGNATURE_DEFINITIONS[0].model_dump(),
                "authority": "setup_authority",
            }
        )
