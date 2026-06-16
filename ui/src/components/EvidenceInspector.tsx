import { AlertTriangle, ChevronLeft, ChevronRight, ClipboardCheck, Crosshair, Database, Info, Layers, MapPin, List, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { ChannelCatalogItem, PlatformEventItem, PlatformEventVisibilityMode, RunOverview } from "../types/telemetry";
import { buildWindowEvidence, buildZoneEvidence, hasWindowSelection } from "../utils/evidenceFocus";
import { filterPlatformEvents, platformEventScopeLabel, platformEventVisibilityModeLabel } from "../utils/platformEventVisibility";
import { ProxyBadge } from "./ProxyBadge";

type EvidenceInspectorProps = {
  overview: RunOverview | null;
  platformEvents: PlatformEventItem[];
  channels: ChannelCatalogItem[];
  collapsed?: boolean;
  onToggle?: () => void;
  eventVisibilityMode: PlatformEventVisibilityMode;
  onEventVisibilityModeChange?: (mode: PlatformEventVisibilityMode) => void;
  onToggleMapOverlay?: () => void;
};

function humanizeSelectionSource(source: ReturnType<typeof useTelemetrySelection>["selection"]["selectionSource"]): string {
  return source.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function humanizeValueBasis(valueBasis: ReturnType<typeof useTelemetrySelection>["selection"]["selectedValueBasis"]): string {
  switch (valueBasis) {
    case "selected_sample":
      return "Selected sample";
    case "selected_window":
      return "Selected window";
    case "full_lap":
      return "Full lap";
    case "run_level":
      return "Run-level";
    case "latest":
      return "Latest";
    default:
      return "Unavailable";
  }
}

export function EvidenceInspector({
  overview,
  platformEvents,
  channels,
  collapsed,
  onToggle,
  eventVisibilityMode,
  onEventVisibilityModeChange,
  onToggleMapOverlay,
}: EvidenceInspectorProps) {
  const { selection, selectEvent } = useTelemetrySelection();
  const [justAnchored, setJustAnchored] = useState(false);
  const prevEventRef = useRef<string | null | undefined>(null);
  const visiblePlatformEvents = useMemo(
    () => filterPlatformEvents(platformEvents, eventVisibilityMode),
    [platformEvents, eventVisibilityMode],
  );

  const selectedEvent = useMemo(
    () => visiblePlatformEvents.find((e) => e.event_id === selection.selectedEventId) ?? null,
    [visiblePlatformEvents, selection.selectedEventId],
  );

  const hiddenSelectedEvent = useMemo(
    () => selectedEvent == null && selection.selectedEventId != null
      ? platformEvents.find((e) => e.event_id === selection.selectedEventId) ?? null
      : null,
    [platformEvents, selectedEvent, selection.selectedEventId],
  );

  const selectedChannel = useMemo(
    () => channels.find((c) => c.name === selection.selectedChannel) ?? null,
    [channels, selection.selectedChannel],
  );

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
      <EventInspector event={selectedEvent} showAnchorBadge={true} collapsed={collapsed} onToggle={onToggle} onToggleMapOverlay={onToggleMapOverlay} />
    </div>
  );
  if (hiddenSelectedEvent) {
    return (
      <HiddenSelectedEventInspector
        event={hiddenSelectedEvent}
        eventVisibilityMode={eventVisibilityMode}
        onShowProxyInternal={onEventVisibilityModeChange ? () => onEventVisibilityModeChange("proxy") : undefined}
        onClearSelection={() => selectEvent(null, "manual")}
        collapsed={collapsed}
        onToggle={onToggle}
      />
    );
  }
  if (selectedChannel) return <ChannelInspector channel={selectedChannel} collapsed={collapsed} onToggle={onToggle} />;
  return <RunInspector overview={overview} channels={channels} collapsed={collapsed} onToggle={onToggle} />;
}

function HiddenSelectedEventInspector({
  event,
  eventVisibilityMode,
  onShowProxyInternal,
  onClearSelection,
  collapsed,
  onToggle,
}: {
  event: PlatformEventItem;
  eventVisibilityMode: PlatformEventVisibilityMode;
  onShowProxyInternal?: () => void;
  onClearSelection: () => void;
  collapsed?: boolean;
  onToggle?: () => void;
}) {
  return (
    <InspectorShell title="Hidden Event" icon={<Info size={16} />} collapsed={collapsed} onToggle={onToggle}>
      <div className="inspector-source-stack hidden-event-fallback">
        <h4>Selected event is hidden by current filter.</h4>
        <p className="inspector-source-item">
          {event.title} is currently outside {platformEventVisibilityModeLabel(eventVisibilityMode)} mode.
        </p>
        {event.reason_for_hidden && (
          <p className="inspector-source-item muted">Hidden by default: {event.reason_for_hidden}</p>
        )}
        <div className="diw-actions" style={{ marginTop: 6 }}>
          {onShowProxyInternal && (
            <button className="trackmap-action-btn" onClick={onShowProxyInternal} title="Show Proxy/Internal events">
              <Layers size={10} /> Show Proxy/Internal
            </button>
          )}
          <button className="trackmap-action-btn" onClick={onClearSelection} title="Clear selected hidden event">
            <ChevronRight size={10} /> Clear Selection
          </button>
        </div>
      </div>
    </InspectorShell>
  );
}

function RunInspector({ overview, channels, collapsed, onToggle }: { overview: RunOverview | null; channels: ChannelCatalogItem[]; collapsed?: boolean; onToggle?: () => void }) {
  const { selection, setWorkspace } = useTelemetrySelection();

  const channelCounts = useMemo(() => ({
    raw: channels.filter((c) => c.is_raw && !c.missing_status).length,
    calc: channels.filter((c) => c.is_calculated && !c.missing_status).length,
    proxy: channels.filter((c) => c.is_proxy).length,
    missing: channels.filter((c) => c.missing_status).length,
  }), [channels]);

  if (!overview) return <InspectorShell title="No Run Loaded" icon={<Database size={16} />} collapsed={collapsed} onToggle={onToggle} />;
  const activeZoneLabel = selection.selectedZoneLabel
    ?? (selection.selectedZoneStartPct != null && selection.selectedZoneEndPct != null
      ? `Zone ${selection.selectedZoneStartPct.toFixed(1)}-${selection.selectedZoneEndPct.toFixed(1)}%`
      : null);

  const { raw, calc, proxy, missing } = channelCounts;

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
      {hasWindowSelection(selection) && (
        <div className="inspector-source-stack">
          <h4>Window Scope</h4>
          <p className="inspector-source-item">
            Selected window: Laps {selection.selectedLapWindowStart}-{selection.selectedLapWindowEnd}
            {selection.selectedRepresentativeLap != null ? ` - Rep Lap ${selection.selectedRepresentativeLap}` : ""}
          </p>
          <p className="inspector-source-item muted">
            Basis: selected window. Lap-level tabs still anchor to the representative lap.
          </p>
        </div>
      )}
      <div className="inspector-source-stack">
        <h4>Current Focus</h4>
        <p className="inspector-source-item">Source: {humanizeSelectionSource(selection.selectionSource)}</p>
        {selection.selectedLapDistFt != null && (
          <p className="inspector-source-item">
            <MapPin size={12} /> {selection.selectedLapDistFt.toFixed(0)} ft
            {selection.selectedLapPct != null ? ` - ${selection.selectedLapPct.toFixed(1)}% lap` : ""}
          </p>
        )}
        {activeZoneLabel && (
          <p className="inspector-source-item">
            <Crosshair size={12} /> {activeZoneLabel}
          </p>
        )}
        {(selection.selectedZoneStartPct != null && selection.selectedZoneEndPct != null) && (
          <div className="diw-actions" style={{ marginTop: 6 }}>
            <button className="trackmap-action-btn" onClick={() => setWorkspace("laps", selection.selectionSource)} title="Review this area from Laps">
              <Crosshair size={10} /> Review in Laps
            </button>
          </div>
        )}
      </div>
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

function EventInspector({
  event,
  showAnchorBadge,
  collapsed,
  onToggle,
  onToggleMapOverlay,
}: {
  event: PlatformEventItem;
  showAnchorBadge?: boolean;
  collapsed?: boolean;
  onToggle?: () => void;
  onToggleMapOverlay?: () => void;
}) {
  const sevColour = event.severity === "critical" ? "#ef4444" : event.severity === "high" ? "#f97316" : event.severity === "watch" ? "#f59e0b" : "#38bdf8";
  const { selection, focusEvidence, setWorkspace } = useTelemetrySelection();
  const eventSource = selection.selectedEventId === event.event_id ? selection.selectionSource : "priority_stack";
  const eventWithinSelectedWindow = hasWindowSelection(selection)
    && event.lap != null
    && event.lap >= (selection.selectedLapWindowStart ?? Number.NEGATIVE_INFINITY)
    && event.lap <= (selection.selectedLapWindowEnd ?? Number.POSITIVE_INFINITY);
  const activeZoneLabel = selection.selectedZoneLabel
    ?? (selection.selectedZoneStartPct != null && selection.selectedZoneEndPct != null
      ? `Zone ${selection.selectedZoneStartPct.toFixed(1)}-${selection.selectedZoneEndPct.toFixed(1)}%`
      : null);

  const eventSampleIndex =
    typeof event.sample_index === "number" &&
    Number.isFinite(event.sample_index) &&
    event.sample_index >= 0
      ? event.sample_index
      : null;

  const eventHasLocation = eventSampleIndex != null || event.lap_dist_ft != null || event.lap_pct != null;

  const focusEventEvidence = useCallback((workspace?: "platform_trace") => {
    focusEvidence({
      runId: selection.selectedRunId,
      lapNumber: event.lap,
      ...buildWindowEvidence(selection, event.lap),
      ...buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null, preserveWithoutLapPct: true }),
      eventId: event.event_id,
      sampleIndex: eventSampleIndex,
      lapDistFt: event.lap_dist_ft,
      lapPct: event.lap_pct,
      trustTier: event.confidence ?? null,
      selectionSource: eventSource,
      lockState: eventHasLocation ? "locked" : "none",
      valueBasis: eventHasLocation ? "selected_sample" : "run_level",
    }, workspace);
  }, [event.event_id, event.lap, event.lap_dist_ft, event.lap_pct, eventSampleIndex, eventHasLocation, eventSource, focusEvidence, selection, event.confidence]);

  const handleOpenPlatform = useCallback(() => focusEventEvidence("platform_trace"), [focusEventEvidence]);
  const handleOpenMap = useCallback(() => {
    focusEventEvidence();
    onToggleMapOverlay?.();
  }, [focusEventEvidence, onToggleMapOverlay]);
  const handleOpenSetup = useCallback(() => {
    focusEvidence({
      runId: selection.selectedRunId,
      lapNumber: event.lap,
      ...buildWindowEvidence(selection, event.lap),
      ...buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null, preserveWithoutLapPct: true }),
      eventId: event.event_id,
      sampleIndex: eventSampleIndex,
      lapDistFt: event.lap_dist_ft,
      lapPct: event.lap_pct,
      trustTier: event.confidence ?? null,
      selectionSource: eventSource,
      lockState: eventHasLocation ? "locked" : "none",
      valueBasis: eventHasLocation ? "selected_sample" : "run_level",
    }, "setup_impact");
  }, [event, eventSampleIndex, eventHasLocation, eventSource, focusEvidence, selection]);

  const handleStageTest = useCallback(() => {
    setWorkspace("notebook", "priority_stack");
  }, [setWorkspace]);

  return (
    <InspectorShell title={event.title} icon={<Crosshair size={16} />} collapsed={collapsed} onToggle={onToggle}>
      <div className="inspector-source-stack">
        <h4>Current Evidence Anchor</h4>
        {showAnchorBadge && <span className="anchor-evidence-badge"><Crosshair size={10} /> Anchored Evidence</span>}
        <p className="inspector-source-item">
          Lap {event.lap ?? "n/a"}{eventSampleIndex != null ? ` - Sample ${eventSampleIndex}` : ""}{event.lap_dist_ft != null ? ` - ${event.lap_dist_ft.toFixed(0)} ft` : ""}
        </p>
      </div>

      <div className="inspector-source-stack">
        <h4>Where</h4>
        <p className="inspector-source-item">
          <MapPin size={12} /> Lap {event.lap ?? "n/a"}{event.lap_dist_ft != null ? ` - ${event.lap_dist_ft.toFixed(0)} ft` : ""}
        </p>
        {eventWithinSelectedWindow && (
          <p className="inspector-source-item muted">
            Parent window: Laps {selection.selectedLapWindowStart}-{selection.selectedLapWindowEnd}
            {event.lap != null ? ` - Rep Lap ${event.lap}` : ""}
          </p>
        )}
        {activeZoneLabel && (
          <p className="inspector-source-item muted">
            <Crosshair size={12} /> Area: {activeZoneLabel}
          </p>
        )}
        <p className="inspector-source-item muted">Source: {humanizeSelectionSource(eventSource)}</p>
      </div>

      <div className="inspector-source-stack">
        <h4>What</h4>
        <div className="inspector-meta">
          <span className="severity-badge" style={{ color: sevColour, borderColor: sevColour }}>
            <AlertTriangle size={12} /> {event.severity.toUpperCase()}
          </span>
          <span>Confidence: {event.confidence}</span>
          <span className="event-scope-pill">{platformEventScopeLabel(event)}</span>
          {event.is_proxy_based && <ProxyBadge kind="proxy" />}
        </div>
        <p className="inspector-source-item">{event.title}</p>
      </div>

      <div className="inspector-source-stack">
        <h4>Trust / Basis</h4>
        <p className="inspector-source-item">Value basis: {humanizeValueBasis(eventHasLocation ? "selected_sample" : "run_level")}</p>
        <p className="inspector-source-item">Confidence: {event.confidence ?? "Unavailable"}</p>
        {!event.is_visible_default && event.reason_for_hidden && (
          <p className="inspector-source-item muted">Hidden by default: {event.reason_for_hidden}</p>
        )}
        {event.is_proxy_based && <p className="inspector-source-item muted">Proxy/estimate evidence is active for this event.</p>}
      </div>

      <div className="inspector-source-stack">
        <h4>Event ID</h4>
        <p className="inspector-source-item">{event.event_id}</p>
      </div>

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

      <div className="inspector-source-stack">
        <h4>Related Telemetry Channels</h4>
        {event.channels_used.length > 0 ? (
          <p className="inspector-source-item">{event.channels_used.slice(0, 5).join(", ")}{event.channels_used.length > 5 ? ` +${event.channels_used.length - 5} more` : ""}</p>
        ) : (
          <p className="inspector-source-item muted">Unavailable. No garage setup value is implied from this event alone.</p>
        )}
      </div>

      <div className="inspector-source-stack">
        <h4>Actions</h4>
        <div className="diw-actions" style={{ marginTop: 4 }}>
          <button className="trackmap-action-btn" onClick={handleOpenPlatform} title="Open Platform">
            <Layers size={10} /> Open Platform
          </button>
          <button className="trackmap-action-btn" onClick={handleOpenMap} title="Show event on map overlay">
            <MapPin size={10} /> Map Overlay
          </button>
          <button className="trackmap-action-btn" onClick={handleOpenSetup} title="Open Setup with event focus">
            <Wrench size={10} /> Open Setup
          </button>
          {(selection.selectedZoneStartPct != null && selection.selectedZoneEndPct != null) && (
            <button className="trackmap-action-btn" onClick={() => setWorkspace("laps", eventSource)} title="Review this area from Laps">
              <Crosshair size={10} /> Review in Laps
            </button>
          )}
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
          {channel.is_proxy && <ProxyBadge kind="proxy" />}
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
      <button
        className="inspector-collapse-btn"
        onClick={onToggle}
        title={collapsed ? "Expand Inspector" : "Collapse Inspector"}
        aria-label={collapsed ? "Expand Inspector" : "Collapse Inspector"}
        aria-expanded={!collapsed}
      >
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
