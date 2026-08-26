import { AlertTriangle, BarChart3, BookOpen, CheckCircle2, Clipboard, Layers, MapPin, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { requestJson } from "../api/client";
import { useCompareBasket } from "../store/CompareBasketContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { NotebookFinding } from "../types/compare";
import { findingToMarkdown } from "../utils/exportUtils";
import { evidenceStrengthOutOf100 } from "../utils/evidenceScore";

type NotebookView = "findings" | "finding-detail";
type FindingSectorSummary = {
  label?: string;
  sector_name?: string;
  avg_speed_delta_mph?: number | null;
  min_cfs_delta_in?: number | null;
};

const STATUS_COLORS: Record<NotebookFinding["status"], string> = {
  saved: "#38bdf8",
  archived: "#8d9aaa",
};

function formatVal(value: number | null | undefined, digits = 2): string {
  return value != null && !Number.isNaN(value) ? value.toFixed(digits) : "-";
}

export function NotebookTab() {
  const { focusEvidence, setWorkspace } = useTelemetrySelection();
  const { setBaseline, setTest } = useCompareBasket();
  const [view, setView] = useState<NotebookView>("findings");
  const [findings, setFindings] = useState<NotebookFinding[]>([]);
  const [selectedFinding, setSelectedFinding] = useState<NotebookFinding | null>(null);
  const [loading, setLoading] = useState(false);
  const [filterCar, setFilterCar] = useState("");
  const [filterTrack, setFilterTrack] = useState("");
  const [filterStatus, setFilterStatus] = useState<"" | NotebookFinding["status"]>("");
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
      if (filterStatus) params.set("status", filterStatus);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      setFindings(await requestJson<NotebookFinding[]>(`/api/notebook/findings${suffix}`));
    } catch {
      setFindings([]);
    } finally {
      setLoading(false);
    }
  }, [filterCar, filterStatus, filterTrack]);

  useEffect(() => { void loadFindings(); }, [loadFindings]);
  useEffect(() => {
    if (detailStatus !== "Changes saved.") return;
    const timer = window.setTimeout(() => setDetailStatus(null), 2000);
    return () => window.clearTimeout(timer);
  }, [detailStatus]);

  const handleSelectFinding = useCallback((finding: NotebookFinding) => {
    setSelectedFinding(finding);
    setEditNotes(finding.notes ?? "");
    setEditTags((finding.tags ?? []).join(", "));
    setDetailStatus(null);
    setView("finding-detail");
  }, []);

  const handleUpdateStatus = useCallback(async (
    findingId: string,
    status: NotebookFinding["status"],
  ) => {
    if (!selectedFinding) return;
    try {
      const updated = await requestJson<NotebookFinding>(`/api/notebook/findings/${findingId}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setSelectedFinding(updated);
      setDetailStatus(status === "archived" ? "Observation archived." : "Observation restored.");
      void loadFindings();
    } catch {
      setDetailStatus("Failed to update.");
    }
  }, [loadFindings, selectedFinding]);

  const handleSaveDetail = useCallback(async () => {
    if (!selectedFinding) return;
    setSavingDetail(true);
    setDetailStatus(null);
    try {
      const tags = editTags.split(",").map((tag) => tag.trim()).filter(Boolean);
      const updated = await requestJson<NotebookFinding>(
        `/api/notebook/findings/${selectedFinding.finding_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ notes: editNotes, tags }),
        },
      );
      setSelectedFinding(updated);
      setDetailStatus("Changes saved.");
      void loadFindings();
    } catch {
      setDetailStatus("Failed to save.");
    } finally {
      setSavingDetail(false);
    }
  }, [editNotes, editTags, loadFindings, selectedFinding]);

  const handleCopyMarkdown = useCallback(() => {
    if (!selectedFinding) return;
    const markdown = findingToMarkdown(selectedFinding);
    if (!navigator.clipboard) {
      setDetailStatus("Clipboard not available.");
      return;
    }
    navigator.clipboard.writeText(markdown).then(
      () => setDetailStatus("Markdown copied."),
      () => setDetailStatus("Failed to copy."),
    );
  }, [selectedFinding]);

  const getFindingEvidence = useCallback((
    finding: NotebookFinding,
    runId: string | null,
    lapNumber: number | null,
  ) => ({
    runId,
    lapNumber,
    lapScope: lapNumber != null ? "single_lap" as const : "run" as const,
    zoneStartPct: Number.isFinite(finding.target_zone_start_pct)
      ? finding.target_zone_start_pct
      : null,
    zoneEndPct: Number.isFinite(finding.target_zone_end_pct)
      ? finding.target_zone_end_pct
      : null,
    valueBasis: lapNumber != null ? "full_lap" as const : "run_level" as const,
    lockState: "none" as const,
    selectionSource: "compare_verdict" as const,
  }), []);

  const hasCompareContext = !!(selectedFinding?.baseline_run_id && selectedFinding?.test_run_id);
  const hasRunContext = !!(selectedFinding?.baseline_run_id || selectedFinding?.test_run_id);

  return (
    <section className="notebook-tab">
      <header className="notebook-header">
        <h2><BookOpen size={18} /> Observation Notebook</h2>
      </header>

      <p className="section-note">
        This is a read-only observation log. Notes, tags, and archive state are editable, but Notebook
        entries cannot authorize setup changes, Keep/Undo decisions, or test plans. Use a P19 controlled
        workflow for those decisions.
      </p>

      {view === "findings" && (
        <div className="notebook-findings">
          <div className="notebook-observation-stats" style={{ marginBottom: 10 }}>
            <div className="observation-stat-card">
              <span className="observation-stat-value">{findings.length}</span>
              <span className="observation-stat-label">Observations</span>
            </div>
            <div className="observation-stat-card" style={{ borderLeftColor: "#38bdf8" }}>
              <span className="observation-stat-value">{findings.filter((finding) => finding.status === "saved").length}</span>
              <span className="observation-stat-label">Saved</span>
            </div>
            <div className="observation-stat-card" style={{ borderLeftColor: "#8d9aaa" }}>
              <span className="observation-stat-value">{findings.filter((finding) => finding.status === "archived").length}</span>
              <span className="observation-stat-label">Archived</span>
            </div>
          </div>

          <div className="notebook-filters">
            <input placeholder="Car" value={filterCar} onChange={(event) => setFilterCar(event.target.value)} className="filter-input" />
            <input placeholder="Track" value={filterTrack} onChange={(event) => setFilterTrack(event.target.value)} className="filter-input" />
            <select
              value={filterStatus}
              onChange={(event) => setFilterStatus(
                event.target.value === "saved" || event.target.value === "archived"
                  ? event.target.value
                  : "",
              )}
            >
              <option value="">All records</option>
              <option value="saved">Saved</option>
              <option value="archived">Archived</option>
            </select>
            <button className="secondary-button" onClick={loadFindings}>
              <RotateCcw size={14} /> Refresh
            </button>
          </div>

          {loading && <p className="muted">Loading observations...</p>}
          {!loading && findings.length === 0 && (
            <div className="notebook-empty">
              <p>No observations yet. Save telemetry evidence from a comparison to review it here.</p>
            </div>
          )}

          {findings.length > 0 && (
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Observation</th>
                  <th>Run / Track / Car</th>
                  <th>Lap / Window / Zone</th>
                  <th>Evidence Type</th>
                  <th>Record State</th>
                  <th>Last Updated</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((finding) => (
                  <tr
                    key={finding.finding_id}
                    className="finding-row"
                    onClick={() => handleSelectFinding(finding)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleSelectFinding(finding);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    aria-label={`Open observation: ${finding.summary_headline ?? finding.finding_id}`}
                  >
                    <td className="cell-val">{finding.summary_headline ?? "Recorded telemetry observation"}</td>
                    <td className="cell-label">
                      {finding.baseline_run_id?.slice(0, 8) ?? "-"} - {finding.track_name ?? "-"} - {finding.car_name ?? "-"}
                    </td>
                    <td className="cell-val">
                      L{finding.baseline_lap ?? "-"} / L{finding.test_lap ?? "-"} - {finding.target_zone_start_pct.toFixed(1)}-{finding.target_zone_end_pct.toFixed(1)}%
                    </td>
                    <td className="cell-val">{finding.target_zone_classification ?? "comparison"}</td>
                    <td>
                      <span className="status-badge" style={{ color: STATUS_COLORS[finding.status] }}>
                        {finding.status}
                      </span>
                    </td>
                    <td className="cell-val">{finding.updated_at?.slice(0, 10) ?? "-"}</td>
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
            Back to Observations
          </button>

          {detailStatus && (
            <p className="status-text" aria-live="polite">
              {detailStatus === "Changes saved."
                ? <><CheckCircle2 size={14} style={{ color: "#22c55e", marginRight: 4 }} />Saved</>
                : detailStatus}
            </p>
          )}

          <div className="insight-card" style={{ borderLeftColor: "#38bdf8" }}>
            <h3>{selectedFinding.summary_headline ?? "Recorded telemetry observation"}</h3>
            <div className="finding-meta">
              <span>Evidence strength: {evidenceStrengthOutOf100(selectedFinding.confidence_score)}</span>
              <span>Tier: {selectedFinding.confidence_tier ?? "-"}</span>
              <span>Classification: {selectedFinding.target_zone_classification ?? "-"}</span>
            </div>
            <p className="finding-car-track">
              {selectedFinding.car_name} @ {selectedFinding.track_name} - {selectedFinding.setup_name}
            </p>
          </div>

          {selectedFinding.key_takeaways.length > 0 && (
            <div className="insight-section">
              <h4>Recorded Observations</h4>
              <ul>{selectedFinding.key_takeaways.map((takeaway, index) => <li key={index}>{takeaway}</li>)}</ul>
            </div>
          )}

          {selectedFinding.evidence.length > 0 && (
            <div className="insight-section">
              <h4>Evidence</h4>
              <ul>{selectedFinding.evidence.map((item, index) => <li key={index}>{item}</li>)}</ul>
            </div>
          )}

          {selectedFinding.sector_summaries.length > 0 && (
            <div className="insight-section">
              <h4>Sector Deltas</h4>
              <table className="compact-table">
                <thead><tr><th>Sector</th><th>Speed Delta</th><th>CFS Delta</th></tr></thead>
                <tbody>
                  {selectedFinding.sector_summaries.map((summary, index) => {
                    const row = summary as FindingSectorSummary;
                    return (
                      <tr key={index}>
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

          {selectedFinding.warnings.length > 0 && (
            <div className="insight-warnings">
              {selectedFinding.warnings.map((warning, index) => (
                <p key={index} className="warning-line"><AlertTriangle size={12} /> {warning}</p>
              ))}
            </div>
          )}

          <div className="insight-section">
            <h4>Notes</h4>
            <textarea
              className="notes-editor"
              value={editNotes}
              onChange={(event) => setEditNotes(event.target.value)}
              rows={4}
              placeholder="Add personal notes about this observation..."
            />
          </div>

          <div className="insight-section">
            <h4>Tags</h4>
            <input
              className="filter-input"
              value={editTags}
              onChange={(event) => setEditTags(event.target.value)}
              placeholder="Comma-separated tags: talladega, platform, 55-70"
              style={{ width: "100%" }}
            />
          </div>

          <div className="finding-actions">
            <div className="selector-group">
              <label>Record state</label>
              <select
                value={selectedFinding.status}
                onChange={(event) => handleUpdateStatus(
                  selectedFinding.finding_id,
                  event.target.value === "archived" ? "archived" : "saved",
                )}
              >
                <option value="saved">Saved</option>
                <option value="archived">Archived</option>
              </select>
            </div>
            <button className="secondary-button" onClick={handleSaveDetail} disabled={savingDetail}>
              {savingDetail ? "Saving..." : "Save Notes & Tags"}
            </button>
          </div>

          <div className="toolbar-actions" style={{ marginTop: 12, flexWrap: "wrap" }}>
            <span className="section-note" style={{ fontSize: 10, color: "#8d9aaa", marginRight: 4, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Inspect evidence:
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
            }} disabled={!hasCompareContext} title={hasCompareContext ? "Inspect this observation in Laps" : "Not available for this record"} aria-label="Inspect observation in Laps">
              <BarChart3 size={10} /> Laps
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
            }} disabled={!hasRunContext} title={hasRunContext ? undefined : "Not available for this record"} aria-label="Inspect observation in Platform">
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
            }} disabled={!hasRunContext} title={hasRunContext ? undefined : "Not available for this record"} aria-label="Inspect observation on Map">
              <MapPin size={10} /> Map
            </button>
            <span style={{ flex: 1 }} />
            <button className="secondary-button" onClick={handleCopyMarkdown}>
              <Clipboard size={14} /> Copy Observation
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
