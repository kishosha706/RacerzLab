import type {
  EngineeringBlocker,
  EngineeringBlockTarget,
  EvidenceState,
  LapSummary,
  SetupSnapshot,
  TelemetryCapabilitySummary,
  TelemetryEvent,
} from "../types/telemetry";

const ACTIONABLE_EVIDENCE_STATES = new Set<EvidenceState>([
  "measured",
  "calculated",
  "estimated_proxy",
  "observed_correlation",
  "controlled_test_effect",
]);

const ENGINEERING_BLOCK_TARGETS = new Set<EngineeringBlockTarget>([
  "observation",
  "comparison",
  "performance",
  "mechanism",
  "component",
  "setup_attribution",
  "navigation",
]);

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
  "CLOCK_RESET_BOUNDARY",
  "TIMING_INTEGRITY_BLOCKED",
  "POSITION_DISCONTINUITY",
  "SPARSE_POSITION_COVERAGE",
  "NON_CREDIBLE_LAP_SAMPLING",
  "INCIDENT_COUNT_INCREASE",
  "INVALID_FOR_PLATFORM_TUNING",
  "NO_SETUP_CONCLUSION",
]);

export function engineeringBlockersMatchRun(
  blockers: unknown,
  runId: string,
): blockers is EngineeringBlocker[] {
  if (!Array.isArray(blockers)) return false;
  const identities = new Set<string>();
  for (const blocker of blockers) {
    if (typeof blocker !== "object" || blocker == null) return false;
    const candidate = blocker as Partial<EngineeringBlocker>;
    if (
      typeof candidate.code !== "string"
      || !/^[A-Z][A-Z0-9_]+$/.test(candidate.code)
      || typeof candidate.scope !== "string"
      || !/^[a-z][a-z0-9_]+$/.test(candidate.scope)
      || !["info", "warning", "blocker", "critical"].includes(candidate.severity ?? "")
      || !["unavailable", "blocked_by_context", "needs_confirmation"].includes(candidate.evidence_state ?? "")
      || typeof candidate.message !== "string"
      || candidate.message.length === 0
      || typeof candidate.recovery !== "string"
      || candidate.recovery.length === 0
      || !Array.isArray(candidate.blocks)
      || candidate.blocks.some((target) => !ENGINEERING_BLOCK_TARGETS.has(target))
      || new Set(candidate.blocks).size !== candidate.blocks.length
      || !Array.isArray(candidate.source_artifact_ids)
      || new Set(candidate.source_artifact_ids).size !== candidate.source_artifact_ids.length
      || !Array.isArray(candidate.source_channels)
      || new Set(candidate.source_channels).size !== candidate.source_channels.length
    ) return false;
    const physical = candidate.physical_scope;
    if (physical != null) {
      if (
        typeof physical !== "object"
        || (physical.run_id != null && physical.run_id !== runId)
        || !Array.isArray(physical.event_ids)
        || new Set(physical.event_ids).size !== physical.event_ids.length
        || (physical.lap_pct_start == null) !== (physical.lap_pct_end == null)
        || (physical.lap_pct_start != null && (
          !Number.isFinite(physical.lap_pct_start)
          || !Number.isFinite(physical.lap_pct_end)
          || physical.lap_pct_start < 0
          || (physical.lap_pct_end ?? -1) > 100
          || physical.lap_pct_start > (physical.lap_pct_end ?? -1)
        ))
      ) return false;
    }
    const identity = `${candidate.code}:${candidate.scope}`;
    if (identities.has(identity)) return false;
    identities.add(identity);
  }
  return true;
}

export function engineeringBlockerBlocksAny(
  blocker: EngineeringBlocker,
  targets: readonly EngineeringBlockTarget[],
): boolean {
  return targets.some((target) => blocker.blocks.includes(target));
}

export function overviewBlockerBlocksDecision(blocker: EngineeringBlocker): boolean {
  return engineeringBlockerBlocksAny(blocker, ["observation", "navigation"]);
}

export function performanceBlockerBlocksDecision(blocker: EngineeringBlocker): boolean {
  return engineeringBlockerBlocksAny(blocker, ["performance", "comparison", "navigation"]);
}

export function telemetryClockDecisionReady(
  summary: TelemetryCapabilitySummary | null | undefined,
): boolean {
  return summary?.qualified_clock_decision_ready === true
    && summary.qualified_clock_state === "qualified"
    && summary.qualified_clock_primary === "session_tick";
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
