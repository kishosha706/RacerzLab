from __future__ import annotations

from pathlib import Path

from api.schemas import ChannelSummaryItem
from racelab_engine.io.ibt_types import IBTVariableDefinition
from racelab_engine.services.import_service import (
    build_channel_summary,
    read_telemetry_rows,
    write_channel_metadata,
    write_telemetry_cache,
)


def test_channel_summary_schema_preserves_boot_metadata(tmp_path: Path) -> None:
    run_id = "summary-contract"
    write_telemetry_cache(
        run_id,
        [{"session_time": 0.0, "speed_mph": 112.0}],
        data_dir=tmp_path,
    )
    write_channel_metadata(
        run_id,
        [
            IBTVariableDefinition(
                name="speed_mph",
                description="Vehicle speed",
                unit="mph",
                data_type="float",
                count=1,
            ),
        ],
        data_dir=tmp_path,
    )

    summary_by_name = {
        item["name"]: ChannelSummaryItem(**item).model_dump()
        for item in build_channel_summary(run_id, tmp_path)
    }

    speed = summary_by_name["speed_mph"]
    assert speed["label"] == "Speed"
    assert speed["description"] == "Vehicle speed"
    assert speed["unit"] == "mph"
    assert speed["type"] == "float"
    assert speed["count"] == 1
    assert speed["source"] == "raw"


def test_read_telemetry_rows_prunes_columns_and_filters_lap(tmp_path: Path) -> None:
    run_id = "column-prune"
    write_telemetry_cache(
        run_id,
        [
            {"lap": 1, "session_time": 0.0, "speed_mph": 100.0, "rpm": 7000},
            {"lap": 2, "session_time": 1.0, "speed_mph": 110.0, "rpm": 7200},
        ],
        data_dir=tmp_path,
    )

    rows = read_telemetry_rows(run_id, data_dir=tmp_path, lap=2, columns=["speed_mph"])

    assert rows == [{"speed_mph": 110.0}]
