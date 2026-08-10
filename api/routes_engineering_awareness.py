from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from racelab_engine.models.engineering_projection import EngineeringAwarenessProjection
from racelab_engine.services.engineering_projection_service import (
    build_engineering_awareness_projection,
)


router = APIRouter(prefix="/api/runs", tags=["engineering-awareness"])


@router.get(
    "/{run_id}/engineering-awareness",
    response_model=EngineeringAwarenessProjection,
)
def get_engineering_awareness(
    run_id: str,
    session_id: str | None = None,
    refresh: Annotated[bool, Query()] = False,
) -> EngineeringAwarenessProjection:
    try:
        return build_engineering_awareness_projection(
            run_id,
            session_id=session_id,
            refresh=refresh,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.casefold() else 409
        raise HTTPException(status_code=status_code, detail=message) from exc


__all__ = ["router"]
