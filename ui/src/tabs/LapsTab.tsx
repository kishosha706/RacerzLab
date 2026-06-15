import {
  AlertTriangle,
  BarChart3,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Clock,
  Gauge,
  LineChart,
  Layers,
  List,
  MapPin,
  SlidersHorizontal,
  Star,
  Target,
  TrendingDown,
  Trophy,
  X,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { compareStints, fetchLapWindows, fetchStints } from "../api/client";
import { makeBasketItem } from "../components/CompareBasket";
import { ValueDisplay } from "../components/ValueDisplay";
import { useCompareBasket } from "../store/CompareBasketContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { LapWindowSummary, LapWindowsResponse, StintCompareResult, StintResponse, StintSummary } from "../types/laps";
import type { RaceLabSession, SessionSelectionSource } from "../types/session";
import type { LapSummary, RunListItem, RunOverview } from "../types/telemetry";

type LapsTabProps = {
  overview: RunOverview;
  session: RaceLabSession | null;
  sessionRuns: RunListItem[];
  sessionRunsLoading: boolean;
  sessionSelectionSource: SessionSelectionSource | null;
};

type StintMode = "ev" | "delta" | "falloff";
type StintGraphMode = "lap_time" | "delta" | "rolling_5";

type EvidenceDescriptor = {
  id: string;
  title: string;
  note: string;
  scope: "single_lap" | "lap_window";
  basisLabel: string;
  lap?: LapSummary | null;
  window?: LapWindowSummary | null;
  representativeLap?: number | null;
  representativeReason?: string | null;
  trustTier: string | null;
  trustScore: number | null;
  engineeringValue: number | null;
  flags: string[];
  reasons: string[];
  paceLabel: string;
};

type StintGraphRenderPoint = {
  id: string;
  seriesId: string;
  x: number;
  stintLap: number;
  lapNumber: number;
  y: number;
  valid: boolean;
  excludedFromScale: boolean;
  exclusionReason: string | null;
  outlierAboveScale: boolean;
  outlierBelowScale: boolean;
  lapTime: number | null;
  deltaToBest: number | null;
  rolling5: number | null;
  invalidReason: string | null;
  warning: string | null;
  sourceLabel: string;
  color: string;
  screenX: number;
  screenY: number;
};

type StintGraphRawPoint = Omit<StintGraphRenderPoint, "sourceLabel" | "color" | "screenX" | "screenY">;

type StintGraphHover = StintGraphRenderPoint & {
  clientX: number;
  clientY: number;
};

const CHART_WIDTH = 720;
const CHART_HEIGHT = 320;
const CHART_PAD_LEFT = 54;
const CHART_PAD_RIGHT = 20;
const CHART_PAD_TOP = 20;
const CHART_PAD_BOTTOM = 34;

const stintAverageColumns = [
  { size: 3, label: "3-Lap Avg" },
  { size: 5, label: "5-Lap Avg" },
  { size: 7, label: "7-Lap Avg" },
  { size: 10, label: "10-Lap Avg" },
  { size: 15, label: "15-Lap Avg" },
  { size: 20, label: "20-Lap Avg" },
  { size: 25, label: "25-Lap Avg" },
  { size: 30, label: "30-Lap Avg" },
  { size: 40, label: "40-Lap Avg" },
  { size: 50, label: "50-Lap Avg" },
  { size: 60, label: "60-Lap Avg" },
] as const;
const stintProgressionColumns = [
  { label: "L1-5", startOffset: 1, endOffset: 5 },
  { label: "L6-10", startOffset: 6, endOffset: 10 },
  { label: "L11-15", startOffset: 11, endOffset: 15 },
  { label: "L16-20", startOffset: 16, endOffset: 20 },
  { label: "L21-25", startOffset: 21, endOffset: 25 },
  { label: "L26-30", startOffset: 26, endOffset: 30 },
  { label: "L31-35", startOffset: 31, endOffset: 35 },
  { label: "L36-40", startOffset: 36, endOffset: 40 },
  { label: "L41-45", startOffset: 41, endOffset: 45 },
  { label: "L46-50", startOffset: 46, endOffset: 50 },
  { label: "L51-55", startOffset: 51, endOffset: 55 },
  { label: "L56-60", startOffset: 56, endOffset: 60 },
] as const;

function stintBucket(stint: StintSummary, label: string) {
  return stint.bucket_averages.find((bucket) => bucket.label === label) ?? null;
}

function stintAverage(stint: StintSummary, size: number): number | null {
  const mapped = stint.best_avg_by_size?.[String(size)];
  if (mapped !== undefined) return mapped;
  switch (size) {
    case 3: return stint.rolling_3_avg_best ?? null;
    case 5: return stint.rolling_5_avg_best ?? null;
    case 7: return stint.rolling_7_avg_best ?? null;
    case 10: return stint.rolling_10_avg_best ?? null;
    case 15: return stint.rolling_15_avg_best ?? null;
    case 20: return stint.rolling_20_avg_best ?? null;
    case 25: return stint.rolling_25_avg_best ?? null;
    case 30: return stint.rolling_30_avg_best ?? null;
    case 40: return stint.rolling_40_avg_best ?? null;
    case 50: return stint.rolling_50_avg_best ?? null;
    case 60: return stint.rolling_60_avg_best ?? null;
    default: return null;
  }
}

function visibleNumberValues(values: Array<number | null | undefined>): number[] {
  return values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
}

function stintChartPolyline(
  points: StintGraphRenderPoint[],
  xMin: number,
  xMax: number,
  yMin: number,
  yMax: number,
): string {
  const xSpan = Math.max(1, xMax - xMin);
  const ySpan = Math.max(0.001, yMax - yMin);
  return points.map((point) => {
    const x = CHART_PAD_LEFT + ((point.x - xMin) / xSpan) * (CHART_WIDTH - CHART_PAD_LEFT - CHART_PAD_RIGHT);
    const y = CHART_PAD_TOP + (1 - ((point.y - yMin) / ySpan)) * (CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function chartX(x: number, xMin: number, xMax: number): number {
  const xSpan = Math.max(1, xMax - xMin);
  return CHART_PAD_LEFT + ((x - xMin) / xSpan) * (CHART_WIDTH - CHART_PAD_LEFT - CHART_PAD_RIGHT);
}

function chartY(y: number, yMin: number, yMax: number): number {
  const ySpan = Math.max(0.001, yMax - yMin);
  return CHART_PAD_TOP + (1 - ((y - yMin) / ySpan)) * (CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM);
}

function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((left, right) => left - right);
  const index = (sorted.length - 1) * p;
  const lower = Math.floor(index);
  const upper = Math.ceil(index);
  if (lower === upper) return sorted[lower];
  return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}

function racePaceDomain(values: number[], includeOutliers: boolean): { min: number; max: number; outlierLow: number; outlierHigh: number; mode: "race_pace" | "full_range" } {
  if (values.length === 0) return { min: 0, max: 1, outlierLow: 0, outlierHigh: 1, mode: includeOutliers ? "full_range" : "race_pace" };
  const sorted = [...values].sort((left, right) => left - right);
  const minRaw = sorted[0];
  const maxRaw = sorted[sorted.length - 1];
  if (includeOutliers || sorted.length < 5) {
    const pad = Math.max(0.05, (maxRaw - minRaw) * 0.12);
    return { min: minRaw - pad, max: maxRaw + pad, outlierLow: minRaw - pad, outlierHigh: maxRaw + pad, mode: includeOutliers ? "full_range" : "race_pace" };
  }
  const q1 = percentile(sorted, 0.25) ?? minRaw;
  const q3 = percentile(sorted, 0.75) ?? maxRaw;
  const p5 = percentile(sorted, 0.05) ?? minRaw;
  const p95 = percentile(sorted, 0.95) ?? maxRaw;
  const iqr = Math.max(0.001, q3 - q1);
  const outlierLow = q1 - iqr * 1.5;
  const outlierHigh = q3 + iqr * 1.5;
  const domainValues = sorted.filter((value) => value >= outlierLow && value <= outlierHigh);
  const domainMin = Math.min(...(domainValues.length > 0 ? domainValues : sorted), p5);
  const domainMax = Math.max(...(domainValues.length > 0 ? domainValues : sorted), p95);
  const pad = Math.max(0.05, (domainMax - domainMin) * 0.18);
  return {
    min: domainMin - pad,
    max: domainMax + pad,
    outlierLow,
    outlierHigh,
    mode: "race_pace",
  };
}

function formatTime(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "-";
  const min = Math.floor(seconds / 60);
  const sec = (seconds % 60).toFixed(3);
  return `${min}:${sec.padStart(6, "0")}`;
}

function formatDelta(seconds: number | null | undefined, best: number | null | undefined): string {
  if (seconds == null || best == null || Number.isNaN(seconds) || Number.isNaN(best)) return "-";
  const delta = seconds - best;
  if (Math.abs(delta) < 0.001) return "BEST";
  return `+${delta.toFixed(3)}`;
}

function formatSignedDelta(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "-";
  if (Math.abs(seconds) < 0.001) return "+0.000";
  return `${seconds > 0 ? "+" : ""}${seconds.toFixed(3)}`;
}

function graphYLabel(value: number, mode: StintGraphMode): string {
  return mode === "delta" ? formatSignedDelta(value) : formatTime(value);
}

function formatScore(score: number | null | undefined): string {
  return score == null || Number.isNaN(score) ? "-" : score.toFixed(0);
}

function formatOptionalNumber(value: number | null | undefined, digits = 1): string {
  return value == null || Number.isNaN(value) ? "-" : value.toFixed(digits);
}

function csvCell(value: string | number | boolean | null | undefined): string {
  if (value == null) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function formatWindowRange(window: Pick<LapWindowSummary, "start_lap" | "end_lap">): string {
  return `Laps ${window.start_lap}-${window.end_lap}`;
}

function formatStintRange(stint: Pick<StintSummary, "start_lap" | "end_lap">): string {
  return `Laps ${stint.start_lap}-${stint.end_lap}`;
}

function compactTrendLabel(kind: "tire" | "platform" | "shock", label: string): string {
  const lower = label.toLowerCase();
  if (lower.includes("limited")) return `${kind[0].toUpperCase()}${kind.slice(1)} limited`;
  if (lower.includes("rf")) return "RF rising";
  if (lower.includes("rear scrape")) return "Rear scrape";
  if (lower.includes("rear")) return "Rear rising";
  if (lower.includes("front contact")) return "Front contact";
  if (lower.includes("rising")) return kind === "shock" ? "Rising activity" : "Rising";
  if (lower.includes("stable")) return "Stable";
  return label;
}

function trendBadgeClass(label: string): string {
  const lower = label.toLowerCase();
  if (lower.includes("limited")) return "stint-trend-badge muted";
  if (lower.includes("rising") || lower.includes("contact") || lower.includes("scrape")) return "stint-trend-badge warn";
  if (lower.includes("stable")) return "stint-trend-badge stable";
  return "stint-trend-badge";
}

function paceQualityColor(score: number | null | undefined): string {
  if (score == null) return "#8d9aaa";
  if (score >= 85) return "#22c55e";
  if (score >= 70) return "#38bdf8";
  if (score >= 50) return "#f59e0b";
  if (score >= 25) return "#f97316";
  return "#ef4444";
}

function classifyPaceTrust(
  paceScore: number | null | undefined,
  trustScore: number | null | undefined,
  warnings: string[] | undefined,
): string {
  const upper = (warnings ?? []).map((warning) => warning.toUpperCase());
  if (upper.some((warning) => warning.includes("INSUFFICIENT") || warning.includes("ONLY"))) return "Limited sample size";
  if (paceScore != null && trustScore != null) {
    if (paceScore >= 70 && trustScore < 50) return "Fast but not trustworthy";
    if (trustScore >= 70 && paceScore < 50) return "Trustworthy but not fast";
    if (paceScore >= 70 && trustScore >= 70) return "Strong pace and trust";
  }
  return "Use with caution";
}

function lapTrustTier(lap: LapSummary): string {
  if (!lap.is_useful) return "Invalid";
  return "Usable";
}

function windowTrustTier(window: LapWindowSummary): string {
  if (window.evidence_confidence_label) return window.evidence_confidence_label;
  if (window.evidence_confidence_score == null) return "Unavailable";
  if (window.evidence_confidence_score >= 80) return "High";
  if (window.evidence_confidence_score >= 60) return "Medium";
  return "Low";
}

function lapFlags(lap: LapSummary): string[] {
  const flags: string[] = [];
  if (!lap.is_useful) flags.push("Invalid");
  if (lap.lap_type !== "timed") flags.push(lap.lap_type);
  return flags;
}

function windowFlags(window: LapWindowSummary): string[] {
  const flags: string[] = [];
  if (window.valid_lap_count < window.window_size) flags.push("Excluded laps");
  if (window.falloff_sec != null) flags.push(`${window.window_size} lap block`);
  return flags;
}

function trustReasonChips(
  score: number | null | undefined,
  warnings: string[] | undefined,
  tags: string[] | undefined,
): string[] {
  if (score == null || score >= 70) return [];
  const chips: string[] = [];
  const upperWarnings = (warnings ?? []).map((warning) => warning.toUpperCase());
  const upperTags = (tags ?? []).map((tag) => tag.toUpperCase());
  if (upperWarnings.some((warning) => warning.includes("INVALID") || warning.includes("INSUFFICIENT") || warning.includes("ONLY"))
    || upperTags.some((tag) => tag.includes("INVALID") || tag.includes("INCOMPLETE"))) chips.push("Few laps");
  if (upperWarnings.some((warning) => warning.includes("SHORT"))) chips.push("Short window");
  if (upperWarnings.some((warning) => warning.includes("TIRE") || warning.includes("TEMP"))) chips.push("Tire data");
  if (upperWarnings.some((warning) => warning.includes("PLATFORM"))) chips.push("Platform data");
  return [...new Set(chips)].slice(0, 4);
}

function windowContainsLap(window: Pick<LapWindowSummary, "start_lap" | "end_lap">, lapNumber: number): boolean {
  return lapNumber >= window.start_lap && lapNumber <= window.end_lap;
}

function matchesSelectionWindow(
  window: Pick<LapWindowSummary, "start_lap" | "end_lap">,
  selectedStart: number | null | undefined,
  selectedEnd: number | null | undefined,
): boolean {
  return window.start_lap === selectedStart && window.end_lap === selectedEnd;
}

function candidateScore(window: LapWindowSummary): number {
  const engineering = window.setup_usefulness_score ?? -1;
  const trust = window.evidence_confidence_score ?? -1;
  const pace = window.pace_quality_score ?? -1;
  return engineering * 10000 + trust * 100 + pace;
}

type RepresentativeLapInfo = {
  lapNumber: number;
  reason: string;
  isFallback: boolean;
};

function bestEvidenceLapInSet(laps: LapSummary[]): LapSummary | null {
  const usefulLaps = laps.filter((lap) => lap.is_useful);
  const source = usefulLaps;
  return [...source]
    .filter((lap) => lap.lap_time != null)
    .sort((left, right) => (left.lap_time ?? 9999) - (right.lap_time ?? 9999))[0] ?? null;
}

function fastestUsableLapInSet(laps: LapSummary[]): LapSummary | null {
  return [...laps]
    .filter((lap) => lap.is_useful && lap.lap_time != null)
    .sort((left, right) => (left.lap_time ?? 9999) - (right.lap_time ?? 9999))[0] ?? null;
}

function deriveRepresentativeLap(window: LapWindowSummary, laps: LapSummary[]): RepresentativeLapInfo {
  const lapsInWindow = laps.filter((lap) => lap.lap_number >= window.start_lap && lap.lap_number <= window.end_lap);
  const bestEvidenceLap = bestEvidenceLapInSet(lapsInWindow);
  if (bestEvidenceLap) {
    return {
      lapNumber: bestEvidenceLap.lap_number,
      reason: "Best evidence lap in window",
      isFallback: false,
    };
  }
  const fastestUsableLap = fastestUsableLapInSet(lapsInWindow);
  if (fastestUsableLap) {
    return {
      lapNumber: fastestUsableLap.lap_number,
      reason: "Fastest usable lap in window",
      isFallback: false,
    };
  }
  return {
    lapNumber: window.start_lap,
    reason: "Fallback to window start lap",
    isFallback: true,
  };
}

function dedupeDescriptors(items: EvidenceDescriptor[]): EvidenceDescriptor[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function describeSelection(
  selection: ReturnType<typeof useTelemetrySelection>["selection"],
  laps: LapSummary[],
  bestWindows: LapWindowSummary[],
): EvidenceDescriptor | null {
  if (selection.selectedLapScope === "lap_window" && selection.selectedLapWindowStart != null && selection.selectedLapWindowEnd != null) {
    const matchingWindow = bestWindows.find((window) =>
      matchesSelectionWindow(window, selection.selectedLapWindowStart, selection.selectedLapWindowEnd));
    const representative = matchingWindow
      ? deriveRepresentativeLap(matchingWindow, laps)
      : null;
    return {
      id: `selection-window-${selection.selectedLapWindowStart}-${selection.selectedLapWindowEnd}`,
      title: "Current Selection",
      note: matchingWindow ? "Selected window driving downstream tabs" : "Selected window preserved in evidence context",
      scope: "lap_window",
      basisLabel: "Selected window",
      window: matchingWindow ?? {
        window_id: "selection-window",
        run_id: "",
        car_name: null,
        track_name: null,
        start_lap: selection.selectedLapWindowStart,
        end_lap: selection.selectedLapWindowEnd,
        window_size: selection.selectedLapWindowEnd - selection.selectedLapWindowStart + 1,
        total_time: null,
        average_lap_time: null,
        fastest_lap_time: null,
        slowest_lap_time: null,
        lap_time_std_dev: null,
        falloff_sec: null,
        falloff_sec_per_lap: null,
        consistency_score: 0,
        valid_lap_count: 0,
        excluded_laps: [],
        classification_tags: [],
        platform_risk_peak: null,
        rear_platform_risk_peak: null,
        whole_car_bottoming_peak: null,
        tire_stress_score: 0,
        shock_stress_score: 0,
        confidence_score: 0,
        warnings: [],
        recommendation: null,
      },
      representativeLap: selection.selectedRepresentativeLap ?? selection.selectedLap ?? representative?.lapNumber ?? matchingWindow?.start_lap ?? selection.selectedLapWindowStart,
      representativeReason: selection.selectedRepresentativeLap != null
        ? "Representative lap preserved in selection"
        : representative?.reason != null
          ? representative.reason
          : "Representative lap unavailable",
      trustTier: selection.selectedTrustTier ?? matchingWindow?.evidence_confidence_label ?? null,
      trustScore: matchingWindow?.evidence_confidence_score ?? null,
      engineeringValue: matchingWindow?.setup_usefulness_score ?? null,
      flags: matchingWindow ? windowFlags(matchingWindow) : [],
      reasons: matchingWindow ? trustReasonChips(matchingWindow.evidence_confidence_score, matchingWindow.pace_quality_warnings, matchingWindow.classification_tags) : [],
      paceLabel: matchingWindow?.average_lap_time != null ? formatTime(matchingWindow.average_lap_time) : "Window preserved",
    };
  }

  const selectedLap = laps.find((lap) => lap.lap_number === selection.selectedLap) ?? null;
  if (!selectedLap) return null;
  return {
    id: `selection-lap-${selectedLap.lap_number}`,
    title: "Current Selection",
    note: "Selected lap driving downstream tabs",
    scope: "single_lap",
    basisLabel: "Selected lap",
    lap: selectedLap,
    trustTier: lapTrustTier(selectedLap),
    trustScore: null,
    engineeringValue: null,
    flags: lapFlags(selectedLap),
    reasons: selectedLap.confidence_notes ?? [],
    paceLabel: formatTime(selectedLap.lap_time),
  };
}

function descriptorForLap(title: string, note: string, lap: LapSummary): EvidenceDescriptor {
  return {
    id: `lap-${lap.lap_number}-${title}`,
    title,
    note,
    scope: "single_lap",
    basisLabel: "Lap-level",
    lap,
    trustTier: lapTrustTier(lap),
    trustScore: null,
    engineeringValue: null,
    flags: lapFlags(lap),
    reasons: lap.confidence_notes ?? [],
    paceLabel: formatTime(lap.lap_time),
  };
}

function descriptorForWindow(
  title: string,
  note: string,
  window: LapWindowSummary,
  representative?: RepresentativeLapInfo | null,
): EvidenceDescriptor {
  return {
    id: `window-${window.start_lap}-${window.end_lap}-${title}`,
    title,
    note,
    scope: "lap_window",
    basisLabel: "Window-level",
    window,
    representativeLap: representative?.lapNumber ?? null,
    representativeReason: representative?.reason ?? null,
    trustTier: windowTrustTier(window),
    trustScore: window.evidence_confidence_score ?? null,
    engineeringValue: window.setup_usefulness_score ?? null,
    flags: windowFlags(window),
    reasons: trustReasonChips(window.evidence_confidence_score, window.pace_quality_warnings, window.classification_tags),
    paceLabel: window.average_lap_time != null ? formatTime(window.average_lap_time) : formatWindowRange(window),
  };
}

export function LapsTab({ overview, session, sessionRuns, sessionRunsLoading, sessionSelectionSource }: LapsTabProps) {
  const { selection, focusEvidence, setWorkspace } = useTelemetrySelection();
  const {
    basket,
    setBaseline,
    setTest,
    addToQueue,
    removeFromQueue,
    clearQueue,
    swap,
    clear,
  } = useCompareBasket();

  const [windowsData, setWindowsData] = useState<LapWindowsResponse | null>(null);
  const [stintData, setStintData] = useState<StintResponse | null>(null);
  const [stintsLoading, setStintsLoading] = useState(false);
  const [showBestWindows, setShowBestWindows] = useState(false);
  const [stintCompareLoading, setStintCompareLoading] = useState(false);
  const [stintCompareError, setStintCompareError] = useState<string | null>(null);
  const [baselineStintId, setBaselineStintId] = useState<string | null>(null);
  const [testStintId, setTestStintId] = useState<string | null>(null);
  const [selectedStintId, setSelectedStintId] = useState<string | null>(null);
  const [stintCompare, setStintCompare] = useState<StintCompareResult | null>(null);
  const [showFieldCompare, setShowFieldCompare] = useState(false);
  const [showAdvancedControls, setShowAdvancedControls] = useState(false);
  const [graphStintIds, setGraphStintIds] = useState<string[]>([]);
  const [stintGraphMode, setStintGraphMode] = useState<StintGraphMode>("lap_time");
  const [showRolling5, setShowRolling5] = useState(false);
  const [excludeInvalidGraphLaps, setExcludeInvalidGraphLaps] = useState(true);
  const [includeOutliersInScale, setIncludeOutliersInScale] = useState(false);
  const [currentRunOnlyFilter, setCurrentRunOnlyFilter] = useState(false);
  const [sameCarTrackOnlyFilter, setSameCarTrackOnlyFilter] = useState(false);
  const [graphedOnlyFilter, setGraphedOnlyFilter] = useState(false);
  const [hideInvalidRowsFilter, setHideInvalidRowsFilter] = useState(false);
  const [summaryDrawerStintId, setSummaryDrawerStintId] = useState<string | null>(null);
  const [hoveredGraphPoint, setHoveredGraphPoint] = useState<StintGraphHover | null>(null);
  const [selectedGraphLap, setSelectedGraphLap] = useState<{ stintId: string; lapNumber: number } | null>(null);
  const [pinnedRunIds, setPinnedRunIds] = useState<Set<string>>(() => new Set());
  const [expandedRunIds, setExpandedRunIds] = useState<Set<string>>(() => new Set([overview.run_id]));
  const [historyStintData, setHistoryStintData] = useState<Record<string, StintResponse>>({});
  const [historyStintsLoading, setHistoryStintsLoading] = useState<Record<string, boolean>>({});
  const [expandedLap, setExpandedLap] = useState<number | null>(null);
  const [stintMode, setStintMode] = useState<StintMode>("ev");
  const [hoveredWindowId, setHoveredWindowId] = useState<string | null>(null);

  const { laps } = overview;

  useEffect(() => {
    setExpandedRunIds(new Set([overview.run_id]));
    setGraphStintIds([]);
    setSummaryDrawerStintId(null);
    setHoveredGraphPoint(null);
    setSelectedGraphLap(null);
    setHistoryStintData({});
    setHistoryStintsLoading({});
  }, [overview.run_id]);

  useEffect(() => {
    fetchLapWindows(overview.run_id)
      .then(setWindowsData)
      .catch(() => setWindowsData(null));
  }, [overview.run_id]);

  useEffect(() => {
    setStintsLoading(true);
    setBaselineStintId(null);
    setTestStintId(null);
    setSelectedStintId(null);
    setGraphStintIds([]);
    setSummaryDrawerStintId(null);
    setStintCompare(null);
    setStintCompareError(null);
    fetchStints(overview.run_id)
      .then(setStintData)
      .catch(() => setStintData(null))
      .finally(() => setStintsLoading(false));
  }, [overview.run_id]);

  const bestTime = useMemo(() => {
    const times = laps.filter((lap) => lap.lap_time != null).map((lap) => lap.lap_time as number);
    return times.length > 0 ? Math.min(...times) : null;
  }, [laps]);

  const usefulLaps = useMemo(() => laps.filter((lap) => lap.is_useful), [laps]);
  const cleanUsefulLaps = useMemo(() => usefulLaps, [usefulLaps]);

  const fastestUsableLap = useMemo(
    () => [...usefulLaps].filter((lap) => lap.lap_time != null).sort((left, right) => (left.lap_time ?? 9999) - (right.lap_time ?? 9999))[0] ?? null,
    [usefulLaps],
  );

  const bestEvidenceLap = useMemo(() => {
    const source = cleanUsefulLaps.length > 0 ? cleanUsefulLaps : usefulLaps;
    return [...source].filter((lap) => lap.lap_time != null).sort((left, right) => (left.lap_time ?? 9999) - (right.lap_time ?? 9999))[0] ?? null;
  }, [cleanUsefulLaps, usefulLaps]);

  const engineeringCueLap = useMemo(() => {
    const source = cleanUsefulLaps.length > 0 ? cleanUsefulLaps : usefulLaps;
    return [...source].sort((left, right) => (left.min_splitter_mm ?? 9999) - (right.min_splitter_mm ?? 9999))[0] ?? null;
  }, [cleanUsefulLaps, usefulLaps]);

  const availableBestWindows = useMemo(
    () => (windowsData?.best_windows ?? [])
      .filter((group) => group.best_window != null)
      .map((group) => group.best_window as LapWindowSummary),
    [windowsData],
  );

  const stints = useMemo(
    () => stintData?.stint_rows ?? stintData?.primary_stints ?? stintData?.stints ?? [],
    [stintData],
  );
  const bestWindowCards = useMemo(
    () => stintData?.best_window_cards ?? [],
    [stintData],
  );
  const alternateStintWindows = useMemo(
    () => (stintData?.all_windows ?? []).filter((stint) => !bestWindowCards.some((card) => card.stint_id === stint.stint_id)),
    [bestWindowCards, stintData],
  );
  const historyStintCandidates = useMemo(
    () => {
      const byId = new Map<string, StintSummary>();
      Object.entries(historyStintData).forEach(([runId, response]) => {
        if (runId === overview.run_id) return;
        [
          ...(response.stint_rows ?? []),
          ...(response.best_window_cards ?? []),
          ...(response.all_windows ?? []),
        ].forEach((stint) => byId.set(stint.stint_id, stint));
      });
      return [...byId.values()];
    },
    [historyStintData, overview.run_id],
  );
  const stintSelectionCandidates = useMemo(
    () => {
      const byId = new Map<string, StintSummary>();
      [...stints, ...bestWindowCards, ...(stintData?.all_windows ?? []), ...historyStintCandidates].forEach((stint) => byId.set(stint.stint_id, stint));
      return [...byId.values()];
    },
    [bestWindowCards, historyStintCandidates, stintData, stints],
  );
  const selectedStint = useMemo(
    () => selectedStintId ? stintSelectionCandidates.find((stint) => stint.stint_id === selectedStintId) ?? null : null,
    [selectedStintId, stintSelectionCandidates],
  );
  const baselineStint = useMemo(
    () => stintSelectionCandidates.find((stint) => stint.stint_id === baselineStintId) ?? null,
    [baselineStintId, stintSelectionCandidates],
  );
  const testStint = useMemo(
    () => stintSelectionCandidates.find((stint) => stint.stint_id === testStintId) ?? null,
    [stintSelectionCandidates, testStintId],
  );
  const strongestSetupStintId = useMemo(
    () => [...stintSelectionCandidates].sort((left, right) => (right.setup_usefulness_score ?? -1) - (left.setup_usefulness_score ?? -1))[0]?.stint_id ?? null,
    [stintSelectionCandidates],
  );
  const bestSustainedStint = useMemo(
    () => [...bestWindowCards]
      .filter((stint) => stint.is_best_for_size)
      .sort((left, right) => {
        const leftLong = left.lap_count >= 20 ? left.lap_count : 0;
        const rightLong = right.lap_count >= 20 ? right.lap_count : 0;
        if (leftLong !== rightLong) return rightLong - leftLong;
        return (left.avg_lap_time ?? 999999) - (right.avg_lap_time ?? 999999);
      })[0]
      ?? null,
    [bestWindowCards],
  );
  const bucketLabels = useMemo(
    () => stintProgressionColumns.map((column) => column.label),
    [],
  );
  const bestFastestLapValue = useMemo(
    () => {
      const values = visibleNumberValues(stints.map((stint) => stint.best_lap_time));
      return values.length > 0 ? Math.min(...values) : null;
    },
    [stints],
  );
  const bestSetupEvValue = useMemo(
    () => {
      const values = visibleNumberValues(stints.map((stint) => stint.setup_usefulness_score));
      return values.length > 0 ? Math.max(...values) : null;
    },
    [stints],
  );
  const bestAverageValues = useMemo(() => {
    const values: Record<number, number | null> = {};
    stintAverageColumns.forEach((column) => {
      const eligible = visibleNumberValues(stints.map((stint) => stintAverage(stint, column.size)));
      values[column.size] = eligible.length > 0 ? Math.min(...eligible) : null;
    });
    return values;
  }, [stints]);
  useEffect(() => {
    if (!baselineStint || !testStint) {
      setStintCompare(null);
      setStintCompareError(null);
      return;
    }
    setStintCompareLoading(true);
    setStintCompareError(null);
    compareStints({
      baseline_run_id: baselineStint.run_id,
      baseline_stint_id: baselineStint.stint_id,
      test_run_id: testStint.run_id,
      test_stint_id: testStint.stint_id,
    })
      .then(setStintCompare)
      .catch((err: unknown) => {
        setStintCompare(null);
        setStintCompareError((err as Error).message ?? "Stint compare failed.");
      })
      .finally(() => setStintCompareLoading(false));
  }, [baselineStint, testStint]);

  const bestWindow = useMemo(
    () => [...availableBestWindows].sort((left, right) => candidateScore(right) - candidateScore(left))[0] ?? null,
    [availableBestWindows],
  );

  const representativeLapByWindowId = useMemo(() => {
    const mapping = new Map<string, RepresentativeLapInfo>();
    availableBestWindows.forEach((window) => {
      mapping.set(window.window_id, deriveRepresentativeLap(window, laps));
    });
    return mapping;
  }, [availableBestWindows, laps]);

  const bestWindowMembership = useMemo(() => {
    const membership = new Map<number, string[]>();
    availableBestWindows.forEach((window) => {
      for (let lapNumber = window.start_lap; lapNumber <= window.end_lap; lapNumber += 1) {
        const row = membership.get(lapNumber) ?? [];
        row.push(`${window.window_size}L`);
        membership.set(lapNumber, row);
      }
    });
    return membership;
  }, [availableBestWindows]);

  const currentSelectionDescriptor = useMemo(
    () => describeSelection(selection, laps, availableBestWindows),
    [selection, laps, availableBestWindows],
  );

  const evidenceSelector = useMemo(() => {
    const items: EvidenceDescriptor[] = [];
    if (fastestUsableLap) items.push(descriptorForLap("Fastest Usable", "Best pace reference", fastestUsableLap));
    if (bestEvidenceLap) items.push(descriptorForLap("Best Evidence Lap", "Best single-lap setup evidence", bestEvidenceLap));
    if (bestWindow) items.push(descriptorForWindow("Best Window", "Best sustained evidence block", bestWindow, representativeLapByWindowId.get(bestWindow.window_id) ?? null));
    if (currentSelectionDescriptor) items.push(currentSelectionDescriptor);
    return items;
  }, [bestEvidenceLap, bestWindow, currentSelectionDescriptor, fastestUsableLap, representativeLapByWindowId]);
  const groupedEvidenceSelector = useMemo(() => {
    const groups: Array<{ label: string; items: EvidenceDescriptor[] }> = [
      { label: "Pace Reference", items: evidenceSelector.filter((item) => item.title.includes("Fastest")) },
      { label: "Evidence Quality", items: evidenceSelector.filter((item) => item.title.includes("Best Evidence")) },
      { label: "Windows", items: evidenceSelector.filter((item) => item.scope === "lap_window" && !item.title.includes("Current")) },
      { label: "Current Selection", items: evidenceSelector.filter((item) => item.title.includes("Current Selection")) },
    ];
    return groups.filter((group) => group.items.length > 0);
  }, [evidenceSelector]);

  const candidateMatrix = useMemo(() => {
    const rows: EvidenceDescriptor[] = [];
    if (fastestUsableLap) rows.push(descriptorForLap("Fastest Usable", "Pace reference", fastestUsableLap));
    if (bestEvidenceLap) rows.push(descriptorForLap("Best Evidence Lap", "Best single-lap evidence", bestEvidenceLap));
    if (engineeringCueLap) rows.push(descriptorForLap("Engineering Cue Lap", "Platform-sensitive single lap", engineeringCueLap));
    availableBestWindows.forEach((window) => {
      rows.push(descriptorForWindow(
        `Window ${window.window_size}L`,
        classifyPaceTrust(window.pace_quality_score, window.evidence_confidence_score, window.pace_quality_warnings),
        window,
        representativeLapByWindowId.get(window.window_id) ?? null,
      ));
    });
    if (currentSelectionDescriptor) rows.push(currentSelectionDescriptor);
    return dedupeDescriptors(rows);
  }, [availableBestWindows, bestEvidenceLap, currentSelectionDescriptor, engineeringCueLap, fastestUsableLap, representativeLapByWindowId]);

  const focusLapEvidence = useCallback((lap: LapSummary, workspace?: "platform_trace" | "map") => {
    focusEvidence({
      runId: overview.run_id,
      lapNumber: lap.lap_number,
      lapScope: "single_lap",
      lapWindowStart: null,
      lapWindowEnd: null,
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      lockState: "none",
      trustTier: lapTrustTier(lap),
      valueBasis: "full_lap",
      selectionSource: "laps",
    }, workspace);
  }, [focusEvidence, overview.run_id]);

  const focusWindowEvidence = useCallback((window: LapWindowSummary, workspace?: "platform_trace" | "map") => {
    const representative = representativeLapByWindowId.get(window.window_id) ?? deriveRepresentativeLap(window, laps);
    focusEvidence({
      runId: overview.run_id,
      lapNumber: representative.lapNumber,
      lapScope: "lap_window",
      lapWindowStart: window.start_lap,
      lapWindowEnd: window.end_lap,
      representativeLap: representative.lapNumber,
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      lockState: "none",
      trustTier: windowTrustTier(window),
      valueBasis: "selected_window",
      selectionSource: "laps",
    }, workspace);
  }, [focusEvidence, laps, overview.run_id, representativeLapByWindowId]);

  const makeLapBasket = useCallback((lap: LapSummary, label: string) => makeBasketItem(
    overview.run_id,
    lap.lap_number,
    label,
    overview.session.car_name ?? null,
    (overview.session.track_display_name ?? overview.session.track_name) ?? null,
    overview.session.setup_name ?? null,
    lap.lap_time ?? null,
    lap.classification_tags ?? [],
    null,
    overview.session.import_time ?? null,
    overview.session.session_type ?? null,
    overview.setup_snapshot != null,
    {
      lapScope: "single_lap",
      trustTier: lapTrustTier(lap),
      valueBasis: "full_lap",
    },
  ), [overview]);

  const makeWindowBasket = useCallback((window: LapWindowSummary, label: string) => makeBasketItem(
    overview.run_id,
    (representativeLapByWindowId.get(window.window_id) ?? deriveRepresentativeLap(window, laps)).lapNumber,
    label,
    overview.session.car_name ?? null,
    (overview.session.track_display_name ?? overview.session.track_name) ?? null,
    overview.session.setup_name ?? null,
    window.average_lap_time ?? null,
    window.classification_tags ?? [],
    window.setup_usefulness_score ?? null,
    overview.session.import_time ?? null,
    overview.session.session_type ?? null,
    overview.setup_snapshot != null,
    {
      lapScope: "lap_window",
      lapWindowStart: window.start_lap,
      lapWindowEnd: window.end_lap,
      representativeLap: (representativeLapByWindowId.get(window.window_id) ?? deriveRepresentativeLap(window, laps)).lapNumber,
      trustTier: windowTrustTier(window),
      valueBasis: "selected_window",
    },
  ), [laps, overview, representativeLapByWindowId]);

  const stintToWindowSummary = useCallback((stint: StintSummary): LapWindowSummary => ({
    window_id: stint.stint_id,
    run_id: stint.run_id,
    car_name: stint.car_name,
    track_name: stint.track_name,
    start_lap: stint.start_lap,
    end_lap: stint.end_lap,
    window_size: stint.lap_count,
    total_time: stint.avg_lap_time != null ? stint.avg_lap_time * stint.valid_lap_count : null,
    average_lap_time: stint.avg_lap_time,
    fastest_lap_time: stint.best_lap_time,
    slowest_lap_time: stint.worst_lap_time,
    lap_time_std_dev: stint.lap_time_std_dev,
    falloff_sec: stint.falloff_total,
    falloff_sec_per_lap: stint.falloff_per_lap,
    consistency_score: stint.consistency_score ?? 0,
    valid_lap_count: stint.valid_lap_count,
    excluded_laps: [],
    classification_tags: [],
    platform_risk_peak: null,
    rear_platform_risk_peak: null,
    whole_car_bottoming_peak: null,
    tire_stress_score: 0,
    shock_stress_score: 0,
    confidence_score: stint.evidence_confidence_score ?? 0,
    warnings: stint.warnings,
    recommendation: stint.stint_label,
    pace_quality_score: stint.pace_quality_score,
    pace_quality_label: null,
    evidence_confidence_score: stint.evidence_confidence_score,
    evidence_confidence_label: null,
    setup_usefulness_score: stint.setup_usefulness_score,
    setup_usefulness_label: null,
    pace_quality_warnings: stint.warnings,
    pace_quality_components: null,
  }), []);

  const makeStintBasket = useCallback((stint: StintSummary, label: string) => makeBasketItem(
    stint.run_id,
    stint.start_lap,
    label,
    stint.car_name ?? overview.session.car_name ?? null,
    stint.track_name ?? (overview.session.track_display_name ?? overview.session.track_name) ?? null,
    stint.setup_name ?? overview.session.setup_name ?? null,
    stint.avg_lap_time ?? null,
    [],
    stint.setup_usefulness_score ?? null,
    stint.session_date ?? overview.session.import_time ?? null,
    overview.session.session_type ?? null,
    overview.setup_snapshot != null,
    {
      lapScope: "lap_window",
      lapWindowStart: stint.start_lap,
      lapWindowEnd: stint.end_lap,
      representativeLap: stint.start_lap,
      trustTier: stint.evidence_confidence_score != null ? `Trust ${stint.evidence_confidence_score.toFixed(0)}` : "Trust unavailable",
      valueBasis: "selected_window",
    },
  ), [overview]);

  const addStintToGraph = useCallback((stintId: string) => {
    setGraphStintIds((ids) => ids.includes(stintId) ? ids : [...ids, stintId]);
  }, []);

  const removeStintFromGraph = useCallback((stintId: string) => {
    setGraphStintIds((ids) => ids.filter((id) => id !== stintId));
  }, []);

  const loadHistoryRunStints = useCallback((runId: string) => {
    if (runId === overview.run_id || historyStintData[runId] || historyStintsLoading[runId]) return;
    setHistoryStintsLoading((current) => ({ ...current, [runId]: true }));
    fetchStints(runId)
      .then((response) => setHistoryStintData((current) => ({ ...current, [runId]: response })))
      .catch(() => setHistoryStintData((current) => {
        const next = { ...current };
        delete next[runId];
        return next;
      }))
      .finally(() => setHistoryStintsLoading((current) => ({ ...current, [runId]: false })));
  }, [historyStintData, historyStintsLoading, overview.run_id]);

  const toggleHistoryRun = useCallback((runId: string) => {
    const willExpand = !expandedRunIds.has(runId);
    setExpandedRunIds((current) => {
      const next = new Set(current);
      if (next.has(runId)) {
        if (runId !== overview.run_id) next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
    if (willExpand) loadHistoryRunStints(runId);
  }, [expandedRunIds, loadHistoryRunStints, overview.run_id]);

  const runHistory = useMemo(() => {
    const current: RunListItem = {
      run_id: overview.run_id,
      car_name: overview.session.car_name ?? null,
      track_name: overview.session.track_display_name ?? overview.session.track_name ?? null,
      setup_name: overview.session.setup_name ?? null,
      imported_at: overview.session.import_time ?? null,
      best_lap_number: overview.best_useful_lap?.lap_number ?? null,
      best_lap_time: overview.best_useful_lap?.lap_time ?? bestTime,
      lap_count: laps.length,
      has_setup_snapshot: overview.setup_snapshot != null,
      primary_issue: overview.primary_findings?.[0] ?? null,
    };
    const byId = new Map<string, RunListItem>();
    byId.set(current.run_id, current);
    sessionRuns.forEach((run) => {
      if (session?.run_ids.includes(run.run_id)) {
        byId.set(run.run_id, run);
      }
    });
    const orderedSessionRuns = session?.run_ids
      .map((runId) => byId.get(runId))
      .filter((run): run is RunListItem => run != null && run.run_id !== overview.run_id)
      ?? [];
    return [current, ...orderedSessionRuns];
  }, [bestTime, laps.length, overview, session, sessionRuns]);

  const sessionRunsSubtitle = useMemo(() => {
    if (runHistory.length <= 1) {
      return "Only the current run is shown. Add runs to this session to compare stints.";
    }
    if (sessionSelectionSource === "existing") {
      return "Runs from the loaded session.";
    }
    return "Current run and runs added to this open session.";
  }, [runHistory.length, sessionSelectionSource]);

  const graphStints = useMemo(() => {
    const explicit = graphStintIds
      .map((id) => stintSelectionCandidates.find((stint) => stint.stint_id === id))
      .filter((stint): stint is StintSummary => stint != null);
    if (explicit.length > 0) return explicit;
    const compared = [baselineStint, testStint].filter((stint): stint is StintSummary => stint != null);
    if (compared.length > 0) return compared;
    return stints[0] ? [stints[0]] : [];
  }, [baselineStint, graphStintIds, stintSelectionCandidates, stints, testStint]);

  const graphChart = useMemo(() => {
    const colors = ["#38bdf8", "#f59e0b", "#22c55e", "#a78bfa", "#fb7185", "#facc15"];
    const series = graphStints.flatMap((stint, index) => {
      const seriesColor = baselineStintId === stint.stint_id ? "#38bdf8" : testStintId === stint.stint_id ? "#f59e0b" : colors[index % colors.length];
      const basePoints = stint.lap_points
        .filter((point) => point.lap_time != null)
        .map((point) => ({
          id: `${stint.stint_id}:${point.lap_number}`,
          seriesId: stint.stint_id,
          x: point.stint_lap,
          stintLap: point.stint_lap,
          lapNumber: point.lap_number,
          y: stintGraphMode === "delta"
            ? point.delta_to_best
            : stintGraphMode === "rolling_5"
              ? point.rolling_5
              : point.lap_time,
          valid: point.valid,
          excludedFromScale: false,
          exclusionReason: null,
          outlierAboveScale: false,
          outlierBelowScale: false,
          lapTime: point.lap_time,
          deltaToBest: point.delta_to_best,
          rolling5: point.rolling_5,
          invalidReason: point.invalid_reason,
          warning: point.warning,
        }))
        .filter((point) => point.y != null)
        .map((point): StintGraphRawPoint => ({ ...point, y: point.y as number }));
      const rows = [{
        id: stint.stint_id,
        label: `${stint.display_label_short} ${formatStintRange(stint)}`,
        color: seriesColor,
        dashed: false,
        stint,
        points: basePoints,
      }];
      if (showRolling5 && stintGraphMode === "lap_time") {
        const rollingPoints = stint.lap_points
          .filter((point) => !excludeInvalidGraphLaps || point.valid)
          .map((point) => ({
            id: `${stint.stint_id}:rolling5:${point.lap_number}`,
            seriesId: stint.stint_id,
            x: point.stint_lap,
            stintLap: point.stint_lap,
            lapNumber: point.lap_number,
            y: point.rolling_5,
            valid: point.valid,
            excludedFromScale: false,
            exclusionReason: null,
            outlierAboveScale: false,
            outlierBelowScale: false,
            lapTime: point.lap_time,
            deltaToBest: point.delta_to_best,
            rolling5: point.rolling_5,
            invalidReason: point.invalid_reason,
            warning: point.warning,
          }))
          .filter((point) => point.y != null)
          .map((point): StintGraphRawPoint => ({ ...point, y: point.y as number }));
        if (rollingPoints.length > 0) {
          rows.push({
            id: `${stint.stint_id}:rolling5`,
            label: `${stint.display_label_short} rolling 5`,
            color: seriesColor,
            dashed: true,
            stint,
            points: rollingPoints,
          });
        }
      }
      return rows;
    });
    const allRawPoints = series.flatMap((item) => item.points);
    const visibleRawPoints = allRawPoints.filter((point) => !excludeInvalidGraphLaps || point.valid);
    const scaleCandidateValues = visibleRawPoints
      .filter((point) => point.valid || includeOutliersInScale)
      .map((point) => point.y);
    if (visibleRawPoints.length === 0) {
      return {
        series: series.map((item) => ({ ...item, points: [] as StintGraphRenderPoint[] })),
        xMin: 1,
        xMax: 1,
        yMin: 0,
        yMax: 1,
        xTicks: [1],
        yTicks: [0, 0.25, 0.5, 0.75, 1],
        bucketGuides: [] as number[],
        zeroLineY: null as number | null,
        scaleLabel: "Scale: Race pace",
        validLapCount: 0,
        excludedLapCount: allRawPoints.length,
        fastestValidLap: null as number | null,
        bestRolling5: null as number | null,
        bestRolling10: bestSustainedStint?.rolling_10_avg_best ?? null,
        selectedLapDetail: null as StintGraphRenderPoint | null,
      };
    }
    const domain = racePaceDomain(scaleCandidateValues.length > 0 ? scaleCandidateValues : visibleRawPoints.map((point) => point.y), includeOutliersInScale);
    const xMin = Math.min(...visibleRawPoints.map((point) => point.x));
    const xMax = Math.max(...visibleRawPoints.map((point) => point.x));
    const xSpan = Math.max(1, Math.max(xMin + 1, xMax) - xMin);
    const yMin = domain.min;
    const yMax = domain.max;
    const ySpan = Math.max(0.001, yMax - yMin);
    const seriesWithCoords = series.map((item) => ({
      ...item,
      points: item.points
        .filter((point) => !excludeInvalidGraphLaps || point.valid)
        .map((point) => {
          const invalidExcluded = !point.valid && !includeOutliersInScale;
          const highOutlier = !includeOutliersInScale && point.y > domain.outlierHigh;
          const lowOutlier = !includeOutliersInScale && point.y < domain.outlierLow;
          const aboveScale = point.y > yMax;
          const belowScale = point.y < yMin;
          const clampedY = Math.min(yMax, Math.max(yMin, point.y));
          const exclusionReason = invalidExcluded
            ? point.warning ?? "invalid lap"
            : highOutlier || lowOutlier || aboveScale || belowScale
              ? "outlier excluded from pace scale"
              : null;
          return {
            ...point,
            excludedFromScale: exclusionReason != null,
            exclusionReason,
            outlierAboveScale: aboveScale || highOutlier,
            outlierBelowScale: belowScale || lowOutlier,
            sourceLabel: item.label,
            color: item.color,
            screenX: CHART_PAD_LEFT + ((point.x - xMin) / xSpan) * (CHART_WIDTH - CHART_PAD_LEFT - CHART_PAD_RIGHT),
            screenY: CHART_PAD_TOP + (1 - ((clampedY - yMin) / ySpan)) * (CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM),
          };
        }),
    }));
    const validLapTimes = visibleRawPoints.filter((point) => point.valid && point.lapTime != null).map((point) => point.lapTime as number);
    const rolling5Values = visibleRawPoints.filter((point) => point.valid && point.rolling5 != null).map((point) => point.rolling5 as number);
    const excludedLapCount = seriesWithCoords.flatMap((item) => item.points).filter((point) => point.excludedFromScale || !point.valid).length;
    const selectedLapCandidate = selectedGraphLap != null
      ? seriesWithCoords
        .flatMap((item) => item.points)
        .find((point) => point.seriesId === selectedGraphLap.stintId && point.lapNumber === selectedGraphLap.lapNumber)
      : selection.selectedLap != null
        ? seriesWithCoords.flatMap((item) => item.points).find((point) => point.lapNumber === selection.selectedLap)
        : null;
    const highlightedTicks = [
      selectedLapCandidate?.x ?? null,
      baselineStint?.start_lap != null ? 1 : null,
      testStint?.start_lap != null ? 1 : null,
    ].filter((value): value is number => value != null);
    const xTicks = buildXAxisTicks(xMin, Math.max(xMin + 1, xMax), highlightedTicks);
    const yTicks = buildYAxisTicks(yMin, yMax);
    const bucketGuides = [5, 10, 15, 20, 25, 30, 40, 50, 60].filter((value) => value > xMin && value < Math.max(xMin + 1, xMax));
    const zeroLineY = stintGraphMode === "delta" && yMin <= 0 && yMax >= 0 ? chartY(0, yMin, yMax) : null;
    return {
      series: seriesWithCoords,
      xMin,
      xMax: Math.max(xMin + 1, xMax),
      yMin,
      yMax,
      xTicks,
      yTicks,
      bucketGuides,
      zeroLineY,
      scaleLabel: includeOutliersInScale ? "Scale: Full range" : "Scale: Race pace",
      validLapCount: validLapTimes.length,
      excludedLapCount,
      fastestValidLap: validLapTimes.length > 0 ? Math.min(...validLapTimes) : null,
      bestRolling5: rolling5Values.length > 0 ? Math.min(...rolling5Values) : null,
      bestRolling10: bestSustainedStint?.rolling_10_avg_best ?? null,
      selectedLapDetail: selectedLapCandidate ?? null,
    };
  }, [baselineStint, baselineStintId, bestSustainedStint, excludeInvalidGraphLaps, graphStints, includeOutliersInScale, selectedGraphLap, selection.selectedLap, showRolling5, stintGraphMode, testStint, testStintId]);

  const summaryDrawerStint = useMemo(
    () => summaryDrawerStintId
      ? stintSelectionCandidates.find((stint) => stint.stint_id === summaryDrawerStintId) ?? null
      : null,
    [stintSelectionCandidates, summaryDrawerStintId],
  );

  const visibleStints = useMemo(
    () => stints.filter((stint) => {
      if (graphedOnlyFilter && !graphStintIds.includes(stint.stint_id)) return false;
      if (hideInvalidRowsFilter && stint.valid_lap_count < stint.lap_count) return false;
      return true;
    }),
    [graphStintIds, graphedOnlyFilter, hideInvalidRowsFilter, stints],
  );

  const visibleBestWindowCards = useMemo(
    () => bestWindowCards.filter((stint) => {
      if (graphedOnlyFilter && !graphStintIds.includes(stint.stint_id)) return false;
      if (hideInvalidRowsFilter && stint.valid_lap_count < stint.lap_count) return false;
      return true;
    }),
    [bestWindowCards, graphStintIds, graphedOnlyFilter, hideInvalidRowsFilter],
  );

  const visibleRunHistory = useMemo(
    () => runHistory.filter((run) => {
      if (currentRunOnlyFilter && run.run_id !== overview.run_id) return false;
      if (sameCarTrackOnlyFilter && run.run_id !== overview.run_id) {
        const trackName = overview.session.track_display_name ?? overview.session.track_name ?? null;
        if (run.car_name !== overview.session.car_name || run.track_name !== trackName) return false;
      }
      if (graphedOnlyFilter && run.run_id !== overview.run_id) {
        const response = historyStintData[run.run_id];
        const ids = [
          ...(response?.stint_rows ?? []),
          ...(response?.best_window_cards ?? []),
          ...(response?.all_windows ?? []),
        ].map((stint) => stint.stint_id);
        if (!ids.some((id) => graphStintIds.includes(id))) return false;
      }
      return true;
    }).sort((left, right) => {
      const leftPinned = pinnedRunIds.has(left.run_id);
      const rightPinned = pinnedRunIds.has(right.run_id);
      if (leftPinned !== rightPinned) return leftPinned ? -1 : 1;
      return 0;
    }),
    [currentRunOnlyFilter, graphStintIds, graphedOnlyFilter, historyStintData, overview.run_id, overview.session.car_name, overview.session.track_display_name, overview.session.track_name, pinnedRunIds, runHistory, sameCarTrackOnlyFilter],
  );

  const exportSelectedStintsCsv = useCallback(() => {
    const selectedForExport = (graphStintIds.length > 0 ? graphStintIds : selectedStint ? [selectedStint.stint_id] : [])
      .map((id) => stintSelectionCandidates.find((stint) => stint.stint_id === id))
      .filter((stint): stint is StintSummary => stint != null);
    if (selectedForExport.length === 0) return;
    const headers = [
      "run_id",
      "setup_name",
      "track_name",
      "car_name",
      "session_date",
      "stint_id",
      "stint_label",
      "lap_number",
      "stint_lap",
      "lap_time",
      "delta_to_best",
      "rolling_5",
      "valid",
      "invalid_reason",
      "avg_speed_mph",
      "max_speed_mph",
      "min_speed_mph",
      "fuel",
      "tire_trend_label",
      "platform_trend_label",
      "shock_trend_label",
    ];
    const rows = selectedForExport.flatMap((stint) => stint.lap_points.map((point) => [
      stint.run_id,
      stint.setup_name,
      stint.track_name,
      stint.car_name,
      stint.session_date,
      stint.stint_id,
      stint.display_label_short,
      point.lap_number,
      point.stint_lap,
      point.lap_time,
      point.delta_to_best,
      point.rolling_5,
      point.valid,
      point.invalid_reason ?? point.warning,
      point.avg_speed_mph,
      point.max_speed_mph,
      point.min_speed_mph,
      point.fuel,
      stint.tire_trend_label,
      stint.platform_trend_label,
      stint.shock_trend_label,
    ]));
    const csv = [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    link.href = url;
    link.download = `racelab-stints-${stamp}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }, [graphStintIds, selectedStint, stintSelectionCandidates]);

  const compareRoleForLap = useCallback((lapNumber: number): string | null => {
    if (basket.baseline?.run_id === overview.run_id && basket.baseline.lap_scope !== "lap_window" && basket.baseline.lap_number === lapNumber) return "Baseline";
    if (basket.test?.run_id === overview.run_id && basket.test.lap_scope !== "lap_window" && basket.test.lap_number === lapNumber) return "Test";
    return null;
  }, [basket.baseline, basket.test, overview.run_id]);

  const selectedWindow = selection.selectedLapScope === "lap_window"
    ? { start: selection.selectedLapWindowStart ?? null, end: selection.selectedLapWindowEnd ?? null }
    : null;

  const graphRangeOverlays = useMemo(() => {
    const pointLookup = new Map<string, StintGraphRenderPoint>();
    graphChart.series
      .filter((series) => !series.dashed)
      .forEach((series) => {
        series.points.forEach((point) => {
          const key = `${point.seriesId}:${point.lapNumber}`;
          if (!pointLookup.has(key)) pointLookup.set(key, point);
        });
      });

    const overlays: Array<{
      key: string;
      label: string;
      startX: number;
      endX: number;
      className: string;
    }> = [];

    const pushRange = (
      key: string,
      label: string,
      className: string,
      matcher: (point: StintGraphRenderPoint) => boolean,
    ) => {
      const matching = [...pointLookup.values()].filter(matcher);
      if (matching.length === 0) return;
      const xs = matching.map((point) => point.screenX);
      overlays.push({
        key,
        label,
        startX: Math.min(...xs),
        endX: Math.max(...xs),
        className,
      });
    };

    if (selectedStint) {
      pushRange(
        `selected:${selectedStint.stint_id}`,
        `Selected Stint - ${formatStintRange(selectedStint)}`,
        "selected",
        (point) => point.seriesId === selectedStint.stint_id,
      );
    }
    if (selectedWindow?.start != null && selectedWindow.end != null) {
      const selectedWindowStart = selectedWindow.start;
      const selectedWindowEnd = selectedWindow.end;
      pushRange(
        `selection-window:${selectedWindowStart}:${selectedWindowEnd}`,
        `Selected Window - Laps ${selectedWindowStart}-${selectedWindowEnd}`,
        "selected-window",
        (point) => point.lapNumber >= selectedWindowStart && point.lapNumber <= selectedWindowEnd,
      );
    }
    if (baselineStint) {
      pushRange(
        `baseline:${baselineStint.stint_id}`,
        `Baseline - ${formatStintRange(baselineStint)}`,
        "baseline",
        (point) => point.seriesId === baselineStint.stint_id,
      );
    }
    if (testStint) {
      pushRange(
        `test:${testStint.stint_id}`,
        `Test - ${formatStintRange(testStint)}`,
        "test",
        (point) => point.seriesId === testStint.stint_id,
      );
    }
    if (
      basket.baseline?.run_id === overview.run_id
      && basket.baseline.lap_scope === "lap_window"
      && basket.baseline.lap_window_start != null
      && basket.baseline.lap_window_end != null
    ) {
      pushRange(
        `baseline-window:${basket.baseline.lap_window_start}:${basket.baseline.lap_window_end}`,
        `Baseline Window - Laps ${basket.baseline.lap_window_start}-${basket.baseline.lap_window_end}`,
        "baseline-window",
        (point) => point.lapNumber >= basket.baseline!.lap_window_start! && point.lapNumber <= basket.baseline!.lap_window_end!,
      );
    }
    if (
      basket.test?.run_id === overview.run_id
      && basket.test.lap_scope === "lap_window"
      && basket.test.lap_window_start != null
      && basket.test.lap_window_end != null
    ) {
      pushRange(
        `test-window:${basket.test.lap_window_start}:${basket.test.lap_window_end}`,
        `Test Window - Laps ${basket.test.lap_window_start}-${basket.test.lap_window_end}`,
        "test-window",
        (point) => point.lapNumber >= basket.test!.lap_window_start! && point.lapNumber <= basket.test!.lap_window_end!,
      );
    }
    return overlays;
  }, [baselineStint, basket.baseline, basket.test, graphChart.series, overview.run_id, selectedStint, selectedWindow, testStint]);

  const graphStatusesForPoint = useCallback((point: StintGraphRenderPoint): string[] => {
    const statuses = new Set<string>();
    if (
      (selectedGraphLap != null && point.seriesId === selectedGraphLap.stintId && point.lapNumber === selectedGraphLap.lapNumber)
      || (selection.selectedLap != null && point.lapNumber === selection.selectedLap)
    ) {
      statuses.add("Selected lap");
    }
    if (selectedStint && point.seriesId === selectedStint.stint_id) statuses.add("Selected stint");
    if (selectedWindow?.start != null && selectedWindow.end != null && point.lapNumber >= selectedWindow.start && point.lapNumber <= selectedWindow.end) {
      statuses.add("Selected window");
    }
    if (baselineStint && point.seriesId === baselineStint.stint_id) statuses.add("Baseline stint");
    if (testStint && point.seriesId === testStint.stint_id) statuses.add("Test stint");
    if (
      basket.baseline?.run_id === overview.run_id
      && basket.baseline.lap_scope === "lap_window"
      && basket.baseline.lap_window_start != null
      && basket.baseline.lap_window_end != null
      && point.lapNumber >= basket.baseline.lap_window_start
      && point.lapNumber <= basket.baseline.lap_window_end
    ) {
      statuses.add("Baseline window");
    }
    if (
      basket.test?.run_id === overview.run_id
      && basket.test.lap_scope === "lap_window"
      && basket.test.lap_window_start != null
      && basket.test.lap_window_end != null
      && point.lapNumber >= basket.test.lap_window_start
      && point.lapNumber <= basket.test.lap_window_end
    ) {
      statuses.add("Test window");
    }
    const compareRole = compareRoleForLap(point.lapNumber);
    if (compareRole === "Baseline") statuses.add("Baseline lap");
    if (compareRole === "Test") statuses.add("Test lap");
    return [...statuses];
  }, [baselineStint, basket.baseline, basket.test, compareRoleForLap, overview.run_id, selectedGraphLap, selectedStint, selectedWindow, selection.selectedLap, testStint]);


  const renderEvidenceActions = useCallback((item: EvidenceDescriptor, compact = false, mode: "full" | "compare_inline" = "full") => {
    const isWindow = item.scope === "lap_window" && item.window;
    const isLap = item.scope === "single_lap" && item.lap;
    if (!isWindow && !isLap) return null;
    const hasWindowContext = item.window != null
      && item.window.start_lap != null
      && item.window.end_lap != null;
    const hasLapContext = item.lap != null && item.lap.lap_number != null;
    const canStage = hasWindowContext || hasLapContext;
    const canOpenPlatform = canStage;
    const disabledReason = "Not available for this run";

    const handleSelect = () => {
      if (item.window) focusWindowEvidence(item.window);
      if (item.lap) focusLapEvidence(item.lap);
    };

    const handlePlatform = () => {
      if (item.window) focusWindowEvidence(item.window, "platform_trace");
      if (item.lap) focusLapEvidence(item.lap, "platform_trace");
    };

    const handleMap = () => {
      if (item.window) focusWindowEvidence(item.window, "map");
      if (item.lap) focusLapEvidence(item.lap, "map");
    };

    const handleBaseline = () => {
      if (item.window) setBaseline(makeWindowBasket(item.window, `${item.title} ${formatWindowRange(item.window)}`));
      if (item.lap) setBaseline(makeLapBasket(item.lap, `${item.title} Lap ${item.lap.lap_number}`));
    };

    const handleTest = () => {
      if (item.window) setTest(makeWindowBasket(item.window, `${item.title} ${formatWindowRange(item.window)}`));
      if (item.lap) setTest(makeLapBasket(item.lap, `${item.title} Lap ${item.lap.lap_number}`));
    };

    const handleBasket = () => {
      if (item.window) addToQueue(makeWindowBasket(item.window, `${item.title} ${formatWindowRange(item.window)}`));
      if (item.lap) addToQueue(makeLapBasket(item.lap, `${item.title} Lap ${item.lap.lap_number}`));
    };

    if (mode === "compare_inline") {
      return (
        <div className="laps-inline-compare-actions">
          <button className="secondary-button" onClick={handleBaseline} disabled={!canStage} title={canStage ? "Stage this evidence as baseline" : disabledReason} aria-label="Set baseline from evidence">
            <Clock size={14} /> Set Baseline
          </button>
          <button className="secondary-button" onClick={handleTest} disabled={!canStage} title={canStage ? "Stage this evidence as test" : disabledReason} aria-label="Set test from evidence">
            <Gauge size={14} /> Set Test
          </button>
          <button className="secondary-button" onClick={handlePlatform} disabled={!canOpenPlatform} title={canOpenPlatform ? "Open Platform with this evidence context" : disabledReason} aria-label="Open evidence in Platform">
            <Layers size={14} /> Open Platform
          </button>
          <button className="secondary-button" onClick={handleMap} disabled={!canStage} title={canStage ? "Open Map with this evidence context" : disabledReason} aria-label="Open evidence on Map">
            <MapPin size={14} /> Open Map
          </button>
        </div>
      );
    }

    return (
      <div className={`laps-action-row${compact ? " compact" : ""}`}>
        <button className="secondary-button" onClick={handleBaseline} disabled={!canStage} title={canStage ? "Stage as compare baseline" : disabledReason} aria-label="Set baseline from evidence">
          <Clock size={14} /> Baseline
        </button>
        <button className="secondary-button" onClick={handleTest} disabled={!canStage} title={canStage ? "Stage as compare test" : disabledReason} aria-label="Set test from evidence">
          <Gauge size={14} /> Test
        </button>
        <button className="secondary-button" onClick={handlePlatform} disabled={!canOpenPlatform} title={canOpenPlatform ? "Open Platform with this evidence context" : disabledReason} aria-label="Open evidence in Platform">
          <Layers size={14} /> Platform
        </button>
        <button className="secondary-button" onClick={handleMap} disabled={!canStage} title={canStage ? "Open Map with this evidence context" : disabledReason} aria-label="Open evidence on Map">
          <MapPin size={14} /> Map
        </button>
        <button className="secondary-button" onClick={handleSelect} disabled={!canStage} title={canStage ? "Use this evidence as current selection" : disabledReason} aria-label={isWindow ? "Select window evidence" : "Select lap evidence"}>
          <Target size={14} /> {isWindow ? "Select Window" : "Select Evidence"}
        </button>
        <button className="secondary-button" onClick={handleBasket} disabled={!canStage} title={canStage ? "Add evidence to Test Basket queue" : disabledReason} aria-label="Add evidence to Test Basket">
          <BarChart3 size={14} /> Basket
        </button>
      </div>
    );
  }, [addToQueue, focusLapEvidence, focusWindowEvidence, makeLapBasket, makeWindowBasket, setBaseline, setTest]);

  const renderDescriptorSummary = useCallback((item: EvidenceDescriptor) => {
    const headline = item.window
      ? formatWindowRange(item.window)
      : item.lap
        ? `Lap ${item.lap.lap_number}`
        : "Unavailable";
    const timeLabel = item.window
      ? item.window.average_lap_time != null
        ? `Avg ${formatTime(item.window.average_lap_time)}`
        : "Avg unavailable"
      : item.lap
        ? formatTime(item.lap.lap_time)
        : "Unavailable";
    const paceMeta = item.window
      ? item.window.pace_quality_score != null
        ? `Pace ${item.window.pace_quality_score.toFixed(0)}`
        : "Pace unavailable"
      : item.lap && item.lap.lap_time != null && bestTime != null
        ? `Delta ${formatDelta(item.lap.lap_time, bestTime)}`
        : "Pace reference unavailable";

    return (
      <>
        <div className="laps-evidence-headline">
          <span className="eyebrow">{item.title}</span>
          <strong>{headline}</strong>
          <span className="muted">{timeLabel}</span>
        </div>
        <div className="laps-chip-row">
          <span className="lap-flag-badge">{item.basisLabel}</span>
          <span className="lap-flag-badge" style={{ background: "rgba(56,189,248,0.12)", color: "#38bdf8" }}>
            {item.trustTier ? `Trust: ${item.trustTier}` : "Trust unavailable"}
          </span>
          <span className="lap-flag-badge" style={{ background: "rgba(34,197,94,0.12)", color: "#22c55e" }}>
            {paceMeta}
          </span>
          {item.engineeringValue != null && (
            <span className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>
              EV {item.engineeringValue.toFixed(0)}
            </span>
          )}
          {item.scope === "lap_window" && item.representativeLap != null && (
            <span className="lap-flag-badge" style={{ background: "rgba(148,163,184,0.12)", color: "#cbd5e1" }}>
              Rep Lap {item.representativeLap}
            </span>
          )}
          {item.lap?.min_splitter_mm != null && (
            <span className="lap-flag-badge" style={{ background: "rgba(148,163,184,0.12)", color: "#cbd5e1" }}>
              Min splitter {item.lap.min_splitter_mm.toFixed(1)} mm
            </span>
          )}
        </div>
        <p className="section-note" style={{ marginBottom: 8 }}>{item.note}</p>
        {item.scope === "lap_window" && item.representativeReason && (
          <p className="section-note" style={{ marginTop: -4, marginBottom: 8 }}>
            Representative lap: {item.representativeLap != null ? `Lap ${item.representativeLap}` : "Unavailable"}.
            {" "}{item.representativeReason}.
          </p>
        )}
        {(item.flags.length > 0 || item.reasons.length > 0) && (
          <div className="laps-chip-row">
            {item.flags.map((flag) => (
              <span key={flag} className="lap-flag-badge">{flag}</span>
            ))}
            {item.reasons.map((reason) => (
              <span key={reason} className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>{reason}</span>
            ))}
          </div>
        )}
      </>
    );
  }, [bestTime]);

  return (
    <div className="tab-grid">
      <section className="workspace-section">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h2><Clock size={18} /> Laps</h2>
            <p className="section-note" style={{ marginBottom: 0 }}>
              Stint timing, best-window evidence, session runs, and baseline/test review for the current imported data.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span className="muted">{overview.session.track_display_name ?? overview.session.track_name} - {overview.session.car_name}</span>
          </div>
        </div>
        <div className="laps-chip-row" style={{ marginTop: 8 }}>
          <span className="lap-flag-badge">Valid laps {windowsData?.total_valid_laps ?? usefulLaps.length}/{windowsData?.total_laps ?? laps.length}</span>
          {selection.selectedLapScope === "lap_window" && selection.selectedLapWindowStart != null && selection.selectedLapWindowEnd != null ? (
            <span className="lap-flag-badge" style={{ background: "rgba(56,189,248,0.12)", color: "#38bdf8" }}>
              Current selection: Window {selection.selectedLapWindowStart}-{selection.selectedLapWindowEnd}
              {selection.selectedRepresentativeLap != null ? ` · Rep Lap ${selection.selectedRepresentativeLap}` : ""}
            </span>
          ) : selection.selectedLap != null ? (
            <span className="lap-flag-badge" style={{ background: "rgba(56,189,248,0.12)", color: "#38bdf8" }}>
              Current selection: Lap {selection.selectedLap}
            </span>
          ) : null}
          {windowsData && windowsData.total_valid_laps < 10 && (
            <span className="lap-flag-badge" style={{ background: "rgba(239,68,68,0.12)", color: "#ef4444" }}>
              <AlertTriangle size={12} /> Need 10+ valid laps for deeper window analysis
            </span>
          )}
        </div>
      </section>

        <section className="workspace-section stint-intelligence-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Imported Data</span>
              <h2><BarChart3 size={16} /> My Stints</h2>
              <p className="section-note">
                Lap averages, falloff, and long-run pace from your imported runs.
              </p>
            </div>
          </div>

          {stintData?.warnings && stintData.warnings.length > 0 && (
            <div className="laps-chip-row" style={{ marginBottom: 10 }}>
              {stintData.warnings.slice(0, 4).map((warning) => (
                <span key={warning} className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>{warning}</span>
              ))}
            </div>
          )}

          <div className="stint-run-summary">
            <div>
              <span className="eyebrow">Run / Setup</span>
              <strong>{stintData?.run_summary?.setup_name ?? overview.session.setup_name ?? "Setup unknown"}</strong>
              <span className="muted">{stintData?.run_summary?.track_name ?? overview.session.track_display_name ?? overview.session.track_name ?? "-"} - {stintData?.run_summary?.car_name ?? overview.session.car_name ?? "-"}</span>
            </div>
            <div><span>Total</span><strong>{stintData?.run_summary?.total_laps ?? windowsData?.total_laps ?? laps.length}</strong></div>
            <div><span>Valid</span><strong>{stintData?.run_summary?.valid_laps ?? windowsData?.total_valid_laps ?? usefulLaps.length}</strong></div>
            <div><span>Best Lap</span><strong>{formatTime(stintData?.run_summary?.best_lap_time ?? bestTime)}</strong></div>
            <div><span>Best Sustained</span><strong>{bestSustainedStint ? `${bestSustainedStint.display_label_short} ${formatTime(bestSustainedStint.avg_lap_time)}` : "-"}</strong></div>
            <div><span>Data</span><strong>{stintData?.run_summary?.data_status ?? (stintData?.warnings?.length ? "Limited" : "Ready")}</strong></div>
          </div>

          {stintsLoading && <p className="muted">Loading stint windows...</p>}
          {!stintsLoading && visibleStints.length === 0 && visibleBestWindowCards.length === 0 && (
            <div className="stint-empty-state">
              <h3>No eligible stint windows yet.</h3>
              <p>Need at least 3 valid laps to start short-run averages.</p>
              <p className="muted">Need 10+ valid laps for meaningful long-run read.</p>
              <p className="muted">Need 50/60 valid laps for 50/60-lap averages.</p>
              <p className="muted">Out laps, pit laps, cooldowns, wrecks, and invalid laps are excluded.</p>
              <p className="muted">Import or select a longer clean run to unlock Stint Intelligence.</p>
            </div>
          )}
          {!stintsLoading && (visibleStints.length > 0 || visibleBestWindowCards.length > 0) && (
            <>
            {visibleStints.length > 0 && (
            <div className="stint-subsection">
              <span className="eyebrow">My Stints</span>
              <div className="stint-table-wrap">
                <table className="compact-table stint-table timing-sheet-table">
                  <thead>
                    <tr>
                      <th>Stint</th>
                      <th># Laps</th>
                      <th>Last Lap</th>
                      <th>Current Avg Lap</th>
                      <th>Fastest Lap</th>
                      {stintAverageColumns.map((column) => <th key={column.size}>{column.label}</th>)}
                      <th>Falloff</th>
                      <th>Consistency</th>
                      <th>Setup EV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleStints.map((stint) => {
                      const isBaseline = baselineStintId === stint.stint_id;
                      const isTest = testStintId === stint.stint_id;
                      const isSelected = selectedStint?.stint_id === stint.stint_id;
                      const isStrongest = strongestSetupStintId === stint.stint_id;
                      const hasLimitedWarning = stint.warnings.some((warning) => /limited|shorter|excluded/i.test(warning));
                      const fastestLapBest = bestFastestLapValue != null && stint.best_lap_time != null && Math.abs(stint.best_lap_time - bestFastestLapValue) < 0.0005;
                      const topSetupEv = bestSetupEvValue != null && stint.setup_usefulness_score != null && Math.abs(stint.setup_usefulness_score - bestSetupEvValue) < 0.0005;
                      return (
                        <tr
                          key={stint.stint_id}
                          className={`${isSelected ? "stint-row-selected" : ""} ${isBaseline ? "stint-row-baseline" : ""} ${isTest ? "stint-row-test" : ""} ${isStrongest ? "stint-row-strongest" : ""} ${hasLimitedWarning ? "stint-row-limited" : ""}`}
                          onClick={() => setSelectedStintId(stint.stint_id)}
                          onDoubleClick={() => setSummaryDrawerStintId(stint.stint_id)}
                        >
                          <td>
                            <strong>{stint.display_label_short}</strong>
                            <div className="muted">{formatStintRange(stint)}</div>
                            <div className="laps-chip-row compact">
                              <span className={trendBadgeClass(stint.stint_label)}>{stint.stint_label}</span>
                              {stint.is_best_long_run && <span className="lap-flag-badge">Best long-run</span>}
                              {(isStrongest || topSetupEv) && <span className="lap-flag-badge">Top EV</span>}
                              {hasLimitedWarning && <span className="lap-flag-badge" style={{ color: "#f59e0b" }}>Limited</span>}
                            </div>
                          </td>
                          <td>{stint.lap_count}</td>
                          <td>{formatTime(stint.last_lap_time)}</td>
                          <td>{formatTime(stint.avg_lap_time)}</td>
                          <td className={fastestLapBest ? "stint-bucket-cell fastest" : ""}>{formatTime(stint.best_lap_time)}</td>
                          {stintAverageColumns.map((column) => {
                            const avg = stintAverage(stint, column.size);
                            const bestAvg = bestAverageValues[column.size];
                            const bucketClass = bestAvg != null && avg != null && Math.abs(avg - bestAvg) < 0.0005
                              ? "stint-bucket-cell fastest"
                              : avg == null
                                ? "stint-bucket-cell unavailable"
                                : "stint-bucket-cell";
                            return (
                              <td
                                key={column.size}
                                className={bucketClass}
                                title={avg == null ? `Need ${column.size} valid laps for this average.` : undefined}
                              >
                                {avg != null ? formatTime(avg) : "\u2014"}
                              </td>
                            );
                          })}
                          <td className={stint.falloff_total != null && stint.falloff_total > 0.5 ? "falloff-warn-cell" : ""}>{stint.falloff_total != null ? `${stint.falloff_total > 0 ? "+" : ""}${stint.falloff_total.toFixed(2)}s` : "-"}</td>
                          <td>{formatScore(stint.consistency_score)}</td>
                          <td className={topSetupEv ? "stint-bucket-cell fastest" : ""} style={{ color: paceQualityColor(stint.setup_usefulness_score) }}>{formatScore(stint.setup_usefulness_score)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            )}

            <div className="stint-graph-panel">
              <div className="section-heading-row">
                <div>
                  <span className="eyebrow">Lap-Time Graph</span>
                  <h3><LineChart size={15} /> Main Graph</h3>
                  <p className="section-note">
                    {graphStintIds.length > 0
                      ? "Showing the selected stint lines."
                      : baselineStint || testStint
                        ? "Showing baseline/test stint lines."
                        : "Showing the current full-run pace curve until a stint is selected."}
                  </p>
                </div>
                {graphStintIds.length > 0 && (
                  <button className="secondary-button" onClick={() => setGraphStintIds([])} title="Clear explicit graph selections">
                    Clear
                  </button>
                )}
              </div>
              <div className="stint-graph-controls">
                <button className={`segmented-option ${stintGraphMode === "lap_time" ? "active" : ""}`} onClick={() => setStintGraphMode("lap_time")}>Lap Time</button>
                <button className={`segmented-option ${stintGraphMode === "delta" ? "active" : ""}`} onClick={() => setStintGraphMode("delta")}>Delta to Best</button>
                <button className={`segmented-option ${stintGraphMode === "rolling_5" ? "active" : ""}`} onClick={() => setStintGraphMode("rolling_5")}>Rolling 5</button>
              </div>
              {graphChart.series.some((series) => series.points.length > 0) ? (
                <div className="stint-graph-canvas">
                  <div className="stint-graph-summary-strip">
                    <span>Mode {stintGraphMode === "lap_time" ? "Lap Time" : stintGraphMode === "delta" ? "Delta to Best" : "Rolling 5"}</span>
                    <span>{graphChart.scaleLabel}</span>
                    <span>Graphing {graphChart.validLapCount} valid laps</span>
                    <span>{graphChart.excludedLapCount} excluded</span>
                    <span>Best {formatTime(graphChart.fastestValidLap)}</span>
                    <span>Best 5 {formatTime(graphChart.bestRolling5)}</span>
                    <span>Best 10 {formatTime(graphChart.bestRolling10)}</span>
                    <span>{graphStints.length} selected stint{graphStints.length === 1 ? "" : "s"}</span>
                  </div>
                  <svg
                    viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
                    role="img"
                    aria-label="Selected stint lap-time line chart"
                    onMouseLeave={() => setHoveredGraphPoint(null)}
                  >
                    {graphChart.bucketGuides.map((tick) => {
                      const x = chartX(tick, graphChart.xMin, graphChart.xMax);
                      return (
                        <line
                          key={`bucket:${tick}`}
                          x1={x}
                          y1={CHART_PAD_TOP}
                          x2={x}
                          y2={CHART_HEIGHT - CHART_PAD_BOTTOM}
                          className="stint-chart-bucket-guide"
                        />
                      );
                    })}
                    {graphChart.yTicks.map((tick) => {
                      const y = chartY(tick, graphChart.yMin, graphChart.yMax);
                      return (
                        <g key={`ytick:${tick.toFixed(4)}`}>
                          <line
                            x1={CHART_PAD_LEFT}
                            y1={y}
                            x2={CHART_WIDTH - CHART_PAD_RIGHT}
                            y2={y}
                            className="stint-chart-gridline"
                          />
                          <text x={CHART_PAD_LEFT - 8} y={y + 4} className="stint-chart-label stint-chart-label-y" textAnchor="end">
                            {graphYLabel(tick, stintGraphMode)}
                          </text>
                        </g>
                      );
                    })}
                    {graphChart.xTicks.map((tick) => {
                      const x = chartX(tick, graphChart.xMin, graphChart.xMax);
                      const selectedTick = graphChart.selectedLapDetail?.x === tick;
                      return (
                        <g key={`xtick:${tick}`}>
                          <line x1={x} y1={CHART_HEIGHT - CHART_PAD_BOTTOM} x2={x} y2={CHART_HEIGHT - CHART_PAD_BOTTOM + 5} className="stint-chart-axis-tick" />
                          <text x={x} y={CHART_HEIGHT - 10} className={`stint-chart-label stint-chart-label-x ${selectedTick ? "highlight" : ""}`} textAnchor="middle">
                            {tick}
                          </text>
                        </g>
                      );
                    })}
                    {graphChart.zeroLineY != null && (
                      <line
                        x1={CHART_PAD_LEFT}
                        y1={graphChart.zeroLineY}
                        x2={CHART_WIDTH - CHART_PAD_RIGHT}
                        y2={graphChart.zeroLineY}
                        className="stint-chart-zero-line"
                      />
                    )}
                    <line x1={CHART_PAD_LEFT} y1={CHART_PAD_TOP} x2={CHART_PAD_LEFT} y2={CHART_HEIGHT - CHART_PAD_BOTTOM} className="stint-chart-axis" />
                    <line x1={CHART_PAD_LEFT} y1={CHART_HEIGHT - CHART_PAD_BOTTOM} x2={CHART_WIDTH - CHART_PAD_RIGHT} y2={CHART_HEIGHT - CHART_PAD_BOTTOM} className="stint-chart-axis" />
                    {graphRangeOverlays.map((overlay, index) => (
                      <g key={overlay.key} className={`stint-chart-range ${overlay.className}`}>
                        <rect
                          x={Math.min(overlay.startX, overlay.endX)}
                          y={CHART_PAD_TOP}
                          width={Math.max(4, Math.abs(overlay.endX - overlay.startX))}
                          height={CHART_HEIGHT - CHART_PAD_TOP - CHART_PAD_BOTTOM}
                        />
                        <line x1={overlay.startX} y1={CHART_PAD_TOP} x2={overlay.startX} y2={CHART_HEIGHT - CHART_PAD_BOTTOM} />
                        <line x1={overlay.endX} y1={CHART_PAD_TOP} x2={overlay.endX} y2={CHART_HEIGHT - CHART_PAD_BOTTOM} />
                        <text x={Math.min(overlay.startX, overlay.endX) + 5} y={CHART_PAD_TOP + 14 + (index % 4) * 13}>
                          {overlay.label}
                        </text>
                      </g>
                    ))}
                    {graphChart.series.map((series) => (
                      <polyline
                        key={series.id}
                        points={stintChartPolyline(series.points, graphChart.xMin, graphChart.xMax, graphChart.yMin, graphChart.yMax)}
                        fill="none"
                        stroke={series.color}
                        strokeWidth={series.dashed ? 1.8 : 2.6}
                        strokeDasharray={series.dashed ? "6 5" : undefined}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    ))}
                    {graphChart.selectedLapDetail && (
                      <line
                        x1={graphChart.selectedLapDetail.screenX}
                        y1={CHART_PAD_TOP}
                        x2={graphChart.selectedLapDetail.screenX}
                        y2={CHART_HEIGHT - CHART_PAD_BOTTOM}
                        className="stint-chart-selected-guide"
                      />
                    )}
                    {graphChart.series.map((series) => {
                      const fastest = series.dashed ? null : series.points.reduce<StintGraphRenderPoint | null>((best, point) => {
                        if (point.lapTime == null || !point.valid) return best;
                        return best == null || point.lapTime < (best.lapTime ?? Number.POSITIVE_INFINITY) ? point : best;
                      }, null);
                      return (
                        <React.Fragment key={`${series.id}:markers`}>
                          {series.points.map((point) => (
                            <circle
                              key={`${series.id}:${point.lapNumber}`}
                              className={`stint-chart-point ${point.valid ? "" : "invalid"} ${point.excludedFromScale ? "excluded" : ""}`}
                              cx={point.screenX}
                              cy={point.screenY}
                              r={point.valid ? 3.2 : 2.5}
                              fill={point.color}
                              onMouseEnter={(event) => setHoveredGraphPoint({ ...point, clientX: event.clientX, clientY: event.clientY })}
                              onClick={() => setSelectedGraphLap({ stintId: series.id.replace(":rolling5", ""), lapNumber: point.lapNumber })}
                            />
                          ))}
                          {series.points.filter((point) => point.outlierAboveScale || point.outlierBelowScale).map((point) => (
                            <text
                              key={`${series.id}:${point.lapNumber}:outlier`}
                              x={point.screenX + 4}
                              y={point.outlierAboveScale ? CHART_PAD_TOP - 6 : CHART_HEIGHT - CHART_PAD_BOTTOM + 16}
                              className="stint-chart-outlier-label"
                            >
                              !
                            </text>
                          ))}
                          {fastest && (
                            <g className="stint-chart-best-group">
                              <circle className="stint-chart-fastest-marker" cx={fastest.screenX} cy={fastest.screenY} r="6" />
                              <text x={fastest.screenX + 8} y={fastest.screenY - 8} className="stint-chart-best-label">Best</text>
                            </g>
                          )}
                        </React.Fragment>
                      );
                    })}
                    {graphChart.selectedLapDetail && (
                      <g className="stint-chart-selected-group">
                        <circle className="stint-chart-selected-marker" cx={graphChart.selectedLapDetail.screenX} cy={graphChart.selectedLapDetail.screenY} r="8" />
                        <text x={graphChart.selectedLapDetail.screenX + 10} y={graphChart.selectedLapDetail.screenY + 4} className="stint-chart-selected-label">Selected</text>
                      </g>
                    )}
                    <text x={CHART_WIDTH / 2} y={CHART_HEIGHT - 10} className="stint-chart-axis-title" textAnchor="middle">Stint Lap</text>
                  </svg>
                  {hoveredGraphPoint && (
                    <div className="stint-graph-tooltip" style={{ left: hoveredGraphPoint.clientX + 12, top: hoveredGraphPoint.clientY + 12 }}>
                      <strong>{hoveredGraphPoint.sourceLabel}</strong>
                      <span>Lap {hoveredGraphPoint.lapNumber} - Stint lap {hoveredGraphPoint.stintLap}</span>
                      <span>Run/Stint {hoveredGraphPoint.sourceLabel}</span>
                      <span>Lap time {formatTime(hoveredGraphPoint.lapTime)}</span>
                      <span>Delta to best {formatSignedDelta(hoveredGraphPoint.deltaToBest)}</span>
                      <span>Rolling 5 {formatTime(hoveredGraphPoint.rolling5)}</span>
                      <span>Status {hoveredGraphPoint.valid ? "Valid" : "Invalid"}</span>
                      {graphStatusesForPoint(hoveredGraphPoint).length > 0 && <span>Flags {graphStatusesForPoint(hoveredGraphPoint).join(" | ")}</span>}
                      {hoveredGraphPoint.excludedFromScale && <span>Excluded from scale: {hoveredGraphPoint.exclusionReason ?? "outlier"}</span>}
                      {!hoveredGraphPoint.valid && <span>Invalid reason {hoveredGraphPoint.invalidReason ?? hoveredGraphPoint.warning ?? "invalid lap"}</span>}
                    </div>
                  )}
                  {graphChart.selectedLapDetail && (
                    <div className="stint-graph-detail-strip">
                      <strong>Selected lap</strong>
                      <span>{graphChart.selectedLapDetail.sourceLabel}</span>
                      <span>Lap {graphChart.selectedLapDetail.lapNumber} - Stint lap {graphChart.selectedLapDetail.stintLap}</span>
                      <span>Lap time {formatTime(graphChart.selectedLapDetail.lapTime)}</span>
                      <span>Delta to best {formatSignedDelta(graphChart.selectedLapDetail.deltaToBest)}</span>
                      <span>Rolling 5 {formatTime(graphChart.selectedLapDetail.rolling5)}</span>
                      <span>{graphChart.selectedLapDetail.valid ? "Valid" : `Invalid - ${graphChart.selectedLapDetail.invalidReason ?? graphChart.selectedLapDetail.warning ?? "reason unavailable"}`}</span>
                      {graphStatusesForPoint(graphChart.selectedLapDetail).length > 0 && <span>{graphStatusesForPoint(graphChart.selectedLapDetail).join(" | ")}</span>}
                    </div>
                  )}
                  <div className="stint-graph-legend">
                    {graphChart.series.map((series) => (
                      <span key={series.id}>
                        <i style={{ backgroundColor: series.color }} />
                        {series.label}
                        {series.id.replace(":rolling5", "") === selectedStint?.stint_id && <b>Selected</b>}
                        {series.id.replace(":rolling5", "") === baselineStintId && <b>Baseline</b>}
                        {series.id.replace(":rolling5", "") === testStintId && <b>Test</b>}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="stint-empty-state">
                  <h3>Select a stint or best-window card to graph lap times.</h3>
                  <p className="muted">Need lap-time points inside the selected stint. Invalid laps are excluded by default.</p>
                </div>
              )}
            </div>

            {selectedStint ? (
              <div className="stint-selected-toolbar">
                <div>
                  <span className="eyebrow">Selected</span>
                  <strong>{selectedStint.display_label_short} - {formatStintRange(selectedStint)}</strong>
                  <span className="muted">Avg {formatTime(selectedStint.avg_lap_time)} - Falloff {selectedStint.falloff_total != null ? `${selectedStint.falloff_total > 0 ? "+" : ""}${selectedStint.falloff_total.toFixed(2)}s` : "-"}</span>
                </div>
                <div className="laps-action-row compact">
                  <button className="secondary-button" onClick={() => setBaselineStintId(selectedStint.stint_id)} title="Stage this stint as baseline">
                    Baseline
                  </button>
                  <button className="secondary-button" onClick={() => setTestStintId(selectedStint.stint_id)} title="Stage this stint as test">
                    Test
                  </button>
                  <button className="secondary-button" onClick={() => graphStintIds.includes(selectedStint.stint_id) ? removeStintFromGraph(selectedStint.stint_id) : addStintToGraph(selectedStint.stint_id)} title="Add or remove this stint from the main graph">
                    {graphStintIds.includes(selectedStint.stint_id) ? "Ungraph" : "Graph"}
                  </button>
                  <button className="secondary-button" onClick={() => setSummaryDrawerStintId(selectedStint.stint_id)} title="Open the stint summary drawer">
                    Summary
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => focusWindowEvidence(stintToWindowSummary(selectedStint), "platform_trace")}
                    disabled={selectedStint.run_id !== overview.run_id}
                    title={selectedStint.run_id !== overview.run_id ? "Open the run before focusing Platform evidence." : "Open this stint in Platform"}
                  >
                    Platform
                  </button>
                  <button className="secondary-button" onClick={() => addToQueue(makeStintBasket(selectedStint, `Stint ${formatStintRange(selectedStint)}`))} title="Add this stint to the Test Basket">
                    Basket
                  </button>
                  <button className="secondary-button" onClick={exportSelectedStintsCsv} title="Export the selected stint or graphed stints as CSV">
                    CSV
                  </button>
                </div>
              </div>
            ) : (
              <div className="stint-selected-hint">
                <p>Select a stint row to graph, compare, or export.</p>
              </div>
            )}

            {baselineStint && testStint && (
              <div className="stint-compare-panel">
                <div>
                  <span className="eyebrow">Stint Compare</span>
                  <h3>{stintCompare?.verdict ?? (stintCompareLoading ? "Comparing selected stints..." : "Comparison pending")}</h3>
                  <p className="section-note">{stintCompareError ?? stintCompare?.summary ?? "Select clean windows with enough laps for stronger deltas."}</p>
                  <svg className="stint-sparkline" viewBox="0 0 104 52" role="img" aria-label="Selected stint pace bucket preview">
                    {[baselineStint, testStint].map((stint, index) => {
                      const values = [stint.early_avg, stint.middle_avg, stint.late_avg].filter((value): value is number => value != null);
                      const min = values.length > 0 ? Math.min(...values) : 0;
                      const max = values.length > 0 ? Math.max(...values) : 1;
                      const spread = Math.max(0.001, max - min);
                      const points = [stint.early_avg, stint.middle_avg, stint.late_avg]
                        .map((value, pointIndex) => {
                          const y = value == null ? 26 : 46 - ((value - min) / spread) * 28;
                          return `${pointIndex * 44 + 8},${y}`;
                        })
                        .join(" ");
                      return <polyline key={stint.stint_id} points={points} fill="none" stroke={index === 0 ? "#38bdf8" : "#f59e0b"} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />;
                    })}
                  </svg>
                </div>
                <div className="stint-compare-metrics">
                  <div><span>Avg</span><strong>{formatSignedDelta(stintCompare?.avg_delta)}</strong></div>
                  <div><span>Best</span><strong>{formatSignedDelta(stintCompare?.best_delta)}</strong></div>
                  {bucketLabels.slice(0, 4).map((label) => {
                    const bucketDelta = stintCompare?.bucket_deltas.find((bucket) => bucket.label === label);
                    return <div key={label}><span>{label}</span><strong>{formatSignedDelta(bucketDelta?.delta)}</strong></div>;
                  })}
                  <div><span>Falloff</span><strong>{formatSignedDelta(stintCompare?.falloff_delta)}</strong></div>
                  <div><span>Consistency</span><strong>{formatSignedDelta(stintCompare?.consistency_delta)}</strong></div>
                </div>
                <div className="laps-chip-row">
                  <span className="lap-flag-badge">Baseline {formatStintRange(baselineStint)}</span>
                  <span className="lap-flag-badge">Test {formatStintRange(testStint)}</span>
                  {stintCompare && <span className="lap-flag-badge">{stintCompare.tire_trend_delta}</span>}
                  {stintCompare && <span className="lap-flag-badge">{stintCompare.platform_trend_delta}</span>}
                  {stintCompare && <span className="lap-flag-badge">{stintCompare.shock_trend_delta}</span>}
                </div>
              </div>
            )}

            <div className="stint-advanced-panel">
              <button
                type="button"
                className="stint-advanced-toggle"
                onClick={() => setShowAdvancedControls((open) => !open)}
                aria-expanded={showAdvancedControls}
              >
                {showAdvancedControls ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                <span>
                  <strong>Advanced Controls</strong>
                  <small>Filters, run visibility, selection tools, and graph options.</small>
                </span>
              </button>
              {showAdvancedControls && (
                <div className="stint-advanced-content">
                  <div className="stint-advanced-grid">
                    <div className="stint-advanced-group">
                      <span className="eyebrow"><SlidersHorizontal size={13} /> Filters</span>
                      <label><input type="checkbox" checked={currentRunOnlyFilter} onChange={(event) => setCurrentRunOnlyFilter(event.currentTarget.checked)} /> Current run only</label>
                      <label><input type="checkbox" checked={sameCarTrackOnlyFilter} onChange={(event) => setSameCarTrackOnlyFilter(event.currentTarget.checked)} /> Same car/track only</label>
                      <label><input type="checkbox" checked={graphedOnlyFilter} onChange={(event) => setGraphedOnlyFilter(event.currentTarget.checked)} /> Graphed only</label>
                      <label><input type="checkbox" checked={hideInvalidRowsFilter} onChange={(event) => setHideInvalidRowsFilter(event.currentTarget.checked)} /> Hide invalid/caution laps</label>
                    </div>
                    <div className="stint-advanced-group">
                      <span className="eyebrow">Run visibility</span>
                      <button className="secondary-button" onClick={() => setExpandedRunIds(new Set([overview.run_id]))} title="Collapse every session run except the current run">Collapse other session runs</button>
                      <button className="secondary-button" onClick={() => setExpandedRunIds((runs) => new Set(runs).add(overview.run_id))} title="Ensure the current run stays expanded">Expand current run</button>
                    </div>
                    <div className="stint-advanced-group">
                      <span className="eyebrow">Selection tools</span>
                      <button
                        className="secondary-button"
                        onClick={() => selectedStint && setPinnedRunIds((runs) => {
                          const next = new Set(runs);
                          next.has(selectedStint.run_id) ? next.delete(selectedStint.run_id) : next.add(selectedStint.run_id);
                          return next;
                        })}
                        disabled={!selectedStint}
                        title={selectedStint ? "Pin or unpin the selected stint's run in Session Runs" : "Select a stint first"}
                      >
                        <Star size={13} /> {selectedStint && pinnedRunIds.has(selectedStint.run_id) ? "Unpin selected run" : "Pin selected run"}
                      </button>
                    </div>
                    <div className="stint-advanced-group">
                      <span className="eyebrow">Graph options</span>
                      <label className="stint-graph-toggle">
                        <input type="checkbox" checked={showRolling5} onChange={(event) => setShowRolling5(event.currentTarget.checked)} />
                        Rolling 5 overlay
                      </label>
                      <label className="stint-graph-toggle">
                        <input type="checkbox" checked={excludeInvalidGraphLaps} onChange={(event) => setExcludeInvalidGraphLaps(event.currentTarget.checked)} />
                        Exclude invalid laps
                      </label>
                      <label className="stint-graph-toggle">
                        <input type="checkbox" checked={includeOutliersInScale} onChange={(event) => setIncludeOutliersInScale(event.currentTarget.checked)} />
                        Include outliers in scale
                      </label>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {(visibleBestWindowCards.length > 0 || alternateStintWindows.length > 0) && (
              <div className="stint-alternate-window-panel">
                <button className="secondary-button" onClick={() => setShowBestWindows((open) => !open)}>
                  {showBestWindows ? "Hide best windows" : "Best Windows"}
                </button>
                {showBestWindows && (
                  <>
                    {visibleBestWindowCards.length > 0 && (
                      <div className="stint-window-card-row" aria-label="Best windows advanced section">
                        {visibleBestWindowCards.map((stint) => {
                          const isSelected = selectedStint?.stint_id === stint.stint_id;
                          const isBaseline = baselineStintId === stint.stint_id;
                          const isTest = testStintId === stint.stint_id;
                          const isGraphed = graphStintIds.includes(stint.stint_id);
                          return (
                            <div
                              key={stint.stint_id}
                              className={`stint-window-card ${isSelected ? "selected" : ""} ${isBaseline ? "baseline" : ""} ${isTest ? "test" : ""} ${isGraphed ? "graphed" : ""}`}
                              onClick={() => setSelectedStintId(stint.stint_id)}
                              onDoubleClick={() => setSummaryDrawerStintId(stint.stint_id)}
                              role="button"
                              tabIndex={0}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") setSelectedStintId(stint.stint_id);
                              }}
                            >
                              <span>{stint.display_label_short}</span>
                              <strong>{formatTime(stint.avg_lap_time)}</strong>
                              <small>{formatStintRange(stint)} - {stint.valid_lap_count}/{stint.lap_count} valid</small>
                              <div>
                                <span className={trendBadgeClass(stint.stint_label)}>{stint.stint_label}</span>
                                <span className="lap-flag-badge">EV {formatScore(stint.setup_usefulness_score)}</span>
                                {isGraphed && <span className="lap-flag-badge">Graphed</span>}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {alternateStintWindows.length > 0 && (
                      <div className="stint-alternate-window-list">
                        {alternateStintWindows.slice(0, 12).map((stint) => (
                          <button
                            type="button"
                            key={stint.stint_id}
                            className={`stint-window-pill ${selectedStint?.stint_id === stint.stint_id ? "selected" : ""}`}
                            onClick={() => setSelectedStintId(stint.stint_id)}
                          >
                            {stint.display_label_short} {formatStintRange(stint)} {formatTime(stint.avg_lap_time)}
                          </button>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            <div className="stint-history-panel">
              <div className="section-heading-row">
                <div>
                  <span className="eyebrow">Session Scope</span>
                  <h3><Clock size={15} /> Session Runs</h3>
                  <p className="section-note">{sessionRunsSubtitle}</p>
                  {sessionSelectionSource !== "existing" && runHistory.length <= 1 && (
                    <p className="section-note">Load older session from startup to view previous runs.</p>
                  )}
                  <p className="section-note">Current run stays expanded. Session runs stay collapsed and load stint data when opened.</p>
                </div>
                {sessionRunsLoading && <span className="muted">Loading session runs...</span>}
              </div>
              {visibleRunHistory.length === 0 && <div className="stint-empty-state"><p className="muted">No session runs available.</p></div>}
              {visibleRunHistory.map((run) => {
                const isCurrentRun = run.run_id === overview.run_id;
                const expanded = expandedRunIds.has(run.run_id);
                const response = isCurrentRun ? stintData : historyStintData[run.run_id];
                const runRows = response?.stint_rows ?? response?.stints ?? [];
                const runCards = response?.best_window_cards ?? [];
                const loading = historyStintsLoading[run.run_id] ?? false;
                return (
                  <div key={run.run_id} className={`stint-history-run ${isCurrentRun ? "current" : ""}`}>
                    <div className="stint-history-header" onClick={() => toggleHistoryRun(run.run_id)} aria-expanded={expanded} role="button" tabIndex={0}>
                      {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                      <span>
                        <strong>{isCurrentRun ? `Current run - ${run.setup_name ?? "Setup unknown"}` : run.setup_name ?? run.run_id}</strong>
                        <small>
                          {run.track_name ?? "-"} - {run.car_name ?? "-"} - {run.imported_at ?? response?.run_summary?.session_date ?? "date unknown"} -
                          {" "}Valid {response?.run_summary?.valid_laps ?? run.lap_count ?? "-"} -
                          {" "}Best {formatTime(run.best_lap_time ?? run.best_lap_time_s ?? response?.run_summary?.best_lap_time)}
                        </small>
                      </span>
                      <span className="stint-history-summary">
                        <b>Best 5</b> {formatTime(response?.run_summary?.best_5_avg)}
                        <b>Best 10</b> {formatTime(response?.run_summary?.best_10_avg)}
                        <b>Best 20</b> {formatTime(response?.run_summary?.best_20_avg)}
                        {pinnedRunIds.has(run.run_id) && <b>Pinned</b>}
                      </span>
                    </div>
                    {expanded && (
                      <div className="stint-history-body">
                        {isCurrentRun && <p className="muted">Current run timing sheet, graph, and advanced best windows are shown above.</p>}
                        {!isCurrentRun && loading && <p className="muted">Loading stint data for this run...</p>}
                        {!isCurrentRun && !loading && !response && <p className="muted">Expand a run to load its stint data.</p>}
                        {!isCurrentRun && response && (
                          <>
                            <div className="stint-window-card-row compact-history">
                              {runCards.map((stint) => {
                                const isGraphed = graphStintIds.includes(stint.stint_id);
                                return (
                                  <div key={stint.stint_id} className={`stint-window-card compact ${isGraphed ? "graphed" : ""}`} onClick={() => setSelectedStintId(stint.stint_id)} onDoubleClick={() => setSummaryDrawerStintId(stint.stint_id)} role="button" tabIndex={0}>
                                    <span>{stint.display_label_short}</span>
                                    <strong>{formatTime(stint.avg_lap_time)}</strong>
                                    <small>{formatStintRange(stint)}</small>
                                  </div>
                                );
                              })}
                            </div>
                            <div className="stint-history-row-list">
                              {runRows.map((stint) => (
                                <div key={stint.stint_id} className={`stint-history-stint-row ${selectedStint?.stint_id === stint.stint_id ? "selected" : ""}`} onClick={() => setSelectedStintId(stint.stint_id)} onDoubleClick={() => setSummaryDrawerStintId(stint.stint_id)} role="button" tabIndex={0}>
                                  <span><strong>{stint.display_label_short}</strong> {formatStintRange(stint)}</span>
                                  <span>Avg {formatTime(stint.avg_lap_time)}</span>
                                  <span>Valid {stint.valid_lap_count}/{stint.lap_count}</span>
                                </div>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="field-compare-panel">
              <button
                type="button"
                className="field-compare-header"
                onClick={() => setShowFieldCompare((open) => !open)}
                aria-expanded={showFieldCompare}
              >
                {showFieldCompare ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                <span>
                  <strong>Field Compare</strong>
                  <small>Compare other drivers' best stint averages against your best equivalent stint.</small>
                </span>
              </button>
              {showFieldCompare && (
                <div className="field-compare-body">
                  <div className="stint-empty-state">
                    <h3>Other-driver stint data is not available yet.</h3>
                    <p className="muted">Live iRSDK / imported shared stint data will unlock field comparison later.</p>
                  </div>
                  <div className="stint-table-wrap field-compare-table-wrap" aria-hidden="true">
                    <table className="compact-table stint-table field-compare-table">
                      <thead>
                        <tr>
                          <th>Driver</th>
                          <th>Stint</th>
                          <th># Laps</th>
                          <th>Fastest Lap</th>
                          {stintAverageColumns.map((column) => <th key={column.size}>{column.label}</th>)}
                          <th>Delta to My Best Equivalent</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                    </table>
                  </div>
                </div>
              )}
            </div>
            </>
          )}
          {summaryDrawerStint && (
            <aside className="stint-summary-drawer" aria-label="Stint Summary">
              <div className="stint-summary-drawer-header">
                <div>
                  <span className="eyebrow">Stint Summary</span>
                  <h3>{summaryDrawerStint.display_label_short} - {formatStintRange(summaryDrawerStint)}</h3>
                  <p className="section-note">
                    {summaryDrawerStint.setup_name ?? "Setup unknown"} - {summaryDrawerStint.track_name ?? "-"} - {summaryDrawerStint.car_name ?? "-"}
                  </p>
                </div>
                <button className="secondary-button" onClick={() => setSummaryDrawerStintId(null)} aria-label="Close stint summary">
                  <X size={14} /> Close
                </button>
              </div>
              <div className="stint-summary-metrics">
                <div><span>Valid</span><strong>{summaryDrawerStint.valid_lap_count}/{summaryDrawerStint.lap_count}</strong></div>
                <div><span>Best</span><strong>{formatTime(summaryDrawerStint.best_lap_time)}</strong></div>
                <div><span>Average</span><strong>{formatTime(summaryDrawerStint.avg_lap_time)}</strong></div>
                <div><span>Falloff</span><strong>{summaryDrawerStint.falloff_total != null ? `${summaryDrawerStint.falloff_total > 0 ? "+" : ""}${summaryDrawerStint.falloff_total.toFixed(2)}s` : "-"}</strong></div>
                <div><span>Consistency</span><strong>{formatScore(summaryDrawerStint.consistency_score)}</strong></div>
                <div><span>Setup EV</span><strong>{formatScore(summaryDrawerStint.setup_usefulness_score)}</strong></div>
              </div>
              <div className="laps-chip-row">
                <span className={trendBadgeClass(summaryDrawerStint.tire_trend_label)}>{summaryDrawerStint.tire_trend_label}</span>
                <span className={trendBadgeClass(summaryDrawerStint.platform_trend_label)}>{summaryDrawerStint.platform_trend_label}</span>
                <span className={trendBadgeClass(summaryDrawerStint.shock_trend_label)}>{summaryDrawerStint.shock_trend_label}</span>
                <span className="lap-flag-badge">Run {summaryDrawerStint.run_id}</span>
              </div>
              <div className="stint-progression-buckets">
                <span className="eyebrow">Progression Buckets</span>
                <div className="stint-progression-grid">
                  {stintProgressionColumns.map((column) => {
                    const bucket = stintBucket(summaryDrawerStint, column.label);
                    const bucketClass = bucket?.avg_lap_time == null
                      ? "stint-progression-card unavailable"
                      : bucket.is_fastest_bucket
                        ? "stint-progression-card fastest"
                        : "stint-progression-card";
                    return (
                      <div key={column.label} className={bucketClass} title={bucket?.warning ?? undefined}>
                        <span>{column.label}</span>
                        <strong>{bucket?.avg_lap_time != null ? formatTime(bucket.avg_lap_time) : "\u2014"}</strong>
                        <small>{bucket != null ? `${bucket.valid_lap_count}/${bucket.lap_count} valid` : "No data"}</small>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="stint-summary-table-wrap">
                <table className="compact-table stint-summary-lap-table">
                  <thead>
                    <tr>
                      <th>Lap</th>
                      <th>Stint Lap</th>
                      <th>Lap Time</th>
                      <th>Delta</th>
                      <th>Rolling 5</th>
                      <th>Status</th>
                      <th>Reason</th>
                      <th>Avg MPH</th>
                      <th>Max MPH</th>
                      <th>Min MPH</th>
                      <th>Fuel</th>
                      <th>Tire</th>
                      <th>Platform</th>
                      <th>Shock</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summaryDrawerStint.lap_points.map((point) => (
                      <tr key={`${summaryDrawerStint.stint_id}:${point.lap_number}`} className={selectedGraphLap?.lapNumber === point.lap_number ? "stint-row-selected" : ""}>
                        <td>{point.lap_number}</td>
                        <td>{point.stint_lap}</td>
                        <td>{formatTime(point.lap_time)}</td>
                        <td>{formatSignedDelta(point.delta_to_best)}</td>
                        <td>{formatTime(point.rolling_5)}</td>
                        <td>{point.valid ? "Valid" : "Invalid"}</td>
                        <td>{point.warning ?? "-"}</td>
                        <td>{formatOptionalNumber(point.avg_speed_mph)}</td>
                        <td>{formatOptionalNumber(point.max_speed_mph)}</td>
                        <td>{formatOptionalNumber(point.min_speed_mph)}</td>
                        <td>{formatOptionalNumber(point.fuel)}</td>
                        <td>{compactTrendLabel("tire", summaryDrawerStint.tire_trend_label)}</td>
                        <td>{compactTrendLabel("platform", summaryDrawerStint.platform_trend_label)}</td>
                        <td>{compactTrendLabel("shock", summaryDrawerStint.shock_trend_label)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </aside>
          )}
        </section>

    </div>
  );
}

function axisTickStep(span: number): number {
  if (span <= 8) return 1;
  if (span <= 16) return 2;
  if (span <= 35) return 5;
  if (span <= 70) return 10;
  return 15;
}

function buildXAxisTicks(xMin: number, xMax: number, highlighted: number[] = []): number[] {
  const step = axisTickStep(Math.max(1, xMax - xMin));
  const ticks = new Set<number>([xMin, xMax]);
  for (let tick = Math.ceil(xMin / step) * step; tick <= xMax; tick += step) {
    ticks.add(tick);
  }
  highlighted.forEach((value) => {
    if (value >= xMin && value <= xMax) ticks.add(value);
  });
  return [...ticks].sort((left, right) => left - right);
}

function buildYAxisTicks(yMin: number, yMax: number): number[] {
  const span = Math.max(0.001, yMax - yMin);
  return [0, 0.25, 0.5, 0.75, 1].map((ratio) => yMin + span * ratio);
}
