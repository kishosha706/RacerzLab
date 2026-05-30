/** Lightweight SVG histogram for shock velocity distribution per corner. */
import { useMemo } from "react";
import type { TraceResponse } from "../types/telemetry";
import { getTraceValues } from "../utils/channelFormat";

type ShockHistogramProps = {
  trace: TraceResponse | null;
  /** Channel name for shock velocity, e.g. "lf_shock_vel_in_s" */
  channelName: string;
  /** Corner label */
  corner: string;
  /** Color */
  color?: string;
  /** Number of bins */
  bins?: number;
  /** Height of the SVG */
  height?: number;
  /** Width of the SVG */
  width?: number;
};

export function ShockHistogram({
  trace,
  channelName,
  corner,
  color = "#3b82f6",
  bins = 20,
  height = 60,
  width = 120,
}: ShockHistogramProps) {
  const histogram = useMemo(() => {
    const vals = getTraceValues(trace, channelName);
    const numeric = vals.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    if (numeric.length === 0) return null;

    const min = Math.min(...numeric);
    const max = Math.max(...numeric);
    const range = max - min || 1;
    const binWidth = range / bins;
    const counts = new Array(bins).fill(0);

    for (const v of numeric) {
      const idx = Math.min(bins - 1, Math.floor((v - min) / binWidth));
      counts[idx]++;
    }

    const maxCount = Math.max(...counts, 1);
    return { counts, maxCount, min, max };
  }, [trace, channelName, bins]);

  if (!histogram) {
    return (
      <div className="shock-histogram">
        <div className="shock-histogram-corner">{corner}</div>
        <div className="shock-histogram-empty">—</div>
      </div>
    );
  }

  const { counts, maxCount, min, max } = histogram;
  const barWidth = width / bins;

  return (
    <div className="shock-histogram">
      <div className="shock-histogram-corner">{corner}</div>
      <svg width={width} height={height} className="shock-histogram-svg">
        {counts.map((count, i) => {
          const barHeight = (count / maxCount) * (height - 4);
          const x = i * barWidth;
          const y = height - 2 - barHeight;
          return (
            <rect
              key={i}
              x={x}
              y={y}
              width={Math.max(barWidth - 1, 1)}
              height={barHeight}
              fill={color}
              opacity={0.7 + 0.3 * (count / maxCount)}
              rx={0.5}
            />
          );
        })}
      </svg>
      <div className="shock-histogram-range">
        {min.toFixed(1)} – {max.toFixed(1)}
      </div>
    </div>
  );
}
