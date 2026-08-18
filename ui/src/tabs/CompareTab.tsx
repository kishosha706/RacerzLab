import { AlertTriangle, BarChart3, MapPin, ShoppingCart } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchCompareInsights, fetchComparePreview, runCompare } from "../api/client";
import { ComparisonInsightPanel } from "../components/ComparisonInsightPanel";
import { DeltaTracesView } from "../components/DeltaTracesView";
import { DidItWorkCard } from "../components/DidItWorkCard";
import { EngineeringAwarenessPanel } from "../components/EngineeringAwarenessPanel";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket, type BasketItem } from "../store/CompareBasketContext";
import type { RunListItem } from "../types/telemetry";
import type {
  ChannelDeltaStats, CompareResponse, ComparisonInsightsResponse, CornerName, CornerMetric,
  CornerMatrix,
  ComparisonObservation, ContextChange, DriverComparison, PaceComparison, PlatformComparison,
  PowertrainComparison, ShockComparison, SetupChange, TireComparison,
  TestDisciplineResult, WholeCarIndex,
} from "../types/compare";

type CompareTabProps = { runs: RunListItem[]; currentRunId: string; sessionId?: string | null };
type SubView =
  | "observation" | "what-changed" | "whole-car-index" | "target-zone"
  | "platform" | "four-corners" | "tires" | "shocks"
  | "driver" | "engine-pull" | "delta-traces" | "evidence" | "insights";
type SubViewGroup = "observation" | "platform" | "systems" | "detail";

const SUBVIEW_GROUPS: Record<SubViewGroup, SubView[]> = {
  observation: ["observation", "whole-car-index", "evidence"],
  platform: ["what-changed", "target-zone", "platform", "four-corners"],
  systems: ["tires", "shocks", "driver", "engine-pull"],
  detail: ["delta-traces", "insights"],
};

const SUBVIEW_LABELS: Record<SubView, string> = {
  observation: "Observation",
  "what-changed": "What Changed",
  "whole-car-index": "Index",
  "target-zone": "Target Zone",
  platform: "Platform",
  "four-corners": "4 Corners",
  tires: "Tires",
  shocks: "Shocks",
  driver: "Driver",
  "engine-pull": "Engine",
  "delta-traces": "Traces",
  evidence: "Evidence",
  insights: "Insights",
};

type PreviewData = {
  baseline_laps: number[]; test_laps: number[];
  suggested_baseline_lap: number | null; suggested_test_lap: number | null;
  setup_changes: SetupChange[]; context_changes: Array<{ key: string; label: string; warning: string | null; is_problem: boolean }>;
  warnings: string[];
};

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

function describeEvidenceScope(
  item: BasketItem | null,
): string {
  if (!item) return "Run-level";
  if (item.lap_scope === "lap_window" && item.lap_window_start != null && item.lap_window_end != null) {
    return `Window ${item.lap_window_start}-${item.lap_window_end}`;
  }
  if (item.lap_number != null) return `Lap ${item.lap_number}`;
  return "Run-level";
}

function describeValueBasisLabel(valueBasis: string | null | undefined): string | null {
  switch (valueBasis) {
    case "selected_window":
      return "Selected window";
    case "full_lap":
      return "Full lap";
    case "selected_sample":
      return "Selected sample";
    case "run_level":
      return "Run-level";
    default:
      return null;
  }
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

type OvalBriefTone = "good" | "watch" | "blocked" | "neutral";

type OvalBriefFact = {
  label: string;
  value: string;
  detail: string;
  tone: OvalBriefTone;
};

function paceBriefFact(pace: PaceComparison | null): OvalBriefFact {
  if (!pace || pace.direction === "insufficient_data" || pace.cohort_delta_s == null) {
    return {
      label: "Clean-lap pace",
      value: "No clean pace call",
      detail: "A qualified baseline and test cohort are required.",
      tone: "blocked",
    };
  }

  const magnitude = Math.abs(pace.cohort_delta_s).toFixed(3);
  const direction = pace.cohort_delta_s < 0 ? "faster" : pace.cohort_delta_s > 0 ? "slower" : "unchanged";
  const noise = pace.noise_band_s != null ? ` · noise band ${pace.noise_band_s.toFixed(3)}s` : "";
  if (pace.is_significant === true && direction !== "unchanged") {
    return {
      label: "Clean-lap pace",
      value: `${magnitude}s ${direction}`,
      detail: `${pace.baseline_eligible_laps} baseline vs ${pace.test_eligible_laps} test laps${noise}`,
      tone: direction === "faster" ? "good" : "watch",
    };
  }
  return {
    label: "Clean-lap pace",
    value: direction === "unchanged" ? "No measured change" : `${magnitude}s ${direction}, not clear`,
    detail: `The observed cohort change does not clear the empirical noise floor${noise}.`,
    tone: "neutral",
  };
}

function targetBriefFact(data: CompareResponse, friendlyLabel?: string | null): OvalBriefFact {
  const speed = data.target_zone?.channel_deltas.find((delta) => delta.channel === "speed_mph") ?? null;
  const scope = friendlyLabel ?? `${data.target_zone_start_pct.toFixed(1)}-${data.target_zone_end_pct.toFixed(1)}% lap`;
  if (speed?.delta == null) {
    return {
      label: "Where it changed",
      value: scope,
      detail: "Target-zone speed evidence is unavailable.",
      tone: "blocked",
    };
  }
  const sign = speed.delta > 0 ? "+" : "";
  return {
    label: "Where it changed",
    value: `${sign}${speed.delta.toFixed(2)} mph`,
    detail: `${scope} · observed speed, not a cause assignment`,
    tone: speed.delta > 0 ? "good" : speed.delta < 0 ? "watch" : "neutral",
  };
}

function driverBriefFact(driver: DriverComparison | null): OvalBriefFact {
  if (!driver) {
    return { label: "Driver match", value: "Unavailable", detail: "No input comparison was returned.", tone: "blocked" };
  }
  if (driver.driver_changed_warning) {
    return {
      label: "Driver match",
      value: "Inputs changed",
      detail: "Setup credit is limited until the driving trace is comparable.",
      tone: "watch",
    };
  }
  if (driver.repeatability_score != null) {
    return {
      label: "Driver match",
      value: `${driver.repeatability_score.toFixed(0)} repeatability`,
      detail: "Brake, throttle, and steering comparison is available.",
      tone: driver.repeatability_score >= 70 ? "good" : "neutral",
    };
  }
  return { label: "Driver match", value: "Not scored", detail: "No repeatability score is available.", tone: "neutral" };
}

function rightFrontBriefFact(tire: TireComparison | null): OvalBriefFact {
  if (!tire) {
    return { label: "Right-front watch", value: "Unavailable", detail: "No tire comparison was returned.", tone: "blocked" };
  }
  if (tire.short_run_warning) {
    return {
      label: "Right-front watch",
      value: "Long-run read withheld",
      detail: "The run is too short for a strong wear or falloff conclusion.",
      tone: "watch",
    };
  }
  const rightFront = tire.corners?.RF;
  const observed = rightFront?.tire_wear ?? rightFront?.temp_spread ?? rightFront?.tire_pressure_gain ?? rightFront?.tire_pressure;
  if (!observed || observed.delta_avg == null) {
    return {
      label: "Right-front watch",
      value: "No comparable trend",
      detail: "Pressure, temperature-spread, or wear evidence is incomplete.",
      tone: "neutral",
    };
  }
  return {
    label: "Right-front watch",
    value: formatDelta(observed),
    detail: `${observed.label} · observed comparison only`,
    tone: observed.direction === "better" ? "good" : observed.direction === "worse" ? "watch" : "neutral",
  };
}

function testDisciplineBriefFact(data: CompareResponse): OvalBriefFact {
  const changeCount = data.setup_changes.length;
  const score = data.test_discipline?.score;
  const scoreText = score != null ? ` · discipline ${score.toFixed(0)}` : "";
  if (changeCount > 1) {
    return {
      label: "Test discipline",
      value: `${changeCount} setup changes`,
      detail: `Causal credit is limited${scoreText}.`,
      tone: "watch",
    };
  }
  if (changeCount === 1) {
    return {
      label: "Test discipline",
      value: "One change recorded",
      detail: `${data.setup_changes[0]?.label ?? "Setup delta"}${scoreText}`,
      tone: "good",
    };
  }
  return {
    label: "Test discipline",
    value: "No setup delta",
    detail: `Use this as an observational or reference comparison${scoreText}.`,
    tone: "neutral",
  };
}

function OvalComparisonBrief({
  data,
  friendlyZoneLabel,
  learningMode,
  onOpen,
}: {
  data: CompareResponse;
  friendlyZoneLabel?: string | null;
  learningMode: boolean;
  onOpen: (view: SubView) => void;
}) {
  const facts = [
    paceBriefFact(data.pace_comparison),
    targetBriefFact(data, friendlyZoneLabel),
    driverBriefFact(data.driver_comparison),
    rightFrontBriefFact(data.tire_comparison),
    testDisciplineBriefFact(data),
  ];
  const pace = facts[0];
  const evidenceDebtGroups = [
    {
      label: "Context",
      items: data.context_changes
        .filter((item) => item.is_problem || item.warning)
        .map((item) => item.warning ?? `${item.label} differs.`),
    },
    {
      label: "Test discipline",
      items: data.test_discipline?.negative_factors ?? [],
    },
    {
      label: "Simulator integrity",
      items: data.sim_integrity?.warnings ?? [],
    },
    {
      label: "Eligibility / evidence",
      items: [
        ...(data.observation?.blocker_reasons ?? []),
        ...data.warnings,
      ],
    },
  ].map((group) => ({ ...group, items: [...new Set(group.items)] }))
    .filter((group) => group.items.length > 0);
  const evidenceDebtCount = evidenceDebtGroups.reduce(
    (total, group) => total + group.items.length,
    0,
  );
  return (
    <section
      className="oval-compare-brief"
      data-decision-state={pace.tone}
      data-authority="comparison-only"
      aria-labelledby="oval-compare-title"
    >
      <header className="oval-compare-header">
        <div>
          <span className="eyebrow">Oval comparison brief</span>
          <h3 id="oval-compare-title">{pace.value}</h3>
          <p>{data.observation?.headline ?? "Read the qualified observations before making the next change."}</p>
        </div>
        <span className="oval-compare-authority">Comparison only</span>
      </header>
      <div className="oval-compare-facts">
        {facts.map((fact) => (
          <article key={fact.label} className="oval-compare-fact" data-tone={fact.tone}>
            <span>{fact.label}</span>
            <strong>{fact.value}</strong>
            <small>{fact.detail}</small>
          </article>
        ))}
      </div>
      <details className="compare-evidence-debt" open={learningMode || undefined}>
        <summary>
          Evidence debt · {evidenceDebtCount === 0 ? "none recorded" : `${evidenceDebtCount} blocker${evidenceDebtCount === 1 ? "" : "s"}`}
        </summary>
        {evidenceDebtGroups.length > 0 ? evidenceDebtGroups.map((group) => (
          <section key={group.label}>
            <strong>{group.label}</strong>
            <ul>{group.items.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        )) : (
          <p>No recorded evidence debt in this response. This remains an observation, not a setup-policy certificate.</p>
        )}
      </details>
      <div className="oval-compare-actions" aria-label="Oval comparison details">
        <button type="button" onClick={() => onOpen("target-zone")}>Where</button>
        <button type="button" onClick={() => onOpen("driver")}>Driver</button>
        <button type="button" onClick={() => onOpen("tires")}>RF / tires</button>
        <button type="button" onClick={() => onOpen("what-changed")}>Setup delta</button>
      </div>
      {learningMode && (
        <p className="oval-compare-coaching">
          Start with cohort pace, then check where the observed difference began, whether the inputs matched, and whether the right-front trend stayed acceptable. This surface reports observations only; setup policy comes from the controlled workflow.
        </p>
      )}
    </section>
  );
}

function ObservationView({ observation, disc, wci, pace, confidence, targetSpeedDeltaMph, setupChanges, contextChanges, weatherWarning, isSelfCompare }: {
  observation: ComparisonObservation | null; disc: TestDisciplineResult | null;
  wci: WholeCarIndex | null; pace: PaceComparison | null; confidence: number;
  targetSpeedDeltaMph?: number | null;
  setupChanges: SetupChange[];
  contextChanges: ContextChange[];
  weatherWarning?: string | null;
  isSelfCompare?: boolean;
}) {
  if (!observation) return <p className="muted">No comparison observation available.</p>;

  return (
    <div className="compare-subview">
      <DidItWorkCard
        observation={observation.observation_state ?? "inconclusive"}
        headline={observation.headline}
        confidenceScore={confidence}
        testDisciplineScore={disc?.score}
        disciplineFactors={disc ? {
          positive: disc.positive_factors,
          negative: disc.negative_factors,
        } : null}
        evidence={observation.evidence}
        warnings={observation.warnings}
        weatherWarning={weatherWarning}
        wholeLapDeltaS={pace?.cohort_delta_s}
        paceNoiseBandS={pace?.noise_band_s}
        eligibleLapCounts={pace ? { baseline: pace.baseline_eligible_laps, test: pace.test_eligible_laps } : null}
        targetZoneDeltaMph={targetSpeedDeltaMph}
        setupChanges={setupChanges}
        contextWarnings={contextChanges
          .filter((change) => change.warning)
          .map((change) => ({ label: change.label, warning: change.warning as string }))}
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
        <div key={label} className="wci-item" data-severity={score == null ? "missing" : score >= 70 ? "safe" : score >= 45 ? "watch" : "high"}>
          <span className="wci-label">{label}</span>
          <span className="wci-score">{score != null ? score.toFixed(0) : "—"}</span>
          <span className="wci-mini-bar" aria-hidden="true">
            <span style={{ width: `${score != null ? Math.max(0, Math.min(100, score)) : 0}%` }} />
          </span>
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

  const setupValue = (value: unknown, unit: string | null): string => {
    if (value == null) return "—";
    const rendered = String(value);
    if (!unit || typeof value !== "number") return rendered;
    return unit === "%" || unit === ":1" ? `${rendered}${unit}` : `${rendered} ${unit}`;
  };

  const sizeLabel = (value: SetupChange["significance"]): string =>
    value === "unknown" ? "Unknown input size" : `Estimated ${value}`;

  if (setup.length === 0 && context.length === 0) return <p className="muted">No setup/context changes detected in this comparison.</p>;
  return (
    <div className="compare-subview">
      {Object.entries(grouped).length > 0 && Object.entries(grouped).map(([group, items]) => (
        <div key={group} className="setup-group">
          <h4>{group.replace(/_/g, " ")}</h4>
          <table className="compact-table">
            <thead><tr><th>Setting</th><th>Baseline</th><th>Test</th><th>Exact change</th><th>Estimated input size</th></tr></thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.setup_key} className={`significance-${s.significance}`}>
                  <td className="cell-label">{s.label}</td>
                  <td className="cell-val">{setupValue(s.baseline_value, s.unit)}</td>
                  <td className="cell-val">{setupValue(s.test_value, s.unit)}</td>
                  <td className="cell-delta">{s.delta ?? "—"}</td>
                  <td className="cell-dir" title={s.magnitude_basis ?? undefined}>{sizeLabel(s.significance)}</td>
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

function TargetZoneView({ data: r, friendlyLabel, onOpenDeltaTraces }: { data: CompareResponse; friendlyLabel?: string | null; onOpenDeltaTraces?: () => void }) {
  const speed = r.target_zone?.channel_deltas.find((delta) => delta.channel === "speed_mph") ?? null;
  return (
    <div className="compare-subview">
      <h3>{friendlyLabel ?? `Target Zone ${r.target_zone_start_pct}–${r.target_zone_end_pct}%`}</h3>
      {friendlyLabel && <p className="section-note">Range {r.target_zone_start_pct}–{r.target_zone_end_pct}%</p>}
      {speed && (
        <div className="overview-trust-summary">
          <span>Baseline {formatVal(speed.baseline_avg, 2)} mph</span>
          <span>Test {formatVal(speed.test_avg, 2)} mph</span>
          <span>Delta {speed.delta != null ? `${speed.delta > 0 ? "+" : ""}${speed.delta.toFixed(2)} mph` : "—"}</span>
          <span>{r.target_zone?.speed_gain_or_loss_label ?? "unavailable"}</span>
        </div>
      )}
      {r.observation && <p><strong>{r.observation.headline}</strong></p>}
      {r.platform && (
        <table className="compact-table">
          <thead><tr><th>Metric</th><th>Direction</th></tr></thead>
          <tbody>
            {deltaRow("CFS Height", r.platform.cfs_height, "in")}
            {deltaRow("Center Rake FS", r.platform.center_rake_fs, "in")}
            {deltaRow("Side Rake", r.platform.side_rake, "in")}
            {deltaRow("Ground-Speed Pressure Proxy", r.platform.dynamic_pressure, "psf")}
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
          {deltaRow("Ground-Speed Pressure Proxy", platform.dynamic_pressure, "psf")}
          {deltaRow("CFS Risk Score", platform.cfs_risk_score, "score")}
        </tbody>
      </table>
      <p className="platform-observation">Platform Observation: {platform.platform_verdict ?? "—"}</p>
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
      <p>Driver Observation: {driver.driver_verdict ?? "—"}</p>
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
      {pt.powertrain_verdict && <p>Observation: {pt.powertrain_verdict}</p>}
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
      {tire.tire_verdict && <p>Tire Observation: {tire.tire_verdict}</p>}
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
      {shock.shock_verdict && <p>Shock Observation: {shock.shock_verdict}</p>}
    </div>
  );
}

function EvidenceView({ observation }: { observation: ComparisonObservation | null }) {
  if (!observation) return <p className="muted">No evidence available.</p>;
  return (
    <div className="compare-subview">
      {observation.evidence.length > 0 && (
        <><h4>Evidence</h4>{observation.evidence.map((e, i) => <p key={i} className="observation-evidence">• {e}</p>)}</>
      )}
      {observation.warnings.length > 0 && (
        <><h4>Warnings</h4>{observation.warnings.map((w, i) => <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>)}</>
      )}
    </div>
  );
}

// ── Main Tab ────────────────────────────────────────────────

export function CompareTab({ runs, currentRunId, sessionId = null }: CompareTabProps) {
  const { basket } = useCompareBasket();
  const [baselineRunId, setBaselineRunId] = useState(currentRunId);
  const [testRunId, setTestRunId] = useState("");
  // Determine if Compare is using basket-driven or manual selections
  const basketBaselineRunId = basket.baseline?.run_id;
  const basketTestRunId = basket.test?.run_id;
  const isBasketDriven = basketBaselineRunId != null
    && baselineRunId === basketBaselineRunId
    && testRunId === basketTestRunId
    && testRunId !== "";
  const [startPct, setStartPct] = useState(55);
  const [endPct, setEndPct] = useState(70);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [subview, setSubview] = useState<SubView>("observation");
  const [loading, setLoading] = useState(false);
  const { selection } = useTelemetrySelection();
  const [error, setError] = useState<string | null>(null);
  const [insights, setInsights] = useState<ComparisonInsightsResponse | null>(null);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [insightsError, setInsightsError] = useState<string | null>(null);
  const [insightsScopeKey, setInsightsScopeKey] = useState<string | null>(null);
  const [activeZoneLabel, setActiveZoneLabel] = useState<string | null>(null);
  const lastSyncedZoneKeyRef = useRef<string | null>(null);
  const comparisonRequestSequenceRef = useRef(0);
  const comparisonAbortRef = useRef<AbortController | null>(null);
  const insightsRequestSequenceRef = useRef(0);
  const basketBaselineLap = basket.baseline?.representative_lap ?? basket.baseline?.lap_number ?? null;
  const basketTestLap = basket.test?.representative_lap ?? basket.test?.lap_number ?? null;
  const effectiveBaselineLap = isBasketDriven ? basketBaselineLap : preview?.suggested_baseline_lap ?? null;
  const effectiveTestLap = isBasketDriven ? basketTestLap : preview?.suggested_test_lap ?? null;
  const compareModeLabel = isBasketDriven ? "Basket-driven" : "Manual / detached";
  const compareScopeNote = basket.baseline?.lap_scope === "lap_window" || basket.test?.lap_scope === "lap_window"
    ? "Compare currently uses representative laps and run-level compare math; window metadata is preserved for context."
    : "Compare currently uses lap or run identity without window metadata.";
  const [subviewGroup, setSubviewGroup] = useState<SubViewGroup>("observation");

  const otherRuns = runs.filter((r) => r.run_id !== baselineRunId);
  const isSameRun = testRunId === baselineRunId && testRunId !== "";
  const baselineRecordingSha = runs.find((run) => run.run_id === baselineRunId)?.recording_sha256 ?? null;
  const testRecordingSha = runs.find((run) => run.run_id === testRunId)?.recording_sha256 ?? null;
  const isSameRecording = baselineRecordingSha != null
    && testRecordingSha != null
    && baselineRecordingSha === testRecordingSha;
  const compareDisabledReason = !testRunId
    ? "Select a test run to enable Compare."
    : isSameRun || isSameRecording
      ? "SAME RECORDING — these entries reference identical telemetry and cannot be compared as independent runs."
      : null;
  const showBasketSyncHint = !isBasketDriven && basketBaselineRunId != null && basketTestRunId != null;
  const selectedZoneReady = selection.selectedRunId === baselineRunId
    && selection.selectedZoneStartPct != null
    && selection.selectedZoneEndPct != null;
  const selectedZoneRangeLabel = selectedZoneReady
    ? selection.selectedZoneLabel ?? `Zone ${selection.selectedZoneStartPct?.toFixed(1)}-${selection.selectedZoneEndPct?.toFixed(1)}%`
    : null;
  const comparisonScopeKey = JSON.stringify({
    baselineRunId,
    testRunId,
    baselineLap: effectiveBaselineLap,
    testLap: effectiveTestLap,
    startPct,
    endPct,
  });
  const insightsStateOwnsScope = insightsScopeKey === comparisonScopeKey;
  const scopedInsights = insightsStateOwnsScope ? insights : null;
  const scopedInsightsLoading = insightsStateOwnsScope && insightsLoading;
  const scopedInsightsError = insightsStateOwnsScope ? insightsError : null;

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
          <p>Bank one more comparable run.</p>
          <p className="muted">Interpret differences only when car, track, fuel, tire age, weather, line, and recorded setup context are comparable.</p>
        </div>
      </section>
    );
  }

  useEffect(() => {
    comparisonAbortRef.current?.abort();
    comparisonRequestSequenceRef.current += 1;
    insightsRequestSequenceRef.current += 1;
    setResult(null);
    setInsights(null);
    setInsightsLoading(false);
    setInsightsError(null);
    setInsightsScopeKey(null);
    setLoading(false);
    setError(null);
  }, [comparisonScopeKey]);

  useEffect(() => {
    if (!testRunId || testRunId === baselineRunId || isSameRecording) return;
    const controller = new AbortController();
    setPreviewLoading(true);
    fetchComparePreview(baselineRunId, testRunId, controller.signal)
      .then(p => { if (!controller.signal.aborted) { setPreview(p); setPreviewLoading(false); } })
      .catch(() => { if (!controller.signal.aborted) { setPreview(null); setPreviewLoading(false); } });
    return () => { controller.abort(); };
  }, [baselineRunId, isSameRecording, testRunId]);

  useEffect(() => {
    if (!selectedZoneReady) {
      if (selection.selectedRunId !== baselineRunId) {
        setActiveZoneLabel(null);
      }
      return;
    }
    const nextKey = [
      baselineRunId,
      selection.selectedZoneId ?? "",
      selection.selectedZoneStartPct,
      selection.selectedZoneEndPct,
      selection.selectedZoneLabel ?? "",
    ].join("|");
    if (lastSyncedZoneKeyRef.current === nextKey) return;
    lastSyncedZoneKeyRef.current = nextKey;
    setStartPct(selection.selectedZoneStartPct ?? 0);
    setEndPct(selection.selectedZoneEndPct ?? 100);
    setActiveZoneLabel(selection.selectedZoneLabel ?? null);
    setResult(null);
  }, [
    baselineRunId,
    selectedZoneReady,
    selection.selectedRunId,
    selection.selectedZoneEndPct,
    selection.selectedZoneId,
    selection.selectedZoneLabel,
    selection.selectedZoneStartPct,
  ]);

  const handleCompare = useCallback(async () => {
    if (!testRunId || isSameRecording) return;
    const request = {
      baseline_run_id: baselineRunId,
      test_run_id: testRunId,
      baseline_lap: effectiveBaselineLap,
      test_lap: effectiveTestLap,
      target_zone_start_pct: startPct,
      target_zone_end_pct: endPct,
    };
    const sequence = ++comparisonRequestSequenceRef.current;
    comparisonAbortRef.current?.abort();
    const controller = new AbortController();
    comparisonAbortRef.current = controller;
    setLoading(true);
    setError(null);
    setResult(null);
    setInsights(null);
    try {
      const res = await runCompare(request, controller.signal);
      if (sequence !== comparisonRequestSequenceRef.current) return;
      const responseMatchesRequest = res.baseline_run_id === request.baseline_run_id
        && res.test_run_id === request.test_run_id
        && (request.baseline_lap == null || res.baseline_lap === request.baseline_lap)
        && (request.test_lap == null || res.test_lap === request.test_lap)
        && Math.abs(res.target_zone_start_pct - request.target_zone_start_pct) <= 0.001
        && Math.abs(res.target_zone_end_pct - request.target_zone_end_pct) <= 0.001;
      if (!responseMatchesRequest) {
        setError("Comparison scope error: the result did not match the selected runs, laps, and target zone.");
        return;
      }
      setResult(res);
      setSubview("observation");
    } catch (e) {
      if (sequence !== comparisonRequestSequenceRef.current) return;
      setError(e instanceof Error ? e.message : "Comparison failed");
    } finally {
      if (sequence === comparisonRequestSequenceRef.current) setLoading(false);
    }
  }, [baselineRunId, effectiveBaselineLap, effectiveTestLap, isSameRecording, testRunId, startPct, endPct]);

  // ── load insights when comparison exists ────────────────────
  useEffect(() => {
    if (!result) {
      insightsRequestSequenceRef.current += 1;
      setInsights(null);
      setInsightsLoading(false);
      setInsightsError(null);
      setInsightsScopeKey(null);
      return;
    }

    const resultMatchesCurrentScope = result.baseline_run_id === baselineRunId
      && result.test_run_id === testRunId
      && (effectiveBaselineLap == null || result.baseline_lap === effectiveBaselineLap)
      && (effectiveTestLap == null || result.test_lap === effectiveTestLap)
      && Math.abs(result.target_zone_start_pct - startPct) <= 0.001
      && Math.abs(result.target_zone_end_pct - endPct) <= 0.001;
    if (!resultMatchesCurrentScope) {
      insightsRequestSequenceRef.current += 1;
      setInsights(null);
      setInsightsLoading(false);
      setInsightsError(null);
      setInsightsScopeKey(null);
      return;
    }

    const request = {
      baseline_run_id: result.baseline_run_id,
      test_run_id: result.test_run_id,
      baseline_lap: result.baseline_lap,
      test_lap: result.test_lap,
      target_zone_start_pct: result.target_zone_start_pct,
      target_zone_end_pct: result.target_zone_end_pct,
    };
    const requestScopeKey = comparisonScopeKey;
    const sequence = ++insightsRequestSequenceRef.current;
    let cancelled = false;
    const isLatestInsightsRequest = () => !cancelled
      && sequence === insightsRequestSequenceRef.current;

    setInsights(null);
    setInsightsLoading(true);
    setInsightsError(null);
    setInsightsScopeKey(requestScopeKey);
    fetchCompareInsights(request).then((nextData) => {
      if (!isLatestInsightsRequest()) return;
      const responseMatchesRequest = nextData.baseline_run_id === request.baseline_run_id
        && nextData.test_run_id === request.test_run_id
        && nextData.baseline_lap === request.baseline_lap
        && nextData.test_lap === request.test_lap
        && Math.abs(nextData.target_zone_start_pct - request.target_zone_start_pct) <= 0.001
        && Math.abs(nextData.target_zone_end_pct - request.target_zone_end_pct) <= 0.001;
      if (!responseMatchesRequest) {
        setInsights(null);
        setInsightsError("Comparison insights scope error: the response did not match the selected runs, laps, and target zone. No insight observation is shown.");
        setInsightsLoading(false);
        return;
      }
      setInsights(nextData);
      setInsightsError(null);
      setInsightsLoading(false);
    }).catch((caught: unknown) => {
      if (!isLatestInsightsRequest()) return;
      setInsights(null);
      setInsightsError(caught instanceof Error
        ? `Comparison insights unavailable: ${caught.message}`
        : "Comparison insights unavailable.");
      setInsightsLoading(false);
    });
    return () => { cancelled = true; };
  }, [
    result,
    comparisonScopeKey,
    baselineRunId,
    testRunId,
    effectiveBaselineLap,
    effectiveTestLap,
    startPct,
    endPct,
  ]);

  const subviewContent = useMemo(() => {
    if (!result) return null;
    switch (subview) {
      case "observation": return (
        <div className="compare-subview">
          {isSelfCompare && (
            <div className="self-compare-banner">
              <span className="self-compare-badge">Reference Mode</span>
              <p className="self-compare-text">Baseline and test are the same run/lap, so no setup decision should be made from this comparison.</p>
            </div>
          )}
          <ObservationView
            observation={result.observation} disc={result.test_discipline}
            wci={result.whole_car_index} confidence={result.confidence_score}
            pace={result.pace_comparison}
            targetSpeedDeltaMph={result.target_zone?.channel_deltas.find((delta) => delta.channel === "speed_mph")?.delta}
            setupChanges={result.setup_changes}
            contextChanges={result.context_changes}
            weatherWarning={preview?.context_changes?.find(c => c.key === "weather")?.warning ?? null}
            isSelfCompare={isSelfCompare}
          />
        </div>
      );
      case "what-changed": return <WhatChangedView setup={result.setup_changes} context={result.context_changes} />;
      case "whole-car-index": return <WholeCarIndexView wci={result.whole_car_index} />;
      case "target-zone": return <TargetZoneView data={result} friendlyLabel={activeZoneLabel} onOpenDeltaTraces={() => setSubview("delta-traces")} />;
      case "platform": return <PlatformView platform={result.platform} onOpenDeltaTraces={() => setSubview("delta-traces")} />;
      case "four-corners": return <FourCornersView cm={result.corner_matrix} onOpenDeltaTraces={() => setSubview("delta-traces")} />;
      case "tires": return <TiresView tire={result.tire_comparison} />;
      case "shocks": return <ShocksView shock={result.shock_comparison} />;
      case "driver": return <DriverView driver={result.driver_comparison} />;
      case "engine-pull": return <EngineView pt={result.powertrain_comparison} />;
      case "delta-traces": return <DeltaTracesView baselineRunId={baselineRunId} testRunId={testRunId} startPct={startPct} endPct={endPct} result={result} />;
      case "evidence": return <EvidenceView observation={result.observation} />;
      case "insights": {
        if (scopedInsightsLoading) return <p className="muted">Loading insights…</p>;
        if (scopedInsightsError) return <p className="error-text" role="alert">{scopedInsightsError}</p>;
        if (!scopedInsights) return <p className="muted">Insights not available.</p>;
        return (
          <div>
            {isSelfCompare && (
              <div className="self-compare-banner">
                <span className="self-compare-badge">Reference Mode</span>
                <p className="self-compare-text">Baseline and test are the same run/lap, so no setup decision should be made from this comparison.</p>
              </div>
            )}
            <ComparisonInsightPanel insights={scopedInsights} onOpenDeltaTraces={() => setSubview("delta-traces")} />
          </div>
        );
      }
      default: return null;
    }
  }, [result, subview, scopedInsights, scopedInsightsError, scopedInsightsLoading]);

  useEffect(() => {
    if (SUBVIEW_GROUPS[subviewGroup].includes(subview)) return;
    const nextGroup = (Object.entries(SUBVIEW_GROUPS) as Array<[SubViewGroup, SubView[]]>)
      .find(([, views]) => views.includes(subview))?.[0] ?? "observation";
    setSubviewGroup(nextGroup);
  }, [subview, subviewGroup]);

  return (
    <section className="compare-workspace">
      <EngineeringAwarenessPanel runId={currentRunId} sessionId={sessionId} surface="compare" />
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
            {otherRuns.map((run) => {
              const sameRecording = baselineRecordingSha != null
                && run.recording_sha256 != null
                && run.recording_sha256 === baselineRecordingSha;
              return (
                <option key={run.run_id} value={run.run_id} disabled={sameRecording}>
                  {run.track_name ?? run.run_id.slice(0, 24)}{sameRecording ? " — SAME RECORDING" : ""}
                </option>
              );
            })}
          </select>
        </div>
        <div className="selector-group">
          <label>Target Zone</label>
          <div className="zone-inputs">
            <input type="number" value={startPct} onChange={e => { setStartPct(Number(e.target.value)); setActiveZoneLabel(null); setResult(null); }} min={0} max={100} />%
            <span>–</span>
            <input type="number" value={endPct} onChange={e => { setEndPct(Number(e.target.value)); setActiveZoneLabel(null); setResult(null); }} min={0} max={100} />%
          </div>
        </div>
        <button
          className="primary-button"
          onClick={handleCompare}
          disabled={!testRunId || loading || isSameRun || isSameRecording}
          title={compareDisabledReason ?? "Run baseline vs test comparison"}
        >
          {loading ? "Comparing..." : isSameRun || isSameRecording ? "Same recording" : "Compare"}
        </button>
      </div>

      <div className="compare-readiness-strip" aria-live="polite">
        {compareDisabledReason ? (
          <p className="compare-readiness-item warn">
            <AlertTriangle size={12} />
            {compareDisabledReason}
          </p>
        ) : (
          <p className="compare-readiness-item ready">Compare is ready. Observation opens first.</p>
        )}
        {showBasketSyncHint && (
          <p className="compare-readiness-item info">
            Compare Basket has a staged pair. Use "Sync from Basket" to align selectors instantly.
          </p>
        )}
      </div>

      {(activeZoneLabel || selectedZoneRangeLabel) && (
        <div className="compare-basket-status" style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
          <span className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>
            <MapPin size={10} style={{ marginRight: 4 }} />
            {activeZoneLabel ?? selectedZoneRangeLabel}
          </span>
          {selectedZoneReady && (
            <span className="section-note" style={{ margin: 0 }}>
              Compare target zone synced from the current spatial selection.
            </span>
          )}
        </div>
      )}

      <div className="laps-chip-row" style={{ marginBottom: 8 }}>
        <span className="lap-flag-badge">Baseline Lap {effectiveBaselineLap ?? "auto"}</span>
        <span className="lap-flag-badge">Test Lap {effectiveTestLap ?? "auto"}</span>
      </div>

      {error && (
        <div className="warning-banner compare-error-recovery" role="alert">
          <AlertTriangle size={14} />
          <span><strong>Comparison unavailable.</strong> {error} No comparison metrics are shown.</span>
        </div>
      )}

      {/* Compare Basket status */}
      <div className="compare-basket-status" style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4 }}>
        <span className="lap-flag-badge" style={{
          background: isBasketDriven ? "rgba(34,197,94,0.12)" : "rgba(245,158,11,0.12)",
          color: isBasketDriven ? "#22c55e" : "#f59e0b",
          fontSize: 10, padding: "2px 8px",
        }}>
          <ShoppingCart size={10} style={{ marginRight: 4 }} />
          {compareModeLabel}
        </span>
        {!isBasketDriven && basketBaselineRunId && basketTestRunId && (
          <button
            className="trackmap-action-btn"
            onClick={() => {
              setBaselineRunId(basketBaselineRunId);
              setTestRunId(basketTestRunId);
              setResult(null);
            }}
            title="Sync runs from Compare Basket"
          >
            <ShoppingCart size={10} /> Sync from Basket
          </button>
        )}
        {(basket.baseline?.lap_scope === "lap_window" || basket.test?.lap_scope === "lap_window") && (
          <span className="lap-flag-badge" style={{ background: "rgba(56,189,248,0.12)", color: "#38bdf8", fontSize: 10, padding: "2px 8px" }}>
            Window metadata preserved
          </span>
        )}
      </div>

      {(basket.baseline || basket.test) && (
        <div className="laps-window-grid" style={{ marginBottom: 10 }}>
          {([
            ["Baseline", basket.baseline, effectiveBaselineLap],
            ["Test", basket.test, effectiveTestLap],
          ] as const).map(([role, item, effectiveLap]) => (
            <article key={role} className="laps-window-card">
              <span className="eyebrow">{role}</span>
              <h3 style={{ margin: 0 }}>{item?.label ?? "Empty"}</h3>
              {item ? (
                <>
                  <div className="laps-chip-row">
                    <span className="lap-flag-badge">{describeEvidenceScope(item)}</span>
                    {item.trust_tier && <span className="lap-flag-badge">Trust {item.trust_tier}</span>}
                    {describeValueBasisLabel(item.value_basis) && <span className="lap-flag-badge">{describeValueBasisLabel(item.value_basis)}</span>}
                    {item.representative_lap != null && <span className="lap-flag-badge">Rep Lap {item.representative_lap}</span>}
                    {item.engineering_value != null && <span className="lap-flag-badge">EV {item.engineering_value.toFixed(0)}</span>}
                  </div>
                  <p className="section-note" style={{ marginBottom: 0 }}>
                    {item.car ?? "-"} · {item.track ?? "-"} · Compare will use {effectiveLap != null ? `Lap ${effectiveLap}` : "run-level identity"} for this side.
                  </p>
                </>
              ) : (
                <p className="muted" style={{ marginBottom: 0 }}>Stage {role.toLowerCase()} evidence from Laps or use manual run selectors below.</p>
              )}
            </article>
          ))}
        </div>
      )}

      <p className="section-note" style={{ marginTop: 0 }}>
        {compareScopeNote}
      </p>

      {/* preview loading */}
      {previewLoading && <div className="compare-preview-loading"><span className="loading-spinner" /> Loading preview…</div>}

      {/* workbook */}
      {result && (
        <div className="compare-workbook">
          <OvalComparisonBrief
            data={result}
            friendlyZoneLabel={activeZoneLabel}
            learningMode={selection.selectedMode === "learning"}
            onOpen={setSubview}
          />
          <p className="section-note compare-group-explainer" style={{ marginTop: 0, marginBottom: 8 }}>
            Grouped navigation: start with Observation, then drill into Platform, Systems, and Detail.
          </p>
          <nav className="compare-group-nav" aria-label="Compare subview groups">
            {(["observation", "platform", "systems", "detail"] as SubViewGroup[]).map((group) => (
              <button
                key={group}
                className={`subnav-item ${subviewGroup === group ? "active" : ""}`}
                aria-current={subviewGroup === group ? "page" : undefined}
                onClick={() => {
                  setSubviewGroup(group);
                  if (!SUBVIEW_GROUPS[group].includes(subview)) {
                    setSubview(SUBVIEW_GROUPS[group][0]);
                  }
                }}
              >
                {group === "observation" ? "Observation" : group === "platform" ? "Platform" : group === "systems" ? "Systems" : "Detail"}
              </button>
            ))}
          </nav>
          <nav className="compare-subnav" aria-label="Compare subviews">
            {SUBVIEW_GROUPS[subviewGroup].map((sv) => (
              <button key={sv} className={`subnav-item ${subview === sv ? "active" : ""}`} onClick={() => setSubview(sv)} aria-current={subview === sv ? "page" : undefined}>
                {SUBVIEW_LABELS[sv]}
              </button>
            ))}
          </nav>
          <div className="compare-subview-container">
            {subviewContent}
          </div>
        </div>
      )}

      {!testRunId && (
        <div className="workspace-placeholder oval-compare-empty">
          <span className="eyebrow">Build a trustworthy oval comparison</span>
          <h3>Select the test run</h3>
          <div className="oval-compare-empty-steps">
            <span><strong>1</strong> Bank a clean baseline</span>
            <span><strong>2</strong> Match fuel, tires, weather, and line</span>
            <span><strong>3</strong> Test one setup change</span>
          </div>
          <p>The brief will lead with race pace, location, driver match, right-front trend, and test discipline.</p>
        </div>
      )}
    </section>
  );
}
