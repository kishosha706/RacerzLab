import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CheckCircle2,
  CircleHelp,
  FlaskConical,
  Gauge,
  History,
  Link2,
  RefreshCcw,
  Search,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchLearningReadiness,
  freezeProspectivePrediction,
  fetchRunIntelligence,
  queryRunIntelligence,
  startEvidenceCampaign,
} from "../api/client";
import {
  exactMindChangeCriteria,
  MindChangeCriteriaCard,
  SmartIntelligenceCards,
} from "../components/SmartIntelligenceCards";
import { EngineeringAwarenessPanel } from "../components/EngineeringAwarenessPanel";
import { VehicleSystemsPanel } from "../components/VehicleSystemsPanel";
import { CrewChiefCommandDeck } from "../components/CrewChiefCommandDeck";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { LapScope } from "../store/types";
import type {
  IntelligenceCitation,
  IntelligenceDataQuality,
  IntelligenceMeasurement,
  IntelligenceQueryResponse,
  RunIntelligenceReport,
} from "../types/intelligence";
import type { EvidenceState } from "../types/telemetry";
import type { LearningReadinessProjection } from "../types/learningReadiness";
import type { CrewChiefEvidenceEntry } from "../types/crewChief";
import type { LearningEvidenceReference } from "../types/engineeringLearning";
import { isVehicleSystemComponentId } from "../types/vehicleSystems";
import { deriveCurrentReportSetupAuthority } from "../utils/currentIntelligenceAuthority";
import {
  isIntelligenceQueryResponseBoundToReport,
  isRunIntelligenceResponse,
} from "../utils/intelligenceResponseTrust";
import {
  exactEventIdentitySet,
  intelligenceMoveScope,
  intelligenceWorkspaceTarget,
  trustedNavigationMove,
  trustedQueryNavigationCitation,
  trustedSetupAuthorizedMove,
} from "../utils/intelligenceNavigation";

type EngineerTabProps = {
  runId: string;
  sessionId: string | null;
  selectedLap: number | null;
  selectedLapScope: LapScope;
  selectedLapWindowStart: number | null;
  selectedLapWindowEnd: number | null;
  selectedRepresentativeLap: number | null;
  sessionRunScopeKey: string;
  workflowId: string | null;
  workflowUpdatedAt: string | null;
  onNavigateCitation: (citation: IntelligenceCitation) => void | Promise<void>;
  onNavigateCrewEvidence: (entry: CrewChiefEvidenceEntry | LearningEvidenceReference) => void | Promise<void>;
};

type ReportLoadState = {
  requestKey: string;
  status: "loading" | "ready" | "error";
  report: RunIntelligenceReport | null;
  error: string | null;
};

type QueryState = {
  requestKey: string | null;
  status: "idle" | "loading" | "ready" | "error";
  response: IntelligenceQueryResponse | null;
  error: string | null;
};

type ReadinessLoadState = {
  requestKey: string | null;
  status: "idle" | "loading" | "ready" | "error";
  projection: LearningReadinessProjection | null;
  error: string | null;
};

type CampaignActionState = {
  campaignKind: string | null;
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
};

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function evidenceStateSupportsAction(state: EvidenceState): boolean {
  return [
    "measured",
    "calculated",
    "estimated_proxy",
    "observed_correlation",
    "controlled_test_effect",
  ].includes(state);
}

function controlledTestStateSupportsAction(state: EvidenceState): boolean {
  return state === "needs_confirmation" || evidenceStateSupportsAction(state);
}

function scopeMatches(
  payload: { run_id?: string; session_id?: string | null },
  runId: string,
  sessionId: string | null,
): boolean {
  return payload.run_id === runId && (payload.session_id ?? null) === sessionId;
}

function stateLabel(state: string): string {
  return state.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function driverFacingLabel(value: string): string {
  return value.replace(/\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/g, (token) => (
    token.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase())
  ));
}

function driverFacingIssue(issue: string | null | undefined): string {
  if (!issue) return "No evidence-qualified issue";
  return driverFacingLabel(issue);
}

function narrativeTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

const ENGINEER_MISSION_HEADLINES: Record<NonNullable<RunIntelligenceReport["mission_stage"]>, string> = {
  qualify: "Make the run trustworthy",
  diagnose: "Name the repeatable loss",
  measure: "Collect the missing proof",
  test: "Run one controlled change",
  compare: "Compare A, B, and A2",
  decide: "Keep, undo, or retest",
  certified: "Carry forward verified learning",
};

function citationMeta(citation: IntelligenceCitation): string {
  const parts: string[] = [];
  if (citation.track_region_label) parts.push(citation.track_region_label);
  if (citation.lap_number != null) parts.push(`Lap ${citation.lap_number}`);
  if (citation.lap_pct != null && Number.isFinite(citation.lap_pct)) {
    parts.push(`${citation.lap_pct.toFixed(1)}%`);
  }
  const channels = asArray(citation.source_channels);
  if (channels.length > 0) parts.push(channels.slice(0, 2).join(" + "));
  return parts.join(" · ");
}

function CitationLinks({
  citations,
  onNavigate,
  label = "Evidence",
}: {
  citations: IntelligenceCitation[] | null | undefined;
  onNavigate: EngineerTabProps["onNavigateCitation"];
  label?: string;
}) {
  const visible = asArray(citations);
  if (visible.length === 0) return null;
  return (
    <div className="engineer-citations" aria-label={label}>
      {visible.map((citation) => (
        <button
          key={citation.citation_id}
          type="button"
          className="engineer-citation"
          onClick={() => { void onNavigate(citation); }}
          title={`Open exact evidence in ${citation.workspace.replace(/_/g, " ")}`}
        >
          <Link2 size={12} aria-hidden="true" />
          <span>
            <strong>{citation.label}</strong>
            {citationMeta(citation) && <small>{citationMeta(citation)}</small>}
          </span>
          <em data-valid={citation.valid_for_tuning ? "true" : "false"}>
            {citation.valid_for_tuning ? stateLabel(citation.evidence_state) : "Evidence only"}
          </em>
        </button>
      ))}
    </div>
  );
}

function DataQualityCard({
  quality,
  learning,
  onNavigate,
}: {
  quality: IntelligenceDataQuality;
  learning: boolean;
  onNavigate: EngineerTabProps["onNavigateCitation"];
}) {
  const StatusIcon = quality.status === "ready"
    ? CheckCircle2
    : quality.status === "limited" ? AlertTriangle : XCircle;
  const firstIssue = asArray(quality.issues)[0];
  const firstRecoveryStep = asArray(quality.recovery_steps)[0];
  return (
    <section className="engineer-quality-card" data-status={quality.status} aria-labelledby="engineer-quality-heading">
      <header>
        <span className="engineer-card-icon"><StatusIcon size={15} aria-hidden="true" /></span>
        <div>
          <span className="eyebrow">Data quality</span>
          <h3 id="engineer-quality-heading">{quality.summary}</h3>
        </div>
        <span className="engineer-quality-state">{quality.status}</span>
      </header>
      <div className="engineer-quality-metrics" aria-label="Evidence qualification counts">
        <span><strong>{quality.eligible_laps}</strong> / {quality.total_laps} eligible laps</span>
        <span><strong>{quality.trusted_events}</strong> trusted events</span>
      </div>
      {!learning && quality.status !== "ready" && (firstIssue || firstRecoveryStep) && (
        <div className="engineer-quality-recovery" role="note" aria-label="First evidence recovery step">
          {firstIssue && <p><strong>Blocked by:</strong> {firstIssue}</p>}
          {firstRecoveryStep && <p><strong>Do next:</strong> {firstRecoveryStep}</p>}
        </div>
      )}
      {learning && (
        <div className="engineer-quality-detail">
          {asArray(quality.issues).length > 0 && (
            <div>
              <h4>Limits</h4>
              <ul>{quality.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
            </div>
          )}
          {asArray(quality.recovery_steps).length > 0 && (
            <div>
              <h4>Recover the evidence</h4>
              <ol>{quality.recovery_steps.map((step) => <li key={step}>{step}</li>)}</ol>
            </div>
          )}
          <CitationLinks citations={quality.citations} onNavigate={onNavigate} label="Data-quality evidence" />
        </div>
      )}
    </section>
  );
}

function LearningReadinessCard({
  state,
  campaignAction,
  predictionAction,
  onFreezePrediction,
  onStartCampaign,
}: {
  state: ReadinessLoadState;
  campaignAction: CampaignActionState;
  predictionAction: CampaignActionState;
  onFreezePrediction: (operationId: string) => void;
  onStartCampaign: (campaignKind: string) => void;
}) {
  if (state.status === "loading" || state.status === "idle") {
    return (
      <section className="engineer-learning-card engineer-readiness" aria-busy="true">
        <header>
          <FlaskConical size={16} aria-hidden="true" />
          <div><span className="eyebrow">Evidence lab</span><h2>Learning readiness</h2></div>
        </header>
        <p className="engineer-empty-detail">Checking qualified scientific evidence…</p>
      </section>
    );
  }
  if (state.status === "error" || !state.projection) {
    return (
      <section className="engineer-learning-card engineer-readiness" data-status="error">
        <header>
          <AlertTriangle size={16} aria-hidden="true" />
          <div><span className="eyebrow">Evidence lab</span><h2>Learning readiness unavailable</h2></div>
        </header>
        <p>{state.error ?? "No readiness record was returned."}</p>
        <strong>No statistical authority was inferred.</strong>
      </section>
    );
  }
  const projection = state.projection;
  const activeCampaign = projection.active_campaigns[0] ?? null;
  const highestOption = projection.acquisition_options.find((option) => option.state === "highest") ?? null;
  const latestRejectedLap = activeCampaign?.latest_assessment?.rejected_lap_numbers[0] ?? null;
  const latestLapRejection = latestRejectedLap == null
    ? null
    : activeCampaign?.latest_assessment?.lap_rejection_reasons[String(latestRejectedLap)]?.[0] ?? null;
  const ledgerSections = [
    ["proven_guardrail", "Proven guardrails"],
    ["in_validation", "In validation"],
    ["failed_validation", "Failed validation"],
    ["locked", "Locked"],
  ] as const;
  return (
    <section className="engineer-learning-card engineer-readiness" aria-labelledby="engineer-readiness-heading">
      <header>
        <FlaskConical size={16} aria-hidden="true" />
        <div>
          <span className="eyebrow">Evidence lab · Offline evaluation</span>
          <h2 id="engineer-readiness-heading">Learning readiness</h2>
        </div>
        <span className="engineer-readiness-state">Advanced models: {projection.advanced_models_summary}</span>
      </header>
      <p className="engineer-readiness-authority">
        Production authority stays with <strong>{projection.deterministic_authority}</strong>.
      </p>
      <section className="engineer-learning-operation" aria-labelledby="engineer-operation-heading">
        <header>
          <div><span className="eyebrow">Today&apos;s test session</span><h3 id="engineer-operation-heading">{activeCampaign
            ? activeCampaign.operation.campaign_kind.replace(/_/g, " ")
            : highestOption?.label ?? "No feasible campaign"}</h3></div>
          <span>{activeCampaign?.state ?? "recommended"}</span>
        </header>
        {activeCampaign ? (
          <>
            <div className="engineer-operation-progress">
              <span>Independent <strong>{activeCampaign.progress.independent_units}</strong></span>
              <span>Clean laps <strong>{activeCampaign.progress.eligible_laps}</strong></span>
              <span>Need units <strong>{activeCampaign.progress.remaining_independent_units}</strong></span>
              <span>Rejected <strong>{activeCampaign.latest_assessment?.rejected_lap_numbers.length ?? 0}</strong></span>
            </div>
            <p>Next recording: {activeCampaign.operation.context.minimum_clean_laps_per_unit} clean laps · exact car/build
              {activeCampaign.operation.context.maximum_traffic_exposure_fraction === 0 ? " · no nearby traffic" : " · bounded nearby traffic"}.</p>
            {activeCampaign.latest_assessment && (
              <small>Latest import: {activeCampaign.latest_assessment.state.replace(/_/g, " ")}
                {latestLapRejection ? ` · Lap ${latestRejectedLap}: ${latestLapRejection}`
                  : activeCampaign.latest_assessment.rejection_reasons[0] ? ` · ${activeCampaign.latest_assessment.rejection_reasons[0]}` : ""}</small>
            )}
            {activeCampaign.operation.campaign_kind === "controlled_setup_response" && (
              <div className="engineer-prospective-lock">
                <span>Frozen predictions <strong>{activeCampaign.prospective_prediction_count}</strong></span>
                <span>Awaiting outcomes <strong>{activeCampaign.unscored_prediction_count}</strong></span>
                {activeCampaign.unscored_prediction_count === 0 && (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={predictionAction.status === "loading"}
                    onClick={() => onFreezePrediction(activeCampaign.operation.operation_id)}
                  >{predictionAction.status === "loading" ? "Freezing prediction…" : "Freeze P19 prediction before B"}</button>
                )}
                {predictionAction.status === "error" && <small className="engineer-operation-error">{predictionAction.error}</small>}
              </div>
            )}
          </>
        ) : highestOption ? (
          <>
            <p>{highestOption.need_next[0]} · helps {highestOption.helps.join(", ")}.</p>
            <div className="engineer-operation-progress">
              <span>Expected cost <strong>{highestOption.score.estimated_driver_laps} laps</strong></span>
              <span>Rule fit <strong>{Math.round(highestOption.score.rule_fit_estimate * 100)}%</strong></span>
              <span>Gates helped <strong>{highestOption.score.gates_helped}</strong></span>
            </div>
            <button
              type="button"
              className="secondary-button"
              disabled={campaignAction.status === "loading"}
              onClick={() => onStartCampaign(highestOption.campaign_kind)}
            >
              {campaignAction.status === "loading" ? "Starting campaign…" : "Start this campaign"}
            </button>
            {campaignAction.status === "error" && <small className="engineer-operation-error">{campaignAction.error}</small>}
          </>
        ) : (
          <p>No campaign can start from this run. Recover immutable run, build, and setup identity first.</p>
        )}
      </section>
      <div className="engineer-readiness-counts" aria-label="Qualified evidence counts">
        {projection.counts.map((count) => (
          <div key={count.key}>
            <span>{count.label}</span>
            <strong>{count.current} / {count.required}</strong>
            <small>{count.unit}</small>
          </div>
        ))}
        <div>
          <span>Vehicle profile</span>
          <strong>{projection.vehicle_profile_status}</strong>
          <small>{projection.vehicle_profile_fields_blocked.length > 0
            ? `Missing: ${projection.vehicle_profile_fields_blocked.join(", ")}`
            : "Required geometry fields confirmed"}</small>
        </div>
      </div>
      <div className="engineer-readiness-capabilities">
        {projection.capabilities.map((capability) => (
          <article key={capability.capability_key} data-state={capability.state}>
            <header><strong>{capability.label}</strong><span>{capability.state.replace(/_/g, " ")}</span></header>
            <p>{capability.summary}</p>
            {capability.blockers[0] && <small>{capability.blockers[0]}</small>}
          </article>
        ))}
      </div>
      <details className="engineer-readiness-debt">
        <summary>Collection missions and scientific debt</summary>
        <div>
          <ul>
            {projection.campaigns.map((campaign) => (
              <li key={campaign.campaign_kind}>
                <strong>{campaign.label}</strong>
                <span>{campaign.usable_units} / {campaign.required_units} units · {campaign.state.replace(/_/g, " ")}</span>
              </li>
            ))}
          </ul>
          <ul>
            {projection.debts.map((debt) => (
              <li key={debt.debt_key}>
                <strong>{debt.summary}</strong>
                <span>{debt.collection_action}</span>
              </li>
            ))}
          </ul>
        </div>
      </details>
      <details className="engineer-learning-ledger">
        <summary>RacerZLab Learning Ledger</summary>
        <div>
          {ledgerSections.map(([section, label]) => {
            const entries = projection.learning_ledger.filter((entry) => entry.section === section);
            if (entries.length === 0) return null;
            return (
              <section key={section}>
                <h4>{label}</h4>
                <ul>{entries.map((entry) => (
                  <li key={entry.ledger_key}>
                    <strong>{entry.label}</strong>
                    {entry.current != null && entry.required != null && <span>{entry.current} / {entry.required}</span>}
                    <small>{entry.summary}</small>
                  </li>
                ))}</ul>
              </section>
            );
          })}
        </div>
      </details>
      {projection.p23_acquisition && (
        <section className="engineer-p23-acquisition" data-profile={projection.p23_acquisition.profile_status}>
          <header className="engineer-p23-header">
            <div>
              <span className="eyebrow">P23 steering workload campaign</span>
              <h3>Evidence acquisition operations</h3>
            </div>
            <span data-state={projection.p23_acquisition.profile_status}>
              {projection.p23_acquisition.profile_status === "complete" ? "Signal truth ready" : "Signal truth required"}
            </span>
          </header>
          <div className="engineer-p23-gates" role="list" aria-label="P23 evidence gates">
            {([
              ["Historical", projection.p23_acquisition.historical_sessions, projection.p23_acquisition.required_historical_sessions],
              ["Null stints", projection.p23_acquisition.null_stints, projection.p23_acquisition.required_null_stints],
              ["Controls", projection.p23_acquisition.negative_controls, projection.p23_acquisition.required_negative_controls],
              ["Subgroups", projection.p23_acquisition.covered_subgroups, projection.p23_acquisition.required_subgroups],
            ] as const).map(([label, current, required]) => (
              <article key={label} role="listitem">
                <span>{label}</span>
                <strong>{current} / {required}</strong>
                <progress value={current} max={required} aria-label={`${label}: ${current} of ${required}`} />
              </article>
            ))}
          </div>
          <div className="engineer-p23-state-row">
            <span><strong>Attempts</strong>{projection.p23_acquisition.qualified_attempts} qualified / {projection.p23_acquisition.total_attempts} recorded</span>
            <span data-state={projection.p23_acquisition.prospective_status}><strong>Prospective</strong>{stateLabel(projection.p23_acquisition.prospective_status)}</span>
          </div>
          <div className="engineer-p23-next">
            <span>Next: {stateLabel(projection.p23_acquisition.next_best_collection_kind)}</span>
            <p>{projection.p23_acquisition.next_best_collection}</p>
          </div>
          {projection.p23_acquisition.latest_certificate_id ? (
            <details className="engineer-p23-certificate">
              <summary>Latest session certificate / {stateLabel(projection.p23_acquisition.latest_qualification_state ?? "inventory_only")}</summary>
              <div>
                <p>{projection.p23_acquisition.latest_eligible_laps} eligible / {projection.p23_acquisition.latest_excluded_laps} excluded</p>
                <p>
                  Signal truth: <strong>{stateLabel(projection.p23_acquisition.latest_signal_truth_state ?? "missing")}</strong>
                  {" / "}FFB: <strong>{stateLabel(projection.p23_acquisition.latest_ffb_fingerprint_state ?? "unavailable")}</strong>
                  {" / "}Ownership: <strong>{stateLabel(projection.p23_acquisition.latest_telemetry_ownership_state ?? "blocked")}</strong>
                </p>
                {projection.p23_acquisition.latest_ffb_fingerprint_sha256 && (
                  <small>FFB {projection.p23_acquisition.latest_ffb_fingerprint_sha256.slice(0, 16)}</small>
                )}
                {projection.p23_acquisition.latest_blockers.length > 0 && (
                  <ul aria-label="Exact qualification blockers">
                    {projection.p23_acquisition.latest_blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
                  </ul>
                )}
                <small>
                  Dataset admissions: {projection.p23_acquisition.latest_dataset_admissions.length
                    ? projection.p23_acquisition.latest_dataset_admissions.join(", ")
                    : "none"}
                </small>
                <ol>
                  {projection.p23_acquisition.latest_flight_recorder.map((entry) => (
                    <li key={entry.lap_number} data-state={entry.state}>
                      <strong>Lap {entry.lap_number}</strong>
                      <span>{stateLabel(entry.state)}</span>
                      {entry.reasons[0] && <small>{entry.reasons[0]}</small>}
                    </li>
                  ))}
                </ol>
                {projection.p23_acquisition.latest_flight_recorder_truncated && (
                  <small>Showing {projection.p23_acquisition.latest_flight_recorder.length} of {projection.p23_acquisition.latest_flight_recorder_total} lap decisions. Open the immutable certificate for the complete recorder.</small>
                )}
              </div>
            </details>
          ) : (
            <div className="engineer-p23-empty">
              <strong>No qualification certificate yet</strong>
              <span>The next source-owned import will preserve its lap decisions here.</span>
            </div>
          )}
          {projection.p23_acquisition.latest_null_run_card && (
            <article className="engineer-p23-run-card" data-state={projection.p23_acquisition.latest_null_run_card.state}>
              <span className="eyebrow">P23 steering workload / null session 01</span>
              <h4>Need {projection.p23_acquisition.latest_null_run_card.minimum_eligible_laps} eligible clean laps</h4>
              <p><strong>Hold:</strong> same setup, FFB, steering ratio, tire compound, and control state.</p>
              <p><strong>Avoid:</strong> pit changes, brake-bias changes, reset fragments, FFB changes, and telemetry faults.</p>
              <p><strong>Target:</strong> no intentional steering or handling intervention.</p>
              <small>
                Fuel {projection.p23_acquisition.latest_null_run_card.fuel_band_minimum.toFixed(2)}–{projection.p23_acquisition.latest_null_run_card.fuel_band_maximum.toFixed(2)} / tire {projection.p23_acquisition.latest_null_run_card.tire_compound} / {projection.p23_acquisition.latest_null_run_card.steering_conversion_model}
              </small>
              <small>RacerZLab qualifies or rejects only after import. Card {projection.p23_acquisition.latest_null_run_card.card_hash.slice(0, 12)}</small>
            </article>
          )}
          <footer>Certificate-owned admission / unique source session / shadow only</footer>
        </section>
      )}
      {projection.first_activation_audit && (
        <section
          className="engineer-first-activation"
          data-decision={projection.first_activation_audit.activation_decision}
        >
          <span className="eyebrow">P23 first earned capability</span>
          <h3>{projection.first_activation_audit.activation_decision === "limited_activation_earned"
            ? "Limited activation earned"
            : "No activation earned"}</h3>
          <p><strong>Selected:</strong> steering workload envelope</p>
          <p>{projection.first_activation_audit.selection_summary}</p>
          <div className="engineer-operation-progress">
            <span>Historical <strong>{projection.first_activation_audit.historical.qualified_real_units} / {projection.first_activation_audit.historical.required_real_units}</strong></span>
            <span>Prospective <strong>{projection.first_activation_audit.prospective.qualified_real_units} / {projection.first_activation_audit.prospective.required_real_units}</strong></span>
            <span>Controls <strong>{projection.first_activation_audit.negative_controls.qualified_real_units} / {projection.first_activation_audit.negative_controls.required_real_units}</strong></span>
            <span>Subgroups <strong>{projection.first_activation_audit.subgroups.qualified_real_units} / {projection.first_activation_audit.subgroups.required_real_units}</strong></span>
          </div>
          <small>Protocol {projection.first_activation_audit.protocol_hash.slice(0, 12)} | shadow only</small>
          <p>{projection.first_activation_audit.next_collection_missions[0]}</p>
          <strong>P19/P20 authority unchanged.</strong>
        </section>
      )}
      {projection.capability_review && (
        <section className="engineer-capability-review" data-decision={projection.capability_review.decision}>
          <span className="eyebrow">Advanced capability review</span>
          <h3>{projection.capability_review.decision === "eligible_for_limited_activation"
            ? `${projection.capability_review.eligible_capability_key?.replace(/_/g, " ")} earned review`
            : "No advanced capability has earned activation"}</h3>
          <p>{projection.capability_review.explanation}</p>
          <strong>{projection.capability_review.decision === "remain_locked" ? "Decision: REMAIN LOCKED" : "Decision: ELIGIBLE FOR LIMITED ACTIVATION"}</strong>
        </section>
      )}
      <p className="engineer-readiness-archive">
        Archive inventory: {projection.archived_sessions} saved sessions · {projection.archived_runs} runs. Archived does not mean qualified.
      </p>
    </section>
  );
}

function MeasurementCard({
  measurement,
  learning,
  onNavigate,
}: {
  measurement: IntelligenceMeasurement;
  learning: boolean;
  onNavigate: EngineerTabProps["onNavigateCitation"];
}) {
  const visibleProcedure = asArray(measurement.procedure).slice(0, learning ? measurement.procedure.length : 3);
  return (
    <section className="engineer-measurement-card" data-mode={learning ? "learning" : "race"} aria-labelledby="engineer-measurement-heading">
      <header>
        <FlaskConical size={17} aria-hidden="true" />
        <div>
          <span className="eyebrow">Best next measurement</span>
          <h3 id="engineer-measurement-heading">{measurement.title}</h3>
        </div>
      </header>
      <p>{measurement.purpose}</p>
      {measurement.required_laps != null && (
        <span className="engineer-measurement-laps">{measurement.required_laps} required laps or passes</span>
      )}
      {visibleProcedure.length > 0 && (
        <ol className="engineer-measurement-checklist" aria-label="Measurement mission checklist">
          {visibleProcedure.map((step, index) => <li key={step}><span>{index + 1}</span><p>{step}</p></li>)}
        </ol>
      )}
      <div className="engineer-measurement-guardrails">
        {measurement.acceptance_threshold && <p><strong>Done when:</strong> {measurement.acceptance_threshold}</p>}
        {measurement.stop_rule && <p><strong>Stop and reset:</strong> {measurement.stop_rule}</p>}
      </div>
      {learning && (
        <div className="engineer-measurement-detail">
          {asArray(measurement.controlled_variables).length > 0 && (
            <p><strong>Hold constant:</strong> {measurement.controlled_variables.join(" · ")}</p>
          )}
          <p><strong>Why this matters:</strong> This mission is the smallest producer-owned measurement that can separate the current evidence. It does not approve a setup change.</p>
          <CitationLinks citations={measurement.citations} onNavigate={onNavigate} label="Measurement evidence" />
        </div>
      )}
    </section>
  );
}

function LoadingState() {
  return (
    <div className="engineer-state" role="status" aria-live="polite">
      <BrainCircuit size={24} aria-hidden="true" />
      <div>
        <h2>Assembling the grounded briefing…</h2>
        <p>Checking eligible laps, event provenance, controlled history, and the best next measurement.</p>
      </div>
      <div className="engineer-loading-bars" aria-hidden="true"><span /><span /><span /></div>
    </div>
  );
}

export function IntelligencePanel({
  runId,
  sessionId,
  selectedLap,
  selectedLapScope,
  selectedLapWindowStart,
  selectedLapWindowEnd,
  selectedRepresentativeLap,
  sessionRunScopeKey,
  workflowId,
  workflowUpdatedAt,
  onNavigateCitation,
  onNavigateCrewEvidence,
}: EngineerTabProps) {
  const { selection, focusEvidence, setWorkspace } = useTelemetrySelection();
  const learning = selection.selectedMode === "learning";
  const workflowRevision = useMemo(() => ({ workflowId, workflowUpdatedAt }), [workflowId, workflowUpdatedAt]);
  const queryNavigationRunIds = useMemo(() => {
    try {
      const parsed: unknown = JSON.parse(sessionRunScopeKey);
      if (
        !Array.isArray(parsed)
        || parsed.length === 0
        || parsed.some((value) => typeof value !== "string" || !value || value.trim() !== value)
        || !parsed.includes(runId)
      ) return new Set<string>();
      return new Set<string>(parsed);
    } catch {
      return new Set<string>();
    }
  }, [runId, sessionRunScopeKey]);
  const crewChiefScopeRunIds = useMemo(
    () => [...queryNavigationRunIds],
    [queryNavigationRunIds],
  );
  const scopeKey = JSON.stringify({
    session_id: sessionId,
    run_id: runId,
    session_run_scope: sessionRunScopeKey,
    workflow_id: workflowId,
    workflow_updated_at: workflowUpdatedAt,
  });
  const candidateRepresentativeLap = selectedRepresentativeLap ?? selectedLap;
  const completeWindowQuestionScope = selectedLapScope === "lap_window"
    && Number.isInteger(selectedLapWindowStart)
    && Number.isInteger(selectedLapWindowEnd)
    && Number.isInteger(candidateRepresentativeLap)
    && (selectedLapWindowStart ?? 0) <= (selectedLapWindowEnd ?? -1)
    && (candidateRepresentativeLap ?? -1) >= (selectedLapWindowStart ?? 0)
    && (candidateRepresentativeLap ?? -1) <= (selectedLapWindowEnd ?? -1);
  const selectedQueryLap = completeWindowQuestionScope
    ? candidateRepresentativeLap
    : selectedLapScope === "lap_window" || selectedLapScope === "run"
      ? null
      : selectedLap;
  const questionScopeKind = completeWindowQuestionScope
    ? "lap_window_representative"
    : selectedQueryLap != null ? "single_lap" : "run";
  const questionScopeLabel = completeWindowQuestionScope
    ? `Representative Lap ${selectedQueryLap} from Window L${selectedLapWindowStart}\u2013L${selectedLapWindowEnd}`
    : selectedLapScope === "lap_window"
      ? "Run (window focus incomplete)"
      : selectedQueryLap != null ? `Lap ${selectedQueryLap}` : "Run";
  const questionScopeKey = JSON.stringify({
    kind: questionScopeKind,
    lap: selectedQueryLap,
    window_start: completeWindowQuestionScope ? selectedLapWindowStart : null,
    window_end: completeWindowQuestionScope ? selectedLapWindowEnd : null,
  });
  const reportSequence = useRef(0);
  const querySequence = useRef(0);
  const readinessSequence = useRef(0);
  const [retryToken, setRetryToken] = useState(0);
  const [reportState, setReportState] = useState<ReportLoadState>({
    requestKey: scopeKey,
    status: "loading",
    report: null,
    error: null,
  });
  const [question, setQuestion] = useState("");
  const [queryState, setQueryState] = useState<QueryState>({
    requestKey: null,
    status: "idle",
    response: null,
    error: null,
  });
  const [readinessState, setReadinessState] = useState<ReadinessLoadState>({
    requestKey: null,
    status: "idle",
    projection: null,
    error: null,
  });
  const [readinessRefreshToken, setReadinessRefreshToken] = useState(0);
  const [campaignAction, setCampaignAction] = useState<CampaignActionState>({
    campaignKind: null,
    status: "idle",
    error: null,
  });
  const [predictionAction, setPredictionAction] = useState<CampaignActionState>({
    campaignKind: null,
    status: "idle",
    error: null,
  });

  const startCampaign = useCallback(async (campaignKind: string) => {
    const requestedRunId = runId;
    setCampaignAction({ campaignKind, status: "loading", error: null });
    try {
      const operation = await startEvidenceCampaign(requestedRunId, campaignKind);
      if (
        operation.campaign_kind !== campaignKind
        || operation.context.reference_run_id !== requestedRunId
      ) {
        setCampaignAction({
          campaignKind,
          status: "error",
          error: "The campaign operation did not match the current run and was not shown.",
        });
        return;
      }
      setCampaignAction({ campaignKind, status: "ready", error: null });
      setReadinessRefreshToken((value) => value + 1);
    } catch (caught: unknown) {
      setCampaignAction({
        campaignKind,
        status: "error",
        error: caught instanceof Error ? caught.message : "The evidence campaign could not start.",
      });
    }
  }, [runId]);

  const freezePrediction = useCallback(async (operationId: string) => {
    const requestedRunId = runId;
    if (!sessionId) {
      setPredictionAction({
        campaignKind: operationId,
        status: "error",
        error: "Save this run in one exact session before freezing a shadow prediction.",
      });
      return;
    }
    setPredictionAction({ campaignKind: operationId, status: "loading", error: null });
    try {
      const prediction = await freezeProspectivePrediction(
        operationId,
        requestedRunId,
        sessionId,
      );
      if (
        prediction.operation_id !== operationId
        || prediction.source_run_id !== requestedRunId
        || prediction.authority !== "shadow_only"
      ) {
        setPredictionAction({
          campaignKind: operationId,
          status: "error",
          error: "The prospective record did not match the current run and was not shown.",
        });
        return;
      }
      setPredictionAction({ campaignKind: operationId, status: "ready", error: null });
      setReadinessRefreshToken((value) => value + 1);
    } catch (caught: unknown) {
      setPredictionAction({
        campaignKind: operationId,
        status: "error",
        error: caught instanceof Error ? caught.message : "The prospective prediction could not be frozen.",
      });
    }
  }, [runId, sessionId]);

  useEffect(() => {
    setCampaignAction({ campaignKind: null, status: "idle", error: null });
    setPredictionAction({ campaignKind: null, status: "idle", error: null });
  }, [runId, sessionId]);

  useEffect(() => {
    const sequence = ++readinessSequence.current;
    if (!learning) {
      setReadinessState({ requestKey: null, status: "idle", projection: null, error: null });
      return;
    }
    const requestedRunId = runId;
    const requestedSessionId = sessionId;
    const requestKey = `${requestedRunId}:${requestedSessionId ?? "no-session"}:${workflowUpdatedAt ?? "no-workflow"}`;
    let cancelled = false;
    setReadinessState({ requestKey, status: "loading", projection: null, error: null });
    void fetchLearningReadiness(requestedRunId, { sessionId: requestedSessionId })
      .then((projection) => {
        if (cancelled || sequence !== readinessSequence.current) return;
        if (
          projection.run_id !== requestedRunId
          || (projection.session_id ?? null) !== requestedSessionId
          || projection.scope_key !== `${requestedRunId}:${requestedSessionId ?? "no-session"}`
        ) {
          setReadinessState({
            requestKey,
            status: "error",
            projection: null,
            error: "Learning readiness returned a different run or session. No result was shown.",
          });
          return;
        }
        setReadinessState({ requestKey, status: "ready", projection, error: null });
      })
      .catch((caught: unknown) => {
        if (cancelled || sequence !== readinessSequence.current) return;
        setReadinessState({
          requestKey,
          status: "error",
          projection: null,
          error: caught instanceof Error ? caught.message : "Learning readiness failed.",
        });
      });
    return () => { cancelled = true; };
  }, [learning, readinessRefreshToken, runId, sessionId, workflowUpdatedAt]);

  useEffect(() => {
    const sequence = ++reportSequence.current;
    let cancelled = false;
    querySequence.current += 1;
    setReportState({ requestKey: scopeKey, status: "loading", report: null, error: null });
    setQuestion("");
    setQueryState({ requestKey: null, status: "idle", response: null, error: null });
    void fetchRunIntelligence(runId, {
      sessionId,
      refreshKey: `${sessionRunScopeKey}:${workflowId ?? "no-workflow"}:${workflowUpdatedAt ?? "no-revision"}:${retryToken}`,
    })
      .then((report) => {
        if (cancelled || sequence !== reportSequence.current) return;
        if (
          !scopeMatches(report, runId, sessionId)
          || !isRunIntelligenceResponse(report, { runId, sessionId })
        ) {
          setReportState({
            requestKey: scopeKey,
            status: "error",
            report: null,
            error: "The engineer returned evidence for a different run or session. Nothing from that response was shown.",
          });
          return;
        }
        setReportState({ requestKey: scopeKey, status: "ready", report, error: null });
      })
      .catch((caught: unknown) => {
        if (cancelled || sequence !== reportSequence.current) return;
        setReportState({
          requestKey: scopeKey,
          status: "error",
          report: null,
          error: caught instanceof Error ? caught.message : "The grounded briefing could not be loaded.",
        });
      });
    return () => {
      cancelled = true;
      if (sequence === reportSequence.current) reportSequence.current += 1;
      querySequence.current += 1;
    };
  }, [retryToken, runId, scopeKey, sessionId, sessionRunScopeKey, workflowId, workflowUpdatedAt]);

  useEffect(() => {
    querySequence.current += 1;
    setQueryState({ requestKey: null, status: "idle", response: null, error: null });
  }, [learning, questionScopeKey, scopeKey]);

  const report = reportState.requestKey === scopeKey ? reportState.report : null;
  const briefing = report?.briefing;
  const action = briefing?.action;
  const decisionStatus = report?.decision_status === "ready"
    || report?.decision_status === "measure"
    || report?.decision_status === "blocked"
    ? report.decision_status
    : "blocked";

  const allCitations = useMemo(() => {
    if (!report) return [];
    const citations = [
      ...asArray(report.competing_causes).flatMap((cause) => [
        ...asArray(cause.evidence_for),
        ...asArray(cause.evidence_against),
      ]),
      ...(report.best_measurement ? asArray(report.best_measurement.citations) : []),
      ...asArray(report.context_matches).flatMap((match) => asArray(match.citations)),
      ...asArray(report.narrative).flatMap((entry) => asArray(entry.citations)),
      ...(report.data_quality ? asArray(report.data_quality.citations) : []),
    ];
    return Array.from(new Map(citations.map((citation) => [citation.citation_id, citation])).values());
  }, [report]);
  const citationById = useMemo(
    () => new Map(allCitations.map((citation) => [citation.citation_id, citation])),
    [allCitations],
  );
  const actionCitations = useMemo(() => {
    const sourceIds = new Set(asArray(action?.source_event_ids));
    if (sourceIds.size === 0) return [];
    return allCitations.filter((citation) => (
      citation.run_id === runId
      && citation.valid_for_tuning
      && evidenceStateSupportsAction(citation.evidence_state)
      && citation.source_channels.length > 0
      && sourceIds.has(citation.event_id ?? "")
    ));
  }, [action?.source_event_ids, allCitations, runId]);
  const actionSourceEventIds = asArray(action?.source_event_ids);
  const currentReportSetupAuthority = deriveCurrentReportSetupAuthority(
    report,
    runId,
    sessionId,
    workflowRevision,
  );
  const actionAuthorized = currentReportSetupAuthority != null;
  const stageBActionWithheld = report?.test_preflight?.stage === "B" && !actionAuthorized;
  const authorizedSetupAction = currentReportSetupAuthority
    ? {
        controlKey: currentReportSetupAuthority.controlKey,
        sourceEventIds: currentReportSetupAuthority.sourceEventIds,
      }
    : null;

  const openNextTrustworthyMove = useCallback((move: NonNullable<RunIntelligenceReport["next_trustworthy_move"]>) => {
    if (!trustedNavigationMove(move, runId, workflowRevision)) return;
    const target = intelligenceWorkspaceTarget(move.workspace);
    const scope = intelligenceMoveScope(move);
    if (!target || !scope) return;
    focusEvidence({
      runId,
      lapNumber: scope.lap,
      lapScope: scope.kind,
      lapWindowStart: scope.windowStart,
      lapWindowEnd: scope.windowEnd,
      representativeLap: scope.kind === "lap_window" ? scope.lap : null,
      eventId: null,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: null,
      zoneId: null,
      zoneLabel: scope.pctStart != null ? "Server-ranked window" : null,
      zoneStartPct: scope.pctStart,
      zoneEndPct: scope.pctEnd,
      channelId: null,
      system: null,
      selectionSource: "engineer",
      lockState: scope.pctStart != null ? "locked" : "none",
      trustTier: move.authority,
      valueBasis: scope.kind === "lap_window" ? "selected_window" : scope.kind === "single_lap" ? "full_lap" : "run_level",
    }, target);
  }, [focusEvidence, runId, workflowRevision]);

  const contextualQuestions = useMemo(() => {
    if (!report) return [];
    const structuredQuestions: string[] = [];
    if (report.opportunity_signature) structuredQuestions.push("How repeatable is the strongest opportunity?");
    if (report.mechanism_observations) structuredQuestions.push("Which typed mechanism has the strongest evidence?");
    if (report.session_ledger) structuredQuestions.push("What changed across the qualified session runs?");
    if (report.hypothesis_lifecycle) structuredQuestions.push("Which hypotheses should I avoid repeating?");
    if (report.driver_focus) structuredQuestions.push("Is driver repeatability limiting this setup decision?");
    if (report.anomalies) structuredQuestions.push("Which same-setup anomaly should I inspect first?");
    if (report.measurement_debt?.items.length) structuredQuestions.push("What evidence should I recover first?");
    if (asArray(report.mind_change_criteria).length) structuredQuestions.push("What would change your mind?");
    const questions = [...structuredQuestions, ...asArray(report.suggested_questions)];
    return Array.from(new Set(questions.map((value) => value.trim()).filter(Boolean))).slice(0, 8);
  }, [report]);

  const submitQuestion = useCallback(async (rawQuestion: string) => {
    const nextQuestion = rawQuestion.trim();
    if (nextQuestion.length < 2) return;
    const sequence = ++querySequence.current;
    const requestKey = JSON.stringify({
      run_id: runId,
      session_id: sessionId,
      question: nextQuestion,
      question_scope: questionScopeKey,
      lap: selectedQueryLap,
    });
    setQuestion(nextQuestion);
    setQueryState({ requestKey, status: "loading", response: null, error: null });
    try {
      const response = await queryRunIntelligence(runId, {
        question: nextQuestion,
        session_id: sessionId,
        selected_lap: selectedQueryLap,
        selected_window_start_lap: completeWindowQuestionScope ? selectedLapWindowStart : null,
        selected_window_end_lap: completeWindowQuestionScope ? selectedLapWindowEnd : null,
        selected_window_representative_lap: completeWindowQuestionScope ? selectedQueryLap : null,
        presentation_mode: learning ? "learning" : "race",
      });
      if (sequence !== querySequence.current) return;
      const responseWindowMatchesScope = completeWindowQuestionScope
        ? response.interpreted_window_start_lap === selectedLapWindowStart
          && response.interpreted_window_end_lap === selectedLapWindowEnd
          && response.interpreted_window_representative_lap === selectedQueryLap
        : response.interpreted_window_start_lap == null
          && response.interpreted_window_end_lap == null
          && response.interpreted_window_representative_lap == null;
      const responseRunScope = Array.isArray(response.scope_run_ids)
        ? response.scope_run_ids
        : [];
      const responseRunScopeMatches = responseRunScope.length === queryNavigationRunIds.size
        && new Set(responseRunScope).size === responseRunScope.length
        && responseRunScope.every((scopeRunId) => (
          typeof scopeRunId === "string"
          && scopeRunId.length > 0
          && scopeRunId.trim() === scopeRunId
          && queryNavigationRunIds.has(scopeRunId)
        ));
      if (
        report == null
        || !isIntelligenceQueryResponseBoundToReport(response, report)
        || !scopeMatches(response, runId, sessionId)
        || !responseRunScopeMatches
        || (response.selected_lap ?? null) !== selectedQueryLap
        || !responseWindowMatchesScope
        || response.question.trim() !== nextQuestion
        || (response.interpreted_component_id != null
          && !isVehicleSystemComponentId(response.interpreted_component_id))
      ) {
        setQueryState({
          requestKey,
          status: "error",
          response: null,
          error: "The answer did not match the current run, session, question scope, and question. It was discarded.",
        });
        return;
      }
      setQueryState({ requestKey, status: "ready", response, error: null });
    } catch (caught: unknown) {
      if (sequence !== querySequence.current) return;
      setQueryState({
        requestKey,
        status: "error",
        response: null,
        error: caught instanceof Error ? caught.message : "The engineer could not answer this question.",
      });
    }
  }, [
    completeWindowQuestionScope,
    learning,
    queryNavigationRunIds,
    questionScopeKey,
    report,
    runId,
    selectedLapWindowEnd,
    selectedLapWindowStart,
    selectedQueryLap,
    sessionId,
  ]);

  const handleSubmit = useCallback((event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submitQuestion(question);
  }, [question, submitQuestion]);

  if (reportState.status === "loading" || reportState.requestKey !== scopeKey) return <LoadingState />;

  if (reportState.status === "error") {
    const evidenceRecoveryNeeded = /422|artifact|archive|cache|manifest|integrity/i.test(reportState.error ?? "");
    return (
      <div className="smart-engineer-workspace">
        <section className="engineer-state engineer-state-error" role="alert">
          <AlertTriangle size={24} aria-hidden="true" />
          <div>
            <span className="eyebrow">Smart Engineer unavailable</span>
            <h2>{evidenceRecoveryNeeded ? "Current evidence needs recovery" : "No stale briefing was kept"}</h2>
            <p>{evidenceRecoveryNeeded
              ? "Re-import the original telemetry or review run health before asking Smart Engineer for a current briefing."
              : "The briefing could not be loaded. Your previous run context was not reused."}</p>
            {learning && <small>{reportState.error}</small>}
          </div>
          <div className="toolbar-actions">
            <button type="button" className="secondary-button" onClick={() => setWorkspace("overview", "engineer")}>Review run health</button>
            <button type="button" className="secondary-button" onClick={() => setRetryToken((value) => value + 1)}>
              <RefreshCcw size={14} aria-hidden="true" /> Retry
            </button>
          </div>
        </section>
        {learning && <LearningReadinessCard state={readinessState} campaignAction={campaignAction} predictionAction={predictionAction} onFreezePrediction={freezePrediction} onStartCampaign={startCampaign} />}
      </div>
    );
  }

  if (!report || report.status === "unavailable" || !briefing || !action) {
    const blockers = asArray(report?.blocker_reasons);
    return (
      <div className="smart-engineer-workspace">
        <section
          className="tab-decision-broadcast"
          data-state="blocked"
          data-authority="withheld"
          data-run-id={runId}
          data-session-id={sessionId ?? undefined}
          data-briefing-scope="run"
          data-question-scope={questionScopeKind}
          data-question-lap={selectedQueryLap ?? undefined}
          data-window-start={completeWindowQuestionScope ? selectedLapWindowStart ?? undefined : undefined}
          data-window-end={completeWindowQuestionScope ? selectedLapWindowEnd ?? undefined : undefined}
          data-representative-lap={completeWindowQuestionScope ? selectedQueryLap ?? undefined : undefined}
          aria-label="Smart Engineer unavailable status and workspace handoffs"
        >
          <div>
            <h3>Evidence first · no engineering call</h3>
            <p>This run cannot support an evidence-bound action. Recover the missing laps or channels before treating a cause as established.</p>
            <div className="tab-decision-facts" aria-label="Unavailable briefing scope">
              <span>Briefing scope <strong>Run</strong></span>
              <span>Question scope <strong>{questionScopeLabel}</strong></span>
              {report?.data_quality && <span>Eligible laps <strong>{report.data_quality.eligible_laps}</strong></span>}
              <span>Setup authority <strong>Withheld</strong></span>
            </div>
          </div>
          <div className="tab-handoff-actions" aria-label="Smart Engineer recovery handoffs">
            <button type="button" onClick={() => setWorkspace("laps", "engineer")}>Review Laps</button>
            <button type="button" onClick={() => setWorkspace("overview", "engineer")}>Review run health</button>
          </div>
        </section>
        <section className="engineer-state engineer-state-unavailable" role="status" aria-live="polite">
          <ShieldCheck size={24} aria-hidden="true" />
          <div>
            <span className="eyebrow">No call</span>
            <h2>A grounded briefing is not available yet</h2>
            <p>No setup conclusion will be created from incomplete or ineligible evidence.</p>
            {blockers.length > 0 && <ul>{blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>}
          </div>
          <button type="button" className="secondary-button" onClick={() => setRetryToken((value) => value + 1)}>
            <RefreshCcw size={14} aria-hidden="true" /> Retry
          </button>
        </section>
        {learning && <LearningReadinessCard state={readinessState} campaignAction={campaignAction} predictionAction={predictionAction} onFreezePrediction={freezePrediction} onStartCampaign={startCampaign} />}
        {report?.best_measurement && (
          <MeasurementCard measurement={report.best_measurement} learning={learning} onNavigate={onNavigateCitation} />
        )}
        {report?.data_quality && (
          <DataQualityCard quality={report.data_quality} learning={learning} onNavigate={onNavigateCitation} />
        )}
        {report && (
          <SmartIntelligenceCards
            report={report}
            runId={runId}
            sessionId={sessionId}
            learning={learning}
            setupActionAuthorized={false}
            authorizedSetupAction={null}
            workflowRevision={workflowRevision}
            onOpenMove={openNextTrustworthyMove}
            onOpenRecovery={(workspace) => setWorkspace(workspace, "engineer")}
          />
        )}
      </div>
    );
  }

  const actionTitle = actionAuthorized ? action.title : "Evidence task only";
  const actionInstruction = actionAuthorized
    ? action.instruction
    : "Use the evidence-linked measurement detail below. No setup change, Keep/Undo, or stop-testing policy is authorized.";
  const queryResponse = queryState.response;
  const queryHasGrounding = Boolean(queryResponse && asArray(queryResponse.citations).length > 0);
  const queryInterpretationMatchesScope = Boolean(
    queryResponse
    && !queryResponse.clarification_required
    && (queryResponse.interpreted_lap_number == null || queryResponse.interpreted_lap_number === selectedQueryLap)
    && (completeWindowQuestionScope
      ? (
        completeWindowQuestionScope
        && queryResponse.interpreted_window_start_lap === selectedLapWindowStart
        && queryResponse.interpreted_window_end_lap === selectedLapWindowEnd
        && queryResponse.interpreted_window_representative_lap === selectedQueryLap
      )
      : queryResponse.interpreted_window_start_lap == null
        && queryResponse.interpreted_window_end_lap == null
        && queryResponse.interpreted_window_representative_lap == null),
  );
  const interpretedQueryWindow = queryResponse?.interpreted_window_start_lap != null
    && queryResponse.interpreted_window_end_lap != null
    ? {
        start: queryResponse.interpreted_window_start_lap,
        end: queryResponse.interpreted_window_end_lap,
      }
    : null;
  const queryActionCitations = asArray(queryResponse?.citations).filter((citation) => (
    citation.run_id === runId
    && (
      interpretedQueryWindow
        ? citation.lap_number != null
          && citation.lap_number >= interpretedQueryWindow.start
          && citation.lap_number <= interpretedQueryWindow.end
        : selectedQueryLap == null || citation.lap_number === selectedQueryLap
    )
    && citation.valid_for_tuning
    && evidenceStateSupportsAction(citation.evidence_state)
    && citation.source_channels.length > 0
  ));
  const queryActionCitationEventIds = queryActionCitations.flatMap((citation) => (
    citation.event_id ? [citation.event_id] : []
  ));
  const queryActionTrusted = Boolean(
    queryResponse?.action_authorized
    && queryResponse.status === "ready"
    && !queryResponse.clarification_required
    && actionAuthorized
    && queryResponse.answer === currentReportSetupAuthority?.instruction
    && queryInterpretationMatchesScope
    && controlledTestStateSupportsAction(queryResponse.evidence_state)
    && asArray(queryResponse.blocker_reasons).length === 0
    && queryActionCitations.length > 0
    && queryActionCitations.length === asArray(queryResponse.citations).length
    && exactEventIdentitySet(
      asArray(queryResponse.action_source_event_ids),
      actionSourceEventIds,
    )
    && exactEventIdentitySet(
      queryActionCitationEventIds,
      asArray(queryResponse.action_source_event_ids),
    )
  );
  const queryActionWithheld = Boolean(queryResponse?.action_authorized && !queryActionTrusted);
  const queryNavigationCitations = queryActionWithheld
    ? []
    : asArray(queryResponse?.suggested_navigation)
        .map((target) => trustedQueryNavigationCitation(target, queryNavigationRunIds))
        .filter((citation): citation is IntelligenceCitation => citation != null)
        .filter((navigation) => !asArray(queryResponse?.citations).some((citation) => (
          citation.workspace === navigation.workspace
          && citation.run_id === navigation.run_id
          && (citation.lap_number ?? null) === (navigation.lap_number ?? null)
          && (citation.event_id ?? null) === (navigation.event_id ?? null)
          && (citation.lap_pct ?? null) === (navigation.lap_pct ?? null)
        )));
  const queryMindChangeCriteria = queryResponse
    && !queryResponse.clarification_required
    && !queryResponse.action_authorized
    ? exactMindChangeCriteria(
        queryResponse.mind_change_criteria,
        report.competing_causes,
        runId,
        sessionId,
      )
    : [];
  const visibleQueryHeadline = queryResponse?.action_authorized
    ? queryActionTrusted ? "Controlled setup action" : "Setup action withheld"
    : queryResponse?.headline;
  const visibleQueryAnswer = queryActionWithheld
    ? "The exact setup target was withheld because its evidence links were incomplete. Keep the current setup and use the measurement guidance instead."
    : queryResponse?.action_authorized && queryActionTrusted
      ? currentReportSetupAuthority?.instruction
      : queryResponse?.answer;
  const graphNodes = asArray(report.evidence_graph?.nodes);
  const graphEdges = asArray(report.evidence_graph?.edges);
  const graphNodeById = new Map(graphNodes.map((node) => [node.node_id, node]));
  const graphKindOrder = { claim: 0, cause: 1, blocker: 2, test: 3, evidence: 4 } as const;
  const graphPreviewNodes = [...graphNodes]
    .sort((left, right) => (
      graphKindOrder[left.kind] - graphKindOrder[right.kind]
      || Number(Boolean(right.citation_id)) - Number(Boolean(left.citation_id))
    ))
    .slice(0, 10);
  const graphPreviewNodeIds = new Set(graphPreviewNodes.map((node) => node.node_id));
  const graphPreviewEdges = graphEdges.filter((edge) => (
    graphPreviewNodeIds.has(edge.source_id) && graphPreviewNodeIds.has(edge.target_id)
  )).slice(0, 12);
  const graphHasAuditDetail = graphPreviewNodes.length < graphNodes.length
    || graphPreviewEdges.length < graphEdges.length;
  const primaryEvidenceCitation = actionCitations[0]
    ?? allCitations.find((citation) => citation.valid_for_tuning)
    ?? allCitations[0];
  const candidateBriefingMove = report.next_trustworthy_move;
  const trustedBriefingMove = stageBActionWithheld
    ? null
    : candidateBriefingMove?.authority === "navigation_only"
    ? trustedNavigationMove(candidateBriefingMove, runId, workflowRevision) ? candidateBriefingMove : null
    : actionAuthorized && authorizedSetupAction && trustedSetupAuthorizedMove(
      candidateBriefingMove,
      runId,
      {
        ...workflowRevision,
        controlKey: authorizedSetupAction.controlKey,
        sourceEventIds: authorizedSetupAction.sourceEventIds,
      },
    ) ? candidateBriefingMove : null;
  const leadingCause = [...asArray(report.competing_causes)].sort((left, right) => left.rank - right.rank)[0];
  const whyNow = trustedBriefingMove?.reason
    ?? asArray(action.blocker_reasons)[0]
    ?? report.best_measurement?.purpose
    ?? leadingCause?.reason
    ?? "This is the highest-signal step the current qualified evidence can support.";
  const effectiveMissionStage = stageBActionWithheld ? "measure" : report.mission_stage;
  const missionHeadline = effectiveMissionStage
    ? ENGINEER_MISSION_HEADLINES[effectiveMissionStage]
    : "Your next trustworthy move";
  const broadcastState = actionAuthorized
    ? "ready"
    : action.kind === "measurement_mission" ? "attention" : "guarded";
  const broadcastHeadline = actionAuthorized
    ? "One controlled test is authorized"
    : action.kind === "measurement_mission"
      ? "Measure before changing the setup"
      : "No setup action is authorized";
  const broadcastDetail = actionAuthorized
    ? "The exact target remains bound to the server-owned card, its qualified events, and the active A/B/A2 protocol."
    : report.best_measurement?.purpose
      ?? "Use the evidence limits and recovery steps before asking the car to prove a setup direction.";

  return (
    <div
      className="smart-engineer-workspace"
      data-mode={learning ? "learning" : "race"}
      data-decision-status={decisionStatus}
    >
      <header className="engineer-workspace-header">
        <div>
          <span className="eyebrow"><BrainCircuit size={13} aria-hidden="true" /> Smart Engineer</span>
          <h1>{learning ? "Decision, causes, and evidence" : missionHeadline}</h1>
          <p>{learning
            ? "See why the call is next, what could still disprove it, and exactly which evidence carries the claim."
            : "One issue. One mission. One done-when check."}</p>
        </div>
        <div className="engineer-header-badges" aria-label="Briefing status">
          <span data-tone={actionAuthorized ? "ready" : "guarded"}>
            {actionAuthorized ? "Test authorized" : action.kind === "measurement_mission" ? "Measurement first" : "Evidence guarded"}
          </span>
          {briefing.confidence_label && <span>{briefing.confidence_label}</span>}
        </div>
      </header>

      {sessionId && (
        <CrewChiefCommandDeck
          runId={runId}
          sessionId={sessionId}
          report={report}
          scopeRunIds={crewChiefScopeRunIds}
          learning={learning}
          onFocusEvidence={(entry) => { void onNavigateCrewEvidence(entry); }}
        />
      )}

      <section
        className="tab-decision-broadcast"
        data-state={broadcastState}
        data-authority={actionAuthorized ? "server-verified" : "withheld"}
        data-run-id={runId}
        data-session-id={sessionId ?? undefined}
        data-briefing-scope="run"
        data-question-scope={questionScopeKind}
        data-question-lap={selectedQueryLap ?? undefined}
        data-window-start={completeWindowQuestionScope ? selectedLapWindowStart ?? undefined : undefined}
        data-window-end={completeWindowQuestionScope ? selectedLapWindowEnd ?? undefined : undefined}
        data-representative-lap={completeWindowQuestionScope ? selectedQueryLap ?? undefined : undefined}
        aria-label="Smart Engineer status and workspace handoffs"
      >
        <div>
          <h3>{broadcastHeadline}</h3>
          <p>{broadcastDetail}</p>
          <div className="tab-decision-facts" aria-label="Briefing scope and authority">
            <span>Briefing scope <strong>Run</strong></span>
            <span>Question scope <strong>{questionScopeLabel}</strong></span>
            {report.data_quality && <span>Eligible laps <strong>{report.data_quality.eligible_laps}</strong></span>}
            {report.data_quality && <span>Trusted events <strong>{report.data_quality.trusted_events}</strong></span>}
            <span>Decision status <strong>{driverFacingLabel(decisionStatus)}</strong></span>
            <span>Setup authority <strong>{actionAuthorized ? "Authorized" : "Withheld"}</strong></span>
          </div>
        </div>
        <div className="tab-handoff-actions" aria-label="Smart Engineer workspace handoffs">
          {primaryEvidenceCitation && (
            <button type="button" onClick={() => { void onNavigateCitation(primaryEvidenceCitation); }}>
              {primaryEvidenceCitation.valid_for_tuning ? "Open exact evidence" : "Open evidence limit"}
            </button>
          )}
          <button type="button" onClick={() => setWorkspace("laps", "engineer")}>Review Laps</button>
          <button
            type="button"
            onClick={() => setWorkspace(actionAuthorized ? "dial_in" : "platform_trace", "engineer")}
          >
            {actionAuthorized ? "Open controlled test" : "Inspect Platform"}
          </button>
        </div>
      </section>

      <EngineeringAwarenessPanel runId={runId} sessionId={sessionId} surface="engineer" />
      <VehicleSystemsPanel
        runId={runId}
        sessionId={sessionId}
        learning={learning}
        surface="engineer"
        refreshKey={`${workflowId ?? "no-workflow"}:${workflowUpdatedAt ?? "no-revision"}`}
        initialProjection={report.vehicle_systems}
      />

      <section className="engineer-briefing" aria-labelledby="engineer-briefing-heading">
        <header>
          <Sparkles size={16} aria-hidden="true" />
          <h2 id="engineer-briefing-heading">Race briefing</h2>
        </header>
        <div className="engineer-decision-grid">
          <article>
            <span>Issue</span>
            <strong>{driverFacingIssue(briefing.issue)}</strong>
          </article>
          <article className="engineer-decision-action" data-authorized={actionAuthorized ? "true" : "false"}>
            <span>{actionAuthorized ? "Crew-chief call" : action.kind === "measurement_mission" ? "Measurement mission" : "Next step"}</span>
            <strong>{actionTitle}</strong>
            <p>{actionInstruction}</p>
            <div className="engineer-briefing-why">
              <span>Why now</span>
              <p>{whyNow}</p>
            </div>
            {actionAuthorized && (action.current_value || action.proposed_value) && (
              <small>{action.current_value ?? "Current value unavailable"} <ArrowRight size={12} aria-hidden="true" /> {action.proposed_value ?? "Proposed value unavailable"}</small>
            )}
          </article>
          <article>
            <span>Done when</span>
            <strong>{briefing.success_check || "Use the measurement mission before judging a change."}</strong>
          </article>
        </div>
        <div className="engineer-evidence-trail" aria-label="High-signal evidence trail">
          <span>Evidence trail</span>
          <ol>
            {report.data_quality && <li><strong>{report.data_quality.eligible_laps} eligible laps</strong><small>of {report.data_quality.total_laps} recorded</small></li>}
            {report.data_quality && <li><strong>{report.data_quality.trusted_events} trusted events</strong><small>provenance complete</small></li>}
            <li><strong>{actionAuthorized ? `${actionCitations.length} tuning citation${actionCitations.length === 1 ? "" : "s"}` : `${allCitations.length} evidence link${allCitations.length === 1 ? "" : "s"}`}</strong><small>{actionAuthorized ? "exact action support" : "observation or recovery only"}</small></li>
            {primaryEvidenceCitation && <li><strong>{primaryEvidenceCitation.label}</strong><small>{citationMeta(primaryEvidenceCitation) || stateLabel(primaryEvidenceCitation.evidence_state)}</small></li>}
          </ol>
        </div>
        {actionAuthorized ? (
          <button type="button" className="engineer-authorized-action" onClick={() => setWorkspace("dial_in", "engineer")}>
            <FlaskConical size={15} aria-hidden="true" /> Open controlled test
          </button>
        ) : (
          <div className="engineer-action-guard" role="note">
            <ShieldCheck size={15} aria-hidden="true" />
            <span>No setup-change control is available from this evidence.</span>
          </div>
        )}
        {asArray(action.blocker_reasons).length > 0 && (
          <ul className="engineer-blockers">
            {action.blocker_reasons.map((blocker) => <li key={blocker}>{blocker}</li>)}
          </ul>
        )}
        <CitationLinks citations={actionCitations} onNavigate={onNavigateCitation} label="Controlled-test evidence" />
      </section>

      <SmartIntelligenceCards
        report={report}
        runId={runId}
        sessionId={sessionId}
        learning={learning}
        setupActionAuthorized={actionAuthorized}
        authorizedSetupAction={authorizedSetupAction}
        workflowRevision={workflowRevision}
        onOpenMove={openNextTrustworthyMove}
        onOpenRecovery={(workspace) => setWorkspace(workspace, "engineer")}
      />

      <div className="engineer-race-support-grid">
        {report.data_quality && (
          <DataQualityCard quality={report.data_quality} learning={learning} onNavigate={onNavigateCitation} />
        )}
        {report.best_measurement && (
          <MeasurementCard measurement={report.best_measurement} learning={learning} onNavigate={onNavigateCitation} />
        )}
      </div>

      <section className="engineer-question-deck" aria-labelledby="engineer-question-heading">
        <header>
          <CircleHelp size={16} aria-hidden="true" />
          <div>
            <span className="eyebrow">Ask this evidence</span>
            <h2 id="engineer-question-heading">Grounded run questions</h2>
          </div>
        </header>
        <form onSubmit={handleSubmit}>
          <label htmlFor="engineer-question">Question about the selected run · {questionScopeLabel}</label>
          {learning && completeWindowQuestionScope && (
            <small>Answers anchor to representative Lap {selectedQueryLap}; full-window pace remains in Laps.</small>
          )}
          <div>
            <Search size={15} aria-hidden="true" />
            <input
              id="engineer-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Where is the strongest repeatable loss?"
              minLength={2}
              maxLength={280}
              autoComplete="off"
              disabled={queryState.status === "loading"}
            />
            <button type="submit" disabled={question.trim().length < 2 || queryState.status === "loading"}>
              {queryState.status === "loading" ? "Checking…" : "Ask"}
            </button>
          </div>
        </form>
        {contextualQuestions.length > 0 && (
          <div className="engineer-question-chips" aria-label={`Suggested grounded questions for ${questionScopeLabel}`}>
            {contextualQuestions.slice(0, learning ? 8 : 5).map((suggestion) => (
              <button
                type="button"
                key={suggestion}
                onClick={() => { void submitQuestion(suggestion); }}
                disabled={queryState.status === "loading"}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
        <div className="engineer-answer" aria-live="polite">
          {queryState.status === "loading" && <p className="engineer-answer-status">Tracing the answer to this run…</p>}
          {queryState.status === "error" && (
            <div className="engineer-answer-error" role="alert">
              <AlertTriangle size={14} aria-hidden="true" /> {queryState.error}
            </div>
          )}
          {queryState.status === "ready" && queryResponse && (
            <article data-grounded={queryHasGrounding && !queryActionWithheld ? "true" : "false"}>
              <header>
                <div>
                  <span className="eyebrow">{queryHasGrounding && !queryActionWithheld ? "Grounded answer" : "Evidence limit"}</span>
                  <h3>{visibleQueryHeadline}</h3>
                </div>
                <span className="engineer-answer-state">
                  {queryActionTrusted ? "Action evidence qualified" : stateLabel(queryResponse.evidence_state)}
                </span>
              </header>
              {!queryResponse.action_authorized && (queryResponse.interpreted_lap_number != null
                 || queryResponse.interpreted_window_start_lap != null
                 || queryResponse.interpreted_phase
                 || queryResponse.interpreted_control_key
                 || queryResponse.interpreted_component_id
                 || queryResponse.interpreted_track_region_label
                || queryResponse.clarification_required) && (
                <div className="engineer-query-interpretation" aria-label="Server-interpreted question context">
                  <span>{queryResponse.clarification_required ? "Clarification needed" : "Interpreted context"}</span>
                  {queryResponse.interpreted_lap_number != null && <strong>Lap {queryResponse.interpreted_lap_number}</strong>}
                  {queryResponse.interpreted_window_start_lap != null && queryResponse.interpreted_window_end_lap != null && (
                    <strong>Window L{queryResponse.interpreted_window_start_lap}\u2013L{queryResponse.interpreted_window_end_lap}</strong>
                  )}
                   {queryResponse.interpreted_phase && <strong>{driverFacingLabel(queryResponse.interpreted_phase)}</strong>}
                   {queryResponse.interpreted_control_key && <strong>{driverFacingLabel(queryResponse.interpreted_control_key)}</strong>}
                   {queryResponse.interpreted_component_id && <strong>{driverFacingLabel(queryResponse.interpreted_component_id)} system</strong>}
                   {queryResponse.interpreted_track_region_label && <strong>{queryResponse.interpreted_track_region_label}</strong>}
                  <small>The answer remains bound to the selected run and question scope.</small>
                </div>
              )}
              <p>{visibleQueryAnswer}</p>
              <MindChangeCriteriaCard
                criteria={queryMindChangeCriteria}
                learning={learning}
                headingId="engineer-query-mind-change-heading"
                scopeLabel="Run-scoped reasoning"
              />
              {queryResponse.action_authorized && !queryActionTrusted && (
                <p className="engineer-query-guard"><ShieldCheck size={13} aria-hidden="true" /> Action withheld because its exact tuning citation was incomplete.</p>
              )}
              {!queryActionWithheld && asArray(queryResponse.blocker_reasons).length > 0 && (
                <ul>{queryResponse.blocker_reasons.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>
              )}
              {!queryActionWithheld && <CitationLinks citations={queryResponse.citations} onNavigate={onNavigateCitation} label="Answer evidence" />}
              {!queryActionWithheld && (
                <CitationLinks
                  citations={queryNavigationCitations}
                  onNavigate={onNavigateCitation}
                  label="Suggested evidence handoffs"
                />
              )}
              {!queryResponse.action_authorized && asArray(queryResponse.follow_up_questions).length > 0 && (
                <div className="engineer-follow-ups">
                  <span>Ask next</span>
                  {queryResponse.follow_up_questions.slice(0, 3).map((followUp) => (
                    <button type="button" key={followUp} onClick={() => { void submitQuestion(followUp); }}>{followUp}</button>
                  ))}
                </div>
              )}
            </article>
          )}
        </div>
      </section>

      {learning && (
        <div className="engineer-learning-grid">
          <LearningReadinessCard state={readinessState} campaignAction={campaignAction} predictionAction={predictionAction} onFreezePrediction={freezePrediction} onStartCampaign={startCampaign} />
          <section className="engineer-learning-card engineer-evidence-graph" aria-labelledby="engineer-graph-heading">
            <header>
              <Link2 size={16} aria-hidden="true" />
              <div><span className="eyebrow">Why this call?</span><h2 id="engineer-graph-heading">Evidence graph</h2></div>
            </header>
            {graphNodes.length > 0 ? (
              <>
                <div className="engineer-graph-nodes">
                  {graphPreviewNodes.map((node) => {
                    const citation = node.citation_id ? citationById.get(node.citation_id) : undefined;
                    return citation ? (
                      <button type="button" key={node.node_id} data-kind={node.kind} onClick={() => { void onNavigateCitation(citation); }}>
                        <span>{node.kind}</span><strong>{driverFacingLabel(node.label)}</strong><small>{node.evidence_state ? stateLabel(node.evidence_state) : "Linked evidence"}</small>
                      </button>
                    ) : (
                      <div key={node.node_id} data-kind={node.kind}>
                        <span>{node.kind}</span><strong>{driverFacingLabel(node.label)}</strong>{node.evidence_state && <small>{stateLabel(node.evidence_state)}</small>}
                      </div>
                    );
                  })}
                </div>
                <ul className="engineer-graph-edges">
                  {graphPreviewEdges.map((edge, index) => {
                    const source = graphNodeById.get(edge.source_id)?.label ?? edge.source_id;
                    const target = graphNodeById.get(edge.target_id)?.label ?? edge.target_id;
                    return <li key={`${edge.source_id}:${edge.target_id}:${edge.relation}:${index}`}><strong>{driverFacingLabel(source)}</strong> {edge.relation} <strong>{driverFacingLabel(target)}</strong></li>;
                  })}
                </ul>
                {graphHasAuditDetail && (
                  <details className="engineer-graph-audit">
                    <summary>Full graph · {graphNodes.length} nodes · {graphEdges.length} relationships</summary>
                    <div>
                      <h3>All nodes</h3>
                      <ul>
                        {graphNodes.map((node) => {
                          const citation = node.citation_id ? citationById.get(node.citation_id) : undefined;
                          return (
                            <li key={node.node_id}>
                              {citation ? (
                                <button type="button" onClick={() => { void onNavigateCitation(citation); }}>
                                  <span>{node.kind}</span> {driverFacingLabel(node.label)}
                                </button>
                              ) : <span><b>{node.kind}</b> {driverFacingLabel(node.label)}</span>}
                            </li>
                          );
                        })}
                      </ul>
                      <h3>All relationships</h3>
                      <ul>
                        {graphEdges.map((edge, index) => {
                          const source = graphNodeById.get(edge.source_id)?.label ?? edge.source_id;
                          const target = graphNodeById.get(edge.target_id)?.label ?? edge.target_id;
                          return <li key={`${edge.source_id}:${edge.target_id}:${edge.relation}:audit:${index}`}><strong>{driverFacingLabel(source)}</strong> {edge.relation} <strong>{driverFacingLabel(target)}</strong></li>;
                        })}
                      </ul>
                    </div>
                  </details>
                )}
              </>
            ) : (
              <p className="engineer-empty-detail">No producer-owned graph was supplied. The cause board remains limited to its exact citations.</p>
            )}
          </section>

          <section className="engineer-learning-card engineer-causes" aria-labelledby="engineer-causes-heading">
            <header>
              <Gauge size={16} aria-hidden="true" />
              <div><span className="eyebrow">Competing explanations</span><h2 id="engineer-causes-heading">Cause board</h2></div>
            </header>
            {asArray(report.competing_causes).length > 0 ? (
              <ol>
                {[...report.competing_causes].sort((left, right) => left.rank - right.rank).map((cause) => (
                  <li key={cause.cause_id} data-state={cause.state}>
                    <header><span>#{cause.rank}</span><strong>{cause.label}</strong><em>{cause.state.replace(/_/g, " ")}</em></header>
                    <p>{cause.reason}</p>
                    <div className="engineer-cause-evidence">
                      <div><h4>Supports</h4><CitationLinks citations={cause.evidence_for} onNavigate={onNavigateCitation} /></div>
                      <div><h4>Contradicts</h4><CitationLinks citations={cause.evidence_against} onNavigate={onNavigateCitation} /></div>
                    </div>
                  </li>
                ))}
              </ol>
            ) : <p className="engineer-empty-detail">No evidence-qualified causes were ranked.</p>}
          </section>

          <section className="engineer-learning-card engineer-calibration" aria-labelledby="engineer-calibration-heading">
            <header>
              <ShieldCheck size={16} aria-hidden="true" />
              <div><span className="eyebrow">Prediction vs. result</span><h2 id="engineer-calibration-heading">Calibration record</h2></div>
            </header>
            <p>{report.calibration.summary}</p>
            {report.calibration.status === "available"
              && report.calibration.qualified_correct != null
              && report.calibration.qualified_total != null && (
                <div className="engineer-calibration-count">
                  <strong>{report.calibration.qualified_correct} / {report.calibration.qualified_total}</strong>
                  <span>protocol-valid gradable direction outcomes</span>
                </div>
              )}
            <p className="engineer-calibration-caveat">{report.calibration.caveat}</p>
          </section>

          <section className="engineer-learning-card engineer-narrative" aria-labelledby="engineer-narrative-heading">
            <header>
              <History size={16} aria-hidden="true" />
              <div><span className="eyebrow">Engineering notebook</span><h2 id="engineer-narrative-heading">Session narrative</h2></div>
            </header>
            {asArray(report.narrative).length > 0 ? (
              <ol>
                {report.narrative.map((entry) => (
                  <li key={entry.entry_id}>
                    <span aria-hidden="true" />
                    <div>
                      <header><strong>{entry.label}</strong>{entry.created_at && <time dateTime={entry.created_at}>{narrativeTime(entry.created_at)}</time>}</header>
                      <p>{entry.summary}</p>
                      <CitationLinks citations={entry.citations} onNavigate={onNavigateCitation} label="Narrative evidence" />
                    </div>
                  </li>
                ))}
              </ol>
            ) : <p className="engineer-empty-detail">No evidence-qualified session history has been recorded yet.</p>}
          </section>

          {report.driver_profile && report.driver_profile.affects_evidence_eligibility === false && (
            <aside className="engineer-learning-card engineer-driver-profile" aria-labelledby="engineer-driver-heading">
              <header>
                <BrainCircuit size={16} aria-hidden="true" />
                <div><span className="eyebrow">Presentation only</span><h2 id="engineer-driver-heading">Adapted presentation</h2></div>
              </header>
              <p>Language: {report.driver_profile.terminology_level ?? "standard"} · Preferred view: {report.driver_profile.preferred_mode ?? "not learned"}</p>
              <p>Consistency: {report.driver_profile.consistency_label ?? "not established"} · Controlled tests: {report.driver_profile.controlled_tests_completed}</p>
              {asArray(report.driver_profile.recurring_symptoms).length > 0 && <p>Recurring terms: {report.driver_profile.recurring_symptoms.join(" · ")}</p>}
              <strong>Personalization never changes lap eligibility, evidence gates, or confidence.</strong>
            </aside>
          )}
        </div>
      )}
    </div>
  );
}

export const EngineerTab = IntelligencePanel;
