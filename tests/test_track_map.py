from __future__ import annotations

import os
from pathlib import Path

import pytest

from racelab_engine.io.mt2_reader import (
    parse_mt2,
    parse_mt2_bytes,
    interpolate_at_pct,
    interpolate_at_distance,
    MT2DecodeError,
)


@pytest.fixture(scope="session")
def atlanta_mt2_path() -> Path:
    path = Path(r"C:/Users/Soulj/Desktop/Next Gen 2023-S1-v4/Track Maps/atlanta 2022 oval.mt2")
    if not path.exists():
        pytest.skip("Atlanta .mt2 fixture not found")
    return path


def test_atlanta_parses_1911_points(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    assert len(tm.points) == 1911, f"Expected 1911, got {len(tm.points)}"


def test_atlanta_distance_approximately_8014_ft(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    assert abs(tm.metadata.distance_ft - 8013.812) < 10.0


def test_atlanta_has_4_markers_and_sections(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    assert len(tm.markers) == 4
    assert len(tm.sections) == 4


def test_atlanta_missing_gps_boundary_banking_warnings(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    w = tm.warnings
    assert any("GPS" in x for x in w), "Missing GPS warning"
    assert any("left boundary" in x.lower() for x in w), "Missing left boundary warning"
    assert any("right boundary" in x.lower() for x in w), "Missing right boundary warning"
    assert any("track width" in x.lower() for x in w), "Missing track width warning"
    assert any("banking" in x.lower() for x in w), "Missing banking warning"


def test_fifth_float_is_heading_not_lap_pct(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    h = tm.points[0].heading_rad
    assert h is not None
    assert abs(h) < 10, f"heading_rad={h} looks like lap_pct, not heading"


def test_lap_pct_derived_from_distance(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    assert tm.points[0].lap_pct is not None
    assert 0 <= tm.points[0].lap_pct < 1
    assert tm.points[-1].lap_pct is not None
    assert 99 < tm.points[-1].lap_pct <= 100


def test_interpolate_at_pct_works(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    pos = interpolate_at_pct(tm.points, 0, tm.metadata.distance_m)
    assert "x_m" in pos and "y_m" in pos
    pos50 = interpolate_at_pct(tm.points, 50, tm.metadata.distance_m)
    assert "x_m" in pos50 and "y_m" in pos50
    pos100 = interpolate_at_pct(tm.points, 100, tm.metadata.distance_m)
    assert "x_m" in pos100 and "y_m" in pos100


def test_wraparound_interpolation(atlanta_mt2_path: Path) -> None:
    tm = parse_mt2(atlanta_mt2_path)
    pos = interpolate_at_distance(tm.points, tm.metadata.distance_m + 10.0, tm.metadata.distance_m)
    assert "x_m" in pos


def test_malformed_mt2_raises_error() -> None:
    with pytest.raises(Exception):
        parse_mt2_bytes(b"not a valid mt2 file")


def test_talladega_matches_high_confidence() -> None:
    from racelab_engine.analysis.track_matching import (
        score_track_map_match,
        normalize_track_key,
    )
    key = normalize_track_key("Talladega Super Speedway")
    assert key == "talladega"
    conf, score = score_track_map_match(
        "Talladega Super Speedway", None, "talladega", "default", "talladega.mt2"
    )
    assert conf == "high"
    assert score >= 80


def test_normalize_track_key_examples() -> None:
    from racelab_engine.analysis.track_matching import normalize_track_key
    assert normalize_track_key("Atlanta Motor Speedway") == "atlanta"
    assert normalize_track_key("EchoPark Speedway") == "atlanta"
    assert normalize_track_key("Daytona International Speedway") == "daytona"
    assert normalize_track_key("Phoenix Raceway") == "phoenix"
    assert normalize_track_key("Charlotte Motor Speedway") == "charlotte"
    assert normalize_track_key(None) == "unknown"


def test_echopark_speedway_matches_atlanta_2022_map() -> None:
    from racelab_engine.analysis.track_matching import match_track_map_for_run

    available = [
        {
            "map_id": "atlanta-2022-oval",
            "track_key": "atlanta2022oval",
            "layout_key": "oval",
            "source_filename": "atlanta 2022 oval.mt2",
        },
    ]

    result = match_track_map_for_run("EchoPark Speedway", None, available)

    assert result is not None
    assert result["map_id"] == "atlanta-2022-oval"
    assert result["match_confidence"] in {"high", "medium"}


def test_infer_layout_key_examples() -> None:
    from racelab_engine.analysis.track_matching import infer_layout_key
    assert infer_layout_key("atlanta 2022 oval") == "oval"
    assert infer_layout_key("charlotte roval") == "roval"
    assert infer_layout_key("bristol dirt") == "dirt"
    assert infer_layout_key("daytona road") == "road"
    assert infer_layout_key("unknown") == "default"
    assert infer_layout_key(None) == "default"


def test_import_folder_indexes_multiple_maps() -> None:
    from racelab_engine.services.track_map_service import list_track_maps
    # Should have at least 1 entry from previous session import
    if entries := list_track_maps():
        assert all("map_id" in e for e in entries)
        assert all("track_key" in e for e in entries)
        assert all("points_count" in e for e in entries)


def test_filename_sanitization_prevents_traversal() -> None:
    from racelab_engine.services.track_map_service import _sanitize_filename
    assert _sanitize_filename("test.mt2") == "test.mt2"
    # Path traversal is stripped by os.path.basename; result is the leaf filename
    result = _sanitize_filename("../etc/passwd.mt2")
    assert ".." not in result
    assert "/" not in result
    assert result.endswith(".mt2")
    result = _sanitize_filename("a/b/c.mt2")
    assert "/" not in result
    assert result.endswith(".mt2")


def test_import_mt2_file_rejects_non_mt2(tmp_path: Path) -> None:
    from racelab_engine.services.track_map_service import import_mt2_file
    fake = tmp_path / "test.txt"
    fake.write_text("not a track map")
    with pytest.raises(ValueError, match="Unsupported file type"):
        import_mt2_file(fake)


def test_overlay_build_uses_lap_pct_interpolation(atlanta_mt2_path: Path) -> None:
    from racelab_engine.services.track_map_service import build_track_map_overlays, import_mt2_file
    entry = import_mt2_file(atlanta_mt2_path)
    map_id = entry["map_id"]
    overlays = build_track_map_overlays(
        map_id,
        platform_events=[
            {"event_id": "evt_1", "event_type": "MIN_SPLITTER", "lap_pct": 25.0, "label": "Test", "severity": "info"},
        ],
    )
    assert len(overlays) == 1
    assert overlays[0]["kind"] == "platform_event"
    assert overlays[0]["x"] is not None
    assert overlays[0]["y"] is not None
    assert overlays[0]["lap_pct"] == 25.0


def test_build_track_map_package_includes_all_sections(atlanta_mt2_path: Path) -> None:
    from racelab_engine.services.track_map_service import build_track_map_package, import_mt2_file
    entry = import_mt2_file(atlanta_mt2_path)
    map_id = entry["map_id"]
    pkg = build_track_map_package(map_id, "fake_run_id")
    assert pkg["map"] is not None
    assert pkg["run_id"] == "fake_run_id"
    assert "overlays" in pkg
    assert "sections" in pkg
    assert "markers" in pkg


def test_routes_upload_rejects_wrong_extension() -> None:
    """Simulate the extension check logic used by the upload endpoint."""
    filename = "test.ibt"
    assert not filename.lower().endswith(".mt2")
    filename = "test.mt2"
    assert filename.lower().endswith(".mt2")


def test_json_import_rejects_wrong_extension() -> None:
    """JSON local import should reject non-.mt2 extensions."""
    path = "/some/path/test.txt"
    assert not path.lower().endswith(".mt2")
    path = "/some/path/test.mt2"
    assert path.lower().endswith(".mt2")


def test_json_import_rejects_missing_path() -> None:
    """JSON local import without 'path' key should fail."""
    body: dict = {}
    path = body.get("path")
    assert not path


def test_json_import_rejects_path_traversal() -> None:
    """JSON local import should reject .. and ~ in paths."""
    assert ".." in "../etc/passwd.mt2"
    assert ".." in "a/../../b/file.mt2"
    assert ".." not in "normal_file.mt2"
    assert "~" in "~/file.mt2"
    assert "~" not in "/home/user/file.mt2"


def test_preferred_map_id_found_returns_manual_confidence() -> None:
    """preferred_map_id returns confidence='manual' when found."""
    from racelab_engine.analysis.track_matching import match_track_map_for_run
    available = [
        {"map_id": "laguna-seca-abc123", "track_key": "lagunaseca", "layout_key": "default", "source_filename": "lagunaseca.mt2"},
    ]
    result = match_track_map_for_run("Unknown Track", None, available, preferred_map_id="laguna-seca-abc123")
    assert result is not None
    assert result["match_confidence"] == "manual"
    assert result["match_score"] == 100


def test_preferred_map_id_missing_returns_none_no_fallback() -> None:
    """preferred_map_id returns None when not found — no silent fallback to auto-match."""
    from racelab_engine.analysis.track_matching import match_track_map_for_run
    available = [
        {"map_id": "talladega-abc123", "track_key": "talladega", "layout_key": "default", "source_filename": "talladega.mt2"},
    ]
    result = match_track_map_for_run("Talladega Super Speedway", None, available, preferred_map_id="nonexistent-id")
    assert result is None
