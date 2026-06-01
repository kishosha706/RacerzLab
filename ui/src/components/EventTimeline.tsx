import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Play, Pause, SkipBack, SkipForward } from "lucide-react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { SEVERITY_COLOURS, EVENT_SHAPES } from "../constants/ui";
import type { PlatformEventItem } from "../types/telemetry";
import { buildWindowEvidence, buildZoneEvidence } from "../utils/evidenceFocus";

type EventTimelineProps = {
  platformEvents: PlatformEventItem[];
};

const CLUSTER_THRESHOLD_PCT = 0.25;
const PLAYBACK_SPEEDS = [0.5, 1, 2] as const;

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
  const { selection, focusEvidence, setHover, setPlaybackActive } = useTelemetrySelection();
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const playbackRef = useRef<number | null>(null);
  const indexRef = useRef(0);
  const staggered = useMemo(() => staggerMarkers(platformEvents), [platformEvents]);

  // ── Playback logic ───────────────────────────────────────────
  const sorted = useMemo(
    () => [...platformEvents].filter((e) => e.lap_pct != null).sort((a, b) => (a.lap_pct ?? 0) - (b.lap_pct ?? 0)),
    [platformEvents],
  );

  useEffect(() => {
    setPlaybackActive(playing);
    return () => setPlaybackActive(false);
  }, [playing, setPlaybackActive]);

  const stepTo = useCallback((index: number) => {
    const event = sorted[index];
    if (!event) return;
    indexRef.current = index;
    setHover(event.lap_pct ?? null, typeof event.sample_index === "number" && Number.isFinite(event.sample_index) && event.sample_index >= 0 ? event.sample_index : null);
  }, [sorted, setHover]);

  const buildTimelineEvidence = useCallback((event: PlatformEventItem) => {
    const validSampleIdx = typeof event.sample_index === "number" && Number.isFinite(event.sample_index) && event.sample_index >= 0 ? event.sample_index : null;
    const hasLocation = validSampleIdx != null || event.lap_dist_ft != null || event.lap_pct != null;
    return {
      runId: selection.selectedRunId ?? null,
      lapNumber: event.lap,
      ...buildWindowEvidence(selection, event.lap),
      ...buildZoneEvidence(selection, { lapPct: event.lap_pct ?? null, preserveWithoutLapPct: true }),
      eventId: event.event_id,
      sampleIndex: validSampleIdx,
      lapDistFt: event.lap_dist_ft,
      lapPct: event.lap_pct,
      selectionSource: "event_timeline" as const,
      lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
      valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
    };
  }, [selection]);

  const commitEvent = useCallback((index: number) => {
    const event = sorted[index];
    if (!event) return;
    focusEvidence(buildTimelineEvidence(event), "platform_trace");
  }, [sorted, focusEvidence, buildTimelineEvidence]);

  const togglePlay = useCallback(() => {
    setPlaying((p) => !p);
  }, []);

  const stepPrev = useCallback(() => {
    setPlaying(false);
    const next = Math.max(0, indexRef.current - 1);
    commitEvent(next);
  }, [commitEvent]);

  const stepNext = useCallback(() => {
    setPlaying(false);
    const next = Math.min(sorted.length - 1, indexRef.current + 1);
    commitEvent(next);
  }, [sorted, commitEvent]);

  // Playback RAF loop
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
      const next = (indexRef.current + 1) % sorted.length;
      stepTo(next);
      if (next === 0) {
        // Looped — commit the last event and stop
        commitEvent(sorted.length - 1);
        setPlaying(false);
        return;
      }
      playbackRef.current = requestAnimationFrame(tick);
    };

    playbackRef.current = requestAnimationFrame(tick);
    return () => {
      if (playbackRef.current != null) cancelAnimationFrame(playbackRef.current);
    };
  }, [playing, speed, sorted, stepTo, commitEvent]);

  // Keyboard shortcut: Space to toggle play
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === " " && sorted.length > 0) {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [togglePlay, sorted]);

  if (platformEvents.length === 0) return null;

  const currentEvent = sorted[indexRef.current];

  return (
    <footer className="event-timeline">
      <div className="timeline-header">
        <span className="timeline-label">Lap Storyline</span>
        <span className="timeline-shortcuts">Esc clear · ←/→ events · L mode · Space play</span>
        <span className="timeline-lap">Lap {selection.selectedLap ?? "—"}</span>
      </div>

      {/* ── Playback controls ── */}
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
            {currentEvent.title}
          </span>
        )}
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
              aria-label={`${event.title}, ${event.severity}, ${left.toFixed(1)} percent lap`}
              onClick={() => {
                const idx = sorted.findIndex((e) => e.event_id === event.event_id);
                if (idx >= 0) indexRef.current = idx;
                focusEvidence(buildTimelineEvidence(event), "platform_trace");
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
