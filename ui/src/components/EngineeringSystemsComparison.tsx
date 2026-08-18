import { AlertTriangle, CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchEngineeringSystems } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type {
  EngineeringConclusion,
  EngineeringGate,
  EngineeringSystemsResponse,
} from "../types/compare";
import { evidenceStrengthOutOf100 } from "../utils/evidenceScore";

type Props = {
  baselineRunId: string;
  testRunId: string;
  baselineLap: number | null;
  testLap: number | null;
};

type EngineeringSystemsRequestState = {
  requestKey: string | null;
  data: EngineeringSystemsResponse | null;
  loading: boolean;
  error: string | null;
};

type RequestIdentity = {
  requestKey: string;
  sequence: number;
};

function label(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function value(valueToFormat: number | null | undefined, digits = 2, suffix = ""): string {
  return valueToFormat == null || !Number.isFinite(valueToFormat)
    ? "Unavailable"
    : `${valueToFormat.toFixed(digits)}${suffix}`;
}

function signed(valueToFormat: number | null | undefined, digits = 3, suffix = ""): string {
  if (valueToFormat == null || !Number.isFinite(valueToFormat)) return "Unavailable";
  return `${valueToFormat > 0 ? "+" : ""}${valueToFormat.toFixed(digits)}${suffix}`;
}

function gateTone(gate: EngineeringGate): "high" | "medium" | "low" {
  if (!gate.eligible) return "low";
  return gate.confidence_cap >= 0.75 ? "high" : gate.confidence_cap >= 0.55 ? "medium" : "low";
}

function ConclusionDetails({ conclusion }: { conclusion: EngineeringConclusion }) {
  return (
    <div className="panel" style={{ marginTop: 8 }}>
      <div className="section-header-row">
        <strong>{label(conclusion.key)}</strong>
        <span className={`confidence-badge ${conclusion.confidence_score >= 0.75 ? "high" : conclusion.confidence_score >= 0.55 ? "medium" : "low"}`}>
          {label(conclusion.evidence_state)} · strength {evidenceStrengthOutOf100(conclusion.confidence_score)}
        </span>
      </div>
      <p className="section-note">{conclusion.summary}</p>
      {conclusion.supporting_evidence.map((item) => <p className="section-note" key={item}>Evidence: {item}</p>)}
      {conclusion.contradicting_evidence.map((item) => <p className="section-note" key={item}>Counter-evidence: {item}</p>)}
      {conclusion.blocker_reasons.map((item) => <p className="section-note" key={item}>Blocked: {item}</p>)}
      {conclusion.source_channels.length > 0 && (
        <p className="section-note" title={conclusion.source_channels.join(", ")}>
          Sources: {conclusion.source_channels.join(", ")}
        </p>
      )}
    </div>
  );
}

export function EngineeringSystemsComparison({ baselineRunId, testRunId, baselineLap, testLap }: Props) {
  const { selection } = useTelemetrySelection();
  const learning = selection.selectedMode === "learning";
  const request = useMemo(() => baselineLap == null || testLap == null ? null : ({
    baseline_run_id: baselineRunId,
    test_run_id: testRunId,
    baseline_lap: baselineLap,
    test_lap: testLap,
    step_pct: 0.2,
  }), [baselineLap, baselineRunId, testLap, testRunId]);
  const requestKey = useMemo(() => request == null ? null : JSON.stringify(request), [request]);
  const requestSequenceRef = useRef(0);
  const latestRequestRef = useRef<RequestIdentity | null>(null);
  const [requestState, setRequestState] = useState<EngineeringSystemsRequestState>({
    requestKey: null,
    data: null,
    loading: false,
    error: null,
  });
  const stateOwnsRequest = requestState.requestKey === requestKey;
  const data = stateOwnsRequest ? requestState.data : null;
  const loading = requestKey != null && (!stateOwnsRequest || requestState.loading);
  const error = stateOwnsRequest ? requestState.error : null;

  const load = useCallback(async () => {
    if (request == null || requestKey == null) {
      latestRequestRef.current = null;
      setRequestState({ requestKey: null, data: null, loading: false, error: null });
      return;
    }
    const requestIdentity = {
      requestKey,
      sequence: ++requestSequenceRef.current,
    };
    latestRequestRef.current = requestIdentity;
    setRequestState({ requestKey, data: null, loading: true, error: null });
    const isLatestRequest = () => {
      const latestRequest = latestRequestRef.current;
      return latestRequest?.requestKey === requestIdentity.requestKey
        && latestRequest.sequence === requestIdentity.sequence;
    };
    try {
      const nextData = await fetchEngineeringSystems(request);
      if (!isLatestRequest()) return;
      const responseMatchesRequest = nextData.baseline_run_id === request.baseline_run_id
        && nextData.test_run_id === request.test_run_id
        && nextData.baseline_lap === request.baseline_lap
        && nextData.test_lap === request.test_lap;
      if (!responseMatchesRequest) {
        setRequestState({
          requestKey,
          data: null,
          loading: false,
          error: "Engineering comparison scope error: the response did not match the selected runs and laps.",
        });
        return;
      }
      setRequestState({ requestKey, data: nextData, loading: false, error: null });
    } catch (caught) {
      if (!isLatestRequest()) return;
      setRequestState({
        requestKey,
        data: null,
        loading: false,
        error: caught instanceof Error ? caught.message : "Engineering evidence unavailable",
      });
    }
  }, [request, requestKey]);

  useEffect(() => {
    void load();
    return () => {
      if (latestRequestRef.current?.requestKey === requestKey) latestRequestRef.current = null;
    };
  }, [load, requestKey]);

  const decision = useMemo(() => {
    if (!data) return null;
    const driver = data.driver_line;
    const rotation = data.corner_rotation;
    const platform = data.aero_platform;
    const delta = platform.comparison_metrics.delta ?? {};
    const tradeoff = typeof delta.time_platform_tradeoff === "string"
      ? label(delta.time_platform_tradeoff)
      : "No Clear Platform Tradeoff";
    return {
      driverHeadline: !driver.gate.eligible
        ? "Driver read blocked"
        : driver.driver_execution_changed === true
          ? "Repeat with matched driving"
          : driver.driver_execution_changed === false
            ? "Driving matched"
            : "Driver match unavailable",
      driverDetail: !driver.gate.eligible
        ? driver.gate.blocker_reasons[0] ?? "Required driver or racing-line evidence is unavailable."
        : driver.driver_execution_changed === true
        ? "Setup attribution is blocked until the driving is repeated."
        : driver.driver_execution_changed === false
          ? `${value(driver.line_deviation_median_m, 2, " m")} median line deviation`
          : "Paired driver-input or racing-line coverage is incomplete; setup attribution is blocked.",
      rotationHeadline: !rotation.gate.eligible
        ? "Rotation read blocked"
        : rotation.conclusions.some((item) => item.evidence_state === "blocked_by_context")
          ? "Rotation attribution blocked"
          : `${rotation.phase_metrics.length} sustained phases compared`,
      rotationDetail: rotation.gate.eligible
        ? "Expected yaw and response are compared by phase."
        : rotation.gate.blocker_reasons[0] ?? "Required evidence is unavailable.",
      platformHeadline: !platform.gate.eligible
        ? "Platform read blocked"
        : !platform.setup_attribution_allowed
          ? "Platform observation only"
          : tradeoff,
      platformDetail: platform.gate.eligible && !platform.setup_attribution_allowed
        ? "Driver pairing blocks setup credit."
        : platform.gate.eligible
        ? `Clearance P05 ${signed(typeof delta.cfs_p05_in_delta === "number" ? delta.cfs_p05_in_delta : null, 3, " in")}`
        : platform.gate.blocker_reasons[0] ?? "Required evidence is unavailable.",
    };
  }, [data]);

  if (loading && !data) return <div className="analysis-state" role="status" aria-live="polite">Checking whether this pair can support a setup decision…</div>;
  if (error) return (
    <div className="warning-banner" role="alert">
      <AlertTriangle size={16} />
      <span>{error}</span>
      <button type="button" className="secondary-button" onClick={() => void load()}><RefreshCw size={14} /> Retry</button>
    </div>
  );
  if (!data || !decision) return null;

  const integrityTone = data.sim_integrity_clear === false
    ? "low"
    : data.sim_integrity_clear === true
      && data.sim_integrity_confidence_cap >= 0.75
      && data.baseline_sim_integrity_status === "pass"
      && data.test_sim_integrity_status === "pass"
      ? "high"
      : "medium";
  const integrityLabel = data.sim_integrity_clear === false
    ? "Blocked"
    : data.sim_integrity_clear == null
      ? "Unknown"
      : integrityTone === "high"
        ? "Clear"
        : "Limited";
  const systems = [
    { title: "Driver + Line", report: data.driver_line, headline: decision.driverHeadline, detail: decision.driverDetail },
    { title: "Corner Rotation", report: data.corner_rotation, headline: decision.rotationHeadline, detail: decision.rotationDetail },
    { title: "Platform Window", report: data.aero_platform, headline: decision.platformHeadline, detail: decision.platformDetail },
  ];

  return (
    <section className="panel" aria-label="Engineering decision layer" data-analysis-surface="engineering_metrics" style={{ marginBottom: 16 }}>
      <div className="section-header-row">
        <div>
          <h3><ShieldCheck size={16} /> Engineering Decision Layer</h3>
          <p className="section-note">
            {learning
              ? "Contract-gated evidence at matched track positions. Proxy conclusions stay explicitly separate from measured and calculated values."
              : "Can this comparison support a setup decision?"}
          </p>
        </div>
        <span className={`confidence-badge ${integrityTone}`} title={`Baseline ${label(data.baseline_sim_integrity_status)}; test ${label(data.test_sim_integrity_status)}`}>
          {integrityTone === "high" ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
          Integrity {integrityLabel}
        </span>
      </div>

      <div className="metric-grid" style={{ marginBottom: 10 }}>
        {systems.map(({ title, report, headline, detail }) => (
          <div className="metric-card" key={title}>
            <span>{title}</span>
            <strong>{headline}</strong>
            <small className="muted">{detail}</small>
            <span className={`confidence-badge ${gateTone(report.gate)}`} style={{ marginTop: 8 }}>
              {report.gate.eligible ? "Eligible" : "Blocked"} · evidence cap {evidenceStrengthOutOf100(report.gate.confidence_cap)}
            </span>
          </div>
        ))}
      </div>

      {data.warnings.slice(0, learning ? data.warnings.length : 2).map((warning) => (
        <div className="section-note analysis-warning" role="status" key={warning}><AlertTriangle size={13} /> {warning}</div>
      ))}
      {!learning && data.warnings.length > 2 && (
        <div className="section-note analysis-warning" role="status">
          <AlertTriangle size={13} /> +{data.warnings.length - 2} more warnings. Switch to Learning Mode to review all evidence limits.
        </div>
      )}

      {learning && (
        <div style={{ marginTop: 12 }}>
          <p className="section-note">
            Alignment: {Math.round(data.alignment_coverage_fraction * 100)}% measured coverage · local quality {evidenceStrengthOutOf100(data.local_alignment_confidence)} ·
            integrity cap {evidenceStrengthOutOf100(data.sim_integrity_confidence_cap)}.
          </p>
          <p className="section-note">
            Curvature basis: baseline {label(data.baseline_curvature_basis)} · test {label(data.test_curvature_basis)}.
            GPS geometry health: {data.baseline_gps_geometry_healthy ? "pass" : "fail"} / {data.test_gps_geometry_healthy ? "pass" : "fail"}.
          </p>
          {systems.map(({ title, report }) => (
            <details key={title} style={{ marginTop: 8 }}>
              <summary>{title}: evidence and blockers</summary>
              {report.conclusions.map((conclusion) => <ConclusionDetails conclusion={conclusion} key={conclusion.key} />)}
              {!report.gate.eligible && report.gate.needed_measurements.map((item) => (
                <p className="section-note" key={item}>Needed: {item}</p>
              ))}
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
