from __future__ import annotations

from pathlib import Path

from racelab_engine.reports.markdown_report import generate_markdown_report
from racelab_engine.storage.repository import RaceLabRepository


class ReportService:
    def __init__(self, db_path: str | Path | None = None):
        self.repository = RaceLabRepository(db_path)

    def generate_markdown(self, run_id: str) -> str | None:
        overview = self.repository.get_overview(run_id)
        if overview is None:
            return None
        return generate_markdown_report(overview)
