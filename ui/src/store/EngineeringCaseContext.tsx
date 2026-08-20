import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { fetchEngineeringCase } from "../api/client";
import type { CanonicalEngineeringCase, EngineeringCaseRevision } from "../types/engineeringCase";

type EngineeringCaseState = {
  requestKey: string | null;
  revision: EngineeringCaseRevision | null;
  status: "idle" | "loading" | "ready" | "stale" | "error";
  error: string | null;
};

type EngineeringCaseContextValue = {
  revision: EngineeringCaseRevision | null;
  engineeringCase: CanonicalEngineeringCase | null;
  status: EngineeringCaseState["status"];
  error: string | null;
  retry: () => void;
  invalidate: () => void;
  replaceRevision: (revision: EngineeringCaseRevision) => void;
};

const EngineeringCaseContext = createContext<EngineeringCaseContextValue | null>(null);

export function EngineeringCaseProvider({
  runId,
  sessionId,
  children,
}: {
  runId: string;
  sessionId: string;
  children: ReactNode;
}) {
  const [retryToken, setRetryToken] = useState(0);
  const [invalidationToken, setInvalidationToken] = useState(0);
  const requestSequence = useRef(0);
  const [state, setState] = useState<EngineeringCaseState>({
    requestKey: null,
    revision: null,
    status: "idle",
    error: null,
  });
  const requestKey = `${runId}:${sessionId}:${retryToken}:${invalidationToken}`;

  useEffect(() => {
    const sequence = ++requestSequence.current;
    let cancelled = false;
    setState({ requestKey, revision: null, status: "loading", error: null });
    void fetchEngineeringCase(runId, sessionId)
      .then((revision) => {
        if (cancelled || sequence !== requestSequence.current) return;
        setState({ requestKey, revision, status: "ready", error: null });
      })
      .catch((reason: unknown) => {
        if (cancelled || sequence !== requestSequence.current) return;
        setState({
          requestKey,
          revision: null,
          status: "error",
          error: reason instanceof Error ? reason.message : "Engineering Case is unavailable.",
        });
      });
    return () => { cancelled = true; };
  }, [requestKey, runId, sessionId]);

  const retry = useCallback(() => setRetryToken((value) => value + 1), []);
  const invalidate = useCallback(() => {
    requestSequence.current += 1;
    setState((current) => ({ ...current, revision: null, status: "stale", error: null }));
    setInvalidationToken((value) => value + 1);
  }, []);
  const replaceRevision = useCallback((revision: EngineeringCaseRevision) => {
    if (revision.case.run_id !== runId || revision.case.session_id !== sessionId) return;
    requestSequence.current += 1;
    setState({ requestKey, revision, status: "ready", error: null });
  }, [requestKey, runId, sessionId]);

  const value = useMemo<EngineeringCaseContextValue>(() => ({
    revision: state.requestKey === requestKey ? state.revision : null,
    engineeringCase: state.requestKey === requestKey ? state.revision?.case ?? null : null,
    status: state.requestKey === requestKey ? state.status : "loading",
    error: state.requestKey === requestKey ? state.error : null,
    retry,
    invalidate,
    replaceRevision,
  }), [invalidate, replaceRevision, requestKey, retry, state]);

  return <EngineeringCaseContext.Provider value={value}>{children}</EngineeringCaseContext.Provider>;
}

export function useEngineeringCase(): EngineeringCaseContextValue {
  const value = useContext(EngineeringCaseContext);
  if (value === null) throw new Error("useEngineeringCase requires EngineeringCaseProvider");
  return value;
}
