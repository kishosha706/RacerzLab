"""Inspectable deterministic rendering for frozen evaluation artifacts."""

from __future__ import annotations

from racelab_engine.evaluation.metric_evaluation import EvaluationArtifact


def render_evaluation_report(artifact: EvaluationArtifact) -> str:
    lines = [
        f"# {artifact.plan_id}",
        "",
        f"Evaluation: `{artifact.evaluation_id}`",
        f"Dataset: `{artifact.dataset_id}`",
        f"Mode: {artifact.evaluation_mode}",
        f"Independent units: {artifact.independent_unit_count}",
        f"State: {artifact.state.upper()}",
        "Authority: EVALUATION ONLY",
        "",
        "## Metrics",
        "",
    ]
    lines.extend(
        f"- {key}: {'unavailable' if value is None else value}"
        for key, value in sorted(artifact.metrics.items())
    )
    lines.extend(["", "## Subgroups", ""])
    for subgroup in artifact.subgroups:
        state = "pass" if subgroup.passed else "fail"
        lines.append(
            f"- {subgroup.subgroup_key}: {state}; "
            f"N={subgroup.independent_unit_count}; metrics={subgroup.metrics}"
        )
        lines.extend(f"  - blocker: {blocker}" for blocker in subgroup.blockers)
    lines.extend(["", "## Negative controls", ""])
    for control in artifact.negative_controls:
        state = "pass" if control.passed else "fail"
        lines.append(f"- {control.control_id}: {state}; observed={control.observed_value}")
        if control.blocker:
            lines.append(f"  - blocker: {control.blocker}")
    if artifact.blockers:
        lines.extend(["", "## Activation blockers", ""])
        lines.extend(f"- {blocker}" for blocker in artifact.blockers)
    return "\n".join(lines) + "\n"


__all__ = ["render_evaluation_report"]
