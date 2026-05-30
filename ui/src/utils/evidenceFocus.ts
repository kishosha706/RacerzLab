import type { EvidenceContext, TelemetrySelection } from "../store/types";

export function hasWindowSelection(selection: TelemetrySelection): boolean {
  return selection.selectedLapScope === "lap_window"
    && selection.selectedLapWindowStart != null
    && selection.selectedLapWindowEnd != null;
}

export function lapIsInsideWindow(selection: TelemetrySelection, lapNumber: number | null | undefined): boolean {
  return hasWindowSelection(selection)
    && lapNumber != null
    && lapNumber >= (selection.selectedLapWindowStart ?? Number.NEGATIVE_INFINITY)
    && lapNumber <= (selection.selectedLapWindowEnd ?? Number.POSITIVE_INFINITY);
}

export function buildWindowEvidence(
  selection: TelemetrySelection,
  lapNumber: number | null | undefined,
): Pick<EvidenceContext, "lapScope" | "lapWindowStart" | "lapWindowEnd" | "representativeLap"> {
  if (lapIsInsideWindow(selection, lapNumber)) {
    return {
      lapScope: "lap_window",
      lapWindowStart: selection.selectedLapWindowStart ?? null,
      lapWindowEnd: selection.selectedLapWindowEnd ?? null,
      representativeLap: lapNumber ?? null,
    };
  }
  return {
    lapScope: lapNumber != null ? "single_lap" : "unknown",
    lapWindowStart: null,
    lapWindowEnd: null,
    representativeLap: null,
  };
}

function normalizePct(pct: number): number {
  const normalized = pct % 100;
  return normalized < 0 ? normalized + 100 : normalized;
}

export function lapPctInRange(
  lapPct: number | null | undefined,
  startPct: number | null | undefined,
  endPct: number | null | undefined,
): boolean {
  if (lapPct == null || startPct == null || endPct == null) return false;
  const normalizedLap = normalizePct(lapPct);
  const normalizedStart = normalizePct(startPct);
  const normalizedEnd = normalizePct(endPct);
  if (normalizedStart <= normalizedEnd) {
    return normalizedLap >= normalizedStart && normalizedLap <= normalizedEnd;
  }
  return normalizedLap >= normalizedStart || normalizedLap <= normalizedEnd;
}

export function buildZoneEvidence(
  selection: TelemetrySelection,
  options?: {
    lapPct?: number | null;
    preserveWithoutLapPct?: boolean;
  },
): Pick<EvidenceContext, "zoneId" | "zoneLabel" | "zoneStartPct" | "zoneEndPct"> {
  const zoneContext = {
    zoneId: selection.selectedZoneId ?? null,
    zoneLabel: selection.selectedZoneLabel ?? null,
    zoneStartPct: selection.selectedZoneStartPct ?? null,
    zoneEndPct: selection.selectedZoneEndPct ?? null,
  };
  const hasZoneSelection = zoneContext.zoneId != null
    || zoneContext.zoneLabel != null
    || zoneContext.zoneStartPct != null
    || zoneContext.zoneEndPct != null;
  if (!hasZoneSelection) {
    return { zoneId: null, zoneLabel: null, zoneStartPct: null, zoneEndPct: null };
  }
  if (options?.lapPct == null) {
    return options?.preserveWithoutLapPct
      ? zoneContext
      : { zoneId: null, zoneLabel: null, zoneStartPct: null, zoneEndPct: null };
  }
  return lapPctInRange(options.lapPct, zoneContext.zoneStartPct, zoneContext.zoneEndPct)
    ? zoneContext
    : { zoneId: null, zoneLabel: null, zoneStartPct: null, zoneEndPct: null };
}
