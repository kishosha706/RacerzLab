import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

const HASH = /^[0-9a-f]{64}$/;
const ORIGINS = new Set(["local_generation", "carried_in", "amplified", "recovered", "surrendered", "unavailable"]);
const REPEATABILITY = new Set(["repeatable", "observed_once", "below_noise", "blocked"]);
const SEPARATION_RESULTS = new Set([
  "driver_execution_changed",
  "vehicle_response_changed_with_matched_inputs",
  "mixed_change",
  "context_contaminated",
  "unresolved",
]);
const EDGE_KINDS = new Set([
  "observed_precedes",
  "co_observed_with",
  "measured_time_consequence",
  "time_effect_persists_into",
  "expected_to_influence",
  "controlled_response_observed",
  "confounded_by",
  "contradicted_by",
]);
const COMPONENT_SUPPORT = new Map([
  ["mechanically_relevant", "knowledge_only"],
  ["response_supported", "observation_only"],
  ["controlled_response_observed", "controlled_history"],
]);
const CREW_MECHANISMS = new Set([
  "driver_execution", "braking_response", "corner_rotation", "tire_state", "damper_response",
  "platform_response", "resistance_scrub_like", "powertrain_response", "stint_trend", "sim_integrity",
]);
const FORBIDDEN_PERFORMANCE_CLAIM = /\b(?:caused?|due\s+to|because\s+of|responsible\s+for|proves?|produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from)|(?:creates?|created)\b.{0,48}\b(?:loss|gain|delta|time)|(?:loss|gain|delta|time)\b.{0,48}\b(?:causes?|caused|creates?|created)|(?:confirms?|confirmed)\b.{0,64}\b(?:cause|caused|created)|optimal(?:\s+setup)?|guaranteed(?:\s+achievable)?|definitive(?:ly)?|exact\s+(?:drag|cda|aero(?:dynamic)?\s+(?:force|coefficient)))\b/i;
const NEGATED_CAUSAL_BOUNDARY = /\b(?:(?:does|do|did)\s+not|cannot|can\s+not|(?:is|are|was|were)\s+not|no|none\s+is)\s+(?:establish(?:ed)?|prove(?:d)?|show(?:n)?|claim(?:ed)?)?\s*(?:as\s+)?(?:a\s+|the\s+)?(?:component\s+)?(?:cause|causation)\b/gi;
const NEGATED_CAUSAL_OUTCOME = /\b(?:(?:does|do|did)\s+not|cannot|can\s+not|(?:is|are|was|were)\s+not)\s+(?:produc(?:e|ed|es|ing)|generat(?:e|ed|es|ing)|result(?:ed|s|ing)?\s+(?:in|from))\b/gi;

const record = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const integer = (value) => Number.isInteger(value) && value >= 0;
const nullableFinite = (value) => value === null || finite(value);
const nullableText = (value) => value === null || safeText(value);
const safeText = (value) => typeof value === "string"
  && value.trim().length > 0
  && !hasSetupAuthorityDirective(value);
const safeNarrative = (value) => safeText(value)
  && !FORBIDDEN_PERFORMANCE_CLAIM.test(value
    .replace(NEGATED_CAUSAL_BOUNDARY, "explicit non-causal boundary")
    .replace(NEGATED_CAUSAL_OUTCOME, "explicit non-causal outcome boundary"));
const unique = (values) => new Set(values).size === values.length;
const safeTexts = (value, { allowEmpty = true } = {}) => Array.isArray(value)
  && (allowEmpty || value.length > 0)
  && value.every((item) => safeText(item))
  && unique(value);
const plainTexts = (value) => Array.isArray(value)
  && value.every((item) => typeof item === "string" && item.trim().length > 0)
  && unique(value);
const integerList = (value, { allowEmpty = true } = {}) => Array.isArray(value)
  && (allowEmpty || value.length > 0)
  && value.every(integer)
  && unique(value);
const fraction = (value) => nullableFinite(value) && (value === null || (value >= 0 && value <= 1));
const percentage = (value) => finite(value) && value >= 0 && value <= 100;
const nullableNonNegative = (value) => nullableFinite(value) && (value === null || value >= 0);
const safeFinitePairs = (value) => Array.isArray(value)
  && value.every((item) => Array.isArray(item) && item.length === 2 && safeText(item[0]) && finite(item[1]));

function validKnowledge(value, kind) {
  if (!record(value)) return false;
  if (kind === "principle") {
    return safeText(value.principle_id)
      && safeText(value.statement)
      && safeTexts(value.applicable_phases, { allowEmpty: false })
      && safeTexts(value.applicable_objectives, { allowEmpty: false })
      && safeTexts(value.required_evidence, { allowEmpty: false })
      && safeTexts(value.forbidden_claims, { allowEmpty: false })
      && safeTexts(value.source_ids, { allowEmpty: false })
      && value.authority === "knowledge_only";
  }
  return safeText(value.mechanism_id)
    && safeText(value.statement)
    && safeTexts(value.operating_phases, { allowEmpty: false })
    && safeTexts(value.required_telemetry, { allowEmpty: false })
    && safeTexts(value.derived_metrics, { allowEmpty: false })
    && safeTexts(value.driver_confounders, { allowEmpty: false })
    && safeTexts(value.context_blockers, { allowEmpty: false })
    && safeTexts(value.p20_mechanism_families)
    && safeTexts(value.p26_component_families)
    && safeTexts(value.performance_outcomes, { allowEmpty: false })
    && safeTexts(value.countereffects, { allowEmpty: false })
    && safeTexts(value.forbidden_claims, { allowEmpty: false })
    && safeTexts(value.source_ids, { allowEmpty: false })
    && value.authority === "knowledge_only";
}

function validOutcome(value) {
  return record(value)
    && safeText(value.outcome_id)
    && safeText(value.label)
    && safeTexts(value.measured_by, { allowEmpty: false })
    && safeTexts(value.protected_outcomes)
    && value.authority === "measurement_only";
}

function validOpportunity(value, scope, basis, knownMechanisms) {
  if (!record(value)) return false;
  const evidence = scope.opportunityEvidence?.get(value.opportunity_id);
  const sourceLaps = value.source_laps;
  const mappedMechanisms = unique(value.mechanism_candidates.map((item) => CREW_MECHANISMS.has(item) ? item : "unclassified"))
    ? value.mechanism_candidates.map((item) => CREW_MECHANISMS.has(item) ? item : "unclassified")
    : [...new Set(value.mechanism_candidates.map((item) => CREW_MECHANISMS.has(item) ? item : "unclassified"))];
  const evidenceIsAtomic = evidence === undefined || (
    record(evidence)
    && evidence.producer_id === "p32.lap_time_opportunity"
    && evidence.artifact_id === value.opportunity_id
    && evidence.run_id === scope.runId
    && evidence.session_id === scope.sessionId
    && evidence.setup_id === basis.setup_id
    && evidence.source_run_id === scope.runId
    && evidence.source_session_id === scope.sessionId
    && evidence.source_setup_id === basis.setup_id
    && evidence.source_setup_sha256 === scope.setupSnapshotHash
    && evidence.source_build_context_sha256 === scope.buildContextHash
    && evidence.workspace_run_id === scope.runId
    && evidence.workspace_session_id === scope.sessionId
    && evidence.workspace_setup_id === basis.setup_id
    && evidence.objective === scope.objectiveId
    && evidence.lap_pct_start === value.start_pct
    && evidence.lap_pct_end === value.end_pct
    && evidence.phase === value.phase
    && JSON.stringify(evidence.lap_numbers) === JSON.stringify(basis.source_lap_numbers)
    && JSON.stringify(evidence.source_channels) === JSON.stringify(value.source_channels)
    && JSON.stringify(evidence.component_ids) === JSON.stringify(value.component_candidates)
    && JSON.stringify(evidence.mechanism_ids) === JSON.stringify(mappedMechanisms)
    && evidence.authority_ceiling === "observation_only"
    && (value.attribution_state === "candidate_only"
      ? evidence.evidence_state === "observed_correlation"
      : evidence.evidence_state === "blocked_by_context" && evidence.blocker_reasons.some((item) => value.attribution_state !== "blocked_by_traffic" || /traffic/i.test(item)))
  );
  return safeText(value.opportunity_id)
    && percentage(value.start_pct)
    && percentage(value.end_pct)
    && value.start_pct <= value.end_pct
    && safeText(value.track_region)
    && nullableText(value.turn)
    && safeText(value.phase)
    && nullableFinite(value.local_delta_s)
    && nullableFinite(value.cumulative_delta_at_entry_s)
    && nullableFinite(value.cumulative_delta_at_exit_s)
    && ORIGINS.has(value.origin_kind)
    && nullableNonNegative(value.persistence_distance_pct)
    && (value.persistence_distance_pct === null || value.persistence_distance_pct <= 100)
    && nullableFinite(value.following_phase_effect_s)
    && (value.following_phase_start_pct === null || percentage(value.following_phase_start_pct))
    && (value.following_phase_end_pct === null || percentage(value.following_phase_end_pct))
    && ((value.following_phase_effect_s === null)
      === (value.following_phase_start_pct === null && value.following_phase_end_pct === null))
    && (value.following_phase_start_pct === null || value.following_phase_start_pct <= value.following_phase_end_pct)
    && REPEATABILITY.has(value.repeatability)
    && safeText(value.noise_basis)
    && integerList(sourceLaps, { allowEmpty: false })
    && sourceLaps.every((lap) => basis.source_lap_numbers.includes(lap) || basis.reference_lap_numbers.includes(lap))
    && safeTexts(value.source_channels)
    && safeText(value.driver_execution_state)
    && safeText(value.vehicle_response_state)
    && safeText(value.context_state)
    && ["candidate_only", "blocked_by_traffic", "blocked_by_context"].includes(value.attribution_state)
    && fraction(value.source_traffic_exposure_fraction)
    && fraction(value.reference_traffic_exposure_fraction)
    && safeTexts(value.mechanism_candidates)
    && value.mechanism_candidates.every((item) => knownMechanisms.has(item))
    && safeTexts(value.component_candidates)
    && (!value.attribution_state.startsWith("blocked_by_") || value.component_candidates.length === 0)
    && safeTexts(value.contradictions, { allowEmpty: false })
    && (value.attribution_state !== "blocked_by_traffic" || value.contradictions.some((item) => /traffic/i.test(item)))
    && value.setup_authorized === false
    && evidenceIsAtomic;
}

function validPhaseState(value) {
  if (value === null) return true;
  if (!record(value)) return false;
  const metrics = [
    value.elapsed_delta_s,
    value.speed_delta_mph,
    value.throttle_delta_pct,
    value.brake_delta_pct,
    value.steering_delta_deg,
    value.yaw_rate_delta,
    value.long_accel_delta,
    value.path_delta_m,
    value.line_separation_m,
  ];
  const measured = metrics.some((item) => item !== null);
  return safeText(value.phase)
    && percentage(value.start_pct)
    && percentage(value.end_pct)
    && value.start_pct <= value.end_pct
    && metrics.every(nullableFinite)
    && nullableNonNegative(value.line_separation_m)
    && fraction(value.driver_demand_source_coverage)
    && fraction(value.driver_demand_reference_coverage)
    && ["measured", "unavailable"].includes(value.evidence_state)
    && ((value.evidence_state === "measured") === measured)
    && safeTexts(value.source_channels)
    && safeTexts(value.blockers)
    && (measured || value.blockers.length > 0);
}

function validSeparation(value) {
  if (!record(value)) return false;
  const nullableBoolean = (item) => item === null || typeof item === "boolean";
  return safeText(value.separation_id)
    && safeText(value.phase)
    && [value.driver_demand_changed, value.vehicle_response_changed, value.line_changed, value.context_changed, value.time_changed].every(nullableBoolean)
    && SEPARATION_RESULTS.has(value.result)
    && safeTexts(value.support)
    && safeTexts(value.contradictions)
    && safeTexts(value.blockers)
    && (!["context_contaminated", "unresolved"].includes(value.result) || value.blockers.length > 0)
    && (value.result !== "vehicle_response_changed_with_matched_inputs"
      || (value.driver_demand_changed === false && value.line_changed === false && value.context_changed === false && value.vehicle_response_changed === true))
    && value.authority === "observation_only";
}

function validCornerChain(value, basis) {
  if (!record(value)) return false;
  const states = [
    value.approach_state,
    value.braking_state,
    value.entry_state,
    value.center_state,
    value.exit_state,
    value.carry_state,
  ];
  const separationDemandIsComplete = (separation) => {
    if (!["driver_execution_changed", "vehicle_response_changed_with_matched_inputs", "mixed_change"]
      .includes(separation.result)) return true;
    const phase = states.find((state) => record(state) && state.phase === separation.phase);
    return record(phase)
      && phase.driver_demand_source_coverage === 1
      && phase.driver_demand_reference_coverage === 1
      && [phase.throttle_delta_pct, phase.brake_delta_pct, phase.steering_delta_deg].every(finite);
  };
  return safeText(value.chain_id)
    && safeText(value.track_region)
    && nullableText(value.turn)
    && integerList(value.lap_numbers)
    && integerList(value.reference_lap_numbers)
    && value.lap_numbers.every((lap) => basis.source_lap_numbers.includes(lap))
    && value.reference_lap_numbers.every((lap) => basis.reference_lap_numbers.includes(lap))
    && states.every(validPhaseState)
    && nullableFinite(value.local_time_effect_s)
    && nullableFinite(value.downstream_time_effect_s)
    && Array.isArray(value.driver_vehicle_separation)
    && value.driver_vehicle_separation.every((item) => (
      validSeparation(item) && separationDemandIsComplete(item)
    ))
    && safeTexts(value.context)
    && safeTexts(value.contradictions, { allowEmpty: false })
    && value.authority === "observation_only";
}

function validTrackDemand(value, knownOpportunityIds) {
  return record(value)
    && fraction(value.full_throttle_fraction)
    && fraction(value.braking_fraction)
    && fraction(value.cornering_fraction)
    && nullableNonNegative(value.speed_min_mph)
    && nullableNonNegative(value.speed_max_mph)
    && (value.speed_min_mph === null || value.speed_max_mph === null || value.speed_min_mph <= value.speed_max_mph)
    && nullableNonNegative(value.median_corner_duration_s)
    && Array.isArray(value.following_straight_carry_lengths_pct)
    && value.following_straight_carry_lengths_pct.every((item) => finite(item) && item >= 0 && item <= 100)
    && fraction(value.combined_acceleration_fraction)
    && Array.isArray(value.platform_load_speed_bands_mph)
    && value.platform_load_speed_bands_mph.every((item) => finite(item) && item >= 0)
    && fraction(value.disturbance_exposure_fraction)
    && fraction(value.traffic_exposure_fraction)
    && ["observable", "short_run", "unavailable"].includes(value.tire_state_development)
    && plainTexts(value.shift_zones)
    && plainTexts(value.limiter_zones)
    && plainTexts(value.shift_limiter_zones)
    && JSON.stringify(value.shift_limiter_zones) === JSON.stringify(value.limiter_zones)
    && safeTexts(value.dominant_measured_opportunity_ids)
    && value.dominant_measured_opportunity_ids.every((item) => knownOpportunityIds.has(item))
    && safeTexts(value.source_channels)
    && safeTexts(value.blockers)
    && value.authority === "observation_only";
}

function validComponentInfluence(value, knownMechanisms) {
  return record(value)
    && safeText(value.influence_id)
    && safeText(value.component_id)
    && safeTexts(value.performance_mechanism_ids, { allowEmpty: false })
    && value.performance_mechanism_ids.every((item) => knownMechanisms.has(item))
    && safeTexts(value.expected_state_ids, { allowEmpty: false })
    && safeTexts(value.measurable_through, { allowEmpty: false })
    && COMPONENT_SUPPORT.has(value.runtime_support_state)
    && value.authority === COMPONENT_SUPPORT.get(value.runtime_support_state)
    && safeTexts(value.source_artifact_ids)
    && safeTexts(value.contradictions, { allowEmpty: false })
    && value.setup_authorized === false;
}

function validResponseRecord(value, scope) {
  return record(value)
    && safeText(value.record_id)
    && safeText(value.workflow_id)
    && safeTexts(value.context_run_ids, { allowEmpty: false })
    && value.context_run_ids.every((runId) => scope.scopeRunIds.has(runId))
    && safeText(value.control)
    && safeText(value.component)
    && safeText(value.expected_state)
    && safeText(value.observed_state)
    && safeText(value.time_origin)
    && nullableFinite(value.time_origin_pct)
    && (value.time_origin_pct === null || percentage(value.time_origin_pct))
    && safeText(value.phase_effect)
    && nullableFinite(value.phase_effect_s)
    && safeText(value.downstream_carry)
    && nullableFinite(value.downstream_carry_s)
    && safeText(value.performance_result)
    && safeTexts(value.countereffects)
    && safeText(value.mechanism_assessment)
    && safeText(value.control_response_assessment)
    && ["keep", "undo", "retest"].includes(value.policy_verdict)
    && value.exact_context === true
    && ((value.time_origin_pct === null) === (value.time_origin === "not_materialized_in_legacy_record"))
    && ((value.downstream_carry_s === null) === (value.downstream_carry === "not_materialized_in_legacy_record"))
    && value.setup_authorized === false;
}

/**
 * Validate the complete P32 runtime contract before any field is rendered.
 * @param {unknown} value
 * @param {{runId:string,sessionId:string,setupId:string,setupSnapshotHash:string,buildContextHash:string,objectiveId:string,p19Hash:string,p20Revision:string,p26Hash:string,projectionHash:string,p19Next:string,scopeRunIds?:ReadonlySet<string>,opportunityEvidence?:Map<string,unknown>}} scope
 * @returns {boolean}
 */
export function isPerformanceIntelligenceProjection(value, scope) {
  if (!record(value)
    || value.schema_version !== "p32.performance-intelligence.v1"
    || value.projection_sha256 !== scope.projectionHash
    || !HASH.test(value.projection_sha256)
    || value.run_id !== scope.runId
    || value.session_id !== scope.sessionId
    || value.objective_id !== scope.objectiveId
    || !safeText(value.knowledge_version)
    || value.p19_reasoning_snapshot_sha256 !== scope.p19Hash
    || value.p20_state_revision !== scope.p20Revision
    || value.p26_knowledge_graph_sha256 !== scope.p26Hash
    || value.authority !== "observation_only"
    || value.setup_authorized !== false
    || value.optimization_state !== "data_locked") return false;

  if (!Array.isArray(value.principles)
    || value.principles.length !== 12
    || !value.principles.every((item) => validKnowledge(item, "principle"))
    || !unique(value.principles.map((item) => item.principle_id))
    || !Array.isArray(value.mechanisms)
    || value.mechanisms.length === 0
    || !value.mechanisms.every((item) => validKnowledge(item, "mechanism"))
    || !unique(value.mechanisms.map((item) => item.mechanism_id))
    || !Array.isArray(value.outcomes)
    || value.outcomes.length === 0
    || !value.outcomes.every(validOutcome)
    || !unique(value.outcomes.map((item) => item.outcome_id))) return false;

  const knownMechanisms = new Set(value.mechanisms.map((item) => item.mechanism_id));
  const objective = value.objective_envelope;
  const basis = value.basis;
  const map = value.opportunity_map;
  if (!record(objective)
    || objective.objective_id !== scope.objectiveId
    || !safeTexts(objective.primary_outcomes, { allowEmpty: false })
    || !safeTexts(objective.protected_outcomes, { allowEmpty: false })
    || !safeTexts(objective.countereffect_limits, { allowEmpty: false })
    || !safeTexts(objective.measurement_requirements, { allowEmpty: false })
    || !safeText(objective.policy_note)
    || objective.physics_changes !== false
    || objective.setup_authorized !== false
    || !record(basis)
    || basis.run_id !== scope.runId
    || basis.setup_id !== scope.setupId
    || nullableText(basis.reference_run_id) === false
    || !safeText(basis.setup_id)
    || nullableText(basis.reference_setup_id) === false
    || !integerList(basis.source_lap_numbers)
    || !integerList(basis.reference_lap_numbers)
    || !HASH.test(basis.physical_alignment_identity)
    || !integer(basis.qualified_phase_segments)
    || !integer(basis.sample_count)
    || !safeTexts(basis.source_channels)
    || !safeText(basis.time_basis)
    || !safeText(basis.path_basis)
    || !fraction(basis.coverage)
    || !["same_run", "compatible", "unavailable"].includes(basis.comparison_compatibility)
    || !safeTexts(basis.context_blockers)
    || basis.materialization !== "narrow_run_owned_once"
    || !record(map)
    || map.run_id !== scope.runId
    || map.reference_run_id !== basis.reference_run_id
    || map.setup_id !== basis.setup_id
    || map.reference_setup_id !== basis.reference_setup_id
    || map.physical_alignment_identity !== basis.physical_alignment_identity
    || !Array.isArray(map.opportunities)
    || !safeFinitePairs(map.phase_totals_s)
    || !nullableFinite(map.total_measured_delta_s)
    || !fraction(map.coverage)
    || map.coverage !== basis.coverage
    || !safeText(map.noise_basis)
    || !safeTexts(map.context_blockers)
    || !nullableNonNegative(map.theoretical_composite_s)
    || map.theoretical_is_guaranteed !== false
    || map.setup_authorized !== false) return false;

  const scoped = {
    ...scope,
    scopeRunIds: scope.scopeRunIds ?? new Set([scope.runId]),
  };
  if (basis.reference_run_id !== null && !scoped.scopeRunIds.has(basis.reference_run_id)) return false;
  if (!map.opportunities.every((item) => validOpportunity(item, scoped, basis, knownMechanisms))
    || !unique(map.opportunities.map((item) => item.opportunity_id))) return false;
  const opportunityIds = new Set(map.opportunities.map((item) => item.opportunity_id));
  if (scope.opportunityEvidence) {
    if (scope.opportunityEvidence.size !== map.opportunities.length
      || [...scope.opportunityEvidence.keys()].some((id) => !opportunityIds.has(id))) return false;
  }
  if (!Array.isArray(value.corner_chains)
    || !value.corner_chains.every((item) => validCornerChain(item, basis))
    || !unique(value.corner_chains.map((item) => item.chain_id))
    || !validTrackDemand(value.track_demand, opportunityIds)
    || !Array.isArray(value.component_influences)
    || !value.component_influences.every((item) => validComponentInfluence(item, knownMechanisms))
    || !unique(value.component_influences.map((item) => item.influence_id))
    || !Array.isArray(value.response_records)
    || !value.response_records.every((item) => validResponseRecord(item, scoped))
    || !unique(value.response_records.map((item) => item.record_id))) return false;
  if (!["available", "unavailable"].includes(value.component_context_state)
    || !safeTexts(value.component_context_blockers)
    || (value.component_context_state === "unavailable"
      && (value.component_context_blockers.length === 0 || value.component_influences.length > 0 || value.response_records.length > 0))
    || (value.component_context_state === "available" && value.component_context_blockers.length > 0)) return false;

  const explanation = value.explanation_chain;
  const story = value.speed_story;
  if (!record(explanation)
    || !safeText(explanation.chain_id)
    || !safeTexts(explanation.node_ids, { allowEmpty: false })
    || !Array.isArray(explanation.edges)
    || !explanation.edges.every((edge) => record(edge)
      && safeText(edge.source_id)
      && safeText(edge.target_id)
      && explanation.node_ids.includes(edge.source_id)
      && explanation.node_ids.includes(edge.target_id)
      && EDGE_KINDS.has(edge.kind))
    || typeof explanation.branched !== "boolean"
    || !safeNarrative(explanation.strongest_contradiction)
    || explanation.p19_next_move !== scope.p19Next
    || explanation.setup_authority !== "p19_only"
    || !record(story)
    || ![
      story.what_costs_time,
      story.where_it_starts,
      story.what_carries,
      story.driver,
      story.car,
      story.systems,
      story.history,
      story.strongest_contradiction,
      story.attribution,
      story.source_context,
      story.reference_context,
      story.comparison_window,
    ].every(safeNarrative)
    || !nullableFinite(story.observed_difference_s)
    || !["loss", "gain", "unavailable"].includes(story.observed_direction)
    || !["candidate_only", "blocked_by_traffic", "blocked_by_context", "unavailable"].includes(story.attribution_state)
    || (story.observed_difference_s === null) !== (story.observed_direction === "unavailable")
    || (story.observed_difference_s !== null && story.observed_difference_s > 0 && story.observed_direction !== "loss")
    || (story.observed_difference_s !== null && story.observed_difference_s < 0 && story.observed_direction !== "gain")
    || (story.observed_difference_s === 0 && story.observed_direction !== "unavailable")
    || (story.attribution_state.startsWith("blocked_by_") && (!/blocked/i.test(story.attribution) || /\bcosts?\b/i.test(story.what_costs_time)))
    || (story.attribution_state === "blocked_by_traffic" && !/traffic/i.test(story.strongest_contradiction))
    || story.strongest_contradiction !== explanation.strongest_contradiction
    || story.next !== scope.p19Next
    || story.authority !== "observation_and_p19_projection"
    || !safeTexts(value.blockers)) return false;

  const measuredLossExists = map.opportunities.some((item) => item.local_delta_s !== null && item.local_delta_s > 0);
  const narratesLoss = /\b(?:costs?|loss|lost|slower)\b/i.test(story.what_costs_time)
    && !/\bno\s+(?:measured\s+)?(?:loss|opportunity)\b/i.test(story.what_costs_time);
  if (narratesLoss && !measuredLossExists) return false;
  const leading = map.opportunities[0];
  if (leading) {
    if (story.observed_difference_s !== leading.local_delta_s
      || story.attribution_state !== leading.attribution_state) return false;
  } else if (story.observed_difference_s !== null || story.attribution_state !== "unavailable") return false;
  const storyTrafficBlocked = story.attribution_state === "blocked_by_traffic";
  if (storyTrafficBlocked && (
    !/traffic/i.test(story.strongest_contradiction)
    || !/\b(?:none\s+is\s+established\s+as\s+cause|without\s+component\s+attribution|no\s+.+attribution|withheld|blocked)\b/i.test(story.systems)
  )) return false;

  return true;
}
