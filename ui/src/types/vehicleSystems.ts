export type ComponentObservabilityState =
  | "definition_known"
  | "setup_captured"
  | "live_response_observable"
  | "current_response_observed"
  | "mechanism_supported"
  | "controlled_response_known"
  | "exact_context_policy_known"
  | "unavailable";

export type ComponentRelevance =
  | "irrelevant"
  | "candidate"
  | "supported"
  | "contradicted"
  | "blocked"
  | "tested";

export type ComponentAwarenessState = {
  component_id: string;
  run_id: string;
  lap_number: number | null;
  phase: string | null;
  lap_pct_start: number | null;
  lap_pct_end: number | null;
  current_settings: string[];
  current_setting_provenance: string[];
  observability_states: ComponentObservabilityState[];
  current_response_state: "observed" | "not_observed" | "unavailable";
  relevance: ComponentRelevance;
  supporting_artifact_ids: string[];
  contradicting_artifact_ids: string[];
  confounders: string[];
  coupled_component_ids: string[];
  controlled_history: Array<{
    workflow_id: string;
    control_key: string;
    mechanism_state: string;
    control_response: string;
    policy_verdict: "keep" | "undo" | "retest" | "invalid";
    countereffects: string[];
    exact_context: true;
  }>;
  current_testability: "measurement_only" | "policy_blocked" | "p19_authorized";
  authority_state: "knowledge_only" | "observation_only" | "controlled_history" | "p19_authorized";
  blocker_reasons: string[];
  setup_authorized: boolean;
};

export type VehicleSystemsProjection = {
  schema_version: "p26.component-awareness.v1";
  run_id: string;
  graph_version: string;
  leading_system: string;
  next_discriminator: string;
  component_states: ComponentAwarenessState[];
  authority: "p19_projection_only";
  setup_authorized: boolean;
};
