from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.knowledge.vehicle_dynamics.next_gen_oval import (
    compile_next_gen_oval_knowledge_graph,
    compile_next_gen_oval_runtime_trust_manifest,
)
from racelab_engine.models.crew_chief import (
    CrewChiefWorkspace,
    EngineeringEvidenceIndexEntry,
    EngineeringObjective,
    engineering_awareness_scientific_sha256,
    p34_qualified_current_artifact_ids,
)
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.observation_intelligence import (
    MechanismKind,
    MechanismObservation,
    MechanismObservationReport,
    ObservationCitation,
    ObservationStatus,
)
from racelab_engine.models.performance_intelligence import (
    PerformanceIntelligenceProjection,
)
from racelab_engine.models.vehicle_dynamics_knowledge import (
    VehicleDynamicsFocusArtifact,
    build_performance_mechanism_assessment,
)
from racelab_engine.services import crew_chief_service
from racelab_engine.services import engineering_projection_service
from racelab_engine.services import import_service, run_intelligence_service
from racelab_engine.services.crew_chief_service import (
    _P35_TOOL_IDS,
    _evidence_index,
    _freeze_p34_pair_for_workspace,
    _select_tool_entries,
    _subgoal,
    build_crew_chief_workspace,
)
from racelab_engine.services.vehicle_dynamics_service import (
    _focus_id,
    build_vehicle_dynamics_assessment,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository
from test_crew_chief_contracts import _identity
from test_performance_truth_closure import _build_public_projection
from test_vehicle_dynamics_service import (
    _assessment,
    _exact_response_projection,
    _p20_for_scope,
    _p26,
)


class _Repository:
    @staticmethod
    def get_setup_snapshots(_run_ids):
        return {}


def _coordinated_p35_workspace_payload(
    workspace: CrewChiefWorkspace,
    assessment,
    *,
    artifact_id_map: dict[str, str] | None = None,
    extra_entries: tuple[dict[str, object], ...] = (),
) -> dict[str, object]:
    artifact_id_map = artifact_id_map or {}
    focus_by_id = {item.artifact_id: item for item in assessment.focus_artifacts}
    entries: list[dict[str, object]] = []
    for entry in workspace.evidence_index.entries:
        payload = entry.model_dump(mode="python")
        if entry.producer_id.startswith("p35."):
            new_id = artifact_id_map.get(entry.artifact_id, entry.artifact_id)
            focus = focus_by_id[new_id]
            payload.update(
                artifact_id=new_id,
                evidence_state=focus.evidence_state,
                source_channels=focus.source_channels,
                blocker_reasons=focus.blocker_reasons,
                typed_artifact={
                    "artifact_type": "vehicle_dynamics_focus",
                    "assessment_sha256": assessment.p35_assessment_sha256,
                    "inspection_tool_id": focus.inspection_tool_id.value,
                    "focus": focus.model_dump(mode="python"),
                },
            )
        entries.append(payload)
    entries.extend(extra_entries)
    identity = workspace.identity.model_dump(mode="python")
    identity["p35_assessment_sha256"] = assessment.p35_assessment_sha256
    public = workspace.model_dump(mode="python")
    public.update(
        identity=identity,
        vehicle_dynamics=assessment.model_dump(mode="python"),
        evidence_index={
            "workspace_revision": workspace.evidence_index.workspace_revision,
            "entries": entries,
            "index_hash": canonical_json_sha256(entries),
        },
    )
    return public


def _synthetic_focus_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path):
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=False
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = _exact_response_projection(p32, p20)
    p32_payload = p32.model_dump(mode="json", exclude={"projection_sha256"})
    p32 = PerformanceIntelligenceProjection.model_validate(
        {
            **p32_payload,
            "projection_sha256": canonical_json_sha256(p32_payload),
        }
    )
    assert p32.projection_sha256 == canonical_json_sha256(
        p32.model_dump(mode="json", exclude={"projection_sha256"})
    )
    p26 = _p26(p32)
    p26.component_states = ()
    p26.leading_component_ids = ()
    p26.knowledge_debt = ()
    p35 = _assessment(p32, p20, p26=p26)
    setup_id = "setup-synthetic-p35"
    runtime_hash = canonical_json_sha256(p26.runtime_identity)
    identity = _identity().model_copy(
        update={
            "run_id": p32.run_id,
            "session_id": p32.session_id,
            "reasoning_snapshot_sha256": p32.p19_reasoning_snapshot_sha256,
            "p20_state_revision": p20.state_revision,
            "p20_profile_hash": p20.profile_hash,
            "p26_graph_version": p26.graph_version,
            "p26_knowledge_graph_sha256": p26.knowledge_graph_sha256,
            "p26_reasoning_snapshot_sha256": p32.p19_reasoning_snapshot_sha256,
            "p32_projection_sha256": p32.projection_sha256,
            "p35_assessment_sha256": p35.p35_assessment_sha256,
            "setup_id": setup_id,
            "setup_snapshot_sha256": "6" * 64,
            "vehicle_runtime_identity_hash": runtime_hash,
            "objective_id": EngineeringObjective.QUALIFYING_PEAK,
            "workspace_revision": "8" * 64,
        }
    )
    opportunity = p32.opportunity_map.opportunities[0]
    citation = ObservationCitation(
        run_id=p32.run_id,
        lap_number=opportunity.source_laps[0],
        setup_id=setup_id,
        lap_pct_start=opportunity.start_pct,
        lap_pct_end=opportunity.end_pct,
        lap_pct_peak=(opportunity.start_pct + opportunity.end_pct) / 2.0,
        phase=opportunity.phase,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=("SteeringWheelAngle", "YawRate"),
        telemetry_sample_count=32,
    )
    observation = MechanismObservation(
        observation_id="p20-observation-corner-rotation",
        producer_id="p20.corner_rotation",
        artifact_id="observation-corner_rotation",
        source_run_ids=(p32.run_id,),
        source_setup_ids=(setup_id,),
        sample_coverage=1.0,
        mechanism=MechanismKind.CORNER_ROTATION,
        run_id=p32.run_id,
        setup_id=setup_id,
        lap_number=opportunity.source_laps[0],
        phase=opportunity.phase,
        lap_pct_start=opportunity.start_pct,
        lap_pct_end=opportunity.end_pct,
        lap_pct_peak=(opportunity.start_pct + opportunity.end_pct) / 2.0,
        summary="Higher steering demand with lower yaw response.",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        qualified=True,
        source_channels=("SteeringWheelAngle", "YawRate"),
        supporting_evidence=("typed-current-observation",),
        telemetry_sample_count=32,
        repetition_count=1,
        citations=(citation,),
    )
    report = MechanismObservationReport(
        status=ObservationStatus.READY,
        run_id=p32.run_id,
        setup_id=setup_id,
        observations=(observation,),
    )
    bundle = SimpleNamespace(
        report=SimpleNamespace(
            reasoning_snapshot=SimpleNamespace(causes=(), mechanism_episodes=()),
            mechanism_observations=report,
            data_quality=SimpleNamespace(status="ready"),
            lap_context=SimpleNamespace(contexts=()),
        )
    )
    return bundle, identity, p26, p32, p35


def _completed_before_p35() -> tuple[str, ...]:
    return (
        "inspect_data_quality",
        "inspect_lap_context",
        "inspect_lap_time_opportunity",
        "inspect_time_loss_origin",
        "inspect_corner_performance_chain",
        "inspect_exit_carry",
        "inspect_path_efficiency",
        "inspect_driver_vehicle_separation",
        "inspect_track_demand",
        "inspect_driver_execution",
        "inspect_p19_causes",
    )


def _folded(*, completed_tool_ids: tuple[str, ...]):
    return SimpleNamespace(
        status="open",
        completed_tool_ids=completed_tool_ids,
        hypotheses=(),
        driver_answers=("center",),
        objective=EngineeringObjective.QUALIFYING_PEAK,
        investigation_id="investigation-p35",
    )


def test_p35_focus_is_one_to_one_navigable_and_excluded_from_p34(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-index.sqlite3"))
    bundle, identity, p26, p32, p35 = _synthetic_focus_inputs(
        monkeypatch, tmp_path
    )

    evidence = _evidence_index(
        bundle,
        identity,
        EngineeringObjective.QUALIFYING_PEAK,
        p26,
        p32,
        _Repository(),
        p35=p35,
    )

    p35_entries = tuple(
        item for item in evidence.entries if item.producer_id.startswith("p35.")
    )
    assert {item.artifact_id for item in p35_entries} == {
        item.artifact_id for item in p35.focus_artifacts
    }
    assert all(
        item.typed_artifact.focus.inspection_tool_id.value
        == item.typed_artifact.inspection_tool_id
        and item.producer_id
        == f"p35.{item.typed_artifact.inspection_tool_id.removeprefix('inspect_')}"
        and item.typed_artifact.assessment_sha256 == p35.p35_assessment_sha256
        for item in p35_entries
    )
    p34_ids = set(p34_qualified_current_artifact_ids(identity, evidence))
    assert p34_ids.isdisjoint(item.artifact_id for item in p35_entries)

    hostile = p35_entries[0].model_dump(mode="python")
    hostile["typed_artifact"]["inspection_tool_id"] = "inspect_pitch_response"
    with pytest.raises(ValidationError, match="producer-owned inspection tool"):
        EngineeringEvidenceIndexEntry.model_validate(hostile)


def test_planner_uses_exact_p35_discriminator_before_other_p35_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-planner.sqlite3"))
    bundle, _identity_value, p26, p32, p35 = _synthetic_focus_inputs(
        monkeypatch, tmp_path
    )
    discriminator_tool = next(
        item.inspection_tool_id.value
        for item in p35.focus_artifacts
        if item.observation_contract_id == p35.next_discriminator_contract_id
    )

    subgoal = _subgoal(
        bundle,
        _folded(completed_tool_ids=_completed_before_p35()),
        p26,
        p32,
        p35=p35,
    )

    assert subgoal is not None
    assert subgoal.selected_tool == discriminator_tool


def test_blocked_p35_focus_is_not_auto_scheduled_or_admitted_to_p34(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    db_path = tmp_path / "p35-blocked-planner.sqlite3"
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    p32 = _build_public_projection(
        monkeypatch, tmp_path, effect_s=0.10, traffic=True
    )
    p20 = _p20_for_scope(p32, MechanismKind.CORNER_ROTATION)
    p32 = p32.model_copy(update={"p20_state_revision": p20.state_revision})
    p26 = _p26(p32)
    p26.component_states = ()
    p26.leading_component_ids = ()
    p35 = _assessment(p32, p20, p26=p26)
    bundle = SimpleNamespace(
        report=SimpleNamespace(
            reasoning_snapshot=SimpleNamespace(causes=(), mechanism_episodes=()),
            data_quality=SimpleNamespace(status="ready"),
            lap_context=SimpleNamespace(contexts=()),
        )
    )

    subgoal = _subgoal(
        bundle,
        _folded(completed_tool_ids=_completed_before_p35()),
        p26,
        p32,
        p35=p35,
    )

    assert subgoal is not None
    assert subgoal.selected_tool not in _P35_TOOL_IDS

    p35_workspace = SimpleNamespace(
        investigation=SimpleNamespace(investigation_id="investigation-p35"),
        folded_state=SimpleNamespace(status="open"),
        current_subgoal=SimpleNamespace(selected_tool="inspect_transient_settling"),
    )
    assert _freeze_p34_pair_for_workspace(p35_workspace, db_path=db_path) is None
    assert not db_path.exists()


def test_synthetic_telemetry_p20_p32_producers_feed_one_truthful_p35_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Exercise real P20/P32 producer paths before the typed-only P35 boundary."""

    monkeypatch.setenv("RACELAB_DB_PATH", str(tmp_path / "p35-producer-path.sqlite3"))
    # This helper drives synthetic position-aligned telemetry rows through the
    # production P32 builder. P35 itself never receives or rereads those rows.
    p32 = _build_public_projection(
        monkeypatch,
        tmp_path,
        effect_s=0.10,
        traffic=False,
    )
    opportunity = p32.opportunity_map.opportunities[0]
    citation = ObservationCitation(
        run_id=p32.run_id,
        lap_number=opportunity.source_laps[0],
        setup_id="setup-producer-path",
        lap_pct_start=opportunity.start_pct,
        lap_pct_end=opportunity.end_pct,
        lap_pct_peak=(opportunity.start_pct + opportunity.end_pct) / 2.0,
        phase=opportunity.phase,
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_channels=("SteeringWheelAngle", "YawRate"),
        telemetry_sample_count=64,
    )
    observation = MechanismObservation(
        observation_id="producer-corner-rotation",
        producer_id="p20.corner_rotation",
        artifact_id="producer-observation-corner-rotation",
        source_run_ids=(p32.run_id,),
        source_setup_ids=("setup-producer-path",),
        sample_coverage=1.0,
        mechanism=MechanismKind.CORNER_ROTATION,
        run_id=p32.run_id,
        setup_id="setup-producer-path",
        lap_number=opportunity.source_laps[0],
        phase=opportunity.phase,
        lap_pct_start=opportunity.start_pct,
        lap_pct_end=opportunity.end_pct,
        lap_pct_peak=(opportunity.start_pct + opportunity.end_pct) / 2.0,
        summary="Synthetic producer observed steering demand and yaw response.",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        qualified=True,
        source_channels=("SteeringWheelAngle", "YawRate"),
        supporting_evidence=("producer-owned synthetic observation",),
        telemetry_sample_count=64,
        repetition_count=1,
        citations=(citation,),
    )
    snapshot = SimpleNamespace(
        causes=(
            SimpleNamespace(
                cause_id=f"observation:{observation.observation_id}",
            ),
        ),
        mechanism_episodes=(),
        mechanism_episode_blocker_reasons=(),
        blocker_reasons=(),
        controlled_outcomes=(),
    )
    producer_bundle = SimpleNamespace(
        report=SimpleNamespace(
            run_id=p32.run_id,
            session_id=p32.session_id,
            reasoning_snapshot=snapshot,
            mechanism_observations=MechanismObservationReport(
                status=ObservationStatus.READY,
                run_id=p32.run_id,
                setup_id="setup-producer-path",
                observations=(observation,),
            ),
            blocker_reasons=(),
        ),
        awareness=SimpleNamespace(
            frames=(),
            transitions=(),
            episodes=(),
            control_mutations=(),
            blocker_reasons=(),
        ),
    )
    trust_budget = _p20_for_scope(
        p32,
        MechanismKind.CORNER_ROTATION,
    ).trust_budget
    monkeypatch.setattr(
        engineering_projection_service,
        "_trust_budget",
        lambda _bundle: trust_budget,
    )
    p20 = engineering_projection_service.project_engineering_awareness(
        producer_bundle
    )
    p32 = p32.model_copy(
        update={
            "p19_reasoning_snapshot_sha256": p20.reasoning_snapshot_id,
            "p20_state_revision": p20.state_revision,
            "projection_sha256": canonical_json_sha256(
                [p32.projection_sha256, p20.state_revision, "producer-path"]
            ),
        }
    )
    p32 = _exact_response_projection(p32, p20)
    p32_payload = p32.model_dump(mode="json", exclude={"projection_sha256"})
    p32 = PerformanceIntelligenceProjection.model_validate(
        {
            **p32_payload,
            "projection_sha256": canonical_json_sha256(p32_payload),
        }
    )
    p26 = _p26(p32)
    assessment = build_vehicle_dynamics_assessment(
        run_id=p32.run_id,
        session_id=p32.session_id,
        objective_id=p32.objective_id,
        p19_reasoning_snapshot_sha256=p20.reasoning_snapshot_id,
        p20=p20,
        p26=p26,
        p32=p32,
    )

    assert p20.primary_state is not None
    assert p20.primary_state.source_artifact_ids == (observation.artifact_id,)
    assert assessment.measured_time_consequence_available
    assert any(candidate.relevance == "candidate" for candidate in assessment.candidates)
    assert assessment.strongest_support_artifact_id is not None
    assert assessment.component_causal_claim_count == 0
    assert assessment.setup_authorized is False


@pytest.mark.integration
def test_real_atlanta_p35_is_read_only_traffic_blocked_and_authority_invariant(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    source_db = Path("data/racelab.sqlite")
    if not source_db.exists():
        pytest.skip("Persisted real Atlanta fixture is unavailable")
    db_path = tmp_path / "p35-real-atlanta.sqlite3"
    shutil.copyfile(source_db, db_path)
    monkeypatch.setenv("RACELAB_DB_PATH", str(db_path))
    # A copied SQLite file is deliberately opened once through the schema
    # initializer before the purity boundary.  That separates SQLite's
    # journal/schema-open bookkeeping from the workspace GET we are proving.
    initializer = initialize_database(db_path)
    initializer.close()
    run_id = "stockcars-chevycamarozl12022-atlanta-2022-oval-2-37e380eb"
    session_id = "session_ed52db305244"
    before_sha256 = hashlib.sha256(db_path.read_bytes()).hexdigest()
    before_mtime = db_path.stat().st_mtime_ns

    typed_p35_inputs: dict[str, object] = {}
    p35_builder = crew_chief_service.build_vehicle_dynamics_assessment

    def capture_p35_inputs(**kwargs):
        typed_p35_inputs.update(kwargs)
        return p35_builder(**kwargs)

    monkeypatch.setattr(
        crew_chief_service,
        "build_vehicle_dynamics_assessment",
        capture_p35_inputs,
    )

    workspace = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        db_path=db_path,
    )

    p35 = workspace.vehicle_dynamics
    knowledge = workspace.engineering_knowledge
    graph = compile_next_gen_oval_knowledge_graph()
    assert workspace.schema_version == "p352.crew-chief-workspace.v1"
    assert (p35.graph_id, p35.graph_version, p35.knowledge_graph_sha256) == (
        graph.graph_id,
        graph.graph_version,
        graph.content_sha256,
    )
    assert (
        graph.graph_id,
        graph.graph_version,
        graph.knowledge_version,
        graph.content_sha256,
    ) == (
        "p35vdg_c14af7ad22a752df5710a6e6",
        "2026.08.next-gen-oval.v1:c14af7ad22a7",
        "2026.08.p35-next-gen-oval.v1",
        "c14af7ad22a752df5710a6e695b50f085fa4d15ecb20b271b3dc6205e3113030",
    )
    assert p35.measured_time_consequence_available
    assert p35.traffic_blocked
    assert p35.candidates
    assert {item.relevance for item in p35.candidates} == {"blocked"}
    assert p35.strongest_support_artifact_id is None
    assert p35.strongest_contradiction_artifact_id is not None
    assert p35.next_discriminator_contract_id is not None
    assert p35.component_causal_claim_count == 0
    assert p35.setup_authorized is False
    assert p35.terminal_authority == "p19_only"
    assert len(knowledge.hypotheses) == 92
    assert knowledge.p32_opportunity_id == p35.performance_opportunity_ids[0]
    assert knowledge.p35_assessment_sha256 == p35.p35_assessment_sha256
    assert knowledge.terminal_authority == "p19_only"
    assert knowledge.non_p19_setup_authorized is False
    assert all(not item.setup_authorized for item in knowledge.hypotheses)
    tools = {item.tool_id: item for item in workspace.available_tools}
    assert tools["inspect_setup_knowledge_for_mechanism"].required_sources == (
        "p351",
        "p35",
        "p32",
    )
    assert tools["inspect_control_experiment_contract"].required_sources == (
        "p351",
        "p19",
        "p26",
    )
    knowledge_tool_entries = _select_tool_entries(
        workspace, "inspect_setup_knowledge_for_mechanism", ()
    )
    assert knowledge_tool_entries
    assert all(
        item.producer_id.startswith("p35.")
        for item in knowledge_tool_entries
    )
    control_tool_entries = _select_tool_entries(
        workspace, "inspect_control_experiment_contract", ()
    )
    assert control_tool_entries
    assert all(
        item.producer_id
        in {
            "p19.reasoning_snapshot",
            "p26.component_awareness",
            "p26.component_state_unavailable",
        }
        for item in control_tool_entries
    )
    assert workspace.performance_intelligence.speed_story.observed_difference_s == (
        pytest.approx(0.136447)
    )
    assert (
        workspace.performance_intelligence.speed_story.attribution_state
        == "blocked_by_traffic"
    )

    # Cache replay is the same scientific workspace.  Only response-delivery
    # metadata may change between the cold and warm representation.
    replay = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        db_path=db_path,
    )
    assert replay.model_dump(
        mode="json", exclude={"generated_at", "cache_state"}
    ) == workspace.model_dump(
        mode="json", exclude={"generated_at", "cache_state"}
    )
    assert workspace.engineering_awareness is not None
    assert replay.engineering_awareness is not None
    assert workspace.identity.p20_projection_sha256 == (
        engineering_awareness_scientific_sha256(workspace.engineering_awareness)
    )
    assert replay.identity.p20_projection_sha256 == (
        workspace.identity.p20_projection_sha256
    )
    captured_awareness = typed_p35_inputs["p20"]
    delivery_variant = captured_awareness.model_copy(
        update={
            "cache_state": "warm",
            "build_duration_ms": captured_awareness.build_duration_ms + 99.0,
        }
    )
    assert engineering_awareness_scientific_sha256(delivery_variant) == (
        workspace.identity.p20_projection_sha256
    )

    bad_index = workspace.model_dump(mode="python")
    bad_index["evidence_index"]["entries"][0]["phase"] = "forged-phase"
    with pytest.raises(ValidationError, match="index hash"):
        CrewChiefWorkspace.model_validate(bad_index)

    quiet_payload = p35.model_dump(
        mode="python", exclude={"p35_assessment_sha256"}
    )
    quiet_candidates = tuple(
        candidate.model_copy(
            update={
                "blocker_reasons": tuple(
                    dict.fromkeys(
                        (
                            *candidate.blocker_reasons,
                            "Synthetic non-authoritative P35 narrative variant.",
                        )
                    )
                )
            }
        )
        for candidate in p35.candidates
    )
    quiet_payload.update(
        candidates=quiet_candidates,
        mechanism_separation=tuple(
            row.model_copy(
                update={
                    "missing_evidence": quiet_candidates[index].blocker_reasons,
                }
            )
            for index, row in enumerate(p35.mechanism_separation)
        ),
        blocker_reasons=tuple(
            dict.fromkeys(
                (*p35.blocker_reasons, "Synthetic P35 narrative variant.")
            )
        ),
    )
    quiet = build_performance_mechanism_assessment(quiet_payload)
    monkeypatch.setattr(
        crew_chief_service,
        "build_vehicle_dynamics_assessment",
        lambda **_kwargs: quiet,
    )
    with crew_chief_service._CACHE_LOCK:
        crew_chief_service._CACHE.clear()
    without_attention = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        db_path=db_path,
    )

    assert workspace.identity.workspace_revision != (
        without_attention.identity.workspace_revision
    )
    assert workspace.identity.authority_revision == (
        without_attention.identity.authority_revision
    )
    assert workspace.identity.reasoning_snapshot_sha256 == (
        without_attention.identity.reasoning_snapshot_sha256
    )
    assert workspace.identity.setup_id == without_attention.identity.setup_id
    assert workspace.identity.setup_snapshot_sha256 == (
        without_attention.identity.setup_snapshot_sha256
    )
    assert workspace.performance_intelligence == (
        without_attention.performance_intelligence
    )
    assert workspace.p19_cause_ids == without_attention.p19_cause_ids
    assert workspace.p19_mission_contract == without_attention.p19_mission_contract
    assert workspace.terminal_decision == without_attention.terminal_decision

    def reject_lower_telemetry(*_args, **_kwargs):
        raise AssertionError("P35 must not read raw/lower telemetry")

    # Rebuild the public P35 assessment from the producer-owned typed inputs
    # captured at the Crew boundary while every lower telemetry seam is fatal.
    # Re-validating the complete public workspace proves the resulting P35 DTO
    # remains attached to the same atomic evidence index and identity contract.
    monkeypatch.setattr(import_service, "read_telemetry_rows", reject_lower_telemetry)
    monkeypatch.setattr(import_service, "read_telemetry_manifest", reject_lower_telemetry)
    monkeypatch.setattr(
        run_intelligence_service, "read_telemetry_rows", reject_lower_telemetry
    )
    monkeypatch.setattr(
        run_intelligence_service, "read_telemetry_manifest", reject_lower_telemetry
    )
    monkeypatch.setattr(RaceLabRepository, "get_laps", reject_lower_telemetry)
    monkeypatch.setattr(RaceLabRepository, "list_segments", reject_lower_telemetry)
    monkeypatch.setattr(RaceLabRepository, "get_segment", reject_lower_telemetry)
    rebuilt_p35 = p35_builder(**typed_p35_inputs)
    assert rebuilt_p35 == p35
    public_payload = workspace.model_dump(mode="python")
    public_payload["vehicle_dynamics"] = rebuilt_p35
    assert CrewChiefWorkspace.model_validate(public_payload).vehicle_dynamics == p35

    first_candidate = p35.candidates[0]
    leading_opportunity = workspace.performance_intelligence.opportunity_map.opportunities[0]
    trust = next(
        item
        for item in compile_next_gen_oval_runtime_trust_manifest().mechanisms
        if item.mechanism_id == first_candidate.mechanism_id
    )
    forged_p20_id = "p20-forged-current-support"
    forged_support_id = _focus_id(
        trust.inspection_tool_id.value,
        leading_opportunity.opportunity_id,
        first_candidate.mechanism_id,
        forged_p20_id,
        "support",
    )
    forged_support = VehicleDynamicsFocusArtifact(
        artifact_id=forged_support_id,
        mechanism_id=first_candidate.mechanism_id,
        observation_contract_id=None,
        inspection_tool_id=trust.inspection_tool_id,
        stage="vehicle_response",
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        source_artifact_ids=(forged_p20_id,),
        source_channels=leading_opportunity.source_channels,
        lap_numbers=(leading_opportunity.source_laps[0],),
        lap_pct_start=leading_opportunity.start_pct,
        lap_pct_end=leading_opportunity.end_pct,
        phase=leading_opportunity.phase,
        polarity="support",
        summary="Forged positive support despite typed traffic context.",
    )
    traffic_rehash_payload = p35.model_dump(
        mode="python", exclude={"p35_assessment_sha256"}
    )
    traffic_rehash_payload["candidates"] = tuple(
        candidate.model_copy(
            update={
                "relevance": "candidate",
                "blocker_reasons": (),
                "support_artifact_ids": (forged_support_id,),
            }
        )
        if candidate.mechanism_id == first_candidate.mechanism_id
        else candidate
        for candidate in p35.candidates
    )
    traffic_rehash_payload["focus_artifacts"] = (
        *p35.focus_artifacts,
        forged_support,
    )
    traffic_rehash_payload["chain"] = tuple(
        stage.model_copy(
            update={
                "evidence_state": EvidenceState.OBSERVED_CORRELATION,
                "source_artifact_ids": tuple(
                    dict.fromkeys((*stage.source_artifact_ids, forged_p20_id))
                ),
                "source_channels": forged_support.source_channels,
                "summary": "Forged current P20/P32 response support.",
                "blocker_reasons": (),
            }
        )
        if stage.stage.value == "vehicle_response"
        else stage
        for stage in p35.chain
    )
    traffic_rehash_payload["strongest_support_artifact_id"] = forged_support_id
    traffic_rehash_payload["mechanism_separation"] = tuple(
        row.model_copy(
            update={
                "state": "alive",
                "support_artifact_ids": (forged_support_id,),
                "missing_evidence": (
                    "The forged candidate still lacks a controlled discriminator.",
                ),
            }
        )
        if row.mechanism_id == first_candidate.mechanism_id
        else row
        for row in p35.mechanism_separation
    )
    with pytest.raises(ValidationError, match="matched demand, line, response, and context"):
        build_performance_mechanism_assessment(traffic_rehash_payload)

    foreign_component_payload = p35.model_dump(
        mode="python", exclude={"p35_assessment_sha256"}
    )
    foreign_component_payload["candidates"] = tuple(
        candidate.model_copy(
            update={"component_family_ids": ("invented_component_family",)}
        )
        if candidate.mechanism_id == first_candidate.mechanism_id
        else candidate
        for candidate in p35.candidates
    )
    foreign_component_payload["mechanism_separation"] = tuple(
        row.model_copy(
            update={"component_family_ids": ("invented_component_family",)}
        )
        if row.mechanism_id == first_candidate.mechanism_id
        else row
        for row in p35.mechanism_separation
    )
    foreign_component = build_performance_mechanism_assessment(
        foreign_component_payload
    )
    with pytest.raises(ValidationError, match="runtime trust manifest"):
        CrewChiefWorkspace.model_validate(
            _coordinated_p35_workspace_payload(workspace, foreign_component)
        )

    foreign_runtime_payload = p35.model_dump(
        mode="python", exclude={"p35_assessment_sha256"}
    )
    foreign_runtime_payload["car_path"] = "stockcars fordmustang2022"
    foreign_runtime = build_performance_mechanism_assessment(
        foreign_runtime_payload
    )
    with pytest.raises(
        ValidationError, match="atomic non-authoritative Crew workspace"
    ):
        CrewChiefWorkspace.model_validate(
            _coordinated_p35_workspace_payload(workspace, foreign_runtime)
        )

    renamed_focus_source = p35.focus_artifacts[0]
    prefix = renamed_focus_source.artifact_id.rsplit(":", 1)[0]
    renamed_focus_id = f"{prefix}:{'f' * 24}"
    if renamed_focus_id == renamed_focus_source.artifact_id:
        renamed_focus_id = f"{prefix}:{'e' * 24}"
    renamed_focus = renamed_focus_source.model_copy(
        update={"artifact_id": renamed_focus_id}
    )
    renamed_focus_payload = p35.model_dump(
        mode="python", exclude={"p35_assessment_sha256"}
    )
    renamed_focus_payload["focus_artifacts"] = tuple(
        renamed_focus if item.artifact_id == renamed_focus_source.artifact_id else item
        for item in p35.focus_artifacts
    )
    renamed_focus_payload["candidates"] = tuple(
        candidate.model_copy(
            update={
                "support_artifact_ids": tuple(
                    renamed_focus_id
                    if value == renamed_focus_source.artifact_id
                    else value
                    for value in candidate.support_artifact_ids
                ),
                "contradiction_artifact_ids": tuple(
                    renamed_focus_id
                    if value == renamed_focus_source.artifact_id
                    else value
                    for value in candidate.contradiction_artifact_ids
                ),
            }
        )
        for candidate in p35.candidates
    )
    renamed_focus_payload["mechanism_separation"] = tuple(
        row.model_copy(
            update={
                "support_artifact_ids": tuple(
                    renamed_focus_id
                    if value == renamed_focus_source.artifact_id
                    else value
                    for value in row.support_artifact_ids
                ),
                "contradiction_artifact_ids": tuple(
                    renamed_focus_id
                    if value == renamed_focus_source.artifact_id
                    else value
                    for value in row.contradiction_artifact_ids
                ),
            }
        )
        for row in p35.mechanism_separation
    )
    if (
        renamed_focus_payload["strongest_support_artifact_id"]
        == renamed_focus_source.artifact_id
    ):
        renamed_focus_payload["strongest_support_artifact_id"] = renamed_focus_id
    if (
        renamed_focus_payload["strongest_contradiction_artifact_id"]
        == renamed_focus_source.artifact_id
    ):
        renamed_focus_payload["strongest_contradiction_artifact_id"] = renamed_focus_id
    renamed_assessment = build_performance_mechanism_assessment(
        renamed_focus_payload
    )
    with pytest.raises(ValidationError, match="canonical producer formula"):
        CrewChiefWorkspace.model_validate(
            _coordinated_p35_workspace_payload(
                workspace,
                renamed_assessment,
                artifact_id_map={
                    renamed_focus_source.artifact_id: renamed_focus_id
                },
            )
        )

    unavailable_payload = p35.model_dump(
        mode="python", exclude={"p35_assessment_sha256"}
    )
    unavailable_payload["unavailable_quantity_ids"] = tuple(
        (*p35.unavailable_quantity_ids[1:], "quantity:invented_exact_force")
    )
    unavailable = build_performance_mechanism_assessment(unavailable_payload)
    with pytest.raises(ValidationError, match="frozen contract"):
        CrewChiefWorkspace.model_validate(
            _coordinated_p35_workspace_payload(workspace, unavailable)
        )

    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_sha256
    assert db_path.stat().st_mtime_ns == before_mtime
