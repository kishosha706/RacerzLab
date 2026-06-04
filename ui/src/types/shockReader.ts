export type ShockCornerName = "LF" | "RF" | "LR" | "RR";

export type ShockPattern =
  | "balanced"
  | "low_speed_bump_heavy"
  | "low_speed_rebound_heavy"
  | "high_speed_bump_heavy"
  | "high_speed_rebound_heavy"
  | "excessive_high_speed_shoulders"
  | "impact_contact_driven"
  | "oscillation_recovery_issue"
  | "insufficient_evidence";

export type ShockCornerRead = {
  corner: ShockCornerName;
  sample_count: number;
  rebound_hi_pct: number;
  rebound_lo_pct: number;
  bump_lo_pct: number;
  bump_hi_pct: number;
  avg_rebound_in_s?: number | null;
  avg_bump_in_s?: number | null;
  center_pct: number;
  rms_in_s?: number | null;
  activity_index?: number | null;
  deflection_delta_range_in?: number | null;
  pattern: ShockPattern;
  confidence: "low" | "medium" | "high";
  setup_values: Record<string, number | null>;
  setting_recommendations: ShockSettingRecommendation[];
};

export type ShockSettingRecommendation = {
  corner: ShockCornerName;
  setting:
    | "ls_compression"
    | "hs_compression"
    | "hs_compression_slope"
    | "ls_rebound"
    | "hs_rebound"
    | "hs_rebound_slope";
  display_label: "LS Comp" | "HS Comp" | "HS-S Comp" | "LS Reb" | "HS Reb" | "HS-S Reb";
  current_value?: number | null;
  delta?: number | null;
  suggested_value?: number | null;
  direction: "add" | "subtract" | "hold" | "blocked" | "needs_more_evidence";
  magnitude: "hold" | "small" | "medium" | "big";
  confidence: "high" | "medium" | "low" | "needs_more_evidence";
  reason_short: string;
  goal: string;
  tradeoff: string;
  watch_for: string[];
  blocked_reason?: string | null;
};

export type ShockRecommendation = {
  id: string;
  corner_scope: ShockCornerName | "front" | "rear" | "all";
  setting:
    | "ls_compression"
    | "ls_rebound"
    | "hs_compression"
    | "hs_rebound"
    | "hs_compression_slope"
    | "hs_rebound_slope"
    | "compression_slope"
    | "rebound_slope";
  display_setting: string;
  semantic_direction: "add" | "subtract" | "move_more_linear" | "move_more_digressive" | "leave_alone";
  numeric_step?: number | null;
  current_value?: number | null;
  suggested_value?: number | null;
  blocked_by_limit: boolean;
  classification: "fine_tune" | "balance_swing" | "package_swing" | "leave_alone";
  goal: string;
  tradeoff: string;
  next_test: string;
  watch_for: string[];
  confidence: "low" | "medium" | "high";
  evidence_summary: string;
  hidden_debug?: Record<string, unknown> | null;
};

export type ShockReaderResponse = {
  run_id: string;
  lap_window?: string | null;
  phase?: string | null;
  boundary_in_s: number;
  bin_width_in_s: number;
  setup_snapshot_available: boolean;
  corners: ShockCornerRead[];
  recommendations: ShockRecommendation[];
  warnings: string[];
};
