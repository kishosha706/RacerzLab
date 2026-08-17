from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path as ApiPath, Query
from pydantic import BaseModel, ConfigDict, Field

from racelab_engine.models.crew_chief import (
    CrewChiefWorkspace,
    EngineeringObjective,
)
from racelab_engine.services.crew_chief_service import (
    abandon_investigation,
    advance_until_boundary,
    build_crew_chief_workspace,
    continue_investigation,
    open_investigation,
    rebase_investigation,
    record_driver_answer,
    select_objective,
)

router = APIRouter(prefix="/api/runs", tags=["crew-chief"])


class CrewChiefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OpenInvestigationRequest(CrewChiefRequest):
    session_id: str = Field(min_length=1, max_length=160)
    driver_report: str = Field(min_length=1, max_length=2000)
    expected_workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective: EngineeringObjective = EngineeringObjective.RACE_LONG_RUN
    origin: Literal["post_import", "driver_report", "manual_review"] = "driver_report"


class RevisionRequest(CrewChiefRequest):
    session_id: str = Field(min_length=1, max_length=160)
    expected_workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class DriverAnswerRequest(RevisionRequest):
    answer: str = Field(min_length=1, max_length=160)


class AdvanceRequest(RevisionRequest):
    max_read_only_steps: int = Field(default=4, ge=1, le=4)


class ObjectiveRequest(RevisionRequest):
    objective: EngineeringObjective


class AbandonRequest(RevisionRequest):
    reason: str = Field(min_length=1, max_length=500)


class RebaseRequest(CrewChiefRequest):
    session_id: str = Field(min_length=1, max_length=160)
    stale_workspace_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


def _http_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status = (
        409
        if any(word in detail.casefold() for word in ("stale", "open", "revision"))
        else 422
    )
    return HTTPException(status_code=status, detail=detail)


@router.get("/{run_id}/crew-chief-workspace", response_model=CrewChiefWorkspace)
def get_crew_chief_workspace(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    session_id: Annotated[str, Query(min_length=1, max_length=160)],
    objective: EngineeringObjective = EngineeringObjective.RACE_LONG_RUN,
    investigation_id: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
) -> CrewChiefWorkspace:
    try:
        return build_crew_chief_workspace(
            run_id,
            session_id=session_id,
            objective=objective,
            investigation_id=investigation_id,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/crew-chief-investigations",
    response_model=CrewChiefWorkspace,
)
def create_crew_chief_investigation(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: OpenInvestigationRequest,
) -> CrewChiefWorkspace:
    try:
        return open_investigation(
            run_id,
            session_id=request.session_id,
            driver_report=request.driver_report,
            expected_workspace_revision=request.expected_workspace_revision,
            objective=request.objective,
            origin=request.origin,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/crew-chief-investigations/{investigation_id}/continue",
    response_model=CrewChiefWorkspace,
)
def continue_crew_chief_investigation(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    investigation_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: RevisionRequest,
) -> CrewChiefWorkspace:
    try:
        return continue_investigation(
            run_id,
            investigation_id,
            session_id=request.session_id,
            expected_workspace_revision=request.expected_workspace_revision,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/crew-chief-investigations/{investigation_id}/advance-until-boundary",
    response_model=CrewChiefWorkspace,
)
def advance_crew_chief_investigation(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    investigation_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: AdvanceRequest,
) -> CrewChiefWorkspace:
    try:
        return advance_until_boundary(
            run_id,
            investigation_id,
            session_id=request.session_id,
            expected_workspace_revision=request.expected_workspace_revision,
            max_read_only_steps=request.max_read_only_steps,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/crew-chief-investigations/{investigation_id}/driver-answer",
    response_model=CrewChiefWorkspace,
)
def answer_crew_chief_question(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    investigation_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: DriverAnswerRequest,
) -> CrewChiefWorkspace:
    try:
        return record_driver_answer(
            run_id,
            investigation_id,
            session_id=request.session_id,
            expected_workspace_revision=request.expected_workspace_revision,
            answer=request.answer,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/crew-chief-investigations/{investigation_id}/objective",
    response_model=CrewChiefWorkspace,
)
def change_crew_chief_objective(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    investigation_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: ObjectiveRequest,
) -> CrewChiefWorkspace:
    try:
        return select_objective(
            run_id,
            investigation_id,
            session_id=request.session_id,
            expected_workspace_revision=request.expected_workspace_revision,
            objective=request.objective,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/crew-chief-investigations/{investigation_id}/abandon",
    response_model=CrewChiefWorkspace,
)
def abandon_crew_chief_investigation(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    investigation_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: AbandonRequest,
) -> CrewChiefWorkspace:
    try:
        return abandon_investigation(
            run_id,
            investigation_id,
            session_id=request.session_id,
            expected_workspace_revision=request.expected_workspace_revision,
            reason=request.reason,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{run_id}/crew-chief-investigations/{investigation_id}/rebase",
    response_model=CrewChiefWorkspace,
)
def rebase_crew_chief_investigation(
    run_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    investigation_id: Annotated[str, ApiPath(min_length=1, max_length=160)],
    request: RebaseRequest,
) -> CrewChiefWorkspace:
    try:
        return rebase_investigation(
            run_id,
            investigation_id,
            session_id=request.session_id,
            stale_workspace_revision=request.stale_workspace_revision,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


__all__ = ["router"]
