import { AlertTriangle, BrainCircuit, Gauge, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { fetchHandlingBalance } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import {
  HANDLING_CLASSIFICATION_LABELS,
  HANDLING_PHASE_LABELS,
} from "../utils/handlingBalanceTrust";
import type { components as OpenApiComponents } from "../types/openapi.generated";

type HandlingBalanceReport = OpenApiComponents["schemas"]["HandlingBalanceReport"];
type HandlingAssessment = NonNullable<HandlingBalanceReport["assessments"]>[number];
type HandlingClassificationValue = OpenApiComponents["schemas"]["HandlingClassification"];

type HandlingBalancePanelProps = {
  runId: string;
  surface?: "overview" | "engineer";
};

type PanelState =
  | { status: "idle"; report: null; error: null }
  | { status: "loading"; report: null; error: null }
  | { status: "ready"; report: HandlingBalanceReport; error: null }
  | { status: "error"; report: null; error: string };

const QUALIFIED_KINDS = new Set([
  "kinematic_residual_observation",
  "rotation_response_deficit",
  "rotation_response_excess",
  "mixed_phase_dependent",
  "transient_rotation_anomaly",
  "steering_response_anomaly",
  "steering_demand_anomaly",
]);

function repeatabilityLabel(assessment: HandlingAssessment): string {
  if (typeof assessment.repeatability !== "string" || !assessment.repeatability) return "repeatability unstated";
  return assessment.repeatability;
}

export function HandlingBalancePanel({ runId, surface = "overview" }: HandlingBalancePanelProps) {
  const { selection, setWorkspace, focusEvidence } = useTelemetrySelection();
  const { selectedMode } = selection;
  const isLearning = selectedMode === "learning";
  const requestSeqRef = useRef(0);
  const [state, setState] = useState<PanelState>({ status: "idle", report: null, error: null });

  useEffect(() => {
    const seq = ++requestSeqRef.current;
    setState({ status: "loading", report: null, error: null });
    fetchHandlingBalance(runId)
      .then((report) => {
        if (seq === requestSeqRef.current) setState({ status: "ready", report, error: null });
      })
      .catch((reason: unknown) => {
        if (seq !== requestSeqRef.current) return;
        setState({
          status: "error",
          report: null,
          error: reason instanceof Error ? reason.message : "Handling balance is unavailable.",
        });
      });
  }, [runId]);

  const qualified = state.status === "ready"
    ? state.report.assessments?.filter((assessment) => QUALIFIED_KINDS.has(assessment.classification as HandlingClassificationValue)) ?? []
    : [];
  const primary = qualified[0] ?? null;

  if (state.status === "idle" || state.status === "loading") {
    return null;
  }

  if (state.status === "error") {
    if (!isLearning) return null;
    return (
      <section className="workspace-section handling-balance-panel" data-ui-state="error" aria-label="Automatic handling balance">
        <h2>Handling Balance</h2>
        <p className="muted">
          <AlertTriangle size={13} /> {state.error}
        </p>
      </section>
    );
  }

  const { report } = state;
  const openPhaseEvidence = (phase: string, lapNumber: number | null) => {
    focusEvidence({
      runId,
      lapNumber,
      lapScope: lapNumber != null ? "single_lap" : "run",
      lapWindowStart: null,
      lapWindowEnd: null,
      representativeLap: null,
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      zoneId: null,
      zoneLabel: null,
      zoneStartPct: null,
      zoneEndPct: null,
      channelId: "yaw_rate",
      lockState: "none",
      valueBasis: lapNumber != null ? "full_lap" : "run_level",
      selectionSource: surface,
    }, "platform_trace");
    void phase;
  };

  if (!isLearning) {
    if (!primary || report.classification === "unavailable") return null;
    const phaseLabel = primary.phase ? HANDLING_PHASE_LABELS[primary.phase] ?? primary.phase : "phase unknown";
    const symptom = primary.canonical_symptom_id ? ` · symptom ${primary.canonical_symptom_id.replace(/_/g, " ")}` : "";
    return (
      <section className="handling-balance-race-line" data-ui-state="qualified" aria-label="Automatic handling observation">
        <Gauge size={14} aria-hidden="true" />
        <span>
          <b>Handling</b>{" "}
          {HANDLING_CLASSIFICATION_LABELS[primary.classification] ?? primary.classification} in {phaseLabel}
          {symptom}. Telemetry-observed · observation only.
        </span>
        <button type="button" onClick={() => setWorkspace("engineer", surface)}>
          <BrainCircuit size={13} /> Investigate
        </button>
      </section>
    );
  }

  return (
    <section className="workspace-section handling-balance-panel" data-ui-state="ready" aria-label="Automatic handling balance">
      <div className="section-header-row">
        <div>
          <h2>Handling Balance</h2>
          <p className="muted">
            {HANDLING_CLASSIFICATION_LABELS[report.classification] ?? report.classification}
            {" · "}{report.eligible_laps} eligible laps · observation only, never a setup call.
          </p>
        </div>
        <span className="dialin-readonly">Observation only</span>
      </div>
      {report.assessments == null || report.assessments.length === 0 ? (
        <p className="muted">No phase-local handling observations qualified for this run.</p>
      ) : (
        <ul className="handling-balance-list">
          {report.assessments.map((assessment) => (
            <li key={assessment.assessment_id} className="handling-balance-item" data-classification={assessment.classification}>
              <div className="handling-balance-item-head">
                <strong>{HANDLING_CLASSIFICATION_LABELS[assessment.classification] ?? assessment.classification}</strong>
                <span className="handling-balance-item-phase">
                  {assessment.phase ? HANDLING_PHASE_LABELS[assessment.phase] ?? assessment.phase : "run"}
                  {" · "}{repeatabilityLabel(assessment)}
                </span>
                <button
                  type="button"
                  onClick={() => openPhaseEvidence(assessment.phase ?? "", assessment.lap_numbers?.[0] ?? null)}
                >
                  <Search size={13} /> Review telemetry
                </button>
              </div>
              <p>{assessment.observation_text}</p>
              {assessment.canonical_symptom_id && (
                <p className="handling-balance-symptom">
                  Canonical symptom <code>{assessment.canonical_symptom_id}</code> — telemetry-observed, not driver testimony.
                </p>
              )}
              {isLearning && assessment.phase_observations?.[0]?.corroboration != null && (
                <p className="handling-balance-corroboration" data-corroborated={
                  assessment.phase_observations[0].corroboration?.corroborated === true
                }>
                  {assessment.phase_observations[0].corroboration.corroborated
                    ? "Two independent strands corroborate: kinematic residual + steering-demand response."
                    : "Kinematic diagnostic only — the residual is a sideslip-rate proxy and cannot establish tight or loose on its own."}
                </p>
              )}
              {isLearning && assessment.supporting_evidence && assessment.supporting_evidence.length > 0 && (
                <ul className="muted handling-balance-evidence">
                  {assessment.supporting_evidence.slice(0, 2).map((line) => <li key={line}>{line}</li>)}
                </ul>
              )}
              {isLearning && assessment.contradicting_evidence && assessment.contradicting_evidence.length > 0 && (
                <p className="handling-balance-contradiction">
                  {assessment.contradicting_evidence[0]}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="muted handling-balance-footnote">
        The kinematic residual is speed × actual-path curvature minus yaw rate — the planar
        sideslip rate, blind to a constant sideslip angle. A tight/loose-family symptom qualifies
        only when the steering-demand-to-response strand independently corroborates it. The
        reference is not the driver's intended path, and P19 remains the only setup authority.
      </p>
    </section>
  );
}
