import type {
  PerformanceMechanismAssessment,
  PerformanceMechanismCandidate,
  MechanismSeparationRow,
  PhaseResponseMetric,
  VehicleDynamicsChainStage,
  VehicleDynamicsChainStageKind,
  VehicleDynamicsFocusArtifact,
  VehicleDynamicsInspectionToolId,
  VehicleProblemSignature,
  VehicleResponseObservation,
} from "../types/vehicleDynamics";
import type { LapTimeOpportunity } from "../types/performanceIntelligence";
import { canonicalJsonSha256 } from "./canonicalJsonSha256.ts";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";
import {
  p35RuntimeTrustManifest,
  type P35RuntimeMechanismTrust,
} from "./vehicleDynamicsRegistry.ts";

const SHA256 = /^[0-9a-f]{64}$/;
const TYPED_ID = /^[a-z0-9][a-z0-9_.:-]*$/;
const P35_RUNTIME_TRUST_SCHEMA = "p35.vehicle-dynamics-runtime-trust.v1";
const P35_RUNTIME_TRUST_SHA256 = "5bc9139f42049f391015040948147f9de37af1b2da770ea99e10d1db72f74164";
const P35_GRAPH_ID = p35RuntimeTrustManifest.graph_id;
const P35_GRAPH_VERSION = p35RuntimeTrustManifest.graph_version;
const P35_KNOWLEDGE_VERSION = p35RuntimeTrustManifest.knowledge_version;
const P35_GRAPH_SHA256 = p35RuntimeTrustManifest.knowledge_graph_sha256;
const P35_PYTHON_FLOAT_KEYS = new Set([
  "lap_pct_end", "lap_pct_start", "local_time_delta_s", "onset_pct", "value",
]);

const CHAIN_ORDER = [
  "driver_input",
  "vehicle_demand",
  "vehicle_response",
  "tire_platform_state",
  "time_consequence",
] as const satisfies readonly VehicleDynamicsChainStageKind[];

export const vehicleDynamicsInspectionToolIds = [
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
] as const satisfies readonly VehicleDynamicsInspectionToolId[];

const EVIDENCE_STATES = new Set([
  "measured",
  "calculated",
  "estimated_proxy",
  "observed_correlation",
  "controlled_test_effect",
  "unavailable",
  "blocked_by_context",
  "needs_confirmation",
]);
const POSITIVE_STAGE_STATES = new Set([
  "measured",
  "calculated",
  "estimated_proxy",
  "observed_correlation",
  "controlled_test_effect",
]);
const MEASURED_TIME_STATES = new Set([
  "measured",
  "calculated",
  "observed_correlation",
  "controlled_test_effect",
]);
const BLOCKED_FOCUS_STATES = new Set([
  "unavailable",
  "blocked_by_context",
  "needs_confirmation",
]);
const REQUIRED_UNAVAILABLE_QUANTITIES = [
  "quantity:exact_tire_force",
  "quantity:exact_wheel_load",
  "quantity:exact_spring_force",
  "quantity:exact_damper_force",
  "quantity:exact_arb_torque",
  "quantity:exact_aerodynamic_downforce",
  "quantity:exact_aerodynamic_balance",
  "quantity:exact_aerodynamic_drag_force",
  "quantity:exact_drag_coefficient",
  "quantity:exact_differential_torque",
  "quantity:exact_contact_patch_distribution",
  "quantity:exact_friction_coefficient",
] as const;

const UNAVAILABLE_PHYSICS_VALUE = new RegExp(
  String.raw`(?:\b(?:tire force|wheel load|spring force|damper force|anti[- ]?roll[- ]?bar torque|arb torque|aerodynamic downforce|aerodynamic balance|aerodynamic drag force|drag coefficient|differential torque|contact[- ]?patch distribution|friction coefficient)\b[^.!?\n]{0,56}(?:=|\bis\b|\bwas\b|\bmeasured\b|\bcalculated\b|\bestimated\b)[^.!?\n]{0,24}[+-]?\d|[+-]?\d[^.!?\n]{0,24}\b(?:lb|lbf|n|nm|n-m|coefficient)\b[^.!?\n]{0,48}\b(?:tire force|wheel load|spring force|damper force|arb torque|downforce|drag|differential torque)\b)`,
  "i",
);
const CAUSAL_AUTHORITY = /\b(?:caused?|proves?|proved|responsible\s+for|due\s+to|because\s+of|attributable\s+to|result(?:ed|s|ing)?\s+(?:in|from)|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|explains?|explained\s+by)\b/i;
const NEGATED_CAUSAL_BOUNDARY = /\b(?:(?:does|do|did)\s+not|cannot|can\s+not|(?:is|are|was|were)\s+not|no|none\s+is)\s+(?:establish(?:ed|es)?|prove(?:d|s|n)?|show(?:n|s)?|claim(?:ed|s)?)?\s*(?:as\s+)?(?:a\s+|the\s+)?(?:component\s+)?(?:cause|causation)\b/gi;
const NEGATED_CAUSAL_OUTCOME = /\b(?:(?:does|do|did)\s+not|cannot|can\s+not|(?:is|are|was|were)\s+not)\s+(?:caus(?:e|ed|es|ing)|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from)|explain(?:ed|s|ing)?)\b/gi;
const LEGACY_SOLID_AXLE_CONTROL = /(?:^|[:_.-])(?:track[_-]?bar|truck[_-]?arm(?:[_-]?mount)?)(?:$|[:_.-])/i;

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const exactKeys = (value: unknown, keys: readonly string[]): value is Record<string, unknown> =>
  record(value)
  && Object.keys(value).length === keys.length
  && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
const nonempty = (value: unknown): value is string =>
  typeof value === "string" && value.trim().length > 0;
const typedId = (value: unknown): value is string =>
  nonempty(value) && TYPED_ID.test(value);
const nullableTypedId = (value: unknown): value is string | null =>
  value === null || typedId(value);
const nullableText = (value: unknown): value is string | null =>
  value === null || nonempty(value);
const finiteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const lapNumbers = (value: unknown): value is number[] =>
  Array.isArray(value)
  && value.every((item) => Number.isInteger(item) && item >= 0)
  && new Set(value).size === value.length;
const texts = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(nonempty);
const uniqueTexts = (value: unknown): value is string[] =>
  texts(value) && new Set(value).size === value.length;
const sameTexts = (value: unknown, expected: readonly string[]): value is string[] =>
  uniqueTexts(value)
  && value.length === expected.length
  && value.every((item, index) => item === expected[index]);
const sameNumbers = (value: unknown, expected: readonly number[]): value is number[] =>
  Array.isArray(value)
  && value.length === expected.length
  && value.every((item, index) => item === expected[index]);

function runtimeSupportContractSatisfied(
  mechanism: P35RuntimeMechanismTrust,
  stages: readonly {
    stage: VehicleDynamicsChainStageKind;
    evidence_state: string;
    source_channels: readonly string[];
  }[],
  p20SourceChannels: readonly string[],
): boolean {
  const byStage = new Map(stages.map((stage) => [stage.stage, stage]));
  if (!mechanism.support_required_evidence_layers.every((layer) => {
    const stage = byStage.get(layer);
    return stage !== undefined && POSITIVE_STAGE_STATES.has(stage.evidence_state);
  })) return false;
  return mechanism.support_required_channel_groups.every((requirement) => {
    const available = new Set<string>();
    for (const layer of requirement.evidence_layer_ids) {
      const stage = byStage.get(layer);
      if (stage) stage.source_channels.forEach((channel) => available.add(channel));
      if (layer === "vehicle_response") {
        p20SourceChannels.forEach((channel) => available.add(channel));
      }
    }
    const matchedAlternatives = requirement.alternatives.filter((alternative) => (
      alternative.accepted_source_channel_ids.some((channel) => available.has(channel))
    )).length;
    return matchedAlternatives >= requirement.minimum_alternatives;
  });
}

export type CanonicalP35P32Binding = {
  p32PerformanceMechanismIds: string[];
  performanceOpportunityIds: string[];
  measuredTimeConsequenceAvailable: boolean;
  timeConsequenceSourceChannels: string[];
  phaseKind: string | null;
  responseRegime: "transient" | "steady_state" | "both" | null;
  timeOriginKind: string | null;
  trafficBlocked: boolean;
  attributionBlocked: boolean;
  candidateOpportunityAvailable: boolean;
  opportunityLapNumbers: number[];
  supportLapNumbers: number[];
  opportunityLapPctStart: number | null;
  opportunityLapPctEnd: number | null;
  opportunityPhase: string | null;
};

function canonicalPhaseKind(phase: string): string | null {
  const text = phase.toLowerCase().replace(/[- ]/g, "_");
  const aliases = new Map<string, string>([
    ["braking", "brake"],
    ["brake_application", "brake"],
    ["brake_release", "transition"],
    ["brake_release_transition", "transition"],
    ["bump_curb", "transition"],
    ["corner_entry", "entry"],
    ["mid_corner", "center"],
    ["apex", "center"],
    ["throttle", "throttle_pickup"],
    ["power", "throttle_pickup"],
    ["full_throttle_exit", "exit"],
    ["carry", "following_straight"],
    ["following_straight_carry", "following_straight"],
    ["following_straight_time", "following_straight"],
  ]);
  const canonical = aliases.get(text) ?? text;
  return [
    "straight", "lift", "brake", "turn_in", "entry", "center",
    "throttle_pickup", "exit", "following_straight", "transition",
  ].includes(canonical) ? canonical : null;
}

function canonicalResponseRegime(
  phase: string | null,
): "transient" | "steady_state" | "both" | null {
  if (phase === null) return null;
  if (["lift", "brake", "turn_in", "entry", "throttle_pickup", "transition"].includes(phase)) {
    return "transient";
  }
  if (["straight", "center", "following_straight"].includes(phase)) {
    return "steady_state";
  }
  return "both";
}

export function deriveCanonicalP35P32Binding(
  opportunities: readonly LapTimeOpportunity[],
  basisContextBlockers: readonly string[] = [],
): CanonicalP35P32Binding {
  const measured = opportunities.filter((item) => item.local_delta_s !== null);
  const losses = measured.filter((item) => (item.local_delta_s ?? 0) > 0);
  const cohort = losses.length > 0 ? losses : measured;
  const leading = cohort.reduce<LapTimeOpportunity | null>((best, item) => {
    if (best === null) return item;
    const itemMagnitude = losses.length > 0
      ? (item.local_delta_s ?? 0) : Math.abs(item.local_delta_s ?? 0);
    const bestMagnitude = losses.length > 0
      ? (best.local_delta_s ?? 0) : Math.abs(best.local_delta_s ?? 0);
    if (itemMagnitude !== bestMagnitude) return itemMagnitude > bestMagnitude ? item : best;
    if (item.start_pct !== best.start_pct) return item.start_pct < best.start_pct ? item : best;
    return item.opportunity_id < best.opportunity_id ? item : best;
  }, null);
  if (leading === null || leading.source_laps.length === 0 || leading.source_channels.length === 0) {
    return {
      p32PerformanceMechanismIds: [],
      performanceOpportunityIds: [],
      measuredTimeConsequenceAvailable: false,
      timeConsequenceSourceChannels: [],
      phaseKind: null,
      responseRegime: null,
      timeOriginKind: null,
      trafficBlocked: false,
      attributionBlocked: false,
      candidateOpportunityAvailable: false,
      opportunityLapNumbers: [],
      supportLapNumbers: [],
      opportunityLapPctStart: null,
      opportunityLapPctEnd: null,
      opportunityPhase: null,
    };
  }
  const phaseKind = canonicalPhaseKind(leading.phase);
  const trafficFractions = [
    leading.source_traffic_exposure_fraction,
    leading.reference_traffic_exposure_fraction,
  ];
  const trafficUnknown = trafficFractions.some((value) => value === null);
  const trafficExposed = trafficFractions.some((value) => value !== null && value > 0);
  const locallyQualified = ["qualified", "qualified_pair"].includes(leading.context_state)
    && leading.attribution_state === "candidate_only";
  return {
    p32PerformanceMechanismIds: [...new Set(leading.mechanism_candidates)],
    performanceOpportunityIds: [leading.opportunity_id],
    measuredTimeConsequenceAvailable: true,
    timeConsequenceSourceChannels: [...leading.source_channels],
    phaseKind,
    responseRegime: canonicalResponseRegime(phaseKind),
    timeOriginKind: leading.origin_kind,
    trafficBlocked: leading.attribution_state === "blocked_by_traffic"
      || trafficExposed
      || basisContextBlockers.some((blocker) => blocker.toLowerCase().includes("traffic")),
    attributionBlocked: !locallyQualified
      || basisContextBlockers.length > 0
      || trafficUnknown
      || trafficExposed,
    candidateOpportunityAvailable: Number.isFinite(leading.local_delta_s)
      && leading.local_delta_s !== 0
      && leading.source_laps.length >= 2,
    opportunityLapNumbers: [...leading.source_laps],
    supportLapNumbers: leading.source_laps.slice(0, 1),
    opportunityLapPctStart: leading.start_pct,
    opportunityLapPctEnd: leading.end_pct,
    opportunityPhase: leading.phase,
  };
}
const safeText = (value: unknown): value is string =>
  nonempty(value) && !hasSetupAuthorityDirective(value) && !UNAVAILABLE_PHYSICS_VALUE.test(value);
const safeTexts = (value: unknown): value is string[] =>
  texts(value) && value.every((item) => !hasSetupAuthorityDirective(item) && !UNAVAILABLE_PHYSICS_VALUE.test(item));
const safeSummary = (value: unknown): value is string =>
  safeText(value) && !CAUSAL_AUTHORITY.test(value
    .replace(NEGATED_CAUSAL_BOUNDARY, "explicit non-causal boundary")
    .replace(NEGATED_CAUSAL_OUTCOME, "explicit non-causal outcome boundary"));

export const vehicleDynamicsStageKeys = [
  "stage",
  "evidence_state",
  "source_artifact_ids",
  "source_channels",
  "summary",
  "blocker_reasons",
  "authority",
] as const;

export const performanceMechanismCandidateKeys = [
  "mechanism_id",
  "p32_performance_mechanism_ids",
  "support_artifact_ids",
  "contradiction_artifact_ids",
  "discriminator_contract_ids",
  "component_family_ids",
  "blocker_reasons",
  "relevance",
  "authority",
  "component_cause_authorized",
  "setup_authorized",
] as const;

export const vehicleDynamicsFocusArtifactKeys = [
  "artifact_id",
  "mechanism_id",
  "observation_contract_id",
  "inspection_tool_id",
  "stage",
  "evidence_state",
  "source_artifact_ids",
  "source_channels",
  "lap_numbers",
  "lap_pct_start",
  "lap_pct_end",
  "phase",
  "polarity",
  "summary",
  "blocker_reasons",
  "authority",
] as const;

export const phaseResponseMetricKeys = [
  "metric_id",
  "quantity",
  "value",
  "units",
  "semantics",
  "source_channels",
  "force_like",
  "setup_authorized",
] as const;

export const vehicleResponseObservationKeys = [
  "observation_id",
  "opportunity_id",
  "run_id",
  "source_lap_numbers",
  "reference_lap_numbers",
  "phase",
  "lap_pct_start",
  "lap_pct_end",
  "onset_pct",
  "onset_resolution",
  "response_regime",
  "driver_demand_state",
  "vehicle_response_state",
  "line_state",
  "context_state",
  "persistence",
  "metrics",
  "source_artifact_ids",
  "source_channels",
  "blocker_reasons",
  "evidence_state",
  "authority",
  "component_cause_authorized",
  "setup_authorized",
] as const;

export const vehicleProblemSignatureKeys = [
  "signature_id",
  "response_observation_id",
  "opportunity_id",
  "time_origin",
  "local_time_delta_s",
  "phase",
  "onset_pct",
  "onset_resolution",
  "response_regime",
  "driver_demand_state",
  "vehicle_response_state",
  "line_state",
  "speed_dependence",
  "stint_dependence",
  "traffic_dependence",
  "surface_dependence",
  "front_rear_corner_scope",
  "strongest_contradiction",
  "authority",
  "component_cause_authorized",
  "setup_authorized",
] as const;

export const mechanismSeparationRowKeys = [
  "mechanism_id",
  "response_observation_id",
  "required_response_kpi_ids",
  "support_artifact_ids",
  "contradiction_artifact_ids",
  "missing_evidence",
  "discriminator_contract_ids",
  "protected_countereffects",
  "component_family_ids",
  "state",
  "authority",
  "setup_authorized",
] as const;

export const performanceMechanismAssessmentKeys = [
  "schema_version",
  "p35_assessment_sha256",
  "run_id",
  "session_id",
  "objective_id",
  "car_path",
  "car_version",
  "iracing_build_version",
  "track_package",
  "vehicle_runtime_identity_sha256",
  "graph_id",
  "graph_version",
  "knowledge_version",
  "knowledge_graph_sha256",
  "p19_reasoning_snapshot_sha256",
  "p20_state_revision",
  "p20_profile_hash",
  "p26_graph_version",
  "p26_knowledge_graph_sha256",
  "p32_projection_sha256",
  "p32_performance_mechanism_ids",
  "performance_opportunity_ids",
  "measured_time_consequence_available",
  "chain",
  "tire_demand_state_ids",
  "load_path_ids",
  "response_regime",
  "response_observations",
  "problem_signature",
  "mechanism_separation",
  "candidates",
  "focus_artifacts",
  "strongest_support_artifact_id",
  "strongest_contradiction_artifact_id",
  "next_discriminator_contract_id",
  "unavailable_quantity_ids",
  "traffic_blocked",
  "applicability_state",
  "applicability_blockers",
  "blocker_reasons",
  "observation_authority",
  "mechanism_authority",
  "component_causal_claim_count",
  "setup_authorized",
  "terminal_authority",
] as const;

function validStage(value: unknown): value is VehicleDynamicsChainStage {
  if (!exactKeys(value, vehicleDynamicsStageKeys)
    || !CHAIN_ORDER.includes(value.stage as VehicleDynamicsChainStageKind)
    || !EVIDENCE_STATES.has(String(value.evidence_state))
    || !uniqueTexts(value.source_artifact_ids)
    || !uniqueTexts(value.source_channels)
    || !safeSummary(value.summary)
    || !safeTexts(value.blocker_reasons)
    || value.authority !== "observation_only") return false;
  const positive = POSITIVE_STAGE_STATES.has(String(value.evidence_state));
  return positive
    ? value.source_artifact_ids.length > 0
      && value.source_channels.length > 0
      && value.blocker_reasons.length === 0
    : value.blocker_reasons.length > 0;
}

function validCandidate(value: unknown): value is PerformanceMechanismCandidate {
  if (!exactKeys(value, performanceMechanismCandidateKeys)
    || !typedId(value.mechanism_id)
    || LEGACY_SOLID_AXLE_CONTROL.test(value.mechanism_id)
    || !uniqueTexts(value.p32_performance_mechanism_ids)
    || value.p32_performance_mechanism_ids.length === 0
    || !uniqueTexts(value.support_artifact_ids)
    || !uniqueTexts(value.contradiction_artifact_ids)
    || !uniqueTexts(value.discriminator_contract_ids)
    || value.discriminator_contract_ids.length === 0
    || !uniqueTexts(value.component_family_ids)
    || value.component_family_ids.length === 0
    || value.component_family_ids.some((item) => LEGACY_SOLID_AXLE_CONTROL.test(item))
    || !safeTexts(value.blocker_reasons)
    || !["candidate", "blocked"].includes(String(value.relevance))
    || value.authority !== "candidate_only"
    || value.component_cause_authorized !== false
    || value.setup_authorized !== false) return false;
  const contradictionArtifactIds = value.contradiction_artifact_ids as string[];
  const overlap = value.support_artifact_ids.some((item) => contradictionArtifactIds.includes(item));
  return !overlap
    && (value.relevance === "blocked"
      ? value.blocker_reasons.length > 0
        && value.support_artifact_ids.length === 0
        && value.contradiction_artifact_ids.length > 0
      : value.blocker_reasons.length === 0 && value.support_artifact_ids.length > 0);
}

function validFocusArtifact(value: unknown): value is VehicleDynamicsFocusArtifact {
  if (!exactKeys(value, vehicleDynamicsFocusArtifactKeys)
    || !typedId(value.artifact_id)
    || !typedId(value.mechanism_id)
    || !nullableTypedId(value.observation_contract_id)
    || !vehicleDynamicsInspectionToolIds.includes(
      value.inspection_tool_id as VehicleDynamicsInspectionToolId,
    )
    || !new RegExp(
      `^p35\\.focus\\.${String(value.inspection_tool_id).replace(/^inspect_/, "")}:[0-9a-f]{24}$`,
    ).test(String(value.artifact_id))
    || !CHAIN_ORDER.includes(value.stage as VehicleDynamicsChainStageKind)
    || !EVIDENCE_STATES.has(String(value.evidence_state))
    || !uniqueTexts(value.source_artifact_ids)
    || value.source_artifact_ids.length === 0
    || !uniqueTexts(value.source_channels)
    || value.source_channels.length === 0
    || !lapNumbers(value.lap_numbers)
    || !((value.lap_pct_start === null && value.lap_pct_end === null)
      || (finiteNumber(value.lap_pct_start)
        && finiteNumber(value.lap_pct_end)
        && value.lap_pct_start >= 0
        && value.lap_pct_end <= 100
        && value.lap_pct_start <= value.lap_pct_end))
    || !nullableText(value.phase)
    || !["support", "contradiction", "uncertainty", "neutral"]
      .includes(String(value.polarity))
    || !safeSummary(value.summary)
    || !safeTexts(value.blocker_reasons)
    || value.authority !== "observation_only") return false;
  if (BLOCKED_FOCUS_STATES.has(String(value.evidence_state))) {
    return value.blocker_reasons.length > 0 && value.polarity !== "support";
  }
  return value.blocker_reasons.length === 0
    && value.polarity !== "uncertainty"
    && value.lap_numbers.length > 0
    && value.lap_pct_start !== null
    && value.lap_pct_end !== null
    && value.phase !== null;
}

const RESPONSE_METRIC_UNITS = new Map<string, string>([
  ["elapsed_time_delta_s", "s"],
  ["speed_delta_mph", "mph"],
  ["throttle_demand_delta_pct", "%"],
  ["brake_demand_delta_pct", "%"],
  ["steering_wheel_demand_delta_deg", "deg"],
  ["yaw_rate_response_delta_rad_s", "rad/s"],
  ["longitudinal_accel_response_delta_mps2", "m/s^2"],
  ["path_delta_m", "m"],
  ["line_separation_m", "m"],
]);
const RESPONSE_METRIC_CHANNELS = new Map<string, Set<string>>([
  ["elapsed_time_delta_s", new Set(["session_time", "SessionTime", "lap_dist_pct_100", "lap_dist_pct"])],
  ["speed_delta_mph", new Set(["speed_mph", "Speed", "speed_mps"])],
  ["throttle_demand_delta_pct", new Set(["Throttle", "throttle_pct", "throttle_01", "throttle"])],
  ["brake_demand_delta_pct", new Set(["Brake", "brake_pct", "brake_01"])],
  ["steering_wheel_demand_delta_deg", new Set(["SteeringWheelAngle", "steering_deg", "steering_rad"])],
  ["yaw_rate_response_delta_rad_s", new Set(["YawRate", "yaw_rate"])],
  ["longitudinal_accel_response_delta_mps2", new Set(["LongAccel", "long_accel", "long_accel_mps2"])],
  ["path_delta_m", new Set(["lat", "lon", "Lat", "Lon", "lap_dist_pct_100"])],
  ["line_separation_m", new Set(["lat", "lon", "Lat", "Lon", "lap_dist_pct_100"])],
]);
const UNSAFE_RESPONSE_CHANNELS = new Set([
  "front_slip_angle_deg",
  "rear_slip_angle_deg",
  "slip_angle_balance_deg",
  "ackermann_steering_error_deg",
  "ackermann_scrub_proxy",
  "wheel_power_proxy_w",
  "cda_coastdown_proxy_m2",
  "full_throttle_resistance_cda_proxy_m2",
  "platform_roll_deg_from_rh",
]);

function validPhaseResponseMetric(value: unknown): value is PhaseResponseMetric {
  const acceptedChannels = RESPONSE_METRIC_CHANNELS.get(String(
    record(value) ? value.quantity : "",
  ));
  return exactKeys(value, phaseResponseMetricKeys)
    && /^p354\.metric:[0-9a-f]{24}$/.test(String(value.metric_id))
    && RESPONSE_METRIC_UNITS.get(String(value.quantity)) === value.units
    && finiteNumber(value.value)
    && ["measured_delta", "calculated_delta"].includes(String(value.semantics))
    && uniqueTexts(value.source_channels)
    && value.source_channels.length > 0
    && acceptedChannels !== undefined
    && value.source_channels.every((channel) => acceptedChannels.has(channel))
    && value.force_like === false
    && value.setup_authorized === false;
}

function validVehicleResponseObservation(
  value: unknown,
): value is VehicleResponseObservation {
  if (!exactKeys(value, vehicleResponseObservationKeys)
    || !/^p354\.response:[0-9a-f]{24}$/.test(String(value.observation_id))
    || !typedId(value.opportunity_id)
    || !nonempty(value.run_id)
    || !lapNumbers(value.source_lap_numbers)
    || value.source_lap_numbers.length === 0
    || !lapNumbers(value.reference_lap_numbers)
    || value.source_lap_numbers.some((lap) => (
      value.reference_lap_numbers as number[]
    ).includes(lap))
    || !nonempty(value.phase)
    || !finiteNumber(value.lap_pct_start)
    || !finiteNumber(value.lap_pct_end)
    || value.lap_pct_start < 0
    || value.lap_pct_end > 100
    || value.lap_pct_start > value.lap_pct_end
    || !finiteNumber(value.onset_pct)
    || value.onset_pct < value.lap_pct_start
    || value.onset_pct > value.lap_pct_end
    || value.onset_resolution !== "phase_boundary"
    || !["transient", "steady_state", "both"].includes(String(value.response_regime))
    || !["matched", "changed", "mixed", "unavailable"].includes(String(value.driver_demand_state))
    || !["changed", "not_established", "unavailable"].includes(String(value.vehicle_response_state))
    || !["matched", "changed", "unavailable"].includes(String(value.line_state))
    || !["qualified", "blocked", "unavailable"].includes(String(value.context_state))
    || !["phase_local", "carried_forward", "recovered", "unavailable"].includes(String(value.persistence))
    || !Array.isArray(value.metrics)
    || value.metrics.length === 0
    || !value.metrics.every(validPhaseResponseMetric)
    || !uniqueTexts(value.source_artifact_ids)
    || value.source_artifact_ids.length === 0
    || !uniqueTexts(value.source_channels)
    || value.source_channels.length === 0
    || value.source_channels.some((channel) => UNSAFE_RESPONSE_CHANNELS.has(channel))
    || !safeTexts(value.blocker_reasons)
    || !["measured", "blocked_by_context", "needs_confirmation"].includes(String(value.evidence_state))
    || value.authority !== "observation_only"
    || value.component_cause_authorized !== false
    || value.setup_authorized !== false) return false;
  const metricChannels = [...new Set(
    value.metrics.flatMap((metric) => metric.source_channels),
  )];
  if (!sameTexts(value.source_channels, metricChannels)) return false;
  return value.evidence_state === "measured"
    ? value.blocker_reasons.length === 0
    : value.blocker_reasons.length > 0;
}

function validVehicleProblemSignature(value: unknown): value is VehicleProblemSignature {
  return exactKeys(value, vehicleProblemSignatureKeys)
    && /^p354\.signature:[0-9a-f]{24}$/.test(String(value.signature_id))
    && /^p354\.response:[0-9a-f]{24}$/.test(String(value.response_observation_id))
    && typedId(value.opportunity_id)
    && ["local_generation", "carried_in", "amplified", "recovered", "surrendered", "unavailable"].includes(String(value.time_origin))
    && finiteNumber(value.local_time_delta_s)
    && nonempty(value.phase)
    && finiteNumber(value.onset_pct)
    && value.onset_pct >= 0
    && value.onset_pct <= 100
    && value.onset_resolution === "phase_boundary"
    && ["transient", "steady_state", "both"].includes(String(value.response_regime))
    && ["matched", "changed", "mixed", "unavailable"].includes(String(value.driver_demand_state))
    && ["changed", "not_established", "unavailable"].includes(String(value.vehicle_response_state))
    && ["matched", "changed", "unavailable"].includes(String(value.line_state))
    && value.speed_dependence === "not_established"
    && value.stint_dependence === "not_established"
    && ["blocked", "clear", "unavailable"].includes(String(value.traffic_dependence))
    && value.surface_dependence === "not_established"
    && value.front_rear_corner_scope === "unresolved"
    && safeSummary(value.strongest_contradiction)
    && value.authority === "observation_only"
    && value.component_cause_authorized === false
    && value.setup_authorized === false;
}

function validMechanismSeparationRow(value: unknown): value is MechanismSeparationRow {
  if (!exactKeys(value, mechanismSeparationRowKeys)
    || !typedId(value.mechanism_id)
    || !/^p354\.response:[0-9a-f]{24}$/.test(String(value.response_observation_id))
    || !uniqueTexts(value.required_response_kpi_ids)
    || value.required_response_kpi_ids.length === 0
    || !uniqueTexts(value.support_artifact_ids)
    || !uniqueTexts(value.contradiction_artifact_ids)
    || value.contradiction_artifact_ids.length === 0
    || !safeTexts(value.missing_evidence)
    || value.missing_evidence.length === 0
    || !uniqueTexts(value.discriminator_contract_ids)
    || value.discriminator_contract_ids.length === 0
    || !safeTexts(value.protected_countereffects)
    || value.protected_countereffects.length === 0
    || !uniqueTexts(value.component_family_ids)
    || value.component_family_ids.length === 0
    || !["alive", "weakened", "blocked"].includes(String(value.state))
    || value.authority !== "candidate_only"
    || value.setup_authorized !== false) return false;
  return value.state === "alive"
    ? value.support_artifact_ids.length > 0
    : value.support_artifact_ids.length === 0;
}

export type VehicleDynamicsTrustScope = {
  runId: string;
  sessionId: string;
  objectiveId: string;
  assessmentSha256: string;
  carPath: string;
  carVersion: string;
  iRacingBuildVersion: string;
  trackPackage: string;
  vehicleRuntimeIdentitySha256: string;
  p19ReasoningSnapshotSha256: string;
  p20StateRevision: string;
  p20ProfileHash: string | null;
  p26GraphVersion: string;
  p26KnowledgeGraphSha256: string;
  p32ProjectionSha256: string;
  p32PerformanceMechanismIds: readonly string[];
  performanceOpportunityIds: readonly string[];
  measuredTimeConsequenceAvailable: boolean;
  timeConsequenceSourceChannels: readonly string[];
  phaseKind: string | null;
  responseRegime: "transient" | "steady_state" | "both" | null;
  timeOriginKind: string | null;
  trafficBlocked: boolean;
  attributionBlocked: boolean;
  candidateOpportunityAvailable: boolean;
  opportunityLapNumbers: readonly number[];
  supportLapNumbers: readonly number[];
  opportunityLapPctStart: number | null;
  opportunityLapPctEnd: number | null;
  opportunityPhase: string | null;
  supportAdmissionAvailable: boolean;
  expectedChain: readonly {
    stage: VehicleDynamicsChainStageKind;
    evidence_state: string;
    source_artifact_ids: readonly string[];
    source_channels: readonly string[];
    blocker_reasons: readonly string[];
  }[];
  evidenceArtifactIds: readonly string[];
};

export function isPerformanceMechanismAssessment(
  value: unknown,
  scope: VehicleDynamicsTrustScope,
): value is PerformanceMechanismAssessment {
  if (!exactKeys(value, performanceMechanismAssessmentKeys)
    || p35RuntimeTrustManifest.schema_version !== P35_RUNTIME_TRUST_SCHEMA
    || p35RuntimeTrustManifest.runtime_trust_sha256 !== P35_RUNTIME_TRUST_SHA256
    || p35RuntimeTrustManifest.mechanisms.length !== 16
    || value.schema_version !== "p35.performance-mechanism-assessment.v1"
    || typeof value.p35_assessment_sha256 !== "string"
    || !SHA256.test(value.p35_assessment_sha256)
    || value.p35_assessment_sha256 !== scope.assessmentSha256
    || value.run_id !== scope.runId
    || value.session_id !== scope.sessionId
    || value.objective_id !== scope.objectiveId
    || !nonempty(value.car_path)
    || value.car_path !== scope.carPath
    || !nonempty(value.car_version)
    || value.car_version !== scope.carVersion
    || !nonempty(value.iracing_build_version)
    || value.iracing_build_version !== scope.iRacingBuildVersion
    || !nonempty(value.track_package)
    || value.track_package !== scope.trackPackage
    || value.vehicle_runtime_identity_sha256 !== scope.vehicleRuntimeIdentitySha256
    || value.knowledge_graph_sha256 !== P35_GRAPH_SHA256
    || value.graph_id !== P35_GRAPH_ID
    || value.graph_version !== P35_GRAPH_VERSION
    || value.knowledge_version !== P35_KNOWLEDGE_VERSION
    || value.p19_reasoning_snapshot_sha256 !== scope.p19ReasoningSnapshotSha256
    || value.p20_state_revision !== scope.p20StateRevision
    || !(value.p20_profile_hash === null
      || (typeof value.p20_profile_hash === "string" && SHA256.test(value.p20_profile_hash)))
    || value.p20_profile_hash !== scope.p20ProfileHash
    || value.p26_graph_version !== scope.p26GraphVersion
    || value.p26_knowledge_graph_sha256 !== scope.p26KnowledgeGraphSha256
    || value.p32_projection_sha256 !== scope.p32ProjectionSha256
    || !uniqueTexts(value.p32_performance_mechanism_ids)
    || !uniqueTexts(value.performance_opportunity_ids)
    || value.performance_opportunity_ids.length > 1
    || typeof value.measured_time_consequence_available !== "boolean"
    || !Array.isArray(value.chain)
    || value.chain.length !== CHAIN_ORDER.length
    || !value.chain.every(validStage)
    || !uniqueTexts(value.tire_demand_state_ids)
    || !uniqueTexts(value.load_path_ids)
    || !(value.response_regime === null
      || ["transient", "steady_state", "both"].includes(String(value.response_regime)))
    || !Array.isArray(value.response_observations)
    || value.response_observations.length > 1
    || !value.response_observations.every(validVehicleResponseObservation)
    || !(value.problem_signature === null
      || validVehicleProblemSignature(value.problem_signature))
    || !Array.isArray(value.mechanism_separation)
    || !value.mechanism_separation.every(validMechanismSeparationRow)
    || !Array.isArray(value.candidates)
    || !value.candidates.every(validCandidate)
    || !Array.isArray(value.focus_artifacts)
    || !value.focus_artifacts.every(validFocusArtifact)
    || !nullableTypedId(value.strongest_support_artifact_id)
    || !nullableTypedId(value.strongest_contradiction_artifact_id)
    || !nullableTypedId(value.next_discriminator_contract_id)
    || !sameTexts(value.unavailable_quantity_ids, REQUIRED_UNAVAILABLE_QUANTITIES)
    || typeof value.traffic_blocked !== "boolean"
    || !["ready", "unavailable", "incompatible", "unreviewed_build"]
      .includes(String(value.applicability_state))
    || !safeTexts(value.applicability_blockers)
    || !safeTexts(value.blocker_reasons)
    || value.observation_authority !== "observation_only"
    || value.mechanism_authority !== "candidate_only"
    || value.component_causal_claim_count !== 0
    || value.setup_authorized !== false
    || value.terminal_authority !== "p19_only") return false;

  if (!value.chain.every((item, index) => item.stage === CHAIN_ORDER[index])) return false;
  if ((value.applicability_state === "ready") !== (value.applicability_blockers.length === 0)) return false;
  if (value.applicability_state !== "ready" && value.candidates.length > 0) return false;
  if (value.response_regime !== scope.responseRegime
    || value.traffic_blocked !== scope.trafficBlocked
    || value.tire_demand_state_ids.length !== 0
    || value.load_path_ids.length !== 0) return false;
  const responseObservations = value.response_observations as VehicleResponseObservation[];
  const problemSignature = value.problem_signature as VehicleProblemSignature | null;
  const separationRows = value.mechanism_separation as MechanismSeparationRow[];
  const responseExpected = scope.measuredTimeConsequenceAvailable
    && scope.responseRegime !== null;
  if (responseObservations.length !== (responseExpected ? 1 : 0)
    || (responseObservations.length > 0) !== (problemSignature !== null)
    || responseObservations.some((item) => (
      item.run_id !== scope.runId
      || !scope.performanceOpportunityIds.includes(item.opportunity_id)
      || item.response_regime !== scope.responseRegime
      || item.lap_pct_start !== scope.opportunityLapPctStart
      || item.lap_pct_end !== scope.opportunityLapPctEnd
      || item.phase !== scope.opportunityPhase
    ))) return false;
  const response = responseObservations[0];
  if (problemSignature && (
    response === undefined
    || problemSignature.response_observation_id !== response.observation_id
    || problemSignature.opportunity_id !== response.opportunity_id
    || problemSignature.response_regime !== response.response_regime
    || problemSignature.phase !== response.phase
    || problemSignature.onset_pct !== response.onset_pct
  )) return false;
  if (value.traffic_blocked
    && !value.chain.some((item) => item.evidence_state === "blocked_by_context")) return false;
  if (scope.attributionBlocked && (
    !value.chain.some((item) => item.evidence_state === "blocked_by_context")
    || value.candidates.some((item) => (
      item.relevance !== "blocked" || item.support_artifact_ids.length > 0
    ))
  )) return false;
  if (value.measured_time_consequence_available
      !== MEASURED_TIME_STATES.has(value.chain[value.chain.length - 1].evidence_state)
    || value.measured_time_consequence_available
      !== (value.performance_opportunity_ids.length === 1)
    || value.measured_time_consequence_available !== scope.measuredTimeConsequenceAvailable
    || !sameTexts(
      value.chain[value.chain.length - 1].source_artifact_ids,
      scope.measuredTimeConsequenceAvailable ? scope.performanceOpportunityIds : [],
    )
    || !sameTexts(
      value.chain[value.chain.length - 1].source_channels,
      scope.timeConsequenceSourceChannels,
    )) return false;

  const evidenceArtifacts = new Set(scope.evidenceArtifactIds);
  if (!sameTexts(value.p32_performance_mechanism_ids, scope.p32PerformanceMechanismIds)
    || !sameTexts(value.performance_opportunity_ids, scope.performanceOpportunityIds)
    || !value.chain.every((item) => item.source_artifact_ids.every((id) => evidenceArtifacts.has(id)))
    || !value.focus_artifacts.every((item) => item.source_artifact_ids.every((id) => evidenceArtifacts.has(id)))
    || !value.candidates.every((item) => (
      item.p32_performance_mechanism_ids
        .every((id) => (value.p32_performance_mechanism_ids as string[]).includes(id))
    ))) return false;

  const expectedMechanisms = value.applicability_state === "ready"
    && scope.candidateOpportunityAvailable
    && scope.phaseKind !== null
    && scope.responseRegime !== null
    && scope.timeOriginKind !== null
    ? p35RuntimeTrustManifest.mechanisms.filter((mechanism) => (
      mechanism.p32_performance_mechanism_ids.some((id) => (
        scope.p32PerformanceMechanismIds.includes(id)
      ))
      && (mechanism.relevant_phases as readonly string[]).includes(scope.phaseKind as string)
      && (mechanism.allowed_time_origin_kinds as readonly string[])
        .includes(scope.timeOriginKind as string)
      && (scope.responseRegime === "both"
        || mechanism.response_regime === scope.responseRegime
        || mechanism.response_regime === "both")
    )).slice(0, 6)
    : [];
  if (value.candidates.length !== expectedMechanisms.length
    || !value.candidates.every((candidate, index) => {
      const mechanism = expectedMechanisms[index];
      const expectedP32Ids = mechanism.p32_performance_mechanism_ids.filter((id) => (
        scope.p32PerformanceMechanismIds.includes(id)
      ));
      return candidate.mechanism_id === mechanism.mechanism_id
        && sameTexts(candidate.p32_performance_mechanism_ids, expectedP32Ids)
        && sameTexts(candidate.component_family_ids, mechanism.component_family_ids)
        && sameTexts(
          candidate.discriminator_contract_ids,
          mechanism.discriminator_observation_contract_ids,
        )
        && candidate.support_artifact_ids.length <= 1
        && candidate.contradiction_artifact_ids.length === 1;
    })) return false;

  const candidates = value.candidates as PerformanceMechanismCandidate[];
  const focusArtifacts = value.focus_artifacts as VehicleDynamicsFocusArtifact[];
  const opportunityIds = value.performance_opportunity_ids as string[];
  const focusIds = new Set(focusArtifacts.map((item) => item.artifact_id));
  const focusById = new Map(focusArtifacts.map((item) => [item.artifact_id, item]));
  const mechanismById = new Map<string, P35RuntimeMechanismTrust>(
    p35RuntimeTrustManifest.mechanisms.map((item) => [item.mechanism_id, item]),
  );
  const candidateIds = candidates.map((item) => item.mechanism_id);
  if (separationRows.length !== candidates.length
    || separationRows.some((row, index) => (
      response === undefined
      || row.response_observation_id !== response.observation_id
      || row.mechanism_id !== candidates[index]?.mechanism_id
      || row.state !== (candidates[index]?.relevance === "candidate" ? "alive" : "blocked")
      || !sameTexts(row.support_artifact_ids, candidates[index]?.support_artifact_ids ?? [])
      || !sameTexts(row.contradiction_artifact_ids, candidates[index]?.contradiction_artifact_ids ?? [])
      || !sameTexts(row.discriminator_contract_ids, candidates[index]?.discriminator_contract_ids ?? [])
      || !sameTexts(row.component_family_ids, candidates[index]?.component_family_ids ?? [])
    ))) return false;
  if (new Set(candidateIds).size !== candidateIds.length
    || focusIds.size !== focusArtifacts.length
    || (candidates.length === 0) !== (focusArtifacts.length === 0)
    || !focusArtifacts.every((item) => candidateIds.includes(item.mechanism_id))
    || !candidates.every((item) => (
      [...item.support_artifact_ids, ...item.contradiction_artifact_ids]
        .every((id) => focusIds.has(id))
      && item.support_artifact_ids.every((id) => (
        focusById.get(id)?.mechanism_id === item.mechanism_id
        && focusById.get(id)?.polarity === "support"
      ))
      && item.contradiction_artifact_ids.every((id) => (
        focusById.get(id)?.mechanism_id === item.mechanism_id
        && ["contradiction", "uncertainty"].includes(String(focusById.get(id)?.polarity))
      ))
    ))) return false;
  if (!scope.supportAdmissionAvailable && candidates.some((candidate) => (
    candidate.relevance === "candidate" || candidate.support_artifact_ids.length > 0
  ))) return false;
  if (!focusArtifacts.every((focus) => {
    const support = candidates.some((candidate) => (
      candidate.support_artifact_ids.includes(focus.artifact_id)
    ));
    return support
      ? sameNumbers(focus.lap_numbers, scope.supportLapNumbers)
        && focus.lap_pct_start === scope.opportunityLapPctStart
        && focus.lap_pct_end === scope.opportunityLapPctEnd
        && focus.phase === scope.opportunityPhase
      : sameNumbers(focus.lap_numbers, scope.opportunityLapNumbers)
        && focus.lap_pct_start === scope.opportunityLapPctStart
        && focus.lap_pct_end === scope.opportunityLapPctEnd
        && focus.phase === scope.opportunityPhase;
  })) return false;
  if (scope.expectedChain.length !== CHAIN_ORDER.length) return false;
  const supportFocusArtifacts = focusArtifacts.filter((focus) => (
    candidates.some((candidate) => candidate.support_artifact_ids.includes(focus.artifact_id))
  ));
  if (supportFocusArtifacts.length > 0
    && scope.expectedChain[2].evidence_state !== "measured") return false;
  if (!value.chain.every((stage, index) => {
    const expected = scope.expectedChain[index];
    const expectedSourceIds = index === 2
      ? [...new Set([
        ...expected.source_artifact_ids,
        ...supportFocusArtifacts.flatMap((focus) => focus.source_artifact_ids),
      ])]
      : expected.source_artifact_ids;
    const expectedChannels = index === 2
      ? [...new Set([
        ...expected.source_channels,
        ...supportFocusArtifacts.flatMap((focus) => focus.source_channels),
      ])]
      : expected.source_channels;
    return stage.stage === expected.stage
      && stage.evidence_state === expected.evidence_state
      && sameTexts(stage.source_artifact_ids, expectedSourceIds)
      && sameTexts(stage.source_channels, expectedChannels)
      && sameTexts(stage.blocker_reasons, expected.blocker_reasons);
  })) return false;
  if (!candidates.every((candidate) => {
    const mechanism = mechanismById.get(candidate.mechanism_id);
    if (!mechanism) return false;
    const roleFocus = [...candidate.support_artifact_ids, ...candidate.contradiction_artifact_ids]
      .map((id) => focusById.get(id));
    const supportFocus = candidate.support_artifact_ids.map((id) => focusById.get(id));
    const contradictionFocus = candidate.contradiction_artifact_ids.map((id) => focusById.get(id));
    const discriminatorFocus = focusArtifacts.filter((focus) => (
      focus.mechanism_id === candidate.mechanism_id
      && focus.observation_contract_id !== null
    ));
    if (supportFocus.length > 0 && !runtimeSupportContractSatisfied(
      mechanism,
      scope.expectedChain,
      supportFocus.flatMap((focus) => focus?.source_channels ?? []),
    )) return false;
    return roleFocus.every((focus) => (
      focus?.inspection_tool_id === mechanism.inspection_tool_id
      && focus.artifact_id.startsWith(mechanism.focus_artifact_prefix)
    ))
      && supportFocus.every((focus) => (
        focus?.stage === "vehicle_response"
        && focus.observation_contract_id === null
        && focus.source_artifact_ids.length === 1
        && focus.source_artifact_ids[0] !== opportunityIds[0]
      ))
      && contradictionFocus.every((focus) => (
        focus?.stage === "tire_platform_state"
        && focus.observation_contract_id === null
        && sameTexts(focus.source_artifact_ids, opportunityIds)
      ))
      && discriminatorFocus.length === 1
      && discriminatorFocus[0].observation_contract_id
        === mechanism.discriminator_observation_contract_ids[0]
      && discriminatorFocus[0].inspection_tool_id === mechanism.inspection_tool_id
      && discriminatorFocus[0].artifact_id.startsWith(mechanism.focus_artifact_prefix)
      && discriminatorFocus[0].polarity === "neutral"
      && discriminatorFocus[0].stage === "tire_platform_state"
      && sameTexts(discriminatorFocus[0].source_artifact_ids, opportunityIds);
  })) return false;
  const chainSourceIds = new Set(value.chain.flatMap((item) => item.source_artifact_ids));
  if (!focusArtifacts.every((item) => (
    item.source_artifact_ids.every((id) => chainSourceIds.has(id))
  ))) return false;
  for (const artifactId of [
    value.strongest_support_artifact_id,
    value.strongest_contradiction_artifact_id,
  ]) {
    if (artifactId !== null && !focusIds.has(artifactId)) return false;
  }
  const candidateDiscriminators = new Set(candidates.flatMap((item) => item.discriminator_contract_ids));
  const supportIds = new Set(candidates.flatMap((item) => item.support_artifact_ids));
  const contradictionIds = new Set(candidates.flatMap((item) => item.contradiction_artifact_ids));
  const hasSupportedCandidate = candidates.some((item) => item.relevance === "candidate");
  if ([...supportIds].some((item) => contradictionIds.has(item))) return false;
  if (!focusArtifacts.every((focus) => (
    supportIds.has(focus.artifact_id)
    || contradictionIds.has(focus.artifact_id)
    || (focus.observation_contract_id !== null && candidates.some((candidate) => (
      candidate.mechanism_id === focus.mechanism_id
      && candidate.discriminator_contract_ids.includes(focus.observation_contract_id as string)
    )))
  ))) return false;
  if (value.candidates.length > 0 && (
    value.performance_opportunity_ids.length !== 1
    ||
    value.next_discriminator_contract_id === null
    || value.strongest_contradiction_artifact_id === null
    || (hasSupportedCandidate && value.strongest_support_artifact_id === null)
    || (!hasSupportedCandidate && value.strongest_support_artifact_id !== null)
    || !candidateDiscriminators.has(value.next_discriminator_contract_id)
    || (value.strongest_support_artifact_id !== null
      && !supportIds.has(value.strongest_support_artifact_id))
    || !contradictionIds.has(value.strongest_contradiction_artifact_id)
    || (value.strongest_support_artifact_id !== null
      && focusById.get(value.strongest_support_artifact_id)?.polarity !== "support")
    || !["contradiction", "uncertainty"].includes(String(
      focusById.get(value.strongest_contradiction_artifact_id)?.polarity,
    ))
    || !value.focus_artifacts.some((item) => (
      item.observation_contract_id === value.next_discriminator_contract_id
      && item.polarity === "neutral"
      && (value.candidates as PerformanceMechanismCandidate[]).some((candidate) => (
        candidate.mechanism_id === item.mechanism_id
        && candidate.discriminator_contract_ids.includes(
          value.next_discriminator_contract_id as string,
        )
      ))
    ))
  )) return false;
  if (value.candidates.length === 0 && (
    value.strongest_support_artifact_id !== null
    || value.strongest_contradiction_artifact_id !== null
    || value.next_discriminator_contract_id !== null
  )) return false;
  const leadingCandidate = candidates.find((item) => item.relevance === "candidate")
    ?? candidates[0];
  if (leadingCandidate && (
    value.strongest_support_artifact_id !== (leadingCandidate.support_artifact_ids[0] ?? null)
    || value.strongest_contradiction_artifact_id
      !== leadingCandidate.contradiction_artifact_ids[0]
    || value.next_discriminator_contract_id
      !== leadingCandidate.discriminator_contract_ids[0]
  )) return false;
  return true;
}

export async function hasCanonicalPerformanceMechanismAssessmentDigest(
  value: unknown,
): Promise<boolean> {
  if (!record(value)
    || typeof value.p35_assessment_sha256 !== "string"
    || !SHA256.test(value.p35_assessment_sha256)) return false;
  const manifestBody: Record<string, unknown> = { ...p35RuntimeTrustManifest };
  delete manifestBody.runtime_trust_sha256;
  try {
    const [assessmentSha256, runtimeTrustSha256] = await Promise.all([
      canonicalPerformanceMechanismAssessmentSha256(value),
      canonicalJsonSha256(manifestBody),
    ]);
    if (assessmentSha256 !== value.p35_assessment_sha256
      || runtimeTrustSha256 !== P35_RUNTIME_TRUST_SHA256
      || !Array.isArray(value.candidates)
      || !Array.isArray(value.focus_artifacts)
      || !Array.isArray(value.performance_opportunity_ids)
      || value.performance_opportunity_ids.length > 1) return false;
    const opportunityId = value.performance_opportunity_ids[0];
    const supportIds = new Set<string>();
    const contradictionIds = new Set<string>();
    for (const candidate of value.candidates) {
      if (!record(candidate)
        || !Array.isArray(candidate.support_artifact_ids)
        || !Array.isArray(candidate.contradiction_artifact_ids)) return false;
      for (const id of candidate.support_artifact_ids) {
        if (typeof id !== "string") return false;
        supportIds.add(id);
      }
      for (const id of candidate.contradiction_artifact_ids) {
        if (typeof id !== "string") return false;
        contradictionIds.add(id);
      }
    }
    if (value.focus_artifacts.length > 0 && typeof opportunityId !== "string") return false;
    const selectedOpportunityId = opportunityId as string;
    const digestFocusArtifacts = value.focus_artifacts as unknown[];
    const expectedIds = await Promise.all(digestFocusArtifacts.map(async (focus) => {
      if (!record(focus)
        || typeof focus.artifact_id !== "string"
        || typeof focus.inspection_tool_id !== "string"
        || typeof focus.mechanism_id !== "string"
        || !Array.isArray(focus.source_artifact_ids)) return null;
      const prefix = `p35.focus.${focus.inspection_tool_id.replace(/^inspect_/, "")}:`;
      let parts: string[];
      if (supportIds.has(focus.artifact_id)) {
        if (focus.source_artifact_ids.length !== 1
          || typeof focus.source_artifact_ids[0] !== "string") return null;
        parts = [
          selectedOpportunityId,
          focus.mechanism_id,
          focus.source_artifact_ids[0],
          "support",
        ];
      } else if (contradictionIds.has(focus.artifact_id)) {
        parts = [
          selectedOpportunityId,
          focus.mechanism_id,
          "uncertainty",
        ];
      } else if (typeof focus.observation_contract_id === "string") {
        parts = [
          selectedOpportunityId,
          focus.mechanism_id,
          focus.observation_contract_id,
          "discriminator",
        ];
      } else return null;
      return `${prefix}${(await canonicalJsonSha256(parts)).slice(0, 24)}`;
    }));
    return expectedIds.every((expected, index) => (
      expected !== null
      && record(digestFocusArtifacts[index])
      && digestFocusArtifacts[index].artifact_id === expected
    ));
  } catch {
    return false;
  }
}

export async function canonicalPerformanceMechanismAssessmentSha256(
  value: unknown,
): Promise<string> {
  if (!record(value)) throw new TypeError("P35 assessment body must be an object.");
  const body = { ...value };
  delete body.p35_assessment_sha256;
  return canonicalJsonSha256(body, { pythonFloatKeys: P35_PYTHON_FLOAT_KEYS });
}
