import { render, screen } from "@testing-library/react";
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

afterEach(() => {
  vi.clearAllMocks();
});

describe("CrewChiefCommandDeck boundary states", () => {
  it("withholds the decision while exact evidence identities are being bound", () => {
    api.fetchCrewChiefWorkspace.mockReturnValue(new Promise(() => {}));
    const { container } = render(<CrewChiefCommandDeck {...props} />);

    expect(container.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.getByText("Binding current evidence")).toBeTruthy();
    expect(screen.getByText(/P19, P20, P26, and P32 identities/)).toBeTruthy();
  });

  it("renders a fail-closed empty boundary when workspace trust rejects", async () => {
    api.fetchCrewChiefWorkspace.mockRejectedValue(new Error("Workspace identity mismatch."));
    render(<CrewChiefCommandDeck {...props} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Crew Chief withheld");
    expect(alert.textContent).toContain("Workspace identity mismatch.");
  });
});
