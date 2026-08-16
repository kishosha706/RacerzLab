import type {
  IntelligenceCitation,
  IntelligenceQueryResponse,
  RunIntelligenceReport,
} from "../types/intelligence";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

const sha256Pattern = /^[0-9a-f]{64}$/;
const citationPhases = new Set(["braking", "entry", "center", "exit", "straight"]);
const trackRegionPhases = new Set(["entry", "center", "exit", "straight"]);
const trackRegionConfidence = new Set(["section_geometry", "centerline_geometry"]);
const citationWorkspaces = new Set([
  "overview",
  "laps",
  "platform_trace",
  "speed_delta",
  "drag_scrub",
  "setup_impact",
  "dial_in",
]);
const evidenceStates = new Set([
  "measured",
  "calculated",
  "estimated_proxy",
  "observed_correlation",
  "controlled_test_effect",
  "unavailable",
  "blocked_by_context",
  "needs_confirmation",
]);
const positiveObservationStates = new Set([
  "measured", "calculated", "estimated_proxy", "observed_correlation",
  "controlled_test_effect",
]);
const mechanismKinds = new Set([
  "driver_execution", "braking_response", "corner_rotation", "tire_state",
  "damper_response", "platform_response", "resistance_scrub_like",
  "powertrain_response", "stint_trend", "sim_integrity", "unclassified",
]);
const actionKinds = new Set([
  "controlled_test",
  "measurement_mission",
  "driver_focus",
  "no_call",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length
    && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
}

function isCanonicalString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.trim() === value;
}

function isNullableCanonicalString(value: unknown): value is string | null {
  return value === null || isCanonicalString(value);
}

function isNullableEnum(value: unknown, values: ReadonlySet<string>): value is string | null {
  return value === null || (typeof value === "string" && values.has(value));
}

function hasSnapshotIdentity(value: Record<string, unknown>): boolean {
  return typeof value.reasoning_snapshot_sha256 === "string"
    && sha256Pattern.test(value.reasoning_snapshot_sha256)
    && isNullableCanonicalString(value.setup_id)
    && (value.setup_snapshot_sha256 === null || (
      typeof value.setup_snapshot_sha256 === "string"
      && sha256Pattern.test(value.setup_snapshot_sha256)
    ))
    && ((value.setup_id === null) === (value.setup_snapshot_sha256 === null));
}

function isCanonicalStringList(value: unknown): value is string[] {
  return Array.isArray(value)
    && value.every(isCanonicalString)
    && new Set(value).size === value.length;
}

function isFinitePercentage(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100;
}

function isObservationCitation(value: unknown): boolean {
  if (!isRecord(value) || !exactKeys(value, [
    "run_id", "lap_number", "setup_id", "lap_pct_start", "lap_pct_end",
    "lap_pct_peak", "phase", "evidence_state", "source_channels", "event_id",
    "telemetry_sample_count", "physical_segments",
  ])) return false;
  if (!Array.isArray(value.physical_segments)
    || value.physical_segments.length === 0
    || !value.physical_segments.every((segment) => isRecord(segment)
      && exactKeys(segment, ["start_pct", "end_pct", "sample_count"])
      && isFinitePercentage(segment.start_pct)
      && isFinitePercentage(segment.end_pct)
      && segment.start_pct <= segment.end_pct
      && Number.isInteger(segment.sample_count)
      && Number(segment.sample_count) >= 1)) return false;
  return isCanonicalString(value.run_id)
    && Number.isInteger(value.lap_number) && Number(value.lap_number) >= 0
    && isCanonicalString(value.setup_id)
    && isFinitePercentage(value.lap_pct_start)
    && isFinitePercentage(value.lap_pct_end)
    && isFinitePercentage(value.lap_pct_peak)
    && value.lap_pct_start <= value.lap_pct_peak
    && value.lap_pct_peak <= value.lap_pct_end
    && isCanonicalString(value.phase)
    && typeof value.evidence_state === "string"
    && positiveObservationStates.has(value.evidence_state)
    && isCanonicalStringList(value.source_channels)
    && value.source_channels.length > 0
    && isNullableCanonicalString(value.event_id)
    && Number.isInteger(value.telemetry_sample_count)
    && Number(value.telemetry_sample_count) >= 1
    && value.physical_segments.reduce(
      (total, segment) => total + Number((segment as Record<string, unknown>).sample_count),
      0,
    ) === value.telemetry_sample_count;
}

function isMechanismObservationReport(
  value: unknown,
  report: Record<string, unknown>,
): boolean {
  if (!isRecord(value) || !exactKeys(value, [
    "status", "run_id", "setup_id", "authority", "observations", "blocker_reasons",
  ]) || !["ready", "no_finding", "blocked"].includes(String(value.status))
    || value.run_id !== report.run_id
    || value.setup_id !== report.setup_id
    || value.authority !== "observation_only"
    || !Array.isArray(value.observations)
    || !isCanonicalStringList(value.blocker_reasons)) return false;
  return value.observations.every((observation) => {
    if (!isRecord(observation) || !exactKeys(observation, [
      "observation_id", "producer_id", "artifact_id", "source_run_ids",
      "source_setup_ids", "sample_coverage", "mechanism", "mechanism_kinds",
      "run_id", "setup_id", "lap_number", "phase", "lap_pct_start", "lap_pct_end",
      "lap_pct_peak", "summary", "evidence_state", "authority", "observational_label",
      "qualified", "source_channels", "required_channels", "supporting_evidence",
      "contradicting_evidence", "telemetry_sample_count", "repetition_count",
      "citations", "blocker_reasons",
    ])) return false;
    const qualified = observation.qualified === true;
    const scopeValues = [
      observation.lap_pct_start,
      observation.lap_pct_end,
      observation.lap_pct_peak,
    ];
    const scopeAbsent = scopeValues.every((item) => item === null);
    const scopeComplete = scopeValues.every(isFinitePercentage)
      && Number(observation.lap_pct_start) <= Number(observation.lap_pct_peak)
      && Number(observation.lap_pct_peak) <= Number(observation.lap_pct_end);
    return isCanonicalString(observation.observation_id)
      && isCanonicalString(observation.producer_id)
      && isCanonicalString(observation.artifact_id)
      && isCanonicalStringList(observation.source_run_ids)
      && observation.source_run_ids.length > 0
      && isCanonicalStringList(observation.source_setup_ids)
      && typeof observation.sample_coverage === "number"
      && Number.isFinite(observation.sample_coverage)
      && observation.sample_coverage >= 0 && observation.sample_coverage <= 1
      && typeof observation.mechanism === "string"
      && mechanismKinds.has(observation.mechanism)
      && isCanonicalStringList(observation.mechanism_kinds)
      && observation.mechanism_kinds.length > 0
      && observation.mechanism_kinds.every((item) => mechanismKinds.has(item))
      && observation.mechanism_kinds.includes(String(observation.mechanism))
      && observation.run_id === report.run_id
      && observation.source_run_ids.includes(String(observation.run_id))
      && observation.setup_id === report.setup_id
      && (observation.setup_id === null
        ? observation.source_setup_ids.length === 0
        : observation.source_setup_ids.includes(String(observation.setup_id)))
      && (observation.lap_number === null || (
        Number.isInteger(observation.lap_number) && Number(observation.lap_number) >= 0
      ))
      && isNullableCanonicalString(observation.phase)
      && (scopeAbsent || scopeComplete)
      && isCanonicalString(observation.summary)
      && typeof observation.evidence_state === "string"
      && evidenceStates.has(observation.evidence_state)
      && observation.authority === "observation_only"
      && observation.observational_label === "typed_mechanism_observation"
      && typeof observation.qualified === "boolean"
      && isCanonicalStringList(observation.source_channels)
      && isCanonicalStringList(observation.required_channels)
      && isCanonicalStringList(observation.supporting_evidence)
      && isCanonicalStringList(observation.contradicting_evidence)
      && Number.isInteger(observation.telemetry_sample_count)
      && Number(observation.telemetry_sample_count) >= 0
      && Number.isInteger(observation.repetition_count)
      && Number(observation.repetition_count) >= 0
      && Array.isArray(observation.citations)
      && observation.citations.every(isObservationCitation)
      && isCanonicalStringList(observation.blocker_reasons)
      && (qualified ? (
        positiveObservationStates.has(observation.evidence_state)
        && observation.setup_id !== null
        && observation.lap_number !== null
        && observation.phase !== null
        && scopeComplete
        && observation.blocker_reasons.length === 0
        && observation.source_channels.length > 0
        && observation.supporting_evidence.length > 0
        && Number(observation.telemetry_sample_count) >= 1
        && Number(observation.repetition_count) >= 1
        && observation.citations.length > 0
      ) : (
        observation.blocker_reasons.length > 0
        && observation.citations.length === 0
      ));
  });
}

function isIntelligenceAction(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) return false;
  const exactValues = [value.control_key, value.current_value, value.proposed_value];
  const semanticIdentity = [
    value.setup_effect_id,
    value.experiment_factor_id,
    value.direction_sign,
  ];
  const missionIdentityPaired = (value.mission_contract_id == null)
    === (value.mission_contract_sha256 == null);
  if (
    typeof value.kind !== "string"
    || !actionKinds.has(value.kind)
    || !isCanonicalString(value.title)
    || !isCanonicalString(value.instruction)
    || typeof value.setup_authorized !== "boolean"
    || typeof value.evidence_state !== "string"
    || !evidenceStates.has(value.evidence_state)
    || !isCanonicalStringList(value.source_event_ids)
    || !isCanonicalStringList(value.blocker_reasons)
    || !missionIdentityPaired
    || (value.mission_contract_id != null && !isCanonicalString(value.mission_contract_id))
    || (value.mission_contract_sha256 != null && (
      typeof value.mission_contract_sha256 !== "string"
      || !sha256Pattern.test(value.mission_contract_sha256)
    ))
  ) return false;
  if (!value.setup_authorized) {
    return exactValues.every((field) => field == null)
      && semanticIdentity.every((field) => field == null)
      && !hasSetupAuthorityDirective(value.title)
      && !hasSetupAuthorityDirective(value.instruction);
  }
  return value.kind === "controlled_test"
    && exactValues.every(isCanonicalString)
    && isCanonicalString(value.setup_effect_id)
    && isCanonicalString(value.experiment_factor_id)
    && (value.direction_sign === -1 || value.direction_sign === 1)
    && value.source_event_ids.length > 0
    && value.blocker_reasons.length === 0;
}

function isBoundVehicleSystemsProjection(
  value: unknown,
  report: Record<string, unknown>,
): boolean {
  return isRecord(value)
    && value.schema_version === "p26.component-awareness.v4"
    && value.run_id === report.run_id
    && value.session_id === report.session_id
    && value.reasoning_snapshot_sha256 === report.reasoning_snapshot_sha256
    && value.setup_id === report.setup_id
    && value.setup_snapshot_sha256 === report.setup_snapshot_sha256
    && value.authority === "p19_projection_only"
    && typeof value.setup_authorized === "boolean";
}

function isCitation(value: unknown): value is IntelligenceCitation {
  if (!isRecord(value)) return false;
  const regionPresent = value.track_region_id !== null;
  return isCanonicalString(value.citation_id)
    && isCanonicalString(value.label)
    && isCanonicalString(value.run_id)
    && (value.lap_number === null || (
      typeof value.lap_number === "number"
      && Number.isInteger(value.lap_number)
      && value.lap_number >= 1
    ))
    && (value.lap_pct === null || (
      typeof value.lap_pct === "number"
      && Number.isFinite(value.lap_pct)
      && value.lap_pct >= 0
      && value.lap_pct <= 100
    ))
    && isNullableCanonicalString(value.event_id)
    && typeof value.workspace === "string"
    && citationWorkspaces.has(value.workspace)
    && typeof value.evidence_state === "string"
    && evidenceStates.has(value.evidence_state)
    && isNullableEnum(value.phase, citationPhases)
    && isNullableCanonicalString(value.track_region_id)
    && isNullableCanonicalString(value.track_region_label)
    && isNullableEnum(value.track_region_phase, trackRegionPhases)
    && isNullableEnum(value.track_region_confidence, trackRegionConfidence)
    && regionPresent === (value.track_region_label !== null)
    && regionPresent === (value.track_region_confidence !== null)
    && (value.track_region_phase === null || regionPresent)
    && Array.isArray(value.source_channels)
    && value.source_channels.every(isCanonicalString)
    && new Set(value.source_channels).size === value.source_channels.length
    && typeof value.valid_for_tuning === "boolean";
}

export function isRunIntelligenceResponse(
  value: unknown,
  expectation: { runId: string; sessionId: string | null },
): value is RunIntelligenceReport {
  if (!isRecord(value) || !hasSnapshotIdentity(value) || !isRecord(value.briefing)) return false;
  const action = value.briefing.action;
  if (
    value.schema_version !== "p19.run-intelligence.v1"
    || value.run_id !== expectation.runId
    || value.session_id !== expectation.sessionId
    || !isIntelligenceAction(action)
    || (action.setup_authorized && value.setup_id === null)
  ) return false;
  if (value.mechanism_observations !== undefined
    && value.mechanism_observations !== null
    && !isMechanismObservationReport(value.mechanism_observations, value)) return false;
  if (value.vehicle_systems === null) return true;
  if (!isBoundVehicleSystemsProjection(value.vehicle_systems, value)) return false;
  const vehicleSystems = value.vehicle_systems as Record<string, unknown>;
  return vehicleSystems.setup_authorized === action.setup_authorized;
}

export function isIntelligenceQueryResponseBoundToReport(
  value: unknown,
  report: RunIntelligenceReport,
): value is IntelligenceQueryResponse {
  if (!isRecord(value) || !hasSnapshotIdentity(value)) return false;
  if (
    value.schema_version !== "p19.intelligence-query.v1"
    || value.run_id !== report.run_id
    || value.session_id !== report.session_id
    || value.reasoning_snapshot_sha256 !== report.reasoning_snapshot_sha256
    || value.setup_id !== report.setup_id
    || value.setup_snapshot_sha256 !== report.setup_snapshot_sha256
    || typeof value.action_authorized !== "boolean"
    || (value.action_authorized && value.setup_id === null)
    || !Array.isArray(value.scope_run_ids)
    || value.scope_run_ids.length === 0
    || !value.scope_run_ids.every(isCanonicalString)
    || new Set(value.scope_run_ids).size !== value.scope_run_ids.length
    || !value.scope_run_ids.includes(report.run_id)
    || !Array.isArray(value.citations)
    || !value.citations.every(isCitation)
  ) return false;
  if (!value.action_authorized) {
    const untrustedProse = [
      value.headline,
      value.answer,
      ...(Array.isArray(value.follow_up_questions) ? value.follow_up_questions : []),
    ];
    if (untrustedProse.some(hasSetupAuthorityDirective)) return false;
  }
  const scopeRunIds = value.scope_run_ids as string[];
  const citations = value.citations as IntelligenceCitation[];
  if (
    citations.some((citation) => !scopeRunIds.includes(citation.run_id))
    || new Set(citations.map((citation) => citation.citation_id)).size !== citations.length
  ) return false;
  if (!isNullableEnum(value.interpreted_phase, citationPhases)) return false;
  if (
    !isNullableCanonicalString(value.interpreted_track_region_id)
    || !isNullableCanonicalString(value.interpreted_track_region_label)
    || ((value.interpreted_track_region_id === null)
      !== (value.interpreted_track_region_label === null))
  ) return false;
  if (
    value.interpreted_phase !== null
    && citations.some((citation) => citation.phase !== value.interpreted_phase)
  ) return false;
  if (
    value.interpreted_track_region_id !== null
    && citations.some(
      (citation) => citation.track_region_id !== value.interpreted_track_region_id,
    )
  ) return false;
  return !(
    value.interpreted_track_region_id !== null
    && typeof value.interpreted_phase === "string"
    && trackRegionPhases.has(value.interpreted_phase)
    && citations.some(
      (citation) => citation.track_region_phase !== value.interpreted_phase,
    )
  );
}
