import { canonicalJsonSha256 } from "./canonicalJsonSha256";
import type { components as OpenApiComponents } from "../types/openapi.generated";

type HandlingKnowledgeProjection =
  OpenApiComponents["schemas"]["HandlingKnowledgeProjection"];

const SCHEMA_VERSION = "p356.handling-knowledge.v1";
const ASSESSMENT_ID = /^hba_[0-9a-f]{24}$/;
const BRIDGE_ID = /^p351b_[0-9a-f]{24}$/;
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

const KNOWLEDGE_LEVELS: ReadonlySet<string> = new Set([
  "p19_testable_control",
  "measurable_hypothesis",
  "educational_knowledge",
  "unsupported_remove",
]);

const KNOWLEDGE_RELEVANCES: ReadonlySet<string> = new Set([
  "supported_candidate",
  "blocked_candidate",
  "knowledge_only",
]);

const APPLICABILITIES: ReadonlySet<string> = new Set([
  "applicable",
  "educational_only",
  "blocked_by_build",
  "unsupported",
]);

const NEXT_ACTION_KINDS: ReadonlySet<string> = new Set([
  "inspect_evidence",
  "measure",
  "p19_authorized_experiment",
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
 * Client trust boundary for the display-only handling-knowledge projection.
 *
 * The projection is a derived view over the exact Engineering Case. Any
 * payload whose case identity mismatches, whose authority drifts, whose
 * setup flag flips without an exact mirrored P19 control, or whose symptom
 * reference is not corroborated is rejected before it can reach Dial-In.
 */
export async function isHandlingKnowledgeProjection(
  payload: unknown,
  expectation: {
    runId: string;
    sessionId: string;
    setupId: string;
    caseId: string;
    caseRevision: string;
    caseSha256: string;
  },
): Promise<boolean> {
  if (!isRecord(payload)) return false;
  if (payload.schema_version !== SCHEMA_VERSION) return false;
  if (!isText(payload.projection_sha256) || !SHA.test(payload.projection_sha256)) return false;
  const body = { ...payload };
  delete body.projection_sha256;
  if (await canonicalJsonSha256(body) !== payload.projection_sha256) return false;
  if (payload.run_id !== expectation.runId) return false;
  if (payload.session_id !== expectation.sessionId) return false;
  if (payload.setup_id !== expectation.setupId) return false;
  if (payload.case_id !== expectation.caseId) return false;
  if (payload.case_revision_sha256 !== expectation.caseRevision) return false;
  if (payload.case_sha256 !== expectation.caseSha256) return false;
  if (typeof payload.assessment_id !== "string" || !ASSESSMENT_ID.test(payload.assessment_id)) return false;
  if (!isText(payload.phase)) return false;
  if (typeof payload.classification !== "string" || !CLASSIFICATIONS.has(payload.classification)) return false;
  if (payload.canonical_symptom_id != null && typeof payload.canonical_symptom_id !== "string") return false;
  if (payload.corroborated !== (payload.canonical_symptom_id != null)) return false;
  if (!isText(payload.observed_behavior) || !isText(payload.evidence_qualification)) return false;
  if (payload.authority !== "derived_observation_view") return false;
  if (payload.setup_authorized !== false) return false;
  if (payload.p19_authority_unchanged !== true) return false;

  if (!Array.isArray(payload.mechanisms)) return false;
  for (const mechanism of payload.mechanisms) {
    if (!isRecord(mechanism)) return false;
    if (!isText(mechanism.mechanism_id) || !mechanism.mechanism_id.startsWith("mechanism:")) return false;
    if (!isText(mechanism.label)) return false;
    if (typeof mechanism.relevance !== "string" || !MECHANISM_RELEVANCES.has(mechanism.relevance)) return false;
    if (mechanism.relevance === "blocked"
      && (!isStringArray(mechanism.missing_evidence) || mechanism.missing_evidence.length === 0)) return false;
    if (mechanism.support_declared !== false) return false;
  }

  if (!Array.isArray(payload.relevant_knowledge)) return false;
  for (const hypothesis of payload.relevant_knowledge) {
    if (!isRecord(hypothesis)) return false;
    if (typeof hypothesis.bridge_id !== "string" || !BRIDGE_ID.test(hypothesis.bridge_id)) return false;
    if (!isText(hypothesis.effect_id) || !isText(hypothesis.setup_area) || !isText(hypothesis.physical_role)) return false;
    if (typeof hypothesis.level !== "string" || !KNOWLEDGE_LEVELS.has(hypothesis.level)) return false;
    if (typeof hypothesis.relevance !== "string" || !KNOWLEDGE_RELEVANCES.has(hypothesis.relevance)) return false;
    if (typeof hypothesis.knowledge_applicability !== "string"
      || !APPLICABILITIES.has(hypothesis.knowledge_applicability)) return false;
    if (!isStringArray(hypothesis.p35_mechanism_ids) || !isStringArray(hypothesis.countereffect_ids)
      || !isStringArray(hypothesis.missing_evidence)) return false;
    const control = hypothesis.p19_control;
    if (control != null) {
      if (!isRecord(control)) return false;
      if (control.effect_id !== hypothesis.effect_id) return false;
      if (!isText(control.control_key) || !isText(control.workflow_id)
        || !isText(control.current_value) || !isText(control.proposed_value)) return false;
      if (control.authority !== "exact_p19_projection") return false;
      if (!isStringArray(control.source_event_ids) || control.source_event_ids.length === 0) return false;
    }
    if (hypothesis.setup_authorized !== (control != null)) return false;
    if (control == null && hypothesis.authority === "exact_p19_projection") return false;
  }

  if (!isStringArray(payload.countereffects) || !isStringArray(payload.evidence_status)) return false;
  if (!isStringArray(payload.next_evidence_channels)) return false;
  const nextAction = payload.next_action;
  if (!isRecord(nextAction)
    || typeof nextAction.kind !== "string" || !NEXT_ACTION_KINDS.has(nextAction.kind)
    || !isText(nextAction.instruction)) return false;
  if (nextAction.kind === "p19_authorized_experiment"
    && !payload.relevant_knowledge.some((hypothesis: Record<string, unknown>) => hypothesis.setup_authorized === true)) {
    return false;
  }
  return true;
}
