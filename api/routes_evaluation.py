from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from racelab_engine.evaluation.campaigns import CampaignKind
from racelab_engine.evaluation.first_activation import (
    P23FirstActivationAudit,
    build_first_activation_audit,
)
from racelab_engine.evaluation.learning_operations import (
    CampaignOperation,
    CampaignOperationEvent,
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


@router.get("/first-activation-audit", response_model=P23FirstActivationAudit)
def get_first_activation_audit() -> P23FirstActivationAudit:
    return build_first_activation_audit()


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
