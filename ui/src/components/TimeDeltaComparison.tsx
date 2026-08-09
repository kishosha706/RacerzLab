import { AlertTriangle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchCompareTimeAnalysis } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { TimeAnalysisResponse } from "../types/compare";

type Props = {
  baselineRunId: string;
  testRunId: string;
  baselineLap: number | null;
  testLap: number | null;
};

type TimeAnalysisRequestState = {
  requestKey: string | null;
  data: TimeAnalysisResponse | null;
  loading: boolean;
  error: string | null;
};

type RequestIdentity = {
  requestKey: string;
  sequence: number;
};

function seconds(value: number | null, signed = true): string {
  if (value == null || !Number.isFinite(value)) return "Unavailable";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)} s`;
}

function phaseLabel(value: string | null | undefined): string {
  return value ? value.replace(/_/g, " ") : "Unknown phase";
}

function pathSegments(values: (number | null)[], width: number, height: number, min: number, max: number): string[] {
  const range = Math.max(0.001, max - min);
  const paths: string[] = [];
  let current = "";
  values.forEach((value, index) => {
    if (value == null) {
      if (current) paths.push(current);
      current = "";
      return;
    }
    const x = values.length <= 1 ? 0 : index / (values.length - 1) * width;
    const y = height - (value - min) / range * height;
    current += `${current ? " L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  });
  if (current) paths.push(current);
  return paths;
}

export function TimeDeltaComparison({ baselineRunId, testRunId, baselineLap, testLap }: Props) {
  const { selection } = useTelemetrySelection();
  const learning = selection.selectedMode === "learning";
  const request = useMemo(() => baselineLap == null || testLap == null ? null : ({
    baseline_run_id: baselineRunId,
    test_run_id: testRunId,
    baseline_lap: baselineLap,
    test_lap: testLap,
    step_pct: 0.1,
  }), [baselineLap, baselineRunId, testLap, testRunId]);
  const requestKey = useMemo(() => request == null ? null : JSON.stringify(request), [request]);
  const requestSequenceRef = useRef(0);
  const latestRequestRef = useRef<RequestIdentity | null>(null);
  const [requestState, setRequestState] = useState<TimeAnalysisRequestState>({
    requestKey: null,
    data: null,
    loading: false,
    error: null,
  });
  const [cursorIndex, setCursorIndex] = useState<number | null>(null);
  const stateOwnsRequest = requestState.requestKey === requestKey;
  const data = stateOwnsRequest ? requestState.data : null;
  const loading = requestKey != null && (!stateOwnsRequest || requestState.loading);
  const error = stateOwnsRequest ? requestState.error : null;

  const load = useCallback(async () => {
    if (request == null || requestKey == null) {
      latestRequestRef.current = null;
      setRequestState({ requestKey: null, data: null, loading: false, error: null });
      setCursorIndex(null);
      return;
    }
    const requestIdentity = {
      requestKey,
      sequence: ++requestSequenceRef.current,
    };
    latestRequestRef.current = requestIdentity;
    setRequestState({ requestKey, data: null, loading: true, error: null });
    setCursorIndex(null);
    const isLatestRequest = () => {
      const latestRequest = latestRequestRef.current;
      return latestRequest?.requestKey === requestIdentity.requestKey
        && latestRequest.sequence === requestIdentity.sequence;
    };
    try {
      const nextData = await fetchCompareTimeAnalysis(request);
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
          error: "Time comparison scope error: the response did not match the selected runs and laps.",
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
        error: caught instanceof Error ? caught.message : "Time analysis unavailable",
      });
    }
  }, [request, requestKey]);

  useEffect(() => {
    void load();
    return () => {
      if (latestRequestRef.current?.requestKey === requestKey) latestRequestRef.current = null;
    };
  }, [load, requestKey]);

  const chart = useMemo(() => {
    if (!data) return null;
    const finite = data.cumulative_delta_s.filter((value): value is number => value != null && Number.isFinite(value));
    if (!finite.length) return null;
    const min = Math.min(0, ...finite);
    const max = Math.max(0, ...finite);
    const width = 1000;
    const height = 220;
    return {
      width,
      height,
      min,
      max,
      zeroY: height - (0 - min) / Math.max(0.001, max - min) * height,
      segments: pathSegments(data.cumulative_delta_s, width, height, min, max),
    };
  }, [data]);

  const cursor = data != null && cursorIndex != null ? {
    pct: data.grid_pct[cursorIndex],
    delta: data.cumulative_delta_s[cursorIndex],
    phase: data.phase_by_position[cursorIndex],
    alignment: data.alignment[cursorIndex],
    basis: data.incremental_basis[cursorIndex],
  } : null;

  const phaseEffects = useMemo(() => (
    [...(data?.phase_effects ?? [])]
      .filter((effect) => effect.delta_s != null)
      .sort((left, right) => Math.abs(right.delta_s ?? 0) - Math.abs(left.delta_s ?? 0))
      .slice(0, learning ? 8 : 4)
  ), [data, learning]);

  if (loading && !data) return <div className="analysis-state" role="status" aria-live="polite">Calculating matched-position time delta…</div>;
  if (error) return (
    <div className="warning-banner" role="alert">
      <AlertTriangle size={16} />
      <span>{error}</span>
      <button type="button" className="secondary-button" onClick={() => void load()}><RefreshCw size={14} /> Retry</button>
    </div>
  );
  if (!data) return null;

  return (
    <section className="panel" aria-label="Physical-position time comparison" data-analysis-surface="matched_position_time_delta" style={{ marginBottom: 16 }}>
      <div className="section-header-row">
        <div>
          <h3>Cumulative Time</h3>
          <p className="section-note">
            {learning
              ? "Calculated at matched physical track positions. Positive is time lost by the test; negative is time gained. Gaps are never connected or extrapolated."
              : "Test vs baseline · negative is faster"}
          </p>
        </div>
        <span className={`confidence-badge ${data.local_alignment_confidence >= 0.75 ? "high" : data.local_alignment_confidence >= 0.55 ? "medium" : "low"}`}>
          {Math.round(data.local_alignment_confidence * 100)}% local alignment
        </span>
      </div>

      <div className="metric-grid" style={{ marginBottom: 12 }}>
        <div className="metric-card"><span>Selected time delta</span><strong>{seconds(data.selected_effect_s)}</strong></div>
        <div className="metric-card"><span>Matched coverage</span><strong>{Math.round(data.coverage_fraction * 100)}%</strong></div>
        <div className="metric-card"><span>Theoretical opportunity</span><strong>{seconds(data.theoretical_opportunity_s, false)}</strong></div>
        <div className="metric-card"><span>Repeatable opportunity</span><strong>{seconds(data.repeatable_opportunity_s, false)}</strong></div>
      </div>

      {!data.time_delta_complete && (
        <div className="warning-banner" role="status"><AlertTriangle size={16} />Incomplete matched coverage: no whole-window time delta is reported.</div>
      )}

      {chart && (
        <div style={{ position: "relative" }}>
          <svg
            viewBox={`0 0 ${chart.width} ${chart.height}`}
            role="img"
            aria-label="Cumulative time delta with honest telemetry gaps"
            style={{ width: "100%", height: 250, display: "block", background: "#0b121b", borderRadius: 8 }}
            onMouseLeave={() => setCursorIndex(null)}
            onMouseMove={(event) => {
              const bounds = event.currentTarget.getBoundingClientRect();
              const ratio = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
              setCursorIndex(Math.round(ratio * (data.grid_pct.length - 1)));
            }}
          >
            <line x1="0" x2={chart.width} y1={chart.zeroY} y2={chart.zeroY} stroke="#526070" strokeDasharray="6 5" />
            {chart.segments.map((path, index) => <path key={index} d={path} fill="none" stroke="#38bdf8" strokeWidth="3" />)}
            {data.gain_origin_pct != null && <line x1={data.gain_origin_pct / 100 * chart.width} x2={data.gain_origin_pct / 100 * chart.width} y1="0" y2={chart.height} stroke="#22c55e" strokeDasharray="4 4" />}
            {data.surrender_pct != null && <line x1={data.surrender_pct / 100 * chart.width} x2={data.surrender_pct / 100 * chart.width} y1="0" y2={chart.height} stroke="#f59e0b" strokeDasharray="4 4" />}
            {cursorIndex != null && <line x1={cursorIndex / Math.max(1, data.grid_pct.length - 1) * chart.width} x2={cursorIndex / Math.max(1, data.grid_pct.length - 1) * chart.width} y1="0" y2={chart.height} stroke="#f8fafc" />}
          </svg>
          <label className="time-delta-scrubber">
            <span>Track position</span>
            <input
              type="range"
              min={0}
              max={Math.max(0, data.grid_pct.length - 1)}
              step={1}
              value={cursorIndex ?? 0}
              onChange={(event) => setCursorIndex(Number(event.target.value))}
              aria-label="Explore the cumulative time delta by track position"
            />
          </label>
          <div className="section-note" style={{ display: "flex", gap: 16, flexWrap: "wrap", marginTop: 6 }}>
            <span>Origin: {data.gain_origin_pct != null ? `${data.gain_origin_pct.toFixed(1)}% · ${phaseLabel(data.gain_origin_phase)}` : "No verified gain"}</span>
            <span>Surrender: {data.surrender_pct != null ? `${data.surrender_pct.toFixed(1)}%` : "Not observed"}</span>
            <span>Persistence: {data.gain_persistence_pct != null ? `${data.gain_persistence_pct.toFixed(1)}% lap` : "Unavailable"}</span>
          </div>
        </div>
      )}

      <div className="panel" style={{ marginTop: 12 }} aria-live="polite">
        <strong>Cursor</strong>{" "}
        {cursor ? (
          <span>
            {cursor.pct.toFixed(1)}% · {phaseLabel(cursor.phase)} · {seconds(cursor.delta)} · {Math.round(cursor.alignment.confidence * 100)}% alignment
            {cursor.alignment.uncertainty_pct != null ? ` · ±${cursor.alignment.uncertainty_pct.toFixed(2)}% position` : ""}
            {cursor.alignment.is_gap ? ` · gap: ${cursor.alignment.gap_reason ?? "missing paired coverage"}` : ""}
            {learning && cursor.basis ? ` · ${phaseLabel(cursor.basis)}` : ""}
          </span>
        ) : <span className="muted">Move over the plot or use the track-position slider for synchronized phase, delta, and uncertainty.</span>}
      </div>

      <div style={{ marginTop: 12 }}>
        <h4>Largest phase effects</h4>
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Phase</th><th>Location</th><th>Time</th><th>Alignment</th>{learning && <th>Basis</th>}</tr></thead>
            <tbody>
              {phaseEffects.map((effect, index) => (
                <tr key={`${effect.phase}-${effect.start_pct}-${index}`}>
                  <td>{phaseLabel(effect.phase)}</td>
                  <td>{effect.start_pct.toFixed(1)}–{effect.end_pct.toFixed(1)}%</td>
                  <td>{seconds(effect.delta_s)}</td>
                  <td>{Math.round(effect.alignment_confidence * 100)}%</td>
                  {learning && <td title={effect.source_channels.join(", ")}>{phaseLabel(effect.calculation_basis)}</td>}
                </tr>
              ))}
              {phaseEffects.length === 0 && (
                <tr><td colSpan={learning ? 5 : 4} className="muted">No phase effect has enough matched coverage to report.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {learning && (
        <div className="section-note" style={{ marginTop: 12 }}>
          Statistical unit: {data.noise.experiment_unit.replace(/_/g, " ")} · {data.noise.paired_lap_differences} paired laps ·
          {data.noise.context_complete ? " context complete" : ` repeatability blocked (${data.noise.context_blockers.join(", ")})`}.
          A/B/A status: {phaseLabel(data.noise.aba_consistency)}.
        </div>
      )}
      {data.warnings.slice(0, learning ? data.warnings.length : 2).map((warning) => (
        <div className="section-note analysis-warning" role="status" key={warning}><AlertTriangle size={13} /> {warning}</div>
      ))}
      {!learning && data.warnings.length > 2 && (
        <div className="section-note analysis-warning" role="status">
          <AlertTriangle size={13} /> +{data.warnings.length - 2} more warnings in Learning Mode.
        </div>
      )}
    </section>
  );
}
