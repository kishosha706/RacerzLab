/**
 * Formats deterministic evidence and trust scores without implying that they are
 * calibrated probabilities. Measured coverage percentages use their own
 * formatters and must not pass through this helper.
 */
export function evidenceStrengthOutOf100(
  score: number | null | undefined,
  fallback = "Unavailable",
): string {
  if (score == null || !Number.isFinite(score)) return fallback;
  const bounded = Math.max(0, Math.min(1, score));
  return `${Math.round(bounded * 100)}/100`;
}

export function evidenceStrengthLabel(
  score: number | null | undefined,
  fallback = "Evidence strength unavailable",
): string {
  const value = evidenceStrengthOutOf100(score, "");
  return value ? `Evidence strength ${value}` : fallback;
}
