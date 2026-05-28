/**
 * Compare Basket — lightweight context for collecting laps/runs to compare.
 *
 * Supports:
 * - baseline slot
 * - test slot
 * - optional queued items
 * - validation warnings (different car, track, draft, etc.)
 */

import { createContext, useCallback, useContext, useEffect, useReducer, type ReactNode } from "react";

export interface BasketItem {
  id: string;
  run_id: string;
  lap_number: number | null;
  label: string;
  car: string | null;
  track: string | null;
  setup_label: string | null;
  lap_time: number | null;
  classification_tags: string[];
  draft_status: string;
  engineering_value: number | null;
  /** Cross-session support */
  date: string | null;
  session_name: string | null;
  has_setup_snapshot: boolean;
}

export type BasketSlot = "baseline" | "test";

export interface CompareBasketState {
  baseline: BasketItem | null;
  test: BasketItem | null;
  queue: BasketItem[];
}

type BasketAction =
  | { type: "SET_BASELINE"; item: BasketItem }
  | { type: "SET_TEST"; item: BasketItem }
  | { type: "SWAP" }
  | { type: "CLEAR" }
  | { type: "REMOVE"; slot: BasketSlot }
  | { type: "ADD_TO_QUEUE"; item: BasketItem }
  | { type: "REMOVE_FROM_QUEUE"; id: string }
  | { type: "CLEAR_QUEUE" };

const STORAGE_KEY = "racelab_compare_basket";

function loadPersistedState(): CompareBasketState {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved) as CompareBasketState;
      // Validate shape — if malformed, return empty
      if (parsed && typeof parsed === "object" && "baseline" in parsed && "test" in parsed) {
        return parsed;
      }
    }
  } catch { /* ignore corrupt data */ }
  return { baseline: null, test: null, queue: [] };
}

const EMPTY: CompareBasketState = { baseline: null, test: null, queue: [] };

function basketReducer(state: CompareBasketState, action: BasketAction): CompareBasketState {
  switch (action.type) {
    case "SET_BASELINE":
      return { ...state, baseline: action.item };
    case "SET_TEST":
      return { ...state, test: action.item };
    case "SWAP":
      return { baseline: state.test, test: state.baseline, queue: state.queue };
    case "CLEAR":
      return { ...EMPTY };
    case "REMOVE":
      return { ...state, [action.slot]: null };
    case "ADD_TO_QUEUE":
      return { ...state, queue: [...state.queue, action.item] };
    case "REMOVE_FROM_QUEUE":
      return { ...state, queue: state.queue.filter((i) => i.id !== action.id) };
    case "CLEAR_QUEUE":
      return { ...state, queue: [] };
    default:
      return state;
  }
}

export type BasketReadiness = "ready" | "caution" | "not_valid" | "reference_mode";

type CompareBasketContextValue = {
  basket: CompareBasketState;
  setBaseline: (item: BasketItem) => void;
  setTest: (item: BasketItem) => void;
  swap: () => void;
  clear: () => void;
  remove: (slot: BasketSlot) => void;
  addToQueue: (item: BasketItem) => void;
  removeFromQueue: (id: string) => void;
  clearQueue: () => void;
  /** Validation warnings for the current baseline/test pair. */
  getWarnings: () => string[];
  /** Readiness state for the current basket pair. */
  getReadiness: () => { status: BasketReadiness; reason: string };
};

const CompareBasketContext = createContext<CompareBasketContextValue | null>(null);

export function CompareBasketProvider({ children }: { children: ReactNode }) {
  const [basket, dispatch] = useReducer(basketReducer, undefined, loadPersistedState);

  // Persist to localStorage on every change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(basket));
    } catch { /* ignore quota errors */ }
  }, [basket]);

  const setBaseline = useCallback((item: BasketItem) => dispatch({ type: "SET_BASELINE", item }), []);
  const setTest = useCallback((item: BasketItem) => dispatch({ type: "SET_TEST", item }), []);
  const swap = useCallback(() => dispatch({ type: "SWAP" }), []);
  const clear = useCallback(() => dispatch({ type: "CLEAR" }), []);
  const remove = useCallback((slot: BasketSlot) => dispatch({ type: "REMOVE", slot }), []);
  const addToQueue = useCallback((item: BasketItem) => dispatch({ type: "ADD_TO_QUEUE", item }), []);
  const removeFromQueue = useCallback((id: string) => dispatch({ type: "REMOVE_FROM_QUEUE", id }), []);
  const clearQueue = useCallback(() => dispatch({ type: "CLEAR_QUEUE" }), []);

  const getWarnings = useCallback((): string[] => {
    const w: string[] = [];
    const { baseline, test } = basket;
    if (!baseline || !test) return w;
    if (baseline.car && test.car && baseline.car !== test.car) {
      w.push("Different car — comparison may not be meaningful.");
    }
    if (baseline.track && test.track && baseline.track !== test.track) {
      w.push("Different track — comparison may not be meaningful.");
    }
    if (test.draft_status === "DRAFT_AFFECTED") {
      w.push("Test lap is draft-affected — setup conclusions limited.");
    }
    if (baseline.draft_status === "DRAFT_AFFECTED") {
      w.push("Baseline lap is draft-affected — reference may not be clean.");
    }
    if (baseline.run_id === test.run_id && baseline.lap_number === test.lap_number) {
      w.push("Same lap selected as baseline and test — this is a self-reference.");
    }
    if (baseline.run_id !== test.run_id) {
      w.push("Cross-session comparison — car/track/weather may differ.");
    }
    if (!baseline.has_setup_snapshot) {
      w.push("Baseline has no setup snapshot — setup diff unavailable.");
    }
    if (!test.has_setup_snapshot) {
      w.push("Test has no setup snapshot — setup diff unavailable.");
    }
    if (baseline.date && test.date && baseline.date !== test.date) {
      w.push("Different session dates — weather/track conditions may differ.");
    }
    return w;
  }, [basket]);

  const getReadiness = useCallback((): { status: BasketReadiness; reason: string } => {
    const { baseline, test } = basket;
    if (!baseline || !test) return { status: "not_valid", reason: "Both baseline and test are required." };
    if (baseline.run_id === test.run_id && baseline.lap_number === test.lap_number) {
      return { status: "reference_mode", reason: "Same lap selected — this is a self-reference." };
    }
    if (baseline.car && test.car && baseline.car !== test.car) {
      return { status: "not_valid", reason: "Different cars — comparison not meaningful." };
    }
    if (baseline.track && test.track && baseline.track !== test.track) {
      return { status: "not_valid", reason: "Different tracks — comparison not meaningful." };
    }
    const warnings = getWarnings();
    if (warnings.length >= 3) {
      return { status: "caution", reason: `${warnings.length} warnings — review before comparing.` };
    }
    if (warnings.length > 0) {
      return { status: "caution", reason: warnings[0] };
    }
    return { status: "ready", reason: "Ready to compare." };
  }, [basket, getWarnings]);

  return (
    <CompareBasketContext.Provider value={{ basket, setBaseline, setTest, swap, clear, remove, addToQueue, removeFromQueue, clearQueue, getWarnings, getReadiness }}>
      {children}
    </CompareBasketContext.Provider>
  );
}

export function useCompareBasket() {
  const ctx = useContext(CompareBasketContext);
  if (!ctx) throw new Error("useCompareBasket must be used within CompareBasketProvider");
  return ctx;
}
