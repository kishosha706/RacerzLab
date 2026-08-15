from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from racelab_engine.models.engineering_learning import (
    EngineeringExperienceContext,
    EngineeringExperienceRecord,
    EngineeringSourceProvenance,
    InvestigationPathFact,
    P19ReasoningMemory,
    ProblemFingerprint,
)
from racelab_engine.services import engineering_learning_service as learning_service
from racelab_engine.services.engineering_learning_service import (
    CurrentLearningInputs,
    build_crew_chief_learning_prior,
    clear_learning_cache,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.engineering_learning_repository import (
    EngineeringLearningIntegrityError,
    EngineeringLearningRepository,
)
from racelab_engine.storage.repository import RaceLabRepository
from test_engineering_memory_service import _planned_workflow, _scored_workflow


def _context(run: int = 1) -> EngineeringExperienceContext:
    return EngineeringExperienceContext.build(
        run_id=f"run-{run}",
        session_id=f"session-{run}",
        driver_id="driver-a",
        car_path="nascar-nextgen-chevy",
        car_version="2026.08",
        iracing_build="2026.08.1",
        track="atlanta",
        track_configuration="oval",
        package_type="speedway",
        setup_family=None,
        setup_snapshot_sha256=f"{run % 10}" * 64,
        objective="race_long_run",
        physical_scope_sha256="b" * 64,
        phase="center",
        physical_region="T1-T2",
        speed_load_band="high_speed_loaded",
        fuel_state="short_run",
        tire_state="short_run",
        weather_state="recorded",
        traffic_state="clear",
        driver_execution_state="matched_inputs",
    )


def _problem(
    artifact_id: str = "artifact-center",
    *,
    physical_episode_id: str = "episode-center",
) -> ProblemFingerprint:
    return ProblemFingerprint.build(
        physical_episode_id=physical_episode_id,
        performance_opportunity_id="opportunity-center",
        phase="center",
        physical_region="T1-T2",
        time_origin_class="local_loss",
        carry_behavior="following_straight_carry",
        driver_demand_state="matched_inputs",
        vehicle_response_state="changed_response",
        p20_mechanism_families=("platform", "tire_state"),
        p26_component_families=("rf_tire",),
        traffic_context_state="clear",
        tire_stint_state="short_run",
        objective="race_long_run",
        source_artifact_ids=(artifact_id,),
    )


def _reasoning() -> P19ReasoningMemory:
    return P19ReasoningMemory(
        reasoning_snapshot_sha256="c" * 64,
        causes=(),
        measurement_plan_kind="measurement_only",
        authority_level="measurement",
        setup_authorized=False,
    )


def _record(index: int) -> EngineeringExperienceRecord:
    context = _context(index)
    artifact_id = f"artifact-{index}"
    provenance = EngineeringSourceProvenance.build(
        artifact_id=artifact_id,
        producer_id="p33.controlled-workflow",
        run_id=context.run_id,
        session_id=context.session_id,
        setup_id=f"setup-{index}",
        setup_snapshot_sha256=context.setup_snapshot_sha256,
        build_context_sha256="4" * 64,
        lap_numbers=(7,),
        lap_pct_start=20.0,
        lap_pct_end=30.0,
        phase="center",
        source_channels=("speed_mps",),
        evidence_state="controlled_test_effect",
        polarity="support",
    )
    return EngineeringExperienceRecord.build(
        source_kind="controlled_workflow",
        source_workflow_id=f"workflow-{index}",
        created_at=datetime(2026, 8, 14, 12, tzinfo=timezone.utc)
        + timedelta(seconds=index),
        context=context,
        problem=_problem(
            artifact_id,
            physical_episode_id=f"episode-center-{index}",
        ),
        source_p19_reasoning_snapshot_sha256="c" * 64,
        closing_reasoning=_reasoning(),
        source_provenance=(provenance,),
        source_artifact_ids=(artifact_id,),
    )


def _current(index: int) -> CurrentLearningInputs:
    record = _record(index)
    return CurrentLearningInputs(
        context=record.context,
        problem=record.problem,
        reasoning=record.closing_reasoning,
        source_provenance=record.source_provenance,
        performance_response=None,
        driver_contributions=(),
    )


def _investigation_record(index: int) -> EngineeringExperienceRecord:
    context = _context(1)
    artifact_id = f"investigation-artifact-{index}"
    investigation_id = f"investigation-{index}"
    created_at = datetime(2026, 8, 14, 13, tzinfo=timezone.utc) + timedelta(
        seconds=index
    )
    provenance = EngineeringSourceProvenance.build(
        artifact_id=artifact_id,
        producer_id="p27.crew_chief_event",
        run_id=context.run_id,
        session_id=context.session_id,
        setup_id="setup-1",
        setup_snapshot_sha256=context.setup_snapshot_sha256,
        build_context_sha256="4" * 64,
        phase="center",
        evidence_state="needs_confirmation",
        polarity="neutral",
    )
    return EngineeringExperienceRecord.build(
        source_kind="resolved_investigation",
        source_investigation_id=investigation_id,
        created_at=created_at,
        context=context,
        problem=_problem(
            artifact_id,
            physical_episode_id=f"episode-center-{index}",
        ),
        source_p19_reasoning_snapshot_sha256="c" * 64,
        closing_reasoning=_reasoning(),
        investigation_outcome=InvestigationPathFact(
            investigation_id=investigation_id,
            started_at=created_at,
            completed_at=created_at,
            tools_inspected=("inspect_time_loss_origin",),
            strongest_contradiction="No qualified mechanism was established.",
            terminal_decision="measurement_only",
            elapsed_seconds=0.0,
            laps_consumed=0,
            tool_steps_consumed=1,
            driver_questions_consumed=0,
            requested_measurement_ids=("inspect_time_loss_origin",),
            completed_measurement_ids=("inspect_time_loss_origin",),
            successful_discriminator_ids=("inspect_time_loss_origin",),
            source_artifact_ids=(artifact_id,),
            historical_retrieval_used=False,
        ),
        source_event_ids=(artifact_id,),
        source_artifact_ids=(artifact_id,),
        source_provenance=(provenance,),
    )


def test_append_is_idempotent_restart_safe_and_transaction_aware(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    record = _record(1)

    first = repository.append_experience(record)
    second = repository.append_experience(record)
    restarted = EngineeringLearningRepository(db_path)

    assert first == second == restarted.stream_state()
    assert first.record_count == 1
    result = restarted.query_relevant(record.context, problem=record.problem)
    assert result.records == (record,)
    assert result.blockers == ()

    connection = initialize_database(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        repository.append_experience(_record(2), connection=connection)
        connection.rollback()
    finally:
        connection.close()
    assert restarted.stream_state().record_count == 1


def test_final_p19_bound_score_and_p33_experience_roll_back_together(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "workflow-learning-atomic.sqlite"
    workflow_id = "p33-atomic-score"
    repository = RaceLabRepository(db_path)
    original = _planned_workflow(workflow_id=workflow_id)
    scored = _scored_workflow(workflow_id=workflow_id)
    connection = initialize_database(db_path)
    try:
        connection.executemany(
            "INSERT INTO runs (run_id, source_file, import_time, imported_at, session_json) "
            "VALUES (?, ?, '2026-08-14', '2026-08-14', '{}')",
            (
                (run_id, f"{run_id}.ibt")
                for run_id in (
                    original.source_run_id,
                    *scored.stage_run_ids.values(),
                )
            ),
        )
        connection.commit()
    finally:
        connection.close()
    repository.save_controlled_workflow(original)
    scored = scored.model_copy(
        update={
            "reproduction_snapshot": {
                **scored.reproduction_snapshot,
                "p19_outcome_binding": {
                    "workflow_id": workflow_id,
                    "reasoning_snapshot_sha256": "c" * 64,
                },
            }
        }
    )
    source = _record(1)
    experience = EngineeringExperienceRecord.build(
        source_kind="controlled_workflow",
        source_workflow_id=workflow_id,
        created_at=scored.updated_at,
        context=source.context,
        problem=source.problem,
        source_p19_reasoning_snapshot_sha256="c" * 64,
        closing_reasoning=source.closing_reasoning,
        source_artifact_ids=source.source_artifact_ids,
        source_provenance=source.source_provenance,
    )

    def fail_after_workflow_write(connection, record):
        raise RuntimeError("injected P33 append failure")

    monkeypatch.setattr(
        EngineeringLearningRepository,
        "append_experience_in_transaction",
        fail_after_workflow_write,
    )
    with pytest.raises(RuntimeError, match="injected P33 append failure"):
        repository.save_scored_workflow_with_experience_if_scope_exclusive(
            scored,
            (scored.source_run_id, *scored.stage_run_ids.values()),
            experience,
        )

    assert repository.get_controlled_workflow(workflow_id) == original
    connection = initialize_database(db_path)
    try:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM engineering_experiences"
            ).fetchone()[0]
            == 0
        )
        stream = connection.execute(
            "SELECT record_count, head_sha256 FROM engineering_experience_stream_head"
        ).fetchone()
        assert tuple(stream) == (0, None)
    finally:
        connection.close()


def test_prior_is_restart_deterministic_and_invalidates_on_append(tmp_path) -> None:
    db_path = tmp_path / "learning-prior-restart.sqlite"
    repository = EngineeringLearningRepository(db_path)
    repository.append_experience(_record(1))
    repository.append_experience(_record(2))
    current = _current(12)
    arguments = {
        "scope_run_ids": (current.context.run_id,),
        "p19_reasoning_snapshot_sha256": (current.reasoning.reasoning_snapshot_sha256),
        "p32_projection_sha256": "f" * 64,
        "max_candidates": 64,
    }

    clear_learning_cache()
    before_restart = build_crew_chief_learning_prior(
        current, repository=repository, **arguments
    )
    clear_learning_cache()
    restarted = build_crew_chief_learning_prior(
        current,
        repository=EngineeringLearningRepository(db_path),
        **arguments,
    )
    assert restarted == before_restart
    assert restarted.projection_sha256 == before_restart.projection_sha256

    repository.append_experience(_record(3))
    after_append = build_crew_chief_learning_prior(
        current, repository=repository, **arguments
    )
    assert after_append.history_revision != before_restart.history_revision
    assert after_append.projection_sha256 != before_restart.projection_sha256


def test_prior_turns_stream_head_corruption_into_typed_blocked_memory(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-prior-corrupt.sqlite"
    repository = EngineeringLearningRepository(db_path)
    repository.append_experience(_record(1))
    current = _current(11)
    connection = initialize_database(db_path)
    try:
        connection.execute(
            "UPDATE engineering_experience_stream_head SET head_sha256 = ?",
            ("f" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    clear_learning_cache()
    prior = build_crew_chief_learning_prior(
        current,
        scope_run_ids=(current.context.run_id,),
        p19_reasoning_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        p32_projection_sha256="f" * 64,
        repository=repository,
    )
    assert prior.state == "blocked"
    assert prior.context_transfer_level == "blocked"
    assert prior.recommended_attention_order == ()
    assert prior.setup_authorized is False
    assert "stream tail is corrupt" in prior.blocker_reasons[0]


def test_attention_session_count_uses_exact_sessions_not_experience_count(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning-attention-sessions.sqlite"
    repository = EngineeringLearningRepository(db_path)
    repository.append_experience(_investigation_record(1))
    repository.append_experience(_investigation_record(2))
    current = _current(11)

    clear_learning_cache()
    prior = build_crew_chief_learning_prior(
        current,
        scope_run_ids=(current.context.run_id,),
        p19_reasoning_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        p32_projection_sha256="f" * 64,
        repository=repository,
    )

    assert len(prior.recommended_attention_order) == 1
    attention = prior.recommended_attention_order[0]
    assert attention.investigation_count == 2
    assert len(attention.source_experience_ids) == 2
    assert attention.session_count == 1


def test_same_source_identity_cannot_be_replayed_with_different_content(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    original = _record(1)
    repository.append_experience(original)
    conflict = EngineeringExperienceRecord.build(
        source_kind=original.source_kind,
        source_workflow_id=original.source_workflow_id,
        created_at=original.created_at + timedelta(seconds=1),
        context=original.context,
        problem=original.problem,
        source_p19_reasoning_snapshot_sha256=(
            original.source_p19_reasoning_snapshot_sha256
        ),
        closing_reasoning=original.closing_reasoning,
        source_provenance=original.source_provenance,
        source_artifact_ids=original.source_artifact_ids,
    )

    with pytest.raises(
        EngineeringLearningIntegrityError,
        match="source identity already owns different experience data",
    ):
        repository.append_experience(conflict)
    assert repository.stream_state().record_count == 1


def test_idempotent_replay_refuses_a_corrupt_existing_row(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    record = _record(1)
    repository.append_experience(record)
    connection = initialize_database(db_path)
    try:
        connection.execute("DROP TRIGGER engineering_experiences_no_update")
        connection.execute(
            "UPDATE engineering_experiences SET physical_region = 'forged-region' "
            "WHERE experience_id = ?",
            (record.experience_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(EngineeringLearningIntegrityError, match="entry identity"):
        repository.append_experience(record)


def test_append_only_triggers_block_deletion_and_relabeling(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    record = _record(1)
    repository.append_experience(record)
    connection = initialize_database(db_path)
    try:
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "DELETE FROM engineering_experiences WHERE experience_id = ?",
                (record.experience_id,),
            )
        with pytest.raises(Exception, match="append-only"):
            connection.execute(
                "UPDATE engineering_experiences SET iracing_build = 'future' "
                "WHERE experience_id = ?",
                (record.experience_id,),
            )
    finally:
        connection.close()


def test_corrupt_relevant_payload_is_contained_without_hiding_valid_history(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    valid = _record(1)
    corrupt = _record(2)
    repository.append_experience(valid)
    repository.append_experience(corrupt)

    connection = initialize_database(db_path)
    try:
        connection.execute("DROP TRIGGER engineering_experiences_no_update")
        connection.execute(
            "UPDATE engineering_experiences SET record_json = '{}' "
            "WHERE experience_id = ?",
            (corrupt.experience_id,),
        )
        connection.commit()
    finally:
        connection.close()

    result = repository.query_relevant(valid.context, problem=valid.problem)
    assert result.records == (valid,)
    assert len(result.blockers) == 1
    assert corrupt.experience_id in result.blockers[0]
    clear_learning_cache()
    current = _current(1)
    prior = build_crew_chief_learning_prior(
        current,
        scope_run_ids=(current.context.run_id,),
        p19_reasoning_snapshot_sha256=(
            current.reasoning.reasoning_snapshot_sha256
        ),
        p32_projection_sha256="f" * 64,
        repository=repository,
    )
    assert prior.state == "blocked"
    assert prior.context_transfer_level == "blocked"
    assert prior.blocker_reasons == result.blockers
    assert prior.recommended_attention_order == ()
    with pytest.raises(EngineeringLearningIntegrityError, match="payload is corrupt"):
        repository.stream_state(validate_chain=True)


def test_explicit_chain_audit_detects_tail_and_sequence_corruption(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    repository.append_experience(_record(1))
    repository.append_experience(_record(2))
    connection = initialize_database(db_path)
    try:
        connection.execute("DROP TRIGGER engineering_experiences_no_update")
        connection.execute(
            "UPDATE engineering_experiences SET previous_entry_sha256 = ? "
            "WHERE sequence = 1",
            ("f" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    # Normal bounded retrieval contains a corrupt candidate instead of hiding
    # the other qualified record or poisoning current P19/P32 evidence.
    result = repository.query_relevant(_context(1), problem=_problem())
    assert len(result.records) == 1
    assert len(result.blockers) == 1
    assert "entry identity" in result.blockers[0]
    with pytest.raises(EngineeringLearningIntegrityError, match="chain link"):
        repository.stream_state(validate_chain=True)


def test_middle_row_deletion_cannot_hide_behind_an_unchanged_stream_head(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    for index in (1, 2, 3):
        repository.append_experience(_record(index))

    connection = initialize_database(db_path)
    try:
        connection.execute("DROP TRIGGER engineering_experiences_no_delete")
        connection.execute("DELETE FROM engineering_experiences WHERE sequence = 2")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(EngineeringLearningIntegrityError, match="deleted or reordered"):
        repository.query_relevant(_context(1), problem=_problem())


def test_head_metadata_corruption_fails_before_history_is_returned(tmp_path) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    record = _record(1)
    repository.append_experience(record)
    connection = initialize_database(db_path)
    try:
        connection.execute(
            "UPDATE engineering_experience_stream_head SET record_count = 2"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(EngineeringLearningIntegrityError, match="deleted or reordered"):
        repository.query_relevant(record.context, problem=record.problem)


def test_relevant_query_is_fixed_branch_bounded_and_never_reads_telemetry(
    tmp_path,
) -> None:
    db_path = tmp_path / "learning.sqlite"
    repository = EngineeringLearningRepository(db_path)
    connection = initialize_database(db_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        for index in range(1, 301):
            repository.append_experience(_record(index), connection=connection)
        connection.commit()

        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        result = repository.query_relevant(
            _context(1), problem=_problem(), limit=37, connection=connection
        )
    finally:
        connection.close()

    payload_queries = [
        statement.upper()
        for statement in statements
        if "SELECT * FROM ENGINEERING_EXPERIENCES WHERE" in statement.upper()
    ]
    assert len(result.records) == 37
    assert result.blockers == ()
    assert len(payload_queries) == 4
    assert all("LIMIT 37" in statement for statement in payload_queries)
    assert not any("TELEMETRY" in statement.upper() for statement in statements)
    assert not any(
        "SELECT * FROM ENGINEERING_EXPERIENCES ORDER BY SEQUENCE" in statement.upper()
        for statement in statements
    )


@pytest.mark.parametrize("limit", (0, 513))
def test_relevant_query_rejects_unbounded_limits(tmp_path, limit: int) -> None:
    repository = EngineeringLearningRepository(tmp_path / "learning.sqlite")
    with pytest.raises(ValueError, match="between 1 and 512"):
        repository.query_relevant(_context(), limit=limit)


@pytest.mark.integration
def test_10001_record_warm_query_stays_bounded_and_reads_no_telemetry(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "learning-large.sqlite"
    repository = EngineeringLearningRepository(db_path)
    connection = initialize_database(db_path)
    try:
        seed_started = time.perf_counter()
        connection.execute("BEGIN IMMEDIATE")
        for index in range(1, 10_002):
            repository.append_experience(_record(index), connection=connection)
        connection.commit()
        seed_elapsed = time.perf_counter() - seed_started

        # First touch warms SQLite's page cache.  The measured read must retain
        # the same fixed four candidate branches at 10k+ history.
        first = repository.query_relevant(
            _context(1), problem=_problem(), limit=64, connection=connection
        )
        statements: list[str] = []
        connection.set_trace_callback(statements.append)
        warm_started = time.perf_counter()
        warm = repository.query_relevant(
            _context(1), problem=_problem(), limit=64, connection=connection
        )
        warm_elapsed = time.perf_counter() - warm_started
    finally:
        connection.close()

    payload_queries = [
        statement.upper()
        for statement in statements
        if "SELECT * FROM ENGINEERING_EXPERIENCES WHERE" in statement.upper()
    ]
    print(
        "P33_10001_SEED_SECONDS="
        f"{seed_elapsed:.6f} P33_10001_WARM_QUERY_SECONDS={warm_elapsed:.6f}"
    )
    assert first.stream_state.record_count == warm.stream_state.record_count == 10_001
    assert len(first.records) == len(warm.records) == 64
    assert first.blockers == warm.blockers == ()
    assert len(payload_queries) == 4
    assert all("LIMIT 64" in statement for statement in payload_queries)
    assert not any("TELEMETRY" in statement.upper() for statement in statements)
    assert warm_elapsed < 0.1

    current = _current(10_002)

    def fail_if_projection_reads_telemetry(*args, **kwargs):
        raise AssertionError("warm P33 history projection read telemetry")

    monkeypatch.setattr(
        learning_service, "read_telemetry_manifest", fail_if_projection_reads_telemetry
    )
    clear_learning_cache()
    prior_started = time.perf_counter()
    prior = build_crew_chief_learning_prior(
        current,
        scope_run_ids=(current.context.run_id,),
        p19_reasoning_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        p32_projection_sha256="f" * 64,
        repository=repository,
        max_candidates=64,
    )
    prior_elapsed = time.perf_counter() - prior_started
    cached_started = time.perf_counter()
    cached = build_crew_chief_learning_prior(
        current,
        scope_run_ids=(current.context.run_id,),
        p19_reasoning_snapshot_sha256=current.reasoning.reasoning_snapshot_sha256,
        p32_projection_sha256="f" * 64,
        repository=repository,
        max_candidates=64,
    )
    cached_elapsed = time.perf_counter() - cached_started
    print(
        "P33_10001_PRIOR_SECONDS="
        f"{prior_elapsed:.6f} P33_10001_CACHED_PRIOR_SECONDS={cached_elapsed:.6f}"
    )
    assert cached is prior
    assert prior.history_revision == warm.stream_state.history_revision
    assert prior.counts.observation_count == 64
    assert prior.authority == "attention_only"
    assert prior.setup_authorized is False
    assert prior.p19_rank_modified is False
    assert prior_elapsed < 0.1
    assert cached_elapsed < 0.1
