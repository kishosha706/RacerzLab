import { ArrowRight, Check } from "lucide-react";
import type { ControlledWorkflow } from "../types/telemetry";
import {
  currentIntelligenceAuthorityMatchesWorkflow,
  type CurrentIntelligenceAuthority,
  type CurrentIntelligenceAuthorityStatus,
} from "../utils/currentIntelligenceAuthority";

type ControlledTestRibbonProps = {
  workflow: ControlledWorkflow;
  currentIntelligenceAuthority: CurrentIntelligenceAuthority | null;
  intelligenceAuthorityStatus: CurrentIntelligenceAuthorityStatus;
  intelligenceAuthorityRecovery: string;
  onOpen: (workflowId: string) => void;
};

const STAGES = ["A", "B", "A2"] as const;

function stageLabel(stage: (typeof STAGES)[number]): string {
  if (stage === "A") return "Baseline";
  if (stage === "B") return "One change";
  return "Restore";
}

function stagePurpose(stage: (typeof STAGES)[number]): string {
  if (stage === "A") return "Baseline evidence for the current car";
  if (stage === "B") return "Evidence for the frozen one-change target";
  return "Restored-baseline evidence for repeatability";
}

function workflowEvidenceStatus(
  workflow: ControlledWorkflow,
  authority: CurrentIntelligenceAuthority | null,
  authorityStatus: CurrentIntelligenceAuthorityStatus,
  authorityRecovery: string,
): { label: string; detail: string } {
  if (!workflow.stage_run_ids.A) {
    return {
      label: "Baseline A pending",
      detail: "No baseline run is attached to this workflow yet.",
    };
  }
  if (!workflow.stage_run_ids.B) {
    if (!authority) {
      return {
        label: authorityStatus === "checking" ? "Stage B authority checking" : "Stage B authority unavailable",
        detail: authorityStatus === "checking"
          ? "The exact source-run report and workflow revision are being checked; the stored target stays hidden."
          : `No exact source-run authority card is available for this workflow revision.${authorityRecovery ? ` ${authorityRecovery}` : ""}`,
      };
    }
    return {
      label: "Changed run B pending",
      detail: "An exact source-run authority card is bound to this workflow revision.",
    };
  }
  if (!workflow.stage_run_ids.A2) {
    return {
      label: "Restore run A2 pending",
      detail: "Baseline A and changed run B are attached; restored-baseline evidence is not.",
    };
  }
  return {
    label: "Scoring pending",
    detail: "All three stage runs are attached; no controlled-test verdict is recorded yet.",
  };
}

export function ControlledTestRibbon({
  workflow,
  currentIntelligenceAuthority,
  intelligenceAuthorityStatus,
  intelligenceAuthorityRecovery,
  onOpen,
}: ControlledTestRibbonProps) {
  if (
    workflow.packet.decision !== "test"
    || workflow.status === "scored"
    || workflow.status === "cancelled"
    || (workflow.stage_run_ids.B != null && workflow.stage_run_ids.A == null)
    || (workflow.stage_run_ids.A2 != null && workflow.stage_run_ids.B == null)
  ) {
    return null;
  }

  const nextStage = STAGES.find((stage) => workflow.stage_run_ids[stage] == null) ?? null;
  const exactSourceRunAuthority = currentIntelligenceAuthorityMatchesWorkflow(
    currentIntelligenceAuthority,
    workflow,
  ) ? currentIntelligenceAuthority : null;
  const evidenceStatus = workflowEvidenceStatus(
    workflow,
    exactSourceRunAuthority,
    intelligenceAuthorityStatus,
    intelligenceAuthorityRecovery,
  );
  const completedStages = STAGES.filter((stage) => workflow.stage_run_ids[stage] != null).length;

  return (
    <section
      className="shell-controlled-test-ribbon"
      data-current-stage={nextStage ?? "score"}
      data-completed-stages={completedStages}
      data-authority={nextStage === "B" && exactSourceRunAuthority ? "source-run-card" : "non-authorizing-progress"}
      data-source-run-id={exactSourceRunAuthority?.sourceRunId}
      aria-label={`Controlled test progress: ${completedStages} of 3 stages verified`}
    >
      <div className="shell-controlled-test-summary">
        <span>Controlled test · {completedStages}/3 verified</span>
        <strong title={workflow.complaint}>{workflow.complaint || "One-change A/B/A2 test"}</strong>
        <small>Status: {evidenceStatus.label}</small>
      </div>

      <ol className="shell-controlled-test-stages" aria-label="A B A2 test stages">
        {STAGES.map((stage) => {
          const complete = workflow.stage_run_ids[stage] != null;
          const current = stage === nextStage;
          return (
            <li
              key={stage}
              className={`${complete ? "complete" : ""}${current ? " current" : ""}`}
              data-state={complete ? "complete" : current ? "current" : "upcoming"}
              aria-current={current ? "step" : undefined}
              title={stagePurpose(stage)}
            >
              <span className="shell-controlled-test-stage-mark" aria-hidden="true">
                {complete ? <Check size={12} /> : stage}
              </span>
              <span>{stageLabel(stage)}<small>{complete ? "Verified" : current ? "Current" : "Pending"}</small></span>
            </li>
          );
        })}
      </ol>

      <button type="button" className="shell-controlled-test-action" aria-label="Review controlled-test evidence" onClick={() => onOpen(workflow.workflow_id)}>
        <span>
          <strong>Review workflow evidence</strong>
          <small>{evidenceStatus.detail}</small>
        </span>
        <ArrowRight size={16} aria-hidden="true" />
      </button>
    </section>
  );
}
