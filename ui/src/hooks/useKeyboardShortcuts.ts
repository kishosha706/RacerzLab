import { useEffect } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { Workspace } from "../store/types";
import type { PlatformEventItem } from "../types/telemetry";

/**
 * Global keyboard shortcuts for RaceLab Garage.
 *
 * Rules:
 * - Ignored while typing in input/textarea/select/contenteditable.
 * - Does not break browser shortcuts (Ctrl/Cmd combos pass through).
 */
export function useKeyboardShortcuts(
  platformEvents: PlatformEventItem[],
  openWorkspace: (ws: Workspace) => void,
) {
  const { selection, selectEvent, selectSample, setMode } = useTelemetrySelection();

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
          selectEvent(null, "manual");
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
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            return (evt as any).lap === selection.selectedLap;
          });
          if (filtered.length === 0) return;
          const currentIdx = filtered.findIndex((evt) => evt.event_id === selection.selectedEventId);
          const nextIdx = currentIdx === -1 ? 0 : (currentIdx + dir + filtered.length) % filtered.length;
          const nextEvt = filtered[nextIdx];
          selectEvent(nextEvt.event_id, "event_timeline");
          if (nextEvt.sample_index != null) {
            selectSample(nextEvt.sample_index, nextEvt.lap_dist_ft ?? undefined, nextEvt.lap_pct ?? undefined, "event_timeline");
          }
          break;
        }
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [platformEvents, selection.selectedLap, selection.selectedMode, selectEvent, selectSample, setMode, openWorkspace]);
}
