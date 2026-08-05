from __future__ import annotations

from pathlib import Path
from typing import Any

from racelab_engine.services.import_service import read_telemetry_manifest
from racelab_engine.reports.markdown_report import (
    generate_controlled_workflow_report,
    generate_markdown_report,
)
from racelab_engine.storage.repository import RaceLabRepository


class ReportService:
    def __init__(self, db_path: str | Path | None = None):
        self.repository = RaceLabRepository(db_path)

    def generate_markdown(self, run_id: str) -> str | None:
        overview = self.repository.get_overview(run_id)
        if overview is None:
            return None
        return generate_markdown_report(overview)

    def generate_workflow_markdown(self, workflow_id: str) -> str | None:
        workflow = self.repository.get_controlled_workflow(workflow_id)
        if workflow is None:
            return None
        stage_overviews = {
            stage: self.repository.get_overview(run_id)
            for stage, run_id in workflow.stage_run_ids.items()
        }
        manifests: dict[str, dict[str, Any]] = {}
        for stage, run_id in workflow.stage_run_ids.items():
            try:
                manifests[stage] = read_telemetry_manifest(run_id)
            except (FileNotFoundError, OSError, ValueError):
                manifests[stage] = {}
        return generate_controlled_workflow_report(
            workflow,
            stage_overviews=stage_overviews,
            manifests=manifests,
        )
