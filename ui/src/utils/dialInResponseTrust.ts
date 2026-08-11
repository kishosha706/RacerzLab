import type { DialInResponse, DialInSwing } from "../types/telemetry";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

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
const confidenceLabels = new Set(["Unsupported", "Needs phase", "Needs clarification", "Clear read"]);
const evidenceStrengthLevels = new Set(["unavailable", "capability_only", "observed_mechanism"]);
const evidenceStrengthReadiness = new Set(["blocked", "measurement_required", "test_hypothesis_ready"]);
const responseKeys = new Set([
  "run_id",
  "complaint_raw",
  "interpreted_symptom",
  "interpreted_phase",
  "balance_direction",
  "confidence_label",
  "readiness_label",
  "driver_message",
  "top_swings",
  "next_step",
  "clarification",
  "hidden_evidence_summary",
  "warnings",
  "evidence_state",
  "source_channels",
  "blocker_reasons",
  "evidence_strength",
]);
const swingKeys = new Set([
  "id",
  "title",
  "setup_area",
  "candidate_control_label",
  "related_control_keys",
  "influence_label",
  "strength_label",
  "risk_label",
  "mechanism_to_verify",
  "counter_effect_to_watch",
  "validate_with",
  "validate_with_labels",
  "watch_for",
  "watch_for_labels",
  "readiness_label",
  "measurement_needed",
  "evidence_state",
  "source_channels",
  "observed_evidence_flags",
  "supporting_event_ids",
  "blocker_reasons",
]);
const clarificationKeys = new Set(["needed", "question", "options"]);
const evidenceStrengthKeys = new Set([
  "level",
  "readiness",
  "capability_flags",
  "observed_mechanism_flags",
  "supporting_event_ids",
  "setup_test_ready",
  "requires_controlled_test",
  "reason",
]);
const forbiddenAuthorityKeys = new Set([
  "change_this",
  "direction_sign",
  "current_value",
  "current_value_label",
  "proposed_value",
  "proposed_value_label",
  "target_value",
  "one_change_test",
  "keep_if",
  "undo_if",
  "exact_change",
  "setup_authorized",
  "recommendation",
  "recommended_action",
  "click_delta",
  "suggested_value",
]);
const publicDriverMessage = "Engineering hypotheses only; no setup change is authorized from this response.";
const publicNextStep = "Collect matched, eligible repeats for the selected phase, then use the controlled P19 workflow to decide whether one setup test is justified.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCanonicalString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.trim() === value;
}

function isNullableCanonicalString(value: unknown): value is string | null | undefined {
  return value == null || isCanonicalString(value);
}

function isStringList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isCanonicalString);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: ReadonlySet<string>): boolean {
  return Object.keys(value).every((key) => allowed.has(key));
}

function hasForbiddenAuthorityKey(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(hasForbiddenAuthorityKey);
  if (!isRecord(value)) return false;
  return Object.entries(value).some(([key, nested]) => (
    forbiddenAuthorityKeys.has(key) || hasForbiddenAuthorityKey(nested)
  ));
}

function renderedSwingText(swing: Record<string, unknown>): unknown[] {
  return [
    swing.title,
    swing.setup_area,
    swing.candidate_control_label,
    swing.influence_label,
    swing.strength_label,
    swing.risk_label,
    swing.mechanism_to_verify,
    swing.counter_effect_to_watch,
    swing.measurement_needed,
    ...(Array.isArray(swing.related_control_keys) ? swing.related_control_keys : []),
    ...(Array.isArray(swing.validate_with) ? swing.validate_with : []),
    ...(Array.isArray(swing.validate_with_labels) ? swing.validate_with_labels : []),
    ...(Array.isArray(swing.watch_for) ? swing.watch_for : []),
    ...(Array.isArray(swing.watch_for_labels) ? swing.watch_for_labels : []),
    ...(Array.isArray(swing.source_channels) ? swing.source_channels : []),
    ...(Array.isArray(swing.observed_evidence_flags) ? swing.observed_evidence_flags : []),
    ...(Array.isArray(swing.blocker_reasons) ? swing.blocker_reasons : []),
  ];
}

function isDialInSwing(value: unknown): value is DialInSwing {
  if (!isRecord(value)) return false;
  return hasOnlyKeys(value, swingKeys)
    && isCanonicalString(value.id)
    && isCanonicalString(value.title)
    && isCanonicalString(value.setup_area)
    && isCanonicalString(value.candidate_control_label)
    && isStringList(value.related_control_keys)
    && isCanonicalString(value.influence_label)
    && isCanonicalString(value.strength_label)
    && isCanonicalString(value.risk_label)
    && isCanonicalString(value.mechanism_to_verify)
    && isCanonicalString(value.counter_effect_to_watch)
    && isStringList(value.validate_with)
    && (value.validate_with_labels === undefined || isStringList(value.validate_with_labels))
    && isStringList(value.watch_for)
    && (value.watch_for_labels === undefined || isStringList(value.watch_for_labels))
    && value.readiness_label === "Measurement required"
    && isCanonicalString(value.measurement_needed)
    && typeof value.evidence_state === "string"
    && evidenceStates.has(value.evidence_state)
    && isStringList(value.source_channels)
    && isStringList(value.observed_evidence_flags)
    && isStringList(value.supporting_event_ids)
    && isStringList(value.blocker_reasons)
    && !renderedSwingText(value).some(hasSetupAuthorityDirective);
}

function isClarification(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, clarificationKeys)) return false;
  if (
    typeof value.needed !== "boolean"
    || !isNullableCanonicalString(value.question)
    || !isStringList(value.options)
  ) return false;
  return ![value.question, ...value.options].some(hasSetupAuthorityDirective);
}

function isEvidenceStrength(value: unknown): boolean {
  if (!isRecord(value) || !hasOnlyKeys(value, evidenceStrengthKeys)) return false;
  return typeof value.level === "string"
    && evidenceStrengthLevels.has(value.level)
    && typeof value.readiness === "string"
    && evidenceStrengthReadiness.has(value.readiness)
    && isStringList(value.capability_flags)
    && isStringList(value.observed_mechanism_flags)
    && isStringList(value.supporting_event_ids)
    && value.setup_test_ready === false
    && value.requires_controlled_test === true
    && isCanonicalString(value.reason)
    && !hasSetupAuthorityDirective(value.reason);
}

function normalizeComplaint(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
}

export function isDialInHypothesisResponse(
  value: unknown,
  expectation: { runId: string; complaint: string },
): value is DialInResponse {
  if (
    !isRecord(value)
    || !hasOnlyKeys(value, responseKeys)
    || hasForbiddenAuthorityKey(value)
  ) return false;
  if (
    value.run_id !== expectation.runId
    || !isCanonicalString(value.complaint_raw)
    || normalizeComplaint(value.complaint_raw) !== normalizeComplaint(expectation.complaint)
    || !isNullableCanonicalString(value.interpreted_symptom)
    || !isNullableCanonicalString(value.interpreted_phase)
    || !isNullableCanonicalString(value.balance_direction)
    || typeof value.confidence_label !== "string"
    || !confidenceLabels.has(value.confidence_label)
    || value.readiness_label !== "Measurement required"
    || value.driver_message !== publicDriverMessage
    || value.next_step !== publicNextStep
    || !Array.isArray(value.top_swings)
    || !value.top_swings.every(isDialInSwing)
    || new Set(value.top_swings.map((item) => (item as Record<string, unknown>).id)).size !== value.top_swings.length
    || !isClarification(value.clarification)
    || !isStringList(value.warnings)
    || !isStringList(value.source_channels)
    || !isStringList(value.blocker_reasons)
    || typeof value.evidence_state !== "string"
    || !evidenceStates.has(value.evidence_state)
  ) return false;
  const renderedText = [
    value.interpreted_symptom,
    value.interpreted_phase,
    value.confidence_label,
    value.driver_message,
    value.next_step,
    ...value.warnings,
    ...value.source_channels,
    ...value.blocker_reasons,
  ];
  if (renderedText.some(hasSetupAuthorityDirective)) return false;
  if (value.evidence_strength != null && !isEvidenceStrength(value.evidence_strength)) return false;
  return true;
}
