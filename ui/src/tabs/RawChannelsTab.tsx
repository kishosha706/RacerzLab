import { Copy, Info, Pin, Search } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { getChannelConfidenceLevel, getChannelDisclaimer } from "../utils/channelMeta";
import type { ChannelCatalogItem, RunOverview, TraceResponse } from "../types/telemetry";
import { ProxyBadge } from "../components/ProxyBadge";

type RawChannelsTabProps = {
  overview: RunOverview;
  trace: TraceResponse | null;
  channels: ChannelCatalogItem[];
  loadError?: string | null;
  onRetry?: () => void;
};

function formatNumber(value: number | null | undefined) {
  if (value == null) return "n/a";
  return Math.abs(value) >= 100 ? value.toFixed(1) : value.toFixed(4);
}

export function channelAllowsContinuousCustomLane(
  channel: Pick<ChannelCatalogItem, "engineering_role" | "engineering_admission_state">,
): boolean {
  return channel.engineering_role !== "pit_snapshot"
    && channel.engineering_admission_state !== "pit_boundary_only";
}

/** Proper useEffect-based debounce hook for search input. */
function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function RawChannelsTab({ overview, trace, channels, loadError = null, onRetry }: RawChannelsTabProps) {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 200);
  const [pinnedChannels, setPinnedChannels] = useState<string[]>(() => {
    try { return JSON.parse(sessionStorage.getItem("racelab_pinned_channels") ?? "[]"); }
    catch { return []; }
  });
  const [expandedChannel, setExpandedChannel] = useState<string | null>(null);
  const [confidenceFilter, setConfidenceFilter] = useState<string>("all");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const { selectChannel, setWorkspace } = useTelemetrySelection();

  const togglePin = useCallback((name: string) => {
    setPinnedChannels(prev => {
      const next = prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name];
      sessionStorage.setItem("racelab_pinned_channels", JSON.stringify(next));
      return next;
    });
  }, []);

  const handleCopyName = useCallback((name: string) => {
    navigator.clipboard?.writeText(name).catch(() => {});
  }, []);

  const handlePinToPlatform = useCallback((channel: ChannelCatalogItem) => {
    if (!channelAllowsContinuousCustomLane(channel)) return;
    selectChannel(channel.name, "channel_catalog");
    setWorkspace("platform_trace", "channel_catalog");
  }, [selectChannel, setWorkspace]);

  const filtered = useMemo(() => {
    let result = channels;
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase();
      result = result.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          (c.unit && c.unit.toLowerCase().includes(q)) ||
          (c.description && c.description.toLowerCase().includes(q)),
      );
    }
    if (confidenceFilter !== "all") {
      result = result.filter((channel) => {
        const level = channel.is_proxy
          ? "proxy"
          : channel.is_calculated
            ? "calculated"
            : getChannelConfidenceLevel(channel.name);
        return level === confidenceFilter;
      });
    }
    if (roleFilter !== "all") {
      result = result.filter((channel) => channel.engineering_role === roleFilter);
    }
    return result;
  }, [channels, debouncedSearch, confidenceFilter, roleFilter]);

  return (
    <section className="workspace-section">
      <div className="section-heading-row">
        <div>
          <h2>Telemetry Capabilities</h2>
          <p className="section-note">
            {channels.length} archived and calculated channels. This Learning-mode inventory is observation-only and cannot create mechanism or setup authority.
          </p>
        </div>
        <div className="catalog-summary">
          <span>{overview.session.telemetry_rate_hz ?? "n/a"} Hz</span>
          <span>{overview.session.variable_count ?? "n/a"} vars</span>
          <span>{trace?.sample_count ?? 0} trace samples</span>
        </div>
      </div>
      {loadError && (
        <div className="analysis-state" role="alert">
          <strong>Telemetry capability inventory unavailable</strong>
          <p>{loadError}</p>
          {onRetry && (
            <button type="button" className="secondary-button" onClick={onRetry}>
              Retry capability inventory
            </button>
          )}
        </div>
      )}
      {/* Pinned channels */}
      {pinnedChannels.length > 0 && (
        <div style={{ marginBottom: 8, display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 10, color: "#8d9aaa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Pinned:</span>
          {pinnedChannels.map((name) => {
            const channel = channels.find((item) => item.name === name);
            const canOpenLane = channel != null && channelAllowsContinuousCustomLane(channel);
            return (
              <button
                type="button"
                key={name}
                disabled={!canOpenLane}
                style={{ fontSize: 10, padding: "2px 6px", background: "rgba(56,189,248,0.1)", border: "1px solid rgba(56,189,248,0.2)", borderRadius: 4, color: "#38bdf8", cursor: canOpenLane ? "pointer" : "default", opacity: canOpenLane ? 1 : 0.72 }}
                onClick={canOpenLane && channel ? () => handlePinToPlatform(channel) : undefined}
                title={canOpenLane ? "Open in Platform Trace" : "Pit-boundary snapshots cannot become continuous on-track evidence"}
                aria-label={canOpenLane ? `Open pinned channel ${name} in Platform Trace` : `Pinned channel ${name} cannot open as a continuous lane`}
              >
                {name} <Pin size={8} style={{ marginLeft: 2 }} />
              </button>
            );
          })}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <Search size={14} style={{ color: "#8d9aaa" }} />
        <input
          type="text"
          aria-label="Search telemetry channels"
          placeholder="Search channels…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: 1,
            padding: "4px 8px",
            background: "#0a0d14",
            border: "1px solid #1f2937",
            borderRadius: 4,
            color: "#e2e8f0",
            fontSize: 12,
          }}
        />
        <select
          aria-label="Filter channels by evidence kind"
          value={confidenceFilter}
          onChange={(e) => setConfidenceFilter(e.target.value)}
          style={{
            padding: "4px 8px",
            background: "#0a0d14",
            border: "1px solid #1f2937",
            borderRadius: 4,
            color: "#e2e8f0",
            fontSize: 11,
          }}
        >
          <option value="all">All</option>
          <option value="measured">Measured</option>
          <option value="calculated">Calculated</option>
          <option value="estimate">Estimate</option>
          <option value="proxy">Proxy</option>
        </select>
        <select
          aria-label="Filter by engineering role"
          value={roleFilter}
          onChange={(event) => setRoleFilter(event.target.value)}
          style={{
            padding: "4px 8px",
            background: "#0a0d14",
            border: "1px solid #1f2937",
            borderRadius: 4,
            color: "#e2e8f0",
            fontSize: 11,
          }}
        >
          <option value="all">All roles</option>
          <option value="admitted_analysis">Admitted</option>
          <option value="measurement_candidate">Candidate</option>
          <option value="corroboration">Corroboration</option>
          <option value="pit_snapshot">Pit snapshot</option>
          <option value="control_state">Control state</option>
          <option value="integrity">Integrity</option>
          <option value="inventory_debug">Inventory / debug</option>
        </select>
        <span style={{ fontSize: 10, color: "#8d9aaa" }}>{filtered.length} of {channels.length}</span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Unit</th>
              <th>Type</th>
              <th>Kind</th>
              <th>Engineering Role</th>
              <th>Min</th>
              <th>Max</th>
              <th>Mean</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((channel) => {
              const isExpanded = expandedChannel === channel.name;
              const disclaimer = getChannelDisclaimer(channel.name);
              const canOpenContinuousLane = channelAllowsContinuousCustomLane(channel);
              return (
                <Fragment key={channel.name}>
                  <tr key={channel.name} style={{ background: pinnedChannels.includes(channel.name) ? "rgba(56,189,248,0.04)" : undefined }}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <button
                          className="trackmap-action-btn"
                          onClick={() => setExpandedChannel(isExpanded ? null : channel.name)}
                          title="Show details"
                          aria-label={`${isExpanded ? "Hide" : "Show"} details for ${channel.name}`}
                        >
                          <Info size={10} />
                        </button>
                        <span title={channel.description ?? undefined}>{channel.name}</span>
                      </div>
                    </td>
                    <td>{channel.unit ?? ""}</td>
                    <td>{channel.type ?? "n/a"}</td>
                    <td>
                      {channel.is_calculated ? (channel.is_proxy ? "proxy" : "calculated") : "raw"}
                      {channel.is_proxy && <span style={{ marginLeft: 4 }}><ProxyBadge kind="proxy" /></span>}
                    </td>
                    <td>
                      {channel.engineering_role?.replace(/_/g, " ") ?? "unreviewed"}
                      {channel.engineering_admission_state && (
                        <small style={{ display: "block" }}>
                          {channel.engineering_admission_state.replace(/_/g, " ")}
                        </small>
                      )}
                    </td>
                    <td>{formatNumber(channel.min)}</td>
                    <td>{formatNumber(channel.max)}</td>
                    <td>{formatNumber(channel.mean)}</td>
                    <td style={{ color: channel.missing_status && channel.missing_status !== "loaded" ? "#f59e0b" : undefined }}>
                      {channel.missing_status ?? "loaded"}
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: 2 }}>
                        <button className="trackmap-action-btn" onClick={() => togglePin(channel.name)} title={pinnedChannels.includes(channel.name) ? "Unpin" : "Pin to workbench"} aria-label={`${pinnedChannels.includes(channel.name) ? "Unpin" : "Pin"} ${channel.name}`}>
                          <Pin size={10} />
                        </button>
                        <button className="trackmap-action-btn" onClick={() => handleCopyName(channel.name)} title="Copy channel name" aria-label={`Copy channel name ${channel.name}`}>
                          <Copy size={10} />
                        </button>
                        <button
                          className="trackmap-action-btn"
                          disabled={!canOpenContinuousLane}
                          onClick={() => handlePinToPlatform(channel)}
                          title={canOpenContinuousLane
                            ? "Open one observation-only custom Platform lane"
                            : "Pit-boundary snapshots cannot become continuous on-track evidence"}
                          aria-label={canOpenContinuousLane
                            ? `Open ${channel.name} as an observation-only Platform lane`
                            : `${channel.name} cannot open as a continuous Platform lane`}
                        >
                          <Pin size={10} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr key={`${channel.name}-detail`}>
                      <td colSpan={10} style={{ padding: "8px 16px", background: "#0a0d14", fontSize: 11 }}>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                          <div>
                            <span className="muted">Identity</span><br />
                            Raw: {channel.raw_name ?? channel.name}<br />
                            Canonical: {channel.canonical_name ?? "not admitted"}
                          </div>
                          <div>
                            <span className="muted">Sampling / health</span><br />
                            {channel.effective_sample_rate_hz ?? channel.base_sample_rate_hz ?? "n/a"} Hz · {channel.variation ?? "unknown"} · {channel.health_status ?? "unknown"}
                          </div>
                          {channel.engineering_authority_limit && (
                            <div style={{ gridColumn: "1 / -1" }}>
                              <span className="muted">Authority limit</span><br />
                              {channel.engineering_authority_limit}
                            </div>
                          )}
                          {channel.description && (
                            <div><span className="muted">Description</span><br />{channel.description}</div>
                          )}
                          {channel.formula && (
                            <div><span className="muted">Formula</span><br /><code style={{ fontSize: 10, color: "#38bdf8" }}>{channel.formula}</code></div>
                          )}
                          {!channel.formula && channel.is_calculated && (
                            <div><span className="muted">Formula</span><br /><span className="muted">Formula unavailable.</span></div>
                          )}
                          {channel.dependencies && channel.dependencies.length > 0 && (
                            <div><span className="muted">Dependencies</span><br />
                              <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginTop: 2 }}>
                                {channel.dependencies.map((dep) => (
                                  <span key={dep} className="channel-chip">{dep}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {disclaimer && (
                            <div style={{ gridColumn: "1 / -1" }}>
                              <span className="muted">⚠ {disclaimer}</span>
                            </div>
                          )}
                          {channel.used_by_charts && channel.used_by_charts.length > 0 && (
                            <div><span className="muted">Used by Charts</span><br />
                              <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginTop: 2 }}>
                                {channel.used_by_charts.map((chart) => (
                                  <span key={chart} className="channel-chip">{chart}</span>
                                ))}
                              </div>
                            </div>
                          )}
                          {channel.used_by_events && channel.used_by_events.length > 0 && (
                            <div><span className="muted">Used by Events</span><br />
                              <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginTop: 2 }}>
                                {channel.used_by_events.map((evt) => (
                                  <span key={evt} className="channel-chip">{evt}</span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
