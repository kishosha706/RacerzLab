import { AlertTriangle, CheckCircle2, Circle, ClipboardList, Crosshair, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  analyzeRunDialIn,
  attachControlledWorkflowStage,
  cancelControlledWorkflow,
  fetchControlledWorkflowReport,
  fetchControlledWorkflows,
  scoreControlledWorkflow,
  startControlledWorkflow,
} from "../api/client";
import { useCompareBasket } from "../store/CompareBasketContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { setupSnapshotMatchesRun } from "../utils/evidenceTrust";
import {
  currentIntelligenceAuthorityMatchesWorkflow,
  type CurrentIntelligenceAuthority,
  type CurrentIntelligenceAuthorityStatus,
} from "../utils/currentIntelligenceAuthority";
import type {
  ControlledWorkflow,
  DialInDecisionContext,
  DialInObjective,
  DialInPriority,
  DialInResponse,
  DialInSwing,
  MeasurementMission,
  RunOverview,
} from "../types/telemetry";

type DialInTabProps = {
  overview: RunOverview | null;
  workflowScopeRunIds: readonly string[];
  workflowHandoffKey: string | null;
  workflowOpenIntentId: string | null;
  currentIntelligenceAuthority: CurrentIntelligenceAuthority | null;
  intelligenceAuthorityStatus: CurrentIntelligenceAuthorityStatus;
  intelligenceAuthorityRecovery: string;
};

const DIAL_IN_INITIAL_LIMIT = 9;
const SHOW_MORE_STEP = 9;
const DIAL_IN_REQUEST_LIMIT = DIAL_IN_INITIAL_LIMIT + SHOW_MORE_STEP;
const MAX_VISIBLE_UNVERIFIED_HYPOTHESES = 3;
const MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER = "Multiple active workflows touch this run or session. Choose one below and abandon the extra workflow until only one remains. No workflow has setup authority while this conflict remains.";

type WorkflowLapScope = "run" | "single_lap" | "lap_window" | "track_zone";

type CompleteDialInDecisionContext = {
  selected_lap: number | null;
  lap_scope: WorkflowLapScope;
  window_start_lap: number | null;
  window_end_lap: number | null;
  representative_lap: number | null;
  selected_zone_start_pct: number | null;
  selected_zone_end_pct: number | null;
  selected_zone_label: string | null;
  selected_phase: string | null;
  objective: DialInObjective;
  priority: DialInPriority;
};

type DialInRequestBinding = {
  run_id: string;
  normalized_complaint: string;
  decision_context: CompleteDialInDecisionContext;
  selection_context: {
    lap_scope: string;
    selected_lap: number | null;
    window_start_lap: number | null;
    window_end_lap: number | null;
    representative_lap: number | null;
  };
};

type WorkflowPlanBinding = {
  workflow_id: string;
  source_run_id: string;
  normalized_complaint: string;
  decision_context: CompleteDialInDecisionContext;
  packet_fingerprint: string;
};

const PHASE_OPTIONS = [
  ["", "Auto-detect"],
  ["braking", "Braking"],
  ["entry", "Corner entry"],
  ["center", "Corner center"],
  ["exit", "Corner exit"],
  ["transition", "Transition"],
  ["bump_curb", "Bump or curb"],
  ["straight", "Straight"],
] as const;

const OBJECTIVE_OPTIONS: Array<[DialInObjective, string]> = [
  ["race-pace", "Race pace"],
  ["qualifying", "Qualifying pace"],
  ["long-run", "Long-run consistency"],
  ["tire-conservation", "Tire conservation"],
  ["driver-confidence", "Driver confidence"],
];

const PRIORITY_OPTIONS: Array<[DialInPriority, string]> = [
  ["overall-pace", "Overall pace"],
  ["entry-security", "Entry pace focus"],
  ["center-rotation", "Center pace focus"],
  ["exit-drive", "Exit pace focus"],
  ["tire-life", "Tire life"],
  ["platform-margin", "Platform margin"],
];

const WORKFLOW_STAGES = ["A", "B", "A2"] as const;

function normalizeComplaint(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLocaleLowerCase().replace(/\s+/g, " ");
  return normalized || null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

function readNullableNumber(record: Record<string, unknown>, key: string): number | null | undefined {
  if (!hasOwn(record, key)) return undefined;
  const value = record[key];
  return value === null || (typeof value === "number" && Number.isFinite(value)) ? value : undefined;
}

function readNullableText(record: Record<string, unknown>, key: string): string | null | undefined {
  if (!hasOwn(record, key)) return undefined;
  const value = record[key];
  if (value === null) return null;
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
}

function readCompleteDecisionContext(workflow: ControlledWorkflow | null): CompleteDialInDecisionContext | null {
  const snapshot = workflow?.reproduction_snapshot;
  if (!isRecord(snapshot) || !isRecord(snapshot.decision_context)) return null;
  const context = snapshot.decision_context;
  const selectedLap = readNullableNumber(context, "selected_lap");
  const lapScope = context.lap_scope;
  const windowStartLap = readNullableNumber(context, "window_start_lap");
  const windowEndLap = readNullableNumber(context, "window_end_lap");
  const representativeLap = readNullableNumber(context, "representative_lap");
  const zoneStart = readNullableNumber(context, "selected_zone_start_pct");
  const zoneEnd = readNullableNumber(context, "selected_zone_end_pct");
  const zoneLabel = readNullableText(context, "selected_zone_label");
  const selectedPhase = readNullableText(context, "selected_phase");
  const objective = context.objective;
  const priority = context.priority;
  if (
    selectedLap === undefined
    || (selectedLap !== null && (!Number.isInteger(selectedLap) || selectedLap < 1))
    || !["run", "single_lap", "lap_window", "track_zone"].includes(String(lapScope))
    || windowStartLap === undefined
    || windowEndLap === undefined
    || representativeLap === undefined
    || [windowStartLap, windowEndLap, representativeLap].some(
      (value) => value !== null && (!Number.isInteger(value) || value < 1),
    )
    || zoneStart === undefined
    || zoneEnd === undefined
    || zoneLabel === undefined
    || selectedPhase === undefined
    || !hasOwn(context, "objective")
    || !OBJECTIVE_OPTIONS.some(([value]) => value === objective)
    || !hasOwn(context, "priority")
    || !PRIORITY_OPTIONS.some(([value]) => value === priority)
  ) return null;
  if (lapScope === "lap_window") {
    if (
      selectedLap === null
      || windowStartLap === null
      || windowEndLap === null
      || representativeLap === null
      || selectedLap !== representativeLap
      || windowStartLap > representativeLap
      || representativeLap > windowEndLap
    ) return null;
  } else if (windowStartLap !== null || windowEndLap !== null || representativeLap !== null) {
    return null;
  }
  if (lapScope === "single_lap" && selectedLap === null) return null;
  if (lapScope === "run" && selectedLap !== null) return null;
  if ((zoneStart === null) !== (zoneEnd === null)) return null;
  if (zoneStart !== null && zoneEnd !== null && !(zoneStart >= 0 && zoneStart < zoneEnd && zoneEnd <= 100)) return null;
  return {
    selected_lap: selectedLap,
    lap_scope: lapScope as WorkflowLapScope,
    window_start_lap: windowStartLap,
    window_end_lap: windowEndLap,
    representative_lap: representativeLap,
    selected_zone_start_pct: zoneStart,
    selected_zone_end_pct: zoneEnd,
    selected_zone_label: zoneLabel,
    selected_phase: selectedPhase,
    objective: objective as DialInObjective,
    priority: priority as DialInPriority,
  };
}

function decisionContextsMatch(
  left: CompleteDialInDecisionContext,
  right: CompleteDialInDecisionContext,
): boolean {
  return left.selected_lap === right.selected_lap
    && left.lap_scope === right.lap_scope
    && left.window_start_lap === right.window_start_lap
    && left.window_end_lap === right.window_end_lap
    && left.representative_lap === right.representative_lap
    && left.selected_zone_start_pct === right.selected_zone_start_pct
    && left.selected_zone_end_pct === right.selected_zone_end_pct
    && left.selected_zone_label === right.selected_zone_label
    && left.selected_phase === right.selected_phase
    && left.objective === right.objective
    && left.priority === right.priority;
}

function requestBindingsMatch(left: DialInRequestBinding | null, right: DialInRequestBinding | null): boolean {
  if (!left || !right) return left === right;
  return left.run_id === right.run_id
    && left.normalized_complaint === right.normalized_complaint
    && decisionContextsMatch(left.decision_context, right.decision_context)
    && left.selection_context.lap_scope === right.selection_context.lap_scope
    && left.selection_context.selected_lap === right.selection_context.selected_lap
    && left.selection_context.window_start_lap === right.selection_context.window_start_lap
    && left.selection_context.window_end_lap === right.selection_context.window_end_lap
    && left.selection_context.representative_lap === right.selection_context.representative_lap;
}

function workflowMatchesRequest(workflow: ControlledWorkflow, request: DialInRequestBinding): boolean {
  const returnedContext = readCompleteDecisionContext(workflow);
  return workflow.workflow_id.length > 0
    && workflow.workflow_id === workflow.workflow_id.trim()
    && workflow.source_run_id === request.run_id
    && normalizeComplaint(workflow.complaint) === request.normalized_complaint
    && returnedContext != null
    && decisionContextsMatch(returnedContext, request.decision_context);
}

function stableSerialize(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableSerialize).join(",")}]`;
  if (isRecord(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableSerialize(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

function captureWorkflowPlanBinding(workflow: ControlledWorkflow): WorkflowPlanBinding | null {
  const normalized = normalizeComplaint(workflow.complaint);
  const context = readCompleteDecisionContext(workflow);
  if (
    !normalized
    || !context
    || !workflow.workflow_id
    || workflow.workflow_id !== workflow.workflow_id.trim()
    || !workflow.source_run_id
    || workflow.source_run_id !== workflow.source_run_id.trim()
  ) return null;
  return {
    workflow_id: workflow.workflow_id,
    source_run_id: workflow.source_run_id,
    normalized_complaint: normalized,
    decision_context: context,
    packet_fingerprint: stableSerialize(workflow.packet),
  };
}

function activeWorkflowIntegrityError(workflow: ControlledWorkflow | null): string | null {
  if (!workflow || workflow.status === "scored" || workflow.status === "cancelled") return null;
  return captureWorkflowPlanBinding(workflow) == null
    ? "The active workflow is missing a complete complaint or decision-context identity. Setup authority is withheld and exact targets are hidden. Reopen Dial-In after the workflow record is repaired."
    : null;
}

function workflowPreservesPlan(binding: WorkflowPlanBinding, workflow: ControlledWorkflow): boolean {
  const returned = captureWorkflowPlanBinding(workflow);
  return returned != null
    && returned.workflow_id === binding.workflow_id
    && returned.source_run_id === binding.source_run_id
    && returned.normalized_complaint === binding.normalized_complaint
    && decisionContextsMatch(returned.decision_context, binding.decision_context)
    && returned.packet_fingerprint === binding.packet_fingerprint;
}

function stageBindingsMatch(
  before: ControlledWorkflow["stage_run_ids"],
  after: ControlledWorkflow["stage_run_ids"],
  requestedStage?: "A" | "B" | "A2",
  requestedRunId?: string,
): boolean {
  if ([...Object.keys(before), ...Object.keys(after)].some(
    (stage) => !WORKFLOW_STAGES.includes(stage as "A" | "B" | "A2"),
  )) return false;
  return WORKFLOW_STAGES.every((stage) => {
    if (stage === requestedStage) return before[stage] == null && after[stage] === requestedRunId;
    return (after[stage] ?? null) === (before[stage] ?? null);
  });
}

const SYMPTOM_PRESETS = [
  ["Tight center", "tight center"],
  ["Loose exit", "loose on corner exit"],
  ["Loose entry", "loose on corner entry"],
  ["Won't stay low", "won't stay on the bottom"],
  ["Bottoming", "nose is dragging or bottoming"],
  ["RF overworked", "right-front tire is overworked"],
] as const;

function workflowDecisionPresentation(workflow: ControlledWorkflow | null): { label: string; explanation: string } {
  if (workflow?.packet.decision === "measure") {
    return {
      label: "Measurement mission",
      explanation: "No setup change is approved. Gather the named evidence first.",
    };
  }
  if (
    workflow?.status === "scored"
    && workflow.quality?.controlled_effect_eligible
    && workflow.quality.verdict === "keep"
  ) {
    return {
      label: "Fix recommendation",
      explanation: "A completed controlled test supports keeping this exact change.",
    };
  }
  return {
    label: "Exploratory test",
    explanation: "One reversible change will test the leading hypothesis; it is not yet a proven fix.",
  };
}

function isActiveControlledTest(workflow: ControlledWorkflow | null): workflow is ControlledWorkflow {
  return workflow?.packet.decision === "test"
    && workflow.status !== "scored"
    && workflow.status !== "cancelled";
}

function cleanLabel(value: string | null | undefined, fallback = "Not mapped"): string {
  if (!value) return fallback;
  const aliases: Record<string, string> = {
    final_drive: "Rear End Ratio",
  };
  if (aliases[value]) return aliases[value];
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDecisionLapScope(context: CompleteDialInDecisionContext): string {
  if (
    context.lap_scope === "lap_window"
    && context.window_start_lap != null
    && context.window_end_lap != null
    && context.representative_lap != null
  ) {
    return `Window L${context.window_start_lap}–L${context.window_end_lap} · Rep L${context.representative_lap}`;
  }
  if (context.selected_lap != null) {
    return context.lap_scope === "track_zone"
      ? `Track zone · Lap ${context.selected_lap}`
      : `Lap ${context.selected_lap}`;
  }
  return context.lap_scope === "track_zone" ? "Track zone" : "Run scope";
}

function dialInTone(label: string): "good" | "warn" | "neutral" {
  const normalized = label.toLowerCase();
  if (normalized.includes("ready") || normalized.includes("clear") || normalized.includes("clean") || normalized.includes("high")) return "good";
  if (normalized.includes("need") || normalized.includes("partial") || normalized.includes("risk") || normalized.includes("missing") || normalized.includes("some")) return "warn";
  return "neutral";
}

function formatTargetList(swing: DialInSwing): string {
  const labels = swing.validate_with_labels ?? swing.validate_with.map((value) => value.replace(/_/g, " "));
  const targets = labels.filter((item, index, all) => item && all.indexOf(item) === index);
  return targets.join(", ") || "the same corner phase";
}

function garageLeverLabel(swing: DialInSwing): string | null {
  if (swing.setup_area === "shock_collar" || swing.setup_area.includes("ride_height")) {
    return "Garage note: use the named Ride Height fields. If this car exposes collar or perch offsets instead, recheck cross weight after the change.";
  }
  return null;
}

function dialInEvidenceHints(response: DialInResponse): string[] {
  const hints = new Set<string>();
  const nextStep = response.next_step ?? "";
  if (nextStep.includes("Compare baseline is missing")) {
    hints.add("Compare baseline is missing.");
  }
  if (nextStep.includes("Compare test run is missing")) {
    hints.add("Compare test run is missing.");
  }
  for (const warning of response.warnings) {
    const lower = warning.toLowerCase();
    if (lower.includes("car family could not be resolved")) hints.add("Car family is generic, so unsupported legacy-only areas stay filtered.");
    if (lower.includes("track family could not be resolved")) hints.add("Track family is generic, so the guide stays conservative.");
  }
  for (const swing of response.top_swings) {
    if (!swing.readiness_label.toLowerCase().includes("need")) continue;
    const area = swing.setup_area.toLowerCase();
    if (area.includes("shock") || area.includes("damper")) {
      hints.add("Live shock data is missing.");
    }
    if (area.includes("platform") || area.includes("ride") || area.includes("diffuser") || area.includes("rake")) {
      hints.add("Platform trace is missing for a stronger read.");
    }
  }
  return [...hints];
}

function SwingCard({ swing, compact = false, learning = false }: { swing: DialInSwing; compact?: boolean; learning?: boolean }) {
  const helper = garageLeverLabel(swing);
  const targetReady = swing.proposed_value_label != null && swing.blocker_reasons.length === 0;
  return (
    <article className={`dialin-swing-card${compact ? " compact" : ""}`}>
      <header>
        <div>
          <span>{cleanLabel(swing.setup_area, "Setup area")}</span>
          <h3>{swing.title}</h3>
          <p className="dialin-change-this">
            <span>{targetReady ? "Make this setup change:" : "Target unavailable — do not change:"}</span> {swing.change_this}
          </p>
          <p className="dialin-garage-helper">Garage control{(swing.control_keys?.length ?? 0) > 1 ? "s" : ""}: {swing.garage_lever}</p>
          <p className="dialin-garage-helper"><span>Why this size:</span> {swing.change_size_explanation}</p>
          {helper && <p className="dialin-garage-note">{helper}</p>}
        </div>
        <div className="dialin-card-pills">
          <span className="dialin-mini-pill">{swing.change_size_label}</span>
          <span className="dialin-mini-pill">{swing.influence_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.risk_label)}`}>{swing.risk_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.readiness_label)}`}>{swing.readiness_label}</span>
        </div>
      </header>
      <div className="dialin-action-grid">
        <div><span>{targetReady ? "Expected improvement" : "Mechanism to verify"}</span><p>{swing.effect}</p></div>
        <div><span>Trade-off</span><p>{swing.counter_effect}</p></div>
        {targetReady && <div><span>Keep it if</span><p>{swing.keep_if}</p></div>}
        {targetReady && <div><span>Undo it if</span><p>{swing.undo_if}</p></div>}
        {targetReady && !compact && <div><span>Test plan</span><p>{swing.one_change_test}</p></div>}
        {!targetReady && <div><span>Needed before a setup test</span><p>{swing.blocker_reasons.join(" ") || swing.disabled_reason}</p></div>}
        {learning && <div><span>What this control does</span><p>{swing.control_expectation}</p></div>}
        {learning && <div><span>Related settings to recheck</span><p>{swing.control_guardrail}</p></div>}
        {learning && (
          <div>
            <span>Evidence signals</span>
            <p>{formatTargetList(swing)}</p>
          </div>
        )}
      </div>
    </article>
  );
}

function workflowStageName(stage: "A" | "B" | "A2"): string {
  if (stage === "A") return "Baseline A";
  if (stage === "B") return "One change B";
  return "Restore A2";
}

function workflowMissionCopy(
  workflow: ControlledWorkflow,
  authority: CurrentIntelligenceAuthority | null,
): { label: string; detail: string } {
  if (workflow.status === "planned") {
    return {
      label: "Record baseline A",
      detail: "Prove the current car first. Do not change the setup yet.",
    };
  }
  if (workflow.status === "a_recorded") {
    return {
      label: authority ? "Run one change as B" : "Review Stage B authority",
      detail: authority?.instruction
        ?? "The stored Stage B target is withheld. Review current evidence, abandon this workflow, or rebuild it from a newly qualified report.",
    };
  }
  if (workflow.status === "b_recorded") {
    return {
      label: "Restore and record A2",
      detail: "Return to the exact baseline setup and repeat the measured laps.",
    };
  }
  if (workflow.status === "a2_recorded") {
    return {
      label: "Compare and score A/B/A2",
      detail: "All three stages are recorded. Let the verified comparison make the call.",
    };
  }
  if (workflow.status === "scored") {
    return {
      label: "Review the controlled verdict",
      detail: "Use the certificate to keep, undo, or retest in this exact context.",
    };
  }
  return {
    label: "Workflow retained as audit history",
    detail: "No setup learning was admitted from the cancelled protocol.",
  };
}

function controlledWorkflowHeadline(
  workflow: ControlledWorkflow,
  authority: CurrentIntelligenceAuthority | null,
): string {
  if (workflow.packet.decision !== "test") return workflow.packet.race_mode_summary;
  if (workflow.status === "planned") return "Record baseline A before any setup change.";
  if (workflow.status === "a_recorded") {
    return authority
      ? `Current source-run card: ${authority.instruction}`
      : "Stage B target withheld pending current source-run intelligence.";
  }
  if (workflow.status === "b_recorded") return "Restore the recorded baseline and verify A2.";
  if (workflow.status === "a2_recorded") return "All A/B/A2 stages are recorded and ready to score.";
  if (workflow.status === "cancelled") return "Cancelled workflow retained as non-authorizing audit history.";
  return "Controlled result retained as historical evidence.";
}

function ControlledWorkflowProgress({
  workflow,
  learning,
  authority,
}: {
  workflow: ControlledWorkflow;
  learning: boolean;
  authority: CurrentIntelligenceAuthority | null;
}) {
  const test = workflow.packet.primary_test;
  if (!test) return null;
  const nextStage = WORKFLOW_STAGES.find((stage) => workflow.stage_run_ids[stage] == null) ?? null;
  const verifiedCount = WORKFLOW_STAGES.filter((stage) => workflow.stage_run_ids[stage] != null).length;
  const mission = workflowMissionCopy(workflow, authority);
  return (
    <div className="dialin-workflow-progress" data-status={workflow.status}>
      <div className="dialin-workflow-mission" role="status" aria-live="polite">
        <div>
          <span>Mission stage</span>
          <strong>{mission.label}</strong>
          <p>{mission.detail}</p>
        </div>
        <span>{verifiedCount}/3 server verified</span>
      </div>
      <div className="dialin-aba-stages" role="list" aria-label="A B A2 controlled-test checklist">
        {test.stages.map((stage) => {
          const verifiedRunId = workflow.stage_run_ids[stage.stage];
          const current = stage.stage === nextStage;
          const state = verifiedRunId ? "complete" : current ? "current" : "upcoming";
          const eligibleLaps = workflow.stage_eligible_lap_numbers?.[stage.stage] ?? [];
          return (
            <div
              className={`dialin-aba-stage${verifiedRunId ? " complete" : ""}${current ? " current" : ""}`}
              data-stage={stage.stage}
              data-state={state}
              role="listitem"
              aria-current={current ? "step" : undefined}
              key={stage.stage}
            >
              <div className="dialin-stage-mark" aria-hidden="true">
                {verifiedRunId ? <CheckCircle2 size={16} /> : <Circle size={16} />}
              </div>
              <strong>{workflowStageName(stage.stage)}</strong>
              <small>{verifiedRunId ? "Server verified" : current ? "Do this now" : "Locked until prior stage"}</small>
              <p>{stage.warmup_laps} warm-up + {stage.required_flying_laps} eligible flying laps</p>
              {stage.stage !== "B" || authority ? (
                <p><strong>Setup:</strong> {stage.stage === "B"
                  ? `Change only the authorized control: ${authority?.instruction}.`
                  : stage.setup_instruction}</p>
              ) : (
                <p data-authority="withheld"><strong>Setup:</strong> Exact Stage B instruction withheld pending current source-run intelligence.</p>
              )}
              {learning && <p><strong>Why:</strong> {stage.purpose}</p>}
              {learning && verifiedRunId && (
                <small title={verifiedRunId}>Run {verifiedRunId.slice(0, 8)}{eligibleLaps.length > 0 ? ` · L${eligibleLaps.join(", L")}` : ""}</small>
              )}
            </div>
          );
        })}
      </div>
      {learning && authority && (
        <div className="dialin-workflow-coaching" aria-label="Controlled-test coaching">
          <div><span>Hypothesis</span><p>{test.hypothesis}</p></div>
          <div><span>Expected mechanism</span><p>{test.expected_mechanism}</p></div>
          <div><span>Prove it with</span><p>{test.success_metrics.join(" · ")}</p></div>
          <div><span>Watch for</span><p>{test.countereffects.join(" · ")}</p></div>
        </div>
      )}
    </div>
  );
}

function MeasurementMissionPanel({
  mission,
  learning,
}: {
  mission: MeasurementMission;
  learning: boolean;
}) {
  return (
    <div className="dialin-mission dialin-measurement-mission" data-authority="measurement-only">
      <header>
        <div><span className="eyebrow">Measurement first · no setup change</span><strong>{mission.required_laps_or_passes} passes to recover the evidence</strong></div>
        <span className="dialin-mini-pill">{cleanLabel(mission.target_phase, "Run scope")}</span>
      </header>
      <p>{mission.purpose}</p>
      <ol className="dialin-mission-checklist" aria-label="Measurement mission checklist">
        {mission.procedure.map((step, index) => <li key={step}><span>{index + 1}</span><p>{step}</p></li>)}
      </ol>
      <div className="dialin-mission-guardrails">
        <div><span>Done when</span><p>{mission.acceptance_thresholds.join(" ")}</p></div>
        <div><span>Stop and reset</span><p>{mission.stop_rule}</p></div>
      </div>
      {learning && mission.blockers.length > 0 && <p className="section-note"><strong>Why setup stays locked:</strong> {mission.blockers.join(" ")}</p>}
      <small>Recording laps does not auto-complete this mission or authorize a setup change.</small>
    </div>
  );
}

export function DialInTab({
  overview,
  workflowScopeRunIds,
  workflowHandoffKey,
  workflowOpenIntentId,
  currentIntelligenceAuthority,
  intelligenceAuthorityStatus,
  intelligenceAuthorityRecovery,
}: DialInTabProps) {
  const { basket } = useCompareBasket();
  const { selection, setWorkspace } = useTelemetrySelection();
  const dialRequestSeqRef = useRef(0);
  const workflowRequestSeqRef = useRef(0);
  const certificateRequestSeqRef = useRef(0);
  const currentRunIdRef = useRef<string | null>(overview?.run_id ?? null);
  const currentWorkflowIdRef = useRef<string | null>(null);
  if (currentRunIdRef.current !== (overview?.run_id ?? null)) {
    currentRunIdRef.current = overview?.run_id ?? null;
    dialRequestSeqRef.current += 1;
    workflowRequestSeqRef.current += 1;
    certificateRequestSeqRef.current += 1;
  }
  const storageKey = overview ? `racerzlab:dial-in:${overview.run_id}` : "racerzlab:dial-in";
  const workflowHandoffStorageKey = workflowHandoffKey
    ? `racerzlab:controlled-workflow-handoff:${workflowHandoffKey}`
    : null;
  const [complaint, setComplaint] = useState("");
  const [selectedPhase, setSelectedPhase] = useState("");
  const [objective, setObjective] = useState<DialInObjective>("race-pace");
  const [priority, setPriority] = useState<DialInPriority>("overall-pace");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [receivedResponse, setResponse] = useState<DialInResponse | null>(null);
  const [responseRequestBinding, setResponseRequestBinding] = useState<DialInRequestBinding | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<ControlledWorkflow | null>(null);
  const [workflowCatalogReady, setWorkflowCatalogReady] = useState(false);
  const [workflowCatalogRetryToken, setWorkflowCatalogRetryToken] = useState(0);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [workflowIdentityError, setWorkflowIdentityError] = useState<string | null>(null);
  const [ambiguousActiveWorkflowCount, setAmbiguousActiveWorkflowCount] = useState(0);
  const [ambiguousActiveWorkflows, setAmbiguousActiveWorkflows] = useState<ControlledWorkflow[]>([]);
  const [abandonConfirmOpen, setAbandonConfirmOpen] = useState(false);
  const [certificateMarkdown, setCertificateMarkdown] = useState<string | null>(null);
  const [certificateBusy, setCertificateBusy] = useState(false);
  const [certificateError, setCertificateError] = useState<string | null>(null);
  const activeControlledTest = isActiveControlledTest(workflow);
  const activeWorkflow = workflow != null && workflow.status !== "scored" && workflow.status !== "cancelled";
  const workflowScopeConflict = ambiguousActiveWorkflowCount > 1;
  currentWorkflowIdRef.current = workflow?.workflow_id ?? null;
  const exactSourceRunIntelligenceAuthority = currentIntelligenceAuthorityMatchesWorkflow(
    currentIntelligenceAuthority,
    workflow,
  ) ? currentIntelligenceAuthority : null;

  const persistedDecisionContext = useMemo(() => readCompleteDecisionContext(workflow), [workflow]);
  const workflowRecordIntegrityReady = !activeWorkflow || (workflow != null && captureWorkflowPlanBinding(workflow) != null);
  const workflowAuthorityBlocked = workflowScopeConflict || workflowIdentityError != null || !workflowRecordIntegrityReady;

  useEffect(() => {
    try {
      setComplaint(window.sessionStorage.getItem(storageKey) ?? "");
    } catch {
      setComplaint("");
    }
    setSelectedPhase("");
    setObjective("race-pace");
    setPriority("overall-pace");
    setAdvancedOpen(false);
    setResponse(null);
    setResponseRequestBinding(null);
    setLoading(false);
    setError(null);
    setWorkflow((current) => {
      if (workflowOpenIntentId) {
        return current?.workflow_id === workflowOpenIntentId ? current : null;
      }
      if (!current || current.status === "scored" || current.status === "cancelled" || !overview) return null;
      const workflowRunIds = [current.source_run_id, ...Object.values(current.stage_run_ids)];
      const isExplicitSessionHandoff = workflowScopeRunIds.includes(overview.run_id)
        && workflowRunIds.some((runId) => runId != null && workflowScopeRunIds.includes(runId));
      return isExplicitSessionHandoff ? current : null;
    });
    setWorkflowBusy(false);
    setWorkflowCatalogReady(false);
    setWorkflowError(null);
    setWorkflowIdentityError(null);
    setAmbiguousActiveWorkflowCount(0);
    setAmbiguousActiveWorkflows([]);
    setAbandonConfirmOpen(false);
    setCertificateMarkdown(null);
    setCertificateBusy(false);
    setCertificateError(null);
  }, [overview, storageKey, workflowOpenIntentId, workflowScopeRunIds]);

  useEffect(() => {
    certificateRequestSeqRef.current += 1;
    setCertificateMarkdown(null);
    setCertificateError(null);
    setAbandonConfirmOpen(false);
  }, [workflow?.workflow_id]);

  useEffect(() => {
    if (!workflowHandoffStorageKey || !workflow) return;
    try {
      if (workflow.status === "scored" || workflow.status === "cancelled") {
        if (window.sessionStorage.getItem(workflowHandoffStorageKey) === workflow.workflow_id) {
          window.sessionStorage.removeItem(workflowHandoffStorageKey);
        }
      } else {
        window.sessionStorage.setItem(workflowHandoffStorageKey, workflow.workflow_id);
      }
    } catch {
      // The handoff is a scoped navigation aid; server verification remains authoritative.
    }
  }, [workflow, workflowHandoffStorageKey]);

  useEffect(() => {
    const context = persistedDecisionContext;
    if (!context) return;
    if (workflow?.complaint) setComplaint(workflow.complaint);
    if (typeof context.selected_phase === "string") setSelectedPhase(context.selected_phase);
    if (OBJECTIVE_OPTIONS.some(([value]) => value === context.objective)) {
      setObjective(context.objective as DialInObjective);
    }
    if (PRIORITY_OPTIONS.some(([value]) => value === context.priority)) {
      setPriority(context.priority as DialInPriority);
    }
  }, [persistedDecisionContext, workflow?.complaint, workflow?.workflow_id]);

  useEffect(() => {
    let cancelled = false;
    if (!overview) return undefined;
    const requestSeq = ++workflowRequestSeqRef.current;
    setWorkflowCatalogReady(false);
    setWorkflowError(null);
    void fetchControlledWorkflows(false).then((items) => {
      if (cancelled || requestSeq !== workflowRequestSeqRef.current) return;
      setWorkflowCatalogReady(true);
      const isActive = (item: ControlledWorkflow) =>
        item.status !== "scored" && item.status !== "cancelled";
      const touchesRun = (item: ControlledWorkflow, runIds: ReadonlySet<string>) =>
        runIds.has(item.source_run_id)
        || Object.values(item.stage_run_ids).some((runId) => runId != null && runIds.has(runId));
      const currentRun = new Set([overview.run_id]);
      const explicitScope = new Set(workflowScopeRunIds);
      const activeAuthorityScope = explicitScope.has(overview.run_id) ? explicitScope : currentRun;
      const scopedActiveWorkflows = items.filter((item) => isActive(item) && touchesRun(item, activeAuthorityScope));
      const workflowScopeIsAmbiguous = scopedActiveWorkflows.length > 1;
      setAmbiguousActiveWorkflowCount(scopedActiveWorkflows.length);
      setAmbiguousActiveWorkflows(workflowScopeIsAmbiguous ? scopedActiveWorkflows : []);
      if (workflowOpenIntentId) {
        const explicitlyRequested = explicitScope.has(overview.run_id)
          ? items.find((item) => (
            item.workflow_id === workflowOpenIntentId
            && item.status !== "cancelled"
            && isActive(item)
            && item.packet.decision === "test"
            && touchesRun(item, explicitScope)
          ))
          : undefined;
        if (workflowScopeIsAmbiguous) {
          setWorkflow(explicitlyRequested ?? null);
          const integrityError = activeWorkflowIntegrityError(explicitlyRequested ?? null);
          if (integrityError) {
            setWorkflowIdentityError(integrityError);
            setResponse(null);
            setResponseRequestBinding(null);
          }
          setWorkflowError(explicitlyRequested
            ? MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER
            : `The selected controlled test is no longer available in this session. ${MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER}`);
          return;
        }
        setWorkflowCatalogReady(Boolean(explicitlyRequested));
        setWorkflow(explicitlyRequested ?? null);
        const integrityError = activeWorkflowIntegrityError(explicitlyRequested ?? null);
        if (integrityError) {
          setWorkflowIdentityError(integrityError);
          setResponse(null);
          setResponseRequestBinding(null);
        }
        setWorkflowError(integrityError ?? (explicitlyRequested ? null : "The selected controlled test is no longer available in this session."));
        return;
      }
      if (workflowScopeIsAmbiguous) {
        setWorkflow(null);
        setWorkflowError(MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER);
        return;
      }
      const related = items.filter((item) => touchesRun(item, currentRun));
      const directlyRelatedActiveTest = related.find((item) => isActive(item) && item.packet.decision === "test");
      const activeRelated = related.find(isActive);
      let handedOff: ControlledWorkflow | undefined;
      if (!directlyRelatedActiveTest && workflowHandoffStorageKey && explicitScope.has(overview.run_id)) {
        try {
          const workflowId = window.sessionStorage.getItem(workflowHandoffStorageKey);
          handedOff = items.find((item) =>
            item.workflow_id === workflowId
            && isActive(item)
            && item.packet.decision === "test"
            && touchesRun(item, explicitScope));
        } catch {
          handedOff = undefined;
        }
      }
      const activeTestInScope = explicitScope.has(overview.run_id)
        ? items.find((item) => isActive(item)
          && item.packet.decision === "test"
          && touchesRun(item, explicitScope))
        : undefined;
      const uniqueActiveWorkflowInScope = explicitScope.has(overview.run_id)
        ? scopedActiveWorkflows[0]
        : undefined;
      const nextWorkflow = directlyRelatedActiveTest
        ?? handedOff
        ?? activeTestInScope
        ?? uniqueActiveWorkflowInScope
        ?? activeRelated
        ?? related[0];
      setWorkflow(nextWorkflow ?? null);
      const integrityError = activeWorkflowIntegrityError(nextWorkflow ?? null);
      if (integrityError) {
        setWorkflowIdentityError(integrityError);
        setWorkflowError(integrityError);
        setResponse(null);
        setResponseRequestBinding(null);
      }
    }).catch(() => {
      if (cancelled || requestSeq !== workflowRequestSeqRef.current) return;
      setWorkflow(null);
      setWorkflowCatalogReady(false);
      setAmbiguousActiveWorkflowCount(0);
      setAmbiguousActiveWorkflows([]);
      setWorkflowError("Controlled-test progress could not be loaded. Retry workflow status before continuing.");
    });
    return () => { cancelled = true; };
  }, [overview, workflowCatalogRetryToken, workflowHandoffStorageKey, workflowOpenIntentId, workflowScopeRunIds]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(storageKey, complaint);
    } catch {
      // Session storage is a convenience only.
    }
  }, [complaint, storageKey]);

  const selectionIsForCurrentRun = selection.selectedRunId === overview?.run_id;
  const setupAvailable = overview != null && setupSnapshotMatchesRun(overview.setup_snapshot, overview.run_id);
  const selectedScopeIsWindow = selectionIsForCurrentRun && selection.selectedLapScope === "lap_window";
  const selectedRepresentativeLap = selectedScopeIsWindow
    ? selection.selectedRepresentativeLap ?? selection.selectedLap
    : selection.selectedLap;
  const selectedWindowHasBounds = selectedScopeIsWindow
    && selection.selectedLapWindowStart != null
    && selection.selectedLapWindowEnd != null;
  const selectedWindowIsComplete = selectedWindowHasBounds
    && selectedRepresentativeLap != null
    && selection.selectedLapWindowStart! <= selectedRepresentativeLap
    && selectedRepresentativeLap <= selection.selectedLapWindowEnd!;
  const requestedLapScope: WorkflowLapScope = !selectionIsForCurrentRun
    ? "run"
    : selectedScopeIsWindow
      ? "lap_window"
      : selection.selectedLapScope === "track_zone"
        ? "track_zone"
        : selection.selectedLapScope === "run"
          ? "run"
          : selection.selectedLapScope === "single_lap"
            ? "single_lap"
            : selection.selectedLap != null
              ? "single_lap"
              : "run";
  const selectedLapForRequest = requestedLapScope === "run"
    ? undefined
    : selectedRepresentativeLap ?? undefined;
  const selectionScopeIsComplete = requestedLapScope === "lap_window"
    ? selectedWindowIsComplete
    : requestedLapScope === "single_lap"
      ? selectedLapForRequest != null
      : true;
  const workflowLapContext = useMemo(() => ({
    lap_scope: requestedLapScope,
    window_start_lap: requestedLapScope === "lap_window" ? selection.selectedLapWindowStart ?? null : null,
    window_end_lap: requestedLapScope === "lap_window" ? selection.selectedLapWindowEnd ?? null : null,
    representative_lap: requestedLapScope === "lap_window" ? selectedRepresentativeLap ?? null : null,
  }), [
    requestedLapScope,
    selectedRepresentativeLap,
    selection.selectedLapWindowEnd,
    selection.selectedLapWindowStart,
  ]);
  const selectedScopeLabel = selectedWindowIsComplete
    ? `Window L${selection.selectedLapWindowStart}–L${selection.selectedLapWindowEnd}${selectedRepresentativeLap != null ? ` · Rep L${selectedRepresentativeLap}` : ""}`
    : selectedScopeIsWindow
      ? "Window selection incomplete"
      : selectionIsForCurrentRun && selection.selectedLap != null
        ? `Lap ${selection.selectedLap}`
        : selectionIsForCurrentRun && selection.selectedLapScope === "single_lap"
          ? "Lap selection incomplete"
        : "Run scope";

  const decisionContext = useMemo<DialInDecisionContext>(() => {
    const zoneIsForRun = selection.selectedRunId === overview?.run_id
      && selection.selectedZoneStartPct != null
      && selection.selectedZoneEndPct != null;
    return {
      selected_zone_start_pct: zoneIsForRun ? selection.selectedZoneStartPct : undefined,
      selected_zone_end_pct: zoneIsForRun ? selection.selectedZoneEndPct : undefined,
      selected_zone_label: zoneIsForRun ? selection.selectedZoneLabel : undefined,
      selected_phase: selectedPhase || undefined,
      objective,
      priority,
    };
  }, [
    objective,
    overview?.run_id,
    priority,
    selectedPhase,
    selection.selectedRunId,
    selection.selectedZoneEndPct,
    selection.selectedZoneLabel,
    selection.selectedZoneStartPct,
  ]);

  const currentRequestBinding = useMemo<DialInRequestBinding | null>(() => {
    if (!overview || !selectionScopeIsComplete) return null;
    return {
    run_id: overview.run_id,
    normalized_complaint: normalizeComplaint(complaint) ?? "",
    decision_context: {
      selected_lap: selectedLapForRequest ?? null,
      ...workflowLapContext,
      selected_zone_start_pct: decisionContext.selected_zone_start_pct ?? null,
      selected_zone_end_pct: decisionContext.selected_zone_end_pct ?? null,
      selected_zone_label: decisionContext.selected_zone_label ?? null,
      selected_phase: decisionContext.selected_phase ?? null,
      objective: decisionContext.objective ?? "race-pace",
      priority: decisionContext.priority ?? "overall-pace",
    },
    selection_context: {
      lap_scope: requestedLapScope,
      selected_lap: selectionIsForCurrentRun && !selectedScopeIsWindow ? selection.selectedLap ?? null : null,
      window_start_lap: selectedScopeIsWindow ? selection.selectedLapWindowStart ?? null : null,
      window_end_lap: selectedScopeIsWindow ? selection.selectedLapWindowEnd ?? null : null,
      representative_lap: selectedScopeIsWindow ? selectedRepresentativeLap ?? null : null,
    },
  };
  }, [
    complaint,
    decisionContext,
    overview,
    requestedLapScope,
    selectedLapForRequest,
    selectedRepresentativeLap,
    selectedScopeIsWindow,
    selectedWindowIsComplete,
    selection.selectedLap,
    selection.selectedLapScope,
    selection.selectedLapWindowEnd,
    selection.selectedLapWindowStart,
    selectionIsForCurrentRun,
    selectionScopeIsComplete,
    workflowLapContext,
  ]);
  const currentRequestBindingRef = useRef<DialInRequestBinding | null>(currentRequestBinding);
  currentRequestBindingRef.current = currentRequestBinding;
  const response = receivedResponse != null
    && requestBindingsMatch(responseRequestBinding, currentRequestBinding)
    ? receivedResponse
    : null;

  const displayedDecisionContext = useMemo<DialInDecisionContext>(() => {
    if (workflow && persistedDecisionContext) {
      return {
        selected_zone_start_pct: persistedDecisionContext.selected_zone_start_pct,
        selected_zone_end_pct: persistedDecisionContext.selected_zone_end_pct,
        selected_zone_label: persistedDecisionContext.selected_zone_label,
        selected_phase: persistedDecisionContext.selected_phase,
        objective: persistedDecisionContext.objective,
        priority: persistedDecisionContext.priority,
      };
    }
    return decisionContext;
  }, [decisionContext, persistedDecisionContext, workflow]);

  const workflowContextMatches = useMemo(() => {
    if (!workflow) return true;
    if (!persistedDecisionContext) return false;
    const selectionTargetsWorkflowSource = selection.selectedRunId === workflow.source_run_id;
    const closeEnough = (current: number | null | undefined, persisted: number | null | undefined) =>
      current == null ? true : persisted != null && Math.abs(current - persisted) <= 0.05;
    const explicitZoneMatches = !selectionTargetsWorkflowSource || (closeEnough(
      decisionContext.selected_zone_start_pct,
      persistedDecisionContext.selected_zone_start_pct,
    ) && closeEnough(
      decisionContext.selected_zone_end_pct,
      persistedDecisionContext.selected_zone_end_pct,
    ));
    const hasExplicitLapSelection = selectionTargetsWorkflowSource && (
      selection.selectedLap != null
      || selection.selectedLapScope === "lap_window"
      || selection.selectedLapScope === "track_zone"
    );
    const explicitLapMatches = !hasExplicitLapSelection || (
      persistedDecisionContext.lap_scope === requestedLapScope
      && persistedDecisionContext.selected_lap === (selectedLapForRequest ?? null)
      && persistedDecisionContext.window_start_lap === workflowLapContext.window_start_lap
      && persistedDecisionContext.window_end_lap === workflowLapContext.window_end_lap
      && persistedDecisionContext.representative_lap === workflowLapContext.representative_lap
    );
    const normalizedComplaint = normalizeComplaint(complaint);
    const persistedComplaint = normalizeComplaint(workflow.complaint);
    return explicitZoneMatches
      && explicitLapMatches
      && normalizedComplaint != null
      && normalizedComplaint === persistedComplaint
      && (selectedPhase || null) === persistedDecisionContext.selected_phase
      && objective === persistedDecisionContext.objective
      && priority === persistedDecisionContext.priority;
  }, [
    decisionContext.selected_zone_end_pct,
    decisionContext.selected_zone_start_pct,
    complaint,
    objective,
    persistedDecisionContext,
    priority,
    requestedLapScope,
    selectedLapForRequest,
    selectedPhase,
    selection.selectedLap,
    selection.selectedLapScope,
    selection.selectedRepresentativeLap,
    selection.selectedRunId,
    workflow,
    workflowLapContext,
  ]);
  const controlledTestAuthorityReady = activeControlledTest
    && workflowCatalogReady
    && !workflowAuthorityBlocked
    && workflowContextMatches
    && workflow.status === "a_recorded"
    && exactSourceRunIntelligenceAuthority != null;

  const submitDialIn = useCallback(async () => {
    if (!overview || !workflowCatalogReady || activeWorkflow || workflowAuthorityBlocked) return;
    const trimmed = complaint.trim();
    const requestedBinding = currentRequestBinding;
    if (!trimmed || !requestedBinding?.normalized_complaint || loading) return;
    const baselineRunId = basket.baseline?.run_id ?? null;
    const usableBaseline = basket.baseline
      && !basket.baseline.stale
      && baselineRunId
      && baselineRunId !== overview.run_id
      ? baselineRunId
      : undefined;
    const requestedRunId = overview.run_id;
    const requestSeq = ++dialRequestSeqRef.current;
    const workflowRequestSeq = ++workflowRequestSeqRef.current;
    setLoading(true);
    setError(null);
    setWorkflowError(null);
    setResponse(null);
    setResponseRequestBinding(null);
    try {
      const [dialResult, workflowResult] = await Promise.allSettled([
        analyzeRunDialIn(overview.run_id, {
          complaint: trimmed,
          selected_lap: selectedLapForRequest,
          ...decisionContext,
          baseline_run_id: usableBaseline,
          limit: DIAL_IN_REQUEST_LIMIT,
          include_debug_evidence: false,
        }),
        startControlledWorkflow({
          run_id: overview.run_id,
          complaint: trimmed,
          selected_lap: selectedLapForRequest,
          ...workflowLapContext,
          ...decisionContext,
        }),
      ]);
      if (
        requestSeq !== dialRequestSeqRef.current
        || workflowRequestSeq !== workflowRequestSeqRef.current
        || currentRunIdRef.current !== requestedRunId
      ) return;
      if (workflowResult.status === "rejected") throw workflowResult.reason;
      const nextWorkflow = workflowResult.value;
      if (!requestBindingsMatch(currentRequestBindingRef.current, requestedBinding)) {
        const message = "The Dial-In request context changed before the response returned. Nothing was updated, and setup authority is withheld. Reopen Dial-In before continuing.";
        setWorkflowIdentityError(message);
        throw new Error(message);
      }
      if (
        !nextWorkflow.workflow_id
        || nextWorkflow.workflow_id !== nextWorkflow.workflow_id.trim()
        || nextWorkflow.source_run_id !== requestedRunId
        || !workflowMatchesRequest(nextWorkflow, requestedBinding)
      ) {
        const message = "The controlled-test response did not match the requested run, complaint, or complete decision context. Nothing was updated, and exact targets are hidden. Reopen Dial-In before continuing.";
        setWorkflowIdentityError(message);
        throw new Error(message);
      }
      if (dialResult.status === "fulfilled" && (
        dialResult.value.run_id !== requestedRunId
        || normalizeComplaint(dialResult.value.complaint_raw) !== requestedBinding.normalized_complaint
      )) {
        const message = "The symptom response did not match the requested run and complaint. Nothing was updated, and exact targets are hidden. Reopen Dial-In before continuing.";
        setWorkflowIdentityError(message);
        throw new Error(message);
      }
      setWorkflow(nextWorkflow);
      setWorkflowError(null);
      setResponse(dialResult.status === "fulfilled" ? dialResult.value : null);
      setResponseRequestBinding(dialResult.status === "fulfilled" ? requestedBinding : null);
    } catch (caught) {
      if (requestSeq !== dialRequestSeqRef.current || currentRunIdRef.current !== requestedRunId) return;
      setResponse(null);
      setResponseRequestBinding(null);
      const message = caught instanceof Error ? caught.message : "Dial-in request failed.";
      setWorkflowError(message);
      setError(message);
    } finally {
      if (requestSeq === dialRequestSeqRef.current && currentRunIdRef.current === requestedRunId) {
        setLoading(false);
      }
    }
  }, [activeWorkflow, basket.baseline, complaint, currentRequestBinding, decisionContext, loading, overview, selectedLapForRequest, workflowAuthorityBlocked, workflowCatalogReady, workflowLapContext]);

  const clearDialIn = useCallback(() => {
    if (workflowBusy || !workflowCatalogReady) return;
    dialRequestSeqRef.current += 1;
    workflowRequestSeqRef.current += 1;
    certificateRequestSeqRef.current += 1;
    setComplaint(activeWorkflow ? workflow?.complaint ?? "" : "");
    setResponse(null);
    setResponseRequestBinding(null);
    setError(null);
    if (!activeWorkflow) setWorkflow(null);
    setWorkflowError(null);
    setAbandonConfirmOpen(false);
    setCertificateMarkdown(null);
    setCertificateError(null);
  }, [activeWorkflow, workflow, workflowBusy, workflowCatalogReady]);

  const buildVerifiedWorkflow = useCallback(async () => {
    if (!overview || !workflowCatalogReady || workflowBusy || activeWorkflow || workflowAuthorityBlocked) return;
    const requestedRunId = overview.run_id;
    const requestedBinding = currentRequestBinding;
    if (!requestedBinding?.normalized_complaint) return;
    const requestSeq = ++workflowRequestSeqRef.current;
    setWorkflowBusy(true);
    setWorkflowError(null);
    try {
      const nextWorkflow = await startControlledWorkflow({
        run_id: overview.run_id,
        complaint: complaint.trim(),
        selected_lap: selectedLapForRequest,
        ...workflowLapContext,
        ...decisionContext,
      });
      if (requestSeq !== workflowRequestSeqRef.current || currentRunIdRef.current !== requestedRunId) return;
      if (
        !requestBindingsMatch(currentRequestBindingRef.current, requestedBinding)
        || !nextWorkflow.workflow_id
        || nextWorkflow.workflow_id !== nextWorkflow.workflow_id.trim()
        || nextWorkflow.source_run_id !== requestedRunId
        || !workflowMatchesRequest(nextWorkflow, requestedBinding)
      ) {
        const message = "The verified-plan response did not match the requested run, complaint, or complete decision context. Nothing was updated, and exact targets are hidden. Reopen Dial-In before continuing.";
        setWorkflowIdentityError(message);
        setResponse(null);
        setResponseRequestBinding(null);
        throw new Error(message);
      }
      setWorkflow(nextWorkflow);
    } catch (caught) {
      if (requestSeq !== workflowRequestSeqRef.current || currentRunIdRef.current !== requestedRunId) return;
      setWorkflowError(caught instanceof Error ? caught.message : "Verified test planning failed.");
    } finally {
      if (requestSeq === workflowRequestSeqRef.current && currentRunIdRef.current === requestedRunId) {
        setWorkflowBusy(false);
      }
    }
  }, [activeWorkflow, complaint, currentRequestBinding, decisionContext, overview, selectedLapForRequest, workflowAuthorityBlocked, workflowBusy, workflowCatalogReady, workflowLapContext]);

  const nextWorkflowStage = activeControlledTest
    ? (["A", "B", "A2"] as const).find((stage) => !workflow.stage_run_ids[stage])
    : undefined;
  const stageBSetupAuthorityWithheld = nextWorkflowStage === "B"
    && exactSourceRunIntelligenceAuthority == null;
  const currentStageRecordingAllowed = nextWorkflowStage !== "B"
    || exactSourceRunIntelligenceAuthority != null;

  const abandonActiveTest = useCallback(async () => {
    if (!activeWorkflow || !workflow || workflowBusy) return;
    const requestedRunId = overview?.run_id ?? null;
    const workflowId = workflow.workflow_id;
    const expectedSourceRunId = workflow.source_run_id;
    const requestSeq = ++workflowRequestSeqRef.current;
    setWorkflowBusy(true);
    setWorkflowError(null);
    setAbandonConfirmOpen(false);
    try {
      const cancelledWorkflow = await cancelControlledWorkflow(workflowId);
      if (
        requestSeq !== workflowRequestSeqRef.current
        || currentRunIdRef.current !== requestedRunId
        || currentWorkflowIdRef.current !== workflowId
      ) return;
      if (
        cancelledWorkflow.workflow_id !== workflowId
        || cancelledWorkflow.source_run_id !== expectedSourceRunId
        || cancelledWorkflow.status !== "cancelled"
      ) {
        setWorkflowIdentityError("The abandon response did not match this workflow and source run. Its active state was left unchanged. Reopen Dial-In before continuing.");
        setWorkflowError("The abandon response did not match this workflow. Its active state was left unchanged.");
        setResponse(null);
        setResponseRequestBinding(null);
        return;
      }
      const remainingActiveWorkflows = ambiguousActiveWorkflows.filter((item) => item.workflow_id !== workflowId);
      setAmbiguousActiveWorkflows(remainingActiveWorkflows.length > 1 ? remainingActiveWorkflows : []);
      setAmbiguousActiveWorkflowCount(remainingActiveWorkflows.length);
      if (remainingActiveWorkflows.length === 1) {
        const remainingWorkflow = remainingActiveWorkflows[0];
        const integrityError = activeWorkflowIntegrityError(remainingWorkflow);
        setWorkflow(remainingWorkflow);
        setWorkflowIdentityError(integrityError);
        setWorkflowError(integrityError);
      } else if (remainingActiveWorkflows.length > 1) {
        setWorkflow(null);
        setWorkflowIdentityError(null);
        setWorkflowError(MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER);
      } else {
        setWorkflow(cancelledWorkflow);
        setWorkflowIdentityError(null);
        setWorkflowError(null);
      }
      setResponse(null);
      setResponseRequestBinding(null);
    } catch (caught) {
      if (requestSeq !== workflowRequestSeqRef.current || currentRunIdRef.current !== requestedRunId) return;
      setWorkflowError(caught instanceof Error ? caught.message : "The workflow could not be abandoned.");
    } finally {
      if (requestSeq === workflowRequestSeqRef.current && currentRunIdRef.current === requestedRunId) {
        setWorkflowBusy(false);
      }
    }
  }, [activeWorkflow, ambiguousActiveWorkflows, overview?.run_id, workflow, workflowBusy]);

  const recordCurrentRun = useCallback(async () => {
    if (
      !overview
      || !workflow
      || !nextWorkflowStage
      || workflowBusy
      || !workflowContextMatches
      || workflowAuthorityBlocked
      || (nextWorkflowStage === "B" && exactSourceRunIntelligenceAuthority == null)
    ) return;
    const requestedRunId = overview.run_id;
    const workflowId = workflow.workflow_id;
    const expectedSourceRunId = workflow.source_run_id;
    const requestedStage = nextWorkflowStage;
    const requestedPlanBinding = captureWorkflowPlanBinding(workflow);
    const previousStageRunIds = { ...workflow.stage_run_ids };
    const expectedStatus = { A: "a_recorded", B: "b_recorded", A2: "a2_recorded" }[requestedStage];
    if (!requestedPlanBinding) {
      const message = "The active workflow is missing its immutable complaint, decision context, target, or protocol identity. No stage was recorded.";
      setWorkflowIdentityError(message);
      setWorkflowError(message);
      setResponse(null);
      setResponseRequestBinding(null);
      return;
    }
    const requestSeq = ++workflowRequestSeqRef.current;
    setWorkflowBusy(true);
    setWorkflowError(null);
    try {
      const nextWorkflow = await attachControlledWorkflowStage(workflowId, requestedStage, requestedRunId);
      if (
        requestSeq !== workflowRequestSeqRef.current
        || currentRunIdRef.current !== requestedRunId
        || currentWorkflowIdRef.current !== workflowId
      ) return;
      if (
        nextWorkflow.workflow_id !== workflowId
        || nextWorkflow.source_run_id !== expectedSourceRunId
        || nextWorkflow.stage_run_ids[requestedStage] !== requestedRunId
        || nextWorkflow.status !== expectedStatus
        || !workflowPreservesPlan(requestedPlanBinding, nextWorkflow)
        || !stageBindingsMatch(previousStageRunIds, nextWorkflow.stage_run_ids, requestedStage, requestedRunId)
      ) {
        const message = "The stage-verification response changed the workflow complaint, decision context, target, protocol, prior stage bindings, or expected transition. Nothing was updated, and exact targets are hidden. Reopen Dial-In before continuing.";
        setWorkflowIdentityError(message);
        setResponse(null);
        setResponseRequestBinding(null);
        throw new Error(message);
      }
      setWorkflow(nextWorkflow);
    } catch (caught) {
      if (requestSeq !== workflowRequestSeqRef.current || currentRunIdRef.current !== requestedRunId) return;
      setWorkflowError(caught instanceof Error ? caught.message : "The current run did not pass stage verification.");
    } finally {
      if (requestSeq === workflowRequestSeqRef.current && currentRunIdRef.current === requestedRunId) {
        setWorkflowBusy(false);
      }
    }
  }, [exactSourceRunIntelligenceAuthority, nextWorkflowStage, overview, workflow, workflowAuthorityBlocked, workflowBusy, workflowContextMatches]);

  const scoreVerifiedWorkflow = useCallback(async () => {
    if (!workflow || workflow.status !== "a2_recorded" || workflowBusy || !workflowContextMatches || workflowAuthorityBlocked) return;
    const requestedRunId = overview?.run_id ?? null;
    const workflowId = workflow.workflow_id;
    const expectedSourceRunId = workflow.source_run_id;
    const requestedPlanBinding = captureWorkflowPlanBinding(workflow);
    const previousStageRunIds = { ...workflow.stage_run_ids };
    if (!requestedPlanBinding) {
      const message = "The active workflow is missing its immutable complaint, decision context, target, or protocol identity. It was not scored.";
      setWorkflowIdentityError(message);
      setWorkflowError(message);
      setResponse(null);
      setResponseRequestBinding(null);
      return;
    }
    const requestSeq = ++workflowRequestSeqRef.current;
    setWorkflowBusy(true);
    setWorkflowError(null);
    try {
      const nextWorkflow = await scoreControlledWorkflow(workflowId);
      if (
        requestSeq !== workflowRequestSeqRef.current
        || currentRunIdRef.current !== requestedRunId
        || currentWorkflowIdRef.current !== workflowId
      ) return;
      if (
        nextWorkflow.workflow_id !== workflowId
        || nextWorkflow.source_run_id !== expectedSourceRunId
        || nextWorkflow.status !== "scored"
        || !workflowPreservesPlan(requestedPlanBinding, nextWorkflow)
        || !stageBindingsMatch(previousStageRunIds, nextWorkflow.stage_run_ids)
      ) {
        const message = "The scoring response changed the workflow complaint, decision context, target, protocol, or A/B/A2 stage bindings. Nothing was updated, and exact targets are hidden. Reopen Dial-In before continuing.";
        setWorkflowIdentityError(message);
        setResponse(null);
        setResponseRequestBinding(null);
        throw new Error(message);
      }
      setWorkflow(nextWorkflow);
    } catch (caught) {
      if (requestSeq !== workflowRequestSeqRef.current || currentRunIdRef.current !== requestedRunId) return;
      setWorkflowError(caught instanceof Error ? caught.message : "Controlled test scoring failed.");
    } finally {
      if (requestSeq === workflowRequestSeqRef.current && currentRunIdRef.current === requestedRunId) {
        setWorkflowBusy(false);
      }
    }
  }, [overview?.run_id, workflow, workflowAuthorityBlocked, workflowBusy, workflowContextMatches]);

  const chooseClarification = useCallback((option: string) => {
    const base = response?.complaint_raw.trim() || complaint.trim();
    const normalized = base.toLowerCase();
    const refinement = option === "Whole corner" ? "center" : option.toLowerCase();
    const nextComplaint = normalized.includes(refinement) ? base : `${base} ${refinement}`;
    setComplaint(nextComplaint.trim());
    setResponse(null);
    setResponseRequestBinding(null);
    setError(null);
  }, [complaint, response]);

  const chooseSymptomPreset = useCallback((preset: string) => {
    setComplaint(preset);
    setResponse(null);
    setResponseRequestBinding(null);
    setError(null);
  }, []);

  const openTestCertificate = useCallback(async () => {
    if (!workflow || certificateBusy) return;
    const requestedRunId = overview?.run_id ?? null;
    const workflowId = workflow.workflow_id;
    const requestSeq = ++certificateRequestSeqRef.current;
    setCertificateBusy(true);
    setCertificateError(null);
    setCertificateMarkdown(null);
    try {
      const certificate = await fetchControlledWorkflowReport(workflowId);
      if (
        requestSeq !== certificateRequestSeqRef.current
        || currentRunIdRef.current !== requestedRunId
        || currentWorkflowIdRef.current !== workflowId
      ) return;
      if (certificate.workflow_id !== workflowId) {
        throw new Error("The certificate response did not match this controlled workflow. No certificate was opened.");
      }
      setCertificateMarkdown(certificate.markdown);
    } catch (caught) {
      if (
        requestSeq !== certificateRequestSeqRef.current
        || currentRunIdRef.current !== requestedRunId
        || currentWorkflowIdRef.current !== workflowId
      ) return;
      setCertificateError(caught instanceof Error ? caught.message : "The test certificate could not be loaded.");
    } finally {
      if (
        requestSeq === certificateRequestSeqRef.current
        && currentRunIdRef.current === requestedRunId
        && currentWorkflowIdRef.current === workflowId
      ) {
        setCertificateBusy(false);
      }
    }
  }, [certificateBusy, overview?.run_id, workflow]);

  const copyTestCertificate = useCallback(async () => {
    if (!certificateMarkdown) return;
    try {
      await navigator.clipboard.writeText(certificateMarkdown);
      setCertificateError(null);
    } catch {
      setCertificateError("Clipboard access was denied. Download the Markdown certificate instead.");
    }
  }, [certificateMarkdown]);

  const downloadTestCertificate = useCallback(() => {
    if (!certificateMarkdown || !workflow) return;
    const url = URL.createObjectURL(new Blob([certificateMarkdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `racerzlab-test-certificate-${workflow.workflow_id}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [certificateMarkdown, workflow]);

  const hints = response ? dialInEvidenceHints(response) : [];
  const primarySwings = useMemo(() => response?.top_swings.slice(0, 1) ?? [], [response]);
  const secondarySwings = useMemo(
    () => response?.top_swings.slice(1, MAX_VISIBLE_UNVERIFIED_HYPOTHESES) ?? [],
    [response],
  );
  const decisionPresentation = workflowDecisionPresentation(workflow);
  const canSubmit = Boolean(overview)
    && workflowCatalogReady
    && currentRequestBinding != null
    && complaint.trim().length > 0
    && !loading
    && !activeWorkflow
    && !workflowAuthorityBlocked;
  const runLabel = overview
    ? `${overview.session.car_name ?? "Unknown car"}${overview.session.track_display_name || overview.session.track_name ? ` - ${overview.session.track_display_name ?? overview.session.track_name}` : ""}`
    : "No run selected";
  const workflowCurrentStage = workflow && overview
    ? WORKFLOW_STAGES.find((stage) => workflow.stage_run_ids[stage] === overview.run_id)
    : undefined;
  const workflowPlanCrossesCurrentRun = Boolean(
    workflow && overview && workflow.source_run_id !== overview.run_id,
  );
  const currentRunIsUnverifiedStageCandidate = Boolean(
    activeControlledTest && workflowPlanCrossesCurrentRun && !workflowCurrentStage,
  );
  const workflowPlanScopeLabel = workflow && persistedDecisionContext
    ? `${workflow.source_run_id === overview?.run_id ? "Current run" : `Source run ${workflow.source_run_id.slice(0, 8)}`} · ${formatDecisionLapScope(persistedDecisionContext)}`
    : selectedScopeLabel;
  const broadcastDecisionContext = workflow && persistedDecisionContext
    ? persistedDecisionContext
    : currentRequestBinding?.decision_context ?? null;
  const broadcastRunId = workflow && persistedDecisionContext ? workflow.source_run_id : overview?.run_id;
  const broadcastLapScope = broadcastDecisionContext?.lap_scope ?? requestedLapScope;
  const dialAuthorityLabel = ((workflowValue: ControlledWorkflow | null) => workflowScopeConflict
    ? "Withheld · workflow conflict"
    : workflowIdentityError
      ? "Withheld · identity mismatch"
      : stageBSetupAuthorityWithheld
        ? intelligenceAuthorityStatus === "checking"
          ? "Checking source-run card"
          : "Withheld · review Stage B"
      : controlledTestAuthorityReady
        ? currentRunIsUnverifiedStageCandidate
          ? "Source-run card · candidate pending"
          : "Source-run card authorized"
        : activeControlledTest && nextWorkflowStage === "A"
          ? "Baseline only · no setup authority"
        : activeControlledTest && nextWorkflowStage === "A2"
          ? "Restore only · no setup authority"
        : activeWorkflow && workflowValue?.packet.decision === "measure"
          ? "Measurement active"
        : workflowValue?.status === "scored" && workflowValue.packet.decision === "test"
          ? "Verified history"
          : "Advisory only")(workflow);
  const dialBroadcast = ((workflowValue: ControlledWorkflow | null) => workflowScopeConflict
    ? {
        state: "blocked",
        headline: `${ambiguousActiveWorkflowCount} active workflows · authority withheld`,
        detail: MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER,
      }
    : workflowIdentityError
      ? {
          state: "blocked",
          headline: "Response identity mismatch · authority withheld",
          detail: workflowIdentityError,
        }
      : !workflowCatalogReady
    ? {
        state: workflowError ? "blocked" : "loading",
        headline: workflowError ? "Controlled-test status is unavailable" : "Checking the controlled-test slot",
        detail: workflowError ?? "Dial-In will not create a second plan until the server-owned workflow catalog is known.",
      }
    : workflowError && !workflowValue
      ? {
          state: "blocked",
          headline: "Controlled workflow was not updated",
          detail: workflowError,
        }
    : !activeWorkflow && !currentRequestBinding
      ? {
          state: "guarded",
          headline: "Evidence scope is incomplete · setup action withheld",
          detail: requestedLapScope === "lap_window"
            ? "Choose a valid window start, end, and representative lap before checking or building a plan."
            : "Choose a valid lap before checking or building a lap-scoped plan.",
        }
    : stageBSetupAuthorityWithheld
      ? {
          state: intelligenceAuthorityStatus === "checking" ? "loading" : "blocked",
          headline: intelligenceAuthorityStatus === "checking"
            ? "Rechecking the source-run Stage B card"
            : "Stage B authority withheld · recovery required",
          detail: intelligenceAuthorityStatus === "checking"
            ? "The exact target and Stage B instruction stay hidden until the current source-run report and workflow revision agree."
            : intelligenceAuthorityRecovery,
        }
    : activeControlledTest && currentRunIsUnverifiedStageCandidate
      ? {
          state: "attention",
          headline: `Controlled test active · current run awaits ${nextWorkflowStage ?? "verification"}`,
          detail: controlledTestAuthorityReady
            ? `The exact card authority remains bound to ${workflowPlanScopeLabel}. The open run is only a candidate for ${nextWorkflowStage ?? "the next stage"} until Verify current run succeeds.`
            : `Progress remains bound to ${workflowPlanScopeLabel}. The open run is only a non-authorizing candidate for ${nextWorkflowStage ?? "the next stage"} until server verification succeeds.`,
        }
    : activeControlledTest
      ? {
          state: "ready",
          headline: nextWorkflowStage ? `Controlled test active · next stage ${nextWorkflowStage}` : "Controlled test ready to score",
          detail: nextWorkflowStage
            ? nextWorkflowStage === "A"
              ? "Record the baseline without changing the setup. Exact Stage B authority is evaluated only after A is verified."
              : "Restore the recorded baseline and verify A2. This is non-authorizing protocol progress, not a new setup direction."
            : "All required stages are recorded. Score the verified workflow before starting another test.",
        }
      : workflowValue?.status === "cancelled"
        ? {
            state: "attention",
            headline: "Cancelled test retained as audit history",
            detail: "No result entered setup memory. The test slot is available for a new evidence check.",
          }
        : workflowValue?.packet.decision === "measure"
          ? {
              state: "attention",
              headline: "Measurement workflow active · no setup change approved",
              detail: `${workflowValue.packet.measurement_mission?.purpose ?? "Collect the requested evidence before considering a garage change."} Finish or explicitly abandon this workflow before starting another diagnosis.`,
            }
          : workflowValue?.packet.decision === "test"
            ? controlledTestAuthorityReady ? {
                state: "ready",
                headline: "One current source-run test card is authorized",
                detail: "The report action, workflow revision, exact values, and qualified citation set agree.",
              } : {
                state: "blocked",
                headline: "Stored test card is not current authority",
                detail: intelligenceAuthorityRecovery,
              }
            : response
              ? {
                  state: response.blocker_reasons.length > 0 ? "guarded" : "attention",
                  headline: response.blocker_reasons.length > 0 ? "Symptom read · setup action withheld" : "Symptom read ready for plan verification",
                  detail: response.blocker_reasons[0] ?? "Build the server-verified plan before treating any setup direction as authorized.",
                }
              : {
                  state: "idle",
                  headline: "Ready for one symptom check",
                  detail: "Describe what the car is doing. Dial-In will return one test, one measurement mission, or an explicit no-call.",
                })(workflow);

  if (!overview) {
    return (
      <section className="dialin-tab">
        <div className="dialin-panel dialin-hero">
          <div className="dialin-header">
            <div>
              <h2><ClipboardList size={16} /> Crew Chief Dial-In</h2>
              <p>Select or import a run before using Dial-In.</p>
            </div>
            <span className="dialin-readonly" title="RacerZLab advises only; it never changes the live car.">Advisory only</span>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="dialin-tab" aria-labelledby="dialin-title">
      <section
        className="tab-decision-broadcast"
        data-state={dialBroadcast.state}
        data-authority={controlledTestAuthorityReady ? "server-verified" : "withheld"}
        data-authority-kind={controlledTestAuthorityReady ? "source-run-card" : "none"}
        data-authority-source-run-id={exactSourceRunIntelligenceAuthority?.sourceRunId}
        data-authority-workflow-revision={exactSourceRunIntelligenceAuthority?.workflowUpdatedAt}
        data-run-id={broadcastRunId}
        data-current-run-id={overview.run_id}
        data-plan-run-id={workflow?.source_run_id}
        data-current-run-authority={currentRunIsUnverifiedStageCandidate ? "unverified-stage-candidate" : workflowCurrentStage ? `verified-stage-${workflowCurrentStage.toLowerCase()}` : "bound-to-plan"}
        data-lap-scope={broadcastLapScope}
        data-selected-lap={broadcastLapScope !== "lap_window" ? broadcastDecisionContext?.selected_lap ?? undefined : undefined}
        data-window-start={broadcastLapScope === "lap_window" ? broadcastDecisionContext?.window_start_lap ?? undefined : undefined}
        data-window-end={broadcastLapScope === "lap_window" ? broadcastDecisionContext?.window_end_lap ?? undefined : undefined}
        data-representative-lap={broadcastLapScope === "lap_window" ? broadcastDecisionContext?.representative_lap ?? undefined : undefined}
        aria-label="Dial-In status and workspace handoffs"
      >
        <div>
          <h3>{dialBroadcast.headline}</h3>
          <p>{dialBroadcast.detail}</p>
          <div className="tab-decision-facts" aria-label="Dial-In scope and authority">
            <span title={workflow?.source_run_id}>Scope <strong>{workflowPlanScopeLabel}</strong></span>
            {workflowPlanCrossesCurrentRun && (
              <span title={overview.run_id}>Current run <strong>{workflowCurrentStage ? `Verified stage ${workflowCurrentStage}` : `Candidate for ${nextWorkflowStage ?? "next stage"}`}</strong></span>
            )}
            <span>{workflowPlanCrossesCurrentRun ? "Current setup" : "Setup"} <strong>{setupAvailable ? "Recorded" : "Unavailable"}</strong></span>
            <span>Authority <strong>{dialAuthorityLabel}</strong></span>
            <span>Workflow slot <strong>{workflowAuthorityBlocked ? "Blocked" : activeWorkflow ? "Active" : workflowCatalogReady ? "Available" : "Checking"}</strong></span>
          </div>
        </div>
        <div className="tab-handoff-actions" aria-label="Dial-In workspace handoffs">
          {!workflowCatalogReady && workflowError && (
            <button type="button" onClick={() => setWorkflowCatalogRetryToken((token) => token + 1)}>
              Retry workflow status
            </button>
          )}
          <button type="button" onClick={() => setWorkspace("engineer", "manual")}>Open Engineer</button>
          <button type="button" onClick={() => setWorkspace("laps", "manual")}>Review Laps</button>
          {setupAvailable && (
            <button type="button" onClick={() => setWorkspace("setup_impact", "manual")}>Inspect Setup</button>
          )}
        </div>
      </section>
      {workflowScopeConflict && (
        <section className="dialin-panel dialin-workflow-recovery" aria-label="Resolve active workflow conflict">
          <span className="eyebrow">Recovery only · setup authority withheld</span>
          <h3>Choose one extra workflow to abandon</h3>
          <p className="section-note">Workflow IDs, source runs, and status are shown only so you can recover the one-workflow rule. Exact setup targets remain hidden until one active workflow remains.</p>
          <div className="dialin-chip-row" role="list" aria-label="Active workflows requiring recovery">
            {ambiguousActiveWorkflows.map((item) => (
              <button
                key={item.workflow_id}
                type="button"
                className={`secondary-button${workflow?.workflow_id === item.workflow_id ? " selected" : ""}`}
                aria-pressed={workflow?.workflow_id === item.workflow_id}
                title={`Workflow ${item.workflow_id}`}
                onClick={() => {
                  setWorkflow(item);
                  setResponse(null);
                  setResponseRequestBinding(null);
                  const integrityError = activeWorkflowIntegrityError(item);
                  setWorkflowIdentityError(integrityError);
                  setWorkflowError(integrityError ?? MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER);
                  setAbandonConfirmOpen(false);
                }}
              >
                {item.packet.decision === "test" ? "Controlled test" : "Measurement"} · {item.workflow_id.slice(0, 8)} · {item.status.replace(/_/g, " ")} · source {item.source_run_id.slice(0, 8)}
              </button>
            ))}
          </div>
          {activeWorkflow && workflow && (
            abandonConfirmOpen ? (
              <div className="dialin-abandon-confirm" role="group" aria-label="Confirm abandoning selected workflow">
                <span>Abandon workflow {workflow.workflow_id.slice(0, 8)} and retain its progress as cancelled audit history?</span>
                <button className="secondary-button" type="button" disabled={workflowBusy} onClick={() => setAbandonConfirmOpen(false)}>Keep workflow</button>
                <button className="secondary-button" type="button" disabled={workflowBusy} onClick={() => void abandonActiveTest()}>Confirm abandon</button>
              </div>
            ) : (
              <button className="secondary-button" type="button" disabled={workflowBusy} onClick={() => setAbandonConfirmOpen(true)}>
                Abandon selected workflow
              </button>
            )
          )}
        </section>
      )}
      <div className="dialin-panel dialin-hero">
        <div className="dialin-header">
          <div>
            <h2 id="dialin-title"><ClipboardList size={16} /> Crew Chief Dial-In</h2>
            <p>{runLabel}</p>
          </div>
          <span className="dialin-readonly" title="RacerZLab advises only; it never changes the live car.">Advisory only</span>
        </div>
        <p className="dialin-tab-subtitle">
          Tell RacerZLab what the car is doing. It will verify whether one specific setup test is justified.
        </p>
        {!setupAvailable && (
          <div className="dialin-alert limited" role="status">
            <AlertTriangle size={14} />
            <span>Setup snapshot unavailable. Garage-specific recommendations are limited until setup data is available, so Dial-In will stay conservative.</span>
          </div>
        )}

        <form
          className="dialin-input-row dialin-command-bar"
          onSubmit={(event) => {
            event.preventDefault();
            void submitDialIn();
          }}
        >
          <input
            className="dialin-input"
            value={complaint}
            onChange={(event) => setComplaint(event.target.value)}
            disabled={activeWorkflow}
            placeholder="Example: loose off, tight center, RF is angry, nose is dragging, won't stay on bottom"
            aria-label="Driver complaint"
            aria-describedby={activeWorkflow ? "active-workflow-rule" : undefined}
          />
          <button className="secondary-button" type="submit" disabled={!canSubmit} title="Check data and symptoms">
            <Search size={14} /> {workflowAuthorityBlocked ? "Resolve workflow blocker" : !workflowCatalogReady ? workflowError ? "Test status unavailable" : "Checking test status" : loading ? "Checking run data" : "Check Data & Symptoms"}
          </button>
          <button className="secondary-button" type="button" onClick={clearDialIn} disabled={workflowBusy || !workflowCatalogReady || (!complaint && !response && !error)} title={activeWorkflow ? "Clear this result; the active workflow stays open" : "Clear complaint"}>
            <X size={14} /> {activeWorkflow ? "Clear result" : "Clear"}
          </button>
        </form>

        <div className="dialin-preset-block" aria-label="Common driver symptoms">
          <span>Quick symptoms</span>
          <div className="dialin-chip-row">
            {SYMPTOM_PRESETS.map(([label, preset]) => (
              <button
                className={`dialin-chip dialin-chip-button${complaint.trim().toLowerCase() === preset ? " selected" : ""}`}
                key={label}
                type="button"
                onClick={() => chooseSymptomPreset(preset)}
                disabled={activeWorkflow}
                aria-pressed={complaint.trim().toLowerCase() === preset}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <details
          className="dialin-advanced-context"
          open={selection.selectedMode === "learning" || advancedOpen}
          onToggle={(event) => {
            if (selection.selectedMode !== "learning") setAdvancedOpen(event.currentTarget.open);
          }}
        >
          <summary>
            <span>Refine diagnosis</span>
            <strong>
              {cleanLabel(selectedPhase, "Auto phase")} · {OBJECTIVE_OPTIONS.find(([value]) => value === objective)?.[1]} · {PRIORITY_OPTIONS.find(([value]) => value === priority)?.[1]}
            </strong>
          </summary>
          <div className="dialin-summary-grid dialin-context-grid" aria-label="Dial-In decision context">
            <div>
              <label htmlFor="dialin-phase">Phase</label>
              <select
                id="dialin-phase"
                className="dialin-input"
                value={selectedPhase}
                onChange={(event) => setSelectedPhase(event.target.value)}
                disabled={activeWorkflow}
              >
                {PHASE_OPTIONS.map(([value, label]) => <option value={value} key={value || "auto"}>{label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="dialin-objective">Objective</label>
              <select
                id="dialin-objective"
                className="dialin-input"
                value={objective}
                onChange={(event) => setObjective(event.target.value as DialInObjective)}
                disabled={activeWorkflow}
              >
                {OBJECTIVE_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="dialin-priority">Priority</label>
              <select
                id="dialin-priority"
                className="dialin-input"
                value={priority}
                onChange={(event) => setPriority(event.target.value as DialInPriority)}
                disabled={activeWorkflow}
              >
                {PRIORITY_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
              </select>
            </div>
            <div>
              <span>Track area</span>
              <strong>
                {displayedDecisionContext.selected_zone_label
                  ?? (displayedDecisionContext.selected_zone_start_pct != null && displayedDecisionContext.selected_zone_end_pct != null
                    ? `${displayedDecisionContext.selected_zone_start_pct.toFixed(1)}-${displayedDecisionContext.selected_zone_end_pct.toFixed(1)}%`
                    : "Auto-detect")}
              </strong>
            </div>
          </div>
        </details>

        <div className="dialin-rule-note">
          <Crosshair size={13} />
          <span>Pick one change. Just one. Run clean laps and compare.</span>
        </div>
      </div>

      {activeWorkflow && !workflowScopeConflict && (
        <section className="dialin-alert limited dialin-active-test-guard" role="status" aria-live="polite">
          <div id="active-workflow-rule">
            <strong>{activeControlledTest ? "Controlled test in progress" : "Measurement workflow in progress"}</strong>
            <span>{activeControlledTest ? "Finish its remaining A/B/A2 stages before checking or building another plan." : "Collect the requested evidence before starting another diagnosis."} If you cannot finish it, abandon it explicitly; RacerZLab will retain the cancelled audit record.</span>
          </div>
          {abandonConfirmOpen ? (
            <div className="dialin-abandon-confirm" role="group" aria-label="Confirm abandoning controlled test">
              <span>Abandon this workflow and keep its recorded progress as cancelled audit history?</span>
              <button className="secondary-button" type="button" disabled={workflowBusy} onClick={() => setAbandonConfirmOpen(false)}>Keep workflow</button>
              <button className="secondary-button" type="button" disabled={workflowBusy} onClick={() => void abandonActiveTest()}>Confirm abandon</button>
            </div>
          ) : (
            <button
              className="secondary-button"
              type="button"
              disabled={workflowBusy}
              aria-expanded="false"
              onClick={() => setAbandonConfirmOpen(true)}
            >
              Abandon workflow
            </button>
          )}
        </section>
      )}

      {workflow?.status === "cancelled" && (
        <div className="dialin-alert limited" role="status">
          <AlertTriangle size={14} />
          <span>Test abandoned. Its stages and cancelled status remain in the audit record; no result was admitted as setup learning.</span>
        </div>
      )}

      {error && (
        <div className="dialin-alert" role="alert">
          <AlertTriangle size={14} />
          <span>
            I couldn't run Dial-In on this run. Try again or check that the run is loaded.
            {selection.selectedMode === "learning" ? ` Technical detail: ${error}` : ""}
          </span>
        </div>
      )}

      {workflowError && !workflow && !response && (
        <div className="dialin-alert limited" role="alert">
          <AlertTriangle size={14} />
          <span>{workflowError}</span>
        </div>
      )}

      {!response && !error && !workflow && !workflowError && (
        <div className="dialin-empty" role="status" aria-live="polite" aria-busy={loading}>
          {loading ? "Checking your complaint against the run data..." : "Tell me what the car is doing, and I'll check the data."}
        </div>
      )}

      {!response && workflow && (
        <section className="dialin-aba-card dialin-verified-workflow" aria-label="Resumed controlled test workflow">
          <header>
            <div>
              <span className="eyebrow">{decisionPresentation.label}</span>
              <h3>{workflowAuthorityBlocked ? "Controlled workflow requires recovery" : controlledWorkflowHeadline(workflow, exactSourceRunIntelligenceAuthority)}</h3>
            </div>
            <span className="dialin-mini-pill">{workflow.status.replace(/_/g, " ")}</span>
          </header>
          {selection.selectedMode === "learning" && !workflowAuthorityBlocked && !stageBSetupAuthorityWithheld && <p className="section-note">{decisionPresentation.explanation}</p>}
          {workflowAuthorityBlocked && (
            <div className="dialin-alert limited" role="alert">
              <AlertTriangle size={14} />
              <span>{workflowIdentityError ?? MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER}</span>
            </div>
          )}
          {!workflowContextMatches && (
            <div className="dialin-alert limited" role="alert">
              <AlertTriangle size={14} />
              <span>Decision context changed. Build a new verified plan before attaching or scoring runs.</span>
            </div>
          )}
          {!workflowAuthorityBlocked && workflow.packet.decision === "measure" && workflow.packet.measurement_mission && (
            <MeasurementMissionPanel
              mission={workflow.packet.measurement_mission}
              learning={selection.selectedMode === "learning"}
            />
          )}
          {!workflowAuthorityBlocked && workflow.packet.decision === "test" && workflow.packet.primary_test && (
            <>
              {exactSourceRunIntelligenceAuthority && (
                <p className="dialin-exact-change"><span>Current source-run one-change target</span><strong>{exactSourceRunIntelligenceAuthority.instruction}</strong></p>
              )}
              {stageBSetupAuthorityWithheld && (
                <div className="dialin-alert limited" role="alert" data-authority="withheld">
                  <AlertTriangle size={14} />
                  <span>{intelligenceAuthorityRecovery}</span>
                </div>
              )}
              <ControlledWorkflowProgress workflow={workflow} learning={selection.selectedMode === "learning"} authority={exactSourceRunIntelligenceAuthority} />
              {exactSourceRunIntelligenceAuthority && (
                <div className="dialin-test-guardrails">
                  <p><strong>Rollback:</strong> {workflow.packet.primary_test.rollback_rule}</p>
                  <p><strong>Stop and reset:</strong> {workflow.packet.primary_test.stop_rule}</p>
                </div>
              )}
              {nextWorkflowStage && <button className="secondary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches || workflowAuthorityBlocked || !currentStageRecordingAllowed} onClick={() => void recordCurrentRun()}>Verify current run as {workflowStageName(nextWorkflowStage)}</button>}
              {workflow.status === "a2_recorded" && <button className="primary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches || workflowAuthorityBlocked} onClick={() => void scoreVerifiedWorkflow()}>Score verified A/B/A2</button>}
              {workflow.quality && <p className="dialin-driver-message">{workflow.quality.verdict.toUpperCase()} · {workflow.quality.score.toFixed(0)}/100 · {workflow.quality.supporting_evidence[0] ?? workflow.quality.contradictory_evidence[0]}</p>}
              {workflow.quality?.controlled_effect_eligible && workflow.learning_admitted === false && (
                <p className="section-note">The test verdict is valid, but setup memory rejected the observation because its provenance contract was incomplete.</p>
              )}
            </>
          )}
          {workflowError && <div className="dialin-alert limited" role="alert"><AlertTriangle size={14} /><span>{workflowError}</span></div>}
        </section>
      )}

      {response && (
        <div className="dialin-result">
          <section className="dialin-decision-first" aria-label="Next action">
            <div>
              <span>{workflow && !workflowAuthorityBlocked ? decisionPresentation.label : "Data-backed read"}</span>
              <h3>{workflowAuthorityBlocked ? "Controlled workflow requires recovery" : workflow ? controlledWorkflowHeadline(workflow, exactSourceRunIntelligenceAuthority) : response.driver_message}</h3>
              {workflow && !workflowAuthorityBlocked && !stageBSetupAuthorityWithheld && <p>{response.driver_message}</p>}
            </div>
            <div className="dialin-decision-badges" aria-label="Decision status">
              <span className={`dialin-pill ${dialInTone(response.confidence_label)}`}>{response.confidence_label}</span>
              <span className={`dialin-pill ${dialInTone(response.readiness_label)}`}>{response.readiness_label}</span>
            </div>
          </section>

          <div className="dialin-summary-grid">
            <div>
              <span>Interpreted</span>
              <strong>{cleanLabel(response.interpreted_symptom)}</strong>
            </div>
            <div>
              <span>Phase</span>
              <strong>{cleanLabel(response.interpreted_phase, "Needs phase")}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong className={`dialin-pill ${dialInTone(response.confidence_label)}`}>{response.confidence_label}</strong>
            </div>
            <div>
              <span>Data Profile</span>
              <strong className={`dialin-pill ${dialInTone(response.readiness_label)}`}>{response.readiness_label}</strong>
            </div>
            <div>
              <span>Evidence</span>
              <strong className={`dialin-pill ${dialInTone(response.evidence_state)}`}>{cleanLabel(response.evidence_state)}</strong>
            </div>
            <div>
              <span>Mechanism proof</span>
              <strong className={`dialin-pill ${dialInTone(response.evidence_strength?.readiness ?? "blocked")}`}>
                {cleanLabel(response.evidence_strength?.level, "Unavailable")}
              </strong>
            </div>
          </div>

          {selection.selectedMode === "learning" && response.evidence_strength && (
            <p className="section-note">{response.evidence_strength.reason}</p>
          )}

          <section className="dialin-aba-card dialin-verified-workflow" aria-label="Verified controlled test workflow">
            <header>
              <div>
                <span className="eyebrow">{workflow && !workflowAuthorityBlocked ? decisionPresentation.label : "Server-verified Test Director"}</span>
                <h3>{workflowAuthorityBlocked ? "Controlled workflow requires recovery" : workflow ? controlledWorkflowHeadline(workflow, exactSourceRunIntelligenceAuthority) : "Build the evidence-gated plan"}</h3>
              </div>
              {(!workflow || !workflowContextMatches) && !activeWorkflow && (
                <button className="primary-button" type="button" disabled={workflowBusy || workflowAuthorityBlocked} onClick={() => void buildVerifiedWorkflow()}>
                  {workflowAuthorityBlocked ? "Resolve workflow blocker" : workflowBusy ? "Verifying evidence" : workflow ? "Build new verified plan" : "Build verified plan"}
                </button>
              )}
            </header>
            {workflow && !workflowAuthorityBlocked && !stageBSetupAuthorityWithheld && selection.selectedMode === "learning" && (
              <>
                <p className="section-note">{decisionPresentation.explanation}</p>
                <p className="section-note">
                  Evidence strength {(workflow.packet.confidence_score * 100).toFixed(0)}/100. {workflow.packet.confidence_basis}
                </p>
                {workflow.packet.recommendation_score_basis && (
                  <p className="section-note">Ranking basis: {workflow.packet.recommendation_score_basis}</p>
                )}
              </>
            )}
            {workflowAuthorityBlocked && (
              <div className="dialin-alert limited" role="alert">
                <AlertTriangle size={14} />
                <span>{workflowIdentityError ?? MULTIPLE_ACTIVE_WORKFLOWS_BLOCKER}</span>
              </div>
            )}
            {workflowError && <div className="dialin-alert limited" role="alert"><AlertTriangle size={14} /><span>{workflowError}</span></div>}
            {workflow && !workflowContextMatches && (
              <div className="dialin-alert limited" role="alert">
                <AlertTriangle size={14} />
                <span>Decision context changed. Build a new verified plan before attaching or scoring runs.</span>
              </div>
            )}
            {!workflowAuthorityBlocked && workflow?.packet.decision === "measure" && workflow.packet.measurement_mission && (
              <MeasurementMissionPanel
                mission={workflow.packet.measurement_mission}
                learning={selection.selectedMode === "learning"}
              />
            )}
            {!workflowAuthorityBlocked && workflow?.packet.decision === "test" && workflow.packet.primary_test && (
              <>
                {exactSourceRunIntelligenceAuthority && (
                  <>
                    <p className="dialin-exact-change"><span>Current source-run one-change target</span><strong>{exactSourceRunIntelligenceAuthority.instruction}</strong><small>{workflow.packet.primary_test.change_size}</small></p>
                    <div className="dialin-test-guardrails">
                      <p><strong>Rollback:</strong> {workflow.packet.primary_test.rollback_rule}</p>
                      <p><strong>Stop and reset:</strong> {workflow.packet.primary_test.stop_rule}</p>
                    </div>
                    {selection.selectedMode === "learning" && <p className="section-note">{workflow.packet.learning_mode_explanation}</p>}
                  </>
                )}
                {stageBSetupAuthorityWithheld && (
                  <div className="dialin-alert limited" role="alert" data-authority="withheld">
                    <AlertTriangle size={14} />
                    <span>{intelligenceAuthorityRecovery}</span>
                  </div>
                )}
                <ControlledWorkflowProgress workflow={workflow} learning={selection.selectedMode === "learning"} authority={exactSourceRunIntelligenceAuthority} />
                {nextWorkflowStage && (
                  <button className="secondary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches || workflowAuthorityBlocked || !currentStageRecordingAllowed} onClick={() => void recordCurrentRun()}>
                    {workflowBusy ? "Checking run" : `Verify current run as ${workflowStageName(nextWorkflowStage)}`}
                  </button>
                )}
                {workflow.status === "a2_recorded" && (
                  <button className="primary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches || workflowAuthorityBlocked} onClick={() => void scoreVerifiedWorkflow()}>
                    {workflowBusy ? "Scoring all eligible laps" : "Score verified A/B/A2"}
                  </button>
                )}
                {workflow.quality && (
                  <div className={`dialin-alert ${workflow.quality.controlled_effect_eligible ? "" : "limited"}`}>
                    <strong>{workflow.quality.verdict.toUpperCase()} · {workflow.quality.score.toFixed(0)}/100</strong>
                    <span>{workflow.quality.supporting_evidence[0] ?? workflow.quality.blockers[0] ?? workflow.quality.contradictory_evidence[0]}</span>
                  </div>
                )}
                {workflow.quality?.controlled_effect_eligible && workflow.learning_admitted === false && (
                  <p className="section-note">Result scored, but setup memory did not admit it; no learned response is implied.</p>
                )}
              </>
            )}
          </section>

          {response.blocker_reasons.length > 0 && (
            <div className="dialin-alert limited" role="status">
              <AlertTriangle size={14} />
              <span>{response.blocker_reasons.join(" ")}</span>
            </div>
          )}

          {selection.selectedMode === "learning" && response.source_channels.length > 0 && (
            <p className="section-note">Measured sources: {response.source_channels.join(", ")}</p>
          )}

          {response.clarification.needed && (
            <div className="dialin-clarification">
              <strong>{response.clarification.question ?? "Clarify the complaint phase."}</strong>
              <div className="dialin-chip-row">
                {response.clarification.options.map((option) => (
                  <button className="dialin-chip dialin-chip-button" key={option} type="button" onClick={() => chooseClarification(option)}>
                    {option}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!response.clarification.needed && response.top_swings.length === 0 && (
            <div className="dialin-empty">I need stronger data before ranking setup changes.</div>
          )}

          {selection.selectedMode === "learning" && !stageBSetupAuthorityWithheld && !response.clarification.needed && response.top_swings.length > 0 && (
            <>
              <div className="dialin-section-header">
                <div>
                  <span>Unverified hypotheses</span>
                  <h3>Ideas awaiting evidence-gated approval</h3>
                </div>
                <p>These explain possible mechanisms only. The server-verified Test Director above is the only setup action.</p>
              </div>
              <div className="dialin-swings">
                {primarySwings.map((swing) => (
                  <div key={swing.id}>
                    <SwingCard swing={swing} learning={selection.selectedMode === "learning"} />
                  </div>
                ))}
              </div>

              {secondarySwings.length > 0 && (
                <>
                  <div className="dialin-section-header compact">
                    <div>
                      <span>Lower priority</span>
                      <h3>Other hypotheses</h3>
                    </div>
                    <p>Only the top three are shown. These are explanations, not approved setup changes.</p>
                  </div>
                  <div className="dialin-other-grid">
                    {secondarySwings.map((swing) => (
                      <SwingCard swing={swing} compact learning={selection.selectedMode === "learning"} key={swing.id} />
                    ))}
                  </div>
                </>
              )}
            </>
          )}

          <div className="dialin-evidence-status">
            <span>Data Profile</span>
            <strong>{stageBSetupAuthorityWithheld
              ? "Stage B setup detail is withheld until current source-run authority is restored."
              : response.next_step ?? response.readiness_label}</strong>
            {!stageBSetupAuthorityWithheld && hints.length > 0 && (
              <div className="dialin-chip-row">
                {hints.map((hint) => <span className="dialin-chip" key={hint}>{hint}</span>)}
              </div>
            )}
          </div>
        </div>
      )}

      {!workflowAuthorityBlocked && workflow?.status === "scored" && workflow.quality && (
        <section className="dialin-aba-card dialin-test-certificate" aria-label="Controlled test certificate">
          <header>
            <div>
              <span className="eyebrow">Auditable test certificate</span>
              <h3>{workflow.quality.verdict.toUpperCase()} · {workflow.quality.score.toFixed(0)}/100 evidence strength</h3>
            </div>
            <span className={`dialin-mini-pill ${workflow.quality.controlled_effect_eligible ? "complete" : ""}`}>
              {workflow.learning_admitted === true ? "Memory admitted" : "No learned claim"}
            </span>
          </header>
          <p><strong>Historical target retained in the auditable certificate · not current setup authority</strong></p>
          {workflow.execution && (
            <div className="dialin-certificate-metrics">
              <div><span>B vs A</span><strong>{workflow.execution.phase_effect_b_vs_a_s?.toFixed(3) ?? "Unavailable"} s</strong></div>
              <div><span>B vs A2</span><strong>{workflow.execution.phase_effect_b_vs_a2_s?.toFixed(3) ?? "Unavailable"} s</strong></div>
              <div><span>Noise floor</span><strong>{workflow.execution.empirical_noise_s?.toFixed(3) ?? "Unavailable"} s</strong></div>
              <div><span>Lap response</span><strong>{workflow.execution.target_effect_distribution_state ?? "Unavailable"}</strong></div>
              <div><span>Other phases</span><strong>{workflow.execution.countereffect_passed === true ? "Passed" : workflow.execution.countereffect_passed === false ? "Rollback" : "Unavailable"}</strong></div>
              <div><span>Control safety</span><strong>{workflow.execution.control_guardrails_passed === true ? "Passed" : workflow.execution.control_guardrails_passed === false ? "Rollback" : "Unavailable"}</strong></div>
            </div>
          )}
          <p className="section-note">
            {workflow.quality.supporting_evidence[0] ?? workflow.quality.blockers[0] ?? workflow.quality.contradictory_evidence[0]}
          </p>
          <div className="dialin-certificate-actions">
            {!certificateMarkdown && (
              <button className="secondary-button" type="button" disabled={certificateBusy} onClick={() => void openTestCertificate()}>
                {certificateBusy ? "Building certificate" : "Open full certificate"}
              </button>
            )}
            {certificateMarkdown && <button className="secondary-button" type="button" onClick={() => void copyTestCertificate()}>Copy Markdown</button>}
            {certificateMarkdown && <button className="secondary-button" type="button" onClick={downloadTestCertificate}>Download Markdown</button>}
          </div>
          {certificateError && <div className="dialin-alert limited" role="alert"><AlertTriangle size={14} /><span>{certificateError}</span></div>}
          {certificateMarkdown && selection.selectedMode === "learning" && (
            <details className="dialin-certificate-details" open>
              <summary>Reproduction evidence and provenance</summary>
              <pre>{certificateMarkdown}</pre>
            </details>
          )}
        </section>
      )}
    </section>
  );
}
