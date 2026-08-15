import { AlertTriangle, ArrowLeft, BrainCircuit, CheckCircle2, ChevronRight, Clock, Crosshair, Gauge, Layers, LoaderCircle, Upload, Wrench } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addRunToSession,
  fetchChannelSummary,
  fetchChannelsFull,
  fetchControlledWorkflow,
  fetchControlledWorkflowCatalog,
  fetchEvents,
  fetchHealth,
  fetchRunIntelligence,
  fetchLaps,
  fetchOverview,
  fetchPlatformEventsReport,
  fetchRunList,
  fetchSessionRunList,
  fetchSession,
  fetchSetup,
  fetchTelemetryCapabilities,
  fetchTrace,
  importIbtFile,
  importMt2File,
} from "./api/client";
import { ImportPanel } from "./components/ImportPanel";
import { ControlledTestRibbon } from "./components/ControlledTestRibbon";
import { RunContextBar } from "./components/RunContextBar";
import { StartupScreen } from "./components/StartupScreen";
import { TelemetrySelectionProvider, useTelemetrySelection } from "./store/TelemetrySelectionContext";
import { CompareBasketProvider, useCompareBasket } from "./store/CompareBasketContext";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { humanizeWorkspaceLabel } from "./constants/ui";

import { TRACE_WORKBENCH_CHANNELS } from "./constants/workbenchChannels";
import { importDebug } from "./utils/importDebug";
import { isTauri } from "./utils/env";
import { buildZoneEvidence } from "./utils/evidenceFocus";
import {
  bestUsefulLapMatchesRun,
  overviewWarningBlocksDecision,
  setupSnapshotMatchesRun,
  telemetryEventIsActionable,
} from "./utils/evidenceTrust";
import type {
  ChannelCatalogItem,
  ControlledWorkflow,
  LapSummary,
  PlatformEventItem,
  PlatformEventVisibilityMode,
  RunListItem,
  RunOverview,
  TrackMapResolution,
  TraceResponse,
  TelemetryCapabilitiesResponse,
} from "./types/telemetry";
import type { RaceLabSession, SessionSelectionSource } from "./types/session";
import type { IntelligenceCitation, IntelligenceCitationWorkspace, IntelligenceNextTrustworthyMove } from "./types/intelligence";
import type { CrewChiefEvidenceEntry } from "./types/crewChief";
import type { LearningEvidenceReference } from "./types/engineeringLearning";
import { canonicalJsonSha256 } from "./utils/canonicalJsonSha256";
import {
  intelligenceMoveScope,
  intelligenceWorkspaceTarget,
  moveScopeLabel,
  trustedNavigationMove,
} from "./utils/intelligenceNavigation";
import {
  CURRENT_INTELLIGENCE_AUTHORITY_RECOVERY,
  currentIntelligenceAuthorityMatchesWorkflow,
  deriveCurrentIntelligenceAuthority,
  type CurrentIntelligenceAuthority,
  type CurrentIntelligenceAuthorityStatus,
} from "./utils/currentIntelligenceAuthority";

type PlatformLoadStatus = "idle" | "loading" | "ready" | "clear" | "unavailable" | "error";

type PlatformLoadState = {
  requestKey: string | null;
  status: PlatformLoadStatus;
  error: string | null;
};

type WorkspaceSignalTone = "idle" | "loading" | "ready" | "attention" | "clear" | "blocked";

type WorkspaceSignal = {
  tone: WorkspaceSignalTone;
  short: string;
  detail: string;
};

const PRIORITY_RAIL_OVERLAY_QUERY = "(max-width: 700px)";

type IntelligenceShellReportStatus = "idle" | "checking" | "ready" | "error";

type IntelligenceShellReportState = {
  requestKey: string | null;
  status: IntelligenceShellReportStatus;
  move: IntelligenceNextTrustworthyMove | null;
  error: string | null;
};

type IntelligenceAuthorityReportState = {
  requestKey: string | null;
  status: CurrentIntelligenceAuthorityStatus;
  authority: CurrentIntelligenceAuthority | null;
  error: string | null;
};

type ControlledWorkflowCatalogStatus = "idle" | "checking" | "ready" | "error";

type ControlledWorkflowCatalogState = {
  requestKey: string | null;
  status: ControlledWorkflowCatalogStatus;
  error: string | null;
};

const LONG_RUN_REVIEW_MIN_LAPS = 10;

function longestContinuousEligibleLapBlock(laps: readonly LapSummary[]): number {
  const lapNumbers = [...new Set(laps.map((lap) => lap.lap_number))].sort((left, right) => left - right);
  let longest = 0;
  let current = 0;
  let previous: number | null = null;
  for (const lapNumber of lapNumbers) {
    current = previous != null && lapNumber === previous + 1 ? current + 1 : 1;
    longest = Math.max(longest, current);
    previous = lapNumber;
  }
  return longest;
}

function controlledWorkflowUpdatedAt(workflow: ControlledWorkflow | null): string | null {
  if (!workflow) return null;
  const value = (workflow as ControlledWorkflow & { updated_at?: unknown }).updated_at;
  return typeof value === "string" && value.trim() === value && value.length > 0 ? value : null;
}

function controlledWorkflowCatalogRecovery(error: unknown): string {
  const reason = error instanceof Error && error.message.trim().length > 0
    ? error.message.trim()
    : null;
  return reason
    ? `Controlled-test status is unavailable: ${reason} Open Dial-In and retry before starting or resuming a workflow.`
    : "Controlled-test status is unavailable. Open Dial-In and retry before starting or resuming a workflow.";
}

function intelligenceShellRecovery(error: unknown): string {
  const reason = error instanceof Error && error.message.trim().length > 0
    ? error.message.trim()
    : null;
  return reason
    ? `Smart Engineer briefing is unavailable: ${reason} Open Engineer and retry the current scope.`
    : "Smart Engineer briefing is unavailable. Open Engineer and retry the current scope.";
}

function sessionPayloadMatchesRequest(session: RaceLabSession, requestedSessionId: string): boolean {
  const runIds = Array.isArray(session.run_ids) ? session.run_ids : [];
  return session.session_id === requestedSessionId
    && runIds.every((runId) => typeof runId === "string" && runId.trim() === runId && runId.length > 0)
    && new Set(runIds).size === runIds.length;
}

function sessionRunListMatchesMembership(
  scopedRuns: RunListItem[],
  expectedRunIds: readonly string[],
): boolean {
  const expected = new Set(expectedRunIds);
  const returned = new Set(scopedRuns.map((run) => run.run_id));
  return returned.size === scopedRuns.length
    && returned.size === expected.size
    && [...returned].every((runId) => expected.has(runId));
}

const EMPTY_PLATFORM_EVENTS: PlatformEventItem[] = [];
const INTELLIGENCE_CITATION_WORKSPACES: ReadonlySet<IntelligenceCitationWorkspace> = new Set([
  "overview",
  "laps",
  "platform_trace",
  "speed_delta",
  "drag_scrub",
  "setup_impact",
  "dial_in",
]);

const loadDialInTab = () => import("./tabs/DialInTab");
const loadEngineerTab = () => import("./tabs/EngineerTab");
const loadOverviewTab = () => import("./tabs/OverviewTab");
const loadLapsTab = () => import("./tabs/LapsTab");
const loadPlatformTab = () => import("./tabs/PlatformTab");
const loadSetupTab = () => import("./tabs/SetupTab");
const loadPriorityRail = () => import("./components/PriorityRail");
const loadEvidenceInspector = () => import("./components/EvidenceInspector");
const loadEventTimeline = () => import("./components/EventTimeline");
const loadTrackMapOverlay = () => import("./components/TrackMapOverlay");
const loadCompareBasket = () => import("./components/CompareBasket");

const DialInTab = lazy(async () => {
  const module = await loadDialInTab();
  return { default: module.DialInTab };
});
const EngineerTab = lazy(async () => {
  const module = await loadEngineerTab();
  return { default: module.EngineerTab };
});
const OverviewTab = lazy(async () => {
  const module = await loadOverviewTab();
  return { default: module.OverviewTab };
});
const PriorityRail = lazy(async () => {
  const module = await loadPriorityRail();
  return { default: module.PriorityRail };
});
const EvidenceInspector = lazy(async () => {
  const module = await loadEvidenceInspector();
  return { default: module.EvidenceInspector };
});
const EventTimeline = lazy(async () => {
  const module = await loadEventTimeline();
  return { default: module.EventTimeline };
});
const TrackMapOverlay = lazy(async () => {
  const module = await loadTrackMapOverlay();
  return { default: module.TrackMapOverlay };
});
const CompareBasket = lazy(async () => {
  const module = await loadCompareBasket();
  return { default: module.CompareBasket };
});
const LapsTab = lazy(async () => {
  const module = await loadLapsTab();
  return { default: module.LapsTab };
});
const PlatformTab = lazy(async () => {
  const module = await loadPlatformTab();
  return { default: module.PlatformTab };
});
const SetupTab = lazy(async () => {
  const module = await loadSetupTab();
  return { default: module.SetupTab };
});

function preloadWorkspace(workspace: string): void {
  if (workspace === "overview") void loadOverviewTab();
  else if (workspace === "engineer") void loadEngineerTab();
  else if (workspace === "laps") void loadLapsTab();
  else if (workspace === "platform_trace") void loadPlatformTab();
  else if (workspace === "setup_impact") void loadSetupTab();
  else if (workspace === "dial_in") void loadDialInTab();
}

function ShellLoadingState({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return (
    <main className="boot-screen shell-loading-screen" role="status" aria-live="polite" aria-busy="true">
      <section className="shell-loading-panel">
        <div className="shell-loading-mark" aria-hidden="true">
          <LoaderCircle size={22} />
        </div>
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h1>{title}</h1>
          <p>{detail}</p>
        </div>
        <div className="shell-loading-track" aria-hidden="true"><span /></div>
      </section>
    </main>
  );
}

// ── cockpit shell ─────────────────────────────────────────────

function CockpitShell() {
  const desktop = isTauri();
  const [engineStatus, setEngineStatus] = useState<"starting" | "ready" | "failed">("starting");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<RaceLabSession | null>(null);
  const [sessionSelectionSource, setSessionSelectionSource] = useState<SessionSelectionSource | null>(null);
  const [sessionRuns, setSessionRuns] = useState<RunListItem[]>([]);
  const [sessionRunsLoading, setSessionRunsLoading] = useState(false);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [traceLoadState, setTraceLoadState] = useState<PlatformLoadState>({ requestKey: null, status: "idle", error: null });
  const [traceRetryToken, setTraceRetryToken] = useState(0);
  const [channels, setChannels] = useState<ChannelCatalogItem[]>([]);
  const [channelsHaveFullCatalog, setChannelsHaveFullCatalog] = useState(false);
  const [platformEvents, setPlatformEvents] = useState<PlatformEventItem[]>([]);
  const [platformEventsLoadState, setPlatformEventsLoadState] = useState<PlatformLoadState>({ requestKey: null, status: "idle", error: null });
  const [platformEventsRetryToken, setPlatformEventsRetryToken] = useState(0);
  const [telemetryCapabilities, setTelemetryCapabilities] = useState<TelemetryCapabilitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [sessionToolsOpen, setSessionToolsOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [importOutcome, setImportOutcome] = useState<"run" | "map" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sessionOpenError, setSessionOpenError] = useState<string | null>(null);
  const [priorityRailOpen, setPriorityRailOpen] = useState(true);
  const [priorityRailUsesOverlay, setPriorityRailUsesOverlay] = useState(() => (
    typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia(PRIORITY_RAIL_OVERLAY_QUERY).matches
  ));
  const priorityRailTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [activeControlledWorkflow, setActiveControlledWorkflow] = useState<ControlledWorkflow | null>(null);
  const [guidanceControlledWorkflow, setGuidanceControlledWorkflow] = useState<ControlledWorkflow | null>(null);
  const [activeControlledWorkflowRequestKey, setActiveControlledWorkflowRequestKey] = useState<string | null>(null);
  const [activeControlledWorkflowAmbiguous, setActiveControlledWorkflowAmbiguous] = useState(false);
  const [controlledWorkflowCatalogState, setControlledWorkflowCatalogState] = useState<ControlledWorkflowCatalogState>({ requestKey: null, status: "idle", error: null });
  const [explicitControlledWorkflowId, setExplicitControlledWorkflowId] = useState<string | null>(null);
  const [intelligenceShellReportState, setIntelligenceShellReportState] = useState<IntelligenceShellReportState>({
    requestKey: null,
    status: "idle",
    move: null,
    error: null,
  });
  const [intelligenceAuthorityReportState, setIntelligenceAuthorityReportState] = useState<IntelligenceAuthorityReportState>({
    requestKey: null,
    status: "idle",
    authority: null,
    error: null,
  });
  const [intelligenceAuthorityRefreshGeneration, setIntelligenceAuthorityRefreshGeneration] = useState(0);
  const [timelineOwnsKeyboard, setTimelineOwnsKeyboard] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const shortcutModalRef = useRef<HTMLElement | null>(null);
  const shortcutModalCloseRef = useRef<HTMLButtonElement | null>(null);
  const [mapOverlayOpen, setMapOverlayOpen] = useState(false);
  const [mapOverlayZoomRange, setMapOverlayZoomRange] = useState<{ startValue?: number; endValue?: number } | null>(null);
  const mapOverlayOpenRef = useRef(false);
  const latestMapOverlayZoomRangeRef = useRef<{ startValue?: number; endValue?: number } | null>(null);
  const [platformEventVisibilityMode, setPlatformEventVisibilityMode] = useState<PlatformEventVisibilityMode>("actionable");
  const loadSelectedRunSeqRef = useRef(0);
  const sessionSelectionSeqRef = useRef(0);
  const sessionRunsRequestSeqRef = useRef(0);
  const importOpenIntentRef = useRef(0);
  const controlledWorkflowRequestSeqRef = useRef(0);
  const intelligenceShellRequestSeqRef = useRef(0);
  const intelligenceAuthorityRequestSeqRef = useRef(0);

  const { selection, dispatch, loadRun, selectRun, selectLap, setWorkspace, focusEvidence, validateSelectionRunIds } = useTelemetrySelection();
  const previousWorkspaceRef = useRef(selection.selectedWorkspace);
  const { basket, validateAvailableRuns } = useCompareBasket();
  const invalidateIntelligenceAuthority = useCallback(() => {
    intelligenceAuthorityRequestSeqRef.current += 1;
    setIntelligenceAuthorityReportState({ requestKey: null, status: "idle", authority: null, error: null });
    setIntelligenceAuthorityRefreshGeneration((generation) => generation + 1);
  }, []);
  const selectedTraceLap = selection.selectedRepresentativeLap ?? selection.selectedLap ?? null;
  const platformTargetLap = overview ? selectedTraceLap ?? overview.best_useful_lap?.lap_number ?? null : null;
  const platformRequestKey = overview && platformTargetLap != null
    ? JSON.stringify({ run_id: overview.run_id, lap: platformTargetLap })
    : null;
  const platformEventsStateOwnsRequest = platformEventsLoadState.requestKey === platformRequestKey;
  const currentPlatformEvents = platformEventsStateOwnsRequest && ["ready", "clear"].includes(platformEventsLoadState.status)
    ? platformEvents
    : EMPTY_PLATFORM_EVENTS;
  const currentPlatformEventsLoadStatus: PlatformLoadStatus = platformRequestKey == null
    ? "idle"
    : platformEventsStateOwnsRequest ? platformEventsLoadState.status : "loading";
  const currentPlatformEventsLoadError = platformEventsStateOwnsRequest ? platformEventsLoadState.error : null;
  const priorityRailIsGenuinelyClear = selection.selectedMode === "race"
    && currentPlatformEventsLoadStatus === "clear";
  const priorityRailNeedsAttention = currentPlatformEventsLoadStatus !== "clear";
  const priorityRailMustStayOpen = !priorityRailUsesOverlay
    && selection.selectedMode === "race"
    && currentPlatformEventsLoadStatus !== "clear";
  const priorityRailExpanded = priorityRailMustStayOpen || priorityRailOpen;
  const priorityRailCollapsedLabel = priorityRailIsGenuinelyClear
    ? "Supported platform checks clear; expand Priority Rail"
    : priorityRailNeedsAttention
      ? "Priority evidence needs attention; expand Priority Rail"
      : "Expand Priority Rail";
  const closePriorityRail = useCallback(() => {
    setPriorityRailOpen(false);
    if (priorityRailUsesOverlay) {
      window.setTimeout(() => priorityRailTriggerRef.current?.focus(), 0);
    }
  }, [priorityRailUsesOverlay]);
  const openPriorityRail = useCallback(() => {
    setPriorityRailOpen(true);
    if (priorityRailUsesOverlay) {
      window.setTimeout(() => {
        document.querySelector<HTMLButtonElement>(
          ".cockpit-body > .priority-rail:not(.collapsed) .rail-collapse-btn",
        )?.focus();
      }, 0);
    }
  }, [priorityRailUsesOverlay]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia(PRIORITY_RAIL_OVERLAY_QUERY);
    const syncLayout = () => setPriorityRailUsesOverlay(query.matches);
    syncLayout();
    query.addEventListener("change", syncLayout);
    return () => query.removeEventListener("change", syncLayout);
  }, []);

  useEffect(() => {
    if (!priorityRailUsesOverlay || !priorityRailExpanded) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (
        event.key !== "Escape"
        || event.defaultPrevented
        || document.querySelector('[role="dialog"][aria-modal="true"]')
      ) return;
      event.preventDefault();
      closePriorityRail();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [closePriorityRail, priorityRailExpanded, priorityRailUsesOverlay]);
  const traceStateOwnsRequest = traceLoadState.requestKey === platformRequestKey;
  const currentTrace = traceStateOwnsRequest && traceLoadState.status === "ready" ? trace : null;
  const currentTraceLoadStatus: PlatformLoadStatus = platformRequestKey == null
    ? "idle"
    : traceStateOwnsRequest ? traceLoadState.status : "loading";
  const currentTraceLoadError = traceStateOwnsRequest ? traceLoadState.error : null;
  const isTraceWorkspace =
    selection.selectedWorkspace === "platform_trace"
    || selection.selectedWorkspace === "speed_delta"
    || selection.selectedWorkspace === "drag_scrub";
  const hasCompareBasketItems = basket.baseline != null || basket.test != null;

  const retryTrace = useCallback(() => setTraceRetryToken((token) => token + 1), []);
  const retryPlatformEvents = useCallback(() => setPlatformEventsRetryToken((token) => token + 1), []);
  const attachedSessionRunIds = useMemo(() => new Set([
    ...(currentSession?.run_ids ?? []),
    ...sessionRuns.map((run) => run.run_id),
  ]), [currentSession?.run_ids, sessionRuns]);
  const sessionRunOptions = useMemo(() => {
    if (!currentSession) return runs;
    if (sessionRuns.length > 0) return sessionRuns;
    return runs.filter((run) => attachedSessionRunIds.has(run.run_id));
  }, [attachedSessionRunIds, currentSession, runs, sessionRuns]);
  const controlledWorkflowScopeRunIds = useMemo(
    () => currentSession
      ? [...attachedSessionRunIds]
      : overview ? [overview.run_id] : [],
    [attachedSessionRunIds, currentSession, overview],
  );
  const controlledWorkflowScopeKey = useMemo(
    () => JSON.stringify([...controlledWorkflowScopeRunIds].sort()),
    [controlledWorkflowScopeRunIds],
  );
  const controlledWorkflowRequestKey = useMemo(() => JSON.stringify({
    run_id: overview?.run_id ?? null,
    selected_session_id: sessionId,
    loaded_session_id: currentSession?.session_id ?? null,
    scope: controlledWorkflowScopeKey,
  }), [controlledWorkflowScopeKey, currentSession?.session_id, overview?.run_id, sessionId]);
  const controlledWorkflowCatalogCanLoad = Boolean(
    overview?.run_id
    && currentSession?.session_id
    && currentSession.session_id === sessionId
    && controlledWorkflowScopeRunIds.includes(overview.run_id),
  );
  const controlledWorkflowCatalogStateOwnsRequest = controlledWorkflowCatalogState.requestKey === controlledWorkflowRequestKey;
  const currentControlledWorkflowCatalogStatus: ControlledWorkflowCatalogStatus = !controlledWorkflowCatalogCanLoad
    ? "idle"
    : controlledWorkflowCatalogStateOwnsRequest ? controlledWorkflowCatalogState.status : "checking";
  const currentControlledWorkflowCatalogError = controlledWorkflowCatalogStateOwnsRequest
    ? controlledWorkflowCatalogState.error
    : null;
  const currentControlledWorkflow = currentControlledWorkflowCatalogStatus === "ready"
    && currentSession?.session_id === sessionId
    && activeControlledWorkflowRequestKey === controlledWorkflowRequestKey
    ? activeControlledWorkflow
    : null;
  const currentControlledWorkflowAmbiguous = currentControlledWorkflowCatalogStatus === "ready"
    && currentSession?.session_id === sessionId
    && activeControlledWorkflowRequestKey === controlledWorkflowRequestKey
    && activeControlledWorkflowAmbiguous;
  const currentGuidanceWorkflow = currentControlledWorkflowCatalogStatus === "ready"
    && currentSession?.session_id === sessionId
    && activeControlledWorkflowRequestKey === controlledWorkflowRequestKey
    ? guidanceControlledWorkflow
    : null;
  const currentGuidanceWorkflowUpdatedAt = controlledWorkflowUpdatedAt(currentGuidanceWorkflow);
  const currentAuthorityWorkflow = currentControlledWorkflow?.packet.decision === "test"
    && currentControlledWorkflow.status === "a_recorded"
    ? currentControlledWorkflow
    : null;
  const currentAuthorityWorkflowUpdatedAt = controlledWorkflowUpdatedAt(currentAuthorityWorkflow);
  const intelligenceAuthorityRequestKey = JSON.stringify({
    source_run_id: currentAuthorityWorkflow?.source_run_id ?? null,
    selected_session_id: sessionId,
    loaded_session_id: currentSession?.session_id ?? null,
    session_run_scope: controlledWorkflowScopeKey,
    workflow_id: currentAuthorityWorkflow?.workflow_id ?? null,
    workflow_status: currentAuthorityWorkflow?.status ?? null,
    workflow_updated_at: currentAuthorityWorkflowUpdatedAt,
    active_workflow_ambiguous: currentControlledWorkflowAmbiguous,
    artifact_refresh_generation: intelligenceAuthorityRefreshGeneration,
  });
  const intelligenceAuthorityCanLoad = Boolean(
    currentAuthorityWorkflow
    && currentAuthorityWorkflowUpdatedAt
    && currentSession?.session_id
    && currentSession.session_id === sessionId
    && controlledWorkflowScopeRunIds.includes(currentAuthorityWorkflow.source_run_id)
    && !currentControlledWorkflowAmbiguous,
  );
  const intelligenceAuthorityStateOwnsRequest = intelligenceAuthorityReportState.requestKey === intelligenceAuthorityRequestKey;
  const currentIntelligenceAuthorityStatus: CurrentIntelligenceAuthorityStatus = !currentAuthorityWorkflow
    ? "idle"
    : intelligenceAuthorityStateOwnsRequest
      ? intelligenceAuthorityReportState.status
      : "checking";
  const currentIntelligenceAuthority = currentAuthorityWorkflow
    && currentIntelligenceAuthorityStatus === "authorized"
    && currentIntelligenceAuthorityMatchesWorkflow(
      intelligenceAuthorityReportState.authority,
      currentAuthorityWorkflow,
    )
    ? intelligenceAuthorityReportState.authority
    : null;
  const currentIntelligenceAuthorityRecovery = intelligenceAuthorityStateOwnsRequest
    ? intelligenceAuthorityReportState.error ?? CURRENT_INTELLIGENCE_AUTHORITY_RECOVERY
    : CURRENT_INTELLIGENCE_AUTHORITY_RECOVERY;
  const intelligenceShellRequestKey = JSON.stringify({
    run_id: overview?.run_id ?? null,
    selected_lap: selection.selectedLap ?? null,
    selected_lap_scope: selection.selectedLapScope ?? "unknown",
    selected_lap_window_start: selection.selectedLapWindowStart ?? null,
    selected_lap_window_end: selection.selectedLapWindowEnd ?? null,
    selected_representative_lap: selection.selectedRepresentativeLap ?? null,
    selected_session_id: sessionId,
    loaded_session_id: currentSession?.session_id ?? null,
    session_run_scope: controlledWorkflowScopeKey,
    guidance_workflow_id: currentGuidanceWorkflow?.workflow_id ?? null,
    guidance_workflow_status: currentGuidanceWorkflow?.status ?? null,
    guidance_workflow_updated_at: currentGuidanceWorkflowUpdatedAt,
    active_workflow_ambiguous: currentControlledWorkflowAmbiguous,
  });
  const intelligenceShellCanLoad = Boolean(
    overview?.run_id
    && currentSession?.session_id
    && currentSession.session_id === sessionId,
  );
  const intelligenceShellStateOwnsRequest = intelligenceShellReportState.requestKey === intelligenceShellRequestKey;
  const currentIntelligenceShellStatus: IntelligenceShellReportStatus = !intelligenceShellCanLoad
    ? "idle"
    : intelligenceShellStateOwnsRequest ? intelligenceShellReportState.status : "checking";
  const currentIntelligenceShellError = intelligenceShellStateOwnsRequest
    ? intelligenceShellReportState.error
    : null;
  const currentIntelligenceShellMove = overview
    && currentSession?.session_id === sessionId
    && currentIntelligenceShellStatus === "ready"
    && trustedNavigationMove(intelligenceShellReportState.move, overview.run_id, {
      workflowId: currentGuidanceWorkflow?.workflow_id ?? null,
      workflowUpdatedAt: currentGuidanceWorkflowUpdatedAt,
    })
    ? intelligenceShellReportState.move
    : null;
  const eligiblePaceLaps = useMemo(
    () => overview?.laps.filter((lap) => bestUsefulLapMatchesRun(lap, overview.run_id)) ?? [],
    [overview],
  );
  const usefulLapCount = eligiblePaceLaps.length;
  const longestEligibleLapBlock = useMemo(
    () => longestContinuousEligibleLapBlock(eligiblePaceLaps),
    [eligiblePaceLaps],
  );
  const longRunLapsNeeded = Math.max(0, LONG_RUN_REVIEW_MIN_LAPS - longestEligibleLapBlock);
  const hasOverviewIntegrityBlocker = useMemo(
    () => overview?.warnings.some((warning) => /integrity|identity|mismatch|malformed|withheld/i.test(warning)) ?? false,
    [overview?.warnings],
  );
  const workspaceSignals = useMemo<Record<"overview" | "engineer" | "laps" | "platform_trace" | "setup_impact" | "dial_in", WorkspaceSignal>>(() => {
    const platformSignal: WorkspaceSignal = currentPlatformEventsLoadStatus === "loading"
      ? { tone: "loading", short: "Checking", detail: "Qualifying the selected lap's platform evidence." }
      : currentPlatformEventsLoadStatus === "ready"
        ? {
            tone: "attention",
            short: `${currentPlatformEvents.length} finding${currentPlatformEvents.length === 1 ? "" : "s"}`,
            detail: "Recorded platform findings are available for the selected lap.",
          }
        : currentPlatformEventsLoadStatus === "clear"
          ? { tone: "clear", short: "Clear", detail: "Supported platform checks found no reportable event on the selected lap." }
          : currentPlatformEventsLoadStatus === "error"
            ? { tone: "blocked", short: "Retry", detail: currentPlatformEventsLoadError ?? "Platform evidence could not be loaded." }
            : currentPlatformEventsLoadStatus === "unavailable"
              ? { tone: "blocked", short: "Limited", detail: currentPlatformEventsLoadError ?? "Required platform evidence is unavailable." }
              : { tone: "idle", short: "Select lap", detail: "Choose an eligible lap to qualify platform evidence." };
    const setupSnapshotReady = overview != null
      && setupSnapshotMatchesRun(overview.setup_snapshot, overview.run_id);
    const bestUsefulLapReady = overview != null
      && bestUsefulLapMatchesRun(overview.best_useful_lap, overview.run_id);
    const setupTechReady = overview?.session.setup_passed_tech !== false;
    const overviewBlockingWarnings = overview?.warnings.filter(overviewWarningBlocksDecision) ?? [];
    const overviewArchiveVerified = Boolean(
      telemetryCapabilities
      && telemetryCapabilities.cache_compatibility.status === "current"
      && telemetryCapabilities.capability_summary.lossless_archive_complete
      && telemetryCapabilities.capability_summary.warning_channels === 0,
    );
    const overviewDecisionContextReady = Boolean(
      usefulLapCount > 0
      && bestUsefulLapReady
      && setupSnapshotReady
      && setupTechReady
      && overviewArchiveVerified
      && overviewBlockingWarnings.length === 0,
    );
    const actionableOverviewFindings = overviewDecisionContextReady
      ? overview?.events.filter(telemetryEventIsActionable).length ?? 0
      : 0;
    const overviewSignal: WorkspaceSignal = usefulLapCount === 0 || !bestUsefulLapReady
      ? { tone: "blocked", short: "No eligible", detail: "No completed, useful lap can support a run conclusion." }
      : !setupSnapshotReady
        ? { tone: "blocked", short: "No setup", detail: "The current run has no identity-matched setup snapshot, so setup conclusions are withheld." }
        : !setupTechReady
          ? { tone: "blocked", short: "Tech failed", detail: "The recorded setup failed tech inspection; setup conclusions are withheld." }
          : !overviewArchiveVerified || overviewBlockingWarnings.length > 0
            ? {
                tone: "blocked",
                short: "No call",
                detail: overviewBlockingWarnings[0]
                  ?? telemetryCapabilities?.cache_compatibility.reason
                  ?? "Telemetry capability verification is unavailable or incomplete.",
              }
            : actionableOverviewFindings > 0
              ? {
                  tone: "attention",
                  short: `${actionableOverviewFindings} finding${actionableOverviewFindings === 1 ? "" : "s"}`,
                  detail: "Tuning-valid telemetry events are ready for evidence review.",
                }
              : { tone: "clear", short: "Hold", detail: "Qualified checks found no tuning-valid issue in this run." };
    return {
      overview: overviewSignal,
      engineer: currentControlledWorkflowAmbiguous
        ? { tone: "blocked", short: "Resolve", detail: "Multiple active workflows share this session; exact action authority is withheld." }
        : !overviewArchiveVerified || overviewBlockingWarnings.length > 0
          ? {
              tone: "blocked",
              short: "Recover",
              detail: overviewBlockingWarnings[0]
                ?? telemetryCapabilities?.cache_compatibility.reason
                ?? "Re-import the original telemetry before opening a current Smart Engineer briefing.",
            }
          : hasOverviewIntegrityBlocker || usefulLapCount === 0 || !bestUsefulLapReady
            ? { tone: "blocked", short: "Limited", detail: "Smart Engineer will stay measurement-only until the run qualifies." }
            : currentIntelligenceShellStatus === "checking" || currentIntelligenceShellStatus === "idle"
              ? { tone: "loading", short: "Checking", detail: "Loading the Smart Engineer briefing for the current run and lap scope." }
              : currentIntelligenceShellStatus === "error"
                ? {
                    tone: "blocked",
                    short: "Unavailable",
                    detail: currentIntelligenceShellError
                      ?? "Smart Engineer briefing is unavailable. Open Engineer and retry the current scope.",
                  }
                : currentControlledWorkflow?.packet.decision === "test"
                  ? { tone: "ready", short: "Test active", detail: "The run briefing includes the active controlled-test state." }
                  : currentControlledWorkflow?.packet.decision === "measure"
                    ? { tone: "attention", short: "Measure", detail: "The run briefing remains measurement-only until this workflow is closed." }
                    : { tone: "attention", short: "Review", detail: "Open the evidence-bound issue, causes, and best next measurement." },
      laps: overviewBlockingWarnings.length > 0
        ? {
            tone: "blocked",
            short: "No call",
            detail: overviewBlockingWarnings[0] ?? "Run integrity must be resolved before pace conclusions.",
          }
        : usefulLapCount > 0
        ? {
            tone: "ready",
            short: longRunLapsNeeded === 0
              ? `${usefulLapCount} clean · 10+ block`
              : `${usefulLapCount} clean · ${longestEligibleLapBlock}/${LONG_RUN_REVIEW_MIN_LAPS}`,
            detail: bestUsefulLapReady && overview?.best_useful_lap?.lap_time != null
              ? longRunLapsNeeded > 0
                ? `Best qualified lap ${overview.best_useful_lap.lap_number}: ${overview.best_useful_lap.lap_time.toFixed(3)} seconds. Longest clean block ${longestEligibleLapBlock}/${LONG_RUN_REVIEW_MIN_LAPS}; bank ${longRunLapsNeeded} more consecutive lap${longRunLapsNeeded === 1 ? "" : "s"} for long-run inspection.`
                : `Best qualified lap ${overview.best_useful_lap.lap_number}: ${overview.best_useful_lap.lap_time.toFixed(3)} seconds. A ${longestEligibleLapBlock}-lap clean block is available for long-run inspection.`
              : "Qualified laps are available for stint and comparison review.",
          }
        : { tone: "blocked", short: "No eligible", detail: "No completed, useful lap can support a lap or stint conclusion." },
      platform_trace: platformSignal,
      setup_impact: setupSnapshotReady
        ? overview.session.setup_passed_tech === false
          ? { tone: "blocked", short: "Tech failed", detail: "The recorded setup failed tech and cannot authorize a test." }
          : { tone: "ready", short: "Recorded", detail: "A setup snapshot is available for evidence-linked inspection." }
        : { tone: "blocked", short: "No snapshot", detail: "Garage values are unavailable; setup-specific conclusions stay limited." },
      dial_in: currentControlledWorkflowCatalogStatus === "checking"
        ? { tone: "loading", short: "Checking", detail: "Checking the server-owned workflow catalog for this session." }
        : currentControlledWorkflowCatalogStatus === "error"
          ? {
              tone: "blocked",
              short: "Unavailable",
              detail: currentControlledWorkflowCatalogError
                ?? "Controlled-test status is unavailable. Open Dial-In and retry before starting or resuming a workflow.",
            }
          : currentControlledWorkflowAmbiguous
            ? { tone: "blocked", short: "Resolve", detail: "Multiple active workflows are present; use Dial-In recovery before starting another diagnosis." }
            : currentControlledWorkflow?.packet.decision === "test"
              ? { tone: "ready", short: "Test active", detail: "Resume the exact server-owned A/B/A2 workflow." }
              : currentControlledWorkflow?.packet.decision === "measure"
                ? { tone: "attention", short: "Measure", detail: "Finish or explicitly abandon the evidence-collection workflow before starting another diagnosis." }
                : { tone: "idle", short: "Advisory", detail: "Describe the symptom; Dial-In will verify whether one test or measurement is justified." },
    };
  }, [currentControlledWorkflow, currentControlledWorkflowAmbiguous, currentControlledWorkflowCatalogError, currentControlledWorkflowCatalogStatus, currentIntelligenceShellError, currentIntelligenceShellStatus, currentPlatformEvents.length, currentPlatformEventsLoadError, currentPlatformEventsLoadStatus, hasOverviewIntegrityBlocker, longRunLapsNeeded, longestEligibleLapBlock, overview, telemetryCapabilities, usefulLapCount]);
  const signalWorkspace = selection.selectedWorkspace === "speed_delta" || selection.selectedWorkspace === "drag_scrub"
    ? "platform_trace"
    : selection.selectedWorkspace;
  const currentWorkspaceSignal = signalWorkspace in workspaceSignals
    ? workspaceSignals[signalWorkspace as keyof typeof workspaceSignals]
    : workspaceSignals.overview;
  const currentWorkspaceLabel = humanizeWorkspaceLabel(signalWorkspace);

  const openMapOverlay = useCallback(() => {
    void loadTrackMapOverlay();
    setMapOverlayZoomRange(latestMapOverlayZoomRangeRef.current);
    mapOverlayOpenRef.current = true;
    setMapOverlayOpen(true);
  }, []);

  const closeMapOverlay = useCallback(() => {
    mapOverlayOpenRef.current = false;
    setMapOverlayOpen(false);
  }, []);

  const clearCurrentRunState = useCallback(() => {
    setOverview(null);
    setSessionRunsLoading(false);
    setTrace(null);
    setTraceLoadState({ requestKey: null, status: "idle", error: null });
    setChannels([]);
    setChannelsHaveFullCatalog(false);
    setPlatformEvents([]);
    setPlatformEventsLoadState({ requestKey: null, status: "idle", error: null });
    setTelemetryCapabilities(null);
    setActiveControlledWorkflow(null);
    setGuidanceControlledWorkflow(null);
    setActiveControlledWorkflowRequestKey(null);
    setActiveControlledWorkflowAmbiguous(false);
    setControlledWorkflowCatalogState({ requestKey: null, status: "idle", error: null });
    setExplicitControlledWorkflowId(null);
    setIntelligenceShellReportState({ requestKey: null, status: "idle", move: null, error: null });
    invalidateIntelligenceAuthority();
    setTimelineOwnsKeyboard(false);
    latestMapOverlayZoomRangeRef.current = null;
    mapOverlayOpenRef.current = false;
    setMapOverlayZoomRange(null);
    setMapOverlayOpen(false);
    selectRun(null);
  }, [invalidateIntelligenceAuthority, selectRun]);

  const openIntelligenceShellMove = useCallback(() => {
    if (!overview || !currentIntelligenceShellMove || !trustedNavigationMove(currentIntelligenceShellMove, overview.run_id, {
      workflowId: currentGuidanceWorkflow?.workflow_id ?? null,
      workflowUpdatedAt: currentGuidanceWorkflowUpdatedAt,
    })) return;
    const target = intelligenceWorkspaceTarget(currentIntelligenceShellMove.workspace);
    const scope = intelligenceMoveScope(currentIntelligenceShellMove);
    if (!target || !scope) return;
    focusEvidence({
      runId: overview.run_id,
      lapNumber: scope.lap,
      lapScope: scope.kind,
      lapWindowStart: scope.windowStart,
      lapWindowEnd: scope.windowEnd,
      representativeLap: scope.kind === "lap_window" ? scope.lap : null,
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      zoneId: null,
      zoneLabel: scope.pctStart != null ? "Server-ranked window" : null,
      zoneStartPct: scope.pctStart,
      zoneEndPct: scope.pctEnd,
      channelId: null,
      system: null,
      selectionSource: "engineer",
      lockState: scope.pctStart != null ? "locked" : "none",
      trustTier: currentIntelligenceShellMove.authority,
      valueBasis: scope.kind === "lap_window" ? "selected_window" : scope.kind === "single_lap" ? "full_lap" : "run_level",
    }, target);
  }, [currentGuidanceWorkflow?.workflow_id, currentGuidanceWorkflowUpdatedAt, currentIntelligenceShellMove, focusEvidence, overview]);

  const handleMapOverlayZoomRangeChange = useCallback((nextRange: { startValue?: number; endValue?: number } | null) => {
    latestMapOverlayZoomRangeRef.current = nextRange;
    if (mapOverlayOpenRef.current) setMapOverlayZoomRange(nextRange);
  }, []);

  useEffect(() => {
    const genuinelyClearInRaceMode = selection.selectedMode === "race"
      && currentPlatformEventsLoadStatus === "clear";
    if (!genuinelyClearInRaceMode) void loadPriorityRail();
    if (priorityRailUsesOverlay) {
      if (genuinelyClearInRaceMode) setPriorityRailOpen(false);
      return;
    }
    setPriorityRailOpen(!genuinelyClearInRaceMode);
  }, [currentPlatformEventsLoadStatus, platformRequestKey, priorityRailUsesOverlay, selection.selectedMode]);

  useEffect(() => {
    const requestSeq = ++controlledWorkflowRequestSeqRef.current;
    const requestedWorkflowKey = controlledWorkflowRequestKey;
    const requestedRunId = overview?.run_id ?? null;
    const requestedSessionId = currentSession?.session_id ?? null;
    const explicitScope = new Set(controlledWorkflowScopeRunIds);
    let cancelled = false;
    let refreshSeq = 0;

    setActiveControlledWorkflow(null);
    setGuidanceControlledWorkflow(null);
    setActiveControlledWorkflowRequestKey(requestedWorkflowKey);
    setActiveControlledWorkflowAmbiguous(false);
    if (
      !requestedRunId
      || !requestedSessionId
      || requestedSessionId !== sessionId
      || !explicitScope.has(requestedRunId)
    ) {
      setControlledWorkflowCatalogState({ requestKey: requestedWorkflowKey, status: "idle", error: null });
      return undefined;
    }
    setControlledWorkflowCatalogState({ requestKey: requestedWorkflowKey, status: "checking", error: null });

    const touchesRuns = (
      workflow: Pick<ControlledWorkflow, "source_run_id" | "stage_run_ids">,
      runIds: ReadonlySet<string>,
    ) => (
      runIds.has(workflow.source_run_id)
      || Object.values(workflow.stage_run_ids).some((runId) => runId != null && runIds.has(runId))
    );
    const isActiveWorkflow = (workflow: Pick<ControlledWorkflow, "status">) => (
      workflow.status !== "scored"
      && workflow.status !== "cancelled"
    );

    const detailsByRevision = new Map<string, ControlledWorkflow>();
    const refreshWorkflow = async () => {
      const currentRefresh = ++refreshSeq;
      try {
        const workflows = await fetchControlledWorkflowCatalog(
          requestedSessionId, requestedRunId,
        );
        if (
          cancelled
          || requestSeq !== controlledWorkflowRequestSeqRef.current
          || currentRefresh !== refreshSeq
        ) return;

        setControlledWorkflowCatalogState({ requestKey: requestedWorkflowKey, status: "ready", error: null });

        const scopedActiveWorkflows = workflows.filter((workflow) => (
          isActiveWorkflow(workflow) && touchesRuns(workflow, explicitScope)
        ));
        if (scopedActiveWorkflows.length > 1) {
          setActiveControlledWorkflowRequestKey(requestedWorkflowKey);
          setActiveControlledWorkflow(null);
          setGuidanceControlledWorkflow(null);
          setActiveControlledWorkflowAmbiguous(true);
          return;
        }

        setActiveControlledWorkflowAmbiguous(false);
        const uniqueScopedActiveCatalog = scopedActiveWorkflows[0] ?? null;
        const currentRun = new Set([requestedRunId]);
        const directlyRelatedCatalog = uniqueScopedActiveCatalog && touchesRuns(uniqueScopedActiveCatalog, currentRun)
          ? uniqueScopedActiveCatalog
          : null;
        const scoredRelatedCatalog = workflows.find((workflow) => (
          workflow.status === "scored" && touchesRuns(workflow, currentRun)
        )) ?? null;
        const detailTargets = [directlyRelatedCatalog, scoredRelatedCatalog, uniqueScopedActiveCatalog]
          .filter((item): item is NonNullable<typeof item> => item != null)
          .filter((item, index, values) => (
            values.findIndex((candidate) => candidate.workflow_id === item.workflow_id) === index
          ));
        const detailEntries = await Promise.all(detailTargets.map(async (item) => {
          const revisionKey = `${item.workflow_id}:${item.revision_sha256}`;
          const cached = detailsByRevision.get(revisionKey);
          if (cached) return [item.workflow_id, cached] as const;
          const detail = await fetchControlledWorkflow(item.workflow_id);
          if (detail.workflow_id !== item.workflow_id || detail.updated_at !== item.updated_at) {
            throw new Error("Controlled-workflow detail changed while its catalog revision was loading.");
          }
          detailsByRevision.set(revisionKey, detail);
          return [item.workflow_id, detail] as const;
        }));
        if (
          cancelled
          || requestSeq !== controlledWorkflowRequestSeqRef.current
          || currentRefresh !== refreshSeq
        ) return;
        const details = new Map(detailEntries);
        const directlyRelated = directlyRelatedCatalog
          ? details.get(directlyRelatedCatalog.workflow_id) ?? null
          : null;
        const scoredRelated = scoredRelatedCatalog
          ? details.get(scoredRelatedCatalog.workflow_id) ?? null
          : null;
        const uniqueScopedActiveWorkflow = uniqueScopedActiveCatalog
          ? details.get(uniqueScopedActiveCatalog.workflow_id) ?? null
          : null;
        setGuidanceControlledWorkflow(directlyRelated ?? scoredRelated);
        if (directlyRelated) {
          setActiveControlledWorkflowRequestKey(requestedWorkflowKey);
          setActiveControlledWorkflow(directlyRelated);
          return;
        }

        let handedOff: ControlledWorkflow | null = null;
        if (requestedSessionId && explicitScope.has(requestedRunId)) {
          try {
            const workflowId = window.sessionStorage.getItem(
              `racerzlab:controlled-workflow-handoff:${requestedSessionId}`,
            );
            if (workflowId && uniqueScopedActiveWorkflow?.workflow_id === workflowId) {
              handedOff = uniqueScopedActiveWorkflow;
            }
          } catch {
            handedOff = null;
          }
        }
        setActiveControlledWorkflowRequestKey(requestedWorkflowKey);
        setActiveControlledWorkflow(handedOff ?? uniqueScopedActiveWorkflow);
      } catch (catalogError) {
        if (
          !cancelled
          && requestSeq === controlledWorkflowRequestSeqRef.current
          && currentRefresh === refreshSeq
        ) {
            setControlledWorkflowCatalogState({
              requestKey: requestedWorkflowKey,
              status: "error",
              error: controlledWorkflowCatalogRecovery(catalogError),
            });
            setActiveControlledWorkflowRequestKey(requestedWorkflowKey);
            setActiveControlledWorkflow(null);
            setGuidanceControlledWorkflow(null);
            setActiveControlledWorkflowAmbiguous(false);
        }
      }
    };

    void refreshWorkflow();
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refreshWorkflow();
    };
    const refreshTimer = window.setInterval(refreshWhenVisible, 10_000);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      cancelled = true;
      if (refreshTimer != null) window.clearInterval(refreshTimer);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [
    controlledWorkflowScopeKey,
    controlledWorkflowRequestKey,
    currentSession?.session_id,
    overview?.run_id,
    sessionId,
  ]);

  useEffect(() => {
    const requestSeq = ++intelligenceShellRequestSeqRef.current;
    const requestKey = intelligenceShellRequestKey;
    const requestedRunId = overview?.run_id ?? null;
    const requestedSessionId = currentSession?.session_id ?? null;
    let cancelled = false;
    setIntelligenceShellReportState({
      requestKey,
      status: intelligenceShellCanLoad ? "checking" : "idle",
      move: null,
      error: null,
    });
    if (!intelligenceShellCanLoad || !requestedRunId || !requestedSessionId || requestedSessionId !== sessionId) return undefined;

    void fetchRunIntelligence(requestedRunId, {
      sessionId: requestedSessionId,
      refreshKey: requestKey,
    })
      .then((report) => {
        if (cancelled || requestSeq !== intelligenceShellRequestSeqRef.current) return;
        const exactReportScope = report.run_id === requestedRunId
          && (report.session_id ?? null) === requestedSessionId;
        if (!exactReportScope) {
          setIntelligenceShellReportState({
            requestKey,
            status: "error",
            move: null,
            error: "Smart Engineer returned a briefing for a different run or session. Open Engineer and retry the current scope.",
          });
          return;
        }
        const move = report.next_trustworthy_move?.authority === "navigation_only"
          && trustedNavigationMove(report.next_trustworthy_move, requestedRunId, {
            workflowId: currentGuidanceWorkflow?.workflow_id ?? null,
            workflowUpdatedAt: currentGuidanceWorkflowUpdatedAt,
          })
          ? report.next_trustworthy_move
          : null;
        setIntelligenceShellReportState({ requestKey, status: "ready", move, error: null });
      })
      .catch((requestError: unknown) => {
        if (!cancelled && requestSeq === intelligenceShellRequestSeqRef.current) {
          setIntelligenceShellReportState({
            requestKey,
            status: "error",
            move: null,
            error: intelligenceShellRecovery(requestError),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currentGuidanceWorkflow?.workflow_id, currentGuidanceWorkflowUpdatedAt, currentSession?.session_id, intelligenceShellCanLoad, intelligenceShellRequestKey, overview?.run_id, sessionId]);

  useEffect(() => {
    const requestSeq = ++intelligenceAuthorityRequestSeqRef.current;
    const requestKey = intelligenceAuthorityRequestKey;
    const requestedWorkflow = currentAuthorityWorkflow;
    const requestedSourceRunId = requestedWorkflow?.source_run_id ?? null;
    const requestedSessionId = currentSession?.session_id ?? null;
    let cancelled = false;
    setIntelligenceAuthorityReportState({
      requestKey,
      status: intelligenceAuthorityCanLoad ? "checking" : "idle",
      authority: null,
      error: null,
    });
    if (
      !intelligenceAuthorityCanLoad
      || !requestedWorkflow
      || !requestedSourceRunId
      || !requestedSessionId
      || requestedSessionId !== sessionId
    ) return undefined;

    void fetchRunIntelligence(requestedSourceRunId, {
      sessionId: requestedSessionId,
      refreshKey: `current-authority:${requestKey}`,
    })
      .then((report) => {
        if (cancelled || requestSeq !== intelligenceAuthorityRequestSeqRef.current) return;
        const authority = deriveCurrentIntelligenceAuthority(
          report,
          requestedWorkflow,
          requestedSourceRunId,
          requestedSessionId,
        );
        setIntelligenceAuthorityReportState({
          requestKey,
          status: authority ? "authorized" : "withheld",
          authority,
          error: authority ? null : CURRENT_INTELLIGENCE_AUTHORITY_RECOVERY,
        });
      })
      .catch(() => {
        if (!cancelled && requestSeq === intelligenceAuthorityRequestSeqRef.current) {
          setIntelligenceAuthorityReportState({
            requestKey,
            status: "error",
            authority: null,
            error: "Current source-run intelligence is unavailable. Review in Engineer, abandon the stale workflow if needed, or retry before recording Stage B.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [currentAuthorityWorkflow?.workflow_id, currentAuthorityWorkflowUpdatedAt, currentSession?.session_id, intelligenceAuthorityCanLoad, intelligenceAuthorityRequestKey, sessionId]);

  useEffect(() => {
    let cancelled = false;
    const deadline = Date.now() + 30_000;

    const pollHealth = async () => {
      while (!cancelled && Date.now() < deadline) {
        try {
          const health = await fetchHealth();
          if (health.status === "ok") {
            setEngineStatus("ready");
            return;
          }
        } catch {
          // The local engine may still be starting.
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      if (!cancelled) setEngineStatus("failed");
    };

    void pollHealth();
    return () => {
      cancelled = true;
    };
  }, []);

  const toCatalogShape = useCallback((channel: Partial<ChannelCatalogItem> & { name: string }): ChannelCatalogItem => ({
    name: channel.name,
    label: channel.label ?? channel.name,
    description: channel.description ?? null,
    unit: channel.unit ?? null,
    type: channel.type ?? null,
    count: channel.count ?? 1,
    is_raw: Boolean(channel.is_raw),
    is_calculated: Boolean(channel.is_calculated),
    is_proxy: Boolean(channel.is_proxy),
    formula: channel.formula ?? null,
    dependencies: channel.dependencies ?? [],
    used_by_charts: channel.used_by_charts ?? [],
    used_by_events: channel.used_by_events ?? [],
    used_by_analyses: channel.used_by_analyses ?? [],
    min: channel.min ?? null,
    max: channel.max ?? null,
    mean: channel.mean ?? null,
    sample_value: channel.sample_value ?? null,
    missing_status: channel.missing_status ?? null,
    group: channel.group ?? null,
    source: channel.source ?? null,
  }), []);

  // ── keyboard shortcuts ─────────────────────────────────────
  useKeyboardShortcuts(currentPlatformEvents, setWorkspace, {
    onTogglePriorityRail: () => {
      if (priorityRailMustStayOpen) setPriorityRailOpen(true);
      else if (priorityRailExpanded) closePriorityRail();
      else openPriorityRail();
    },
    onToggleInspector: () => {
      void loadEvidenceInspector();
      setInspectorOpen((open) => !open);
    },
    onToggleMapOverlay: () => {
      if (mapOverlayOpenRef.current) closeMapOverlay();
      else openMapOverlay();
    },
    onShowShortcuts: () => setShortcutsOpen(true),
    onHideShortcuts: () => setShortcutsOpen(false),
    shortcutsOpen,
    eventTimelineOwnsKeyboard: timelineOwnsKeyboard,
  });

  useEffect(() => {
    const previousWorkspace = previousWorkspaceRef.current;
    previousWorkspaceRef.current = selection.selectedWorkspace;
    if (previousWorkspace === "dial_in" && selection.selectedWorkspace !== "dial_in") {
      setExplicitControlledWorkflowId(null);
    }
  }, [selection.selectedWorkspace]);

  useEffect(() => {
    if (!shortcutsOpen) return undefined;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusFrame = requestAnimationFrame(() => shortcutModalCloseRef.current?.focus());
    const trapTab = (event: KeyboardEvent) => {
      if (event.key !== "Tab" || !shortcutModalRef.current) return;
      const focusable = [...shortcutModalRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )];
      if (focusable.length === 0) {
        event.preventDefault();
        shortcutModalRef.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", trapTab);
    return () => {
      cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", trapTab);
      previouslyFocused?.focus();
    };
  }, [shortcutsOpen]);

  // ── load a run ──────────────────────────────────────────────
  const loadSelectedRun = useCallback(
    async (runId: string, errorScope: "general" | "session_open" = "general") => {
      const seq = ++loadSelectedRunSeqRef.current;
      invalidateIntelligenceAuthority();
      setLoading(true);
      setError(null);
      setTelemetryCapabilities(null);
      try {
        const base = await fetchOverview(runId);
        if (base.run_id !== runId || base.session.run_id !== runId) {
          throw new Error("The run overview response did not match the requested run. Reload the run before reviewing evidence.");
        }
        const baseBestUsefulLap = base.best_useful_lap;
        const bestLap = bestUsefulLapMatchesRun(baseBestUsefulLap, runId)
          ? baseBestUsefulLap.lap_number
          : undefined;
        const [laps, events, setup, channelCatalog, capabilityPayload] = await Promise.all([
          fetchLaps(runId).catch(() => base.laps),
          fetchEvents(runId).catch(() => base.events),
          fetchSetup(runId).catch(() => base.setup_snapshot ?? null),
          fetchChannelSummary(runId).catch(() => []),
          fetchTelemetryCapabilities(runId).catch(() => null),
        ]);
        if (seq !== loadSelectedRunSeqRef.current) return false;
        const safeLaps = laps.filter((lap) => lap.run_id === runId);
        const safeEvents = events.filter((event) => event.run_id === runId);
        const safeBestUsefulLap = bestUsefulLapMatchesRun(baseBestUsefulLap, runId)
          ? baseBestUsefulLap
          : null;
        const setupMatchesRun = setupSnapshotMatchesRun(setup, runId);
        const capabilityMatchesRun = capabilityPayload?.run_id === runId;
        const nestedIdentityWarnings = [
          ...(safeLaps.length !== laps.length
            ? ["Lap response identity mismatch. Cross-run lap rows were withheld."]
            : []),
          ...(safeEvents.length !== events.length
            ? ["Event response identity mismatch. Cross-run events were withheld."]
            : []),
          ...(baseBestUsefulLap != null && safeBestUsefulLap == null
            ? ["Best-lap identity or eligibility mismatch. The best-lap conclusion was withheld."]
            : []),
          ...(setup != null && !setupMatchesRun
            ? ["Setup snapshot identity mismatch. Setup conclusions are withheld for this run."]
            : []),
          ...(capabilityPayload != null && !capabilityMatchesRun
            ? ["Telemetry capability identity mismatch. Archive-derived conclusions are withheld for this run."]
            : []),
        ];
        const derivedIdentityMismatch = nestedIdentityWarnings.length > 0;
        setOverview({
          ...base,
          best_useful_lap: safeBestUsefulLap,
          laps: safeLaps,
          events: safeEvents,
          setup_snapshot: setupMatchesRun ? setup : null,
          primary_findings: derivedIdentityMismatch ? [] : base.primary_findings,
          warnings: [...base.warnings, ...nestedIdentityWarnings],
        });
        setChannels(channelCatalog.map((item) => toCatalogShape(item)));
        setChannelsHaveFullCatalog(false);
        setTelemetryCapabilities(capabilityMatchesRun ? capabilityPayload : null);
        setTrace(null);
        setPlatformEvents([]);
        loadRun(runId, bestLap ?? null);
        return true;
      } catch (caught) {
        if (seq !== loadSelectedRunSeqRef.current) return false;
        const message = caught instanceof Error ? caught.message : "Failed to load run.";
        if (errorScope === "session_open") setSessionOpenError(message);
        else setError(message);
        return false;
      } finally {
        if (seq === loadSelectedRunSeqRef.current) setLoading(false);
      }
    },
    [invalidateIntelligenceAuthority, loadRun, toCatalogShape],
  );

  const openAttachedSessionRun = useCallback((runId: string) => {
    if (currentSession && !attachedSessionRunIds.has(runId)) {
      setError("That run is not attached to the open session.");
      return;
    }
    setError(null);
    void loadSelectedRun(runId);
  }, [attachedSessionRunIds, currentSession, loadSelectedRun]);

  const openIntelligenceCitation = useCallback(async (citation: IntelligenceCitation) => {
    if (!INTELLIGENCE_CITATION_WORKSPACES.has(citation.workspace)) {
      setError("That evidence link named an unsupported workspace, so it was not opened.");
      return;
    }
    if (currentSession && !attachedSessionRunIds.has(citation.run_id)) {
      setError("That evidence source is not attached to the open session, so the current run was left unchanged.");
      return;
    }
    const citationLap = typeof citation.lap_number === "number"
      && Number.isInteger(citation.lap_number)
      && citation.lap_number >= 0
      ? citation.lap_number
      : null;
    const citationLapPct = typeof citation.lap_pct === "number"
      && Number.isFinite(citation.lap_pct)
      && citation.lap_pct >= 0
      && citation.lap_pct <= 100
      ? citation.lap_pct
      : null;
    if (overview?.run_id !== citation.run_id) {
      const loaded = await loadSelectedRun(citation.run_id);
      if (!loaded) return;
    }
    const citationZoneEvidence = citation.run_id === selection.selectedRunId
      ? buildZoneEvidence(selection, { lapPct: citationLapPct })
      : { zoneId: null, zoneLabel: null, zoneStartPct: null, zoneEndPct: null };
    setError(null);
    dispatch({ type: "SELECT_SETUP_KEY", setupKey: null });
    focusEvidence({
      runId: citation.run_id,
      lapNumber: citationLap,
      lapScope: citationLap != null ? "single_lap" : "run",
      eventId: citation.event_id ?? null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: citationLapPct,
      ...citationZoneEvidence,
      channelId: null,
      selectionSource: "engineer",
      lockState: citationLapPct != null || citation.event_id ? "locked" : "none",
      trustTier: citation.evidence_state,
      valueBasis: citationLapPct != null ? "selected_sample" : citationLap != null ? "full_lap" : "run_level",
    }, citation.workspace);
  }, [attachedSessionRunIds, currentSession, dispatch, focusEvidence, loadSelectedRun, overview?.run_id, selection]);

  // ── session management (defined after loadSelectedRun to avoid hoisting issues) ──
  const refreshSessionRuns = useCallback(async (sid: string, expectedRunIds: readonly string[]) => {
    const requestSeq = ++sessionRunsRequestSeqRef.current;
    let identityMismatch = false;
    setSessionRunsLoading(true);
    try {
      const scopedRuns = await fetchSessionRunList(sid);
      if (requestSeq !== sessionRunsRequestSeqRef.current) return [];
      if (!sessionRunListMatchesMembership(scopedRuns, expectedRunIds)) {
        identityMismatch = true;
        throw new Error("The session run list did not match the selected session membership.");
      }
      setSessionRuns(scopedRuns);
      return scopedRuns;
    } catch (caught) {
      if (requestSeq !== sessionRunsRequestSeqRef.current) return [];
      setSessionRuns([]);
      if (identityMismatch) throw caught;
      return [];
    } finally {
      if (requestSeq === sessionRunsRequestSeqRef.current) setSessionRunsLoading(false);
    }
  }, []);

  const handleSessionSelected = useCallback(async (
    sid: string,
    source: SessionSelectionSource,
    exactRunId?: string,
  ): Promise<boolean> => {
    const selectionSeq = ++sessionSelectionSeqRef.current;
    sessionRunsRequestSeqRef.current += 1;
    loadSelectedRunSeqRef.current += 1;
    importOpenIntentRef.current += 1;
    const isLatestSelection = () => selectionSeq === sessionSelectionSeqRef.current;
    clearCurrentRunState();
    setSessionId(sid);
    setSessionSelectionSource(source);
    setCurrentSession(null);
    setSessionRuns([]);
    setSessionToolsOpen(false);
    setLoading(true);
    setError(null);
    setSessionOpenError(null);
    try {
      const session = await fetchSession(sid);
      if (!isLatestSelection()) return false;
      if (!sessionPayloadMatchesRequest(session, sid)) {
        throw new Error("The session response did not match the session that was selected.");
      }
      if (exactRunId && !session.run_ids.includes(exactRunId)) {
        throw new Error("The requested historical evidence run is not attached to its recorded session.");
      }
      setCurrentSession(session);
      const [recentRuns] = await Promise.all([
        fetchRunList().catch(() => []),
        refreshSessionRuns(sid, session.run_ids),
      ]);
      if (!isLatestSelection()) return false;
      setRuns(recentRuns);
      if (session.run_ids.length > 0) {
        void loadOverviewTab();
        void loadEventTimeline();
        const loaded = await loadSelectedRun(
          exactRunId ?? session.run_ids[session.run_ids.length - 1],
          "session_open",
        );
        return loaded && isLatestSelection();
      } else {
        if (isLatestSelection()) setLoading(false);
        return exactRunId == null;
      }
    } catch (caught) {
      if (!isLatestSelection()) return false;
      setCurrentSession(null);
      setSessionRuns([]);
      setSessionOpenError(caught instanceof Error ? caught.message : "The session could not be opened.");
      setLoading(false);
      return false;
    }
  }, [clearCurrentRunState, loadSelectedRun, refreshSessionRuns]);

  const openCrewChiefEvidence = useCallback(async (target: CrewChiefEvidenceEntry | LearningEvidenceReference) => {
    const learningReference = "provenance" in target ? target : null;
    if (!("provenance" in target) && target.producer_id === "p33.engineering_experience") {
      setError("Historical evidence must be opened from its typed Engineering Memory source reference.");
      return;
    }
    if (learningReference?.state === "unavailable") {
      setError(learningReference.blocker_reasons.join(" ") || "That historical telemetry source is unavailable.");
      return;
    }
    const provenance = learningReference?.provenance ?? null;
    const sourceRunId = provenance?.run_id ?? (target as CrewChiefEvidenceEntry).source_run_id;
    const sourceSessionId = provenance?.session_id ?? (target as CrewChiefEvidenceEntry).source_session_id;
    const sourceSetupId = provenance?.setup_id ?? (target as CrewChiefEvidenceEntry).source_setup_id;
    const sourceSetupHash = provenance?.setup_snapshot_sha256 ?? (target as CrewChiefEvidenceEntry).source_setup_sha256;
    const sourceBuildHash = provenance?.build_context_sha256 ?? (target as CrewChiefEvidenceEntry).source_build_context_sha256;
    const sourceProvenanceAvailable = provenance !== null || (target as CrewChiefEvidenceEntry).source_provenance_available;
    if (
      !sourceSessionId
      || !sourceProvenanceAvailable
      || !sourceSetupId
      || !sourceSetupHash
      || !sourceBuildHash
    ) {
      setError("That Crew Chief evidence source has incomplete provenance, so the current run was left unchanged.");
      return;
    }
    const sameSession = currentSession?.session_id === sourceSessionId;
    if (sameSession) {
      if (!attachedSessionRunIds.has(sourceRunId)) {
        setError("That Crew Chief evidence source is not attached to its saved session, so the current run was left unchanged.");
        return;
      }
    } else {
      try {
        const sourceSession = await fetchSession(sourceSessionId);
        if (
          !sessionPayloadMatchesRequest(sourceSession, sourceSessionId)
          || !sourceSession.run_ids.includes(sourceRunId)
        ) {
          setError("That Crew Chief evidence source does not belong to its recorded session, so the current run was left unchanged.");
          return;
        }
      } catch {
        setError("The recorded Crew Chief evidence session could not be verified, so the current run was left unchanged.");
        return;
      }
    }
    try {
      const sourceReport = await fetchRunIntelligence(sourceRunId, { sessionId: sourceSessionId });
      const runtimeIdentity = sourceReport.vehicle_systems?.runtime_identity;
      const runtimeHash = runtimeIdentity ? await canonicalJsonSha256(runtimeIdentity) : null;
      if (
        sourceReport.run_id !== sourceRunId
        || sourceReport.session_id !== sourceSessionId
        || sourceReport.setup_id !== sourceSetupId
        || sourceReport.setup_snapshot_sha256 !== sourceSetupHash
        || runtimeHash === null
        || runtimeHash !== sourceBuildHash
      ) {
        setError("That historical telemetry source no longer matches its saved setup and build identity, so the current run was left unchanged.");
        return;
      }
    } catch {
      setError("The recorded Crew Chief evidence identity could not be verified, so the current run was left unchanged.");
      return;
    }
    if (sameSession) {
      if (overview?.run_id !== sourceRunId) {
        const loaded = await loadSelectedRun(sourceRunId);
        if (!loaded) return;
      }
    } else {
      const loaded = await handleSessionSelected(sourceSessionId, "existing", sourceRunId);
      if (!loaded) return;
    }
    const lapNumbers = provenance ? provenance.lap_numbers : (target as CrewChiefEvidenceEntry).lap_numbers;
    const lapPctStart = provenance ? provenance.lap_pct_start : (target as CrewChiefEvidenceEntry).lap_pct_start;
    const lapPctEnd = provenance ? provenance.lap_pct_end : (target as CrewChiefEvidenceEntry).lap_pct_end;
    const phase = provenance ? provenance.phase : (target as CrewChiefEvidenceEntry).phase;
    const sourceChannels = provenance ? provenance.source_channels : (target as CrewChiefEvidenceEntry).source_channels;
    const producerId = provenance ? provenance.producer_id : (target as CrewChiefEvidenceEntry).producer_id;
    const artifactId = provenance ? provenance.artifact_id : (target as CrewChiefEvidenceEntry).artifact_id;
    const componentId = provenance ? null : (target as CrewChiefEvidenceEntry).component_ids[0] ?? null;
    const lap = lapNumbers[0] ?? null;
    const hasWindow = lapPctStart != null && lapPctEnd != null;
    const midpoint = hasWindow ? (lapPctStart + lapPctEnd) / 2 : null;
    setError(null);
    dispatch({ type: "SELECT_SETUP_KEY", setupKey: null });
    focusEvidence({
      runId: sourceRunId,
      lapNumber: lap,
      lapScope: hasWindow ? "track_zone" : lap == null ? "run" : "single_lap",
      lapWindowStart: null,
      lapWindowEnd: null,
      representativeLap: null,
      eventId: null,
      producerId,
      artifactId,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: midpoint,
      zoneId: hasWindow ? `crew:${producerId}:${artifactId}` : null,
      zoneLabel: phase,
      zoneStartPct: lapPctStart,
      zoneEndPct: lapPctEnd,
      channelId: sourceChannels[0] ?? null,
      system: componentId,
      sourceRunId,
      sourceSetupId,
      selectionSource: "engineer",
      lockState: hasWindow ? "locked" : "none",
      trustTier: "navigation_only",
      valueBasis: hasWindow ? "selected_window" : lap == null ? "run_level" : "full_lap",
    }, "platform_trace");
  }, [attachedSessionRunIds, currentSession?.session_id, dispatch, focusEvidence, handleSessionSelected, loadSelectedRun, overview?.run_id]);

  // ── import ──────────────────────────────────────────────────
  const [importStage, setImportStage] = useState<string | null>(null);

  const openImportedRun = useCallback(
    async (runId?: string | null, trackMap?: TrackMapResolution | null, expectedIntent = importOpenIntentRef.current): Promise<boolean> => {
      if (expectedIntent !== importOpenIntentRef.current) return false;
      const isLatestImportIntent = () => expectedIntent === importOpenIntentRef.current;
      setError(null);
      setStatus(null);

      importDebug.start("sessions_refresh_started", { runId, track_map_status: trackMap?.status });
      let sessionAttachFailed = false;
      let expectedSessionRunIds = currentSession?.session_id === sessionId
        ? currentSession.run_ids
        : null;
      if (sessionId && runId) {
        const updatedSession = await addRunToSession(sessionId, runId).catch((caught) => {
          importDebug.error(
            "sessions_refresh_started",
            caught instanceof Error ? caught.message : "Could not attach run to session.",
            { sessionId, runId },
          );
          return null;
        });
        if (!isLatestImportIntent()) return false;
        if (updatedSession?.session_id === sessionId && updatedSession.run_ids.includes(runId)) {
          setCurrentSession(updatedSession);
          expectedSessionRunIds = updatedSession.run_ids;
        } else {
          sessionAttachFailed = true;
        }
      }
      let recentRuns: RunListItem[];
      try {
        [recentRuns] = await Promise.all([
          fetchRunList(),
          sessionId && expectedSessionRunIds
            ? refreshSessionRuns(sessionId, expectedSessionRunIds)
            : Promise.resolve([]),
        ]);
      } catch (caught) {
        if (!isLatestImportIntent()) return false;
        const detail = caught instanceof Error ? caught.message : "The local run library could not be refreshed.";
        throw new Error([
          "Import saved",
          "The telemetry run was imported and saved, but the local session library could not refresh.",
          "Return to Sessions and reopen this session. If the run is not listed, choose the same .ibt file once to retry attachment.",
          `Technical detail: ${detail}`,
        ].join("\n"));
      }
      if (!isLatestImportIntent()) return false;
      setRuns(recentRuns);
      importDebug.success("sessions_refresh_finished", { run_count: recentRuns.length });

      if (sessionAttachFailed) {
        throw new Error([
          "Import saved",
          "The telemetry run was imported and saved, but it could not be attached to the open session.",
          "The current session was left unchanged.",
          "Choose the same .ibt file again to retry the attachment. RacerZLab will reuse the saved run instead of creating a duplicate.",
        ].join("\n"));
      }

      if (!runId) {
        // Track-map-only import: suppress success message in normal UI
        // Only show if there's an actual error or ambiguity
        if (trackMap?.status === "matched") {
          setStatus(null);
        } else {
          setStatus(trackMap?.message ?? null);
        }
        return true;
      }

      importDebug.start("open_imported_run_started", { runId });
      if (!isLatestImportIntent()) return false;
      setWorkspace("overview", "manual");
      const opened = await loadSelectedRun(runId);
      if (!isLatestImportIntent()) return false;
      if (!opened) {
        throw new Error([
          "Import saved",
          "The telemetry run was imported and saved, but the cockpit could not verify and open it.",
          "Review run health or open the saved run from Sessions. You do not need to import it again.",
        ].join("\n"));
      }
      importDebug.success("open_imported_run_finished", { runId });
      // Suppress success messages for normal auto-resolution
      setStatus(null);
      return true;
    },
    [currentSession, loadSelectedRun, refreshSessionRuns, sessionId, setWorkspace],
  );

  const handleFileSelected = useCallback(async (file: File | null) => {
    if (!file) return;
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext === "ibt") invalidateIntelligenceAuthority();
    const expectedIntent = importOpenIntentRef.current;
    const isLatestImportIntent = () => expectedIntent === importOpenIntentRef.current;
    setImporting(true);
    setError(null);
    setStatus(null);
    setImportOutcome(null);
    setImportStage("Opening file…");
    try {
      if (ext === "mt2") {
        setImportStage("Reading track map...");
        const entry = await importMt2File(file);
        if (!isLatestImportIntent()) return;
        setImportStage("Saving local map index...");
        const dupNote = entry.import_status === "already_indexed" ? " (already indexed; refreshed cache)" : "";
        setStatus(`Imported track map: ${entry.points_count?.toLocaleString()} centerline points, ${entry.markers_count} markers, ${entry.sections_count} sections.${dupNote}`);
        setImportOutcome("map");
        setImportStage(null);
        setImporting(false);
        setLoading(false);
        return true;
      }
      setImportStage("Reading .ibt and decoding telemetry...");
      const result = await importIbtFile(file);
      if (!isLatestImportIntent()) return;
      if (ext === "ibt" && !result.run_id) {
        setError([
          "Import failed",
          result.status.message || "The telemetry file could not be processed.",
          "No completed run was created.",
          "Try importing again, or choose a different .ibt file.",
        ].join("\n"));
        setImportStage(null);
        return true;
      }
      if (result.run_id) {
        setImportStage("Normalizing channels, building laps/events, and writing cache...");
      }
      setImportStage("Opening cockpit...");
      const opened = await openImportedRun(result.run_id, result.track_map ?? null, expectedIntent);
      if (!isLatestImportIntent()) return;
      if (!opened) return;
      setImportOutcome("run");
      setSessionToolsOpen(false);
      if (result.existing_run_updated) {
        setStatus("Existing run updated. Duplicate telemetry detected - updated the existing run record.");
      }
      setImportStage(null);
    } catch (caught) {
      if (!isLatestImportIntent()) return;
      setError(caught instanceof Error ? caught.message : [
        "Import failed",
        "The telemetry file could not be processed.",
        "No completed run was created.",
        "Try importing again, or choose a different .ibt file.",
      ].join("\n"));
      setImportOutcome(null);
      setImportStage(null);
    } finally {
      if (isLatestImportIntent()) {
        setImporting(false);
        setLoading(false);
      }
    }
  }, [invalidateIntelligenceAuthority, openImportedRun]);

  const leaveCurrentSession = useCallback(() => {
    sessionSelectionSeqRef.current += 1;
    sessionRunsRequestSeqRef.current += 1;
    loadSelectedRunSeqRef.current += 1;
    importOpenIntentRef.current += 1;
    clearCurrentRunState();
    setSessionId(null);
    setSessionSelectionSource(null);
    setCurrentSession(null);
    setSessionRuns([]);
    setSessionToolsOpen(false);
    setError(null);
    setSessionOpenError(null);
    setStatus(null);
    setImportOutcome(null);
    setImportStage(null);
    setImporting(false);
    setLoading(false);
  }, [clearCurrentRunState]);

  const handleImportClick = useCallback(() => {
    const input = fileInputRef.current;
    if (!input) return;
    input.value = "";
    input.click();
  }, []);

  useEffect(() => {
    if (!overview || platformTargetLap == null || platformRequestKey == null) {
      setPlatformEvents([]);
      setPlatformEventsLoadState({ requestKey: null, status: "idle", error: null });
      return;
    }
    let cancelled = false;
    setPlatformEvents([]);
    setPlatformEventsLoadState({ requestKey: platformRequestKey, status: "loading", error: null });
    fetchPlatformEventsReport(overview.run_id, { lap: platformTargetLap })
      .then((report) => {
        if (cancelled) return;
        const responseMatchesScope = report.run_id === overview.run_id
          && report.lap === platformTargetLap
          && report.events.every((event) => event.lap === platformTargetLap);
        if (!responseMatchesScope) {
          setPlatformEvents([]);
          setPlatformEventsLoadState({
            requestKey: platformRequestKey,
            status: "error",
            error: "Platform findings did not match the selected run and lap.",
          });
          return;
        }
        setPlatformEvents(report.events);
        setPlatformEventsLoadState({
          requestKey: platformRequestKey,
          status: report.evidence_status === "findings" ? "ready" : report.evidence_status,
          error: report.blocker_reasons.join(" ") || null,
        });
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setPlatformEvents([]);
        setPlatformEventsLoadState({
          requestKey: platformRequestKey,
          status: "error",
          error: caught instanceof Error ? caught.message : "Platform events could not be loaded.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [overview, platformEventsRetryToken, platformRequestKey, platformTargetLap]);

  useEffect(() => {
    if (!overview || !isTraceWorkspace || platformTargetLap == null || platformRequestKey == null) return;

    let cancelled = false;
    setTrace(null);
    setTraceLoadState({ requestKey: platformRequestKey, status: "loading", error: null });
    fetchTrace(overview.run_id, {
      lap: platformTargetLap,
      x: "lap_dist_ft",
      channels: TRACE_WORKBENCH_CHANNELS,
      downsample: "auto",
      preserveExtrema: true,
    })
      .then((nextTrace) => {
        if (cancelled) return;
        if (nextTrace.run_id !== overview.run_id || nextTrace.lap !== platformTargetLap) {
          setTrace(null);
          setTraceLoadState({
            requestKey: platformRequestKey,
            status: "error",
            error: "Trace response did not match the selected run and lap.",
          });
          return;
        }
        setTrace(nextTrace);
        setTraceLoadState({ requestKey: platformRequestKey, status: "ready", error: null });
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setTrace(null);
        setTraceLoadState({
          requestKey: platformRequestKey,
          status: "error",
          error: caught instanceof Error ? caught.message : "Trace data could not be loaded.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [isTraceWorkspace, overview, platformRequestKey, platformTargetLap, traceRetryToken]);

  useEffect(() => {
    if (!overview || channelsHaveFullCatalog) return;
    const needsFullCatalog = selection.selectedWorkspace === "channels" || selection.selectedChannel != null;
    if (!needsFullCatalog) return;
    let cancelled = false;
    fetchChannelsFull(overview.run_id)
      .then((fullCatalog) => {
        if (cancelled) return;
        setChannels(fullCatalog.map((item) => toCatalogShape(item)));
        setChannelsHaveFullCatalog(true);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [overview, selection.selectedWorkspace, selection.selectedChannel, channelsHaveFullCatalog, toCatalogShape]);

  useEffect(() => {
    if (!sessionId || sessionRunsLoading) return;
    if (!currentSession && sessionRuns.length === 0) return;
    const runIds = sessionRuns.length > 0
      ? sessionRuns.map((run) => run.run_id)
      : currentSession?.run_ids ?? runs.map((run) => run.run_id);
    if (selection.selectedRunId != null && !runIds.includes(selection.selectedRunId)) {
      setStatus("Selection cleared because the active session changed. Choose a run or stint from the current session.");
    }
    validateAvailableRuns(runIds, currentSession ? "session" : "run list");
    validateSelectionRunIds(runIds);
  }, [currentSession, runs, selection.selectedRunId, sessionId, sessionRuns, sessionRunsLoading, validateAvailableRuns, validateSelectionRunIds]);

  // ── workspace content ───────────────────────────────────────
  const workspaceContent = useMemo(() => {
    if (!overview) return null;
    const ws = selection.selectedWorkspace;
    if (ws === "overview") return <OverviewTab overview={overview} sessionId={currentSession?.session_id ?? null} telemetryCapabilities={telemetryCapabilities} onToggleMapOverlay={openMapOverlay} />;
    if (ws === "engineer") {
      return (
        <EngineerTab
          key={`${currentSession?.session_id ?? "no-session"}:${overview.run_id}`}
          runId={overview.run_id}
          sessionId={currentSession?.session_id ?? null}
          selectedLap={selection.selectedLap ?? null}
          selectedLapScope={selection.selectedLapScope ?? "unknown"}
          selectedLapWindowStart={selection.selectedLapWindowStart ?? null}
          selectedLapWindowEnd={selection.selectedLapWindowEnd ?? null}
          selectedRepresentativeLap={selection.selectedRepresentativeLap ?? null}
          sessionRunScopeKey={controlledWorkflowScopeKey}
          workflowId={currentGuidanceWorkflow?.workflow_id ?? null}
          workflowUpdatedAt={currentGuidanceWorkflowUpdatedAt}
          onNavigateCitation={openIntelligenceCitation}
          onNavigateCrewEvidence={openCrewChiefEvidence}
        />
      );
    }
    if (ws === "platform_trace" || ws === "speed_delta" || ws === "drag_scrub") {
      const initialWorkbenchView = ws === "drag_scrub"
        ? "scrub_steering"
        : ws === "speed_delta"
          ? "grade_pull"
          : "balance";
      return (
        <PlatformTab
          overview={overview}
          sessionId={currentSession?.session_id ?? null}
          trace={currentTrace}
          traceLoadStatus={currentTraceLoadStatus}
          traceLoadError={currentTraceLoadError}
          onRetryTrace={retryTrace}
          platformEvents={currentPlatformEvents}
          platformEventsLoadStatus={currentPlatformEventsLoadStatus}
          platformEventsLoadError={currentPlatformEventsLoadError}
          onRetryPlatformEvents={retryPlatformEvents}
          initialWorkbenchView={initialWorkbenchView}
          platformEventVisibilityMode={platformEventVisibilityMode}
          onPlatformEventVisibilityModeChange={setPlatformEventVisibilityMode}
          onToggleMapOverlay={openMapOverlay}
          onMapOverlayZoomRangeChange={handleMapOverlayZoomRangeChange}
        />
      );
    }
    if (ws === "setup_impact") return (
      <SetupTab
        overview={overview}
        sessionId={currentSession?.session_id ?? null}
        workflowId={currentGuidanceWorkflow?.workflow_id ?? null}
        workflowUpdatedAt={currentGuidanceWorkflowUpdatedAt}
        onToggleMapOverlay={openMapOverlay}
      />
    );
    if (ws === "dial_in") {
      return (
        <DialInTab
          key={`${overview.run_id}:${explicitControlledWorkflowId ?? "auto"}`}
          overview={overview}
          sessionId={currentSession?.session_id ?? null}
          workflowScopeRunIds={controlledWorkflowScopeRunIds}
          workflowHandoffKey={currentSession?.session_id ?? null}
          workflowOpenIntentId={explicitControlledWorkflowId}
          currentIntelligenceAuthority={currentIntelligenceAuthority}
          intelligenceAuthorityStatus={currentIntelligenceAuthorityStatus}
          intelligenceAuthorityRecovery={currentIntelligenceAuthorityRecovery}
        />
      );
    }
    if (ws === "channels") {
      // Channels removed from nav; redirect to overview if stale state exists
      return <OverviewTab overview={overview} sessionId={currentSession?.session_id ?? null} telemetryCapabilities={telemetryCapabilities} onToggleMapOverlay={openMapOverlay} />;
    }
    if (ws === "laps") {
      return (
        <LapsTab
          overview={overview}
          session={currentSession}
          sessionRuns={sessionRuns}
          sessionRunsLoading={sessionRunsLoading}
          sessionSelectionSource={sessionSelectionSource}
          onToggleMapOverlay={openMapOverlay}
        />
      );
    }
    return <OverviewTab overview={overview} sessionId={currentSession?.session_id ?? null} telemetryCapabilities={telemetryCapabilities} onToggleMapOverlay={openMapOverlay} />;
  }, [currentGuidanceWorkflow?.workflow_id, currentGuidanceWorkflowUpdatedAt, currentIntelligenceAuthority, currentIntelligenceAuthorityRecovery, currentIntelligenceAuthorityStatus, currentPlatformEvents, currentPlatformEventsLoadError, currentPlatformEventsLoadStatus, currentSession, currentTrace, currentTraceLoadError, currentTraceLoadStatus, explicitControlledWorkflowId, handleMapOverlayZoomRangeChange, openCrewChiefEvidence, openIntelligenceCitation, openMapOverlay, overview, platformEventVisibilityMode, retryPlatformEvents, retryTrace, selection.selectedLap, selection.selectedLapScope, selection.selectedLapWindowEnd, selection.selectedLapWindowStart, selection.selectedRepresentativeLap, selection.selectedWorkspace, sessionRuns, sessionRunsLoading, sessionSelectionSource]);

  if (engineStatus === "starting") {
    return (
      <ShellLoadingState
        eyebrow="Local-first telemetry"
        title="Starting RacerZLab"
        detail="Connecting the decision cockpit to your local analysis engine."
      />
    );
  }

  if (engineStatus === "failed") {
    return (
      <main className="empty-state">
        <section className="empty-panel">
          <span className="eyebrow">RACERZLAB</span>
          <h1>Local engine failed to start.</h1>
          <p className="muted">Close and reopen RacerZLab, then retry. Restarting does not delete your local sessions or telemetry files.</p>
          {!desktop && (
            <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              Development mode: start the backend with <code style={{ color: "#38bdf8", fontSize: 11 }}>python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8010</code>
            </p>
          )}
          <button type="button" className="secondary-button" onClick={() => window.location.reload()}>
            Retry engine check
          </button>
        </section>
      </main>
    );
  }

  const intelligenceShellScope = currentIntelligenceShellMove
    ? intelligenceMoveScope(currentIntelligenceShellMove)
    : null;

  // ── no session yet → show startup screen ───────────────────
  if (!sessionId) {
    return <StartupScreen onSessionSelected={handleSessionSelected} />;
  }

  // ── loading / empty state ───────────────────────────────────
  if (loading && !overview) {
    return (
      <ShellLoadingState
        eyebrow={currentSession?.name ?? "Selected session"}
        title="Opening session"
        detail="Restoring the attached run, clean-lap readiness, setup identity, and workspace state."
      />
    );
  }

  const renderedImportIntent = importOpenIntentRef.current;

  if (!overview) {
    const sessionOpenFailed = Boolean(sessionOpenError);
    return (
      <main className="empty-state">
        <section className="empty-panel empty-session-panel" aria-labelledby="empty-session-title">
          <div className="empty-session-heading">
            <div>
              <span className="eyebrow">{currentSession?.name ?? "RACERZLAB SESSION"}</span>
              <h1 id="empty-session-title">{sessionOpenFailed ? "We couldn't open this session" : "Import the first telemetry run"}</h1>
              <p className="muted">
                {sessionOpenFailed
                  ? "The session or its latest run could not be loaded. Retry it, return to the session chooser, or import another telemetry file."
                  : <>This session is ready. Add an iRacing <strong>.ibt</strong> file to build laps, evidence, and setup context locally.</>}
              </p>
            </div>
            <Upload size={28} aria-hidden="true" />
          </div>
          {sessionOpenFailed ? (
            <div className="warning-banner" role="alert">
              <span>{sessionOpenError}</span>
              <button
                type="button"
                className="secondary-button"
                onClick={() => { if (sessionId) void handleSessionSelected(sessionId, sessionSelectionSource ?? "existing"); }}
              >
                Retry session
              </button>
            </div>
          ) : (
            <ol className="empty-session-steps" aria-label="What happens after import">
              <li><strong>Choose a file</strong><span>Select a completed telemetry recording.</span></li>
              <li><strong>Qualify the run</strong><span>Junk laps stay excluded; 10 consecutive clean laps open long-run inspection.</span></li>
              <li><strong>Follow one move</strong><span>See the corner or area priority, then verify one trustworthy next step.</span></li>
            </ol>
          )}
          <ImportPanel
            onImportComplete={(runId, trackMap) => openImportedRun(runId, trackMap, renderedImportIntent)}
            importing={importing}
            importStage={importStage}
            error={error}
            status={status}
            importOutcome={importOutcome}
            fileInputRef={fileInputRef}
            onFileSelected={(file) => { void handleFileSelected(file); }}
            onImportClick={handleImportClick}
          />
          <button
            type="button"
            className="secondary-button empty-session-back"
            onClick={leaveCurrentSession}
          >
            <ArrowLeft size={14} /> Back to sessions
          </button>
        </section>
      </main>
    );
  }

  // ── cockpit layout ──────────────────────────────────────────
  return (
    <div className="cockpit-shell" data-mode={selection.selectedMode}>
      <a className="shell-skip-link" href="#primary-workspace">Skip to workspace</a>
      <RunContextBar
        overview={overview}
        runs={sessionRunOptions}
        onSelectRun={openAttachedSessionRun}
        onSelectLap={(lap) => {
          selectLap(lap);
        }}
      />
      {currentControlledWorkflow?.packet.decision === "test" && (
        <ControlledTestRibbon
          workflow={currentControlledWorkflow}
          currentIntelligenceAuthority={currentIntelligenceAuthority}
          intelligenceAuthorityStatus={currentIntelligenceAuthorityStatus}
          intelligenceAuthorityRecovery={currentIntelligenceAuthorityRecovery}
          onOpen={(workflowId) => {
            if (
              workflowId !== currentControlledWorkflow.workflow_id
              || currentSession?.session_id !== sessionId
            ) return;
            setExplicitControlledWorkflowId(workflowId);
            setWorkspace("dial_in", "manual");
          }}
        />
      )}
      {currentIntelligenceShellMove
        && intelligenceShellScope
        && selection.selectedWorkspace !== "engineer"
        && currentControlledWorkflow?.packet.decision !== "test"
        && (
        <aside
          className="shell-next-trustworthy-move"
          data-authority={currentIntelligenceShellMove.authority}
          data-run-id={currentIntelligenceShellMove.run_id}
          data-scope={intelligenceShellScope.kind}
          role="status"
          aria-label="Next trustworthy move"
        >
          <BrainCircuit size={16} aria-hidden="true" />
          <div className="shell-next-move-copy">
            <span>Next trustworthy move</span>
            <strong>{currentIntelligenceShellMove.title}</strong>
            <small>{currentIntelligenceShellMove.instruction}</small>
          </div>
          <div className="shell-next-move-scope">
            <span>{moveScopeLabel(intelligenceShellScope)}</span>
            <strong>{currentIntelligenceShellMove.authority === "setup_authorized" ? "Controlled-test authority" : "Navigation only"}</strong>
            <small>Opens the evidence view only</small>
          </div>
          <button type="button" onClick={openIntelligenceShellMove}>
            Open {currentIntelligenceShellMove.workspace === "dial_in" ? "Dial-In" : currentIntelligenceShellMove.workspace.replace(/_/g, " ")}
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </aside>
      )}

      <div
        className="cockpit-body"
        data-priority-rail-layout={priorityRailUsesOverlay ? "overlay" : "inline"}
        data-priority-rail-state={priorityRailExpanded ? "expanded" : "collapsed"}
      >
        <nav className="workspace-nav-rail" aria-label="Main workspaces">
          <div className="nav-rail-heading" aria-hidden="true">
            <span>Driver flow</span>
            <small>Read · verify · test</small>
          </div>
          {([
            ["overview", "Overview", Gauge],
            ["engineer", "Engineer", BrainCircuit],
            ["laps", "Laps", Clock],
            ["platform_trace", "Platform", Layers],
            ["setup_impact", "Setup", Wrench],
            ["dial_in", "Dial-In", Crosshair],
          ] as const).map(([key, label, Icon]) => {
            const signal = workspaceSignals[key];
            return (
              <button
                key={key}
                type="button"
                className={`nav-rail-item ${selection.selectedWorkspace === key ? "active" : ""}`}
                onClick={() => setWorkspace(key, "manual")}
                onPointerEnter={() => preloadWorkspace(key)}
                onFocus={() => preloadWorkspace(key)}
                title={`${label}: ${signal.short}. ${signal.detail}`}
                aria-label={`Open ${label}. Status: ${signal.short}. ${signal.detail}`}
                aria-current={selection.selectedWorkspace === key ? "page" : undefined}
              >
                <span className="nav-rail-icon" aria-hidden="true"><Icon size={17} /></span>
                <span className="nav-rail-copy">
                  <strong>{label}</strong>
                  <small className="nav-rail-signal" data-tone={signal.tone} aria-hidden="true">
                    <i /> {signal.short}
                  </small>
                </span>
              </button>
            );
          })}
        </nav>

        {priorityRailExpanded ? (
          <Suspense fallback={<aside className="priority-rail" aria-hidden="true" />}>
            <PriorityRail
              runId={overview.run_id}
              selectedLap={selection.selectedLap}
              collapsed={false}
              onToggle={closePriorityRail}
              collapseDisabled={priorityRailMustStayOpen}
              platformEvents={currentPlatformEvents}
              loadStatus={currentPlatformEventsLoadStatus}
              loadError={currentPlatformEventsLoadError}
              eventVisibilityMode={platformEventVisibilityMode}
            />
          </Suspense>
        ) : (
          <aside className={`priority-rail collapsed${priorityRailIsGenuinelyClear ? " shell-clear" : priorityRailNeedsAttention ? " shell-attention" : ""}`}>
            <button
              ref={priorityRailTriggerRef}
              className="rail-collapse-btn"
              onClick={openPriorityRail}
              onPointerEnter={() => { void loadPriorityRail(); }}
              onFocus={() => { void loadPriorityRail(); }}
              title={priorityRailCollapsedLabel}
              aria-label={priorityRailCollapsedLabel}
              aria-expanded="false"
            >
              {priorityRailIsGenuinelyClear
                ? <CheckCircle2 size={16} aria-hidden="true" />
                : priorityRailNeedsAttention
                  ? <AlertTriangle size={16} aria-hidden="true" />
                  : <ChevronRight size={16} aria-hidden="true" />}
            </button>
          </aside>
        )}

        <main id="primary-workspace" className="cockpit-workspace" tabIndex={-1}>
          <div className="workspace-toolbar shell-session-toolbar">
            <div className="shell-session-toolbar-context">
              <button type="button" className="shell-toolbar-action" onClick={leaveCurrentSession}>
                <ArrowLeft size={14} /> Sessions
              </button>
              <span className="shell-session-identity" title={currentSession?.name ?? "Current session"}>
                <small>Session · {currentSession?.run_ids.length ?? sessionRunOptions.length} run{(currentSession?.run_ids.length ?? sessionRunOptions.length) === 1 ? "" : "s"}</small>
                <strong className="shell-session-name">{currentSession?.name ?? "Current session"}</strong>
              </span>
            </div>
            <div className="shell-workspace-heading">
              <h1 className="shell-workspace-name">{currentWorkspaceLabel}</h1>
              <div
                className="shell-workspace-broadcast"
                data-tone={currentWorkspaceSignal.tone}
                role="status"
                aria-live="polite"
                aria-label={`${currentWorkspaceLabel} status: ${currentWorkspaceSignal.short}. ${currentWorkspaceSignal.detail}`}
                title={currentWorkspaceSignal.detail}
              >
                <i aria-hidden="true" />
                <strong>{currentWorkspaceSignal.short}</strong>
                <span>{currentWorkspaceSignal.detail}</span>
              </div>
            </div>
            <button
              type="button"
              className="shell-toolbar-action shell-import-trigger"
              onClick={() => setSessionToolsOpen((open) => !open)}
              disabled={importing}
              aria-expanded={sessionToolsOpen}
              aria-controls="session-import-drawer"
            >
              <Upload size={14} /> {importing ? "Importing…" : "Add run"}
            </button>
          </div>
          {sessionToolsOpen && (
            <div id="session-import-drawer" className="shell-import-drawer" role="region" aria-label="Add a run to this session">
              <ImportPanel
                onImportComplete={async (runId, trackMap) => {
                  const opened = await openImportedRun(runId, trackMap, renderedImportIntent);
                  if (opened) setSessionToolsOpen(false);
                  return opened;
                }}
                importing={importing}
                importStage={importStage}
                error={error}
                status={status}
                importOutcome={importOutcome}
                fileInputRef={fileInputRef}
                onFileSelected={(file) => { void handleFileSelected(file); }}
                onImportClick={handleImportClick}
              />
            </div>
          )}
          {status && <p className="status-text" role="status" aria-live="polite">{status}</p>}
          {error && <p className="error-text" role="alert">{error}</p>}
          <div className="cockpit-workspace-body">
            <div className="cockpit-workspace-main">
              <Suspense fallback={(
                <div className="workspace-placeholder shell-workspace-loading" role="status" aria-live="polite" aria-busy="true">
                  <span className="eyebrow">{currentWorkspaceLabel}</span>
                  <h3>Preparing workspace</h3>
                  <p>Keeping the current run and lap scope attached while this view opens.</p>
                  <div className="shell-workspace-loading-bars" aria-hidden="true"><span /><span /><span /></div>
                </div>
              )}
              >
                {workspaceContent}
              </Suspense>
            </div>
          </div>
        </main>

        {inspectorOpen ? (
          <Suspense fallback={<aside className="evidence-inspector" aria-hidden="true" />}>
            <EvidenceInspector
              overview={overview}
              platformEvents={currentPlatformEvents}
              channels={channels}
              collapsed={false}
              onToggle={() => setInspectorOpen(false)}
              eventVisibilityMode={platformEventVisibilityMode}
              onEventVisibilityModeChange={setPlatformEventVisibilityMode}
              onToggleMapOverlay={openMapOverlay}
            />
          </Suspense>
        ) : (
          <aside className="evidence-inspector collapsed">
            <button
              className="inspector-collapse-btn"
              onClick={() => setInspectorOpen(true)}
              onPointerEnter={() => { void loadEvidenceInspector(); }}
              onFocus={() => { void loadEvidenceInspector(); }}
              title="Expand Inspector"
              aria-label="Expand Inspector"
              aria-expanded="false"
            >
              <ChevronRight size={16} />
            </button>
          </aside>
        )}
      </div>

      <Suspense fallback={<footer className="event-timeline" aria-hidden="true" />}>
        <EventTimeline platformEvents={currentPlatformEvents}
          eventVisibilityMode={platformEventVisibilityMode}
          workspace={selection.selectedWorkspace}
          onKeyboardOwnershipChange={setTimelineOwnsKeyboard}
        />
      </Suspense>
      {mapOverlayOpen && (
        <Suspense fallback={null}>
          <TrackMapOverlay
            open={mapOverlayOpen}
            runId={overview.run_id}
            lap={selectedTraceLap}
            trackName={overview.session.track_display_name ?? overview.session.track_name}
            targetZoneStartPct={selection.selectedZoneStartPct}
            targetZoneEndPct={selection.selectedZoneEndPct}
            zoomRangeFt={mapOverlayZoomRange}
            platformEvents={currentPlatformEvents}
            eventVisibilityMode={platformEventVisibilityMode}
            onClose={closeMapOverlay}
          />
        </Suspense>
      )}
      {hasCompareBasketItems && (
        <Suspense fallback={null}>
          <CompareBasket />
        </Suspense>
      )}
      {shortcutsOpen && (
        <div className="shortcut-modal-backdrop" role="presentation" onClick={() => setShortcutsOpen(false)}>
          <section
            ref={shortcutModalRef}
            className="shortcut-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="shortcut-modal-header">
              <h2>Keyboard Shortcuts</h2>
              <button ref={shortcutModalCloseRef} className="shortcut-modal-close" onClick={() => setShortcutsOpen(false)} aria-label="Close keyboard shortcuts">X</button>
            </header>
            <div className="shortcut-grid">
              <span>?</span><p>Open shortcuts</p>
              <span>Esc</span><p>Clear evidence focus</p>
              <span>Left / Right</span><p>Step through events</p>
              <span>P</span><p>Open Platform</p>
              <span>M</span><p>Toggle Map Overlay</p>
              <span>O</span><p>Open Overview</p>
              <span>E</span><p>Open Smart Engineer</p>
              <span>C</span><p>Open Laps</p>
              <span>D</span><p>Open Dial-In</p>
              <span>L</span><p>Toggle race/learning mode</p>
              <span>[ / ]</span><p>Toggle rails</p>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

// ── root ──────────────────────────────────────────────────────

function App() {
  return (
    <TelemetrySelectionProvider>
      <CompareBasketProvider>
        <CockpitShell />
      </CompareBasketProvider>
    </TelemetrySelectionProvider>
  );
}

export default App;
