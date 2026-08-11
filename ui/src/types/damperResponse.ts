export interface DamperCornerMetrics {
  corner: "LF" | "RF" | "LR" | "RR";
  sample_count: number;
  velocity_histogram_pct: Record<string, number>;
  low_speed_regime_pct: number;
  high_speed_regime_pct: number;
  velocity_rms_in_s: number | null;
  dominant_frequency_hz: number | null;
  dominant_psd_proxy: number | null;
  spectral_evidence: {
    source_lap_ids: number[];
    qualified_window_count: number;
    effective_sample_rates_hz: number[];
    continuous_window_durations_s: number[];
    half_window_peak_hz: number[];
    frequency_resolution_hz: number[];
    agreement_tolerance_hz: number | null;
    agreeing_peak_count: number;
    repeated: boolean;
    rejection_reasons: string[];
  } | null;
}

export interface DamperConclusion {
  key: string;
  summary: string;
  evidence_state: string;
  confidence_score: number;
  source_channels: string[];
  supporting_evidence: string[];
  contradicting_evidence: string[];
  blocker_reasons: string[];
}

export interface DamperResponseReport {
  run_id: string;
  selected_lap: number;
  phases: string[];
  gate: {
    eligible: boolean;
    confidence_cap: number;
    blocker_reasons: string[];
    needed_measurements: string[];
  };
  corners: DamperCornerMetrics[];
  conclusions: DamperConclusion[];
}
