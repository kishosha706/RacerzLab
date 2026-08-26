from __future__ import annotations

import os
import secrets

from fastapi import FastAPI, Request, status as http_status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes_compare import router as compare_router
from api.routes_crew_chief import router as crew_chief_router
from api.routes_analysis_contracts import router as analysis_contracts_router
from api.routes_events import router as events_router
from api.routes_engineering import router as engineering_router
from api.routes_engineering_case import router as engineering_case_router
from api.routes_engineering_awareness import router as engineering_awareness_router
from api.routes_evaluation import router as evaluation_router
from api.routes_imports import router as imports_router
from api.routes_intelligence import router as intelligence_router
from api.routes_laps import router as laps_router
from api.routes_laps import stints_router
from api.routes_notebook import router as notebook_router
from api.routes_p3_engineering import router as p3_engineering_router
from api.routes_reports import router as reports_router
from api.routes_runs import router as runs_router
from api.routes_sessions import router as sessions_router
from api.routes_shock_reader import router as shock_reader_router
from api.routes_track_map import router as track_map_router
from api.schemas import HealthResponse, HealthUnavailableResponse
from racelab_engine import __version__
from racelab_engine.services.import_service import TelemetryArtifactIdentityError
from racelab_engine.services.storage_readiness_service import check_storage_readiness
from racelab_engine.storage.repository import StoredEvidenceIntegrityError

app = FastAPI(title="RacerZLab API", version=__version__)
_CAPABILITY_ENV = "RACERZLAB_BACKEND_CAPABILITY_TOKEN"
_CAPABILITY_HEADER = "X-RacerZLab-Capability"


@app.exception_handler(StoredEvidenceIntegrityError)
def stored_evidence_integrity_error(
    _request: Request,
    exc: StoredEvidenceIntegrityError,
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(TelemetryArtifactIdentityError)
def telemetry_artifact_identity_error(
    _request: Request,
    exc: TelemetryArtifactIdentityError,
) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.middleware("http")
async def require_desktop_capability(request: Request, call_next):
    expected = os.environ.get(_CAPABILITY_ENV)
    if (
        expected is not None
        and request.method != "OPTIONS"
        and request.url.path != "/api/health"
    ):
        supplied = request.headers.get(_CAPABILITY_HEADER) or ""
        expected_has_valid_format = (
            len(expected) == 64
            and all(character in "0123456789abcdef" for character in expected)
        )
        if not (
            expected_has_valid_format
            and secrets.compare_digest(supplied, expected)
        ):
            return JSONResponse(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Unauthorized."},
                headers={"Cache-Control": "no-store"},
            )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/api/health",
    response_model=HealthResponse,
    responses={
        http_status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": HealthUnavailableResponse,
            "description": "Configured local storage is not ready.",
        }
    },
)
def health() -> HealthResponse | JSONResponse:
    instance_id = os.environ.get("RACERZLAB_BACKEND_INSTANCE_TOKEN") or None
    readiness = check_storage_readiness()
    if not readiness.ready:
        unavailable = HealthUnavailableResponse(
            version=__version__,
            instance_id=instance_id,
            readiness_code=readiness.code.value,
            recovery_code=readiness.recovery_code.value,
        )
        return JSONResponse(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            content=unavailable.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )

    return HealthResponse(
        status="ok",
        app="RacerZLab",
        version=__version__,
        instance_id=instance_id,
    )


app.include_router(compare_router)
app.include_router(crew_chief_router)
app.include_router(analysis_contracts_router)
app.include_router(imports_router)
app.include_router(runs_router)
app.include_router(laps_router)
app.include_router(stints_router)
app.include_router(events_router)
app.include_router(intelligence_router)
app.include_router(engineering_router)
app.include_router(engineering_case_router)
app.include_router(engineering_awareness_router)
app.include_router(evaluation_router)
app.include_router(p3_engineering_router)
app.include_router(reports_router)
app.include_router(notebook_router)
app.include_router(sessions_router)
app.include_router(shock_reader_router)
app.include_router(track_map_router)
