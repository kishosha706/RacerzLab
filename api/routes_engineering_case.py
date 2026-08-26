from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path as ApiPath, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from racelab_engine.models.crew_chief import EngineeringObjective
from racelab_engine.models.engineering_case import (
    DriverIntent,
    EngineeringCaseDeliveryDiagnostics,
    EngineeringCaseRevision,
    EngineeringCaseRevisionSummary,
)
from racelab_engine.models.controlled_workflow import ControlledWorkflow
from racelab_engine.identity import canonical_json_sha256
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
from racelab_engine.storage.controlled_workflow_mutation_repository import (
    ControlledWorkflowMutationIntegrityError,
    ControlledWorkflowMutationReceipt,
    ControlledWorkflowMutationRepository,
)
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository
from api.routes_engineering import (
    WorkflowStartRequest,
    _controlled_workflow_revision_sha256,
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

    schema_version: Literal[
        "p3544.atomic-driver-intent-workflow.v2"
    ] = "p3544.atomic-driver-intent-workflow.v2"
    mutation_id: str = Field(pattern=r"^cwm_[0-9a-f]{24}$")
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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
    workflow_revision_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    withholding_reason: str | None = None

    @model_validator(mode="after")
    def exact_successor_is_complete(self) -> AtomicDriverIntentWorkflowResponse:
        if (
            self.case_revision.previous_case_sha256
            != self.expected_case_sha256
            or (self.workflow is None)
            != (self.workflow_revision_sha256 is None)
        ):
            raise ValueError(
                "Atomic DriverIntent response is not the complete exact-case successor."
            )
        if self.workflow is not None and (
            self.case_revision.case.active_workflow_id
            != self.workflow.workflow_id
            or self.case_revision.case.active_workflow_revision
            != self.workflow_revision_sha256
        ):
            raise ValueError(
                "Atomic DriverIntent response workflow does not match the successor case."
            )
        return self


def _http_error(exc: Exception) -> HTTPException:
    detail = str(exc)
    status = 409 if any(
        value in detail.casefold()
        for value in ("stale", "revision", "corrupt", "another")
    ) else 422
    return HTTPException(status_code=status, detail=detail)


def _persisted_current_workspace(
    *,
    run_id: str,
    session_id: str,
    expected_case_sha256: str,
    db_path: str | Path | None = None,
):
    case_repository = EngineeringCaseRepository(db_path)
    persisted = case_repository.current_for_scope(run_id, session_id)
    if persisted is None:
        raise ValueError("Open the current Engineering Case before changing it.")
    if persisted.case_sha256 != expected_case_sha256:
        raise ValueError(
            "Engineering Case mutation is stale for the persisted current revision."
        )
    try:
        current_objective = EngineeringObjective(persisted.case.objective_id)
    except ValueError as exc:
        raise EngineeringCaseIntegrityError(
            "Persisted Engineering Case objective is not supported."
        ) from exc
    workspace = build_crew_chief_workspace(
        run_id,
        session_id=session_id,
        objective=current_objective,
        db_path=db_path,
    )
    if workspace.engineering_case.case_sha256 != expected_case_sha256:
        raise ValueError(
            "Engineering Case changed at its canonical sources; refresh before mutating it."
        )
    return workspace


def _assert_expected_case_in_transaction(
    repository: EngineeringCaseRepository,
    connection,
    *,
    run_id: str,
    session_id: str,
    expected_case_sha256: str,
) -> EngineeringCaseRevision:
    current = repository.current_for_scope_in_transaction(
        connection, run_id, session_id
    )
    if current is None or current.case_sha256 != expected_case_sha256:
        raise ValueError(
            "Engineering Case mutation is stale for the persisted current revision."
        )
    return current


def _preview_database(connection, directory: str) -> Path:
    """Materialize this transaction for canonical reads before it commits."""

    preview_path = Path(directory) / "engineering-case-preview.sqlite"
    preview_path.write_bytes(connection.serialize())
    return preview_path


def _atomic_workflow_mutation_identity(
    run_id: str,
    request: AtomicDriverIntentWorkflowRequest,
) -> tuple[str, str]:
    request_sha256 = canonical_json_sha256(
        {
            "schema": "p3544.atomic-driver-intent-workflow-request.v2",
            "action": "start",
            "route_run_id": run_id,
            "request": request.model_dump(mode="json"),
        }
    )
    return f"cwm_{request_sha256[:24]}", request_sha256


def _atomic_workflow_receipt_expectation(
    *,
    run_id: str,
    request: AtomicDriverIntentWorkflowRequest,
    request_sha256: str,
) -> dict[str, object]:
    return {
        "request_sha256": request_sha256,
        "action": "start",
        "run_id": run_id,
        "session_id": request.session_id,
        "request_workflow_id": None,
        "expected_case_sha256": request.expected_case_sha256,
    }


def _atomic_response_from_receipt(
    receipt: ControlledWorkflowMutationReceipt,
) -> AtomicDriverIntentWorkflowResponse:
    try:
        response = AtomicDriverIntentWorkflowResponse.model_validate(
            receipt.response_payload
        )
    except (TypeError, ValueError) as exc:
        raise ControlledWorkflowMutationIntegrityError(
            "Atomic DriverIntent mutation receipt response contract is corrupt."
        ) from exc
    workflow_id = (
        response.workflow.workflow_id if response.workflow is not None else None
    )
    if (
        response.mutation_id != receipt.mutation_id
        or response.request_sha256 != receipt.request_sha256
        or response.expected_case_sha256 != receipt.expected_case_sha256
        or response.case_revision.case_sha256 != receipt.result_case_sha256
        or response.case_revision.case.run_id != receipt.run_id
        or response.case_revision.case.session_id != receipt.session_id
        or workflow_id != receipt.result_workflow_id
        or response.workflow_revision_sha256
        != receipt.result_workflow_revision_sha256
    ):
        raise ControlledWorkflowMutationIntegrityError(
            "Atomic DriverIntent mutation receipt result identity is corrupt."
        )
    return response


def _recover_workflow_plan(
    response: AtomicDriverIntentWorkflowResponse,
    *,
    db_path: str | Path | None,
) -> None:
    if response.workflow is None:
        return
    persisted = RaceLabRepository(db_path).get_controlled_workflow(
        response.workflow.workflow_id
    )
    if persisted is None or (
        _controlled_workflow_revision_sha256(persisted)
        != response.workflow_revision_sha256
    ):
        raise ControlledWorkflowMutationIntegrityError(
            "Atomic DriverIntent receipt points to a missing workflow revision."
        )
    try:
        record_workflow_plan(persisted, db_path=db_path)
    except (OSError, ValueError):
        pass


@router.get(
    "/api/runs/{run_id}/engineering-case",
    response_model=EngineeringCaseRevision,
)
def get_current_engineering_case(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    session_id: Annotated[str, Query(min_length=1, max_length=160)],
    objective: EngineeringObjective | None = None,
    expected_case_sha256: Annotated[
        str | None, Query(pattern=r"^[0-9a-f]{64}$")
    ] = None,
) -> EngineeringCaseRevision:
    started = perf_counter()
    intelligence_before = run_intelligence_snapshot_stats()["build_count"]
    crew_before = crew_chief_workspace_stats()["build_count"]
    case_before = engineering_case_projection_stats()["build_count"]
    try:
        if objective is None:
            persisted = EngineeringCaseRepository().current_for_scope(
                run_id, session_id
            )
            objective = (
                EngineeringObjective.RACE_LONG_RUN
                if persisted is None
                else EngineeringObjective(persisted.case.objective_id)
            )
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
            response_bytes=None,
        )
        delivered = revision.model_copy(update={"delivery_diagnostics": diagnostics})
        for _ in range(3):
            response_bytes = len(delivered.model_dump_json().encode("utf-8"))
            if delivered.delivery_diagnostics is not None and (
                delivered.delivery_diagnostics.response_bytes == response_bytes
            ):
                break
            delivered = delivered.model_copy(
                update={
                    "delivery_diagnostics": diagnostics.model_copy(
                        update={"response_bytes": response_bytes}
                    )
                }
            )
        return delivered
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
        _persisted_current_workspace(
            run_id=run_id,
            session_id=request.session_id,
            expected_case_sha256=request.expected_case_sha256,
        )
        repository = EngineeringCaseRepository()
        case_id = engineering_case_id(run_id=run_id, session_id=request.session_id)
        connection = initialize_database(repository.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            _assert_expected_case_in_transaction(
                repository,
                connection,
                run_id=run_id,
                session_id=request.session_id,
                expected_case_sha256=request.expected_case_sha256,
            )
            repository.append_driver_intent_in_transaction(
                connection,
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
                typed_interpretation_provenance=(
                    request.typed_interpretation_provenance
                ),
            )
            with TemporaryDirectory(prefix="racelab-case-preview-") as directory:
                preview_path = _preview_database(connection, directory)
                rebuilt = build_crew_chief_workspace(
                    run_id,
                    session_id=request.session_id,
                    objective=request.objective,
                    db_path=preview_path,
                )
                if (
                    rebuilt.engineering_case.driver_intent is None
                    or rebuilt.engineering_case.driver_intent.raw_driver_wording
                    != request.raw_driver_wording
                ):
                    raise EngineeringCaseIntegrityError(
                        "DriverIntent was not atomically reflected in the rebuilt case."
                    )
                revision = repository.finalize_case_in_transaction(
                    connection,
                    rebuilt.engineering_case,
                    change_category="driver_intent",
                )
            connection.commit()
            return revision
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
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
    mutation_id, request_sha256 = _atomic_workflow_mutation_identity(
        run_id, request
    )
    expectation = _atomic_workflow_receipt_expectation(
        run_id=run_id,
        request=request,
        request_sha256=request_sha256,
    )
    receipt_repository = ControlledWorkflowMutationRepository(repository.db_path)
    case_repository = EngineeringCaseRepository(repository.db_path)
    objective = {
        "race-pace": EngineeringObjective.RACE_LONG_RUN,
        "long-run": EngineeringObjective.RACE_LONG_RUN,
        "qualifying": EngineeringObjective.QUALIFYING_PEAK,
        "tire-conservation": EngineeringObjective.TIRE_CONSERVATION,
        "driver-confidence": EngineeringObjective.DRIVER_CONFIDENCE,
    }[request.objective]
    try:
        receipt = receipt_repository.receipt(mutation_id, **expectation)
        if receipt is not None:
            response = _atomic_response_from_receipt(receipt)
            _recover_workflow_plan(response, db_path=repository.db_path)
            return response
        current_workspace = _persisted_current_workspace(
            run_id=run_id,
            session_id=request.session_id,
            expected_case_sha256=request.expected_case_sha256,
            db_path=repository.db_path,
        )
        target_workspace = (
            current_workspace
            if current_workspace.engineering_case.objective_id == objective.value
            else build_crew_chief_workspace(
                run_id,
                session_id=request.session_id,
                objective=objective,
                db_path=repository.db_path,
            )
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
            engineering_knowledge=target_workspace.engineering_knowledge,
            p19_terminal_decision=target_workspace.terminal_decision,
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

        published_workflow: ControlledWorkflow | None = None
        connection = initialize_database(repository.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            receipt = ControlledWorkflowMutationRepository.receipt_in_transaction(
                connection, mutation_id, **expectation
            )
            if receipt is not None:
                response = _atomic_response_from_receipt(receipt)
                connection.rollback()
            else:
                _assert_expected_case_in_transaction(
                    case_repository,
                    connection,
                    run_id=run_id,
                    session_id=request.session_id,
                    expected_case_sha256=request.expected_case_sha256,
                )
                intent = case_repository.append_driver_intent_in_transaction(
                    connection,
                    case_id=target_workspace.engineering_case.case_id,
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
                with TemporaryDirectory(prefix="racelab-case-preview-") as directory:
                    preview_path = _preview_database(connection, directory)
                    rebuilt = build_crew_chief_workspace(
                        run_id,
                        session_id=request.session_id,
                        objective=objective,
                        db_path=preview_path,
                    )
                    if (
                        rebuilt.engineering_case.driver_intent is None
                        or rebuilt.engineering_case.driver_intent.intent_sha256
                        != intent.intent_sha256
                    ):
                        raise EngineeringCaseIntegrityError(
                            "DriverIntent was not atomically reflected in the rebuilt case."
                        )
                    if candidate is not None:
                        published_workflow = project_workflow_for_publication(
                            candidate,
                            repository=RaceLabRepository(preview_path),
                        )
                    revision = case_repository.finalize_case_in_transaction(
                        connection,
                        rebuilt.engineering_case,
                        change_category=(
                            "workflow" if candidate is not None else "driver_intent"
                        ),
                    )
                state = (
                    "workflow_created"
                    if candidate is not None
                    else "measurement_required"
                    if rebuilt.terminal_decision.kind == "measurement_mission"
                    else "insufficient_evidence"
                )
                workflow_revision_sha256 = (
                    _controlled_workflow_revision_sha256(candidate)
                    if candidate is not None
                    else None
                )
                response = AtomicDriverIntentWorkflowResponse(
                    mutation_id=mutation_id,
                    request_sha256=request_sha256,
                    expected_case_sha256=request.expected_case_sha256,
                    state=state,
                    case_revision=revision,
                    driver_intent=intent,
                    advisory=advisory,
                    workflow=published_workflow,
                    workflow_revision_sha256=workflow_revision_sha256,
                    withholding_reason=withholding_reason,
                )
                ControlledWorkflowMutationRepository.save_receipt_in_transaction(
                    connection,
                    mutation_id=mutation_id,
                    **expectation,
                    result_case_sha256=revision.case_sha256,
                    result_workflow_id=(
                        candidate.workflow_id if candidate is not None else None
                    ),
                    result_workflow_revision_sha256=workflow_revision_sha256,
                    response_payload=response.model_dump(mode="json"),
                )
                connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        _recover_workflow_plan(response, db_path=repository.db_path)
        return response
    except (EngineeringCaseIntegrityError, ValueError) as exc:
        raise _http_error(exc) from exc


__all__ = ["router"]
