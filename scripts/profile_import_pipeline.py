#!/usr/bin/env python
"""
Import pipeline profiler.

Runs ImportService.import_ibt_file() with detailed stage timing.
Prints a sorted timing table and identifies the slowest stages.

Usage:
    python scripts/profile_import_pipeline.py --ibt "C:\\path\\to\\file.ibt"
    python scripts/profile_import_pipeline.py --ibt "C:\\path\\to\\file.ibt" --no-db
"""

import argparse
import sys
import time
from pathlib import Path


def profile(path_str: str, no_db: bool = False) -> None:
    path = Path(path_str)  # sourcery skip: move-assignment-closer
    if not path.exists():
        print(f"File not found: {path}")
        return

    print("=== Import Pipeline Profile ===")
    print(f"  File: {path}")
    print(f"  Size: {path.stat().st_size:,} bytes")
    print(f"  No DB: {no_db}")
    print()

    # Ensure PYTHONPATH is set
    import sys
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from racelab_engine.services.import_service import ImportService
    from racelab_engine.io.ibt_reader import import_ibt
    from racelab_engine.services.import_service import (
        write_telemetry_cache, write_channel_metadata,
        read_telemetry_rows, default_data_dir,
    )
    from racelab_engine.storage.repository import RaceLabRepository
    import logging
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    timings: dict[str, float] = {}

    # Stage 1: Decode IBT
    t0 = time.time()
    result = import_ibt(path)
    timings["1_decode_ibt"] = time.time() - t0
    print(f"  1_decode_ibt:          {timings['1_decode_ibt']:.3f}s")
    if result.overview is None:
        print(f"  FAIL: {result.status.message}")
        return
    run_id = result.overview.run_id
    print(f"  Run ID: {run_id}")
    print(f"  Laps: {len(result.overview.laps)}")
    print(f"  Records: {len(result.records):,}")

    if no_db:
        print(f"\n  Skipping DB stages (--no-db)")
        print("\n=== Profile Summary ===")
        total = sum(timings.values())
        print(f"  Total: {total:.3f}s")
        return

    # Stage 2: Write parquet cache
    t0 = time.time()
    cache_result = write_telemetry_cache(run_id, result.records)
    timings["2_write_parquet_cache"] = time.time() - t0
    print(f"  2_write_parquet_cache:  {timings['2_write_parquet_cache']:.3f}s ({cache_result.format})")

    # Stage 3: Write channel metadata
    t0 = time.time()
    write_channel_metadata(run_id, result.variable_definitions)
    timings["3_write_channel_metadata"] = time.time() - t0
    print(f"  3_write_channel_meta:   {timings['3_write_channel_metadata']:.3f}s")

    # Stage 4: Save run metadata
    t0 = time.time()
    repo = RaceLabRepository()
    repo.save_import(result.overview, result.fingerprint)
    timings["4_save_run_metadata"] = time.time() - t0
    print(f"  4_save_run_metadata:    {timings['4_save_run_metadata']:.3f}s")

    # Stage 5: Segment building
    t0 = time.time()
    try:
        from racelab_engine.analysis.segments import build_fixed_pct_segments
        from racelab_engine.models.segment import SegmentSummary as ModelSegment
        rows = read_telemetry_rows(run_id)
        if raw_segments := build_fixed_pct_segments(rows, run_id=run_id):
            model_segments = [ModelSegment(**seg.model_dump()) for seg in raw_segments]
            repo.save_segments(run_id, model_segments)
            print(f"    Segments saved: {len(model_segments)}")
    except Exception as exc:
        print(f"    Segment error: {exc}")
    timings["5_segment_building"] = time.time() - t0
    print(f"  5_segment_building:     {timings['5_segment_building']:.3f}s")

    # Stage 6: Draft detection
    t0 = time.time()
    try:
        from racelab_engine.analysis.draft_detection import classify_draft_status
        rows = read_telemetry_rows(run_id)
        tags_updated = False
        for lap in result.overview.laps:
            if not lap.is_useful:
                continue
            draft = classify_draft_status(rows, lap_number=lap.lap_number)
            if draft.status.value != "UNKNOWN_DRAFT_STATUS":
                tag = draft.status.value
                if not lap.classification_tags:
                    lap.classification_tags = []
                if tag not in lap.classification_tags:
                    lap.classification_tags.append(tag)
                    tags_updated = True
        if tags_updated:
            repo.save_import(result.overview, result.fingerprint)
            print("    Draft tags updated")
    except Exception as exc:
        print(f"    Draft detection error: {exc}")
    timings["6_draft_detection"] = time.time() - t0
    print(f"  6_draft_detection:      {timings['6_draft_detection']:.3f}s")

    # Summary
    print(f"\n=== Profile Summary ===")
    total = sum(timings.values())
    print(f"  Total: {total:.3f}s")
    print(f"\n  Stages sorted by duration (slowest first):")
    for name, dur in sorted(timings.items(), key=lambda x: -x[1]):
        pct = (dur / total) * 100 if total > 0 else 0
        print(f"    {name}: {dur:.3f}s ({pct:.1f}%)")

    slowest = max(timings, key=lambda k: timings[k])  # type: ignore[arg-type]
    print(f"\n  Slowest stage: {slowest} ({timings[slowest]:.3f}s)")
    print(f"  Run ID: {run_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile the import pipeline")
    parser.add_argument("--ibt", required=True, help="Path to .ibt file")
    parser.add_argument("--no-db", action="store_true", help="Skip DB stages (decode only)")
    args = parser.parse_args()
    profile(args.ibt, no_db=args.no_db)


if __name__ == "__main__":
    main()
