from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RaceLabSession:
    session_id: str
    name: str
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    track_name: str | None = None
    car_name: str | None = None
    run_ids: list[str] = field(default_factory=list)
    last_opened_run_id: str | None = None
    last_selected_lap: int | None = None
    last_workspace: str | None = None
    notebook_finding_ids: list[str] = field(default_factory=list)
    status: Literal["active", "archived"] = "active"

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "track_name": self.track_name,
            "car_name": self.car_name,
            "run_ids": self.run_ids,
            "last_opened_run_id": self.last_opened_run_id,
            "last_selected_lap": self.last_selected_lap,
            "last_workspace": self.last_workspace,
            "notebook_finding_ids": self.notebook_finding_ids,
            "status": self.status,
        }
