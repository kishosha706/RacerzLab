from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.intelligence_adapter import (
    _cause,
    _context_match,
    _driver_profile,
    _reference_citation,
    to_public_intelligence_navigation,
    to_public_intelligence_report,
    to_public_mind_change_criterion,
)
from api.intelligence_schemas import (
    IntelligenceCitationResponse,
    IntelligenceMindChangeCriterionResponse,
    IntelligenceQueryRequest,
    IntelligenceQueryResponse,
    RunIntelligenceResponse,
)
from api.main import app
from api.routes_intelligence import (
    _citation_track_locations,
    _query_action_matches_current_report,
    _region_aware_query_answer,
)
from racelab_engine.analysis.crew_chief_packet import (
    KaizenEvidencePacket,
    OpportunityEvidence,
)
from racelab_engine.analysis.test_director import (
    ControlledTestCard,
    MeasurementMission,
    TestEvidenceLink,
    build_controlled_test,
)
from racelab_engine.analysis.test_director import (
    TestStage as ControlledTestStage,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.engineering_memory import (
    DriverPresentationProfile,
    EngineeringEvidenceReference,
    EngineeringNarrativeEntry,
    RecurringSymptom,
)
from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.evidence import EvidenceState
from racelab_engine.models.intelligence import (
    ControlledCauseOutcome,
    EvidenceCitation,
    GroundedQueryResult,
    MindChangeCriterion,
    NavigationTarget,
    PublicCompetingCause,
    ResponseMemorySummary,
)
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services.controlled_workflow_service import (
    _workflow_decision_context,
    _workflow_plan_binding_hash,
    revalidate_controlled_test_packet,
    validate_controlled_test_target,
)
from racelab_engine.services.intelligence_service import (
    answer_grounded_query,
    build_evidence_graph,
    plan_best_next_measurement,
    rank_competing_causes,
)
from racelab_engine.services.run_intelligence_service import (
    _card_semantic_blockers,
    _claims,
    _controlled_decision,
    _hypotheses,
    _repository_setup_authority_verifier,
    _require_one_active_workflow_in_explicit_session,
    _selected_workflow,
    _setup_values,
    build_run_intelligence,
)
from racelab_engine.services.session_service import (
    add_run_to_session,
    create_session,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository

client = TestClient(app)


def test_grounded_query_citations_resolve_canonical_track_regions(monkeypatch) -> None:
    citation = EvidenceCitation(
        citation_id="event-location",
        run_id="smart-run",
        lap_number=4,
        lap_pct_peak=17.5,
        event_id="event-location",
        workspace="platform",
        phase="center",
        channels=("speed_mph",),
        evidence_state=EvidenceState.MEASURED,
        valid_for_tuning=True,
        summary="Qualified loss event.",
    )
    regions = [
        {
            "region_id": "turn_1",
            "kind": "turn",
            "number": 1,
            "label": "Turn 1",
            "short_label": "T1",
            "start_lap_pct": 10.0,
            "end_lap_pct": 25.0,
            "anchor_lap_pct": 17.5,
            "placement_source": "split two-end oval sections",
            "confidence": "section_geometry",
        }
    ]
    monkeypatch.setattr(
        "api.routes_intelligence.RaceLabRepository",
        lambda: SimpleNamespace(
            get_overview=lambda run_id: SimpleNamespace(
                session=SimpleNamespace(track_name="Test Oval", track_display_name="Test Oval")
            )
        ),
    )
    monkeypatch.setattr(
        "api.routes_intelligence.find_best_map_for_run",
        lambda run_id, track_name: {"map_id": "test-oval"},
    )
    monkeypatch.setattr("api.routes_intelligence.get_track_map", lambda map_id: object())
    monkeypatch.setattr(
        "api.routes_intelligence.build_track_regions",
        lambda track_map, match: regions,
    )

    locations = _citation_track_locations((citation,))

    assert locations["event-location"]["display_label"] == "Turn 1 center"
    public_citation = IntelligenceCitationResponse(
        citation_id=citation.citation_id,
        label=citation.summary,
        run_id=citation.run_id,
        lap_number=citation.lap_number,
        lap_pct=citation.lap_pct_peak,
        event_id=citation.event_id,
        workspace="platform_trace",
        source_channels=list(citation.channels),
        evidence_state=citation.evidence_state,
        valid_for_tuning=True,
        track_region_id="turn_1",
        track_region_label="Turn 1 center",
        track_region_phase="center",
        track_region_confidence="section_geometry",
    )
    query = GroundedQueryResult(
        supported=True,
        intent="where_is_loss",
        answer="The earliest qualified track location is near 17.5% of lap 4; open the cited event for the recorded trace.",
        citations=(citation,),
        suggested_navigation=(),
    )
    assert "Turn 1 center" in _region_aware_query_answer(query, [public_citation])


def _seed_untrusted_run(db_path: Path, run_id: str = "smart-run") -> None:
    laps = [
        LapSummary(
            lap_id=f"{run_id}:lap:{number}",
            run_id=run_id,
            lap_number=number,
            lap_type="flying",
            is_complete=True,
            is_useful=True,
            lap_time=90.0 + number / 10.0,
            pct_min=0.0,
            pct_max=100.0,
            pct_span=100.0,
            sample_count=1_000,
            avg_speed_mph=110.0,
            min_speed_mph=75.0,
            classification_tags=["SOLO_CLEAN"],
        )
        for number in range(1, 4)
    ]
    event = TelemetryEvent(
        event_id=f"{run_id}:legacy-event",
        run_id=run_id,
        lap_number=2,
        event_type="PLATFORM_LOW",
        valid_for_tuning=True,
        related_setup_keys=["front_ride_height"],
        recommended_actions=["Raise front ride height."],
        evidence_state=EvidenceState.UNAVAILABLE,
        source_channels=[],
        blocker_reasons=["Legacy evidence provenance is unavailable."],
    )
    recommendation = Recommendation(
        recommendation_id=f"{run_id}:legacy-rec",
        run_id=run_id,
        issue="Platform",
        cause_bucket="platform",
        recommendation_text="Raise front ride height.",
        evidence_event_ids=[event.event_id],
        evidence_state=EvidenceState.UNAVAILABLE,
        source_channels=[],
        blocker_reasons=["Legacy recommendation provenance is unavailable."],
    )
    RaceLabRepository(db_path).save_import(RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            car_name="Cup",
            car_path="stockcars cup",
            track_name="Test Oval",
            track_id_or_path="test-oval",
            session_type="Practice",
        ),
        laps=laps,
        events=[event],
        recommendations=[recommendation],
    ))


def _controlled_card() -> ControlledTestCard:
    stages = tuple(
        ControlledTestStage(
            stage=stage,
            setup_instruction="Keep baseline" if stage != "B" else "Apply one change",
            warmup_laps=1,
            required_flying_laps=3,
            purpose="Measure the target phase.",
        )
        for stage in ("A", "B", "A2")
    )
    return ControlledTestCard(
        hypothesis="More cross weight improves center stability.",
        control_key="cross_weight_percent",
        control_label="Cross Weight",
        direction_sign=1,
        current_value=50.0,
        proposed_value="50.1%",
        proposed_value_raw=50.1,
        proposed_value_provenance=("tech-passing-setup:source",),
        exact_change="50.0% -> 50.1% (adjacent observed tech-passing option)",
        change_size="Small",
        target_phase="center",
        expected_mechanism="rotation balance",
        success_metrics=("Target phase improves beyond noise.",),
        countereffects=("Center time must not worsen beyond normal variation.",),
        rollback_rule="Restore 50.0%.",
        keep_rule="Keep only after A/B/A2 confirmation.",
        stages=stages,
        evidence_event_ids=("event-platform",),
        do_not_change=("Everything else",),
    )


def test_run_intelligence_fails_closed_on_untrusted_legacy_actions(tmp_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path)

    bundle = build_run_intelligence("smart-run", db_path=db_path)
    public = to_public_intelligence_report(
        bundle.report,
        narrative_entries=bundle.narrative_entries,
        calibration=bundle.calibration,
        driver_profile=bundle.driver_profile,
    )

    assert public.briefing.action.setup_authorized is False
    assert public.briefing.action.control_key is None
    assert public.briefing.action.current_value is None
    assert public.briefing.action.proposed_value is None
    assert public.briefing.issue == "Evidence review requires another measurement."
    assert public.data_quality is not None
    assert public.data_quality.trusted_events == 0
    assert public.data_quality.status in {"limited", "blocked"}
    assert public.calibration.status == "insufficient_history"
    assert public.driver_profile is not None
    assert public.driver_profile.affects_evidence_eligibility is False


def test_run_intelligence_withholds_malformed_derived_rows_without_crashing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path)
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE laps SET lap_json = '{bad' WHERE run_id = ? AND lap_number = 1",
            ("smart-run",),
        )
        connection.execute(
            "UPDATE events SET event_json = '{bad' WHERE run_id = ?",
            ("smart-run",),
        )
        connection.execute(
            "UPDATE recommendations SET recommendation_json = '{bad' WHERE run_id = ?",
            ("smart-run",),
        )
        connection.execute(
            """
            INSERT INTO setup_snapshots (
                setup_id, run_id, setup_name, setup_json, snapshot_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("bad-setup", "smart-run", "Bad", "{}", "{bad"),
        )
    connection.close()

    overview = RaceLabRepository(db_path).get_overview("smart-run")
    assert overview is not None
    integrity_warnings = " ".join(overview.warnings).casefold()
    assert "lap summary" in integrity_warnings
    assert "telemetry event" in integrity_warnings
    assert "recommendation" in integrity_warnings
    assert "setup snapshot" in integrity_warnings

    bundle = build_run_intelligence("smart-run", db_path=db_path)

    assert bundle.report.briefing.action.setup_authorized is False
    assert bundle.report.data_quality.status == "blocked"
    assert bundle.report.data_quality.issues == (
        "One or more canonical evidence qualification checks failed.",
    )


def test_run_intelligence_scopes_fail_closed_workflow_reads(tmp_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path, "smart-run")
    _seed_untrusted_run(db_path, "unrelated-run")
    connection = initialize_database(db_path)
    with connection:
        for workflow_id, source_run_id in (
            ("related-bad", "smart-run"),
            ("unrelated-bad", "unrelated-run"),
        ):
            connection.execute(
                """
                INSERT INTO controlled_test_workflows (
                    workflow_id, created_at, updated_at, status, source_run_id,
                    complaint, packet_json, stage_run_ids_json,
                    stage_eligible_lap_numbers_json, analysis_version,
                    reproduction_snapshot_json
                ) VALUES (?, ?, ?, 'planned', ?, ?, '{bad', '{}', '{}', ?, '{}')
                """,
                (
                    workflow_id,
                    "2026-08-08T00:00:00+00:00",
                    "2026-08-08T00:00:00+00:00",
                    source_run_id,
                    "test",
                    "controlled-workflow-aba2-v2",
                ),
            )
    connection.close()

    repository = RaceLabRepository(db_path)
    current_rows, current_blockers = repository.list_controlled_workflows_for_run_scope(
        ("smart-run",)
    )
    unrelated_rows, unrelated_blockers = (
        repository.list_controlled_workflows_for_run_scope(("unrelated-run",))
    )

    assert current_rows == []
    assert unrelated_rows == []
    assert current_blockers == (
        "A controlled-workflow record in this scope failed integrity validation.",
    )
    assert unrelated_blockers == current_blockers
    assert build_run_intelligence("smart-run", db_path=db_path).report.status == "blocked"
    assert build_run_intelligence("unrelated-run", db_path=db_path).report.status == "blocked"


def test_run_intelligence_binds_derived_payloads_to_stored_run_identity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path, "run-A")
    _seed_untrusted_run(db_path, "run-B")
    repository = RaceLabRepository(db_path)
    original = repository.get_overview("run-A")
    assert original is not None
    foreign_lap = original.laps[0].model_copy(update={
        "lap_id": "run-B:foreign-lap",
        "run_id": "run-B",
    })
    foreign_event = original.events[0].model_copy(update={"run_id": "run-B"})
    foreign_recommendation = original.recommendations[0].model_copy(
        update={"run_id": "run-B"}
    )
    foreign_setup = SetupSnapshot(
        setup_id="run-B:setup",
        run_id="run-B",
        setup_name="Foreign",
    )
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE laps SET lap_json = ? WHERE run_id = ? AND lap_number = 1",
            (foreign_lap.model_dump_json(), "run-A"),
        )
        connection.execute(
            "UPDATE events SET event_json = ? WHERE run_id = ?",
            (foreign_event.model_dump_json(), "run-A"),
        )
        connection.execute(
            "UPDATE recommendations SET recommendation_json = ? WHERE run_id = ?",
            (foreign_recommendation.model_dump_json(), "run-A"),
        )
        connection.execute(
            """
            INSERT INTO setup_snapshots (
                setup_id, run_id, setup_name, setup_json, snapshot_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "run-A:setup",
                "run-A",
                "Foreign",
                "{}",
                foreign_setup.model_dump_json(),
            ),
        )
    connection.close()

    overview = repository.get_overview("run-A")
    assert overview is not None
    assert all(lap.run_id == "run-A" for lap in overview.laps)
    assert overview.events == []
    assert overview.recommendations == []
    assert overview.setup_snapshot is None
    assert repository.get_setup_snapshot("run-A") is None
    assert len([
        warning for warning in overview.warnings
        if "identity-mismatched" in warning
    ]) == 4
    bundle = build_run_intelligence("run-A", db_path=db_path)
    assert bundle.report.data_quality.status == "blocked"
    assert bundle.report.briefing.action.setup_authorized is False

    connection = initialize_database(db_path)
    foreign_session = original.session.model_copy(update={
        "run_id": "run-B",
        "car_path": "foreign-car",
        "setup_passed_tech": True,
    })
    with connection:
        connection.execute(
            """
            UPDATE runs
            SET session_json = ?, car_path = ?, setup_passed_tech = 0
            WHERE run_id = ?
            """,
            (foreign_session.model_dump_json(), "sql-canonical-car", "run-A"),
        )
    connection.close()

    canonical = repository.get_overview("run-A")
    assert canonical is not None
    assert canonical.session.run_id == "run-A"
    assert canonical.session.car_path == "sql-canonical-car"
    assert canonical.session.setup_passed_tech is False


def test_tech_passing_setup_candidates_withhold_identity_mismatches(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path, "run-A")
    foreign_setup = SetupSnapshot(
        setup_id="run-B:setup",
        run_id="run-B",
        setup_name="Foreign",
    )
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE runs SET setup_passed_tech = 1 WHERE run_id = ?",
            ("run-A",),
        )
        connection.execute(
            """
            INSERT INTO setup_snapshots (
                setup_id, run_id, setup_name, setup_json, snapshot_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "run-A:setup",
                "run-A",
                "Foreign",
                "{}",
                foreign_setup.model_dump_json(),
            ),
        )
    connection.close()

    candidates = RaceLabRepository(db_path).list_tech_passing_setup_candidates(
        car_path=None,
        track_id_or_path=None,
        session_type=None,
    )

    assert candidates == []


def test_grounded_query_refuses_unsupported_or_unqualified_setup_authority(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path)
    report = build_run_intelligence("smart-run", db_path=db_path).report

    unsupported = answer_grounded_query("Invent the fastest setup", report)
    next_step = answer_grounded_query("What should I do next?", report)

    assert unsupported.supported is False
    assert unsupported.citations == ()
    assert next_step.supported is True
    assert report.briefing.action.setup_authorized is False
    assert next_step.citations == ()


def test_query_action_must_match_the_current_authorized_report_exactly() -> None:
    from racelab_engine.services.smart_guidance_service import build_smart_guidance
    from tests.test_internal_intelligence_service import _authorized_report, _workflow

    report = _authorized_report()
    action = report.briefing.action
    exact = SimpleNamespace(
        action_authorized=True,
        answer=action.instruction,
        action_source_event_ids=action.source_event_ids,
    )
    invented_instruction = SimpleNamespace(
        action_authorized=True,
        answer="Set an unrelated control to an invented value.",
        action_source_event_ids=action.source_event_ids,
    )
    borrowed_event = SimpleNamespace(
        action_authorized=True,
        answer=action.instruction,
        action_source_event_ids=("unrelated-event",),
    )

    assert _query_action_matches_current_report(exact, report) is True
    assert _query_action_matches_current_report(invented_instruction, report) is False
    assert _query_action_matches_current_report(borrowed_event, report) is False

    blocked_reports = (
        report.model_copy(update={"blocker_reasons": ("Late report blocker.",)}),
        report.model_copy(
            update={
                "briefing": report.briefing.model_copy(
                    update={"blocker_reasons": ("Late briefing blocker.",)}
                )
            }
        ),
        report.model_copy(
            update={
                "briefing": report.briefing.model_copy(
                    update={
                        "action": report.briefing.action.model_copy(
                            update={"blocker_reasons": ("Late action blocker.",)}
                        )
                    }
                )
            }
        ),
        report.model_copy(
            update={
                "data_quality": report.data_quality.model_copy(
                    update={"issues": ("Late data-quality issue.",)}
                )
            }
        ),
    )
    assert all(
        _query_action_matches_current_report(exact, blocked) is False
        for blocked in blocked_reports
    )

    workflow = _workflow().model_copy(
        update={
            "status": "a_recorded",
            "stage_run_ids": {"A": "run-1"},
            "stage_eligible_lap_numbers": {"A": (4, 5, 6)},
            "execution": None,
            "quality": None,
            "learning_admitted": False,
        }
    )
    guidance = build_smart_guidance(report, workflow=workflow)
    active_report = report.model_copy(update={"smart_guidance": guidance})
    assert _query_action_matches_current_report(exact, active_report) is True
    divergent_move = guidance.next_trustworthy_move.model_copy(
        update={"instruction": "Apply a second unrelated setup command."}
    )
    divergent_report = active_report.model_copy(
        update={
            "smart_guidance": guidance.model_copy(
                update={"next_trustworthy_move": divergent_move}
            )
        }
    )
    assert _query_action_matches_current_report(exact, divergent_report) is False


def test_public_cause_board_cites_controlled_support_and_contradiction() -> None:
    def outcome(kind: str, verdict: str, workflow_id: str) -> ControlledCauseOutcome:
        return ControlledCauseOutcome(
            workflow_id=workflow_id,
            outcome=kind,
            verdict=verdict,
            source_run_id="run-1",
            stage_run_ids=("run-a", "run-b", "run-a2"),
            eligible_lap_ids=tuple(f"lap-{index}" for index in range(1, 10)),
            metric="corner_exit_speed",
            phase="exit",
            control_key="track_bar_right",
                countereffects=("No entry penalty beyond the frozen threshold.",),
                diagnostic_validity="mechanism_diagnostic",
                control_direction_result=(
                    "matched" if kind == "supported" else "missed"
                ),
            )

    supported = _cause(
        PublicCompetingCause(
            cause_id="rear-support",
            label="Rear support",
            state="leading",
            rank=1,
            evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
            reason="One exact controlled result supported this explanation.",
            evidence_for=(),
            evidence_against=(),
            controlled_outcomes=(outcome("supported", "keep", "workflow-keep"),),
        )
    )
    contradicted = _cause(
        PublicCompetingCause(
            cause_id="rear-support",
            label="Rear support",
            state="ruled_out",
            rank=1,
            evidence_state=EvidenceState.CONTROLLED_TEST_EFFECT,
            reason="One exact controlled result contradicted this explanation.",
            evidence_for=(),
            evidence_against=(),
            controlled_outcomes=(outcome("contradicted", "undo", "workflow-undo"),),
        )
    )

    assert supported.evidence_state == EvidenceState.CONTROLLED_TEST_EFFECT
    assert supported.evidence_for[0].workspace == "dial_in"
    assert supported.evidence_for[0].valid_for_tuning is False
    assert "supported" in supported.evidence_for[0].label
    assert contradicted.evidence_state == EvidenceState.CONTROLLED_TEST_EFFECT
    assert contradicted.evidence_against[0].workspace == "dial_in"
    assert contradicted.evidence_against[0].valid_for_tuning is False
    assert "contradicted" in contradicted.evidence_against[0].label


def test_public_report_rejects_unlinked_or_mismatched_setup_authority() -> None:
    from tests.test_internal_intelligence_service import _authorized_report

    public = to_public_intelligence_report(_authorized_report())
    no_citations = public.model_dump(mode="json")
    for cause in no_citations["competing_causes"]:
        cause["evidence_for"] = []
        cause["evidence_against"] = []
    no_citations["best_measurement"]["citations"] = []
    no_citations["context_matches"] = []
    no_citations["narrative"] = []
    no_citations["data_quality"]["citations"] = []
    no_citations["evidence_graph"] = None
    with pytest.raises(ValueError, match="exact current-run tuning citation set"):
        RunIntelligenceResponse.model_validate(no_citations)

    unauthorized_measurement = public.model_dump(mode="json")
    unauthorized_measurement["decision_status"] = "measure"
    unauthorized_measurement["briefing"]["action"] = {
        "kind": "no_call",
        "title": "No setup call",
        "instruction": "Keep the current setup.",
        "setup_authorized": False,
        "control_key": None,
        "current_value": None,
        "proposed_value": None,
        "evidence_state": "unavailable",
        "source_event_ids": [],
        "blocker_reasons": ["The exact controlled target was withheld."],
    }
    with pytest.raises(ValueError, match="controlled-test measurement detail"):
        RunIntelligenceResponse.model_validate(unauthorized_measurement)

    forged_move = public.model_dump(mode="json")
    forged_move["test_preflight"] = {
        "workflow_id": "workflow-forged",
        "stage": "B",
        "status": "ready",
        "title": "Run Stage B",
        "checks": [],
        "blocker_reasons": [],
    }
    forged_move["next_trustworthy_move"] = {
        "move_id": "forged-move",
        "kind": "controlled_test",
        "title": "Invented setup call",
        "instruction": "Set Cross Weight to 99%.",
        "reason": "Forged response",
        "workspace": "dial_in",
        "authority": "setup_authorized",
        "run_id": public.run_id,
        "workflow_id": "workflow-forged",
        "workflow_updated_at": "2026-08-09T12:00:00Z",
        "control_key": public.briefing.action.control_key,
        "source_event_ids": public.briefing.action.source_event_ids,
        "blocker_reasons": [],
    }
    with pytest.raises(ValueError, match="exact current action and workflow"):
        RunIntelligenceResponse.model_validate(forged_move)


def test_fresh_public_report_keeps_one_exact_pre_workflow_action() -> None:
    from tests.test_internal_intelligence_service import _authorized_report

    public = to_public_intelligence_report(_authorized_report())

    assert public.briefing.action.setup_authorized is True
    assert public.test_preflight is None
    assert public.next_trustworthy_move is None
    assert public.best_measurement is not None
    assert public.best_measurement.procedure == [
        "Keep Cross Weight at the recorded baseline value.",
        (
            "Change only Cross Weight: 50.0% -> 50.1% "
            "(adjacent observed tech-passing option)."
        ),
        "Keep Cross Weight at the recorded baseline value.",
    ]


@pytest.mark.parametrize(
    ("field", "nested_field"),
    [
        ("blocker_reasons", None),
        ("briefing", "blocker_reasons"),
        ("data_quality", "issues"),
    ],
)
def test_public_schema_rejects_authorized_action_with_any_global_blocker(
    field: str,
    nested_field: str | None,
) -> None:
    from tests.test_internal_intelligence_service import _authorized_report

    payload = to_public_intelligence_report(_authorized_report()).model_dump(mode="json")
    if nested_field is None:
        payload[field] = ["A hostile late blocker was injected."]
    else:
        payload[field][nested_field] = ["A hostile late blocker was injected."]

    with pytest.raises(ValueError, match="no report, briefing, quality, or action blockers"):
        RunIntelligenceResponse.model_validate(payload)


def test_public_schema_rejects_appended_second_stage_b_command() -> None:
    from tests.test_internal_intelligence_service import _authorized_report

    payload = to_public_intelligence_report(_authorized_report()).model_dump(mode="json")
    payload["best_measurement"]["procedure"][1] += " Set tape to 99%."

    with pytest.raises(ValueError, match="exact authorized action"):
        RunIntelligenceResponse.model_validate(payload)


def test_public_schema_rejects_self_consistent_wrong_control_label() -> None:
    from tests.test_internal_intelligence_service import _authorized_report

    payload = to_public_intelligence_report(_authorized_report()).model_dump(mode="json")
    instruction = payload["briefing"]["action"]["instruction"]
    payload["best_measurement"]["controlled_variables"] = [
        "Change only Rear End Ratio."
    ]
    payload["best_measurement"]["procedure"] = [
        "Keep Rear End Ratio at the recorded baseline value.",
        f"Change only Rear End Ratio: {instruction}.",
        "Keep Rear End Ratio at the recorded baseline value.",
    ]

    with pytest.raises(ValueError, match="exact authorized action"):
        RunIntelligenceResponse.model_validate(payload)


def test_adapter_redacts_unauthorized_stage_b_but_preserves_safe_recovery() -> None:
    from racelab_engine.services.smart_guidance_service import build_smart_guidance
    from tests.test_internal_intelligence_service import _authorized_report, _workflow

    report = _authorized_report()
    workflow = _workflow().model_copy(
        update={
            "status": "a_recorded",
            "stage_run_ids": {"A": "run-1"},
            "stage_eligible_lap_numbers": {"A": (4, 5, 6)},
            "execution": None,
            "quality": None,
            "learning_admitted": False,
        }
    )
    guidance = build_smart_guidance(report, workflow=workflow)
    hostile = report.model_copy(
        update={
            "smart_guidance": guidance,
            "blocker_reasons": ("A late report blocker withdrew setup authority.",),
        }
    )

    public = to_public_intelligence_report(hostile)

    assert public.briefing.action.setup_authorized is False
    assert public.best_measurement is None
    assert public.mission_stage == "measure"
    assert public.test_preflight is not None
    assert public.test_preflight.stage == "B"
    assert public.test_preflight.status == "blocked"
    assert [check.check_id for check in public.test_preflight.checks] == [
        "current-card-authority"
    ]
    assert all(check.check_id != "setup-state" for check in public.test_preflight.checks)
    assert public.next_trustworthy_move is not None
    assert public.next_trustworthy_move.kind == "recover"
    assert public.next_trustworthy_move.authority == "navigation_only"
    assert public.next_trustworthy_move.control_key is None
    assert public.next_trustworthy_move.source_event_ids == ()


@pytest.mark.parametrize("status", ["ready", "blocked"])
def test_public_schema_rejects_unauthorized_stage_b_exact_detail(status: str) -> None:
    from racelab_engine.services.smart_guidance_service import build_smart_guidance
    from tests.test_internal_intelligence_service import _authorized_report, _workflow

    report = _authorized_report()
    workflow = _workflow().model_copy(
        update={
            "status": "a_recorded",
            "stage_run_ids": {"A": "run-1"},
            "stage_eligible_lap_numbers": {"A": (4, 5, 6)},
            "execution": None,
            "quality": None,
            "learning_admitted": False,
        }
    )
    guidance = build_smart_guidance(report, workflow=workflow)
    hostile = report.model_copy(
        update={
            "smart_guidance": guidance,
            "blocker_reasons": ("A late report blocker withdrew setup authority.",),
        }
    )
    payload = to_public_intelligence_report(hostile).model_dump(mode="json")
    payload["mission_stage"] = "measure" if status == "blocked" else "test"
    payload["test_preflight"] = {
        "workflow_id": workflow.workflow_id,
        "stage": "B",
        "status": status,
        "title": "Run the exact Stage B target",
        "checks": [
            {
                "check_id": "setup-state",
                "label": "Apply setup",
                "state": "blocked" if status == "blocked" else "required",
                "detail": guidance.test_preflight.checks[-1].detail,
            }
        ],
        "blocker_reasons": (
            ["The exact setup target is blocked."] if status == "blocked" else []
        ),
    }

    with pytest.raises(ValueError, match="redact exact setup detail"):
        RunIntelligenceResponse.model_validate(payload)


def test_run_intelligence_requires_the_exact_requested_session(tmp_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path)
    attached = create_session("Attached", db_path)
    unrelated = create_session("Unrelated", db_path)
    add_run_to_session(attached.session_id, "smart-run", db_path)

    try:
        build_run_intelligence(
            "smart-run",
            session_id=unrelated.session_id,
            db_path=db_path,
        )
    except ValueError as exc:
        assert "not attached" in str(exc)
    else:
        raise AssertionError("an unrelated session must not receive intelligence for this run")


def test_run_intelligence_rejects_non_list_session_membership(tmp_path: Path) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path, "run-A")
    session = create_session("Malformed", db_path)
    connection = initialize_database(db_path)
    with connection:
        connection.execute(
            "UPDATE racelab_sessions SET run_ids_json = ? WHERE session_id = ?",
            ('"prefix-run-A-suffix"', session.session_id),
        )
    connection.close()

    with pytest.raises(ValueError, match="run identities"):
        build_run_intelligence(
            "run-A",
            session_id=session.session_id,
            db_path=db_path,
        )


def test_explicit_session_rejects_multiple_active_controlled_workflows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path, "run-A")
    _seed_untrusted_run(db_path, "run-B")
    session = create_session("Two active tests", db_path)
    add_run_to_session(session.session_id, "run-A", db_path)
    add_run_to_session(session.session_id, "run-B", db_path)
    active = [
        SimpleNamespace(
            workflow_id=f"workflow-{run_id}",
            source_run_id=run_id,
            stage_run_ids={},
            status="planned",
        )
        for run_id in ("run-A", "run-B")
    ]
    monkeypatch.setattr(
        RaceLabRepository,
        "list_controlled_workflows_for_run_scope",
        lambda self, run_ids, active_only=False: (active, ()),
    )

    with pytest.raises(ValueError, match="Multiple active controlled workflows"):
        build_run_intelligence(
            "run-A",
            session_id=session.session_id,
            db_path=db_path,
        )

    with pytest.raises(ValueError, match="Multiple active controlled workflows"):
        _require_one_active_workflow_in_explicit_session(
            tuple(active),
            session_id=session.session_id,
        )


def test_intelligence_api_exposes_only_grounded_intent_fields(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path)
    bundle = build_run_intelligence("smart-run", db_path=db_path)
    monkeypatch.setattr(
        "api.routes_intelligence.build_run_intelligence",
        lambda run_id, session_id=None: bundle,
    )
    monkeypatch.setattr(
        "api.routes_intelligence.record_driver_presentation_preference_for_run",
        lambda *args, **kwargs: None,
    )

    report = client.get("/api/runs/smart-run/intelligence")
    engineer_refresh = client.get(
        "/api/runs/smart-run/intelligence",
        params={"refresh": '["smart-run"]:workflow-1:2026-08-09T12:00:00Z:1'},
    )
    shell_refresh = client.get(
        "/api/runs/smart-run/intelligence",
        params={
            "refresh": (
                '{"run_id":"smart-run","selected_lap":2,'
                '"session_run_scope":"[\\"smart-run\\"]"}'
            )
        },
    )
    oversized_refresh = client.get(
        "/api/runs/smart-run/intelligence",
        params={"refresh": "r" * 1025},
    )
    query = client.post(
        "/api/runs/smart-run/intelligence/query",
        json={
            "question": "What should I do next?",
            "selected_lap": 2,
            "presentation_mode": "learning",
        },
    )
    window_query = client.post(
        "/api/runs/smart-run/intelligence/query",
        json={
            "question": "Is the data good on laps 1-3?",
            "selected_lap": 2,
            "selected_window_start_lap": 1,
            "selected_window_end_lap": 3,
            "selected_window_representative_lap": 2,
            "presentation_mode": "learning",
        },
    )
    injected = client.post(
        "/api/runs/smart-run/intelligence/query",
        json={
            "question": "What should I do next?",
            "setup_authorized": True,
            "proposed_value": "invented",
        },
    )
    monkeypatch.setattr(
        "api.routes_intelligence.record_driver_presentation_preference_for_run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("corrupt presentation memory")
        ),
    )
    query_with_profile_failure = client.post(
        "/api/runs/smart-run/intelligence/query",
        json={
            "question": "Is the data good?",
            "selected_lap": 2,
            "presentation_mode": "race",
        },
    )
    monkeypatch.setattr(
        "api.routes_intelligence.answer_grounded_query",
        lambda *args, **kwargs: SimpleNamespace(
            supported=True,
            intent="what_worked_before",
            answer="Open the exact-context source run.",
                citations=(),
                suggested_navigation=(
                    NavigationTarget(workspace="dial_in", run_id="smart-run"),
            ),
            mind_change_criteria=(),
            interpreted_lap_number=None,
            interpreted_window_start_lap=None,
            interpreted_window_end_lap=None,
            interpreted_window_representative_lap=None,
            interpreted_phase=None,
            interpreted_control_key=None,
            clarification_required=False,
            action_authorized=False,
            action_source_event_ids=(),
            blocker_reasons=(),
        ),
    )
    navigation_query = client.post(
        "/api/runs/smart-run/intelligence/query",
        json={"question": "What worked here before?"},
    )
    monkeypatch.setattr(
        "api.routes_intelligence.answer_grounded_query",
        lambda *args, **kwargs: SimpleNamespace(
            supported=True,
            intent="what_worked_before",
            answer="Open the exact-context source run.",
            citations=(),
            suggested_navigation=(
                NavigationTarget(workspace="dial_in", run_id="outside-session"),
            ),
            mind_change_criteria=(),
            interpreted_lap_number=None,
            interpreted_window_start_lap=None,
            interpreted_window_end_lap=None,
            interpreted_window_representative_lap=None,
            interpreted_phase=None,
            interpreted_control_key=None,
            clarification_required=False,
            action_authorized=False,
            action_source_event_ids=(),
            blocker_reasons=(),
        ),
    )
    outside_navigation_query = client.post(
        "/api/runs/smart-run/intelligence/query",
        json={"question": "What worked here before?"},
    )

    assert report.status_code == 200
    assert engineer_refresh.status_code == 200
    assert shell_refresh.status_code == 200
    assert oversized_refresh.status_code == 422
    report_payload = report.json()
    assert report_payload["run_id"] == "smart-run"
    assert report_payload["decision_status"] == bundle.report.status
    assert isinstance(report_payload["mind_change_criteria"], list)
    assert report_payload["opportunity_signature"]["authority"] == "observation_only"
    assert report_payload["driver_focus"]["authority"] == "driver_coaching_only"
    assert report_payload["next_trustworthy_move"]["authority"] == "navigation_only"
    assert report_payload["measurement_debt"]["status"] in {"open", "blocked"}
    assert query.status_code == 200
    query_payload = query.json()
    assert query_payload["selected_lap"] == 2
    assert query_payload["action_authorized"] is False
    assert query_payload["action_source_event_ids"] == []
    assert isinstance(query_payload["suggested_navigation"], list)
    assert window_query.status_code == 200
    window_payload = window_query.json()
    assert window_payload["selected_lap"] == 2
    assert window_payload["interpreted_window_start_lap"] == 1
    assert window_payload["interpreted_window_end_lap"] == 3
    assert window_payload["interpreted_window_representative_lap"] == 2
    assert injected.status_code == 422
    assert query_with_profile_failure.status_code == 200
    assert navigation_query.status_code == 200
    navigation_payload = navigation_query.json()
    assert navigation_payload["evidence_state"] == "needs_confirmation"
    assert navigation_payload["suggested_navigation"] == [
        {
            "workspace": "dial_in",
            "run_id": "smart-run",
            "lap_number": None,
            "event_id": None,
            "lap_pct": None,
        }
    ]
    assert outside_navigation_query.status_code == 200
    outside_payload = outside_navigation_query.json()
    assert outside_payload["suggested_navigation"] == []
    assert "outside the open run/session scope was withheld" in outside_payload["answer"]


def test_text_only_lap_window_query_fails_closed_without_response_validation_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path)
    bundle = build_run_intelligence("smart-run", db_path=db_path)
    monkeypatch.setattr(
        "api.routes_intelligence.build_run_intelligence",
        lambda run_id, session_id=None: bundle,
    )

    response = client.post(
        "/api/runs/smart-run/intelligence/query",
        json={"question": "Where is the loss on laps 1-3?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["clarification_required"] is True
    assert "representative lap" in payload["answer"]
    assert payload["interpreted_window_start_lap"] is None
    assert payload["interpreted_window_end_lap"] is None
    assert payload["interpreted_window_representative_lap"] is None


def test_omitted_session_keeps_intelligence_in_run_only_scope(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "racelab.sqlite"
    _seed_untrusted_run(db_path)
    first = create_session("First", db_path)
    second = create_session("Second", db_path)
    for session in (first, second):
        add_run_to_session(session.session_id, "smart-run", db_path)

    bundle = build_run_intelligence("smart-run", db_path=db_path)

    assert bundle.report.session_id is None
    assert bundle.calibration.scope_run_ids == ("smart-run",)


def test_context_memory_links_qualified_source_runs_without_inventing_an_event() -> None:
    memory = ResponseMemorySummary(
        context_key="exact-context",
        status="exact_context_match",
        control_key="front_ride_height",
        direction_sign=1,
        qualified_observation_count=1,
        verdicts=("keep",),
        source_observation_ids=("observation-1",),
        source_run_ids=("source-a", "source-b", "source-a2"),
        evidence_event_ids=("old-event",),
        matching_context=("same car", "same track"),
    )

    public = _context_match(memory, {})

    assert {citation.run_id for citation in public.citations} == {
        "source-a", "source-b", "source-a2",
    }
    assert all(citation.event_id is None for citation in public.citations)
    assert all(
        citation.evidence_state == EvidenceState.CONTROLLED_TEST_EFFECT
        for citation in public.citations
    )
    assert all(
        citation.source_channels == ["controlled_workflow_outcome"]
        for citation in public.citations
    )
    assert all(citation.valid_for_tuning is False for citation in public.citations)


def test_historical_event_reference_cannot_bind_a_current_run_id_collision() -> None:
    current = IntelligenceCitationResponse(
        citation_id="event:shared-event",
        label="Current run event",
        run_id="current-run",
        lap_number=4,
        event_id="shared-event",
        workspace="platform_trace",
        source_channels=["Speed"],
        evidence_state=EvidenceState.MEASURED,
        valid_for_tuning=True,
    )
    entry = EngineeringNarrativeEntry(
        entry_id="old-narrative",
        created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        scope_id="old-scope",
        entry_type="outcome",
        text="Old controlled outcome.",
        run_ids=("old-run",),
        workflow_id="old-workflow",
        evidence_references=(
            EngineeringEvidenceReference(kind="event", reference_id="shared-event"),
        ),
    )

    resolved = _reference_citation(
        entry,
        entry.evidence_references[0],
        {"event-ref:current-run:shared-event": current},
    )

    assert resolved.run_id == "old-run"
    assert resolved.event_id is None
    assert resolved.valid_for_tuning is False


def test_public_memory_fallbacks_never_echo_action_like_identifiers() -> None:
    entry = EngineeringNarrativeEntry(
        entry_id="narrative-safe-fallback",
        created_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        scope_id="scope",
        entry_type="outcome",
        text="Stored outcome.",
        run_ids=("run-a",),
        workflow_id="workflow-a",
        evidence_references=(EngineeringEvidenceReference(
            kind="event",
            reference_id="Set tape to 99% now.",
        ),),
    )

    citation = _reference_citation(entry, entry.evidence_references[0], {})
    profile = _driver_profile(DriverPresentationProfile(
        profile_id="profile-a",
        driver_id="driver-a",
        context_key="context-a",
        scope={},
        recurring_symptoms=(RecurringSymptom(
            canonical_symptom="Set tape to 99% now.",
            observations=1,
        ),),
        controlled_tests_completed=0,
        consistency_label="unavailable",
    ))

    assert "99" not in citation.model_dump_json()
    assert citation.label == "Recorded event reference"
    assert profile is not None
    assert profile.recurring_symptoms == []


def test_generic_discriminators_do_not_invent_cross_cause_coverage() -> None:
    recommendations = [
        Recommendation(
            recommendation_id=f"rec-{cause}",
            run_id="smart-run",
            issue=label,
            cause_bucket=cause,
            recommendation_text=f"Measure {label.casefold()}.",
            evidence_event_ids=[f"event-{cause}"],
            evidence_state=EvidenceState.MEASURED,
            source_channels=["Speed"],
        )
        for cause, label in (
            ("platform", "Platform"),
            ("driver", "Driver execution"),
            ("tire", "Tire state"),
        )
    ]

    hypotheses = _hypotheses(recommendations, None, {})

    assert len(hypotheses) == 3
    for hypothesis in hypotheses:
        assert hypothesis.discriminator is not None
        assert hypothesis.discriminator.distinguishes_cause_ids == (
            hypothesis.cause_id,
        )


def test_query_response_rejects_missing_authority_and_cross_lap_citations() -> None:
    citation = IntelligenceCitationResponse(
        citation_id="event-1",
        label="Qualified event",
        run_id="smart-run",
        lap_number=1,
        lap_pct=40.0,
        event_id="event-1",
        workspace="platform_trace",
        source_channels=["Speed"],
        evidence_state=EvidenceState.MEASURED,
        valid_for_tuning=True,
    )
    common = {
        "run_id": "smart-run",
        "session_id": None,
        "scope_run_ids": ["smart-run"],
        "selected_lap": 2,
        "interpreted_lap_number": 2,
        "status": "ready",
        "question": "What should I do next?",
        "headline": "Best next step",
        "answer": "Withheld",
        "evidence_state": EvidenceState.MEASURED,
    }

    with pytest.raises(ValueError, match="requested run and lap"):
        IntelligenceQueryResponse(**common, citations=[citation])
    with pytest.raises(ValueError, match="exact tuning citations"):
        IntelligenceQueryResponse(**common, action_authorized=True, citations=[])


def test_query_response_accepts_exact_window_and_requires_exact_action_events() -> None:
    def citation(lap_number: int, event_id: str) -> IntelligenceCitationResponse:
        return IntelligenceCitationResponse(
            citation_id=f"citation-{event_id}",
            label=f"Qualified event on lap {lap_number}",
            run_id="smart-run",
            lap_number=lap_number,
            lap_pct=40.0,
            event_id=event_id,
            workspace="platform_trace",
            source_channels=["Speed"],
            evidence_state=EvidenceState.MEASURED,
            valid_for_tuning=True,
        )

    citations = [citation(4, "event-4"), citation(5, "event-5")]
    common = {
        "run_id": "smart-run",
        "session_id": None,
        "scope_run_ids": ["smart-run"],
        "selected_lap": 4,
        "status": "ready",
        "question": "What should I do next on laps 4-5?",
        "headline": "Best next step",
        "answer": "Run the controlled test.",
        "interpreted_lap_number": 4,
        "interpreted_window_start_lap": 4,
        "interpreted_window_end_lap": 5,
        "interpreted_window_representative_lap": 4,
        "action_authorized": True,
        "action_source_event_ids": ["event-4", "event-5"],
        "evidence_state": EvidenceState.MEASURED,
        "citations": citations,
        "suggested_navigation": [
            NavigationTarget(
                workspace="platform",
                run_id="smart-run",
                lap_number=5,
                event_id="event-5",
                lap_pct=40.0,
            ).model_dump()
            | {"workspace": "platform_trace"},
        ],
    }

    response = IntelligenceQueryResponse(**common)
    assert [item.lap_number for item in response.citations] == [4, 5]
    assert response.action_source_event_ids == ["event-4", "event-5"]

    for hostile_update in (
        {"status": "unavailable"},
        {"clarification_required": True},
        {"blocker_reasons": ["The answer is blocked."]},
        {"evidence_state": EvidenceState.NEEDS_CONFIRMATION},
    ):
        with pytest.raises(ValueError, match="ready, unambiguous, unblocked qualified"):
            IntelligenceQueryResponse(**(common | hostile_update))

    with pytest.raises(ValueError, match="exact source event set"):
        IntelligenceQueryResponse(
            **(common | {"action_source_event_ids": ["event-4"]})
        )
    with pytest.raises(ValueError, match="interpreted lap window"):
        IntelligenceQueryResponse(
            **(common | {"citations": [*citations, citation(6, "event-6")]})
        )
    with pytest.raises(ValueError, match="selected representative lap"):
        IntelligenceQueryResponse(**(common | {"selected_lap": 3}))


def test_query_request_requires_one_exact_selected_scope() -> None:
    request = IntelligenceQueryRequest(
        question="What changed in this window?",
        selected_lap=4,
        selected_window_start_lap=2,
        selected_window_end_lap=6,
        selected_window_representative_lap=4,
    )

    assert request.selected_window_start_lap == 2
    assert request.selected_window_end_lap == 6
    assert request.selected_window_representative_lap == 4

    with pytest.raises(ValueError, match="start, end, and representative"):
        IntelligenceQueryRequest(
            question="What changed in this window?",
            selected_lap=4,
            selected_window_start_lap=2,
        )
    with pytest.raises(ValueError, match="selected window representative"):
        IntelligenceQueryRequest(
            question="What changed in this window?",
            selected_lap=5,
            selected_window_start_lap=2,
            selected_window_end_lap=6,
            selected_window_representative_lap=4,
        )


def test_query_response_allows_only_non_action_history_from_exact_session_scope() -> None:
    history = IntelligenceCitationResponse(
        citation_id="history-run-a",
        label="Prior qualified run",
        run_id="run-a",
        lap_number=4,
        workspace="laps",
        source_channels=[],
        evidence_state=EvidenceState.OBSERVED_CORRELATION,
        valid_for_tuning=False,
    )
    common = {
        "run_id": "run-b",
        "session_id": "session-1",
        "scope_run_ids": ["run-a", "run-b"],
        "status": "ready",
        "question": "What changed?",
        "headline": "Qualified session change",
        "answer": "Run B improved relative to Run A.",
        "evidence_state": EvidenceState.OBSERVED_CORRELATION,
        "citations": [history],
    }

    response = IntelligenceQueryResponse(**common)
    assert response.citations == [history]

    with pytest.raises(ValueError, match="run-only queries"):
        IntelligenceQueryResponse(
            **(common | {"session_id": None})
        )
    with pytest.raises(ValueError, match="exact tuning citations"):
        IntelligenceQueryResponse(
            **(
                common
                | {
                    "action_authorized": True,
                    "action_source_event_ids": ["history-event"],
                }
            )
        )
    with pytest.raises(ValueError, match="exact run/session scope"):
        IntelligenceQueryResponse(
            **(common | {"scope_run_ids": ["run-b"]})
        )


def test_query_navigation_adapter_is_navigation_only_and_maps_public_workspaces() -> None:
    public = to_public_intelligence_navigation(
        NavigationTarget(
            workspace="setup",
            run_id="source-run",
            lap_number=7,
            event_id="source-event",
            lap_pct=52.5,
        )
    )

    assert public.workspace == "setup_impact"
    assert public.run_id == "source-run"
    assert public.lap_number == 7
    assert public.event_id == "source-event"
    assert "authority" not in public.model_dump()
    assert "valid_for_tuning" not in public.model_dump()


def test_mind_change_criteria_are_public_safe_and_exactly_scope_bound() -> None:
    criterion = MindChangeCriterion(
        criterion_id="criterion-platform",
        cause_id="platform",
        current_state="possible",
        evidence_kind="discriminator",
        run_id="smart-run",
        session_id="session-1",
        metric="Matched-position platform compression",
        phase="entry",
        threshold_source="Driver-specific same-setup noise floor",
        acceptance_conditions=("Compression repeats above the measured noise floor.",),
        falsification_conditions=("Compression remains inside the measured noise floor.",),
        minimum_independent_evidence_units=2,
        minimum_evidence="Two independent eligible laps at matched track position.",
        next_state_if_accepted="possible",
        next_state_if_falsified="unresolved",
    )

    public = to_public_mind_change_criterion(criterion)
    assert public.run_id == "smart-run"
    assert public.session_id == "session-1"
    assert "setup_authorized" not in public.model_dump()
    assert "proposed_value" not in public.model_dump()

    common = {
        "run_id": "smart-run",
        "session_id": "session-1",
        "scope_run_ids": ["smart-run"],
        "status": "ready",
        "question": "What would change your mind?",
        "headline": "What would change the call",
        "answer": "Repeat the discriminator.",
        "evidence_state": EvidenceState.NEEDS_CONFIRMATION,
        "mind_change_criteria": [public],
    }
    response = IntelligenceQueryResponse(**common)
    assert response.mind_change_criteria == [public]

    wrong_scope = IntelligenceMindChangeCriterionResponse(
        **(public.model_dump() | {"run_id": "other-run"})
    )
    with pytest.raises(ValueError, match="exact query scope"):
        IntelligenceQueryResponse(
            **(common | {"mind_change_criteria": [wrong_scope]})
        )


def test_evidence_graph_inputs_never_copy_setup_action_prose_or_exact_values() -> None:
    recommendation = Recommendation(
        recommendation_id="ready-rec",
        run_id="smart-run",
        issue="Platform compression",
        cause_bucket="platform",
        recommendation_text="Decrease front ride height from 50.0 to 49.5.",
        evidence_event_ids=["event-platform"],
        evidence_state=EvidenceState.MEASURED,
        source_channels=["CFSRideHeight"],
    )
    card = _controlled_card()
    workflow = SimpleNamespace(
        workflow_id="workflow-1",
        packet=SimpleNamespace(
            primary_test=card,
            race_mode_summary="Test one change: 50.0 -> 49.5.",
            evidence_state=EvidenceState.MEASURED,
            opportunity=SimpleNamespace(
                evidence_event_ids=("event-platform",),
                source_channels=("CFSRideHeight",),
            ),
            blockers=(),
        ),
    )

    claims = _claims([recommendation], workflow)
    setup_values = _setup_values(workflow)
    visible_claim_text = " ".join(claim.text for claim in claims)

    assert "49.5" not in visible_claim_text
    assert "Decrease front ride height" not in visible_claim_text
    assert "Platform evidence" in visible_claim_text
    assert setup_values[0].value_display is None


def test_run_orchestration_blocks_blank_recommendation_semantics_without_crashing() -> None:
    malformed = Recommendation(
        recommendation_id="blank-rec",
        run_id="smart-run",
        issue="   ",
        cause_bucket="   ",
        recommendation_text="   ",
        evidence_event_ids=["event-1"],
        evidence_state=EvidenceState.MEASURED,
        source_channels=["Speed"],
    )

    claims = _claims([malformed], None)
    hypotheses = _hypotheses([malformed], None, {})

    assert claims[0].text.startswith("Unresolved telemetry evidence")
    assert claims[0].evidence_state == EvidenceState.BLOCKED_BY_CONTEXT
    assert hypotheses == ()


def test_persisted_card_requires_complete_semantics_and_nonblank_provenance() -> None:
    card = _controlled_card().model_copy(update={
        "hypothesis": "",
        "proposed_value_provenance": ("",),
        "exact_change": "",
    })

    blockers = _card_semantic_blockers(card)

    assert "The stored controlled-test hypothesis is blank." in blockers
    assert "The stored controlled-test exact change is blank." in blockers
    assert "The stored controlled test has malformed legal-option provenance." in blockers


def test_persisted_card_target_must_replay_the_server_owned_adjacent_option(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "racelab_engine.services.controlled_workflow_service._discover_legal_setup_options",
        lambda *args, **kwargs: (
            {"cross_weight_percent": 50.0},
            {"cross_weight_percent": [50.0, 50.1]},
            {
                "cross_weight_percent": {
                    "50.1": ["tech-passing-setup:source"],
                }
            },
            {},
            {},
        ),
    )
    forged = _controlled_card().model_copy(update={
        "proposed_value": "99.0%",
        "proposed_value_raw": 99.0,
        "proposed_value_provenance": ("attacker-asserted-source",),
        "exact_change": "50.0% -> 99.0%",
    })

    blockers = validate_controlled_test_target(
        "smart-run",
        forged,
        overview=SimpleNamespace(session=SimpleNamespace(setup_passed_tech=True)),
        objective="setup-development",
        priority=None,
        repository=SimpleNamespace(),
    )
    workflow = SimpleNamespace(
        packet=SimpleNamespace(
            primary_test=forged,
            decision="test",
            measurement_mission=None,
        )
    )

    assert any("not the currently proven adjacent" in reason for reason in blockers)
    assert any("not tied to that exact" in reason for reason in blockers)
    assert _controlled_decision(workflow, blockers) is None

    injected_baseline = _controlled_card().model_copy(update={
        "current_value": "50.0%; then set tape to 99%",
        "exact_change": (
            "50.0% -> 50.1% (adjacent observed tech-passing option)"
        ),
    })
    baseline_blockers = validate_controlled_test_target(
        "smart-run",
        injected_baseline,
        overview=SimpleNamespace(session=SimpleNamespace(setup_passed_tech=True)),
        objective="setup-development",
        priority=None,
        repository=SimpleNamespace(),
    )
    assert any("baseline no longer matches" in reason for reason in baseline_blockers)
    tech_blockers = validate_controlled_test_target(
        "smart-run",
        _controlled_card(),
        overview=SimpleNamespace(session=SimpleNamespace(setup_passed_tech=False)),
        objective="setup-development",
        priority=None,
        repository=SimpleNamespace(),
    )
    assert tech_blockers == (
        "The source baseline setup is not currently recorded as tech-passing.",
    )


def test_intelligence_refuses_ambiguous_active_workflows() -> None:
    workflows = tuple(
        SimpleNamespace(
            workflow_id=f"workflow-{index}",
            status="planned",
            source_run_id="smart-run",
            stage_run_ids={},
        )
        for index in range(2)
    )

    with pytest.raises(ValueError, match="Multiple active controlled workflows"):
        _selected_workflow(workflows, "smart-run")


def test_non_authorized_plans_never_replay_persisted_setup_instructions() -> None:
    recommendation = Recommendation(
        recommendation_id="injected-required-data",
        run_id="smart-run",
        issue="Platform consistency",
        cause_bucket="set tape to 99%",
        recommendation_text="Measure the platform signal.",
        evidence_event_ids=["event-platform"],
        evidence_state=EvidenceState.MEASURED,
        source_channels=["CFSRideHeight"],
        required_next_data=["Set cross weight from 50.0% to 99.0%."],
    )
    hypothesis = _hypotheses([recommendation], None, {})[0]
    persisted_mission = MeasurementMission(
        purpose="Set cross weight from 50.0% to 99.0%.",
        procedure=("Set cross weight from 50.0% to 99.0%.",),
        required_laps_or_passes=1,
        controlled_variables=("cross weight 99.0%",),
        target_phase="cross weight 99.0%",
        acceptance_thresholds=("cross weight reaches 99.0%",),
        stop_rule="Keep 99.0%.",
        blockers=("Set 99.0%.",),
    )
    workflow = SimpleNamespace(
        packet=SimpleNamespace(
            primary_test=None,
            decision="measure",
            measurement_mission=persisted_mission,
        )
    )

    decision = _controlled_decision(workflow)
    assert decision is not None and decision.mission is not None
    visible = " ".join((
        hypothesis.label,
        hypothesis.discriminator.title,
        hypothesis.discriminator.instruction,
        decision.mission.purpose,
        *decision.mission.procedure,
        *decision.mission.controlled_variables,
        decision.mission.target_phase,
        *decision.mission.acceptance_thresholds,
        decision.mission.stop_rule,
        *decision.mission.blockers,
    ))
    assert "99.0" not in visible
    assert "Set cross weight" not in visible
    assert "Set Tape" not in visible

    workflow_hypothesis = _hypotheses(
        [],
        SimpleNamespace(packet=SimpleNamespace(
            primary_test=_controlled_card(),
            primary_cause_bucket="set tape to 99%",
            blockers=(),
        )),
        {},
        ("Stored workflow authority is blocked.",),
    )[0]
    assert "99%" not in workflow_hypothesis.model_dump_json()
    assert workflow_hypothesis.cause_id == (
        "workflow:setup_control_cross_weight_percent"
    )


def test_mutated_protocol_is_rejected_against_rebuilt_server_evidence(
    monkeypatch,
) -> None:
    canonical = _controlled_card()
    forged = canonical.model_copy(update={
        "success_metrics": ("Set tape to 99% after the run.",),
        "stop_rule": "Stop, then set tape to 99%.",
    })
    opportunity = OpportunityEvidence(
        start_pct=20.0,
        end_pct=30.0,
        phase="entry",
        observed_time_loss_s=0.2,
        empirical_noise_s=0.04,
        alignment_confidence=0.95,
        repeatable=True,
        evidence_links=(),
        source_channels=("lap_dist_pct_100", "speed_mps"),
    )
    rebuilt_packet = KaizenEvidencePacket(
        decision="test",
        opportunity=opportunity,
        canonical_symptom="tight_entry",
        primary_cause_bucket="corner_balance",
        evidence_state=EvidenceState.NEEDS_CONFIRMATION,
        confidence_score=0.9,
        blockers=(),
        supporting_evidence=(),
        contradictory_evidence=(),
        primary_test=canonical,
        held_back_alternatives=0,
        race_mode_summary="Test one server-owned change.",
        learning_mode_explanation="Server-owned protocol.",
    )
    stored_packet = rebuilt_packet.model_copy(update={"primary_test": forged})
    monkeypatch.setattr(
        "racelab_engine.services.controlled_workflow_service.build_server_kaizen_packet",
        lambda *args, **kwargs: rebuilt_packet,
    )
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    workflow = ControlledWorkflow(
        workflow_id="workflow-mutated-protocol",
        created_at=now,
        updated_at=now,
        status="planned",
        source_run_id="smart-run",
        complaint="tight in the center",
        reproduction_snapshot={"decision_context": {
            "selected_lap": None,
            "lap_scope": "run",
            "window_start_lap": None,
            "window_end_lap": None,
            "representative_lap": None,
            "selected_zone_start_pct": None,
            "selected_zone_end_pct": None,
            "selected_zone_label": None,
            "selected_phase": None,
            "objective": "setup-development",
            "priority": None,
        }},
        packet=rebuilt_packet,
    )
    workflow.reproduction_snapshot["plan_binding_sha256"] = _workflow_plan_binding_hash(
        workflow,
        rebuilt_packet,
        _workflow_decision_context(workflow),
    )
    workflow = workflow.model_copy(update={"packet": stored_packet})

    packet, blockers = revalidate_controlled_test_packet(
        workflow,
        repository=SimpleNamespace(),
    )

    assert packet is None
    assert any("packet" in blocker and "plan binding" in blocker for blocker in blockers)


def test_active_source_run_card_uses_event_provenance_without_claiming_an_outcome() -> None:
    lap = LapSummary(
        lap_id="smart-run:lap:2",
        run_id="smart-run",
        lap_number=2,
        lap_type="flying",
        is_complete=True,
        is_useful=True,
        lap_time=90.0,
        pct_min=0.0,
        pct_max=100.0,
        pct_span=100.0,
        sample_count=1_000,
        avg_speed_mph=110.0,
        min_speed_mph=75.0,
        classification_tags=["SOLO_CLEAN"],
    )
    event = TelemetryEvent(
        event_id="event-platform",
        run_id="smart-run",
        lap_number=2,
        event_type="platform_balance",
        event_subtype="center_settle",
        lap_pct_start=42.0,
        lap_pct_end=45.0,
        lap_pct_peak=43.5,
        valid_for_tuning=True,
        related_setup_keys=["cross_weight_percent"],
        evidence_state=EvidenceState.CALCULATED,
        source_channels=["Speed"],
        blocker_reasons=[],
    )
    director = build_controlled_test(
        control_key="cross_weight_percent",
        current_value=50.0,
        direction_sign=1,
        hypothesis="Test whether center platform recovery improves.",
        target_phase="center",
        success_metrics=["Center time improves beyond the empirical noise floor."],
        countereffects=["Entry time must not worsen beyond normal variation."],
        evidence_links=[TestEvidenceLink(
            event_id=event.event_id,
            eligible_lap=True,
            valid_for_tuning=True,
            phase="center",
            related_setup_keys=("cross_weight_percent",),
        )],
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values=[50.0, 50.1],
        legal_value_provenance={"50.1": ["tech-passing-setup:source"]},
    )
    assert director.card is not None
    card = director.card
    workflow = SimpleNamespace(
        workflow_id="workflow-active",
        source_run_id="smart-run",
        status="planned",
        quality=None,
        execution=None,
        stage_run_ids={},
        stage_eligible_lap_numbers={},
        packet=SimpleNamespace(
            primary_test=card,
            primary_cause_bucket="corner_balance",
            evidence_state=EvidenceState.MEASURED,
            opportunity=SimpleNamespace(
                evidence_event_ids=(event.event_id,),
                source_channels=("Speed",),
            ),
            blockers=(),
            decision="test",
            measurement_mission=None,
        ),
    )
    graph = build_evidence_graph(
        claims=_claims([], workflow),
        events=(event,),
        laps=(lap,),
        setup_values=_setup_values(workflow),
        workflows=(workflow,),
        setup_authority_verifier=_repository_setup_authority_verifier(
            workflow,
            requested_run_id="smart-run",
            card_blockers=(),
        ),
    )
    ranked = rank_competing_causes(
        _hypotheses([], workflow, {event.event_id: event}),
        graph,
    )
    plan = plan_best_next_measurement(
        ranked,
        controlled_decision=director,
        graph=graph,
    )

    setup_node = next(node for node in graph.nodes if node.node_id == "setup:cross_weight_percent")
    workflow_node = next(node for node in graph.nodes if node.node_id == "workflow:workflow-active")
    assert setup_node.qualified is True
    assert workflow_node.qualified is False
    assert [citation.event_id for citation in ranked[0].supporting_evidence] == [
        event.event_id
    ]
    assert any(
        edge.source_node_id == f"event:{event.event_id}"
        and edge.target_node_id == "setup:cross_weight_percent"
        and edge.qualified
        for edge in graph.edges
    )
    assert plan.kind == "controlled_test", plan
    assert plan.setup_authorized is True
