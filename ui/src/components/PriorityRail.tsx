import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Gauge, Shield, ShieldOff, Siren, ToggleLeft, Waves } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { fetchPlatformEvents } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import {
  CATEGORY_LABELS, CATEGORY_ORDER, SEVERITY_ORDER,
  SEVERITY_COLOURS, eventWorkspace,
} from "../constants/ui";
import type { PlatformEventItem } from "../types/telemetry";

type PriorityRailProps = {
  runId: string;
  selectedLap?: number | null;
};

export function PriorityRail({ runId, selectedLap }: PriorityRailProps) {
  const { selection, selectEvent, setWorkspace } = useTelemetrySelection();
  const [events, setEvents] = useState<PlatformEventItem[]>([]);
  const [showInvalid, setShowInvalid] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchPlatformEvents(runId, { lap: selectedLap ?? undefined })
      .then((e) => { if (!cancelled) setEvents(e); })
      .catch(() => { if (!cancelled) setEvents([]); });
    return () => { cancelled = true; };
  }, [runId, selectedLap]);

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

  const handleClick = (event: PlatformEventItem) => {
    selectEvent(event.event_id, "priority_stack");
    const ws = eventWorkspace(event.event_type) as Parameters<typeof setWorkspace>[0];
    setWorkspace(ws, "priority_stack");
  };

  /** Map event type to a category icon for accessibility (color + icon). */
  const categoryIcon = (eventType: string, size = 12) => {
    const cat = CATEGORY_LABELS[eventType] ?? "";
    if (cat.includes("Platform") || cat.includes("Rear")) return <Gauge size={size} />;
    if (cat.includes("Speed")) return <Siren size={size} />;
    if (cat.includes("Drag") || cat.includes("Scrub")) return <Waves size={size} />;
    if (cat.includes("Shock")) return <ToggleLeft size={size} />;
    return <Shield size={size} />;
  };

  return (
    <aside className="priority-rail">
      <header className="rail-header">
        <h3>Priority Stack</h3>
        <span className="rail-count">{valid.length} events</span>
      </header>

      <div className="rail-list">
        {valid.length === 0 && (
          <p className="rail-empty">No diagnostic events yet. Import a run to populate the stack.</p>
        )}
        {valid.map((event, idx) => (
          <button
            key={event.event_id}
            className={`priority-card ${selection.selectedEventId === event.event_id ? "active" : ""}`}
            onClick={() => handleClick(event)}
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
                {event.lap_pct != null && `${event.lap_pct.toFixed(1)}%`}
                {event.lap_dist_ft != null && ` | ${event.lap_dist_ft.toFixed(0)} ft`}
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
