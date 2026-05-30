import { ChevronDown, ChevronRight, Crosshair, Gauge, Layers, MapPin, Sliders, Wrench } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket } from "../store/CompareBasketContext";
import type { RunOverview, SetupSnapshot } from "../types/telemetry";

type SetupTabProps = { overview: RunOverview };

// ── Imperial display conversions ─────────────────────────────────
const MM_IN   = 1 / 25.4;        // mm → in
const KPA_PSI = 0.1450377;      // kPa → psi
const NMM_LB  = 5.710147;       // N/mm → lb/in
const N_LB    = 0.224808943;    // N → lb (iRacing CornerWeight raw)
const NM_FTLB = 0.737562;       // Nm → ft-lb

function imp(v: number | null, c: number, d: number): number | null {
  return v != null ? +(v * c).toFixed(d) : null;
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

// ── Field Row ────────────────────────────────────────────────────
function Field({ l, v, u, d }: { l: string; v: string | number | null; u?: string; d?: boolean }) {
  const m = v == null;
  return (
    <div className={`gr-row${d ? " dim" : ""}${m ? " missing" : ""}`}>
      <span className="gr-label">{l}</span>
      <span className="gr-value">{m ? "\u2014" : `${v}${u ? ` ${u}` : ""}`}</span>
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
    <div className={`gr-corner${glow ? " glow" : ""}`}>
      <div className="gr-corner-head">{label}</div>
      <div className="gr-corner-body">
        <Field l="Corner Weight" v={wt} u="lb" />
        <Field l="Ride Height" v={rh} u="in" />
        <Field l="Shock Collar" v={collar} u="in" d />
        <Field l="Spring Rate" v={spring} u="lb/in" />
        <div className="gr-sep" />
        <Field l="Tire PSI" v={psi} u="psi" />
        <div className="gr-sep" />
        <Field l="LS Compression" v={lsC} u="clk" d />
        <Field l="HS Compression" v={hsC} u="clk" d />
        <Field l="HS Comp Slope" v={hsCS} d />
        <Field l="LS Rebound" v={lsR} u="clk" d />
        <Field l="HS Rebound" v={hsR} u="clk" d />
        <Field l="HS Reb Slope" v={hsRS} d />
        <div className="gr-sep" />
        <Field l="Camber" v={camber} u="deg" />
        <Field l="Caster" v={caster} u="deg" d={corner === "lr" || corner === "rr"} />
        <Field l="Toe-In" v={toe} u="in" d />
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
  const diffReason = basket.baseline
    ? "Setup diff unavailable \u2014 baseline setup snapshot not found."
    : "Add a baseline run to Compare Basket to view setup diff.";

  const handlePlatform = useCallback(() => setWorkspace("platform_trace", "setup_table"), [setWorkspace]);
  const handleMap = useCallback(() => setWorkspace("map", "setup_table"), [setWorkspace]);

  if (!setup) {
    return (
      <section className="workspace-section">
        <h2>Setup Board</h2>
        <div className="gr-empty">
          <Sliders size={40} style={{ opacity: 0.2 }} />
          <p style={{ fontSize: 13, color: "#8d9aaa", marginTop: 8 }}>No setup snapshot available.</p>
          <p className="section-note">Import a run with a CarSetup section to populate the setup board.</p>
        </div>
      </section>
    );
  }

  const car = overview.session.car_name ?? "Unknown Car";
  const track = overview.session.track_display_name ?? overview.session.track_name ?? "";

  return (
    <section className="garage-board">
      {/* ── Top Bar ── */}
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
              <span>{evtName}</span>
              {selection.selectedLap && <span className="gr-ev-lap">L{selection.selectedLap}</span>}
              <span className={`gr-ev-tag ${isInferred ? "inferred" : "explicit"}`}>
                {isInferred ? "Inferred" : "Explicit"}
              </span>
              <button className="gr-icon-btn" onClick={handlePlatform} title="Platform"><Layers size={12} /></button>
              <button className="gr-icon-btn" onClick={handleMap} title="Map"><MapPin size={12} /></button>
            </div>
          )}
          <div className="gr-diff-tabs">
            <button className={`gr-diff-tab ${diffMode === "current" ? "active" : ""}`} onClick={() => setDiffMode("current")}>Current</button>
            <button className={`gr-diff-tab ${diffMode === "diff" ? "active" : ""}`} onClick={() => setDiffMode("diff")}>Diff</button>
          </div>
        </div>
      </div>

      {showDiffUnavailable && <p className="gr-diff-empty">{diffReason}</p>}

      {/* ── Top Row: Controls / Balance / ARB&Diff ── */}
      <div className="gr-toprow">

        {/* Steering / Controls */}
        <div className="gr-card">
          <div className="gr-card-head"><Gauge size={12} /> Steering / Controls</div>
          <div className="gr-card-body">
            <Field l="Steering Ratio" v={setup.steering_ratio ?? null} />
            <Field l="Offset" v={setup.steering_offset_deg ?? null} u="deg" />
            <Field l="Pinion" v={evNum(setup, "steering_pinion_mm")} u="mm/rev" d />
            <Field l="Brake Bias" v={setup.front_brake_bias_percent ?? null} u="%" />
            <Field l="Front Master Cyl" v={evNum(setup, "front_mc_mm")} u="mm" d />
            <Field l="Rear Master Cyl" v={evNum(setup, "rear_mc_mm")} u="mm" d />
            <Field l="Tape" v={setup.tape_percent ?? null} u="%" />
            <Field l="Rear Gear" v={setup.rear_end_ratio ?? null} u=":1" />
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
            } u="%" d />
            <Field l="Final Drive" v={evNum(setup, "final_drive_ratio")} u=":1" d />
          </div>
        </div>

        {/* ARB / Diff */}
        <div className="gr-card">
          <div className="gr-card-head" onClick={() => setArbOpen(!arbOpen)} style={{ cursor: "pointer" }}>
            <Wrench size={12} /> ARB / Diff
            <span style={{ marginLeft: "auto" }}>{arbOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span>
          </div>
          {arbOpen && (
            <div className="gr-card-body">
              <div className="gr-subhead">Front ARB</div>
              <Field l="Diameter" v={imp(evNum(setup, "front_arb_diameter_mm"), MM_IN, 3)} u="in" />
              <Field l="Arm Length" v={imp(evNum(setup, "front_arb_arm_mm"), MM_IN, 3)} u="in" d />
              <Field l="Preload" v={imp(evNum(setup, "front_arb_preload_nm"), NM_FTLB, 1)} u="ft-lb" d />
              <div className="gr-subhead">Rear ARB</div>
              <Field l="Diameter" v={imp(evNum(setup, "rear_arb_diameter_mm"), MM_IN, 3)} u="in" />
              <Field l="Arm Length" v={imp(evNum(setup, "rear_arb_arm_mm"), MM_IN, 3)} u="in" d />
              <Field l="Preload" v={imp(evNum(setup, "rear_arb_preload_nm"), NM_FTLB, 1)} u="ft-lb" d />
              <div className="gr-subhead">Differential</div>
              <Field l="Preload" v={imp(evNum(setup, "diff_preload_nm"), NM_FTLB, 1)} u="ft-lb" d />
            </div>
          )}
        </div>
      </div>

      {/* ── Four Corner Panels — 2×2 ── */}
      <div className="gr-corners">
        <CornerPanel label="LEFT FRONT"   corner="lf" setup={setup} glow={focusZone === "front" || focusZone === "all" || focusZone === "steering"} />
        <CornerPanel label="RIGHT FRONT"  corner="rf" setup={setup} glow={focusZone === "front" || focusZone === "all" || focusZone === "steering"} />
        <CornerPanel label="LEFT REAR"    corner="lr" setup={setup} glow={focusZone === "rear"  || focusZone === "all"} />
        <CornerPanel label="RIGHT REAR"   corner="rr" setup={setup} glow={focusZone === "rear"  || focusZone === "all"} />
      </div>
    </section>
  );
}
