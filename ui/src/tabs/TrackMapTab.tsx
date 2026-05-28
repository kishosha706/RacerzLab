import { Info, Layers, Map as MapIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { TrackMapOverlayMarker, TrackMapPackage, TrackMapSection } from "../types/trackMap";
import { fetchRunTrackMapPackage } from "../api/client";
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

const EVENT_SYMBOLS: Record<string, { sym: string; label: string }> = {
  MIN_SPLITTER: { sym: "⬇", label: "Min Splitter" },
  WORST_SPEED_LOSS: { sym: "▼", label: "Worst Speed Loss" },
  WORST_DRAG_SCRUB: { sym: "⚠", label: "Worst Drag/Scrub" },
  HIGHEST_RAKE: { sym: "▲", label: "Highest Rake" },
  HIGHEST_PLATFORM_COMPRESSION: { sym: "●", label: "Platform Compression" },
  HIGHEST_SHOCK_ACTIVITY: { sym: "S", label: "Shock Activity" },
  MAX_DYNAMIC_PRESSURE: { sym: "○", label: "Max Dynamic Pressure" },
  REAR_SCRAPE: { sym: "R!", label: "Rear Scrape" },
  REAR_PLATFORM_LOW: { sym: "R", label: "Rear Platform Low" },
  REAR_MIN_HEIGHT: { sym: "Rmin", label: "Min Rear Ride Height" },
  REAR_CONTACT_RISK: { sym: "R?", label: "Rear Contact Risk" },
  WHOLE_CAR_BOTTOMING: { sym: "⇣", label: "Whole-Car Bottoming" },
  FRONT_SCRAPE: { sym: "F!", label: "Front Scrape" },
  FRONT_PLATFORM_LOW: { sym: "F", label: "Front Platform Low" },
};

type InspectorTarget =
  | { kind: "overlay"; overlay: TrackMapOverlayMarker }
  | { kind: "section"; section: TrackMapSection }
  | { kind: "none" };

export function TrackMapTab({ runId, lap, trackName, carName, setupName, targetZoneStartPct, targetZoneEndPct }: Props) {
  const [pkg, setPkg] = useState<TrackMapPackage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showEvents, setShowEvents] = useState(true);
  const [showTargetZone, setShowTargetZone] = useState(true);
  const [showSections, setShowSections] = useState(true);
  const [inspector, setInspector] = useState<InspectorTarget>({ kind: "none" });
  const { selectSample, selectEvent, selectZone } = useTelemetrySelection();

  useEffect(() => {
    if (!runId) { setPkg(null); return; }
    setLoading(true);
    setError(null);
    fetchRunTrackMapPackage(runId, {
      lap: lap ?? undefined,
      target_zone_start_pct: targetZoneStartPct,
      target_zone_end_pct: targetZoneEndPct,
    })
      .then(setPkg)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load track map"))
      .finally(() => setLoading(false));
  }, [runId, lap, targetZoneStartPct, targetZoneEndPct]);

  const points = pkg?.map?.points ?? [];
  const bounds = pkg?.map?.bounds;
  const overlays = pkg?.overlays ?? [];
  const markers = pkg?.map?.markers ?? [];
  const sections = pkg?.map?.sections ?? [];
  const metadata = pkg?.map?.metadata;
  const match = pkg?.match;

  const handleOverlayClick = useCallback((overlay: TrackMapOverlayMarker) => {
    setInspector({ kind: "overlay", overlay });
    if (overlay.lap_pct != null) {
      selectSample(0, undefined, overlay.lap_pct, "track_map");
    }
    if (overlay.kind === "platform_event" && overlay.source_id) {
      selectEvent(overlay.source_id, "track_map");
    }
  }, [selectSample, selectEvent]);

  const handleSectionClick = useCallback((section: TrackMapSection) => {
    setInspector({ kind: "section", section });
    selectZone(section.section_id);
  }, [selectZone]);

  const viewBox = useMemo(() => {
    if (!bounds) return "0 0 800 600";
    const pad = 50;
    const w = bounds.width_m + pad * 2;
    const h = bounds.height_m + pad * 2;
    return `${bounds.min_x_m - pad} ${bounds.min_y_m - pad} ${w} ${h}`;
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
    if (!showSections || sections.length === 0) return [];
    return sections.map((s) => {
      const secPts = points.filter((p) => {
        if (p.lap_pct == null) return false;
        if (s.wraps_start_finish) return p.lap_pct >= s.start_lap_pct || p.lap_pct <= s.end_lap_pct;
        return p.lap_pct >= s.start_lap_pct && p.lap_pct <= s.end_lap_pct;
      });
      const d = secPts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x ?? p.x_m} ${p.y ?? p.y_m}`).join(" ");
      return { section: s, d, count: secPts.length };
    }).filter((sp) => sp.count > 1);
  }, [points, sections, showSections]);

  // count events within a section
  const eventsInSection = useCallback((sec: TrackMapSection) => {
    return overlays.filter((o) => {
      if (o.lap_pct == null) return false;
      if (sec.wraps_start_finish) return o.lap_pct >= sec.start_lap_pct || o.lap_pct <= sec.end_lap_pct;
      return o.lap_pct >= sec.start_lap_pct && o.lap_pct <= sec.end_lap_pct;
    });
  }, [overlays]);

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

  if (!pkg?.map) {
    return (
      <section className="notebook-tab">
        <h2><MapIcon size={18} /> Track Map</h2>
        <div className="notebook-empty">
          <p>No track map available for this run.</p>
          <p className="muted">Import a matching .mt2 file from your Track Maps folder.</p>
          {/* TODO: manual map selector — call /api/runs/{run_id}/track-map-package?preferred_map_id=<id> */}
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
        {/* Header summary */}
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

        {/* Warning */}
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
            {/* Centerline */}
            <path d={pointPath} fill="none" stroke="#4ade80" strokeWidth={4} strokeOpacity={0.7} />
            {/* Target Zone */}
            {showTargetZone && targetZonePath && (
              <path d={targetZonePath} fill="none" stroke="#22c55e" strokeWidth={8} strokeOpacity={0.4} />
            )}
            {/* Sections */}
            {sectionPolylines.map((sp) => (
              <g key={sp.section.section_id} style={{ cursor: "pointer" }} onClick={() => handleSectionClick(sp.section)}>
                <title>
                  {sp.section.name} ({sp.section.section_type})
                  {"\n"}{sp.section.start_lap_pct.toFixed(1)}%–{sp.section.end_lap_pct.toFixed(1)}% · {sp.section.length_ft.toFixed(0)} ft
                  {sp.section.wraps_start_finish ? "\nwraps start/finish" : ""}
                </title>
                <path
                  d={sp.d}
                  fill="none"
                  stroke={selectedSectionId === sp.section.section_id ? "#38bdf8" : "#1e40af"}
                  strokeWidth={selectedSectionId === sp.section.section_id ? 6 : 3}
                  strokeOpacity={selectedSectionId === sp.section.section_id ? 0.9 : 0.45}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            ))}
            {/* Markers */}
            {showMarkers && markers.map((m) => (
              <g key={m.marker_id}>
                <title>{m.name} — {m.distance_ft?.toFixed(0)} ft</title>
                <circle cx={m.x} cy={m.y} r={4} fill="#38bdf8" />
                <text x={m.x + 6} y={m.y - 6} fill="#8d9aaa" fontSize={9} fontFamily="Inter, sans-serif">{m.name}</text>
              </g>
            ))}
            {/* Event overlays */}
            {showEvents && overlays
              .filter((o) => o.kind === "platform_event")
              .map((o) =>
                o.x != null && o.y != null ? (
                  <g key={o.marker_id} style={{ cursor: "pointer" }} onClick={() => handleOverlayClick(o)}>
                    <title>{o.label}{o.description ? ` — ${o.description}` : ""} @ {o.lap_pct?.toFixed(1)}%</title>
                    <circle
                      cx={o.x} cy={o.y}
                      r={selectedOverlayId === o.marker_id ? 7 : 5}
                      fill={o.color ?? "#f59e0b"}
                      stroke={selectedOverlayId === o.marker_id ? "#fff" : "#0a0d14"}
                      strokeWidth={selectedOverlayId === o.marker_id ? 2.5 : 1.5}
                    />
                    <text x={o.x + 8} y={o.y + 4} fill={o.color ?? "#f59e0b"} fontSize={9} fontFamily="Inter, sans-serif">
                      {o.symbol ?? "◆"} {o.label}
                    </text>
                  </g>
                ) : null
              )}
          </svg>
        </div>

        {/* Fallback events (no map position) */}
        {overlays.filter((o) => o.kind === "platform_event" && o.x == null).length > 0 && (
          <div className="map-fallback-events">
            <h4>Events (lap-distance only)</h4>
            {overlays.filter((o) => o.kind === "platform_event" && o.x == null).map((o) => (
              <div key={o.marker_id} className="map-event-row" style={{ cursor: "pointer" }} onClick={() => handleOverlayClick(o)}>
                <span className="event-symbol" style={{ color: o.color }}>{o.symbol} {o.label}</span>
                <span className="event-pct">@{o.lap_pct?.toFixed(1)}%</span>
              </div>
            ))}
          </div>
        )}

        {/* Layer toggles */}
        <div className="trackmap-toggles">
          <h4><Layers size={13} /> Layers</h4>
          <div className="trackmap-toggle-grid">
            <label className="toggle-label"><input type="checkbox" checked={showSections} onChange={(e) => setShowSections(e.target.checked)} /> Sections</label>
            <label className="toggle-label"><input type="checkbox" checked={showTargetZone} onChange={(e) => setShowTargetZone(e.target.checked)} /> Target Zone</label>
            <label className="toggle-label"><input type="checkbox" checked={showEvents} onChange={(e) => setShowEvents(e.target.checked)} /> Platform Events</label>
            <label className="toggle-label"><input type="checkbox" checked={showMarkers} onChange={(e) => setShowMarkers(e.target.checked)} /> Markers</label>
            <label className="toggle-label toggle-disabled"><input type="checkbox" disabled /> Front/Rear Scrape</label>
            <label className="toggle-label toggle-disabled"><input type="checkbox" disabled /> Whole-Car Bottoming</label>
            <label className="toggle-label toggle-disabled"><input type="checkbox" disabled /> Delta</label>
            <label className="toggle-label toggle-disabled"><input type="checkbox" disabled /> Insights</label>
            <label className="toggle-label toggle-disabled"><input type="checkbox" disabled /> Tires/Shocks</label>
            <label className="toggle-label toggle-disabled"><input type="checkbox" disabled /> Notebook</label>
          </div>
        </div>

        {/* Legend */}
        <div className="trackmap-legend">
          <h4>Legend</h4>
          <div className="trackmap-legend-grid">
            {Object.entries(EVENT_SYMBOLS).map(([type, { sym, label }]) => (
              <span key={type} className="legend-item">
                <span className="legend-sym">{sym}</span> {label}
              </span>
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
          </div>
        )}

        {/* ── Section Inspector ── */}
        {inspector.kind === "section" && (
          <div className="inspector-body">
            <h3>{inspector.section.name}</h3>
            <span className="inspector-badge" data-type={inspector.section.section_type}>
              {inspector.section.section_type}
            </span>
            <div className="inspector-fields">
              <div><label>Start</label><span>{inspector.section.start_lap_pct.toFixed(1)}% · {inspector.section.start_distance_ft.toFixed(0)} ft</span></div>
              <div><label>End</label><span>{inspector.section.end_lap_pct.toFixed(1)}% · {inspector.section.end_distance_ft.toFixed(0)} ft</span></div>
              <div><label>Length</label><span>{inspector.section.length_ft.toFixed(0)} ft</span></div>
              {inspector.section.wraps_start_finish && (
                <div><label>Wraps</label><span>start / finish line</span></div>
              )}
            </div>
            {(() => {
              const secEvents = eventsInSection(inspector.section);
              if (secEvents.length === 0) {
                return <p className="muted" style={{ marginTop: 12 }}>No events in this section.</p>;
              }
              const worst = secEvents.reduce((a, b) =>
                (a.severity === "critical" || b.severity !== "critical") && a.severity !== "info" ? a : b
              , secEvents[0]);
              return (
                <div className="inspector-events">
                  <h4>{secEvents.length} event{secEvents.length !== 1 ? "s" : ""}</h4>
                  {worst && <p className="muted">Worst: <span className="event-symbol" style={{ color: worst.color }}>{worst.symbol} {worst.label}</span> ({worst.severity})</p>}
                  {secEvents.slice(0, 10).map((e) => (
                    <div key={e.marker_id} className="inspector-event-row" onClick={() => handleOverlayClick(e)}>
                      <span className="event-symbol" style={{ color: e.color }}>{e.symbol}</span>
                      <span>{e.label}</span>
                      <span className="muted">@{e.lap_pct?.toFixed(1)}%</span>
                    </div>
                  ))}
                  {secEvents.length > 10 && <p className="muted">+{secEvents.length - 10} more</p>}
                </div>
              );
            })()}
          </div>
        )}

        {/* ── Overlay Inspector ── */}
        {inspector.kind === "overlay" && (
          <div className="inspector-body">
            <h3>{inspector.overlay.label}</h3>
            <div className="inspector-badges">
              <span className="inspector-badge" data-severity={inspector.overlay.severity ?? "info"}>
                {inspector.overlay.severity ?? "info"}
              </span>
              <span className="inspector-badge">{inspector.overlay.kind}</span>
              {inspector.overlay.confidence && (
                <span className="inspector-badge">{inspector.overlay.confidence}</span>
              )}
            </div>
            <div className="inspector-fields">
              {inspector.overlay.description && (
                <div><label>Description</label><span>{inspector.overlay.description}</span></div>
              )}
              <div><label>Lap %</label><span>{inspector.overlay.lap_pct?.toFixed(2)}%</span></div>
              {inspector.overlay.distance_ft != null && (
                <div><label>Distance</label><span>{inspector.overlay.distance_ft.toFixed(0)} ft</span></div>
              )}
              {inspector.overlay.source_type && (
                <div><label>Source</label><span>{inspector.overlay.source_type}</span></div>
              )}
              {inspector.overlay.source_id && (
                <div><label>Source ID</label><span className="mono">{inspector.overlay.source_id}</span></div>
              )}
              {inspector.overlay.related_channels && inspector.overlay.related_channels.length > 0 && (
                <div><label>Channels</label><span>{inspector.overlay.related_channels.join(", ")}</span></div>
              )}
              {inspector.overlay.heading_rad != null && (
                <div><label>Heading</label><span>{((inspector.overlay.heading_rad * 180) / Math.PI).toFixed(1)}°</span></div>
              )}
            </div>

            {/* ── Platform balance ── */}
            {(inspector.overlay as any).front_platform_risk_score != null || (inspector.overlay as any).rear_platform_risk_score != null || (inspector.overlay as any).whole_car_bottoming_risk != null ? (
              <div className="inspector-platform">
                <h4>Platform Balance</h4>
                <div className="platform-rows">
                  {(inspector.overlay as any).platform_balance_label && (
                    <div className="platform-row">
                      <label>Balance</label>
                      <span className={`platform-label platform-${String((inspector.overlay as any).platform_balance_label).toLowerCase().replace(/\s+/g, "-")}`}>
                        {(inspector.overlay as any).platform_balance_label}
                      </span>
                    </div>
                  )}
                  {(inspector.overlay as any).front_platform_risk_score != null && (
                    <div className="platform-row">
                      <label>Front Risk</label>
                      <span>{(inspector.overlay as any).front_platform_risk_score}</span>
                    </div>
                  )}
                  {(inspector.overlay as any).rear_platform_risk_score != null && (
                    <div className="platform-row">
                      <label>Rear Risk</label>
                      <span>{(inspector.overlay as any).rear_platform_risk_score}</span>
                    </div>
                  )}
                  {(inspector.overlay as any).whole_car_bottoming_risk != null && (
                    <div className="platform-row platform-row-emphasis">
                      <label>Whole-Car Bottoming</label>
                      <span>{(inspector.overlay as any).whole_car_bottoming_risk}</span>
                    </div>
                  )}
                  {(inspector.overlay as any).platform_balance_explanation && (
                    <div className="platform-explanation">{(inspector.overlay as any).platform_balance_explanation}</div>
                  )}
                  {(inspector.overlay as any).rear_scrape_side_label && (
                    <div className="platform-row">
                      <label>Scrape Side</label>
                      <span>{(inspector.overlay as any).rear_scrape_side_label}</span>
                    </div>
                  )}
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
