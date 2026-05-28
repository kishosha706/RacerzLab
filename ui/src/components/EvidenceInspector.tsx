import { AlertTriangle, ClipboardCheck, Crosshair, Database, Info } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { ChannelCatalogItem, PlatformEventItem, RunOverview } from "../types/telemetry";

type EvidenceInspectorProps = {
  overview: RunOverview | null;
  platformEvents: PlatformEventItem[];
  channels: ChannelCatalogItem[];
};

export function EvidenceInspector({ overview, platformEvents, channels }: EvidenceInspectorProps) {
  const { selection } = useTelemetrySelection();
  const [justAnchored, setJustAnchored] = useState(false);
  const prevEventRef = useRef<string | null | undefined>(null);

  const selectedEvent = useMemo(
    () => platformEvents.find((e) => e.event_id === selection.selectedEventId) ?? null,
    [platformEvents, selection.selectedEventId],
  );

  const selectedChannel = useMemo(
    () => channels.find((c) => c.name === selection.selectedChannel) ?? null,
    [channels, selection.selectedChannel],
  );

  // Evidence Anchor Beam: pulse when event selection changes
  useEffect(() => {
    if (selection.selectedEventId && selection.selectedEventId !== prevEventRef.current) {
      setJustAnchored(true);
      const timer = setTimeout(() => setJustAnchored(false), 700);
      prevEventRef.current = selection.selectedEventId;
      return () => clearTimeout(timer);
    }
  }, [selection.selectedEventId]);

  const anchorClass = selectedEvent
    ? ` evidence-inspector anchored${justAnchored ? " anchor-just-selected" : ""}`
    : "";

  if (selectedEvent) return (
    <div className={anchorClass}>
      <EventInspector event={selectedEvent} showAnchorBadge={true} />
    </div>
  );
  if (selectedChannel) return <ChannelInspector channel={selectedChannel} />;
  return <RunInspector overview={overview} channels={channels} />;
}

function RunInspector({ overview, channels }: { overview: RunOverview | null; channels: ChannelCatalogItem[] }) {
  if (!overview) return <InspectorShell title="No Run Loaded" icon={<Database size={16} />} />;

  const raw = channels.filter((c) => c.is_raw && !c.missing_status).length;
  const calc = channels.filter((c) => c.is_calculated && !c.missing_status).length;
  const proxy = channels.filter((c) => c.is_proxy).length;
  const missing = channels.filter((c) => c.missing_status).length;

  return (
    <InspectorShell title="Run Overview" icon={<Info size={16} />}>
      <dl>
        <dt>Track</dt>
        <dd>{overview.session.track_display_name ?? overview.session.track_name ?? "Unknown"}</dd>
        <dt>Car</dt>
        <dd>{overview.session.car_name ?? "Unknown"}</dd>
        <dt>Setup</dt>
        <dd>{overview.session.setup_name ?? "None"}</dd>
        <dt>Best Lap</dt>
        <dd>{overview.best_useful_lap ? `Lap ${overview.best_useful_lap.lap_number} (${overview.best_useful_lap.lap_time?.toFixed(2)}s)` : "None"}</dd>
        <dt>Useful Laps</dt>
        <dd>{overview.laps.filter((l) => l.is_useful).length} / {overview.laps.length}</dd>
      </dl>
      <div className="inspector-data-coverage">
        <h4>Data Coverage</h4>
        <div className="coverage-grid">
          <span>Raw: {raw}</span>
          <span>Calculated: {calc}</span>
          <span>Proxy: {proxy}</span>
          {missing > 0 && <span className="coverage-warn">Missing: {missing}</span>}
        </div>
      </div>
      {overview.warnings.length > 0 && (
        <div className="inspector-warnings">
          {overview.warnings.map((w, i) => (
            <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>
          ))}
        </div>
      )}
      <CrewChiefSummary overview={overview} />
    </InspectorShell>
  );
}

function CrewChiefSummary({ overview }: { overview: RunOverview }) {
  const [collapsed, setCollapsed] = useState(false);
  const recommendation = overview.recommendations?.[0];
  return (
    <details className="crew-chief-inline" open={!collapsed}>
      <summary onClick={() => setCollapsed(!collapsed)}>
        <ClipboardCheck size={14} /> Crew Chief {collapsed ? "" : ""}
      </summary>
      <p className="crew-summary">{overview.crew_chief_summary}</p>
      {recommendation ? (
        <div className="inspector-crew-block">
          <span className="eyebrow">Next test</span>
          <p>{recommendation.recommendation_text}</p>
          <strong>{recommendation.success_metric}</strong>
        </div>
      ) : (
        <div className="inspector-crew-block">
          <span className="eyebrow">No call</span>
          <p>No recommendation is shown without supporting evidence.</p>
        </div>
      )}
    </details>
  );
}

function EventInspector({ event, showAnchorBadge }: { event: PlatformEventItem; showAnchorBadge?: boolean }) {
  const sevColour = event.severity === "critical" ? "#ef4444" : event.severity === "high" ? "#f97316" : event.severity === "watch" ? "#f59e0b" : "#38bdf8";

  return (
    <InspectorShell title={event.title} icon={<Crosshair size={16} />}>
      {showAnchorBadge && <span className="anchor-evidence-badge"><Crosshair size={10} /> Anchored Evidence</span>}
      <div className="inspector-meta">
        <span className="severity-badge" style={{ color: sevColour, borderColor: sevColour }}>
          <AlertTriangle size={12} /> {event.severity.toUpperCase()}
        </span>
        <span>Confidence: {event.confidence}</span>
        {event.is_proxy_based && <span className="proxy-pill">PROXY</span>}
      </div>
      <dl>
        <dt>Location</dt>
        <dd>
          Lap {event.lap ?? "n/a"}
          {event.lap_dist_ft != null && ` · ${event.lap_dist_ft.toFixed(0)} ft`}
        </dd>
        {event.primary_value != null && (
          <>
            <dt>Value</dt>
            <dd>{event.primary_value.toFixed(3)} {event.primary_unit ?? ""}</dd>
          </>
        )}
      </dl>
      {event.evidence.length > 0 && (
        <div className="inspector-evidence">
          <h4>Why it was flagged</h4>
          <ul>
            {event.evidence.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </div>
      )}
      {event.recommended_action && (
        <div className="inspector-action">
          <h4>Recommended</h4>
          <p>{event.recommended_action}</p>
        </div>
      )}
      {event.is_proxy_based && event.proxy_warning && (
        <p className="inspector-proxy-warning">{event.proxy_warning}</p>
      )}
    </InspectorShell>
  );
}

function ChannelInspector({ channel }: { channel: ChannelCatalogItem }) {
  return (
    <InspectorShell title={channel.name} icon={<Database size={16} />}>
      <dl>
        <dt>Type</dt>
        <dd>
          {channel.is_calculated ? "Calculated" : channel.is_raw ? "Raw" : "Derived"}
          {channel.is_proxy && <span className="proxy-pill">PROXY</span>}
        </dd>
        {channel.unit && <><dt>Unit</dt><dd>{channel.unit}</dd></>}
        {channel.description && <><dt>Description</dt><dd>{channel.description}</dd></>}
        {channel.min != null && <><dt>Min</dt><dd>{channel.min.toFixed(4)}</dd></>}
        {channel.max != null && <><dt>Max</dt><dd>{channel.max.toFixed(4)}</dd></>}
        {channel.mean != null && <><dt>Mean</dt><dd>{channel.mean.toFixed(4)}</dd></>}
      </dl>
      {channel.missing_status && <p className="inspector-warn">{channel.missing_status}</p>}
    </InspectorShell>
  );
}

function InspectorShell({ title, icon, children }: { title: string; icon: React.ReactNode; children?: React.ReactNode }) {
  return (
    <aside className="evidence-inspector">
      <header className="inspector-header">
        {icon}
        <h3>{title}</h3>
      </header>
      <div className="inspector-body">{children}</div>
    </aside>
  );
}
