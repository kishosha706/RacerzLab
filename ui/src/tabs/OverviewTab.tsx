import { AlertTriangle, CheckCircle, Info, Lightbulb, MapPin } from "lucide-react";
import { useMemo } from "react";
import { EvidenceCard } from "../components/EvidenceCard";
import { EngineeringMetricCard } from "../components/EngineeringMetricCard";
import { ProxyBadge } from "../components/ProxyBadge";
import { ValueDisplay } from "../components/ValueDisplay";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { SEVERITY_COLOURS } from "../constants/ui";
import { isProxyChannel } from "../utils/channelMeta";
import type { RunOverview, TelemetryEvent } from "../types/telemetry";

type OverviewTabProps = {
  overview: RunOverview;
};

/** Classify a target zone gain type for visual styling. */
function gainClass(event: TelemetryEvent): { cls: string; label: string; color: string } {
  const t = event.event_type;
  if (t.includes("SCRAPE") || t.includes("BOTTOMING") || t.includes("CONTACT")) {
    return { cls: "gain-negative", label: "Critical", color: "#ef4444" };
  }
  if (t.includes("LOW") || t.includes("RISK") || t.includes("LOSS")) {
    return { cls: "gain-risky", label: "Warning", color: "#f59e0b" };
  }
  if (t.includes("PRESSURE") || t.includes("STABLE")) {
    return { cls: "gain-clean", label: "Stable", color: "#22c55e" };
  }
  return { cls: "gain-neutral", label: "Info", color: "#38bdf8" };
}

export function OverviewTab({ overview }: OverviewTabProps) {
  const lap = overview.best_useful_lap;
  const topEvent = overview.events.length > 0 ? overview.events[0] : null;
  const crewBrief = overview.crew_chief_summary;
  const { setWorkspace, selectEvent } = useTelemetrySelection();

  const gainInfo = useMemo(() => topEvent ? gainClass(topEvent) : null, [topEvent]);

  // Count proxy-based events
  const proxyEventCount = useMemo(
    () => overview.events.filter((e) => {
      const keys = Object.keys(e.evidence_json ?? {});
      return keys.some((k) => isProxyChannel(k));
    }).length,
    [overview.events],
  );

  return (
    <div className="tab-grid">
      {/* ── Decision-First Hero ── */}
      <section className={`overview-hero${gainInfo ? ` ${gainInfo.cls}` : ""}`}>
        <div className="overview-hero-header">
          <h2>
            {topEvent ? (
              <span style={{ color: gainInfo?.color ?? "#38bdf8" }}>
                {topEvent.event_type.replace(/_/g, " ")}
              </span>
            ) : "Run Overview"}
          </h2>
          {gainInfo && (
            <span className="gain-badge" style={{ background: `${gainInfo.color}20`, color: gainInfo.color, border: `1px solid ${gainInfo.color}40` }}>
              {gainInfo.label}
            </span>
          )}
        </div>

        {/* Main Issue */}
        {topEvent ? (
          <div className="overview-hero-issue">
            <p className="overview-hero-headline">
              {topEvent.event_subtype ?? topEvent.event_type}
            </p>
            {topEvent.zone_name && (
              <p className="overview-hero-location">
                <MapPin size={14} /> {topEvent.zone_name}
                {topEvent.lap_pct_peak != null && ` at ${topEvent.lap_pct_peak.toFixed(1)}% lap`}
              </p>
            )}
            <p className="overview-hero-why">
              {topEvent.severity === "critical" ? "This affects corner-exit stability and straight-line speed." :
               topEvent.severity === "high" ? "This may limit corner speed and tire life." :
               "Monitor this area for changes with setup adjustments."}
            </p>

            {/* Evidence chips */}
            <div className="overview-evidence-chips">
              <span className="evidence-chip" style={{ borderColor: SEVERITY_COLOURS[topEvent.severity] ?? "#8d9aaa" }}>
                <AlertTriangle size={12} /> {topEvent.severity.toUpperCase()}
              </span>
              {topEvent.confidence_score != null && (
                <span className="evidence-chip">
                  Confidence: {(topEvent.confidence_score * 100).toFixed(0)}%
                </span>
              )}
              {topEvent.valid_for_tuning && (
                <span className="evidence-chip" style={{ borderColor: "#22c55e" }}>
                  <CheckCircle size={12} /> Valid for tuning
                </span>
              )}
            </div>

            {/* Next action */}
            {overview.next_test && (
              <p className="overview-hero-next">
                <Lightbulb size={14} /> Next: {overview.next_test}
              </p>
            )}

            {/* Proxy warning */}
            {proxyEventCount > 0 && (
              <p className="overview-hero-proxy-warning">
                <Info size={14} /> {proxyEventCount} event{proxyEventCount > 1 ? "s" : ""} based on proxy/estimate channels.
              </p>
            )}
          </div>
        ) : (
          <div className="overview-hero-empty">
            <p>No issues detected. Import a run to begin analysis.</p>
          </div>
        )}

        {/* Quick actions */}
        <div className="overview-hero-actions">
          {topEvent && (
            <button className="secondary-button" onClick={() => {
              selectEvent(topEvent.event_id, "overview");
              setWorkspace("platform_trace", "overview");
            }}>
              <AlertTriangle size={14} /> Open in Platform Trace
            </button>
          )}
          <button className="secondary-button" onClick={() => setWorkspace("compare", "overview")}>
            <Lightbulb size={14} /> Compare Runs
          </button>
        </div>
      </section>

      {/* Crew Chief Brief */}
      {crewBrief && (
        <section className="crew-chief-brief">
          <h2>Crew Chief Brief</h2>
          <p className="crew-chief-text">{crewBrief}</p>
        </section>
      )}

      {/* Key Metrics */}
      <section className="metrics-row">
        <EngineeringMetricCard title="Best Lap" value={lap ? `Lap ${lap.lap_number}` : null} color="#22c55e" />
        <EngineeringMetricCard title="Avg Speed" value={lap?.avg_speed_mph != null ? `${lap.avg_speed_mph.toFixed(1)} mph` : null} color="#38bdf8" />
        <EngineeringMetricCard title="Min Splitter" value={lap?.min_splitter_mm != null ? `${lap.min_splitter_mm.toFixed(1)} mm` : null} color="#f59e0b" />
        <EngineeringMetricCard title="Brake" value={lap?.avg_brake_pct != null ? `${lap.avg_brake_pct}%` : null} color="#ef4444" />
      </section>

      {/* Data Coverage */}
      {overview.warnings.length > 0 && (
        <section className="workspace-section">
          <h2>Data Coverage</h2>
          <ul className="warnings-list">
            {overview.warnings.map((w) => (
              <li key={w} className="muted">{w}</li>
            ))}
          </ul>
        </section>
      )}

      {/* Primary Findings */}
      <section className="workspace-section">
        <h2>Primary Findings</h2>
        <ol className="findings-list">
          {overview.primary_findings.length > 0
            ? overview.primary_findings.map((finding) => (
                <li key={finding}>{finding}</li>
              ))
            : <li className="muted">No findings yet. Import a run and run comparison to generate findings.</li>}
        </ol>
      </section>

      {/* Events */}
      <section className="evidence-list">
        {overview.events.map((event) => (
          <EvidenceCard event={event} key={event.event_id} />
        ))}
      </section>
    </div>
  );
}
