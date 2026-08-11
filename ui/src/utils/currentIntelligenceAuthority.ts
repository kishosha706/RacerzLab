import type { IntelligenceCitation, RunIntelligenceReport } from "../types/intelligence";
import type { ControlledWorkflow, EvidenceState } from "../types/telemetry";
import {
  exactEventIdentitySet,
  trustedSetupAuthorizedMove,
  type IntelligenceWorkflowRevision,
} from "./intelligenceNavigation";

export type CurrentIntelligenceAuthority = {
  sourceRunId: string;
  sessionId: string;
  workflowId: string;
  workflowUpdatedAt: string;
  stage: "B";
  controlKey: string;
  currentValue: string;
  proposedValue: string;
  instruction: string;
  sourceEventIds: readonly string[];
};

export type CurrentReportSetupAuthority = {
  sourceRunId: string;
  sessionId: string | null;
  workflowId: string | null;
  workflowUpdatedAt: string | null;
  stage: "fresh" | "B";
  controlKey: string;
  currentValue: string;
  proposedValue: string;
  instruction: string;
  sourceEventIds: readonly string[];
};

export type CurrentIntelligenceAuthorityStatus = "idle" | "checking" | "authorized" | "withheld" | "error";

type RuntimeCard = {
  controlKey: string;
  controlLabel: string;
  currentValue: string;
  proposedValue: string;
  instruction: string;
  sourceEventIds: string[];
  stageInstructions: string[];
  requiredLaps: number;
  acceptanceThreshold: string;
  stopRule: string;
};

const QUALIFIED_CITATION_STATES: ReadonlySet<EvidenceState> = new Set([
  "measured",
  "calculated",
  "estimated_proxy",
  "observed_correlation",
  "controlled_test_effect",
]);

const AUTHORIZED_ACTION_STATES: ReadonlySet<EvidenceState> = new Set([
  ...QUALIFIED_CITATION_STATES,
  "needs_confirmation",
]);

const SETUP_CONTROL_LABELS: Readonly<Record<string, string>> = {
  lf_ride_height_mm: "LF Ride Height",
  rf_ride_height_mm: "RF Ride Height",
  lr_ride_height_mm: "LR Ride Height",
  rr_ride_height_mm: "RR Ride Height",
  lf_front_spring_n_per_mm: "LF Spring",
  rf_front_spring_n_per_mm: "RF Spring",
  lr_rear_spring_n_per_mm: "LR Spring",
  rr_rear_spring_n_per_mm: "RR Spring",
  nose_weight_percent: "Nose Weight",
  cross_weight_percent: "Cross Weight",
  tape_percent: "Tape / Cooling Configuration",
  rear_end_ratio: "Rear End Ratio",
  front_brake_bias_percent: "Front Brake Bias",
  steering_ratio: "Steering Ratio / Pinion",
  steering_offset_deg: "Steering Offset",
};

const SETUP_VALUE_FORMATS: Readonly<Record<string, { factor: number; decimals: number; unit: string | null }>> = {
  lf_ride_height_mm: { factor: 1 / 25.4, decimals: 3, unit: "in" },
  rf_ride_height_mm: { factor: 1 / 25.4, decimals: 3, unit: "in" },
  lr_ride_height_mm: { factor: 1 / 25.4, decimals: 3, unit: "in" },
  rr_ride_height_mm: { factor: 1 / 25.4, decimals: 3, unit: "in" },
  lf_front_spring_n_per_mm: { factor: 5.71014716277, decimals: 0, unit: "lb/in" },
  rf_front_spring_n_per_mm: { factor: 5.71014716277, decimals: 0, unit: "lb/in" },
  lr_rear_spring_n_per_mm: { factor: 5.71014716277, decimals: 0, unit: "lb/in" },
  rr_rear_spring_n_per_mm: { factor: 5.71014716277, decimals: 0, unit: "lb/in" },
  nose_weight_percent: { factor: 1, decimals: 1, unit: "%" },
  cross_weight_percent: { factor: 1, decimals: 1, unit: "%" },
  tape_percent: { factor: 1, decimals: 0, unit: "%" },
  rear_end_ratio: { factor: 1, decimals: 3, unit: ":1" },
  front_brake_bias_percent: { factor: 1, decimals: 1, unit: "%" },
  steering_ratio: { factor: 1, decimals: 1, unit: null },
  steering_offset_deg: { factor: 1, decimals: 1, unit: "deg" },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function canonicalText(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.trim() === value;
}

function canonicalTextList(value: unknown, requireNonempty = false): value is string[] {
  if (!Array.isArray(value) || (requireNonempty && value.length === 0)) return false;
  return value.every(canonicalText) && new Set(value).size === value.length;
}

function exactTextList(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function numericSetupValue(value: unknown): number | null {
  if (typeof value === "boolean" || value == null) return null;
  const candidate = typeof value === "number"
    ? value
    : typeof value === "string"
      ? value.replace(/,/g, "").match(/[-+]?\d+(?:\.\d+)?/)?.[0]
      : null;
  if (candidate == null) return null;
  const parsed = Number(candidate);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatSetupValue(controlKey: string, value: unknown): string | null {
  const format = SETUP_VALUE_FORMATS[controlKey];
  if (!format || value == null || typeof value === "boolean") return null;
  if (
    controlKey === "steering_ratio"
    && typeof value === "string"
    && (value.includes(":") || value.toLocaleLowerCase().includes("mm/rev"))
  ) return canonicalText(value) ? value : null;
  const numeric = numericSetupValue(value);
  if (numeric == null) return canonicalText(value) ? value : null;
  const rendered = (numeric * format.factor).toFixed(format.decimals);
  if (!format.unit) return rendered;
  return ["%", ":1"].includes(format.unit)
    ? `${rendered}${format.unit}`
    : `${rendered} ${format.unit}`;
}

function runtimeCard(workflow: ControlledWorkflow): RuntimeCard | null {
  if (
    workflow.packet.decision !== "test"
    || workflow.status !== "a_recorded"
    || workflow.stage_run_ids.A !== workflow.source_run_id
    || workflow.stage_run_ids.B != null
    || workflow.stage_run_ids.A2 != null
  ) return null;
  const value = workflow.packet.primary_test as unknown;
  if (!isRecord(value)) return null;
  const controlKey = value.control_key;
  const controlLabel = value.control_label;
  const proposedValue = value.proposed_value;
  const instruction = value.exact_change;
  const sourceEventIds = value.evidence_event_ids;
  const stopRule = value.stop_rule;
  const successMetrics = value.success_metrics;
  const stages = value.stages;
  if (
    !canonicalText(controlKey)
    || !canonicalText(controlLabel)
    || controlLabel !== SETUP_CONTROL_LABELS[controlKey]
    || !canonicalText(proposedValue)
    || !canonicalText(instruction)
    || !canonicalTextList(sourceEventIds, true)
    || !canonicalText(stopRule)
    || !canonicalTextList(successMetrics, true)
    || !Array.isArray(stages)
    || stages.length !== 3
  ) return null;
  const currentValue = formatSetupValue(controlKey, value.current_value);
  const proposedRawValue = formatSetupValue(controlKey, value.proposed_value_raw);
  if (
    !currentValue
    || proposedRawValue !== proposedValue
    || instruction !== `${currentValue} -> ${proposedValue} (adjacent observed tech-passing option)`
  ) return null;
  const stageInstructions: string[] = [];
  let requiredLaps = 0;
  const expectedStages = ["A", "B", "A2"];
  for (const [index, stage] of stages.entries()) {
    if (!isRecord(stage) || stage.stage !== expectedStages[index] || !canonicalText(stage.setup_instruction)) return null;
    if (
      typeof stage.warmup_laps !== "number"
      || !Number.isInteger(stage.warmup_laps)
      || stage.warmup_laps < 0
      || typeof stage.required_flying_laps !== "number"
      || !Number.isInteger(stage.required_flying_laps)
      || stage.required_flying_laps < 1
    ) return null;
    stageInstructions.push(stage.setup_instruction);
    requiredLaps += stage.warmup_laps + stage.required_flying_laps;
  }
  if (stageInstructions[1] !== `Change only ${controlLabel}: ${instruction}.`) return null;
  return {
    controlKey,
    controlLabel,
    currentValue,
    proposedValue,
    instruction,
    sourceEventIds,
    stageInstructions,
    requiredLaps,
    acceptanceThreshold: successMetrics.join("; "),
    stopRule,
  };
}

function citationIsQualified(citation: unknown, runId: string): citation is IntelligenceCitation {
  return isRecord(citation)
    && citation.run_id === runId
    && canonicalText(citation.event_id)
    && citation.valid_for_tuning === true
    && QUALIFIED_CITATION_STATES.has(citation.evidence_state as EvidenceState)
    && canonicalTextList(citation.source_channels, true);
}

function reportCitations(report: RunIntelligenceReport): IntelligenceCitation[] {
  const citations: IntelligenceCitation[] = [];
  const append = (value: unknown) => {
    if (!Array.isArray(value)) return;
    citations.push(...value.filter(isRecord) as unknown as IntelligenceCitation[]);
  };
  if (Array.isArray(report.competing_causes)) {
    report.competing_causes.forEach((cause) => {
      if (!isRecord(cause)) return;
      append(cause.evidence_for);
      append(cause.evidence_against);
    });
  }
  if (isRecord(report.best_measurement)) append(report.best_measurement.citations);
  if (Array.isArray(report.context_matches)) {
    report.context_matches.forEach((match) => {
      if (isRecord(match)) append(match.citations);
    });
  }
  if (Array.isArray(report.narrative)) {
    report.narrative.forEach((entry) => {
      if (isRecord(entry)) append(entry.citations);
    });
  }
  if (isRecord(report.data_quality)) append(report.data_quality.citations);
  return citations;
}

/**
 * Validates the complete public-report side of a Stage B setup action. This is
 * deliberately shared by Engineer and the persisted-workflow projection so a
 * report cannot be actionable in one workspace and withheld in another.
 */
export function deriveCurrentReportSetupAuthority(
  report: RunIntelligenceReport | null | undefined,
  sourceRunId: string | null | undefined,
  sessionId: string | null | undefined,
  workflowRevision: IntelligenceWorkflowRevision,
): CurrentReportSetupAuthority | null {
  if (!report || !canonicalText(sourceRunId) || !canonicalText(sessionId)) return null;
  const hasWorkflowId = workflowRevision.workflowId != null;
  const hasWorkflowUpdatedAt = workflowRevision.workflowUpdatedAt != null;
  if (
    hasWorkflowId !== hasWorkflowUpdatedAt
    || (hasWorkflowId && (
      !canonicalText(workflowRevision.workflowId)
      || !canonicalText(workflowRevision.workflowUpdatedAt)
    ))
  ) return null;
  const workflowBound = hasWorkflowId && hasWorkflowUpdatedAt;
  const briefing = report.briefing;
  const action = briefing?.action;
  const measurement = report.best_measurement;
  const preflight = report.test_preflight;
  const move = report.next_trustworthy_move;
  const telemetryHealth = report.telemetry_health;
  if (
    report.run_id !== sourceRunId
    || report.session_id !== sessionId
    || telemetryHealth?.session_id !== sessionId
    || telemetryHealth.current_run_id !== sourceRunId
    || !canonicalTextList(telemetryHealth.ordered_session_run_ids, true)
    || !telemetryHealth.ordered_session_run_ids.includes(sourceRunId)
    || report.status !== "ready"
    || report.decision_status !== "ready"
    || report.data_quality?.status !== "ready"
    || !Array.isArray(report.data_quality.issues)
    || report.data_quality.issues.length !== 0
    || !Array.isArray(report.blocker_reasons)
    || report.blocker_reasons.length !== 0
    || !briefing
    || !Array.isArray(briefing.blocker_reasons)
    || briefing.blocker_reasons.length !== 0
    || action?.kind !== "controlled_test"
    || action.setup_authorized !== true
    || !canonicalText(action.control_key)
    || !canonicalText(action.current_value)
    || !canonicalText(action.proposed_value)
    || !canonicalText(action.instruction)
    || action.instruction !== `${action.current_value} -> ${action.proposed_value} (adjacent observed tech-passing option)`
    || !AUTHORIZED_ACTION_STATES.has(action.evidence_state)
    || !canonicalTextList(action.source_event_ids, true)
    || !Array.isArray(action.blocker_reasons)
    || action.blocker_reasons.length !== 0
    || !measurement
    || measurement.mission_id !== `controlled-test:${action.control_key}`
    || !Array.isArray(measurement.procedure)
    || measurement.procedure.length !== 3
    || !measurement.procedure.every(canonicalText)
    || typeof measurement.required_laps !== "number"
    || !Number.isInteger(measurement.required_laps)
    || measurement.required_laps < 1
    || !canonicalText(measurement.acceptance_threshold)
    || !canonicalText(measurement.stop_rule)
    || !canonicalTextList(measurement.controlled_variables, true)
    || measurement.controlled_variables.length !== 1
  ) return null;
  const controlledVariable = measurement.controlled_variables[0];
  const controlledLabel = SETUP_CONTROL_LABELS[action.control_key] ?? null;
  if (
    !canonicalText(controlledLabel)
    || controlledVariable !== `Change only ${controlledLabel}.`
    || !exactTextList(measurement.procedure, [
      `Keep ${controlledLabel} at the recorded baseline value.`,
      `Change only ${controlledLabel}: ${action.instruction}.`,
      `Keep ${controlledLabel} at the recorded baseline value.`,
    ])
  ) return null;

  const measurementCitations = Array.isArray(measurement.citations) ? measurement.citations : [];
  if (
    measurementCitations.length !== action.source_event_ids.length
    || !measurementCitations.every((citation) => citationIsQualified(citation, sourceRunId))
    || !exactEventIdentitySet(
      action.source_event_ids,
      measurementCitations.flatMap((citation) => citation.event_id ? [citation.event_id] : []),
    )
  ) return null;

  const actionEventSet = new Set(action.source_event_ids);
  const qualifiedActionCitationIds = [...new Set(
    reportCitations(report)
      .filter((citation) => citation.event_id != null && actionEventSet.has(citation.event_id))
      .filter((citation) => citationIsQualified(citation, sourceRunId))
      .flatMap((citation) => citation.event_id ? [citation.event_id] : []),
  )];
  if (!exactEventIdentitySet(action.source_event_ids, qualifiedActionCitationIds)) return null;

  if (!workflowBound) {
    if (
      preflight != null
      || move?.authority === "setup_authorized"
      || move?.workflow_id != null
      || move?.workflow_updated_at != null
    ) return null;
    return {
      sourceRunId,
      sessionId,
      workflowId: null,
      workflowUpdatedAt: null,
      stage: "fresh",
      controlKey: action.control_key,
      currentValue: action.current_value,
      proposedValue: action.proposed_value,
      instruction: action.instruction,
      sourceEventIds: [...action.source_event_ids],
    };
  }

  if (
    report.mission_stage !== "test"
    || preflight?.workflow_id !== workflowRevision.workflowId
    || preflight.stage !== "B"
    || preflight.status !== "ready"
    || !Array.isArray(preflight.blocker_reasons)
    || preflight.blocker_reasons.length !== 0
    || !Array.isArray(preflight.checks)
  ) return null;
  const setupChecks = preflight.checks.filter((check) => check.check_id === "setup-state");
  if (
    setupChecks.length !== 1
    || setupChecks[0].state !== "required"
    || setupChecks[0].detail !== measurement.procedure[1]
  ) return null;
  if (!trustedSetupAuthorizedMove(move, sourceRunId, {
    ...workflowRevision,
    controlKey: action.control_key,
    sourceEventIds: action.source_event_ids,
  }) || move.instruction !== action.instruction) return null;

  return {
    sourceRunId,
    sessionId,
    workflowId: workflowRevision.workflowId,
    workflowUpdatedAt: workflowRevision.workflowUpdatedAt,
    stage: "B",
    controlKey: action.control_key,
    currentValue: action.current_value,
    proposedValue: action.proposed_value,
    instruction: action.instruction,
    sourceEventIds: [...action.source_event_ids],
  };
}

/**
 * Projects the only UI setup authority: an exact source-run Stage B card whose
 * current public report, workflow revision, and qualified citations all agree.
 */
export function deriveCurrentIntelligenceAuthority(
  report: RunIntelligenceReport | null | undefined,
  workflow: ControlledWorkflow | null | undefined,
  sourceRunId: string | null | undefined,
  sessionId: string | null | undefined,
): CurrentIntelligenceAuthority | null {
  if (!report || !workflow || !canonicalText(sourceRunId) || !canonicalText(sessionId)) return null;
  const workflowUpdatedAt = workflow.updated_at ?? null;
  const card = runtimeCard(workflow);
  const measurement = report.best_measurement;
  const reportAuthority = deriveCurrentReportSetupAuthority(
    report,
    sourceRunId,
    sessionId,
    { workflowId: workflow.workflow_id, workflowUpdatedAt },
  );
  if (
    !card
    || !reportAuthority
    || reportAuthority.stage !== "B"
    || reportAuthority.sessionId == null
    || reportAuthority.workflowId == null
    || reportAuthority.workflowUpdatedAt == null
    || workflow.source_run_id !== sourceRunId
    || !canonicalText(workflow.workflow_id)
    || !canonicalText(workflowUpdatedAt)
    || reportAuthority.controlKey !== card.controlKey
    || reportAuthority.currentValue !== card.currentValue
    || reportAuthority.proposedValue !== card.proposedValue
    || reportAuthority.instruction !== card.instruction
    || !exactEventIdentitySet(reportAuthority.sourceEventIds, card.sourceEventIds)
    || !measurement
    || !Array.isArray(measurement.procedure)
    || !exactTextList(measurement.procedure, card.stageInstructions)
    || measurement.required_laps !== card.requiredLaps
    || measurement.acceptance_threshold !== card.acceptanceThreshold
    || measurement.stop_rule !== card.stopRule
    || !Array.isArray(measurement.controlled_variables)
    || !exactTextList(measurement.controlled_variables, [`Change only ${card.controlLabel}.`])
  ) return null;
  return {
    ...reportAuthority,
    sessionId: reportAuthority.sessionId,
    workflowId: reportAuthority.workflowId,
    workflowUpdatedAt: reportAuthority.workflowUpdatedAt,
    stage: "B",
  };
}

export function currentIntelligenceAuthorityMatchesWorkflow(
  authority: CurrentIntelligenceAuthority | null | undefined,
  workflow: ControlledWorkflow | null | undefined,
): authority is CurrentIntelligenceAuthority {
  if (!authority || !workflow) return false;
  const card = runtimeCard(workflow);
  return card != null
    && authority.sourceRunId === workflow.source_run_id
    && authority.workflowId === workflow.workflow_id
    && authority.workflowUpdatedAt === workflow.updated_at
    && authority.stage === "B"
    && authority.controlKey === card.controlKey
    && authority.currentValue === card.currentValue
    && authority.proposedValue === card.proposedValue
    && authority.instruction === card.instruction
    && exactEventIdentitySet(authority.sourceEventIds, card.sourceEventIds);
}

export const CURRENT_INTELLIGENCE_AUTHORITY_RECOVERY =
  "Current source-run intelligence withheld the exact Stage B card. Review the current evidence, abandon the stale workflow if needed, or rebuild it from a newly qualified report.";
