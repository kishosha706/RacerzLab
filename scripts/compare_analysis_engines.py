#!/usr/bin/env python3
"""Compare row-by-row and vectorized analysis engines on a sample data file.

Usage
-----
    python scripts/compare_analysis_engines.py path/to/sample.json
    python scripts/compare_analysis_engines.py path/to/sample.jsonl

The input file should contain an array of telemetry row dicts (JSON) or
one dict per line (JSONL).  Each dict must have at least ``Speed`` and
``SessionTime`` keys.

Exit code:
    0 — comparison passed (all channels match within tolerance)
    1 — comparison failed (mismatches found or input error)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from racelab_engine.analysis.vectorized_channels import (
    compare_row_vs_vectorized,
    get_analysis_engine_mode,
)


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Load telemetry rows from a JSON or JSONL file."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Try JSON array first
    if text.startswith("["):
        data = json.loads(text)
        if isinstance(data, list):
            return data

    # Try JSONL (one dict per line)
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def print_report(report: dict[str, Any]) -> None:
    """Print a human-readable comparison report."""
    print("=" * 60)
    print("  Analysis Engine Comparison Report")
    print("=" * 60)
    print(f"  Rows compared:       {report['row_count']}")
    print(f"  Channels compared:   {len(report['compared_channels'])}")
    print(f"  Tolerance:           {report['tolerance']}")
    print(f"  Pass/Fail:           {'PASS' if report['pass_fail'] else 'FAIL'}")
    print()

    if report["missing_in_row"]:
        print(f"  Missing in row path: {', '.join(report['missing_in_row'])}")
    if report["missing_in_vector"]:
        print(f"  Missing in vector:   {', '.join(report['missing_in_vector'])}")
    if report["early_window_exemptions"]:
        print(f"  Early-window exemptions (shock rolling): {report['early_window_exemptions']}")
    print()

    mismatches = {ch: cnt for ch, cnt in report["mismatch_count_by_channel"].items() if cnt > 0}
    if mismatches:
        header = f"  {'Channel':<40s} {'Mismatches':<12s} {'Max |diff|':<12s}"
        print(header)
        print("  " + "-" * 40 + " " + "-" * 12 + " " + "-" * 12)
        for ch in sorted(mismatches):
            max_diff = report["max_abs_diff_by_channel"].get(ch, 0.0)
            diff_str = f"{max_diff:.2e}" if isinstance(max_diff, float) else str(max_diff)
            print(f"  {ch:<40s} {mismatches[ch]:<12d} {diff_str:<12s}")
    else:
        print("  All channels match within tolerance.")
    print("=" * 60)


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} path/to/sample.json[l]", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    print(f"Loading rows from {path} ... ", end="", flush=True)
    t0 = time.perf_counter()
    rows = load_rows(path)
    t1 = time.perf_counter()
    print(f"{len(rows)} rows loaded in {t1 - t0:.3f}s")

    if not rows:
        print("No rows found in input file.", file=sys.stderr)
        return 1

    # Check current engine mode
    mode = get_analysis_engine_mode()
    print(f"Current engine mode: {mode} (env: RACELAB_ANALYSIS_ENGINE)")
    print()

    # Run comparison
    print("Running comparison ... ", end="", flush=True)
    t0 = time.perf_counter()
    report = compare_row_vs_vectorized(rows)
    t1 = time.perf_counter()
    print(f"done in {t1 - t0:.3f}s")
    print()

    print_report(report)

    return 0 if report["pass_fail"] else 1


if __name__ == "__main__":
    sys.exit(main())
