import { afterEach, describe, expect, it, vi } from "vitest";

import {
  BackendReadinessError,
  fetchBackendHealth,
} from "./backendHealth";


afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchBackendHealth", () => {
  it("returns only a validated healthy RacerZLab response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "ok",
      app: "RacerZLab",
      version: "0.1.0",
      instance_id: "owned-instance",
    }), { status: 200 })));

    await expect(fetchBackendHealth()).resolves.toMatchObject({
      status: "ok",
      instance_id: "owned-instance",
    });
  });

  it("preserves a validated typed storage failure for startup recovery", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "unavailable",
      app: "RacerZLab",
      version: "0.1.0",
      instance_id: "owned-instance",
      readiness_code: "database_unavailable",
      recovery_code: "restart_or_restore_local_storage",
    }), { status: 503 })));

    const error = await fetchBackendHealth().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(BackendReadinessError);
    expect(error).toMatchObject({
      instanceId: "owned-instance",
      failure: {
        readinessCode: "database_unavailable",
        recoveryCode: "restart_or_restore_local_storage",
      },
    });
  });

  it("does not forward untyped backend detail or local paths", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "unavailable",
      app: "RacerZLab",
      version: "0.1.0",
      readiness_code: "unknown_failure",
      recovery_code: "C:\\Users\\private\\telemetry",
    }), { status: 503 })));

    const error = await fetchBackendHealth().catch((caught: unknown) => caught);

    expect(error).not.toBeInstanceOf(BackendReadinessError);
    expect((error as Error).message).toBe("Local engine health check failed (503).");
    expect((error as Error).message).not.toContain("private");
  });
});
