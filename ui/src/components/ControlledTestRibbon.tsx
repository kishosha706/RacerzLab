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
  if (stage === "A") return "Prove the current car before changing it";
  if (stage === "B") return "Run only the frozen one-change target";
  return "Return to baseline and prove the response repeats";
}

function nextWorkflowAction(
  workflow: ControlledWorkflow,
  authority: CurrentIntelligenceAuthority | null,
  authorityStatus: CurrentIntelligenceAuthorityStatus,
  authorityRecovery: string,
): { label: string; detail: string } {
  if (!workflow.stage_run_ids.A) {
    return {
      label: "Record baseline A",
      detail: "Complete the baseline procedure before changing the car.",
    };
  }
  if (!workflow.stage_run_ids.B) {
    if (!authority) {
      return {
        label: authorityStatus === "checking" ? "Rechecking Stage B" : "Review Stage B authority",
        detail: authorityStatus === "checking"
          ? "Rechecking the exact source-run report and workflow revision. The stored target stays hidden."
          : authorityRecovery,
      };
    }
    return {
      label: "Record changed run B",
      detail: authority.instruction,
    };
  }
  if (!workflow.stage_run_ids.A2) {
    return {
      label: "Restore and record A2",
      detail: "Return to the baseline setup, then repeat the measured laps.",
    };
  }
  return {
    label: "Score the controlled test",
    detail: "Verify the effect, countereffects, and rollback rule in Dial-In.",
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
  const nextAction = nextWorkflowAction(
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
        <small>Now: {nextAction.label}</small>
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
              <span>{stageLabel(stage)}<small>{complete ? "Verified" : current ? "Now" : "Next"}</small></span>
            </li>
          );
        })}
      </ol>

      <button type="button" className="shell-controlled-test-action" aria-label={`${nextAction.label}. Open controlled workflow.`} onClick={() => onOpen(workflow.workflow_id)}>
        <span>
          <strong>{nextAction.label}</strong>
          <small>{nextAction.detail}</small>
        </span>
        <ArrowRight size={16} aria-hidden="true" />
      </button>
    </section>
  );
}
