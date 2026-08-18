"""Local audit assertions for import-pipeline contracts.

Returns:
  0 pass
  2 skip (no fixture)
  1 fail
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _pick_fixture() -> Path | None:
    return next(Path("data/imports/ibt").glob("*.ibt"), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()
    fixture = args.fixture or _pick_fixture()
    if fixture is None:
        print("SKIP: No .ibt fixture found for import-pipeline contract audit.")
        return 2

    cmd = [
        sys.executable,
        "-B",
        "scripts/profile_import_pipeline.py",
        str(fixture),
        "--json",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if proc.returncode != 0:
        print("FAIL: profile_import_pipeline.py failed")
        print(proc.stdout)
        print(proc.stderr)
        return 1

    report = json.loads(proc.stdout)
    failures: list[str] = []
    if report.get("decoder_mode") != "columnar":
        failures.append("default decoder must be columnar")
    if report.get("analysis_engine_mode") != "vectorized":
        failures.append("default analysis engine must be vectorized")
    if bool(report.get("fallback_used")):
        failures.append("fallback_used must be false")
    if int(report.get("duplicate_normalize", -1)) != 0:
        failures.append("duplicate_normalize must be 0")
    if int(report.get("duplicate_cache_read", -1)) != 0:
        failures.append("duplicate_cache_read must be 0")
    if int(report.get("parquet_read_count_during_import", -1)) != 0:
        failures.append("parquet_read_count_during_import must be 0")
    if int(report.get("read_telemetry_rows_count_during_import", -1)) != 0:
        failures.append("read_telemetry_rows_count_during_import must be 0")
    if bool(report.get("trace_blocking")):
        failures.append("trace_blocking must be false")
    if "draft_detection_status" in report:
        failures.append("draft_detection_status must not be present")

    if failures:
        print("FAIL: Import pipeline contract audit failed:")
        for f in failures:
            print(f" - {f}")
        return 1

    print("PASS: Import pipeline contract audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
