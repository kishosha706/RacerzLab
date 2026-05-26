from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from racelab_engine.models.event import TelemetryEvent
from racelab_engine.models.lap import LapSummary
from racelab_engine.models.recommendation import Recommendation
from racelab_engine.models.setup import SetupSnapshot


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionSummary(BaseModel):
    run_id: str
    source_file: Optional[str] = None
    file_hash: Optional[str] = None
    import_time: datetime = Field(default_factory=utc_now)
    sim_date_time: Optional[str] = None
    car_name: Optional[str] = None
    car_path: Optional[str] = None
    track_name: Optional[str] = None
    track_display_name: Optional[str] = None
    track_id_or_path: Optional[str] = None
    session_type: Optional[str] = None
    weather_summary: Optional[str] = None
    air_temp: Optional[float] = None
    track_temp: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    air_pressure: Optional[float] = None
    telemetry_rate_hz: Optional[int] = None
    variable_count: Optional[int] = None
    record_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    setup_name: Optional[str] = None
    setup_passed_tech: Optional[bool] = None
    setup_modified: Optional[bool] = None
    notes: list[str] = Field(default_factory=list)


class RunOverview(BaseModel):
    run_id: str
    session: SessionSummary
    best_useful_lap: Optional[LapSummary] = None
    laps: list[LapSummary] = Field(default_factory=list)
    events: list[TelemetryEvent] = Field(default_factory=list)
    setup_snapshot: Optional[SetupSnapshot] = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    primary_findings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    crew_chief_summary: Optional[str] = None
    next_test: Optional[str] = None
