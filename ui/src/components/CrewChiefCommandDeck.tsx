import { useEffect, useState } from "react";
import { BrainCircuit, CheckCircle2, CircleHelp, Play, ShieldCheck } from "lucide-react";

import {
  answerCrewChiefQuestion,
  continueCrewChiefInvestigation,
  fetchCrewChiefWorkspace,
  openCrewChiefInvestigation,
} from "../api/client";
import type { CrewChiefEvidenceEntry, CrewChiefWorkspace, EngineeringObjective } from "../types/crewChief";
import type { RunIntelligenceReport } from "../types/intelligence";

type Props = {
  runId: string;
  sessionId: string;
  report: RunIntelligenceReport;
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

export function CrewChiefCommandDeck({ runId, sessionId, report, learning, onFocusEvidence }: Props) {
  const [workspace, setWorkspace] = useState<CrewChiefWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [driverReport, setDriverReport] = useState("");
  const [objective, setObjective] = useState<EngineeringObjective>("race_long_run");

  useEffect(() => {
    let cancelled = false;
    setWorkspace(null);
    setError(null);
    void fetchCrewChiefWorkspace(runId, sessionId, report, { objective })
      .then((value) => { if (!cancelled) setWorkspace(value); })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Crew Chief unavailable.");
      });
    return () => { cancelled = true; };
  }, [objective, report, runId, sessionId]);

  const runMutation = async (operation: () => Promise<CrewChiefWorkspace>) => {
    setBusy(true);
    setError(null);
    try {
      setWorkspace(await operation());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Crew Chief operation failed.");
    } finally {
      setBusy(false);
    }
  };

  if (error && !workspace) {
    return <section className="crew-chief-deck crew-chief-error" role="alert"><b>Crew Chief withheld</b><p>{error}</p></section>;
  }
  if (!workspace) {
    return <section className="crew-chief-deck" aria-busy="true"><span className="eyebrow">Crew Chief</span><p>Binding the current P19, P20, and P26 workspace…</p></section>;
  }

  const decision = workspace.terminal_decision;
  const investigationId = workspace.identity.investigation_id;
  const revision = workspace.identity.workspace_revision;
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

      <div className="crew-chief-race-brief" aria-label="Race-mode command brief">
        <p><b>WHAT</b> {decision.instruction}</p>
        <p><b>WHERE</b> {workspace.success_contract.target_scope}</p>
        <p><b>WHY IT MATTERS</b> {workspace.current_subgoal?.why_this_tool ?? workspace.post_run_brief[0]}</p>
        <p><b>KNOW</b> {workspace.evidence_index.entries.length} exact artifacts · {workspace.run_sentinel.accepted_laps} accepted laps</p>
        <p><b>UNCERTAIN</b> {workspace.critique.strongest_contradiction ?? workspace.blocker_reasons[0] ?? "No stronger contradiction is attached."}</p>
        <p><b>NEXT</b> {workspace.current_subgoal?.title ?? decision.title}</p>
      </div>

      {decision.kind === "controlled_test" && (
        <div className="crew-chief-exact-test">
          <b>Exact P19 controlled test</b>
          <span>{decision.control_key}: {decision.current_value} → {decision.proposed_value}</span>
          <small>Workflow {decision.workflow_id} · revision {decision.workflow_revision}</small>
        </div>
      )}

      {!workspace.investigation ? (
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
            onClick={() => { void runMutation(() => openCrewChiefInvestigation(runId, sessionId, report, {
              driver_report: driverReport,
              expected_workspace_revision: revision,
              objective,
            })); }}
          ><Play size={14} /> Open investigation</button>
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
                runId, sessionId, investigationId!, revision, answer, report,
              )); }}
            >{answer}</button>
          ))}</div>
        </div>
      ) : workspace.folded_state?.status === "open" ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => { void runMutation(() => continueCrewChiefInvestigation(
            runId, sessionId, investigationId!, revision, report,
          )); }}
        ><Play size={14} /> {workspace.current_subgoal ? "Run next inspection" : "Emit bounded decision"}</button>
      ) : null}

      {learning && (
        <div className="crew-chief-learning">
          <section><h3>Mission ribbon</h3><p>{workspace.run_sentinel.mission}</p><small>Stage {workspace.run_sentinel.stage} · {workspace.run_sentinel.accepted_laps}/{workspace.run_sentinel.required_laps} accepted</small></section>
          <section><h3>Critic</h3><p>{workspace.critique.passed ? "Authority and identity checks passed." : workspace.critique.findings.join(" ")}</p></section>
          <section><h3>Success contract</h3><p>{workspace.success_contract.acceptance_rule}</p><small>{workspace.success_contract.independence_unit}</small></section>
          <section><h3>Run sentinel</h3><p>{workspace.run_sentinel.need}</p><ul>{workspace.run_sentinel.laps.slice(-6).map((lap) => <li key={lap.lap_number}><CheckCircle2 size={12} /> Lap {lap.lap_number}: {lap.status}{lap.reasons.length ? ` — ${lap.reasons.join(", ")}` : ""}</li>)}</ul></section>
          <section><h3>Evidence index</h3><ul>{workspace.evidence_index.entries.slice(0, 8).map((item) => <li key={item.artifact_id}><button type="button" onClick={() => onFocusEvidence(item)}><b>{item.producer_id}</b> {item.artifact_id} · {item.mechanism_ids.join(", ") || "unclassified"}</button></li>)}</ul></section>
          <section><h3>Response atlas</h3><p>{workspace.response_history_ids.length} exact-context controlled response records attached.</p></section>
          <section><h3>Driver intelligence</h3><p>{workspace.driver_memory_ids.length} complaint/context records retained as non-authoritative priors.</p></section>
          <section><h3>Research boundary</h3><p>Adaptive experimentation: {workspace.adaptive_research.state.replace(/_/g, " ")}.</p><small>{workspace.adaptive_research.activation_gate}</small></section>
        </div>
      )}
      {error && <p className="crew-chief-inline-error" role="alert">{error}</p>}
    </section>
  );
}
