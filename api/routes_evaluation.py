from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from racelab_engine.evaluation.acquisition_operations import (
    CampaignQualificationCertificate,
    NegativeControlExpectation,
    NegativeControlRecipe,
    P23AcquisitionProgress,
    P23CollectionKind,
    P23CollectionTemplate,
    P23PreRunChecklist,
    P25NullSessionRunCard,
    build_pre_run_checklist,
    freeze_negative_control_expectation,
    freeze_null_session_run_card,
    latest_null_session_run_card,
    list_qualification_certificates,
    negative_control_recipe_catalog,
    p23_acquisition_progress,
    p23_collection_templates,
    save_negative_control_expectation,
)
from racelab_engine.evaluation.campaigns import CampaignKind
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
    session_id: str = Field(min_length=1)


class ProspectivePredictionReceipt(BaseModel):
    """Non-authoritative receipt for an internally frozen shadow artifact."""

    prediction_id: str = Field(pattern=r"^ptp-[0-9a-f]{20}$")
    operation_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    session_id: str | None = None
    predicted_at: datetime
    prospective: Literal[True] = True
    authority: Literal["shadow_only"] = "shadow_only"
    setup_authorized: Literal[False] = False


class FreezeNegativeControlRequest(BaseModel):
    operation_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)


class FreezeNullRunCardRequest(BaseModel):
    reference_run_id: str = Field(min_length=1)


@router.get("/first-activation-audit", response_model=P23FirstActivationAudit)
def get_first_activation_audit() -> P23FirstActivationAudit:
    return build_first_activation_audit()


@router.get("/p23-acquisition-progress", response_model=P23AcquisitionProgress)
def get_p23_acquisition_progress() -> P23AcquisitionProgress:
    return p23_acquisition_progress()


@router.get("/p25-null-session-run-card", response_model=P25NullSessionRunCard | None)
def get_p25_null_session_run_card() -> P25NullSessionRunCard | None:
    return latest_null_session_run_card()


@router.post("/p25-null-session-run-card", response_model=P25NullSessionRunCard)
def freeze_p25_null_session_run_card(
    payload: FreezeNullRunCardRequest,
) -> P25NullSessionRunCard:
    try:
        return freeze_null_session_run_card(payload.reference_run_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc


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
def get_p23_qualification_certificates(
    limit: int = Query(default=50, ge=1, le=200),
) -> tuple[CampaignQualificationCertificate, ...]:
    return list_qualification_certificates(limit=limit)


@router.get(
    "/p23-negative-control-recipes",
    response_model=tuple[NegativeControlRecipe, ...],
)
def get_p23_negative_control_recipes() -> tuple[NegativeControlRecipe, ...]:
    return negative_control_recipe_catalog()


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


@router.post("/prospective-predictions", response_model=ProspectivePredictionReceipt)
def freeze_prediction(
    payload: FreezeProspectivePredictionRequest,
) -> ProspectivePredictionReceipt:
    try:
        prediction = freeze_p19_controlled_prediction(
            payload.operation_id,
            payload.run_id,
            session_id=payload.session_id,
            code_hash=prospective_runtime_code_hash(),
        )
        save_prospective_prediction(prediction)
        return ProspectivePredictionReceipt(
            prediction_id=prediction.prediction_id,
            operation_id=prediction.operation_id,
            source_run_id=prediction.source_run_id,
            session_id=prediction.session_id,
            predicted_at=prediction.predicted_at,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status, detail=message) from exc

__all__ = ["router"]
