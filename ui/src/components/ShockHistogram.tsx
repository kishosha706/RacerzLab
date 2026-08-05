import { useMemo } from "react";
import type { ShockSettingRecommendation } from "../types/shockReader";

export type ShockSetupField = {
  label: string;
  value: string;
  unavailable?: boolean;
  recommendation?: ShockSettingRecommendation | null;
};

type ShockHistogramProps = {
  corner: string;
  color?: string;
  samples: number[];
  axisLimit: number;
  bucketThreshold: number;
  setupFields: ShockSetupField[];
  setupSide?: "left" | "right";
  repeatabilitySummary?: string;
  learningMode?: boolean;
  unavailableReason?: string;
};

type HistogramBin = {
  count: number;
  center: number;
  percent: number;
  side: "rebound" | "center" | "bump";
};

type HistogramModel = {
  bins: HistogramBin[];
  maxPercent: number;
  clippedPercent: number;
  min: number;
  max: number;
  avgReboundMag: number | null;
  avgBump: number | null;
  reboundHighPct: number;
  reboundLowPct: number;
  bumpLowPct: number;
  bumpHighPct: number;
};

function recommendationBadgeText(recommendation?: ShockSettingRecommendation | null): string {
  if (!recommendation) return "action withheld";
  const isSlope = recommendation.setting === "hs_compression_slope" || recommendation.setting === "hs_rebound_slope";
  if (isSlope && recommendation.direction === "needs_more_evidence") return "slope withheld";
  if (isSlope && recommendation.direction === "blocked") return "slope limit";
  if (isSlope && recommendation.direction === "hold") return "hold curve shape";
  if (isSlope && (recommendation.direction === "add" || recommendation.direction === "subtract")) {
    const shape = recommendation.direction === "add" ? "more linear" : "more digressive";
    if (recommendation.delta != null && recommendation.suggested_value != null) {
      const sign = recommendation.delta > 0 ? "+" : "";
      return `${shape} ${sign}${recommendation.delta} → ${recommendation.suggested_value}`;
    }
    return shape;
  }
  if (recommendation.direction === "blocked") return "limit";
  if (recommendation.direction === "needs_more_evidence") return recommendation.blocked_reason === "setup value missing" ? "need setup" : "need data";
  if (recommendation.direction === "hold") return "hold";
  if (recommendation.delta != null && recommendation.suggested_value != null) {
    const sign = recommendation.delta > 0 ? "+" : "";
    return `${sign}${recommendation.delta} -> ${recommendation.suggested_value}`;
  }
  if (recommendation.blocked_reason === "setup value missing") return "need setup";
  return recommendation.direction === "add" ? "add" : "subtract";
}

function recommendationTitle(recommendation?: ShockSettingRecommendation | null, learningMode = false): string {
  if (!recommendation) return "Action withheld: no qualified shock-reader recommendation is available for this setting.";
  const bits = [
    `Action: ${recommendation.action_text}`,
    `Expected: ${recommendation.expected_effect}`,
    `Change size: ${recommendation.change_size_explanation}`,
    `Keep if: ${recommendation.keep_if}`,
    `Undo if: ${recommendation.undo_if}`,
  ];
  if (recommendation.blocked_reason) bits.push(`Action withheld: ${recommendation.blocked_reason}`);
  if (learningMode) {
    bits.push(
      `Why: ${recommendation.reason_short}`,
      `Goal: ${recommendation.goal}`,
      `Trade-off: ${recommendation.tradeoff}`,
      `Watch: ${recommendation.watch_for.join("; ")}`,
    );
  }
  return bits.join("\n");
}

const CHART_WIDTH = 720;
const CHART_HEIGHT = 260;
const CHART_PADDING = { top: 32, right: 46, bottom: 32, left: 46 };
const DEFAULT_PERCENT_AXIS_MAX = 35;
const TICK_EPSILON = 0.000001;
const DEFAULT_BIN_WIDTH_IN_S = 0.5;
const CENTER_DEADBAND_IN_S = 0.05;
const AXIS_LABEL_INTERVAL_IN_S = DEFAULT_BIN_WIDTH_IN_S * 2;

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function roundTick(value: number): number {
  return Number(value.toFixed(3));
}

function sameTick(a: number, b: number): boolean {
  return Math.abs(a - b) < TICK_EPSILON;
}

function buildShockAxisTicks(axisLimit: number): number[] {
  if (!Number.isFinite(axisLimit) || axisLimit <= 0) return [0];

  const step = AXIS_LABEL_INTERVAL_IN_S;
  const start = Math.ceil(-axisLimit / step) * step;
  const end = Math.floor(axisLimit / step) * step;
  const ticks: number[] = [];

  for (let value = start; value <= end + TICK_EPSILON; value += step) {
    ticks.push(roundTick(value));
  }

  if (!ticks.some((tick) => sameTick(tick, 0))) ticks.push(0);
  return ticks.sort((a, b) => a - b);
}

function buildShockMinorAxisTicks(axisLimit: number, majorTicks: number[]): number[] {
  if (!Number.isFinite(axisLimit) || axisLimit <= 0) return [];

  const minorStep = DEFAULT_BIN_WIDTH_IN_S;
  const start = Math.ceil(-axisLimit / minorStep) * minorStep;
  const end = Math.floor(axisLimit / minorStep) * minorStep;
  const ticks: number[] = [];

  for (let value = start; value <= end + TICK_EPSILON; value += minorStep) {
    const rounded = roundTick(value);
    if (!majorTicks.some((major) => sameTick(major, rounded))) ticks.push(rounded);
  }

  return ticks;
}

function buildPercentAxisTicks(percentAxisMax: number): number[] {
  const mid = Math.round((percentAxisMax / 2) / 5) * 5;
  return Array.from(new Set([0, mid, percentAxisMax])).sort((a, b) => a - b);
}

function formatShockAxisTick(value: number): string {
  const normalized = sameTick(value, 0) ? 0 : value;
  if (sameTick(normalized, Math.round(normalized))) return `${Math.round(normalized)}`;
  if (sameTick(normalized * 2, Math.round(normalized * 2))) return normalized.toFixed(1);
  return normalized.toFixed(2);
}

export function scaleShockX(value: number, rangeAbs: number, plotLeft: number, plotWidth: number): number {
  return plotLeft + ((value + rangeAbs) / (rangeAbs * 2)) * plotWidth;
}

export function buildShockBinCenters(rangeAbs: number, binWidth: number): number[] {
  if (!Number.isFinite(rangeAbs) || rangeAbs <= 0 || !Number.isFinite(binWidth) || binWidth <= 0) return [];

  const halfBinCount = Math.round(rangeAbs / binWidth);
  const centers: number[] = [];
  for (let index = -halfBinCount; index <= halfBinCount; index += 1) {
    centers.push(roundTick(index * binWidth));
  }

  if (!centers.some((center) => sameTick(center, 0))) centers.push(0);
  return centers
    .filter((center) => center >= -rangeAbs - TICK_EPSILON && center <= rangeAbs + TICK_EPSILON)
    .sort((a, b) => a - b);
}

export function assignShockSampleToCenteredBin(value: number, binCenters: number[], binWidth: number): number | null {
  if (!Number.isFinite(value) || binCenters.length === 0 || !Number.isFinite(binWidth) || binWidth <= 0) return null;

  const minCenter = binCenters[0];
  const maxCenter = binCenters[binCenters.length - 1];
  const nearestCenter = roundTick(Math.round(value / binWidth) * binWidth);
  return Math.max(minCenter, Math.min(maxCenter, nearestCenter));
}

export function buildShockHistogram(samples: number[], binCenters: number[], binWidth: number): HistogramBin[] {
  const validSamples = samples.filter((value) => Number.isFinite(value));
  if (validSamples.length === 0 || binCenters.length === 0) return [];

  const centerKey = (value: number) => roundTick(value).toFixed(3);
  const counts = new Map(binCenters.map((center) => [centerKey(center), 0]));

  for (const value of validSamples) {
    const center = assignShockSampleToCenteredBin(value, binCenters, binWidth);
    if (center == null) continue;
    const key = centerKey(center);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  return binCenters.map((center) => ({
    count: counts.get(centerKey(center)) ?? 0,
    center,
    percent: ((counts.get(centerKey(center)) ?? 0) / validSamples.length) * 100,
    side: (center < 0 ? "rebound" : center > 0 ? "bump" : "center") as "rebound" | "center" | "bump",
  }));
}

function blendHexWithWhite(hex: string, amount: number): string {
  const safe = hex.replace("#", "");
  const normalized = safe.length === 3 ? safe.split("").map((char) => `${char}${char}`).join("") : safe;
  if (normalized.length !== 6) return hex;

  const mix = Math.max(0, Math.min(1, amount));
  const rgb = [0, 2, 4].map((index) => parseInt(normalized.slice(index, index + 2), 16));
  const blended = rgb.map((channel) => Math.round(channel + ((255 - channel) * mix)));
  return `#${blended.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function buildHistogramModel(samples: number[], axisLimit: number, bucketThreshold: number, binWidth: number): HistogramModel | null {
  const validSamples = samples.filter((value) => Number.isFinite(value));
  if (!Number.isFinite(axisLimit) || axisLimit <= 0 || validSamples.length === 0) return null;

  const binCenters = buildShockBinCenters(axisLimit, binWidth);
  if (binCenters.length < 2 || !binCenters.some((center) => sameTick(center, 0))) return null;

  const min = Math.min(...validSamples);
  const max = Math.max(...validSamples);
  const clipped = validSamples.filter((value) => Math.abs(value) > axisLimit).length;

  const negatives = validSamples.filter((value) => value < 0);
  const positives = validSamples.filter((value) => value > 0);
  const total = validSamples.length;
  const highThreshold = Math.min(Math.abs(bucketThreshold), axisLimit);
  const deadband = Math.min(CENTER_DEADBAND_IN_S, highThreshold / 2);
  const binsModel = buildShockHistogram(validSamples, binCenters, binWidth);
  const maxPercent = Math.max(1, ...binsModel.map((bin) => bin.percent));

  const reboundHighCount = validSamples.filter((value) => value <= -highThreshold).length;
  const reboundLowCount = validSamples.filter((value) => value > -highThreshold && value < -deadband).length;
  const bumpLowCount = validSamples.filter((value) => value > deadband && value < highThreshold).length;
  const bumpHighCount = validSamples.filter((value) => value >= highThreshold).length;
  const movingTotal = reboundHighCount + reboundLowCount + bumpLowCount + bumpHighCount;
  const movingPercent = (count: number) => movingTotal > 0 ? (count / movingTotal) * 100 : 0;
  const reboundHighPct = movingPercent(reboundHighCount);
  const reboundLowPct = movingPercent(reboundLowCount);
  const bumpLowPct = movingPercent(bumpLowCount);
  const bumpHighPct = movingPercent(bumpHighCount);

  return {
    bins: binsModel,
    maxPercent,
    clippedPercent: (clipped / total) * 100,
    min,
    max,
    avgReboundMag: average(negatives.map((value) => Math.abs(value))),
    avgBump: average(positives),
    reboundHighPct,
    reboundLowPct,
    bumpLowPct,
    bumpHighPct,
  };
}

export function ShockHistogram({
  corner,
  color = "#38bdf8",
  samples,
  axisLimit,
  bucketThreshold,
  setupFields,
  setupSide = "left",
  repeatabilitySummary,
  learningMode = false,
  unavailableReason = "Shock movement telemetry unavailable for this run.",
}: ShockHistogramProps) {
  const histogram = useMemo(
    () => buildHistogramModel(samples, axisLimit, bucketThreshold, DEFAULT_BIN_WIDTH_IN_S),
    [samples, axisLimit, bucketThreshold],
  );

  const chartInnerWidth = CHART_WIDTH - CHART_PADDING.left - CHART_PADDING.right;
  const chartInnerHeight = CHART_HEIGHT - CHART_PADDING.top - CHART_PADDING.bottom;
  const scaleX = (value: number) => scaleShockX(value, axisLimit, CHART_PADDING.left, chartInnerWidth);
  const zeroX = scaleX(0);
  const highThreshold = Math.min(Math.abs(bucketThreshold), axisLimit);
  const zoneRegions = [
    { key: "rebound-high", start: -axisLimit, end: -highThreshold, className: "rebound-high" },
    { key: "rebound-low", start: -highThreshold, end: 0, className: "rebound-low" },
    { key: "bump-low", start: 0, end: highThreshold, className: "bump-low" },
    { key: "bump-high", start: highThreshold, end: axisLimit, className: "bump-high" },
  ].filter((zone) => zone.end > zone.start);
  const zoneBoundaries = [
    { key: "rebound-high", value: -highThreshold, className: "shock-threshold-line" },
    { key: "bump-high", value: highThreshold, className: "shock-threshold-line" },
  ];
  const percentAxisMax = DEFAULT_PERCENT_AXIS_MAX;
  const yTicks = buildPercentAxisTicks(percentAxisMax);
  const xTicks = buildShockAxisTicks(axisLimit);
  const xMinorTicks = buildShockMinorAxisTicks(axisLimit, xTicks);
  const clipPathId = `shock-plot-${corner.toLowerCase().replace(/[^a-z0-9-]/g, "")}`;

  return (
    <section className={`shock-panel setup-${setupSide}`} aria-label={`${corner} shock distribution`} data-analysis-surface="damper_velocity_histogram">
      <div className="shock-panel-body">
        <aside className="shock-setup-strip" aria-label={`${corner} damper setup context`}>
          <div className="shock-setup-strip-title">Setup</div>
          <div className="shock-setup-grid">
            {setupFields.map((field) => (
              <div
                key={field.label}
                className={`shock-setup-field${field.unavailable ? " unavailable" : ""}`}
              >
                <span className="shock-setup-label">{field.label}</span>
                <strong>{field.value}</strong>
                <span
                  className={`shock-setup-recommendation-badge ${field.recommendation?.direction ?? "needs_more_evidence"}`}
                  title={recommendationTitle(field.recommendation, learningMode)}
                >
                  {recommendationBadgeText(field.recommendation)}
                </span>
              </div>
            ))}
          </div>
          {repeatabilitySummary && (
            <p className="shock-repeatability-note" title={repeatabilitySummary}>
              {learningMode ? repeatabilitySummary : repeatabilitySummary.split(" · ")[0]}
            </p>
          )}
        </aside>

        <div className="shock-panel-main">
          {histogram ? (
            <div className="shock-chart-shell">
              <div className="shock-chart-stage">
                <div className="shock-chart-overlay" aria-label={`${corner} summary overlay`}>
                  <span className="shock-overlay-channel" style={{ color }}>{corner}shockVel</span>
                  <div className="shock-overlay-metric avg-rebound">
                    <span>Avg R</span>
                    <strong>{histogram.avgReboundMag?.toFixed(2) ?? "n/a"}</strong>
                  </div>
                  <div className="shock-overlay-metric rebound-high">
                    <span>R Hi</span>
                    <strong>{histogram.reboundHighPct.toFixed(1)}</strong>
                  </div>
                  <div className="shock-overlay-metric rebound-low">
                    <span>R Lo</span>
                    <strong>{histogram.reboundLowPct.toFixed(1)}</strong>
                  </div>
                  <span className="shock-overlay-center-gap" aria-hidden="true" />
                  <div className="shock-overlay-metric bump-low">
                    <span>B Lo</span>
                    <strong>{histogram.bumpLowPct.toFixed(1)}</strong>
                  </div>
                  <div className="shock-overlay-metric bump-high">
                    <span>B Hi</span>
                    <strong>{histogram.bumpHighPct.toFixed(1)}</strong>
                  </div>
                  <div className="shock-overlay-metric avg-bump">
                    <span>Avg B</span>
                    <strong>{histogram.avgBump?.toFixed(2) ?? "n/a"}</strong>
                  </div>
                  <span className="shock-overlay-unit">[in/s]</span>
                </div>
                <svg
                  className="shock-panel-svg"
                  viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
                  role="img"
                  aria-label={`${corner} shock histogram, rebound on the left and bump on the right`}
                >
                  <defs>
                    <clipPath id={clipPathId}>
                      <rect
                        x={CHART_PADDING.left}
                        y={CHART_PADDING.top}
                        width={chartInnerWidth}
                        height={chartInnerHeight}
                      />
                    </clipPath>
                  </defs>
                  <text
                    x={15}
                    y={CHART_PADDING.top + chartInnerHeight / 2}
                    className="shock-axis-label"
                    transform={`rotate(-90 15 ${CHART_PADDING.top + chartInnerHeight / 2})`}
                    textAnchor="middle"
                  >
                    Percent
                  </text>
                  {zoneRegions.map((zone) => (
                    <rect
                      key={zone.key}
                      x={scaleX(zone.start)}
                      y={CHART_PADDING.top}
                      width={scaleX(zone.end) - scaleX(zone.start)}
                      height={chartInnerHeight}
                      className={`shock-zone-region ${zone.className}`}
                    />
                  ))}
                  {xMinorTicks.map((tick) => {
                    const x = scaleX(tick);
                    return (
                      <line
                        key={`minor-${tick}`}
                        x1={x}
                        x2={x}
                        y1={CHART_PADDING.top}
                        y2={CHART_HEIGHT - CHART_PADDING.bottom}
                        className="shock-gridline minor-vertical"
                      />
                    );
                  })}
                  {yTicks.map((tick) => {
                    const y = CHART_PADDING.top + chartInnerHeight - ((tick / percentAxisMax) * chartInnerHeight);
                    return (
                      <g key={tick}>
                        <line
                          x1={CHART_PADDING.left}
                          x2={CHART_WIDTH - CHART_PADDING.right}
                          y1={y}
                          y2={y}
                          className="shock-gridline"
                        />
                        <text x={CHART_PADDING.left - 6} y={y + 3} className="shock-axis-label" textAnchor="end">
                          {tick.toFixed(0)}
                        </text>
                      </g>
                    );
                  })}
                  {xTicks.map((tick) => {
                    const x = scaleX(tick);
                    return (
                      <g key={tick}>
                        <line
                          x1={x}
                          x2={x}
                          y1={CHART_PADDING.top}
                          y2={CHART_HEIGHT - CHART_PADDING.bottom}
                          className="shock-gridline vertical"
                        />
                        <text
                          x={x}
                          y={CHART_HEIGHT - 10}
                          className="shock-axis-label"
                          textAnchor={sameTick(tick, -axisLimit) ? "start" : sameTick(tick, axisLimit) ? "end" : "middle"}
                          dominantBaseline="hanging"
                        >
                          {formatShockAxisTick(tick)}
                        </text>
                      </g>
                    );
                  })}
                  <text
                    x={CHART_PADDING.left + chartInnerWidth * 0.28}
                    y={CHART_PADDING.top + 13}
                    className="shock-zone-label"
                    textAnchor="middle"
                  >
                    Rebound
                  </text>
                  <text
                    x={CHART_PADDING.left + chartInnerWidth * 0.72}
                    y={CHART_PADDING.top + 13}
                    className="shock-zone-label"
                    textAnchor="middle"
                  >
                    Bump
                  </text>
                  <g clipPath={`url(#${clipPathId})`}>
                    {histogram.bins.map((bin, index) => {
                      const isOverAxisMax = bin.percent > percentAxisMax;
                      const height = (Math.min(bin.percent, percentAxisMax) / percentAxisMax) * chartInnerHeight;
                      const binLeft = scaleX(bin.center - (DEFAULT_BIN_WIDTH_IN_S / 2));
                      const binRight = scaleX(bin.center + (DEFAULT_BIN_WIDTH_IN_S / 2));
                      const binWidthPx = binRight - binLeft;
                      const gap = Math.min(1.6, Math.max(0.7, binWidthPx * 0.16));
                      const x = binLeft + gap / 2;
                      const y = CHART_PADDING.top + chartInnerHeight - height;
                      const distanceRatio = Math.min(1, Math.abs(bin.center) / Math.max(axisLimit, 0.001));
                      const fill = blendHexWithWhite(color, 0.12 + (distanceRatio * 0.52));
                      return (
                        <rect
                          key={`${corner}-${index}`}
                          x={x}
                          y={y}
                          width={Math.max(binWidthPx - gap, 1)}
                          height={height}
                          className={`shock-bar ${bin.side}${isOverAxisMax ? " over-limit" : ""}`}
                          fill={fill}
                        />
                      );
                    })}
                  </g>
                  {zoneBoundaries.map((boundary) => (
                    <line
                      key={boundary.key}
                      x1={scaleX(boundary.value)}
                      x2={scaleX(boundary.value)}
                      y1={CHART_PADDING.top}
                      y2={CHART_HEIGHT - CHART_PADDING.bottom}
                      className={boundary.className}
                    />
                  ))}
                  <line x1={zeroX} x2={zeroX} y1={CHART_PADDING.top} y2={CHART_HEIGHT - CHART_PADDING.bottom} className="shock-zero-line" />
                  <line
                    x1={CHART_PADDING.left}
                    x2={CHART_PADDING.left}
                    y1={CHART_PADDING.top}
                    y2={CHART_HEIGHT - CHART_PADDING.bottom}
                    className="shock-axis-line"
                  />
                  <line
                    x1={CHART_PADDING.left}
                    x2={CHART_WIDTH - CHART_PADDING.right}
                    y1={CHART_HEIGHT - CHART_PADDING.bottom}
                    y2={CHART_HEIGHT - CHART_PADDING.bottom}
                    className="shock-axis-line"
                  />
                  <rect
                    x={CHART_PADDING.left}
                    y={CHART_PADDING.top}
                    width={chartInnerWidth}
                    height={chartInnerHeight}
                    className="shock-plot-outline"
                  />
                </svg>
              </div>
            </div>
          ) : (
            <div className="shock-panel-empty">
              <span>{unavailableReason}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
