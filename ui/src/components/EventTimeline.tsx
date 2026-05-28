import { useMemo } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { SEVERITY_COLOURS, EVENT_SHAPES } from "../constants/ui";
import type { PlatformEventItem } from "../types/telemetry";

type EventTimelineProps = {
  platformEvents: PlatformEventItem[];
};

const CLUSTER_THRESHOLD_PCT = 0.25;

/** Assign staggered vertical offsets to events that cluster within threshold. */
type StaggeredEvent = PlatformEventItem & { staggerOffset: number; _lapPct: number };

function staggerMarkers(events: PlatformEventItem[]): StaggeredEvent[] {
  const withPct = events
    .filter((e) => e.lap_pct != null)
    .map((e) => ({ ...e, _lapPct: e.lap_pct! }));

  // Sort by lap_pct
  withPct.sort((a, b) => a._lapPct - b._lapPct);

  const result: StaggeredEvent[] = [];
  let clusterStart = 0;

  for (let i = 0; i < withPct.length; i++) {
    // Detect cluster boundary
    if (i === withPct.length - 1 || withPct[i + 1]._lapPct - withPct[i]._lapPct > CLUSTER_THRESHOLD_PCT) {
      const clusterSize = i - clusterStart + 1;
      for (let j = clusterStart; j <= i; j++) {
        // Offset within cluster: center around 0, spread by 10px per item
        const offset = (j - clusterStart - (clusterSize - 1) / 2) * 10;
        result.push({ ...withPct[j], staggerOffset: offset });
      }
      clusterStart = i + 1;
    }
  }

  return result;
}

export function EventTimeline({ platformEvents }: EventTimelineProps) {
  const { selection, selectEvent, setWorkspace, selectSample } = useTelemetrySelection();

  const staggered = useMemo(() => staggerMarkers(platformEvents), [platformEvents]);

  if (platformEvents.length === 0) return null;

  return (
    <footer className="event-timeline">
      <div className="timeline-header">
        <span className="timeline-label">Lap Storyline</span>
        <span className="timeline-lap">Lap {selection.selectedLap ?? "—"}</span>
      </div>
      <div className="timeline-track">
        {/* percentage markers */}
        {[0, 25, 50, 75, 100].map((pct) => (
          <span key={pct} className="timeline-pct-marker" style={{ left: `${pct}%` }}>
            <span className="timeline-pct-label">{pct}%</span>
            <span className="timeline-pct-tick" />
          </span>
        ))}

        {/* event markers with staggering */}
        {staggered.map((event) => {
          const left = Math.max(0, Math.min(100, event._lapPct));
          const isActive = selection.selectedEventId === event.event_id;
          const colour = SEVERITY_COLOURS[event.severity] ?? "#8d9aaa";
          const shape = EVENT_SHAPES[event.event_type] ?? "●";

          return (
            <button
              key={event.event_id}
              className={`timeline-marker ${isActive ? "active" : ""}`}
              style={{ left: `${left}%`, top: `${event.staggerOffset}px`, color: colour }}
              title={`${event.title} — ${event.severity}`}
              onClick={() => {
                selectEvent(event.event_id, "event_timeline");
                if (event.sample_index != null) {
                  selectSample(event.sample_index, event.lap_dist_ft ?? undefined, event.lap_pct ?? undefined, "event_timeline");
                }
                setWorkspace("platform_trace", "event_timeline");
              }}
            >
              <span className="timeline-shape" style={{ color: colour }}>{shape}</span>
            </button>
          );
        })}
      </div>
    </footer>
  );
}
