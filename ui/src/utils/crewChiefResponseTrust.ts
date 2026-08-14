import type { CrewChiefEvidenceEntry, CrewChiefWorkspace } from "../types/crewChief";
import type { RunIntelligenceReport } from "../types/intelligence";
import type { PerformanceIntelligenceProjection } from "../types/performanceIntelligence";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";
import { isPerformanceIntelligenceProjection } from "./performanceIntelligenceTrust.js";

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
const evidenceStates = new Set([
  "measured", "calculated", "estimated_proxy", "observed_correlation",
  "controlled_test_effect", "unavailable", "blocked_by_context", "needs_confirmation",
]);
const performanceProducers = new Map<string, string>([
  ["p32.lap_time_opportunity", "lap_time_opportunity"],
  ["p32.time_loss_origin", "time_loss_origin"],
  ["p32.corner_performance_chain", "corner_performance_chain"],
  ["p32.exit_carry", "exit_carry"],
  ["p32.path_efficiency", "path_efficiency"],
  ["p32.driver_vehicle_separation", "driver_vehicle_separation"],
  ["p32.track_demand", "track_demand"],
  ["p32.component_performance_link", "component_performance_link"],
  ["p32.objective_envelope", "objective_envelope"],
]);
const crewMechanisms = new Set([
  "driver_execution", "braking_response", "corner_rotation", "tire_state",
  "damper_response", "platform_response", "resistance_scrub_like",
  "powertrain_response", "stint_trend", "sim_integrity",
]);
const percentage = (value: unknown): value is number =>
  finiteNumber(value) && value >= 0 && value <= 100;
const sameJson = (left: unknown, right: unknown): boolean =>
  JSON.stringify(left) === JSON.stringify(right);
const deepEqual = (left: unknown, right: unknown): boolean => {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right)
      && left.length === right.length
      && left.every((item, index) => deepEqual(item, right[index]));
  }
  if (!record(left) || !record(right)) return false;
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return sameJson(leftKeys, rightKeys)
    && leftKeys.every((key) => deepEqual(left[key], right[key]));
};

function uniqueChannels(states: Array<Record<string, unknown> | null>): string[] {
  const channels: string[] = [];
  for (const state of states) {
    if (!state || !Array.isArray(state.source_channels)) continue;
    for (const channel of state.source_channels) {
      if (typeof channel === "string" && !channels.includes(channel)) channels.push(channel);
    }
  }
  return channels;
}
const mappedMechanisms = (values: string[]): string[] => [
  ...new Set(values.map((item) => crewMechanisms.has(item) ? item : "unclassified")),
];

function validTypedArtifactEnvelope(value: Record<string, unknown>): boolean {
  const expectedType = performanceProducers.get(String(value.producer_id));
  const artifact = value.typed_artifact;
  if (expectedType === undefined) return artifact === null;
  if (!record(artifact) || typeof artifact.artifact_type !== "string") return false;
  if (artifact.artifact_type === "unavailable") {
    return artifact.claimed_artifact_type === expectedType
      && value.evidence_state === "unavailable"
      && safeTexts(artifact.blocker_reasons)
      && artifact.blocker_reasons.length > 0
      && sameJson(artifact.blocker_reasons, value.blocker_reasons)
      && (value.phase !== "unavailable" || (
        value.lap_pct_start === 0
        && value.lap_pct_end === 100
        && new RegExp(`^${String(value.producer_id).replace(/\./g, "\\.")}:unavailable:[0-9a-f]{16}$`)
          .test(String(value.artifact_id))
      ));
  }
  if (artifact.artifact_type !== expectedType || value.evidence_state === "unavailable") return false;
  switch (artifact.artifact_type) {
    case "lap_time_opportunity":
    case "time_loss_origin": {
      if (!record(artifact.opportunity)) return false;
      const suffix = artifact.artifact_type === "time_loss_origin" ? ":time-origin" : "";
      return value.artifact_id === `${String(artifact.opportunity.opportunity_id)}${suffix}`
        && value.lap_pct_start === artifact.opportunity.start_pct
        && value.lap_pct_end === artifact.opportunity.end_pct;
    }
    case "exit_carry":
      return record(artifact.opportunity)
        && finiteNumber(artifact.opportunity.following_phase_effect_s)
        && percentage(artifact.opportunity.following_phase_start_pct)
        && percentage(artifact.opportunity.following_phase_end_pct)
        && artifact.opportunity.following_phase_start_pct <= artifact.opportunity.following_phase_end_pct
        && value.artifact_id === `${String(artifact.opportunity.opportunity_id)}:exit-carry`
        && value.lap_pct_start === artifact.opportunity.following_phase_start_pct
        && value.lap_pct_end === artifact.opportunity.following_phase_end_pct;
    case "corner_performance_chain":
      return percentage(artifact.start_pct)
        && percentage(artifact.end_pct)
        && artifact.start_pct <= artifact.end_pct
        && record(artifact.chain)
        && value.artifact_id === artifact.chain.chain_id
        && value.lap_pct_start === artifact.start_pct
        && value.lap_pct_end === artifact.end_pct;
    case "path_efficiency":
      return safeText(artifact.chain_id)
        && record(artifact.phase_state)
        && finiteNumber(artifact.phase_state.path_delta_m)
        && percentage(artifact.phase_state.start_pct)
        && percentage(artifact.phase_state.end_pct)
        && artifact.phase_state.start_pct <= artifact.phase_state.end_pct
        && value.artifact_id === `${artifact.chain_id}:path:${String(artifact.phase_state.phase)}`
        && value.lap_pct_start === artifact.phase_state.start_pct
        && value.lap_pct_end === artifact.phase_state.end_pct;
    case "driver_vehicle_separation":
      return safeText(artifact.chain_id)
        && safeText(artifact.track_region)
        && percentage(artifact.start_pct)
        && percentage(artifact.end_pct)
        && artifact.start_pct <= artifact.end_pct
        && record(artifact.separation)
        && value.artifact_id === artifact.separation.separation_id
        && value.lap_pct_start === artifact.start_pct
        && value.lap_pct_end === artifact.end_pct;
    case "track_demand":
      return record(artifact.profile)
        && /^p32-track-demand:[0-9a-f]{20}$/.test(String(value.artifact_id));
    case "component_performance_link":
      return record(artifact.influence)
        && value.artifact_id === artifact.influence.influence_id;
    case "objective_envelope":
      return record(artifact.envelope)
        && /^p32-objective:[0-9a-f]{20}$/.test(String(value.artifact_id));
    default:
      return false;
  }
}

function unavailableMatchesProjection(
  claimedType: string,
  projection: PerformanceIntelligenceProjection,
): boolean {
  switch (claimedType) {
    case "lap_time_opportunity":
    case "time_loss_origin":
      return projection.opportunity_map.opportunities.length === 0;
    case "corner_performance_chain":
      return projection.corner_chains.length === 0 || projection.corner_chains.every((chain) => (
        [chain.approach_state, chain.braking_state, chain.entry_state, chain.center_state, chain.exit_state, chain.carry_state]
          .every((state) => state === null)
        && chain.local_time_effect_s === null
        && chain.downstream_time_effect_s === null
      ));
    case "exit_carry":
      return projection.opportunity_map.opportunities.every((item) => item.following_phase_effect_s === null);
    case "path_efficiency":
      return projection.corner_chains.every((chain) => (
        [chain.approach_state, chain.braking_state, chain.entry_state, chain.center_state, chain.exit_state, chain.carry_state]
          .every((state) => state?.path_delta_m == null)
      ));
    case "driver_vehicle_separation":
      return projection.corner_chains.every((chain) => chain.driver_vehicle_separation.length === 0);
    case "track_demand":
      return [
        projection.track_demand.full_throttle_fraction,
        projection.track_demand.braking_fraction,
        projection.track_demand.cornering_fraction,
        projection.track_demand.speed_min_mph,
        projection.track_demand.speed_max_mph,
        projection.track_demand.disturbance_exposure_fraction,
        projection.track_demand.traffic_exposure_fraction,
      ].every((metric) => metric === null);
    case "component_performance_link":
      return projection.component_influences.length === 0;
    case "objective_envelope":
      return false;
    default:
      return false;
  }
}

export function typedArtifactMatchesProjection(
  entry: CrewChiefEvidenceEntry,
  projection: PerformanceIntelligenceProjection,
  identity: Record<string, unknown>,
): boolean {
  if (!entry.producer_id.startsWith("p32.")) return entry.typed_artifact === null;
  const artifact = entry.typed_artifact;
  if (artifact === null
    || entry.run_id !== projection.run_id
    || entry.session_id !== projection.session_id
    || entry.setup_id !== projection.basis.setup_id
    || entry.workspace_run_id !== projection.run_id
    || entry.workspace_session_id !== projection.session_id
    || entry.workspace_setup_id !== projection.basis.setup_id
    || entry.source_run_id !== projection.run_id
    || entry.source_session_id !== projection.session_id
    || entry.source_setup_id !== projection.basis.setup_id
    || entry.source_setup_sha256 !== identity.setup_snapshot_sha256
    || entry.source_build_context_sha256 !== identity.vehicle_runtime_identity_hash
    || entry.source_provenance_available !== true
    || entry.objective !== projection.objective_id
    || entry.polarity !== "neutral"
    || entry.control_keys.length !== 0
    || !sameJson(entry.lap_numbers, projection.basis.source_lap_numbers)) return false;
  if (artifact.artifact_type === "unavailable") {
    const expectedAuthority = artifact.claimed_artifact_type === "driver_vehicle_separation" || artifact.claimed_artifact_type === "objective_envelope"
      ? "context_only" : "observation_only";
    if (entry.authority_ceiling !== expectedAuthority) return false;
    if (entry.phase === "unavailable") {
      return entry.source_channels.length === 0
        && entry.component_ids.length === 0
        && unavailableMatchesProjection(artifact.claimed_artifact_type, projection);
    }
    if (artifact.claimed_artifact_type === "corner_performance_chain" && entry.phase === "corner_chain") {
      const chain = projection.corner_chains.find((item) => item.chain_id === entry.artifact_id);
      if (!chain) return false;
      const states = [chain.approach_state, chain.braking_state, chain.entry_state, chain.center_state, chain.exit_state, chain.carry_state];
      const present = states.filter((state) => state !== null);
      const start = present.length ? Math.min(...present.map((state) => state.start_pct)) : 0;
      const end = present.length ? Math.max(...present.map((state) => state.end_pct)) : 100;
      return present.length === 0
        && chain.local_time_effect_s === null
        && chain.downstream_time_effect_s === null
        && entry.lap_pct_start === start
        && entry.lap_pct_end === end
        && sameJson(entry.source_channels, uniqueChannels(states as Array<Record<string, unknown> | null>));
    }
    if (artifact.claimed_artifact_type === "track_demand" && entry.phase === "whole_run") {
      return unavailableMatchesProjection("track_demand", projection)
        && /^p32-track-demand:[0-9a-f]{20}$/.test(entry.artifact_id)
        && sameJson(entry.source_channels, projection.track_demand.source_channels);
    }
    return false;
  }
  const opportunities = projection.opportunity_map.opportunities;
  const chains = projection.corner_chains;
  switch (artifact.artifact_type) {
    case "lap_time_opportunity":
    case "time_loss_origin": {
      const canonical = opportunities.find((item) => item.opportunity_id === artifact.opportunity.opportunity_id);
      return canonical !== undefined
        && deepEqual(artifact.opportunity, canonical)
        && entry.phase === canonical.phase
        && entry.evidence_state === (["qualified", "qualified_pair"].includes(canonical.context_state) ? "observed_correlation" : "blocked_by_context")
        && sameJson(entry.source_channels, canonical.source_channels)
        && sameJson(entry.mechanism_ids, mappedMechanisms(canonical.mechanism_candidates))
        && sameJson(entry.component_ids, canonical.component_candidates)
        && entry.authority_ceiling === "observation_only";
    }
    case "exit_carry": {
      const canonical = opportunities.find((item) => item.opportunity_id === artifact.opportunity.opportunity_id);
      return canonical !== undefined
        && deepEqual(artifact.opportunity, canonical)
        && entry.phase === "following_straight_carry"
        && entry.evidence_state === (["qualified", "qualified_pair"].includes(canonical.context_state) ? "observed_correlation" : "blocked_by_context")
        && sameJson(entry.source_channels, canonical.source_channels)
        && sameJson(entry.mechanism_ids, mappedMechanisms(canonical.mechanism_candidates))
        && sameJson(entry.component_ids, canonical.component_candidates)
        && entry.authority_ceiling === "observation_only";
    }
    case "corner_performance_chain": {
      const canonical = chains.find((item) => item.chain_id === artifact.chain.chain_id);
      const channels = canonical ? uniqueChannels([
        canonical.approach_state, canonical.braking_state, canonical.entry_state,
        canonical.center_state, canonical.exit_state, canonical.carry_state,
      ] as Array<Record<string, unknown> | null>) : [];
      return canonical !== undefined
        && deepEqual(artifact.chain, canonical)
        && entry.phase === "corner_chain"
        && entry.evidence_state === (projection.basis.context_blockers.length ? "blocked_by_context" : "calculated")
        && sameJson(entry.source_channels, channels)
        && entry.mechanism_ids.length === 0
        && entry.component_ids.length === 0
        && entry.authority_ceiling === "observation_only";
    }
    case "path_efficiency": {
      const chain = chains.find((item) => item.chain_id === artifact.chain_id);
      const states = chain ? [chain.approach_state, chain.braking_state, chain.entry_state, chain.center_state, chain.exit_state, chain.carry_state] : [];
      return chain !== undefined
        && states.some((state) => state !== null && deepEqual(state, artifact.phase_state))
        && entry.phase === artifact.phase_state.phase
        && entry.evidence_state === (projection.basis.context_blockers.length ? "blocked_by_context" : "calculated")
        && sameJson(entry.source_channels, artifact.phase_state.source_channels)
        && entry.mechanism_ids.length === 0
        && entry.component_ids.length === 0
        && entry.authority_ceiling === "observation_only";
    }
    case "driver_vehicle_separation": {
      const chain = chains.find((item) => item.chain_id === artifact.chain_id);
      const channels = chain ? uniqueChannels([
        chain.approach_state, chain.braking_state, chain.entry_state,
        chain.center_state, chain.exit_state, chain.carry_state,
      ] as Array<Record<string, unknown> | null>) : [];
      const canonical = chain?.driver_vehicle_separation.find((item) => item.separation_id === artifact.separation.separation_id);
      return chain !== undefined
        && artifact.track_region === chain.track_region
        && canonical !== undefined
        && deepEqual(artifact.separation, canonical)
        && entry.phase === canonical.phase
        && entry.evidence_state === (["context_contaminated", "unresolved"].includes(canonical.result) ? "blocked_by_context" : "observed_correlation")
        && sameJson(entry.source_channels, channels)
        && entry.mechanism_ids.length === 0
        && entry.component_ids.length === 0
        && entry.authority_ceiling === "context_only";
    }
    case "track_demand":
      return deepEqual(artifact.profile, projection.track_demand)
        && entry.phase === "whole_run"
        && entry.evidence_state === "calculated"
        && sameJson(entry.source_channels, projection.track_demand.source_channels)
        && entry.mechanism_ids.length === 0
        && entry.component_ids.length === 0
        && entry.authority_ceiling === "observation_only";
    case "component_performance_link": {
      const canonical = projection.component_influences.find((item) => item.influence_id === artifact.influence.influence_id);
      return canonical !== undefined
        && deepEqual(artifact.influence, canonical)
        && entry.phase === "component_performance_link"
        && entry.evidence_state === ({
          mechanically_relevant: "needs_confirmation",
          response_supported: "observed_correlation",
          controlled_response_observed: "controlled_test_effect",
        } as const)[canonical.runtime_support_state]
        && sameJson(entry.source_channels, canonical.measurable_through)
        && sameJson(entry.mechanism_ids, mappedMechanisms(canonical.performance_mechanism_ids))
        && sameJson(entry.component_ids, [canonical.component_id])
        && entry.authority_ceiling === "observation_only";
    }
    case "objective_envelope":
      return deepEqual(artifact.envelope, projection.objective_envelope)
        && entry.phase === "whole_run"
        && entry.evidence_state === "calculated"
        && entry.source_channels.length === 0
        && entry.mechanism_ids.length === 0
        && entry.component_ids.length === 0
        && entry.authority_ceiling === "context_only";
    default:
      return false;
  }
}

export function validEvidenceEntry(
  value: unknown,
  sessionId: string,
  scopeRunIds: ReadonlySet<string>,
  objectiveId: string,
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
    && value.objective === objectiveId
    && evidenceStates.has(String(value.evidence_state))
    && ["support", "contradiction", "neutral"].includes(String(value.polarity))
    && safeTexts(value.blocker_reasons)
    && (value.source_provenance_available
      || value.blocker_reasons.includes("source identity unavailable"))
    && new Set(value.blocker_reasons).size === value.blocker_reasons.length
    && validTypedArtifactEnvelope(value)
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
    objectiveId: string;
  },
): value is CrewChiefWorkspace {
  if (!record(value) || value.schema_version !== "p32.crew-chief-workspace.v2") return false;
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
    || identity.objective_id !== scope.objectiveId
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
    || typeof identity.p32_projection_sha256 !== "string"
    || !hash.test(identity.p32_projection_sha256)
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
      validEvidenceEntry(entry, scope.sessionId, scopeRunIds, scope.objectiveId)
    ))
  ) return false;
  const trustedEntries = value.evidence_index.entries as CrewChiefEvidenceEntry[];
  const p32Evidence = new Map<string, CrewChiefEvidenceEntry>(
    trustedEntries
      .filter((entry) => entry.producer_id === "p32.lap_time_opportunity"
        && entry.evidence_state !== "unavailable"
        && entry.lap_pct_start !== null
        && entry.lap_pct_end !== null)
      .map((entry) => [String(entry.artifact_id), entry]),
  );
  const p19Next = scope.report.briefing.action.instruction
    || scope.report.briefing.action.title
    || "Hold the current setup and complete the P19 measurement plan.";
  if (!isPerformanceIntelligenceProjection(value.performance_intelligence, {
    runId: scope.runId,
    sessionId: scope.sessionId,
    setupId: String(identity.setup_id),
    setupSnapshotHash: String(identity.setup_snapshot_sha256),
    buildContextHash: String(identity.vehicle_runtime_identity_hash),
    objectiveId: scope.objectiveId,
    p19Hash: String(identity.reasoning_snapshot_sha256),
    p20Revision: String(identity.p20_state_revision),
    p26Hash: String(identity.p26_knowledge_graph_sha256),
    projectionHash: String(identity.p32_projection_sha256),
    p19Next,
    scopeRunIds,
    opportunityEvidence: p32Evidence,
  })) return false;
  const trustedProjection = value.performance_intelligence as PerformanceIntelligenceProjection;
  if (!trustedEntries.every((entry) => (
    typedArtifactMatchesProjection(entry, trustedProjection, identity)
  ))) return false;
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
