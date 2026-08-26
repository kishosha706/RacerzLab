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
import type { EngineeringObjective } from "../types/crewChief";
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
  objective: EngineeringObjective | null;
  retry: () => void;
  invalidate: () => void;
  selectObjective: (objective: EngineeringObjective) => void;
  replaceRevision: (revision: EngineeringCaseRevision) => boolean;
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
  const scopeKey = `${runId}:${sessionId}`;
  const objectiveRef = useRef<{ scopeKey: string; value: EngineeringObjective | null }>({
    scopeKey,
    value: null,
  });
  const revisionRef = useRef<{
    requestKey: string | null;
    revision: EngineeringCaseRevision | null;
  }>({ requestKey: null, revision: null });
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
    revisionRef.current = { requestKey, revision: null };
    setState({ requestKey, revision: null, status: "loading", error: null });
    void fetchEngineeringCase(runId, sessionId, {
      objective: objectiveRef.current.scopeKey === scopeKey
        ? objectiveRef.current.value
        : null,
    })
      .then((revision) => {
        if (cancelled || sequence !== requestSequence.current) return;
        objectiveRef.current = {
          scopeKey,
          value: revision.case.objective_id as EngineeringObjective,
        };
        revisionRef.current = { requestKey, revision };
        setState({ requestKey, revision, status: "ready", error: null });
      })
      .catch((reason: unknown) => {
        if (cancelled || sequence !== requestSequence.current) return;
        revisionRef.current = { requestKey, revision: null };
        setState({
          requestKey,
          revision: null,
          status: "error",
          error: reason instanceof Error ? reason.message : "Engineering Case is unavailable.",
        });
      });
    return () => { cancelled = true; };
  }, [requestKey, runId, scopeKey, sessionId]);

  const retry = useCallback(() => {
    requestSequence.current += 1;
    revisionRef.current = { requestKey: null, revision: null };
    setRetryToken((value) => value + 1);
  }, []);
  const invalidate = useCallback(() => {
    requestSequence.current += 1;
    revisionRef.current = { requestKey: null, revision: null };
    setState((current) => ({ ...current, revision: null, status: "stale", error: null }));
    setInvalidationToken((value) => value + 1);
  }, []);
  const selectObjective = useCallback((objective: EngineeringObjective) => {
    if (objectiveRef.current.scopeKey === scopeKey
      && objectiveRef.current.value === objective) return;
    objectiveRef.current = { scopeKey, value: objective };
    requestSequence.current += 1;
    revisionRef.current = { requestKey: null, revision: null };
    setState((current) => ({ ...current, revision: null, status: "stale", error: null }));
    setInvalidationToken((value) => value + 1);
  }, [scopeKey]);
  const replaceRevision = useCallback((revision: EngineeringCaseRevision) => {
    if (revision.case.run_id !== runId || revision.case.session_id !== sessionId) return false;
    const current = revisionRef.current;
    if (current.requestKey !== requestKey || current.revision === null) return false;
    const currentRevision = current.revision;
    const idempotent = revision.case_id === currentRevision.case_id
      && revision.case_revision === currentRevision.case_revision
      && revision.case_sha256 === currentRevision.case_sha256;
    if (idempotent) return true;
    const exactSuccessor = revision.case_id === currentRevision.case_id
      && revision.case_revision === currentRevision.case_revision + 1
      && revision.previous_case_sha256 === currentRevision.case_sha256;
    if (!exactSuccessor) return false;
    requestSequence.current += 1;
    objectiveRef.current = {
      scopeKey,
      value: revision.case.objective_id as EngineeringObjective,
    };
    revisionRef.current = { requestKey, revision };
    setState({ requestKey, revision, status: "ready", error: null });
    return true;
  }, [requestKey, runId, scopeKey, sessionId]);

  const value = useMemo<EngineeringCaseContextValue>(() => ({
    revision: state.requestKey === requestKey ? state.revision : null,
    engineeringCase: state.requestKey === requestKey ? state.revision?.case ?? null : null,
    status: state.requestKey === requestKey ? state.status : "loading",
    error: state.requestKey === requestKey ? state.error : null,
    objective: state.requestKey === requestKey
      ? (state.revision?.case.objective_id as EngineeringObjective | undefined)
        ?? (objectiveRef.current.scopeKey === scopeKey ? objectiveRef.current.value : null)
      : null,
    retry,
    invalidate,
    selectObjective,
    replaceRevision,
  }), [invalidate, replaceRevision, requestKey, retry, scopeKey, selectObjective, state]);

  return <EngineeringCaseContext.Provider value={value}>{children}</EngineeringCaseContext.Provider>;
}

export function useEngineeringCase(): EngineeringCaseContextValue {
  const value = useContext(EngineeringCaseContext);
  if (value === null) throw new Error("useEngineeringCase requires EngineeringCaseProvider");
  return value;
}
