import { AlertTriangle, ClipboardList, Crosshair, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { analyzeRunDialIn } from "../api/client";
import { useCompareBasket } from "../store/CompareBasketContext";
import type { DialInResponse, DialInSwing, RunOverview } from "../types/telemetry";

type DialInTabProps = { overview: RunOverview | null };

const DIAL_IN_LIMIT = 9;

function cleanLabel(value: string | null | undefined, fallback = "Not mapped"): string {
  if (!value) return fallback;
  const aliases: Record<string, string> = {
    final_drive: "Rear End Ratio",
  };
  if (aliases[value]) return aliases[value];
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function dialInTone(label: string): "good" | "warn" | "neutral" {
  const normalized = label.toLowerCase();
  if (normalized.includes("ready") || normalized.includes("clear") || normalized.includes("clean") || normalized.includes("high")) return "good";
  if (normalized.includes("need") || normalized.includes("partial") || normalized.includes("risk") || normalized.includes("missing") || normalized.includes("some")) return "warn";
  return "neutral";
}

function swingKindLabel(strength: string, risk: string): string {
  const combined = `${strength} ${risk}`.toLowerCase();
  if (combined.includes("package") || combined.includes("big") || combined.includes("high risk")) return "Big swing";
  if (combined.includes("balance")) return "Balance swing";
  if (combined.includes("fine")) return "Fine-tune";
  return "Feel polish";
}

const TARGET_LABELS: Record<string, string> = {
  brake_lock: "brake lock",
  center_balance: "center balance",
  center_rotation: "center rotation",
  center_speed: "center speed",
  correction_count: "correction count",
  cfs_height: "CFS height",
  drag_scrub: "drag/scrub",
  drive_off: "drive-off",
  entry_balance: "entry balance",
  entry_stability: "entry stability",
  entry_yaw: "entry yaw",
  exit_drive: "exit drive",
  exit_yaw: "exit yaw",
  front_contact: "front contact",
  front_height: "front height",
  front_platform_contact: "front platform contact",
  front_response: "front response",
  front_slip: "front slip",
  garage_state: "garage state",
  high_steering_demand: "high steering demand",
  lap_falloff: "lap falloff",
  long_run_falloff: "long-run falloff",
  phase_balance: "phase balance",
  platform_rate: "platform rate",
  platform_stability: "platform stability",
  rear_float: "rear float",
  rear_height: "rear height",
  rear_scrape_margin: "rear scrape margin",
  rear_slip: "rear slip",
  rear_tire_trend: "rear tire trend",
  rf_tire_temp: "RF tire temp",
  ride_height_trace: "ride-height trace",
  scrape: "scrape",
  speed_loss: "speed loss",
  speed_trace: "speed trace",
  steering_correction: "steering correction",
  steering_load: "steering load",
  steering_trace: "steering trace",
  throttle_pickup: "throttle pickup",
  tight_center: "tight center",
  tight_exit: "tight exit",
  tire_overwork: "tire overwork",
  tire_temp: "tire temperature",
  tire_temp_spread: "tire temperature spread",
  tire_trend: "tire trend",
  transition_yaw: "transition yaw",
  turn_in_response: "turn-in response",
  unstable_exit: "unstable exit",
};

function formatTargetLabel(value: string): string {
  return TARGET_LABELS[value] ?? value.replace(/_/g, " ");
}

function formatTargetList(validateWith: string[], watchFor: string[]): string {
  const targets = [...validateWith, ...watchFor].filter((item, index, all) => item && all.indexOf(item) === index);
  return targets.map(formatTargetLabel).join(", ") || "Balance shift";
}

function dialInEvidenceHints(response: DialInResponse): string[] {
  const hints = new Set<string>();
  const nextStep = response.next_step ?? "";
  if (nextStep.includes("Compare baseline is missing")) {
    hints.add("Compare baseline is missing.");
  }
  if (nextStep.includes("Compare test run is missing")) {
    hints.add("Compare test run is missing.");
  }
  for (const warning of response.warnings) {
    const lower = warning.toLowerCase();
    if (lower.includes("car family could not be resolved")) hints.add("Car family is generic, so unsupported legacy-only areas stay filtered.");
    if (lower.includes("track family could not be resolved")) hints.add("Track family is generic, so the guide stays conservative.");
  }
  for (const swing of response.top_swings) {
    if (!swing.readiness_label.toLowerCase().includes("need")) continue;
    const area = swing.setup_area.toLowerCase();
    if (area.includes("shock") || area.includes("damper")) {
      hints.add("Live shock data is missing.");
    }
    if (area.includes("platform") || area.includes("ride") || area.includes("diffuser") || area.includes("rake")) {
      hints.add("Platform trace is missing for a stronger read.");
    }
  }
  return [...hints];
}

function SwingCard({ swing, compact = false }: { swing: DialInSwing; compact?: boolean }) {
  return (
    <article className={`dialin-swing-card${compact ? " compact" : ""}`}>
      <header>
        <div>
          <span>{cleanLabel(swing.setup_area, "Setup area")}</span>
          <h3>{swingKindLabel(swing.strength_label, swing.risk_label)}: {swing.title}</h3>
        </div>
        <div className="dialin-card-pills">
          <span className="dialin-mini-pill">{swing.strength_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.risk_label)}`}>{swing.risk_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.readiness_label)}`}>{swing.readiness_label}</span>
        </div>
      </header>
      <div className="dialin-action-grid">
        <div><span>Goal</span><p>{swing.effect}</p></div>
        <div><span>The Trade-off</span><p>{swing.counter_effect}</p></div>
        <div><span>Your Next Test</span><p>{swing.one_change_test}</p></div>
        <div>
          <span>What to watch for</span>
          <p>{formatTargetList(swing.validate_with, swing.watch_for)}</p>
        </div>
      </div>
    </article>
  );
}

export function DialInTab({ overview }: DialInTabProps) {
  const { basket } = useCompareBasket();
  const storageKey = overview ? `racerzlab:dial-in:${overview.run_id}` : "racerzlab:dial-in";
  const [complaint, setComplaint] = useState("");
  const [response, setResponse] = useState<DialInResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      setComplaint(window.sessionStorage.getItem(storageKey) ?? "");
    } catch {
      setComplaint("");
    }
    setResponse(null);
    setError(null);
  }, [storageKey]);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(storageKey, complaint);
    } catch {
      // Session storage is a convenience only.
    }
  }, [complaint, storageKey]);

  const submitDialIn = useCallback(async () => {
    if (!overview) return;
    const trimmed = complaint.trim();
    if (!trimmed || loading) return;
    const baselineRunId = basket.baseline?.run_id ?? null;
    const usableBaseline = baselineRunId && baselineRunId !== overview.run_id ? baselineRunId : undefined;
    setLoading(true);
    setError(null);
    try {
      const nextResponse = await analyzeRunDialIn(overview.run_id, {
        complaint: trimmed,
        baseline_run_id: usableBaseline,
        limit: DIAL_IN_LIMIT,
        include_debug_evidence: false,
      });
      setResponse(nextResponse);
    } catch (caught) {
      setResponse(null);
      setError(caught instanceof Error ? caught.message : "Dial-in request failed.");
    } finally {
      setLoading(false);
    }
  }, [basket.baseline, complaint, loading, overview]);

  const clearDialIn = useCallback(() => {
    setComplaint("");
    setResponse(null);
    setError(null);
  }, []);

  const chooseClarification = useCallback((option: string) => {
    const base = response?.complaint_raw.trim() || complaint.trim();
    const normalized = base.toLowerCase();
    const refinement = option === "Whole corner" ? "center" : option.toLowerCase();
    const nextComplaint = normalized.includes(refinement) ? base : `${base} ${refinement}`;
    setComplaint(nextComplaint.trim());
    setResponse(null);
    setError(null);
  }, [complaint, response]);

  const hints = response ? dialInEvidenceHints(response) : [];
  const primarySwings = useMemo(() => response?.top_swings.slice(0, 3) ?? [], [response]);
  const secondarySwings = useMemo(() => response?.top_swings.slice(3, DIAL_IN_LIMIT) ?? [], [response]);
  const canSubmit = Boolean(overview) && complaint.trim().length > 0 && !loading;
  const runLabel = overview
    ? `${overview.session.car_name ?? "Unknown car"}${overview.session.track_display_name || overview.session.track_name ? ` - ${overview.session.track_display_name ?? overview.session.track_name}` : ""}`
    : "No run selected";

  if (!overview) {
    return (
      <section className="dialin-tab">
        <div className="dialin-panel dialin-hero">
          <div className="dialin-header">
            <div>
              <h2><ClipboardList size={16} /> Crew Chief Dial-In</h2>
              <p>Select or import a run before using Dial-In.</p>
            </div>
            <span className="dialin-readonly">Read-only</span>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="dialin-tab" aria-labelledby="dialin-title">
      <div className="dialin-panel dialin-hero">
        <div className="dialin-header">
          <div>
            <h2 id="dialin-title"><ClipboardList size={16} /> Crew Chief Dial-In</h2>
            <p>{runLabel}</p>
          </div>
          <span className="dialin-readonly">Read-only</span>
        </div>
        <p className="dialin-tab-subtitle">
          Tell RacerZLab what the car is doing. It will give setup swings to test, one change at a time.
        </p>

        <form
          className="dialin-input-row dialin-command-bar"
          onSubmit={(event) => {
            event.preventDefault();
            void submitDialIn();
          }}
        >
          <input
            className="dialin-input"
            value={complaint}
            onChange={(event) => setComplaint(event.target.value)}
            placeholder="Example: loose off, tight center, RF is angry, nose is dragging, won't stay on bottom"
            aria-label="Driver complaint"
          />
          <button className="secondary-button" type="submit" disabled={!canSubmit} title="Check data and symptoms">
            <Search size={14} /> {loading ? "Checking run data" : "Check Data & Symptoms"}
          </button>
          <button className="secondary-button" type="button" onClick={clearDialIn} disabled={!complaint && !response && !error} title="Clear complaint">
            <X size={14} /> Clear
          </button>
        </form>

        <div className="dialin-rule-note">
          <Crosshair size={13} />
          <span>Pick one. Just one. Run clean laps and compare.</span>
        </div>
      </div>

      {error && (
        <div className="dialin-alert" role="alert">
          <AlertTriangle size={14} />
          <span>I couldn't run Dial-In on this run. Try again or check that the run is loaded.</span>
        </div>
      )}

      {!response && !error && (
        <div className="dialin-empty">{loading ? "Checking your complaint against the run data..." : "Tell me what the car is doing, and I'll check the data."}</div>
      )}

      {response && (
        <div className="dialin-result">
          <div className="dialin-summary-grid">
            <div>
              <span>Interpreted</span>
              <strong>{cleanLabel(response.interpreted_symptom)}</strong>
            </div>
            <div>
              <span>Phase</span>
              <strong>{cleanLabel(response.interpreted_phase, "Needs phase")}</strong>
            </div>
            <div>
              <span>Confidence</span>
              <strong className={`dialin-pill ${dialInTone(response.confidence_label)}`}>{response.confidence_label}</strong>
            </div>
            <div>
              <span>Data Profile</span>
              <strong className={`dialin-pill ${dialInTone(response.readiness_label)}`}>{response.readiness_label}</strong>
            </div>
          </div>

          <p className="dialin-driver-message">{response.driver_message}</p>

          {response.clarification.needed && (
            <div className="dialin-clarification">
              <strong>{response.clarification.question ?? "Clarify the complaint phase."}</strong>
              <div className="dialin-chip-row">
                {response.clarification.options.map((option) => (
                  <button className="dialin-chip dialin-chip-button" key={option} type="button" onClick={() => chooseClarification(option)}>
                    {option}
                  </button>
                ))}
              </div>
            </div>
          )}

          {!response.clarification.needed && response.top_swings.length === 0 && (
            <div className="dialin-empty">I need stronger data before ranking setup swings.</div>
          )}

          {!response.clarification.needed && response.top_swings.length > 0 && (
            <>
              <div className="dialin-section-header">
                <div>
                  <span>Possible swings</span>
                  <h3>Best first swings</h3>
                </div>
                <p>These are possible swings. Do not stack these changes. Pick one, test, then compare.</p>
              </div>
              <div className="dialin-swings">
                {primarySwings.map((swing) => (
                  <SwingCard swing={swing} key={swing.id} />
                ))}
              </div>

              {secondarySwings.length > 0 && (
                <>
                  <div className="dialin-section-header compact">
                    <div>
                      <span>Lower priority</span>
                      <h3>Other possible swings</h3>
                    </div>
                    <p>Still test one at a time. Use these when the first read does not match the driver feel.</p>
                  </div>
                  <div className="dialin-other-grid">
                    {secondarySwings.map((swing) => (
                      <SwingCard swing={swing} compact key={swing.id} />
                    ))}
                  </div>
                </>
              )}
            </>
          )}

          <div className="dialin-evidence-status">
            <span>Data Profile</span>
            <strong>{response.next_step ?? response.readiness_label}</strong>
            {hints.length > 0 && (
              <div className="dialin-chip-row">
                {hints.map((hint) => <span className="dialin-chip" key={hint}>{hint}</span>)}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
