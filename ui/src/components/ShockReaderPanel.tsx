import { AlertTriangle, Gauge } from "lucide-react";
import type { ShockReaderResponse } from "../types/shockReader";

type ShockReaderPanelProps = {
  data: ShockReaderResponse | null;
  loading: boolean;
  error?: string | null;
};

function titleCasePattern(pattern: string): string {
  return pattern.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

export function ShockReaderPanel({ data, loading, error }: ShockReaderPanelProps) {
  return (
    <section className="shock-reader-panel" aria-label="Shock Reader">
      <header className="shock-reader-header">
        <div>
          <span className="eyebrow">Platform / Shocks</span>
          <h3><Gauge size={18} /> Shock Reader</h3>
          <p>Inline damper worksheet recommendations use the selected shock movement window.</p>
        </div>
        <span className={`shock-reader-status ${error ? "error" : loading ? "loading" : data?.corners.length ? "ready" : "missing"}`}>
          {error ? "Unavailable" : loading ? "Reading" : data?.corners.length ? "Ready" : "No data"}
        </span>
      </header>

      {error && (
        <div className="shock-reader-warning" role="status">
          <AlertTriangle size={14} />
          <span>{error}</span>
        </div>
      )}

      {!error && data && (
        <>
          <div className="shock-reader-context">
            <span>Window: {data.lap_window ?? "whole run"}</span>
            <span>Phase: {data.phase ?? "not selected"}</span>
            <span>Boundary: +/-{data.boundary_in_s.toFixed(1)} in/s</span>
            <span>{data.setup_snapshot_available ? "Setup ready" : "Setup missing"}</span>
          </div>

          <div className="shock-reader-corners">
            {data.corners.map((corner) => (
              <div key={corner.corner} className="shock-reader-corner-card">
                <div>
                  <strong>{corner.corner}</strong>
                  <span>{titleCasePattern(corner.pattern)}</span>
                </div>
                <dl>
                  <div><dt>R Hi</dt><dd>{corner.rebound_hi_pct.toFixed(1)}%</dd></div>
                  <div><dt>R Lo</dt><dd>{corner.rebound_lo_pct.toFixed(1)}%</dd></div>
                  <div><dt>B Lo</dt><dd>{corner.bump_lo_pct.toFixed(1)}%</dd></div>
                  <div><dt>B Hi</dt><dd>{corner.bump_hi_pct.toFixed(1)}%</dd></div>
                </dl>
              </div>
            ))}
          </div>

          <p className="shock-reader-inline-note">
            Shock Reader: per-corner recommendations shown beside setup values. Pick one change and run clean laps.
          </p>

          {data.warnings.length > 0 && (
            <div className="shock-reader-warning" role="status">
              <AlertTriangle size={14} />
              <span>{data.warnings[0]}</span>
            </div>
          )}
        </>
      )}
    </section>
  );
}
