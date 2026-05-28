import { Search } from "lucide-react";
import { useMemo, useState } from "react";
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
            </tr>
          </thead>
          <tbody>
            {filtered.map((channel) => (
              <tr key={channel.name}>
                <td title={channel.description ?? undefined}>{channel.name}</td>
                <td>{channel.unit ?? ""}</td>
                <td>{channel.type ?? "n/a"}</td>
                <td>{channel.is_calculated ? "calculated" : "raw"}</td>
                <td>{formatNumber(channel.min)}</td>
                <td>{formatNumber(channel.max)}</td>
                <td>{formatNumber(channel.mean)}</td>
                <td>{channel.missing_status ?? "loaded"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
