// ── Shared UI constants for RaceLab Garage ──────────────────
// Centralized to avoid duplication across components.

export const SEVERITY_COLOURS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  watch: "#f59e0b",
  info: "#38bdf8",
};

export const EVENT_SHAPES: Record<string, string> = {
  MIN_SPLITTER: "▼",
  WORST_SPEED_LOSS: "◆",
  WORST_DRAG_SCRUB: "■",
  HIGHEST_RAKE: "▲",
  HIGHEST_PLATFORM_COMPRESSION: "●",
  HIGHEST_SHOCK_ACTIVITY: "⬟",
  MAX_DYNAMIC_PRESSURE: "○",
};

export const CATEGORY_LABELS: Record<string, string> = {
  MIN_SPLITTER: "Platform Risk",
  WORST_SPEED_LOSS: "Speed Loss",
  WORST_DRAG_SCRUB: "Drag / Scrub",
  HIGHEST_RAKE: "Platform",
  HIGHEST_PLATFORM_COMPRESSION: "Platform Risk",
  HIGHEST_SHOCK_ACTIVITY: "Shock / Stability",
  MAX_DYNAMIC_PRESSURE: "Aero Context",
};

export const CATEGORY_ORDER: Record<string, number> = {
  "Platform Risk": 1,
  "Speed Loss": 2,
  "Drag / Scrub": 3,
  Platform: 4,
  "Shock / Stability": 5,
  "Aero Context": 6,
};

export const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  watch: 2,
  info: 3,
};

/** Map event type to the workspace tab that should open when clicked. */
export const EVENT_WORKSPACE_MAP: Record<string, string> = {
  MIN_SPLITTER: "platform_trace",
  WORST_SPEED_LOSS: "speed_delta",
  WORST_DRAG_SCRUB: "drag_scrub",
  HIGHEST_RAKE: "platform_trace",
  HIGHEST_PLATFORM_COMPRESSION: "platform_trace",
  HIGHEST_SHOCK_ACTIVITY: "platform_trace",
  MAX_DYNAMIC_PRESSURE: "platform_trace",
};

export function eventWorkspace(eventType: string): string {
  return EVENT_WORKSPACE_MAP[eventType] ?? "platform_trace";
}

export function eventLabel(eventType: string): string {
  const map: Record<string, string> = {
    MIN_SPLITTER: "Platform Trace",
    WORST_SPEED_LOSS: "Speed Delta",
    WORST_DRAG_SCRUB: "Drag/Scrub",
    HIGHEST_RAKE: "Platform Trace",
    HIGHEST_PLATFORM_COMPRESSION: "Platform Trace",
    HIGHEST_SHOCK_ACTIVITY: "Platform Trace",
    MAX_DYNAMIC_PRESSURE: "Platform Trace",
  };
  return map[eventType] ?? "Platform Trace";
}

/** Channels tagged as proxies/estimates — shown with dashed lines and "(proxy)" badge. */
export const PROXY_CHANNELS = new Set([
  "drag_scrub_suspicion",
  "full_throttle_resistance_index",
  "driven_wheel_slip_proxy",
  "aero_balance_front_pct",
  "platform_compression_index",
  "platform_risk_score",
  "lf_slip_ratio_proxy", "rf_slip_ratio_proxy",
  "lr_slip_ratio_proxy", "rr_slip_ratio_proxy",
]);
