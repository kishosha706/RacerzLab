from __future__ import annotations

from typing import Annotated, Literal
from time import perf_counter

from fastapi import APIRouter, HTTPException, Path as ApiPath, Query
from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.models.crew_chief import EngineeringObjective
from racelab_engine.models.engineering_case import (
    DriverIntent,
    EngineeringCaseDeliveryDiagnostics,
    EngineeringCaseRevision,
    EngineeringCaseRevisionSummary,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.knowledge.setup.dial_in_schema import DialInHypothesisResponse
from racelab_engine.knowledge.setup.dial_in_service import build_dial_in_response
from racelab_engine.services.controlled_workflow_service import (
    persist_workflow_candidate,
    project_workflow_for_publication,
)
from racelab_engine.services.engineering_memory_service import record_workflow_plan
from racelab_engine.services.crew_chief_service import (
    build_crew_chief_workspace,
    crew_chief_workspace_stats,
)
from racelab_engine.services.engineering_case_service import (
    engineering_case_id,
    engineering_case_projection_stats,
)
from racelab_engine.services.run_intelligence_service import (
    run_intelligence_snapshot_stats,
)
from racelab_engine.storage.engineering_case_repository import (
    EngineeringCaseIntegrityError,
    EngineeringCaseRepository,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository
from api.routes_engineering import (
    WorkflowStartRequest,
    build_authorized_workflow_candidate,
)


router = APIRouter(tags=["engineering-case"])


class DriverIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: str = Field(min_length=1, max_length=160)
    expected_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_driver_wording: str = Field(min_length=1, max_length=2000)
    canonical_symptom: str | None = Field(
        default=None, pattern=r"^[a-z0-9][a-z0-9_.:-]*$"
    )
    phase_scope: str | None = Field(default=None, max_length=120)
    response_regime_scope: Literal[
        "transient", "steady_state", "migration", "unknown", "context_only"
    ] = "unknown"
    traffic_context: Literal["clear", "exposed", "unknown", "context_only"] = (
        "unknown"
    )
    stint_context: str | None = Field(default=None, max_length=200)
    power_state_context: str | None = Field(default=None, max_length=120)
    time_origin_scope: str | None = Field(default=None, max_length=120)
    driver_demand_scope: str | None = Field(default=None, max_length=200)
    objective: EngineeringObjective = EngineeringObjective.RACE_LONG_RUN
    source: Literal[
        "manual", "crew_question", "dial_in", "smart_engineer", "session_restore"
    ] = "manual"
    typed_interpretation_provenance: tuple[str, ...] = ()


class AtomicDriverIntentWorkflowRequest(WorkflowStartRequest):
    expected_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_run_id: str | None = Field(default=None, min_length=1, max_length=160)


class AtomicDriverIntentWorkflowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal[
        "workflow_created",
        "measurement_required",
        "blocked",
        "no_current_problem",
        "insufficient_evidence",
        "unsupported_context",
    ]
    case_revision: EngineeringCaseRevision
    driver_intent: DriverIntent
    advisory: DialInHypothesisResponse
    workflow: ControlledWorkflow | None = None
    withholding_reason: str | None = None


def _http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    status = 409 if any(
        value in detail.casefold()
        for value in ("stale", "revision", "corrupt", "another")
    ) else 422
    return HTTPException(status_code=status, detail=detail)


@router.get(
    "/api/runs/{run_id}/engineering-case",
    response_model=EngineeringCaseRevision,
)
def get_current_engineering_case(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    session_id: Annotated[str, Query(min_length=1, max_length=160)],
    objective: EngineeringObjective = EngineeringObjective.RACE_LONG_RUN,
    expected_case_sha256: Annotated[
        str | None, Query(pattern=r"^[0-9a-f]{64}$")
    ] = None,
) -> EngineeringCaseRevision:
    started = perf_counter()
    intelligence_before = run_intelligence_snapshot_stats()["build_count"]
    crew_before = crew_chief_workspace_stats()["build_count"]
    case_before = engineering_case_projection_stats()["build_count"]
    try:
        workspace = build_crew_chief_workspace(
            run_id, session_id=session_id, objective=objective
        )
        revision = EngineeringCaseRepository().finalize_case(
            workspace.engineering_case, change_category="rebuild"
        )
        if expected_case_sha256 is not None and (
            revision.case_sha256 != expected_case_sha256
        ):
            raise ValueError(
                "Engineering Case changed; refresh the exact current revision."
            )
        diagnostics = EngineeringCaseDeliveryDiagnostics(
            route_duration_ms=(perf_counter() - started) * 1000.0,
            run_intelligence_build_count_delta=(
                run_intelligence_snapshot_stats()["build_count"]
                - intelligence_before
            ),
            crew_workspace_build_count_delta=(
                crew_chief_workspace_stats()["build_count"] - crew_before
            ),
            case_projection_build_count_delta=(
                engineering_case_projection_stats()["build_count"] - case_before
            ),
            response_bytes=len(revision.model_dump_json().encode("utf-8")),
        )
        return revision.model_copy(update={"delivery_diagnostics": diagnostics})
    except (EngineeringCaseIntegrityError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.get(
    "/api/engineering-cases/{case_id}/revisions",
    response_model=list[EngineeringCaseRevisionSummary],
)
def list_engineering_case_revisions(
    case_id: Annotated[str, ApiPath(pattern=r"^p3543case_[0-9a-f]{24}$")],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[EngineeringCaseRevisionSummary]:
    try:
        return list(EngineeringCaseRepository().history(case_id, limit=limit))
    except EngineeringCaseIntegrityError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/runs/{run_id}/engineering-case/driver-intent",
    response_model=EngineeringCaseRevision,
)
def append_engineering_case_driver_intent(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: DriverIntentRequest,
) -> EngineeringCaseRevision:
    try:
        workspace = build_crew_chief_workspace(
            run_id, session_id=request.session_id, objective=request.objective
        )
        if workspace.engineering_case.case_sha256 != request.expected_case_sha256:
            raise ValueError(
                "DriverIntent request is stale for the current Engineering Case revision."
            )
        repository = EngineeringCaseRepository()
        repository.finalize_case(workspace.engineering_case, change_category="rebuild")
        case_id = engineering_case_id(run_id=run_id, session_id=request.session_id)
        repository.append_driver_intent(
            case_id=case_id,
            raw_driver_wording=request.raw_driver_wording,
            canonical_symptom=request.canonical_symptom,
            phase_scope=request.phase_scope,
            response_regime_scope=request.response_regime_scope,
            traffic_context=request.traffic_context,
            stint_context=request.stint_context,
            power_state_context=request.power_state_context,
            time_origin_scope=request.time_origin_scope,
            driver_demand_scope=request.driver_demand_scope,
            objective=request.objective.value,
            source=request.source,
            typed_interpretation_provenance=request.typed_interpretation_provenance,
        )
        rebuilt = build_crew_chief_workspace(
            run_id, session_id=request.session_id, objective=request.objective
        )
        if (
            rebuilt.engineering_case.driver_intent is None
            or rebuilt.engineering_case.driver_intent.raw_driver_wording
            != request.raw_driver_wording
        ):
            raise EngineeringCaseIntegrityError(
                "DriverIntent was not atomically reflected in the rebuilt case."
            )
        return repository.finalize_case(
            rebuilt.engineering_case, change_category="driver_intent"
        )
    except (EngineeringCaseIntegrityError, ValueError) as exc:
        raise _http_error(exc) from exc


@router.post(
    "/api/runs/{run_id}/engineering-case/driver-intent-workflow",
    response_model=AtomicDriverIntentWorkflowResponse,
)
def submit_atomic_driver_intent_workflow(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: AtomicDriverIntentWorkflowRequest,
) -> AtomicDriverIntentWorkflowResponse:
    if request.run_id != run_id:
        raise HTTPException(
            status_code=409,
            detail="DriverIntent workflow route and payload run identities disagree.",
        )
    repository = RaceLabRepository()
    case_repository = EngineeringCaseRepository(repository.db_path)
    objective = {
        "race-pace": EngineeringObjective.RACE_LONG_RUN,
        "long-run": EngineeringObjective.RACE_LONG_RUN,
        "qualifying": EngineeringObjective.QUALIFYING_PEAK,
        "tire-conservation": EngineeringObjective.TIRE_CONSERVATION,
        "driver-confidence": EngineeringObjective.DRIVER_CONFIDENCE,
    }[request.objective]
    try:
        current_workspace = build_crew_chief_workspace(
            run_id,
            session_id=request.session_id,
            objective=objective,
            db_path=repository.db_path,
        )
        if current_workspace.engineering_case.case_sha256 != request.expected_case_sha256:
            raise ValueError(
                "DriverIntent/workflow request is stale for the current Engineering Case revision."
            )
        case_repository.finalize_case(
            current_workspace.engineering_case, change_category="rebuild"
        )
        internal_advisory = build_dial_in_response(
            run_id,
            request.complaint,
            baseline_run_id=request.baseline_run_id,
            selected_lap=request.selected_lap,
            selected_zone_start_pct=request.selected_zone_start_pct,
            selected_zone_end_pct=request.selected_zone_end_pct,
            selected_phase=request.selected_phase,
            objective=request.objective,
            priority=request.priority,
            limit=92,
            include_debug_evidence=False,
            canonical_runtime_owned=True,
        )
        advisory = DialInHypothesisResponse.from_internal(
            internal_advisory,
            engineering_knowledge=current_workspace.engineering_knowledge,
            p19_terminal_decision=current_workspace.terminal_decision,
            limit=92,
        )
        candidate: ControlledWorkflow | None = None
        withholding_reason: str | None = None
        try:
            candidate = build_authorized_workflow_candidate(
                request, repository=repository
            )
        except ValueError as exc:
            withholding_reason = str(exc)

        connection = initialize_database(repository.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            intent = case_repository.append_driver_intent_in_transaction(
                connection,
                case_id=current_workspace.engineering_case.case_id,
                raw_driver_wording=request.complaint,
                canonical_symptom=internal_advisory.interpreted_symptom,
                phase_scope=request.selected_phase,
                response_regime_scope="unknown",
                traffic_context="unknown",
                objective=objective.value,
                source="dial_in",
                typed_interpretation_provenance=(
                    "p35.4.4.atomic-driver-intent-workflow",
                ),
            )
            if candidate is not None:
                persist_workflow_candidate(
                    candidate,
                    repository=repository,
                    connection=connection,
                    record_plan=False,
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        if candidate is not None:
            try:
                record_workflow_plan(candidate, db_path=repository.db_path)
            except (OSError, ValueError):
                # Narrative memory is derived and non-authoritative.  The exact
                # workflow and DriverIntent transaction has already committed.
                pass
        rebuilt = build_crew_chief_workspace(
            run_id,
            session_id=request.session_id,
            objective=objective,
            db_path=repository.db_path,
        )
        revision = case_repository.finalize_case(
            rebuilt.engineering_case,
            change_category="workflow" if candidate is not None else "driver_intent",
        )
        state = (
            "workflow_created"
            if candidate is not None
            else "measurement_required"
            if rebuilt.terminal_decision.kind == "measurement_mission"
            else "insufficient_evidence"
        )
        return AtomicDriverIntentWorkflowResponse(
            state=state,
            case_revision=revision,
            driver_intent=intent,
            advisory=advisory,
            workflow=(
                project_workflow_for_publication(candidate, repository=repository)
                if candidate is not None
                else None
            ),
            withholding_reason=withholding_reason,
        )
    except (EngineeringCaseIntegrityError, ValueError) as exc:
        raise _http_error(exc) from exc


__all__ = ["router"]
