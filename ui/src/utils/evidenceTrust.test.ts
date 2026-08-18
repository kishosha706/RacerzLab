import { describe, expect, it } from "vitest";

import type { EngineeringBlocker, TelemetryCapabilitySummary } from "../types/telemetry";
import {
  engineeringBlockersMatchRun,
  overviewBlockerBlocksDecision,
  performanceBlockerBlocksDecision,
  telemetryClockDecisionReady,
} from "./evidenceTrust";

function trafficBlocker(): EngineeringBlocker {
  return {
    code: "TRAFFIC_EXPOSURE",
    severity: "blocker",
    scope: "relative_resistance",
    blocks: ["mechanism", "component", "setup_attribution"],
    message: "Relative resistance attribution is blocked by nearby-car context.",
    evidence_state: "blocked_by_context",
    source_artifact_ids: ["run:run-1"],
    source_channels: ["car_dist_ahead", "car_dist_behind"],
    physical_scope: { run_id: "run-1", lap_number: 4, lap_pct_start: 20, lap_pct_end: 40, event_ids: ["event-1"] },
    recovery: "Repeat the same window without nearby-car exposure.",
  };
}

describe("typed engineering blocker scope", () => {
  it("keeps pace and platform observation usable when only resistance attribution is blocked", () => {
    const blocker = trafficBlocker();

    expect(engineeringBlockersMatchRun([blocker], "run-1")).toBe(true);
    expect(overviewBlockerBlocksDecision(blocker)).toBe(false);
    expect(performanceBlockerBlocksDecision(blocker)).toBe(false);
  });

  it("fails closed on typed run-integrity scope", () => {
    const blocker: EngineeringBlocker = {
      ...trafficBlocker(),
      code: "STORED_EVIDENCE_INTEGRITY_FAILURE",
      scope: "run_integrity",
      blocks: ["observation", "comparison", "performance", "navigation"],
    };

    expect(overviewBlockerBlocksDecision(blocker)).toBe(true);
    expect(performanceBlockerBlocksDecision(blocker)).toBe(true);
  });

  it("rejects foreign physical scope and unknown decision targets", () => {
    expect(engineeringBlockersMatchRun([
      { ...trafficBlocker(), physical_scope: { run_id: "foreign", event_ids: [] } },
    ], "run-1")).toBe(false);
    expect(engineeringBlockersMatchRun([
      { ...trafficBlocker(), blocks: ["performance", "made_up_target"] },
    ], "run-1")).toBe(false);
  });
});

describe("qualified telemetry clock readiness", () => {
  const summary: TelemetryCapabilitySummary = {
    declared_channels: 2,
    cached_channels: 2,
    unmapped_channels: 0,
    warning_channels: 0,
    lossless_archive_complete: true,
    analysis_readiness_counts: {},
    qualified_clock_state: "qualified",
    qualified_clock_primary: "session_tick",
    qualified_clock_decision_ready: true,
  };

  it("requires a server-qualified tick-primary clock", () => {
    expect(telemetryClockDecisionReady(summary)).toBe(true);
    expect(telemetryClockDecisionReady({
      ...summary,
      qualified_clock_state: "degraded",
    })).toBe(false);
    expect(telemetryClockDecisionReady({
      ...summary,
      qualified_clock_primary: "session_time",
    })).toBe(false);
    expect(telemetryClockDecisionReady({
      ...summary,
      qualified_clock_decision_ready: false,
    })).toBe(false);
  });
});
