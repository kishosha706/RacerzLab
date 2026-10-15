import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HandlingInvestigationPanel } from "./HandlingInvestigationPanel";

const mockSetWorkspace = vi.fn();
const mockFocusEvidence = vi.fn();

vi.mock("../store/EngineeringCaseContext", () => ({
  useEngineeringCase: () => ({
    engineeringCase: {
      case_id: "p3543case_" + "f".repeat(24),
      case_revision_sha256: "a".repeat(64),
      case_sha256: "b".repeat(64),
      run_id: "run-1",
      session_id: "session-1",
      setup_id: "setup-1",
      handling_investigation: projection(),
    },
    revision: null,
    status: "ready",
    error: null,
    retry: vi.fn(),
  }),
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: { selectedMode: "learning", selectedRunId: "run-1" },
    setWorkspace: mockSetWorkspace,
    focusEvidence: mockFocusEvidence,
  }),
}));

function projection(): import("../types/openapi.generated").components["schemas"]["HandlingInvestigationProjection"] {
  return {
    schema_version: "p356.handling-investigation.v1",
    projection_sha256: "a".repeat(64),
    run_id: "run-1",
    session_id: "session-1",
    setup_id: "setup-1",
    handling_report_classification: "rotation_response_deficit",
    assessment_refs: [{
      assessment_id: "hba_" + "1".repeat(24),
      run_id: "run-1",
      phase: "center",
      classification: "rotation_response_deficit",
      canonical_symptom_id: "tight_center",
      corroborated: true,
      lap_numbers: [1, 2, 3, 4, 5, 6],
    }],
    evidence_dependence: [
      "The strands share path curvature and the run-local reference group; they are not statistically independent evidence.",
      "A run-local reference cannot detect a uniform balance offset.",
    ],
    findings: [{
      assessment_id: "hba_" + "1".repeat(24),
      phase: "center",
      what: "Corroborated reduced rotation response.",
      where: "center across 6 eligible laps (laps 1-6)",
      driver: "Steering demand per achieved curvature was elevated relative to the run-local reference.",
      response: "Median kinematic residual +0.0300 rad/s against the path-kinematic reference.",
      mechanisms: [{
        mechanism_id: "mechanism:center_rotation_deficit",
        label: "Center rotation deficit",
        relevance: "informed_by_observation",
        response_regime: "steady_state",
        applicable_phases: ["center"],
        direction: "deficit_aligned",
        discriminator_contract_ids: ["observation:settled_center_rotation:separate_driver_from_vehicle"],
        p26_component_family_ids: ["anti_roll_bars", "springs"],
        required_channels: ["steering_deg", "yaw_rate"],
        missing_evidence: [],
        support_declared: false,
      }],
      components: [{
        component_id: "anti_roll_bars",
        relevance: "observable",
        observability_states: ["live_response_observable"],
        source: "p26_component_awareness",
        malfunction_declared: false,
      }],
      performance: [{
        opportunity_id: "p32o-opportunity",
        track_region: "Turn 1",
        phase: "center",
        measured_delta_s: 0.12,
        repeatability: "repeatable",
        attribution_state: "candidate_only",
        wording: "The center handling observation co-occurs with a repeatable measured time loss of +0.120 s in Turn 1. This is a co-occurrence; it does not establish that the observation caused the loss or that any component did.",
        causation_declared: false,
      }],
      contradictions: ["The reference is actual-path curvature, not the driver's intended path."],
      uncertain: ["Mechanical cause unresolved: no mechanism is declared supported by this observation."],
      next: "Review matched steering and yaw traces across the qualified lap group.",
      next_evidence_channels: ["steering_deg", "yaw_rate"],
    }],
    authority: "derived_observation_view",
    setup_authorized: false,
    p19_authority_unchanged: true,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HandlingInvestigationPanel unified investigation", () => {
  it("renders the full derived investigation in Learning mode", async () => {
    render(<HandlingInvestigationPanel runId="run-1" sessionId="session-1" learning />);
    expect(await screen.findByText(/center_rotation_deficit/)).toBeTruthy();
    expect(screen.getByText(/Mechanical cause unresolved/)).toBeTruthy();
    expect(screen.getByText(/co-occurs with a repeatable measured time loss/)).toBeTruthy();
    expect(screen.getByText(/No mechanism is declared supported/)).toBeTruthy();
    expect(screen.getByText(/not statistically independent evidence/)).toBeTruthy();
    expect(screen.getByText(/never authorizes a setup change/)).toBeTruthy();
  });

  it("shows the concise race-mode line without the learning sections", () => {
    render(<HandlingInvestigationPanel runId="run-1" sessionId="session-1" learning={false} />);
    expect(screen.getByText(/CENTER ROTATION/)).toBeTruthy();
    expect(screen.getByText(/Mechanical cause unresolved/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Review matched traces/ })).toBeTruthy();
    expect(screen.queryByText(/No mechanism is declared supported/)).toBeNull();
  });

  it("renders nothing when the case does not match the requested scope", () => {
    render(<HandlingInvestigationPanel runId="run-other" sessionId="session-1" learning />);
    expect(screen.queryByText(/CENTER ROTATION/)).toBeNull();
    expect(screen.queryByText(/No mechanism is declared supported/)).toBeNull();
  });

  it("hands the exact case identity to Dial-In without fabricating driver wording", () => {
    try {
      window.sessionStorage.clear();
    } catch {
      return;
    }
    render(<HandlingInvestigationPanel runId="run-1" sessionId="session-1" learning />);
    fireEvent.click(screen.getByRole("button", { name: /Dial-In knowledge/ }));
    expect(mockSetWorkspace).toHaveBeenCalledWith("dial_in", "engineer");
    const raw = window.sessionStorage.getItem("racerzlab:handling-observation-handoff:session-1");
    expect(raw).not.toBeNull();
    const handoff = JSON.parse(raw ?? "null") as Record<string, unknown>;
    expect(handoff.runId).toBe("run-1");
    expect(handoff.sessionId).toBe("session-1");
    expect(handoff.assessmentId).toBe("hba_" + "1".repeat(24));
    expect(handoff.phase).toBe("center");
    expect(handoff.canonicalSymptomId).toBe("tight_center");
    expect(handoff.caseId).toBe("p3543case_" + "f".repeat(24));
    expect(handoff.caseRevision).toBe("a".repeat(64));
    expect(handoff.caseSha256).toBe("b".repeat(64));
  });

  it("deep-links the qualified lap window from a finding", () => {
    render(<HandlingInvestigationPanel runId="run-1" sessionId="session-1" learning />);
    fireEvent.click(screen.getByRole("button", { name: /Review laps/ }));
    const evidence = mockFocusEvidence.mock.calls[0];
    expect(evidence[0].lapScope).toBe("lap_window");
    expect(evidence[0].lapWindowStart).toBe(1);
    expect(evidence[0].lapWindowEnd).toBe(6);
    expect(evidence[0].zoneLabel).toBe("center");
    expect(evidence[1]).toBe("laps");
  });

  it("focuses setup relevance with the exact case identity", () => {
    render(<HandlingInvestigationPanel runId="run-1" sessionId="session-1" learning />);
    fireEvent.click(screen.getByRole("button", { name: /Setup relevance/ }));
    const evidence = mockFocusEvidence.mock.calls[0];
    expect(evidence[0].caseId).toBe("p3543case_" + "f".repeat(24));
    expect(evidence[0].caseRevision).toBe("a".repeat(64));
    expect(evidence[0].caseSha256).toBe("b".repeat(64));
    expect(evidence[0].mechanismIds).toContain("mechanism:center_rotation_deficit");
    expect(evidence[0].componentIds).toContain("anti_roll_bars");
    expect(evidence[1]).toBe("setup_impact");
  });

  it("renders the compact overview status card", () => {
    render(
      <HandlingInvestigationPanel
        runId="run-1"
        sessionId="session-1"
        learning
        surface="overview"
      />,
    );
    expect(screen.getByText(/HANDLING INVESTIGATION/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Open investigation/ })).toBeTruthy();
    expect(screen.queryByText(/No mechanism is declared supported/)).toBeNull();
  });
});
