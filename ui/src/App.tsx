import { Clock, Gauge, GitCompare, Layers, List, MapPin, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addRunToSession,
  fetchChannelSummary,
  fetchChannelsFull,
  fetchEvents,
  fetchLaps,
  fetchOverview,
  fetchPlatformEvents,
  fetchRunList,
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
import { CompareTab } from "./tabs/CompareTab";
import { LapsTab } from "./tabs/LapsTab";
import { NotebookTab } from "./tabs/NotebookTab";
import { OverviewTab } from "./tabs/OverviewTab";
import { PlatformTab } from "./tabs/PlatformTab";
import { SetupTab } from "./tabs/SetupTab";
import { TrackMapTab } from "./tabs/TrackMapTab";
import { importDebug } from "./utils/importDebug";
import type {
  ChannelCatalogItem,
  PlatformEventItem,
  RunListItem,
  RunOverview,
  TrackMapResolution,
  TraceResponse,
} from "./types/telemetry";

// ── cockpit shell ─────────────────────────────────────────────

function CockpitShell() {
  const [sessionId, setSessionId] = useState<string | null>(null);
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
  });

  // ── load a run ──────────────────────────────────────────────
  const loadSelectedRun = useCallback(
    async (runId: string) => {
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
        setOverview({ ...base, laps, events, setup_snapshot: setup });
        setChannels(channelCatalog.map((item) => toCatalogShape(item)));
        setChannelsHaveFullCatalog(false);
        setTrace(null);        // reset; loaded lazily in effect below
        setPlatformEvents([]);  // reset; loaded lazily in effect below
        loadRun(runId, bestLap ?? null);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Failed to load run.");
      } finally {
        setLoading(false);
      }
    },
    [loadRun, toCatalogShape],
  );

  // ── session management (defined after loadSelectedRun to avoid hoisting issues) ──
  const handleSessionSelected = useCallback(async (sid: string) => {
    setSessionId(sid);
    try {
      const session = await fetchSession(sid);
      if (session.run_ids.length > 0) {
        const recentRuns = await fetchRunList();
        setRuns(recentRuns);
        await loadSelectedRun(session.run_ids[session.run_ids.length - 1]);
      } else {
        setLoading(false);
      }
    } catch {
      setLoading(false);
    }
  }, [loadSelectedRun]);

  // ── import ──────────────────────────────────────────────────
  const [importStage, setImportStage] = useState<string | null>(null);

  const openImportedRun = useCallback(
    async (runId?: string | null, trackMap?: TrackMapResolution | null) => {
      setError(null);
      setStatus(null);

      importDebug.start("sessions_refresh_started", { runId, track_map_status: trackMap?.status });
      if (sessionId && runId) {
        await addRunToSession(sessionId, runId).catch((caught) => {
          importDebug.error(
            "sessions_refresh_started",
            caught instanceof Error ? caught.message : "Could not attach run to session.",
            { sessionId, runId },
          );
        });
      }
      const recentRuns = await fetchRunList();
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
    [loadSelectedRun, sessionId, setWorkspace],
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
        setImportStage("Importing track map…");
        const entry = await importMt2File(file);
        setImportStage("Saving local copy…");
        const dupNote = entry.import_status === "already_indexed" ? " (already indexed; refreshed cache)" : "";
        setStatus(`Parsed .mt2 centerline: ${entry.points_count?.toLocaleString()} points, ${entry.markers_count} markers, ${entry.sections_count} sections.${dupNote}`);
        setImportStage(null);
        setImporting(false);
        setLoading(false);
        return;
      }
      setImportStage("Importing telemetry…");
      const result = await importIbtFile(file);
      setImportStage("Saving local copy…");
      if (result.run_id) {
        setImportStage("Building analysis…");
      }
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
    if (!overview) return;
    const targetLap = selectedTraceLap ?? overview.best_useful_lap?.lap_number ?? null;
    if (targetLap == null) return;
    if (trace?.run_id === overview.run_id && trace?.lap === targetLap) return;

    let cancelled = false;
    const loadTrace = () => {
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
        .catch(() => {});
    };

    if (isTraceWorkspace) {
      loadTrace();
      return () => {
        cancelled = true;
      };
    }

    const schedulePrefetch = () => loadTrace();
    let timeoutId: number | null = null;
    let idleId: number | null = null;
    const requestIdle = (window as unknown as {
      requestIdleCallback?: (cb: () => void, options?: { timeout: number }) => number;
    }).requestIdleCallback;
    const cancelIdle = (window as unknown as {
      cancelIdleCallback?: (id: number) => void;
    }).cancelIdleCallback;
    if (typeof requestIdle === "function") {
      idleId = requestIdle(schedulePrefetch, { timeout: 1800 });
    } else {
      timeoutId = window.setTimeout(schedulePrefetch, 450);
    }

    return () => {
      cancelled = true;
      if (idleId != null && typeof cancelIdle === "function") {
        cancelIdle(idleId);
      }
      if (timeoutId != null) window.clearTimeout(timeoutId);
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
      return <PlatformTab overview={overview} trace={trace} platformEvents={platformEvents} initialWorkbenchView={initialWorkbenchView} />;
    }
    if (ws === "setup_impact") return <SetupTab overview={overview} />;
    if (ws === "channels") {
      // Channels removed from nav; redirect to overview if stale state exists
      return <OverviewTab overview={overview} />;
    }
    if (ws === "notebook") {
      return <NotebookTab />;
    }
    if (ws === "compare") {
      return <CompareTab runs={runs} currentRunId={overview.run_id} />;
    }
    if (ws === "laps") {
      return <LapsTab overview={overview} />;
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
  }, [overview, selection.selectedWorkspace, selectedTraceLap, trace, channels, platformEvents, runs]);

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
            ["map", "Map", MapPin],
            ["laps", "Laps", Clock],
            ["platform_trace", "Platform", Layers],
            ["setup_impact", "Setup", Wrench],
            ["compare", "Compare", GitCompare],
            ["notebook", "Notes", List],
          ] as const).map(([key, label, Icon]) => (
            <button
              key={key}
              className={`nav-rail-item ${selection.selectedWorkspace === key ? "active" : ""}`}
              onClick={() => setWorkspace(key, "manual")}
              title={label}
            >
              <Icon size={17} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <PriorityRail runId={overview.run_id} selectedLap={selection.selectedLap} collapsed={!priorityRailOpen} onToggle={() => setPriorityRailOpen(!priorityRailOpen)} platformEvents={platformEvents} />

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
              {workspaceContent}
            </div>
          </div>
        </main>

        <EvidenceInspector overview={overview} platformEvents={platformEvents} channels={channels} collapsed={!inspectorOpen} onToggle={() => setInspectorOpen(!inspectorOpen)} />
      </div>

      <EventTimeline platformEvents={platformEvents} />
      <CompareBasket />
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
