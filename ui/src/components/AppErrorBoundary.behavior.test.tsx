import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "./AppErrorBoundary";

function ThrowingChild({ message = "simulated shell failure" }: { message?: string }): never {
  throw new Error(message);
}

function HealthyChild() {
  return <p>workspace rendered</p>;
}

/** React logs caught boundary errors to console.error; keep test output clean. */
function silenceBoundaryLogging(): void {
  vi.spyOn(console, "error").mockImplementation(() => {});
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AppErrorBoundary whole-shell recovery", () => {
  it("renders children unchanged when the shell is healthy", () => {
    render(
      <AppErrorBoundary>
        <HealthyChild />
      </AppErrorBoundary>,
    );
    expect(screen.getByText("workspace rendered")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("contains a shell render throw and reports the exact message", () => {
    silenceBoundaryLogging();
    render(
      <AppErrorBoundary>
        <ThrowingChild message="provider exploded" />
      </AppErrorBoundary>,
    );
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("could not render this screen");
    expect(screen.getByText("provider exploded")).toBeTruthy();
  });

  it("states that telemetry and engineering history were not modified", () => {
    silenceBoundaryLogging();
    render(
      <AppErrorBoundary>
        <ThrowingChild />
      </AppErrorBoundary>,
    );
    expect(screen.getByText(/telemetry, setups, and engineering history were not modified/i))
      .toBeTruthy();
  });

  it("offers reload and retry, and never offers a decision action", () => {
    silenceBoundaryLogging();
    render(
      <AppErrorBoundary>
        <ThrowingChild />
      </AppErrorBoundary>,
    );
    expect(screen.getByRole("button", { name: /Reload RacerZLab/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Try rendering again/ })).toBeTruthy();
    // A crash surface must not manufacture setup authority.
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/apply|recommend|keep\b|undo\b|retest/i);
  });

  it("hides technical detail until the driver asks for it", async () => {
    silenceBoundaryLogging();
    render(
      <AppErrorBoundary>
        <ThrowingChild message="hidden detail probe" />
      </AppErrorBoundary>,
    );
    expect(screen.queryByText(/RacerZLab shell error report/)).toBeNull();
    screen.getByRole("button", { name: /Show technical detail/ }).click();
    expect(await screen.findByText(/RacerZLab shell error report/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Hide technical detail/ })).toBeTruthy();
  });

  it("recovers the shell when a retry succeeds", async () => {
    silenceBoundaryLogging();
    let shouldThrow = true;
    function Flaky() {
      if (shouldThrow) throw new Error("transient failure");
      return <p>recovered workspace</p>;
    }
    render(
      <AppErrorBoundary>
        <Flaky />
      </AppErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeTruthy();
    shouldThrow = false;
    screen.getByRole("button", { name: /Try rendering again/ }).click();
    expect(await screen.findByText("recovered workspace")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("reloads the desktop window when the driver chooses reload", () => {
    silenceBoundaryLogging();
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload, href: "http://127.0.0.1:5173/" },
    });
    render(
      <AppErrorBoundary>
        <ThrowingChild />
      </AppErrorBoundary>,
    );
    screen.getByRole("button", { name: /Reload RacerZLab/ }).click();
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
