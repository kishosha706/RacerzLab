import type { ControlledWorkflow } from "../types/telemetry";
import { hasSetupAuthorityDirective } from "./setupAuthorityLanguage.js";

const hash = /^[0-9a-f]{64}$/;
const experienceId = /^p33x_[0-9a-f]{24}$/;
const statuses = new Set([
  "planned", "a_recorded", "b_recorded", "a2_recorded", "scored", "cancelled",
]);
const workflowKeys = [
  "workflow_id", "created_at", "updated_at", "status", "source_run_id", "complaint",
  "packet", "stage_run_ids", "stage_eligible_lap_numbers", "stage_experiment_contexts",
  "analysis_version", "execution", "reproduction_snapshot", "quality", "learning_admitted",
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
    || !stageMap(value.stage_run_ids)
    || !stageLapMap(value.stage_eligible_lap_numbers)
    || !stageContextMap(value.stage_experiment_contexts)
    || !nonempty(value.analysis_version)
    || !nullableRecord(value.execution)
    || !record(value.reproduction_snapshot)
    || !nullableRecord(value.quality)
    || !(value.learning_admitted === null || typeof value.learning_admitted === "boolean")
    || !hasValidLearningCaptureMetadata(value)) return false;
  return value.status === "scored" || value.learning_capture_state === "not_applicable";
}
