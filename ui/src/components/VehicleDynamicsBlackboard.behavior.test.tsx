// @ts-expect-error Vitest executes this contract in Node; the app tsconfig is browser-only.
import { readFileSync } from "node:fs";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CrewChiefEvidenceEntry } from "../types/crewChief";
import type { PerformanceMechanismAssessment } from "../types/vehicleDynamics";
import { VehicleDynamicsBlackboard } from "./VehicleDynamicsBlackboard";

const styles = readFileSync("src/styles.css", "utf8");

const supportId = `p35.focus.roll_response:${"a".repeat(24)}`;
const contradictionId = `p35.focus.roll_response:${"b".repeat(24)}`;
const discriminatorId = `p35.focus.roll_response:${"c".repeat(24)}`;
const mechanismId = "mechanism:front_tire_demand";
const discriminatorContractId = "contract:front_demand_discriminator";

const assessment = (): PerformanceMechanismAssessment => ({
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
  p32_performance_mechanism_ids: ["mechanism:corner_rotation"],
  performance_opportunity_ids: ["opportunity-1"],
  measured_time_consequence_available: true,
  chain: [
    ["driver_input", "Steering demand is measured."],
    ["vehicle_demand", "The selected window carries sustained corner demand."],
    ["vehicle_response", "Yaw response is observed alongside steering demand."],
    ["tire_platform_state", "Relative tire and platform state remains a proxy."],
    ["time_consequence", "The selected window has a measured time consequence."],
  ].map(([stage, summary], index) => ({
    stage: stage as PerformanceMechanismAssessment["chain"][number]["stage"],
    evidence_state: "measured",
    source_artifact_ids: [`source-${index}`],
    source_channels: [
      "steering_angle_deg",
      "yaw_rate_deg_s",
      "speed_mph",
      "lat_accel_g",
      "long_accel_g",
    ],
    summary,
    blocker_reasons: [],
    authority: "observation_only",
  })),
  tire_demand_state_ids: ["tire_demand:combined_front"],
  load_path_ids: ["load_path:steering_to_front_contact"],
  response_regime: "steady_state",
  candidates: [{
    mechanism_id: mechanismId,
    p32_performance_mechanism_ids: ["mechanism:corner_rotation"],
    support_artifact_ids: [supportId],
    contradiction_artifact_ids: [contradictionId],
    discriminator_contract_ids: [discriminatorContractId],
    component_family_ids: ["component_family:front_roll"],
    blocker_reasons: [],
    relevance: "candidate",
    authority: "candidate_only",
    component_cause_authorized: false,
    setup_authorized: false,
  }],
  focus_artifacts: [
    {
      artifact_id: supportId,
      mechanism_id: mechanismId,
      observation_contract_id: null,
      inspection_tool_id: "inspect_roll_response",
      stage: "vehicle_response",
      evidence_state: "observed_correlation",
      source_artifact_ids: ["source-2"],
      source_channels: ["steering_angle_deg", "yaw_rate_deg_s"],
      lap_numbers: [7], lap_pct_start: 42.5, lap_pct_end: 51.5, phase: "center",
      polarity: "support",
      summary: "Higher steering demand and lower yaw support front-demand relevance.",
      blocker_reasons: [], authority: "observation_only",
    },
    {
      artifact_id: contradictionId,
      mechanism_id: mechanismId,
      observation_contract_id: null,
      inspection_tool_id: "inspect_roll_response",
      stage: "vehicle_response",
      evidence_state: "observed_correlation",
      source_artifact_ids: ["source-2"],
      source_channels: ["steering_angle_deg", "yaw_rate_deg_s"],
      lap_numbers: [7], lap_pct_start: 42.5, lap_pct_end: 51.5, phase: "center",
      polarity: "contradiction",
      summary: "A current response contradiction remains visible.",
      blocker_reasons: [], authority: "observation_only",
    },
    {
      artifact_id: discriminatorId,
      mechanism_id: mechanismId,
      observation_contract_id: discriminatorContractId,
      inspection_tool_id: "inspect_roll_response",
      stage: "vehicle_response",
      evidence_state: "needs_confirmation",
      source_artifact_ids: ["source-2"],
      source_channels: [
        "steering_angle_deg",
        "yaw_rate_deg_s",
        "speed_mph",
        "lat_accel_g",
        "long_accel_g",
      ],
      lap_numbers: [7], lap_pct_start: 42.5, lap_pct_end: 51.5, phase: "center",
      polarity: "neutral",
      summary: "A clean repeated response window would separate the candidates.",
      blocker_reasons: ["A repeated clean window is required."], authority: "observation_only",
    },
  ],
  strongest_support_artifact_id: supportId,
  strongest_contradiction_artifact_id: contradictionId,
  next_discriminator_contract_id: discriminatorContractId,
  unavailable_quantity_ids: ["quantity:exact_wheel_load", "quantity:exact_tire_force"],
  traffic_blocked: false,
  applicability_state: "ready",
  applicability_blockers: [],
  blocker_reasons: [],
  observation_authority: "observation_only",
  mechanism_authority: "candidate_only",
  component_causal_claim_count: 0,
  setup_authorized: false,
  terminal_authority: "p19_only",
});

const p35Entry = (artifactId: string, polarity: CrewChiefEvidenceEntry["polarity"]): CrewChiefEvidenceEntry => ({
  artifact_id: artifactId,
  producer_id: "p35.roll_response",
  run_id: "run-1",
  session_id: "session-1",
  setup_id: "setup-1",
  workspace_run_id: "run-1",
  workspace_session_id: "session-1",
  workspace_setup_id: "setup-1",
  source_run_id: "run-1",
  source_session_id: "session-1",
  source_setup_id: "setup-1",
  source_setup_sha256: "2".repeat(64),
  source_build_context_sha256: "b".repeat(64),
  source_provenance_available: true,
  lap_numbers: [7],
  lap_pct_start: 42.5,
  lap_pct_end: 51.5,
  phase: "center",
  mechanism_ids: [mechanismId],
  component_ids: [],
  control_keys: [],
  objective: "race_long_run",
  source_channels: artifactId === discriminatorId
    ? [
      "steering_angle_deg",
      "yaw_rate_deg_s",
      "speed_mph",
      "lat_accel_g",
      "long_accel_g",
    ]
    : ["steering_angle_deg", "yaw_rate_deg_s"],
  evidence_state: artifactId === discriminatorId ? "needs_confirmation" : "observed_correlation",
  polarity,
  blocker_reasons: artifactId === discriminatorId ? ["A repeated clean window is required."] : [],
  typed_artifact: null,
  authority_ceiling: "observation_only",
});

const p32OpportunityEntry = (): CrewChiefEvidenceEntry => ({
  ...p35Entry(supportId, "support"),
  artifact_id: "opportunity-1",
  producer_id: "p32.performance_opportunity",
  lap_numbers: [7, 5],
  source_channels: ["lap_dist_pct", "speed_mph"],
});

afterEach(cleanup);

describe("VehicleDynamicsBlackboard", () => {
  it("renders the complete compact Learning-mode reasoning surface without setup authority", () => {
    const value = assessment();
    render(<VehicleDynamicsBlackboard
      assessment={value}
      evidenceEntries={[
        p32OpportunityEntry(),
        p35Entry(supportId, "support"),
        p35Entry(contradictionId, "contradiction"),
        p35Entry(discriminatorId, "neutral"),
      ]}
      p19Next="Acquire one clean repeated center window."
      onFocusEvidence={vi.fn()}
    />);

    const board = screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only");
    expect(board.getAttribute("data-ui-state")).toBe("ready");
    expect(within(board).getByText("Candidate review")).toBeTruthy();
    expect(within(board).getByText("reviewed build · graph applicable · observation only")).toBeTruthy();
    expect(within(board).queryByText("ready · no setup authority")).toBeNull();
    expect(within(board).getByText(/1 candidate has typed support/i)).toBeTruthy();
    const chain = within(board).getByRole("list", {
      name: "Five-stage vehicle dynamics evidence chain",
    });
    expect(within(chain).getAllByRole("listitem")).toHaveLength(5);
    for (const heading of [
      "Five-stage evidence chain",
      "Performance problem",
      "Driver demand",
      "Vehicle response",
      "Tire demand",
      "Load transfer / platform",
      "Transient or steady-state?",
      "Mechanism candidates",
      "Component families",
      "Strongest support",
      "Strongest contradiction",
      "Next bounded inspection",
      "NEXT · P19",
    ]) expect(within(board).getByRole("heading", { name: heading })).toBeTruthy();
    expect(within(board).getByText("Acquire one clean repeated center window.")).toBeTruthy();
    expect(within(board).getByText(/Static candidate map only; current P26 relevance remains unproven; zero component causal claims/)).toBeTruthy();
    expect(within(board).getByText(/candidate relevance only/i)).toBeTruthy();
    expect(within(board).getByText(/zero component causal claims/i)).toBeTruthy();
    expect(within(board).getByText(/exact wheel load remains unavailable/i)).toBeTruthy();
    expect(within(board).getByText("front tire demand")).toBeTruthy();
    expect(within(board).queryByText(/mechanism front tire demand/i)).toBeNull();
    expect(within(board).getByText("Measured comparison · laps 7, 5 · center · 42.5–51.5%")).toBeTruthy();
    expect(within(board).queryByText(/opportunity 1/i)).toBeNull();
    expect(within(chain).getAllByText(/\+2 more/)).toHaveLength(5);
    const channelDisclosures = board.querySelectorAll("details.vehicle-dynamics-channels");
    expect(channelDisclosures).toHaveLength(5);
    fireEvent.click(within(channelDisclosures[0] as HTMLElement).getByText(/\+2 more/));
    expect(channelDisclosures[0].hasAttribute("open")).toBe(true);
    expect(within(channelDisclosures[0] as HTMLElement).getByText(/^Channels: steering_angle_deg/)).toBeTruthy();
    expect(within(board).getByText("Inspection")).toBeTruthy();
    expect(within(board).getByText("roll response")).toBeTruthy();
    expect(within(board).getByText("Current source context")).toBeTruthy();
    expect(within(board).getByText("Evidence scope")).toBeTruthy();
    expect(within(board).getByText("Current blocker")).toBeTruthy();
    expect(within(board).queryByText("Signals")).toBeNull();
    expect(within(board).queryByText("Condition")).toBeNull();
    expect(within(board).getByText("A repeated clean window is required.")).toBeTruthy();
    expect(within(board).getByRole("heading", { name: "Strongest contradiction" })).toBeTruthy();
    expect(within(board).getByText("A current response contradiction remains visible.")).toBeTruthy();
    const sourceContextDisclosure = board.querySelector(
      "details.vehicle-dynamics-source-context",
    );
    expect(sourceContextDisclosure).toBeTruthy();
    expect(within(sourceContextDisclosure as HTMLElement).getByText(
      "steering_angle_deg, yaw_rate_deg_s, speed_mph · +2 more",
    )).toBeTruthy();
    fireEvent.click(within(sourceContextDisclosure as HTMLElement).getByText(/\+2 more/));
    expect(sourceContextDisclosure?.hasAttribute("open")).toBe(true);
    expect(within(sourceContextDisclosure as HTMLElement).getByText(
      "steering_angle_deg, yaw_rate_deg_s, speed_mph, lat_accel_g, long_accel_g",
    )).toBeTruthy();
    expect(within(board).getByLabelText("Vehicle dynamics authority boundary")).toBeTruthy();
    expect(within(board).queryByText(/increase|decrease|set .*spring/i)).toBeNull();
  });

  it("routes support, contradiction, and discriminator through exact evidence entries", () => {
    const entries = [
      p35Entry(supportId, "support"),
      p35Entry(contradictionId, "contradiction"),
      p35Entry(discriminatorId, "neutral"),
    ];
    const onFocusEvidence = vi.fn();
    render(<VehicleDynamicsBlackboard
      assessment={assessment()}
      evidenceEntries={entries}
      p19Next="Acquire one clean repeated center window."
      onFocusEvidence={onFocusEvidence}
    />);

    fireEvent.click(screen.getByRole("button", {
      name: "Open support evidence · lap 7 · center · 42.5–51.5%",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "Open contradiction evidence · lap 7 · center · 42.5–51.5%",
    }));
    fireEvent.click(screen.getByRole("button", {
      name: "Open discriminator evidence · lap 7 · center · 42.5–51.5%",
    }));

    expect(onFocusEvidence).toHaveBeenNthCalledWith(1, entries[0]);
    expect(onFocusEvidence).toHaveBeenNthCalledWith(2, entries[1]);
    expect(onFocusEvidence).toHaveBeenNthCalledWith(3, entries[2]);
  });

  it("uses plural agreement when more than one candidate has typed support", () => {
    const value = assessment();
    value.candidates = [
      ...value.candidates,
      {
        ...value.candidates[0],
        mechanism_id: "mechanism:rear_tire_demand",
        component_family_ids: ["component_family:rear_roll"],
      },
    ];

    render(<VehicleDynamicsBlackboard
      assessment={value}
      evidenceEntries={[]}
      p19Next="Acquire one clean repeated center window."
      onFocusEvidence={vi.fn()}
    />);

    const board = screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only");
    expect(within(board).getByText(/2 candidates have typed support/i)).toBeTruthy();
    expect(within(board).queryByText(/2 candidates has typed support/i)).toBeNull();
  });

  it("makes traffic-blocked attribution unmistakable while retaining measured time and navigation", () => {
    const value = assessment();
    value.traffic_blocked = true;
    value.blocker_reasons = ["No compatible prior run exists."];
    value.chain = value.chain.map((stage) => stage.stage === "vehicle_response"
      ? {
        ...stage,
        evidence_state: "unavailable",
        source_artifact_ids: [],
        source_channels: [],
        blocker_reasons: ["Driver-demand response is unavailable."],
      }
      : stage);
    value.candidates = value.candidates.map((candidate) => ({
      ...candidate,
      relevance: "blocked",
      support_artifact_ids: [],
      blocker_reasons: ["Traffic exposure covered the comparison window."],
    }));
    value.focus_artifacts = value.focus_artifacts.filter(
      (focus) => focus.artifact_id !== supportId,
    ).map((focus) => focus.artifact_id === contradictionId
      ? {
        ...focus,
        polarity: "uncertainty",
        summary: "Strongest contradiction or uncertainty: Traffic prevents attribution.",
      }
      : focus);
    value.strongest_support_artifact_id = null;

    render(<VehicleDynamicsBlackboard
      assessment={value}
      evidenceEntries={[
        p35Entry(contradictionId, "contradiction"),
        p35Entry(discriminatorId, "neutral"),
      ]}
      p19Next="Acquire one clean repeated center window."
      onFocusEvidence={vi.fn()}
    />);

    const board = screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only");
    expect(board.getAttribute("data-ui-state")).toBe("blocked");
    expect(within(board).getByText("Attribution blocked")).toBeTruthy();
    expect(within(board).getByRole("heading", {
      name: "Measured time, attribution blocked",
    })).toBeTruthy();
    expect(within(board).queryByRole("heading", {
      name: /Observed response, attribution blocked/i,
    })).toBeNull();
    expect(within(board).getByText("reviewed build · graph applicable · observation only")).toBeTruthy();
    expect(within(board).queryByText("ready · no setup authority")).toBeNull();
    expect(within(board).getByText("Traffic exposure covered the comparison window.")).toBeTruthy();
    expect(within(board).queryByText("No compatible prior run exists.")).toBeNull();
    expect(within(board).getByText("Measured time consequence retained.")).toBeTruthy();
    expect(within(board).getByText("No typed focus artifact cleared this role.")).toBeTruthy();
    expect(within(board).queryByRole("button", { name: /Open support evidence/ })).toBeNull();
    expect(within(board).getByRole("heading", { name: "Strongest uncertainty" })).toBeTruthy();
    expect(within(board).getByText("Traffic prevents attribution.")).toBeTruthy();
    expect(within(board).queryByText(/Strongest contradiction or uncertainty:/i)).toBeNull();
    expect(within(board).getByRole("button", { name: /Open uncertainty evidence/ })).toBeTruthy();
    expect(within(board).queryByRole("button", { name: /Open contradiction evidence/ })).toBeNull();
    expect(within(board).getByRole("button", { name: /Open discriminator evidence/ })).toBeTruthy();
    expect(within(board).getByText("Static possibility map · not current attribution")).toBeTruthy();
    expect(within(board).getByText(
      "Every candidate is blocked; current P26 relevance and component causation remain unproven.",
    )).toBeTruthy();
    expect(within(board).getAllByText(
      "Static possibility map · not current attribution",
    )).toHaveLength(1);
  });

  it("distinguishes an empty candidate set from an unavailable assessment", () => {
    const empty = assessment();
    empty.candidates = [];
    empty.focus_artifacts = [];
    empty.strongest_support_artifact_id = null;
    empty.strongest_contradiction_artifact_id = null;
    empty.next_discriminator_contract_id = null;

    const { rerender } = render(<VehicleDynamicsBlackboard
      assessment={empty}
      evidenceEntries={[]}
      p19Next="Retain the current P19 decision."
      onFocusEvidence={vi.fn()}
    />);

    let board = screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only");
    expect(board.getAttribute("data-ui-state")).toBe("empty");
    expect(within(board).getByText("No candidate cleared")).toBeTruthy();
    expect(within(board).getByRole("heading", {
      name: "Measured time, no mechanism candidate",
    })).toBeTruthy();
    expect(within(board).queryByRole("heading", { name: /Observed chain/i })).toBeNull();
    expect(within(board).getByText(/Measured P32 time remains visible/i)).toBeTruthy();
    expect(within(board).getByText("0 candidates")).toBeTruthy();
    expect(within(board).queryAllByRole("button")).toHaveLength(0);

    const noTime: PerformanceMechanismAssessment = {
      ...empty,
      performance_opportunity_ids: [],
      measured_time_consequence_available: false,
      response_regime: null,
      tire_demand_state_ids: [],
      load_path_ids: [],
      chain: empty.chain.map((stage) => ({
        ...stage,
        evidence_state: "unavailable",
        source_artifact_ids: [],
        source_channels: [],
        blocker_reasons: ["The current iRacing build has not been reviewed."],
      })),
    };
    rerender(<VehicleDynamicsBlackboard
      assessment={noTime}
      evidenceEntries={[]}
      p19Next="Retain the current P19 decision."
      onFocusEvidence={vi.fn()}
    />);

    board = screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only");
    expect(board.getAttribute("data-ui-state")).toBe("empty");
    expect(within(board).getByRole("heading", { name: "No mechanism candidate" })).toBeTruthy();
    expect(within(board).queryByRole("heading", { name: /Observed chain/i })).toBeNull();

    const unavailable: PerformanceMechanismAssessment = {
      ...noTime,
      applicability_state: "unreviewed_build",
      applicability_blockers: ["The current iRacing build has not been reviewed."],
    };
    rerender(<VehicleDynamicsBlackboard
      assessment={unavailable}
      evidenceEntries={[]}
      p19Next="Retain the current P19 decision."
      onFocusEvidence={vi.fn()}
    />);

    board = screen.getByLabelText("Vehicle Dynamics Blackboard, candidate mechanisms only");
    expect(board.getAttribute("data-ui-state")).toBe("unavailable");
    expect(within(board).getByRole("heading", {
      name: "Vehicle dynamics assessment unavailable",
    })).toBeTruthy();
    expect(within(board).queryByRole("heading", { name: /Observed chain/i })).toBeNull();
    expect(within(board).getAllByText("unreviewed build").length).toBeGreaterThan(0);
    expect(within(board).getByText("The current iRacing build has not been reviewed.")).toBeTruthy();
    expect(within(board).getAllByText("channels unavailable")).toHaveLength(5);
    expect(within(board).queryAllByRole("button")).toHaveLength(0);
  });

  it("pins the Learning slice through the common narrow-shell range and stacks dense evidence", () => {
    expect(styles).toContain("@media (max-width: 640px)");
    expect(styles).not.toContain("@media (max-width: 390px)");
    expect(styles).toContain(".crew-chief-deck:has(.vehicle-dynamics-blackboard)");
    expect(styles).toContain(".crew-chief-learning:has(> .vehicle-dynamics-blackboard) > *");
    expect(styles).toContain(".performance-ribbon button");
    expect(styles).toMatch(/\.crew-chief-deck:has\(\.vehicle-dynamics-blackboard\)[\s\S]*?min-width: 0;/);
    expect(styles).not.toMatch(/\.crew-chief-deck:has\(\.vehicle-dynamics-blackboard\)\s*\{[^}]*overflow:\s*hidden/);
    expect(styles).toMatch(/\.vehicle-dynamics-chain,[\s\S]*?grid-template-columns: 1fr;/);
    expect(styles).toMatch(/\.vehicle-dynamics-focus \.vehicle-dynamics-focus-scope[\s\S]*?white-space: normal;/);
  });
});
