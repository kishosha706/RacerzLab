import { AlertTriangle, Thermometer, TrendingDown, TrendingUp } from "lucide-react";
import type { ObservationKind } from "../types/compare";

export interface TireContextProps {
  pressureGainDelta?: number | null;
  tempSpreadDelta?: number | null;
  camberBiasDelta?: number | null;
  wearSpreadDelta?: number | null;
  runLengthLaps?: number | null;
  isShortRun?: boolean;
}

export interface DidItWorkCardProps {
  observation: ObservationKind;
  headline: string;
  confidenceScore: number;           // 0-1
  testDisciplineScore?: number;      // 0-100
  targetZoneDeltaMph?: number | null;
  splitterDeltaMm?: number | null;
  platformRiskDelta?: number | null;
  scrubDelta?: number | null;
  wholeLapDeltaS?: number | null;
  paceNoiseBandS?: number | null;
  eligibleLapCounts?: { baseline: number; test: number } | null;
  evidence: string[];
  warnings: string[];
  setupChanges?: Array<{ label: string; baseline_value: unknown; test_value: unknown }>;
  contextWarnings?: Array<{ label: string; warning: string }>;
  weatherWarning?: string | null;
  tireContext?: TireContextProps | null;
  /** Callbacks */
  onOpenEvidence?: () => void;
  onOpenMap?: () => void;
  disabled?: boolean;
}

const OBSERVATION_COLORS: Record<ObservationKind, string> = {
  observed_improvement: "#22c55e",
  observed_regression: "#ef4444",
  needs_confirmation: "#f59e0b",
  inconclusive: "#8d9aaa",
};

const OBSERVATION_ICONS: Record<ObservationKind, typeof TrendingUp> = {
  observed_improvement: TrendingUp,
  observed_regression: TrendingDown,
  needs_confirmation: AlertTriangle,
  inconclusive: AlertTriangle,
};

function disciplineColor(score: number): string {
  if (score >= 80) return "#22c55e";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

function deltaSign(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "";
  return v > 0 ? "+" : "";
}

function tireContextColor(delta: number | null | undefined): string {
  if (delta == null || Number.isNaN(delta)) return "#8d9aaa";
  const abs = Math.abs(delta);
  if (abs < 2) return "#22c55e";
  if (abs < 5) return "#f59e0b";
  return "#ef4444";
}

export function DidItWorkCard({
  observation, headline, confidenceScore, testDisciplineScore,
  targetZoneDeltaMph, splitterDeltaMm, platformRiskDelta, scrubDelta,
  wholeLapDeltaS, paceNoiseBandS, eligibleLapCounts,
  evidence, warnings,
  setupChanges, contextWarnings, weatherWarning,
  tireContext,
  onOpenEvidence, onOpenMap,
  disabled,
}: DidItWorkCardProps) {
  const color = OBSERVATION_COLORS[observation] ?? "#8d9aaa";
  const Icon = OBSERVATION_ICONS[observation] ?? AlertTriangle;
  const discColor = testDisciplineScore != null ? disciplineColor(testDisciplineScore) : "#8d9aaa";

  return (
    <div className="did-it-work-card" style={{ borderColor: color }}>
      {/* ── Observation header ── */}
      <div className="diw-header" style={{ borderColor: color }}>
        <Icon size={20} color={color} />
        <h3 style={{ color }}>{observation.replace(/_/g, " ").toUpperCase()}</h3>
        <span className="diw-confidence" style={{ background: `${color}18`, color, borderColor: `${color}30` }}>
          {Math.round(confidenceScore * 100)}% confidence
        </span>
      </div>

      <p className="diw-headline">{headline}</p>

      {/* ── Score row ── */}
      <div className="diw-score-row">
        {testDisciplineScore != null && (
          <div className="diw-score-block" style={{ borderColor: discColor }}>
            <span className="diw-score-label">Test Discipline</span>
            <span className="diw-score-value" style={{ color: discColor }}>{testDisciplineScore}/100</span>
          </div>
        )}
        {wholeLapDeltaS != null && (
          <div className="diw-score-block" style={{ borderColor: wholeLapDeltaS < 0 ? "#22c55e" : wholeLapDeltaS > 0 ? "#ef4444" : "#8d9aaa" }}>
            <span className="diw-score-label">Median Whole-Lap Pace</span>
            <span className="diw-score-value" style={{ color: wholeLapDeltaS < 0 ? "#22c55e" : wholeLapDeltaS > 0 ? "#ef4444" : "#8d9aaa" }}>
              {deltaSign(wholeLapDeltaS)}{wholeLapDeltaS.toFixed(3)} s
            </span>
            {paceNoiseBandS != null && <span className="muted">noise ±{paceNoiseBandS.toFixed(3)} s</span>}
            {eligibleLapCounts && <span className="muted">{eligibleLapCounts.baseline} / {eligibleLapCounts.test} eligible laps</span>}
          </div>
        )}
        {/* Delta summary */}
        {(targetZoneDeltaMph != null || splitterDeltaMm != null || scrubDelta != null) && (
          <div className="diw-deltas">
            {targetZoneDeltaMph != null && (
              <span className="diw-delta" style={{ color: targetZoneDeltaMph > 0 ? "#22c55e" : "#ef4444" }}>
                {deltaSign(targetZoneDeltaMph)}{targetZoneDeltaMph.toFixed(2)} mph
              </span>
            )}
            {splitterDeltaMm != null && (
              <span className="diw-delta" style={{ color: splitterDeltaMm > 0 ? "#22c55e" : "#f97316" }}>
                Splitter: {deltaSign(splitterDeltaMm)}{splitterDeltaMm.toFixed(1)} mm
              </span>
            )}
            {scrubDelta != null && (
              <span className="diw-delta" style={{ color: scrubDelta > 0 ? "#ef4444" : "#22c55e" }}>
                Scrub: {deltaSign(scrubDelta)}{scrubDelta.toFixed(3)}
              </span>
            )}
            {platformRiskDelta != null && (
              <span className="diw-delta" style={{ color: platformRiskDelta > 0 ? "#ef4444" : "#22c55e" }}>
                Platform Risk: {deltaSign(platformRiskDelta)}{platformRiskDelta.toFixed(3)}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Context warnings (grouped) ── */}
      {(weatherWarning || (contextWarnings?.length ?? 0) > 0) && (
        <div className="diw-context-warnings">
          <h4 style={{ fontSize: 11, color: "#8d9aaa", textTransform: "uppercase", letterSpacing: "0.04em", margin: "0 0 4px" }}>
            <AlertTriangle size={12} /> Context Warnings
          </h4>          {weatherWarning && <p className="warning-line"><AlertTriangle size={12} /> {weatherWarning}</p>}
          {contextWarnings?.map(cw => (
            <p key={cw.label} className="warning-line"><AlertTriangle size={12} /> {cw.warning}</p>
          ))}
        </div>
      )}

      {/* ── Evidence ── */}
      {evidence.length > 0 && (
        <div className="diw-section">
          <h4>Evidence</h4>
          {evidence.map((e, i) => <p key={i} className="diw-evidence-item">• {e}</p>)}
        </div>
      )}

      {/* ── Setup changes ── */}
      {setupChanges && setupChanges.length > 0 && (
        <div className="diw-section">
          <h4>Setup Changes</h4>
          {setupChanges.slice(0, 8).map((sc, i) => (
            <div key={i} className="diw-change-row">
              <span>{sc.label}</span>
              <span className="muted">{String(sc.baseline_value ?? "—")} → {String(sc.test_value ?? "—")}</span>
            </div>
          ))}
          {setupChanges.length > 8 && <p className="muted">+{setupChanges.length - 8} more changes</p>}
        </div>
      )}

      {/* ── Tire Lifecycle Context ── */}
      {tireContext && (
        <div className="diw-section">
          <h4><Thermometer size={12} /> Tire Lifecycle Context</h4>
          {tireContext.isShortRun && (
            <p className="warning-line"><AlertTriangle size={12} /> Short run — tire falloff conclusions are low confidence.</p>
          )}
          {tireContext.runLengthLaps != null && (
            <div className="diw-change-row">
              <span>Run Length</span>
              <span>{tireContext.runLengthLaps} lap{tireContext.runLengthLaps !== 1 ? "s" : ""}</span>
            </div>
          )}
          {tireContext.pressureGainDelta != null && (
            <div className="diw-change-row">
              <span>Pressure Gain Δ</span>
              <span style={{ color: tireContextColor(tireContext.pressureGainDelta) }}>
                {tireContext.pressureGainDelta > 0 ? "+" : ""}{tireContext.pressureGainDelta.toFixed(1)} psi
              </span>
            </div>
          )}
          {tireContext.tempSpreadDelta != null && (
            <div className="diw-change-row">
              <span>Temp Spread Δ</span>
              <span style={{ color: tireContextColor(tireContext.tempSpreadDelta) }}>
                {tireContext.tempSpreadDelta > 0 ? "+" : ""}{tireContext.tempSpreadDelta.toFixed(1)}°C
              </span>
            </div>
          )}
          {tireContext.camberBiasDelta != null && (
            <div className="diw-change-row">
              <span>Camber Bias Δ</span>
              <span style={{ color: tireContextColor(tireContext.camberBiasDelta) }}>
                {tireContext.camberBiasDelta > 0 ? "+" : ""}{tireContext.camberBiasDelta.toFixed(1)}°C
              </span>
            </div>
          )}
          {tireContext.wearSpreadDelta != null && (
            <div className="diw-change-row">
              <span>Wear Spread Δ</span>
              <span style={{ color: tireContextColor(tireContext.wearSpreadDelta) }}>
                {tireContext.wearSpreadDelta > 0 ? "+" : ""}{tireContext.wearSpreadDelta.toFixed(2)} percentage points
              </span>
            </div>
          )}
          {tireContext.pressureGainDelta == null && tireContext.tempSpreadDelta == null &&
           tireContext.camberBiasDelta == null && tireContext.wearSpreadDelta == null && (
            <p className="muted">Tire lifecycle context unavailable.</p>
          )}
        </div>
      )}

      {/* ── Warnings (grouped) ── */}
      {warnings.length > 0 && (
        <div className="diw-section diw-warnings">
          <h4><AlertTriangle size={12} /> Warnings</h4>
          {warnings.map((w, i) => <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>)}
          {testDisciplineScore != null && testDisciplineScore < 50 && (
            <p style={{ fontSize: 10, marginTop: 8, color: "#f59e0b", fontStyle: "italic" }}>
              ℹ Comparison is useful for review, not setup authority.
            </p>
          )}
        </div>
      )}

      {/* ── Evidence navigation only ── */}
      <div className="diw-actions">
        {onOpenMap && (
          <button className="diw-btn" onClick={onOpenMap} disabled={disabled} aria-disabled={disabled}>
            Map Overlay
          </button>
        )}
        {onOpenEvidence && (
          <button className="diw-btn" onClick={onOpenEvidence} disabled={disabled} aria-disabled={disabled}>
            Open Evidence
          </button>
        )}
      </div>
    </div>
  );
}

