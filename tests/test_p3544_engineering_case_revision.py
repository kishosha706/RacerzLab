from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from api.routes_engineering_case import (
    AtomicDriverIntentWorkflowRequest,
    get_current_engineering_case,
    submit_atomic_driver_intent_workflow,
)

from racelab_engine.identity import canonical_json_sha256
from racelab_engine.knowledge.engineering_semantic_registry import (
    compile_engineering_semantic_registry,
)
from racelab_engine.models.engineering_case import (
    CanonicalEngineeringCase,
    EngineeringCaseCampaignCapture,
    EngineeringMission,
    EngineeringSemanticFocusState,
    SetupEffectReadiness,
)
from racelab_engine.services.engineering_case_service import engineering_case_id
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_case_repository import (
    EngineeringCaseIntegrityError,
    EngineeringCaseRepository,
)
from racelab_engine.storage.repository import RaceLabRepository


RUN_ID = "p3544-run"
SESSION_ID = "p3544-session"
WORKSPACE = "a" * 64


def _seed_run(db_path) -> None:
    connection = initialize_database(db_path)
    connection.execute(
        """
        INSERT INTO runs(
          run_id, source_file, file_hash, import_time, imported_at, session_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_ID,
            "synthetic.ibt",
            "1" * 64,
            "2026-08-20T00:00:00+00:00",
            "2026-08-20T00:00:00+00:00",
            "{}",
        ),
    )
    connection.commit()
    connection.close()


def _case(*, next_move: str = "Collect exact evidence.", driver_intent=None):
    case_id = engineering_case_id(run_id=RUN_ID, session_id=SESSION_ID)
    terminal = canonical_json_sha256({"next": next_move})
    mission = EngineeringMission(
        what="Measure the current problem",
        where="center · 20.0–30.0%",
        why_it_matters="Current P19 evidence requires measurement.",
        uncertain="Cause remains unresolved.",
        next=next_move,
        done_when="Three independent laps clear the contract.",
        source_authority="p19_measurement_mirror",
        terminal_move_sha256=terminal,
    )
    return CanonicalEngineeringCase.build(
        case_id=case_id,
        case_revision_sha256=WORKSPACE,
        run_id=RUN_ID,
        session_id=SESSION_ID,
        recording_sha256="1" * 64,
        setup_id="setup-p3544",
        setup_snapshot_sha256="2" * 64,
        objective_id="race_long_run",
        condition_epoch_sha256="3" * 64,
        p19_reasoning_snapshot_sha256="4" * 64,
        p20_state_revision="5" * 64,
        p26_knowledge_graph_sha256="6" * 64,
        p32_projection_sha256="7" * 64,
        p35_assessment_sha256="8" * 64,
        p351_projection_sha256="9" * 64,
        p33_projection_sha256="b" * 64,
        semantic_registry_sha256=(
            compile_engineering_semantic_registry().registry_sha256
        ),
        evidence_index_sha256="c" * 64,
        driver_intent=driver_intent,
        effect_readiness=(
            SetupEffectReadiness(
                effect_id="effect:synthetic",
                bridge_id="p351b_" + "d" * 24,
                state="knowledge_only",
                missing_evidence=("Exact response evidence is unavailable.",),
                authority="knowledge_only",
            ),
        ),
        workspace_revision=WORKSPACE,
        terminal_move_sha256=terminal,
        mission=mission,
        semantic_focus=EngineeringSemanticFocusState(
            case_id=case_id,
            case_revision_sha256=WORKSPACE,
        ),
        campaign_capture=EngineeringCaseCampaignCapture(
            state="pending",
            blocker_reasons=("Real P36 evidence is not qualified.",),
        ),
    )


def test_case_revision_stream_is_immutable_idempotent_and_restart_safe(tmp_path) -> None:
    db_path = tmp_path / "case.sqlite"
    _seed_run(db_path)
    repository = EngineeringCaseRepository(db_path)
    first_case = _case()
    first = repository.finalize_case(
        first_case,
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    repeated = repository.finalize_case(
        first_case,
        created_at=datetime(2026, 8, 20, tzinfo=UTC) + timedelta(hours=1),
    )
    assert repeated == first
    assert first.case_revision == 1
    assert first.previous_case_sha256 is None

    second_case = _case(next_move="Repeat the exact measurement.")
    second = repository.finalize_case(second_case, change_category="evidence")
    assert second.case_id == first.case_id
    assert second.case_revision == 2
    assert second.case_sha256 != first.case_sha256
    assert second.previous_case_sha256 == first.case_sha256
    assert EngineeringCaseRepository(db_path).current(first.case_id) == second
    history = repository.history(first.case_id)
    assert [item.case_revision for item in history] == [2, 1]
    assert history[0].previous_case_sha256 == history[1].case_sha256


def test_driver_intent_is_append_only_context_and_corrupt_case_fails_closed(tmp_path) -> None:
    db_path = tmp_path / "case.sqlite"
    _seed_run(db_path)
    repository = EngineeringCaseRepository(db_path)
    first = repository.finalize_case(_case())
    intent = repository.append_driver_intent(
        case_id=first.case_id,
        raw_driver_wording="Tight after five laps, mostly center.",
        canonical_symptom="tight_center",
        phase_scope="center",
        response_regime_scope="migration",
        stint_context="after_five_laps",
        objective="race_long_run",
        source="manual",
        typed_interpretation_provenance=("driver-wording",),
    )
    assert intent.physical_truth_modified is False
    assert intent.setup_authorized is False
    assert repository.current_driver_intent(first.case_id) == intent

    connection = initialize_database(db_path)
    connection.execute(
        "UPDATE engineering_case_revisions SET revision_json = ? WHERE case_id = ?",
        ("{}", first.case_id),
    )
    connection.commit()
    connection.close()
    with pytest.raises(EngineeringCaseIntegrityError, match="unreadable or corrupt"):
        repository.current(first.case_id)


def test_case_api_finalizes_current_revision_and_atomic_workflow_failure_rolls_back_intent(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "case.sqlite"
    _seed_run(db_path)
    case = _case()
    race_repository = RaceLabRepository(db_path)
    monkeypatch.setattr(
        "api.routes_engineering_case.RaceLabRepository",
        lambda: race_repository,
    )
    monkeypatch.setattr(
        "api.routes_engineering_case.EngineeringCaseRepository",
        lambda db_path=None: EngineeringCaseRepository(db_path or race_repository.db_path),
    )
    workspace = type(
        "Workspace",
        (),
        {
            "engineering_case": case,
            "engineering_knowledge": object(),
            "terminal_decision": object(),
        },
    )()
    monkeypatch.setattr(
        "api.routes_engineering_case.build_crew_chief_workspace",
        lambda *args, **kwargs: workspace,
    )
    revision = get_current_engineering_case(
        RUN_ID, SESSION_ID, expected_case_sha256=None
    )
    assert revision.case_sha256 == case.case_sha256

    monkeypatch.setattr(
        "api.routes_engineering_case.build_dial_in_response",
        lambda *args, **kwargs: type(
            "Advisory", (), {"interpreted_symptom": "tight_center"}
        )(),
    )
    monkeypatch.setattr(
        "api.routes_engineering_case.DialInHypothesisResponse.from_internal",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "api.routes_engineering_case.build_authorized_workflow_candidate",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "api.routes_engineering_case.persist_workflow_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("workflow persistence failed")
        ),
    )
    request = AtomicDriverIntentWorkflowRequest(
        run_id=RUN_ID,
        session_id=SESSION_ID,
        complaint="Tight center after five laps.",
        expected_case_sha256=case.case_sha256,
        objective="race-pace",
        priority="overall-pace",
    )
    with pytest.raises(HTTPException, match="workflow persistence failed"):
        submit_atomic_driver_intent_workflow(RUN_ID, request)
    assert EngineeringCaseRepository(db_path).current_driver_intent(case.case_id) is None
