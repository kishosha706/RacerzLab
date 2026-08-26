import type { components as OpenApiComponents } from "../types/openapi.generated";

const API_BASE =
  import.meta.env.VITE_RACELAB_API_BASE_URL
  ?? import.meta.env.VITE_API_BASE_URL
  ?? "http://127.0.0.1:8010";
const HEALTH_TIMEOUT_MS = 2_000;

export type BackendHealthResponse = OpenApiComponents["schemas"]["HealthResponse"];
type BackendHealthUnavailableResponse = OpenApiComponents["schemas"]["HealthUnavailableResponse"];
export type BackendReadinessCode = BackendHealthUnavailableResponse["readiness_code"];
export type BackendRecoveryCode = BackendHealthUnavailableResponse["recovery_code"];

export type BackendReadinessFailure = {
  readinessCode: BackendReadinessCode;
  recoveryCode: BackendRecoveryCode;
};

export class BackendReadinessError extends Error {
  readonly app: "RacerZLab";
  readonly instanceId: string | null;
  readonly failure: BackendReadinessFailure;

  constructor(response: BackendHealthUnavailableResponse) {
    super("RacerZLab local storage is unavailable.");
    this.name = "BackendReadinessError";
    this.app = response.app;
    this.instanceId = response.instance_id ?? null;
    this.failure = {
      readinessCode: response.readiness_code,
      recoveryCode: response.recovery_code,
    };
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value != null && !Array.isArray(value);
}

function hasInstanceId(value: Record<string, unknown>): boolean {
  return value.instance_id == null || typeof value.instance_id === "string";
}

function isHealthyResponse(value: unknown): value is BackendHealthResponse {
  return isRecord(value)
    && value.status === "ok"
    && value.app === "RacerZLab"
    && typeof value.version === "string"
    && hasInstanceId(value);
}

function isUnavailableResponse(value: unknown): value is BackendHealthUnavailableResponse {
  if (!isRecord(value)
    || value.status !== "unavailable"
    || value.app !== "RacerZLab"
    || typeof value.version !== "string"
    || !hasInstanceId(value)) {
    return false;
  }

  return (
    value.readiness_code === "database_unavailable"
    && value.recovery_code === "restart_or_restore_local_storage"
  ) || (
    value.readiness_code === "data_storage_unavailable"
    && value.recovery_code === "free_space_or_restore_local_storage"
  );
}

export async function fetchBackendHealth(): Promise<BackendHealthResponse> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api/health`, {
      cache: "no-store",
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error("Local engine returned an invalid health response.");
  }

  if (response.ok && isHealthyResponse(payload)) return payload;
  if (response.status === 503 && isUnavailableResponse(payload)) {
    throw new BackendReadinessError(payload);
  }
  throw new Error(`Local engine health check failed (${response.status}).`);
}
