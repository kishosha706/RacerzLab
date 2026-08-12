import type { CrewChiefWorkspace } from "../types/crewChief";
import type { RunIntelligenceReport } from "../types/intelligence";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

const hash = /^[0-9a-f]{64}$/;
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string" && item.length > 0);
const nullableString = (value: unknown): value is string | null =>
  value === null || typeof value === "string";
const finiteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const safeText = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && !hasSetupAuthorityDirective(value);
const safeTexts = (value: unknown): value is string[] =>
  strings(value) && value.every((item) => !hasSetupAuthorityDirective(item));

function validEvidenceEntry(value: unknown, sessionId: string): boolean {
  if (!record(value)) return false;
  return typeof value.artifact_id === "string"
    && typeof value.producer_id === "string"
    && typeof value.run_id === "string"
    && value.session_id === sessionId
    && typeof value.setup_id === "string"
    && Array.isArray(value.lap_numbers)
    && value.lap_numbers.every((lap) => Number.isInteger(lap) && lap >= 0)
    && (value.lap_pct_start === null || finiteNumber(value.lap_pct_start))
    && (value.lap_pct_end === null || finiteNumber(value.lap_pct_end))
    && nullableString(value.phase)
    && strings(value.mechanism_ids)
    && strings(value.component_ids)
    && strings(value.control_keys)
    && strings(value.source_channels)
    && typeof value.evidence_state === "string"
    && ["support", "contradiction", "neutral"].includes(String(value.polarity))
    && safeTexts(value.blocker_reasons)
    && ["observation_only", "context_only", "measurement_only", "p19_projection_only"]
      .includes(String(value.authority_ceiling));
}

export function isCrewChiefWorkspaceResponse(
  value: unknown,
  scope: { runId: string; sessionId: string; report: RunIntelligenceReport },
): value is CrewChiefWorkspace {
  if (!record(value) || value.schema_version !== "p27.crew-chief-workspace.v1") return false;
  if (
    !record(value.identity)
    || !record(value.terminal_decision)
    || !record(value.evidence_index)
    || !record(value.success_contract)
    || !record(value.run_sentinel)
    || !record(value.critique)
    || !record(value.adaptive_research)
  ) return false;
  const identity = value.identity;
  const decision = value.terminal_decision;
  if (
    identity.run_id !== scope.runId
    || identity.session_id !== scope.sessionId
    || identity.reasoning_snapshot_sha256 !== scope.report.reasoning_snapshot_sha256
    || identity.setup_id !== scope.report.setup_id
    || identity.setup_snapshot_sha256 !== scope.report.setup_snapshot_sha256
    || typeof identity.workspace_revision !== "string"
    || !hash.test(identity.workspace_revision)
    || typeof identity.selected_scope_hash !== "string"
    || !hash.test(identity.selected_scope_hash)
    || typeof identity.p20_state_revision !== "string"
    || !hash.test(identity.p20_state_revision)
    || !(identity.p20_profile_hash === null
      || (typeof identity.p20_profile_hash === "string" && hash.test(identity.p20_profile_hash)))
    || typeof identity.p26_graph_version !== "string"
    || identity.p26_graph_version.length === 0
    || typeof identity.p26_knowledge_graph_sha256 !== "string"
    || !hash.test(identity.p26_knowledge_graph_sha256)
    || typeof identity.p26_reasoning_snapshot_sha256 !== "string"
    || identity.p26_reasoning_snapshot_sha256 !== scope.report.reasoning_snapshot_sha256
    || typeof identity.vehicle_runtime_identity_hash !== "string"
    || !hash.test(identity.vehicle_runtime_identity_hash)
    || !nullableString(identity.active_workflow_id)
    || !nullableString(identity.active_workflow_revision)
    || ((identity.active_workflow_id === null) !== (identity.active_workflow_revision === null))
    || !nullableString(identity.investigation_id)
    || value.evidence_index.workspace_revision !== identity.workspace_revision
    || typeof value.evidence_index.index_hash !== "string"
    || !hash.test(value.evidence_index.index_hash)
    || !Array.isArray(value.evidence_index.entries)
    || !value.evidence_index.entries.every((entry) => validEvidenceEntry(entry, scope.sessionId))
  ) return false;
  if (
    typeof decision.kind !== "string"
    || typeof decision.title !== "string"
    || typeof decision.instruction !== "string"
    || !strings(decision.source_event_ids)
    || !safeTexts(decision.blocker_reasons)
  ) return false;
  const success = value.success_contract;
  const sentinel = value.run_sentinel;
  const critique = value.critique;
  if (
    success.workspace_revision !== identity.workspace_revision
    || !safeText(success.target_scope)
    || !safeText(success.acceptance_rule)
    || !safeText(success.independence_unit)
    || !safeText(sentinel.mission)
    || !safeText(sentinel.need)
    || !safeText(sentinel.success)
    || !safeTexts(sentinel.stop)
    || !Number.isInteger(sentinel.required_laps)
    || !Number.isInteger(sentinel.accepted_laps)
    || !Array.isArray(sentinel.laps)
    || !sentinel.laps.every((lap) => record(lap)
      && Number.isInteger(lap.lap_number)
      && ["accepted", "rejected"].includes(String(lap.status))
      && safeTexts(lap.reasons))
    || typeof critique.passed !== "boolean"
    || !safeTexts(critique.findings)
    || !(critique.strongest_contradiction === null || safeText(critique.strongest_contradiction))
    || !safeTexts(value.blocker_reasons)
    || !safeTexts(value.post_run_brief)
    || !strings(value.response_history_ids)
    || !strings(value.driver_memory_ids)
    || value.adaptive_research.state !== "data_locked"
    || value.adaptive_research.authority !== "none"
    || !safeText(value.adaptive_research.activation_gate)
  ) return false;
  if (value.current_subgoal !== null && (
    !record(value.current_subgoal)
    || !safeText(value.current_subgoal.title)
    || !safeText(value.current_subgoal.why_this_tool)
  )) return false;
  if (value.pending_driver_question !== null && (
    !record(value.pending_driver_question)
    || value.pending_driver_question.workspace_revision !== identity.workspace_revision
    || !safeText(value.pending_driver_question.question)
    || !safeText(value.pending_driver_question.reason)
    || !safeTexts(value.pending_driver_question.answer_options)
  )) return false;
  if (value.investigation !== null && (
    !record(value.investigation)
    || value.investigation.investigation_id !== identity.investigation_id
    || typeof value.investigation.raw_driver_report !== "string"
    || typeof value.investigation.canonical_problem !== "string"
  )) return false;
  if (value.folded_state !== null && (
    !record(value.folded_state)
    || value.folded_state.investigation_id !== identity.investigation_id
    || !["open", "complete", "stale", "abandoned"].includes(String(value.folded_state.status))
  )) return false;
  const action = scope.report.briefing.action;
  if (decision.kind === "controlled_test") {
    const move = scope.report.next_trustworthy_move;
    return decision.authority === "p19_projection_only"
      && action.setup_authorized === true
      && action.kind === "controlled_test"
      && decision.title === action.title
      && decision.instruction === action.instruction
      && decision.control_key === action.control_key
      && decision.current_value === action.current_value
      && decision.proposed_value === action.proposed_value
      && JSON.stringify(decision.source_event_ids) === JSON.stringify(action.source_event_ids)
      && decision.workflow_id === identity.active_workflow_id
      && decision.workflow_revision === identity.active_workflow_revision
      && decision.workflow_id === move?.workflow_id
      && decision.workflow_revision === move?.workflow_updated_at;
  }
  if (
    decision.authority === "p19_projection_only"
    || decision.control_key != null
    || decision.current_value != null
    || decision.proposed_value != null
    || decision.workflow_id != null
    || decision.workflow_revision != null
  ) return false;
  return !hasSetupAuthorityDirective(decision.title)
    && !hasSetupAuthorityDirective(decision.instruction);
}
