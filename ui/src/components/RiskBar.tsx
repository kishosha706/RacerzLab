/** Horizontal risk bar showing severity level. */
type RiskBarProps = {
  value: number | null | undefined;
  label?: string;
  thresholds?: number[];
  colors?: string[];
};

const DEFAULT_THRESHOLDS = [0, 0.38, 0.72, 0.92, 1.0];
const DEFAULT_COLORS = ["#22c55e", "#f59e0b", "#f97316", "#ef4444", "#dc2626"];

export function RiskBar({ value, label, thresholds = DEFAULT_THRESHOLDS, colors = DEFAULT_COLORS }: RiskBarProps) {
  if (value == null || Number.isNaN(value)) {
    return (
      <div className="risk-bar">
        <div className="risk-bar-track" style={{ opacity: 0.3 }}>
          <div className="risk-bar-fill" style={{ width: "0%" }} />
        </div>
        {label && <span className="risk-bar-label">Unavailable</span>}
      </div>
    );
  }

  const pct = Math.min(100, Math.max(0, value * 100));
  let color = colors[0];
  let riskClass = "";
  for (let i = thresholds.length - 1; i >= 0; i--) {
    if (value >= thresholds[i]) { color = colors[i]; break; }
  }
  if (value >= 0.92) riskClass = " risk-critical";
  else if (value >= 0.72) riskClass = " risk-high";
  else if (value >= 0.38) riskClass = " risk-watch";

  return (
    <div className="risk-bar">
      <div className="risk-bar-track">
        <div className={`risk-bar-fill${riskClass}`} style={{ width: `${pct}%`, background: color }} />
      </div>
      {label && <span className="risk-bar-label" style={{ color }}>{label}</span>}
    </div>
  );
}
