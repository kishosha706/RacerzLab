from __future__ import annotations

import argparse
import json
from pathlib import Path

from racelab_engine.reports.markdown_report import generate_markdown_report
from racelab_engine.services.import_service import ImportService, build_trace_payload
from racelab_engine.storage.db import initialize_database
from racelab_engine.storage.repository import RaceLabRepository


def _cmd_init_db(args: argparse.Namespace) -> int:
    connection = initialize_database(args.db)
    connection.close()
    print(f"Initialized RaceLab Garage database: {args.db or 'data/racelab.sqlite'}")
    return 0


def _cmd_import_ibt(args: argparse.Namespace) -> int:
    result, cache = ImportService(db_path=args.db, data_dir=args.data_dir).import_ibt_file(args.path)
    print(result.status.message)
    if result.overview is None:
        print(result.status.model_dump_json(indent=2))
        return 1

    overview = result.overview
    best_lap = overview.best_useful_lap
    print(f"Run ID: {overview.run_id}")
    print(f"Track: {overview.session.track_display_name or overview.session.track_name}")
    print(f"Car: {overview.session.car_name}")
    if best_lap is not None:
        print(f"Best useful lap: Lap {best_lap.lap_number} ({best_lap.lap_time:.3f} sec)")
    if cache is not None:
        print(f"Telemetry cache: {cache.path} ({cache.format})")
    return 0


def _cmd_list_runs(args: argparse.Namespace) -> int:
    for run in RaceLabRepository(args.db).list_runs():
        print(json.dumps(run, default=str))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    overview = RaceLabRepository(args.db).get_overview(args.run_id)
    if overview is None:
        print(f"Run not found: {args.run_id}")
        return 1
    report = generate_markdown_report(overview)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
        print(f"Wrote report: {output}")
    else:
        print(report)
    return 0


def _cmd_trace(args: argparse.Namespace) -> int:
    channels = [item.strip() for item in args.channels.split(",") if item.strip()] if args.channels else None
    payload = build_trace_payload(
        args.run_id,
        lap=args.lap,
        channels=channels,
        downsample=args.downsample,
        data_dir=args.data_dir,
    )
    print(json.dumps(payload, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="racelab", description="RaceLab Garage local-first tools")
    parser.add_argument("--db", default=None, help="SQLite database path. Defaults to data/racelab.sqlite.")
    parser.add_argument("--data-dir", default=None, help="RaceLab data directory. Defaults to data/.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Initialize the SQLite schema.")
    init_db.set_defaults(func=_cmd_init_db)

    import_ibt = subparsers.add_parser("import-ibt", help="Import and persist an iRacing .ibt file.")
    import_ibt.add_argument("path")
    import_ibt.set_defaults(func=_cmd_import_ibt)

    list_runs = subparsers.add_parser("list-runs", help="List persisted runs.")
    list_runs.set_defaults(func=_cmd_list_runs)

    report = subparsers.add_parser("report", help="Generate a Markdown report for a run.")
    report.add_argument("run_id")
    report.add_argument("--output", default=None)
    report.set_defaults(func=_cmd_report)

    trace = subparsers.add_parser("trace", help="Print lightweight trace JSON for a run.")
    trace.add_argument("run_id")
    trace.add_argument("--lap", type=int, default=None)
    trace.add_argument("--channels", default="speed_mph,rpm,throttle_pct,brake_pct,cfsr_height_mm")
    trace.add_argument("--downsample", type=int, default=5)
    trace.set_defaults(func=_cmd_trace)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
