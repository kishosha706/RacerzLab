import { AlertTriangle, ChevronDown, ChevronRight, Crosshair, Gauge, Layers, MapPin, Sliders, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchSetup } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket } from "../store/CompareBasketContext";
import type { RunOverview, SetupSnapshot } from "../types/telemetry";

type SetupTabProps = { overview: RunOverview };

// ── Imperial display conversions ─────────────────────────────────
// iRacing CornerWeight raw values are Newtons, stored under corner_weight_kg
// key for legacy reasons; convert with N→lb.
const MM_IN   = 1 / 25.4;
const KPA_PSI = 0.1450377;
const NMM_LB  = 5.710147;
const N_LB    = 0.224808943;
const NM_FTLB = 0.737562;

function imp(v: number | null, c: number, d: number): number | null {
  return v != null ? +(v * c).toFixed(d) : null;
}

// ── Steering pinion → ratio lookup ───────────────────────────────
// Steering pinion constants (mm/rev)
const PINION_TO_RATIO: Record<number, string> = {
  40: "31:1", 46.5: "27.5:1", 53: "24:1", 60: "20.5:1",
  67: "18.5:1", 73: "17:1", 80: "15.5:1",
};

function deriveSteeringRatio(pinionMm: number | null): string | null {
  if (pinionMm == null) return null;
  // Closest match: find nearest key
  const keys = Object.keys(PINION_TO_RATIO).map(Number);
  let bestKey = keys[0];
  let bestDelta = Math.abs(pinionMm - bestKey);
  for (const k of keys) {
    const delta = Math.abs(pinionMm - k);
    if (delta < bestDelta) { bestDelta = delta; bestKey = k; }
  }
  return bestDelta <= 2 ? PINION_TO_RATIO[bestKey] : null;
}

// ── Data helpers ─────────────────────────────────────────────────
function evNum(s: SetupSnapshot, k: string): number | null {
  const v = s.extracted_values?.[k];
  return (typeof v === "number" && Number.isFinite(v)) ? v : null;
}
function evCorner(s: SetupSnapshot, c: string, k: string): number | null {
  const o = s.extracted_values?.[c];
  if (typeof o === "object" && o !== null) {
    const v = (o as Record<string, unknown>)[k];
    return (typeof v === "number" && Number.isFinite(v)) ? v : null;
  }
  return null;
}

type SetupDiffValue = string | number | null;

type SetupDiffField = {
  key: string;
  group: string;
  label: string;
  unit?: string;
  decimals?: number;
  value: (setup: SetupSnapshot) => SetupDiffValue;
};

const SETUP_DIFF_FIELDS: SetupDiffField[] = [
  { key: "lf_ride_height_mm", group: "Front platform", label: "LF Ride Height", unit: "in", decimals: 3, value: (s) => imp(s.lf_ride_height_mm ?? null, MM_IN, 3) },
  { key: "rf_ride_height_mm", group: "Front platform", label: "RF Ride Height", unit: "in", decimals: 3, value: (s) => imp(s.rf_ride_height_mm ?? null, MM_IN, 3) },
  { key: "lr_ride_height_mm", group: "Rear platform", label: "LR Ride Height", unit: "in", decimals: 3, value: (s) => imp(s.lr_ride_height_mm ?? null, MM_IN, 3) },
  { key: "rr_ride_height_mm", group: "Rear platform", label: "RR Ride Height", unit: "in", decimals: 3, value: (s) => imp(s.rr_ride_height_mm ?? null, MM_IN, 3) },
  { key: "lf_front_spring_n_per_mm", group: "Springs", label: "LF Spring", unit: "lb/in", decimals: 0, value: (s) => imp(s.lf_front_spring_n_per_mm ?? null, NMM_LB, 0) },
  { key: "rf_front_spring_n_per_mm", group: "Springs", label: "RF Spring", unit: "lb/in", decimals: 0, value: (s) => imp(s.rf_front_spring_n_per_mm ?? null, NMM_LB, 0) },
  { key: "lr_rear_spring_n_per_mm", group: "Springs", label: "LR Spring", unit: "lb/in", decimals: 0, value: (s) => imp(s.lr_rear_spring_n_per_mm ?? null, NMM_LB, 0) },
  { key: "rr_rear_spring_n_per_mm", group: "Springs", label: "RR Spring", unit: "lb/in", decimals: 0, value: (s) => imp(s.rr_rear_spring_n_per_mm ?? null, NMM_LB, 0) },
  { key: "nose_weight_percent", group: "Weight", label: "Nose Weight", unit: "%", decimals: 1, value: (s) => s.nose_weight_percent ?? null },
  { key: "cross_weight_percent", group: "Weight", label: "Cross Weight", unit: "%", decimals: 1, value: (s) => s.cross_weight_percent ?? null },
  { key: "tape_percent", group: "Aero/cooling", label: "Tape", unit: "%", decimals: 0, value: (s) => s.tape_percent ?? null },
  { key: "rear_end_ratio", group: "Gearing", label: "Rear Gear", unit: ":1", decimals: 3, value: (s) => s.rear_end_ratio ?? null },
  { key: "front_brake_bias_percent", group: "Controls", label: "Brake Bias", unit: "%", decimals: 1, value: (s) => s.front_brake_bias_percent ?? null },
  { key: "steering_ratio", group: "Controls", label: "Steering Ratio", value: (s) => s.steering_ratio ?? deriveSteeringRatio(evNum(s, "steering_pinion_mm")) },
  { key: "steering_offset_deg", group: "Controls", label: "Steering Offset", unit: "deg", decimals: 2, value: (s) => s.steering_offset_deg ?? null },
];

function sameDiffValue(left: SetupDiffValue, right: SetupDiffValue): boolean {
  if (left == null && right == null) return true;
  if (left == null || right == null) return false;
  if (typeof left === "number" && typeof right === "number") {
    return Math.abs(left - right) < 1e-9;
  }
  return String(left) === String(right);
}

function formatDiffValue(value: SetupDiffValue, unit?: string): string {
  if (value == null || (typeof value === "number" && !Number.isFinite(value))) return "Unavailable";
  return `${value}${unit ? ` ${unit}` : ""}`;
}

function formatDelta(baseline: SetupDiffValue, current: SetupDiffValue, decimals = 3): string {
  if (typeof baseline !== "number" || typeof current !== "number") return "changed";
  const delta = current - baseline;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(decimals)}`;
}

// ── Field Row ────────────────────────────────────────────────────
function Field({ l, v, u, imp: isImp }: {
  l: string; v: string | number | null | undefined;
  u?: string; imp?: boolean;
}) {
  const missing = v == null || (typeof v === "number" && !Number.isFinite(v)) || (typeof v === "object");
  const display = missing ? "Unavailable" : `${v}${u ? ` ${u}` : ""}`;
  const cls = ["gr-row"];
  if (missing) cls.push("missing");
  else if (isImp) cls.push("important");
  return (
    <div className={cls.join(" ")} role="row">
      <span className="gr-label" role="rowheader">{l}</span>
      <span className="gr-value" role="cell">{display}</span>
    </div>
  );
}

// ── Corner Panel ─────────────────────────────────────────────────
function CornerPanel({ label, corner, setup, glow }: {
  label: string; corner: string; setup: SetupSnapshot; glow?: boolean;
}) {
  const wt     = imp(evCorner(setup, corner, "corner_weight_kg"), N_LB, 0);
  const rh     = imp(evCorner(setup, corner, "ride_height_mm"), MM_IN, 3);
  const collar = imp(evCorner(setup, corner, "shock_collar_offset_mm"), MM_IN, 3);
  const spring = imp(evCorner(setup, corner, "spring_rate_n_per_mm"), NMM_LB, 0);
  const psi    = imp(evCorner(setup, corner, "cold_pressure_kpa"), KPA_PSI, 1);
  const lsC    = evCorner(setup, corner, "ls_compression");
  const hsC    = evCorner(setup, corner, "hs_compression");
  const hsCS   = evCorner(setup, corner, "hs_comp_slope");
  const lsR    = evCorner(setup, corner, "ls_rebound");
  const hsR    = evCorner(setup, corner, "hs_rebound");
  const hsRS   = evCorner(setup, corner, "hs_reb_slope");
  const camber = evCorner(setup, corner, "camber_deg");
  const caster = evCorner(setup, corner, "caster_deg");
  const toe    = imp(evCorner(setup, corner, "toe_in_mm"), MM_IN, 4);

  return (
    <div className={`gr-corner${glow ? " glow" : ""}`} role="region" aria-label={label}>
      <div className="gr-corner-head">{label}</div>
      <div className="gr-corner-body">
        <Field l="Tire PSI" v={psi} u="psi" imp />
        <Field l="Ride Height" v={rh} u="in" imp />
        <Field l="Spring Rate" v={spring} u="lb/in" imp />
        <Field l="Corner Weight" v={wt} u="lb" imp />
        <Field l="Shock Collar" v={collar} u="in" />
        <div className="gr-group-head">Dampers</div>
        <Field l="LS Compression" v={lsC} u="clk" />
        <Field l="HS Compression" v={hsC} u="clk" />
        <Field l="HS Comp Slope" v={hsCS} />
        <Field l="LS Rebound" v={lsR} u="clk" />
        <Field l="HS Rebound" v={hsR} u="clk" />
        <Field l="HS Reb Slope" v={hsRS} />
        <div className="gr-group-head">Alignment</div>
        <Field l="Camber" v={camber} u="deg" />
        <Field l="Caster" v={caster} u="deg" />
        <Field l="Toe-In" v={toe} u="in" />
      </div>
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────
export function SetupTab({ overview }: SetupTabProps) {
  const setup = overview.setup_snapshot;
  const { selection, setWorkspace } = useTelemetrySelection();
  const { basket } = useCompareBasket();
  const [diffMode, setDiffMode] = useState<"current" | "diff">("current");
  const [arbOpen, setArbOpen] = useState(false);
  const [baselineSetup, setBaselineSetup] = useState<SetupSnapshot | null>(null);
  const [baselineSetupLoading, setBaselineSetupLoading] = useState(false);
  const [baselineSetupError, setBaselineSetupError] = useState<string | null>(null);

  const selectedEvent = useMemo(() => {
    if (!selection.selectedEventId) return null;
    return overview.events.find(e => e.event_id === selection.selectedEventId) ?? null;
  }, [selection.selectedEventId, overview.events]);

  const isInferred = selectedEvent ? (selectedEvent.related_setup_keys?.length ?? 0) === 0 : false;
  const evtName = selectedEvent
    ? (selectedEvent.event_subtype ?? selectedEvent.event_type.replace(/_/g, " "))
    : null;

  const focusZone = useMemo(() => {
    if (!selectedEvent) return "none";
    const et = selectedEvent.event_type;
    if (/REAR/.test(et)) return "rear";
    if (/SPLITTER|PLATFORM/.test(et) && !/REAR/.test(et)) return "front";
    if (/BOTTOMING|COMPRESSION|RAKE/.test(et)) return "all";
    if (/STEER|SCRUB|ACKERMANN/.test(et)) return "steering";
    if (/TIRE|PRESSURE|CAMBER|TEMP/.test(et)) return "tires";
    if (/SHOCK|DAMPER/.test(et)) return "dampers";
    return "all";
  }, [selectedEvent]);

  const showDiffUnavailable = diffMode === "diff" && (!basket.baseline || !basket.baseline.has_setup_snapshot);
  const setupDiffRows = useMemo(() => {
    if (!setup || !baselineSetup) return [];
    return SETUP_DIFF_FIELDS
      .map((field) => {
        const baseline = field.value(baselineSetup);
        const current = field.value(setup);
        return {
          ...field,
          baseline,
          current,
          changed: !sameDiffValue(baseline, current),
          delta: formatDelta(baseline, current, field.decimals),
        };
      })
      .filter((row) => row.changed);
  }, [baselineSetup, setup]);

  useEffect(() => {
    const baselineRunId = basket.baseline?.run_id ?? null;
    const canLoadBaseline = diffMode === "diff" && baselineRunId && basket.baseline?.has_setup_snapshot;
    if (!canLoadBaseline) {
      setBaselineSetup(null);
      setBaselineSetupLoading(false);
      setBaselineSetupError(null);
      return;
    }
    if (baselineRunId === overview.run_id) {
      setBaselineSetup(overview.setup_snapshot ?? null);
      setBaselineSetupLoading(false);
      setBaselineSetupError(null);
      return;
    }

    let cancelled = false;
    setBaselineSetupLoading(true);
    setBaselineSetupError(null);
    fetchSetup(baselineRunId)
      .then((nextSetup) => {
        if (cancelled) return;
        setBaselineSetup(nextSetup);
      })
      .catch((caught) => {
        if (cancelled) return;
        setBaselineSetup(null);
        setBaselineSetupError(caught instanceof Error ? caught.message : "Baseline setup could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setBaselineSetupLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [basket.baseline, diffMode, overview.run_id, overview.setup_snapshot]);

  const handlePlatform = useCallback(() => setWorkspace("platform_trace", "setup_table"), [setWorkspace]);
  const handleMap = useCallback(() => setWorkspace("map", "setup_table"), [setWorkspace]);
  const handleDialIn = useCallback(() => setWorkspace("dial_in", "setup_table"), [setWorkspace]);

  if (!setup) {
    return (
      <section className="garage-board">
        <div className="setup-dialin-callout">
          <div>
            <strong>Need help dialing the car?</strong>
            <span>Open Dial-In for source-backed setup swings to test one at a time.</span>
          </div>
          <button className="secondary-button" type="button" onClick={handleDialIn}>
            <Crosshair size={14} /> Open Dial-In
          </button>
        </div>
        <section className="workspace-section">
          <h2>Setup Board</h2>
          <div className="gr-empty">
            <Sliders size={40} style={{ opacity: 0.2 }} />
            <p style={{ fontSize: 13, color: "#8d9aaa", marginTop: 8 }}>Setup snapshot unavailable.</p>
            <p className="section-note">Garage-specific recommendations are limited until a setup snapshot is available.</p>
            <p className="section-note">Import a telemetry file with setup data or attach a setup snapshot if supported.</p>
          </div>
        </section>
      </section>
    );
  }

  const car = overview.session.car_name ?? "Unknown Car";
  const track = overview.session.track_display_name ?? overview.session.track_name ?? "";

  // Steering: true ratio wins; fallback to pinion-derived ratio.
  const rawRatio = setup.steering_ratio;
  const pinion  = evNum(setup, "steering_pinion_mm");
  const derivedRatio = (!rawRatio || rawRatio === "") ? deriveSteeringRatio(pinion) : null;
  const displayRatio = rawRatio || derivedRatio;
  // Master cylinders → imperial
  const frontMc = imp(evNum(setup, "front_mc_mm"), MM_IN, 3);
  const rearMc  = imp(evNum(setup, "rear_mc_mm"), MM_IN, 3);

  return (
    <section className="garage-board">
      {/* 1) Setup Context / Evidence Focus strip */}
      <div className="gr-topbar">
        <div className="gr-topbar-left">
          <Sliders size={16} />
          <div>
            <span className="gr-topbar-name">{setup.setup_name ?? "Unnamed Setup"}</span>
            <span className="gr-topbar-meta">{car}{track ? ` \u00b7 ${track}` : ""}</span>
          </div>
          <span className="gr-tag source">.ibt CarSetup</span>
        </div>
        <div className="gr-topbar-right">
          {selectedEvent && (
            <div className={`gr-evidence ${focusZone}`}>
              <Crosshair size={11} />
              <span className="gr-ev-name">{evtName}</span>
              {selection.selectedLap != null && <span className="gr-ev-lap">L{selection.selectedLap}</span>}
              {selection.selectedLapPct != null && (
                <span className="gr-ev-pct">{selection.selectedLapPct.toFixed(1)}%</span>
              )}
              {selection.selectedZoneLabel && (
                <span className="gr-ev-zone">{selection.selectedZoneLabel}</span>
              )}
              <span className={`gr-ev-tag ${isInferred ? "inferred" : "explicit"}`}>
                {isInferred ? "Inferred" : "Explicit"}
              </span>
              {focusZone !== "none" && <span className="gr-ev-tag explicit">{focusZone === "all" ? "Front/Rear" : focusZone.charAt(0).toUpperCase() + focusZone.slice(1)}</span>}
            </div>
          )}
        </div>
      </div>

      <div className="setup-dialin-callout">
        <div>
          <strong>Need help dialing the car?</strong>
          <span>Open Dial-In for source-backed setup swings to test one at a time.</span>
        </div>
        <button className="secondary-button" type="button" onClick={handleDialIn}>
          <Crosshair size={14} /> Open Dial-In
        </button>
      </div>

      {/* 2) 2x2 Corner Board */}
      <div className="gr-corners">
        <CornerPanel label="LEFT FRONT" corner="lf" setup={setup} glow={focusZone === "front" || focusZone === "all" || focusZone === "steering"} />
        <CornerPanel label="RIGHT FRONT" corner="rf" setup={setup} glow={focusZone === "front" || focusZone === "all" || focusZone === "steering"} />
        <CornerPanel label="LEFT REAR" corner="lr" setup={setup} glow={focusZone === "rear" || focusZone === "all"} />
        <CornerPanel label="RIGHT REAR" corner="rr" setup={setup} glow={focusZone === "rear" || focusZone === "all"} />
      </div>

      {/* 3) Top Controls / Balance / ARB-Diff row */}
      <div className="gr-toprow">
        <div className="gr-card">
          <div className="gr-card-head"><Gauge size={12} /> Steering / Controls</div>
          <div className="gr-card-body">
            <Field l="Steering Ratio" v={displayRatio ?? null} />
            {derivedRatio && pinion != null && (
              <Field l="Steering Pinion" v={pinion} u="mm/rev" />
            )}
            <Field l="Steering Offset" v={setup.steering_offset_deg ?? null} u="deg" />
            <Field l="Brake Bias" v={setup.front_brake_bias_percent ?? null} u="%" />
            <Field l="Front Master Cyl" v={frontMc} u="in" />
            <Field l="Rear Master Cyl" v={rearMc} u="in" />
            <Field l="Tape" v={setup.tape_percent ?? null} u="%" />
          </div>
        </div>

        {/* Balance */}
        <div className="gr-card">
          <div className="gr-card-head"><Crosshair size={12} /> Balance</div>
          <div className="gr-card-body">
            <Field l="Nose Weight" v={setup.nose_weight_percent ?? null} u="%" />
            <Field l="Cross Weight" v={setup.cross_weight_percent ?? null} u="%" />
            <Field l="Left Weight" v={
              (() => {
                const lf = evCorner(setup, "lf", "corner_weight_kg");
                const lr = evCorner(setup, "lr", "corner_weight_kg");
                const rf = evCorner(setup, "rf", "corner_weight_kg");
                const rr = evCorner(setup, "rr", "corner_weight_kg");
                if (lf != null && lr != null && rf != null && rr != null) {
                  const t = lf + rf + lr + rr;
                  return t > 0 ? +((lf + lr) / t * 100).toFixed(1) : null;
                }
                return null;
              })()
            } u="%" />
            <Field l="Rear End Ratio" v={evNum(setup, "final_drive_ratio")} u=":1" />
          </div>
        </div>

        {/* ARB / Diff */}
        <div className="gr-card">
          <button
            className="gr-card-head gr-card-head-btn"
            onClick={() => setArbOpen(!arbOpen)}
            aria-expanded={arbOpen}
            aria-controls="arb-diff-body"
          >
            <Wrench size={12} /> ARB / Diff
            <span className="gr-card-chev">{arbOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span>
          </button>
          {arbOpen && (
            <div className="gr-card-body" id="arb-diff-body">
              <div className="gr-subhead">Front ARB</div>
              <Field l="Diameter" v={imp(evNum(setup, "front_arb_diameter_mm"), MM_IN, 3)} u="in" />
              <Field l="Arm Length" v={imp(evNum(setup, "front_arb_arm_mm"), MM_IN, 3)} u="in" />
              <Field l="Preload" v={imp(evNum(setup, "front_arb_preload_nm"), NM_FTLB, 1)} u="ft-lb" />
              <div className="gr-subhead">Rear ARB</div>
              <Field l="Diameter" v={imp(evNum(setup, "rear_arb_diameter_mm"), MM_IN, 3)} u="in" />
              <Field l="Arm Length" v={imp(evNum(setup, "rear_arb_arm_mm"), MM_IN, 3)} u="in" />
              <Field l="Preload" v={imp(evNum(setup, "rear_arb_preload_nm"), NM_FTLB, 1)} u="ft-lb" />
              <div className="gr-subhead">Differential</div>
              <Field l="Preload" v={imp(evNum(setup, "diff_preload_nm"), NM_FTLB, 1)} u="ft-lb" />
            </div>
          )}
        </div>
      </div>

      {/* 4) Diff Mode / Baseline Warning */}
      <div className="gr-diff-tabs" role="tablist" aria-label="Setup view mode" style={{ marginBottom: 10 }}>
        <button
          className={`gr-diff-tab ${diffMode === "current" ? "active" : ""}`}
          onClick={() => setDiffMode("current")}
          role="tab"
          aria-selected={diffMode === "current"}
          aria-pressed={diffMode === "current"}
        >
          Current
        </button>
        <button
          className={`gr-diff-tab ${diffMode === "diff" ? "active" : ""}`}
          onClick={() => setDiffMode("diff")}
          role="tab"
          aria-selected={diffMode === "diff"}
          aria-pressed={diffMode === "diff"}
        >
          Diff
        </button>
      </div>
      {showDiffUnavailable && (
        <div className="map-warning-banner" role="alert" style={{ marginBottom: 10 }}>
          <AlertTriangle size={14} />
          <span>Diff unavailable - no real baseline snapshot selected. Current setup values are shown.</span>
        </div>
      )}
      {diffMode === "diff" && basket.baseline?.has_setup_snapshot && (
        <div className="setup-diff-list" aria-live="polite">
          {baselineSetupLoading && (
            <p className="setup-diff-empty">Loading baseline setup...</p>
          )}
          {baselineSetupError && (
            <div className="map-warning-banner" role="alert">
              <AlertTriangle size={14} />
              <span>{baselineSetupError}</span>
            </div>
          )}
          {!baselineSetupLoading && !baselineSetupError && baselineSetup && setupDiffRows.length === 0 && (
            <p className="setup-diff-empty">No setup changes detected against {basket.baseline.label}.</p>
          )}
          {!baselineSetupLoading && !baselineSetupError && setupDiffRows.length > 0 && (
            <>
              <div className="setup-diff-group-label">Baseline: {basket.baseline.label}</div>
              {setupDiffRows.map((row) => (
                <div key={row.key} className="setup-diff-row changed">
                  <span>{row.group} / {row.label}</span>
                  <span className="setup-diff-values">
                    <span className="setup-diff-baseline">{formatDiffValue(row.baseline, row.unit)}</span>
                    <span className="setup-diff-arrow">to</span>
                    <span className="setup-diff-test">{formatDiffValue(row.current, row.unit)}</span>
                    <span className="setup-diff-test">({row.delta})</span>
                  </span>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* 5) Related Evidence Links */}
      <div className="toolbar-actions">
        <button className="secondary-button" onClick={handlePlatform}>
          <Layers size={14} /> Open Platform
        </button>
        <button className="secondary-button" onClick={handleMap}>
          <MapPin size={14} /> Open Map
        </button>
      </div>
    </section>
  );
}
