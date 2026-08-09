import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Play, Pause, SkipBack, SkipForward } from "lucide-react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { TelemetrySelection, Workspace } from "../store/types";
import { SEVERITY_COLOURS, EVENT_SHAPES } from "../constants/ui";
import type { PlatformEventItem, PlatformEventVisibilityMode } from "../types/telemetry";
import { buildWindowEvidence, buildZoneEvidence, lapPctInRange } from "../utils/evidenceFocus";
import { filterPlatformEvents, isMutedPlatformEvent, platformEventScopeLabel } from "../utils/platformEventVisibility";

type EventTimelineProps = {
  platformEvents: PlatformEventItem[];
  eventVisibilityMode: PlatformEventVisibilityMode;
  workspace: Workspace;
  onKeyboardOwnershipChange?: (ownsKeyboard: boolean) => void;
};

const CLUSTER_THRESHOLD_PCT = 0.25;
const PLAYBACK_SPEEDS = [0.5, 1, 2] as const;
const TRACE_HEAVY_WORKSPACES: ReadonlySet<Workspace> = new Set([
  "platform_trace",
  "speed_delta",
  "drag_scrub",
]);

type StaggeredEvent = PlatformEventItem & { staggerOffset: number; _lapPct: number };

function staggerMarkers(events: PlatformEventItem[]): StaggeredEvent[] {
  const withPct = events
    .filter((e) => e.lap_pct != null)
    .map((e) => ({ ...e, _lapPct: e.lap_pct! }));

  withPct.sort((a, b) => a._lapPct - b._lapPct);

  const result: StaggeredEvent[] = [];
  let clusterStart = 0;

  for (let i = 0; i < withPct.length; i++) {
    if (i === withPct.length - 1 || withPct[i + 1]._lapPct - withPct[i]._lapPct > CLUSTER_THRESHOLD_PCT) {
      const clusterSize = i - clusterStart + 1;
      for (let j = clusterStart; j <= i; j++) {
        const offset = (j - clusterStart - (clusterSize - 1) / 2) * 10;
        result.push({ ...withPct[j], staggerOffset: offset });
      }
      clusterStart = i + 1;
    }
  }

  return result;
}

function timelineEventLocationLabel(event: PlatformEventItem, selection: TelemetrySelection): string {
  if (
    selection.selectedZoneLabel
    && lapPctInRange(event.lap_pct, selection.selectedZoneStartPct, selection.selectedZoneEndPct)
  ) {
    return selection.selectedZoneLabel;
  }
  if (event.lap_dist_ft != null) return `${Math.round(event.lap_dist_ft).toLocaleString()} ft`;
  return "location unavailable";
}

export function EventTimeline({ platformEvents, eventVisibilityMode, workspace, onKeyboardOwnershipChange }: EventTimelineProps) {
  const { selection, focusEvidence, setHover, setPlaybackActive } = useTelemetrySelection();
  const [browseIndex, setBrowseIndex] = useState<number | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const [expanded, setExpanded] = useState(() => TRACE_HEAVY_WORKSPACES.has(workspace));
  const [focusWithin, setFocusWithin] = useState(false);
  const timelineRef = useRef<HTMLElement | null>(null);
  const playbackRef = useRef<number | null>(null);
  const indexRef = useRef(0);
  const visibleEvents = useMemo(
    () => filterPlatformEvents(platformEvents, eventVisibilityMode),
    [platformEvents, eventVisibilityMode],
  );
  const staggered = useMemo(() => staggerMarkers(visibleEvents), [visibleEvents]);
  const traceHeavy = TRACE_HEAVY_WORKSPACES.has(workspace);
  const eventScopeKey = useMemo(() => JSON.stringify({
    run_id: selection.selectedRunId ?? null,
    lap: selection.selectedLap ?? null,
    visibility: eventVisibilityMode,
    events: visibleEvents.map((event) => [
      event.event_id,
      event.lap ?? null,
      event.lap_pct ?? null,
      event.sample_index ?? null,
      event.lap_dist_ft ?? null,
      event.event_type,
    ]),
  }), [eventVisibilityMode, selection.selectedLap, selection.selectedRunId, visibleEvents]);
  const ownsKeyboard = expanded && focusWithin && visibleEvents.length > 0;

  const sorted = useMemo(
    () => [...visibleEvents].filter((e) => e.lap_pct != null).sort((a, b) => (a.lap_pct ?? 0) - (b.lap_pct ?? 0)),
    [visibleEvents],
  );

  useEffect(() => {
    setPlaybackActive(playing);
    return () => setPlaybackActive(false);
  }, [playing, setPlaybackActive]);

  useEffect(() => {
    setExpanded(TRACE_HEAVY_WORKSPACES.has(workspace));
  }, [workspace]);

  useEffect(() => {
    if (!expanded) {
      setPlaying(false);
      setBrowseIndex(null);
      setHoveredIndex(null);
      setHover(null, null);
    }
  }, [expanded, setHover]);

  useEffect(() => {
    onKeyboardOwnershipChange?.(ownsKeyboard);
    return () => onKeyboardOwnershipChange?.(false);
  }, [onKeyboardOwnershipChange, ownsKeyboard]);

  const setPreviewHover = useCallback((event: PlatformEventItem | null) => {
    if (!event) {
      setHover(null, null);
      return;
    }
    const sampleIndex =
      typeof event.sample_index === "number" && Number.isFinite(event.sample_index) && event.sample_index >= 0
        ? event.sample_index
        : null;
    setHover(event.lap_pct ?? null, sampleIndex);
  }, [setHover]);

  useEffect(() => {
    if (playbackRef.current != null) {
      cancelAnimationFrame(playbackRef.current);
      playbackRef.current = null;
    }
    indexRef.current = 0;
    setPlaying(false);
    setBrowseIndex(null);
    setHoveredIndex(null);
    setPreviewHover(null);
    setPlaybackActive(false);
  }, [eventScopeKey, setPlaybackActive, setPreviewHover]);

  const stepTo = useCallback((index: number) => {
    const event = sorted[index];
    if (!event) return;
    indexRef.current = index;
    setBrowseIndex(index);
    setHoveredIndex(null);
    setPreviewHover(event);
  }, [sorted, setPreviewHover]);

  const buildTimelineEvidence = useCallback((event: PlatformEventItem) => {
    const validSampleIdx = typeof event.sample_index === "number" && Number.isFinite(event.sample_index) && event.sample_index >= 0 ? event.sample_index : null;
    const hasLocation = validSampleIdx != null || event.lap_dist_ft != null || event.lap_pct != null;
    return {
      runId: selection.selectedRunId ?? null,
      lapNumber: event.lap,
      ...buildWindowEvidence(selection, event.lap),
      ...buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null }),
      eventId: event.event_id,
      sampleIndex: validSampleIdx,
      lapDistFt: event.lap_dist_ft,
      lapPct: event.lap_pct,
      trustTier: event.confidence ?? null,
      selectionSource: "event_timeline" as const,
      lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
      valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
    };
  }, [selection]);

  const commitEvent = useCallback((index: number) => {
    const event = sorted[index];
    if (!event) return;
    indexRef.current = index;
    setBrowseIndex(index);
    setHoveredIndex(null);
    focusEvidence(buildTimelineEvidence(event));
  }, [sorted, focusEvidence, buildTimelineEvidence]);

  const togglePlay = useCallback(() => {
    if (sorted.length === 0) return;
    setPlaying((p) => {
      if (p) return false;
      if (indexRef.current >= sorted.length - 1) {
        stepTo(0);
      }
      return true;
    });
  }, [sorted.length, stepTo]);

  const stepPrev = useCallback(() => {
    setPlaying(false);
    const next = Math.max(0, indexRef.current - 1);
    stepTo(next);
  }, [stepTo]);

  const stepNext = useCallback(() => {
    setPlaying(false);
    const next = Math.min(sorted.length - 1, indexRef.current + 1);
    stepTo(next);
  }, [sorted.length, stepTo]);

  useEffect(() => {
    if (!playing || sorted.length === 0) {
      if (playbackRef.current != null) {
        cancelAnimationFrame(playbackRef.current);
        playbackRef.current = null;
      }
      return;
    }

    let lastTime = performance.now();
    const intervalMs = 1000 / speed;

    const tick = (now: number) => {
      if (now - lastTime < intervalMs) {
        playbackRef.current = requestAnimationFrame(tick);
        return;
      }
      lastTime = now;
      const next = indexRef.current + 1;
      if (next >= sorted.length) {
        setPlaying(false);
        playbackRef.current = null;
        return;
      }
      stepTo(next);
      playbackRef.current = requestAnimationFrame(tick);
    };

    playbackRef.current = requestAnimationFrame(tick);
    return () => {
      if (playbackRef.current != null) cancelAnimationFrame(playbackRef.current);
    };
  }, [playing, speed, sorted, stepTo, commitEvent]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!expanded || !timelineRef.current?.contains(document.activeElement)) return;
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (sorted.length === 0) return;
      if (e.target instanceof HTMLElement && e.target.closest("select, [contenteditable='true']")) return;
      const buttonOwnsActivation = e.target instanceof HTMLElement && e.target.closest("button") != null;

      if (e.key === " ") {
        if (buttonOwnsActivation) return;
        e.preventDefault();
        togglePlay();
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setPlaying(false);
        stepTo(Math.max(0, indexRef.current - 1));
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        setPlaying(false);
        stepTo(Math.min(sorted.length - 1, indexRef.current + 1));
        return;
      }
      if (e.key === "Enter") {
        if (buttonOwnsActivation) return;
        e.preventDefault();
        setPlaying(false);
        commitEvent(indexRef.current);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setPlaying(false);
        setHoveredIndex(null);
        setBrowseIndex(null);
        setHover(null, null);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [expanded, togglePlay, sorted, stepTo, commitEvent, setHover]);

  useEffect(() => {
    if (sorted.length === 0) {
      indexRef.current = 0;
      setBrowseIndex(null);
      setHoveredIndex(null);
      return;
    }

    const selectedIndex = selection.selectedEventId == null
      ? -1
      : sorted.findIndex((event) => event.event_id === selection.selectedEventId);
    if (selectedIndex >= 0 && browseIndex == null && hoveredIndex == null) {
      indexRef.current = selectedIndex;
    } else if (indexRef.current >= sorted.length) {
      indexRef.current = sorted.length - 1;
    }
  }, [sorted, selection.selectedEventId, browseIndex, hoveredIndex]);

  if (visibleEvents.length === 0) return null;

  const selectedIndex = selection.selectedEventId == null
    ? -1
    : sorted.findIndex((event) => event.event_id === selection.selectedEventId);
  const previewIndex = hoveredIndex ?? browseIndex;
  const currentIndex = previewIndex ?? (selectedIndex >= 0 ? selectedIndex : indexRef.current);
  const currentEvent = sorted[currentIndex];

  return (
    <footer
      ref={timelineRef}
      className={`event-timeline${expanded ? " expanded" : " compact"}`}
      data-workspace={workspace}
      data-event-timeline-keyboard-owner={ownsKeyboard ? "true" : "false"}
      tabIndex={expanded ? 0 : -1}
      aria-label="Lap event storyline"
      onFocusCapture={() => setFocusWithin(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setFocusWithin(false);
      }}
    >
      <div className="timeline-header">
        <button
          type="button"
          className="timeline-collapse-toggle"
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          aria-controls="event-timeline-details"
          aria-label={`${expanded ? "Collapse" : "Expand"} lap storyline`}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          <span className="timeline-label">{traceHeavy ? "Lap Storyline" : "Lap Context"}</span>
          <span className="timeline-event-count">{sorted.length} events</span>
        </button>
        {expanded && <span className="timeline-shortcuts">Esc clear preview - Left/Right browse - Enter commit - Space play</span>}
        <span className="timeline-lap">Lap {selection.selectedLap ?? "-"}</span>
      </div>

      <div id="event-timeline-details" className="timeline-details" hidden={!expanded}>
          <div className="playback-controls">
            <button className="playback-btn" onClick={stepPrev} title="Previous event" aria-label="Previous event">
              <SkipBack size={14} />
            </button>
            <button className="playback-btn playback-btn-play" onClick={togglePlay} title={playing ? "Pause" : "Play"} aria-label={playing ? "Pause playback" : "Start playback"}>
              {playing ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <button className="playback-btn" onClick={stepNext} title="Next event" aria-label="Next event">
              <SkipForward size={14} />
            </button>
            <div className="playback-speed">
              {PLAYBACK_SPEEDS.map((s) => (
                <button
                  key={s}
                  className={`playback-speed-btn${speed === s ? " active" : ""}`}
                  onClick={() => setSpeed(s)}
                  aria-label={`${s}x speed`}
                >
                  {s}x
                </button>
              ))}
            </div>
            {currentEvent && (
              <span className="playback-location" title={currentEvent.title} aria-live="polite">
                {currentEvent.title} · {timelineEventLocationLabel(currentEvent, selection)}
              </span>
            )}
          </div>

          <div className="timeline-track">
            {[0, 25, 50, 75, 100].map((pct) => (
              <span key={pct} className="timeline-pct-marker" style={{ left: `${pct}%` }}>
                <span className="timeline-pct-label">{pct}%</span>
                <span className="timeline-pct-tick" />
              </span>
            ))}

            {staggered.map((event) => {
              const left = Math.max(0, Math.min(100, event._lapPct));
              const isActive = selection.selectedEventId === event.event_id;
              const isBrowsed = previewIndex != null && sorted[previewIndex]?.event_id === event.event_id;
              const colour = SEVERITY_COLOURS[event.severity] ?? "#8d9aaa";
              const shape = EVENT_SHAPES[event.event_type] ?? "*";
              const muted = isMutedPlatformEvent(event, eventVisibilityMode);
              const locationLabel = timelineEventLocationLabel(event, selection);

              return (
                <button
                  key={event.event_id}
                  className={`timeline-marker${isActive ? " active" : ""}${isBrowsed ? " browsed" : ""}${muted ? " muted" : ""}`}
                  style={{ left: `${left}%`, top: `${event.staggerOffset}px`, color: colour }}
                  title={`${event.title} - ${locationLabel} - ${left.toFixed(1)} percent lap - ${platformEventScopeLabel(event)} - ${event.severity}`}
                  aria-label={`${event.title}, ${locationLabel}, ${platformEventScopeLabel(event)}, ${event.severity}`}
                  onClick={() => {
                    const idx = sorted.findIndex((e) => e.event_id === event.event_id);
                    if (idx >= 0) commitEvent(idx);
                  }}
                  onMouseEnter={() => {
                    const idx = sorted.findIndex((e) => e.event_id === event.event_id);
                    if (idx >= 0) {
                      setHoveredIndex(idx);
                      setPreviewHover(event);
                    }
                  }}
                  onMouseLeave={() => {
                    setHoveredIndex(null);
                    if (browseIndex != null) {
                      setPreviewHover(sorted[browseIndex] ?? null);
                    } else {
                      setHover(null, null);
                    }
                  }}
                >
                  <span className="timeline-shape" style={{ color: colour }}>{shape}</span>
                </button>
              );
            })}
          </div>
      </div>
    </footer>
  );
}
