import type { CrewChiefWorkspace } from "../types/crewChief";
import type { RunIntelligenceReport } from "../types/intelligence";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

const hash = /^[0-9a-f]{64}$/;
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const strings = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string" && item.length > 0);
const uniqueStrings = (value: unknown): value is string[] =>
  strings(value) && new Set(value).size === value.length;
const nullableString = (value: unknown): value is string | null =>
  value === null || typeof value === "string";
const finiteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const integerNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value);
const safeText = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0 && !hasSetupAuthorityDirective(value);
const safeTexts = (value: unknown): value is string[] =>
  strings(value) && value.every((item) => !hasSetupAuthorityDirective(item));

function validEvidenceEntry(
  value: unknown,
  sessionId: string,
  scopeRunIds: ReadonlySet<string>,
): boolean {
  if (!record(value)) return false;
  const lapNumbers = value.lap_numbers;
  const start = value.lap_pct_start;
  const end = value.lap_pct_end;
  return typeof value.artifact_id === "string" && value.artifact_id.length > 0
    && typeof value.producer_id === "string" && value.producer_id.length > 0
    && typeof value.run_id === "string" && scopeRunIds.has(value.run_id)
    && value.run_id === value.source_run_id
    && value.session_id === sessionId
    && value.workspace_session_id === sessionId
    && typeof value.workspace_run_id === "string"
    && scopeRunIds.has(String(value.workspace_run_id))
    && typeof value.workspace_setup_id === "string"
    && value.workspace_setup_id.length > 0
    && nullableString(value.setup_id)
    && nullableString(value.source_session_id)
    && nullableString(value.source_setup_id)
    && value.setup_id === value.source_setup_id
    && (value.source_setup_sha256 === null
      || (typeof value.source_setup_sha256 === "string" && hash.test(value.source_setup_sha256)))
    && (value.source_build_context_sha256 === null
      || (typeof value.source_build_context_sha256 === "string" && hash.test(value.source_build_context_sha256)))
    && typeof value.source_provenance_available === "boolean"
    && value.source_provenance_available === Boolean(
      value.source_session_id && value.source_setup_id
      && value.source_setup_sha256 && value.source_build_context_sha256,
    )
    && Array.isArray(lapNumbers)
    && lapNumbers.every((lap) => Number.isInteger(lap) && lap >= 0)
    && new Set(lapNumbers).size === lapNumbers.length
    && ((start === null && end === null)
      || (finiteNumber(start) && finiteNumber(end)
        && start >= 0 && end <= 100 && start <= end))
    && nullableString(value.phase)
    && uniqueStrings(value.mechanism_ids)
    && uniqueStrings(value.component_ids)
    && uniqueStrings(value.control_keys)
    && uniqueStrings(value.source_channels)
    && typeof value.evidence_state === "string"
    && ["support", "contradiction", "neutral"].includes(String(value.polarity))
    && safeTexts(value.blocker_reasons)
    && (value.source_provenance_available
      || value.blocker_reasons.includes("source identity unavailable"))
    && new Set(value.blocker_reasons).size === value.blocker_reasons.length
    && ["observation_only", "context_only", "measurement_only", "p19_projection_only"]
      .includes(String(value.authority_ceiling));
}

export function isCrewChiefWorkspaceResponse(
  value: unknown,
  scope: {
    runId: string;
    sessionId: string;
    report: RunIntelligenceReport;
    scopeRunIds?: readonly string[];
  },
): value is CrewChiefWorkspace {
  if (!record(value) || value.schema_version !== "p27.crew-chief-workspace.v1") return false;
  if (
    !record(value.identity)
    || !record(value.terminal_decision)
    || !record(value.evidence_index)
    || !record(value.run_sentinel)
    || !record(value.critique)
    || !record(value.adaptive_research)
  ) return false;
  const missionContract = value.p19_mission_contract;
  if (!(missionContract === null || (
    record(missionContract)
    && missionContract.schema_version === "p19.measurement-mission.v2"
    && typeof missionContract.contract_id === "string"
    && typeof missionContract.contract_sha256 === "string"
    && hash.test(missionContract.contract_sha256)
    && missionContract.run_id === scope.runId
    && missionContract.source_setup_id === scope.report.setup_id
    && missionContract.setup_sha256 === scope.report.setup_snapshot_sha256
    && integerNumber(missionContract.required_laps)
    && missionContract.required_laps >= 1
    && safeTexts(missionContract.acceptance_thresholds)
    && safeTexts(missionContract.integrity_stop_rules)
    && safeText(missionContract.purpose)
  ))) return false;
  const identity = value.identity;
  const decision = value.terminal_decision;
  const scopeRunIds = new Set(scope.scopeRunIds ?? [scope.runId]);
  if (
    scopeRunIds.size === 0
    || !scopeRunIds.has(scope.runId)
    || identity.run_id !== scope.runId
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
    || !value.evidence_index.entries.every((entry) => (
      validEvidenceEntry(entry, scope.sessionId, scopeRunIds)
    ))
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
  if (["blocked", "stop_testing"].includes(String(sentinel.p19_plan_kind))
    && (success !== null || sentinel.required_laps !== null || sentinel.collection_complete)) return false;
  const critique = value.critique;
  let acceptedOrdinal = 0;
  const sentinelLapsAreCanonical = Array.isArray(sentinel.laps)
    && sentinel.laps.every((lap) => {
      if (!record(lap)
        || !integerNumber(lap.lap_number)
        || !["accepted", "rejected"].includes(String(lap.status))
        || !safeTexts(lap.reasons)) return false;
      if (lap.status === "accepted") {
        acceptedOrdinal += 1;
        return lap.reasons.length === 0 && lap.accepted_ordinal === acceptedOrdinal;
      }
      return lap.reasons.length > 0 && lap.accepted_ordinal === null;
    });
  if (
    !(success === null || (record(success)
      && success.workspace_revision === identity.workspace_revision
      && safeText(success.target_scope)
      && safeText(success.acceptance_rule)
      && safeText(success.independence_unit)))
    || !["collecting", "blocked_by_p19", "stopped_by_p19", "awaiting_p19_score", "collection_complete"]
      .includes(String(sentinel.mission_state))
    || !["controlled_test", "measurement_mission", "discriminator", "stop_testing", "blocked"]
      .includes(String(sentinel.p19_plan_kind))
    || !safeText(sentinel.mission)
    || !safeText(sentinel.need)
    || !safeText(sentinel.success)
    || !safeTexts(sentinel.stop)
    || !(sentinel.required_laps === null
      || (integerNumber(sentinel.required_laps) && sentinel.required_laps >= 1))
    || !integerNumber(sentinel.accepted_laps)
    || sentinel.accepted_laps !== acceptedOrdinal
    || typeof sentinel.collection_complete !== "boolean"
    || sentinel.collection_complete !== (
      sentinel.required_laps !== null
      && acceptedOrdinal >= sentinel.required_laps
      && !["blocked_by_p19", "stopped_by_p19", "awaiting_p19_score"].includes(String(sentinel.mission_state))
    )
    || !["measurement", "A", "B", "A2", "blocked", "stopped", "awaiting_score"].includes(String(sentinel.stage))
    || !sentinelLapsAreCanonical
    || typeof critique.passed !== "boolean"
    || !["pass", "blocked", "reinvestigate", "ask_driver"].includes(String(critique.outcome))
    || critique.passed !== (critique.outcome === "pass")
    || !safeTexts(critique.findings)
    || (!critique.passed && critique.findings.length === 0)
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
    || typeof value.folded_state.accepted_workspace_revision !== "string"
    || !hash.test(value.folded_state.accepted_workspace_revision)
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
