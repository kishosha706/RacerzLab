import { describe, expect, it } from "vitest";
import { canonicalJsonSha256 } from "./canonicalJsonSha256";
import { isHandlingKnowledgeProjection } from "./handlingKnowledgeTrust";

const CASE_ID = "p3543case_" + "f".repeat(24);
const REVISION = "a".repeat(64);
const CASE_SHA = "b".repeat(64);
const ASSESSMENT_ID = "hba_" + "1".repeat(24);

const EXPECTATION = {
  runId: "run-1",
  sessionId: "session-1",
  setupId: "setup-1",
  caseId: CASE_ID,
  caseRevision: REVISION,
  caseSha256: CASE_SHA,
};

async function payload(overrides: Record<string, unknown> = {}) {
  const body = {
    schema_version: "p356.handling-knowledge.v1",
    run_id: "run-1",
    session_id: "session-1",
    setup_id: "setup-1",
    case_id: CASE_ID,
    case_revision_sha256: REVISION,
    case_sha256: CASE_SHA,
    assessment_id: ASSESSMENT_ID,
    phase: "center",
    classification: "kinematic_residual_observation",
    canonical_symptom_id: null,
    corroborated: false,
    observed_behavior: "Kinematic residual observation without steering-response corroboration.",
    evidence_qualification: "Single-strand kinematic diagnostic; no canonical symptom is attached.",
    mechanisms: [{
      mechanism_id: "mechanism:center_rotation_deficit",
      label: "Center rotation deficit",
      relevance: "blocked",
      missing_evidence: ["Required channel throttle_pct is not part of the handling observation source."],
      support_declared: false,
    }],
    relevant_knowledge: [],
    countereffects: [],
    evidence_status: ["Mechanical cause unresolved."],
    next_evidence_channels: ["steering_deg", "yaw_rate"],
    next_action: {
      kind: "measure",
      instruction: "Review matched steering and yaw traces across the qualified lap group.",
    },
    authority: "derived_observation_view",
    setup_authorized: false,
    p19_authority_unchanged: true,
    ...overrides,
  };
  return {
    ...body,
    projection_sha256: await canonicalJsonSha256(body),
  };
}

describe("Handling knowledge runtime trust", () => {
  it("accepts an exact residual-only projection", async () => {
    expect(await isHandlingKnowledgeProjection(await payload(), EXPECTATION)).toBe(true);
  });

  it("rejects a rehashed projection", async () => {
    const forged = await payload();
    forged.projection_sha256 = "f".repeat(64);
    expect(await isHandlingKnowledgeProjection(forged, EXPECTATION)).toBe(false);
  });

  it("rejects a foreign case identity", async () => {
    expect(await isHandlingKnowledgeProjection(
      await payload({ case_id: "p3543case_" + "e".repeat(24) }),
      EXPECTATION,
    )).toBe(false);
  });

  it("rejects a stale case revision", async () => {
    expect(await isHandlingKnowledgeProjection(
      await payload({ case_revision_sha256: "d".repeat(64) }),
      EXPECTATION,
    )).toBe(false);
  });

  it("rejects a symptom without corroboration", async () => {
    expect(await isHandlingKnowledgeProjection(
      await payload({ canonical_symptom_id: "tight_center", corroborated: false }),
      EXPECTATION,
    )).toBe(false);
  });

  it("rejects drifted observation-only authority", async () => {
    expect(await isHandlingKnowledgeProjection(
      await payload({ setup_authorized: true }),
      EXPECTATION,
    )).toBe(false);
  });

  it("rejects a hypothesis claiming setup authority without an exact P19 control", async () => {
    expect(await isHandlingKnowledgeProjection(
      await payload({
        relevant_knowledge: [{
          bridge_id: "p351b_" + "a".repeat(24),
          effect_id: "effect:test",
          setup_area: "arb",
          physical_role: "roll stiffness",
          level: "measurable_hypothesis",
          relevance: "supported_candidate",
          knowledge_applicability: "applicable",
          p35_mechanism_ids: ["mechanism:center_rotation_deficit"],
          countereffect_ids: [],
          missing_evidence: [],
          authority: "measurement_only",
          setup_authorized: true,
          p19_control: null,
        }],
      }),
      EXPECTATION,
    )).toBe(false);
  });

  it("accepts an exact mirrored P19 control with per-hypothesis authorization", async () => {
    expect(await isHandlingKnowledgeProjection(
      await payload({
        relevant_knowledge: [{
          bridge_id: "p351b_" + "a".repeat(24),
          effect_id: "effect:test",
          setup_area: "arb",
          physical_role: "roll stiffness",
          level: "p19_testable_control",
          relevance: "supported_candidate",
          knowledge_applicability: "applicable",
          p35_mechanism_ids: ["mechanism:center_rotation_deficit"],
          countereffect_ids: [],
          missing_evidence: [],
          authority: "exact_p19_projection",
          setup_authorized: true,
          p19_control: {
            effect_id: "effect:test",
            control_key: "arb_adjustment",
            direction_sign: -1,
            experiment_factor_id: "arb_adjustment",
            current_value: "4",
            proposed_value: "5",
            workflow_id: "cwf-exact",
            workflow_revision: "w".repeat(64),
            source_event_ids: ["cce_exact"],
            authority: "exact_p19_projection",
          },
        }],
        next_action: {
          kind: "p19_authorized_experiment",
          instruction: "P19 has authorized one exact controlled experiment.",
        },
      }),
      EXPECTATION,
    )).toBe(true);
  });

  it("rejects an authorized-experiment action without an authorized hypothesis", async () => {
    expect(await isHandlingKnowledgeProjection(
      await payload({
        next_action: {
          kind: "p19_authorized_experiment",
          instruction: "P19 has authorized one exact controlled experiment.",
        },
      }),
      EXPECTATION,
    )).toBe(false);
  });
});
