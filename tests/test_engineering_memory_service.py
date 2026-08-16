from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from racelab_engine.analysis.crew_chief_packet import (
    CauseCandidate,
    OpportunityEvidence,
    build_kaizen_packet,
)
from racelab_engine.analysis.test_director import (
    TestEvidenceLink,
    TestExecution,
    TestQualityResult as WorkflowQualityResult,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.engineering_memory import (
    DriverPresentationObservation,
    EngineeringNarrativeEntry,
)
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.services import controlled_workflow_service
from racelab_engine.services.engineering_memory_service import (
    build_prediction_contract,
    get_driver_presentation_profile,
    get_driver_presentation_profile_for_run,
    get_prediction_calibration,
    get_prediction_contract,
    get_prediction_grade,
    list_engineering_narrative,
    presentation_profile_identity,
    record_driver_presentation_preference,
    record_driver_presentation_preference_for_run,
    record_workflow_outcome,
    record_workflow_plan,
    record_workflow_stage,
    save_driver_presentation_observation,
    save_narrative_entry,
    save_prediction_contract,
)
from racelab_engine.services.session_service import add_run_to_session, create_session
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _packet(*, exact_prediction: bool = True):
    link = TestEvidenceLink(
        event_id="event-entry-17",
        eligible_lap=True,
        valid_for_tuning=True,
        phase="entry",
        related_setup_keys=("cross_weight_percent",),
    )
    packet = build_kaizen_packet(
        opportunity=OpportunityEvidence(
            start_pct=20.0,
            end_pct=30.0,
            phase="entry",
            observed_time_loss_s=0.2,
            empirical_noise_s=0.01,
            alignment_confidence=0.95,
            repeatable=True,
            evidence_links=(link,),
            source_channels=("lap_dist_pct_100", "speed_mps"),
            supporting_evidence=("Entry loss repeated on three eligible laps.",),
        ),
        canonical_symptom="tight_entry",
        candidates=[
            CauseCandidate(
                cause_bucket="corner_balance",
                effect_id="add_crossweight_small",
                control_key="cross_weight_percent",
                direction_sign=1,
                experiment_factor_id="factor:crossweight",
                score=0.9,
                hypothesis="Test whether a small cross-weight increase reduces entry time.",
                success_metrics=("Entry time improves without a center-time loss.",),
                countereffects=(
                    "Median non-target phase time must not worsen beyond empirical noise.",
                ),
                supporting_event_ids=("event-entry-17",),
            )
        ],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={
            "cross_weight_percent": {"50.5": ["tech-passing-setup:option-run"]}
        },
    )
    if exact_prediction:
        packet = packet.model_copy(
            update={
                "recommendation_score_components": {
                    **packet.recommendation_score_components,
                    "personal_model_prediction_s": -0.06,
                    "personal_model_uncertainty_s": 0.02,
                }
            }
        )
    return packet


def _planned_workflow(
    workflow_id: str = "aba-memory",
    *,
    source_run_id: str = "source-run",
    exact_prediction: bool = True,
) -> ControlledWorkflow:
    return ControlledWorkflow(
        workflow_id=workflow_id,
        created_at=NOW,
        updated_at=NOW,
        status="planned",
        source_run_id=source_run_id,
        complaint="It pushes on entry",
        packet=_packet(exact_prediction=exact_prediction),
    )


def _scored_workflow(
    workflow_id: str = "aba-memory",
    *,
    source_run_id: str = "source-run",
    driver_match_score: float = 0.94,
    verdict: str = "keep",
) -> ControlledWorkflow:
    planned = _planned_workflow(workflow_id, source_run_id=source_run_id)
    return planned.model_copy(
        update={
            "updated_at": NOW + timedelta(hours=1),
            "status": "scored",
            "stage_run_ids": {
                "A": f"{source_run_id}-a",
                "B": f"{source_run_id}-b",
                "A2": f"{source_run_id}-a2",
            },
            "stage_eligible_lap_numbers": {
                "A": (3, 4, 5),
                "B": (3, 4, 5),
                "A2": (3, 4, 5),
            },
            "execution": TestExecution(
                eligible_laps_a=3,
                eligible_laps_b=3,
                eligible_laps_a2=3,
                unrelated_setup_changes=0,
                control_key="cross_weight_percent",
                planned_b_value=50.5,
                observed_a_value=50.0,
                observed_b_value=50.5,
                observed_a2_value=50.0,
                context_match_score=0.96,
                driver_match_score=driver_match_score,
                sim_integrity_score=0.98,
                phase_effect_b_vs_a_s=-0.05,
                phase_effect_b_vs_a2_s=-0.05,
                empirical_noise_s=0.01,
                empirical_noise_observations=4,
                minimum_alignment_confidence=0.93,
                target_effect_distributions_consistent=True,
                target_effect_distribution_state="faster",
                countereffect_passed=True,
                control_guardrails_passed=True,
            ),
            "quality": WorkflowQualityResult(
                protocol_valid=True,
                score=91.0,
                verdict=verdict,
                blockers=(),
                supporting_evidence=("B beat A and A2 beyond noise.",),
                contradictory_evidence=(),
                controlled_effect_eligible=True,
            ),
            "reproduction_snapshot": {
                "pooled_target_effect_s": -0.05,
                "decision_context": {"objective": "setup-development"},
            },
            "learning_admitted": verdict == "keep",
        }
    )


def _overview(run_id: str) -> RunOverview:
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            source_file=f"{run_id}.ibt",
            car_name="Test Car",
            track_name="test_track",
            setup_passed_tech=True,
        ),
    )


def test_prediction_contract_freezes_supported_range_thresholds_and_evidence() -> None:
    contract = build_prediction_contract(_planned_workflow())

    assert contract.support == "exact_context_model"
    assert contract.expected_direction == "decrease"
    assert contract.expected_range_s == pytest.approx((-0.08, -0.04))
    assert contract.score_is_probability is False
    assert "not a calibrated probability" in contract.score_basis
    assert any("-0.010000 s" in threshold for threshold in contract.success_thresholds)
    assert {(ref.kind, ref.reference_id) for ref in contract.evidence_references} >= {
        ("run", "source-run"),
        ("workflow", "aba-memory"),
        ("event", "event-entry-17"),
        ("channel", "speed_mps"),
        ("setup", "tech-passing-setup:option-run"),
    }


def test_prediction_contract_withholds_numeric_range_without_exact_context_history() -> None:
    contract = build_prediction_contract(_planned_workflow(exact_prediction=False))

    assert contract.support == "mechanism_evidence"
    assert contract.expected_direction == "decrease"
    assert contract.expected_range_s is None
    assert "no qualified numeric response range" in contract.score_basis


def test_prediction_grade_uses_actual_controlled_effect_and_never_calls_score_probability(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite"
    planned = _planned_workflow()
    scored = _scored_workflow()
    record_workflow_plan(planned, db_path=db_path)

    grade = record_workflow_outcome(scored, db_path=db_path)

    assert grade.actual_effect_s == pytest.approx(-0.05)
    assert grade.actual_direction == "decrease"
    assert grade.direction_result == "matched"
    assert grade.range_result == "inside"
    assert grade.grade_label == "matched_direction_and_range"
    assert grade.protocol_evidence_score == 91.0
    assert grade.score_is_probability is False
    assert "Ordinal" in grade.score_basis
    assert get_prediction_grade(scored.workflow_id, db_path=db_path) == grade


def test_prediction_calibration_counts_only_exact_scope_protocol_valid_gradable_results(tmp_path) -> None:
    db_path = tmp_path / "calibration.sqlite"
    for workflow_id, source_run in (
        ("aba-valid", "source-run"),
        ("aba-other-session", "other-run"),
    ):
        record_workflow_plan(
            _planned_workflow(workflow_id, source_run_id=source_run), db_path=db_path
        )
        record_workflow_outcome(
            _scored_workflow(workflow_id, source_run_id=source_run), db_path=db_path
        )
    invalid = _scored_workflow("aba-invalid", source_run_id="source-run")
    invalid = invalid.model_copy(update={
        "quality": invalid.quality.model_copy(update={
            "protocol_valid": False,
            "verdict": "invalid",
            "score": 42.0,
            "controlled_effect_eligible": False,
        })
    })
    record_workflow_plan(
        _planned_workflow("aba-invalid", source_run_id="source-run"), db_path=db_path
    )
    record_workflow_outcome(invalid, db_path=db_path)

    summary = get_prediction_calibration(
        session_run_ids=("source-run", "unrelated-stage-run"), db_path=db_path
    )

    assert summary.scope_run_ids == ("source-run", "unrelated-stage-run")
    assert summary.source_run_ids == ("source-run",)
    assert summary.workflow_ids == ("aba-valid",)
    assert summary.graded_predictions == 1
    assert summary.matched_predictions == 1
    assert summary.score_is_probability is False
    assert "not a calibrated probability" in summary.basis


def test_engineering_memory_is_idempotent_but_rejects_a_conflicting_rewrite(tmp_path) -> None:
    db_path = tmp_path / "immutable.sqlite"
    contract = build_prediction_contract(_planned_workflow())
    assert save_prediction_contract(contract, db_path=db_path) == contract
    assert save_prediction_contract(contract, db_path=db_path) == contract

    changed = contract.model_copy(update={"rollback_rule": "Silently replace history."})
    with pytest.raises(ValueError, match="immutable prediction contract"):
        save_prediction_contract(changed, db_path=db_path)


def test_session_narrative_covers_the_engineering_chain_with_exact_references(tmp_path) -> None:
    db_path = tmp_path / "narrative.sqlite"
    session = create_session("Test night", db_path=db_path)
    add_run_to_session(session.session_id, "source-run", db_path=db_path)
    planned = _planned_workflow()
    scored = _scored_workflow(verdict="undo")

    record_workflow_plan(planned, db_path=db_path)
    record_workflow_stage(scored, "B", db_path=db_path)
    record_workflow_outcome(scored, db_path=db_path)
    entries = list_engineering_narrative(session_id=session.session_id, db_path=db_path)

    assert {entry.entry_type for entry in entries} >= {
        "complaint",
        "hypothesis",
        "measurement",
        "change",
        "outcome",
        "rollback",
        "learning",
    }
    assert all(entry.workflow_id == "aba-memory" for entry in entries)
    assert all("source-run" in entry.run_ids for entry in entries)
    assert all(
        ("workflow", "aba-memory")
        in {(reference.kind, reference.reference_id) for reference in entry.evidence_references}
        for entry in entries
    )


def test_driver_profile_is_context_scoped_and_presentation_only(tmp_path) -> None:
    db_path = tmp_path / "driver-profile.sqlite"
    context = {
        "car_id": "nextgen",
        "track_id": "atlanta",
        "track_configuration_name": "oval",
        "iracing_build_version": "2026.08",
    }
    other_context = {**context, "track_id": "bristol"}
    record_driver_presentation_preference(
        driver_id="driver-7",
        context=context,
        source_key="settings:driver-7:atlanta:v1",
        preferred_mode="learning",
        terminology_level="engineering",
        db_path=db_path,
    )
    profile_id, context_key, scope = presentation_profile_identity("driver-7", context)
    for index, symptom in enumerate(("tight_entry", "tight_entry", "loose_exit"), start=1):
        observation = DriverPresentationObservation(
            observation_id=f"symptom-{index}",
            created_at=NOW + timedelta(minutes=index),
            source_key=f"complaint-{index}",
            profile_id=profile_id,
            driver_id="driver-7",
            context_key=context_key,
            context_scope=scope,
            kind="symptom_observed",
            canonical_symptom=symptom,
            symptom_phrase="pushes" if symptom == "tight_entry" else "snaps loose",
            run_id=f"run-{index}",
        )
        save_driver_presentation_observation(observation, db_path=db_path)

    profile = get_driver_presentation_profile(
        driver_id="driver-7", context=context, db_path=db_path
    )
    other = get_driver_presentation_profile(
        driver_id="driver-7", context=other_context, db_path=db_path
    )

    assert profile.profile_id == profile_id
    assert profile.preferred_mode == "learning"
    assert profile.terminology_level == "engineering"
    assert profile.recurring_symptoms[0].canonical_symptom == "tight_entry"
    assert profile.recurring_symptoms[0].observations == 2
    assert profile.affects_evidence_eligibility is False
    assert other.profile_id != profile.profile_id
    assert other.recurring_symptoms == ()
    assert other.preferred_mode == "race"


def test_prediction_calibration_rejects_a_grade_detached_from_its_contract(
    tmp_path,
) -> None:
    db_path = tmp_path / "forged-calibration.sqlite"
    planned = _planned_workflow()
    scored = _scored_workflow()
    record_workflow_plan(planned, db_path=db_path)
    record_workflow_outcome(scored, db_path=db_path)
    assert get_prediction_calibration(
        run_id="source-run", db_path=db_path,
    ).graded_predictions == 1

    connection = initialize_database(db_path)
    row = connection.execute(
        "SELECT grade_id, grade_json FROM engineering_prediction_grades"
    ).fetchone()
    original = json.loads(row["grade_json"])
    forged = dict(original)
    forged["actual_direction"] = "increase"
    forged["direction_result"] = "matched"
    forged["grade_label"] = "matched_direction"
    with connection:
        connection.execute(
            "UPDATE engineering_prediction_grades SET grade_json = ? WHERE grade_id = ?",
            (json.dumps(forged), row["grade_id"]),
        )
    connection.close()

    summary = get_prediction_calibration(run_id="source-run", db_path=db_path)
    assert summary.graded_predictions == 0
    assert summary.matched_predictions == 0
    assert summary.workflow_ids == ()

    detached = dict(original)
    detached["prediction_contract_sha256"] = "0" * 64
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE engineering_prediction_grades SET grade_json = ? WHERE grade_id = ?",
            (json.dumps(detached), row["grade_id"]),
        )
    connection.close()
    assert get_prediction_calibration(
        run_id="source-run", db_path=db_path,
    ).graded_predictions == 0


def test_driver_profile_rejects_cross_driver_writes_and_skips_corrupt_history(
    tmp_path,
) -> None:
    db_path = tmp_path / "driver-isolation.sqlite"
    context = {"car_id": "nextgen", "track_id": "atlanta"}
    profile_id, context_key, scope = presentation_profile_identity("driver-a", context)
    forged = DriverPresentationObservation(
        observation_id="forged-driver-observation",
        created_at=NOW,
        source_key="forged-driver-source",
        profile_id=profile_id,
        driver_id="driver-b",
        context_key=context_key,
        context_scope=scope,
        kind="symptom_observed",
        canonical_symptom="driver_b_private_symptom",
    )
    with pytest.raises(ValueError, match="exact driver and normalized context"):
        save_driver_presentation_observation(forged, db_path=db_path)

    legitimate = DriverPresentationObservation(
        observation_id="legitimate-driver-observation",
        created_at=NOW,
        source_key="legitimate-driver-source",
        profile_id=profile_id,
        driver_id="driver-a",
        context_key=context_key,
        context_scope=scope,
        kind="symptom_observed",
        canonical_symptom="tight_entry",
    )
    save_driver_presentation_observation(legitimate, db_path=db_path)
    connection = initialize_database(db_path)
    payload = legitimate.model_dump(mode="json")
    payload["driver_id"] = "driver-b"
    with connection:
        connection.execute(
            "UPDATE driver_presentation_observations SET observation_json = ? "
            "WHERE observation_id = ?",
            (json.dumps(payload), legitimate.observation_id),
        )
    connection.close()

    profile = get_driver_presentation_profile(
        driver_id="driver-a", context=context, db_path=db_path,
    )
    assert profile.driver_id == "driver-a"
    assert profile.recurring_symptoms == ()
    assert profile.controlled_tests_completed == 0


def test_driver_profile_withholds_noncanonical_action_like_symptoms(tmp_path) -> None:
    db_path = tmp_path / "driver-symptom.sqlite"
    context = {"car_id": "nextgen", "track_id": "atlanta"}
    profile_id, context_key, scope = presentation_profile_identity("driver-a", context)
    save_driver_presentation_observation(
        DriverPresentationObservation(
            observation_id="action-like-symptom",
            created_at=NOW,
            source_key="action-like-symptom-source",
            profile_id=profile_id,
            driver_id="driver-a",
            context_key=context_key,
            context_scope=scope,
            kind="symptom_observed",
            canonical_symptom="Set tape to 99% now.",
        ),
        db_path=db_path,
    )

    profile = get_driver_presentation_profile(
        driver_id="driver-a",
        context=context,
        db_path=db_path,
    )

    assert profile.recurring_symptoms == ()


def test_narrative_read_rejects_payloads_detached_from_stored_session_identity(
    tmp_path,
) -> None:
    db_path = tmp_path / "narrative-isolation.sqlite"
    RaceLabRepository(db_path).save_import(_overview("run-a"))
    session = create_session("Session A", db_path)
    add_run_to_session(session.session_id, "run-a", db_path)
    entry = EngineeringNarrativeEntry(
        entry_id="narrative-a",
        created_at=NOW,
        scope_id=session.session_id,
        session_id=session.session_id,
        entry_type="outcome",
        text="Qualified controlled outcome.",
        run_ids=("run-a",),
        workflow_id="workflow-a",
        evidence_references=(),
    )
    save_narrative_entry(entry, db_path=db_path)
    assert list_engineering_narrative(
        session_id=session.session_id, db_path=db_path,
    ) == (entry,)

    malformed_reference = entry.model_dump(mode="json")
    malformed_reference["evidence_references"] = [{
        "kind": "event",
        "reference_id": "Set tape to 99% now.",
    }]
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE engineering_narrative_entries SET entry_json = ? WHERE entry_id = ?",
            (json.dumps(malformed_reference), entry.entry_id),
        )
    connection.close()
    assert list_engineering_narrative(
        session_id=session.session_id, db_path=db_path,
    ) == ()

    forged = entry.model_dump(mode="json")
    forged.update({
        "session_id": "session-b",
        "scope_id": "session-b",
        "run_ids": ["run-b"],
        "workflow_id": "workflow-b",
        "text": "Set tape to 99% now.",
    })
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE engineering_narrative_entries SET entry_json = ? WHERE entry_id = ?",
            (json.dumps(forged), entry.entry_id),
        )
    connection.close()

    assert list_engineering_narrative(
        session_id=session.session_id, db_path=db_path,
    ) == ()


def test_reimport_cannot_delete_or_rewrite_engineering_memory(tmp_path) -> None:
    db_path = tmp_path / "reimport.sqlite"
    repo = RaceLabRepository(db_path)
    source = _overview("source-run")
    repo.save_import(source)
    planned = _planned_workflow()
    scored = _scored_workflow()
    repo.save_controlled_workflow(planned)
    record_workflow_plan(planned, db_path=db_path)
    record_workflow_outcome(scored, db_path=db_path)
    connection = initialize_database(db_path)
    before = {
        table: tuple(
            tuple(row)
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        )
        for table in (
            "engineering_prediction_contracts",
            "engineering_prediction_grades",
            "engineering_narrative_entries",
            "driver_presentation_observations",
        )
    }
    connection.close()

    source.session.setup_name = "Reimported without touching history"
    repo.save_import(source)
    connection = initialize_database(db_path)
    after = {
        table: tuple(
            tuple(row)
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        )
        for table in before
    }
    connection.close()

    assert after == before
    assert get_prediction_contract("aba-memory", db_path=db_path) is not None


def test_controlled_workflow_create_and_cancel_hooks_persist_memory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "hook.sqlite"
    repo = RaceLabRepository(db_path)
    repo.save_import(_overview("source-run"))
    monkeypatch.setattr(
        controlled_workflow_service,
        "build_server_kaizen_packet",
        lambda *_args, **_kwargs: _packet(),
    )

    workflow = controlled_workflow_service.create_workflow(
        "source-run", "It pushes on entry", repository=repo
    )
    assert get_prediction_contract(workflow.workflow_id, db_path=db_path) is None
    repo.save_controlled_workflow(workflow)
    record_workflow_plan(workflow, db_path=db_path)
    contract = get_prediction_contract(workflow.workflow_id, db_path=db_path)
    assert contract is not None
    assert contract.created_at == workflow.created_at

    cancelled = controlled_workflow_service.cancel_workflow(
        workflow.workflow_id, repository=repo
    )
    assert cancelled.status == "cancelled"
    narrative = list_engineering_narrative(
        workflow_id=workflow.workflow_id, db_path=db_path
    )
    assert any(
        entry.entry_type == "rollback"
        and entry.metadata.get("reason") == "explicit_abandon"
        for entry in narrative
    )
    profile = get_driver_presentation_profile_for_run("source-run", db_path=db_path)
    assert profile.recurring_symptoms[0].canonical_symptom == "tight_entry"
    assert profile.affects_evidence_eligibility is False
    record_driver_presentation_preference_for_run(
        "source-run",
        source_key="ui-mode:source-run:v1",
        preferred_mode="learning",
        terminology_level="engineering",
        db_path=db_path,
    )
    personalized = get_driver_presentation_profile_for_run("source-run", db_path=db_path)
    assert personalized.preferred_mode == "learning"
    assert personalized.terminology_level == "engineering"


def test_engineering_memory_schema_migrates_additively(tmp_path) -> None:
    connection = initialize_database(tmp_path / "schema.sqlite")
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    connection.close()
    assert {
        "engineering_prediction_contracts",
        "engineering_prediction_grades",
        "engineering_narrative_entries",
        "driver_presentation_observations",
    } <= tables
