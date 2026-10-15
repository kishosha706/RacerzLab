import { AlertTriangle, BrainCircuit, Gauge, Search, Wrench } from "lucide-react";
import { useEngineeringCase } from "../store/EngineeringCaseContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { HANDLING_PHASE_LABELS } from "../utils/handlingBalanceTrust";
import { writeHandlingObservationHandoff } from "../utils/handlingObservationHandoff";
import type { components as OpenApiComponents } from "../types/openapi.generated";

type HandlingInvestigationProjection =
  OpenApiComponents["schemas"]["HandlingInvestigationProjection"];
type HandlingInvestigationFinding =
  NonNullable<HandlingInvestigationProjection["findings"]>[number];

const MECHANISM_RELEVANCE_LABELS: Record<string, string> = {
  applicable: "applicable hypothesis",
  informed_by_observation: "informed by observation",
  blocked: "needs more channels",
};

const COMPONENT_RELEVANCE_LABELS: Record<string, string> = {
  mechanically_relevant: "mechanically relevant",
  observable: "observable",
  supported: "P26 supported",
  contradicted: "P26 contradicted",
  unavailable: "unavailable",
};

function phaseLabel(phase: string): string {
  return HANDLING_PHASE_LABELS[phase] ?? phase.replace(/_/g, " ");
}

type HandlingInvestigationPanelProps = {
  runId: string;
  sessionId: string;
  learning: boolean;
  surface?: "engineer" | "overview";
};

export function HandlingInvestigationPanel({
  runId,
  sessionId,
  learning,
  surface = "engineer",
}: HandlingInvestigationPanelProps) {
  const { engineeringCase, status } = useEngineeringCase();
  const { focusEvidence, setWorkspace } = useTelemetrySelection();
  const caseBound = status === "ready"
    && engineeringCase
    && engineeringCase.run_id === runId
    && engineeringCase.session_id === sessionId;
  const investigation = caseBound && engineeringCase
    ? engineeringCase.handling_investigation ?? null
    : null;

  if (!investigation) return null;

  const primary: HandlingInvestigationFinding | null =
    investigation.findings?.[0] ?? null;

  const openTrace = (finding: HandlingInvestigationFinding) => {
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
      zoneLabel: null,
      zoneStartPct: null,
      zoneEndPct: null,
      channelId: finding.next_evidence_channels?.[0] ?? "yaw_rate",
      lockState: "none",
      valueBasis: "run_level",
      selectionSource: "engineer",
    }, "platform_trace");
  };

  const openLaps = (finding: HandlingInvestigationFinding) => {
    const ref = investigation.assessment_refs?.find(
      (item) => item.assessment_id === finding.assessment_id,
    );
    const laps = ref?.lap_numbers ?? [];
    const first = laps[0] ?? null;
    const last = laps[laps.length - 1] ?? null;
    const window = first !== null && last !== null && last > first;
    focusEvidence({
      runId,
      lapNumber: first,
      lapScope: window ? "lap_window" : "single_lap",
      lapWindowStart: window ? first : null,
      lapWindowEnd: window ? last : null,
      representativeLap: first,
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      zoneId: null,
      zoneLabel: finding.phase,
      zoneStartPct: null,
      zoneEndPct: null,
      channelId: null,
      lockState: "none",
      valueBasis: "run_level",
      selectionSource: "engineer",
    }, "laps");
  };

  const openDialInKnowledge = (finding: HandlingInvestigationFinding) => {
    if (!caseBound || !engineeringCase) return;
    const ref = investigation.assessment_refs?.find(
      (item) => item.assessment_id === finding.assessment_id,
    );
    writeHandlingObservationHandoff({
      runId,
      sessionId,
      assessmentId: finding.assessment_id,
      phase: finding.phase,
      canonicalSymptomId: ref?.canonical_symptom_id ?? null,
      caseId: engineeringCase.case_id,
      caseRevision: engineeringCase.case_revision_sha256,
      caseSha256: engineeringCase.case_sha256,
    });
    setWorkspace("dial_in", "engineer");
  };

  const openSetupRelevance = (finding: HandlingInvestigationFinding) => {
    if (!caseBound || !engineeringCase) return;
    focusEvidence({
      runId,
      lapNumber: null,
      lapScope: "run",
      lapWindowStart: null,
      lapWindowEnd: null,
      representativeLap: null,
      eventId: null,
      producerId: null,
      artifactId: null,
      caseId: engineeringCase.case_id,
      caseRevision: engineeringCase.case_revision_sha256,
      caseSha256: engineeringCase.case_sha256,
      mechanismIds: finding.mechanisms?.map((item) => item.mechanism_id) ?? [],
      componentIds: finding.components?.map((item) => item.component_id) ?? [],
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      zoneId: null,
      zoneLabel: finding.phase,
      zoneStartPct: null,
      zoneEndPct: null,
      channelId: null,
      system: "setup",
      lockState: "locked",
      valueBasis: "run_level",
      selectionSource: "engineer",
    }, "setup_impact");
  };

  if (surface === "overview") {
    if (!primary) return null;
    return (
      <section
        className="handling-balance-race-line"
        data-ui-state="qualified"
        aria-label="Handling investigation status"
      >
        <BrainCircuit size={14} aria-hidden="true" />
        <span>
          <b>HANDLING INVESTIGATION</b>{" "}
          {investigation.findings?.length ?? 0} finding
          {(investigation.findings?.length ?? 0) === 1 ? "" : "s"}{" · "}
          {phaseLabel(primary.phase)} — {learning
            ? primary.next
            : "next inspection available in Engineer"}.
        </span>
        <button type="button" onClick={() => setWorkspace("engineer", "overview")}>
          <BrainCircuit size={13} /> {learning ? "Open investigation" : "Engineer"}
        </button>
      </section>
    );
  }

  if (!learning) {
    if (!primary) return null;
    return (
      <section
        className="handling-balance-race-line"
        data-ui-state="qualified"
        aria-label="Unified handling investigation"
      >
        <Gauge size={14} aria-hidden="true" />
        <span>
          <b>{phaseLabel(primary.phase).toUpperCase()} ROTATION</b>{" "}
          {primary.what} {primary.where}. Mechanical cause unresolved.
        </span>
        <button type="button" onClick={() => openTrace(primary)}>
          <Search size={13} /> Review matched traces
        </button>
        <button type="button" onClick={() => openDialInKnowledge(primary)}>
          <BrainCircuit size={13} /> Dial-In knowledge
        </button>
      </section>
    );
  }

  return (
    <section
      className="workspace-section handling-balance-panel"
      data-ui-state="ready"
      aria-label="Unified handling investigation"
    >
      <div className="section-header-row">
        <div>
          <h2>Handling Investigation</h2>
          <p className="muted">
            Derived observation view · mechanisms informed, never supported ·
            P19 authority unchanged.
          </p>
        </div>
        <span className="dialin-readonly">Observation only</span>
      </div>
      <ul className="handling-balance-list">
        {investigation.findings?.map((finding) => (
          <li
            key={finding.assessment_id}
            className="handling-balance-item"
            data-classification="mixed_phase_dependent"
          >
            <div className="handling-balance-item-head">
              <strong>{phaseLabel(finding.phase)}</strong>
              <span className="handling-balance-item-phase">{finding.where}</span>
              <button type="button" onClick={() => openTrace(finding)}>
                <Search size={13} /> Review telemetry
              </button>
              <button type="button" onClick={() => openLaps(finding)}>
                <Gauge size={13} /> Review laps
              </button>
              <button type="button" onClick={() => openSetupRelevance(finding)}>
                <Wrench size={13} /> Setup relevance
              </button>
              <button type="button" onClick={() => openDialInKnowledge(finding)}>
                <BrainCircuit size={13} /> Dial-In knowledge
              </button>
            </div>
            <p><b>What.</b> {finding.what}</p>
            <p><b>Driver.</b> {finding.driver}</p>
            <p><b>Response.</b> {finding.response}</p>
            {finding.mechanisms && finding.mechanisms.length > 0 && (
              <>
                <p><b>Mechanisms.</b> No mechanism is declared supported;
                  the observation only informs relevance.</p>
                <div className="dialin-chip-row">
                  {finding.mechanisms.slice(0, 6).map((mechanism) => (
                    <span key={mechanism.mechanism_id} className="dialin-chip">
                      {mechanism.mechanism_id.replace("mechanism:", "")}
                      {" · "}
                      {MECHANISM_RELEVANCE_LABELS[mechanism.relevance] ?? mechanism.relevance}
                    </span>
                  ))}
                </div>
              </>
            )}
            {finding.components && finding.components.length > 0 && (
              <>
                <p><b>Components.</b> Relevance is never proof of malfunction.</p>
                <div className="dialin-chip-row">
                  {finding.components.slice(0, 8).map((component) => (
                    <span key={component.component_id} className="dialin-chip">
                      {component.component_id}
                      {" · "}
                      {COMPONENT_RELEVANCE_LABELS[component.relevance] ?? component.relevance}
                    </span>
                  ))}
                </div>
              </>
            )}
            {finding.performance && finding.performance.length > 0 && (
              finding.performance.map((association) => (
                <p
                  key={association.opportunity_id}
                  className="dialin-driver-message"
                >
                  {association.wording}
                </p>
              ))
            )}
            {finding.contradictions && finding.contradictions.length > 0 && (
              <p className="handling-balance-contradiction">
                {finding.contradictions[0]}
              </p>
            )}
            {finding.uncertain && finding.uncertain.length > 0 && (
              <>
                <p><b>Unresolved.</b></p>
                <ul className="muted handling-balance-evidence">
                  {finding.uncertain.map((note) => <li key={note}>{note}</li>)}
                </ul>
              </>
            )}
            <div className="dialin-rule-note">
              <BrainCircuit size={13} aria-hidden="true" />
              <span><b>Next:</b> {finding.next}</span>
            </div>
          </li>
        ))}
      </ul>
      {investigation.evidence_dependence && investigation.evidence_dependence.length > 0 && (
        <p className="muted handling-balance-footnote">
          {investigation.evidence_dependence[0]}
        </p>
      )}
      <p className="muted handling-balance-footnote">
        <AlertTriangle size={12} aria-hidden="true" /> This is a derived view.
        It never writes DriverIntent and never authorizes a setup change.
      </p>
    </section>
  );
}
