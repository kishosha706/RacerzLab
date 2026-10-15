import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HandlingBalancePanel } from "./HandlingBalancePanel";

vi.mock("../api/client", () => ({
  fetchHandlingBalance: vi.fn(),
}));

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: { selectedMode: "learning", selectedRunId: "run-1" },
    setWorkspace: vi.fn(),
    focusEvidence: vi.fn(),
  }),
}));

import { fetchHandlingBalance } from "../api/client";

const fetchMock = vi.mocked(fetchHandlingBalance);

function qualifiedReport(overrides: Record<string, unknown> = {}): import("../types/openapi.generated").components["schemas"]["HandlingBalanceReport"] {
  return {
    schema_version: "p-handling-balance.report.v2",
    run_id: "run-1",
    selected_lap: 4,
    eligible_laps: 6,
    reference_lap_count: 6,
    classification: "rotation_response_deficit",
    assessments: [{
      schema_version: "p-handling-balance.assessment.v2",
      assessment_id: "hba_000000000000000000000000",
      run_id: "run-1",
      lap_numbers: [2, 3, 4],
      phase: "center",
      classification: "rotation_response_deficit",
      canonical_symptom_id: "tight_center",
      observation_text: "Reduced rotation response repeats in center across 3 eligible laps.",
      evidence_state: "observed_correlation",
      confidence_score: 0.5,
      repeatability: "3/3 laps beyond the run-local noise envelope",
      source_channels: ["lap_dist_pct_100", "speed_mps", "yaw_rate", "steering_rad"],
      supporting_evidence: [
        "Median signed rotation-response deficit +0.0450 rad/s.",
        "Canonical symptom association tight_center is telemetry-observed; it is not driver testimony.",
      ],
      contradicting_evidence: [
        "The reference is actual-path curvature, not the driver's intended path.",
      ],
      phase_observations: [{
        phase: "center",
        eligible_laps: 6,
        sample_bins: 120,
        steering_demand_floor_deg: 3.0,
        coverage_fraction: 0.95,
        corroboration: {
          kinematic_residual_strand_qualified: true,
          steering_response_strand_qualified: true,
          steering_response_direction: "elevated",
          aligned: true,
          corroborated: true,
          shared_input_channels: ["curvature_1_per_m"],
          shared_reference_laps: true,
          independence_qualification: "The strands share curvature and the reference group; they are not statistically independent evidence.",
        },
      }],
      authority: "observation_only",
      setup_authorized: false,
      driver_feedback_source: false,
    }],
    conclusions: [],
    gate: { contract_key: "automatic_handling_balance", eligible: true, confidence_cap: 0.7, blocker_reasons: [], needed_measurements: [] },
    warnings: [],
    authority: "observation_only",
    setup_authorized: false,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("HandlingBalancePanel observation-only contract", () => {
  it("renders qualified phase observations with the canonical symptom in Learning mode", async () => {
    fetchMock.mockResolvedValue(qualifiedReport());
    render(<HandlingBalancePanel runId="run-1" />);
    expect(await screen.findByText(/Reduced rotation response repeats in center/)).toBeTruthy();
    expect(screen.getAllByText(/Canonical symptom/).length).toBeGreaterThan(0);
    expect(screen.getByText(/telemetry-observed, not driver testimony/)).toBeTruthy();
    expect(screen.getAllByText("Observation only").length).toBeGreaterThan(0);
  });

  it("renders the residual-only diagnostic without a symptom claim", async () => {
    fetchMock.mockResolvedValue(qualifiedReport({
      classification: "kinematic_residual_observation",
      assessments: [{
        schema_version: "p-handling-balance.assessment.v2",
        assessment_id: "hba_000000000000000000000001",
        run_id: "run-1",
        lap_numbers: [1, 2, 3, 4, 5, 6],
        phase: "center",
        classification: "kinematic_residual_observation",
        canonical_symptom_id: null,
        observation_text: "A kinematic residual in center is reported across 6 eligible laps without steering-response corroboration.",
        evidence_state: "observed_correlation",
        confidence_score: 0.4,
        repeatability: "kinematic residual beyond the run-local envelope; steering response unaligned",
        source_channels: ["lap_dist_pct_100", "speed_mps", "yaw_rate", "steering_rad"],
        supporting_evidence: ["Median signed kinematic residual +0.0450 rad/s."],
        contradicting_evidence: ["Steering-response evidence does not corroborate the residual."],
        phase_observations: [{
          phase: "center",
          eligible_laps: 6,
          sample_bins: 120,
          steering_demand_floor_deg: 3.0,
          coverage_fraction: 0.95,
          corroboration: {
            kinematic_residual_strand_qualified: true,
            steering_response_strand_qualified: false,
            steering_response_direction: null,
            aligned: false,
            corroborated: false,
            shared_input_channels: ["curvature_1_per_m"],
            shared_reference_laps: true,
            independence_qualification: "The strands share curvature and the reference group; they are not statistically independent evidence.",
          },
        }],
        authority: "observation_only",
        setup_authorized: false,
        driver_feedback_source: false,
      }],
    }));
    render(<HandlingBalancePanel runId="run-1" />);
    expect(await screen.findByText(/without steering-response corroboration/)).toBeTruthy();
    expect(screen.queryByText(/Canonical symptom/)).toBeNull();
    expect(screen.getByText(/cannot establish tight or loose on its own/)).toBeTruthy();
  });

  it("renders no section while loading", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    const { container } = render(<HandlingBalancePanel runId="run-1" />);
    expect(container.querySelector(".handling-balance-panel")).toBeNull();
  });

  it("shows the error state only in Learning mode", async () => {
    fetchMock.mockRejectedValue(new Error("backend gone"));
    render(<HandlingBalancePanel runId="run-1" />);
    expect(await screen.findByText(/backend gone/)).toBeTruthy();
  });

  it("refetches when the run changes", async () => {
    fetchMock.mockResolvedValue(qualifiedReport());
    const { rerender } = render(<HandlingBalancePanel runId="run-1" />);
    await screen.findByText(/Reduced rotation response repeats in center/);
    rerender(<HandlingBalancePanel runId="run-2" />);
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("run-2"));
  });
});
