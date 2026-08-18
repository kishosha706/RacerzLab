import { Activity, AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchDamperResponse } from "../api/client";
import type { DamperResponseReport } from "../types/damperResponse";
import { evidenceStrengthOutOf100 } from "../utils/evidenceScore";

type Props = {
  runId: string;
  lap: number | null;
};

function percent(value: number): string {
  return Number.isFinite(value) ? `${value.toFixed(1)}%` : "Unavailable";
}

export function DamperSpectrumSummary({ runId, lap }: Props) {
  const [report, setReport] = useState<DamperResponseReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setReport(null);
    setError(null);
    if (lap == null) return () => { live = false; };
    void fetchDamperResponse(runId, lap)
      .then((payload) => {
        if (!live) return;
        if (payload.run_id !== runId || payload.selected_lap !== lap) {
          setError("Damper spectrum response did not match the selected run and lap.");
          return;
        }
        setReport(payload);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : "Damper spectrum unavailable");
      });
    return () => { live = false; };
  }, [lap, runId]);

  if (lap == null) {
    return <p className="section-note">Select an eligible lap to qualify suspension spectrum evidence.</p>;
  }
  if (error) {
    return <p className="section-note analysis-warning"><AlertTriangle size={13} /> {error}</p>;
  }
  if (!report) {
    return <p className="section-note" role="status">Checking continuous suspension windows and repeatability...</p>;
  }
  if (!report.gate.eligible) {
    return (
      <div className="shock-workstation-warning" role="status">
        <AlertTriangle size={14} />
        <span>Damper spectrum blocked: {report.gate.blocker_reasons.join(" ") || "required evidence is unavailable."}</span>
      </div>
    );
  }

  return (
    <section aria-label="Server-qualified damper spectrum" data-analysis-surface="damper_psd" style={{ marginTop: 12 }}>
      <div className="section-header-row">
        <div>
          <h4><Activity size={14} /> Repeated suspension spectrum</h4>
          <p className="section-note">
            Server-derived from continuous shaft-velocity windows. Gaps, clock jitter, clipping, short windows, and non-repeated peaks are withheld.
          </p>
        </div>
        <span className={`confidence-badge ${report.gate.confidence_cap >= 0.75 ? "high" : "medium"}`}>
          evidence cap {evidenceStrengthOutOf100(report.gate.confidence_cap)}
        </span>
      </div>
      <div className="metric-grid">
        {report.corners.map((corner) => {
          const conclusion = report.conclusions.find((item) => item.key.startsWith(corner.corner.toLowerCase()));
          return (
            <div className="metric-card" key={corner.corner} title={conclusion?.source_channels.join(", ")}>
              <span>{corner.corner} shaft velocity</span>
              <strong>{corner.dominant_frequency_hz == null ? "PSD withheld" : `${corner.dominant_frequency_hz.toFixed(2)} Hz repeated`}</strong>
              <small className="muted">
                {percent(corner.low_speed_regime_pct)} low-speed / {percent(corner.high_speed_regime_pct)} high-speed - {corner.sample_count} samples
              </small>
              <small className="muted">
                {corner.dominant_frequency_hz == null
                  ? `No trustworthy repeated peak. ${corner.spectral_evidence?.rejection_reasons[0] ?? "Qualification evidence unavailable."}`
                  : `Lap ${corner.spectral_evidence?.source_lap_ids.join(", ") || "Unavailable"}; ${corner.spectral_evidence?.agreeing_peak_count ?? 0} agreeing half-windows; tolerance ${corner.spectral_evidence?.agreement_tolerance_hz?.toFixed(2) ?? "Unavailable"} Hz. Not measured damper force.`}
              </small>
            </div>
          );
        })}
      </div>
    </section>
  );
}
