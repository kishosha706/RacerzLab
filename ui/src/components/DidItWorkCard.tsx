import { AlertTriangle, Bookmark, CheckCircle, RotateCcw, Thermometer, XCircle } from "lucide-react";
import { VERDICT_COLORS } from "../constants/verdict";
import type { VerdictKind } from "../types/compare";

export interface TireContextProps {
  pressureGainDelta?: number | null;
  tempSpreadDelta?: number | null;
  camberBiasDelta?: number | null;
  wearSpreadDelta?: number | null;
  runLengthLaps?: number | null;
  isShortRun?: boolean;
}

export interface DidItWorkCardProps {
  verdict: VerdictKind;
  headline: string;
  confidenceScore: number;           // 0-1
  testDisciplineScore?: number;      // 0-100
  targetZoneDeltaMph?: number | null;
  splitterDeltaMm?: number | null;
  platformRiskDelta?: number | null;
  scrubDelta?: number | null;
  evidence: string[];
  warnings: string[];
  nextStep?: string | null;
  successMetric?: string | null;
  causeBucket?: string | null;
  requiredNextData?: string[];
  doNotChangeWarnings?: string[];
  setupChanges?: Array<{ label: string; baseline_value: unknown; test_value: unknown }>;
  contextWarnings?: Array<{ label: string; warning: string }>;
  draftWarning?: string | null;
  weatherWarning?: string | null;
  tireContext?: TireContextProps | null;
  /** Callbacks */
  onSaveFinding?: () => void;
  onCreateTestPlan?: () => void;
  onStageNextTest?: () => void;
  onOpenSetup?: () => void;
  onOpenEvidence?: () => void;
  onOpenMap?: () => void;
  saving?: boolean;
  saveStatus?: string | null;
  disabled?: boolean;
}

const VERDICT_ICONS: Record<VerdictKind, typeof CheckCircle> = {
  keep_direction: CheckCircle,
  undo_partially: RotateCcw,
  undo: XCircle,
  retest: RotateCcw,
  inconclusive: AlertTriangle,
  reference_mode: AlertTriangle,
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
  verdict, headline, confidenceScore, testDisciplineScore,
  targetZoneDeltaMph, splitterDeltaMm, platformRiskDelta, scrubDelta,
  evidence, warnings, nextStep, successMetric,
  causeBucket, requiredNextData, doNotChangeWarnings,
  setupChanges, contextWarnings, draftWarning, weatherWarning,
  tireContext,
  onSaveFinding, onCreateTestPlan, onStageNextTest, onOpenSetup, onOpenEvidence, onOpenMap,
  saving, saveStatus, disabled,
}: DidItWorkCardProps) {
  const color = VERDICT_COLORS[verdict] ?? "#8d9aaa";
  const Icon = VERDICT_ICONS[verdict] ?? AlertTriangle;
  const discColor = testDisciplineScore != null ? disciplineColor(testDisciplineScore) : "#8d9aaa";

  return (
    <div className="did-it-work-card" style={{ borderColor: color }}>
      {/* ── Verdict header ── */}
      <div className="diw-header" style={{ borderColor: color }}>
        <Icon size={20} color={color} />
        <h3 style={{ color }}>{verdict.replace(/_/g, " ").toUpperCase()}</h3>
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
      {(draftWarning || weatherWarning || (contextWarnings?.length ?? 0) > 0) && (
        <div className="diw-context-warnings">
          <h4 style={{ fontSize: 11, color: "#8d9aaa", textTransform: "uppercase", letterSpacing: "0.04em", margin: "0 0 4px" }}>
            <AlertTriangle size={12} /> Context Warnings
          </h4>
          {draftWarning && <p className="warning-line"><AlertTriangle size={12} /> {draftWarning}</p>}
          {weatherWarning && <p className="warning-line"><AlertTriangle size={12} /> {weatherWarning}</p>}
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
                {tireContext.wearSpreadDelta > 0 ? "+" : ""}{tireContext.wearSpreadDelta.toFixed(2)} mm
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
              ℹ Comparison is useful for review, not setup verdict.
            </p>
          )}
        </div>
      )}

      {/* ── Next step / Success metric ── */}
      {nextStep && (
        <div className="diw-section">
          <h4>Next Step</h4>
          <p className="diw-next-step">{nextStep}</p>
        </div>
      )}
      {successMetric && (
        <div className="diw-section">
          <h4>Success Metric</h4>
          <p className="diw-success-metric">{successMetric}</p>
        </div>
      )}

      {/* ── Cause bucket ── */}
      {causeBucket && (
        <div className="diw-section">
          <h4>Cause</h4>
          <p className="diw-evidence-item">{causeBucket}</p>
        </div>
      )}

      {/* ── Required next data ── */}
      {requiredNextData && requiredNextData.length > 0 && (
        <div className="diw-section">
          <h4>Required Next Data</h4>
          {requiredNextData.map((d, i) => <p key={i} className="diw-evidence-item">• {d}</p>)}
        </div>
      )}

      {/* ── Do Not Change Yet ── */}
      {doNotChangeWarnings && doNotChangeWarnings.length > 0 && (
        <div className="diw-section diw-warnings">
          <h4><AlertTriangle size={12} /> Do Not Change Yet</h4>
          {doNotChangeWarnings.map((w, i) => <p key={i} className="warning-line"><AlertTriangle size={12} /> {w}</p>)}
        </div>
      )}

      {/* ── Action buttons ── */}
      <div className="diw-actions">
        {onSaveFinding && (
          <button className="diw-btn diw-btn-primary" onClick={onSaveFinding} disabled={saving || disabled}
            style={{ fontWeight: 600, fontSize: 13 }}>
            <Bookmark size={14} /> {saving ? "Saving…" : "Save Finding"}
          </button>
        )}
        {onStageNextTest && (
          <button className="diw-btn diw-btn-primary" onClick={onStageNextTest} disabled={disabled}
            style={{ fontWeight: 600, fontSize: 13 }}>
            Stage Next Test
          </button>
        )}
        {onCreateTestPlan && (
          <button className="diw-btn" onClick={onCreateTestPlan} disabled={disabled}>
            Create Next Test
          </button>
        )}
        {onOpenSetup && (
          <button className="diw-btn" onClick={onOpenSetup} disabled={disabled}>
            Open Setup
          </button>
        )}
        {onOpenMap && (
          <button className="diw-btn" onClick={onOpenMap} disabled={disabled}>
            Open Map
          </button>
        )}
        {onOpenEvidence && (
          <button className="diw-btn" onClick={onOpenEvidence} disabled={disabled}>
            Open Evidence
          </button>
        )}
      </div>
      {saveStatus && <p className="diw-save-status">{saveStatus}</p>}
    </div>
  );
}
