import { createContext, useCallback, useContext, useReducer, type ReactNode } from "react";
import type { SelectionMode, SelectionSource, TelemetrySelection, Workspace } from "./types";

const DEFAULT_SELECTION: TelemetrySelection = {
  selectedRunId: null,
  selectedMode: "diagnose",
  selectedWorkspace: "overview",
  selectionSource: "manual",
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
  | { type: "RESET_SELECTION" }
  | { type: "LOAD_RUN"; runId: string; bestLap: number | null };

function selectionReducer(state: TelemetrySelection, action: SelectionAction): TelemetrySelection {
  switch (action.type) {
    case "SELECT_RUN":
      return { ...state, selectedRunId: action.runId, selectedCompareRunId: null };
    case "SELECT_COMPARE_RUN":
      return { ...state, selectedCompareRunId: action.runId };
    case "SELECT_LAP":
      return { ...state, selectedLap: action.lap, selectedSampleIndex: null, selectedLapDistFt: null, selectedLapPct: null };
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
      return { ...state, selectedZoneId: action.zoneId, selectionSource: "track_map" };
    case "RESET_SELECTION":
      return { ...DEFAULT_SELECTION, selectedRunId: state.selectedRunId, selectedMode: state.selectedMode };
    case "LOAD_RUN":
      return {
        ...DEFAULT_SELECTION,
        selectedRunId: action.runId,
        selectedLap: action.bestLap,
        selectedMode: state.selectedMode,
      };
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
  setMode: (mode: SelectionMode) => void;
  setWorkspace: (workspace: Workspace, source?: SelectionSource) => void;
  loadRun: (runId: string, bestLap: number | null) => void;
};

const TelemetrySelectionContext = createContext<TelemetrySelectionContextValue | null>(null);

export function TelemetrySelectionProvider({ children }: { children: ReactNode }) {
  const [selection, dispatch] = useReducer(selectionReducer, DEFAULT_SELECTION);

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

  return (
    <TelemetrySelectionContext.Provider
      value={{ selection, dispatch, selectRun, selectLap, selectSample, selectEvent, selectChannel, selectZone, setMode, setWorkspace, loadRun }}
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
