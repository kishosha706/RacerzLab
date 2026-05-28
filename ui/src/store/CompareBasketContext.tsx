/**
 * Compare Basket — lightweight context for collecting laps/runs to compare.
 *
 * Supports:
 * - baseline slot
 * - test slot
 * - optional queued items
 * - validation warnings (different car, track, draft, etc.)
 */

import { createContext, useCallback, useContext, useReducer, type ReactNode } from "react";

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
};

const CompareBasketContext = createContext<CompareBasketContextValue | null>(null);

export function CompareBasketProvider({ children }: { children: ReactNode }) {
  const [basket, dispatch] = useReducer(basketReducer, EMPTY);

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
    if (baseline.run_id === test.run_id && baseline.lap_number === test.lap_number) {
      w.push("Same lap selected as baseline and test — this is a self-reference.");
    }
    return w;
  }, [basket]);

  return (
    <CompareBasketContext.Provider value={{ basket, setBaseline, setTest, swap, clear, remove, addToQueue, removeFromQueue, clearQueue, getWarnings }}>
      {children}
    </CompareBasketContext.Provider>
  );
}

export function useCompareBasket() {
  const ctx = useContext(CompareBasketContext);
  if (!ctx) throw new Error("useCompareBasket must be used within CompareBasketProvider");
  return ctx;
}
