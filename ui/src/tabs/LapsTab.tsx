import type { RunOverview } from "../types/telemetry";

type LapsTabProps = {
  overview: RunOverview;
};

export function LapsTab({ overview }: LapsTabProps) {
  return (
    <section className="workspace-section">
      <h2>Laps</h2>
      <table>
        <thead>
          <tr>
            <th>Lap</th>
            <th>Type</th>
            <th>Useful</th>
            <th>Time</th>
            <th>Avg mph</th>
            <th>Tags</th>
          </tr>
        </thead>
        <tbody>
          {overview.laps.map((lap) => (
            <tr key={lap.lap_id}>
              <td>{lap.lap_number}</td>
              <td>{lap.lap_type}</td>
              <td>{lap.is_useful ? "yes" : "no"}</td>
              <td>{lap.lap_time?.toFixed(3) ?? "n/a"}</td>
              <td>{lap.avg_speed_mph?.toFixed(2) ?? "n/a"}</td>
              <td>{lap.classification_tags.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
