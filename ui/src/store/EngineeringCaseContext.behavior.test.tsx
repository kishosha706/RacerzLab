import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { EngineeringCaseRevision } from "../types/engineeringCase";
import {
  EngineeringCaseProvider,
  useEngineeringCase,
} from "./EngineeringCaseContext";

const api = vi.hoisted(() => ({ fetchEngineeringCase: vi.fn() }));
vi.mock("../api/client", () => ({ fetchEngineeringCase: api.fetchEngineeringCase }));

function revision(number: number, sha: string): EngineeringCaseRevision {
  return {
    schema_version: "p3544.engineering-case-revision.v1",
    case_id: `p3543case_${"a".repeat(24)}`,
    case_revision: number,
    case_sha256: sha,
    previous_case_sha256: number === 1 ? null : "b".repeat(64),
    created_at: "2026-08-20T00:00:00Z",
    change_category: number === 1 ? "initial" : "driver_intent",
    source_workspace_revision: "c".repeat(64),
    delivery_diagnostics: null,
    case: {
      run_id: "run-1",
      session_id: "session-1",
      case_id: `p3543case_${"a".repeat(24)}`,
      case_sha256: sha,
      mission: { next: `Move ${number}` },
    } as EngineeringCaseRevision["case"],
  };
}

let replacement: ((value: EngineeringCaseRevision) => void) | null = null;

function Consumer() {
  const value = useEngineeringCase();
  replacement = value.replaceRevision;
  return <output>{value.revision ? `${value.revision.case_revision}:${value.engineeringCase?.mission.next}` : value.status}</output>;
}

describe("EngineeringCaseProvider", () => {
  it("loads one exact current case and atomically replaces its revision", async () => {
    api.fetchEngineeringCase.mockResolvedValueOnce(revision(1, "b".repeat(64)));
    render(
      <EngineeringCaseProvider runId="run-1" sessionId="session-1">
        <Consumer />
      </EngineeringCaseProvider>,
    );
    await waitFor(() => expect(screen.getByText("1:Move 1")).toBeTruthy());
    expect(api.fetchEngineeringCase).toHaveBeenCalledTimes(1);

    act(() => replacement?.(revision(2, "d".repeat(64))));
    expect(screen.getByText("2:Move 2")).toBeTruthy();
  });

  it("rejects a mutation result from another run without mixing revisions", async () => {
    api.fetchEngineeringCase.mockResolvedValueOnce(revision(1, "b".repeat(64)));
    render(
      <EngineeringCaseProvider runId="run-1" sessionId="session-1">
        <Consumer />
      </EngineeringCaseProvider>,
    );
    await waitFor(() => expect(screen.getByText("1:Move 1")).toBeTruthy());
    const foreign = revision(2, "d".repeat(64));
    foreign.case.run_id = "run-foreign";
    act(() => replacement?.(foreign));
    expect(screen.getByText("1:Move 1")).toBeTruthy();
  });
});
