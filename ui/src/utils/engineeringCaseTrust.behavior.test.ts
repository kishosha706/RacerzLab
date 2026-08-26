import { describe, expect, it } from "vitest";

import type { EngineeringCaseRevision } from "../types/engineeringCase";
import { canonicalJsonSha256 } from "./canonicalJsonSha256";
import { engineeringCaseFloatKeys } from "./crewChiefResponseTrust";
import { isEngineeringCaseRevision } from "./engineeringCaseTrust";

const runId = "run-1";
const sessionId = "session-1";

async function validRevision(): Promise<EngineeringCaseRevision> {
  const lifecycle = await canonicalJsonSha256({
    schema: "p3544.engineering-case-lifecycle.v1",
    run_id: runId,
    session_id: sessionId,
  });
  const stableCaseId = `p3543case_${lifecycle.slice(0, 24)}`;
  const workspaceRevision = "c".repeat(64);
  const terminalMove = "d".repeat(64);
  const caseBody = {
    schema_version: "p3544.unified-engineering-case.v1",
    case_revision_sha256: workspaceRevision,
    run_id: runId,
    session_id: sessionId,
    selected_run_ids: [runId],
    recording_sha256: "1".repeat(64),
    vehicle_runtime_identity_sha256: "0".repeat(64),
    car_identity: "test-car",
    car_version: "test-version",
    iracing_build_version: "test-build",
    track_configuration: "test-track",
    setup_id: "setup-1",
    setup_snapshot_sha256: "2".repeat(64),
    objective_id: "race_long_run",
    condition_epoch_sha256: "3".repeat(64),
    p19_reasoning_snapshot_sha256: "4".repeat(64),
    p20_state_revision: "5".repeat(64),
    p26_knowledge_graph_sha256: "6".repeat(64),
    p32_projection_sha256: "7".repeat(64),
    p35_assessment_sha256: "8".repeat(64),
    p351_projection_sha256: "9".repeat(64),
    p33_projection_sha256: "a".repeat(64),
    semantic_registry_sha256: "b".repeat(64),
    evidence_index_sha256: "e".repeat(64),
    driver_intent: null,
    crew_event_head_sha256: null,
    crew_current_subgoal: null,
    crew_critic_state: "unavailable",
    active_workflow_id: null,
    active_workflow_revision: null,
    primary_opportunity_id: null,
    response_artifacts: [],
    response_expectation_contracts: [],
    response_expectation_evaluations: [],
    p19_response_admissions: [],
    mechanism_ids: [],
    component_ids: [],
    effect_readiness: [{
      effect_id: "effect:synthetic",
      bridge_id: `p351b_${"f".repeat(24)}`,
      state: "knowledge_only",
      response_artifact_ids: [],
      expected_response_relation_ids: [],
      exact_control_keys: [],
      experiment_factor_id: null,
      countereffect_measurement_ids: [],
      missing_evidence: [],
      deficit_ids: [],
      authority: "knowledge_only",
      setup_authorized: false,
    }],
    active_discriminator_id: null,
    investigation_id: null,
    workspace_revision: workspaceRevision,
    terminal_move_sha256: terminalMove,
    mission: {
      what: "Measure the current problem.",
      where: "Run scope",
      why_it_matters: "The cause remains unresolved.",
      uncertain: "No stronger causal claim is authorized.",
      next: "Collect exact evidence.",
      done_when: "The exact contract is satisfied.",
      source_authority: "p19_measurement_mirror",
      terminal_move_sha256: terminalMove,
      source_artifact_ids: [],
      setup_authorized: false,
    },
    evidence_deficits: [],
    capability_resolutions: [],
    quantity_observability: [],
    semantic_focus: {
      case_id: stableCaseId,
      case_revision_sha256: workspaceRevision,
      artifact_id: null,
      lap_numbers: [],
      lap_pct_start: null,
      lap_pct_end: null,
      phase: null,
      mechanism_ids: [],
      response_relation_id: null,
      component_ids: [],
      effect_ids: [],
      control_keys: [],
      p19_cause_ids: [],
      authority: "navigation_only",
    },
    campaign_capture: {
      state: "pending",
      blocker_reasons: ["Real campaign evidence is not qualified."],
      historical_count_credited: false,
      null_count_credited: false,
      negative_control_count_credited: false,
      subgroup_count_credited: false,
      authority: "qualification_only",
    },
    authority: "case_receipt_only",
    p19_authority_unchanged: true,
    setup_authorized: false,
  };
  const caseSha = await canonicalJsonSha256(caseBody, {
    pythonFloatKeys: engineeringCaseFloatKeys,
  });
  return {
    schema_version: "p3544.engineering-case-revision.v1",
    case_id: stableCaseId,
    case_revision: 1,
    case_sha256: caseSha,
    previous_case_sha256: null,
    created_at: "2026-08-26T12:00:00Z",
    change_category: "initial",
    source_workspace_revision: workspaceRevision,
    delivery_diagnostics: null,
    case: {
      ...caseBody,
      case_id: stableCaseId,
      case_sha256: caseSha,
    } as EngineeringCaseRevision["case"],
  };
}

async function rehashCase(revision: EngineeringCaseRevision): Promise<void> {
  const body = structuredClone(revision.case) as Record<string, unknown>;
  delete body.case_id;
  delete body.case_sha256;
  const digest = await canonicalJsonSha256(body, {
    pythonFloatKeys: engineeringCaseFloatKeys,
  });
  revision.case.case_sha256 = digest;
  revision.case_sha256 = digest;
}

async function expectCoordinatedMutationRejected(
  mutate: (revision: EngineeringCaseRevision) => void,
): Promise<void> {
  const revision = await validRevision();
  mutate(revision);
  await rehashCase(revision);
  expect(await isEngineeringCaseRevision(revision, { runId, sessionId })).toBe(false);
}

describe("Engineering Case runtime trust", () => {
  it("accepts a complete exact case revision", async () => {
    expect(await isEngineeringCaseRevision(await validRevision(), { runId, sessionId }))
      .toBe(true);
  });

  it("rejects a coordinated rehash with foreign semantic focus", async () => {
    const revision = await validRevision();
    revision.case.semantic_focus.case_id = `p3543case_${"0".repeat(24)}`;
    await rehashCase(revision);
    expect(await isEngineeringCaseRevision(revision, { runId, sessionId })).toBe(false);
  });

  it("rejects coordinated rehashes with malformed core authority identities", async () => {
    const hashFields = [
      "case_revision_sha256",
      "recording_sha256",
      "vehicle_runtime_identity_sha256",
      "setup_snapshot_sha256",
      "condition_epoch_sha256",
      "p19_reasoning_snapshot_sha256",
      "p20_state_revision",
      "p26_knowledge_graph_sha256",
      "p32_projection_sha256",
      "p35_assessment_sha256",
      "p351_projection_sha256",
      "p33_projection_sha256",
      "semantic_registry_sha256",
      "evidence_index_sha256",
      "workspace_revision",
      "terminal_move_sha256",
    ] as const;
    for (const field of hashFields) {
      await expectCoordinatedMutationRejected((revision) => {
        (revision.case as unknown as Record<string, unknown>)[field] = "attacker-controlled";
      });
    }
  });

  it("rejects coordinated rehashes that invent readiness semantics", async () => {
    await expectCoordinatedMutationRejected((revision) => {
      (revision.case.effect_readiness[0] as unknown as Record<string, unknown>).state = "ready";
    });
    await expectCoordinatedMutationRejected((revision) => {
      const readiness = revision.case.effect_readiness[0] as unknown as Record<string, unknown>;
      readiness.state = "response_evidence_ready";
      readiness.authority = "measurement_only";
      readiness.response_artifact_ids = [];
    });
    await expectCoordinatedMutationRejected((revision) => {
      const readiness = revision.case.effect_readiness[0] as unknown as Record<string, unknown>;
      readiness.state = "p19_testable";
      readiness.authority = "exact_p19_projection";
      readiness.setup_authorized = true;
      readiness.experiment_factor_id = null;
      readiness.exact_control_keys = [];
    });
  });

  it("rejects coordinated rehashes that invent or hollow out mission authority", async () => {
    await expectCoordinatedMutationRejected((revision) => {
      revision.case.mission.next = "   ";
    });
    await expectCoordinatedMutationRejected((revision) => {
      (revision.case.mission as unknown as Record<string, unknown>).source_authority = "setup_directive";
    });
    await expectCoordinatedMutationRejected((revision) => {
      revision.case.mission.source_authority = "p19_exact_mirror";
      revision.case.mission.setup_authorized = false;
    });
  });

  it("does not require an exact P19 mission to originate in the P35.1 effect map", async () => {
    const revision = await validRevision();
    revision.case.mission.source_authority = "p19_exact_mirror";
    revision.case.mission.setup_authorized = true;
    await rehashCase(revision);
    expect(await isEngineeringCaseRevision(revision, { runId, sessionId })).toBe(true);
  });

  it("rejects an impossible outer revision lineage", async () => {
    const revision = await validRevision();
    revision.case_revision = 2;
    expect(await isEngineeringCaseRevision(revision, { runId, sessionId })).toBe(false);
  });
});
