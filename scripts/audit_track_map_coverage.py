from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from racelab_engine.analysis.track_matching import (  # type: ignore  # noqa: E402
    infer_layout_key,
    match_track_map_for_run,
    rank_track_map_matches,
    suggest_track_map_display_name,
)
from racelab_engine.services.track_map_service import get_track_map  # type: ignore  # noqa: E402


LOW_POINT_COUNT_THRESHOLD = 100
SHORT_DISTANCE_MILES_THRESHOLD = 0.25
LONG_DISTANCE_MILES_THRESHOLD = 10.0
EXPECTED_WARNING_SNIPPETS = ("gps", "left boundary", "right boundary", "track width", "banking")


@contextmanager
def _data_dir_env(data_dir: Path):
    previous = os.environ.get("RACELAB_DATA_DIR")
    os.environ["RACELAB_DATA_DIR"] = str(data_dir)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("RACELAB_DATA_DIR", None)
        else:
            os.environ["RACELAB_DATA_DIR"] = previous


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _track_maps_dir(data_dir: Path) -> Path:
    return data_dir / "track_maps"


def _index_path(data_dir: Path) -> Path:
    return _track_maps_dir(data_dir) / "track_map_index.json"


def _imports_mt2_dir(data_dir: Path) -> Path:
    return data_dir / "imports" / "mt2"


def _coverage_row(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_key": entry.get("track_key"),
        "layout_key": entry.get("layout_key"),
        "display_name": entry.get("display_name"),
        "map_id": entry.get("map_id"),
        "distance_miles": round(float(entry.get("distance_ft", 0.0)) / 5280.0, 3) if entry.get("distance_ft") is not None else None,
        "points_count": entry.get("points_count"),
        "markers_count": entry.get("markers_count"),
        "sections_count": entry.get("sections_count"),
        "warnings_count": len(entry.get("warnings", [])),
        "supported": entry.get("supported"),
        "partial": entry.get("partial"),
        "status": entry.get("status"),
    }


def _validate_index_entry(entry: dict[str, Any], canonical_path: Path) -> list[str]:
    issues: list[str] = []
    if not entry.get("map_id"):
        issues.append("missing map_id")
    if not entry.get("display_name"):
        issues.append("missing display_name")
    if not entry.get("track_key"):
        issues.append("missing track_key")
    if not entry.get("layout_key"):
        issues.append("missing layout_key")
    if not canonical_path.exists():
        issues.append("missing canonical JSON")
    if "local_path" in entry:
        issues.append("index exposes local_path")
    if not entry.get("source_removed", False):
        issues.append("source_removed not true")
    if not (entry.get("source_hash") or entry.get("sha256")):
        issues.append("missing source hash")
    return issues


def _validate_track_map_object(entry: dict[str, Any], track_map: Any) -> list[str]:
    issues: list[str] = []
    if track_map is None:
        return ["get_track_map returned None"]
    if not getattr(track_map, "map_id", None):
        issues.append("loaded map missing map_id")
    if getattr(track_map, "map_id", None) != entry.get("map_id"):
        issues.append("loaded map_id mismatch")

    metadata = getattr(track_map, "metadata", None)
    bounds = getattr(track_map, "bounds", None)
    points = list(getattr(track_map, "points", []) or [])
    markers = list(getattr(track_map, "markers", []) or [])
    sections = list(getattr(track_map, "sections", []) or [])
    warnings = [str(w).lower() for w in getattr(track_map, "warnings", []) or []]

    if metadata is None:
        issues.append("missing metadata")
        return issues
    if not getattr(metadata, "display_name", None):
        issues.append("metadata missing display_name")
    if not _is_finite_number(getattr(metadata, "distance_m", None)) or float(metadata.distance_m) <= 0:
        issues.append("invalid metadata.distance_m")
    if not _is_finite_number(getattr(metadata, "distance_ft", None)) or float(metadata.distance_ft) <= 0:
        issues.append("invalid metadata.distance_ft")

    if bounds is None:
        issues.append("missing bounds")
    else:
        for attr in ("min_x_m", "max_x_m", "min_y_m", "max_y_m", "width_m", "height_m"):
            if not _is_finite_number(getattr(bounds, attr, None)):
                issues.append(f"non-finite bounds.{attr}")

    if len(points) <= 1:
        issues.append("points_count <= 1")
    last_distance = -math.inf
    for index, point in enumerate(points):
        x_value = getattr(point, "x_m", None)
        y_value = getattr(point, "y_m", None)
        distance_m = getattr(point, "distance_m", None)
        if not _is_finite_number(x_value):
            issues.append(f"point {index} has non-finite x")
            break
        if not _is_finite_number(y_value):
            issues.append(f"point {index} has non-finite y")
            break
        if not _is_finite_number(distance_m):
            issues.append(f"point {index} has non-finite distance")
            break
        distance_value = float(distance_m)
        if distance_value + 1e-6 < last_distance:
            issues.append(f"point {index} distance is not monotonic")
            break
        last_distance = distance_value
        lap_pct = getattr(point, "lap_pct", None)
        if lap_pct is None or not _is_finite_number(lap_pct) or float(lap_pct) < -1e-6 or float(lap_pct) > 100.0001:
            issues.append(f"point {index} has invalid lap_pct")
            break

    if len(markers) != int(entry.get("markers_count", len(markers))):
        issues.append("marker count mismatch")
    if len(sections) != int(entry.get("sections_count", len(sections))):
        issues.append("section count mismatch")

    for snippet in EXPECTED_WARNING_SNIPPETS:
        if not any(snippet in warning for warning in warnings):
            issues.append(f"missing expected warning: {snippet}")
            break

    if getattr(track_map, "source_file", "unexpected") not in (None, ""):
        issues.append("source_file should be null/absent")
    return issues


def _run_matching_coverage(index_entries: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        from racelab_engine.storage.repository import RaceLabRepository
    except Exception as exc:  # pragma: no cover - defensive
        return {"available": False, "reason": f"run repository unavailable: {exc}"}

    try:
        repo = RaceLabRepository()
        runs = repo.list_runs(limit=500)
    except Exception as exc:
        return {"available": False, "reason": f"run repository query failed: {exc}"}

    if not runs:
        return {"available": False, "reason": "no imported runs available"}

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for run in runs:
        run_id = run.get("run_id")
        track_name = run.get("track_name") or ""
        run_layout = infer_layout_key(track_name)
        ranked = rank_track_map_matches(
            track_name,
            run_layout,
            index_entries,
            run_context=str(run_id or ""),
        )
        ranked = [candidate for candidate in ranked if candidate["score"] > 0]
        best_score = ranked[0]["score"] if ranked else 0
        tied_top = [
            {
                "map_id": candidate["entry"].get("map_id"),
                "display_name": candidate["entry"].get("display_name"),
                "score": candidate["score"],
                "confidence": candidate["confidence"],
            }
            for candidate in ranked
            if candidate["score"] == best_score
        ]
        match = match_track_map_for_run(
            track_name,
            run_layout,
            index_entries,
            preferred_map_id=None,
            run_context=str(run_id or ""),
        )
        if match is None and len(tied_top) > 1:
            ambiguous.append(
                {
                    "run_id": run_id,
                    "track_name": track_name,
                    "top_score": best_score,
                    "top_candidates": tied_top,
                }
            )
            continue
        if match is None:
            unmatched.append(
                {
                    "run_id": run_id,
                    "track_name": track_name,
                    "best_score": best_score,
                    "top_candidates": tied_top[:3],
                }
            )
            continue
        matched.append(
            {
            "run_id": run_id,
            "track_name": track_name,
            "matched_map_id": match.get("map_id"),
            "match_score": match.get("match_score"),
            "match_confidence": match.get("match_confidence"),
            }
        )

    return {
        "available": True,
        "matched": matched,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "total_runs": len(runs),
    }


def audit_track_map_coverage(
    data_dir: Path,
    *,
    strict_count: int | None = None,
    show_warnings: bool = False,
    check_runs: bool = False,
) -> dict[str, Any]:
    track_maps_dir = _track_maps_dir(data_dir)
    index_path = _index_path(data_dir)
    imports_dir = _imports_mt2_dir(data_dir)
    audit: dict[str, Any] = {
        "data_dir": str(data_dir),
        "strict_count": strict_count,
        "violations": [],
    }

    if not index_path.exists():
        audit["violations"].append(f"missing index: {index_path}")
        return audit

    index_entries = _load_json(index_path)
    if not isinstance(index_entries, list):
        audit["violations"].append("track_map_index.json is not a list")
        return audit

    canonical_json_paths = sorted(track_maps_dir.glob("*.json"))
    canonical_map_paths = [path for path in canonical_json_paths if path.name != "track_map_index.json"]
    staging_files = sorted(p.name for p in imports_dir.glob("*") if p.is_file())
    staging_source_files = [name for name in staging_files if name != ".gitkeep"]

    audit["expected_source_count"] = strict_count
    audit["index_entry_count"] = len(index_entries)
    audit["canonical_json_count"] = len(canonical_map_paths)
    audit["unique_map_id_count"] = len({entry.get("map_id") for entry in index_entries if entry.get("map_id")})
    audit["unique_source_hash_count"] = len({
        entry.get("source_hash") or entry.get("sha256")
        for entry in index_entries
        if entry.get("source_hash") or entry.get("sha256")
    })
    audit["staging_files"] = staging_files
    audit["staging_source_files"] = staging_source_files
    audit["imports_dir_only_gitkeep"] = staging_files in ([], [".gitkeep"])

    hash_counter = Counter(
        entry.get("source_hash") or entry.get("sha256")
        for entry in index_entries
        if entry.get("source_hash") or entry.get("sha256")
    )
    duplicate_hashes = {
        hash_value: count for hash_value, count in hash_counter.items() if hash_value and count > 1
    }
    audit["duplicate_hashes"] = duplicate_hashes

    track_layout_counter = Counter(
        (entry.get("track_key"), entry.get("layout_key"))
        for entry in index_entries
    )
    duplicate_track_layouts = [
        {"track_key": track_key, "layout_key": layout_key, "count": count}
        for (track_key, layout_key), count in track_layout_counter.items()
        if count > 1
    ]
    audit["duplicate_track_layouts"] = duplicate_track_layouts

    referenced_cache_paths: set[Path] = set()
    missing_canonical_json: list[str] = []
    broken_index_entries: list[dict[str, Any]] = []
    invalid_json_maps: list[dict[str, Any]] = []
    broken_maps: list[dict[str, Any]] = []
    unsupported_or_partial: list[dict[str, Any]] = []
    no_sections: list[str] = []
    no_markers: list[str] = []
    suspicious_low_points: list[dict[str, Any]] = []
    suspicious_distances: list[dict[str, Any]] = []
    naming_cleanup_candidates: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    with _data_dir_env(data_dir):
        for entry in index_entries:
            cache_path_raw = entry.get("cache_path")
            cache_path = Path(cache_path_raw) if cache_path_raw else track_maps_dir / f"{entry.get('map_id')}.json"
            if not cache_path.is_absolute():
                cache_path = REPO_ROOT / cache_path
            referenced_cache_paths.add(cache_path.resolve())

            entry_issues = _validate_index_entry(entry, cache_path)
            if entry_issues:
                broken_index_entries.append({"map_id": entry.get("map_id"), "issues": entry_issues})
            if not cache_path.exists():
                missing_canonical_json.append(entry.get("map_id"))
                continue

            try:
                cache_payload = _load_json(cache_path)
            except Exception as exc:
                invalid_json_maps.append({"map_id": entry.get("map_id"), "error": str(exc)})
                continue

            if cache_payload.get("source_file") not in (None, ""):
                broken_maps.append({"map_id": entry.get("map_id"), "issues": ["canonical payload exposes source_file"]})

            track_map = get_track_map(str(entry.get("map_id")))
            track_map_issues = _validate_track_map_object(entry, track_map)
            if track_map_issues:
                broken_maps.append({"map_id": entry.get("map_id"), "issues": track_map_issues})

            coverage_rows.append(_coverage_row(entry))
            if entry.get("partial") or not entry.get("supported") or entry.get("status") != "parsed":
                unsupported_or_partial.append(_coverage_row(entry))
            if int(entry.get("sections_count", 0) or 0) == 0:
                no_sections.append(str(entry.get("map_id")))
            if int(entry.get("markers_count", 0) or 0) == 0:
                no_markers.append(str(entry.get("map_id")))
            if int(entry.get("points_count", 0) or 0) < LOW_POINT_COUNT_THRESHOLD:
                suspicious_low_points.append(_coverage_row(entry))

            distance_miles = float(entry.get("distance_ft", 0.0) or 0.0) / 5280.0
            if distance_miles < SHORT_DISTANCE_MILES_THRESHOLD or distance_miles > LONG_DISTANCE_MILES_THRESHOLD:
                suspicious_distances.append(_coverage_row(entry))

            cleanup = suggest_track_map_display_name(
                entry.get("display_name"),
                source_filename=entry.get("source_filename"),
                map_id=entry.get("map_id"),
                layout_key=entry.get("layout_key"),
            )
            source_name = str(entry.get("source_filename", "")).lower()
            heuristic_flag = (
                (
                    entry.get("layout_key") == "default"
                    and any(token in source_name for token in ("oval", "road", "roval", "dirt", "outer", "fullpit"))
                )
                or any(char.isdigit() for char in str(entry.get("track_key", "")))
            )
            if cleanup["auto_fixable"] or heuristic_flag:
                naming_cleanup_candidates.append(
                    {
                        **_coverage_row(entry),
                        "current_display_name": cleanup["current_display_name"],
                        "suggested_display_name": cleanup["suggested_display_name"],
                        "reason": cleanup["reason"] or "Heuristic semantic cleanup candidate.",
                        "classification": cleanup["classification"],
                        "auto_fixable": cleanup["auto_fixable"],
                    }
                )

    unreferenced_json_files = [
        str(path.name)
        for path in canonical_map_paths
        if path.resolve() not in referenced_cache_paths
    ]

    unique_tracks = defaultdict(set)
    for row in coverage_rows:
        unique_tracks[str(row["track_key"])].add(str(row["layout_key"]))

    audit["duplicate_count"] = sum(count - 1 for count in hash_counter.values() if count > 1)
    audit["missing_canonical_json"] = missing_canonical_json
    audit["unreferenced_json_files"] = unreferenced_json_files
    audit["broken_index_entries"] = broken_index_entries
    audit["invalid_json_maps"] = invalid_json_maps
    audit["broken_maps"] = broken_maps
    audit["unsupported_or_partial"] = unsupported_or_partial
    audit["coverage_rows"] = coverage_rows
    audit["tracks_with_multiple_layouts"] = {
        track_key: sorted(layouts) for track_key, layouts in unique_tracks.items() if len(layouts) > 1
    }
    audit["total_tracks_covered"] = len(unique_tracks)
    audit["total_track_layouts_covered"] = len(coverage_rows)
    audit["tracks_with_no_sections"] = no_sections
    audit["tracks_with_no_markers"] = no_markers
    audit["tracks_with_warnings_only"] = [
        row for row in coverage_rows
        if row["warnings_count"] > 0 and row["markers_count"] > 0 and row["sections_count"] > 0
    ]
    audit["suspicious_low_point_maps"] = suspicious_low_points
    audit["suspicious_distance_maps"] = suspicious_distances
    audit["manual_naming_layout_cleanup_candidates"] = naming_cleanup_candidates
    audit["show_warnings"] = show_warnings

    if check_runs:
        audit["run_matching"] = _run_matching_coverage(index_entries)
    else:
        audit["run_matching"] = {"available": False, "reason": "run matching skipped"}

    if strict_count is not None and len(index_entries) != strict_count:
        audit["violations"].append(
            f"index entry count {len(index_entries)} does not match strict count {strict_count}"
        )
    if len(index_entries) != len(canonical_map_paths):
        audit["violations"].append(
            f"index entry count {len(index_entries)} does not match canonical JSON count {len(canonical_map_paths)}"
        )
    if staging_source_files:
        audit["violations"].append(f"retained staging source files: {', '.join(staging_source_files)}")
    if missing_canonical_json:
        audit["violations"].append(f"missing canonical JSON for {len(missing_canonical_json)} map(s)")
    if unreferenced_json_files:
        audit["violations"].append(f"unreferenced canonical JSON files: {len(unreferenced_json_files)}")
    if duplicate_track_layouts:
        audit["violations"].append(f"duplicate track/layout entries: {len(duplicate_track_layouts)}")
    if broken_index_entries:
        audit["violations"].append(f"broken index entries: {len(broken_index_entries)}")
    if invalid_json_maps:
        audit["violations"].append(f"invalid canonical JSON maps: {len(invalid_json_maps)}")
    if broken_maps:
        audit["violations"].append(f"broken canonical maps: {len(broken_maps)}")
    return audit


def _format_table(rows: list[dict[str, Any]], columns: list[str], max_rows: int | None = None) -> str:
    if not rows:
        return "(none)"
    display_rows = rows[:max_rows] if max_rows is not None else rows
    widths = {column: len(column) for column in columns}
    for row in display_rows:
        for column in columns:
            widths[column] = max(widths[column], len(str(row.get(column, ""))))
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    divider = "-+-".join("-" * widths[column] for column in columns)
    body = [
        " | ".join(str(row.get(column, "")).ljust(widths[column]) for column in columns)
        for row in display_rows
    ]
    suffix = []
    if max_rows is not None and len(rows) > max_rows:
        suffix.append(f"... {len(rows) - max_rows} more")
    return "\n".join([header, divider, *body, *suffix])


def _print_human_report(audit: dict[str, Any], show_warnings: bool) -> None:
    print("RacerZLab Track Map Coverage Audit")
    print(f"Data dir: {audit['data_dir']}")
    print(f"Index entries: {audit.get('index_entry_count', 0)}")
    print(f"Canonical JSON files: {audit.get('canonical_json_count', 0)}")
    print(f"Unique map_id count: {audit.get('unique_map_id_count', 0)}")
    print(f"Unique source hash count: {audit.get('unique_source_hash_count', 0)}")
    print(f"Staging files: {', '.join(audit.get('staging_files', [])) or '(empty)'}")
    print(f"Violations: {len(audit.get('violations', []))}")
    for violation in audit.get("violations", []):
        print(f"  - {violation}")
    print()
    print("Coverage")
    print(_format_table(
        audit.get("coverage_rows", []),
        ["track_key", "layout_key", "display_name", "map_id", "distance_miles", "points_count", "markers_count", "sections_count", "warnings_count", "supported", "partial", "status"],
        max_rows=25,
    ))
    if show_warnings:
        print()
        print("Warnings by Map")
        warning_rows = [
            {"map_id": row["map_id"], "display_name": row["display_name"], "warnings_count": row["warnings_count"]}
            for row in audit.get("coverage_rows", [])
            if row["warnings_count"] > 0
        ]
        print(_format_table(warning_rows, ["map_id", "display_name", "warnings_count"], max_rows=25))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit RacerZLab canonical track map coverage.")
    parser.add_argument("--data-dir", default="data", help="Path to RacerZLab data directory. Defaults to ./data")
    parser.add_argument("--strict-count", type=int, default=None, help="Require exactly this many index entries.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a human table summary.")
    parser.add_argument("--show-warnings", action="store_true", help="Show warning summary in human output.")
    parser.add_argument("--check-runs", action="store_true", help="Attempt to compare current run history against the mapbase.")
    args = parser.parse_args()

    audit = audit_track_map_coverage(
        Path(args.data_dir),
        strict_count=args.strict_count,
        show_warnings=args.show_warnings,
        check_runs=args.check_runs,
    )
    if args.json:
        print(json.dumps(audit, indent=2))
    else:
        _print_human_report(audit, show_warnings=args.show_warnings)
    return 1 if audit.get("violations") else 0


if __name__ == "__main__":
    raise SystemExit(main())
