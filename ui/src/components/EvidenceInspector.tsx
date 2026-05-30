import { AlertTriangle, ChevronLeft, ChevronRight, ClipboardCheck, Crosshair, Database, Info, Layers, MapPin, List, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { ChannelCatalogItem, PlatformEventItem, RunOverview } from "../types/telemetry";

type EvidenceInspectorProps = {
  overview: RunOverview | null;
  platformEvents: PlatformEventItem[];
  channels: ChannelCatalogItem[];
  collapsed?: boolean;
  onToggle?: () => void;
};

export function EvidenceInspector({ overview, platformEvents, channels, collapsed, onToggle }: EvidenceInspectorProps) {
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
      <EventInspector event={selectedEvent} showAnchorBadge={true} collapsed={collapsed} onToggle={onToggle} />
    </div>
  );
  if (selectedChannel) return <ChannelInspector channel={selectedChannel} collapsed={collapsed} onToggle={onToggle} />;
  return <RunInspector overview={overview} channels={channels} collapsed={collapsed} onToggle={onToggle} />;
}

function RunInspector({ overview, channels, collapsed, onToggle }: { overview: RunOverview | null; channels: ChannelCatalogItem[]; collapsed?: boolean; onToggle?: () => void }) {
  if (!overview) return <InspectorShell title="No Run Loaded" icon={<Database size={16} />} collapsed={collapsed} onToggle={onToggle} />;

  const { raw, calc, proxy, missing } = useMemo(() => ({
    raw: channels.filter((c) => c.is_raw && !c.missing_status).length,
    calc: channels.filter((c) => c.is_calculated && !c.missing_status).length,
    proxy: channels.filter((c) => c.is_proxy).length,
    missing: channels.filter((c) => c.missing_status).length,
  }), [channels]);

  return (
    <InspectorShell title="Run Overview" icon={<Info size={16} />} collapsed={collapsed} onToggle={onToggle}>
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
  const [open, setOpen] = useState(true);
  const recommendation = overview.recommendations?.[0];
  return (
    <details className="crew-chief-inline" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <ClipboardCheck size={14} /> Crew Chief
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

function EventInspector({ event, showAnchorBadge, collapsed, onToggle }: { event: PlatformEventItem; showAnchorBadge?: boolean; collapsed?: boolean; onToggle?: () => void }) {
  const sevColour = event.severity === "critical" ? "#ef4444" : event.severity === "high" ? "#f97316" : event.severity === "watch" ? "#f59e0b" : "#38bdf8";
  const { setWorkspace, selectLap, selectSample, selectEvent } = useTelemetrySelection();

  const handleOpenPlatform = useCallback(() => {
    if (event.lap != null) selectLap(event.lap);
    selectEvent(event.event_id, "priority_stack");
    if (typeof event.sample_index === "number" && Number.isFinite(event.sample_index) && event.sample_index >= 0) {
      selectSample(event.sample_index, event.lap_dist_ft ?? undefined, event.lap_pct ?? undefined, "priority_stack");
    }
    setWorkspace("platform_trace", "priority_stack");
  }, [event.event_id, event.lap, event.lap_dist_ft, event.lap_pct, event.sample_index, selectEvent, selectLap, selectSample, setWorkspace]);

  const handleOpenMap = useCallback(() => {
    if (event.lap != null) selectLap(event.lap);
    selectEvent(event.event_id, "priority_stack");
    if (typeof event.sample_index === "number" && Number.isFinite(event.sample_index) && event.sample_index >= 0) {
      selectSample(event.sample_index, event.lap_dist_ft ?? undefined, event.lap_pct ?? undefined, "priority_stack");
    }
    setWorkspace("map", "priority_stack");
  }, [event.event_id, event.lap, event.lap_dist_ft, event.lap_pct, event.sample_index, selectEvent, selectLap, selectSample, setWorkspace]);

  const handleStageTest = useCallback(() => {
    setWorkspace("notebook", "priority_stack");
  }, [setWorkspace]);

  return (
    <InspectorShell title={event.title} icon={<Crosshair size={16} />} collapsed={collapsed} onToggle={onToggle}>
      {showAnchorBadge && <span className="anchor-evidence-badge"><Crosshair size={10} /> Anchored Evidence</span>}

      {/* Source Stack: Where */}
      <div className="inspector-source-stack">
        <h4>Where</h4>
        <p className="inspector-source-item">
          <MapPin size={12} /> Lap {event.lap ?? "n/a"}{event.lap_dist_ft != null ? ` · ${event.lap_dist_ft.toFixed(0)} ft` : ""}
        </p>
      </div>

      {/* Source Stack: What */}
      <div className="inspector-source-stack">
        <h4>What</h4>
        <div className="inspector-meta">
          <span className="severity-badge" style={{ color: sevColour, borderColor: sevColour }}>
            <AlertTriangle size={12} /> {event.severity.toUpperCase()}
          </span>
          <span>Confidence: {event.confidence}</span>
          {event.is_proxy_based && <span className="proxy-pill">PROXY</span>}
        </div>
        <p className="inspector-source-item">{event.title}</p>
      </div>

      {/* Source Stack: Evidence */}
      {event.evidence.length > 0 && (
        <div className="inspector-source-stack">
          <h4>Evidence</h4>
          <ul>
            {event.evidence.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
          {event.primary_value != null && (
            <p className="inspector-source-item">
              <Database size={12} /> {event.primary_value.toFixed(3)} {event.primary_unit ?? ""}
            </p>
          )}
        </div>
      )}

      {/* Source Stack: Related Setup */}
      <div className="inspector-source-stack">
        <h4>Related Setup</h4>
        {event.channels_used.length > 0 ? (
          <p className="inspector-source-item">{event.channels_used.slice(0, 5).join(", ")}{event.channels_used.length > 5 ? ` +${event.channels_used.length - 5} more` : ""}</p>
        ) : (
          <p className="inspector-source-item muted">Unavailable</p>
        )}
      </div>

      {/* Source Stack: Decision */}
      <div className="inspector-source-stack">
        <h4>Decision</h4>
        <div className="diw-actions" style={{ marginTop: 4 }}>
          <button className="trackmap-action-btn" onClick={handleOpenPlatform} title="Open Platform">
            <Layers size={10} /> Platform
          </button>
          <button className="trackmap-action-btn" onClick={handleOpenMap} title="Open Map">
            <MapPin size={10} /> Map
          </button>
          <button className="trackmap-action-btn" onClick={() => setWorkspace("setup_impact")} title="Open Setup with event focus">
            <Wrench size={10} /> Setup
          </button>
          <button className="trackmap-action-btn" onClick={handleStageTest} title="Stage Test">
            <List size={10} /> Test
          </button>
        </div>
      </div>

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

function ChannelInspector({ channel, collapsed, onToggle }: { channel: ChannelCatalogItem; collapsed?: boolean; onToggle?: () => void }) {
  return (
    <InspectorShell title={channel.name} icon={<Database size={16} />} collapsed={collapsed} onToggle={onToggle}>
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

function InspectorShell({ title, icon, children, collapsed, onToggle }: { title: string; icon: React.ReactNode; children?: React.ReactNode; collapsed?: boolean; onToggle?: () => void }) {
  return (
    <aside className={`evidence-inspector${collapsed ? " collapsed" : ""}`}>
      <button className="inspector-collapse-btn" onClick={onToggle} title={collapsed ? "Expand Inspector" : "Collapse Inspector"}>
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
      <header className="inspector-header">
        {icon}
        <h3>{title}</h3>
      </header>
      <div className="inspector-body">{children}</div>
    </aside>
  );
}
