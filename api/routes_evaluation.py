from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from racelab_engine.evaluation.campaigns import CampaignKind
from racelab_engine.evaluation.acquisition_operations import (
    CampaignQualificationCertificate,
    NegativeControlExpectation,
    P23AcquisitionProgress,
    P23CollectionKind,
    P23CollectionTemplate,
    P23PreRunChecklist,
    build_pre_run_checklist,
    freeze_negative_control_expectation,
    list_qualification_certificates,
    p23_acquisition_progress,
    p23_collection_templates,
    save_negative_control_expectation,
)
from racelab_engine.evaluation.first_activation import (
    P23FirstActivationAudit,
    build_first_activation_audit,
)
from racelab_engine.evaluation.learning_operations import (
    CampaignOperation,
    CampaignOperationEvent,
    list_campaign_operations,
    start_campaign_operation,
    transition_campaign_operation,
)
from racelab_engine.evaluation.prospective import (
    ProspectiveTestOutcome,
    ProspectiveTestPrediction,
    append_prospective_outcome,
    attach_p19_workflow_outcome,
    freeze_p19_controlled_prediction,
    prospective_runtime_code_hash,
    save_prospective_prediction,
)
from racelab_engine.evaluation.readiness import (
    LearningReadinessProjection,
    build_learning_readiness_projection,
)


router = APIRouter(prefix="/api/evaluation", tags=["evidence-evaluation"])


class StartCampaignOperationRequest(BaseModel):
    run_id: str = Field(min_length=1)
    campaign_kind: CampaignKind


class TransitionCampaignOperationRequest(BaseModel):
    event_type: Literal["paused", "resumed", "completed", "abandoned"]
    reason: str = Field(min_length=1, max_length=500)


class FreezeProspectivePredictionRequest(BaseModel):
    operation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    session_id: str | None = None


class AttachProspectiveOutcomeRequest(BaseModel):
    workflow_id: str = Field(min_length=1)


class FreezeNegativeControlRequest(BaseModel):
    operation_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)


@router.get("/first-activation-audit", response_model=P23FirstActivationAudit)
def get_first_activation_audit() -> P23FirstActivationAudit:
    return build_first_activation_audit()


@router.get("/p23-acquisition-progress", response_model=P23AcquisitionProgress)
def get_p23_acquisition_progress() -> P23AcquisitionProgress:
    return p23_acquisition_progress()


@router.get(
    "/p23-collection-templates",
    response_model=tuple[P23CollectionTemplate, ...],
)
def get_p23_collection_templates() -> tuple[P23CollectionTemplate, ...]:
    return p23_collection_templates()


@router.get(
    "/p23-qualification-certificates",
    response_model=tuple[CampaignQualificationCertificate, ...],
)
def get_p23_qualification_certificates() -> tuple[CampaignQualificationCertificate, ...]:
    return list_qualification_certificates()


@router.get("/p23-pre-run-checklist", response_model=P23PreRunChecklist)
def get_p23_pre_run_checklist(
    run_id: str,
    collection_kind: P23CollectionKind = "historical_exact_ffb",
) -> P23PreRunChecklist:
    try:
        return build_pre_run_checklist(run_id, collection_kind=collection_kind)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc


@router.post(
    "/p23-negative-control-expectations",
    response_model=NegativeControlExpectation,
)
def freeze_p23_negative_control(
    payload: FreezeNegativeControlRequest,
) -> NegativeControlExpectation:
    operation = next(
        (
            item
            for item in list_campaign_operations()
            if item.operation_id == payload.operation_id
        ),
        None,
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Campaign operation not found.")
    try:
        expectation = freeze_negative_control_expectation(
            recipe_id=payload.recipe_id,
            operation=operation,
        )
        save_negative_control_expectation(expectation)
        return expectation
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/learning-readiness", response_model=LearningReadinessProjection)
def get_learning_readiness(
    run_id: str,
    session_id: str | None = None,
) -> LearningReadinessProjection:
    try:
        return build_learning_readiness_projection(run_id, session_id=session_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc


@router.post("/campaign-operations/start", response_model=CampaignOperation)
def start_operation(payload: StartCampaignOperationRequest) -> CampaignOperation:
    try:
        return start_campaign_operation(payload.campaign_kind, payload.run_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc


@router.post(
    "/campaign-operations/{operation_id}/transition",
    response_model=CampaignOperationEvent,
)
def transition_operation(
    operation_id: str,
    payload: TransitionCampaignOperationRequest,
) -> CampaignOperationEvent:
    try:
        return transition_campaign_operation(
            operation_id,
            payload.event_type,
            payload.reason,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc


@router.post("/prospective-predictions", response_model=ProspectiveTestPrediction)
def freeze_prediction(
    payload: FreezeProspectivePredictionRequest,
) -> ProspectiveTestPrediction:
    try:
        prediction = freeze_p19_controlled_prediction(
            payload.operation_id,
            payload.run_id,
            session_id=payload.session_id,
            code_hash=prospective_runtime_code_hash(),
        )
        save_prospective_prediction(prediction)
        return prediction
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc


@router.post(
    "/prospective-predictions/{prediction_id}/outcome",
    response_model=ProspectiveTestOutcome,
)
def attach_prediction_outcome(
    prediction_id: str,
    payload: AttachProspectiveOutcomeRequest,
) -> ProspectiveTestOutcome:
    try:
        outcome = attach_p19_workflow_outcome(prediction_id, payload.workflow_id)
        append_prospective_outcome(outcome)
        return outcome
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc


__all__ = ["router"]
