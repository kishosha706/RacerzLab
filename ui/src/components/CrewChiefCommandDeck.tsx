import { useEffect, useRef, useState } from "react";
import { BrainCircuit, CheckCircle2, CircleHelp, Play, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

import {
  answerCrewChiefQuestion,
  abandonCrewChiefInvestigation,
  advanceCrewChiefInvestigation,
  fetchCrewChiefWorkspace,
  openCrewChiefInvestigation,
  rebaseCrewChiefInvestigation,
  updateCrewChiefObjective,
} from "../api/client";
import type { CrewChiefEvidenceEntry, CrewChiefWorkspace, EngineeringObjective } from "../types/crewChief";
import type { LearningEvidenceReference } from "../types/engineeringLearning";
import type {
  InvestigationDecision,
  InvestigationImprovementProjection,
} from "../types/investigationImprovement";
import type { RunIntelligenceReport } from "../types/intelligence";
import { VehicleDynamicsBlackboard } from "./VehicleDynamicsBlackboard";
import { EngineeringKnowledgeSpine } from "./EngineeringKnowledgeSpine";

type Props = {
  runId: string;
  sessionId: string;
  report: RunIntelligenceReport;
  scopeRunIds: readonly string[];
  learning: boolean;
  onFocusEvidence: (entry: CrewChiefEvidenceEntry | LearningEvidenceReference) => void;
};

const objectives: Array<[EngineeringObjective, string]> = [
  ["race_long_run", "Race long run"],
  ["qualifying_peak", "Qualifying peak"],
  ["tire_conservation", "Tire conservation"],
  ["driver_confidence", "Driver confidence"],
  ["traffic_robustness", "Traffic robustness"],
  ["superspeedway_stability", "Superspeedway stability"],
  ["fuel_strategy", "Fuel strategy"],
];

const evidenceStateOrder: readonly CrewChiefEvidenceEntry["evidence_state"][] = [
  "measured",
  "controlled_test_effect",
  "calculated",
  "estimated_proxy",
  "observed_correlation",
  "needs_confirmation",
  "blocked_by_context",
  "unavailable",
];

function humanize(value: string): string {
  return value.replace(/_/g, " ");
}

function sentenceFragment(value: string): string {
  return value.trim().replace(/[.!?]+$/, "");
}

function evidenceStateSummary(entries: readonly CrewChiefEvidenceEntry[]): string {
  const counts = new Map<CrewChiefEvidenceEntry["evidence_state"], number>();
  for (const entry of entries) counts.set(entry.evidence_state, (counts.get(entry.evidence_state) ?? 0) + 1);
  const summary = evidenceStateOrder.flatMap((state) => {
    const count = counts.get(state) ?? 0;
    return count > 0 ? [`${count} ${humanize(state)}`] : [];
  });
  return summary.join(" · ") || "No current-scope evidence states published";
}

function contextClearedLapSummary(cleared: number, required: number | null): string {
  if (required != null) return `${cleared} context-cleared · ${required} mission target`;
  return `${cleared} context-cleared lap${cleared === 1 ? "" : "s"}`;
}

type EvidenceSourceSummary = {
  lap_numbers: readonly number[];
  lap_pct_start: number | null;
  lap_pct_end: number | null;
  phase: string | null;
  evidence_state: CrewChiefEvidenceEntry["evidence_state"];
};

function compactPercent(value: number): string {
  return Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1);
}

function evidenceSourceLabel(source: EvidenceSourceSummary): string {
  const laps = source.lap_numbers.length === 1
    ? `Lap ${source.lap_numbers[0]}`
    : source.lap_numbers.length > 1
      ? `Laps ${source.lap_numbers.join(", ")}`
      : "Run scope";
  const parts = [laps];
  if (source.phase) parts.push(humanize(source.phase));
  if (source.lap_pct_start != null && source.lap_pct_end != null) {
    parts.push(`${compactPercent(source.lap_pct_start)}–${compactPercent(source.lap_pct_end)}%`);
  }
  parts.push(humanize(source.evidence_state));
  return parts.join(" · ");
}

function investigationActionsDiffer(
  baseline: InvestigationDecision,
  memory: InvestigationDecision,
): boolean {
  return baseline.decision_kind !== memory.decision_kind
    || baseline.action_id !== memory.action_id
    || baseline.priority_tier !== memory.priority_tier
    || baseline.safe_reorder_group !== memory.safe_reorder_group
    || baseline.selected_ordinal !== memory.selected_ordinal;
}

function InvestigationMemoryRecords({
  label,
  openLabel,
  recordIds,
  evidenceReferences,
  onFocusEvidence,
}: {
  label: string;
  openLabel: string;
  recordIds: readonly string[];
  evidenceReferences: readonly LearningEvidenceReference[];
  onFocusEvidence: (reference: LearningEvidenceReference) => void;
}) {
  return (
    <div className="investigation-improvement-memory">
      <span>{label}</span>
      {recordIds.length > 0 ? <ul>{recordIds.map((recordId) => {
        const reference = evidenceReferences.find((item) => item.experience_id === recordId);
        return <li key={recordId}>
          <code>{recordId}</code>
          {reference?.state === "available" ? <button
            type="button"
            onClick={() => onFocusEvidence(reference)}
            aria-label={`Open P33 source · ${evidenceSourceLabel(reference.provenance)}`}
          >{openLabel}</button> : <small>{reference?.blocker_reasons[0] ?? "Trusted source link unavailable"}</small>}
        </li>;
      })}</ul> : <small>No P33 memory record IDs were accepted.</small>}
    </div>
  );
}

function InvestigationImprovementCard({
  projection,
  evidenceReferences,
  onFocusEvidence,
}: {
  projection: InvestigationImprovementProjection;
  evidenceReferences: readonly LearningEvidenceReference[];
  onFocusEvidence: (reference: LearningEvidenceReference) => void;
}) {
  const pair = projection.current_pair;
  const completedPair = projection.latest_completed_pair;
  const comparison = projection.latest_completed_comparison;
  const comparisonObservable = comparison != null
    && ["directly_observed", "counterfactual_observable"].includes(comparison.observability);
  const qualifiedDiscriminatorAdvance = comparison != null
    && comparison.qualified
    && comparison.observability === "counterfactual_observable"
    && comparison.bounded_reorder_observed
    && comparison.bounded_discriminator_step_advance === 1;
  const completedDecisionsDiffer = completedPair != null && investigationActionsDiffer(
    completedPair.baseline_decision,
    completedPair.memory_decision,
  );
  const stateLabel = humanize(projection.memory_policy_state);
  const productionLabel = humanize(projection.production_policy);
  const qualifiedCases = projection.readiness.qualified_historical_investigations
    + projection.readiness.qualified_prospective_investigations;
  const readinessDeficits = [
    ["Historical investigations", projection.readiness.historical_deficit],
    ["Prospective investigations", projection.readiness.prospective_deficit],
    ["Exact recurrence", projection.readiness.exact_recurrence_deficit],
    ["Compatible recurrence", projection.readiness.compatible_recurrence_deficit],
    ["Contexts", projection.readiness.context_deficit],
    ["Problem families", projection.readiness.problem_family_deficit],
    ["Objectives", projection.readiness.objective_deficit],
  ] as const;
  const remainingDeficits = readinessDeficits.filter(([, count]) => count > 0);
  const blockers = [...new Set([
    ...projection.safety_blockers,
    ...projection.readiness.blockers,
  ])];
  return (
    <section
      className="investigation-improvement"
      data-state={projection.state}
      data-outcome={projection.latest_outcome_status ?? projection.current_pair_status ?? "none"}
      aria-label="Investigation Improvement, read only"
    >
      <header>
        <div>
          <span className="eyebrow">INVESTIGATION IMPROVEMENT / READ ONLY</span>
          <h3>{pair
            ? "Frozen baseline versus memory attention"
            : comparison
              ? "Latest completed paired evaluation"
              : "Paired evaluation unavailable"}</h3>
        </div>
        <span className="investigation-improvement-state">{stateLabel}</span>
      </header>
      <p>{projection.difference_explanation}</p>
      <p className="investigation-improvement-policy">
        <b>Active production policy</b> {productionLabel} / {stateLabel}.
      </p>
      <p className="investigation-improvement-policy">
        <b>Gate evaluation</b> {humanize(projection.readiness.evaluation_decision)}. <b>Effective now</b> {humanize(projection.readiness.activation_decision)}.
      </p>
      {pair ? (
        <div className="investigation-improvement-decisions" aria-label="Frozen paired investigation decisions">
          <article>
            <span>BASELINE NEXT</span>
            <strong>{humanize(pair.baseline_decision.action_id)}</strong>
            <small>{humanize(pair.baseline_decision.priority_tier)}</small>
          </article>
          <article>
            <span>MEMORY NEXT / {stateLabel}</span>
            <strong>{humanize(pair.memory_decision.action_id)}</strong>
            <small>{projection.decisions_differ ? "Different executable action" : "Same executable action"}</small>
          </article>
        </div>
      ) : (
        <p className="investigation-improvement-unobservable">
          No current frozen pair is available. No current investigation benefit is inferred.
        </p>
      )}
      {pair && projection.decisions_differ && (
        <InvestigationMemoryRecords
          label={`Transfer / ${humanize(projection.context_transfer_class)}`}
          openLabel="Open source"
          recordIds={projection.memory_evidence_record_ids}
          evidenceReferences={evidenceReferences}
          onFocusEvidence={onFocusEvidence}
        />
      )}
      {pair && (
        <p className="investigation-improvement-observability">
          <b>Current frozen pair</b> {humanize(projection.current_pair_status ?? "pending")}; pre-outcome only. A different shadow action is not evidence that it saves time, laps, or investigation steps.
        </p>
      )}
      {comparison && completedPair && (
        <article className="investigation-improvement-comparison" aria-label="Latest completed investigation comparison">
          <div>
            <span>Latest completed comparison</span>
            <strong>{humanize(comparison.observability)}</strong>
            <small>{comparison.qualified ? "Qualified evaluation record" : "Withheld from activation evidence"}</small>
          </div>
          <div className="investigation-improvement-completed-decisions">
            <small>Completed baseline / {humanize(completedPair.baseline_decision.action_id)}</small>
            <small>Completed memory / {humanize(completedPair.memory_decision.action_id)}</small>
            <small>{completedDecisionsDiffer ? "Different executable action" : "Same executable action"}</small>
          </div>
          {completedDecisionsDiffer && (
            <InvestigationMemoryRecords
              label={`Completed transfer / ${humanize(completedPair.context_transfer_class)}`}
              openLabel="Open source"
              recordIds={completedPair.memory_records_consulted}
              evidenceReferences={evidenceReferences}
              onFocusEvidence={onFocusEvidence}
            />
          )}
          <p>{comparisonObservable
            ? pair
              ? "Its outcome is certificate-bound historical evidence and does not establish a benefit for the current decision."
              : "Its observed outcome is certificate-bound historical evidence; it does not authorize a setup or policy change."
            : "Its counterfactual outcome is unobservable; no time, lap, or investigation-step saving is inferred."}</p>
          {qualifiedDiscriminatorAdvance && (
            <p className="investigation-improvement-observed">
              <b>Qualified observed discriminator timing</b> The frozen memory order reached one useful discriminator position earlier. This is a localized ordering observation, not a time, lap, terminal-path, or setup benefit.
            </p>
          )}
          {comparison.blockers.length > 0 && (
            <ul>{comparison.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
          )}
        </article>
      )}
      {!pair && !comparison && (
        <p className="investigation-improvement-observability">
          <b>Outcome observability</b> unavailable. A different shadow action is not evidence that it saves time, laps, or investigation steps.
        </p>
      )}
      <div className="investigation-improvement-counts" aria-label="Investigation evaluation readiness">
        <span>Historical <strong>{projection.readiness.qualified_historical_investigations}</strong></span>
        <span>Prospective <strong>{projection.readiness.qualified_prospective_investigations}</strong></span>
        <span>Observable pairs <strong>{projection.readiness.observable_comparisons}</strong></span>
        <span>Safety <strong>{qualifiedCases === 0 || projection.readiness.observable_comparisons === 0
          ? "coverage incomplete"
          : projection.readiness.safety_gate_passed ? "0 violations" : "locked"}</strong></span>
        <span>Negative controls <strong>{projection.readiness.negative_controls_passed ? "gate met" : "locked"}</strong></span>
        <span>Subgroups <strong>{projection.readiness.subgroup_gate_passed ? "gate met" : "locked"}</strong></span>
      </div>
      {blockers[0] && <small className="investigation-improvement-blocker">Blocked: {blockers[0]}</small>}
      {projection.readiness.remaining_collection_missions.length > 0 && (
        <ul className="investigation-improvement-list investigation-improvement-next" aria-label="Next collection missions">
          {projection.readiness.remaining_collection_missions.slice(0, 3)
            .map((mission) => <li key={mission}>Next evidence: {mission}</li>)}
        </ul>
      )}
      {(remainingDeficits.length > 0
        || blockers.length > 0
        || projection.readiness.remaining_collection_missions.length > 0) && (
        <details className="investigation-improvement-audit">
          <summary>
            Full readiness audit / {remainingDeficits.length} deficits / {blockers.length} blockers / {projection.readiness.remaining_collection_missions.length} missions
          </summary>
          {remainingDeficits.length > 0 && <div>
            <b>Remaining evaluation deficits</b>
            <ul aria-label="Remaining evaluation deficits">
              {remainingDeficits.map(([label, count]) => <li key={label}>{label}: <strong>{count}</strong></li>)}
            </ul>
          </div>}
          {blockers.length > 0 && <div>
            <b>All blockers</b>
            <ul aria-label="Investigation improvement blockers">
              {blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
            </ul>
          </div>}
          {projection.readiness.remaining_collection_missions.length > 0 && <div>
            <b>All collection missions</b>
            <ul aria-label="Remaining collection missions">
              {projection.readiness.remaining_collection_missions.map((mission) => <li key={mission}>{mission}</li>)}
            </ul>
          </div>}
        </details>
      )}
      <footer>
        P19 authority unchanged / no setup authority / no client activation control. Frozen v1 still requires a qualified prospective trial that directly observes the memory path before terminal-path efficiency can be earned.
      </footer>
    </section>
  );
}

export function CrewChiefCommandDeck({ runId, sessionId, report, scopeRunIds, learning, onFocusEvidence }: Props) {
  const [workspace, setWorkspace] = useState<CrewChiefWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [driverReport, setDriverReport] = useState("");
  const [objective, setObjective] = useState<EngineeringObjective>("race_long_run");
  const workspaceSequence = useRef(0);

  useEffect(() => {
    const sequence = ++workspaceSequence.current;
    setWorkspace(null);
    setError(null);
    setBusy(true);
    void fetchCrewChiefWorkspace(runId, sessionId, report, { objective, scopeRunIds })
      .then((value) => { if (sequence === workspaceSequence.current) setWorkspace(value); })
      .catch((caught: unknown) => {
        if (sequence === workspaceSequence.current) {
          setError(caught instanceof Error ? caught.message : "Crew Chief unavailable.");
        }
      })
      .finally(() => { if (sequence === workspaceSequence.current) setBusy(false); });
    return () => {
      if (sequence === workspaceSequence.current) workspaceSequence.current += 1;
    };
  }, [objective, report, runId, scopeRunIds, sessionId]);

  const runMutation = async (operation: () => Promise<CrewChiefWorkspace>) => {
    const sequence = ++workspaceSequence.current;
    setBusy(true);
    setError(null);
    try {
      const value = await operation();
      if (sequence === workspaceSequence.current) setWorkspace(value);
    } catch (caught) {
      if (sequence === workspaceSequence.current) {
        setError(caught instanceof Error ? caught.message : "Crew Chief operation failed.");
      }
    } finally {
      if (sequence === workspaceSequence.current) setBusy(false);
    }
  };

  if (error && !workspace) {
    return <section className="crew-chief-deck crew-chief-error" role="alert"><b>Crew Chief withheld</b><p>{error}</p></section>;
  }
  if (!workspace) {
    return <section className="crew-chief-deck crew-chief-loading" aria-busy="true" aria-live="polite">
      <span className="eyebrow"><BrainCircuit size={13} aria-hidden="true" /> Crew Chief</span>
      <b>{busy ? "Binding current evidence" : "Crew Chief is waiting"}</b>
      <p>Checking the exact P19, P20, P26, P32, P33, P34, and P35 identities before showing a decision.</p>
    </section>;
  }

  const decision = workspace.terminal_decision;
  const investigationId = workspace.identity.investigation_id;
  const revision = workspace.identity.workspace_revision;
  const status = workspace.folded_state?.status;
  const performance = workspace.performance_intelligence;
  const memory = workspace.learning_prior;
  const story = performance.speed_story;
  const currentEvidenceEntries = workspace.evidence_index.entries.filter(
    (entry) => entry.producer_id !== "p33.engineering_experience",
  );
  const evidenceSummary = evidenceStateSummary(currentEvidenceEntries);
  const contextClearedLaps = contextClearedLapSummary(
    workspace.run_sentinel.context_cleared_laps,
    workspace.run_sentinel.required_laps,
  );
  const missionState = humanize(workspace.run_sentinel.mission_state);
  const missionAcceptance = workspace.run_sentinel.mission_acceptance_basis === "unbound"
    ? "Mission acceptance not established"
    : `${workspace.run_sentinel.mission_accepted_lap_ids.length} contract-accepted lap${workspace.run_sentinel.mission_accepted_lap_ids.length === 1 ? "" : "s"} · basis ${humanize(workspace.run_sentinel.mission_acceptance_basis)}`;
  const measurementAttempts = `${workspace.run_sentinel.measurement_attempt_ids.length} measurement attempt${workspace.run_sentinel.measurement_attempt_ids.length === 1 ? "" : "s"}`;
  const activeObjective = workspace.folded_state?.objective ?? objective;
  const toolEligibility = workspace.tool_eligibility ?? [];
  const activeEligibility = workspace.current_subgoal == null
    ? null
    : toolEligibility.find(
      (item) => item.tool_id === workspace.current_subgoal?.selected_tool,
    ) ?? null;
  const relevantTools = toolEligibility.filter((item) => item.currently_relevant);
  const driverInterpretations = workspace.folded_state?.driver_answer_interpretations ?? [];
  const latestDriverInterpretation = driverInterpretations.length
    ? driverInterpretations[driverInterpretations.length - 1]
    : null;
  const opportunityEvidence = new Map(
    workspace.evidence_index.entries
      .filter((item) => item.producer_id === "p32.lap_time_opportunity")
      .map((item) => [item.artifact_id, item]),
  );
  const memoryLine = memory.state === "available"
    ? memory.post_run_brief.what_we_learned[0]
      ?? memory.post_run_brief.next_attention[0]
      ?? memory.recurrence.statement
    : memory.blocker_reasons[0]
      ?? memory.post_run_brief.blocker_reasons[0]
      ?? "No qualified engineering history is available for this context.";
  const leadingDynamicsCandidate = workspace.vehicle_dynamics.candidates.find(
    (candidate) => candidate.relevance === "candidate",
  );
  const blockedDynamicsCandidate = workspace.vehicle_dynamics.candidates.find(
    (candidate) => candidate.relevance === "blocked",
  );
  const dynamicsBlocker = blockedDynamicsCandidate?.blocker_reasons[0]
    ?? workspace.vehicle_dynamics.blocker_reasons[0]
    ?? workspace.vehicle_dynamics.chain.flatMap((stage) => stage.blocker_reasons)[0]
    ?? "No typed current-scope vehicle-response evidence is available.";
  const dynamicsRaceState = leadingDynamicsCandidate
    ? "ready"
    : workspace.vehicle_dynamics.applicability_state === "ready"
      ? "blocked"
      : "unavailable";
  const dynamicsCandidateLabel = leadingDynamicsCandidate
    ? humanize(leadingDynamicsCandidate.mechanism_id.replace(/^mechanism:/, ""))
    : null;
  const dynamicsSignature = workspace.vehicle_dynamics.problem_signature ?? null;
  const dynamicsSignatureLine = dynamicsSignature
    ? `${dynamicsSignature.local_time_delta_s >= 0 ? "+" : ""}${dynamicsSignature.local_time_delta_s.toFixed(3)} s ${humanize(dynamicsSignature.phase)} begins at ${dynamicsSignature.onset_pct.toFixed(1)}% lap. Driver ${humanize(dynamicsSignature.driver_demand_state)}; vehicle response ${humanize(dynamicsSignature.vehicle_response_state)}. Contradiction: ${dynamicsSignature.strongest_contradiction}`
    : null;
  const dynamicsUnavailableReason = workspace.vehicle_dynamics.applicability_blockers[0];
  const dynamicsRaceLine = dynamicsRaceState === "ready"
    ? `${dynamicsSignatureLine ? `${dynamicsSignatureLine} ` : ""}Current evidence supports ${dynamicsCandidateLabel} as a mechanism candidate to inspect.`
    : dynamicsRaceState === "blocked"
      ? `${dynamicsSignatureLine ? `${dynamicsSignatureLine} ` : ""}${workspace.vehicle_dynamics.measured_time_consequence_available
        ? "Time loss is measured; vehicle mechanism remains unresolved."
        : "Vehicle mechanism remains unresolved."} ${sentenceFragment(dynamicsBlocker)}.`
      : `Vehicle-response evidence is unavailable in this scope${dynamicsUnavailableReason
        ? `: ${sentenceFragment(dynamicsUnavailableReason)}`
        : ""}.`;
  const dynamicsLearningLine = dynamicsRaceState === "ready"
    ? `A current mechanism candidate cleared the evidence screen. Follow its support, uncertainty, and discriminator below.`
    : dynamicsRaceState === "blocked"
      ? `${workspace.vehicle_dynamics.measured_time_consequence_available
        ? "The time loss is measured, but the vehicle mechanism is not isolated."
        : "The vehicle mechanism is not isolated."} ${workspace.vehicle_dynamics.next_discriminator_contract_id !== null
        ? "The blackboard shows the blocker and the next discriminator."
        : "The blackboard shows the blocker and the evidence still missing in this scope."}`
      : "Vehicle-response evidence is unavailable in this scope. The blackboard keeps the missing evidence explicit.";
  const evidenceLinks = (experienceIds: readonly string[]) => experienceIds.length ? (
    <div className="engineering-memory-evidence" aria-label="Historical telemetry evidence">
      {(() => {
        const references = memory.evidence_references.filter((item) => experienceIds.includes(item.experience_id));
        if (!references.length) return <small>Historical source navigation was not published for this memory.</small>;
        return references.map((reference) => reference.state === "available"
          ? <button
            type="button"
            key={reference.reference_id}
            onClick={() => onFocusEvidence(reference)}
            aria-label={`Open source · ${evidenceSourceLabel(reference.provenance)}`}
            title={`Technical provenance: ${reference.provenance.producer_id} · ${reference.provenance.artifact_id}`}
          ><b>Open source</b><span>{evidenceSourceLabel(reference.provenance)}</span></button>
          : <small key={reference.reference_id}>{reference.blocker_reasons.join(" ")}</small>);
      })()}
    </div>
  ) : null;
  const canStartFollowUp = status === "complete" || status === "abandoned";
  return (
    <section
      className="crew-chief-deck"
      data-mode={learning ? "learning" : "race"}
      data-authority={decision.authority}
      data-workspace-revision={revision}
      aria-labelledby="crew-chief-title"
    >
      <header>
        <div>
          <span className="eyebrow"><BrainCircuit size={13} aria-hidden="true" /> Autonomous Crew Chief</span>
          <h2 id="crew-chief-title">{decision.title}</h2>
        </div>
        <span className="crew-chief-authority"><ShieldCheck size={14} /> {decision.authority.replace(/_/g, " ")}</span>
      </header>

      <div className="crew-chief-race-brief speed-story" aria-label="Measured Speed Story">
        <p className="speed-story-next"><b>NEXT · P19</b> {story.next}</p>
        <p><b>OBSERVED · {story.observed_direction.toUpperCase()}</b> {story.what_costs_time}</p>
        <p><b>ATTRIBUTION</b> {story.attribution}</p>
        <p className="speed-story-contradiction"><b>STRONGEST CONTRADICTION</b> {story.strongest_contradiction}</p>
        {learning && <>
          <p><b>WHERE IT STARTS</b> {story.where_it_starts}</p>
          <p><b>WHAT CARRIES</b> {story.what_carries}</p>
          <p><b>DRIVER</b> {story.driver}</p>
          <p><b>CAR</b> {story.car}</p>
          <p><b>SYSTEMS</b> {story.systems}</p>
          <p><b>EVIDENCE STATES</b> {evidenceSummary} · {contextClearedLaps}</p>
        </>}
      </div>

      {!learning && (
        <div className="crew-chief-race-secondary">
          <p
            className="vehicle-dynamics-race-line"
            data-state={dynamicsRaceState}
            aria-label="Vehicle Dynamics, candidate mechanisms only"
          ><b>VEHICLE DYNAMICS · {dynamicsRaceState.toUpperCase()}</b> {dynamicsRaceLine}</p>
          <details className="speed-story-detail">
            <summary>Origin and carry</summary>
            <div>
              <p><b>WHERE IT STARTS</b> {story.where_it_starts}</p>
              <p><b>WHAT CARRIES</b> {story.what_carries}</p>
            </div>
          </details>
          <p
            className="speed-story-memory"
            data-learning-state={memory.state}
            aria-label="Engineering memory, attention only"
          ><b>MEMORY · ATTENTION ONLY</b> {memoryLine}</p>
        </div>
      )}

      {decision.kind === "controlled_test" && (
        <div className="crew-chief-exact-test">
          <b>Exact P19 controlled test</b>
          <span>{decision.control_key}: {decision.current_value} → {decision.proposed_value}</span>
          <small>Workflow {decision.workflow_id} · revision {decision.workflow_revision}</small>
        </div>
      )}

      {(!workspace.investigation || canStartFollowUp) ? (
        <div className="crew-chief-open">
          <label>Engineering objective
            <select value={objective} onChange={(event) => setObjective(event.target.value as EngineeringObjective)}>
              {objectives.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <label>Driver report
            <input value={driverReport} onChange={(event) => setDriverReport(event.target.value)} placeholder="Where and how does the car misbehave?" />
          </label>
          <button
            type="button"
            disabled={busy || driverReport.trim().length === 0}
            onClick={() => { void runMutation(() => openCrewChiefInvestigation(runId, sessionId, report, scopeRunIds, {
              driver_report: driverReport,
              expected_workspace_revision: revision,
              objective,
            })); }}
          ><Play size={14} /> {canStartFollowUp ? "Start follow-up investigation" : "Open investigation"}</button>
        </div>
      ) : workspace.pending_driver_question ? (
        <div className="crew-chief-question">
          <b><CircleHelp size={14} /> {workspace.pending_driver_question.question}</b>
          <p>{workspace.pending_driver_question.reason}</p>
          <div>{workspace.pending_driver_question.answer_options.map((answer) => (
            <button
              type="button"
              key={answer}
              disabled={busy}
              onClick={() => { void runMutation(() => answerCrewChiefQuestion(
                runId, sessionId, investigationId!, revision, answer, report, scopeRunIds,
                activeObjective,
              )); }}
            >{answer}</button>
          ))}</div>
        </div>
      ) : workspace.folded_state?.status === "open" ? (
        <div className="crew-chief-lifecycle">
          {workspace.current_subgoal && <p className="crew-chief-active-subgoal">
            <b>NEXT INSPECTION</b> {workspace.current_subgoal.title.replace(/^Inspect /, "")}
            {activeEligibility?.required_by_mandatory_gate && <small>Mandatory integrity/context gate</small>}
          </p>}
          <label>Investigation objective
            <select
              value={workspace.folded_state.objective}
              disabled={busy}
              onChange={(event) => { const next = event.target.value as EngineeringObjective; setObjective(next); void runMutation(() => updateCrewChiefObjective(
                runId, sessionId, investigationId!, revision, next, report, scopeRunIds,
              )); }}
            >{objectives.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select>
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => { void runMutation(() => advanceCrewChiefInvestigation(
              runId, sessionId, investigationId!, revision, report, scopeRunIds,
              activeObjective,
            )); }}
          ><Play size={14} /> {busy ? "Working the problem…" : workspace.current_subgoal ? "Work to next boundary" : "Continue to boundary"}</button>
          <button type="button" disabled={busy} onClick={() => { void runMutation(() => abandonCrewChiefInvestigation(
            runId, sessionId, investigationId!, revision, "Abandoned explicitly by driver.", report, scopeRunIds,
            activeObjective,
          )); }}><XCircle size={14} /> Abandon</button>
        </div>
      ) : null}

      {status === "stale" && investigationId && (
        <button type="button" disabled={busy} onClick={() => { void runMutation(() => rebaseCrewChiefInvestigation(
          runId, sessionId, investigationId, workspace.folded_state!.accepted_workspace_revision, report, scopeRunIds,
          activeObjective,
        )); }}><RefreshCw size={14} /> Rebase explicitly to current P19/P20/P26/P32 state</button>
      )}
      {error && workspace && (
        <button type="button" disabled={busy} onClick={() => { void runMutation(() => fetchCrewChiefWorkspace(
          runId, sessionId, report, { objective, scopeRunIds, investigationId },
        )); }}><RefreshCw size={14} /> Retry current investigation</button>
      )}

      {learning && (
        <div className="crew-chief-learning">
          <p
            className="vehicle-dynamics-learning-handoff"
            data-state={dynamicsRaceState}
            aria-label="Vehicle Dynamics learning handoff"
          ><b>MECHANISM HANDOFF · {dynamicsRaceState.toUpperCase()}</b> {dynamicsLearningLine}</p>
          <VehicleDynamicsBlackboard
            assessment={workspace.vehicle_dynamics}
            evidenceEntries={workspace.evidence_index.entries}
            p19Next={performance.explanation_chain.p19_next_move}
            onFocusEvidence={onFocusEvidence}
          />
          <EngineeringKnowledgeSpine
            projection={workspace.engineering_knowledge}
            evidenceEntries={workspace.evidence_index.entries}
            p19Next={workspace.terminal_decision}
            onFocusEvidence={(entry) => onFocusEvidence(entry)}
          />
          <InvestigationImprovementCard
            projection={workspace.investigation_improvement}
            evidenceReferences={workspace.learning_prior.evidence_references}
            onFocusEvidence={onFocusEvidence}
          />
          {memory.state === "available" ? <section className="engineering-memory" aria-label="Engineering Memory, attention only">
            <header>
              <div><span className="eyebrow">ENGINEERING MEMORY · ATTENTION ONLY</span><h3>{memory.recurrence.classification.replace(/_/g, " ")}</h3></div>
              <div className="engineering-memory-badges">
                <span>{memory.strength.replace(/_/g, " ")}</span>
                <span>{memory.context_transfer_level.replace(/_/g, " ")} transfer</span>
              </div>
            </header>

            <div className="engineering-memory-grid">
              <article>
                <h4>Recurrence</h4>
                <p>{memory.recurrence.statement}</p>
                <small>{memory.recurrence.counts.independent_episode_count} independent episodes · {memory.recurrence.counts.distinct_session_count} sessions</small>
                {memory.recurrence.useful_discriminator && <small>Useful discriminator: {memory.recurrence.useful_discriminator}</small>}
                {memory.recurrence.prior_dead_end && <small>Prior dead end: {memory.recurrence.prior_dead_end}</small>}
                {memory.recurrence.strongest_contradiction && <small>Contradiction: {memory.recurrence.strongest_contradiction}</small>}
              </article>

              <article>
                <h4>Context transfer</h4>
                <p>{memory.context_transfer_level.replace(/_/g, " ")}</p>
                {memory.context_transfers.length ? memory.context_transfers.slice(0, 4).map((item) => (
                  <small key={item.experience_id}>{item.level.replace(/_/g, " ")} · matches {item.matching_dimensions.join(", ") || "none"}{item.mismatched_dimensions.length ? ` · mismatches ${item.mismatched_dimensions.join(", ")}` : ""}{item.drift_reasons.length ? ` · drift ${item.drift_reasons.join("; ")}` : ""}{item.blocker_reasons.length ? ` · blocked ${item.blocker_reasons.join("; ")}` : ""}</small>
                )) : <small>No prior context cleared transfer.</small>}
              </article>

              <article>
                <h4>Driver fingerprint</h4>
                {memory.driver_tendencies.length ? memory.driver_tendencies.map((item) => (
                  <div key={item.fingerprint_id}>
                    <p>{item.state.replace(/_/g, " ")}</p>
                    {item.tendencies.map((tendency) => <div key={tendency.contribution_id}>
                      <small><b>{tendency.metric.replace(/_/g, " ")}</b> · {tendency.statement}</small>
                    </div>)}
                    {item.contradictions.map((contradiction) => <small key={contradiction}>Contradiction: {contradiction}</small>)}
                    {evidenceLinks(item.source_experience_ids)}
                  </div>
                )) : <p>No qualified driver tendency.</p>}
              </article>

              <article>
                <h4>Car response</h4>
                {memory.car_response_history.length ? memory.car_response_history.map((item) => (
                  <div key={item.fingerprint_id}>
                    <p>{item.statement}</p>
                    <small>{item.response.component} · historical {item.response.policy_verdict} · {item.response.p19_mechanism_assessment}</small>
                    {item.response.countereffects.map((countereffect) => <small key={countereffect}>Countereffect: {countereffect}</small>)}
                    {item.contradictions.map((contradiction) => <small key={contradiction}>Contradiction: {contradiction}</small>)}
                    {evidenceLinks(item.source_experience_ids)}
                  </div>
                )) : <p>No controlled car-response history cleared this context.</p>}
              </article>

              <article>
                <h4>Investigation effectiveness</h4>
                {memory.useful_prior_investigations.length ? memory.useful_prior_investigations.map((item) => (
                  <div key={item.outcome_id}>
                    <p>{item.explanation}</p>
                    <small>{item.outcome.terminal_decision.replace(/_/g, " ")} · {item.outcome.tool_steps_consumed} tool steps · {item.outcome.laps_consumed} laps</small>
                    {item.outcome.strongest_contradiction && <small>Contradiction: {item.outcome.strongest_contradiction}</small>}
                    {item.outcome.successful_discriminator_ids.length > 0 && <small>Useful discriminators: {item.outcome.successful_discriminator_ids.join(", ")}</small>}
                    {evidenceLinks([item.experience_id])}
                  </div>
                )) : <p>No prior investigation is qualified as useful here.</p>}
              </article>

              <article>
                <h4>Mind changes</h4>
                {memory.mind_change_history.length ? memory.mind_change_history.map((item) => (
                  <div key={item.fact.mind_change_id}>
                    <p>{item.statement}</p>
                    <small>{item.fact.causes_promoted.length} promoted · {item.fact.causes_demoted.length} demoted · {item.fact.causes_ruled_out.length} ruled out</small>
                    <small>{item.fact.evidence_discriminated ? "Evidence discriminated" : "No evidence discriminator"} · {item.fact.driver_question_involved ? "driver answer involved" : "no driver answer"} · {item.fact.controlled_evidence_involved ? "controlled evidence" : "observational evidence"}</small>
                    {evidenceLinks([item.experience_id])}
                  </div>
                )) : <p>No qualified P19 mind change is retained.</p>}
              </article>

              <article>
                <h4>Dead ends</h4>
                {memory.known_dead_ends.length ? memory.known_dead_ends.map((item) => (
                  <div key={item.fact.dead_end_id}>
                    <p>{item.fact.statement}</p>
                    <small>{item.fact.kind.replace(/_/g, " ")} · current evidence may override</small>
                    {evidenceLinks(item.experience_ids)}
                  </div>
                )) : <p>No qualified dead end is retained.</p>}
              </article>

              <article>
                <h4>Attention</h4>
                {memory.recommended_attention_order.length ? <ol>{memory.recommended_attention_order.map((item) => (
                  <li key={item.tool_id}><b>{item.learned_rank_within_band}. {item.tool_id}</b><small>{item.reason}</small></li>
                ))}</ol> : <p>Baseline safety order remains unchanged.</p>}
                <small>Attention only · P19 cause rank unchanged.</small>
              </article>

              <article>
                <h4>Learning ledger</h4>
                <p>{memory.ledger.investigations_resolved}/{memory.ledger.investigations_opened} investigations resolved · {memory.ledger.controlled_tests} controlled tests</p>
                <small>{memory.ledger.measurement_missions} measurement missions · {memory.ledger.questions_asked} driver questions · {memory.ledger.laps_consumed_before_resolution} laps consumed</small>
                <small>Keep {memory.ledger.keep_outcomes} · Undo {memory.ledger.undo_outcomes} · Retest {memory.ledger.retest_outcomes} · No-call {memory.ledger.no_call_outcomes}</small>
                <small>{memory.ledger.recurring_problem_count} recurring problems · {memory.ledger.recurrence_resolved_faster_count} resolved faster · {memory.ledger.driver_focus_outcomes} driver-focus outcomes</small>
                {memory.ledger.average_tool_steps_before_resolution != null && <small>Average {memory.ledger.average_tool_steps_before_resolution.toFixed(1)} tool steps before resolution.</small>}
                {memory.ledger.repeated_dead_end_tools.length > 0 && <small>Repeated dead-end tools: {memory.ledger.repeated_dead_end_tools.join(", ")}</small>}
                {memory.ledger.successful_discriminators.length > 0 && <small>Successful discriminators: {memory.ledger.successful_discriminators.join(", ")}</small>}
              </article>

              <article>
                <h4>Post-run brief</h4>
                {memory.post_run_brief.what_we_learned.map((item) => <p key={`learned:${item}`}><b>Learned</b> {item}</p>)}
                {memory.post_run_brief.what_changed_our_mind.map((item) => <p key={`changed:${item}`}><b>Changed our mind</b> {item}</p>)}
                {memory.post_run_brief.what_did_not_work.map((item) => <p key={`dead:${item}`}><b>Did not work</b> {item}</p>)}
                {memory.post_run_brief.next_attention.map((item) => <p key={`next:${item}`}><b>Next attention</b> {item}</p>)}
                {memory.post_run_brief.blocker_reasons.map((item) => <small key={`brief-blocker:${item}`}>{item}</small>)}
              </article>

              <article>
                <h4>Blockers / strength</h4>
                <p>{memory.strength.replace(/_/g, " ")} · {memory.counts.observation_count} qualified observations</p>
                {memory.blocker_reasons.length ? memory.blocker_reasons.map((item) => <small key={item}>{item}</small>) : <small>No learning projection blocker.</small>}
                <small>Authority: attention only · setup not authorized · P19 rank not modified.</small>
              </article>
            </div>
          </section> : (
            <section
              className="engineering-memory engineering-memory-compact"
              data-learning-state={memory.state}
              aria-label="Engineering Memory, attention only"
            >
              <header>
                <div>
                  <span className="eyebrow">ENGINEERING MEMORY · ATTENTION ONLY</span>
                  <h3>{humanize(memory.state)}</h3>
                </div>
                <div className="engineering-memory-badges"><span>P19 order unchanged</span></div>
              </header>
              <p>{memoryLine}</p>
              <small>Historical attention is withheld for this context. Current evidence and P19 remain authoritative.</small>
            </section>
          )}
          <section className="performance-ribbon">
            <h3>Time-loss ribbon</h3>
            {performance.opportunity_map.opportunities.length ? (
              <ol>{performance.opportunity_map.opportunities.map((item) => {
                const evidence = opportunityEvidence.get(item.opportunity_id);
                return <li key={item.opportunity_id}>
                  <button type="button" disabled={!evidence} onClick={() => { if (evidence) onFocusEvidence(evidence); }}>
                    <b>{item.track_region} · {item.phase.replace(/_/g, " ")}</b>
                    <span>{item.local_delta_s == null ? "time unavailable" : `${item.local_delta_s >= 0 ? "+" : ""}${item.local_delta_s.toFixed(3)} s`} · {item.origin_kind.replace(/_/g, " ")} · {item.repeatability.replace(/_/g, " ")}</span>
                  </button>
                </li>;
              })}</ol>
            ) : <p>{performance.opportunity_map.context_blockers.join(" ") || "No measured opportunity cleared the current time floor."}</p>}
          </section>
          <section>
            <h3>Corner performance chain</h3>
            {performance.corner_chains.length ? performance.corner_chains.slice(0, 3).map((chain) => (
              <div className="performance-chain" key={chain.chain_id}>
                <b>{chain.track_region}</b>
                <p>{[chain.braking_state, chain.entry_state, chain.center_state, chain.exit_state, chain.carry_state].map((state) => (
                  state ? `${state.phase} ${state.elapsed_delta_s == null ? "—" : `${state.elapsed_delta_s >= 0 ? "+" : ""}${state.elapsed_delta_s.toFixed(3)} s`}` : null
                )).filter(Boolean).join(" → ")}</p>
                <small>{chain.contradictions[0]}</small>
              </div>
            )) : <p>No qualified connected corner chain is available.</p>}
          </section>
          <section>
            <h3>Driver / car separation</h3>
            {performance.corner_chains.some((chain) => chain.driver_vehicle_separation.length) ? performance.corner_chains.flatMap((chain) => chain.driver_vehicle_separation).slice(0, 6).map((item) => (
              <p key={item.separation_id}><b>{item.phase}</b> {item.result.replace(/_/g, " ")}<small>{item.blockers[0] ?? item.contradictions[0] ?? item.support[0]}</small></p>
            )) : <p>Driver-versus-car separation is unavailable for this qualified scope.</p>}
          </section>
          <section>
            <h3>Measured track demand</h3>
            <p>{performance.track_demand.full_throttle_fraction == null ? "Full-throttle fraction unavailable" : `${(performance.track_demand.full_throttle_fraction * 100).toFixed(1)}% full throttle`} · {performance.track_demand.braking_fraction == null ? "braking unavailable" : `${(performance.track_demand.braking_fraction * 100).toFixed(1)}% braking`} · {performance.track_demand.cornering_fraction == null ? "cornering unavailable" : `${(performance.track_demand.cornering_fraction * 100).toFixed(1)}% cornering`}</p>
            <small>Traffic exposure {performance.track_demand.traffic_exposure_fraction == null ? "unavailable" : `${(performance.track_demand.traffic_exposure_fraction * 100).toFixed(1)}%`}</small>
          </section>
          <section>
            <h3>Comparison context</h3>
            <p>{story.comparison_window}</p>
            <small>Source: {story.source_context} · Reference: {story.reference_context}</small>
          </section>
          <section>
            <h3>P20 / P26 performance bridge</h3>
            {performance.component_influences.length ? <ul>{performance.component_influences.map((item) => (
              <li key={item.influence_id}><b>{item.component_id.replace(/_/g, " ")}</b> · {item.runtime_support_state.replace(/_/g, " ")}<small>{item.performance_mechanism_ids.join(", ")}</small></li>
            ))}</ul> : <p>No component relevance is attached to the measured time scope.</p>}
          </section>
          <section><h3>Objective envelope</h3><p>Primary: {performance.objective_envelope.primary_outcomes.join(", ")}</p><small>Protected: {performance.objective_envelope.protected_outcomes.join(", ")}. Objective changes policy, not measured physics.</small></section>
          <section><h3>Strongest contradiction</h3><p>{performance.explanation_chain.strongest_contradiction}</p><small>Generic component relevance cannot authorize setup. P19 next: {performance.explanation_chain.p19_next_move}</small></section>
          <section><h3>Mission ribbon</h3><p>{workspace.run_sentinel.mission}</p><small>State {missionState} · Stage {workspace.run_sentinel.stage} · {contextClearedLaps} · {missionAcceptance} · {measurementAttempts}</small></section>
          {workspace.investigation && <section>
            <h3>Investigation path</h3>
            {workspace.current_subgoal ? <>
              <p><b>{workspace.current_subgoal.title}</b> · tier {activeEligibility?.safe_priority_tier.replace(/_/g, " ") ?? "verified"}</p>
              <small>{workspace.current_subgoal.why_this_tool}</small>
              <small>{workspace.current_subgoal.required_evidence.join(" · ")}</small>
            </> : <p>The deterministic planner is at a driver, evidence, or P19 terminal boundary.</p>}
            <small>{relevantTools.length} reachable inspection{relevantTools.length === 1 ? "" : "s"}; {toolEligibility.length - relevantTools.length} explicitly skipped or complete.</small>
            {latestDriverInterpretation && <small>
              Driver scope: {latestDriverInterpretation.context_record_only
                ? "context only"
                : [
                  latestDriverInterpretation.phase_scope.join("/"),
                  latestDriverInterpretation.response_regime_scope.join("/"),
                  latestDriverInterpretation.traffic_scope,
                  latestDriverInterpretation.stint_scope,
                  latestDriverInterpretation.power_state_scope,
                  latestDriverInterpretation.time_origin_scope,
                ].filter((item) => item && item !== "all").join(" · ") || "all typed contexts"}.
            </small>}
          </section>}
          {workspace.latest_tool_result && <section>
            <h3>Latest inspection · {workspace.latest_tool_result.finding_kind.replace(/_/g, " ")}</h3>
            <p>{workspace.latest_tool_result.observed_finding ?? workspace.latest_tool_result.summary}</p>
            <small>Ambiguity {workspace.latest_tool_result.ambiguity_before} → {workspace.latest_tool_result.ambiguity_after}. {workspace.latest_tool_result.missing_evidence[0] ?? "No additional evidence debt recorded by this inspection."}</small>
            {workspace.latest_tool_result.selection_receipt && <small>
              Selected {workspace.latest_tool_result.selection_receipt.selected_count}/{workspace.latest_tool_result.selection_receipt.candidate_count} exact artifacts · required evidence {workspace.latest_tool_result.selection_receipt.required_artifacts_present ? "present" : "missing"}.
            </small>}
          </section>}
          <section><h3>Critic · {(workspace.critique.outcome ?? (workspace.critique.passed ? "pass" : "blocked")).replace(/_/g, " ")}</h3><p>{workspace.critique.passed ? "Mandatory context, contradiction, and authority checks passed." : workspace.critique.findings.join(" ")}</p></section>
          {workspace.prospective_consumption && <section>
            <h3>Post-open consumption · operational only</h3>
            <p>{workspace.prospective_consumption.tool_request_event_ids.length} tool requests · {workspace.prospective_consumption.continue_action_count} driver continue actions · {workspace.prospective_consumption.driver_question_ids.length} questions</p>
            <small>{workspace.prospective_consumption.accepted_lap_ids_after_open.length} new accepted laps · {workspace.prospective_consumption.measurement_attempt_ids_after_open.length} new measurement attempts · {workspace.prospective_consumption.workflow_ids_opened_after_open.length} workflows opened.</small>
          </section>}
          <section><h3>P19 collection contract</h3>{workspace.p19_mission_contract
            ? <><p>{workspace.p19_mission_contract.acceptance_thresholds.join("; ")}</p><small>{workspace.p19_mission_contract.contract_id}</small></>
            : workspace.success_contract
              ? <><p>{workspace.success_contract.acceptance_rule}</p><small>{workspace.success_contract.independence_unit}</small></>
              : <p>{workspace.run_sentinel.blocker_reasons.join(" ") || "P19 published no collection contract."}</p>}
          </section>
          <section><h3>Run sentinel</h3><p>{workspace.run_sentinel.need}</p>{workspace.run_sentinel.laps.length ? <ul>{workspace.run_sentinel.laps.slice(-6).map((lap) => <li key={lap.lap_number}>{lap.status === "context_cleared" ? <CheckCircle2 size={12} /> : <XCircle size={12} />} Lap {lap.lap_number}: {lap.status === "context_cleared" ? "context-cleared" : "rejected"}{lap.reasons.length ? ` — ${lap.reasons.join(", ")}` : ""}</li>)}</ul> : <small>No laps have been assessed for this mission yet.</small>}</section>
          <section>
            <h3>Evidence index</h3>
            {currentEvidenceEntries.length ? <ul>{currentEvidenceEntries.slice(0, 8).map((item) => (
              <li key={item.artifact_id}>
                <button
                  type="button"
                  onClick={() => onFocusEvidence(item)}
                  aria-label={`Open source · ${evidenceSourceLabel(item)}`}
                  title={`Technical provenance: ${item.producer_id} · ${item.artifact_id}`}
                >
                  <b>Open source</b>
                  <span>{evidenceSourceLabel(item)}</span>
                </button>
              </li>
            ))}</ul> : <p>No current-scope artifacts are available. Historical P33 sources remain inside Engineering Memory.</p>}
          </section>
          <section><h3>Research boundary</h3><p>Adaptive experimentation: {workspace.adaptive_research.state.replace(/_/g, " ")}.</p><small>{workspace.adaptive_research.activation_gate}</small></section>
        </div>
      )}
      {error && <p className="crew-chief-inline-error" role="alert">{error}</p>}
    </section>
  );
}
