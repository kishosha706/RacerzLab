from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from racelab_engine.io.file_fingerprint import FileFingerprint
from racelab_engine.models.session import RunOverview


class IBTHeader(BaseModel):
    version: Optional[int] = None
    status: Optional[int] = None
    telemetry_rate_hz: Optional[int] = None
    session_info_update: Optional[int] = None
    session_info_length: Optional[int] = None
    session_info_offset: Optional[int] = None
    variable_count: Optional[int] = None
    variable_header_offset: Optional[int] = None
    buffer_count: Optional[int] = None
    record_length: Optional[int] = None
    data_offset: Optional[int] = None
    record_count: Optional[int] = None
    duration_seconds: Optional[float] = None
    raw_header: dict[str, Any] = Field(default_factory=dict)


class IBTVariableDefinition(BaseModel):
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None
    data_type: Optional[str] = None
    data_type_id: Optional[int] = None
    offset: int = 0
    count: int = 1
    count_as_time: bool = False


class ImportStatus(BaseModel):
    status: str
    message: str
    implemented: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IBTImportResult(BaseModel):
    status: ImportStatus
    fingerprint: Optional[FileFingerprint] = None
    header: Optional[IBTHeader] = None
    variable_definitions: list[IBTVariableDefinition] = Field(default_factory=list)
    session_yaml: Optional[str] = None
    records: list[dict[str, Any]] = Field(default_factory=list)
    missing_channels: list[str] = Field(default_factory=list)
    overview: Optional[RunOverview] = None
