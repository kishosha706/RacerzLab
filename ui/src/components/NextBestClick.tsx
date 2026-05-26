import { ArrowRight, Lightbulb } from "lucide-react";
import { useMemo } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { eventWorkspace, eventLabel } from "../constants/ui";
import type { Workspace } from "../store/types";
import type { PlatformEventItem } from "../types/telemetry";

type NextBestClickProps = {
  runId: string;
  platformEvents: PlatformEventItem[];
};

export function NextBestClick({ runId, platformEvents }: NextBestClickProps) {
  const { selection, setWorkspace, selectEvent } = useTelemetrySelection();

  const suggestion = useMemo(() => {
    if (platformEvents.length === 0) {
      return { question: "No diagnostic events yet", action: "Import a run to begin analysis", workspace: "overview" as const };
    }

    // If no event selected, suggest the top-priority event
    if (!selection.selectedEventId) {
      const top = platformEvents[0];
      if (!top) return { question: "No events", action: "Check data coverage", workspace: "overview" as const };
      const ws = eventWorkspace(top.event_type) as Workspace;
      return {
        question: `What happened at ${top.lap_pct?.toFixed(1) ?? "?"}%?`,
        action: `Open ${eventLabel(top.event_type)}`,
        workspace: ws,
        eventId: top.event_id,
      };
    }

    // Event is selected — suggest next step
    const event = platformEvents.find((e) => e.event_id === selection.selectedEventId);
    if (!event) return { question: "Event not found", action: "Select another event", workspace: "overview" as const };

    const currentWs = selection.selectedWorkspace;

    if (currentWs === "platform_trace" || currentWs === "speed_delta" || currentWs === "drag_scrub") {
      return { question: "Which setup values relate to this?", action: "Open Setup Impact", workspace: "setup_impact" as const };
    }
    if (currentWs === "setup_impact") {
      return { question: "What should we test next?", action: "Create Test Note", workspace: "notebook" as const };
    }
    if (currentWs === "compare") {
      return { question: "Did the change work?", action: "Save Finding", workspace: "notebook" as const };
    }

    return { question: "Inspect this event in detail", action: "Open Platform Trace", workspace: "platform_trace" as const };
  }, [platformEvents, selection]);

  return (
    <div className="next-best-click">
      <Lightbulb size={14} />
      <div className="nbc-body">
        <span className="nbc-question">{suggestion.question}</span>
        <button
          className="nbc-action"
          onClick={() => {
            setWorkspace(suggestion.workspace, "manual");
            if ("eventId" in suggestion && suggestion.eventId) {
              selectEvent(suggestion.eventId, "priority_stack");
            }
          }}
        >
          <ArrowRight size={14} /> {suggestion.action}
        </button>
      </div>
    </div>
  );
}

// eventWorkspace and eventLabel moved to ../constants/ui
