import { Clock, Crosshair, Gauge, Layers, List, MapPin, Wrench } from "lucide-react";
import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addRunToSession,
  fetchChannelSummary,
  fetchChannelsFull,
  fetchEvents,
  fetchLaps,
  fetchOverview,
  fetchPlatformEvents,
  fetchRunList,
  fetchSessionRunList,
  fetchSession,
  fetchSetup,
  fetchTrace,
  importIbtFile,
  importMt2File,
} from "./api/client";
import { EventTimeline } from "./components/EventTimeline";
import { EvidenceInspector } from "./components/EvidenceInspector";
import { ImportPanel } from "./components/ImportPanel";
import { PriorityRail } from "./components/PriorityRail";
import { RunContextBar } from "./components/RunContextBar";
import { StartupScreen } from "./components/StartupScreen";
import { TelemetrySelectionProvider, useTelemetrySelection } from "./store/TelemetrySelectionContext";
import { CompareBasketProvider } from "./store/CompareBasketContext";
import { CompareBasket } from "./components/CompareBasket";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";

import { TRACE_WORKBENCH_CHANNELS } from "./constants/workbenchChannels";
import { OverviewTab } from "./tabs/OverviewTab";
import { importDebug } from "./utils/importDebug";
import type {
  ChannelCatalogItem,
  PlatformEventItem,
  PlatformEventVisibilityMode,
  RunListItem,
  RunOverview,
  TrackMapResolution,
  TraceResponse,
} from "./types/telemetry";
import type { RaceLabSession, SessionSelectionSource } from "./types/session";

const DialInTab = lazy(async () => {
  const module = await import("./tabs/DialInTab");
  return { default: module.DialInTab };
});
const LapsTab = lazy(async () => {
  const module = await import("./tabs/LapsTab");
  return { default: module.LapsTab };
});
const NotebookTab = lazy(async () => {
  const module = await import("./tabs/NotebookTab");
  return { default: module.NotebookTab };
});
const PlatformTab = lazy(async () => {
  const module = await import("./tabs/PlatformTab");
  return { default: module.PlatformTab };
});
const SetupTab = lazy(async () => {
  const module = await import("./tabs/SetupTab");
  return { default: module.SetupTab };
});
const TrackMapTab = lazy(async () => {
  const module = await import("./tabs/TrackMapTab");
  return { default: module.TrackMapTab };
});

// ── cockpit shell ─────────────────────────────────────────────

function CockpitShell() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentSession, setCurrentSession] = useState<RaceLabSession | null>(null);
  const [sessionSelectionSource, setSessionSelectionSource] = useState<SessionSelectionSource | null>(null);
  const [sessionRuns, setSessionRuns] = useState<RunListItem[]>([]);
  const [sessionRunsLoading, setSessionRunsLoading] = useState(false);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [channels, setChannels] = useState<ChannelCatalogItem[]>([]);
  const [channelsHaveFullCatalog, setChannelsHaveFullCatalog] = useState(false);
  const [platformEvents, setPlatformEvents] = useState<PlatformEventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [priorityRailOpen, setPriorityRailOpen] = useState(true);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [platformEventVisibilityMode, setPlatformEventVisibilityMode] = useState<PlatformEventVisibilityMode>("actionable");
  const loadSelectedRunSeqRef = useRef(0);

  const { selection, loadRun, selectLap, setWorkspace } = useTelemetrySelection();
  const selectedTraceLap = selection.selectedRepresentativeLap ?? selection.selectedLap ?? null;
  const isTraceWorkspace =
    selection.selectedWorkspace === "platform_trace"
    || selection.selectedWorkspace === "speed_delta"
    || selection.selectedWorkspace === "drag_scrub";

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
    used_by_recommendations: channel.used_by_recommendations ?? [],
    min: channel.min ?? null,
    max: channel.max ?? null,
    mean: channel.mean ?? null,
    sample_value: channel.sample_value ?? null,
    missing_status: channel.missing_status ?? null,
    group: channel.group ?? null,
    source: channel.source ?? null,
  }), []);

  // ── keyboard shortcuts ─────────────────────────────────────
  useKeyboardShortcuts(platformEvents, setWorkspace, {
    onTogglePriorityRail: () => setPriorityRailOpen((open) => !open),
    onToggleInspector: () => setInspectorOpen((open) => !open),
    onShowShortcuts: () => setShortcutsOpen(true),
    onHideShortcuts: () => setShortcutsOpen(false),
    shortcutsOpen,
  });

  // ── load a run ──────────────────────────────────────────────
  const loadSelectedRun = useCallback(
    async (runId: string) => {
      const seq = ++loadSelectedRunSeqRef.current;
      setLoading(true);
      setError(null);
      try {
        const base = await fetchOverview(runId);
        const bestLap = base.best_useful_lap?.lap_number;
        const [laps, events, setup, channelCatalog] = await Promise.all([
          fetchLaps(runId),
          fetchEvents(runId),
          fetchSetup(runId).catch(() => base.setup_snapshot ?? null),
          fetchChannelSummary(runId).catch(() => []),
        ]);
        if (seq !== loadSelectedRunSeqRef.current) return;
        setOverview({ ...base, laps, events, setup_snapshot: setup });
        setChannels(channelCatalog.map((item) => toCatalogShape(item)));
        setChannelsHaveFullCatalog(false);
        setTrace(null);
        setPlatformEvents([]);
        loadRun(runId, bestLap ?? null);
      } catch (caught) {
        if (seq !== loadSelectedRunSeqRef.current) return;
        setError(caught instanceof Error ? caught.message : "Failed to load run.");
      } finally {
        if (seq === loadSelectedRunSeqRef.current) setLoading(false);
      }
    },
    [loadRun, toCatalogShape],
  );

  // ── session management (defined after loadSelectedRun to avoid hoisting issues) ──
  const refreshSessionRuns = useCallback(async (sid: string) => {
    setSessionRunsLoading(true);
    try {
      const scopedRuns = await fetchSessionRunList(sid);
      setSessionRuns(scopedRuns);
      return scopedRuns;
    } catch {
      setSessionRuns([]);
      return [];
    } finally {
      setSessionRunsLoading(false);
    }
  }, []);

  const handleSessionSelected = useCallback(async (sid: string, source: SessionSelectionSource) => {
    setSessionId(sid);
    setSessionSelectionSource(source);
    setCurrentSession(null);
    setSessionRuns([]);
    setLoading(true);
    try {
      const session = await fetchSession(sid);
      setCurrentSession(session);
      const [recentRuns] = await Promise.all([
        fetchRunList().catch(() => []),
        refreshSessionRuns(sid),
      ]);
      setRuns(recentRuns);
      if (session.run_ids.length > 0) {
        await loadSelectedRun(session.run_ids[session.run_ids.length - 1]);
      } else {
        setLoading(false);
      }
    } catch {
      setCurrentSession(null);
      setSessionRuns([]);
      setLoading(false);
    }
  }, [loadSelectedRun, refreshSessionRuns]);

  // ── import ──────────────────────────────────────────────────
  const [importStage, setImportStage] = useState<string | null>(null);

  const openImportedRun = useCallback(
    async (runId?: string | null, trackMap?: TrackMapResolution | null) => {
      setError(null);
      setStatus(null);

      importDebug.start("sessions_refresh_started", { runId, track_map_status: trackMap?.status });
      if (sessionId && runId) {
        const updatedSession = await addRunToSession(sessionId, runId).catch((caught) => {
          importDebug.error(
            "sessions_refresh_started",
            caught instanceof Error ? caught.message : "Could not attach run to session.",
            { sessionId, runId },
          );
          return null;
        });
        if (updatedSession) {
          setCurrentSession(updatedSession);
        }
      }
      const [recentRuns] = await Promise.all([
        fetchRunList(),
        sessionId ? refreshSessionRuns(sessionId) : Promise.resolve([]),
      ]);
      setRuns(recentRuns);
      importDebug.success("sessions_refresh_finished", { run_count: recentRuns.length });

      if (!runId) {
        // Track-map-only import: suppress success message in normal UI
        // Only show if there's an actual error or ambiguity
        if (trackMap?.status === "matched") {
          setStatus(null);
        } else {
          setStatus(trackMap?.message ?? null);
        }
        return;
      }

      importDebug.start("open_imported_run_started", { runId });
      setWorkspace("overview", "manual");
      await loadSelectedRun(runId);
      importDebug.success("open_imported_run_finished", { runId });
      // Suppress success messages for normal auto-resolution
      setStatus(null);
    },
    [loadSelectedRun, refreshSessionRuns, sessionId, setWorkspace],
  );

  const handleFileSelected = useCallback(async (file: File | null) => {
    if (!file) return;
    setImporting(true);
    setError(null);
    setStatus(null);
    setImportStage("Opening file…");
    try {
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext === "mt2") {
        setImportStage("Reading track map...");
        const entry = await importMt2File(file);
        setImportStage("Saving local map index...");
        const dupNote = entry.import_status === "already_indexed" ? " (already indexed; refreshed cache)" : "";
        setStatus(`Imported track map: ${entry.points_count?.toLocaleString()} centerline points, ${entry.markers_count} markers, ${entry.sections_count} sections.${dupNote}`);
        setImportStage(null);
        setImporting(false);
        setLoading(false);
        return;
      }
      setImportStage("Reading .ibt and decoding telemetry...");
      const result = await importIbtFile(file);
      if (result.run_id) {
        setImportStage("Normalizing channels, building laps/events, and writing cache...");
      }
      setImportStage("Opening cockpit...");
      await openImportedRun(result.run_id, result.track_map ?? null);
      setImportStage(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed.");
      setImportStage(null);
    } finally {
      setImporting(false);
      setLoading(false);
    }
  }, [openImportedRun]);

  const handleImportClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  useEffect(() => {
    if (!overview) return;
    const targetLap = selectedTraceLap ?? overview.best_useful_lap?.lap_number ?? null;
    if (targetLap == null) return;
    let cancelled = false;
    setPlatformEvents([]);
    fetchPlatformEvents(overview.run_id, { lap: targetLap })
      .then((nextPlatformEvents) => {
        if (!cancelled) setPlatformEvents(nextPlatformEvents);
      })
      .catch(() => {
        if (!cancelled) setPlatformEvents([]);
      });
    return () => {
      cancelled = true;
    };
  }, [overview, selectedTraceLap]);

  useEffect(() => {
    if (!overview || !isTraceWorkspace) return;
    const targetLap = selectedTraceLap ?? overview.best_useful_lap?.lap_number ?? null;
    if (targetLap == null) return;
    if (trace?.run_id === overview.run_id && trace?.lap === targetLap) return;

    let cancelled = false;
    setTrace(null);
    fetchTrace(overview.run_id, {
      lap: targetLap,
      x: "lap_dist_ft",
      channels: TRACE_WORKBENCH_CHANNELS,
      downsample: "auto",
      preserveExtrema: true,
    })
      .then((nextTrace) => {
        if (!cancelled) setTrace(nextTrace);
      })
      .catch(() => {
        if (!cancelled) setTrace(null);
      });

    return () => {
      cancelled = true;
    };
  }, [overview, selectedTraceLap, trace?.lap, trace?.run_id, isTraceWorkspace]);

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

  // ── workspace content ───────────────────────────────────────
  const workspaceContent = useMemo(() => {
    if (!overview) return null;
    const ws = selection.selectedWorkspace;
    if (ws === "overview") return <OverviewTab overview={overview} />;
    if (ws === "platform_trace" || ws === "speed_delta" || ws === "drag_scrub") {
      const initialWorkbenchView = ws === "drag_scrub"
        ? "scrub_steering"
        : ws === "speed_delta"
          ? "grade_pull"
          : "balance";
      return (
        <PlatformTab
          overview={overview}
          trace={trace}
          platformEvents={platformEvents}
          initialWorkbenchView={initialWorkbenchView}
          platformEventVisibilityMode={platformEventVisibilityMode}
          onPlatformEventVisibilityModeChange={setPlatformEventVisibilityMode}
        />
      );
    }
    if (ws === "setup_impact") return <SetupTab overview={overview} />;
    if (ws === "dial_in") return <DialInTab overview={overview} />;
    if (ws === "channels") {
      // Channels removed from nav; redirect to overview if stale state exists
      return <OverviewTab overview={overview} />;
    }
    if (ws === "notebook") {
      return <NotebookTab />;
    }
    if (ws === "laps") {
      return (
        <LapsTab
          overview={overview}
          session={currentSession}
          sessionRuns={sessionRuns}
          sessionRunsLoading={sessionRunsLoading}
          sessionSelectionSource={sessionSelectionSource}
        />
      );
    }
    if (ws === "map") {
      return <TrackMapTab runId={overview.run_id} lap={selectedTraceLap}
        trackName={overview.session.track_display_name ?? overview.session.track_name}
        carName={overview.session.car_name}
        setupName={overview.session.setup_name}
        targetZoneStartPct={selection.selectedZoneStartPct ?? undefined}
        targetZoneEndPct={selection.selectedZoneEndPct ?? undefined} />;
    }
    return <OverviewTab overview={overview} />;
  }, [currentSession, overview, platformEventVisibilityMode, platformEvents, selectedTraceLap, selection.selectedWorkspace, sessionRuns, sessionRunsLoading, sessionSelectionSource, trace]);

  // ── no session yet → show startup screen ───────────────────
  if (!sessionId) {
    return <StartupScreen onSessionSelected={handleSessionSelected} />;
  }

  // ── loading / empty state ───────────────────────────────────
  if (loading && !overview) {
    return <main className="boot-screen">RacerZLab</main>;
  }

  if (!overview) {
    return (
      <main className="empty-state">
        <section className="empty-panel">
          <span className="eyebrow">RACERZLAB</span>
          <h1>No persisted runs yet</h1>
          <ImportPanel
            onImportComplete={(runId, trackMap) => {
              void openImportedRun(runId, trackMap);
            }}
            importing={importing}
            importStage={importStage}
            error={error}
            status={status}
            fileInputRef={fileInputRef}
            onFileSelected={(file) => { void handleFileSelected(file); }}
            onImportClick={handleImportClick}
          />
        </section>
      </main>
    );
  }

  // ── cockpit layout ──────────────────────────────────────────
  return (
    <div className="cockpit-shell">
      <RunContextBar
        overview={overview}
        runs={runs}
        onSelectRun={(runId) => { void loadSelectedRun(runId); }}
        onSelectLap={(lap) => {
          selectLap(lap);
        }}
      />

      <div className="cockpit-body">
        <nav className="workspace-nav-rail">
          {([
            ["overview", "Overview", Gauge],
            ["laps", "Laps", Clock],
            ["platform_trace", "Platform", Layers],
            ["map", "Track Map", MapPin],
            ["setup_impact", "Setup", Wrench],
            ["dial_in", "Dial-In", Crosshair],
            ["notebook", "Notebook", List],
          ] as const).map(([key, label, Icon]) => (
            <button
              key={key}
              className={`nav-rail-item ${selection.selectedWorkspace === key ? "active" : ""}`}
              onClick={() => setWorkspace(key, "manual")}
              title={label}
              aria-current={selection.selectedWorkspace === key ? "page" : undefined}
            >
              <Icon size={17} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <PriorityRail
          runId={overview.run_id}
          selectedLap={selection.selectedLap}
          collapsed={!priorityRailOpen}
          onToggle={() => setPriorityRailOpen(!priorityRailOpen)}
          platformEvents={platformEvents}
          eventVisibilityMode={platformEventVisibilityMode}
        />

        <main className="cockpit-workspace">
          <div className="workspace-toolbar">
            <ImportPanel
              onImportComplete={(runId, trackMap) => {
                void openImportedRun(runId, trackMap);
              }}
              importing={importing}
              importStage={importStage}
              error={error}
              status={status}
              fileInputRef={fileInputRef}
              onFileSelected={(file) => { void handleFileSelected(file); }}
              onImportClick={handleImportClick}
            />
          </div>
          {status && <p className="status-text">{status}</p>}
          {error && <p className="error-text">{error}</p>}
          <div className="cockpit-workspace-body">
            <div className="cockpit-workspace-main">
              <Suspense fallback={(
                <div className="workspace-placeholder">
                  <h3>Loading workspace...</h3>
                  <p>Preparing view data and UI.</p>
                </div>
              )}
              >
                {workspaceContent}
              </Suspense>
            </div>
          </div>
        </main>

        <EvidenceInspector
          overview={overview}
          platformEvents={platformEvents}
          channels={channels}
          collapsed={!inspectorOpen}
          onToggle={() => setInspectorOpen(!inspectorOpen)}
          eventVisibilityMode={platformEventVisibilityMode}
          onEventVisibilityModeChange={setPlatformEventVisibilityMode}
        />
      </div>

      <EventTimeline platformEvents={platformEvents} eventVisibilityMode={platformEventVisibilityMode} />
      <CompareBasket />
      {shortcutsOpen && (
        <div className="shortcut-modal-backdrop" role="presentation" onClick={() => setShortcutsOpen(false)}>
          <section
            className="shortcut-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Keyboard shortcuts"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="shortcut-modal-header">
              <h2>Keyboard Shortcuts</h2>
              <button className="shortcut-modal-close" onClick={() => setShortcutsOpen(false)} aria-label="Close keyboard shortcuts">X</button>
            </header>
            <div className="shortcut-grid">
              <span>?</span><p>Open shortcuts</p>
              <span>Esc</span><p>Clear evidence focus</p>
              <span>Left / Right</span><p>Step through events</p>
              <span>P</span><p>Open Platform</p>
              <span>M</span><p>Open Track Map</p>
              <span>O</span><p>Open Overview</p>
              <span>C</span><p>Open Laps</p>
              <span>D</span><p>Open Dial-In</p>
              <span>N</span><p>Open Notebook</p>
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
