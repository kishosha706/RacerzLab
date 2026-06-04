from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from racelab_engine.analysis.shock_reader import build_shock_reader_response
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
    parser = argparse.ArgumentParser(description="Query guarded shock histogram recommendations for a run.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--lap", type=int)
    parser.add_argument("--lap-window")
    parser.add_argument("--phase")
    parser.add_argument("--boundary-in-s", type=float, default=1.0)
    parser.add_argument("--include-debug", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo = RaceLabRepository()
    if repo.get_session(args.run_id) is None:
        raise SystemExit(f"Run not found: {args.run_id}")

    response = build_shock_reader_response(
        args.run_id,
        lap=args.lap,
        lap_window=_parse_lap_window(args.lap_window),
        phase=args.phase,
        boundary_in_s=args.boundary_in_s,
        include_debug=args.include_debug,
        setup_snapshot=repo.get_setup_snapshot(args.run_id),
    )
    payload = response.model_dump(mode="json", exclude_none=True)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Shock Reader: {response.run_id}")
    print(f"Window: {response.lap_window or 'whole run'} | Phase: {response.phase or 'not selected'}")
    for corner in response.corners:
        print(
            f"- {corner.corner}: {corner.pattern} "
            f"(RHi {corner.rebound_hi_pct:.1f}, RLo {corner.rebound_lo_pct:.1f}, "
            f"BLo {corner.bump_lo_pct:.1f}, BHi {corner.bump_hi_pct:.1f})"
        )
        for rec in corner.setting_recommendations:
            if rec.direction in {"hold", "needs_more_evidence"}:
                badge = "hold" if rec.direction == "hold" else "need data"
            elif rec.direction == "blocked":
                badge = "limit"
            elif rec.delta is not None and rec.suggested_value is not None:
                badge = f"{rec.delta:+d} -> {rec.suggested_value}"
            elif rec.blocked_reason == "setup value missing":
                badge = "need setup"
            else:
                badge = rec.direction
            print(f"  {rec.display_label}: {badge} | {rec.reason_short}")
    if response.recommendations:
        print("Compatibility recommendation:")
        for rec in response.recommendations:
            value_text = ""
            if rec.current_value is not None:
                if rec.suggested_value is not None:
                    value_text = f" {rec.current_value} -> {rec.suggested_value}"
                elif rec.blocked_by_limit:
                    value_text = f" blocked at {rec.current_value}"
            print(f"- {rec.corner_scope} {rec.display_setting}: {rec.semantic_direction}{value_text}")
            print(f"  Goal: {rec.goal}")
            print(f"  Trade-off: {rec.tradeoff}")
    else:
        print("No guarded shock recommendation.")
    for warning in response.warnings:
        print(f"Warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
