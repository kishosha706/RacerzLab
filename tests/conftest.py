from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

DEFAULT_TALLADEGA_IBT = Path(
    r"c:\Users\Soulj\Documents\iRacing\telemetry\stockcars camarozl12018_talladega 2026-05-07 15-05-45.ibt"
)


@pytest.fixture(scope="session")
def talladega_ibt_path() -> Path:
    path = Path(os.environ.get("RACELAB_TALLADEGA_IBT", DEFAULT_TALLADEGA_IBT))
    if not path.exists():
        pytest.skip(f"Talladega .ibt fixture not found: {path}")
    return path


@dataclass(frozen=True)
class ImportedRunFixture:
    run_id: str
    data_dir: Path


@pytest.fixture(scope="module")
def talladega_run(talladega_ibt_path: Path, tmp_path_factory) -> ImportedRunFixture:
    """Import the Talladega .ibt once per test module and reuse across tests."""
    from racelab_engine.services.import_service import ImportService

    db_path = tmp_path_factory.mktemp("mod") / "racelab.sqlite"
    data_dir = db_path.parent / "data"
    data_dir.mkdir(exist_ok=True)

    result, _cache = ImportService(db_path=db_path, data_dir=data_dir).import_ibt_file(talladega_ibt_path)
    assert result.overview is not None, "Module-level Talladega import failed"
    return ImportedRunFixture(run_id=result.overview.run_id, data_dir=data_dir)
