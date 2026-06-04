import {
  Crosshair, Info, Layers, Map as MapIcon, Pin, PinOff, Search, X, Copy,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  TrackMapBounds,
  TrackMapIndexEntry,
  TrackMapMarker,
  TrackMapOverlayMarker,
  TrackMapPackage,
  TrackMapPoint,
  TrackMapSection,
} from "../types/trackMap";
import { fetchRunTrackMapPackage, fetchTrackMaps } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { buildWindowEvidence } from "../utils/evidenceFocus";
import { calculateTrackLocation, describeLapPctRangeAsLocations } from "../utils/trackLocation";
import { buildTrackMapSummary, buildEventSentence, buildProblemFingerprints, buildNextBestClick } from "../utils/trackMapInsights";
import {
  type LayerId, type SeverityLevel, type PresetId,
  SEVERITY_RANK, LAYER_DEFS, PRESETS,
  classifyOverlayLayer, severityPasses, detectActivePreset,
} from "../utils/trackMapFilters";

const DEBUG_LOCATION = false;

interface Props {
  runId: string | null; lap?: number | null;
  trackName?: string | null; carName?: string | null; setupName?: string | null;
  targetZoneStartPct?: number; targetZoneEndPct?: number;
}

// ── constants ────────────────────────────────────────────────
type HeatmapMode = "normal" | "density" | "severity";

interface CategoryGroup {
  category: LayerId; label: string; events: TrackMapOverlayMarker[]; worst: TrackMapOverlayMarker | null;
}
type PlatformBalanceOverlay = TrackMapOverlayMarker & {
  front_platform_risk_score?: number | null;
  rear_platform_risk_score?: number | null;
  whole_car_bottoming_risk?: number | null;
  platform_balance_label?: string | null;
  rear_scrape_side_label?: string | null;
  platform_balance_explanation?: string | null;
};

type InspectorTarget =
  | { kind: "overlay"; overlay: TrackMapOverlayMarker }
  | { kind: "section"; section: TrackMapSection }
  | { kind: "none" };

const SEVERITY_HEAT_COLORS: Record<string, string> = {
  critical: "#ef4444", high: "#f97316", watch: "#f59e0b", info: "#38bdf8",
};

const CATEGORY_LABELS: Record<string, string> = {
  front_scrape: "Front Platform", rear_scrape: "Rear Platform",
  whole_car_bottoming: "Whole-Car", drag_scrub: "Drag/Scrub",
  aero: "Aero", shocks: "Shocks", speed_loss: "Speed Loss",
  all_events: "Other Events", delta: "Delta", insights: "Insights",
  tires: "Tires", notebook: "Notebook",
};

const MAP_PADDING_RATIO = 0.06;
const MAP_MIN_PADDING = 24;

type DrawablePoint = {
  source: TrackMapPoint;
  x: number;
  y: number;
  lapPct: number | null;
};

type DrawableMarker = TrackMapMarker & { x: number; y: number };
type DrawableOverlay = TrackMapOverlayMarker & { x: number; y: number };

type NumericBounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  width: number;
  height: number;
};

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function getTrackPointCoordinate(point: Pick<TrackMapPoint, "x" | "y" | "x_m" | "y_m">): { x: number; y: number } | null {
  const x = isFiniteNumber(point.x_m) ? point.x_m : isFiniteNumber(point.x) ? point.x : null;
  const y = isFiniteNumber(point.y_m) ? point.y_m : isFiniteNumber(point.y) ? point.y : null;
  if (x == null || y == null) return null;
  return { x, y };
}

function getXYCoordinate(point: { x?: number | null; y?: number | null }): { x: number; y: number } | null {
  if (!isFiniteNumber(point.x) || !isFiniteNumber(point.y)) return null;
  return { x: point.x, y: point.y };
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

function getBoundsFromCanonicalBounds(bounds: TrackMapBounds | null | undefined): NumericBounds | null {
  if (!bounds) return null;
  if (
    !isFiniteNumber(bounds.min_x_m) ||
    !isFiniteNumber(bounds.max_x_m) ||
    !isFiniteNumber(bounds.min_y_m) ||
    !isFiniteNumber(bounds.max_y_m)
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

function collectLapRangePoints(points: DrawablePoint[], section: TrackMapSection): DrawablePoint[] {
  return points.filter((point) => {
    if (!isFiniteNumber(point.lapPct)) return false;
    return section.wraps_start_finish
      ? point.lapPct >= section.start_lap_pct || point.lapPct <= section.end_lap_pct
      : point.lapPct >= section.start_lap_pct && point.lapPct <= section.end_lap_pct;
  });
}

function circularLapDifference(a: number, b: number): number {
  const diff = Math.abs(a - b);
  return Math.min(diff, 100 - diff);
}

function interpolatePointAtLapPct(points: DrawablePoint[], lapPct: number | null | undefined): { x: number; y: number } | null {
  if (!isFiniteNumber(lapPct) || points.length < 2) return null;
  let bestPoint: DrawablePoint | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const point of points) {
    if (!isFiniteNumber(point.lapPct)) continue;
    const distance = circularLapDifference(point.lapPct, lapPct);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestPoint = point;
    }
  }
  return bestPoint ? { x: bestPoint.x, y: bestPoint.y } : null;
}

function groupEventsByCategory(events: TrackMapOverlayMarker[]): CategoryGroup[] {
  const m = new Map<LayerId, TrackMapOverlayMarker[]>();
  for (const e of events) {
    const c = classifyOverlayLayer(e);
    if (!m.has(c)) m.set(c, []);
    m.get(c)!.push(e);
  }
  return [...m.entries()].map(([c, evts]) => ({
    category: c,
    label: CATEGORY_LABELS[c] ?? c,
    events: evts,
    worst: evts.reduce((a, b) =>
      (SEVERITY_RANK[a.severity ?? "info"] ?? 99) <= (SEVERITY_RANK[b.severity ?? "info"] ?? 99) ? a : b, evts[0]),
  }));
}

function areaRiskScore(events: TrackMapOverlayMarker[]): number {
  return events.reduce((sum, e) => {
    const s = e.severity ?? "info";
    return sum + (s === "critical" ? 5 : s === "high" ? 3 : s === "watch" ? 1 : 0);
  }, 0);
}

export function TrackMapTab({ runId, lap, trackName, carName, setupName, targetZoneStartPct, targetZoneEndPct }: Props) {
  const [pkg, setPkg] = useState<TrackMapPackage|null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [activeLayers, setActiveLayers] = useState<Set<LayerId>>(()=>new Set(["sections","target_zone","markers","all_events"]));
  const [severityFilter, setSeverityFilter] = useState<SeverityLevel>("all");
  const [heatmap, setHeatmap] = useState<HeatmapMode>("normal");
  const [inspector, setInspector] = useState<InspectorTarget>({kind:"none"});
  const [availableMaps, setAvailableMaps] = useState<TrackMapIndexEntry[]>([]);
  const [mapSearch, setMapSearch] = useState("");
  const [preferredMapId, setPreferredMapId] = useState<string | null>(null);
  const [problemFocus, setProblemFocus] = useState(false);
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(new Set());
  const [selectedArea, setSelectedArea] = useState<string | null>(null);
  const inspectorRef = useRef<HTMLDivElement>(null);
  const loadSeqRef = useRef(0);
  const { selection, focusEvidence, setWorkspace } = useTelemetrySelection();

  useEffect(() => {
    let cancelled = false;
    fetchTrackMaps()
      .then((maps) => {
        if (!cancelled) setAvailableMaps(maps);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    const seq = ++loadSeqRef.current;
    if (!runId) {
      setPkg(null);
      setLoading(false);
      setError(null);
      return () => { cancelled = true; };
    }
    setLoading(true);
    setError(null);
    fetchRunTrackMapPackage(runId, {
      lap: lap ?? undefined,
      target_zone_start_pct: targetZoneStartPct,
      target_zone_end_pct: targetZoneEndPct,
      preferred_map_id: preferredMapId ?? undefined,
    })
      .then((nextPkg) => {
        if (!cancelled && seq === loadSeqRef.current) setPkg(nextPkg);
      })
      .catch((e) => {
        if (!cancelled && seq === loadSeqRef.current) {
          setError(e instanceof Error ? e.message : "Failed to load track map");
        }
      })
      .finally(() => {
        if (!cancelled && seq === loadSeqRef.current) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, lap, targetZoneStartPct, targetZoneEndPct, preferredMapId]);

  const points = pkg?.map?.points ?? [];
  const bounds = pkg?.map?.bounds;
  const overlays = pkg?.overlays ?? [];
  const markers = pkg?.markers?.length ? pkg.markers : pkg?.map?.markers ?? [];
  const sections = pkg?.sections?.length ? pkg.sections : pkg?.map?.sections ?? [];
  const metadata = pkg?.map?.metadata;
  const match = pkg?.match;
  const hasMap = pkg?.map != null;
  const isMapLoading = loading;
  const mapError = error;
  const hasPoints = points.length > 0;

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
          };
        })
        .filter((point): point is DrawablePoint => point != null),
    [points],
  );

  const boundsFromPayload = useMemo(() => getBoundsFromCanonicalBounds(bounds), [bounds]);
  const boundsFromPoints = useMemo(() => getBoundsFromPoints(drawablePoints), [drawablePoints]);
  const mergedBounds = useMemo(() => mergeBounds(boundsFromPayload, boundsFromPoints), [boundsFromPayload, boundsFromPoints]);
  const hasBounds = mergedBounds != null;

  const svgViewport = useMemo(() => {
    if (!mergedBounds) return null;
    const maxDimension = Math.max(mergedBounds.width, mergedBounds.height);
    const padding = Math.max(maxDimension * MAP_PADDING_RATIO, MAP_MIN_PADDING);
    const width = mergedBounds.width + padding * 2;
    const height = mergedBounds.height + padding * 2;
    if (!(width > 0) || !(height > 0)) return null;
    return {
      ...mergedBounds,
      padding,
      viewBox: `${mergedBounds.minX - padding} ${mergedBounds.minY - padding} ${width} ${height}`,
    };
  }, [mergedBounds]);

  const pointPath = useMemo(() => buildSvgPath(drawablePoints), [drawablePoints]);
  const hasDrawableTrack = drawablePoints.length > 1 && svgViewport != null && pointPath.length > 0;
  const currentMapId = pkg?.map?.map_id ?? "track-map";

  const markerPositionsByName = useMemo(() => {
    const entries = new Map<string, { x: number; y: number }>();
    markers.forEach((marker) => {
      const coordinate = getXYCoordinate(marker);
      if (coordinate) entries.set(marker.name, coordinate);
    });
    return entries;
  }, [markers]);

  const drawableMarkers = useMemo<DrawableMarker[]>(
    () =>
      markers
        .map((marker) => {
          const coordinate = getXYCoordinate(marker);
          return coordinate ? { ...marker, x: coordinate.x, y: coordinate.y } : null;
        })
        .filter((marker): marker is DrawableMarker => marker != null),
    [markers],
  );

  useEffect(() => {
    if (isMapLoading) {
      setInspector({ kind: "none" });
      setSelectedArea(null);
    }
  }, [isMapLoading, runId, lap, preferredMapId]);

  useEffect(() => {
    if (selectedArea && !sections.some((section) => section.section_id === selectedArea)) {
      setSelectedArea(null);
    }
    if (inspector.kind === "section" && !sections.some((section) => section.section_id === inspector.section.section_id)) {
      setInspector({ kind: "none" });
    }
    if (inspector.kind === "overlay" && !overlays.some((overlay) => overlay.marker_id === inspector.overlay.marker_id)) {
      setInspector({ kind: "none" });
    }
  }, [currentMapId, sections, overlays, selectedArea, inspector]);

  const getLocation = useCallback(
    (lapPct: number | null | undefined) => calculateTrackLocation(lapPct, sections),
    [sections],
  );

  const windowContextActive = selection.selectedLapScope === "lap_window"
    && selection.selectedLapWindowStart != null
    && selection.selectedLapWindowEnd != null;
  const representativeLap = selection.selectedRepresentativeLap ?? lap ?? selection.selectedLap ?? null;
  const selectedAreaSection = useMemo(
    () => (selectedArea ? sections.find((s) => s.section_id === selectedArea) ?? null : null),
    [sections, selectedArea],
  );
  const selectedAreaLabel = useMemo(
    () => (selectedAreaSection ? describeLapPctRangeAsLocations(selectedAreaSection.start_lap_pct, selectedAreaSection.end_lap_pct, sections) : null),
    [selectedAreaSection, sections],
  );
  const sectionMidLapPct = useCallback((section: TrackMapSection) => {
    const span = (section.end_lap_pct - section.start_lap_pct + 100) % 100;
    return (section.start_lap_pct + span / 2) % 100;
  }, []);
  const sectionValueBasis = windowContextActive ? "selected_window" as const : "full_lap" as const;

  const buildSectionEvidence = useCallback((section: TrackMapSection) => ({
    runId,
    lapNumber: representativeLap,
    ...buildWindowEvidence(selection, representativeLap),
    eventId: null,
    sampleIndex: null,
    lapDistFt: section.start_distance_ft ?? null,
    lapPct: sectionMidLapPct(section),
    zoneId: section.section_id,
    zoneLabel: describeLapPctRangeAsLocations(section.start_lap_pct, section.end_lap_pct, sections),
    zoneStartPct: section.start_lap_pct,
    zoneEndPct: section.end_lap_pct,
    channelId: null,
    selectionSource: "track_map" as const,
    lockState: "locked" as const,
    valueBasis: sectionValueBasis,
    trustTier: null,
  }), [representativeLap, runId, sectionMidLapPct, sections, sectionValueBasis, selection]);

  const buildOverlayEvidence = useCallback((overlay: TrackMapOverlayMarker) => {
    const loc = getLocation(overlay.lap_pct);
    return {
      runId,
      lapNumber: representativeLap,
      ...buildWindowEvidence(selection, representativeLap),
      eventId: overlay.kind === "platform_event" ? overlay.source_id ?? null : null,
      sampleIndex: null,
      lapDistFt: overlay.distance_ft ?? null,
      lapPct: overlay.lap_pct ?? null,
      zoneId: loc.section_id,
      zoneLabel: loc.friendly_section_name !== "Unknown section" ? loc.friendly_section_name : null,
      zoneStartPct: loc.start_lap_pct ?? null,
      zoneEndPct: loc.end_lap_pct ?? null,
      channelId: null,
      selectionSource: "track_map" as const,
      lockState: "locked" as const,
      valueBasis: "selected_sample" as const,
      trustTier: overlay.confidence ?? null,
    };
  }, [getLocation, representativeLap, runId, selection]);

  // ── Active preset ────────────────────────────────────────────
  const activePreset = useMemo(
    () => detectActivePreset(activeLayers, severityFilter),
    [activeLayers, severityFilter],
  );

  // ── Handlers ─────────────────────────────────────────────────
  const handleOverlayClick = useCallback(
    (o: TrackMapOverlayMarker) => {
      setInspector({ kind: "overlay", overlay: o });
      focusEvidence(buildOverlayEvidence(o));
      inspectorRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    },
    [buildOverlayEvidence, focusEvidence],
  );

  const handleSectionClick = useCallback(
    (s: TrackMapSection) => {
      setInspector({ kind: "section", section: s });
      setSelectedArea(s.section_id);
      focusEvidence(buildSectionEvidence(s));
    },
    [buildSectionEvidence, focusEvidence],
  );

  const toggleLayer = useCallback((id: LayerId) =>
    setActiveLayers((p) => {
      const n = new Set(p);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    }), []);

  const applyPreset = useCallback((presetId: PresetId) => {
    const preset = PRESETS.find((p) => p.id === presetId);
    if (!preset) return;
    setActiveLayers(new Set(preset.layers));
    setSeverityFilter(preset.severity);
  }, []);

  const togglePin = useCallback((markerId: string) =>
    setPinnedIds((p) => {
      const n = new Set(p);
      n.has(markerId) ? n.delete(markerId) : n.add(markerId);
      return n;
    }), []);

  const setPreferredMap = useCallback((id: string) => {
    setPreferredMapId(id);
    setInspector({ kind: "none" });
  }, []);

  const clearPreferredMap = useCallback(() => {
    setPreferredMapId(null);
    setMapSearch("");
  }, []);

  const focusSelected = useCallback(() => {
    inspectorRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [inspectorRef]);

  // ── Computed overlays ────────────────────────────────────────
  const layerCounts = useMemo(() => {
    const c = new Map<LayerId, number>();
    for (const o of overlays) {
      const cat = classifyOverlayLayer(o);
      c.set(cat, (c.get(cat) ?? 0) + 1);
      c.set("all_events", (c.get("all_events") ?? 0) + 1);
    }
    return c;
  }, [overlays]);

  const visibleOverlays = useMemo(
    () =>
      overlays.filter((o) => {
        const cat = classifyOverlayLayer(o);
        if (cat === "all_events" && !activeLayers.has("all_events")) {
          const el = LAYER_DEFS.filter((d) => d.group === "events" && d.id !== "all_events").map((d) => d.id);
          if (!el.some((id) => activeLayers.has(id))) return false;
        } else if (!activeLayers.has(cat) && cat !== "all_events") {
          return false;
        }
        if (problemFocus && o.kind === "platform_event") {
          const s = o.severity ?? "info";
          if (s === "info") return false;
        }
        return severityPasses(o.severity, severityFilter);
      }),
    [overlays, activeLayers, severityFilter, problemFocus],
  );
  const orderedVisibleOverlays = useMemo(
    () => [...visibleOverlays].sort((a, b) => (SEVERITY_RANK[b.severity ?? "info"] ?? 99) - (SEVERITY_RANK[a.severity ?? "info"] ?? 99)),
    [visibleOverlays],
  );

  const selectedHidden =
    inspector.kind === "overlay" &&
    !visibleOverlays.some((o) => o.marker_id === inspector.overlay.marker_id);

  // ── Section stats ────────────────────────────────────────────
  const sectionStats = useMemo(
    () =>
      sections.map((s) => {
        const evts = overlays.filter((o) => {
          if (o.lap_pct == null) return false;
          return s.wraps_start_finish
            ? o.lap_pct >= s.start_lap_pct || o.lap_pct <= s.end_lap_pct
            : o.lap_pct >= s.start_lap_pct && o.lap_pct <= s.end_lap_pct;
        });
        const worst = evts.reduce(
          (a, b) =>
            (SEVERITY_RANK[a.severity ?? "info"] ?? 99) <= (SEVERITY_RANK[b.severity ?? "info"] ?? 99) ? a : b,
          evts[0],
        );
        const cats = new Map<string, number>();
        for (const e of evts) {
          const c = classifyOverlayLayer(e);
          cats.set(c, (cats.get(c) ?? 0) + 1);
        }
        let topCat = "";
        let topN = 0;
        for (const [k, v] of cats) if (v > topN) { topCat = k; topN = v; }
        return { section: s, count: evts.length, worst, topCat, riskScore: areaRiskScore(evts) };
      }),
    [sections, overlays],
  );

  // ── Summary ──────────────────────────────────────────────────
  const summary = useMemo(
    () =>
      buildTrackMapSummary({
        visibleOverlays,
        sections,
        activePreset: activePreset,
        problemFocus,
        pinnedCount: pinnedIds.size,
        manualMap: preferredMapId != null,
      }),
    [visibleOverlays, sections, activePreset, problemFocus, pinnedIds, preferredMapId],
  );

  // ── Fingerprints ─────────────────────────────────────────────
  const fingerprints = useMemo(
    () => buildProblemFingerprints(visibleOverlays, sections),
    [visibleOverlays, sections],
  );

  // ── Next Best Click ──────────────────────────────────────────
  const nextBestClick = useMemo(
    () =>
      buildNextBestClick(
        visibleOverlays,
        sections,
        inspector.kind === "overlay" ? inspector.overlay.marker_id : null,
      ),
    [visibleOverlays, sections, inspector],
  );

  // ── Pinned evidence ──────────────────────────────────────────
  const pinnedOverlays = useMemo(
    () =>
      [...pinnedIds]
        .map((id) => overlays.find((o) => o.marker_id === id))
        .filter((o): o is TrackMapOverlayMarker => o != null)
        .slice(0, 5),
    [pinnedIds, overlays],
  );

  // ── Clusters ─────────────────────────────────────────────────
  const clusters = useMemo(() => {
    const groups = new Map<string, TrackMapOverlayMarker[]>();
    for (const o of visibleOverlays) {
      if (o.kind !== "platform_event" || o.lap_pct == null) continue;
      const loc = getLocation(o.lap_pct);
      const key = `${loc.friendly_section_name}|${loc.phase ?? "unknown"}|${classifyOverlayLayer(o)}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(o);
    }
    return [...groups.entries()]
      .filter(([, evts]) => evts.length > 1)
      .map(([key, evts]) => {
        const [sectionName, phase] = key.split("|");
        const worst = evts.reduce((a, b) =>
          (SEVERITY_RANK[a.severity ?? "info"] ?? 99) <= (SEVERITY_RANK[b.severity ?? "info"] ?? 99) ? a : b,
        );
        return { key, sectionName, phase, count: evts.length, worst, events: evts };
      })
      .sort((a, b) => b.count - a.count);
  }, [visibleOverlays, getLocation]);

  // ── Copy summary ─────────────────────────────────────────────
  const copySummary = useCallback(() => {
    const selOvl = inspector.kind === "overlay" ? inspector.overlay : null;
    const selLoc = selOvl ? getLocation(selOvl.lap_pct) : null;
    const lines = [
      "RacerZLab Track Map Summary",
      `Map: ${metadata?.track_name ?? "Unknown"}`,
      ...(selLoc ? [`Location: ${selLoc.display_label}`] : []),
      ...(selOvl ? [`Event: ${selOvl.label}`, `Severity: ${selOvl.severity ?? "info"}`] : []),
      ...(summary.worstEvent ? [`Worst: ${summary.worstEvent.label} in ${summary.worstLocation}`] : []),
      `Visible events: ${summary.total} across ${summary.affectedAreas} areas`,
      ...(summary.dominantCategory ? [`Dominant category: ${summary.dominantCategory}`] : []),
      ...(summary.mostAffectedArea ? [`Most affected area: ${summary.mostAffectedArea}`] : []),
      ...(fingerprints.length ? ["", "Patterns:", ...fingerprints.map((f) => `  ${f.pattern}`)] : []),
      ...(pinnedOverlays.length ? ["", "Pinned:", ...pinnedOverlays.map((p) => `  ${getLocation(p.lap_pct).display_label} · ${p.label}`)] : []),
      ...(metadata?.warnings?.length ? ["", "Warnings:", ...metadata.warnings] : []),
    ];
    const text = lines.join("\n");
    navigator.clipboard.writeText(text).catch(() => {});
  }, [inspector, metadata, summary, fingerprints, pinnedOverlays, getLocation]);

  // ── Keyboard shortcuts ───────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      switch (e.key) {
        case "Escape":
          setInspector({ kind: "none" });
          setSelectedArea(null);
          break;
        case "f":
        case "F":
          setProblemFocus((p) => !p);
          break;
        case "a":
        case "A":
          applyPreset("all");
          break;
        case "s":
        case "S":
          applyPreset("scrape");
          break;
        case "m":
        case "M":
          applyPreset("map_only");
          break;
        case "ArrowLeft": {
          const vis = visibleOverlays.filter((o) => o.kind === "platform_event");
          if (!vis.length) break;
          const idx = vis.findIndex((o) => o.marker_id === (inspector.kind === "overlay" ? inspector.overlay.marker_id : null));
          const prev = idx > 0 ? vis[idx - 1] : vis[vis.length - 1];
          handleOverlayClick(prev);
          break;
        }
        case "ArrowRight": {
          const vis = visibleOverlays.filter((o) => o.kind === "platform_event");
          if (!vis.length) break;
          const idx = vis.findIndex((o) => o.marker_id === (inspector.kind === "overlay" ? inspector.overlay.marker_id : null));
          const next = idx < vis.length - 1 ? vis[idx + 1] : vis[0];
          handleOverlayClick(next);
          break;
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [visibleOverlays, inspector, handleOverlayClick, applyPreset]);

  // ── heatmap section color ──
  const sectionColor = useCallback((sp: { count: number; worst: TrackMapOverlayMarker | null }, selected: boolean) => {
    if (heatmap === "density") {
      const maxEvts = Math.max(1, ...sectionStats.map((s) => s.count));
      const t = sp.count / maxEvts;
      return selected
        ? "#38bdf8"
        : `rgba(${Math.round(56 + 180 * t)},${Math.round(189 - 150 * t)},${Math.round(248 - 200 * t)},${0.4 + 0.5 * t})`;
    }
    if (heatmap === "severity" && sp.worst) {
      return selected ? "#38bdf8" : SEVERITY_HEAT_COLORS[sp.worst.severity ?? "info"] ?? "#8d9aaa";
    }
    return selected ? "#38bdf8" : "#1e40af";
  }, [heatmap, sectionStats]);

  // ── SVG ──
  const clipPathId = useMemo(() => `trackmap-clip-${currentMapId.replace(/[^a-zA-Z0-9_-]/g, "-")}`, [currentMapId]);
  const gridPatternId = useMemo(() => `trackmap-grid-${currentMapId.replace(/[^a-zA-Z0-9_-]/g, "-")}`, [currentMapId]);

  const tzPath = useMemo(() => {
    const explicitPoints =
      pkg?.target_zone?.points
        ?.map((point) => getXYCoordinate(point))
        .filter((point): point is { x: number; y: number } => point != null) ?? [];
    if (explicitPoints.length >= 2) return buildSvgPath(explicitPoints);

    const targetOverlay = overlays.find((overlay) => overlay.kind === "target_zone");
    const overlayPoints =
      targetOverlay?.points
        ?.map((point) => getXYCoordinate(point))
        .filter((point): point is { x: number; y: number } => point != null) ?? [];
    if (overlayPoints.length >= 2) return buildSvgPath(overlayPoints);

    const startPct = pkg?.target_zone?.start_pct ?? targetOverlay?.start_pct ?? null;
    const endPct = pkg?.target_zone?.end_pct ?? targetOverlay?.end_pct ?? null;
    if (!isFiniteNumber(startPct) || !isFiniteNumber(endPct) || drawablePoints.length < 2) return null;
    const wraps = startPct > endPct;
    const zonePoints = drawablePoints.filter((point) =>
      point.lapPct == null
        ? false
        : wraps
          ? point.lapPct >= startPct || point.lapPct <= endPct
          : point.lapPct >= startPct && point.lapPct <= endPct,
    );
    return buildSvgPath(zonePoints);
  }, [pkg?.target_zone, overlays, drawablePoints]);

  const sectionPolylines = useMemo(() => {
    if (!activeLayers.has("sections") || !sections.length || !hasDrawableTrack) return [];
    return sections
      .map((s) => {
        const sectionPoints = collectLapRangePoints(drawablePoints, s);
        const midpoint = interpolatePointAtLapPct(drawablePoints, sectionMidLapPct(s));
        const startMarker = markerPositionsByName.get(s.start_marker) ?? null;
        const endMarker = markerPositionsByName.get(s.end_marker) ?? null;
        const label =
          midpoint ??
          (startMarker && endMarker
            ? { x: (startMarker.x + endMarker.x) / 2, y: (startMarker.y + endMarker.y) / 2 }
            : startMarker ?? endMarker);
        return { section: s, d: buildSvgPath(sectionPoints), count: sectionPoints.length, label };
      })
      .filter((sp) => sp.count > 1 && sp.d.length > 0);
  }, [activeLayers, sections, hasDrawableTrack, drawablePoints, sectionMidLapPct, markerPositionsByName]);

  const drawableOverlayEvents = useMemo<DrawableOverlay[]>(
    () =>
      orderedVisibleOverlays
        .filter((overlay) => overlay.kind === "platform_event")
        .map((overlay) => {
          const coordinate = getXYCoordinate(overlay) ?? interpolatePointAtLapPct(drawablePoints, overlay.lap_pct);
          return coordinate ? { ...overlay, x: coordinate.x, y: coordinate.y } : null;
        })
        .filter((overlay): overlay is DrawableOverlay => overlay != null),
    [orderedVisibleOverlays, drawablePoints],
  );

  const mapWarnings = useMemo(
    () =>
      [...(pkg?.warnings ?? []), ...(pkg?.map?.warnings ?? []), ...(metadata?.warnings ?? [])].filter(
        (warning, index, source) => source.indexOf(warning) === index,
      ),
    [pkg?.warnings, pkg?.map?.warnings, metadata?.warnings],
  );

  // ── Empty states ─────────────────────────────────────────────
  if (!runId)
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="muted">No run loaded. Import an .ibt file to view telemetry events on a track map.</p>
      </section>
    );
  if (isMapLoading)
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="muted">Loading track map...</p>
      </section>
    );
  if (mapError)
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="error-text">{mapError}</p>
      </section>
    );
  if (!hasMap) {
    const filtered = availableMaps.filter(
      (m) =>
        !mapSearch ||
        m.display_name.toLowerCase().includes(mapSearch.toLowerCase()) ||
        m.track_key.toLowerCase().includes(mapSearch.toLowerCase()) ||
        m.layout_key.toLowerCase().includes(mapSearch.toLowerCase()),
    );
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <div className="notebook-empty">
          <p>No local RacerZLab cached map matched this run.</p>
          <p className="muted">Import a track map file or choose an imported map manually.</p>
          <p className="muted">Choose an imported map manually:</p>
          <div className="trackmap-manual-select">
            <div className="trackmap-search-row">
              <Search size={14} className="muted" />
              <input
                className="trackmap-search-input"
                placeholder="Search maps…"
                value={mapSearch}
                onChange={(e) => setMapSearch(e.target.value)}
              />
            </div>
            {filtered.length > 0 ? (
              <select
                className="trackmap-select"
                size={Math.min(8, filtered.length)}
                value={preferredMapId ?? ""}
                onChange={(e) => setPreferredMap(e.target.value)}
              >
                <option value="" disabled>Select a track map…</option>
                {filtered.map((m) => (
                  <option key={m.map_id} value={m.map_id}>
                    {m.display_name} — {m.distance_ft.toFixed(0)} ft
                    {m.partial ? " · partial" : ""}
                  </option>
                ))}
              </select>
            ) : (
              <p className="muted">No maps found for "{mapSearch}"</p>
            )}
          </div>
        </div>
      </section>
    );
  }

  const selSecId = inspector.kind === "section" ? inspector.section.section_id : selectedArea;
  const selOvlId = inspector.kind === "overlay" ? inspector.overlay.marker_id : null;
  const visiblePlatformOverlayCount = orderedVisibleOverlays.filter((overlay) => overlay.kind === "platform_event").length;
  const mapEmptyMessage = !hasPoints
    ? "Imported map has no drawable centerline points."
    : !hasBounds
      ? "Imported map has no usable centerline bounds."
    : !hasDrawableTrack
      ? "Imported map has no drawable centerline points."
      : null;

  return (
    <section className="trackmap-cockpit">
      <div className="trackmap-left">
        {/* ── Header ── */}
        <header className="trackmap-header">
          <h2><MapIcon size={18} /> {metadata?.track_name ?? "Track Map"}</h2>
          <div className="trackmap-header-stats">
            <span className="source-badge source-mt2">Imported map</span>
            {metadata && <span>{metadata.distance_miles.toFixed(2)} mi · {metadata.distance_ft.toFixed(0)} ft</span>}
            <span>{points.length.toLocaleString()} pts</span>
            <span>{markers.length} mk · {sections.length} sec</span>
          </div>
          <div className="trackmap-header-run">
            {trackName && <span className="muted">{trackName}</span>}
            {carName && <span className="muted">— {carName}</span>}
            {setupName && <span className="muted">· {setupName}</span>}
          </div>
          <div className="trackmap-header-run">
            <span className="muted">Using local RacerZLab cached map data for matching, overlays, and interpolation.</span>
          </div>
          {windowContextActive && (
            <p className="scope-banner">
              Selected window: Laps {selection.selectedLapWindowStart}-{selection.selectedLapWindowEnd}. Map is currently showing representative lap {representativeLap ?? selection.selectedLapWindowStart}. Full window overlay filtering is not yet supported, so the window context stays preserved for navigation and event focus.
            </p>
          )}
          {match && (
            <div className="trackmap-header-match">
              <span className="map-confidence-badge" data-confidence={match.match_confidence ?? "medium"}>
                {match.match_confidence ?? "medium"}
              </span>
              <span className="muted">{match.display_name}</span>
              {lap != null && <span className="muted">· Lap {lap}</span>}
              {preferredMapId && (
                <button className="trackmap-action-btn" onClick={clearPreferredMap} title="Clear manual map" aria-label="Clear manual map selection">
                  <X size={12} /> Clear
                </button>
              )}
            </div>
          )}
        </header>

        {/* ── Summary ── */}
        {summary.total > 0 && (
          <div className="trackmap-summary">
            <span>
              {summary.total} visible event{summary.total !== 1 ? "s" : ""} across {summary.affectedAreas} area{summary.affectedAreas !== 1 ? "s" : ""}.
            </span>
            {summary.worstEvent && (
              <span>
                {" "}Worst: <span className="event-symbol" style={{ color: summary.worstEvent.color }}>
                  {summary.worstEvent.symbol} {summary.worstEvent.label}
                </span> in {summary.worstLocation}.
              </span>
            )}
            {summary.dominantCategory && (
              <span className="muted" style={{ marginLeft: 4 }}>
                {" "}Dominant: {summary.dominantCategory}.
              </span>
            )}
            {summary.mostAffectedArea && (
              <span className="muted" style={{ marginLeft: 4 }}>
                {" "}Most affected: {summary.mostAffectedArea}.
              </span>
            )}
            {problemFocus && <span className="inspector-badge inspector-badge-sm" style={{ marginLeft: 6 }}>Problem Focus</span>}
            {preferredMapId && <span className="inspector-badge inspector-badge-sm" style={{ marginLeft: 6 }}>Manual Map</span>}
            {activePreset !== "all" && activePreset !== "custom" && (
              <span className="muted" style={{ marginLeft: 4 }}>Preset: {PRESETS.find((p) => p.id === activePreset)?.label ?? activePreset}.</span>
            )}
            {fingerprints.length > 0 && (
              <div className="trackmap-fingerprints" style={{ marginTop: 4 }}>
                {fingerprints.slice(0, 2).map((fp, i) => (
                  <span key={i} className="muted" style={{ display: "block", fontSize: 11 }}>
                    Pattern: {fp.pattern}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {summary.total === 0 && overlays.length > 0 && (
          <div className="trackmap-summary muted">
            Active filters hide all events. Switch preset to All or lower the severity filter.
          </div>
        )}

        {summary.total === 0 && overlays.length === 0 && (
          <div className="trackmap-summary muted">
            Map loaded. No telemetry overlays are available for the selected lap.
          </div>
        )}

        {windowContextActive && (
          <div className="laps-chip-row" style={{ marginBottom: 8 }}>
            <span className="lap-flag-badge">Window {selection.selectedLapWindowStart}-{selection.selectedLapWindowEnd}</span>
            {representativeLap != null && <span className="lap-flag-badge">Rep Lap {representativeLap}</span>}
          </div>
        )}

        {preferredMapId && match?.display_name && (
          <div className="laps-chip-row" style={{ marginBottom: 8 }}>
            <span className="lap-flag-badge">Using {match.display_name}</span>
            <button className="trackmap-action-btn" onClick={clearPreferredMap} aria-label="Reset manual map selection">
              <X size={10} /> Reset
            </button>
          </div>
        )}

        {metadata && !metadata.origin.gps_supported && (
          <div className="map-warning-banner"><Info size={14} /><span>Centerline-only imported map — no boundaries, banking, GPS, or track width found.</span></div>
        )}

        {mapWarnings.length > 0 && (
          <div className="trackmap-warning-row" aria-label="Track map warnings">
            {mapWarnings.map((warning) => (
              <span key={`${currentMapId}-${warning}`} className="trackmap-warning-chip">
                {warning}
              </span>
            ))}
          </div>
        )}

        {/* ── Target zone translation ── */}
        {targetZoneStartPct != null && targetZoneEndPct != null && sections.length > 0 && (
          <div className="trackmap-target-zone-label">
            <span className="inspector-badge inspector-badge-sm" style={{ background: "#22c55e20", color: "#22c55e" }}>
              Target Zone
            </span>
            <span style={{ marginLeft: 6 }}>
              {describeLapPctRangeAsLocations(targetZoneStartPct, targetZoneEndPct, sections)}
            </span>
          </div>
        )}

        <div className="trackmap-mode-row" style={{ marginBottom: 8 }}>
          <label className="muted" style={{ fontSize: 11 }}>
            Overlay Layer
            <select
              className="trackmap-select trackmap-select-sm"
              value={activePreset}
              onChange={(e) => applyPreset(e.target.value as typeof activePreset)}
              style={{ marginLeft: 6 }}
            >
              <option value="all">Events / Severity</option>
              <option value="drag_scrub">Scrub Risk</option>
              <option value="platform">Platform Risk</option>
              <option value="aero">Ride Height / Aero</option>
              <option value="shocks">Shock Activity</option>
            </select>
          </label>
          <label className="muted" style={{ fontSize: 11 }}>
            Severity
            <select className="trackmap-select trackmap-select-sm" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value as SeverityLevel)} style={{ marginLeft: 6 }}>
              <option value="all">All</option>
              <option value="critical">Critical</option>
              <option value="high">High+</option>
              <option value="watch">Watch+</option>
              <option value="info">Info+</option>
            </select>
          </label>
          {selectedAreaSection && hasDrawableTrack && (
            <span className="lap-flag-badge">
              {selectedAreaLabel ?? selectedAreaSection.section_id}
            </span>
          )}
          {selectedAreaSection && hasDrawableTrack && (
            <button
              className="trackmap-action-btn"
              onClick={() => {
                focusEvidence(buildSectionEvidence(selectedAreaSection), "laps");
                setWorkspace("laps", "track_map");
              }}
              title="Review selected zone in Laps"
            >
              <Crosshair size={12} /> Review Selected Zone
            </button>
          )}
          {preferredMapId && (
            <button className="trackmap-action-btn" onClick={clearPreferredMap} aria-label="Reset manual map selection">
              <X size={10} /> Reset
            </button>
          )}
        </div>

        {/* ── Mode row ── */}
        <div className="trackmap-mode-row">
          <div className="trackmap-quick-actions">
            <button className={`trackmap-action-btn${heatmap === "normal" ? " active" : ""}`} onClick={() => setHeatmap("normal")}>Normal</button>
            <button className={`trackmap-action-btn${heatmap === "density" ? " active" : ""}`} onClick={() => setHeatmap("density")}>Density</button>
            <button className={`trackmap-action-btn${heatmap === "severity" ? " active" : ""}`} onClick={() => setHeatmap("severity")}>Severity</button>
          </div>
          <button className="trackmap-action-btn" onClick={focusSelected} title="Focus selected"><Crosshair size={12} /> Focus</button>
          <button className={`trackmap-action-btn${problemFocus ? " active" : ""}`} onClick={() => setProblemFocus((p) => !p)} title="Toggle Problem Focus">
            F
          </button>
          {selectedAreaSection && hasDrawableTrack && (
            <button
              className="trackmap-action-btn"
              onClick={() => {
                focusEvidence(buildSectionEvidence(selectedAreaSection), "laps");
                setWorkspace("laps", "track_map");
              }}
              title="Review selected zone in Laps"
              aria-label={`Review selected zone ${selectedAreaLabel ?? selectedAreaSection.section_id} in Laps`}
            >
              <Crosshair size={12} /> Review Selected Zone
            </button>
          )}
          <button className="trackmap-action-btn" onClick={copySummary} title="Copy Summary">
            <Copy size={12} /> Copy
          </button>
        </div>
        {heatmap === "severity" && (
          <div className="trackmap-summary muted" style={{ marginTop: 6 }}>
            Severity legend: Critical (red), High (orange), Watch (amber), Info (blue).
          </div>
        )}

        {/* ── Presets ── */}
        <div className="trackmap-presets">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              className={`trackmap-action-btn${activePreset === p.id ? " active" : ""}`}
              onClick={() => applyPreset(p.id)}
              title={p.label}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* ── SVG ── */}
        <div className="trackmap-canvas">
          {hasDrawableTrack && svgViewport ? (
            <svg
              viewBox={svgViewport.viewBox}
              className="trackmap-svg"
              preserveAspectRatio="xMidYMid meet"
            >
            <title>Track Map — {metadata?.track_name ?? "Unknown"}</title>
            <defs>
              <pattern id={gridPatternId} width="64" height="64" patternUnits="userSpaceOnUse">
                <path d="M 64 0 L 0 0 0 64" fill="none" stroke="#142132" strokeWidth="1" />
              </pattern>
              <clipPath id={clipPathId}>
                <rect
                  x={svgViewport.minX - svgViewport.padding}
                  y={svgViewport.minY - svgViewport.padding}
                  width={svgViewport.width + svgViewport.padding * 2}
                  height={svgViewport.height + svgViewport.padding * 2}
                />
              </clipPath>
            </defs>
            <g className="trackmap-layer" clipPath={`url(#${clipPathId})`}>
              <rect
                x={svgViewport.minX - svgViewport.padding}
                y={svgViewport.minY - svgViewport.padding}
                width={svgViewport.width + svgViewport.padding * 2}
                height={svgViewport.height + svgViewport.padding * 2}
                fill={`url(#${gridPatternId})`}
                opacity={0.35}
              />
              <path
                d={pointPath}
                fill="none"
                stroke="#7dd3fc"
                strokeWidth={8}
                strokeOpacity={0.15}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                d={pointPath}
                fill="none"
                stroke="#38bdf8"
                strokeWidth={3.5}
                strokeOpacity={0.95}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {activeLayers.has("target_zone") && tzPath && (
                <path
                  d={tzPath}
                  fill="none"
                  stroke="#22c55e"
                  strokeWidth={8}
                  strokeOpacity={0.45}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}
              {sectionPolylines.map((sp) => {
              const stat = sectionStats.find((ss) => ss.section.section_id === sp.section.section_id);
              const loc = getLocation(sp.section.start_lap_pct);
              return (
                <g
                  key={`${currentMapId}-${sp.section.section_id}`}
                  style={{ cursor: "pointer" }}
                  onClick={() => handleSectionClick(sp.section)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      handleSectionClick(sp.section);
                    }
                  }}
                >
                  <title>
                    {loc.friendly_section_name} ({sp.section.section_type})
                    {"\n"}{sp.section.length_ft.toFixed(0)} ft
                    {sp.section.wraps_start_finish ? "\nwraps start/finish" : ""}
                    {stat ? `\n${stat.count} events` : "\n0 events"}
                  </title>
                  <path
                    d={sp.d}
                    fill="none"
                    stroke={sectionColor({ count: stat?.count ?? 0, worst: stat?.worst ?? null }, selSecId === sp.section.section_id)}
                    strokeWidth={selSecId === sp.section.section_id ? 6 : 3}
                    strokeOpacity={selSecId === sp.section.section_id ? 0.9 : heatmap === "normal" ? 0.45 : 0.7}
                    strokeLinecap="round" strokeLinejoin="round"
                  />
                  {sp.label && (
                    <text x={sp.label.x} y={sp.label.y} className="trackmap-label" textAnchor="middle" dy="-8">
                      {loc.short_label}
                    </text>
                  )}
                </g>
              );
            })}
            {activeLayers.has("markers") &&
              drawableMarkers.map((marker) => {
                const loc = getLocation(marker.lap_pct);
                const m = marker;
                return (
                  <g key={`${currentMapId}-${marker.marker_id}`}>
                    <title>{loc.display_label} — {m.distance_ft?.toFixed(0)} ft</title>
                    <circle cx={marker.x} cy={marker.y} r={3.5} fill="#38bdf8" />
                    <text x={marker.x + 6} y={marker.y - 6} className="trackmap-label">
                      {loc.short_label}
                    </text>
                  </g>
                );
              })}
            {drawableOverlayEvents
              .map((overlay) => {
                const loc = getLocation(overlay.lap_pct);
                const o = overlay;
                return (
                  <g
                    key={`${currentMapId}-${overlay.marker_id}`}
                    style={{ cursor: "pointer" }}
                    onClick={() => handleOverlayClick(overlay)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleOverlayClick(overlay);
                      }
                    }}
                    aria-label={`${o.label} — ${loc.display_label} — ${o.severity ?? "info"}`}
                  >
                    <title>
                      {o.symbol ?? ""} {o.label} — {loc.display_label}
                      {o.description ? ` — ${o.description}` : ""}
                    </title>
                    {/* Glow ring for selected marker */}
                    {selOvlId === o.marker_id && (
                      <circle
                        cx={overlay.x} cy={overlay.y}
                        r={9}
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth={2}
                        strokeOpacity={0.5}
                        className="trackmap-marker-glow-ring"
                      />
                    )}
                    <circle
                      cx={overlay.x} cy={overlay.y}
                      r={selOvlId === overlay.marker_id ? 7 : 5}
                      fill={overlay.color ?? "#f59e0b"}
                      stroke={selOvlId === overlay.marker_id ? "#fff" : "#0a0d14"}
                      strokeWidth={selOvlId === overlay.marker_id ? 2.5 : 1.5}
                    />
                    <text x={overlay.x + 8} y={overlay.y + 4} className="trackmap-label" fill={overlay.color ?? "#f59e0b"}>
                      {o.symbol ?? "◆"} {loc.short_label}
                    </text>
                  </g>
                );
              })}
              </g>
            </svg>
          ) : (
            <div className="trackmap-empty">
              <Info size={18} />
              <div>
                <strong>Track map unavailable</strong>
                <p>{mapEmptyMessage ?? "Imported map has no drawable centerline points."}</p>
                <p className="muted">
                  {hasBounds
                    ? "The current package includes a map, but the centerline could not be drawn safely."
                    : "The current package does not include usable drawable bounds, so the map canvas stays hidden instead of faking geometry."}
                </p>
              </div>
            </div>
          )}
          {hasDrawableTrack && visiblePlatformOverlayCount === 0 && overlays.length > 0 && (
            <div className="trackmap-empty-map-overlay"><Info size={14} /><span>No visible events for active layers.</span></div>
          )}
        </div>

        {/* ── Section Heat Strip (risk-colored timeline) ── */}
        {hasDrawableTrack && (
          <div className="trackmap-timeline">
          <div className="trackmap-timeline-bar">
            {sectionStats.map((s) => {
              const loc = getLocation(s.section.start_lap_pct);
              // Risk intensity color
              const riskColor =
                s.riskScore >= 5 ? "#ef4444" :
                s.riskScore >= 3 ? "#f97316" :
                s.riskScore >= 1 ? "#f59e0b" :
                "#1e293b";
              return (
                <button
                  key={s.section.section_id}
                  type="button"
                  className="trackmap-timeline-section"
                  style={{
                    left: `${s.section.start_lap_pct}%`,
                    width: `${Math.max(0.5, s.section.end_lap_pct - s.section.start_lap_pct)}%`,
                    background: selSecId === s.section.section_id ? "#38bdf8" : riskColor,
                    opacity: selSecId === s.section.section_id ? 1 : s.riskScore > 0 ? 0.85 : 0.4,
                  }}
                  onClick={() => handleSectionClick(s.section)}
                  title={`${loc.friendly_section_name}: ${s.count} event${s.count !== 1 ? "s" : ""} · risk score ${s.riskScore}`}
                  aria-label={`${loc.friendly_section_name}, ${s.count} events, risk score ${s.riskScore}`}
                >
                  <span className="trackmap-timeline-label">{loc.short_label}</span>
                </button>
              );
            })}
            {orderedVisibleOverlays
              .filter((o) => o.kind === "platform_event" && o.lap_pct != null)
              .map((o) => {
                const loc = getLocation(o.lap_pct);
                return (
                  <button
                    key={o.marker_id}
                    type="button"
                    className={`trackmap-timeline-dot${selOvlId === o.marker_id ? " selected" : ""}`}
                    style={{ left: `${o.lap_pct}%`, background: o.color ?? "#f59e0b" }}
                    onClick={() => handleOverlayClick(o)}
                    title={`${o.symbol ?? ""} ${o.label} — ${loc.display_label}`}
                    aria-label={`${o.label}, ${loc.display_label}`}
                  ></button>
                );
              })}
          </div>
          <div className="trackmap-timeline-ticks">
            {sections.map((s) => {
              const loc = getLocation(s.start_lap_pct);
              return (
                <span key={s.section_id} style={{ left: `${s.start_lap_pct}%`, position: "absolute", fontSize: 9, color: "#64748b" }}>
                  {loc.short_label}
                </span>
              );
            })}
          </div>
          </div>
        )}

        {/* ── Location Jump Chips ── */}
        {hasDrawableTrack && sections.length > 0 && (
          <div className="trackmap-jump-chips">
            <h4>Jump to Area</h4>
            <div className="trackmap-jump-chip-list">
              {sections.map((s) => {
                const loc = getLocation(s.start_lap_pct);
                const stat = sectionStats.find((st) => st.section.section_id === s.section_id);
                const isHot = (stat?.riskScore ?? 0) > 0;
                return (
                  <button
                    key={s.section_id}
                    className={`trackmap-jump-chip${selSecId === s.section_id ? " selected" : ""}${isHot ? " hot" : ""}`}
                    onClick={() => handleSectionClick(s)}
                    title={`${loc.friendly_section_name} · ${stat?.count ?? 0} events`}
                  >
                    {loc.short_label}
                    {isHot && <span className="trackmap-jump-chip-dot" />}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Clusters ── */}
        {clusters.length > 0 && (
          <div className="trackmap-clusters">
            <h4>Clusters</h4>
            <div className="trackmap-cluster-list">
              {clusters.slice(0, 5).map((c) => (
                <button
                  key={c.key}
                  type="button"
                  className="trackmap-cluster-item"
                  onClick={() => handleOverlayClick(c.worst)}
                  aria-label={`${c.count} events in ${c.sectionName}`}
                >
                  <span className="trackmap-cluster-badge">{c.count}</span>
                  <span>{c.count} event{c.count > 1 ? "s" : ""} in {c.sectionName}{c.phase !== "unknown" && c.phase ? ` · ${c.phase}` : ""}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Pinned evidence ── */}
        {pinnedOverlays.length > 0 && (
          <div className="trackmap-pinned">
            <h4>Pinned Evidence {pinnedIds.size > 5 && <span className="muted">+{pinnedIds.size - 5} more</span>}</h4>
            <div className="trackmap-pinned-list">
              {pinnedOverlays.map((o) => {
                const loc = getLocation(o.lap_pct);
                return (
                  <div
                    key={o.marker_id}
                    className="trackmap-pinned-item"
                    style={{ cursor: "pointer" }}
                    onClick={() => handleOverlayClick(o)}
                  >
                    <span className="event-symbol" style={{ color: o.color }}>{o.symbol}</span>
                    <span>{loc.display_label}</span>
                    <span className="muted">· {o.label}</span>
                    <span className="inspector-badge inspector-badge-sm" data-severity={o.severity ?? "info"}>{o.severity}</span>
                    <button className="trackmap-action-btn" onClick={(e) => { e.stopPropagation(); togglePin(o.marker_id); }} title="Unpin">
                      <PinOff size={10} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Area Drilldown ── */}
        {hasDrawableTrack && sectionStats.length > 0 && (
          <div className="trackmap-area-drilldown">
            <h4>Area Drilldown <span className="muted" style={{ fontWeight: 400, fontSize: 10 }}>Based on active filters.</span></h4>
            <div className="trackmap-drilldown-table">
              <div className="trackmap-drilldown-header">
                <span className="trackmap-drilldown-cell">Area</span>
                <span className="trackmap-drilldown-cell">Events</span>
                <span className="trackmap-drilldown-cell">Worst</span>
                <span className="trackmap-drilldown-cell">Top</span>
                <span className="trackmap-drilldown-cell">Front</span>
                <span className="trackmap-drilldown-cell">Rear</span>
                <span className="trackmap-drilldown-cell">Bot</span>
                <span className="trackmap-drilldown-cell">D/S</span>
                <span className="trackmap-drilldown-cell">Aero</span>
                <span className="trackmap-drilldown-cell">Shock</span>
              </div>
              {(problemFocus ? [...sectionStats].sort((a, b) => b.riskScore - a.riskScore) : sectionStats).map((s) => {
                const loc = getLocation(s.section.start_lap_pct);
                const cats = new Map<LayerId, number>();
                const secEvts = overlays.filter((o) => {
                  if (o.lap_pct == null) return false;
                  return s.section.wraps_start_finish
                    ? o.lap_pct >= s.section.start_lap_pct || o.lap_pct <= s.section.end_lap_pct
                    : o.lap_pct >= s.section.start_lap_pct && o.lap_pct <= s.section.end_lap_pct;
                });
                for (const e of secEvts) {
                  const c = classifyOverlayLayer(e);
                  cats.set(c, (cats.get(c) ?? 0) + 1);
                }
                return (
                  <div
                    key={s.section.section_id}
                    className="trackmap-drilldown-row"
                    style={{ cursor: "pointer", background: selSecId === s.section.section_id ? "#1e293b" : undefined }}
                    onClick={() => handleSectionClick(s.section)}
                  >
                    <span className="trackmap-drilldown-cell">{loc.short_label}</span>
                    <span className="trackmap-drilldown-cell">{s.count}</span>
                    <span className="trackmap-drilldown-cell">
                      {s.worst && <span className="inspector-badge inspector-badge-sm" data-severity={s.worst.severity ?? "info"}>{s.worst.severity}</span>}
                    </span>
                    <span className="trackmap-drilldown-cell">{s.topCat ? CATEGORY_LABELS[s.topCat]?.slice(0, 6) ?? s.topCat : ""}</span>
                    <span className="trackmap-drilldown-cell">{cats.get("front_scrape") ?? 0}</span>
                    <span className="trackmap-drilldown-cell">{cats.get("rear_scrape") ?? 0}</span>
                    <span className="trackmap-drilldown-cell">{cats.get("whole_car_bottoming") ?? 0}</span>
                    <span className="trackmap-drilldown-cell">{(cats.get("drag_scrub") ?? 0) + (cats.get("speed_loss") ?? 0)}</span>
                    <span className="trackmap-drilldown-cell">{cats.get("aero") ?? 0}</span>
                    <span className="trackmap-drilldown-cell">{cats.get("shocks") ?? 0}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Section cards ── */}
        {hasDrawableTrack && (
          <div className="trackmap-section-cards">
          <h4>Areas</h4>
          <div className="trackmap-section-cards-grid">
            {(problemFocus ? [...sectionStats].sort((a, b) => b.riskScore - a.riskScore) : sectionStats).slice(0, 12).map((s) => {
              const loc = getLocation(s.section.start_lap_pct);
              return (
                <button
                  key={s.section.section_id}
                  type="button"
                  className={`trackmap-section-card${selSecId === s.section.section_id ? " selected" : ""}`}
                  onClick={() => handleSectionClick(s.section)}
                  aria-label={`${loc.friendly_section_name}, ${s.count} events`}
                >
                  <div className="trackmap-section-card-header">
                    <span className="trackmap-section-card-name">{loc.friendly_section_name}</span>
                    <span className="inspector-badge inspector-badge-sm" data-type={s.section.section_type}>{s.section.section_type}</span>
                  </div>
                  <div className="trackmap-section-card-meta">
                    <span>{s.section.length_ft.toFixed(0)} ft</span>
                  </div>
                  <div className="trackmap-section-card-stats">
                    <span>{s.count} event{s.count !== 1 ? "s" : ""}</span>
                    {s.worst && <span className="inspector-badge inspector-badge-sm" data-severity={s.worst.severity ?? "info"}>{s.worst.severity}</span>}
                    {s.topCat && <span className="muted">{CATEGORY_LABELS[s.topCat] ?? s.topCat}</span>}
                  </div>
                </button>
              );
            })}
          </div>
          </div>
        )}

        {/* ── Fallback events ── */}
        {orderedVisibleOverlays.filter((o) => o.kind === "platform_event" && o.x == null).length > 0 && (
          <div className="map-fallback-events">
            <h4>Events (lap-distance only)</h4>
            {visibleOverlays
              .filter((o) => o.kind === "platform_event" && o.x == null)
              .map((o) => {
                const loc = getLocation(o.lap_pct);
                return (
                  <button key={o.marker_id} type="button" className="map-event-row" onClick={() => handleOverlayClick(o)} aria-label={`${o.label}, ${loc.display_label}`}>
                    <span className="event-symbol" style={{ color: o.color }}>{o.symbol} {o.label}</span>
                    <span className="muted"> — {loc.display_label}</span>
                    {o.distance_ft != null && <span className="muted"> · {o.distance_ft.toFixed(0)} ft</span>}
                  </button>
                );
              })}
          </div>
        )}

        {/* ── Next Best Click ── */}
        {nextBestClick && (
          <div className="trackmap-next-click">
            <span className="muted" style={{ fontSize: 11 }}>Next Best Click: {nextBestClick}</span>
          </div>
        )}

        {/* ── Layers ── */}
        <div className="trackmap-toggles">
          <div className="trackmap-toggles-header">
            <h4><Layers size={13} /> Layers</h4>
          </div>
          <div className="trackmap-toggle-grid">
            {LAYER_DEFS.map((d) => {
              const count = layerCounts.get(d.id);
              const hasData = d.group === "map" || (count != null && count > 0);
              return (
                <label
                  key={d.id}
                  className={`toggle-label${!hasData ? " toggle-disabled" : ""}`}
                  title={!hasData ? "No data for this layer" : d.label}
                >
                  <input
                    type="checkbox"
                    checked={activeLayers.has(d.id)}
                    disabled={!hasData}
                    onChange={() => toggleLayer(d.id)}
                  />
                  {d.label}
                  {count != null ? ` (${count})` : ""}
                </label>
              );
            })}
          </div>
          <div className="trackmap-severity-filter">
            <label className="muted" style={{ fontSize: 11 }}>Severity:</label>
            <select
              className="trackmap-select trackmap-select-sm"
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as SeverityLevel)}
            >
              <option value="all">All</option>
              <option value="critical">Critical</option>
              <option value="high">High+</option>
              <option value="watch">Watch+</option>
              <option value="info">Info</option>
            </select>
          </div>
        </div>

        {/* ── Keyboard shortcuts hint ── */}
        <div className="trackmap-shortcuts-hint" style={{ marginTop: 8, fontSize: 10, color: "#475569" }}>
          Shortcuts: Esc=clear · F=Problem Focus · A=All · S=Scrape · M=Map · ← → = navigate events
        </div>
      </div>

      {/* ── RIGHT: Inspector ── */}
      <aside className="trackmap-inspector" ref={inspectorRef}>
        {inspector.kind === "none" && (
          <div className="inspector-empty">
            <Info size={20} />
            <p>Click a section or event marker to inspect track evidence.</p>
            {!match && availableMaps.length > 0 && (
              <div className="trackmap-manual-select" style={{ marginTop: 12 }}>
                <p className="muted" style={{ marginBottom: 6 }}>Or pick a map manually:</p>
                <select className="trackmap-select" value={preferredMapId ?? ""} onChange={(e) => setPreferredMap(e.target.value)}>
                  <option value="" disabled>Select a track map…</option>
                  {availableMaps.map((m) => (
                    <option key={m.map_id} value={m.map_id}>{m.display_name}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        {/* ── Section inspector ── */}
        {inspector.kind === "section" && (() => {
          const loc = getLocation(inspector.section.start_lap_pct);
          const se = overlays.filter((o) => {
            if (o.lap_pct == null) return false;
            const s = inspector.section;
            return s.wraps_start_finish
              ? o.lap_pct >= s.start_lap_pct || o.lap_pct <= s.end_lap_pct
              : o.lap_pct >= s.start_lap_pct && o.lap_pct <= s.end_lap_pct;
          });
          return (
            <div className="inspector-body">
              <h3>{loc.friendly_section_name}</h3>
              <span className="inspector-badge" data-type={inspector.section.section_type}>{inspector.section.section_type}</span>
              <div className="inspector-fields">
                <div><label>Length</label><span>{inspector.section.length_ft.toFixed(0)} ft</span></div>
                {inspector.section.wraps_start_finish && <div><label>Wraps</label><span>start/finish line</span></div>}
                {DEBUG_LOCATION && (
                  <>
                    <div><label>Lap %</label><span>{inspector.section.start_lap_pct.toFixed(1)}–{inspector.section.end_lap_pct.toFixed(1)}%</span></div>
                    <div><label>Section ID</label><span className="mono">{inspector.section.section_id}</span></div>
                    <div><label>Raw name</label><span>{inspector.section.name}</span></div>
                  </>
                )}
              </div>
              <div className="inspector-evidence" style={{ marginTop: 12 }}>
                <div className="inspector-block">
                  <label>Trust / Basis</label>
                  <div className="inspector-block-content">
                    <span>Basis: {sectionValueBasis === "selected_window" ? "Selected window area anchor" : "Full-lap area anchor"}</span>
                    <span className="muted" style={{ fontSize: 11 }}>Confidence unavailable until you select a specific event or trace sample.</span>
                  </div>
                </div>
              </div>
              <div className="diw-actions" style={{ marginTop: 12 }}>
                <button
                  className="trackmap-action-btn"
                  onClick={() => focusEvidence(buildSectionEvidence(inspector.section), "platform_trace")}
                  title="Open Platform for this area"
                >
                  <Layers size={10} /> Open Platform
                </button>
                <button
                  className="trackmap-action-btn"
                  onClick={() => focusEvidence(buildSectionEvidence(inspector.section), "laps")}
                  title="Review this area in Laps"
                >
                  <Crosshair size={10} /> Review in Laps
                </button>
              </div>
              {se.length === 0 ? (
                <p className="muted" style={{ marginTop: 12 }}>No events in this area.</p>
              ) : (
                <div className="inspector-events">
                  <h4>{se.length} event{se.length !== 1 ? "s" : ""} in {loc.friendly_section_name}</h4>
                  {groupEventsByCategory(se).map((g) => (
                    <div key={g.category} className="inspector-event-group">
                      <div className="inspector-event-group-header">
                        <span className="event-symbol" style={{ color: g.worst?.color }}>{g.worst?.symbol ?? ""}</span>
                        <span>{g.label}</span>
                        <span className="muted">({g.events.length})</span>
                        {g.worst && <span className="inspector-badge inspector-badge-sm" data-severity={g.worst.severity ?? "info"}>{g.worst.severity}</span>}
                      </div>
                      {g.events.slice(0, 5).map((e) => {
                        const eloc = getLocation(e.lap_pct);
                        return (
                          <button key={e.marker_id} type="button" className="inspector-event-row" onClick={() => handleOverlayClick(e)}>
                            <span className="event-symbol" style={{ color: e.color }}>{e.symbol}</span>
                            <span>{e.label}</span>
                            <span className="muted"> — {eloc.display_label}</span>
                          </button>
                        );
                      })}
                      {g.events.length > 5 && <p className="muted" style={{ fontSize: 10, margin: 0 }}>+{g.events.length - 5} more</p>}
                    </div>
                  ))}
                </div>
              )}
              {(() => {
                const stat = sectionStats.find((s) => s.section.section_id === inspector.section.section_id);
                if (!stat) return null;
                // Pinned events in this area
                const pinnedInArea = pinnedOverlays.filter((po) => {
                  if (po.lap_pct == null) return false;
                  const s = inspector.section;
                  return s.wraps_start_finish
                    ? po.lap_pct >= s.start_lap_pct || po.lap_pct <= s.end_lap_pct
                    : po.lap_pct >= s.start_lap_pct && po.lap_pct <= s.end_lap_pct;
                });
                // Problem fingerprint for this area
                const areaFingerprint = fingerprints.find((fp) =>
                  fp.areas.some((a) => a === loc.friendly_section_name),
                );
                return (
                  <div className="inspector-evidence">
                    <h4>Evidence Stack</h4>
                    <div className="inspector-block"><label>Location</label><span>{loc.display_label} · {inspector.section.length_ft.toFixed(0)} ft</span></div>
                    <div className="inspector-block"><label>Type</label><span>{inspector.section.section_type}</span></div>
                    <div className="inspector-block"><label>Severity</label><span className="inspector-badge inspector-badge-sm" data-severity={stat.worst?.severity ?? "info"}>{stat.worst?.severity ?? "none"}</span></div>
                    <div className="inspector-block"><label>Top Category</label><span>{stat.topCat ? CATEGORY_LABELS[stat.topCat] ?? stat.topCat : "—"}</span></div>
                    {stat.count > 0 && (
                      <div className="inspector-block">
                        <label>Events</label>
                        <span>{stat.count} events · worst: {stat.worst?.label ?? "—"} in {stat.worst ? getLocation(stat.worst.lap_pct).display_label : "—"}</span>
                      </div>
                    )}
                    {areaFingerprint && (
                      <div className="inspector-block inspector-block-emphasis">
                        <label>Pattern</label>
                        <span className="muted" style={{ fontSize: 11 }}>{areaFingerprint.pattern}</span>
                      </div>
                    )}
                    {pinnedInArea.length > 0 && (
                      <div className="inspector-block">
                        <label>Pinned in Area</label>
                        <div className="inspector-block-content">
                          {pinnedInArea.map((po) => (
                            <button key={po.marker_id} type="button" className="inspector-event-row" onClick={() => handleOverlayClick(po)}>
                              <span className="event-symbol" style={{ color: po.color }}>{po.symbol}</span>
                              <span>{po.label}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          );
        })()}

        {/* ── Overlay inspector ── */}
        {inspector.kind === "overlay" && (() => {
          const o = inspector.overlay;
          const platformOverlay = o as PlatformBalanceOverlay;
          const loc = getLocation(o.lap_pct);
          const isPinned = pinnedIds.has(o.marker_id);
          return (
            <div className="inspector-body">
              {selectedHidden && <div className="map-warning-banner" style={{ marginBottom: 10 }}><Info size={12} /><span>Selected event hidden — adjust layer filters.</span></div>}
              <h3>{o.symbol} {o.label}</h3>
              <div className="inspector-badges">
                <span className="inspector-badge" data-severity={o.severity ?? "info"}>{o.severity ?? "info"}</span>
                <span className="inspector-badge">{o.kind}</span>
                {o.confidence && <span className="inspector-badge">{o.confidence}</span>}
                {o.event_type && <span className="inspector-badge">{o.event_type}</span>}
                <button
                  className="trackmap-action-btn"
                  aria-pressed={isPinned}
                  aria-label={isPinned ? `Unpin ${o.label}` : `Pin ${o.label}`}
                  onClick={() => togglePin(o.marker_id)}
                  title={isPinned ? "Unpin" : "Pin"}
                  style={{ marginLeft: "auto" }}
                >
                  {isPinned ? <PinOff size={12} /> : <Pin size={12} />}
                </button>
              </div>
              <div className="inspector-evidence">
                <div className="inspector-block">
                  <label>Location</label>
                  <span>
                    {loc.display_label}
                    {o.distance_ft != null ? ` · ${o.distance_ft.toFixed(0)} ft` : ""}
                    {loc.confidence !== "high" && (
                      <span className="muted" style={{ marginLeft: 6, fontSize: 10 }}>Location confidence: {loc.confidence}</span>
                    )}
                  </span>
                </div>
                <div className="inspector-block">
                  <label>Actions</label>
                  <div className="diw-actions">
                    <button
                      className="trackmap-action-btn"
                      onClick={() => focusEvidence(buildOverlayEvidence(o), "platform_trace")}
                      title="Open Platform at this location"
                    >
                      <Layers size={10} /> Open Platform
                    </button>
                    {o.lap_pct != null && (
                      <button
                        className="trackmap-action-btn"
                        onClick={() => focusEvidence(buildOverlayEvidence(o), "laps")}
                        title="Review this area in Laps"
                      >
                        <Crosshair size={10} /> Review in Laps
                      </button>
                    )}
                  </div>
                </div>
                {DEBUG_LOCATION && o.lap_pct != null && (
                  <div className="inspector-block">
                    <label>Debug</label>
                    <span className="mono" style={{ fontSize: 10 }}>
                      lap_pct={o.lap_pct.toFixed(2)}% · section_id={loc.section_id} · local_fraction={loc.local_fraction?.toFixed(3)}
                    </span>
                  </div>
                )}
                <div className="inspector-block">
                  <label>Severity</label>
                  <span className="inspector-badge inspector-badge-sm" data-severity={o.severity ?? "info"}>{o.severity ?? "info"}</span>
                  {o.confidence && <span className="muted" style={{ marginLeft: 6 }}>confidence: {o.confidence}</span>}
                  {o.source_type && <span className="muted" style={{ marginLeft: 6 }}>source: {o.source_type}</span>}
                </div>
                <div className="inspector-block">
                  <label>Trust / Basis</label>
                  <div className="inspector-block-content">
                    <span>Basis: selected map location</span>
                    <span className="muted" style={{ fontSize: 11 }}>
                      {o.confidence ? `Trust tier: ${o.confidence}` : "Trust tier unavailable for this overlay."}
                    </span>
                  </div>
                </div>
                {o.description && (
                  <div className="inspector-block"><label>Description</label><span>{o.description}</span></div>
                )}
                {platformOverlay.front_platform_risk_score != null || platformOverlay.rear_platform_risk_score != null || platformOverlay.whole_car_bottoming_risk != null ? (
                  <div className="inspector-block inspector-block-emphasis">
                    <label>Platform Balance</label>
                    <div className="inspector-block-content">
                      {platformOverlay.platform_balance_label && (
                        <span className={`platform-label platform-${String(platformOverlay.platform_balance_label).toLowerCase().replace(/\s+/g, "-")}`}>
                          {platformOverlay.platform_balance_label}
                        </span>
                      )}
                      <div className="inspector-block-grid">
                        {platformOverlay.front_platform_risk_score != null && <span>Front: {platformOverlay.front_platform_risk_score}</span>}
                        {platformOverlay.rear_platform_risk_score != null && <span>Rear: {platformOverlay.rear_platform_risk_score}</span>}
                        {platformOverlay.whole_car_bottoming_risk != null && <span className="text-critical">Bottoming: {platformOverlay.whole_car_bottoming_risk}</span>}
                        {platformOverlay.rear_scrape_side_label && <span>Side: {platformOverlay.rear_scrape_side_label}</span>}
                      </div>
                      {platformOverlay.platform_balance_explanation && (
                        <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>{platformOverlay.platform_balance_explanation}</p>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="inspector-block" style={{ opacity: 0.5 }}><label>Platform Balance</label><span className="muted">Unavailable</span></div>
                )}
                {o.related_channels && o.related_channels.length > 0 && (
                  <div className="inspector-block"><label>Channels</label><div className="channel-chips">{o.related_channels.map((c) => <span key={c} className="channel-chip">{c}</span>)}</div></div>
                )}
                {o.source_id && <div className="inspector-block"><label>Source ID</label><span className="mono">{o.source_id}</span></div>}
              </div>
              {buildEventSentence(o, sections) && (
                <div className="inspector-block" style={{ marginTop: 8 }}>
                  <label>Summary</label>
                  <span className="muted" style={{ fontSize: 11 }}>{buildEventSentence(o, sections)}</span>
                </div>
              )}
            </div>
          );
        })()}
      </aside>
    </section>
  );
}
