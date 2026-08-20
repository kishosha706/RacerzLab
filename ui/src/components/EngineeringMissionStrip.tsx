import { Crosshair, RefreshCw } from "lucide-react";

import { useEngineeringCase } from "../store/EngineeringCaseContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";

function positionLabel(lap: number | null | undefined, pct: number | null | undefined): string {
  if (lap == null) return "Run scope";
  return `Lap ${lap}${pct != null ? ` · ${pct.toFixed(1)}%` : ""}`;
}

export function EngineeringMissionStrip() {
  const { engineeringCase, revision, status, error, retry } = useEngineeringCase();
  const { selection, focusEvidence } = useTelemetrySelection();

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
  const decisionLap = focus.lap_numbers[0] ?? null;
  const supporting = engineeringCase.response_artifacts[0] ?? null;
  const sameScope = decisionLap === (selection.selectedLap ?? null)
    && (focus.lap_pct_start == null || Math.abs((selection.selectedLapPct ?? -1) - focus.lap_pct_start) < 0.1);

  const focusDecision = () => {
    focusEvidence({
      runId: engineeringCase.run_id,
      lapNumber: decisionLap,
      lapScope: decisionLap == null ? "run" : "single_lap",
      eventId: null,
      producerId: supporting?.source_producer_id ?? null,
      artifactId: focus.artifact_id,
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
      lockState: focus.lap_pct_start == null ? "none" : "locked",
      trustTier: mission.source_authority,
      compareRole: null,
      sourceRunId: engineeringCase.run_id,
      sourceSetupId: engineeringCase.setup_id,
      valueBasis: decisionLap == null ? "run_level" : "full_lap",
    }, "engineer");
  };

  return (
    <aside
      className="engineering-mission-strip"
      data-authority={mission.source_authority}
      data-case-sha256={engineeringCase.case_sha256}
      aria-label="Current Engineering Case mission"
    >
      <header>
        <span>Current Engineering Case</span>
        <strong>Revision {revision.case_revision} · {engineeringCase.case_sha256.slice(0, 12)}</strong>
      </header>
      <div className="engineering-mission-fields">
        <article><span>What</span><strong>{mission.what}</strong></article>
        <article><span>Where</span><strong>{mission.where}</strong></article>
        <article><span>Why</span><strong>{mission.why_it_matters}</strong></article>
        <article><span>Uncertain</span><strong>{mission.uncertain}</strong></article>
        <article className="mission-next"><span>Next</span><strong>{mission.next}</strong></article>
        <article><span>Done when</span><strong>{mission.done_when}</strong></article>
      </div>
      <div className="engineering-scope-stack" aria-label="Engineering Case scope stack">
        <span><small>Viewing</small>{positionLabel(selection.selectedLap, selection.selectedLapPct)}</span>
        <span><small>Active decision</small>{positionLabel(decisionLap, focus.lap_pct_start)}</span>
        <span><small>Supporting evidence</small>{supporting ? positionLabel(supporting.source_lap_numbers[0], supporting.lap_pct_start) : "No response artifact"}</span>
        {!sameScope && <button type="button" onClick={focusDecision}><Crosshair size={14} /> Focus decision scope</button>}
      </div>
    </aside>
  );
}
