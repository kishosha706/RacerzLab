import type { ControlledWorkflow } from "../types/telemetry";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

const hash = /^[0-9a-f]{64}$/;
const experienceId = /^p33x_[0-9a-f]{24}$/;
const statuses = new Set([
  "planned", "a_recorded", "b_recorded", "a2_recorded", "scored", "cancelled",
]);
const workflowKeys = [
  "workflow_id", "created_at", "updated_at", "status", "source_run_id", "complaint",
  "packet", "p32_opportunity_id", "p32_projection_sha256",
  "engineering_knowledge_projection_sha256", "stage_run_ids", "stage_eligible_lap_numbers", "stage_experiment_contexts",
  "analysis_version", "execution", "reproduction_snapshot", "quality", "learning_admitted",
  "controlled_response_receipt",
  "learning_capture_state", "learning_capture_experience_id",
  "learning_capture_experience_sha256", "learning_capture_blocker_reason",
] as const;

const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const exactKeys = (value: Record<string, unknown>, keys: readonly string[]): boolean =>
  Object.keys(value).length === keys.length
  && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
const nonempty = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;
const nullableRecord = (value: unknown): boolean => value === null || record(value);
const uniqueStrings = (value: unknown): value is string[] => Array.isArray(value)
  && value.every(nonempty)
  && new Set(value).size === value.length;
const safeTexts = (value: unknown): value is string[] => uniqueStrings(value)
  && value.every((item) => !hasSetupAuthorityDirective(item));
const stageMap = (value: unknown): boolean => record(value)
  && Object.entries(value).every(([stage, runId]) => (
    ["A", "B", "A2"].includes(stage) && nonempty(runId)
  ));
const stageLapMap = (value: unknown): boolean => record(value)
  && Object.entries(value).every(([stage, laps]) => (
    ["A", "B", "A2"].includes(stage)
    && Array.isArray(laps)
    && laps.every((lap) => Number.isInteger(lap) && lap >= 0)
    && new Set(laps).size === laps.length
  ));
const stageContextMap = (value: unknown): boolean => record(value)
  && Object.entries(value).every(([stage, context]) => (
    ["A", "B", "A2"].includes(stage) && record(context)
  ));

const controlledResponseReceipt = (value: unknown, workflowId: string): boolean => {
  if (value === null) return true;
  if (!record(value)
    || !/^p3543receipt_[0-9a-f]{24}$/.test(String(value.receipt_id))
    || typeof value.receipt_sha256 !== "string" || !hash.test(value.receipt_sha256)
    || value.workflow_id !== workflowId
    || !nonempty(value.control_key)
    || !nonempty(value.setup_effect_id)
    || !nonempty(value.experiment_factor_id)
    || ![-1, 1].includes(Number(value.direction_sign))
    || !Array.isArray(value.stages)
    || value.stages.length !== 3
    || !Array.isArray(value.expected_response_relation_ids)
    || value.expected_response_relation_ids.length === 0
    || !Array.isArray(value.observed_metric_deltas)
    || !["ready", "blocked"].includes(String(value.state))
    || !safeTexts(value.blocker_reasons)
    || value.authority !== "p19_controlled_response_receipt"
    || value.setup_authorized !== false) return false;
  const stages = value.stages as Array<Record<string, unknown>>;
  const runIds = stages.map((item) => String(item.run_id));
  const recordings = stages.map((item) => String(item.source_recording_sha256));
  return stages.every((item, index) => (
    record(item)
    && item.stage === ["A", "B", "A2"][index]
    && nonempty(item.run_id)
    && typeof item.source_recording_sha256 === "string"
    && hash.test(item.source_recording_sha256)
    && typeof item.setup_snapshot_sha256 === "string"
    && hash.test(item.setup_snapshot_sha256)
    && uniqueStrings(item.response_artifact_ids)
    && uniqueStrings(item.source_channels)
    && Array.isArray(item.eligible_lap_numbers)
    && item.eligible_lap_numbers.length >= 3
  )) && new Set(runIds).size === 3
    && new Set(recordings).size === 3
    && (value.state === "ready"
      ? value.observed_metric_deltas.length > 0 && value.blocker_reasons.length === 0
      : value.observed_metric_deltas.length === 0 && value.blocker_reasons.length > 0);
};

export function hasValidLearningCaptureMetadata(value: unknown): boolean {
  if (!record(value)
    || !Object.prototype.hasOwnProperty.call(value, "learning_capture_state")
    || !Object.prototype.hasOwnProperty.call(value, "learning_capture_experience_id")
    || !Object.prototype.hasOwnProperty.call(value, "learning_capture_experience_sha256")
    || !Object.prototype.hasOwnProperty.call(value, "learning_capture_blocker_reason")) return false;
  const state = value.learning_capture_state;
  const id = value.learning_capture_experience_id;
  const digest = value.learning_capture_experience_sha256;
  const blocker = value.learning_capture_blocker_reason;
  if (!["not_applicable", "captured", "blocked"].includes(String(state))) return false;
  if (state === "not_applicable") {
    return id === null && digest === null && blocker === null;
  }
  if (typeof id !== "string" || !experienceId.test(id)
    || typeof digest !== "string" || !hash.test(digest)
    || id !== `p33x_${digest.slice(0, 24)}`) return false;
  if (state === "captured") return blocker === null;
  return typeof blocker === "string"
    && blocker.length > 0
    && blocker.length <= 240
    && !hasSetupAuthorityDirective(blocker);
}

export function isControlledWorkflowResponse(value: unknown): value is ControlledWorkflow {
  if (!record(value) || !exactKeys(value, workflowKeys)
    || !nonempty(value.workflow_id)
    || !nonempty(value.created_at) || !Number.isFinite(Date.parse(value.created_at))
    || !nonempty(value.updated_at) || !Number.isFinite(Date.parse(value.updated_at))
    || !statuses.has(String(value.status))
    || !nonempty(value.source_run_id)
    || !nonempty(value.complaint)
    || !record(value.packet)
    || !(
      value.p32_opportunity_id === null
      || nonempty(value.p32_opportunity_id)
    )
    || !(
      value.p32_projection_sha256 === null
      || typeof value.p32_projection_sha256 === "string" && hash.test(value.p32_projection_sha256)
    )
    || !(
      value.engineering_knowledge_projection_sha256 === null
      || typeof value.engineering_knowledge_projection_sha256 === "string"
        && hash.test(value.engineering_knowledge_projection_sha256)
    )
    || !stageMap(value.stage_run_ids)
    || !stageLapMap(value.stage_eligible_lap_numbers)
    || !stageContextMap(value.stage_experiment_contexts)
    || !nonempty(value.analysis_version)
    || !nullableRecord(value.execution)
    || !record(value.reproduction_snapshot)
    || !nullableRecord(value.quality)
    || !controlledResponseReceipt(value.controlled_response_receipt, String(value.workflow_id))
    || !(value.learning_admitted === null || typeof value.learning_admitted === "boolean")
    || !hasValidLearningCaptureMetadata(value)) return false;
  const performanceIdentity = [
    value.p32_opportunity_id,
    value.p32_projection_sha256,
    value.engineering_knowledge_projection_sha256,
  ];
  if (performanceIdentity.some((item) => item === null)
    !== performanceIdentity.every((item) => item === null)) return false;
  return value.status === "scored" || value.learning_capture_state === "not_applicable";
}
