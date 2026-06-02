import type { NotebookFinding } from "../types/compare";

type FindingSectorSummary = {
  label?: string;
  sector_name?: string;
  avg_speed_delta_mph?: number | null;
  min_cfs_delta_in?: number | null;
};

type FindingSetupChange = {
  label?: string;
  delta?: string | null;
};

function formatVal(v: number | null | undefined, digits = 2): string {
  return v != null && !Number.isNaN(v) ? v.toFixed(digits) : "-";
}

export function findingToMarkdown(f: NotebookFinding): string {
  const lines: string[] = [];
  lines.push(`# ${f.summary_headline ?? "RacerZLab Finding"}`);
  lines.push("");
  lines.push(`**Car:** ${f.car_name ?? "-"}  **Track:** ${f.track_name ?? "-"}  **Setup:** ${f.setup_name ?? "-"}`);
  lines.push(`**Verdict:** ${f.verdict?.replace(/_/g, " ") ?? "-"}  **Confidence:** ${formatVal(f.confidence_score * 100, 0)}%  **Tier:** ${f.confidence_tier ?? "-"}`);
  lines.push(`**Target Zone:** ${f.target_zone_start_pct}-${f.target_zone_end_pct}%`);
  if (f.target_zone_classification) lines.push(`**Classification:** ${f.target_zone_classification}`);
  lines.push("");
  if (f.key_takeaways.length > 0) {
    lines.push("## Key Takeaways");
    f.key_takeaways.forEach((t) => lines.push(`- ${t}`));
    lines.push("");
  }
  if (f.evidence.length > 0) {
    lines.push("## Evidence");
    f.evidence.forEach((e) => lines.push(`- ${e}`));
    lines.push("");
  }
  if (f.sector_summaries.length > 0) {
    lines.push("## Sector Deltas");
    lines.push("| Sector | Speed Delta | CFS Delta |");
    lines.push("|--------|-------------|-----------|");
    f.sector_summaries.forEach((s) => {
      const row = s as FindingSectorSummary;
      lines.push(`| ${row.label ?? row.sector_name ?? "-"} | ${formatVal(row.avg_speed_delta_mph, 3)} | ${formatVal(row.min_cfs_delta_in, 3)} |`);
    });
    lines.push("");
  }
  if (f.setup_changes.length > 0) {
    lines.push("## Setup Changes");
    f.setup_changes.forEach((s) => {
      const row = s as FindingSetupChange;
      lines.push(`- ${row.label ?? "Setting"}: ${row.delta ?? "-"}`);
    });
    lines.push("");
  }
  if (f.warnings.length > 0) {
    lines.push("## Warnings");
    f.warnings.forEach((w) => lines.push(`- Warning: ${w}`));
    lines.push("");
  }
  if (f.next_step) lines.push(`**Next Step:** ${f.next_step}`);
  if (f.notes) lines.push(`\n## Notes\n${f.notes}`);
  return lines.join("\n");
}
