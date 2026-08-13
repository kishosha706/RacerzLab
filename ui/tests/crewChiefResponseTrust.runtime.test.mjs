import assert from "node:assert/strict";
import { isCrewChiefWorkspaceResponse } from "../src/utils/crewChiefResponseTrust.ts";

const h = (value) => value.repeat(64);
const report = {
  reasoning_snapshot_sha256: h("a"), setup_id: "setup-1", setup_snapshot_sha256: h("b"),
  briefing: { action: { kind: "measurement_mission", title: "Measure", instruction: "Collect three eligible laps.", setup_authorized: false, control_key: null, current_value: null, proposed_value: null, source_event_ids: [] } },
  next_trustworthy_move: null,
};
const workspace = {
  schema_version: "p27.crew-chief-workspace.v1",
  identity: {
    run_id: "run-1", session_id: "session-1", reasoning_snapshot_sha256: h("a"),
    setup_id: "setup-1", setup_snapshot_sha256: h("b"), workspace_revision: h("c"),
    selected_scope_hash: h("f"), p20_profile_hash: null, p26_graph_version: "p26.v1",
    p20_state_revision: h("d"), p26_knowledge_graph_sha256: h("e"),
    p26_reasoning_snapshot_sha256: h("a"), active_workflow_id: null, active_workflow_revision: null,
    vehicle_runtime_identity_hash: h("9"), investigation_id: null,
  },
  evidence_index: { workspace_revision: h("c"), index_hash: h("8"), entries: [] },
  p19_mission_contract: null,
  success_contract: {
    workspace_revision: h("c"), target_scope: "braking entry", acceptance_rule: "Repeat the metric.",
    independence_unit: "eligible lap",
  },
  run_sentinel: {
    mission_state: "collecting", p19_plan_kind: "measurement_mission",
    mission: "Collect evidence", need: "Three eligible laps", success: "Repeatable evidence",
    stop: ["Stop on integrity failure."], required_laps: 3, accepted_laps: 0,
    collection_complete: false, stage: "measurement", laps: [],
  },
  critique: { outcome: "pass", passed: true, findings: [], strongest_contradiction: null },
  adaptive_research: { state: "data_locked", authority: "none", activation_gate: "Held-out evidence is required." },
  current_subgoal: null, pending_driver_question: null, investigation: null, folded_state: null,
  blocker_reasons: [], post_run_brief: ["P19 status: ready."], response_history_ids: [], driver_memory_ids: [],
  terminal_decision: {
    kind: "measurement_mission", title: "Measure", instruction: "Collect three eligible laps.",
    authority: "measurement_only", control_key: null, current_value: null, proposed_value: null,
    source_event_ids: [], workflow_id: null, workflow_revision: null, blocker_reasons: [],
  },
};
const scope = { runId: "run-1", sessionId: "session-1", report };
assert.equal(isCrewChiefWorkspaceResponse(workspace, scope), true);
for (const instruction of ["Set cross_weight_percent to 52.0.", "Keep.", "Stop the test."]) {
  const hostile = structuredClone(workspace);
  hostile.terminal_decision.instruction = instruction;
  assert.equal(isCrewChiefWorkspaceResponse(hostile, scope), false, instruction);
}
const foreign = structuredClone(workspace);
foreign.identity.session_id = "session-2";
assert.equal(isCrewChiefWorkspaceResponse(foreign, scope), false);
const forged = structuredClone(workspace);
forged.terminal_decision.control_key = "cross_weight_percent";
assert.equal(isCrewChiefWorkspaceResponse(forged, scope), false);
const malformedNested = structuredClone(workspace);
delete malformedNested.evidence_index.entries;
assert.equal(isCrewChiefWorkspaceResponse(malformedNested, scope), false);
const smuggledBrief = structuredClone(workspace);
smuggledBrief.post_run_brief = ["Set lf.ls_rebound to 4 clicks."];
assert.equal(isCrewChiefWorkspaceResponse(smuggledBrief, scope), false);
const foreignEvidence = structuredClone(workspace);
foreignEvidence.evidence_index.entries = [{
  artifact_id: "event-2", producer_id: "p19.reasoning_snapshot", run_id: "run-2",
  session_id: "session-1", setup_id: "setup-1", lap_numbers: [4],
  workspace_run_id: "run-1", workspace_session_id: "session-1", workspace_setup_id: "setup-1",
  source_run_id: "run-2", source_session_id: "session-1", source_setup_id: "setup-1",
  source_setup_sha256: h("7"), source_build_context_sha256: h("6"),
  source_provenance_available: true,
  lap_pct_start: 20, lap_pct_end: 30, phase: "center", mechanism_ids: [],
  component_ids: [], control_keys: [], source_channels: ["YawRate"],
  evidence_state: "measured", polarity: "support", blocker_reasons: [],
  authority_ceiling: "measurement_only",
}];
assert.equal(isCrewChiefWorkspaceResponse(foreignEvidence, scope), false);
assert.equal(isCrewChiefWorkspaceResponse(
  foreignEvidence, { ...scope, scopeRunIds: ["run-1", "run-2"] },
), true);
foreignEvidence.evidence_index.entries[0].lap_pct_start = 40;
assert.equal(isCrewChiefWorkspaceResponse(
  foreignEvidence, { ...scope, scopeRunIds: ["run-1", "run-2"] },
), false);

const controlledReport = structuredClone(report);
controlledReport.briefing.action = {
  kind: "controlled_test", title: "One P19 test", instruction: "Set the exact card.",
  setup_authorized: true, control_key: "cross_weight_percent", current_value: "51.5%",
  proposed_value: "52.0%", source_event_ids: ["event-1"],
};
controlledReport.next_trustworthy_move = { workflow_id: "workflow-1", workflow_updated_at: "revision-1" };
const controlled = structuredClone(workspace);
Object.assign(controlled.identity, { active_workflow_id: "workflow-1", active_workflow_revision: "revision-1" });
controlled.terminal_decision = {
  kind: "controlled_test", title: "One P19 test", instruction: "Set the exact card.",
  authority: "p19_projection_only", control_key: "cross_weight_percent", current_value: "51.5%",
  proposed_value: "52.0%", source_event_ids: ["event-1"], workflow_id: "workflow-1",
  workflow_revision: "revision-1", blocker_reasons: [],
};
assert.equal(isCrewChiefWorkspaceResponse(controlled, { ...scope, report: controlledReport }), true);
controlled.terminal_decision.proposed_value = "53.0%";
assert.equal(isCrewChiefWorkspaceResponse(controlled, { ...scope, report: controlledReport }), false);
