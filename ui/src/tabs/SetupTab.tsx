import type { RunOverview } from "../types/telemetry";

type SetupTabProps = {
  overview: RunOverview;
};

export function SetupTab({ overview }: SetupTabProps) {
  const setup = overview.setup_snapshot;

  return (
    <section className="workspace-section setup-grid">
      <h2>Setup</h2>
      <dl>
        <div><dt>Tape</dt><dd>{setup?.tape_percent ?? "n/a"}%</dd></div>
        <div><dt>Rear gear</dt><dd>{setup?.rear_end_ratio ?? "n/a"}</dd></div>
        <div><dt>Front ride heights</dt><dd>LF {setup?.lf_ride_height_mm ?? "n/a"} / RF {setup?.rf_ride_height_mm ?? "n/a"} mm</dd></div>
        <div><dt>Rear ride heights</dt><dd>LR {setup?.lr_ride_height_mm ?? "n/a"} / RR {setup?.rr_ride_height_mm ?? "n/a"} mm</dd></div>
        <div><dt>Springs</dt><dd>LF {setup?.lf_front_spring_n_per_mm ?? "n/a"} / RF {setup?.rf_front_spring_n_per_mm ?? "n/a"} / LR {setup?.lr_rear_spring_n_per_mm ?? "n/a"} / RR {setup?.rr_rear_spring_n_per_mm ?? "n/a"}</dd></div>
        <div><dt>Steering</dt><dd>{setup?.steering_ratio ?? "n/a"} / {setup?.steering_offset_deg ?? "n/a"} deg</dd></div>
      </dl>
    </section>
  );
}
