"""Profile import pipeline with stable schema, counters, and baseline comparison."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_BASELINE = Path("data/perf_baselines/local_import_baseline.json")


def _pick_ibt() -> Path | None:
    imports = Path("data/imports/ibt")
    return next(imports.glob("*.ibt"), None)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _mb(path: Path) -> float:
    return round(path.stat().st_size / (1024 * 1024), 3)


def profile_import(ibt_path: Path) -> dict[str, Any]:
    import polars as pl
    from racelab_engine.analysis import vectorized_channels as vec_mod
    from racelab_engine.analysis import calculated_channels as row_mod
    from racelab_engine.io import ibt_reader as ibt_mod
    from racelab_engine.services import import_service as svc_mod
    from racelab_engine.services.import_service import ImportService

    counters: dict[str, Any] = {
        "fallback_used": False,
        "row_decoder_used": 0,
        "row_normalize_used": 0,
        "vectorized_normalize_used": 0,
        "duplicate_normalize": 0,
        "duplicate_cache_read": 0,
        "parquet_read_count_during_import": 0,
        "read_telemetry_rows_count_during_import": 0,
        "trace_blocking": False,
    }
    timings: dict[str, float] = {
        "file_read_s": 0.0,
        "header_parse_s": 0.0,
        "var_defs_s": 0.0,
        "session_yaml_s": 0.0,
        "decode_s": 0.0,
        "normalize_s": 0.0,
        "overview_build_s": 0.0,
        "cache_write_s": 0.0,
        "channel_metadata_write_s": 0.0,
        "segment_build_s": 0.0,
        "service_import_total_s": 0.0,
        "total_import_s": 0.0,
        "decode_normalize_overview_s": 0.0,
    }

    original = {
        "read_records_columnar": ibt_mod._read_records_columnar,
        "read_records_row": ibt_mod._read_records_from_data,
        "row_norm_mod": row_mod.normalize_telemetry_rows,
        "row_norm_ibt": ibt_mod.normalize_telemetry_rows,
        "vec_norm": vec_mod.normalize_telemetry_frame,
        "overview": ibt_mod._build_overview,
        "read_telemetry_rows": svc_mod.read_telemetry_rows,
        "read_parquet": pl.read_parquet,
        "trace_payload": svc_mod.build_trace_payload,
    }

    def wrap_col(*args, **kwargs):
        t0 = time.perf_counter()
        out = original["read_records_columnar"](*args, **kwargs)
        timings["decode_s"] += time.perf_counter() - t0
        return out

    def wrap_row_dec(*args, **kwargs):
        counters["row_decoder_used"] += 1
        t0 = time.perf_counter()
        out = original["read_records_row"](*args, **kwargs)
        timings["decode_s"] += time.perf_counter() - t0
        return out

    def wrap_row_norm(*args, **kwargs):
        counters["row_normalize_used"] += 1
        t0 = time.perf_counter()
        out = original["row_norm_mod"](*args, **kwargs)
        timings["normalize_s"] += time.perf_counter() - t0
        return out

    def wrap_vec_norm(*args, **kwargs):
        counters["vectorized_normalize_used"] += 1
        t0 = time.perf_counter()
        out = original["vec_norm"](*args, **kwargs)
        timings["normalize_s"] += time.perf_counter() - t0
        return out

    def wrap_overview(*args, **kwargs):
        t0 = time.perf_counter()
        out = original["overview"](*args, **kwargs)
        timings["overview_build_s"] += time.perf_counter() - t0
        return out

    def wrap_read_telemetry_rows(*args, **kwargs):
        counters["read_telemetry_rows_count_during_import"] += 1
        return original["read_telemetry_rows"](*args, **kwargs)

    def wrap_read_parquet(*args, **kwargs):
        counters["parquet_read_count_during_import"] += 1
        return original["read_parquet"](*args, **kwargs)

    def wrap_trace_payload(*args, **kwargs):
        counters["trace_blocking"] = True
        return original["trace_payload"](*args, **kwargs)

    ibt_mod._read_records_columnar = wrap_col
    ibt_mod._read_records_from_data = wrap_row_dec
    row_mod.normalize_telemetry_rows = wrap_row_norm
    ibt_mod.normalize_telemetry_rows = wrap_row_norm
    vec_mod.normalize_telemetry_frame = wrap_vec_norm
    ibt_mod._build_overview = wrap_overview
    svc_mod.read_telemetry_rows = wrap_read_telemetry_rows
    pl.read_parquet = wrap_read_parquet
    svc_mod.build_trace_payload = wrap_trace_payload
    prev_subprofile = os.environ.get("RACELAB_IMPORT_SUBPROFILE")
    os.environ["RACELAB_IMPORT_SUBPROFILE"] = "1"

    try:
        t0 = time.perf_counter()
        data = ibt_mod._read_bytes(ibt_path)
        timings["file_read_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        header = ibt_mod._parse_header(data, len(data))
        timings["header_parse_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        ibt_mod._parse_variable_definitions(data, header)
        timings["var_defs_s"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        ibt_mod.read_session_yaml(ibt_path)
        timings["session_yaml_s"] = time.perf_counter() - t0

        service = ImportService()
        t0 = time.perf_counter()
        result, _ = service.import_ibt_file(ibt_path)
        timings["service_import_total_s"] = time.perf_counter() - t0
        timings["total_import_s"] = timings["service_import_total_s"]
        timings["decode_normalize_overview_s"] = timings["decode_s"] + timings["normalize_s"] + timings["overview_build_s"]
        svc_timings = dict(getattr(service, "last_import_timings", {}) or {})
        timings["cache_write_s"] = float(svc_timings.get("write_parquet_cache", 0.0))
        timings["channel_metadata_write_s"] = float(svc_timings.get("write_channel_metadata", 0.0))
        timings["segment_build_s"] = float(svc_timings.get("segment_building", 0.0))
        sub_timings = {
            k: float(v)
            for k, v in svc_timings.items()
            if isinstance(v, (int, float))
            and (k.startswith("decode_sub_") or k.startswith("cache_") or k.startswith("segment_sub_"))
        }
        normalized_frame_available = float(sub_timings.get("decode_sub_normalized_frame_available", 0.0)) > 0.0
        rows_materialized = float(sub_timings.get("decode_sub_rows_materialized_during_import", 0.0)) > 0.0
        frame_to_rows_count = int(float(sub_timings.get("decode_sub_frame_to_rows_count", 0.0)))
        frame_to_rows_s = float(sub_timings.get("decode_sub_frame_to_rows_s", 0.0))
        frame_to_rows_reason = str(svc_timings.get("decode_sub_frame_to_rows_reason", "none"))
        cache_write_from_frame = float(sub_timings.get("cache_write_from_frame", 0.0)) > 0.0
        overview_consumers_frame_native = float(sub_timings.get("decode_sub_overview_consumers_frame_native", 0.0)) > 0.0
        overview_legacy_consumers_remaining = str(svc_timings.get("decode_sub_overview_legacy_consumers_remaining", "unknown"))

        counters["fallback_used"] = counters["row_decoder_used"] > 0 and (os.environ.get("RACELAB_IBT_DECODER", "").strip().lower() != "row")
        total_norm = counters["row_normalize_used"] + counters["vectorized_normalize_used"]
        counters["duplicate_normalize"] = max(0, total_norm - 1)
        counters["duplicate_cache_read"] = max(0, counters["read_telemetry_rows_count_during_import"] - 0)
        notes: list[str] = []
        if timings["segment_build_s"] == 0.0:
            notes.append("segment_build_s: stage did not run or had no measurable work for this fixture.")
        if not notes:
            notes.append("service sub-stage timings sourced directly from ImportService.last_import_timings.")

        return {
            "fixture_path": str(ibt_path),
            "fixture_size_mb": _mb(ibt_path),
            "row_count": len(result.records) if result.records else int(getattr(result.header, "record_count", 0) or 0),
            "decoder_mode": os.environ.get("RACELAB_IBT_DECODER", "").strip().lower() or "columnar",
            "analysis_engine_mode": vec_mod.get_analysis_engine_mode(),
            **counters,
            "timings": {k: round(v, 4) for k, v in timings.items()},
            "sub_stage_timings": {k: round(v, 4) for k, v in sorted(sub_timings.items())},
            "normalized_frame_available": normalized_frame_available,
            "rows_materialized_during_import": rows_materialized,
            "frame_to_rows_count": frame_to_rows_count,
            "frame_to_rows_s": round(frame_to_rows_s, 4),
            "frame_to_rows_reason": frame_to_rows_reason,
            "cache_write_from_frame": cache_write_from_frame,
            "overview_consumers_frame_native": overview_consumers_frame_native,
            "overview_legacy_consumers_remaining": overview_legacy_consumers_remaining,
            "notes": notes,
        }
    finally:
        if prev_subprofile is None:
            os.environ.pop("RACELAB_IMPORT_SUBPROFILE", None)
        else:
            os.environ["RACELAB_IMPORT_SUBPROFILE"] = prev_subprofile
        ibt_mod._read_records_columnar = original["read_records_columnar"]
        ibt_mod._read_records_from_data = original["read_records_row"]
        row_mod.normalize_telemetry_rows = original["row_norm_mod"]
        ibt_mod.normalize_telemetry_rows = original["row_norm_ibt"]
        vec_mod.normalize_telemetry_frame = original["vec_norm"]
        ibt_mod._build_overview = original["overview"]
        svc_mod.read_telemetry_rows = original["read_telemetry_rows"]
        pl.read_parquet = original["read_parquet"]
        svc_mod.build_trace_payload = original["trace_payload"]


def compare_to_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    deltas: dict[str, float] = {}
    cur_t = current.get("timings", {})
    base_t = baseline.get("timings", {})
    for key, cur in cur_t.items():
        base = base_t.get(key)
        if isinstance(cur, (int, float)) and isinstance(base, (int, float)) and base > 0:
            deltas[key] = ((cur - base) / base) * 100.0
    return deltas


def warnings_for(report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if report["decoder_mode"] != "columnar":
        warnings.append("Decoder is not columnar on this run.")
    if report["analysis_engine_mode"] != "vectorized":
        warnings.append("Analysis engine is not vectorized on this run.")
    if report["fallback_used"]:
        warnings.append("Fallback path used.")
    if report["duplicate_normalize"] > 0:
        warnings.append("duplicate_normalize > 0")
    if report["duplicate_cache_read"] > 0:
        warnings.append("duplicate_cache_read > 0")
    if report["parquet_read_count_during_import"] > 0:
        warnings.append("parquet_read_count_during_import > 0")
    if report["trace_blocking"]:
        warnings.append("trace_blocking == true")
    return warnings


def print_table(report: dict[str, Any], deltas: dict[str, float] | None = None) -> None:
    print("\nImport Pipeline Profile")
    print(f"fixture: {report['fixture_path']}")
    print(f"size_mb: {report['fixture_size_mb']}  rows: {report['row_count']}")
    print(f"decoder: {report['decoder_mode']}  engine: {report['analysis_engine_mode']}")
    print("counters:")
    for k in (
        "fallback_used",
        "row_decoder_used",
        "row_normalize_used",
        "duplicate_normalize",
        "duplicate_cache_read",
        "parquet_read_count_during_import",
        "read_telemetry_rows_count_during_import",
        "trace_blocking",
    ):
        print(f"  {k:40s} {report[k]}")
    print("timings (s):")
    for k, v in report["timings"].items():
        suffix = ""
        if deltas and k in deltas:
            suffix = f"  ({deltas[k]:+6.2f}%)"
        print(f"  {k:40s} {v:8.4f}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", nargs="?", help="Path to .ibt fixture")
    parser.add_argument("--fixture", dest="fixture_opt", help="Path to .ibt fixture (named option)")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    parser.add_argument("--write-baseline", action="store_true", help="Write current run as baseline")
    parser.add_argument("--baseline-file", default=str(DEFAULT_BASELINE), help="Baseline JSON path")
    args = parser.parse_args()

    fixture_arg = args.fixture_opt or args.fixture
    fixture = Path(fixture_arg) if fixture_arg else _pick_ibt()
    if fixture is None or not fixture.exists():
        msg = {"status": "skip", "reason": "No .ibt fixture found."}
        print(json.dumps(msg, indent=2))
        return 0

    report = profile_import(fixture)
    baseline_path = Path(args.baseline_file)
    baseline = _read_json(baseline_path)
    deltas = compare_to_baseline(report, baseline) if baseline else None
    warns = warnings_for(report)

    payload = {
        **report,
        "baseline_file": str(baseline_path),
        "baseline_present": baseline is not None,
        "baseline_deltas_pct": deltas or {},
        "warnings": warns,
    }

    if args.write_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        payload["baseline_write"] = f"Wrote baseline to {baseline_path}"
    elif baseline is None:
        payload["baseline_write"] = "No baseline found; writing current run as candidate baseline requires --write-baseline."

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print_table(payload, deltas)
        print("\nWarnings:")
        if warns:
            for w in warns:
                print(f"  - {w}")
        else:
            print("  none")
        print("\nJSON:")
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

