/**
 * CompareBasket - compact persistent basket for collecting baseline/test evidence.
 *
 * Lives at the bottom of the nav rail or as a bottom-right drawer.
 * Visible only when at least one item is added.
 */

import { AlertTriangle, ArrowLeftRight, BarChart3, CheckCircle, Trash2, X } from "lucide-react";
import { useCallback, useState } from "react";
import { useCompareBasket, type BasketItem, type BasketReadiness } from "../store/CompareBasketContext";
import { useTelemetrySelection } from "../store/TelemetrySelectionContext";

const READINESS_COLORS: Record<BasketReadiness, string> = {
  ready: "#22c55e",
  caution: "#f59e0b",
  not_valid: "#ef4444",
  reference_mode: "#38bdf8",
};

function describeBasketScope(item: BasketItem): string {
  if (item.lap_scope === "lap_window" && item.lap_window_start != null && item.lap_window_end != null) {
    return `Window ${item.lap_window_start}-${item.lap_window_end}`;
  }
  if (item.lap_number != null) return `Lap ${item.lap_number}`;
  return "Run-level";
}

function describeRepresentativeLap(item: BasketItem): string | null {
  if (item.lap_scope !== "lap_window" || item.representative_lap == null) return null;
  return `Rep Lap ${item.representative_lap}`;
}

function describeBasketBasis(item: BasketItem): string | null {
  switch (item.value_basis) {
    case "selected_window":
      return "Selected window";
    case "full_lap":
      return "Full lap";
    case "selected_sample":
      return "Selected sample";
    case "run_level":
      return "Run-level";
    default:
      return null;
  }
}

export function CompareBasket() {
  const { basket, swap, clear, remove, getWarnings, getReadiness } = useCompareBasket();
  const { setWorkspace } = useTelemetrySelection();
  const [expanded, setExpanded] = useState(false);

  const hasItems = basket.baseline != null || basket.test != null;
  const warnings = getWarnings();
  const readiness = getReadiness();

  const handleReviewInLaps = useCallback(() => {
    setWorkspace("laps", "manual");
  }, [setWorkspace]);

  if (!hasItems && !expanded) return null;

  return (
    <div className="compare-basket">
      <div className="compare-basket-header">
        <button
          className="compare-basket-toggle"
          onClick={() => setExpanded(!expanded)}
          title={expanded ? "Collapse" : "Expand Test Basket"}
          aria-label={expanded ? "Collapse Test Basket" : "Expand Test Basket"}
          aria-expanded={expanded}
        >
          <BarChart3 size={14} />
          <span>Test Basket {basket.baseline ? "•" : ""}{basket.test ? "•" : ""}</span>
        </button>
        {hasItems && (
          <div className="compare-basket-actions">
            <button className="compare-basket-action-btn" onClick={handleReviewInLaps} title="Review in Laps" aria-label="Review Test Basket in Laps">
              <BarChart3 size={12} />
            </button>
            <button className="compare-basket-action-btn" onClick={clear} title="Clear All" aria-label="Clear Test Basket">
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>

      {expanded && (
        <div className="compare-basket-body">
          {basket.baseline && basket.test && (
            <div
              className="compare-basket-readiness"
              style={{
                background: `${READINESS_COLORS[readiness.status]}10`,
                borderColor: `${READINESS_COLORS[readiness.status]}30`,
                color: READINESS_COLORS[readiness.status],
              }}
            >
              {readiness.status === "ready" ? <CheckCircle size={12} /> : <AlertTriangle size={12} />}
              <span style={{ fontWeight: 600, textTransform: "uppercase", fontSize: 10, letterSpacing: "0.04em" }}>
                {readiness.status.replace(/_/g, " ")}
              </span>
              <span style={{ fontSize: 10, opacity: 0.8 }}>— {readiness.reason}</span>
            </div>
          )}

          {basket.baseline && basket.test && readiness.status === "ready" && (
            <button
              className="compare-basket-ready-btn"
              onClick={handleReviewInLaps}
              style={{
                background: READINESS_COLORS.ready,
                color: "white",
                border: "none",
                padding: "6px 12px",
                borderRadius: 4,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                marginTop: 8,
                width: "100%",
              }}
            >
              Review in Laps
            </button>
          )}

          {basket.baseline && basket.test && readiness.status === "caution" && (
            <p style={{ fontSize: 11, color: READINESS_COLORS.caution, margin: "6px 0", lineHeight: 1.4 }}>
              Caution: {readiness.reason}
            </p>
          )}
          {basket.baseline && basket.test && readiness.status === "not_valid" && (
            <p style={{ fontSize: 11, color: READINESS_COLORS.not_valid, margin: "6px 0", lineHeight: 1.4 }}>
              Not valid: {readiness.reason}
            </p>
          )}
          {basket.baseline && basket.test && readiness.status === "reference_mode" && (
            <p style={{ fontSize: 11, color: READINESS_COLORS.reference_mode, margin: "6px 0", lineHeight: 1.4 }}>
              Reference mode: {readiness.reason}
            </p>
          )}

          {basket.baseline && !basket.test && (
            <p style={{ fontSize: 11, color: "#8d9aaa", margin: "8px 0" }}>1/2 — Add test evidence</p>
          )}
          {!basket.baseline && basket.test && (
            <p style={{ fontSize: 11, color: "#8d9aaa", margin: "8px 0" }}>1/2 — Add baseline evidence</p>
          )}

          <BasketSlotDisplay
            label="Baseline"
            slot="baseline"
            item={basket.baseline}
            onSet={() => {}}
            onRemove={() => remove("baseline")}
          />
          <BasketSlotDisplay
            label="Test"
            slot="test"
            item={basket.test}
            onSet={() => {}}
            onRemove={() => remove("test")}
          />

          {basket.baseline && basket.test && (
            <button className="compare-basket-swap-btn" onClick={swap}>
              <ArrowLeftRight size={12} /> Swap
            </button>
          )}

          {warnings.length > 0 && (
            <div className="compare-basket-warnings">
              {warnings.map((warning, index) => (
                <p key={index} className="warning-line"><AlertTriangle size={10} /> {warning}</p>
              ))}
            </div>
          )}

          {(!basket.baseline || !basket.test) && (
            <p className="compare-basket-hint">Add laps or windows from Laps to stage a comparison.</p>
          )}
        </div>
      )}
    </div>
  );
}

function BasketSlotDisplay({
  label,
  item,
  onRemove,
}: {
  label: string;
  slot: "baseline" | "test";
  item: BasketItem | null;
  onSet: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="compare-basket-slot" tabIndex={0}>
      <div className="compare-basket-slot-header">
        <span className="compare-basket-slot-label">{label}</span>
        {item && (
          <button className="compare-basket-action-btn" onClick={onRemove} title={`Remove ${label}`} aria-label={`Remove ${label} slot`}>
            <X size={10} />
          </button>
        )}
      </div>
      {item ? (
        <div className="compare-basket-slot-item">
          <span className="compare-basket-item-label">{item.label}</span>
          <span className="compare-basket-item-meta">
            {describeBasketScope(item)}
            {item.lap_time != null ? ` · ${item.lap_time.toFixed(3)}s` : ""}
            {item.car ? ` · ${item.car}` : ""}
          </span>
          {(item.trust_tier || describeBasketBasis(item)) && (
            <span className="compare-basket-item-meta">
              {item.trust_tier ? `Trust: ${item.trust_tier}` : ""}
              {item.trust_tier && describeBasketBasis(item) ? " · " : ""}
              {describeBasketBasis(item) ?? ""}
            </span>
          )}
          {describeRepresentativeLap(item) && (
            <span className="compare-basket-item-meta">{describeRepresentativeLap(item)}</span>
          )}
          {item.engineering_value != null && (
            <span className="compare-basket-item-ev">EV: {item.engineering_value.toFixed(0)}</span>
          )}
        </div>
      ) : (
        <span className="compare-basket-empty">Empty</span>
      )}
    </div>
  );
}

/** Helper to create a BasketItem from lap or window data. */
export function makeBasketItem(
  runId: string,
  lapNumber: number | null,
  label: string,
  car: string | null,
  track: string | null,
  setupLabel: string | null,
  lapTime: number | null,
  tags: string[],
  engineeringValue: number | null,
  date?: string | null,
  sessionName?: string | null,
  hasSetupSnapshot?: boolean,
  metadata?: {
    lapScope?: BasketItem["lap_scope"];
    lapWindowStart?: number | null;
    lapWindowEnd?: number | null;
    representativeLap?: number | null;
    trustTier?: string | null;
    valueBasis?: BasketItem["value_basis"];
  },
): BasketItem {
  return {
    id: `${runId}_${lapNumber ?? "run"}_${Date.now()}`,
    run_id: runId,
    lap_number: lapNumber,
    lap_scope: metadata?.lapScope ?? null,
    lap_window_start: metadata?.lapWindowStart ?? null,
    lap_window_end: metadata?.lapWindowEnd ?? null,
    representative_lap: metadata?.representativeLap ?? null,
    label,
    car,
    track,
    setup_label: setupLabel,
    lap_time: lapTime,
    classification_tags: tags,
    engineering_value: engineeringValue,
    date: date ?? null,
    session_name: sessionName ?? null,
    has_setup_snapshot: hasSetupSnapshot ?? false,
    trust_tier: metadata?.trustTier ?? null,
    value_basis: metadata?.valueBasis ?? null,
  };
}
