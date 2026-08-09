import { AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Gauge, Lightbulb, LoaderCircle, SearchX, Shield, ShieldOff, Siren, ToggleLeft, Waves } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchPlatformEvents } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import {
  CATEGORY_LABELS, CATEGORY_ORDER, SEVERITY_ORDER,
  SEVERITY_COLOURS, eventWorkspace, eventLabel,
} from "../constants/ui";
import { ProxyBadge } from "./ProxyBadge";
import type { PlatformEventItem, PlatformEventVisibilityMode } from "../types/telemetry";
import type { EvidenceContext, Workspace } from "../store/types";
import { buildWindowEvidence, buildZoneEvidence } from "../utils/evidenceFocus";
import { filterPlatformEvents, isClearPlatformDiagnostic, isMutedPlatformEvent, platformEventScopeLabel } from "../utils/platformEventVisibility";

type PriorityRailProps = {
  runId: string;
  selectedLap?: number | null;
  collapsed?: boolean;
  onToggle?: () => void;
  collapseDisabled?: boolean;
  platformEvents?: PlatformEventItem[];
  loadStatus?: "idle" | "loading" | "ready" | "clear" | "unavailable" | "error";
  loadError?: string | null;
  eventVisibilityMode: PlatformEventVisibilityMode;
};

export function PriorityRail({
  runId,
  selectedLap,
  collapsed,
  onToggle,
  collapseDisabled = false,
  platformEvents: externalEvents,
  loadStatus = "ready",
  loadError,
  eventVisibilityMode,
}: PriorityRailProps) {
  const { selection, setWorkspace, focusEvidence } = useTelemetrySelection();
  const internalRequestKey = `${runId}:${selectedLap ?? "all"}`;
  const [internalEvents, setInternalEvents] = useState<{
    requestKey: string | null;
    events: PlatformEventItem[];
  }>({ requestKey: null, events: [] });
  const [showInvalid, setShowInvalid] = useState(false);

  useEffect(() => {
    if (externalEvents !== undefined) return;
    let cancelled = false;
    setInternalEvents({ requestKey: null, events: [] });
    fetchPlatformEvents(runId, { lap: selectedLap ?? undefined })
      .then((events) => {
        if (!cancelled) setInternalEvents({ requestKey: internalRequestKey, events });
      })
      .catch(() => {
        if (!cancelled) setInternalEvents({ requestKey: internalRequestKey, events: [] });
      });
    return () => { cancelled = true; };
  }, [runId, selectedLap, externalEvents, internalRequestKey]);

  const events = externalEvents !== undefined
    ? externalEvents
    : internalEvents.requestKey === internalRequestKey ? internalEvents.events : [];

  const visibleEvents = useMemo(
    () => filterPlatformEvents(events, eventVisibilityMode),
    [events, eventVisibilityMode],
  );
  const clearDiagnosticCount = useMemo(
    () => events.filter((event) => isClearPlatformDiagnostic(event)).length,
    [events],
  );
  const eventsRenderable = loadStatus === "ready" || (loadStatus === "clear" && eventVisibilityMode !== "actionable");
  const railStatus = loadStatus === "ready"
    ? { label: "Ready", tone: "attention" }
    : loadStatus === "clear"
      ? { label: "Clear", tone: "clear" }
      : loadStatus === "loading"
        ? { label: "Checking", tone: "loading" }
        : loadStatus === "error"
          ? { label: "Retry", tone: "blocked" }
          : loadStatus === "unavailable"
            ? { label: "Limited", tone: "blocked" }
            : { label: "Waiting", tone: "idle" };

  const { valid, invalid } = useMemo(() => {
    const v: PlatformEventItem[] = [];
    const inv: PlatformEventItem[] = [];
    for (const e of visibleEvents) {
      if (e.severity === "info" && e.confidence === "low") {
        inv.push(e);
      } else {
        v.push(e);
      }
    }
    v.sort((a, b) => {
      const sevA = SEVERITY_ORDER[a.severity] ?? 99;
      const sevB = SEVERITY_ORDER[b.severity] ?? 99;
      if (sevA !== sevB) return sevA - sevB;

      const selectedA = selection.selectedEventId != null && a.event_id === selection.selectedEventId ? -1 : 0;
      const selectedB = selection.selectedEventId != null && b.event_id === selection.selectedEventId ? -1 : 0;
      if (selectedA !== selectedB) return selectedA - selectedB;

      const lapDeltaA = selectedLap != null && a.lap != null ? Math.abs(a.lap - selectedLap) : 999;
      const lapDeltaB = selectedLap != null && b.lap != null ? Math.abs(b.lap - selectedLap) : 999;
      if (lapDeltaA !== lapDeltaB) return lapDeltaA - lapDeltaB;

      const catA = CATEGORY_ORDER[CATEGORY_LABELS[a.event_type] ?? "Platform"] ?? 99;
      const catB = CATEGORY_ORDER[CATEGORY_LABELS[b.event_type] ?? "Platform"] ?? 99;
      return catA - catB;
    });
    return { valid: v, invalid: inv };
  }, [selectedLap, selection.selectedEventId, visibleEvents]);

  const buildPriorityEvidence = useCallback((event: PlatformEventItem): Partial<EvidenceContext> => {
    const sampleIndex =
      typeof event.sample_index === "number" &&
      Number.isInteger(event.sample_index) &&
      event.sample_index >= 0
        ? event.sample_index
        : null;

    const hasLocation = sampleIndex != null || event.lap_dist_ft != null || event.lap_pct != null;

    return {
      runId,
      lapNumber: event.lap,
      ...buildWindowEvidence(selection, event.lap),
      ...buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null }),
      eventId: event.event_id,
      sampleIndex,
      lapDistFt: event.lap_dist_ft,
      lapPct: event.lap_pct,
      trustTier: event.confidence ?? null,
      lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
      valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
      selectionSource: "priority_stack",
    };
  }, [runId, selection]);

  const handleClick = useCallback((event: PlatformEventItem) => {
    focusEvidence(buildPriorityEvidence(event), eventWorkspace(event.event_type) as Parameters<typeof setWorkspace>[0]);
  }, [buildPriorityEvidence, focusEvidence, setWorkspace]);

  const secondaryWorkspace = useCallback((eventType: string): Workspace => {
    if (/TIRE|SHOCK|DAMPER|CAMBER|PRESSURE/i.test(eventType)) return "setup_impact";
    if (/SCRUB|SPEED|DRAG|YAW|STEER/i.test(eventType)) return "compare";
    return "map";
  }, []);

  const handleSecondaryAction = useCallback((event: PlatformEventItem) => {
    focusEvidence(buildPriorityEvidence(event), secondaryWorkspace(event.event_type));
  }, [buildPriorityEvidence, focusEvidence, secondaryWorkspace]);

  const categoryIcon = (eventType: string, size = 12) => {
    const cat = CATEGORY_LABELS[eventType] ?? "";
    if (cat.includes("Platform") || cat.includes("Rear")) return <Gauge size={size} />;
    if (cat.includes("Speed")) return <Siren size={size} />;
    if (cat.includes("Drag") || cat.includes("Scrub")) return <Waves size={size} />;
    if (cat.includes("Shock")) return <ToggleLeft size={size} />;
    return <Shield size={size} />;
  };

  const suggestion = useMemo(() => {
    if (valid.length === 0) {
      return { question: "No priority events", action: "Review Overview", workspace: "overview" as const };
    }
    if (!selection.selectedEventId) {
      const top = valid[0];
      const ws = eventWorkspace(top.event_type) as Workspace;
      return {
        question: `What happened at ${top.title}?`,
        action: `Open ${eventLabel(top.event_type)}`,
        workspace: ws,
        event: top,
      };
    }
    const event = valid.find((e) => e.event_id === selection.selectedEventId);
    if (!event) return { question: "Select an event", action: "Browse events", workspace: "overview" as const };
    const currentWs = selection.selectedWorkspace;
    if (currentWs === "platform_trace" || currentWs === "speed_delta" || currentWs === "drag_scrub") {
      return { question: "Which setup values relate?", action: "Open Setup", workspace: "setup_impact" as const };
    }
    if (currentWs === "setup_impact") {
      return { question: "Review the lap context?", action: "Open Laps", workspace: "laps" as const };
    }
    return { question: "Inspect in detail", action: "Open Platform Trace", workspace: "platform_trace" as const };
  }, [valid, selection]);

  return (
    <aside className={`priority-rail${collapsed ? " collapsed" : ""}`} aria-label="Priority evidence">
      <button
        type="button"
        className="rail-collapse-btn"
        onClick={onToggle}
        disabled={collapseDisabled}
        title={collapseDisabled ? "Priority Rail stays open until evidence is genuinely clear" : collapsed ? "Expand Priority Rail" : "Collapse Priority Rail"}
        aria-label={collapseDisabled ? "Priority Rail stays open until evidence is genuinely clear" : collapsed ? "Expand Priority Rail" : "Collapse Priority Rail"}
        aria-expanded={!collapsed}
      >
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
      <header className="rail-header">
        <span className="rail-heading-copy">
          <small>Evidence queue</small>
          <h3>Priority</h3>
        </span>
        <span className="rail-count" data-tone={railStatus.tone}>
          <i aria-hidden="true" /> {eventsRenderable ? `${valid.length} events` : railStatus.label}
        </span>
      </header>

      {eventsRenderable && <div className="rail-next-action">
        <div className="rail-next-action-body">
          <span className="rail-next-action-label">
            <Lightbulb size={12} /> Next Action
          </span>
          <span className="nbc-question">{suggestion.question}</span>
          <button
            type="button"
            className="nbc-action"
            onClick={() => {
              if ("event" in suggestion && suggestion.event) {
                handleClick(suggestion.event);
              } else {
                setWorkspace(suggestion.workspace, "manual");
              }
            }}
            aria-label={`Next action: ${suggestion.action}`}
          >
            <ArrowRight size={14} /> {suggestion.action}
          </button>
        </div>
      </div>}

      <div className="rail-list">
        {loadStatus === "error" && (
          <div className="rail-empty rail-state" data-state="error" role="alert">
            <span className="rail-state-icon" aria-hidden="true"><AlertTriangle size={18} /></span>
            <strong>Priority evidence unavailable</strong>
            <p>Platform events could not be loaded.</p>
            {selection.selectedMode === "learning" && loadError && (
              <p className="muted">Technical detail: {loadError}</p>
            )}
            <button type="button" className="secondary-button" onClick={() => setWorkspace("platform_trace", "manual")}>
              Open Platform to retry
            </button>
          </div>
        )}
        {loadStatus === "loading" && (
          <div className="rail-empty rail-state rail-loading-state" role="status" aria-live="polite" aria-busy="true">
            <span className="rail-state-icon" aria-hidden="true"><LoaderCircle size={18} /></span>
            <strong>Qualifying evidence</strong>
            <p>Checking the selected lap for supported platform events.</p>
            <span className="rail-loading-bars" aria-hidden="true"><i /><i /><i /></span>
          </div>
        )}
        {loadStatus === "unavailable" && (
          <div className="rail-empty rail-state" data-state="limited" role="status">
            <span className="rail-state-icon" aria-hidden="true"><ShieldOff size={18} /></span>
            <strong>Evidence is limited</strong>
            <p>Platform diagnostics unavailable.</p>
            <p className="muted">Missing evidence is not a clear result.</p>
            {selection.selectedMode === "learning" && loadError && <p className="muted">Needed evidence: {loadError}</p>}
          </div>
        )}
        {loadStatus === "clear" && !eventsRenderable && (
          <div className="rail-empty rail-state" data-state="clear" role="status">
            <span className="rail-state-icon" aria-hidden="true"><CheckCircle2 size={18} /></span>
            <strong>Supported checks are clear</strong>
            <p>Supported platform risk checks are clear for this eligible lap.</p>
            <p className="muted">{clearDiagnosticCount} qualified checks; no broader safety claim is implied.</p>
          </div>
        )}
        {eventsRenderable && valid.length === 0 && (
          <div className="rail-empty rail-state" data-state="empty" role="status">
            <span className="rail-state-icon" aria-hidden="true"><SearchX size={18} /></span>
            <strong>Nothing needs priority</strong>
            <p>{eventVisibilityMode === "actionable" ? "No actionable platform events for this lap." : "No platform events for this lap."}</p>
            {eventVisibilityMode === "actionable" && events.length > 0 && (
              <p className="muted">Internal evidence is still available for analysis.</p>
            )}
            {clearDiagnosticCount > 0 && (
              <p className="muted">{clearDiagnosticCount} qualified clear checks hidden.</p>
            )}
          </div>
        )}
        {eventsRenderable && valid.map((event, idx) => (
          <button
            type="button"
            key={event.event_id}
            className={`priority-card ${selection.selectedEventId === event.event_id ? "active" : ""}${isMutedPlatformEvent(event, eventVisibilityMode) ? " internal" : ""}`}
            data-severity={event.severity}
            data-active={selection.selectedEventId === event.event_id ? "true" : "false"}
            onClick={() => handleClick(event)}
            onDoubleClick={() => handleSecondaryAction(event)}
            onKeyDown={(keyEvent) => {
              if (keyEvent.key === "Enter" && keyEvent.shiftKey) {
                keyEvent.preventDefault();
                handleSecondaryAction(event);
              }
            }}
            aria-keyshortcuts="Shift+Enter"
            aria-pressed={selection.selectedEventId === event.event_id}
            aria-label={`${event.title}, ${event.severity}, ${event.lap_dist_ft != null ? `${Math.round(event.lap_dist_ft)} feet` : "unknown location"}`}
            title="Open evidence. Shift+Enter opens the related secondary view."
          >
            <span className="priority-rank" aria-hidden="true">{idx + 1}</span>
            <span className="priority-colour" aria-hidden="true" style={{ backgroundColor: SEVERITY_COLOURS[event.severity] ?? "#8d9aaa" }} />
            <div className="priority-body">
              <span className="priority-severity" style={{ color: SEVERITY_COLOURS[event.severity] }}>
                <AlertTriangle size={12} /> {event.severity.toUpperCase()}
              </span>
              <span className="priority-category">{categoryIcon(event.event_type)} {CATEGORY_LABELS[event.event_type] ?? event.event_type}</span>
              <span className="priority-location">
                Lap {event.lap ?? "n/a"} - {event.lap_dist_ft != null ? `${event.lap_dist_ft.toFixed(0)} ft` : "location unavailable"}
              </span>
              <div className="priority-title-row">
                <strong>{event.title}</strong>
              </div>
              {isMutedPlatformEvent(event, eventVisibilityMode) && (
                <span className="event-scope-pill">{platformEventScopeLabel(event)}</span>
              )}
              <span className="priority-recommendation">
                {event.recommended_action ?? event.reason_for_hidden ?? event.evidence?.[0] ?? "Open this event for detailed evidence."}
              </span>
              <span className="priority-next">
                <ArrowRight size={12} /> Open {CATEGORY_LABELS[event.event_type] ?? "Trace"}
              </span>
              {event.is_proxy_based && <ProxyBadge kind="proxy" />}
            </div>
          </button>
        ))}
      </div>

      {eventsRenderable && invalid.length > 0 && (
        <div className="rail-invalid-section">
          <button
            type="button"
            className="rail-invalid-toggle"
            onClick={() => setShowInvalid(!showInvalid)}
            aria-expanded={showInvalid}
            aria-controls="low-confidence-priority-events"
          >
            {showInvalid ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <ShieldOff size={14} /> Invalid / Low Confidence ({invalid.length})
          </button>
          {showInvalid && (
            <div id="low-confidence-priority-events" className="rail-list">
              {invalid.map((event) => (
                <button
                  type="button"
                  key={event.event_id}
                  className="priority-card invalid"
                  onClick={() => handleClick(event)}
                  aria-label={`${event.title}, low confidence`}
                >
                  <span className="priority-colour" style={{ backgroundColor: "#6b7280" }} />
                  <div className="priority-body">
                    <strong>{event.title}</strong>
                    <span className="priority-category">{event.severity} - {event.confidence} confidence</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
