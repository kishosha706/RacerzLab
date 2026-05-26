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

export function RawChannelsTab({ overview, trace, channels }: RawChannelsTabProps) {
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
            {channels.map((channel) => (
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
