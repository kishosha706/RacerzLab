/** Shared verdict styling and labels — single source of truth across DidItWorkCard and NotebookTab. */

export const VERDICT_COLORS: Record<string, string> = {
  keep_direction: "#22c55e",
  undo_partially: "#f97316",
  undo: "#ef4444",
  retest: "#f59e0b",
  inconclusive: "#8d9aaa",
  reference_mode: "#38bdf8",
};

export const VERDICT_LABELS: Record<string, string> = {
  keep_direction: "Keep Direction",
  undo_partially: "Undo Partially",
  undo: "Undo",
  retest: "Retest",
  inconclusive: "Inconclusive",
  reference_mode: "Reference",
};

export function getVerdictLabel(verdict: string | null | undefined): string {
  if (!verdict) return "Unknown";
  return VERDICT_LABELS[verdict] ?? verdict.replace(/_/g, " ");
}

export function getVerdictColor(verdict: string | null | undefined): string {
  if (!verdict) return "#8d9aaa";
  return VERDICT_COLORS[verdict] ?? "#8d9aaa";
}

export function getVerdictTone(verdict: string | null | undefined): "positive" | "negative" | "warning" | "neutral" {
  if (!verdict) return "neutral";
  if (verdict === "keep_direction") return "positive";
  if (verdict === "undo" || verdict === "undo_partially") return "negative";
  if (verdict === "retest") return "warning";
  return "neutral";
}
