/** Four-corner tire map showing per-corner tire state. */
import type { TraceResponse } from "../types/telemetry";
import { getTraceValues, formatChannelValue, safeStringValue } from "../utils/channelFormat";

type TireMapMode = "pressure" | "pressure_gain" | "temp_spread" | "wear_spread" | "slip" | "camber";

type CornerTireMapProps = {
  trace: TraceResponse | null;
  mode: TireMapMode;
  onModeChange?: (mode: TireMapMode) => void;
};

const MODES: { id: TireMapMode; label: string }[] = [
  { id: "pressure", label: "Pressure" },
  { id: "pressure_gain", label: "Pressure Gain" },
  { id: "temp_spread", label: "Temp Spread" },
  { id: "wear_spread", label: "Wear Spread" },
  { id: "slip", label: "Slip" },
  { id: "camber", label: "Camber" },
];

function cornerValue(trace: TraceResponse | null, corner: string, mode: TireMapMode): string {
  const ch = `${corner}_${mode === "camber" ? "camber_temp_bias_c" : mode === "slip" ? "slip_ratio_proxy" : mode}`;
  const vals = getTraceValues(trace, ch);
  const v = vals.length > 0 ? vals[vals.length - 1] : null;
  if (v == null) return "—";
  if (typeof v === "string") return v;
  return v.toFixed(mode === "pressure" ? 1 : 2);
}

function cornerColor(trace: TraceResponse | null, corner: string, mode: TireMapMode): string {
  const ch = `${corner}_${mode === "camber" ? "camber_temp_bias_c" : mode === "slip" ? "slip_ratio_proxy" : mode}`;
  const vals = getTraceValues(trace, ch);
  const v = vals.length > 0 ? vals[vals.length - 1] : null;
  if (v == null || typeof v === "string") return "#475569";
  const abs = Math.abs(v);
  if (abs > 20) return "#ef4444";
  if (abs > 10) return "#f97316";
  if (abs > 5) return "#f59e0b";
  return "#22c55e";
}

function cornerLabel(trace: TraceResponse | null, corner: string): string {
  const biasCh = `${corner}_camber_bias_label`;
  const vals = getTraceValues(trace, biasCh);
  const v = vals.length > 0 ? vals[vals.length - 1] : null;
  return v ? safeStringValue(v) : "";
}

export function CornerTireMap({ trace, mode, onModeChange }: CornerTireMapProps) {
  return (
    <div className="corner-tire-map">
      <div className="tire-map-mode-select">
        {MODES.map((m) => (
          <button
            key={m.id}
            className={`tire-map-mode-btn${mode === m.id ? " active" : ""}`}
            onClick={() => onModeChange?.(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="tire-map-grid">
        <div className="tire-map-label top">FRONT</div>
        <div className="tire-map-corner lf" style={{ borderColor: cornerColor(trace, "lf", mode) }}>
          <div className="tire-corner-value">{cornerValue(trace, "lf", mode)}</div>
          <div className="tire-corner-label">LF</div>
          <div className="tire-corner-sub">{cornerLabel(trace, "lf")}</div>
        </div>
        <div className="tire-map-corner rf" style={{ borderColor: cornerColor(trace, "rf", mode) }}>
          <div className="tire-corner-value">{cornerValue(trace, "rf", mode)}</div>
          <div className="tire-corner-label">RF</div>
          <div className="tire-corner-sub">{cornerLabel(trace, "rf")}</div>
        </div>
        <div className="tire-map-corner lr" style={{ borderColor: cornerColor(trace, "lr", mode) }}>
          <div className="tire-corner-value">{cornerValue(trace, "lr", mode)}</div>
          <div className="tire-corner-label">LR</div>
          <div className="tire-corner-sub">{cornerLabel(trace, "lr")}</div>
        </div>
        <div className="tire-map-corner rr" style={{ borderColor: cornerColor(trace, "rr", mode) }}>
          <div className="tire-corner-value">{cornerValue(trace, "rr", mode)}</div>
          <div className="tire-corner-label">RR</div>
          <div className="tire-corner-sub">{cornerLabel(trace, "rr")}</div>
        </div>
        <div className="tire-map-label bottom">REAR</div>
      </div>
    </div>
  );
}
