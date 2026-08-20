import { AlertTriangle, Boxes, RefreshCcw, Search, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchVehicleSystemComponent,
  fetchVehicleSystemControlTrace,
  fetchVehicleSystems,
} from "../api/client";
import {
  isComponentInspectionResponse,
  isControlMechanismTraceResponse,
  isVehicleSystemsProjection,
  type ComponentInspectionResponse,
  type ControlMechanismTraceResponse,
  type VehicleSystemsProjection,
} from "../types/vehicleSystems";
import { useEngineeringCase } from "../store/EngineeringCaseContext";

type Props = {
  runId: string;
  sessionId?: string | null;
  learning: boolean;
  surface: "engineer" | "setup";
  refreshKey?: string | number | null;
  expectedSetupId?: string | null;
  /** Undefined fetches independently; null is an explicit unavailable report projection. */
  initialProjection?: VehicleSystemsProjection | null;
};

type LoadState = {
  key: string;
  status: "loading" | "ready" | "error";
  projection: VehicleSystemsProjection | null;
  error: string | null;
};

type InspectionState = {
  key: string | null;
  status: "idle" | "loading" | "ready" | "error";
  response: ComponentInspectionResponse | null;
  error: string | null;
};

type TraceState = {
  key: string | null;
  status: "idle" | "loading" | "ready" | "error";
  response: ControlMechanismTraceResponse | null;
  error: string | null;
};

const visibleRelevance = new Set(["supported", "tested", "candidate", "contradicted", "blocked"]);
const relevanceRank: Record<string, number> = {
  supported: 0,
  tested: 1,
  candidate: 2,
  contradicted: 3,
  blocked: 4,
};

function label(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}

function responseLabel(value: "observed" | "not_observed" | "unavailable"): string {
  if (value === "observed") return "response observed";
  if (value === "not_observed") return "response not observed";
  return "response unavailable";
}

export function VehicleSystemsPanel({
  runId,
  sessionId = null,
  learning,
  surface,
  refreshKey = null,
  expectedSetupId,
  initialProjection,
}: Props) {
  const { engineeringCase } = useEngineeringCase();
  const [retryToken, setRetryToken] = useState(0);
  const embeddedKey = initialProjection === undefined
    ? "fetch"
    : initialProjection == null
      ? "embedded-unavailable"
      : `${initialProjection.reasoning_snapshot_sha256}:${initialProjection.knowledge_graph_sha256}:${initialProjection.setup_snapshot_sha256 ?? "no-setup"}`;
  const key = JSON.stringify({
    runId,
    sessionId,
    refreshKey,
    retryToken,
    expectedSetupId,
    embeddedKey,
    caseSha256: engineeringCase?.case_sha256 ?? null,
  });
  const [state, setState] = useState<LoadState>({
    key,
    status: initialProjection === undefined ? "loading" : "error",
    projection: null,
    error: null,
  });
  const [inspection, setInspection] = useState<InspectionState>({
    key: null,
    status: "idle",
    response: null,
    error: null,
  });
  const [trace, setTrace] = useState<TraceState>({
    key: null,
    status: "idle",
    response: null,
    error: null,
  });
  const inspectionSequence = useRef(0);
  const traceSequence = useRef(0);
  const embeddedProjection = useMemo(() => (
    initialProjection != null && isVehicleSystemsProjection(initialProjection, {
      runId,
      sessionId,
      setupId: expectedSetupId,
    })
      ? initialProjection
      : null
  ), [expectedSetupId, initialProjection, runId, sessionId]);

  useEffect(() => {
    let cancelled = false;
    inspectionSequence.current += 1;
    traceSequence.current += 1;
    setInspection({ key: null, status: "idle", response: null, error: null });
    setTrace({ key: null, status: "idle", response: null, error: null });
    const expectation = { runId, sessionId, setupId: expectedSetupId };
    if (engineeringCase == null) {
      setState({ key, status: "loading", projection: null, error: null });
      return () => { cancelled = true; };
    }
    if (initialProjection !== undefined) {
      if (initialProjection === null) {
        setState({
          key,
          status: "error",
          projection: null,
          error: "Vehicle Systems is unavailable in this exact report.",
        });
      } else if (embeddedProjection
        && embeddedProjection.reasoning_snapshot_sha256 === engineeringCase.p19_reasoning_snapshot_sha256
        && embeddedProjection.knowledge_graph_sha256 === engineeringCase.p26_knowledge_graph_sha256) {
        setState({ key, status: "ready", projection: embeddedProjection, error: null });
      } else {
        setState({
          key,
          status: "error",
          projection: null,
          error: "Vehicle Systems did not match this report's evidence scope.",
        });
      }
      return () => { cancelled = true; };
    }

    setState({ key, status: "loading", projection: null, error: null });
    void fetchVehicleSystems(runId, {
      sessionId,
      refreshKey: `${refreshKey ?? "no-revision"}:${retryToken}`,
    })
      .then((projection) => {
        if (cancelled) return;
        if (!isVehicleSystemsProjection(projection, expectation)
          || projection.reasoning_snapshot_sha256 !== engineeringCase.p19_reasoning_snapshot_sha256
          || projection.knowledge_graph_sha256 !== engineeringCase.p26_knowledge_graph_sha256) {
          setState({
            key,
            status: "error",
            projection: null,
            error: "Vehicle Systems returned a different evidence scope.",
          });
          return;
        }
        setState({ key, status: "ready", projection, error: null });
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setState({
          key,
          status: "error",
          projection: null,
          error: reason instanceof Error ? reason.message : "Vehicle Systems is unavailable for this exact case.",
        });
      });
    return () => { cancelled = true; };
  }, [embeddedProjection, engineeringCase, expectedSetupId, initialProjection, key, refreshKey, retryToken, runId, sessionId]);

  const projection = initialProjection === undefined
    ? state.key === key ? state.projection : null
    : embeddedProjection;
  const components = useMemo(() => (
    projection?.component_states
      .filter((item) => visibleRelevance.has(item.relevance))
      .sort((left, right) => (
        (relevanceRank[left.relevance] ?? 99) - (relevanceRank[right.relevance] ?? 99)
        || Number(projection.leading_component_ids.includes(right.component_id))
          - Number(projection.leading_component_ids.includes(left.component_id))
        || right.supporting_artifact_ids.length - left.supporting_artifact_ids.length
        || left.component_id.localeCompare(right.component_id)
      ))
      .slice(0, learning ? 6 : 1) ?? []
  ), [learning, projection]);

  const inspectComponent = useCallback((componentId: string) => {
    if (!projection || !learning) return;
    const sequence = ++inspectionSequence.current;
    traceSequence.current += 1;
    const requestKey = `${projection.reasoning_snapshot_sha256}:${componentId}`;
    setInspection({ key: requestKey, status: "loading", response: null, error: null });
    setTrace({ key: null, status: "idle", response: null, error: null });
    void fetchVehicleSystemComponent(runId, componentId, {
      sessionId,
      refreshKey: `${refreshKey ?? "no-revision"}:${projection.reasoning_snapshot_sha256}`,
    })
      .then((response) => {
        if (sequence !== inspectionSequence.current) return;
        if (!isComponentInspectionResponse(response, projection, componentId)) {
          setInspection({
            key: requestKey,
            status: "error",
            response: null,
            error: "Component details did not match the open evidence snapshot.",
          });
          return;
        }
        setInspection({ key: requestKey, status: "ready", response, error: null });
      })
      .catch(() => {
        if (sequence !== inspectionSequence.current) return;
        setInspection({
          key: requestKey,
          status: "error",
          response: null,
          error: "Read-only component details are unavailable.",
        });
      });
  }, [learning, projection, refreshKey, runId, sessionId]);

  const traceControl = useCallback((controlKey: string) => {
    if (!projection || !learning) return;
    const sequence = ++traceSequence.current;
    const requestKey = `${projection.graph_version}:${controlKey}`;
    setTrace({ key: requestKey, status: "loading", response: null, error: null });
    void fetchVehicleSystemControlTrace(runId, controlKey, {
      refreshKey: projection.graph_version,
    })
      .then((response) => {
        if (sequence !== traceSequence.current) return;
        if (!isControlMechanismTraceResponse(response, projection, controlKey)) {
          setTrace({
            key: requestKey,
            status: "error",
            response: null,
            error: "The expectation trace did not match this vehicle-system graph.",
          });
          return;
        }
        setTrace({ key: requestKey, status: "ready", response, error: null });
      })
      .catch(() => {
        if (sequence !== traceSequence.current) return;
        setTrace({
          key: requestKey,
          status: "error",
          response: null,
          error: "The read-only expectation trace is unavailable.",
        });
      });
  }, [learning, projection, runId]);

  if (state.status === "loading") {
    return (
      <section className="vehicle-systems-panel" data-surface={surface}>
        <span>Assembling vehicle-system evidence…</span>
      </section>
    );
  }
  if (state.status === "error" || !projection) {
    return (
      <section className="vehicle-systems-panel" data-surface={surface} data-state="blocked" role="status">
        <AlertTriangle size={15} aria-hidden="true" />
        <span>{state.error ?? "Vehicle Systems is unavailable."}</span>
        {initialProjection === undefined && (
          <button type="button" onClick={() => setRetryToken((value) => value + 1)}>
            <RefreshCcw size={13} aria-hidden="true" /> Retry
          </button>
        )}
      </section>
    );
  }

  return (
    <section
      className="vehicle-systems-panel"
      data-surface={surface}
      data-mode={learning ? "learning" : "race"}
      aria-labelledby={`vehicle-systems-${surface}`}
    >
      <header>
        <Boxes size={16} aria-hidden="true" />
        <div>
          <span>Vehicle Systems</span>
          <h2 id={`vehicle-systems-${surface}`}>{projection.leading_system}</h2>
        </div>
        <small><ShieldCheck size={12} aria-hidden="true" /> Read-only · P19 decides setup</small>
      </header>
      <p className="vehicle-systems-next">
        <strong>Evidence check:</strong> {projection.next_discriminator}
      </p>
      {learning && (
        <p className="vehicle-systems-next">
          <strong>Verified scope:</strong> Next Gen {projection.runtime_identity.car_version} · iRacing {projection.runtime_identity.iracing_build_version}
        </p>
      )}
      {learning && (
        <p className="vehicle-systems-next">
          <strong>Contradiction check:</strong> {projection.strongest_contradiction}
        </p>
      )}
      {learning && components.length > 0 && (
        <div className="vehicle-systems-grid">
          {components.map((component) => (
            <article key={component.component_id} data-relevance={component.relevance}>
              <div>
                <strong>{label(component.component_id)}</strong>
                <span>{label(component.relevance)}</span>
              </div>
              <p>
                {component.supporting_artifact_ids.length} observed artifact{component.supporting_artifact_ids.length === 1 ? "" : "s"} · {component.contradicting_citation_ids.length} contradiction{component.contradicting_citation_ids.length === 1 ? "" : "s"}
              </p>
              <small>
                {component.current_testability === "p19_authorized"
                  ? `P19 authorized only ${label(component.authorized_control_key ?? "unknown_control")}`
                  : component.current_testability === "policy_blocked"
                    ? `Prior Undo blocks ${component.blocked_control_keys.map(label).join(", ")}`
                    : "Measurement / hypothesis only"}
              </small>
              <small>
                {component.supporting_cause_ids.length} typed cause link{component.supporting_cause_ids.length === 1 ? "" : "s"} · {responseLabel(component.current_response_state)}
              </small>
              {component.observation_scopes.slice(0, 2).map((scope) => (
                <small key={`${scope.artifact_id}:${scope.observation_id}`}>
                  L{scope.lap_number} · {label(scope.phase)} · {scope.lap_pct_start.toFixed(1)}–{scope.lap_pct_end.toFixed(1)}%
                </small>
              ))}
              {component.current_settings.slice(0, 2).map((setting) => <em key={setting}>{setting}</em>)}
              {component.interaction_summaries.slice(0, 2).map((interaction) => (
                <small key={interaction}>{interaction}</small>
              ))}
              {component.controlled_history.some((item) => (
                item.exact_context && item.policy_verdict === "undo"
              )) && (
                <b>Previous exact-context Undo preserved</b>
              )}
              {component.live_response_blocker_reasons[0] && (
                <small>Live response: {component.live_response_blocker_reasons[0]}</small>
              )}
              <small>Not directly measurable: {component.unavailable_quantities.slice(0, 2).join(", ")}</small>
              <button type="button" onClick={() => inspectComponent(component.component_id)}>
                <Search size={13} aria-hidden="true" /> Inspect read-only details
              </button>
            </article>
          ))}
        </div>
      )}
      {learning && components.length === 0 && (
        <p>No component is isolated. Definitions remain available, but current-run evidence does not activate them.</p>
      )}
      {learning && inspection.status === "loading" && <p role="status">Loading read-only component details…</p>}
      {learning && inspection.status === "error" && <p role="status">{inspection.error}</p>}
      {learning && inspection.status === "ready" && inspection.response && (
        <section className="vehicle-systems-detail" aria-label={`${inspection.response.definition.label} read-only details`}>
          <header>
            <div>
              <span>Read-only component inspection</span>
              <h3>{inspection.response.definition.label}</h3>
            </div>
            <small>No setup authority</small>
          </header>
          <p>{inspection.response.definition.physical_role}</p>
          <p><strong>Load / speed relevance:</strong> {inspection.response.definition.speed_load_relevance}</p>
          <ul>
            {inspection.response.definition.measurement_requirements.slice(0, 3).map((requirement) => (
              <li key={requirement}>{requirement}</li>
            ))}
          </ul>
          {inspection.response.interactions.slice(0, 3).map((interaction) => (
            <small key={interaction.interaction_id}>{interaction.description}</small>
          ))}
          {inspection.response.controls.length > 0 && (
            <div className="vehicle-systems-controls" aria-label="Read-only expectation traces">
              {inspection.response.controls.map((control) => (
                <button type="button" key={control} onClick={() => traceControl(control)}>
                  Trace {label(control)}
                </button>
              ))}
            </div>
          )}
        </section>
      )}
      {learning && trace.status === "loading" && <p role="status">Loading engineering expectation trace…</p>}
      {learning && trace.status === "error" && <p role="status">{trace.error}</p>}
      {learning && trace.status === "ready" && trace.response && (
        <section className="vehicle-systems-detail" aria-label={`${label(trace.response.control_key)} expectation trace`}>
          <header>
            <div>
              <span>Engineering expectation only</span>
              <h3>{label(trace.response.control_key)}</h3>
            </div>
            <small>Cannot authorize a change</small>
          </header>
          <ul>
            {trace.response.edges.slice(0, 6).map((edge) => (
              <li key={edge.edge_id}>
                {label(edge.kind)}: {label(edge.source_node_id)} → {label(edge.target_node_id)}
              </li>
            ))}
          </ul>
        </section>
      )}
      {learning && projection.knowledge_debt.length > 0 && (
        <p><strong>Knowledge debt:</strong> {projection.knowledge_debt.slice(0, 2).join("; ")}</p>
      )}
    </section>
  );
}
