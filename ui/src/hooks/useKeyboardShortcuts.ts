import { useEffect } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { Workspace } from "../store/types";
import type { PlatformEventItem } from "../types/telemetry";
import { buildWindowEvidence, buildZoneEvidence } from "../utils/evidenceFocus";

/**
 * Global keyboard shortcuts for RacerZLab.
 *
 * Rules:
 * - Ignored while typing in input/textarea/select/contenteditable.
 * - Does not break browser shortcuts (Ctrl/Cmd combos pass through).
 */
export function useKeyboardShortcuts(
  platformEvents: PlatformEventItem[],
  openWorkspace: (ws: Workspace) => void,
  options?: {
    onTogglePriorityRail?: () => void;
    onToggleInspector?: () => void;
  },
) {
  const { selection, focusEvidence, setMode } = useTelemetrySelection();

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase() ?? "";
      if (tag === "input" || tag === "textarea" || tag === "select" || (e.target as HTMLElement)?.isContentEditable) {
        return; // ignore while typing
      }
      if (e.ctrlKey || e.metaKey) return; // pass browser shortcuts through

      const key = e.key;

      switch (key) {
        case "Escape":
          focusEvidence({ eventId: null, selectionSource: "manual" });
          break;
        case "[":
          options?.onTogglePriorityRail?.();
          break;
        case "]":
          options?.onToggleInspector?.();
          break;
        case "m":
        case "M":
          openWorkspace("map");
          break;
        case "p":
        case "P":
          openWorkspace("platform_trace");
          break;
        case "o":
        case "O":
          openWorkspace("overview");
          break;
        case "c":
        case "C":
          openWorkspace("compare");
          break;
        case "n":
        case "N":
          openWorkspace("notebook");
          break;
        case "l":
        case "L":
          setMode(selection.selectedMode === "learning" ? "race" : "learning");
          break;
        case "ArrowLeft":
        case "ArrowRight": {
          e.preventDefault();
          const dir = key === "ArrowLeft" ? -1 : 1;
          const filtered = platformEvents.filter((evt) => {
            if (!selection.selectedLap) return true;
            return (evt as any).lap === selection.selectedLap;
          });
          if (filtered.length === 0) return;
          const currentIdx = filtered.findIndex((evt) => evt.event_id === selection.selectedEventId);
          const nextIdx = currentIdx === -1 ? 0 : (currentIdx + dir + filtered.length) % filtered.length;
          const nextEvt = filtered[nextIdx];
          const validSampleIdx = typeof nextEvt.sample_index === "number" && Number.isFinite(nextEvt.sample_index) && nextEvt.sample_index >= 0 ? nextEvt.sample_index : null;
          const hasLocation = validSampleIdx != null || nextEvt.lap_dist_ft != null || nextEvt.lap_pct != null;
          focusEvidence({
            runId: selection.selectedRunId,
            lapNumber: nextEvt.lap ?? null,
            ...buildWindowEvidence(selection, nextEvt.lap),
            ...buildZoneEvidence(selection, { lapPct: nextEvt.lap_pct ?? null, preserveWithoutLapPct: true }),
            eventId: nextEvt.event_id,
            sampleIndex: validSampleIdx,
            lapDistFt: nextEvt.lap_dist_ft,
            lapPct: nextEvt.lap_pct,
            selectionSource: "event_timeline",
            lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
            valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
          }, "platform_trace");
          break;
        }
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [platformEvents, selection.selectedLap, selection.selectedMode, focusEvidence, setMode, openWorkspace, options]);
}
