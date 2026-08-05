import { AlertTriangle, ClipboardList, Crosshair, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  analyzeRunDialIn,
  attachControlledWorkflowStage,
  fetchControlledWorkflowReport,
  fetchControlledWorkflows,
  scoreControlledWorkflow,
  startControlledWorkflow,
} from "../api/client";
import { useCompareBasket } from "../store/CompareBasketContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type {
  ControlledWorkflow,
  DialInDecisionContext,
  DialInObjective,
  DialInPriority,
  DialInResponse,
  DialInSwing,
  RunOverview,
} from "../types/telemetry";

type DialInTabProps = { overview: RunOverview | null };

const DIAL_IN_INITIAL_LIMIT = 9;
const SHOW_MORE_STEP = 9;
const DIAL_IN_REQUEST_LIMIT = DIAL_IN_INITIAL_LIMIT + SHOW_MORE_STEP;
const MAX_VISIBLE_UNVERIFIED_HYPOTHESES = 3;

const PHASE_OPTIONS = [
  ["", "Auto-detect"],
  ["braking", "Braking"],
  ["entry", "Corner entry"],
  ["center", "Corner center"],
  ["exit", "Corner exit"],
  ["transition", "Transition"],
  ["bump_curb", "Bump or curb"],
  ["straight", "Straight"],
] as const;

const OBJECTIVE_OPTIONS: Array<[DialInObjective, string]> = [
  ["race-pace", "Race pace"],
  ["qualifying", "Qualifying pace"],
  ["long-run", "Long-run consistency"],
  ["tire-conservation", "Tire conservation"],
  ["driver-confidence", "Driver confidence"],
];

const PRIORITY_OPTIONS: Array<[DialInPriority, string]> = [
  ["overall-pace", "Overall pace"],
  ["entry-security", "Entry pace focus"],
  ["center-rotation", "Center pace focus"],
  ["exit-drive", "Exit pace focus"],
  ["tire-life", "Tire life"],
  ["platform-margin", "Platform margin"],
];

function workflowDecisionPresentation(workflow: ControlledWorkflow | null): { label: string; explanation: string } {
  if (workflow?.packet.decision === "measure") {
    return {
      label: "Measurement mission",
      explanation: "No setup change is approved. Gather the named evidence first.",
    };
  }
  if (
    workflow?.status === "scored"
    && workflow.quality?.controlled_effect_eligible
    && workflow.quality.verdict === "keep"
  ) {
    return {
      label: "Fix recommendation",
      explanation: "A completed controlled test supports keeping this exact change.",
    };
  }
  return {
    label: "Exploratory test",
    explanation: "One reversible change will test the leading hypothesis; it is not yet a proven fix.",
  };
}

function cleanLabel(value: string | null | undefined, fallback = "Not mapped"): string {
  if (!value) return fallback;
  const aliases: Record<string, string> = {
    final_drive: "Rear End Ratio",
  };
  if (aliases[value]) return aliases[value];
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function dialInTone(label: string): "good" | "warn" | "neutral" {
  const normalized = label.toLowerCase();
  if (normalized.includes("ready") || normalized.includes("clear") || normalized.includes("clean") || normalized.includes("high")) return "good";
  if (normalized.includes("need") || normalized.includes("partial") || normalized.includes("risk") || normalized.includes("missing") || normalized.includes("some")) return "warn";
  return "neutral";
}

function formatTargetList(swing: DialInSwing): string {
  const labels = swing.validate_with_labels ?? swing.validate_with.map((value) => value.replace(/_/g, " "));
  const targets = labels.filter((item, index, all) => item && all.indexOf(item) === index);
  return targets.join(", ") || "the same corner phase";
}

function garageLeverLabel(swing: DialInSwing): string | null {
  if (swing.setup_area === "shock_collar" || swing.setup_area.includes("ride_height")) {
    return "Garage note: use the named Ride Height fields. If this car exposes collar or perch offsets instead, recheck cross weight after the change.";
  }
  return null;
}

function dialInEvidenceHints(response: DialInResponse): string[] {
  const hints = new Set<string>();
  const nextStep = response.next_step ?? "";
  if (nextStep.includes("Compare baseline is missing")) {
    hints.add("Compare baseline is missing.");
  }
  if (nextStep.includes("Compare test run is missing")) {
    hints.add("Compare test run is missing.");
  }
  for (const warning of response.warnings) {
    const lower = warning.toLowerCase();
    if (lower.includes("car family could not be resolved")) hints.add("Car family is generic, so unsupported legacy-only areas stay filtered.");
    if (lower.includes("track family could not be resolved")) hints.add("Track family is generic, so the guide stays conservative.");
  }
  for (const swing of response.top_swings) {
    if (!swing.readiness_label.toLowerCase().includes("need")) continue;
    const area = swing.setup_area.toLowerCase();
    if (area.includes("shock") || area.includes("damper")) {
      hints.add("Live shock data is missing.");
    }
    if (area.includes("platform") || area.includes("ride") || area.includes("diffuser") || area.includes("rake")) {
      hints.add("Platform trace is missing for a stronger read.");
    }
  }
  return [...hints];
}

function SwingCard({ swing, compact = false, learning = false }: { swing: DialInSwing; compact?: boolean; learning?: boolean }) {
  const helper = garageLeverLabel(swing);
  return (
    <article className={`dialin-swing-card${compact ? " compact" : ""}`}>
      <header>
        <div>
          <span>{cleanLabel(swing.setup_area, "Setup area")}</span>
          <h3>{swing.title}</h3>
          <p className="dialin-change-this"><span>Make this setup change:</span> {swing.change_this}</p>
          <p className="dialin-garage-helper">Garage control{(swing.control_keys?.length ?? 0) > 1 ? "s" : ""}: {swing.garage_lever}</p>
          <p className="dialin-garage-helper"><span>Why this size:</span> {swing.change_size_explanation}</p>
          {helper && <p className="dialin-garage-note">{helper}</p>}
        </div>
        <div className="dialin-card-pills">
          <span className="dialin-mini-pill">{swing.change_size_label}</span>
          <span className="dialin-mini-pill">{swing.influence_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.risk_label)}`}>{swing.risk_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.readiness_label)}`}>{swing.readiness_label}</span>
        </div>
      </header>
      <div className="dialin-action-grid">
        <div><span>Expected improvement</span><p>{swing.effect}</p></div>
        <div><span>Trade-off</span><p>{swing.counter_effect}</p></div>
        <div><span>Keep it if</span><p>{swing.keep_if}</p></div>
        <div><span>Undo it if</span><p>{swing.undo_if}</p></div>
        {!compact && <div><span>Test plan</span><p>{swing.one_change_test}</p></div>}
        {learning && <div><span>What this control does</span><p>{swing.control_expectation}</p></div>}
        {learning && <div><span>Related settings to recheck</span><p>{swing.control_guardrail}</p></div>}
        {learning && (
          <div>
            <span>Evidence signals</span>
            <p>{formatTargetList(swing)}</p>
          </div>
        )}
      </div>
    </article>
  );
}

export function DialInTab({ overview }: DialInTabProps) {
  const { basket } = useCompareBasket();
  const { selection } = useTelemetrySelection();
  const storageKey = overview ? `racerzlab:dial-in:${overview.run_id}` : "racerzlab:dial-in";
  const [complaint, setComplaint] = useState("");
  const [selectedPhase, setSelectedPhase] = useState("");
  const [objective, setObjective] = useState<DialInObjective>("race-pace");
  const [priority, setPriority] = useState<DialInPriority>("overall-pace");
  const [response, setResponse] = useState<DialInResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<ControlledWorkflow | null>(null);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowError, setWorkflowError] = useState<string | null>(null);
  const [certificateMarkdown, setCertificateMarkdown] = useState<string | null>(null);
  const [certificateBusy, setCertificateBusy] = useState(false);
  const [certificateError, setCertificateError] = useState<string | null>(null);

  const persistedDecisionContext = useMemo(() => {
    const persisted = workflow?.reproduction_snapshot?.decision_context;
    if (!persisted || typeof persisted !== "object") return null;
    return persisted as Partial<DialInDecisionContext> & { selected_lap?: number | null };
  }, [workflow?.reproduction_snapshot]);

  useEffect(() => {
    try {
      setComplaint(window.sessionStorage.getItem(storageKey) ?? "");
    } catch {
      setComplaint("");
    }
    setSelectedPhase("");
    setObjective("race-pace");
    setPriority("overall-pace");
    setResponse(null);
    setError(null);
    setWorkflow(null);
    setWorkflowError(null);
    setCertificateMarkdown(null);
    setCertificateError(null);
  }, [storageKey]);

  useEffect(() => {
    setCertificateMarkdown(null);
    setCertificateError(null);
  }, [workflow?.workflow_id]);

  useEffect(() => {
    const context = persistedDecisionContext;
    if (!context) return;
    if (workflow?.complaint) setComplaint(workflow.complaint);
    if (typeof context.selected_phase === "string") setSelectedPhase(context.selected_phase);
    if (OBJECTIVE_OPTIONS.some(([value]) => value === context.objective)) {
      setObjective(context.objective as DialInObjective);
    }
    if (PRIORITY_OPTIONS.some(([value]) => value === context.priority)) {
      setPriority(context.priority as DialInPriority);
    }
  }, [persistedDecisionContext, workflow?.complaint, workflow?.workflow_id]);

  useEffect(() => {
    let cancelled = false;
    if (!overview) return undefined;
    void fetchControlledWorkflows(false).then((items) => {
      if (cancelled) return;
      const related = items.find((item) =>
        item.source_run_id === overview.run_id || Object.values(item.stage_run_ids).includes(overview.run_id));
      const active = items.find((item) => item.status !== "scored" && item.status !== "cancelled");
      setWorkflow(related ?? active ?? null);
    }).catch(() => { /* Explicit workflow actions surface actionable errors. */ });
    return () => { cancelled = true; };
  }, [overview]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(storageKey, complaint);
    } catch {
      // Session storage is a convenience only.
    }
  }, [complaint, storageKey]);

  const decisionContext = useMemo<DialInDecisionContext>(() => {
    const zoneIsForRun = selection.selectedRunId === overview?.run_id
      && selection.selectedZoneStartPct != null
      && selection.selectedZoneEndPct != null;
    return {
      selected_zone_start_pct: zoneIsForRun ? selection.selectedZoneStartPct : undefined,
      selected_zone_end_pct: zoneIsForRun ? selection.selectedZoneEndPct : undefined,
      selected_zone_label: zoneIsForRun ? selection.selectedZoneLabel : undefined,
      selected_phase: selectedPhase || undefined,
      objective,
      priority,
    };
  }, [
    objective,
    overview?.run_id,
    priority,
    selectedPhase,
    selection.selectedRunId,
    selection.selectedZoneEndPct,
    selection.selectedZoneLabel,
    selection.selectedZoneStartPct,
  ]);

  const displayedDecisionContext = useMemo<DialInDecisionContext>(() => {
    if (decisionContext.selected_zone_start_pct != null && decisionContext.selected_zone_end_pct != null) {
      return decisionContext;
    }
    return {
      ...decisionContext,
      selected_zone_start_pct: persistedDecisionContext?.selected_zone_start_pct,
      selected_zone_end_pct: persistedDecisionContext?.selected_zone_end_pct,
      selected_zone_label: persistedDecisionContext?.selected_zone_label,
    };
  }, [decisionContext, persistedDecisionContext]);

  const workflowContextMatches = useMemo(() => {
    if (!workflow || !persistedDecisionContext) return true;
    const closeEnough = (current: number | null | undefined, persisted: number | null | undefined) =>
      current == null ? true : persisted != null && Math.abs(current - persisted) <= 0.05;
    const explicitZoneMatches = closeEnough(
      decisionContext.selected_zone_start_pct,
      persistedDecisionContext.selected_zone_start_pct,
    ) && closeEnough(
      decisionContext.selected_zone_end_pct,
      persistedDecisionContext.selected_zone_end_pct,
    );
    const selectedLap = selection.selectedRunId === workflow.source_run_id ? selection.selectedLap : undefined;
    const explicitLapMatches = selectedLap == null
      || (persistedDecisionContext.selected_lap != null
        && selectedLap === persistedDecisionContext.selected_lap);
    const normalizedComplaint = complaint.trim().toLocaleLowerCase().replace(/\s+/g, " ");
    const persistedComplaint = workflow.complaint.trim().toLocaleLowerCase().replace(/\s+/g, " ");
    return explicitZoneMatches
      && explicitLapMatches
      && normalizedComplaint === persistedComplaint
      && (selectedPhase || undefined) === (persistedDecisionContext.selected_phase || undefined)
      && objective === (persistedDecisionContext.objective ?? "race-pace")
      && priority === (persistedDecisionContext.priority ?? "overall-pace");
  }, [
    decisionContext.selected_zone_end_pct,
    decisionContext.selected_zone_start_pct,
    complaint,
    objective,
    persistedDecisionContext,
    priority,
    selectedPhase,
    selection.selectedLap,
    selection.selectedRunId,
    workflow,
  ]);

  const submitDialIn = useCallback(async () => {
    if (!overview) return;
    const trimmed = complaint.trim();
    if (!trimmed || loading) return;
    const baselineRunId = basket.baseline?.run_id ?? null;
    const usableBaseline = baselineRunId && baselineRunId !== overview.run_id ? baselineRunId : undefined;
    setLoading(true);
    setError(null);
    try {
      const selectedLap = selection.selectedRunId === overview.run_id ? selection.selectedLap : undefined;
      const [dialResult, workflowResult] = await Promise.allSettled([
        analyzeRunDialIn(overview.run_id, {
          complaint: trimmed,
          selected_lap: selectedLap,
          ...decisionContext,
          baseline_run_id: usableBaseline,
          limit: DIAL_IN_REQUEST_LIMIT,
          include_debug_evidence: false,
        }),
        startControlledWorkflow({
          run_id: overview.run_id,
          complaint: trimmed,
          selected_lap: selectedLap,
          ...decisionContext,
        }),
      ]);
      if (workflowResult.status === "rejected") throw workflowResult.reason;
      setWorkflow(workflowResult.value);
      setWorkflowError(null);
      setResponse(dialResult.status === "fulfilled" ? dialResult.value : null);
    } catch (caught) {
      setResponse(null);
      setError(caught instanceof Error ? caught.message : "Dial-in request failed.");
    } finally {
      setLoading(false);
    }
  }, [basket.baseline, complaint, decisionContext, loading, overview, selection.selectedLap, selection.selectedRunId]);

  const clearDialIn = useCallback(() => {
    setComplaint("");
    setResponse(null);
    setError(null);
    setWorkflow(null);
    setWorkflowError(null);
    setCertificateMarkdown(null);
    setCertificateError(null);
  }, []);

  const buildVerifiedWorkflow = useCallback(async () => {
    if (!overview || workflowBusy) return;
    setWorkflowBusy(true);
    setWorkflowError(null);
    try {
      setWorkflow(await startControlledWorkflow({
        run_id: overview.run_id,
        complaint: complaint.trim(),
        selected_lap: selection.selectedRunId === overview.run_id ? selection.selectedLap : undefined,
        ...decisionContext,
      }));
    } catch (caught) {
      setWorkflowError(caught instanceof Error ? caught.message : "Verified test planning failed.");
    } finally {
      setWorkflowBusy(false);
    }
  }, [complaint, decisionContext, overview, selection.selectedLap, selection.selectedRunId, workflowBusy]);

  const nextWorkflowStage = workflow && workflow.packet.decision === "test"
    ? (["A", "B", "A2"] as const).find((stage) => !workflow.stage_run_ids[stage])
    : undefined;

  const recordCurrentRun = useCallback(async () => {
    if (!overview || !workflow || !nextWorkflowStage || workflowBusy || !workflowContextMatches) return;
    setWorkflowBusy(true);
    setWorkflowError(null);
    try {
      setWorkflow(await attachControlledWorkflowStage(workflow.workflow_id, nextWorkflowStage, overview.run_id));
    } catch (caught) {
      setWorkflowError(caught instanceof Error ? caught.message : "The current run did not pass stage verification.");
    } finally {
      setWorkflowBusy(false);
    }
  }, [nextWorkflowStage, overview, workflow, workflowBusy, workflowContextMatches]);

  const scoreVerifiedWorkflow = useCallback(async () => {
    if (!workflow || workflowBusy || !workflowContextMatches) return;
    setWorkflowBusy(true);
    setWorkflowError(null);
    try {
      setWorkflow(await scoreControlledWorkflow(workflow.workflow_id));
    } catch (caught) {
      setWorkflowError(caught instanceof Error ? caught.message : "Controlled test scoring failed.");
    } finally {
      setWorkflowBusy(false);
    }
  }, [workflow, workflowBusy, workflowContextMatches]);

  const chooseClarification = useCallback((option: string) => {
    const base = response?.complaint_raw.trim() || complaint.trim();
    const normalized = base.toLowerCase();
    const refinement = option === "Whole corner" ? "center" : option.toLowerCase();
    const nextComplaint = normalized.includes(refinement) ? base : `${base} ${refinement}`;
    setComplaint(nextComplaint.trim());
    setResponse(null);
    setError(null);
  }, [complaint, response]);

  const openTestCertificate = useCallback(async () => {
    if (!workflow || certificateBusy) return;
    setCertificateBusy(true);
    setCertificateError(null);
    try {
      const certificate = await fetchControlledWorkflowReport(workflow.workflow_id);
      setCertificateMarkdown(certificate.markdown);
    } catch (caught) {
      setCertificateError(caught instanceof Error ? caught.message : "The test certificate could not be loaded.");
    } finally {
      setCertificateBusy(false);
    }
  }, [certificateBusy, workflow]);

  const copyTestCertificate = useCallback(async () => {
    if (!certificateMarkdown) return;
    try {
      await navigator.clipboard.writeText(certificateMarkdown);
      setCertificateError(null);
    } catch {
      setCertificateError("Clipboard access was denied. Download the Markdown certificate instead.");
    }
  }, [certificateMarkdown]);

  const downloadTestCertificate = useCallback(() => {
    if (!certificateMarkdown || !workflow) return;
    const url = URL.createObjectURL(new Blob([certificateMarkdown], { type: "text/markdown;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `racerzlab-test-certificate-${workflow.workflow_id}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [certificateMarkdown, workflow]);

  const hints = response ? dialInEvidenceHints(response) : [];
  const primarySwings = useMemo(() => response?.top_swings.slice(0, 1) ?? [], [response]);
  const secondarySwings = useMemo(
    () => response?.top_swings.slice(1, MAX_VISIBLE_UNVERIFIED_HYPOTHESES) ?? [],
    [response],
  );
  const decisionPresentation = workflowDecisionPresentation(workflow);
  const canSubmit = Boolean(overview) && complaint.trim().length > 0 && !loading;
  const runLabel = overview
    ? `${overview.session.car_name ?? "Unknown car"}${overview.session.track_display_name || overview.session.track_name ? ` - ${overview.session.track_display_name ?? overview.session.track_name}` : ""}`
    : "No run selected";

  if (!overview) {
    return (
      <section className="dialin-tab">
        <div className="dialin-panel dialin-hero">
          <div className="dialin-header">
            <div>
              <h2><ClipboardList size={16} /> Crew Chief Dial-In</h2>
              <p>Select or import a run before using Dial-In.</p>
            </div>
            <span className="dialin-readonly">Read-only</span>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="dialin-tab" aria-labelledby="dialin-title">
      <div className="dialin-panel dialin-hero">
        <div className="dialin-header">
          <div>
            <h2 id="dialin-title"><ClipboardList size={16} /> Crew Chief Dial-In</h2>
            <p>{runLabel}</p>
          </div>
          <span className="dialin-readonly">Read-only</span>
        </div>
        <p className="dialin-tab-subtitle">
          Tell RacerZLab what the car is doing. It will verify whether one specific setup test is justified.
        </p>
        {!overview.setup_snapshot && (
          <div className="dialin-alert limited" role="status">
            <AlertTriangle size={14} />
            <span>Setup snapshot unavailable. Garage-specific recommendations are limited until setup data is available, so Dial-In will stay conservative.</span>
          </div>
        )}

        <form
          className="dialin-input-row dialin-command-bar"
          onSubmit={(event) => {
            event.preventDefault();
            void submitDialIn();
          }}
        >
          <input
            className="dialin-input"
            value={complaint}
            onChange={(event) => setComplaint(event.target.value)}
            placeholder="Example: loose off, tight center, RF is angry, nose is dragging, won't stay on bottom"
            aria-label="Driver complaint"
          />
          <button className="secondary-button" type="submit" disabled={!canSubmit} title="Check data and symptoms">
            <Search size={14} /> {loading ? "Checking run data" : "Check Data & Symptoms"}
          </button>
          <button className="secondary-button" type="button" onClick={clearDialIn} disabled={!complaint && !response && !error} title="Clear complaint">
            <X size={14} /> Clear
          </button>
        </form>

        <div className="dialin-summary-grid" aria-label="Dial-In decision context">
          <div>
            <label htmlFor="dialin-phase">Phase</label>
            <select
              id="dialin-phase"
              className="dialin-input"
              value={selectedPhase}
              onChange={(event) => setSelectedPhase(event.target.value)}
            >
              {PHASE_OPTIONS.map(([value, label]) => <option value={value} key={value || "auto"}>{label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="dialin-objective">Objective</label>
            <select
              id="dialin-objective"
              className="dialin-input"
              value={objective}
              onChange={(event) => setObjective(event.target.value as DialInObjective)}
            >
              {OBJECTIVE_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="dialin-priority">Priority</label>
            <select
              id="dialin-priority"
              className="dialin-input"
              value={priority}
              onChange={(event) => setPriority(event.target.value as DialInPriority)}
            >
              {PRIORITY_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </div>
          <div>
            <span>Track area</span>
            <strong>
              {displayedDecisionContext.selected_zone_label
                ?? (displayedDecisionContext.selected_zone_start_pct != null && displayedDecisionContext.selected_zone_end_pct != null
                  ? `${displayedDecisionContext.selected_zone_start_pct.toFixed(1)}-${displayedDecisionContext.selected_zone_end_pct.toFixed(1)}%`
                  : "Auto-detect")}
            </strong>
          </div>
        </div>

        <div className="dialin-rule-note">
          <Crosshair size={13} />
          <span>Pick one change. Just one. Run clean laps and compare.</span>
        </div>
      </div>

      {error && (
        <div className="dialin-alert" role="alert">
          <AlertTriangle size={14} />
          <span>
            I couldn't run Dial-In on this run. Try again or check that the run is loaded.
            {selection.selectedMode === "learning" ? ` Technical detail: ${error}` : ""}
          </span>
        </div>
      )}

      {!response && !error && !workflow && (
        <div className="dialin-empty" role="status" aria-live="polite" aria-busy={loading}>
          {loading ? "Checking your complaint against the run data..." : "Tell me what the car is doing, and I'll check the data."}
        </div>
      )}

      {!response && workflow && (
        <section className="dialin-aba-card dialin-verified-workflow" aria-label="Resumed controlled test workflow">
          <header>
            <div>
              <span className="eyebrow">{decisionPresentation.label}</span>
              <h3>{workflow.packet.race_mode_summary}</h3>
            </div>
            <span className="dialin-mini-pill">{workflow.status.replace(/_/g, " ")}</span>
          </header>
          {selection.selectedMode === "learning" && <p className="section-note">{decisionPresentation.explanation}</p>}
          {!workflowContextMatches && (
            <div className="dialin-alert limited" role="alert">
              <AlertTriangle size={14} />
              <span>Decision context changed. Build a new verified plan before attaching or scoring runs.</span>
            </div>
          )}
          {workflow.packet.decision === "measure" && workflow.packet.measurement_mission && (
            <div className="dialin-mission">
              <strong>No setup change is approved.</strong>
              <p>{workflow.packet.measurement_mission.purpose}</p>
              {selection.selectedMode === "learning" && <p className="section-note">{workflow.packet.measurement_mission.blockers.join(" ")}</p>}
            </div>
          )}
          {workflow.packet.decision === "test" && workflow.packet.primary_test && (
            <>
              <p><strong>{workflow.packet.primary_test.exact_change}</strong></p>
              <div className="dialin-aba-stages">
              {workflow.packet.primary_test.stages.map((stage) => (
                  <div className={`dialin-aba-stage ${workflow.stage_run_ids[stage.stage] ? "complete" : ""}`} key={stage.stage}>
                    <strong>{stage.stage}</strong>
                    <span>{workflow.stage_run_ids[stage.stage] ? "Server verified" : stage.setup_instruction}</span>
                  </div>
              ))}
              </div>
              <p className="section-note">Rollback: {workflow.packet.primary_test.rollback_rule}</p>
              {nextWorkflowStage && <button className="secondary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches} onClick={() => void recordCurrentRun()}>Verify current run as {nextWorkflowStage}</button>}
              {!nextWorkflowStage && workflow.status !== "scored" && <button className="primary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches} onClick={() => void scoreVerifiedWorkflow()}>Score verified A/B/A2</button>}
              {workflow.quality && <p className="dialin-driver-message">{workflow.quality.verdict.toUpperCase()} · {workflow.quality.score.toFixed(0)}/100 · {workflow.quality.supporting_evidence[0] ?? workflow.quality.contradictory_evidence[0]}</p>}
              {workflow.quality?.controlled_effect_eligible && workflow.learning_admitted === false && (
                <p className="section-note">The test verdict is valid, but setup memory rejected the observation because its provenance contract was incomplete.</p>
              )}
            </>
          )}
          {workflowError && <div className="dialin-alert limited" role="alert"><AlertTriangle size={14} /><span>{workflowError}</span></div>}
        </section>
      )}

      {response && (
        <div className="dialin-result">
          <div className="dialin-summary-grid">
            <div>
              <span>Interpreted</span>
              <strong>{cleanLabel(response.interpreted_symptom)}</strong>
            </div>
            <div>
              <span>Phase</span>
              <strong>{cleanLabel(response.interpreted_phase, "Needs phase")}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong className={`dialin-pill ${dialInTone(response.confidence_label)}`}>{response.confidence_label}</strong>
            </div>
            <div>
              <span>Data Profile</span>
              <strong className={`dialin-pill ${dialInTone(response.readiness_label)}`}>{response.readiness_label}</strong>
            </div>
            <div>
              <span>Evidence</span>
              <strong className={`dialin-pill ${dialInTone(response.evidence_state)}`}>{cleanLabel(response.evidence_state)}</strong>
            </div>
            <div>
              <span>Mechanism proof</span>
              <strong className={`dialin-pill ${dialInTone(response.evidence_strength?.readiness ?? "blocked")}`}>
                {cleanLabel(response.evidence_strength?.level, "Unavailable")}
              </strong>
            </div>
          </div>

          <p className="dialin-driver-message">{response.driver_message}</p>
          {selection.selectedMode === "learning" && response.evidence_strength && (
            <p className="section-note">{response.evidence_strength.reason}</p>
          )}

          <section className="dialin-aba-card dialin-verified-workflow" aria-label="Verified controlled test workflow">
            <header>
              <div>
                <span className="eyebrow">{workflow ? decisionPresentation.label : "Server-verified Test Director"}</span>
                <h3>{workflow ? workflow.packet.race_mode_summary : "Build the evidence-gated plan"}</h3>
              </div>
              {(!workflow || !workflowContextMatches) && (
                <button className="primary-button" type="button" disabled={workflowBusy} onClick={() => void buildVerifiedWorkflow()}>
                  {workflowBusy ? "Verifying evidence" : workflow ? "Build new verified plan" : "Build verified plan"}
                </button>
              )}
            </header>
            {workflow && selection.selectedMode === "learning" && (
              <>
                <p className="section-note">{decisionPresentation.explanation}</p>
                <p className="section-note">
                  Evidence strength {(workflow.packet.confidence_score * 100).toFixed(0)}/100. {workflow.packet.confidence_basis}
                </p>
                {workflow.packet.recommendation_score_basis && (
                  <p className="section-note">Ranking basis: {workflow.packet.recommendation_score_basis}</p>
                )}
              </>
            )}
            {workflowError && <div className="dialin-alert limited" role="alert"><AlertTriangle size={14} /><span>{workflowError}</span></div>}
            {workflow && !workflowContextMatches && (
              <div className="dialin-alert limited" role="alert">
                <AlertTriangle size={14} />
                <span>Decision context changed. Build a new verified plan before attaching or scoring runs.</span>
              </div>
            )}
            {workflow?.packet.decision === "measure" && workflow.packet.measurement_mission && (
              <div className="dialin-mission">
                <strong>Measurement mission · {workflow.packet.measurement_mission.required_laps_or_passes} passes</strong>
                <p>{workflow.packet.measurement_mission.purpose}</p>
                {selection.selectedMode === "learning" && (
                  <>
                    <ol>{workflow.packet.measurement_mission.procedure.map((step) => <li key={step}>{step}</li>)}</ol>
                    <p className="section-note">Stop rule: {workflow.packet.measurement_mission.stop_rule}</p>
                  </>
                )}
              </div>
            )}
            {workflow?.packet.decision === "test" && workflow.packet.primary_test && (
              <>
                <p><strong>{workflow.packet.primary_test.exact_change}</strong> · {workflow.packet.primary_test.change_size}</p>
                <p className="section-note">Rollback: {workflow.packet.primary_test.rollback_rule}</p>
                {selection.selectedMode === "learning" && <p className="section-note">{workflow.packet.learning_mode_explanation}</p>}
                <div className="dialin-aba-stages">
                  {workflow.packet.primary_test.stages.map((stage) => (
                    <div className={`dialin-aba-stage ${workflow.stage_run_ids[stage.stage] ? "complete" : ""}`} key={stage.stage}>
                      <strong>{stage.stage}</strong>
                      <span>{workflow.stage_run_ids[stage.stage] ? "Server verified" : `${stage.warmup_laps} warm-up + ${stage.required_flying_laps} flying laps`}</span>
                    </div>
                  ))}
                </div>
                {nextWorkflowStage && (
                  <button className="secondary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches} onClick={() => void recordCurrentRun()}>
                    {workflowBusy ? "Checking run" : `Verify current run as ${nextWorkflowStage}`}
                  </button>
                )}
                {!nextWorkflowStage && workflow.status !== "scored" && (
                  <button className="primary-button dialin-workflow-action" type="button" disabled={workflowBusy || !workflowContextMatches} onClick={() => void scoreVerifiedWorkflow()}>
                    {workflowBusy ? "Scoring all eligible laps" : "Score verified A/B/A2"}
                  </button>
                )}
                {workflow.quality && (
                  <div className={`dialin-alert ${workflow.quality.controlled_effect_eligible ? "" : "limited"}`}>
                    <strong>{workflow.quality.verdict.toUpperCase()} · {workflow.quality.score.toFixed(0)}/100</strong>
                    <span>{workflow.quality.supporting_evidence[0] ?? workflow.quality.blockers[0] ?? workflow.quality.contradictory_evidence[0]}</span>
                  </div>
                )}
                {workflow.quality?.controlled_effect_eligible && workflow.learning_admitted === false && (
                  <p className="section-note">Result scored, but setup memory did not admit it; no learned response is implied.</p>
                )}
              </>
            )}
          </section>

          {response.blocker_reasons.length > 0 && (
            <div className="dialin-alert limited" role="status">
              <AlertTriangle size={14} />
              <span>{response.blocker_reasons.join(" ")}</span>
            </div>
          )}

          {selection.selectedMode === "learning" && response.source_channels.length > 0 && (
            <p className="section-note">Measured sources: {response.source_channels.join(", ")}</p>
          )}

          {response.clarification.needed && (
            <div className="dialin-clarification">
              <strong>{response.clarification.question ?? "Clarify the complaint phase."}</strong>
              <div className="dialin-chip-row">
                {response.clarification.options.map((option) => (
                  <button className="dialin-chip dialin-chip-button" key={option} type="button" onClick={() => chooseClarification(option)}>
                    {option}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!response.clarification.needed && response.top_swings.length === 0 && (
            <div className="dialin-empty">I need stronger data before ranking setup changes.</div>
          )}

          {selection.selectedMode === "learning" && !response.clarification.needed && response.top_swings.length > 0 && (
            <>
              <div className="dialin-section-header">
                <div>
                  <span>Unverified hypotheses</span>
                  <h3>Ideas awaiting evidence-gated approval</h3>
                </div>
                <p>These explain possible mechanisms only. The server-verified Test Director above is the only setup action.</p>
              </div>
              <div className="dialin-swings">
                {primarySwings.map((swing) => (
                  <div key={swing.id}>
                    <SwingCard swing={swing} learning={selection.selectedMode === "learning"} />
                  </div>
                ))}
              </div>

              {secondarySwings.length > 0 && (
                <>
                  <div className="dialin-section-header compact">
                    <div>
                      <span>Lower priority</span>
                      <h3>Other hypotheses</h3>
                    </div>
                    <p>Only the top three are shown. These are explanations, not approved setup changes.</p>
                  </div>
                  <div className="dialin-other-grid">
                    {secondarySwings.map((swing) => (
                      <SwingCard swing={swing} compact learning={selection.selectedMode === "learning"} key={swing.id} />
                    ))}
                  </div>
                </>
              )}
            </>
          )}

          <div className="dialin-evidence-status">
            <span>Data Profile</span>
            <strong>{response.next_step ?? response.readiness_label}</strong>
            {hints.length > 0 && (
              <div className="dialin-chip-row">
                {hints.map((hint) => <span className="dialin-chip" key={hint}>{hint}</span>)}
              </div>
            )}
          </div>
        </div>
      )}

      {workflow?.status === "scored" && workflow.quality && (
        <section className="dialin-aba-card dialin-test-certificate" aria-label="Controlled test certificate">
          <header>
            <div>
              <span className="eyebrow">Auditable test certificate</span>
              <h3>{workflow.quality.verdict.toUpperCase()} · {workflow.quality.score.toFixed(0)}/100 evidence strength</h3>
            </div>
            <span className={`dialin-mini-pill ${workflow.quality.controlled_effect_eligible ? "complete" : ""}`}>
              {workflow.learning_admitted === true ? "Memory admitted" : "No learned claim"}
            </span>
          </header>
          <p><strong>{workflow.packet.primary_test?.exact_change ?? "No setup change certified"}</strong></p>
          {workflow.execution && (
            <div className="dialin-certificate-metrics">
              <div><span>B vs A</span><strong>{workflow.execution.phase_effect_b_vs_a_s?.toFixed(3) ?? "Unavailable"} s</strong></div>
              <div><span>B vs A2</span><strong>{workflow.execution.phase_effect_b_vs_a2_s?.toFixed(3) ?? "Unavailable"} s</strong></div>
              <div><span>Noise floor</span><strong>{workflow.execution.empirical_noise_s?.toFixed(3) ?? "Unavailable"} s</strong></div>
              <div><span>Lap response</span><strong>{workflow.execution.target_effect_distribution_state ?? "Unavailable"}</strong></div>
              <div><span>Other phases</span><strong>{workflow.execution.countereffect_passed === true ? "Passed" : workflow.execution.countereffect_passed === false ? "Rollback" : "Unavailable"}</strong></div>
              <div><span>Control safety</span><strong>{workflow.execution.control_guardrails_passed === true ? "Passed" : workflow.execution.control_guardrails_passed === false ? "Rollback" : "Unavailable"}</strong></div>
            </div>
          )}
          <p className="section-note">
            {workflow.quality.supporting_evidence[0] ?? workflow.quality.blockers[0] ?? workflow.quality.contradictory_evidence[0]}
          </p>
          <div className="dialin-certificate-actions">
            {!certificateMarkdown && (
              <button className="secondary-button" type="button" disabled={certificateBusy} onClick={() => void openTestCertificate()}>
                {certificateBusy ? "Building certificate" : "Open full certificate"}
              </button>
            )}
            {certificateMarkdown && <button className="secondary-button" type="button" onClick={() => void copyTestCertificate()}>Copy Markdown</button>}
            {certificateMarkdown && <button className="secondary-button" type="button" onClick={downloadTestCertificate}>Download Markdown</button>}
          </div>
          {certificateError && <div className="dialin-alert limited" role="alert"><AlertTriangle size={14} /><span>{certificateError}</span></div>}
          {certificateMarkdown && selection.selectedMode === "learning" && (
            <details className="dialin-certificate-details" open>
              <summary>Reproduction evidence and provenance</summary>
              <pre>{certificateMarkdown}</pre>
            </details>
          )}
        </section>
      )}
    </section>
  );
}
