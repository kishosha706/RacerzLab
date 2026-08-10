import { AlertTriangle, Boxes, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { fetchVehicleSystems } from "../api/client";
import type { VehicleSystemsProjection } from "../types/vehicleSystems";

type Props = {
  runId: string;
  sessionId?: string | null;
  learning: boolean;
  surface: "engineer" | "setup";
};

type LoadState = {
  key: string;
  status: "loading" | "ready" | "error";
  projection: VehicleSystemsProjection | null;
  error: string | null;
};

const visibleRelevance = new Set(["supported", "tested", "candidate", "contradicted", "blocked"]);
const relevanceRank: Record<string, number> = { supported: 0, tested: 1, candidate: 2, contradicted: 3, blocked: 4 };

function label(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

export function VehicleSystemsPanel({ runId, sessionId = null, learning, surface }: Props) {
  const key = `${runId}:${sessionId ?? "no-session"}`;
  const [state, setState] = useState<LoadState>({ key, status: "loading", projection: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ key, status: "loading", projection: null, error: null });
    void fetchVehicleSystems(runId, { sessionId })
      .then((projection) => {
        if (cancelled) return;
        if (
          projection.run_id !== runId
          || projection.authority !== "p19_projection_only"
          || projection.schema_version !== "p26.component-awareness.v2"
          || projection.version_scope_state !== "verified"
          || !projection.runtime_identity
          || projection.reasoning_snapshot_sha256 !== projection.runtime_graph.reasoning_snapshot_sha256
          || projection.runtime_graph.setup_authorized !== false
        ) {
          setState({ key, status: "error", projection: null, error: "Vehicle Systems returned a different evidence scope." });
          return;
        }
        setState({ key, status: "ready", projection, error: null });
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setState({ key, status: "error", projection: null, error: caught instanceof Error ? caught.message : "Vehicle Systems is unavailable." });
      });
    return () => { cancelled = true; };
  }, [key, runId, sessionId]);

  const projection = state.key === key ? state.projection : null;
  const components = useMemo(() => (
    projection?.component_states
      .filter((item) => visibleRelevance.has(item.relevance))
      .sort((left, right) => (
        (relevanceRank[left.relevance] ?? 99) - (relevanceRank[right.relevance] ?? 99)
        || Number(projection.leading_component_ids.includes(right.component_id)) - Number(projection.leading_component_ids.includes(left.component_id))
        || right.supporting_artifact_ids.length - left.supporting_artifact_ids.length
        || left.component_id.localeCompare(right.component_id)
      ))
      .slice(0, learning ? 6 : 1) ?? []
  ), [learning, projection]);

  if (state.status === "loading") return <section className="vehicle-systems-panel" data-surface={surface}><span>Assembling vehicle-system evidence…</span></section>;
  if (state.status === "error" || !projection) return (
    <section className="vehicle-systems-panel" data-surface={surface} data-state="blocked" role="status">
      <AlertTriangle size={15} aria-hidden="true" /><span>{state.error ?? "Vehicle Systems is unavailable."}</span>
    </section>
  );

  return (
    <section className="vehicle-systems-panel" data-surface={surface} data-mode={learning ? "learning" : "race"} aria-labelledby={`vehicle-systems-${surface}`}>
      <header>
        <Boxes size={16} aria-hidden="true" />
        <div><span>Vehicle Systems</span><h2 id={`vehicle-systems-${surface}`}>{projection.leading_system}</h2></div>
        <small><ShieldCheck size={12} aria-hidden="true" /> P19 authority only</small>
      </header>
      <p className="vehicle-systems-next"><strong>Next:</strong> {projection.next_discriminator}</p>
      {learning && <p className="vehicle-systems-next"><strong>Contradiction check:</strong> {projection.strongest_contradiction}</p>}
      {learning && components.length > 0 && (
        <div className="vehicle-systems-grid">
          {components.map((component) => (
            <article key={component.component_id} data-relevance={component.relevance}>
              <div><strong>{label(component.component_id)}</strong><span>{label(component.relevance)}</span></div>
              <p>{component.supporting_artifact_ids.length} supporting · {component.contradicting_artifact_ids.length} contradicting artifact{component.contradicting_artifact_ids.length === 1 ? "" : "s"}</p>
              <small>{component.current_testability === "p19_authorized" ? "Exact test authorized by P19" : component.current_testability === "policy_blocked" ? "Prior Undo blocks repetition" : "Measurement / hypothesis only"}</small>
              <small>{component.supporting_cause_ids.length} typed cause link{component.supporting_cause_ids.length === 1 ? "" : "s"} · {component.current_response_state === "observed" ? "response observed" : "response unavailable"}</small>
              {component.current_settings.slice(0, 2).map((setting) => <em key={setting}>{setting}</em>)}
              {component.controlled_history.some((item) => item.policy_verdict === "undo") && <b>Previous exact-context Undo preserved</b>}
              <small>Not directly measurable: {component.unavailable_quantities.slice(0, 2).join(", ")}</small>
            </article>
          ))}
        </div>
      )}
      {learning && components.length === 0 && <p>No component is isolated. Definitions remain available, but current-run evidence does not activate them.</p>}
    </section>
  );
}
