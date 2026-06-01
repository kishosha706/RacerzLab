import { AlertTriangle, ClipboardCheck, Gauge, Lightbulb, MapPin, ShieldAlert, Wrench } from "lucide-react";
import type { RunOverview } from "../types/telemetry";

type CrewChiefPanelProps = {
  overview: RunOverview;
  onOpenMap?: () => void;
  onOpenPlatform?: () => void;
  onOpenSetup?: () => void;
  onOpenNotebook?: () => void;
  isLearning?: boolean;
};

function warnColor(text: string): string {
  const t = text.toLowerCase();
  if (/invalid|worsen/.test(t)) return "#f59e0b";
  if (/risk|critical|danger/.test(t)) return "#ef4444";
  return "#38bdf8";
}

export function CrewChiefPanel({ overview, onOpenMap, onOpenPlatform, onOpenSetup, onOpenNotebook, isLearning }: CrewChiefPanelProps) {
  const recommendation = overview.recommendations?.[0];

  return (
    <aside className="crew-panel">
      <header>
        <ClipboardCheck size={18} />
        <h2>Crew Chief</h2>
      </header>
      <p className="crew-summary">
        {isLearning ? overview.crew_chief_summary : ((overview.crew_chief_summary?.split(". ").slice(0, 2).join(". ") ?? "") + ".") || ""}
      </p>
      {recommendation ? (
        <section className="crew-block">
          <span className="eyebrow">Next test</span>
          <p>{recommendation.recommendation_text}</p>
          <strong>{recommendation.success_metric}</strong>
        </section>
      ) : (
        <section className="crew-block">
          <span className="eyebrow">No call</span>
          <p>No recommendation is shown without supporting evidence.</p>
        </section>
      )}

      {/* ── Action buttons ── */}
      <section className="crew-block">
        <span className="eyebrow">Actions</span>
        <div className="crew-actions">
          {onOpenPlatform && (
            <button className="crew-action-btn" onClick={onOpenPlatform}>
              <Gauge size={12} /> Open Platform
            </button>
          )}
          {onOpenMap && (
            <button className="crew-action-btn" onClick={onOpenMap}>
              <MapPin size={12} /> Open Map
            </button>
          )}
          {onOpenSetup && (
            <button className="crew-action-btn" onClick={onOpenSetup}>
              <Wrench size={12} /> Open Setup
            </button>
          )}
          {onOpenNotebook && (
            <button className="crew-action-btn" onClick={onOpenNotebook}>
              <Lightbulb size={12} /> Test Note
            </button>
          )}
        </div>
      </section>

      {/* ── Warnings with severity colors ── */}
      {overview.warnings.length > 0 && (
        <section className="crew-block crew-warnings">
          <span><ShieldAlert size={16} /> Warnings</span>
          {overview.warnings.map((warning) => {
            const color = warnColor(warning);
            return (
              <p key={warning} className="crew-warning-line" style={{ borderLeftColor: color }}>
                <AlertTriangle size={12} color={color} /> {warning}
              </p>
            );
          })}
        </section>
      )}
    </aside>
  );
}

