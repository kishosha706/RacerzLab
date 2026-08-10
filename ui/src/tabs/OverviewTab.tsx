import { AlertTriangle, BrainCircuit, CheckCircle2, Clock, Layers, MapPin, Wrench } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { EvidenceCard } from "../components/EvidenceCard";
import { EngineeringMetricCard } from "../components/EngineeringMetricCard";
import { EngineeringAwarenessPanel } from "../components/EngineeringAwarenessPanel";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { SEVERITY_COLOURS, humanizeEventLabel } from "../constants/ui";
import { isProxyChannel } from "../utils/channelMeta";
import { buildZoneEvidence } from "../utils/evidenceFocus";
import {
  bestUsefulLapMatchesRun,
  overviewWarningBlocksDecision,
  recommendationBlockedReason,
  recommendationIsActionable,
  setupSnapshotMatchesRun,
  telemetryEventIsActionable,
} from "../utils/evidenceTrust";
import type { LapSummary, RunOverview, TelemetryCapabilitiesResponse, TelemetryEvent } from "../types/telemetry";

type OverviewTabProps = {
  overview: RunOverview;
  sessionId?: string | null;
  telemetryCapabilities?: TelemetryCapabilitiesResponse | null;
  onToggleMapOverlay?: () => void;
};

const LONG_RUN_REVIEW_MIN_LAPS = 10;

function longestContinuousEligibleLapBlock(laps: readonly LapSummary[]): number {
  const lapNumbers = [...new Set(laps.map((lap) => lap.lap_number))].sort((left, right) => left - right);
  let longest = 0;
  let current = 0;
  let previous: number | null = null;
  for (const lapNumber of lapNumbers) {
    current = previous != null && lapNumber === previous + 1 ? current + 1 : 1;
    longest = Math.max(longest, current);
    previous = lapNumber;
  }
  return longest;
}

function explicitOvalPhase(event: TelemetryEvent): "Entry" | "Center" | "Exit" | "Straight" | null {
  const evidenceLabel = `${event.event_type} ${event.event_subtype ?? ""} ${event.zone_name ?? ""}`.toLowerCase();
  if (/entry|brak|turn.?in/.test(evidenceLabel)) return "Entry";
  if (/center|centre|mid.?corner|apex|rotation|yaw/.test(evidenceLabel)) return "Center";
  if (/exit|throttle|drive.?off|power.?down/.test(evidenceLabel)) return "Exit";
  if (/straight|full.?throttle|speed.?loss|resist|scrub/.test(evidenceLabel)) return "Straight";
  return null;
}

function eventLocationLabel(event: TelemetryEvent): string {
  if (event.zone_name?.trim()) return event.zone_name.trim();
  const lapPct = event.lap_pct_peak ?? event.lap_pct_start;
  return lapPct != null && Number.isFinite(lapPct)
    ? `${lapPct.toFixed(1)}% lap distance`
    : "Run-level evidence";
}

function severityLabel(severity: TelemetryEvent["severity"]): "CRITICAL" | "HIGH" | "WATCH" | "INFO" {
  if (severity === "critical") return "CRITICAL";
  if (severity === "high") return "HIGH";
  if (severity === "watch") return "WATCH";
  return "INFO";
}

function buildWhyText(event: TelemetryEvent, isLearning: boolean): string {
  const parts: string[] = [];
  const t = humanizeEventLabel(event.event_type);
  if (event.primary_metric_name && event.primary_metric_value != null) {
    const pv = Number(event.primary_metric_value);
    parts.push(`${t} at ${pv.toFixed(2)}`);
  } else {
    parts.push(t);
  }

  if (event.severity === "critical") parts.push("this is a critical risk");
  else if (event.severity === "high") parts.push("elevated risk zone");
  else if (event.severity === "watch") parts.push("monitor this area");

  if (isLearning && event.confidence_score != null && event.confidence_score < 0.6) {
    parts.push("low confidence, treat as proxy/estimate until repeated");
  }
  return parts.join(" - ");
}

function orderedWarnings(warnings: string[]): Array<{ key: string; label: string; matches: string[]; items: string[] }> {
  const definitions = [
    { key: "missing_required", label: "Missing required telemetry", matches: ["missing required"] },
    { key: "missing_optional", label: "Missing optional telemetry", matches: ["missing optional"] },
    {
      key: "setup_snapshot",
      label: "Setup snapshot unavailable",
      matches: [
        "setup snapshot",
        "snapshot unavailable",
        "snapshot missing",
        "carsetup unavailable",
        "carsetup missing",
        "no setup data",
        "garage values unavailable",
      ],
    },
    { key: "proxy_heavy", label: "Proxy/estimate-heavy result", matches: ["proxy", "estimate"] },
    { key: "short_run", label: "Short run / low confidence", matches: ["short", "low confidence", "insufficient", "few laps"] },
  ];
  const assigned = new Set<number>();
  const groups = definitions.map((group) => ({
    ...group,
    items: warnings.filter((warning, index) => {
      if (assigned.has(index) || !group.matches.some((match) => warning.toLowerCase().includes(match))) return false;
      assigned.add(index);
      return true;
    }),
  }));
  const other = warnings.filter((_, index) => !assigned.has(index));
  return other.length > 0
    ? [...groups, { key: "other", label: "Other data-quality warnings", matches: [], items: other }]
    : groups;
}

export function OverviewTab({ overview, sessionId = null, telemetryCapabilities, onToggleMapOverlay }: OverviewTabProps) {
  const lap = bestUsefulLapMatchesRun(overview.best_useful_lap, overview.run_id)
    ? overview.best_useful_lap
    : null;
  const { setWorkspace, focusEvidence, selection } = useTelemetrySelection();
  const [openWarningKeys, setOpenWarningKeys] = useState<Record<string, boolean>>({});
  const isLearning = selection.selectedMode === "learning";

  const sortedEvents = useMemo(() => {
    const sevOrder: Record<string, number> = { critical: 0, high: 1, watch: 2, info: 3 };
    return [...overview.events].sort((a, b) => {
      const aActionable = telemetryEventIsActionable(a);
      const bActionable = telemetryEventIsActionable(b);
      if (aActionable !== bActionable) return aActionable ? -1 : 1;
      const sevDiff = (sevOrder[a.severity] ?? 9) - (sevOrder[b.severity] ?? 9);
      if (sevDiff !== 0) return sevDiff;
      const confA = a.confidence_score ?? 0;
      const confB = b.confidence_score ?? 0;
      if (confB !== confA) return confB - confA;
      return 0;
    });
  }, [overview.events]);

  const topEvent = sortedEvents.find(telemetryEventIsActionable) ?? null;
  const topObservedEvent = useMemo(() => {
    const severityOrder: Record<string, number> = { critical: 0, high: 1, watch: 2, info: 3 };
    return [...overview.events].sort((left, right) => {
      const severityDifference = (severityOrder[left.severity] ?? 9) - (severityOrder[right.severity] ?? 9);
      if (severityDifference !== 0) return severityDifference;
      return (right.confidence_score ?? 0) - (left.confidence_score ?? 0);
    })[0] ?? null;
  }, [overview.events]);
  const evidenceQualifiedRecommendations = useMemo(
    () => overview.recommendations.filter((recommendation) => (
      recommendationIsActionable(recommendation, overview.events)
    )),
    [overview.events, overview.recommendations],
  );

  const buildOverviewEvidence = useCallback((event: TelemetryEvent) => {
    const hasLocation = event.lap_pct_peak != null || event.lap_pct_start != null || event.distance_m_peak != null;
    const lapDistFt = event.distance_m_peak != null ? event.distance_m_peak * 3.280839895 : null;
    const lapPct = event.lap_pct_peak ?? event.lap_pct_start ?? null;
    const zoneEvidence = selection.selectedRunId === overview.run_id
      ? buildZoneEvidence(selection, { lapPct })
      : { zoneId: null, zoneLabel: null, zoneStartPct: null, zoneEndPct: null };
    return {
      runId: overview.run_id,
      lapNumber: event.lap_number ?? null,
      lapScope: event.lap_number != null ? "single_lap" as const : "run" as const,
      lapWindowStart: null,
      lapWindowEnd: null,
      representativeLap: null,
      eventId: event.event_id,
      sampleIndex: null,
      lapDistFt,
      lapPct,
      ...zoneEvidence,
      channelId: null,
      lockState: (hasLocation ? "locked" : "none") as "locked" | "none",
      valueBasis: (hasLocation ? "selected_sample" : "run_level") as "selected_sample" | "run_level",
      selectionSource: "overview" as const,
    };
  }, [overview.run_id, selection]);

  const openTopEvent = useCallback(() => {
    if (!topEvent) return;
    focusEvidence(buildOverviewEvidence(topEvent), "platform_trace");
  }, [topEvent, buildOverviewEvidence, focusEvidence]);

  const openObservedEvent = useCallback(() => {
    if (!topObservedEvent) return;
    focusEvidence(buildOverviewEvidence(topObservedEvent), "platform_trace");
  }, [buildOverviewEvidence, focusEvidence, topObservedEvent]);

  const openTopEventMapOverlay = useCallback(() => {
    if (!topEvent) return;
    focusEvidence(buildOverviewEvidence(topEvent));
    onToggleMapOverlay?.();
  }, [topEvent, buildOverviewEvidence, focusEvidence, onToggleMapOverlay]);

  const openEngineerBriefing = useCallback(() => {
    if (topEvent) {
      focusEvidence(buildOverviewEvidence(topEvent), "engineer");
      return;
    }
    focusEvidence({
      runId: overview.run_id,
      lapNumber: lap?.lap_number ?? null,
      lapScope: lap ? "single_lap" : "run",
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
      channelId: null,
      lockState: "none",
      valueBasis: lap ? "full_lap" : "run_level",
      selectionSource: "overview",
    }, "engineer");
  }, [buildOverviewEvidence, focusEvidence, lap, overview.run_id, topEvent]);

  const warningsByOrder = useMemo(() => orderedWarnings(overview.warnings), [overview.warnings]);
  const proxyEventCount = useMemo(
    () => overview.events.filter((event) => Object.keys(event.evidence_json ?? {}).some((key) => isProxyChannel(key))).length,
    [overview.events],
  );

  const eligibleTimedLaps = useMemo(
    () => overview.laps.filter((candidate) => bestUsefulLapMatchesRun(candidate, overview.run_id)),
    [overview.laps, overview.run_id],
  );
  const usefulCount = eligibleTimedLaps.length;
  const excludedCount = overview.laps.length - usefulCount;
  const usefulTimedLapTimes = useMemo(
    () => eligibleTimedLaps
      .map((candidate) => candidate.lap_time as number)
      .sort((left, right) => left - right),
    [eligibleTimedLaps],
  );
  const longestCleanBlock = useMemo(
    () => longestContinuousEligibleLapBlock(eligibleTimedLaps),
    [eligibleTimedLaps],
  );
  const longRunLapsNeeded = Math.max(0, LONG_RUN_REVIEW_MIN_LAPS - longestCleanBlock);
  const medianUsefulLapTime = usefulTimedLapTimes.length > 0
    ? usefulTimedLapTimes.length % 2 === 1
      ? usefulTimedLapTimes[Math.floor(usefulTimedLapTimes.length / 2)]
      : (
        usefulTimedLapTimes[usefulTimedLapTimes.length / 2 - 1]
        + usefulTimedLapTimes[usefulTimedLapTimes.length / 2]
      ) / 2
    : null;
  const bestToMedianDelta = lap?.lap_time != null && medianUsefulLapTime != null
    ? medianUsefulLapTime - lap.lap_time
    : null;
  const actionableSeverity = topEvent ? severityLabel(topEvent.severity) : "NONE";
  const observedSeverity = topObservedEvent ? severityLabel(topObservedEvent.severity) : "NONE";
  const timedLapCount = overview.laps.filter((l) => l.lap_type === "timed" || l.lap_type === "flying" || l.lap_type === "complete").length;
  const setupAvailable = setupSnapshotMatchesRun(overview.setup_snapshot, overview.run_id);
  const setupTechReady = overview.session.setup_passed_tech !== false;
  const archiveVerified = Boolean(
    telemetryCapabilities
    && telemetryCapabilities.cache_compatibility.status === "current"
    && telemetryCapabilities.capability_summary.lossless_archive_complete
    && telemetryCapabilities.capability_summary.warning_channels === 0,
  );
  const blockingOverviewWarnings = overview.warnings.filter(overviewWarningBlocksDecision);
  const dataTrustReady = archiveVerified && blockingOverviewWarnings.length === 0;
  const decisionContextReady = Boolean(lap && setupAvailable && setupTechReady && dataTrustReady);
  const trustBlocker = !telemetryCapabilities
    ? "Telemetry capability verification is unavailable for this run."
    : telemetryCapabilities.cache_compatibility.status !== "current"
      ? telemetryCapabilities.cache_compatibility.reason
      : !telemetryCapabilities.capability_summary.lossless_archive_complete
        ? "The universal telemetry archive is incomplete."
        : telemetryCapabilities.capability_summary.warning_channels > 0
          ? `${telemetryCapabilities.capability_summary.warning_channels} telemetry channels have health warnings.`
          : blockingOverviewWarnings[0] ?? null;
  const decisionState = !decisionContextReady
    ? "NO CALL"
    : topEvent
      ? "INVESTIGATE"
      : "HOLD";
  const priorityPhase = topEvent ? explicitOvalPhase(topEvent) : null;
  const priorityLocation = topEvent ? eventLocationLabel(topEvent) : null;
  const cornerPriorityLabel = topEvent
    ? `${priorityPhase ? `${priorityPhase} · ` : ""}${priorityLocation} · ${humanizeEventLabel(topEvent.event_type)}`
    : "No tuning-valid corner call";
  const longRunReadinessLabel = longRunLapsNeeded === 0
    ? `${longestCleanBlock}-lap clean block · inspect in Laps`
    : `${longestCleanBlock}/${LONG_RUN_REVIEW_MIN_LAPS} clean · need ${longRunLapsNeeded} more`;
  const decisionHeadline = !lap
    ? "Bank one clean lap before tuning."
    : !setupAvailable
      ? "Clean lap found; garage context is missing."
      : !setupTechReady
        ? "Reset to a tech-passing baseline."
      : !dataTrustReady
        ? "Data warning: hold the setup call."
        : topEvent
          ? `${humanizeEventLabel(topEvent.event_type)} needs inspection.`
          : "No setup issue earned a call.";
  const decisionDetail = !lap
    ? "Complete a clean timed lap before making a setup decision."
    : !setupAvailable
      ? "Capture the setup before the next run so every change can be attributed."
      : !setupTechReady
        ? "Return to a tech-passing baseline before drawing a setup conclusion."
      : !dataTrustReady
        ? trustBlocker ?? "Resolve the run warnings before using this run for a setup decision."
      : topEvent
          ? `${priorityPhase ? `${priorityPhase} | ` : ""}${priorityLocation}${topEvent.lap_number != null ? ` | Lap ${topEvent.lap_number}` : ""}`
          : "Hold the current setup or begin one small, controlled test.";
  const decisionNext = !lap
    ? "Bank one complete, clean timed lap. Out laps, pit laps, cooldowns, wrecks, and partial laps will stay out of the call."
    : !setupAvailable
      ? "Capture the exact setup snapshot on the next run, then repeat the same clean-lap process."
      : !setupTechReady
        ? "Return to a tech-passing baseline before collecting comparison evidence."
        : !dataTrustReady
          ? "Recover the blocked telemetry evidence, then let the run be re-qualified."
          : topEvent
            ? "Inspect the exact event location, ask Engineer to separate competing causes, then validate at most one setup change in Dial-In."
            : longRunLapsNeeded > 0
              ? `Hold the setup. If long-run pace matters, extend this same-setup clean block by ${longRunLapsNeeded} lap${longRunLapsNeeded === 1 ? "" : "s"} before reviewing falloff.`
              : "Hold the setup. Review the continuous clean block in Laps; only stage a test when qualified evidence supports one change."
  const decisionPaceComparison = lap?.lap_time != null
    ? bestToMedianDelta != null && usefulTimedLapTimes.length >= 2
      ? bestToMedianDelta >= 0
        ? `${lap.lap_time.toFixed(3)}s | ${bestToMedianDelta.toFixed(3)}s quicker than clean-lap median`
        : `${lap.lap_time.toFixed(3)}s | ${Math.abs(bestToMedianDelta).toFixed(3)}s slower than clean-lap median`
      : `${lap.lap_time.toFixed(3)}s | single clean reference`
    : "No clean reference";
  const decisionSignal = topEvent
    ? `${severityLabel(topEvent.severity)} | ${(topEvent.confidence_score * 100).toFixed(0)}% confidence`
    : decisionContextReady
      ? "No tuning-valid event"
      : "Withheld";
  const visibleRunLabel = isLearning ? `Run ${overview.run_id}` : "Current run";
  const decisionScope = topEvent
    ? `${visibleRunLabel} | ${topEvent.lap_number != null ? `Lap ${topEvent.lap_number}` : "run-level evidence"}${(topEvent.lap_pct_peak ?? topEvent.lap_pct_start) != null ? ` | ${(topEvent.lap_pct_peak ?? topEvent.lap_pct_start)?.toFixed(1)}% lap distance` : ""}`
    : lap
      ? `${visibleRunLabel} | Best eligible Lap ${lap.lap_number}`
      : `${visibleRunLabel} | No eligible lap`;
  const actionableRecommendations = decisionContextReady ? evidenceQualifiedRecommendations : [];
  const firstBlockedRecommendation = overview.recommendations.find((recommendation) => (
    !recommendationIsActionable(recommendation, overview.events)
  ));
  const recommendationNoCallReason = !decisionContextReady
    ? decisionDetail
    : firstBlockedRecommendation
      ? recommendationBlockedReason(firstBlockedRecommendation)
      : "No evidence-qualified recommendation was produced for this run.";
  const trustedPrimaryFindings = topEvent && dataTrustReady ? overview.primary_findings : [];
  const broadcastWarning = blockingOverviewWarnings[0] ?? overview.warnings[0] ?? null;

  const runRiskEvents = useMemo(
    () => overview.events.filter((event) => event.lap_pct_peak != null || event.lap_pct_start != null || event.distance_m_peak != null).slice(0, 24),
    [overview.events],
  );
  const decisionBroadcastState = decisionState === "NO CALL"
    ? "blocked"
    : decisionState === "INVESTIGATE"
      ? "attention"
      : "clear";
  const decisionBroadcast = (
    <section
      className="tab-decision-broadcast"
      data-state={decisionBroadcastState}
      data-run-id={overview.run_id}
      data-long-run-state={longRunLapsNeeded === 0 ? "review-ready" : "short-run"}
      data-oval-priority={topEvent ? priorityPhase?.toLowerCase() ?? "located" : "clear"}
      aria-label="Overview decision briefing"
      aria-live="polite"
    >
      <div>
        <span className="eyebrow">
          {decisionState === "HOLD" ? <CheckCircle2 size={12} /> : <AlertTriangle size={12} />}
          {decisionState}
        </span>
        <h2>{decisionHeadline}</h2>
        <p><strong>Why:</strong> {decisionDetail}</p>
        <p><strong>What next:</strong> {decisionNext}</p>
        <p title={`Exact run ${overview.run_id}`}>Exact scope: {decisionScope}</p>
        <div className="tab-decision-facts">
          <span>
            <strong>Scope</strong>{" "}
            {topEvent?.lap_number != null ? `L${topEvent.lap_number}` : lap ? `L${lap.lap_number}` : "run"}
          </span>
          <span><strong>Clean</strong> {usefulCount}/{overview.laps.length} laps</span>
          <span data-driver-signal="long-run"><strong>Long run</strong> {longRunReadinessLabel}</span>
          <span data-driver-signal="corner-priority"><strong>Corner / area</strong> {cornerPriorityLabel}</span>
          <span><strong>Pace</strong> {decisionPaceComparison}</span>
          <span><strong>Signal</strong> {decisionSignal}</span>
          <span><strong>Setup</strong> {!setupAvailable ? "missing" : setupTechReady ? "captured" : "tech failed"}</span>
          <span><strong>Archive</strong> {archiveVerified ? "verified" : "not verified"}</span>
        </div>
        {isLearning && (
          <div className="tab-decision-learning">
            <p>
              The pace comparison uses only complete, useful pace laps from this exact run. The median is descriptive context, not evidence that setup caused the gap.
            </p>
            <p>
              Long-run readiness uses the longest uninterrupted eligible block. Invalid, pit, cooldown, wreck, reset, and partial laps break the chain. Ten clean laps open inspection; they do not prove tire degradation or a setup cause.
            </p>
            <p>
              Driver debrief: describe what the car did on entry, center, and exit at {priorityLocation ?? "the area you felt most"}. That observation narrows the review but does not authorize a setup change.
            </p>
            {topObservedEvent && (
              <p>
                Strongest observed signal: {humanizeEventLabel(topObservedEvent.event_type)} | evidence state {topObservedEvent.evidence_state.replace(/_/g, " ")} | {topObservedEvent.source_channels.length} source channel{topObservedEvent.source_channels.length === 1 ? "" : "s"}.
              </p>
            )}
          </div>
        )}
      </div>
      <div className="tab-handoff-actions" aria-label="Overview handoffs">
        {topEvent && (
          <button type="button" onClick={openTopEvent}>
            <Layers size={13} /> Inspect evidence
          </button>
        )}
        {!topEvent && topObservedEvent && (
          <button type="button" onClick={openObservedEvent}>
            <Layers size={13} /> Inspect evidence limit
          </button>
        )}
        {topEvent && onToggleMapOverlay && (
          <button type="button" onClick={openTopEventMapOverlay}>
            <MapPin size={13} /> Show on map
          </button>
        )}
        <button type="button" onClick={openEngineerBriefing}>
          <BrainCircuit size={13} /> Engineer briefing
        </button>
        <button type="button" onClick={() => setWorkspace("laps", "overview")}>
          <Clock size={13} /> Review laps
        </button>
        {topEvent && decisionContextReady && (
          <button type="button" onClick={() => focusEvidence(buildOverviewEvidence(topEvent), "setup_impact")}>
            <Wrench size={13} /> Setup impact
          </button>
        )}
      </div>
    </section>
  );

  if (!isLearning) {
    return (
      <div className="race-decision-shell" style={{ alignContent: "start" }}>
        {decisionBroadcast}

        {broadcastWarning && (
          <section className="race-warning-line">
            <AlertTriangle size={14} />
            <span>{broadcastWarning}</span>
            {overview.warnings.length > 1 && <span className="muted">+{overview.warnings.length - 1} more in Learning Mode</span>}
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="tab-grid">
      {decisionBroadcast}
      <EngineeringAwarenessPanel runId={overview.run_id} sessionId={sessionId} surface="overview" />

      <section className="overview-hero">
        <div className="overview-hero-header">
          <h2>Observed Signal</h2>
          {topObservedEvent && (
            <span className="gain-badge" style={{ borderColor: SEVERITY_COLOURS[topObservedEvent.severity], color: SEVERITY_COLOURS[topObservedEvent.severity] }}>
              {severityLabel(topObservedEvent.severity)}
            </span>
          )}
        </div>
        {topObservedEvent ? (
          <button className="overview-hero-issue" onClick={openObservedEvent} style={{ textAlign: "left", background: "transparent", border: "1px solid var(--line)" }}>
            <p className="overview-hero-location">
              <MapPin size={14} /> {humanizeEventLabel(topObservedEvent.event_type)}
              {topObservedEvent.lap_number != null ? ` · Lap ${topObservedEvent.lap_number}` : ""}
              {topObservedEvent.zone_name ? ` · ${topObservedEvent.zone_name}` : ""}
              {(topObservedEvent.lap_pct_peak ?? topObservedEvent.lap_pct_start) != null ? ` · ${(topObservedEvent.lap_pct_peak ?? topObservedEvent.lap_pct_start)?.toFixed(1)}%` : ""}
            </p>
            <p className="overview-hero-why">{buildWhyText(topObservedEvent, isLearning)}</p>
            {!telemetryEventIsActionable(topObservedEvent) && (
              <p className="overview-hero-proxy-warning">
                Evidence only - this signal does not authorize a setup call.
                {topObservedEvent.blocker_reasons[0] ? ` ${topObservedEvent.blocker_reasons[0]}` : ""}
              </p>
            )}
          </button>
        ) : (
          <p className="muted">No evidence-qualified issue is available for a setup call.</p>
        )}
      </section>

      <section className="workspace-section overview-visual-summary">
        <h2>Run Health / Risk Summary</h2>
        <div className="overview-trust-summary">
          <span>Useful {usefulCount}</span>
          <span>Excluded {excludedCount}</span>
          <span>Events {overview.events.length}</span>
          <span>Observed severity {observedSeverity}</span>
          <span>Actionable severity {actionableSeverity}</span>
          <span>Decision {decisionState}</span>
        </div>
      </section>

      {telemetryCapabilities && (
        <section className="workspace-section" aria-label="Telemetry capability summary">
          <h2>Telemetry Capability</h2>
          <div className="overview-trust-summary">
            <span>Declared {telemetryCapabilities.capability_summary.declared_channels}</span>
            <span>Archived {telemetryCapabilities.capability_summary.cached_channels}</span>
            <span>Unmapped {telemetryCapabilities.capability_summary.unmapped_channels}</span>
            <span>Warnings {telemetryCapabilities.capability_summary.warning_channels}</span>
          </div>
          <p className="muted">
            {telemetryCapabilities.capability_summary.lossless_archive_complete
              ? "Every file-declared channel is preserved in the universal archive."
              : "This run does not satisfy the universal archive invariant."}
          </p>
          {telemetryCapabilities.cache_compatibility.status !== "current" && (
            <div className="race-warning-line">
              <AlertTriangle size={14} />
              <span>{telemetryCapabilities.cache_compatibility.reason}</span>
            </div>
          )}
        </section>
      )}

      <section className="metrics-row">
        <EngineeringMetricCard title="Best Useful Lap" value={lap ? `Lap ${lap.lap_number} · ${lap.lap_time?.toFixed(3)}s` : null} color="#22c55e" />
        <EngineeringMetricCard title="Lap Count / Clean Pace Laps" value={`${overview.laps.length} / ${usefulCount}`} subtitle={`Excluded: ${excludedCount}`} color="#38bdf8" />
        <EngineeringMetricCard
          title="Longest Clean Block"
          value={`${longestCleanBlock} lap${longestCleanBlock === 1 ? "" : "s"}`}
          subtitle={longRunLapsNeeded > 0 ? `${longRunLapsNeeded} more for long-run inspection` : "Long-run inspection gate met"}
          color={longRunLapsNeeded > 0 ? "#f59e0b" : "#22c55e"}
        />
        <EngineeringMetricCard
          title="Canonical Pace Laps"
          value={`${timedLapCount} timed/flying/complete`}
          subtitle={`${overview.laps.length - timedLapCount} other or legacy classifications`}
          color="#60a5fa"
        />
        <EngineeringMetricCard title="Observed Severity" value={observedSeverity} subtitle="Includes evidence-only events" color="#ef4444" />
        <EngineeringMetricCard title="Actionable Platform Signal" value={actionableSeverity} subtitle={topEvent?.event_type ? humanizeEventLabel(topEvent.event_type) : "No qualified event"} color="#f97316" />
        <EngineeringMetricCard title="Scrub / Resistance Risk" value={overview.events.filter((event) => /SCRUB|RESIST|DRAG/i.test(event.event_type)).length} color="#f59e0b" />
        <EngineeringMetricCard title="Tire Condition Summary" value={overview.events.filter((event) => /TIRE|TEMP|PRESSURE|CAMBER/i.test(event.event_type)).length} subtitle="tire-related events" color="#22d3ee" />
        <EngineeringMetricCard title="Setup Snapshot Status" value={setupAvailable ? "Available" : "Unavailable"} color={setupAvailable ? "#22c55e" : "#ef4444"} />
        <EngineeringMetricCard title="Data Quality Status" value={overview.warnings.length === 0 ? "Clean" : `${overview.warnings.length} warning(s)`} subtitle={proxyEventCount > 0 ? `${proxyEventCount} proxy/estimate event(s)` : undefined} color={overview.warnings.length === 0 ? "#22c55e" : "#f59e0b"} />
      </section>

      {warningsByOrder.some((group) => group.items.length > 0) && (
        <section className="workspace-section">
          <h2>Import / Data Quality Warnings</h2>
          {warningsByOrder.map((group) => (
            <div key={group.key} style={{ marginBottom: 8 }}>
              <button
                className="trackmap-action-btn"
                onClick={() => setOpenWarningKeys((prev) => ({ ...prev, [group.key]: !prev[group.key] }))}
                disabled={group.items.length === 0}
                style={{ opacity: group.items.length === 0 ? 0.5 : 1 }}
              >
                <AlertTriangle size={12} /> {group.label} ({group.items.length})
              </button>
              {openWarningKeys[group.key] && (
                <ul className="warnings-list">
                  {group.items.map((warning) => <li key={warning} className="muted">{warning}</li>)}
                </ul>
              )}
            </div>
          ))}
        </section>
      )}

      <section className="workspace-section overview-visual-summary">
        <h2>Event Summary / Timeline Preview</h2>
        <div className="overview-risk-strip">
          {runRiskEvents.length === 0 ? (
            <span className="risk-strip-empty">No located events available.</span>
          ) : runRiskEvents.map((event) => {
            const pos = event.lap_pct_peak ?? event.lap_pct_start ?? 0;
            return (
              <button
                key={event.event_id}
                className="overview-risk-marker"
                data-severity={event.severity}
                style={{ left: `${Math.max(0, Math.min(100, pos))}%` }}
                onClick={() => { focusEvidence(buildOverviewEvidence(event), "platform_trace"); }}
                title={`${humanizeEventLabel(event.event_type)} | ${event.severity}`}
                aria-label={`Open ${humanizeEventLabel(event.event_type)} in Platform`}
              />
            );
          })}
        </div>
      </section>

      <section className="workspace-section">
        <h2>Recommendations from Crew Chief</h2>
        {actionableRecommendations.length > 0 ? (
          <ol className="findings-list">
            {actionableRecommendations.map((rec) => (
              <li key={rec.recommendation_id}>
                <strong>P{rec.priority_rank}:</strong> {rec.recommendation_text}
              </li>
            ))}
          </ol>
        ) : (
          <div className="inspector-crew-block">
            <span className="eyebrow">No call</span>
            <p>No recommendation is shown without supporting evidence.</p>
            <p className="muted">{recommendationNoCallReason}</p>
          </div>
        )}
      </section>

      <section className="workspace-section">
        <h2>Recent Findings</h2>
        <div className="toolbar-actions">
          <button className="secondary-button" onClick={() => setWorkspace("laps", "overview")}>
            <Clock size={14} /> Review in Laps
          </button>
        </div>
        <ol className="findings-list">
          {trustedPrimaryFindings.length > 0
            ? trustedPrimaryFindings.map((finding) => <li key={finding}>{finding}</li>)
            : <li className="muted">No findings yet.</li>}
        </ol>
      </section>

      {sortedEvents.length > 0 && (
        <section className="evidence-list">
          {sortedEvents.slice(0, 6).map((event) => (
            <EvidenceCard event={event} key={event.event_id} onToggleMapOverlay={onToggleMapOverlay} />
          ))}
        </section>
      )}
    </div>
  );
}
