import type {
  CurrentEngineeringKnowledgeProjection,
  CurrentKnowledgeHypothesis,
} from "../types/engineeringKnowledge";
import type { CrewChiefWorkspace } from "../types/crewChief";
import type { VehicleSystemsProjection } from "../types/vehicleSystems";
import { canonicalJsonSha256 } from "./canonicalJsonSha256.ts";
import { ENGINEERING_KNOWLEDGE_STATIC_REGISTRY } from "./engineeringKnowledgeRegistry.ts";

const SHA = /^[0-9a-f]{64}$/;
const ID = /^[a-z0-9][a-z0-9_.:-]*$/;
const BRIDGE_ID = /^p351b_[0-9a-f]{24}$/;
const STATIC_BRIDGES = new Map(
  ENGINEERING_KNOWLEDGE_STATIC_REGISTRY.map((item) => [item.effectId, item]),
);
export const ENGINEERING_KNOWLEDGE_COVERAGE_SHA256 =
  "a7dd3bcb645b037d803289dd94ffa7a0c89c6d01e7ce7c52e635c8471826cc1c";
const PROJECTION_KEYS = new Set([
  "schema_version", "projection_sha256", "run_id", "session_id", "complaint_prior",
  "p19_reasoning_snapshot_sha256", "p20_state_revision", "p26_knowledge_graph_sha256",
  "p32_projection_sha256", "p35_assessment_sha256", "p33_projection_sha256",
  "bridge_coverage_sha256", "p32_opportunity_id", "hypotheses", "leading_hypothesis_ids",
  "next_discriminator_contract_id", "blocker_reasons", "terminal_authority",
  "non_p19_setup_authorized",
]);
const HYPOTHESIS_KEYS = new Set([
  "bridge_id", "effect_id", "setup_area", "physical_role", "direction_sign",
  "experiment_factor_id", "level", "relevance", "p32_opportunity_id",
  "p35_mechanism_ids", "p20_mechanism_ids", "possible_component_family_ids",
  "p26_component_family_ids", "current_candidate_component_ids",
  "current_supported_component_ids", "contradicted_component_ids",
  "blocked_component_ids", "unobservable_component_ids", "irrelevant_component_ids",
  "response_regimes", "relevant_phases", "expected_vehicle_response_ids",
  "expected_vehicle_state_ids", "validation_metric_ids", "countereffect_ids",
  "countereffect_state_ids", "protected_outcomes",
  "protected_performance_outcome_ids", "rollback_condition_ids", "inspection_tool_ids",
  "support_artifact_ids", "contradiction_artifact_ids", "discriminator_contract_ids",
  "missing_evidence", "controlled_history", "knowledge_applicability",
  "runtime_evidence_state", "p19_control", "authority", "setup_authorized",
]);
const HISTORY_KEYS = new Set([
  "experience_id", "workflow_id", "component_family_id", "control_key", "transfer_level",
  "mechanism_assessment", "control_response", "policy_verdict", "countereffects",
  "source_artifact_ids", "authority", "setup_authorized",
]);
const CONTROL_KEYS = new Set([
  "effect_id", "control_key", "direction_sign", "experiment_factor_id",
  "current_value", "proposed_value", "workflow_id", "workflow_revision",
  "source_event_ids", "authority",
]);

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function onlyKeys(value: Record<string, unknown>, keys: ReadonlySet<string>): boolean {
  return Object.keys(value).length === keys.size && Object.keys(value).every((key) => keys.has(key));
}

function text(value: unknown): value is string {
  return typeof value === "string" && value.trim() === value && value.length > 0;
}

function nullableText(value: unknown): value is string | null {
  return value === null || text(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text) && new Set(value).size === value.length;
}

function semanticIds(value: unknown, role: string, effectId: string): value is string[] {
  return strings(value) && value.length > 0
    && value.every((item) => item.startsWith(`p352.${role}:${effectId}:`));
}

function expectedLeadingHypotheses(
  hypotheses: CurrentKnowledgeHypothesis[],
  discriminatorId: string | null,
): string[] {
  const current = hypotheses.filter((item) => (
    item.relevance === "supported_candidate" || item.relevance === "blocked_candidate"
  ));
  const selected: CurrentKnowledgeHypothesis[] = [];
  const mechanisms = new Set<string>();
  const components = new Set<string>();
  const discriminatorOwner = discriminatorId == null ? undefined : current.find(
    (item) => item.discriminator_contract_ids.includes(discriminatorId),
  );
  if (discriminatorOwner != null) selected.push(discriminatorOwner);
  for (const item of selected) {
    item.p35_mechanism_ids.forEach((id) => mechanisms.add(id));
    item.p26_component_family_ids.forEach((id) => components.add(id));
  }
  for (const item of current) {
    if (selected.includes(item)) continue;
    const addsMechanism = item.p35_mechanism_ids.some((id) => !mechanisms.has(id));
    const addsComponent = item.p26_component_family_ids.some((id) => !components.has(id));
    if (!addsMechanism && !addsComponent) continue;
    selected.push(item);
    item.p35_mechanism_ids.forEach((id) => mechanisms.add(id));
    item.p26_component_family_ids.forEach((id) => components.add(id));
    if (selected.length === 8) return selected.map((item) => item.effect_id);
  }
  for (const item of current) {
    if (!selected.includes(item)) selected.push(item);
    if (selected.length === 8) break;
  }
  return selected.map((item) => item.effect_id);
}

function controlledHistoryShape(value: unknown): boolean {
  return record(value) && onlyKeys(value, HISTORY_KEYS)
    && typeof value.experience_id === "string" && /^p33x_[0-9a-f]{24}$/.test(value.experience_id)
    && text(value.workflow_id) && typeof value.component_family_id === "string" && ID.test(value.component_family_id)
    && typeof value.control_key === "string" && ID.test(value.control_key)
    && ["exact", "compatible"].includes(String(value.transfer_level))
    && ["supported", "weakened", "unchanged", "inconclusive", "invalid"].includes(String(value.mechanism_assessment))
    && ["matched", "missed", "inconclusive", "unavailable", "invalid"].includes(String(value.control_response))
    && ["keep", "undo", "retest", "invalid"].includes(String(value.policy_verdict))
    && strings(value.countereffects) && strings(value.source_artifact_ids)
    && value.authority === "controlled_history_only" && value.setup_authorized === false;
}

function controlledHistory(value: unknown, workspace: CrewChiefWorkspace): boolean {
  if (!controlledHistoryShape(value) || !record(value)) return false;
  return workspace.learning_prior.car_response_history.some((fingerprint) => {
    if (!(["exact", "compatible"] as string[]).includes(fingerprint.transfer_level)
      || fingerprint.transfer_level !== value.transfer_level
      || fingerprint.response.component !== value.component_family_id
      || fingerprint.response.control !== value.control_key
      || fingerprint.response.p19_mechanism_assessment !== value.mechanism_assessment
      || fingerprint.response.control_response_assessment !== value.control_response
      || fingerprint.response.policy_verdict !== value.policy_verdict
      || JSON.stringify(fingerprint.response.countereffects) !== JSON.stringify(value.countereffects)
      || JSON.stringify(fingerprint.response.source_artifact_ids)
        !== JSON.stringify(value.source_artifact_ids)) return false;
    const index = fingerprint.source_experience_ids.indexOf(String(value.experience_id));
    return index >= 0 && value.workflow_id === fingerprint.source_workflow_ids[
      Math.min(index, fingerprint.source_workflow_ids.length - 1)
    ];
  });
}

function exactP19Control(value: unknown, workspace: CrewChiefWorkspace): boolean {
  const decision = workspace.terminal_decision;
  return record(value) && onlyKeys(value, CONTROL_KEYS)
    && value.authority === "exact_p19_projection"
    && value.effect_id === decision.setup_effect_id
    && value.control_key === decision.control_key
    && value.direction_sign === decision.direction_sign
    && value.experiment_factor_id === decision.experiment_factor_id
    && value.current_value === decision.current_value
    && value.proposed_value === decision.proposed_value
    && value.workflow_id === decision.workflow_id
    && value.workflow_revision === decision.workflow_revision
    && strings(value.source_event_ids)
    && JSON.stringify(value.source_event_ids) === JSON.stringify(decision.source_event_ids);
}

function hypothesis(
  value: unknown,
  workspace: CrewChiefWorkspace,
  p26: VehicleSystemsProjection | null,
): value is CurrentKnowledgeHypothesis {
  if (!record(value) || !onlyKeys(value, HYPOTHESIS_KEYS)) return false;
  if (
    typeof value.bridge_id !== "string" || !BRIDGE_ID.test(value.bridge_id)
    || typeof value.effect_id !== "string" || !ID.test(value.effect_id)
    || typeof value.setup_area !== "string" || !ID.test(value.setup_area)
    || !text(value.physical_role)
    || ![-1, 0, 1].includes(Number(value.direction_sign))
    || !(value.experiment_factor_id === null
      || typeof value.experiment_factor_id === "string" && ID.test(value.experiment_factor_id))
    || !["educational_knowledge", "measurable_hypothesis", "p19_testable_control", "unsupported_remove"].includes(String(value.level))
    || !["supported_candidate", "blocked_candidate", "knowledge_only", "inapplicable"].includes(String(value.relevance))
    || !nullableText(value.p32_opportunity_id)
    || !strings(value.p35_mechanism_ids) || !strings(value.p20_mechanism_ids)
    || !strings(value.possible_component_family_ids)
    || !strings(value.p26_component_family_ids)
    || !strings(value.current_candidate_component_ids)
    || !strings(value.current_supported_component_ids)
    || !strings(value.contradicted_component_ids)
    || !strings(value.blocked_component_ids)
    || !strings(value.unobservable_component_ids)
    || !strings(value.irrelevant_component_ids)
    || !strings(value.support_artifact_ids)
    || !Array.isArray(value.response_regimes)
    || !value.response_regimes.every((item) => ["transient", "steady_state", "both"].includes(String(item)))
    || !strings(value.relevant_phases) || !strings(value.expected_vehicle_response_ids)
    || !semanticIds(value.expected_vehicle_state_ids, "expected_vehicle_state", value.effect_id)
    || !semanticIds(value.validation_metric_ids, "validation_metric", value.effect_id)
    || !strings(value.countereffect_ids)
    || !semanticIds(value.countereffect_state_ids, "countereffect_state", value.effect_id)
    || !strings(value.protected_outcomes)
    || !semanticIds(value.protected_performance_outcome_ids, "protected_outcome", value.effect_id)
    || !strings(value.rollback_condition_ids)
    || value.rollback_condition_ids.length !== 1
    || value.rollback_condition_ids[0] !== `p352.rollback:${value.effect_id}`
    || !strings(value.inspection_tool_ids)
    || !strings(value.contradiction_artifact_ids) || !strings(value.discriminator_contract_ids)
    || !strings(value.missing_evidence)
    || !Array.isArray(value.controlled_history)
    || !value.controlled_history.every((item) => controlledHistory(item, workspace))
    || !["applicable", "educational_only", "blocked_by_build", "unsupported"]
      .includes(String(value.knowledge_applicability))
    || !["unavailable", "measured", "calculated", "estimated_proxy",
      "observed_correlation", "controlled_test_effect", "blocked_by_context"]
      .includes(String(value.runtime_evidence_state))
    || typeof value.setup_authorized !== "boolean"
  ) return false;
  const staticBridge = STATIC_BRIDGES.get(value.effect_id as string);
  const currentMechanismIds = new Set(
    workspace.vehicle_dynamics.candidates.map((item) => item.mechanism_id),
  );
  const readyP20MechanismIds = new Set<string>(
    (workspace.engineering_awareness?.subsystem_states ?? [])
      .filter((item) => item.status === "ready")
      .map((item) => item.mechanism),
  );
  if (
    staticBridge == null
    || value.bridge_id !== staticBridge.bridgeId
    || value.direction_sign !== staticBridge.directionSign
    || value.experiment_factor_id !== staticBridge.experimentFactorId
    || JSON.stringify(value.p35_mechanism_ids) !== JSON.stringify(
      staticBridge.p35MechanismIds.filter((item) => currentMechanismIds.has(item)),
    )
    || JSON.stringify(value.p20_mechanism_ids) !== JSON.stringify(
      staticBridge.p20MechanismIds.filter((item) => readyP20MechanismIds.has(item)),
    )
    || JSON.stringify(value.possible_component_family_ids)
      !== JSON.stringify(staticBridge.possibleComponentFamilyIds)
  ) return false;
  const mechanismIds = value.p35_mechanism_ids as string[];
  const dynamicsCandidates = mechanismIds.flatMap((mechanismId) => {
    const candidate = workspace.vehicle_dynamics.candidates.find(
      (item) => item.mechanism_id === mechanismId,
    );
    return candidate == null ? [] : [candidate];
  });
  const expectedSupport = dynamicsCandidates.flatMap((candidate) => candidate.support_artifact_ids);
  const expectedContradiction = dynamicsCandidates.flatMap((candidate) => candidate.contradiction_artifact_ids);
  const expectedDiscriminators = [...new Set(dynamicsCandidates.flatMap((candidate) => candidate.discriminator_contract_ids))];
  const current = value.relevance === "supported_candidate" || value.relevance === "blocked_candidate";
  const expectedApplicability = value.level === "unsupported_remove"
    ? "unsupported"
    : workspace.vehicle_dynamics.applicability_state !== "ready"
      ? "blocked_by_build"
      : current ? "applicable" : "educational_only";
  const evidencePriority = [
    "controlled_test_effect", "observed_correlation", "measured", "calculated",
    "estimated_proxy",
  ];
  const focusState = new Map(
    workspace.vehicle_dynamics.focus_artifacts.map((item) => [item.artifact_id, item.evidence_state]),
  );
  const positiveStates = (value.support_artifact_ids as string[])
    .map((id) => focusState.get(id))
    .flatMap((state) => (
      state != null && evidencePriority.includes(state) ? [String(state)] : []
    ));
  const expectedRuntimeState = dynamicsCandidates.some((item) => item.relevance === "blocked")
    ? "blocked_by_context"
    : positiveStates.length > 0
      ? [...positiveStates].sort(
        (left, right) => evidencePriority.indexOf(left) - evidencePriority.indexOf(right),
      )[0]
      : "unavailable";
  const possibleComponents = value.possible_component_family_ids as string[];
  const componentStates = new Map(
    (p26?.component_states ?? []).map((item) => [item.component_id, item]),
  );
  const expectedPartitions: Record<string, string[]> = {
    candidate: [], supported: [], contradicted: [], blocked: [], unobservable: [], irrelevant: [],
  };
  for (const componentId of possibleComponents) {
    const state = componentStates.get(componentId);
    if (state == null) continue;
    if (state.observability_states.includes("unavailable")
      || state.current_response_state === "unavailable") {
      expectedPartitions.unobservable.push(componentId);
    } else if (state.relevance === "supported" || state.relevance === "tested") {
      expectedPartitions.supported.push(componentId);
    } else if (Object.prototype.hasOwnProperty.call(expectedPartitions, state.relevance)) {
      expectedPartitions[state.relevance].push(componentId);
    }
  }
  const expectedCurrent = [
    ...expectedPartitions.candidate,
    ...expectedPartitions.supported,
  ];
  if (
    (current && value.p32_opportunity_id !== workspace.engineering_knowledge.p32_opportunity_id)
    || (!current && value.p32_opportunity_id !== null)
    || JSON.stringify(value.support_artifact_ids) !== JSON.stringify(expectedSupport)
    || JSON.stringify(value.contradiction_artifact_ids) !== JSON.stringify(expectedContradiction)
    || JSON.stringify(value.discriminator_contract_ids) !== JSON.stringify(expectedDiscriminators)
    || (p26 !== null
      && !possibleComponents.every((item) => workspace.p26_component_ids.includes(item)))
    || JSON.stringify(value.current_candidate_component_ids) !== JSON.stringify(expectedPartitions.candidate)
    || JSON.stringify(value.current_supported_component_ids) !== JSON.stringify(expectedPartitions.supported)
    || JSON.stringify(value.contradicted_component_ids) !== JSON.stringify(expectedPartitions.contradicted)
    || JSON.stringify(value.blocked_component_ids) !== JSON.stringify(expectedPartitions.blocked)
    || JSON.stringify(value.unobservable_component_ids) !== JSON.stringify(expectedPartitions.unobservable)
    || JSON.stringify(value.irrelevant_component_ids) !== JSON.stringify(expectedPartitions.irrelevant)
    || JSON.stringify(value.p26_component_family_ids) !== JSON.stringify(expectedCurrent)
    || value.knowledge_applicability !== expectedApplicability
    || value.runtime_evidence_state !== expectedRuntimeState
  ) return false;
  if (value.level === "p19_testable_control") {
    return value.relevance !== "inapplicable" && value.setup_authorized === true
      && value.authority === "exact_p19_projection"
      && exactP19Control(value.p19_control, workspace)
      && workspace.terminal_decision.kind === "controlled_test";
  }
  if (value.p19_control !== null || value.setup_authorized || value.authority === "exact_p19_projection") return false;
  if (value.level === "measurable_hypothesis") {
    return value.authority === "measurement_only" && current;
  }
  return value.authority === "knowledge_only"
    && ((value.level === "unsupported_remove") === (value.relevance === "inapplicable"));
}

export function isCurrentEngineeringKnowledgeProjection(
  value: unknown,
  workspace: CrewChiefWorkspace,
  p26: VehicleSystemsProjection | null,
): value is CurrentEngineeringKnowledgeProjection {
  if (!record(value) || !onlyKeys(value, PROJECTION_KEYS)) return false;
  const expectedOpportunity = workspace.vehicle_dynamics.performance_opportunity_ids[0] ?? null;
  if (
    value.schema_version !== "p352.current-engineering-knowledge.v1"
    || typeof value.projection_sha256 !== "string" || !SHA.test(value.projection_sha256)
    || value.run_id !== workspace.identity.run_id || value.session_id !== workspace.identity.session_id
    || !nullableText(value.complaint_prior)
    || value.p19_reasoning_snapshot_sha256 !== workspace.identity.reasoning_snapshot_sha256
    || value.p20_state_revision !== workspace.identity.p20_state_revision
    || value.p26_knowledge_graph_sha256 !== workspace.identity.p26_knowledge_graph_sha256
    || value.p32_projection_sha256 !== workspace.identity.p32_projection_sha256
    || value.p35_assessment_sha256 !== workspace.identity.p35_assessment_sha256
    || value.p33_projection_sha256 !== workspace.identity.learning_projection_sha256
    || value.bridge_coverage_sha256 !== ENGINEERING_KNOWLEDGE_COVERAGE_SHA256
    || value.p32_opportunity_id !== expectedOpportunity
    || !Array.isArray(value.hypotheses) || value.hypotheses.length !== 92
    || !strings(value.leading_hypothesis_ids) || !nullableText(value.next_discriminator_contract_id)
    || value.next_discriminator_contract_id !== workspace.vehicle_dynamics.next_discriminator_contract_id
    || !strings(value.blocker_reasons) || value.terminal_authority !== "p19_only"
    || value.non_p19_setup_authorized !== false
  ) return false;
  if (!value.hypotheses.every((item) => hypothesis(item, workspace, p26))) return false;
  const effectIds = value.hypotheses.map((item) => item.effect_id);
  const expectedEffectIds = ENGINEERING_KNOWLEDGE_STATIC_REGISTRY.map((item) => item.effectId);
  if (effectIds.length !== expectedEffectIds.length
    || expectedEffectIds.some((effectId) => !effectIds.includes(effectId))) return false;
  if (new Set(effectIds).size !== effectIds.length) return false;
  const bridgeIds = value.hypotheses.map((item) => item.bridge_id);
  if (new Set(bridgeIds).size !== bridgeIds.length) return false;
  const projectedMechanisms = new Set(value.hypotheses
    .filter((item) => item.relevance === "supported_candidate"
      || item.relevance === "blocked_candidate")
    .flatMap((item) => item.p35_mechanism_ids));
  const candidateMechanisms = new Set(
    workspace.vehicle_dynamics.candidates.map((item) => item.mechanism_id),
  );
  if (projectedMechanisms.size !== candidateMechanisms.size
    || [...candidateMechanisms].some((item) => !projectedMechanisms.has(item))) return false;
  const expectedLeading = expectedLeadingHypotheses(
    value.hypotheses,
    value.next_discriminator_contract_id,
  );
  if (JSON.stringify(value.leading_hypothesis_ids) !== JSON.stringify(expectedLeading)) return false;
  return value.hypotheses.filter((item) => item.level === "p19_testable_control").length <= 1;
}

export async function hasCanonicalEngineeringKnowledgeDigest(
  value: CurrentEngineeringKnowledgeProjection,
): Promise<boolean> {
  const { projection_sha256: expected, ...body } = value;
  return await canonicalJsonSha256(body) === expected;
}

export function isStandaloneEngineeringKnowledgeProjection(
  value: unknown,
  runId: string,
  sessionId: string,
  p19TerminalDecision?: unknown,
): value is CurrentEngineeringKnowledgeProjection {
  if (!record(value) || !onlyKeys(value, PROJECTION_KEYS)) return false;
  if (
    value.schema_version !== "p352.current-engineering-knowledge.v1"
    || typeof value.projection_sha256 !== "string" || !SHA.test(value.projection_sha256)
    || value.run_id !== runId || value.session_id !== sessionId
    || !nullableText(value.complaint_prior)
    || typeof value.p19_reasoning_snapshot_sha256 !== "string" || !SHA.test(value.p19_reasoning_snapshot_sha256)
    || typeof value.p20_state_revision !== "string" || !SHA.test(value.p20_state_revision)
    || typeof value.p26_knowledge_graph_sha256 !== "string" || !SHA.test(value.p26_knowledge_graph_sha256)
    || typeof value.p32_projection_sha256 !== "string" || !SHA.test(value.p32_projection_sha256)
    || typeof value.p35_assessment_sha256 !== "string" || !SHA.test(value.p35_assessment_sha256)
    || typeof value.p33_projection_sha256 !== "string" || !SHA.test(value.p33_projection_sha256)
    || value.bridge_coverage_sha256 !== ENGINEERING_KNOWLEDGE_COVERAGE_SHA256
    || !nullableText(value.p32_opportunity_id)
    || !Array.isArray(value.hypotheses) || value.hypotheses.length !== 92
    || !strings(value.leading_hypothesis_ids)
    || !nullableText(value.next_discriminator_contract_id)
    || !strings(value.blocker_reasons)
    || value.terminal_authority !== "p19_only"
    || value.non_p19_setup_authorized !== false
  ) return false;
  const hypotheses = value.hypotheses as unknown[];
  if (!hypotheses.every((item) => {
    if (!record(item) || !onlyKeys(item, HYPOTHESIS_KEYS)
      || typeof item.bridge_id !== "string" || !BRIDGE_ID.test(item.bridge_id)
      || typeof item.effect_id !== "string" || !ID.test(item.effect_id)
      || typeof item.setup_area !== "string" || !ID.test(item.setup_area)
      || !text(item.physical_role)
      || ![-1, 0, 1].includes(Number(item.direction_sign))
      || !(item.experiment_factor_id === null || text(item.experiment_factor_id))
      || !["educational_knowledge", "measurable_hypothesis", "p19_testable_control", "unsupported_remove"].includes(String(item.level))
      || !["supported_candidate", "blocked_candidate", "knowledge_only", "inapplicable"].includes(String(item.relevance))
      || !nullableText(item.p32_opportunity_id)
      || !strings(item.p35_mechanism_ids) || !strings(item.p20_mechanism_ids)
      || !strings(item.possible_component_family_ids)
      || !strings(item.p26_component_family_ids)
      || !strings(item.current_candidate_component_ids)
      || !strings(item.current_supported_component_ids)
      || !strings(item.contradicted_component_ids)
      || !strings(item.blocked_component_ids)
      || !strings(item.unobservable_component_ids)
      || !strings(item.irrelevant_component_ids)
      || !strings(item.response_regimes)
      || !strings(item.relevant_phases) || !strings(item.expected_vehicle_response_ids)
      || !semanticIds(item.expected_vehicle_state_ids, "expected_vehicle_state", item.effect_id)
      || !semanticIds(item.validation_metric_ids, "validation_metric", item.effect_id)
      || !strings(item.countereffect_ids)
      || !semanticIds(item.countereffect_state_ids, "countereffect_state", item.effect_id)
      || !strings(item.protected_outcomes)
      || !semanticIds(item.protected_performance_outcome_ids, "protected_outcome", item.effect_id)
      || !strings(item.rollback_condition_ids)
      || item.rollback_condition_ids.length !== 1
      || item.rollback_condition_ids[0] !== `p352.rollback:${item.effect_id}`
      || !strings(item.inspection_tool_ids) || !strings(item.support_artifact_ids)
      || !strings(item.contradiction_artifact_ids) || !strings(item.discriminator_contract_ids)
      || !strings(item.missing_evidence) || !Array.isArray(item.controlled_history)
      || !item.controlled_history.every(controlledHistoryShape)
      || !["applicable", "educational_only", "blocked_by_build", "unsupported"]
        .includes(String(item.knowledge_applicability))
      || !["unavailable", "measured", "calculated", "estimated_proxy",
        "observed_correlation", "controlled_test_effect", "blocked_by_context"]
        .includes(String(item.runtime_evidence_state))
      || typeof item.setup_authorized !== "boolean") return false;
    const staticBridge = STATIC_BRIDGES.get(item.effect_id as string);
    if (staticBridge == null
      || item.bridge_id !== staticBridge.bridgeId
      || item.direction_sign !== staticBridge.directionSign
      || item.experiment_factor_id !== staticBridge.experimentFactorId
      || !(item.p35_mechanism_ids as string[]).every(
        (value) => staticBridge.p35MechanismIds.includes(value),
      )
      || !(item.p20_mechanism_ids as string[]).every(
        (value) => staticBridge.p20MechanismIds.includes(value),
      )
      || JSON.stringify(item.possible_component_family_ids)
        !== JSON.stringify(staticBridge.possibleComponentFamilyIds)) return false;
    if (item.level === "p19_testable_control") {
      return item.authority === "exact_p19_projection" && item.setup_authorized === true
        && record(item.p19_control) && onlyKeys(item.p19_control, CONTROL_KEYS)
        && record(p19TerminalDecision)
        && item.p19_control.authority === "exact_p19_projection"
        && item.p19_control.effect_id === p19TerminalDecision.setup_effect_id
        && item.p19_control.direction_sign === p19TerminalDecision.direction_sign
        && item.p19_control.experiment_factor_id
          === p19TerminalDecision.experiment_factor_id
        && strings(item.p19_control.source_event_ids)
        && p19TerminalDecision.kind === "controlled_test"
        && item.p19_control.control_key === p19TerminalDecision.control_key
        && item.p19_control.current_value === p19TerminalDecision.current_value
        && item.p19_control.proposed_value === p19TerminalDecision.proposed_value
        && item.p19_control.workflow_id === p19TerminalDecision.workflow_id
        && item.p19_control.workflow_revision === p19TerminalDecision.workflow_revision
        && JSON.stringify(item.p19_control.source_event_ids)
          === JSON.stringify(p19TerminalDecision.source_event_ids);
    }
    if (item.p19_control !== null || item.setup_authorized || item.authority === "exact_p19_projection") return false;
    return item.level === "measurable_hypothesis"
      ? item.authority === "measurement_only"
      : item.authority === "knowledge_only";
  })) return false;
  const effectIds = hypotheses.map((item) => (item as Record<string, unknown>).effect_id);
  const bridgeIds = hypotheses.map((item) => (item as Record<string, unknown>).bridge_id);
  const leading = value.leading_hypothesis_ids as string[];
  const expectedEffectIds = ENGINEERING_KNOWLEDGE_STATIC_REGISTRY.map((item) => item.effectId);
  return effectIds.length === expectedEffectIds.length
    && expectedEffectIds.every((effectId) => effectIds.includes(effectId))
    && new Set(effectIds).size === 92 && new Set(bridgeIds).size === 92
    && leading.every((item) => effectIds.includes(item))
    && hypotheses.filter((item) => record(item) && item.level === "p19_testable_control").length <= 1;
}
