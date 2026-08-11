import type { EvidenceState } from "./telemetry";

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
  source_lap_numbers: number[];
  repeatability_lap_count: number;
  high_speed_compression_repeatable: boolean;
  high_speed_rebound_repeatable: boolean;
  compression_boundary_stable: boolean;
  rebound_boundary_stable: boolean;
  boundary_sensitivity_patterns: string[];
  setup_values: Record<
    | "ls_compression"
    | "hs_compression"
    | "hs_compression_slope"
    | "ls_rebound"
    | "hs_rebound"
    | "hs_rebound_slope",
    number | null
  >;
};

export type ShockReaderResponse = {
  run_id: string;
  lap_window?: string | null;
  phase?: string | null;
  zone_start_pct?: number | null;
  zone_end_pct?: number | null;
  boundary_in_s: number;
  boundary_basis: string;
  bin_width_in_s: number;
  setup_snapshot_available: boolean;
  corners: ShockCornerRead[];
  setup_authority: "withheld";
  warnings: string[];
  evidence_state: EvidenceState;
  source_channels: string[];
  blocker_reasons: string[];
};
