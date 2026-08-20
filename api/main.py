from __future__ import annotations

import os

from fastapi import FastAPI, Request
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
from api.schemas import HealthResponse
from racelab_engine import __version__
from racelab_engine.services.import_service import TelemetryArtifactIdentityError
from racelab_engine.storage.repository import StoredEvidenceIntegrityError

app = FastAPI(title="RacerZLab API", version=__version__)


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


@app.get("/api/health")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        app="RacerZLab",
        version=__version__,
        instance_id=os.environ.get("RACERZLAB_BACKEND_INSTANCE_TOKEN") or None,
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
