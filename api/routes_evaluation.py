from __future__ import annotations

from fastapi import APIRouter, HTTPException

from racelab_engine.evaluation.readiness import (
    LearningReadinessProjection,
    build_learning_readiness_projection,
)


router = APIRouter(prefix="/api/evaluation", tags=["evidence-evaluation"])


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


__all__ = ["router"]
