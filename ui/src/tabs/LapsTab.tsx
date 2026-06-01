import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock,
  Gauge,
  Layers,
  List,
  MapPin,
  Target,
  TrendingDown,
  Trophy,
} from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { fetchLapWindows, fetchRunList } from "../api/client";
import { makeBasketItem } from "../components/CompareBasket";
import { ValueDisplay } from "../components/ValueDisplay";
import { useCompareBasket } from "../store/CompareBasketContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { LapWindowSummary, LapWindowsResponse } from "../types/laps";
import type { LapSummary, RunListItem, RunOverview } from "../types/telemetry";

type LapsTabProps = {
  overview: RunOverview;
};

type LapsSubview = "current" | "windows" | "all_sessions" | "baselines" | "basket";
type StintMode = "ev" | "delta" | "falloff";

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

function formatWindowRange(window: Pick<LapWindowSummary, "start_lap" | "end_lap">): string {
  return `Laps ${window.start_lap}-${window.end_lap}`;
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
  if (upperWarnings.some((warning) => warning.includes("INVALID") || warning.includes("INSUFFICIENT") || warning.includes("ONLY"))) chips.push("Few laps");
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

export function LapsTab({ overview }: LapsTabProps) {
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
  const [expandedLap, setExpandedLap] = useState<number | null>(null);
  const [stintMode, setStintMode] = useState<StintMode>("ev");
  const [subview, setSubview] = useState<LapsSubview>("current");
  const [allRuns, setAllRuns] = useState<RunListItem[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [hoveredWindowId, setHoveredWindowId] = useState<string | null>(null);

  const { laps } = overview;

  useEffect(() => {
    if (subview === "all_sessions" || subview === "baselines") {
      setRunsLoading(true);
      fetchRunList()
        .then(setAllRuns)
        .catch(() => setAllRuns([]))
        .finally(() => setRunsLoading(false));
    }
  }, [subview]);

  useEffect(() => {
    fetchLapWindows(overview.run_id)
      .then(setWindowsData)
      .catch(() => setWindowsData(null));
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

  const compareRoleForLap = useCallback((lapNumber: number): string | null => {
    if (basket.baseline?.run_id === overview.run_id && basket.baseline.lap_scope !== "lap_window" && basket.baseline.lap_number === lapNumber) return "Baseline";
    if (basket.test?.run_id === overview.run_id && basket.test.lap_scope !== "lap_window" && basket.test.lap_number === lapNumber) return "Test";
    return null;
  }, [basket.baseline, basket.test, overview.run_id]);

  const selectedWindow = selection.selectedLapScope === "lap_window"
    ? { start: selection.selectedLapWindowStart ?? null, end: selection.selectedLapWindowEnd ?? null }
    : null;

  useEffect(() => {
    if (subview !== "current" || selection.selectedLap == null || selection.selectedLapScope === "lap_window") return;
    const row = document.querySelector(`[data-lap-row="${selection.selectedLap}"]`) as HTMLElement | null;
    if (!row) return;
    row.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selection.selectedLap, selection.selectedLapScope, subview]);

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
        </div>
      );
    }

    return (
      <div className={`laps-action-row${compact ? " compact" : ""}`}>
        <button className="secondary-button" onClick={handleSelect} disabled={!canStage} title={canStage ? "Use this evidence as current selection" : disabledReason} aria-label={isWindow ? "Select window evidence" : "Select lap evidence"}>
          <Target size={14} /> {isWindow ? "Select Window" : "Select Evidence"}
        </button>
        <button className="secondary-button" onClick={handlePlatform} disabled={!canOpenPlatform} title={canOpenPlatform ? "Open Platform with this evidence context" : disabledReason} aria-label="Open evidence in Platform">
          <Layers size={14} /> Platform
        </button>
        <button className="secondary-button" onClick={handleMap} disabled={!canStage} title={canStage ? "Open Map with this evidence context" : disabledReason} aria-label="Open evidence on Map">
          <MapPin size={14} /> Map
        </button>
        <button className="secondary-button" onClick={handleBaseline} disabled={!canStage} title={canStage ? "Stage as compare baseline" : disabledReason} aria-label="Set baseline from evidence">
          <Clock size={14} /> Baseline
        </button>
        <button className="secondary-button" onClick={handleTest} disabled={!canStage} title={canStage ? "Stage as compare test" : disabledReason} aria-label="Set test from evidence">
          <Gauge size={14} /> Test
        </button>
        <button className="secondary-button" onClick={handleBasket} disabled={!canStage} title={canStage ? "Add evidence to Compare Basket queue" : disabledReason} aria-label="Add evidence to Compare Basket">
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
              Evidence center for selecting trustworthy lap or lap-window context before jumping to Platform, Map, Compare, or Notebook.
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

      <div className="compare-subnav">
        {(["current", "windows", "all_sessions", "baselines", "basket"] as LapsSubview[]).map((view) => (
          <button
            key={view}
            className={`subnav-item ${subview === view ? "active" : ""}`}
            onClick={() => setSubview(view)}
          >
            {view === "current" ? "Evidence" : view === "windows" ? "Windows" : view === "all_sessions" ? "All Sessions" : view === "baselines" ? "Baselines" : "Basket"}
          </button>
        ))}
      </div>

      {subview === "current" && evidenceSelector.length > 0 && (
        <section className="workspace-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Task 1</span>
              <h2><Target size={16} /> Evidence Selector</h2>
            </div>
          </div>
          {groupedEvidenceSelector.map((group) => (
            <div key={group.label} style={{ marginBottom: 12 }}>
              <h4 style={{ margin: "0 0 6px 2px" }}>{group.label}</h4>
              <div className="laps-evidence-selector">
                {group.items.map((item) => (
                  <article key={item.id} className="laps-evidence-card">
                    {renderDescriptorSummary(item)}
                    {item.scope === "lap_window" && (
                      <p className="section-note" style={{ marginTop: 8 }}>
                        Window context stays preserved globally. Platform and Map use the representative lap for lap-level anchoring and still label the selection as a window.
                      </p>
                    )}
                    {renderEvidenceActions(item, false, "compare_inline")}
                  </article>
                ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {subview === "current" && candidateMatrix.length > 0 && (
        <section className="workspace-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Task 3</span>
              <h2><BarChart3 size={16} /> Trust / Pace / Engineering Matrix</h2>
            </div>
          </div>
          <p className="section-note">
            This matrix stays truthful about grain: lap rows use lap-level data, window rows use window-level scores, and unavailable values stay unavailable.
          </p>
          <div className="table-scroll">
            <table className="compact-table" style={{ marginTop: 0 }}>
              <thead>
                <tr>
                  <th>Candidate</th>
                  <th>Scope</th>
                  <th>Pace</th>
                  <th>Trust</th>
                  <th>Engineering</th>
                  <th>Flags</th>
                  <th>Basis</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {candidateMatrix.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.title}</strong>
                      <div className="muted" style={{ fontSize: 11 }}>
                        {item.window ? formatWindowRange(item.window) : item.lap ? `Lap ${item.lap.lap_number}` : "Unavailable"}
                      </div>
                    </td>
                    <td>{item.window ? "Window" : "Lap"}</td>
                    <td>{item.window ? formatTime(item.window.average_lap_time) : item.lap ? formatTime(item.lap.lap_time) : "-"}</td>
                    <td>
                      {item.trustScore != null ? (
                        <span style={{ color: paceQualityColor(item.trustScore) }}>{item.trustTier} ({item.trustScore.toFixed(0)})</span>
                      ) : item.trustTier ?? "Unavailable"}
                    </td>
                    <td>
                      {item.engineeringValue != null ? (
                        <span style={{ color: paceQualityColor(item.engineeringValue) }}>{item.engineeringValue.toFixed(0)}</span>
                      ) : item.lap?.min_splitter_mm != null ? (
                        <span>Min splitter {item.lap.min_splitter_mm.toFixed(1)} mm</span>
                      ) : "Unavailable"}
                    </td>
                    <td>
                      <div className="laps-chip-row">
                        {item.flags.map((flag) => <span key={flag} className="lap-flag-badge">{flag}</span>)}
                        {item.reasons.map((reason) => (
                          <span key={reason} className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>{reason}</span>
                        ))}
                      </div>
                    </td>
                    <td>{item.basisLabel}</td>
                    <td>{renderEvidenceActions(item, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {subview === "current" && windowsData && laps.length > 0 && (
        <section className="workspace-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Task 4</span>
              <h2><CheckCircle2 size={16} /> Stint Map Truthfulness</h2>
            </div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {(["ev", "delta", "falloff"] as StintMode[]).map((mode) => (
                <button
                  key={mode}
                  className={`setup-diff-toggle-btn ${stintMode === mode ? "active" : ""}`}
                  onClick={() => setStintMode(mode)}
                >
                  {mode === "ev" ? "Eng Value" : mode === "delta" ? "Delta" : "Falloff"}
                </button>
              ))}
            </div>
          </div>
          <div className="laps-chip-row" style={{ marginBottom: 8 }}>
            <span className="lap-flag-badge">
              Basis: {stintMode === "delta" ? "Lap-level" : stintMode === "ev" ? "Window-level" : "Run-level"}
            </span>
            {stintMode === "ev" && bestWindow && (
              <span className="lap-flag-badge" style={{ background: "rgba(56,189,248,0.12)", color: "#38bdf8" }}>
                Best window EV {bestWindow.setup_usefulness_score?.toFixed(0) ?? "-"} for {formatWindowRange(bestWindow)}
              </span>
            )}
            {stintMode === "falloff" && windowsData.degradation && (
              <span className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>
                Run falloff {windowsData.degradation.falloff_early_to_late != null ? `+${windowsData.degradation.falloff_early_to_late.toFixed(2)}s` : "Unavailable"}
              </span>
            )}
          </div>
          <div className="laps-stint-shell">
            <div
              className="laps-stint-overlay-row"
              style={{ gridTemplateColumns: `repeat(${laps.length}, minmax(24px, 1fr))` }}
            >
              {availableBestWindows.map((window) => {
                const startIndex = laps.findIndex((lap) => lap.lap_number === window.start_lap);
                const endIndex = laps.findIndex((lap) => lap.lap_number === window.end_lap);
                if (startIndex < 0 || endIndex < 0) return null;
                const isSelected = matchesSelectionWindow(window, selection.selectedLapWindowStart, selection.selectedLapWindowEnd);
                const isHovered = hoveredWindowId === window.window_id;
                return (
                  <button
                    key={window.window_id}
                    className={`laps-stint-window-band${isSelected ? " selected" : ""}${isHovered ? " hovered" : ""}`}
                    style={{ gridColumn: `${startIndex + 1} / ${endIndex + 2}` }}
                    onMouseEnter={() => setHoveredWindowId(window.window_id)}
                    onMouseLeave={() => setHoveredWindowId(null)}
                    onClick={() => focusWindowEvidence(window)}
                    aria-label={`Select window ${window.start_lap} through ${window.end_lap}`}
                    title={`${formatWindowRange(window)} - EV ${window.setup_usefulness_score?.toFixed(0) ?? "-"} - Trust ${window.evidence_confidence_score?.toFixed(0) ?? "-"}`}
                  >
                    {window.window_size}L
                  </button>
                );
              })}
            </div>
            <div
              className="laps-stint-map-grid"
              style={{ gridTemplateColumns: `repeat(${laps.length}, minmax(24px, 1fr))` }}
            >
              {laps.map((lap) => {
                const tags = lap.classification_tags ?? [];
                const isValid = lap.is_useful;
                const isSelectedLap = selection.selectedLapScope !== "lap_window" && selection.selectedLap === lap.lap_number;
                const inSelectedWindow = selectedWindow?.start != null && selectedWindow.end != null
                  ? lap.lap_number >= selectedWindow.start && lap.lap_number <= selectedWindow.end
                  : false;
                const inHoveredWindow = availableBestWindows.some((window) =>
                  hoveredWindowId === window.window_id && windowContainsLap(window, lap.lap_number));

                let background = "#1f2937";
                if (stintMode === "delta") {
                  const delta = lap.lap_time != null && bestTime != null ? lap.lap_time - bestTime : null;
                  if (delta == null) background = "#1f2937";
                  else if (delta < 0.1) background = "#22c55e";
                  else if (delta < 0.5) background = "#f59e0b";
                  else background = "#ef4444";
                }

                const markers: string[] = [];
                if (!lap.is_useful) markers.push("!");
                if (lap.lap_type === "out") markers.push("O");
                if (lap.lap_type === "in") markers.push("I");

                return (
                  <button
                    key={lap.lap_id}
                    className={`laps-stint-block${isSelectedLap ? " selected" : ""}${inSelectedWindow ? " window-highlight" : ""}${inHoveredWindow ? " window-hover" : ""}`}
                    style={{ background, opacity: isValid ? 1 : 0.7 }}
                    onClick={() => focusLapEvidence(lap)}
                    aria-label={`Select lap ${lap.lap_number}`}
                    title={`Lap ${lap.lap_number} - ${formatTime(lap.lap_time)} - ${lapTrustTier(lap)}`}
                  >
                    <span className="laps-stint-block-label">{lap.lap_number}</span>
                    {markers.length > 0 && <span className="laps-stint-marker">{markers[0]}</span>}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="laps-stint-legend">
            <span className="laps-stint-legend-item"><span className="laps-stint-legend-swatch" style={{ background: "#22c55e" }} /> Fast / clean</span>
            <span className="laps-stint-legend-item"><span className="laps-stint-legend-swatch" style={{ background: "#f59e0b" }} /> Warning</span>
            <span className="laps-stint-legend-item"><span className="laps-stint-legend-swatch" style={{ background: "#ef4444" }} /> Slow / invalid</span>
            <span className="laps-stint-legend-item"><span className="laps-stint-legend-swatch" style={{ outline: "2px solid var(--cyan)", background: "transparent" }} /> Selected lap</span>
            <span className="laps-stint-legend-item"><span className="laps-stint-legend-swatch" style={{ border: "1px solid var(--cyan)", background: "transparent" }} /> Selected window</span>
          </div>
        </section>
      )}

      {subview === "current" && windowsData?.degradation?.coaching_message && windowsData.degradation.lap_count >= 10 && (
        <section className="workspace-section">
          <h2><TrendingDown size={16} /> Pace Trend</h2>
          <p className="section-note">{windowsData.degradation.coaching_message}</p>
          <div className="laps-chip-row">
            <span className="lap-flag-badge">Run-level</span>
            {windowsData.degradation.falloff_early_to_late != null && (
              <span className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>
                Falloff +{windowsData.degradation.falloff_early_to_late.toFixed(2)}s
              </span>
            )}
          </div>
        </section>
      )}

      {subview === "windows" && (
        <section className="workspace-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Task 7</span>
              <h2><BarChart3 size={16} /> Best Windows</h2>
            </div>
          </div>
          {!windowsData || availableBestWindows.length === 0 ? (
            <p className="muted">No windows available yet. More valid laps are needed before window evidence is trustworthy.</p>
          ) : (
            <div className="laps-window-grid">
              {availableBestWindows
                .sort((left, right) => candidateScore(right) - candidateScore(left))
                .map((window) => (
                  <article
                    key={window.window_id}
                    className={`laps-window-card${matchesSelectionWindow(window, selection.selectedLapWindowStart, selection.selectedLapWindowEnd) ? " active" : ""}`}
                    onMouseEnter={() => setHoveredWindowId(window.window_id)}
                    onMouseLeave={() => setHoveredWindowId(null)}
                  >
                    <div className="section-heading-row">
                      <div>
                        <span className="eyebrow">Window {window.window_size}L</span>
                        <h3 style={{ margin: 0 }}>{formatWindowRange(window)}</h3>
                      </div>
                      <span className="lap-flag-badge">{windowTrustTier(window)}</span>
                    </div>
                    <div className="laps-chip-row">
                      <span className="lap-flag-badge">Window-level</span>
                      <span className="lap-flag-badge">Avg {formatTime(window.average_lap_time)}</span>
                      <span className="lap-flag-badge" style={{ color: paceQualityColor(window.setup_usefulness_score), borderColor: "transparent" }}>
                        EV {window.setup_usefulness_score?.toFixed(0) ?? "-"}
                      </span>
                      <span className="lap-flag-badge" style={{ color: paceQualityColor(window.evidence_confidence_score), borderColor: "transparent" }}>
                        Trust {window.evidence_confidence_score?.toFixed(0) ?? "-"}
                      </span>
                    </div>
                    <p className="section-note">{classifyPaceTrust(window.pace_quality_score, window.evidence_confidence_score, window.pace_quality_warnings)}</p>
                    <div className="laps-chip-row">
                      {windowFlags(window).map((flag) => <span key={flag} className="lap-flag-badge">{flag}</span>)}
                      {trustReasonChips(window.evidence_confidence_score, window.pace_quality_warnings, window.classification_tags).map((reason) => (
                        <span key={reason} className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>{reason}</span>
                      ))}
                      {(window.warnings ?? []).slice(0, 3).map((warning) => (
                        <span key={warning} className="lap-flag-badge" style={{ background: "rgba(239,68,68,0.12)", color: "#ef4444" }}>{warning}</span>
                      ))}
                    </div>
                    <div className="laps-window-metrics">
                      <div><span className="muted">Fastest</span><strong>{formatTime(window.fastest_lap_time)}</strong></div>
                      <div><span className="muted">Slowest</span><strong>{formatTime(window.slowest_lap_time)}</strong></div>
                      <div><span className="muted">Falloff</span><strong>{window.falloff_sec != null ? `+${window.falloff_sec.toFixed(2)}s` : "Unavailable"}</strong></div>
                      <div><span className="muted">Valid laps</span><strong>{window.valid_lap_count}/{window.window_size}</strong></div>
                    </div>
                    {renderEvidenceActions(descriptorForWindow(
                      `Window ${window.window_size}L`,
                      "Actionable evidence scope",
                      window,
                      representativeLapByWindowId.get(window.window_id) ?? null,
                    ), false, "compare_inline")}
                  </article>
                ))}
            </div>
          )}
        </section>
      )}

      {subview === "all_sessions" && (
        <section className="workspace-section">
          <h2><List size={16} /> All Sessions</h2>
          {runsLoading && <p className="muted">Loading runs...</p>}
          {!runsLoading && allRuns.length === 0 && <p className="muted">No imported runs found.</p>}
          {!runsLoading && allRuns.length > 0 && (
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Car</th>
                  <th>Track</th>
                  <th>Setup</th>
                  <th>Laps</th>
                  <th>Best Lap</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {allRuns.map((run) => (
                  <tr key={run.run_id}>
                    <td>{run.imported_at?.slice(0, 10) ?? "-"}</td>
                    <td>{run.car_name ?? "-"}</td>
                    <td>{run.track_name ?? "-"}</td>
                    <td>{run.setup_name ?? "-"}</td>
                    <td>{run.lap_count ?? "-"}</td>
                    <td>{run.best_lap_time_s != null ? `${run.best_lap_time_s.toFixed(3)}s` : "-"}</td>
                    <td>
                      <div className="laps-action-row compact">
                        <button
                          className="secondary-button"
                          onClick={() => setBaseline(makeBasketItem(
                            run.run_id,
                            null,
                            `${run.car_name ?? "Car"} @ ${run.track_name ?? "Track"}`,
                            run.car_name ?? null,
                            run.track_name ?? null,
                            run.setup_name ?? null,
                            run.best_lap_time_s ?? null,
                            [],
                            null,
                            run.imported_at ?? null,
                            null,
                            run.has_setup_snapshot ?? false,
                            { valueBasis: "run_level" },
                          ))}
                        >
                          <Clock size={14} /> Baseline
                        </button>
                        <button
                          className="secondary-button"
                          onClick={() => setTest(makeBasketItem(
                            run.run_id,
                            null,
                            `${run.car_name ?? "Car"} @ ${run.track_name ?? "Track"}`,
                            run.car_name ?? null,
                            run.track_name ?? null,
                            run.setup_name ?? null,
                            run.best_lap_time_s ?? null,
                            [],
                            null,
                            run.imported_at ?? null,
                            null,
                            run.has_setup_snapshot ?? false,
                            { valueBasis: "run_level" },
                          ))}
                        >
                          <Gauge size={14} /> Test
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {subview === "baselines" && (
        <section className="workspace-section">
          <h2><Trophy size={16} /> Baseline Suggestions</h2>
          <div className="laps-window-grid">
            {bestEvidenceLap && (
              <article className="laps-window-card">
                {renderDescriptorSummary(descriptorForLap("Best Evidence Lap", "Strong single-lap baseline candidate", bestEvidenceLap))}
                {renderEvidenceActions(descriptorForLap("Best Evidence Lap", "Strong single-lap baseline candidate", bestEvidenceLap), false, "compare_inline")}
              </article>
            )}
            {bestWindow && (
              <article className="laps-window-card">
                {renderDescriptorSummary(descriptorForWindow(
                  "Best Window",
                  "Sustained baseline candidate",
                  bestWindow,
                  representativeLapByWindowId.get(bestWindow.window_id) ?? null,
                ))}
                {renderEvidenceActions(descriptorForWindow(
                  "Best Window",
                  "Sustained baseline candidate",
                  bestWindow,
                  representativeLapByWindowId.get(bestWindow.window_id) ?? null,
                ), false, "compare_inline")}
              </article>
            )}
          </div>
        </section>
      )}

      {subview === "basket" && (
        <section className="workspace-section">
          <div className="section-heading-row">
            <div>
              <span className="eyebrow">Task 9</span>
              <h2><BarChart3 size={16} /> Compare Basket Staging</h2>
            </div>
            <div className="laps-action-row compact">
              <button className="secondary-button" onClick={swap} disabled={!basket.baseline || !basket.test}>
                <Gauge size={14} /> Swap
              </button>
              <button className="secondary-button" onClick={clearQueue} disabled={basket.queue.length === 0}>
                <List size={14} /> Clear Queue
              </button>
              <button className="secondary-button" onClick={clear} disabled={!basket.baseline && !basket.test && basket.queue.length === 0}>
                <AlertTriangle size={14} /> Clear Basket
              </button>
              <button className="secondary-button" onClick={() => setWorkspace("compare", "laps")}>
                <Layers size={14} /> Open Compare
              </button>
            </div>
          </div>
          <p className="section-note">
            Basket cards preserve whether you staged a lap or a window. Compare still syncs run-level identity first, so window metadata is preserved truthfully but not yet consumed deeply by the compare engine.
          </p>
          <div className="laps-window-grid">
            {([["Baseline", basket.baseline], ["Test", basket.test]] as const).map(([label, item]) => (
              <article key={label} className="laps-window-card">
                <span className="eyebrow">{label}</span>
                <h3 style={{ marginTop: 0 }}>{item?.label ?? "Empty"}</h3>
                {item ? (
                  <>
                    <div className="laps-chip-row">
                      <span className="lap-flag-badge">{item.lap_scope === "lap_window" ? `Window ${item.lap_window_start}-${item.lap_window_end}` : item.lap_number != null ? `Lap ${item.lap_number}` : "Run-level"}</span>
                      {item.representative_lap != null && item.lap_scope === "lap_window" && <span className="lap-flag-badge">Rep Lap {item.representative_lap}</span>}
                      {item.trust_tier && <span className="lap-flag-badge">Trust {item.trust_tier}</span>}
                      {item.value_basis && <span className="lap-flag-badge">{item.value_basis}</span>}
                    </div>
                    <p className="section-note">
                      {item.car ?? "-"} - {item.track ?? "-"} - {item.lap_time != null ? formatTime(item.lap_time) : "Time unavailable"}
                    </p>
                  </>
                ) : (
                  <p className="muted">Stage evidence from the Evidence Selector, table, or Best Windows cards.</p>
                )}
              </article>
            ))}
          </div>
          {basket.queue.length > 0 && (
            <>
              <h3>Queue</h3>
              <div className="laps-basket-queue">
                {basket.queue.map((item) => (
                  <div key={item.id} className="laps-basket-queue-item">
                    <div>
                      <strong>{item.label}</strong>
                      <div className="muted" style={{ fontSize: 11 }}>
                        {item.lap_scope === "lap_window" ? `Window ${item.lap_window_start}-${item.lap_window_end}` : item.lap_number != null ? `Lap ${item.lap_number}` : "Run-level"}
                        {item.lap_scope === "lap_window" && item.representative_lap != null ? ` - Rep Lap ${item.representative_lap}` : ""}
                        {item.trust_tier ? ` - Trust ${item.trust_tier}` : ""}
                      </div>
                    </div>
                    <button className="secondary-button" onClick={() => removeFromQueue(item.id)}>Remove</button>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {subview === "current" && (
        <section className="workspace-section" style={{ padding: 0, overflow: "auto" }}>
          <div style={{ padding: "12px 12px 0" }}>
            <span className="eyebrow">Task 6</span>
            <h2><List size={16} /> All Laps</h2>
            <p className="section-note">
              Explicit row actions preserve evidence identity better than hidden row-click behavior. Expand buttons remain keyboard-safe.
            </p>
          </div>
          <table className="compact-table" style={{ marginTop: 0 }}>
            <thead>
              <tr>
                <th>Expand</th>
                <th>#</th>
                <th>Time</th>
                <th>Delta</th>
                <th>Trust</th>
                <th>Engineering</th>
                <th>Flags</th>
                <th>Best Window</th>
                <th>Compare</th>
                <th>Selection</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {laps.map((lap) => {
                const isExpanded = expandedLap === lap.lap_number;
                const role = compareRoleForLap(lap.lap_number);
                const memberships = bestWindowMembership.get(lap.lap_number) ?? [];
                const isSelectedLap = selection.selectedLapScope !== "lap_window" && selection.selectedLap === lap.lap_number;
                const inSelectedWindow = selectedWindow?.start != null && selectedWindow.end != null
                  ? lap.lap_number >= selectedWindow.start && lap.lap_number <= selectedWindow.end
                  : false;

                return (
                  <React.Fragment key={lap.lap_id}>
                    <tr data-lap-row={lap.lap_number} className={isSelectedLap ? "selected-row" : ""} style={{ opacity: lap.is_useful ? 1 : 0.72 }}>
                      <td>
                        <button
                          className="secondary-button"
                          onClick={() => setExpandedLap(isExpanded ? null : lap.lap_number)}
                          aria-expanded={isExpanded}
                          aria-label={`${isExpanded ? "Collapse" : "Expand"} lap ${lap.lap_number} details`}
                        >
                          {isExpanded ? "Hide" : "Show"}
                        </button>
                      </td>
                      <td>{lap.lap_number}</td>
                      <td style={{ fontWeight: 600 }}>{formatTime(lap.lap_time)}</td>
                      <td style={{ color: formatDelta(lap.lap_time, bestTime) === "BEST" ? "#22c55e" : "#8d9aaa" }}>{formatDelta(lap.lap_time, bestTime)}</td>
                      <td>{lapTrustTier(lap)}</td>
                      <td>{lap.min_splitter_mm != null ? `${lap.min_splitter_mm.toFixed(1)} mm` : "Unavailable"}</td>
                      <td>
                        <div className="laps-chip-row">
                          {lapFlags(lap).map((flag) => <span key={flag} className="lap-flag-badge">{flag}</span>)}
                        </div>
                      </td>
                      <td>
                        <div className="laps-chip-row">
                          {memberships.length > 0 ? memberships.map((membership) => <span key={membership} className="lap-flag-badge">{membership}</span>) : <span className="muted">-</span>}
                        </div>
                      </td>
                      <td>{role ?? "-"}</td>
                      <td>{isSelectedLap ? "Selected lap" : inSelectedWindow ? "In selected window" : "-"}</td>
                      <td>
                        <div className="laps-action-row compact">
                          <button className="secondary-button" onClick={() => focusLapEvidence(lap)} aria-label={`Select lap ${lap.lap_number}`}>Select</button>
                          <button className="secondary-button" onClick={() => focusLapEvidence(lap, "platform_trace")} aria-label={`Open lap ${lap.lap_number} in Platform`}>Platform</button>
                          <button className="secondary-button" onClick={() => focusLapEvidence(lap, "map")} aria-label={`Open lap ${lap.lap_number} on Map`}>Map</button>
                          <button className="secondary-button" onClick={() => setBaseline(makeLapBasket(lap, `Baseline Lap ${lap.lap_number}`))}>Baseline</button>
                          <button className="secondary-button" onClick={() => setTest(makeLapBasket(lap, `Test Lap ${lap.lap_number}`))}>Test</button>
                          <button className="secondary-button" onClick={() => addToQueue(makeLapBasket(lap, `Lap ${lap.lap_number}`))}>Basket</button>
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr>
                        <td colSpan={11} style={{ padding: "10px 16px", background: "#0a0d14" }}>
                          <div className="laps-window-metrics">
                            <div><span className="muted">Basis</span><strong>Lap-level</strong></div>
                            <div><span className="muted">Avg Speed</span><strong><ValueDisplay value={lap.avg_speed_mph} unit="mph" precision={1} /></strong></div>
                            <div><span className="muted">Max Speed</span><strong><ValueDisplay value={lap.max_speed_mph} unit="mph" precision={1} /></strong></div>
                            <div><span className="muted">Avg RPM</span><strong><ValueDisplay value={lap.avg_rpm} unit="rpm" precision={0} /></strong></div>
                            <div><span className="muted">Min Splitter</span><strong><ValueDisplay value={lap.min_splitter_mm} unit="mm" precision={1} /></strong></div>
                          </div>
                          {lap.confidence_notes?.length > 0 && (
                            <div className="laps-chip-row" style={{ marginTop: 8 }}>
                              {lap.confidence_notes.map((note) => (
                                <span key={note} className="lap-flag-badge" style={{ background: "rgba(245,158,11,0.12)", color: "#f59e0b" }}>{note}</span>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
