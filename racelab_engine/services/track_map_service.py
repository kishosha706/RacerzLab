from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from racelab_engine.io.mt2_reader import (
    TrackMap,
    parse_mt2_bytes,
)
from racelab_engine.analysis.track_matching import (
    build_match_aliases,
    normalize_track_key,
    infer_layout_key,
    match_track_map_for_run,
    suggest_track_map_display_name,
)

DEFAULT_DATA_DIR = Path("data")
TRACK_MAPS_DIR_NAME = "track_maps"
IMPORTS_MT2_DIR_NAME = Path("imports/mt2")


def _data_dir() -> Path:
    return Path(os.environ.get("RACELAB_DATA_DIR", DEFAULT_DATA_DIR))


def _mt2_imports_dir() -> Path:
    d = _data_dir() / IMPORTS_MT2_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _track_maps_dir() -> Path:
    d = _data_dir() / TRACK_MAPS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path() -> Path:
    return _track_maps_dir() / "track_map_index.json"


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name)
    if ".." in name or "/" in name or "\\" in name:
        raise ValueError("Invalid filename")
    import re
    return re.sub(r'[^\w.\- ]', "_", name)


# ── index management ─────────────────────────────────────────

def _load_index() -> list[dict[str, Any]]:
    path = _index_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_index(entries: list[dict[str, Any]]) -> None:
    _index_path().write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")


def _find_index_entry(entries: list[dict[str, Any]], *, map_id: str | None = None, sha256: str | None = None) -> int | None:
    for i, entry in enumerate(entries):
        if map_id and entry.get("map_id") == map_id:
            return i
        if sha256 and entry.get("sha256") == sha256:
            return i
    return None


def _upsert_index_entry(entry: dict[str, Any]) -> bool:
    """Insert or update an index entry. Returns True if new (inserted), False if updated."""
    entries = _load_index()
    existing_index = _find_index_entry(entries, map_id=entry["map_id"], sha256=entry.get("sha256"))
    if existing_index is not None:
        entries[existing_index] = entry
        _save_index(entries)
        return False  # updated
    entries.append(entry)
    _save_index(entries)
    return True  # inserted


def _canonical_cache_dict(track_map: TrackMap) -> dict[str, Any]:
    data = track_map.as_dict()
    layout_key = infer_layout_key(Path(track_map.source_file or "").name if track_map.source_file else None)
    if metadata := data.get("metadata"):
        metadata["display_name"] = suggest_track_map_display_name(
            metadata.get("display_name") or metadata.get("track_name"),
            source_filename=Path(track_map.source_file or "").name if track_map.source_file else None,
            map_id=track_map.map_id,
            layout_key=layout_key,
        )["suggested_display_name"]
    data["source_file"] = None
    data["source_hash"] = track_map.sha256
    return data


def _canonical_index_entry(
    track_map: TrackMap,
    *,
    source_filename: str,
    cache_path: Path,
) -> dict[str, Any]:
    track_name = track_map.metadata.track_name
    track_key = normalize_track_key(track_name)
    layout_key = infer_layout_key(source_filename)
    display_name = suggest_track_map_display_name(
        track_map.metadata.display_name or track_name,
        source_filename=source_filename,
        map_id=track_map.map_id,
        layout_key=layout_key,
    )["suggested_display_name"]
    return {
        "map_id": track_map.map_id,
        "track_key": track_key,
        "layout_key": layout_key,
        "display_name": display_name,
        "source_filename": source_filename,
        "cache_path": str(cache_path),
        "source_type": track_map.source_type,
        "source_removed": True,
        "status": track_map.status,
        "supported": track_map.supported,
        "partial": track_map.partial,
        "points_count": len(track_map.points),
        "markers_count": len(track_map.markers),
        "sections_count": len(track_map.sections),
        "distance_ft": track_map.metadata.distance_ft,
        "match_aliases": build_match_aliases(display_name, source_filename, layout_key),
        "warnings": track_map.warnings,
        "sha256": track_map.sha256,
        "source_hash": track_map.sha256,
        "file_size_bytes": track_map.file_size_bytes,
    }


def _normalize_index_entry(entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(entry)
    source_hash = normalized.get("source_hash") or normalized.get("sha256")
    if source_hash:
        normalized["source_hash"] = source_hash
        normalized["sha256"] = normalized.get("sha256", source_hash)
    display_cleanup = suggest_track_map_display_name(
        normalized.get("display_name"),
        source_filename=normalized.get("source_filename"),
        map_id=normalized.get("map_id"),
        layout_key=normalized.get("layout_key"),
    )
    if display_cleanup["suggested_display_name"]:
        normalized["display_name"] = display_cleanup["suggested_display_name"]
        normalized["match_aliases"] = build_match_aliases(
            normalized["display_name"],
            str(normalized.get("source_filename", "")),
            str(normalized.get("layout_key", "default")),
        )
    normalized["source_removed"] = True
    normalized.pop("local_path", None)
    return normalized


def _retained_source_path(entry: dict[str, Any]) -> Path | None:
    local_path = entry.get("local_path")
    if not local_path:
        return None
    try:
        return Path(local_path)
    except (TypeError, ValueError):
        return None


def _delete_retained_source_file(entry: dict[str, Any]) -> bool:
    retained_path = _retained_source_path(entry)
    cache_path_value = entry.get("cache_path")
    if retained_path is None or not cache_path_value:
        return False
    cache_path = Path(cache_path_value)
    if not cache_path.exists() or not retained_path.exists() or retained_path.suffix.lower() != ".mt2":
        return False
    retained_path.unlink()
    return True


def _sanitize_canonical_cache(entry: dict[str, Any]) -> bool:
    cache_path_value = entry.get("cache_path")
    if not cache_path_value:
        return False
    cache_path = Path(cache_path_value)
    if not cache_path.exists():
        return False
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False

    original = json.dumps(data, sort_keys=True)
    data["source_file"] = None
    if "sha256" in data and "source_hash" not in data:
        data["source_hash"] = data["sha256"]
    if metadata := data.get("metadata"):
        metadata["display_name"] = suggest_track_map_display_name(
            metadata.get("display_name") or metadata.get("track_name"),
            source_filename=entry.get("source_filename"),
            map_id=entry.get("map_id"),
            layout_key=entry.get("layout_key"),
        )["suggested_display_name"]

    if json.dumps(data, sort_keys=True) == original:
        return False
    cache_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return True


def cleanup_track_map_storage() -> dict[str, int]:
    entries = _load_index()
    if not entries:
        return {"entries_updated": 0, "source_files_removed": 0, "cache_files_updated": 0}

    normalized_entries: list[dict[str, Any]] = []
    entries_updated = 0
    source_files_removed = 0
    cache_files_updated = 0
    for entry in entries:
        if _delete_retained_source_file(entry):
            source_files_removed += 1
        if _sanitize_canonical_cache(entry):
            cache_files_updated += 1
        normalized = _normalize_index_entry(entry)
        if normalized != entry:
            entries_updated += 1
        normalized_entries.append(normalized)

    if entries_updated or source_files_removed:
        _save_index(normalized_entries)
    return {
        "entries_updated": entries_updated,
        "source_files_removed": source_files_removed,
        "cache_files_updated": cache_files_updated,
    }


# ── import ────────────────────────────────────────────────────

def import_mt2_file(path: Path) -> dict[str, Any]:
    """Import a single track map file into the canonical local cache."""
    if path.suffix.lower() != ".mt2":
        raise ValueError("Unsupported file type. Please select a track map file.")

    data = path.read_bytes()
    track_map = parse_mt2_bytes(data, source_file=str(path))

    # Cache canonical RacerZLab track-map JSON
    cache_path = _track_maps_dir() / f"{track_map.map_id}.json"
    cache_path.write_text(json.dumps(_canonical_cache_dict(track_map), indent=2, default=str), encoding="utf-8")

    entry = _canonical_index_entry(
        track_map,
        source_filename=path.name,
        cache_path=cache_path,
    )
    is_new = _upsert_index_entry(entry)
    entry["import_status"] = "indexed" if is_new else "already_indexed"
    return entry


def save_and_import_mt2_upload(filename: str, data: bytes) -> dict[str, Any]:
    """Parse uploaded track map bytes and write only the canonical local cache."""
    safe_name = _sanitize_filename(filename)
    track_map = parse_mt2_bytes(data, source_file=safe_name)
    cache_path = _track_maps_dir() / f"{track_map.map_id}.json"
    cache_path.write_text(json.dumps(_canonical_cache_dict(track_map), indent=2, default=str), encoding="utf-8")
    entry = _canonical_index_entry(
        track_map,
        source_filename=safe_name,
        cache_path=cache_path,
    )
    is_new = _upsert_index_entry(entry)
    entry["import_status"] = "indexed" if is_new else "already_indexed"
    return entry


def import_mt2_folder(folder_path: str | Path) -> list[dict[str, Any]]:
    """Import all supported track map files from a local folder."""
    p = Path(folder_path)
    if not p.is_dir():
        raise ValueError(f"Not a directory: {folder_path}")
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for f in sorted(p.glob("*.mt2")):
        try:
            entry = import_mt2_file(f)
            entries.append(entry)
        except Exception as exc:
            errors.append(f"{f.name}: {exc}")
    # If nothing succeeded, raise
    if not entries and errors:
        raise RuntimeError(f"All track map imports failed: {'; '.join(errors[:5])}")
    return entries


# ── query ─────────────────────────────────────────────────────

def list_track_maps() -> list[dict[str, Any]]:
    return _load_index()


def get_track_map(map_id: str) -> TrackMap | None:
    """Load full TrackMap from cache."""
    cache_path = _track_maps_dir() / f"{map_id}.json"
    if not cache_path.exists():
        # Try from index
        entries = _load_index()
        for e in entries:
            if e.get("map_id") == map_id:
                cache_path = Path(e.get("cache_path", ""))
                break
    if not cache_path or not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return _dict_to_track_map(data)
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def _dict_to_track_map(d: dict[str, Any]) -> TrackMap:
    """Reconstitute a TrackMap from its dict form (cheap deserialization)."""
    from racelab_engine.io.mt2_reader import (
        TrackMapMetadata, TrackMapBounds, TrackMapOrigin, TrackMapPoint,
        TrackMapMarker, TrackMapSection,
    )
    meta = d["metadata"]
    metadata = TrackMapMetadata(
        format=meta["format"],
        version=meta.get("version"),
        track_name=meta["track_name"],
        display_name=meta.get("display_name"),
        model_name=meta.get("model_name"),
        closed=meta["closed"],
        clockwise_flag=meta["clockwise_flag"],
        x_over=meta.get("x_over", False),
        z_rotation_rad=meta.get("z_rotation_rad", 0.0),
        distance_m=meta["distance_m"],
        distance_ft=meta["distance_ft"],
        distance_miles=meta["distance_miles"],
        point_record=meta["point_record"],
        units=meta["units"],
        origin=TrackMapOrigin(**meta["origin"]),
        has_boundaries=meta.get("has_boundaries", False),
        has_sections=meta.get("has_sections", False),
        has_markers=meta.get("has_markers", False),
        warnings=meta.get("warnings", []),
    )
    bounds_data = d["bounds"]
    bounds = TrackMapBounds(**bounds_data)
    points = [TrackMapPoint(**p) for p in d["points"]]
    markers = [TrackMapMarker(**m) for m in d["markers"]]
    sections = [TrackMapSection(**s) for s in d["sections"]]

    return TrackMap(
        map_id=d["map_id"],
        source_file=d.get("source_file"),
        source_type=d.get("source_type", "mt2"),
        file_size_bytes=d.get("file_size_bytes", 0),
        sha256=d.get("sha256", d.get("source_hash", "")),
        metadata=metadata,
        bounds=bounds,
        points=points,
        markers=markers,
        sections=sections,
        status=d.get("status", "parsed"),
        supported=d.get("supported", True),
        partial=d.get("partial", False),
        warnings=d.get("warnings", []),
    )


def find_best_map_for_run(run_id: str, track_name: str, layout: str | None = None, preferred_map_id: str | None = None) -> dict[str, Any] | None:
    """Match a run to the best available track map.

    If *preferred_map_id* is provided, it bypasses autodetection entirely.
    """
    entries = _load_index()
    return match_track_map_for_run(
        track_name,
        layout,
        entries,
        preferred_map_id=preferred_map_id,
        run_context=run_id,
    )


# ── overlay builders ─────────────────────────────────────────

def build_track_map_overlays(
    map_id: str,
    platform_events: list[dict[str, Any]] | None = None,
    target_zone_start_pct: float | None = None,
    target_zone_end_pct: float | None = None,
) -> list[dict[str, Any]]:
    """Build overlay markers from platform events and target zone."""
    overlays: list[dict[str, Any]] = []

    track_map = get_track_map(map_id)
    points = track_map.points if track_map else []
    total_dist = track_map.metadata.distance_m if track_map else 0.0

    # Platform event overlays
    if platform_events:
        for event in platform_events:
            pct = event.get("lap_pct") or event.get("position_pct")
            if pct is None:
                continue
            from racelab_engine.io.mt2_reader import interpolate_at_pct
            try:
                pos = interpolate_at_pct(points, pct, total_dist)
            except Exception:
                pos = None
            overlays.append({
                "marker_id": event.get("event_id", f"evt_{event.get('event_type','')}"),
                "kind": "platform_event",
                "label": event.get("label", event.get("event_type", "")),
                "description": event.get("description", ""),
                "lap_pct": pct,
                "distance_ft": event.get("distance_ft"),
                "x": pos["x_m"] if pos else None,
                "y": pos["y_m"] if pos else None,
                "heading_rad": pos["heading_rad"] if pos else None,
                "severity": event.get("severity", "info"),
                "symbol": _event_symbol(event.get("event_type", "")),
                "color": _severity_color(event.get("severity", "info")),
                "source_id": event.get("event_id"),
                "source_type": "platform_event",
                "related_channels": event.get("related_channels", []),
                "confidence": event.get("confidence"),
                "event_type": event.get("event_type"),
                "category": _event_category(event.get("event_type", "")),
            })

    # Target zone
    if target_zone_start_pct is not None and target_zone_end_pct is not None and points and total_dist > 0:
        from racelab_engine.io.mt2_reader import interpolate_at_pct
        zone_points = []
        step = (target_zone_end_pct - target_zone_start_pct) / 50.0
        p = target_zone_start_pct
        from contextlib import suppress
        while p <= target_zone_end_pct:
            with suppress(Exception):
                pos = interpolate_at_pct(points, p, total_dist)
                zone_points.append({"x": pos["x_m"], "y": pos["y_m"], "pct": p})
            p += step
        overlays.append({
            "marker_id": "target_zone",
            "kind": "target_zone",
            "label": f"Target Zone {target_zone_start_pct}–{target_zone_end_pct}%",
            "start_pct": target_zone_start_pct,
            "end_pct": target_zone_end_pct,
            "points": zone_points,
        })

    return overlays


def build_track_map_package(
    map_id: str,
    run_id: str,
    lap: int | None = None,
    platform_events: list[dict[str, Any]] | None = None,
    target_zone_start_pct: float | None = None,
    target_zone_end_pct: float | None = None,
) -> dict[str, Any]:
    """Build the full track map package for frontend rendering."""
    track_map = get_track_map(map_id)
    entries = _load_index()
    match = next((e for e in entries if e.get("map_id") == map_id), None)

    overlays = build_track_map_overlays(
        map_id,
        platform_events=platform_events,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
    )

    from dataclasses import asdict
    return {
        "run_id": run_id,
        "lap": lap,
        "map": track_map.as_dict() if track_map else None,
        "match": match,
        "overlays": overlays,
        "sections": [asdict(s) for s in (track_map.sections if track_map else [])],
        "markers": [asdict(m) for m in (track_map.markers if track_map else [])],
        "target_zone": {
            "start_pct": target_zone_start_pct,
            "end_pct": target_zone_end_pct,
        } if target_zone_start_pct is not None else None,
        "warnings": track_map.warnings if track_map else [],
    }


def _event_symbol(event_type: str) -> str:
    mapping = {
        "MIN_SPLITTER": "⬇",
        "WORST_SPEED_LOSS": "▼",
        "WORST_DRAG_SCRUB": "⚠",
        "HIGHEST_RAKE": "▲",
        "HIGHEST_PLATFORM_COMPRESSION": "●",
        "HIGHEST_SHOCK_ACTIVITY": "S",
        "MAX_DYNAMIC_PRESSURE": "○",
        "MIN_REAR_RIDE_HEIGHT": "Rmin",
        "REAR_PLATFORM_LOW": "R",
        "REAR_PLATFORM_SCRAPE": "R!",
        "WHOLE_CAR_BOTTOMING_RISK": "⇣",
    }
    return mapping.get(event_type, "◆")


def _event_category(event_type: str) -> str:
    """Map event type to a stable category for frontend layer filtering."""
    mapping: dict[str, str] = {
        "MIN_SPLITTER": "front_platform",
        "FRONT_PLATFORM_LOW": "front_platform",
        "FRONT_PLATFORM_SCRAPE": "front_platform",
        "FRONT_SCRAPE": "front_platform",
        "REAR_PLATFORM_LOW": "rear_platform",
        "REAR_PLATFORM_SCRAPE": "rear_platform",
        "REAR_SCRAPE": "rear_platform",
        "MIN_REAR_RIDE_HEIGHT": "rear_platform",
        "WHOLE_CAR_BOTTOMING_RISK": "whole_car_bottoming",
        "WORST_DRAG_SCRUB": "drag_scrub",
        "FULL_THROTTLE_SPEED_LOSS": "drag_scrub",
        "STEERING_SCRUB": "drag_scrub",
        "WORST_SPEED_LOSS": "speed_loss",
        "MAX_DYNAMIC_PRESSURE": "aero_dynamic_pressure",
        "DYNAMIC_PRESSURE_PEAK": "aero_dynamic_pressure",
        "HIGHEST_SHOCK_ACTIVITY": "shocks",
        "HIGHEST_RAKE": "aero_dynamic_pressure",
        "HIGHEST_PLATFORM_COMPRESSION": "front_platform",
    }
    return mapping.get(event_type, "other")


def _severity_color(severity: str) -> str:
    return {
        "critical": "#ef4444",
        "high": "#f97316",
        "watch": "#f59e0b",
        "info": "#38bdf8",
    }.get(severity, "#8d9aaa")
