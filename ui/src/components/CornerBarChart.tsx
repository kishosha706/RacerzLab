/** Four-corner bar chart for comparing LF/RF/LR/RR values. */
import { useMemo } from "react";
import type { TraceResponse } from "../types/telemetry";
import { getTraceValues } from "../utils/channelFormat";

type CornerBarChartProps = {
  trace: TraceResponse | null;
  /** Channel name prefix, e.g. "lf_shock_activity_index" — the prefix is replaced per corner */
  channelPrefix: string;
  /** Display label for the value */
  label?: string;
  /** Unit suffix */
  unit?: string;
  /** Max value for scaling (auto if not set) */
  maxValue?: number;
  /** Color for bars */
  color?: string;
  /** Number of decimal places */
  decimals?: number;
};

const CORNERS = ["LF", "RF", "LR", "RR"] as const;
const CORNER_PREFIXES = ["lf_", "rf_", "lr_", "rr_"] as const;

export function CornerBarChart({
  trace,
  channelPrefix,
  label,
  unit,
  maxValue,
  color = "#3b82f6",
  decimals = 2,
}: CornerBarChartProps) {
  // Extract the suffix after the corner prefix (e.g., "lf_shock_activity_index" -> "shock_activity_index")
  const suffix = channelPrefix.replace(/^(lf_|rf_|lr_|rr_)/, "");

  const values = useMemo(() => {
    return CORNER_PREFIXES.map((prefix) => {
      const ch = `${prefix}${suffix}`;
      const vals = getTraceValues(trace, ch);
      const v = vals.length > 0 ? vals[vals.length - 1] : null;
      return typeof v === "number" && Number.isFinite(v) ? v : null;
    });
  }, [trace, suffix]);

  const max = maxValue ?? Math.max(...values.filter((v): v is number => v != null), 1);

  const hasData = values.some((v) => v != null);
  if (!hasData) {
    return (
      <div className="corner-bar-chart">
        {label && <div className="corner-bar-label">{label}</div>}
        <div className="corner-bar-empty">No data</div>
      </div>
    );
  }

  return (
    <div className="corner-bar-chart">
      {label && <div className="corner-bar-label">{label}</div>}
      <div className="corner-bar-grid">
        {CORNERS.map((corner, i) => {
          const v = values[i];
          const pct = v != null ? Math.min(100, Math.max(0, (v / max) * 100)) : 0;
          return (
            <div key={corner} className="corner-bar-item">
              <div className="corner-bar-track">
                <div
                  className="corner-bar-fill"
                  style={{
                    height: `${pct}%`,
                    backgroundColor: v != null ? color : "#475569",
                    opacity: v != null ? 1 : 0.3,
                  }}
                />
              </div>
              <div className="corner-bar-value">
                {v != null ? v.toFixed(decimals) : "—"}
                {v != null && unit ? ` ${unit}` : ""}
              </div>
              <div className="corner-bar-corner">{corner}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
