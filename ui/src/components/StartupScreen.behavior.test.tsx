import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StartupScreen } from "./StartupScreen";

const api = vi.hoisted(() => ({
  fetchSessions: vi.fn(),
  updateSession: vi.fn(),
  archiveSession: vi.fn(),
}));

vi.mock("../api/client", () => ({
  fetchSessions: api.fetchSessions,
  updateSession: api.updateSession,
  archiveSession: api.archiveSession,
  createSession: vi.fn(),
  deleteSession: vi.fn(),
}));

const session = {
  session_id: "session_alpha_123456",
  name: "Atlanta baseline",
  created_at: "2026-08-20T10:00:00Z",
  updated_at: "2026-08-20T11:00:00Z",
  track_name: "EchoPark Speedway",
  car_name: "NASCAR Chevrolet Camaro ZL1",
  run_ids: ["run-1"],
  last_opened_run_id: "run-1",
  last_selected_lap: 4,
  last_workspace: "engineer",
  notebook_finding_ids: [],
  status: "active" as const,
};

describe("StartupScreen session cohesion", () => {
  beforeEach(() => {
    localStorage.setItem("racerzlab.launchSplashDismissed.v1", "true");
    api.fetchSessions.mockResolvedValue([session]);
    api.updateSession.mockResolvedValue({ ...session, name: "Race trim" });
    api.archiveSession.mockResolvedValue({ ...session, status: "archived" });
  });

  it("searches, renames, and archives presentation metadata without changing identity", async () => {
    render(<StartupScreen onSessionSelected={vi.fn()} />);
    await screen.findByText("Atlanta baseline");
    expect(screen.getByText(/Created .* · Updated .* · 123456/)).toBeTruthy();

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Bristol" } });
    expect(screen.getByText("No sessions match this search.")).toBeTruthy();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Atlanta" } });

    fireEvent.click(screen.getByRole("button", { name: /Rename session Atlanta baseline/ }));
    fireEvent.change(screen.getByLabelText("Rename Atlanta baseline"), { target: { value: "Race trim" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.updateSession).toHaveBeenCalledWith(session.session_id, { name: "Race trim" }));

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /Archive session Race trim/ }));
    await waitFor(() => expect(api.archiveSession).toHaveBeenCalledWith(session.session_id));
    expect(api.updateSession.mock.calls[0][0]).toBe(session.session_id);
  });
});
