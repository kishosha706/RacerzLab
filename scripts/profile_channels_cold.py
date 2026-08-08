"""Profile cold /channels and /channels/summary construction stages.

Usage:
  PYTHONPATH=. python -B scripts/profile_channels_cold.py
"""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from api.main import app
from api.schemas import ChannelCatalogItem, ChannelSummaryItem
from racelab_engine.services import import_service as svc
from racelab_engine.storage.repository import RaceLabRepository


def _clear_caches() -> None:
    svc._TELEMETRY_ROWS_CACHE.clear()  # type: ignore[attr-defined]
    svc._CHANNEL_CATALOG_CACHE.clear()  # type: ignore[attr-defined]
    svc._CHANNEL_SUMMARY_CACHE.clear()  # type: ignore[attr-defined]


def _timed(fn):
    t0 = time.perf_counter()
    value = fn()
    return (time.perf_counter() - t0) * 1000.0, value


def _catalog_names(definitions: dict[str, dict[str, Any]], columns: list[str]) -> list[str]:
    names = list(definitions)
    names.extend(name for name in svc.HIGH_VALUE_RAW_CHANNELS if name not in names)
    names.extend(name for name in columns if name not in names)
    names.extend(name for name in svc.CALCULATED_CHANNEL_UNITS if name not in names)
    return names


def _profile_full(run_id: str, data_root: Path) -> dict[str, Any]:
    path = svc.parquet_path(data_root, run_id)
    rows = None
    if path.exists() and importlib.util.find_spec("polars") is not None:
        pl = __import__("polars")
        rows = int(pl.scan_parquet(path).select(pl.len()).collect(engine="streaming").item())
    else:
        rows = None

    schema_ms, schema = _timed(lambda: __import__("polars").read_parquet_schema(path) if path.exists() and importlib.util.find_spec("polars") else {})
    columns = list(schema.keys()) if isinstance(schema, dict) else []

    stats_ms, stats_result = _timed(
        lambda: svc._precompute_channel_stats_from_parquet(path)  # type: ignore[attr-defined]
        if path.exists()
        else ({}, [])
    )
    stats_map, stat_columns = stats_result
    if stat_columns:
        columns = stat_columns

    metadata_ms, definitions = _timed(lambda: {d["name"]: d for d in svc.read_channel_metadata(run_id, data_root)})
    names = _catalog_names(definitions, columns)

    merge_ms, catalog = _timed(lambda: [
        svc._build_catalog_item(  # type: ignore[attr-defined]
            name,
            definitions.get(name),
            (is_raw := definitions.get(name) is not None or name in svc.HIGH_VALUE_RAW_CHANNELS),
            name in svc.CALCULATED_CHANNEL_UNITS or (not is_raw and name in set(columns)),
            name in set(columns),
            stats_map,
        )
        for name in names
    ])

    model_ms, models = _timed(lambda: [ChannelCatalogItem(**item) for item in catalog])
    serialize_ms, payload = _timed(lambda: json.dumps([m.model_dump(mode="json") for m in models]).encode("utf-8"))
    parse_ms, _ = _timed(lambda: json.loads(payload.decode("utf-8")))

    return {
        "rows": rows,
        "columns": len(columns),
        "payload_size": len(payload),
        "stages": [
            {"stage": "parquet_schema_read", "time_ms": round(schema_ms, 2)},
            {"stage": "stats_compute", "time_ms": round(stats_ms, 2)},
            {"stage": "metadata_read", "time_ms": round(metadata_ms, 2)},
            {"stage": "metadata_merge", "time_ms": round(merge_ms, 2)},
            {"stage": "pydantic_models", "time_ms": round(model_ms, 2)},
            {"stage": "json_serialize", "time_ms": round(serialize_ms, 2)},
            {"stage": "json_parse_frontend_estimate", "time_ms": round(parse_ms, 2)},
        ],
    }


def _profile_summary(run_id: str, data_root: Path) -> dict[str, Any]:
    path = svc.parquet_path(data_root, run_id)
    if path.exists() and importlib.util.find_spec("polars") is not None:
        pl = __import__("polars")
        rows = int(pl.scan_parquet(path).select(pl.len()).collect(engine="streaming").item())
    else:
        rows = None

    schema_ms, schema = _timed(lambda: __import__("polars").read_parquet_schema(path) if path.exists() and importlib.util.find_spec("polars") else {})
    columns = list(schema.keys()) if isinstance(schema, dict) else []

    metadata_ms, definitions = _timed(lambda: {d["name"]: d for d in svc.read_channel_metadata(run_id, data_root)})
    names = _catalog_names(definitions, columns)
    column_set = set(columns)

    merge_ms, summary = _timed(lambda: [
        svc._build_summary_item(  # type: ignore[attr-defined]
            name,
            definitions.get(name),
            (is_raw := definitions.get(name) is not None or name in svc.HIGH_VALUE_RAW_CHANNELS),
            name in svc.CALCULATED_CHANNEL_UNITS or (not is_raw and name in column_set),
            name in column_set,
        )
        for name in names
    ])

    model_ms, models = _timed(lambda: [ChannelSummaryItem(**item) for item in summary])
    serialize_ms, payload = _timed(lambda: json.dumps([m.model_dump(mode="json") for m in models]).encode("utf-8"))
    parse_ms, _ = _timed(lambda: json.loads(payload.decode("utf-8")))

    return {
        "rows": rows,
        "columns": len(columns),
        "payload_size": len(payload),
        "stages": [
            {"stage": "parquet_schema_read", "time_ms": round(schema_ms, 2)},
            {"stage": "metadata_read", "time_ms": round(metadata_ms, 2)},
            {"stage": "metadata_merge", "time_ms": round(merge_ms, 2)},
            {"stage": "pydantic_models", "time_ms": round(model_ms, 2)},
            {"stage": "json_serialize", "time_ms": round(serialize_ms, 2)},
            {"stage": "json_parse_frontend_estimate", "time_ms": round(parse_ms, 2)},
        ],
    }


def _profile_endpoint_times(run_id: str) -> dict[str, Any]:
    with TestClient(app) as client:
        _clear_caches()
        t0 = time.perf_counter()
        full_resp = client.get(f"/api/runs/{run_id}/channels?compact=true")
        full_ms = (time.perf_counter() - t0) * 1000.0
        _clear_caches()
        t0 = time.perf_counter()
        summary_resp = client.get(f"/api/runs/{run_id}/channels/summary?compact=true")
        summary_ms = (time.perf_counter() - t0) * 1000.0
    return {
        "full_ms": round(full_ms, 2),
        "full_payload_size": len(full_resp.content),
        "summary_ms": round(summary_ms, 2),
        "summary_payload_size": len(summary_resp.content),
        "full_status": full_resp.status_code,
        "summary_status": summary_resp.status_code,
    }


def main() -> None:
    repo = RaceLabRepository()
    runs = repo.list_runs()
    if not runs:
        print(json.dumps({"error": "No runs found"}, indent=2))
        return
    run_id = runs[0]["run_id"]
    data_root = svc.default_data_dir()

    _clear_caches()
    full = _profile_full(run_id, data_root)
    _clear_caches()
    summary = _profile_summary(run_id, data_root)
    endpoint = _profile_endpoint_times(run_id)

    print(json.dumps({
        "run_id": run_id,
        "full_profile": full,
        "summary_profile": summary,
        "endpoint": endpoint,
    }, indent=2))


if __name__ == "__main__":
    main()
