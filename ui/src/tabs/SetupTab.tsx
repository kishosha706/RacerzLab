import { AlertTriangle, BrainCircuit, Crosshair, Gauge, Layers, MapPin, ShieldCheck, Sliders, Wrench } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchSetup } from "../api/client";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";
import { useCompareBasket } from "../store/CompareBasketContext";
import { EngineeringAwarenessPanel } from "../components/EngineeringAwarenessPanel";
import { VehicleSystemsPanel } from "../components/VehicleSystemsPanel";
import type { RunOverview, SetupSnapshot, TelemetryEvent } from "../types/telemetry";

type SetupTabProps = {
  overview: RunOverview;
  sessionId?: string | null;
  onToggleMapOverlay?: () => void;
};

type SetupEvidenceFocus = Pick<TelemetryEvent, "event_id" | "event_type" | "related_setup_keys"> &
  Partial<Pick<
    TelemetryEvent,
    | "event_subtype"
    | "lap_number"
    | "lap_pct_peak"
    | "zone_name"
    | "valid_for_tuning"
    | "evidence_state"
    | "source_channels"
    | "blocker_reasons"
  >> & {
    trusted_overview_event: boolean;
  };

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
function evText(s: SetupSnapshot, k: string): string | null {
  const v = s.extracted_values?.[k];
  return typeof v === "string" && v.trim() ? v : null;
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
  { key: "tape_percent", group: "Aero/cooling", label: "Tape / Cooling", unit: "%", decimals: 0, value: (s) => s.tape_percent ?? null },
  { key: "rear_end_ratio", group: "Gearing", label: "Rear End Ratio", unit: ":1", decimals: 3, value: (s) => s.rear_end_ratio ?? null },
  { key: "front_brake_bias_percent", group: "Brakes", label: "Front Brake Bias", unit: "%", decimals: 1, value: (s) => s.front_brake_bias_percent ?? null },
  { key: "steering_ratio", group: "Driver controls", label: "Steering Ratio / Pinion", value: (s) => s.steering_ratio ?? deriveSteeringRatio(evNum(s, "steering_pinion_mm")) },
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
  return `${value}${unit && typeof value === "number" ? ` ${unit}` : ""}`;
}

function formatDelta(baseline: SetupDiffValue, current: SetupDiffValue, decimals = 3): string {
  if (typeof baseline !== "number" || typeof current !== "number") return "changed";
  const delta = current - baseline;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(decimals)}`;
}

function normalizedSetupKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

function isEvidenceLinkedControl(relevantKeys: ReadonlySet<string>, ...candidateKeys: string[]): boolean {
  if (relevantKeys.size === 0) return false;
  return candidateKeys.some((candidate) => {
    const normalizedCandidate = normalizedSetupKey(candidate);
    return Array.from(relevantKeys).some((key) => key === normalizedCandidate || key.endsWith(`_${normalizedCandidate}`));
  });
}

// ── Field Row ────────────────────────────────────────────────────
function Field({ l, v, u, imp: isImp, relevant = false }: {
  l: string; v: string | number | null | undefined;
  u?: string; imp?: boolean; relevant?: boolean;
}) {
  const missing = v == null || (typeof v === "number" && !Number.isFinite(v)) || (typeof v === "object");
  const cls = ["gr-row"];
  if (missing) cls.push("missing");
  else if (isImp) cls.push("important");
  if (relevant) cls.push("evidence-linked");
  return (
    <div className={cls.join(" ")} role="row" data-evidence-linked={relevant ? "true" : undefined}>
      <span className="gr-label" role="rowheader">{l}</span>
      <span className="gr-value" role="cell">{missing ? "—" : v}</span>
      <span className="gr-value-unit" aria-hidden={missing || !u ? "true" : undefined}>{missing ? "" : (u ?? "")}</span>
      {relevant && <span className="gr-row-evidence" role="cell">Evidence-linked</span>}
    </div>
  );
}

// ── Corner Panel ─────────────────────────────────────────────────
function CornerPanel({ label, corner, setup, glow, relevantKeys }: {
  label: string; corner: string; setup: SetupSnapshot; glow?: boolean; relevantKeys: ReadonlySet<string>;
}) {
  const wt     = imp(evCorner(setup, corner, "corner_weight_kg"), N_LB, 0);
  const rh     = imp(evCorner(setup, corner, "ride_height_mm"), MM_IN, 3);
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
  const frontCorner = corner === "lf" || corner === "rf";
  const relevant = (...keys: string[]) => isEvidenceLinkedControl(
    relevantKeys,
    ...keys.flatMap((key) => [`${corner}_${key}`, `${corner}.${key}`]),
  );

  return (
    <div className={`gr-corner${glow ? " glow" : ""}`} data-corner={corner} role="region" aria-label={`${label} setup controls`}>
      <div className="gr-corner-head">{label}</div>
      <div className="gr-corner-body">
        <Field l="Tire PSI" v={psi} u="psi" imp relevant={relevant("cold_pressure_kpa", "pressure")} />
        <Field l="Ride Height" v={rh} u="in" imp relevant={relevant("ride_height_mm", "ride_height")} />
        <Field l="Spring Rate" v={spring} u="lb/in" imp relevant={relevant("spring_rate_n_per_mm", `${frontCorner ? "front" : "rear"}_spring_n_per_mm`, "spring")} />
        <Field l="Corner Weight" v={wt} u="lb" imp relevant={relevant("corner_weight_kg", "corner_weight")} />
        <div className="gr-group-head">Dampers</div>
        <Field l="LS Compression" v={lsC} u="clk" relevant={relevant("ls_compression")} />
        <Field l="HS Compression" v={hsC} u="clk" relevant={relevant("hs_compression")} />
        <Field l="HS Comp Slope" v={hsCS} relevant={relevant("hs_comp_slope")} />
        <Field l="LS Rebound" v={lsR} u="clk" relevant={relevant("ls_rebound")} />
        <Field l="HS Rebound" v={hsR} u="clk" relevant={relevant("hs_rebound")} />
        <Field l="HS Reb Slope" v={hsRS} relevant={relevant("hs_reb_slope")} />
        <div className="gr-group-head">Alignment</div>
        <Field l="Camber" v={camber} u="deg" relevant={relevant("camber_deg", "camber")} />
        {frontCorner && <Field l="Caster" v={caster} u="deg" relevant={relevant("caster_deg", "caster")} />}
        <Field l="Toe-In" v={toe} u="in" relevant={relevant("toe_in_mm", "toe")} />
      </div>
    </div>
  );
}

// ── Main ─────────────────────────────────────────────────────────
export function SetupTab({ overview, sessionId = null, onToggleMapOverlay }: SetupTabProps) {
  const setupIdentityMismatch = Boolean(
    overview.setup_snapshot && overview.setup_snapshot.run_id !== overview.run_id,
  );
  const setup = setupIdentityMismatch ? null : overview.setup_snapshot;
  const { selection, setWorkspace } = useTelemetrySelection();
  const learning = selection.selectedMode === "learning";
  const { basket } = useCompareBasket();
  const hasValidBaselineComparison = Boolean(
    setup
    && basket.baseline
    && basket.baseline.has_setup_snapshot
    && !basket.baseline.stale
    && basket.baseline.run_id !== overview.run_id,
  );
  const currentCarIdentity = overview.session.car_name ?? null;
  const currentTrackIdentity = overview.session.track_display_name ?? overview.session.track_name ?? null;
  const setupComparisonContextMatches = Boolean(
    basket.baseline
    && basket.baseline.car
    && currentCarIdentity
    && basket.baseline.car === currentCarIdentity
    && basket.baseline.track
    && currentTrackIdentity
    && basket.baseline.track === currentTrackIdentity,
  );
  const comparisonKey = hasValidBaselineComparison ? `${basket.baseline?.run_id}:${overview.run_id}` : null;
  const [diffMode, setDiffMode] = useState<"current" | "diff">(hasValidBaselineComparison ? "diff" : "current");
  const defaultedComparisonKeyRef = useRef<string | null>(comparisonKey);
  const [baselineSetup, setBaselineSetup] = useState<SetupSnapshot | null>(null);
  const [baselineSetupLoading, setBaselineSetupLoading] = useState(false);
  const [baselineSetupError, setBaselineSetupError] = useState<string | null>(null);

  const selectedEvent = useMemo<SetupEvidenceFocus | null>(() => {
    if (!selection.selectedEventId) return null;
    const overviewEvent = overview.events.find(e => e.event_id === selection.selectedEventId);
    if (overviewEvent) return { ...overviewEvent, trusted_overview_event: true };
    try {
      const raw = window.sessionStorage.getItem("racelab_setup_evidence_focus");
      if (!raw) return null;
      const handoff = JSON.parse(raw) as Record<string, unknown>;
      if (handoff.run_id !== overview.run_id || handoff.event_id !== selection.selectedEventId) return null;
      if (typeof handoff.event_type !== "string" || typeof handoff.event_title !== "string") return null;
      return {
        event_id: handoff.event_id,
        event_type: handoff.event_type,
        event_subtype: handoff.event_title,
        lap_number: typeof handoff.lap_number === "number" ? handoff.lap_number : null,
        lap_pct_peak: typeof handoff.lap_pct_peak === "number" ? handoff.lap_pct_peak : null,
        related_setup_keys: Array.isArray(handoff.related_setup_keys)
          ? handoff.related_setup_keys.filter((key): key is string => typeof key === "string")
          : [],
        valid_for_tuning: false,
        trusted_overview_event: false,
      };
    } catch {
      return null;
    }
  }, [overview.events, overview.run_id, selection.selectedEventId]);

  const isInferred = selectedEvent
    ? !selectedEvent.trusted_overview_event || (selectedEvent.related_setup_keys?.length ?? 0) === 0
    : false;
  const evtName = selectedEvent
    ? (selectedEvent.event_subtype ?? selectedEvent.event_type.replace(/_/g, " "))
    : null;

  const relevantSetupKeys = useMemo(
    () => new Set((selectedEvent?.related_setup_keys ?? []).map(normalizedSetupKey)),
    [selectedEvent],
  );

  useEffect(() => {
    if (comparisonKey && comparisonKey !== defaultedComparisonKeyRef.current) {
      setDiffMode("diff");
    } else if (!comparisonKey && defaultedComparisonKeyRef.current) {
      setDiffMode("current");
    }
    defaultedComparisonKeyRef.current = comparisonKey;
  }, [comparisonKey]);

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
  const relevant = (...keys: string[]) => isEvidenceLinkedControl(relevantSetupKeys, ...keys);

  const showDiffUnavailable = diffMode === "diff" && !hasValidBaselineComparison;
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
    const canLoadBaseline = diffMode === "diff" && baselineRunId && hasValidBaselineComparison;
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
        if (nextSetup.run_id !== baselineRunId) {
          setBaselineSetup(null);
          setBaselineSetupError("Baseline setup identity did not match the selected run.");
          return;
        }
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
  }, [basket.baseline, diffMode, hasValidBaselineComparison, overview.run_id, overview.setup_snapshot]);

  const handlePlatform = useCallback(() => setWorkspace("platform_trace", "setup_table"), [setWorkspace]);
  const handleMap = useCallback(() => onToggleMapOverlay?.(), [onToggleMapOverlay]);
  const handleDialIn = useCallback(() => setWorkspace("dial_in", "setup_table"), [setWorkspace]);
  const handleEngineer = useCallback(() => setWorkspace("engineer", "setup_table"), [setWorkspace]);

  if (!setup) {
    return (
      <section className="garage-board">
        <section
          className="tab-decision-broadcast setup-decision-broadcast"
          data-state="blocked"
          data-diagnostic-state="unavailable"
          data-authority="withheld"
          data-run-id={overview.run_id}
          aria-labelledby="setup-decision-title"
          aria-live="polite"
        >
          <div>
            <h2 id="setup-decision-title">Garage snapshot missing for this run</h2>
            <p><strong>Why:</strong> No setup change is authorized by this tab because no exact run-owned snapshot is available.</p>
            <p><strong>What next:</strong> Capture the setup with the next telemetry import, then return here before comparing or planning a test.</p>
            <div className="tab-decision-facts" aria-label="Setup scope and authority">
              <span>Diagnostic <strong>Unavailable</strong></span>
              <span>Scope <strong>Current run</strong></span>
              <span><ShieldCheck size={12} /> Authority <strong>Withheld</strong></span>
              <span>Next <strong>Recover setup evidence</strong></span>
            </div>
            {selection.selectedMode === "learning" && setupIdentityMismatch && (
              <p className="section-note">A setup row was withheld because its run identity did not match the open run.</p>
            )}
          </div>
          <div className="tab-handoff-actions" aria-label="Setup evidence handoffs">
            <button type="button" onClick={handleEngineer}>
              <BrainCircuit size={14} /> Ask Engineer
            </button>
            <button type="button" onClick={handleDialIn}>
              <Crosshair size={14} /> Test prerequisites
            </button>
          </div>
        </section>
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
  const steeringControlLabel = typeof displayRatio === "string" && displayRatio.toLowerCase().includes("mm/rev")
    ? "Steering Pinion"
    : "Steering Ratio";
  // Master cylinders → imperial
  const frontMc = imp(evNum(setup, "front_mc_mm"), MM_IN, 3);
  const rearMc  = imp(evNum(setup, "rear_mc_mm"), MM_IN, 3);
  const hasQualifiedEvidenceLink = Boolean(
    selectedEvent?.trusted_overview_event
    && selectedEvent.valid_for_tuning
    && relevantSetupKeys.size > 0,
  );
  const setupDecisionState = selectedEvent
    ? hasQualifiedEvidenceLink ? "evidence_linked" : "context_only"
    : "recorded_snapshot";
  const evidenceLap = selectedEvent?.lap_number ?? null;
  const evidencePct = selectedEvent?.lap_pct_peak ?? null;
  const evidenceScope = [
    evidenceLap != null ? `Lap ${evidenceLap}` : null,
    evidencePct != null ? `${evidencePct.toFixed(1)}%` : null,
    selectedEvent?.zone_name ?? null,
  ].filter((value): value is string => value != null).join(" · ") || "Current run";
  const comparisonStatus = diffMode === "current"
    ? "Current snapshot"
    : !hasValidBaselineComparison
      ? "Diff unavailable"
      : baselineSetupLoading
        ? "Checking baseline"
        : baselineSetupError
          ? "Baseline unavailable"
          : baselineSetup
            ? `${setupDiffRows.length} displayed difference${setupDiffRows.length === 1 ? "" : "s"}`
            : "Baseline pending";
  const decisionTitle = selectedEvent
    ? hasQualifiedEvidenceLink
      ? `Inspect ${relevantSetupKeys.size} evidence-linked control${relevantSetupKeys.size === 1 ? "" : "s"}`
      : "Evidence context received; control attribution withheld"
    : "Recorded setup reference; choose evidence before changing it";
  const nextHandoff = selectedEvent
    ? hasQualifiedEvidenceLink
      ? "Verify one legal change"
      : "Qualify the cause first"
    : "Select a diagnostic first";
  const setupDecisionWhy = selectedEvent
    ? hasQualifiedEvidenceLink
      ? `${relevantSetupKeys.size} recorded control${relevantSetupKeys.size === 1 ? " is" : "s are"} explicitly linked to this tuning-valid event. The link narrows inspection; it does not choose a target.`
      : "The exact evidence location is preserved, but its producer did not supply a trusted, tuning-valid control link."
    : "This is the setup captured with the current run. Without selected evidence it is a reference, not a change request.";
  const setupDecisionNext = selectedEvent
    ? hasQualifiedEvidenceLink
      ? "Inspect the highlighted controls, ask Engineer to test the explanation, then let Dial-In verify one legal change."
      : "Return to Platform or Engineer and qualify the cause before touching a garage control."
    : "Choose a qualified diagnostic in Overview or Platform before deciding whether any control deserves a test.";
  const setupHeadlineMetric = hasQualifiedEvidenceLink
    ? `${relevantSetupKeys.size} linked control${relevantSetupKeys.size === 1 ? "" : "s"}`
    : baselineSetup && hasValidBaselineComparison
      ? `${setupDiffRows.length} displayed change${setupDiffRows.length === 1 ? "" : "s"}`
      : "Recorded reference";
  const rfColdPressurePsi = imp(evCorner(setup, "rf", "cold_pressure_kpa"), KPA_PSI, 1);
  const rrColdPressurePsi = imp(evCorner(setup, "rr", "cold_pressure_kpa"), KPA_PSI, 1);
  const rearEndRatio = setup.rear_end_ratio ?? evNum(setup, "final_drive_ratio");
  const setupTechState = overview.session.setup_passed_tech === true
    ? "Passed when recorded"
    : overview.session.setup_passed_tech === false
      ? "Not passed when recorded"
      : "Not reported";
  const setupModifiedState = overview.session.setup_modified === true
    ? "Modified"
    : overview.session.setup_modified === false
      ? "Unmodified"
      : "Not reported";
  const changeGuard = !hasValidBaselineComparison
    ? {
        state: "reference" as const,
        headline: "Reference only",
        detail: "Stage a distinct run with its own setup snapshot before auditing what changed.",
      }
    : !setupComparisonContextMatches
      ? {
          state: "withheld" as const,
          headline: "Context mismatch",
          detail: "A one-change audit requires the same known car and track configuration. The displayed diff remains reference-only.",
        }
    : diffMode !== "diff"
      ? {
          state: "reference" as const,
          headline: "Comparison staged",
          detail: "Open Diff to audit the displayed fields against the selected baseline.",
        }
      : baselineSetupLoading
        ? {
            state: "checking" as const,
            headline: "Checking displayed changes",
            detail: "The baseline snapshot is loading; no one-change claim is available yet.",
          }
        : baselineSetupError || !baselineSetup
          ? {
              state: "withheld" as const,
              headline: "Change audit withheld",
              detail: "The baseline snapshot is unavailable, so the app cannot count displayed differences.",
            }
          : setupDiffRows.length === 0
            ? {
                state: "clear" as const,
                headline: "No displayed changes",
                detail: "The tracked setup fields match this baseline. This is not proof that every hidden or unsupported garage value matches.",
              }
            : setupDiffRows.length === 1
              ? {
                  state: "single" as const,
                  headline: "One displayed change",
                  detail: "One tracked difference is visible. Dial-In must still verify the complete snapshot, legality, and evidence before a test.",
                }
              : {
                  state: "multiple" as const,
                  headline: `${setupDiffRows.length} displayed changes`,
                  detail: "Multiple tracked differences reduce causal confidence. Return to one small legal change before an A/B/A2 test.",
                };

  return (
    <section className="garage-board">
      <EngineeringAwarenessPanel runId={overview.run_id} sessionId={sessionId} surface="setup" />
      <VehicleSystemsPanel runId={overview.run_id} sessionId={sessionId} learning={learning} surface="setup" />
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
              {evidenceLap != null && <span className="gr-ev-lap">L{evidenceLap}</span>}
              {evidencePct != null && (
                <span className="gr-ev-pct">{evidencePct.toFixed(1)}%</span>
              )}
              {selectedEvent.zone_name && (
                <span className="gr-ev-zone">{selectedEvent.zone_name}</span>
              )}
              <span className={`gr-ev-tag ${isInferred ? "inferred" : "explicit"}`}>
                {isInferred ? "Inferred" : "Explicit"}
              </span>
              {focusZone !== "none" && <span className="gr-ev-tag explicit">{focusZone === "all" ? "Front/Rear" : focusZone.charAt(0).toUpperCase() + focusZone.slice(1)}</span>}
            </div>
          )}
        </div>
      </div>

      <section
        className="tab-decision-broadcast setup-decision-broadcast"
        data-state={hasQualifiedEvidenceLink ? "attention" : "guarded"}
        data-diagnostic-state={setupDecisionState}
        data-authority="withheld"
        data-run-id={overview.run_id}
        aria-labelledby="setup-decision-title"
        aria-live="polite"
      >
        <div>
          <h2 id="setup-decision-title">{decisionTitle}</h2>
          <p><strong>Why:</strong> {setupDecisionWhy}</p>
          <p><strong>What next:</strong> {setupDecisionNext}</p>
          <p className="section-note">
            {selectedEvent
              ? hasQualifiedEvidenceLink
                ? "Use the highlighted controls to understand the diagnostic. No setup change is authorized by this tab."
                : "The exact evidence location is preserved, but no trusted control link is available. No setup change is authorized by this tab."
              : "These are recorded values, not a recommendation. No setup change is authorized by this tab."}
          </p>
          <div className="tab-decision-facts" aria-label="Setup scope and authority">
            <span>Diagnostic <strong>{selectedEvent ? evtName : "None selected"}</strong></span>
            <span>Scope <strong>{selectedEvent ? evidenceScope : "Current run - recorded setup snapshot"}</strong></span>
            <span>Headline <strong>{setupHeadlineMetric}</strong></span>
            <span>Comparison <strong>{comparisonStatus}</strong></span>
            <span><ShieldCheck size={12} /> Authority <strong>Withheld</strong></span>
            <span>Next <strong>{nextHandoff}</strong></span>
          </div>
          {selection.selectedMode === "learning" && (
            <div className="tab-decision-learning">
              <p>
                <strong>Why:</strong> Setup values describe what was recorded. Evidence linkage identifies controls worth inspecting, while exact targets remain behind Dial-In's server-verified one-change workflow.
              </p>
              {selectedEvent && (
                <p>
                  Evidence status: {selectedEvent.trusted_overview_event
                    ? selectedEvent.evidence_state?.replace(/_/g, " ") ?? "not reported"
                    : "context handoff only"}
                  {selectedEvent.source_channels?.length
                    ? ` · Channels: ${selectedEvent.source_channels.join(", ")}`
                    : ""}
                  {selectedEvent.blocker_reasons?.[0]
                    ? ` · Blocker: ${selectedEvent.blocker_reasons[0]}`
                    : ""}
                </p>
              )}
            </div>
          )}
        </div>
        <div className="tab-handoff-actions" aria-label="Setup evidence handoffs">
          <button type="button" onClick={handlePlatform}>
            <Layers size={14} /> {selectedEvent ? "Trace evidence" : "Platform evidence"}
          </button>
          <button type="button" onClick={handleEngineer}>
            <BrainCircuit size={14} /> Ask Engineer
          </button>
          {hasQualifiedEvidenceLink && (
            <button type="button" onClick={handleDialIn}>
              <Crosshair size={14} /> Verify change
            </button>
          )}
          {selectedEvent && selection.selectedMode === "learning" && onToggleMapOverlay && (
            <button type="button" onClick={handleMap}>
              <MapPin size={14} /> Show location
            </button>
          )}
        </div>
      </section>

      <section
        className="workspace-section setup-driver-snapshot"
        data-setup-reference="run-owned"
        data-run-id={overview.run_id}
        aria-labelledby="setup-driver-snapshot-title"
      >
        <div className="section-heading-row">
          <div>
            <span className="eyebrow">Driver Reference</span>
            <h2 id="setup-driver-snapshot-title"><Gauge size={16} /> Setup at a glance</h2>
            <p className="section-note">The setup that produced this telemetry, the oval controls drivers ask for first, and the one-change audit.</p>
          </div>
          <span className="gr-tag source">Recorded snapshot</span>
        </div>
        <div className="setup-driver-snapshot-grid">
          <article className="setup-driver-reference-card" data-reference-state="exact-run">
            <span className="eyebrow">Reference identity</span>
            <strong>{setup.setup_name ?? "Unnamed Setup"}</strong>
            <dl className="setup-driver-facts">
              <div><dt>Tech</dt><dd>{setupTechState}</dd></div>
              <div><dt>File state</dt><dd>{setupModifiedState}</dd></div>
              <div><dt>Run</dt><dd>{selection.selectedMode === "learning" ? overview.run_id : "Current run"}</dd></div>
            </dl>
            {selection.selectedMode === "learning" && (
              <small>Snapshot {setup.setup_id}. Recorded identity is context, not setup authority.</small>
            )}
          </article>

          <article className="setup-driver-anchor-card">
            <span className="eyebrow">Oval decision anchors</span>
            <dl className="setup-driver-facts setup-driver-anchor-facts">
              <div><dt>Cross</dt><dd>{formatDiffValue(setup.cross_weight_percent ?? null, "%")}</dd></div>
              <div><dt>Nose</dt><dd>{formatDiffValue(setup.nose_weight_percent ?? null, "%")}</dd></div>
              <div><dt>Brake bias</dt><dd>{formatDiffValue(setup.front_brake_bias_percent ?? null, "%")}</dd></div>
              <div><dt>Tape</dt><dd>{formatDiffValue(typeof setup.tape_percent === "number" ? setup.tape_percent : null, "%")}</dd></div>
              <div><dt>RF cold</dt><dd>{formatDiffValue(rfColdPressurePsi, "psi")}</dd></div>
              <div><dt>RR cold</dt><dd>{formatDiffValue(rrColdPressurePsi, "psi")}</dd></div>
              <div><dt>Rear gear</dt><dd>{formatDiffValue(rearEndRatio, ":1")}</dd></div>
              <div><dt>Steering</dt><dd>{displayRatio ?? "Unavailable"}</dd></div>
            </dl>
          </article>

          <article
            className="setup-one-change-guard"
            data-one-change-state={changeGuard.state}
            data-authority="withheld"
          >
            <span className="eyebrow"><ShieldCheck size={12} /> One-change guard</span>
            <strong>{changeGuard.headline}</strong>
            <p>{changeGuard.detail}</p>
            <small>Displayed differences are an audit aid, never permission to change the car.</small>
            <div className="toolbar-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setDiffMode("diff")}
                disabled={!hasValidBaselineComparison || diffMode === "diff"}
              >
                <Layers size={13} /> Audit displayed changes
              </button>
              <button className="secondary-button" type="button" onClick={handleEngineer}>
                <BrainCircuit size={13} /> Explain evidence
              </button>
            </div>
          </article>
        </div>
      </section>

      <div className="gr-view-control">
        <div className="gr-diff-tabs" role="group" aria-label="Setup view mode">
          <button
            type="button"
            className={`gr-diff-tab ${diffMode === "current" ? "active" : ""}`}
            onClick={() => setDiffMode("current")}
            aria-pressed={diffMode === "current"}
          >
            Current
          </button>
          <button
            type="button"
            className={`gr-diff-tab ${diffMode === "diff" ? "active" : ""}`}
            onClick={() => setDiffMode("diff")}
            aria-pressed={diffMode === "diff"}
          >
            Diff
          </button>
        </div>
        <span>
          {diffMode === "diff" && hasValidBaselineComparison
            ? `Changes from ${basket.baseline?.label ?? "selected baseline"}`
            : "Recorded values from the current setup snapshot"}
        </span>
      </div>
      {showDiffUnavailable && (
        <div className="map-warning-banner setup-diff-warning" role="alert">
          <AlertTriangle size={14} />
          <span>Diff unavailable - select a different, available run with a real setup snapshot. Current setup values remain available.</span>
        </div>
      )}
      {diffMode === "diff" && hasValidBaselineComparison && basket.baseline && (
        <div id="setup-diff-values" className="setup-diff-list" aria-live="polite">
          {baselineSetupLoading && (
            <p className="setup-diff-empty" role="status">Loading baseline setup...</p>
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

      <div className="setup-current-board-heading" id="setup-current-values">
        <div>
          <span className="eyebrow">{diffMode === "diff" ? "Current reference" : "Setup board"}</span>
          <strong>{diffMode === "diff" ? "Current setup values" : "Car systems and corners"}</strong>
        </div>
        {relevantSetupKeys.size > 0 && (
          <span className="setup-evidence-count"><Crosshair size={12} /> {relevantSetupKeys.size} evidence-linked control{relevantSetupKeys.size === 1 ? "" : "s"}</span>
        )}
      </div>

      {/* 2) High-value setup systems */}
      <div className="gr-toprow">
        <div className="gr-card setup-system-card setup-system-steering" data-evidence-relevant={relevant("steering_ratio", "steering_pinion_mm", "steering_offset_deg", "front_brake_bias_percent") ? "true" : undefined} data-evidence-context={relevantSetupKeys.size === 0 && focusZone === "steering" ? "true" : undefined}>
          <div className="gr-card-head"><Gauge size={12} /> Steering / Control</div>
          <div className="gr-card-body">
            <Field l={steeringControlLabel} v={displayRatio ?? null} relevant={relevant("steering_ratio", "steering_pinion_mm")} />
            {derivedRatio && pinion != null && (
              <Field l="Steering Pinion" v={pinion} u="mm/rev" relevant={relevant("steering_pinion_mm")} />
            )}
            <Field l="Steering Offset" v={setup.steering_offset_deg ?? null} u="deg" relevant={relevant("steering_offset_deg")} />
            <Field l="Front Brake Bias" v={setup.front_brake_bias_percent ?? null} u="%" relevant={relevant("front_brake_bias_percent")} />
            <Field l="Front Master Cyl" v={frontMc} u="in" relevant={relevant("front_mc_mm")} />
            <Field l="Rear Master Cyl" v={rearMc} u="in" relevant={relevant("rear_mc_mm")} />
            <Field l="Tape / Cooling" v={setup.tape_percent ?? null} u={typeof setup.tape_percent === "number" ? "%" : undefined} relevant={relevant("tape_percent")} />
          </div>
        </div>

        <div className="gr-card setup-system-card setup-system-balance" data-evidence-relevant={relevant("nose_weight_percent", "cross_weight_percent", "final_drive_ratio") ? "true" : undefined} data-evidence-context={relevantSetupKeys.size === 0 && (focusZone === "front" || focusZone === "rear" || focusZone === "all") ? "true" : undefined}>
          <div className="gr-card-head"><Crosshair size={12} /> Balance</div>
          <div className="gr-card-body">
            <Field l="Nose Weight" v={setup.nose_weight_percent ?? null} u="%" relevant={relevant("nose_weight_percent")} />
            <Field l="Cross Weight" v={setup.cross_weight_percent ?? null} u="%" relevant={relevant("cross_weight_percent")} />
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
            <Field l="Rear End Ratio" v={evNum(setup, "final_drive_ratio")} u=":1" relevant={relevant("rear_end_ratio", "final_drive_ratio")} />
          </div>
        </div>

        <div className="gr-card setup-system-card setup-system-arb" data-evidence-relevant={relevant("front_arb_diameter_mm", "front_arb_arm_position", "front_arb_preload_nm", "rear_arb_diameter_mm", "rear_arb_arm_position", "rear_arb_preload_nm") ? "true" : undefined} data-evidence-context={relevantSetupKeys.size === 0 && (focusZone === "front" || focusZone === "rear" || focusZone === "all") ? "true" : undefined}>
          <div className="gr-card-head"><Wrench size={12} /> ARB</div>
          <div className="gr-card-body">
            <div className="gr-subhead">Front ARB</div>
            <Field l="Diameter" v={imp(evNum(setup, "front_arb_diameter_mm"), MM_IN, 3)} u="in" relevant={relevant("front_arb_diameter_mm")} />
            <Field l="Arm Position" v={evText(setup, "front_arb_arm_position")} relevant={relevant("front_arb_arm_position")} />
            <Field l="Preload" v={imp(evNum(setup, "front_arb_preload_nm"), NM_FTLB, 1)} u="ft-lb" relevant={relevant("front_arb_preload_nm")} />
            <Field l="Attach" v={evNum(setup, "front_arb_attach")} relevant={relevant("front_arb_attach")} />
            <div className="gr-subhead">Rear ARB</div>
            <Field l="Diameter" v={imp(evNum(setup, "rear_arb_diameter_mm"), MM_IN, 3)} u="in" relevant={relevant("rear_arb_diameter_mm")} />
            <Field l="Arm Position" v={evText(setup, "rear_arb_arm_position")} relevant={relevant("rear_arb_arm_position")} />
            <Field l="Preload" v={imp(evNum(setup, "rear_arb_preload_nm"), NM_FTLB, 1)} u="ft-lb" relevant={relevant("rear_arb_preload_nm")} />
          </div>
        </div>

        <div className="gr-card setup-system-card setup-system-diff" data-evidence-relevant={relevant("diff_preload_nm", "rear_end_ratio", "final_drive_ratio") ? "true" : undefined}>
          <div className="gr-card-head"><Layers size={12} /> Diff</div>
          <div className="gr-card-body">
            <Field l="Diff Preload" v={imp(evNum(setup, "diff_preload_nm"), NM_FTLB, 1)} u="ft-lb" relevant={relevant("diff_preload_nm")} />
            <Field l="Rear End Ratio" v={setup.rear_end_ratio ?? evNum(setup, "final_drive_ratio")} u=":1" relevant={relevant("rear_end_ratio", "final_drive_ratio")} />
          </div>
        </div>
      </div>

      {/* 3) 2x2 Corner Board */}
      <div className="gr-corners" aria-label="Setup by car corner">
        <div className="gr-axle-label front"><span>Front axle</span><small>Direction of travel</small></div>
        <CornerPanel label="LEFT FRONT" corner="lf" setup={setup} relevantKeys={relevantSetupKeys} glow={focusZone === "front" || focusZone === "all" || focusZone === "steering" || focusZone === "tires" || focusZone === "dampers"} />
        <CornerPanel label="RIGHT FRONT" corner="rf" setup={setup} relevantKeys={relevantSetupKeys} glow={focusZone === "front" || focusZone === "all" || focusZone === "steering" || focusZone === "tires" || focusZone === "dampers"} />
        <div className="gr-axle-label rear"><span>Rear axle</span><small>Power delivery</small></div>
        <CornerPanel label="LEFT REAR" corner="lr" setup={setup} relevantKeys={relevantSetupKeys} glow={focusZone === "rear" || focusZone === "all" || focusZone === "tires" || focusZone === "dampers"} />
        <CornerPanel label="RIGHT REAR" corner="rr" setup={setup} relevantKeys={relevantSetupKeys} glow={focusZone === "rear" || focusZone === "all" || focusZone === "tires" || focusZone === "dampers"} />
      </div>

      {/* 5) Related Evidence Links */}
      {selection.selectedMode === "learning" && (
        <div className="toolbar-actions tab-handoff-actions" aria-label="Continue this setup evidence">
          <button className="secondary-button" type="button" onClick={handlePlatform}>
            <Layers size={14} /> {selectedEvent ? "Trace exact evidence" : "Choose platform evidence"}
          </button>
          <button className="secondary-button" type="button" onClick={handleEngineer}>
            <BrainCircuit size={14} /> Explain context
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={handleDialIn}
            disabled={!hasQualifiedEvidenceLink}
            title={hasQualifiedEvidenceLink ? "Open the server-verified one-change workflow" : "Choose a trusted tuning-valid evidence link first"}
          >
            <Crosshair size={14} /> Validate one change
          </button>
          {selectedEvent && onToggleMapOverlay && (
            <button className="secondary-button" type="button" onClick={handleMap}>
              <MapPin size={14} /> Show exact location
            </button>
          )}
        </div>
      )}
    </section>
  );
}
