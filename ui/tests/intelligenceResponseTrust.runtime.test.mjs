import assert from "node:assert/strict";

import {
  isIntelligenceQueryResponseBoundToReport,
  isRunIntelligenceResponse,
} from "../src/utils/intelligenceResponseTrust.ts";
import { hasSetupAuthorityDirective } from "../src/utils/setupAuthorityLanguage.js";

const hostileAuthorityProse = [
  "Set cross weight to 52.0% now.",
  "Cross weight: set it to 52.0%.",
  "RF spring should be 500 lb/in.",
  "Use 500 lb/in for the RF spring.",
  "Retain the new setup.",
  "Revert this change.",
  "End testing this direction.",
  "Do not continue testing.",
  "Keep.",
  "Undo it.",
  "Stop the test.",
  "This change is a keep.",
  "The change should be reverted.",
  "Rollback now.",
  "No more testing.",
  "Testing is over.",
  "We are done testing.",
  "Do not test again.",
  "Cross weight: fifty-two percent.",
  "RF spring: five hundred pounds per inch.",
  "Set LF LS rebound to 4 clicks.",
  "LF LS compression: 6 clicks.",
  "Set RF HS compression slope to 3 clicks.",
  "Set front master cylinder to 17.8 mm.",
  "Rear master cylinder: 19.1 mm.",
  "Set LF toe-in to 1.5 mm.",
  "RF toe-in: 2 mm.",
  "Set cross_weight_percent to 52.0.",
  "Set front_mc_mm to 17.8.",
  "Set lf.ls_rebound to 4 clicks.",
];
for (const prose of hostileAuthorityProse) {
  assert.equal(hasSetupAuthorityDirective(prose), true, prose);
}
for (const prose of [
  "Inspect the RF spring trace with the setup unchanged.",
  "Cross weight was captured in the setup snapshot.",
  "Only P19 may authorize one exact target, Keep/Undo, or stop-testing.",
]) {
  assert.equal(hasSetupAuthorityDirective(prose), false, prose);
}

const reasoningHash = "a".repeat(64);
const setupHash = "b".repeat(64);

const report = {
  schema_version: "p19.run-intelligence.v1",
  run_id: "run-1",
  session_id: "session-1",
  reasoning_snapshot_sha256: reasoningHash,
  setup_id: "setup-1",
  setup_snapshot_sha256: setupHash,
  briefing: {
    action: {
      kind: "measurement_mission",
      title: "Measure first",
      instruction: "Collect the frozen mission.",
      setup_authorized: false,
      control_key: null,
      current_value: null,
      proposed_value: null,
      evidence_state: "needs_confirmation",
      source_event_ids: [],
      blocker_reasons: [],
    },
  },
  vehicle_systems: null,
};

const reportExpectation = { runId: "run-1", sessionId: "session-1" };
assert.equal(isRunIntelligenceResponse(report, reportExpectation), true);

const projectedReport = structuredClone(report);
projectedReport.vehicle_systems = {
  schema_version: "p26.component-awareness.v4",
  run_id: "run-1",
  session_id: "session-1",
  reasoning_snapshot_sha256: reasoningHash,
  setup_id: "setup-1",
  setup_snapshot_sha256: setupHash,
  authority: "p19_projection_only",
  setup_authorized: false,
};
assert.equal(isRunIntelligenceResponse(projectedReport, reportExpectation), true);
projectedReport.vehicle_systems.reasoning_snapshot_sha256 = "c".repeat(64);
assert.equal(isRunIntelligenceResponse(projectedReport, reportExpectation), false);

const staleReport = structuredClone(report);
staleReport.reasoning_snapshot_sha256 = "c".repeat(64);
staleReport.vehicle_systems = { reasoning_snapshot_sha256: reasoningHash };
assert.equal(isRunIntelligenceResponse(staleReport, reportExpectation), false);

const missingSetupHash = structuredClone(report);
missingSetupHash.setup_snapshot_sha256 = null;
assert.equal(isRunIntelligenceResponse(missingSetupHash, reportExpectation), false);

const authorityWithoutSetup = structuredClone(report);
authorityWithoutSetup.setup_id = null;
authorityWithoutSetup.setup_snapshot_sha256 = null;
authorityWithoutSetup.briefing.action.setup_authorized = true;
assert.equal(isRunIntelligenceResponse(authorityWithoutSetup, reportExpectation), false);

const unauthorizedExactTarget = structuredClone(report);
unauthorizedExactTarget.briefing.action.proposed_value = "52.0%";
assert.equal(isRunIntelligenceResponse(unauthorizedExactTarget, reportExpectation), false);

for (const prose of hostileAuthorityProse) {
  const unauthorizedProseTarget = structuredClone(report);
  unauthorizedProseTarget.briefing.action.instruction = prose;
  assert.equal(isRunIntelligenceResponse(unauthorizedProseTarget, reportExpectation), false, prose);
}

const incompleteAuthorizedAction = structuredClone(report);
incompleteAuthorizedAction.briefing.action = {
  ...incompleteAuthorizedAction.briefing.action,
  kind: "controlled_test",
  setup_authorized: true,
  control_key: "cross_weight_percent",
  current_value: "51.8%",
  proposed_value: "52.0%",
};
assert.equal(isRunIntelligenceResponse(incompleteAuthorizedAction, reportExpectation), false);

const citation = {
  citation_id: "event-1",
  label: "Turn 1 center evidence",
  run_id: "run-1",
  lap_number: 4,
  lap_pct: 17.5,
  event_id: "event-1",
  workspace: "platform_trace",
  evidence_state: "measured",
  phase: "center",
  source_channels: ["Speed"],
  valid_for_tuning: true,
  track_region_id: "turn_1",
  track_region_label: "Turn 1 center",
  track_region_phase: "center",
  track_region_confidence: "section_geometry",
};
const query = {
  schema_version: "p19.intelligence-query.v1",
  run_id: "run-1",
  session_id: "session-1",
  reasoning_snapshot_sha256: reasoningHash,
  setup_id: "setup-1",
  setup_snapshot_sha256: setupHash,
  scope_run_ids: ["run-1"],
  action_authorized: false,
  interpreted_phase: "center",
  interpreted_track_region_id: "turn_1",
  interpreted_track_region_label: "Turn 1",
  citations: [citation],
};
assert.equal(isIntelligenceQueryResponseBoundToReport(query, report), true);

const straightQuery = structuredClone(query);
straightQuery.interpreted_phase = "straight";
straightQuery.interpreted_track_region_id = "front_stretch";
straightQuery.interpreted_track_region_label = "Front Stretch";
straightQuery.citations[0].phase = "straight";
straightQuery.citations[0].track_region_id = "front_stretch";
straightQuery.citations[0].track_region_label = "Front Stretch";
straightQuery.citations[0].track_region_phase = "straight";
assert.equal(isIntelligenceQueryResponseBoundToReport(straightQuery, report), true);
straightQuery.citations[0].track_region_id = "straight:front_stretch";
assert.equal(isIntelligenceQueryResponseBoundToReport(straightQuery, report), false);

for (const answer of ["Race-mode answer.", "Learning-mode explanation with more detail."]) {
  const presentationVariant = structuredClone(query);
  presentationVariant.answer = answer;
  assert.equal(isIntelligenceQueryResponseBoundToReport(presentationVariant, report), true);
}

for (const prose of hostileAuthorityProse) {
  const forgedQueryProse = structuredClone(query);
  forgedQueryProse.answer = prose;
  assert.equal(isIntelligenceQueryResponseBoundToReport(forgedQueryProse, report), false, prose);
}

const staleReasoning = structuredClone(query);
staleReasoning.reasoning_snapshot_sha256 = "c".repeat(64);
assert.equal(isIntelligenceQueryResponseBoundToReport(staleReasoning, report), false);

const staleSetup = structuredClone(query);
staleSetup.setup_snapshot_sha256 = "d".repeat(64);
assert.equal(isIntelligenceQueryResponseBoundToReport(staleSetup, report), false);

const forgedPhase = structuredClone(query);
forgedPhase.interpreted_phase = "exit";
assert.equal(isIntelligenceQueryResponseBoundToReport(forgedPhase, report), false);

const forgedRegion = structuredClone(query);
forgedRegion.interpreted_track_region_id = "turn_2";
forgedRegion.interpreted_track_region_label = "Turn 2";
assert.equal(isIntelligenceQueryResponseBoundToReport(forgedRegion, report), false);

const incompleteRegion = structuredClone(query);
incompleteRegion.citations[0].track_region_confidence = null;
assert.equal(isIntelligenceQueryResponseBoundToReport(incompleteRegion, report), false);

const foreignCitation = structuredClone(query);
foreignCitation.citations[0].run_id = "run-foreign";
assert.equal(isIntelligenceQueryResponseBoundToReport(foreignCitation, report), false);
