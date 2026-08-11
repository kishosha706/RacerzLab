import { Activity, AlertTriangle, BrainCircuit, CheckCircle2, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchEngineeringAwareness } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { EngineeringAwarenessProjection, TrustAxis } from "../types/engineeringAwareness";

type AwarenessSurface = "overview" | "laps" | "platform" | "setup" | "compare" | "engineer";

type Props = {
  runId: string;
  sessionId?: string | null;
  surface: AwarenessSurface;
};

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function Axis({ label, axis, learning }: { label: string; axis: TrustAxis; learning: boolean }) {
  return (
    <article className={`awareness-axis awareness-axis--${axis.state}`}>
      <span>{label}</span>
      <strong>{humanize(axis.state)}</strong>
      {learning && <p>{axis.basis}</p>}
      {axis.blockers[0] && <small>{axis.blockers[0]}</small>}
    </article>
  );
}

export function EngineeringAwarenessPanel({ runId, sessionId = null, surface }: Props) {
  const { selection, focusEvidence } = useTelemetrySelection();
  const learning = selection.selectedMode === "learning";
  const [projection, setProjection] = useState<EngineeringAwarenessProjection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const requestSequence = useRef(0);

  useEffect(() => {
    const sequence = ++requestSequence.current;
    const requestedRunId = runId;
    const requestedSessionId = sessionId;
    setLoading(true);
    setError(null);
    setProjection(null);
    fetchEngineeringAwareness(requestedRunId, { sessionId: requestedSessionId })
      .then((response) => {
        if (
          sequence !== requestSequence.current
          || response.run_id !== requestedRunId
          || response.request_identity.run_id !== requestedRunId
          || response.session_id !== requestedSessionId
          || response.request_identity.session_id !== requestedSessionId
        ) return;
        setProjection(response);
      })
      .catch((reason: unknown) => {
        if (sequence !== requestSequence.current) return;
        setError(reason instanceof Error ? reason.message : "Engineering awareness is unavailable.");
      })
      .finally(() => {
        if (sequence === requestSequence.current) setLoading(false);
      });
    return () => { requestSequence.current += 1; };
  }, [runId, sessionId]);

  const focusPrimary = useCallback(() => {
    const primary = projection?.primary_state;
    if (!primary || projection.run_id !== runId) return;
    focusEvidence({
      runId,
      lapNumber: primary.lap_number,
      lapScope: "track_zone",
      lapPct: primary.lap_pct_peak,
      zoneId: `awareness:${primary.state_id}`,
      zoneLabel: humanize(primary.mechanism),
      zoneStartPct: primary.lap_pct_start,
      zoneEndPct: primary.lap_pct_end,
      channelId: primary.source_channels[0] ?? null,
      system: primary.mechanism,
      selectionSource: "engineer",
      lockState: "locked",
      trustTier: primary.evidence_state,
      valueBasis: "selected_window",
    });
  }, [focusEvidence, projection, runId]);

  const blockedCount = useMemo(
    () => projection?.subsystem_states.filter((item) => item.status !== "ready").length ?? 0,
    [projection],
  );

  if (loading) {
    return <section className="engineering-awareness engineering-awareness--loading" aria-live="polite">Reading whole-car engineering state…</section>;
  }
  if (error || !projection) {
    return (
      <section className="engineering-awareness engineering-awareness--blocked" role="status">
        <AlertTriangle size={16} />
        <div><strong>Whole-car awareness unavailable</strong><p>{error ?? "No exact projection was returned."}</p></div>
      </section>
    );
  }

  const primary = projection.primary_state;
  return (
    <section className="engineering-awareness" data-awareness-surface={surface} data-state-revision={projection.state_revision}>
      <header className="engineering-awareness__header">
        <div>
          <span className="eyebrow"><BrainCircuit size={14} /> Whole-car state</span>
          <h3>{primary?.label ?? "No qualified primary mechanism"}</h3>
          <p>
            {primary
              ? `Lap ${primary.lap_number} · ${primary.phase} · ${primary.lap_pct_start.toFixed(1)}–${primary.lap_pct_end.toFixed(1)}%`
              : projection.knowledge_debt[0] ?? "Producer-owned evidence has not earned a primary state."}
          </p>
        </div>
        <div className="engineering-awareness__status">
          <ShieldCheck size={16} />
          <strong>Observation only</strong>
          <small>{blockedCount} of 10 systems need evidence</small>
        </div>
      </header>

      {primary && (
        <button type="button" className="engineering-awareness__focus" onClick={focusPrimary}>
          <Activity size={15} /> Focus exact telemetry window
        </button>
      )}

      {surface === "overview" && (
        <div className="engineering-awareness__brief">
          <article><span>Evidence boundary</span><strong>P20 reports measured state only</strong><p>Use the controlled P19 workflow for setup policy and test actions.</p></article>
          {projection.knowledge_debt[0] && <article className="is-blocked"><span>Knowledge debt</span><p>{projection.knowledge_debt[0]}</p></article>}
        </div>
      )}

      {surface === "laps" && (
        <div className="engineering-awareness__grid">
          {projection.episodes.length ? projection.episodes.slice(0, learning ? undefined : 2).map((episode) => (
            <article key={episode.episode_id}>
              <span>Laps {episode.lap_scope.join(", ")} · {episode.phase}</span>
              <strong>{episode.supporting_mechanism_kinds.map(humanize).join(" → ")}</strong>
              <p>{episode.lap_pct_start.toFixed(1)}–{episode.lap_pct_end.toFixed(1)}% · {episode.transition_ids.length} transitions</p>
            </article>
          )) : <article className="is-blocked"><span>Temporal episodes</span><p>{projection.knowledge_debt.find((item) => item.includes("episode")) ?? "No exact episode crossed the evidence gate."}</p></article>}
          <article className={projection.state_drift_status === "ready" ? "" : "is-blocked"}>
            <span>Clean-stint drift</span><strong>{humanize(projection.state_drift_status)}</strong>
            {projection.state_drift_blocker_reasons[0] && <p>{projection.state_drift_blocker_reasons[0]}</p>}
          </article>
        </div>
      )}

      {surface === "platform" && (
        <div className="engineering-awareness__grid">
          {projection.episodes.slice(0, learning ? 4 : 2).map((episode) => (
            <article key={episode.episode_id}>
              <span>{episode.phase} response chain</span>
              <strong>{episode.supporting_mechanism_kinds.map(humanize).join(" → ")}</strong>
              <p>Window {episode.lap_pct_start.toFixed(1)}–{episode.lap_pct_end.toFixed(1)}% · exact transitions {episode.transition_ids.length}</p>
            </article>
          ))}
          {!projection.episodes.length && <article className="is-blocked"><p>No exact chassis/platform episode earned display authority.</p></article>}
        </div>
      )}

      {surface === "setup" && (
        <div className="engineering-awareness__grid">
          {projection.control_mutations.length ? projection.control_mutations.slice(0, learning ? undefined : 3).map((item) => (
            <article key={item.mutation_id}>
              <span>{humanize(item.control_key)}</span>
              <strong>Observed {humanize(item.mutation_kind)}</strong>
              <p>Lap {item.lap} · {item.lap_pct.toFixed(1)}%</p>
            </article>
          )) : <article className="is-blocked"><p>No setup-control mutation was observed in this run.</p></article>}
        </div>
      )}

      {surface === "compare" && (
        <div className="engineering-awareness__grid">
          {projection.expected_vs_observed.length ? projection.expected_vs_observed.slice(0, learning ? undefined : 2).map((item) => (
            <article key={item.workflow_id}>
              <span>{item.control_key ? humanize(item.control_key) : "Diagnostic intervention"} · {item.phase}</span>
              <strong>Mechanism {humanize(item.mechanism_state)} · Response {humanize(item.control_response)}</strong>
              {learning && <p>{item.mechanism_reason} {item.control_response_reason}</p>}
            </article>
          )) : <article className="is-blocked"><p>No completed controlled workflow is attached to this exact P19 snapshot.</p></article>}
        </div>
      )}

      {surface === "engineer" && (
        learning ? <>
          <div className="engineering-awareness__systems">
            {projection.subsystem_states.map((item) => (
              <article key={item.mechanism} className={item.status === "ready" ? "is-ready" : "is-blocked"}>
                {item.status === "ready" ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                <span>{humanize(item.mechanism)}</span><strong>{humanize(item.status)}</strong>
                {learning && <p>{item.summary}</p>}
                {item.blocker_reasons[0] && <small>{item.blocker_reasons[0]}</small>}
              </article>
            ))}
          </div>
          <div className="engineering-awareness__trust">
            {Object.entries(projection.trust_budget).map(([key, axis]) => (
              <Axis key={key} label={humanize(key)} axis={axis} learning={learning} />
            ))}
          </div>
        </> : <div className="engineering-awareness__brief">
          <article className="is-blocked">
            <span>Current blocker</span>
            <strong>{projection.knowledge_debt[0] ?? "No active blocker"}</strong>
          </article>
          <article>
            <span>Evidence boundary</span>
            <strong>Observation only</strong>
            <p>Use the controlled P19 workflow for setup policy and test actions.</p>
          </article>
        </div>
      )}
    </section>
  );
}
