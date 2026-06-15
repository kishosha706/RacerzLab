import * as echarts from "echarts";
import type { EChartsOption, SeriesOption } from "echarts";
import { Activity, AlertTriangle, BarChart3, Crosshair, LocateFixed, MapPin, RotateCcw, Wrench, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EvidenceCard } from "../components/EvidenceCard";
import { EngineeringMetricCard } from "../components/EngineeringMetricCard";
import { CornerTireMap } from "../components/CornerTireMap";
import { CornerBarChart } from "../components/CornerBarChart";
import { ShockHistogram } from "../components/ShockHistogram";
import type { ShockSetupField } from "../components/ShockHistogram";
import { WorkbenchSubnav } from "../components/WorkbenchSubnav";
import type { WorkbenchView } from "../components/WorkbenchSubnav";
import { ProxyBadge } from "../components/ProxyBadge";
import { fetchPlatformEvents, fetchShockReader } from "../api/client";
import { isProxyChannel, isEstimateChannel } from "../utils/channelMeta";
import { getTraceValues, formatChannelValue, formatForceProxyN, safeStringValue } from "../utils/channelFormat";
import { buildPlatformChartAnnotations } from "../utils/platformChartAnnotations";
import { filterPlatformEvents, isMutedPlatformEvent, platformEventScopeLabel } from "../utils/platformEventVisibility";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { buildWindowEvidence, buildZoneEvidence } from "../utils/evidenceFocus";
import type {
  PlatformEventItem,
  PlatformEventVisibilityMode,
  RunOverview,
  SetupSnapshot,
  TelemetryEvent,
  TraceChannelPayload,
  TraceResponse,
} from "../types/telemetry";
import type { ShockReaderResponse } from "../types/shockReader";

type PlatformTabProps = {
  overview: RunOverview;
  trace: TraceResponse | null;
  platformEvents?: PlatformEventItem[];
  initialWorkbenchView?: WorkbenchView;
  platformEventVisibilityMode?: PlatformEventVisibilityMode;
  onPlatformEventVisibilityModeChange?: (mode: PlatformEventVisibilityMode) => void;
};

type PlatformTraceWorkbenchProps = {
  overview: RunOverview;
  trace: TraceResponse;
  platformEvents?: PlatformEventItem[];
  initialWorkbenchView?: WorkbenchView;
  platformEventVisibilityMode?: PlatformEventVisibilityMode;
  onPlatformEventVisibilityModeChange?: (mode: PlatformEventVisibilityMode) => void;
};

type ChartRow = {
  label: string;
  channels: Array<{ name: string; label: string; color: string }>;
  min?: number;
  max?: number;
};

type ShockCornerKey = "lf" | "rf" | "lr" | "rr";

type ShockCornerDefinition = {
  key: ShockCornerKey;
  label: string;
  color: string;
};

type ShockPanelModel = ShockCornerDefinition & {
  samples: number[];
  setupFields: ShockSetupField[];
  unavailableReason?: string;
};

const SHOCK_BUCKET_THRESHOLD_IN_S = 1;
const SHOCK_FIXED_AXIS_LIMIT_IN_S = 10;
const SHOCK_CORNERS: ShockCornerDefinition[] = [
  { key: "lf", label: "LF", color: "#4ade80" },
  { key: "rf", label: "RF", color: "#ef4444" },
  { key: "lr", label: "LR", color: "#eab308" },
  { key: "rr", label: "RR", color: "#22d3ee" },
];

function numericTraceValues(trace: TraceResponse | null, channel: string): number[] {
  return getTraceValues(trace, channel).filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

function setupCornerNumber(setup: SetupSnapshot | null | undefined, corner: ShockCornerKey, key: string): number | null {
  const cornerValues = setup?.extracted_values?.[corner];
  if (typeof cornerValues !== "object" || cornerValues == null) return null;
  const value = (cornerValues as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatSetupClicks(value: number | null): string {
  if (value == null) return "Unavailable";
  return `${value.toFixed(0)} clk`;
}

const PRESET_ROWS: Record<string, ChartRow[]> = {
  "Platform / Rake / Ride Height": [
    { label: "CFS / LF / RF Ride Height [in]", channels: [
      { name: "cfs_ride_height_in", label: "CFS", color: "#4ade80" },
      { name: "lf_ride_height_in", label: "LF", color: "#eab308" },
      { name: "rf_ride_height_in", label: "RF", color: "#ef4444" },
    ] },
    { label: "LR / RR Ride Height [in]", channels: [
      { name: "lr_ride_height_in", label: "LR", color: "#eab308" },
      { name: "rr_ride_height_in", label: "RR", color: "#22d3ee" },
    ] },
    { label: "Front / Rear Avg RH [in]", channels: [
      { name: "front_avg_rh_in", label: "Front Avg", color: "#38bdf8" },
      { name: "rear_avg_rh_in", label: "Rear Avg", color: "#a78bfa" },
    ] },
    { label: "Center Rake [in]", channels: [{ name: "center_rake_fs_in", label: "Center Rake", color: "#4ade80" }] },
    { label: "Side Rake [in]", channels: [{ name: "side_rake_in", label: "Side Rake", color: "#f59e0b" }] },
  ],
  "Rear Scrape": [
    { label: "Rear Min / Scrape Margin [mm]", channels: [
      { name: "rear_min_ride_height_mm", label: "Rear Min", color: "#22d3ee" },
      { name: "rear_scrape_margin_mm", label: "Margin", color: "#f97316" },
    ] },
    { label: "Rear Scrape Risk", channels: [
      { name: "rear_scrape_risk_score", label: "Scrape Risk", color: "#ef4444" },
      { name: "rear_platform_contact_risk", label: "Contact Risk", color: "#f59e0b" },
    ], min: 0, max: 1 },
    { label: "Rear Ride Heights", channels: [
      { name: "lr_ride_height_mm", label: "LR", color: "#eab308" },
      { name: "rr_ride_height_mm", label: "RR", color: "#22d3ee" },
      { name: "rear_min_ride_height_in", label: "Rear Min [in]", color: "#a78bfa" },
    ] },
    { label: "CFS / Speed Context", channels: [
      { name: "cfs_ride_height_mm", label: "CFS", color: "#38bdf8" },
      { name: "speed_mph", label: "Speed", color: "#93c5fd" },
    ] },
    { label: "Throttle / Brake [%]", channels: [
      { name: "throttle_pct", label: "Throttle", color: "#22c55e" },
      { name: "brake_pct", label: "Brake", color: "#ef4444" },
    ], min: 0, max: 105 },
  ],
  "Aero Load": [
    { label: "Speed / Dynamic Pressure", channels: [
      { name: "speed_mph", label: "Speed", color: "#93c5fd" },
      { name: "dynamic_pressure_psf", label: "Dyn Pressure", color: "#38bdf8" },
    ] },
    { label: "Dynamic Pressure Index", channels: [
      { name: "dynamic_pressure_lap_index", label: "Lap Index", color: "#60a5fa" },
      { name: "dynamic_pressure_index", label: "Index", color: "#22d3ee" },
    ] },
    { label: "Aero Load Index", channels: [
      { name: "aero_load_index", label: "Aero Load", color: "#f59e0b" },
      { name: "aero_load_index_180mph", label: "180 mph Index", color: "#f97316" },
    ] },
    { label: "Front / Rear Aero Proxy [N]", channels: [
      { name: "front_aero_proxy_n", label: "Front", color: "#22d3ee" },
      { name: "rear_aero_proxy_n", label: "Rear", color: "#a78bfa" },
    ] },
    { label: "Aero Balance Front [%]", channels: [{ name: "aero_balance_front_pct", label: "Front Balance", color: "#22c55e" }] },
  ],
  "Speed / RPM / Pull": [
    { label: "Speed [mph]", channels: [{ name: "speed_mph", label: "Speed", color: "#93c5fd" }] },
    { label: "RPM", channels: [{ name: "rpm", label: "RPM", color: "#fde047" }] },
    { label: "Gear", channels: [{ name: "gear", label: "Gear", color: "#a78bfa" }] },
    { label: "Throttle / Brake [%]", channels: [{ name: "throttle_pct", label: "Throttle", color: "#22c55e" }, { name: "brake_pct", label: "Brake", color: "#ef4444" }], min: 0, max: 105 },
    { label: "Speed Rate [mph/s]", channels: [{ name: "speed_rate_mph_s", label: "Speed Rate", color: "#f59e0b" }] },
  ],
  "Drag / Scrub": [
    { label: "Drag/Scrub Risk", channels: [
      { name: "drag_scrub_suspicion", label: "Scrub Suspicion", color: "#ef4444" },
      { name: "full_throttle_resistance_index", label: "Resistance", color: "#f97316" },
      { name: "front_scrub_proxy", label: "Front Scrub", color: "#a78bfa" },
      { name: "rear_scrub_proxy", label: "Rear Scrub", color: "#38bdf8" },
    ], min: 0, max: 1 },
    { label: "Speed Loss", channels: [
      { name: "speed_rate_mph_1000ft", label: "Rate/1000ft", color: "#f97316" },
      { name: "grade_corrected_speed_loss_mph_s", label: "Grade-Corrected", color: "#22c55e" },
    ] },
    { label: "Throttle / Brake [%]", channels: [{ name: "throttle_pct", label: "Throttle", color: "#22c55e" }, { name: "brake_pct", label: "Brake", color: "#ef4444" }], min: 0, max: 105 },
    { label: "Steering [deg]", channels: [{ name: "abs_steering_deg", label: "Steering", color: "#f59e0b" }] },
    { label: "Ackermann Error / Scrub", channels: [
      { name: "ackermann_steering_expected_deg", label: "Expected", color: "#38bdf8" },
      { name: "ackermann_steering_error_deg", label: "Error", color: "#f97316" },
      { name: "ackermann_scrub_proxy", label: "Scrub Proxy", color: "#ef4444" },
    ] },
    { label: "Full-Throttle Resistance", channels: [{ name: "full_throttle_resistance_index", label: "Resistance", color: "#f59e0b" }], min: 0, max: 1 },
    { label: "Lat Accel", channels: [{ name: "abs_lat_accel", label: "Lat Accel", color: "#a78bfa" }] },
    { label: "CFS Ride Height [in]", channels: [{ name: "cfs_ride_height_in", label: "CFS", color: "#38bdf8" }] },
  ],
  "Grade / Pull": [
    { label: "Speed [mph]", channels: [{ name: "speed_mph", label: "Speed", color: "#93c5fd" }] },
    { label: "Speed Rate / Pull", channels: [
      { name: "speed_rate_mph_s", label: "mph/s", color: "#f59e0b" },
      { name: "speed_rate_mph_1000ft", label: "mph/1000ft", color: "#f97316" },
      { name: "grade_corrected_speed_loss_mph_s", label: "Grade-Corrected", color: "#22c55e" },
    ] },
    { label: "RPM / Gear", channels: [
      { name: "rpm", label: "RPM", color: "#fde047" },
      { name: "gear", label: "Gear", color: "#a78bfa" },
    ] },
    { label: "Throttle / Grade", channels: [
      { name: "throttle_pct", label: "Throttle", color: "#22c55e" },
      { name: "dynamic_grade_deg", label: "Grade", color: "#38bdf8" },
    ] },
    { label: "Grade Force Proxy", channels: [{ name: "grade_force_proxy_n", label: "Force", color: "#f59e0b" }] },
  ],
  "Tires": [
    { label: "LF Tire Temps [C]", channels: [
      { name: "lf_temp_inner", label: "Inner", color: "#4ade80" },
      { name: "lf_temp_middle", label: "Middle", color: "#22c55e" },
      { name: "lf_temp_outer", label: "Outer", color: "#16a34a" },
    ] },
    { label: "RF Tire Temps [C]", channels: [
      { name: "rf_temp_inner", label: "Inner", color: "#ef4444" },
      { name: "rf_temp_middle", label: "Middle", color: "#dc2626" },
      { name: "rf_temp_outer", label: "Outer", color: "#b91c1c" },
    ] },
    { label: "LR Tire Temps [C]", channels: [
      { name: "lr_temp_inner", label: "Inner", color: "#eab308" },
      { name: "lr_temp_middle", label: "Middle", color: "#ca8a04" },
      { name: "lr_temp_outer", label: "Outer", color: "#a16207" },
    ] },
    { label: "RR Tire Temps [C]", channels: [
      { name: "rr_temp_inner", label: "Inner", color: "#22d3ee" },
      { name: "rr_temp_middle", label: "Middle", color: "#06b6d4" },
      { name: "rr_temp_outer", label: "Outer", color: "#0891b2" },
    ] },
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
    { label: "Temp Spread [C]", channels: [
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
  "Shocks": [
    { label: "Throttle / Brake [%]", channels: [{ name: "throttle_pct", label: "Throttle", color: "#22c55e" }, { name: "brake_pct", label: "Brake", color: "#ef4444" }], min: 0, max: 105 },
    { label: "Shock Deflection [in]", channels: [
      { name: "lf_shock_defl_in", label: "LF", color: "#4ade80" },
      { name: "rf_shock_defl_in", label: "RF", color: "#ef4444" },
      { name: "lr_shock_defl_in", label: "LR", color: "#eab308" },
      { name: "rr_shock_defl_in", label: "RR", color: "#22d3ee" },
    ] },
    { label: "Shock Velocity [in/s]", channels: [
      { name: "lf_shock_vel_in_s", label: "LF", color: "#4ade80" },
      { name: "rf_shock_vel_in_s", label: "RF", color: "#ef4444" },
      { name: "lr_shock_vel_in_s", label: "LR", color: "#eab308" },
      { name: "rr_shock_vel_in_s", label: "RR", color: "#22d3ee" },
    ] },
    { label: "Shock Activity Index", channels: [
      { name: "lf_shock_activity_index", label: "LF", color: "#4ade80" },
      { name: "rf_shock_activity_index", label: "RF", color: "#ef4444" },
      { name: "lr_shock_activity_index", label: "LR", color: "#eab308" },
      { name: "rr_shock_activity_index", label: "RR", color: "#22d3ee" },
    ] },
    { label: "Damper Energy Proxy", channels: [
      { name: "lf_damper_energy_proxy", label: "LF", color: "#4ade80" },
      { name: "rf_damper_energy_proxy", label: "RF", color: "#ef4444" },
      { name: "lr_damper_energy_proxy", label: "LR", color: "#eab308" },
      { name: "rr_damper_energy_proxy", label: "RR", color: "#22d3ee" },
    ] },
  ],
  "Engine": [
    { label: "Speed [mph]", channels: [{ name: "speed_mph", label: "Speed", color: "#93c5fd" }] },
    { label: "RPM", channels: [{ name: "rpm", label: "RPM", color: "#fde047" }] },
    { label: "Gear", channels: [{ name: "gear", label: "Gear", color: "#a78bfa" }] },
    { label: "Throttle / Brake [%]", channels: [{ name: "throttle_pct", label: "Throttle", color: "#22c55e" }, { name: "brake_pct", label: "Brake", color: "#ef4444" }], min: 0, max: 105 },
    { label: "Speed Rate / Pull", channels: [
      { name: "speed_rate_mph_s", label: "Speed Rate", color: "#f59e0b" },
      { name: "speed_rate_mph_1000ft", label: "Rate/1000ft", color: "#f97316" },
      { name: "grade_corrected_speed_loss_mph_s", label: "Grade-Corrected", color: "#22c55e" },
    ] },
    { label: "Dynamic Pressure", channels: [
      { name: "dynamic_pressure_psf", label: "Pressure", color: "#38bdf8" },
      { name: "dynamic_pressure_lap_index", label: "Lap Index", color: "#60a5fa" },
    ] },
  ],
  "Rear Scrape / Scrub": [
    { label: "Rear Min / Scrape [mm]", channels: [
      { name: "rear_min_ride_height_mm", label: "Min RH", color: "#22d3ee" },
      { name: "rear_scrape_margin_mm", label: "Margin", color: "#f97316" },
    ] },
    { label: "Scrape / Contact Risk", channels: [
      { name: "rear_scrape_risk_score", label: "Scrape Risk", color: "#ef4444" },
      { name: "rear_platform_contact_risk", label: "Contact Risk", color: "#f59e0b" },
    ] },
    { label: "Scrub / Resistance", channels: [
      { name: "drag_scrub_suspicion", label: "Scrub", color: "#ef4444" },
      { name: "full_throttle_resistance_index", label: "Resistance", color: "#f97316" },
      { name: "front_scrub_proxy", label: "F-Scrub", color: "#a78bfa" },
      { name: "rear_scrub_proxy", label: "R-Scrub", color: "#38bdf8" },
    ] },
    { label: "Steering / Yaw", channels: [
      { name: "abs_steering_deg", label: "Steering", color: "#22c55e" },
      { name: "yaw_error_proxy", label: "Yaw Error", color: "#f59e0b" },
      { name: "ackermann_scrub_proxy", label: "Ackermann", color: "#a78bfa" },
    ] },
  ],
  Diffuser: [
    { label: "Ground Speed [mph]", channels: [{ name: "speed_mph", label: "Speed", color: "#22c55e" }] },
    { label: "Front Center RH [in]", channels: [{ name: "front_center_rh_in", label: "Front Center", color: "#38bdf8" }] },
    { label: "Rear Center RH [in]", channels: [{ name: "rear_center_rh_in", label: "Rear Center", color: "#a78bfa" }] },
    { label: "Smooth Diffuser Volume [ft3]", channels: [{ name: "smooth_diffuser_volume_ft3", label: "Smooth Vol", color: "#4ade80" }] },
    { label: "Diffuser Base Volume [ft3]", channels: [{ name: "diffuser_base_volume_ft3", label: "Base Vol", color: "#60a5fa" }] },
    { label: "Diffuser Wedge Volume [ft3]", channels: [{ name: "diffuser_wedge_volume_ft3", label: "Wedge Vol", color: "#f97316" }] },
    { label: "Smooth Center Rake [in]", channels: [{ name: "smooth_center_rake_in", label: "Center Rake", color: "#c084fc" }] },
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
  return trace.x.lap_dist_ft ?? trace.x_by_name?.lap_dist_ft ?? trace.x_by_name?.lap_dist_pct ?? [];
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

/** Scale a value into a 0-1 risk range, returning null for missing data. */
function scaledRisk(value: number | null | undefined, divisor: number): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return Math.min(1, Math.max(0, value / divisor));
}

function riskLabel(cfsIn: number | null | undefined) {
  if (cfsIn == null) return "Unavailable";
  if (cfsIn <= 0) return "Scrape";
  if (cfsIn <= 0.118) return "Critical";
  if (cfsIn <= 0.236) return "High";
  if (cfsIn <= 0.394) return "Watch";
  return "Safer";
}

function semanticSeverity(value: number | null | undefined): "missing" | "safe" | "watch" | "high" | "critical" {
  if (value == null || !Number.isFinite(value)) return "missing";
  if (value >= 0.85) return "critical";
  if (value >= 0.65) return "high";
  if (value >= 0.35) return "watch";
  return "safe";
}

function eventDistanceFt(event: TelemetryEvent) {
  return event.distance_m_peak == null ? null : event.distance_m_peak * 3.280839895;
}

/**
 * Compact multi-lane risk corridor SVG microchart.
 * Each lane shows risk (0–1) over lap distance as a colored heat bar.
 * Clicking a segment calls onJump(index).
 */
function RiskCorridorSVG({
  channels, trace, xs, selectedIndex, onJump, height = 60,
}: {
  channels: string[];
  trace: TraceResponse;
  xs: (number | null)[];
  selectedIndex: number | null;
  onJump: (index: number) => void;
  height?: number;
}) {
  const laneCount = channels.length;
  const laneH = Math.max(6, Math.floor((height - 4) / Math.max(laneCount, 1)));
  const totalH = 4 + laneCount * laneH;
  const w = 600;
  const pad = { left: 28, right: 8 };
  const iw = w - pad.left - pad.right;
  if (xs.length < 2) return null;

  const minX = xs[0] ?? 0;
  const maxX = xs[xs.length - 1] ?? 1;
  const xRange = Math.max(maxX - minX, 1);
  const segCount = Math.min(80, Math.max(16, Math.floor(xs.length / 6)));

  return (
    <svg width="100%" height={totalH} viewBox={`0 0 ${w} ${totalH}`} style={{ display: "block" }}>
      {channels.map((ch, laneIdx) => {
        const vals = values(trace, ch) as (number | null)[];
        const hasData = vals.some(v => typeof v === "number" && Number.isFinite(v));
        const top = 2 + laneIdx * laneH;
        return (
          <g key={ch}>
            {Array.from({ length: segCount }, (_, segIdx) => {
              const segStart = Math.floor((segIdx / segCount) * xs.length);
              const segEnd = Math.min(xs.length - 1, Math.floor(((segIdx + 1) / segCount) * xs.length));
              let segRisk: number | null = null;
              for (let i = segStart; i <= segEnd; i++) {
                const v = vals[i];
                if (typeof v === "number" && Number.isFinite(v)) segRisk = Math.max(segRisk ?? 0, v);
              }
              const x1 = pad.left + (xs[segStart]! - minX) / xRange * iw;
              const x2 = pad.left + (xs[segEnd]! - minX) / xRange * iw;
              const segSev = semanticSeverity(segRisk);
              const fill = segSev === "critical" ? "#ef4444" : segSev === "high" ? "#f97316" : segSev === "watch" ? "#f59e0b" : segSev === "safe" ? "#22c55e" : "#1f2937";
              const isSel = selectedIndex != null && selectedIndex >= segStart && selectedIndex <= segEnd;
              return (
                <rect
                  key={segIdx}
                  x={x1} y={top} width={Math.max(1, x2 - x1)} height={laneH - 1}
                  fill={hasData ? fill : "#1a1d27"}
                  stroke={isSel ? "#fff" : "none"}
                  strokeWidth={isSel ? 1 : 0}
                  rx={1}
                  style={{ cursor: "pointer" }}
                  onClick={() => onJump(Math.floor((segStart + segEnd) / 2))}
                />
              );
            })}
            <text x={2} y={top + laneH - 2} fill="#8d9aaa" fontSize={7} fontWeight={600}>
              {ch.replace(/_/g, " ").replace(/(risk|score|index)/gi, "").trim().slice(0, 12)}
            </text>
          </g>
        );
      })}
    </svg>
  );
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

/** Inline readout card shown when a trace sample is clicked. */
export function TraceSampleReadout({
  trace,
  sampleIndex,
  rows,
  onClose,
}: {
  trace: TraceResponse;
  sampleIndex: number;
  rows: ChartRow[];
  onClose: () => void;
}) {
  const xs = xValues(trace);
  const distFt = xs[sampleIndex];
  const distStr = distFt != null && !Number.isNaN(distFt) ? `${Math.round(distFt).toLocaleString()} ft` : "—";
  return (
    <div className="trace-sample-readout">
      <div className="readout-header">
        <span className="readout-title">Sample Readout</span>
        <button className="readout-close" onClick={onClose} aria-label="Close readout" title="Close (Esc)">
          <X size={14} />
        </button>
      </div>
      <div className="readout-distance">{distStr}</div>
      <div className="readout-rows">
        {rows.map((row) => (
          <div key={row.label} className="readout-row-group">
            <div className="readout-row-label">{row.label}</div>
            {row.channels.map((ch) => {
              const raw = values(trace, ch.name)[sampleIndex];
              const numVal = typeof raw === "number" ? raw : null;
              const display = numVal != null && !Number.isNaN(numVal)
                ? formatTooltipValue(ch.name, numVal) + (rowUnit(ch.name) ? ` ${rowUnit(ch.name)}` : "")
                : "—";
              return (
                <div key={ch.name} className="readout-channel">
                  <span className="readout-bullet" style={{ color: ch.color }}>●</span>
                  <span className="readout-channel-label">{ch.label}</span>
                  <span className="readout-channel-value">
                    {display}
                    {isProxyChannel(ch.name) && (
                      <span style={{ marginLeft: 6 }}>
                        <ProxyBadge kind={isEstimateChannel(ch.name) ? "estimate" : "proxy"} />
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
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

function nearestIndexByPct(trace: TraceResponse | null, targetPct: number): number | null {
  const pctValues = values(trace, "lap_dist_pct_100") as Array<number | null>;
  let bestIndex: number | null = null;
  let bestDelta = Number.POSITIVE_INFINITY;
  pctValues.forEach((pct, index) => {
    if (pct == null || !Number.isFinite(pct)) return;
    const delta = Math.abs(pct - targetPct);
    if (delta < bestDelta) {
      bestDelta = delta;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function validSampleIndex(index: number | null | undefined, length: number): number | null {
  if (index == null || !Number.isInteger(index)) return null;
  if (index < 0 || index >= length) return null;
  return index;
}

export function PlatformTab({
  overview,
  trace,
  platformEvents,
  initialWorkbenchView,
  platformEventVisibilityMode,
  onPlatformEventVisibilityModeChange,
}: PlatformTabProps) {
  const xs = useMemo(() => xValues(trace), [trace]);

  if (!trace) {
    return (
      <section className="platform-workbench">
        <header className="platform-header">
          <div>
            <span className="eyebrow">Platform / Aero Workbench</span>
            <h2>Platform Trace Workbench</h2>
          </div>
        </header>
        <div className="platform-empty">
          <p className="loading-text">Loading trace data...</p>
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

  return (
    <PlatformTraceWorkbench
      overview={overview}
      trace={trace}
      platformEvents={platformEvents}
      initialWorkbenchView={initialWorkbenchView}
      platformEventVisibilityMode={platformEventVisibilityMode}
      onPlatformEventVisibilityModeChange={onPlatformEventVisibilityModeChange}
    />
  );
}

function PlatformTraceWorkbench({
  overview,
  trace,
  platformEvents: externalPlatformEvents,
  initialWorkbenchView = "balance",
  platformEventVisibilityMode = "actionable",
  onPlatformEventVisibilityModeChange,
}: PlatformTraceWorkbenchProps) {
  const { selection, setWorkspace, focusEvidence } = useTelemetrySelection();
  const chartNode = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const cursorLineRef = useRef<HTMLDivElement | null>(null);
  const clickedSampleIndexRef = useRef<number | null>(null);
  const hoverSampleIndexRef = useRef<number | null>(null);
  const zoomRangeRef = useRef<{ startValue?: number; endValue?: number } | null>(null);
  const latestXsRef = useRef<Array<number | null>>([]);
  const gridLeftRef = useRef(100);
  const updateCursorRef = useRef<(index: number | null, eventId?: string | null) => void>(() => {});
  const showCursorLineRef = useRef<(offsetX: number, locked: boolean) => void>(() => {});
  const hideCursorLineRef = useRef<() => void>(() => {});
  const commitHoverSampleRef = useRef<(index: number | null) => void>(() => {});
  const hoverRafRef = useRef<number | null>(null);
  const pendingHoverSampleIndexRef = useRef<number | null>(null);
  const lastHoverCommitRef = useRef(0);
  const [platformEvents, setPlatformEvents] = useState<PlatformEventItem[]>([]);
  const [shockReader, setShockReader] = useState<ShockReaderResponse | null>(null);
  const [selectedPlatformEvent, setSelectedPlatformEvent] = useState<PlatformEventItem | null>(null);
  const [clickedSampleIndex, setClickedSampleIndex] = useState<number | null>(null);
  const [hoverSampleIndex, setHoverSampleIndex] = useState<number | null>(null);
  const [tireMapMode, setTireMapMode] = useState<any>("pressure");
  const normalizedInitialView = initialWorkbenchView === "scrub_steering" ? "rear_scrape" : initialWorkbenchView;
  const [workbenchView, setWorkbenchView] = useState<WorkbenchView>(normalizedInitialView);
  useEffect(() => {
    setWorkbenchView(normalizedInitialView);
  }, [normalizedInitialView]);

  const presetFromView: Record<WorkbenchView, string> = {
    balance: "Platform / Rake / Ride Height",
    rear_scrape: "Rear Scrape / Scrub",
    aero_load: "Aero Load",
    scrub_steering: "Rear Scrape / Scrub",
    tires: "Tires",
    shocks: "Shocks",
    grade_pull: "Grade / Pull",
    diffuser: "Diffuser",
  };
  const preset = presetFromView[workbenchView] ?? "Platform / Rake / Ride Height";
  const presetRef = useRef(preset);
  useEffect(() => {
    presetRef.current = preset;
  }, [preset]);
  const handleViewChange = useCallback((view: WorkbenchView) => {
    setWorkbenchView(view);
    setHoverSampleIndex(null);
  }, [setWorkbenchView, setHoverSampleIndex]);
  const xs = useMemo(() => xValues(trace), [trace]);

  useEffect(() => {
    latestXsRef.current = xs;
  }, [xs]);

  useEffect(() => {
    clickedSampleIndexRef.current = clickedSampleIndex;
  }, [clickedSampleIndex]);

  useEffect(() => {
    hoverSampleIndexRef.current = hoverSampleIndex;
  }, [hoverSampleIndex]);

  const legacyEvents = useMemo(
    () => overview.events.filter((event) => event.event_type.startsWith("PLATFORM")),
    [overview.events],
  );
  const rows = useMemo(() => PRESET_ROWS[preset] ?? PRESET_ROWS["Platform / Rake / Ride Height"], [preset]);
  const rowsRef = useRef<ChartRow[]>(rows);
  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);
  const windowContextActive = selection.selectedLapScope === "lap_window"
    && selection.selectedLapWindowStart != null
    && selection.selectedLapWindowEnd != null;
  const representativeLap = selection.selectedRepresentativeLap ?? trace?.lap ?? selection.selectedLap ?? null;
  const windowLapNumbers = useMemo(() => {
    if (!windowContextActive) return [];
    return overview.laps
      .filter((lap) =>
        lap.lap_number >= (selection.selectedLapWindowStart ?? -Infinity)
        && lap.lap_number <= (selection.selectedLapWindowEnd ?? Infinity))
      .map((lap) => lap.lap_number);
  }, [overview.laps, selection.selectedLapWindowEnd, selection.selectedLapWindowStart, windowContextActive]);
  const representativeLapIndex = representativeLap != null ? windowLapNumbers.indexOf(representativeLap) : -1;
  const shockReaderLapWindow = windowContextActive
    ? `${selection.selectedLapWindowStart}-${selection.selectedLapWindowEnd}`
    : null;

  useEffect(() => {
    let cancelled = false;
    if (workbenchView !== "shocks") return;
    fetchShockReader(overview.run_id, {
      lap: shockReaderLapWindow ? null : trace?.lap ?? representativeLap,
      lapWindow: shockReaderLapWindow,
      boundaryInS: SHOCK_BUCKET_THRESHOLD_IN_S,
      includeDebug: false,
    })
      .then((payload) => {
        if (!cancelled) setShockReader(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setShockReader(null);
        }
      })
    return () => {
      cancelled = true;
    };
  }, [overview.run_id, representativeLap, shockReaderLapWindow, trace?.lap, workbenchView]);

  const buildTraceEvidence = useCallback((
    lapNumber: number | null,
    lapPct: number | null,
    sampleIndex: number | null,
    lapDistFt: number | null,
    eventId: string | null,
  ) => ({
    runId: overview.run_id,
    lapNumber,
    ...buildWindowEvidence(selection, lapNumber),
    ...buildZoneEvidence(selection, { lapPct, preserveWithoutLapPct: true }),
    eventId,
    sampleIndex,
    lapDistFt,
    lapPct,
    trustTier: selection.selectedTrustTier ?? null,
  }), [overview.run_id, selection]);

  // ── load structured platform events from API (or use external prop) ──
  useEffect(() => {
    if (externalPlatformEvents) {
      setPlatformEvents(externalPlatformEvents);
      return;
    }
    let cancelled = false;
    fetchPlatformEvents(overview.run_id, { lap: trace?.lap ?? undefined })
      .then((events) => { if (!cancelled) setPlatformEvents(events); })
      .catch(() => { if (!cancelled) setPlatformEvents([]); });
    return () => { cancelled = true; };
  }, [overview.run_id, trace?.lap, externalPlatformEvents]);

  const visiblePlatformEvents = useMemo(
    () => filterPlatformEvents(platformEvents, platformEventVisibilityMode),
    [platformEvents, platformEventVisibilityMode],
  );

  useEffect(() => {
    if (
      selectedPlatformEvent
      && !visiblePlatformEvents.some((event) => event.event_id === selectedPlatformEvent.event_id)
    ) {
      setSelectedPlatformEvent(null);
    }
  }, [selectedPlatformEvent, visiblePlatformEvents]);

  // ── event lookup helpers ─────────────────────────────────────
  const findEvent = useCallback(
    (reference?: string | null) => {
      if (!reference) return null;
      return visiblePlatformEvents.find((event) => event.event_id === reference)
        ?? visiblePlatformEvents.find((event) => event.event_type === reference)
        ?? null;
    },
    [visiblePlatformEvents],
  );

  const indexForPlatformEvent = useCallback(
    (event: PlatformEventItem | null): number | null => {
      if (!event) return null;
      if (event.lap_dist_ft != null) {
        return nearestIndexByFt(xs, event.lap_dist_ft);
      }
      const si = validSampleIndex(event.sample_index, xs.length);
      if (si != null) return si;
      if (event.lap_pct != null) {
        return nearestIndexByPct(trace, event.lap_pct);
      }
      return null;
    },
    [trace, xs],
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
      return indexForPlatformEvent(event) ?? fallbackIndex;
    },
    [findEvent, indexForPlatformEvent],
  );

  const minSplitterIndex = resolveIndex("MIN_SPLITTER", fallbackMinSplitterIndex);
  const worstSpeedLossIndex = resolveIndex("WORST_SPEED_LOSS", fallbackWorstSpeedLossIndex);
  const playbackIndex = selection.playbackActive
    ? validSampleIndex(selection.hoverSampleIndex, xs.length)
      ?? (selection.hoverLapPct != null ? nearestIndexByPct(trace, selection.hoverLapPct) : null)
    : null;
  const lockedIndex = validSampleIndex(clickedSampleIndex, xs.length);
  const transientHoverIndex = validSampleIndex(hoverSampleIndex, xs.length);
  const cursorIndex = validSampleIndex(selection.selectedSampleIndex, xs.length);
  const selectedEventForContext = findEvent(selection.selectedEventId);
  const selectedEventContextIndex = indexForPlatformEvent(selectedEventForContext);
  const selectedContextIndex = selection.selectedLapDistFt != null
    ? nearestIndexByFt(xs, selection.selectedLapDistFt)
    : selection.selectedLapPct != null
      ? nearestIndexByPct(trace, selection.selectedLapPct)
      : validSampleIndex(selection.selectedSampleIndex, xs.length) ?? selectedEventContextIndex;
  // Prefer selection context over shell cursor — selection is the canonical source
  const defaultIndex = selectedContextIndex ?? cursorIndex ?? minSplitterIndex ?? 0;
  const selectedIndex = playbackIndex ?? lockedIndex ?? transientHoverIndex ?? defaultIndex;
  const readoutSource = playbackIndex != null
    ? "Playback"
    : lockedIndex != null
      ? "Locked"
      : transientHoverIndex != null
        ? "Hover"
        : selection.selectedEventId
          ? "Event"
          : "Default";

  // ── nearest event for cursor index ───────────────────────────

  const nearestEventForIndex = useCallback(
    (index: number | null): PlatformEventItem | null => {
      if (index == null) return null;
      const dist = xs[index];
      const pct = valueAt(trace, "lap_dist_pct_100", index);
      let best: PlatformEventItem | null = null;
      let bestScore = Number.POSITIVE_INFINITY;
      for (const event of visiblePlatformEvents) {
        let score = Number.POSITIVE_INFINITY;
        if (dist != null && event.lap_dist_ft != null) {
          score = Math.abs(dist - event.lap_dist_ft);
          if (score > 120) continue;
        } else if (pct != null && event.lap_pct != null) {
          score = Math.abs(pct - event.lap_pct) * 40;
          if (score > 20) continue;
        } else if (event.sample_index != null) {
          score = Math.abs(index - event.sample_index);
          if (score > 15) continue;
        }
        if (score < bestScore) {
          bestScore = score;
          best = event;
        }
      }
      return best;
    },
    [trace, visiblePlatformEvents, xs],
  );

  // ── cursor management ────────────────────────────────────────
  const updateCursor = useCallback(
    (index: number | null, eventId?: string | null) => {
      if (index == null || !trace) return;
      const lapPct = valueAt(trace, "lap_dist_pct_100", index);
      const pevt = eventId
        ? findEvent(eventId)
        : nearestEventForIndex(index);
      focusEvidence({
        ...buildTraceEvidence(
          trace.lap ?? overview.best_useful_lap?.lap_number ?? null,
          lapPct,
          index,
          xs[index] ?? null,
          pevt?.event_id ?? eventId ?? null,
        ),
        sampleIndex: index,
        lockState: "locked",
        valueBasis: "selected_sample",
        selectionSource: "trace_cursor",
      });
      setSelectedPlatformEvent(pevt ?? null);
    },
    [trace, overview, xs, focusEvidence, findEvent, visiblePlatformEvents, nearestEventForIndex, buildTraceEvidence],
  );

  const jumpToIndex = useCallback(
    (index: number | null, eventId?: string | null) => {
      if (index == null) return;
      setClickedSampleIndex(index);
      setHoverSampleIndex(null);
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

  const focusRepresentativeLap = useCallback((lapNumber: number) => {
    if (!windowContextActive) return;
    focusEvidence({
      ...buildTraceEvidence(lapNumber, null, null, null, null),
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      selectionSource: "manual",
      lockState: "none",
      valueBasis: "selected_window",
    }, "platform_trace");
    setClickedSampleIndex(null);
    setHoverSampleIndex(null);
    setSelectedPlatformEvent(null);
  }, [focusEvidence, buildTraceEvidence, windowContextActive]);

  useEffect(() => {
    if (!trace || xs.length === 0 || selection.selectionSource === "trace_cursor") return;
    const eventFromSelection = findEvent(selection.selectedEventId);
    const indexFromSelection = selection.selectedLapDistFt != null
      ? nearestIndexByFt(xs, selection.selectedLapDistFt)
      : selection.selectedLapPct != null
        ? nearestIndexByPct(trace, selection.selectedLapPct)
        : validSampleIndex(selection.selectedSampleIndex, xs.length)
          ?? indexForPlatformEvent(eventFromSelection);

    if (indexFromSelection == null) return;
    setClickedSampleIndex(indexFromSelection);
    setHoverSampleIndex(null);

    const event = eventFromSelection ?? nearestEventForIndex(indexFromSelection);
    setSelectedPlatformEvent(event);
  }, [
    trace,
    xs,
    selection.selectionSource,
    selection.selectedSampleIndex,
    selection.selectedLapDistFt,
    selection.selectedLapPct,
    selection.selectedEventId,
    visiblePlatformEvents,
    nearestEventForIndex,
    findEvent,
    indexForPlatformEvent,
  ]);

  const showCursorLine = useCallback((offsetX: number, locked: boolean) => {
    const line = cursorLineRef.current;
    const node = chartNode.current;
    if (!line || !node) return;
    const boundedX = Math.max(0, Math.min(offsetX, node.clientWidth));
    line.hidden = false;
    line.dataset.locked = locked ? "true" : "false";
    line.style.transform = `translateX(${boundedX}px)`;
  }, []);

  const hideCursorLine = useCallback(() => {
    if (cursorLineRef.current) {
      cursorLineRef.current.hidden = true;
      cursorLineRef.current.dataset.locked = "false";
    }
  }, []);

  const positionCursorLineForIndex = useCallback(
    (index: number | null, locked: boolean) => {
      const chart = chartRef.current;
      if (index == null || !chart) return;
      const x = xs[index];
      if (x == null || !Number.isFinite(x)) return;
      const pixel = chart.convertToPixel({ xAxisIndex: 0 }, [x, 0]);
      const offsetX = Array.isArray(pixel) ? pixel[0] : pixel;
      if (typeof offsetX === "number" && Number.isFinite(offsetX)) {
        showCursorLine(offsetX, locked);
      }
    },
    [showCursorLine, xs],
  );
  const positionCursorLineForIndexRef = useRef(positionCursorLineForIndex);
  useEffect(() => {
    positionCursorLineForIndexRef.current = positionCursorLineForIndex;
  }, [positionCursorLineForIndex]);

  const commitHoverSample = useCallback((index: number | null) => {
    pendingHoverSampleIndexRef.current = index;
    if (hoverRafRef.current != null) return;
    hoverRafRef.current = requestAnimationFrame(() => {
      hoverRafRef.current = null;
      const nextIndex = pendingHoverSampleIndexRef.current;
      if (nextIndex === hoverSampleIndexRef.current) return;
      const now = performance.now();
      if (now - lastHoverCommitRef.current < 80) return;
      lastHoverCommitRef.current = now;
      setHoverSampleIndex(nextIndex);
    });
  }, []);

  useEffect(() => {
    if (readoutSource === "Default" && clickedSampleIndex == null && hoverSampleIndex == null) return;
    positionCursorLineForIndex(selectedIndex, readoutSource === "Locked");
  }, [clickedSampleIndex, hoverSampleIndex, positionCursorLineForIndex, readoutSource, selectedIndex, preset]);

  // ── jump button click flash ──────────────────────────────────
  const [jumpedBtn, setJumpedBtn] = useState<string | null>(null);
  const handleJumpClick = useCallback((label: string, index: number | null, eventId?: string | null) => {
    jumpToIndex(index, eventId);
    setJumpedBtn(label);
    setTimeout(() => setJumpedBtn(null), 350);
  }, [jumpToIndex]);

  // ── chart lifecycle ──────────────────────────────────────────
  useEffect(() => {
    updateCursorRef.current = updateCursor;
    showCursorLineRef.current = showCursorLine;
    hideCursorLineRef.current = hideCursorLine;
    commitHoverSampleRef.current = commitHoverSample;
  }, [commitHoverSample, hideCursorLine, showCursorLine, updateCursor]);

  useEffect(() => {
    const node = chartNode.current;
    if (!node) return;
    const chart = echarts.init(node, "dark");
    chartRef.current = chart;

    const GRID_RIGHT = 36;
    const GRID_TOP = 50;

    const indexFromPoint = (offsetX: number, offsetY: number): number | null => {
      if (!Number.isFinite(offsetX) || !Number.isFinite(offsetY)) return null;
      const xsRef = latestXsRef.current;
      if (xsRef.length === 0) return null;
      const gl = gridLeftRef.current;
      const right = node.clientWidth - GRID_RIGHT;
      if (right <= gl || offsetX < gl || offsetX > right) return null;

      // Y hit-test: is cursor inside any row grid?
      const sectionRowConfigH: Record<string, { height: number; gap: number }> = {
        "Platform / Rake / Ride Height": { height: 100, gap: 12 },
        "Rear Scrape / Scrub": { height: 104, gap: 12 },
        "Aero Load": { height: 104, gap: 12 },
        "Tires": { height: 130, gap: 12 },
        "Shocks": { height: 120, gap: 12 },
        "Grade / Pull": { height: 104, gap: 12 },
        "Diffuser": { height: 104, gap: 12 },
      };
      const cfg = sectionRowConfigH[presetRef.current] ?? { height: 100, gap: 12 };
      const ROW_H = cfg.height; const ROW_GAP = cfg.gap; const nRows = rowsRef.current.length;
      let insideGrid = false;
      for (let i = 0; i < nRows; i++) {
        const top = GRID_TOP + i * (ROW_H + ROW_GAP);
        if (offsetY >= top && offsetY <= top + ROW_H) { insideGrid = true; break; }
      }
      if (!insideGrid) return null;

      const ratio = (offsetX - gl) / (right - gl);
      const finiteXs = xsRef.filter((x): x is number => typeof x === "number" && Number.isFinite(x));
      if (finiteXs.length === 0) return null;
      const minX = finiteXs[0];
      const maxX = finiteXs[finiteXs.length - 1];
      const zoom = (chart.getOption().dataZoom as any[] | undefined)?.[0] ?? {};
      const startValue = typeof zoom.startValue === "number"
        ? zoom.startValue
        : minX + ((typeof zoom.start === "number" ? zoom.start : 0) / 100) * (maxX - minX);
      const endValue = typeof zoom.endValue === "number"
        ? zoom.endValue
        : minX + ((typeof zoom.end === "number" ? zoom.end : 100) / 100) * (maxX - minX);
      return nearestIndexByFt(xsRef, startValue + ratio * (endValue - startValue));
    };

    // Single pointer path: DOM pointer events only
    const handlePointerMove = (event: PointerEvent) => {
      const rect = node.getBoundingClientRect();
      const ox = event.clientX - rect.left;
      const oy = event.clientY - rect.top;
      const index = indexFromPoint(ox, oy);
      if (index == null) {
        if (clickedSampleIndexRef.current == null) {
          commitHoverSampleRef.current(null);
          hideCursorLineRef.current();
        }
        return;
      }
      showCursorLineRef.current(ox, clickedSampleIndexRef.current != null);
      if (clickedSampleIndexRef.current == null) {
        commitHoverSampleRef.current(index);
      }
    };

    const handlePointerDown = (event: PointerEvent) => {
      const rect = node.getBoundingClientRect();
      const ox = event.clientX - rect.left;
      const oy = event.clientY - rect.top;
      const index = indexFromPoint(ox, oy);
      if (index == null) return;
      setClickedSampleIndex(index);
      setHoverSampleIndex(null);
      updateCursorRef.current(index);
      showCursorLineRef.current(ox, true);
    };

    const handlePointerLeave = () => {
      if (clickedSampleIndexRef.current == null) {
        commitHoverSampleRef.current(null);
        hideCursorLineRef.current();
      }
    };

    // ResizeObserver for responsive sizing
    const ro = new ResizeObserver(() => {
      if (!chartNode.current || chart.isDisposed()) return;
      chart.resize({ width: chartNode.current.clientWidth, height: chartNode.current.clientHeight });
      const idx = clickedSampleIndexRef.current ?? hoverSampleIndexRef.current;
      if (idx != null) positionCursorLineForIndexRef.current(idx, clickedSampleIndexRef.current != null);
    });
    ro.observe(node);

    const handleDataZoom = () => {
      const zoom = (chart.getOption().dataZoom as any[] | undefined)?.[0] ?? {};
      zoomRangeRef.current = {
        startValue: typeof zoom.startValue === "number" ? zoom.startValue : undefined,
        endValue: typeof zoom.endValue === "number" ? zoom.endValue : undefined,
      };
    };

    chart.on("datazoom", handleDataZoom);
    node.addEventListener("pointermove", handlePointerMove);
    node.addEventListener("pointerdown", handlePointerDown);
    node.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      ro.disconnect();
      chart.off("datazoom", handleDataZoom);
      node.removeEventListener("pointermove", handlePointerMove);
      node.removeEventListener("pointerdown", handlePointerDown);
      node.removeEventListener("pointerleave", handlePointerLeave);
      if (hoverRafRef.current != null) {
        cancelAnimationFrame(hoverRafRef.current);
        hoverRafRef.current = null;
      }
      chart.dispose();
      if (chartRef.current === chart) chartRef.current = null;
    };
  }, []);;

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !chartNode.current) return;

    const sectionRowConfig: Record<string, { height: number; gap: number }> = {
      "Platform / Rake / Ride Height": { height: 100, gap: 12 },
      "Rear Scrape / Scrub": { height: 104, gap: 12 },
      "Aero Load": { height: 104, gap: 12 },
      "Diffuser": { height: 104, gap: 12 },
      "Tires": { height: 130, gap: 12 },
      "Shocks": { height: 120, gap: 12 },
      "Grade / Pull": { height: 104, gap: 12 },
    };
    const config = sectionRowConfig[preset] ?? { height: 100, gap: 12 };
    const ROW_H = config.height;
    const ROW_GAP = config.gap;
    const isTires = preset === "Tires";
    const GRID_LEFT = isTires ? 130 : 100;
    const LABEL_LEFT = 4;
    gridLeftRef.current = GRID_LEFT;
    const GRID_RIGHT = 36;

    const grid = rows.map((_, index) => ({
      left: GRID_LEFT,
      right: GRID_RIGHT,
      top: 50 + index * (ROW_H + ROW_GAP),
      height: ROW_H,
    }));
    const xAxis = rows.map((_, index) => ({
      type: "value" as const,
      gridIndex: index,
      min: "dataMin",
      max: "dataMax",
      scale: isTires,
      axisLabel: { show: index === rows.length - 1, color: "#8d9aaa", fontSize: 10 },
      axisLine: { lineStyle: { color: "#263241" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    }));
    const yAxis = rows.map((row, index) => ({
      type: "value" as const,
      gridIndex: index,
      min: row.min,
      max: row.max,
      scale: isTires,
      axisLabel: { color: "#8d9aaa", fontSize: 10 },
      axisLine: { lineStyle: { color: "#263241" } },
      splitLine: { lineStyle: { color: "#1f2937" } },
    }));

    const graphic: any[] = [];
    rows.forEach((row, index) => {
      const top = 50 + index * (ROW_H + ROW_GAP);
      graphic.push({
        type: "line",
        shape: { x1: GRID_LEFT, y1: top, x2: 9999, y2: top },
        style: { stroke: "rgba(31,41,55,0.5)", lineWidth: 1 },
        silent: true,
        z: 1,
      });
      graphic.push({
        type: "rect",
        left: 0,
        right: 0,
        top,
        height: ROW_H,
        style: { fill: "rgba(15,17,23,0.5)", opacity: 1 },
        silent: true,
        z: 0,
      });
      graphic.push({
        type: "line",
        shape: { x1: GRID_LEFT, y1: top, x2: GRID_LEFT, y2: top + ROW_H },
        style: { stroke: "rgba(31,41,55,0.4)", lineWidth: 1 },
        silent: true,
        z: 1,
      });
      graphic.push({
        type: "text",
        left: LABEL_LEFT,
        top: top + 6,
        style: {
          text: row.label,
          fill: "#8d9aaa",
          fontSize: 10,
          fontWeight: 600,
          fontFamily: "Inter, sans-serif",
          lineWidth: 0,
        },
        z: 2,
      });
    });

    if (rows.length > 0) {
      const lastTop = 50 + (rows.length - 1) * (ROW_H + ROW_GAP);
      graphic.push({
        type: "line",
        shape: { x1: GRID_LEFT, y1: lastTop + ROW_H, x2: 9999, y2: lastTop + ROW_H },
        style: { stroke: "rgba(31,41,55,0.5)", lineWidth: 1 },
        silent: true,
        z: 1,
      });
    }

    const totalChartH = 50 + rows.length * (ROW_H + ROW_GAP) + 34;
    chartNode.current.style.height = `${totalChartH}px`;
    chartNode.current.style.minHeight = `${totalChartH}px`;

    const eventAnnotations = buildPlatformChartAnnotations({
      platformEvents,
      legacyEvents,
      mode: platformEventVisibilityMode,
    });

    const series: SeriesOption[] = [];
    rows.forEach((row, rowIndex) => {
      row.channels.forEach((channel, channelIndex) => {
        const channelValues = values(trace, channel.name);
        const data = xs.map((x, index) => [x, channelValues[index]]);
        let lineType: "solid" | "dashed" | "dotted" = "solid";
        if (preset === "Tires") {
          const label = channel.label.toLowerCase();
          if (label === "inner") lineType = "solid";
          else if (label === "middle") lineType = "dashed";
          else if (label === "outer") lineType = "dotted";
        }
        if (isProxyChannel(channel.name)) lineType = "dashed";
        series.push({
          type: "line",
          name: channel.label,
          xAxisIndex: rowIndex,
          yAxisIndex: rowIndex,
          showSymbol: false,
          sampling: "lttb",
          connectNulls: false,
          lineStyle: { width: 1.35, color: channel.color, type: lineType },
          itemStyle: { color: channel.color },
          data,
          markLine: rowIndex === 0 && channelIndex === 0 ? {
            symbol: "none",
            label: { show: eventAnnotations.showLineLabels, color: "#f59e0b" },
            lineStyle: { color: "#f59e0b", type: "dashed" },
            data: eventAnnotations.markLines,
          } : undefined,
          markArea: channel.name === "cfs_ride_height_in" ? {
            silent: true,
            itemStyle: { opacity: 0.14 },
            data: [
              [{ yAxis: 0, itemStyle: { color: "#ef4444" } }, { yAxis: 0.118, itemStyle: { color: "#ef4444" } }],
              [{ yAxis: 0.118, itemStyle: { color: "#f97316" } }, { yAxis: 0.236, itemStyle: { color: "#f97316" } }],
              [{ yAxis: 0.236, itemStyle: { color: "#f59e0b" } }, { yAxis: 0.394, itemStyle: { color: "#f59e0b" } }],
            ],
          } : (rowIndex === 0 && channelIndex === 0 && eventAnnotations.markAreas.length > 0 ? {
            silent: true,
            data: eventAnnotations.markAreas.map((area) => [
              { xAxis: area.xAxis, itemStyle: { color: area.color, opacity: area.opacity } },
              { xAxis: area.xAxis + 50, itemStyle: { color: area.color, opacity: area.opacity } },
            ]),
          } : undefined),
        });
      });
    });

    const option: EChartsOption = {
      backgroundColor: "transparent",
      animation: false,
      color: rows.flatMap((row) => row.channels.map((channel) => channel.color)),
      tooltip: { show: false, trigger: "none", axisPointer: { type: "cross" } },
      legend: {
        type: "scroll",
        top: 0,
        left: 18,
        right: 18,
        data: rows.flatMap((row) => row.channels.map((channel) => channel.label)),
        itemWidth: 10,
        itemHeight: 8,
        itemGap: 10,
        textStyle: { color: "#cbd6e3", fontSize: 11 },
        pageIconColor: "#38bdf8",
        pageIconInactiveColor: "#334155",
        pageTextStyle: { color: "#8d9aaa" },
      },
      grid,
      xAxis,
      yAxis,
      graphic,
      dataZoom: [
        { type: "slider", xAxisIndex: rows.map((_, i) => i), bottom: 0, height: 14, filterMode: "none",
          borderColor: "#1f2937", backgroundColor: "rgba(15,17,23,0.6)", fillerColor: "rgba(59,130,246,0.15)",
          handleStyle: { color: "#3b82f6", borderColor: "#3b82f6" },
          textStyle: { color: "#7d8a99", fontSize: 9 },
          labelFormatter: (value: number) => `${Math.round(value).toLocaleString()} ft`,
          showDetail: false,
          ...(zoomRangeRef.current ?? {}),
        },
      ],
      toolbox: { feature: { dataZoom: { yAxisIndex: "none" }, restore: {} }, iconStyle: { borderColor: "#8d9aaa" } },
      axisPointer: { link: [{ xAxisIndex: rows.map((_, i) => i) }], snap: false },
      series,
    };
    chart.setOption(option, { notMerge: false, lazyUpdate: true, replaceMerge: ["series", "legend", "xAxis", "yAxis", "grid", "graphic"] });
    chart.resize();

    // Reposition locked cursor after chart re-render to match new grid layout
    const lockedSampleIdx = clickedSampleIndexRef.current;
    if (lockedSampleIdx != null) {
      positionCursorLineForIndexRef.current(lockedSampleIdx, true);
    }
  }, [legacyEvents, platformEventVisibilityMode, platformEvents, preset, rows, trace, xs]);

  // ── Escape key clears clicked sample ─────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (clickedSampleIndexRef.current != null) {
        setClickedSampleIndex(null);
        setHoverSampleIndex(null);
        focusEvidence({
          ...buildTraceEvidence(
            trace?.lap ?? overview.best_useful_lap?.lap_number ?? null,
            null,
            null,
            null,
            null,
          ),
          sampleIndex: null,
          lapDistFt: null,
          lapPct: null,
          eventId: null,
          lockState: "none",
          valueBasis: "unavailable",
          selectionSource: "trace_cursor",
        });
      }
      hideCursorLine();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [overview.best_useful_lap?.lap_number, trace?.lap, hideCursorLine, focusEvidence, buildTraceEvidence]);

  const handleOpenMapFromCursor = useCallback(() => {
    const lapNumber = trace?.lap ?? overview.best_useful_lap?.lap_number ?? null;
    const lapPct = valueAt(trace, "lap_dist_pct_100", selectedIndex);
    focusEvidence({
      ...buildTraceEvidence(
        lapNumber,
        lapPct,
        selectedIndex,
        xs[selectedIndex] ?? null,
        selectedPlatformEvent?.event_id ?? selection.selectedEventId ?? null,
      ),
      lockState: readoutSource === "Locked" ? "locked" : "none",
      valueBasis: selectedIndex != null ? "selected_sample" : selection.selectedValueBasis ?? "unavailable",
      selectionSource: "trace_cursor",
    }, "map");
  }, [
    buildTraceEvidence,
    focusEvidence,
    overview.best_useful_lap?.lap_number,
    readoutSource,
    selectedIndex,
    selectedPlatformEvent?.event_id,
    selection.selectedEventId,
    selection.selectedValueBasis,
    trace,
    xs,
  ]);

  const handleOpenMapFromPlatformEvent = useCallback((event: PlatformEventItem) => {
    focusEvidence({
      ...buildTraceEvidence(
        event.lap ?? trace?.lap ?? overview.best_useful_lap?.lap_number ?? null,
        event.lap_pct ?? null,
        event.sample_index ?? null,
        event.lap_dist_ft ?? null,
        event.event_id,
      ),
      lockState: "locked",
      valueBasis: "selected_sample",
      selectionSource: "trace_cursor",
    }, "map");
  }, [buildTraceEvidence, focusEvidence, overview.best_useful_lap?.lap_number, trace?.lap]);

  // ── clear clicked sample when trace/preset changes ───────────
  useEffect(() => {
    setHoverSampleIndex(null);
  }, [trace]);

  // ── cursor readout ───────────────────────────────────────────
  const selected = {
    distanceFt: xs[selectedIndex] ?? null,
    lapPct: valueAt(trace, "lap_dist_pct_100", selectedIndex),
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
    rearMinMm: valueAt(trace, "rear_min_ride_height_mm", selectedIndex),
    rearScrapeMarginMm: valueAt(trace, "rear_scrape_margin_mm", selectedIndex),
    aeroLoadIndex: valueAt(trace, "aero_load_index", selectedIndex),
    wholeCarBottomingRisk: valueAt(trace, "whole_car_bottoming_risk", selectedIndex),
    cfsRisk: valueAt(trace, "cfs_risk_score", selectedIndex),
    platformRisk: valueAt(trace, "platform_risk_score", selectedIndex),
    dragScrub: valueAt(trace, "drag_scrub_suspicion", selectedIndex),
    fullThrottleResistance: valueAt(trace, "full_throttle_resistance_index", selectedIndex),
  };

  const platformBalanceValue = values(trace, "platform_balance_label")[selectedIndex];
  const selectedPlatformBalance = typeof platformBalanceValue === "string" ? platformBalanceValue : null;

  // ── event severity badge colour ──────────────────────────────
  const severityColour = (sev: string) =>
    sev === "critical" ? "#ef4444" : sev === "high" ? "#f97316" : sev === "watch" ? "#f59e0b" : "#38bdf8";

  // ── helper to get value at selected/hover sample, falling back to latest ──
  const latest = useCallback((ch: string) => {
    const vals = getTraceValues(trace, ch);
    if (vals.length === 0) return null;
    // Prefer clicked sample, then hover, then last value
    const idx = clickedSampleIndex ?? hoverSampleIndex;
    if (idx != null && idx >= 0 && idx < vals.length) {
      const v = vals[idx];
      if (v != null && (typeof v !== "number" || Number.isFinite(v))) return v;
    }
    return vals[vals.length - 1] ?? null;
  }, [trace, clickedSampleIndex, hoverSampleIndex]);

  /** What basis the engineering cards are using. */
  const sampleBasisLabel: string = clickedSampleIndex != null
    ? "Selected sample"
    : hoverSampleIndex != null
      ? "Hover sample"
      : "Latest sample";

  const shockSetupSnapshot = overview.setup_snapshot ?? null;
  const shockDistributionModeLabel = "Full Lap Distribution";

  const shockCornerModels = useMemo<ShockPanelModel[]>(() => (
    SHOCK_CORNERS.map((corner) => {
      const samples = numericTraceValues(trace, `${corner.key}_shock_vel_in_s`);
      const readerCorner = shockReader?.corners.find((item) => item.corner === corner.label);
      const recommendationFor = (displayLabel: ShockSetupField["label"]) => (
        readerCorner?.setting_recommendations.find((recommendation) => recommendation.display_label === displayLabel) ?? null
      );
      const setupFields: ShockSetupField[] = [
        { label: "LS Comp", value: formatSetupClicks(setupCornerNumber(shockSetupSnapshot, corner.key, "ls_compression")), unavailable: setupCornerNumber(shockSetupSnapshot, corner.key, "ls_compression") == null, recommendation: recommendationFor("LS Comp") },
        { label: "HS Comp", value: formatSetupClicks(setupCornerNumber(shockSetupSnapshot, corner.key, "hs_compression")), unavailable: setupCornerNumber(shockSetupSnapshot, corner.key, "hs_compression") == null, recommendation: recommendationFor("HS Comp") },
        { label: "HS-S Comp", value: formatSetupClicks(setupCornerNumber(shockSetupSnapshot, corner.key, "hs_comp_slope")), unavailable: setupCornerNumber(shockSetupSnapshot, corner.key, "hs_comp_slope") == null, recommendation: recommendationFor("HS-S Comp") },
        { label: "LS Reb", value: formatSetupClicks(setupCornerNumber(shockSetupSnapshot, corner.key, "ls_rebound")), unavailable: setupCornerNumber(shockSetupSnapshot, corner.key, "ls_rebound") == null, recommendation: recommendationFor("LS Reb") },
        { label: "HS Reb", value: formatSetupClicks(setupCornerNumber(shockSetupSnapshot, corner.key, "hs_rebound")), unavailable: setupCornerNumber(shockSetupSnapshot, corner.key, "hs_rebound") == null, recommendation: recommendationFor("HS Reb") },
        { label: "HS-S Reb", value: formatSetupClicks(setupCornerNumber(shockSetupSnapshot, corner.key, "hs_reb_slope")), unavailable: setupCornerNumber(shockSetupSnapshot, corner.key, "hs_reb_slope") == null, recommendation: recommendationFor("HS-S Reb") },
      ];
      return {
        ...corner,
        samples,
        setupFields,
        unavailableReason: samples.length === 0
          ? "Shock movement telemetry unavailable for this run."
          : undefined,
      };
    })
  ), [shockReader, shockSetupSnapshot, trace]);

  const hasAnyShockTelemetry = shockCornerModels.some((corner) => corner.samples.length > 0);
  const sharedShockAxisLimit = SHOCK_FIXED_AXIS_LIMIT_IN_S;

  const platformGeometrySummaryItems = [
    { label: "CFS", value: selected.cfsIn != null ? `${selected.cfsIn.toFixed(3)} in` : "Unavailable", badge: "measured", severity: riskLabel(selected.cfsIn).toLowerCase() },
    { label: "LF / RF", value: selected.lf != null || selected.rf != null ? `${fmt(selected.lf, 3)} / ${fmt(selected.rf, 3)} in` : "Unavailable", badge: "measured", severity: selected.lf != null || selected.rf != null ? "safe" : "missing" },
    { label: "LR / RR", value: selected.lr != null || selected.rr != null ? `${fmt(selected.lr, 3)} / ${fmt(selected.rr, 3)} in` : "Unavailable", badge: "measured", severity: selected.lr != null || selected.rr != null ? "safe" : "missing" },
    { label: "Rake", value: selected.centerRake != null || selected.sideRake != null ? `${fmt(selected.centerRake, 2)} / ${fmt(selected.sideRake, 3)} in` : "Unavailable", badge: "calculated", severity: "safe" },
    { label: "Selected", value: selected.distanceFt != null ? `Lap ${trace?.lap ?? "n/a"} @ ${selected.distanceFt.toFixed(0)} ft` : `Lap ${trace?.lap ?? "n/a"}`, badge: readoutSource.toLowerCase(), severity: selected.distanceFt != null ? "safe" : "missing" },
  ];

  const diagnosticSummaryItems = [
    { label: "CFS", value: selected.cfsIn != null ? `${selected.cfsIn.toFixed(3)} in` : "Unavailable", badge: "measured", severity: riskLabel(selected.cfsIn).toLowerCase() },
    { label: "Rear min", value: selected.rearMinMm != null ? `${selected.rearMinMm.toFixed(1)} mm` : "Unavailable", badge: "calculated", severity: semanticSeverity(selected.rearScrapeMarginMm != null ? 1 - Math.max(0, Math.min(1, selected.rearScrapeMarginMm / 25)) : null) },
    { label: "Rake", value: selected.centerRake != null || selected.sideRake != null ? `${fmt(selected.centerRake, 2)} / ${fmt(selected.sideRake, 3)} in` : "Unavailable", badge: "calculated", severity: "safe" },
    { label: "Aero load", value: selected.aeroLoadIndex != null ? selected.aeroLoadIndex.toFixed(3) : "Unavailable", badge: "proxy", severity: semanticSeverity(selected.aeroLoadIndex != null ? Math.abs(selected.aeroLoadIndex - 1) : null) },
    { label: "Bottoming", value: selected.wholeCarBottomingRisk != null ? selected.wholeCarBottomingRisk.toFixed(2) : "Unavailable", badge: "proxy", severity: semanticSeverity(selected.wholeCarBottomingRisk) },
    { label: "Balance", value: selectedPlatformBalance ?? "Unavailable", badge: "derived", severity: selectedPlatformBalance ? (selectedPlatformBalance.toLowerCase().includes("bottom") ? "critical" : selectedPlatformBalance.toLowerCase().includes("risk") ? "high" : "safe") : "missing" },
    { label: "Scrub", value: selected.dragScrub != null ? selected.dragScrub.toFixed(2) : "Unavailable", badge: "proxy", severity: semanticSeverity(selected.dragScrub) },
    { label: "Selected", value: selected.distanceFt != null ? `Lap ${trace?.lap ?? "n/a"} @ ${selected.distanceFt.toFixed(0)} ft` : `Lap ${trace?.lap ?? "n/a"}`, badge: readoutSource.toLowerCase(), severity: selected.distanceFt != null ? "safe" : "missing" },
  ];
  const summaryItems = workbenchView === "balance" ? platformGeometrySummaryItems : diagnosticSummaryItems;

  const riskSegments = useMemo(() => {
    const riskChannels = [
      "cfs_risk_score",
      "platform_risk_score",
      "rear_scrape_risk_score",
      "rear_platform_contact_risk",
      "whole_car_bottoming_risk",
      "drag_scrub_suspicion",
      "full_throttle_resistance_index",
    ];
    const available = riskChannels
      .map((name) => values(trace, name) as Array<number | null>)
      .filter((vals) => vals.some((v) => typeof v === "number" && Number.isFinite(v)));
    if (available.length === 0 || xs.length === 0) return [];
    const segmentCount = Math.min(120, Math.max(24, Math.floor(xs.length / 8)));
    return Array.from({ length: segmentCount }, (_, segmentIndex) => {
      const startIndex = Math.floor((segmentIndex / segmentCount) * xs.length);
      const endIndex = Math.min(xs.length - 1, Math.floor(((segmentIndex + 1) / segmentCount) * xs.length));
      let risk: number | null = null;
      for (const vals of available) {
        for (let i = startIndex; i <= endIndex; i += 1) {
          const value = vals[i];
          if (typeof value === "number" && Number.isFinite(value)) risk = Math.max(risk ?? 0, value);
        }
      }
      return {
        startIndex,
        endIndex,
        risk,
        severity: semanticSeverity(risk),
      };
    });
  }, [trace, xs]);

  const scatterPoints = useMemo(() => {
    if (workbenchView !== "aero_load") return [];
    const speed = values(trace, "speed_mph") as Array<number | null>;
    const aero = (values(trace, "aero_load_index") as Array<number | null>).some((v) => typeof v === "number")
      ? values(trace, "aero_load_index") as Array<number | null>
      : values(trace, "dynamic_pressure_lap_index") as Array<number | null>;
    const maxSpeed2 = speed.reduce<number>((max, v) => typeof v === "number" ? Math.max(max, v * v) : max, 0);
    const maxAero = aero.reduce<number>((max, v) => typeof v === "number" ? Math.max(max, Math.abs(v)) : max, 0);
    if (maxSpeed2 <= 0 || maxAero <= 0) return [];
    const stride = Math.max(1, Math.floor(speed.length / 180));
    const points: Array<{ x: number; y: number; risk: number | null; distance: number | null }> = [];
    for (let i = 0; i < speed.length; i += stride) {
      const s = speed[i];
      const y = aero[i];
      if (typeof s !== "number" || typeof y !== "number" || !Number.isFinite(s) || !Number.isFinite(y)) continue;
      points.push({ x: (s * s) / maxSpeed2, y: y / maxAero, risk: valueAt(trace, "whole_car_bottoming_risk", i), distance: xs[i] ?? null });
    }
    return points;
  }, [trace, workbenchView, xs]);

  // ── engineering panel renderers ──────────────────────────────
  const setupAction = useCallback((_setupKeys: string[], label: string, isInferred: boolean) => {
    return (
      <div className="setup-link-row" style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 6 }}>
        <button className="trackmap-action-btn" onClick={() => setWorkspace("setup_impact", "trace_cursor")} title={`Open ${label}`}>
          <Wrench size={10} /> {label}
        </button>
        <span className="lap-flag-badge" style={{
          background: isInferred ? "rgba(245,158,11,0.12)" : "rgba(34,197,94,0.12)",
          color: isInferred ? "#f59e0b" : "#22c55e",
          fontSize: 8, padding: "1px 5px",
        }}>
          {isInferred ? "Inferred" : "Explicit"}
        </span>
      </div>
    );
  }, [setWorkspace]);

  const renderBalancePanel = () => (
    <div className="engineering-panel">
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="CFS Ride Height" channelName="cfs_ride_height_in" value={latest("cfs_ride_height_in")} color="#4ade80" />
        <EngineeringMetricCard title="Front Ride Heights" value={`LF ${formatChannelValue(latest("lf_ride_height_in") as number, "in")} / RF ${formatChannelValue(latest("rf_ride_height_in") as number, "in")}`} color="#38bdf8" />
        <EngineeringMetricCard title="Rear Ride Heights" value={`LR ${formatChannelValue(latest("lr_ride_height_in") as number, "in")} / RR ${formatChannelValue(latest("rr_ride_height_in") as number, "in")}`} color="#22d3ee" />
        <EngineeringMetricCard title="Front / Rear Avg RH" value={`Front ${formatChannelValue(latest("front_avg_rh_in") as number, "in")} / Rear ${formatChannelValue(latest("rear_avg_rh_in") as number, "in")}`} color="#a78bfa" />
        <EngineeringMetricCard title="Center Rake" channelName="center_rake_fs_in" value={latest("center_rake_fs_in")} color="#4ade80" />
        <EngineeringMetricCard title="Side Rake" channelName="side_rake_in" value={latest("side_rake_in")} color="#f59e0b" />
        <EngineeringMetricCard title="Roll / Pitch" value={`Roll ${formatChannelValue(latest("platform_roll_deg_from_rh") as number, "°")}`} subtitle={`Pitch ${formatChannelValue(latest("platform_pitch_deg_from_rh") as number, "°")}`} color="#a78bfa" />
      </div>
      {setupAction(["lf_ride_height_mm", "rf_ride_height_mm", "nose_weight_pct", "cross_weight_pct"], "Platform / Ride Height Setup", true)}
    </div>
  );

  const renderRearScrapeScrubPanel = () => (
    <div className="engineering-panel">
      {/* ── Metric cards ── */}
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="Rear Scrape Margin" channelName="rear_scrape_margin_mm" value={latest("rear_scrape_margin_mm")} color="#f97316" />
        <EngineeringMetricCard title="Rear Scrape Risk" channelName="rear_scrape_risk_score" value={latest("rear_scrape_risk_score")} riskValue={latest("rear_scrape_risk_score") as number | null} color="#ef4444" />
        <EngineeringMetricCard title="Rear Contact Risk" channelName="rear_platform_contact_risk" value={latest("rear_platform_contact_risk")} riskValue={latest("rear_platform_contact_risk") as number | null} color="#f59e0b" />
        <EngineeringMetricCard title="Drag/Scrub Suspicion" channelName="drag_scrub_suspicion" value={latest("drag_scrub_suspicion")} riskValue={latest("drag_scrub_suspicion") as number | null} color="#ef4444" />
        <EngineeringMetricCard title="Full-Throttle Resistance" channelName="full_throttle_resistance_index" value={latest("full_throttle_resistance_index")} riskValue={latest("full_throttle_resistance_index") as number | null} color="#f97316" />
        <EngineeringMetricCard title="Grade-Corrected Speed Loss" channelName="grade_corrected_speed_loss_mph_s" value={latest("grade_corrected_speed_loss_mph_s")} subtitle={`Raw: ${formatChannelValue(latest("speed_rate_mph_s") as number, "mph/s")}`} color="#22c55e" />
        <EngineeringMetricCard title="Yaw Error" value={formatChannelValue(latest("yaw_error_proxy") as number, "rad/s")} channelName="yaw_error_proxy" color="#38bdf8" />
        <EngineeringMetricCard title="Rear Scrub Proxy" value={formatChannelValue(latest("rear_scrub_proxy") as number, "proxy")} channelName="rear_scrub_proxy" color="#a78bfa" />
      </div>

      {/* ── Jump buttons ── */}
      <div className="toolbar-actions" style={{ marginTop: 6 }}>
        <button className={`secondary-button${jumpedBtn === "worst_scrape" ? " jump-clicked" : ""}`} onClick={() => {
          const scrapeVals = values(trace, "rear_scrape_risk_score") as (number | null)[];
          let worstIdx: number | null = null;
          let worstVal = -Infinity;
          scrapeVals.forEach((v, i) => { if (typeof v === "number" && v > worstVal) { worstVal = v; worstIdx = i; } });
          handleJumpClick("worst_scrape", worstIdx);
        }}>
          <Activity size={14} /> Jump to Worst Rear Scrape
        </button>
        <button className={`secondary-button${jumpedBtn === "worst_scrub" ? " jump-clicked" : ""}`} onClick={() => {
          const scrubVals = values(trace, "drag_scrub_suspicion") as (number | null)[];
          let worstIdx: number | null = null;
          let worstVal = -Infinity;
          scrubVals.forEach((v, i) => { if (typeof v === "number" && v > worstVal) { worstVal = v; worstIdx = i; } });
          handleJumpClick("worst_scrub", worstIdx);
        }}>
          <Activity size={14} /> Jump to Max Scrub
        </button>
        <button className={`secondary-button${jumpedBtn === "worst_resistance" ? " jump-clicked" : ""}`} onClick={() => {
          const resVals = values(trace, "full_throttle_resistance_index") as (number | null)[];
          let worstIdx: number | null = null;
          let worstVal = -Infinity;
          resVals.forEach((v, i) => { if (typeof v === "number" && v > worstVal) { worstVal = v; worstIdx = i; } });
          handleJumpClick("worst_resistance", worstIdx);
        }}>
          <Activity size={14} /> Jump to Worst Resistance
        </button>
      </div>

      {/* ── Combined corridor ── */}
      <div style={{ marginTop: 8 }}>
        <span style={{ fontSize: 9, color: "#8d9aaa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Rear Scrape / Scrub Corridor</span>
        {trace && xs.length > 1 ? (
          <RiskCorridorSVG
            channels={["rear_scrape_risk_score", "rear_platform_contact_risk", "drag_scrub_suspicion", "full_throttle_resistance_index", "rear_scrub_proxy"]}
            trace={trace}
            xs={xs}
            selectedIndex={selectedIndex}
            onJump={(idx) => jumpToIndex(idx)}
            height={64}
          />
        ) : (
          <p className="muted" style={{ fontSize: 9 }}>Risk corridor unavailable.</p>
        )}
      </div>

      {/* ── Setup actions ── */}
      {setupAction(["lr_ride_height_mm", "rr_ride_height_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm", "lr_packer_mm", "rr_packer_mm"], "Rear Platform Setup", false)}
      {setupAction(["steering_ratio", "steering_offset_deg", "front_arb_rating", "cross_weight_pct"], "Steering / Front Geometry Setup", false)}

      {/* ── Section note ── */}
      <p className="section-note" style={{ marginTop: 8 }}>
        Rear scrape and scrub are grouped because both represent potential speed loss/resistance. Rear scrape comes from platform/ride-height contact risk; scrub comes from steering/yaw/tire resistance proxies. Missing telemetry remains unavailable, never safe or zero.
      </p>
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
          <div className="aero-pressure-fill aero-flow" style={{ width: `${ribbonPct}%`, background: ribbonColor }} />
        </div>
        <span className="aero-pressure-label" style={{ color: ribbonColor }}>{aeroIdx?.toFixed(3) ?? "—"}</span>
      </div>
      <div className="aero-scatter-panel">
        <div className="aero-scatter-header">
          <span><BarChart3 size={13} /> Speed² vs aero/load proxy</span>
          <ProxyBadge kind="proxy" />
        </div>
        {scatterPoints.length === 0 ? (
          <p className="muted" style={{ margin: 0, fontSize: 11 }}>Unavailable: speed and aero/load proxy channels are required.</p>
        ) : (
          <svg className="aero-scatter-svg" viewBox="0 0 360 120" role="img" aria-label="Speed squared versus aero load proxy scatter">
            <line x1="28" y1="96" x2="344" y2="96" className="scatter-axis" />
            <line x1="28" y1="10" x2="28" y2="96" className="scatter-axis" />
            <text x="344" y="113" className="scatter-label" textAnchor="end">speed²</text>
            <text x="4" y="16" className="scatter-label" fill="#8d9aaa" fontSize={8}>proxy</text>
            {scatterPoints.map((point, index) => {
              const isSelectedSample = selectedIndex != null && point.distance != null && Math.abs(xs[selectedIndex]! - point.distance) < 1;
              return (
                <circle
                  key={`${point.distance ?? index}-${index}`}
                  cx={28 + point.x * 316}
                  cy={96 - point.y * 82}
                  r={isSelectedSample ? 4 : point.distance === selected.distanceFt ? 3.8 : 2.2}
                  className={isSelectedSample ? "scatter-point-selected" : "scatter-point"}
                  data-severity={semanticSeverity(point.risk)}
                />
              );
            })}
          </svg>
        )}
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
      {setupAction(["tape_percent", "lf_ride_height_mm", "rf_ride_height_mm"], "Aero / Ride Height Setup", true)}
    </div>
    );
  };

  const renderTiresPanel = () => (
    <div className="engineering-panel">
      <p className="section-note" style={{ fontSize: 10, marginBottom: 6 }}>
        Tire temps are measured iRacing telemetry channels. Lines show inner/middle/outer surface temperature across each tire.
      </p>
      <div className="basis-label" style={{ fontSize: 9, color: "#8d9aaa", marginBottom: 4 }}>
        <span className="lap-flag-badge" style={{ background: "rgba(141,154,170,0.12)", color: "#8d9aaa", fontSize: 9, padding: "1px 6px" }}>
          Tire map: Full-lap distribution
        </span>
      </div>
      <CornerTireMap trace={trace} mode={tireMapMode} onModeChange={setTireMapMode} />
      <div className="engineering-panel-grid" style={{ marginTop: 8 }}>
        <CornerBarChart trace={trace} channelPrefix="lf_pressure_gain" label="Pressure Gain" unit="kPa" color="#4ade80" decimals={1} />
        <CornerBarChart trace={trace} channelPrefix="lf_temp_spread" label="Temp Spread" unit="°C" color="#f97316" decimals={1} />
        <CornerBarChart trace={trace} channelPrefix="lf_slip_ratio_proxy" label="Slip Ratio" color="#a78bfa" decimals={3} />
      </div>
      {setupAction(["lf_pressure_kpa", "rf_pressure_kpa", "lr_pressure_kpa", "rr_pressure_kpa"], "Tire Pressure / Camber Setup", true)}
      <p className="section-note" style={{ fontSize: 9, color: "#8d9aaa", marginTop: 2 }}>
        Bar charts show <strong>{sampleBasisLabel === "Latest sample" ? "latest" : sampleBasisLabel.toLowerCase()} sample</strong> values.
      </p>
      <p className="section-note" style={{ marginTop: 8 }}>Inner hotter than outer may indicate camber load. Outer hotter than inner may indicate rollover, under-camber, or overdriving. Slip values are proxies unless true wheel/ground speed calibration is available.</p>
    </div>
  );

  const renderShocksPanel = () => (
    <div className="engineering-panel shock-workstation">
      <header className="shock-workstation-header">
        <div>
          <h3>Shocks</h3>
          <p className="section-note">
            Live shock velocity/deflection telemetry from the run. Setup damper clicks shown separately when available.
          </p>
        </div>
        <div className="shock-workstation-badges">
          <span className="lap-flag-badge">{shockDistributionModeLabel}</span>
          <span className="lap-flag-badge">Shared axis ±{sharedShockAxisLimit.toFixed(1)} in/s</span>
        </div>
      </header>

      {!hasAnyShockTelemetry && (
        <div className="shock-workstation-warning" role="status">
          <AlertTriangle size={14} />
          <span>
            Shock movement telemetry is unavailable for this run. Garage damper settings may still exist in Setup, but live shock deflection/velocity analysis is unavailable.
          </span>
        </div>
      )}

      <div className="shock-workstation-toolbar" aria-label="Shock histogram range summary">
        <p className="shock-range-note">
          Histograms use a fixed -{sharedShockAxisLimit.toFixed(1)} to +{sharedShockAxisLimit.toFixed(1)} in/s range, 0.50 in/s bins, labels every 1.0 in/s, and ±{SHOCK_BUCKET_THRESHOLD_IN_S.toFixed(1)} in/s hi/lo boundaries.
        </p>
      </div>

      <div className="shock-workstation-grid">
        {shockCornerModels.map((corner) => (
          <ShockHistogram
            key={corner.key}
            corner={corner.label}
            color={corner.color}
            samples={corner.samples}
            axisLimit={sharedShockAxisLimit}
            bucketThreshold={SHOCK_BUCKET_THRESHOLD_IN_S}
            setupFields={corner.setupFields}
            setupSide={corner.key === "rf" || corner.key === "rr" ? "right" : "left"}
            unavailableReason={corner.unavailableReason}
          />
        ))}
      </div>
    </div>
  );

  const renderDiffuserPanel = () => (
    <div className="engineering-panel">
      <div className="engineering-panel-grid">
        <EngineeringMetricCard title="Front Center RH" channelName="front_center_rh_in" value={latest("front_center_rh_in")} color="#38bdf8" />
        <EngineeringMetricCard title="Rear Center RH" channelName="rear_center_rh_in" value={latest("rear_center_rh_in")} color="#a78bfa" />
        <EngineeringMetricCard title="Smooth Center Rake" channelName="smooth_center_rake_in" value={latest("smooth_center_rake_in")} color="#c084fc" />
        <EngineeringMetricCard title="Smooth Diffuser Volume" channelName="smooth_diffuser_volume_ft3" value={latest("smooth_diffuser_volume_ft3")} color="#4ade80" />
        <EngineeringMetricCard title="Diffuser Base Volume" channelName="diffuser_base_volume_ft3" value={latest("diffuser_base_volume_ft3")} color="#60a5fa" />
        <EngineeringMetricCard title="Diffuser Wedge Volume" channelName="diffuser_wedge_volume_ft3" value={latest("diffuser_wedge_volume_ft3")} color="#f97316" />
        <EngineeringMetricCard title="Track Width Used" channelName="diffuser_track_width_in" value={latest("diffuser_track_width_in")} color="#8d9aaa" />
        <EngineeringMetricCard title="Wheelbase Used" channelName="diffuser_wheelbase_in" value={latest("diffuser_wheelbase_in")} color="#8d9aaa" />
      </div>
      {/* Jump buttons */}
      <div className="toolbar-actions" style={{ marginTop: 6 }}>
        <button className={`secondary-button${jumpedBtn === "min_diffuser_vol" ? " jump-clicked" : ""}`} onClick={() => {
          const vals = values(trace, "smooth_diffuser_volume_ft3") as (number | null)[];
          let worstIdx: number | null = null;
          let worstVal = Infinity;
          vals.forEach((v, i) => { if (typeof v === "number" && v < worstVal) { worstVal = v; worstIdx = i; } });
          handleJumpClick("min_diffuser_vol", worstIdx);
        }}>
          <Activity size={14} /> Jump to Min Smooth Diffuser Volume
        </button>
        <button className={`secondary-button${jumpedBtn === "worst_wedge" ? " jump-clicked" : ""}`} onClick={() => {
          const vals = values(trace, "diffuser_wedge_volume_ft3") as (number | null)[];
          let worstIdx: number | null = null;
          let worstVal = -Infinity;
          vals.forEach((v, i) => { if (typeof v === "number" && v > worstVal) { worstVal = v; worstIdx = i; } });
          handleJumpClick("worst_wedge", worstIdx);
        }}>
          <Activity size={14} /> Jump to Max Wedge Volume
        </button>
        <button className={`secondary-button${jumpedBtn === "lowest_rear_crh" ? " jump-clicked" : ""}`} onClick={() => {
          const vals = values(trace, "rear_center_rh_in") as (number | null)[];
          let worstIdx: number | null = null;
          let worstVal = Infinity;
          vals.forEach((v, i) => { if (typeof v === "number" && v < worstVal) { worstVal = v; worstIdx = i; } });
          handleJumpClick("lowest_rear_crh", worstIdx);
        }}>
          <Activity size={14} /> Jump to Lowest Rear Center RH
        </button>
      </div>
      {setupAction(["lf_ride_height_mm", "rf_ride_height_mm", "lr_ride_height_mm", "rr_ride_height_mm", "lf_front_spring_n_per_mm", "rf_front_spring_n_per_mm", "lr_rear_spring_n_per_mm", "rr_rear_spring_n_per_mm", "cross_weight_pct"], "Diffuser Geometry Setup", true)}
      <p className="section-note" style={{ marginTop: 8 }}>
        Diffuser channels are derived from ride-height geometry and resolved vehicle geometry. They describe underbody volume/rake shape, not direct aerodynamic force. Missing ride-height telemetry remains unavailable and is never treated as zero.
      </p>
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
      {setupAction(["rear_end_ratio", "tape_percent"], "Gearing / Pull Setup", true)}
      <p className="section-note" style={{ marginTop: 8 }}>Raw speed loss includes slope effects. Grade-corrected speed loss estimates what remains after removing uphill/downhill gravity component. Grade values are estimates from acceleration and speed derivative, not surveyed elevation.</p>
    </div>
  );

  const renderEngineeringPanel = () => {
    switch (workbenchView) {
      case "balance": return renderBalancePanel();
      case "rear_scrape": return renderRearScrapeScrubPanel();
      case "aero_load": return renderAeroPanel();
      case "scrub_steering": return renderRearScrapeScrubPanel();
      case "tires": return renderTiresPanel();
      case "shocks": return renderShocksPanel();
      case "grade_pull": return renderGradePanel();
      case "diffuser": return renderDiffuserPanel();
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
            Lap {trace?.lap ?? overview.best_useful_lap?.lap_number ?? "n/a"} | X Axis: Lap Distance [ft]
          </p>
          {windowContextActive && (
            <>
              <p className="scope-banner">
                Selected window: Laps {selection.selectedLapWindowStart}-{selection.selectedLapWindowEnd}. Platform trace is currently showing representative lap {trace?.lap ?? representativeLap ?? selection.selectedLapWindowStart}.
              </p>
              <div className="laps-chip-row" style={{ marginTop: 6 }}>
                <span className="lap-flag-badge">Basis: selected window / representative lap</span>
                {representativeLap != null && <span className="lap-flag-badge">Rep Lap {representativeLap}</span>}
                {windowLapNumbers.length > 0 && <span className="lap-flag-badge">{windowLapNumbers.length} laps in window</span>}
              </div>
            </>
          )}
        </div>
        <div className="toolbar-actions">
          {windowContextActive && (
            <>
              <button
                className="secondary-button"
                onClick={() => {
                  if (representativeLapIndex <= 0) return;
                  focusRepresentativeLap(windowLapNumbers[representativeLapIndex - 1]);
                }}
                disabled={representativeLapIndex <= 0}
              >
                Previous Lap
              </button>
              <button
                className="secondary-button"
                onClick={() => {
                  if (representativeLapIndex < 0 || representativeLapIndex >= windowLapNumbers.length - 1) return;
                  focusRepresentativeLap(windowLapNumbers[representativeLapIndex + 1]);
                }}
                disabled={representativeLapIndex < 0 || representativeLapIndex >= windowLapNumbers.length - 1}
              >
                Next Lap
              </button>
              <button
                className="secondary-button"
                onClick={() => {
                  if (trace?.lap == null || trace.lap === representativeLap) return;
                  focusRepresentativeLap(trace.lap);
                }}
                disabled={trace?.lap == null || trace.lap === representativeLap}
              >
                Use This Lap
              </button>
              <button className="secondary-button" onClick={() => setWorkspace("laps", "manual")}>
                Return to Laps
              </button>
            </>
          )}
          <label className="platform-event-filter">
            <span>Event markers</span>
            <select
              value={platformEventVisibilityMode}
              onChange={(event) => {
                onPlatformEventVisibilityModeChange?.(event.target.value as PlatformEventVisibilityMode);
              }}
              aria-label="Platform event visibility"
            >
              <option value="actionable">Actionable</option>
              <option value="proxy">Proxy / Internal</option>
              <option value="all">All</option>
            </select>
          </label>
          <button className="secondary-button" onClick={() => { zoomRangeRef.current = null; chartRef.current?.dispatchAction({ type: "restore" }); }}>
            <RotateCcw size={16} /> Reset Zoom
          </button>
          <button className={`secondary-button${jumpedBtn === "min_splitter" ? " jump-clicked" : ""}`} onClick={() => handleJumpClick("min_splitter", minSplitterIndex, "MIN_SPLITTER")}>
            <LocateFixed size={16} /> Jump to Min Splitter
          </button>
          <button className={`secondary-button${jumpedBtn === "worst_speed" ? " jump-clicked" : ""}`} onClick={() => handleJumpClick("worst_speed", worstSpeedLossIndex, "WORST_SPEED_LOSS")}>
            <Activity size={16} /> Jump to Worst Speed Loss
          </button>
          <button className="secondary-button" onClick={handleOpenMapFromCursor}>
            <MapPin size={16} /> Open Map
          </button>
        </div>
      </header>
      <p className="proxy-warning">
        Force values are estimates/proxies derived from telemetry, setup spring rates, ride heights, shock movement, and dynamic pressure. They are not direct iRacing aerodynamic force channels.
      </p>
      <div className="platform-summary-bar" aria-label="Current platform summary">
        {summaryItems.map((item) => (
          <div key={item.label} className="platform-summary-chip" data-severity={item.severity}>
            <span className="platform-summary-label">{item.label}</span>
            <strong>{item.value}</strong>
            <span className="platform-summary-badge">{item.badge}</span>
          </div>
        ))}
      </div>
      {workbenchView !== "balance" && (
        <div className="platform-risk-strip" aria-label="Platform risk over lap distance">
          {riskSegments.length === 0 ? (
            <span className="risk-strip-empty">Risk strip unavailable: required risk channels are missing.</span>
          ) : (
            riskSegments.map((segment) => {
              const isSelected = selectedIndex >= segment.startIndex && selectedIndex <= segment.endIndex;
              const dist = xs[Math.floor((segment.startIndex + segment.endIndex) / 2)];
              return (
                <button
                  key={`${segment.startIndex}-${segment.endIndex}`}
                  className={`risk-strip-segment${isSelected ? " selected" : ""}`}
                  data-severity={segment.severity}
                  style={{ width: `${100 / riskSegments.length}%` }}
                  title={dist != null ? `${Math.round(dist).toLocaleString()} ft | risk ${segment.risk?.toFixed(2) ?? "unavailable"}` : "Risk unavailable"}
                  onClick={() => jumpToIndex(Math.floor((segment.startIndex + segment.endIndex) / 2))}
                  aria-label={dist != null ? `Jump to ${Math.round(dist)} feet` : "Risk segment unavailable"}
                />
              );
            })
          )}
        </div>
      )}
      <WorkbenchSubnav active={workbenchView} onChange={handleViewChange} />
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
        <span className="laps-stint-legend-item" style={{ fontSize: 10, color: "#8d9aaa", fontWeight: 600 }}>
          Engineering cards basis:
        </span>
        <span className="lap-flag-badge" style={{
          background: sampleBasisLabel === "Selected sample" ? "rgba(56,189,248,0.15)" : "rgba(141,154,170,0.12)",
          color: sampleBasisLabel === "Selected sample" ? "#38bdf8" : "#8d9aaa",
          fontSize: 10, padding: "2px 8px",
        }}>
          {sampleBasisLabel}
        </span>
      </div>
      {renderEngineeringPanel()}
      <div className="platform-layout">
        <div className="trace-panel-wrapper">
          <div className="trace-panel" ref={chartNode} />
          <div className="trace-cursor-line" ref={cursorLineRef} hidden />
        </div>
        <aside className="cursor-panel">
          <header>
            <span><Crosshair size={16} /> Cursor Readout</span>
            <span className={`cursor-source-badge source-${readoutSource.toLowerCase()}`}>{readoutSource}</span>
            {readoutSource === "Locked" && <span className="cursor-unlock-hint">Esc to unlock</span>}
          </header>
          <dl>
            <div><dt>Lap</dt><dd>{trace?.lap ?? "n/a"}</dd></div>
            <div><dt>Distance</dt><dd>{fmt(selected.distanceFt, 0)} ft</dd></div>
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
      {(visiblePlatformEvents.length > 0 || platformEvents.length > 0) && (
        <div className="platform-events-section">
          <h3>Platform Diagnostic Events</h3>
          {visiblePlatformEvents.length > 0 ? (
            <div className="event-jump-row">
              {visiblePlatformEvents.map((event) => {
                const muted = isMutedPlatformEvent(event, platformEventVisibilityMode);
                return (
                  <button
                    className={`secondary-button platform-event-button${muted ? " muted" : ""}`}
                    key={event.event_id}
                    onClick={() => {
                      const idx = indexForPlatformEvent(event);
                      jumpToIndex(idx, event.event_id);
                    }}
                  >
                    <Activity size={16} /> {event.title}
                    {muted && <span className="event-scope-pill">{platformEventScopeLabel(event)}</span>}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="platform-events-empty">
              <p>No actionable platform events in this window.</p>
              <p className="muted">Internal evidence is still available for analysis.</p>
            </div>
          )}
          {selectedPlatformEvent && (
            <div className="evidence-card platform-evidence-card">
              <h4>{selectedPlatformEvent.title}</h4>
              <div className="evidence-meta">
                <span style={{ color: severityColour(selectedPlatformEvent.severity) }}>
                  <AlertTriangle size={14} /> {selectedPlatformEvent.severity}
                </span>
                <span>Confidence: {selectedPlatformEvent.confidence}</span>
                <span className="event-scope-pill">{platformEventScopeLabel(selectedPlatformEvent)}</span>
                {selectedPlatformEvent.is_proxy_based && <ProxyBadge kind="proxy" />}
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
              {selectedPlatformEvent.reason_for_hidden && (
                <p className="proxy-note">Hidden by default: {selectedPlatformEvent.reason_for_hidden}</p>
              )}
              <div className="diw-actions" style={{ marginTop: 8 }}>
                <button className="trackmap-action-btn" onClick={() => handleOpenMapFromPlatformEvent(selectedPlatformEvent)} title="Open Map at selected event">
                  <MapPin size={10} /> Open Map
                </button>
              </div>
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

      {/* ── legacy platform events (only shown when no structured events exist) ── */}
      {visiblePlatformEvents.length === 0 && legacyEvents.length > 0 && (
        <>
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
        </>
      )}
    </section>
  );
}
