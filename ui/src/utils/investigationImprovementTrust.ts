import type {
  InvestigationAdaptationContext,
  InvestigationDecision,
  InvestigationImprovementProjection,
  InvestigationImprovementReadiness,
  InvestigationNegativeControlEvidence,
  InvestigationP19CauseState,
  PairedInvestigationComparison,
  PairedInvestigationDecision,
} from "../types/investigationImprovement";
import type { CrewChiefEvidenceEntry } from "../types/crewChief";
import type { CrewChiefLearningPrior } from "../types/engineeringLearning";
import { canonicalJsonSha256 } from "./canonicalJsonSha256.ts";
import { canonicalEngineeringLearningSha256 } from "./engineeringLearningTrust.js";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

const HASH = /^[0-9a-f]{64}$/;
const PAIR_ID = /^p34pair_[0-9a-f]{24}$/;
const POLICY_ID = /^p34pol_[0-9a-f]{24}$/;
const PROTOCOL_ID = /^p34proto_[0-9a-f]{24}$/;
const ACTIVATION_ID = /^p34act_[0-9a-f]{24}$/;
const COMPARISON_ID = /^p34cmp_[0-9a-f]{24}$/;
const CERTIFICATE_ID = /^p34out_[0-9a-f]{24}$/;
const DISCRIMINATOR_ID = /^p34disc_[0-9a-f]{24}$/;
const FOLLOWUP_ID = /^p34follow_[0-9a-f]{24}$/;
const P33_RECORD_ID = /^p33x_[0-9a-f]{24}$/;

const FROZEN_BASELINE_POLICY = {
  id: "p34pol_48190cf9a560de6fae1bb655",
  sha256: "48190cf9a560de6fae1bb655fe365b41478038825653743b2a391d62ea788709",
} as const;
const FROZEN_SHADOW_POLICY = {
  id: "p34pol_de720756ba383ec92910e64e",
  sha256: "de720756ba383ec92910e64e6360685d9d0f900adb4e5f9156db4488b3e55198",
} as const;
const FROZEN_LIMITED_POLICY = {
  id: "p34pol_d9e85250e6c0f43d3eadb5c7",
  sha256: "d9e85250e6c0f43d3eadb5c7aad06fd257e23956d3fb0bcba5b586b17b7a0795",
} as const;
const FROZEN_ACTIVATION_PROTOCOL = {
  id: "p34proto_487dd9698e01a7f77d493d01",
  sha256: "487dd9698e01a7f77d493d011e4f0ec0246ba0ed7efdaea17ef164cbc7a8fd61",
  frozenAt: "2026-08-15T08:12:46Z",
} as const;
const PERFORMANCE_REORDER_GROUP = [
  "inspect_lap_time_opportunity",
  "inspect_time_loss_origin",
  "inspect_corner_performance_chain",
  "inspect_exit_carry",
  "inspect_path_efficiency",
  "inspect_driver_vehicle_separation",
  "inspect_track_demand",
] as const;
// P34's frozen decision cohort predates P35. P35 remains part of the current
// workspace truth hash, but it cannot retroactively change P34 tool/artifact
// availability or authority-revision inputs.
const P35_INSPECTION_TOOL_IDS = new Set([
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
]);
const FROZEN_TOOL_PRIORITY = new Map<string, string>([
  ["inspect_data_quality", "identity_integrity"],
  ["inspect_lap_context", "context_qualification"],
  ...PERFORMANCE_REORDER_GROUP.map((tool) => [tool, "driver_car_confounders"] as const),
  ["inspect_driver_execution", "driver_car_confounders"],
  ["inspect_p19_causes", "strongest_contradiction"],
  ["inspect_mechanism_episodes", "unresolved_p19_mechanisms"],
  ["inspect_component_performance_link", "component_family_separation"],
  ["inspect_component_state", "component_family_separation"],
  ["inspect_controlled_history", "exact_history"],
  ["inspect_objective_tradeoff", "exact_history"],
  ["inspect_measurement_debt", "measurement_debt"],
]);
const QUALIFIED_ARTIFACT_STATES = new Set([
  "measured", "calculated", "controlled_test_effect",
]);
const P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS = new Set([
  "track", "track_configuration", "package_type", "phase",
  "physical_region", "objective", "speed_load_band",
]);

const decisionKinds = new Set([
  "inspect_tool", "ask_driver", "surface_prior", "observe_only", "no_call",
]);
const priorityTiers = new Set([
  "identity_integrity", "context_qualification", "driver_car_confounders",
  "strongest_contradiction", "unresolved_p19_mechanisms",
  "component_family_separation", "exact_history", "measurement_debt", "terminal",
]);
const transferClasses = new Set(["none", "exact", "compatible", "weak", "blocked"]);
const counterfactualStates = new Set([
  "pending", "directly_observed", "counterfactual_observable",
  "counterfactual_unobservable", "invalid",
]);
const memoryPolicyStates = new Set(["shadow_only", "limited_attention"]);
const problemFamilies = new Set([
  "braking", "entry", "center", "exit", "straight", "long_run", "mixed", "unresolved",
]);
const problemOrientations = new Set(["driver", "vehicle", "combined", "unresolved"]);
const trackClasses = new Set([
  "short_track", "intermediate", "superspeedway", "road_course", "unknown",
]);
const negativeControlConditions = new Set([
  "no_relevant_history", "incompatible_history", "corrupt_history",
  "generic_component_knowledge_only", "same_words_different_physical_scope",
  "material_driver_drift", "future_memory_record",
]);
const P34_PYTHON_FLOAT_KEYS = new Set([
  "baseline_elapsed_seconds", "memory_elapsed_seconds",
]);

export function canonicalInvestigationImprovementSha256(value: unknown): Promise<string> {
  return canonicalJsonSha256(value, { pythonFloatKeys: P34_PYTHON_FLOAT_KEYS });
}

export const UNOBSERVED_BENEFIT = /(?:\b(?:sav(?:e|ed|es|ing)|faster|quicker|sooner|improv(?:e|ed|es|ing|ement)|reduc(?:e|ed|es|ing|tion)|fewer|outperform(?:ed|s|ing)?)\b[^.!?\n]{0,64}\b(?:seconds?|time|laps?|steps?|questions?|percent|%)\b|\b(?:seconds?|time|laps?|steps?|questions?)\b[^.!?\n]{0,64}\b(?:sav(?:e|ed|es|ing)|faster|quicker|sooner|improv(?:e|ed|es|ing|ement)|reduc(?:e|ed|es|ing|tion)|fewer)\b|\b\d+(?:\.\d+)?\s*%\s*(?:improvement|faster|reduction|saved)\b|\b(?:shadow|memory|policy|decision|approach|investigation)\b[^.!?\n]{0,40}\b(?:successful|better|faster|more\s+efficient|an\s+improvement|worked)\b|\b(?:proved|demonstrated|achieved|delivered)\s+(?:a\s+)?(?:success|successful\s+result|benefit)\b|\bsuccessfully\s+(?:saved|reduced|improved|resolved|completed|shortened)\b)/i;
const NEGATED_BENEFIT = /\b(?:cannot|can\s+not|does\s+not|do\s+not|did\s+not|is\s+not|are\s+not|was\s+not|were\s+not|no)\b[^.!?\n]{0,96}\b(?:sav(?:e|ed|es|ing)|faster|quicker|sooner|improv(?:e|ed|es|ing|ement)|reduc(?:e|ed|es|ing|tion)|fewer|benefit|successful|better|efficient|outperform(?:ed|s|ing)?)\b[^.!?\n]{0,64}\b(?:seconds?|time|laps?|steps?|questions?|percent|%)?\b/gi;
const UNSAFE_MEMORY_PROSE = [
  /\b(?:set|adjust|change)\s+[a-z][\w -]{0,48}\s+to\s+[-+]?\d/i,
  /\b(?:increase|decrease|raise|lower|add|remove)\s+[a-z][\w -]{0,48}\s+by\s+[-+]?\d/i,
  /\b(?:keep|undo)\s+(?:the|this)\s+(?:change|setup)\b/i,
  /\b(?:recommend|recommended|must|should)\s+(?:set|adjust|change|increase|decrease|raise|lower)\b/i,
  /\b(?:caused?|due\s+to|because\s+of|responsible\s+for|proves?|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from)|creates?|drives?|drove|explains?|accounts?\s+for|stems?\s+from|comes?\s+from)\b[^.!?\n]{0,64}\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b/i,
  /\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b[^.!?\n]{0,64}\b(?:caused?|due\s+to|because\s+of|responsible\s+for|driven\s+by|explained\s+by|attributable\s+to|came\s+from|result(?:ed|s|ing)?\s+from)\b/i,
  /\b(?:cross[ -]?weight|corner[ -]?weight|ballast|wedge|brake[ -]?bias|ride[ -]?height|shock|damper|spring|tire[ -]?pressure|anti[ -]?roll[ -]?bar|sway[ -]?bar|camber|caster|toe|track[ -]?bar|gear|final[ -]?drive|splitter|tape)\b[^.!?\n]{0,64}[+-]?\d+(?:\.\d+)?\s*(?:%|psi|kpa|bar|lb\/?in|n\/?mm|clicks?|inches?|mm|degrees?)?/i,
  /(?:^|[.!?]\s+)(?:keep|undo|revert|rollback|roll back|stop testing|no more testing)(?:\s+it|\s+the change|\s+this change)?(?=[.!?]|$)/i,
];
const NEGATED_CAUSAL_MEMORY = /\b(?:does\s+not|do\s+not|did\s+not|cannot|can\s+not|is\s+not|are\s+not|was\s+not|were\s+not)\s+(?:caus(?:e|ed|es|ing)|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from)|create(?:d|s|ing)?|drive|drives|drove|explain(?:ed|s|ing)?|establish(?:ed|es|ing)?|prove(?:d|s|n|ing)?)\b[^.!?\n]{0,64}\b(?:loss|gain|delta|time|problem|handling|instability|understeer|oversteer)\b/gi;

const decisionKeys = [
  "decision_kind", "action_id", "priority_tier", "safe_reorder_group",
  "baseline_ordinal", "selected_ordinal", "reason", "mandatory_check_ids",
  "source_memory_record_ids", "setup_authorized", "terminal_policy_authorized",
] as const;
const p19CauseStateKeys = ["cause_id", "state"] as const;
const negativeControlEvidenceKeys = [
  "condition", "p33_projection_sha256", "p33_state",
  "context_transfer_record_ids", "context_transfer_levels",
  "useful_prior_experience_ids", "component_history_experience_ids",
  "physical_scope_mismatch_dimensions", "recurrence_class",
  "corruption_blocker_sha256s", "future_memory_record_ids",
  "future_memory_record_completed_ats", "driver_drift_state",
] as const;
const pairKeys = [
  "schema_version", "pair_id", "pair_sha256", "investigation_id",
  "investigation_opened_at", "run_id",
  "session_id", "workspace_revision", "authority_revision", "step_number",
  "baseline_policy_id", "baseline_policy_sha256", "memory_policy_id",
  "memory_policy_sha256", "activation_protocol_id", "activation_protocol_sha256",
  "activation_state", "activation_decision_id", "activation_decision_sha256",
  "production_policy_kind", "baseline_decision", "memory_decision",
  "production_decision", "available_tool_ids", "eligible_tool_ids",
  "completed_tool_ids", "available_artifact_ids",
  "qualified_available_artifact_ids",
  "qualified_available_artifact_evidence_states",
  "qualified_available_artifact_provenance_sha256s",
  "current_evidence_pinned_tool_ids",
  "current_truth_sha256", "p19_snapshot_sha256", "p20_projection_sha256",
  "p26_projection_sha256", "p32_projection_sha256", "current_p19_cause_ids",
  "current_p19_cause_states",
  "current_contradiction_ids", "strongest_contradiction_id", "current_objective",
  "p33_projection_sha256", "p33_history_revision", "p33_ledger_head_sha256", "p33_context_sha256",
  "p33_problem_sha256", "track", "track_configuration", "package_type",
  "iracing_build", "problem_family", "problem_orientation", "track_class",
  "phase", "context_subgroup_keys",
  "build_review_state", "driver_drift_state", "memory_records_consulted",
  "negative_control_condition", "negative_control_evidence",
  "future_memory_record_ids",
  "context_transfer_class", "decision_frozen_at", "outcome_exposed",
  "p19_rank_unchanged", "p19_authority_unchanged",
  "p19_terminal_action_unchanged", "setup_authorized",
] as const;
const comparisonKeys = [
  "schema_version", "comparison_id", "comparison_sha256", "investigation_id",
  "pair_id", "pair_sha256", "activation_protocol_id", "activation_protocol_sha256",
  "certificate_id", "certificate_sha256", "discriminator_outcome_id",
  "discriminator_outcome_sha256", "outcome_followup_id", "outcome_followup_sha256",
  "counterfactual_source_certificate_id", "counterfactual_source_certificate_sha256",
  "independently_observed_artifact_ids", "decision_frozen_at", "observability",
  "context_identity_sha256", "problem_family", "objective", "context_transfer_class",
  "subgroup_keys", "baseline_tool_steps", "memory_path_metrics_observed",
  "bounded_reorder_observed", "bounded_discriminator_step_advance",
  "bounded_discriminator_step_delay", "bounded_dead_end_promoted",
  "memory_tool_steps", "baseline_elapsed_seconds", "memory_elapsed_seconds",
  "baseline_consumption_metrics_observed", "memory_consumption_metrics_observed",
  "baseline_laps", "memory_laps", "baseline_questions", "memory_questions",
  "baseline_dead_ends", "memory_dead_ends", "baseline_measurement_missions",
  "memory_measurement_missions", "baseline_repeated_no_findings",
  "memory_repeated_no_findings", "baseline_useful_discriminator_step",
  "memory_useful_discriminator_step", "baseline_unresolved_or_abandoned",
  "memory_unresolved_or_abandoned", "useful_discriminator_hit",
  "strongest_contradiction_handled", "recurrence_match_correct",
  "context_transfer_correct", "driver_car_separation_correct",
  "eventual_p19_resolution", "no_call_stable", "authority_violations",
  "p19_action_mismatches", "stale_workspace_actions", "mandatory_check_violations",
  "hidden_contradiction_failures", "incompatible_history_transfers",
  "driver_memory_mechanical_diagnoses", "memory_only_terminal_actions",
  "prospective", "synthetic", "qualified", "blockers", "compared_at",
  "setup_authorized",
] as const;
const readinessKeys = [
  "production_policy", "memory_policy_state", "activation_decision",
  "evaluation_decision", "effective_activation_decision_id",
  "effective_activation_decision_sha256",
  "qualified_historical_investigations", "qualified_prospective_investigations",
  "observable_comparisons", "unobservable_comparisons", "historical_deficit",
  "prospective_deficit", "exact_recurrence_deficit", "compatible_recurrence_deficit",
  "context_deficit", "problem_family_deficit", "objective_deficit",
  "safety_gate_passed", "negative_controls_passed", "subgroup_gate_passed",
  "blockers", "remaining_collection_missions", "authority_ceiling", "setup_authorized",
] as const;
const contextKeys = [
  "schema_version", "context_binding_sha256", "run_id", "session_id",
  "workspace_revision", "current_truth_sha256", "p19_snapshot_sha256",
  "p20_projection_sha256", "p26_projection_sha256", "p32_projection_sha256",
  "p33_projection_sha256", "p33_context_sha256", "p33_problem_sha256",
  "qualified_available_artifact_ids",
  "qualified_available_artifact_evidence_states",
  "qualified_available_artifact_provenance_sha256s",
  "current_evidence_pinned_tool_ids", "track", "track_configuration",
  "package_type", "iracing_build", "problem_family", "problem_orientation",
  "track_class", "phase", "current_objective", "build_review_state",
  "driver_drift_state", "context_subgroup_keys", "negative_control_condition",
  "negative_control_evidence_sha256",
] as const;
const projectionKeys = [
  "schema_version", "projection_sha256", "run_id", "session_id",
  "workspace_revision", "state", "production_policy", "memory_policy_state",
  "current_pair", "current_context", "current_pair_status", "latest_completed_pair",
  "latest_completed_comparison", "latest_outcome_status", "decisions_differ",
  "difference_explanation", "memory_evidence_record_ids", "context_transfer_class",
  "readiness", "safety_blockers", "p19_authority_unchanged", "setup_authorized",
] as const;

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const exactKeys = (value: unknown, keys: readonly string[]): value is Record<string, unknown> =>
  record(value)
  && Object.keys(value).length === keys.length
  && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
const nonempty = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;
const hash = (value: unknown): value is string =>
  typeof value === "string" && HASH.test(value);
const nullableHash = (value: unknown): value is string | null =>
  value === null || hash(value);
const positiveInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= 1;
const nonnegativeInteger = (value: unknown): value is number =>
  typeof value === "number" && Number.isInteger(value) && value >= 0;
const nullableNonnegativeInteger = (value: unknown): value is number | null =>
  value === null || nonnegativeInteger(value);
const nullablePositiveInteger = (value: unknown): value is number | null =>
  value === null || positiveInteger(value);
const nonnegativeFinite = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0;
const nullableNonnegativeFinite = (value: unknown): value is number | null =>
  value === null || nonnegativeFinite(value);
const nullableBoolean = (value: unknown): value is boolean | null =>
  value === null || typeof value === "boolean";
const uniqueStrings = (value: unknown): value is string[] =>
  Array.isArray(value)
  && value.every(nonempty)
  && new Set(value).size === value.length;
const safeText = (value: unknown): value is string => {
  if (!nonempty(value) || value !== value.split(/\s+/).join(" ")) return false;
  const causalScope = value.replace(
    NEGATED_CAUSAL_MEMORY,
    "explicit non-causal boundary",
  );
  return !hasSetupAuthorityDirective(value)
    && !UNSAFE_MEMORY_PROSE.some((pattern) => pattern.test(causalScope));
};
const safeTexts = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(safeText);
const validDate = (value: unknown): value is string =>
  nonempty(value) && Number.isFinite(Date.parse(value));
const validAwareDate = (value: unknown): value is string =>
  validDate(value) && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
const sameList = (left: readonly unknown[], right: readonly unknown[]): boolean =>
  left.length === right.length && left.every((value, index) => value === right[index]);
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
  return sameList(leftKeys, rightKeys)
    && leftKeys.every((key) => deepEqual(left[key], right[key]));
};
const matchingNullableIdentity = (
  id: unknown,
  digest: unknown,
  idPattern: RegExp,
): boolean => (id === null && digest === null)
  || (typeof id === "string" && idPattern.test(id) && hash(digest)
    && id.endsWith(digest.slice(0, 24)));

export const executableIdentity = (decision: InvestigationDecision): readonly unknown[] => [
  decision.decision_kind,
  decision.action_id,
  decision.priority_tier,
  decision.safe_reorder_group,
  decision.selected_ordinal,
];
const executableDecisionsDiffer = (
  baseline: InvestigationDecision,
  memory: InvestigationDecision,
): boolean => !sameList(executableIdentity(baseline), executableIdentity(memory));

function canonicalContextSubgroups(pair: PairedInvestigationDecision): string[] {
  const values = [
    pair.context_transfer_class === "exact" || pair.context_transfer_class === "compatible"
      ? `${pair.context_transfer_class}_context_history`
      : "weak_history",
    pair.problem_orientation === "driver"
      ? "driver_first"
      : pair.problem_orientation === "vehicle"
        ? "vehicle_response"
        : "mixed_problem",
  ];
  if (["braking", "entry", "center", "exit", "straight", "long_run"]
    .includes(pair.problem_family)) values.push(pair.problem_family);
  const objectiveSubgroup = new Map([
    ["qualifying_peak", "qualifying_objective"],
    ["race_long_run", "race_long_run_objective"],
    ["driver_confidence", "driver_confidence_objective"],
  ]).get(pair.current_objective);
  if (objectiveSubgroup) values.push(objectiveSubgroup);
  if (pair.track_class !== "unknown") values.push(pair.track_class);
  values.push(pair.driver_drift_state === "stable"
    ? "stable_driver_fingerprint"
    : pair.driver_drift_state === "material_drift"
      ? "driver_drift_detected"
      : "driver_state_unknown");
  values.push(pair.build_review_state);
  return [...new Set(values)];
}

function negativeControlMatchesContext(pair: PairedInvestigationDecision): boolean {
  if (pair.negative_control_condition === null) return true;
  if (executableDecisionsDiffer(pair.baseline_decision, pair.memory_decision)
    || pair.memory_records_consulted.length > 0) return false;
  switch (pair.negative_control_condition) {
    case "no_relevant_history":
      return pair.context_transfer_class === "none";
    case "incompatible_history":
      return pair.context_transfer_class === "blocked"
        && pair.driver_drift_state === "stable"
        && pair.build_review_state !== "future_unreviewed_build";
    case "corrupt_history":
      return pair.context_transfer_class === "blocked";
    case "generic_component_knowledge_only":
      return pair.context_transfer_class === "weak"
        && pair.problem_orientation === "vehicle";
    case "same_words_different_physical_scope":
      return pair.context_transfer_class === "weak"
        && (pair.problem_orientation === "combined"
          || pair.problem_orientation === "unresolved");
    case "material_driver_drift":
      return pair.driver_drift_state === "material_drift";
    case "future_memory_record":
      return pair.future_memory_record_ids.length > 0;
  }
}

export type InvestigationImprovementTrustScope = {
  runId: string;
  sessionId: string;
  workspaceRevision: string;
  generatedAt: string;
  investigationId: string | null;
  investigationOpenedAt: string | null;
  objectiveId: string;
  p19SnapshotSha256: string;
  p20ProjectionSha256: string;
  p26ProjectionSha256: string;
  p32ProjectionSha256: string;
  p33ProjectionSha256: string;
  p33HistoryRevision: string;
  p33LedgerHeadSha256: string | null;
  p33ContextSha256: string;
  p33ProblemSha256: string;
  foldedStatus: string | null;
  stepNumber: number | null;
  p19CauseIds: readonly string[];
  p19CauseStates: ReadonlyArray<{ cause_id: string; p19_state: string }>;
  p19ContradictionArtifactIds: readonly string[];
  availableToolIds: readonly string[];
  availableArtifactIds: readonly string[];
  completedToolIds: readonly string[];
  evidenceEntries: readonly CrewChiefEvidenceEntry[];
  learningPrior: CrewChiefLearningPrior;
  currentSubgoal: null | {
    selectedTool: string;
    distinguishesCauseIds: readonly string[];
  };
  driverAnswers: readonly string[];
  blockerReasons: readonly string[];
};

function validDecision(value: unknown): value is InvestigationDecision {
  if (!exactKeys(value, decisionKeys)
    || !decisionKinds.has(String(value.decision_kind))
    || !safeText(value.action_id)
    || !priorityTiers.has(String(value.priority_tier))
    || !(value.safe_reorder_group === null || safeText(value.safe_reorder_group))
    || !positiveInteger(value.baseline_ordinal)
    || !positiveInteger(value.selected_ordinal)
    || !safeText(value.reason)
    || !uniqueStrings(value.mandatory_check_ids)
    || !uniqueStrings(value.source_memory_record_ids)
    || value.setup_authorized !== false
    || value.terminal_policy_authorized !== false
  ) return false;
  const decision = value as unknown as InvestigationDecision;
  return (decision.decision_kind === "inspect_tool" || decision.safe_reorder_group === null)
    && (decision.source_memory_record_ids.length === 0
      || decision.safe_reorder_group !== null)
    && decision.source_memory_record_ids.every((item) => P33_RECORD_ID.test(item));
}

function validP19CauseState(value: unknown): value is InvestigationP19CauseState {
  return exactKeys(value, p19CauseStateKeys)
    && nonempty(value.cause_id)
    && ["likely", "possible", "ruled_out", "unresolved"].includes(String(value.state));
}

function validNegativeControlEvidence(
  value: unknown,
): value is InvestigationNegativeControlEvidence {
  if (!exactKeys(value, negativeControlEvidenceKeys)
    || !negativeControlConditions.has(String(value.condition))
    || !hash(value.p33_projection_sha256)
    || !["available", "insufficient_history", "blocked"].includes(String(value.p33_state))
    || !uniqueStrings(value.context_transfer_record_ids)
    || !value.context_transfer_record_ids.every((item) => P33_RECORD_ID.test(item))
    || !Array.isArray(value.context_transfer_levels)
    || !value.context_transfer_levels.every((item) => ["exact", "compatible", "weak", "blocked"].includes(String(item)))
    || value.context_transfer_record_ids.length !== value.context_transfer_levels.length
    || !uniqueStrings(value.useful_prior_experience_ids)
    || !value.useful_prior_experience_ids.every((item) => P33_RECORD_ID.test(item))
    || !uniqueStrings(value.component_history_experience_ids)
    || !value.component_history_experience_ids.every((item) => P33_RECORD_ID.test(item))
    || !uniqueStrings(value.physical_scope_mismatch_dimensions)
    || !["new_problem", "possible_recurrence", "strong_recurrence", "exact_context_recurrence"]
      .includes(String(value.recurrence_class))
    || !uniqueStrings(value.corruption_blocker_sha256s)
    || !value.corruption_blocker_sha256s.every(hash)
    || !uniqueStrings(value.future_memory_record_ids)
    || !value.future_memory_record_ids.every((item) => P33_RECORD_ID.test(item))
    || !Array.isArray(value.future_memory_record_completed_ats)
    || !value.future_memory_record_completed_ats.every(validAwareDate)
    || value.future_memory_record_ids.length !== value.future_memory_record_completed_ats.length
    || !["stable", "material_drift", "unknown"].includes(String(value.driver_drift_state))
  ) return false;
  const proof = value as unknown as InvestigationNegativeControlEvidence;
  const exactCondition = {
    no_relevant_history: (
      ["available", "insufficient_history"].includes(proof.p33_state)
      && proof.context_transfer_record_ids.length === 0
      && proof.useful_prior_experience_ids.length === 0
      && proof.component_history_experience_ids.length === 0
      && proof.recurrence_class === "new_problem"
      && proof.future_memory_record_ids.length === 0
    ),
    incompatible_history: (
      proof.p33_state !== "blocked"
      && proof.context_transfer_levels.includes("blocked")
      && proof.corruption_blocker_sha256s.length === 0
      && proof.future_memory_record_ids.length === 0
      && proof.driver_drift_state === "stable"
    ),
    corrupt_history: (
      proof.p33_state === "blocked"
      && proof.corruption_blocker_sha256s.length > 0
      && proof.future_memory_record_ids.length === 0
    ),
    generic_component_knowledge_only: (
      proof.p33_state === "available"
      && proof.context_transfer_levels.includes("weak")
      && proof.component_history_experience_ids.length > 0
      && proof.useful_prior_experience_ids.length === 0
      && proof.physical_scope_mismatch_dimensions.length === 0
      && proof.future_memory_record_ids.length === 0
    ),
    same_words_different_physical_scope: (
      proof.p33_state === "available"
      && proof.context_transfer_levels.includes("weak")
      && proof.physical_scope_mismatch_dimensions.length > 0
      && proof.recurrence_class !== "new_problem"
      && proof.future_memory_record_ids.length === 0
    ),
    material_driver_drift: (
      proof.driver_drift_state === "material_drift"
      && proof.future_memory_record_ids.length === 0
    ),
    future_memory_record: proof.future_memory_record_ids.length > 0,
  } as const;
  return exactCondition[proof.condition];
}

function pairUsesFrozenContract(pair: PairedInvestigationDecision): boolean {
  const expectedMemory = pair.activation_state === "shadow_only"
    ? FROZEN_SHADOW_POLICY : FROZEN_LIMITED_POLICY;
  return pair.baseline_policy_id === FROZEN_BASELINE_POLICY.id
    && pair.baseline_policy_sha256 === FROZEN_BASELINE_POLICY.sha256
    && pair.memory_policy_id === expectedMemory.id
    && pair.memory_policy_sha256 === expectedMemory.sha256
    && pair.activation_protocol_id === FROZEN_ACTIVATION_PROTOCOL.id
    && pair.activation_protocol_sha256 === FROZEN_ACTIVATION_PROTOCOL.sha256
    && Date.parse(pair.decision_frozen_at) >= Date.parse(FROZEN_ACTIVATION_PROTOCOL.frozenAt);
}

function expectedSafeGroup(actionId: string): string | null {
  return PERFORMANCE_REORDER_GROUP.includes(
    actionId as (typeof PERFORMANCE_REORDER_GROUP)[number],
  ) ? "performance_measurement" : null;
}

function validFrozenInspectDecision(decision: InvestigationDecision): boolean {
  if (decision.decision_kind !== "inspect_tool") return true;
  const priority = FROZEN_TOOL_PRIORITY.get(decision.action_id);
  const group = expectedSafeGroup(decision.action_id);
  const ordinal = group === null ? 1 : PERFORMANCE_REORDER_GROUP.indexOf(
    decision.action_id as (typeof PERFORMANCE_REORDER_GROUP)[number],
  ) + 1;
  return priority !== undefined
    && decision.priority_tier === priority
    && decision.safe_reorder_group === group
    && decision.baseline_ordinal === ordinal;
}

function expectedEligibleTools(pair: PairedInvestigationDecision): string[] {
  const baseline = pair.baseline_decision;
  if (baseline.decision_kind !== "inspect_tool") return [];
  const expected = [baseline.action_id];
  const position = PERFORMANCE_REORDER_GROUP.indexOf(
    baseline.action_id as (typeof PERFORMANCE_REORDER_GROUP)[number],
  );
  if (position >= 0) {
    const next = PERFORMANCE_REORDER_GROUP.slice(position + 1).find((toolId) => (
      pair.available_tool_ids.includes(toolId)
      && !pair.completed_tool_ids.includes(toolId)
    ));
    if (next) expected.push(next);
  }
  return expected;
}

function validPairShape(value: unknown): value is PairedInvestigationDecision {
  if (!exactKeys(value, pairKeys)
    || value.schema_version !== "p34.paired-investigation-decision.v1"
    || typeof value.pair_id !== "string" || !PAIR_ID.test(value.pair_id)
    || !hash(value.pair_sha256)
    || !nonempty(value.investigation_id)
    || !validDate(value.investigation_opened_at)
    || !nonempty(value.run_id)
    || !nonempty(value.session_id)
    || !hash(value.workspace_revision)
    || !hash(value.authority_revision)
    || !nonnegativeInteger(value.step_number)
    || typeof value.baseline_policy_id !== "string" || !POLICY_ID.test(value.baseline_policy_id)
    || !hash(value.baseline_policy_sha256)
    || typeof value.memory_policy_id !== "string" || !POLICY_ID.test(value.memory_policy_id)
    || !hash(value.memory_policy_sha256)
    || typeof value.activation_protocol_id !== "string" || !PROTOCOL_ID.test(value.activation_protocol_id)
    || !hash(value.activation_protocol_sha256)
    || !memoryPolicyStates.has(String(value.activation_state))
    || !matchingNullableIdentity(value.activation_decision_id, value.activation_decision_sha256, ACTIVATION_ID)
    || !["deterministic_baseline", "limited_attention"].includes(String(value.production_policy_kind))
    || !validDecision(value.baseline_decision)
    || !validDecision(value.memory_decision)
    || !validDecision(value.production_decision)
    || !uniqueStrings(value.available_tool_ids)
    || !uniqueStrings(value.eligible_tool_ids)
    || !uniqueStrings(value.completed_tool_ids)
    || !uniqueStrings(value.available_artifact_ids)
    || !uniqueStrings(value.qualified_available_artifact_ids)
    || !Array.isArray(value.qualified_available_artifact_evidence_states)
    || !value.qualified_available_artifact_evidence_states.every((item) => (
      QUALIFIED_ARTIFACT_STATES.has(String(item))
    ))
    || !Array.isArray(value.qualified_available_artifact_provenance_sha256s)
    || !value.qualified_available_artifact_provenance_sha256s.every(hash)
    || !uniqueStrings(value.current_evidence_pinned_tool_ids)
    || !hash(value.current_truth_sha256)
    || !hash(value.p19_snapshot_sha256)
    || !hash(value.p20_projection_sha256)
    || !hash(value.p26_projection_sha256)
    || !hash(value.p32_projection_sha256)
    || !uniqueStrings(value.current_p19_cause_ids)
    || !Array.isArray(value.current_p19_cause_states)
    || !value.current_p19_cause_states.every(validP19CauseState)
    || !uniqueStrings(value.current_contradiction_ids)
    || !(value.strongest_contradiction_id === null || nonempty(value.strongest_contradiction_id))
    || !nonempty(value.current_objective)
    || !hash(value.p33_projection_sha256)
    || !hash(value.p33_history_revision)
    || !nullableHash(value.p33_ledger_head_sha256)
    || !hash(value.p33_context_sha256)
    || !hash(value.p33_problem_sha256)
    || !nonempty(value.track)
    || !nonempty(value.track_configuration)
    || !nonempty(value.package_type)
    || !nonempty(value.iracing_build)
    || !problemFamilies.has(String(value.problem_family))
    || !problemOrientations.has(String(value.problem_orientation))
    || !trackClasses.has(String(value.track_class))
    || !nonempty(value.phase)
    || !uniqueStrings(value.context_subgroup_keys)
    || value.context_subgroup_keys.length === 0
    || !["same_build", "reviewed_compatible_build", "future_unreviewed_build"]
      .includes(String(value.build_review_state))
    || !["stable", "material_drift", "unknown"].includes(String(value.driver_drift_state))
    || !(value.negative_control_condition === null
      || negativeControlConditions.has(String(value.negative_control_condition)))
    || !(value.negative_control_evidence === null
      || validNegativeControlEvidence(value.negative_control_evidence))
    || !uniqueStrings(value.future_memory_record_ids)
    || !value.future_memory_record_ids.every((item) => P33_RECORD_ID.test(item))
    || !uniqueStrings(value.memory_records_consulted)
    || !value.memory_records_consulted.every((item) => P33_RECORD_ID.test(item))
    || !transferClasses.has(String(value.context_transfer_class))
    || !validAwareDate(value.decision_frozen_at)
    || value.outcome_exposed !== false
    || value.p19_rank_unchanged !== true
    || value.p19_authority_unchanged !== true
    || value.p19_terminal_action_unchanged !== true
    || value.setup_authorized !== false
  ) return false;
  const pair = value as unknown as PairedInvestigationDecision;
  const baseline = pair.baseline_decision;
  const memory = pair.memory_decision;
  const differs = executableDecisionsDiffer(baseline, memory);
  const qualifiedCount = pair.qualified_available_artifact_ids.length;
  const baselinePinned = baseline.decision_kind === "inspect_tool"
    && pair.current_evidence_pinned_tool_ids.includes(baseline.action_id);
  return pairUsesFrozenContract(pair)
    && validFrozenInspectDecision(baseline)
    && validFrozenInspectDecision(memory)
    && pair.eligible_tool_ids.every((item) => pair.available_tool_ids.includes(item))
    && pair.completed_tool_ids.every((item) => pair.available_tool_ids.includes(item))
    && pair.eligible_tool_ids.every((item) => !pair.completed_tool_ids.includes(item))
    && sameList(pair.eligible_tool_ids, expectedEligibleTools(pair))
    && pair.current_evidence_pinned_tool_ids.every((item) => pair.eligible_tool_ids.includes(item))
    && sameList(
      pair.current_evidence_pinned_tool_ids,
      pair.current_evidence_pinned_tool_ids.length > 0 && baseline.decision_kind === "inspect_tool"
        ? [baseline.action_id] : [],
    )
    && (pair.current_evidence_pinned_tool_ids.length === 0 || qualifiedCount > 0)
    && pair.qualified_available_artifact_evidence_states.length === qualifiedCount
    && pair.qualified_available_artifact_provenance_sha256s.length === qualifiedCount
    && pair.qualified_available_artifact_ids.every((item) => pair.available_artifact_ids.includes(item))
    && sameList(
      pair.current_p19_cause_states.map((item) => item.cause_id),
      pair.current_p19_cause_ids,
    )
    && (pair.activation_state !== "shadow_only" || (
    pair.production_policy_kind === "deterministic_baseline"
    && deepEqual(pair.production_decision, baseline)
    && pair.activation_decision_id === null
    && pair.activation_decision_sha256 === null
  ))
    && (pair.activation_state !== "limited_attention" || (
      pair.production_policy_kind === "limited_attention"
      && deepEqual(pair.production_decision, memory)
      && typeof pair.activation_decision_id === "string"
      && ACTIVATION_ID.test(pair.activation_decision_id)
      && hash(pair.activation_decision_sha256)
    ))
    && baseline.source_memory_record_ids.length === 0
    && Date.parse(pair.investigation_opened_at) <= Date.parse(pair.decision_frozen_at)
    && baseline.selected_ordinal === baseline.baseline_ordinal
    && sameList(pair.memory_records_consulted, memory.source_memory_record_ids)
    && (baseline.decision_kind !== "inspect_tool"
      || pair.eligible_tool_ids.includes(baseline.action_id))
    && (memory.decision_kind !== "inspect_tool"
      || pair.eligible_tool_ids.includes(memory.action_id))
    && pair.future_memory_record_ids.every((item) => !pair.memory_records_consulted.includes(item))
    && ((pair.memory_records_consulted.length === 0 && pair.future_memory_record_ids.length === 0)
      || pair.p33_ledger_head_sha256 !== null)
    && pair.strongest_contradiction_id === (pair.current_contradiction_ids[0] ?? null)
    && sameList(baseline.mandatory_check_ids, memory.mandatory_check_ids)
    && (!(pair.context_transfer_class === "none"
      || pair.context_transfer_class === "weak"
      || pair.context_transfer_class === "blocked")
      || (!differs && pair.memory_records_consulted.length === 0))
    && (pair.build_review_state !== "future_unreviewed_build"
      || (pair.context_transfer_class === "blocked" && !differs))
    && (pair.driver_drift_state === "stable" || !differs)
    && (!differs || (
      memory.safe_reorder_group !== null
      && memory.safe_reorder_group === baseline.safe_reorder_group
      && memory.priority_tier === baseline.priority_tier
      && memory.baseline_ordinal === baseline.baseline_ordinal + 1
      && memory.selected_ordinal === baseline.selected_ordinal
    ))
    && (!baselinePinned || (
      !differs
      && pair.memory_records_consulted.length === 0
      && pair.context_transfer_class === "blocked"
    ))
    && sameList(pair.context_subgroup_keys, canonicalContextSubgroups(pair))
    && negativeControlMatchesContext(pair)
    && ((pair.negative_control_condition === null
      && pair.negative_control_evidence === null
      && pair.future_memory_record_ids.length === 0) || (
      pair.negative_control_condition !== null
      && pair.negative_control_evidence !== null
      && pair.negative_control_evidence.condition === pair.negative_control_condition
      && pair.negative_control_evidence.p33_projection_sha256 === pair.p33_projection_sha256
      && sameList(
        pair.negative_control_evidence.future_memory_record_ids,
        pair.future_memory_record_ids,
      )
      && pair.negative_control_evidence.driver_drift_state === pair.driver_drift_state
      && pair.negative_control_evidence.future_memory_record_completed_ats.every((item) => (
        Date.parse(item) >= Date.parse(pair.decision_frozen_at)
      ))
      && !differs
      && pair.memory_records_consulted.length === 0
    ))
    && Math.abs(memory.selected_ordinal - memory.baseline_ordinal) <= 1;
}

function validCurrentPair(
  pair: PairedInvestigationDecision,
  scope: InvestigationImprovementTrustScope,
): boolean {
  return scope.investigationId !== null
    && pair.investigation_id === scope.investigationId
    && pair.investigation_opened_at === scope.investigationOpenedAt
    && pair.run_id === scope.runId
    && pair.session_id === scope.sessionId
    && pair.workspace_revision === scope.workspaceRevision
    && scope.foldedStatus === "open"
    && scope.stepNumber !== null
    && pair.step_number === scope.stepNumber
    && pair.p19_snapshot_sha256 === scope.p19SnapshotSha256
    && pair.p20_projection_sha256 === scope.p20ProjectionSha256
    && pair.p26_projection_sha256 === scope.p26ProjectionSha256
    && pair.p32_projection_sha256 === scope.p32ProjectionSha256
    && pair.current_objective === scope.objectiveId
    && pair.p33_projection_sha256 === scope.p33ProjectionSha256
    && pair.p33_history_revision === scope.p33HistoryRevision
    && pair.p33_ledger_head_sha256 === scope.p33LedgerHeadSha256
    && pair.p33_context_sha256 === scope.p33ContextSha256
    && pair.p33_problem_sha256 === scope.p33ProblemSha256
    && sameList(pair.available_tool_ids, scope.availableToolIds)
    && sameList(pair.available_artifact_ids, scope.availableArtifactIds)
    && sameList(pair.completed_tool_ids, scope.completedToolIds)
    && sameList(pair.current_p19_cause_ids, scope.p19CauseIds)
    && deepEqual(
      pair.current_p19_cause_states.map((item) => [item.cause_id, item.state]),
      scope.p19CauseStates.map((item) => [item.cause_id, item.p19_state]),
    )
    && sameList(pair.current_contradiction_ids, scope.p19ContradictionArtifactIds)
    && pair.strongest_contradiction_id
      === (scope.p19ContradictionArtifactIds[0] ?? null)
    && Date.parse(pair.decision_frozen_at) <= Date.parse(scope.generatedAt);
}

function validComparison(value: unknown): value is PairedInvestigationComparison {
  if (!exactKeys(value, comparisonKeys)
    || value.schema_version !== "p34.paired-investigation-comparison.v1"
    || typeof value.comparison_id !== "string" || !COMPARISON_ID.test(value.comparison_id)
    || !hash(value.comparison_sha256)
    || !nonempty(value.investigation_id)
    || typeof value.pair_id !== "string" || !PAIR_ID.test(value.pair_id)
    || !hash(value.pair_sha256)
    || typeof value.activation_protocol_id !== "string" || !PROTOCOL_ID.test(value.activation_protocol_id)
    || !hash(value.activation_protocol_sha256)
    || typeof value.certificate_id !== "string" || !CERTIFICATE_ID.test(value.certificate_id)
    || !hash(value.certificate_sha256)
    || !value.certificate_id.endsWith(value.certificate_sha256.slice(0, 24))
    || !matchingNullableIdentity(value.discriminator_outcome_id, value.discriminator_outcome_sha256, DISCRIMINATOR_ID)
    || !matchingNullableIdentity(value.outcome_followup_id, value.outcome_followup_sha256, FOLLOWUP_ID)
    || !matchingNullableIdentity(
      value.counterfactual_source_certificate_id,
      value.counterfactual_source_certificate_sha256,
      CERTIFICATE_ID,
    )
    || !uniqueStrings(value.independently_observed_artifact_ids)
    || !validAwareDate(value.decision_frozen_at)
    || !counterfactualStates.has(String(value.observability))
    || !hash(value.context_identity_sha256)
    || !nonempty(value.problem_family)
    || !nonempty(value.objective)
    || !transferClasses.has(String(value.context_transfer_class))
    || !uniqueStrings(value.subgroup_keys)
    || value.subgroup_keys.length === 0
    || !nonnegativeInteger(value.baseline_tool_steps)
    || typeof value.memory_path_metrics_observed !== "boolean"
    || typeof value.bounded_reorder_observed !== "boolean"
    || ![0, 1].includes(Number(value.bounded_discriminator_step_advance))
    || ![0, 1].includes(Number(value.bounded_discriminator_step_delay))
    || typeof value.bounded_dead_end_promoted !== "boolean"
    || !nullableNonnegativeInteger(value.memory_tool_steps)
    || !nonnegativeFinite(value.baseline_elapsed_seconds)
    || !nullableNonnegativeFinite(value.memory_elapsed_seconds)
    || typeof value.baseline_consumption_metrics_observed !== "boolean"
    || typeof value.memory_consumption_metrics_observed !== "boolean"
    || !nullableNonnegativeInteger(value.baseline_laps)
    || !nullableNonnegativeInteger(value.memory_laps)
    || !nonnegativeInteger(value.baseline_questions)
    || !nullableNonnegativeInteger(value.memory_questions)
    || !nonnegativeInteger(value.baseline_dead_ends)
    || !nullableNonnegativeInteger(value.memory_dead_ends)
    || !nullableNonnegativeInteger(value.baseline_measurement_missions)
    || !nullableNonnegativeInteger(value.memory_measurement_missions)
    || !nonnegativeInteger(value.baseline_repeated_no_findings)
    || !nullableNonnegativeInteger(value.memory_repeated_no_findings)
    || !nullablePositiveInteger(value.baseline_useful_discriminator_step)
    || !nullablePositiveInteger(value.memory_useful_discriminator_step)
    || typeof value.baseline_unresolved_or_abandoned !== "boolean"
    || !nullableBoolean(value.memory_unresolved_or_abandoned)
    || typeof value.useful_discriminator_hit !== "boolean"
    || typeof value.strongest_contradiction_handled !== "boolean"
    || !nullableBoolean(value.recurrence_match_correct)
    || !nullableBoolean(value.context_transfer_correct)
    || !nullableBoolean(value.driver_car_separation_correct)
    || !nullableBoolean(value.eventual_p19_resolution)
    || !nullableBoolean(value.no_call_stable)
    || !nonnegativeInteger(value.authority_violations)
    || !nonnegativeInteger(value.p19_action_mismatches)
    || !nonnegativeInteger(value.stale_workspace_actions)
    || !nonnegativeInteger(value.mandatory_check_violations)
    || !nonnegativeInteger(value.hidden_contradiction_failures)
    || !nonnegativeInteger(value.incompatible_history_transfers)
    || !nonnegativeInteger(value.driver_memory_mechanical_diagnoses)
    || !nonnegativeInteger(value.memory_only_terminal_actions)
    || typeof value.prospective !== "boolean"
    || typeof value.synthetic !== "boolean"
    || typeof value.qualified !== "boolean"
    || !safeTexts(value.blockers)
    || !validAwareDate(value.compared_at)
    || value.setup_authorized !== false
  ) return false;
  const comparison = value as unknown as PairedInvestigationComparison;
  const memoryMetrics = [
    comparison.memory_tool_steps,
    comparison.memory_elapsed_seconds,
    comparison.memory_questions,
    comparison.memory_dead_ends,
    comparison.memory_repeated_no_findings,
    comparison.memory_unresolved_or_abandoned,
  ];
  const baselineConsumptionComplete = comparison.baseline_laps !== null
    && comparison.baseline_measurement_missions !== null;
  const memoryConsumptionComplete = comparison.memory_laps !== null
    && comparison.memory_measurement_missions !== null;
  const unobservable = comparison.observability === "pending"
    || comparison.observability === "counterfactual_unobservable"
    || comparison.observability === "invalid";
  if (unobservable && (
    memoryMetrics.some((item) => item !== null)
    || comparison.memory_useful_discriminator_step !== null
    || comparison.memory_path_metrics_observed
    || comparison.memory_consumption_metrics_observed
    || comparison.context_transfer_correct !== null
    || comparison.driver_car_separation_correct !== null
  )) return false;
  if (comparison.baseline_consumption_metrics_observed !== baselineConsumptionComplete
    || comparison.memory_consumption_metrics_observed !== memoryConsumptionComplete) return false;
  if (!unobservable && comparison.memory_path_metrics_observed
    !== memoryMetrics.every((item) => item !== null)) return false;
  if (comparison.bounded_reorder_observed) {
    if (comparison.observability !== "counterfactual_observable"
      || comparison.bounded_discriminator_step_advance
        + comparison.bounded_discriminator_step_delay !== 1
      || !comparison.useful_discriminator_hit) return false;
  } else if (comparison.bounded_discriminator_step_advance
    || comparison.bounded_discriminator_step_delay
    || comparison.bounded_dead_end_promoted) return false;
  if (comparison.bounded_dead_end_promoted
    && comparison.bounded_discriminator_step_delay !== 1) return false;
  if (comparison.observability === "counterfactual_observable"
    && comparison.memory_path_metrics_observed
    && comparison.counterfactual_source_certificate_id === null) return false;
  if (comparison.observability === "directly_observed" && (
    !comparison.memory_path_metrics_observed
    || comparison.memory_tool_steps !== comparison.baseline_tool_steps
    || comparison.memory_elapsed_seconds !== comparison.baseline_elapsed_seconds
    || comparison.memory_consumption_metrics_observed
      !== comparison.baseline_consumption_metrics_observed
    || comparison.memory_laps !== comparison.baseline_laps
    || comparison.memory_questions !== comparison.baseline_questions
    || comparison.memory_dead_ends !== comparison.baseline_dead_ends
    || comparison.memory_measurement_missions !== comparison.baseline_measurement_missions
    || comparison.memory_repeated_no_findings !== comparison.baseline_repeated_no_findings
    || comparison.memory_useful_discriminator_step
      !== comparison.baseline_useful_discriminator_step
    || comparison.memory_unresolved_or_abandoned
      !== comparison.baseline_unresolved_or_abandoned
  )) return false;
  return Date.parse(comparison.compared_at) >= Date.parse(comparison.decision_frozen_at)
    && !(comparison.qualified && (
    comparison.synthetic
    || comparison.blockers.length > 0
    || comparison.observability === "invalid"
  )) && (comparison.qualified || comparison.blockers.length > 0);
}

function validReadiness(value: unknown): value is InvestigationImprovementReadiness {
  if (!exactKeys(value, readinessKeys)) return false;
  const countFields = [
    "qualified_historical_investigations", "qualified_prospective_investigations",
    "observable_comparisons", "unobservable_comparisons", "historical_deficit",
    "prospective_deficit", "exact_recurrence_deficit", "compatible_recurrence_deficit",
    "context_deficit", "problem_family_deficit", "objective_deficit",
  ] as const;
  if (!countFields.every((field) => nonnegativeInteger(value[field]))
    || !["deterministic_baseline", "limited_attention"].includes(String(value.production_policy))
    || !memoryPolicyStates.has(String(value.memory_policy_state))
    || !["no_activation_earned", "limited_attention_earned"].includes(String(value.activation_decision))
    || !["no_activation_earned", "limited_attention_earned"].includes(String(value.evaluation_decision))
    || !matchingNullableIdentity(
      value.effective_activation_decision_id,
      value.effective_activation_decision_sha256,
      ACTIVATION_ID,
    )
    || typeof value.safety_gate_passed !== "boolean"
    || typeof value.negative_controls_passed !== "boolean"
    || typeof value.subgroup_gate_passed !== "boolean"
    || !safeTexts(value.blockers)
    || !safeTexts(value.remaining_collection_missions)
    || value.authority_ceiling !== "attention_only"
    || value.setup_authorized !== false
  ) return false;
  const readiness = value as unknown as InvestigationImprovementReadiness;
  const deficits = [
    readiness.historical_deficit, readiness.prospective_deficit,
    readiness.exact_recurrence_deficit, readiness.compatible_recurrence_deficit,
    readiness.context_deficit, readiness.problem_family_deficit, readiness.objective_deficit,
  ];
  const allGatesPassed = readiness.safety_gate_passed
    && readiness.negative_controls_passed
    && readiness.subgroup_gate_passed;
  return (readiness.memory_policy_state !== "shadow_only" || (
    readiness.production_policy === "deterministic_baseline"
    && readiness.activation_decision === "no_activation_earned"
    && readiness.effective_activation_decision_id === null
    && readiness.effective_activation_decision_sha256 === null
    && readiness.blockers.length > 0
  )) && (readiness.memory_policy_state !== "limited_attention" || (
    readiness.production_policy === "limited_attention"
    && readiness.activation_decision === "limited_attention_earned"
    && readiness.effective_activation_decision_id !== null
    && readiness.effective_activation_decision_sha256 !== null
    && deficits.every((item) => item === 0)
    && allGatesPassed
    && readiness.blockers.length === 0
    && readiness.remaining_collection_missions.length === 0
  ));
}

function validAdaptationContext(value: unknown): value is InvestigationAdaptationContext {
  if (!exactKeys(value, contextKeys)
    || value.schema_version !== "p34.investigation-adaptation-context.v1"
    || !hash(value.context_binding_sha256)
    || !nonempty(value.run_id)
    || !nonempty(value.session_id)
    || !hash(value.workspace_revision)
    || !hash(value.current_truth_sha256)
    || !hash(value.p19_snapshot_sha256)
    || !hash(value.p20_projection_sha256)
    || !hash(value.p26_projection_sha256)
    || !hash(value.p32_projection_sha256)
    || !hash(value.p33_projection_sha256)
    || !hash(value.p33_context_sha256)
    || !hash(value.p33_problem_sha256)
    || !uniqueStrings(value.qualified_available_artifact_ids)
    || !Array.isArray(value.qualified_available_artifact_evidence_states)
    || !value.qualified_available_artifact_evidence_states.every((item) => (
      QUALIFIED_ARTIFACT_STATES.has(String(item))
    ))
    || !Array.isArray(value.qualified_available_artifact_provenance_sha256s)
    || !value.qualified_available_artifact_provenance_sha256s.every(hash)
    || !uniqueStrings(value.current_evidence_pinned_tool_ids)
    || !nonempty(value.track)
    || !nonempty(value.track_configuration)
    || !nonempty(value.package_type)
    || !nonempty(value.iracing_build)
    || !problemFamilies.has(String(value.problem_family))
    || !problemOrientations.has(String(value.problem_orientation))
    || !trackClasses.has(String(value.track_class))
    || !nonempty(value.phase)
    || !nonempty(value.current_objective)
    || !["same_build", "reviewed_compatible_build", "future_unreviewed_build"]
      .includes(String(value.build_review_state))
    || !["stable", "material_drift", "unknown"].includes(String(value.driver_drift_state))
    || !uniqueStrings(value.context_subgroup_keys)
    || value.context_subgroup_keys.length === 0
    || !(value.negative_control_condition === null
      || negativeControlConditions.has(String(value.negative_control_condition)))
    || !nullableHash(value.negative_control_evidence_sha256)
  ) return false;
  const context = value as unknown as InvestigationAdaptationContext;
  const count = context.qualified_available_artifact_ids.length;
  return context.qualified_available_artifact_evidence_states.length === count
    && context.qualified_available_artifact_provenance_sha256s.length === count
    && ((context.negative_control_condition === null)
      === (context.negative_control_evidence_sha256 === null));
}

function contextMatchesPair(
  context: InvestigationAdaptationContext,
  pair: PairedInvestigationDecision,
): boolean {
  const negativeEvidenceDigestPresence = pair.negative_control_evidence === null
    ? context.negative_control_evidence_sha256 === null
    : context.negative_control_evidence_sha256 !== null;
  return context.run_id === pair.run_id
    && context.session_id === pair.session_id
    && context.workspace_revision === pair.workspace_revision
    && context.current_truth_sha256 === pair.current_truth_sha256
    && context.p19_snapshot_sha256 === pair.p19_snapshot_sha256
    && context.p20_projection_sha256 === pair.p20_projection_sha256
    && context.p26_projection_sha256 === pair.p26_projection_sha256
    && context.p32_projection_sha256 === pair.p32_projection_sha256
    && context.p33_projection_sha256 === pair.p33_projection_sha256
    && context.p33_context_sha256 === pair.p33_context_sha256
    && context.p33_problem_sha256 === pair.p33_problem_sha256
    && sameList(context.qualified_available_artifact_ids, pair.qualified_available_artifact_ids)
    && sameList(
      context.qualified_available_artifact_evidence_states,
      pair.qualified_available_artifact_evidence_states,
    )
    && sameList(
      context.qualified_available_artifact_provenance_sha256s,
      pair.qualified_available_artifact_provenance_sha256s,
    )
    && sameList(context.current_evidence_pinned_tool_ids, pair.current_evidence_pinned_tool_ids)
    && context.track === pair.track
    && context.track_configuration === pair.track_configuration
    && context.package_type === pair.package_type
    && context.iracing_build === pair.iracing_build
    && context.problem_family === pair.problem_family
    && context.problem_orientation === pair.problem_orientation
    && context.track_class === pair.track_class
    && context.phase === pair.phase
    && context.current_objective === pair.current_objective
    && context.build_review_state === pair.build_review_state
    && context.driver_drift_state === pair.driver_drift_state
    && sameList(context.context_subgroup_keys, pair.context_subgroup_keys)
    && context.negative_control_condition === pair.negative_control_condition
    && negativeEvidenceDigestPresence;
}

function hasUnobservedBenefitClaim(projection: InvestigationImprovementProjection): boolean {
  const surfacedPairs = [
    projection.current_pair,
    projection.latest_completed_pair,
  ].filter((pair): pair is PairedInvestigationDecision => pair !== null);
  const frozenProse = [
    projection.difference_explanation,
    ...projection.safety_blockers,
    ...projection.readiness.blockers,
    ...projection.readiness.remaining_collection_missions,
    ...surfacedPairs.flatMap((pair) => [
      pair.baseline_decision.reason,
      pair.memory_decision.reason,
      pair.production_decision.reason,
    ]),
  ];
  const claimsBenefit = (item: string) => UNOBSERVED_BENEFIT.test(
    item.replace(NEGATED_BENEFIT, "explicit no-benefit boundary"),
  );
  if (frozenProse.some(claimsBenefit)) return true;
  const comparison = projection.latest_completed_comparison;
  return comparison !== null
    && (comparison.observability === "pending"
      || comparison.observability === "counterfactual_unobservable"
      || comparison.observability === "invalid")
    && comparison.blockers.some(claimsBenefit);
}

export function isInvestigationImprovementProjection(
  value: unknown,
  scope: InvestigationImprovementTrustScope,
): value is InvestigationImprovementProjection {
  if (!exactKeys(value, projectionKeys)
    || value.schema_version !== "p34.investigation-improvement-projection.v1"
    || !hash(value.projection_sha256)
    || !validDate(scope.generatedAt)
    || value.run_id !== scope.runId
    || value.session_id !== scope.sessionId
    || value.workspace_revision !== scope.workspaceRevision
    || !["available", "unavailable"].includes(String(value.state))
    || !["deterministic_baseline", "limited_attention"].includes(String(value.production_policy))
    || !memoryPolicyStates.has(String(value.memory_policy_state))
    || !(value.current_pair === null || validPairShape(value.current_pair))
    || !(value.current_context === null || validAdaptationContext(value.current_context))
    || !(value.current_pair_status === null || value.current_pair_status === "pending")
    || !(value.latest_completed_pair === null || validPairShape(value.latest_completed_pair))
    || !(value.latest_completed_comparison === null
      || validComparison(value.latest_completed_comparison))
    || !(value.latest_outcome_status === null
      || counterfactualStates.has(String(value.latest_outcome_status)))
    || typeof value.decisions_differ !== "boolean"
    || !safeText(value.difference_explanation)
    || !uniqueStrings(value.memory_evidence_record_ids)
    || !value.memory_evidence_record_ids.every((item) => P33_RECORD_ID.test(item))
    || !transferClasses.has(String(value.context_transfer_class))
    || !validReadiness(value.readiness)
    || !safeTexts(value.safety_blockers)
    || value.p19_authority_unchanged !== true
    || value.setup_authorized !== false
  ) return false;
  const projection = value as unknown as InvestigationImprovementProjection;
  if ((projection.current_pair === null) !== (projection.current_pair_status === null)) return false;
  if ((projection.current_pair === null) !== (projection.current_context === null)) return false;
  const completedParts = [
    projection.latest_completed_pair,
    projection.latest_completed_comparison,
    projection.latest_outcome_status,
  ];
  if (!completedParts.every((item) => item === null)
    && !completedParts.every((item) => item !== null)) return false;
  if (projection.state === "available"
    && projection.current_pair === null
    && projection.latest_completed_comparison === null) return false;
  if (projection.current_pair !== null
    && !validCurrentPair(projection.current_pair, scope)) return false;
  if (projection.current_pair !== null && projection.current_context !== null
    && !contextMatchesPair(projection.current_context, projection.current_pair)) return false;
  const surfacedPair = projection.current_pair ?? projection.latest_completed_pair;
  if (surfacedPair !== null && (
    projection.decisions_differ !== executableDecisionsDiffer(
      surfacedPair.baseline_decision,
      surfacedPair.memory_decision,
    )
    || !sameList(projection.memory_evidence_record_ids, surfacedPair.memory_records_consulted)
    || projection.context_transfer_class !== surfacedPair.context_transfer_class
  )) return false;
  if (projection.latest_completed_comparison !== null) {
    const completedPair = projection.latest_completed_pair;
    const comparison = projection.latest_completed_comparison;
    if (completedPair === null
      || comparison.pair_id !== completedPair.pair_id
      || comparison.pair_sha256 !== completedPair.pair_sha256
      || comparison.investigation_id !== completedPair.investigation_id
      || comparison.activation_protocol_id !== completedPair.activation_protocol_id
      || comparison.activation_protocol_sha256 !== completedPair.activation_protocol_sha256
      || comparison.decision_frozen_at !== completedPair.decision_frozen_at
      || comparison.context_identity_sha256 !== completedPair.p33_context_sha256
      || comparison.problem_family !== completedPair.problem_family
      || comparison.objective !== completedPair.current_objective
      || comparison.context_transfer_class !== completedPair.context_transfer_class
      || !sameList(comparison.subgroup_keys, completedPair.context_subgroup_keys)
      || projection.latest_outcome_status !== comparison.observability) return false;
  }
  if (projection.state === "unavailable" && (
    projection.current_pair !== null
    || projection.current_context !== null
    || projection.current_pair_status !== null
    || projection.latest_completed_pair !== null
    || projection.latest_completed_comparison !== null
    || projection.latest_outcome_status !== null
    || projection.decisions_differ
    || projection.memory_evidence_record_ids.length > 0
    || projection.safety_blockers.length === 0
  )) return false;
  const expectedPolicy = projection.memory_policy_state === "shadow_only"
    ? "deterministic_baseline" : "limited_attention";
  if (projection.production_policy !== expectedPolicy
    || projection.readiness.production_policy !== projection.production_policy
    || projection.readiness.memory_policy_state !== projection.memory_policy_state
    || (projection.current_pair !== null && (
      projection.current_pair.activation_state !== projection.memory_policy_state
      || projection.current_pair.production_policy_kind !== projection.production_policy
      || (projection.current_pair.activation_state === "limited_attention" && (
        projection.current_pair.activation_decision_id
          !== projection.readiness.effective_activation_decision_id
        || projection.current_pair.activation_decision_sha256
          !== projection.readiness.effective_activation_decision_sha256
      ))
    ))
    || hasUnobservedBenefitClaim(projection)) return false;
  return true;
}

function authorityIdentityBody(identity: Record<string, unknown>): Record<string, unknown> {
  const excluded = new Set([
    "objective_id", "investigation_id", "workspace_revision",
    "learning_history_revision", "learning_ledger_head_sha256",
    "learning_projection_sha256", "run_sentinel_sha256", "p35_assessment_sha256",
  ]);
  return Object.fromEntries(
    Object.entries(identity).filter(([key]) => !excluded.has(key)),
  );
}

async function validContentIdentity(
  value: Record<string, unknown>,
  idKey: string,
  digestKey: string,
  idPrefix: string,
): Promise<boolean> {
  const body = { ...value };
  const id = body[idKey];
  const digest = body[digestKey];
  delete body[idKey];
  delete body[digestKey];
  const expected = await canonicalInvestigationImprovementSha256(body);
  return digest === expected && id === `${idPrefix}${expected.slice(0, 24)}`;
}

async function expectedProductionAction(
  workspace: Record<string, unknown>,
): Promise<readonly [string, string] | null> {
  if (record(workspace.current_subgoal)
    && nonempty(workspace.current_subgoal.selected_tool)) {
    return ["inspect_tool", workspace.current_subgoal.selected_tool];
  }
  if (!record(workspace.folded_state)) return null;
  const folded = workspace.folded_state;
  if (!nonempty(folded.investigation_id)
    || !nonnegativeInteger(folded.last_sequence)
    || !Array.isArray(folded.driver_answers)) return null;
  if (folded.pending_driver_question_id !== null || folded.driver_answers.length === 0) {
    const actionId = nonempty(folded.pending_driver_question_id)
      ? folded.pending_driver_question_id
      : `ccq_${(await canonicalJsonSha256([
        folded.investigation_id,
        folded.last_sequence + 1,
      ])).slice(0, 20)}`;
    return ["ask_driver", actionId];
  }
  if (!record(workspace.terminal_decision)
    || !nonempty(workspace.terminal_decision.kind)
    || !nonempty(workspace.terminal_decision.instruction)) {
    return null;
  }
  const terminal = workspace.terminal_decision;
  const kind = terminal.kind === "no_call" ? "no_call" : "observe_only";
  const digest = await canonicalJsonSha256([terminal.kind, terminal.instruction]);
  return [kind, `terminal:${terminal.kind}:${digest.slice(0, 24)}`];
}

function uniqueInOrder(values: readonly string[]): string[] {
  return [...new Set(values.filter((item) => item.length > 0))];
}

function qualifiedCurrentEntries(
  workspace: Record<string, unknown>,
): Array<Record<string, unknown>> | null {
  if (!record(workspace.identity)
    || !record(workspace.evidence_index)
    || !Array.isArray(workspace.evidence_index.entries)) return null;
  const identity = workspace.identity;
  return workspace.evidence_index.entries.filter((item): item is Record<string, unknown> => (
    record(item)
    && !String(item.producer_id).startsWith("p35.")
    && QUALIFIED_ARTIFACT_STATES.has(String(item.evidence_state))
    && Array.isArray(item.blocker_reasons)
    && item.blocker_reasons.length === 0
    && item.source_provenance_available === true
    && item.run_id === identity.run_id
    && item.session_id === identity.session_id
    && item.setup_id === identity.setup_id
    && item.workspace_run_id === identity.run_id
    && item.workspace_session_id === identity.session_id
    && item.workspace_setup_id === identity.setup_id
    && item.source_run_id === identity.run_id
    && item.source_session_id === identity.session_id
    && item.source_setup_id === identity.setup_id
    && item.source_setup_sha256 === identity.setup_snapshot_sha256
    && item.source_build_context_sha256 === identity.vehicle_runtime_identity_hash
  ));
}

function selectedToolEntries(
  entries: Array<Record<string, unknown>>,
  toolId: string,
  causeIds: readonly string[],
  driverAnswers: readonly string[],
): Array<Record<string, unknown>> {
  const answer = driverAnswers.length > 0
    ? driverAnswers[driverAnswers.length - 1] : null;
  const answerPhase = new Map<string, readonly string[]>([
    ["braking/entry", ["brak", "entry", "turn"]],
    ["center", ["center", "apex", "corner"]],
    ["exit/power", ["exit", "throttle", "power"]],
  ]).get(answer ?? "") ?? [];
  let selected: Array<Record<string, unknown>>;
  if (toolId === "inspect_data_quality") {
    selected = entries.filter((item) => (
      Array.isArray(item.blocker_reasons)
      && item.blocker_reasons.length > 0
      && !String(item.producer_id).startsWith("p32.")
      && item.producer_id !== "p26.component_state_unavailable"
    ));
  } else if (toolId === "inspect_lap_context") {
    selected = entries.filter((item) => item.producer_id === "p19.reasoning_snapshot"
      && ((Array.isArray(item.blocker_reasons) && item.blocker_reasons.length > 0)
        || item.evidence_state === "blocked_by_context"));
  } else if (toolId === "inspect_driver_execution") {
    selected = entries.filter((item) => item.producer_id === "p19.reasoning_snapshot"
      && (answerPhase.length === 0
        || answerPhase.some((token) => String(item.phase ?? "").toLowerCase().includes(token))));
  } else {
    const producerByTool = new Map<string, string>([
      ["inspect_lap_time_opportunity", "p32.lap_time_opportunity"],
      ["inspect_time_loss_origin", "p32.time_loss_origin"],
      ["inspect_corner_performance_chain", "p32.corner_performance_chain"],
      ["inspect_exit_carry", "p32.exit_carry"],
      ["inspect_path_efficiency", "p32.path_efficiency"],
      ["inspect_driver_vehicle_separation", "p32.driver_vehicle_separation"],
      ["inspect_track_demand", "p32.track_demand"],
      ["inspect_component_performance_link", "p32.component_performance_link"],
      ["inspect_objective_tradeoff", "p32.objective_envelope"],
    ]);
    const producer = producerByTool.get(toolId);
    if (producer !== undefined) {
      const producerEntries = entries.filter((item) => item.producer_id === producer);
      if (toolId === "inspect_driver_vehicle_separation" && answerPhase.length > 0) {
        const scoped = producerEntries.filter((item) => (
          answerPhase.some((token) => String(item.phase ?? "").toLowerCase().includes(token))
          || item.evidence_state === "unavailable"
        ));
        selected = scoped.length > 0 ? scoped : producerEntries;
      } else selected = producerEntries;
    } else if (toolId === "inspect_p19_causes") {
      selected = entries.filter((item) => item.producer_id === "p19.reasoning_snapshot"
        && (causeIds.length === 0
          || item.polarity === "contradiction"
          || (Array.isArray(item.component_ids) && item.component_ids.length > 0)));
    } else if (toolId === "inspect_mechanism_episodes") {
      selected = entries.filter((item) => item.producer_id === "p20.mechanism_episode");
    } else if (toolId === "inspect_component_state") {
      const unavailable = entries.filter(
        (item) => item.producer_id === "p26.component_state_unavailable",
      );
      selected = unavailable.length > 0 ? unavailable : entries.filter((item) => (
        Array.isArray(item.component_ids)
        && item.component_ids.length > 0
        && !String(item.producer_id).startsWith("p32.")
      ));
    } else if (toolId === "inspect_controlled_history") {
      selected = entries.filter(
        (item) => Array.isArray(item.control_keys) && item.control_keys.length > 0,
      );
    } else {
      selected = entries.filter(
        (item) => Array.isArray(item.blocker_reasons) && item.blocker_reasons.length > 0,
      );
    }
  }
  return selected.slice(0, 16);
}

function expectedCurrentEvidencePin(
  workspace: Record<string, unknown>,
  pair: PairedInvestigationDecision,
  qualifiedArtifactIds: readonly string[],
): string[] | null {
  if (!record(workspace.current_subgoal)) return [];
  if (!record(workspace.folded_state)
    || !Array.isArray(workspace.folded_state.hypotheses)
    || !Array.isArray(workspace.folded_state.driver_answers)
    || !Array.isArray(workspace.current_subgoal.distinguishes_cause_ids)
    || !nonempty(workspace.current_subgoal.selected_tool)) return null;
  const causeIds = workspace.current_subgoal.distinguishes_cause_ids;
  if (!causeIds.every(nonempty)) return null;
  const currentCauseArtifactIds = new Set<string>();
  for (const item of workspace.folded_state.hypotheses) {
    if (!record(item) || !nonempty(item.cause_id)
      || !Array.isArray(item.support_artifact_ids)
      || !Array.isArray(item.contradiction_artifact_ids)) return null;
    if (!causeIds.includes(item.cause_id)) continue;
    for (const artifactId of [...item.support_artifact_ids, ...item.contradiction_artifact_ids]) {
      if (!nonempty(artifactId)) return null;
      currentCauseArtifactIds.add(artifactId);
    }
  }
  if (!record(workspace.evidence_index)
    || !Array.isArray(workspace.evidence_index.entries)) return null;
  const entries = workspace.evidence_index.entries.filter((item): item is Record<string, unknown> => (
    record(item) && !String(item.producer_id).startsWith("p35.")
  ));
  const selected = selectedToolEntries(
    entries,
    workspace.current_subgoal.selected_tool,
    causeIds,
    workspace.folded_state.driver_answers.filter(nonempty),
  );
  const qualified = new Set(qualifiedArtifactIds);
  const pinsBaseline = currentCauseArtifactIds.size > 0 && selected.some((item) => (
    nonempty(item.artifact_id)
    && currentCauseArtifactIds.has(item.artifact_id)
    && qualified.has(item.artifact_id)
  ));
  return pinsBaseline && pair.eligible_tool_ids.includes(workspace.current_subgoal.selected_tool)
    ? [workspace.current_subgoal.selected_tool] : [];
}

function currentFutureMemoryCohort(
  learningPrior: CrewChiefLearningPrior,
  decisionFrozenAt: string,
): Array<{ id: string; completedAt: string }> | null {
  const ids = learningPrior.useful_prior_investigations.map((item) => item.experience_id);
  if (new Set(ids).size !== ids.length) return null;
  return learningPrior.useful_prior_investigations
    .filter((item) => Date.parse(item.outcome.completed_at) >= Date.parse(decisionFrozenAt))
    .map((item) => ({ id: item.experience_id, completedAt: item.outcome.completed_at }));
}

async function expectedNegativeControlEvidence(
  pair: PairedInvestigationDecision,
  learningPrior: CrewChiefLearningPrior,
): Promise<InvestigationNegativeControlEvidence | null> {
  if (pair.negative_control_condition === null) return null;
  const transfers = learningPrior.context_transfers;
  const componentHistoryIds = uniqueInOrder(learningPrior.car_response_history.flatMap(
    (item) => item.source_experience_ids,
  ));
  const physicalMismatches = uniqueInOrder(transfers.flatMap((item) => (
    item.level === "weak"
      ? item.mismatched_dimensions.filter((dimension) => (
        P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS.has(dimension)
      )) : []
  )));
  const future = currentFutureMemoryCohort(learningPrior, pair.decision_frozen_at);
  if (future === null) return null;
  return {
    condition: pair.negative_control_condition,
    p33_projection_sha256: learningPrior.projection_sha256,
    p33_state: learningPrior.state,
    context_transfer_record_ids: transfers.map((item) => item.experience_id),
    context_transfer_levels: transfers.map((item) => item.level),
    useful_prior_experience_ids: learningPrior.useful_prior_investigations.map(
      (item) => item.experience_id,
    ),
    component_history_experience_ids: componentHistoryIds,
    physical_scope_mismatch_dimensions: physicalMismatches,
    recurrence_class: learningPrior.recurrence.classification,
    corruption_blocker_sha256s: learningPrior.state === "blocked"
      ? await Promise.all(learningPrior.blocker_reasons.map((item) => (
        canonicalJsonSha256(item)
      ))) : [],
    future_memory_record_ids: future.map((item) => item.id),
    future_memory_record_completed_ats: future.map((item) => item.completedAt),
    driver_drift_state: pair.driver_drift_state,
  };
}

function expectedNegativeControlCondition(
  pair: PairedInvestigationDecision,
  learningPrior: CrewChiefLearningPrior,
): string | null {
  const transfers = learningPrior.context_transfers;
  const blockedTransfer = transfers.some((item) => item.level === "blocked");
  const weakTransfer = transfers.some((item) => item.level === "weak");
  const physicalMismatch = transfers.some((item) => item.level === "weak"
    && item.mismatched_dimensions.some((dimension) => (
      P34_PHYSICAL_SCOPE_MISMATCH_DIMENSIONS.has(dimension)
    )));
  if (pair.future_memory_record_ids.length > 0) return "future_memory_record";
  if (pair.driver_drift_state === "material_drift") return "material_driver_drift";
  if (learningPrior.state === "blocked") return "corrupt_history";
  if (blockedTransfer
    && pair.build_review_state !== "future_unreviewed_build"
    && pair.driver_drift_state === "stable") return "incompatible_history";
  if (weakTransfer
    && pair.problem_orientation === "vehicle"
    && learningPrior.car_response_history.length > 0
    && learningPrior.useful_prior_investigations.length === 0
    && !physicalMismatch) return "generic_component_knowledge_only";
  if (weakTransfer && physicalMismatch
    && learningPrior.recurrence.classification !== "new_problem") {
    return "same_words_different_physical_scope";
  }
  if (pair.context_transfer_class === "none"
    && learningPrior.useful_prior_investigations.length === 0
    && transfers.length === 0) return "no_relevant_history";
  return null;
}

function currentMemoryDecisionMatchesPrior(
  pair: PairedInvestigationDecision,
  learningPrior: CrewChiefLearningPrior,
): boolean {
  const differs = executableDecisionsDiffer(pair.baseline_decision, pair.memory_decision);
  const completionById = new Map(learningPrior.useful_prior_investigations.map(
    (item) => [item.experience_id, item.outcome.completed_at],
  ));
  if (!pair.memory_records_consulted.every((item) => {
    const completedAt = completionById.get(item);
    return completedAt !== undefined
      && Date.parse(completedAt) < Date.parse(pair.decision_frozen_at);
  })) return false;
  if (pair.memory_records_consulted.length === 0) return !differs;
  if (learningPrior.state !== "available"
    || !["exact", "compatible"].includes(learningPrior.context_transfer_level)
    || learningPrior.driver_tendencies.some((item) => item.state === "changed_behavior")) {
    return false;
  }
  const transfers = new Map(learningPrior.context_transfers.map(
    (item) => [item.experience_id, item],
  ));
  if (!pair.memory_records_consulted.every((item) => {
    const transfer = transfers.get(item);
    return transfer !== undefined
      && ["exact", "compatible"].includes(transfer.level)
      && transfer.drift_reasons.length === 0
      && transfer.blocker_reasons.length === 0;
  })) return false;
  return learningPrior.recommended_attention_order.some((item) => (
    item.tool_id === pair.memory_decision.action_id
    && item.safety_band === "performance_measurement"
    && item.transfer_level === pair.context_transfer_class
    && sameList(item.source_experience_ids, pair.memory_records_consulted)
    && (item.learned_rank_within_band < item.baseline_rank_within_band) === differs
    && item.baseline_rank_within_band === PERFORMANCE_REORDER_GROUP.indexOf(
      item.tool_id as (typeof PERFORMANCE_REORDER_GROUP)[number],
    ) + 1
  ));
}

function expectedDriverDriftState(
  pair: PairedInvestigationDecision,
  learningPrior: CrewChiefLearningPrior,
): "stable" | "material_drift" | "unknown" {
  if (learningPrior.driver_tendencies.some((item) => item.state === "changed_behavior")) {
    return "material_drift";
  }
  const consulted = new Set(pair.memory_records_consulted);
  const selectedTransfers = learningPrior.context_transfers.filter(
    (item) => consulted.has(item.experience_id),
  );
  const transfers = selectedTransfers.length > 0
    ? selectedTransfers : learningPrior.context_transfers;
  return transfers.length > 0 && transfers.every((item) => (
    item.drift_reasons.length === 0
    && item.matching_dimensions.includes("driver_execution_state")
    && !item.mismatched_dimensions.includes("driver_execution_state")
  )) ? "stable" : "unknown";
}

function expectedBuildReviewState(
  pair: PairedInvestigationDecision,
  learningPrior: CrewChiefLearningPrior,
  blockerReasons: readonly string[],
): "same_build" | "future_unreviewed_build" {
  if (blockerReasons.some((item) => {
    const normalized = item.toLowerCase();
    return normalized.includes("future") && normalized.includes("build");
  })) return "future_unreviewed_build";
  const consulted = new Set(pair.memory_records_consulted);
  const selectedTransfers = learningPrior.context_transfers.filter(
    (item) => consulted.has(item.experience_id),
  );
  const transfers = selectedTransfers.length > 0
    ? selectedTransfers : learningPrior.context_transfers;
  return transfers.some((item) => item.mismatched_dimensions.includes("iRacing_build"))
    ? "future_unreviewed_build" : "same_build";
}

function expectedCurrentTransferClass(
  pair: PairedInvestigationDecision,
  learningPrior: CrewChiefLearningPrior,
  currentEvidencePin: readonly string[],
): string | null {
  const differs = executableDecisionsDiffer(pair.baseline_decision, pair.memory_decision);
  let transfer: string = "none";
  if (pair.memory_records_consulted.length > 0) {
    const attention = learningPrior.recommended_attention_order.find((item) => (
      item.tool_id === pair.memory_decision.action_id
      && sameList(item.source_experience_ids, pair.memory_records_consulted)
    ));
    if (!attention) return null;
    transfer = attention.transfer_level;
  } else if (pair.baseline_decision.action_id === "inspect_driver_vehicle_separation"
    && pair.context_transfer_class === "blocked") {
    transfer = "blocked";
  } else if (currentEvidencePin.length > 0 || learningPrior.state === "blocked"
    || learningPrior.context_transfers.some((item) => item.level === "blocked")) {
    transfer = "blocked";
  } else if (learningPrior.context_transfers.some((item) => item.level === "weak")) {
    transfer = "weak";
  }
  if (pair.future_memory_record_ids.length > 0
    || pair.build_review_state === "future_unreviewed_build"
    || pair.driver_drift_state === "material_drift"
    || (pair.driver_drift_state === "unknown" && differs)) return "blocked";
  return transfer;
}

export async function hasCanonicalInvestigationImprovementDigests(
  value: unknown,
  workspace: unknown,
): Promise<boolean> {
  if (!record(value)
    || !record(workspace)
    || !record(workspace.identity)
    || !record(workspace.evidence_index)
    || !record(workspace.terminal_decision)
    || !record(workspace.learning_prior)
    || !uniqueStrings(workspace.p19_cause_ids)
    || !uniqueStrings(workspace.p19_contradiction_artifact_ids)) return false;
  try {
    const projectionBody = { ...value };
    delete projectionBody.projection_sha256;
    if (await canonicalInvestigationImprovementSha256(projectionBody)
      !== value.projection_sha256) return false;
    const pairValues = [value.current_pair, value.latest_completed_pair]
      .filter((item): item is Record<string, unknown> => record(item));
    for (const pair of pairValues) {
      if (!validPairShape(pair)) return false;
      if (!await validContentIdentity(pair, "pair_id", "pair_sha256", "p34pair_")) {
        return false;
      }
    }
    if (record(value.latest_completed_comparison)) {
      if (!validComparison(value.latest_completed_comparison)
        || !await validContentIdentity(
          value.latest_completed_comparison,
          "comparison_id",
          "comparison_sha256",
          "p34cmp_",
        )) return false;
    }
    if (record(value.current_context)) {
      if (!validAdaptationContext(value.current_context)) return false;
      const contextBody: Record<string, unknown> = { ...value.current_context };
      delete contextBody.context_binding_sha256;
      if (await canonicalInvestigationImprovementSha256(contextBody)
        !== value.current_context.context_binding_sha256) return false;
    }
    if (record(value.current_pair)) {
      const identity = workspace.identity;
      const pair = value.current_pair as unknown as PairedInvestigationDecision;
      const learningPrior = workspace.learning_prior as unknown as CrewChiefLearningPrior;
      if (!record(workspace.folded_state)
        || !Array.isArray(workspace.folded_state.hypotheses)
        || !Array.isArray(workspace.folded_state.completed_tool_ids)
        || !Array.isArray(workspace.available_tools)
        || !Array.isArray(workspace.evidence_index.entries)
        || !validDate(workspace.generated_at)) return false;
      const authorityRevision = await canonicalJsonSha256(authorityIdentityBody(identity));
      const p19CauseStates = workspace.folded_state.hypotheses.map((item) => {
        if (!record(item) || !nonempty(item.cause_id) || !nonempty(item.p19_state)) {
          throw new TypeError("Invalid current P19 cause state.");
        }
        return [item.cause_id, item.p19_state];
      });
      const currentTruth = await canonicalJsonSha256({
        identity,
        evidence_index_sha256: workspace.evidence_index.index_hash,
        terminal_decision: workspace.terminal_decision,
        p19_cause_ids: workspace.p19_cause_ids,
        p19_cause_states: p19CauseStates,
        p19_contradiction_artifact_ids: workspace.p19_contradiction_artifact_ids,
      });
      const expectedAction = await expectedProductionAction(workspace);
      const entries = qualifiedCurrentEntries(workspace);
      if (entries === null) return false;
      const qualifiedIds = entries.map((entry) => String(entry.artifact_id));
      const qualifiedStates = entries.map((entry) => String(entry.evidence_state));
      const qualifiedProvenance = await Promise.all(
        entries.map((entry) => canonicalEngineeringLearningSha256(entry)),
      );
      const expectedPin = expectedCurrentEvidencePin(workspace, pair, qualifiedIds);
      const future = currentFutureMemoryCohort(learningPrior, pair.decision_frozen_at);
      const expectedNegativeEvidence = await expectedNegativeControlEvidence(pair, learningPrior);
      const expectedCondition = expectedNegativeControlCondition(pair, learningPrior);
      const negativeEvidenceSha256 = pair.negative_control_evidence === null
        ? null : await canonicalInvestigationImprovementSha256(pair.negative_control_evidence);
      if (pair.authority_revision !== authorityRevision
        || pair.current_truth_sha256 !== currentTruth
        || expectedAction === null
        || pair.production_decision.decision_kind !== expectedAction[0]
        || pair.production_decision.action_id !== expectedAction[1]
        || pair.p19_snapshot_sha256 !== identity.reasoning_snapshot_sha256
        || pair.p20_projection_sha256 !== identity.p20_state_revision
        || pair.p26_projection_sha256 !== identity.p26_knowledge_graph_sha256
        || pair.p32_projection_sha256 !== identity.p32_projection_sha256
        || pair.p33_projection_sha256 !== learningPrior.projection_sha256
        || pair.p33_history_revision !== identity.learning_history_revision
        || pair.p33_ledger_head_sha256 !== identity.learning_ledger_head_sha256
        || pair.p33_context_sha256 !== learningPrior.current_context_sha256
        || pair.p33_problem_sha256 !== learningPrior.current_problem_sha256
        || !sameList(
          pair.available_tool_ids,
          workspace.available_tools
            .filter((tool) => record(tool) && !P35_INSPECTION_TOOL_IDS.has(String(tool.tool_id)))
            .map((tool) => record(tool) ? tool.tool_id : null),
        )
        || !sameList(
          pair.available_artifact_ids,
          workspace.evidence_index.entries
            .filter((entry) => record(entry) && !String(entry.producer_id).startsWith("p35."))
            .map((entry) => record(entry) ? entry.artifact_id : null),
        )
        || !sameList(pair.completed_tool_ids, workspace.folded_state.completed_tool_ids)
        || !sameList(pair.qualified_available_artifact_ids, qualifiedIds)
        || !sameList(pair.qualified_available_artifact_evidence_states, qualifiedStates)
        || !sameList(pair.qualified_available_artifact_provenance_sha256s, qualifiedProvenance)
        || expectedPin === null
        || !sameList(pair.current_evidence_pinned_tool_ids, expectedPin)
        || pair.driver_drift_state !== expectedDriverDriftState(pair, learningPrior)
        || pair.build_review_state !== expectedBuildReviewState(
          pair,
          learningPrior,
          Array.isArray(workspace.blocker_reasons)
            ? workspace.blocker_reasons.filter(nonempty) : [],
        )
        || pair.context_transfer_class
          !== expectedCurrentTransferClass(pair, learningPrior, expectedPin)
        || future === null
        || !sameList(pair.future_memory_record_ids, future.map((item) => item.id))
        || pair.negative_control_condition !== expectedCondition
        || !deepEqual(pair.negative_control_evidence, expectedNegativeEvidence)
        || !currentMemoryDecisionMatchesPrior(pair, learningPrior)
        || !record(value.current_context)
        || value.current_context.negative_control_evidence_sha256 !== negativeEvidenceSha256
        || Date.parse(pair.decision_frozen_at) > Date.parse(workspace.generated_at)) return false;
    }
    return true;
  } catch {
    return false;
  }
}
