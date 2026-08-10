import { MapPin, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import { fetchRunTrackMapPackage } from "../api/client";
import { useTelemetryCursor, useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { PlatformEventItem, PlatformEventVisibilityMode } from "../types/telemetry";
import type {
  TrackMapBounds,
  TrackMapOverlayMarker,
  TrackMapPackage,
  TrackMapPoint,
  TrackMapSection,
  TrackMapTurn,
} from "../types/trackMap";
import { filterPlatformEvents, isClearPlatformDiagnostic } from "../utils/platformEventVisibility";
import { layoutTrackMapTurnLabel } from "../utils/trackMapTurnLayout";

type TrackMapOverlayProps = {
  open: boolean;
  runId: string | null;
  lap?: number | null;
  trackName?: string | null;
  targetZoneStartPct?: number | null;
  targetZoneEndPct?: number | null;
  zoomRangeFt?: { startValue?: number; endValue?: number } | null;
  platformEvents?: PlatformEventItem[];
  eventVisibilityMode?: PlatformEventVisibilityMode;
  onClose: () => void;
};

type DrawablePoint = {
  source: TrackMapPoint;
  x: number;
  y: number;
  lapPct: number | null;
  distanceFt: number | null;
};

type LapPositionedPoint = DrawablePoint & { lapPct: number };

type NumericBounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  width: number;
  height: number;
};

type OverlayLayout = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type OverlayInteraction = {
  kind: "drag" | "resize";
  startX: number;
  startY: number;
  initial: OverlayLayout;
};

const MAP_PADDING_RATIO = 0.08;
const MAP_MIN_PADDING = 18;
const OVERLAY_MIN_WIDTH = 300;
const OVERLAY_MIN_HEIGHT = 240;
const OVERLAY_EDGE_MARGIN = 10;
const OVERLAY_LAYOUT_STORAGE_KEY = "racelab_track_map_overlay_layout";
const OVERLAY_OPACITY_STORAGE_KEY = "racelab_track_map_overlay_opacity";

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function formatDistanceNumber(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function getTrackPointCoordinate(point: Pick<TrackMapPoint, "x" | "y" | "x_m" | "y_m">): { x: number; y: number } | null {
  const x = isFiniteNumber(point.x_m) ? point.x_m : isFiniteNumber(point.x) ? point.x : null;
  const y = isFiniteNumber(point.y_m) ? point.y_m : isFiniteNumber(point.y) ? point.y : null;
  if (x == null || y == null) return null;
  return { x, y };
}

function getBoundsFromPoints(points: Array<{ x: number; y: number }>): NumericBounds | null {
  if (points.length < 2) return null;
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const width = maxX - minX;
  const height = maxY - minY;
  if (!(width > 0) || !(height > 0)) return null;
  return { minX, maxX, minY, maxY, width, height };
}

function getBoundsFromPayload(bounds: TrackMapBounds | null | undefined): NumericBounds | null {
  if (!bounds) return null;
  if (
    !isFiniteNumber(bounds.min_x_m)
    || !isFiniteNumber(bounds.max_x_m)
    || !isFiniteNumber(bounds.min_y_m)
    || !isFiniteNumber(bounds.max_y_m)
  ) {
    return null;
  }
  const width = bounds.max_x_m - bounds.min_x_m;
  const height = bounds.max_y_m - bounds.min_y_m;
  if (!(width > 0) || !(height > 0)) return null;
  return {
    minX: bounds.min_x_m,
    maxX: bounds.max_x_m,
    minY: bounds.min_y_m,
    maxY: bounds.max_y_m,
    width,
    height,
  };
}

function mergeBounds(primary: NumericBounds | null, secondary: NumericBounds | null): NumericBounds | null {
  if (primary == null) return secondary;
  if (secondary == null) return primary;
  const minX = Math.min(primary.minX, secondary.minX);
  const maxX = Math.max(primary.maxX, secondary.maxX);
  const minY = Math.min(primary.minY, secondary.minY);
  const maxY = Math.max(primary.maxY, secondary.maxY);
  const width = maxX - minX;
  const height = maxY - minY;
  if (!(width > 0) || !(height > 0)) return null;
  return { minX, maxX, minY, maxY, width, height };
}

function buildSvgPath(points: Array<{ x: number; y: number }>): string {
  if (points.length < 2) return "";
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`).join(" ");
}

function circularLapDifference(a: number, b: number): number {
  const diff = Math.abs(a - b);
  return Math.min(diff, 100 - diff);
}

function nearestPointByLapPct(points: LapPositionedPoint[], lapPct: number | null | undefined): DrawablePoint | null {
  if (!isFiniteNumber(lapPct) || points.length === 0) return null;
  const target = ((lapPct % 100) + 100) % 100;
  let low = 0;
  let high = points.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (points[middle].lapPct < target) low = middle + 1;
    else high = middle;
  }

  // Include both insertion neighbors and both ends because lap percentage is
  // circular at start/finish. This changes a cursor lookup from O(points) to
  // O(log points) without changing physical-position selection.
  const candidates = [...new Set([low - 1, low, 0, points.length - 1])]
    .filter((index) => index >= 0 && index < points.length)
    .sort((left, right) => left - right);
  let best: LapPositionedPoint | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const index of candidates) {
    const point = points[index];
    const distance = circularLapDifference(point.lapPct, target);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = point;
    }
  }
  return best;
}

function nearestPointByDistance(points: DrawablePoint[], distanceFt: number | null | undefined): DrawablePoint | null {
  if (!isFiniteNumber(distanceFt) || points.length === 0) return null;
  let best: DrawablePoint | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const point of points) {
    if (!isFiniteNumber(point.distanceFt)) continue;
    const distance = Math.abs(point.distanceFt - distanceFt);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = point;
    }
  }
  return best;
}

function markerPosition(marker: TrackMapOverlayMarker, points: LapPositionedPoint[]): DrawablePoint | null {
  if (isFiniteNumber(marker.x) && isFiniteNumber(marker.y)) {
    return {
      source: points[0]?.source ?? ({
        index: -1,
        x: marker.x,
        y: marker.y,
        z: null,
        x_m: marker.x,
        y_m: marker.y,
        z_m: null,
        distance_m: null,
        distance_ft: marker.distance_ft ?? null,
        lap_pct: marker.lap_pct ?? null,
        heading_rad: marker.heading_rad ?? null,
        curvature_1_per_m: null,
        radius_m: null,
        section_name: null,
        section_type: null,
        kind: "unknown",
      } satisfies TrackMapPoint),
      x: marker.x,
      y: marker.y,
      lapPct: marker.lap_pct ?? null,
      distanceFt: marker.distance_ft ?? null,
    };
  }
  return nearestPointByLapPct(points, marker.lap_pct);
}

function sectionMidpoint(section: TrackMapSection): number {
  const span = (section.end_lap_pct - section.start_lap_pct + 100) % 100;
  return (section.start_lap_pct + span / 2) % 100;
}

function rangePoints(points: DrawablePoint[], zoomRangeFt: TrackMapOverlayProps["zoomRangeFt"]): DrawablePoint[] {
  if (!zoomRangeFt || !isFiniteNumber(zoomRangeFt.startValue) || !isFiniteNumber(zoomRangeFt.endValue)) return [];
  const start = Math.min(zoomRangeFt.startValue, zoomRangeFt.endValue);
  const end = Math.max(zoomRangeFt.startValue, zoomRangeFt.endValue);
  return points.filter((point) => isFiniteNumber(point.distanceFt) && point.distanceFt >= start && point.distanceFt <= end);
}

function formatDistanceRange(zoomRangeFt: TrackMapOverlayProps["zoomRangeFt"]): string {
  if (!zoomRangeFt || !isFiniteNumber(zoomRangeFt.startValue) || !isFiniteNumber(zoomRangeFt.endValue)) return "Full chart range";
  const start = Math.min(zoomRangeFt.startValue, zoomRangeFt.endValue);
  const end = Math.max(zoomRangeFt.startValue, zoomRangeFt.endValue);
  return `${formatDistanceNumber(start)}-${formatDistanceNumber(end)} ft`;
}

function viewportSize(): { width: number; height: number } {
  if (typeof window === "undefined") return { width: 1280, height: 800 };
  return { width: window.innerWidth, height: window.innerHeight };
}

function clampOverlayLayout(layout: OverlayLayout): OverlayLayout {
  const viewport = viewportSize();
  const maxWidth = Math.max(OVERLAY_MIN_WIDTH, viewport.width - OVERLAY_EDGE_MARGIN * 2);
  const maxHeight = Math.max(OVERLAY_MIN_HEIGHT, viewport.height - OVERLAY_EDGE_MARGIN * 2);
  const width = Math.min(Math.max(layout.width, OVERLAY_MIN_WIDTH), maxWidth);
  const height = Math.min(Math.max(layout.height, OVERLAY_MIN_HEIGHT), maxHeight);
  const left = Math.min(Math.max(layout.left, OVERLAY_EDGE_MARGIN), Math.max(OVERLAY_EDGE_MARGIN, viewport.width - width - OVERLAY_EDGE_MARGIN));
  const top = Math.min(Math.max(layout.top, OVERLAY_EDGE_MARGIN), Math.max(OVERLAY_EDGE_MARGIN, viewport.height - height - OVERLAY_EDGE_MARGIN));
  return { left, top, width, height };
}

function defaultOverlayLayout(): OverlayLayout {
  const viewport = viewportSize();
  const width = Math.min(380, Math.max(OVERLAY_MIN_WIDTH, viewport.width - OVERLAY_EDGE_MARGIN * 2));
  const height = Math.min(340, Math.max(OVERLAY_MIN_HEIGHT, viewport.height - OVERLAY_EDGE_MARGIN * 2));
  return clampOverlayLayout({
    left: viewport.width - width - 18,
    top: Math.max(64, viewport.height - height - 68),
    width,
    height,
  });
}

function loadOverlayLayout(): OverlayLayout {
  if (typeof window === "undefined") return defaultOverlayLayout();
  try {
    const raw = window.localStorage.getItem(OVERLAY_LAYOUT_STORAGE_KEY);
    if (!raw) return defaultOverlayLayout();
    const parsed = JSON.parse(raw) as Partial<OverlayLayout>;
    if (
      !isFiniteNumber(parsed.left)
      || !isFiniteNumber(parsed.top)
      || !isFiniteNumber(parsed.width)
      || !isFiniteNumber(parsed.height)
    ) {
      return defaultOverlayLayout();
    }
    return clampOverlayLayout(parsed as OverlayLayout);
  } catch {
    return defaultOverlayLayout();
  }
}

function loadOverlayOpacity(): number {
  if (typeof window === "undefined") return 0.78;
  const raw = window.localStorage.getItem(OVERLAY_OPACITY_STORAGE_KEY);
  const value = raw == null ? 0.78 : Number(raw);
  return isFiniteNumber(value) ? Math.min(0.9, Math.max(0.6, value)) : 0.78;
}

export function TrackMapOverlay({
  open,
  runId,
  lap,
  trackName,
  targetZoneStartPct,
  targetZoneEndPct,
  zoomRangeFt,
  platformEvents = [],
  eventVisibilityMode = "actionable",
  onClose,
}: TrackMapOverlayProps) {
  const { selection } = useTelemetrySelection();
  const telemetryCursor = useTelemetryCursor();
  const [pkg, setPkg] = useState<TrackMapPackage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLabels, setShowLabels] = useState(false);
  const [showEvents, setShowEvents] = useState(false);
  const [opacity, setOpacity] = useState(loadOverlayOpacity);
  const [layout, setLayout] = useState(loadOverlayLayout);
  const [interactionKind, setInteractionKind] = useState<OverlayInteraction["kind"] | null>(null);
  const requestSeqRef = useRef(0);
  const interactionRef = useRef<OverlayInteraction | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(OVERLAY_LAYOUT_STORAGE_KEY, JSON.stringify(layout));
  }, [layout]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(OVERLAY_OPACITY_STORAGE_KEY, String(opacity));
  }, [opacity]);

  useEffect(() => {
    if (!open) return;
    const handleResize = () => setLayout((current) => clampOverlayLayout(current));
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [open]);

  useEffect(() => {
    if (interactionKind == null) return;

    const handlePointerMove = (event: PointerEvent) => {
      const interaction = interactionRef.current;
      if (!interaction) return;
      const dx = event.clientX - interaction.startX;
      const dy = event.clientY - interaction.startY;
      setLayout((current) => {
        const base = interaction.initial;
        if (interaction.kind === "drag") {
          return clampOverlayLayout({ ...base, left: base.left + dx, top: base.top + dy });
        }
        return clampOverlayLayout({ ...base, width: base.width + dx, height: base.height + dy });
      });
    };

    const handlePointerUp = () => {
      interactionRef.current = null;
      setInteractionKind(null);
      document.body.dataset.trackMapOverlayDragging = "false";
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
    window.addEventListener("pointercancel", handlePointerUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
      window.removeEventListener("pointercancel", handlePointerUp);
    };
  }, [interactionKind]);

  const beginOverlayInteraction = useCallback((kind: OverlayInteraction["kind"], event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement | null;
    if (kind === "drag" && target?.closest("button, input, select, textarea, label, a")) return;
    event.preventDefault();
    interactionRef.current = {
      kind,
      startX: event.clientX,
      startY: event.clientY,
      initial: layout,
    };
    setInteractionKind(kind);
    document.body.dataset.trackMapOverlayDragging = kind === "drag" ? "true" : "false";
  }, [layout]);

  useEffect(() => {
    if (!open || !runId) {
      setLoading(false);
      if (!open) setError(null);
      return;
    }
    let cancelled = false;
    const seq = ++requestSeqRef.current;
    setLoading(true);
    setError(null);
    fetchRunTrackMapPackage(runId, {
      lap: lap ?? undefined,
      target_zone_start_pct: targetZoneStartPct ?? undefined,
      target_zone_end_pct: targetZoneEndPct ?? undefined,
    })
      .then((nextPkg) => {
        if (!cancelled && seq === requestSeqRef.current) setPkg(nextPkg);
      })
      .catch((caught) => {
        if (!cancelled && seq === requestSeqRef.current) {
          setPkg(null);
          setError(caught instanceof Error ? caught.message : "Track map unavailable for this run.");
        }
      })
      .finally(() => {
        if (!cancelled && seq === requestSeqRef.current) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [lap, open, runId, targetZoneEndPct, targetZoneStartPct]);

  const points = pkg?.map?.points ?? [];
  const drawablePoints = useMemo<DrawablePoint[]>(
    () =>
      points
        .filter((point) => point.kind === "centerline" || point.kind === "unknown")
        .map((point) => {
          const coordinate = getTrackPointCoordinate(point);
          if (!coordinate) return null;
          return {
            source: point,
            x: coordinate.x,
            y: coordinate.y,
            lapPct: point.lap_pct,
            distanceFt: point.distance_ft,
          };
        })
        .filter((point): point is DrawablePoint => point != null),
    [points],
  );

  const mergedBounds = useMemo(
    () => mergeBounds(getBoundsFromPayload(pkg?.map?.bounds), getBoundsFromPoints(drawablePoints)),
    [drawablePoints, pkg?.map?.bounds],
  );
  const lapPositionedPoints = useMemo<LapPositionedPoint[]>(
    () => drawablePoints
      .filter((point): point is LapPositionedPoint => isFiniteNumber(point.lapPct))
      .sort((left, right) => left.lapPct - right.lapPct),
    [drawablePoints],
  );

  const svgViewport = useMemo(() => {
    if (!mergedBounds) return null;
    const maxDimension = Math.max(mergedBounds.width, mergedBounds.height);
    const padding = Math.max(maxDimension * MAP_PADDING_RATIO, MAP_MIN_PADDING);
    const width = mergedBounds.width + padding * 2;
    const height = mergedBounds.height + padding * 2;
    if (!(width > 0) || !(height > 0)) return null;
    return {
      viewBox: `${mergedBounds.minX - padding} ${mergedBounds.minY - padding} ${width} ${height}`,
    };
  }, [mergedBounds]);

  const pointPath = useMemo(() => buildSvgPath(drawablePoints), [drawablePoints]);
  const highlightedPoints = useMemo(() => rangePoints(drawablePoints, zoomRangeFt), [drawablePoints, zoomRangeFt]);
  const highlightedPath = useMemo(() => buildSvgPath(highlightedPoints), [highlightedPoints]);
  const cursorLapPct = telemetryCursor.hoverLapPct ?? selection.selectedLapPct ?? null;
  const cursorPoint = nearestPointByLapPct(lapPositionedPoints, cursorLapPct);
  const selectedEventMarker = useMemo(() => {
    const overlays = pkg?.overlays ?? [];
    if (!selection.selectedEventId) return null;
    return overlays.find((overlay) =>
      overlay.source_id === selection.selectedEventId
      || overlay.marker_id === selection.selectedEventId
      || overlay.event_type === selection.selectedEventId) ?? null;
  }, [pkg?.overlays, selection.selectedEventId]);
  const selectedEventPoint = selectedEventMarker
    ? markerPosition(selectedEventMarker, lapPositionedPoints)
    : nearestPointByLapPct(lapPositionedPoints, selection.selectedLapPct);
  const rangeStartPoint = nearestPointByDistance(drawablePoints, zoomRangeFt?.startValue);
  const rangeEndPoint = nearestPointByDistance(drawablePoints, zoomRangeFt?.endValue);
  const visiblePlatformEventIds = useMemo(
    () => new Set(
      filterPlatformEvents(platformEvents, eventVisibilityMode)
        .filter((event) => !isClearPlatformDiagnostic(event))
        .map((event) => event.event_id),
    ),
    [eventVisibilityMode, platformEvents],
  );
  const visibleEventMarkers = useMemo(
    () => (pkg?.overlays ?? [])
      .filter((overlay) => overlay.kind === "platform_event")
      .filter((overlay) => platformEvents.length === 0 || (overlay.source_id != null && visiblePlatformEventIds.has(overlay.source_id)))
      .slice(0, 24)
      .map((overlay) => ({ overlay, point: markerPosition(overlay, lapPositionedPoints) }))
      .filter((item): item is { overlay: TrackMapOverlayMarker; point: DrawablePoint } => item.point != null),
    [lapPositionedPoints, pkg?.overlays, platformEvents.length, visiblePlatformEventIds],
  );
  const sectionLabels = useMemo(
    () => (pkg?.sections ?? [])
      .filter((section) => !(pkg?.turns?.length && section.section_type === "corner"))
      .slice(0, 16)
      .map((section) => ({ section, point: nearestPointByLapPct(lapPositionedPoints, sectionMidpoint(section)) }))
      .filter((item): item is { section: TrackMapSection; point: DrawablePoint } => item.point != null),
    [lapPositionedPoints, pkg?.sections, pkg?.turns?.length],
  );
  const turnLabels = useMemo(
    () => (pkg?.turns ?? [])
      .map((turn) => {
        const point = nearestPointByLapPct(lapPositionedPoints, turn.lap_pct);
        if (!point || !mergedBounds) return null;
        return {
          turn,
          point,
          layout: layoutTrackMapTurnLabel(point, mergedBounds, {
            labelOffsetRatio: 0.045,
            fontSizeRatio: 0.04,
            markerRadiusRatio: 0.009,
          }),
        };
      })
      .filter((item): item is NonNullable<typeof item> => item != null),
    [lapPositionedPoints, mergedBounds, pkg?.turns],
  );
  const hasDrawableTrack = Boolean(svgViewport && pointPath && drawablePoints.length > 1);
  const hasAnyContext = Boolean(cursorPoint || selectedEventPoint || highlightedPath);
  const title = pkg?.map?.metadata.display_name ?? pkg?.map?.metadata.track_name ?? trackName ?? "Track Map";
  const selectedLabel = selectedEventMarker?.label ?? (selection.selectedEventId ? "Selected event" : "Selected sample");

  if (!open) return null;

  const overlayStyle = {
    left: layout.left,
    top: layout.top,
    width: layout.width,
    height: layout.height,
    "--track-map-overlay-opacity": opacity,
  } as CSSProperties;

  return (
    <aside
      className={`track-map-overlay${interactionKind === "drag" ? " dragging" : ""}${interactionKind === "resize" ? " resizing" : ""}`}
      role="dialog"
      aria-modal="false"
      aria-labelledby="track-map-overlay-title"
      style={overlayStyle}
    >
      <header
        className="track-map-overlay-header"
        onPointerDown={(event) => beginOverlayInteraction("drag", event)}
        aria-label="Drag map overlay"
      >
        <div>
          <span className="eyebrow">Map Overlay</span>
          <h2 id="track-map-overlay-title"><MapPin size={15} /> {title}</h2>
        </div>
        <div className="track-map-overlay-controls">
          <label className="track-map-overlay-toggle">
            <input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} />
            Labels
          </label>
          <label className="track-map-overlay-toggle">
            <input type="checkbox" checked={showEvents} onChange={(event) => setShowEvents(event.target.checked)} />
            Events
          </label>
          <label className="track-map-overlay-opacity">
            <span>Opacity</span>
            <input
              type="range"
              min="0.6"
              max="0.9"
              step="0.05"
              value={opacity}
              onChange={(event) => setOpacity(Number(event.target.value))}
              aria-label="Map overlay opacity"
            />
          </label>
          <button className="track-map-overlay-close" type="button" onClick={onClose} aria-label="Close track map overlay">
            <X size={15} />
          </button>
        </div>
      </header>

      {loading && (
        <div className="track-map-overlay-empty">
          <strong>Loading local track map...</strong>
          <span>Chart inspection remains active.</span>
        </div>
      )}

      {!loading && (error || !pkg?.map || !hasDrawableTrack) && (
        <div className="track-map-overlay-empty" role="status">
          <strong>Track map unavailable</strong>
          <span>No local map data is available for this run.</span>
          <span>Chart inspection still works.</span>
        </div>
      )}

      {!loading && !error && hasDrawableTrack && svgViewport && (
        <>
          <div className="track-map-overlay-status" aria-live="polite">
            <span>{highlightedPath ? "Chart range highlighted" : "Hover or select chart data"}</span>
            {highlightedPath && <span>{formatDistanceRange(zoomRangeFt)}</span>}
          </div>
          <svg className="track-map-overlay-svg" viewBox={svgViewport.viewBox} role="img" aria-label={`Track map overlay for ${title}`}>
            <title>{`Track map overlay for ${title}`}</title>
            <path className="track-map-overlay-line" d={pointPath} />
            {highlightedPath && <path className="track-map-overlay-window" d={highlightedPath} aria-label="Current chart zoom window" />}
            {rangeStartPoint && <circle className="track-map-overlay-range-start" cx={rangeStartPoint.x} cy={rangeStartPoint.y} r={7} aria-label="Zoom range start" />}
            {rangeEndPoint && <circle className="track-map-overlay-range-end" cx={rangeEndPoint.x} cy={rangeEndPoint.y} r={7} aria-label="Zoom range end" />}
            {showLabels && sectionLabels.map(({ section, point }) => (
              <text key={section.section_id} className="track-map-overlay-section-label" x={point.x} y={point.y}>
                {section.name}
              </text>
            ))}
            {showLabels && turnLabels.map(({ turn, point, layout }) => (
              <g key={turn.turn_id} className="track-map-overlay-turn-marker">
                <title>{`${turn.label} — ${turn.lap_pct.toFixed(1)}% lap position`}</title>
                <line x1={point.x} y1={point.y} x2={layout.leaderEndX} y2={layout.leaderEndY} />
                <circle cx={point.x} cy={point.y} r={layout.markerRadius} />
                <text
                  className="track-map-overlay-turn-label"
                  x={layout.labelX}
                  y={layout.labelY}
                  fontSize={layout.fontSize}
                  textAnchor={layout.textAnchor}
                  dominantBaseline="middle"
                >
                  {turn.short_label}
                </text>
              </g>
            ))}
            {showEvents && visibleEventMarkers.map(({ overlay, point }) => (
              <circle
                key={overlay.marker_id}
                className="track-map-overlay-event"
                cx={point.x}
                cy={point.y}
                r={5}
                aria-label={`Event marker: ${overlay.label}`}
              />
            ))}
            {selectedEventPoint && (
              <g aria-label={selectedLabel}>
                <circle className="track-map-overlay-selected-ring" cx={selectedEventPoint.x} cy={selectedEventPoint.y} r={11} />
                <circle className="track-map-overlay-selected-dot" cx={selectedEventPoint.x} cy={selectedEventPoint.y} r={6} />
              </g>
            )}
            {cursorPoint && (
              <g aria-label="Current chart cursor marker">
                <circle className="track-map-overlay-cursor-ring" cx={cursorPoint.x} cy={cursorPoint.y} r={10} />
                <circle className="track-map-overlay-cursor-dot" cx={cursorPoint.x} cy={cursorPoint.y} r={4} />
              </g>
            )}
          </svg>
          {!hasAnyContext && (
            <p className="track-map-overlay-note">Hover or select chart data to locate it on track.</p>
          )}
        </>
      )}
      <button
        type="button"
        className="track-map-overlay-resize"
        onPointerDown={(event) => beginOverlayInteraction("resize", event)}
        aria-label="Resize map overlay"
        title="Resize map overlay"
      />
    </aside>
  );
}
