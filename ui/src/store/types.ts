/**
 * UI mode — controls explanation verbosity and decision style.
 *
 * - ``"race"``      — Short, direct, decision-first. Minimal explanation.
 * - ``"learning"``  — Verbose, coaching style. Explains *why*.
 */
export type SelectionMode = "race" | "learning";

export type Workspace =
  | "overview"
  | "engineer"
  | "map"
  | "laps"
  | "platform_trace"
  | "speed_delta"
  | "drag_scrub"
  | "setup_impact"
  | "dial_in"
  | "compare"
  | "notebook"
  | "channels";

export type SelectionSource =
  | "priority_stack"
  | "event_timeline"
  | "track_map"
  | "trace_cursor"
  | "setup_table"
  | "channel_catalog"
  | "compare_verdict"
  | "overview"
  | "engineer"
  | "laps"
  | "manual";

/** Describes what grain of data the current value represents. */
export type LapScope = "single_lap" | "lap_window" | "run" | "track_zone" | "unknown";

/** Describes the lock state of a cursor selection. */
export type LockState = "none" | "hover" | "locked" | "playback";

/** Describes what data the current UI value reflects. */
export type ValueBasis =
  | "selected_sample"
  | "selected_window"
  | "latest"
  | "full_lap"
  | "run_level"
  | "unavailable";

/** Compare role for current evidence context. */
export type CompareRole = "baseline" | "test" | null;

/**
 * Canonical evidence context — one place to answer what the UI is
 * currently inspecting and at what data grain.
 */
export interface EvidenceContext {
  runId: string | null;
  lapNumber: number | null;
  lapScope: LapScope;
  /** For lap_window scope: window start lap */
  lapWindowStart?: number | null;
  /** For lap_window scope: window end lap */
  lapWindowEnd?: number | null;
  /** For lap_window scope: representative lap used to anchor lap-level tabs. */
  representativeLap?: number | null;
  eventId: string | null;
  producerId?: string | null;
  artifactId?: string | null;
  sampleIndex: number | null;
  lapDistFt: number | null;
  lapPct: number | null;
  zoneId: string | null;
  zoneLabel?: string | null;
  zoneStartPct?: number | null;
  zoneEndPct?: number | null;
  channelId: string | null;
  system: string | null;
  selectionSource: SelectionSource;
  lockState: LockState;
  trustTier: string | null;
  compareRole: CompareRole;
  sourceRunId?: string | null;
  sourceSetupId?: string | null;
  valueBasis: ValueBasis;
}

export type TelemetrySelection = {
  selectedRunId: string | null;
  selectedCompareRunId?: string | null;

  selectedLap?: number | null;
  /** Lap scope — what grain the current lap selection represents. */
  selectedLapScope?: LapScope;
  /** Window start lap when lapScope is "lap_window". */
  selectedLapWindowStart?: number | null;
  /** Window end lap when lapScope is "lap_window". */
  selectedLapWindowEnd?: number | null;
  /** Representative lap used to anchor lap-level tabs for lap windows. */
  selectedRepresentativeLap?: number | null;
  selectedSampleIndex?: number | null;
  selectedLapDistFt?: number | null;
  selectedLapPct?: number | null;
  /** What data basis the current selection reflects. */
  selectedValueBasis?: ValueBasis;
  /** Lock state of the current cursor/selection. */
  selectedLockState?: LockState;
  /** Trust tier of the currently focused evidence. */
  selectedTrustTier?: string | null;

  selectedEventId?: string | null;
  selectedProducerId?: string | null;
  selectedArtifactId?: string | null;
  selectedSystem?: string | null;
  selectedCompareRole?: CompareRole;
  selectedSourceRunId?: string | null;
  selectedSourceSetupId?: string | null;
  selectedChannel?: string | null;
  selectedSetupKey?: string | null;
  selectedZoneId?: string | null;
  selectedZoneLabel?: string | null;
  selectedZoneStartPct?: number | null;
  selectedZoneEndPct?: number | null;

  /** Transient hover position — updated at high frequency, not committed to React state on every frame. */
  hoverLapPct?: number | null;
  hoverSampleIndex?: number | null;
  playbackActive?: boolean;

  selectedMode: SelectionMode;
  selectedWorkspace: Workspace;
  selectionSource: SelectionSource;
};
