import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { EngineeringCaseRevision } from "../types/engineeringCase";
import {
  EngineeringCaseProvider,
  useEngineeringCase,
} from "./EngineeringCaseContext";

const api = vi.hoisted(() => ({ fetchEngineeringCase: vi.fn() }));
vi.mock("../api/client", () => ({ fetchEngineeringCase: api.fetchEngineeringCase }));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function revision(
  number: number,
  sha: string,
  options?: { previousSha?: string | null; objective?: string },
): EngineeringCaseRevision {
  return {
    schema_version: "p3544.engineering-case-revision.v1",
    case_id: `p3543case_${"a".repeat(24)}`,
    case_revision: number,
    case_sha256: sha,
    previous_case_sha256: number === 1 ? null : options?.previousSha ?? "b".repeat(64),
    created_at: "2026-08-20T00:00:00Z",
    change_category: number === 1 ? "initial" : "driver_intent",
    source_workspace_revision: "c".repeat(64),
    delivery_diagnostics: null,
    case: {
      run_id: "run-1",
      session_id: "session-1",
      case_id: `p3543case_${"a".repeat(24)}`,
      case_sha256: sha,
      objective_id: options?.objective ?? "race_long_run",
      mission: { next: `Move ${number}` },
    } as EngineeringCaseRevision["case"],
  };
}

let replacement: ((value: EngineeringCaseRevision) => void) | null = null;
let invalidate: (() => void) | null = null;
let selectObjective: ((objective: "qualifying_peak") => void) | null = null;

function Consumer() {
  const value = useEngineeringCase();
  replacement = value.replaceRevision;
  invalidate = value.invalidate;
  selectObjective = value.selectObjective;
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

  it("accepts only the exact successor and rejects competing or older revisions", async () => {
    api.fetchEngineeringCase.mockResolvedValueOnce(revision(1, "b".repeat(64)));
    render(
      <EngineeringCaseProvider runId="run-1" sessionId="session-1">
        <Consumer />
      </EngineeringCaseProvider>,
    );
    await waitFor(() => expect(screen.getByText("1:Move 1")).toBeTruthy());

    act(() => replacement?.(revision(2, "d".repeat(64))));
    expect(screen.getByText("2:Move 2")).toBeTruthy();
    act(() => replacement?.(revision(2, "e".repeat(64))));
    act(() => replacement?.(revision(1, "b".repeat(64))));
    expect(screen.getByText("2:Move 2")).toBeTruthy();
  });

  it("does not let a delayed mutation cancel an in-flight refresh", async () => {
    api.fetchEngineeringCase.mockResolvedValueOnce(revision(1, "b".repeat(64)));
    let resolveRefresh: ((value: EngineeringCaseRevision) => void) | null = null;
    api.fetchEngineeringCase.mockImplementationOnce(() => new Promise((resolve) => {
      resolveRefresh = resolve;
    }));
    render(
      <EngineeringCaseProvider runId="run-1" sessionId="session-1">
        <Consumer />
      </EngineeringCaseProvider>,
    );
    await waitFor(() => expect(screen.getByText("1:Move 1")).toBeTruthy());
    act(() => invalidate?.());
    await waitFor(() => expect(screen.getByText("loading")).toBeTruthy());
    act(() => replacement?.(revision(2, "d".repeat(64))));
    act(() => resolveRefresh?.(revision(2, "d".repeat(64))));
    await waitFor(() => expect(screen.getByText("2:Move 2")).toBeTruthy());
  });

  it("reloads the shared case when the engineering objective changes", async () => {
    api.fetchEngineeringCase
      .mockResolvedValueOnce(revision(1, "b".repeat(64)))
      .mockResolvedValueOnce(revision(2, "d".repeat(64), {
        previousSha: "b".repeat(64),
        objective: "qualifying_peak",
      }));
    render(
      <EngineeringCaseProvider runId="run-1" sessionId="session-1">
        <Consumer />
      </EngineeringCaseProvider>,
    );
    await waitFor(() => expect(screen.getByText("1:Move 1")).toBeTruthy());
    act(() => selectObjective?.("qualifying_peak"));
    await waitFor(() => expect(screen.getByText("2:Move 2")).toBeTruthy());
    expect(api.fetchEngineeringCase).toHaveBeenLastCalledWith(
      "run-1",
      "session-1",
      { objective: "qualifying_peak" },
    );
  });
});
