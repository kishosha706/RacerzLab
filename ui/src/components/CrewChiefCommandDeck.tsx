import { useEffect, useRef, useState } from "react";
import { BrainCircuit, CheckCircle2, CircleHelp, Play, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

import {
  answerCrewChiefQuestion,
  abandonCrewChiefInvestigation,
  continueCrewChiefInvestigation,
  fetchCrewChiefWorkspace,
  openCrewChiefInvestigation,
  rebaseCrewChiefInvestigation,
  updateCrewChiefObjective,
} from "../api/client";
import type { CrewChiefEvidenceEntry, CrewChiefWorkspace, EngineeringObjective } from "../types/crewChief";
import type { RunIntelligenceReport } from "../types/intelligence";

type Props = {
  runId: string;
  sessionId: string;
  report: RunIntelligenceReport;
  scopeRunIds: readonly string[];
  learning: boolean;
  onFocusEvidence: (entry: CrewChiefEvidenceEntry) => void;
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
      <p>Checking the exact P19, P20, P26, and P32 identities before showing a decision.</p>
    </section>;
  }

  const decision = workspace.terminal_decision;
  const investigationId = workspace.identity.investigation_id;
  const revision = workspace.identity.workspace_revision;
  const status = workspace.folded_state?.status;
  const performance = workspace.performance_intelligence;
  const story = performance.speed_story;
  const activeObjective = workspace.folded_state?.objective ?? objective;
  const opportunityEvidence = new Map(
    workspace.evidence_index.entries
      .filter((item) => item.producer_id === "p32.lap_time_opportunity")
      .map((item) => [item.artifact_id, item]),
  );
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
        <p><b>WHERE IT STARTS</b> {story.where_it_starts}</p>
        <p><b>WHAT CARRIES</b> {story.what_carries}</p>
        <p className="speed-story-contradiction"><b>STRONGEST CONTRADICTION</b> {story.strongest_contradiction}</p>
        {learning && <>
          <p><b>DRIVER</b> {story.driver}</p>
          <p><b>CAR</b> {story.car}</p>
          <p><b>SYSTEMS</b> {story.systems}</p>
          <p><b>HISTORY</b> {story.history}</p>
          <p><b>KNOW</b> {workspace.evidence_index.entries.length} exact artifacts · {workspace.run_sentinel.accepted_laps} accepted laps</p>
        </>}
      </div>

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
            onClick={() => { void runMutation(() => continueCrewChiefInvestigation(
              runId, sessionId, investigationId!, revision, report, scopeRunIds,
              activeObjective,
            )); }}
          ><Play size={14} /> {workspace.current_subgoal ? "Run next inspection" : "Emit bounded decision"}</button>
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
          <section><h3>Performance history</h3><p>{performance.response_records.length} controlled performance records attached.</p>{performance.response_records.slice(0, 3).map((item) => <small key={item.record_id}>{item.control} · {item.phase_effect} · {item.policy_verdict}</small>)}</section>
          <section><h3>Strongest contradiction</h3><p>{performance.explanation_chain.strongest_contradiction}</p><small>Generic component relevance cannot authorize setup. P19 next: {performance.explanation_chain.p19_next_move}</small></section>
          <section><h3>Mission ribbon</h3><p>{workspace.run_sentinel.mission}</p><small>Stage {workspace.run_sentinel.stage} · {workspace.run_sentinel.accepted_laps}/{workspace.run_sentinel.required_laps} accepted</small></section>
          <section><h3>Critic</h3><p>{workspace.critique.passed ? "Authority and identity checks passed." : workspace.critique.findings.join(" ")}</p></section>
          <section><h3>P19 collection contract</h3>{workspace.p19_mission_contract
            ? <><p>{workspace.p19_mission_contract.acceptance_thresholds.join("; ")}</p><small>{workspace.p19_mission_contract.contract_id}</small></>
            : workspace.success_contract
              ? <><p>{workspace.success_contract.acceptance_rule}</p><small>{workspace.success_contract.independence_unit}</small></>
              : <p>{workspace.run_sentinel.blocker_reasons.join(" ") || "P19 published no collection contract."}</p>}
          </section>
          <section><h3>Run sentinel</h3><p>{workspace.run_sentinel.need}</p>{workspace.run_sentinel.laps.length ? <ul>{workspace.run_sentinel.laps.slice(-6).map((lap) => <li key={lap.lap_number}><CheckCircle2 size={12} /> Lap {lap.lap_number}: {lap.status}{lap.reasons.length ? ` — ${lap.reasons.join(", ")}` : ""}</li>)}</ul> : <small>No laps have been assessed for this mission yet.</small>}</section>
          <section><h3>Evidence index</h3>{workspace.evidence_index.entries.length ? <ul>{workspace.evidence_index.entries.slice(0, 8).map((item) => <li key={item.artifact_id}><button type="button" onClick={() => onFocusEvidence(item)}><b>{item.producer_id}</b> {item.artifact_id} · {item.mechanism_ids.join(", ") || "unclassified"}</button></li>)}</ul> : <p>No exact artifacts are available for the selected scope.</p>}</section>
          <section><h3>Response atlas</h3><p>{workspace.response_history_ids.length} exact-context controlled response records attached.</p></section>
          <section><h3>Driver intelligence</h3><p>{workspace.driver_memory_ids.length} complaint/context records retained as non-authoritative priors.</p></section>
          <section><h3>Research boundary</h3><p>Adaptive experimentation: {workspace.adaptive_research.state.replace(/_/g, " ")}.</p><small>{workspace.adaptive_research.activation_gate}</small></section>
        </div>
      )}
      {error && <p className="crew-chief-inline-error" role="alert">{error}</p>}
    </section>
  );
}
