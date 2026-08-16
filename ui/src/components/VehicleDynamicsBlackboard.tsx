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

function humanize(value: string): string {
  return value.replace(/[_:.-]+/g, " ");
}

function scopeLabel(entry: CrewChiefEvidenceEntry): string {
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

function StageSummary({ stage }: { stage: VehicleDynamicsChainStage }) {
  return <div className="vehicle-dynamics-stage" data-state={stage.evidence_state}>
    <span>{humanize(stage.stage)}</span>
    <p>{stage.summary}</p>
    <small title={stage.source_channels.length
      ? `Channels: ${stage.source_channels.join(", ")}`
      : undefined}
    >{humanize(stage.evidence_state)} · {channelSummary(stage.source_channels)}</small>
    {stage.blocker_reasons[0] && <small className="vehicle-dynamics-blocker">
      Blocked: {stage.blocker_reasons[0]}
    </small>}
  </div>;
}

export function VehicleDynamicsBlackboard({
  assessment,
  evidenceEntries,
  p19Next,
  onFocusEvidence,
}: Props) {
  const stageByKind = new Map(assessment.chain.map((stage) => [stage.stage, stage]));
  const evidenceById = new Map(
    evidenceEntries
      .filter((entry) => entry.producer_id.startsWith("p35."))
      .map((entry) => [entry.artifact_id, entry]),
  );
  const focusById = new Map(
    assessment.focus_artifacts.map((focus) => [focus.artifact_id, focus]),
  );
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

  const evidenceButton = (
    focus: VehicleDynamicsFocusArtifact | undefined,
    label: string,
  ) => {
    if (!focus) return <small>No typed focus artifact cleared this role.</small>;
    const entry = evidenceById.get(focus.artifact_id);
    if (!entry) return <small>Trusted source navigation is unavailable.</small>;
    return <button
      type="button"
      className="vehicle-dynamics-focus"
      onClick={() => onFocusEvidence(entry)}
      aria-label={`${label} · ${scopeLabel(entry)}`}
      title={`Technical provenance: ${entry.producer_id} · ${entry.artifact_id}`}
    >
      <b>{label}</b>
      <span>{scopeLabel(entry)}</span>
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

  return <section
    className="vehicle-dynamics-blackboard"
    data-applicability={assessment.applicability_state}
    data-authority={assessment.mechanism_authority}
    aria-label="Vehicle Dynamics Blackboard, candidate mechanisms only"
  >
    <header>
      <div>
        <span className="eyebrow">VEHICLE DYNAMICS BLACKBOARD · CANDIDATE ONLY</span>
        <h3>{assessment.traffic_blocked
          ? "Observed response, context-blocked attribution"
          : "Driver demand to time consequence"}</h3>
      </div>
      <span className="vehicle-dynamics-authority">
        {humanize(assessment.applicability_state)} · no setup authority
      </span>
    </header>

    <div className="vehicle-dynamics-chain" aria-label="Five-stage vehicle dynamics evidence chain">
      {assessment.chain.map((stage) => <StageSummary key={stage.stage} stage={stage} />)}
    </div>

    <div className="vehicle-dynamics-grid">
      <article>
        <h4>Performance problem</h4>
        <p>{timeConsequence.summary}</p>
        <small>{assessment.measured_time_consequence_available
          ? "Measured time consequence retained."
          : "Measured time consequence unavailable."}</small>
        {assessment.performance_opportunity_ids.length > 0
          ? <small>Opportunity: {assessment.performance_opportunity_ids.map(humanize).join(", ")}</small>
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
          ? <small>{assessment.tire_demand_state_ids.map(humanize).join(" · ")}</small>
          : <small>Typed tire-demand state unavailable; no tire-force value inferred.</small>}
      </article>

      <article>
        <h4>Load transfer / platform</h4>
        {assessment.load_path_ids.length > 0
          ? <p>{assessment.load_path_ids.map(humanize).join(" → ")}</p>
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

      <article className="vehicle-dynamics-wide">
        <h4>Mechanism candidates</h4>
        {assessment.candidates.length > 0 ? <ul className="vehicle-dynamics-candidates">
          {assessment.candidates.map((candidate) => <li key={candidate.mechanism_id}>
            <div>
              <b>{humanize(candidate.mechanism_id)}</b>
              <span>{humanize(candidate.relevance)} · candidate relevance only</span>
            </div>
            <small>{candidate.support_artifact_ids.length} support · {candidate.contradiction_artifact_ids.length} contradiction/uncertainty</small>
            {candidate.blocker_reasons[0] && <small className="vehicle-dynamics-blocker">Blocked: {candidate.blocker_reasons[0]}</small>}
          </li>)}
        </ul> : <p>No mechanism candidate cleared current evidence.</p>}
      </article>

      <article>
        <h4>Component families</h4>
        {componentFamilies.length > 0
          ? <p>{componentFamilies.map(humanize).join(" · ")}</p>
          : <p>No supported current component relevance is established.</p>}
        {!hasSupportedCandidate && componentFamilies.length > 0
          && <small>No supported current component relevance is established; every mechanism candidate is blocked.</small>}
        <small>Static candidate map only · not current P26 component relevance · zero component causal claims.</small>
      </article>

      <article>
        <h4>Strongest support</h4>
        <p>{strongestSupport?.summary ?? "No supporting focus artifact cleared."}</p>
        {evidenceButton(strongestSupport, "Open support evidence")}
      </article>

      <article>
        <h4>Strongest contradiction</h4>
        <p>{strongestContradiction?.summary ?? "No contradiction or uncertainty focus cleared."}</p>
        {evidenceButton(strongestContradiction, "Open contradiction evidence")}
      </article>

      <article>
        <h4>What would separate them?</h4>
        <p>{discriminator?.summary
          ?? (assessment.next_discriminator_contract_id === null
            ? "No candidate-owned discriminator is available."
            : humanize(assessment.next_discriminator_contract_id))}</p>
        {evidenceButton(discriminator, "Open discriminator evidence")}
      </article>

      <article className="vehicle-dynamics-next">
        <h4>NEXT · P19</h4>
        <p>{p19Next}</p>
        <small>P19 remains the sole terminal cause, test, and setup authority.</small>
      </article>
    </div>

    <footer>
      {assessment.unavailable_quantity_ids.length} exact physics quantities withheld · observation only · candidate mechanisms only · setup authorization false
    </footer>
  </section>;
}
