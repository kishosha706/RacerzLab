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
  RunListItem,
  RunOverview,
  SetupSnapshot,
  TelemetryCapabilitiesResponse,
  TelemetryEvent,
  TraceResponse,
} from "../types/telemetry";
import type { DamperResponseReport } from "../types/damperResponse";

const API_BASE =
  import.meta.env.VITE_RACELAB_API_BASE_URL ??
  import.meta.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8010";

/** Default timeout for normal API requests (10 seconds). */
const REQUEST_TIMEOUT_MS = 10_000;

/** Timeout for telemetry import requests (3 minutes — large .ibt files take time). */
const IMPORT_TIMEOUT_MS = 180_000;

/** Timeout for track map import requests (1 minute). */
const MAP_IMPORT_TIMEOUT_MS = 60_000;

/** Timeout for folder scan requests (30 seconds). */
const SCAN_TIMEOUT_MS = 30_000;

/** Timeout for full telemetry trace payloads (1 minute). */
const TRACE_TIMEOUT_MS = 60_000;
const GET_CACHE_DEFAULT_TTL_MS = 8_000;
const GET_CACHE_TRACE_TTL_MS = 2_000;

type JsonCacheEntry = {
  expiresAt: number;
  value: unknown;
};

export type HealthResponse = {
  status: string;
  app: string;
  version: string;
};

const inflightGetRequests = new Map<string, Promise<unknown>>();
const getResponseCache = new Map<string, JsonCacheEntry>();

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
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
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
        detail.title ?? "Import failed",
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
      getResponseCache.set(key, {
        value: payload,
        expiresAt: Date.now() + cacheTtlMs(path),
      });
    } else {
      invalidateApiCache();
    }
    return payload;
  };

  if (method !== "GET") return run();

  const promise = run().finally(() => {
    inflightGetRequests.delete(key);
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
  return requestJson<DialInResponse>(`/api/runs/${encodeURIComponent(runId)}/dial-in`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function startControlledWorkflow(payload: {
  run_id: string;
  complaint: string;
  selected_lap?: number | null;
} & DialInDecisionContext): Promise<ControlledWorkflow> {
  return requestJson<ControlledWorkflow>("/api/engineering/workflows", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function attachControlledWorkflowStage(
  workflowId: string,
  stage: "A" | "B" | "A2",
  runId: string,
): Promise<ControlledWorkflow> {
  return requestJson<ControlledWorkflow>(
    `/api/engineering/workflows/${encodeURIComponent(workflowId)}/stages/${stage}`,
    { method: "POST", body: JSON.stringify({ run_id: runId }) },
  );
}

export function scoreControlledWorkflow(workflowId: string): Promise<ControlledWorkflow> {
  return requestJson<ControlledWorkflow>("/api/engineering/test-director/score", {
    method: "POST",
    body: JSON.stringify({ workflow_id: workflowId }),
  });
}

export function fetchControlledWorkflows(activeOnly = false): Promise<ControlledWorkflow[]> {
  return requestJson<ControlledWorkflow[]>(`/api/engineering/workflows?active_only=${activeOnly ? "true" : "false"}`);
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
    includeDebug?: boolean;
  },
): Promise<ShockReaderResponse> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.lapWindow) params.set("lap_window", options.lapWindow);
  if (options?.phase) params.set("phase", options.phase);
  if (options?.zoneStartPct != null) params.set("zone_start_pct", String(options.zoneStartPct));
  if (options?.zoneEndPct != null) params.set("zone_end_pct", String(options.zoneEndPct));
  if (options?.includeDebug != null) params.set("include_debug", String(options.includeDebug));
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
