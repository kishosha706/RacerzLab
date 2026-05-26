import type {
  ImportIbtResponse,
  ChannelCatalogItem,
  LapSummary,
  PlatformEventItem,
  RunListItem,
  RunOverview,
  SetupSnapshot,
  TelemetryEvent,
  TraceResponse,
} from "../types/telemetry";

const API_BASE = import.meta.env.VITE_RACELAB_API_BASE_URL ?? "http://127.0.0.1:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function fetchRunList(): Promise<RunListItem[]> {
  return requestJson<RunListItem[]>("/api/runs");
}

export function importIbtFile(file: File): Promise<ImportIbtResponse> {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_BASE}/api/imports/ibt`, {
    method: "POST",
    body: form,
  }).then(async (response) => {
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Import failed: ${response.status}`);
    }
    return response.json() as Promise<ImportIbtResponse>;
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

export function fetchChannels(runId: string): Promise<ChannelCatalogItem[]> {
  return requestJson<ChannelCatalogItem[]>(`/api/runs/${encodeURIComponent(runId)}/channels`);
}

export function fetchReport(runId: string): Promise<{ run_id: string; markdown: string }> {
  return requestJson<{ run_id: string; markdown: string }>(`/api/runs/${encodeURIComponent(runId)}/report`);
}

export function fetchTrace(
  runId: string,
  options?: { lap?: number; channels?: string[]; x?: string; downsample?: number | string; preserveExtrema?: boolean },
): Promise<TraceResponse> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.channels?.length) params.set("channels", options.channels.join(","));
  if (options?.x) params.set("x", options.x);
  if (options?.downsample != null) params.set("downsample", String(options.downsample));
  if (options?.preserveExtrema != null) params.set("preserve_extrema", String(options.preserveExtrema));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<TraceResponse>(`/api/runs/${encodeURIComponent(runId)}/trace${suffix}`);
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

import type { ComparisonInsightsResponse, DeltaTraceRequest, DeltaTraceResponse } from "../types/compare";

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

import type { RaceLabSession, RunLapList } from "../types/session";
import type { TrackMapIndexEntry, TrackMapPackage } from "../types/trackMap";

export function importMt2File(file: File): Promise<TrackMapIndexEntry> {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_BASE}/api/imports/mt2`, {
    method: "POST",
    body: form,
  }).then(async (response) => {
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `Import failed: ${response.status}`);
    }
    return response.json() as Promise<TrackMapIndexEntry>;
  });
}

export function importMt2Folder(folderPath: string): Promise<{ imported: number; entries: TrackMapIndexEntry[] }> {
  return requestJson<{ imported: number; entries: TrackMapIndexEntry[] }>("/api/imports/mt2-folder", {
    method: "POST",
    body: JSON.stringify({ folder_path: folderPath }),
  });
}

export function fetchTrackMaps(): Promise<TrackMapIndexEntry[]> {
  return requestJson<TrackMapIndexEntry[]>("/api/track-maps");
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

export function fetchRunLapList(runId: string): Promise<RunLapList> {
  return requestJson<RunLapList>(`/api/sessions/runs/${encodeURIComponent(runId)}/laps`);
}

export function fetchRunTrackMapPackage(
  runId: string,
  options?: { lap?: number; target_zone_start_pct?: number; target_zone_end_pct?: number },
): Promise<TrackMapPackage> {
  const params = new URLSearchParams();
  if (options?.lap != null) params.set("lap", String(options.lap));
  if (options?.target_zone_start_pct != null) params.set("target_zone_start_pct", String(options.target_zone_start_pct));
  if (options?.target_zone_end_pct != null) params.set("target_zone_end_pct", String(options.target_zone_end_pct));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return requestJson<TrackMapPackage>(`/api/runs/${encodeURIComponent(runId)}/track-map-package${suffix}`);
}
