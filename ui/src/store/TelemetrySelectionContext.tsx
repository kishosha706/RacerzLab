import { createContext, useCallback, useContext, useEffect, useReducer, type ReactNode } from "react";
import type { EvidenceContext, SelectionMode, SelectionSource, TelemetrySelection, Workspace } from "./types";

const VALID_WORKSPACES: Workspace[] = ["overview", "map", "laps", "platform_trace", "speed_delta", "drag_scrub", "setup_impact", "compare", "notebook", "channels"];

function loadLastWorkspace(): Workspace {
  try {
    const saved = localStorage.getItem("racelab_last_workspace");
    if (saved && VALID_WORKSPACES.includes(saved as Workspace)) return saved as Workspace;
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
  | { type: "SET_HOVER"; lapPct: number | null; sampleIndex?: number | null }
  | { type: "SET_PLAYBACK_ACTIVE"; active: boolean }
  | { type: "RESET_SELECTION" }
  | { type: "LOAD_RUN"; runId: string; bestLap: number | null }
  | { type: "FOCUS_EVENT"; eventId: string; lap: number | null; sampleIndex: number | null; lapDistFt: number | null; lapPct: number | null; workspace: Workspace; source: SelectionSource }
  /** Focus full evidence context — sets all relevant fields in one transaction. */
  | { type: "FOCUS_EVIDENCE"; evidence: Partial<EvidenceContext>; workspace?: Workspace };

function selectionReducer(state: TelemetrySelection, action: SelectionAction): TelemetrySelection {
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
      return { ...state, selectedWorkspace: action.workspace, selectionSource: action.source };
    case "SELECT_ZONE":
      return {
        ...state,
        selectedZoneId: action.zoneId,
        selectedZoneLabel: action.zoneId == null ? null : state.selectedZoneLabel,
        selectedZoneStartPct: action.zoneId == null ? null : state.selectedZoneStartPct,
        selectedZoneEndPct: action.zoneId == null ? null : state.selectedZoneEndPct,
        selectionSource: "track_map",
      };
    case "SET_HOVER":
      return { ...state, hoverLapPct: action.lapPct, hoverSampleIndex: action.sampleIndex ?? state.hoverSampleIndex };
    case "SET_PLAYBACK_ACTIVE":
      return { ...state, playbackActive: action.active };
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
        selectedValueBasis: action.bestLap != null ? "full_lap" : "unavailable",
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
        selectedWorkspace: action.workspace,
        selectionSource: action.source,
        hoverLapPct: null,
        hoverSampleIndex: null,
      };
    case "FOCUS_EVIDENCE": {
      const ev = action.evidence;
      const nextLapScope = ev.lapScope !== undefined ? ev.lapScope : state.selectedLapScope;
      const nextRepresentativeLap = ev.representativeLap !== undefined
        ? ev.representativeLap
        : nextLapScope === "lap_window"
          ? ev.lapNumber !== undefined
            ? ev.lapNumber
            : state.selectedRepresentativeLap
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
        selectedEventId: ev.eventId !== undefined ? ev.eventId : state.selectedEventId,
        selectedSampleIndex: ev.sampleIndex !== undefined ? ev.sampleIndex : state.selectedSampleIndex,
        selectedLapDistFt: ev.lapDistFt !== undefined ? ev.lapDistFt : state.selectedLapDistFt,
        selectedLapPct: ev.lapPct !== undefined ? ev.lapPct : state.selectedLapPct,
        selectedZoneId: ev.zoneId !== undefined ? ev.zoneId : state.selectedZoneId,
        selectedZoneLabel: ev.zoneLabel !== undefined ? ev.zoneLabel : state.selectedZoneLabel,
        selectedZoneStartPct: ev.zoneStartPct !== undefined ? ev.zoneStartPct : state.selectedZoneStartPct,
        selectedZoneEndPct: ev.zoneEndPct !== undefined ? ev.zoneEndPct : state.selectedZoneEndPct,
        selectedChannel: ev.channelId !== undefined ? ev.channelId : state.selectedChannel,
        selectedValueBasis: ev.valueBasis !== undefined ? ev.valueBasis : state.selectedValueBasis,
        selectedLockState: ev.lockState !== undefined ? ev.lockState : state.selectedLockState,
        selectedTrustTier: ev.trustTier !== undefined ? ev.trustTier : state.selectedTrustTier,
        selectionSource: ev.selectionSource !== undefined ? ev.selectionSource : state.selectionSource,
        selectedWorkspace: action.workspace !== undefined ? action.workspace : state.selectedWorkspace,
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
};

const TelemetrySelectionContext = createContext<TelemetrySelectionContextValue | null>(null);

export function TelemetrySelectionProvider({ children }: { children: ReactNode }) {
  const [selection, dispatch] = useReducer(selectionReducer, DEFAULT_SELECTION);

  // Persist last workspace to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("racelab_last_workspace", selection.selectedWorkspace);
    } catch { /* ignore */ }
  }, [selection.selectedWorkspace]);

  const selectRun = useCallback((runId: string | null) => dispatch({ type: "SELECT_RUN", runId }), []);
  const selectLap = useCallback((lap: number | null) => dispatch({ type: "SELECT_LAP", lap }), []);
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
    (lapPct: number | null, sampleIndex?: number | null) =>
      dispatch({ type: "SET_HOVER", lapPct, sampleIndex }),
    [],
  );
  const setPlaybackActive = useCallback(
    (active: boolean) => dispatch({ type: "SET_PLAYBACK_ACTIVE", active }),
    [],
  );
  const setMode = useCallback((mode: SelectionMode) => dispatch({ type: "SET_MODE", mode }), []);
  const setWorkspace = useCallback(
    (workspace: Workspace, source: SelectionSource = "manual") =>
      dispatch({ type: "SET_WORKSPACE", workspace, source }),
    [],
  );
  const loadRun = useCallback(
    (runId: string, bestLap: number | null) => dispatch({ type: "LOAD_RUN", runId, bestLap }),
    [],
  );
  const focusTelemetryEvent = useCallback(
    (eventId: string, lap: number | null, sampleIndex: number | null, lapDistFt: number | null, lapPct: number | null, workspace: Workspace, source: SelectionSource = "priority_stack") =>
      dispatch({ type: "FOCUS_EVENT", eventId, lap, sampleIndex, lapDistFt, lapPct, workspace, source }),
    [],
  );

  const focusEvidence = useCallback(
    (evidence: Partial<EvidenceContext>, workspace?: Workspace) =>
      dispatch({ type: "FOCUS_EVIDENCE", evidence, workspace }),
    [],
  );

  return (
    <TelemetrySelectionContext.Provider
      value={{ selection, dispatch, selectRun, selectLap, selectSample, selectEvent, selectChannel, selectZone, setHover, setPlaybackActive, setMode, setWorkspace, loadRun, focusTelemetryEvent, focusEvidence }}
    >
      {children}
    </TelemetrySelectionContext.Provider>
  );
}

export function useTelemetrySelection() {
  const ctx = useContext(TelemetrySelectionContext);
  if (!ctx) throw new Error("useTelemetrySelection must be used within TelemetrySelectionProvider");
  return ctx;
}
