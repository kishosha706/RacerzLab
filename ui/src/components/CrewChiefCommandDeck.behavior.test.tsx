import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunIntelligenceReport } from "../types/intelligence";
import { CrewChiefCommandDeck } from "./CrewChiefCommandDeck";

const api = vi.hoisted(() => ({
  fetchCrewChiefWorkspace: vi.fn(),
}));

vi.mock("../api/client", () => ({
  fetchCrewChiefWorkspace: api.fetchCrewChiefWorkspace,
  answerCrewChiefQuestion: vi.fn(),
  abandonCrewChiefInvestigation: vi.fn(),
  advanceCrewChiefInvestigation: vi.fn(),
  openCrewChiefInvestigation: vi.fn(),
  rebaseCrewChiefInvestigation: vi.fn(),
  updateCrewChiefObjective: vi.fn(),
}));

const report = {} as RunIntelligenceReport;
const props = {
  runId: "run-1",
  sessionId: "session-1",
  report,
  scopeRunIds: ["run-1"],
  learning: false,
  onFocusEvidence: vi.fn(),
};

const vehicleDynamicsAssessment = () => ({
  schema_version: "p35.performance-mechanism-assessment.v1",
  p35_assessment_sha256: "a".repeat(64),
  run_id: "run-1",
  session_id: "session-1",
  objective_id: "race_long_run",
  car_path: "stockcars chevycamarozl1 2022",
  car_version: "next-gen",
  iracing_build_version: "2026.08.01.01",
  track_package: "oval",
  vehicle_runtime_identity_sha256: "b".repeat(64),
  graph_id: "p35vdg_c14af7ad22a752df5710a6e6",
  graph_version: "2026.08.next-gen-oval.v1:c14af7ad22a7",
  knowledge_version: "2026.08.p35-next-gen-oval.v1",
  knowledge_graph_sha256: "c14af7ad22a752df5710a6e695b50f085fa4d15ecb20b271b3dc6205e3113030",
  p19_reasoning_snapshot_sha256: "c".repeat(64),
  p20_state_revision: "d".repeat(64),
  p20_profile_hash: null,
  p26_graph_version: "p26.next-gen.v1",
  p26_knowledge_graph_sha256: "e".repeat(64),
  p32_projection_sha256: "f".repeat(64),
  p32_performance_mechanism_ids: [],
  performance_opportunity_ids: [],
  measured_time_consequence_available: false,
  chain: ["driver_input", "vehicle_demand", "vehicle_response", "tire_platform_state", "time_consequence"]
    .map((stage) => ({
      stage,
      evidence_state: "unavailable",
      source_artifact_ids: [],
      source_channels: [],
      summary: `${stage.replace(/_/g, " ")} is unavailable in this scope.`,
      blocker_reasons: ["No clean comparison window is available."],
      authority: "observation_only",
    })),
  tire_demand_state_ids: [],
  load_path_ids: [],
  response_regime: null,
  response_observations: [],
  problem_signature: null,
  operational_response_evidence: [],
  mechanism_separation: [],
  candidates: [],
  focus_artifacts: [],
  strongest_support_artifact_id: null,
  strongest_contradiction_artifact_id: null,
  next_discriminator_contract_id: null,
  unavailable_quantity_ids: ["quantity:exact_wheel_load", "quantity:exact_tire_force"],
  traffic_blocked: false,
  applicability_state: "ready",
  applicability_blockers: [],
  blocker_reasons: ["No clean comparison window is available."],
  observation_authority: "observation_only",
  mechanism_authority: "candidate_only",
  component_causal_claim_count: 0,
  setup_authorized: false,
  terminal_authority: "p19_only",
});

const workspace = () => ({
  identity: { investigation_id: null, workspace_revision: "revision-1" },
  terminal_decision: {
    kind: "measurement_mission", title: "Measure the next clean pass", instruction: "Collect three clean laps.",
    authority: "measurement_only", control_key: null, setup_effect_id: null,
    experiment_factor_id: null, direction_sign: null, current_value: null, proposed_value: null,
    source_event_ids: [], workflow_id: null, workflow_revision: null, blocker_reasons: [],
  },
  investigation: null,
  folded_state: null,
  evidence_index: { entries: [] },
  performance_intelligence: {
    speed_story: {
      next: "Collect three clean laps.", observed_direction: "unavailable", what_costs_time: "No clean comparison yet.",
      attribution: "Attribution unavailable.", where_it_starts: "Origin unavailable.", what_carries: "Carry unavailable.",
      strongest_contradiction: "No clean reference lap.", driver: "Driver evidence unavailable.",
      car: "Car evidence unavailable.", systems: "System evidence unavailable.", history: "Legacy history must not render.",
      comparison_window: "Window unavailable.", source_context: "Source unavailable.", reference_context: "Reference unavailable.",
    },
    opportunity_map: { opportunities: [], context_blockers: ["No clean reference lap."] },
    corner_chains: [],
    track_demand: {
      full_throttle_fraction: null, braking_fraction: null, cornering_fraction: null,
      traffic_exposure_fraction: null,
    },
    component_influences: [],
    objective_envelope: { primary_outcomes: ["repeatability"], protected_outcomes: ["stability"] },
    explanation_chain: { strongest_contradiction: "No clean reference lap.", p19_next_move: "Collect three clean laps." },
  },
  vehicle_dynamics: vehicleDynamicsAssessment(),
  engineering_knowledge: {
    schema_version: "p352.current-engineering-knowledge.v1",
    projection_sha256: "9".repeat(64),
    run_id: "run-1", session_id: "session-1", complaint_prior: null,
    p19_reasoning_snapshot_sha256: "c".repeat(64), p20_state_revision: "d".repeat(64),
    p26_knowledge_graph_sha256: "e".repeat(64), p32_projection_sha256: "f".repeat(64),
    p35_assessment_sha256: "a".repeat(64), p33_projection_sha256: "2".repeat(64),
    bridge_coverage_sha256: "8".repeat(64), p32_opportunity_id: null,
    hypotheses: [{
      bridge_id: `p351b_${"1".repeat(24)}`, effect_id: "front_arb_knowledge", setup_area: "front_arb_arm",
      physical_role: "Changes direction-neutral front roll support.",
      direction_sign: 0, experiment_factor_id: null,
      level: "educational_knowledge", relevance: "knowledge_only", p32_opportunity_id: null,
      p35_mechanism_ids: [], p20_mechanism_ids: [], possible_component_family_ids: [],
      p26_component_family_ids: [], current_candidate_component_ids: [],
      current_supported_component_ids: [], contradicted_component_ids: [],
      blocked_component_ids: [], unobservable_component_ids: [], irrelevant_component_ids: [],
      response_regimes: ["steady_state"], relevant_phases: ["center"],
      expected_vehicle_response_ids: ["front_roll_response"],
      expected_vehicle_state_ids: ["p352.expected_vehicle_state:front_arb_knowledge:0:front_roll_response"],
      validation_metric_ids: ["p352.validation_metric:front_arb_knowledge:0:front_roll_response"],
      countereffect_ids: ["exit_security"], protected_outcomes: ["exit security"],
      countereffect_state_ids: ["p352.countereffect_state:front_arb_knowledge:0:exit_security"],
      protected_performance_outcome_ids: ["p352.protected_outcome:front_arb_knowledge:0:exit_security"],
      rollback_condition_ids: ["p352.rollback:front_arb_knowledge"],
      inspection_tool_ids: ["inspect_steady_platform"],
      support_artifact_ids: [], contradiction_artifact_ids: [], discriminator_contract_ids: [],
      missing_evidence: ["Current mechanism evidence is unavailable."], controlled_history: [],
      knowledge_applicability: "educational_only", runtime_evidence_state: "unavailable",
      p19_control: null, authority: "knowledge_only", setup_authorized: false,
    }],
    leading_hypothesis_ids: [], next_discriminator_contract_id: null,
    blocker_reasons: ["No clean comparison window is available."], terminal_authority: "p19_only",
    non_p19_setup_authorized: false,
  },
  learning_prior: {
    state: "available", strength: "single_case", context_transfer_level: "compatible",
    recurrence: {
      classification: "possible_recurrence", statement: "A similar qualified driver pattern was observed once.",
      counts: { independent_episode_count: 1, distinct_session_count: 1 },
      useful_discriminator: null, prior_dead_end: null,
    },
    context_transfers: [],
    driver_tendencies: [{
      fingerprint_id: "fingerprint-1", state: "repeatable_tendency",
      source_experience_ids: ["p33x-1"],
      contradictions: [],
      tendencies: [{
        contribution_id: "contribution-1", metric: "brake_release_timing_consistency",
        statement: "Brake release timing repeated in the source window.", source_artifact_ids: ["artifact-1"],
      }],
    }],
    car_response_history: [], useful_prior_investigations: [], mind_change_history: [], known_dead_ends: [],
    recommended_attention_order: [],
    ledger: {
      investigations_resolved: 1, investigations_opened: 1, controlled_tests: 0,
      measurement_missions: 1, questions_asked: 0, laps_consumed_before_resolution: 3,
      keep_outcomes: 0, undo_outcomes: 0, retest_outcomes: 0, no_call_outcomes: 1,
      driver_focus_outcomes: 0, recurring_problem_count: 1, recurrence_resolved_faster_count: 0,
      average_tool_steps_before_resolution: null, repeated_dead_end_tools: [], successful_discriminators: [],
    },
    post_run_brief: {
      what_we_learned: ["Brake release timing repeated in one qualified source window."],
      what_changed_our_mind: [], what_did_not_work: [], next_attention: [], blocker_reasons: [],
    },
    counts: { observation_count: 1 }, blocker_reasons: [],
    evidence_references: [{
      reference_id: "p33ref-1", experience_id: "p33x-1", state: "available", blocker_reasons: [],
      provenance: {
        provenance_sha256: "provenance-hash",
        artifact_id: "artifact-1", producer_id: "p20.physical_episode", run_id: "run-history",
        session_id: "session-history", setup_id: "setup-history", setup_snapshot_sha256: "setup-hash",
        build_context_sha256: "build-hash", lap_numbers: [7], lap_pct_start: 20, lap_pct_end: 30,
        phase: "entry", source_channels: ["brake_pct"], evidence_state: "measured", polarity: "support",
      },
    }],
  },
  investigation_improvement: {
    schema_version: "p34.investigation-improvement-projection.v1",
    projection_sha256: "projection-hash",
    run_id: "run-1",
    session_id: "session-1",
    workspace_revision: "revision-1",
    state: "unavailable",
    production_policy: "deterministic_baseline",
    memory_policy_state: "shadow_only",
    current_pair: null,
    current_context: null,
    current_pair_status: null,
    latest_completed_pair: null,
    latest_completed_comparison: null,
    latest_outcome_status: null,
    decisions_differ: false,
    difference_explanation: "The deterministic baseline remains production; no frozen pair is available.",
    memory_evidence_record_ids: [],
    context_transfer_class: "none",
    readiness: {
      production_policy: "deterministic_baseline",
      memory_policy_state: "shadow_only",
      activation_decision: "no_activation_earned",
      evaluation_decision: "no_activation_earned",
      effective_activation_decision_id: null,
      effective_activation_decision_sha256: null,
      qualified_historical_investigations: 0,
      qualified_prospective_investigations: 0,
      observable_comparisons: 0,
      unobservable_comparisons: 0,
      historical_deficit: 20,
      prospective_deficit: 12,
      exact_recurrence_deficit: 5,
      compatible_recurrence_deficit: 5,
      context_deficit: 3,
      problem_family_deficit: 4,
      objective_deficit: 2,
      safety_gate_passed: false,
      negative_controls_passed: false,
      subgroup_gate_passed: false,
      blockers: ["Limited attention has not earned activation."],
      remaining_collection_missions: [
        "Collect qualified independent investigations.",
        "Cover another compatible context subgroup.",
      ],
      authority_ceiling: "attention_only",
      setup_authorized: false,
    },
    safety_blockers: ["No frozen pre-outcome pair exists."],
    p19_authority_unchanged: true,
    setup_authorized: false,
  },
  run_sentinel: {
    mission_state: "collecting", p19_plan_kind: "measurement_mission",
    context_cleared_laps: 0, mission_accepted_lap_ids: [], measurement_attempt_ids: [],
    mission_acceptance_basis: "unbound", required_laps: 3, mission: "Collect clean laps", stage: "measurement",
    need: "Three clean laps", hold_constant: [], watch: [], success: "Three context-cleared laps",
    stop: [], collection_complete: false, laps: [], blocker_reasons: [],
  },
  critique: { passed: true, findings: [] },
  p19_mission_contract: null,
  success_contract: null,
  current_subgoal: null,
  pending_driver_question: null,
  adaptive_research: { state: "data_locked", activation_gate: "Held-out evidence is required." },
}) as never;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CrewChiefCommandDeck boundary states", () => {
  it("withholds the decision while exact evidence identities are being bound", () => {
    api.fetchCrewChiefWorkspace.mockReturnValue(new Promise(() => {}));
    const { container } = render(<CrewChiefCommandDeck {...props} />);

    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.getByText("Binding current evidence")).toBeTruthy();
    expect(screen.getByText(/P19, P20, P26, P32, P33, P34, and P35 identities/)).toBeTruthy();
  });

  it("renders a fail-closed empty boundary when workspace trust rejects", async () => {
    api.fetchCrewChiefWorkspace.mockRejectedValue(new Error("Workspace identity mismatch."));
    render(<CrewChiefCommandDeck {...props} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Crew Chief withheld");
    expect(alert.textContent).toContain("Workspace identity mismatch.");
  });

  it("shows one concise engineering-memory line in Race Mode", async () => {
    api.fetchCrewChiefWorkspace.mockResolvedValue(workspace());
    const { container } = render(<CrewChiefCommandDeck {...props} />);

    expect(await screen.findByText("MEMORY · ATTENTION ONLY")).toBeTruthy();
    expect(screen.getByText(/Brake release timing repeated in one qualified source window/)).toBeTruthy();
    expect(screen.queryByText(/ENGINEERING MEMORY/)).toBeNull();
    expect(screen.queryByText(/Legacy history must not render/)).toBeNull();

    const primaryStory = screen.getByLabelText("Measured Speed Story");
    expect(primaryStory.querySelectorAll(":scope > p")).toHaveLength(4);
    for (const label of ["NEXT · P19", "OBSERVED · UNAVAILABLE", "ATTRIBUTION", "STRONGEST CONTRADICTION"]) {
      expect(within(primaryStory).getByText(label)).toBeTruthy();
    }
    expect(within(primaryStory).queryByText("WHERE IT STARTS")).toBeNull();
    expect(within(primaryStory).queryByText("WHAT CARRIES")).toBeNull();

    const disclosure = container.querySelector<HTMLDetailsElement>("details.speed-story-detail");
    expect(disclosure).not.toBeNull();
    expect(disclosure?.hasAttribute("open")).toBe(false);
    expect(within(disclosure as HTMLElement).getByText("Origin and carry")).toBeTruthy();
    expect(within(disclosure as HTMLElement).getByText("WHERE IT STARTS")).toBeTruthy();
    expect(within(disclosure as HTMLElement).getByText("WHAT CARRIES")).toBeTruthy();
    expect(screen.queryByLabelText("Investigation Improvement, read only")).toBeNull();
    expect(screen.queryByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only")).toBeNull();
    expect(screen.queryByLabelText("Vehicle Dynamics learning handoff")).toBeNull();
    expect(screen.queryByLabelText("Unified Dial-In engineering knowledge")).toBeNull();
    const dynamicsLine = screen.getByLabelText("Vehicle Dynamics, candidate mechanisms only");
    expect(within(dynamicsLine).getByText("VEHICLE DYNAMICS · BLOCKED")).toBeTruthy();
    expect(dynamicsLine.textContent).toContain("Vehicle mechanism remains unresolved.");
    expect(dynamicsLine.textContent).toContain("No clean comparison window is available.");
  });

  it("renders the unified knowledge spine only in Learning Mode without inventing setup authority", async () => {
    api.fetchCrewChiefWorkspace.mockResolvedValue(workspace());
    render(<CrewChiefCommandDeck {...props} learning />);

    const spine = await screen.findByLabelText("Unified Dial-In engineering knowledge");
    for (const heading of [
      "Why this system is relevant",
      "What it physically changes",
      "What the car is doing now",
      "What evidence is missing",
      "What would separate the candidates",
      "What history says",
    ]) expect(within(spine).getByText(heading)).toBeTruthy();
    expect(within(spine).getByText(/NEXT .* P19/)).toBeTruthy();
    expect(within(spine).getByText("P19 ONLY FOR ACTION")).toBeTruthy();
    expect(spine.textContent).toContain("Reviewed setup knowledge");
    expect(spine.textContent).toContain("Changes direction-neutral front roll support.");
    expect(spine.textContent).not.toContain("proposed value");
    expect(spine.textContent).not.toContain("setup target");
  });

  it("names only the leading supported mechanism candidate in the Race secondary line", async () => {
    const value = workspace() as any;
    value.vehicle_dynamics.candidates = [{
      mechanism_id: "mechanism:center_rotation_deficit",
      relevance: "candidate",
      blocker_reasons: [],
    }];
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);
    render(<CrewChiefCommandDeck {...props} />);

    const dynamicsLine = await screen.findByLabelText("Vehicle Dynamics, candidate mechanisms only");
    expect(within(dynamicsLine).getByText("VEHICLE DYNAMICS · READY")).toBeTruthy();
    expect(dynamicsLine.textContent).toContain("Current evidence supports center rotation deficit as a mechanism candidate to inspect.");
    expect(dynamicsLine.textContent).not.toContain("component cause");
    expect(dynamicsLine.textContent).not.toContain("setup authority");
    expect(screen.queryByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only")).toBeNull();
  });

  it("keeps a reviewed ready scope with no candidate in the blocked hierarchy", async () => {
    const value = workspace() as any;
    value.vehicle_dynamics.applicability_state = "ready";
    value.vehicle_dynamics.applicability_blockers = [];
    value.vehicle_dynamics.blocker_reasons = [];
    value.vehicle_dynamics.candidates = [];
    value.vehicle_dynamics.chain = value.vehicle_dynamics.chain.map((stage: any) => ({
      ...stage,
      blocker_reasons: [],
    }));
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);
    render(<CrewChiefCommandDeck {...props} />);

    const dynamicsLine = await screen.findByLabelText("Vehicle Dynamics, candidate mechanisms only");
    expect(within(dynamicsLine).getByText("VEHICLE DYNAMICS · BLOCKED")).toBeTruthy();
    expect(dynamicsLine.textContent).toContain("Vehicle mechanism remains unresolved.");
    expect(dynamicsLine.textContent).toContain("No typed current-scope vehicle-response evidence is available.");
    expect(dynamicsLine.textContent).not.toContain("VEHICLE DYNAMICS · UNAVAILABLE");
  });

  it("keeps measured time above a blocked mechanism call in the Race secondary line", async () => {
    const value = workspace() as any;
    value.vehicle_dynamics.measured_time_consequence_available = true;
    value.vehicle_dynamics.candidates = [{
      mechanism_id: "mechanism:center_rotation_deficit",
      relevance: "blocked",
      blocker_reasons: ["Traffic overlaps the comparison window."],
    }];
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);
    render(<CrewChiefCommandDeck {...props} />);

    const dynamicsLine = await screen.findByLabelText("Vehicle Dynamics, candidate mechanisms only");
    expect(within(dynamicsLine).getByText("VEHICLE DYNAMICS · BLOCKED")).toBeTruthy();
    expect(dynamicsLine.textContent).toContain("Time loss is measured; vehicle mechanism remains unresolved.");
    expect(dynamicsLine.textContent).toContain("Traffic overlaps the comparison window.");
    expect(dynamicsLine.textContent).not.toContain("setup authority");
  });

  it("labels an unreviewed runtime unavailable instead of implying a blocked diagnosis", async () => {
    const value = workspace() as any;
    value.vehicle_dynamics.applicability_state = "unreviewed_build";
    value.vehicle_dynamics.applicability_blockers = ["This iRacing build has not been reviewed."];
    value.vehicle_dynamics.blocker_reasons = [];
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);
    render(<CrewChiefCommandDeck {...props} />);

    const dynamicsLine = await screen.findByLabelText("Vehicle Dynamics, candidate mechanisms only");
    expect(within(dynamicsLine).getByText("VEHICLE DYNAMICS · UNAVAILABLE")).toBeTruthy();
    expect(dynamicsLine.textContent).toContain("Vehicle-response evidence is unavailable in this scope");
    expect(dynamicsLine.textContent).toContain("This iRacing build has not been reviewed.");
    expect(dynamicsLine.textContent).not.toContain("mechanism remains unresolved");
  });

  it("hands a ready mechanism candidate into the Learning blackboard without a cause call", async () => {
    const value = workspace() as any;
    value.vehicle_dynamics.candidates = [{
      mechanism_id: "mechanism:center_rotation_deficit",
      p32_performance_mechanism_ids: ["mechanism:mid_corner_rotation"],
      support_artifact_ids: [],
      contradiction_artifact_ids: [],
      discriminator_contract_ids: [],
      component_family_ids: [],
      relevance: "candidate",
      blocker_reasons: [],
    }];
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);
    render(<CrewChiefCommandDeck {...props} learning />);

    const handoff = await screen.findByLabelText("Vehicle Dynamics learning handoff");
    expect(within(handoff).getByText("MECHANISM HANDOFF · READY")).toBeTruthy();
    expect(handoff.textContent).toContain("A current mechanism candidate cleared the evidence screen.");
    expect(handoff.textContent).toContain("Follow its support, uncertainty, and discriminator below.");
    expect(handoff.textContent).not.toContain("cause");
    expect(handoff.textContent).not.toContain("setup authority");
    expect(screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only")).toBeTruthy();
  });

  it("does not promise a discriminator for a blocked empty assessment with none published", async () => {
    const value = workspace() as any;
    value.vehicle_dynamics.candidates = [];
    value.vehicle_dynamics.next_discriminator_contract_id = null;
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);
    render(<CrewChiefCommandDeck {...props} learning />);

    const handoff = await screen.findByLabelText("Vehicle Dynamics learning handoff");
    expect(within(handoff).getByText("MECHANISM HANDOFF · BLOCKED")).toBeTruthy();
    expect(handoff.textContent).toContain("The blackboard shows the blocker and the evidence still missing in this scope.");
    expect(handoff.textContent).not.toContain("next discriminator");
  });

  it("shows unavailable Investigation Improvement only in Learning Mode without activation controls", async () => {
    const value = workspace() as any;
    value.vehicle_dynamics.next_discriminator_contract_id = "contract:separate-current-response";
    value.investigation_improvement.readiness.observable_comparisons = 1;
    value.investigation_improvement.readiness.safety_gate_passed = true;
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);
    render(<CrewChiefCommandDeck {...props} learning />);

    const improvement = await screen.findByLabelText("Investigation Improvement, read only");
    const handoff = screen.getByLabelText("Vehicle Dynamics learning handoff");
    expect(within(handoff).getByText("MECHANISM HANDOFF · BLOCKED")).toBeTruthy();
    expect(handoff.textContent).toContain("The vehicle mechanism is not isolated.");
    expect(handoff.textContent).toContain("The blackboard shows the blocker and the next discriminator.");
    expect(handoff.textContent).not.toContain("setup authority");
    expect(screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "NEXT · P19" })).toBeTruthy();
    expect(within(improvement).getByText("Paired evaluation unavailable")).toBeTruthy();
    expect(within(improvement).getByText(/No current frozen pair is available. No current investigation benefit is inferred/)).toBeTruthy();
    expect(within(improvement).getByText(/not evidence that it saves time, laps, or investigation steps/)).toBeTruthy();
    expect(within(improvement).getByText("coverage incomplete")).toBeTruthy();
    expect(within(improvement).getByText("Negative controls")).toBeTruthy();
    expect(within(improvement).getByText("Subgroups")).toBeTruthy();
    expect(within(improvement).getByText("Historical investigations:")).toBeTruthy();
    expect(within(improvement).getAllByText(/Cover another compatible context subgroup/)).toHaveLength(2);
    expect(within(improvement).queryByText(/safety passed/i)).toBeNull();
    expect(within(improvement).queryByRole("button")).toBeNull();
    expect(within(improvement).queryByText(/activate/i)).toBeNull();
  });

  it("labels a differing pending shadow as unobservable rather than an improvement", async () => {
    const value = workspace() as any;
    const decision = (actionId: string, selectedOrdinal: number, memoryIds: string[] = []) => ({
      decision_kind: "inspect_tool",
      action_id: actionId,
      priority_tier: "measurement_debt",
      safe_reorder_group: "measurement",
      baseline_ordinal: selectedOrdinal,
      selected_ordinal: selectedOrdinal,
      reason: "Frozen pre-outcome attention choice.",
      mandatory_check_ids: ["identity"],
      source_memory_record_ids: memoryIds,
      setup_authorized: false,
      terminal_policy_authorized: false,
    });
    value.investigation_improvement.state = "available";
    value.investigation_improvement.decisions_differ = true;
    value.investigation_improvement.difference_explanation = "The frozen shadow selected a different bounded inspection.";
    value.investigation_improvement.context_transfer_class = "exact";
    value.investigation_improvement.memory_evidence_record_ids = ["p33x_444444444444444444444444"];
    value.learning_prior.evidence_references[0].experience_id = "p33x_444444444444444444444444";
    value.investigation_improvement.current_pair_status = "pending";
    value.investigation_improvement.current_pair = {
      production_decision: decision("inspect_exit_carry", 1),
      baseline_decision: decision("inspect_exit_carry", 1),
      memory_decision: decision("inspect_path_efficiency", 2, ["p33x_444444444444444444444444"]),
    };
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);

    render(<CrewChiefCommandDeck {...props} learning />);

    const improvement = await screen.findByLabelText("Investigation Improvement, read only");
    expect(within(improvement).getByText("inspect exit carry")).toBeTruthy();
    expect(within(improvement).getByText("inspect path efficiency")).toBeTruthy();
    expect(within(improvement).getByText("Different executable action")).toBeTruthy();
    expect(within(improvement).getByText("Transfer / exact")).toBeTruthy();
    expect(within(improvement).getByText("p33x_444444444444444444444444")).toBeTruthy();
    fireEvent.click(within(improvement).getByLabelText(/Open P33 source/));
    expect(props.onFocusEvidence).toHaveBeenCalledWith(value.learning_prior.evidence_references[0]);
    expect(within(improvement).getByText(/not evidence that it saves time, laps, or investigation steps/)).toBeTruthy();
    expect(within(improvement).queryByText(/saved 2 laps/i)).toBeNull();
  });

  it("keeps a latest completed comparison separate when there is no current pair", async () => {
    const value = workspace() as any;
    value.investigation_improvement.state = "available";
    value.investigation_improvement.latest_outcome_status = "counterfactual_unobservable";
    value.investigation_improvement.difference_explanation = "The latest completed evaluation was withheld from activation evidence.";
    const completedDecision = {
      decision_kind: "inspect_tool",
      action_id: "inspect_exit_carry",
      priority_tier: "measurement_debt",
      safe_reorder_group: "measurement",
      baseline_ordinal: 1,
      selected_ordinal: 1,
      reason: "Frozen before the outcome.",
      mandatory_check_ids: ["identity"],
      source_memory_record_ids: [],
      setup_authorized: false,
      terminal_policy_authorized: false,
    };
    value.investigation_improvement.latest_completed_pair = {
      baseline_decision: completedDecision,
      memory_decision: completedDecision,
      memory_records_consulted: [],
      context_transfer_class: "none",
    };
    value.investigation_improvement.latest_completed_comparison = {
      comparison_id: "p34cmp_555555555555555555555555",
      observability: "counterfactual_unobservable",
      qualified: false,
      blockers: ["The shadow action was not directly executed."],
    };
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);

    render(<CrewChiefCommandDeck {...props} learning />);

    const improvement = await screen.findByLabelText("Investigation Improvement, read only");
    expect(within(improvement).getByText("Latest completed paired evaluation")).toBeTruthy();
    expect(within(improvement).getByText("Latest completed comparison")).toBeTruthy();
    expect(within(improvement).getByText("counterfactual unobservable")).toBeTruthy();
    expect(within(improvement).getByText(/No current frozen pair is available/)).toBeTruthy();
    expect(within(improvement).getByText(/no time, lap, or investigation-step saving is inferred/i)).toBeTruthy();
    expect(within(improvement).queryByText("Current frozen pair")).toBeNull();
  });

  it("renders only a qualified observed one-position discriminator advance", async () => {
    const value = workspace() as any;
    const decision = {
      decision_kind: "inspect_tool", action_id: "inspect_exit_carry",
      priority_tier: "driver_car_confounders", safe_reorder_group: "performance_measurement",
      baseline_ordinal: 4, selected_ordinal: 4,
      reason: "Frozen before the outcome.", mandatory_check_ids: ["workspace_identity"],
      source_memory_record_ids: [], setup_authorized: false, terminal_policy_authorized: false,
    };
    value.investigation_improvement.state = "available";
    value.investigation_improvement.latest_completed_pair = {
      baseline_decision: decision, memory_decision: decision,
      memory_records_consulted: [], context_transfer_class: "none",
    };
    value.investigation_improvement.latest_completed_comparison = {
      observability: "counterfactual_observable", qualified: true, blockers: [],
      bounded_reorder_observed: true, bounded_discriminator_step_advance: 1,
      bounded_discriminator_step_delay: 0, bounded_dead_end_promoted: false,
    };
    value.investigation_improvement.latest_outcome_status = "counterfactual_observable";
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);

    render(<CrewChiefCommandDeck {...props} learning />);

    const improvement = await screen.findByLabelText("Investigation Improvement, read only");
    expect(within(improvement).getByText("Qualified observed discriminator timing")).toBeTruthy();
    expect(within(improvement).getByText(/one useful discriminator position earlier/)).toBeTruthy();
    expect(within(improvement).queryByText(/seconds? saved|laps? saved|faster lap/i)).toBeNull();
  });

  it("labels earned limited attention without exposing an activation control", async () => {
    const value = workspace() as any;
    const decision = {
      decision_kind: "inspect_tool",
      action_id: "inspect_exit_carry",
      priority_tier: "measurement_debt",
      safe_reorder_group: "measurement",
      baseline_ordinal: 1,
      selected_ordinal: 1,
      reason: "Frozen pre-outcome attention choice.",
      mandatory_check_ids: ["identity"],
      source_memory_record_ids: [],
      setup_authorized: false,
      terminal_policy_authorized: false,
    };
    value.investigation_improvement = {
      ...value.investigation_improvement,
      state: "available",
      production_policy: "limited_attention",
      memory_policy_state: "limited_attention",
      current_pair: {
        production_decision: decision,
        baseline_decision: decision,
        memory_decision: decision,
      },
      current_pair_status: "pending",
      difference_explanation: "The earned policy retained the same executable inspection.",
      readiness: {
        ...value.investigation_improvement.readiness,
        production_policy: "limited_attention",
        memory_policy_state: "limited_attention",
        activation_decision: "limited_attention_earned",
        evaluation_decision: "limited_attention_earned",
        effective_activation_decision_id: `p34act_${"a".repeat(24)}`,
        effective_activation_decision_sha256: "a".repeat(64),
        historical_deficit: 0,
        prospective_deficit: 0,
        exact_recurrence_deficit: 0,
        compatible_recurrence_deficit: 0,
        context_deficit: 0,
        problem_family_deficit: 0,
        objective_deficit: 0,
        safety_gate_passed: true,
        negative_controls_passed: true,
        subgroup_gate_passed: true,
        blockers: [],
        remaining_collection_missions: [],
      },
      safety_blockers: [],
    };
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);

    render(<CrewChiefCommandDeck {...props} learning />);

    const improvement = await screen.findByLabelText("Investigation Improvement, read only");
    expect(within(improvement).getAllByText("limited attention").length).toBeGreaterThan(0);
    expect(within(improvement).getByText("Active production policy")).toBeTruthy();
    expect(within(improvement).getByText("BASELINE NEXT")).toBeTruthy();
    expect(within(improvement).getByText("MEMORY NEXT / limited attention")).toBeTruthy();
    expect(within(improvement).queryByRole("button")).toBeNull();
  });

  it("renders the compact full P33 projection and navigates only an available typed source", async () => {
    const onFocusEvidence = vi.fn();
    api.fetchCrewChiefWorkspace.mockResolvedValue(workspace());
    render(<CrewChiefCommandDeck {...props} learning onFocusEvidence={onFocusEvidence} />);

    expect(await screen.findByText("ENGINEERING MEMORY · ATTENTION ONLY")).toBeTruthy();
    for (const heading of [
      "Recurrence", "Context transfer", "Driver fingerprint", "Car response",
      "Investigation effectiveness", "Mind changes", "Dead ends", "Attention",
      "Learning ledger", "Post-run brief", "Blockers / strength",
    ]) expect(screen.getByText(heading)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Open source · Lap 7 · entry · 20–30% · measured/ }));
    expect(onFocusEvidence).toHaveBeenCalledWith(expect.objectContaining({ reference_id: "p33ref-1", state: "available" }));
    expect(screen.queryByText("Performance history")).toBeNull();
    expect(screen.queryByText("Response atlas")).toBeNull();
    expect(screen.getByText(/Mission acceptance not established/)).toBeTruthy();
    expect(screen.queryByText(/Contract accepted/)).toBeNull();
  });

  it("reports evidence states and context-cleared mission progress without exact-artifact or accepted-lap overclaim", async () => {
    const value = workspace() as any;
    const evidenceEntry = (artifactId: string, evidenceState: string) => ({
      artifact_id: artifactId,
      producer_id: "p20.physical_episode",
      run_id: "run-1",
      session_id: "session-1",
      setup_id: "setup-1",
      workspace_run_id: "run-1",
      workspace_session_id: "session-1",
      workspace_setup_id: "setup-1",
      source_run_id: "run-1",
      source_session_id: "session-1",
      source_setup_id: "setup-1",
      source_setup_sha256: "setup-hash",
      source_build_context_sha256: "build-hash",
      source_provenance_available: true,
      lap_numbers: [4],
      lap_pct_start: 20,
      lap_pct_end: 30,
      phase: "entry",
      mechanism_ids: [],
      component_ids: [],
      control_keys: [],
      objective: "race_long_run",
      source_channels: ["speed"],
      evidence_state: evidenceState,
      polarity: "neutral",
      blocker_reasons: [],
      typed_artifact: null,
      authority_ceiling: "observation_only",
    });
    value.evidence_index.entries = [
      evidenceEntry("measured-1", "measured"),
      evidenceEntry("blocked-1", "blocked_by_context"),
      { ...evidenceEntry("historical-1", "measured"), producer_id: "p33.engineering_experience" },
    ];
    value.run_sentinel.context_cleared_laps = 2;
    value.run_sentinel.required_laps = 3;
    value.run_sentinel.mission_state = "collecting";
    value.run_sentinel.mission_accepted_lap_ids = ["mission-lap-4"];
    value.run_sentinel.measurement_attempt_ids = ["attempt-1", "attempt-2"];
    value.run_sentinel.mission_acceptance_basis = "p19_measurement_attempt";
    value.run_sentinel.laps = [
      { lap_id: "lap-4", lap_number: 4, status: "context_cleared", reasons: [], context_ordinal: 1 },
      { lap_id: "lap-5", lap_number: 5, status: "context_cleared", reasons: [], context_ordinal: 2 },
      { lap_id: "lap-6", lap_number: 6, status: "rejected", reasons: ["Traffic in the comparison window."], context_ordinal: null },
    ];
    api.fetchCrewChiefWorkspace.mockResolvedValue(value);

    render(<CrewChiefCommandDeck {...props} learning />);

    expect(await screen.findByText("EVIDENCE STATES")).toBeTruthy();
    expect(screen.getByText(/1 measured · 1 blocked by context · 2 context-cleared · 3 mission target/)).toBeTruthy();
    expect(screen.getByText(/State collecting · Stage measurement · 2 context-cleared · 3 mission target · 1 contract-accepted lap · basis p19 measurement attempt · 2 measurement attempts/)).toBeTruthy();
    expect(screen.getByText((_content, element) => (
      element?.tagName === "LI" && element.textContent?.includes("Lap 4: context-cleared") === true
    ))).toBeTruthy();
    expect(screen.getByText((_content, element) => (
      element?.tagName === "LI" && element.textContent?.includes("Lap 6: rejected") === true
    ))).toBeTruthy();
    expect(screen.queryByText(/exact artifacts/i)).toBeNull();
    expect(screen.queryByText(/accepted laps/i)).toBeNull();
  });

  it.each(["insufficient_history", "blocked"])(
    "collapses %s Learning history to one attention-only summary",
    async (state) => {
      const value = workspace() as any;
      value.learning_prior.state = state;
      value.learning_prior.blocker_reasons = [state === "blocked"
        ? "Engineering history integrity could not be verified."
        : "No independent prior engineering episode cleared this context."];
      api.fetchCrewChiefWorkspace.mockResolvedValue(value);

      render(<CrewChiefCommandDeck {...props} learning />);

      const memory = await screen.findByLabelText("Engineering Memory, attention only");
      expect(within(memory).getByText("ENGINEERING MEMORY · ATTENTION ONLY")).toBeTruthy();
      expect(within(memory).getByText(state.replace(/_/g, " "))).toBeTruthy();
      expect(within(memory).getByText("P19 order unchanged")).toBeTruthy();
      expect(within(memory).getByText(/Current evidence and P19 remain authoritative/)).toBeTruthy();
      for (const emptyCardHeading of ["Recurrence", "Driver fingerprint", "Car response", "Dead ends", "Learning ledger"]) {
        expect(within(memory).queryByText(emptyCardHeading)).toBeNull();
      }
    },
  );

  it("renders an unavailable historical source as a blocker without a focus target", async () => {
    const blocked = workspace() as any;
    blocked.learning_prior.evidence_references[0].state = "unavailable";
    blocked.learning_prior.evidence_references[0].blocker_reasons = ["Saved source session is unavailable."];
    api.fetchCrewChiefWorkspace.mockResolvedValue(blocked);
    render(<CrewChiefCommandDeck {...props} learning />);

    expect(await screen.findByText("Saved source session is unavailable.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Open source · Lap 7/ })).toBeNull();
  });
});
