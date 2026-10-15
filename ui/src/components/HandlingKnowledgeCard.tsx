import { AlertTriangle, BrainCircuit, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { fetchHandlingKnowledge } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { HandlingObservationHandoff } from "../utils/handlingObservationHandoff";
import type { components as OpenApiComponents } from "../types/openapi.generated";

type HandlingKnowledgeProjection =
  OpenApiComponents["schemas"]["HandlingKnowledgeProjection"];

const LEVEL_LABELS: Record<string, string> = {
  p19_testable_control: "P19-testable control family",
  measurable_hypothesis: "Measurable setup hypothesis",
  educational_knowledge: "Educational setup area",
  unsupported_remove: "Not applicable to this car",
};

const APPLICABILITY_LABELS: Record<string, string> = {
  applicable: "applies to this car",
  educational_only: "educational only",
  blocked_by_build: "blocked by this build",
  unsupported: "unsupported",
};

function cleanLabel(value: string | null | undefined, fallback = "Not mapped"): string {
  if (!value) return fallback;
  return value
    .replace(/^effect:/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

type HandlingKnowledgeCardProps = {
  runId: string;
  sessionId: string;
  handoff: HandlingObservationHandoff;
  expectedCase: {
    caseId: string;
    caseRevision: string;
    caseSha256: string;
    setupId: string;
  };
  onDismiss: () => void;
};

/**
 * P35.6 P4: telemetry-observed handling knowledge inside Dial-In.
 *
 * This card is display-only. It never writes the driver complaint input,
 * never fabricates driver wording, and never unlocks setup hypotheses that
 * the P35.1 spine has not marked `setup_authorized` through an exact P19
 * projection.
 */
export function HandlingKnowledgeCard({
  runId,
  sessionId,
  handoff,
  expectedCase,
  onDismiss,
}: HandlingKnowledgeCardProps) {
  const { focusEvidence } = useTelemetrySelection();
  const requestSeqRef = useRef(0);
  const [state, setState] = useState<{
    status: "loading" | "ready" | "error";
    projection: HandlingKnowledgeProjection | null;
    error: string | null;
  }>({ status: "loading", projection: null, error: null });

  useEffect(() => {
    const seq = ++requestSeqRef.current;
    setState({ status: "loading", projection: null, error: null });
    void fetchHandlingKnowledge(runId, sessionId, handoff.assessmentId, expectedCase)
      .then((projection) => {
        if (seq !== requestSeqRef.current) return;
        setState({ status: "ready", projection, error: null });
      })
      .catch((reason: unknown) => {
        if (seq !== requestSeqRef.current) return;
        setState({
          status: "error",
          projection: null,
          error: reason instanceof Error
            ? reason.message
            : "Handling knowledge is unavailable.",
        });
      });
  }, [runId, sessionId, handoff.assessmentId, expectedCase]);

  const openEvidence = () => {
    const { projection } = state;
    focusEvidence({
      runId,
      lapNumber: null,
      lapScope: "run",
      lapWindowStart: null,
      lapWindowEnd: null,
      representativeLap: null,
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      zoneId: null,
      zoneLabel: handoff.phase,
      zoneStartPct: null,
      zoneEndPct: null,
      channelId: projection?.next_evidence_channels?.[0] ?? "yaw_rate",
      lockState: "none",
      valueBasis: "run_level",
      selectionSource: "engineer",
    }, "platform_trace");
  };

  return (
    <section
      className="dialin-panel dialin-hero handling-knowledge-card"
      data-origin="telemetry_observed"
      data-symptom={handoff.canonicalSymptomId ?? "none"}
      aria-label="Telemetry-observed handling behavior"
    >
      <div className="dialin-header">
        <div>
          <span className="eyebrow">Telemetry-observed handling behavior · not driver wording</span>
          <h3>
            {state.status === "ready" && state.projection
              ? state.projection.observed_behavior
              : "Loading the observation knowledge…"}
          </h3>
        </div>
        <span className="dialin-readonly">Observation only</span>
        <button
          className="secondary-button"
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss telemetry-observed handling knowledge"
        >
          <X size={14} /> Dismiss
        </button>
      </div>
      {state.status === "error" && (
        <div className="dialin-alert limited" role="alert">
          <AlertTriangle size={14} />
          <span>{state.error}</span>
        </div>
      )}
      {state.status === "ready" && state.projection && (
        <>
          <div className="dialin-summary-grid">
            <div>
              <span>Evidence qualification</span>
              <strong>{state.projection.evidence_qualification}</strong>
            </div>
            <div>
              <span>Phase</span>
              <strong>{cleanLabel(state.projection.phase)}</strong>
            </div>
            <div>
              <span>Canonical symptom</span>
              <strong>{state.projection.canonical_symptom_id
                ? cleanLabel(state.projection.canonical_symptom_id)
                : "None — no tight/loose claim"}</strong>
            </div>
          </div>
          {state.projection.mechanisms.length > 0 && (
            <div className="dialin-chip-row" aria-label="Mechanism evidence status">
              {state.projection.mechanisms.slice(0, 6).map((mechanism) => (
                <span
                  key={mechanism.mechanism_id}
                  className="dialin-chip"
                  data-relevance={mechanism.relevance}
                >
                  {mechanism.mechanism_id.replace("mechanism:", "")}
                  {" · "}
                  {mechanism.relevance === "blocked"
                    ? "needs more channels"
                    : mechanism.relevance === "informed_by_observation"
                      ? "informed by observation"
                      : "applicable hypothesis"}
                </span>
              ))}
            </div>
          )}
          {state.projection.relevant_knowledge.length > 0 && (
            <div className="dialin-chip-row" aria-label="Relevant setup knowledge">
              {(() => {
                const seenAreas = new Set<string>();
                return state.projection.relevant_knowledge
                  .filter((hypothesis) => {
                    if (seenAreas.has(hypothesis.setup_area)) return false;
                    seenAreas.add(hypothesis.setup_area);
                    return true;
                  })
                  .slice(0, 6)
                  .map((hypothesis) => (
                    <span key={hypothesis.bridge_id} className="dialin-chip" data-authorized={hypothesis.setup_authorized}>
                      {cleanLabel(hypothesis.setup_area)}
                      {" · "}
                      {LEVEL_LABELS[hypothesis.level] ?? hypothesis.level}
                      {hypothesis.setup_authorized ? " · P19-authorized experiment" : ""}
                      {hypothesis.relevance === "knowledge_only" ? " · catalog knowledge only" : ""}
                      {" · "}
                      {APPLICABILITY_LABELS[hypothesis.knowledge_applicability] ?? hypothesis.knowledge_applicability}
                    </span>
                  ));
              })()}
            </div>
          )}
          {state.projection.countereffects.length > 0 && (
            <p className="dialin-garage-helper">
              <b>Countereffects to protect during any future test:</b>{" "}
              {state.projection.countereffects.map((item) => cleanLabel(item)).join(" · ")}
            </p>
          )}
          {state.projection.evidence_status.length > 0 && (
            <ul className="muted handling-balance-evidence">
              {state.projection.evidence_status.slice(0, 4).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
          <div className="dialin-rule-note" data-kind={state.projection.next_action.kind}>
            <BrainCircuit size={13} aria-hidden="true" />
            <span><b>Next action:</b> {state.projection.next_action.instruction}</span>
          </div>
          <div className="tab-handoff-actions" aria-label="Handling observation handoffs">
            <button type="button" onClick={openEvidence}>
              <Search size={13} /> Review evidence
            </button>
          </div>
          <p className="section-note">
            <AlertTriangle size={12} aria-hidden="true" /> This card is telemetry-derived.
            It did not create DriverIntent and did not fill the complaint box. If the driver
            agrees with this observation, describe it in the driver's own words above.
          </p>
        </>
      )}
    </section>
  );
}
