/**
 * CompareBasket — compact persistent basket for collecting laps/runs to compare.
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

export function CompareBasket() {
  const { basket, setBaseline, setTest, swap, clear, remove, getWarnings, getReadiness } = useCompareBasket();
  const { setWorkspace } = useTelemetrySelection();
  const [expanded, setExpanded] = useState(false);

  const hasItems = basket.baseline != null || basket.test != null;
  const warnings = getWarnings();
  const readiness = getReadiness();

  const handleOpenCompare = useCallback(() => {
    setWorkspace("compare", "manual");
  }, [setWorkspace]);

  if (!hasItems && !expanded) return null;

  return (
    <div className="compare-basket">
      <div className="compare-basket-header">
        <button
          className="compare-basket-toggle"
          onClick={() => setExpanded(!expanded)}
          title={expanded ? "Collapse" : "Expand Compare Basket"}
        >
          <BarChart3 size={14} />
          <span>Compare {basket.baseline ? "•" : ""}{basket.test ? "•" : ""}</span>
        </button>
        {hasItems && (
          <div className="compare-basket-actions">
            <button className="compare-basket-action-btn" onClick={handleOpenCompare} title="Open Compare">
              <BarChart3 size={12} />
            </button>
            <button className="compare-basket-action-btn" onClick={clear} title="Clear All">
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>

      {expanded && (
        <div className="compare-basket-body">
          {/* Readiness badge */}
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
              {warnings.map((w, i) => (
                <p key={i} className="warning-line"><AlertTriangle size={10} /> {w}</p>
              ))}
            </div>
          )}

          {(!basket.baseline || !basket.test) && (
            <p className="compare-basket-hint">Add laps from Laps or Overview to compare.</p>
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
    <div className="compare-basket-slot">
      <div className="compare-basket-slot-header">
        <span className="compare-basket-slot-label">{label}</span>
        {item && (
          <button className="compare-basket-action-btn" onClick={onRemove} title={`Remove ${label}`}>
            <X size={10} />
          </button>
        )}
      </div>
      {item ? (
        <div className="compare-basket-slot-item">
          <span className="compare-basket-item-label">{item.label}</span>
          <span className="compare-basket-item-meta">
            {item.car && `${item.car} · `}{item.lap_time != null ? `${item.lap_time.toFixed(3)}s` : ""}
          </span>
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

/** Helper to create a BasketItem from lap data. */
export function makeBasketItem(
  runId: string,
  lapNumber: number | null,
  label: string,
  car: string | null,
  track: string | null,
  setupLabel: string | null,
  lapTime: number | null,
  tags: string[],
  draftStatus: string,
  engineeringValue: number | null,
  date?: string | null,
  sessionName?: string | null,
  hasSetupSnapshot?: boolean,
): BasketItem {
  return {
    id: `${runId}_${lapNumber ?? "run"}_${Date.now()}`,
    run_id: runId,
    lap_number: lapNumber,
    label,
    car,
    track,
    setup_label: setupLabel,
    lap_time: lapTime,
    classification_tags: tags,
    draft_status: draftStatus,
    engineering_value: engineeringValue,
    date: date ?? null,
    session_name: sessionName ?? null,
    has_setup_snapshot: hasSetupSnapshot ?? false,
  };
}
