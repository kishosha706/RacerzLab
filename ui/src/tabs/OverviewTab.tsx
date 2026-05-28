import { AlertTriangle, CheckCircle, Info, Lightbulb, MapPin } from "lucide-react";
import { useMemo } from "react";
import { EvidenceCard } from "../components/EvidenceCard";
import { EngineeringMetricCard } from "../components/EngineeringMetricCard";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { SEVERITY_COLOURS, humanizeEventLabel } from "../constants/ui";
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

function buildWhyText(event: TelemetryEvent, isLearning: boolean): string {
  // Build from evidence fields
  const parts: string[] = [];
  const t = humanizeEventLabel(event.event_type);
  if (event.primary_metric_name && event.primary_metric_value != null) {
    const pv = Number(event.primary_metric_value);
    parts.push(`${t} at ${pv.toFixed(2)}`);
  } else {
    parts.push(t);
  }

  if (event.severity === "critical") parts.push("— this is a critical risk");
  else if (event.severity === "high") parts.push("— elevated risk zone");
  else if (event.severity === "watch") parts.push("— monitor this area");

  if (isLearning) {
    if (event.related_setup_keys?.length) {
      const areas = event.related_setup_keys.slice(0, 3).map(k => k.replace(/_/g, " ")).join(", ");
      parts.push(`. Review related setup: ${areas}`);
    }
    if (event.confidence_score != null && event.confidence_score < 0.6) {
      parts.push(". Treat as a proxy/estimate until confirmed by repeated events");
    }
  }

  return parts.join("");
}

export function OverviewTab({ overview }: OverviewTabProps) {
  const lap = overview.best_useful_lap;
  const topEvent = overview.events.length > 0 ? overview.events[0] : null;
  const crewBrief = overview.crew_chief_summary;
  const { setWorkspace, selectEvent, selection } = useTelemetrySelection();
  const isLearning = selection.selectedMode === "learning";

  const gainInfo = useMemo(() => topEvent ? gainClass(topEvent) : null, [topEvent]);
  const whyText = useMemo(() => topEvent ? buildWhyText(topEvent, isLearning) : null, [topEvent, isLearning]);

  const proxyEventCount = useMemo(
    () => overview.events.filter((e) => {
      const keys = Object.keys(e.evidence_json ?? {});
      return keys.some((k) => isProxyChannel(k));
    }).length,
    [overview.events],
  );

  const handleOpenPlatform = () => {
    if (topEvent) selectEvent(topEvent.event_id, "overview");
    setWorkspace("platform_trace", "overview");
  };

  return (
    <div className="tab-grid">
      {/* ── Decision-First Hero ── */}
      <section className={`overview-hero${gainInfo ? ` ${gainInfo.cls}` : ""}`}>
        <div className="overview-hero-header">
          <h2>
            {topEvent ? (
              <span style={{ color: gainInfo?.color ?? "#38bdf8" }}>
                {humanizeEventLabel(topEvent.event_type)}
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
              {humanizeEventLabel(topEvent.event_type)}
            </p>
            {topEvent.zone_name && (
              <p className="overview-hero-location">
                <MapPin size={14} /> {topEvent.zone_name}
                {topEvent.lap_pct_peak != null && ` in target zone`}
              </p>
            )}
            {whyText && <p className="overview-hero-why">{whyText}</p>}

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

            {/* Next action as button */}
            <div className="overview-hero-actions">
              <button className="secondary-button" onClick={handleOpenPlatform}>
                <AlertTriangle size={14} /> Open in Platform Trace
              </button>
              <button className="secondary-button" onClick={() => setWorkspace("compare", "overview")}>
                <Lightbulb size={14} /> Compare Runs
              </button>
              {overview.next_test && (
                <button className="secondary-button" onClick={() => setWorkspace("notebook", "overview")}>
                  <Lightbulb size={14} /> {isLearning ? `Create test: ${overview.next_test}` : "Create Test Note"}
                </button>
              )}
            </div>

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

        {/* Learning mode extra context */}
        {isLearning && topEvent && (
          <div className="overview-learning-context">
            <h4>Why This Matters</h4>
            <p>
              {topEvent.event_type.includes("PLATFORM") || topEvent.event_type.includes("SPLITTER")
                ? "Platform events affect aero balance and straight-line speed. When the splitter or rear platform gets too low, drag increases or the aero platform can become unstable. Compare with another setup before making large changes."
                : topEvent.event_type.includes("SCRUB") || topEvent.event_type.includes("STEERING")
                ? "Steering scrub or slip means the tires are fighting each other or the track surface. This wastes speed and can overheat tires. Look at wheel-speed mismatch, steering angle, and lat G in the affected zone."
                : topEvent.event_type.includes("PRESSURE") || topEvent.event_type.includes("AERO")
                ? "Aero pressure variations affect downforce and drag balance. Higher dynamic pressure means more aero load — useful in corners, costly on straights. Compare with a tape/ride-height change."
                : "This event was flagged as notable. Open the Platform Trace to see the full telemetry context and linked setup values."}
            </p>
          </div>
        )}
      </section>

      {/* Crew Chief Brief */}
      {crewBrief && (
        <section className="crew-chief-brief">
          <h2>Crew Chief Brief</h2>
          <p className="crew-chief-text">{isLearning ? crewBrief : crewBrief.split(". ").slice(0, 2).join(". ") + "."}</p>
        </section>
      )}

      {/* Key Metrics */}
      <section className="metrics-row">
        <EngineeringMetricCard title="Best Lap" value={lap ? `Lap ${lap.lap_number} · ${lap.lap_time?.toFixed(3)}s` : null} color="#22c55e" />
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
