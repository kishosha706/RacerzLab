"""Profile the full .ibt import pipeline with per-stage timing."""
from __future__ import annotations
import time, sys, os, json
from pathlib import Path

def _read_bytes(path):
    with open(path, "rb") as f:
        return f.read()

def profile(ibt_path: str, engine: str | None = None):
    if engine:
        os.environ["RACELAB_ANALYSIS_ENGINE"] = engine
    else:
        os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)

    stages = {}

    # Stage 1: file read
    t0 = time.perf_counter()
    data = _read_bytes(ibt_path)
    stages["file_read"] = time.perf_counter() - t0

    # Stage 2: header parse
    from racelab_engine.io.ibt_reader import _parse_header, _parse_variable_definitions
    t0 = time.perf_counter()
    header = _parse_header(data, len(data))
    stages["header_parse"] = time.perf_counter() - t0

    # Stage 3: variable definitions
    t0 = time.perf_counter()
    definitions = _parse_variable_definitions(data, header)
    available = {d.name for d in definitions}
    stages["var_defs"] = time.perf_counter() - t0

    # Stage 4: raw row extraction
    from racelab_engine.io.ibt_reader import _read_records_from_data, CORE_REQUIRED_CHANNELS, TARGET_CHANNELS
    t0 = time.perf_counter()
    target_vars = [c for c in TARGET_CHANNELS if c in available]
    raw_rows = _read_records_from_data(data, header, definitions, variables=target_vars)
    stages["raw_rows"] = time.perf_counter() - t0

    # Stage 5: normalization (dispatched)
    from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows
    t0 = time.perf_counter()
    normalized = normalize_telemetry_rows(raw_rows)
    stages["normalize"] = time.perf_counter() - t0

    missing = [c for c in CORE_REQUIRED_CHANNELS if c not in available]

    result = {
        "file": str(Path(ibt_path).name),
        "engine": engine or "default",
        "rows": len(raw_rows),
        "raw_channels": len(available),
        "normalized_cols": len(normalized[0]) if normalized else 0,
        "missing_core": missing,
        "stages": {k: round(v, 4) for k, v in stages.items()},
        "total": round(sum(stages.values()), 4),
    }

    # Also time DataFrame construction alone
    t0 = time.perf_counter()
    import polars as pl
    df = pl.from_dicts(raw_rows, infer_schema_length=None)
    result["df_construction"] = round(time.perf_counter() - t0, 4)

    # Also time row-path normalize alone for comparison
    if engine != "row":
        os.environ["RACELAB_ANALYSIS_ENGINE"] = "row"
        from racelab_engine.analysis.calculated_channels import normalize_telemetry_rows as row_normalize
        t0 = time.perf_counter()
        row_normalize(raw_rows)
        result["row_normalize_time"] = round(time.perf_counter() - t0, 4)
        os.environ.pop("RACELAB_ANALYSIS_ENGINE", None)

    return result

if __name__ == "__main__":
    ibt = sys.argv[1] if len(sys.argv) > 1 else None
    engine = sys.argv[2] if len(sys.argv) > 2 else None
    if not ibt:
        # Find first available .ibt
        imports = Path("data/imports/ibt")
        ibt = str(next(imports.glob("*.ibt"), None))
        if not ibt:
            print("No .ibt found")
            sys.exit(1)
    
    r = profile(ibt, engine)
    print(json.dumps(r, indent=2))
    print(f"\nSlowest stages:")
    for s, t in sorted(r["stages"].items(), key=lambda x: -x[1]):
        bar = "#" * int(t / r["total"] * 40)
        print(f"  {s:20s} {t:8.3f}s  {bar}")
