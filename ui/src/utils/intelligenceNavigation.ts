import type { Workspace } from "../store/types";
import type {
  IntelligenceCitation,
  IntelligenceCitationWorkspace,
  IntelligenceMoveWorkspace,
  IntelligenceNextTrustworthyMove,
  IntelligenceQueryNavigationTarget,
  IntelligenceRecoveryKind,
} from "../types/intelligence";

export type IntelligenceMoveScope =
  | { kind: "run"; lap: null; windowStart: null; windowEnd: null; pctStart: null; pctEnd: null }
  | { kind: "single_lap"; lap: number; windowStart: null; windowEnd: null; pctStart: number | null; pctEnd: number | null }
  | { kind: "lap_window"; lap: number; windowStart: number; windowEnd: number; pctStart: number | null; pctEnd: number | null };

export type IntelligenceWorkflowRevision = {
  workflowId: string | null;
  workflowUpdatedAt: string | null;
};

export type IntelligenceSetupMoveAuthorization = IntelligenceWorkflowRevision & {
  controlKey: string | null;
  sourceEventIds: readonly string[];
};

const WORKSPACE_MAP: Record<IntelligenceMoveWorkspace, Workspace> = {
  overview: "overview",
  laps: "laps",
  platform: "platform_trace",
  setup: "setup_impact",
  engineer: "engineer",
  dial_in: "dial_in",
};

const RECOVERY_KINDS: ReadonlySet<IntelligenceRecoveryKind> = new Set([
  "select_eligible_lap",
  "retry_resource",
  "inspect_missing_channel",
  "repeat_measurement",
  "resume_workflow",
]);

const MOVE_KINDS: ReadonlySet<IntelligenceNextTrustworthyMove["kind"]> = new Set([
  "recover",
  "qualify",
  "diagnose",
  "measure",
  "controlled_test",
  "compare",
  "decide",
]);

const QUERY_NAVIGATION_WORKSPACES: ReadonlySet<IntelligenceCitationWorkspace> = new Set([
  "overview",
  "laps",
  "platform_trace",
  "speed_delta",
  "drag_scrub",
  "setup_impact",
  "dial_in",
]);

function positiveInteger(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

function canonicalIdentity(value: string | null | undefined): value is string {
  return typeof value === "string" && value.length > 0 && value.trim() === value;
}

function workflowRevisionIsCanonical(revision: IntelligenceWorkflowRevision): boolean {
  const hasWorkflowId = revision.workflowId != null;
  const hasUpdatedAt = revision.workflowUpdatedAt != null;
  return hasWorkflowId === hasUpdatedAt
    && (!hasWorkflowId || (
      canonicalIdentity(revision.workflowId)
      && canonicalIdentity(revision.workflowUpdatedAt)
    ));
}

function moveWorkflowRevision(move: IntelligenceNextTrustworthyMove): IntelligenceWorkflowRevision {
  return {
    workflowId: move.workflow_id ?? null,
    workflowUpdatedAt: move.workflow_updated_at ?? null,
  };
}

export function exactEventIdentitySet(left: readonly string[], right: readonly string[]): boolean {
  if (left.length === 0 || left.length !== right.length) return false;
  const leftSet = new Set(left);
  const rightSet = new Set(right);
  return leftSet.size === left.length
    && rightSet.size === right.length
    && [...leftSet].every((identity) => canonicalIdentity(identity) && rightSet.has(identity));
}

/** Converts a validated query handoff to evidence-only navigation. It never grants setup authority. */
export function trustedQueryNavigationCitation(
  target: IntelligenceQueryNavigationTarget | null | undefined,
  allowedRunIds: ReadonlySet<string>,
): IntelligenceCitation | null {
  if (!target || !canonicalIdentity(target.run_id) || !allowedRunIds.has(target.run_id)) return null;
  if (!QUERY_NAVIGATION_WORKSPACES.has(target.workspace)) return null;
  const lapNumber = target.lap_number ?? null;
  const lapPct = target.lap_pct ?? null;
  const eventId = target.event_id ?? null;
  if (lapNumber != null && !positiveInteger(lapNumber)) return null;
  if (
    lapPct != null
    && (
      typeof lapPct !== "number"
      || !Number.isFinite(lapPct)
      || lapPct < 0
      || lapPct > 100
    )
  ) return null;
  if (eventId != null && !canonicalIdentity(eventId)) return null;
  return {
    citation_id: `query-navigation:${JSON.stringify([
      target.workspace,
      target.run_id,
      lapNumber,
      eventId,
      lapPct,
    ])}`,
    label: eventId ? "Open linked evidence" : "Open linked source run",
    run_id: target.run_id,
    lap_number: lapNumber,
    lap_pct: lapPct,
    event_id: eventId,
    workspace: target.workspace,
    source_channels: [],
    evidence_state: "needs_confirmation",
    valid_for_tuning: false,
  };
}

export function intelligenceWorkspaceTarget(value: string): Workspace | null {
  return Object.prototype.hasOwnProperty.call(WORKSPACE_MAP, value)
    ? WORKSPACE_MAP[value as IntelligenceMoveWorkspace]
    : null;
}

export function intelligenceMoveScope(move: IntelligenceNextTrustworthyMove): IntelligenceMoveScope | null {
  const hasPctStart = move.lap_pct_start != null;
  const hasPctEnd = move.lap_pct_end != null;
  if (hasPctStart || hasPctEnd) {
    if (
      typeof move.lap_pct_start !== "number"
      || !Number.isFinite(move.lap_pct_start)
      || typeof move.lap_pct_end !== "number"
      || !Number.isFinite(move.lap_pct_end)
      || move.lap_pct_start < 0
      || move.lap_pct_end > 100
      || move.lap_pct_start >= move.lap_pct_end
      || !positiveInteger(move.lap_number)
    ) return null;
  }
  const pctStart = hasPctStart ? move.lap_pct_start as number : null;
  const pctEnd = hasPctEnd ? move.lap_pct_end as number : null;
  const hasWindowStart = move.window_start_lap != null;
  const hasWindowEnd = move.window_end_lap != null;
  if (hasWindowStart || hasWindowEnd) {
    if (
      !positiveInteger(move.window_start_lap)
      || !positiveInteger(move.window_end_lap)
      || move.window_start_lap > move.window_end_lap
      || !positiveInteger(move.lap_number)
      || move.lap_number < move.window_start_lap
      || move.lap_number > move.window_end_lap
    ) return null;
    return {
      kind: "lap_window",
      lap: move.lap_number,
      windowStart: move.window_start_lap,
      windowEnd: move.window_end_lap,
      pctStart,
      pctEnd,
    };
  }
  if (move.lap_number == null) {
    return { kind: "run", lap: null, windowStart: null, windowEnd: null, pctStart: null, pctEnd: null };
  }
  if (!positiveInteger(move.lap_number)) return null;
  return { kind: "single_lap", lap: move.lap_number, windowStart: null, windowEnd: null, pctStart, pctEnd };
}

/** Runtime trust check for optional server data. It grants navigation, never execution. */
export function trustedNavigationMove(
  move: IntelligenceNextTrustworthyMove | null | undefined,
  runId: string,
  expectedWorkflow?: IntelligenceWorkflowRevision,
): move is IntelligenceNextTrustworthyMove {
  if (!move || move.run_id !== runId) return false;
  if (!move.move_id?.trim() || !move.title?.trim() || !move.instruction?.trim()) return false;
  if (!MOVE_KINDS.has(move.kind)) return false;
  if (!intelligenceWorkspaceTarget(move.workspace) || !intelligenceMoveScope(move)) return false;
  if (!Array.isArray(move.source_event_ids) || !Array.isArray(move.blocker_reasons)) return false;
  if (
    move.source_event_ids.some((eventId) => typeof eventId !== "string" || !eventId.trim())
    || move.blocker_reasons.some((reason) => typeof reason !== "string" || !reason.trim())
  ) return false;
  const moveRevision = moveWorkflowRevision(move);
  if (!workflowRevisionIsCanonical(moveRevision)) return false;
  const moveIsWorkflowBound = moveRevision.workflowId != null;
  const workflowMoveRequiresBinding = move.workspace === "dial_in"
    || ["controlled_test", "compare", "decide"].includes(move.kind);
  if (workflowMoveRequiresBinding && !moveIsWorkflowBound) return false;
  if (expectedWorkflow) {
    if (!workflowRevisionIsCanonical(expectedWorkflow)) return false;
    if (
      moveIsWorkflowBound
        ? (
          moveRevision.workflowId !== expectedWorkflow.workflowId
          || moveRevision.workflowUpdatedAt !== expectedWorkflow.workflowUpdatedAt
        )
        : false
    ) return false;
  }
  if (move.authority === "navigation_only") return move.control_key == null;
  return move.authority === "setup_authorized"
    && move.kind === "controlled_test"
    && move.workspace === "dial_in"
    && canonicalIdentity(move.workflow_id)
    && canonicalIdentity(move.workflow_updated_at)
    && canonicalIdentity(move.control_key)
    && move.source_event_ids.length > 0
    && move.blocker_reasons.length === 0;
}

export function trustedSetupAuthorizedMove(
  move: IntelligenceNextTrustworthyMove | null | undefined,
  runId: string,
  authorization: IntelligenceSetupMoveAuthorization,
): move is IntelligenceNextTrustworthyMove {
  return trustedNavigationMove(move, runId, authorization)
    && move.authority === "setup_authorized"
    && canonicalIdentity(authorization.controlKey)
    && move.control_key === authorization.controlKey
    && exactEventIdentitySet(move.source_event_ids, authorization.sourceEventIds);
}

export function trustedRecoveryTarget(
  recoveryKind: string,
  workspace: string,
): { kind: IntelligenceRecoveryKind; workspace: Workspace } | null {
  const target = intelligenceWorkspaceTarget(workspace);
  if (!RECOVERY_KINDS.has(recoveryKind as IntelligenceRecoveryKind) || !target) return null;
  return { kind: recoveryKind as IntelligenceRecoveryKind, workspace: target };
}

export function moveScopeLabel(scope: IntelligenceMoveScope): string {
  const trackWindow = scope.pctStart != null && scope.pctEnd != null
    ? ` \u00b7 ${scope.pctStart.toFixed(1)}\u2013${scope.pctEnd.toFixed(1)}%`
    : "";
  if (scope.kind === "lap_window") {
    return `Window L${scope.windowStart}\u2013L${scope.windowEnd} \u00b7 representative Lap ${scope.lap}${trackWindow}`;
  }
  if (scope.kind === "single_lap") return `Lap ${scope.lap}${trackWindow}`;
  return "Current run";
}
