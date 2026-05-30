from __future__ import annotations

import re
from pathlib import Path
from typing import Any


TRACK_NAME_MAP: dict[str, str] = {
    "atlanta motor speedway": "atlanta",
    "echopark speedway": "atlanta",
    "autoclub speedway": "california",
    "bristol motor speedway": "bristol",
    "charlotte motor speedway": "charlotte",
    "chicagoland speedway": "chicagoland",
    "darlington raceway": "darlington",
    "daytona international speedway": "daytona",
    "dover international speedway": "dover",
    "gateway motorsports park": "gateway",
    "homestead miami speedway": "homestead",
    "indianapolis motor speedway": "indianapolis",
    "iowa speedway": "iowa",
    "irwindale speedway": "irwindale",
    "kansas speedway": "kansas",
    "kentucky speedway": "kentucky",
    "las vegas motor speedway": "vegas",
    "martinsville speedway": "martinsville",
    "michigan international speedway": "michigan",
    "myrtle beach speedway": "myrtlebeach",
    "new hampshire motor speedway": "newhampshire",
    "new smyrna speedway": "newsmyrna",
    "north wilkesboro speedway": "northwilkesboro",
    "phoenix raceway": "phoenix",
    "richmond raceway": "richmond",
    "rockingham speedway": "rockingham",
    "stafford motor speedway": "stafford",
    "talladega super speedway": "talladega",
    "talladega superspeedway": "talladega",
    "texas motor speedway": "texas",
    # TODO: Road course name mappings are incomplete.  Known iRacing names that
    # may not fuzzy-match our indexed track_keys include:
    #   "Road America", "Road Atlanta", "Sebring International Raceway",
    #   "WeatherTech Raceway Laguna Seca", "Lime Rock Park", "Mid-Ohio Sports Car Course",
    #   "Canadian Tire Motorsports Park" (Mosport), "Circuit Gilles Villeneuve" (Montreal),
    #   "Mount Panorama Circuit" (Bathurst), "Silverstone Circuit", "Spa-Francorchamps",
    #   "Autodromo Jose Carlos Pace" (Interlagos), "Phillip Island Circuit",
    #   "Suzuka International Racing Course", "Circuit Zolder", "Circuit Park Zandvoort",
    #   "Donington Park", "Brands Hatch", "Oulton Park", "Okayama International Circuit",
    #   "Twin Ring Motegi", "Virginia International Raceway", "Watkins Glen International",
    #   "Sonoma Raceway", "Summit Point Motorsports Park".
    # Users can bypass autodetection by passing ?preferred_map_id=<map_id> on
    # the /api/runs/{run_id}/track-map-package endpoint.
}


def normalize_track_key(name: str | None) -> str:
    if not name:
        return "unknown"
    normalized = name.strip().lower()
    # Remove common suffixes
    for suffix in [" speedway", " raceway", " international speedway", " motor speedway",
                   " superspeedway", " super speedway", " motorsports park"]:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    # Use map first
    for full, short in TRACK_NAME_MAP.items():
        if full in normalized or normalized in full:
            return short
    # Slugify
    key = re.sub(r"[^a-z0-9]", "", normalized)
    return key or "unknown"


def infer_layout_key(filename_or_name: str | None) -> str:
    if not filename_or_name:
        return "default"
    lower = filename_or_name.strip().lower()
    if "roval" in lower:
        return "roval"
    if "dirt" in lower:
        return "dirt"
    if "oval" in lower:
        return "oval"
    if "road" in lower:
        return "road"
    if "fullpit" in lower:
        return "fullpit"
    if "outer" in lower:
        return "outer"
    return "default"


def build_map_id(track_key: str, layout_key: str, sha_or_name: str) -> str:
    return f"{track_key}_{layout_key}_{sha_or_name.lower()[:12]}"


def score_track_map_match(
    run_track_name: str,
    run_layout: str | None,
    map_track_name: str,
    map_layout: str | None,
    map_filename: str,
) -> tuple[str, int]:
    """Return (confidence: high/medium/low/none, score) for a track map match."""
    norm_run = normalize_track_key(run_track_name)
    norm_map = normalize_track_key(map_track_name)
    layout_run = run_layout or infer_layout_key(run_track_name)
    layout_map = map_layout or infer_layout_key(map_filename or map_track_name)

    if norm_run == "unknown" or norm_map == "unknown":
        return "none", 0

    score = 0
    if norm_run == norm_map:
        score += 60  # track name match is strongest signal
    elif norm_run in norm_map or norm_map in norm_run:
        score += 30

    if layout_run == layout_map:
        score += 30  # layout match
    else:
        # Less common layouts still get partial if track matches
        score += 10

    # Filename containing track key is a bonus
    if norm_run in (map_filename or "").lower():
        score += 10

    if score >= 80:
        return "high", score
    if score >= 50:
        return "medium", score
    if score >= 20:
        return "low", score
    return "none", score


def match_track_map_for_run(
    run_track_name: str,
    run_layout: str | None,
    available_maps: list[dict[str, Any]],
    preferred_map_id: str | None = None,
) -> dict[str, Any] | None:
    """Return the best matching map entry dict, or None.

    If *preferred_map_id* is given:
      - returns the entry with confidence='manual' if found
      - returns None if not found (caller should 404)
    """
    # ── manual override ──
    if preferred_map_id:
        for entry in available_maps:
            if entry.get("map_id") == preferred_map_id:
                entry["match_confidence"] = "manual"
                entry["match_score"] = 100
                return entry
        # Explicitly requested but not found — do NOT fall through to auto-match
        return None
    best_score = -1
    best_match: dict[str, Any] | None = None
    best_confidence = "none"

    for entry in available_maps:
        conf, score = score_track_map_match(
            run_track_name,
            run_layout,
            entry.get("track_key", ""),
            entry.get("layout_key"),
            entry.get("source_filename", ""),
        )
        if score > best_score:
            best_score = score
            best_confidence = conf
            best_match = entry

    if best_match and best_confidence in ("high", "medium"):
        best_match["match_confidence"] = best_confidence
        best_match["match_score"] = best_score
        return best_match
    return None
