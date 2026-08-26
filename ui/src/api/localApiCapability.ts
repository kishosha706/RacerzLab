import { isTauri } from "../utils/env";

const CAPABILITY_PATTERN = /^[0-9a-f]{64}$/;
let capabilityTokenPromise: Promise<string> | null = null;

async function loadCapabilityToken(): Promise<string> {
  const { invoke } = await import("@tauri-apps/api/core");
  const token = await invoke<string>("backend_capability_token");
  if (!CAPABILITY_PATTERN.test(token)) {
    throw new Error("Desktop API capability is unavailable.");
  }
  return token;
}

export async function getLocalApiCapabilityToken(): Promise<string | null> {
  if (!isTauri()) return null;
  if (!capabilityTokenPromise) {
    capabilityTokenPromise = loadCapabilityToken().catch((error: unknown) => {
      capabilityTokenPromise = null;
      throw error;
    });
  }
  return capabilityTokenPromise;
}
