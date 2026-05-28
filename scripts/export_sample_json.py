#!/usr/bin/env python3
"""Export a small normalized telemetry sample as JSON for engine comparison.

Usage
-----
    python scripts/export_sample_json.py <run_id> [--output path/to/sample.json] [--max-rows 500]

If no run_id is given, lists available runs.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from racelab_engine.services.import_service import read_telemetry_rows
from racelab_engine.storage.repository import RaceLabRepository


def list_runs() -> None:
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "racelab.sqlite")
    repo = RaceLabRepository(db_path=db_path)
    runs = repo.list_runs()
    print(f"Available runs ({len(runs)}):")
    for r in runs:
        rid = r.get("run_id", "?")
        car = r.get("car_name", "?")
        track = r.get("track_name", "?")
        laps = r.get("total_laps", "?")
        print(f"  {rid}")
        print(f"    Car: {car} @ {track} ({laps} laps)")


def export_sample(run_id: str, output: str, max_rows: int = 500) -> None:
    print(f"Reading telemetry for {run_id} ... ", end="", flush=True)
    rows = read_telemetry_rows(run_id)
    print(f"{len(rows)} rows total")

    if max_rows and len(rows) > max_rows:
        # Take rows from the middle of a lap to get varied data
        mid = len(rows) // 2
        start = max(0, mid - max_rows // 2)
        rows = rows[start:start + max_rows]
        print(f"  Subsampled to {len(rows)} rows (offset {start})")

    # Strip raw iRacing columns to keep file small
    raw_prefixes = ("LFSH", "RFSH", "LRSH", "RRSH", "LFtemp", "RFtemp", "LRtemp", "RRtemp",
                    "LFwear", "RFwear", "LRwear", "RRwear", "LFcold", "RFcold", "LRcold", "RRcold",
                    "LFpressure", "RFpressure", "LRpressure", "RRpressure",
                    "LFspeed", "RFspeed", "LRspeed", "RRspeed",
                    "LFrideHeight", "RFrideHeight", "LRrideHeight", "RRrideHeight",
                    "CFSRrideHeight", "SteeringWheelAngle", "SessionTime", "SessionTick",
                    "LapDist", "LapDistPct", "VelocityX", "VelocityY", "VelocityZ",
                    "YawRate", "LatAccel", "LongAccel", "VertAccel", "Yaw", "Pitch", "Roll",
                    "AirDensity", "AirTemp", "TrackTemp", "WindVel", "WindDir",
                    "WaterTemp", "OilTemp", "FuelLevel", "FuelLevelPct", "FuelPress",
                    "RPM", "Gear", "Throttle", "Brake", "Clutch", "Speed", "Alt", "Lat", "Lon",
                    "Engine0_RPM", "EngineWarnings")

    # Keep only raw columns that are actually present
    sample = []
    for row in rows:
        cleaned = {k: v for k, v in row.items() if not any(k.startswith(p) for p in raw_prefixes) or k in (
            "Speed", "SessionTime", "LapDist", "LapDistPct", "Throttle", "Brake",
            "SteeringWheelAngle", "LatAccel", "LongAccel", "AirDensity",
            "LFspeed", "RFspeed", "LRspeed", "RRspeed",
            "CFSRrideHeight", "LFrideHeight", "RFrideHeight", "LRrideHeight", "RRrideHeight",
            "LFSHshockDefl", "RFSHshockDefl", "LRSHshockDefl", "RRSHshockDefl",
            "LFSHshockVel", "RFSHshockVel", "LRSHshockVel", "RRSHshockVel",
            "LFpressure", "RFpressure", "LRpressure", "RRpressure",
            "LFcoldPressure", "RFcoldPressure", "LRcoldPressure", "RRcoldPressure",
            "LFtempL", "LFtempM", "LFtempR", "RFtempL", "RFtempM", "RFtempR",
            "LRtempL", "LRtempM", "LRtempR", "RRtempL", "RRtempM", "RRtempR",
            "LFtempCL", "LFtempCM", "LFtempCR", "RFtempCL", "RFtempCM", "RFtempCR",
            "LRtempCL", "LRtempCM", "LRtempCR", "RRtempCL", "RRtempCM", "RRtempCR",
            "LFwearL", "LFwearM", "LFwearR", "RFwearL", "RFwearM", "RFwearR",
            "LRwearL", "LRwearM", "LRwearR", "RRwearL", "RRwearM", "RRwearR",
            "YawRate", "RPM", "Gear", "Alt", "Lat", "Lon", "VertAccel",
        )}
        sample.append(cleaned)

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample, indent=2, default=str), encoding="utf-8")
    print(f"Exported {len(sample)} rows to {output}")


def main() -> int:
    if len(sys.argv) < 2:
        list_runs()
        return 0

    run_id = sys.argv[1]
    output = "sample_telemetry.json"
    max_rows = 500

    args = iter(sys.argv[2:])
    for arg in args:
        if arg == "--output":
            output = next(args)
        elif arg == "--max-rows":
            max_rows = int(next(args))

    export_sample(run_id, output, max_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
