import { AlertTriangle, Map as MapIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { TrackMapPackage } from "../types/trackMap";
import { fetchRunTrackMapPackage } from "../api/client";

interface Props {
  runId: string | null;
  lap?: number | null;
  trackName?: string | null;
  carName?: string | null;
  setupName?: string | null;
  targetZoneStartPct?: number;
  targetZoneEndPct?: number;
}

export function TrackMapTab({ runId, lap, trackName, carName, setupName, targetZoneStartPct, targetZoneEndPct }: Props) {
  const [pkg, setPkg] = useState<TrackMapPackage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showOverlays, setShowOverlays] = useState(true);
  const [showTargetZone, setShowTargetZone] = useState(true);

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
        </div>
      </section>
    );
  }

  // ── render ──
  return (
    <section className="notebook-tab">
      <header className="notebook-header">
        <h2><MapIcon size={18} /> Track Map</h2>
        <div className="track-map-controls">
          <span className="source-badge source-mt2">.mt2</span>
          <label className="toggle-label"><input type="checkbox" checked={showMarkers} onChange={(e) => setShowMarkers(e.target.checked)} /> Markers</label>
          <label className="toggle-label"><input type="checkbox" checked={showOverlays} onChange={(e) => setShowOverlays(e.target.checked)} /> Events</label>
          <label className="toggle-label"><input type="checkbox" checked={showTargetZone} onChange={(e) => setShowTargetZone(e.target.checked)} /> Target Zone</label>
        </div>
      </header>

      {/* loaded run identity */}
      <div className="map-identity-section">
        <div className="map-identity-row">
          <span className="map-identity-label">Loaded Run:</span>
          <span className="map-identity-value">
            {trackName ?? "Unknown Track"}
            {carName && ` — ${carName}`}
            {setupName && ` · ${setupName}`}
          </span>
        </div>
        {match ? (
          <div className="map-identity-row">
            <span className="map-identity-label">Matched Map:</span>
            <span className="map-identity-value" style={{ color: match.match_confidence === "high" ? "#4ade80" : "#f59e0b" }}>
              {match.source_filename ?? match.display_name}
              <span className="map-confidence-badge" data-confidence={match.match_confidence ?? "medium"}>
                {match.match_confidence ?? "medium"} confidence
              </span>
            </span>
          </div>
        ) : (
          <div className="map-identity-row">
            <span className="map-identity-label">Matched Map:</span>
            <span className="map-identity-value" style={{ color: "#8d9aaa" }}>
              No .mt2 file matched — {pkg?.map ? "using telemetry-derived layout" : "no map available"}
            </span>
          </div>
        )}
      </div>

      {pkg?.map && (
        <>
          {/* warnings */}
          {metadata?.warnings && metadata.warnings.length > 0 && (
            <div className="map-warnings">
              {metadata.warnings.map((w: string, i: number) => (
                <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>
              ))}
            </div>
          )}

          {/* parsed summary */}
          <p className="map-summary">
            Parsed .mt2 centerline: {points.length.toLocaleString()} points
            {metadata?.has_markers && `, ${markers.length} markers`}
            {metadata?.has_sections && `, ${sections.length} sections`}
            . {metadata && !metadata.origin.gps_supported && "No GPS, banking, width, or boundary data found."}
          </p>

          {/* SVG map */}
          <div className="track-map-svg-container">
            <svg viewBox={viewBox} className="track-map-svg">
              <path d={pointPath} fill="none" stroke="#4ade80" strokeWidth={4} strokeOpacity={0.7} />
              {showTargetZone && targetZonePath && (
                <path d={targetZonePath} fill="none" stroke="#22c55e" strokeWidth={8} strokeOpacity={0.5} />
              )}
              {showMarkers && markers.map((m) => (
                <g key={m.marker_id}>
                  <circle cx={m.x} cy={m.y} r={4} fill="#38bdf8" />
                  <text x={m.x + 6} y={m.y - 6} fill="#8d9aaa" fontSize={9} fontFamily="Inter, sans-serif">{m.name}</text>
                </g>
              ))}
              {showOverlays && overlays
                .filter((o) => o.kind === "platform_event")
                .map((o) => (
                  o.x != null && o.y != null ? (
                    <g key={o.marker_id}>
                      <circle cx={o.x} cy={o.y} r={5} fill={o.color ?? "#f59e0b"} stroke="#0a0d14" strokeWidth={1.5} />
                      <text x={o.x + 7} y={o.y + 4} fill={o.color ?? "#f59e0b"} fontSize={9} fontFamily="Inter, sans-serif">{o.symbol ?? "◆"} {o.label}</text>
                    </g>
                  ) : null
                ))}
            </svg>
          </div>

          {overlays.filter((o) => o.kind === "platform_event" && o.x == null).length > 0 && (
            <div className="map-fallback-events">
              <h4>Events (lap-distance only)</h4>
              {overlays.filter((o) => o.kind === "platform_event" && o.x == null).map((o) => (
                <div key={o.marker_id} className="map-event-row">
                  <span className="event-symbol" style={{ color: o.color }}>{o.symbol} {o.label}</span>
                  <span className="event-pct">@{o.lap_pct?.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
