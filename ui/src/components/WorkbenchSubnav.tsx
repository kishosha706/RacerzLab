/** Internal workbench sub-navigation for PlatformTab. */
export type WorkbenchView =
  | "balance"
  | "rear_scrape"
  | "aero_load"
  | "scrub_steering"
  | "diffuser"
  | "tires"
  | "shocks"
  | "grade_pull";

export const WORKBENCH_VIEWS: { id: WorkbenchView; label: string; icon: string }[] = [
  { id: "balance", label: "Balance", icon: "BAL" },
  { id: "rear_scrape", label: "Scrape / Scrub", icon: "SCR" },
  { id: "shocks", label: "Shocks", icon: "SHK" },
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
          <span className="workbench-subnav-label">{v.label}</span>
        </button>
      ))}
    </nav>
  );
}
