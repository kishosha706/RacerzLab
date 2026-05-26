import { BarChart3, Boxes, Gauge, Layers, List, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchChannels,
  fetchEvents,
  fetchLaps,
  fetchOverview,
  fetchPlatformEvents,
  fetchReport,
  fetchRunList,
  fetchSetup,
  fetchTrace,
  importIbtFile,
} from "./api/client";
import { EventTimeline } from "./components/EventTimeline";
import { EvidenceInspector } from "./components/EvidenceInspector";
import { NextBestClick } from "./components/NextBestClick";
import { PriorityRail } from "./components/PriorityRail";
import { RunContextBar } from "./components/RunContextBar";
import { TelemetrySelectionProvider, useTelemetrySelection } from "./store/TelemetrySelectionContext";
import { CompareTab } from "./tabs/CompareTab";
import { NotebookTab } from "./tabs/NotebookTab";
import { OverviewTab } from "./tabs/OverviewTab";
import { PlatformTab } from "./tabs/PlatformTab";
import { RawChannelsTab } from "./tabs/RawChannelsTab";
import { SetupTab } from "./tabs/SetupTab";
import type {
  ChannelCatalogItem,
  PlatformEventItem,
  RunListItem,
  RunOverview,
  TelemetryCursor,
  TraceResponse,
} from "./types/telemetry";

// ── cockpit shell ─────────────────────────────────────────────

function CockpitShell() {
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [trace, setTrace] = useState<TraceResponse | null>(null);
  const [channels, setChannels] = useState<ChannelCatalogItem[]>([]);
  const [platformEvents, setPlatformEvents] = useState<PlatformEventItem[]>([]);
  const [cursor, setCursor] = useState<TelemetryCursor>({});
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { selection, loadRun, selectLap, selectEvent, setWorkspace } = useTelemetrySelection();

  // ── load a run ──────────────────────────────────────────────
  const loadSelectedRun = useCallback(
    async (runId: string) => {
      setLoading(true);
      setError(null);
      try {
        const base = await fetchOverview(runId);
        const bestLap = base.best_useful_lap?.lap_number;
        const [laps, events, setup, channelCatalog, nextTrace, pevents] = await Promise.all([
          fetchLaps(runId),
          fetchEvents(runId),
          fetchSetup(runId).catch(() => base.setup_snapshot ?? null),
          fetchChannels(runId).catch(() => []),
          fetchTrace(runId, {
            lap: bestLap ?? undefined,
            x: "lap_dist_ft",
            channels: [
              "throttle_pct", "brake_pct", "center_rake_fs_in", "side_rake_in",
              "cfs_ride_height_in", "cfs_ride_height_mm",
              "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in",
              "speed_mph", "rpm", "gear", "dynamic_pressure_psf", "lap_dist_pct_100",
              "speed_rate_mph_s", "speed_rate_mph_1000ft",
              "drag_scrub_suspicion", "abs_steering_deg", "abs_lat_accel",
              "lf_pressure", "rf_pressure", "lr_pressure", "rr_pressure",
              "lf_pressure_gain", "rf_pressure_gain", "lr_pressure_gain", "rr_pressure_gain",
              "lf_temp_spread", "rf_temp_spread", "lr_temp_spread", "rr_temp_spread",
              "lf_slip_ratio_proxy", "rf_slip_ratio_proxy", "lr_slip_ratio_proxy", "rr_slip_ratio_proxy",
            ],
            downsample: "auto",
            preserveExtrema: true,
          }).catch(() => null),
          fetchPlatformEvents(runId, { lap: bestLap ?? undefined }).catch(() => []),
        ]);
        setOverview({ ...base, laps, events, setup_snapshot: setup });
        setChannels(channelCatalog);
        setTrace(nextTrace);
        setPlatformEvents(pevents);
        loadRun(runId, bestLap ?? null);
        setCursor({
          selected_run_id: runId,
          selected_lap: bestLap ?? null,
          selected_sample_index: null,
          selected_lap_dist_ft: null,
          selected_lap_pct: null,
          selected_event_id: null,
        });
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Failed to load run.");
      } finally {
        setLoading(false);
      }
    },
    [loadRun],
  );

  // ── initial load ────────────────────────────────────────────
  const loadRecent = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const recentRuns = await fetchRunList();
      setRuns(recentRuns);
      if (recentRuns.length > 0) {
        await loadSelectedRun(recentRuns[0].run_id);
      } else {
        setOverview(null);
        setTrace(null);
        setChannels([]);
        setPlatformEvents([]);
        setLoading(false);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reach RaceLab API.");
      setOverview(null);
      setTrace(null);
      setChannels([]);
      setPlatformEvents([]);
      setLoading(false);
    }
  }, [loadSelectedRun]);

  useEffect(() => { void loadRecent(); }, [loadRecent]);

  // ── import ──────────────────────────────────────────────────
  const [importStage, setImportStage] = useState<string | null>(null);

  const handleFileSelected = useCallback(async (file: File | null) => {
    if (!file) return;
    setImporting(true);
    setError(null);
    setStatus(null);
    setImportStage("Opening file…");
    try {
      setImportStage("Importing telemetry…");
      const result = await importIbtFile(file);
      setImportStage("Saving local copy…");
      const recentRuns = await fetchRunList();
      setRuns(recentRuns);
      if (result.run_id) {
        setImportStage("Building analysis…");
        await loadSelectedRun(result.run_id);
      }
      setStatus(result.status.message);
      setImportStage(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed.");
      setImportStage(null);
    } finally {
      setImporting(false);
      setLoading(false);
    }
  }, [loadSelectedRun]);

  const handleImportClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleExportReport = async () => {
    if (!overview) return;
    const report = await fetchReport(overview.run_id);
    setStatus(`Report generated (${report.markdown.length} chars).`);
  };

  // ── workspace content ───────────────────────────────────────
  const workspaceContent = useMemo(() => {
    if (!overview) return null;
    const ws = selection.selectedWorkspace;
    if (ws === "overview") return <OverviewTab overview={overview} />;
    if (ws === "platform_trace" || ws === "speed_delta" || ws === "drag_scrub") {
      return <PlatformTab overview={overview} trace={trace} cursor={cursor} onCursorChange={setCursor} />;
    }
    if (ws === "setup_impact") return <SetupTab overview={overview} />;
    if (ws === "channels") return <RawChannelsTab overview={overview} trace={trace} channels={channels} />;
    if (ws === "notebook") {
      return <NotebookTab />;
    }
    if (ws === "compare") {
      return <CompareTab runs={runs} currentRunId={overview.run_id} />;
    }
    if (ws === "map") {
      return (
        <section className="workspace-placeholder">
          <h3>Track Map</h3>
          <p>Track map will be available when GPS data or .mt2 parsing is active.</p>
        </section>
      );
    }
    return <OverviewTab overview={overview} />;
  }, [overview, selection.selectedWorkspace, trace, cursor, channels]);

  // ── loading / empty state ───────────────────────────────────
  if (loading && !overview) {
    return <main className="boot-screen">RaceLab Garage</main>;
  }

  if (!overview) {
    return (
      <main className="empty-state">
        <section className="empty-panel">
          <span className="eyebrow">RaceLab Garage</span>
          <h1>No persisted runs yet</h1>
          <p>Import a local iRacing `.ibt` file to create the first baseline run.</p>
          <div className="import-row">
            <input
              ref={fileInputRef}
              type="file"
              accept=".ibt,.sto,.mt2"
              style={{ display: "none" }}
              onChange={(e) => {
                const files = e.currentTarget.files;
                if (files && files.length > 0) void handleFileSelected(files[0]);
              }}
            />
            <button className="secondary-button" onClick={handleImportClick} disabled={importing}>
              {importStage ?? (importing ? "Importing…" : "Import .ibt")}
            </button>
          </div>
          {error && <p className="error-text">{error}</p>}
          {status && <p className="status-text">{status}</p>}
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
          if (overview) {
            fetchTrace(overview.run_id, {
              lap: lap ?? undefined,
              x: "lap_dist_ft",
              channels: [
                "throttle_pct", "brake_pct", "center_rake_fs_in", "side_rake_in",
                "cfs_ride_height_in", "cfs_ride_height_mm",
                "lf_ride_height_in", "rf_ride_height_in", "lr_ride_height_in", "rr_ride_height_in",
                "speed_mph", "rpm", "gear", "dynamic_pressure_psf", "lap_dist_pct_100",
                "speed_rate_mph_s", "speed_rate_mph_1000ft",
                "drag_scrub_suspicion", "abs_steering_deg", "abs_lat_accel",
              ],
              downsample: "auto",
              preserveExtrema: true,
            }).then((t) => setTrace(t)).catch(() => {});
            fetchPlatformEvents(overview.run_id, { lap: lap ?? undefined })
              .then((pe) => setPlatformEvents(pe)).catch(() => {});
          }
        }}
      />

      <div className="cockpit-body">
        <nav className="workspace-nav-rail">
          {([
            ["overview", "Overview", Gauge],
            ["platform_trace", "Platform", Layers],
            ["setup_impact", "Setup", Wrench],
            ["compare", "Compare", BarChart3],
            ["channels", "Channels", Boxes],
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

        <PriorityRail runId={overview.run_id} selectedLap={selection.selectedLap} />

        <main className="cockpit-workspace">
          <div className="workspace-toolbar">
            <div>
              <span className="eyebrow">
                {selection.selectedMode} · {selection.selectedWorkspace.replace(/_/g, " ")}
              </span>
            </div>
            <div className="toolbar-actions">
              <input
                ref={fileInputRef}
                type="file"
                accept=".ibt,.sto,.mt2"
                style={{ display: "none" }}
                onChange={(e) => {
                  const files = e.currentTarget.files;
                  if (files && files.length > 0) void handleFileSelected(files[0]);
                }}
              />
              <button className="secondary-button" onClick={handleImportClick} disabled={importing}>
                <BarChart3 size={16} /> {importStage ?? (importing ? "Importing…" : "Import .ibt")}
              </button>
              <button className="secondary-button" onClick={handleExportReport}>
                <BarChart3 size={16} /> Export
              </button>
            </div>
          </div>
          {status && <p className="status-text">{status}</p>}
          {error && <p className="error-text">{error}</p>}
          <NextBestClick runId={overview.run_id} platformEvents={platformEvents} />
          {workspaceContent}
        </main>

        <EvidenceInspector overview={overview} platformEvents={platformEvents} channels={channels} />
      </div>

      <EventTimeline platformEvents={platformEvents} />
    </div>
  );
}

// ── root ──────────────────────────────────────────────────────

function App() {
  return (
    <TelemetrySelectionProvider>
      <CockpitShell />
    </TelemetrySelectionProvider>
  );
}

export default App;
