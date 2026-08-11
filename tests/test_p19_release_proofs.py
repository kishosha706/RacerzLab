from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from api.intelligence_adapter import to_public_intelligence_report
from racelab_engine.analysis.crew_chief_packet import (
    CauseCandidate,
    OpportunityEvidence,
    build_kaizen_packet,
)
from racelab_engine.analysis.test_director import TestEvidenceLink
from racelab_engine.identity import canonical_json_sha256
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import controlled_workflow_service as workflow_service
from racelab_engine.services import import_service
from racelab_engine.services.engineering_memory_service import (
    get_prediction_contract,
    get_prediction_grade,
    list_engineering_narrative,
)
from racelab_engine.services.session_service import add_run_to_session, create_session
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository
from tests.test_internal_intelligence_service import _authorized_report, _report


def _count_true_setup_authorities(value: Any) -> int:
    if isinstance(value, dict):
        return int(value.get("setup_authorized") is True) + sum(
            _count_true_setup_authorities(child) for child in value.values()
        )
    if isinstance(value, (list, tuple)):
        return sum(_count_true_setup_authorities(child) for child in value)
    return 0


def test_pristine_p19_evidence_earns_exactly_one_setup_action() -> None:
    report = _authorized_report()
    public = to_public_intelligence_report(
        report,
        setup_snapshot=SetupSnapshot(
            setup_id="run-1:setup",
            run_id="run-1",
            setup_name="Pristine P19 fixture",
            cross_weight_percent=50.0,
        ),
    )

    assert report.status == "ready"
    assert report.data_quality.status == "ready"
    assert report.blocker_reasons == ()
    assert public.decision_status == "ready"
    assert public.briefing.action.kind == "controlled_test"
    assert public.briefing.action.setup_authorized is True
    assert public.briefing.action.control_key == "cross_weight_percent"
    assert public.briefing.action.current_value == "50.0%"
    assert public.briefing.action.proposed_value == "50.1%"
    assert public.briefing.action.source_event_ids == ["event-support"]
    assert public.best_measurement is not None
    assert public.best_measurement.procedure == [
        "Keep Cross Weight at the recorded baseline value.",
        (
            "Change only Cross Weight: 50.0% -> 50.1% "
            "(adjacent observed tech-passing option)."
        ),
        "Keep Cross Weight at the recorded baseline value.",
    ]
    assert _count_true_setup_authorities(public.model_dump(mode="json")) == 1


def test_closed_p19_gate_preserves_rich_observational_explanations() -> None:
    report = _report()
    public = to_public_intelligence_report(
        report,
        setup_snapshot=SetupSnapshot(
            setup_id="run-1:setup",
            run_id="run-1",
            setup_name="Observation-only fixture",
            cross_weight_percent=50.0,
        ),
    )

    assert report.status == "measure"
    assert public.decision_status == "measure"
    assert public.briefing.action.setup_authorized is False
    assert public.briefing.action.control_key is None
    assert public.briefing.action.proposed_value is None
    assert [cause.cause_id for cause in public.competing_causes] == [
        "platform",
        "tire",
        "driver",
    ]
    assert len(public.competing_causes[0].evidence_for) == 2
    assert len(public.competing_causes[2].evidence_against) == 1
    assert public.best_measurement is not None
    assert public.best_measurement.title == "Evidence discriminator"
    assert public.best_measurement.citations[0].event_id == "event-support"
    assert [entry.summary for entry in public.narrative] == [
        "Cause ordering is ordinal and evidence-scoped.",
        "No exact setup target is authorized by this report.",
    ]


def _controlled_packet():
    link = TestEvidenceLink(
        event_id="entry-proof",
        eligible_lap=True,
        valid_for_tuning=True,
        phase="entry",
        related_setup_keys=("cross_weight_percent",),
    )
    return build_kaizen_packet(
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
        candidates=(
            CauseCandidate(
                cause_bucket="corner_balance",
                control_key="cross_weight_percent",
                direction_sign=1,
                score=0.9,
                hypothesis="Test whether a small cross-weight increase reduces entry time.",
                success_metrics=("Entry time improves beyond the empirical noise floor.",),
                countereffects=(
                    "Median non-target phase time must not worsen beyond empirical noise.",
                ),
                supporting_event_ids=("entry-proof",),
            ),
        ),
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": (50.0, 50.5)},
        legal_value_provenance_by_control={
            "cross_weight_percent": {"50.5": ("tech-passing-setup:option-run",)},
        },
    )


def _run(
    run_id: str,
    *,
    cross_weight: float,
    started_at: datetime,
    file_hash: str,
) -> RunOverview:
    setup = SetupSnapshot(
        setup_id=f"{run_id}:setup",
        run_id=run_id,
        setup_name=f"{run_id}.sto",
        cross_weight_percent=cross_weight,
    )
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            source_file=f"{run_id}.ibt",
            file_hash=file_hash,
            sim_date_time=started_at.isoformat(),
            car_name="Synthetic Next Gen",
            car_path="stockcars/synthetic-next-gen",
            track_name="Synthetic Oval",
            track_id_or_path="synthetic-oval",
            session_type="Test",
            telemetry_rate_hz=60.0,
            setup_name=setup.setup_name,
            setup_passed_tech=True,
        ),
        laps=[
            LapSummary(
                lap_id=f"{run_id}:lap:{lap_number}",
                run_id=run_id,
                lap_number=lap_number,
                lap_type="flying",
                is_complete=True,
                is_useful=True,
                lap_time=30.0 + lap_number / 10.0,
            )
            for lap_number in range(1, 6)
        ],
        events=(
            [
                TelemetryEvent(
                    event_id="entry-proof",
                    run_id=run_id,
                    lap_number=3,
                    event_type="platform_balance",
                    event_subtype="entry_settle",
                    lap_pct_start=20.0,
                    lap_pct_end=30.0,
                    lap_pct_peak=25.0,
                    valid_for_tuning=True,
                    evidence_state="calculated",
                    source_channels=["lap_dist_pct_100", "speed_mps"],
                    related_setup_keys=["cross_weight_percent"],
                    blocker_reasons=[],
                )
            ]
            if run_id == "source"
            else []
        ),
        setup_snapshot=setup,
    )


def _synthetic_row(run_id: str, lap_number: int) -> dict[str, object]:
    stage = "B" if run_id == "run-b" else "baseline"
    return {
        "lap": lap_number,
        "lap_dist_pct_100": 25.0,
        "session_time": float(lap_number),
        "stage": stage,
        "player_tire_compound": "dry",
        "tire_sets_used": 1,
        "fuel_level": 50.0,
        "air_temp": 25.0,
        "track_temp": 30.0,
        "wind_vel": 1.0,
        "lf_tire_distance_m": 1_000.0,
        "rf_tire_distance_m": 1_000.0,
        "lr_tire_distance_m": 1_000.0,
        "rr_tire_distance_m": 1_000.0,
        "car_distance_ahead_m": 500_000.0,
        "car_distance_behind_m": 500_000.0,
        "speed_mps": 50.0,
    }


def test_full_aba2_keep_survives_restart_with_durable_memory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "p19-release-proof.sqlite"
    repository = RaceLabRepository(db_path)
    now = datetime.now(timezone.utc)
    source = _run(
        "source",
        cross_weight=50.0,
        started_at=now - timedelta(hours=1),
        file_hash="1" * 64,
    )
    run_b = _run(
        "run-b",
        cross_weight=50.5,
        started_at=now + timedelta(hours=1),
        file_hash="2" * 64,
    )
    run_a2 = _run(
        "run-a2",
        cross_weight=50.0,
        started_at=now + timedelta(hours=2),
        file_hash="3" * 64,
    )
    repository.save_import(source)
    repository.save_import(run_b)
    repository.save_import(run_a2)

    session = create_session("Synthetic A/B/A2 release proof", db_path=db_path)
    add_run_to_session(session.session_id, source.run_id, db_path=db_path)

    identity = {
        "driver_user_id": "synthetic-driver",
        "car_id": "synthetic-next-gen",
        "car_name": "Synthetic Next Gen",
        "car_path": "stockcars/synthetic-next-gen",
        "car_version": "2026.08.1",
        "track_id": "synthetic-oval",
        "track_name": "Synthetic Oval",
        "track_configuration_name": "oval",
        "track_version": "2026.08.1",
        "iracing_build_version": "2026.08.1",
        "session_type": "test",
    }
    compatibility_fingerprint = "a" * 64

    def manifest(_run_id: str) -> dict[str, object]:
        return {
            "compatibility_identity": identity,
            "compatibility_fingerprint": compatibility_fingerprint,
            "schema_fingerprint": "b" * 64,
            "cache_version": "synthetic-v1",
            "recording_session_time_bounds_s": {"start": 0.0, "end": 100.0},
        }

    packet = _controlled_packet()
    monkeypatch.setattr(
        workflow_service,
        "build_server_kaizen_packet",
        lambda *_args, **_kwargs: packet,
    )
    monkeypatch.setattr(workflow_service, "read_telemetry_manifest", manifest)
    monkeypatch.setattr(import_service, "read_telemetry_manifest", manifest)
    monkeypatch.setattr(
        workflow_service,
        "_lap_rows",
        lambda run_id, lap_numbers: {
            number: [_synthetic_row(run_id, number)] for number in lap_numbers
        },
    )
    monkeypatch.setattr(workflow_service, "_context_score", lambda *_args, **_kwargs: 1.0)
    monkeypatch.setattr(workflow_service, "_driver_similarity", lambda *_args: 1.0)
    monkeypatch.setattr(
        workflow_service,
        "setup_controls_comparable",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        workflow_service,
        "unmapped_setup_change_paths",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        workflow_service,
        "build_sim_integrity_certificate",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_clear_for_analysis=True,
            confidence_cap=1.0,
        ),
    )

    def alignment(left, right, **_kwargs):
        controlled = right[0]["stage"] == "B" and left[0]["stage"] != "B"
        target_delta = -0.08 if controlled else 0.005
        center_delta = 0.0 if controlled else 0.001
        return SimpleNamespace(
            grid_pct=[25.0, 50.0],
            phase_by_position=["entry", "center"],
            incremental_delta_s=[target_delta, center_delta],
            source_channels=["lap_dist_pct_100", "session_time"],
            time_delta_complete=True,
            coverage_fraction=1.0,
            local_alignment_confidence=0.99,
            alignment=[
                SimpleNamespace(is_gap=False, confidence=0.99),
                SimpleNamespace(is_gap=False, confidence=0.99),
            ],
            phase_effects=[],
        )

    monkeypatch.setattr(workflow_service, "analyze_time_alignment", alignment)

    candidate = workflow_service.create_workflow(
        source.run_id,
        "tight on entry",
        repository=repository,
        persist=False,
    )
    action = workflow_service.workflow_authority_action_identity(candidate)
    source_setup = source.setup_snapshot
    assert source_setup is not None
    authority_binding = {
        "schema_version": workflow_service.P19_WORKFLOW_AUTHORITY_BINDING_SCHEMA,
        "workflow_id": candidate.workflow_id,
        "run_id": source.run_id,
        "session_id": session.session_id,
        "session_run_ids": [source.run_id],
        "setup_id": source_setup.setup_id,
        "setup_snapshot_sha256": canonical_json_sha256(source_setup),
        "source_file_sha256": source.session.file_hash,
        "compatibility_fingerprint": compatibility_fingerprint,
        "compatibility_identity_sha256": canonical_json_sha256(identity),
        "plan_binding_sha256": candidate.reproduction_snapshot["plan_binding_sha256"],
        "authority_action_sha256": canonical_json_sha256(action),
        "eligible_lap_ids": [f"source:lap:{number}" for number in (3, 4, 5)],
        "source_event_ids": list(action["source_event_ids"]),
        "reasoning_snapshot_sha256": "c" * 64,
        "bound_at": now.isoformat(),
    }
    candidate = candidate.model_copy(
        update={
            "reproduction_snapshot": {
                **candidate.reproduction_snapshot,
                "p19_authority_binding": authority_binding,
            }
        }
    )
    planned = workflow_service.persist_workflow_candidate(
        candidate,
        repository=repository,
    )
    assert planned.status == "planned"

    stage_a = workflow_service.attach_stage(
        planned.workflow_id,
        "A",
        source.run_id,
        repository=repository,
    )
    assert stage_a.status == "a_recorded"
    add_run_to_session(session.session_id, run_b.run_id, db_path=db_path)
    stage_b = workflow_service.attach_stage(
        planned.workflow_id,
        "B",
        run_b.run_id,
        repository=repository,
    )
    assert stage_b.status == "b_recorded"
    add_run_to_session(session.session_id, run_a2.run_id, db_path=db_path)
    stage_a2 = workflow_service.attach_stage(
        planned.workflow_id,
        "A2",
        run_a2.run_id,
        repository=repository,
    )
    assert stage_a2.status == "a2_recorded"

    scored = workflow_service.score_workflow(
        planned.workflow_id,
        repository=repository,
    )
    assert scored.status == "scored"
    assert scored.quality is not None
    assert scored.quality.verdict == "keep"
    assert scored.quality.protocol_valid is True
    assert scored.learning_admitted is True
    assert scored.stage_run_ids == {
        "A": source.run_id,
        "B": run_b.run_id,
        "A2": run_a2.run_id,
    }

    restarted_repository = RaceLabRepository(db_path)
    reloaded = restarted_repository.get_controlled_workflow(planned.workflow_id)
    assert reloaded is not None
    assert reloaded.status == "scored"
    assert reloaded.quality is not None and reloaded.quality.verdict == "keep"
    assert reloaded.learning_admitted is True
    contract = get_prediction_contract(reloaded.workflow_id, db_path=db_path)
    grade = get_prediction_grade(reloaded.workflow_id, db_path=db_path)
    narrative = list_engineering_narrative(
        workflow_id=reloaded.workflow_id,
        db_path=db_path,
    )
    assert contract is not None
    assert grade is not None and grade.workflow_verdict == "keep"
    assert {entry.entry_type for entry in narrative} >= {
        "complaint",
        "hypothesis",
        "measurement",
        "change",
        "outcome",
        "learning",
    }
    connection = initialize_database(db_path)
    response_memory = connection.execute(
        "SELECT comparison_id, baseline_run_id, test_run_id, setup_key, verdict "
        "FROM setup_response_observations WHERE comparison_id = ?",
        (reloaded.workflow_id,),
    ).fetchall()
    connection.close()
    assert [tuple(row) for row in response_memory] == [
        (
            reloaded.workflow_id,
            source.run_id,
            run_b.run_id,
            "cross_weight_percent",
            "keep_direction",
        )
    ]
