from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes_compare import router as compare_router
from api.routes_events import router as events_router
from api.routes_imports import router as imports_router
from api.routes_laps import router as laps_router
from api.routes_notebook import router as notebook_router
from api.routes_reports import router as reports_router
from api.routes_runs import router as runs_router
from api.routes_sessions import router as sessions_router
from api.routes_track_map import router as track_map_router
from api.schemas import HealthResponse
from racelab_engine import __version__

app = FastAPI(title="RacerZLab API", version=__version__)

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
    return HealthResponse(status="ok", app="RacerZLab", version=__version__)


app.include_router(compare_router)
app.include_router(imports_router)
app.include_router(runs_router)
app.include_router(laps_router)
app.include_router(events_router)
app.include_router(reports_router)
app.include_router(notebook_router)
app.include_router(sessions_router)
app.include_router(track_map_router)
