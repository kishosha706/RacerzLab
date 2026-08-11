from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.services import controlled_workflow_service as service
from racelab_engine.services.report_service import ReportService
from racelab_engine.services.session_intelligence_service import (
    build_hypothesis_lifecycle,
    controlled_hypothesis_policy_identity,
)
from racelab_engine.services.session_service import add_run_to_session, create_session
from racelab_engine.storage.repository import RaceLabRepository
from test_session_intelligence_service import IDENTITY, _lifecycle_fixture, _setup


def _undo_fixture(tmp_path, monkeypatch: pytest.MonkeyPatch):
    db_path, data_dir, _session_id, failed = _lifecycle_fixture(tmp_path, "undo")
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))
    return RaceLabRepository(db_path), failed


def _planned_candidate(failed: ControlledWorkflow) -> ControlledWorkflow:
    now = datetime.now(timezone.utc)
    decision_context = dict(failed.reproduction_snapshot["decision_context"])
    candidate = ControlledWorkflow(
        workflow_id="repeat-policy-candidate",
        created_at=now,
        updated_at=now,
        status="planned",
        source_run_id=failed.source_run_id,
        complaint=failed.complaint,
        packet=failed.packet,
        reproduction_snapshot={"decision_context": decision_context},
    )
    candidate.reproduction_snapshot["plan_binding_sha256"] = service._workflow_plan_binding_hash(
        candidate,
        candidate.packet,
        decision_context,
    )
    return candidate


def _assert_exact_target_withheld(packet, exact_change: str) -> None:
    assert packet.decision == "measure"
    assert packet.primary_test is None
    assert packet.measurement_mission is not None
    assert any(
        "No setup change is authorized" in variable
        for variable in packet.measurement_mission.controlled_variables
    )
    assert exact_change not in packet.model_dump_json()


def test_create_never_persists_or_returns_an_exact_do_not_repeat_target(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, failed = _undo_fixture(tmp_path, monkeypatch)
    card = failed.packet.primary_test
    assert card is not None
    monkeypatch.setattr(
        service,
        "build_server_kaizen_packet",
        lambda *_args, **_kwargs: failed.packet,
    )

    created = service.create_workflow(
        failed.source_run_id,
        failed.complaint,
        repository=repository,
    )

    _assert_exact_target_withheld(created.packet, card.exact_change)
    assert any("do-not-repeat" in reason for reason in created.packet.blockers)
    stored = repository.get_controlled_workflow(created.workflow_id)
    assert stored is None


def test_publication_redacts_and_attachment_rejects_a_legacy_exact_repeat(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, failed = _undo_fixture(tmp_path, monkeypatch)
    candidate = _planned_candidate(failed)
    card = candidate.packet.primary_test
    assert card is not None
    repository.save_controlled_workflow(candidate)
    monkeypatch.setattr(
        service,
        "revalidate_controlled_workflow_packet",
        lambda current, **_kwargs: (current.packet, ()),
    )

    public = service.project_workflow_for_publication(candidate, repository=repository)

    assert public.workflow_id == candidate.workflow_id
    assert public.status == "planned"
    _assert_exact_target_withheld(public.packet, card.exact_change)
    assert public.reproduction_snapshot == {}
    with pytest.raises(ValueError, match="P19 authority origin"):
        service.attach_stage(
            candidate.workflow_id,
            "A",
            candidate.source_run_id,
            repository=repository,
        )
    with pytest.raises(ValueError, match="P19 authority origin"):
        service.validate_workflow_for_authoritative_use(
            candidate,
            repository=repository,
        )
    unchanged = repository.get_controlled_workflow(candidate.workflow_id)
    assert unchanged is not None
    assert unchanged.status == "planned"
    assert unchanged.stage_run_ids == {}

    cancelled = service.cancel_workflow(candidate.workflow_id, repository=repository)
    assert cancelled.status == "cancelled"
    cancelled_public = service.project_workflow_for_publication(
        cancelled,
        repository=repository,
    )
    assert cancelled_public.status == "cancelled"
    _assert_exact_target_withheld(cancelled_public.packet, card.exact_change)


@pytest.mark.parametrize(
    "endpoint",
    ("/api/engineering/test-director/plan", "/api/engineering/crew-chief/packet"),
)
def test_legacy_engineering_packet_endpoints_are_removed(
    endpoint: str,
) -> None:
    assert endpoint not in app.openapi()["paths"]
    assert TestClient(app).post(endpoint, json={}).status_code == 404


def test_ambiguous_session_scope_fails_closed_without_exposing_the_target(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, failed = _undo_fixture(tmp_path, monkeypatch)
    second = create_session("ambiguous-repeat-scope", db_path=repository.db_path)
    assert add_run_to_session(
        second.session_id,
        failed.source_run_id,
        db_path=repository.db_path,
    ) is not None
    card = failed.packet.primary_test
    assert card is not None

    candidate = _planned_candidate(failed)
    authorized, blockers = service.enforce_hypothesis_repeat_policy(
        candidate,
        repository=repository,
    )
    assert authorized is None
    packet = service.withhold_workflow_authority(candidate, *blockers).packet

    _assert_exact_target_withheld(packet, card.exact_change)
    assert any("could not be verified" in reason for reason in packet.blockers)


def test_a_material_policy_change_remains_eligible_for_a_new_controlled_test(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, failed = _undo_fixture(tmp_path, monkeypatch)
    changed = failed.packet.model_copy(update={"canonical_symptom": "tight_center"})

    candidate = _planned_candidate(failed).model_copy(update={"packet": changed})
    packet, blockers = service.enforce_hypothesis_repeat_policy(
        candidate,
        repository=repository,
    )

    assert blockers == ()
    assert packet == changed
    assert packet.decision == "test"
    assert packet.primary_test is not None


def test_central_gate_allows_the_same_control_for_a_different_physical_window(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, failed = _undo_fixture(tmp_path, monkeypatch)
    changed_opportunity = failed.packet.opportunity.model_copy(
        update={"start_pct": 70.0, "end_pct": 80.0},
    )
    changed_packet = failed.packet.model_copy(
        update={"opportunity": changed_opportunity},
    )
    candidate = _planned_candidate(failed).model_copy(
        update={"packet": changed_packet},
    )

    authorized, blockers = service.enforce_hypothesis_repeat_policy(
        candidate,
        repository=repository,
    )

    assert blockers == ()
    assert authorized == changed_packet


@pytest.mark.parametrize(
    "endpoint",
    ("/api/engineering/test-director/plan", "/api/engineering/crew-chief/packet"),
)
def test_removed_direct_packet_endpoints_cannot_publish_a_physical_window(
    endpoint: str,
) -> None:
    response = TestClient(app).post(
        endpoint,
        json={
            "run_id": "run-legacy-preview",
            "complaint": "tight on exit",
            "lap_scope": "track_zone",
            "selected_zone_start_pct": 70.0,
            "selected_zone_end_pct": 80.0,
            "selected_zone_label": "Turn 4 exit",
        },
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "endpoint",
    ("/api/engineering/workflows",),
)
def test_track_zone_requests_fail_closed_without_an_exact_physical_window(
    endpoint: str,
) -> None:
    response = TestClient(app).post(
        endpoint,
        json={
            "run_id": "run-with-missing-zone",
            "session_id": "session-with-missing-zone",
            "complaint": "tight on exit",
            "lap_scope": "track_zone",
        },
    )

    assert response.status_code == 422
    assert "exact physical window" in response.text


def test_central_gate_fails_closed_without_a_nonzero_physical_window(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, failed = _undo_fixture(tmp_path, monkeypatch)
    invalid_packet = failed.packet.model_copy(
        update={
            "opportunity": failed.packet.opportunity.model_copy(
                update={"end_pct": failed.packet.opportunity.start_pct},
            )
        },
    )
    candidate = _planned_candidate(failed).model_copy(
        update={"packet": invalid_packet},
    )

    authorized, blockers = service.enforce_hypothesis_repeat_policy(
        candidate,
        repository=repository,
    )

    assert authorized is None
    assert any("could not be verified" in reason for reason in blockers)


def test_central_gate_blocks_compatibility_and_setup_representation_churn(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, data_dir, session_id, failed = _lifecycle_fixture(tmp_path, "undo")
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))
    lifecycle = build_hypothesis_lifecycle(
        session_id,
        db_path=db_path,
        data_dir=data_dir,
    )
    integer_setup = _setup(failed.source_run_id).model_copy(update={
        "cross_weight_percent": None,
        "setup_json": {"Chassis": {"Front": {"CrossWeight": 50}}},
        "extracted_values": {},
    })
    float_setup = _setup(failed.source_run_id).model_copy(update={
        "cross_weight_percent": None,
        "setup_json": {},
        "extracted_values": {"crossweight": 50.0},
    })
    prior_policy = controlled_hypothesis_policy_identity(
        failed,
        IDENTITY,
        source_setup=integer_setup,
    )
    prior_entry = lifecycle.entries[0].model_copy(
        update={"hypothesis_policy": prior_policy},
    )
    frozen_lifecycle = lifecycle.model_copy(update={
        "entries": (prior_entry,),
        "do_not_repeat_hypothesis_policy_keys": (prior_policy.policy_key,),
    })

    class RepresentationChurnRepository(RaceLabRepository):
        def get_setup_snapshot(self, run_id: str):
            if run_id == failed.source_run_id:
                return float_setup
            return super().get_setup_snapshot(run_id)

    repository = RepresentationChurnRepository(db_path)
    compatibility_churn = {
        key: f"  {value.upper()}  " if isinstance(value, str) else value
        for key, value in IDENTITY.items()
    }
    monkeypatch.setattr(
        service,
        "build_hypothesis_lifecycle",
        lambda *_args, **_kwargs: frozen_lifecycle,
    )
    monkeypatch.setattr(
        service,
        "read_telemetry_manifest",
        lambda _run_id: {"compatibility_identity": compatibility_churn},
    )

    authorized, blockers = service.enforce_hypothesis_repeat_policy(
        _planned_candidate(failed),
        repository=repository,
    )

    assert authorized is None
    assert any("do-not-repeat" in reason for reason in blockers)


def test_legacy_unbound_scored_undo_cannot_publish_or_generate_a_report(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, scored_undo = _undo_fixture(tmp_path, monkeypatch)
    card = scored_undo.packet.primary_test
    assert card is not None
    integrity_checks: list[tuple[str, bool]] = []

    def revalidate(current: ControlledWorkflow, **_kwargs):
        return current.packet, ()

    def verify_integrity(
        current: ControlledWorkflow,
        packet,
        _repository,
        *,
        require_complete: bool,
    ) -> None:
        integrity_checks.append((current.workflow_id, require_complete))
        assert packet == current.packet
        if current.status == "scored":
            assert current.execution is not None
            assert current.quality is not None
            assert set(current.stage_run_ids) == {"A", "B", "A2"}
            assert current.quality == service.score_test_execution(current.execution)

    monkeypatch.setattr(service, "revalidate_controlled_workflow_packet", revalidate)
    monkeypatch.setattr(service, "_validate_recorded_stage_bindings", verify_integrity)

    public_history = service.project_workflow_for_publication(
        scored_undo,
        repository=repository,
    )
    with pytest.raises(ValueError, match="P19 authority origin"):
        ReportService(repository.db_path).generate_workflow_markdown(
            scored_undo.workflow_id,
        )

    assert public_history.status == "scored"
    _assert_exact_target_withheld(public_history.packet, card.exact_change)
    assert public_history.quality is None
    assert public_history.reproduction_snapshot == {}
    assert integrity_checks == []

    future = _planned_candidate(scored_undo)
    public_future = service.project_workflow_for_publication(
        future,
        repository=repository,
    )
    _assert_exact_target_withheld(public_future.packet, card.exact_change)
    with pytest.raises(ValueError, match="P19 authority origin"):
        service.validate_workflow_for_authoritative_use(
            future,
            repository=repository,
        )
