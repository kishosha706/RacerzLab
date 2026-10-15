import type { components as OpenApiComponents } from "../types/openapi.generated";

type HandlingInvestigationProjection =
  OpenApiComponents["schemas"]["HandlingInvestigationProjection"];

const SCHEMA_VERSION = "p356.handling-investigation.v1";
const ASSESSMENT_ID = /^hba_[0-9a-f]{24}$/;
const SHA = /^[0-9a-f]{64}$/;

const CLASSIFICATIONS: ReadonlySet<string> = new Set([
  "no_significant_imbalance_qualified",
  "kinematic_residual_observation",
  "rotation_response_deficit",
  "rotation_response_excess",
  "mixed_phase_dependent",
  "transient_rotation_anomaly",
  "steering_response_anomaly",
  "steering_demand_anomaly",
  "inconclusive",
  "unavailable",
]);

const MECHANISM_RELEVANCES: ReadonlySet<string> = new Set([
  "applicable",
  "informed_by_observation",
  "blocked",
]);

const COMPONENT_RELEVANCES: ReadonlySet<string> = new Set([
  "mechanically_relevant",
  "observable",
  "supported",
  "contradicted",
  "unavailable",
]);

const EXPLANATION_STATES: ReadonlySet<string> = new Set([
  "supported",
  "contradicted",
  "plausible_unresolved",
  "not_observable",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * Client trust boundary for the derived handling-investigation projection.
 *
 * The projection is a derived, non-authoritative view. Any payload whose
 * authority drifts, whose setup flag flips, whose run/session/setup identity
 * mismatches, or whose symptom reference is not corroborated is rejected
 * before it can reach a workspace.
 */
export function isHandlingInvestigationProjection(
  payload: unknown,
  expectation: { runId: string; sessionId: string; setupId: string },
): payload is HandlingInvestigationProjection {
  if (!isRecord(payload)) return false;
  if (payload.schema_version !== SCHEMA_VERSION) return false;
  if (!isText(payload.projection_sha256) || !SHA.test(payload.projection_sha256)) return false;
  if (payload.run_id !== expectation.runId) return false;
  if (payload.session_id !== expectation.sessionId) return false;
  if (payload.setup_id !== expectation.setupId) return false;
  if (typeof payload.handling_report_classification !== "string"
    || !CLASSIFICATIONS.has(payload.handling_report_classification)) return false;
  if (payload.authority !== "derived_observation_view") return false;
  if (payload.setup_authorized !== false) return false;
  if (payload.p19_authority_unchanged !== true) return false;

  const refs = payload.assessment_refs;
  if (!Array.isArray(refs) || refs.length === 0) return false;
  const refIds = new Set<string>();
  for (const ref of refs) {
    if (!isRecord(ref)) return false;
    if (typeof ref.assessment_id !== "string" || !ASSESSMENT_ID.test(ref.assessment_id)) return false;
    if (refIds.has(ref.assessment_id)) return false;
    refIds.add(ref.assessment_id);
    if (ref.run_id !== expectation.runId) return false;
    if (!isText(ref.phase)) return false;
    if (typeof ref.classification !== "string" || !CLASSIFICATIONS.has(ref.classification)) return false;
    if (ref.canonical_symptom_id != null && typeof ref.canonical_symptom_id !== "string") return false;
    if (ref.corroborated !== (ref.canonical_symptom_id != null)) return false;
    if (!Array.isArray(ref.lap_numbers) || ref.lap_numbers.length === 0
      || !ref.lap_numbers.every((lap: unknown) => Number.isInteger(lap))) return false;
  }

  const { findings } = payload;
  if (!Array.isArray(findings) || findings.length === 0) return false;
  for (const finding of findings) {
    if (!isRecord(finding)) return false;
    if (typeof finding.assessment_id !== "string" || !refIds.has(finding.assessment_id)) return false;
    if (!isText(finding.phase) || !isText(finding.what) || !isText(finding.where)
      || !isText(finding.driver) || !isText(finding.response) || !isText(finding.next)) return false;
    if (!Array.isArray(finding.mechanisms)) return false;
    for (const mechanism of finding.mechanisms) {
      if (!isRecord(mechanism)) return false;
      if (!isText(mechanism.mechanism_id) || !mechanism.mechanism_id.startsWith("mechanism:")) return false;
      if (!isText(mechanism.label)) return false;
      if (typeof mechanism.relevance !== "string" || !MECHANISM_RELEVANCES.has(mechanism.relevance)) return false;
      if (mechanism.support_declared !== false) return false;
      if (!isStringArray(mechanism.missing_evidence)) return false;
    }
    if (!Array.isArray(finding.components)) return false;
    for (const component of finding.components) {
      if (!isRecord(component)) return false;
      if (!isText(component.component_id)) return false;
      if (typeof component.relevance !== "string" || !COMPONENT_RELEVANCES.has(component.relevance)) return false;
      if (component.malfunction_declared !== false) return false;
      if (component.source !== "p26_component_awareness") return false;
    }
    if (!Array.isArray(finding.performance)) return false;
    for (const association of finding.performance) {
      if (!isRecord(association)) return false;
      if (!isText(association.opportunity_id)) return false;
      if (association.causation_declared !== false) return false;
      if (!isText(association.wording) || !association.wording.includes("co-occurs")) return false;
    }
    if (!isStringArray(finding.contradictions) || !isStringArray(finding.uncertain)) return false;
    if (!isStringArray(finding.next_evidence_channels)) return false;
  }

  if (!Array.isArray(payload.evidence_dependence)
    || payload.evidence_dependence.length === 0
    || !payload.evidence_dependence.every(isText)) return false;
  return true;
}
