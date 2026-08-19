import { useId } from "react";

import type { CrewChiefEvidenceEntry } from "../types/crewChief";
import type {
  PerformanceMechanismAssessment,
  VehicleDynamicsChainStage,
  VehicleDynamicsFocusArtifact,
} from "../types/vehicleDynamics";

type Props = {
  assessment: PerformanceMechanismAssessment;
  evidenceEntries: readonly CrewChiefEvidenceEntry[];
  p19Next: string;
  onFocusEvidence: (entry: CrewChiefEvidenceEntry) => void;
};

type BlackboardUiState = "ready" | "blocked" | "empty" | "unavailable";

type BlackboardPresentation = {
  state: BlackboardUiState;
  label: string;
  title: string;
  detail: string;
};

type EvidenceScope = Pick<
  CrewChiefEvidenceEntry,
  "lap_numbers" | "lap_pct_start" | "lap_pct_end" | "phase"
>;

function humanize(value: string): string {
  return value.replace(/[_:.-]+/g, " ");
}

function displayTypedId(value: string): string {
  const parts = value.split(":");
  return humanize(parts[parts.length - 1] ?? value);
}

function inspectionLabel(value: string): string {
  return humanize(value.replace(/^inspect_/, ""));
}

function responseMetricLabel(value: string): string {
  return ({
    elapsed_time_delta_s: "Phase time",
    speed_delta_mph: "Speed response",
    throttle_demand_delta_pct: "Throttle demand",
    brake_demand_delta_pct: "Brake demand",
    steering_wheel_demand_delta_deg: "Steering-wheel demand",
    yaw_rate_response_delta_rad_s: "Yaw response",
    longitudinal_accel_response_delta_mps2: "Acceleration response",
    path_delta_m: "Path delta",
    line_separation_m: "Line separation",
  } as Record<string, string>)[value] ?? humanize(value);
}

function signedMetric(value: number, units: string): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(3)} ${units}`;
}

function operationalRelationLabel(value: string): string {
  return ({
    brake_to_pressure: "BRAKE → PRESSURE",
    brake_to_deceleration: "BRAKE → DECELERATION",
    brake_to_yaw: "BRAKE → YAW",
    brake_release_to_yaw: "RELEASE → YAW",
    throttle_to_acceleration: "THROTTLE → ACCELERATION",
    throttle_to_yaw: "THROTTLE → YAW",
    steering_wheel_to_yaw: "STEERING-WHEEL → YAW",
    disturbance_to_chassis: "DISTURBANCE → CHASSIS",
    stint_migration: "STINT MIGRATION",
  } as Record<string, string>)[value] ?? humanize(value).toUpperCase();
}

function operationalMetricValue(value: number, units: string): string {
  return `${value.toFixed(units === "count" ? 1 : 3)} ${units}`;
}

function scopeLabel(entry: EvidenceScope): string {
  const laps = entry.lap_numbers.length === 0
    ? "run scope"
    : entry.lap_numbers.length === 1
      ? `lap ${entry.lap_numbers[0]}`
      : `laps ${entry.lap_numbers.join(", ")}`;
  const window = entry.lap_pct_start === null || entry.lap_pct_end === null
    ? null
    : `${entry.lap_pct_start.toFixed(1)}–${entry.lap_pct_end.toFixed(1)}%`;
  return [laps, entry.phase && humanize(entry.phase), window]
    .filter((item): item is string => Boolean(item))
    .join(" · ");
}

function channelSummary(channels: readonly string[]): string {
  if (channels.length === 0) return "channels unavailable";
  const visible = channels.slice(0, 3).join(", ");
  return channels.length > 3 ? `${visible} · +${channels.length - 3} more` : visible;
}

function responseEvidenceHeadline(
  assessment: PerformanceMechanismAssessment,
): string | null {
  const state = assessment.chain.find(
    (stage) => stage.stage === "vehicle_response",
  )?.evidence_state;
  if (state === "measured" || state === "observed_correlation") return "Observed response";
  if (state === "calculated") return "Calculated response";
  if (state === "estimated_proxy") return "Response proxy";
  if (state === "controlled_test_effect") return "Controlled response effect";
  return null;
}

function assessmentPresentation(
  assessment: PerformanceMechanismAssessment,
  supportedCandidateCount: number,
): BlackboardPresentation {
  const candidateBlockers = assessment.candidates.flatMap(
    (candidate) => candidate.blocker_reasons,
  );
  const stageBlockers = assessment.chain.flatMap((stage) => stage.blocker_reasons);
  const attributionBlockers = [
    ...candidateBlockers,
    ...stageBlockers,
    ...assessment.blocker_reasons,
  ];
  const attributionBlocker = assessment.traffic_blocked
    ? attributionBlockers.find((blocker) => /traffic/i.test(blocker))
      ?? attributionBlockers[0]
    : attributionBlockers[0];

  if (assessment.applicability_state !== "ready") {
    return {
      state: "unavailable",
      label: humanize(assessment.applicability_state),
      title: "Vehicle dynamics assessment unavailable",
      detail: assessment.applicability_blockers[0]
        ?? assessment.blocker_reasons[0]
        ?? "The current car, build, track package, or evidence scope is unavailable for P35.",
    };
  }
  if (assessment.traffic_blocked || (
    assessment.candidates.length > 0 && supportedCandidateCount === 0
  )) {
    const responseHeadline = responseEvidenceHeadline(assessment);
    const title = responseHeadline
      ? `${responseHeadline}, attribution blocked`
      : assessment.measured_time_consequence_available
        ? "Measured time, attribution blocked"
        : "Attribution blocked";
    return {
      state: "blocked",
      label: "Attribution blocked",
      title,
      detail: attributionBlocker
        ?? "Measured time remains visible, but current evidence cannot clear mechanism attribution.",
    };
  }
  if (assessment.candidates.length === 0) {
    const responseHeadline = responseEvidenceHeadline(assessment);
    return {
      state: "empty",
      label: "No candidate cleared",
      title: assessment.measured_time_consequence_available
        ? "Measured time, no mechanism candidate"
        : responseHeadline
          ? `${responseHeadline}, no mechanism candidate`
          : "No mechanism candidate",
      detail: assessment.measured_time_consequence_available
        ? "Measured P32 time remains visible; no mechanism candidate cleared this evidence scope."
        : "The typed chain remains visible; neither measured time nor a mechanism candidate cleared this scope.",
    };
  }
  return {
    state: "ready",
    label: "Candidate review",
    title: "Driver demand to time consequence",
    detail: `${supportedCandidateCount} candidate${supportedCandidateCount === 1 ? "" : "s"} ${supportedCandidateCount === 1 ? "has" : "have"} typed support. Candidate-only relevance still requires contradiction review and a P19 decision.`,
  };
}

function StageSummary({
  stage,
  index,
}: {
  stage: VehicleDynamicsChainStage;
  index: number;
}) {
  const fullChannelLabel = stage.source_channels.length
    ? `Channels: ${stage.source_channels.join(", ")}`
    : "Channels unavailable";

  return <li className="vehicle-dynamics-stage" data-state={stage.evidence_state}>
    <div className="vehicle-dynamics-stage-heading">
      <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
      <h4>{humanize(stage.stage)}</h4>
    </div>
    <p>{stage.summary}</p>
    <div className="vehicle-dynamics-stage-meta">
      <span data-state={stage.evidence_state}>{humanize(stage.evidence_state)}</span>
      {stage.source_channels.length > 0
        ? <details className="vehicle-dynamics-channels">
          <summary>{channelSummary(stage.source_channels)}</summary>
          <small>{fullChannelLabel}</small>
        </details>
        : <small>channels unavailable</small>}
    </div>
    {stage.blocker_reasons[0] && <small className="vehicle-dynamics-blocker">
      Blocked: {stage.blocker_reasons[0]}
    </small>}
  </li>;
}

export function VehicleDynamicsBlackboard({
  assessment,
  evidenceEntries,
  p19Next,
  onFocusEvidence,
}: Props) {
  const stateDescriptionId = useId();
  const stageByKind = new Map(assessment.chain.map((stage) => [stage.stage, stage]));
  const evidenceById = new Map(
    evidenceEntries
      .filter((entry) => entry.producer_id.startsWith("p35."))
      .map((entry) => [entry.artifact_id, entry]),
  );
  const focusById = new Map(
    assessment.focus_artifacts.map((focus) => [focus.artifact_id, focus]),
  );
  const opportunityEntry = assessment.performance_opportunity_ids
    .map((artifactId) => evidenceEntries.find((entry) => entry.artifact_id === artifactId))
    .find((entry): entry is CrewChiefEvidenceEntry => entry !== undefined);
  const driverInput = stageByKind.get("driver_input")!;
  const vehicleDemand = stageByKind.get("vehicle_demand")!;
  const vehicleResponse = stageByKind.get("vehicle_response")!;
  const tirePlatform = stageByKind.get("tire_platform_state")!;
  const timeConsequence = stageByKind.get("time_consequence")!;
  const componentFamilies = [...new Set(
    assessment.candidates.flatMap((candidate) => candidate.component_family_ids),
  )];
  const hasSupportedCandidate = assessment.candidates.some(
    (candidate) => candidate.relevance === "candidate",
  );
  const supportedCandidateCount = assessment.candidates.filter(
    (candidate) => candidate.relevance === "candidate",
  ).length;
  const presentation = assessmentPresentation(assessment, supportedCandidateCount);
  // Trusted API payloads require these fields. Keep the component defensive for
  // stale in-memory fixtures or a pre-P35.4 view that survives hot reload.
  const responseObservation = assessment.response_observations?.[0];
  const problemSignature = assessment.problem_signature ?? null;
  const mechanismSeparation = assessment.mechanism_separation ?? [];

  const evidenceButton = (
    focus: VehicleDynamicsFocusArtifact | undefined,
    label: string,
  ) => {
    if (!focus) return <small className="vehicle-dynamics-empty">
      No typed focus artifact cleared this role.
    </small>;
    const entry = evidenceById.get(focus.artifact_id);
    if (!entry) return <small className="vehicle-dynamics-empty">
      Trusted source navigation is unavailable.
    </small>;
    const scope = scopeLabel(entry);
    return <button
      type="button"
      className="vehicle-dynamics-focus"
      onClick={() => onFocusEvidence(entry)}
      aria-label={`${label} · ${scope}`}
      title={`Technical provenance: ${entry.producer_id} · ${entry.artifact_id}`}
    >
      <span className="vehicle-dynamics-focus-action">
        <b>{label}</b>
        <span aria-hidden="true">↗</span>
      </span>
      <span className="vehicle-dynamics-focus-scope">{scope}</span>
    </button>;
  };

  const strongestSupport = assessment.strongest_support_artifact_id === null
    ? undefined
    : focusById.get(assessment.strongest_support_artifact_id);
  const strongestContradiction = assessment.strongest_contradiction_artifact_id === null
    ? undefined
    : focusById.get(assessment.strongest_contradiction_artifact_id);
  const discriminator = assessment.next_discriminator_contract_id === null
    ? undefined
    : assessment.focus_artifacts.find(
      (focus) => focus.observation_contract_id === assessment.next_discriminator_contract_id,
    );
  const strongestChallengeKind = strongestContradiction?.polarity === "uncertainty"
    ? "uncertainty"
    : "contradiction";
  const strongestChallengeHeading = strongestChallengeKind === "uncertainty"
    ? "Strongest uncertainty"
    : "Strongest contradiction";
  const strongestChallengeAction = strongestChallengeKind === "uncertainty"
    ? "Open uncertainty evidence"
    : "Open contradiction evidence";
  const strongestChallengeSummary = strongestContradiction?.summary.replace(
    /^Strongest contradiction or uncertainty:\s*/i,
    "",
  ) ?? "No contradiction or uncertainty focus cleared.";

  return <section
    className="vehicle-dynamics-blackboard"
    data-applicability={assessment.applicability_state}
    data-authority={assessment.mechanism_authority}
    data-ui-state={presentation.state}
    aria-label="Vehicle Dynamics Blackboard, candidate mechanisms only"
    aria-describedby={stateDescriptionId}
  >
    <header>
      <div className="vehicle-dynamics-title">
        <span className="eyebrow">VEHICLE DYNAMICS BLACKBOARD · CANDIDATE ONLY</span>
        <h3>{presentation.title}</h3>
        <p id={stateDescriptionId}>{presentation.detail}</p>
      </div>
      <div className="vehicle-dynamics-status-stack">
        <span className="vehicle-dynamics-state" data-state={presentation.state}>
          {presentation.label}
        </span>
        <span className="vehicle-dynamics-authority">
          {assessment.applicability_state === "ready"
            ? "reviewed build · graph applicable"
            : `${humanize(assessment.applicability_state)} · graph unavailable`} · observation only
        </span>
      </div>
    </header>

    <div className="vehicle-dynamics-chain-intro">
      <h4>Five-stage evidence chain</h4>
      <p>Read left to right. Every step keeps its own evidence state and source channels.</p>
    </div>
    <ol className="vehicle-dynamics-chain" aria-label="Five-stage vehicle dynamics evidence chain">
      {assessment.chain.map((stage, index) => <StageSummary
        key={stage.stage}
        stage={stage}
        index={index}
      />)}
    </ol>

    <div className="vehicle-dynamics-grid">
      {problemSignature && responseObservation && <article
        className="vehicle-dynamics-wide vehicle-response-story"
        aria-label="Phase-resolved vehicle problem signature"
      >
        <div className="vehicle-dynamics-section-heading">
          <h4>Phase-resolved car state</h4>
          <span>{humanize(responseObservation.evidence_state)}</span>
        </div>
        <dl className="vehicle-response-story-grid">
          <div>
            <dt>WHAT</dt>
            <dd>{signedMetric(problemSignature.local_time_delta_s, "s")} · {humanize(problemSignature.phase)}</dd>
          </div>
          <div>
            <dt>ONSET</dt>
            <dd>{problemSignature.onset_pct.toFixed(1)}% lap · {humanize(problemSignature.onset_resolution)} resolution</dd>
          </div>
          <div>
            <dt>DRIVER</dt>
            <dd>Demand {humanize(problemSignature.driver_demand_state)} · line {humanize(problemSignature.line_state)}</dd>
          </div>
          <div>
            <dt>CAR RESPONSE</dt>
            <dd>{humanize(problemSignature.vehicle_response_state)} · {humanize(problemSignature.response_regime)}</dd>
          </div>
          <div>
            <dt>PERSISTENCE</dt>
            <dd>{humanize(responseObservation.persistence)}</dd>
          </div>
          <div>
            <dt>CONTEXT</dt>
            <dd>Traffic {humanize(problemSignature.traffic_dependence)}</dd>
          </div>
        </dl>
        <ul className="vehicle-response-metrics" aria-label="Measured response deltas">
          {responseObservation.metrics.map((metric) => <li key={metric.metric_id}>
            <span>{responseMetricLabel(metric.quantity)}</span>
            <b>{signedMetric(metric.value, metric.units)}</b>
          </li>)}
        </ul>
        {assessment.operational_response_evidence.length > 0 && <div
          className="vehicle-operational-response"
          aria-label="Qualified operational response evidence"
        >
          {assessment.operational_response_evidence.map((evidence) => <section
            key={evidence.evidence_id}
            data-relation={evidence.relation}
          >
            <div>
              <b>{operationalRelationLabel(evidence.relation)}</b>
              <small>{evidence.repetition_count} independent laps · {humanize(evidence.evidence_state)}</small>
            </div>
            <ul>
              {evidence.metrics.slice(0, evidence.relation === "stint_migration" ? 10 : 8).map((metric) => <li key={metric.metric_id}>
                <span>{metric.corner ? `${metric.corner.toUpperCase()} ` : ""}{metric.label}{metric.lap_number !== null ? ` · L${metric.lap_number}` : ""}</span>
                <b>{operationalMetricValue(metric.value, metric.units)}</b>
              </li>)}
            </ul>
            {evidence.speed_median_mps !== null && <small>
              Observed speed band {evidence.speed_min_mps?.toFixed(1)}–{evidence.speed_max_mps?.toFixed(1)} m/s · median {evidence.speed_median_mps.toFixed(1)} m/s
            </small>}
            {evidenceById.get(evidence.evidence_id) && <button
              type="button"
              className="vehicle-dynamics-focus"
              onClick={() => onFocusEvidence(evidenceById.get(evidence.evidence_id)!)}
            >
              Open connected response evidence
            </button>}
          </section>)}
        </div>}
        <small>Steering values are steering-wheel demand, never road-wheel angle. Onset is only shown at the resolution currently measured.</small>
      </article>}

      <article className="vehicle-dynamics-summary-card">
        <h4>Performance problem</h4>
        <p>{timeConsequence.summary}</p>
        <small>{assessment.measured_time_consequence_available
          ? "Measured time consequence retained."
          : "Measured time consequence unavailable."}</small>
        {assessment.performance_opportunity_ids.length > 0
          ? <small>{opportunityEntry
            ? `Measured comparison · ${scopeLabel(opportunityEntry)}`
            : "Measured P32 opportunity is bound to this scope."}</small>
          : <small>No P32 opportunity cleared this scope.</small>}
      </article>

      <article>
        <h4>Driver demand</h4>
        <p><b>Input</b> {driverInput.summary}</p>
        <p><b>Demand</b> {vehicleDemand.summary}</p>
        {[...driverInput.blocker_reasons, ...vehicleDemand.blocker_reasons][0]
          && <small className="vehicle-dynamics-blocker">Unresolved: {[...driverInput.blocker_reasons, ...vehicleDemand.blocker_reasons][0]}</small>}
      </article>

      <article>
        <h4>Vehicle response</h4>
        <p>{vehicleResponse.summary}</p>
        <small>{humanize(vehicleResponse.evidence_state)} · observation only</small>
      </article>

      <article>
        <h4>Tire demand</h4>
        <p>{tirePlatform.summary}</p>
        {assessment.tire_demand_state_ids.length > 0
          ? <small>{assessment.tire_demand_state_ids.map(displayTypedId).join(" · ")}</small>
          : <small>Typed tire-demand state unavailable; no tire-force value inferred.</small>}
      </article>

      <article>
        <h4>Load transfer / platform</h4>
        {assessment.load_path_ids.length > 0
          ? <p>{assessment.load_path_ids.map(displayTypedId).join(" → ")}</p>
          : <p>No load-path candidate cleared current evidence.</p>}
        <small>Relative platform state only · exact wheel load remains unavailable.</small>
      </article>

      <article>
        <h4>Transient or steady-state?</h4>
        <p>{assessment.response_regime === null
          ? "Unresolved from current typed evidence."
          : humanize(assessment.response_regime)}</p>
        <small>Response regime describes timing; it does not establish cause.</small>
      </article>

      <article className="vehicle-dynamics-wide vehicle-dynamics-mechanisms">
        <div className="vehicle-dynamics-section-heading">
          <h4>Mechanism candidates</h4>
          <span>{assessment.candidates.length} {assessment.candidates.length === 1
            ? "candidate"
            : "candidates"}</span>
        </div>
        {assessment.candidates.length > 0 ? <ul className="vehicle-dynamics-candidates">
          {assessment.candidates.map((candidate) => <li
            key={candidate.mechanism_id}
            data-relevance={candidate.relevance}
          >
            <div>
              <b>{displayTypedId(candidate.mechanism_id)}</b>
              <span className="vehicle-dynamics-candidate-state">
                {humanize(candidate.relevance)} · candidate relevance only
              </span>
            </div>
            <small>{candidate.support_artifact_ids.length} support · {candidate.contradiction_artifact_ids.length} contradiction/uncertainty</small>
            {candidate.blocker_reasons[0] && <small className="vehicle-dynamics-blocker">Blocked: {candidate.blocker_reasons[0]}</small>}
          </li>)}
        </ul> : <p>No mechanism candidate cleared current evidence.</p>}
      </article>

      {mechanismSeparation.length > 0 && <article
        className="vehicle-dynamics-wide vehicle-dynamics-separation"
      >
        <div className="vehicle-dynamics-section-heading">
          <h4>Mechanism separation</h4>
          <span>support · contradiction · discriminator</span>
        </div>
        <div className="vehicle-dynamics-separation-scroll">
          <table>
            <thead><tr>
              <th>Mechanism</th>
              <th>State</th>
              <th>Support</th>
              <th>Response evidence</th>
              <th>Contradiction</th>
              <th>Missing evidence</th>
              <th>Best discriminator</th>
            </tr></thead>
            <tbody>{mechanismSeparation.map((row) => <tr key={row.mechanism_id}>
              <th>{displayTypedId(row.mechanism_id)}</th>
              <td>{humanize(row.state)}</td>
              <td>{row.support_artifact_ids.length || "none"}</td>
              <td>{row.response_evidence_ids.length > 0
                ? row.response_evidence_ids.map((id) => {
                  const evidence = assessment.operational_response_evidence.find((item) => item.evidence_id === id);
                  return evidence ? operationalRelationLabel(evidence.relation) : "unavailable";
                }).join(" · ")
                : "none"}</td>
              <td>{row.contradiction_artifact_ids.length}</td>
              <td>{row.missing_evidence[0]}</td>
              <td>{displayTypedId(row.discriminator_contract_ids[0] ?? "unavailable")}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <small>Component families remain mechanically relevant possibilities only. Exact control authority stays with P19.</small>
      </article>}

      <article className="vehicle-dynamics-components">
        <h4>Component families</h4>
        {!hasSupportedCandidate && componentFamilies.length > 0
          && <strong className="vehicle-dynamics-map-label">
            Static possibility map · not current attribution
          </strong>}
        {componentFamilies.length > 0
          ? <p>{componentFamilies.map(displayTypedId).join(" · ")}</p>
          : <p>No supported current component relevance is established.</p>}
        <small>{assessment.candidates.length === 0
          ? "No current P26 relevance or component causation is established."
          : hasSupportedCandidate
            ? "Static candidate map only; current P26 relevance remains unproven; zero component causal claims."
            : "Every candidate is blocked; current P26 relevance and component causation remain unproven."}</small>
      </article>

      <article className="vehicle-dynamics-evidence-card" data-evidence-role="support">
        <h4>Strongest support</h4>
        <p>{strongestSupport?.summary ?? "No supporting focus artifact cleared."}</p>
        {evidenceButton(strongestSupport, "Open support evidence")}
      </article>

      <article className="vehicle-dynamics-evidence-card" data-evidence-role="contradiction">
        <h4>{strongestChallengeHeading}</h4>
        <p>{strongestChallengeSummary}</p>
        {evidenceButton(strongestContradiction, strongestChallengeAction)}
      </article>

      <article className="vehicle-dynamics-evidence-card" data-evidence-role="discriminator">
        <h4>Next bounded inspection</h4>
        <p>{discriminator?.summary
          ?? (assessment.next_discriminator_contract_id === null
            ? "No candidate-owned discriminator is available."
            : humanize(assessment.next_discriminator_contract_id))}</p>
        {discriminator && <dl className="vehicle-dynamics-discriminator-detail">
          <div>
            <dt>Inspection</dt>
            <dd>{inspectionLabel(discriminator.inspection_tool_id)}</dd>
          </div>
          <div>
            <dt>Current source context</dt>
            <dd>{discriminator.source_channels.length > 0
              ? <details className="vehicle-dynamics-source-context">
                <summary>{channelSummary(discriminator.source_channels)}</summary>
                <span>{discriminator.source_channels.join(", ")}</span>
              </details>
              : "No source channels are projected in this focus artifact."}</dd>
          </div>
          <div>
            <dt>Evidence scope</dt>
            <dd>{scopeLabel(discriminator)}</dd>
          </div>
          <div>
            <dt>Current blocker</dt>
            <dd>{discriminator.blocker_reasons[0]
              ?? "No current blocker is projected in this focus artifact."}</dd>
          </div>
        </dl>}
        {evidenceButton(discriminator, "Open discriminator evidence")}
      </article>

      <article className="vehicle-dynamics-next">
        <h4>NEXT · P19</h4>
        <p>{p19Next}</p>
        <small>P19 remains the sole terminal cause, test, and setup authority.</small>
      </article>
    </div>

    <footer aria-label="Vehicle dynamics authority boundary">
      <span>{assessment.unavailable_quantity_ids.length} exact physics quantities withheld</span>
      <span>Observation only</span>
      <span>Candidate mechanisms only</span>
      <span>no setup authority</span>
    </footer>
  </section>;
}
