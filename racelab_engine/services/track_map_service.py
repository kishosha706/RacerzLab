from __future__ import annotations

import hashlib
import json
import math
import os
from copy import deepcopy
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from racelab_engine.analysis.track_matching import (
    build_match_aliases,
    infer_layout_key,
    match_track_map_for_run,
    normalize_track_key,
    suggest_track_map_display_name,
)
from racelab_engine.io.mt2_reader import (
    TrackMap,
    TrackMapSection,
    interpolate_at_pct,
    parse_mt2_bytes,
)

DEFAULT_DATA_DIR = Path("data")
TRACK_MAPS_DIR_NAME = "track_maps"
IMPORTS_MT2_DIR_NAME = Path("imports/mt2")
_TRACK_MAP_CACHE_MAX_ENTRY_BYTES = 4 * 1024 * 1024
_TRACK_MAP_INDEX_CACHE_MAX_ENTRY_BYTES = 2 * 1024 * 1024
_TRACK_MAP_STORAGE_LOCK = RLock()

_DEFAULT_OVAL_FAMILIES = {
    "bristol",
    "chicagoland",
    "darlington",
    "dover",
    "lakeland",
    "langley",
    "martinsville",
    "michigan",
    "milwaukee",
    "myrtlebeach",
    "newsmyrna",
    "northwilkesboro",
    "richmond",
    "talladega",
}
_OVAL_VARIANT_LAYOUTS = {"oval", "outer", "fullpit", "dirt"}


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

def _read_stable_file(path: Path) -> tuple[tuple[Any, ...], bytes]:
    """Read one coherent generation and include content identity in its cache key."""
    for _attempt in range(3):
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
        before_key = (
            before.st_mtime_ns, before.st_size, before.st_ctime_ns, before.st_dev, before.st_ino,
        )
        after_key = (
            after.st_mtime_ns, after.st_size, after.st_ctime_ns, after.st_dev, after.st_ino,
        )
        if before_key == after_key and len(payload) == after.st_size:
            return (
                str(path.resolve()),
                *after_key,
                hashlib.sha256(payload).hexdigest(),
            ), payload
    raise OSError(f"Track-map file changed while it was being read: {path}")


def _atomic_write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="") as file_obj:
            file_obj.write(payload)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _invalidate_track_map_file_caches() -> None:
    _load_index_cached.cache_clear()
    _get_track_map_cached.cache_clear()


def _load_index() -> list[dict[str, Any]]:
    path = _index_path()
    if not path.exists():
        return []
    try:
        signature, payload = _read_stable_file(path)
        # Callers normalize and decorate index entries.  Keep those mutations
        # isolated from the process cache, including nested alias/warning lists.
        return deepcopy(
            list(
                _load_index_cached(*signature, payload)
                if len(payload) <= _TRACK_MAP_INDEX_CACHE_MAX_ENTRY_BYTES
                else _decode_index(payload)
            )
        )
    except (json.JSONDecodeError, OSError):
        return []


def _decode_index(payload: bytes) -> tuple[dict[str, Any], ...]:
    decoded = json.loads(payload.decode("utf-8"))
    return tuple(decoded) if isinstance(decoded, list) else ()


@lru_cache(maxsize=8)
def _load_index_cached(
    _path: str,
    _mtime_ns: int,
    _size: int,
    _ctime_ns: int,
    _device: int,
    _inode: int,
    _digest: str,
    payload_bytes: bytes,
) -> tuple[dict[str, Any], ...]:
    del _path, _mtime_ns, _size, _ctime_ns, _device, _inode, _digest
    payload = json.loads(payload_bytes.decode("utf-8"))
    return tuple(payload) if isinstance(payload, list) else ()


def _save_index(entries: list[dict[str, Any]]) -> None:
    _atomic_write_text(_index_path(), json.dumps(entries, indent=2, default=str))
    _invalidate_track_map_file_caches()


def _find_index_entry(entries: list[dict[str, Any]], *, map_id: str | None = None, sha256: str | None = None) -> int | None:
    for i, entry in enumerate(entries):
        if map_id and entry.get("map_id") == map_id:
            return i
        if sha256 and entry.get("sha256") == sha256:
            return i
    return None


def _upsert_index_entry(entry: dict[str, Any]) -> bool:
    """Insert or update an index entry. Returns True if new (inserted), False if updated."""
    with _TRACK_MAP_STORAGE_LOCK:
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
        metadata["format"] = "track_map_v2"
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
        metadata["format"] = "track_map_v2"
        metadata["display_name"] = suggest_track_map_display_name(
            metadata.get("display_name") or metadata.get("track_name"),
            source_filename=entry.get("source_filename"),
            map_id=entry.get("map_id"),
            layout_key=entry.get("layout_key"),
        )["suggested_display_name"]

    if json.dumps(data, sort_keys=True) == original:
        return False
    _atomic_write_text(cache_path, json.dumps(data, indent=2, default=str))
    _invalidate_track_map_file_caches()
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
    _atomic_write_text(cache_path, json.dumps(_canonical_cache_dict(track_map), indent=2, default=str))
    _invalidate_track_map_file_caches()

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
    _atomic_write_text(cache_path, json.dumps(_canonical_cache_dict(track_map), indent=2, default=str))
    _invalidate_track_map_file_caches()
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
        except Exception as exc:  # noqa: BLE001 - continue auditing the remaining files
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
        signature, payload = _read_stable_file(cache_path)
        cached = (
            _get_track_map_cached(*signature, payload)
            if len(payload) <= _TRACK_MAP_CACHE_MAX_ENTRY_BYTES
            else _dict_to_track_map(json.loads(payload.decode("utf-8")))
        )
        # The cached canonical object is process-owned.  Return a cheap model
        # reconstruction so callers cannot corrupt later reads by mutating a
        # point, list, or nested metadata collection.
        return _dict_to_track_map(cached.as_dict())
    except (json.JSONDecodeError, OSError, KeyError):
        return None


@lru_cache(maxsize=8)
def _get_track_map_cached(
    _path: str,
    _mtime_ns: int,
    _size: int,
    _ctime_ns: int,
    _device: int,
    _inode: int,
    _digest: str,
    payload_bytes: bytes,
) -> TrackMap:
    del _path, _mtime_ns, _size, _ctime_ns, _device, _inode, _digest
    return _dict_to_track_map(json.loads(payload_bytes.decode("utf-8")))


def _dict_to_track_map(d: dict[str, Any]) -> TrackMap:
    """Reconstitute a TrackMap from its dict form (cheap deserialization)."""
    from racelab_engine.io.mt2_reader import (
        TrackMapBounds,
        TrackMapMarker,
        TrackMapMetadata,
        TrackMapOrigin,
        TrackMapPoint,
        TrackMapSection,
    )
    meta = d["metadata"]
    metadata = TrackMapMetadata(
        format="track_map_v2",
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

def _lap_pct_at_fraction(start_pct: float, end_pct: float, fraction: float) -> float:
    span = (float(end_pct) - float(start_pct) + 100.0) % 100.0
    return (float(start_pct) + span * fraction) % 100.0


def _section_fraction_pct(section: TrackMapSection, fraction: float) -> float:
    return _lap_pct_at_fraction(section.start_lap_pct, section.end_lap_pct, fraction)


def _oval_map_family(track_map: TrackMap, match: dict[str, Any] | None) -> str:
    candidates = [
        match.get("display_name") if match else None,
        track_map.metadata.display_name,
        track_map.metadata.track_name,
        match.get("track_key") if match else None,
        track_map.map_id,
    ]
    for candidate in candidates:
        family = normalize_track_key(candidate)
        if family and family != "unknown":
            return family
    return "unknown"


def is_oval_track_map(track_map: TrackMap, match: dict[str, Any] | None = None) -> bool:
    """Return whether a matched map represents an oval racing layout."""
    family = _oval_map_family(track_map, match)
    layout = str(match.get("layout_key") if match else "").strip().lower()
    if not layout:
        layout = infer_layout_key(
            (match or {}).get("source_filename")
            or track_map.metadata.display_name
            or track_map.metadata.track_name
            or track_map.map_id
        )
    if layout in {"road", "roval"}:
        return False
    if layout == "oval":
        return True
    if layout in _OVAL_VARIANT_LAYOUTS:
        return family in {"bristol", "irwindale"}
    return layout == "default" and family in _DEFAULT_OVAL_FAMILIES


def _heading_quarter_turn_pcts(track_map: TrackMap) -> list[float]:
    cumulative: list[tuple[float, float]] = []
    prior_heading: float | None = None
    rotation = 0.0
    for point in track_map.points:
        if point.lap_pct is None or point.heading_rad is None:
            continue
        heading = float(point.heading_rad)
        if not math.isfinite(heading):
            continue
        if prior_heading is not None:
            rotation += (heading - prior_heading + math.pi) % (2.0 * math.pi) - math.pi
        cumulative.append((float(point.lap_pct), rotation))
        prior_heading = heading
    if len(cumulative) < 4 or abs(rotation) < 1.5 * math.pi:
        return []
    direction = 1.0 if rotation >= 0.0 else -1.0
    monotonic: list[tuple[float, float]] = []
    furthest_progress = 0.0
    for lap_pct, raw_rotation in cumulative:
        progress = raw_rotation * direction
        furthest_progress = max(furthest_progress, progress)
        monotonic.append((lap_pct, furthest_progress))
    if furthest_progress < 1.5 * math.pi:
        return []

    anchors: list[float] = []
    for fraction in (0.125, 0.375, 0.625, 0.875):
        target = furthest_progress * fraction
        for (left_pct, left_rotation), (right_pct, right_rotation) in pairwise(monotonic):
            if left_rotation <= target <= right_rotation and right_rotation > left_rotation:
                local_fraction = (target - left_rotation) / (right_rotation - left_rotation)
                anchors.append(_lap_pct_at_fraction(left_pct, right_pct, local_fraction))
                break
        else:
            anchors.append(min(monotonic, key=lambda item: abs(item[1] - target))[0])
    return anchors


def _oval_turn_anchor_pcts(
    track_map: TrackMap,
    match: dict[str, Any] | None,
) -> tuple[list[float], str]:
    corners = [section for section in track_map.sections if section.section_type == "corner"]
    map_id = track_map.map_id.lower()
    family = _oval_map_family(track_map, match)

    if family == "pocono" and len(corners) >= 3:
        return ([_section_fraction_pct(section, 0.5) for section in corners[:3]], "three-corner oval sections")

    if "atlanta-quadoval" in map_id and len(corners) >= 5:
        return (
            [
                _section_fraction_pct(corners[2], 0.25),
                _section_fraction_pct(corners[2], 0.75),
                _section_fraction_pct(corners[3], 0.5),
                _section_fraction_pct(corners[4], 0.5),
            ],
            "quad-oval conventional corner sections",
        )

    if family == "talladega" and len(corners) >= 3:
        return (
            [
                _section_fraction_pct(corners[0], 0.5),
                _section_fraction_pct(corners[1], 0.5),
                _section_fraction_pct(corners[2], 0.25),
                _section_fraction_pct(corners[2], 0.75),
            ],
            "tri-oval conventional corner sections",
        )

    if (
        family == "indianapolis"
        and "indianapolis-oval-" in map_id
        and "2022" not in map_id
        and "indypit" not in map_id
        and len(corners) >= 5
    ):
        return (
            [
                _section_fraction_pct(corners[0], 0.5),
                _section_fraction_pct(corners[1], 0.5),
                _section_fraction_pct(corners[2], 0.5),
                _lap_pct_at_fraction(corners[3].start_lap_pct, corners[4].end_lap_pct, 0.5),
            ],
            "four-corner oval sections with merged final corner",
        )

    if len(corners) == 2:
        return (
            [
                _section_fraction_pct(corners[0], 0.25),
                _section_fraction_pct(corners[0], 0.75),
                _section_fraction_pct(corners[1], 0.25),
                _section_fraction_pct(corners[1], 0.75),
            ],
            "split two-end oval sections",
        )

    if len(corners) == 4:
        return ([_section_fraction_pct(section, 0.5) for section in corners], "four-corner oval sections")

    fallback = _heading_quarter_turn_pcts(track_map)
    return (fallback, "centerline heading quarters" if fallback else "unavailable")


def build_oval_turn_markers(
    track_map: TrackMap,
    match: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build conventional, geometry-positioned turn labels for an oval map."""
    if not is_oval_track_map(track_map, match):
        return []
    lap_pcts, placement_source = _oval_turn_anchor_pcts(track_map, match)
    total_distance_m = float(track_map.metadata.distance_m)
    if not lap_pcts or total_distance_m <= 0.0 or not track_map.points:
        return []

    turns: list[dict[str, Any]] = []
    for number, lap_pct in enumerate(lap_pcts, start=1):
        if not math.isfinite(lap_pct):
            continue
        position = interpolate_at_pct(track_map.points, lap_pct, total_distance_m)
        distance_m = lap_pct / 100.0 * total_distance_m
        turns.append(
            {
                "turn_id": f"turn_{number}",
                "number": number,
                "label": f"Turn {number}",
                "short_label": f"T{number}",
                "lap_pct": lap_pct,
                "distance_m": distance_m,
                "distance_ft": distance_m * 3.280839895013123,
                "x": position["x_m"],
                "y": position["y_m"],
                "z": position["z_m"],
                "heading_rad": position["heading_rad"],
                "placement_source": placement_source,
            }
        )
    return turns


def _lap_pct_offset(start_pct: float, lap_pct: float) -> float:
    return (float(lap_pct) - float(start_pct) + 100.0) % 100.0


def _lap_pct_in_region(start_pct: float, end_pct: float, lap_pct: float) -> bool:
    span = _lap_pct_offset(start_pct, end_pct)
    offset = _lap_pct_offset(start_pct, lap_pct)
    return offset <= span + 1e-9


def _friendly_straight_region_label(section: TrackMapSection) -> str:
    raw = section.name.strip()
    lower = raw.casefold()
    if section.wraps_start_finish or "front" in lower or "str 0" in lower:
        return "Front Stretch"
    if "back" in lower or "str 1" in lower:
        return "Backstretch"
    midpoint = _section_fraction_pct(section, 0.5)
    return "Front Stretch" if midpoint >= 75.0 or midpoint < 25.0 else "Backstretch"


def _adaptive_turn_region_bounds(
    lap_pcts: list[float],
    index: int,
) -> tuple[float, float]:
    current = lap_pcts[index]
    previous = lap_pcts[index - 1]
    following = lap_pcts[(index + 1) % len(lap_pcts)]
    previous_gap = _lap_pct_offset(previous, current)
    following_gap = _lap_pct_offset(current, following)
    half_width = min(previous_gap, following_gap) * 0.48
    return ((current - half_width) % 100.0, (current + half_width) % 100.0)


def build_track_regions(
    track_map: TrackMap,
    match: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build vendor-neutral physical regions for maps and grounded intelligence."""
    turns = build_oval_turn_markers(track_map, match)
    regions: list[dict[str, Any]] = []
    placement_source = ""
    turn_bounds: dict[int, tuple[float, float, str]] = {}
    if turns:
        lap_pcts = [float(turn["lap_pct"]) for turn in turns]
        for index, _turn in enumerate(turns):
            start_pct, end_pct = _adaptive_turn_region_bounds(lap_pcts, index)
            turn_bounds[index] = (start_pct, end_pct, "centerline_geometry")

        placement_source = str(turns[0]["placement_source"])
        corners = [section for section in track_map.sections if section.section_type == "corner"]
        if placement_source != "centerline heading quarters":
            for section in corners:
                members = [
                    (index, lap_pct)
                    for index, lap_pct in enumerate(lap_pcts)
                    if _lap_pct_in_region(
                        section.start_lap_pct,
                        section.end_lap_pct,
                        lap_pct,
                    )
                ]
                members.sort(key=lambda item: _lap_pct_offset(section.start_lap_pct, item[1]))
                if not members:
                    continue
                boundaries = [float(section.start_lap_pct)]
                boundaries.extend(
                    _lap_pct_at_fraction(left_pct, right_pct, 0.5)
                    for (_, left_pct), (_, right_pct) in pairwise(members)
                )
                boundaries.append(float(section.end_lap_pct))
                for member_index, (turn_index, _lap_pct) in enumerate(members):
                    turn_bounds[turn_index] = (
                        boundaries[member_index],
                        boundaries[member_index + 1],
                        "section_geometry",
                    )

        if placement_source == "four-corner oval sections with merged final corner":
            corners = [section for section in track_map.sections if section.section_type == "corner"]
            if len(corners) >= 5 and len(turns) >= 4:
                turn_bounds[3] = (
                    float(corners[3].start_lap_pct),
                    float(corners[4].end_lap_pct),
                    "section_geometry",
                )

        for index, turn in enumerate(turns):
            start_pct, end_pct, confidence = turn_bounds[index]
            regions.append(
                {
                    "region_id": turn["turn_id"],
                    "kind": "turn",
                    "number": turn["number"],
                    "label": turn["label"],
                    "short_label": turn["short_label"],
                    "start_lap_pct": start_pct,
                    "end_lap_pct": end_pct,
                    "anchor_lap_pct": turn["lap_pct"],
                    "placement_source": turn["placement_source"],
                    "confidence": confidence,
                }
            )

    straight_candidates: list[dict[str, Any]] = []
    for section in track_map.sections:
        if section.section_type == "corner" and turns:
            continue
        if section.section_type == "straight":
            label = _friendly_straight_region_label(section)
            kind = "straight"
        else:
            raw_label = section.name.strip()
            label = raw_label if raw_label and "motec" not in raw_label.casefold() else "Track Section"
            kind = section.section_type
        region = {
                "region_id": f"section:{section.section_id}",
                "kind": kind,
                "number": None,
                "label": label,
                "short_label": label,
                "start_lap_pct": float(section.start_lap_pct),
                "end_lap_pct": float(section.end_lap_pct),
                "anchor_lap_pct": _section_fraction_pct(section, 0.5),
                "placement_source": "source section geometry",
                "confidence": "section_geometry",
            }
        if kind == "straight" and turns:
            straight_candidates.append(region)
        else:
            regions.append(region)

    turn_regions = [region for region in regions if region["kind"] == "turn"]
    if turns:
        gap_candidates: list[dict[str, Any]] = []
        for index, region in enumerate(turn_regions):
            following = turn_regions[(index + 1) % len(turn_regions)]
            start_pct = float(region["end_lap_pct"])
            end_pct = float(following["start_lap_pct"])
            span = _lap_pct_offset(start_pct, end_pct)
            if span < 5.0:
                continue
            anchor_pct = _lap_pct_at_fraction(start_pct, end_pct, 0.5)
            label = "Front Stretch" if anchor_pct >= 75.0 or anchor_pct < 25.0 else "Backstretch"
            gap_candidates.append(
                {
                    "region_id": "",
                    "kind": "straight",
                    "number": None,
                    "label": label,
                    "short_label": label,
                    "start_lap_pct": start_pct,
                    "end_lap_pct": end_pct,
                    "anchor_lap_pct": anchor_pct,
                    "placement_source": "canonical gaps between turn regions",
                    "confidence": (
                        "section_geometry"
                        if region["confidence"] == following["confidence"] == "section_geometry"
                        else "centerline_geometry"
                    ),
                }
            )
        straight_candidates = gap_candidates

    if turns:
        primary_by_label: dict[str, dict[str, Any]] = {}
        for region in straight_candidates:
            label = str(region["label"])
            span = _lap_pct_offset(region["start_lap_pct"], region["end_lap_pct"])
            current = primary_by_label.get(label)
            current_span = (
                _lap_pct_offset(current["start_lap_pct"], current["end_lap_pct"])
                if current is not None
                else -1.0
            )
            if span > current_span:
                primary_by_label[label] = region
        primary_ids = {id(region) for region in primary_by_label.values()}
        connectors = sorted(
            (region for region in straight_candidates if id(region) not in primary_ids),
            key=lambda region: float(region["anchor_lap_pct"]),
        )
        for label, region in primary_by_label.items():
            region["region_id"] = (
                "straight:front_stretch" if label == "Front Stretch" else "straight:backstretch"
            )
            regions.append(region)
        for number, region in enumerate(connectors, start=1):
            region["region_id"] = f"straight:connector_{number}"
            region["label"] = f"Connector {number}"
            region["short_label"] = f"Conn {number}"
            regions.append(region)
    return regions


def locate_track_region(
    regions: list[dict[str, Any]],
    lap_pct: float | None,
) -> dict[str, Any] | None:
    """Resolve one physical lap position to a canonical region and phase."""
    if lap_pct is None or not math.isfinite(lap_pct):
        return None
    normalized = float(lap_pct) % 100.0
    ordered = sorted(regions, key=lambda region: 0 if region.get("kind") == "turn" else 1)
    for region in ordered:
        start_pct = float(region["start_lap_pct"])
        end_pct = float(region["end_lap_pct"])
        if not _lap_pct_in_region(start_pct, end_pct, normalized):
            continue
        span = _lap_pct_offset(start_pct, end_pct)
        fraction = _lap_pct_offset(start_pct, normalized) / span if span > 0.0 else 0.5
        if region.get("kind") == "turn":
            phase = "entry" if fraction < 1.0 / 3.0 else "center" if fraction <= 2.0 / 3.0 else "exit"
            display_label = f"{region['label']} {phase}"
        else:
            phase = "straight" if region.get("kind") == "straight" else None
            display_label = str(region["label"])
        return {
            "region_id": region["region_id"],
            "kind": region["kind"],
            "label": region["label"],
            "display_label": display_label,
            "phase": phase,
            "lap_pct": normalized,
            "confidence": region["confidence"],
        }
    return None


_TARGET_ZONE_ERROR = (
    "Target zone requires finite start and end positions satisfying "
    "0 <= start < end <= 100."
)


def validate_target_zone(
    start_pct: float | None,
    end_pct: float | None,
) -> tuple[float, float] | None:
    """Normalize a complete, bounded target zone or fail closed."""
    if start_pct is None and end_pct is None:
        return None
    if start_pct is None or end_pct is None:
        raise ValueError(_TARGET_ZONE_ERROR)
    if isinstance(start_pct, bool) or isinstance(end_pct, bool):
        raise ValueError(_TARGET_ZONE_ERROR)  # noqa: TRY004 - API validation uses one error contract
    try:
        start = float(start_pct)
        end = float(end_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError(_TARGET_ZONE_ERROR) from exc
    if (
        not math.isfinite(start)
        or not math.isfinite(end)
        or start < 0.0
        or end > 100.0
        or start >= end
    ):
        raise ValueError(_TARGET_ZONE_ERROR)
    return start, end

def build_track_map_overlays(
    map_id: str,
    platform_events: list[dict[str, Any]] | None = None,
    target_zone_start_pct: float | None = None,
    target_zone_end_pct: float | None = None,
    *,
    _track_map: TrackMap | None = None,
) -> list[dict[str, Any]]:
    """Build overlay markers from platform events and target zone."""
    overlays: list[dict[str, Any]] = []
    target_zone = validate_target_zone(target_zone_start_pct, target_zone_end_pct)

    track_map = _track_map or get_track_map(map_id)
    points = track_map.points if track_map else []
    total_dist = track_map.metadata.distance_m if track_map else 0.0

    # Platform event overlays
    if platform_events:
        for event in platform_events:
            pct = event.get("lap_pct")
            if pct is None:
                pct = event.get("position_pct")
            if pct is None:
                continue
            from racelab_engine.io.mt2_reader import interpolate_at_pct
            try:
                pos = interpolate_at_pct(points, pct, total_dist)
            except Exception:  # noqa: BLE001 - one malformed event must not remove the map
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
    if target_zone is not None and points and total_dist > 0:
        from racelab_engine.io.mt2_reader import interpolate_at_pct
        target_zone_start_pct, target_zone_end_pct = target_zone
        zone_points = []
        from contextlib import suppress
        span = target_zone_end_pct - target_zone_start_pct
        for sample_index in range(51):
            p = target_zone_start_pct + span * sample_index / 50.0
            with suppress(Exception):
                pos = interpolate_at_pct(points, p, total_dist)
                zone_points.append({"x": pos["x_m"], "y": pos["y_m"], "pct": p})
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
    target_zone = validate_target_zone(target_zone_start_pct, target_zone_end_pct)
    if target_zone is not None:
        target_zone_start_pct, target_zone_end_pct = target_zone
    track_map = get_track_map(map_id)
    entries = _load_index()
    match = next((e for e in entries if e.get("map_id") == map_id), None)
    turns = build_oval_turn_markers(track_map, match) if track_map else []
    regions = build_track_regions(track_map, match) if track_map else []

    overlays = build_track_map_overlays(
        map_id,
        platform_events=platform_events,
        target_zone_start_pct=target_zone_start_pct,
        target_zone_end_pct=target_zone_end_pct,
        _track_map=track_map,
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
        "turns": turns,
        "regions": regions,
        "target_zone": {
            "start_pct": target_zone_start_pct,
            "end_pct": target_zone_end_pct,
        } if target_zone is not None else None,
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
