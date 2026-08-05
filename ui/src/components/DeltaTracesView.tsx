import type { EChartsOption, SeriesOption } from "echarts";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchCompareDeltaTraces } from "../api/client";
import type { CompareResponse, DeltaTraceResponse } from "../types/compare";
import { TimeDeltaComparison } from "./TimeDeltaComparison";
import { echarts, type EChartsType } from "../utils/echarts";

type DeltaTracesViewProps = {
  baselineRunId: string;
  testRunId: string;
  startPct: number;
  endPct: number;
  result: CompareResponse;
};

const DELTA_PRESET_CHANNELS: Record<string, string[]> = {
  "Speed / Platform Delta": [
    "speed_mph", "cfs_ride_height_in", "center_rake_fs_in",
    "side_rake_in", "drag_scrub_suspicion", "abs_steering_deg",
    "rpm", "dynamic_pressure_psf",
  ],
  "Four-Corner Ride Height Delta": [
    "lf_ride_height_in", "rf_ride_height_in",
    "lr_ride_height_in", "rr_ride_height_in",
  ],
  "Tire Delta": [
    "lf_pressure_gain", "rf_pressure_gain",
    "lr_pressure_gain", "rr_pressure_gain",
    "lf_temp_spread", "rf_temp_spread",
    "lr_temp_spread", "rr_temp_spread",
    "lf_slip_ratio_proxy", "rf_slip_ratio_proxy",
    "lr_slip_ratio_proxy", "rr_slip_ratio_proxy",
  ],
};

const DELTA_ROW_COLORS: Record<string, string> = {
  speed_mph: "#93c5fd",
  cfs_ride_height_in: "#4ade80",
  center_rake_fs_in: "#4ade80",
  side_rake_in: "#f59e0b",
  drag_scrub_suspicion: "#ef4444",
  abs_steering_deg: "#f59e0b",
  rpm: "#fde047",
  dynamic_pressure_psf: "#38bdf8",
  lf_ride_height_in: "#eab308",
  rf_ride_height_in: "#ef4444",
  lr_ride_height_in: "#eab308",
  rr_ride_height_in: "#22d3ee",
  lf_pressure_gain: "#4ade80",
  rf_pressure_gain: "#ef4444",
  lr_pressure_gain: "#eab308",
  rr_pressure_gain: "#22d3ee",
  lf_temp_spread: "#f97316",
  rf_temp_spread: "#ef4444",
  lr_temp_spread: "#eab308",
  rr_temp_spread: "#22d3ee",
  lf_slip_ratio_proxy: "#a78bfa",
  rf_slip_ratio_proxy: "#ef4444",
  lr_slip_ratio_proxy: "#eab308",
  rr_slip_ratio_proxy: "#f59e0b",
};

export function DeltaTracesView({ baselineRunId, testRunId, startPct, endPct, result }: DeltaTracesViewProps) {
  const chartNode = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const [preset, setPreset] = useState("Speed / Platform Delta");
  const [deltaData, setDeltaData] = useState<DeltaTraceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDeltaTraces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const channels = DELTA_PRESET_CHANNELS[preset] ?? DELTA_PRESET_CHANNELS["Speed / Platform Delta"];
      const data = await fetchCompareDeltaTraces({
        baseline_run_id: baselineRunId,
        test_run_id: testRunId,
        baseline_lap: result.baseline_lap,
        test_lap: result.test_lap,
        channels,
        x_axis: "lap_dist_ft",
        start_pct: 0,
        end_pct: 100,
        target_zone_start_pct: startPct,
        target_zone_end_pct: endPct,
      });
      setDeltaData(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load delta traces");
    } finally {
      setLoading(false);
    }
  }, [baselineRunId, testRunId, result.baseline_lap, result.test_lap, preset, startPct, endPct]);

  useEffect(() => { void loadDeltaTraces(); }, [loadDeltaTraces]);

  // ── chart ────────────────────────────────────────────────────
  useEffect(() => {
    if (!chartNode.current || !deltaData) return;
    const chart = echarts.init(chartNode.current, "dark");
    chartRef.current = chart;

    const channels = DELTA_PRESET_CHANNELS[preset] ?? DELTA_PRESET_CHANNELS["Speed / Platform Delta"];
    const available = channels.filter((ch) => deltaData.channels[ch] && !deltaData.channels[ch].unavailable_reason);
    const xs = deltaData.x_values;

    if (available.length === 0 || xs.length === 0) {
      chart.dispose();
      chartRef.current = null;
      return;
    }

    const ROW_H = 80;
    const ROW_GAP = 10;
    const GRID_LEFT = 80;
    const n = available.length;

    const grid = available.map((_, i) => ({
      left: GRID_LEFT,
      right: 24,
      top: 36 + i * (ROW_H + ROW_GAP),
      height: ROW_H,
    }));

    const xAxis = available.map((_, i) => ({
      type: "value" as const,
      gridIndex: i,
      min: "dataMin",
      max: "dataMax",
      axisLabel: { show: i === n - 1, color: "#8d9aaa" },
      axisLine: { lineStyle: { color: "#263241" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    }));

    const yAxis = available.map(() => ({
      type: "value" as const,
      axisLabel: { color: "#8d9aaa", fontSize: 10 },
      axisLine: { lineStyle: { color: "#263241" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    }));

    const graphic: any[] = available.map((ch, i) => ({
      type: "text",
      left: 4,
      top: 39 + i * (ROW_H + ROW_GAP),
      style: {
        text: deltaData.channels[ch]?.label ?? ch,
        fill: "#8d9aaa",
        fontSize: 11,
        fontWeight: 600,
        fontFamily: "Inter, sans-serif",
      },
    }));

    const totalH = 36 + n * (ROW_H + ROW_GAP) + 30;
    if (chartNode.current) {
      chartNode.current.style.height = `${totalH}px`;
      chartNode.current.style.minHeight = `${totalH}px`;
    }

    // Target zone highlight
    const tzStart = deltaData.target_zone_start_pct;
    const tzEnd = deltaData.target_zone_end_pct;
    const tzStartX = xs[Math.round((tzStart / 100) * (xs.length - 1))] ?? 0;
    const tzEndX = xs[Math.round((tzEnd / 100) * (xs.length - 1))] ?? 0;

    const series: SeriesOption[] = [];
    available.forEach((ch, i) => {
      const chData = deltaData.channels[ch];
      if (!chData) return;
      const color = DELTA_ROW_COLORS[ch] ?? "#8d9aaa";
      const data = xs.map((x, idx) => [x, chData.delta_values[idx]]);
      series.push({
        type: "line",
        name: ch,
        xAxisIndex: i,
        yAxisIndex: i,
        showSymbol: false,
        sampling: "lttb",
        connectNulls: false,
        lineStyle: { width: 1.35, color, type: chData.is_proxy ? "dashed" : "solid" },
        itemStyle: { color },
        data,
        markArea: {
          silent: true,
          itemStyle: { color: "#22c55e", opacity: 0.08 },
          data: [[{ xAxis: tzStartX }, { xAxis: tzEndX }]],
        },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "#555", type: "dashed", width: 1 },
          data: [{ yAxis: 0, label: { show: false } }],
        },
      });
    });

    const option: EChartsOption = {
      backgroundColor: "transparent",
      animation: false,
      tooltip: { show: false, axisPointer: { type: "cross" } },
      legend: { show: false },
      grid,
      xAxis,
      yAxis,
      graphic,
      dataZoom: [
        { type: "slider", xAxisIndex: available.map((_, i) => i), bottom: 4, height: 20, filterMode: "none" },
      ],
      toolbox: { feature: { dataZoom: { yAxisIndex: "none" }, restore: {} }, iconStyle: { borderColor: "#8d9aaa" } },
      axisPointer: { link: [{ xAxisIndex: available.map((_, i) => i) }] },
      series,
    };

    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
      if (chartRef.current === chart) chartRef.current = null;
    };
  }, [deltaData, preset]);

  // ── interpretation summary ───────────────────────────────────
  const summary = useMemo(() => {
    if (!deltaData) return null;
    const speed = deltaData.channels["speed_mph"];
    const cfs = deltaData.channels["cfs_ride_height_in"];

    const tzStart = deltaData.target_zone_start_pct;
    const tzEnd = deltaData.target_zone_end_pct;
    const tzStartIdx = Math.round((tzStart / 100) * (deltaData.lap_pct_values.length - 1));
    const tzEndIdx = Math.round((tzEnd / 100) * (deltaData.lap_pct_values.length - 1));

    const tzSpeedDeltas = speed?.delta_values.slice(tzStartIdx, tzEndIdx + 1).filter((d): d is number => d != null) ?? [];
    const tzCfsDeltas = cfs?.delta_values.slice(tzStartIdx, tzEndIdx + 1).filter((d): d is number => d != null) ?? [];
    const avgSpeedDelta = tzSpeedDeltas.length > 0 ? tzSpeedDeltas.reduce((a, b) => a + b, 0) / tzSpeedDeltas.length : null;
    const minCfsDelta = tzCfsDeltas.length > 0 ? Math.min(...tzCfsDeltas) : null;

    const speedDeltas = speed?.delta_values ?? [];
    let maxGainIdx = -1, maxLossIdx = -1;
    speedDeltas.forEach((d, i) => {
      if (d == null) return;
      if (maxGainIdx === -1 || d > (speedDeltas[maxGainIdx] ?? -Infinity)) maxGainIdx = i;
      if (maxLossIdx === -1 || d < (speedDeltas[maxLossIdx] ?? Infinity)) maxLossIdx = i;
    });

    const gainLoc = maxGainIdx >= 0 ? deltaData.x_values[maxGainIdx] : null;
    const lossLoc = maxLossIdx >= 0 ? deltaData.x_values[maxLossIdx] : null;
    const gainVal = maxGainIdx >= 0 ? speedDeltas[maxGainIdx] : null;
    const lossVal = maxLossIdx >= 0 ? speedDeltas[maxLossIdx] : null;

    const cfsDeltas = cfs?.delta_values ?? [];
    let worstCfsIdx = -1;
    cfsDeltas.forEach((d, i) => {
      if (d == null) return;
      if (worstCfsIdx === -1 || d < (cfsDeltas[worstCfsIdx] ?? Infinity)) worstCfsIdx = i;
    });
    const worstCfsLoc = worstCfsIdx >= 0 ? deltaData.x_values[worstCfsIdx] : null;
    const worstCfsVal = worstCfsIdx >= 0 ? cfsDeltas[worstCfsIdx] : null;

    return { avgSpeedDelta, minCfsDelta, gainLoc, gainVal, lossLoc, lossVal, worstCfsLoc, worstCfsVal };
  }, [deltaData]);

  return (
    <div className="compare-subview">
      <TimeDeltaComparison
        baselineRunId={baselineRunId}
        testRunId={testRunId}
        baselineLap={result.baseline_lap}
        testLap={result.test_lap}
      />
      <div className="delta-traces-controls">
        <select value={preset} onChange={(e) => setPreset(e.target.value)} aria-label="Delta trace preset">
          <option>Speed / Platform Delta</option>
          <option>Four-Corner Ride Height Delta</option>
          <option>Tire Delta</option>
        </select>
        <button className="secondary-button" onClick={loadDeltaTraces} disabled={loading}>
          <RefreshCw size={14} /> {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <p className="error-text">{error}</p>}

      {/* interpretation summary */}
      {summary && (
        <div className="delta-summary">
          <div className="delta-summary-item">
            <span className="delta-summary-label">Target Zone Avg Speed Δ</span>
            <span className="delta-summary-value" style={{ color: (summary.avgSpeedDelta ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
              {summary.avgSpeedDelta != null ? `${summary.avgSpeedDelta > 0 ? "+" : ""}${summary.avgSpeedDelta.toFixed(3)} mph` : "—"}
            </span>
          </div>
          <div className="delta-summary-item">
            <span className="delta-summary-label">Target Zone Min CFS Δ</span>
            <span className="delta-summary-value" style={{ color: (summary.minCfsDelta ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
              {summary.minCfsDelta != null ? `${summary.minCfsDelta > 0 ? "+" : ""}${summary.minCfsDelta.toFixed(3)} in` : "—"}
            </span>
          </div>
          <div className="delta-summary-item">
            <span className="delta-summary-label">Biggest Speed Gain</span>
            <span className="delta-summary-value">
              {summary.gainVal != null ? `${summary.gainVal > 0 ? "+" : ""}${summary.gainVal.toFixed(2)} mph` : "—"}
              {summary.gainLoc != null ? ` @ ${summary.gainLoc.toFixed(0)} ft` : ""}
            </span>
          </div>
          <div className="delta-summary-item">
            <span className="delta-summary-label">Biggest Speed Loss</span>
            <span className="delta-summary-value" style={{ color: "#ef4444" }}>
              {summary.lossVal != null ? `${summary.lossVal > 0 ? "+" : ""}${summary.lossVal.toFixed(2)} mph` : "—"}
              {summary.lossLoc != null ? ` @ ${summary.lossLoc.toFixed(0)} ft` : ""}
            </span>
          </div>
          <div className="delta-summary-item">
            <span className="delta-summary-label">Worst CFS Worsening</span>
            <span className="delta-summary-value" style={{ color: "#ef4444" }}>
              {summary.worstCfsVal != null ? `${summary.worstCfsVal.toFixed(3)} in` : "—"}
              {summary.worstCfsLoc != null ? ` @ ${summary.worstCfsLoc.toFixed(0)} ft` : ""}
            </span>
          </div>
        </div>
      )}

      {/* Data scope label — truthful about range semantics */}
      <p className="section-note" style={{ fontSize: 10, margin: 0 }}>
        Full-lap delta trace — target zone ({startPct}–{endPct}%) highlighted in green band.
      </p>

      {/* missing channels */}
      {deltaData && deltaData.missing_channels.length > 0 && (
        <p className="warning-line">
          <AlertTriangle size={12} /> Channels not available: {deltaData.missing_channels.join(", ")}
        </p>
      )}

      {/* chart */}
      {loading && !deltaData && <p className="muted">Loading delta traces…</p>}
      <div ref={chartNode} className="delta-traces-chart" />
      {deltaData && Object.keys(deltaData.channels).length === 0 && (
        <p className="muted">No delta trace data available for the selected channels.</p>
      )}
    </div>
  );
}
