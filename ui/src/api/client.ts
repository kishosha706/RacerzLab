import type {
  ImportIbtResponse,
  ChannelCatalogItem,
  ChannelSummaryItem,
  DialInDecisionContext,
  DialInRequest,
  DialInResponse,
  ControlledWorkflow,
  LapSummary,
  PlatformEventItem,
  PlatformEventsReport,
  RunListItem,
  RunOverview,
  SetupSnapshot,
  TelemetryCapabilitiesResponse,
  TelemetryEvent,
  TraceResponse,
} from "../types/telemetry";
import type { components as OpenApiComponents } from "../types/openapi.generated";
import type { DamperResponseReport } from "../types/damperResponse";
import type {
  IntelligenceQueryRequest,
  IntelligenceQueryResponse,
  IntelligenceShellProjection,
  RunIntelligenceReport,
} from "../types/intelligence";
import type {
  ComponentInspectionResponse,
  ControlMechanismTraceResponse,
  VehicleSystemsProjection,
} from "../types/vehicleSystems";
import { isVehicleSystemsProjection } from "../types/vehicleSystems";
import type { EngineeringAwarenessProjection } from "../types/engineeringAwareness";
import { isEngineeringAwarenessProjection } from "../types/engineeringAwareness";
import type { CrewChiefWorkspace, EngineeringObjective } from "../types/crewChief";
import type {
  CampaignOperationStartResponse,
  LearningReadinessProjection,
  ProspectivePredictionResponse,
} from "../types/learningReadiness";
import {
  isIntelligenceShellProjection,
  isRunIntelligenceResponse,
} from "../utils/intelligenceResponseTrust";
import { isDialInHypothesisResponse } from "../utils/dialInResponseTrust";
import { isControlledWorkflowResponse } from "../utils/controlledWorkflowTrust";

const API_BASE =
  import.meta.env.VITE_RACELAB_API_BASE_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8010";

/** Default timeout for normal API requests (10 seconds). */
const REQUEST_TIMEOUT_MS = 10_000;

/** Full intelligence assembly can exceed 30 seconds on a real Next Gen run. */
const INTELLIGENCE_TIMEOUT_MS = 60_000;

/** Timeout for telemetry import requests (3 minutes — large .ibt files take time). */
const IMPORT_TIMEOUT_MS = 180_000;

/** Timeout for track map import requests (1 minute). */
const MAP_IMPORT_TIMEOUT_MS = 60_000;

/** Timeout for folder scan requests (30 seconds). */
const SCAN_TIMEOUT_MS = 30_000;

/** Timeout for full telemetry trace payloads (1 minute). */
const TRACE_TIMEOUT_MS = 60_000;

/** Learning-only archive projection; never blocks Race Mode or cockpit open. */
const LEARNING_READINESS_TIMEOUT_MS = 30_000;
const GET_CACHE_DEFAULT_TTL_MS = 8_000;
const GET_CACHE_TRACE_TTL_MS = 2_000;

type JsonCacheEntry = {
  expiresAt: number;
  value: unknown;
};

export type HealthResponse = OpenApiComponents["schemas"]["HealthResponse"];

const inflightGetRequests = new Map<string, Promise<unknown>>();
const getResponseCache = new Map<string, JsonCacheEntry>();
let apiCacheGeneration = 0;

function requestMethod(init?: RequestInit): string {
  return (init?.method ?? "GET").toUpperCase();
}

function requestKey(path: string, timeoutMs: number): string {
  return `${timeoutMs}:${path}`;
}

function cacheTtlMs(path: string): number {
  if (path.includes("/trace") || path.includes("/platform-events")) return GET_CACHE_TRACE_TTL_MS;
  return GET_CACHE_DEFAULT_TTL_MS;
}

function invalidateApiCache(pathPrefix?: string): void {
  apiCacheGeneration += 1;
  if (!pathPrefix) {
    inflightGetRequests.clear();
    getResponseCache.clear();
    return;
  }
  for (const key of inflightGetRequests.keys()) {
    if (key.includes(pathPrefix)) inflightGetRequests.delete(key);
  }
  for (const key of getResponseCache.keys()) {
    if (key.includes(pathPrefix)) getResponseCache.delete(key);
  }
}

/**
 * Fetch with timeout. Throws if the request does not complete within `ms`.
 * The AbortController is cleaned up on completion to avoid memory leaks.
 */
async function fetchWithTimeout(url: string, init: RequestInit, ms: number = REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const externalSignal = init.signal;
  const abortFromCaller = () => controller.abort();
  if (externalSignal?.aborted) controller.abort();
  else externalSignal?.addEventListener("abort", abortFromCaller, { once: true });
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
    externalSignal?.removeEventListener("abort", abortFromCaller);
  }
}

/**
 * Build a timeout error message. For the default timeout, mention the backend.
 * For longer timeouts (imports), mention the operation-specific message.
 */
function timeoutErrorMessage(ms: number, label: string): string {
  if (ms === REQUEST_TIMEOUT_MS) {
    return `Request timed out. Is the backend running at ${API_BASE}?`;
  }
  return `${label} timed out after ${(ms / 1000).toFixed(0)} seconds. The backend may still be processing or the file may be too large or corrupt.`;
}

function errorMessageFromResponseText(text: string, fallback: string): string {
  if (!text) return fallback;
  try {
    const payload = JSON.parse(text) as {
      detail?: string | {
        title?: string;
        message?: string;
        impact?: string;
        next_step?: string;
        cleanup?: string;
        technical_detail?: string;
      };
    };
    if (typeof payload.detail === "string") return payload.detail;
    if (payload.detail && typeof payload.detail === "object") {
      const detail = payload.detail;
      return [
        detail.title ?? fallback,
        detail.message,
        detail.impact,
        detail.next_step,
        detail.cleanup,
        detail.technical_detail ? `Technical detail: ${detail.technical_detail}` : null,
      ].filter(Boolean).join("\n");
    }
  } catch {
    // Fall through to raw server text for non-JSON responses.
  }
  return text || fallback;
}

async function requestJson<T>(path: string, init?: RequestInit, timeoutMs: number = REQUEST_TIMEOUT_MS, timeoutLabel: string = "Request"): Promise<T> {
  const method = requestMethod(init);
  const key = requestKey(path, timeoutMs);
  const requestCacheGeneration = apiCacheGeneration;
  if (method === "GET") {
    const cached = getResponseCache.get(key);
    if (cached && cached.expiresAt > Date.now()) {
      return cached.value as T;
    }
    const inflight = inflightGetRequests.get(key);
    if (inflight) return inflight as Promise<T>;
  }

  const run = async (): Promise<T> => {
    let response: Response;
    try {
      // Spread init FIRST so its headers don't overwrite our Content-Type default.
      // Then explicitly set Content-Type and merge any user headers on top.
      const mergedHeaders: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (init?.headers) {
        const userHeaders = init.headers as Record<string, string>;
        for (const key of Object.keys(userHeaders)) {
          mergedHeaders[key] = userHeaders[key];
        }
      }
      response = await fetchWithTimeout(`${API_BASE}${path}`, {
        ...init,
        headers: mergedHeaders,
      }, timeoutMs);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") {
        throw new Error(timeoutErrorMessage(timeoutMs, timeoutLabel));
      }
      throw new Error(`Network error: ${(err as Error).message ?? "Unknown error"}`);
    }
    if (!response.ok) {
      const text = await response.text();
      throw new Error(errorMessageFromResponseText(text, `Request failed: ${response.status}`));
    }
    const payload = (await response.json()) as T;
    if (method === "GET") {
      if (requestCacheGeneration === apiCacheGeneration) {
        getResponseCache.set(key, {
          value: payload,
          expiresAt: Date.now() + cacheTtlMs(path),
        });
      }
    } else {
      invalidateApiCache();
    }
    return payload;
  };

  if (method !== "GET") return run();

  const promise = run().finally(() => {
    if (inflightGetRequests.get(key) === promise) {
      inflightGetRequests.delete(key);
    }
  });
  inflightGetRequests.set(key, promise);
  return promise;
}

export function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/health", undefined, 2_000, "Health check");
}

/** Like requestJson but with a longer timeout for import operations. */
async function importJson<T>(path: string, init?: RequestInit): Promise<T> {
  return requestJson<T>(path, init, IMPORT_TIMEOUT_MS, "Telemetry import");
}

/** Like requestJson but with a medium timeout for map import operations. */
async function mapImportJson<T>(path: string, init?: RequestInit): Promise<T> {
  return requestJson<T>(path, init, MAP_IMPORT_TIMEOUT_MS, "Track map import");
}

/** Like requestJson but with a scan timeout for folder scan operations. */
async function scanJson<T>(path: string, init?: RequestInit): Promise<T> {
  return requestJson<T>(path, init, SCAN_TIMEOUT_MS, "Folder scan");
}

export function fetchRunList(): Promise<RunListItem[]> {
  return requestJson<RunListItem[]>("/api/runs");
}

export function importIbtFile(file: File): Promise<ImportIbtResponse> {
  const form = new FormData();
  form.append("file", file);
  return fetchWithTimeout(`${API_BASE}/api/imports/ibt`, {
    method: "POST",
    body: form,
  }, IMPORT_TIMEOUT_MS).then(async (response) => {
    if (!response.ok) {
      const text = await response.text();
      throw new Error(errorMessageFromResponseText(text, `Import failed: ${response.status}`));
    }
    const payload = await response.json() as ImportIbtResponse;
    invalidateApiCache();
    return payload;
  }).catch((err: unknown) => {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(timeoutErrorMessage(IMPORT_TIMEOUT_MS, "Telemetry import"));
    }
    throw err;
  });
}

/** Generate a correlation ID for import requests. */
function importRequestId(): string {
  const now = new Date();
  const ts = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}${String(now.getMinutes()).padStart(2, "0")}${String(now.getSeconds()).padStart(2, "0")}`;
  const rand = Math.random().toString(36).slice(2, 8);
  return `import_${ts}_${rand}`;
}

/** Import an .ibt file from a local filesystem path (Tauri native picker). */
export function importIbtFileFromPath(filePath: string): Promise<ImportIbtResponse> {
  const reqId = importRequestId();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-RacerZLab-Request-Id": reqId,
  };
  // Debug log safe header info
  if (typeof localStorage !== "undefined") {
    try {
      if (localStorage.getItem("DEBUG_IMPORT") === "1") {
        console.debug("[ImportDebug] Request headers:", JSON.stringify(headers));
      }
    } catch { /* ignore */ }
  }
  return importJson<ImportIbtResponse>("/api/imports/ibt", {
    method: "POST",
    headers,
    body: JSON.stringify({ path: filePath }),
  }).then((payload) => {
    invalidateApiCache();
    return payload;
  });
}

export function fetchOverview(runId: string): Promise<RunOverview> {
  return requestJson<RunOverview>(`/api/runs/${encodeURIComponent(runId)}/overview`);
}

export function fetchRunIntelligence(
  runId: string,
  options?: { sessionId?: string | null; refreshKey?: string | number },
): Promise<RunIntelligenceReport> {
  const params = new URLSearchParams();
  if (options?.sessionId) params.set("session_id", options.sessionId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/intelligence${suffix}`,
    undefined,
    INTELLIGENCE_TIMEOUT_MS,
    "Run intelligence",
  ).then((payload) => {
    if (!isRunIntelligenceResponse(payload, {
      runId,
      sessionId: options?.sessionId ?? null,
    })) {
      throw new Error(
        "Run intelligence failed its exact schema, run, session, setup, or snapshot identity check.",
      );
    }
    return payload;
  });
}

export function fetchIntelligenceShellProjection(
  runId: string,
  options?: { sessionId?: string | null },
): Promise<IntelligenceShellProjection> {
  const params = new URLSearchParams();
  if (options?.sessionId) params.set("session_id", options.sessionId);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/intelligence-shell${suffix}`,
    undefined,
    REQUEST_TIMEOUT_MS,
    "Intelligence shell projection",
  ).then((payload) => {
    if (!isIntelligenceShellProjection(payload, {
      runId,
      sessionId: options?.sessionId ?? null,
    })) {
      throw new Error(
        "The intelligence shell projection failed its exact run, session, schema, or navigation-only authority check.",
      );
    }
    return payload;
  });
}

async function trustedCrewChiefResponse(
  payload: unknown,
  runId: string,
  sessionId: string,
  report: RunIntelligenceReport,
  objectiveId: EngineeringObjective,
  scopeRunIds?: readonly string[],
): Promise<CrewChiefWorkspace> {
  const [
    crewTrust,
    learningTrust,
    investigationTrust,
    vehicleDynamicsTrust,
    engineeringKnowledgeTrust,
  ] = await Promise.all([
    import("../utils/crewChiefResponseTrust"),
    import("../utils/engineeringLearningTrust.js"),
    import("../utils/investigationImprovementTrust"),
    import("../utils/vehicleDynamicsTrust.ts"),
    import("../utils/engineeringKnowledgeTrust.ts"),
  ]);
  if (!crewTrust.isCrewChiefWorkspaceResponse(payload, {
    runId, sessionId, report, objectiveId, scopeRunIds,
  })) {
    throw new Error("Crew Chief failed its exact P19/P20/P26/P32/P33/P34/P35 workspace authority check.");
  }
  if (!await crewTrust.hasCanonicalEngineeringAwarenessDigest(payload)) {
    throw new Error("Crew Chief failed its canonical P20 scientific-projection identity check.");
  }
  if (!await vehicleDynamicsTrust.hasCanonicalPerformanceMechanismAssessmentDigest(payload.vehicle_dynamics)) {
    throw new Error("Crew Chief failed its canonical P35 vehicle-dynamics identity check.");
  }
  if (!await engineeringKnowledgeTrust.hasCanonicalEngineeringKnowledgeDigest(payload.engineering_knowledge)) {
    throw new Error("Crew Chief failed its canonical P35.1 engineering-knowledge identity check.");
  }
  if (!await crewTrust.hasCanonicalVehicleRuntimeIdentityDigest(payload)) {
    throw new Error("Crew Chief failed its canonical P26/P35 vehicle runtime identity check.");
  }
  if (!await crewTrust.hasCanonicalCrewEvidenceIndexDigest(payload)) {
    throw new Error("Crew Chief failed its canonical evidence-index identity check.");
  }
  if (!await crewTrust.hasCanonicalEngineeringCaseDigest(payload)) {
    throw new Error("Crew Chief failed its canonical P35.4.3 engineering-case identity check.");
  }
  if (!await learningTrust.hasCanonicalEngineeringLearningDigests(payload.learning_prior)) {
    throw new Error("Crew Chief failed its canonical P33 learning identity check.");
  }
  if (!await investigationTrust.hasCanonicalInvestigationImprovementDigests(
    payload.investigation_improvement,
    payload,
  )) {
    throw new Error("Crew Chief failed its canonical P34 investigation-improvement identity check.");
  }
  if (!await crewTrust.hasCanonicalMeasurementMissionDigest(payload.p19_mission_contract)) {
    throw new Error("Crew Chief failed its canonical P19 measurement-mission identity check.");
  }
  if (!await crewTrust.hasCanonicalRunSentinelDigest(
    payload.run_sentinel,
    payload.identity.run_sentinel_sha256,
  )) {
    throw new Error("Crew Chief failed its canonical mission-progress identity check.");
  }
  return payload;
}

export function fetchCrewChiefWorkspace(
  runId: string,
  sessionId: string,
  report: RunIntelligenceReport,
  options?: {
    investigationId?: string | null;
    objective?: EngineeringObjective;
    scopeRunIds?: readonly string[];
  },
): Promise<CrewChiefWorkspace> {
  const objective = options?.objective ?? "race_long_run";
  const params = new URLSearchParams({ session_id: sessionId });
  if (options?.investigationId) params.set("investigation_id", options.investigationId);
  params.set("objective", objective);
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/crew-chief-workspace?${params}`,
    undefined,
    INTELLIGENCE_TIMEOUT_MS,
    "Crew Chief workspace",
  ).then((payload) => trustedCrewChiefResponse(
    payload, runId, sessionId, report, objective, options?.scopeRunIds,
  ));
}

export function openCrewChiefInvestigation(
  runId: string,
  sessionId: string,
  report: RunIntelligenceReport,
  scopeRunIds: readonly string[],
  body: { driver_report: string; expected_workspace_revision: string; objective: EngineeringObjective },
): Promise<CrewChiefWorkspace> {
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/crew-chief-investigations`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, ...body }) },
    INTELLIGENCE_TIMEOUT_MS,
    "Open Crew Chief investigation",
  ).then((payload) => trustedCrewChiefResponse(payload, runId, sessionId, report, body.objective, scopeRunIds));
}

export function continueCrewChiefInvestigation(
  runId: string,
  sessionId: string,
  investigationId: string,
  expectedWorkspaceRevision: string,
  report: RunIntelligenceReport,
  scopeRunIds: readonly string[],
  objective: EngineeringObjective,
): Promise<CrewChiefWorkspace> {
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/crew-chief-investigations/${encodeURIComponent(investigationId)}/continue`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, expected_workspace_revision: expectedWorkspaceRevision }) },
    INTELLIGENCE_TIMEOUT_MS,
    "Continue Crew Chief investigation",
  ).then((payload) => trustedCrewChiefResponse(payload, runId, sessionId, report, objective, scopeRunIds));
}

export function advanceCrewChiefInvestigation(
  runId: string,
  sessionId: string,
  investigationId: string,
  expectedWorkspaceRevision: string,
  report: RunIntelligenceReport,
  scopeRunIds: readonly string[],
  objective: EngineeringObjective,
): Promise<CrewChiefWorkspace> {
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/crew-chief-investigations/${encodeURIComponent(investigationId)}/advance-until-boundary`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, expected_workspace_revision: expectedWorkspaceRevision, max_read_only_steps: 4 }) },
    INTELLIGENCE_TIMEOUT_MS,
    "Advance Crew Chief to the next boundary",
  ).then((payload) => trustedCrewChiefResponse(payload, runId, sessionId, report, objective, scopeRunIds));
}

export function answerCrewChiefQuestion(
  runId: string,
  sessionId: string,
  investigationId: string,
  expectedWorkspaceRevision: string,
  answer: string,
  report: RunIntelligenceReport,
  scopeRunIds: readonly string[],
  objective: EngineeringObjective,
): Promise<CrewChiefWorkspace> {
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/crew-chief-investigations/${encodeURIComponent(investigationId)}/driver-answer`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, expected_workspace_revision: expectedWorkspaceRevision, answer }) },
    INTELLIGENCE_TIMEOUT_MS,
    "Crew Chief driver answer",
  ).then((payload) => trustedCrewChiefResponse(payload, runId, sessionId, report, objective, scopeRunIds));
}

function mutateCrewChiefInvestigation(
  runId: string,
  sessionId: string,
  investigationId: string,
  action: "objective" | "abandon" | "rebase",
  body: Record<string, unknown>,
  report: RunIntelligenceReport,
  scopeRunIds: readonly string[],
  objective: EngineeringObjective,
): Promise<CrewChiefWorkspace> {
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/crew-chief-investigations/${encodeURIComponent(investigationId)}/${action}`,
    { method: "POST", body: JSON.stringify({ session_id: sessionId, ...body }) },
    INTELLIGENCE_TIMEOUT_MS,
    `Crew Chief ${action}`,
  ).then((payload) => trustedCrewChiefResponse(payload, runId, sessionId, report, objective, scopeRunIds));
}

export function updateCrewChiefObjective(
  runId: string, sessionId: string, investigationId: string,
  expectedWorkspaceRevision: string, objective: EngineeringObjective,
  report: RunIntelligenceReport, scopeRunIds: readonly string[],
): Promise<CrewChiefWorkspace> {
  return mutateCrewChiefInvestigation(runId, sessionId, investigationId, "objective", {
    expected_workspace_revision: expectedWorkspaceRevision, objective,
  }, report, scopeRunIds, objective);
}

export function abandonCrewChiefInvestigation(
  runId: string, sessionId: string, investigationId: string,
  expectedWorkspaceRevision: string, reason: string,
  report: RunIntelligenceReport, scopeRunIds: readonly string[],
  objective: EngineeringObjective,
): Promise<CrewChiefWorkspace> {
  return mutateCrewChiefInvestigation(runId, sessionId, investigationId, "abandon", {
    expected_workspace_revision: expectedWorkspaceRevision, reason,
  }, report, scopeRunIds, objective);
}

export function rebaseCrewChiefInvestigation(
  runId: string, sessionId: string, investigationId: string,
  staleWorkspaceRevision: string, report: RunIntelligenceReport,
  scopeRunIds: readonly string[],
  objective: EngineeringObjective,
): Promise<CrewChiefWorkspace> {
  return mutateCrewChiefInvestigation(runId, sessionId, investigationId, "rebase", {
    stale_workspace_revision: staleWorkspaceRevision,
  }, report, scopeRunIds, objective);
}

export function fetchVehicleSystems(
  runId: string,
  options?: { sessionId?: string | null; refreshKey?: string | number },
): Promise<VehicleSystemsProjection> {
  const params = new URLSearchParams();
  if (options?.sessionId) params.set("session_id", options.sessionId);
  if (options?.refreshKey != null) params.set("refresh", String(options.refreshKey));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/vehicle-systems${suffix}`,
    undefined,
    INTELLIGENCE_TIMEOUT_MS,
    "Vehicle systems",
  ).then((payload) => {
    if (!isVehicleSystemsProjection(payload, {
      runId,
      sessionId: options?.sessionId ?? null,
    })) throw new Error("Vehicle systems failed complete runtime identity and authority validation.");
    return payload;
  });
}

export function fetchVehicleSystemComponent(
  runId: string,
  componentId: string,
  options?: { sessionId?: string | null; refreshKey?: string | number },
): Promise<ComponentInspectionResponse> {
  const params = new URLSearchParams();
  if (options?.sessionId) params.set("session_id", options.sessionId);
  if (options?.refreshKey != null) params.set("refresh", String(options.refreshKey));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ComponentInspectionResponse>(
    `/api/runs/${encodeURIComponent(runId)}/vehicle-systems/components/${encodeURIComponent(componentId)}${suffix}`,
    undefined,
    INTELLIGENCE_TIMEOUT_MS,
    "Vehicle-system component",
  );
}

export function fetchVehicleSystemControlTrace(
  runId: string,
  controlKey: string,
  options?: { refreshKey?: string | number },
): Promise<ControlMechanismTraceResponse> {
  const params = new URLSearchParams();
  if (options?.refreshKey != null) params.set("refresh", String(options.refreshKey));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ControlMechanismTraceResponse>(
    `/api/runs/${encodeURIComponent(runId)}/vehicle-systems/controls/${encodeURIComponent(controlKey)}/trace${suffix}`,
  );
}

export function fetchEngineeringAwareness(
  runId: string,
  options?: { sessionId?: string | null; refresh?: boolean },
): Promise<EngineeringAwarenessProjection> {
  const params = new URLSearchParams();
  if (options?.sessionId) params.set("session_id", options.sessionId);
  if (options?.refresh) params.set("refresh", "true");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<unknown>(
    `/api/runs/${encodeURIComponent(runId)}/engineering-awareness${suffix}`,
    undefined,
    INTELLIGENCE_TIMEOUT_MS,
    "Engineering awareness",
  ).then((payload) => {
    if (!isEngineeringAwarenessProjection(payload, {
      runId, sessionId: options?.sessionId ?? null,
    })) throw new Error("Engineering awareness failed complete P20 runtime validation.");
    return payload;
  });
}

export function fetchLearningReadiness(
  runId: string,
  options?: { sessionId?: string | null },
): Promise<LearningReadinessProjection> {
  const params = new URLSearchParams({ run_id: runId });
  if (options?.sessionId) params.set("session_id", options.sessionId);
  return requestJson<LearningReadinessProjection>(
    `/api/evaluation/learning-readiness?${params.toString()}`,
    undefined,
    LEARNING_READINESS_TIMEOUT_MS,
    "Learning readiness",
  );
}

export function startEvidenceCampaign(
  runId: string,
  campaignKind: string,
): Promise<CampaignOperationStartResponse> {
  return requestJson<CampaignOperationStartResponse>(
    "/api/evaluation/campaign-operations/start",
    {
      method: "POST",
      body: JSON.stringify({ run_id: runId, campaign_kind: campaignKind }),
    },
  );
}

export function freezeProspectivePrediction(
  operationId: string,
  runId: string,
  sessionId: string,
): Promise<ProspectivePredictionResponse> {
  return requestJson<ProspectivePredictionResponse>(
    "/api/evaluation/prospective-predictions",
    {
      method: "POST",
      body: JSON.stringify({
        operation_id: operationId,
        run_id: runId,
        session_id: sessionId,
      }),
    },
  );
}

export function queryRunIntelligence(
  runId: string,
  payload: IntelligenceQueryRequest,
): Promise<IntelligenceQueryResponse> {
  return requestJson<IntelligenceQueryResponse>(
    `/api/runs/${encodeURIComponent(runId)}/intelligence/query`,
    { method: "POST", body: JSON.stringify(payload) },
    INTELLIGENCE_TIMEOUT_MS,
    "Engineer question",
  );
}

export function fetchLaps(runId: string): Promise<LapSummary[]> {
  return requestJson<LapSummary[]>(`/api/runs/${encodeURIComponent(runId)}/laps`);
}

export function fetchEvents(runId: string, options?: { lap?: number; type?: string }): Promise<TelemetryEvent[]> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.type) params.set("type", options.type);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<TelemetryEvent[]>(`/api/runs/${encodeURIComponent(runId)}/events${suffix}`);
}

export function fetchSetup(runId: string): Promise<SetupSnapshot> {
  return requestJson<SetupSnapshot>(`/api/runs/${encodeURIComponent(runId)}/setup`);
}

export function analyzeRunDialIn(runId: string, payload: DialInRequest): Promise<DialInResponse> {
  return requestJson<unknown>(`/api/runs/${encodeURIComponent(runId)}/dial-in`, {
    method: "POST",
    body: JSON.stringify(payload),
  }).then(async (response) => {
    if (!isDialInHypothesisResponse(response, {
      runId,
      complaint: payload.complaint,
      sessionId: payload.session_id,
    })) {
      throw new Error("Dial-In returned an invalid or action-bearing hypothesis response.");
    }
    const engineeringKnowledge = response.engineering_knowledge;
    if (engineeringKnowledge != null) {
      const trust = await import("../utils/engineeringKnowledgeTrust.ts");
      if (!await trust.hasCanonicalEngineeringKnowledgeDigest(engineeringKnowledge)) {
        throw new Error(
          "Dial-In returned a non-canonical engineering-knowledge projection.",
        );
      }
    }
    return response;
  });
}

export function startControlledWorkflow(payload: {
  run_id: string;
  session_id: string;
  complaint: string;
  selected_lap?: number | null;
  lap_scope?: "run" | "single_lap" | "lap_window" | "track_zone" | null;
  window_start_lap?: number | null;
  window_end_lap?: number | null;
  representative_lap?: number | null;
} & DialInDecisionContext): Promise<ControlledWorkflow> {
  return requestJson<unknown>("/api/engineering/workflows", {
    method: "POST",
    body: JSON.stringify(payload),
  }).then((response) => trustedControlledWorkflow(response));
}

function trustedControlledWorkflow(payload: unknown): ControlledWorkflow {
  if (!isControlledWorkflowResponse(payload)) {
    throw new Error("Controlled workflow failed its exact lifecycle and P33 capture-containment check.");
  }
  return payload;
}

export function attachControlledWorkflowStage(
  workflowId: string,
  stage: "A" | "B" | "A2",
  runId: string,
): Promise<ControlledWorkflow> {
  return requestJson<unknown>(
    `/api/engineering/workflows/${encodeURIComponent(workflowId)}/stages/${stage}`,
    { method: "POST", body: JSON.stringify({ run_id: runId }) },
  ).then((response) => trustedControlledWorkflow(response));
}

export function scoreControlledWorkflow(workflowId: string): Promise<ControlledWorkflow> {
  return requestJson<unknown>(
    `/api/engineering/workflows/${encodeURIComponent(workflowId)}/score`, {
    method: "POST",
  }).then((response) => trustedControlledWorkflow(response));
}

export function cancelControlledWorkflow(workflowId: string): Promise<ControlledWorkflow> {
  return requestJson<unknown>(
    `/api/engineering/workflows/${encodeURIComponent(workflowId)}/cancel`,
    { method: "POST" },
  ).then((response) => trustedControlledWorkflow(response));
}

export function fetchControlledWorkflows(
  sessionId: string,
  runId: string,
  activeOnly = false,
): Promise<ControlledWorkflow[]> {
  const params = new URLSearchParams({
    session_id: sessionId,
    run_id: runId,
    active_only: activeOnly ? "true" : "false",
  });
  return requestJson<unknown>(`/api/engineering/workflows?${params.toString()}`).then((response) => {
    if (!Array.isArray(response) || !response.every(isControlledWorkflowResponse)) {
      throw new Error("Controlled-workflow catalog failed its exact lifecycle and P33 capture-containment check.");
    }
    return response;
  });
}

export type ControlledWorkflowCatalogItem = Pick<
  ControlledWorkflow,
  "workflow_id" | "status" | "source_run_id" | "stage_run_ids" | "updated_at"
> & { revision_sha256: string };

export function fetchControlledWorkflowCatalog(
  sessionId: string,
  runId: string,
): Promise<ControlledWorkflowCatalogItem[]> {
  const params = new URLSearchParams({ session_id: sessionId, run_id: runId });
  return requestJson<ControlledWorkflowCatalogItem[]>(
    `/api/engineering/workflows/catalog?${params.toString()}`,
  );
}

export function fetchControlledWorkflow(workflowId: string): Promise<ControlledWorkflow> {
  return requestJson<unknown>(
    `/api/engineering/workflows/${encodeURIComponent(workflowId)}`,
  ).then((response) => trustedControlledWorkflow(response));
}

export function fetchControlledWorkflowReport(workflowId: string): Promise<{ workflow_id: string; markdown: string }> {
  return requestJson<{ workflow_id: string; markdown: string }>(
    `/api/engineering/workflows/${encodeURIComponent(workflowId)}/report`,
  );
}

export function fetchChannels(runId: string): Promise<ChannelCatalogItem[]> {
  return requestJson<ChannelCatalogItem[]>(`/api/runs/${encodeURIComponent(runId)}/channels?compact=true`);
}

export function fetchChannelSummary(runId: string): Promise<ChannelSummaryItem[]> {
  return requestJson<ChannelSummaryItem[]>(`/api/runs/${encodeURIComponent(runId)}/channels/summary?compact=true`);
}

export function fetchTelemetryCapabilities(runId: string): Promise<TelemetryCapabilitiesResponse> {
  return requestJson<TelemetryCapabilitiesResponse>(
    `/api/runs/${encodeURIComponent(runId)}/telemetry-capabilities`,
  );
}

export function fetchChannelsFull(runId: string): Promise<ChannelCatalogItem[]> {
  return requestJson<ChannelCatalogItem[]>(`/api/runs/${encodeURIComponent(runId)}/channels?compact=true`);
}

export function fetchReport(runId: string): Promise<{ run_id: string; markdown: string }> {
  return requestJson<{ run_id: string; markdown: string }>(`/api/runs/${encodeURIComponent(runId)}/report`);
}

export function fetchTrace(
  runId: string,
  options?: {
    lap?: number;
    channels?: string[];
    x?: string;
    downsample?: number | string;
    preserveExtrema?: boolean;
    resolution?: "raw";
    startFt?: number;
    endFt?: number;
  },
): Promise<TraceResponse> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.channels?.length) params.set("channels", options.channels.join(","));
  if (options?.x) params.set("x", options.x);
  if (options?.downsample != null) params.set("downsample", String(options.downsample));
  if (options?.preserveExtrema != null) params.set("preserve_extrema", String(options.preserveExtrema));
  if (options?.resolution) params.set("resolution", options.resolution);
  if (options?.startFt != null) params.set("start_ft", String(options.startFt));
  if (options?.endFt != null) params.set("end_ft", String(options.endFt));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<TraceResponse>(
    `/api/runs/${encodeURIComponent(runId)}/trace${suffix}`,
    undefined,
    TRACE_TIMEOUT_MS,
    "Telemetry trace",
  );
}

export function fetchPlatformEvents(
  runId: string,
  options?: { lap?: number; event_type?: string },
): Promise<PlatformEventItem[]> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.event_type) params.set("event_type", options.event_type);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<PlatformEventItem[]>(`/api/runs/${encodeURIComponent(runId)}/platform-events${suffix}`);
}

import type {
  CompareResponse,
  ComparisonInsightsResponse,
  DeltaTraceRequest,
  DeltaTraceResponse,
  EngineeringSystemsResponse,
  TimeAnalysisRequest,
  TimeAnalysisResponse,
} from "../types/compare";
import type { ShockReaderResponse } from "../types/shockReader";

export function fetchCompareDeltaTraces(request: DeltaTraceRequest): Promise<DeltaTraceResponse> {
  return requestJson<DeltaTraceResponse>("/api/compare/delta-traces", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

type ComparePreview = {
  baseline_laps: number[];
  test_laps: number[];
  suggested_baseline_lap: number | null;
  suggested_test_lap: number | null;
  setup_changes: import("../types/compare").SetupChange[];
  context_changes: Array<{ key: string; label: string; warning: string | null; is_problem: boolean }>;
  warnings: string[];
  compare_identity: import("../types/compare").CompareIdentity;
};

const sha256Pattern = /^[0-9a-f]{64}$/;
function compareIdentityMatches(
  payload: unknown,
  request: { baseline_run_id: string; test_run_id: string; baseline_lap?: number | null; test_lap?: number | null; target_zone_start_pct?: number; target_zone_end_pct?: number },
): payload is CompareResponse {
  if (typeof payload !== "object" || payload === null) return false;
  const response = payload as Partial<CompareResponse>;
  const identity = response.compare_identity;
  if (!identity || identity.schema_version !== "p31.compare-identity.v1") return false;
  const runs = [identity.baseline, identity.test];
  return response.baseline_run_id === request.baseline_run_id
    && response.test_run_id === request.test_run_id
    && identity.baseline.run_id === request.baseline_run_id
    && identity.test.run_id === request.test_run_id
    && (request.baseline_lap == null || response.baseline_lap === request.baseline_lap)
    && (request.test_lap == null || response.test_lap === request.test_lap)
    && (request.target_zone_start_pct == null || identity.target_zone_start_pct === request.target_zone_start_pct)
    && (request.target_zone_end_pct == null || identity.target_zone_end_pct === request.target_zone_end_pct)
    && sha256Pattern.test(identity.identity_sha256)
    && runs.every((run) => sha256Pattern.test(run.source_file_sha256)
      && sha256Pattern.test(run.telemetry_cache_sha256)
      && sha256Pattern.test(run.compatibility_fingerprint)
      && ((run.setup_id === null && run.setup_sha256 === null)
        || (typeof run.setup_id === "string" && run.setup_id.length > 0
          && typeof run.setup_sha256 === "string" && sha256Pattern.test(run.setup_sha256))));
}

export function fetchComparePreview(
  baselineRunId: string, testRunId: string, signal?: AbortSignal,
): Promise<ComparePreview> {
  const params = new URLSearchParams({ baseline_run_id: baselineRunId, test_run_id: testRunId });
  return requestJson<ComparePreview>(`/api/compare/preview?${params}`, { signal }).then((payload) => {
    const identity = payload.compare_identity;
    if (!identity || identity.baseline.run_id !== baselineRunId || identity.test.run_id !== testRunId
      || !sha256Pattern.test(identity.identity_sha256)) {
      throw new Error("Compare preview failed exact source identity validation.");
    }
    return payload;
  });
}

export function runCompare(
  request: { baseline_run_id: string; test_run_id: string; baseline_lap?: number | null; test_lap?: number | null; target_zone_start_pct: number; target_zone_end_pct: number },
  signal?: AbortSignal,
): Promise<CompareResponse> {
  return requestJson<unknown>("/api/compare", {
    method: "POST", body: JSON.stringify(request), signal,
  }, INTELLIGENCE_TIMEOUT_MS, "Compare").then((payload) => {
    if (!compareIdentityMatches(payload, request)) {
      throw new Error("Compare result failed exact source, setup, lap, or physical-zone identity validation.");
    }
    return payload;
  });
}

export function fetchCompareInsights(request: {
  baseline_run_id: string;
  test_run_id: string;
  baseline_lap?: number | null;
  test_lap?: number | null;
  target_zone_start_pct?: number;
  target_zone_end_pct?: number;
  channels?: string[] | null;
}): Promise<ComparisonInsightsResponse> {
  return requestJson<ComparisonInsightsResponse>("/api/compare/insights", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

import type { LapWindowsResponse, StintCompareRequest, StintCompareResult, StintResponse } from "../types/laps";
import type { RaceLabSession, RunLapList } from "../types/session";
import type { TrackMap, TrackMapIndexEntry, TrackMapPackage } from "../types/trackMap";

export function importMt2File(file: File): Promise<TrackMapIndexEntry> {
  const form = new FormData();
  form.append("file", file);
  return fetchWithTimeout(`${API_BASE}/api/imports/mt2`, {
    method: "POST",
    body: form,
  }, MAP_IMPORT_TIMEOUT_MS).then(async (response) => {
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Import failed: ${response.status}`);
    }
    const payload = await response.json() as TrackMapIndexEntry;
    invalidateApiCache("/api/track-maps");
    return payload;
  }).catch((err: unknown) => {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(timeoutErrorMessage(MAP_IMPORT_TIMEOUT_MS, "Track map import"));
    }
    throw err;
  });
}

/** Import a track map file from a local filesystem path (Tauri native picker). */
export function importMt2FileFromPath(filePath: string): Promise<TrackMapIndexEntry> {
  return mapImportJson<TrackMapIndexEntry>("/api/imports/mt2", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: filePath }),
  }).then((payload) => {
    invalidateApiCache("/api/track-maps");
    return payload;
  });
}

export function fetchPlatformEventsReport(
  runId: string,
  options?: { lap?: number; event_type?: string },
): Promise<PlatformEventsReport> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.event_type) params.set("event_type", options.event_type);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<PlatformEventsReport>(`/api/runs/${encodeURIComponent(runId)}/platform-events-report${suffix}`);
}

export function fetchCompareTimeAnalysis(request: TimeAnalysisRequest): Promise<TimeAnalysisResponse> {
  return requestJson<TimeAnalysisResponse>("/api/compare/time-analysis", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function fetchEngineeringSystems(request: TimeAnalysisRequest): Promise<EngineeringSystemsResponse> {
  return requestJson<EngineeringSystemsResponse>("/api/compare/engineering-systems", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function importMt2Folder(folderPath: string): Promise<{ imported: number; entries: TrackMapIndexEntry[] }> {
  return mapImportJson<{ imported: number; entries: TrackMapIndexEntry[] }>("/api/imports/mt2-folder", {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath }),
  }).then((payload) => {
    invalidateApiCache("/api/track-maps");
    return payload;
  });
}

export function fetchTrackMaps(): Promise<TrackMapIndexEntry[]> {
  return requestJson<TrackMapIndexEntry[]>("/api/track-maps");
}

export function fetchTrackMap(mapId: string): Promise<TrackMap> {
  return requestJson<TrackMap>(`/api/track-maps/${encodeURIComponent(mapId)}`);
}

// ── Session API ────────────────────────────────────────────

export function createSession(name?: string): Promise<RaceLabSession> {
  return requestJson<RaceLabSession>("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ name: name ?? null }),
  });
}

export function fetchSessions(includeArchived = false): Promise<RaceLabSession[]> {
  const params = includeArchived ? "?include_archived=true" : "";
  return requestJson<RaceLabSession[]>(`/api/sessions${params}`);
}

export function fetchSession(sessionId: string): Promise<RaceLabSession> {
  return requestJson<RaceLabSession>(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export function updateSession(sessionId: string, payload: Record<string, unknown>): Promise<RaceLabSession> {
  return requestJson<RaceLabSession>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSession(sessionId: string): Promise<{ deleted: boolean; session_id: string }> {
  return requestJson<{ deleted: boolean; session_id: string }>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function archiveSession(sessionId: string): Promise<RaceLabSession> {
  return requestJson<RaceLabSession>(`/api/sessions/${encodeURIComponent(sessionId)}/archive`, {
    method: "POST",
  });
}

export function addRunToSession(sessionId: string, runId: string): Promise<RaceLabSession> {
  return requestJson<RaceLabSession>(`/api/sessions/${encodeURIComponent(sessionId)}/runs`, {
    method: "POST",
    body: JSON.stringify({ run_id: runId }),
  });
}

export function fetchSessionRunList(sessionId: string): Promise<RunListItem[]> {
  return requestJson<RunListItem[]>(`/api/sessions/${encodeURIComponent(sessionId)}/runs`);
}

export function fetchRunLapList(runId: string): Promise<RunLapList> {
  return requestJson<RunLapList>(`/api/sessions/runs/${encodeURIComponent(runId)}/laps`);
}

export function fetchLapWindows(runId: string): Promise<LapWindowsResponse> {
  return requestJson<LapWindowsResponse>(`/api/runs/${encodeURIComponent(runId)}/lap-windows`);
}

export function fetchStints(runId: string): Promise<StintResponse> {
  return requestJson<StintResponse>(`/api/runs/${encodeURIComponent(runId)}/stints`);
}

export function compareStints(request: StintCompareRequest): Promise<StintCompareResult> {
  return requestJson<StintCompareResult>("/api/stints/compare", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function fetchShockReader(
  runId: string,
  options?: {
    lap?: number | null;
    lapWindow?: string | null;
    phase?: string | null;
    zoneStartPct?: number | null;
    zoneEndPct?: number | null;
  },
): Promise<ShockReaderResponse> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.lapWindow) params.set("lap_window", options.lapWindow);
  if (options?.phase) params.set("phase", options.phase);
  if (options?.zoneStartPct != null) params.set("zone_start_pct", String(options.zoneStartPct));
  if (options?.zoneEndPct != null) params.set("zone_end_pct", String(options.zoneEndPct));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<ShockReaderResponse>(`/api/runs/${encodeURIComponent(runId)}/shock-reader${suffix}`);
}

export function fetchDamperResponse(runId: string, lap: number): Promise<DamperResponseReport> {
  const params = new URLSearchParams({ lap: String(lap) });
  return requestJson<DamperResponseReport>(
    `/api/runs/${encodeURIComponent(runId)}/damper-response?${params.toString()}`,
  );
}

export interface TelemetryFileEntry {
  name: string;
  path: string;
  size_bytes: number;
  modified_at: string;
}

export interface ScanTelemetryFolderResponse {
  files: TelemetryFileEntry[];
  folder: string;
  count: number;
}

/** Scan a local folder for .ibt telemetry files (Tauri native only). */
export function scanTelemetryFolder(folderPath: string): Promise<ScanTelemetryFolderResponse> {
  return scanJson<ScanTelemetryFolderResponse>("/api/imports/scan-telemetry-folder", {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath }),
  });
}

export function fetchRunTrackMapPackage(
  runId: string,
  options?: { lap?: number; target_zone_start_pct?: number; target_zone_end_pct?: number; preferred_map_id?: string },
): Promise<TrackMapPackage> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.target_zone_start_pct != null) params.set("target_zone_start_pct", String(options.target_zone_start_pct));
  if (options?.target_zone_end_pct != null) params.set("target_zone_end_pct", String(options.target_zone_end_pct));
  if (options?.preferred_map_id) params.set("preferred_map_id", options.preferred_map_id);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<TrackMapPackage>(`/api/runs/${encodeURIComponent(runId)}/track-map-package${suffix}`);
}
