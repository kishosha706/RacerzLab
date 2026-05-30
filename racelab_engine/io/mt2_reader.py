from __future__ import annotations

import bisect
import hashlib
import json
import math
import re
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

FT_PER_M = 3.280839895013123
EPSILON = 1e-9


class MT2DecodeError(ValueError):
    """Raised when a .mt2 file cannot be decoded into usable track geometry."""


@dataclass(frozen=True)
class Node:
    name: str
    attrs: dict[str, bytes]
    children: list["Node"]


class Reader:
    """Length-prefixed MoTeCTrackV2 tree reader with strict bounds checks."""

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def require(self, n: int, label: str) -> None:
        if n < 0 or self.offset + n > len(self.data):
            raise MT2DecodeError(
                f"Unexpected end of file while reading {label}: "
                f"offset={self.offset}, requested={n}, size={len(self.data)}"
            )

    def u32(self) -> int:
        self.require(4, "uint32")
        value = struct.unpack_from("<I", self.data, self.offset)[0]
        self.offset += 4
        return value

    def raw(self, n: int, label: str = "raw bytes") -> bytes:
        self.require(n, label)
        value = self.data[self.offset:self.offset + n]
        self.offset += n
        return value

    def ascii_string(self) -> str:
        n = self.u32()
        if n > self.remaining():
            raise MT2DecodeError(f"Invalid string length {n} at offset {self.offset}")
        return self.raw(n, "ASCII string").decode("ascii", errors="replace")

    def node(self, depth: int = 0) -> Node:
        if depth > 64:
            raise MT2DecodeError("Node nesting is unexpectedly deep; refusing to continue.")
        name = self.ascii_string()
        attr_count = self.u32()
        attrs: dict[str, bytes] = {}
        for _ in range(attr_count):
            key = self.ascii_string()
            n = self.u32()
            attrs[key] = self.raw(n, f"attribute {key}")
        child_count = self.u32()
        children = [self.node(depth + 1) for _ in range(child_count)]
        return Node(name=name, attrs=attrs, children=children)


def text_value(raw: bytes) -> str:
    if not raw:
        return ""
    # MoTeC names in this file are UTF-16LE-looking null-padded values. Fall back to ASCII.
    if len(raw) % 2 == 0 and raw[1::2].count(0) >= max(1, len(raw) // 4):
        return raw.decode("utf-16le", errors="replace").rstrip("\x00")
    return raw.decode("ascii", errors="replace").rstrip("\x00")


def bool_value(raw: bytes) -> bool:
    return bool(raw and raw[0])


def f32(raw: bytes) -> float:
    if len(raw) != 4:
        raise MT2DecodeError(f"Expected float32 value, got {len(raw)} bytes")
    return struct.unpack("<f", raw)[0]


def f64(raw: bytes) -> float:
    if len(raw) != 8:
        raise MT2DecodeError(f"Expected float64 value, got {len(raw)} bytes")
    return struct.unpack("<d", raw)[0]


def u32_value(raw: bytes) -> int:
    if len(raw) != 4:
        raise MT2DecodeError(f"Expected uint32 value, got {len(raw)} bytes")
    return struct.unpack("<I", raw)[0]


def find_child(node: Node | None, name: str) -> Node | None:
    if node is None:
        return None
    return next((child for child in node.children if child.name == name), None)


def children_by_name(node: Node | None, name: str) -> list[Node]:
    return [child for child in (node.children if node else []) if child.name == name]


def required_attr(node: Node, key: str) -> bytes:
    if key not in node.attrs:
        raise MT2DecodeError(f"Node {node.name!r} is missing required attribute {key!r}")
    return node.attrs[key]


def finite(value: float) -> bool:
    return not (math.isnan(value) or math.isinf(value))


def unwrap_angles(values: list[float]) -> list[float]:
    if not values:
        return []
    out = [values[0]]
    for raw in values[1:]:
        value = raw
        prev = out[-1]
        while value - prev > math.pi:
            value -= math.tau
        while value - prev < -math.pi:
            value += math.tau
        out.append(value)
    return out


def circular_lerp_angle(a: float, b: float, t: float) -> float:
    delta = (b - a + math.pi) % math.tau - math.pi
    return a + delta * t


def normalized_angle(angle: float) -> float:
    value = angle % math.tau
    return value + math.tau if value < 0 else value


@dataclass
class TrackMapPoint:
    index: int
    x: float
    y: float
    z: float | None = None
    x_m: float | None = None
    y_m: float | None = None
    z_m: float | None = None
    distance_m: float | None = None
    distance_ft: float | None = None
    lap_pct: float | None = None
    heading_rad: float | None = None
    curvature_1_per_m: float | None = None
    curvature_raw_1_per_m: float | None = None
    curvature_smoothed_1_per_m: float | None = None
    radius_m: float | None = None
    radius_smoothed_m: float | None = None
    section_name: str | None = None
    section_type: str | None = None
    kind: Literal["centerline", "left_boundary", "right_boundary", "unknown"] = "centerline"


@dataclass
class TrackMapMarker:
    marker_id: str
    name: str
    distance_m: float
    distance_ft: float
    lap_pct: float
    x: float
    y: float
    z: float | None = None
    heading_rad: float | None = None
    source: Literal["mt2", "telemetry", "fallback"] = "mt2"


@dataclass
class TrackMapSection:
    section_id: str
    name: str
    section_type: Literal["straight", "corner", "unknown"]
    start_marker: str
    end_marker: str
    start_distance_m: float
    end_distance_m: float
    start_distance_ft: float
    end_distance_ft: float
    start_lap_pct: float
    end_lap_pct: float
    length_m: float
    length_ft: float
    wraps_start_finish: bool = False


@dataclass
class TrackMapBounds:
    min_x_m: float
    max_x_m: float
    min_y_m: float
    max_y_m: float
    width_m: float
    height_m: float
    min_x_ft: float
    max_x_ft: float
    min_y_ft: float
    max_y_ft: float
    width_ft: float
    height_ft: float


@dataclass
class TrackMapOrigin:
    lat: float | None = None
    lng: float | None = None
    alt: float | None = None
    gps_supported: bool = False


@dataclass
class TrackMapMetadata:
    format: str
    version: int | None
    track_name: str
    model_name: str | None
    closed: bool
    clockwise_flag: bool
    x_over: bool
    z_rotation_rad: float
    distance_m: float
    distance_ft: float
    distance_miles: float
    point_record: list[str]
    units: dict[str, str]
    origin: TrackMapOrigin
    has_boundaries: bool
    has_sections: bool
    has_markers: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class TrackMap:
    map_id: str
    source_file: str | None
    file_size_bytes: int
    sha256: str
    metadata: TrackMapMetadata
    bounds: TrackMapBounds
    points: list[TrackMapPoint]
    markers: list[TrackMapMarker]
    sections: list[TrackMapSection]
    status: Literal["parsed", "partial", "unsupported"] = "parsed"
    supported: bool = True
    partial: bool = False
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "track-map"


def _bounds(points: list[TrackMapPoint]) -> TrackMapBounds:
    xs = [float(p.x_m if p.x_m is not None else p.x) for p in points]
    ys = [float(p.y_m if p.y_m is not None else p.y) for p in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    return TrackMapBounds(
        min_x_m=min_x,
        max_x_m=max_x,
        min_y_m=min_y,
        max_y_m=max_y,
        width_m=max_x - min_x,
        height_m=max_y - min_y,
        min_x_ft=min_x * FT_PER_M,
        max_x_ft=max_x * FT_PER_M,
        min_y_ft=min_y * FT_PER_M,
        max_y_ft=max_y * FT_PER_M,
        width_ft=(max_x - min_x) * FT_PER_M,
        height_ft=(max_y - min_y) * FT_PER_M,
    )


def smooth_curvature_5point(
    curvatures: list[float | None],
    weights: tuple[float, float, float, float, float] = (1.0, 2.0, 4.0, 2.0, 1.0),
) -> list[float | None]:
    """Apply weighted 5-point smoothing to a curvature array.

    Preserves raw values at edges (first 2, last 2 points).
    Uses [1,2,4,2,1] weights by default — a binomial-like kernel
    that preserves overall shape while reducing jitter.

    Args:
        curvatures: Raw curvature values (1/m). None values are skipped.
        weights: 5-tuple of weights for the smoothing kernel.

    Returns:
        Smoothed curvature array (same length). None values propagate.
    """
    n = len(curvatures)
    if n < 5:
        return list(curvatures)  # Not enough points to smooth
    w_sum = sum(weights)
    result: list[float | None] = [None] * n
    for i in range(n):
        if curvatures[i] is None:
            continue
        # Edge points: preserve raw value
        if i < 2 or i >= n - 2:
            result[i] = curvatures[i]
            continue
        # Interior: weighted average
        vals: list[float] = []
        w_used: list[float] = []
        for j, w in enumerate(weights):
            offset = i - 2 + j
            v = curvatures[offset]
            if v is not None:
                vals.append(v)
                w_used.append(w)
        if vals:
            result[i] = sum(v * w for v, w in zip(vals, w_used)) / sum(w_used)
    return result


def _derive_curvature(points: list[TrackMapPoint]) -> None:
    headings = [p.heading_rad for p in points]
    if len(points) < 3 or any(h is None for h in headings):
        return
    unwrapped = unwrap_angles([float(h) for h in headings if h is not None])
    raw_curvatures: list[float | None] = [None] * len(points)
    for i, point in enumerate(points):
        if point.distance_m is None:
            continue
        if i == 0:
            j0, j1 = 0, 1
        elif i == len(points) - 1:
            j0, j1 = len(points) - 2, len(points) - 1
        else:
            j0, j1 = i - 1, i + 1
        d0 = points[j0].distance_m
        d1 = points[j1].distance_m
        if d0 is None or d1 is None or abs(d1 - d0) < EPSILON:
            continue
        curvature = (unwrapped[j1] - unwrapped[j0]) / (d1 - d0)
        if finite(curvature):
            raw_curvatures[i] = curvature
            point.curvature_1_per_m = curvature
            point.curvature_raw_1_per_m = curvature
            point.radius_m = 1.0 / abs(curvature) if abs(curvature) > EPSILON else None

    # Apply 5-point smoothing for a cleaner curvature signal
    # Raw curvature_1_per_m is preserved; smoothed goes into separate field
    smoothed = smooth_curvature_5point(raw_curvatures)
    for i, point in enumerate(points):
        sv = smoothed[i]
        if sv is not None:
            point.curvature_smoothed_1_per_m = sv
            point.radius_smoothed_m = 1.0 / abs(sv) if abs(sv) > EPSILON else None


def parse_points(points_node: Node, total_dist_m: float) -> list[TrackMapPoint]:
    count = u32_value(required_attr(points_node, "Count"))
    raw = required_attr(points_node, "Data")
    expected = count * 20
    if count <= 1:
        raise MT2DecodeError(f"Points.Count must be greater than 1, got {count}")
    if len(raw) != expected:
        raise MT2DecodeError(f"Unexpected Points.Data length: got {len(raw)} bytes, expected {expected}")

    points: list[TrackMapPoint] = []
    last_distance = -math.inf
    for i in range(count):
        x_m, y_m, z_m, distance_m, heading_rad = struct.unpack_from("<5f", raw, i * 20)
        values = [x_m, y_m, z_m, distance_m, heading_rad]
        if not all(finite(v) for v in values):
            raise MT2DecodeError(f"Non-finite point value at point index {i}")
        if distance_m + 1e-6 < last_distance:
            raise MT2DecodeError(f"Point distance is not monotonic at point index {i}")
        last_distance = distance_m
        lap_pct = distance_m / total_dist_m * 100.0 if total_dist_m > 0 else None
        points.append(
            TrackMapPoint(
                index=i,
                x=x_m,
                y=y_m,
                z=z_m,
                x_m=x_m,
                y_m=y_m,
                z_m=z_m,
                distance_m=distance_m,
                distance_ft=distance_m * FT_PER_M,
                lap_pct=lap_pct,
                heading_rad=heading_rad,
                kind="centerline",
            )
        )
    _derive_curvature(points)
    return points


def _interpolate_point(p1: TrackMapPoint, p2: TrackMapPoint, t: float) -> dict[str, float]:
    """Interpolate between two track map points at parameter t (0-1)."""
    heading = circular_lerp_angle(float(p1.heading_rad or 0.0), float(p2.heading_rad or 0.0), t)
    return {
        "x_m": float(p1.x_m or p1.x) + (float(p2.x_m or p2.x) - float(p1.x_m or p1.x)) * t,
        "y_m": float(p1.y_m or p1.y) + (float(p2.y_m or p2.y) - float(p1.y_m or p1.y)) * t,
        "z_m": float(p1.z_m or p1.z or 0.0) + (float(p2.z_m or p2.z or 0.0) - float(p1.z_m or p1.z or 0.0)) * t,
        "heading_rad": normalized_angle(heading),
    }


def interpolate_at_distance(points: list[TrackMapPoint], distance_m: float, total_dist_m: float) -> dict[str, float]:
    if not points:
        raise MT2DecodeError("Cannot interpolate an empty point list")
    d = distance_m if total_dist_m <= 0 else distance_m % total_dist_m

    distances = [float(p.distance_m or 0.0) for p in points]
    if d <= distances[0]:
        p = points[0]
        return {
            "x_m": float(p.x_m or p.x),
            "y_m": float(p.y_m or p.y),
            "z_m": float(p.z_m or p.z or 0.0),
            "heading_rad": float(p.heading_rad or 0.0),
        }

    if d > distances[-1] and total_dist_m > distances[-1]:
        p1 = points[-1]
        p2 = points[0]
        span = max(EPSILON, total_dist_m - distances[-1])
        t = (d - distances[-1]) / span
        return _interpolate_point(p1, p2, t)

    i2 = bisect.bisect_left(distances, d)
    i2 = min(max(1, i2), len(points) - 1)
    p1 = points[i2 - 1]
    p2 = points[i2]
    d1 = float(p1.distance_m or 0.0)
    d2 = float(p2.distance_m or d1)
    span = max(EPSILON, d2 - d1)
    t = (d - d1) / span
    return _interpolate_point(p1, p2, t)


def interpolate_at_pct(points: list[TrackMapPoint], lap_pct: float, total_dist_m: float) -> dict[str, float]:
    return interpolate_at_distance(points, lap_pct / 100.0 * total_dist_m, total_dist_m)


def pct_inside_section(pct: float, start: float, end: float) -> bool:
    return start <= pct <= end if start <= end else pct >= start or pct <= end


def section_at_pct(sections: list[TrackMapSection], pct: float) -> TrackMapSection | None:
    return next((s for s in sections if pct_inside_section(pct, s.start_lap_pct, s.end_lap_pct)), None)


def _section_type(value: str) -> Literal["straight", "corner", "unknown"]:
    normalized = value.strip().lower()
    if normalized.startswith("straight"):
        return "straight"
    if normalized.startswith("corner") or normalized.startswith("turn"):
        return "corner"
    return "unknown"


def _section_type_from_node(section: Node) -> str:
    nested_types = find_child(section, "SectionTypes")
    if nested_types and nested_types.children:
        # Typical file: SectionTypes -> Straights/Corners child, sometimes with Name attr.
        first = nested_types.children[0]
        return text_value(first.attrs.get("Name", b"")) or first.name
    raw = section.attrs.get("Type") or section.attrs.get("SectionType")
    return text_value(raw) if raw else "unknown"


def parse_markers_and_sections(root: Node, points: list[TrackMapPoint], total_dist_m: float) -> tuple[list[TrackMapMarker], list[TrackMapSection]]:
    section_groups = find_child(root, "SectionGroups")
    if not section_groups or not section_groups.children:
        return [], []

    group = section_groups.children[0]
    markers_node = find_child(group, "Markers")
    markers: list[TrackMapMarker] = []
    if markers_node:
        for i, marker in enumerate(markers_node.children):
            if "Dist" not in marker.attrs:
                continue
            dist_m = f64(marker.attrs["Dist"])
            name = text_value(marker.attrs.get("Name", b"")) or f"Marker ({i})"
            pos = interpolate_at_distance(points, dist_m, total_dist_m)
            markers.append(
                TrackMapMarker(
                    marker_id=f"mt2_marker_{i}",
                    name=name,
                    distance_m=dist_m,
                    distance_ft=dist_m * FT_PER_M,
                    lap_pct=dist_m / total_dist_m * 100.0 if total_dist_m > 0 else 0.0,
                    x=pos["x_m"],
                    y=pos["y_m"],
                    z=pos["z_m"],
                    heading_rad=pos["heading_rad"],
                )
            )

    marker_by_name = {marker.name: marker for marker in markers}
    sections_node = find_child(group, "Sections")
    sections: list[TrackMapSection] = []
    if not sections_node:
        return markers, sections

    for i, sec_node in enumerate(sections_node.children):
        m1_name = text_value(sec_node.attrs.get("Marker1", b""))
        m2_name = text_value(sec_node.attrs.get("Marker2", b""))
        start = marker_by_name.get(m1_name)
        end = marker_by_name.get(m2_name)
        if start is None or end is None:
            continue
        length_m = end.distance_m - start.distance_m
        wraps = False
        if length_m < 0:
            length_m += total_dist_m
            wraps = True
        raw_name = text_value(sec_node.attrs.get("Name", b"")) or f"Section {i}"
        type_name = _section_type_from_node(sec_node)
        section_type = _section_type(type_name)
        sections.append(
            TrackMapSection(
                section_id=f"mt2_section_{i}",
                name=raw_name,
                section_type=section_type,
                start_marker=start.name,
                end_marker=end.name,
                start_distance_m=start.distance_m,
                end_distance_m=end.distance_m,
                start_distance_ft=start.distance_ft,
                end_distance_ft=end.distance_ft,
                start_lap_pct=start.lap_pct,
                end_lap_pct=end.lap_pct,
                length_m=length_m,
                length_ft=length_m * FT_PER_M,
                wraps_start_finish=wraps,
            )
        )

    for point in points:
        if point.lap_pct is None:
            continue
        if matched := section_at_pct(sections, point.lap_pct):
            point.section_name = matched.name
            point.section_type = matched.section_type

    return markers, sections


def parse_mt2_bytes(data: bytes, source_file: str | None = None) -> TrackMap:
    sha = hashlib.sha256(data).hexdigest()
    reader = Reader(data)
    root = reader.node()
    if root.name != "MoTeCTrackV2":
        raise MT2DecodeError(f"Unsupported .mt2 format signature: {root.name!r}")
    if "Dist" not in root.attrs:
        raise MT2DecodeError("MoTeCTrackV2 root is missing Dist.")

    total_dist_m = f32(root.attrs["Dist"])
    if total_dist_m <= 0 or not finite(total_dist_m):
        raise MT2DecodeError(f"Invalid root Dist value: {total_dist_m!r}")

    models_node = find_child(root, "Models")
    if not models_node or not models_node.children:
        raise MT2DecodeError("MoTeCTrackV2 file has no Models/Model node.")
    model = models_node.children[0]
    points_node = find_child(model, "Points")
    if points_node is None:
        raise MT2DecodeError("MoTeCTrackV2 Model has no Points node.")

    origin_node = find_child(model, "Origin")
    origin = TrackMapOrigin(
        alt=f64(origin_node.attrs["Alt"]) if origin_node and "Alt" in origin_node.attrs else None,
        lat=f64(origin_node.attrs["Lat"]) if origin_node and "Lat" in origin_node.attrs else None,
        lng=f64(origin_node.attrs["Lng"]) if origin_node and "Lng" in origin_node.attrs else None,
    )
    origin.gps_supported = origin.lat not in (None, 0.0) or origin.lng not in (None, 0.0)

    points = parse_points(points_node, total_dist_m)
    markers, sections = parse_markers_and_sections(root, points, total_dist_m)
    bounds = _bounds(points)

    warnings: list[str] = []
    if not origin.gps_supported:
        warnings.append("No real GPS origin found; use lap percentage / distance alignment, not map tiles.")
    if all((p.z_m or 0.0) == 0.0 for p in points):
        warnings.append("No altitude variation found in this .mt2 file.")
    warnings.extend([
        "No left boundary found.",
        "No right boundary found.",
        "No track width found.",
        "No banking data found.",
    ])

    track_name = text_value(root.attrs.get("Name", b"")) or Path(source_file or "track-map").stem
    metadata = TrackMapMetadata(
        format=root.name,
        version=u32_value(root.attrs["Version"]) if "Version" in root.attrs else None,
        track_name=track_name,
        model_name=text_value(model.attrs.get("Name", b"")) if model else None,
        closed=bool_value(root.attrs.get("Closed", b"")),
        clockwise_flag=bool_value(root.attrs.get("Clockwise", b"")),
        x_over=bool_value(root.attrs.get("XOver", b"")),
        z_rotation_rad=f32(root.attrs["ZRotation"]) if "ZRotation" in root.attrs else 0.0,
        distance_m=total_dist_m,
        distance_ft=total_dist_m * FT_PER_M,
        distance_miles=total_dist_m * FT_PER_M / 5280.0,
        point_record=["x_m", "y_m", "z_m", "distance_m", "heading_rad"],
        units={"coordinates": "meters", "distance": "meters", "heading": "radians"},
        origin=origin,
        has_boundaries=False,
        has_sections=bool(sections),
        has_markers=bool(markers),
        warnings=warnings,
    )

    map_id = f"{_slug(track_name)}-{sha[:12]}"
    return TrackMap(
        map_id=map_id,
        source_file=source_file,
        file_size_bytes=len(data),
        sha256=sha,
        metadata=metadata,
        bounds=bounds,
        points=points,
        markers=markers,
        sections=sections,
        status="parsed",
        supported=True,
        partial=False,
        warnings=warnings,
    )


def parse_mt2(path: str | Path) -> TrackMap:
    p = Path(path)
    return parse_mt2_bytes(p.read_bytes(), source_file=str(p))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Decode a MoTeCTrackV2 .mt2 track map.")
    parser.add_argument("path")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    track_map = parse_mt2(args.path)
    data = track_map.as_dict()
    text = json.dumps(data, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
