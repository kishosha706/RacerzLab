import type { EngineeringCaseRevision } from "../types/engineeringCase";
import { canonicalJsonSha256 } from "./canonicalJsonSha256";
import { engineeringCaseFloatKeys } from "./crewChiefResponseTrust";

const hash = /^[0-9a-f]{64}$/;
const caseId = /^p3543case_[0-9a-f]{24}$/;

function record(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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
    || typeof value.case_sha256 !== "string" || !hash.test(value.case_sha256)
    || (value.previous_case_sha256 !== null
      && (typeof value.previous_case_sha256 !== "string" || !hash.test(value.previous_case_sha256)))
    || typeof value.created_at !== "string"
    || typeof value.source_workspace_revision !== "string" || !hash.test(value.source_workspace_revision)
    || !record(value.case)) return false;

  const engineeringCase = value.case;
  if (engineeringCase.schema_version !== "p3544.unified-engineering-case.v1"
    || engineeringCase.case_id !== value.case_id
    || engineeringCase.case_sha256 !== value.case_sha256
    || engineeringCase.run_id !== expected.runId
    || engineeringCase.session_id !== expected.sessionId
    || engineeringCase.workspace_revision !== value.source_workspace_revision
    || engineeringCase.setup_authorized !== false
    || engineeringCase.p19_authority_unchanged !== true
    || engineeringCase.authority !== "case_receipt_only"
    || !record(engineeringCase.mission)
    || engineeringCase.mission.terminal_move_sha256 !== engineeringCase.terminal_move_sha256
    || !Array.isArray(engineeringCase.response_artifacts)
    || !Array.isArray(engineeringCase.p19_response_admissions)
    || !Array.isArray(engineeringCase.evidence_deficits)
    || !Array.isArray(engineeringCase.effect_readiness)) return false;

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

  const artifactIds = engineeringCase.response_artifacts.map((item: any) => item.artifact_id);
  if (new Set(artifactIds).size !== artifactIds.length) return false;
  for (const artifact of engineeringCase.response_artifacts) {
    const artifactBody = structuredClone(artifact);
    const artifactDigest = artifactBody.artifact_sha256;
    delete artifactBody.artifact_sha256;
    if (!record(artifact)
      || artifact.case_id !== value.case_id
      || artifact.case_revision_sha256 !== engineeringCase.case_revision_sha256
      || artifact.run_id !== expected.runId
      || artifact.session_id !== expected.sessionId
      || artifact.setup_id !== engineeringCase.setup_id
      || artifact.setup_authorized !== false
      || typeof artifactDigest !== "string"
      || await canonicalJsonSha256(artifactBody, {
        pythonFloatKeys: engineeringCaseFloatKeys,
      }) !== artifactDigest) return false;
  }

  for (const admission of engineeringCase.p19_response_admissions) {
    if (!record(admission)
      || admission.case_id !== value.case_id
      || !artifactIds.includes(admission.response_artifact_id)
      || admission.reasoning_rank_modified !== false
      || admission.terminal_action_modified !== false
      || admission.setup_authorized !== false
      || !await contentDigest(admission, "admission_id", "admission_sha256", "p19response_")) return false;
  }
  for (const deficit of engineeringCase.evidence_deficits) {
    if (!record(deficit)
      || deficit.setup_authorized !== false
      || !await contentDigest(deficit, "deficit_id", "deficit_sha256", "p3544deficit_")) return false;
  }
  return true;
}
