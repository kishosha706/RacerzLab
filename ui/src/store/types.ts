/**
 * UI mode — controls explanation verbosity and decision style.
 *
 * - ``"race"``      — Short, direct, decision-first. Minimal explanation.
 * - ``"learning"``  — Verbose, coaching style. Explains *why*.
 */
export type SelectionMode =
  | "race"
  | "compare"
  | "build_test"
  | "long_run"
  | "learning";

export type Workspace =
  | "overview"
  | "map"
  | "laps"
  | "platform_trace"
  | "speed_delta"
  | "drag_scrub"
  | "setup_impact"
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
  | "manual";

export type TelemetrySelection = {
  selectedRunId: string | null;
  selectedCompareRunId?: string | null;

  selectedLap?: number | null;
  selectedSampleIndex?: number | null;
  selectedLapDistFt?: number | null;
  selectedLapDistM?: number | null;
  selectedLapPct?: number | null;

  selectedEventId?: string | null;
  selectedChannel?: string | null;
  selectedSetupKey?: string | null;
  selectedZoneId?: string | null;

  /** Transient hover position — updated at high frequency, not committed to React state on every frame. */
  hoverLapPct?: number | null;
  hoverSampleIndex?: number | null;

  selectedMode: SelectionMode;
  selectedWorkspace: Workspace;
  selectionSource: SelectionSource;
};
