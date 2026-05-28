import {
  Crosshair, Info, Layers, Map as MapIcon, Pin, PinOff, Search, X, Copy,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TrackMapIndexEntry, TrackMapOverlayMarker, TrackMapPackage, TrackMapSection } from "../types/trackMap";
import { fetchRunTrackMapPackage, fetchTrackMaps } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
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
  const { selectSample, selectEvent, selectZone } = useTelemetrySelection();

  useEffect(() => { fetchTrackMaps().then(setAvailableMaps).catch(()=>{}); }, []);
  useEffect(() => {
    if (!runId) { setPkg(null); return; }
    setLoading(true); setError(null);
    fetchRunTrackMapPackage(runId, { lap: lap??undefined, target_zone_start_pct: targetZoneStartPct, target_zone_end_pct: targetZoneEndPct, preferred_map_id: preferredMapId??undefined })
      .then(setPkg).catch((e)=>setError(e instanceof Error?e.message:"Failed to load track map")).finally(()=>setLoading(false));
  }, [runId, lap, targetZoneStartPct, targetZoneEndPct, preferredMapId]);

  const points = pkg?.map?.points ?? [];
  const bounds = pkg?.map?.bounds;
  const overlays = pkg?.overlays ?? [];
  const markers = pkg?.map?.markers ?? [];
  const sections = pkg?.map?.sections ?? [];
  const metadata = pkg?.map?.metadata;
  const match = pkg?.match;

  const getLocation = useCallback(
    (lapPct: number | null | undefined) => calculateTrackLocation(lapPct, sections),
    [sections],
  );

  // ── Active preset ────────────────────────────────────────────
  const activePreset = useMemo(
    () => detectActivePreset(activeLayers, severityFilter),
    [activeLayers, severityFilter],
  );

  // ── Handlers ─────────────────────────────────────────────────
  const handleOverlayClick = useCallback(
    (o: TrackMapOverlayMarker) => {
      setInspector({ kind: "overlay", overlay: o });
      if (o.lap_pct != null) selectSample(0, undefined, o.lap_pct, "track_map");
      if (o.kind === "platform_event" && o.source_id) selectEvent(o.source_id, "track_map");
      inspectorRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    },
    [selectSample, selectEvent],
  );

  const handleSectionClick = useCallback(
    (s: TrackMapSection) => {
      setInspector({ kind: "section", section: s });
      setSelectedArea(s.section_id);
      selectZone(s.section_id);
    },
    [selectZone],
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
      .sort((a, b) => a.count - b.count);
  }, [visibleOverlays, getLocation]);

  // ── Copy summary ─────────────────────────────────────────────
  const copySummary = useCallback(() => {
    const selOvl = inspector.kind === "overlay" ? inspector.overlay : null;
    const selLoc = selOvl ? getLocation(selOvl.lap_pct) : null;
    const lines = [
      "RaceLab Track Map Summary",
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
  const viewBox = useMemo(() => {
    if (!bounds) return "0 0 800 600";
    const p = 50;
    return `${bounds.min_x_m - p} ${bounds.min_y_m - p} ${bounds.width_m + p * 2} ${bounds.height_m + p * 2}`;
  }, [bounds]);

  const pointPath = useMemo(
    () =>
      points.length
        ? points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x ?? p.x_m} ${p.y ?? p.y_m}`).join(" ")
        : "",
    [points],
  );

  const tzPath = useMemo(() => {
    const tz = overlays.find((o) => o.kind === "target_zone");
    const pts = tz?.points;
    if (!pts || pts.length < 2) return null;
    return pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  }, [overlays]);

  const sectionPolylines = useMemo(() => {
    if (!activeLayers.has("sections") || !sections.length) return [];
    return sections
      .map((s) => {
        const sp = points.filter((p) => {
          if (p.lap_pct == null) return false;
          return s.wraps_start_finish
            ? p.lap_pct >= s.start_lap_pct || p.lap_pct <= s.end_lap_pct
            : p.lap_pct >= s.start_lap_pct && p.lap_pct <= s.end_lap_pct;
        });
        const d = sp.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x ?? p.x_m} ${p.y ?? p.y_m}`).join(" ");
        return { section: s, d, count: sp.length };
      })
      .filter((sp) => sp.count > 1);
  }, [points, sections, activeLayers]);

  // ── Empty states ─────────────────────────────────────────────
  if (!runId)
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="muted">No run loaded. Import an .ibt file to view telemetry events on a track map.</p>
      </section>
    );
  if (loading)
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="muted">Loading track map…</p>
      </section>
    );
  if (error)
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="error-text">{error}</p>
      </section>
    );
  if (!pkg?.map) {
    const filtered = availableMaps.filter(
      (m) =>
        !mapSearch ||
        m.display_name.toLowerCase().includes(mapSearch.toLowerCase()) ||
        m.track_key.toLowerCase().includes(mapSearch.toLowerCase()) ||
        m.source_filename.toLowerCase().includes(mapSearch.toLowerCase()),
    );
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <div className="notebook-empty">
          <p>No matching track map found. Import a local .mt2 map or choose one manually.</p>
          <p className="muted">Choose a track map manually:</p>
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
                onChange={(e) => setPreferredMap(e.target.value)}
                defaultValue=""
              >
                <option value="" disabled>Select a track map…</option>
                {filtered.map((m) => (
                  <option key={m.map_id} value={m.map_id}>
                    {m.display_name} — {m.distance_ft.toFixed(0)} ft
                    {m.source_type === "mt2" ? " · .mt2" : ""}
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

  return (
    <section className="trackmap-cockpit">
      <div className="trackmap-left">
        {/* ── Header ── */}
        <header className="trackmap-header">
          <h2><MapIcon size={18} /> {metadata?.track_name ?? "Track Map"}</h2>
          <div className="trackmap-header-stats">
            <span className="source-badge source-mt2">.mt2</span>
            {metadata && <span>{metadata.distance_miles.toFixed(2)} mi · {metadata.distance_ft.toFixed(0)} ft</span>}
            <span>{points.length.toLocaleString()} pts</span>
            <span>{markers.length} mk · {sections.length} sec</span>
          </div>
          <div className="trackmap-header-run">
            {trackName && <span className="muted">{trackName}</span>}
            {carName && <span className="muted">— {carName}</span>}
            {setupName && <span className="muted">· {setupName}</span>}
          </div>
          {match && (
            <div className="trackmap-header-match">
              <span className="map-confidence-badge" data-confidence={match.match_confidence ?? "medium"}>
                {match.match_confidence ?? "medium"}
              </span>
              <span className="muted">{match.source_filename ?? match.display_name}</span>
              {lap != null && <span className="muted">· Lap {lap}</span>}
              {preferredMapId && (
                <button className="trackmap-action-btn" onClick={clearPreferredMap} title="Clear manual map">
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
                {" "}Worst: <span className="event-symbol" style={{ color: (summary.worstEvent as any).color }}>
                  {(summary.worstEvent as any).symbol} {summary.worstEvent.label}
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

        {metadata && !metadata.origin.gps_supported && (
          <div className="map-warning-banner"><Info size={14} /><span>Centerline-only .mt2 map — no boundaries, banking, GPS, or track width found.</span></div>
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
          <button className="trackmap-action-btn" onClick={copySummary} title="Copy Summary">
            <Copy size={12} /> Copy
          </button>
        </div>

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
        <div className="track-map-svg-container">
          <svg viewBox={viewBox} className="track-map-svg">
            <title>Track Map — {metadata?.track_name ?? "Unknown"}</title>
            <path d={pointPath} fill="none" stroke="#4ade80" strokeWidth={4} strokeOpacity={0.7} />
            {activeLayers.has("target_zone") && tzPath && (
              <path d={tzPath} fill="none" stroke="#22c55e" strokeWidth={8} strokeOpacity={0.4} />
            )}
            {sectionPolylines.map((sp) => {
              const stat = sectionStats.find((ss) => ss.section.section_id === sp.section.section_id);
              const loc = getLocation(sp.section.start_lap_pct);
              return (
                <g key={sp.section.section_id} style={{ cursor: "pointer" }} onClick={() => handleSectionClick(sp.section)}>
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
                </g>
              );
            })}
            {activeLayers.has("markers") &&
              markers.map((m) => {
                const loc = getLocation(m.lap_pct);
                return (
                  <g key={m.marker_id}>
                    <title>{loc.display_label} — {m.distance_ft?.toFixed(0)} ft</title>
                    <circle cx={m.x} cy={m.y} r={4} fill="#38bdf8" />
                    <text x={m.x + 6} y={m.y - 6} fill="#8d9aaa" fontSize={9} fontFamily="Inter, sans-serif">
                      {loc.short_label}
                    </text>
                  </g>
                );
              })}
            {visibleOverlays
              .filter((o) => o.kind === "platform_event" && o.x != null && o.y != null)
              .map((o) => {
                const loc = getLocation(o.lap_pct);
                return (
                  <g key={o.marker_id} style={{ cursor: "pointer" }} onClick={() => handleOverlayClick(o)} aria-label={`${o.label} — ${loc.display_label} — ${o.severity ?? "info"}`}>
                    <title>
                      {o.symbol ?? ""} {o.label} — {loc.display_label}
                      {o.description ? ` — ${o.description}` : ""}
                    </title>
                    {/* Glow ring for selected marker */}
                    {selOvlId === o.marker_id && (
                      <circle
                        cx={o.x!} cy={o.y!}
                        r={9}
                        fill="none"
                        stroke="#38bdf8"
                        strokeWidth={2}
                        strokeOpacity={0.5}
                        className="trackmap-marker-glow-ring"
                      />
                    )}
                    <circle
                      cx={o.x!} cy={o.y!}
                      r={selOvlId === o.marker_id ? 7 : 5}
                      fill={o.color ?? "#f59e0b"}
                      stroke={selOvlId === o.marker_id ? "#fff" : "#0a0d14"}
                      strokeWidth={selOvlId === o.marker_id ? 2.5 : 1.5}
                    />
                    <text x={(o.x ?? 0) + 8} y={(o.y ?? 0) + 4} fill={o.color ?? "#f59e0b"} fontSize={9} fontFamily="Inter, sans-serif">
                      {o.symbol ?? "◆"} {loc.short_label}
                    </text>
                  </g>
                );
              })}
          </svg>
          {visibleOverlays.filter((o) => o.kind === "platform_event").length === 0 && overlays.length > 0 && (
            <div className="trackmap-empty-map-overlay"><Info size={14} /><span>No visible events for active layers.</span></div>
          )}
        </div>

        {/* ── Section Heat Strip (risk-colored timeline) ── */}
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
                <div
                  key={s.section.section_id}
                  className="trackmap-timeline-section"
                  style={{
                    left: `${s.section.start_lap_pct}%`,
                    width: `${Math.max(0.5, s.section.end_lap_pct - s.section.start_lap_pct)}%`,
                    background: selSecId === s.section.section_id ? "#38bdf8" : riskColor,
                    opacity: selSecId === s.section.section_id ? 1 : s.riskScore > 0 ? 0.85 : 0.4,
                  }}
                  onClick={() => handleSectionClick(s.section)}
                  title={`${loc.friendly_section_name}: ${s.count} event${s.count !== 1 ? "s" : ""} · risk score ${s.riskScore}`}
                >
                  <span className="trackmap-timeline-label">{loc.short_label}</span>
                </div>
              );
            })}
            {visibleOverlays
              .filter((o) => o.kind === "platform_event" && o.lap_pct != null)
              .map((o) => {
                const loc = getLocation(o.lap_pct);
                return (
                  <div
                    key={o.marker_id}
                    className={`trackmap-timeline-dot${selOvlId === o.marker_id ? " selected" : ""}`}
                    style={{ left: `${o.lap_pct}%`, background: o.color ?? "#f59e0b" }}
                    onClick={() => handleOverlayClick(o)}
                    title={`${o.symbol ?? ""} ${o.label} — ${loc.display_label}`}
                  />
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

        {/* ── Location Jump Chips ── */}
        {sections.length > 0 && (
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
                <div
                  key={c.key}
                  className="trackmap-cluster-item"
                  style={{ cursor: "pointer" }}
                  onClick={() => handleOverlayClick(c.worst)}
                >
                  <span className="trackmap-cluster-badge">{c.count}</span>
                  <span>{c.count} event{c.count > 1 ? "s" : ""} in {c.sectionName}{c.phase !== "unknown" && c.phase ? ` · ${c.phase}` : ""}</span>
                </div>
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
        {sectionStats.length > 0 && (
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
        <div className="trackmap-section-cards">
          <h4>Areas</h4>
          <div className="trackmap-section-cards-grid">
            {(problemFocus ? [...sectionStats].sort((a, b) => b.riskScore - a.riskScore) : sectionStats).slice(0, 12).map((s) => {
              const loc = getLocation(s.section.start_lap_pct);
              return (
                <div
                  key={s.section.section_id}
                  className={`trackmap-section-card${selSecId === s.section.section_id ? " selected" : ""}`}
                  onClick={() => handleSectionClick(s.section)}
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
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Fallback events ── */}
        {visibleOverlays.filter((o) => o.kind === "platform_event" && o.x == null).length > 0 && (
          <div className="map-fallback-events">
            <h4>Events (lap-distance only)</h4>
            {visibleOverlays
              .filter((o) => o.kind === "platform_event" && o.x == null)
              .map((o) => {
                const loc = getLocation(o.lap_pct);
                return (
                  <div key={o.marker_id} className="map-event-row" style={{ cursor: "pointer" }} onClick={() => handleOverlayClick(o)}>
                    <span className="event-symbol" style={{ color: o.color }}>{o.symbol} {o.label}</span>
                    <span className="muted"> — {loc.display_label}</span>
                    {o.distance_ft != null && <span className="muted"> · {o.distance_ft.toFixed(0)} ft</span>}
                  </div>
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
                <select className="trackmap-select" onChange={(e) => setPreferredMap(e.target.value)} defaultValue="">
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
                          <div key={e.marker_id} className="inspector-event-row" onClick={() => handleOverlayClick(e)}>
                            <span className="event-symbol" style={{ color: e.color }}>{e.symbol}</span>
                            <span>{e.label}</span>
                            <span className="muted"> — {eloc.display_label}</span>
                          </div>
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
                            <div key={po.marker_id} className="inspector-event-row" onClick={() => handleOverlayClick(po)}>
                              <span className="event-symbol" style={{ color: po.color }}>{po.symbol}</span>
                              <span>{po.label}</span>
                            </div>
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
                {o.description && (
                  <div className="inspector-block"><label>Description</label><span>{o.description}</span></div>
                )}
                {(o as any).front_platform_risk_score != null || (o as any).rear_platform_risk_score != null || (o as any).whole_car_bottoming_risk != null ? (
                  <div className="inspector-block inspector-block-emphasis">
                    <label>Platform Balance</label>
                    <div className="inspector-block-content">
                      {(o as any).platform_balance_label && (
                        <span className={`platform-label platform-${String((o as any).platform_balance_label).toLowerCase().replace(/\s+/g, "-")}`}>
                          {(o as any).platform_balance_label}
                        </span>
                      )}
                      <div className="inspector-block-grid">
                        {(o as any).front_platform_risk_score != null && <span>Front: {(o as any).front_platform_risk_score}</span>}
                        {(o as any).rear_platform_risk_score != null && <span>Rear: {(o as any).rear_platform_risk_score}</span>}
                        {(o as any).whole_car_bottoming_risk != null && <span className="text-critical">Bottoming: {(o as any).whole_car_bottoming_risk}</span>}
                        {(o as any).rear_scrape_side_label && <span>Side: {(o as any).rear_scrape_side_label}</span>}
                      </div>
                      {(o as any).platform_balance_explanation && (
                        <p className="muted" style={{ fontSize: 11, marginTop: 4 }}>{(o as any).platform_balance_explanation}</p>
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
