import type {
  EvidenceState,
  LapSummary,
  Recommendation,
  SetupSnapshot,
  TelemetryEvent,
} from "../types/telemetry";

const ACTIONABLE_EVIDENCE_STATES = new Set<EvidenceState>([
  "measured",
  "calculated",
  "estimated_proxy",
  "observed_correlation",
  "controlled_test_effect",
]);

const NON_BLOCKING_RACE_WARNING_PREFIXES = [
  "short runs cannot support strong tire degradation or cooling conclusions",
  "do not overclaim exact aerodynamic drag force",
  "missing optional channels",
  "shock movement telemetry is unavailable",
  "at least one low/negative splitter event occurred in slowdown context",
];

// Mirrors racelab_engine.analysis.lap_eligibility.INVALID_TUNING_TAGS so a
// hostile or stale overview cannot make a canonically rejected lap look clean
// while the authoritative backend is still loading or unavailable.
const INVALID_PACE_LAP_TAGS = new Set([
  "PARTIAL",
  "SHORT_RUN",
  "OUT_LAP",
  "COOLDOWN",
  "PIT_ROAD",
  "OFF_TRACK",
  "WRECK_OR_SPIN",
  "INVALID_SPEED_EVENT",
  "CAUTION",
  "YELLOW",
  "RESET",
  "ACTIVE_RESET",
  "SAMPLE_DISCONTINUITY",
  "POSITION_DISCONTINUITY",
  "SPARSE_POSITION_COVERAGE",
  "NON_CREDIBLE_LAP_SAMPLING",
  "INCIDENT_COUNT_INCREASE",
  "INVALID_FOR_PLATFORM_TUNING",
  "NO_SETUP_CONCLUSION",
]);

export function overviewWarningBlocksDecision(warning: string): boolean {
  const lower = warning.toLowerCase();
  if (NON_BLOCKING_RACE_WARNING_PREFIXES.some((prefix) => lower.startsWith(prefix))) return false;
  // New warning text fails closed until it is explicitly reviewed as a
  // scope-only caution. Unknown warnings cannot silently earn a Race call.
  return true;
}

export function setupSnapshotMatchesRun(
  snapshot: SetupSnapshot | null | undefined,
  runId: string,
): snapshot is SetupSnapshot {
  return snapshot != null && snapshot.run_id === runId;
}

export function bestUsefulLapMatchesRun(
  lap: LapSummary | null | undefined,
  runId: string,
): lap is LapSummary & { lap_time: number } {
  return lap != null
    && lap.run_id === runId
    && lap.is_complete
    && lap.is_useful
    && Number.isFinite(lap.lap_time)
    && (lap.lap_time ?? 0) > 0
    && !lap.classification_tags.some((tag) => INVALID_PACE_LAP_TAGS.has(tag.trim().toUpperCase()));
}

export function telemetryEventIsActionable(event: TelemetryEvent): boolean {
  return event.valid_for_tuning
    && ACTIONABLE_EVIDENCE_STATES.has(event.evidence_state)
    && event.blocker_reasons.length === 0
    && event.source_channels.length > 0;
}

export function recommendationIsActionable(
  recommendation: Recommendation,
  events: TelemetryEvent[],
): boolean {
  if (
    !ACTIONABLE_EVIDENCE_STATES.has(recommendation.evidence_state)
    || recommendation.blocker_reasons.length > 0
    || recommendation.source_channels.length === 0
    || recommendation.evidence_event_ids.length === 0
  ) return false;
  const actionableEventIds = new Set(
    events.filter(telemetryEventIsActionable).map((event) => event.event_id),
  );
  return recommendation.evidence_event_ids.every((eventId) => actionableEventIds.has(eventId));
}

export function recommendationBlockedReason(recommendation?: Recommendation | null): string {
  if (!recommendation) return "No recommendation is available.";
  return recommendation.blocker_reasons[0]
    ?? recommendation.confidence_limit_reasons[0]
    ?? "Supporting telemetry evidence is unavailable or incomplete.";
}
