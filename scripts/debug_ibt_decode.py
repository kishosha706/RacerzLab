#!/usr/bin/env python
"""
Standalone IBT decoder diagnostic script.

Tests whether a given .ibt file can be read, parsed, and decoded
by the RaceLab IBT decoder, without importing into the database.

Usage:
    python scripts/debug_ibt_decode.py --ibt "C:\\path\\to\\file.ibt"
    python scripts/debug_ibt_decode.py --ibt "C:\\path\\to\\file.ibt" --import
"""

import argparse
import sys
import time
from pathlib import Path


def diagnose(path_str: str, do_import: bool = False) -> None:
    path = Path(path_str)
    print("=== IBT Decode Diagnostic ===")
    print(f"  Path: {path}")
    print(f"  Exists: {path.exists()}")
    if not path.exists():
        print("  FAIL: File does not exist.")
        return

    size = path.stat().st_size
    print(f"  Size: {size:,} bytes ({size / 1024 / 1024:.1f} MB)")
    print(f"  Suffix: {path.suffix.lower()}")

    if path.suffix.lower() != ".ibt":
        print("  FAIL: File does not have .ibt extension.")
        return

    try:  # sourcery skip: extract-duplicate-code
        with open(path, "rb") as f:
            first_bytes = f.read(16)
        print(f"  First 16 bytes (hex): {first_bytes.hex()}")
        # iRacing IBT files start with a version int (little-endian 4 bytes)
        import struct
        version = struct.unpack_from("<i", first_bytes, 0)[0]
        print(f"  Header version field: {version}")
        if version <= 0:
            print("  WARN: Version <= 0, may not be a valid IBT file.")
    except OSError as e:
        print(f"  FAIL: Could not read file: {e}")
        return

    # Try decoder stages
    try:
        from racelab_engine.io.ibt_reader import (
            read_header,
            read_variable_definitions,
            read_session_yaml,
            read_normalized_records,
            import_ibt,
        )
    except ImportError as e:
        print(f"  FAIL: Could not import decoder: {e}")
        print("  Make sure PYTHONPATH includes the racelab-garage directory.")
        return

    # Stage 1: Header
    print()
    t0 = time.time()
    try:
        header = read_header(path)
        t1 = time.time()
        print(f"=== Stage 1: Header ({t1-t0:.3f}s) ===")
        print(f"  Version: {header.version}")
        print(f"  Tick Rate: {header.telemetry_rate_hz} Hz")
        print(f"  Variables: {header.variable_count}")
        print(f"  Records: {header.record_count:,}")
        print(f"  Duration: {header.duration_seconds:.1f}s" if header.duration_seconds else "  Duration: N/A")
        print(f"  Session Info Offset: {header.session_info_offset}")
        print(f"  Session Info Length: {header.session_info_length}")
        print(f"  Data Offset: {header.data_offset}")
        print(f"  Record Length: {header.record_length}")
    except Exception as e:
        print(f"  FAIL: Header parse error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Stage 2: Variable definitions
    t0 = time.time()
    try:
        defs = read_variable_definitions(path)
        t1 = time.time()
        print(f"\n=== Stage 2: Variable Definitions ({t1-t0:.3f}s) ===")
        print(f"  Count: {len(defs)}")
        # Show first 5
        for d in defs[:5]:
            print(f"    {d.name}: type={d.data_type} offset={d.offset} count={d.count}")
        if len(defs) > 5:
            print(f"    ... and {len(defs) - 5} more")
    except Exception as e:
        print(f"  FAIL: Variable definitions error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Stage 3: Session YAML
    t0 = time.time()
    try:
        yaml_text = read_session_yaml(path)
        t1 = time.time()
        print(f"\n=== Stage 3: Session YAML ({t1-t0:.3f}s) ===")
        print(f"  Length: {len(yaml_text):,} chars")
        # Extract car/track from YAML
        import re
        car_match = re.search(r'CarName:\s*(.+)', yaml_text)
        track_match = re.search(r'TrackDisplayName:\s*(.+)', yaml_text)
        track_id_match = re.search(r'TrackID:\s*(.+)', yaml_text)
        print(f"  Car: {car_match.group(1).strip() if car_match else 'NOT FOUND'}")
        print(f"  Track: {track_match.group(1).strip() if track_match else 'NOT FOUND'}")
        print(f"  Track ID: {track_id_match.group(1).strip() if track_id_match else 'NOT FOUND'}")
    except Exception as e:
        print(f"  FAIL: Session YAML error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Stage 4: Normalized records
    t0 = time.time()
    try:
        rows, missing = read_normalized_records(path)
        t1 = time.time()
        print(f"\n=== Stage 4: Normalized Records ({t1-t0:.3f}s) ===")
        print(f"  Rows: {len(rows):,}")
        print(f"  Missing channels: {missing or 'None'}")
        if rows:
            first = rows[0]
            print(f"  First row keys: {list(first.keys())[:10]}...")
            print(f"  First row lap: {first.get('lap')}")
            print(f"  First row speed_mph: {first.get('speed_mph')}")
            print(f"  First row session_time: {first.get('session_time')}")
    except Exception as e:
        print(f"  FAIL: Normalized records error: {e}")
        import traceback
        traceback.print_exc()
        return

    # Stage 5: Full import (optional)
    if do_import:
        t0 = time.time()
        try:
            result = import_ibt(path)
            t1 = time.time()
            print(f"\n=== Stage 5: Full import_ibt() ({t1-t0:.3f}s) ===")
            print(f"  Status: {result.status.status}")
            print(f"  Message: {result.status.message[:200]}")
            print(f"  Run ID: {result.overview.run_id if result.overview else 'N/A'}")
            print(f"  Laps: {len(result.overview.laps) if result.overview else 'N/A'}")
            print(f"  Events: {len(result.overview.events) if result.overview else 'N/A'}")
            print(f"  Warnings: {result.overview.warnings if result.overview else 'N/A'}")
        except Exception as e:
            print(f"  FAIL: Full import error: {e}")
            import traceback
            traceback.print_exc()
            return
    else:
        print(f"\n=== Stage 5: Full import (skipped) ===")
        print("  Pass --import to run full import_ibt()")

    print(f"\n=== Diagnostic Complete ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose IBT file decoding")
    parser.add_argument("--ibt", required=True, help="Path to .ibt file")
    parser.add_argument("--import", action="store_true", dest="do_import",
                        help="Also run full import_ibt() (does not write to DB)")
    args = parser.parse_args()
    diagnose(args.ibt, do_import=args.do_import)


if __name__ == "__main__":
    main()
