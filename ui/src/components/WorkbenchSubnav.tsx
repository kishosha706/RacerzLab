/** Internal workbench sub-navigation for PlatformTab. */
export type WorkbenchView =
  | "balance" | "rear_scrape" | "aero_load" | "scrub_steering"
  | "tires" | "shocks" | "grade_pull";

export const WORKBENCH_VIEWS: { id: WorkbenchView; label: string; icon: string }[] = [
  { id: "balance", label: "Balance", icon: "⚖" },
  { id: "rear_scrape", label: "Rear Scrape", icon: "R" },
  { id: "aero_load", label: "Aero Load", icon: "🌊" },
  { id: "scrub_steering", label: "Scrub / Steering", icon: "↩" },
  { id: "tires", label: "Tires", icon: "◯" },
  { id: "shocks", label: "Shocks", icon: "〰" },
  { id: "grade_pull", label: "Grade / Pull", icon: "⛰" },
];

type WorkbenchSubnavProps = {
  active: WorkbenchView;
  onChange: (view: WorkbenchView) => void;
};

export function WorkbenchSubnav({ active, onChange }: WorkbenchSubnavProps) {
  return (
    <nav className="workbench-subnav">
      {WORKBENCH_VIEWS.map((v) => (
        <button
          key={v.id}
          className={`workbench-subnav-item${active === v.id ? " active" : ""}`}
          onClick={() => onChange(v.id)}
          aria-pressed={active === v.id}
          aria-label={`Show ${v.label} platform section`}
        >
          <span className="workbench-subnav-icon">{v.icon}</span>
          <span>{v.label}</span>
        </button>
      ))}
    </nav>
  );
}
