export type ReadinessCount = {
  key: string;
  label: string;
  current: number;
  required: number;
  unit: string;
  qualified_only: true;
};

export type CampaignReadiness = {
  campaign_kind: string;
  label: string;
  usable_units: number;
  required_units: number;
  invalid_attempts: number;
  remaining_units: number;
  state: "not_started" | "collecting" | "complete";
};

export type CapabilityReadiness = {
  capability_key: string;
  label: string;
  state: "locked" | "shadow" | "descriptive_only" | "deterministic";
  summary: string;
  blockers: string[];
  authority: "p19_p20_unchanged";
};

export type LearningDebt = {
  debt_key: string;
  summary: string;
  collection_action: string;
};

export type LearningReadinessProjection = {
  run_id: string;
  session_id: string | null;
  scope_key: string;
  generated_at: string;
  deterministic_authority: "P19 reasoning / P20 awareness";
  advanced_models_summary: "Shadow only";
  archived_sessions: number;
  archived_runs: number;
  counts: ReadinessCount[];
  campaigns: CampaignReadiness[];
  capabilities: CapabilityReadiness[];
  vehicle_profile_status: string;
  vehicle_profile_fields_ready: string[];
  vehicle_profile_fields_blocked: string[];
  debts: LearningDebt[];
  offline_evaluation_only: true;
};
