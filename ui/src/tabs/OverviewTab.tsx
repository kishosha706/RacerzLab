import { AlertTriangle, BarChart3, CheckCircle, Clock, Info, Layers, Lightbulb, MapPin } from "lucide-react";
import { useCallback, useMemo } from "react";
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

  // Sort events by severity (critical first), then confidence, then actionable priority
  const sortedEvents = useMemo(() => {
    const sevOrder: Record<string, number> = { critical: 0, high: 1, watch: 2, info: 3 };
    return [...overview.events].sort((a, b) => {
      const sevDiff = (sevOrder[a.severity] ?? 9) - (sevOrder[b.severity] ?? 9);
      if (sevDiff !== 0) return sevDiff;
      const confA = a.confidence_score ?? 0;
      const confB = b.confidence_score ?? 0;
      if (confB !== confA) return confB - confA; // higher confidence first
      // Actionable events (valid_for_tuning) before non-actionable
      if (a.valid_for_tuning !== b.valid_for_tuning) return a.valid_for_tuning ? -1 : 1;
      return 0;
    });
  }, [overview.events]);

  const topEvent = sortedEvents.length > 0 ? sortedEvents[0] : null;
  const crewBrief = overview.crew_chief_summary;
  const { setWorkspace, focusEvidence, selection } = useTelemetrySelection();
  const isLearning = selection.selectedMode === "learning";

  const buildOverviewEvidence = useCallback((event: TelemetryEvent) => {
    const hasLocation = event.lap_pct_peak != null || event.lap_pct_start != null || event.distance_m_peak != null;
    const lapDistFt = event.distance_m_peak != null ? event.distance_m_peak * 3.280839895 : null;
    const lapPct = event.lap_pct_peak ?? event.lap_pct_start ?? null;
    return {
      runId: overview.run_id,
      lapNumber: event.lap_number ?? null,
      eventId: event.event_id,
      sampleIndex: null,
      lapDistFt,
      lapPct,
      lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
      valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
      selectionSource: "overview" as const,
    };
  }, [overview.run_id]);

  const handleOpenPlatform = useCallback(() => {
    if (topEvent) focusEvidence(buildOverviewEvidence(topEvent), "platform_trace");
  }, [topEvent, focusEvidence, buildOverviewEvidence]);

  const handleOpenSetup = useCallback(() => {
    if (topEvent) focusEvidence(buildOverviewEvidence(topEvent), "setup_impact");
  }, [topEvent, focusEvidence, buildOverviewEvidence]);

  const gainInfo = useMemo(() => topEvent ? gainClass(topEvent) : null, [topEvent]);
  const whyText = useMemo(() => topEvent ? buildWhyText(topEvent, isLearning) : null, [topEvent, isLearning]);

  const proxyEventCount = useMemo(
    () => overview.events.filter((e) => {
      const keys = Object.keys(e.evidence_json ?? {});
      return keys.some((k) => isProxyChannel(k));
    }).length,
    [overview.events],
  );

  const runRiskEvents = useMemo(() => overview.events
    .filter((event) => event.lap_pct_peak != null || event.lap_pct_start != null || event.distance_m_peak != null)
    .slice(0, 24),
    [overview.events],
  );

  const usefulCount = overview.laps.filter((l) => l.is_useful).length;
  const draftCount = overview.laps.filter((l) => (l.classification_tags ?? []).some((tag) => tag.includes("DRAFT"))).length;
  const invalidCount = overview.laps.filter((l) => !l.is_useful).length;
  const systemCounts = useMemo(() => {
    const systems = [
      { key: "platform", label: "Platform", match: /PLATFORM|SPLITTER|BOTTOM|RIDE/i },
      { key: "tires", label: "Tires", match: /TIRE|PRESSURE|CAMBER/i },
      { key: "shocks", label: "Shocks", match: /SHOCK|DAMPER/i },
      { key: "aero", label: "Aero", match: /AERO|PRESSURE|RAKE/i },
      { key: "scrub", label: "Scrub", match: /SCRUB|STEER|DRAG/i },
    ];
    return systems.map((system) => ({
      ...system,
      count: overview.events.filter((event) => system.match.test(event.event_type)).length,
      worst: overview.events.find((event) => system.match.test(event.event_type))?.severity ?? "info",
    }));
  }, [overview.events]);

  const handleBuildOverviewRiskEvidence = useCallback((event: TelemetryEvent) => {
    focusEvidence(buildOverviewEvidence(event), "platform_trace");
  }, [focusEvidence, buildOverviewEvidence]);

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
            {topEvent.zone_name && (
              <p className="overview-hero-location">
                <MapPin size={14} /> {topEvent.zone_name}
                {topEvent.lap_pct_peak != null && ` in target zone`}
              </p>
            )}
            {whyText && <p className="overview-hero-why">{whyText}</p>}

            {/* Evidence chips — clickable when context is available */}
            <div className="overview-evidence-chips">
              <button
                className="evidence-chip evidence-chip-clickable"
                style={{ borderColor: SEVERITY_COLOURS[topEvent.severity] ?? "#8d9aaa", cursor: "pointer", background: "none", color: "inherit", font: "inherit", padding: "2px 8px" }}
                onClick={handleOpenPlatform}
                title="Open in Platform Trace"
              >
                <AlertTriangle size={12} /> {topEvent.severity.toUpperCase()}
              </button>
              {topEvent.confidence_score != null && (
                <span className="evidence-chip" title={`Confidence: ${(topEvent.confidence_score * 100).toFixed(0)}%`}>
                  Confidence: {(topEvent.confidence_score * 100).toFixed(0)}%
                </span>
              )}
              {topEvent.valid_for_tuning && (
                <button
                  className="evidence-chip evidence-chip-clickable"
                  style={{ borderColor: "#22c55e", cursor: "pointer", background: "none", color: "inherit", font: "inherit", padding: "2px 8px" }}
                  onClick={handleOpenSetup}
                  title="Open in Setup"
                >
                  <CheckCircle size={12} /> Valid for tuning
                </button>
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
        ) : overview.events.length === 0 ? (
          <div className="overview-zero-state">
            <h3>No critical events detected.</h3>
            <p>Platform margins appear within safe limits.</p>
            <p>Review Laps for pace quality and Compare for setup validation.</p>
            <div className="overview-zero-actions">
              <button className="secondary-button" onClick={() => setWorkspace("laps", "overview")}>
                <Clock size={14} /> Open Laps
              </button>
              <button className="secondary-button" onClick={() => setWorkspace("platform_trace", "overview")}>
                <Layers size={14} /> Open Platform
              </button>
              <button className="secondary-button" onClick={() => setWorkspace("compare", "overview")}>
                <BarChart3 size={14} /> Open Compare
              </button>
            </div>
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

      <section className="workspace-section overview-visual-summary">
        <h2>Run Risk Timeline</h2>
        <div className="overview-risk-strip">
          {runRiskEvents.length === 0 ? (
            <span className="risk-strip-empty">No located events available.</span>
          ) : runRiskEvents.map((event) => {
            const pos = event.lap_pct_peak ?? event.lap_pct_start ?? 0;
            return (
              <button
                key={event.event_id}
                className="overview-risk-marker"
                data-severity={event.severity}
                style={{ left: `${Math.max(0, Math.min(100, pos))}%` }}
                onClick={() => { focusEvidence(buildOverviewEvidence(event), "platform_trace"); }}
                title={`${humanizeEventLabel(event.event_type)} | ${event.severity}`}
                aria-label={`Open ${humanizeEventLabel(event.event_type)} in Platform`}
              />
            );
          })}
        </div>
        <div className="overview-trust-system-grid">
          <div className="overview-trust-summary">
            <span>Useful {usefulCount}</span>
            <span>Draft {draftCount}</span>
            <span>Invalid {invalidCount}</span>
          </div>
          <div className="overview-system-counts">
            {systemCounts.map((system) => (
              <span key={system.key} className="overview-system-chip" data-severity={system.count > 0 ? system.worst : "missing"}>
                {system.label}: {system.count}
              </span>
            ))}
          </div>
        </div>
      </section>

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

      {/* Recommendations */}
      <section className="workspace-section">
        <h2>Recommendations</h2>
        {overview.recommendations.length > 0 ? (
          <ol className="findings-list">
            {overview.recommendations.map((rec) => (
              <li key={rec.recommendation_id}>
                <strong>P{rec.priority_rank}:</strong> {rec.recommendation_text}
                {rec.success_metric && <span className="muted" style={{ marginLeft: 8 }}>— Success metric: {rec.success_metric}</span>}
                {rec.evidence_strength && rec.evidence_strength !== "unknown" && <span className="muted" style={{ marginLeft: 8 }}>({rec.evidence_strength} evidence)</span>}
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No recommendations yet. Compare runs to generate setup recommendations.</p>
        )}
      </section>

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
