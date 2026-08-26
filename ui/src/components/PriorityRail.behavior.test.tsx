import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PriorityRail } from "./PriorityRail";

vi.mock("../store/TelemetrySelectionContext", () => ({
  useTelemetrySelection: () => ({
    selection: { selectedMode: "race" },
    setWorkspace: vi.fn(),
    focusEvidence: vi.fn(),
  }),
}));

describe("PriorityRail narrow modal contract", () => {
  it("exposes a real modal dialog, marks its isolation layer, and takes focus", async () => {
    render(
      <PriorityRail
        runId="run-1"
        selectedLap={4}
        platformEvents={[]}
        loadStatus="clear"
        eventVisibilityMode="actionable"
        modal
        onToggle={vi.fn()}
      />,
    );
    const dialog = screen.getByRole("dialog", { name: "Priority evidence" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("data-priority-modal-layer")).toBe("true");
    const close = screen.getByRole("button", { name: "Collapse Priority Rail" });
    await waitFor(() => expect(document.activeElement).toBe(close));
  });
});
