import { Crosshair, RefreshCw } from "lucide-react";
import { useRef } from "react";

import { useEngineeringCase } from "../store/EngineeringCaseContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { EvidenceContext, Workspace } from "../store/types";

function pctRangeLabel(start: number | null | undefined, end: number | null | undefined): string | null {
  if (start == null && end == null) return null;
  if (start != null && end != null) {
    return Math.abs(start - end) < 0.001
      ? `${start.toFixed(1)}%`
      : `${start.toFixed(1)}–${end.toFixed(1)}%`;
  }
  return `${(start ?? end)?.toFixed(1)}%`;
}

function evidenceScopeLabel(
  laps: readonly number[],
  pctStart: number | null | undefined,
  pctEnd: number | null | undefined,
): string {
  const uniqueLaps = [...new Set(laps)].sort((left, right) => left - right);
  const lapLabel = uniqueLaps.length === 0
    ? "Run scope"
    : uniqueLaps.length === 1
      ? `Lap ${uniqueLaps[0]}`
      : `Laps ${uniqueLaps.join(", ")}`;
  const pctLabel = pctRangeLabel(pctStart, pctEnd);
  return pctLabel ? `${lapLabel} · ${pctLabel}` : lapLabel;
}

function sameOptionalNumber(
  left: number | null | undefined,
  right: number | null | undefined,
): boolean {
  if (left == null || right == null) return left == null && right == null;
  return Math.abs(left - right) < 0.001;
}

export function EngineeringMissionStrip() {
  const { engineeringCase, revision, status, error, retry } = useEngineeringCase();
  const { selection, focusEvidence } = useTelemetrySelection();
  const priorFocusRef = useRef<{
    caseSha256: string;
    evidence: Partial<EvidenceContext>;
    workspace: Workspace;
  } | null>(null);

  if (status === "loading" || status === "stale") {
    return <aside className="engineering-mission-strip loading" role="status" aria-live="polite">Binding one current Engineering Case…</aside>;
  }
  if (status === "error" || !engineeringCase || !revision) {
    return (
      <aside className="engineering-mission-strip error" role="alert">
        <div><strong>Current Engineering Case unavailable</strong><span>{error ?? "No exact case revision was returned."}</span></div>
        <button type="button" onClick={retry}><RefreshCw size={14} /> Retry</button>
      </aside>
    );
  }

  const mission = engineeringCase.mission;
  const focus = engineeringCase.semantic_focus;
  const isLearning = selection.selectedMode === "learning";
  const decisionLaps = [...new Set(focus.lap_numbers)].sort((left, right) => left - right);
  const decisionLap = decisionLaps[0] ?? null;
  const decisionWindowStart = decisionLaps.length > 1 ? decisionLaps[0] : null;
  const decisionWindowEnd = decisionLaps.length > 1 ? decisionLaps[decisionLaps.length - 1] : null;
  const hasDecisionZone = focus.lap_pct_start != null || focus.lap_pct_end != null;
  const decisionLapScope = decisionLaps.length > 1
    ? "lap_window"
    : hasDecisionZone
      ? "track_zone"
      : decisionLap == null
        ? "run"
        : "single_lap";
  const supporting = focus.artifact_id == null
    ? null
    : engineeringCase.response_artifacts.find((artifact) => (
      artifact.artifact_id === focus.artifact_id
      && artifact.case_id === engineeringCase.case_id
      && artifact.case_revision_sha256 === engineeringCase.case_revision_sha256
      && artifact.run_id === engineeringCase.run_id
      && artifact.session_id === engineeringCase.session_id
      && artifact.setup_id === engineeringCase.setup_id
    )) ?? null;
  const decisionScopeIsValid = decisionLaps.every((lap) => Number.isInteger(lap) && lap >= 0)
    && decisionLaps.length === focus.lap_numbers.length
    && (focus.lap_pct_start == null) === (focus.lap_pct_end == null)
    && (focus.lap_pct_start == null || (
      Number.isFinite(focus.lap_pct_start)
      && Number.isFinite(focus.lap_pct_end)
      && focus.lap_pct_start >= 0
      && focus.lap_pct_end! <= 100
      && focus.lap_pct_start <= focus.lap_pct_end!
    ));
  const canFocusDecision = focus.case_id === engineeringCase.case_id
    && focus.case_revision_sha256 === engineeringCase.case_revision_sha256
    && decisionScopeIsValid
    && (focus.artifact_id == null || supporting != null);
  const sameScope = canFocusDecision
    && selection.selectedRunId === engineeringCase.run_id
    && (selection.selectedLap ?? null) === decisionLap
    && (selection.selectedLapScope ?? "unknown") === decisionLapScope
    && (selection.selectedLapWindowStart ?? null) === decisionWindowStart
    && (selection.selectedLapWindowEnd ?? null) === decisionWindowEnd
    && (selection.selectedRepresentativeLap ?? null) === (decisionLaps.length > 1 ? decisionLap : null)
    && sameOptionalNumber(selection.selectedLapPct, focus.lap_pct_start)
    && sameOptionalNumber(selection.selectedZoneStartPct, focus.lap_pct_start)
    && sameOptionalNumber(selection.selectedZoneEndPct, focus.lap_pct_end)
    && (selection.selectedCaseId ?? null) === engineeringCase.case_id
    && (selection.selectedCaseRevision ?? null) === engineeringCase.case_revision_sha256
    && (selection.selectedCaseSha256 ?? null) === engineeringCase.case_sha256
    && (selection.selectedArtifactId ?? null) === focus.artifact_id;

  const focusDecision = () => {
    if (!canFocusDecision) return;
    priorFocusRef.current = {
      caseSha256: engineeringCase.case_sha256,
      workspace: selection.selectedWorkspace,
      evidence: {
        runId: selection.selectedRunId,
        lapNumber: selection.selectedLap ?? null,
        lapScope: selection.selectedLapScope ?? "unknown",
        lapWindowStart: selection.selectedLapWindowStart ?? null,
        lapWindowEnd: selection.selectedLapWindowEnd ?? null,
        representativeLap: selection.selectedRepresentativeLap ?? null,
        eventId: selection.selectedEventId ?? null,
        producerId: selection.selectedProducerId ?? null,
        artifactId: selection.selectedArtifactId ?? null,
        caseId: selection.selectedCaseId ?? null,
        caseRevision: selection.selectedCaseRevision ?? null,
        caseSha256: selection.selectedCaseSha256 ?? null,
        mechanismIds: selection.selectedMechanismIds ?? [],
        responseRelationId: selection.selectedResponseRelationId ?? null,
        componentIds: selection.selectedComponentIds ?? [],
        effectIds: selection.selectedEffectIds ?? [],
        controlKeys: selection.selectedControlKeys ?? [],
        p19CauseIds: selection.selectedP19CauseIds ?? [],
        quantityIds: selection.selectedQuantityIds ?? [],
        discriminatorId: selection.selectedDiscriminatorId ?? null,
        workflowId: selection.selectedWorkflowId ?? null,
        workflowRevision: selection.selectedWorkflowRevision ?? null,
        sampleIndex: selection.selectedSampleIndex ?? null,
        lapDistFt: selection.selectedLapDistFt ?? null,
        lapPct: selection.selectedLapPct ?? null,
        zoneId: selection.selectedZoneId ?? null,
        zoneLabel: selection.selectedZoneLabel ?? null,
        zoneStartPct: selection.selectedZoneStartPct ?? null,
        zoneEndPct: selection.selectedZoneEndPct ?? null,
        channelId: selection.selectedChannel ?? null,
        system: selection.selectedSystem ?? null,
        selectionSource: selection.selectionSource,
        lockState: selection.selectedLockState ?? "none",
        trustTier: selection.selectedTrustTier ?? null,
        compareRole: selection.selectedCompareRole ?? null,
        sourceRunId: selection.selectedSourceRunId ?? null,
        sourceSetupId: selection.selectedSourceSetupId ?? null,
        valueBasis: selection.selectedValueBasis ?? "unavailable",
      },
    };
    focusEvidence({
      runId: engineeringCase.run_id,
      lapNumber: decisionLap,
      lapScope: decisionLapScope,
      lapWindowStart: decisionWindowStart,
      lapWindowEnd: decisionWindowEnd,
      representativeLap: decisionLaps.length > 1 ? decisionLap : null,
      eventId: null,
      producerId: supporting?.source_producer_id ?? null,
      artifactId: supporting?.artifact_id ?? null,
      caseId: engineeringCase.case_id,
      caseRevision: engineeringCase.case_revision_sha256,
      caseSha256: engineeringCase.case_sha256,
      mechanismIds: focus.mechanism_ids,
      responseRelationId: focus.response_relation_id,
      componentIds: focus.component_ids,
      effectIds: focus.effect_ids,
      controlKeys: focus.control_keys,
      p19CauseIds: focus.p19_cause_ids,
      quantityIds: engineeringCase.quantity_observability.map((item) => item.quantity_id),
      discriminatorId: engineeringCase.active_discriminator_id,
      sampleIndex: null,
      lapDistFt: null,
      lapPct: focus.lap_pct_start,
      zoneId: null,
      zoneLabel: focus.phase,
      zoneStartPct: focus.lap_pct_start,
      zoneEndPct: focus.lap_pct_end,
      channelId: null,
      system: null,
      selectionSource: "engineer",
      lockState: hasDecisionZone ? "locked" : "none",
      trustTier: mission.source_authority,
      compareRole: null,
      sourceRunId: engineeringCase.run_id,
      sourceSetupId: engineeringCase.setup_id,
      valueBasis: decisionLaps.length > 1
        ? "selected_window"
        : hasDecisionZone
          ? "selected_window"
          : decisionLap == null
            ? "run_level"
            : "full_lap",
    }, "engineer");
  };
  const priorFocus = priorFocusRef.current?.caseSha256 === engineeringCase.case_sha256
    ? priorFocusRef.current
    : null;
  const restorePriorFocus = () => {
    if (priorFocus == null) return;
    priorFocusRef.current = null;
    focusEvidence(priorFocus.evidence, priorFocus.workspace);
  };

  return (
    <aside
      className="engineering-mission-strip"
      data-mode={isLearning ? "learning" : "race"}
      data-authority={mission.source_authority}
      data-case-sha256={engineeringCase.case_sha256}
      aria-label="Current Engineering Case mission"
    >
      <header>
        <span>Current Engineering Case</span>
        <strong>Revision {revision.case_revision} · {engineeringCase.case_sha256.slice(0, 12)}</strong>
      </header>
      <div className="engineering-mission-fields">
        {isLearning && <article><span>What</span><strong>{mission.what}</strong></article>}
        <article><span>Where</span><strong>{mission.where}</strong></article>
        {isLearning && <article><span>Why</span><strong>{mission.why_it_matters}</strong></article>}
        {isLearning && <article><span>Uncertain</span><strong>{mission.uncertain}</strong></article>}
        <article className="mission-next"><span>Next</span><strong>{mission.next}</strong></article>
        <article><span>Done when</span><strong>{mission.done_when}</strong></article>
      </div>
      <div className="engineering-scope-stack" aria-label="Engineering Case scope stack">
        <span><small>Viewing</small>{evidenceScopeLabel(
          selection.selectedLapScope === "lap_window"
            ? [selection.selectedLapWindowStart, selection.selectedLapWindowEnd]
              .filter((lap): lap is number => lap != null)
            : selection.selectedLap == null ? [] : [selection.selectedLap],
          selection.selectedZoneStartPct ?? selection.selectedLapPct,
          selection.selectedZoneEndPct ?? selection.selectedLapPct,
        )}</span>
        <span><small>Active decision</small>{evidenceScopeLabel(decisionLaps, focus.lap_pct_start, focus.lap_pct_end)}</span>
        <span><small>Supporting evidence</small>{supporting
          ? evidenceScopeLabel(supporting.source_lap_numbers, supporting.lap_pct_start, supporting.lap_pct_end)
          : "No exact response artifact"}</span>
        {!sameScope && (
          <button
            type="button"
            onClick={focusDecision}
            disabled={!canFocusDecision}
            title={canFocusDecision ? "Focus the exact current decision scope" : "Exact decision identity or response artifact is unavailable"}
          ><Crosshair size={14} /> Focus decision scope</button>
        )}
        {sameScope && priorFocus != null && (
          <button
            type="button"
            onClick={restorePriorFocus}
            title="Return to the evidence scope you were viewing"
          ><Crosshair size={14} /> Return to previous focus</button>
        )}
      </div>
    </aside>
  );
}
