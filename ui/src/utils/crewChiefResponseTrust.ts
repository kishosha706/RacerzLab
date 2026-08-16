import type { CrewChiefEvidenceEntry, CrewChiefWorkspace } from "../types/crewChief";
import type { RunIntelligenceReport } from "../types/intelligence";
import {
  type EngineeringAwarenessProjection,
  isEngineeringAwarenessProjection,
} from "../types/engineeringAwareness.ts";
import type {
  CornerPerformanceChain,
  LapTimeOpportunity,
  PerformanceIntelligenceProjection,
  PerformancePhaseState,
} from "../types/performanceIntelligence";
import type {
  PerformanceMechanismAssessment,
  VehicleDynamicsChainStageKind,
} from "../types/vehicleDynamics";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";
import {
  canonicalEngineeringLearningSha256,
  isCrewChiefLearningPrior,
  isP19ReasoningMemory,
  isProblemFingerprint,
} from "./engineeringLearningTrust.js";
import { isPerformanceIntelligenceProjection } from "./performanceIntelligenceTrust.js";
import { isInvestigationImprovementProjection } from "./investigationImprovementTrust.ts";
import {
  type CanonicalP35P32Binding,
  deriveCanonicalP35P32Binding,
  isPerformanceMechanismAssessment,
} from "./vehicleDynamicsTrust.ts";
import { p35RuntimeTrustManifest } from "./vehicleDynamicsRegistry.ts";
import { canonicalJsonSha256 } from "./canonicalJsonSha256.ts";

const hash = /^[0-9a-f]{64}$/;
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const exactKeys = (value: unknown, keys: readonly string[]): value is Record<string, unknown> =>
  record(value)
  && Object.keys(value).length === keys.length
  && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
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
const positiveEvidenceStates = new Set([
  "measured", "calculated", "estimated_proxy", "observed_correlation",
  "controlled_test_effect",
]);
const p20ScientificFloatKeys = new Set([
  "empirical_noise_floor",
  "lap_pct",
  "lap_pct_end",
  "lap_pct_peak",
  "lap_pct_start",
  "new_value",
  "observed_delta",
  "previous_value",
  "session_time",
  "time_effect_s",
]);
const crewEvidenceIndexFloatKeys = new Set([
  "brake_delta_pct",
  "braking_fraction",
  "combined_acceleration_fraction",
  "cornering_fraction",
  "cumulative_delta_at_entry_s",
  "cumulative_delta_at_exit_s",
  "disturbance_exposure_fraction",
  "downstream_time_effect_s",
  "driver_demand_reference_coverage",
  "driver_demand_source_coverage",
  "elapsed_delta_s",
  "end_pct",
  "following_phase_effect_s",
  "following_phase_end_pct",
  "following_phase_start_pct",
  "following_straight_carry_lengths_pct",
  "full_throttle_fraction",
  "lap_pct_end",
  "lap_pct_start",
  "line_separation_m",
  "local_delta_s",
  "local_time_effect_s",
  "long_accel_delta",
  "median_corner_duration_s",
  "path_delta_m",
  "persistence_distance_pct",
  "platform_load_speed_bands_mph",
  "reference_traffic_exposure_fraction",
  "source_traffic_exposure_fraction",
  "speed_delta_mph",
  "speed_max_mph",
  "speed_min_mph",
  "start_pct",
  "steering_delta_deg",
  "throttle_delta_pct",
  "traffic_exposure_fraction",
  "yaw_rate_delta",
]);
const engineeringObjectives = new Set([
  "qualifying_peak", "race_long_run", "tire_conservation", "driver_confidence",
  "traffic_robustness", "superspeedway_stability", "fuel_strategy",
]);
const workspaceIdentityKeys = [
  "run_id", "session_id", "selected_scope_hash", "reasoning_snapshot_sha256",
  "p20_state_revision", "p20_projection_sha256", "p20_profile_hash", "p26_graph_version",
  "p26_knowledge_graph_sha256", "p26_reasoning_snapshot_sha256",
  "p32_projection_sha256", "p35_assessment_sha256", "run_sentinel_sha256",
  "learning_history_revision", "learning_ledger_head_sha256",
  "learning_projection_sha256",
  "setup_id", "setup_snapshot_sha256", "vehicle_runtime_identity_hash",
  "vehicle_runtime_identity",
  "active_workflow_id", "active_workflow_revision", "objective_id",
  "investigation_id", "workspace_revision",
] as const;
const vehicleRuntimeIdentityKeys = [
  "run_id", "car_path", "car_version", "iracing_build_version",
  "track_configuration_name", "source_file_sha256", "telemetry_cache_sha256",
  "schema_fingerprint", "compatibility_fingerprint", "available_telemetry_channels",
  "source",
] as const;
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
const vehicleDynamicsToolIds = [
  "inspect_tire_demand",
  "inspect_load_transfer",
  "inspect_roll_response",
  "inspect_pitch_response",
  "inspect_platform_state",
  "inspect_transient_settling",
  "inspect_steady_state_balance",
  "inspect_brake_vehicle_response",
  "inspect_power_on_response",
  "inspect_differential_response",
  "inspect_alignment_response",
  "inspect_tire_state_migration",
  "inspect_traffic_platform_response",
  "inspect_gear_acceleration_response",
] as const;
const vehicleDynamicsProducers = new Map(
  vehicleDynamicsToolIds.map((toolId) => [
    `p35.${toolId.replace(/^inspect_/, "")}`,
    toolId,
  ]),
);
const crewMechanisms = new Set([
  "driver_execution", "braking_response", "corner_rotation", "tire_state",
  "damper_response", "platform_response", "resistance_scrub_like",
  "powertrain_response", "stint_trend", "sim_integrity",
]);
const toolDefinitionKeys = [
  "tool_id", "allowed_scope", "input_schema", "output_artifact_type",
  "authority_ceiling", "required_sources",
] as const;
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

type P35ChainTruth = {
  stage: VehicleDynamicsChainStageKind;
  evidence_state: string;
  source_artifact_ids: string[];
  source_channels: string[];
  blocker_reasons: string[];
};

const unavailableP35Stage = (
  stage: VehicleDynamicsChainStageKind,
  reason: string,
  options: { blocked?: boolean; artifactIds?: string[]; channels?: string[] } = {},
): P35ChainTruth => ({
  stage,
  evidence_state: options.blocked ? "blocked_by_context" : "unavailable",
  source_artifact_ids: options.artifactIds ?? [],
  source_channels: options.channels ?? [],
  blocker_reasons: [reason],
});

const chainPhaseStates = (chain: CornerPerformanceChain): PerformancePhaseState[] => [
  chain.approach_state,
  chain.braking_state,
  chain.entry_state,
  chain.center_state,
  chain.exit_state,
  chain.carry_state,
].filter((state): state is PerformancePhaseState => state !== null);

function matchingP35Chain(
  projection: PerformanceIntelligenceProjection,
  opportunity: LapTimeOpportunity | null,
): { chain: CornerPerformanceChain | null; phaseState: PerformancePhaseState | null } {
  if (opportunity === null || opportunity.source_laps.length < 2) {
    return { chain: null, phaseState: null };
  }
  const sourceLaps = opportunity.source_laps.slice(0, 1);
  const referenceLaps = opportunity.source_laps.slice(1);
  const ranked = projection.corner_chains.filter((chain) => (
    chain.track_region === opportunity.track_region
    && chain.turn === opportunity.turn
    && sameJson(chain.lap_numbers, sourceLaps)
    && sameJson(chain.reference_lap_numbers, referenceLaps)
  )).sort((left, right) => {
    const leftMissing = !chainPhaseStates(left).some((state) => state.phase === opportunity.phase);
    const rightMissing = !chainPhaseStates(right).some((state) => state.phase === opportunity.phase);
    if (leftMissing !== rightMissing) return leftMissing ? 1 : -1;
    return left.chain_id < right.chain_id ? -1 : left.chain_id > right.chain_id ? 1 : 0;
  });
  const chain = ranked[0] ?? null;
  const phaseState = chain === null ? null : chainPhaseStates(chain).find((state) => (
    state.phase === opportunity.phase
    && state.start_pct === opportunity.start_pct
    && state.end_pct === opportunity.end_pct
  )) ?? null;
  return { chain, phaseState };
}

function p35ContextBlockers(
  projection: PerformanceIntelligenceProjection,
  opportunity: LapTimeOpportunity | null,
): string[] {
  if (opportunity === null) return [];
  const fractions = [
    opportunity.source_traffic_exposure_fraction,
    opportunity.reference_traffic_exposure_fraction,
  ];
  const trafficUnknown = fractions.some((value) => value === null);
  const trafficExposed = fractions.some((value) => value !== null && value > 0);
  const locallyQualified = ["qualified", "qualified_pair"].includes(opportunity.context_state)
    && opportunity.attribution_state === "candidate_only";
  return [...new Set([
    ...projection.basis.context_blockers,
    ...(trafficUnknown
      ? ["Traffic exposure context is unavailable for one or both sides of the selected P32 comparison."]
      : []),
    ...(trafficExposed ? ["Nonzero typed traffic exposure blocks P35 mechanism attribution."] : []),
    ...(!locallyQualified
      ? [`P32 attribution is blocked by the current typed comparison context (${opportunity.attribution_state}).`]
      : []),
    ...(!locallyQualified ? opportunity.contradictions : []),
  ])];
}

export function deriveP35ChainTruth(
  projection: PerformanceIntelligenceProjection,
  entries: readonly CrewChiefEvidenceEntry[],
  binding: CanonicalP35P32Binding,
): { expectedChain: P35ChainTruth[]; supportAdmissionAvailable: boolean } {
  const opportunity = projection.opportunity_map.opportunities.find(
    (item) => item.opportunity_id === binding.performanceOpportunityIds[0],
  ) ?? null;
  const { chain, phaseState } = matchingP35Chain(projection, opportunity);
  const driverValues = [
    phaseState?.throttle_delta_pct,
    phaseState?.brake_delta_pct,
    phaseState?.steering_delta_deg,
  ];
  const driverAvailable = chain !== null
    && phaseState !== null
    && driverValues.some((value) => value !== null && value !== undefined)
    && phaseState.source_channels.length > 0
    && chain.lap_numbers.length > 0;
  const driverStage: P35ChainTruth = driverAvailable ? {
    stage: "driver_input", evidence_state: "measured",
    source_artifact_ids: [chain!.chain_id], source_channels: [...phaseState!.source_channels],
    blocker_reasons: [],
  } : unavailableP35Stage(
    "driver_input",
    "Driver-input demand is unresolved in the typed P32 phase evidence.",
  );

  const demand = projection.track_demand;
  const demandAvailable = [
    demand.braking_fraction,
    demand.cornering_fraction,
    demand.combined_acceleration_fraction,
    demand.speed_min_mph,
    demand.speed_max_mph,
    demand.median_corner_duration_s,
  ].some((value) => value !== null) && demand.source_channels.length > 0;
  const trackDemandEntry = entries.find((entry) => entry.producer_id === "p32.track_demand");
  const trackDemandArtifactIds = trackDemandEntry ? [trackDemandEntry.artifact_id] : [];
  const demandStage: P35ChainTruth = demandAvailable && trackDemandArtifactIds.length === 1 ? {
    stage: "vehicle_demand", evidence_state: "estimated_proxy",
    source_artifact_ids: trackDemandArtifactIds, source_channels: [...demand.source_channels],
    blocker_reasons: [],
  } : unavailableP35Stage(
    "vehicle_demand",
    "Run-specific vehicle demand is unavailable from the typed P32 track profile.",
  );

  const responseValues = [
    phaseState?.yaw_rate_delta,
    phaseState?.long_accel_delta,
    phaseState?.speed_delta_mph,
    phaseState?.line_separation_m,
  ];
  const responseAvailable = chain !== null
    && phaseState !== null
    && responseValues.some((value) => value !== null && value !== undefined)
    && phaseState.source_channels.length > 0
    && chain.lap_numbers.length > 0;
  const responseStage: P35ChainTruth = responseAvailable ? {
    stage: "vehicle_response", evidence_state: "measured",
    source_artifact_ids: [chain!.chain_id], source_channels: [...phaseState!.source_channels],
    blocker_reasons: [],
  } : unavailableP35Stage(
    "vehicle_response",
    "Yaw, acceleration, speed, and line response are unresolved in typed P32 evidence.",
  );

  const contextBlockers = p35ContextBlockers(projection, opportunity);
  const proxyAvailable = demand.source_channels.length > 0 && (
    demand.combined_acceleration_fraction !== null
    || demand.platform_load_speed_bands_mph.length > 0
    || demand.disturbance_exposure_fraction !== null
    || demand.tire_state_development === "observable"
  );
  let tireStage: P35ChainTruth;
  if (binding.trafficBlocked) {
    tireStage = unavailableP35Stage(
      "tire_platform_state",
      "Traffic exposure blocks clean tire/platform and aero-proxy attribution.",
      { blocked: true, artifactIds: trackDemandArtifactIds, channels: [...demand.source_channels] },
    );
  } else if (contextBlockers.length > 0) {
    tireStage = unavailableP35Stage(
      "tire_platform_state",
      contextBlockers[0],
      { blocked: true, artifactIds: trackDemandArtifactIds, channels: [...demand.source_channels] },
    );
  } else if (proxyAvailable && trackDemandArtifactIds.length === 1) {
    tireStage = {
      stage: "tire_platform_state", evidence_state: "estimated_proxy",
      source_artifact_ids: trackDemandArtifactIds, source_channels: [...demand.source_channels],
      blocker_reasons: [],
    };
  } else {
    tireStage = unavailableP35Stage(
      "tire_platform_state",
      "Typed tire/platform proxies are unavailable; exact tire force and platform loads stay locked.",
    );
  }

  const timeStage: P35ChainTruth = opportunity !== null
    && opportunity.local_delta_s !== null
    && opportunity.source_channels.length > 0
    && opportunity.source_laps.length > 0 ? {
      stage: "time_consequence", evidence_state: "measured",
      source_artifact_ids: [opportunity.opportunity_id],
      source_channels: [...opportunity.source_channels], blocker_reasons: [],
    } : unavailableP35Stage(
      "time_consequence",
      "No measured P32 elapsed-time consequence is available for a qualified physical scope.",
    );
  const separationMatched = chain !== null && opportunity !== null
    && chain.driver_vehicle_separation.some((item) => (
      item.phase === opportunity.phase
      && item.result === "vehicle_response_changed_with_matched_inputs"
      && item.driver_demand_changed === false
      && item.vehicle_response_changed === true
      && item.line_changed === false
      && item.context_changed === false
      && item.time_changed === true
      && item.blockers.length === 0
    ));
  return {
    expectedChain: [driverStage, demandStage, responseStage, tireStage, timeStage],
    supportAdmissionAvailable: driverAvailable
      && responseAvailable
      && separationMatched
      && contextBlockers.length === 0,
  };
}
const mappedMechanisms = (values: string[]): string[] => [
  ...new Set(values.map((item) => crewMechanisms.has(item) ? item : "unclassified")),
];

export async function hasCanonicalMeasurementMissionDigest(
  value: unknown,
): Promise<boolean> {
  if (value === null) return true;
  if (!record(value) || !record(value.resource_snapshot)
    || typeof value.contract_sha256 !== "string"
    || typeof value.contract_id !== "string") return false;
  const payload: Record<string, unknown> = { ...value };
  delete payload.contract_id;
  delete payload.contract_sha256;
  delete payload.created_at;
  const resourceSnapshot = { ...value.resource_snapshot };
  delete resourceSnapshot.captured_at;
  payload.resource_snapshot = resourceSnapshot;
  try {
    const digest = await canonicalEngineeringLearningSha256(payload);
    return value.contract_sha256 === digest
      && value.contract_id === `mission:${digest.slice(0, 20)}`;
  } catch {
    return false;
  }
}

export async function hasCanonicalRunSentinelDigest(
  value: unknown,
  expectedSha256: unknown,
): Promise<boolean> {
  if (!record(value) || typeof expectedSha256 !== "string" || !hash.test(expectedSha256)) {
    return false;
  }
  try {
    return await canonicalEngineeringLearningSha256(value) === expectedSha256;
  } catch {
    return false;
  }
}

export async function hasCanonicalVehicleRuntimeIdentityDigest(
  workspace: CrewChiefWorkspace,
): Promise<boolean> {
  const runtime = workspace.identity.vehicle_runtime_identity;
  if (runtime === null) {
    return workspace.vehicle_dynamics.car_path === "unavailable"
      && workspace.vehicle_dynamics.car_version === "unavailable"
      && workspace.vehicle_dynamics.iracing_build_version === "unavailable"
      && workspace.vehicle_dynamics.track_package === "unavailable"
      && workspace.vehicle_dynamics.candidates.length === 0
      && workspace.vehicle_dynamics.focus_artifacts.length === 0;
  }
  try {
    const digest = await canonicalJsonSha256(runtime);
    return digest === workspace.identity.vehicle_runtime_identity_hash
      && digest === workspace.vehicle_dynamics.vehicle_runtime_identity_sha256;
  } catch {
    return false;
  }
}

export async function hasCanonicalEngineeringAwarenessDigest(
  workspace: CrewChiefWorkspace,
): Promise<boolean> {
  const expected = workspace.identity.p20_projection_sha256;
  if (typeof expected !== "string" || !hash.test(expected)) return false;
  try {
    return await canonicalEngineeringAwarenessScientificSha256(
      workspace.engineering_awareness,
    ) === expected;
  } catch {
    return false;
  }
}

export async function canonicalEngineeringAwarenessScientificSha256(
  awareness: EngineeringAwarenessProjection,
): Promise<string> {
  const scientificBody: Record<string, unknown> = {
    ...awareness,
  };
  delete scientificBody.generated_at;
  delete scientificBody.cache_state;
  delete scientificBody.build_duration_ms;
  return canonicalJsonSha256(scientificBody, {
    pythonFloatKeys: p20ScientificFloatKeys,
  });
}

export async function canonicalCrewEvidenceIndexSha256(
  entries: readonly CrewChiefEvidenceEntry[],
): Promise<string> {
  return canonicalJsonSha256(entries, {
    pythonFloatKeys: crewEvidenceIndexFloatKeys,
  });
}

export async function hasCanonicalCrewEvidenceIndexDigest(
  workspace: CrewChiefWorkspace,
): Promise<boolean> {
  try {
    return await canonicalCrewEvidenceIndexSha256(workspace.evidence_index.entries)
      === workspace.evidence_index.index_hash;
  } catch {
    return false;
  }
}

function validWorkspaceIdentityShape(value: unknown): value is Record<string, unknown> {
  if (!exactKeys(value, workspaceIdentityKeys)) return false;
  return typeof value.run_id === "string" && value.run_id.length > 0
    && typeof value.session_id === "string" && value.session_id.length > 0
    && typeof value.selected_scope_hash === "string" && hash.test(value.selected_scope_hash)
    && typeof value.reasoning_snapshot_sha256 === "string" && hash.test(value.reasoning_snapshot_sha256)
    && typeof value.p20_state_revision === "string" && hash.test(value.p20_state_revision)
    && typeof value.p20_projection_sha256 === "string" && hash.test(value.p20_projection_sha256)
    && (value.p20_profile_hash === null
      || (typeof value.p20_profile_hash === "string" && hash.test(value.p20_profile_hash)))
    && typeof value.p26_graph_version === "string" && value.p26_graph_version.length > 0
    && typeof value.p26_knowledge_graph_sha256 === "string" && hash.test(value.p26_knowledge_graph_sha256)
    && typeof value.p26_reasoning_snapshot_sha256 === "string" && hash.test(value.p26_reasoning_snapshot_sha256)
    && typeof value.p32_projection_sha256 === "string" && hash.test(value.p32_projection_sha256)
    && typeof value.p35_assessment_sha256 === "string" && hash.test(value.p35_assessment_sha256)
    && typeof value.run_sentinel_sha256 === "string" && hash.test(value.run_sentinel_sha256)
    && typeof value.learning_history_revision === "string" && hash.test(value.learning_history_revision)
    && (value.learning_ledger_head_sha256 === null
      || (typeof value.learning_ledger_head_sha256 === "string"
        && hash.test(value.learning_ledger_head_sha256)))
    && typeof value.learning_projection_sha256 === "string" && hash.test(value.learning_projection_sha256)
    && typeof value.setup_id === "string" && value.setup_id.length > 0
    && typeof value.setup_snapshot_sha256 === "string" && hash.test(value.setup_snapshot_sha256)
    && typeof value.vehicle_runtime_identity_hash === "string" && hash.test(value.vehicle_runtime_identity_hash)
    && (value.vehicle_runtime_identity === null || (
      exactKeys(value.vehicle_runtime_identity, vehicleRuntimeIdentityKeys)
      && safeText(value.vehicle_runtime_identity.run_id)
      && safeText(value.vehicle_runtime_identity.car_path)
      && safeText(value.vehicle_runtime_identity.car_version)
      && safeText(value.vehicle_runtime_identity.iracing_build_version)
      && safeText(value.vehicle_runtime_identity.track_configuration_name)
      && typeof value.vehicle_runtime_identity.source_file_sha256 === "string"
      && hash.test(value.vehicle_runtime_identity.source_file_sha256)
      && typeof value.vehicle_runtime_identity.telemetry_cache_sha256 === "string"
      && hash.test(value.vehicle_runtime_identity.telemetry_cache_sha256)
      && typeof value.vehicle_runtime_identity.schema_fingerprint === "string"
      && hash.test(value.vehicle_runtime_identity.schema_fingerprint)
      && typeof value.vehicle_runtime_identity.compatibility_fingerprint === "string"
      && hash.test(value.vehicle_runtime_identity.compatibility_fingerprint)
      && uniqueStrings(value.vehicle_runtime_identity.available_telemetry_channels)
      && value.vehicle_runtime_identity.source === "verified_telemetry_artifact"
    ))
    && nullableString(value.active_workflow_id)
    && nullableString(value.active_workflow_revision)
    && ((value.active_workflow_id === null) === (value.active_workflow_revision === null))
    && typeof value.objective_id === "string" && engineeringObjectives.has(value.objective_id)
    && nullableString(value.investigation_id)
    && typeof value.workspace_revision === "string" && hash.test(value.workspace_revision);
}

function validInvestigation(value: unknown): value is Record<string, unknown> {
  if (!exactKeys(value, [
    "investigation_id", "workspace_identity", "origin", "objective",
    "raw_driver_report", "canonical_problem", "opening_reasoning", "opening_problem",
    "opened_at", "status",
  ]) || !validWorkspaceIdentityShape(value.workspace_identity)
    || !isP19ReasoningMemory(value.opening_reasoning)
    || !isProblemFingerprint(value.opening_problem)) return false;
  const openingIdentity = value.workspace_identity;
  const openingReasoning = value.opening_reasoning;
  const openingProblem = value.opening_problem;
  return typeof value.investigation_id === "string" && value.investigation_id.length > 0
    && ["post_import", "driver_report", "manual_review"].includes(String(value.origin))
    && typeof value.objective === "string" && engineeringObjectives.has(value.objective)
    && typeof value.raw_driver_report === "string" && value.raw_driver_report.length > 0
    && typeof value.canonical_problem === "string" && value.canonical_problem.length > 0
    && typeof value.opened_at === "string" && Number.isFinite(Date.parse(value.opened_at))
    && ["open", "complete", "stale", "abandoned"].includes(String(value.status))
    && value.objective === openingIdentity.objective_id
    && openingProblem.objective === value.objective
    && openingReasoning.reasoning_snapshot_sha256 === openingIdentity.reasoning_snapshot_sha256;
}

function validToolDefinition(value: unknown): value is Record<string, unknown> {
  if (!exactKeys(value, toolDefinitionKeys) || !safeText(value.tool_id)) return false;
  const toolId = String(value.tool_id);
  const dynamicsTool = vehicleDynamicsToolIds.includes(
    toolId as (typeof vehicleDynamicsToolIds)[number],
  );
  const expectedDynamicsOutput = `P35 ${toolId.replace(/^inspect_/, "").replace(/_/g, " ")} evidence`;
  return (dynamicsTool
    ? value.input_schema === "P35 typed mechanism assessment and existing P20/P26/P32 evidence"
      && value.output_artifact_type === expectedDynamicsOutput
    : safeText(value.input_schema) && safeText(value.output_artifact_type))
    && ["run", "session", "component", "workflow"].includes(String(value.allowed_scope))
    && ["observation_only", "context_only", "measurement_only"]
      .includes(String(value.authority_ceiling))
    && uniqueStrings(value.required_sources);
}

function validTypedArtifactEnvelope(value: Record<string, unknown>): boolean {
  const expectedType = performanceProducers.get(String(value.producer_id));
  const expectedDynamicsTool = vehicleDynamicsProducers.get(String(value.producer_id));
  const artifact = value.typed_artifact;
  if (expectedType === undefined && expectedDynamicsTool === undefined) return artifact === null;
  if (!record(artifact) || typeof artifact.artifact_type !== "string") return false;
  if (expectedDynamicsTool !== undefined) {
    return exactKeys(artifact, [
      "artifact_type", "inspection_tool_id", "assessment_sha256", "focus",
    ])
      && artifact.artifact_type === "vehicle_dynamics_focus"
      && artifact.inspection_tool_id === expectedDynamicsTool
      && typeof artifact.assessment_sha256 === "string"
      && hash.test(artifact.assessment_sha256)
      && record(artifact.focus);
  }
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
  if (entry.producer_id.startsWith("p35.")) {
    return entry.typed_artifact?.artifact_type === "vehicle_dynamics_focus";
  }
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
    || entry.control_keys.length !== 0) return false;
  if (artifact.artifact_type === "unavailable") {
    const expectedAuthority = artifact.claimed_artifact_type === "driver_vehicle_separation" || artifact.claimed_artifact_type === "objective_envelope"
      ? "context_only" : "observation_only";
    if (entry.authority_ceiling !== expectedAuthority) return false;
    if (entry.phase === "unavailable") {
      return sameJson(entry.lap_numbers, projection.basis.source_lap_numbers)
        && entry.lap_pct_start === 0
        && entry.lap_pct_end === 100
        && entry.source_channels.length === 0
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
        && sameJson(entry.lap_numbers, [...new Set([
          ...chain.lap_numbers, ...chain.reference_lap_numbers,
        ])])
        && entry.lap_pct_start === start
        && entry.lap_pct_end === end
        && sameJson(entry.source_channels, uniqueChannels(states as Array<Record<string, unknown> | null>));
    }
    if (artifact.claimed_artifact_type === "track_demand" && entry.phase === "whole_run") {
      return unavailableMatchesProjection("track_demand", projection)
        && /^p32-track-demand:[0-9a-f]{20}$/.test(entry.artifact_id)
        && sameJson(entry.lap_numbers, projection.basis.source_lap_numbers)
        && entry.lap_pct_start === 0
        && entry.lap_pct_end === 100
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
        && sameJson(entry.lap_numbers, canonical.source_laps)
        && entry.lap_pct_start === canonical.start_pct
        && entry.lap_pct_end === canonical.end_pct
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
        && sameJson(entry.lap_numbers, canonical.source_laps)
        && entry.lap_pct_start === canonical.following_phase_start_pct
        && entry.lap_pct_end === canonical.following_phase_end_pct
        && entry.phase === "following_straight_carry"
        && entry.evidence_state === (["qualified", "qualified_pair"].includes(canonical.context_state) ? "observed_correlation" : "blocked_by_context")
        && sameJson(entry.source_channels, canonical.source_channels)
        && sameJson(entry.mechanism_ids, mappedMechanisms(canonical.mechanism_candidates))
        && sameJson(entry.component_ids, canonical.component_candidates)
        && entry.authority_ceiling === "observation_only";
    }
    case "corner_performance_chain": {
      const canonical = chains.find((item) => item.chain_id === artifact.chain.chain_id);
      const canonicalStates = canonical ? [
        canonical.approach_state, canonical.braking_state, canonical.entry_state,
        canonical.center_state, canonical.exit_state, canonical.carry_state,
      ].filter((state) => state !== null) : [];
      const channels = canonical ? uniqueChannels([
        canonical.approach_state, canonical.braking_state, canonical.entry_state,
        canonical.center_state, canonical.exit_state, canonical.carry_state,
      ] as Array<Record<string, unknown> | null>) : [];
      const chainStart = canonicalStates.length
        ? Math.min(...canonicalStates.map((state) => state.start_pct)) : 0;
      const chainEnd = canonicalStates.length
        ? Math.max(...canonicalStates.map((state) => state.end_pct)) : 100;
      return canonical !== undefined
        && deepEqual(artifact.chain, canonical)
        && sameJson(entry.lap_numbers, [...new Set([
          ...canonical.lap_numbers, ...canonical.reference_lap_numbers,
        ])])
        && entry.lap_pct_start === chainStart
        && entry.lap_pct_end === chainEnd
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
        && sameJson(entry.lap_numbers, [...new Set([
          ...chain.lap_numbers, ...chain.reference_lap_numbers,
        ])])
        && entry.lap_pct_start === artifact.phase_state.start_pct
        && entry.lap_pct_end === artifact.phase_state.end_pct
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
      const present = chain ? [
        chain.approach_state, chain.braking_state, chain.entry_state,
        chain.center_state, chain.exit_state, chain.carry_state,
      ].filter((state) => state !== null) : [];
      const chainStart = present.length
        ? Math.min(...present.map((state) => state.start_pct)) : 0;
      const chainEnd = present.length
        ? Math.max(...present.map((state) => state.end_pct)) : 100;
      return chain !== undefined
        && artifact.track_region === chain.track_region
        && canonical !== undefined
        && deepEqual(artifact.separation, canonical)
        && sameJson(entry.lap_numbers, [...new Set([
          ...chain.lap_numbers, ...chain.reference_lap_numbers,
        ])])
        && entry.lap_pct_start === chainStart
        && entry.lap_pct_end === chainEnd
        && entry.phase === canonical.phase
        && entry.evidence_state === (["context_contaminated", "unresolved"].includes(canonical.result) ? "blocked_by_context" : "observed_correlation")
        && sameJson(entry.source_channels, channels)
        && entry.mechanism_ids.length === 0
        && entry.component_ids.length === 0
        && entry.authority_ceiling === "context_only";
    }
    case "track_demand":
      return deepEqual(artifact.profile, projection.track_demand)
        && sameJson(entry.lap_numbers, projection.basis.source_lap_numbers)
        && entry.lap_pct_start === 0
        && entry.lap_pct_end === 100
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
        && sameJson(entry.lap_numbers, projection.basis.source_lap_numbers)
        && entry.lap_pct_start === 0
        && entry.lap_pct_end === 100
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
        && sameJson(entry.lap_numbers, projection.basis.source_lap_numbers)
        && entry.lap_pct_start === 0
        && entry.lap_pct_end === 100
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

function p20EntryIsProjectionOwned(
  entry: CrewChiefEvidenceEntry,
  awareness: EngineeringAwarenessProjection,
): boolean {
  const matchedMechanisms = new Set<string>();
  const primary = awareness.primary_state;
  if (primary !== null
    && primary.source_artifact_ids.includes(entry.artifact_id)
    && sameJson(entry.lap_numbers, [primary.lap_number])
    && entry.lap_pct_start === primary.lap_pct_start
    && entry.lap_pct_end === primary.lap_pct_end
    && entry.phase === primary.phase
    && entry.evidence_state === primary.evidence_state
    && sameJson(entry.source_channels, primary.source_channels)) {
    matchedMechanisms.add(primary.mechanism);
  }
  for (const state of awareness.subsystem_states) {
    if (state.status === "ready"
      && state.blocker_reasons.length === 0
      && state.source_artifact_ids.includes(entry.artifact_id)
      && state.lap_number !== null
      && sameJson(entry.lap_numbers, [state.lap_number])
      && entry.lap_pct_start === state.lap_pct_start
      && entry.lap_pct_end === state.lap_pct_end
      && entry.phase === state.phase
      && entry.evidence_state === state.evidence_state
      && sameJson(entry.source_channels, state.source_channels)) {
      matchedMechanisms.add(state.mechanism);
    }
  }
  return entry.mechanism_ids.length > 0
    && entry.mechanism_ids.every((mechanismId) => matchedMechanisms.has(mechanismId));
}

export function p35FocusEntriesMatchAssessment(
  entries: readonly CrewChiefEvidenceEntry[],
  assessment: PerformanceMechanismAssessment,
  identity: Record<string, unknown>,
  report: RunIntelligenceReport,
  awareness: EngineeringAwarenessProjection,
): boolean {
  const dynamicsEntries = entries.filter((entry) => entry.producer_id.startsWith("p35."));
  if (dynamicsEntries.length !== assessment.focus_artifacts.length) return false;
  const dynamicsById = new Map(dynamicsEntries.map((entry) => [entry.artifact_id, entry]));
  if (dynamicsById.size !== dynamicsEntries.length) return false;
  const sourceEntries = entries.filter((entry) => !entry.producer_id.startsWith("p35."));
  const sourceById = new Map(sourceEntries.map((entry) => [entry.artifact_id, entry]));
  if (sourceById.size !== sourceEntries.length) return false;

  const supportIds = new Set(assessment.candidates.flatMap((item) => item.support_artifact_ids));
  const contradictionIds = new Set(
    assessment.candidates.flatMap((item) => item.contradiction_artifact_ids),
  );
  if ([...supportIds].some((artifactId) => contradictionIds.has(artifactId))) return false;

  for (const focus of assessment.focus_artifacts) {
    const entry = dynamicsById.get(focus.artifact_id);
    if (!entry) return false;
    const artifact = entry.typed_artifact;
    if (artifact?.artifact_type !== "vehicle_dynamics_focus") return false;
    const toolId = vehicleDynamicsProducers.get(entry.producer_id);
    const mechanismTrust = p35RuntimeTrustManifest.mechanisms.find(
      (item) => item.mechanism_id === focus.mechanism_id,
    );
    const toolSuffix = toolId?.replace(/^inspect_/, "");
    const expectedPolarity = supportIds.has(focus.artifact_id)
      ? "support"
      : contradictionIds.has(focus.artifact_id)
        ? "contradiction"
        : "neutral";
    if (!toolId
      || !mechanismTrust
      || artifact.inspection_tool_id !== toolId
      || focus.inspection_tool_id !== toolId
      || artifact.assessment_sha256 !== assessment.p35_assessment_sha256
      || !deepEqual(artifact.focus, focus)
      || toolSuffix === undefined
      || entry.producer_id !== `p35.${toolSuffix}`
      || !new RegExp(`^p35\\.focus\\.${toolSuffix}:[0-9a-f]{24}$`).test(focus.artifact_id)
      || entry.artifact_id !== focus.artifact_id
      || entry.run_id !== assessment.run_id
      || entry.session_id !== assessment.session_id
      || entry.setup_id !== identity.setup_id
      || entry.workspace_run_id !== assessment.run_id
      || entry.workspace_session_id !== assessment.session_id
      || entry.workspace_setup_id !== identity.setup_id
      || entry.source_run_id !== assessment.run_id
      || entry.source_session_id !== assessment.session_id
      || entry.source_setup_id !== identity.setup_id
      || entry.source_setup_sha256 !== identity.setup_snapshot_sha256
      || entry.source_build_context_sha256 !== identity.vehicle_runtime_identity_hash
      || entry.source_provenance_available !== true
      || entry.objective !== assessment.objective_id
      || entry.authority_ceiling !== "observation_only"
      || entry.component_ids.length !== 0
      || entry.control_keys.length !== 0
      || entry.evidence_state !== focus.evidence_state
      || !sameJson(entry.source_channels, focus.source_channels)
      || !sameJson(entry.blocker_reasons, focus.blocker_reasons)
      || !sameJson(entry.lap_numbers, focus.lap_numbers)
      || entry.lap_pct_start !== focus.lap_pct_start
      || entry.lap_pct_end !== focus.lap_pct_end
      || entry.phase !== focus.phase) return false;

    const sources = focus.source_artifact_ids.map((artifactId) => sourceById.get(artifactId));
    if (sources.some((source) => source === undefined)) return false;
    const resolved = sources as CrewChiefEvidenceEntry[];
    const sourceChannels = [...new Set(resolved.flatMap((source) => source.source_channels))];
    const sourceMechanisms = [...new Set(resolved.flatMap((source) => source.mechanism_ids))];
    const positiveFocus = positiveEvidenceStates.has(focus.evidence_state);
    const supportSource = resolved[0];
    const reportObservation = expectedPolarity === "support"
      ? report.mechanism_observations?.observations.find((observation) => (
        observation.artifact_id === supportSource?.artifact_id
      ))
      : undefined;
    if (!focus.source_channels.every((channel) => sourceChannels.includes(channel))
      || !sameJson(sourceMechanisms, entry.mechanism_ids)
      || (expectedPolarity === "support" && (
        resolved.length !== 1
        || resolved[0].producer_id !== "p20.mechanism_observation"
        || resolved[0].mechanism_ids.length === 0
        || !resolved[0].mechanism_ids.every((mechanismId) => (
          (mechanismTrust.p20_mechanism_ids as readonly string[]).includes(mechanismId)
        ))
        || !p20EntryIsProjectionOwned(resolved[0], awareness)
        || report.mechanism_observations?.status !== "ready"
        || reportObservation === undefined
        || reportObservation.qualified !== true
        || reportObservation.run_id !== assessment.run_id
        || reportObservation.setup_id !== identity.setup_id
        || !sameJson(reportObservation.source_run_ids, [assessment.run_id])
        || !sameJson(reportObservation.source_setup_ids, [identity.setup_id])
        || !sameJson(reportObservation.mechanism_kinds, resolved[0].mechanism_ids)
        || reportObservation.lap_number !== focus.lap_numbers[0]
        || focus.lap_numbers.length !== 1
        || reportObservation.phase !== focus.phase
        || reportObservation.lap_pct_start !== focus.lap_pct_start
        || reportObservation.lap_pct_end !== focus.lap_pct_end
        || !sameJson(reportObservation.source_channels, focus.source_channels)
        || reportObservation.evidence_state !== focus.evidence_state
        || reportObservation.blocker_reasons.length !== 0
      ))
      || (expectedPolarity !== "support" && (
        !sameJson(focus.source_artifact_ids, assessment.performance_opportunity_ids)
        || resolved.some((source) => source.producer_id !== "p32.lap_time_opportunity")
      ))
      || (positiveFocus && resolved.some((source) => (
        source.blocker_reasons.length > 0 || !positiveEvidenceStates.has(source.evidence_state)
      )))
      || !resolved.every((source) => (
        source.run_id === assessment.run_id
        && source.session_id === assessment.session_id
        && source.setup_id === identity.setup_id
        && source.source_run_id === assessment.run_id
        && source.source_session_id === assessment.session_id
        && source.source_setup_id === identity.setup_id
        && source.source_setup_sha256 === identity.setup_snapshot_sha256
        && source.source_build_context_sha256 === identity.vehicle_runtime_identity_hash
        && source.source_provenance_available === true
        && sameJson(source.lap_numbers, focus.lap_numbers)
        && source.lap_pct_start === focus.lap_pct_start
        && source.lap_pct_end === focus.lap_pct_end
        && source.phase === focus.phase
      ))) return false;

    if (entry.polarity !== expectedPolarity) return false;
  }

  if (assessment.strongest_support_artifact_id !== null
    && dynamicsById.get(assessment.strongest_support_artifact_id)?.polarity !== "support") return false;
  if (assessment.strongest_contradiction_artifact_id !== null
    && dynamicsById.get(assessment.strongest_contradiction_artifact_id)?.polarity
      !== "contradiction") return false;
  if (assessment.next_discriminator_contract_id !== null) {
    const focus = assessment.focus_artifacts.find((item) => (
      item.observation_contract_id === assessment.next_discriminator_contract_id
    ));
    if (!focus || dynamicsById.get(focus.artifact_id)?.polarity !== "neutral") return false;
  }
  return true;
}

export function validEvidenceEntry(
  value: unknown,
  runId: string,
  sessionId: string,
  scopeRunIds: ReadonlySet<string>,
  objectiveId: string,
): boolean {
  if (!exactKeys(value, [
    "artifact_id", "producer_id", "run_id", "session_id", "setup_id",
    "workspace_run_id", "workspace_session_id", "workspace_setup_id",
    "source_run_id", "source_session_id", "source_setup_id", "source_setup_sha256",
    "source_build_context_sha256", "source_provenance_available", "lap_numbers",
    "lap_pct_start", "lap_pct_end", "phase", "mechanism_ids", "component_ids",
    "control_keys", "objective", "source_channels", "evidence_state", "polarity",
    "blocker_reasons", "typed_artifact", "authority_ceiling",
  ])) return false;
  const p33Producer = typeof value.producer_id === "string" && value.producer_id.startsWith("p33.");
  const learningEvidence = value.producer_id === "p33.engineering_experience";
  if (p33Producer && !learningEvidence) return false;
  const lapNumbers = value.lap_numbers;
  const start = value.lap_pct_start;
  const end = value.lap_pct_end;
  return typeof value.artifact_id === "string" && value.artifact_id.length > 0
    && typeof value.producer_id === "string" && value.producer_id.length > 0
    && typeof value.run_id === "string" && (learningEvidence || scopeRunIds.has(value.run_id))
    && value.run_id === value.source_run_id
    && (learningEvidence ? value.session_id === value.source_session_id : value.session_id === sessionId)
    && value.workspace_session_id === sessionId
    && value.workspace_run_id === runId
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
    && (!learningEvidence || value.source_provenance_available === true)
    && (!learningEvidence || (
      /^p33ref_[0-9a-f]{24}$/.test(String(value.artifact_id))
      && value.mechanism_ids.length === 0
      && value.component_ids.length === 0
      && value.control_keys.length === 0
      && value.blocker_reasons.length === 0
    ))
    && new Set(value.blocker_reasons).size === value.blocker_reasons.length
    && validTypedArtifactEnvelope(value)
    && (learningEvidence
      ? value.authority_ceiling === "attention_only"
      : ["observation_only", "context_only", "measurement_only", "p19_projection_only"]
        .includes(String(value.authority_ceiling)));
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
  if (!record(value) || value.schema_version !== "p35.crew-chief-workspace.v1") return false;
  if (
    !record(value.identity)
    || !record(value.terminal_decision)
    || !record(value.evidence_index)
    || !record(value.run_sentinel)
    || !record(value.critique)
    || !record(value.adaptive_research)
    || !record(value.learning_prior)
    || !record(value.investigation_improvement)
    || !record(value.engineering_awareness)
    || !record(value.vehicle_dynamics)
  ) return false;
  const missionContract = value.p19_mission_contract;
  const reportAction = scope.report.briefing.action;
  const reportHasMissionContract = (
    typeof reportAction.mission_contract_id === "string"
    && reportAction.mission_contract_id.length > 0
    && typeof reportAction.mission_contract_sha256 === "string"
    && hash.test(reportAction.mission_contract_sha256)
  );
  const reportHasNoMissionContract = (
    reportAction.mission_contract_id == null
    && reportAction.mission_contract_sha256 == null
  );
  if (
    (!reportHasMissionContract && !reportHasNoMissionContract)
    || (missionContract === null) !== reportHasNoMissionContract
    || (missionContract !== null && !(
      record(missionContract)
    && missionContract.schema_version === "p19.measurement-mission.v2"
    && typeof missionContract.contract_id === "string"
    && missionContract.contract_id === reportAction.mission_contract_id
    && typeof missionContract.contract_sha256 === "string"
    && hash.test(missionContract.contract_sha256)
    && missionContract.contract_sha256 === reportAction.mission_contract_sha256
    && missionContract.run_id === scope.runId
    && missionContract.session_id === scope.sessionId
    && missionContract.source_setup_id === scope.report.setup_id
    && typeof missionContract.setup_sha256 === "string"
    && hash.test(missionContract.setup_sha256)
    && integerNumber(missionContract.required_laps)
    && missionContract.required_laps >= 1
    && safeTexts(missionContract.acceptance_thresholds)
    && safeTexts(missionContract.integrity_stop_rules)
    && safeText(missionContract.purpose)
    ))
  ) return false;
  const identity = value.identity;
  const decision = value.terminal_decision;
  const scopeRunIds = new Set(scope.scopeRunIds ?? [scope.runId]);
  if (
    !validWorkspaceIdentityShape(identity)
    || scopeRunIds.size === 0
    || !scopeRunIds.has(scope.runId)
    || identity.run_id !== scope.runId
    || identity.session_id !== scope.sessionId
    || identity.objective_id !== scope.objectiveId
    || identity.reasoning_snapshot_sha256 !== scope.report.reasoning_snapshot_sha256
    || identity.setup_id !== scope.report.setup_id
    || identity.setup_snapshot_sha256 !== scope.report.setup_snapshot_sha256
    || typeof value.generated_at !== "string"
    || !Number.isFinite(Date.parse(value.generated_at))
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
    || typeof identity.p35_assessment_sha256 !== "string"
    || !hash.test(identity.p35_assessment_sha256)
    || typeof identity.learning_history_revision !== "string"
    || !hash.test(identity.learning_history_revision)
    || !(identity.learning_ledger_head_sha256 === null
      || (typeof identity.learning_ledger_head_sha256 === "string"
        && hash.test(identity.learning_ledger_head_sha256)))
    || typeof identity.learning_projection_sha256 !== "string"
    || !hash.test(identity.learning_projection_sha256)
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
      validEvidenceEntry(entry, scope.runId, scope.sessionId, scopeRunIds, scope.objectiveId)
    ))
    || new Set(value.evidence_index.entries.map((entry) => entry.artifact_id)).size
      !== value.evidence_index.entries.length
    || !Array.isArray(value.available_tools)
    || !value.available_tools.every(validToolDefinition)
    || new Set(value.available_tools.map((tool) => tool.tool_id)).size !== value.available_tools.length
    || !vehicleDynamicsToolIds.every((toolId) => (
      value.available_tools as Array<Record<string, unknown>>
    ).some((tool) => (
      tool.tool_id === toolId
      && tool.allowed_scope === "run"
      && tool.authority_ceiling === "observation_only"
      && sameJson(tool.required_sources, ["p35", "p20", "p32"])
    )))
    || !uniqueStrings(value.p19_cause_ids)
    || !uniqueStrings(value.p19_contradiction_artifact_ids)
  ) return false;
  if (!isEngineeringAwarenessProjection(value.engineering_awareness, {
    runId: scope.runId,
    sessionId: scope.sessionId,
  })
    || value.engineering_awareness.reasoning_snapshot_id
      !== identity.reasoning_snapshot_sha256
    || value.engineering_awareness.request_identity.reasoning_snapshot_id
      !== identity.reasoning_snapshot_sha256
    || value.engineering_awareness.state_revision !== identity.p20_state_revision
    || value.engineering_awareness.request_identity.state_revision
      !== identity.p20_state_revision
    || value.engineering_awareness.profile_hash !== identity.p20_profile_hash
    || value.engineering_awareness.authority !== "observation_only"
    || value.engineering_awareness.raw_trace_included !== false
    || !Number.isFinite(Date.parse(value.engineering_awareness.generated_at))
    || !["cold", "warm"].includes(value.engineering_awareness.cache_state)) return false;
  const trustedAwareness = value.engineering_awareness as EngineeringAwarenessProjection;
  const trustedEntries = value.evidence_index.entries as CrewChiefEvidenceEntry[];
  if (!(value.p19_contradiction_artifact_ids as string[]).every((artifactId) => (
    trustedEntries.some((entry) => entry.artifact_id === artifactId && entry.polarity === "contradiction")
  ))) return false;
  if (!isCrewChiefLearningPrior(value.learning_prior, {
    runId: scope.runId,
    sessionId: scope.sessionId,
    objectiveId: scope.objectiveId,
    selectedScopeHash: String(identity.selected_scope_hash),
    p19Hash: String(identity.reasoning_snapshot_sha256),
    p32Hash: String(identity.p32_projection_sha256),
    historyRevision: String(identity.learning_history_revision),
    projectionHash: String(identity.learning_projection_sha256),
  })) return false;
  const trustedLearning = value.learning_prior;
  const learningEntries = trustedEntries.filter((entry) => entry.producer_id === "p33.engineering_experience");
  const availableReferences = trustedLearning.evidence_references.filter((item) => item.state === "available");
  const learningEntryById = new Map(learningEntries.map((entry) => [entry.artifact_id, entry]));
  if (learningEntries.length !== availableReferences.length
    || availableReferences.some((reference) => {
      const entry = learningEntryById.get(reference.reference_id);
      const source = reference.provenance;
      return !entry
        || entry.run_id !== source.run_id
        || entry.session_id !== source.session_id
        || entry.setup_id !== source.setup_id
        || entry.workspace_run_id !== scope.runId
        || entry.workspace_session_id !== scope.sessionId
        || entry.workspace_setup_id !== identity.setup_id
        || entry.source_run_id !== source.run_id
        || entry.source_session_id !== source.session_id
        || entry.source_setup_id !== source.setup_id
        || entry.source_setup_sha256 !== source.setup_snapshot_sha256
        || entry.source_build_context_sha256 !== source.build_context_sha256
        || !sameJson(entry.lap_numbers, source.lap_numbers)
        || entry.lap_pct_start !== source.lap_pct_start
        || entry.lap_pct_end !== source.lap_pct_end
        || entry.phase !== source.phase
        || !sameJson(entry.source_channels, source.source_channels)
        || entry.evidence_state !== source.evidence_state
        || entry.polarity !== source.polarity
        || entry.authority_ceiling !== "attention_only"
        || entry.typed_artifact !== null;
    })) return false;
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
  const dynamicsP32Binding = deriveCanonicalP35P32Binding(
    trustedProjection.opportunity_map.opportunities,
    trustedProjection.basis.context_blockers,
  );
  const dynamicsChainTruth = deriveP35ChainTruth(
    trustedProjection,
    trustedEntries,
    dynamicsP32Binding,
  );
  const producerRuntime = identity.vehicle_runtime_identity as Record<string, unknown> | null;
  const reportRuntime = scope.report.vehicle_systems?.runtime_identity ?? null;
  if ((producerRuntime === null) !== (reportRuntime === null)
    || (producerRuntime !== null && (
      !deepEqual(producerRuntime, reportRuntime)
      || scope.report.vehicle_systems?.graph_version !== identity.p26_graph_version
      || scope.report.vehicle_systems.knowledge_graph_sha256
        !== identity.p26_knowledge_graph_sha256
      || producerRuntime.run_id !== scope.runId
    ))) return false;
  const expectedCarPath = producerRuntime === null ? "unavailable" : String(producerRuntime.car_path);
  const expectedCarVersion = producerRuntime === null
    ? "unavailable" : String(producerRuntime.car_version);
  const expectedBuild = producerRuntime === null
    ? "unavailable" : String(producerRuntime.iracing_build_version);
  const expectedTrackPackage = producerRuntime !== null
    && String(producerRuntime.track_configuration_name).toLowerCase() === "oval"
    ? "oval" : "unavailable";
  if (!isPerformanceMechanismAssessment(value.vehicle_dynamics, {
    runId: scope.runId,
    sessionId: scope.sessionId,
    objectiveId: scope.objectiveId,
    assessmentSha256: String(identity.p35_assessment_sha256),
    carPath: expectedCarPath,
    carVersion: expectedCarVersion,
    iRacingBuildVersion: expectedBuild,
    trackPackage: expectedTrackPackage,
    vehicleRuntimeIdentitySha256: String(identity.vehicle_runtime_identity_hash),
    p19ReasoningSnapshotSha256: String(identity.reasoning_snapshot_sha256),
    p20StateRevision: String(identity.p20_state_revision),
    p20ProfileHash: identity.p20_profile_hash as string | null,
    p26GraphVersion: String(identity.p26_graph_version),
    p26KnowledgeGraphSha256: String(identity.p26_knowledge_graph_sha256),
    p32ProjectionSha256: String(identity.p32_projection_sha256),
    ...dynamicsP32Binding,
    ...dynamicsChainTruth,
    evidenceArtifactIds: trustedEntries
      .filter((entry) => !entry.producer_id.startsWith("p35."))
      .map((entry) => entry.artifact_id),
  })) return false;
  const trustedDynamics = value.vehicle_dynamics;
  if (producerRuntime === null && (
    trustedDynamics.candidates.length > 0
    || trustedDynamics.focus_artifacts.length > 0
  )) return false;
  if (!p35FocusEntriesMatchAssessment(
    trustedEntries,
    trustedDynamics,
    identity,
    scope.report,
    trustedAwareness,
  )) return false;
  if (
    typeof decision.kind !== "string"
    || typeof decision.title !== "string"
    || typeof decision.instruction !== "string"
    || !strings(decision.source_event_ids)
    || !safeTexts(decision.blocker_reasons)
  ) return false;
  const success = value.success_contract;
  const sentinel = value.run_sentinel;
  const p19Action = scope.report.briefing.action;
  const sentinelPlanMatchesP19 = (
    (p19Action.kind === "controlled_test" && sentinel.p19_plan_kind === "controlled_test")
    || (p19Action.kind === "measurement_mission"
      && ["measurement_mission", "discriminator"].includes(String(sentinel.p19_plan_kind)))
    || (p19Action.kind === "driver_focus"
      && ["measurement_mission", "discriminator"].includes(String(sentinel.p19_plan_kind)))
    || (p19Action.kind === "no_call"
      && ["blocked", "stop_testing"].includes(String(sentinel.p19_plan_kind)))
  );
  if (!exactKeys(sentinel, [
    "mission_state", "p19_plan_kind", "mission", "need", "hold_constant",
    "watch", "success", "stop", "required_laps", "context_cleared_laps",
    "mission_accepted_lap_ids", "measurement_attempt_ids",
    "mission_acceptance_basis", "collection_complete", "stage", "laps",
    "blocker_reasons",
  ])) return false;
  if (["blocked", "stop_testing"].includes(String(sentinel.p19_plan_kind))
    && (success !== null || sentinel.required_laps !== null || sentinel.collection_complete)) return false;
  const critique = value.critique;
  let contextOrdinal = 0;
  const sentinelLapsAreCanonical = Array.isArray(sentinel.laps)
    && sentinel.laps.every((lap) => {
      if (!exactKeys(lap, ["lap_id", "lap_number", "status", "reasons", "context_ordinal"])
        || !safeText(lap.lap_id)
        || !integerNumber(lap.lap_number)
        || !["context_cleared", "rejected"].includes(String(lap.status))
        || !safeTexts(lap.reasons)) return false;
      if (lap.status === "context_cleared") {
        contextOrdinal += 1;
        return lap.reasons.length === 0 && lap.context_ordinal === contextOrdinal;
      }
      return lap.reasons.length > 0 && lap.context_ordinal === null;
    });
  const missionAcceptedIds = sentinel.mission_accepted_lap_ids;
  const attemptIds = sentinel.measurement_attempt_ids;
  const acceptanceBasis = String(sentinel.mission_acceptance_basis);
  const acceptanceBasisIsCanonical = uniqueStrings(missionAcceptedIds)
    && uniqueStrings(attemptIds)
    && ["unbound", "p19_measurement_attempt", "controlled_workflow_stage"]
      .includes(acceptanceBasis)
    && (acceptanceBasis !== "unbound"
      || (missionAcceptedIds.length === 0 && attemptIds.length === 0))
    && (acceptanceBasis !== "p19_measurement_attempt"
      || (["measurement_mission", "discriminator"].includes(String(sentinel.p19_plan_kind))
        && missionContract !== null
        && missionAcceptedIds.length > 0 && attemptIds.length > 0))
    && (acceptanceBasis !== "controlled_workflow_stage"
      || (sentinel.p19_plan_kind === "controlled_test"
        && missionAcceptedIds.length > 0 && attemptIds.length === 0));
  const expectedComplete = sentinel.required_laps !== null
    && Array.isArray(missionAcceptedIds)
    && missionAcceptedIds.length >= Number(sentinel.required_laps)
    && !["blocked_by_p19", "stopped_by_p19"].includes(String(sentinel.mission_state));
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
    || typeof sentinel.mission !== "string" || sentinel.mission.length === 0
    || typeof sentinel.need !== "string" || sentinel.need.length === 0
    || typeof sentinel.success !== "string" || sentinel.success.length === 0
    || !strings(sentinel.hold_constant)
    || !strings(sentinel.watch)
    || !strings(sentinel.stop)
    || !sentinelPlanMatchesP19
    || sentinel.mission !== p19Action.title
    || sentinel.need !== p19Action.instruction
    || (typeof scope.report.briefing.success_check === "string"
      && sentinel.success !== scope.report.briefing.success_check)
    || !(sentinel.required_laps === null
      || (integerNumber(sentinel.required_laps) && sentinel.required_laps >= 1))
    || !integerNumber(sentinel.context_cleared_laps)
    || sentinel.context_cleared_laps !== contextOrdinal
    || !acceptanceBasisIsCanonical
    || typeof sentinel.collection_complete !== "boolean"
    || sentinel.collection_complete !== expectedComplete
    || (sentinel.mission_state === "collection_complete" && !sentinel.collection_complete)
    || (sentinel.collection_complete
      && !["collection_complete", "awaiting_p19_score"].includes(String(sentinel.mission_state)))
    || !["measurement", "A", "B", "A2", "blocked", "stopped", "awaiting_score"].includes(String(sentinel.stage))
    || !sentinelLapsAreCanonical
    || !safeTexts(sentinel.blocker_reasons)
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
    || !safeText(value.current_subgoal.subgoal_id)
    || !safeText(value.current_subgoal.title)
    || !safeText(value.current_subgoal.selected_tool)
    || !value.available_tools.some((tool) => (
      tool.tool_id === String((value.current_subgoal as Record<string, unknown>).selected_tool)
    ))
    || !safeText(value.current_subgoal.why_this_tool)
    || !uniqueStrings(value.current_subgoal.distinguishes_cause_ids)
    || !uniqueStrings(value.current_subgoal.required_evidence)
    || !safeText(value.current_subgoal.stop_condition)
    || !integerNumber(value.current_subgoal.priority_rank)
    || value.current_subgoal.priority_rank < 1
  )) return false;
  if (value.pending_driver_question !== null && (
    !record(value.pending_driver_question)
    || value.pending_driver_question.workspace_revision !== identity.workspace_revision
    || !safeText(value.pending_driver_question.question)
    || !safeText(value.pending_driver_question.reason)
    || !safeTexts(value.pending_driver_question.answer_options)
  )) return false;
  if (value.investigation !== null && (
    !validInvestigation(value.investigation)
    || value.investigation.investigation_id !== identity.investigation_id
  )) return false;
  if (value.folded_state !== null && (
    !record(value.folded_state)
    || value.folded_state.investigation_id !== identity.investigation_id
    || !["open", "complete", "stale", "abandoned"].includes(String(value.folded_state.status))
    || !integerNumber(value.folded_state.last_sequence)
    || value.folded_state.last_sequence < 0
    || !uniqueStrings(value.folded_state.completed_tool_ids)
    || !strings(value.folded_state.driver_answers)
    || !Array.isArray(value.folded_state.hypotheses)
    || !value.folded_state.hypotheses.every((item) => (
      record(item)
      && typeof item.cause_id === "string" && item.cause_id.length > 0
      && ["likely", "possible", "ruled_out", "unresolved"].includes(String(item.p19_state))
      && ["uninspected", "inspection_pending", "inspected", "needs_driver_answer",
        "needs_measurement", "complete", "stale"].includes(String(item.progress))
      && uniqueStrings(item.component_ids)
      && uniqueStrings(item.support_artifact_ids)
      && uniqueStrings(item.contradiction_artifact_ids)
    ))
    || new Set(value.folded_state.hypotheses.map((item) => (
      (item as Record<string, unknown>).cause_id
    ))).size !== value.folded_state.hypotheses.length
    || !nullableString(value.folded_state.pending_driver_question_id)
    || typeof value.folded_state.accepted_workspace_revision !== "string"
    || !hash.test(value.folded_state.accepted_workspace_revision)
  )) return false;
  const p34Entries = trustedEntries.filter((entry) => !entry.producer_id.startsWith("p35."));
  const p34ToolIds = value.available_tools
    .map((tool) => String(tool.tool_id))
    .filter((toolId) => !vehicleDynamicsToolIds.includes(
      toolId as (typeof vehicleDynamicsToolIds)[number],
    ));
  if (!isInvestigationImprovementProjection(value.investigation_improvement, {
    runId: scope.runId,
    sessionId: scope.sessionId,
    workspaceRevision: String(identity.workspace_revision),
    generatedAt: String(value.generated_at),
    investigationId: identity.investigation_id as string | null,
    investigationOpenedAt: value.investigation === null
      ? null : String(value.investigation.opened_at),
    objectiveId: scope.objectiveId,
    p19SnapshotSha256: String(identity.reasoning_snapshot_sha256),
    p20ProjectionSha256: String(identity.p20_state_revision),
    p26ProjectionSha256: String(identity.p26_knowledge_graph_sha256),
    p32ProjectionSha256: String(identity.p32_projection_sha256),
    p33ProjectionSha256: trustedLearning.projection_sha256,
    p33HistoryRevision: String(identity.learning_history_revision),
    p33LedgerHeadSha256: identity.learning_ledger_head_sha256 as string | null,
    p33ContextSha256: trustedLearning.current_context_sha256,
    p33ProblemSha256: trustedLearning.current_problem_sha256,
    foldedStatus: value.folded_state === null ? null : String(value.folded_state.status),
    stepNumber: value.folded_state === null ? null : Number(value.folded_state.last_sequence),
    p19CauseIds: value.p19_cause_ids as string[],
    p19CauseStates: value.folded_state === null
      ? [] : value.folded_state.hypotheses as Array<{ cause_id: string; p19_state: string }>,
    p19ContradictionArtifactIds: value.p19_contradiction_artifact_ids as string[],
    availableToolIds: p34ToolIds,
    availableArtifactIds: p34Entries.map((entry) => entry.artifact_id),
    completedToolIds: value.folded_state === null
      ? [] : value.folded_state.completed_tool_ids as string[],
    evidenceEntries: p34Entries,
    learningPrior: trustedLearning,
    currentSubgoal: value.current_subgoal === null ? null : {
      selectedTool: String(value.current_subgoal.selected_tool),
      distinguishesCauseIds: value.current_subgoal.distinguishes_cause_ids as string[],
    },
    driverAnswers: value.folded_state === null
      ? [] : value.folded_state.driver_answers as string[],
    blockerReasons: value.blocker_reasons as string[],
  })) return false;
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
