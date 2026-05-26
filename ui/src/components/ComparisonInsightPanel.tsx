import { AlertTriangle, BarChart3, TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { ComparisonInsightsResponse, TraceAnnotation, CorrelationInsight, SectorDeltaSummary } from "../types/compare";

type ComparisonInsightPanelProps = {
  insights: ComparisonInsightsResponse;
  onOpenDeltaTraces?: () => void;
};

const TIER_COLORS: Record<string, string> = {
  high: "#22c55e",
  medium: "#f59e0b",
  low: "#ef4444",
};

const CLASSIFICATION_COLORS: Record<string, string> = {
  stable_gain: "#22c55e",
  risky_gain: "#f59e0b",
  platform_sensitive_gain: "#f59e0b",
  driver_input_gain: "#38bdf8",
  drag_reduction: "#4ade80",
  mechanical_balance_improvement: "#a78bfa",
  inconclusive: "#8d9aaa",
};

const SEVERITY_ICONS: Record<string, typeof AlertTriangle> = {
  critical: AlertTriangle,
  high: TrendingDown,
  watch: Minus,
  info: TrendingUp,
};

function annotationIcon(kind: string) {
  switch (kind) {
    case "speed_gain": return <TrendingUp size={14} style={{ color: "#22c55e" }} />;
    case "speed_loss": return <TrendingDown size={14} style={{ color: "#ef4444" }} />;
    case "cfs_compression": return <TrendingDown size={14} style={{ color: "#f97316" }} />;
    case "drag_scrub_spike": return <AlertTriangle size={14} style={{ color: "#ef4444" }} />;
    default: return <Minus size={14} style={{ color: "#8d9aaa" }} />;
  }
}

function formatVal(v: number | null | undefined, digits = 2): string {
  return v != null && !Number.isNaN(v) ? v.toFixed(digits) : "—";
}

export function ComparisonInsightPanel({ insights, onOpenDeltaTraces }: ComparisonInsightPanelProps) {
  const tz = insights.target_zone_classification;
  const cwv = insights.confidence_weighted_verdict;

  return (
    <div className="compare-subview">
      {/* ── Summary headline ── */}
      {insights.summary_headline && (
        <div className="insight-summary-headline">
          <h3>{insights.summary_headline}</h3>
        </div>
      )}

      {/* ── Key takeaways ── */}
      {insights.key_takeaways.length > 0 && (
        <div className="insight-takeaways">
          <h4>Key Takeaways</h4>
          <ul>
            {insights.key_takeaways.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Target zone classification ── */}
      {tz && (
        <div className="insight-card" style={{ borderLeftColor: CLASSIFICATION_COLORS[tz.classification] ?? "#8d9aaa" }}>
          <div className="insight-card-header">
            <span className="insight-badge" style={{ backgroundColor: CLASSIFICATION_COLORS[tz.classification] ?? "#8d9aaa" }}>
              {tz.headline}
            </span>
            <span className="insight-confidence">{formatVal(tz.confidence * 100, 0)}% confidence</span>
          </div>
          {tz.evidence.length > 0 && (
            <ul className="insight-evidence">
              {tz.evidence.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
          {tz.recommendation && <p className="insight-recommendation"><strong>Next:</strong> {tz.recommendation}</p>}
        </div>
      )}

      {/* ── Confidence-weighted verdict ── */}
      {cwv && (
        <div className="insight-card" style={{ borderLeftColor: TIER_COLORS[cwv.confidence_tier] ?? "#8d9aaa" }}>
          <div className="insight-card-header">
            <span className="insight-badge" style={{ backgroundColor: TIER_COLORS[cwv.confidence_tier] ?? "#8d9aaa" }}>
              {cwv.confidence_tier.toUpperCase()} confidence
            </span>
            <span className="insight-verdict-label">{cwv.original_verdict.replace(/_/g, " ")}</span>
          </div>
          {cwv.boosts.length > 0 && (
            <div className="insight-factors">
              <span className="insight-factors-label">Boosts:</span>
              {cwv.boosts.map((b, i) => <span key={i} className="insight-factor-positive">+ {b}</span>)}
            </div>
          )}
          {cwv.penalties.length > 0 && (
            <div className="insight-factors">
              <span className="insight-factors-label">Penalties:</span>
              {cwv.penalties.map((p, i) => <span key={i} className="insight-factor-negative">− {p}</span>)}
            </div>
          )}
          {cwv.final_recommendation && <p className="insight-recommendation"><strong>Recommendation:</strong> {cwv.final_recommendation}</p>}
        </div>
      )}

      {/* ── Trace annotations ── */}
      {insights.annotations.length > 0 && (
        <div className="insight-section">
          <h4>Trace Annotations ({insights.annotations.length})</h4>
          <div className="insight-annotation-list">
            {insights.annotations.map((ann: TraceAnnotation) => (
              <div key={ann.id} className="insight-annotation-item">
                <span className="annotation-icon">{annotationIcon(ann.kind)}</span>
                <div className="annotation-body">
                  <span className="annotation-label">{ann.label}</span>
                  <span className="annotation-location">
                    {ann.lap_pct != null ? `${ann.lap_pct.toFixed(1)}%` : ""}
                    {ann.distance_ft != null ? ` · ${ann.distance_ft.toFixed(0)} ft` : ""}
                  </span>
                  <span className="annotation-value">{ann.description}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Correlations ── */}
      {insights.correlations.length > 0 && (
        <div className="insight-section">
          <h4>Correlations</h4>
          <div className="insight-correlation-list">
            {insights.correlations.map((corr: CorrelationInsight, i: number) => (
              <div key={i} className="insight-correlation-item">
                <span className="correlation-narrative">{corr.narrative}</span>
                <span className="correlation-strength" style={{
                  color: corr.strength === "strong" ? "#22c55e" : corr.strength === "moderate" ? "#f59e0b" : "#8d9aaa",
                }}>
                  {corr.strength} · r={corr.correlation != null ? corr.correlation.toFixed(2) : "—"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Sector summaries ── */}
      {insights.sectors.length > 0 && (
        <div className="insight-section">
          <h4>Sector Deltas</h4>
          <table className="compact-table">
            <thead>
              <tr>
                <th>Sector</th>
                <th>Speed Δ</th>
                <th>CFS Δ</th>
                <th>Steering Δ</th>
                <th>Drag Δ</th>
                <th>RPM Δ</th>
              </tr>
            </thead>
            <tbody>
              {insights.sectors.map((s: SectorDeltaSummary) => (
                <tr key={s.sector_id}>
                  <td className="cell-label">{s.label}</td>
                  <td className="cell-delta" style={{ color: (s.avg_speed_delta_mph ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                    {formatVal(s.avg_speed_delta_mph, 3)}
                  </td>
                  <td className="cell-delta" style={{ color: (s.min_cfs_delta_in ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                    {formatVal(s.min_cfs_delta_in, 3)}
                  </td>
                  <td className="cell-val">{formatVal(s.avg_steering_delta_deg, 2)}</td>
                  <td className="cell-val">{formatVal(s.avg_drag_scrub_delta, 3)}</td>
                  <td className="cell-val">{formatVal(s.avg_rpm_delta, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Warnings / missing channels ── */}
      {insights.warnings.length > 0 && (
        <div className="insight-warnings">
          {insights.warnings.map((w, i) => (
            <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>
          ))}
        </div>
      )}
      {insights.missing_channels.length > 0 && (
        <p className="warning-line">
          <AlertTriangle size={12} /> Channels not available: {insights.missing_channels.join(", ")}
        </p>
      )}

      {/* ── Open Delta Traces ── */}
      {onOpenDeltaTraces && (
        <button className="secondary-button" onClick={onOpenDeltaTraces} style={{ marginTop: 12 }}>
          <BarChart3 size={14} /> Open Delta Traces
        </button>
      )}
    </div>
  );
}
