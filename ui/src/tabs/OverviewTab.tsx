import { AlertTriangle, CheckCircle, Clock, Layers, Lightbulb, MapPin, Wrench } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { EvidenceCard } from "../components/EvidenceCard";
import { EngineeringMetricCard } from "../components/EngineeringMetricCard";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { SEVERITY_COLOURS, humanizeEventLabel } from "../constants/ui";
import { isProxyChannel } from "../utils/channelMeta";
import type { RunOverview, TelemetryEvent } from "../types/telemetry";

type OverviewTabProps = {
  overview: RunOverview;
  onToggleMapOverlay?: () => void;
};

function severityLabel(severity: TelemetryEvent["severity"]): "CRITICAL" | "HIGH" | "WATCH" | "INFO" {
  if (severity === "critical") return "CRITICAL";
  if (severity === "high") return "HIGH";
  if (severity === "watch") return "WATCH";
  return "INFO";
}

function buildWhyText(event: TelemetryEvent, isLearning: boolean): string {
  const parts: string[] = [];
  const t = humanizeEventLabel(event.event_type);
  if (event.primary_metric_name && event.primary_metric_value != null) {
    const pv = Number(event.primary_metric_value);
    parts.push(`${t} at ${pv.toFixed(2)}`);
  } else {
    parts.push(t);
  }

  if (event.severity === "critical") parts.push("this is a critical risk");
  else if (event.severity === "high") parts.push("elevated risk zone");
  else if (event.severity === "watch") parts.push("monitor this area");

  if (isLearning && event.confidence_score != null && event.confidence_score < 0.6) {
    parts.push("low confidence, treat as proxy/estimate until repeated");
  }
  return parts.join(" - ");
}

function orderedWarnings(warnings: string[]): Array<{ key: string; label: string; matches: string[]; items: string[] }> {
  const groups = [
    { key: "missing_required", label: "Missing required telemetry", matches: ["missing required"] },
    { key: "missing_optional", label: "Missing optional telemetry", matches: ["missing optional"] },
    { key: "setup_snapshot", label: "Setup snapshot unavailable", matches: ["setup", "snapshot", "carsetup"] },
    { key: "proxy_heavy", label: "Proxy/estimate-heavy result", matches: ["proxy", "estimate"] },
    { key: "short_run", label: "Short run / low confidence", matches: ["short", "low confidence", "insufficient", "few laps"] },
  ].map((group) => ({
    ...group,
    items: warnings.filter((warning) => group.matches.some((match) => warning.toLowerCase().includes(match))),
  }));
  return groups;
}

export function OverviewTab({ overview, onToggleMapOverlay }: OverviewTabProps) {
  const lap = overview.best_useful_lap;
  const { setWorkspace, focusEvidence, selection } = useTelemetrySelection();
  const [openWarningKeys, setOpenWarningKeys] = useState<Record<string, boolean>>({});
  const isLearning = selection.selectedMode === "learning";

  const sortedEvents = useMemo(() => {
    const sevOrder: Record<string, number> = { critical: 0, high: 1, watch: 2, info: 3 };
    return [...overview.events].sort((a, b) => {
      const sevDiff = (sevOrder[a.severity] ?? 9) - (sevOrder[b.severity] ?? 9);
      if (sevDiff !== 0) return sevDiff;
      const confA = a.confidence_score ?? 0;
      const confB = b.confidence_score ?? 0;
      if (confB !== confA) return confB - confA;
      if (a.valid_for_tuning !== b.valid_for_tuning) return a.valid_for_tuning ? -1 : 1;
      return 0;
    });
  }, [overview.events]);

  const topEvent = sortedEvents[0] ?? null;

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

  const openTopEvent = useCallback(() => {
    if (!topEvent) return;
    focusEvidence(buildOverviewEvidence(topEvent), "platform_trace");
  }, [topEvent, buildOverviewEvidence, focusEvidence]);

  const openTopEventMapOverlay = useCallback(() => {
    if (!topEvent) return;
    focusEvidence(buildOverviewEvidence(topEvent));
    onToggleMapOverlay?.();
  }, [topEvent, buildOverviewEvidence, focusEvidence, onToggleMapOverlay]);

  const warningsByOrder = useMemo(() => orderedWarnings(overview.warnings), [overview.warnings]);
  const proxyEventCount = useMemo(
    () => overview.events.filter((event) => Object.keys(event.evidence_json ?? {}).some((key) => isProxyChannel(key))).length,
    [overview.events],
  );

  const usefulCount = overview.laps.filter((l) => l.is_useful).length;
  const invalidCount = overview.laps.length - usefulCount;
  const topSeverity = topEvent ? severityLabel(topEvent.severity) : "INFO";

  const runRiskEvents = useMemo(
    () => overview.events.filter((event) => event.lap_pct_peak != null || event.lap_pct_start != null || event.distance_m_peak != null).slice(0, 24),
    [overview.events],
  );

  return (
    <div className="tab-grid">
      <section className="overview-hero">
        <div className="overview-hero-header">
          <h2>Top Issue</h2>
          {topEvent && (
            <span className="gain-badge" style={{ borderColor: SEVERITY_COLOURS[topEvent.severity], color: SEVERITY_COLOURS[topEvent.severity] }}>
              {severityLabel(topEvent.severity)}
            </span>
          )}
        </div>
        {topEvent ? (
          <button className="overview-hero-issue" onClick={openTopEvent} style={{ textAlign: "left", background: "transparent", border: "1px solid var(--line)" }}>
            <p className="overview-hero-location">
              <MapPin size={14} /> {humanizeEventLabel(topEvent.event_type)}
              {topEvent.lap_number != null ? ` · Lap ${topEvent.lap_number}` : ""}
              {topEvent.zone_name ? ` · ${topEvent.zone_name}` : ""}
              {(topEvent.lap_pct_peak ?? topEvent.lap_pct_start) != null ? ` · ${(topEvent.lap_pct_peak ?? topEvent.lap_pct_start)?.toFixed(1)}%` : ""}
            </p>
            <p className="overview-hero-why">{buildWhyText(topEvent, isLearning)}</p>
          </button>
        ) : (
          <p className="muted">No issues detected in this run.</p>
        )}
      </section>

      <section className="workspace-section">
        <h2>Next Actions</h2>
        <div className="toolbar-actions">
          <button className="secondary-button" onClick={() => topEvent && focusEvidence(buildOverviewEvidence(topEvent), "platform_trace")}>
            <Layers size={14} /> Open Platform
          </button>
          <button className="secondary-button" onClick={openTopEventMapOverlay}>
            <MapPin size={14} /> Map Overlay
          </button>
          <button className="secondary-button" onClick={() => topEvent && focusEvidence(buildOverviewEvidence(topEvent), "setup_impact")}>
            <Wrench size={14} /> Open Setup
          </button>
          <button className="secondary-button" onClick={() => setWorkspace("notebook", "overview")}>
            <Lightbulb size={14} /> Add to Notebook
          </button>
        </div>
      </section>

      <section className="workspace-section overview-visual-summary">
        <h2>Run Health / Risk Summary</h2>
        <div className="overview-trust-summary">
          <span>Useful {usefulCount}</span>
          <span>Invalid {invalidCount}</span>
          <span>Events {overview.events.length}</span>
          <span>Top Severity {topSeverity}</span>
        </div>
      </section>

      <section className="metrics-row">
        <EngineeringMetricCard title="Best Useful Lap" value={lap ? `Lap ${lap.lap_number} · ${lap.lap_time?.toFixed(3)}s` : null} color="#22c55e" />
        <EngineeringMetricCard title="Lap Count / Useful Laps" value={`${overview.laps.length} / ${usefulCount}`} subtitle={`Invalid: ${invalidCount}`} color="#38bdf8" />
        <EngineeringMetricCard title="Classification Breakdown" value={`${overview.laps.filter((l) => l.lap_type === "flying").length} flying`} subtitle={`${overview.laps.filter((l) => l.lap_type !== "flying").length} non-flying`} color="#60a5fa" />
        <EngineeringMetricCard title="Top Severity" value={topSeverity} color="#ef4444" />
        <EngineeringMetricCard title="Platform Risk Score" value={topEvent?.severity ? severityLabel(topEvent.severity) : "INFO"} subtitle={topEvent?.event_type ? humanizeEventLabel(topEvent.event_type) : "No active issue"} color="#f97316" />
        <EngineeringMetricCard title="Scrub / Resistance Risk" value={overview.events.filter((event) => /SCRUB|RESIST|DRAG/i.test(event.event_type)).length} color="#f59e0b" />
        <EngineeringMetricCard title="Tire Condition Summary" value={overview.events.filter((event) => /TIRE|TEMP|PRESSURE|CAMBER/i.test(event.event_type)).length} subtitle="tire-related events" color="#22d3ee" />
        <EngineeringMetricCard title="Setup Snapshot Status" value={overview.setup_snapshot ? "Available" : "Unavailable"} color={overview.setup_snapshot ? "#22c55e" : "#ef4444"} />
        <EngineeringMetricCard title="Data Quality Status" value={overview.warnings.length === 0 ? "Clean" : `${overview.warnings.length} warning(s)`} subtitle={proxyEventCount > 0 ? `${proxyEventCount} proxy/estimate event(s)` : undefined} color={overview.warnings.length === 0 ? "#22c55e" : "#f59e0b"} />
      </section>

      {warningsByOrder.some((group) => group.items.length > 0) && (
        <section className="workspace-section">
          <h2>Import / Data Quality Warnings</h2>
          {warningsByOrder.map((group) => (
            <div key={group.key} style={{ marginBottom: 8 }}>
              <button
                className="trackmap-action-btn"
                onClick={() => setOpenWarningKeys((prev) => ({ ...prev, [group.key]: !prev[group.key] }))}
                disabled={group.items.length === 0}
                style={{ opacity: group.items.length === 0 ? 0.5 : 1 }}
              >
                <AlertTriangle size={12} /> {group.label} ({group.items.length})
              </button>
              {openWarningKeys[group.key] && (
                <ul className="warnings-list">
                  {group.items.map((warning) => <li key={warning} className="muted">{warning}</li>)}
                </ul>
              )}
            </div>
          ))}
        </section>
      )}

      <section className="workspace-section overview-visual-summary">
        <h2>Event Summary / Timeline Preview</h2>
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
      </section>

      <section className="workspace-section">
        <h2>Recommendations from Crew Chief</h2>
        {overview.recommendations.length > 0 ? (
          <ol className="findings-list">
            {overview.recommendations.map((rec) => (
              <li key={rec.recommendation_id}>
                <strong>P{rec.priority_rank}:</strong> {rec.recommendation_text}
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">No recommendations yet.</p>
        )}
      </section>

      <section className="workspace-section">
        <h2>Recent Findings / Notebook Links</h2>
        <div className="toolbar-actions">
          <button className="secondary-button" onClick={() => setWorkspace("notebook", "overview")}>
            <CheckCircle size={14} /> Open Notebook
          </button>
          <button className="secondary-button" onClick={() => setWorkspace("laps", "overview")}>
            <Clock size={14} /> Review in Laps
          </button>
          <button className="secondary-button" onClick={() => setWorkspace("laps", "overview")}>
            <Clock size={14} /> Open Laps
          </button>
        </div>
        <ol className="findings-list">
          {overview.primary_findings.length > 0
            ? overview.primary_findings.map((finding) => <li key={finding}>{finding}</li>)
            : <li className="muted">No findings yet.</li>}
        </ol>
      </section>

      {sortedEvents.length > 0 && (
        <section className="evidence-list">
          {sortedEvents.slice(0, 6).map((event) => (
            <EvidenceCard event={event} key={event.event_id} onToggleMapOverlay={onToggleMapOverlay} />
          ))}
        </section>
      )}
    </div>
  );
}
