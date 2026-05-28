import { AlertTriangle, BarChart3, Bookmark } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchCompareInsights } from "../api/client";
import { ComparisonInsightPanel } from "../components/ComparisonInsightPanel";
import { DeltaTracesView } from "../components/DeltaTracesView";
import { DidItWorkCard } from "../components/DidItWorkCard";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { RunListItem } from "../types/telemetry";
import type {
  ChannelDeltaStats, CompareResponse, ComparisonInsightsResponse, CornerName, CornerMetric,
  CornerMatrix,
  DidItWorkVerdict, DriverComparison, PlatformComparison,
  PowertrainComparison, ShockComparison, SetupChange, TireComparison,
  WholeCarIndex,
} from "../types/compare";

const API_BASE = import.meta.env.VITE_RACELAB_API_BASE_URL ?? "http://127.0.0.1:8000";

type CompareTabProps = { runs: RunListItem[]; currentRunId: string };
type SubView =
  | "verdict" | "what-changed" | "whole-car-index" | "target-zone"
  | "platform" | "four-corners" | "tires" | "shocks"
  | "driver" | "engine-pull" | "delta-traces" | "evidence" | "insights";

type PreviewData = {
  baseline_laps: number[]; test_laps: number[];
  suggested_baseline_lap: number | null; suggested_test_lap: number | null;
  setup_changes: SetupChange[]; context_changes: Array<{ key: string; label: string; warning: string | null; is_problem: boolean }>;
  warnings: string[];
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json" }, ...init });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ── utilities ───────────────────────────────────────────────

function safeDelta(d: ChannelDeltaStats | null | undefined): ChannelDeltaStats | null {
  return d ?? null;
}

function formatVal(v: number | null | undefined, digits = 2): string {
  return v != null && !Number.isNaN(v) ? v.toFixed(digits) : "—";
}

function formatDelta(d: ChannelDeltaStats | null | undefined): string {
  const s = safeDelta(d);
  if (!s || s.delta_avg == null) return "—";
  const sign = s.delta_avg > 0 ? "+" : "";
  return `${sign}${s.delta_avg.toFixed(3)} ${s.unit ?? ""}`.trim();
}

function formatBaselineTest(d: ChannelDeltaStats | null | undefined, digits = 2): string {
  const s = safeDelta(d);
  if (!s) return "—";
  return `${formatVal(s.baseline_avg, digits)} → ${formatVal(s.test_avg, digits)}`;
}

function dirColor(dir: string | null | undefined): string {
  if (!dir) return "#8d9aaa";
  if (dir === "better") return "#22c55e";
  if (dir === "worse") return "#ef4444";
  if (dir === "mixed" || dir === "context") return "#f59e0b";
  return "#8d9aaa";
}

function deltaRow(label: string, d: ChannelDeltaStats | null | undefined, unit = "") {
  const s = safeDelta(d);
  return (
    <tr key={label}>
      <td className="cell-label">{label}</td>
      <td className="cell-val">{formatVal(s?.baseline_avg, unit === "rpm" ? 0 : 3)}</td>
      <td className="cell-val">{formatVal(s?.test_avg, unit === "rpm" ? 0 : 3)}</td>
      <td className="cell-delta" style={{ color: dirColor(s?.direction) }}>
        {s?.delta_avg != null ? `${s.delta_avg > 0 ? "+" : ""}${s.delta_avg.toFixed(unit === "rpm" ? 0 : 3)}` : "—"}
      </td>
      <td className="cell-dir" style={{ color: dirColor(s?.direction) }}>{s?.direction ?? "—"}</td>
    </tr>
  );
}

function cornerMini(c: CornerName, m: CornerMetric | undefined) {
  return (
    <div key={c} className="corner-cell">
      <strong>{c}</strong>
      <div className="corner-rh">{formatBaselineTest(m?.ride_height_in)} in</div>
      <div className="corner-delta" style={{ color: dirColor(m?.ride_height_in?.direction) }}>
        {formatDelta(m?.ride_height_in)}
      </div>
    </div>
  );
}

// ── Sub-views ───────────────────────────────────────────────

function VerdictView({ verdict: v, disc, wci, confidence, draftWarning, weatherWarning, onSaveFinding, onStageNextTest, onOpenMap, saving, saveStatus, isSelfCompare }: {
  verdict: DidItWorkVerdict | null; disc: { score: number; label: string } | null;
  wci: WholeCarIndex | null; confidence: number;
  draftWarning?: string | null; weatherWarning?: string | null;
  onSaveFinding?: () => void; onStageNextTest?: () => void; onOpenMap?: () => void;
  saving?: boolean; saveStatus?: string | null; isSelfCompare?: boolean;
}) {
  if (!v) return <p className="muted">No verdict available.</p>;

  return (
    <div className="compare-subview">
      <DidItWorkCard
        verdict={(v.verdict as "keep_direction" | "undo_partially" | "undo" | "retest" | "inconclusive" | "reference_mode") ?? "inconclusive"}
        headline={v.headline}
        confidenceScore={confidence}
        testDisciplineScore={disc?.score}
        evidence={v.evidence}
        warnings={v.warnings}
        nextStep={v.next_step}
        draftWarning={draftWarning}
        weatherWarning={weatherWarning}
        onSaveFinding={isSelfCompare ? undefined : onSaveFinding}
        onStageNextTest={isSelfCompare ? undefined : onStageNextTest}
        onOpenMap={onOpenMap}
        saving={saving}
        saveStatus={saveStatus}
        disabled={isSelfCompare}
      />
      {wci && <div className="wci-strip">{indexStrip(wci)}</div>}
    </div>
  );
}

function indexStrip(wci: WholeCarIndex) {
  const items: [string, number | null][] = [
    ["Speed", wci.speed_index], ["Platform", wci.platform_index],
    ["Driver", wci.driver_index], ["Powertrain", wci.powertrain_index],
    ["Tires", wci.tire_index], ["Shocks", wci.shock_index],
    ["Discipline", wci.test_discipline_index], ["Overall", wci.overall_index],
  ];
  return (
    <div className="wci-strip">
      {items.map(([label, score]) => (
        <div key={label} className="wci-item">
          <span className="wci-label">{label}</span>
          <span className="wci-score">{score != null ? score.toFixed(0) : "—"}</span>
        </div>
      ))}
      {wci.overall_label && <span className="wci-label">{wci.overall_label}</span>}
    </div>
  );
}

function WholeCarIndexView({ wci }: { wci: WholeCarIndex | null }) {
  if (!wci) return <p className="muted">Whole Car Index not available.</p>;
  const rows: [string, number | null][] = [
    ["Speed Index", wci.speed_index], ["Platform Index", wci.platform_index],
    ["Tire Index", wci.tire_index], ["Shock Index", wci.shock_index],
    ["Driver Index", wci.driver_index], ["Powertrain Index", wci.powertrain_index],
    ["Test Discipline Index", wci.test_discipline_index],
    ["Confidence Index", wci.confidence_index], ["Overall Index", wci.overall_index],
  ];
  return (
    <div className="compare-subview">
      {indexStrip(wci)}
      <table className="compact-table">
        <thead><tr><th>Metric</th><th>Score</th><th>Label</th></tr></thead>
        <tbody>
          {rows.map(([label, score]) => (
            <tr key={label} className={label === "Overall Index" ? "overall-row" : ""}>
              <td className="cell-label">{label}</td>
              <td className="cell-val">{score != null ? score.toFixed(1) : "—"}</td>
              <td className={`cell-dir`} style={{ color: score != null && score >= 70 ? "#22c55e" : score != null && score >= 40 ? "#f59e0b" : "#ef4444" }}>
                {score != null ? (score >= 85 ? "Strong" : score >= 70 ? "Good" : score >= 55 ? "Mixed" : score >= 40 ? "Low" : "Worse") : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WhatChangedView({ setup, context }: { setup: SetupChange[]; context: Array<{ key: string; label: string; warning: string | null; is_problem: boolean }> }) {
  const grouped = useMemo(() => {
    const g: Record<string, SetupChange[]> = {};
    for (const s of setup) {
      const grp = s.group ?? "unknown";
      if (!g[grp]) g[grp] = [];
      g[grp].push(s);
    }
    return g;
  }, [setup]);

  if (setup.length === 0 && context.length === 0) return <p className="muted">No setup/context changes detected in this comparison.</p>;
  return (
    <div className="compare-subview">
      {Object.entries(grouped).length > 0 && Object.entries(grouped).map(([group, items]) => (
        <div key={group} className="setup-group">
          <h4>{group.replace(/_/g, " ")}</h4>
          <table className="compact-table">
            <thead><tr><th>Setting</th><th>Baseline</th><th>Test</th><th>Delta</th><th>Significance</th></tr></thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.setup_key} className={`significance-${s.significance}`}>
                  <td className="cell-label">{s.label}</td>
                  <td className="cell-val">{String(s.baseline_value ?? "—")}</td>
                  <td className="cell-val">{String(s.test_value ?? "—")}</td>
                  <td className="cell-delta">{s.delta ?? "—"}</td>
                  <td className="cell-dir">{s.significance}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {context.filter(c => c.warning).length > 0 && (
        <div className="context-warnings">
          <h4>Context</h4>
          {context.filter(c => c.warning).map(c => (
            <p key={c.key} className="warning-line"><AlertTriangle size={12} /> {c.warning}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function TargetZoneView({ data: r, onOpenDeltaTraces }: { data: CompareResponse; onOpenDeltaTraces?: () => void }) {
  return (
    <div className="compare-subview">
      <h3>Target Zone {r.target_zone_start_pct}–{r.target_zone_end_pct}%</h3>
      {r.verdict && (
        <p>Speed: <strong>{r.verdict.headline}</strong></p>
      )}
      {r.platform && (
        <table className="compact-table">
          <thead><tr><th>Metric</th><th>Direction</th></tr></thead>
          <tbody>
            {deltaRow("CFS Height", r.platform.cfs_height, "in")}
            {deltaRow("Center Rake FS", r.platform.center_rake_fs, "in")}
            {deltaRow("Side Rake", r.platform.side_rake, "in")}
            {deltaRow("Dynamic Pressure", r.platform.dynamic_pressure, "psf")}
          </tbody>
        </table>
      )}
      {onOpenDeltaTraces && (
        <button className="secondary-button" onClick={onOpenDeltaTraces} style={{ marginTop: 8 }}>
          <BarChart3 size={14} /> Open Delta Traces
        </button>
      )}
    </div>
  );
}

function PlatformView({ platform, onOpenDeltaTraces }: { platform: PlatformComparison | null; onOpenDeltaTraces?: () => void }) {
  if (!platform) return <p className="muted">Platform comparison not available.</p>;
  return (
    <div className="compare-subview">
      <table className="compact-table">
        <thead><tr><th>Metric</th><th>Baseline</th><th>Test</th><th>Delta</th><th>Direction</th></tr></thead>
        <tbody>
          {deltaRow("CFS Height", platform.cfs_height, "in")}
          {deltaRow("Front Avg RH", platform.front_avg_rh, "in")}
          {deltaRow("Rear Avg RH", platform.rear_avg_rh, "in")}
          {deltaRow("Center Rake FS", platform.center_rake_fs, "in")}
          {deltaRow("Side Rake", platform.side_rake, "in")}
          {deltaRow("Dynamic Pressure", platform.dynamic_pressure, "psf")}
          {deltaRow("CFS Risk Score", platform.cfs_risk_score, "score")}
        </tbody>
      </table>
      <p className="platform-verdict">Platform Verdict: {platform.platform_verdict ?? "—"}</p>
      {onOpenDeltaTraces && (
        <button className="secondary-button" onClick={onOpenDeltaTraces} style={{ marginTop: 8 }}>
          <BarChart3 size={14} /> Open Delta Traces
        </button>
      )}
    </div>
  );
}

function FourCornersView({ cm, onOpenDeltaTraces }: { cm: Partial<CornerMatrix> | null; onOpenDeltaTraces?: () => void }) {
  const corners: CornerName[] = ["LF", "RF", "LR", "RR"];
  const rows: Array<{ label: string; key: keyof CornerMetric }> = [
    { label: "Ride Height [in]", key: "ride_height_in" },
    { label: "Shock Defl [in]", key: "shock_defl_in" },
    { label: "Tire Pressure", key: "tire_pressure" },
    { label: "Wheel Speed", key: "wheel_speed" },
    { label: "Slip Ratio", key: "slip_ratio_proxy" },
  ];
  return (
    <div className="compare-subview">
      <p className="section-note">Baseline → Test | Delta | Direction</p>
      <p className="warning-line" style={{ marginBottom: 8 }}>
        Short runs reduce confidence for tire wear and falloff conclusions.
      </p>
      <table className="compact-table corner-matrix">
        <thead><tr><th>Metric</th>{corners.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.key}>
              <td className="cell-label">{row.label}</td>
              {corners.map(c => {
                const m = cm?.[c];
                const d = m ? (m[row.key] as ChannelDeltaStats | null) ?? null : null;
                return (
                  <td key={c} className="cell-corner" style={{ color: dirColor(d?.direction) }}>
                    {d ? `${formatVal(d.baseline_avg, 3)} → ${formatVal(d.test_avg, 3)}` : "Unavailable"}
                    <br /><small>{d?.direction ?? ""}</small>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="corner-mini-layout">
        <div className="corner-front-label">FRONT</div>
        <div className="corner-row">{["LF", "RF"].map(c => cornerMini(c as CornerName, cm?.[c as CornerName]))}</div>
        <div className="corner-row">{["LR", "RR"].map(c => cornerMini(c as CornerName, cm?.[c as CornerName]))}</div>
        <div className="corner-rear-label">REAR</div>
      </div>
      {onOpenDeltaTraces && (
        <button className="secondary-button" onClick={onOpenDeltaTraces} style={{ marginTop: 8 }}>
          <BarChart3 size={14} /> Open Delta Traces
        </button>
      )}
    </div>
  );
}

function DriverView({ driver }: { driver: DriverComparison | null }) {
  if (!driver) return <p className="muted">Driver comparison not available.</p>;
  return (
    <div className="compare-subview">
      <table className="compact-table">
        <thead><tr><th>Metric</th><th>Baseline</th><th>Test</th><th>Delta</th><th>Direction</th></tr></thead>
        <tbody>
          {deltaRow("Throttle", driver.avg_throttle_pct, "%")}
          {deltaRow("Brake", driver.avg_brake_pct, "%")}
          {deltaRow("Steering Avg", driver.avg_abs_steering_deg, "deg")}
        </tbody>
      </table>
      {driver.driver_changed_warning && <p className="warning-line"><AlertTriangle size={12} /> {driver.driver_changed_warning}</p>}
      <p>Driver Verdict: {driver.driver_verdict ?? "—"}</p>
    </div>
  );
}

function EngineView({ pt }: { pt: PowertrainComparison | null }) {
  if (!pt) return <p className="muted">Powertrain comparison not available.</p>;
  return (
    <div className="compare-subview">
      <table className="compact-table">
        <thead><tr><th>Metric</th><th>Baseline</th><th>Test</th><th>Delta</th><th>Direction</th></tr></thead>
        <tbody>
          {deltaRow("RPM", pt.avg_rpm, "rpm")}
          {deltaRow("Pull Score", pt.pull_score, "mph/1000ft")}
        </tbody>
      </table>
      {pt.powertrain_verdict && <p>Verdict: {pt.powertrain_verdict}</p>}
    </div>
  );
}

function TiresView({ tire }: { tire: TireComparison | null }) {
  if (!tire) return <p className="muted">Tire comparison not available. Requires additional channels or a longer run.</p>;
  const corners: CornerName[] = ["LF", "RF", "LR", "RR"];
  return (
    <div className="compare-subview">
      <p className="warning-line"><AlertTriangle size={12} /> Tire wear/falloff conclusions are low confidence unless the run is long enough.</p>
      {tire.short_run_warning && <p className="warning-line"><AlertTriangle size={12} /> {tire.short_run_warning}</p>}

      <table className="compact-table">
        <thead><tr><th>Metric</th>{corners.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          <tr>
            <td className="cell-label">Tire Pressure</td>
            {corners.map(c => <td key={c} className="cell-corner">{formatBaselineTest(tire.corners?.[c]?.tire_pressure)}</td>)}
          </tr>
          <tr>
            <td className="cell-label">Wheel Speed</td>
            {corners.map(c => <td key={c} className="cell-corner">{formatBaselineTest(tire.corners?.[c]?.wheel_speed)}</td>)}
          </tr>
          <tr>
            <td className="cell-label">Slip Ratio</td>
            {corners.map(c => <td key={c} className="cell-corner" style={{ color: dirColor(tire.corners?.[c]?.slip_ratio_proxy?.direction) }}>{formatDelta(tire.corners?.[c]?.slip_ratio_proxy)}</td>)}
          </tr>
        </tbody>
      </table>

      <br />
      <div className="corner-mini-layout">
        <div className="corner-row">{corners.slice(0, 2).map(c => cornerMini(c as CornerName, tire.corners?.[c as CornerName]))}</div>
        <div className="corner-row">{corners.slice(2).map(c => cornerMini(c as CornerName, tire.corners?.[c as CornerName]))}</div>
      </div>
      {tire.tire_verdict && <p>Tire Verdict: {tire.tire_verdict}</p>}
    </div>
  );
}

function ShocksView({ shock }: { shock: ShockComparison | null }) {
  if (!shock) return <p className="muted">Shock comparison not available. Requires additional channels.</p>;
  const corners: CornerName[] = ["LF", "RF", "LR", "RR"];
  return (
    <div className="compare-subview">
      <table className="compact-table">
        <thead><tr><th>Metric</th>{corners.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          <tr>
            <td className="cell-label">Shock Defl [in]</td>
            {corners.map(c => <td key={c} className="cell-corner">{formatBaselineTest(shock.corners?.[c]?.shock_defl_in)}</td>)}
          </tr>
          <tr>
            <td className="cell-label">Shock Vel [in/s]</td>
            {corners.map(c => <td key={c} className="cell-corner">{formatBaselineTest(shock.corners?.[c]?.shock_vel_in_s)}</td>)}
          </tr>
        </tbody>
      </table>
      {shock.shock_verdict && <p>Shock Verdict: {shock.shock_verdict}</p>}
    </div>
  );
}

function EvidenceView({ verdict }: { verdict: DidItWorkVerdict | null }) {
  if (!verdict) return <p className="muted">No evidence available.</p>;
  return (
    <div className="compare-subview">
      {verdict.evidence.length > 0 && (
        <><h4>Evidence</h4>{verdict.evidence.map((e, i) => <p key={i} className="verdict-evidence">• {e}</p>)}</>
      )}
      {verdict.warnings.length > 0 && (
        <><h4>Warnings</h4>{verdict.warnings.map((w, i) => <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>)}</>
      )}
      {verdict.next_step && <p className="verdict-next"><strong>Next:</strong> {verdict.next_step}</p>}
    </div>
  );
}

// ── Main Tab ────────────────────────────────────────────────

export function CompareTab({ runs, currentRunId }: CompareTabProps) {
  const [baselineRunId, setBaselineRunId] = useState(currentRunId);
  const [testRunId, setTestRunId] = useState("");
  const [startPct, setStartPct] = useState(55);
  const [endPct, setEndPct] = useState(70);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [subview, setSubview] = useState<SubView>("verdict");
  const [loading, setLoading] = useState(false);
  const { setWorkspace } = useTelemetrySelection();
  const [error, setError] = useState<string | null>(null);
  const [insights, setInsights] = useState<ComparisonInsightsResponse | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Resolve car/track/setup from the baseline run in the runs list
  const baselineRun = runs.find((r) => r.run_id === baselineRunId);
  const carName = baselineRun?.car_name ?? null;
  const trackName = baselineRun?.track_name ?? null;

  const handleSaveFinding = useCallback(async (force = false) => {
    if (!result || saving) return;
    setSaving(true);
    setSaveStatus("Saving…");
    try {
      const body: Record<string, unknown> = {
        car_name: carName,
        track_name: trackName,
        baseline_run_id: baselineRunId,
        test_run_id: testRunId,
        comparison_id: result.comparison_id,
        baseline_lap: result.baseline_lap,
        test_lap: result.test_lap,
        target_zone_start_pct: startPct,
        target_zone_end_pct: endPct,
        verdict: result.verdict?.verdict ?? null,
        confidence_score: result.confidence_score,
        confidence_tier: result.confidence_score >= 0.7 ? "high" : result.confidence_score >= 0.4 ? "medium" : "low",
        test_discipline_score: result.test_discipline?.score ?? null,
        target_zone_classification: insights?.target_zone_classification?.classification ?? null,
        summary_headline: result.verdict?.headline ?? null,
        key_takeaways: insights?.key_takeaways ?? [],
        evidence: result.verdict?.evidence ?? [],
        warnings: [...(result.warnings ?? []), ...(insights?.warnings ?? [])],
        sector_summaries: insights?.sectors ?? [],
        setup_changes: result.setup_changes ?? [],
        context_changes: result.context_changes ?? [],
        next_step: result.verdict?.next_step ?? null,
        force,
      };
      const resp = await req<Record<string, unknown>>("/api/notebook/findings/from-comparison", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (resp.duplicate) {
        setSaveStatus("Finding already saved. Click again to save duplicate.");
        setSaving(false);
        return;
      }
      setSaveStatus("Finding saved to Notebook.");
    } catch {
      setSaveStatus("Failed to save finding.");
    } finally {
      setSaving(false);
    }
  }, [result, insights, baselineRunId, testRunId, startPct, endPct, carName, trackName, saving]);

  const otherRuns = runs.filter((r) => r.run_id !== baselineRunId);
  const isSameRun = testRunId === baselineRunId && testRunId !== "";

  // ── Same-run reference mode ──────────────────────────────────
  const isSelfCompare = result != null && result.baseline_lap === result.test_lap && isSameRun;

  // ── empty state: only one run ───────────────────────────────
  if (runs.length <= 1) {
    return (
      <section className="compare-workspace">
        <header className="compare-header">
          <h2>Compare Mode</h2>
          <p className="section-note">Whole-car comparison workbook.</p>
        </header>
        <div className="compare-empty">
          <p>Import another run to compare.</p>
          <p className="muted">You need at least two imported runs to use the compare workbook.</p>
        </div>
      </section>
    );
  }

  useEffect(() => {
    if (!testRunId || testRunId === baselineRunId) return;
    let cancelled = false;
    setPreviewLoading(true);
    req<PreviewData>(`/api/compare/preview?baseline_run_id=${encodeURIComponent(baselineRunId)}&test_run_id=${encodeURIComponent(testRunId)}`)
      .then(p => { if (!cancelled) { setPreview(p); setPreviewLoading(false); } })
      .catch(() => { if (!cancelled) { setPreview(null); setPreviewLoading(false); } });
    return () => { cancelled = true; };
  }, [baselineRunId, testRunId]);

  const handleCompare = useCallback(async () => {
    if (!testRunId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await req<CompareResponse>("/api/compare", {
        method: "POST",
        body: JSON.stringify({
          baseline_run_id: baselineRunId,
          test_run_id: testRunId,
          baseline_lap: preview?.suggested_baseline_lap ?? null,
          test_lap: preview?.suggested_test_lap ?? null,
          target_zone_start_pct: startPct,
          target_zone_end_pct: endPct,
        }),
      });
      setResult(res);
      setSubview("verdict");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Comparison failed");
    } finally {
      setLoading(false);
    }
  }, [baselineRunId, testRunId, startPct, endPct, preview]);

  // ── load insights when comparison exists ────────────────────
  useEffect(() => {
    if (!result) return;
    let cancelled = false;
    setInsightsLoading(true);
    fetchCompareInsights({
      baseline_run_id: baselineRunId,
      test_run_id: testRunId,
      baseline_lap: result.baseline_lap,
      test_lap: result.test_lap,
      target_zone_start_pct: startPct,
      target_zone_end_pct: endPct,
    }).then((data) => {
      if (!cancelled) { setInsights(data); setInsightsLoading(false); }
    }).catch(() => {
      if (!cancelled) { setInsights(null); setInsightsLoading(false); }
    });
    return () => { cancelled = true; };
  }, [result, baselineRunId, testRunId, startPct, endPct]);

  const subviewContent = useMemo(() => {
    if (!result) return null;
    switch (subview) {
      case "verdict": return (
        <div className="compare-subview">
          {isSelfCompare && (
            <div className="self-compare-banner">
              <span className="self-compare-badge">Reference Mode</span>
              <p className="self-compare-text">Baseline and test are the same run/lap, so no setup decision should be made from this comparison.</p>
            </div>
          )}
          <VerdictView
            verdict={result.verdict} disc={result.test_discipline}
            wci={result.whole_car_index} confidence={result.confidence_score}
            draftWarning={preview?.context_changes?.find(c => c.key === "draft" || c.key === "draft_status")?.warning ?? null}
            weatherWarning={preview?.context_changes?.find(c => c.key === "weather")?.warning ?? null}
            onSaveFinding={() => {
              const isDup = saveStatus === "Finding already saved. Click again to save duplicate.";
              handleSaveFinding(isDup);
            }}
            onStageNextTest={() => {
              handleSaveFinding(false);
              setWorkspace("notebook", "compare_verdict");
            }}
            onOpenMap={() => setWorkspace("map", "compare_verdict")}
            saving={saving}
            saveStatus={saveStatus}
            isSelfCompare={isSelfCompare}
          />
        </div>
      );
      case "what-changed": return <WhatChangedView setup={result.setup_changes} context={result.context_changes} />;
      case "whole-car-index": return <WholeCarIndexView wci={result.whole_car_index} />;
      case "target-zone": return <TargetZoneView data={result} onOpenDeltaTraces={() => setSubview("delta-traces")} />;
      case "platform": return <PlatformView platform={result.platform} onOpenDeltaTraces={() => setSubview("delta-traces")} />;
      case "four-corners": return <FourCornersView cm={result.corner_matrix} onOpenDeltaTraces={() => setSubview("delta-traces")} />;
      case "tires": return <TiresView tire={result.tire_comparison} />;
      case "shocks": return <ShocksView shock={result.shock_comparison} />;
      case "driver": return <DriverView driver={result.driver_comparison} />;
      case "engine-pull": return <EngineView pt={result.powertrain_comparison} />;
      case "delta-traces": return <DeltaTracesView baselineRunId={baselineRunId} testRunId={testRunId} startPct={startPct} endPct={endPct} result={result} />;
      case "evidence": return <EvidenceView verdict={result.verdict} />;
      case "insights": {
        if (insightsLoading) return <p className="muted">Loading insights…</p>;
        if (!insights) return <p className="muted">Insights not available.</p>;
        return (
          <div>
            {isSelfCompare && (
              <div className="self-compare-banner">
                <span className="self-compare-badge">Reference Mode</span>
                <p className="self-compare-text">Baseline and test are the same run/lap, so no setup decision should be made from this comparison.</p>
              </div>
            )}
            <ComparisonInsightPanel insights={insights} onOpenDeltaTraces={() => setSubview("delta-traces")} />
            <div className="toolbar-actions" style={{ marginTop: 12 }}>
              <button className="secondary-button" onClick={() => {
                const isDuplicate = saveStatus === "Finding already saved. Click again to save duplicate.";
                handleSaveFinding(isDuplicate);
              }} disabled={saving || isSelfCompare} title={isSelfCompare ? "Cannot save finding for self-comparison" : undefined}>
                <Bookmark size={14} /> {isSelfCompare ? "Self-Comparison" : saving ? "Saving…" : saveStatus === "Finding already saved. Click again to save duplicate." ? "Save Duplicate" : "Save Insight Finding"}
              </button>
              {saveStatus && <span className="status-text" style={{ marginLeft: 8 }}>{saveStatus}</span>}
            </div>
          </div>
        );
      }
      default: return null;
    }
  }, [result, subview, insights, insightsLoading]);

  return (
    <section className="compare-workspace">
      <header className="compare-header">
        <h2>Compare Mode</h2>
        <p className="section-note">Whole-car comparison workbook. Compare baseline vs test run.</p>
      </header>

      {/* selectors */}
      <div className="compare-selectors">
        <div className="selector-group">
          <label>Baseline Run</label>
          <select value={baselineRunId} onChange={(e) => { setBaselineRunId(e.target.value); setResult(null); }}>
            {runs.map(r => <option key={r.run_id} value={r.run_id}>{r.track_name ?? r.run_id.slice(0, 24)}</option>)}
          </select>
        </div>
        <div className="selector-group">
          <label>Test Run</label>
          <select value={testRunId} onChange={(e) => { setTestRunId(e.target.value); setResult(null); }}>
            <option value="">Select test run...</option>
            {otherRuns.map(r => <option key={r.run_id} value={r.run_id}>{r.track_name ?? r.run_id.slice(0, 24)}</option>)}
          </select>
        </div>
        <div className="selector-group">
          <label>Target Zone</label>
          <div className="zone-inputs">
            <input type="number" value={startPct} onChange={e => setStartPct(Number(e.target.value))} min={0} max={100} />%
            <span>–</span>
            <input type="number" value={endPct} onChange={e => setEndPct(Number(e.target.value))} min={0} max={100} />%
          </div>
        </div>
        <button className="primary-button" onClick={handleCompare} disabled={!testRunId || loading || isSameRun}>
          {loading ? "Comparing..." : isSameRun ? "Same run selected" : "Compare"}
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}

      {/* preview loading */}
      {previewLoading && <div className="compare-preview-loading"><span className="loading-spinner" /> Loading preview…</div>}

      {/* workbook */}
      {result && (
        <div className="compare-workbook">
          <nav className="compare-subnav">
            {(["verdict", "what-changed", "whole-car-index", "target-zone", "platform", "four-corners",
               "tires", "shocks", "driver", "engine-pull", "delta-traces", "evidence", "insights"] as SubView[]).map(sv => (
              <button key={sv} className={`subnav-item ${subview === sv ? "active" : ""}`} onClick={() => setSubview(sv)}>
                {sv === "verdict" ? "Verdict" : sv === "what-changed" ? "What Changed" : sv === "whole-car-index" ? "Index"
                 : sv === "target-zone" ? "Target Zone" : sv === "platform" ? "Platform" : sv === "four-corners" ? "4 Corners"
                 : sv === "tires" ? "Tires" : sv === "shocks" ? "Shocks" : sv === "driver" ? "Driver"
                 : sv === "engine-pull" ? "Engine" : sv === "delta-traces" ? "Traces" : sv === "evidence" ? "Evidence"
                 : "Insights"}
              </button>
            ))}
          </nav>
          <div className="compare-subview-container">
            {subviewContent}
          </div>
        </div>
      )}

      {!testRunId && (
        <div className="workspace-placeholder">
          <h3>Select a test run to compare</h3>
          <p>Compare against the baseline to see what changed and whether it worked.</p>
        </div>
      )}
    </section>
  );
}
