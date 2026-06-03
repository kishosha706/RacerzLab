from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from racelab_engine.io.ibt_reader import (
    _SHOCK_MOVEMENT_UNAVAILABLE_WARNING,
    _build_missing_optional_warnings,
)
from racelab_engine.services.import_service import ImportService, build_channel_catalog


DEFAULT_CANONICAL_SHOCK_IBT = Path(
    r"c:\Users\Soulj\Documents\iRacing\telemetry\stockcars chevycamarozl12022_charlotte 2025 oval 2026-05-14 16-28-36.ibt"
)


def test_missing_optional_warnings_replace_raw_shock_ids_with_human_warning() -> None:
    missing = [
        "LFSHshockDefl",
        "RFSHshockDefl",
        "LRSHshockDefl",
        "RRSHshockDefl",
        "LFSHshockVel",
        "RFSHshockVel",
        "LRSHshockVel",
        "RRSHshockVel",
    ]

    warnings = _build_missing_optional_warnings(missing, available_channels={"Speed", "LapDist"})

    assert warnings == [_SHOCK_MOVEMENT_UNAVAILABLE_WARNING]
    assert all("shockDefl" not in warning for warning in warnings)
    assert all("shockVel" not in warning for warning in warnings)


def test_missing_optional_warnings_treat_canonical_shock_aliases_as_available() -> None:
    missing = [
        "LFSHshockDefl",
        "RFSHshockDefl",
        "LRSHshockDefl",
        "RRSHshockDefl",
        "LFSHshockVel",
        "RFSHshockVel",
        "LRSHshockVel",
        "RRSHshockVel",
    ]
    available = {
        "LFshockDefl",
        "RFshockDefl",
        "LRshockDefl",
        "RRshockDefl",
        "LFshockVel",
        "RFshockVel",
        "LRshockVel",
        "RRshockVel",
    }

    warnings = _build_missing_optional_warnings(missing, available_channels=available)

    assert warnings == []


def test_missing_optional_warnings_keep_non_shock_channel_details() -> None:
    missing = [
        "LFSHshockDefl",
        "LFSHshockVel",
        "WaterTemp",
        "OilTemp",
    ]

    warnings = _build_missing_optional_warnings(missing, available_channels={"Speed"})

    assert warnings == [
        "Missing optional channels: WaterTemp, OilTemp.",
        _SHOCK_MOVEMENT_UNAVAILABLE_WARNING,
    ]


def test_canonical_shock_file_channel_catalog_contains_raw_channels() -> None:
    path = Path(os.environ.get("RACELAB_CANONICAL_SHOCK_IBT", DEFAULT_CANONICAL_SHOCK_IBT))
    if not path.exists():
        pytest.skip(f"Canonical shock .ibt fixture not found: {path}")

    with TemporaryDirectory() as td:
        root = Path(td)
        result, _cache = ImportService(db_path=root / "racelab.sqlite", data_dir=root / "data").import_ibt_file(path)
        assert result.overview is not None
        catalog = build_channel_catalog(result.overview.run_id, data_dir=root / "data")
        catalog_by_name = {item["name"]: item for item in catalog}

        for channel in (
            "LFshockDefl", "RFshockDefl", "LRshockDefl", "RRshockDefl",
            "LFshockVel", "RFshockVel", "LRshockVel", "RRshockVel",
        ):
            item = catalog_by_name.get(channel)
            assert item is not None, f"Missing channel catalog entry for {channel}"
            assert item["is_raw"] is True
            assert item["missing_status"] is None
