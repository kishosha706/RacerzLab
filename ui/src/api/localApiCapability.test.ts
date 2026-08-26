import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock("@tauri-apps/api/core", () => ({ invoke: invokeMock }));

const CAPABILITY_TOKEN = "a7".repeat(32);

function setTauri(enabled: boolean): void {
  if (enabled) {
    Object.defineProperty(window, "__TAURI_INTERNALS__", {
      configurable: true,
      value: {},
    });
    return;
  }
  Reflect.deleteProperty(window, "__TAURI_INTERNALS__");
}

beforeEach(() => {
  vi.resetModules();
  invokeMock.mockReset();
});

afterEach(() => {
  setTauri(false);
  vi.unstubAllGlobals();
});

describe("local API capability propagation", () => {
  it("lazily obtains one shell token and sends it on every shared-client request", async () => {
    setTauri(true);
    invokeMock.mockResolvedValue(CAPABILITY_TOKEN);
    const fetchMock = vi.fn().mockImplementation(
      async () => new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { requestJson } = await import("./client");

    expect(invokeMock).not.toHaveBeenCalled();
    await requestJson("/api/capability-test-one", { method: "POST" });
    await requestJson("/api/capability-test-two", { method: "POST" });

    expect(invokeMock).toHaveBeenCalledTimes(1);
    expect(invokeMock).toHaveBeenCalledWith("backend_capability_token");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const [, init] of fetchMock.mock.calls as Array<[string, RequestInit]>) {
      expect(new Headers(init.headers).get("X-RacerZLab-Capability"))
        .toBe(CAPABILITY_TOKEN);
    }
  });

  it("preserves browser development requests when there is no Tauri shell", async () => {
    setTauri(false);
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { requestJson } = await import("./client");

    await requestJson("/api/browser-test", { method: "POST" });

    expect(invokeMock).not.toHaveBeenCalled();
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(init.headers).has("X-RacerZLab-Capability")).toBe(false);
  });

  it("fails closed before fetch when the shell returns a malformed token", async () => {
    setTauri(true);
    invokeMock.mockResolvedValue("not-a-32-byte-token");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { requestJson } = await import("./client");

    await expect(requestJson("/api/rejected", { method: "POST" }))
      .rejects.toThrow("Desktop API capability is unavailable.");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
