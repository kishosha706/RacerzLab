import type { components as OpenApiComponents } from "../types/openapi.generated";

type HandlingBalanceReport = OpenApiComponents["schemas"]["HandlingBalanceReport"];

const REPORT_SCHEMA_VERSION = "p-handling-balance.report.v1";
const ASSESSMENT_SCHEMA_VERSION = "p-handling-balance.assessment.v1";

const CLASSIFICATIONS: ReadonlySet<string> = new Set([
  "no_significant_imbalance_qualified",
  "rotation_response_deficit",
  "rotation_response_excess",
  "mixed_phase_dependent",
  "transient_rotation_anomaly",
  "steering_response_anomaly",
  "inconclusive",
  "unavailable",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Client trust boundary for the automatic handling-balance report.
 *
 * The report is observation-only by contract. Any payload whose authority
 * drifts from `observation_only`, whose setup_authorized becomes true, or whose
 * run identity mismatches is rejected before it can reach a workspace.
 */
export function isHandlingBalanceReport(
  payload: unknown,
  expectation: { runId: string },
): payload is HandlingBalanceReport {
  if (!isRecord(payload)) return false;
  if (payload.schema_version !== REPORT_SCHEMA_VERSION) return false;
  if (payload.run_id !== expectation.runId) return false;
  if (payload.authority !== "observation_only") return false;
  if (payload.setup_authorized !== false) return false;
  if (typeof payload.classification !== "string" || !CLASSIFICATIONS.has(payload.classification)) {
    return false;
  }
  if (typeof payload.eligible_laps !== "number" || payload.eligible_laps < 0) return false;
  if (typeof payload.reference_lap_count !== "number" || payload.reference_lap_count < 0) return false;

  const assessments = payload.assessments;
  if (assessments !== undefined) {
    if (!Array.isArray(assessments)) return false;
    for (const assessment of assessments) {
      if (!isRecord(assessment)) return false;
      if (assessment.schema_version !== ASSESSMENT_SCHEMA_VERSION) return false;
      if (assessment.run_id !== expectation.runId) return false;
      if (assessment.authority !== "observation_only") return false;
      if (assessment.setup_authorized !== false) return false;
      if (assessment.driver_feedback_source !== false) return false;
      if (
        typeof assessment.classification !== "string"
        || !CLASSIFICATIONS.has(assessment.classification)
      ) {
        return false;
      }
      if (typeof assessment.observation_text !== "string" || assessment.observation_text.trim() === "") {
        return false;
      }
      if (typeof assessment.confidence_score !== "number"
        || assessment.confidence_score < 0 || assessment.confidence_score > 1) {
        return false;
      }
    }
  }
  return true;
}

export const HANDLING_CLASSIFICATION_LABELS: Record<string, string> = {
  no_significant_imbalance_qualified: "No significant imbalance qualified",
  rotation_response_deficit: "Reduced rotation response",
  rotation_response_excess: "Excess rotation-like response",
  mixed_phase_dependent: "Mixed phase-dependent response",
  transient_rotation_anomaly: "Transient rotation anomaly",
  steering_response_anomaly: "Steering-response anomaly",
  inconclusive: "Inconclusive",
  unavailable: "Unavailable",
};

export const HANDLING_PHASE_LABELS: Record<string, string> = {
  turn_in: "Turn-in",
  entry: "Entry",
  apex_region: "Apex",
  center: "Center",
  initial_throttle: "Initial throttle",
  full_throttle_exit: "Exit",
  following_straight_carry: "Exit carry",
};
