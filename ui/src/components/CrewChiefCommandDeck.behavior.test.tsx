import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  continueCrewChiefInvestigation: vi.fn(),
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

const workspace = () => ({
  identity: { investigation_id: null, workspace_revision: "revision-1" },
  terminal_decision: {
    kind: "measurement_mission", title: "Measure the next clean pass", instruction: "Collect three clean laps.",
    authority: "measurement_only", control_key: null, current_value: null, proposed_value: null,
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
        artifact_id: "artifact-1", producer_id: "p20.physical_episode", run_id: "run-history",
        session_id: "session-history", setup_id: "setup-history", setup_snapshot_sha256: "setup-hash",
        build_context_sha256: "build-hash", lap_numbers: [7], lap_pct_start: 20, lap_pct_end: 30,
        phase: "entry", source_channels: ["brake_pct"],
      },
    }],
  },
  run_sentinel: {
    accepted_laps: 0, required_laps: 3, mission: "Collect clean laps", stage: "measurement",
    need: "Three clean laps", laps: [], blocker_reasons: [],
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
    expect(screen.getByText(/P19, P20, P26, P32, and P33 identities/)).toBeTruthy();
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
    render(<CrewChiefCommandDeck {...props} />);

    expect(await screen.findByText("MEMORY")).toBeTruthy();
    expect(screen.getByText(/Brake release timing repeated in one qualified source window/)).toBeTruthy();
    expect(screen.queryByText("ENGINEERING MEMORY")).toBeNull();
    expect(screen.queryByText(/Legacy history must not render/)).toBeNull();
  });

  it("renders the compact full P33 projection and navigates only an available typed source", async () => {
    const onFocusEvidence = vi.fn();
    api.fetchCrewChiefWorkspace.mockResolvedValue(workspace());
    render(<CrewChiefCommandDeck {...props} learning onFocusEvidence={onFocusEvidence} />);

    expect(await screen.findByText("ENGINEERING MEMORY")).toBeTruthy();
    for (const heading of [
      "Recurrence", "Context transfer", "Driver fingerprint", "Car response",
      "Investigation effectiveness", "Mind changes", "Dead ends", "Attention",
      "Learning ledger", "Post-run brief", "Blockers / strength",
    ]) expect(screen.getByText(heading)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Open telemetry · artifact-1/ }));
    expect(onFocusEvidence).toHaveBeenCalledWith(expect.objectContaining({ reference_id: "p33ref-1", state: "available" }));
    expect(screen.queryByText("Performance history")).toBeNull();
    expect(screen.queryByText("Response atlas")).toBeNull();
  });

  it("renders an unavailable historical source as a blocker without a focus target", async () => {
    const blocked = workspace() as any;
    blocked.learning_prior.evidence_references[0].state = "unavailable";
    blocked.learning_prior.evidence_references[0].blocker_reasons = ["Saved source session is unavailable."];
    api.fetchCrewChiefWorkspace.mockResolvedValue(blocked);
    render(<CrewChiefCommandDeck {...props} learning />);

    expect(await screen.findByText("Saved source session is unavailable.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Open telemetry · artifact-1/ })).toBeNull();
  });
});
