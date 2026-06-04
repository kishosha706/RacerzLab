import { AlertTriangle, BarChart3, BookOpen, CheckCircle2, Clipboard, Layers, List, MapPin, RotateCcw, Wrench } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useCompareBasket } from "../store/CompareBasketContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { NotebookFinding, SetupMemorySummary, TestPlan } from "../types/compare";
import { findingToMarkdown } from "../utils/exportUtils";
import { VERDICT_COLORS } from "../constants/verdict";

const API_BASE =
  import.meta.env.VITE_RACELAB_API_BASE_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8010";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

type NotebookView = "findings" | "finding-detail" | "test-plans" | "setup-memory";
type FindingSectorSummary = {
  label?: string;
  sector_name?: string;
  avg_speed_delta_mph?: number | null;
  min_cfs_delta_in?: number | null;
};
type FindingSetupChange = {
  label?: string;
  delta?: string | null;
};

const STATUS_COLORS: Record<string, string> = {
  saved: "#38bdf8",
  confirmed: "#22c55e",
  rejected: "#ef4444",
  needs_retest: "#f59e0b",
  archived: "#8d9aaa",
};

function formatVal(v: number | null | undefined, digits = 2): string {
  return v != null && !Number.isNaN(v) ? v.toFixed(digits) : "-";
}

export function NotebookTab() {
  const { focusEvidence, setWorkspace } = useTelemetrySelection();
  const { setBaseline, setTest } = useCompareBasket();
  const [view, setView] = useState<NotebookView>("findings");
  const [findings, setFindings] = useState<NotebookFinding[]>([]);
  const [selectedFinding, setSelectedFinding] = useState<NotebookFinding | null>(null);
  const [testPlans, setTestPlans] = useState<TestPlan[]>([]);
  const [setupMemory, setSetupMemory] = useState<SetupMemorySummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [filterCar, setFilterCar] = useState("");
  const [filterTrack, setFilterTrack] = useState("");
  const [filterVerdict, setFilterVerdict] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editTags, setEditTags] = useState("");
  const [savingDetail, setSavingDetail] = useState(false);
  const [detailStatus, setDetailStatus] = useState<string | null>(null);

  const loadFindings = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterCar) params.set("car_name", filterCar);
      if (filterTrack) params.set("track_name", filterTrack);
      if (filterVerdict) params.set("verdict", filterVerdict);
      if (filterStatus) params.set("status", filterStatus);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await req<NotebookFinding[]>(`/api/notebook/findings${suffix}`);
      setFindings(data);
    } catch { /* empty */ }
    finally { setLoading(false); }
  }, [filterCar, filterTrack, filterVerdict, filterStatus]);

  useEffect(() => { void loadFindings(); }, [loadFindings]);

  const loadTestPlans = useCallback(async () => {
    try {
      const data = await req<TestPlan[]>("/api/notebook/test-plans");
      setTestPlans(data);
    } catch { /* empty */ }
  }, []);

  const loadSetupMemory = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filterCar) params.set("car_name", filterCar);
      if (filterTrack) params.set("track_name", filterTrack);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await req<SetupMemorySummary>(`/api/notebook/setup-memory${suffix}`);
      setSetupMemory(data);
    } catch { /* empty */ }
  }, [filterCar, filterTrack]);

  useEffect(() => { if (view === "test-plans") void loadTestPlans(); }, [view, loadTestPlans]);
  useEffect(() => { if (view === "setup-memory") void loadSetupMemory(); }, [view, loadSetupMemory]);
  useEffect(() => {
    if (detailStatus !== "Changes saved.") return;
    const timer = window.setTimeout(() => setDetailStatus(null), 2000);
    return () => window.clearTimeout(timer);
  }, [detailStatus]);

  const handleSelectFinding = useCallback(async (finding: NotebookFinding) => {
    setSelectedFinding(finding);
    setEditNotes(finding.notes ?? "");
    setEditTags((finding.tags ?? []).join(", "));
    setDetailStatus(null);
    setView("finding-detail");
  }, []);

  const handleUpdateStatus = useCallback(async (findingId: string, status: string) => {
    if (!selectedFinding) return;
    try {
      await req(`/api/notebook/findings/${findingId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      void loadFindings();
      if (selectedFinding.finding_id === findingId) {
        setSelectedFinding({ ...selectedFinding, status });
      }
      setDetailStatus("Status updated.");
    } catch { setDetailStatus("Failed to update."); }
  }, [loadFindings, selectedFinding]);

  const handleSaveDetail = useCallback(async () => {
    if (!selectedFinding) return;
    setSavingDetail(true);
    setDetailStatus(null);
    try {
      const tags = editTags.split(",").map((t) => t.trim()).filter(Boolean);
      const updated = await req<NotebookFinding>(`/api/notebook/findings/${selectedFinding.finding_id}`, {
        method: "PATCH",
        body: JSON.stringify({ notes: editNotes, tags }),
      });
      setSelectedFinding(updated);
      setDetailStatus("Changes saved.");
      void loadFindings();
    } catch { setDetailStatus("Failed to save."); }
    finally { setSavingDetail(false); }
  }, [selectedFinding, editNotes, editTags, loadFindings]);

  const handleCopyMarkdown = useCallback(() => {
    if (!selectedFinding) return;
    const md = findingToMarkdown(selectedFinding);
    if (navigator.clipboard) {
      navigator.clipboard.writeText(md).then(
        () => setDetailStatus("Markdown copied."),
        () => setDetailStatus("Failed to copy."),
      );
    } else {
      setDetailStatus("Clipboard not available.");
    }
  }, [selectedFinding]);

  const handleCreateTestPlan = useCallback(async (findingId: string) => {
    if (!selectedFinding) return;
    try {
      await req(`/api/notebook/findings/${findingId}/test-plan`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setDetailStatus("Test plan created.");
    } catch { setDetailStatus("Failed to create test plan."); }
  }, [selectedFinding]);

  const getFindingEvidence = useCallback((finding: NotebookFinding, runId: string | null, lapNumber: number | null) => {
    const hasZoneStart = Number.isFinite(finding.target_zone_start_pct);
    const hasZoneEnd = Number.isFinite(finding.target_zone_end_pct);
    return {
      runId,
      lapNumber,
      lapScope: lapNumber != null ? "single_lap" as const : "run" as const,
      zoneStartPct: hasZoneStart ? finding.target_zone_start_pct : null,
      zoneEndPct: hasZoneEnd ? finding.target_zone_end_pct : null,
      valueBasis: lapNumber != null ? "full_lap" as const : "run_level" as const,
      lockState: "none" as const,
      selectionSource: "compare_verdict" as const,
    };
  }, []);

  const hasCompareRevisitContext = !!(selectedFinding?.baseline_run_id && selectedFinding?.test_run_id);
  const hasSingleRunRevisitContext = !!(selectedFinding?.baseline_run_id || selectedFinding?.test_run_id);
  const compareRevisitTitle = hasCompareRevisitContext
    ? "Review this finding in Laps"
    : "Not available for this run";
  const singleRunRevisitTitle = hasSingleRunRevisitContext
    ? undefined
    : "Not available for this run";

  // -- render --------------------------------------------------
  return (
    <section className="notebook-tab">
      <header className="notebook-header">
        <h2><BookOpen size={18} /> Notebook & Setup Memory</h2>
        <nav className="notebook-nav">
          {(["findings", "test-plans", "setup-memory"] as NotebookView[]).map((v) => (
            <button key={v} className={`subnav-item ${view === v ? "active" : ""}`} onClick={() => setView(v)}>
              {v === "findings" ? "Findings" : v === "test-plans" ? "Test Plans" : "Setup Memory"}
            </button>
          ))}
        </nav>
      </header>

      {view === "findings" && (
        <div className="notebook-findings">
          <div className="setup-memory-grid" style={{ marginBottom: 10 }}>
            <div className="memory-card">
              <span className="memory-stat">{findings.length}</span>
              <span className="memory-label">Findings</span>
            </div>
            <div className="memory-card" style={{ borderLeftColor: "#ef4444" }}>
              <span className="memory-stat">{findings.filter((finding) => finding.verdict === "undo").length}</span>
              <span className="memory-label">High</span>
            </div>
            <div className="memory-card" style={{ borderLeftColor: "#f59e0b" }}>
              <span className="memory-stat">{findings.filter((finding) => finding.verdict === "retest").length}</span>
              <span className="memory-label">Watch</span>
            </div>
            <div className="memory-card" style={{ borderLeftColor: "#22c55e" }}>
              <span className="memory-stat">{findings.filter((finding) => finding.status === "confirmed").length}</span>
              <span className="memory-label">Confirmed</span>
            </div>
          </div>
          <div className="notebook-filters">
            <input placeholder="Car" value={filterCar} onChange={(e) => setFilterCar(e.target.value)} className="filter-input" />
            <input placeholder="Track" value={filterTrack} onChange={(e) => setFilterTrack(e.target.value)} className="filter-input" />
            <select value={filterVerdict} onChange={(e) => setFilterVerdict(e.target.value)}>
              <option value="">All verdicts</option>
              <option value="keep_direction">Keep</option>
              <option value="undo">Undo</option>
              <option value="retest">Retest</option>
              <option value="inconclusive">Inconclusive</option>
            </select>
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="">All statuses</option>
              <option value="saved">Saved</option>
              <option value="confirmed">Confirmed</option>
              <option value="rejected">Rejected</option>
              <option value="needs_retest">Needs Retest</option>
              <option value="archived">Archived</option>
            </select>
            <button className="secondary-button" onClick={loadFindings}><RotateCcw size={14} /> Refresh</button>
          </div>

          {loading && <p className="muted">Loading findings...</p>}

          {!loading && findings.length === 0 && (
            <div className="notebook-empty">
              <p>No findings yet. Run a comparison and save it to the Notebook.</p>
            </div>
          )}

          {findings.length > 0 && (
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Verdict / Finding Title</th>
                  <th>Run / Track / Car</th>
                  <th>Lap / Window / Zone</th>
                  <th>Evidence Type</th>
                  <th>Status</th>
                  <th>Last Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((f) => (
                  <tr key={f.finding_id} className="finding-row" onClick={() => handleSelectFinding(f)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleSelectFinding(f); } }} tabIndex={0} role="button" aria-label={`Open finding: ${f.summary_headline ?? f.finding_id}`}>
                    <td className="cell-delta" style={{ color: (f.verdict === "undo" ? "#ef4444" : f.verdict === "retest" ? "#f59e0b" : "#22c55e") }}>
                      {f.verdict === "undo" ? "HIGH" : f.verdict === "retest" ? "WATCH" : "INFO"}
                    </td>
                    <td className="cell-val">{(f.verdict?.replace(/_/g, " ") ?? "-").toUpperCase()} - {f.summary_headline ?? "-"}</td>
                    <td className="cell-label">{f.baseline_run_id?.slice(0, 8) ?? "-"} - {f.track_name ?? "-"} - {f.car_name ?? "-"}</td>
                    <td className="cell-val">
                      L{f.baseline_lap ?? "-"} / L{f.test_lap ?? "-"} - {f.target_zone_start_pct.toFixed(1)}-{f.target_zone_end_pct.toFixed(1)}%
                    </td>
                    <td className="cell-val">{f.target_zone_classification ?? "comparison"}</td>
                    <td>
                      <span className="status-badge" style={{ color: STATUS_COLORS[f.status] ?? "#8d9aaa" }}>
                        {f.status}
                      </span>
                    </td>
                    <td className="cell-val">{f.updated_at?.slice(0, 10) ?? "-"}</td>
                    <td>
                      <button className="secondary-button" onClick={(e) => { e.stopPropagation(); handleCreateTestPlan(f.finding_id); }}>
                        <List size={12} /> Plan
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {view === "finding-detail" && selectedFinding && (
        <div className="notebook-detail">
          <button className="secondary-button" onClick={() => setView("findings")} style={{ marginBottom: 12 }}>
            Back to Findings
          </button>

          {detailStatus && (
            <p className="status-text" aria-live="polite">
              {detailStatus === "Changes saved." ? <><CheckCircle2 size={14} style={{ color: "#22c55e", marginRight: 4 }} />Saved</> : detailStatus}
            </p>
          )}

          <div className="insight-card" style={{ borderLeftColor: VERDICT_COLORS[selectedFinding.verdict ?? ""] ?? "#8d9aaa" }}>
            <h3>{selectedFinding.summary_headline ?? "Finding"}</h3>
            <div className="finding-meta">
              <span style={{ color: VERDICT_COLORS[selectedFinding.verdict ?? ""] ?? "#8d9aaa" }}>
                {selectedFinding.verdict?.replace(/_/g, " ").toUpperCase()}
              </span>
              <span>Confidence: {formatVal(selectedFinding.confidence_score * 100, 0)}%</span>
              <span>Tier: {selectedFinding.confidence_tier ?? "-"}</span>
              <span>Classification: {selectedFinding.target_zone_classification ?? "-"}</span>
            </div>
            <p className="finding-car-track">{selectedFinding.car_name} @ {selectedFinding.track_name} - {selectedFinding.setup_name}</p>
          </div>

          {selectedFinding.key_takeaways.length > 0 && (
            <div className="insight-section">
              <h4>Key Takeaways</h4>
              <ul>{selectedFinding.key_takeaways.map((t, i) => <li key={i}>{t}</li>)}</ul>
            </div>
          )}

          {selectedFinding.evidence.length > 0 && (
            <div className="insight-section">
              <h4>Evidence</h4>
              <ul>{selectedFinding.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </div>
          )}

          {selectedFinding.sector_summaries.length > 0 && (
            <div className="insight-section">
              <h4>Sector Deltas</h4>
              <table className="compact-table">
                <thead><tr><th>Sector</th><th>Speed Delta</th><th>CFS Delta</th></tr></thead>
                <tbody>
                  {selectedFinding.sector_summaries.map((s, i: number) => {
                    const row = s as FindingSectorSummary;
                    return (
                      <tr key={i}>
                        <td className="cell-label">{row.label ?? row.sector_name}</td>
                        <td className="cell-delta">{formatVal(row.avg_speed_delta_mph, 3)}</td>
                        <td className="cell-delta">{formatVal(row.min_cfs_delta_in, 3)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {selectedFinding.setup_changes.length > 0 && (
            <div className="insight-section">
              <h4>Setup Changes</h4>
              <table className="compact-table">
                <thead><tr><th>Setting</th><th>Delta</th></tr></thead>
                <tbody>
                  {selectedFinding.setup_changes.map((s, i: number) => {
                    const row = s as FindingSetupChange;
                    return (
                      <tr key={i}>
                        <td className="cell-label">{row.label ?? "-"}</td>
                        <td className="cell-delta">{row.delta ?? "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {selectedFinding.warnings.length > 0 && (
            <div className="insight-warnings">
              {selectedFinding.warnings.map((w, i) => (
                <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>
              ))}
            </div>
          )}

          {selectedFinding.next_step && (
            <p className="insight-recommendation"><strong>Next:</strong> {selectedFinding.next_step}</p>
          )}

          {/* -- Notes editor -- */}
          <div className="insight-section">
            <h4>Notes</h4>
            <textarea
              className="notes-editor"
              value={editNotes}
              onChange={(e) => setEditNotes(e.target.value)}
              rows={4}
              placeholder="Add notes about this finding..."
            />
          </div>

          {/* -- Tags editor -- */}
          <div className="insight-section">
            <h4>Tags</h4>
            <input
              className="filter-input"
              value={editTags}
              onChange={(e) => setEditTags(e.target.value)}
              placeholder="Comma-separated tags: talladega, platform, 55-70"
              style={{ width: "100%" }}
            />
          </div>

          {/* -- Actions -- */}
          <div className="finding-actions">
            <div className="selector-group">
              <label>Status</label>
              <select value={selectedFinding.status} onChange={(e) => handleUpdateStatus(selectedFinding.finding_id, e.target.value)}>
                <option value="saved">Saved</option>
                <option value="confirmed">Confirmed</option>
                <option value="rejected">Rejected</option>
                <option value="needs_retest">Needs Retest</option>
                <option value="archived">Archived</option>
              </select>
            </div>
            <button className="secondary-button" onClick={handleSaveDetail} disabled={savingDetail}>
              {savingDetail ? "Saving..." : "Save Changes"}
            </button>
          </div>

          {/* -- Relaunch actions -- */}
          <div className="toolbar-actions" style={{ marginTop: 12, flexWrap: "wrap" }}>
            <span className="section-note" style={{ fontSize: 10, color: "#8d9aaa", marginRight: 4, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Revisit:
            </span>
            <button className="trackmap-action-btn" onClick={() => {
              if (!selectedFinding.baseline_run_id || !selectedFinding.test_run_id) return;
              setBaseline({
                id: `notebook-baseline-${selectedFinding.finding_id}`,
                run_id: selectedFinding.baseline_run_id,
                lap_number: selectedFinding.baseline_lap,
                lap_scope: "single_lap",
                label: `Notebook baseline ${selectedFinding.finding_id}`,
                car: selectedFinding.car_name ?? null,
                track: selectedFinding.track_name ?? null,
                setup_label: selectedFinding.setup_name ?? null,
                lap_time: null,
                classification_tags: [],
                engineering_value: null,
                date: null,
                session_name: null,
                has_setup_snapshot: true,
                value_basis: selectedFinding.baseline_lap != null ? "full_lap" : "run_level",
              });
              setTest({
                id: `notebook-test-${selectedFinding.finding_id}`,
                run_id: selectedFinding.test_run_id,
                lap_number: selectedFinding.test_lap,
                lap_scope: "single_lap",
                label: `Notebook test ${selectedFinding.finding_id}`,
                car: selectedFinding.car_name ?? null,
                track: selectedFinding.track_name ?? null,
                setup_label: selectedFinding.setup_name ?? null,
                lap_time: null,
                classification_tags: [],
                engineering_value: null,
                date: null,
                session_name: null,
                has_setup_snapshot: true,
                value_basis: selectedFinding.test_lap != null ? "full_lap" : "run_level",
              });
              focusEvidence(
                getFindingEvidence(selectedFinding, selectedFinding.baseline_run_id, selectedFinding.baseline_lap),
                "laps",
              );
              setWorkspace("laps", "compare_verdict");
            }} disabled={!hasCompareRevisitContext} title={compareRevisitTitle} aria-label="Review finding in Laps">
              <BarChart3 size={10} /> Review in Laps
            </button>
            <button className="trackmap-action-btn" onClick={() => {
              const runId = selectedFinding.baseline_run_id ?? selectedFinding.test_run_id;
              if (runId) {
                focusEvidence(
                  getFindingEvidence(
                    selectedFinding,
                    runId,
                    selectedFinding.baseline_run_id ? selectedFinding.baseline_lap : selectedFinding.test_lap,
                  ),
                  "platform_trace",
                );
              }
            }} disabled={!hasSingleRunRevisitContext} title={singleRunRevisitTitle} aria-label="Revisit in Platform">
              <Layers size={10} /> Platform
            </button>
            <button className="trackmap-action-btn" onClick={() => {
              const runId = selectedFinding.baseline_run_id ?? selectedFinding.test_run_id;
              if (runId) {
                focusEvidence(
                  getFindingEvidence(
                    selectedFinding,
                    runId,
                    selectedFinding.baseline_run_id ? selectedFinding.baseline_lap : selectedFinding.test_lap,
                  ),
                  "map",
                );
              }
            }} disabled={!hasSingleRunRevisitContext} title={singleRunRevisitTitle} aria-label="Revisit on Map">
              <MapPin size={10} /> Map
            </button>
            <button className="trackmap-action-btn" onClick={() => {
              const runId = selectedFinding.baseline_run_id ?? selectedFinding.test_run_id;
              if (runId) {
                focusEvidence(
                  getFindingEvidence(
                    selectedFinding,
                    runId,
                    selectedFinding.baseline_run_id ? selectedFinding.baseline_lap : selectedFinding.test_lap,
                  ),
                  "setup_impact",
                );
              }
            }} disabled={!hasSingleRunRevisitContext} title={singleRunRevisitTitle} aria-label="Revisit in Setup">
              <Wrench size={10} /> Setup
            </button>
            <span style={{ flex: 1 }} />
            <button className="secondary-button" onClick={handleCopyMarkdown}>
              <Clipboard size={14} /> Copy Markdown
            </button>
            <button className="secondary-button" onClick={() => handleCreateTestPlan(selectedFinding.finding_id)}>
              <List size={14} /> Create Test Plan
            </button>
          </div>

          {/* -- Test plan status -- */}
          {selectedFinding.next_step && (
            <p className="insight-recommendation" style={{ marginTop: 12 }}>
              <strong>Next test:</strong> {selectedFinding.next_step}
            </p>
          )}
        </div>
      )}

      {view === "test-plans" && (
        <div className="notebook-test-plans">
          {testPlans.length === 0 && <p className="muted">No test plans yet. Create one from a finding.</p>}
          {testPlans.length > 0 && (
            <table className="compact-table">
              <thead><tr><th>Date</th><th>Car</th><th>Track</th><th>Goal</th><th>Change</th><th>Status</th></tr></thead>
              <tbody>
                {testPlans.map((p) => (
                  <tr key={p.test_plan_id}>
                    <td className="cell-val">{p.created_at?.slice(0, 10)}</td>
                    <td className="cell-label">{p.car_name}</td>
                    <td className="cell-label">{p.track_name}</td>
                    <td className="cell-val">{p.goal ?? "-"}</td>
                    <td className="cell-val">{p.change_to_try ?? "-"}</td>
                    <td className="cell-delta">{p.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {view === "setup-memory" && (
        <div className="notebook-setup-memory">
          <div className="notebook-filters">
            <input placeholder="Car" value={filterCar} onChange={(e) => setFilterCar(e.target.value)} className="filter-input" />
            <input placeholder="Track" value={filterTrack} onChange={(e) => setFilterTrack(e.target.value)} className="filter-input" />
            <button className="secondary-button" onClick={loadSetupMemory}><RotateCcw size={14} /> Refresh</button>
          </div>

          {!setupMemory && <p className="muted">Select filters and refresh to load setup memory.</p>}

          {setupMemory && (
            <div className="setup-memory-grid">
              <div className="memory-card">
                <span className="memory-stat">{setupMemory.total_findings}</span>
                <span className="memory-label">Total Findings</span>
              </div>
              <div className="memory-card" style={{ borderLeftColor: "#22c55e" }}>
                <span className="memory-stat">{setupMemory.keep_count}</span>
                <span className="memory-label">Keep</span>
              </div>
              <div className="memory-card" style={{ borderLeftColor: "#ef4444" }}>
                <span className="memory-stat">{setupMemory.undo_count}</span>
                <span className="memory-label">Undo</span>
              </div>
              <div className="memory-card" style={{ borderLeftColor: "#f59e0b" }}>
                <span className="memory-stat">{setupMemory.retest_count}</span>
                <span className="memory-label">Retest</span>
              </div>
              <div className="memory-card">
                <span className="memory-stat">{setupMemory.confirmed_count}</span>
                <span className="memory-label">Confirmed</span>
              </div>
              <div className="memory-card">
                <span className="memory-stat">{setupMemory.rejected_count}</span>
                <span className="memory-label">Rejected</span>
              </div>
              {setupMemory.most_common_issue && (
                <div className="memory-card-wide">
                  <span className="memory-label">Most Common Issue</span>
                  <span className="memory-stat">{setupMemory.most_common_issue}</span>
                </div>
              )}
              {setupMemory.best_known_target_zone && (
                <div className="memory-card-wide">
                  <span className="memory-label">Best Known Target Zone</span>
                  <span className="memory-stat">{setupMemory.best_known_target_zone}</span>
                </div>
              )}
              {setupMemory.recommended_next_test && (
                <div className="memory-card-wide">
                  <span className="memory-label">Recommended Next Test</span>
                  <span className="memory-stat">{setupMemory.recommended_next_test}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}


