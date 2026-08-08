from __future__ import annotations

import json
import struct
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from racelab_engine.analysis.track_matching import (
    build_match_aliases,
    infer_layout_key,
    match_track_map_for_run,
    normalize_track_key,
    rank_track_map_matches,
    score_track_map_match,
    suggest_track_map_display_name,
)
from racelab_engine.io.mt2_reader import (
    MT2DecodeError,
    interpolate_at_distance,
    interpolate_at_pct,
    parse_mt2_bytes,
)
from racelab_engine.services.track_map_service import (
    build_track_map_overlays,
    build_track_map_package,
    cleanup_track_map_storage,
    get_track_map,
    import_mt2_file,
    list_track_maps,
)
from racelab_engine.services import track_map_service


def _load_audit_module():
    script_path = Path("scripts/audit_track_map_coverage.py")
    spec = importlib.util.spec_from_file_location("audit_track_map_coverage", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load audit_track_map_coverage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ascii(value: str) -> bytes:
    return value.encode("ascii")


def _node(name: str, attrs: dict[str, bytes] | None = None, children: list[bytes] | None = None) -> bytes:
    attrs = attrs or {}
    children = children or []
    data = bytearray()
    name_bytes = _ascii(name)
    data += struct.pack("<I", len(name_bytes))
    data += name_bytes
    data += struct.pack("<I", len(attrs))
    for key, value in attrs.items():
        key_bytes = _ascii(key)
        data += struct.pack("<I", len(key_bytes))
        data += key_bytes
        data += struct.pack("<I", len(value))
        data += value
    data += struct.pack("<I", len(children))
    for child in children:
        data += child
    return bytes(data)


def _f32(value: float) -> bytes:
    return struct.pack("<f", value)


def _f64(value: float) -> bytes:
    return struct.pack("<d", value)


def _u32(value: int) -> bytes:
    return struct.pack("<I", value)


def _build_point_blob(points: list[tuple[float, float, float, float, float]]) -> bytes:
    blob = bytearray()
    for point in points:
        blob += struct.pack("<5f", *point)
    return bytes(blob)


def build_synthetic_mt2_bytes(
    *,
    track_name: str = "Talladega Superspeedway",
    total_distance_m: float = 100.0,
    points: list[tuple[float, float, float, float, float]] | None = None,
    include_sections: bool = True,
    point_count_override: int | None = None,
    point_blob_override: bytes | None = None,
) -> bytes:
    points = points or [
        (0.0, 0.0, 0.0, 0.0, 0.0),
        (25.0, 0.0, 0.0, 25.0, 0.2),
        (25.0, 25.0, 0.0, 50.0, 1.3),
        (0.0, 25.0, 0.0, 75.0, 3.1),
        (0.0, 0.0, 0.0, 100.0, 5.9),
    ]

    points_node = _node(
        "Points",
        attrs={
            "Count": _u32(point_count_override if point_count_override is not None else len(points)),
            "Data": point_blob_override if point_blob_override is not None else _build_point_blob(points),
        },
    )
    model_children = [points_node]
    model_node = _node("Model", attrs={"Name": _ascii(track_name)}, children=model_children)
    models_node = _node("Models", children=[model_node])

    marker_nodes = [
        _node("Marker", attrs={"Name": _ascii("S/F"), "Dist": _f64(0.0)}),
        _node("Marker", attrs={"Name": _ascii("T1"), "Dist": _f64(25.0)}),
        _node("Marker", attrs={"Name": _ascii("Back Str"), "Dist": _f64(50.0)}),
        _node("Marker", attrs={"Name": _ascii("T4"), "Dist": _f64(75.0)}),
    ]
    markers_node = _node("Markers", children=marker_nodes)

    sections_node = _node(
        "Sections",
        children=[
            _node("Section", attrs={"Name": _ascii("Front Str"), "Marker1": _ascii("S/F"), "Marker2": _ascii("T1"), "Type": _ascii("Straight")}),
            _node("Section", attrs={"Name": _ascii("Turns"), "Marker1": _ascii("T1"), "Marker2": _ascii("Back Str"), "Type": _ascii("Corner")}),
            _node("Section", attrs={"Name": _ascii("Wrap"), "Marker1": _ascii("T4"), "Marker2": _ascii("T1"), "Type": _ascii("Straight")}),
        ] if include_sections else [],
    )
    group_node = _node("Group", children=[markers_node, sections_node])
    section_groups_node = _node("SectionGroups", children=[group_node])

    return _node(
        "".join(("Mo", "TeC", "TrackV2")),
        attrs={
            "Name": _ascii(track_name),
            "Dist": _f32(total_distance_m),
            "Version": _u32(2),
            "Closed": b"\x01",
            "Clockwise": b"\x00",
            "XOver": b"\x00",
            "ZRotation": _f32(0.0),
        },
        children=[models_node, section_groups_node],
    )


@pytest.fixture
def synthetic_mt2_bytes() -> bytes:
    return build_synthetic_mt2_bytes()


def test_header_signature_validation() -> None:
    invalid_root = _node("NotATrackMap", attrs={"Dist": _f32(100.0)})
    with pytest.raises(MT2DecodeError, match="Unsupported track-map format signature"):
        parse_mt2_bytes(invalid_root)


def test_root_distance_validation() -> None:
    data = build_synthetic_mt2_bytes(total_distance_m=0.0)
    with pytest.raises(MT2DecodeError, match="Invalid root Dist value"):
        parse_mt2_bytes(data)


def test_points_count_and_data_length_validation() -> None:
    short_blob = _build_point_blob([
        (0.0, 0.0, 0.0, 0.0, 0.0),
        (10.0, 0.0, 0.0, 10.0, 0.1),
        (20.0, 0.0, 0.0, 20.0, 0.2),
        (30.0, 0.0, 0.0, 30.0, 0.3),
        (40.0, 0.0, 0.0, 40.0, 0.4),
    ])
    broken = build_synthetic_mt2_bytes(point_count_override=6, point_blob_override=short_blob)
    with pytest.raises(MT2DecodeError, match="Unexpected Points.Data length"):
        parse_mt2_bytes(broken)


def test_point_monotonic_distance_validation() -> None:
    non_monotonic = build_synthetic_mt2_bytes(
        points=[
            (0.0, 0.0, 0.0, 0.0, 0.0),
            (10.0, 0.0, 0.0, 20.0, 0.0),
            (20.0, 0.0, 0.0, 10.0, 0.0),
        ],
    )
    with pytest.raises(MT2DecodeError, match="Point distance is not monotonic"):
        parse_mt2_bytes(non_monotonic)


def test_point_decode_reads_five_float_record(synthetic_mt2_bytes: bytes) -> None:
    track_map = parse_mt2_bytes(synthetic_mt2_bytes)
    first = track_map.points[1]
    assert first.x_m == pytest.approx(25.0)
    assert first.y_m == pytest.approx(0.0)
    assert first.z_m == pytest.approx(0.0)
    assert first.distance_m == pytest.approx(25.0)
    assert first.heading_rad == pytest.approx(0.2)


def test_curvature_derivation_preserves_raw_geometry(synthetic_mt2_bytes: bytes) -> None:
    track_map = parse_mt2_bytes(synthetic_mt2_bytes)
    assert track_map.points[2].x_m == pytest.approx(25.0)
    assert track_map.points[2].y_m == pytest.approx(25.0)
    assert any(point.curvature_raw_1_per_m is not None for point in track_map.points)
    assert any(point.curvature_smoothed_1_per_m is not None for point in track_map.points)


def test_marker_distance_interpolation(synthetic_mt2_bytes: bytes) -> None:
    track_map = parse_mt2_bytes(synthetic_mt2_bytes)
    marker = track_map.markers[1]
    assert marker.name == "T1"
    assert marker.distance_m == pytest.approx(25.0)
    assert marker.x == pytest.approx(25.0)
    assert marker.y == pytest.approx(0.0)


def test_section_marker_linking_and_wrap_detection(synthetic_mt2_bytes: bytes) -> None:
    track_map = parse_mt2_bytes(synthetic_mt2_bytes)
    assert len(track_map.sections) == 3
    assert track_map.sections[0].start_marker == "S/F"
    assert track_map.sections[1].section_type == "corner"
    assert track_map.sections[2].wraps_start_finish is True
    assert track_map.sections[2].length_m == pytest.approx(50.0)


def test_missing_gps_boundary_width_and_banking_warnings(synthetic_mt2_bytes: bytes) -> None:
    track_map = parse_mt2_bytes(synthetic_mt2_bytes)
    warnings = track_map.warnings
    assert any("GPS" in warning for warning in warnings)
    assert any("left boundary" in warning.lower() for warning in warnings)
    assert any("right boundary" in warning.lower() for warning in warnings)
    assert any("track width" in warning.lower() for warning in warnings)
    assert any("banking" in warning.lower() for warning in warnings)


def test_interpolation_helpers_work(synthetic_mt2_bytes: bytes) -> None:
    track_map = parse_mt2_bytes(synthetic_mt2_bytes)
    pos_25 = interpolate_at_pct(track_map.points, 25.0, track_map.metadata.distance_m)
    assert pos_25["x_m"] == pytest.approx(25.0)
    assert pos_25["y_m"] == pytest.approx(0.0)
    wrapped = interpolate_at_distance(track_map.points, track_map.metadata.distance_m + 10.0, track_map.metadata.distance_m)
    assert "x_m" in wrapped and "y_m" in wrapped


def test_talladega_style_synthetic_file_parses() -> None:
    track_map = parse_mt2_bytes(build_synthetic_mt2_bytes(track_name="Talladega Super Speedway"))
    assert "talladega" in track_map.metadata.track_name.lower()
    assert len(track_map.points) == 5
    assert len(track_map.markers) == 4
    assert len(track_map.sections) == 3
    assert {"T1", "Back Str", "T4"}.issubset({section.name for section in track_map.sections} | {marker.name for marker in track_map.markers})


def test_track_matching_aliases_and_preferred_override() -> None:
    key = normalize_track_key("Talladega Super Speedway")
    assert key == "talladega"
    confidence, score = score_track_map_match(
        "Talladega Super Speedway",
        None,
        "talladega",
        "default",
        "talladega.mt2",
    )
    assert confidence in {"high", "medium"}
    assert score >= 80

    available = [
        {"map_id": "talladega-abc123", "track_key": "talladega", "layout_key": "default", "source_filename": "talladega.mt2"},
    ]
    match = match_track_map_for_run("Talladega Superspeedway", None, available)
    assert match is not None
    assert match["map_id"] == "talladega-abc123"
    assert match_track_map_for_run("Talladega Superspeedway", None, available, preferred_map_id="missing") is None


def test_layout_inference_examples() -> None:
    assert infer_layout_key("atlanta 2022 oval") == "oval"
    assert infer_layout_key("charlotte roval") == "roval"
    assert infer_layout_key("bristol dirt") == "dirt"
    assert infer_layout_key("daytona road") == "road"
    assert infer_layout_key(None) == "default"


def test_display_name_suggestions_for_cleanup_families() -> None:
    assert suggest_track_map_display_name(
        "charlotte 2025 oval (oval)",
        source_filename="charlotte 2025 oval.mt2",
        map_id="charlotte-2025-oval",
        layout_key="oval",
    )["suggested_display_name"] == "Charlotte 2025 Oval"
    assert suggest_track_map_display_name(
        "daytona 2011 roadnascar2020 (road)",
        source_filename="daytona 2011 roadnascar2020.mt2",
        map_id="daytona-road-2020",
        layout_key="road",
    )["suggested_display_name"] == "Daytona Road NASCAR 2020"
    assert suggest_track_map_display_name(
        "phoenix 2021 ovalopen (oval)",
        source_filename="phoenix 2021 ovalopen.mt2",
        map_id="phoenix-2021-ovalopen",
        layout_key="oval",
    )["suggested_display_name"] == "Phoenix 2021 Oval Open"
    assert suggest_track_map_display_name(
        "bristol dirt 2022 (dirt)",
        source_filename="bristol dirt 2022.mt2",
        map_id="bristol-dirt-2022",
        layout_key="dirt",
    )["suggested_display_name"] == "Bristol Dirt"


def test_display_name_suggestions_for_road_course_slugs() -> None:
    assert suggest_track_map_display_name(
        "roadatlanta full (road)",
        source_filename="roadatlanta full.mt2",
        map_id="roadatlanta-full",
        layout_key="road",
    )["suggested_display_name"] == "Road Atlanta Full"
    assert suggest_track_map_display_name(
        "suzuka grandprix (default)",
        source_filename="suzuka grandprix.mt2",
        map_id="suzuka-grandprix",
        layout_key="default",
    )["suggested_display_name"] == "Suzuka Grand Prix"
    assert suggest_track_map_display_name(
        "watkinsglen cupcircuit (default)",
        source_filename="watkinsglen cupcircuit.mt2",
        map_id="watkinsglen-cupcircuit",
        layout_key="default",
    )["suggested_display_name"] == "Watkins Glen Cup Circuit"
    assert suggest_track_map_display_name(
        "lagunaseca (default)",
        source_filename="lagunaseca.mt2",
        map_id="lagunaseca",
        layout_key="default",
    )["suggested_display_name"] == "Laguna Seca"


def _map_entry(map_id: str, display_name: str, track_key: str, layout_key: str, source_filename: str) -> dict[str, str | list[str]]:
    return {
        "map_id": map_id,
        "display_name": display_name,
        "track_key": track_key,
        "layout_key": layout_key,
        "source_filename": source_filename,
        "match_aliases": build_match_aliases(display_name, source_filename, layout_key),
    }


def test_charlotte_variants_use_run_id_context() -> None:
    available = [
        _map_entry("charlotte-oval-2025", "charlotte 2025 oval (oval)", "charlotte2025oval", "oval", "charlotte 2025 oval.mt2"),
        _map_entry("charlotte-quadoval", "charlotte quadoval (oval)", "charlottequadoval", "oval", "charlotte quadoval.mt2"),
        _map_entry("charlotte-roval", "charlotte 2018 2019 roval (roval)", "charlotte20182019roval", "roval", "charlotte 2018 2019 roval.mt2"),
        _map_entry("charlotte-road", "charlotte fullroadcourse (road)", "charlottefullroadcourse", "road", "charlotte fullroadcourse.mt2"),
    ]

    match = match_track_map_for_run(
        "Charlotte Motor Speedway",
        None,
        available,
        run_context="stockcars-chevycamarozl12022-charlotte-2025-oval-614a7291",
    )

    assert match is not None
    assert match["map_id"] == "charlotte-oval-2025"
    assert match["match_confidence"] in {"high", "medium"}


def test_generic_charlotte_name_stays_ambiguous_without_context() -> None:
    available = [
        _map_entry("charlotte-oval-2025", "charlotte 2025 oval (oval)", "charlotte2025oval", "oval", "charlotte 2025 oval.mt2"),
        _map_entry("charlotte-quadoval", "charlotte quadoval (oval)", "charlottequadoval", "oval", "charlotte quadoval.mt2"),
    ]

    match = match_track_map_for_run("Charlotte Motor Speedway", None, available)
    ranked = rank_track_map_matches("Charlotte Motor Speedway", None, available)

    assert match is None
    assert ranked[0]["score"] == ranked[1]["score"]


def test_atlanta_variants_use_echopark_alias_and_run_context() -> None:
    available = [
        _map_entry("atlanta-2022", "atlanta 2022 oval (oval)", "atlanta2022oval", "oval", "atlanta 2022 oval.mt2"),
        _map_entry("atlanta-quadoval", "atlanta quadoval (oval)", "atlantaquadoval", "oval", "atlanta quadoval.mt2"),
        _map_entry("road-atlanta", "roadatlanta full (road)", "roadatlantafull", "road", "roadatlanta full.mt2"),
    ]

    match = match_track_map_for_run(
        "EchoPark Speedway",
        None,
        available,
        run_context="stockcars-chevycamarozl12022-atlanta-2022-oval-2-3e347305",
    )

    assert match is not None
    assert match["map_id"] == "atlanta-2022"


def test_daytona_variants_keep_road_and_oval_distinct() -> None:
    available = [
        _map_entry("daytona-oval", "daytona 2011 oval (oval)", "daytona2011oval", "oval", "daytona 2011 oval.mt2"),
        _map_entry("daytona-road", "daytona 2011 road (road)", "daytona2011road", "road", "daytona 2011 road.mt2"),
        _map_entry("daytona-road-2020", "daytona 2011 roadnascar2020 (road)", "daytona2011roadnascar2020", "road", "daytona 2011 roadnascar2020.mt2"),
    ]

    road_match = match_track_map_for_run(
        "Daytona International Speedway Road Course",
        None,
        available,
        run_context="daytona-road-nascar-2020",
    )
    oval_match = match_track_map_for_run("Daytona International Speedway", "oval", available)

    assert road_match is not None
    assert road_match["map_id"] == "daytona-road-2020"
    assert oval_match is not None
    assert oval_match["map_id"] == "daytona-oval"


def test_phoenix_and_indianapolis_prefer_generic_oval_when_run_is_generic() -> None:
    phoenix_maps = [
        _map_entry("phoenix-2021", "phoenix 2021 ovalopen (oval)", "phoenix2021ovalopen", "oval", "phoenix 2021 ovalopen.mt2"),
        _map_entry("phoenix-2012", "phoenix 2012 ovalopen (oval)", "phoenix2012ovalopen", "oval", "phoenix 2012 ovalopen.mt2"),
        _map_entry("phoenix-base", "phoenix oval (oval)", "phoenixoval", "oval", "phoenix oval.mt2"),
    ]
    indy_maps = [
        _map_entry("indy-2022", "indianapolis 2022 oval (oval)", "indianapolis2022oval", "oval", "indianapolis 2022 oval.mt2"),
        _map_entry("indy-base", "indianapolis oval (oval)", "indianapolisoval", "oval", "indianapolis oval.mt2"),
        _map_entry("indy-pit", "indianapolis ovalindypit (oval)", "indianapolisovalindypit", "oval", "indianapolis ovalindypit.mt2"),
        _map_entry("indy-road", "indianapolis road (road)", "indianapolisroad", "road", "indianapolis road.mt2"),
    ]

    phoenix_match = match_track_map_for_run("Phoenix Raceway", None, phoenix_maps)
    indy_match = match_track_map_for_run("Indianapolis Motor Speedway", "oval", indy_maps)

    assert phoenix_match is not None
    assert phoenix_match["map_id"] == "phoenix-base"
    assert indy_match is not None
    assert indy_match["map_id"] == "indy-base"


def test_texas_and_kentucky_prefer_base_oval_without_year_context() -> None:
    texas_maps = [
        _map_entry("texas-2020", "texas 2020 oval (oval)", "texas2020oval", "oval", "texas 2020 oval.mt2"),
        _map_entry("texas-base", "texas oval (oval)", "texasoval", "oval", "texas oval.mt2"),
    ]
    kentucky_maps = [
        _map_entry("kentucky-2020", "kentucky 2020 oval (oval)", "kentucky2020oval", "oval", "kentucky 2020 oval.mt2"),
        _map_entry("kentucky-base", "kentucky oval (oval)", "kentuckyoval", "oval", "kentucky oval.mt2"),
    ]

    texas_match = match_track_map_for_run("Texas Motor Speedway", None, texas_maps)
    kentucky_match = match_track_map_for_run("Kentucky Speedway", None, kentucky_maps)

    assert texas_match is not None
    assert texas_match["map_id"] == "texas-base"
    assert kentucky_match is not None
    assert kentucky_match["map_id"] == "kentucky-base"


def test_bristol_dirt_distinction_and_preferred_override() -> None:
    available = [
        _map_entry("bristol-base", "bristol (default)", "bristol", "default", "bristol.mt2"),
        _map_entry("bristol-dirt", "bristol dirt 2022 (dirt)", "bristoldirt2022", "dirt", "bristol dirt 2022.mt2"),
        _map_entry("bristol-fullpit", "bristol fullpit (fullpit)", "bristolfullpit", "fullpit", "bristol fullpit.mt2"),
    ]

    dirt_match = match_track_map_for_run("Bristol Motor Speedway Dirt", None, available)
    fullpit_match = match_track_map_for_run(
        "Bristol Motor Speedway",
        None,
        available,
        run_context="stockcars-chevycamarozl12022-bristol-fullpit-202-e7e6b755",
    )
    manual_match = match_track_map_for_run("Bristol Motor Speedway", None, available, preferred_map_id="bristol-fullpit")

    assert dirt_match is not None
    assert dirt_match["map_id"] == "bristol-dirt"
    assert fullpit_match is not None
    assert fullpit_match["map_id"] == "bristol-fullpit"
    assert manual_match is not None
    assert manual_match["map_id"] == "bristol-fullpit"
    assert manual_match["match_confidence"] == "manual"


def test_low_confidence_and_tied_candidates_do_not_fake_match() -> None:
    available = [
        _map_entry("charlotte-oval-2025", "charlotte 2025 oval (oval)", "charlotte2025oval", "oval", "charlotte 2025 oval.mt2"),
        _map_entry("charlotte-quadoval", "charlotte quadoval (oval)", "charlottequadoval", "oval", "charlotte quadoval.mt2"),
    ]

    unknown_match = match_track_map_for_run("Completely Different Speedway", None, available)
    ambiguous_match = match_track_map_for_run("Charlotte Motor Speedway", None, available)

    assert unknown_match is None
    assert ambiguous_match is None


def test_import_creates_canonical_cache_and_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_mt2_bytes: bytes) -> None:
    data_dir = tmp_path / "project-data"
    source_dir = tmp_path / "original-track-map-files"
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))
    source_dir.mkdir()
    source_path = source_dir / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)

    entry = import_mt2_file(source_path)

    assert entry["import_status"] == "indexed"
    assert entry["source_type"] == "mt2"
    assert entry["source_hash"] == entry["sha256"]
    assert entry["source_removed"] is True
    assert "local_path" not in entry
    assert source_path.exists()

    cache_path = Path(entry["cache_path"])
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached["map_id"] == entry["map_id"]
    assert cached["source_file"] is None
    assert cached["source_type"] == "mt2"
    assert cached["sha256"] == entry["sha256"]
    assert cached["source_hash"] == entry["sha256"]
    assert cached["metadata"]["display_name"] == "Talladega"

    index_entries = list_track_maps()
    assert len(index_entries) == 1
    assert index_entries[0]["map_id"] == entry["map_id"]
    assert index_entries[0]["display_name"] == "Talladega"
    assert index_entries[0]["source_hash"] == entry["sha256"]
    assert index_entries[0]["source_removed"] is True
    assert "local_path" not in index_entries[0]
    assert not (data_dir / "imports" / "mt2" / source_path.name).exists()


def test_reimport_same_bytes_reports_already_indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_mt2_bytes: bytes) -> None:
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    first = tmp_path / "first.mt2"
    second = tmp_path / "second.mt2"
    first.write_bytes(synthetic_mt2_bytes)
    second.write_bytes(synthetic_mt2_bytes)

    first_entry = import_mt2_file(first)
    second_entry = import_mt2_file(second)

    assert first_entry["map_id"] == second_entry["map_id"]
    assert second_entry["import_status"] == "already_indexed"
    assert len(list_track_maps()) == 1


def test_overlay_and_package_use_canonical_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, synthetic_mt2_bytes: bytes) -> None:
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    entry = import_mt2_file(source_path)

    overlays = build_track_map_overlays(
        entry["map_id"],
        platform_events=[
            {"event_id": "evt_1", "event_type": "MIN_SPLITTER", "lap_pct": 25.0, "label": "Splitter", "severity": "watch"},
        ],
    )
    assert overlays[0]["x"] is not None
    assert overlays[0]["y"] is not None

    package = build_track_map_package(entry["map_id"], "run-1")
    assert package["map"] is not None
    assert package["map"]["source_file"] is None
    assert package["match"]["map_id"] == entry["map_id"]
    assert package["sections"]
    assert package["markers"]


def test_cleanup_removes_retained_staging_and_rewrites_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    data_dir = tmp_path / "project-data"
    source_dir = tmp_path / "original-track-map-files"
    monkeypatch.setenv("RACELAB_DATA_DIR", str(data_dir))
    source_dir.mkdir()
    source_path = source_dir / "legacy.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)

    entry = import_mt2_file(source_path)
    legacy_staging_dir = data_dir / "imports" / "mt2"
    legacy_staging_dir.mkdir(parents=True, exist_ok=True)
    legacy_staging_path = legacy_staging_dir / source_path.name
    legacy_staging_path.write_bytes(synthetic_mt2_bytes)

    legacy_index = list_track_maps()
    legacy_index[0]["local_path"] = str(legacy_staging_path)
    legacy_index[0].pop("source_removed", None)
    index_path = data_dir / "track_maps" / "track_map_index.json"
    index_path.write_text(json.dumps(legacy_index, indent=2), encoding="utf-8")

    result = cleanup_track_map_storage()

    assert result["source_files_removed"] == 1
    assert result["entries_updated"] == 1
    assert result["cache_files_updated"] >= 0
    assert source_path.exists()
    assert not legacy_staging_path.exists()

    cleaned_entries = list_track_maps()
    assert cleaned_entries[0]["map_id"] == entry["map_id"]
    assert cleaned_entries[0]["display_name"] == "Talladega"
    assert cleaned_entries[0]["source_removed"] is True
    assert cleaned_entries[0]["source_hash"] == entry["sha256"]
    assert "talladega" in cleaned_entries[0]["match_aliases"]
    assert "local_path" not in cleaned_entries[0]

    track_map = get_track_map(entry["map_id"])
    assert track_map is not None
    assert track_map.map_id == entry["map_id"]
    assert track_map.source_file is None
    assert track_map.metadata.display_name == "Talladega"


def test_track_map_list_endpoint_hides_internal_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    import_mt2_file(source_path)

    client = TestClient(app)
    response = client.get("/api/track-maps")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    entry = payload[0]
    assert entry["map_id"]
    assert entry["display_name"] == "Talladega"
    assert "cache_path" not in entry
    assert "local_path" not in entry
    assert "source_filename" not in entry
    assert "source_type" not in entry
    assert "source_removed" not in entry


def test_canonical_track_map_endpoint_retains_full_point_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    entry = import_mt2_file(source_path)

    response = TestClient(app).get(f"/api/track-maps/{entry['map_id']}")

    assert response.status_code == 200
    point = response.json()["points"][0]
    assert "distance_m" in point
    assert "heading_rad" in point
    assert "curvature_1_per_m" in point
    assert "radius_m" in point
    assert "section_name" in point
    assert "section_type" in point


def test_track_map_package_endpoint_returns_sanitized_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    entry = import_mt2_file(source_path)

    class DummyRepo:
        def get_overview(self, run_id: str):
            return SimpleNamespace(
                session=SimpleNamespace(
                    track_name="Talladega Superspeedway",
                    track_display_name="Talladega Superspeedway",
                ),
            )

    monkeypatch.setattr("api.routes_track_map.repository", lambda: DummyRepo())

    client = TestClient(app)
    response = client.get("/api/runs/run-1/track-map-package")

    assert response.status_code == 200
    payload = response.json()
    assert payload["match"]["map_id"] == entry["map_id"]
    assert "cache_path" not in payload["match"]
    assert "source_filename" not in payload["match"]
    assert payload["map"]["map_id"] == entry["map_id"]
    assert payload["map"]["points"]
    assert set(payload["map"]["points"][0]) == {
        "index", "x", "y", "x_m", "y_m", "distance_ft", "lap_pct", "kind",
    }
    assert payload["map"]["markers"]
    assert payload["map"]["sections"]
    assert "source_file" not in payload["map"]
    assert "source_type" not in payload["map"]
    assert "sha256" not in payload["map"]
    assert "file_size_bytes" not in payload["map"]
    assert "format" not in payload["map"]["metadata"]
    assert "point_record" not in payload["map"]["metadata"]


def test_track_map_cache_reuses_decode_without_leaking_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    entry = import_mt2_file(source_path)
    track_map_service._get_track_map_cached.cache_clear()

    first = get_track_map(entry["map_id"])
    second = get_track_map(entry["map_id"])

    assert first is not None
    assert second is not None
    assert second is not first
    original_x = second.points[0].x
    first.points[0].x = original_x + 100.0
    first.metadata.units["caller"] = "mutation"
    third = get_track_map(entry["map_id"])

    assert third is not None
    assert third.points[0].x == original_x
    assert "caller" not in third.metadata.units


def test_track_map_serialization_does_not_share_nested_metadata(
    synthetic_mt2_bytes: bytes,
) -> None:
    track_map = parse_mt2_bytes(synthetic_mt2_bytes, source_file="talladega.mt2")
    payload = track_map.as_dict()
    payload["metadata"]["point_record"].append("caller-only-field")
    payload["metadata"]["units"]["caller"] = "mutation"

    assert "caller-only-field" not in track_map.metadata.point_record
    assert "caller" not in track_map.metadata.units


def test_track_map_index_cache_does_not_leak_caller_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    import_mt2_file(source_path)
    track_map_service._load_index_cached.cache_clear()

    first = list_track_maps()
    first[0]["match_aliases"].append("caller-only-alias")
    second = list_track_maps()

    assert "caller-only-alias" not in second[0]["match_aliases"]


def test_user_facing_track_map_copy_avoids_vendor_branding() -> None:
    import_panel = Path("ui/src/components/ImportPanel.tsx").read_text(encoding="utf-8")
    track_map_tab = Path("ui/src/tabs/TrackMapTab.tsx").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "imported file" not in track_map_tab.lower()
    forbidden = "".join(("mo", "tec", "trackv2"))
    assert forbidden not in import_panel.lower()
    assert forbidden not in readme.lower()


def test_audit_track_map_coverage_accepts_valid_canonical_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    audit_module = _load_audit_module()
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    import_mt2_file(source_path)

    report = audit_module.audit_track_map_coverage(tmp_path)

    assert report["index_entry_count"] == 1
    assert report["canonical_json_count"] == 1
    assert report["imports_dir_only_gitkeep"] is True
    assert report["broken_maps"] == []
    assert report["violations"] == []


def test_audit_track_map_coverage_catches_missing_canonical_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    audit_module = _load_audit_module()
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    entry = import_mt2_file(source_path)
    Path(entry["cache_path"]).unlink()

    report = audit_module.audit_track_map_coverage(tmp_path)

    assert entry["map_id"] in report["missing_canonical_json"]
    assert any("missing canonical JSON" in violation for violation in report["violations"])


def test_audit_track_map_coverage_catches_broken_index_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    audit_module = _load_audit_module()
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    import_mt2_file(source_path)

    index_path = tmp_path / "track_maps" / "track_map_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index[0]["display_name"] = ""
    index[0]["source_removed"] = False
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    report = audit_module.audit_track_map_coverage(tmp_path)

    assert report["broken_index_entries"]
    assert any("broken index entries" in violation for violation in report["violations"])


def test_audit_track_map_coverage_catches_retained_staging_source_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    audit_module = _load_audit_module()
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    import_mt2_file(source_path)

    staging_dir = tmp_path / "imports" / "mt2"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "leftover.mt2").write_bytes(synthetic_mt2_bytes)

    report = audit_module.audit_track_map_coverage(tmp_path)

    assert report["staging_source_files"] == ["leftover.mt2"]
    assert any("retained staging source files" in violation for violation in report["violations"])


def test_audit_track_map_coverage_reports_duplicate_source_hashes_cleanly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    audit_module = _load_audit_module()
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "talladega.mt2"
    source_path.write_bytes(synthetic_mt2_bytes)
    entry = import_mt2_file(source_path)

    index_path = tmp_path / "track_maps" / "track_map_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    duplicate = dict(index[0])
    duplicate["map_id"] = f"{entry['map_id']}-dup"
    duplicate["cache_path"] = index[0]["cache_path"]
    index.append(duplicate)
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    report = audit_module.audit_track_map_coverage(tmp_path)

    assert report["duplicate_hashes"][entry["sha256"]] == 2
    assert report["duplicate_count"] == 1


def test_audit_track_map_coverage_reports_display_name_suggestions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synthetic_mt2_bytes: bytes,
) -> None:
    audit_module = _load_audit_module()
    monkeypatch.setenv("RACELAB_DATA_DIR", str(tmp_path))
    source_path = tmp_path / "daytona 2011 roadnascar2020.mt2"
    source_path.write_bytes(build_synthetic_mt2_bytes(track_name="daytona 2011 roadnascar2020"))
    import_mt2_file(source_path)

    report = audit_module.audit_track_map_coverage(tmp_path)

    candidate = next(row for row in report["manual_naming_layout_cleanup_candidates"] if "daytona" in row["map_id"])
    assert candidate["current_display_name"] == "Daytona Road NASCAR 2020"
    assert candidate["suggested_display_name"] == "Daytona Road NASCAR 2020"
    assert candidate["reason"]
    assert candidate["classification"] in {"display-name cleanup only", "display-name cleanup only; alias cleanup"}
