import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import type { EvidenceContext, SelectionMode, SelectionSource, TelemetrySelection, Workspace } from "./types";

const VALID_WORKSPACES: Workspace[] = ["overview", "engineer", "map", "laps", "platform_trace", "speed_delta", "drag_scrub", "setup_impact", "dial_in", "compare", "notebook", "channels"];

function normalizeWorkspace(workspace: Workspace): Workspace {
  if (workspace === "compare") return "laps";
  if (workspace === "map") return "overview";
  if (workspace === "notebook") return "overview";
  return workspace;
}

function loadLastWorkspace(): Workspace {
  try {
    const saved = localStorage.getItem("racelab_last_workspace");
    if (saved && VALID_WORKSPACES.includes(saved as Workspace)) return normalizeWorkspace(saved as Workspace);
  } catch { /* ignore */ }
  return "overview";
}

const DEFAULT_SELECTION: TelemetrySelection = {
  selectedRunId: null,
  selectedMode: "race",
  selectedWorkspace: loadLastWorkspace(),
  selectionSource: "manual",
  selectedValueBasis: "unavailable",
  selectedLockState: "none",
  selectedLapScope: "unknown",
  selectedTrustTier: null,
  selectedZoneId: null,
  selectedZoneLabel: null,
  selectedZoneStartPct: null,
  selectedZoneEndPct: null,
};

type SelectionAction =
  | { type: "SELECT_RUN"; runId: string | null }
  | { type: "SELECT_COMPARE_RUN"; runId: string | null }
  | { type: "SELECT_LAP"; lap: number | null }
  | { type: "SELECT_SAMPLE"; sampleIndex: number; lapDistFt?: number; lapPct?: number; source: SelectionSource }
  | { type: "SELECT_EVENT"; eventId: string | null; source: SelectionSource }
  | { type: "SELECT_CHANNEL"; channel: string | null; source: SelectionSource }
  | { type: "SELECT_SETUP_KEY"; setupKey: string | null }
  | { type: "SET_MODE"; mode: SelectionMode }
  | { type: "SET_WORKSPACE"; workspace: Workspace; source: SelectionSource }
  | { type: "SELECT_ZONE"; zoneId: string | null }
  | { type: "CLEAR_EVIDENCE_FOCUS" }
  | { type: "RESET_SELECTION" }
  | { type: "LOAD_RUN"; runId: string; bestLap: number | null }
  | { type: "VALIDATE_RUN_IDS"; runIds: string[] }
  | { type: "FOCUS_EVENT"; eventId: string; lap: number | null; sampleIndex: number | null; lapDistFt: number | null; lapPct: number | null; workspace: Workspace; source: SelectionSource }
  /** Focus full evidence context — sets all relevant fields in one transaction. */
  | { type: "FOCUS_EVIDENCE"; evidence: Partial<EvidenceContext>; workspace?: Workspace };

export function selectionReducer(state: TelemetrySelection, action: SelectionAction): TelemetrySelection {
  switch (action.type) {
    case "SELECT_RUN":
      return {
        ...DEFAULT_SELECTION,
        selectedRunId: action.runId,
        selectedCompareRunId: null,
        selectedMode: state.selectedMode,
        selectedWorkspace: state.selectedWorkspace,
      };
    case "SELECT_COMPARE_RUN":
      return { ...state, selectedCompareRunId: action.runId };
    case "SELECT_LAP":
      // Manual lap change: clear sample/event/distance/hover to prevent stale cross-lap context
      return {
        ...state,
        selectedLap: action.lap,
        selectedLapScope: "single_lap",
        selectedLapWindowStart: null,
        selectedLapWindowEnd: null,
        selectedRepresentativeLap: null,
        selectedSampleIndex: null,
        selectedLapDistFt: null,
        selectedLapPct: null,
        selectedEventId: null,
        selectedChannel: null,
        selectedZoneId: null,
        selectedZoneLabel: null,
        selectedZoneStartPct: null,
        selectedZoneEndPct: null,
        selectedValueBasis: action.lap != null ? "full_lap" : "unavailable",
        selectedLockState: "none",
        hoverLapPct: null,
        hoverSampleIndex: null,
        playbackActive: false,
      };
    case "SELECT_SAMPLE":
      return {
        ...state,
        selectedSampleIndex: action.sampleIndex,
        selectedLapDistFt: action.lapDistFt ?? state.selectedLapDistFt,
        selectedLapPct: action.lapPct ?? state.selectedLapPct,
        selectionSource: action.source,
      };
    case "SELECT_EVENT":
      return { ...state, selectedEventId: action.eventId, selectionSource: action.source };
    case "SELECT_CHANNEL":
      return { ...state, selectedChannel: action.channel, selectionSource: action.source };
    case "SELECT_SETUP_KEY":
      return { ...state, selectedSetupKey: action.setupKey };
    case "SET_MODE":
      return { ...state, selectedMode: action.mode };
    case "SET_WORKSPACE":
      return { ...state, selectedWorkspace: normalizeWorkspace(action.workspace), selectionSource: action.source };
    case "SELECT_ZONE":
      return {
        ...state,
        selectedZoneId: action.zoneId,
        selectedZoneLabel: action.zoneId == null ? null : state.selectedZoneLabel,
        selectedZoneStartPct: action.zoneId == null ? null : state.selectedZoneStartPct,
        selectedZoneEndPct: action.zoneId == null ? null : state.selectedZoneEndPct,
        selectionSource: "track_map",
      };
    case "CLEAR_EVIDENCE_FOCUS": {
      // Escape drops every evidence-owned value. Rebuild from the durable
      // run/lap scope instead of spreading state so a newly-added focus field
      // cannot silently survive this boundary.
      const selectedLapScope = state.selectedLapScope === "lap_window"
        ? "lap_window"
        : state.selectedLap != null
          ? "single_lap"
          : state.selectedRunId != null
            ? "run"
            : "unknown";
      const selectedValueBasis = selectedLapScope === "lap_window"
        ? "selected_window"
        : selectedLapScope === "single_lap"
          ? "full_lap"
          : selectedLapScope === "run"
            ? "run_level"
            : "unavailable";
      return {
        ...DEFAULT_SELECTION,
        selectedRunId: state.selectedRunId,
        selectedCompareRunId: state.selectedCompareRunId ?? null,
        selectedLap: state.selectedLap ?? null,
        selectedLapScope,
        selectedLapWindowStart: selectedLapScope === "lap_window" ? state.selectedLapWindowStart ?? null : null,
        selectedLapWindowEnd: selectedLapScope === "lap_window" ? state.selectedLapWindowEnd ?? null : null,
        selectedRepresentativeLap: selectedLapScope === "lap_window" ? state.selectedRepresentativeLap ?? null : null,
        selectedMode: state.selectedMode,
        selectedWorkspace: state.selectedWorkspace,
        selectedEventId: null,
        selectedSampleIndex: null,
        selectedLapDistFt: null,
        selectedLapPct: null,
        selectedChannel: null,
        selectedSetupKey: null,
        selectedZoneId: null,
        selectedZoneLabel: null,
        selectedZoneStartPct: null,
        selectedZoneEndPct: null,
        selectedValueBasis,
        selectedLockState: "none",
        selectedTrustTier: null,
        selectionSource: "manual",
        hoverLapPct: null,
        hoverSampleIndex: null,
        playbackActive: false,
      };
    }
    case "RESET_SELECTION":
      return { ...DEFAULT_SELECTION, selectedRunId: state.selectedRunId, selectedMode: state.selectedMode };
    case "LOAD_RUN":
      return {
        ...DEFAULT_SELECTION,
        selectedRunId: action.runId,
        selectedLap: action.bestLap,
        selectedLapScope: "single_lap",
        selectedRepresentativeLap: null,
        selectedMode: state.selectedMode,
        selectedWorkspace: state.selectedWorkspace,
        selectedValueBasis: action.bestLap != null ? "full_lap" : "unavailable",
      };
    case "VALIDATE_RUN_IDS":
      if (state.selectedRunId == null || action.runIds.includes(state.selectedRunId)) {
        return state;
      }
      return {
        ...DEFAULT_SELECTION,
        selectedRunId: null,
        selectedCompareRunId: null,
        selectedMode: state.selectedMode,
        selectedWorkspace: state.selectedWorkspace,
      };
    case "FOCUS_EVENT":
      return {
        ...state,
        selectedEventId: action.eventId,
        selectedLap: action.lap,
        selectedLapScope: action.lap != null ? "single_lap" : state.selectedLapScope,
        selectedLapWindowStart: action.lap != null ? null : state.selectedLapWindowStart,
        selectedLapWindowEnd: action.lap != null ? null : state.selectedLapWindowEnd,
        selectedRepresentativeLap: action.lap != null ? null : state.selectedRepresentativeLap,
        selectedSampleIndex: action.sampleIndex,
        selectedLapDistFt: action.lapDistFt,
        selectedLapPct: action.lapPct,
        selectedValueBasis: action.sampleIndex != null ? "selected_sample" : state.selectedValueBasis,
        selectedLockState: action.sampleIndex != null ? "locked" : state.selectedLockState,
        selectedWorkspace: normalizeWorkspace(action.workspace),
        selectionSource: action.source,
        hoverLapPct: null,
        hoverSampleIndex: null,
      };
    case "FOCUS_EVIDENCE": {
      const ev = action.evidence;
      // Evidence focus is a replace transaction. Omitted evidence-grain fields
      // clear instead of inheriting an event/sample from a different reality.
      const nextLapScope = ev.lapScope ?? (ev.lapNumber != null ? "single_lap" : ev.runId != null ? "run" : "unknown");
      const nextRepresentativeLap = ev.representativeLap !== undefined
        ? ev.representativeLap
        : nextLapScope === "lap_window"
          ? ev.lapNumber !== undefined
            ? ev.lapNumber
            : null
          : null;
      return {
        ...state,
        selectedRunId: ev.runId !== undefined ? ev.runId : state.selectedRunId,
        selectedLap: ev.lapNumber !== undefined ? ev.lapNumber : state.selectedLap,
        selectedLapScope: nextLapScope,
        selectedLapWindowStart: nextLapScope === "lap_window"
          ? ev.lapWindowStart !== undefined ? ev.lapWindowStart : state.selectedLapWindowStart
          : null,
        selectedLapWindowEnd: nextLapScope === "lap_window"
          ? ev.lapWindowEnd !== undefined ? ev.lapWindowEnd : state.selectedLapWindowEnd
          : null,
        selectedRepresentativeLap: nextRepresentativeLap,
        selectedEventId: ev.eventId ?? null,
        selectedProducerId: ev.producerId ?? null,
        selectedArtifactId: ev.artifactId ?? null,
        selectedSystem: ev.system ?? null,
        selectedCompareRole: ev.compareRole ?? null,
        selectedSourceRunId: ev.sourceRunId ?? ev.runId ?? null,
        selectedSourceSetupId: ev.sourceSetupId ?? null,
        selectedSampleIndex: ev.sampleIndex ?? null,
        selectedLapDistFt: ev.lapDistFt ?? null,
        selectedLapPct: ev.lapPct ?? null,
        selectedZoneId: ev.zoneId ?? null,
        selectedZoneLabel: ev.zoneLabel ?? null,
        selectedZoneStartPct: ev.zoneStartPct ?? null,
        selectedZoneEndPct: ev.zoneEndPct ?? null,
        selectedChannel: ev.channelId ?? null,
        selectedValueBasis: ev.valueBasis ?? "unavailable",
        selectedLockState: ev.lockState ?? "none",
        selectedTrustTier: ev.trustTier ?? null,
        selectionSource: ev.selectionSource !== undefined ? ev.selectionSource : state.selectionSource,
        selectedWorkspace: action.workspace !== undefined ? normalizeWorkspace(action.workspace) : state.selectedWorkspace,
        hoverLapPct: null,
        hoverSampleIndex: null,
        playbackActive: false,
      };
    }
    default:
      return state;
  }
}

type TelemetrySelectionContextValue = {
  selection: TelemetrySelection;
  dispatch: React.Dispatch<SelectionAction>;
  selectRun: (runId: string | null) => void;
  selectLap: (lap: number | null) => void;
  selectSample: (sampleIndex: number, lapDistFt?: number, lapPct?: number, source?: SelectionSource) => void;
  selectEvent: (eventId: string | null, source?: SelectionSource) => void;
  selectChannel: (channel: string | null, source?: SelectionSource) => void;
  selectZone: (zoneId: string | null) => void;
  setHover: (lapPct: number | null, sampleIndex?: number | null) => void;
  setPlaybackActive: (active: boolean) => void;
  setMode: (mode: SelectionMode) => void;
  setWorkspace: (workspace: Workspace, source?: SelectionSource) => void;
  loadRun: (runId: string, bestLap: number | null) => void;
  focusTelemetryEvent: (eventId: string, lap: number | null, sampleIndex: number | null, lapDistFt: number | null, lapPct: number | null, workspace: Workspace, source?: SelectionSource) => void;
  /** Set all relevant evidence context in one transaction. */
  focusEvidence: (evidence: Partial<EvidenceContext>, workspace?: Workspace) => void;
  /** Clear evidence focus while preserving only the active run/lap scope. */
  clearEvidenceFocus: () => void;
  validateSelectionRunIds: (runIds: string[]) => void;
};

const TelemetrySelectionContext = createContext<TelemetrySelectionContextValue | null>(null);

export type TelemetryCursorState = Readonly<{
  hoverLapPct: number | null;
  hoverSampleIndex: number | null;
  playbackActive: boolean;
}>;

const EMPTY_CURSOR: TelemetryCursorState = Object.freeze({
  hoverLapPct: null,
  hoverSampleIndex: null,
  playbackActive: false,
});

let cursorSnapshot = EMPTY_CURSOR;
const cursorListeners = new Set<() => void>();

function publishCursor(next: TelemetryCursorState): void {
  if (
    next.hoverLapPct === cursorSnapshot.hoverLapPct
    && next.hoverSampleIndex === cursorSnapshot.hoverSampleIndex
    && next.playbackActive === cursorSnapshot.playbackActive
  ) return;
  cursorSnapshot = Object.freeze(next);
  cursorListeners.forEach((listener) => listener());
}

function resetCursor(): void {
  publishCursor(EMPTY_CURSOR);
}

function subscribeCursor(listener: () => void): () => void {
  cursorListeners.add(listener);
  return () => cursorListeners.delete(listener);
}

function getCursorSnapshot(): TelemetryCursorState {
  return cursorSnapshot;
}

export function TelemetrySelectionProvider({ children }: { children: ReactNode }) {
  const [selection, dispatch] = useReducer(selectionReducer, DEFAULT_SELECTION);

  // Persist last workspace to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("racelab_last_workspace", selection.selectedWorkspace);
    } catch { /* ignore */ }
  }, [selection.selectedWorkspace]);

  const selectRun = useCallback((runId: string | null) => {
    resetCursor();
    dispatch({ type: "SELECT_RUN", runId });
  }, []);
  const selectLap = useCallback((lap: number | null) => {
    resetCursor();
    dispatch({ type: "SELECT_LAP", lap });
  }, []);
  const selectSample = useCallback(
    (sampleIndex: number, lapDistFt?: number, lapPct?: number, source: SelectionSource = "manual") =>
      dispatch({ type: "SELECT_SAMPLE", sampleIndex, lapDistFt, lapPct, source }),
    [],
  );
  const selectEvent = useCallback(
    (eventId: string | null, source: SelectionSource = "priority_stack") =>
      dispatch({ type: "SELECT_EVENT", eventId, source }),
    [],
  );
  const selectChannel = useCallback(
    (channel: string | null, source: SelectionSource = "manual") =>
      dispatch({ type: "SELECT_CHANNEL", channel, source }),
    [],
  );
  const selectZone = useCallback(
    (zoneId: string | null) => dispatch({ type: "SELECT_ZONE", zoneId }),
    [],
  );
  const setHover = useCallback(
    (lapPct: number | null, sampleIndex: number | null = null) => publishCursor({
      ...cursorSnapshot,
      hoverLapPct: lapPct,
      hoverSampleIndex: sampleIndex,
    }),
    [],
  );
  const setPlaybackActive = useCallback(
    (active: boolean) => publishCursor({ ...cursorSnapshot, playbackActive: active }),
    [],
  );
  const setMode = useCallback((mode: SelectionMode) => dispatch({ type: "SET_MODE", mode }), []);
  const setWorkspace = useCallback(
    (workspace: Workspace, source: SelectionSource = "manual") =>
      dispatch({ type: "SET_WORKSPACE", workspace: normalizeWorkspace(workspace), source }),
    [],
  );
  const loadRun = useCallback(
    (runId: string, bestLap: number | null) => {
      resetCursor();
      dispatch({ type: "LOAD_RUN", runId, bestLap });
    },
    [],
  );
  const focusTelemetryEvent = useCallback(
    (eventId: string, lap: number | null, sampleIndex: number | null, lapDistFt: number | null, lapPct: number | null, workspace: Workspace, source: SelectionSource = "priority_stack") => {
      resetCursor();
      dispatch({ type: "FOCUS_EVENT", eventId, lap, sampleIndex, lapDistFt, lapPct, workspace, source });
    },
    [],
  );

  const focusEvidence = useCallback(
    (evidence: Partial<EvidenceContext>, workspace?: Workspace) => {
      resetCursor();
      dispatch({ type: "FOCUS_EVIDENCE", evidence, workspace });
    },
    [],
  );
  const clearEvidenceFocus = useCallback(() => {
    resetCursor();
    dispatch({ type: "CLEAR_EVIDENCE_FOCUS" });
  }, []);
  const validateSelectionRunIds = useCallback(
    (runIds: string[]) => dispatch({ type: "VALIDATE_RUN_IDS", runIds }),
    [],
  );

  useEffect(() => resetCursor(), [selection.selectedRunId, selection.selectedLap]);

  const contextValue = useMemo<TelemetrySelectionContextValue>(() => ({
    selection,
    dispatch,
    selectRun,
    selectLap,
    selectSample,
    selectEvent,
    selectChannel,
    selectZone,
    setHover,
    setPlaybackActive,
    setMode,
    setWorkspace,
    loadRun,
    focusTelemetryEvent,
    focusEvidence,
    clearEvidenceFocus,
    validateSelectionRunIds,
  }), [
    clearEvidenceFocus,
    focusEvidence,
    focusTelemetryEvent,
    loadRun,
    selectChannel,
    selectEvent,
    selectLap,
    selection,
    selectRun,
    selectSample,
    selectZone,
    setHover,
    setMode,
    setPlaybackActive,
    setWorkspace,
    validateSelectionRunIds,
  ]);

  return (
    <TelemetrySelectionContext.Provider value={contextValue}>
      {children}
    </TelemetrySelectionContext.Provider>
  );
}

export function useTelemetrySelection() {
  const ctx = useContext(TelemetrySelectionContext);
  if (!ctx) throw new Error("useTelemetrySelection must be used within TelemetrySelectionProvider");
  return ctx;
}

/** Subscribe only to high-frequency chart cursor state, without rerendering the cockpit selection tree. */
export function useTelemetryCursor(): TelemetryCursorState {
  return useSyncExternalStore(subscribeCursor, getCursorSnapshot, getCursorSnapshot);
}
