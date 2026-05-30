import { AlertTriangle, ArrowRight, ChevronDown, ChevronLeft, ChevronRight, Gauge, Lightbulb, Shield, ShieldOff, Siren, ToggleLeft, Waves } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchPlatformEvents } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import {
  CATEGORY_LABELS, CATEGORY_ORDER, SEVERITY_ORDER,
  SEVERITY_COLOURS, eventWorkspace, eventLabel,
} from "../constants/ui";
import type { PlatformEventItem } from "../types/telemetry";
import type { EvidenceContext, Workspace } from "../store/types";
import { buildWindowEvidence, buildZoneEvidence } from "../utils/evidenceFocus";

type PriorityRailProps = {
  runId: string;
  selectedLap?: number | null;
  collapsed?: boolean;
  onToggle?: () => void;
  platformEvents?: PlatformEventItem[];
};

export function PriorityRail({ runId, selectedLap, collapsed, onToggle, platformEvents: externalEvents }: PriorityRailProps) {
  const { selection, setWorkspace, focusEvidence } = useTelemetrySelection();
  const [events, setEvents] = useState<PlatformEventItem[]>([]);
  const [showInvalid, setShowInvalid] = useState(false);

  useEffect(() => {
    if (externalEvents) {
      setEvents(externalEvents);
      return;
    }
    let cancelled = false;
    fetchPlatformEvents(runId, { lap: selectedLap ?? undefined })
      .then((e) => { if (!cancelled) setEvents(e); })
      .catch(() => { if (!cancelled) setEvents([]); });
    return () => { cancelled = true; };
  }, [runId, selectedLap, externalEvents]);

  const { valid, invalid } = useMemo(() => {
    const v: PlatformEventItem[] = [];
    const inv: PlatformEventItem[] = [];
    for (const e of events) {
      // Proxy-based events with very low confidence go to invalid
      if (e.severity === "info" && e.confidence === "low") {
        inv.push(e);
      } else {
        v.push(e);
      }
    }
    v.sort((a, b) => {
      const catA = CATEGORY_ORDER[CATEGORY_LABELS[a.event_type] ?? "Platform"] ?? 99;
      const catB = CATEGORY_ORDER[CATEGORY_LABELS[b.event_type] ?? "Platform"] ?? 99;
      if (catA !== catB) return catA - catB;
      const sevA = SEVERITY_ORDER[a.severity] ?? 99;
      const sevB = SEVERITY_ORDER[b.severity] ?? 99;
      return sevA - sevB;
    });
    return { valid: v, invalid: inv };
  }, [events]);

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
      ...buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null, preserveWithoutLapPct: true }),
      eventId: event.event_id,
      sampleIndex,
      lapDistFt: event.lap_dist_ft,
      lapPct: event.lap_pct,
      trustTier: selection.selectedTrustTier ?? null,
      lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
      valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
      selectionSource: "priority_stack",
    };
  }, [runId, selection]);

  const handleClick = useCallback((event: PlatformEventItem) => {
    focusEvidence(buildPriorityEvidence(event), eventWorkspace(event.event_type) as Parameters<typeof setWorkspace>[0]);
  }, [buildPriorityEvidence, focusEvidence, setWorkspace]);

  /** Map event type to a category icon for accessibility (color + icon). */
  const categoryIcon = (eventType: string, size = 12) => {
    const cat = CATEGORY_LABELS[eventType] ?? "";
    if (cat.includes("Platform") || cat.includes("Rear")) return <Gauge size={size} />;
    if (cat.includes("Speed")) return <Siren size={size} />;
    if (cat.includes("Drag") || cat.includes("Scrub")) return <Waves size={size} />;
    if (cat.includes("Shock")) return <ToggleLeft size={size} />;
    return <Shield size={size} />;
  };

  // ── decision-first suggestion ──────────────────────────────
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
      return { question: "What to test next?", action: "Create Test Note", workspace: "notebook" as const };
    }
    return { question: "Inspect in detail", action: "Open Platform Trace", workspace: "platform_trace" as const };
  }, [valid, selection]);

  return (
    <aside className={`priority-rail${collapsed ? " collapsed" : ""}`}>
      <button className="rail-collapse-btn" onClick={onToggle} title={collapsed ? "Expand Priority Rail" : "Collapse Priority Rail"}>
        {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
      <header className="rail-header">
        <h3>Priority Stack</h3>
        <span className="rail-count">{valid.length} events</span>
      </header>

      {/* decision-first next-action card */}
      <div className="rail-next-action">
        <div className="nbc-body" style={{ flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--muted)", fontSize: "0.68rem", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.5px" }}>
            <Lightbulb size={12} /> Next Action
          </span>
          <span className="nbc-question">{suggestion.question}</span>
          <button
            className="nbc-action"
            onClick={() => {
              if ("event" in suggestion && suggestion.event) {
                handleClick(suggestion.event);
              } else {
                setWorkspace(suggestion.workspace, "manual");
              }
            }}
          >
            <ArrowRight size={14} /> {suggestion.action}
          </button>
        </div>
      </div>

      <div className="rail-list">
        {valid.length === 0 && (
          <p className="rail-empty">No priority events for this lap.</p>
        )}
        {valid.map((event, idx) => (
          <button
            key={event.event_id}
            className={`priority-card ${selection.selectedEventId === event.event_id ? "active" : ""}`}
            onClick={() => handleClick(event)}
            aria-label={`${event.title}, ${event.severity}, ${event.lap_dist_ft != null ? `${Math.round(event.lap_dist_ft)} feet` : "unknown location"}`}
          >
            <span className="priority-rank">{idx + 1}</span>
            <span className="priority-colour" style={{ backgroundColor: SEVERITY_COLOURS[event.severity] ?? "#8d9aaa" }} />
            <div className="priority-body">
              <div className="priority-title-row">
                <strong>{event.title}</strong>
                {event.is_proxy_based && <span className="proxy-pill">PROXY</span>}
              </div>
              <span className="priority-category">{categoryIcon(event.event_type)} {CATEGORY_LABELS[event.event_type] ?? event.event_type}</span>
              <span className="priority-location">
                {event.lap_dist_ft != null ? `${event.lap_dist_ft.toFixed(0)} ft` : "Unknown location"}
              </span>
              <span className="priority-severity" style={{ color: SEVERITY_COLOURS[event.severity] }}>
                <AlertTriangle size={12} /> {event.severity.toUpperCase()}
              </span>
              <span className="priority-next">
                <ArrowRight size={12} /> Open {CATEGORY_LABELS[event.event_type] ?? "Trace"}
              </span>
            </div>
          </button>
        ))}
      </div>

      {invalid.length > 0 && (
        <div className="rail-invalid-section">
          <button className="rail-invalid-toggle" onClick={() => setShowInvalid(!showInvalid)}>
            {showInvalid ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <ShieldOff size={14} /> Invalid / Low Confidence ({invalid.length})
          </button>
          {showInvalid && (
            <div className="rail-list">
              {invalid.map((event) => (
                <button
                  key={event.event_id}
                  className="priority-card invalid"
                  onClick={() => handleClick(event)}
                  aria-label={`${event.title}, low confidence`}
                >
                  <span className="priority-colour" style={{ backgroundColor: "#6b7280" }} />
                  <div className="priority-body">
                    <strong>{event.title}</strong>
                    <span className="priority-category">{event.severity} · {event.confidence} confidence</span>
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
