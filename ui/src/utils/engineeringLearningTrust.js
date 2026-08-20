import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";
import { canonicalJsonSha256 } from "./canonicalJsonSha256.ts";

const HASH = /^[0-9a-f]{64}$/;
const EXPERIENCE_ID = /^p33x_[0-9a-f]{24}$/;
const REFERENCE_ID = /^p33ref_[0-9a-f]{24}$/;
const OBJECTIVES = new Set([
  "qualifying_peak", "race_long_run", "tire_conservation", "driver_confidence",
  "traffic_robustness", "superspeedway_stability", "fuel_strategy",
]);
const TRANSFER_LEVELS = new Set(["exact", "compatible", "weak", "blocked"]);
const STRENGTHS = new Set([
  "single_case", "repeated_same_context", "repeated_multi_session", "controlled_repeated",
  "cross_context_supported", "conflicted", "insufficient",
]);
const DRIVER_METRICS = new Set([
  "brake_onset_consistency", "brake_release_timing_consistency", "steering_onset_consistency",
  "steering_workload", "correction_frequency", "throttle_pickup_timing", "throttle_realization",
  "line_repeatability", "phase_time_repeatability", "short_run_long_run_behavior",
  "traffic_execution", "controlled_test_execution_consistency", "driver_vehicle_separation",
]);
const EVIDENCE_STATES = new Set([
  "measured", "calculated", "estimated_proxy", "observed_correlation",
  "controlled_test_effect", "unavailable", "blocked_by_context", "needs_confirmation",
]);
const P33_FLOAT_KEYS = new Set([
  "observed_delta_s", "phase_effect_s", "carry_effect_s", "phase_time_effect_s",
  "elapsed_seconds", "lap_pct_start", "lap_pct_end", "average_tool_steps_before_resolution",
  "remaining_time_s", "fuel_laps_available",
]);
const UNSAFE_MEMORY_PROSE = [
  /\b(?:set|adjust|change)\s+[a-z][\w -]{0,48}\s+to\s+[-+]?\d/i,
  /\b(?:increase|decrease|raise|lower|add|remove)\s+[a-z][\w -]{0,48}\s+by\s+[-+]?\d/i,
  /\b(?:keep|undo)\s+(?:the|this)\s+(?:change|setup)\b/i,
  /\b(?:recommend|recommended|must|should)\s+(?:set|adjust|change|increase|decrease|raise|lower)\b/i,
  /\b(?:caused|causes|produced|generated|resulted in)\s+(?:the\s+)?(?:loss|gain|problem|handling)\b/i,
];
const FORBIDDEN_CAUSAL_MEMORY = /\b(?:caused?|due\s+to|because\s+of|responsible\s+for|proves?|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from)|creates?|drives?|drove|explains?|accounts?\s+for|stems?\s+from|comes?\s+from)\b[^.!?\n]{0,64}\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b|\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b[^.!?\n]{0,64}\b(?:caused?|due\s+to|because\s+of|responsible\s+for|driven\s+by|explained\s+by|attributable\s+to|came\s+from|result(?:ed|s|ing)?\s+from)\b|(?:confirms?|confirmed)\b[^.!?\n]{0,64}\b(?:cause|caused|created)/i;
const NEGATED_CAUSAL_MEMORY = /\b(?:does\s+not|do\s+not|did\s+not|cannot|can\s+not|is\s+not|are\s+not|was\s+not|were\s+not)\s+(?:caus(?:e|ed|es|ing)|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from)|create(?:d|s|ing)?|drive|drives|drove|explain(?:ed|s|ing)?|establish(?:ed|es|ing)?|prove(?:d|s|n|ing)?)\b[^.!?\n]{0,64}\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b/gi;

const record = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
const exactKeys = (value, keys) => record(value)
  && Object.keys(value).length === keys.length
  && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const integer = (value) => finite(value) && Number.isInteger(value);
const nonnegativeInteger = (value) => integer(value) && value >= 0;
const nonempty = (value) => typeof value === "string" && value.length > 0;
const nullableNonempty = (value) => value === null || nonempty(value);
const strings = (value) => Array.isArray(value) && value.every((item) => typeof item === "string");
const nonemptyStrings = (value) => strings(value) && value.every(nonempty);
const uniqueNonemptyStrings = (value) => nonemptyStrings(value) && new Set(value).size === value.length;
const hash = (value) => typeof value === "string" && HASH.test(value);
const experienceId = (value) => typeof value === "string" && EXPERIENCE_ID.test(value);
const member = (value, values) => typeof value === "string" && values.has(value);
const isoDate = (value) => typeof value === "string" && Number.isFinite(Date.parse(value));
const nullableFinite = (value) => value === null || finite(value);
const nullableBoolean = (value) => value === null || typeof value === "boolean";
const sameSetSubset = (values, allowed) => values.every((value) => allowed.has(value));
const ids = (items, getId) => {
  const values = items.map(getId);
  return values.every(nonempty) && new Set(values).size === values.length;
};

function safeMemoryText(value, requireNonempty = true) {
  if (typeof value !== "string" || (requireNonempty && value.length === 0)) return false;
  if (value !== value.split(/\s+/).join(" ")) return false;
  const causalScope = value.replace(NEGATED_CAUSAL_MEMORY, "explicit non-causal boundary");
  return !hasSetupAuthorityDirective(value)
    && !UNSAFE_MEMORY_PROSE.some((pattern) => pattern.test(value))
    && !FORBIDDEN_CAUSAL_MEMORY.test(causalScope);
}

const safeUniqueTexts = (value) => uniqueNonemptyStrings(value)
  && value.every((item) => safeMemoryText(item));

function validCounts(value) {
  const keys = [
    "observation_count", "independent_episode_count", "independent_workflow_count",
    "distinct_session_count", "distinct_context_count",
  ];
  return exactKeys(value, keys)
    && keys.every((key) => nonnegativeInteger(value[key]))
    && value.independent_episode_count <= value.observation_count
    && value.independent_workflow_count <= value.observation_count
    && value.distinct_session_count <= value.observation_count
    && value.distinct_context_count <= value.observation_count;
}

function validP19Cause(value) {
  return exactKeys(value, ["cause_id", "status", "ordinal_rank", "mechanism_family"])
    && nonempty(value.cause_id)
    && ["likely", "possible", "ruled_out", "unresolved"].includes(value.status)
    && integer(value.ordinal_rank) && value.ordinal_rank >= 1
    && nullableNonempty(value.mechanism_family);
}

function validP19Reasoning(value) {
  if (!exactKeys(value, [
    "reasoning_snapshot_sha256", "causes", "measurement_plan_kind", "discriminator_ids",
    "authority_level", "setup_authorized",
  ]) || !hash(value.reasoning_snapshot_sha256)
    || !Array.isArray(value.causes) || !value.causes.every(validP19Cause)
    || !ids(value.causes, (item) => item.cause_id)
    || !nonempty(value.measurement_plan_kind)
    || !uniqueNonemptyStrings(value.discriminator_ids)
    || !["observation", "measurement", "controlled_setup", "blocked"].includes(value.authority_level)
    || typeof value.setup_authorized !== "boolean") return false;
  return value.setup_authorized === (value.authority_level === "controlled_setup");
}

function validProblemFingerprint(value) {
  return exactKeys(value, [
    "problem_sha256", "physical_episode_id", "performance_opportunity_id", "phase",
    "physical_region", "time_origin_class", "carry_behavior", "driver_demand_state",
    "vehicle_response_state", "p20_mechanism_families", "p26_component_families",
    "traffic_context_state", "tire_stint_state", "objective", "source_artifact_ids",
  ])
    && hash(value.problem_sha256)
    && nullableNonempty(value.physical_episode_id)
    && nullableNonempty(value.performance_opportunity_id)
    && nonempty(value.phase)
    && nonempty(value.physical_region)
    && nonempty(value.time_origin_class)
    && nonempty(value.carry_behavior)
    && nonempty(value.driver_demand_state)
    && nonempty(value.vehicle_response_state)
    && uniqueNonemptyStrings(value.p20_mechanism_families)
    && uniqueNonemptyStrings(value.p26_component_families)
    && nonempty(value.traffic_context_state)
    && nonempty(value.tire_stint_state)
    && member(value.objective, OBJECTIVES)
    && uniqueNonemptyStrings(value.source_artifact_ids);
}

export function isP19ReasoningMemory(value) {
  return validP19Reasoning(value);
}

export function isProblemFingerprint(value) {
  return validProblemFingerprint(value);
}

function validDriverContribution(value) {
  return exactKeys(value, [
    "contribution_id", "metric", "tendency", "statement", "physical_episode_ids",
    "source_artifact_ids", "source_lap_count", "authority", "setup_authorized",
  ])
    && nonempty(value.contribution_id)
    && member(value.metric, DRIVER_METRICS)
    && ["repeatable_tendency", "context_dependent_tendency", "insufficient_history", "changed_behavior"].includes(value.tendency)
    && safeMemoryText(value.statement)
    && uniqueNonemptyStrings(value.physical_episode_ids)
    && uniqueNonemptyStrings(value.source_artifact_ids) && value.source_artifact_ids.length >= 1
    && nonnegativeInteger(value.source_lap_count)
    && value.authority === "driver_context_only"
    && value.setup_authorized === false;
}

function validPerformanceResponse(value) {
  if (!exactKeys(value, [
    "performance_opportunity_id", "observed_delta_s", "observed_direction", "attribution_state",
    "time_origin", "phase_effect_s", "carry_effect_s", "recovery_surrender",
    "source_response_record_id", "source_artifact_ids",
  ]) || !nullableNonempty(value.performance_opportunity_id)
    || !nullableFinite(value.observed_delta_s)
    || !["loss", "gain", "unavailable"].includes(value.observed_direction)
    || !["candidate_only", "blocked_by_traffic", "blocked_by_context", "unavailable"].includes(value.attribution_state)
    || !nonempty(value.time_origin) || !nullableFinite(value.phase_effect_s)
    || !nullableFinite(value.carry_effect_s) || !nonempty(value.recovery_surrender)
    || !nullableNonempty(value.source_response_record_id)
    || !uniqueNonemptyStrings(value.source_artifact_ids)) return false;
  if (value.observed_delta_s === null) {
    return value.observed_direction === "unavailable" && value.attribution_state === "unavailable";
  }
  if (value.attribution_state === "unavailable") return false;
  const expected = value.observed_delta_s < 0
    ? "gain"
    : value.observed_delta_s > 0 ? "loss" : "unavailable";
  return value.observed_direction === expected;
}

function validCarResponse(value) {
  if (!exactKeys(value, [
    "response_id", "component", "control", "direction", "magnitude_class",
    "expected_vehicle_response", "observed_vehicle_response", "p32_time_origin",
    "phase_time_effect_s", "carry_effect_s", "recovery_surrender", "countereffects",
    "p19_mechanism_assessment", "control_response_assessment", "policy_verdict",
    "source_workflow_id", "source_response_record_id", "response_expectation_contract_ids",
    "response_metric_delta_ids", "stage_response_artifact_ids", "response_phase",
    "response_speed_band_mps", "source_artifact_ids", "setup_authorized",
  ])) return false;
  const requiredText = [
    "response_id", "component", "control", "direction", "magnitude_class",
    "expected_vehicle_response", "observed_vehicle_response", "p32_time_origin",
    "recovery_surrender", "source_workflow_id",
  ];
  return requiredText.every((key) => nonempty(value[key]))
    && /^[a-z][a-z0-9_.:-]*$/.test(value.component)
    && /^[a-z][a-z0-9_.:-]*$/.test(value.control)
    && ["increase", "decrease", "unchanged", "unknown"].includes(value.direction)
    && ["adjacent", "small", "medium", "large", "unknown"].includes(value.magnitude_class)
    && safeMemoryText(value.expected_vehicle_response)
    && safeMemoryText(value.observed_vehicle_response)
    && safeMemoryText(value.recovery_surrender)
    && nullableFinite(value.phase_time_effect_s) && nullableFinite(value.carry_effect_s)
    && safeUniqueTexts(value.countereffects)
    && ["supported", "weakened", "unchanged", "inconclusive", "invalid"].includes(value.p19_mechanism_assessment)
    && ["matched", "missed", "inconclusive", "unavailable", "invalid"].includes(value.control_response_assessment)
    && ["keep", "undo", "retest", "invalid"].includes(value.policy_verdict)
    && nullableNonempty(value.source_response_record_id)
    && uniqueNonemptyStrings(value.response_expectation_contract_ids)
    && uniqueNonemptyStrings(value.response_metric_delta_ids)
    && Array.isArray(value.stage_response_artifact_ids)
    && (value.stage_response_artifact_ids.length === 0
      || JSON.stringify(value.stage_response_artifact_ids.map((item) => item[0])) === JSON.stringify(["A", "B", "A2"]))
    && value.stage_response_artifact_ids.every((item) => (
      Array.isArray(item) && item.length === 2 && uniqueNonemptyStrings(item[1])
    ))
    && (value.response_phase === null || nonempty(value.response_phase))
    && (value.response_speed_band_mps === null || (
      Array.isArray(value.response_speed_band_mps)
      && value.response_speed_band_mps.length === 2
      && value.response_speed_band_mps.every(Number.isFinite)
      && value.response_speed_band_mps[1] >= value.response_speed_band_mps[0]
    ))
    && uniqueNonemptyStrings(value.source_artifact_ids)
    && value.setup_authorized === false
    && (value.policy_verdict !== "undo" || value.countereffects.length > 0)
    && (value.policy_verdict !== "invalid" || (value.phase_time_effect_s === null && value.carry_effect_s === null));
}

function validInvestigation(value) {
  const keys = [
    "investigation_id", "started_at", "completed_at", "initial_cause_ids", "tools_inspected",
    "driver_question_ids", "driver_answers", "requested_measurement_ids", "completed_measurement_ids",
    "strongest_contradiction", "eliminated_cause_ids", "unresolved_cause_ids", "terminal_decision",
    "workflow_ids", "elapsed_seconds", "laps_consumed", "tool_steps_consumed",
    "driver_questions_consumed", "successful_discriminator_ids", "source_artifact_ids",
    "historical_retrieval_used", "historical_match_confirmed",
  ];
  if (!exactKeys(value, keys) || !nonempty(value.investigation_id)
    || !isoDate(value.started_at) || !isoDate(value.completed_at)
    || Date.parse(value.completed_at) < Date.parse(value.started_at)) return false;
  for (const key of [
    "initial_cause_ids", "driver_question_ids", "requested_measurement_ids",
    "completed_measurement_ids", "eliminated_cause_ids", "unresolved_cause_ids",
    "workflow_ids", "successful_discriminator_ids", "source_artifact_ids",
  ]) if (!uniqueNonemptyStrings(value[key])) return false;
  return strings(value.tools_inspected) && strings(value.driver_answers)
    && safeMemoryText(value.strongest_contradiction, false)
    && ["controlled_test", "retest", "no_call", "driver_focus", "measurement_only", "abandoned"].includes(value.terminal_decision)
    && finite(value.elapsed_seconds) && value.elapsed_seconds >= 0
    && nonnegativeInteger(value.laps_consumed)
    && nonnegativeInteger(value.tool_steps_consumed) && value.tool_steps_consumed === value.tools_inspected.length
    && nonnegativeInteger(value.driver_questions_consumed) && value.driver_questions_consumed === value.driver_question_ids.length
    && sameSetSubset(value.completed_measurement_ids, new Set(value.requested_measurement_ids))
    && sameSetSubset(value.successful_discriminator_ids, new Set(value.completed_measurement_ids))
    && sameSetSubset(value.successful_discriminator_ids, new Set(value.tools_inspected))
    && typeof value.historical_retrieval_used === "boolean"
    && nullableBoolean(value.historical_match_confirmed);
}

function validMindChange(value) {
  const uniqueFields = [
    "new_artifact_ids", "causes_promoted", "causes_demoted", "causes_ruled_out",
  ];
  if (!exactKeys(value, [
    "mind_change_id", "before_reasoning", "after_reasoning", "new_evidence_states", ...uniqueFields,
    "measurement_discriminator_id", "evidence_discriminated", "driver_question_involved",
    "controlled_evidence_involved", "context_gate_involved",
  ]) || !nonempty(value.mind_change_id)
    || !validP19Reasoning(value.before_reasoning) || !validP19Reasoning(value.after_reasoning)
    || value.before_reasoning.reasoning_snapshot_sha256 === value.after_reasoning.reasoning_snapshot_sha256
    || !uniqueFields.every((key) => uniqueNonemptyStrings(value[key]))
    || value.new_artifact_ids.length < 1 || !nonemptyStrings(value.new_evidence_states)
    || value.new_evidence_states.length !== value.new_artifact_ids.length
    || !nullableNonempty(value.measurement_discriminator_id)
    || !["evidence_discriminated", "driver_question_involved", "controlled_evidence_involved", "context_gate_involved"]
      .every((key) => typeof value[key] === "boolean")) return false;
  return value.evidence_discriminated
    ? value.measurement_discriminator_id !== null
    : value.measurement_discriminator_id === null;
}

function validDeadEnd(value) {
  return exactKeys(value, [
    "dead_end_id", "kind", "tool_id", "component_family", "control", "statement",
    "source_artifact_ids", "source_workflow_ids", "current_evidence_may_override", "authority",
  ])
    && nonempty(value.dead_end_id)
    && [
      "failed_investigation", "non_discriminating_measurement", "repeated_no_finding_tool",
      "repeated_undo_policy", "irrelevant_component_family", "context_invalidated_comparison",
    ].includes(value.kind)
    && nullableNonempty(value.tool_id) && nullableNonempty(value.component_family) && nullableNonempty(value.control)
    && safeMemoryText(value.statement)
    && uniqueNonemptyStrings(value.source_artifact_ids)
    && uniqueNonemptyStrings(value.source_workflow_ids)
    && value.current_evidence_may_override === true
    && value.authority === "attention_only";
}

function validTransfer(value) {
  if (!exactKeys(value, [
    "experience_id", "level", "matching_dimensions", "mismatched_dimensions",
    "drift_reasons", "blocker_reasons",
  ]) || !experienceId(value.experience_id) || !member(value.level, TRANSFER_LEVELS)) return false;
  for (const key of ["matching_dimensions", "mismatched_dimensions", "drift_reasons", "blocker_reasons"])
    if (!uniqueNonemptyStrings(value[key])) return false;
  if (value.level === "exact" && (value.mismatched_dimensions.length || value.drift_reasons.length || value.blocker_reasons.length)) return false;
  return value.level !== "blocked" || value.blocker_reasons.length > 0;
}

function validSourceProvenance(value) {
  if (!exactKeys(value, [
    "provenance_sha256", "artifact_id", "producer_id", "run_id", "session_id", "setup_id",
    "setup_snapshot_sha256", "build_context_sha256", "lap_numbers", "lap_pct_start",
    "lap_pct_end", "phase", "source_channels", "evidence_state", "polarity",
  ]) || !hash(value.provenance_sha256)
    || !["artifact_id", "producer_id", "run_id", "session_id", "setup_id"].every((key) => nonempty(value[key]))
    || !hash(value.setup_snapshot_sha256) || !hash(value.build_context_sha256)
    || !Array.isArray(value.lap_numbers)
    || !value.lap_numbers.every((lap) => nonnegativeInteger(lap))
    || new Set(value.lap_numbers).size !== value.lap_numbers.length
    || !nullableFinite(value.lap_pct_start) || !nullableFinite(value.lap_pct_end)
    || ((value.lap_pct_start === null) !== (value.lap_pct_end === null))
    || (value.lap_pct_start !== null && (
      value.lap_pct_start < 0 || value.lap_pct_start > 100
      || value.lap_pct_end < value.lap_pct_start || value.lap_pct_end > 100
    ))
    || !nullableNonempty(value.phase) || !uniqueNonemptyStrings(value.source_channels)
    || !member(value.evidence_state, EVIDENCE_STATES)
    || !["support", "contradiction", "neutral"].includes(value.polarity)) return false;
  return true;
}

function validEvidenceReference(value) {
  return exactKeys(value, [
    "reference_id", "experience_id", "provenance", "state", "blocker_reasons",
    "authority", "setup_authorized",
  ])
    && typeof value.reference_id === "string" && REFERENCE_ID.test(value.reference_id)
    && experienceId(value.experience_id) && validSourceProvenance(value.provenance)
    && ["available", "unavailable"].includes(value.state)
    && safeUniqueTexts(value.blocker_reasons)
    && (value.state === "available" ? value.blocker_reasons.length === 0 : value.blocker_reasons.length > 0)
    && value.authority === "attention_only" && value.setup_authorized === false;
}

function validRecurrence(value) {
  if (!exactKeys(value, [
    "recurrence_id", "classification", "problem_sha256s", "experience_ids", "investigation_ids",
    "statement", "useful_discriminator", "prior_dead_end", "strongest_contradiction", "transfer",
    "counts", "strength", "authority", "setup_authorized",
  ]) || !nonempty(value.recurrence_id)
    || !["new_problem", "possible_recurrence", "strong_recurrence", "exact_context_recurrence"].includes(value.classification)
    || !uniqueNonemptyStrings(value.problem_sha256s) || value.problem_sha256s.length < 1
    || !uniqueNonemptyStrings(value.experience_ids) || !uniqueNonemptyStrings(value.investigation_ids)
    || !safeMemoryText(value.statement)
    || !(value.useful_discriminator === null || safeMemoryText(value.useful_discriminator))
    || !(value.prior_dead_end === null || safeMemoryText(value.prior_dead_end))
    || !safeMemoryText(value.strongest_contradiction, false)
    || !(value.transfer === null || validTransfer(value.transfer))
    || !validCounts(value.counts) || !member(value.strength, STRENGTHS)
    || value.authority !== "attention_only" || value.setup_authorized !== false) return false;
  if (value.classification === "new_problem" && value.experience_ids.length) return false;
  return !["strong_recurrence", "exact_context_recurrence"].includes(value.classification)
    || value.counts.independent_episode_count >= 2
    || value.counts.independent_workflow_count >= 2;
}

function validDriverFingerprint(value) {
  if (!(exactKeys(value, [
    "fingerprint_id", "driver_id", "transfer_level", "state", "tendencies", "counts",
    "source_experience_ids", "contradictions", "authority", "setup_authorized",
  ])
    && nonempty(value.fingerprint_id) && nonempty(value.driver_id)
    && member(value.transfer_level, TRANSFER_LEVELS)
    && ["repeatable_tendency", "context_dependent_tendency", "insufficient_history", "changed_behavior"].includes(value.state)
    && Array.isArray(value.tendencies) && value.tendencies.every(validDriverContribution)
    && validCounts(value.counts) && uniqueNonemptyStrings(value.source_experience_ids)
    && uniqueNonemptyStrings(value.contradictions)
    && value.authority === "driver_context_only" && value.setup_authorized === false
    && (value.state !== "insufficient_history" || value.tendencies.length === 0))) return false;
  if (!value.tendencies.every((item) => item.tendency === value.state)) return false;
  return !["repeatable_tendency", "changed_behavior"].includes(value.state)
    || value.counts.independent_episode_count >= 2
    || value.counts.independent_workflow_count >= 2;
}

function validCarFingerprint(value) {
  return exactKeys(value, [
    "fingerprint_id", "transfer_level", "response", "counts", "source_experience_ids",
    "source_workflow_ids", "contradictions", "statement", "authority", "setup_authorized",
  ])
    && nonempty(value.fingerprint_id) && member(value.transfer_level, TRANSFER_LEVELS)
    && validCarResponse(value.response) && validCounts(value.counts)
    && uniqueNonemptyStrings(value.source_experience_ids) && value.source_experience_ids.length >= 1
    && uniqueNonemptyStrings(value.source_workflow_ids) && value.source_workflow_ids.length >= 1
    && value.counts.independent_workflow_count >= 1
    && value.counts.independent_workflow_count === value.source_workflow_ids.length
    && uniqueNonemptyStrings(value.contradictions) && safeMemoryText(value.statement)
    && value.authority === "controlled_history_only" && value.setup_authorized === false;
}

function validInvestigationOutcome(value) {
  return exactKeys(value, ["outcome_id", "experience_id", "transfer_level", "outcome", "counts", "useful", "explanation", "authority"])
    && nonempty(value.outcome_id) && experienceId(value.experience_id)
    && member(value.transfer_level, TRANSFER_LEVELS) && validInvestigation(value.outcome)
    && validCounts(value.counts) && typeof value.useful === "boolean"
    && safeMemoryText(value.explanation) && value.authority === "attention_only";
}

function validMindChangeRecord(value) {
  return exactKeys(value, ["experience_id", "transfer_level", "fact", "statement", "authority"])
    && experienceId(value.experience_id) && member(value.transfer_level, TRANSFER_LEVELS)
    && validMindChange(value.fact) && safeMemoryText(value.statement)
    && value.authority === "attention_only";
}

function validDeadEndRecord(value) {
  if (!(exactKeys(value, [
    "experience_ids", "transfer_level", "fact", "counts", "may_deprioritize_within_band",
    "may_veto_current_evidence",
  ])
    && uniqueNonemptyStrings(value.experience_ids) && value.experience_ids.length >= 1
    && member(value.transfer_level, TRANSFER_LEVELS) && validDeadEnd(value.fact)
    && validCounts(value.counts) && typeof value.may_deprioritize_within_band === "boolean"
    && value.may_veto_current_evidence === false)) return false;
  return !value.may_deprioritize_within_band || (
    ["exact", "compatible"].includes(value.transfer_level)
    && (value.counts.independent_episode_count >= 2
      || value.counts.independent_workflow_count >= 2)
  );
}

function validAttention(value) {
  return exactKeys(value, [
    "tool_id", "safety_band", "learned_rank_within_band", "baseline_rank_within_band", "reason",
    "transfer_level", "source_experience_ids", "investigation_count", "session_count",
    "independent_workflow_count", "authority",
  ])
    && nonempty(value.tool_id) && nonempty(value.safety_band)
    && integer(value.learned_rank_within_band) && value.learned_rank_within_band >= 1
    && integer(value.baseline_rank_within_band) && value.baseline_rank_within_band >= 1
    && safeMemoryText(value.reason) && ["exact", "compatible"].includes(value.transfer_level)
    && uniqueNonemptyStrings(value.source_experience_ids) && value.source_experience_ids.length >= 1
    && value.source_experience_ids.length >= 2
    && integer(value.investigation_count) && value.investigation_count >= 2
    && integer(value.session_count) && value.session_count >= 1
    && nonnegativeInteger(value.independent_workflow_count)
    && value.authority === "attention_only";
}

function validLedger(value) {
  const countKeys = [
    "investigations_opened", "investigations_resolved", "no_call_outcomes", "driver_focus_outcomes",
    "measurement_missions", "controlled_tests", "keep_outcomes", "undo_outcomes", "retest_outcomes",
    "laps_consumed_before_resolution", "questions_asked", "recurring_problem_count",
    "recurrence_resolved_faster_count",
  ];
  return exactKeys(value, [
    ...countKeys.slice(0, 9), "average_tool_steps_before_resolution",
    ...countKeys.slice(9), "repeated_dead_end_tools", "successful_discriminators",
    "claims_lap_time_improvement",
  ])
    && countKeys.every((key) => nonnegativeInteger(value[key]))
    && (value.average_tool_steps_before_resolution === null
      || (finite(value.average_tool_steps_before_resolution) && value.average_tool_steps_before_resolution >= 0))
    && uniqueNonemptyStrings(value.repeated_dead_end_tools)
    && uniqueNonemptyStrings(value.successful_discriminators)
    && value.claims_lap_time_improvement === false
    && value.investigations_resolved <= value.investigations_opened;
}

function validBrief(value) {
  if (!exactKeys(value, [
    "state", "what_we_learned", "what_changed_our_mind", "what_did_not_work",
    "next_attention", "blocker_reasons", "authority", "setup_authorized",
  ]) || !["available", "insufficient_history", "blocked"].includes(value.state)
    || !["what_we_learned", "what_changed_our_mind", "what_did_not_work", "next_attention", "blocker_reasons"]
      .every((key) => safeUniqueTexts(value[key]))
    || value.authority !== "attention_only" || value.setup_authorized !== false) return false;
  const content = value.what_we_learned.length || value.what_changed_our_mind.length
    || value.what_did_not_work.length || value.next_attention.length;
  return value.state === "available"
    ? Boolean(content)
    : !content && value.blocker_reasons.length > 0;
}

/** Return every telemetry artifact identity cited by the trusted projection. */
export function learningSourceArtifactIds(value) {
  if (!record(value) || !Array.isArray(value.evidence_references)) return [];
  return [...new Set(value.evidence_references
    .map((item) => item?.provenance?.artifact_id)
    .filter(nonempty))];
}

export function canonicalEngineeringLearningSha256(value) {
  return canonicalJsonSha256(value, { pythonFloatKeys: P33_FLOAT_KEYS });
}

/**
 * Recompute every content-derived P33 identity before an API response becomes
 * trusted.  The synchronous mirror below owns shape and semantic containment;
 * this async pass owns the canonical Python-compatible digest bindings.
 */
export async function hasCanonicalEngineeringLearningDigests(value) {
  if (!record(value) || !Array.isArray(value.evidence_references)) return false;
  try {
    const projection = { ...value };
    delete projection.projection_sha256;
    if (await canonicalEngineeringLearningSha256(projection) !== value.projection_sha256) return false;
    for (const reference of value.evidence_references) {
      if (!record(reference) || !record(reference.provenance)) return false;
      const provenance = { ...reference.provenance };
      delete provenance.provenance_sha256;
      const provenanceHash = await canonicalEngineeringLearningSha256(provenance);
      if (provenanceHash !== reference.provenance.provenance_sha256) return false;
      const referenceHash = await canonicalJsonSha256({
        experience_id: reference.experience_id,
        provenance_sha256: reference.provenance.provenance_sha256,
      });
      if (reference.reference_id !== `p33ref_${referenceHash.slice(0, 24)}`) return false;
    }
    return true;
  } catch {
    return false;
  }
}

/**
 * Deep fail-closed mirror for `CrewChiefLearningPrior`.
 * The scope binds the nested projection to the atomic workspace identity.
 */
export function isCrewChiefLearningPrior(value, scope) {
  if (!exactKeys(value, [
    "schema_version", "projection_sha256", "history_revision", "run_id", "session_id", "objective_id",
    "selected_scope_hash", "p19_reasoning_snapshot_sha256", "p32_projection_sha256",
    "current_context_sha256", "current_problem_sha256", "state", "recurrence",
    "useful_prior_investigations", "known_dead_ends", "driver_tendencies", "car_response_history",
    "mind_change_history", "recommended_attention_order", "context_transfers", "evidence_references", "context_transfer_level",
    "strength", "counts", "ledger", "post_run_brief", "blocker_reasons", "authority",
    "setup_authorized", "p19_rank_modified",
  ]) || !record(scope)
    || value.schema_version !== "p33.engineering-learning.v1"
    || value.projection_sha256 !== scope.projectionHash || !hash(value.projection_sha256)
    || value.history_revision !== scope.historyRevision || !hash(value.history_revision)
    || value.run_id !== scope.runId || value.session_id !== scope.sessionId
    || value.objective_id !== scope.objectiveId || !member(value.objective_id, OBJECTIVES)
    || value.selected_scope_hash !== scope.selectedScopeHash || !hash(value.selected_scope_hash)
    || value.p19_reasoning_snapshot_sha256 !== scope.p19Hash || !hash(value.p19_reasoning_snapshot_sha256)
    || value.p32_projection_sha256 !== scope.p32Hash || !hash(value.p32_projection_sha256)
    || !hash(value.current_context_sha256) || !hash(value.current_problem_sha256)
    || !["available", "insufficient_history", "blocked"].includes(value.state)
    || !validRecurrence(value.recurrence)
    || !Array.isArray(value.useful_prior_investigations) || !value.useful_prior_investigations.every(validInvestigationOutcome)
    || !Array.isArray(value.known_dead_ends) || !value.known_dead_ends.every(validDeadEndRecord)
    || !Array.isArray(value.driver_tendencies) || !value.driver_tendencies.every(validDriverFingerprint)
    || !Array.isArray(value.car_response_history) || !value.car_response_history.every(validCarFingerprint)
    || !Array.isArray(value.mind_change_history) || !value.mind_change_history.every(validMindChangeRecord)
    || !Array.isArray(value.recommended_attention_order) || !value.recommended_attention_order.every(validAttention)
    || !Array.isArray(value.context_transfers) || !value.context_transfers.every(validTransfer)
    || !Array.isArray(value.evidence_references) || !value.evidence_references.every(validEvidenceReference)
    || !member(value.context_transfer_level, TRANSFER_LEVELS) || !member(value.strength, STRENGTHS)
    || !validCounts(value.counts) || !validLedger(value.ledger) || !validBrief(value.post_run_brief)
    || !safeUniqueTexts(value.blocker_reasons)
    || value.authority !== "attention_only" || value.setup_authorized !== false || value.p19_rank_modified !== false
    || !ids(value.useful_prior_investigations, (item) => item.outcome_id)
    || !ids(value.known_dead_ends, (item) => item.fact.dead_end_id)
    || !ids(value.driver_tendencies, (item) => item.fingerprint_id)
    || !ids(value.car_response_history, (item) => item.fingerprint_id)
    || !ids(value.mind_change_history, (item) => item.fact.mind_change_id)
    || !ids(value.recommended_attention_order, (item) => item.tool_id)
    || !ids(value.context_transfers, (item) => item.experience_id)
    || !ids(value.evidence_references, (item) => item.reference_id)) return false;
  const surfacedExperienceIds = new Set([
    ...value.useful_prior_investigations.map((item) => item.experience_id),
    ...value.known_dead_ends.flatMap((item) => item.experience_ids),
    ...value.driver_tendencies.flatMap((item) => item.source_experience_ids),
    ...value.car_response_history.flatMap((item) => item.source_experience_ids),
    ...value.mind_change_history.map((item) => item.experience_id),
  ]);
  if (value.evidence_references.some((item) => !surfacedExperienceIds.has(item.experience_id))) return false;
  for (const mindChange of value.mind_change_history) {
    if (!mindChange.fact.evidence_discriminated) continue;
    const matchingOutcomes = value.useful_prior_investigations.filter(
      (item) => item.experience_id === mindChange.experience_id,
    );
    if (matchingOutcomes.length !== 1) return false;
    const discriminatorId = mindChange.fact.measurement_discriminator_id;
    if (!matchingOutcomes[0].outcome.successful_discriminator_ids.includes(discriminatorId)) return false;
  }
  const memoryItems = value.useful_prior_investigations.length + value.known_dead_ends.length
    + value.driver_tendencies.length + value.car_response_history.length + value.mind_change_history.length;
  if (value.state === "available" && memoryItems === 0) return false;
  if (value.state === "insufficient_history"
    && (memoryItems || value.recommended_attention_order.length || !value.blocker_reasons.length)) return false;
  if (value.state === "blocked" && (value.recommended_attention_order.length || !value.blocker_reasons.length)) return false;
  if (["weak", "blocked"].includes(value.context_transfer_level) && value.recommended_attention_order.length) return false;
  return true;
}
