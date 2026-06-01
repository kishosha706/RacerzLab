"""Profile key backend endpoints with payload and repeat-call timings.

Usage:
  PYTHONPATH=. python -B scripts/profile_api_endpoints.py
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from fastapi.testclient import TestClient

from api.main import app


@dataclass
class EndpointProfile:
    endpoint: str
    method: str
    duration_ms: float
    payload_size: int
    rows: int | None
    columns: int | None
    status_code: int
    duplicate_call_ms: float


def _payload_shape(payload: Any) -> tuple[int | None, int | None]:
    if isinstance(payload, list):
        rows = len(payload)
        if rows > 0 and isinstance(payload[0], dict):
            return rows, len(payload[0])
        return rows, None
    if isinstance(payload, dict):
        if "sample_count" in payload:
            channels = payload.get("channels")
            if isinstance(channels, dict):
                return int(payload.get("sample_count") or 0), len(channels)
        return None, len(payload)
    return None, None


def _timed_request(client: TestClient, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[float, Any, int, int]:
    t0 = time.perf_counter()
    if method == "GET":
        response = client.get(path)
    else:
        response = client.post(path, json=body or {})
    dt_ms = (time.perf_counter() - t0) * 1000.0
    payload_size = len(response.content)
    data = response.json() if response.headers.get("content-type", "").startswith("application/json") else None
    return dt_ms, data, response.status_code, payload_size


def main() -> None:
    profiles: list[EndpointProfile] = []
    with TestClient(app) as client:
        runs = client.get("/api/runs").json()
        if not runs:
            print(json.dumps({"error": "No runs available in local database."}, indent=2))
            return

        run_id = runs[0]["run_id"]
        run_id_2 = runs[1]["run_id"] if len(runs) > 1 else runs[0]["run_id"]
        overview = client.get(f"/api/runs/{run_id}/overview").json()
        lap = overview.get("best_useful_lap", {}).get("lap_number")

        requests: list[tuple[str, str, str, dict[str, Any] | None]] = [
            ("runs/list", "GET", "/api/runs", None),
            ("run/open", "GET", f"/api/runs/{run_id}/overview", None),
            ("laps", "GET", f"/api/runs/{run_id}/laps", None),
            ("events", "GET", f"/api/runs/{run_id}/events", None),
            ("trace", "GET", f"/api/runs/{run_id}/trace?lap={lap}&x=lap_dist_ft&downsample=auto", None),
            ("platform-events", "GET", f"/api/runs/{run_id}/platform-events?lap={lap}", None),
            ("setup snapshot", "GET", f"/api/runs/{run_id}/setup", None),
            ("channels", "GET", f"/api/runs/{run_id}/channels", None),
            ("track-map package", "GET", f"/api/runs/{run_id}/track-map-package?lap={lap}", None),
            ("compare preview", "GET", f"/api/compare/preview?baseline_run_id={run_id}&test_run_id={run_id_2}", None),
            ("notebook/findings", "GET", "/api/notebook/findings", None),
        ]

        for endpoint, method, path, body in requests:
            first_ms, payload, status, payload_size = _timed_request(client, method, path, body)
            second_ms, _payload2, _status2, _payload_size2 = _timed_request(client, method, path, body)
            rows, columns = _payload_shape(payload)
            profiles.append(
                EndpointProfile(
                    endpoint=endpoint,
                    method=method,
                    duration_ms=round(first_ms, 2),
                    duplicate_call_ms=round(second_ms, 2),
                    payload_size=payload_size,
                    rows=rows,
                    columns=columns,
                    status_code=status,
                )
            )

    summary = {
        "run_id": run_id,
        "lap": lap,
        "profiles": [profile.__dict__ for profile in profiles],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
