import { Copy, Pin, Search } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import type { ChannelCatalogItem, RunOverview, TraceResponse } from "../types/telemetry";

type RawChannelsTabProps = {
  overview: RunOverview;
  trace: TraceResponse | null;
  channels: ChannelCatalogItem[];
};

function formatNumber(value: number | null | undefined) {
  if (value == null) return "n/a";
  return Math.abs(value) >= 100 ? value.toFixed(1) : value.toFixed(4);
}

/** Simple debounce hook for search input. */
function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  // Use a simple timeout-based debounce
  let timeout: ReturnType<typeof setTimeout> | undefined;
  timeout = setTimeout(() => setDebounced(value), delay);
  // Cleanup on unmount or value change
  useMemo(() => {
    clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return debounced;
}

export function RawChannelsTab({ overview, trace, channels }: RawChannelsTabProps) {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 200);
  const [pinnedChannels, setPinnedChannels] = useState<string[]>(() => {
    try { return JSON.parse(sessionStorage.getItem("racelab_pinned_channels") ?? "[]"); }
    catch { return []; }
  });
  const { selectChannel, setWorkspace, selection } = useTelemetrySelection();

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

  const handlePinToPlatform = useCallback((name: string) => {
    selectChannel(name, "channel_catalog");
    setWorkspace("platform_trace", "channel_catalog");
  }, [selectChannel, setWorkspace]);

  const filtered = useMemo(() => {
    if (!debouncedSearch) return channels;
    const q = debouncedSearch.toLowerCase();
    return channels.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.unit && c.unit.toLowerCase().includes(q)) ||
        (c.description && c.description.toLowerCase().includes(q)),
    );
  }, [channels, debouncedSearch]);

  return (
    <section className="workspace-section">
      <div className="section-heading-row">
        <div>
          <h2>Channel Catalog</h2>
          <p className="section-note">
            {channels.length} raw/calculated channels available from the local telemetry cache.
          </p>
        </div>
        <div className="catalog-summary">
          <span>{overview.session.telemetry_rate_hz ?? "n/a"} Hz</span>
          <span>{overview.session.variable_count ?? "n/a"} vars</span>
          <span>{trace?.sample_count ?? 0} trace samples</span>
        </div>
      </div>
      {/* Pinned channels */}
      {pinnedChannels.length > 0 && (
        <div style={{ marginBottom: 8, display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 10, color: "#8d9aaa", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>Pinned:</span>
          {pinnedChannels.map(name => (
            <span key={name} style={{ fontSize: 10, padding: "2px 6px", background: "rgba(56,189,248,0.1)", border: "1px solid rgba(56,189,248,0.2)", borderRadius: 4, color: "#38bdf8", cursor: "pointer" }}
              onClick={() => handlePinToPlatform(name)} title="Open in Platform Trace">
              {name} <Pin size={8} style={{ marginLeft: 2 }} />
            </span>
          ))}
        </div>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <Search size={14} style={{ color: "#8d9aaa" }} />
        <input
          type="text"
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
            outline: "none",
          }}
        />
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
              <th>Min</th>
              <th>Max</th>
              <th>Mean</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((channel) => (
              <tr key={channel.name} style={{ background: pinnedChannels.includes(channel.name) ? "rgba(56,189,248,0.04)" : undefined }}>
                <td title={channel.description ?? undefined}>{channel.name}</td>
                <td>{channel.unit ?? ""}</td>
                <td>{channel.type ?? "n/a"}</td>
                <td>{channel.is_calculated ? "calculated" : "raw"}</td>
                <td>{formatNumber(channel.min)}</td>
                <td>{formatNumber(channel.max)}</td>
                <td>{formatNumber(channel.mean)}</td>
                <td>{channel.missing_status ?? "loaded"}</td>
                <td>
                  <div style={{ display: "flex", gap: 2 }}>
                    <button className="trackmap-action-btn" onClick={() => togglePin(channel.name)} title={pinnedChannels.includes(channel.name) ? "Unpin" : "Pin to workbench"}>
                      <Pin size={10} />
                    </button>
                    <button className="trackmap-action-btn" onClick={() => handleCopyName(channel.name)} title="Copy channel name">
                      <Copy size={10} />
                    </button>
                    <button className="trackmap-action-btn" onClick={() => handlePinToPlatform(channel.name)} title="Open in Platform Trace">
                      <Pin size={10} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
