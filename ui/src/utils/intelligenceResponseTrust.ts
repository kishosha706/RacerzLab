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
const actionKinds = new Set([
  "controlled_test",
  "measurement_mission",
  "driver_focus",
  "no_call",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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

function isIntelligenceAction(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) return false;
  const exactValues = [value.control_key, value.current_value, value.proposed_value];
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
      && !hasSetupAuthorityDirective(value.title)
      && !hasSetupAuthorityDirective(value.instruction);
  }
  return value.kind === "controlled_test"
    && exactValues.every(isCanonicalString)
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
