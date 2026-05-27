from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Any

from racelab_engine.io.mt2_reader import (
    TrackMap,
    TrackMapPoint,
    TrackMapMarker,
    TrackMapSection,
    parse_mt2_bytes,
    MT2DecodeError,
)
from racelab_engine.analysis.track_matching import (
    normalize_track_key,
    infer_layout_key,
    match_track_map_for_run,
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


def _upsert_index_entry(entry: dict[str, Any]) -> bool:
    """Insert or update an index entry. Returns True if new (inserted), False if updated."""
    entries = _load_index()
    for i, e in enumerate(entries):
        if e.get("map_id") == entry["map_id"]:
            entries[i] = entry
            _save_index(entries)
            return False  # updated
    entries.append(entry)
    _save_index(entries)
    return True  # inserted


# ── import ────────────────────────────────────────────────────

def import_mt2_file(path: Path) -> dict[str, Any]:
    """Import a single .mt2 file: copy, parse, cache, index. Returns index entry dict."""
    if not path.suffix.lower() == ".mt2":
        raise ValueError("Unsupported file type. Please select an .mt2 track map file.")

    safe_name = _sanitize_filename(path.name)
    dest = _mt2_imports_dir() / safe_name
    data = path.read_bytes()
    dest.write_bytes(data)

    sha = hashlib.sha256(data).hexdigest()
    track_map = parse_mt2_bytes(data, source_file=str(path))

    # Cache parsed JSON
    cache_path = _track_maps_dir() / f"{track_map.map_id}.json"
    cache_path.write_text(json.dumps(track_map.as_dict(), indent=2, default=str), encoding="utf-8")

    track_name = track_map.metadata.track_name
    track_key = normalize_track_key(track_name)
    layout_key = infer_layout_key(path.name)

    entry = {
        "map_id": track_map.map_id,
        "track_key": track_key,
        "layout_key": layout_key,
        "display_name": f"{track_name} ({layout_key})",
        "source_filename": path.name,
        "local_path": str(dest),
        "cache_path": str(cache_path),
        "source_type": "mt2",
        "status": track_map.status,
        "supported": track_map.supported,
        "partial": track_map.partial,
        "points_count": len(track_map.points),
        "markers_count": len(track_map.markers),
        "sections_count": len(track_map.sections),
        "distance_ft": track_map.metadata.distance_ft,
        "match_aliases": [track_name.lower(), track_key, path.stem.lower()],
        "warnings": track_map.warnings,
        "sha256": sha,
        "file_size_bytes": len(data),
    }
    is_new = _upsert_index_entry(entry)
    entry["import_status"] = "indexed" if is_new else "already_indexed"
    return entry


def save_and_import_mt2_upload(filename: str, data: bytes) -> dict[str, Any]:
    """Save uploaded .mt2 bytes to local imports dir, then parse and index."""
    safe_name = _sanitize_filename(filename)
    dest = _mt2_imports_dir() / safe_name
    dest.write_bytes(data)
    return import_mt2_file(dest)


def import_mt2_folder(folder_path: str | Path) -> list[dict[str, Any]]:
    """Import all .mt2 files from a local folder."""
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
        raise RuntimeError(f"All .mt2 imports failed: {'; '.join(errors[:5])}")
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
        file_size_bytes=d.get("file_size_bytes", 0),
        sha256=d.get("sha256", ""),
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
    return match_track_map_for_run(track_name, layout, entries, preferred_map_id=preferred_map_id)


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
            })

    # Target zone
    if target_zone_start_pct is not None and target_zone_end_pct is not None and points and total_dist > 0:
        from racelab_engine.io.mt2_reader import interpolate_at_pct
        zone_points = []
        step = (target_zone_end_pct - target_zone_start_pct) / 50.0
        p = target_zone_start_pct
        while p <= target_zone_end_pct:
            try:
                pos = interpolate_at_pct(points, p, total_dist)
                zone_points.append({"x": pos["x_m"], "y": pos["y_m"], "pct": p})
            except Exception:
                pass
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
        "REAR_CONTACT_RISK": "R?",
        "WHOLE_CAR_BOTTOMING_RISK": "⇣",
    }
    return mapping.get(event_type, "◆")


def _severity_color(severity: str) -> str:
    return {
        "critical": "#ef4444",
        "high": "#f97316",
        "watch": "#f59e0b",
        "info": "#38bdf8",
    }.get(severity, "#8d9aaa")
