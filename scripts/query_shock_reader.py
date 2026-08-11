from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.analysis.shock_reader import build_shock_reader_response
from racelab_engine.analysis.ride_height_calibration import is_next_gen_car_path
from racelab_engine.storage.repository import RaceLabRepository


def _parse_lap_window(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.replace(":", "-").replace(",", "-").split("-") if part.strip()]
    if len(parts) != 2:
        raise SystemExit("--lap-window must look like 3-8")
    start, end = int(parts[0]), int(parts[1])
    if start <= 0 or end < start:
        raise SystemExit("--lap-window must be a positive ascending range")
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description="Query guarded shock histogram observations for a run.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--lap", type=int)
    parser.add_argument("--lap-window")
    parser.add_argument("--phase")
    parser.add_argument("--zone-start-pct", type=float)
    parser.add_argument("--zone-end-pct", type=float)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo = RaceLabRepository()
    overview = repo.get_overview(args.run_id)
    if overview is None:
        raise SystemExit(f"Run not found: {args.run_id}")

    next_gen = is_next_gen_car_path(overview.session.car_path)
    boundary_basis = (
        "Official iRacing Next Gen guidance: approximate 1.5 in/s high-speed transition; sensitivity plus/minus 25%."
        if next_gen
        else "Descriptive 1.0 in/s boundary only; no verified car-specific high-speed transition is available."
    )
    response = build_shock_reader_response(
        args.run_id,
        lap=args.lap,
        lap_window=_parse_lap_window(args.lap_window),
        phase=args.phase,
        zone_start_pct=args.zone_start_pct,
        zone_end_pct=args.zone_end_pct,
        boundary_in_s=1.5 if next_gen else 1.0,
        boundary_basis=boundary_basis,
        setup_snapshot=repo.get_setup_snapshot(args.run_id),
        lap_summaries=overview.laps,
    )
    payload = response.model_dump(mode="json", exclude_none=True)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Shock Reader: {response.run_id}")
    zone = (
        f"{response.zone_start_pct:.1f}-{response.zone_end_pct:.1f}%"
        if response.zone_start_pct is not None and response.zone_end_pct is not None
        else "not selected"
    )
    print(f"Window: {response.lap_window or 'whole run'} | Phase: {response.phase or 'not selected'} | Zone: {zone}")
    print(f"Boundary: {response.boundary_in_s:.2f} in/s | {response.boundary_basis}")
    for corner in response.corners:
        print(
            f"- {corner.corner}: {corner.pattern} "
            f"(RHi {corner.rebound_hi_pct:.1f}, RLo {corner.rebound_lo_pct:.1f}, "
            f"BLo {corner.bump_lo_pct:.1f}, BHi {corner.bump_hi_pct:.1f})"
        )
    print("Setup authority: withheld (P19 controlled workflow required).")
    print("Measurement: repeat the same eligible track region with the setup unchanged.")
    for warning in response.warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
