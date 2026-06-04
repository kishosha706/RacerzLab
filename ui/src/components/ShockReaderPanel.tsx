import { Activity, AlertTriangle, Gauge, Wrench } from "lucide-react";
import type { ShockReaderResponse, ShockRecommendation } from "../types/shockReader";

type ShockReaderPanelProps = {
  data: ShockReaderResponse | null;
  loading: boolean;
  error?: string | null;
};

function titleCasePattern(pattern: string): string {
  return pattern.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function directionLabel(rec: ShockRecommendation): string {
  if (rec.semantic_direction === "move_more_linear") return "More linear";
  if (rec.semantic_direction === "move_more_digressive") return "More digressive";
  if (rec.semantic_direction === "leave_alone") return "Leave alone";
  return rec.semantic_direction === "add" ? "Add" : "Subtract";
}

function valueText(rec: ShockRecommendation): string | null {
  if (rec.blocked_by_limit && rec.current_value != null) return `Blocked at ${rec.current_value}`;
  if (rec.current_value != null && rec.suggested_value != null) return `${rec.current_value} -> ${rec.suggested_value}`;
  if (rec.current_value == null && rec.semantic_direction !== "leave_alone") return "No setup value";
  return null;
}

export function ShockReaderPanel({ data, loading, error }: ShockReaderPanelProps) {
  const recommendation = data?.recommendations[0] ?? null;
  return (
    <section className="shock-reader-panel" aria-label="Shock Reader">
      <header className="shock-reader-header">
        <div>
          <span className="eyebrow">Platform / Shocks</span>
          <h3><Gauge size={18} /> Shock Reader</h3>
          <p>Reads the live shock movement signature and suggests one shock/slope swing to test.</p>
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

          {recommendation ? (
            <article className="shock-reader-recommendation">
              <header>
                <span className="shock-reader-rec-setting"><Wrench size={15} /> {recommendation.display_setting}</span>
                <span className="shock-reader-rec-direction">{directionLabel(recommendation)}</span>
                {valueText(recommendation) && <span className="shock-reader-rec-value">{valueText(recommendation)}</span>}
              </header>
              <div className="shock-reader-rec-grid">
                <div><span>Goal</span><p>{recommendation.goal}</p></div>
                <div><span>The Trade-off</span><p>{recommendation.tradeoff}</p></div>
                <div><span>Your Next Test</span><p>{recommendation.next_test}</p></div>
                <div>
                  <span>What to watch for</span>
                  <p>{recommendation.watch_for.join("; ")}</p>
                </div>
              </div>
              <footer>
                <span>Confidence: {recommendation.confidence}</span>
                <span>{recommendation.classification.replace("_", " ")}</span>
              </footer>
            </article>
          ) : (
            <div className="shock-reader-empty">
              <Activity size={16} />
              <span>No guarded shock/slope swing for this window.</span>
            </div>
          )}

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
