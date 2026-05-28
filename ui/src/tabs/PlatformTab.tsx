import * as echarts from "echarts";
import type { EChartsOption, SeriesOption } from "echarts";
import { Activity, AlertTriangle, Crosshair, LocateFixed, RotateCcw } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EvidenceCard } from "../components/EvidenceCard";
import { EngineeringMetricCard } from "../components/EngineeringMetricCard";
import { CornerTireMap } from "../components/CornerTireMap";
import { ProxyBadge } from "../components/ProxyBadge";
import { RiskBar } from "../components/RiskBar";
import { WorkbenchSubnav } from "../components/WorkbenchSubnav";
import type { WorkbenchView } from "../components/WorkbenchSubnav";
import { fetchPlatformEvents } from "../api/client";
import { isProxyChannel, isEstimateChannel, getChannelDisclaimer } from "../utils/channelMeta";
import { getTraceValues, formatChannelValue, formatRiskScore, formatForceProxyN, safeStringValue } from "../utils/channelFormat";
import type {
  PlatformEventItem,
  RunOverview,
  TelemetryCursor,
  TelemetryEvent,
  TraceChannelPayload,
  TraceResponse,
} from "../types/telemetry";

type PlatformTabProps = {
  overview: RunOverview;
  trace: TraceResponse | null;
  cursor: TelemetryCursor;
  onCursorChange: (cursor: TelemetryCursor) => void;
};

type ChartRow = {
  label: string;
  channels: Array<{ name: string; label: string; color: string }>;
  min?: number;
  max?: number;
};

const PRESET_ROWS: Record<string, ChartRow[]> = {
  "Platform / Rake / Ride Height": [
    { label: "Throttle / Brake [%]", channels: [{ name: "throttle_pct", label: "Throttle", color: "#22c55e" }, { name: "brake_pct", label: "Brake", color: "#ef4444" }], min: 0, max: 105 },
    { label: "Center Rake FS [in]", channels: [{ name: "center_rake_fs_in", label: "Center Rake", color: "#4ade80" }] },
    { label: "Side Rake [in]", channels: [{ name: "side_rake_in", label: "Side Rake", color: "#f59e0b" }] },
    { label: "CFS / LF / RF Ride Height [in]", channels: [
      { name: "cfs_ride_height_in", label: "CFS", color: "#4ade80" },
      { name: "lf_ride_height_in", label: "LF", color: "#eab308" },
      { name: "rf_ride_height_in", label: "RF", color: "#ef4444" },
    ] },
    { label: "LR / RR Ride Height [in]", channels: [
      { name: "lr_ride_height_in", label: "LR", color: "#eab308" },
      { name: "rr_ride_height_in", label: "RR", color: "#22d3ee" },
    ] },
  ],
  "Speed / RPM / Pull": [
    { label: "Speed [mph]", channels: [{ name: "speed_mph", label: "Speed", color: "#93c5fd" }] },
    { label: "RPM", channels: [{ name: "rpm", label: "RPM", color: "#fde047" }] },
    { label: "Gear", channels: [{ name: "gear", label: "Gear", color: "#a78bfa" }] },
    { label: "Throttle / Brake [%]", channels: [{ name: "throttle_pct", label: "Throttle", color: "#22c55e" }, { name: "brake_pct", label: "Brake", color: "#ef4444" }], min: 0, max: 105 },
    { label: "Speed Rate [mph/s]", channels: [{ name: "speed_rate_mph_s", label: "Speed Rate", color: "#f59e0b" }] },
  ],
  "Drag / Scrub": [
    { label: "Drag/Scrub Suspicion", channels: [{ name: "drag_scrub_suspicion", label: "Suspicion", color: "#ef4444" }], min: 0, max: 1 },
    { label: "Speed Rate / 1000 ft", channels: [{ name: "speed_rate_mph_1000ft", label: "Rate/1000ft", color: "#f97316" }] },
    { label: "Throttle / Brake [%]", channels: [{ name: "throttle_pct", label: "Throttle", color: "#22c55e" }, { name: "brake_pct", label: "Brake", color: "#ef4444" }], min: 0, max: 105 },
    { label: "Steering [deg]", channels: [{ name: "abs_steering_deg", label: "Steering", color: "#f59e0b" }] },
    { label: "Lat Accel", channels: [{ name: "abs_lat_accel", label: "Lat Accel", color: "#a78bfa" }] },
    { label: "CFS Ride Height [in]", channels: [{ name: "cfs_ride_height_in", label: "CFS", color: "#38bdf8" }] },
  ],
  "Tires": [
    { label: "Tire Pressure [kPa]", channels: [
      { name: "lf_pressure", label: "LF", color: "#4ade80" },
      { name: "rf_pressure", label: "RF", color: "#ef4444" },
      { name: "lr_pressure", label: "LR", color: "#eab308" },
      { name: "rr_pressure", label: "RR", color: "#22d3ee" },
    ] },
    { label: "Pressure Gain [kPa]", channels: [
      { name: "lf_pressure_gain", label: "LF", color: "#4ade80" },
      { name: "rf_pressure_gain", label: "RF", color: "#ef4444" },
      { name: "lr_pressure_gain", label: "LR", color: "#eab308" },
      { name: "rr_pressure_gain", label: "RR", color: "#22d3ee" },
    ] },
    { label: "Temp Spread [°C]", channels: [
      { name: "lf_temp_spread", label: "LF", color: "#4ade80" },
      { name: "rf_temp_spread", label: "RF", color: "#ef4444" },
      { name: "lr_temp_spread", label: "LR", color: "#eab308" },
      { name: "rr_temp_spread", label: "RR", color: "#22d3ee" },
    ] },
    { label: "Slip Ratio Proxy", channels: [
      { name: "lf_slip_ratio_proxy", label: "LF", color: "#4ade80" },
      { name: "rf_slip_ratio_proxy", label: "RF", color: "#ef4444" },
      { name: "lr_slip_ratio_proxy", label: "LR", color: "#eab308" },
      { name: "rr_slip_ratio_proxy", label: "RR", color: "#22d3ee" },
    ] },
  ],
};

function asPayload(trace: TraceResponse | null, channel: string): TraceChannelPayload | null {
  const raw = trace?.channels[channel];
  if (!raw) return null;
  return Array.isArray(raw) ? { values: raw } : raw;
}

function values(trace: TraceResponse | null, channel: string): Array<number | string | null> {
  return asPayload(trace, channel)?.values ?? [];
}

function xValues(trace: TraceResponse | null): Array<number | null> {
  if (!trace) return [];
  if (Array.isArray(trace.x)) return trace.x;
  return (trace as any).x?.lap_dist_ft ?? trace.x_by_name?.lap_dist_ft ?? trace.x_by_name?.lap_dist_pct ?? [];
}

function valueAt(trace: TraceResponse | null, channel: string, index: number | null | undefined): number | null {
  if (index == null) return null;
  const v = values(trace, channel)[index];
  if (v == null || typeof v === "string") return null;
  return v;
}

function fmt(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return "n/a";
  return value.toFixed(digits);
}

function riskLabel(cfsIn: number | null | undefined) {
  if (cfsIn == null) return "Unavailable";
  if (cfsIn <= 0) return "Scrape";
  if (cfsIn <= 0.118) return "Critical";
  if (cfsIn <= 0.236) return "High";
  if (cfsIn <= 0.394) return "Watch";
  return "Safer";
}

function eventDistanceFt(event: TelemetryEvent) {
  return event.distance_m_peak == null ? null : event.distance_m_peak * 3.280839895;
}

/** Find the trace sample index nearest to a given lap_dist_ft value. */
function formatTooltipValue(channel: string, y: number | null | undefined): string {
  if (y == null || Number.isNaN(y)) return "—";
  if (channel.includes("_pct") || channel === "gear") return y.toFixed(0);
  if (channel.includes("mph")) return y.toFixed(2);
  if (channel.includes("_in") && channel.includes("cfs")) return y.toFixed(3);
  if (channel.includes("_in")) return y.toFixed(2);
  if (channel.includes("psf")) return y.toFixed(1);
  if (channel === "rpm") return y.toFixed(0);
  return y.toFixed(2);
}

function makeTooltipFormatter(rows: ChartRow[]) {
  // map series label → channel name for unit resolution
  const labelToChannel: Record<string, string> = {};
  for (const row of rows) {
    for (const ch of row.channels) {
      labelToChannel[ch.label] = ch.name;
    }
  }
  return (params: any) => {
    if (!Array.isArray(params) || params.length === 0) return "";
    const first = params[0];
    const tuple = Array.isArray(first.value) ? first.value : Array.isArray(first.data) ? first.data : null;
    const xVal = tuple ? tuple[0] : first.axisValue;
    const distFt = typeof xVal === "number" && !Number.isNaN(xVal) ? Math.round(xVal).toLocaleString() : "—";
    let html = `<div style="font-weight:600;margin-bottom:4px">Distance: ${distFt} ft</div>`;
    for (const p of params) {
      const pt = Array.isArray(p.value) ? p.value : Array.isArray(p.data) ? p.data : null;
      const y = pt ? pt[1] : p.value;
      const chName = labelToChannel[p.seriesName] ?? p.seriesName;
      const unit = rowUnit(chName);
      const unitStr = unit ? ` ${unit}` : "";
      const proxyTag = isProxyChannel(chName) ? (isEstimateChannel(chName) ? " (estimate)" : " (proxy)") : "";
      const display = y != null && !Number.isNaN(y) ? formatTooltipValue(chName, y) + unitStr + proxyTag : "—";
      html += `<div style="display:flex;justify-content:space-between;gap:16px">`
        + `<span style="color:${p.color}">● ${p.seriesName}</span>`
        + `<span>${display}</span></div>`;
    }
    return html;
  };
}

function rowUnit(channel: string): string {
  if (channel.includes("_pct") || channel === "throttle_pct" || channel === "brake_pct") return "%";
  if (channel.includes("_in")) return "in";
  if (channel.includes("mph")) return "mph";
  if (channel === "rpm") return "rpm";
  if (channel === "gear") return "";
  if (channel.includes("psf")) return "psf";
  if (channel.includes("deg")) return "°";
  return "";
}

function nearestIndexByFt(xs: Array<number | null>, targetFt: number): number | null {
  let bestIndex: number | null = null;
  let bestDelta = Number.POSITIVE_INFINITY;
  xs.forEach((x, index) => {
    if (x == null) return;
    const delta = Math.abs(x - targetFt);
    if (delta < bestDelta) {
      bestDelta = delta;
      bestIndex = index;
    }
  });
  return bestIndex;
}

export function PlatformTab({ overview, trace, cursor, onCursorChange }: PlatformTabProps) {
  const chartNode = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [preset, setPreset] = useState("Platform / Rake / Ride Height");
  const [platformEvents, setPlatformEvents] = useState<PlatformEventItem[]>([]);
  const [selectedPlatformEvent, setSelectedPlatformEvent] = useState<PlatformEventItem | null>(null);
  const xs = useMemo(() => xValues(trace), [trace]);

  // ── loading / empty states ──────────────────────────────────
  if (!trace) {
    return (
      <section className="platform-workbench">
        <header className="platform-header">
          <div>
            <span className="eyebrow">Platform / Aero Workbench</span>
            <h2>Platform Trace Workbench</h2>
          </div>
        </header>
        <div className="platform-loading">
          <div className="skeleton-chart">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="skeleton-row" style={{ animationDelay: `${i * 0.1}s` }} />
            ))}
          </div>
          <p className="loading-text">Loading trace data…</p>
        </div>
      </section>
    );
  }

  if (xs.length === 0) {
    return (
      <section className="platform-workbench">
        <header className="platform-header">
          <div>
            <span className="eyebrow">Platform / Aero Workbench</span>
            <h2>Platform Trace Workbench</h2>
          </div>
        </header>
        <div className="platform-empty">
          <p>Select a run and lap to view telemetry.</p>
        </div>
      </section>
    );
  }
  const legacyEvents = overview.events.filter((event) => event.event_type.startsWith("PLATFORM"));
  const rows = useMemo(() => PRESET_ROWS[preset] ?? PRESET_ROWS["Platform / Rake / Ride Height"], [preset]);

  // ── load structured platform events from API ──────────────────
  useEffect(() => {
    let cancelled = false;
    fetchPlatformEvents(overview.run_id, { lap: trace?.lap ?? undefined })
      .then((events) => { if (!cancelled) setPlatformEvents(events); })
      .catch(() => { if (!cancelled) setPlatformEvents([]); });
    return () => { cancelled = true; };
  }, [overview.run_id, trace?.lap]);

  // ── event lookup helpers ─────────────────────────────────────
  const findEvent = useCallback(
    (type: string) => platformEvents.find((e) => e.event_type === type) ?? null,
    [platformEvents],
  );

  // ── fallback raw channel scans (used when no structured event exists) ──
  const fallbackMinSplitterIndex = useMemo(() => {
    const cfs = values(trace, "cfs_ride_height_in") as number[];
    let bestIndex: number | null = null;
    let bestValue = Number.POSITIVE_INFINITY;
    cfs.forEach((value, index) => {
      if (value != null && value < bestValue) { bestIndex = index; bestValue = value; }
    });
    return bestIndex;
  }, [trace]);

  const fallbackWorstSpeedLossIndex = useMemo(() => {
    const rates = values(trace, "speed_rate_mph_s") as number[];
    let bestIndex: number | null = null;
    let bestValue = Number.POSITIVE_INFINITY;
    rates.forEach((value, index) => {
      if (value != null && value < bestValue) { bestIndex = index; bestValue = value; }
    });
    return bestIndex;
  }, [trace]);

  // ── resolve jump target from event or fallback ───────────────
  const resolveIndex = useCallback(
    (eventType: string, fallbackIndex: number | null): number | null => {
      const event = findEvent(eventType);
      if (event && event.lap_dist_ft != null) {
        return nearestIndexByFt(xs, event.lap_dist_ft);
      }
      if (event && event.sample_index != null && event.sample_index < xs.length) {
        return event.sample_index;
      }
      return fallbackIndex;
    },
    [findEvent, xs],
  );

  const minSplitterIndex = resolveIndex("MIN_SPLITTER", fallbackMinSplitterIndex);
  const worstSpeedLossIndex = resolveIndex("WORST_SPEED_LOSS", fallbackWorstSpeedLossIndex);
  const selectedIndex = cursor.selected_sample_index ?? minSplitterIndex ?? 0;

  // ── event-to-index for remaining jump buttons ────────────────
  const resolveEventIndex = useCallback(
    (eventType: string): number | null => {
      const event = findEvent(eventType);
      if (!event) return null;
      if (event.lap_dist_ft != null) return nearestIndexByFt(xs, event.lap_dist_ft);
      if (event.sample_index != null && event.sample_index < xs.length) return event.sample_index;
      return null;
    },
    [findEvent, xs],
  );

  // ── cursor management ────────────────────────────────────────
  const updateCursor = useCallback(
    (index: number | null, eventId?: string | null) => {
      if (index == null || !trace) return;
      const lapPct = valueAt(trace, "lap_dist_pct_100", index);
      const pevt = eventId ? findEvent(eventId) ?? platformEvents.find((e) => e.event_id === eventId) : null;
      onCursorChange({
        selected_run_id: overview.run_id,
        selected_lap: trace.lap ?? overview.best_useful_lap?.lap_number ?? null,
        selected_sample_index: index,
        selected_lap_dist_ft: xs[index] ?? null,
        selected_lap_pct: lapPct,
        selected_event_id: eventId ?? null,
      });
      setSelectedPlatformEvent(pevt ?? null);
    },
    [trace, overview, xs, onCursorChange, findEvent, platformEvents],
  );

  const jumpToIndex = useCallback(
    (index: number | null, eventId?: string | null) => {
      if (index == null) return;
      updateCursor(index, eventId);
      const x = xs[index];
      if (x != null && chartRef.current) {
        chartRef.current.dispatchAction({
          type: "dataZoom",
          startValue: Math.max(0, x - 200),
          endValue: x + 200,
        });
      }
    },
    [updateCursor, xs],
  );

  // ── chart ────────────────────────────────────────────────────
  useEffect(() => {
    if (!chartNode.current || !trace || xs.length === 0) return;
    const chart = echarts.init(chartNode.current, "dark");
    chartRef.current = chart;
    const ROW_H = 90;
    const ROW_GAP = 12;
    const GRID_LEFT = 80;
    const grid = rows.map((_, index) => ({
      left: GRID_LEFT,
      right: 24,
      top: 40 + index * (ROW_H + ROW_GAP),
      height: ROW_H,
    }));
    const xAxis = rows.map((_, index) => ({
      type: "value" as const,
      gridIndex: index,
      min: "dataMin",
      max: "dataMax",
      axisLabel: { show: index === rows.length - 1, color: "#8d9aaa" },
      axisLine: { lineStyle: { color: "#263241" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    }));
    const yAxis = rows.map((row, index) => ({
      type: "value" as const,
      gridIndex: index,
      min: row.min,
      max: row.max,
      axisLabel: { color: "#8d9aaa", fontSize: 10 },
      axisLine: { lineStyle: { color: "#263241" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    }));
    // horizontal row labels as ECharts graphic text
    const graphic: any[] = rows.map((row, index) => ({
      type: "text",
      left: 4,
      top: 43 + index * (ROW_H + ROW_GAP),
      style: {
        text: row.label,
        fill: "#8d9aaa",
        fontSize: 11,
        fontWeight: 600,
        fontFamily: "Inter, sans-serif",
      },
    }));
    const totalChartH = 40 + rows.length * (ROW_H + ROW_GAP) + 30;
    if (chartNode.current) {
      chartNode.current.style.height = `${totalChartH}px`;
      chartNode.current.style.minHeight = `${totalChartH}px`;
    }
    const eventLines = legacyEvents
      .map((event) => eventDistanceFt(event))
      .filter((value): value is number => value != null)
      .map((x) => ({ xAxis: x }));
    const series: SeriesOption[] = [];
    rows.forEach((row, rowIndex) => {
      row.channels.forEach((channel, channelIndex) => {
        const channelValues = values(trace, channel.name);
        const data = xs.map((x, index) => [x, channelValues[index]]);
        series.push({
          type: "line",
          name: channel.label,
          xAxisIndex: rowIndex,
          yAxisIndex: rowIndex,
          showSymbol: false,
          sampling: "lttb",
          connectNulls: false,
          lineStyle: { width: 1.35, color: channel.color, type: isProxyChannel(channel.name) ? "dashed" : "solid" },
          itemStyle: { color: channel.color },
          data,
          markLine: rowIndex === 0 && channelIndex === 0 ? {
            symbol: "none",
            label: { color: "#f59e0b", formatter: "event" },
            lineStyle: { color: "#f59e0b", type: "dashed" },
            data: eventLines,
          } : undefined,
          markArea: channel.name === "cfs_ride_height_in" ? {
            silent: true,
            itemStyle: { opacity: 0.14 },
            data: [
              [{ yAxis: 0, itemStyle: { color: "#ef4444" } }, { yAxis: 0.118, itemStyle: { color: "#ef4444" } }],
              [{ yAxis: 0.118, itemStyle: { color: "#f97316" } }, { yAxis: 0.236, itemStyle: { color: "#f97316" } }],
              [{ yAxis: 0.236, itemStyle: { color: "#f59e0b" } }, { yAxis: 0.394, itemStyle: { color: "#f59e0b" } }],
            ],
          } : undefined,
        });
      });
    });
    const option: EChartsOption = {
      backgroundColor: "transparent",
      animation: false,
      color: rows.flatMap((row) => row.channels.map((channel) => channel.color)),
      tooltip: { trigger: "axis", axisPointer: { type: "cross" }, formatter: makeTooltipFormatter(rows) },
      legend: { top: 0, right: 0, textStyle: { color: "#cbd6e3" } },
      grid,
      xAxis,
      yAxis,
      graphic,
      dataZoom: [
        { type: "inside", xAxisIndex: rows.map((_, i) => i), filterMode: "none" },
        { type: "slider", xAxisIndex: rows.map((_, i) => i), bottom: 4, height: 20, filterMode: "none" },
      ],
      toolbox: { feature: { dataZoom: { yAxisIndex: "none" }, restore: {} }, iconStyle: { borderColor: "#8d9aaa" } },
      axisPointer: { link: [{ xAxisIndex: rows.map((_, i) => i) }] },
      series,
    };
    chart.setOption(option);

    // Throttled hover — use RAF to avoid flooding React state on mousemove
    let rafId: number | null = null;
    chart.on("updateAxisPointer", (event: any) => {
      if (event.dataIndex == null) return;
      if (rafId != null) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        rafId = null;
        updateCursor(event.dataIndex);
      });
    });
    chart.on("click", (params) => {
      if (typeof params.dataIndex === "number") updateCursor(params.dataIndex);
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
      if (chartRef.current === chart) chartRef.current = null;
    };
  }, [overview.run_id, legacyEvents, trace, xs, rows, updateCursor]);

  // ── cursor readout ───────────────────────────────────────────
  const selected = {
    distanceFt: cursor.selected_lap_dist_ft ?? xs[selectedIndex] ?? null,
    lapPct: cursor.selected_lap_pct ?? valueAt(trace, "lap_dist_pct_100", selectedIndex),
    speed: valueAt(trace, "speed_mph", selectedIndex),
    throttle: valueAt(trace, "throttle_pct", selectedIndex),
    brake: valueAt(trace, "brake_pct", selectedIndex),
    cfsIn: valueAt(trace, "cfs_ride_height_in", selectedIndex),
    cfsMm: valueAt(trace, "cfs_ride_height_mm", selectedIndex),
    lf: valueAt(trace, "lf_ride_height_in", selectedIndex),
    rf: valueAt(trace, "rf_ride_height_in", selectedIndex),
    lr: valueAt(trace, "lr_ride_height_in", selectedIndex),
    rr: valueAt(trace, "rr_ride_height_in", selectedIndex),
    centerRake: valueAt(trace, "center_rake_fs_in", selectedIndex),
    sideRake: valueAt(trace, "side_rake_in", selectedIndex),
    dynamicPressure: valueAt(trace, "dynamic_pressure_psf", selectedIndex),
  };

  // ── event severity badge colour ──────────────────────────────
  const severityColour = (sev: string) =>
    sev === "critical" ? "#ef4444" : sev === "high" ? "#f97316" : sev === "watch" ? "#f59e0b" : "#38bdf8";

  // ── workbench subview ────────────────────────────────────────
  const [workbenchView, setWorkbenchView] = useState<WorkbenchView>("balance");
  const [tireMapMode, setTireMapMode] = useState<any>("pressure");

  // ── helper to get latest value ───────────────────────────────
  const latest = useCallback((ch: string) => {
    const vals = getTraceValues(trace, ch);
    return vals.length > 0 ? vals[vals.length - 1] : null;
  }, [trace]);

  // ── engineering panel renderers ──────────────────────────────
  const renderBalancePanel = () => (
    <div className="engineering-panel">
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="Front Platform Risk" channelName="front_platform_risk_score" value={latest("front_platform_risk_score")} riskValue={latest("front_platform_risk_score") as number | null} color="#38bdf8" />
        <EngineeringMetricCard title="Rear Platform Risk" channelName="rear_platform_risk_score" value={latest("rear_platform_risk_score")} riskValue={latest("rear_platform_risk_score") as number | null} color="#a78bfa" />
        <EngineeringMetricCard title="Whole-Car Bottoming" channelName="whole_car_bottoming_risk" value={latest("whole_car_bottoming_risk")} riskValue={latest("whole_car_bottoming_risk") as number | null} color="#ef4444" />
        <EngineeringMetricCard title="Platform Balance" value={safeStringValue(latest("platform_balance_label"))} subtitle={safeStringValue(latest("platform_balance_explanation"))} color="#22c55e" />
        <EngineeringMetricCard title="Rear Scrape Side" value={safeStringValue(latest("rear_scrape_side_label"))} subtitle={latest("rear_scrape_margin_mm") != null ? `${formatChannelValue(latest("rear_scrape_margin_mm") as number, "mm")} margin` : undefined} channelName="rear_scrape_side_label" color="#f59e0b" />
        <EngineeringMetricCard title="Roll Balance" value={`Front ${formatChannelValue(latest("front_platform_roll_deg_from_rh") as number, "°")} / Rear ${formatChannelValue(latest("rear_platform_roll_deg_from_rh") as number, "°")}`} subtitle={`Balance: ${formatChannelValue(latest("platform_roll_balance_deg") as number, "°")}`} channelName="platform_roll_balance_deg" color="#a78bfa" />
        <EngineeringMetricCard title="Rake / Pitch" value={`Rake ${formatChannelValue(latest("center_rake_fs_in") as number, "in")}`} subtitle={`Pitch ${formatChannelValue(latest("platform_pitch_deg_from_rh") as number, "°")}`} color="#4ade80" />
      </div>
    </div>
  );

  const renderAeroPanel = () => {
    const aeroIdx = latest("aero_load_index") as number | null;
    const dynPsf = latest("dynamic_pressure_psf") as number | null;
    const ribbonPct = aeroIdx != null ? Math.min(100, Math.max(0, (aeroIdx / 2) * 100)) : 0;
    const ribbonColor = aeroIdx != null ? (aeroIdx > 1.2 ? "#ef4444" : aeroIdx > 0.8 ? "#f59e0b" : "#22c55e") : "#475569";
    return (
    <div className="engineering-panel">
      <p className="proxy-warning">Aero/load values are telemetry-derived estimates/proxies, not direct force sensor measurements. Confidence depends on setup geometry, mass, motion ratios, and steady-state conditions.</p>
      {/* Aero Load Pressure Ribbon */}
      <div className="aero-pressure-ribbon" title={`Aero Load Index: ${aeroIdx?.toFixed(3) ?? "—"} · Dynamic Pressure: ${dynPsf?.toFixed(1) ?? "—"} psf`}>
        <span className="aero-pressure-label">Aero Load</span>
        <div className="aero-pressure-track">
          <div className="aero-pressure-fill" style={{ width: `${ribbonPct}%`, background: ribbonColor }} />
        </div>
        <span className="aero-pressure-label" style={{ color: ribbonColor }}>{aeroIdx?.toFixed(3) ?? "—"}</span>
      </div>
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="Aero Load Index" channelName="aero_load_index" value={latest("aero_load_index")} color="#38bdf8" />
        <EngineeringMetricCard title="Dynamic Pressure" value={`${formatChannelValue(latest("dynamic_pressure_psf") as number, "psf")} / ${formatChannelValue(latest("dynamic_pressure_pa") as number, "Pa")}`} subtitle={`Lap index: ${formatChannelValue(latest("dynamic_pressure_lap_index") as number, "index")}`} channelName="dynamic_pressure_lap_index" color="#60a5fa" />
        <EngineeringMetricCard title="Front Aero Proxy" channelName="front_aero_proxy_n" value={latest("front_aero_proxy_n")} color="#22d3ee" />
        <EngineeringMetricCard title="Rear Aero Proxy" channelName="rear_aero_proxy_n" value={latest("rear_aero_proxy_n")} color="#a78bfa" />
        <EngineeringMetricCard title="Rear Platform Proxy" channelName="rear_platform_proxy_n" value={latest("rear_platform_proxy_n")} subtitle={`Diffuser: ${formatForceProxyN(latest("rear_diffuser_proxy_n") as number | null)}`} color="#c084fc" />
        <EngineeringMetricCard title="Aero Balance Front" channelName="aero_balance_front_pct" value={latest("aero_balance_front_pct")} color="#22c55e" />
        <EngineeringMetricCard title="Grade Context" value={safeStringValue(latest("grade_context_label"))} subtitle={`${formatChannelValue(latest("dynamic_grade_deg") as number, "°")} · Force: ${formatForceProxyN(latest("grade_force_proxy_n") as number | null)}`} channelName="grade_context_label" color="#f59e0b" />
      </div>
    </div>
    );
  };

  const renderScrubPanel = () => (
    <div className="engineering-panel">
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="Drag/Scrub Suspicion" channelName="drag_scrub_suspicion" value={latest("drag_scrub_suspicion")} riskValue={latest("drag_scrub_suspicion") as number | null} color="#ef4444" />
        <EngineeringMetricCard title="Full-Throttle Resistance" channelName="full_throttle_resistance_index" value={latest("full_throttle_resistance_index")} riskValue={latest("full_throttle_resistance_index") as number | null} color="#f97316" />
        <EngineeringMetricCard title="Ackermann Steering Error" value={`${formatChannelValue(latest("ackermann_steering_error_deg") as number, "°")} error`} subtitle={`Expected: ${formatChannelValue(latest("ackermann_steering_expected_deg") as number, "°")} · Scrub proxy: ${formatChannelValue(latest("ackermann_scrub_proxy") as number, "proxy")}`} channelName="ackermann_scrub_proxy" color="#a78bfa" />
        <EngineeringMetricCard title="Yaw / Scrub" value={`Yaw error: ${formatChannelValue(latest("yaw_error_proxy") as number, "rad/s")}`} subtitle={`Front scrub: ${formatChannelValue(latest("front_scrub_proxy") as number, "proxy")} · Rear: ${formatChannelValue(latest("rear_scrub_proxy") as number, "proxy")}`} channelName="yaw_error_proxy" color="#38bdf8" />
        <EngineeringMetricCard title="Wheel Mismatch" value={`Front: ${formatChannelValue(latest("front_wheel_speed_mismatch_corrected") as number, "m/s")}`} subtitle={`Rear: ${formatChannelValue(latest("rear_wheel_speed_mismatch_corrected") as number, "m/s")}`} color="#f59e0b" />
        <EngineeringMetricCard title="Grade-Corrected Speed Loss" channelName="grade_corrected_speed_loss_mph_s" value={latest("grade_corrected_speed_loss_mph_s")} subtitle={`Raw: ${formatChannelValue(latest("speed_rate_mph_s") as number, "mph/s")}`} color="#22c55e" />
      </div>
      <p className="section-note" style={{ marginTop: 8 }}>Extra steering beyond track radius suggests tire scrub. Grade-corrected speed loss removes estimated uphill/downhill effect. Corrected wheel mismatch subtracts yaw-rate geometry so ovals do not look like false slip.</p>
    </div>
  );

  const renderTiresPanel = () => (
    <div className="engineering-panel">
      <CornerTireMap trace={trace} mode={tireMapMode} onModeChange={setTireMapMode} />
      <p className="section-note" style={{ marginTop: 8 }}>Inner hotter than outer may indicate camber load. Outer hotter than inner may indicate rollover, under-camber, or overdriving. Slip values are proxies unless true wheel/ground speed calibration is available.</p>
    </div>
  );

  const renderShocksPanel = () => (
    <div className="engineering-panel">
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="Shock Velocity RMS" channelName="shock_velocity_rms" value={latest("shock_velocity_rms")} riskValue={Math.min(1, (latest("shock_velocity_rms") as number ?? 0) / 5)} color="#38bdf8" />
        <EngineeringMetricCard title="Shock Activity" channelName="shock_activity_index" value={latest("shock_activity_index")} riskValue={Math.min(1, (latest("shock_activity_index") as number ?? 0) / 10)} color="#a78bfa" />
        <EngineeringMetricCard title="Damper Energy Proxy" channelName="damper_energy_proxy" value={latest("damper_energy_proxy")} color="#c084fc" />
        <EngineeringMetricCard title="Platform Stability" value={`Stability: ${formatChannelValue(latest("platform_stability_score") as number, "index")}`} subtitle={`Rake stability: ${formatChannelValue(latest("rake_stability_score") as number, "index")}`} channelName="platform_stability_score" riskValue={latest("platform_stability_score") as number | null} color="#22c55e" />
        <EngineeringMetricCard title="Platform Compression" channelName="platform_compression_index" value={latest("platform_compression_index")} riskValue={latest("platform_compression_index") as number | null} color="#f97316" />
      </div>
      <p className="section-note" style={{ marginTop: 8 }}>Frequency-domain shock analysis can later split aero oscillation from bump activity.</p>
    </div>
  );

  const renderGradePanel = () => (
    <div className="engineering-panel">
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="Grade Context" channelName="grade_context_label" value={latest("grade_context_label")} subtitle={`${formatChannelValue(latest("dynamic_grade_deg") as number, "°")}`} color="#22c55e" />
        <EngineeringMetricCard title="Grade Force Proxy" channelName="grade_force_proxy_n" value={latest("grade_force_proxy_n")} color="#f59e0b" />
        <EngineeringMetricCard title="Raw Speed Loss" value={formatChannelValue(latest("speed_rate_mph_s") as number, "mph/s")} color="#ef4444" />
        <EngineeringMetricCard title="Grade-Corrected Speed Loss" channelName="grade_corrected_speed_loss_mph_s" value={latest("grade_corrected_speed_loss_mph_s")} color="#22c55e" />
        <EngineeringMetricCard title="Pull Context" value={`${formatChannelValue(latest("speed_rate_mph_1000ft") as number, "mph/1000ft")}`} subtitle={`RPM: ${formatChannelValue(latest("rpm") as number, "rpm")} · Gear: ${latest("gear") ?? "—"}`} color="#93c5fd" />
        <EngineeringMetricCard title="Grade-Corrected Long Accel" channelName="grade_corrected_long_accel_mps2" value={latest("grade_corrected_long_accel_mps2")} color="#4ade80" />
      </div>
      <p className="section-note" style={{ marginTop: 8 }}>Raw speed loss includes slope effects. Grade-corrected speed loss estimates what remains after removing uphill/downhill gravity component. Grade values are estimates from acceleration and speed derivative, not surveyed elevation.</p>
    </div>
  );

  const renderEngineeringPanel = () => {
    switch (workbenchView) {
      case "balance": return renderBalancePanel();
      case "aero_load": return renderAeroPanel();
      case "scrub_steering": return renderScrubPanel();
      case "tires": return renderTiresPanel();
      case "shocks": return renderShocksPanel();
      case "grade_pull": return renderGradePanel();
      default: return renderBalancePanel();
    }
  };

  return (
    <section className="platform-workbench">
      <header className="platform-header">
        <div>
          <span className="eyebrow">Platform / Aero Workbench</span>
          <h2>Platform Trace Workbench</h2>
          <p className="section-note">
            Lap {trace?.lap ?? overview.best_useful_lap?.lap_number ?? "n/a"} | X Axis: Lap Distance [ft] | Preset: {preset}
          </p>
        </div>
        <div className="toolbar-actions">
          <select value={preset} onChange={(event) => setPreset(event.target.value)} aria-label="Chart preset">
            <option>Platform / Rake / Ride Height</option>
            <option>Speed / RPM / Pull</option>
            <option>Drag / Scrub</option>
            <option>Tires</option>
            <option>Shocks</option>
            <option>Engine</option>
          </select>
          <button className="secondary-button" onClick={() => chartRef.current?.dispatchAction({ type: "restore" })}>
            <RotateCcw size={16} /> Reset Zoom
          </button>
          <button className="secondary-button" onClick={() => jumpToIndex(minSplitterIndex, "MIN_SPLITTER")}>
            <LocateFixed size={16} /> Jump to Min Splitter
          </button>
          <button className="secondary-button" onClick={() => jumpToIndex(worstSpeedLossIndex, "WORST_SPEED_LOSS")}>
            <Activity size={16} /> Jump to Worst Speed Loss
          </button>
        </div>
      </header>
      <p className="proxy-warning">
        Force values are estimates/proxies derived from telemetry, setup spring rates, ride heights, shock movement, and dynamic pressure. They are not direct iRacing aerodynamic force channels.
      </p>
      <WorkbenchSubnav active={workbenchView} onChange={setWorkbenchView} />
      {renderEngineeringPanel()}
      <div className="platform-layout">
        <div className="trace-panel" ref={chartNode} />
        <aside className="cursor-panel">
          <header><Crosshair size={16} /> Cursor Readout</header>
          <dl>
            <div><dt>Lap</dt><dd>{trace?.lap ?? "n/a"}</dd></div>
            <div><dt>Distance</dt><dd>{fmt(selected.distanceFt, 0)} ft</dd></div>
            <div><dt>Position</dt><dd>{fmt(selected.lapPct, 2)}%</dd></div>
            <div><dt>Speed</dt><dd>{fmt(selected.speed, 2)} mph</dd></div>
            <div><dt>Throttle</dt><dd>{fmt(selected.throttle, 1)}%</dd></div>
            <div><dt>Brake</dt><dd>{fmt(selected.brake, 1)}%</dd></div>
            <div><dt>CFS</dt><dd>{fmt(selected.cfsIn, 3)} in / {fmt(selected.cfsMm, 2)} mm</dd></div>
            <div><dt>LF/RF</dt><dd>{fmt(selected.lf, 2)} / {fmt(selected.rf, 2)} in</dd></div>
            <div><dt>LR/RR</dt><dd>{fmt(selected.lr, 2)} / {fmt(selected.rr, 2)} in</dd></div>
            <div><dt>Center Rake FS</dt><dd>{fmt(selected.centerRake, 2)} in</dd></div>
            <div><dt>Side Rake</dt><dd>{fmt(selected.sideRake, 3)} in</dd></div>
            <div><dt>Dynamic Pressure</dt><dd>{fmt(selected.dynamicPressure, 1)} psf</dd></div>
            <div><dt>Risk</dt><dd>{riskLabel(selected.cfsIn)}</dd></div>
          </dl>
        </aside>
      </div>

      {/* ── structured platform event evidence cards ── */}
      {platformEvents.length > 0 && (
        <div className="platform-events-section">
          <h3>Platform Diagnostic Events</h3>
          <div className="event-jump-row">
            {platformEvents.map((event) => (
              <button
                className="secondary-button"
                key={event.event_id}
                onClick={() => {
                  const idx = resolveEventIndex(event.event_type);
                  jumpToIndex(idx, event.event_id);
                }}
              >
                <Activity size={16} /> {event.title}
              </button>
            ))}
          </div>
          {selectedPlatformEvent && (
            <div className="evidence-card platform-evidence-card">
              <h4>{selectedPlatformEvent.title}</h4>
              <div className="evidence-meta">
                <span style={{ color: severityColour(selectedPlatformEvent.severity) }}>
                  <AlertTriangle size={14} /> {selectedPlatformEvent.severity}
                </span>
                <span>Confidence: {selectedPlatformEvent.confidence}</span>
                {selectedPlatformEvent.is_proxy_based && <span className="proxy-badge">PROXY</span>}
              </div>
              <dl>
                <dt>Location</dt>
                <dd>
                  Lap {selectedPlatformEvent.lap ?? "n/a"}
                  {selectedPlatformEvent.lap_dist_ft != null && ` | ${selectedPlatformEvent.lap_dist_ft.toFixed(0)} ft`}
                </dd>
                {selectedPlatformEvent.primary_value != null && (
                  <>
                    <dt>Value</dt>
                    <dd>{selectedPlatformEvent.primary_value.toFixed(3)} {selectedPlatformEvent.primary_unit ?? ""}</dd>
                  </>
                )}
              </dl>
              {selectedPlatformEvent.evidence.length > 0 && (
                <>
                  <p className="evidence-title">Why it was flagged:</p>
                  <ul>
                    {selectedPlatformEvent.evidence.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
              {selectedPlatformEvent.recommended_action && (
                <p className="recommended-action">
                  <strong>Recommended:</strong> {selectedPlatformEvent.recommended_action}
                </p>
              )}
              {selectedPlatformEvent.is_proxy_based && selectedPlatformEvent.proxy_warning && (
                <p className="proxy-note">Note: {selectedPlatformEvent.proxy_warning}</p>
              )}
              {selectedPlatformEvent.channels_used.length > 0 && (
                <p className="channels-used">
                  Channels: {selectedPlatformEvent.channels_used.join(", ")}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── legacy platform events ── */}
      <div className="event-jump-row">
        {legacyEvents.map((event) => (
          <button
            className="secondary-button"
            key={event.event_id}
            onClick={() => {
              const targetFt = eventDistanceFt(event);
              if (targetFt == null) return;
              const idx = nearestIndexByFt(xs, targetFt);
              jumpToIndex(idx, event.event_id);
            }}
          >
            <Activity size={16} /> {event.event_subtype ?? event.event_type}
          </button>
        ))}
      </div>
      <div className="evidence-list">
        {legacyEvents.map((event) => (
          <EvidenceCard event={event} key={event.event_id} />
        ))}
      </div>
    </section>
  );
}
