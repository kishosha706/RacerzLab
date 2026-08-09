import type { EChartsOption, SeriesOption } from "echarts";
import { AlertTriangle, RefreshCw, RotateCcw } from "lucide-react";
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

type DeltaTooltipParam = {
  dataIndex?: number;
  seriesIndex?: number;
  value?: unknown;
};

function escapeTooltipText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function finiteChartNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function compactAxisValue(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (magnitude >= 10) return value.toFixed(0);
  if (magnitude >= 1) return value.toFixed(1);
  return value.toFixed(2);
}

export function DeltaTracesView({ baselineRunId, testRunId, startPct, endPct, result }: DeltaTracesViewProps) {
  const chartNode = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const requestSequenceRef = useRef(0);
  const latestRequestRef = useRef<{ key: string; sequence: number } | null>(null);
  const [preset, setPreset] = useState("Speed / Platform Delta");
  const [deltaResult, setDeltaResult] = useState<{ requestKey: string; data: DeltaTraceResponse } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requestedChannels = useMemo(
    () => DELTA_PRESET_CHANNELS[preset] ?? DELTA_PRESET_CHANNELS["Speed / Platform Delta"],
    [preset],
  );
  const deltaRequest = useMemo(() => ({
    baseline_run_id: baselineRunId,
    test_run_id: testRunId,
    baseline_lap: result.baseline_lap,
    test_lap: result.test_lap,
    channels: requestedChannels,
    x_axis: "lap_dist_ft",
    start_pct: 0,
    end_pct: 100,
    target_zone_start_pct: startPct,
    target_zone_end_pct: endPct,
  }), [baselineRunId, endPct, requestedChannels, result.baseline_lap, result.test_lap, startPct, testRunId]);
  const deltaRequestKey = useMemo(() => JSON.stringify(deltaRequest), [deltaRequest]);
  const deltaData = deltaResult?.requestKey === deltaRequestKey ? deltaResult.data : null;

  const loadDeltaTraces = useCallback(async () => {
    const requestIdentity = { key: deltaRequestKey, sequence: ++requestSequenceRef.current };
    latestRequestRef.current = requestIdentity;
    setLoading(true);
    setError(null);
    setDeltaResult(null);
    const isLatestRequest = () => latestRequestRef.current?.key === requestIdentity.key
      && latestRequestRef.current.sequence === requestIdentity.sequence;
    try {
      const data = await fetchCompareDeltaTraces(deltaRequest);
      if (!isLatestRequest()) return;
      const responseMatchesRequest = data.baseline_run_id === deltaRequest.baseline_run_id
        && data.test_run_id === deltaRequest.test_run_id
        && data.baseline_lap === deltaRequest.baseline_lap
        && data.test_lap === deltaRequest.test_lap
        && data.x_axis === deltaRequest.x_axis
        && Math.abs(data.target_zone_start_pct - deltaRequest.target_zone_start_pct) < 1e-9
        && Math.abs(data.target_zone_end_pct - deltaRequest.target_zone_end_pct) < 1e-9
        && requestedChannels.every((channel) => channel in data.channels || data.missing_channels.includes(channel));
      if (!responseMatchesRequest) {
        throw new Error("Delta trace scope error: the response did not match the selected runs, laps, channels, and target zone.");
      }
      setDeltaResult({ requestKey: deltaRequestKey, data });
    } catch (e) {
      if (!isLatestRequest()) return;
      setDeltaResult(null);
      setError(e instanceof Error ? e.message : "Failed to load delta traces");
    } finally {
      if (isLatestRequest()) setLoading(false);
    }
  }, [deltaRequest, deltaRequestKey, requestedChannels]);

  useEffect(() => { void loadDeltaTraces(); }, [loadDeltaTraces]);

  const resetChartView = useCallback(() => {
    chartRef.current?.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
  }, []);

  // ── chart ────────────────────────────────────────────────────
  useEffect(() => {
    const node = chartNode.current;
    if (!node || !deltaData) return;
    const channels = DELTA_PRESET_CHANNELS[preset] ?? DELTA_PRESET_CHANNELS["Speed / Platform Delta"];
    const available = channels.filter((ch) => deltaData.channels[ch] && !deltaData.channels[ch].unavailable_reason);
    const xs = deltaData.x_values;

    if (available.length === 0 || xs.length === 0) {
      node.style.height = "160px";
      node.style.minHeight = "160px";
      return;
    }

    const ROW_H = 86;
    const ROW_GAP = 8;
    const GRID_TOP = 34;
    const GRID_LEFT = 164;
    const n = available.length;
    const totalH = GRID_TOP + n * (ROW_H + ROW_GAP) + 64;
    node.style.height = `${totalH}px`;
    node.style.minHeight = `${totalH}px`;

    const chart = echarts.init(node, "dark");
    chartRef.current = chart;

    const grid = available.map((_, i) => ({
      left: GRID_LEFT,
      right: 22,
      top: GRID_TOP + i * (ROW_H + ROW_GAP),
      height: ROW_H,
      containLabel: false,
    }));

    const xAxis = available.map((_, i) => ({
      type: "value" as const,
      gridIndex: i,
      min: "dataMin",
      max: "dataMax",
      axisLabel: {
        show: i === n - 1,
        color: "#758497",
        fontSize: 9,
        hideOverlap: true,
        margin: 9,
        formatter: (value: number) => compactAxisValue(value),
      },
      axisLine: {
        show: i === n - 1,
        lineStyle: { color: "rgba(148, 163, 184, 0.22)", width: 1 },
      },
      axisTick: { show: false },
      splitNumber: 6,
      splitLine: {
        show: true,
        lineStyle: { color: "rgba(148, 163, 184, 0.055)", width: 1 },
      },
      axisPointer: {
        show: true,
        snap: true,
        lineStyle: { color: "rgba(226, 232, 240, 0.68)", width: 1 },
        label: { show: false },
      },
    }));

    const yAxis = available.map((_, i) => ({
      type: "value" as const,
      gridIndex: i,
      axisLabel: {
        color: "#718094",
        fontSize: 9,
        margin: 8,
        formatter: (value: number) => compactAxisValue(value),
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitNumber: 3,
      splitLine: {
        show: true,
        lineStyle: { color: "rgba(148, 163, 184, 0.075)", width: 1 },
      },
    }));

    const graphic: any[] = available.flatMap((ch, i) => {
      const chData = deltaData.channels[ch];
      const color = DELTA_ROW_COLORS[ch] ?? "#94a3b8";
      const rowTop = GRID_TOP + i * (ROW_H + ROW_GAP);
      return [
        {
          type: "rect",
          silent: true,
          left: 3,
          top: rowTop + 3,
          shape: { width: 3, height: 30, r: 2 },
          style: { fill: color, shadowBlur: 8, shadowColor: color },
        },
        {
          type: "text",
          silent: true,
          left: 16,
          top: rowTop + 1,
          style: {
            text: chData?.label ?? ch,
            width: GRID_LEFT - 26,
            overflow: "truncate",
            fill: "#dbe7f3",
            fontSize: 11,
            fontWeight: 650,
            fontFamily: "Inter, sans-serif",
          },
        },
        {
          type: "text",
          silent: true,
          left: 16,
          top: rowTop + 21,
          style: {
            text: `${chData?.unit || "unitless"} · ${chData?.is_proxy ? "PROXY DELTA" : "CHANNEL DELTA"}`,
            fill: chData?.is_proxy ? "#d8b4fe" : "#69798d",
            fontSize: 8,
            fontWeight: 700,
            fontFamily: "Inter, sans-serif",
          },
        },
      ];
    });

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
        name: chData.label,
        xAxisIndex: i,
        yAxisIndex: i,
        showSymbol: false,
        symbol: "circle",
        symbolSize: 6,
        sampling: "lttb",
        connectNulls: false,
        smooth: false,
        clip: true,
        lineStyle: {
          width: chData.is_proxy ? 1.9 : 2.25,
          color,
          opacity: chData.is_proxy ? 0.86 : 0.96,
          type: chData.is_proxy ? "dashed" : "solid",
          cap: "round",
          join: "round",
        },
        itemStyle: { color },
        emphasis: {
          focus: "series",
          lineStyle: { width: chData.is_proxy ? 2.5 : 3.1, opacity: 1 },
          itemStyle: { color, borderColor: "#f8fafc", borderWidth: 1 },
        },
        areaStyle: ch === "speed_mph" && !chData.is_proxy ? {
          origin: 0,
          opacity: 1,
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(147, 197, 253, 0.16)" },
            { offset: 0.72, color: "rgba(56, 189, 248, 0.035)" },
            { offset: 1, color: "rgba(56, 189, 248, 0)" },
          ]),
        } : undefined,
        data,
        markArea: {
          silent: true,
          label: {
            show: i === 0,
            position: "insideTop",
            color: "rgba(134, 239, 172, 0.72)",
            fontSize: 8,
            fontWeight: 700,
            formatter: "TARGET ZONE",
          },
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
              { offset: 0, color: "rgba(34, 197, 94, 0.025)" },
              { offset: 0.5, color: "rgba(34, 197, 94, 0.085)" },
              { offset: 1, color: "rgba(34, 197, 94, 0.025)" },
            ]),
          },
          data: [[{ xAxis: tzStartX }, { xAxis: tzEndX }]],
        },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: "rgba(226, 232, 240, 0.3)", type: "solid", width: 1.1 },
          data: [{
            yAxis: 0,
            label: {
              show: true,
              formatter: "0 Δ",
              position: "insideEndTop",
              color: "rgba(203, 213, 225, 0.54)",
              fontSize: 8,
              distance: 3,
            },
          }],
        },
        z: 3,
      });
    });

    const formatTooltip = (rawParams: DeltaTooltipParam | DeltaTooltipParam[]) => {
      const param = Array.isArray(rawParams) ? rawParams[0] : rawParams;
      if (!param) return "";
      const channel = available[param.seriesIndex ?? 0];
      const channelData = channel ? deltaData.channels[channel] : null;
      if (!channelData) return "";
      const tuple = Array.isArray(param.value) ? param.value : [];
      const distance = finiteChartNumber(tuple[0]);
      const delta = finiteChartNumber(tuple[1]);
      const lapPct = param.dataIndex == null ? null : deltaData.lap_pct_values[param.dataIndex] ?? null;
      const inTargetZone = lapPct != null && lapPct >= tzStart && lapPct <= tzEnd;
      const color = DELTA_ROW_COLORS[channel] ?? "#94a3b8";
      const unit = escapeTooltipText(channelData.unit || "unitless");
      const value = delta == null ? "Gap · no paired sample" : `${delta > 0 ? "+" : ""}${compactAxisValue(delta)} ${unit}`;
      const location = distance == null
        ? "Physical position unavailable"
        : `${distance.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${escapeTooltipText(deltaData.x_unit)}`;
      const position = lapPct == null ? "" : ` · ${lapPct.toFixed(1)}% lap`;
      return [
        `<div class="delta-chart-tooltip" data-proxy="${channelData.is_proxy ? "true" : "false"}">`,
        `<div class="delta-chart-tooltip-location">${location}${position}${inTargetZone ? " · TARGET ZONE" : ""}</div>`,
        `<div class="delta-chart-tooltip-signal"><span style="background:${color}"></span>${escapeTooltipText(channelData.label)}</div>`,
        `<div class="delta-chart-tooltip-value">${value}</div>`,
        `<div class="delta-chart-tooltip-basis">Test − baseline · ${channelData.is_proxy ? "proxy delta" : "channel delta"}</div>`,
        "</div>",
      ].join("");
    };

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const option: EChartsOption = {
      backgroundColor: "transparent",
      animation: !reduceMotion,
      animationDuration: 360,
      animationEasing: "cubicOut",
      tooltip: {
        show: true,
        trigger: "axis",
        triggerOn: "mousemove|click",
        confine: true,
        renderMode: "html",
        backgroundColor: "rgba(7, 12, 20, 0.96)",
        borderColor: "rgba(148, 163, 184, 0.28)",
        borderWidth: 1,
        padding: [10, 12],
        textStyle: { color: "#e5edf6", fontSize: 11 },
        extraCssText: "border-radius:10px;box-shadow:0 16px 44px rgba(0,0,0,.42);backdrop-filter:blur(10px);",
        axisPointer: { type: "line" },
        formatter: formatTooltip,
      },
      legend: { show: false },
      grid,
      xAxis,
      yAxis,
      graphic,
      dataZoom: [
        {
          type: "slider",
          xAxisIndex: available.map((_, i) => i),
          bottom: 3,
          height: 22,
          filterMode: "none",
          showDetail: false,
          brushSelect: false,
          borderColor: "transparent",
          backgroundColor: "rgba(15, 23, 42, 0.5)",
          fillerColor: "rgba(56, 189, 248, 0.15)",
          dataBackground: {
            lineStyle: { color: "rgba(125, 211, 252, 0.32)", width: 1 },
            areaStyle: { color: "rgba(56, 189, 248, 0.035)" },
          },
          selectedDataBackground: {
            lineStyle: { color: "rgba(125, 211, 252, 0.55)", width: 1 },
            areaStyle: { color: "rgba(56, 189, 248, 0.075)" },
          },
          handleSize: "65%",
          handleStyle: {
            color: "#7dd3fc",
            borderColor: "rgba(224, 242, 254, 0.72)",
            borderWidth: 1,
          },
          moveHandleStyle: { color: "rgba(125, 211, 252, 0.46)" },
          emphasis: {
            handleLabel: { show: false },
            handleStyle: { color: "#bae6fd", borderColor: "#f0f9ff" },
            moveHandleStyle: { color: "rgba(186, 230, 253, 0.72)" },
          },
        },
      ],
      axisPointer: {
        link: [{ xAxisIndex: available.map((_, i) => i) }],
        lineStyle: { color: "rgba(226, 232, 240, 0.68)", width: 1 },
      },
      series,
    };

    chart.setOption(option);
    let resizeFrame: number | null = null;
    const resize = () => {
      if (resizeFrame != null) window.cancelAnimationFrame(resizeFrame);
      resizeFrame = window.requestAnimationFrame(() => {
        resizeFrame = null;
        if (!chart.isDisposed()) chart.resize();
      });
    };
    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    resizeObserver?.observe(node);
    window.addEventListener("resize", resize);
    return () => {
      resizeObserver?.disconnect();
      window.removeEventListener("resize", resize);
      if (resizeFrame != null) window.cancelAnimationFrame(resizeFrame);
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
    <div
      className="compare-subview delta-traces-view"
      data-chart-surface="delta-comparison"
      data-chart-density="trace-lanes"
    >
      <TimeDeltaComparison
        baselineRunId={baselineRunId}
        testRunId={testRunId}
        baselineLap={result.baseline_lap}
        testLap={result.test_lap}
      />

      <section className="delta-traces-surface" aria-label="Full-lap signal delta traces">
        <header className="delta-traces-header" data-chart-header>
          <div className="delta-traces-heading">
            <span className="delta-traces-overline">Signal comparison</span>
            <h3>Full-Lap Delta Traces</h3>
            <p>Matched track position · test minus baseline</p>
          </div>
          <div className="delta-traces-controls" data-chart-controls>
            <label className="delta-traces-preset">
              <span>Signal set</span>
              <select value={preset} onChange={(e) => setPreset(e.target.value)} aria-label="Delta trace preset">
                <option>Speed / Platform Delta</option>
                <option>Four-Corner Ride Height Delta</option>
                <option>Tire Delta</option>
              </select>
            </label>
            <button
              type="button"
              className="secondary-button delta-traces-action"
              onClick={resetChartView}
              disabled={loading || !deltaData}
              aria-label="Reset delta trace zoom"
            >
              <RotateCcw size={14} /> Reset view
            </button>
            <button
              type="button"
              className="secondary-button delta-traces-action"
              onClick={() => void loadDeltaTraces()}
              disabled={loading}
            >
              <RefreshCw size={14} /> {loading ? "Loading…" : "Refresh"}
            </button>
          </div>
        </header>

        <div className="delta-traces-key" data-chart-legend aria-label="Delta trace visual key">
          <span className="delta-traces-key-direction">Test − baseline</span>
          <span className="delta-traces-key-item" data-trace-key="channel">
            <span className="delta-traces-key-line" aria-hidden="true" /> Channel delta
          </span>
          <span className="delta-traces-key-item" data-trace-key="proxy">
            <span className="delta-traces-key-line is-proxy" aria-hidden="true" /> Proxy delta
          </span>
          <span className="delta-traces-key-item" data-trace-key="target-zone">
            <span className="delta-traces-key-zone" aria-hidden="true" /> Target zone
          </span>
        </div>

        {error && <p className="error-text" role="alert">{error}</p>}

        {/* interpretation summary */}
        {summary && (
          <div className="delta-summary" data-chart-summary>
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
        <p className="section-note delta-traces-scope">
          Full-lap delta trace — target zone ({startPct}–{endPct}%) highlighted in green band.
        </p>

        {/* missing channels */}
        {deltaData && deltaData.missing_channels.length > 0 && (
          <p className="warning-line">
            <AlertTriangle size={12} /> Channels not available: {deltaData.missing_channels.join(", ")}
          </p>
        )}

        {/* chart */}
        {loading && !deltaData && <p className="muted" role="status">Loading delta traces…</p>}
        <div className="delta-traces-stage" data-chart-stage data-loading={loading ? "true" : "false"}>
          {loading && deltaData && (
            <span className="delta-traces-loading" role="status">Refreshing signals…</span>
          )}
          <div
            ref={chartNode}
            className="delta-traces-chart"
            data-chart-engine="echarts"
            data-trace-preset={preset}
            role="img"
            aria-label={`${preset}. Full-lap test-minus-baseline signal deltas with synchronized physical-position cursor and honest data gaps.`}
          />
        </div>
        {deltaData && Object.keys(deltaData.channels).length === 0 && (
          <p className="muted">No delta trace data available for the selected channels.</p>
        )}
      </section>
    </div>
  );
}
