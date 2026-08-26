import type { EngineeringCaseRevision } from "../types/engineeringCase";
import { canonicalJsonSha256 } from "./canonicalJsonSha256";
import { engineeringCaseFloatKeys } from "./crewChiefResponseTrust";

const hash = /^[0-9a-f]{64}$/;
const caseId = /^p3543case_[0-9a-f]{24}$/;
const identifier = /^[a-z0-9][a-z0-9_.:-]*$/;
const responseArtifactId = /^p3542\.response:[0-9a-f]{24}$/;
const bridgeId = /^p351b_[0-9a-f]{24}$/;
const engineeringObjectives = new Set([
  "qualifying_peak",
  "race_long_run",
  "tire_conservation",
  "driver_confidence",
  "traffic_robustness",
  "superspeedway_stability",
  "fuel_strategy",
]);
const changeCategories = new Set([
  "initial",
  "evidence",
  "driver_intent",
  "investigation",
  "workflow",
  "controlled_outcome",
  "history",
  "setup",
  "scope",
  "rebuild",
]);
const criticStates = new Set([
  "pass",
  "blocked",
  "reinvestigate",
  "ask_driver",
  "unavailable",
]);
const readinessStates = new Set([
  "knowledge_only",
  "measurement_ready",
  "response_evidence_ready",
  "p19_testable",
  "blocked",
]);
const readinessAuthorities = new Set([
  "knowledge_only",
  "measurement_only",
  "exact_p19_projection",
]);
const missionAuthorities = new Set([
  "p19_exact_mirror",
  "p19_measurement_mirror",
  "navigation_only",
]);
const campaignStates = new Set([
  "pending",
  "rejected",
  "qualified",
  "duplicate",
  "corrupt",
]);
const deficitCodes = new Set([
  "CHANNEL_MISSING",
  "CHANNEL_UNHEALTHY",
  "WRONG_UPDATE_SEMANTIC",
  "PIT_SNAPSHOT_ONLY",
  "INSUFFICIENT_REPETITION",
  "INSUFFICIENT_CLEAN_LAPS",
  "TRAFFIC_CONTAMINATED",
  "SPEED_BAND_MISMATCH",
  "PHASE_MISMATCH",
  "SETUP_MISMATCH",
  "CASE_REVISION_MISMATCH",
  "RECORDING_NOT_INDEPENDENT",
  "REQUIRED_COUNTEREFFECT_MISSING",
  "EXACT_SEMANTIC_BRIDGE_MISSING",
  "EXACT_LEGAL_OPTION_MISSING",
  "P19_AUTHORITY_REQUIRED",
  "BUILD_APPLICABILITY_BLOCKED",
  "STRUCTURALLY_UNAVAILABLE",
]);
const recoveryStatuses = new Map([
  ["use_current_data", "available_now"],
  ["collect_more_laps", "requires_more_laps"],
  ["collect_new_run", "requires_new_run"],
  ["pit_snapshot", "pit_snapshot_only"],
  ["controlled_test", "controlled_test_required"],
  ["unavailable", "structurally_unavailable"],
]);

function record(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function safeText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function safeIdentifier(value: unknown): value is string {
  return typeof value === "string" && identifier.test(value);
}

function nullableText(value: unknown): value is string | null {
  return value === null || safeText(value);
}

function nullableIdentifier(value: unknown): value is string | null {
  return value === null || safeIdentifier(value);
}

function validHash(value: unknown): value is string {
  return typeof value === "string" && hash.test(value);
}

function nullableHash(value: unknown): value is string | null {
  return value === null || validHash(value);
}

function uniqueStrings(value: unknown, minimum = 0): value is string[] {
  return Array.isArray(value)
    && value.length >= minimum
    && value.every(safeText)
    && new Set(value).size === value.length;
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function validDeliveryDiagnostics(value: unknown): boolean {
  return value === null || (record(value)
    && finiteNumber(value.route_duration_ms)
    && value.route_duration_ms >= 0
    && Number.isInteger(value.run_intelligence_build_count_delta)
    && value.run_intelligence_build_count_delta >= 0
    && Number.isInteger(value.crew_workspace_build_count_delta)
    && value.crew_workspace_build_count_delta >= 0
    && Number.isInteger(value.case_projection_build_count_delta)
    && value.case_projection_build_count_delta >= 0
    && (value.response_bytes === null
      || (Number.isInteger(value.response_bytes) && value.response_bytes >= 0))
    && value.authority === "delivery_only");
}

async function contentDigest(
  value: Record<string, any>,
  idKey: string,
  hashKey: string,
  prefix: string,
): Promise<boolean> {
  const body = structuredClone(value);
  const identity = body[idKey];
  const digest = body[hashKey];
  delete body[idKey];
  delete body[hashKey];
  if (typeof identity !== "string" || typeof digest !== "string" || !hash.test(digest)) return false;
  return identity === `${prefix}${digest.slice(0, 24)}`
    && await canonicalJsonSha256(body, { pythonFloatKeys: engineeringCaseFloatKeys }) === digest;
}

export async function isEngineeringCaseRevision(
  value: unknown,
  expected: { runId: string; sessionId: string },
): Promise<boolean> {
  if (!record(value)
    || value.schema_version !== "p3544.engineering-case-revision.v1"
    || typeof value.case_id !== "string" || !caseId.test(value.case_id)
    || !Number.isInteger(value.case_revision) || value.case_revision < 1
    || !validHash(value.case_sha256)
    || !nullableHash(value.previous_case_sha256)
    || (value.case_revision === 1) !== (value.previous_case_sha256 === null)
    || value.previous_case_sha256 === value.case_sha256
    || typeof value.created_at !== "string"
    || !Number.isFinite(Date.parse(value.created_at))
    || !changeCategories.has(value.change_category)
    || !validHash(value.source_workspace_revision)
    || !validDeliveryDiagnostics(value.delivery_diagnostics)
    || !record(value.case)) return false;

  const engineeringCase = value.case;
  if (engineeringCase.schema_version !== "p3544.unified-engineering-case.v1"
    || engineeringCase.case_id !== value.case_id
    || engineeringCase.case_sha256 !== value.case_sha256
    || engineeringCase.run_id !== expected.runId
    || engineeringCase.session_id !== expected.sessionId
    || !validHash(engineeringCase.case_revision_sha256)
    || !uniqueStrings(engineeringCase.selected_run_ids, 1)
    || !engineeringCase.selected_run_ids.includes(expected.runId)
    || !validHash(engineeringCase.recording_sha256)
    || !validHash(engineeringCase.vehicle_runtime_identity_sha256)
    || !safeText(engineeringCase.car_identity)
    || !safeText(engineeringCase.car_version)
    || !safeText(engineeringCase.iracing_build_version)
    || !safeText(engineeringCase.track_configuration)
    || !safeText(engineeringCase.setup_id)
    || !validHash(engineeringCase.setup_snapshot_sha256)
    || engineeringCase.workspace_revision !== value.source_workspace_revision
    || !engineeringObjectives.has(engineeringCase.objective_id)
    || !validHash(engineeringCase.condition_epoch_sha256)
    || !validHash(engineeringCase.p19_reasoning_snapshot_sha256)
    || !validHash(engineeringCase.p20_state_revision)
    || !validHash(engineeringCase.p26_knowledge_graph_sha256)
    || !validHash(engineeringCase.p32_projection_sha256)
    || !validHash(engineeringCase.p35_assessment_sha256)
    || !validHash(engineeringCase.p351_projection_sha256)
    || !validHash(engineeringCase.p33_projection_sha256)
    || !validHash(engineeringCase.semantic_registry_sha256)
    || !validHash(engineeringCase.evidence_index_sha256)
    || !nullableHash(engineeringCase.crew_event_head_sha256)
    || !nullableText(engineeringCase.crew_current_subgoal)
    || !criticStates.has(engineeringCase.crew_critic_state)
    || !nullableText(engineeringCase.active_workflow_id)
    || !nullableHash(engineeringCase.active_workflow_revision)
    || !nullableText(engineeringCase.primary_opportunity_id)
    || !uniqueStrings(engineeringCase.mechanism_ids)
    || !uniqueStrings(engineeringCase.component_ids)
    || !nullableIdentifier(engineeringCase.active_discriminator_id)
    || !nullableText(engineeringCase.investigation_id)
    || !validHash(engineeringCase.workspace_revision)
    || !validHash(engineeringCase.terminal_move_sha256)
    || engineeringCase.setup_authorized !== false
    || engineeringCase.p19_authority_unchanged !== true
    || engineeringCase.authority !== "case_receipt_only"
    || !record(engineeringCase.mission)
    || engineeringCase.mission.terminal_move_sha256 !== engineeringCase.terminal_move_sha256
    || !Array.isArray(engineeringCase.response_artifacts)
    || !Array.isArray(engineeringCase.response_expectation_contracts)
    || !Array.isArray(engineeringCase.response_expectation_evaluations)
    || !Array.isArray(engineeringCase.p19_response_admissions)
    || !Array.isArray(engineeringCase.evidence_deficits)
    || !Array.isArray(engineeringCase.effect_readiness)
    || !Array.isArray(engineeringCase.capability_resolutions)
    || !Array.isArray(engineeringCase.quantity_observability)
    || !record(engineeringCase.semantic_focus)
    || !record(engineeringCase.campaign_capture)
    || (engineeringCase.active_workflow_id === null)
      !== (engineeringCase.active_workflow_revision === null)
  ) return false;

  const stableIdDigest = await canonicalJsonSha256({
    schema: "p3544.engineering-case-lifecycle.v1",
    run_id: expected.runId,
    session_id: expected.sessionId,
  });
  if (value.case_id !== `p3543case_${stableIdDigest.slice(0, 24)}`) return false;

  const caseBody = structuredClone(engineeringCase);
  delete caseBody.case_id;
  delete caseBody.case_sha256;
  if (await canonicalJsonSha256(caseBody, {
    pythonFloatKeys: engineeringCaseFloatKeys,
  }) !== value.case_sha256) return false;

  if (!engineeringCase.response_artifacts.every(record)) return false;
  const artifactIds = engineeringCase.response_artifacts.map((item: any) => item.artifact_id);
  if (artifactIds.some((item: unknown) => (
    typeof item !== "string" || !responseArtifactId.test(item)
  ))
    || new Set(artifactIds).size !== artifactIds.length) return false;
  for (const artifact of engineeringCase.response_artifacts) {
    const artifactBody = structuredClone(artifact);
    const artifactDigest = artifactBody.artifact_sha256;
    delete artifactBody.artifact_sha256;
    if (artifact.artifact_type !== "engineering_response"
      || !validHash(artifactDigest)
      || artifact.case_id !== value.case_id
      || artifact.case_revision_sha256 !== engineeringCase.case_revision_sha256
      || artifact.run_id !== expected.runId
      || artifact.session_id !== expected.sessionId
      || artifact.setup_id !== engineeringCase.setup_id
      || artifact.source_recording_sha256 !== engineeringCase.recording_sha256
      || !record(artifact.operational_evidence)
      || artifact.artifact_id !== artifact.operational_evidence.evidence_id
      || artifact.relation !== artifact.operational_evidence.relation
      || artifact.phase !== artifact.operational_evidence.phase
      || artifact.lap_pct_start !== artifact.operational_evidence.lap_pct_start
      || artifact.lap_pct_end !== artifact.operational_evidence.lap_pct_end
      || artifact.authority_ceiling !== "observation_only"
      || artifact.p19_support_authorized !== false
      || artifact.component_support_authorized !== false
      || artifact.setup_authorized !== false
      || await canonicalJsonSha256(artifactBody, {
        pythonFloatKeys: engineeringCaseFloatKeys,
      }) !== artifactDigest) return false;
  }

  const driverIntent = engineeringCase.driver_intent;
  if (driverIntent !== null && (!record(driverIntent)
    || driverIntent.schema_version !== "p3544.driver-intent.v1"
    || driverIntent.case_id !== value.case_id
    || driverIntent.objective !== engineeringCase.objective_id
    || !Number.isInteger(driverIntent.intent_revision)
    || driverIntent.intent_revision < 1
    || (driverIntent.intent_revision === 1) !== (driverIntent.supersedes_intent_id === null)
    || driverIntent.authority !== "driver_context_only"
    || driverIntent.physical_truth_modified !== false
    || driverIntent.setup_authorized !== false
    || !await contentDigest(driverIntent, "intent_id", "intent_sha256", "p3544intent_"))) {
    return false;
  }

  if (!engineeringCase.effect_readiness.every(record)) return false;
  const projectedEffectIds = engineeringCase.effect_readiness
    .map((item: any) => item.effect_id);
  const projectedMechanismIds = Array.isArray(engineeringCase.mechanism_ids)
    ? engineeringCase.mechanism_ids
    : [];
  const expectationIds = engineeringCase.response_expectation_contracts
    .map((item: any) => item.expectation_contract_id);
  if (expectationIds.some((item: unknown) => typeof item !== "string")
    || new Set(expectationIds).size !== expectationIds.length) return false;
  for (const contract of engineeringCase.response_expectation_contracts) {
    if (!record(contract)
      || !projectedEffectIds.includes(contract.owning_effect_id)
      || !Array.isArray(contract.owning_mechanism_ids)
      || !contract.owning_mechanism_ids.every((id: unknown) => (
        typeof id === "string" && projectedMechanismIds.includes(id)
      ))
      || contract.authority_ceiling !== "relationship_only"
      || contract.setup_authorized !== false
      || !await contentDigest(
        contract,
        "expectation_contract_id",
        "expectation_sha256",
        "p3544expect_",
      )) return false;
  }

  const evaluationIds = engineeringCase.response_expectation_evaluations
    .map((item: any) => item.evaluation_id);
  if (evaluationIds.some((item: unknown) => typeof item !== "string")
    || new Set(evaluationIds).size !== evaluationIds.length) return false;
  for (const evaluation of engineeringCase.response_expectation_evaluations) {
    if (!record(evaluation)
      || !expectationIds.includes(evaluation.expectation_contract_id)
      || !artifactIds.includes(evaluation.response_artifact_id)
      || evaluation.authority !== "p19_response_evaluation_only"
      || evaluation.rank_modified !== false
      || evaluation.setup_authorized !== false
      || !await contentDigest(
        evaluation,
        "evaluation_id",
        "evaluation_sha256",
        "p3544evaluation_",
      )) return false;
  }

  const admittedArtifactIds: string[] = [];
  for (const admission of engineeringCase.p19_response_admissions) {
    if (!record(admission)
      || admission.case_id !== value.case_id
      || admission.case_revision_sha256 !== engineeringCase.case_revision_sha256
      || !artifactIds.includes(admission.response_artifact_id)
      || admission.p19_reasoning_snapshot_sha256
        !== engineeringCase.p19_reasoning_snapshot_sha256
      || !Array.isArray(admission.assessments)
      || admission.assessments.some((assessment: any) => !record(assessment)
        || !Array.isArray(assessment.matched_mechanism_ids)
        || !assessment.matched_mechanism_ids.every((id: unknown) => (
          typeof id === "string" && projectedMechanismIds.includes(id)
        ))
        || !Array.isArray(assessment.expectation_contract_ids)
        || !assessment.expectation_contract_ids.every((id: unknown) => expectationIds.includes(id))
        || !Array.isArray(assessment.evaluation_ids)
        || !assessment.evaluation_ids.every((id: unknown) => evaluationIds.includes(id))
        || assessment.rank_modified !== false
        || assessment.setup_authorized !== false)
      || admission.reasoning_rank_modified !== false
      || admission.terminal_action_modified !== false
      || admission.setup_authorized !== false
      || !await contentDigest(admission, "admission_id", "admission_sha256", "p19response_")) return false;
    admittedArtifactIds.push(admission.response_artifact_id);
  }
  if (new Set(admittedArtifactIds).size !== admittedArtifactIds.length
    || admittedArtifactIds.length !== artifactIds.length
    || artifactIds.some((id: string) => !admittedArtifactIds.includes(id))) return false;

  const deficitById = new Map<string, Record<string, any>>();
  for (const deficit of engineeringCase.evidence_deficits) {
    if (!record(deficit)
      || !deficitCodes.has(deficit.code)
      || !uniqueStrings(deficit.affected_contract_ids)
      || !uniqueStrings(deficit.affected_effect_ids)
      || !uniqueStrings(deficit.affected_mechanism_ids)
      || !uniqueStrings(deficit.affected_tool_ids)
      || !uniqueStrings(deficit.required_channel_ids)
      || !uniqueStrings(deficit.current_channel_capability_ids)
      || !uniqueStrings(deficit.blocker_reasons, 1)
      || !recoveryStatuses.has(deficit.recovery_mode)
      || typeof deficit.mission_eligible !== "boolean"
      || deficit.authority !== "measurement_routing_only"
      || deficit.setup_authorized !== false
      || !await contentDigest(deficit, "deficit_id", "deficit_sha256", "p3544deficit_")) return false;
    if (deficitById.has(deficit.deficit_id)) return false;
    deficitById.set(deficit.deficit_id, deficit);
  }

  if (projectedEffectIds.some((item: unknown) => typeof item !== "string")
    || new Set(projectedEffectIds).size !== projectedEffectIds.length) return false;
  for (const readiness of engineeringCase.effect_readiness) {
    const exactP19 = readiness.state === "p19_testable";
    if (!safeIdentifier(readiness.effect_id)
      || typeof readiness.bridge_id !== "string" || !bridgeId.test(readiness.bridge_id)
      || !readinessStates.has(readiness.state)
      || !readinessAuthorities.has(readiness.authority)
      || !uniqueStrings(readiness.response_artifact_ids)
      || !readiness.response_artifact_ids.every((id: unknown) => artifactIds.includes(id))
      || !uniqueStrings(readiness.expected_response_relation_ids)
      || !uniqueStrings(readiness.exact_control_keys)
      || !nullableIdentifier(readiness.experiment_factor_id)
      || !uniqueStrings(readiness.countereffect_measurement_ids)
      || !uniqueStrings(readiness.missing_evidence)
      || !uniqueStrings(readiness.deficit_ids)
      || !readiness.deficit_ids.every((id: unknown) => deficitById.has(String(id)))
      || exactP19 !== (readiness.setup_authorized === true)
      || exactP19 !== (readiness.authority === "exact_p19_projection")
      || (exactP19 && (readiness.exact_control_keys.length === 0
        || readiness.experiment_factor_id === null))
      || (readiness.state === "response_evidence_ready"
        && readiness.response_artifact_ids.length === 0)
      || (readiness.state === "blocked" && readiness.missing_evidence.length === 0)) return false;
  }

  for (const resolution of engineeringCase.capability_resolutions) {
    const deficit = record(resolution)
      ? deficitById.get(String(resolution.deficit_id))
      : undefined;
    if (!record(resolution)
      || deficit === undefined
      || resolution.deficit_code !== deficit.code
      || !uniqueStrings(resolution.source_artifact_ids)
      || !resolution.source_artifact_ids.every((id: unknown) => artifactIds.includes(id))
      || resolution.status !== recoveryStatuses.get(resolution.recovery_mode)
      || resolution.authority !== "measurement_routing_only"
      || resolution.setup_authorized !== false) return false;
  }

  const quantityIds = engineeringCase.quantity_observability
    .map((item: any) => item.quantity_id);
  if (quantityIds.some((item: unknown) => typeof item !== "string")
    || new Set(quantityIds).size !== quantityIds.length) return false;
  for (const quantity of engineeringCase.quantity_observability) {
    if (!record(quantity)
      || !Array.isArray(quantity.response_artifact_ids)
      || !quantity.response_artifact_ids.every((id: unknown) => artifactIds.includes(id))
      || quantity.state !== "currently_observable"
      || quantity.authority !== "quantity_observation_only"
      || quantity.component_support_authorized !== false
      || quantity.setup_authorized !== false) return false;
  }

  const focus = engineeringCase.semantic_focus;
  if (focus.case_id !== value.case_id
    || focus.case_revision_sha256 !== engineeringCase.case_revision_sha256
    || (focus.artifact_id !== null && !artifactIds.includes(focus.artifact_id))
    || focus.authority !== "navigation_only") return false;

  const mission = engineeringCase.mission;
  if (!safeText(mission.what)
    || !safeText(mission.where)
    || !safeText(mission.why_it_matters)
    || !safeText(mission.uncertain)
    || !safeText(mission.next)
    || !safeText(mission.done_when)
    || !missionAuthorities.has(mission.source_authority)
    || !validHash(mission.terminal_move_sha256)
    || !uniqueStrings(mission.source_artifact_ids)
    || !mission.source_artifact_ids
      .filter((id: string) => id.startsWith("p3542.response:"))
      .every((id: string) => artifactIds.includes(id))
    || mission.setup_authorized !== (mission.source_authority === "p19_exact_mirror")) {
    return false;
  }

  const campaign = engineeringCase.campaign_capture;
  if (!campaignStates.has(campaign.state)
    || !uniqueStrings(campaign.blocker_reasons)
    || campaign.authority !== "qualification_only"
    || campaign.historical_count_credited !== false
    || campaign.null_count_credited !== false
    || campaign.negative_control_count_credited !== false
    || campaign.subgroup_count_credited !== false) return false;
  return true;
}
