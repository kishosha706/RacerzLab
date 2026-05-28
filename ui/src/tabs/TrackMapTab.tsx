import { Info, Layers, Map as MapIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { TrackMapIndexEntry, TrackMapOverlayMarker, TrackMapPackage, TrackMapSection } from "../types/trackMap";
import { fetchRunTrackMapPackage, fetchTrackMaps } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";

interface Props {
  runId: string | null;
  lap?: number | null;
  trackName?: string | null;
  carName?: string | null;
  setupName?: string | null;
  targetZoneStartPct?: number;
  targetZoneEndPct?: number;
}

// ── layer categories ─────────────────────────────────────────
type LayerId =
  | "sections" | "target_zone" | "markers"
  | "all_events" | "front_scrape" | "rear_scrape" | "whole_car_bottoming"
  | "drag_scrub" | "speed_loss" | "aero" | "shocks"
  | "delta" | "insights" | "tires" | "notebook";

interface LayerDef {
  id: LayerId;
  label: string;
  group: "map" | "events" | "other";
}

const LAYER_DEFS: LayerDef[] = [
  { id: "sections", label: "Sections", group: "map" },
  { id: "target_zone", label: "Target Zone", group: "map" },
  { id: "markers", label: "Markers", group: "map" },
  { id: "all_events", label: "All Events", group: "events" },
  { id: "front_scrape", label: "Front Scrape", group: "events" },
  { id: "rear_scrape", label: "Rear Scrape", group: "events" },
  { id: "whole_car_bottoming", label: "Bottoming", group: "events" },
  { id: "drag_scrub", label: "Drag/Scrub", group: "events" },
  { id: "speed_loss", label: "Speed Loss", group: "events" },
  { id: "aero", label: "Aero / DP", group: "events" },
  { id: "shocks", label: "Shocks", group: "events" },
  { id: "delta", label: "Delta", group: "other" },
  { id: "insights", label: "Insights", group: "other" },
  { id: "tires", label: "Tires", group: "other" },
  { id: "notebook", label: "Notebook", group: "other" },
];

const EVENT_SYMBOLS: Record<string, { sym: string; label: string }> = {
  MIN_SPLITTER: { sym: "\u2b07", label: "Min Splitter" },
  WORST_SPEED_LOSS: { sym: "\u25bc", label: "Worst Speed Loss" },
  WORST_DRAG_SCRUB: { sym: "\u26a0", label: "Worst Drag/Scrub" },
  HIGHEST_RAKE: { sym: "\u25b2", label: "Highest Rake" },
  HIGHEST_PLATFORM_COMPRESSION: { sym: "\u25cf", label: "Platform Compression" },
  HIGHEST_SHOCK_ACTIVITY: { sym: "S", label: "Shock Activity" },
  MAX_DYNAMIC_PRESSURE: { sym: "\u25cb", label: "Max Dynamic Pressure" },
  REAR_SCRAPE: { sym: "R!", label: "Rear Scrape" },
  REAR_PLATFORM_LOW: { sym: "R", label: "Rear Platform Low" },
  REAR_MIN_HEIGHT: { sym: "Rmin", label: "Min Rear Ride Height" },
  REAR_CONTACT_RISK: { sym: "R?", label: "Rear Contact Risk" },
  WHOLE_CAR_BOTTOMING: { sym: "\u21e3", label: "Whole-Car Bottoming" },
  FRONT_SCRAPE: { sym: "F!", label: "Front Scrape" },
  FRONT_PLATFORM_LOW: { sym: "F", label: "Front Platform Low" },
};

type SeverityLevel = "all" | "critical" | "high" | "watch" | "info";
const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, watch: 2, info: 3 };

function classifyOverlayLayer(o: TrackMapOverlayMarker): LayerId {
  if (o.kind === "delta_annotation") return "delta";
  if (o.kind === "insight") return "insights";
  if (o.kind === "tire_shock") return "tires";
  if (o.kind === "notebook_finding") return "notebook";
  const label = (o.label || "").toLowerCase();
  if (/whole.?car.?bottoming|bottoming/.test(label)) return "whole_car_bottoming";
  if (/front.?scrape|front.?platform.?low|splitter/.test(label)) return "front_scrape";
  if (/rear.?scrape|rear.?platform.?low|rear.?ride.?height|rear.?contact|min.?rear/.test(label)) return "rear_scrape";
  if (/drag|scrub/.test(label)) return "drag_scrub";
  if (/speed.?loss/.test(label)) return "speed_loss";
  if (/dynamic.?pressure|aero/.test(label)) return "aero";
  if (/shock|damper/.test(label)) return "shocks";
  return "all_events";
}

function severityPasses(severity: string | undefined, filter: SeverityLevel): boolean {
  if (filter === "all" || !severity) return true;
  const rank = SEVERITY_RANK[severity] ?? 99;
  const threshold = SEVERITY_RANK[filter] ?? 0;
  return rank <= threshold;
}

type CategoryGroup = { category: LayerId; label: string; events: TrackMapOverlayMarker[]; worst: TrackMapOverlayMarker | null };

function groupEventsByCategory(events: TrackMapOverlayMarker[]): CategoryGroup[] {
  const map = new Map<LayerId, TrackMapOverlayMarker[]>();
  for (const e of events) {
    const cat = classifyOverlayLayer(e);
    if (!map.has(cat)) map.set(cat, []);
    map.get(cat)!.push(e);
  }
  const defLabels: Record<string, string> = {
    front_scrape: "Front Platform", rear_scrape: "Rear Platform",
    whole_car_bottoming: "Whole-Car", drag_scrub: "Drag/Scrub",
    aero: "Aero", shocks: "Shocks", speed_loss: "Speed Loss",
    all_events: "Other Events", delta: "Delta", insights: "Insights",
    tires: "Tires", notebook: "Notebook",
  };
  return [...map.entries()].map(([cat, evts]) => ({
    category: cat, label: defLabels[cat] ?? cat,
    events: evts,
    worst: evts.reduce((a, b) => ((SEVERITY_RANK[a.severity ?? "info"] ?? 99) <= (SEVERITY_RANK[b.severity ?? "info"] ?? 99) ? a : b), evts[0]),
  }));
}

type InspectorTarget =
  | { kind: "overlay"; overlay: TrackMapOverlayMarker }
  | { kind: "section"; section: TrackMapSection }
  | { kind: "none" };

export function TrackMapTab({ runId, lap, trackName, carName, setupName, targetZoneStartPct, targetZoneEndPct }: Props) {
  const [pkg, setPkg] = useState<TrackMapPackage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // layer state — set of active LayerIds
  const [activeLayers, setActiveLayers] = useState<Set<LayerId>>(
    () => new Set<LayerId>(["sections", "target_zone", "markers", "all_events"])
  );
  const [severityFilter, setSeverityFilter] = useState<SeverityLevel>("all");
  const [inspector, setInspector] = useState<InspectorTarget>({ kind: "none" });

  // manual map association
  const [availableMaps, setAvailableMaps] = useState<TrackMapIndexEntry[]>([]);
  const [preferredMapId, setPreferredMapId] = useState<string | null>(null);

  const { selectSample, selectEvent, selectZone } = useTelemetrySelection();

  // load available maps on mount for manual association
  useEffect(() => {
    fetchTrackMaps().then(setAvailableMaps).catch(() => {});
  }, []);

  // load/reload package
  useEffect(() => {
    if (!runId) { setPkg(null); return; }
    setLoading(true);
    setError(null);
    fetchRunTrackMapPackage(runId, {
      lap: lap ?? undefined,
      target_zone_start_pct: targetZoneStartPct,
      target_zone_end_pct: targetZoneEndPct,
      preferred_map_id: preferredMapId ?? undefined,
    })
      .then(setPkg)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load track map"))
      .finally(() => setLoading(false));
  }, [runId, lap, targetZoneStartPct, targetZoneEndPct, preferredMapId]);

  const points = pkg?.map?.points ?? [];
  const bounds = pkg?.map?.bounds;
  const overlays = pkg?.overlays ?? [];
  const markers = pkg?.map?.markers ?? [];
  const sections = pkg?.map?.sections ?? [];
  const metadata = pkg?.map?.metadata;
  const match = pkg?.match;

  const handleOverlayClick = useCallback((overlay: TrackMapOverlayMarker) => {
    setInspector({ kind: "overlay", overlay });
    if (overlay.lap_pct != null) selectSample(0, undefined, overlay.lap_pct, "track_map");
    if (overlay.kind === "platform_event" && overlay.source_id) selectEvent(overlay.source_id, "track_map");
  }, [selectSample, selectEvent]);

  const handleSectionClick = useCallback((section: TrackMapSection) => {
    setInspector({ kind: "section", section });
    selectZone(section.section_id);
  }, [selectZone]);

  // ── layer counts ──
  const layerCounts = useMemo(() => {
    const counts = new Map<LayerId, number>();
    for (const o of overlays) {
      const cat = classifyOverlayLayer(o);
      counts.set(cat, (counts.get(cat) ?? 0) + 1);
      counts.set("all_events", (counts.get("all_events") ?? 0) + 1);
    }
    return counts;
  }, [overlays]);

  // ── visible overlays ──
  const visibleOverlays = useMemo(() => {
    return overlays.filter((o) => {
      const cat = classifyOverlayLayer(o);
      if (cat === "all_events" && !activeLayers.has("all_events")) {
        // covered by any active specific event layer?
        const eventLayers = LAYER_DEFS.filter((d) => d.group === "events" && d.id !== "all_events").map((d) => d.id);
        if (!eventLayers.some((id) => activeLayers.has(id))) return false;
      } else if (!activeLayers.has(cat) && cat !== "all_events") {
        return false;
      }
      return severityPasses(o.severity, severityFilter);
    });
  }, [overlays, activeLayers, severityFilter]);

  // check if selected item is still visible
  const selectedHidden = useMemo(() => {
    if (inspector.kind !== "overlay") return false;
    return !visibleOverlays.some((o) => o.marker_id === inspector.overlay.marker_id);
  }, [visibleOverlays, inspector]);

  // ── layer toggle helpers ──
  const toggleLayer = useCallback((id: LayerId) => {
    setActiveLayers((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const quickAction = useCallback((action: "show_all" | "hide_events" | "platform_only" | "scrape_only") => {
    setActiveLayers(() => {
      const set = new Set<LayerId>(["sections", "target_zone", "markers"]);
      if (action === "show_all") {
        for (const d of LAYER_DEFS) set.add(d.id);
      } else if (action === "hide_events") {
        // keep map layers only
      } else if (action === "platform_only") {
        set.add("all_events");
      } else if (action === "scrape_only") {
        for (const id of ["front_scrape", "rear_scrape", "whole_car_bottoming"] as LayerId[]) set.add(id);
      }
      return set;
    });
  }, []);

  const setPreferredMap = useCallback((mapId: string) => {
    setPreferredMapId(mapId);
    setInspector({ kind: "none" });
  }, []);

  // ── SVG helpers ──
  const viewBox = useMemo(() => {
    if (!bounds) return "0 0 800 600";
    const pad = 50;
    return `${bounds.min_x_m - pad} ${bounds.min_y_m - pad} ${bounds.width_m + pad * 2} ${bounds.height_m + pad * 2}`;
  }, [bounds]);

  const pointPath = useMemo(() => {
    if (points.length === 0) return "";
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x ?? p.x_m} ${p.y ?? p.y_m}`).join(" ");
  }, [points]);

  const targetZonePath = useMemo(() => {
    const tz = overlays.find((o) => o.kind === "target_zone");
    const pts = tz?.points;
    if (!pts || pts.length < 2) return null;
    return pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  }, [overlays]);

  const sectionPolylines = useMemo(() => {
    if (!activeLayers.has("sections") || sections.length === 0) return [];
    return sections.map((s) => {
      const secPts = points.filter((p) => {
        if (p.lap_pct == null) return false;
        if (s.wraps_start_finish) return p.lap_pct >= s.start_lap_pct || p.lap_pct <= s.end_lap_pct;
        return p.lap_pct >= s.start_lap_pct && p.lap_pct <= s.end_lap_pct;
      });
      const d = secPts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x ?? p.x_m} ${p.y ?? p.y_m}`).join(" ");
      return { section: s, d, count: secPts.length };
    }).filter((sp) => sp.count > 1);
  }, [points, sections, activeLayers]);

  // ── empty states ──
  if (!runId) {
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="muted">Import a run and .mt2 track map to view spatial data.</p>
      </section>
    );
  }
  if (loading) {
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="muted">Loading track map…</p>
      </section>
    );
  }
  if (error) {
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <p className="error-text">{error}</p>
      </section>
    );
  }

  // ── no map matched ──
  if (!pkg?.map) {
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <div className="notebook-empty">
          <p>No track map matched for this run.</p>
          <p className="muted">Choose a track map manually:</p>
          {availableMaps.length > 0 ? (
            <div className="trackmap-manual-select">
              <select className="trackmap-select" onChange={(e) => setPreferredMap(e.target.value)} defaultValue="">
                <option value="" disabled>Select a track map…</option>
                {availableMaps.map((m) => (
                  <option key={m.map_id} value={m.map_id}>{m.display_name} — {m.distance_ft.toFixed(0)} ft</option>
                ))}
              </select>
            </div>
          ) : (
            <p className="muted">Loading map index…</p>
          )}
        </div>
      </section>
    );
  }

  // ── render ──
  const selectedSectionId = inspector.kind === "section" ? inspector.section.section_id : null;
  const selectedOverlayId = inspector.kind === "overlay" ? inspector.overlay.marker_id : null;

  return (
    <section className="trackmap-cockpit">
      {/* ── LEFT PANEL: Map ── */}
      <div className="trackmap-left">
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
            </div>
          )}
        </header>

        {metadata && !metadata.origin.gps_supported && (
          <div className="map-warning-banner">
            <Info size={14} />
            <span>Centerline-only .mt2 map — no boundaries, banking, GPS, or track width found.</span>
          </div>
        )}

        {/* SVG Map */}
        <div className="track-map-svg-container">
          <svg viewBox={viewBox} className="track-map-svg">
            <title>Track Map — {metadata?.track_name ?? "Unknown"}</title>
            <path d={pointPath} fill="none" stroke="#4ade80" strokeWidth={4} strokeOpacity={0.7} />
            {activeLayers.has("target_zone") && targetZonePath && (
              <path d={targetZonePath} fill="none" stroke="#22c55e" strokeWidth={8} strokeOpacity={0.4} />
            )}
            {sectionPolylines.map((sp) => (
              <g key={sp.section.section_id} style={{ cursor: "pointer" }} onClick={() => handleSectionClick(sp.section)}>
                <title>{sp.section.name} ({sp.section.section_type}){"\n"}{sp.section.start_lap_pct.toFixed(1)}%–{sp.section.end_lap_pct.toFixed(1)}% · {sp.section.length_ft.toFixed(0)} ft{sp.section.wraps_start_finish ? "\nwraps start/finish" : ""}</title>
                <path d={sp.d} fill="none"
                  stroke={selectedSectionId === sp.section.section_id ? "#38bdf8" : "#1e40af"}
                  strokeWidth={selectedSectionId === sp.section.section_id ? 6 : 3}
                  strokeOpacity={selectedSectionId === sp.section.section_id ? 0.9 : 0.45}
                  strokeLinecap="round" strokeLinejoin="round" />
              </g>
            ))}
            {activeLayers.has("markers") && markers.map((m) => (
              <g key={m.marker_id}>
                <title>{m.name} — {m.distance_ft?.toFixed(0)} ft</title>
                <circle cx={m.x} cy={m.y} r={4} fill="#38bdf8" />
                <text x={m.x + 6} y={m.y - 6} fill="#8d9aaa" fontSize={9} fontFamily="Inter, sans-serif">{m.name}</text>
              </g>
            ))}
            {visibleOverlays
              .filter((o) => o.kind === "platform_event" && o.x != null && o.y != null)
              .map((o) => (
                <g key={o.marker_id} style={{ cursor: "pointer" }} onClick={() => handleOverlayClick(o)}>
                  <title>{o.label}{o.description ? ` — ${o.description}` : ""} @ {o.lap_pct?.toFixed(1)}%</title>
                  <circle cx={o.x ?? undefined} cy={o.y ?? undefined}
                    r={selectedOverlayId === o.marker_id ? 7 : 5}
                    fill={o.color ?? "#f59e0b"}
                    stroke={selectedOverlayId === o.marker_id ? "#fff" : "#0a0d14"}
                    strokeWidth={selectedOverlayId === o.marker_id ? 2.5 : 1.5} />
                  <text x={(o.x ?? 0) + 8} y={(o.y ?? 0) + 4} fill={o.color ?? "#f59e0b"} fontSize={9} fontFamily="Inter, sans-serif">{o.symbol ?? "\u25c6"} {o.label}</text>
                </g>
              ))}
          </svg>
          {visibleOverlays.filter((o) => o.kind === "platform_event").length === 0 && overlays.length > 0 && (
            <div className="trackmap-empty-map-overlay">
              <Info size={14} />
              <span>No visible events for active layers.</span>
            </div>
          )}
        </div>

        {/* Fallback events */}
        {visibleOverlays.filter((o) => o.kind === "platform_event" && o.x == null).length > 0 && (
          <div className="map-fallback-events">
            <h4>Events (lap-distance only)</h4>
            {visibleOverlays.filter((o) => o.kind === "platform_event" && o.x == null).map((o) => (
              <div key={o.marker_id} className="map-event-row" style={{ cursor: "pointer" }} onClick={() => handleOverlayClick(o)}>
                <span className="event-symbol" style={{ color: o.color }}>{o.symbol} {o.label}</span>
                <span className="event-pct">@{o.lap_pct?.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        )}

        {/* Layer toggles + quick actions */}
        <div className="trackmap-toggles">
          <div className="trackmap-toggles-header">
            <h4><Layers size={13} /> Layers</h4>
            <div className="trackmap-quick-actions">
              <button className="trackmap-action-btn" onClick={() => quickAction("show_all")} title="Show All">All</button>
              <button className="trackmap-action-btn" onClick={() => quickAction("hide_events")} title="Hide all event overlays">Map</button>
              <button className="trackmap-action-btn" onClick={() => quickAction("platform_only")} title="Platform events only">Plat</button>
              <button className="trackmap-action-btn" onClick={() => quickAction("scrape_only")} title="Scrape events only">Scrape</button>
            </div>
          </div>
          <div className="trackmap-toggle-grid">
            {LAYER_DEFS.map((d) => {
              const count = layerCounts.get(d.id);
              const hasData = d.group === "map" || (count != null && count > 0);
              return (
                <label key={d.id} className={`toggle-label${!hasData ? " toggle-disabled" : ""}`}>
                  <input type="checkbox" checked={activeLayers.has(d.id)} disabled={!hasData} onChange={() => toggleLayer(d.id)} />
                  {d.label}{count != null ? ` (${count})` : ""}
                </label>
              );
            })}
          </div>
          <div className="trackmap-severity-filter">
            <label className="muted" style={{ fontSize: 11 }}>Severity:</label>
            <select className="trackmap-select trackmap-select-sm" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value as SeverityLevel)}>
              <option value="all">All</option>
              <option value="critical">Critical</option>
              <option value="high">High+</option>
              <option value="watch">Watch+</option>
              <option value="info">Info</option>
            </select>
          </div>
        </div>

        {/* Legend */}
        <div className="trackmap-legend">
          <h4>Legend</h4>
          <div className="trackmap-legend-grid">
            {Object.entries(EVENT_SYMBOLS).map(([type, { sym, label }]) => (
              <span key={type} className="legend-item"><span className="legend-sym">{sym}</span> {label}</span>
            ))}
          </div>
        </div>
      </div>

      {/* ── RIGHT PANEL: Inspector ── */}
      <aside className="trackmap-inspector">
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

        {/* Section Inspector */}
        {inspector.kind === "section" && (
          <div className="inspector-body">
            <h3>{inspector.section.name}</h3>
            <span className="inspector-badge" data-type={inspector.section.section_type}>{inspector.section.section_type}</span>
            <div className="inspector-fields">
              <div><label>Start</label><span>{inspector.section.start_lap_pct.toFixed(1)}% · {inspector.section.start_distance_ft.toFixed(0)} ft</span></div>
              <div><label>End</label><span>{inspector.section.end_lap_pct.toFixed(1)}% · {inspector.section.end_distance_ft.toFixed(0)} ft</span></div>
              <div><label>Length</label><span>{inspector.section.length_ft.toFixed(0)} ft</span></div>
              {inspector.section.wraps_start_finish && <div><label>Wraps</label><span>start / finish line</span></div>}
            </div>
            {(() => {
              const secEvts = overlays.filter((o) => {
                if (o.lap_pct == null) return false;
                const s = inspector.section;
                if (s.wraps_start_finish) return o.lap_pct >= s.start_lap_pct || o.lap_pct <= s.end_lap_pct;
                return o.lap_pct >= s.start_lap_pct && o.lap_pct <= s.end_lap_pct;
              });
              if (secEvts.length === 0) return <p className="muted" style={{ marginTop: 12 }}>No events in this section.</p>;
              const groups = groupEventsByCategory(secEvts);
              return (
                <div className="inspector-events">
                  <h4>{secEvts.length} event{secEvts.length !== 1 ? "s" : ""} in {groups.length} categor{groups.length !== 1 ? "ies" : "y"}</h4>
                  {groups.map((g) => (
                    <div key={g.category} className="inspector-event-group">
                      <div className="inspector-event-group-header">
                        <span className="event-symbol" style={{ color: g.worst?.color }}>{g.worst?.symbol ?? ""}</span>
                        <span>{g.label}</span>
                        <span className="muted">({g.events.length})</span>
                        {g.worst && <span className={`inspector-badge inspector-badge-sm`} data-severity={g.worst.severity ?? "info"}>{g.worst.severity}</span>}
                      </div>
                      {g.events.slice(0, 5).map((e) => (
                        <div key={e.marker_id} className="inspector-event-row" onClick={() => handleOverlayClick(e)}>
                          <span className="event-symbol" style={{ color: e.color }}>{e.symbol}</span>
                          <span>{e.label}</span>
                          <span className="muted">@{e.lap_pct?.toFixed(1)}%</span>
                        </div>
                      ))}
                      {g.events.length > 5 && <p className="muted" style={{ fontSize: 10, margin: 0 }}>+{g.events.length - 5} more</p>}
                    </div>
                  ))}
                </div>
              );
            })()}
          </div>
        )}

        {/* Overlay Inspector */}
        {inspector.kind === "overlay" && (
          <div className="inspector-body">
            {selectedHidden && (
              <div className="map-warning-banner" style={{ marginBottom: 10 }}>
                <Info size={12} />
                <span>Selected event is hidden by current filters.</span>
              </div>
            )}
            <h3>{inspector.overlay.label}</h3>
            <div className="inspector-badges">
              <span className="inspector-badge" data-severity={inspector.overlay.severity ?? "info"}>{inspector.overlay.severity ?? "info"}</span>
              <span className="inspector-badge">{inspector.overlay.kind}</span>
              {inspector.overlay.confidence && <span className="inspector-badge">{inspector.overlay.confidence}</span>}
            </div>
            <div className="inspector-fields">
              {inspector.overlay.description && <div><label>Description</label><span>{inspector.overlay.description}</span></div>}
              <div><label>Lap %</label><span>{inspector.overlay.lap_pct?.toFixed(2)}%</span></div>
              {inspector.overlay.distance_ft != null && <div><label>Distance</label><span>{inspector.overlay.distance_ft.toFixed(0)} ft</span></div>}
              {inspector.overlay.source_type && <div><label>Source</label><span>{inspector.overlay.source_type}</span></div>}
              {inspector.overlay.source_id && <div><label>Source ID</label><span className="mono">{inspector.overlay.source_id}</span></div>}
              {inspector.overlay.related_channels && inspector.overlay.related_channels.length > 0 && <div><label>Channels</label><span>{inspector.overlay.related_channels.join(", ")}</span></div>}
              {inspector.overlay.heading_rad != null && <div><label>Heading</label><span>{((inspector.overlay.heading_rad * 180) / Math.PI).toFixed(1)}°</span></div>}
            </div>
            {(inspector.overlay as any).front_platform_risk_score != null || (inspector.overlay as any).rear_platform_risk_score != null || (inspector.overlay as any).whole_car_bottoming_risk != null ? (
              <div className="inspector-platform">
                <h4>Platform Balance</h4>
                <div className="platform-rows">
                  {(inspector.overlay as any).platform_balance_label && (
                    <div className="platform-row"><label>Balance</label>
                      <span className={`platform-label platform-${String((inspector.overlay as any).platform_balance_label).toLowerCase().replace(/\s+/g, "-")}`}>{(inspector.overlay as any).platform_balance_label}</span>
                    </div>
                  )}
                  {(inspector.overlay as any).front_platform_risk_score != null && <div className="platform-row"><label>Front Risk</label><span>{(inspector.overlay as any).front_platform_risk_score}</span></div>}
                  {(inspector.overlay as any).rear_platform_risk_score != null && <div className="platform-row"><label>Rear Risk</label><span>{(inspector.overlay as any).rear_platform_risk_score}</span></div>}
                  {(inspector.overlay as any).whole_car_bottoming_risk != null && (
                    <div className="platform-row platform-row-emphasis"><label>Whole-Car Bottoming</label><span>{(inspector.overlay as any).whole_car_bottoming_risk}</span></div>
                  )}
                  {(inspector.overlay as any).platform_balance_explanation && <div className="platform-explanation">{(inspector.overlay as any).platform_balance_explanation}</div>}
                  {(inspector.overlay as any).rear_scrape_side_label && <div className="platform-row"><label>Scrape Side</label><span>{(inspector.overlay as any).rear_scrape_side_label}</span></div>}
                </div>
              </div>
            ) : (
              <div className="inspector-platform" style={{ opacity: 0.5 }}>
                <h4>Platform Balance</h4>
                <p className="muted">Unavailable for this event type.</p>
              </div>
            )}
          </div>
        )}
      </aside>
    </section>
  );
}
