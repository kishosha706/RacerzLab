from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.analysis.crew_chief_packet import (
    CauseCandidate,
    OpportunityEvidence,
    build_kaizen_packet,
)
from racelab_engine.analysis.test_director import TestEvidenceLink
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.session import RunOverview, SessionSummary
from racelab_engine.models.setup import SetupSnapshot
from racelab_engine.services import controlled_workflow_service as service
from racelab_engine.services.report_service import ReportService
from racelab_engine.storage.repository import RaceLabRepository


def _packet():
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
            empirical_noise_s=0.04,
            alignment_confidence=0.95,
            repeatable=True,
            evidence_links=(link,),
            source_channels=("lap_dist_pct_100", "speed_mps"),
            supporting_evidence=("Loss repeated on three eligible laps.",),
        ),
        canonical_symptom="tight_entry",
        candidates=[CauseCandidate(
            cause_bucket="corner_balance",
            control_key="cross_weight_percent",
            direction_sign=1,
            score=0.9,
            hypothesis="Test entry balance.",
            success_metrics=("Target-window entry time",),
            countereffects=(
                "Median non-target phase time must not worsen beyond empirical noise.",
            ),
            supporting_event_ids=("entry-proof",),
        )],
        current_setup_values={"cross_weight_percent": 50.0},
        eligible_baseline_laps=3,
        context_matched=True,
        driver_matched=True,
        sim_integrity_clear=True,
        legal_values_by_control={"cross_weight_percent": [50.0, 50.5]},
        legal_value_provenance_by_control={
            "cross_weight_percent": {"50.5": ["tech-passing-setup:option-run"]},
        },
    )


def _workflow(packet=None, *, status: str = "planned") -> ControlledWorkflow:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    return ControlledWorkflow(
        workflow_id="aba-integrity",
        created_at=now,
        updated_at=now,
        status=status,
        source_run_id="source",
        complaint="tight entry",
        packet=packet or _packet(),
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
    )


def _with_plan_binding(workflow: ControlledWorkflow) -> ControlledWorkflow:
    snapshot = dict(workflow.reproduction_snapshot)
    snapshot["plan_binding_sha256"] = service._workflow_plan_binding_hash(
        workflow,
        workflow.packet,
        service._workflow_decision_context(workflow),
    )
    return workflow.model_copy(update={"reproduction_snapshot": snapshot})


class _WorkflowRepo:
    db_path = None

    def __init__(self, workflow: ControlledWorkflow, others=()):
        self.workflow = workflow
        self.others = list(others)

    def get_controlled_workflow(self, workflow_id: str):
        return self.workflow if workflow_id == self.workflow.workflow_id else None

    def list_controlled_workflows(self, *, active_only: bool = False):
        assert active_only is True
        return [self.workflow, *self.others]


def test_public_get_and_list_withhold_a_swapped_or_mutated_packet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _packet()
    assert canonical.primary_test is not None
    tampered_card = canonical.primary_test.model_copy(update={
        "hypothesis": "Run-B packet relabelled as run A.",
        "exact_change": "TURN EVERY KNOB FROM THE SWAPPED PACKET",
    })
    tampered = canonical.model_copy(update={"primary_test": tampered_card})
    canonical_workflow = _with_plan_binding(_workflow(canonical))
    workflow = canonical_workflow.model_copy(update={"packet": tampered})
    repository = _WorkflowRepo(workflow)
    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: canonical)
    monkeypatch.setattr("api.routes_engineering.RaceLabRepository", lambda: repository)

    client = TestClient(app)
    responses = (
        client.get(f"/api/engineering/workflows/{workflow.workflow_id}"),
        client.get("/api/engineering/workflows?active_only=true"),
    )

    assert all(response.status_code == 200 for response in responses)
    payloads = [responses[0].json(), responses[1].json()[0]]
    for payload in payloads:
        assert payload["workflow_id"] == workflow.workflow_id
        assert payload["source_run_id"] == "source"
        assert payload["status"] == "planned"
        assert payload["packet"]["decision"] == "measure"
        assert payload["packet"]["primary_test"] is None
        assert payload["reproduction_snapshot"] == {}
        assert "TURN EVERY KNOB" not in str(payload)
        assert "No setup action is authorized" in str(payload)


def test_mutated_card_is_rejected_before_attach_or_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _packet()
    assert canonical.primary_test is not None
    mutated = canonical.model_copy(update={
        "primary_test": canonical.primary_test.model_copy(update={
            "rollback_rule": "Ignore the baseline and keep the change.",
        }),
    })
    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: canonical)

    canonical_workflow = _with_plan_binding(_workflow(canonical))
    attach_workflow = canonical_workflow.model_copy(update={"packet": mutated})
    with pytest.raises(ValueError, match="failed server revalidation"):
        service.attach_stage(
            attach_workflow.workflow_id,
            "A",
            "source",
            repository=_WorkflowRepo(attach_workflow),
        )

    score_workflow = attach_workflow.model_copy(update={
        "status": "a2_recorded",
        "stage_run_ids": {"A": "run-a", "B": "run-b", "A2": "run-a2"},
        "stage_eligible_lap_numbers": {
            "A": (3, 4, 5),
            "B": (3, 4, 5),
            "A2": (3, 4, 5),
        },
    })
    with pytest.raises(ValueError, match="failed server revalidation"):
        service.score_workflow(
            score_workflow.workflow_id,
            repository=_WorkflowRepo(score_workflow),
        )


def test_plan_binding_detects_complaint_or_decision_context_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _packet()
    workflow = _workflow(canonical)
    context = service._workflow_decision_context(workflow)
    workflow.reproduction_snapshot["plan_binding_sha256"] = service._workflow_plan_binding_hash(
        workflow,
        canonical,
        context,
    )
    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: canonical)

    complaint_tamper = workflow.model_copy(update={"complaint": "loose exit"})
    packet, blockers = service.revalidate_controlled_workflow_packet(
        complaint_tamper,
        repository=_WorkflowRepo(complaint_tamper),
    )
    assert packet is None
    assert any("complaint, decision context, or packet" in blocker for blocker in blockers)

    snapshot = dict(workflow.reproduction_snapshot)
    snapshot["decision_context"] = {
        **snapshot["decision_context"],
        "priority": "exit-drive",
    }
    context_tamper = workflow.model_copy(update={"reproduction_snapshot": snapshot})
    packet, blockers = service.revalidate_controlled_workflow_packet(
        context_tamper,
        repository=_WorkflowRepo(context_tamper),
    )
    assert packet is None
    assert any("complaint, decision context, or packet" in blocker for blocker in blockers)


def test_missing_plan_or_stage_binding_is_non_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _packet()
    missing_plan = _workflow(packet)
    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: packet)

    rebuilt, blockers = service.revalidate_controlled_workflow_packet(
        missing_plan,
        repository=SimpleNamespace(),
    )
    assert rebuilt is None
    assert any("plan binding is unavailable" in blocker for blocker in blockers)

    missing_stage = _with_plan_binding(_workflow(packet, status="a_recorded")).model_copy(update={
        "stage_run_ids": {"A": "run-a"},
        "stage_eligible_lap_numbers": {"A": (3, 4, 5)},
    })
    projection = service.project_workflow_for_publication(
        missing_stage,
        repository=SimpleNamespace(),
    )
    assert projection.workflow_id == missing_stage.workflow_id
    assert projection.status == "a_recorded"
    assert projection.packet.decision == "measure"
    assert projection.packet.primary_test is None


def test_same_representative_lap_in_different_windows_has_a_distinct_plan_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _packet()

    class CreateRepo:
        db_path = None

        def list_controlled_workflows(self, *, active_only: bool = False):
            assert active_only is True
            return []

        def save_controlled_workflow(self, _workflow: ControlledWorkflow) -> None:
            pass

    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: packet)
    repository = CreateRepo()
    first = service.create_workflow(
        "source",
        "tight entry",
        selected_lap=5,
        lap_scope="lap_window",
        window_start_lap=3,
        window_end_lap=7,
        representative_lap=5,
        repository=repository,
    )
    second = service.create_workflow(
        "source",
        "tight entry",
        selected_lap=5,
        lap_scope="lap_window",
        window_start_lap=4,
        window_end_lap=8,
        representative_lap=5,
        repository=repository,
    )

    first_context = first.reproduction_snapshot["decision_context"]
    second_context = second.reproduction_snapshot["decision_context"]
    assert first_context["window_start_lap"] == 3
    assert first_context["window_end_lap"] == 7
    assert first_context["representative_lap"] == 5
    assert second_context["window_start_lap"] == 4
    assert second_context["window_end_lap"] == 8
    assert (
        first.reproduction_snapshot["plan_binding_sha256"]
        != second.reproduction_snapshot["plan_binding_sha256"]
    )

    swapped_snapshot = dict(first.reproduction_snapshot)
    swapped_snapshot["decision_context"] = second_context
    swapped = first.model_copy(update={"reproduction_snapshot": swapped_snapshot})
    rebuilt, blockers = service.revalidate_controlled_workflow_packet(
        swapped,
        repository=repository,
    )
    assert rebuilt is None
    assert any("plan binding" in blocker for blocker in blockers)


def test_measurement_and_test_share_one_active_session_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    measurement = _workflow(service._blocked_workflow_packet())

    class Repo(_WorkflowRepo):
        def save_controlled_workflow(self, _workflow: ControlledWorkflow) -> None:
            raise AssertionError("A second active workflow must not be saved.")

    monkeypatch.setattr(
        service,
        "build_server_kaizen_packet",
        lambda *_args, **_kwargs: pytest.fail("The active-slot gate must run before planning."),
    )

    with pytest.raises(ValueError, match="active controlled workflow"):
        service.create_workflow(
            "source",
            "loose exit",
            repository=Repo(measurement),
        )


def test_repository_atomically_reserves_one_active_slot_for_any_decision(tmp_path) -> None:
    repository = RaceLabRepository(tmp_path / "workflow-slot.sqlite")
    repository.save_import(_overview("source", 10))
    measurement = _workflow(service._blocked_workflow_packet())
    repository.create_controlled_workflow_if_scope_available(measurement, ("source",))
    competing_test = _workflow(_packet()).model_copy(update={
        "workflow_id": "aba-competing-test",
    })

    with pytest.raises(ValueError, match="active controlled workflow"):
        repository.create_controlled_workflow_if_scope_available(
            competing_test,
            ("source",),
        )

    assert repository.get_controlled_workflow(measurement.workflow_id) == measurement
    assert repository.get_controlled_workflow(competing_test.workflow_id) is None


def test_repository_atomically_rechecks_a_new_stage_scope_before_save(tmp_path) -> None:
    repository = RaceLabRepository(tmp_path / "workflow-stage-slot.sqlite")
    for run_id, hour in (("source-one", 10), ("source-two", 11), ("shared-stage", 13)):
        repository.save_import(_overview(run_id, hour))
    first = _workflow(_packet()).model_copy(update={
        "workflow_id": "aba-first",
        "source_run_id": "source-one",
    })
    second = _workflow(service._blocked_workflow_packet()).model_copy(update={
        "workflow_id": "aba-second",
        "source_run_id": "source-two",
    })
    repository.save_controlled_workflow(first)
    repository.save_controlled_workflow(second)
    first_attached = first.model_copy(update={
        "status": "a_recorded",
        "stage_run_ids": {"A": "shared-stage"},
        "stage_eligible_lap_numbers": {"A": (3, 4, 5)},
    })
    second_attached = second.model_copy(update={
        "status": "a_recorded",
        "stage_run_ids": {"A": "shared-stage"},
        "stage_eligible_lap_numbers": {"A": (3, 4, 5)},
    })

    repository.save_controlled_workflow_if_scope_exclusive(
        first_attached,
        ("source-one", "shared-stage"),
    )
    with pytest.raises(ValueError, match="aba-first"):
        repository.save_controlled_workflow_if_scope_exclusive(
            second_attached,
            ("source-two", "shared-stage"),
        )

    assert repository.get_controlled_workflow(first.workflow_id) == first_attached
    assert repository.get_controlled_workflow(second.workflow_id) == second


def test_attach_and_score_recheck_for_a_competing_active_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _packet()
    competing = _workflow(service._blocked_workflow_packet()).model_copy(update={
        "workflow_id": "aba-competing-measurement",
    })
    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: canonical)

    attach_workflow = _with_plan_binding(_workflow(canonical))
    with pytest.raises(ValueError, match="aba-competing-measurement"):
        service.attach_stage(
            attach_workflow.workflow_id,
            "A",
            "source",
            repository=_WorkflowRepo(attach_workflow, (competing,)),
        )

    score_workflow = _with_plan_binding(_workflow(canonical, status="a2_recorded")).model_copy(update={
        "stage_run_ids": {"A": "run-a", "B": "run-b", "A2": "run-a2"},
        "stage_eligible_lap_numbers": {
            "A": (3, 4, 5),
            "B": (3, 4, 5),
            "A2": (3, 4, 5),
        },
    })
    with pytest.raises(ValueError, match="aba-competing-measurement"):
        service.score_workflow(
            score_workflow.workflow_id,
            repository=_WorkflowRepo(score_workflow, (competing,)),
        )


def _overview(run_id: str, hour: int) -> RunOverview:
    return RunOverview(
        run_id=run_id,
        session=SessionSummary(
            run_id=run_id,
            sim_date_time=f"2026-08-04T{hour:02d}:00:00+00:00",
            setup_passed_tech=True,
        ),
        laps=[
            LapSummary(
                lap_id=f"{run_id}:{number}",
                run_id=run_id,
                lap_number=number,
                lap_type="flying",
                is_complete=True,
                is_useful=True,
                lap_time=30.0 + number,
            )
            for number in range(1, 6)
        ],
    )


def test_publication_blocks_tampered_active_stage_and_attach_cannot_extend_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _packet()
    workflow = _with_plan_binding(_workflow(packet, status="a_recorded")).model_copy(update={
        "stage_run_ids": {"A": "run-a"},
        "stage_eligible_lap_numbers": {"A": (3, 4, 5)},
        # A valid attachment always records source/A chronology. Its absence
        # models a structurally valid stage row swapped into this workflow.
    })

    class StageRepo(_WorkflowRepo):
        def __init__(self):
            super().__init__(workflow)
            self.overviews = {
                "source": _overview("source", 10),
                "run-a": _overview("run-a", 11),
            }
            self.setups = {
                run_id: SetupSnapshot(
                    setup_id=f"setup-{run_id}",
                    run_id=run_id,
                    cross_weight_percent=50.0,
                )
                for run_id in self.overviews
            }
            self.saved = False

        def get_overview(self, run_id: str):
            return self.overviews.get(run_id)

        def get_setup_snapshot(self, run_id: str):
            return self.setups.get(run_id)

        def save_controlled_workflow(self, _workflow: ControlledWorkflow) -> None:
            self.saved = True

    identity = {
        "driver_user_id": "driver",
        "car_id": "car",
        "car_path": "car/path",
        "car_version": "1",
        "track_id": "track",
        "track_configuration_name": "oval",
        "track_version": "1",
        "iracing_build_version": "build",
        "session_type": "test",
    }
    manifest = {
        "compatibility_identity": identity,
        "recording_session_time_bounds_s": {"start": 0.0, "end": 100.0},
    }
    repository = StageRepo()
    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: packet)
    monkeypatch.setattr(service, "read_telemetry_manifest", lambda _run_id: manifest)
    monkeypatch.setattr(service, "setup_controls_comparable", lambda *_args: True)
    monkeypatch.setattr(service, "unmapped_setup_change_paths", lambda *_args: [])
    monkeypatch.setattr(service, "diff_setups", lambda *_args: [])
    monkeypatch.setattr(
        service,
        "_lap_rows",
        lambda _run_id, numbers: {number: [{"lap": number}] for number in numbers},
    )
    monkeypatch.setattr(service, "_continuous_stage_cohort", lambda *_args: (True, None))

    projection = service.project_workflow_for_publication(workflow, repository=repository)
    assert projection.workflow_id == workflow.workflow_id
    assert projection.source_run_id == workflow.source_run_id
    assert projection.status == "a_recorded"
    assert projection.packet.decision == "measure"
    assert projection.packet.primary_test is None

    with pytest.raises(ValueError, match="immutable stage binding"):
        service.attach_stage(
            workflow.workflow_id,
            "B",
            "run-b",
            repository=repository,
        )
    assert repository.saved is False


def test_report_rejects_a_cherry_picked_or_corrupted_stage_cohort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _packet()
    workflow = _with_plan_binding(_workflow(packet, status="a2_recorded")).model_copy(update={
        "stage_run_ids": {"A": "run-a", "B": "run-b", "A2": "run-a2"},
        "stage_eligible_lap_numbers": {
            "A": (3, 4, 5),
            "B": (2, 4, 5),
            "A2": (3, 4, 5),
        },
    })
    workflow.reproduction_snapshot["stage_binding_sha256"] = service._stage_binding_hash(
        workflow.stage_run_ids,
        workflow.stage_eligible_lap_numbers,
        {},
    )

    class EvidenceRepo(_WorkflowRepo):
        def __init__(self):
            super().__init__(workflow)
            self.overviews = {
                run_id: _overview(run_id, hour)
                for run_id, hour in (
                    ("source", 10),
                    ("run-a", 11),
                    ("run-b", 13),
                    ("run-a2", 14),
                )
            }
            self.setups = {
                "source": SetupSnapshot(
                    setup_id="setup-source",
                    run_id="source",
                    cross_weight_percent=50.0,
                ),
                "run-a": SetupSnapshot(
                    setup_id="setup-a",
                    run_id="run-a",
                    cross_weight_percent=50.0,
                ),
                "run-b": SetupSnapshot(
                    setup_id="setup-b",
                    run_id="run-b",
                    cross_weight_percent=50.5,
                ),
                "run-a2": SetupSnapshot(
                    setup_id="setup-a2",
                    run_id="run-a2",
                    cross_weight_percent=50.0,
                ),
            }

        def get_overview(self, run_id: str):
            return self.overviews.get(run_id)

        def get_setup_snapshot(self, run_id: str):
            return self.setups.get(run_id)

    identity = {
        "driver_user_id": "driver",
        "car_id": "car",
        "car_path": "car/path",
        "car_version": "1",
        "track_id": "track",
        "track_configuration_name": "oval",
        "track_version": "1",
        "iracing_build_version": "build",
        "session_type": "test",
    }
    manifest = {
        "compatibility_identity": identity,
        "recording_session_time_bounds_s": {"start": 0.0, "end": 100.0},
    }
    monkeypatch.setattr(service, "build_server_kaizen_packet", lambda *_args, **_kwargs: packet)
    monkeypatch.setattr(service, "read_telemetry_manifest", lambda _run_id: manifest)
    monkeypatch.setattr(service, "setup_controls_comparable", lambda _left, _right: True)
    monkeypatch.setattr(service, "unmapped_setup_change_paths", lambda *_args: [])
    monkeypatch.setattr(
        service,
        "diff_setups",
        lambda left, right: (
            []
            if left.cross_weight_percent == right.cross_weight_percent
            else [SimpleNamespace(setup_key="cross_weight_percent")]
        ),
    )
    monkeypatch.setattr(
        service,
        "_lap_rows",
        lambda _run_id, numbers: {number: [{"lap": number}] for number in numbers},
    )
    monkeypatch.setattr(service, "_continuous_stage_cohort", lambda *_args: (True, None))
    monkeypatch.setattr(
        "racelab_engine.services.report_service.read_telemetry_manifest",
        lambda _run_id: manifest,
    )
    report = ReportService()
    report.repository = EvidenceRepo()

    with pytest.raises(ValueError, match="cherry-picked"):
        report.generate_workflow_markdown(workflow.workflow_id)


def test_report_api_returns_a_blocked_conflict_instead_of_a_certificate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BlockedReportService:
        def generate_workflow_markdown(self, _workflow_id: str):
            raise ValueError("The scored certificate stage bindings failed integrity validation.")

    monkeypatch.setattr("api.routes_engineering.ReportService", BlockedReportService)
    response = TestClient(app).get("/api/engineering/workflows/aba-corrupt/report")

    assert response.status_code == 409
    assert "certificate stage bindings" in response.json()["detail"]
