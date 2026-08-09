import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  History,
  Lightbulb,
  ListChecks,
  Route,
  Scale,
  ShieldCheck,
  Target,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Workspace } from "../store/types";
import type {
  IntelligenceAnomalyReport,
  IntelligenceAttentionItem,
  IntelligenceCause,
  IntelligenceHypothesisLifecycle,
  IntelligenceMindChangeCriterion,
  IntelligenceMechanismObservation,
  IntelligenceMeasurementDebt,
  IntelligenceNextTrustworthyMove,
  IntelligenceOpportunityReport,
  IntelligenceOpportunitySignature,
  IntelligenceRecoveryKind,
  IntelligenceSessionLedger,
  IntelligenceTelemetryHealthReport,
  RunIntelligenceReport,
} from "../types/intelligence";
import {
  intelligenceMoveScope,
  intelligenceWorkspaceTarget,
  moveScopeLabel,
  trustedNavigationMove,
  trustedRecoveryTarget,
  trustedSetupAuthorizedMove,
} from "../utils/intelligenceNavigation";
import type { IntelligenceWorkflowRevision } from "../utils/intelligenceNavigation";

type AttentionSnapshot = Record<string, string>;
type MissionStage = NonNullable<RunIntelligenceReport["mission_stage"]>;

const MISSION_STAGES: MissionStage[] = [
  "qualify",
  "diagnose",
  "measure",
  "test",
  "compare",
  "decide",
  "certified",
];

const MISSION_STAGE_COPY: Record<MissionStage, {
  title: string;
  race: string;
  learning: string;
}> = {
  qualify: {
    title: "Make the run trustworthy",
    race: "Clear the evidence gate before diagnosing the car.",
    learning: "Only complete, continuous, eligible laps can support the diagnosis. Recover the first failed qualification before interpreting pace or balance.",
  },
  diagnose: {
    title: "Name the repeatable loss",
    race: "Find the strongest pattern that repeats above driver noise.",
    learning: "Compare qualified laps at the same track position, keep competing explanations visible, and do not turn an observation into a setup cause.",
  },
  measure: {
    title: "Collect the missing proof",
    race: "Run the smallest measurement that separates the open explanations.",
    learning: "Hold the named context constant, follow the producer-owned procedure, and stop when the measurement contract says the evidence is no longer comparable.",
  },
  test: {
    title: "Run one controlled change",
    race: "Follow the frozen A/B/A2 card one stage at a time.",
    learning: "The exact target remains in Dial-In. Warm-up, flying-lap, rollback, and stop rules must all remain intact before the change can earn causal credit.",
  },
  compare: {
    title: "Compare A, B, and A2",
    race: "Score the verified stages before making a keep-or-undo call.",
    learning: "The comparison must reproduce against both baselines, clear empirical noise, and pass countereffect and control guardrails.",
  },
  decide: {
    title: "Keep, undo, or retest",
    race: "Use the controlled verdict; do not average away contradictions.",
    learning: "A decision is only as strong as the frozen protocol. Inconclusive or contradictory outcomes stay unresolved and should become a narrower retest.",
  },
  certified: {
    title: "Carry forward verified learning",
    race: "Review the certificate and reuse only its exact context.",
    learning: "Certified learning remains bound to the tested car, track, setup, control, conditions, and evidence identities; it is not a universal setup rule.",
  },
};

function readAttentionSnapshot(key: string): AttentionSnapshot {
  if (typeof window === "undefined") return {};
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(key) ?? "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([id, fingerprint]) => (
        id.trim().length > 0
        && typeof fingerprint === "string"
        && fingerprint.trim().length >= 16
      )),
    );
  } catch {
    return {};
  }
}

function attentionStorageKey(runId: string, sessionId: string | null): string {
  return `racelab:intelligence-attention:v1:${sessionId ?? "run-only"}:${runId}`;
}

type SmartIntelligenceCardsProps = {
  report: RunIntelligenceReport;
  runId: string;
  sessionId: string | null;
  learning: boolean;
  setupActionAuthorized: boolean;
  authorizedSetupAction: {
    controlKey: string | null;
    sourceEventIds: readonly string[];
  } | null;
  workflowRevision: IntelligenceWorkflowRevision;
  onOpenMove: (move: IntelligenceNextTrustworthyMove) => void;
  onOpenRecovery: (workspace: Workspace, recoveryKind: IntelligenceRecoveryKind) => void;
};

function seconds(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "not measured";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)} s`;
}

function percent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(1)}%` : "unknown position";
}

function sentenceLabel(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

type OvalCrewPhase = "entry" | "center" | "exit" | "carry";

const OVAL_CREW_PHASES: Array<{
  key: OvalCrewPhase;
  label: string;
  cue: string;
}> = [
  { key: "entry", label: "Entry", cue: "Brake, release, turn-in" },
  { key: "center", label: "Center", cue: "Rotation" },
  { key: "exit", label: "Exit", cue: "Throttle commitment" },
  { key: "carry", label: "Carry", cue: "Straightaway speed" },
];

function ovalCrewPhase(value: string | null | undefined): OvalCrewPhase | null {
  const phase = value?.trim().toLowerCase().replace(/[ -]+/g, "_") ?? "";
  if (["braking", "brake_application", "threshold_braking", "brake_release", "turn_in", "entry"].includes(phase)) {
    return "entry";
  }
  if (["center", "apex", "apex_region"].includes(phase)) return "center";
  if (["exit", "initial_throttle", "full_throttle_exit"].includes(phase)) return "exit";
  if (["straight", "following_straight_carry"].includes(phase)) return "carry";
  return null;
}

function exactOvalMechanismObservations(
  report: RunIntelligenceReport,
): IntelligenceMechanismObservation[] {
  const mechanismReport = report.mechanism_observations;
  if (
    !mechanismReport
    || mechanismReport.run_id !== report.run_id
    || mechanismReport.authority !== "observation_only"
  ) return [];
  return mechanismReport.observations.filter((observation) => (
    observation.run_id === report.run_id
    && observation.authority === "observation_only"
    && observation.qualified
    && observation.blocker_reasons.length === 0
    && observation.source_channels.length > 0
    && ovalCrewPhase(observation.phase) != null
    && observation.citations.some((citation) => citation.run_id === report.run_id)
  ));
}

function exactOvalOpportunities(report: RunIntelligenceReport): IntelligenceOpportunitySignature[] {
  const opportunityReport = report.opportunity_signature;
  if (
    !opportunityReport
    || opportunityReport.run_id !== report.run_id
    || opportunityReport.authority !== "observation_only"
  ) return [];
  return opportunityReport.signatures.filter((signature) => (
    signature.run_id === report.run_id
    && signature.authority === "observation_only"
    && signature.evidence_state === "observed_correlation"
    && signature.blocker_reasons.length === 0
    && signature.source_channels.length > 0
    && signature.repetition_count >= 2
    && signature.median_opportunity_s > signature.empirical_noise_s
    && ovalCrewPhase(signature.phase) != null
    && signature.citations.some((citation) => citation.run_id === report.run_id)
  ));
}

function workspaceLabel(workspace: string): string {
  const target = intelligenceWorkspaceTarget(workspace);
  if (target === "platform_trace") return "Platform";
  if (target === "setup_impact") return "Setup";
  if (target === "dial_in") return "Dial-In";
  return target ? sentenceLabel(target) : "workspace";
}

function recoveryLabel(kind: IntelligenceRecoveryKind): string {
  const labels: Record<IntelligenceRecoveryKind, string> = {
    select_eligible_lap: "Select an eligible lap",
    retry_resource: "Open recovery view",
    inspect_missing_channel: "Inspect missing channels",
    repeat_measurement: "Review measurement",
    resume_workflow: "Resume workflow",
  };
  return labels[kind];
}

function opportunitySignature(
  value: RunIntelligenceReport["opportunity_signature"],
  runId: string,
): { signature: IntelligenceOpportunitySignature | null; report: IntelligenceOpportunityReport | null } {
  if (!value) return { signature: null, report: null };
  if (value.run_id !== runId || value.authority !== "observation_only") {
    return { signature: null, report: null };
  }
  return {
    report: value,
    signature: value.signatures.find((signature) => (
      signature.run_id === runId
      && signature.authority === "observation_only"
      && signature.blocker_reasons.length === 0
    )) ?? null,
  };
}

function anomalyReport(
  value: RunIntelligenceReport["anomalies"],
  runId: string,
): IntelligenceAnomalyReport | null {
  if (!value) return null;
  return value.run_id === runId && value.authority === "observation_only" ? value : null;
}

function exactSessionLedger(
  value: IntelligenceSessionLedger | null | undefined,
  sessionId: string | null,
): IntelligenceSessionLedger | null {
  return value && sessionId && value.session_id === sessionId ? value : null;
}

function exactHypothesisLifecycle(
  value: IntelligenceHypothesisLifecycle | null | undefined,
  sessionId: string | null,
): IntelligenceHypothesisLifecycle | null {
  return value && sessionId && value.session_id === sessionId ? value : null;
}

export type ExactMindChangeCriterion = {
  criterion: IntelligenceMindChangeCriterion;
  cause: IntelligenceCause;
  sourceIndex: number;
};

const MIND_CHANGE_STATES = new Set(["leading", "possible", "ruled_out", "unresolved"]);
const MIND_CHANGE_PHASES = new Set(["braking", "entry", "center", "exit", "straight"]);
const MIND_CHANGE_EVIDENCE_KINDS = new Set(["controlled_test", "measurement_mission", "discriminator"]);

function canonicalText(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.trim() === value;
}

function canonicalUniqueTextList(value: unknown, allowEmpty: boolean): value is string[] {
  return Array.isArray(value)
    && (allowEmpty || value.length > 0)
    && value.every(canonicalText)
    && new Set(value).size === value.length;
}

export function exactMindChangeCriteria(
  candidates: IntelligenceMindChangeCriterion[] | null | undefined,
  causes: IntelligenceCause[] | null | undefined,
  runId: string,
  sessionId: string | null,
): ExactMindChangeCriterion[] {
  const causeById = new Map((Array.isArray(causes) ? causes : []).map((cause) => [cause.cause_id, cause]));
  const seenCriterionIds = new Set<string>();
  const exact: ExactMindChangeCriterion[] = [];
  const suppliedCriteria = Array.isArray(candidates) ? candidates : [];
  suppliedCriteria.forEach((criterion, sourceIndex) => {
    const cause = causeById.get(criterion.cause_id);
    const minimumUnits = criterion.minimum_independent_evidence_units;
    const minimumLaps = criterion.minimum_laps_per_stage ?? null;
    if (
      !cause
      || cause.state !== criterion.current_state
      || criterion.run_id !== runId
      || (criterion.session_id ?? null) !== sessionId
      || !canonicalText(criterion.criterion_id)
      || seenCriterionIds.has(criterion.criterion_id)
      || !MIND_CHANGE_STATES.has(criterion.current_state)
      || !MIND_CHANGE_STATES.has(criterion.next_state_if_accepted)
      || !MIND_CHANGE_STATES.has(criterion.next_state_if_falsified)
      || criterion.next_state_if_inconclusive !== "unresolved"
      || !MIND_CHANGE_PHASES.has(criterion.phase)
      || !MIND_CHANGE_EVIDENCE_KINDS.has(criterion.evidence_kind)
      || !canonicalText(criterion.metric)
      || !canonicalText(criterion.threshold_source)
      || !canonicalText(criterion.minimum_evidence)
      || (criterion.control_key != null && !canonicalText(criterion.control_key))
      || !canonicalUniqueTextList(criterion.acceptance_conditions, false)
      || !canonicalUniqueTextList(criterion.falsification_conditions, false)
      || !canonicalUniqueTextList(criterion.countereffects, true)
      || !canonicalUniqueTextList(criterion.source_event_ids, true)
      || !Number.isInteger(minimumUnits)
      || minimumUnits < 2
      || (
        criterion.requires_aba2
          ? !Number.isInteger(minimumLaps) || (minimumLaps ?? 0) < 3 || minimumUnits < 9
          : minimumLaps != null
      )
    ) return;
    seenCriterionIds.add(criterion.criterion_id);
    exact.push({ criterion, cause, sourceIndex });
  });
  return exact.sort((left, right) => (
    left.cause.rank - right.cause.rank
    || left.sourceIndex - right.sourceIndex
    || left.criterion.criterion_id.localeCompare(right.criterion.criterion_id)
  ));
}

function missionStagePresentation(stage: MissionStage | null | undefined, learning: boolean) {
  if (!stage) {
    return {
      stage: null,
      position: null,
      title: "What this run teaches next",
      detail: "Follow the single evidence-qualified move, then reassess.",
    };
  }
  const copy = MISSION_STAGE_COPY[stage];
  return {
    stage,
    position: MISSION_STAGES.indexOf(stage) + 1,
    title: copy.title,
    detail: learning ? copy.learning : copy.race,
  };
}

const PREFLIGHT_PROGRESS_STAGES = ["A", "B", "A2", "complete"] as const;

function preflightStageLabel(stage: (typeof PREFLIGHT_PROGRESS_STAGES)[number]): string {
  if (stage === "A") return "Baseline A";
  if (stage === "B") return "One change B";
  if (stage === "A2") return "Restore A2";
  return "Compare";
}

function NextMoveCard({
  move,
  runId,
  workflowRevision,
  learning,
  onOpen,
}: {
  move: IntelligenceNextTrustworthyMove;
  runId: string;
  workflowRevision: IntelligenceWorkflowRevision;
  learning: boolean;
  onOpen: SmartIntelligenceCardsProps["onOpenMove"];
}) {
  if (!trustedNavigationMove(move, runId, workflowRevision)) return null;
  const scope = intelligenceMoveScope(move);
  if (!scope) return null;
  const setupAuthorized = move.authority === "setup_authorized";
  return (
    <section
      className="engineer-smart-card engineer-next-move"
      data-authority={move.authority}
      data-move-kind={move.kind}
      aria-labelledby={`engineer-next-move-${move.move_id}`}
    >
      <header>
        <Route size={16} aria-hidden="true" />
        <div><span className="eyebrow">Next trustworthy move</span><h3 id={`engineer-next-move-${move.move_id}`}>{move.title}</h3></div>
        <span className="engineer-smart-authority" data-authorized={setupAuthorized ? "true" : "false"}>
          {setupAuthorized ? "Controlled-test authority" : "Navigation only"}
        </span>
      </header>
      <p className="engineer-smart-command">{move.instruction}</p>
      <div className="engineer-smart-why" aria-label="Why this move is next">
        <strong>Why now</strong>
        <p>{move.reason}</p>
      </div>
      <div className="engineer-smart-facts">
        <span><strong>Scope</strong> {moveScopeLabel(scope)}</span>
        <span><strong>Handoff</strong> {workspaceLabel(move.workspace)}</span>
        <span><strong>Authority</strong> {setupAuthorized ? "Exact target stays in Dial-In" : "No setup change"}</span>
        {move.source_event_ids.length > 0 && <span><strong>Evidence</strong> {move.source_event_ids.length} bound event{move.source_event_ids.length === 1 ? "" : "s"}</span>}
      </div>
      {move.blocker_reasons.length > 0 && (
        <ul className="engineer-smart-blockers">{move.blocker_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      )}
      <button type="button" onClick={() => onOpen(move)}>
        {setupAuthorized ? "Continue in" : "Go to"} {workspaceLabel(move.workspace)} <ArrowRight size={13} aria-hidden="true" />
      </button>
      <small>{learning
        ? "This handoff preserves the exact run and evidence scope. It never starts, records, or advances a test."
        : "Handoff only — no test advances automatically."}</small>
    </section>
  );
}

function OpportunityCard({
  signature,
  report,
  learning,
}: {
  signature: IntelligenceOpportunitySignature | null;
  report: IntelligenceOpportunityReport | null;
  learning: boolean;
}) {
  if (!signature && !report) return null;
  if (!signature) {
    return (
      <section className="engineer-smart-card" data-state={report?.status ?? "blocked"}>
        <header><Target size={16} aria-hidden="true" /><div><span className="eyebrow">Repeatable opportunity</span><h3>No qualified signature published</h3></div></header>
        <p>{report?.status === "no_finding" ? "Same-setup eligible laps did not produce a repeatable opportunity above the empirical noise floor." : "The opportunity scan is blocked by its evidence contract."}</p>
        {learning && report && report.blocker_reasons.length > 0 && <ul className="engineer-smart-blockers">{report.blocker_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
      </section>
    );
  }
  const clearsNoise = signature.median_opportunity_s > signature.empirical_noise_s;
  return (
    <section className="engineer-smart-card engineer-opportunity" data-state={clearsNoise ? "ready" : "guarded"}>
      <header><Target size={16} aria-hidden="true" /><div><span className="eyebrow">Repeatable opportunity</span><h3>{sentenceLabel(signature.phase)} · {percent(signature.lap_pct_start)}–{percent(signature.lap_pct_end)}</h3></div><span className="engineer-smart-authority">Observation only</span></header>
      <div className="engineer-smart-metric"><strong>{seconds(signature.median_opportunity_s)}</strong><span>median same-setup opportunity</span></div>
      <div className="engineer-smart-facts">
        <span>{signature.repetition_count} repetitions</span>
        <span>{signature.eligible_lap_count} eligible laps</span>
        <span>Noise {seconds(signature.empirical_noise_s)}</span>
      </div>
      <p>{clearsNoise ? "The position-aligned signal repeated above this driver's empirical noise floor." : "The observed signal does not clear the empirical noise floor, so no action is implied."}</p>
      {learning && <small>{signature.telemetry_sample_count.toLocaleString()} telemetry samples support the lap-level summary. Samples are not counted as independent experiments.</small>}
    </section>
  );
}

function DriverFocusCard({ report, learning }: { report: RunIntelligenceReport; learning: boolean }) {
  const driverFocus = report.driver_focus;
  if (!driverFocus || driverFocus.run_id !== report.run_id || driverFocus.authority !== "driver_coaching_only") return null;
  const focus = driverFocus.focus;
  return (
    <section className="engineer-smart-card" data-state={driverFocus.status}>
      <header><Activity size={16} aria-hidden="true" /><div><span className="eyebrow">Driver repeatability</span><h3>{focus ? `${sentenceLabel(focus.phase)} focus` : "No coaching focus published"}</h3></div><span className="engineer-smart-authority">Coaching only</span></header>
      {focus ? (
        <>
          <p>{focus.instruction}</p>
          <div className="engineer-smart-facts"><span>{percent(focus.lap_pct_start)}–{percent(focus.lap_pct_end)}</span><span>{focus.channel}</span><span>{driverFocus.eligible_lap_count} same-setup laps</span></div>
          <p className="engineer-smart-success"><strong>Success:</strong> {focus.success_check}</p>
        </>
      ) : (
        <p>{driverFocus.status === "no_finding" ? "Execution variance does not currently outrank the setup signal." : "The coaching comparison is blocked until its required evidence is available."}</p>
      )}
      {learning && driverFocus.blocker_reasons.length > 0 && <ul className="engineer-smart-blockers">{driverFocus.blocker_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
      <small>Driver coaching never authorizes a setup change.</small>
    </section>
  );
}

export function MindChangeCriteriaCard({
  criteria,
  learning,
  headingId,
  scopeLabel,
}: {
  criteria: ExactMindChangeCriterion[];
  learning: boolean;
  headingId: string;
  scopeLabel: string;
}) {
  const visibleCriteria = learning ? criteria : criteria.slice(0, 1);
  if (visibleCriteria.length === 0) return null;
  return (
    <section
      className="engineer-smart-card engineer-mind-change"
      data-authority="reasoning-only"
      data-setup-authorized="false"
      data-mode={learning ? "learning" : "race"}
      data-reasoning-scope={scopeLabel}
      aria-labelledby={headingId}
    >
      <header>
        <Scale size={16} aria-hidden="true" />
        <div>
          <span className="eyebrow">What changes the call · {scopeLabel}</span>
          <h3 id={headingId}>
            {learning && visibleCriteria.length > 1
              ? `${visibleCriteria.length} deterministic evidence gates`
              : "The clearest way to accept or falsify the leading candidate"}
          </h3>
        </div>
        <span
          className="engineer-smart-authority"
          aria-label="Reasoning only. No setup authority."
        >
          Reasoning only · no setup authority
        </span>
      </header>
      <div
        className="engineer-mind-change-list"
        role="list"
        aria-label={learning ? "All exact mind-change criteria" : "Top exact mind-change criterion"}
      >
        {visibleCriteria.map(({ criterion, cause }, index) => {
          const criterionHeadingId = `${headingId}-criterion-${index}`;
          const acceptance = criterion.acceptance_conditions;
          const falsification = criterion.falsification_conditions;
          const countereffects = criterion.countereffects;
          const evidenceRequirement = criterion.requires_aba2
            ? `A/B/A2 required · ${criterion.minimum_laps_per_stage} eligible laps per stage · ${criterion.minimum_independent_evidence_units} independent lap-stage units`
            : `${criterion.minimum_independent_evidence_units} independent evidence units · A/B/A2 not required`;
          return (
            <article
              key={criterion.criterion_id}
              className="engineer-mind-change-criterion"
              data-cause-id={criterion.cause_id}
              data-current-state={criterion.current_state}
              data-evidence-kind={criterion.evidence_kind}
              role="listitem"
              aria-labelledby={criterionHeadingId}
            >
              <header>
                <div>
                  <span>Current candidate · {sentenceLabel(criterion.current_state)}</span>
                  <h4 id={criterionHeadingId}>{cause.label}</h4>
                </div>
                <strong>{sentenceLabel(criterion.evidence_kind)}</strong>
              </header>
              <div className="engineer-mind-change-scope" aria-label={`Exact reasoning scope for ${cause.label}`}>
                <span><strong>Phase</strong>{sentenceLabel(criterion.phase)}</span>
                <span><strong>Metric</strong>{criterion.metric}</span>
                {criterion.control_key && <span><strong>Control</strong>{sentenceLabel(criterion.control_key)}</span>}
              </div>
              <div className="engineer-mind-change-conditions">
                <section aria-labelledby={`${criterionHeadingId}-accept`}>
                  <h5 id={`${criterionHeadingId}-accept`}>Accept this candidate if</h5>
                  <ul aria-label={`Acceptance conditions for ${cause.label}`}>
                    {acceptance.map((condition) => <li key={condition}>{condition}</li>)}
                  </ul>
                </section>
                <section aria-labelledby={`${criterionHeadingId}-falsify`}>
                  <h5 id={`${criterionHeadingId}-falsify`}>Falsify this candidate if</h5>
                  <ul aria-label={`Falsification conditions for ${cause.label}`}>
                    {falsification.map((condition) => <li key={condition}>{condition}</li>)}
                  </ul>
                </section>
              </div>
              <div className="engineer-mind-change-minimum" role="note" aria-label={`Minimum independent evidence for ${cause.label}`}>
                <strong>Minimum proof</strong>
                <span>{evidenceRequirement}</span>
                {learning && <small>{criterion.minimum_evidence}</small>}
                {learning && <small>Threshold source: {criterion.threshold_source}</small>}
              </div>
              <dl className="engineer-mind-change-states" aria-label={`Deterministic next states for ${cause.label}`}>
                <div><dt>Accepted</dt><dd>{sentenceLabel(criterion.next_state_if_accepted)}</dd></div>
                <div><dt>Falsified</dt><dd>{sentenceLabel(criterion.next_state_if_falsified)}</dd></div>
                <div><dt>Inconclusive</dt><dd>{sentenceLabel(criterion.next_state_if_inconclusive)}</dd></div>
              </dl>
              <div className="engineer-mind-change-countereffects">
                <strong>Countereffects to protect</strong>
                {countereffects.length > 0 ? (
                  <ul aria-label={`Countereffects for ${cause.label}`}>
                    {countereffects.map((countereffect) => <li key={countereffect}>{countereffect}</li>)}
                  </ul>
                ) : <p>No countereffect guardrail is published for this criterion.</p>}
              </div>
              {learning && criterion.source_event_ids.length > 0 && (
                <small>{criterion.source_event_ids.length} source event{criterion.source_event_ids.length === 1 ? "" : "s"} bind this reasoning gate to the current report.</small>
              )}
            </article>
          );
        })}
      </div>
      {!learning && criteria.length > visibleCriteria.length && (
        <small>{criteria.length - visibleCriteria.length} lower-ranked criterion{criteria.length - visibleCriteria.length === 1 ? "" : "s"} remain available in Learning Mode.</small>
      )}
      <p className="engineer-mind-change-guard">
        <ShieldCheck size={13} aria-hidden="true" /> Reasoning only. This card cannot choose a setup value, start a test, or advance a workflow.
      </p>
    </section>
  );
}

function OvalCrewBoard({
  report,
  ledger,
  move,
  learning,
}: {
  report: RunIntelligenceReport;
  ledger: IntelligenceSessionLedger | null;
  move: IntelligenceNextTrustworthyMove | null;
  learning: boolean;
}) {
  const observations = exactOvalMechanismObservations(report);
  const opportunities = exactOvalOpportunities(report);
  const driverFocus = report.driver_focus
    && report.driver_focus.run_id === report.run_id
    && report.driver_focus.authority === "driver_coaching_only"
    ? report.driver_focus
    : null;
  const coachingFocus = driverFocus?.status === "ready"
    && driverFocus.blocker_reasons.length === 0
    && driverFocus.focus
    && driverFocus.focus.setup_authorized === false
    && driverFocus.focus.citations.some((citation) => citation.run_id === report.run_id)
    ? driverFocus.focus
    : null;
  const latestCurrentRunChange = ledger
    ? [...ledger.entries].reverse().find((entry) => entry.test_run_id === report.run_id) ?? null
    : null;
  const recoveryItem = report.measurement_debt?.items[0] ?? null;
  const hasCornerEvidence = observations.length > 0
    || opportunities.length > 0
    || coachingFocus != null;
  if (!hasCornerEvidence) return null;

  return (
    <section
      className="engineer-smart-card engineer-oval-crew-board"
      data-authority="read-only-synthesis"
      aria-labelledby="engineer-oval-crew-board-heading"
    >
      <header>
        <Route size={16} aria-hidden="true" />
        <div>
          <span className="eyebrow">Corner-cycle crew board</span>
          <h3 id="engineer-oval-crew-board-heading">Entry → center → exit → carry</h3>
        </div>
        <span className="engineer-smart-authority">Observation + coaching only</span>
      </header>
      <ol className="engineer-smart-list engineer-smart-grid oval-crew-phase-strip" aria-label="Qualified corner-cycle evidence">
        {OVAL_CREW_PHASES.map((phase) => {
          const observation = observations.find((item) => ovalCrewPhase(item.phase) === phase.key) ?? null;
          const opportunity = opportunities.find((item) => ovalCrewPhase(item.phase) === phase.key) ?? null;
          const coaching = coachingFocus && ovalCrewPhase(coachingFocus.phase) === phase.key
            ? coachingFocus
            : null;
          const state = observation ? "observed" : opportunity ? "repeatable" : coaching ? "coaching" : "no_finding";
          return (
            <li key={phase.key} data-phase={phase.key} data-state={state}>
              <span className="oval-crew-phase-label">{phase.label}<small>{phase.cue}</small></span>
              {observation ? (
                <>
                  <strong>{sentenceLabel(observation.mechanism)}</strong>
                  <span>{observation.summary}</span>
                  <small>
                    {sentenceLabel(observation.phase ?? phase.key)} · {percent(observation.lap_pct_start)}–{percent(observation.lap_pct_end)} · {observation.repetition_count} repetition{observation.repetition_count === 1 ? "" : "s"}
                  </small>
                  <small>{sentenceLabel(observation.evidence_state)} · observation only</small>
                  {(observation.evidence_state === "estimated_proxy" || observation.mechanism === "resistance_scrub_like") && (
                    <small>Proxy/like evidence only · no aerodynamic force or coefficient is measured.</small>
                  )}
                </>
              ) : opportunity ? (
                <>
                  <strong>Repeatable time opportunity</strong>
                  <span>{seconds(opportunity.median_opportunity_s)} against {seconds(opportunity.empirical_noise_s)} empirical noise.</span>
                  <small>{percent(opportunity.lap_pct_start)}–{percent(opportunity.lap_pct_end)} · {opportunity.repetition_count} same-setup repetitions</small>
                </>
              ) : coaching ? (
                <>
                  <strong>Repeatability focus · {sentenceLabel(coaching.channel)}</strong>
                  <span>{coaching.instruction}</span>
                  <small>{percent(coaching.lap_pct_start)}–{percent(coaching.lap_pct_end)} · coaching only</small>
                </>
              ) : (
                <>
                  <strong>No qualified observation published</strong>
                  <span>Keep this phase ungraded until the producer publishes exact, eligible evidence.</span>
                </>
              )}
              {observation && opportunity && (
                <small>Repeatable window: {seconds(opportunity.median_opportunity_s)} vs {seconds(opportunity.empirical_noise_s)} noise.</small>
              )}
              {observation && coaching && <small>Coaching focus: {coaching.instruction}</small>}
              {learning && observation && <small>Channels: {observation.source_channels.join(" · ")}</small>}
              {learning && opportunity && !observation && <small>Channels: {opportunity.source_channels.join(" · ")}</small>}
            </li>
          );
        })}
      </ol>
      <div className="oval-crew-repeatability" data-state={driverFocus?.status ?? "unavailable"}>
        <span className="eyebrow">Corner repeatability</span>
        {coachingFocus ? (
          <>
            <strong>{coachingFocus.instruction}</strong>
            <p><strong>Success check:</strong> {coachingFocus.success_check}</p>
            <small>{driverFocus?.eligible_lap_count ?? 0} eligible same-setup laps · driver coaching only</small>
          </>
        ) : driverFocus?.status === "no_finding" ? (
          <p>No driver coaching focus currently outranks the setup signal on qualified same-setup laps.</p>
        ) : driverFocus?.status === "blocked" ? (
          <p>The repeatability comparison is blocked by its evidence contract.</p>
        ) : (
          <p>No same-setup driver repeatability report is available for this run.</p>
        )}
        {learning && driverFocus && driverFocus.channel_repeatability.length > 0 && (
          <small>
            Median position-aligned spread: {driverFocus.channel_repeatability.map((item) => (
              `${sentenceLabel(item.channel)} ${item.median_robust_spread.toFixed(2)} ${item.unit}`
            )).join(" · ")}
          </small>
        )}
      </div>
      <div className="engineer-smart-grid oval-crew-change-grid">
        <article data-kind="what-changed" data-state={latestCurrentRunChange?.state ?? "unavailable"}>
          <span className="eyebrow">What changed</span>
          {latestCurrentRunChange ? (
            <>
              <strong>{sentenceLabel(latestCurrentRunChange.state)}{latestCurrentRunChange.delta_s != null ? ` · ${seconds(latestCurrentRunChange.delta_s)}` : ""}</strong>
              <p>{latestCurrentRunChange.description}</p>
              {learning && latestCurrentRunChange.setup_changes.length > 0 && (
                <small>{latestCurrentRunChange.setup_changes.length} recorded setup difference{latestCurrentRunChange.setup_changes.length === 1 ? "" : "s"} · causal attribution withheld</small>
              )}
            </>
          ) : <p>No evidence-qualified current-run change is published.</p>}
        </article>
        <article data-kind="check-next" data-authority={move?.authority ?? (recoveryItem ? "recovery_only" : "withheld")}>
          <span className="eyebrow">What to check next</span>
          {move ? (
            <>
              <strong>{move.title}</strong>
              <p>{move.instruction}</p>
              <small>{move.authority === "setup_authorized" ? "Exact controlled-test target stays in Dial-In." : "Navigation only · no setup change"}</small>
            </>
          ) : recoveryItem ? (
            <>
              <strong>{recoveryItem.label}</strong>
              <p>{recoveryItem.reason}</p>
              <small>Evidence recovery only</small>
            </>
          ) : <p>No server-ranked next check is published.</p>}
        </article>
      </div>
      <small>Read-only crew synthesis. No setup direction is created here, and telemetry samples are not counted as independent experiments.</small>
    </section>
  );
}

function TelemetryHealthCard({
  report,
  learning,
  onOpenRecovery,
}: {
  report: IntelligenceTelemetryHealthReport;
  learning: boolean;
  onOpenRecovery: SmartIntelligenceCardsProps["onOpenRecovery"];
}) {
  const needsRecovery = report.status === "warning" || report.status === "blocked";
  const title = report.status === "healthy"
    ? `${report.assessed_channels.length} critical channels match trusted history`
    : report.status === "warning"
      ? `${report.findings.length} recording-health change${report.findings.length === 1 ? "" : "s"}`
      : report.status === "insufficient_history"
        ? "More trusted runs are needed"
        : "Telemetry health is blocked";
  const recoveryAction = report.recovery[0]?.action
    ?? report.findings[0]?.recovery.action
    ?? null;
  const recoveryActionLabel = recoveryAction === "reimport_original_ibt"
    ? "Re-import original .ibt"
    : recoveryAction === "record_verification_run"
      ? "Record verification run"
      : "Review recording recovery";
  return (
    <section
      className="engineer-smart-card engineer-telemetry-health"
      data-state={report.status === "warning" ? "attention" : report.status}
      data-authority="measurement-health-only"
    >
      <header>
        {needsRecovery
          ? <AlertTriangle size={16} aria-hidden="true" />
          : <ShieldCheck size={16} aria-hidden="true" />}
        <div><span className="eyebrow">Cross-run telemetry health</span><h3>{title}</h3></div>
        <span className="engineer-smart-authority">Measurement health only</span>
      </header>
      {report.findings.length > 0 && (
        <ul className="engineer-smart-list">
          {report.findings.slice(0, learning ? 5 : 2).map((finding) => (
            <li key={finding.finding_id} data-state="warning">
              <strong>{sentenceLabel(finding.kind)} · {finding.channel}</strong>
              <span>{finding.observation}</span>
              {learning && <small>Compared with {finding.baseline_run_ids.length} exact compatible runs.</small>}
            </li>
          ))}
        </ul>
      )}
      {report.blocker_reasons.length > 0 && (
        <ul className="engineer-smart-blockers">
          {report.blocker_reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}
      {recoveryAction && (
        <button type="button" onClick={() => onOpenRecovery("overview", "retry_resource")}>
          {recoveryActionLabel} <ArrowRight size={12} aria-hidden="true" />
        </button>
      )}
      <small>Recording health can request a re-import or verification run. It never diagnoses a vehicle cause or authorizes a setup change.</small>
    </section>
  );
}

function MechanismCard({ report, learning }: { report: RunIntelligenceReport; learning: boolean }) {
  const mechanismReport = report.mechanism_observations;
  if (!mechanismReport || mechanismReport.run_id !== report.run_id || mechanismReport.authority !== "observation_only") return null;
  const observations = mechanismReport.observations.filter((observation) => (
    observation.run_id === report.run_id
    && observation.authority === "observation_only"
    && observation.qualified
    && observation.blocker_reasons.length === 0
  ));
  return (
    <section className="engineer-smart-card" data-state={observations.length > 0 ? "ready" : mechanismReport.status}>
      <header><Activity size={16} aria-hidden="true" /><div><span className="eyebrow">Typed mechanism evidence</span><h3>{observations.length > 0 ? `${observations.length} qualified observation${observations.length === 1 ? "" : "s"}` : "No qualified mechanism observation"}</h3></div><span className="engineer-smart-authority">Observation only</span></header>
      {observations.length > 0 ? (
        <ul className="engineer-smart-list">
          {observations.slice(0, learning ? 5 : 2).map((observation) => (
            <li key={observation.observation_id}>
              <strong>{sentenceLabel(observation.mechanism)}{observation.phase ? ` · ${sentenceLabel(observation.phase)}` : ""}</strong>
              <span>{observation.summary}</span>
              <small>
                {observation.lap_number != null ? `Lap ${observation.lap_number}` : "Run evidence"}
                {observation.lap_pct_start != null && observation.lap_pct_end != null ? ` · ${percent(observation.lap_pct_start)}–${percent(observation.lap_pct_end)}` : ""}
                {` · ${sentenceLabel(observation.evidence_state)}`}
              </small>
              {learning && observation.supporting_evidence.length > 0 && <small>Supports: {observation.supporting_evidence.join(" · ")}</small>}
              {learning && observation.contradicting_evidence.length > 0 && <small>Contradicts: {observation.contradicting_evidence.join(" · ")}</small>}
            </li>
          ))}
        </ul>
      ) : <p>{mechanismReport.status === "blocked" ? "Mechanism typing is blocked by its declared evidence contract." : "No typed mechanism repeated strongly enough to publish."}</p>}
      <small>Mechanism observations describe measured behavior. They do not create a setup target.</small>
    </section>
  );
}

function AnomalyCard({ report, learning }: { report: IntelligenceAnomalyReport; learning: boolean }) {
  const visible = report.anomalies.filter((anomaly) => (
    anomaly.run_id === report.run_id
    && anomaly.authority === "observation_only"
    && anomaly.blocker_reasons.length === 0
  ));
  return (
    <section className="engineer-smart-card" data-state={visible.length > 0 ? "attention" : report.status}>
      <header><AlertTriangle size={16} aria-hidden="true" /><div><span className="eyebrow">Same-setup anomaly envelope</span><h3>{visible.length > 0 ? `${visible.length} sustained deviation${visible.length === 1 ? "" : "s"}` : "No sustained deviation published"}</h3></div><span className="engineer-smart-authority">Cause unassigned</span></header>
      {visible.length > 0 ? (
        <ul className="engineer-smart-list">
          {visible.slice(0, learning ? 4 : 2).map((anomaly) => (
            <li key={anomaly.anomaly_id}>
              <strong>Lap {anomaly.lap_number} · {sentenceLabel(anomaly.phase)}</strong>
              <span>{anomaly.channel} {sentenceLabel(anomaly.direction).toLowerCase()} · {percent(anomaly.lap_pct_start)}–{percent(anomaly.lap_pct_end)}</span>
              {learning && <small>Compared with L{anomaly.reference_lap_numbers.join(", L")} · {anomaly.telemetry_sample_count.toLocaleString()} samples</small>}
            </li>
          ))}
        </ul>
      ) : <p>Eligible same-setup laps did not produce a reportable sustained envelope deviation.</p>}
      <small>An anomaly says what was unexpected, not why it happened.</small>
    </section>
  );
}

function MeasurementDebtCard({
  debt,
  learning,
  onOpenRecovery,
}: {
  debt: IntelligenceMeasurementDebt;
  learning: boolean;
  onOpenRecovery: SmartIntelligenceCardsProps["onOpenRecovery"];
}) {
  const visibleItems = learning ? debt.items : debt.items.slice(0, 1);
  return (
    <section className="engineer-smart-card engineer-measurement-debt" data-state={debt.status} aria-labelledby="engineer-measurement-debt-heading">
      <header><ListChecks size={16} aria-hidden="true" /><div><span className="eyebrow">Measurement debt</span><h3 id="engineer-measurement-debt-heading">{debt.summary}</h3></div><span className="engineer-smart-authority">Recovery only</span></header>
      {debt.items.length > 0 ? (
        <ol className="engineer-recovery-list" aria-label="Evidence recovery order">
          {visibleItems.map((item, index) => {
            const target = trustedRecoveryTarget(item.recovery_kind, item.workspace);
            return (
              <li key={item.debt_id} data-priority={index + 1}>
                <div>
                  <small>Priority {index + 1} of {debt.items.length}</small>
                  <strong>{item.label}</strong>
                  <p>{item.reason}</p>
                  {learning && item.required_channels.length > 0 && <small>Required channels: {item.required_channels.join(" · ")}</small>}
                </div>
                {target && <button type="button" onClick={() => onOpenRecovery(target.workspace, target.kind)}>{recoveryLabel(target.kind)} in {workspaceLabel(item.workspace)} <ArrowRight size={12} aria-hidden="true" /></button>}
                {learning && item.blocker_reasons.length > 0 && <ul>{item.blocker_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
              </li>
            );
          })}
        </ol>
      ) : <p>No unresolved measurement requirement is attached to this run.</p>}
      {!learning && debt.items.length > visibleItems.length && (
        <small>{debt.items.length - visibleItems.length} lower-priority recovery item{debt.items.length - visibleItems.length === 1 ? "" : "s"} remain in Learning Mode.</small>
      )}
      <small>Recovery buttons navigate to evidence; they do not retry imports or run workflows automatically.</small>
    </section>
  );
}

function PreflightCard({
  report,
  learning,
  setupActionAuthorized,
  authorizedSetupAction,
  workflowRevision,
  onOpenRecovery,
}: Pick<SmartIntelligenceCardsProps, "report" | "learning" | "setupActionAuthorized" | "authorizedSetupAction" | "workflowRevision" | "onOpenRecovery">) {
  const preflight = report.test_preflight;
  if (!preflight || preflight.workflow_id !== workflowRevision.workflowId || !workflowRevision.workflowUpdatedAt) return null;
  const stageBSetupAuthorized = preflight.stage !== "B" || Boolean(
    setupActionAuthorized
    && authorizedSetupAction
    && trustedSetupAuthorizedMove(report.next_trustworthy_move, report.run_id, {
      ...workflowRevision,
      controlKey: authorizedSetupAction.controlKey,
      sourceEventIds: authorizedSetupAction.sourceEventIds,
    }),
  );
  const stageIndex = preflight.stage === "complete"
    ? preflight.status === "complete" ? PREFLIGHT_PROGRESS_STAGES.length : PREFLIGHT_PROGRESS_STAGES.length - 1
    : PREFLIGHT_PROGRESS_STAGES.indexOf(preflight.stage);
  const orderedChecks = [...preflight.checks].sort((left, right) => {
    const priority = { blocked: 0, required: 1, verified: 2 } as const;
    return priority[left.state] - priority[right.state];
  });
  const verifiedChecks = preflight.checks.filter((check) => check.state === "verified").length;
  const visibleChecks = orderedChecks.slice(0, learning ? orderedChecks.length : 4);
  const actionLabel = preflight.stage === "complete"
    ? preflight.status === "complete" ? "Review controlled verdict" : "Compare and score A/B/A2"
    : `Prepare ${preflightStageLabel(preflight.stage)}`;
  if (!stageBSetupAuthorized) {
    return (
      <section className="engineer-smart-card engineer-preflight" data-state="blocked" data-stage="B" data-authority="withheld" aria-labelledby="engineer-preflight-heading">
        <header><ClipboardCheck size={16} aria-hidden="true" /><div><span className="eyebrow">Controlled-test preflight · One change B</span><h3 id="engineer-preflight-heading">Stage B authority needs review</h3></div><span className="engineer-smart-authority">Setup withheld</span></header>
        <p>The current source-run report, workflow revision, and qualified evidence do not agree. The stored Stage B target and all action-bearing preflight prose remain hidden.</p>
        <button type="button" onClick={() => onOpenRecovery("dial_in", "resume_workflow")}>Review or rebuild in Dial-In <ArrowRight size={12} aria-hidden="true" /></button>
        <small>Progress is retained for audit. Do not record Stage B until the current card is authorized again.</small>
      </section>
    );
  }
  return (
    <section className="engineer-smart-card engineer-preflight" data-state={preflight.status} data-stage={preflight.stage} aria-labelledby="engineer-preflight-heading">
      <header><ClipboardCheck size={16} aria-hidden="true" /><div><span className="eyebrow">Controlled-test preflight · {preflightStageLabel(preflight.stage)}</span><h3 id="engineer-preflight-heading">{preflight.title}</h3></div><span className="engineer-smart-authority">{verifiedChecks}/{preflight.checks.length} checks clear</span></header>
      <ol className="engineer-mission-progress" aria-label="Controlled-test mission progress">
        {PREFLIGHT_PROGRESS_STAGES.map((stage, index) => {
          const complete = index < stageIndex || preflight.status === "complete";
          const current = index === stageIndex && preflight.status !== "complete";
          return (
            <li key={stage} data-state={complete ? "complete" : current ? "current" : "upcoming"} aria-current={current ? "step" : undefined}>
              <span>{complete ? <CheckCircle2 size={12} aria-hidden="true" /> : index + 1}</span>
              <strong>{preflightStageLabel(stage)}</strong>
              <small>{complete ? "Recorded" : current ? "Now" : "Later"}</small>
            </li>
          );
        })}
      </ol>
      <ul className="engineer-check-list" aria-label="Current stage checklist">
        {visibleChecks.map((check) => (
          <li key={check.check_id} data-state={check.state}>
            {check.state === "verified" ? <CheckCircle2 size={13} aria-hidden="true" /> : <AlertTriangle size={13} aria-hidden="true" />}
            <span><strong>{check.label}</strong>{(learning || check.state !== "verified") && <small>{check.detail}</small>}</span>
          </li>
        ))}
      </ul>
      {preflight.blocker_reasons.length > 0 && <ul className="engineer-smart-blockers">{preflight.blocker_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
      <button type="button" onClick={() => onOpenRecovery("dial_in", "resume_workflow")}>{actionLabel} <ArrowRight size={12} aria-hidden="true" /></button>
      <small>Preflight reports workflow readiness. Only the server-owned Dial-In card can authorize or advance the test.</small>
    </section>
  );
}

function SessionLedgerCard({ ledger, learning }: { ledger: IntelligenceSessionLedger; learning: boolean }) {
  return (
    <section className="engineer-smart-card engineer-session-ledger" data-state={ledger.status}>
      <header><History size={16} aria-hidden="true" /><div><span className="eyebrow">Session engineering ledger</span><h3>{ledger.entries.length > 0 ? `${ledger.entries.length} evidence-qualified change${ledger.entries.length === 1 ? "" : "s"}` : "No comparable run change"}</h3></div><span className="engineer-smart-authority">Observation only</span></header>
      {ledger.entries.length > 0 ? (
        <ul className="engineer-smart-list">
          {ledger.entries.slice(0, learning ? 6 : 3).map((entry) => (
            <li key={entry.entry_id} data-state={entry.state}>
              <strong>{sentenceLabel(entry.state)}{entry.delta_s != null ? ` · ${seconds(entry.delta_s)}` : ""}</strong>
              <span>{entry.description}</span>
              {learning && <small>{sentenceLabel(entry.evidence_scope)}{entry.phase ? ` · ${sentenceLabel(entry.phase)}` : ""} · never treated as a causal setup claim</small>}
            </li>
          ))}
        </ul>
      ) : <p>Runs in this session are not yet comparable on qualified evidence.</p>}
      {learning && ledger.blocker_reasons.length > 0 && <ul className="engineer-smart-blockers">{ledger.blocker_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
    </section>
  );
}

function HypothesisCard({ lifecycle, learning }: { lifecycle: IntelligenceHypothesisLifecycle; learning: boolean }) {
  const visible = lifecycle.entries.slice(0, learning ? 6 : 3);
  return (
    <section className="engineer-smart-card engineer-hypotheses" data-state={lifecycle.status}>
      <header><Lightbulb size={16} aria-hidden="true" /><div><span className="eyebrow">Controlled hypothesis memory</span><h3>{lifecycle.entries.length > 0 ? `${lifecycle.entries.length} graded hypothes${lifecycle.entries.length === 1 ? "is" : "es"}` : "No completed hypothesis"}</h3></div><span className="engineer-smart-authority">Controlled outcomes</span></header>
      {visible.length > 0 ? (
        <ul className="engineer-smart-list">
          {visible.map((entry) => (
            <li key={entry.workflow_id} data-state={entry.lifecycle_state}>
              <strong>{sentenceLabel(entry.lifecycle_state)}</strong>
              <span>{entry.hypothesis}</span>
              {entry.do_not_repeat && <em>Do not repeat{entry.do_not_repeat_reason ? ` · ${entry.do_not_repeat_reason}` : ""}</em>}
              {learning && <small>{entry.protocol.protocol_valid ? "Protocol valid" : "Protocol invalid"}{entry.protocol.evidence_score != null ? ` · evidence ${entry.protocol.evidence_score.toFixed(2)}` : ""} · {entry.target_effect.actual_effect_s != null ? seconds(entry.target_effect.actual_effect_s) : "effect not gradable"}</small>}
            </li>
          ))}
        </ul>
      ) : <p>Finish a valid A/B/A2 workflow before a hypothesis can become durable evidence.</p>}
      {lifecycle.do_not_repeat_hypothesis_fingerprints.length > 0 && (
        <p className="engineer-do-not-repeat"><ShieldCheck size={13} aria-hidden="true" /> {lifecycle.do_not_repeat_hypothesis_fingerprints.length} failed or invalid hypothesis fingerprint{lifecycle.do_not_repeat_hypothesis_fingerprints.length === 1 ? " is" : "s are"} blocked from casual repetition.</p>
      )}
    </section>
  );
}

function AttentionCard({
  items,
  runId,
  sessionId,
}: {
  items: IntelligenceAttentionItem[];
  runId: string;
  sessionId: string | null;
}) {
  const exactItems = useMemo(
    () => items.filter((item) => item.run_id === runId),
    [items, runId],
  );
  const key = attentionStorageKey(runId, sessionId);
  const fingerprintSet = useMemo(
    () => Object.fromEntries(exactItems.map((item) => [item.attention_id, item.fingerprint])),
    [exactItems],
  );
  const fingerprintSignature = useMemo(
    () => JSON.stringify(fingerprintSet),
    [fingerprintSet],
  );
  const [snapshot, setSnapshot] = useState<{ key: string; previous: AttentionSnapshot }>({
    key: "",
    previous: {},
  });
  const committedRevisionRef = useRef("");

  useEffect(() => {
    const revision = `${key}:${fingerprintSignature}`;
    if (committedRevisionRef.current === revision) return;
    const previous = readAttentionSnapshot(key);
    setSnapshot({ key, previous });
    committedRevisionRef.current = revision;
  }, [fingerprintSignature, key]);

  const markUpdatesSeen = () => {
    try {
      window.localStorage.setItem(key, fingerprintSignature);
    } catch {
      // Presentation memory is optional and never affects evidence or authority.
    }
    setSnapshot({ key, previous: fingerprintSet });
  };

  if (snapshot.key !== key) return null;
  const visible = exactItems.flatMap((item) => {
    const previous = snapshot.previous[item.attention_id];
    if (previous === item.fingerprint) return [];
    const state = previous == null ? "new" : item.state === "resolved" ? "resolved" : "changed";
    return [{ ...item, state }];
  });
  if (visible.length === 0) return null;

  return (
    <section className="engineer-smart-card engineer-attention" data-authority="presentation-only">
      <header>
        <Activity size={16} aria-hidden="true" />
        <div><span className="eyebrow">Changed since last view</span><h3>{visible.length} evidence update{visible.length === 1 ? "" : "s"}</h3></div>
        <span className="engineer-smart-authority">Presentation only</span>
      </header>
      <ul className="engineer-smart-list">
        {visible.slice(0, 4).map((item) => (
          <li key={item.attention_id} data-state={item.state}>
            <strong>{sentenceLabel(item.state)}</strong>
            <span>{item.label}</span>
            <small>{workspaceLabel(item.workspace)} · exact run scope</small>
          </li>
        ))}
      </ul>
      <button type="button" onClick={markUpdatesSeen}>
        Mark updates seen
      </button>
      <small>Seen state changes only this display. It never changes evidence, ranking, or setup authority.</small>
    </section>
  );
}

export function SmartIntelligenceCards(props: SmartIntelligenceCardsProps) {
  const {
    report,
    runId,
    sessionId,
    learning,
    setupActionAuthorized,
    authorizedSetupAction,
    workflowRevision,
    onOpenMove,
    onOpenRecovery,
  } = props;
  const candidateMove = report.next_trustworthy_move;
  const stageBActionWithheld = report.test_preflight?.stage === "B" && !setupActionAuthorized;
  const move = stageBActionWithheld
    ? null
    : candidateMove?.authority === "navigation_only"
    ? trustedNavigationMove(candidateMove, runId, workflowRevision) ? candidateMove : null
    : setupActionAuthorized && authorizedSetupAction && trustedSetupAuthorizedMove(
      candidateMove,
      runId,
      {
        ...workflowRevision,
        controlKey: authorizedSetupAction.controlKey,
        sourceEventIds: authorizedSetupAction.sourceEventIds,
      },
    ) ? candidateMove : null;
  const opportunity = opportunitySignature(report.opportunity_signature, runId);
  const anomalies = anomalyReport(report.anomalies, runId);
  const ledger = exactSessionLedger(report.session_ledger, sessionId);
  const lifecycle = exactHypothesisLifecycle(report.hypothesis_lifecycle, sessionId);
  const mindChangeCriteria = report.run_id === runId && (report.session_id ?? null) === sessionId
    ? exactMindChangeCriteria(
        report.mind_change_criteria,
        report.competing_causes,
        runId,
        sessionId,
      )
    : [];
  const telemetryHealth = report.telemetry_health
    && report.telemetry_health.current_run_id === runId
    && report.telemetry_health.session_id === sessionId
    && report.telemetry_health.authority === "measurement_health_only"
    && report.telemetry_health.setup_authorized === false
    && report.telemetry_health.vehicle_cause_attributed === false
    ? report.telemetry_health
    : null;
  const disclosureKey = "racelab:smart-disclosure:v1";
  const [supportingDetailOpen, setSupportingDetailOpen] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      return window.localStorage.getItem(disclosureKey) === "open";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(disclosureKey, supportingDetailOpen ? "open" : "closed");
    } catch {
      // Presentation preference is optional and cannot alter evidence.
    }
  }, [supportingDetailOpen]);
  const hasStructuredIntelligence = Boolean(
    move
    || opportunity.signature
    || opportunity.report
    || report.mechanism_observations
    || report.driver_focus
    || anomalies
    || report.measurement_debt
    || (
      report.test_preflight
      && report.test_preflight.workflow_id === workflowRevision.workflowId
      && workflowRevision.workflowUpdatedAt
    )
    || ledger
    || lifecycle
    || mindChangeCriteria.length > 0
    || telemetryHealth
    || (report.attention_items?.length ?? 0) > 0
  );
  if (!hasStructuredIntelligence) return null;
  const mission = missionStagePresentation(stageBActionWithheld ? "measure" : report.mission_stage, learning);
  const hasRecoveryQueue = Boolean(
    (report.attention_items?.length ?? 0) > 0
    || (report.measurement_debt?.items.length ?? 0) > 0
    || (telemetryHealth && ["warning", "blocked"].includes(telemetryHealth.status))
  );
  return (
    <section className="engineer-smart-layer" data-mission-stage={mission.stage ?? "unassigned"} aria-labelledby="engineer-smart-layer-heading">
      <header className="engineer-smart-layer-heading engineer-mission-command">
        <div>
          <span className="eyebrow">{mission.position ? `Mission stage ${mission.position} of ${MISSION_STAGES.length}` : "Evidence compounding"}</span>
          <h2 id="engineer-smart-layer-heading">{mission.title}</h2>
          <p>{mission.detail}</p>
        </div>
        {mission.stage && <span aria-label={`Current mission stage: ${sentenceLabel(mission.stage)}`}>{sentenceLabel(mission.stage)}</span>}
      </header>
      <div className="engineer-smart-grid engineer-smart-primary">
        {move && <NextMoveCard move={move} runId={runId} workflowRevision={workflowRevision} learning={learning} onOpen={onOpenMove} />}
        <PreflightCard
          report={report}
          learning={learning}
          setupActionAuthorized={setupActionAuthorized}
          authorizedSetupAction={authorizedSetupAction}
          workflowRevision={workflowRevision}
          onOpenRecovery={onOpenRecovery}
        />
      </div>
      <MindChangeCriteriaCard
        criteria={mindChangeCriteria}
        learning={learning}
        headingId="engineer-report-mind-change-heading"
        scopeLabel="Current run"
      />
      <OvalCrewBoard report={report} ledger={ledger} move={move} learning={learning} />
      {hasRecoveryQueue && <div className="engineer-smart-section-label"><span>Recovery queue</span><small>Clear the first evidence blocker, then reassess.</small></div>}
      <div className="engineer-smart-grid engineer-smart-recovery">
        {report.attention_items && (
          <AttentionCard
            items={report.attention_items}
            runId={runId}
            sessionId={sessionId}
          />
        )}
        {report.measurement_debt && <MeasurementDebtCard debt={report.measurement_debt} learning={learning} onOpenRecovery={onOpenRecovery} />}
        {telemetryHealth && ["warning", "blocked"].includes(telemetryHealth.status) && (
          <TelemetryHealthCard report={telemetryHealth} learning={learning} onOpenRecovery={onOpenRecovery} />
        )}
      </div>
      {learning ? (
        <div className="engineer-smart-grid engineer-smart-supporting">
          <OpportunityCard signature={opportunity.signature} report={opportunity.report} learning />
          <MechanismCard report={report} learning />
          <DriverFocusCard report={report} learning />
          {anomalies && <AnomalyCard report={anomalies} learning />}
          {ledger && <SessionLedgerCard ledger={ledger} learning />}
          {lifecycle && <HypothesisCard lifecycle={lifecycle} learning />}
          {telemetryHealth && !["warning", "blocked"].includes(telemetryHealth.status) && (
            <TelemetryHealthCard report={telemetryHealth} learning onOpenRecovery={onOpenRecovery} />
          )}
        </div>
      ) : (
        <details
          className="engineer-smart-disclosure"
          open={supportingDetailOpen}
          onToggle={(event) => setSupportingDetailOpen(event.currentTarget.open)}
        >
          <summary>Supporting verified intelligence</summary>
          <div className="engineer-smart-grid engineer-smart-supporting">
            <OpportunityCard signature={opportunity.signature} report={opportunity.report} learning={false} />
            <MechanismCard report={report} learning={false} />
            <DriverFocusCard report={report} learning={false} />
            {anomalies && <AnomalyCard report={anomalies} learning={false} />}
            {ledger && <SessionLedgerCard ledger={ledger} learning={false} />}
            {lifecycle && <HypothesisCard lifecycle={lifecycle} learning={false} />}
            {telemetryHealth && !["warning", "blocked"].includes(telemetryHealth.status) && (
              <TelemetryHealthCard report={telemetryHealth} learning={false} onOpenRecovery={onOpenRecovery} />
            )}
          </div>
          <button
            type="button"
            className="engineer-smart-reset"
            onClick={() => setSupportingDetailOpen(false)}
          >
            Reset compact view
          </button>
          <small>This display preference never changes evidence, ranking, or setup authority.</small>
        </details>
      )}
    </section>
  );
}
