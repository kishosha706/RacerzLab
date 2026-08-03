import { AlertTriangle, ClipboardList, Crosshair, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { analyzeRunDialIn } from "../api/client";
import { useCompareBasket } from "../store/CompareBasketContext";
import type { DialInResponse, DialInSwing, RunOverview } from "../types/telemetry";

type DialInTabProps = { overview: RunOverview | null };

const DIAL_IN_INITIAL_LIMIT = 9;
const SHOW_MORE_STEP = 9;
const DIAL_IN_REQUEST_LIMIT = DIAL_IN_INITIAL_LIMIT + SHOW_MORE_STEP;

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

function formatTargetList(swing: DialInSwing): string {
  const labels = swing.validate_with_labels ?? swing.validate_with.map((value) => value.replace(/_/g, " "));
  const targets = labels.filter((item, index, all) => item && all.indexOf(item) === index);
  return targets.join(", ") || "the same corner phase";
}

function garageLeverLabel(swing: DialInSwing): string | null {
  if (swing.setup_area === "shock_collar" || swing.setup_area.includes("ride_height")) {
    return "Garage note: use the named Ride Height fields. If this car exposes collar or perch offsets instead, recheck cross weight after the change.";
  }
  return null;
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
  const helper = garageLeverLabel(swing);
  return (
    <article className={`dialin-swing-card${compact ? " compact" : ""}`}>
      <header>
        <div>
          <span>{cleanLabel(swing.setup_area, "Setup area")}</span>
          <h3>{swing.title}</h3>
          <p className="dialin-change-this"><span>Make this setup change:</span> {swing.change_this}</p>
          <p className="dialin-garage-helper">Garage control{(swing.control_keys?.length ?? 0) > 1 ? "s" : ""}: {swing.garage_lever}</p>
          <p className="dialin-garage-helper"><span>Why this size:</span> {swing.change_size_explanation}</p>
          {helper && <p className="dialin-garage-note">{helper}</p>}
        </div>
        <div className="dialin-card-pills">
          <span className="dialin-mini-pill">{swing.change_size_label}</span>
          <span className="dialin-mini-pill">{swing.influence_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.risk_label)}`}>{swing.risk_label}</span>
          <span className={`dialin-mini-pill ${dialInTone(swing.readiness_label)}`}>{swing.readiness_label}</span>
        </div>
      </header>
      <div className="dialin-action-grid">
        <div><span>Expected improvement</span><p>{swing.effect}</p></div>
        <div><span>Trade-off</span><p>{swing.counter_effect}</p></div>
        <div><span>What this control does</span><p>{swing.control_expectation}</p></div>
        <div><span>Related settings to recheck</span><p>{swing.control_guardrail}</p></div>
        <div><span>Keep it if</span><p>{swing.keep_if}</p></div>
        <div><span>Undo it if</span><p>{swing.undo_if}</p></div>
        <div><span>Test plan</span><p>{swing.one_change_test}</p></div>
        <div>
          <span>Evidence signals</span>
          <p>{formatTargetList(swing)}</p>
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
  const [shownSwingCount, setShownSwingCount] = useState(DIAL_IN_INITIAL_LIMIT);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      setComplaint(window.sessionStorage.getItem(storageKey) ?? "");
    } catch {
      setComplaint("");
    }
    setResponse(null);
    setShownSwingCount(DIAL_IN_INITIAL_LIMIT);
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
        limit: DIAL_IN_REQUEST_LIMIT,
        include_debug_evidence: false,
      });
      setResponse(nextResponse);
      setShownSwingCount(DIAL_IN_INITIAL_LIMIT);
    } catch (caught) {
      setResponse(null);
      setShownSwingCount(DIAL_IN_INITIAL_LIMIT);
      setError(caught instanceof Error ? caught.message : "Dial-in request failed.");
    } finally {
      setLoading(false);
    }
  }, [basket.baseline, complaint, loading, overview]);

  const clearDialIn = useCallback(() => {
    setComplaint("");
    setResponse(null);
    setShownSwingCount(DIAL_IN_INITIAL_LIMIT);
    setError(null);
  }, []);

  const chooseClarification = useCallback((option: string) => {
    const base = response?.complaint_raw.trim() || complaint.trim();
    const normalized = base.toLowerCase();
    const refinement = option === "Whole corner" ? "center" : option.toLowerCase();
    const nextComplaint = normalized.includes(refinement) ? base : `${base} ${refinement}`;
    setComplaint(nextComplaint.trim());
    setResponse(null);
    setShownSwingCount(DIAL_IN_INITIAL_LIMIT);
    setError(null);
  }, [complaint, response]);

  const hints = response ? dialInEvidenceHints(response) : [];
  const primarySwings = useMemo(() => response?.top_swings.slice(0, 3) ?? [], [response]);
  const secondarySwings = useMemo(() => response?.top_swings.slice(3, shownSwingCount) ?? [], [response, shownSwingCount]);
  const remainingSwingCount = response ? Math.max(0, response.top_swings.length - shownSwingCount) : 0;
  const nextRevealCount = Math.min(SHOW_MORE_STEP, remainingSwingCount);
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
          Tell RacerZLab what the car is doing. It will rank specific setup changes to test, one change at a time.
        </p>
        {!overview.setup_snapshot && (
          <div className="dialin-alert limited" role="status">
            <AlertTriangle size={14} />
            <span>Setup snapshot unavailable. Garage-specific recommendations are limited until setup data is available, so Dial-In will stay conservative.</span>
          </div>
        )}

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
          <span>Pick one change. Just one. Run clean laps and compare.</span>
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
            <div className="dialin-empty">I need stronger data before ranking setup changes.</div>
          )}

          {!response.clarification.needed && response.top_swings.length > 0 && (
            <>
              <div className="dialin-section-header">
                <div>
                  <span>Ranked changes</span>
                  <h3>Best first setup changes</h3>
                </div>
                <p>These are setup changes to test. Do not stack them. Pick one, test, then compare.</p>
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
                      <h3>Other setup changes</h3>
                    </div>
                    <p>Use these only if the first change does not match the driver feel. Test one at a time.</p>
                  </div>
                  <div className="dialin-other-grid">
                    {secondarySwings.map((swing) => (
                      <SwingCard swing={swing} compact key={swing.id} />
                    ))}
                  </div>
                  {remainingSwingCount > 0 && (
                    <div className="dialin-show-more-row">
                      <button
                        className="secondary-button dialin-show-more-button"
                        type="button"
                        onClick={() => setShownSwingCount((count) => Math.min(count + SHOW_MORE_STEP, response.top_swings.length))}
                      >
                        Show {nextRevealCount} more setup changes
                      </button>
                    </div>
                  )}
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
